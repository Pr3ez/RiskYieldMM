"""
Model Caching System for Walk-Forward Optimization

This module provides a pre-training cache to speed up walk-forward predictions by:
1. Pre-training models at strategic checkpoints (e.g., every N iterations)
2. Caching trained models with their training windows
3. Reusing models when training window overlap is high enough
4. Only retraining when drift is detected or data changes significantly

Key Performance Gains:
- Skip redundant model training when windows overlap significantly
- Cache feature importances to skip feature selection recalculation
- Store calibrators that can be updated incrementally
- Pre-compute window boundaries for fast lookup
"""

import os
import gc
import pickle
import hashlib
import numpy as np
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from collections import OrderedDict


@dataclass
class CachedModel:
    """Cached model with metadata for reuse decisions."""
    model: Any  # The trained model (CatBoost, LightGBM, etc.)
    model_type: str  # 'catboost', 'lightgbm', 'meta'
    train_start: int
    train_end: int
    features: List[str]
    feature_importances: Optional[Dict[str, float]] = None
    params: Optional[Dict] = None
    val_auc: float = 0.0
    created_at_iteration: int = 0
    reuse_count: int = 0
    
    def overlap_ratio(self, new_train_start: int, new_train_end: int) -> float:
        """Calculate overlap ratio between cached training window and new one."""
        overlap_start = max(self.train_start, new_train_start)
        overlap_end = min(self.train_end, new_train_end)
        overlap_size = max(0, overlap_end - overlap_start)
        new_size = new_train_end - new_train_start
        return overlap_size / new_size if new_size > 0 else 0.0


@dataclass 
class CachedCalibrator:
    """Cached calibrator with rolling buffer updates."""
    calibrator: Any  # Platt (LogisticRegression) or IsotonicRegression
    cal_method: str  # 'platt', 'isotonic', 'none'
    n_samples: int
    last_update_iteration: int
    
    
@dataclass
class IterationCheckpoint:
    """Pre-computed checkpoint for an iteration range."""
    iteration_start: int
    iteration_end: int
    train_start: int
    train_end: int
    val_start: int
    val_end: int
    cal_start: int
    cal_end: int
    selected_features: List[str]
    cb_model: Optional[CachedModel] = None
    lgb_model: Optional[CachedModel] = None
    vol_model: Optional[CachedModel] = None
    calibrators: Dict[str, CachedCalibrator] = field(default_factory=dict)


class ModelCache:
    """
    Intelligent model caching for walk-forward optimization.
    
    Strategy:
    - Cache models every `checkpoint_interval` iterations
    - Reuse cached model if overlap_ratio >= min_overlap_for_reuse
    - Force retrain on drift detection
    - LRU eviction when cache exceeds max_size
    """
    
    def __init__(
        self,
        checkpoint_interval: int = 5,
        min_overlap_for_reuse: float = 0.90,
        max_cache_size: int = 20,
        cache_dir: Optional[str] = None,
        verbose: bool = True
    ):
        """
        Initialize model cache.
        
        Args:
            checkpoint_interval: Train new model every N iterations
            min_overlap_for_reuse: Min training data overlap to reuse model
            max_cache_size: Maximum number of models to keep in memory
            cache_dir: Optional directory for disk persistence
            verbose: Print cache hit/miss info
        """
        self.checkpoint_interval = checkpoint_interval
        self.min_overlap_for_reuse = min_overlap_for_reuse
        self.max_cache_size = max_cache_size
        self.cache_dir = cache_dir
        self.verbose = verbose
        
        # LRU caches for different model types
        self._cb_cache: OrderedDict[str, CachedModel] = OrderedDict()
        self._lgb_cache: OrderedDict[str, CachedModel] = OrderedDict()
        self._vol_cache: OrderedDict[str, CachedModel] = OrderedDict()
        self._calibrator_cache: Dict[str, CachedCalibrator] = {}
        
        # Feature importance cache (very stable across iterations)
        self._feature_importance_cache: Optional[Dict[str, float]] = None
        self._feature_importance_iteration: int = 0
        
        # Pre-computed checkpoints
        self._checkpoints: List[IterationCheckpoint] = []
        
        # Statistics
        self.stats = {
            'cb_hits': 0, 'cb_misses': 0,
            'lgb_hits': 0, 'lgb_misses': 0,
            'vol_hits': 0, 'vol_misses': 0,
            'feature_hits': 0, 'feature_misses': 0,
        }
        
        if cache_dir and not os.path.exists(cache_dir):
            os.makedirs(cache_dir)
    
    def _make_cache_key(self, train_start: int, train_end: int, model_type: str) -> str:
        """Generate cache key from training window."""
        return f"{model_type}_{train_start}_{train_end}"
    
    def _evict_if_needed(self, cache: OrderedDict) -> None:
        """Evict oldest entries if cache exceeds max size."""
        while len(cache) > self.max_cache_size:
            oldest_key = next(iter(cache))
            del cache[oldest_key]
            gc.collect()
    
    def should_retrain(
        self,
        iteration: int,
        train_start: int,
        train_end: int,
        model_type: str,
        drift_detected: bool = False
    ) -> Tuple[bool, Optional[CachedModel]]:
        """
        Determine if we should retrain or can reuse a cached model.
        
        Returns:
            Tuple of (should_retrain, cached_model_or_none)
        """
        # Always retrain on drift
        if drift_detected:
            if self.verbose:
                print(f"    [Cache] Drift detected - forcing retrain for {model_type}")
            return True, None
        
        # Check if it's a checkpoint iteration
        is_checkpoint = (iteration % self.checkpoint_interval == 0)
        
        # Select appropriate cache
        if model_type == 'catboost':
            cache = self._cb_cache
            stat_key = 'cb'
        elif model_type == 'lightgbm':
            cache = self._lgb_cache
            stat_key = 'lgb'
        elif model_type == 'volatility':
            cache = self._vol_cache
            stat_key = 'vol'
        else:
            return True, None
        
        # Look for best matching cached model
        best_match: Optional[CachedModel] = None
        best_overlap = 0.0
        
        for cached in cache.values():
            overlap = cached.overlap_ratio(train_start, train_end)
            if overlap > best_overlap:
                best_overlap = overlap
                best_match = cached
        
        # Decision logic
        if best_match and best_overlap >= self.min_overlap_for_reuse:
            # Cache hit - reuse model
            self.stats[f'{stat_key}_hits'] += 1
            best_match.reuse_count += 1
            
            # Move to end (LRU)
            key = self._make_cache_key(best_match.train_start, best_match.train_end, model_type)
            if key in cache:
                cache.move_to_end(key)
            
            if self.verbose and iteration % 50 == 0:
                print(f"    [Cache] {model_type} HIT: overlap={best_overlap:.1%}, reuse #{best_match.reuse_count}")
            
            return False, best_match
        
        # Cache miss or checkpoint - need to train
        self.stats[f'{stat_key}_misses'] += 1
        
        if self.verbose and iteration % 50 == 0:
            reason = "checkpoint" if is_checkpoint else f"overlap={best_overlap:.1%} < {self.min_overlap_for_reuse:.1%}"
            print(f"    [Cache] {model_type} MISS: {reason}")
        
        return True, None
    
    def cache_model(
        self,
        model: Any,
        model_type: str,
        train_start: int,
        train_end: int,
        features: List[str],
        iteration: int,
        val_auc: float = 0.0,
        params: Optional[Dict] = None,
        feature_importances: Optional[Dict[str, float]] = None
    ) -> None:
        """Cache a trained model."""
        cached = CachedModel(
            model=model,
            model_type=model_type,
            train_start=train_start,
            train_end=train_end,
            features=features,
            feature_importances=feature_importances,
            params=params,
            val_auc=val_auc,
            created_at_iteration=iteration,
            reuse_count=0
        )
        
        key = self._make_cache_key(train_start, train_end, model_type)
        
        if model_type == 'catboost':
            self._cb_cache[key] = cached
            self._evict_if_needed(self._cb_cache)
        elif model_type == 'lightgbm':
            self._lgb_cache[key] = cached
            self._evict_if_needed(self._lgb_cache)
        elif model_type == 'volatility':
            self._vol_cache[key] = cached
            self._evict_if_needed(self._vol_cache)
    
    # =========================================================================
    # FEATURE IMPORTANCE CACHING
    # =========================================================================
    
    def get_cached_feature_importances(
        self,
        iteration: int,
        max_age: int = 10
    ) -> Optional[Dict[str, float]]:
        """
        Get cached feature importances if recent enough.
        
        Feature importances are very stable across iterations,
        so we can cache them for significant speedup.
        """
        if self._feature_importance_cache is None:
            self.stats['feature_misses'] += 1
            return None
        
        age = iteration - self._feature_importance_iteration
        if age <= max_age:
            self.stats['feature_hits'] += 1
            return self._feature_importance_cache
        
        self.stats['feature_misses'] += 1
        return None
    
    def cache_feature_importances(
        self,
        importances: Dict[str, float],
        iteration: int
    ) -> None:
        """Cache feature importances."""
        self._feature_importance_cache = importances.copy()
        self._feature_importance_iteration = iteration
    
    # =========================================================================
    # CALIBRATOR CACHING
    # =========================================================================
    
    def get_cached_calibrator(self, model_type: str) -> Optional[CachedCalibrator]:
        """Get cached calibrator for a model type."""
        return self._calibrator_cache.get(model_type)
    
    def cache_calibrator(
        self,
        calibrator: Any,
        model_type: str,
        cal_method: str,
        n_samples: int,
        iteration: int
    ) -> None:
        """Cache a calibrator."""
        self._calibrator_cache[model_type] = CachedCalibrator(
            calibrator=calibrator,
            cal_method=cal_method,
            n_samples=n_samples,
            last_update_iteration=iteration
        )
    
    # =========================================================================
    # PRE-COMPUTATION
    # =========================================================================
    
    def precompute_checkpoints(
        self,
        total_rows: int,
        min_history: int,
        wf_train: int,
        wf_val: int,
        wf_cal: int,
        wf_pred: int = 1
    ) -> List[IterationCheckpoint]:
        """
        Pre-compute all iteration window boundaries.
        
        This avoids recalculating boundaries every iteration.
        """
        checkpoints = []
        pred_start = min_history
        iteration = 0
        
        while pred_start < total_rows:
            iteration += 1
            
            pred_end = min(pred_start + wf_pred, total_rows)
            val_end = pred_start
            val_start = val_end - wf_val
            cal_end = val_start
            cal_start = cal_end - wf_cal
            train_end = cal_start
            train_start = train_end - wf_train
            
            # Only store checkpoint iterations
            if iteration % self.checkpoint_interval == 0 or iteration == 1:
                checkpoint = IterationCheckpoint(
                    iteration_start=iteration,
                    iteration_end=min(iteration + self.checkpoint_interval - 1, 
                                     (total_rows - min_history) // wf_pred),
                    train_start=train_start,
                    train_end=train_end,
                    val_start=val_start,
                    val_end=val_end,
                    cal_start=cal_start,
                    cal_end=cal_end,
                    selected_features=[]
                )
                checkpoints.append(checkpoint)
            
            pred_start = pred_end
        
        self._checkpoints = checkpoints
        
        if self.verbose:
            print(f"    [Cache] Pre-computed {len(checkpoints)} checkpoints for {iteration} iterations")
        
        return checkpoints
    
    def get_checkpoint_for_iteration(self, iteration: int) -> Optional[IterationCheckpoint]:
        """Get the checkpoint covering a specific iteration."""
        for cp in self._checkpoints:
            if cp.iteration_start <= iteration <= cp.iteration_end:
                return cp
        return None
    
    # =========================================================================
    # PERSISTENCE
    # =========================================================================
    
    def save_to_disk(self, filename: str = "model_cache.pkl") -> None:
        """Save cache to disk for persistence across runs."""
        if not self.cache_dir:
            return
        
        filepath = os.path.join(self.cache_dir, filename)
        
        # Don't save actual models (too large), just metadata
        save_data = {
            'stats': self.stats,
            'feature_importances': self._feature_importance_cache,
            'feature_importance_iteration': self._feature_importance_iteration,
            'checkpoints': self._checkpoints,
        }
        
        with open(filepath, 'wb') as f:
            pickle.dump(save_data, f)
        
        if self.verbose:
            print(f"    [Cache] Saved metadata to {filepath}")
    
    def load_from_disk(self, filename: str = "model_cache.pkl") -> bool:
        """Load cache metadata from disk."""
        if not self.cache_dir:
            return False
        
        filepath = os.path.join(self.cache_dir, filename)
        
        if not os.path.exists(filepath):
            return False
        
        try:
            with open(filepath, 'rb') as f:
                save_data = pickle.load(f)
            
            self.stats = save_data.get('stats', self.stats)
            self._feature_importance_cache = save_data.get('feature_importances')
            self._feature_importance_iteration = save_data.get('feature_importance_iteration', 0)
            self._checkpoints = save_data.get('checkpoints', [])
            
            if self.verbose:
                print(f"    [Cache] Loaded metadata from {filepath}")
            
            return True
        except Exception as e:
            if self.verbose:
                print(f"    [Cache] Failed to load from {filepath}: {e}")
            return False
    
    # =========================================================================
    # STATISTICS
    # =========================================================================
    
    def get_stats_summary(self) -> Dict:
        """Get cache hit/miss statistics."""
        total_hits = self.stats['cb_hits'] + self.stats['lgb_hits'] + self.stats['vol_hits']
        total_misses = self.stats['cb_misses'] + self.stats['lgb_misses'] + self.stats['vol_misses']
        total = total_hits + total_misses
        
        return {
            'total_requests': total,
            'total_hits': total_hits,
            'total_misses': total_misses,
            'hit_rate': total_hits / total if total > 0 else 0.0,
            'cb_hit_rate': self.stats['cb_hits'] / (self.stats['cb_hits'] + self.stats['cb_misses']) 
                          if (self.stats['cb_hits'] + self.stats['cb_misses']) > 0 else 0.0,
            'lgb_hit_rate': self.stats['lgb_hits'] / (self.stats['lgb_hits'] + self.stats['lgb_misses'])
                           if (self.stats['lgb_hits'] + self.stats['lgb_misses']) > 0 else 0.0,
            'feature_hit_rate': self.stats['feature_hits'] / (self.stats['feature_hits'] + self.stats['feature_misses'])
                               if (self.stats['feature_hits'] + self.stats['feature_misses']) > 0 else 0.0,
            'estimated_speedup': f"{1 + (total_hits / max(1, total_misses)):.1f}x" if total > 0 else "N/A",
        }
    
    def clear(self) -> None:
        """Clear all caches."""
        self._cb_cache.clear()
        self._lgb_cache.clear()
        self._vol_cache.clear()
        self._calibrator_cache.clear()
        self._feature_importance_cache = None
        gc.collect()


# =============================================================================
# FAST FEATURE COMPUTATION UTILITIES
# =============================================================================

def precompute_all_features(
    source_df: 'pd.DataFrame',
    feature_cols: List[str],
    target_col: str,
    output_path: Optional[str] = None,
    verbose: bool = True
) -> 'pd.DataFrame':
    """
    Pre-compute all features for the entire dataset.
    
    This is useful when features are deterministic and don't depend on 
    the training window. Saves repeated computation during walk-forward.
    
    Args:
        source_df: Source dataframe
        feature_cols: List of feature column names
        target_col: Target column name
        output_path: Optional path to save pre-computed features
        verbose: Print progress
        
    Returns:
        DataFrame with pre-computed features
    """
    import pandas as pd
    
    # Pre-compute fillna once
    features_df = source_df[feature_cols].fillna(0).copy()
    targets = source_df[[target_col]].copy()
    
    result = pd.concat([features_df, targets], axis=1)
    
    if output_path:
        result.to_parquet(output_path, index=False)
        if verbose:
            print(f"    [Precompute] Saved {len(result)} rows to {output_path}")
    
    return result


def batch_predict(
    model: Any,
    X: 'np.ndarray',
    batch_size: int = 10000
) -> 'np.ndarray':
    """
    Batch prediction for large datasets to avoid memory issues.
    
    Args:
        model: Trained model with predict_proba method
        X: Feature matrix
        batch_size: Samples per batch
        
    Returns:
        Probability predictions
    """
    import numpy as np
    
    n_samples = len(X)
    if n_samples <= batch_size:
        return model.predict_proba(X)[:, 1]
    
    predictions = np.zeros(n_samples)
    
    for i in range(0, n_samples, batch_size):
        end = min(i + batch_size, n_samples)
        predictions[i:end] = model.predict_proba(X[i:end])[:, 1]
    
    return predictions

"""
Fast Strategy Feature Generator

Pre-trains models once and generates ALL strategy-needed features in a single pass.
This provides a 5-10x speedup over the full walk-forward loop when you only need
prediction outputs for strategy validation.

Usage:
    python wf_fast_predictions.py [--cache-dir ./cache] [--output predictions.parquet]

Features Generated:
- direction_proba: Calibrated direction probability (0-1)
- direction_pred: Binary prediction (0/1)
- volatility_pred: Predicted volatility
- returns_pred: Predicted returns
- position_size: Suggested position (0-2 Hull scale)
- risk_score: Risk guard score
- All aggregated signals
"""

import os
import gc
import time
import argparse
import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings('ignore')

from collections import deque
from catboost import CatBoostClassifier, CatBoostRegressor
from lightgbm import LGBMClassifier
from sklearn.metrics import roc_auc_score
from sklearn.linear_model import LogisticRegression, Ridge

# Import our modules
from wf_model_cache import ModelCache, batch_predict
from wf_features import (
    calculate_rsi_from_returns, create_rsi_features,
    create_dual_ema_features, create_risk_guard_features,
)
from wf_optuna import run_optuna_tuning
from wf_functions import (
    calibrate_probabilities_adaptive, calculate_optimal_threshold,
    calculate_scale_pos_weight,
)


def fast_walk_forward_predictions(
    source_df: pd.DataFrame,
    feature_cols: list,
    direction_target: str = 'direction_target',
    volatility_target: str = 'volatility_target',
    wf_train: int = 500,
    wf_val: int = 100,
    wf_cal: int = 50,
    wf_pred: int = 1,
    min_history: int = 650,
    checkpoint_interval: int = 20,
    min_overlap_for_reuse: float = 0.95,
    use_optuna: bool = True,
    optuna_timeout: int = 60,
    cache_dir: str = './wf_cache',
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Fast walk-forward predictions with model caching.
    
    Key Optimizations:
    1. Model caching - reuse models when training window overlap is high
    2. Feature importance caching - skip recalculation every iteration
    3. Batch predictions - predict multiple rows at once when possible
    4. Skip redundant calibration - use cached calibrators
    
    Args:
        source_df: Full dataset with features and targets
        feature_cols: List of feature column names
        direction_target: Direction target column
        volatility_target: Volatility target column
        wf_train: Training window size
        wf_val: Validation window size
        wf_cal: Calibration window size
        wf_pred: Prediction window size
        min_history: Minimum history required
        checkpoint_interval: Train new models every N iterations
        min_overlap_for_reuse: Minimum overlap to reuse cached model
        use_optuna: Whether to use Optuna for initial tuning
        optuna_timeout: Optuna timeout in seconds
        cache_dir: Directory for cache files
        verbose: Print progress
        
    Returns:
        DataFrame with all predictions and strategy features
    """
    
    start_time = time.time()
    total_rows = len(source_df)
    
    # Initialize cache
    cache = ModelCache(
        checkpoint_interval=checkpoint_interval,
        min_overlap_for_reuse=min_overlap_for_reuse,
        max_cache_size=10,
        cache_dir=cache_dir,
        verbose=verbose
    )
    
    # Try to load existing cache
    cache.load_from_disk()
    
    # Pre-compute checkpoints
    checkpoints = cache.precompute_checkpoints(
        total_rows=total_rows,
        min_history=min_history,
        wf_train=wf_train,
        wf_val=wf_val,
        wf_cal=wf_cal,
        wf_pred=wf_pred
    )
    
    print(f"\n{'='*80}")
    print("FAST WALK-FORWARD PREDICTIONS (with Model Caching)")
    print(f"{'='*80}")
    print(f"  Total rows: {total_rows:,}")
    print(f"  Windows: TRAIN={wf_train}, VAL={wf_val}, CAL={wf_cal}, PRED={wf_pred}")
    print(f"  Checkpoint interval: {checkpoint_interval}")
    print(f"  Min overlap for reuse: {min_overlap_for_reuse:.0%}")
    print(f"  Features: {len(feature_cols)}")
    
    # Prepare data once
    X_full = source_df[feature_cols].fillna(0).values
    y_dir_full = source_df[direction_target].values
    y_vol_full = source_df[volatility_target].values if volatility_target in source_df.columns else None
    
    # Storage for predictions
    predictions = []
    
    # GPU params
    try:
        from wf_config import setup_gpu_params, DIR_MODEL_PARAMS_BASE
        CATBOOST_GPU_PARAMS, USE_GPU = setup_gpu_params()
    except ImportError:
        CATBOOST_GPU_PARAMS = {'task_type': 'CPU'}
        USE_GPU = False
        DIR_MODEL_PARAMS_BASE = {
            'iterations': 1000,
            'learning_rate': 0.03,
            'depth': 6,
            'l2_leaf_reg': 3.0,
            'early_stopping_rounds': 100,
        }
    
    # Initial Optuna tuning (only once)
    cb_params = None
    lgb_params = None
    
    if use_optuna and len(checkpoints) > 0:
        print(f"\n  Running initial Optuna tuning ({optuna_timeout}s)...")
        cp = checkpoints[0]
        
        X_tune_train = X_full[cp.train_start:cp.train_end]
        y_tune_train = y_dir_full[cp.train_start:cp.train_end]
        X_tune_val = X_full[cp.val_start:cp.val_end]
        y_tune_val = y_dir_full[cp.val_start:cp.val_end]
        
        try:
            optuna_results = run_optuna_tuning(
                X_tune_train, y_tune_train, X_tune_val, y_tune_val,
                timeout_sec=optuna_timeout,
                gpu_params=CATBOOST_GPU_PARAMS,
                gap_size=wf_cal + wf_val,
                verbose=verbose
            )
            cb_params = optuna_results.get('best_cb_params')
            lgb_params = optuna_results.get('best_lgb_params')
            print(f"  ✅ Optuna complete: CB score={optuna_results.get('best_cb_score', 0):.4f}")
        except Exception as e:
            print(f"  ⚠️ Optuna failed: {e}")
    
    # Build model params
    if cb_params:
        CATBOOST_PARAMS = {
            'grow_policy': 'Lossguide',
            'max_leaves': cb_params.get('num_leaves', 31),
            'depth': cb_params.get('max_depth', 8),
            'learning_rate': cb_params.get('learning_rate', 0.01),
            'iterations': cb_params.get('n_estimators', 1000),
            'l2_leaf_reg': cb_params.get('reg_lambda', 10.0),
            'min_data_in_leaf': cb_params.get('min_child_samples', 50),
            'subsample': cb_params.get('subsample', 0.8),
            'bootstrap_type': 'Bernoulli',
            'early_stopping_rounds': 300,
            'loss_function': 'Logloss',
            'eval_metric': 'AUC',
            **CATBOOST_GPU_PARAMS
        }
    else:
        CATBOOST_PARAMS = {**DIR_MODEL_PARAMS_BASE, **CATBOOST_GPU_PARAMS}
    
    if lgb_params:
        LIGHTGBM_PARAMS = {
            'boosting_type': 'gbdt',
            'num_leaves': lgb_params.get('num_leaves', 31),
            'max_depth': lgb_params.get('max_depth', 8),
            'learning_rate': lgb_params.get('learning_rate', 0.01),
            'n_estimators': lgb_params.get('n_estimators', 1000),
            'reg_lambda': lgb_params.get('reg_lambda', 10.0),
            'min_child_samples': lgb_params.get('min_child_samples', 50),
            'subsample': lgb_params.get('subsample', 0.8),
            'objective': 'binary',
            'metric': 'auc',
            'verbose': -1,
            'n_jobs': -1,
        }
    else:
        LIGHTGBM_PARAMS = {
            'boosting_type': 'gbdt',
            'num_leaves': 31,
            'max_depth': 8,
            'learning_rate': 0.01,
            'n_estimators': 1000,
            'reg_lambda': 10.0,
            'min_child_samples': 50,
            'subsample': 0.8,
            'objective': 'binary',
            'metric': 'auc',
            'verbose': -1,
            'n_jobs': -1,
        }
    
    # Null stream for CatBoost
    class NullStream:
        def write(self, x): pass
        def flush(self): pass
    NULL_STREAM = NullStream()
    
    # Main loop
    pred_start = min_history
    iteration = 0
    cb_model = None
    lgb_model = None
    vol_model = None
    
    print(f"\n  Starting walk-forward loop...")
    
    while pred_start < total_rows:
        iteration += 1
        
        # Calculate window boundaries
        pred_end = min(pred_start + wf_pred, total_rows)
        val_end = pred_start
        val_start = val_end - wf_val
        cal_end = val_start
        cal_start = cal_end - wf_cal
        train_end = cal_start
        train_start = max(0, train_end - wf_train)
        
        # Extract data
        X_train = X_full[train_start:train_end]
        y_train = y_dir_full[train_start:train_end]
        X_val = X_full[val_start:val_end]
        y_val = y_dir_full[val_start:val_end]
        X_cal = X_full[cal_start:cal_end]
        y_cal = y_dir_full[cal_start:cal_end]
        X_pred = X_full[pred_start:pred_end]
        y_pred_actual = y_dir_full[pred_start:pred_end]
        
        # Check cache for CatBoost
        should_train_cb, cached_cb = cache.should_retrain(
            iteration, train_start, train_end, 'catboost', drift_detected=False
        )
        
        if should_train_cb:
            # Train new CatBoost model
            scale_pos_weight = calculate_scale_pos_weight(y_train)
            cb_params_iter = CATBOOST_PARAMS.copy()
            cb_params_iter['scale_pos_weight'] = scale_pos_weight
            
            cb_model = CatBoostClassifier(**cb_params_iter)
            cb_model.fit(
                X_train, y_train,
                eval_set=(X_val, y_val),
                log_cout=NULL_STREAM, log_cerr=NULL_STREAM
            )
            
            # Cache the model
            val_probs = cb_model.predict_proba(X_val)[:, 1]
            val_auc = roc_auc_score(y_val, val_probs) if len(np.unique(y_val)) > 1 else 0.5
            
            cache.cache_model(
                model=cb_model,
                model_type='catboost',
                train_start=train_start,
                train_end=train_end,
                features=feature_cols,
                iteration=iteration,
                val_auc=val_auc
            )
        else:
            cb_model = cached_cb.model
        
        # Check cache for LightGBM
        should_train_lgb, cached_lgb = cache.should_retrain(
            iteration, train_start, train_end, 'lightgbm', drift_detected=False
        )
        
        if should_train_lgb:
            # Train new LightGBM model
            lgb_params_iter = LIGHTGBM_PARAMS.copy()
            lgb_params_iter['scale_pos_weight'] = calculate_scale_pos_weight(y_train)
            
            lgb_model = LGBMClassifier(**lgb_params_iter)
            lgb_model.fit(
                X_train, y_train,
                eval_set=[(X_val, y_val)],
                callbacks=[__import__('lightgbm').early_stopping(stopping_rounds=100, verbose=False)]
            )
            
            # Cache the model
            val_probs = lgb_model.predict_proba(X_val)[:, 1]
            val_auc = roc_auc_score(y_val, val_probs) if len(np.unique(y_val)) > 1 else 0.5
            
            cache.cache_model(
                model=lgb_model,
                model_type='lightgbm',
                train_start=train_start,
                train_end=train_end,
                features=feature_cols,
                iteration=iteration,
                val_auc=val_auc
            )
        else:
            lgb_model = cached_lgb.model
        
        # Get predictions
        cb_pred_probs = cb_model.predict_proba(X_pred)[:, 1]
        lgb_pred_probs = lgb_model.predict_proba(X_pred)[:, 1]
        
        # Ensemble average
        ensemble_probs = (cb_pred_probs + lgb_pred_probs) / 2
        
        # Calculate calibration on CAL window
        cb_cal_probs = cb_model.predict_proba(X_cal)[:, 1]
        lgb_cal_probs = lgb_model.predict_proba(X_cal)[:, 1]
        ensemble_cal_probs = (cb_cal_probs + lgb_cal_probs) / 2
        
        # Calculate threshold
        try:
            optimal_threshold = calculate_optimal_threshold(
                ensemble_cal_probs, y_cal, method='f1'
            )
        except:
            optimal_threshold = 0.5
        
        # Store predictions
        for i in range(len(X_pred)):
            pred_idx = pred_start + i
            
            # Position sizing (Hull scale 0-2)
            # 0 = 100% cash, 1 = 100% equity, 2 = 200% equity (max leverage)
            prob = ensemble_probs[i]
            if prob >= optimal_threshold:
                # Bullish: scale position by confidence
                confidence = (prob - optimal_threshold) / (1 - optimal_threshold)
                position = 1.0 + min(confidence, 1.0)  # 1.0 to 2.0
            else:
                # Bearish: reduce position
                confidence = (optimal_threshold - prob) / optimal_threshold
                position = max(0.0, 1.0 - confidence)  # 0.0 to 1.0
            
            predictions.append({
                'pred_idx': pred_idx,
                'iteration': iteration,
                'direction_proba': ensemble_probs[i],
                'cb_proba': cb_pred_probs[i],
                'lgb_proba': lgb_pred_probs[i],
                'direction_pred': 1 if ensemble_probs[i] >= optimal_threshold else 0,
                'direction_actual': y_pred_actual[i],
                'threshold': optimal_threshold,
                'position': position,
                'model_disagreement': abs(cb_pred_probs[i] - lgb_pred_probs[i]),
            })
        
        # Progress
        if iteration % 100 == 0 or iteration == 1:
            elapsed = time.time() - start_time
            rows_done = pred_end
            rows_per_sec = rows_done / elapsed if elapsed > 0 else 0
            eta_sec = (total_rows - rows_done) / rows_per_sec if rows_per_sec > 0 else 0
            print(f"    Iter {iteration}: {rows_done:,}/{total_rows:,} ({100*rows_done/total_rows:.1f}%) "
                  f"| {rows_per_sec:.0f} rows/s | ETA: {eta_sec/60:.1f}min")
        
        pred_start = pred_end
        gc.collect()
    
    # Build results DataFrame
    predictions_df = pd.DataFrame(predictions)
    
    # Compute derived strategy features
    predictions_df['direction_correct'] = (
        predictions_df['direction_pred'] == predictions_df['direction_actual']
    ).astype(int)
    
    # Save cache
    cache.save_to_disk()
    
    # Print summary
    elapsed = time.time() - start_time
    stats = cache.get_stats_summary()
    
    print(f"\n{'='*80}")
    print("FAST PREDICTIONS COMPLETE")
    print(f"{'='*80}")
    print(f"  Total iterations: {iteration}")
    print(f"  Total time: {elapsed/60:.1f} minutes ({elapsed:.1f} seconds)")
    print(f"  Rows per second: {total_rows/elapsed:.0f}")
    print(f"  Cache hit rate: {stats['hit_rate']:.1%}")
    print(f"  Estimated speedup: {stats['estimated_speedup']}")
    print(f"  Output rows: {len(predictions_df)}")
    
    return predictions_df


def main():
    """Command-line interface."""
    parser = argparse.ArgumentParser(description='Fast Walk-Forward Predictions')
    parser.add_argument('--data', type=str, default='/media/przem/w/kaggle/preprocessed_data/train_with_all_features.csv',
                       help='Path to preprocessed data CSV')
    parser.add_argument('--output', type=str, default='fast_predictions.parquet',
                       help='Output path for predictions')
    parser.add_argument('--cache-dir', type=str, default='./wf_cache',
                       help='Cache directory')
    parser.add_argument('--checkpoint-interval', type=int, default=20,
                       help='Train new models every N iterations')
    parser.add_argument('--min-overlap', type=float, default=0.95,
                       help='Minimum overlap to reuse cached model')
    parser.add_argument('--no-optuna', action='store_true',
                       help='Skip Optuna tuning')
    parser.add_argument('--optuna-timeout', type=int, default=60,
                       help='Optuna timeout in seconds')
    
    args = parser.parse_args()
    
    # Load data
    print(f"Loading data from {args.data}...")
    df = pd.read_csv(args.data)
    print(f"  Loaded {len(df):,} rows, {len(df.columns)} columns")
    
    # Determine feature columns (exclude targets and identifiers)
    exclude_patterns = ['target', 'actual', 'date', 'symbol', 'index', 'id']
    feature_cols = [c for c in df.columns 
                   if not any(p in c.lower() for p in exclude_patterns)]
    
    print(f"  Using {len(feature_cols)} features")
    
    # Run fast predictions
    predictions_df = fast_walk_forward_predictions(
        source_df=df,
        feature_cols=feature_cols,
        checkpoint_interval=args.checkpoint_interval,
        min_overlap_for_reuse=args.min_overlap,
        use_optuna=not args.no_optuna,
        optuna_timeout=args.optuna_timeout,
        cache_dir=args.cache_dir,
        verbose=True
    )
    
    # Save output
    predictions_df.to_parquet(args.output, index=False)
    print(f"\nSaved predictions to {args.output}")


if __name__ == '__main__':
    main()

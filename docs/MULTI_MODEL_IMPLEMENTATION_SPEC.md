# Multi-Model Optimization Implementation Specification

> **Status:** Design Complete | **Target:** l2_backtest_sync.py  
> **Created:** 2026-01-19 | **Validation:** All 4 tasks passed

---

## 1. Executive Summary

### Goal
Store ALL data needed for post-backtest optimization analysis. Every prediction should contain enough information to:
1. Reconstruct what the model saw at prediction time
2. Analyze per-model performance independently
3. Optimize window sizes, feature selection, and weights post-hoc
4. Debug any anomalies without re-running

### Current State
- **Fields stored:** 27-33 per prediction (depends on task type)
- **Missing:** ~30 fields for comprehensive optimization

### Design Principle
**Extend existing modules, don't create new ones:**
- `helpers/icir_config.py` → Template for PerModelConfig
- `helpers/icir_selection.py` → Extend for per-model feature selection
- `validation/statistical_metrics.py` → Add rolling metrics

---

## 2. Complete Metrics Schema

### 2.1 Current Fields (Keep All)

```python
# Core prediction fields (in data.predictions.append())
{
    "step": int,                    # Walk-forward step number
    "pred_position": int,           # Position within batch
    "pred_idx": int,                # Index in combined_df (INTEGER)
    "y_pred": int | float,          # Ensemble prediction
    "y_true": int | float,          # Actual target value
    "pred_error": float,            # y_pred - y_true (regression)
    "abs_pred_error": float,        # |y_pred - y_true|
    "covered": bool,                # Conformal coverage
    "interval_width": float,        # Conformal interval width (regression)
    "set_size": int,                # Conformal set size (classification)
    "window_start": int,            # Training window start idx
    "window_end": int,              # Training window end idx
}

# Model predictions (in components dict)
{
    "cb_pred": int | float,         # CatBoost prediction
    "lgb_pred": int | float,        # LightGBM prediction
    "lstm_pred": int | float,       # LSTM prediction
    "linear_pred": int | float,     # Linear model prediction
}

# Probabilities (classification only)
{
    "cb_prob": float,               # CatBoost probability
    "lgb_prob": float,              # LightGBM probability
    "lstm_prob": float,             # LSTM probability
    "linear_prob": float,           # Linear probability
    "y_prob": float,                # Ensemble probability
    "ensemble_confidence": float,   # Max prob across classes
    "model_agreement": float,       # Fraction of models agreeing
}

# Hyperparameters (current - from Optuna)
{
    "cb_iterations": int,
    "cb_depth": int,
    "cb_lr": float,
    "cb_l2": float,
    "lgb_n_estimators": int,
    "lgb_max_depth": int,
    "lgb_lr": float,
    "lgb_lambda": float,
}

# Data sizes
{
    "n_train": int,
    "n_val": int,
    "n_cal": int,
}

# Conformal (regression)
{
    "conformal_width": float,
    "interval_lower": float,
    "interval_upper": float,
    "cal_residual_mean": float,
    "cal_residual_std": float,
}

# Raw predictions (regression)
{
    "cb_pred_raw": float,
    "lgb_pred_raw": float,
    "lstm_pred_raw": float,
    "linear_pred_raw": float,
    "y_pred_raw": float,
    "pred_std": float,
    "pred_range": float,
}
```

### 2.2 NEW Fields to Add (~30 total)

#### Category A: Timing (4 fields)
```python
{
    "cb_train_time_ms": int,         # CatBoost training time in milliseconds
    "lgb_train_time_ms": int,        # LightGBM training time
    "lstm_train_time_ms": int,       # LSTM training time
    "linear_train_time_ms": int,     # Linear model training time
}
```

**Implementation:**
```python
import time

t0 = time.perf_counter()
cb_model.fit(X_train, y_train, ...)
cb_train_time_ms = int((time.perf_counter() - t0) * 1000)
```

#### Category B: Feature Information (7 fields)
```python
{
    "n_features_total": int,         # Total features before selection
    "n_features_used": int,          # Features after selection (shared)
    "cb_n_features": int,            # Features used by CatBoost (if per-model)
    "lgb_n_features": int,           # Features used by LightGBM
    "lstm_n_features": int,          # Features used by LSTM
    "linear_n_features": int,        # Features used by Linear
    "feature_selection_method": str, # "none"|"icir"|"importance"|"variance"
}
```

**Note:** For Phase 1, all models use same features. Per-model selection comes in Phase 3.

#### Category C: Feature Importance (4 fields)
```python
{
    # Store top 5 features as JSON string (compact)
    "cb_top5_features": str,         # '{"f1":0.23,"f2":0.18,...}'
    "lgb_top5_features": str,        # Same format
    "cb_importance_sum": float,      # Sum of top 10 importances (concentration)
    "lgb_importance_sum": float,     # Same
}
```

**Implementation:**
```python
import json

importances = cb_model.get_feature_importance()
indices = np.argsort(importances)[::-1][:5]
top5 = {feature_cols[i]: float(importances[i]) for i in indices}
cb_top5_features = json.dumps(top5)
cb_importance_sum = float(importances[indices[:10]].sum())
```

#### Category D: Per-Model Window Sizes (4 fields)
```python
{
    "cb_window_size": int,           # Training window for CatBoost
    "lgb_window_size": int,          # Training window for LightGBM
    "lstm_window_size": int,         # Training window for LSTM
    "linear_window_size": int,       # Training window for Linear
}
```

**Note:** For Phase 1, all same as `window_end - window_start`. Per-model windows come in Phase 2.

#### Category E: Timestamp (1 field)
```python
{
    "pred_datetime": str,            # ISO format: "2024-03-15T08:00:00"
}
```

**Implementation:**
```python
# At config load time (once):
index_8h = pd.read_parquet("data/precomputed/index_8h.parquet")
pred_idx_to_datetime = dict(zip(index_8h["pred_idx"], index_8h["timestamp"]))

# At prediction time:
pred_datetime = pred_idx_to_datetime.get(pred_idx, "").isoformat()
```

#### Category F: Rolling Performance Metrics (6 fields)
```python
{
    # EMA of recent performance (updated each step)
    "rolling_acc_ema20": float,      # EMA(accuracy, span=20)
    "rolling_acc_ema50": float,      # EMA(accuracy, span=50)
    "rolling_ic_ema20": float,       # EMA(IC, span=20) - regression
    "rolling_ic_ema50": float,       # EMA(IC, span=50)
    "rolling_cb_acc_ema20": float,   # Per-model EMA
    "rolling_lgb_acc_ema20": float,  # Per-model EMA
}
```

**Implementation:**
```python
# Track in BacktestData class
class BacktestData:
    def __init__(self):
        self.rolling_acc_ema20 = None  # Start with None
        self.rolling_acc_ema50 = None
        
    def update_rolling_metrics(self, is_correct: bool):
        alpha20 = 2 / (20 + 1)
        alpha50 = 2 / (50 + 1)
        
        if self.rolling_acc_ema20 is None:
            self.rolling_acc_ema20 = float(is_correct)
            self.rolling_acc_ema50 = float(is_correct)
        else:
            self.rolling_acc_ema20 = alpha20 * is_correct + (1 - alpha20) * self.rolling_acc_ema20
            self.rolling_acc_ema50 = alpha50 * is_correct + (1 - alpha50) * self.rolling_acc_ema50
```

#### Category G: Ensemble Weights (4 fields)
```python
{
    "cb_weight_used": float,         # Actual weight used (may be adaptive)
    "lgb_weight_used": float,
    "lstm_weight_used": float,
    "linear_weight_used": float,
}
```

**Note:** Currently weights come from config. With adaptive weights, they change per step.

#### Category H: Regime Context (2 fields)
```python
{
    "vol_regime_at_pred": int,       # 0/1/2 volatility regime at prediction
    "trend_regime_at_pred": int,     # 0/1 trend regime at prediction
}
```

**Implementation:**
```python
# Extract from combined_df at prediction index
vol_regime_at_pred = int(combined_df.loc[pred_idx, "y_vol_regime"]) if "y_vol_regime" in combined_df else -1
trend_regime_at_pred = int(combined_df.loc[pred_idx, "y_trend_regime"]) if "y_trend_regime" in combined_df else -1
```

#### Category I: LSTM-Specific (2 fields)
```python
{
    "lstm_val_loss": float,          # Best validation loss achieved
    "lstm_epochs_actual": int,       # Actual epochs run (may early stop)
}
```

---

## 3. PerModelConfig Design

### 3.1 Dataclass Structure

```python
from dataclasses import dataclass, field
from typing import Literal

@dataclass
class PerModelConfig:
    """Per-model configuration for independent optimization.
    
    Research basis:
    - Tree models (CB/LGB): Robust with 300-500 samples, benefit from recent data
    - LSTM: Needs 500+ for sequence learning, longer windows help
    - Linear: Most data-hungry, 800+ recommended for stability
    
    References:
    - de Prado "Advances in Financial ML" Ch. 7 (sample size)
    - arXiv 2305.17094 (tree depth/regularization)
    """
    
    # Window configuration
    train_window: int = 500              # Training window size
    train_ratio: float = 0.55            # Train split within window
    val_ratio: float = 0.15              # Validation split
    cal_ratio: float = 0.30              # Calibration split
    
    # Embargo (target-horizon aware)
    embargo_bars: int = 24               # Gap between splits
    
    # Feature selection
    feature_selection: Literal["none", "icir", "importance", "variance"] = "none"
    feature_selection_ratio: float = 1.0  # Keep top X% of features
    min_features: int = 20               # Never go below this
    
    # Model-specific hyperparameters (optional overrides)
    hyperparams: dict = field(default_factory=dict)


# Default configurations per model type
DEFAULT_CB_CONFIG = PerModelConfig(
    train_window=400,
    embargo_bars=24,
    feature_selection="importance",
    feature_selection_ratio=0.6,  # Keep top 60%
)

DEFAULT_LGB_CONFIG = PerModelConfig(
    train_window=400,
    embargo_bars=24,
    feature_selection="importance",
    feature_selection_ratio=0.6,
)

DEFAULT_LSTM_CONFIG = PerModelConfig(
    train_window=600,             # LSTM benefits from more data
    embargo_bars=24,
    feature_selection="variance",  # Remove low-variance (LSTM sensitive)
    feature_selection_ratio=0.8,
)

DEFAULT_LINEAR_CONFIG = PerModelConfig(
    train_window=800,             # Linear needs most data
    embargo_bars=24,
    feature_selection="icir",     # ICIR best for linear stability
    feature_selection_ratio=0.5,
)
```

### 3.2 Integration with SyncBacktestConfig

```python
@dataclass
class SyncBacktestConfig:
    """Configuration for synchronized L2 backtest."""
    
    # ... existing fields ...
    
    # NEW: Per-model configurations (optional)
    # If None, uses shared settings (backward compatible)
    cb_config: PerModelConfig | None = None
    lgb_config: PerModelConfig | None = None
    lstm_config: PerModelConfig | None = None
    linear_config: PerModelConfig | None = None
    
    def get_model_config(self, model: str) -> PerModelConfig:
        """Get config for specific model, with fallback to shared."""
        configs = {
            "cb": self.cb_config,
            "lgb": self.lgb_config,
            "lstm": self.lstm_config,
            "linear": self.linear_config,
        }
        
        if configs.get(model) is not None:
            return configs[model]
        
        # Fallback: create from shared settings
        return PerModelConfig(
            train_window=self.train_window,
            train_ratio=self.train_ratio,
            val_ratio=self.val_ratio,
            cal_ratio=self.cal_ratio,
            embargo_bars=self.embargo_bars,
        )
```

---

## 4. Feature Selection API

### 4.1 Functions to Add to `helpers/icir_selection.py`

```python
def select_features_by_importance(
    model,
    feature_cols: list[str],
    ratio: float = 0.6,
    min_features: int = 20,
) -> list[str]:
    """Select top features by tree model importance.
    
    Args:
        model: Trained CatBoost or LightGBM model
        feature_cols: All feature column names
        ratio: Keep top X% of features
        min_features: Minimum features to keep
        
    Returns:
        List of selected feature names
    """
    importances = model.get_feature_importance()
    n_keep = max(int(len(feature_cols) * ratio), min_features)
    n_keep = min(n_keep, len(feature_cols))
    
    indices = np.argsort(importances)[::-1][:n_keep]
    return [feature_cols[i] for i in indices]


def select_features_by_variance(
    X: pd.DataFrame,
    ratio: float = 0.8,
    min_features: int = 20,
) -> list[str]:
    """Remove low-variance features.
    
    Args:
        X: Feature DataFrame
        ratio: Keep top X% by variance
        min_features: Minimum features to keep
        
    Returns:
        List of selected feature names
    """
    variances = X.var()
    n_keep = max(int(len(X.columns) * ratio), min_features)
    n_keep = min(n_keep, len(X.columns))
    
    top_cols = variances.nlargest(n_keep).index.tolist()
    return top_cols


def apply_feature_selection(
    X: pd.DataFrame,
    method: str,
    model=None,
    target: np.ndarray | None = None,
    config: PerModelConfig | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """Apply feature selection based on method.
    
    Args:
        X: Feature DataFrame
        method: "none", "icir", "importance", "variance"
        model: Trained model (for importance method)
        target: Target values (for icir method)
        config: PerModelConfig with ratio and min_features
        
    Returns:
        (filtered X, selected column names)
    """
    if config is None:
        ratio = 1.0
        min_features = 20
    else:
        ratio = config.feature_selection_ratio
        min_features = config.min_features
    
    if method == "none":
        return X, X.columns.tolist()
    
    elif method == "importance":
        if model is None:
            return X, X.columns.tolist()
        selected = select_features_by_importance(
            model, X.columns.tolist(), ratio, min_features
        )
        return X[selected], selected
    
    elif method == "variance":
        selected = select_features_by_variance(X, ratio, min_features)
        return X[selected], selected
    
    elif method == "icir":
        if target is None:
            return X, X.columns.tolist()
        # Use existing select_features_by_icir
        from .icir_config import ICIRConfig
        icir_config = ICIRConfig(icir_threshold=0.2)  # Lenient for selection
        selected = select_features_by_icir(X, target, icir_config)
        if len(selected) < min_features:
            # Fall back to keeping more
            selected = X.columns.tolist()[:min_features]
        return X[selected], selected
    
    return X, X.columns.tolist()
```

---

## 5. Rolling Metrics Implementation

### 5.1 Add to `validation/statistical_metrics.py`

```python
@dataclass
class RollingMetricsState:
    """State for tracking rolling performance metrics.
    
    Uses Exponential Moving Average (EMA) for smooth tracking.
    EMA formula: EMA_t = α * x_t + (1 - α) * EMA_{t-1}
    where α = 2 / (span + 1)
    """
    
    # Ensemble metrics
    acc_ema20: float | None = None
    acc_ema50: float | None = None
    ic_ema20: float | None = None
    ic_ema50: float | None = None
    
    # Per-model metrics
    cb_acc_ema20: float | None = None
    lgb_acc_ema20: float | None = None
    lstm_acc_ema20: float | None = None
    linear_acc_ema20: float | None = None
    
    def update_classification(
        self,
        ens_correct: bool,
        cb_correct: bool,
        lgb_correct: bool,
        lstm_correct: bool | None,
        linear_correct: bool,
    ) -> dict:
        """Update rolling metrics for classification task.
        
        Returns dict of current rolling values.
        """
        alpha20 = 2 / (20 + 1)
        alpha50 = 2 / (50 + 1)
        
        def update_ema(current: float | None, value: float, alpha: float) -> float:
            if current is None:
                return value
            return alpha * value + (1 - alpha) * current
        
        self.acc_ema20 = update_ema(self.acc_ema20, float(ens_correct), alpha20)
        self.acc_ema50 = update_ema(self.acc_ema50, float(ens_correct), alpha50)
        self.cb_acc_ema20 = update_ema(self.cb_acc_ema20, float(cb_correct), alpha20)
        self.lgb_acc_ema20 = update_ema(self.lgb_acc_ema20, float(lgb_correct), alpha20)
        self.linear_acc_ema20 = update_ema(self.linear_acc_ema20, float(linear_correct), alpha20)
        
        if lstm_correct is not None:
            self.lstm_acc_ema20 = update_ema(self.lstm_acc_ema20, float(lstm_correct), alpha20)
        
        return {
            "rolling_acc_ema20": self.acc_ema20,
            "rolling_acc_ema50": self.acc_ema50,
            "rolling_cb_acc_ema20": self.cb_acc_ema20,
            "rolling_lgb_acc_ema20": self.lgb_acc_ema20,
        }
    
    def update_regression(
        self,
        y_true: float,
        y_pred: float,
        cb_pred: float,
        lgb_pred: float,
    ) -> dict:
        """Update rolling metrics for regression task.
        
        Uses IC (correlation) instead of accuracy.
        """
        # For rolling IC, we track residual correlation
        # Simplified: track rolling MAE ratio as proxy
        alpha20 = 2 / (20 + 1)
        alpha50 = 2 / (50 + 1)
        
        error = abs(y_true - y_pred)
        # Normalize by target magnitude (avoid div by zero)
        normalized_acc = 1.0 / (1.0 + error / max(abs(y_true), 0.001))
        
        def update_ema(current: float | None, value: float, alpha: float) -> float:
            if current is None:
                return value
            return alpha * value + (1 - alpha) * current
        
        self.ic_ema20 = update_ema(self.ic_ema20, normalized_acc, alpha20)
        self.ic_ema50 = update_ema(self.ic_ema50, normalized_acc, alpha50)
        
        return {
            "rolling_ic_ema20": self.ic_ema20,
            "rolling_ic_ema50": self.ic_ema50,
        }
```

---

## 6. Implementation Order (Code Changes)

### Phase 1: Core Storage Extension (Tasks 8-9)

**File:** `l2_backtest_sync.py`

1. Add `PerModelConfig` dataclass after `SyncBacktestConfig` (~L480)
2. Add default configs (`DEFAULT_CB_CONFIG`, etc.)
3. Add `get_model_config()` method to `SyncBacktestConfig`

### Phase 2: Timing & Feature Tracking (Tasks 10-13)

**File:** `l2_backtest_sync.py`

1. Wrap model training in timing blocks
2. Add `n_features_*` tracking
3. Add `cb_top5_features` extraction after training

### Phase 3: Timestamp Addition (Task 14-15)

**File:** `l2_backtest_sync.py`

1. Load `index_8h.parquet` in `_preload_all_configs()`
2. Create `pred_idx_to_datetime` mapping
3. Add `pred_datetime` to prediction dict

### Phase 4: Rolling Metrics (Task 16)

**File:** `validation/statistical_metrics.py` + `l2_backtest_sync.py`

1. Add `RollingMetricsState` dataclass to statistical_metrics.py
2. Initialize in `BacktestData.__init__()`
3. Update after each prediction
4. Add rolling values to components dict

### Phase 5: Weights & Regime (Tasks 17-18)

**File:** `l2_backtest_sync.py`

1. Add `*_weight_used` fields (copy from config or adaptive)
2. Add `vol_regime_at_pred`, `trend_regime_at_pred`

### Phase 6: Testing (Tasks 19-22)

**File:** `tests/test_l2_backtest_extended.py` (new)

1. Test pred_idx alignment across different windows
2. Test no leakage in feature selection
3. Test all new fields present in output
4. Compare baseline vs extended metrics

---

## 7. Integration Points Summary

| Line Range | Function/Class | Change Required |
|------------|----------------|-----------------|
| L402-482 | `SyncBacktestConfig` | Add `PerModelConfig` fields |
| L650-680 | `ConfigData` | No change |
| L720-780 | `_preload_single_config` | Add timestamp mapping |
| L928-1000 | `_train_predict_classification` (Binary) | Add timing, features |
| L1079-1150 | `_train_predict_classification` (Multiclass) | Add timing, features |
| L1222-1400 | `_train_predict_regression` | Add timing, features |
| L1470-1520 | Binary components dict | Extend with new fields |
| L1620-1680 | Multiclass components dict | Extend with new fields |
| L1870-1930 | Regression components dict | Extend with new fields |
| L2240-2280 | `data.predictions.append()` | Add core new fields |

---

## 8. Backward Compatibility

### Guaranteed
- All existing fields preserved
- `PerModelConfig = None` uses shared settings (current behavior)
- Parquet output compatible (new columns added, not modified)

### Migration Path
1. Run with `PerModelConfig = None` → same as before
2. Add individual model configs one at a time
3. Compare results before/after

---

## 9. Validation Checklist (Pre-Implementation)

- [x] Audit current storage → 27-33 fields documented
- [x] Document config flow → All models share window/splits
- [x] Check timestamp availability → Need index_8h mapping
- [x] Identify reusable modules → icir_selection, icir_config, statistical_metrics
- [x] Design metrics schema → 30 new fields in 9 categories
- [x] Design PerModelConfig → Dataclass with defaults
- [x] Design feature selection API → 3 methods

---

## 10. Files to Modify (VALIDATED 2026-01-19)

### Architecture Validation Summary

✅ **NO CONFLICTS FOUND** - All proposed classes/functions are new
✅ **Module structure matches main_wf.py patterns**
✅ **Extends existing modules, no redundant files**

### File Placement (Consistent with Pipeline Structure)

| File | Changes | Rationale |
|------|---------|-----------|
| `scripts/target_models/validation/l2_backtest_sync.py` | Add `PerModelConfig`, extend `SyncBacktestConfig`, add timing/metrics | **Main backtest file** - keeps all backtest logic together |
| `scripts/target_models/helpers/icir_selection.py` | Add `select_features_by_importance()`, `select_features_by_variance()`, `apply_feature_selection()` | **Existing feature selection module** (438 lines) - already has ICIR functions |
| `scripts/target_models/validation/statistical_metrics.py` | Add `RollingMetricsState` class | **Existing metrics module** (1542 lines) - already has DSR, PBO, regime metrics |
| `scripts/workflow/config.py` | Extend `L2BacktestDefaults` with per-model options | **Workflow config hub** - main_wf.py imports from here |

### What We Are NOT Creating (Avoided Redundancy)

| ❌ Rejected | ✅ Instead |
|-------------|-----------|
| New `permodel_config.py` module | Add `PerModelConfig` to `l2_backtest_sync.py` (next to `SyncBacktestConfig`) |
| New `feature_selection.py` module | Extend `helpers/icir_selection.py` (already has similar functions) |
| New `rolling_metrics.py` module | Add to `validation/statistical_metrics.py` (already has metrics) |
| New config file | Extend existing `L2BacktestDefaults` in `scripts/workflow/config.py` |

### Integration with main_wf.py (Step 10)

```python
# Current main_wf.py Step 10 pattern (keep unchanged):
from scripts.target_models.validation.l2_backtest_sync import (
    SyncBacktestConfig,
    run_sync_backtest,
)
from scripts.workflow.config import L2BacktestDefaults

defaults = L2BacktestDefaults()
sync_config = SyncBacktestConfig(**defaults.to_sync_config_kwargs())
results = run_sync_backtest(configs=backtest_configs, config=sync_config)

# After implementation - same pattern, new options available:
defaults = L2BacktestDefaults(
    use_per_model_config=True,  # NEW: Enable per-model windows
    store_extended_metrics=True,  # NEW: Store all 34 new fields
)
```

**Total estimated LoC:** ~300-400 additions, ~50 modifications

---

## Appendix A: Field Reference Card

```
TIMING (4):        cb_train_time_ms, lgb_train_time_ms, lstm_train_time_ms, linear_train_time_ms
FEATURES (7):      n_features_total, n_features_used, cb_n_features, lgb_n_features, lstm_n_features, linear_n_features, feature_selection_method
IMPORTANCE (4):    cb_top5_features, lgb_top5_features, cb_importance_sum, lgb_importance_sum
WINDOWS (4):       cb_window_size, lgb_window_size, lstm_window_size, linear_window_size
TIMESTAMP (1):     pred_datetime
ROLLING (6):       rolling_acc_ema20, rolling_acc_ema50, rolling_ic_ema20, rolling_ic_ema50, rolling_cb_acc_ema20, rolling_lgb_acc_ema20
WEIGHTS (4):       cb_weight_used, lgb_weight_used, lstm_weight_used, linear_weight_used
REGIME (2):        vol_regime_at_pred, trend_regime_at_pred
LSTM (2):          lstm_val_loss, lstm_epochs_actual

TOTAL NEW: 34 fields
```

---

*Document generated for implementation guidance. Follow section 6 for implementation order.*

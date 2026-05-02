# Architecture Scalability Analysis

## Purpose

Before implementing dynamic window/split optimization, verify that the current architecture supports **completely independent workflows per model** without conflicts.

---

## Current Architecture Overview

```
backtest/
├── core/
│   ├── base.py              # ModelConfig ABC, ModelResult dataclass
│   └── features.py          # extract_per_model_splits(), apply_feature_selection()
├── domain/
│   └── config.py            # SyncBacktestConfig, PerModelConfig
├── models/
│   ├── catboost_model.py    # CatBoostModelConfig, tune_*, train_and_predict_*
│   ├── lightgbm_model.py    # LightGBMModelConfig, tune_*, train_and_predict_*
│   ├── lstm_model.py        # LSTMModelConfig, tune_*, train_and_predict_*
│   └── linear_model.py      # LinearModelConfig, tune_*, train_and_predict_*
└── services/
    └── training.py          # Orchestration: _get_model_configs(), train_predict_*_permodel()
```

---

## Analysis: Can Models Have Independent Workflows?

### ✅ YES: Each Model Module Is Self-Contained

Each model module (`catboost_model.py`, `lightgbm_model.py`, etc.) contains:
1. **Own config class** extending `ModelConfig`
2. **Own tuning function** (`tune_*_classifier`, `tune_*_regressor`)
3. **Own train+predict function** (`train_and_predict_classifier/regressor`)
4. **Returns standardized `ModelResult`**

**Evidence:**
```python
# catboost_model.py
@dataclass
class CatBoostModelConfig(ModelConfig):
    # CatBoost-specific hyperparameters
    n_estimators: int = 100
    max_depth: int = 6
    ...

def train_and_predict_classifier(
    X_train, y_train, X_val, y_val, X_cal, y_cal, X_pred,
    config: CatBoostModelConfig,
    ...
) -> ModelResult:
    # Completely self-contained
```

**Conclusion:** Models are already independent. We can add completely different logic per model.

---

### ⚠️ BOTTLENECK: Orchestration Layer (`training.py`)

**Current problem:** `_get_model_configs()` creates configs in ONE place with FIXED values from `SyncBacktestConfig`.

```python
def _get_model_configs(config: SyncBacktestConfig, horizon: int):
    cb_cfg = CatBoostModelConfig(
        train_window=config.cb_config.train_window if config.cb_config else 400,  # FIXED!
        train_ratio=config.cb_config.train_ratio if config.cb_config else 0.60,   # FIXED!
        ...
    )
```

**Issue:** No access to data (X_full, y_full) at this point → Can't analyze data to decide optimal config.

---

### ⚠️ BOTTLENECK: Split Extraction (`features.py`)

**Current:** `extract_per_model_splits()` uses config values directly without opportunity for adaptation.

```python
def extract_per_model_splits(X_full, y_full, model_config, full_window_size):
    model_window = model_config.train_window  # From config, not adaptive
    ...
```

---

## What Needs To Change For Scalability

### Option A: Add Pre-Training Adaptation Hook

Each model module gets an **`optimize_config()`** function called BEFORE training:

```python
# In catboost_model.py
def optimize_catboost_config(
    X_full: pd.DataFrame,
    y_full: pd.Series,
    base_config: CatBoostModelConfig,
    task_type: str,
    previous_results: dict | None = None,
) -> CatBoostModelConfig:
    """Analyze data and return optimized config for this step."""
    # CatBoost-specific optimization logic
    optimal_window = _analyze_optimal_window_cb(X_full, y_full)
    optimal_splits = _analyze_optimal_splits_cb(X_full, y_full, task_type)
    
    return dataclasses.replace(
        base_config,
        train_window=optimal_window,
        train_ratio=optimal_splits['train'],
        val_ratio=optimal_splits['val'],
        cal_ratio=optimal_splits['cal'],
    )
```

**Orchestration change in `training.py`:**
```python
def train_predict_classification_permodel(...):
    # Get base configs
    cb_cfg, lgb_cfg, lstm_cfg, linear_cfg = _get_model_configs(config, horizon)
    
    # NEW: Per-model optimization hooks
    cb_cfg = optimize_catboost_config(X_full, y_full, cb_cfg, task_type, previous_best)
    lgb_cfg = optimize_lightgbm_config(X_full, y_full, lgb_cfg, task_type, previous_best)
    lstm_cfg = optimize_lstm_config(X_full, y_full, lstm_cfg, task_type, previous_best)
    linear_cfg = optimize_linear_config(X_full, y_full, linear_cfg, task_type, previous_best)
    
    # Then extract splits with optimized configs
    cb_X_train, cb_y_train, ... = extract_per_model_splits(X_full, y_full, cb_cfg, ...)
```

**Pros:**
- Clean separation of concerns
- Each model can have COMPLETELY different optimization logic
- No conflicts between models
- Easy to test in isolation

**Cons:**
- Adds one function call per model per step

---

### Option B: Move Optimization INSIDE Model Modules

Each `train_and_predict_*` function handles its own split extraction:

```python
# In catboost_model.py
def train_and_predict_classifier(
    X_full: pd.DataFrame,  # Changed from X_train!
    y_full: pd.Series,
    X_pred: pd.DataFrame,
    config: CatBoostModelConfig,
    ...
) -> ModelResult:
    # Step 1: Optimize config based on X_full, y_full
    optimized_config = _optimize_config_internal(X_full, y_full, config)
    
    # Step 2: Extract splits with optimized config
    X_train, y_train, X_val, y_val, X_cal, y_cal = _extract_splits(
        X_full, y_full, optimized_config
    )
    
    # Step 3: Feature selection
    # Step 4: Training
    # Step 5: Prediction
```

**Pros:**
- Each module is 100% self-contained (including data handling)
- Maximum flexibility per model

**Cons:**
- Bigger change to function signatures
- Duplicates split extraction logic across modules

---

## Recommendation: Option A

**Option A** (pre-training hooks) is better because:

1. **Minimal signature changes** - Current function signatures mostly preserved
2. **Shared utilities remain shared** - `extract_per_model_splits()` stays in `features.py`
3. **Clear separation** - Optimization logic clearly separate from training logic
4. **Testable** - Can unit test `optimize_*_config()` functions independently
5. **Incremental** - Can add one model at a time without breaking others

---

## Implementation Checklist

### Phase 0: Verify Architecture (THIS DOCUMENT)
- [x] Analyze current architecture
- [x] Identify bottlenecks
- [x] Design solution approach

### Phase 1: Add Optimization Hooks Interface
- [ ] Create `core/adaptive.py` with base protocol/interface
- [ ] Add `optimize_*_config()` stub to each model module (returns config unchanged)
- [ ] Modify `training.py` to call optimization hooks
- [ ] Run backtest to verify no regression

### Phase 2-5: Implement Per-Model Optimization (separate docs)
- [ ] CatBoost: Early stopping signals + nested CV
- [ ] LightGBM: Similar to CB with leaf-wise considerations  
- [ ] LSTM: PACF for lookback + window optimization
- [ ] Linear: Joint window+alpha optimization

---

## Questions Resolved

| Question | Answer |
|----------|--------|
| Can models have independent workflows? | **YES** - self-contained modules |
| Where's the bottleneck? | `_get_model_configs()` - fixed configs, no data access |
| Best extension point? | Add `optimize_*_config()` hooks called before split extraction |
| Will this cause conflicts? | **NO** - each model's hook is independent |
| Is architecture scalable? | **YES with Option A** - clean, testable, incremental |

---

## Summary

**Current architecture is already 90% scalable.** We only need to:

1. Add `optimize_*_config()` function to each model module
2. Call these hooks in `training.py` before `extract_per_model_splits()`
3. Pass optimized config (instead of fixed config) to split extraction

This design allows **completely different optimization logic per model** with **zero conflicts**.

---

*Created: 2025-01-19*
*Status: Analysis complete - architecture supports scalable per-model optimization*

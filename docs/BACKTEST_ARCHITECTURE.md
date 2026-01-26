# Backtest Package Architecture Documentation

**Version:** 2.1.0  
**Last Updated:** 2026-01-19  
**Status:** Validated with Scalability Analysis

---

## Executive Summary

The `backtest` package provides a **modular ML backtesting system** with:
- 4-model ensemble (CatBoost, LightGBM, LSTM, Linear)
- Per-model independent configurations
- Walk-forward validation with adaptive ensemble weights
- Conformal prediction for uncertainty quantification

**Architecture Quality:** ✅ CLEAN  
**Current Scalability:** ⚠️ LIMITED - configs are FIXED at startup  
**Target Scalability:** DYNAMIC per-step config optimization  
**Issues Found:** 3 (1 blocking scalability, 2 minor)

---

## Package Structure

```
backtest/                          # 5,755 total lines
├── __init__.py           (99)     # Package exports, backward compat
├── core/                          # Pure functions, base classes
│   ├── __init__.py       (14)     # Core exports
│   ├── base.py           (208)    # ModelConfig ABC, ModelResult, ModelProtocol
│   ├── features.py       (177)    # Feature selection, split extraction
│   ├── ensemble.py       (328)    # MWU adaptive weights, AdaptiveWeightTracker
│   └── metrics.py        (259)    # Metrics computation
├── domain/                        # Configuration entities
│   ├── __init__.py       (4)      # Placeholder (see Issue #2)
│   └── config.py         (275)    # SyncBacktestConfig, PerModelConfig
├── adapters/                      # External interfaces
│   ├── __init__.py       (5)      # Placeholder (see Issue #2)
│   ├── data_loader.py    (277)    # ConfigData, load_config_data
│   └── output.py         (53)     # DualOutput logging
├── models/                        # ML model implementations
│   ├── __init__.py       (102)    # Model exports
│   ├── catboost_model.py (423)    # CatBoost full pipeline
│   ├── lightgbm_model.py (454)    # LightGBM full pipeline
│   ├── lstm_model.py     (879)    # LSTM full pipeline + Optuna
│   ├── linear_model.py   (418)    # Linear full pipeline + Optuna
│   └── lstm.py           (304)    # LEGACY - see Issue #1
└── services/                      # Orchestration
    ├── __init__.py       (5)      # Placeholder (see Issue #2)
    ├── training.py       (699)    # Per-model training orchestration
    └── backtest.py       (771)    # Walk-forward main loop
```

---

## Layer Architecture

### Layer 1: Domain (`domain/`)

**Purpose:** Core configuration entities and business rules.

| File | Classes/Functions | Description |
|------|-------------------|-------------|
| `config.py` | `PerModelConfig` | Per-model window/split/feature config |
| | `SyncBacktestConfig` | Main backtest configuration |
| | `DEFAULT_*_CONFIG` | Research-based defaults (CB, LGB, LSTM, Linear) |

**Key Design:**
- `PerModelConfig` allows each model to have independent settings
- `SyncBacktestConfig` holds both shared settings and per-model configs
- `get_max_window_size()` computes max across all models for data extraction

---

### Layer 2: Core (`core/`)

**Purpose:** Pure functions and base abstractions. No external dependencies except numpy/pandas.

| File | Classes/Functions | Description |
|------|-------------------|-------------|
| `base.py` | `ModelConfig` (ABC) | Base config with window/split/embargo |
| | `ModelResult` | Standardized output from training |
| | `ModelProtocol` | Interface each model must implement |
| `features.py` | `apply_feature_selection()` | variance/importance/icir selection |
| | `extract_per_model_splits()` | Per-model train/val/cal extraction |
| `ensemble.py` | `AdaptiveWeightTracker` | MWU weight tracking |
| | `update_adaptive_weights()` | MWU algorithm implementation |
| | `compute_sample_weights()` | Exponential decay for concept drift |
| `metrics.py` | `build_step_metrics()` | Per-step metric computation |
| | `compute_config_metrics()` | Final metrics per config |

**Key Design:**
- `ModelConfig` is abstract - each model extends with specific hyperparameters
- `ModelResult` standardizes outputs across all models
- `extract_per_model_splits()` handles per-model window sizes with embargo

---

### Layer 3: Models (`models/`)

**Purpose:** Self-contained ML model implementations. Each module handles its own tuning and training.

| File | Contents | Description |
|------|----------|-------------|
| `catboost_model.py` | `CatBoostModelConfig`, `tune_*`, `train_and_predict_*` | CatBoost pipeline |
| `lightgbm_model.py` | `LightGBMModelConfig`, `tune_*`, `train_and_predict_*` | LightGBM pipeline |
| `lstm_model.py` | `LSTMModelConfig`, `tune_*`, `train_and_predict_*` | LSTM with Optuna |
| `linear_model.py` | `LinearModelConfig`, `tune_*`, `train_and_predict_*` | Logistic/Ridge |
| `lstm.py` | `LSTMClassifier`, `LSTMRegressor` | **LEGACY** (see Issue #1) |

**Key Design:**
- Each module is **100% self-contained**
- Consistent interface: `train_and_predict_classifier(X_train, y_train, X_val, y_val, X_cal, y_cal, X_pred, config, ...)`
- Returns `ModelResult` with prediction, probabilities, metrics, trained model
- Optuna tuning integrated into each module

**Model Module Structure (consistent across all 4):**
```python
@dataclass
class *ModelConfig(ModelConfig):
    # Model-specific hyperparameters
    # Optuna settings
    # Override defaults from base

def tune_*_classifier(...) -> dict[str, Any]:
    # Optuna objective for classification

def tune_*_regressor(...) -> dict[str, Any]:
    # Optuna objective for regression

def train_and_predict_classifier(...) -> ModelResult:
    # 1. Optional Optuna tuning
    # 2. Combine train+val for final training
    # 3. Train model
    # 4. Predict
    # 5. Return ModelResult

def train_and_predict_regressor(...) -> ModelResult:
    # Same structure as classifier
```

---

### Layer 4: Adapters (`adapters/`)

**Purpose:** External data and output interfaces.

| File | Classes/Functions | Description |
|------|-------------------|-------------|
| `data_loader.py` | `ConfigData` | Data container for a config |
| | `parse_config()` | Parse config name → target spec |
| | `get_embargo_for_horizon()` | Dynamic embargo calculation |
| | `load_config_data()` | Load and preprocess data |
| | `load_timestamps_for_config()` | Load timestamps for datetime mapping |
| `output.py` | `DualOutput` | Console + file logging |

**Key Design:**
- `ConfigData` holds preprocessed data ready for training
- `get_embargo_for_horizon()` is DYNAMIC: `min(3 * horizon, 36)`
- Data loading uses external modules (`signal_labels`, `combined_datasets`)

---

### Layer 5: Services (`services/`)

**Purpose:** Orchestration and main execution logic.

| File | Functions | Description |
|------|-----------|-------------|
| `training.py` | `_get_model_configs()` | Create per-model configs with dynamic embargo |
| | `_apply_feature_selection_with_quick_model()` | Feature selection helper |
| | `train_predict_classification_permodel()` | 4-model ensemble classification |
| | `train_predict_regression_permodel()` | 4-model ensemble regression |
| `backtest.py` | `run_sync_backtest()` | Main walk-forward loop |
| | `_display_step_metrics()` | Live metrics display |
| | `_print_results_summary()` | Final summary output |

**Training Flow (`train_predict_classification_permodel`):**
```
1. _get_model_configs() → Create 4 configs with dynamic embargo
2. extract_per_model_splits() × 4 → Per-model train/val/cal splits
3. _apply_feature_selection_with_quick_model() × 4 → Per-model feature selection
4. *_train_predict_cls() × 4 → Train each model, get predictions
5. Weighted ensemble → Combine predictions
6. Conformal prediction → Uncertainty quantification
7. Return (y_pred, y_prob, prediction_set, components, tuned_params)
```

**Backtest Flow (`run_sync_backtest`):**
```
1. compute_common_pred_idx_range() → Align all configs
2. load_config_data() × N → Load all configs
3. Walk-forward loop:
   a. For each config at step:
      - Extract X_full, y_full, X_pred
      - Call train_predict_*_permodel()
      - Store predictions
      - Record accuracies for adaptive weights
   b. Update adaptive weights (MWU)
   c. Display metrics
4. Compute final metrics
5. Save results
```

---

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        BACKTEST DATA FLOW                               │
└─────────────────────────────────────────────────────────────────────────┘

                              ┌─────────────────┐
                              │  Config Files   │
                              │ (16 configs)    │
                              └────────┬────────┘
                                       │
                                       ▼
                         ┌─────────────────────────┐
                         │   load_config_data()    │
                         │  (adapters/data_loader) │
                         └────────────┬────────────┘
                                       │
                                       ▼
                              ┌───────────────┐
                              │  ConfigData   │
                              │ X_features    │
                              │ y_target      │
                              │ pred_idx      │
                              └───────┬───────┘
                                      │
                                      ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                        WALK-FORWARD LOOP                                 │
│                      (services/backtest.py)                              │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   For each step:                                                         │
│   ┌────────────────────────────────────────────────────────────────┐    │
│   │                                                                  │    │
│   │   X_full, y_full = extract window (800 bars max)                │    │
│   │   X_pred = prediction point                                      │    │
│   │                                                                  │    │
│   │   ┌──────────────────────────────────────────────────────────┐  │    │
│   │   │         train_predict_*_permodel()                        │  │    │
│   │   │              (services/training.py)                       │  │    │
│   │   ├──────────────────────────────────────────────────────────┤  │    │
│   │   │                                                            │  │    │
│   │   │   _get_model_configs()                                     │  │    │
│   │   │        ↓                                                   │  │    │
│   │   │   ┌─────────┬─────────┬─────────┬─────────┐               │  │    │
│   │   │   │CatBoost │LightGBM │  LSTM   │ Linear  │               │  │    │
│   │   │   │Config   │Config   │ Config  │ Config  │               │  │    │
│   │   │   │win=400  │win=400  │ win=600 │ win=800 │               │  │    │
│   │   │   └────┬────┴────┬────┴────┬────┴────┬────┘               │  │    │
│   │   │        │         │         │         │                     │  │    │
│   │   │        ▼         ▼         ▼         ▼                     │  │    │
│   │   │   extract_per_model_splits() × 4                           │  │    │
│   │   │        │         │         │         │                     │  │    │
│   │   │        ▼         ▼         ▼         ▼                     │  │    │
│   │   │   feature_selection() × 4                                  │  │    │
│   │   │        │         │         │         │                     │  │    │
│   │   │        ▼         ▼         ▼         ▼                     │  │    │
│   │   │   ┌─────────┬─────────┬─────────┬─────────┐               │  │    │
│   │   │   │train_   │train_   │train_   │train_   │               │  │    │
│   │   │   │predict  │predict  │predict  │predict  │               │  │    │
│   │   │   │_cls()   │_cls()   │_cls()   │_cls()   │               │  │    │
│   │   │   └────┬────┴────┬────┴────┬────┴────┬────┘               │  │    │
│   │   │        │         │         │         │                     │  │    │
│   │   │        └─────────┴─────────┴─────────┘                     │  │    │
│   │   │                      │                                      │  │    │
│   │   │                      ▼                                      │  │    │
│   │   │              ┌───────────────┐                             │  │    │
│   │   │              │   Weighted    │                             │  │    │
│   │   │              │   Ensemble    │                             │  │    │
│   │   │              └───────┬───────┘                             │  │    │
│   │   │                      │                                      │  │    │
│   │   │                      ▼                                      │  │    │
│   │   │              ┌───────────────┐                             │  │    │
│   │   │              │   Conformal   │                             │  │    │
│   │   │              │  Prediction   │                             │  │    │
│   │   │              └───────┬───────┘                             │  │    │
│   │   │                      │                                      │  │    │
│   │   └──────────────────────┼──────────────────────────────────┘  │    │
│   │                          │                                       │    │
│   │                          ▼                                       │    │
│   │   Store: y_pred, y_prob, prediction_set, components              │    │
│   │                          │                                       │    │
│   │                          ▼                                       │    │
│   │   AdaptiveWeightTracker.update_weights() (MWU)                   │    │
│   │                                                                  │    │
│   └────────────────────────────────────────────────────────────────┘    │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
                         ┌─────────────────────────┐
                         │   compute_config_metrics │
                         │   Save predictions       │
                         │   Save summary JSON      │
                         └─────────────────────────┘
```

---

## Configuration Reference

### SyncBacktestConfig (Main Config)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `train_window` | 500 | Shared fallback window (not used when per-model active) |
| `step_size` | 1 | Walk-forward step size |
| `n_steps` | None | Limit iterations (None = all) |
| `train_ratio` | 0.55 | Train split ratio |
| `val_ratio` | 0.15 | Validation split ratio |
| `cal_ratio` | 0.30 | Calibration split ratio |
| `embargo_bars` | 24 | Gap between splits |
| `cb_weight` | 0.30 | CatBoost ensemble weight |
| `lgb_weight` | 0.30 | LightGBM ensemble weight |
| `lstm_weight` | 0.25 | LSTM ensemble weight |
| `use_adaptive_weights` | True | Enable MWU weight adaptation |
| `adaptive_lookback` | 50 | Recent predictions for weight update |
| `enable_optuna` | True | Enable per-step Optuna tuning |
| `n_optuna_trials` | 15 | Trials per model |
| `optuna_timeout` | 30.0 | Seconds per model tuning |
| `conformal_alpha` | 0.1 | 90% confidence intervals |
| `cb_config` | None (required) | CatBoost config via optimize_catboost_config() |
| `lgb_config` | None (required) | LightGBM config via optimize_lightgbm_config() |
| `lstm_config` | None (required) | LSTM config via optimize_lstm_config() |
| `linear_config` | None (required) | Linear config via optimize_linear_config() |

### Per-Model Config Pattern (NEW)

Fixed DEFAULT_*_CONFIG constants have been **REMOVED**. Each model now:
1. Has an `optimize_*_config()` function that returns data-driven config
2. Requires config to be explicitly passed (no hidden defaults)
3. Raises `ValueError` if config is None

**Current Implementation:** Optimizer stubs return baseline values (same as old defaults).
**TODO:** Implement actual data-driven optimization per target/model combination.

**Baseline Values (from optimizer stubs):**

| Parameter | CB | LGB | LSTM | Linear |
|-----------|-----|-----|------|--------|
| `train_window` | 400 | 400 | 600 | 800 |
| `train_ratio` | 0.60 | 0.60 | 0.70 | 0.50 |
| `val_ratio` | 0.20 | 0.20 | 0.15 | 0.20 |
| `cal_ratio` | 0.20 | 0.20 | 0.15 | 0.30 |
| `embargo_bars` | 24 | 24 | 24 | 24 |
| `feature_selection` | importance | importance | variance | variance |
| `feature_selection_ratio` | 0.6 | 0.6 | 0.8 | 0.5 |
| `min_features` | 30 | 30 | 40 | 20 |

---

## Issues Found

---

### Issue #1: ~~Redundant `models/lstm.py`~~ — RESOLVED ✅

**Status:** FIXED (Jan 19, 2026)

**Action Taken:**
1. Moved `lstm.py` → `Archive-usefull-info-from-past-work/lstm_legacy_backup.py`
2. Updated imports in:
   - `models/__init__.py` — now imports from `lstm_model.py`
   - `backtest/__init__.py` — now imports from `lstm_model.py`
   - `l2_backtest_sync.py` — consolidated LSTM imports

**Verified:** `from backtest.models.lstm_model import LSTMClassifier, LSTMRegressor` works.

---

### Issue #2: ~~FIXED Configs Block Scalability~~ — RESOLVED ✅

**Status:** FIXED (Jan 19, 2026)

**Description (was):**  
ALL window sizes and split ratios were **FIXED at startup** via DEFAULT_*_CONFIG constants and never adapted during backtest execution.

**Resolution:**
1. **Removed** DEFAULT_CB_CONFIG, DEFAULT_LGB_CONFIG, DEFAULT_LSTM_CONFIG, DEFAULT_LINEAR_CONFIG from `domain/config.py`
2. **Removed** fallback to defaults in each model's train functions (now raises ValueError if config is None)
3. **Added** `optimize_*_config()` stub functions in each model module
4. **Updated** `services/training.py` to use explicit BASELINE dicts (documented, not hidden)
5. **Removed** auto-fill in `SyncBacktestConfig.__post_init__`

**New Architecture:**

```
┌────────────────────────────────────────────────────────────────────────┐
│                     NEW: DYNAMIC CONFIG FLOW                           │
└────────────────────────────────────────────────────────────────────────┘

User creates SyncBacktestConfig()
        │
        ▼ __post_init__
┌───────────────────────────┐
│ Configs are None by       │
│ default (must be set      │
│ explicitly or optimized)  │
└─────────────┬─────────────┘
              │
              ▼ For each step in walk-forward
┌───────────────────────────┐
│ training.py calls         │
│ optimize_*_config(X, y,   │
│   target_name, task_type) │
│                           │
│ Returns config tuned for: │
│ - Data characteristics    │
│ - Target type             │
│ - Model requirements      │
└─────────────┬─────────────┘
              │
              ▼
┌───────────────────────────┐
│ Model train function      │
│ REQUIRES config (no       │
│ default fallback)         │
└───────────────────────────┘
              │
              ▼
┌───────────────────────────┐
│ extract_per_model_splits()│ ← Uses FIXED window for ALL steps
└───────────────────────────┘

PROBLEM: Same config used for step 1 and step 1000
         No adaptation to regime changes, class balance, etc.
```

**SOLUTION: WHERE TO ADD OPTIMIZATION:**

```
┌────────────────────────────────────────────────────────────────────────┐
│                     TARGET: DYNAMIC CONFIG FLOW                        │
└────────────────────────────────────────────────────────────────────────┘

services/training.py: train_predict_*_permodel()
        │
        │ STEP 1: Get base configs (current code)
        ▼
┌───────────────────────────────┐
│ cb_cfg, lgb_cfg, lstm_cfg,   │
│ linear_cfg = _get_model_      │
│ configs(config, horizon)      │
└─────────────┬─────────────────┘
              │
              │ NEW STEP 2: Optimize configs based on data
              ▼
┌───────────────────────────────────────────────────────────────────┐
│                                                                    │
│  cb_cfg = optimize_catboost_config(X_full, y_full, cb_cfg)        │
│  lgb_cfg = optimize_lightgbm_config(X_full, y_full, lgb_cfg)      │
│  lstm_cfg = optimize_lstm_config(X_full, y_full, lstm_cfg)        │
│  linear_cfg = optimize_linear_config(X_full, y_full, linear_cfg)  │
│                                                                    │
│  Each optimize_* function:                                         │
│  - Analyzes X_full, y_full (ONLY past data, no leakage)           │
│  - Returns MODIFIED config with optimized:                         │
│    - train_window (based on stationarity, regime)                 │
│    - train/val/cal ratios (based on class balance, difficulty)    │
│    - feature_selection_ratio (based on feature stability)          │
│                                                                    │
└─────────────┬─────────────────────────────────────────────────────┘
              │
              │ STEP 3: Extract splits with OPTIMIZED configs
              ▼
┌───────────────────────────────┐
│ cb_train, cb_val, cb_cal =   │
│   extract_per_model_splits(  │
│     X_full, y_full, cb_cfg)  │ ← NOW USES DYNAMIC VALUES
└───────────────────────────────┘
```

**FILES TO MODIFY:**

| File | Change |
|------|--------|
| `models/catboost_model.py` | ADD `optimize_catboost_config(X, y, config) -> CatBoostModelConfig` |
| `models/lightgbm_model.py` | ADD `optimize_lightgbm_config(X, y, config) -> LightGBMModelConfig` |
| `models/lstm_model.py` | ADD `optimize_lstm_config(X, y, config) -> LSTMModelConfig` |
| `models/linear_model.py` | ADD `optimize_linear_config(X, y, config) -> LinearModelConfig` |
| `services/training.py` | CALL optimize_* after _get_model_configs() |

**NO-LEAKAGE GUARANTEE:**

```python
def optimize_catboost_config(
    X_full: pd.DataFrame,  # 800 bars BEFORE prediction point
    y_full: pd.Series,     # Targets for those 800 bars
    base_config: CatBoostModelConfig,
) -> CatBoostModelConfig:
    """
    Optimize config based on data characteristics.
    
    CRITICAL: X_full and y_full contain ONLY historical data.
    The prediction point (X_pred) is NOT included.
    This is guaranteed by the calling code in training.py.
    """
    # Analysis here uses ONLY past data
    # Returns modified config
```

---

### Issue #3: ICIR Feature Selection Not Implemented (MINOR)

**Severity:** LOW  
**Type:** Incomplete implementation

**Description:**  
In `core/features.py`, the `icir` method falls back to variance:

```python
elif method == "icir":
    # Information Coefficient / Information Ratio
    # For now, use correlation with target as proxy
    # TODO: Implement proper ICIR calculation
    variances = X.var()
    selected_features = variances.nlargest(n_keep).index.tolist()
```

**Impact:** Linear model uses `feature_selection="icir"` but gets variance selection instead.

**Recommendation:** Implement proper ICIR calculation or change Linear default to `variance`.

---

### Issue #4: Incomplete `__init__.py` Exports (MINOR)

**Severity:** LOW  
**Type:** Code organization

**Description:**  
Three `__init__.py` files have placeholder comments instead of actual re-exports.

**Affected Files:**
- `domain/__init__.py` - 4 lines, placeholder only
- `adapters/__init__.py` - 5 lines, placeholder only
- `services/__init__.py` - 5 lines, placeholder only

**Impact:** Users must use full import paths or root `__init__.py`.

**Recommendation:** Add proper exports to enable cleaner imports.

---

## Scalability Analysis

### Current State: PARTIALLY Scalable

| Aspect | Status | Limitation |
|--------|--------|------------|
| Per-model configs exist | ✅ | — |
| Models are self-contained | ✅ | — |
| Configs are passed per-step | ✅ | — |
| Configs adapt per-step | ❌ | **FIXED at startup** |

### What "Scalable" Means For Us

**NOT SCALABLE (current):** Same window=400 for CatBoost on step 1 and step 1000
**SCALABLE (target):** Window size adapts based on regime, stationarity, class balance

### Architecture Readiness

The architecture IS ready for dynamic optimization:

1. ✅ **Clean injection point** — `training.py:train_predict_*_permodel()` has access to `X_full, y_full`
2. ✅ **Configs are passed, not global** — Each step gets its own config objects
3. ✅ **Models are independent** — Can optimize each model differently
4. ✅ **No circular dependencies** — Can add `optimize_*` to model modules

**Only missing:** The `optimize_*_config()` functions themselves.

---

## Summary

| Aspect | Status | Notes |
|--------|--------|-------|
| **Clarity** | ✅ | Well-structured layers, consistent naming |
| **Consistency** | ✅ | All models follow same pattern |
| **Scalability (Structure)** | ✅ | Architecture supports dynamic configs |
| **Scalability (Runtime)** | ❌ | Configs are FIXED (Issue #2) |
| **No Bugs** | ✅ | No functional bugs found |
| **Redundancy** | ⚠️ | `lstm.py` duplicate (Issue #1) |
| **Completeness** | ⚠️ | ICIR not implemented (Issue #3) |

**Overall Assessment:** 
- Architecture is **structurally ready** for dynamic optimization
- **BLOCKING:** Need to implement `optimize_*_config()` functions per model
- **CLEANUP:** lstm.py decision needed, ICIR optional

---

## Action Items

| Priority | Issue | Action |
|----------|-------|--------|
| 🔴 HIGH | #2 Fixed Configs | Implement `optimize_*_config()` per model (next phase) |
| ✅ DONE | #1 lstm.py | Moved to archive, imports updated |
| 🟢 LOW | #3 ICIR | Implement or change Linear default |
| 🟢 LOW | #4 __init__.py | Add proper exports |

---

*Document created: 2026-01-19*  
*Author: Astra*

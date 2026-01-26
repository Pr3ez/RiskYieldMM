# CatBoost Model Module Documentation

**Module:** `backtest/models/catboost_model.py`  
**Lines:** 1405  
**Last Verified:** January 2026

---

## 1. Overview

The CatBoost model module provides a **self-contained, 4-stage dynamic configuration optimization pipeline** for CatBoost training. It automatically adapts training parameters based on data characteristics, eliminating the need for manual tuning.

### Key Design Principles
1. **Self-contained** - No dependencies on legacy `training.py` or `tuning.py`
2. **Temporal integrity** - All operations maintain strict temporal splits (no leakage)
3. **Data-driven** - Configs are optimized per-step based on actual data characteristics
4. **Warm-start capable** - Can use previous step's best params as starting point

---

## 2. Module Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        catboost_model.py (1405 lines)                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ SECTION 1: CONFIGURATION (lines 60-112)                              │    │
│  │  └── CatBoostModelConfig (dataclass)                                 │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ SECTION 2: FEATURE SELECTION (lines 118-220)                         │    │
│  │  ├── select_features_catboost()      ← importance-based (trains model)│    │
│  │  └── select_features_catboost_regression()  ← variance-based (fast)  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ SECTION 3: DATA CHARACTERIZATION - Stage 1 (lines 226-396)           │    │
│  │  ├── DataCharacteristics (dataclass, 21 fields)                      │    │
│  │  └── characterize_data()             ← Analyzes X_full, y_full       │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ SECTION 4: CANDIDATE GENERATION - Stage 2 (lines 402-600)            │    │
│  │  └── generate_candidate_configs()    ← Creates 3-5 configs           │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ SECTION 5: HOLDOUT VALIDATION - Stage 3 (lines 606-800)              │    │
│  │  ├── _quick_train_evaluate()         ← Internal helper               │    │
│  │  └── validate_configs_on_holdout()   ← Oldest 15% as test set        │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ SECTION 6: HYPERPARAMETER REFINEMENT - Stage 4 (lines 806-970)       │    │
│  │  └── refine_hyperparameters()        ← Optuna fine-tuning            │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ SECTION 7: CONFIG OPTIMIZATION (lines 976-1068)                      │    │
│  │  └── optimize_catboost_config()      ← PUBLIC: Calls Stages 1-4      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ SECTION 8: TUNING FUNCTIONS (lines 1074-1192)                        │    │
│  │  ├── tune_catboost_classifier()      ← Optuna at runtime             │    │
│  │  └── tune_catboost_regressor()       ← Optuna at runtime             │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ SECTION 9: TRAINING FUNCTIONS (lines 1198-1405)                      │    │
│  │  ├── train_and_predict_classifier()  ← Full train + predict pipeline │    │
│  │  └── train_and_predict_regressor()   ← Full train + predict pipeline │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Exports (`__all__`)

| Export | Type | Usage | Called By |
|--------|------|-------|-----------|
| `CatBoostModelConfig` | dataclass | Config container | training.py, tests |
| `DataCharacteristics` | dataclass | Internal (Stage 1 output) | tests only |
| `characterize_data` | function | Internal (Stage 1) | tests only |
| `generate_candidate_configs` | function | Internal (Stage 2) | internal only |
| `validate_configs_on_holdout` | function | Internal (Stage 3) | internal only |
| `refine_hyperparameters` | function | Internal (Stage 4) | internal only |
| `select_features_catboost` | function | **Production** | training.py:377 |
| `select_features_catboost_regression` | function | **Production** | training.py:701 |
| `tune_catboost_classifier` | function | Internal (called by training funcs) | l2_backtest_sync.py |
| `tune_catboost_regressor` | function | Internal (called by training funcs) | internal only |
| `train_and_predict_classifier` | function | **Production** | training.py |
| `train_and_predict_regressor` | function | **Production** | training.py |
| `optimize_catboost_config` | function | **Production** | training.py:322, 666 |

### Production vs Internal

**Production (imported by training.py):**
- `CatBoostModelConfig`
- `optimize_catboost_config`
- `select_features_catboost` / `select_features_catboost_regression`
- `train_and_predict_classifier` / `train_and_predict_regressor`

**Internal (called within module only):**
- `characterize_data` → Stage 1
- `generate_candidate_configs` → Stage 2
- `validate_configs_on_holdout` → Stage 3
- `refine_hyperparameters` → Stage 4
- `tune_catboost_classifier/regressor` → Called by training funcs

---

## 4. The 4-Stage Optimization Pipeline

```
          optimize_catboost_config(X_full, y_full, target_name, ...)
                                    │
                                    ▼
    ┌───────────────────────────────────────────────────────────────┐
    │ STAGE 1: DATA CHARACTERIZATION                                 │
    │ characterize_data() → DataCharacteristics                      │
    │                                                                │
    │ Computes 21 metrics across 5 categories:                       │
    │ • Target: n_classes, class_balance, imbalance_ratio, etc.      │
    │ • Stationarity: ADF test, rolling drift                        │
    │ • Regime: volatility_level, volatility_ratio, trend_strength   │
    │ • Features: n_features, n_low_variance, correlations           │
    │ • Samples: n_samples, samples_per_class                        │
    └───────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
    ┌───────────────────────────────────────────────────────────────┐
    │ STAGE 2: CANDIDATE GENERATION                                  │
    │ generate_candidate_configs() → List[CatBoostModelConfig]       │
    │                                                                │
    │ Creates 3-5 configs based on:                                  │
    │ 1. Baseline config                                             │
    │ 2. Class balance adjustment (if imbalanced)                    │
    │ 3. Stationarity adjustment (if non-stationary)                 │
    │ 4. Volatility regime adjustment (high/low)                     │
    │ 5. Target-type specific (direction/volatility/regime/extreme)  │
    │ 6. Horizon multiplier (1/3/6/12 → 1.0/1.1/1.2/1.3x)           │
    └───────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
    ┌───────────────────────────────────────────────────────────────┐
    │ STAGE 3: HOLDOUT VALIDATION                                    │
    │ validate_configs_on_holdout() → best_config                    │
    │                                                                │
    │ • Holdout = OLDEST 15% (temporal, no shuffle)                  │
    │ • Train/val from remaining 85%                                 │
    │ • Score = 0.6*accuracy + 0.4*(1 - log_loss_normalized)         │
    │ • Returns config with highest combined_score                   │
    └───────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
    ┌───────────────────────────────────────────────────────────────┐
    │ STAGE 4: HYPERPARAMETER REFINEMENT (Optional)                  │
    │ refine_hyperparameters() → final_config                        │
    │                                                                │
    │ • Optuna 10 trials, 20s timeout                                │
    │ • Search around Stage 3 best:                                  │
    │   - iterations: 50-300                                         │
    │   - depth: base ± 2 (clamped 4-10)                             │
    │   - learning_rate: 0.5x-2x base (log scale)                    │
    │   - l2_leaf_reg: 0.5x-2x base                                  │
    │ • Warm-start from previous_best if provided                    │
    └───────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
                          CatBoostModelConfig
```

---

## 5. Configuration Bounds

All generated configs must satisfy:

| Parameter | Min | Max | Default |
|-----------|-----|-----|---------|
| `train_window` | 200 | 700 | 400 |
| `train_ratio` | 0.50 | 0.70 | 0.60 |
| `val_ratio` | 0.15 | 0.25 | 0.20 |
| `cal_ratio` | 0.10 | 0.30 | 0.20 |
| **Sum of ratios** | | | **1.00 ± 0.01** |

---

## 6. Feature Selection

### Classification: `select_features_catboost()`
1. Trains a **quick CatBoost model** (50 iterations, depth 4)
2. Gets feature importances from trained model
3. Selects top features by importance

### Regression: `select_features_catboost_regression()`
1. Computes variance of each feature
2. Selects features with highest variance
3. Faster than training a model

### Note on Consistency
⚠️ **Potential Concern:** Stage 3/4 use variance-based selection for speed (in `_quick_train_evaluate`), but actual training uses importance-based selection (in `training.py`). This is intentional - Stage 3/4 need fast evaluation, while actual training can afford the extra model fit.

---

## 7. Optuna Integration

The module has **two places** where Optuna is used:

### A. Runtime Tuning (`tune_catboost_classifier/regressor`)
- Called from `train_and_predict_classifier/regressor` when `tune=True`
- **Fixed search space:**
  - iterations: 50-300
  - depth: 3-8
  - learning_rate: 0.01-0.3 (log)
  - l2_leaf_reg: 1.0-10.0

### B. Stage 4 Refinement (`refine_hyperparameters`)
- Called from `optimize_catboost_config` when `enable_hyperparameter_refinement=True`
- **Search around base config:**
  - iterations: 50-300
  - depth: base ± 2
  - learning_rate: 0.5x-2x base (log)
  - l2_leaf_reg: 0.5x-2x base

### Warm-Start
Both support `previous_best` parameter to seed Optuna with previous step's best params.

---

## 8. Usage Examples

### Basic Usage (Production)
```python
from backtest.models.catboost_model import (
    CatBoostModelConfig,
    optimize_catboost_config,
    select_features_catboost,
    train_and_predict_classifier,
)

# 1. Optimize config based on data (ALL 4 STAGES - quality first)
config = optimize_catboost_config(
    X_full=X_history,
    y_full=y_history,
    target_name="direction_1bar",
    task_type="classification",
    horizon=1,
    enable_hyperparameter_refinement=True,  # Stage 4 enabled for quality
    previous_best=prev_params,              # Warm-start for better results
)

# 2. Select features
features = select_features_catboost(X_train, y_train, config, n_classes=3)
X_train_sel = X_train[features]
X_val_sel = X_val[features]
X_cal_sel = X_cal[features]
X_pred_sel = X_pred[features]

# 3. Train and predict
result = train_and_predict_classifier(
    X_train=X_train_sel,
    y_train=y_train,
    X_val=X_val_sel,
    y_val=y_val,
    X_cal=X_cal_sel,
    y_cal=y_cal,
    X_pred=X_pred_sel,
    config=config,
    n_classes=3,
    tune=True,
)

prediction = result.prediction       # 0, 1, or 2
probabilities = result.probabilities # [p0, p1, p2]
```

### Testing Internal Components
```python
from backtest.models.catboost_model import (
    DataCharacteristics,
    characterize_data,
    generate_candidate_configs,
    validate_configs_on_holdout,
)

# Inspect data characteristics
chars = characterize_data(X_full, y_full, "classification")
print(f"Classes: {chars.n_classes}, Balance: {chars.class_balance}")
print(f"Stationary: {chars.is_stationary}, Drift: {chars.rolling_mean_drift}")

# Generate candidates
candidates = generate_candidate_configs(chars, "direction_1bar", horizon=1)
print(f"Generated {len(candidates)} candidate configs")

# Validate candidates
best_config, results = validate_configs_on_holdout(
    X_full, y_full, candidates, "classification", n_classes=3
)
print(f"Best combined score: {results['best_score']['combined_score']:.3f}")
```

---

## 9. Test Coverage

### Unit Tests (`tests/test_catboost_optimization_unit.py`)
| Test | What It Verifies |
|------|------------------|
| `test_data_characteristics_fields` | All 21 DataCharacteristics fields present |
| `test_characterize_data_classification` | Classification analysis correct |
| `test_characterize_data_regression` | Regression analysis correct |
| `test_no_leakage_in_optimization` | No future data in optimization |
| `test_config_bounds` | Configs within valid bounds |
| `test_target_specific_adjustments` | Different targets → different configs |
| `test_all_28_configs` | All 7 targets × 4 horizons work |

### Integration Tests (`tests/compare_baseline_vs_optimized.py`)
- Compares baseline (fixed config) vs optimized (dynamic config) accuracy
- Pass threshold: optimized >= 95% of baseline

### Coverage Gaps
- `tune_catboost_classifier/regressor` - No direct unit tests (tested via integration)
- `refine_hyperparameters` - Disabled in most tests for speed

---

## 10. Configuration Reference

### CatBoostModelConfig Fields

```python
@dataclass
class CatBoostModelConfig(ModelConfig):
    # CatBoost Hyperparameters
    n_estimators: int = 100       # iterations
    max_depth: int = 6            # arXiv 2305.17094 optimal
    learning_rate: float = 0.03   # Conservative
    l2_leaf_reg: float = 5.0      # Increased regularization

    # GPU Settings
    use_gpu: bool = True
    gpu_device: str = "0"

    # Optuna Tuning (quality-first settings)
    enable_tuning: bool = True
    n_optuna_trials: int = 25         # More trials for quality
    optuna_timeout: float | None = 60.0  # 60s for thorough search

    # Split Configuration (from ModelConfig)
    train_window: int = 400
    train_ratio: float = 0.60
    val_ratio: float = 0.20
    cal_ratio: float = 0.20
    embargo_bars: int = 24

    # Feature Selection
    feature_selection: str = "importance"
    feature_selection_ratio: float = 0.6
    min_features: int = 30
```

### DataCharacteristics Fields (21 total)

| Category | Fields |
|----------|--------|
| **Target (7)** | `task_type`, `n_classes`, `class_balance`, `class_imbalance_ratio`, `target_mean`, `target_std`, `target_skew` |
| **Stationarity (5)** | `adf_statistic`, `adf_pvalue`, `is_stationary`, `rolling_mean_drift`, `rolling_std_drift` |
| **Regime (3)** | `volatility_level`, `volatility_ratio`, `trend_strength` |
| **Features (4)** | `n_features`, `n_low_variance`, `mean_correlation`, `max_correlation` |
| **Samples (2)** | `n_samples`, `samples_per_class` |

---

## 11. Dependencies

### External
- `catboost` - CatBoostClassifier, CatBoostRegressor
- `optuna` - Hyperparameter optimization
- `numpy`, `pandas` - Data manipulation
- `scipy.stats` - skew calculation
- `statsmodels.tsa.stattools` - ADF test
- `sklearn.metrics` - accuracy_score, log_loss, MSE, MAE

### Internal
- `backtest.core.base` - ModelConfig, ModelResult

---

## 12. Maintenance Notes

### Adding New Target Types
1. Add case in `generate_candidate_configs()` (lines ~530-600)
2. Update tests in `test_all_28_configs()`

### Changing Optimization Stages
- Stage 1: Modify `characterize_data()` and `DataCharacteristics`
- Stage 2: Modify `generate_candidate_configs()`
- Stage 3: Modify `validate_configs_on_holdout()` and `_quick_train_evaluate()`
- Stage 4: Modify `refine_hyperparameters()`

### Performance Tuning
- **Quality First:** All stages enabled by default
- Stage 4 uses 25 trials, 60s timeout for thorough hyperparameter search
- Runtime tuning uses 25 trials, 60s timeout
- Use `previous_best` warm-start to leverage learnings from previous steps

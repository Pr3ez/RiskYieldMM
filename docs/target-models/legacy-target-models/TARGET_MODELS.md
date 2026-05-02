# Target Models Documentation

> **20 Models**: 5 targets × 4 horizons  
> **Architecture**: One optimized dataset per target-horizon, one model per dataset

---

## Overview

Each target-horizon combination has:
1. **Optimized base features** in `data/datasets/{target}_{horizon}bar.parquet`
2. **Optimized helper configs** per target-horizon in `data/analysis/results/optimal_helper_configs.json`
3. **Trained model** per dataset in `data/models/`
4. **Results storage** in `data/target_model_results/`

**Key principle**: Everything is optimized SEPARATELY for each of the 20 target-horizon combinations:
- Base feature preprocessing (Winsorize, ZScore, Interactions) → per target-horizon
- Helper model configs (HMM states, Kalman noise, etc.) → per target-horizon  
- Supervised models (CatBoost, LightGBM) → per target-horizon

---

## Target Summary

| Target | Task Type | Primary Metric | Models | Description |
|--------|-----------|----------------|--------|-------------|
| **volatility** | Regression | RMSE | CatBoost, LightGBM, Ridge | Predict `|forward_return|` magnitude |
| **direction** | Binary | AUC | CatBoost, LightGBM, LogisticRegression | Predict sign of forward return (1=up, 0=down) |
| **returns** | Regression | RMSE | CatBoost, LightGBM, Ridge | Predict raw forward return value |
| **vol_regime** | Multiclass | Accuracy | CatBoost, LightGBM, RandomForest | Classify volatility regime (low/medium/high) |
| **trend_regime** | Binary | AUC | CatBoost, LightGBM, LogisticRegression | Classify trend state (trending vs mean-reverting) |

---

## Data Flow: Complete Isolation Per Target-Horizon

**Critical principle**: Each of the 20 target-horizons is COMPLETELY ISOLATED. Nothing is shared.

### Data Files (20 separate parquet files)

```
data/datasets/
├── volatility_1bar.parquet    # volatility predictions, 1-bar horizon
├── volatility_3bar.parquet
├── volatility_6bar.parquet
├── volatility_12bar.parquet
├── direction_1bar.parquet     # direction predictions, 1-bar horizon
├── direction_3bar.parquet
├── direction_6bar.parquet
├── direction_12bar.parquet
├── returns_1bar.parquet
├── returns_3bar.parquet
├── returns_6bar.parquet
├── returns_12bar.parquet
├── vol_regime_1bar.parquet
├── vol_regime_3bar.parquet
├── vol_regime_6bar.parquet
├── vol_regime_12bar.parquet
├── trend_regime_1bar.parquet
├── trend_regime_3bar.parquet
├── trend_regime_6bar.parquet
└── trend_regime_12bar.parquet
```

### Loading Data

```python
from scripts.target_models.registry import load_target_data

# Each call loads a SEPARATE parquet file
X_vol6, y_vol6, spec = load_target_data("volatility", 6)   # → volatility_6bar.parquet
X_dir1, y_dir1, spec = load_target_data("direction", 1)    # → direction_1bar.parquet
```

### Optimization Pipeline (Per Target-Horizon)

```
FOR EACH of the 20 target-horizons:
    
    1. LOAD: data/datasets/{target}_{horizon}bar.parquet
           ↓
    2. OPTIMIZE BASE FEATURES (already done by auto-optimizer):
       - Winsorize, ZScore, Interactions selected PER target-horizon
       - Results stored IN the parquet file
           ↓
    3. OPTIMIZE HELPERS (Layer 1):
       - Grid search for HMM, GARCH, IF, Kalman, CUSUM configs
       - IC computed against THIS target's y values
       - Results: data/analysis/results/optimal_helper_configs.json
           ↓
    4. TRAIN SUPERVISED MODELS (Layer 2):
       - CatBoost/LightGBM/Ridge trained on helper features
       - Optimized for THIS specific target
           ↓
    5. OUTPUT: Predictions for THIS target-horizon only
```

### Volatility (Regression)

| Horizon | Features | Samples | Valid Targets | Size (KB) | Dataset Path |
|---------|----------|---------|---------------|-----------|--------------|
| 1-bar | 166 | 5,438 | 5,437 | 6,212 | `volatility_1bar.parquet` |
| 3-bar | 166 | 5,438 | 5,435 | 6,212 | `volatility_3bar.parquet` |
| 6-bar | 166 | 5,438 | 5,432 | 6,212 | `volatility_6bar.parquet` |
| 12-bar | 166 | 5,438 | 5,426 | 6,212 | `volatility_12bar.parquet` |

**Target column**: `y_volatility`  
**Optimization result**: +0.2% to +0.3% IC improvement (Winsorize only)  
**Note**: No interactions added (they degraded performance)

---

### Direction (Binary Classification)

| Horizon | Features | Samples | Valid Targets | Size (KB) | Dataset Path |
|---------|----------|---------|---------------|-----------|--------------|
| 1-bar | 171 | 5,438 | 5,437 | 6,360 | `direction_1bar.parquet` |
| 3-bar | 171 | 5,438 | 5,435 | 6,345 | `direction_3bar.parquet` |
| 6-bar | 171 | 5,438 | 5,432 | 6,365 | `direction_6bar.parquet` |
| 12-bar | 170 | 5,438 | 5,426 | 6,312 | `direction_12bar.parquet` |

**Target column**: `y_direction`  
**Optimization result**: +5.7% to +26.0% IC improvement  
**Pipeline**: Winsorize + ZScore + Interactions

---

### Returns (Regression)

| Horizon | Features | Samples | Valid Targets | Size (KB) | Dataset Path |
|---------|----------|---------|---------------|-----------|--------------|
| 1-bar | 171 | 5,438 | 5,437 | 6,400 | `returns_1bar.parquet` |
| 3-bar | 170 | 5,438 | 5,435 | 6,352 | `returns_3bar.parquet` |
| 6-bar | 171 | 5,438 | 5,432 | 6,399 | `returns_6bar.parquet` |
| 12-bar | 171 | 5,438 | 5,426 | 6,399 | `returns_12bar.parquet` |

**Target column**: `y_returns`  
**Optimization result**: +5.3% to +22.6% IC improvement  
**Pipeline**: Winsorize + ZScore + Interactions

---

### Vol Regime (Multiclass Classification)

| Horizon | Features | Samples | Valid Targets | Size (KB) | Dataset Path |
|---------|----------|---------|---------------|-----------|--------------|
| 1-bar | 171 | 5,438 | 5,438 | 6,367 | `vol_regime_1bar.parquet` |
| 3-bar | 171 | 5,438 | 5,438 | 6,367 | `vol_regime_3bar.parquet` |
| 6-bar | 171 | 5,438 | 5,438 | 6,367 | `vol_regime_6bar.parquet` |
| 12-bar | 171 | 5,438 | 5,438 | 6,367 | `vol_regime_12bar.parquet` |

**Target column**: `y_vol_regime`  
**Classes**: 0 (low), 1 (medium), 2 (high)  
**Optimization result**: +4.1% to +4.9% IC improvement  
**Pipeline**: Winsorize + Interactions

---

### Trend Regime (Binary Classification)

| Horizon | Features | Samples | Valid Targets | Size (KB) | Dataset Path |
|---------|----------|---------|---------------|-----------|--------------|
| 1-bar | 170 | 5,438 | 5,376 | 6,327 | `trend_regime_1bar.parquet` |
| 3-bar | 170 | 5,438 | 5,376 | 6,327 | `trend_regime_3bar.parquet` |
| 6-bar | 170 | 5,438 | 5,349 | 6,327 | `trend_regime_6bar.parquet` |
| 12-bar | 169 | 5,438 | 5,259 | 6,284 | `trend_regime_12bar.parquet` |

**Target column**: `y_trend_regime`  
**Classes**: 0 (mean-reverting), 1 (trending)  
**Optimization result**: +3.9% to +10.1% IC improvement  
**Pipeline**: Winsorize + Interactions

---

## Dual-Layer Walk-Forward Architecture

During inference/backtesting, the pipeline uses a dual-layer walk-forward structure:

### Window Layout

```
Data: [0 ─────────────────────────────────────────── N]
           │<── L1 EXPANDING ──>│<── L2 SLIDING ──>│pred
           [0 ─────────── L2_start][L2 window ───→][1]
                 grows ↑              slides →
```

**Layer 1 (Helpers)**: Expanding window using ALL historical data
**Layer 2 (Supervised)**: Fixed sliding window (e.g., 500 rows)

### Detailed Window Structure

```
[0 ─────────── L2_start][L2_train][purge][L2_cal][L2_val][pred]
│<─── L1 expanding ───>│<────── L2 sliding ─────────────>│
```

This structure ensures:
1. **No data leakage** — L1 ends before L2 starts
2. **Purge gap** — prevents autocorrelation leakage
3. **Consistent prediction timestamps** — all targets can predict same point

### Default Configuration

| Layer | Component | Default Size | Purpose |
|-------|-----------|-------------|---------|
| **L1** | min_warmup | 500 | Minimum rows before L1 produces features |
| **L1** | holdout_ratio | 0.2 | Last 20% for validation |
| **L2** | window_size | 500 | Total L2 window |
| **L2** | train_ratio | 0.7 | 70% for training |
| **L2** | cal_ratio | 0.15 | 15% for calibration |
| **L2** | val_ratio | 0.15 | 15% for validation |
| **L2** | purge_gap | 21 | Gap between train and cal |

---

## Layer 1: Helper Models

Layer 1 consists of **6 unsupervised helper models** that generate **58 features** for Layer 2.

### Helper Summary

| Helper | States/Modes | Features | Purpose |
|--------|-------------|----------|---------|
| **HMM4** | 4 market regimes | 9 | Market regime detection |
| **HMM5** | 5 volatility regimes | 10 | Volatility regime detection |
| **GARCH** | (1,1) model | 8 | Conditional volatility estimation |
| **IsolationForest** | 3 contamination levels | 12 | Multi-level anomaly detection |
| **Kalman** | 3D state estimation | 7 | State estimation/smoothing |
| **CUSUM** | Change detection | 12 | Change point detection |
| **Total** | — | **58** | — |

### Helper Optimization — Per Target-Horizon

**Each of the 20 target-horizons gets its OWN optimized helper configs.**

The helper optimizer loads data from `data/datasets/{target}_{horizon}bar.parquet` and finds the best configuration for each helper model against that specific target.

```bash
# Optimize helpers for volatility_6bar
python -c "
from scripts.analysis.optimizers.helper_optimizer import run_helper_optimization
run_helper_optimization(targets=['volatility'], horizons=[6])
"

# Optimize ALL 20 target-horizons
python -c "
from scripts.analysis.optimizers.helper_optimizer import run_helper_optimization
run_helper_optimization()  # targets=None, horizons=None runs all 20
"
```

### ICIR Feature Selection (Layer 1 → Layer 2)

After helpers produce ~58 features, **ICIR (Information Coefficient Information Ratio)** filters for stable, non-redundant features.

**Why ICIR over IC?**
| Metric | Formula | What it measures |
|--------|---------|------------------|
| **IC** | Spearman(feature, target) | Single-point correlation |
| **ICIR** | mean(IC) / std(IC) | Signal **consistency** over time |

**Algorithm:**
1. Compute **rolling ICIR** over 5 windows per feature
2. Keep features with `|ICIR| >= 0.30` (configurable)
3. Apply **correlation filter** (drop `|corr| > 0.90` pairs, keep higher ICIR)
4. Fallback to single IC if insufficient data

**Configuration:**
```python
from scripts.target_models.helpers import ICIRConfig, DEFAULT_ICIR_CONFIG

# Default configuration
config = ICIRConfig(
    enable_icir=True,             # Master switch
    icir_threshold=0.30,          # Min ICIR to keep feature
    correlation_threshold=0.90,   # Max correlation between features
    n_rolling_windows=5,          # Windows for rolling ICIR
)

# Preset configurations
from scripts.target_models.helpers import (
    DEFAULT_ICIR_CONFIG,    # Balanced (ICIR=0.30, corr=0.90)
    ICIR_CONFIG_STRICT,     # Fewer features (ICIR=0.50, corr=0.80)
    ICIR_CONFIG_LENIENT,    # More features (ICIR=0.20, corr=0.95)
    ICIR_CONFIG_DISABLED,   # Legacy IC-only mode
)
```

**Validation Results (all 20 targets):**
| Metric | Value |
|--------|-------|
| Avg ICIR-selected | 27.2 features |
| Avg IC-selected (legacy) | 40.5 features |
| Avg reduction | **32.1%** |
| Targets >30% reduction | 12/20 |

**Output structure** (`data/analysis/results/optimal_helper_configs.json`):
```json
{
  "volatility_1bar": {
    "helpers": {
      "hmm4": {"config": {"n_states": 4}, "ic": 0.082},
      "kalman": {"config": {"process_noise": 1e-5}, "ic": 0.045},
      ...
    }
  },
  "volatility_3bar": { ... },
  "direction_1bar": { ... },
  ...  // All 20 target-horizons
}
```

### Helper Optimization Results (Per Target-Horizon)

Optimized configurations stored in `data/analysis/results/optimal_helper_configs.json`:

| Helper | Avg IC Improvement | Best Config Parameters |
|--------|-------------------|------------------------|
| **HMM4** | +48.6% | n_states, covariance_type |
| **Kalman** | +26.8% | process_noise, measurement_noise |
| **HMM5** | +23.1% | n_states, covariance_type |
| **IF** | +18.2% | contamination levels |
| **CUSUM** | +16.9% | threshold, drift |
| **GARCH** | +0.0% | Default always best |

### Helper Optimization Leak Prevention

Helper optimization uses **ONLY L1 data**:
- L1.train (first 80%): Fit helpers
- L1.val (last 20%): Compute IC for config selection
- L2 data is **NEVER** seen during optimization

---

## Model Architectures

### Regression Models (volatility, returns)

| Model | Implementation | Handles NaN | Default Params |
|-------|----------------|-------------|----------------|
| **CatBoost** | `CatBoostRegressor` | ✅ Yes | depth=6, lr=0.03, iterations=1000 |
| **LightGBM** | `LGBMRegressor` | ✅ Yes | max_depth=6, lr=0.03, n_estimators=1000 |
| **Ridge** | `sklearn.Ridge` | ❌ No | alpha=1.0 (needs imputation) |

### Binary Classification Models (direction, trend_regime)

| Model | Implementation | Handles NaN | Default Params |
|-------|----------------|-------------|----------------|
| **CatBoost** | `CatBoostClassifier` | ✅ Yes | depth=6, lr=0.03, iterations=1000 |
| **LightGBM** | `LGBMClassifier` | ✅ Yes | max_depth=6, lr=0.03, n_estimators=1000 |
| **LogisticRegression** | `sklearn.LogisticRegression` | ❌ No | C=1.0, max_iter=1000 |

### Multiclass Classification Models (vol_regime)

| Model | Implementation | Handles NaN | Default Params |
|-------|----------------|-------------|----------------|
| **CatBoost** | `CatBoostClassifier` | ✅ Yes | depth=6, lr=0.03, loss_function=MultiClass |
| **LightGBM** | `LGBMClassifier` | ✅ Yes | max_depth=6, objective=multiclass |
| **RandomForest** | `sklearn.RandomForestClassifier` | ❌ No | n_estimators=500, max_depth=10 |

---

## Cross-Validation Strategy

**PurgedTimeSeriesSplit** — temporal CV with gap enforcement

```
Configuration:
- n_splits: 5
- purge_gap: 21 bars (prevent look-ahead leakage)
- embargo_gap: 12 bars (prevent autocorrelation leakage)
```

```
Visual representation:

Fold 1: [=====TRAIN=====]---purge---[==TEST==]---embargo---
Fold 2: [========TRAIN========]---purge---[==TEST==]---embargo---
Fold 3: [===========TRAIN===========]---purge---[==TEST==]---embargo---
Fold 4: [==============TRAIN==============]---purge---[==TEST==]---embargo---
Fold 5: [=================TRAIN=================]---purge---[==TEST==]
```

---

## Evaluation Metrics

### Regression (volatility, returns)

| Metric | Description | Optimal |
|--------|-------------|---------|
| **RMSE** | Root Mean Squared Error | Lower is better |
| **MAE** | Mean Absolute Error | Lower is better |
| **R²** | Coefficient of determination | Higher (>0) is better |
| **IC** | Information Coefficient (Spearman) | Higher is better |

### Binary Classification (direction, trend_regime)

| Metric | Description | Optimal |
|--------|-------------|---------|
| **AUC** | Area Under ROC Curve | Higher (>0.5) is better |
| **Accuracy** | Correct predictions / Total | Higher is better |
| **F1** | Harmonic mean of precision/recall | Higher is better |
| **Log Loss** | Negative log likelihood | Lower is better |

### Multiclass Classification (vol_regime)

| Metric | Description | Optimal |
|--------|-------------|---------|
| **Accuracy** | Correct predictions / Total | Higher is better |
| **F1 Macro** | Average F1 across classes | Higher is better |
| **Log Loss** | Negative log likelihood | Lower is better |

---

## Usage

### Running Cross-Validation

```bash
# Volatility (implemented)
python -m scripts.target_models.run_volatility cv --horizon 6

# All horizons
python -m scripts.target_models.run_volatility cv --horizon 1
python -m scripts.target_models.run_volatility cv --horizon 3
python -m scripts.target_models.run_volatility cv --horizon 6
python -m scripts.target_models.run_volatility cv --horizon 12
```

### Training Final Model

```bash
python -m scripts.target_models.run_volatility train --horizon 6 --model catboost
```

### Evaluating Saved Model

```bash
python -m scripts.target_models.run_volatility evaluate --horizon 6 --model catboost
```

---

## File Structure

```
scripts/target_models/
├── __init__.py              # Package exports
├── config.py                # TargetConfig, paths, hyperparameter spaces
├── base.py                  # BaseTargetModel, PurgedTimeSeriesSplit, metrics
├── registry.py              # 20 target-horizon registry, data loading
├── pipeline.py              # Pipeline orchestrator (1009 lines)
├── volatility.py            # VolatilityCatBoost, VolatilityLightGBM, VolatilityRidge
├── run_volatility.py        # CLI for volatility training
├── core/                    # Walk-forward window management
│   ├── __init__.py          # Exports with backward compatibility aliases
│   ├── window.py            # Single-layer walk-forward (WindowSlice)
│   └── aligned_dual_window.py  # Dual-layer: Expanding L1 + Sliding L2 (591 lines)
└── helpers/                 # Layer 1 helper models
    ├── __init__.py          # Package exports (~58 features total)
    ├── base.py              # BaseHelper, HelperConfig, HelperOutput
    ├── ensemble.py          # HelperEnsemble, EnsembleOutput
    ├── icir_config.py       # ICIR configuration (ICIRConfig, presets)
    ├── icir_selection.py    # ICIR feature selection algorithms
    ├── helper_selection.py  # get_helpers_for_target, get_incremental_helpers
    ├── hmm.py               # HMMHelper, MarketRegimeHMM, VolatilityRegimeHMM
    ├── garch.py             # GARCHHelper, GARCHConfig
    ├── isolation_forest.py  # IsolationForestHelper, IsolationForestConfig
    ├── kalman.py            # KalmanHelper
    └── cusum.py             # CUSUMHelper, CUSUMConfig

scripts/analysis/optimizers/
├── helper_optimizer.py      # Grid search for helper configs (682 lines)
│   └── run_helper_optimization()  # Main entry point
└── ... (other optimizers)

data/
├── datasets/                # Optimized datasets (20 total)
│   └── {target}_{horizon}bar.parquet
├── analysis/results/
│   ├── optimal_helper_configs.json  # Best configs per target-horizon
│   └── helper_optimization_summary.csv
├── models/                  # Saved model files
│   └── {target}_{horizon}bar_{model}.joblib
└── target_model_results/    # CV results and metrics
    └── {target}_{horizon}bar_results.csv
```

---

## Optimization Summary

All 20 datasets optimized with per-target pipelines:

| Target | IC Improvement Range | Pipeline Applied |
|--------|---------------------|------------------|
| **volatility** | +0.2% to +0.3% | Winsorize only |
| **direction** | +5.7% to +26.0% | Winsorize + ZScore + Interactions |
| **returns** | +5.3% to +22.6% | Winsorize + ZScore + Interactions |
| **vol_regime** | +4.1% to +4.9% | Winsorize + Interactions |
| **trend_regime** | +3.9% to +10.1% | Winsorize + Interactions |

**Key finding**: Volatility target benefits minimally from feature engineering — suggests the signal is already captured in raw features.

---

## Implementation Status

| Component | Status | Notes |
|-----------|--------|-------|
| **Target Registry** | ✅ Complete | 20 target-horizon specs, `load_aligned_data()` |
| **Aligned Dual Window** | ✅ Complete | Expanding L1 + Sliding L2 architecture |
| **Helper Models (L1)** | ✅ Complete | 6 helpers, 58 features |
| **ICIR Feature Selection** | ✅ Complete | 32% avg feature reduction |
| **Helper Optimization** | ✅ Complete | Grid search with leak-free validation |
| **Pipeline Orchestrator** | ✅ Complete | 1009 lines, full walk-forward |
| **Volatility Models** | ✅ Complete | CatBoost, LightGBM, Ridge |
| **Direction Models** | ⬜ TODO | Reuse architecture |
| **Returns Models** | ⬜ TODO | Reuse architecture |
| **Vol Regime Models** | ⬜ TODO | Multiclass adaptation |
| **Trend Regime Models** | ⬜ TODO | Binary classification |
| **Ensemble Layer** | ⬜ TODO | Cross-target aggregation |
| **Position Sizing** | ⬜ TODO | V3 pipeline integration |

---

## Key Classes

### Registry (`registry.py`)

```python
from scripts.target_models.registry import (
    TARGET_REGISTRY,       # Dict of 20 TargetSpec objects
    ALL_TARGETS,           # ("volatility", "returns", "direction", "vol_regime", "trend_regime")
    ALL_HORIZONS,          # (1, 3, 6, 12)
    get_target_spec,       # Get TargetSpec for target+horizon
    load_target_data,      # Load X, y for target+horizon
    load_aligned_data,     # Load timestamp-aligned data for all targets
)
```

### Aligned Dual Window (`core/aligned_dual_window.py`)

```python
from scripts.target_models.core import (
    # New names (preferred)
    AlignedDualConfig,     # Combined L1+L2 configuration
    AlignedDualEngine,     # Walk-forward iterator
    AlignedDualWindow,     # Window at specific prediction timestamp
    ExpandingL1Config,     # L1 configuration
    SlidingL2Config,       # L2 configuration
    create_aligned_config, # Factory function

    # Backward compatibility aliases
    DualLayerConfig,       # → AlignedDualConfig
    DualLayerEngine,       # → AlignedDualEngine
    DualLayerWindow,       # → AlignedDualWindow
    create_dual_config,    # → create_aligned_config
)
```

### Helpers (`helpers/`)

```python
from scripts.target_models.helpers import (
    create_helper_ensemble,  # Create all 6 helpers for target
    HelperEnsemble,          # Manages all helpers
    EnsembleOutput,          # Output container
    
    # Individual helpers
    HMMHelper,               # 4-state and 5-state HMM
    GARCHHelper,             # GARCH(1,1) volatility
    IsolationForestHelper,   # Multi-level anomaly detection
    KalmanHelper,            # 3D state estimation
    CUSUMHelper,             # Change point detection
    
    # ICIR feature selection
    ICIRConfig,              # Configuration for ICIR selection
    DEFAULT_ICIR_CONFIG,     # Balanced (ICIR=0.30, corr=0.90)
    ICIR_CONFIG_STRICT,      # Fewer features (ICIR=0.50, corr=0.80)
    ICIR_CONFIG_LENIENT,     # More features (ICIR=0.20, corr=0.95)
    ICIR_CONFIG_DISABLED,    # Legacy IC-only mode
    select_features_full_pipeline,  # Full ICIR selection algorithm
)
```

---

## Next Steps

1. ✅ ~~Build dual-layer architecture~~ — Expanding L1 + Sliding L2 implemented
2. ✅ ~~Implement helper models~~ — 6 helpers generating 58 features
3. ✅ ~~Helper optimization~~ — Grid search with leak-free validation
4. ⬜ Implement remaining target models — direction, returns, vol_regime, trend_regime
5. ⬜ Build ensemble aggregation — Cross-target prediction combination
6. ⬜ Position sizing layer — V3 pipeline (gate → ratio → alignment → vol adjust)
7. ⬜ Walk-forward backtesting — Full production validation

---

*Last updated: January 2025*

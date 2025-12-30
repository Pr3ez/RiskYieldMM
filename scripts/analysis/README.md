# RiskYieldMM Analysis Package

Modular analysis tools for walk-forward position prediction on perpetual futures.

## Quick Start

```bash
# Run complete analysis pipeline
python -m scripts.analysis.run all

# Or run individual steps
python -m scripts.analysis.run prepare       # Create analysis dataset
python -m scripts.analysis.run features      # Feature IC/ICIR analysis
python -m scripts.analysis.run importance    # Feature importance (MDI)
python -m scripts.analysis.run mda           # Feature importance (MDA)
python -m scripts.analysis.run cv            # Cross-validation
python -m scripts.analysis.run backtest      # Walk-forward backtest
```

## Commands

| Command | Description | Key Options |
|---------|-------------|-------------|
| `prepare` | Create `analysis_8h.parquet` with targets | — |
| `features` | IC/ICIR analysis, redundancy check | `--no-plot` |
| `importance` | LightGBM MDI (in-sample) | `--no-plot` |
| `mda` | Permutation importance (OOS) | `--n-repeats N` |
| `cv` | Cross-validation | `--purged` |
| `backtest` | Walk-forward simulation | `--iterations N`, `--no-plot` |
| `optimize` | Feature optimization pipeline | `--pipeline {default,quality,minimal}` |
| `all` | Run all steps | `--force` |

### Feature Importance: MDI vs MDA

| Method | Command | Type | Model | Best For |
|--------|---------|------|-------|----------|
| **MDI** | `importance` | In-sample | Tree-based | Quick screening |
| **MDA** | `mda` | Out-of-sample | Any | Production selection |

```bash
# MDI (fast, in-sample)
python -m scripts.analysis.run importance

# MDA (slower, more reliable)
python -m scripts.analysis.run mda --n-repeats 10
```

### Cross-Validation: Standard vs Purged

| Method | Flag | Gap Type | Academic Source |
|--------|------|----------|-----------------|
| TimeSeriesSplit | (default) | Fixed gap | sklearn |
| **PurgedKFold** | `--purged` | Purge + Embargo | Lopez de Prado AFML |

```bash
# Standard CV
python -m scripts.analysis.run cv

# Purged CV (prevents temporal leakage)
python -m scripts.analysis.run cv --purged
```

**PurgedKFold Parameters:**
- `purge_gap=21`: Max feature lookback (21 bars = 7 days at 8h)
- `embargo_gap=12`: Max target horizon (12 bars = 4 days at 8h)

### Feature Optimization Pipeline

```bash
# Run default pipeline (Winsorize → RollingZScore → Interactions)
python -m scripts.analysis.run optimize

# Run quality pipeline (all optimizers)
python -m scripts.analysis.run optimize --pipeline quality

# Run minimal pipeline (only winsorization)
python -m scripts.analysis.run optimize --pipeline minimal
```

**Available Base Feature Optimizers:**
| Optimizer | Purpose | Typical IC Change |
|-----------|---------|-------------------|
| `WinsorizeOptimizer` | Clip outliers to 1%/99% | ±0% |
| `RollingZScoreOptimizer` | Fix distribution drift | +0.5% |
| `RegimeConditioningOptimizer` | Weight by regime | ±0.7% |
| `DomainPCAOptimizer` | Reduce redundancy | +10% |
| `InteractionOptimizer` | Cross-domain features | +9% |
| `ExpandingRankOptimizer` | Expanding percentile rank | +2-5% |
| `ExpandingZScoreOptimizer` | Expanding standardization | +1-3% |
| `LogTransformOptimizer` | Log transform for skewed features | +0.5-1% |

**Helper Model Optimizer:**
| Optimizer | Purpose | Location |
|-----------|---------|----------|
| `helper_optimizer.py` | Grid search for Layer 1 helper configs | `scripts/analysis/optimizers/` |

The helper optimizer finds optimal configurations for the 6 helper models (HMM4, HMM5, GARCH, IF, Kalman, CUSUM) with **leak-free validation** using only L1 data.

**ICIR Feature Selection (Layer 1 → Layer 2):**

After helpers generate ~58 features, the **ICIR system** selects stable, non-redundant features:

| Config | ICIR Threshold | Corr Threshold | Avg Selected | Use Case |
|--------|---------------|----------------|--------------|----------|
| `DEFAULT_ICIR_CONFIG` | 0.30 | 0.90 | 27 features | Balanced |
| `ICIR_CONFIG_STRICT` | 0.50 | 0.80 | ~20 features | High stability |
| `ICIR_CONFIG_LENIENT` | 0.20 | 0.95 | ~35 features | More signal |
| `ICIR_CONFIG_DISABLED` | — | — | ~40 features | Legacy IC |

```python
from scripts.target_models.helpers import (
    ICIRConfig, DEFAULT_ICIR_CONFIG, ICIR_CONFIG_DISABLED,
    create_helper_ensemble,
)

# Default ICIR (recommended)
ensemble = create_helper_ensemble('volatility', 6)

# Disable ICIR for legacy IC behavior
ensemble = create_helper_ensemble('volatility', 6, icir_config=ICIR_CONFIG_DISABLED)

# Custom config
config = ICIRConfig(icir_threshold=0.4, correlation_threshold=0.85)
ensemble = create_helper_ensemble('volatility', 6, icir_config=config)
```

**Usage from Python:**
```python
from scripts.analysis.optimizers import (
    OptimizationPipeline,
    WinsorizeOptimizer,
    RollingZScoreOptimizer,
)

pipeline = OptimizationPipeline([
    WinsorizeOptimizer(lower=0.01, upper=0.99),
    RollingZScoreOptimizer(window=252),
])
X_optimized = pipeline.fit_transform(X, y)
pipeline.print_report()
```

## Package Structure

```
scripts/analysis/
├── __init__.py     # Package exports
├── config.py       # Centralized configuration
├── data.py         # Data loading, target generation
├── features.py     # IC/ICIR, importance, domain classification
├── models.py       # CatBoost, LightGBM, PurgedKFold
├── backtest.py     # Walk-forward simulation
├── viz.py          # Plotting utilities
├── run.py          # CLI entry point (1406 lines)
└── optimizers/     # Feature and helper optimization
    ├── __init__.py         # Exports all optimizers
    ├── base.py             # BaseOptimizer, OptimizerMetrics
    ├── rolling_zscore.py   # Distribution drift fix
    ├── regime_conditioning.py  # Regime-based weighting
    ├── domain_pca.py       # Redundancy reduction
    ├── interactions.py     # Cross-domain features
    ├── winsorize.py        # Outlier handling
    ├── pipeline.py         # Optimizer chaining
    ├── expanding_rank.py   # Expanding percentile rank (leak-free)
    ├── expanding_zscore.py # Expanding standardization (leak-free)
    ├── log_transform.py    # Log transform for skewed features
    └── helper_optimizer.py # Grid search for Layer 1 helpers (682 lines)

scripts/target_models/helpers/
├── icir_config.py    # ICIRConfig dataclass, preset configs
└── icir_selection.py # ICIR computation, correlation filter
```

## Modules

### `config.py`
Centralized configuration constants.

```python
from scripts.analysis import config

# Paths
config.FEATURES_FILE      # data/features_8h.parquet
config.RAW_FILE           # data/merged_8h_raw.parquet
config.ANALYSIS_FILE      # data/analysis_8h.parquet

# Temporal parameters
config.MAX_LOOKBACK_BARS  # 21 (max feature window)
config.MAX_HORIZON_BARS   # 12 (max target horizon)

# Model config
config.MODEL_CONFIG.n_cv_splits
config.MODEL_CONFIG.cb_iterations
```

### `data.py`
Data loading and target generation.

```python
from scripts.analysis import data

# Load analysis dataset
df = data.load_analysis_data()  # Returns pandas DataFrame

# Get feature/target columns
features = data.get_feature_columns(df)  # 166 features
targets = data.get_target_columns()       # y_direction, y_volatility, etc.

# Create dataset from scratch
data.create_analysis_dataset()
```

**Targets Generated:**
| Target | Type | Description |
|--------|------|-------------|
| `y_direction` | Int8 | Binary (1=up, 0=down) |
| `y_volatility` | Float64 | \|forward_return_1\| |
| `y_forward_return_{1,3,6,12}` | Float64 | Multi-horizon returns |
| `y_vol_regime` | Int8 | LOW/MED/HIGH (0/1/2) |
| `y_trend_regime` | Int8 | SMA crossover |

### `features.py`
Feature analysis utilities.

```python
from scripts.analysis import features

# IC/ICIR analysis
ic_results = features.compute_ic_analysis(df, feature_cols, "y_forward_return_1")

# Domain classification
domains = features.classify_all_features(feature_cols)
# {'Volatility': [...], 'Momentum': [...], 'Funding': [...], ...}

# Redundancy detection
redundant = features.find_redundant_features(df, feature_cols)

# Feature importance (MDI)
importances = features.compute_lgb_importance(X, y)

# Feature importance (MDA - permutation)
mda = features.compute_permutation_importance(model, X_val, y_val, n_repeats=10)
```

### `models.py`
Model training and cross-validation.

```python
from scripts.analysis import models

# Direction models
dir_results = models.run_direction_cv(X, y)
dir_results = models.run_direction_cv(X, y, use_purged=True)  # With PurgedKFold

# Volatility model
vol_result = models.run_volatility_cv(X, y, use_purged=True)

# Direct training
result = models.train_direction_ensemble(X_train, y_train, X_val, y_val)

# PurgedKFold (custom CV splitter)
from scripts.analysis.models import PurgedKFold
cv = PurgedKFold(n_splits=5, purge_gap=21, embargo_gap=12)
for train_idx, test_idx in cv.split(X):
    # No overlap, proper temporal gaps
    pass
```

### `backtest.py`
Walk-forward backtesting.

```python
from scripts.analysis import backtest

# Run walk-forward
results_df, metrics = backtest.run_walk_forward(df, max_iterations=500)

# Results include: timestamp, prediction, position, pnl, etc.
```

### `viz.py`
Visualization utilities.

```python
from scripts.analysis import viz

viz.plot_ic_analysis(ic_results)
viz.plot_feature_importance(importances)
viz.plot_backtest_results(results_df)
viz.plot_pnl_analysis(results_df)
```

## Output Files

All outputs saved to `data/analysis/`:

```
data/analysis/
├── analysis_8h.parquet          # Combined features + targets
├── results/
│   ├── ic_analysis.csv          # Feature IC/ICIR results
│   ├── feature_importance.csv   # MDI importance
│   ├── mda_importance.csv       # MDA importance
│   ├── cv_results.csv           # CV fold results
│   ├── backtest_results.csv     # Walk-forward results
│   ├── optimal_helper_configs.json  # Best helper configs per target-horizon
│   └── helper_optimization_summary.csv  # Detailed optimization results
└── plots/
    └── *.png                    # Generated visualizations
```

---

## Helper Model Optimization

The `helper_optimizer.py` optimizes Layer 1 helper configs **separately for each of the 20 target-horizons**.

Each target-horizon gets its own optimal helper configurations because:
- `volatility_6bar` benefits from different HMM states than `direction_1bar`
- Optimal Kalman noise settings vary by target
- Helper IC is measured against the SPECIFIC target being predicted

### Running Helper Optimization

```bash
# Optimize helpers for ONE target-horizon
python -c "
from scripts.analysis.optimizers.helper_optimizer import run_helper_optimization
run_helper_optimization(targets=['volatility'], horizons=[6])
"

# Optimize helpers for ALL 20 target-horizons
python -c "
from scripts.analysis.optimizers.helper_optimizer import run_helper_optimization
run_helper_optimization()  # All 5 targets × 4 horizons = 20 optimizations
"
```

### Helpers Optimized

| Helper | Config Parameters | Typical Configs Tested |
|--------|------------------|------------------------|
| **HMM4** | n_states, covariance_type, n_iter | 6 configs |
| **HMM5** | n_states, covariance_type, n_iter | 6 configs |
| **GARCH** | p, q, mean | 3 configs |
| **IF** | contamination_extreme/moderate/mild, n_estimators | 5 configs |
| **Kalman** | process_noise, measurement_noise | 5 configs |
| **CUSUM** | threshold, drift | 4 configs |

### Leak-Free Validation

Helper optimization uses **ONLY L1 data** to prevent look-ahead bias:

```
Architecture:
[0 ─────────── L2_start][L2_train][purge][L2_cal][L2_val][pred]
│<─── L1 expanding ───>│<────── L2 sliding ─────────────>│

L1.train (80%): Fit helpers
L1.val (20%): Compute IC for config selection
L2 data: NEVER seen during optimization
```

### Output Files (Per Target-Horizon)

Results stored in `data/analysis/results/`:

**`optimal_helper_configs.json`** — Best configs for each target-horizon:
```json
{
  "volatility_1bar": {"helpers": {"hmm4": {...}, "kalman": {...}, ...}},
  "volatility_3bar": {"helpers": {...}},
  ...
  "trend_regime_12bar": {"helpers": {...}}
}
```

**`helper_optimization_summary.csv`** — Full results table

| Helper | Avg IC Improvement | Notes |
|--------|-------------------|-------|
| **HMM4** | +48.6% | Market regime detection |
| **Kalman** | +26.8% | State estimation smoothing |
| **HMM5** | +23.1% | Volatility regime detection |
| **IF** | +18.2% | Anomaly detection |
| **CUSUM** | +16.9% | Change point detection |
| **GARCH** | +0.0% | Default (1,1) always best |

### Usage from Python

```python
from scripts.analysis.optimizers.helper_optimizer import (
    run_helper_optimization,
    optimize_single_helper,
    create_helper_with_config,
    load_optimal_configs,
    HELPER_CONFIG_SEARCH_SPACE,
)

# Run full optimization
results = run_helper_optimization(
    targets=["volatility", "direction"],
    horizons=[6, 12],
    output_dir="data/analysis/results"
)

# Load saved configs
configs = load_optimal_configs("data/analysis/results/optimal_helper_configs.json")
print(configs["volatility_6bar"]["helpers"]["hmm4"]["config"])
```

---

## Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Test coverage
python -m pytest tests/ -v --tb=short
```

**Test Files:**
- `tests/test_features.py` — 8 tests for MDA
- `tests/test_models.py` — 11 tests for PurgedKFold

## Academic References

| Method | Source |
|--------|--------|
| IC/ICIR | Grinold & Kahn (1999) |
| FDR Correction | Benjamini & Hochberg (1995) |
| MDI | Breiman (2001) |
| MDA | Lopez de Prado AFML Ch.8 |
| Purged K-Fold | Lopez de Prado AFML Ch.7 |
| CatBoost | Prokhorenkova et al. (2018) |
| Calibration | Zadrozny & Elkan (2002) |

## Usage Examples

### Full Analysis Pipeline

```python
from scripts.analysis import config, data, features, models

# 1. Load data
df = data.load_analysis_data()
feature_cols = data.get_feature_columns(df)

# 2. Feature analysis
ic_results = features.compute_ic_analysis(df, feature_cols, "y_forward_return_1")
top_features = ic_results.head(20)["feature"].tolist()

# 3. Prepare for modeling
mask = df["y_direction"].notna()
X = df.loc[mask, feature_cols]
y = df.loc[mask, "y_direction"]

# 4. Cross-validation with purging
results = models.run_direction_cv(X, y, use_purged=True)
for model_name, cv_result in results.items():
    print(f"{model_name}: AUC={cv_result.mean_auc:.4f}")
```

### Feature Selection with MDA

```python
import lightgbm as lgb
from sklearn.model_selection import train_test_split
from scripts.analysis import data, features

# Load and split
df = data.load_analysis_data()
feature_cols = data.get_feature_columns(df)
X = df[feature_cols]
y = df["y_direction"]
X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.2, shuffle=False)

# Train model
model = lgb.LGBMClassifier(n_estimators=100, random_state=42)
model.fit(X_train, y_train)

# Get MDA importance
mda = features.compute_permutation_importance(model, X_val, y_val, n_repeats=10)
print(mda.sort_values("importance_mean", ascending=False).head(20))
```

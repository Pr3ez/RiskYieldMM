# Part 2: Libraries and Dependencies

> **Document Version**: 1.0  
> **Last Updated**: 2025-12-22  
> **Module**: `scripts/analysis/`

---

## Overview

This document justifies every library choice in the analysis system, with references to academic literature and practical considerations for time-series financial data.

---

## Core Data Libraries

### Polars

**Version**: 0.20+  
**Purpose**: Primary data loading and manipulation

```python
import polars as pl
df = pl.read_parquet("data/analysis_8h.parquet")
```

| Aspect | Details |
|--------|---------|
| **Why Chosen** | 10-100x faster than Pandas for large datasets |
| **Time-Series Suitability** | Lazy evaluation, efficient window functions |
| **Alternative Considered** | Pandas (slower), Dask (overkill for our data size) |
| **Academic Validation** | Industry standard, used in production ML systems |

**Key Operations Used**:
- `read_parquet()` — Efficient columnar data loading
- `filter()` — Row selection without copying
- `select()` — Column selection
- `with_columns()` — Feature engineering

**Limitation**: Some scipy functions require Pandas conversion.

---

### Pandas

**Version**: 2.0+  
**Purpose**: Compatibility layer, some scipy operations

```python
import pandas as pd
df_pd = df.to_pandas()  # Convert when needed for scipy
```

| Aspect | Details |
|--------|---------|
| **Why Kept** | scipy.stats requires Pandas/NumPy inputs |
| **Usage** | Limited to statistical computations |
| **Minimization Strategy** | Convert only when necessary, keep Polars as primary |

---

### NumPy

**Version**: 1.24+  
**Purpose**: Numerical operations, array manipulation

| Aspect | Details |
|--------|---------|
| **Why Chosen** | Universal numerical backend |
| **Academic Validation** | Standard in all ML/scientific Python |
| **Key Operations** | `np.clip()`, `np.sign()`, array math |

---

## Machine Learning Libraries

### CatBoost

**Version**: 1.2+  
**Purpose**: Direction classification, volatility regression

```python
from catboost import CatBoostClassifier, CatBoostRegressor
```

| Aspect | Details |
|--------|---------|
| **Why Chosen** | Ordered boosting prevents target leakage |
| **Academic Citation** | Prokhorenkova et al., NeurIPS 2018 |
| **Paper**: | "CatBoost: unbiased boosting with categorical features" |
| **Key Innovation** | Permutation-driven training prevents prediction shift |

**Configuration Used**:
```python
CatBoostClassifier(
    iterations=500,
    depth=6,
    learning_rate=0.03,
    l2_leaf_reg=3.0,
    early_stopping_rounds=50,
)
```

**Time-Series Consideration**: Ordered boosting naturally respects temporal ordering.

---

### LightGBM

**Version**: 4.0+  
**Purpose**: Direction classification (ensemble member)

```python
from lightgbm import LGBMClassifier
```

| Aspect | Details |
|--------|---------|
| **Why Chosen** | Fast training, efficient memory usage |
| **Academic Citation** | Ke et al., NeurIPS 2017 |
| **Paper** | "LightGBM: A Highly Efficient Gradient Boosting Decision Tree" |
| **Ensemble Rationale** | Different bias/variance tradeoffs vs CatBoost |

**Configuration Used**:
```python
LGBMClassifier(
    n_estimators=500,
    max_depth=6,
    learning_rate=0.03,
    reg_lambda=1.0,
)
```

**Why Ensemble?**: CatBoost + LightGBM ensemble reduces variance through model diversity.

---

### scikit-learn

**Version**: 1.3+  
**Purpose**: Cross-validation, Ridge regression, calibration, metrics

```python
from sklearn.model_selection import TimeSeriesSplit
from sklearn.linear_model import Ridge
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import roc_auc_score, accuracy_score, mean_squared_error
```

| Component | Purpose | Academic Basis |
|-----------|---------|----------------|
| `TimeSeriesSplit` | Temporal CV without leakage | Standard practice |
| `Ridge` | Regularized returns regression | Tikhonov regularization |
| `IsotonicRegression` | Probability calibration | Zadrozny & Elkan (2002) |
| `roc_auc_score` | Model evaluation | Standard ML metrics |

**Time-Series CV Configuration**:
```python
TimeSeriesSplit(n_splits=5, gap=50)  # Gap prevents label overlap
```

**Gap Parameter Justification**: 
- Our features use 21-bar rolling windows
- Gap of 50 bars ensures no feature/target overlap
- Based on Lopez de Prado's purged CV concept (AFML Chapter 7)

---

## Statistical Libraries

### SciPy

**Version**: 1.11+  
**Purpose**: Statistical tests, correlation analysis

```python
from scipy import stats
```

| Function | Purpose | Academic Basis |
|----------|---------|----------------|
| `stats.spearmanr()` | Information Coefficient | Grinold & Kahn (1999) |
| `stats.pearsonr()` | Linear correlation | Standard statistics |

**IC Calculation**:
```python
ic, pvalue = stats.spearmanr(feature_ranks, return_ranks)
```

**Why Spearman (not Pearson)?**
- Robust to outliers common in financial returns
- Captures monotonic relationships, not just linear
- Standard in quantitative finance (Grinold & Kahn)

---

## Visualization Libraries

### Matplotlib

**Version**: 3.7+  
**Purpose**: All plotting and visualization

```python
import matplotlib.pyplot as plt
```

| Aspect | Details |
|--------|---------|
| **Why Chosen** | Full control, publication-quality figures |
| **Alternative Considered** | Plotly (interactive but heavier) |
| **Style** | Clean, minimal, suitable for reports |

**Standard Plot Types**:
- IC distribution histograms
- Feature importance bar charts
- Equity curves
- Walk-forward performance

---

## Library Validation Against Research

| Method | Our Library | Academic Standard | Match? |
|--------|-------------|-------------------|--------|
| IC/ICIR | scipy.stats.spearmanr | Grinold & Kahn | ✅ Yes |
| FDR Correction | Custom B-H implementation | Benjamini-Hochberg (1995) | ✅ Yes |
| Gradient Boosting | CatBoost | Prokhorenkova NeurIPS 2018 | ✅ Yes |
| Time-Series CV | PurgedKFold with purge/embargo | Lopez de Prado AFML Ch.7 | ✅ Yes |
| Probability Calibration | sklearn IsotonicRegression | Zadrozny & Elkan (2002) | ✅ Yes |
| Feature Importance (MDI) | LightGBM built-in | Breiman (2001) | ✅ Yes |
| Feature Importance (MDA) | sklearn permutation_importance | Lopez de Prado AFML Ch.8 | ✅ Yes |

### Implementation Notes

1. **PurgedKFold**: Custom implementation with `purge_gap` (21 bars) and `embargo_gap` (12 bars)
   - Prevents look-ahead bias from overlapping feature windows and target horizons
   - CLI: `python -m scripts.analysis.run cv --purged`

2. **MDA (Permutation Importance)**: Out-of-sample, model-agnostic importance
   - More reliable than MDI for production feature selection
   - CLI: `python -m scripts.analysis.run mda --n-repeats 10`

---

## Dependencies Summary

```toml
# pyproject.toml (relevant sections)
[project.dependencies]
polars = ">=0.20"
pandas = ">=2.0"
numpy = ">=1.24"
catboost = ">=1.2"
lightgbm = ">=4.0"
scikit-learn = ">=1.3"
scipy = ">=1.11"
matplotlib = ">=3.7"
```

---

## Import Structure

```python
# Standard pattern in our modules
import numpy as np
import pandas as pd
import polars as pl
from scipy import stats
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import roc_auc_score

# ML libraries with availability checks
try:
    from catboost import CatBoostClassifier
    HAS_CATBOOST = True
except ImportError:
    HAS_CATBOOST = False
```

**Graceful Degradation**: Modules check library availability and skip functionality if not installed.

---

## Performance Considerations

| Library | Memory Efficiency | Speed | Notes |
|---------|------------------|-------|-------|
| Polars | Excellent | Excellent | Primary choice |
| CatBoost | Good | Good | GPU available if needed |
| LightGBM | Excellent | Excellent | Histogram-based |
| scipy | Good | Good | JIT-compiled operations |

**Data Size Context**: Our analysis_8h.parquet is ~6MB (5,438 rows × 178 cols) — all libraries handle this efficiently.

---

## Academic References

1. **Prokhorenkova, L. et al.** (2018). "CatBoost: unbiased boosting with categorical features." *NeurIPS 2018*.

2. **Ke, G. et al.** (2017). "LightGBM: A Highly Efficient Gradient Boosting Decision Tree." *NeurIPS 2017*.

3. **Grinold, R. & Kahn, R.** (1999). *Active Portfolio Management*. McGraw-Hill.

4. **Benjamini, Y. & Hochberg, Y.** (1995). "Controlling the false discovery rate." *Journal of the Royal Statistical Society B*, 57(1):289-300.

5. **Lopez de Prado, M.** (2018). *Advances in Financial Machine Learning*. Wiley.

6. **Zadrozny, B. & Elkan, C.** (2002). "Transforming classifier scores into accurate multiclass probability estimates." *KDD 2002*.

---

## Feature Optimization Library

### Optimizer Module

**Location**: `scripts/analysis/optimizers/`  
**Purpose**: Signal quality improvement through systematic feature transformation

The optimizer module provides a pipeline-based approach to feature engineering, following sklearn conventions for consistency.

#### Available Optimizers

| Optimizer | Purpose | Key Parameters |
|-----------|---------|----------------|
| `RollingZScoreOptimizer` | Fix distribution drift | `window=252` |
| `WinsorizeOptimizer` | Handle outliers | `lower=0.01, upper=0.99` |
| `RegimeConditioningOptimizer` | Weight features by regime | `regime_feature`, `output_mode` |
| `DomainPCAOptimizer` | Reduce redundancy via PCA | `variance_threshold=0.90` |
| `InteractionOptimizer` | Cross-domain interactions | `top_k=3, n_interactions=10` |

#### Base Class Interface

```python
from scripts.analysis.optimizers import BaseOptimizer, OptimizerMetrics

class CustomOptimizer(BaseOptimizer):
    name = "CustomOptimizer"
    
    def fit(self, X: pd.DataFrame, y: pd.Series | None = None) -> "CustomOptimizer":
        # Learn parameters from data
        self.is_fitted = True
        return self
    
    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        # Apply transformation
        return X_transformed
```

#### Pipeline Usage

```python
from scripts.analysis.optimizers import (
    OptimizationPipeline,
    WinsorizeOptimizer,
    RollingZScoreOptimizer,
    InteractionOptimizer,
)

pipeline = OptimizationPipeline([
    WinsorizeOptimizer(lower=0.01, upper=0.99),
    RollingZScoreOptimizer(window=252),
    InteractionOptimizer(top_k=3, n_interactions=10),
])

# Fit and transform
X_optimized = pipeline.fit_transform(X, y)

# Get metrics for each step
metrics_df = pipeline.get_metrics_df()
print(metrics_df)

# Compare baseline vs optimized
comparison = pipeline.compare_performance(X, y)
print(f"IC Improvement: {comparison['ic_improvement_pct']:.1f}%")
```

#### OptimizerMetrics Dataclass

Each optimizer tracks these metrics after `evaluate()`:

| Field | Description |
|-------|-------------|
| `ic_before` | Mean absolute IC before transformation |
| `ic_after` | Mean absolute IC after transformation |
| `ic_improvement` | Relative improvement |
| `n_features_in` | Input feature count |
| `n_features_out` | Output feature count |
| `nan_pct_before/after` | Missing data percentage |
| `outlier_pct_before/after` | Outlier percentage (3×IQR) |
| `fit_time_ms` | Fitting time in milliseconds |
| `transform_time_ms` | Transform time in milliseconds |

#### CLI Usage

```bash
# Run default pipeline
python -m scripts.analysis.run optimize

# Run specific pipeline preset
python -m scripts.analysis.run optimize --pipeline quality
python -m scripts.analysis.run optimize --pipeline minimal
```

#### Test Coverage

34 unit tests in `tests/test_optimizers.py`:
- `TestOptimizerMetrics` — 3 tests (creation, serialization)
- `TestRollingZScoreOptimizer` — 5 tests (fit, transform, evaluate)
- `TestWinsorizeOptimizer` — 4 tests (bounds, clipping)
- `TestRegimeConditioningOptimizer` — 3 tests (regime detection)
- `TestDomainPCAOptimizer` — 3 tests (domain reduction)
- `TestInteractionOptimizer` — 3 tests (feature generation)
- `TestOptimizationPipeline` — 7 tests (chaining, metrics)
- `TestIntegration` — 2 tests (end-to-end)
- `TestEdgeCases` — 4 tests (empty, NaN, constant handling)

#### Research Basis

| Optimizer | Research Basis |
|-----------|----------------|
| Rolling Z-Score | Volatility regime changes create non-stationarity; rolling normalization adapts |
| Winsorization | Funding and mark price features have 10-23% outliers (3×IQR) |
| Regime Conditioning | Lopez de Prado AFML: Momentum features flip sign between trending/reverting |
| Domain PCA | 148 redundant pairs (r>0.9) identified; Oscillator domain has 74% PC1 |
| Interactions | momAtr_3 × volumeRoc_3 = IC +0.055 (better than either alone) |


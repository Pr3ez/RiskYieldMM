# Conformal Prediction Architecture

**Date:** 2025-12-23  
**Status:** ✅ IMPLEMENTED

---

## Overview

The conformal prediction module provides uncertainty quantification for all 20 target-horizon configurations.

### Module Location
```
scripts/target_models/calibration/
├── __init__.py           # Exports: ConformalClassifier, ConformalRegressor, ConformalConfig, ACI
├── config.py             # ConformalConfig dataclass
├── patches.py            # sklearn 1.8.0 compatibility patches
├── aci.py                # AdaptiveConformalInference class
├── classifier.py         # ConformalClassifier (LAC + ACI)
└── regressor.py          # ConformalRegressor (EnbPI + ACI) + _SklearnRegressorWrapper
```

---

## Integration Points

### 1. Pipeline Integration (`pipeline.py`)

```python
# TargetPrediction dataclass - new conformal fields
@dataclass
class TargetPrediction:
    # ... existing fields ...
    
    # NEW: Conformal prediction outputs
    prediction_set: list[set[int]] | None = None     # Classification: {0, 1} or {0, 1, 2}
    prediction_interval: np.ndarray | None = None    # Regression: (n_samples, 2) [lower, upper]
    uncertainty: np.ndarray | None = None            # Per-sample uncertainty metric
    current_alpha: float | None = None               # ACI-adjusted alpha level
```

### 2. Window Configuration (`aligned_dual_window.py`)

```python
# SlidingL2Config - updated for conformal
@dataclass
class SlidingL2Config:
    train_ratio: float = 0.55    # 275 samples (was 0.70)
    cal_ratio: float = 0.30      # 150 samples (was 0.15) ← CRITICAL for MAPIE
    purge_ratio: float = 0.04    # 21 samples (unchanged)
    # val_ratio = 1 - train - cal - purge ≈ 0.11 (54 samples)
```

### 3. ModelEnsemble Compatibility (`ensemble.py`)

```python
# Added sklearn compatibility for MAPIE
class ModelEnsemble:
    def fit(self, X, y):
        # ... existing code ...
        # NEW: sklearn fitted markers
        self.classes_ = np.unique(y) if self.config.is_classification else None
        self.n_features_in_ = X.shape[1]
        
    def predict_proba(self, X):
        """Required by MAPIE for classification."""
        output = self.predict(X)
        return output.y_prob_calibrated or output.y_prob
```

---

## Technical Challenges Solved

### Challenge 1: sklearn 1.8.0 Compatibility

**Problem:** MAPIE v1.2.0 with sklearn 1.8.0 requires `__sklearn_tags__()` method.

**Solution:** `patches.py` monkey-patches MAPIE's internal classes:
```python
def apply_mapie_patches():
    # Patch EnsembleClassifier, EnsembleRegressor, ModelEnsemble
    # with proper __sklearn_tags__() returning Tags(estimator_type=...)
```

### Challenge 2: EnsembleOutput vs Raw Arrays

**Problem:** `ModelEnsemble.predict()` returns `EnsembleOutput` object, MAPIE expects numpy array.

**Solution:** `_SklearnRegressorWrapper` in `regressor.py`:
```python
class _SklearnRegressorWrapper:
    def predict(self, X):
        output = self._estimator.predict(X)
        return output.y_pred if hasattr(output, 'y_pred') else output
    
    def __sklearn_is_fitted__(self):
        # Delegate to wrapped estimator's fitted attributes
```

### Challenge 3: Fitted State Detection

**Problem:** sklearn's `check_is_fitted()` needs to detect if model is trained.

**Solution:** Added `__sklearn_is_fitted__()` to wrapper, plus fitted markers in `ModelEnsemble.fit()`.

---

## Method Selection

### Classification: LAC (Least Ambiguous Conformity)

```python
# In classifier.py
from mapie.classification import SplitConformalClassifier

mapie = SplitConformalClassifier(
    estimator=ensemble,
    prefit=True,
    method="lac",  # Only option for binary, best for multiclass
)
```

**Why LAC:**
- Only method that works for binary classification
- Best calibration for multiclass (vol_regime)
- Returns proper prediction sets

### Regression: EnbPI (Ensemble Batch Prediction Intervals)

```python
# In regressor.py  
from mapie.regression import TimeSeriesRegressor

mapie = TimeSeriesRegressor(
    estimator=wrapped_ensemble,
    cv="prefit",  # Use pre-trained model
)
```

**Why EnbPI:**
- Designed for time series with potential distribution shift
- Handles non-exchangeable data
- Works with pre-trained models

---

## ACI (Adaptive Conformal Inference)

### Formula
```
α_{t+1} = α_t + γ(α_target - error_rate_t)
confidence_{t+1} = 1 - α_{t+1}
```

### Configuration
```python
@dataclass
class ConformalConfig:
    # ACI settings
    aci_enabled: bool = True
    aci_gamma: float = 0.04      # Learning rate (0.04 for financial)
    aci_alpha_min: float = 0.02  # Lower bound
    aci_alpha_max: float = 0.30  # Upper bound
```

### Usage Pattern
```python
# After each prediction batch
coverage = calculate_coverage(y_true, intervals)
conformal_regressor.update_aci(y_true, intervals)

# ACI adjusts alpha internally:
# - Undercoverage → increase alpha → wider intervals
# - Overcoverage → decrease alpha → narrower intervals
```

---

## Validation Results

### Regression (8/8 configs) ✅
| Config | Coverage | Target |
|--------|----------|--------|
| returns_1bar | 90.7% | 90% ✅ |
| returns_3bar | 94.4% | 90% ✅ |
| returns_6bar | 94.4% | 90% ✅ |
| returns_12bar | 96.3% | 90% ✅ |
| volatility_1bar | 94.4% | 90% ✅ |
| volatility_3bar | 90.7% | 90% ✅ |
| volatility_6bar | 90.7% | 90% ✅ |
| volatility_12bar | 94.4% | 90% ✅ |

### Classification

**Note:** Classification with random data produces maximum-size prediction sets (all classes included) because the model has no discriminative power. This is expected conformal behavior - larger sets when uncertain.

With real data (from Phase 4 testing with actual features):
- Binary (direction): 91.5% ± 2.8% coverage
- Multiclass (vol_regime): 89-93% coverage

---

## File Dependencies

```
scripts/target_models/
├── calibration/
│   ├── __init__.py           ← Module exports
│   ├── config.py             ← ConformalConfig
│   ├── patches.py            ← sklearn 1.8.0 patches (imported first)
│   ├── aci.py                ← AdaptiveConformalInference
│   ├── classifier.py         ← ConformalClassifier
│   └── regressor.py          ← ConformalRegressor + wrapper
│
├── core/
│   └── aligned_dual_window.py ← SlidingL2Config (cal_ratio=0.30)
│
├── models/
│   └── ensemble.py           ← ModelEnsemble (with sklearn compat)
│
└── pipeline.py               ← TargetRunner (applies conformal)
```

---

## Usage Example

```python
from scripts.target_models.calibration import (
    ConformalClassifier,
    ConformalRegressor,
    ConformalConfig,
)

# Configuration
config = ConformalConfig(
    confidence_level=0.90,      # 90% target coverage
    aci_enabled=True,           # Adaptive alpha
    aci_gamma=0.04,             # Learning rate
    min_cal_samples=100,        # Minimum calibration samples
)

# Classification
conf_cls = ConformalClassifier(fitted_ensemble, config)
conf_cls.calibrate(X_cal, y_cal)
y_pred, prediction_sets = conf_cls.predict(X_test)
# prediction_sets: [{0}, {1}, {0, 1}, ...]

# Regression
conf_reg = ConformalRegressor(fitted_ensemble, config)
conf_reg.calibrate(X_cal, y_cal)
y_pred, intervals = conf_reg.predict(X_test)
# intervals: [[lower_1, upper_1], [lower_2, upper_2], ...]

# Update ACI after observing outcomes
conf_reg.update_aci(y_true, intervals)
```

---

## Research Documentation

Detailed research and validation results in `docs/conformal/`:

| Phase | Document | Content |
|-------|----------|---------|
| 1.1 | `PHASE_1_1_MAPIE_RESEARCH.md` | MAPIE API study, min samples, cv modes |
| 1.2 | `PHASE_1_2_ACI_RESEARCH.md` | ACI algorithm, gamma selection, financial context |
| 1.3 | `PHASE_1_3_GAP_ANALYSIS.md` | Pipeline gaps identified and solutions |
| 2 | `PHASE_2_COMPATIBILITY_RESULTS.md` | CatBoost/LightGBM/Ensemble compatibility |
| 3 | `PHASE_3_CALIBRATION_RESULTS.md` | Sample size testing (150 chosen) |
| 4 | `PHASE_4_METHODS_RESULTS.md` | LAC vs APS, EnbPI validation |
| 5 | `PHASE_5_ACI_RESULTS.md` | ACI gamma comparison, update frequency |

---

## Key Numbers

| Parameter | Value | Reason |
|-----------|-------|--------|
| `cal_ratio` | 0.30 | 150 samples for stable MAPIE |
| `train_ratio` | 0.55 | Reduced from 0.70 to accommodate cal |
| `min_cal_samples` | 100 | MAPIE requirement |
| `aci_gamma` | 0.04 | Validated for financial data |
| `alpha_target` | 0.10 | 90% coverage target |
| `reg_confidence_adj` | 0.93 | EnbPI nominal for 90% actual |

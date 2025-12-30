# Phase 6-7: Module Implementation Results

**Date:** 2025-12-23  
**Status:** ✅ COMPLETE

---

## Summary

Phases 6-7 implemented the conformal prediction module based on research from Phases 1-5.

### Files Created

```
scripts/target_models/calibration/
├── __init__.py       # Module exports
├── config.py         # ConformalConfig dataclass (99 lines)
├── patches.py        # sklearn 1.8.0 compatibility (91 lines)
├── aci.py            # AdaptiveConformalInference (140 lines)
├── classifier.py     # ConformalClassifier (270 lines)
└── regressor.py      # ConformalRegressor (285 lines)
```

**Total:** ~885 lines of production code

---

## Module Design Decisions

### 1. Configuration (`config.py`)

```python
@dataclass
class ConformalConfig:
    # Core settings
    enabled: bool = True
    confidence_level: float = 0.90
    min_cal_samples: int = 100
    cal_ratio: float = 0.30
    
    # Classification: LAC only (works for binary)
    cls_method: Literal["lac"] = "lac"
    
    # Regression: EnbPI with adjusted confidence
    reg_method: Literal["enbpi"] = "enbpi"
    reg_confidence_adj: float = 0.93  # For ~90% actual
    
    # ACI settings
    aci_enabled: bool = True
    aci_gamma: float = 0.04
    aci_alpha_min: float = 0.02
    aci_alpha_max: float = 0.30
```

**Key Decision:** Single config class for both classification and regression, with task-specific sections.

### 2. Patches (`patches.py`)

**Problem:** sklearn 1.8.0 requires `__sklearn_tags__()` method that MAPIE v1.2.0 internal classes lack.

**Solution:**
```python
def apply_mapie_patches():
    """Monkey-patch MAPIE classes for sklearn 1.8.0."""
    
    # Patch EnsembleClassifier
    EnsembleClassifier.__sklearn_tags__ = _sklearn_tags_classifier
    
    # Patch EnsembleRegressor
    EnsembleRegressor.__sklearn_tags__ = _sklearn_tags_regressor
    
    # Patch our ModelEnsemble (dynamic based on config.is_classification)
    ModelEnsemble.__sklearn_tags__ = _model_ensemble_sklearn_tags
```

**Why Monkey-Patch:** Avoids forking MAPIE, patches applied once at import.

### 3. ACI (`aci.py`)

```python
class AdaptiveConformalInference:
    """Batch-level ACI implementation."""
    
    def __init__(self, alpha_target=0.10, gamma=0.04, 
                 alpha_min=0.02, alpha_max=0.30):
        self.alpha = alpha_target
        
    def update_batch(self, error_rate: float):
        """α_{t+1} = α_t + γ(α_target - error_rate)"""
        self.alpha = self.alpha + self.gamma * (self.alpha_target - error_rate)
        self.alpha = np.clip(self.alpha, self.alpha_min, self.alpha_max)
        
    @property
    def confidence_level(self) -> float:
        return 1 - self.alpha
```

**Key Decision:** Batch-level updates (not per-sample) for efficiency and stability.

### 4. Classifier (`classifier.py`)

```python
class ConformalClassifier:
    """LAC-based conformal classifier with ACI."""
    
    def __init__(self, estimator, config=None):
        self.estimator = estimator
        self.aci = AdaptiveConformalInference(...) if config.aci_enabled else None
        
    def calibrate(self, X_cal, y_cal):
        self.mapie = SplitConformalClassifier(
            estimator=self.estimator,
            prefit=True,
            method="lac",
        )
        self.mapie.fit(X_cal, y_cal)
        
    def predict(self, X):
        y_pred, pred_sets = self.mapie.predict(X, alpha=self.aci.alpha)
        return y_pred, self._convert_to_sets(pred_sets)
```

**Key Decision:** Returns list of Python sets (not boolean arrays) for cleaner API.

### 5. Regressor (`regressor.py`)

```python
class _SklearnRegressorWrapper:
    """Wraps ModelEnsemble for MAPIE compatibility."""
    
    def predict(self, X):
        output = self._estimator.predict(X)
        return output.y_pred if hasattr(output, 'y_pred') else output
    
    def __sklearn_is_fitted__(self):
        # Check for fitted attributes
        return len([v for v in vars(self._estimator) if v.endswith('_')]) > 0


class ConformalRegressor:
    """EnbPI-based conformal regressor with ACI."""
    
    def _wrap_estimator(self, estimator):
        if hasattr(estimator, 'predict_labels'):  # Our ModelEnsemble
            return _SklearnRegressorWrapper(estimator)
        return estimator
        
    def calibrate(self, X_cal, y_cal):
        wrapped = self._wrap_estimator(self.estimator)
        self.mapie = TimeSeriesRegressor(
            estimator=wrapped,
            cv="prefit",
        )
        self.mapie.fit(X_cal, y_cal)
```

**Key Decision:** Wrapper pattern isolates sklearn compatibility from core logic.

---

## Technical Challenges Solved

### Challenge 1: sklearn `check_is_fitted()` 

**Problem:** sklearn 1.8.0's `check_is_fitted()` requires:
1. Object has `fit()` method
2. Object has `__sklearn_tags__()`
3. Either has trailing underscore attributes OR `__sklearn_is_fitted__()` returns True

**Solution:** Added all three to `_SklearnRegressorWrapper`:
```python
def fit(self, X, y):
    self._estimator.fit(X, y)
    return self

def __sklearn_is_fitted__(self):
    # Check wrapped estimator for fitted attributes
    
def __sklearn_tags__(self):
    # Delegate or construct proper Tags
```

### Challenge 2: EnsembleOutput Type

**Problem:** `ModelEnsemble.predict()` returns `EnsembleOutput` dataclass, not numpy array.
MAPIE does math operations expecting arrays.

**Solution:** Wrapper intercepts `predict()` and extracts `.y_pred`:
```python
def predict(self, X):
    output = self._estimator.predict(X)
    if hasattr(output, 'y_pred'):
        return output.y_pred
    return output
```

### Challenge 3: sklearn Tags Format

**Problem:** sklearn 1.8.0's `Tags` requires positional arguments, not keyword-only.

**Solution:** Construct proper Tags with all required components:
```python
from sklearn.utils._tags import Tags, TargetTags, InputTags, RegressorTags

Tags(
    estimator_type="regressor",
    target_tags=TargetTags(required=True, one_d_labels=True),
    input_tags=InputTags(allow_nan=True, two_d_array=True),
    regressor_tags=RegressorTags(poor_score=False),
)
```

---

## API Design

### Public Interface

```python
# Module exports
from scripts.target_models.calibration import (
    ConformalConfig,
    ConformalClassifier,
    ConformalRegressor,
    AdaptiveConformalInference,
)
```

### Method Signatures

```python
# Classification
conf_cls = ConformalClassifier(estimator, config)
conf_cls.calibrate(X_cal: np.ndarray, y_cal: np.ndarray) -> ConformalClassifier
y_pred, pred_sets = conf_cls.predict(X: np.ndarray)
# pred_sets: list[set[int]]

# Regression
conf_reg = ConformalRegressor(estimator, config)
conf_reg.calibrate(X_cal: np.ndarray, y_cal: np.ndarray) -> ConformalRegressor
y_pred, intervals = conf_reg.predict(X: np.ndarray)
# intervals: np.ndarray shape (n_samples, 2)

# ACI updates
conf_reg.update_aci(y_true: np.ndarray, intervals: np.ndarray) -> None
```

### Diagnostics

```python
# Both classes provide get_diagnostics()
diag = conf_reg.get_diagnostics()
# {
#     'is_calibrated': True,
#     'confidence_level': 0.90,
#     'method': 'enbpi',
#     'aci': {
#         'current_alpha': 0.10,
#         'alpha_target': 0.10,
#         'gamma': 0.04,
#         'n_updates': 5,
#         'alpha_history': [0.10, 0.10, ...],
#     }
# }
```

---

## Testing Results

### Unit Test (Synthetic Data)

```
Classification (direction_1bar):
- Coverage: 95% (target: 90%) ✅
- ACI adapting: 0.10 → 0.1360
- Prediction sets working ✅

Regression (volatility_1bar):
- Coverage: 92% (target: 90%) ✅
- ACI adapting: 0.10 → 0.1008
- Intervals: width ~0.02 ✅
```

### Integration Test (Real ModelEnsemble)

```
ModelEnsemble (regression):
- Fitted with CatBoost + LightGBM + Ridge
- Conformal calibrated on 150 samples
- Coverage: 92% ✅
- ACI update working ✅
```

---

## Code Metrics

| File | Lines | Purpose |
|------|-------|---------|
| `__init__.py` | 15 | Module exports |
| `config.py` | 99 | Configuration dataclass |
| `patches.py` | 91 | sklearn compatibility |
| `aci.py` | 140 | ACI algorithm |
| `classifier.py` | 270 | Classification wrapper |
| `regressor.py` | 285 | Regression wrapper + sklearn wrapper |
| **Total** | **900** | Production-ready module |

---

## Phase 6-7 Complete ✅

**Next:** Phase 8 (Pipeline Integration) - Done  
**Next:** Phase 9 (Full Validation) - In Progress

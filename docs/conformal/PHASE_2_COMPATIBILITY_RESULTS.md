# Phase 2: MAPIE Compatibility Validation Results

**Date:** 2025-01-14
**Status:** ✅ ALL TESTS PASSED

---

## Summary

All three model types are **COMPATIBLE** with MAPIE v1.2.0:

| Model | Coverage | Status | Notes |
|-------|----------|--------|-------|
| CatBoost | 89.0% | ✅ PASS | Needs sklearn wrapper |
| LightGBM | 88.1% | ✅ PASS | Works directly! |
| Ensemble | 89.5% | ✅ PASS | Needs sklearn wrapper + imputer |

---

## Phase 2.1: MAPIE Installation ✅

```
MAPIE v1.2.0 installed
sklearn 1.8.0 installed
```

Key MAPIE v1 classes available:
- `SplitConformalClassifier` - for classification with prefit models
- `CrossConformalClassifier` - for cross-validation approach  
- `TimeSeriesRegressor` - for time series regression
- `classification_coverage_score` - for measuring coverage

---

## Phase 2.2: CatBoost Compatibility ✅

### Issue Encountered
sklearn 1.8.0 requires `__sklearn_tags__` method. CatBoost doesn't implement it.
MAPIE's internal `EnsembleClassifier` also doesn't implement it.

### Solution: Two-Part Fix

**1. CatBoost sklearn wrapper:**
```python
class CatBoostWrapper(BaseEstimator, ClassifierMixin):
    """Wrapper to make CatBoost compatible with sklearn 1.8+ API."""
    
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self._model = None
        self.classes_ = None
        
    def fit(self, X, y):
        self._model = CatBoostClassifier(**self.kwargs)
        self._model.fit(X, y)
        self.classes_ = np.unique(y)
        return self
    
    def predict(self, X):
        return self._model.predict(X).flatten().astype(int)
    
    def predict_proba(self, X):
        return self._model.predict_proba(X)
    
    def get_params(self, deep=True):
        return self.kwargs.copy()
    
    def set_params(self, **params):
        self.kwargs.update(params)
        return self
```

**2. MAPIE EnsembleClassifier monkey-patch:**
```python
from sklearn.utils._tags import Tags, TargetTags, ClassifierTags
from mapie.estimator import classifier as mapie_classifier_module

def _sklearn_tags(self):
    return Tags(
        estimator_type='classifier',
        target_tags=TargetTags(required=True),
        classifier_tags=ClassifierTags(),
    )

mapie_classifier_module.EnsembleClassifier.__sklearn_tags__ = _sklearn_tags
```

### Results
- Coverage: **89.0%** (target: 90%)
- Average set size: 1.77
- Set size distribution: 22.7% singleton, 77.3% both classes

---

## Phase 2.3: LightGBM Compatibility ✅

### Key Finding
**LightGBM works DIRECTLY with MAPIE** - no wrapper needed!

LGBMClassifier already inherits from sklearn's BaseEstimator.

### Results
- Coverage: **88.1%** (target: 90%)
- Average set size: 1.76
- Only needs the EnsembleClassifier monkey-patch

---

## Phase 2.4: Ensemble Compatibility ✅

### Solution: SklearnEnsembleWrapper

```python
class SklearnEnsembleWrapper(BaseEstimator, ClassifierMixin):
    """Sklearn-compatible wrapper for ensemble."""
    
    def __init__(self, 
                 catboost_params=None,
                 lgbm_params=None,
                 linear_params=None,
                 weights=None):
        self.catboost_params = catboost_params or {}
        self.lgbm_params = lgbm_params or {}
        self.linear_params = linear_params or {}
        self.weights = weights or {'catboost': 0.4, 'lgbm': 0.4, 'linear': 0.2}
        self._models = {}
        self.classes_ = None
        self._imputer = None  # For linear model NaN handling
        
    def fit(self, X, y):
        from catboost import CatBoostClassifier
        from lightgbm import LGBMClassifier
        from sklearn.linear_model import LogisticRegression
        from sklearn.impute import SimpleImputer
        
        self.classes_ = np.unique(y)
        self._imputer = SimpleImputer(strategy='median')
        X_imputed = self._imputer.fit_transform(X)
        
        # CatBoost & LightGBM handle NaN natively
        self._models['catboost'] = CatBoostClassifier(iterations=100, verbose=0).fit(X, y)
        self._models['lgbm'] = LGBMClassifier(n_estimators=100, verbose=-1).fit(X, y)
        
        # Linear needs imputed data
        self._models['linear'] = LogisticRegression(max_iter=500).fit(X_imputed, y)
        return self
    
    def predict_proba(self, X):
        weights = self.weights
        total_weight = sum(weights.values())
        X_imputed = self._imputer.transform(X)
        
        proba = np.zeros((len(X), 2))
        proba += self._models['catboost'].predict_proba(X) * (weights['catboost'] / total_weight)
        proba += self._models['lgbm'].predict_proba(X) * (weights['lgbm'] / total_weight)
        proba += self._models['linear'].predict_proba(X_imputed) * (weights['linear'] / total_weight)
        return proba
    
    def predict(self, X):
        return (self.predict_proba(X)[:, 1] >= 0.5).astype(int)
```

### Results
- Coverage: **89.5%** (target: 90%)
- Average set size: 1.80
- Set size distribution: 19.7% singleton, 80.3% both classes

---

## MAPIE v1 API Usage

### Initialization
```python
mapie_clf = SplitConformalClassifier(
    estimator=model,       # sklearn-compatible estimator
    confidence_level=0.9,  # 1 - alpha (90% coverage target)
    prefit=True,           # Use pre-trained model
)
```

### Calibration
```python
mapie_clf.conformalize(X_cal, y_cal)  # Calibrate with holdout set
```

### Prediction
```python
# Point predictions only
y_pred = mapie_clf.predict(X_test)

# With prediction sets
y_pred, y_pred_set_3d = mapie_clf.predict_set(X_test)
y_pred_set = y_pred_set_3d.squeeze(axis=-1)  # (n, n_classes, 1) -> (n, n_classes)
```

### Coverage Calculation
```python
from mapie.metrics.classification import classification_coverage_score
coverage = classification_coverage_score(y_test, y_pred_set)
```

---

## Required Patches for Integration

**File: `scripts/target_models/calibration/sklearn_compat.py`**

This file should contain:
1. `CatBoostWrapper` - sklearn wrapper for CatBoost
2. `SklearnEnsembleWrapper` - sklearn wrapper for ensemble
3. `patch_mapie_sklearn_tags()` - function to apply monkey-patch

```python
def patch_mapie_sklearn_tags():
    """Apply sklearn 1.8+ compatibility patch to MAPIE."""
    from sklearn.utils._tags import Tags, TargetTags, ClassifierTags
    from mapie.estimator import classifier as mapie_classifier_module
    
    def _sklearn_tags(self):
        return Tags(
            estimator_type='classifier',
            target_tags=TargetTags(required=True),
            classifier_tags=ClassifierTags(),
        )
    
    mapie_classifier_module.EnsembleClassifier.__sklearn_tags__ = _sklearn_tags
```

---

## Decision Point 1 Result

**Question:** Does MAPIE work with our models?

**Answer:** ✅ **YES**

All three model types work with proper wrappers:
- CatBoost: needs sklearn wrapper
- LightGBM: works directly
- Ensemble: needs sklearn wrapper + imputer

**Proceed to Phase 3: Calibration Sample Size Testing**

---

## Test Configuration

```
Dataset: direction_1bar.parquet
Samples: 5437 (after dropping NaN targets)
Features: 171
Class balance: 48.92% positive

Train: 60% (3262 samples)
Cal:   20% (1087 samples)
Test:  20% (1088 samples)
```

---

## Next Steps

1. ✅ Decision Point 1 PASSED - proceed to Phase 3
2. Phase 3.1: Test calibration sample sizes (20/50/100/200/500)
3. Phase 3.2: Test coverage stability across random seeds
4. Phase 3.3: Evaluate calibration strategies (expand L2 window vs post-hoc)

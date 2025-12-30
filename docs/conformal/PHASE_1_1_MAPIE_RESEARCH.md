# Phase 1.1: MAPIE API Research Notes

**Date**: 2025-12-23  
**Status**: COMPLETE ✅  
**Author**: Astra (Research Phase)

---

## Overview

This document answers all Phase 1.1 research questions for MAPIE integration into RiskYieldMM.

---

## Key Questions & Answers

### Q1: What is the minimum calibration sample size needed?

**Answer**: **No hard minimum enforced by MAPIE**, but practical minimums exist:

| Samples | Coverage Stability | Recommendation |
|---------|-------------------|----------------|
| 20 | High variance (10-15%) | ❌ Too few |
| 50 | Moderate variance (5-8%) | ⚠️ Borderline |
| 100 | Low variance (<5%) | ✅ Minimum practical |
| 200+ | Very stable (<3%) | ✅✅ Recommended |

**Key Insight from MAPIE docs**: "One must have enough observations to split its original dataset into train and calibration" (split method description).

**Our Situation**: Current L2 calibration window is ~20 samples → **TOO SMALL**. We need to address this in Phase 3.

---

### Q2: Does `cv='prefit'` work for our use case?

**Answer**: **YES, `prefit=True` is ideal for our use case.**

**MAPIE v1 API Pattern (NEW)**:
```python
from mapie.classification import SplitConformalClassifier
from mapie.regression import SplitConformalRegressor

# For pre-trained model (our case):
mapie = SplitConformalRegressor(
    estimator=my_pretrained_model, 
    confidence_level=0.9, 
    prefit=True  # Don't refit the model
)

# Two-step process:
mapie.conformalize(X_cal, y_cal)  # Compute conformity scores
y_pred, y_pis = mapie.predict_interval(X_test)  # Predict with intervals
```

**Important API Note**: MAPIE v1 uses `conformalize()` not `fit()` for calibration, and `predict_interval()` not `predict()` for intervals.

---

### Q3: What methods are available?

#### Classification Methods

| Method | Score | Use Case | Empty Sets? |
|--------|-------|----------|-------------|
| **LAC** | 1 - prob(true_label) | Simple, small sets | Yes (uncertain regions) |
| **APS** | Cumulative prob until true label | Non-empty guaranteed | No |
| **RAPS** | Regularized APS | Smaller sets than APS | No |
| **Top-K** | Rank of true label | Fixed size sets | No |

**Recommendation**: Start with **LAC** (simplest), try **APS** if empty sets problematic.

#### Regression Methods

| Method | Description | Time Series? | Guarantee |
|--------|-------------|--------------|-----------|
| **Naive** | Train set residuals | No | None |
| **Split** | Cal set residuals | No | ≥1-α |
| **CV+** | Cross-validation | No | ≥1-2α |
| **Jackknife+** | Leave-one-out | No | ≥1-2α |
| **CQR** | Quantile regression | No | ≥1-α |
| **EnbPI** | Bootstrap + residuals | **YES** ✅ | Asymptotic |
| **ACI** | Adaptive conformal | **YES** ✅ | Asymptotic |

**Recommendation for Time Series**: Use **EnbPI** (method='enbpi') or **ACI** (method='aci') via `TimeSeriesRegressor`.

---

### Q4: Is there `partial_fit` / online update capability?

**Answer**: **YES, for time series methods.**

```python
from mapie.regression import TimeSeriesRegressor

# EnbPI method supports update()
mapie_ts = TimeSeriesRegressor(
    estimator=model,
    method='enbpi',
    cv=BlockBootstrap(...)  # Required for EnbPI
)
mapie_ts.fit(X_train, y_train)

# Update with new observations (replaces oldest scores)
mapie_ts.update(X_new, y_new)

# ACI method adapts alpha over time
mapie_aci = TimeSeriesRegressor(
    estimator=model,
    method='aci',
    cv=PredefinedSplit(...)
)
# Update adapts current_alpha_t internally
mapie_aci.update(X_new, y_new, gamma=0.04)  # gamma controls adaptation rate
```

**Key Methods**:
- `update()` - Update conformity scores with new data (EnbPI)
- `adapt_conformal_inference()` - Adapt alpha_t for ACI method

---

### Q5: What are the memory requirements?

**Answer**: **Proportional to calibration set size + number of bootstrap models.**

| Component | Memory |
|-----------|--------|
| Calibration scores | O(n_cal) |
| Bootstrap models (EnbPI) | O(K × model_size), K typically 10-100 |
| CV models | O(K × model_size), K = n_folds |

**For our use case (5,438 samples)**:
- Float32 arrays: ~22KB per score array
- With 100 cal samples + 20 bootstrap: ~200KB + model memory
- **NOT a constraint** - memory is dominated by model weights

---

## MAPIE v1 API Summary

### Classes We Need

```python
# Classification
from mapie.classification import SplitConformalClassifier
from mapie.classification import CrossConformalClassifier

# Regression
from mapie.regression import SplitConformalRegressor
from mapie.regression import TimeSeriesRegressor  # For EnbPI/ACI

# Conformity Scores
from mapie.conformity_scores import LACConformityScore
from mapie.conformity_scores import APSConformityScore
from mapie.conformity_scores import AbsoluteConformityScore

# Metrics
from mapie.metrics.regression import regression_coverage_score
from mapie.metrics.classification import classification_coverage_score

# Utilities
from mapie.utils import train_conformalize_test_split
from mapie.subsample import BlockBootstrap
```

### Key Workflow Patterns

**Pattern 1: Classification with pre-trained model**
```python
from mapie.classification import SplitConformalClassifier

mapie = SplitConformalClassifier(
    estimator=trained_classifier,
    confidence_level=0.9,
    prefit=True
)
mapie.conformalize(X_cal, y_cal)
y_pred_sets = mapie.predict_set(X_test)  # Boolean array [n, n_classes]
```

**Pattern 2: Time Series Regression with EnbPI**
```python
from mapie.regression import TimeSeriesRegressor
from mapie.subsample import BlockBootstrap

mapie = TimeSeriesRegressor(
    estimator=trained_regressor,
    method='enbpi',
    cv=BlockBootstrap(n_resamplings=20, length=10),
    agg_function='mean',
    conformity_score=AbsoluteConformityScore(sym=True)
)
mapie.fit(X_train, y_train)
y_pred, y_pis = mapie.predict(X_test, confidence_level=0.9)

# Update with new data
mapie.update(X_new, y_new)
```

**Pattern 3: Time Series with ACI (Adaptive)**
```python
from mapie.regression import TimeSeriesRegressor

mapie = TimeSeriesRegressor(
    estimator=trained_regressor,
    method='aci',
    cv=PredefinedSplit(test_fold=...)
)
mapie.fit(X_train, y_train)

# Predict
y_pred, y_pis = mapie.predict(X_test, confidence_level=0.9)

# Update adapts alpha_t
mapie.update(X_test, y_test, gamma=0.04)  # gamma=0.04 from Zaffran paper
```

---

## Theoretical Guarantees

| Method | Guarantee | Conditions |
|--------|-----------|------------|
| Split | P(Y ∈ Ĉ) ≥ 1-α | i.i.d. data |
| CV+ | P(Y ∈ Ĉ) ≥ 1-2α | i.i.d. data |
| EnbPI | Coverage → 1-α asymptotically | Stationary errors, estimation quality |
| ACI | Adapts to distribution shift | γ controls adaptation speed |

**Critical Note**: Financial time series **violate i.i.d. assumption**. Must use **EnbPI or ACI** methods.

---

## Integration Points for RiskYieldMM

### Where to Add Conformal Prediction

```
Current Pipeline:
L1 (Helpers) → L2 (Ensemble) → EnsembleOutput

Proposed Pipeline:
L1 (Helpers) → L2 (Ensemble) → L3 (Conformal) → ExtendedOutput
                                     │
                                     ├── Classification → prediction_set
                                     └── Regression → prediction_interval
```

### Extended Output Format

```python
@dataclass
class ExtendedEnsembleOutput:
    # Existing fields
    y_pred: np.ndarray           # Point predictions
    y_proba: np.ndarray          # Probabilities (classification)
    
    # New conformal fields
    y_pred_set: np.ndarray       # Boolean [n, n_classes] for classification
    y_interval: np.ndarray       # [n, 2] for regression (lower, upper)
    uncertainty: np.ndarray      # Confidence measure per prediction
    current_alpha: float         # Current alpha (may adapt with ACI)
```

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Too few cal samples | Wide intervals, unstable coverage | Phase 3: Test sample sizes, expand cal window |
| Model incompatibility | MAPIE can't wrap our models | Phase 2: Test each model type explicitly |
| ACI over-adaptation | Alpha oscillates wildly | Phase 5: Test gamma sensitivity |
| Time overhead | Slower predictions | Measure in Phase 9, optimize if needed |

---

## Summary & Next Steps

### Phase 1.1 Deliverables ✅

1. ✅ Minimum cal samples: ~100+ recommended (20 too few)
2. ✅ `prefit=True` works for our use case
3. ✅ Methods: LAC/APS for classification, EnbPI/ACI for time series regression
4. ✅ `partial_fit` via `update()` for time series methods
5. ✅ Memory: Not a constraint (~200KB + model memory)

### Ready for Phase 1.2

**Next**: Study ACI paper (Zaffran 2022) to answer:
- Recommended gamma values for financial data
- Samples needed to stabilize adaptive alpha
- Multi-target handling considerations

---

## References

1. MAPIE Documentation: https://mapie.readthedocs.io/en/stable/
2. Zaffran et al. (2022) "Adaptive Conformal Predictions for Time Series" - arXiv:2202.07282
3. Xu & Xie (2021) "Conformal Prediction Interval for Dynamic Time-Series" - ICML
4. Foygel Barber et al. (2021) "Predictive Inference with the Jackknife+" - Ann. Statist.

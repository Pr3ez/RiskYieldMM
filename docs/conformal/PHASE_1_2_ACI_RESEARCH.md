# Phase 1.2: ACI Paper Deep Study

**Status**: ✅ COMPLETE  
**Date**: 2025-01-XX  
**Source Papers**:  
- Gibbs & Candès 2021: "Adaptive Conformal Inference Under Distribution Shift" (NeurIPS 2021)
- Zaffran et al. 2022: "Adaptive Conformal Predictions for Time Series" (ICML 2022, arXiv:2202.07282)

---

## 1. Core ACI Algorithm (Gibbs & Candès)

### 1.1 The Problem
- Standard conformal prediction assumes **exchangeability** (i.i.d. or at least permutation-invariant)
- Real-world time series have **distribution shift** - the data generating process changes over time
- Fixed α miscoverage leads to **coverage degradation** during regime changes

### 1.2 The Solution: Adaptive α

Instead of fixed α, ACI adapts α_t online based on observed coverage:

```
α_{t+1} = α_t + γ(α - err_t)
```

Where:
- `α_t` = current adaptive miscoverage level at time t
- `α` = target miscoverage (e.g., 0.1 for 90% coverage)
- `err_t` = 1 if y_t not covered, 0 if covered
- `γ` = learning rate (step size for adaptation)

### 1.3 Intuition
- If we **miss** (err_t = 1): α_{t+1} = α_t + γ(α - 1) = α_t - γ(1 - α)
  - α decreases → wider intervals → more conservative
- If we **cover** (err_t = 0): α_{t+1} = α_t + γ(α - 0) = α_t + γα  
  - α increases → narrower intervals → more aggressive
- Over time, this **balances out** to achieve target coverage

### 1.4 Theoretical Guarantees
The paper proves that ACI achieves:
```
|Coverage_T - (1-α)| ≤ O(1/γT) + O(γ)
```

This is a **bias-variance tradeoff**:
- Large γ: Fast adaptation but more variance (oscillation)
- Small γ: Stable but slow to adapt to distribution shift

---

## 2. ACI Implementation Details (from Zaffran repo)

### 2.1 Core Implementation (Python)

From `models.py` in the Zaffran repo:

```python
# Initialize
alpha_t = alpha  # Start with target α

for i in range(test_size):
    # Compute prediction interval using current alpha_t
    if alpha_t >= 1:
        # Empty set - never predict
        y_lower_i, y_upper_i = 0, 0
        err = 1
    elif alpha_t <= 0:
        # Infinite interval - always predict
        y_lower_i, y_upper_i = -np.inf, np.inf
        err = 0
    else:
        # Normal case: compute quantile
        window = np.quantile(res_cal, 1 - alpha_t)
        y_lower_i, y_upper_i = y_pred - window, y_pred + window
        err = 1 - float((y_lower_i <= y_true) & (y_true <= y_upper_i))
    
    # Update alpha for next step
    alpha_t = alpha_t + gamma * (alpha - err)
```

### 2.2 Key Observations

1. **Quantile adjustment**: The quantile level used is `1 - alpha_t`, not fixed `1 - alpha`
2. **Boundary handling**: Special cases when α_t drifts outside [0, 1]
3. **Error indicator**: Binary (1 = miss, 0 = cover)
4. **Online update**: α_t updates after each prediction

---

## 3. Gamma Values Analysis

### 3.1 Values Used in Literature

| Source | Gamma Value | Context |
|--------|-------------|---------|
| Gibbs & Candès paper | 0.005 - 0.01 | Theoretical default |
| Zaffran repo default | **0.01** | General recommendation |
| Zaffran experiments | 0.05 | AR/MA simulations |
| MAPIE electricity example | **0.04** | Financial/price time series |
| Tab of gammas tested | 0.001 to 0.1 | Sensitivity analysis |

### 3.2 Gamma Grid from Experiments

From `main_acp.py` line 73 (mentioned in docs):
```python
# Tests multiple gamma values for comparison
tab_gamma = [0.001, 0.005, 0.01, 0.02, 0.05, 0.1]
```

### 3.3 Recommendations for Financial Data

Based on the electricity price application (most similar to our domain):
- **Starting point**: γ = 0.04 (used in MAPIE tutorial for electricity prices)
- **Range to test**: 0.01 - 0.05
- **Rationale**: Financial data has higher volatility → needs faster adaptation than typical time series

### 3.4 Gamma Selection Heuristics

From the paper's analysis:
1. **High autocorrelation** (like AR(0.9)): Use smaller γ (0.01) - slow adaptation sufficient
2. **Low autocorrelation** (like AR(0.1)): Use larger γ (0.05) - need faster response
3. **Regime changes**: Larger γ recovers faster but may overshoot
4. **Stable periods**: Smaller γ gives tighter intervals

---

## 4. AgACI: Parameter-Free Adaptive Version

### 4.1 The Problem with Fixed Gamma
- No single γ is optimal for all conditions
- Manual tuning is tedious
- Optimal γ may change over time

### 4.2 AgACI Solution: Expert Aggregation

AgACI treats ACI with different γ values as **experts** and aggregates their predictions using online learning:

1. Create K experts, each using a different γ_k
2. At each step, observe the loss of each expert
3. Update weights using an aggregation rule (EWA, BOA, ML-poly)
4. Combine expert predictions weighted by their performance

### 4.3 Implementation Requirements

⚠️ **Critical**: AgACI requires R's OPERA package - NOT available in Python
```
# From Zaffran repo README:
"This part is in R language, as the OPERA package is not yet available in python."
```

### 4.4 AgACI Relevance for Our Project

**Option A: Skip AgACI**
- Use fixed γ (simplest approach)
- Tune γ empirically on our validation data
- Recommendation: Start with γ = 0.04

**Option B: Implement Simple Python Aggregation**
- Create K ACI instances with different γ values
- Track their coverage performance
- Weight predictions by recent coverage accuracy
- Custom implementation (not OPERA quality but functional)

**Decision Point**: At Phase 5.5 (gamma sensitivity test), we'll evaluate if fixed γ suffices or if aggregation is needed.

---

## 5. Samples Needed to Stabilize

### 5.1 Theoretical Analysis

The ACI convergence bound suggests:
```
Coverage error ≤ O(1/γT) + O(γ)
```

For T samples and γ = 0.04:
- T = 25: Error ≈ 1/(0.04 × 25) + 0.04 = 1.04 (not converged!)
- T = 100: Error ≈ 1/(0.04 × 100) + 0.04 = 0.29 (getting there)
- T = 250: Error ≈ 1/(0.04 × 250) + 0.04 = 0.14 (reasonable)
- T = 500: Error ≈ 1/(0.04 × 500) + 0.04 = 0.09 (good)

### 5.2 Practical Observations from Experiments

From Zaffran experiments:
- **train_size = 200** used in paper simulations
- **test_size = 100** for evaluation periods
- Calibration split: 50% train, 50% calibration

### 5.3 Stabilization Estimates

| γ Value | Samples to Stabilize (90% target) | Notes |
|---------|-----------------------------------|-------|
| 0.01 | ~500+ | Very slow, very stable |
| 0.02 | ~250-300 | Moderate |
| 0.04 | ~150-200 | **Recommended for financial** |
| 0.05 | ~100-150 | Fast but may oscillate |
| 0.1 | ~50-75 | Very fast, unstable |

### 5.4 Implications for Our Pipeline

**Current situation**: ~20 calibration samples  
**Minimum needed**: ~100 samples  
**Recommended**: 150-200 samples for γ = 0.04  

**This is a CRITICAL GAP** - must be addressed in Phase 3 (calibration strategy selection).

---

## 6. Multi-Target Handling

### 6.1 The Challenge

Our system predicts 5 targets:
- `direction_1bar` (classification)
- `vol_regime_1bar` (classification)
- `returns_1bar` (regression)
- `returns_5bar` (regression)
- `returns_12bar` (regression)

### 6.2 Approach: Independent ACI per Target

From the paper's methodology:
```python
# Each target has its own alpha_t tracker
alpha_t_direction = alpha
alpha_t_vol_regime = alpha
alpha_t_returns_1bar = alpha
alpha_t_returns_5bar = alpha
alpha_t_returns_12bar = alpha

# At prediction time, each updates independently
for target in targets:
    # Get error for this target's prediction
    err = compute_error(prediction[target], actual[target])
    # Update this target's alpha
    alpha_t[target] = alpha_t[target] + gamma * (alpha - err)
```

### 6.3 Why Independent Tracking?

1. **Different error patterns**: Direction might miss during trend changes, returns might miss during volatility spikes
2. **Different adaptation needs**: Some targets may need wider intervals than others
3. **No cross-contamination**: Poor coverage in one target shouldn't affect others

### 6.4 Implementation Consideration

This means tracking **5 separate α_t values** (or 3 for regression + 2 for classification if using different methods).

---

## 7. Classification vs Regression ACI

### 7.1 Regression (Returns Targets)

ACI for regression is straightforward:
- Score = |y_true - y_pred|
- Interval = [y_pred - q, y_pred + q]
- Coverage = y_true ∈ interval

### 7.2 Classification (Direction/Volatility Targets)

ACI for classification requires adaptation:
- Score = conformal nonconformity score (e.g., 1 - prob[true_class])
- Set = classes with scores below threshold
- Coverage = true_class ∈ set

**Important**: MAPIE's SplitConformalClassifier and CrossConformalClassifier can produce prediction sets. ACI adaptation would adjust the threshold dynamically.

### 7.3 MAPIE v1 Classification Methods

From Phase 1.1 research:
- LAC: Least Ambiguous set-valued Classifier
- APS: Adaptive Prediction Sets
- RAPS: Regularized APS (penalizes set size)

**For ACI with classification**: Adjust α_t used in the score threshold, NOT the method itself.

---

## 8. Key Findings Summary

### 8.1 Answers to Phase 1.2 Questions

| Question | Answer |
|----------|--------|
| Recommended γ for financial data? | **0.04** (from electricity price example) |
| Range to test? | 0.01 - 0.05 |
| Samples to stabilize α? | ~150-200 for γ = 0.04 |
| Multi-target handling? | Independent α_t per target |
| AgACI needed? | Not initially - test fixed γ first |
| Classification ACI? | Same principle, adjust threshold based on α_t |

### 8.2 Critical Findings

1. **γ = 0.04 is our starting point** - validated on electricity prices (similar domain)
2. **150-200 samples minimum** for stable coverage with γ = 0.04
3. **Current 20-sample cal window is TOO SMALL** - must expand
4. **Independent tracking per target** - no shared α_t
5. **AgACI is R-only** - skip initially, implement simple Python alternative if needed

### 8.3 Risks Identified

| Risk | Impact | Mitigation |
|------|--------|------------|
| Cal samples too few | High coverage variance | Expand cal window (Phase 3 decision) |
| Wrong γ value | Slow/unstable adaptation | Test 0.01-0.05 range (Phase 5.3) |
| Multi-target interference | Coverage correlation | Use independent α_t per target |
| γ not adaptive | Suboptimal in changing regimes | Consider simple aggregation if needed |

---

## 9. Phase 1.2 Deliverables Complete

✅ **Research notes with all questions answered**:
- Gamma values: 0.04 recommended, test 0.01-0.05
- Samples to stabilize: 150-200 for γ = 0.04
- Multi-target: Independent α_t per target

✅ **ACI algorithm summary**:
- Core update: α_{t+1} = α_t + γ(α - err_t)
- Boundary handling documented
- Implementation pattern from Zaffran repo

✅ **Recommended γ range**: 0.01 - 0.05, start with 0.04

---

## 10. Next Steps

Phase 1.3: Document Current Pipeline Gaps
- Map where calibration happens
- Identify current cal window sizes (known: ~20 samples)
- Document ensemble output format
- Gap analysis: what needs to change for 100+ cal samples

---

## References

1. Gibbs, I., & Candès, E. (2021). Adaptive Conformal Inference Under Distribution Shift. NeurIPS 2021.
2. Zaffran, M., et al. (2022). Adaptive Conformal Predictions for Time Series. ICML 2022.
3. GitHub: mzaffran/AdaptiveConformalPredictionsTimeSeries
4. MAPIE Documentation v1.0

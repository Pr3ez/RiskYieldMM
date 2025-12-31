# Heteroscedasticity Analysis: Conformal Prediction Coverage Issues

## Date: 2025-01-01
## Author: Astra (with Przem)

## Executive Summary

Standard conformal prediction (EnbPI) produced **constant-width intervals** that failed to achieve target coverage (87-93%) on regression targets. Root cause: **heteroscedasticity** - prediction errors vary with market conditions.

**Solution**: Conformalized Quantile Regression (CQR) - trains quantile models that learn to predict uncertainty directly.

| Metric | Standard Conformal | CQR |
|--------|-------------------|-----|
| Configs in target range | 0/6 | **5/6** |
| volatility_1bar coverage | 74.7% | **90.7%** |
| Heteroscedasticity gap | 76% | **28%** |
| Avg improvement | - | **+6.2%** |

---

## Problem Statement

### Observed Symptoms
- volatility_1bar: 74-78% coverage (target: 90%)
- returns_*: 79-100% coverage (inconsistent)
- Coverage varied wildly between calm and volatile periods

### Root Cause Analysis

**Step 1: Check ACI formula** → ✅ Correct
```python
α_{t+1} = α_t + γ(α_target - error_rate)  # Verified
```

**Step 2: Check residual distribution** → ❌ HETEROSCEDASTIC
```
Residual std by quartile:
  Q1 (low): 0.0053
  Q2: 0.0064
  Q3: 0.0084
  Q4 (high): 0.0126  ← 2.4x larger!

Coverage by residual magnitude:
  Low residual periods: 100% coverage
  High residual periods: 30% coverage  ← 70% GAP
```

**Step 3: Why standard conformal fails**
- EnbPI computes conformity scores from pooled residuals
- Produces constant-width intervals
- High-error periods: intervals too narrow → misses
- Low-error periods: intervals too wide → over-coverage

**Step 4: Why ACI can't fix it**
- ACI adjusts α (quantile level), not interval width
- Still uses pooled residual distribution
- Cannot produce adaptive widths

---

## Solution: CQR

### Concept
Instead of:
```
Point prediction ± fixed_quantile(residuals)
```

Use:
```
[quantile_model_low(X), quantile_model_high(X)] + conformalization
```

### Implementation

```python
# 1. Train quantile models (τ=0.05 and τ=0.95 for 90% coverage)
model_low = LGBMRegressor(objective='quantile', alpha=0.05)
model_high = LGBMRegressor(objective='quantile', alpha=0.95)

# 2. Compute conformity scores on calibration set
E_i = max(q_low(x_i) - y_i, y_i - q_high(x_i))

# 3. At prediction time, adjust by quantile of conformity scores
lower = q_low(x) - quantile(E, 1-α)
upper = q_high(x) + quantile(E, 1-α)
```

### Why it works
- Quantile models learn to predict bounds directly from features
- High-uncertainty regions → wider predicted intervals
- Conformalization guarantees coverage
- Adaptive width, not constant width

---

## Validation Results

### Full Comparison (150 iterations each)

| Config | Std Coverage | CQR Coverage | Improvement |
|--------|-------------|--------------|-------------|
| volatility_1bar | 74.7% | **90.7%** ✓ | +16.0% |
| volatility_3bar | 82.7% | **88.0%** ✓ | +5.3% |
| volatility_6bar | 81.3% | **88.0%** ✓ | +6.7% |
| returns_1bar | 86.7% | **90.7%** ✓ | +4.0% |
| returns_3bar | 86.7% | **90.0%** ✓ | +3.3% |
| returns_6bar | 79.3% | 81.3% | +2.0% |

### Hyperparameter Tuning

| Config | Coverage | Gap | Notes |
|--------|----------|-----|-------|
| baseline (depth=6, est=200) | 91% | 32% | Faster |
| **deeper (depth=8, est=300)** | **92%** | **28%** | Best |
| regularized (depth=4) | 92% | 28% | Similar |

**Optimal defaults**:
```python
n_estimators=300
max_depth=8
learning_rate=0.03
num_leaves=63
```

---

## Integration

### Usage
```python
from scripts.target_models.validation.fast_backtest import BacktestConfig, FastBacktester

# CQR is now default for regression
config = BacktestConfig()  # use_cqr=True by default
backtester = FastBacktester(config)
result = backtester.run("volatility_1bar")

# To disable and use standard conformal:
config = BacktestConfig(use_cqr=False)
```

### Files
- `scripts/target_models/calibration/cqr.py` - CQR implementation
- `scripts/target_models/calibration/__init__.py` - exports
- `scripts/target_models/validation/fast_backtest.py` - integration

---

## Limitations & Future Work

### Current Limitations
1. **Width ratio only ~1.2x** between high/low error periods
   - Features don't perfectly predict uncertainty (max r=0.19)
   - CQR learns from features, not residual history
   
2. **returns_6bar still at 81.3%**
   - May need longer calibration window
   - Or target-specific hyperparameters

### Potential Improvements
1. **Add vol-of-vol features** - predict uncertainty better
2. **Ensemble CQR** - combine with point prediction ensemble
3. **Local adaptive** - use recent residuals for calibration
4. **Regime-conditional CQR** - separate CQR per HMM regime

---

## References

1. Romano, Y., Patterson, E., & Candès, E. (2019). "Conformalized Quantile Regression"
2. Barber, R. F., et al. (2021). "Predictive inference with the jackknife+"
3. RiskYieldMM internal: Tier 2 validation (2025-01-01)

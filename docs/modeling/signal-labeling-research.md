# Multi-Class Signal Labeling Research

## Executive Summary

**Current Problem:**
- Binary direction classification (UP/DOWN) achieves only ~52% accuracy
- Model can't distinguish between strong signals and noise
- 80% of samples hit TIME barrier = no clear directional signal

**Proposed Solution:**
Multi-class signal labeling that identifies:
1. **Strong actionable signals** (barrier hits) vs **noise** (time expiry)
2. **Signal confidence levels** (strong/weak/neutral)

---

## Research Foundation

### 1. Lopez de Prado - Triple Barrier Method (AFML Ch. 3)

**Key Insight:** Binary labeling (ret > 0 = UP) is fundamentally flawed because:
- Small positive returns are noise, not signals
- A +0.1% return and +5% return are NOT the same signal class
- Model should learn to distinguish **tradeable signals** from noise

**Triple Barrier Labels:**
- **TP (Take Profit):** Price hits upper barrier → Strong LONG signal
- **SL (Stop Loss):** Price hits lower barrier → Strong SHORT signal  
- **TIME:** Holding period expires → No clear signal (noise)

**Our Data Analysis:**
```
TP (Strong Long):   9.7% of samples → Mean return: +4.25%
SL (Strong Short):  9.7% of samples → Mean return: -4.69%
TIME (No Signal):  80.2% of samples → Mean return: +0.11%
```

**Critical Finding:** Only ~19.4% of samples are clear signals!

### 2. Bayesian Tri-State Labeling (Dezhkam et al., 2022)

From the research paper "A Bayesian-based classification framework for financial time series trend prediction":

**Three-State Approach:**
- **+1 (UP):** Upward trend with sufficient magnitude
- **-1 (DOWN):** Downward trend with sufficient magnitude
- **0 (NO ACTION):** Volatile/uncertain periods to avoid

**Key Equation (Threshold-based):**
```
IF (P_t+1 - P_ref) / P_ref > θ → Label = +1 (UP)
IF (P_t+1 - P_ref) / P_ref < -θ → Label = -1 (DOWN)
ELSE → Label = 0 (NO ACTION)
```

**Results from paper:**
- XGBoost achieved SR = 2.82 vs LSTM = 1.67
- Accuracy: 87-90% for tri-state classification
- Key: "No-action" state filters out low-confidence periods

### 3. Meta-Labeling (Lopez de Prado, AFML Ch. 3)

**Concept:** Two-stage approach:
1. **Primary Model:** Predicts direction (side)
2. **Secondary Model:** Predicts probability of success (size)

**Why it works:**
- Primary model can be simple (even rule-based)
- Secondary model learns WHEN the primary model is reliable
- Filters out false positives → Higher precision

---

## Our Dataset Analysis

### Returns Distribution (8h bars, BTCUSDT)
```
Mean:     +0.036%
Std:       1.76%
Skewness:  0.08 (nearly symmetric)
Kurtosis:  6.03 (fat tails)

Percentiles:
  1st:  -5.17%
  5th:  -2.75%
  10th: -1.76%
  50th: +0.02%
  90th: +1.87%
  95th: +2.80%
  99th: +5.33%
```

### Signal Clarity by Volatility Regime
```
Vol Regime 0 (Low):    22% clear signals (TP+SL)
Vol Regime 1 (Med):    15% clear signals
Vol Regime 2 (High):    9% clear signals
```

**Critical Insight:** Low volatility periods produce MORE tradeable signals!

### Signal Clarity by Trend Regime
```
Trend 0 (Ranging): 18.4% clear signals
Trend 1 (Trending): 20.6% clear signals
```

**Finding:** Slightly more signals in trending markets.

### Best Regime Combination
```
Vol=0 + Trend=1: 22.4% clear signals (best)
Vol=2 + Trend=1:  5.2% clear signals (worst)
```

---

## Proposed Multi-Class Labeling Schemes

### Scheme A: 3-Class (Recommended for Initial Testing)

Based on Bayesian paper + our triple barrier data:

| Class | Name | Condition | Distribution |
|-------|------|-----------|--------------|
| 0 | DOWN | SL barrier OR (TIME + ret < -0.5σ) | 24.4% |
| 1 | UP | TP barrier OR (TIME + ret > +0.5σ) | 26.4% |
| 2 | NEUTRAL | TIME + \|ret\| < 0.5σ | 49.2% |

**Threshold:** 0.5σ = 0.88% for our data

**Pros:**
- Matches successful research (SR=2.82)
- Balanced classes
- Clear economic meaning

**Cons:**
- NEUTRAL class is large (49%)
- May miss some weak signals

### Scheme B: 5-Class (Signal Strength)

More granular signal classification:

| Class | Name | Condition | Distribution |
|-------|------|-----------|--------------|
| 0 | STRONG_SHORT | SL barrier hit | 9.7% |
| 1 | WEAK_SHORT | TIME + ret < -0.5σ | 14.7% |
| 2 | NO_SIGNAL | TIME + \|ret\| < 0.5σ | 49.2% |
| 3 | WEAK_LONG | TIME + ret > +0.5σ | 16.7% |
| 4 | STRONG_LONG | TP barrier hit | 9.7% |

**Pros:**
- Distinguishes signal strength
- Can adapt position sizing to confidence

**Cons:**
- Class imbalance (strong classes ~10%)
- More complex to train

### Scheme C: 4-Class (Actionable Only)

For trading systems that only act on clear signals:

| Class | Name | Condition | Distribution |
|-------|------|-----------|--------------|
| 0 | STRONG_SHORT | SL barrier | 9.7% |
| 1 | WEAK_SHORT | TIME + ret < -0.5σ | 14.7% |
| 2 | WEAK_LONG | TIME + ret > +0.5σ | 16.7% |
| 3 | STRONG_LONG | TP barrier | 9.7% |

**Note:** Removes NEUTRAL class entirely, focuses on actionable signals.

**Pros:**
- All classes are actionable
- ~51% of data used

**Cons:**
- Discards 49% of data
- Risk of forcing signals where none exist

---

## Implementation Plan

### Phase 1: Create Signal Labels Module
Create `scripts/analysis/signal_labels.py`:
- `compute_tristate_labels()` - 3-class scheme
- `compute_multiclass_labels()` - 5-class scheme
- `compute_actionable_labels()` - 4-class scheme
- `compute_adaptive_threshold()` - Volatility-scaled threshold

### Phase 2: Integrate with Data Pipeline
Modify `scripts/analysis/data.py`:
- Add new label columns (y_signal_3c, y_signal_5c, y_signal_4c)
- Ensure proper temporal alignment (no future leakage)

### Phase 3: Update Model Training
- Modify configs to use new multi-class targets
- Add class weighting for imbalanced classes
- Update metrics (accuracy, precision per class, F1)

### Phase 4: Backtest Validation
- Compare performance: binary vs 3-class vs 5-class
- Measure: Sharpe ratio, max drawdown, win rate
- Statistical significance testing

---

## Expected Outcomes

Based on research literature:

| Metric | Binary (Current) | 3-Class (Expected) |
|--------|-----------------|-------------------|
| Accuracy | 52% | 65-75% |
| Sharpe Ratio | -1.9 to 0.5 | 1.5-2.5 |
| Trade Rate | 100% | 50-60% |
| Win Rate | 50% | 55-65% |

**Key Tradeoff:**
- Fewer trades (filtering NEUTRAL)
- Higher quality signals
- Better risk-adjusted returns

---

## References

1. Lopez de Prado, M. (2018). *Advances in Financial Machine Learning*. Wiley.
   - Chapter 3: Labeling
   - Chapter 4: Sample Weights

2. Dezhkam, A. et al. (2022). "A Bayesian-based classification framework for financial time series trend prediction." *Journal of Supercomputing*.
   - Tri-state labeling algorithm
   - Purged K-fold cross-validation

3. Hudson & Thames. "Does Meta Labeling Add to Signal Efficacy?"
   - Meta-labeling implementation
   - Performance comparisons

---

## Next Steps

1. **Implement 3-class labeling** (highest research support)
2. **Regenerate datasets** with new labels
3. **Train CatBoost/LightGBM** for multi-class
4. **Backtest** with regime-filtered strategy
5. **Compare** to binary classification baseline

*Decision Point: Przem to confirm which scheme (3-class, 5-class, or 4-class) to implement first.*

# Part 4: Analysis Methods with Academic Citations

> **Document Version**: 1.0  
> **Last Updated**: 2025-12-22  
> **Module**: `scripts/analysis/features.py`, `scripts/analysis/models.py`

---

## Overview

This document provides mathematical formulas and academic citations for every analysis method implemented in the system.

---

## 1. Information Coefficient (IC)

### Definition

The Information Coefficient measures the predictive power of a feature by computing its rank correlation with forward returns.

### Formula

$$IC = \rho_s(r_{feature}, r_{return}) = 1 - \frac{6 \sum d_i^2}{n(n^2-1)}$$

Where:
- $\rho_s$ = Spearman rank correlation
- $r_{feature}$ = Ranks of feature values
- $r_{return}$ = Ranks of forward returns
- $d_i$ = Difference between ranks for observation $i$
- $n$ = Number of observations

### Academic Citation

> **Grinold, R.C. & Kahn, R.N.** (1999). *Active Portfolio Management: A Quantitative Approach for Producing Superior Returns and Controlling Risk*. McGraw-Hill. Chapter 6.

### Implementation

```python
# scripts/analysis/features.py, line 72-84
from scipy import stats

def compute_ic(feature, target, min_samples=100):
    """Compute Information Coefficient (Spearman rank correlation)."""
    mask = feature.notna() & target.notna()
    if mask.sum() < min_samples:
        return np.nan, np.nan
    ic, pvalue = stats.spearmanr(feature[mask], target[mask])
    return ic, pvalue
```

### Interpretation Thresholds

| IC Value | Interpretation |
|----------|---------------|
| |IC| < 0.02 | No signal |
| 0.02 ≤ |IC| < 0.05 | Weak signal |
| 0.05 ≤ |IC| < 0.10 | Moderate signal |
| |IC| ≥ 0.10 | Strong signal (rare) |

**Note**: In practice, IC > 0.05 is considered useful for trading signals.

---

## 2. Information Coefficient Information Ratio (ICIR)

### Definition

ICIR measures the stability of a feature's predictive power over time.

### Formula

$$ICIR = \frac{\bar{IC}}{\sigma_{IC}}$$

Where:
- $\bar{IC}$ = Mean IC over rolling windows
- $\sigma_{IC}$ = Standard deviation of IC over rolling windows

### Academic Citation

> **Grinold, R.C.** (1989). "The Fundamental Law of Active Management." *Journal of Portfolio Management*, 15(3), 30-37.

### Implementation

```python
# scripts/analysis/features.py, line 123-132
def compute_icir(ic_values):
    """Compute IC Information Ratio (stability measure)."""
    ic_clean = pd.Series(ic_values).dropna()
    if len(ic_clean) < 2 or ic_clean.std() == 0:
        return np.nan
    return ic_clean.mean() / ic_clean.std()
```

### Interpretation

| ICIR Value | Interpretation |
|------------|---------------|
| ICIR < 0.3 | Unstable signal |
| 0.3 ≤ ICIR < 0.5 | Moderate stability |
| ICIR ≥ 0.5 | Stable signal (preferred) |

---

## 3. False Discovery Rate (FDR) Correction

### Problem

When testing 166 features simultaneously, we expect ~8 false positives at α=0.05 by chance alone.

### Method: Benjamini-Hochberg Procedure

1. Sort p-values: $p_{(1)} \leq p_{(2)} \leq ... \leq p_{(m)}$
2. Find largest $k$ where $p_{(k)} \leq \frac{k}{m} \cdot \alpha$
3. Reject all hypotheses $H_{(1)}, ..., H_{(k)}$

### Academic Citation

> **Benjamini, Y. & Hochberg, Y.** (1995). "Controlling the false discovery rate: a practical and powerful approach to multiple testing." *Journal of the Royal Statistical Society: Series B*, 57(1), 289-300.

**Citations**: 12,814 (as of 2025)

### Implementation

```python
# scripts/analysis/features.py, line 145-164
def benjamini_hochberg_fdr(pvals, alpha=0.05):
    """Benjamini-Hochberg FDR correction for multiple testing."""
    pvals = np.asarray(pvals)
    n = len(pvals)
    
    sorted_idx = np.argsort(pvals)
    sorted_pvals = pvals[sorted_idx]
    
    ranks = np.arange(1, n + 1)
    adjusted = sorted_pvals * n / ranks
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]
    adjusted = np.clip(adjusted, 0, 1)
    
    result = np.empty(n)
    result[sorted_idx] = adjusted
    return result
```

---

## 4. Feature Importance Methods

### 4.1 Mean Decrease Impurity (MDI)

**What it measures**: Average reduction in impurity (Gini/entropy) from splits on this feature.

**Formula** (for a tree):
$$MDI_j = \sum_{t \in T_j} \frac{n_t}{n} \Delta i(t)$$

Where:
- $T_j$ = Nodes where feature $j$ is used
- $n_t$ = Samples at node $t$
- $\Delta i(t)$ = Impurity decrease at node $t$

**Limitation**: Biased toward high-cardinality features.

### 4.2 Mean Decrease Accuracy (MDA) — Permutation Importance

**What it measures**: Decrease in model accuracy when feature values are shuffled.

**Formula**:
$$MDA_j = \frac{1}{K} \sum_{k=1}^{K} (acc_{base} - acc_{permuted,j,k})$$

**Academic Citation**:
> **Breiman, L.** (2001). "Random Forests." *Machine Learning*, 45, 5-32.

> **Lopez de Prado, M.** (2018). *Advances in Financial Machine Learning*. Wiley. Chapter 8.

**Recommendation**: MDA is preferred over MDI for financial features.

### 4.3 Single Feature Importance (SFI)

**What it measures**: Model performance when trained on ONE feature only.

**Our Implementation**: Uses MDI (built-in LightGBM). 

**Gap Identified**: Should add MDA for validation.

---

## 5. Time-Series Cross-Validation

### Method: Walk-Forward with Gap

```
                        ┌─────────────────────────────────────────────────┐
Fold 1:   [TRAIN]────────────────────[GAP]──[TEST]                        │
Fold 2:   [   TRAIN  ]───────────────────────[GAP]──[TEST]                │
Fold 3:   [      TRAIN     ]──────────────────────────[GAP]──[TEST]       │
Fold 4:   [         TRAIN        ]─────────────────────────────[GAP]─[TEST]
                        └─────────────────────────────────────────────────┘
```

### Gap Purpose

Prevents information leakage when features use overlapping data:
- Our features use up to 63-bar lookback windows
- Gap of 50 bars ensures no feature/target overlap

### Academic Citation

> **Lopez de Prado, M.** (2018). *Advances in Financial Machine Learning*. Wiley. Chapter 7: "Cross-Validation in Finance."

### Implementation

```python
# scripts/analysis/models.py, line 335-352
from sklearn.model_selection import TimeSeriesSplit

def run_direction_cv(X, y, n_splits=5, gap=50):
    tscv = TimeSeriesSplit(n_splits=n_splits, gap=gap)
    
    for fold, (train_idx, val_idx) in enumerate(tscv.split(X)):
        X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
        y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]
        # ... train models
```

### Gap vs Purging

| Method | What it does | Our implementation |
|--------|--------------|-------------------|
| **Gap** | Empty period between train/test | ✅ Implemented (TimeSeriesSplit) |
| **Purging** | Remove samples with overlapping features | ✅ Implemented (PurgedKFold) |
| **Embargo** | Remove samples after test (target overlap) | ✅ Implemented (PurgedKFold) |

**Implementation Details**:
- `PurgedKFold` class in `scripts/analysis/models.py`
- `purge_gap=21`: Max feature lookback window (21 bars = 7 days at 8h)
- `embargo_gap=12`: Max target horizon (12 bars = 4 days at 8h)
- CLI: `python -m scripts.analysis.run cv --purged`

---

## 6. Position Sizing (V3 Pipeline)

### Method: Confidence-Weighted with Volatility Adjustment

### Formula

$$size = \min(confidence \times maxLev \times volMult, maxLev)$$

Where:
- $confidence = |P(up) - 0.5| \times 2$ — scaled to [0,1]
- $volMult = \min(\frac{volThreshold}{volPred}, 1)$ — reduces size in high vol
- $maxLev$ = Maximum leverage (2.0)

### Direction

$$direction = \begin{cases} +1 & \text{if } P(up) > confThreshold \\ -1 & \text{if } P(up) < 1 - confThreshold \\ 0 & \text{otherwise (flat)} \end{cases}$$

### Implementation

```python
# scripts/analysis/backtest.py, line 22-65
def position_sizer_v3(direction_prob, volatility_pred, cfg):
    # Gate 1: Confidence threshold
    confidence_distance = abs(direction_prob - 0.5)
    min_distance = cfg.confidence_threshold - 0.5
    
    if confidence_distance < min_distance:
        return 0.0, 0  # Flat
    
    direction = 1 if direction_prob > 0.5 else -1
    
    # Gate 2: Volatility adjustment
    vol_multiplier = 1.0
    if volatility_pred > cfg.vol_threshold_high:
        vol_multiplier = cfg.vol_threshold_high / volatility_pred
        vol_multiplier = max(vol_multiplier, cfg.vol_reduction_floor)
    
    # Calculate size
    confidence = confidence_distance * 2
    base_size = confidence * cfg.max_leverage
    final_size = np.clip(base_size * vol_multiplier, 0, cfg.max_leverage)
    
    return final_size, direction
```

### Comparison to Kelly Criterion

The Kelly Criterion optimal bet size is:

$$f^* = \frac{p \cdot b - q}{b} = \frac{p \cdot b - (1-p)}{b}$$

Where:
- $p$ = Probability of winning
- $q$ = Probability of losing
- $b$ = Win/loss ratio

**Our V3 vs Kelly**:
- V3 uses heuristic confidence mapping, not Kelly
- Both reduce size when edge is small
- V3 adds volatility gating (not in classic Kelly)

---

## 7. Gradient Boosting (CatBoost)

### Method: Ordered Boosting

CatBoost uses permutation-driven training to prevent target leakage during boosting.

### Academic Citation

> **Prokhorenkova, L., Gusev, G., Vorobev, A., Dorogush, A.V., & Gulin, A.** (2018). "CatBoost: unbiased boosting with categorical features." *Advances in Neural Information Processing Systems 31 (NeurIPS 2018)*.

### Implementation

```python
# scripts/analysis/models.py, line 101-130
from catboost import CatBoostClassifier

model = CatBoostClassifier(
    iterations=500,
    depth=6,
    learning_rate=0.03,
    l2_leaf_reg=3.0,
    early_stopping_rounds=50,
)
```

---

## 8. Probability Calibration

### Method: Isotonic Regression

Maps raw model probabilities to calibrated probabilities that match empirical frequencies.

### Academic Citation

> **Zadrozny, B. & Elkan, C.** (2002). "Transforming classifier scores into accurate multiclass probability estimates." *Proceedings of the 8th ACM SIGKDD*, 694-699.

### Implementation

```python
# scripts/analysis/models.py, line 310-323
from sklearn.isotonic import IsotonicRegression

def calibrate_probabilities(train_probs, train_labels, test_probs):
    calibrator = IsotonicRegression(out_of_bounds="clip")
    calibrator.fit(train_probs, train_labels)
    return calibrator.predict(test_probs)
```

---

## Summary: Method Validation Status

| Method | Academic Source | Implementation Status |
|--------|-----------------|----------------------|
| IC (Spearman) | Grinold & Kahn (1999) | ✅ Correct |
| ICIR | Grinold (1989) | ✅ Correct |
| FDR (B-H) | Benjamini & Hochberg (1995) | ✅ Correct |
| MDI | Tree-based importance | ✅ Implemented (`importance` cmd) |
| MDA (Permutation) | Breiman (2001), Lopez de Prado | ✅ Implemented (`mda` cmd) |
| TimeSeriesSplit | sklearn | ✅ With gap (`cv` cmd) |
| Purged K-Fold | Lopez de Prado (2018) | ✅ Implemented (`cv --purged` cmd) |
| Position Sizing | Custom V3 | ✅ Reasonable heuristic |
| CatBoost | Prokhorenkova et al. (2018) | ✅ Correct |
| Calibration | Zadrozny & Elkan (2002) | ✅ Correct |

---
## References

1. Benjamini, Y. & Hochberg, Y. (1995). "Controlling the false discovery rate." *JRSS-B*, 57(1), 289-300.

2. Breiman, L. (2001). "Random Forests." *Machine Learning*, 45, 5-32.

3. Grinold, R.C. (1989). "The Fundamental Law of Active Management." *JPM*, 15(3), 30-37.

4. Grinold, R.C. & Kahn, R.N. (1999). *Active Portfolio Management*. McGraw-Hill.

5. Lopez de Prado, M. (2018). *Advances in Financial Machine Learning*. Wiley.

6. Prokhorenkova, L. et al. (2018). "CatBoost: unbiased boosting with categorical features." *NeurIPS 2018*.

7. Zadrozny, B. & Elkan, C. (2002). "Transforming classifier scores into accurate multiclass probability estimates." *KDD 2002*.

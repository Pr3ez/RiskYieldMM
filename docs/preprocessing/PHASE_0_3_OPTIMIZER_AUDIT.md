# Phase 0.3: Optimizer Audit Report

**Date**: 2025-12-24
**Status**: COMPLETE ✅

---

## Summary

| Optimizer | Causal | Leakage Risk | Verdict |
|-----------|--------|--------------|---------|
| WinsorizeOptimizer | ✅ YES | NONE | ✅ SAFE |
| RollingZScoreOptimizer | ✅ YES | NONE | ✅ SAFE |
| InteractionOptimizer | ✅ YES | NONE | ✅ SAFE |
| RegimeConditioningOptimizer | ✅ YES | NONE | ✅ SAFE |
| DomainPCAOptimizer | ❌ DEPRECATED | N/A | ✅ REMOVED |

**Result**: All active optimizers are already causal. No fixes needed.

---

## 0.3.1 WinsorizeOptimizer — ✅ SAFE

**File**: `scripts/analysis/optimizers/winsorize.py`

### Fit Method
```python
# Line 63-80: Only identifies which columns to clip
# Does NOT store any bounds
self._cols_to_clip.append(col)
```
**Analysis**: Stores column list only, no statistics.

### Transform Method
```python
# Line 102-112: Uses EXPANDING quantiles with shift(1)
expanding_lower = (
    series.expanding(min_periods=self.min_periods)
    .quantile(self.lower)
    .shift(1)  # Use only past data ✅
)
expanding_upper = (
    series.expanding(min_periods=self.min_periods)
    .quantile(self.upper)
    .shift(1)  # Use only past data ✅
)
result[col] = series.clip(lower=expanding_lower, upper=expanding_upper)
```
**Analysis**: 
- Uses `.expanding().quantile().shift(1)`
- At row N, quantile is computed from rows 0..N-1
- **Causal guaranteed** ✅

### Verdict: ✅ SAFE — No leakage

---

## 0.3.2 RollingZScoreOptimizer — ✅ SAFE

**File**: `scripts/analysis/optimizers/rolling_zscore.py`

### Fit Method
```python
# Line 67-77: Only identifies columns to transform
# No statistics stored
self._cols_to_transform.append(col)
```
**Analysis**: Stores column list only, no statistics.

### Transform Method
```python
# Line 95-107: Uses ROLLING mean/std
rolling_mean = series.rolling(
    window=self.window, min_periods=self.min_periods
).mean()
rolling_std = series.rolling(
    window=self.window, min_periods=self.min_periods
).std()
result[col] = (series - rolling_mean) / rolling_std
```
**Analysis**:
- Uses `.rolling(window)` with specified window
- At row N, stats computed from rows N-window..N (only past)
- **No future data used** ✅

### Note on Rolling vs Expanding
- Rolling: Fixed window, more recent data weighted equally
- Expanding: Growing window, adapts to full history
- **Both are causal** — neither uses future data

### Verdict: ✅ SAFE — No leakage

---

## 0.3.3 InteractionOptimizer — ✅ SAFE

**File**: `scripts/analysis/optimizers/interactions.py`

### Fit Method (Selection)
```python
# Line 155-156: Uses global mean/std for IC calculation
x1 = (X[f1] - X[f1].mean()) / (X[f1].std() + 1e-10)
x2 = (X[f2] - X[f2].mean()) / (X[f2].std() + 1e-10)
interaction = x1 * x2
# Then computes IC to select interactions
```
**Analysis**:
- Global mean/std used **only for feature selection** during fit
- This happens on L1 training data (historical)
- Doesn't leak into transform output
- **Acceptable** — selection bias is minimal since:
  1. L1 data is strictly before L2 data
  2. We're just deciding which pairs to combine
  3. Actual transform uses causal stats

### Transform Method (Production)
```python
# Line 204-217: Uses EXPANDING mean/std with shift(1)
expanding_mean_1 = (
    X[f1].expanding(min_periods=self.min_periods).mean().shift(1)  # ✅
)
expanding_std_1 = (
    X[f1].expanding(min_periods=self.min_periods).std().shift(1)   # ✅
)
# ... same for f2
x1 = (X[f1] - expanding_mean_1) / (expanding_std_1 + 1e-10)
x2 = (X[f2] - expanding_mean_2) / (expanding_std_2 + 1e-10)
result[name] = x1 * x2
```
**Analysis**:
- Uses `.expanding().mean().shift(1)` and `.expanding().std().shift(1)`
- At row N, stats computed from rows 0..N-1
- **Causal guaranteed** ✅

### Verdict: ✅ SAFE — No leakage in transform

---

## 0.3.4 RegimeConditioningOptimizer — ✅ SAFE

**File**: `scripts/analysis/optimizers/regime_conditioning.py`

### Fit Method
```python
# Line 85-91: Uses FIXED theoretical threshold
if self.regime_threshold is None:
    self._regime_median = 0.5  # Theoretical boundary, not data-dependent ✅
else:
    self._regime_median = self.regime_threshold
```
**Analysis**:
- Uses fixed Hurst threshold of 0.5 (theoretical boundary)
- **No data-dependent threshold** — no leakage
- H > 0.5 = trending, H < 0.5 = mean-reverting (standard interpretation)

### IC Computation in Fit
```python
# Line 118-123: Computes IC per regime
ic_trend, _ = stats.spearmanr(x_vals[mask_t], y_vals[mask_t])
ic_revert, _ = stats.spearmanr(x_vals[mask_r], y_vals[mask_r])
```
**Analysis**:
- IC computed on training data only
- Used to decide which features to condition
- **Selection on historical data is acceptable**

### Transform Method
```python
# Uses regime mask from current Hurst value
# No global statistics — just regime-dependent weights
```
**Analysis**:
- Weights learned during fit (on L1 data)
- Applied based on current Hurst (point-in-time)
- **No future data leakage** ✅

### Verdict: ✅ SAFE — Fixed threshold prevents leakage

---

## 0.3.5 DomainPCAOptimizer — ✅ DEPRECATED

**File**: `_domain_pca_DEPRECATED.py`

**Status**: Already removed from active optimizers (see `docs/LEAKAGE_FIXES.md`)

**Reason for deprecation**:
- PCA requires global covariance matrix
- Cannot be made causal without significant approximation
- Online PCA methods exist but add complexity

**Decision**: Removed rather than fixed. Other optimizers provide sufficient feature improvement.

---

## Summary of Optimizer Causal Patterns

| Pattern | Used In | How It Works |
|---------|---------|--------------|
| `expanding().X().shift(1)` | Winsorize, Interactions | Computes stat from rows 0..N-1 for row N |
| `rolling(window).X()` | RollingZScore | Computes stat from rows N-window..N |
| Fixed threshold | RegimeConditioning | Uses theoretical value (0.5 for Hurst) |
| Selection on L1 only | Interactions, Regime | Feature selection uses training data |

---

## Recommendations for Phase 2

### Already Usable
1. **WinsorizeOptimizer**: Can be used directly with expanding quantiles
2. **RollingZScoreOptimizer**: Can be used directly for returns/momentum features
3. **InteractionOptimizer**: Can be used directly (transform is causal)

### Need New Implementation
For the 20-workflow system, we need:
1. **ExpandingZScoreScaler**: Like RollingZScore but expanding (for volatility targets)
2. **ExpandingRankTransformer**: Maps to [0,1] percentile (for classification targets)
3. **LogTransformer**: Stateless log transform (for right-skewed volatility features)

These don't exist yet but follow the same causal patterns.

---

## Phase 0.3 Completion Checklist

- [x] 0.3.1 Review WinsorizeOptimizer — is it truly causal?
- [x] 0.3.2 Review RollingZScoreOptimizer — correct window usage?
- [x] 0.3.3 Review InteractionOptimizer — any leakage in IC computation?
- [x] 0.3.4 Review RegimeConditioningOptimizer — safe thresholds?
- [x] 0.3.5 Document what's usable vs what needs fixing

**Key Finding**: All 4 active optimizers are already causal ✅

**Status**: COMPLETE ✅

**Next**: Phase 0.4 — Audit AlignedDualEngine data flow

# Future Leakage Fixes in Feature Optimization Pipeline

**Date:** 2025-12-22  
**Issue:** Multiple optimizers were using future data during transformation  
**Impact:** All affected optimizers now use strictly causal (expanding window) computations

---

## Executive Summary

During a code audit, we discovered that 4 out of 5 feature optimizers were computing statistics using **all data** (including future values), which constitutes **look-ahead bias** or **future leakage**. This would cause artificially inflated backtesting performance that wouldn't replicate in live trading.

### Severity Assessment

| Optimizer | Leakage Type | Severity | Resolution |
|-----------|--------------|----------|------------|
| WinsorizeOptimizer | Global quantiles | 🔴 HIGH | Fixed - expanding quantiles |
| InteractionOptimizer | Global mean/std | 🔴 HIGH | Fixed - expanding mean/std |
| DomainPCAOptimizer | PCA.fit() on full data | 🔴 CRITICAL | **REMOVED** |
| RegimeConditioningOptimizer | Global median | 🟡 MEDIUM | Fixed - theoretical threshold |
| RollingZScoreOptimizer | — | ✅ SAFE | No changes needed |

---

## Detailed Analysis

### 1. WinsorizeOptimizer (FIXED)

**Location:** `scripts/analysis/optimizers/winsorize.py`

**Leaking Code (lines 76-77):**
```python
lower_bound = col_data.quantile(self.lower)
upper_bound = col_data.quantile(self.upper)
```

**Problem:** Computing quantiles across the entire column uses future values to determine clipping bounds.

**Fix Applied:**
```python
# Causal expanding quantile with shift to prevent leakage
lower_exp = col_series.expanding(min_periods=self.min_periods).quantile(self.lower).shift(1)
upper_exp = col_series.expanding(min_periods=self.min_periods).quantile(self.upper).shift(1)
```

**Parameters:**
- `min_periods=252` (default): ~84 days of 8h bars for stable quantile estimates
- `shift(1)`: Ensures row N only uses data from rows 0..N-1

---

### 2. InteractionOptimizer (FIXED)

**Location:** `scripts/analysis/optimizers/interactions.py`

**Leaking Code (lines 148-149, 168-169):**
```python
# During fit:
self._feature_means[col] = X[col].mean()
self._feature_stds[col] = X[col].std()

# During transform:
mean = self._feature_means.get(col, 0)
std = self._feature_stds.get(col, 1)
```

**Problem:** Computing mean/std during fit() uses future data when fit_transform() is called on full dataset.

**Fix Applied:**
```python
# Causal expanding mean/std with shift
mean_exp = col_series.expanding(min_periods=self.min_periods).mean().shift(1)
std_exp = col_series.expanding(min_periods=self.min_periods).std().shift(1).replace(0, 1)
standardized = (col_series - mean_exp) / std_exp
```

**Parameters:**
- `min_periods=126` (default): ~42 days for stable mean/std estimates
- Removed `_feature_means` and `_feature_stds` storage (no longer needed)

---

### 3. DomainPCAOptimizer (REMOVED)

**Location:** `scripts/analysis/optimizers/domain_pca.py` → **RENAMED TO `_domain_pca_DEPRECATED.py`**

**Leaking Code (lines 146, 151):**
```python
X_scaled = self._scaler.fit_transform(X_domain)  # Uses future
pca.fit(X_scaled)  # PCA needs full covariance matrix
```

**Problem:** PCA fundamentally requires computing the covariance matrix across all samples. The covariance matrix is:
```
Cov(X) = (1/n) * Σᵢ (xᵢ - μ)(xᵢ - μ)ᵀ
```
This sum includes ALL rows, making it impossible to compute causally.

**Why PCA Cannot Be Made Causal:**
1. Eigenvector computation requires the full covariance matrix
2. Incremental PCA still uses a batch of future data
3. Online PCA algorithms change components over time, causing non-stationarity

**Resolution:** DomainPCAOptimizer has been **completely removed** from the pipeline:
- Removed from `__init__.py` exports
- Removed from `run.py` pipeline definitions
- File renamed to `_domain_pca_DEPRECATED.py`
- "pca" pipeline option removed from CLI

---

### 4. RegimeConditioningOptimizer (FIXED)

**Location:** `scripts/analysis/optimizers/regime_conditioning.py`

**Leaking Code (line 85):**
```python
hurst_threshold = np.nanmedian(hurst)
```

**Problem:** Computing median Hurst across all data uses future values to determine the regime threshold.

**Fix Applied:**
```python
# Fixed threshold based on Hurst exponent theory
# H > 0.5: trending/persistent, H < 0.5: mean-reverting
# Using theoretical boundary eliminates data dependency
hurst_threshold = 0.5
```

**Rationale:**
- Hurst exponent theory defines H=0.5 as the boundary between trending (H>0.5) and mean-reverting (H<0.5) behavior
- This is a **domain knowledge constant**, not a data-derived statistic
- Eliminates all future leakage while preserving regime detection functionality

---

### 5. RollingZScoreOptimizer (ALREADY SAFE)

**Location:** `scripts/analysis/optimizers/rolling_zscore.py`

**Code (lines 68-69):**
```python
rolling_mean = col_data.rolling(window=self.window, min_periods=self.min_periods).mean()
rolling_std = col_data.rolling(window=self.window, min_periods=self.min_periods).std()
```

**Why It's Safe:**
- `rolling()` is inherently backward-looking
- Each row N uses only rows (N-window)..N
- No future data is accessed

---

## Pipeline Impact

### Before Fix
```
Pipelines available: default, pca, regime, all
```

### After Fix
```
Pipelines available: default, regime, all
(pca pipeline removed - DomainPCAOptimizer caused future leakage)
```

---

## Warmup Period

All causal optimizers now have a **warmup period** controlled by `min_periods`:

| Optimizer | min_periods | Warmup (8h bars) | Warmup (days) |
|-----------|-------------|------------------|---------------|
| WinsorizeOptimizer | 252 | 252 | ~84 days |
| InteractionOptimizer | 126 | 126 | ~42 days |
| RollingZScoreOptimizer | window//4 | 63 | ~21 days |

During the warmup period, outputs are `NaN`. This is **correct behavior** — we cannot compute reliable statistics without sufficient historical data.

---

## Verification

To verify the fixes work correctly:

```bash
# Run tests
python -m pytest tests/test_optimizers.py -v

# Re-run all optimizations
for target in direction returns volatility vol_regime trend_regime; do
  for horizon in 1 3 6 12; do
    python -m scripts.analysis.run optimize --target $target --horizon $horizon
  done
done

# Rebuild datasets
python -m scripts.analysis.run build-datasets
```

---

## Key Principle

**At row N, only use data from rows 0..N-1.**

This is enforced via:
1. `expanding().stat().shift(1)` — Uses all past data, shifted by one row
2. `rolling(window).stat()` — Uses only recent past data
3. Domain knowledge constants — No data dependency at all

---

## References

- [Look-Ahead Bias in Backtesting](https://www.investopedia.com/terms/l/lookaheadbias.asp)
- [Hurst Exponent Theory](https://en.wikipedia.org/wiki/Hurst_exponent)
- [Online/Incremental PCA Limitations](https://scikit-learn.org/stable/modules/decomposition.html#incremental-pca)

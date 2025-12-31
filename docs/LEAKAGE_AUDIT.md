# Data Leakage Audit

**Question:** Is there accidental future data leakage in scaling or feature computation?

---

## ✅ SAFE (No Leakage)

### 1. Model Training Scaler (`ensemble.py`)
```python
# fit_transform on TRAINING data only
X_scaled = self._scaler.fit_transform(X_train)

# transform (not fit) on validation/test  
X_val_scaled = self._scaler.transform(X_val)
```
**Verdict:** ✅ SAFE - Scaler learns parameters from training set only, applies to future data.

### 2. Rolling Features (`compute_features.py`)
```python
rolling_vol = log_returns.rolling(n).std()  # Uses past n bars only
sma_21 = close.rolling_mean(21)             # Uses past 21 bars only
```
**Verdict:** ✅ SAFE - `rolling()` looks backward by default in pandas/polars.

### 3. Expanding Features (`compute_features.py`)
```python
# Within a ROLLING window (safe)
def rolling_max_dd(window):
    peak = window.expanding().max()  # Expanding within the window
```
**Verdict:** ✅ SAFE - This is expanding within a rolling window, not full dataset.

### 4. Interaction Features (`optimizers/interactions.py`)
```python
# Uses shift(1) to exclude current row
expanding_mean_1 = X[f1].expanding(min_periods=252).mean().shift(1)
expanding_std_1 = X[f1].expanding(min_periods=252).std().shift(1)
```
**Verdict:** ✅ SAFE - Explicit `.shift(1)` ensures only past data used.

### 5. GARCH Regime Thresholds (`helpers/garch.py`)
```python
# Computed during fit() on TRAINING data only
cond_vol = self._compute_conditional_vol(returns)  # training returns
self._regime_low_thresh = np.nanpercentile(cond_vol, self.config.regime_low_pct)
```
**Verdict:** ✅ SAFE - Percentiles computed from training data only.

### 6. CQR Conformity Scores (`calibration/cqr.py`)
```python
# Computed on CALIBRATION set (after training)
self.conformity_scores = ...  # from calibration set
q_adjust = np.quantile(self.conformity_scores, quantile_level)
```
**Verdict:** ✅ SAFE - Scores from calibration set, applied to future test data.

---

## ⚠️ POTENTIAL LEAKAGE POINTS

### 1. Volatility Regime Labels (`data.py:163-164`) ⚠️

```python
# PROBLEM: Computes quantiles on ENTIRE dataset including future!
vol_25 = df["rolling_vol_21"].quantile(0.25)  # Uses ALL rows
vol_75 = df["rolling_vol_21"].quantile(0.75)  # Uses ALL rows

y_vol_regime = (
    pl.when(df["rolling_vol_21"] < vol_25).then(0)
    .when(df["rolling_vol_21"] < vol_75).then(1)
    .otherwise(2)
)
```

**Issue:** The 25th/75th percentile thresholds are computed on the FULL dataset. This means:
- When predicting at time T, we know the volatility distribution of T+1, T+2, etc.
- In live trading, we won't know future vol distribution

**Severity:** MEDIUM
- This affects `y_vol_regime` labels (a TARGET, not a feature)
- Used for regime filtering, not direct prediction
- The underlying `rolling_vol_21` feature is safe (rolling lookback)

**Fix Required:**
```python
# Option 1: Use expanding quantile (only past data)
vol_25 = df["rolling_vol_21"].expanding().quantile(0.25).shift(1)
vol_75 = df["rolling_vol_21"].expanding().quantile(0.75).shift(1)

# Option 2: Use fixed historical thresholds (e.g., from first 1000 bars)
# This is what we'd do in production anyway
```

### 2. Similar Issue in `run.py` (Lines 616-617, 811-812, 1091)

Same pattern - computing quantiles on full rolling_vol.

---

## 🔍 IMPLEMENTATION PLAN ADDITIONS NEEDED

For our new features:

### Derivatives Features (NEW)
Must use EXPANDING or ROLLING for z-scores:
```python
# WRONG (leakage):
zscore = (funding_rate - funding_rate.mean()) / funding_rate.std()

# RIGHT (no leakage):
rolling_mean = funding_rate.rolling(21).mean()
rolling_std = funding_rate.rolling(21).std()
zscore = (funding_rate - rolling_mean) / rolling_std
```

### Triple-Barrier Labels (NEW)
Uses future prices by design (it's a TARGET):
- TP/SL hit detection requires seeing future highs/lows
- This is acceptable - targets ARE supposed to use future data
- Key: Features must NOT use future data

### Sample Uniqueness (NEW)
Must compute concurrency using only known labels:
```python
# In training: Use expanding window of known outcomes
# At row T, only count overlaps with rows 0..T-1
```

### Fractional Differentiation (NEW)
Uses filter weights on PAST values only:
```python
# fracdiff(x, d) at time T uses x[T], x[T-1], x[T-2], ...
# No future values - SAFE by design
```

---

## ✅ RECOMMENDATIONS

### Immediate Fix (Before Implementation)

1. **Fix `y_vol_regime` in `data.py`:**
   - Replace full-dataset quantile with expanding quantile
   - Or use fixed historical thresholds

2. **Fix `run.py` vol_regime computation:**
   - Same pattern, same fix needed

### Guidelines for New Features

1. **Never use `.mean()`, `.std()`, `.quantile()` without window:**
   ```python
   # BAD: Uses all data
   df['feature'].mean()
   
   # GOOD: Uses rolling window
   df['feature'].rolling(21).mean()
   
   # GOOD: Uses expanding (all PAST data)
   df['feature'].expanding().mean().shift(1)
   ```

2. **Always shift(1) expanding statistics:**
   ```python
   # The expanding mean at row T should not include row T
   expanding_mean = series.expanding().mean().shift(1)
   ```

3. **Test with `timeseries_validation.py`:**
   ```bash
   python -m scripts.feature_engineering.timeseries_validation
   ```
   This module already exists and checks for leakage!

---

## 📊 Summary

| Component | Status | Risk |
|-----------|--------|------|
| Model scaler | ✅ Safe | None |
| Rolling features | ✅ Safe | None |
| Interaction features | ✅ Safe | None |
| GARCH thresholds | ✅ Safe | None |
| CQR calibration | ✅ Safe | None |
| **y_vol_regime labels** | ⚠️ **LEAKAGE** | Medium |
| run.py regime | ⚠️ **LEAKAGE** | Medium |

**Overall Assessment:** The feature pipeline is well-designed with proper temporal handling. One issue in `y_vol_regime` label computation needs fixing before production.

---

*Audit completed: 2025-12-31*
*Per aspera ad astra*

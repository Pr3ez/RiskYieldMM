# Phase 0.1: Helper Feature Audit Report

**Date**: 2025-12-24
**Status**: COMPLETE ✅

---

## Summary

| Metric | Value |
|--------|-------|
| **Total Helper Features** | 58 |
| **Helpers Audited** | 6 (IF, CUSUM, GARCH, HMM4, HMM5, Kalman) |
| **Leakage Found** | ❌ **YES - 5 issues identified** |
| **Safe Features** | 40/58 (69%) |
| **Needs Fix** | 18/58 (31%) |

---

## 0.1.1 Complete Feature List (58 features)

### Isolation Forest (12 features)
| # | Feature | Type | Leakage Risk |
|---|---------|------|--------------|
| 1 | `H_vol_1_if_extreme_score` | float | ⚠️ MODERATE |
| 2 | `H_vol_1_if_extreme_is` | binary | ⚠️ MODERATE |
| 3 | `H_vol_1_if_extreme_severity` | float [0,1] | ⚠️ MODERATE |
| 4 | `H_vol_1_if_moderate_score` | float | ⚠️ MODERATE |
| 5 | `H_vol_1_if_moderate_is` | binary | ⚠️ MODERATE |
| 6 | `H_vol_1_if_moderate_severity` | float [0,1] | ⚠️ MODERATE |
| 7 | `H_vol_1_if_mild_score` | float | ⚠️ MODERATE |
| 8 | `H_vol_1_if_mild_is` | binary | ⚠️ MODERATE |
| 9 | `H_vol_1_if_mild_severity` | float [0,1] | ⚠️ MODERATE |
| 10 | `H_vol_1_if_mean_score` | float | ⚠️ MODERATE |
| 11 | `H_vol_1_if_max_severity` | float [0,1] | ⚠️ MODERATE |
| 12 | `H_vol_1_if_n_anomalies` | int [0,3] | ⚠️ MODERATE |

### CUSUM (12 features)
| # | Feature | Type | Leakage Risk |
|---|---------|------|--------------|
| 13 | `H_vol_1_cusum_ret_pos` | float | ⚠️ HIGH |
| 14 | `H_vol_1_cusum_ret_neg` | float | ⚠️ HIGH |
| 15 | `H_vol_1_cusum_vol_pos` | float | ⚠️ HIGH |
| 16 | `H_vol_1_cusum_vol_neg` | float | ⚠️ HIGH |
| 17 | `H_vol_1_cp_ret_up` | binary | ✅ LOW |
| 18 | `H_vol_1_cp_ret_down` | binary | ✅ LOW |
| 19 | `H_vol_1_cp_vol_up` | binary | ✅ LOW |
| 20 | `H_vol_1_cp_vol_down` | binary | ✅ LOW |
| 21 | `H_vol_1_cp_any` | binary | ✅ LOW |
| 22 | `H_vol_1_cp_magnitude` | float | ⚠️ HIGH |
| 23 | `H_vol_1_days_since_cp` | int | ✅ LOW |
| 24 | `H_vol_1_cp_count_21` | int [0,21] | ✅ LOW |

### GARCH (8 features)
| # | Feature | Type | Leakage Risk |
|---|---------|------|--------------|
| 25 | `H_vol_1_garch_cond_vol` | float | ✅ LOW |
| 26 | `H_vol_1_garch_vol_forecast` | float | ✅ LOW |
| 27 | `H_vol_1_garch_vol_zscore` | float | ⚠️ MODERATE |
| 28 | `H_vol_1_garch_vol_shock` | float | ✅ LOW |
| 29 | `H_vol_1_garch_persistence` | float [0,1] | ✅ LOW |
| 30 | `H_vol_1_garch_vol_regime` | int [0,2] | ⚠️ MODERATE |
| 31 | `H_vol_1_garch_vol_change` | float | ✅ LOW |
| 32 | `H_vol_1_garch_vol_ratio` | float | ✅ LOW |

### HMM-4 Market Regime (9 features)
| # | Feature | Type | Leakage Risk |
|---|---------|------|--------------|
| 33 | `H_volatility_1_hmm4_prob_bullish` | float [0,1] | ⚠️ MODERATE |
| 34 | `H_volatility_1_hmm4_prob_bearish` | float [0,1] | ⚠️ MODERATE |
| 35 | `H_volatility_1_hmm4_prob_neutral` | float [0,1] | ⚠️ MODERATE |
| 36 | `H_volatility_1_hmm4_prob_volatile` | float [0,1] | ⚠️ MODERATE |
| 37 | `H_volatility_1_hmm4_state` | int [0,3] | ⚠️ MODERATE |
| 38 | `H_volatility_1_hmm4_entropy` | float | ✅ LOW |
| 39 | `H_volatility_1_hmm4_confidence` | float [0,1] | ✅ LOW |
| 40 | `H_volatility_1_hmm4_duration` | int | ✅ LOW |
| 41 | `H_volatility_1_hmm4_change` | binary | ✅ LOW |

### HMM-5 Volatility Regime (10 features)
| # | Feature | Type | Leakage Risk |
|---|---------|------|--------------|
| 42 | `H_volatility_1_hmm5_prob_very_low` | float [0,1] | ⚠️ MODERATE |
| 43 | `H_volatility_1_hmm5_prob_low` | float [0,1] | ⚠️ MODERATE |
| 44 | `H_volatility_1_hmm5_prob_medium` | float [0,1] | ⚠️ MODERATE |
| 45 | `H_volatility_1_hmm5_prob_high` | float [0,1] | ⚠️ MODERATE |
| 46 | `H_volatility_1_hmm5_prob_very_high` | float [0,1] | ⚠️ MODERATE |
| 47 | `H_volatility_1_hmm5_state` | int [0,4] | ⚠️ MODERATE |
| 48 | `H_volatility_1_hmm5_entropy` | float | ✅ LOW |
| 49 | `H_volatility_1_hmm5_confidence` | float [0,1] | ✅ LOW |
| 50 | `H_volatility_1_hmm5_duration` | int | ✅ LOW |
| 51 | `H_volatility_1_hmm5_change` | binary | ✅ LOW |

### Kalman (7 features)
| # | Feature | Type | Leakage Risk |
|---|---------|------|--------------|
| 52 | `H_volatility_1_kalman_filtered_dev` | float | ✅ LOW |
| 53 | `H_volatility_1_kalman_velocity` | float | ✅ LOW |
| 54 | `H_volatility_1_kalman_acceleration` | float | ✅ LOW |
| 55 | `H_volatility_1_kalman_pred_error` | float | ✅ LOW |
| 56 | `H_volatility_1_kalman_innovation` | float | ✅ LOW |
| 57 | `H_volatility_1_kalman_zscore` | float | ⚠️ HIGH |
| 58 | `H_volatility_1_kalman_regime` | int [0,2] | ⚠️ HIGH |

---

## 0.1.2 Leakage Analysis by Helper

### 1. Isolation Forest (IF) — ⚠️ MODERATE RISK

**Fit Logic**:
```python
# isolation_forest.py line 108-119
model.fit(X)  # Fits on L1 training data
scores = model.decision_function(X)
self._score_mins[level] = float(np.min(scores))  # Global min
self._score_maxs[level] = float(np.max(scores))  # Global max
```

**Transform Logic**:
```python
# isolation_forest.py line 207-213
severity = (score_max - scores) / score_range  # Uses global min/max
```

**LEAKAGE IDENTIFIED**:
- `_score_mins` and `_score_maxs` are computed on FULL L1 training data
- When transforming L2 data, these global stats are used for severity normalization
- **This is NOT a leakage problem** because:
  - L1 data is BEFORE L2 data (no future info)
  - Stats are from L1 train, not L2 transform window

**VERDICT**: ✅ SAFE — L1 → L2 temporal separation maintained

---

### 2. CUSUM — ⚠️ **HIGH RISK - LEAKAGE FOUND**

**Fit Logic**:
```python
# cusum.py line 99-107
self._return_mean = float(np.nanmedian(returns))  # Global median
self._return_std = float(np.nanstd(returns))      # Global std
self._vol_mean = float(np.nanmedian(volatility))  # Global median
self._vol_std = float(np.nanstd(volatility))      # Global std
```

**Transform Logic**:
```python
# cusum.py line 237-242 (in _compute_cusum loop)
if window > 0 and i >= window:
    window_data = series[max(0, i - window) : i]  # Rolling uses past only ✅
    local_mean = np.nanmean(window_data)
    local_std = np.nanstd(window_data) + 1e-8
else:
    local_mean = mean  # Falls back to GLOBAL stats ⚠️
    local_std = std
```

**LEAKAGE IDENTIFIED**:
1. **Magnitude calculation (line ~180)**: Uses `self._return_mean` and `self._return_std` from global fit
   ```python
   ret_zscore = np.abs((returns - self._return_mean) / self._return_std)
   ```
   - This z-score uses GLOBAL mean/std, not causal rolling stats
   
2. **Early warmup (i < window)**: Falls back to global stats for first 63 bars

**SEVERITY**: HIGH — Magnitude feature directly uses future information when computing z-scores

**FIX REQUIRED**:
- Replace global stats with expanding window stats in transform
- Use `expanding().mean()` and `expanding().std()` with `.shift(1)`

---

### 3. GARCH — ⚠️ MODERATE RISK

**Fit Logic**:
```python
# garch.py line 179-182
self._regime_low_thresh = float(np.nanpercentile(cond_vol, self.config.regime_low_pct))
self._regime_high_thresh = float(np.nanpercentile(cond_vol, self.config.regime_high_pct))
```

**Transform Logic**:
```python
# garch.py line 251-253
vol_regime = np.ones(n_samples)  # Default MED
vol_regime[cond_vol < self._regime_low_thresh] = 0  # LOW
vol_regime[cond_vol > self._regime_high_thresh] = 2  # HIGH
```

**LEAKAGE IDENTIFIED**:
1. **Regime thresholds**: Computed from L1 training data percentiles
   - When L2 data has different distribution, thresholds may be inappropriate
   - **NOT strict leakage** — L1 data is in the past

2. **Vol z-score (line 266-278)**:
   ```python
   # _compute_vol_zscore uses rolling window internally
   ```
   - Uses rolling window → ✅ SAFE

**VERDICT**: ✅ SAFE — Regime thresholds from L1 are acceptable (no L2 future info)

---

### 4. HMM (4 and 5) — ⚠️ **MODERATE RISK - POTENTIAL LEAKAGE**

**Fit Logic**:
```python
# hmm.py line 95-102
self.model = hmm.GaussianHMM(...)
self.model.fit(obs)  # Learns transition matrix from L1 data
```

**Transform Logic**:
```python
# hmm.py line 130-140
probs = self.model.predict_proba(obs)  # Forward-backward algorithm
states = self.model.predict(obs)       # Viterbi decoding
```

**LEAKAGE IDENTIFIED**:
1. **predict_proba() uses FULL sequence**: Forward-backward algorithm sees entire L2 window
   - At time t, probability P(state_t) uses information from t+1...T
   - **This is BIDIRECTIONAL** — looks both forward and backward

2. **predict() (Viterbi) also uses FULL sequence**: 
   - Finds globally optimal state sequence
   - State at t can be influenced by future observations

**SEVERITY**: MODERATE to HIGH — HMM smoothed probabilities use future within L2 window

**FIX REQUIRED**:
- Replace `predict_proba()` with **filter** (forward only, no backward pass)
- hmmlearn doesn't expose filtering directly — need custom implementation or use `score_samples()` differently

**Academic Reference**: 
- Forward pass alone gives P(state_t | obs_1:t) — causal
- Forward-backward gives P(state_t | obs_1:T) — non-causal

---

### 5. Kalman — ⚠️ **HIGH RISK - LEAKAGE FOUND**

**Transform Logic**:
```python
# kalman.py line 221-223
inn_mean = np.mean(innovations)  # GLOBAL mean of innovations
inn_std = np.std(innovations) + 1e-10  # GLOBAL std
zscores = (innovations - inn_mean) / inn_std  # Z-score using global stats
```

```python
# kalman.py line 227
vel_zscore = (velocities - np.mean(velocities)) / (np.std(velocities) + 1e-10)
regime = np.where(vel_zscore > 1, 2, np.where(vel_zscore < -1, 0, 1))
```

**LEAKAGE IDENTIFIED**:
1. **Innovation z-score**: Computed using mean/std of ALL innovations in transform window
   - Innovation at t=0 uses mean/std computed from t=0...T
   - **Direct future information leak**

2. **Regime feature**: Computed using mean/std of ALL velocities in window
   - Velocity at t=0's regime assignment uses future velocities

**SEVERITY**: HIGH — Two features directly use future within transform window

**FIX REQUIRED**:
- Replace global mean/std with expanding or rolling stats:
  ```python
  # Causal z-score
  expanding_mean = pd.Series(innovations).expanding().mean().shift(1)
  expanding_std = pd.Series(innovations).expanding().std().shift(1)
  zscores = (innovations - expanding_mean) / (expanding_std + 1e-10)
  ```

---

## 0.1.3 Distribution Analysis

### Feature Distributions by Type

**Bounded [0,1]**:
- All severity features (3): if_extreme_severity, if_moderate_severity, if_mild_severity
- All HMM probabilities (9): hmm4_prob_*, hmm5_prob_*
- HMM confidence (2): hmm4_confidence, hmm5_confidence

**Bounded [0,N]**:
- if_n_anomalies: [0,3]
- HMM states: hmm4_state [0,3], hmm5_state [0,4]
- Kalman regime: [0,2]

**Binary**:
- All `_is` features (3): if_extreme_is, if_moderate_is, if_mild_is
- All changepoint features (5): cp_ret_up, cp_ret_down, cp_vol_up, cp_vol_down, cp_any
- HMM change (2): hmm4_change, hmm5_change

**Unbounded**:
- All score features (4): if_*_score, if_mean_score
- All CUSUM values (4): cusum_ret_pos, cusum_ret_neg, cusum_vol_pos, cusum_vol_neg
- cp_magnitude
- All GARCH features except regime
- Kalman filtered_dev, velocity, acceleration, pred_error, innovation, zscore
- HMM entropy (2)

### Recommended Preprocessing by Distribution

| Distribution | Features | Recommended Preprocessing |
|--------------|----------|---------------------------|
| Bounded [0,1] | 14 | None needed (already normalized) |
| Bounded [0,N] | 4 | None needed or OneHot if categorical |
| Binary | 10 | None needed |
| Unbounded | 30 | **ExpandingWinsorize → ExpandingZScore/Rank** |

---

## 0.1.4 Features Needing Different Preprocessing per Target

### By Task Type:

**Regression (returns, volatility)**:
- Unbounded features: ExpandingWinsorize + RollingZScore
- Bounded [0,1]: No change
- Binary: No change (or exclude)

**Classification (direction, trend_regime, vol_regime)**:
- Unbounded features: ExpandingWinsorize + ExpandingRank
- Bounded [0,1]: No change
- Binary: No change

### Feature-Specific Recommendations:

| Feature | Returns | Volatility | Direction | vol_regime | trend_regime |
|---------|---------|------------|-----------|------------|--------------|
| if_*_score | RollingZScore | RollingZScore | ExpandingRank | ExpandingRank | ExpandingRank |
| cusum_* (continuous) | RollingZScore | RollingZScore | ExpandingRank | ExpandingRank | ExpandingRank |
| garch_cond_vol | RollingZScore | Log+ExpandZScore | ExpandingRank | ExpandingRank | ExpandingRank |
| kalman_* (continuous) | RollingZScore | RollingZScore | ExpandingRank | ExpandingRank | ExpandingRank |
| All bounded/binary | None | None | None | None | None |

---

## Summary of Leakage Issues Found

| Helper | Feature | Issue | Severity | Fix |
|--------|---------|-------|----------|-----|
| CUSUM | cp_magnitude | Uses global mean/std | HIGH | Use expanding stats |
| CUSUM | Early warmup | Falls back to global stats | MODERATE | Use expanding with min_periods |
| HMM4/5 | prob_* | Forward-backward uses future | MODERATE | Use forward pass only |
| HMM4/5 | state | Viterbi uses future | MODERATE | Use filter() not smooth() |
| Kalman | zscore | Global mean/std of innovations | HIGH | Use expanding stats |
| Kalman | regime | Global mean/std of velocities | HIGH | Use expanding stats |

**Total Issues**: 5 distinct leakage patterns affecting 18 features

---

## Actionable Fixes for Phase 2

### Fix 1: CUSUM Magnitude
```python
# Replace in cusum.py line ~180
# OLD:
ret_zscore = np.abs((returns - self._return_mean) / self._return_std)

# NEW:
expanding_mean = pd.Series(returns).expanding().mean().shift(1).fillna(0)
expanding_std = pd.Series(returns).expanding().std().shift(1).fillna(1)
ret_zscore = np.abs((returns - expanding_mean.values) / (expanding_std.values + 1e-8))
```

### Fix 2: Kalman Z-Score & Regime
```python
# Replace in kalman.py line ~221
# OLD:
inn_mean = np.mean(innovations)
inn_std = np.std(innovations) + 1e-10
zscores = (innovations - inn_mean) / inn_std

# NEW:
inn_series = pd.Series(innovations)
expanding_mean = inn_series.expanding().mean().shift(1).fillna(0)
expanding_std = inn_series.expanding().std().shift(1).fillna(1)
zscores = (innovations - expanding_mean.values) / (expanding_std.values + 1e-10)
```

### Fix 3: HMM Filtering
```python
# Replace predict_proba with forward algorithm only
# This requires custom implementation since hmmlearn doesn't expose it directly

def forward_filter(model, obs):
    """Forward pass only - gives P(state_t | obs_1:t)"""
    # Implement using model.startprob_, model.transmat_, model._compute_log_likelihood
    ...
```

---

## Phase 0.1 Completion Checklist

- [x] 0.1.1 List all 58 helper features from ensemble output
- [x] 0.1.2 Check each feature for potential leakage
- [x] 0.1.3 Document feature distributions per task type
- [x] 0.1.4 Identify features that need different preprocessing per target

**Status**: COMPLETE ✅

**Next**: Phase 0.2 — Audit base features (166 features)

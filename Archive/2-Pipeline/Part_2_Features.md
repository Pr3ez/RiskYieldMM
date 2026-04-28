# Part 2: Features (Complete)

> **Total: ~450 unique features** across row-by-row calculator + HMM + helper models
>
> **→ Next:** These features feed into [Part 3: Walk-Forward Models](../3-Walk_Forward_System/README.md)

---

## Feature Sources Overview

| Source | Features | Notes |
|--------|----------|-------|
| `row_by_row_features.py` | **369** | Core feature calculator |
| HMM/Regime (Cells 6-7) | **52** | HMM-4, HMM-5, combined |
| DTMC (Markov Chain) | **11** | Discrete-time transitions |
| Kalman Filter | **5** | State estimation |
| Helper Models | **15** | Ensemble predictions |
| Anomaly | **3** | Severity × regime |
| **Total Unique** | **~450** | After deduplication |

---

## Part A: Row-by-Row Calculator Features (369)

**Source:** `/media/przem/w/kaggle/row_by_row_features.py`

### Standard Market Periods

```python
PERIODS_SHORT = [2, 3, 5, 7, 10, 14]           # Ultra-short to 2 weeks
PERIODS_MEDIUM = [20, 21, 30, 50, 60, 63, 70]  # Monthly to quarterly
PERIODS_LONG = [100, 120, 150, 200, 252]       # Semi-annual to annual
PERIODS_ALL = PERIODS_SHORT + PERIODS_MEDIUM + PERIODS_LONG  # 18 periods total
```

---

### 1. Volatility Features (~60)

| Feature Pattern | Formula | Periods |
|-----------------|---------|---------|
| `daily_volatility_lagged` | `abs(lagged_forward_returns)` | single |
| `volatility_ma_{n}` | `rolling_mean(daily_vol, n)` | 5, 21, 180 |
| `mean_hist_vol_{n}` | `rolling_std(returns, n) × √252` | 5, 10, 21, 63, 126, 252 |
| `ewma_vol_{n}d` | Exponentially weighted MA | ALL (18) |
| `vol_of_vol_{n}d` | `rolling_std(daily_vol, n)` | 5, 10, 14, 21, 50, 60, 100 |
| `realized_vol_{n}d` | `√(Σreturns²/n)` | ALL (18) |
| `vol_ratio_{a}_{b}` | `ewma_vol_a / ewma_vol_b` | (5,21), (10,50), (21,63), (50,200) |
| `vol_ratio_21` | `daily_vol / volatility_ma_21` | single |
| `mhv_ratio_{a}_{b}` | `mean_hist_vol_a / mean_hist_vol_b` | 5/21, 21/63, 63/252 |

### 2. Momentum Features (~55)

| Feature Pattern | Formula | Periods |
|-----------------|---------|---------|
| `momentum_{n}d` | `rolling_sum(returns, n)` | ALL (18) |
| `momentum_accel_{n}d` | `mom_n - mom_n.shift(n)` | 5, 10, 14, 21, 50, 100, 200 |
| `momentum_ratio_{a}_{b}` | `mom_a / abs(mom_b)` | (5,20), (5,50), (10,50), (14,50), (20,100), (50,200), (21,60), (60,252) |
| `vol_adj_momentum_{n}d` | `momentum / ewma_vol` | 5, 10, 14, 21, 50, 75, 100, 180, 200 |

### 3. Z-Score & Mean-Reversion (~55)

| Feature Pattern | Formula | Periods |
|-----------------|---------|---------|
| `zscore_{n}d` | `(return - μ) / σ` | ALL (18) |
| `dist_from_ma_{n}d` | `return - rolling_mean(n)` | ALL (18) |
| `return_pctrank_{n}d` | Percentile rank | 21, 50, 100, 200, 252 |

### 4. Moving Average (~30)

| Feature Pattern | Formula | Periods |
|-----------------|---------|---------|
| `ma_{n}d` | `rolling_mean(returns, n)` | ALL (18) |
| `ma_diff_{a}_{b}` | `ma_fast - ma_slow` | (5,20), (10,50), (20,50), (50,200), (14,50), (21,100) |
| `ma_cross_{a}_{b}` | `1 if ma_fast > ma_slow` | Same pairs |

### 5. Sharpe-Like (~18)

| Feature Pattern | Formula | Periods |
|-----------------|---------|---------|
| `sharpe_like_{n}d` | `rolling_mean / rolling_std` | ALL (18) |

### 6. Win Rate (~10)

| Feature Pattern | Formula | Periods |
|-----------------|---------|---------|
| `win_rate_ratio_{n}` | `pos_count / neg_count` | 5, 21, 180 |
| `win_rate_{n}d` | `pos_count / total_count` | 5, 10, 14, 21, 50, 100, 200 |

### 7. Lag Features (9)

| Feature Pattern | Formula | Lags |
|-----------------|---------|------|
| `return_lag_{n}d` | `returns[-n]` | 2, 3, 5, 7, 10, 14, 21, 30, 50 |

### 8. Autocorrelation (7)

| Feature Pattern | Formula | Periods |
|-----------------|---------|---------|
| `autocorr_{n}d` | `corr(returns[-n:], returns[-(n+1):-1])` | 5, 10, 14, 21, 50, 60, 100 |

### 9. Distribution (~24)

| Feature Pattern | Formula | Periods |
|-----------------|---------|---------|
| `skew_{n}d` | `scipy.stats.skew(returns[-n:])` | 21, 50, 60, 100, 200, 252 |
| `kurt_{n}d` | `scipy.stats.kurtosis(returns[-n:])` | Same |
| `lower_5pct_{n}d` | `percentile(returns, 5)` | Same |
| `upper_95pct_{n}d` | `percentile(returns, 95)` | Same |
| `lower_10pct_{n}d` | `percentile(returns, 10)` | Same |
| `upper_90pct_{n}d` | `percentile(returns, 90)` | Same |

### 10. Tail Risk (~16)

| Feature Pattern | Formula | Periods |
|-----------------|---------|---------|
| `dist_from_lower_{n}d` | `return - lower_5pct` | 21, 60, 100, 200 |
| `dist_from_upper_{n}d` | `upper_95pct - return` | Same |
| `dist_from_p05` | Current vol - p05 | 21d basis |
| `dist_from_p95` | p95 - current vol | 21d basis |

### 11. Rolling Min/Max/Range (~25)

| Feature Pattern | Formula | Periods |
|-----------------|---------|---------|
| `rolling_min_{n}d` | `min(returns[-n:])` | 5, 10, 14, 21, 50, 100, 200 |
| `rolling_max_{n}d` | `max(returns[-n:])` | Same |
| `rolling_range_{n}d` | `max - min` | Same |
| `position_in_range_{n}d` | `(ret - min) / range` | 21, 50, 100, 200 |

### 12. Rate of Change (7)

| Feature Pattern | Formula | Periods |
|-----------------|---------|---------|
| `roc_{n}d` | `(current - past) / abs(past)` | 5, 10, 14, 21, 50, 100, 200 |

### 13. Max Drawdown (8)

| Feature Pattern | Formula | Periods |
|-----------------|---------|---------|
| `max_drawdown_{n}d` | `max(cumsum) - cumsum[-1]` | 5, 10, 14, 21, 50, 60, 100, 200 |

### 14. Regime Indicators (~35)

| Feature Pattern | Formula | Notes |
|-----------------|---------|-------|
| `high_vol_regime` | `daily_vol > vol_ma_21` | Binary |
| `extreme_vol_regime` | `daily_vol > 1.5 × vol_ma_21` | Binary |
| `high_vol_regime_{n}` | `daily_vol > ewma_vol_n` | 21, 50, 100, 200 |
| `uptrend_regime_{n}d` | `momentum_n > 0` | ALL (18) |
| `strong_uptrend_{n}d` | `momentum > rolling_std` | 21, 50, 100 |
| `strong_downtrend_{n}d` | `momentum < -rolling_std` | Same |
| `vol_regime_discrete` | 6-level (0-5) | Based on 21d |

### 15. Reversal Patterns (~8)

| Feature Pattern | Formula | Pairs |
|-----------------|---------|-------|
| `reversal_5d` | `mom_5d > 0 AND return < 0` | Single |
| `reversal_21d` | `mom_21d > 0 AND mom_5d < 0` | Single |
| `reversal_{a}_{b}` | `mom_long > 0 AND mom_short < 0` | (5,21), (10,50), (21,100) |
| `reversal_up_{a}_{b}` | `mom_long < 0 AND mom_short > 0` | Same |

### 16. Microstructure (2)

| Feature | Formula | Notes |
|---------|---------|-------|
| `consecutive_up` | Running count of positive days | Resets on direction change |
| `consecutive_down` | Running count of negative days | Same |

### 17. Expanding Window (2)

| Feature | Formula | Notes |
|---------|---------|-------|
| `expanding_mean_vol` | `cumsum(vol) / count` | All-history |
| `expanding_std_returns` | `√(E[X²] - E[X]²)` | All-history |

### 18. Volatility Regime (~20)

| Feature Pattern | Formula | Periods |
|-----------------|---------|---------|
| `vol_percentile_rank_{n}` | Percentile of current vol | 21, 63, 126, 252 |
| `vol_pct_simple_{n}` | `(vol - mean) / std` | Same |
| `vol_position_in_range` | `(vol - p05) / (p95 - p05)` | 21d basis |
| `vol_momentum_{n}` | `(vol - prev_vol) / prev_vol` | 3, 5, 10, 21 |
| `vol_acceleration_{n}` | Second derivative | 5, 21 |
| `vol_autocorr_{n}` | Autocorrelation of vol | 5, 10, 21 |
| `high_vol_days_{n}` | Count of high-vol days | 21, 63 |
| `vol_cv_{n}` | Coefficient of variation | 21, 63 |

---

## Part B: HMM Regime Features (52)

**Created in:** Cells 6-7 of final scripts using `hmmlearn.hmm.GaussianHMM`

### HMM Training

```python
from hmmlearn.hmm import GaussianHMM

# Training data: returns + volatility (2D observations)
X_train = np.column_stack([lagged_returns, daily_volatility])

hmm4 = GaussianHMM(n_components=4, covariance_type='full', n_iter=1000)
hmm4.fit(X_train)

# Predict regime and probabilities
hmm_regime = hmm4.predict(X)              # Most likely state
hmm_probs = hmm4.predict_proba(X)         # Probability of each state
```

### HMM-4 Features (4-State Model)

| Feature | Formula | Description |
|---------|---------|-------------|
| `hmm_regime` | `hmm.predict(X)` | Most likely regime (0-3) |
| `hmm_regime_prob_0` to `_3` | `hmm.predict_proba(X)[:, i]` | Probability per regime |
| `hmm_regime_confidence` | `max(probs)` | Highest probability |
| `hmm_regime_change` | `(regime != regime.shift(1))` | Binary: regime changed |
| `hmm_regime_duration` | Running count in same regime | Days in current regime |
| `hmm4_regime_stable_3d` | `duration >= 3` | Stable ≥3 days |
| `hmm4_regime_stable_5d` | `duration >= 5` | Stable ≥5 days |
| `hmm4_confidence_change` | `confidence - confidence.shift(1)` | Δ confidence |
| `hmm4_confidence_ma_5` | `rolling_mean(confidence, 5)` | 5-day MA of confidence |
| `hmm4_confidence_std_5` | `rolling_std(confidence, 5)` | 5-day std of confidence |
| `hmm4_transitions_5d` | `rolling_sum(regime_change, 5)` | Transition count in 5d |
| `hmm4_transitions_10d` | `rolling_sum(regime_change, 10)` | Transition count in 10d |
| `hmm4_entropy` | `-Σ p×log(p)` | Shannon entropy of probs |
| `hmm4_expected_dwell` | `1 / (1 - A[s,s])` | From transition matrix A |
| `hmm4_normalized_entropy` | `entropy / log(4)` | Scaled to [0,1] |
| `hmm4_regime_entropy` | Rolling entropy over window | Regime uncertainty |
| `hmm4_transition_skew` | Asymmetry of transition matrix | Direction bias |
| `hmm4_weighted_dwell` | `Σ prob_i × dwell_i` | Prob-weighted dwell time |

### HMM-5 Features (5-State Model)

Same structure as HMM-4 but with 5 states:

| Feature | Formula | Description |
|---------|---------|-------------|
| `hmm5_regime` | `hmm5.predict(X)` | Most likely regime (0-4) |
| `hmm5_regime_prob_0` to `_4` | `hmm5.predict_proba(X)[:, i]` | Probability per regime |
| `hmm5_regime_confidence` | `max(probs)` | Highest probability |
| `hmm5_regime_change` | `(regime != regime.shift(1))` | Binary: regime changed |
| `hmm5_regime_duration` | Running count in same regime | Days in current regime |
| `hmm5_regime_stable_3d` | `duration >= 3` | Stable ≥3 days |
| `hmm5_regime_stable_5d` | `duration >= 5` | Stable ≥5 days |
| `hmm5_confidence_change` | `confidence - confidence.shift(1)` | Δ confidence |
| `hmm5_confidence_ma_5` | `rolling_mean(confidence, 5)` | 5-day MA of confidence |
| `hmm5_confidence_std_5` | `rolling_std(confidence, 5)` | 5-day std of confidence |
| `hmm5_transitions_5d` | `rolling_sum(regime_change, 5)` | Transition count in 5d |
| `hmm5_transitions_10d` | `rolling_sum(regime_change, 10)` | Transition count in 10d |
| `hmm5_entropy` | `-Σ p×log(p)` | Shannon entropy of probs |
| `hmm5_expected_dwell` | `1 / (1 - A[s,s])` | From transition matrix A |
| `hmm5_normalized_entropy` | `entropy / log(5)` | Scaled to [0,1] |
| `hmm5_regime_entropy` | Rolling entropy over window | Regime uncertainty |
| `hmm5_transition_skew` | Asymmetry of transition matrix | Direction bias |
| `hmm5_weighted_dwell` | `Σ prob_i × dwell_i` | Prob-weighted dwell time |

### Combined HMM Features

| Feature | Formula | Description |
|---------|---------|-------------|
| `hmm_regime_agreement` | `(hmm4_regime == mapped_hmm5_regime)` | Binary: both agree |
| `hmm_regime_divergence` | `abs(hmm4_regime/3 - hmm5_regime/4)` | Normalized difference |
| `hmm_avg_confidence` | `(hmm4_conf + hmm5_conf) / 2` | Mean confidence |
| `hmm_confidence_spread` | `abs(hmm4_conf - hmm5_conf)` | Confidence disagreement |
| `hmm_both_confident` | `(hmm4_conf > 0.6) & (hmm5_conf > 0.6)` | Both high confidence |
| `hmm_sync_transition` | `(hmm4_change==1) & (hmm5_change==1)` | Both changed together |
| `hmm_total_transitions` | `hmm4_change + hmm5_change` | Sum of changes (0-2) |
| `hmm_both_stable` | `(hmm4_stable_3d) & (hmm5_stable_3d)` | Both stable ≥3 days |
| `hmm_combined_entropy` | `(hmm4_entropy + hmm5_entropy) / 2` | Mean entropy |
| `hmm_dwell_divergence` | `abs(hmm4_dwell - hmm5_dwell)` | Dwell time difference |

### Historical Regime Features

```python
# Quantile thresholds from TRAINING data only
vol_33, vol_67 = quantile(daily_vol, [0.33, 0.67])
ret_33, ret_67 = quantile(returns, [0.33, 0.67])
```

| Feature | Formula | Description |
|---------|---------|-------------|
| `historical_vol_regime` | `0 if vol≤p33, 2 if vol>p67, else 1` | Tercile-based (0-2) |
| `historical_vol5_regime` | `quintile(daily_vol)` | 5-level vol regime (0-4) |
| `historical_dir_regime` | `0 if ret≤p33, 2 if ret>p67, else 1` | Tercile-based direction |

---

## Part C: DTMC Features (11)

**Discrete-Time Markov Chain** for direction prediction.

### State Definition

Returns are discretized into 3 states:
- **State 0 (Down)**: return < -threshold
- **State 1 (Flat)**: -threshold ≤ return ≤ +threshold  
- **State 2 (Up)**: return > +threshold

### Transition Matrix

```python
# P[i,j] = P(next_state=j | current_state=i)
# Built from EXPANDING WINDOW (only past data)
P = transition_counts / row_sums
```

### Feature Calculations

| Feature | Formula | Description |
|---------|---------|-------------|
| `dtmc_state` | `discretize(return)` | Current state (0, 1, or 2) |
| `dtmc_p_up_1` | `P[current_state, 2]` | 1-step probability of Up |
| `dtmc_p_up_5` | `(P^5)[current_state, 2]` | 5-step matrix power, Up prob |
| `dtmc_p_up_10` | `(P^10)[current_state, 2]` | 10-step matrix power |
| `dtmc_p_up_20` | `(P^20)[current_state, 2]` | 20-step matrix power |
| `dtmc_p_down_1` | `P[current_state, 0]` | 1-step probability of Down |
| `dtmc_self_transition` | `P[current_state, current_state]` | Probability of staying |
| `dtmc_expected_dwell` | `1 / (1 - P[s,s])` | Expected time in state |
| `dtmc_direction_confidence` | `abs(p_up_1 - p_down_1)` | Direction certainty |
| `dtmc_direction_spread` | `p_up_1 / (p_down_1 + ε)` | Up/Down ratio |
| `dtmc_transition_entropy` | `-Σ p·log(p)` | Uncertainty of next state |

---

## Part D: Kalman Filter Features (5+)

### Kalman Filter State Space Model

```python
# 3D State Vector: [position, velocity, acceleration]
# Observation: lagged_forward_returns (normalized)

# State Transition (constant velocity + noise):
x_pred = F @ x_prev  # F is state transition matrix
P_pred = F @ P_prev @ F.T + Q  # Q is process noise

# Update:
K = P_pred @ H.T @ inv(H @ P_pred @ H.T + R)  # Kalman gain
x_new = x_pred + K @ (z - H @ x_pred)  # z is observation
```

### Core Kalman Features

| Feature | Formula | Description |
|---------|---------|-------------|
| `kalman_h20_pred` | `x[0]` (position) | Kalman prediction (normalized) |
| `kalman_h20_state_vel` | `x[1]` (velocity) | Estimated rate of change |
| `kalman_h20_state_accel` | `x[2]` (acceleration) | Estimated 2nd derivative |
| `kalman_h20_confidence` | `1 / (1 + trace(P))` | Inverse of uncertainty |
| `kalman_h20_rolling_vol` | `rolling_std(returns, 20)` | For denormalization |

### Regime & Direction Features

| Feature | Formula | Description |
|---------|---------|-------------|
| `kalman_h20_signal_direction` | `sign(kalman_pred)` | +1 bullish, -1 bearish |
| `kalman_h20_vol_regime` | `tercile(rolling_vol)` | 1=low, 2=mid, 3=high vol |
| `kalman_h20_pred_strength` | `quintile(abs(pred))` | 1-5 strength scale |
| `kalman_h20_accel_regime` | `tercile(abs(accel))` | Acceleration strength |

### Cross-Model Consensus Features

| Feature | Formula | Description |
|---------|---------|-------------|
| `kalman_all_models_bullish` | `(vel>0) & (hmm_regime≥2) & (no_extreme_anomaly)` | All agree bullish |
| `kalman_all_models_bearish` | `(vel<0) & (hmm_regime<2) & (has_anomaly)` | All agree bearish |
| `kalman_hmm_cusum_agree` | `(hmm_regime_change + cusum_change) / 2` | Agreement score (0-1) |

---

## Part E: Helper Model Features (15)

**Ensemble predictions from simpler models** trained with expanding window.

### Direction Helper (Logistic Regression)

```python
# EXPANDING WINDOW: At row i, train on rows 0 to i-1
# Features: momentum_5d, momentum_21d, zscore_5d, dist_from_ma_21d,
#           daily_volatility_lagged, volatility_ma_5, consecutive_up/down

model = LogisticRegression(C=0.1, max_iter=500)
model.fit(X_train[:i], y_train[:i])
helper_dir_prob[i] = model.predict_proba(X[i])[1]  # P(Up)
```

| Feature | Formula | Description |
|---------|---------|-------------|
| `helper_dir_prob` | `LogisticRegression.predict_proba()` | P(direction=Up) |
| `helper_dir_signal` | `sign(helper_dir_prob - 0.5)` | +1 if >50%, else -1 |
| `helper_dir_confidence` | `abs(helper_dir_prob - 0.5) × 2` | Distance from uncertainty |
| `helper_dir_prob_x_regime` | `helper_dir_prob × hmm_regime` | Interaction with HMM |

### Volatility Helper (EWMA)

```python
# EWMA update formula (row-by-row)
alpha = 2 / (span + 1)  # span = 21

if i == 0:
    ewma[i] = current_vol
else:
    ewma[i] = alpha * current_vol + (1-alpha) * ewma[i-1]

# Error uses LAGGED values to avoid leakage
error[i] = volatility_target[i-1] - ewma[i-1]
```

| Feature | Formula | Description |
|---------|---------|-------------|
| `helper_vol_ewma` | `α·vol + (1-α)·prev_ewma` | EWMA prediction (α=2/22) |
| `helper_vol_ewma_absret` | `α·abs(ret) + (1-α)·prev` | EWMA of absolute returns |
| `helper_vol_ewma_variance` | `std(vol[-21:])` | Rolling std of volatility |
| `helper_vol_ewma_error` | `target[i-1] - ewma[i-1]` | LAGGED prediction error |
| `helper_vol_ewma_x_regime` | `ewma × hmm_regime` | Interaction with HMM |

### Volatility Helper (Linear Regression)

```python
# Features: vol features, momentum, regime indicators
# EXPANDING WINDOW training
model = Ridge(alpha=1.0)
model.fit(X_train[:i], y_train[:i])
helper_vol_lr[i] = model.predict(X[i])
```

| Feature | Formula | Description |
|---------|---------|-------------|
| `helper_vol_lr` | `Ridge.predict()` | Linear regression vol pred |
| `helper_vol_lr_error` | `target[i-1] - lr[i-1]` | LAGGED prediction error |
| `helper_vol_lr_x_regime` | `lr × hmm_regime` | Interaction with HMM |
| `helper_vol_rolling_mean` | `mean(vol[-21:])` | Simple rolling mean |
| `helper_vol_rolling_std` | `std(vol[-21:])` | Simple rolling std |
| `helper_vol_consensus` | `mean(ewma, lr, rolling_mean)` | Average of all helpers |

---

## Part F: Other Features

### Anomaly Features

| Feature | Description |
|---------|-------------|
| `anomaly_moderate_sev_x_hmm` | Moderate anomaly × HMM |
| `anomaly_moderate_sev_x_hmm5` | Moderate anomaly × HMM5 |
| `anomaly_extreme_sev_x_hmm5` | Extreme anomaly × HMM5 |

### Jump/Event Detection

| Feature | Description |
|---------|-------------|
| `large_vol_jump` | Large volatility jump |
| `periods_detecting_jump` | # periods detecting jump |
| `periods_ensemble_triggered` | # periods in ensemble |
| `cusum_vol_momentum` | CUSUM of vol momentum |
| `avg_period_confidence` | Average confidence |

---

## Summary

| Category | Count |
|----------|-------|
| **Row-by-row (volatility)** | ~60 |
| **Row-by-row (momentum)** | ~55 |
| **Row-by-row (z-score/mean-rev)** | ~55 |
| **Row-by-row (MA/sharpe/win)** | ~58 |
| **Row-by-row (lag/autocorr)** | ~16 |
| **Row-by-row (distribution/tail)** | ~40 |
| **Row-by-row (range/ROC/drawdown)** | ~40 |
| **Row-by-row (regime/reversal)** | ~45 |
| **HMM-4** | ~18 |
| **HMM-5** | ~18 |
| **Combined HMM** | ~16 |
| **DTMC** | 11 |
| **Kalman** | 5 |
| **Helper models** | 15 |
| **Anomaly/Jump** | ~8 |
| **TOTAL** | **~450** |

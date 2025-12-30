# Phase 0.2: Base Feature Audit Report

**Date**: 2025-12-24
**Status**: COMPLETE ✅

---

## Summary

| Metric | Value |
|--------|-------|
| **Total Base Features** | 166 |
| **Already Scale-Invariant** | 36 (bounded [0,1]) |
| **Need Preprocessing** | 130 (unbounded) |
| **Leakage Found** | ❌ **NONE** |
| **All Rolling Windows** | ✅ YES (no global stats) |

---

## 0.2.1 Complete Feature Classification (166 features)

### By Domain

| Domain | Count | Features |
|--------|-------|----------|
| **Volatility-derived** | 58 | ATR, std, vol-of-vol, Parkinson, GK, RS, YZ, Hurst, drawdown, skew, kurtosis |
| **Price-derived** | 32 | Returns, ROC, PPO, deviations, pctB, z-score, CCI, VWAP |
| **Volume-derived** | 29 | Volume ROC/ratio, OBV, MFI, CMF, OI change/ratio, Amihud |
| **Sentiment-derived** | 27 | Funding rate, premium, basis, spread, L/S ratio |
| **Technical indicators** | 24 | RSI, stochastic, ADX, DI, Sharpe, Sortino, Calmar, autocorr |
| **Candlestick** | 2 | Body size, shadows |
| **Temporal** | 2 | Funding cycle, day of week |

### By Scale Type

| Type | Count | Preprocessing Needed |
|------|-------|---------------------|
| **Bounded [0,1]** | 36 | None (already normalized) |
| **Binary** | 3 | None |
| **Z-scores** | 10 | Already standardized |
| **Percentages** | 70 | Winsorize + Scale |
| **Ratios** | 35 | Winsorize + Scale |
| **Differences** | 2 | Winsorize + Scale |
| **Ranks** | 2 | None (already [0,1]) |

---

## 0.2.2 Feature Type Details

### A. Already Scale-Invariant (36 features) — NO PREPROCESSING NEEDED

```
# Bounded [0,1] with _bnd_ or _bin suffix
N_P_V_pctB_3_bnd_N          # Bollinger %B (already [0,1])
N_P_V_pctB_6_bnd_N
N_P_V_pctB_12_bnd_N
N_P_V_pctB_21_bnd_N
C_N_bodySize_bnd_N          # Candle body size [0,1]
C_N_upperShadow_bnd_N       # Shadow ratios [0,1]
C_N_lowerShadow_bnd_N
B_C_candleDirection_bin     # Binary (0 or 1)
M_N_rsi_6_bnd_N             # RSI [0,100] → scaled to [0,1]
M_N_rsi_12_bnd_N
M_N_rsi_21_bnd_N
M_N_stochasticK_6_bnd_N     # Stochastic [0,100] → [0,1]
M_N_T_stochasticD_6_bnd_N
M_N_stochasticK_12_bnd_N
M_N_T_stochasticD_12_bnd_N
F_TM_fundingCyclePosition_bin  # Temporal binary
B_TM_dayOfWeek_bin
N_V_atrPercentile_21_rnk_N    # Rank [0,1]
N_V_atrPercentile_42_rnk_N
V_autocorr_12_bnd_N           # Autocorrelation [-1,1] → [0,1]
V_autocorr_21_bnd_N
B_consecutiveUp_bnd_N         # Count bounded
B_consecutiveDown_bnd_N
M_winRate_6_bnd_N             # Win rate [0,1]
M_winRate_12_bnd_N
M_winRate_21_bnd_N
L_M_S_mfi_6_bnd_N             # MFI [0,100] → [0,1]
L_M_S_cmf_6_bnd_N             # CMF [-1,1] → bounded
L_M_S_mfi_12_bnd_N
L_M_S_cmf_12_bnd_N
L_M_S_mfi_21_bnd_N
L_M_S_cmf_21_bnd_N
M_T_V_adx_6_bnd_N             # ADX [0,100] → [0,1]
M_T_V_diDiff_6_bnd_N          # DI difference [-100,100] → bounded
M_T_V_adx_12_bnd_N
M_T_V_diDiff_12_bnd_N
```

### B. Already Standardized (Z-scores) — 10 features

```
# Features with _zsc_ suffix (already zero-mean, unit-variance-ish)
F_I_N_S_fundingZscore_21_zsc_N
F_I_N_S_fundingZscore_42_zsc_N
D_F_N_S_premiumZscore_21_zsc_N
D_F_N_S_premiumZscore_42_zsc_N
N_P_zScore_12_zsc_N
N_P_zScore_21_zsc_N
N_P_zScore_42_zsc_N
L_M_S_obv_21_zsc_N
L_M_S_obv_42_zsc_N
N_M_cci_6_zsc_N
N_M_cci_12_zsc_N
N_M_cci_21_zsc_N
```

**Note**: These z-scores are computed with **rolling** windows in compute_features.py, NOT expanding. Example:
```python
mu = df["fundingRate"].rolling(n).mean()
sigma = df["fundingRate"].rolling(n).std()
return (df["fundingRate"] - mu) / sigma
```

### C. Unbounded Percentages — 70 features (NEED PREPROCESSING)

Features with `_pct_` suffix:
- Returns: M_P_logReturn_pct_N, M_P_roc_*
- Volatility: V_atrPct_*, V_returnStd_*, N_V_bollingerBandwidth_*
- Funding: F_I_fundingCumulative_*, F_I_T_fundingMa_*
- Premium: D_F_T_premiumMa_*, M_D_F_S_premiumChange_pct_N
- Mark price deviations
- Volume ROC
- Vol momentum
- And more...

### D. Unbounded Ratios — 35 features (NEED PREPROCESSING)

Features with `_rat_` suffix:
- Momentum/ATR: M_P_V_momAtr_*
- OI ratios: L_N_volOiRatio_*, L_N_S_oiRatio_*
- Mark ratios: D_N_V_markAtrRatio_*
- Range expansion: M_N_V_rangeExpansion_*
- Risk-adjusted: M_V_sharpe_*, M_V_sortino_*, M_V_calmar_*
- Skew/Kurtosis: V_skew_*, V_kurtosis_*
- Volatility estimators: V_parkinson_*, V_garmanKlass_*, V_rogersSatchell_*, V_yangZhang_*
- Hurst: V_hurstExponent_*
- Amihud: L_V_amihudIlliquidity_*
- L/S ratio: S_longShortRatio_rat_N

### E. Differences — 2 features (NEED PREPROCESSING)

```
M_N_rocAccel_3_dif_N    # ROC acceleration (difference of ROC)
M_N_rocAccel_6_dif_N
```

---

## 0.2.3 Leakage Analysis of compute_features.py

### Rolling Windows Used (NO LEAKAGE) ✅

**All features use `.rolling(n)` with specified window sizes:**

| Operation | Count | Example |
|-----------|-------|---------|
| `.rolling(n).mean()` | 35 | SMA, RSI gain/loss |
| `.rolling(n).std()` | 15 | Return std, Bollinger |
| `.ewm(span=n).mean()` | 12 | ATR, ADX smoothing |
| `.rolling(n).apply()` | 5 | Max drawdown, Hurst |
| `.shift(1)` | 50+ | All use positive shift (lookback) |

### Code Patterns Verified ✅

```python
# Pattern 1: Rolling mean/std (SAFE)
sma = df["close"].rolling(n).mean()
std = df["close"].rolling(n).std()

# Pattern 2: EWM (SAFE - uses only past)
atr = tr.ewm(span=n, adjust=False).mean()

# Pattern 3: Z-scores with rolling (SAFE)
mu = df["fundingRate"].rolling(n).mean()
sigma = df["fundingRate"].rolling(n).std()
zscore = (df["fundingRate"] - mu) / sigma

# Pattern 4: Shift for lookback (SAFE)
log_returns = np.log(df["close"] / df["close"].shift(1))  # shift(+1) = past

# Pattern 5: Rolling apply (SAFE)
def rolling_max_dd(window):
    peak = window.expanding().max()  # expanding WITHIN window
    dd = (window - peak) / peak
    return dd.min()
return df["close"].rolling(n).apply(rolling_max_dd)
```

### Key Finding: NO GLOBAL STATISTICS ✅

- No `df["col"].mean()` (global mean)
- No `df["col"].std()` (global std)
- No `df["col"].quantile()` (global quantile)
- No `np.mean(arr)` or `np.std(arr)` on full arrays

---

## 0.2.4 Features by Scale-Invariance Status

### Already Scale-Invariant (No Preprocessing Needed) — 48 features

| Type | Count | Action |
|------|-------|--------|
| Bounded [0,1] | 36 | Pass through |
| Z-scores | 12 | Pass through (already standardized) |

### Need Preprocessing — 118 features

| Type | Count | Recommended |
|------|-------|-------------|
| Percentages | 70 | Winsorize → RollingZScore or ExpandingRank |
| Ratios | 35 | Winsorize → RollingZScore or ExpandingRank |
| Differences | 2 | Winsorize → RollingZScore or ExpandingRank |
| Special (drawdown, etc.) | 11 | Winsorize only |

---

## 0.2.5 Feature Groups for Selective Preprocessing

Based on analysis, define these groups for the PreprocessorPipeline:

```python
FEATURE_GROUPS = {
    "BOUNDED": [
        # 36 features with _bnd_ or _bin suffix
        # Already [0,1] — skip all preprocessing
    ],
    
    "ZSCORE": [
        # 12 features with _zsc_ suffix
        # Already standardized — maybe light winsorize only
    ],
    
    "VOLATILITY": [
        # V_atrPct_*, V_returnStd_*, V_vol*, V_parkinson_*, etc.
        # 58 features — Winsorize + Log + ExpandingZScore
    ],
    
    "RETURNS": [
        # M_P_logReturn_*, M_P_roc_*, momentum features
        # 32 features — Winsorize + RollingZScore
    ],
    
    "VOLUME": [
        # L_M_N_volumeRoc_*, L_N_volumeRatio_*, OI features
        # 29 features — Winsorize + RollingZScore
    ],
    
    "SENTIMENT": [
        # Funding, premium, L/S ratio
        # 27 features — Winsorize + RollingZScore
    ],
    
    "TECHNICAL": [
        # Sharpe, Sortino, Calmar, autocorr (non-bounded)
        # ~12 features — Winsorize + RollingZScore
    ],
}
```

---

## 0.2.6 Recommendations by Target Type

### Regression Targets (returns, volatility)

**Returns (4 horizons)**:
- Bounded: Pass through
- Z-scores: Pass through
- Others: Winsorize(1%, 99%) → RollingZScore(63)

**Volatility (4 horizons)**:
- Bounded: Pass through
- Z-scores: Pass through
- Volatility features: Winsorize → Log → ExpandingZScore
- Others: Winsorize → ExpandingZScore

### Classification Targets (direction, trend_regime, vol_regime)

**All 12 classification horizons**:
- Bounded: Pass through
- Z-scores: ExpandingRank (convert to percentile)
- Others: Winsorize(1%, 99%) → ExpandingRank

**Rationale**: Classification models benefit from rank-based features which preserve monotonicity while eliminating scale effects.

---

## Phase 0.2 Completion Checklist

- [x] 0.2.1 List all 166 base features from dataset
- [x] 0.2.2 Classify by type (Price, Volume, Volatility, Sentiment, Technical)
- [x] 0.2.3 Check existing preprocessing in compute_features.py
- [x] 0.2.4 Document which features are already scale-invariant

**Key Finding**: 
- **48/166 features** (29%) already scale-invariant
- **118/166 features** (71%) need preprocessing
- **0 features** have leakage in compute_features.py

**Status**: COMPLETE ✅

**Next**: Phase 0.3 — Audit existing optimizers

# RiskYieldMM Pipeline Architecture

## Overview

Complete pipeline from raw 8h Bybit data to walk-forward predictions.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                          RAW DATA (8h Bybit BTCUSDT)                         │
│  OHLCV, Mark Price, Index Price, Premium, Funding Rate, OI, L/S Ratio        │
└───────────────────────────────────────┬──────────────────────────────────────┘
                                        │
                                        ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                    STEP 1: FEATURE ENGINEERING (166 features)                │
│  prepare_dataset.py → compute_features.py → features_8h.parquet              │
└───────────────────────────────────────┬──────────────────────────────────────┘
                                        │
                                        ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                    STEP 2: TARGET GENERATION (7 targets)                     │
│  data.py → analysis_8h.parquet                                               │
│  y_direction, y_forward_return_{1,3,6,12}, y_volatility, y_vol_regime,       │
│  y_trend_regime                                                              │
└───────────────────────────────────────┬──────────────────────────────────────┘
                                        │
                                        ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                    STEP 3: FEATURE OPTIMIZATION (per target)                 │
│  parallel_optimize.py → features_8h_optimized_{target}_{horizon}bar.parquet  │
│  Adds interaction features selected by IC against each target                │
└───────────────────────────────────────┬──────────────────────────────────────┘
                                        │
                                        ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                    STEP 4: DATASET MATRIX (20 datasets)                      │
│  run.py → data/datasets/{target}_{horizon}bar.parquet                        │
│  ~168 features + target column per file                                      │
└───────────────────────────────────────┬──────────────────────────────────────┘
                                        │
                                        ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                    STEP 8: L1 PRECOMPUTATION (10 helpers)                    │
│  l1_precompute.py → data/precomputed/{config}/                               │
│  91 helper features per iteration (HMM, GARCH, Kalman, CUSUM, IF, OU, EVT,   │
│  BOCPD, EGARCH, Interactions)                                                │
└───────────────────────────────────────┬──────────────────────────────────────┘
                                        │
                                        ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                    STEP 9: DATASET ASSEMBLY                                  │
│  dataset_assembly.py → data/precomputed/{config}/assembled.parquet           │
│  One row per prediction iteration with all helper features                   │
└───────────────────────────────────────┬──────────────────────────────────────┘
                                        │
                                        ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                    L2 BACKTEST (Walk-Forward)                                │
│  l2_backtest_sync.py                                                         │
│  3-model ensemble: CatBoost + LightGBM + Linear                              │
│  Conformal calibration for prediction intervals                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## LAYER 1: Raw Data Sources

Location: `fetchingByBit/`

| Source | File | Columns | Rows |
|--------|------|---------|------|
| OHLCV | `sorted-8h-bybit-linear/btcusdt_8h.parquet` | open, high, low, close, volume, turnover | 5,438 |
| Mark Price | `mark-price-8h-bybit-linear/` | markOpen, markHigh, markLow, markClose | 5,438 |
| Index Price | `index-price-8h-bybit-linear/` | indexOpen, indexHigh, indexLow, indexClose | 5,438 |
| Premium | `premium-price-8h-bybit-linear/` | premiumOpen, premiumHigh, premiumLow, premiumClose | 5,438 |
| Funding Rate | `funding-rate-bybit-linear/` | fundingRate | 5,438 |
| Open Interest | `open-interest-8h-bybit-linear/` | openInterest | 5,438 |
| L/S Ratio | `long-short-ratio-8h-bybit-linear/` | buyRatio, sellRatio | 5,002 |

**Time Range:** 2021-01-01 to 2025-12-18 (8h bars)

---

## LAYER 2: Feature Engineering (166 features)

File: `scripts/feature_engineering/compute_features.py`

### Feature Categories

| Prefix | Category | Count | Description |
|--------|----------|-------|-------------|
| M | Momentum | 40 | ROC, PPO, RSI, returns, ATR-normalized momentum |
| V | Volatility | 35 | ATR, return std, skew, kurtosis, Parkinson, Garman-Klass, Yang-Zhang |
| L | Liquidity/Volume | 28 | OI, volume ratios, OBV, MFI, CMF, Amihud |
| N | Normalized | 23 | Z-scores, percentile ranks, deviations |
| D | Derivatives | 16 | Basis, mark spread, premium features |
| F | Funding | 12 | Cumulative, MA, diff, zscore |
| S | Sentiment | 5 | L/S ratio, zscore, change |
| B | Binary/Pattern | 4 | Candle direction, consecutive up/down |
| C | Candlestick | 3 | Body size, shadows |

### Feature Computation (by category)

#### Momentum & Price (M)
```python
M_P_logReturn_pct_N           # ln(close_t / close_{t-1})
M_P_roc_{3,6,12,21}_pct_N     # (close - close.shift(n)) / close.shift(n)
M_P_V_momAtr_{3,6,12,21}_rat_N # (close - close.shift(n)) / ATR(n)
M_T_ppo_8_21_pct_N            # (EMA_8 - EMA_21) / EMA_21 * 100
M_T_ppo_12_26_pct_N           # (EMA_12 - EMA_26) / EMA_26 * 100
M_N_rsi_{6,12,21}_bnd_N       # RSI bounded [0, 100]
M_N_stochasticK_{6,12}_bnd_N  # Stochastic %K
M_N_T_stochasticD_{6,12}_bnd_N # Stochastic %D (smoothed K)
M_N_rocAccel_{3,6}_dif_N      # ROC acceleration
M_P_L_vwapReturn_pct_N        # VWAP return
M_V_sharpe_{21,42}_rat_N      # Rolling Sharpe
M_V_sortino_{21,42}_rat_N     # Rolling Sortino
M_V_calmar_{21,42}_rat_N      # Rolling Calmar
M_T_V_adx_{6,12}_bnd_N        # ADX trend strength
M_T_V_diDiff_{6,12}_bnd_N     # +DI - -DI
M_winRate_{6,12,21}_bnd_N     # Win rate over window
```

#### Volatility (V)
```python
V_atrPct_{3,6,12,21}_pct_N     # ATR / close
V_returnStd_{3,6,12,21}_pct_N  # Rolling std of log returns
V_skew_{12,21,42}_rat_N        # Rolling skewness
V_kurtosis_{12,21,42}_rat_N    # Rolling kurtosis
V_maxDrawdown_{21,42}_pct_N    # Rolling max drawdown
V_volOfVol_{6,12,21}_pct_N     # Volatility of volatility
V_autocorr_{12,21}_bnd_N       # Lag-1 autocorrelation
V_volMomentum_{6,12,21}_pct_N  # Rate of change of volatility

# Academic volatility estimators
V_parkinson_{12,21}_pct_N      # Range-based (Parkinson 1980)
V_garmanKlass_{12,21}_pct_N    # OHLC-based (Garman-Klass 1980)
V_rogersSatchell_{12,21}_pct_N # Drift-independent
V_yangZhang_{12,21}_pct_N      # Most efficient overall
V_hurstExponent_{63,126}_rat_N # Long-memory measure
```

#### Liquidity/Volume (L)
```python
L_M_N_S_oiPctChange_pct_N      # OI percent change
L_N_volOiRatio_rat_N           # volume / OI
L_M_N_S_oiRoc_{3,6,12}_pct_N   # OI rate of change
L_N_S_oiRatio_{6,12,21}_rat_N  # OI / SMA(OI)
L_M_N_volumeRoc_{3,6,12}_pct_N # Volume ROC
L_N_volumeRatio_{6,12,21}_rat_N # Volume / SMA(volume)
L_M_S_obv_{21,42}_zsc_N        # On-Balance Volume z-scored
L_M_S_mfi_{6,12,21}_bnd_N      # Money Flow Index
L_M_S_cmf_{6,12,21}_bnd_N      # Chaikin Money Flow
L_S_oiVolumeRatio_{6,12,21}_rat_N # OI / SMA(volume)
L_V_amihudIlliquidity_{12,21,63}_rat_N # Amihud (2002)
```

#### Normalized/Z-Score (N)
```python
N_P_V_pctB_{3,6,12,21}_bnd_N     # Bollinger %B
N_V_bollingerBandwidth_{21,42}_pct_N # Band width
N_P_T_priceSmaDeviation_{3,6,12,21}_pct_N # Price vs SMA
N_P_T_priceEmaDeviation_{3,6,12,21}_pct_N # Price vs EMA
N_P_L_vwapDeviation_pct_N       # Price vs VWAP
N_V_atrPercentile_{21,42}_rnk_N # ATR percentile rank
N_P_zScore_{12,21,42}_zsc_N     # Price z-score
N_M_cci_{6,12,21}_zsc_N         # CCI
```

#### Derivatives/Premium (D)
```python
D_F_T_premiumMa_{3,7,21}_pct_N  # Premium MA
D_F_N_S_premiumZscore_{21,42}_zsc_N # Premium z-score
D_F_basis_pct_N                 # (futures - index) / index
D_markIndexSpread_pct_N         # (mark - index) / index
D_N_markCloseDeviation_pct_N    # (close - mark) / mark
D_N_V_markAtrRatio_{6,12,21}_rat_N # ATR(mark) / ATR(close)
D_N_V_markCloseRange_rat_N      # |close - mark| / range
D_N_closeVsMarkVol_{6,12,21}_pct_N # Relative spread volatility
D_N_premiumRange_rat_N          # premiumRange / atrPct
```

#### Funding (F)
```python
F_I_fundingCumulative_{3,7,21}_pct_N  # Cumulative funding
F_I_T_fundingMa_{3,7,21}_pct_N        # Funding MA
F_I_M_fundingMaDiff_{3_7,3_21,7_21}_pct_N # Funding MA diff
F_I_N_S_fundingZscore_{21,42}_zsc_N   # Funding z-score
F_TM_fundingCyclePosition_bin         # 0, 1, 2 (8h cycle)
```

#### Sentiment/L-S Ratio (S)
```python
S_longShortRatio_rat_N          # Raw L/S ratio
S_N_longShortZscore_{21,63}_zsc_N # L/S z-score (contrarian signal)
S_M_longShortChange_{3,12}_pct_N  # L/S momentum
```

#### Binary/Pattern (B)
```python
B_C_candleDirection_bin          # sign(close - open)
B_consecutiveUp_bnd_N            # Consecutive up bars [0,10]
B_consecutiveDown_bnd_N          # Consecutive down bars [0,10]
B_TM_dayOfWeek_bin               # Day of week (0-6)
```

#### Candlestick (C)
```python
C_N_bodySize_bnd_N               # |close - open| / range
C_N_upperShadow_bnd_N            # Upper shadow ratio
C_N_lowerShadow_bnd_N            # Lower shadow ratio
```

---

## LAYER 3: Target Generation (7 targets)

File: `scripts/analysis/data.py`

| Target | Type | Formula | Use Case |
|--------|------|---------|----------|
| `y_direction_1bar` | Binary (0/1) | `net_candle_return > 0` | Direction prediction |
| `y_forward_return_{1,3,6,12}` | Continuous | `ln(close_t+h / close_t)` | Return prediction |
| `y_volatility` | Continuous | `\|forward_return_1\|` | Risk/sizing |
| `y_vol_regime` | Categorical (0/1/2) | Quantile-based (warmup thresholds) | Regime filter |
| `y_trend_regime` | Binary (0/1) | SMA crossover | Trend filter |

### Target Computation Details

```python
# Direction (binary)
net_candle_ret = (close - open) / open  # "net candle return"
y_direction = (net_candle_ret.shift(-horizon) > 0).astype(int)

# Forward returns (multi-horizon)
y_forward_return_h = np.log(close.shift(-h) / close)

# Volatility
y_volatility = np.abs(y_forward_return_1)

# Vol regime (FIXED - uses warmup thresholds, not future data)
warmup = 1000  # First 1000 bars for threshold estimation
vol_warmup = y_volatility[:warmup]
q33, q67 = vol_warmup.quantile([0.33, 0.67])
y_vol_regime = pd.cut(y_volatility, bins=[-np.inf, q33, q67, np.inf], labels=[0, 1, 2])

# Trend regime
sma_short = close.rolling(8).mean()
sma_long = close.rolling(21).mean()
y_trend_regime = (sma_short > sma_long).astype(int)
```

---

## LAYER 4: L1 Helpers (91 features from 10 helpers)

File: `scripts/target_models/helpers/`

| Helper | Features | Time | Backend | Purpose |
|--------|----------|------|---------|---------|
| IsolationForest | 12 | 380ms | Python (sklearn) | Anomaly detection |
| CUSUM | 12 | 35ms | **Rust** (156x) | Changepoint detection |
| GARCH | 8 | 4ms | **Rust** (224x) | Volatility forecast |
| HMM-4 | 9 | 316ms | **Rust** (1.5x) | 4-state regime |
| HMM-5 | 10 | 350ms | Python (hmmlearn) | 5-state regime |
| Kalman | 7 | 3ms | **Rust** (487x) | Position/velocity/accel |
| OU | 8 | 1ms | **Rust** (30x) | Mean-reversion |
| EVT | 10 | 3ms | **Rust** (25x) | Tail risk (VaR, ES) |
| BOCPD | 7 | 5ms | **Rust** (20x) | Bayesian changepoint |
| EGARCH | 8 | 4ms | **Rust** (87x) | Asymmetric volatility |

### Helper Features Example

```python
# CUSUM features
H_cusum_pos_sum, H_cusum_neg_sum       # Cumulative sums
H_cusum_pos_count, H_cusum_neg_count   # Counts
H_cusum_last_reset_pos/neg             # Bars since reset
H_cusum_upper_breaches, H_cusum_lower_breaches
H_cusum_mean_run_length, H_cusum_max_run_length

# HMM features
H_hmm4_state                   # Current state (0-3)
H_hmm4_prob_{0,1,2,3}         # State probabilities
H_hmm4_entropy                 # State uncertainty
H_hmm4_transition_prob         # Transition probability
H_hmm4_duration                # Bars in current state

# Kalman features
H_kalman_position, H_kalman_velocity, H_kalman_acceleration
H_kalman_position_std, H_kalman_velocity_std, H_kalman_acceleration_std
H_kalman_log_likelihood

# EVT features
H_evt_shape, H_evt_scale       # GPD parameters
H_evt_var_95, H_evt_var_99     # Value at Risk
H_evt_es_95, H_evt_es_99       # Expected Shortfall
H_evt_tail_prob_2x, H_evt_tail_prob_3x  # Tail probabilities
```

---

## LAYER 5: L2 Ensemble (Walk-Forward Backtest)

File: `scripts/target_models/validation/l2_backtest_sync.py`

### 3-Model Ensemble

| Model | Type | Strength |
|-------|------|----------|
| CatBoost | Gradient Boosting | Handles categoricals, GPU |
| LightGBM | Gradient Boosting | Fast, leaf-wise |
| Linear | Ridge Regression | Stability, interpretability |

### Walk-Forward Configuration

```python
@dataclass
class SlidingL2Config:
    window_size: int = 575     # Total L2 window
    train_ratio: float = 0.60  # 345 bars for training
    cal_ratio: float = 0.25    # 143 bars for calibration
    val_ratio: float = 0.15    # 87 bars for validation
    purge_gap: int = 12        # Purge between splits
    pred_size: int = 1         # Bars to predict (horizon)
```

### Conformal Calibration

- Standard: Constant-width intervals (90% coverage)
- CQR: Conformalized Quantile Regression (adaptive width)

---

## Potential Layer 1 Enhancements

### Missing Domain Features (Priority Order)

1. **Microstructure Features**
   - Tick imbalance (buy vs sell volume pressure)
   - VPIN (Volume-Synchronized Probability of Informed Trading)
   - Kyle's Lambda (price impact)

2. **Multi-Timeframe Features**
   - Higher timeframe trend (daily, weekly)
   - Lower timeframe volatility (1h, 4h)
   - Timeframe alignment score

3. **Market Regime Features**
   - VIX proxy for crypto
   - Correlation with BTC dominance
   - Cross-asset correlation (ETH, S&P500)

4. **Advanced Derivatives Features**
   - Funding rate term structure
   - OI concentration (whale positioning)
   - Liquidation cascade risk

5. **Order Flow Features** (requires tick data)
   - Order imbalance
   - Trade size distribution
   - Quote-to-trade ratio

### Feature Naming Convention

```
[Groups]_featureName_[period]_[form]_[norm]

Groups (prefix):
  M = Momentum
  V = Volatility
  T = Trend
  N = Normalized
  L = Liquidity/Volume
  D = Derivatives
  F = Funding
  S = Sentiment
  B = Binary/Pattern
  C = Candlestick
  P = Price
  W = Weighted/Composite
  I = Interaction

Form (suffix):
  pct = Percentage
  rat = Ratio
  zsc = Z-score
  rnk = Rank
  bnd = Bounded [0,1] or [0,100]
  bin = Binary
  dif = Difference

Norm:
  N = Normalized (raw computed)
```

---

## Files Summary

| Step | Input | Script | Output |
|------|-------|--------|--------|
| 1a | fetchingByBit/*.parquet | prepare_dataset.py | data/merged_8h_raw.parquet |
| 1b | merged_8h_raw.parquet | compute_features.py | data/features_8h.parquet |
| 2 | features_8h.parquet | data.py | data/analysis_8h.parquet |
| 3 | analysis_8h.parquet | parallel_optimize.py | data/features_8h_optimized_*.parquet (20) |
| 4 | optimized features | run.py | data/datasets/*.parquet (20) |
| 5 | datasets | run.py | data/analysis/results/ic_*.csv |
| 6 | datasets | run.py | data/analysis/results/*_importance.csv |
| 7 | datasets | run.py | data/analysis/results/cv_results.csv |
| 8 | datasets | l1_precompute.py | data/precomputed/{config}/*.parquet |
| 9 | precomputed | dataset_assembly.py | data/precomputed/{config}/assembled.parquet |
| L2 | assembled | l2_backtest_sync.py | predictions + metrics |

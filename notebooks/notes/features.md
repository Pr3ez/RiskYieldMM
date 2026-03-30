# HTF Features Notes

## Current Stored Feature Schema

Verified after the available-data feature expansion implementation.

- Current stored feature schema:
  - `1m` and `15m`: `128` feature columns per built HTF feature tree
  - legacy `5m`: `93` feature columns and intentionally unchanged
- Multi-regime authoritative trees:
  - `8h/B`: `1m=128`, `15m=128`
  - `8h/C`: `1m=128`, `15m=128`
  - `24h/B`: `1m=128`, `15m=128`
  - `24h/C`: `1m=128`, `15m=128`
  - `7d/B`: `1m=128`, `15m=128`
  - `7d/C`: `1m=128`, `15m=128`
- Legacy-only tree:
  - `8h/B/5m=93`

Current `1m` / `15m` stored files contain:
- `89` core OHLCV-based engine features
- `25` source-dependent fetched-data features
- `10` composite derivatives-pressure features
- `4` custom causal `D_*` distance features

Legacy `5m` remains the original OHLCV-only schema:
- `89` core OHLCV-based engine features
- `4` custom causal `D_*` distance features

## Window Meaning

The core engine scales windows by timeframe so they cover roughly the same time span:

- `short` ~= `1h`
- `med` ~= `2h`
- `long` ~= `4h`
- `xlong` ~= `8h`

Custom causal distance features use fixed windows by timeframe:

- `1m`: `w120`, `w240`
- `5m`: `w24`, `w48`
- `15m`: `w8`, `w16`

## How Features Are Built

- Source data comes from fetched parquet trees in `fetchingByBit`
- Combined HTF batch files are prepared first
- Features are computed on the full continuous combined series, not batch-by-batch
- For `1m` and `15m`, the continuous OHLCV stream is causally augmented with already-fetched auxiliary sources before feature computation:
  - `mark_price`
  - `index_price`
  - `premium_price`
  - `open_interest`
  - `long_short_ratio`
  - `funding_rate`
- If a source is not natively available at the target timeframe, the feature engine broadcasts the last available higher-timeframe value to the lower-timeframe rows using the existing causal merge rules
- After computation, features are split back into per-batch parquet files
- Family `C` feature files are materialized from timestamp-aligned base feature rows plus shifted-family metadata

This design avoids breaking long rolling windows at batch boundaries.

## Stored Feature Inventory

### Momentum And Price

- `M_P_logReturn_pct`: bar-to-bar log return
- `M_P_roc_short_pct`: short-window price rate of change
- `M_P_roc_med_pct`: medium-window price rate of change
- `M_P_roc_long_pct`: long-window price rate of change
- `M_P_V_momAtr_short_rat`: short-window momentum normalized by ATR
- `M_P_V_momAtr_med_rat`: medium-window momentum normalized by ATR
- `M_P_V_momAtr_long_rat`: long-window momentum normalized by ATR

### Volatility

- `V_atrPct_short_pct`: short-window ATR as percent of price
- `V_atrPct_med_pct`: medium-window ATR as percent of price
- `V_atrPct_long_pct`: long-window ATR as percent of price
- `V_returnStd_short_pct`: short-window return standard deviation
- `V_returnStd_med_pct`: medium-window return standard deviation
- `V_returnStd_long_pct`: long-window return standard deviation
- `V_parkinson_short_pct`: short-window Parkinson volatility
- `V_parkinson_med_pct`: medium-window Parkinson volatility
- `V_parkinson_long_pct`: long-window Parkinson volatility
- `V_garmanKlass_short_pct`: short-window Garman-Klass volatility
- `V_garmanKlass_med_pct`: medium-window Garman-Klass volatility
- `V_garmanKlass_long_pct`: long-window Garman-Klass volatility
- `V_yangZhang_short_pct`: short-window Yang-Zhang volatility
- `V_yangZhang_med_pct`: medium-window Yang-Zhang volatility
- `V_yangZhang_long_pct`: long-window Yang-Zhang volatility
- `N_V_bollingerBW_long_pct`: long-window Bollinger band width
- `N_V_bollingerBW_xlong_pct`: extra-long-window Bollinger band width

### Normalized Price Position

- `N_P_V_pctB_short_bnd`: price position inside short-window Bollinger bands
- `N_P_V_pctB_med_bnd`: price position inside medium-window Bollinger bands
- `N_P_V_pctB_long_bnd`: price position inside long-window Bollinger bands

### Trend

- `M_T_ppo_short_long_pct`: PPO using short vs long EMA pair
- `M_T_ppo_med_xlong_pct`: PPO using medium vs extra-long EMA pair
- `N_P_T_priceSmaDeviation_short_pct`: price deviation from short SMA
- `N_P_T_priceSmaDeviation_med_pct`: price deviation from medium SMA
- `N_P_T_priceSmaDeviation_long_pct`: price deviation from long SMA
- `N_P_T_priceEmaDeviation_short_pct`: price deviation from short EMA
- `N_P_T_priceEmaDeviation_med_pct`: price deviation from medium EMA
- `N_P_T_priceEmaDeviation_long_pct`: price deviation from long EMA

### Oscillators

- `M_N_rsi_short_bnd`: short-window RSI
- `M_N_rsi_med_bnd`: medium-window RSI
- `M_N_rsi_long_bnd`: long-window RSI
- `M_N_stochasticK_short_bnd`: short-window stochastic `%K`
- `M_N_stochasticK_med_bnd`: medium-window stochastic `%K`
- `M_N_stochasticK_long_bnd`: long-window stochastic `%K`
- `M_N_T_stochasticD_short_bnd`: short-window stochastic `%D`
- `M_N_T_stochasticD_med_bnd`: medium-window stochastic `%D`
- `M_N_T_stochasticD_long_bnd`: long-window stochastic `%D`

### Volume And Flow

- `L_M_N_volumeRoc_short_pct`: short-window volume rate of change
- `L_M_N_volumeRoc_med_pct`: medium-window volume rate of change
- `L_M_N_volumeRoc_long_pct`: long-window volume rate of change
- `L_N_volumeRatio_short_rat`: short-window current volume vs rolling average
- `L_N_volumeRatio_med_rat`: medium-window current volume vs rolling average
- `L_N_volumeRatio_long_rat`: long-window current volume vs rolling average
- `L_M_S_obv_long_zsc`: long-window OBV z-score
- `L_M_S_obv_xlong_zsc`: extra-long-window OBV z-score
- `L_M_S_mfi_long_bnd`: long-window Money Flow Index
- `L_M_S_mfi_xlong_bnd`: extra-long-window Money Flow Index
- `L_M_S_cmf_long_bnd`: long-window Chaikin Money Flow
- `L_M_S_cmf_xlong_bnd`: extra-long-window Chaikin Money Flow

### Trend Strength

- `M_T_V_adx_short_bnd`: short-window ADX
- `M_T_V_adx_med_bnd`: medium-window ADX
- `M_T_V_diDiff_short_bnd`: short-window directional movement imbalance
- `M_T_V_diDiff_med_bnd`: medium-window directional movement imbalance
- `N_M_cci_short_zsc`: short-window CCI
- `N_M_cci_med_zsc`: medium-window CCI

### Regime Detection

- `V_autocorr_med_bnd`: medium-window autocorrelation
- `V_autocorr_long_bnd`: long-window autocorrelation
- `N_P_zScore_med_zsc`: medium-window price z-score
- `N_P_zScore_long_zsc`: long-window price z-score
- `V_volMomentum_med_pct`: medium-window volatility momentum
- `V_volMomentum_long_pct`: long-window volatility momentum

### Distribution Shape

- `V_skew_med_rat`: medium-window return skewness
- `V_skew_long_rat`: long-window return skewness
- `V_skew_xlong_rat`: extra-long-window return skewness
- `V_kurtosis_med_rat`: medium-window return kurtosis
- `V_kurtosis_long_rat`: long-window return kurtosis
- `V_kurtosis_xlong_rat`: extra-long-window return kurtosis

### Risk Metrics

- `V_maxDrawdown_long_pct`: long-window maximum drawdown
- `V_maxDrawdown_xlong_pct`: extra-long-window maximum drawdown
- `M_V_sharpe_long_rat`: long-window Sharpe ratio
- `M_V_sharpe_xlong_rat`: extra-long-window Sharpe ratio
- `M_V_sortino_long_rat`: long-window Sortino ratio
- `M_V_sortino_xlong_rat`: extra-long-window Sortino ratio

### Candlestick And Direction

- `C_N_bodySize_bnd`: candle body size
- `C_N_upperShadow_bnd`: upper wick size
- `C_N_lowerShadow_bnd`: lower wick size
- `B_C_candleDirection_bin`: bullish vs bearish candle direction
- `B_consecutiveUp_bnd`: run length of consecutive up candles
- `B_consecutiveDown_bnd`: run length of consecutive down candles
- `M_winRate_short_bnd`: short-window share of positive-return bars
- `M_winRate_med_bnd`: medium-window share of positive-return bars
- `M_winRate_long_bnd`: long-window share of positive-return bars

### Custom Causal Distance Features

These are added on top of the core engine and are computed only from past OHLCV inside the current batch context.

- `D_dist_bot5_low_w*`: distance from current close to the bottom-tail average of past lows
- `D_dist_avg_high_w*`: distance from current close to the average of past highs
- `D_dist_avg_low_w*`: distance from current close to the average of past lows
- `D_dist_top5_high_w*`: distance from current close to the top-tail average of past highs

Current stored variants:

- `1m`:
  - `D_dist_bot5_low_w120`
  - `D_dist_avg_high_w240`
  - `D_dist_avg_low_w240`
  - `D_dist_top5_high_w240`
- `5m`:
  - `D_dist_bot5_low_w24`
  - `D_dist_avg_high_w48`
  - `D_dist_avg_low_w48`
  - `D_dist_top5_high_w48`
- `15m`:
  - `D_dist_bot5_low_w8`
  - `D_dist_avg_high_w16`
  - `D_dist_avg_low_w16`
  - `D_dist_top5_high_w16`

### Source-Dependent Fetched-Data Features

These are now present in stored `1m` and `15m` HTF feature files. They are not built for the legacy `5m` tree.

Open interest:
- `L_M_N_S_oiPctChange_pct`: one-step percentage change in open interest
- `L_N_volOiRatio_rat`: current traded volume divided by current open interest
- `L_M_N_S_oiRoc_short_pct`: short-window open-interest rate of change
- `L_M_N_S_oiRoc_med_pct`: medium-window open-interest rate of change
- `L_M_N_S_oiRoc_long_pct`: long-window open-interest rate of change

Funding:
- `F_I_fundingCumulative_short_pct`: short-window cumulative funding
- `F_I_fundingCumulative_med_pct`: medium-window cumulative funding
- `F_I_fundingCumulative_long_pct`: long-window cumulative funding
- `F_I_T_fundingMa_short_pct`: short-window funding moving average
- `F_I_T_fundingMa_med_pct`: medium-window funding moving average
- `F_I_T_fundingMa_long_pct`: long-window funding moving average
- `F_I_N_S_fundingZscore_long_zsc`: long-window funding z-score
- `F_I_N_S_fundingZscore_xlong_zsc`: extra-long-window funding z-score

Long/short ratio:
- `S_longShortRatio_rat`: raw long/short ratio
- `S_M_longShortChange_short_pct`: short-window long/short ratio change
- `S_M_longShortChange_med_pct`: medium-window long/short ratio change
- `S_N_longShortZscore_long_zsc`: long-window long/short ratio z-score
- `S_N_longShortZscore_xlong_zsc`: extra-long-window long/short ratio z-score

Derivatives pricing:
- `D_F_basis_pct`: basis between futures close and index close
- `D_N_markCloseDeviation_pct`: close-vs-mark deviation
- `D_F_T_premiumMa_short_pct`: short-window premium moving average
- `D_F_T_premiumMa_med_pct`: medium-window premium moving average
- `D_F_T_premiumMa_long_pct`: long-window premium moving average
- `D_F_N_S_premiumZscore_long_zsc`: long-window premium z-score
- `D_F_N_S_premiumZscore_xlong_zsc`: extra-long-window premium z-score

### Composite Derivatives-Pressure Features

These combine currently fetched derivatives-state inputs with returns. They are present in stored `1m` and `15m` HTF feature files only.

- `X_D_oiRetPressure_short_pct`: rolling mean of `ΔOI × log return` over the short window
- `X_D_oiRetPressure_med_pct`: rolling mean of `ΔOI × log return` over the medium window
- `X_D_oiRetPressure_long_pct`: rolling mean of `ΔOI × log return` over the long window
- `X_D_basisRetPressure_short_pct`: rolling mean of `basis × log return` over the short window
- `X_D_basisRetPressure_med_pct`: rolling mean of `basis × log return` over the medium window
- `X_D_basisRetPressure_long_pct`: rolling mean of `basis × log return` over the long window
- `X_D_fundingBasisPressure_long_pct`: rolling mean of `funding × basis` over the long window
- `X_D_fundingBasisPressure_xlong_pct`: rolling mean of `funding × basis` over the extra-long window
- `X_D_longShortRetPressure_long_pct`: rolling mean of `pct_change(longShortRatio) × log return` over the long window
- `X_D_longShortRetPressure_xlong_pct`: rolling mean of `pct_change(longShortRatio) × log return` over the extra-long window

## Practical Takeaway

- Current `1m` and `15m` HTF feature files use the richer `128`-feature schema
- Legacy `5m` remains on the older `93`-feature schema by design
- The same `128`-feature list is now used across `8h`, `24h`, and `7d`
- Differences between regimes still come from batch geometry and metadata, not from a different feature list

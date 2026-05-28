# HTF Feature And Helper Inventory

## Purpose

List the current HTF feature and helper families produced by the
`htf_pythonscript` workflow, explain their intended purpose, and define how
they should be treated when designing regression-optimized features.

## Current Status

Inventory and design guidance only. No existing HTF feature is removed or
rewritten by this document.

## Scope

Applies to current model-facing `htf_with_helpers` features used as candidate
context for `regression_path_features_v1` and `distance_horizon_vol_v2`.

## Source Of Truth

- HTF feature formulas: `scripts/feature_engineering/compute_htf_features.py`
- Helper cache and materialization: `scripts/feature_engineering/htf_helper_cache.py`
- Helper implementations: `scripts/target_models/helpers/`
- Current feature inventory summary: `current_htf_feature_inventory.md`

## What This Does Not Decide

This document does not promote any feature into the regression feature set. It
documents purpose and likely regression use so future optimization can decide
with walk-forward evidence.

## Current Feature Surface

The current BTCUSDT `8h/B` all-core merged regression root contains:

- `1,162` model feature columns;
- about `169` target BTC features;
- about `992` context features;
- one unprefixed `bar_in_batch_norm` feature.

Feature availability differs by asset. Crypto assets have derivatives-specific
features from open interest, funding, long/short ratio, mark/index/premium
sources. Session assets mostly have OHLCV-derived features and helper outputs.

## Naming Convention

Current merged Stage-1 feature names use:

- `T_<asset>__<feature>` for target-asset features;
- `C_<asset>__<feature>` for context-asset features;
- unprefixed `bar_in_batch_norm` for target batch position.

Feature prefixes indicate broad intent:

| Prefix | Meaning | Current Role |
|---|---|---|
| `M_*` | momentum, trend, oscillator, risk-adjusted momentum | direction/regime context |
| `V_*` | volatility, distribution, drawdown | volatility denominator and risk state |
| `N_*` | normalized price/band/value position | location and mean-reversion context |
| `L_*` | liquidity, volume, money flow, open interest | participation/pressure context |
| `B_*` | binary candle/run state | short-term directional state |
| `C_*` | candle geometry | rejection and candle pressure context |
| `D_*` | derivatives/basis/premium/distance features | crypto-specific market structure |
| `F_*` | funding-rate features | crypto carry/positioning context |
| `S_*` | long/short ratio features | crypto sentiment/positioning context |
| `X_*` | composite derivatives-pressure features | crypto pressure interaction context |
| `H_*` | helper-model outputs | state-space, change-point, volatility-model context |

## OHLCV And Batch Position

| Feature Template | Purpose | Regression Treatment |
|---|---|---|
| `open`, `high`, `low`, `close`, `volume` | raw market bars retained in some merged roots | Do not use raw unscaled OHLCV as model-facing regression features. Re-express as normalized room, pressure, or path-shape features. |
| `bar_in_batch_norm` | normalized row position inside the family entry window | Keep only as timing context. Audit separately because it can proxy label-window geometry. |

## Momentum And Direction Features

| Feature Template | Purpose | Regression Treatment |
|---|---|---|
| `M_P_logReturn_pct` | current log return | Useful as immediate impulse, but insufficient alone for distance targets. |
| `M_P_roc_{short,med,long}_pct` | trailing price rate of change | Directional pressure candidate for up/down targets. Optimize target-specific sign and horizon. |
| `M_P_V_momAtr_{short,med,long}_rat` | momentum normalized by ATR | Useful for impulse scaled by local volatility. Compare against horizon-vol-normalized room features. |
| `M_T_ppo_short_long_pct`, `M_T_ppo_med_xlong_pct` | moving-average trend spread | Broad trend context. Better for mean targets than extreme targets. |
| `M_N_rsi_{short,med,long}_bnd` | bounded momentum oscillator | Overbought/oversold context. Needs pairing with room/rejection features. |
| `M_N_stochasticK_*_bnd`, `M_N_T_stochasticD_*_bnd` | range-position oscillator | Acceptance/rejection context if combined with close-location features. |
| `M_T_V_adx_{short,med}_bnd` | trend strength | Gate persistence features; does not indicate direction alone. |
| `M_T_V_diDiff_{short,med}_bnd` | DMI directional imbalance | Candidate for up/down pressure. Validate stability by target. |
| `M_V_sharpe_{long,xlong}_rat`, `M_V_sortino_{long,xlong}_rat` | risk-adjusted trailing return | Directional quality context. Likely slow-moving and redundant with volatility/momentum. |
| `M_winRate_{short,med,long}_bnd` | share of recent positive bars | Persistence context. Useful for mean-high/mean-low targets if direction-specific. |

## Volatility And Distribution Features

| Feature Template | Purpose | Regression Treatment |
|---|---|---|
| `V_atrPct_{short,med,long}_pct` | ATR as price percentage | Core denominator-quality context. Must be compared to label horizon volatility. |
| `V_returnStd_{short,med,long}_pct` | trailing return volatility | Core denominator-quality context. Useful when ATR/std dominance matters. |
| `V_parkinson_*_pct`, `V_garmanKlass_*_pct`, `V_yangZhang_*_pct` | range-based volatility estimators | High-value context for future path width; likely important for all targets. |
| `N_V_bollingerBW_{long,xlong}_pct` | Bollinger bandwidth/compression | Useful for spike/breakout targets and volatility expansion potential. |
| `V_autocorr_{med,long}_bnd` | lag-1 return autocorrelation | Helps separate persistence from mean reversion/chop. |
| `V_volMomentum_{med,long}_pct` | change in volatility | Useful for expansion/exhaustion state. |
| `V_skew_{med,long,xlong}_rat` | trailing return skewness | Tail asymmetry context. Candidate for extreme targets. |
| `V_kurtosis_{med,long,xlong}_rat` | trailing return kurtosis | Tail/thin-liquidity context. Candidate for extreme targets. |
| `V_maxDrawdown_{long,xlong}_pct` | trailing adverse excursion | Downside fragility and regime stress context. |

## Normalized Location Features

| Feature Template | Purpose | Regression Treatment |
|---|---|---|
| `N_P_V_pctB_{short,med,long}_bnd` | price location inside Bollinger bands | Useful for structural location but not enough for distance-to-level. Needs explicit room features. |
| `N_P_T_priceSmaDeviation_*_pct` | distance from SMA | Value-location context. Normalize by horizon volatility for regression-specific variants. |
| `N_P_T_priceEmaDeviation_*_pct` | distance from EMA | Same as SMA deviation with faster response. |
| `N_P_zScore_{med,long}_zsc` | z-score of price versus trailing mean | Mean-reversion/stretch context. Must be clipped and audited for outliers. |
| `N_M_cci_{short,med}_zsc` | commodity-channel index | Stretch/reversion context. Useful only if stable across windows. |

## Liquidity, Volume, And Participation Features

| Feature Template | Purpose | Regression Treatment |
|---|---|---|
| `L_M_N_volumeRoc_{short,med,long}_pct` | volume rate of change | Participation acceleration. Useful for breakout/spike confirmation. |
| `L_N_volumeRatio_{short,med,long}_rat` | volume relative to trailing norm | Confirmation of pressure or illiquidity state. |
| `L_M_S_obv_{long,xlong}_zsc` | OBV z-score | Directional volume accumulation context. |
| `L_M_S_mfi_{long,xlong}_bnd` | money flow index | Volume-weighted oscillator. Candidate for acceptance/rejection. |
| `L_M_S_cmf_{long,xlong}_bnd` | Chaikin money flow | Sustained accumulation/distribution context. |
| `L_M_N_S_oiPctChange_pct` | open-interest percent change | Crypto participation/leverage state. |
| `L_N_volOiRatio_rat` | volume divided by open interest | Turnover relative to positioning. |
| `L_M_N_S_oiRoc_{short,med,long}_pct` | open-interest ROC | Positioning expansion/contraction context. |

## Candle Shape And Microstructure Proxies

| Feature Template | Purpose | Regression Treatment |
|---|---|---|
| `C_N_bodySize_bnd` | candle body relative to range | Immediate conviction proxy. |
| `C_N_upperShadow_bnd` | upper wick share | Rejection above current price; important for up-mean vs up-extreme separation. |
| `C_N_lowerShadow_bnd` | lower wick share | Rejection below current price; important for down-mean vs down-extreme separation. |
| `B_C_candleDirection_bin` | up/down candle direction | Basic direction context only. |
| `B_consecutiveUp_bnd`, `B_consecutiveDown_bnd` | recent run length | Persistence context; should be paired with pullback/acceptance features. |

## Crypto Derivatives And Positioning Features

| Feature Template | Purpose | Regression Treatment |
|---|---|---|
| `F_I_fundingCumulative_{short,med,long}_pct` | rolling funding carry | Crowded-position context. |
| `F_I_T_fundingMa_{short,med,long}_pct` | funding moving average | Smoother carry pressure context. |
| `S_longShortRatio_rat` | account long/short ratio | Sentiment/positioning imbalance. |
| `S_M_longShortChange_{short,med}_pct` | long/short ratio change | Sentiment momentum. |
| `S_N_longShortZscore_{long,xlong}_zsc` | long/short ratio z-score | Positioning stretch. |
| `D_F_basis_pct` | index/mark basis | Futures basis pressure. |
| `D_N_markCloseDeviation_pct` | mark-close deviation | Mark/index dislocation. |
| `D_F_T_premiumMa_{short,med,long}_pct` | premium moving average | Smoothed premium pressure. |
| `D_F_N_S_premiumZscore_{long,xlong}_zsc` | premium z-score | Premium stretch/dislocation. |
| `X_D_oiRetPressure_{short,med,long}_pct` | open-interest change times return | Leveraged directional pressure. |
| `X_D_basisRetPressure_{short,med,long}_pct` | basis times return | Basis-confirmed directional pressure. |
| `X_D_fundingBasisPressure_{long,xlong}_pct` | funding times basis | Carry/basis crowding pressure. |
| `X_D_longShortRetPressure_{long,xlong}_pct` | long/short change times return | Sentiment-confirmed directional pressure. |

These features exist only where the underlying source exists. For non-crypto
assets, the regression workflow must not assume these columns are present.

## Existing Distance Feature

| Feature Template | Purpose | Regression Treatment |
|---|---|---|
| `D_dist_bot5_low_w120` | existing past downside distance statistic | Keep as historical context, but redesign distance features explicitly for both upside and downside room in horizon-volatility units. |

The original HTF feature policy excluded some batch-local distance features
from final outputs because they were structurally incompatible with front-half
saved rows. The regression workflow should rebuild distance/room features from
canonical history with explicit causal windows.

## Helper Feature Inventory

Helper outputs are prefixed as `H_*`. They are valuable state estimates, but
they should be treated as context features rather than complete regression
features.

### OU Helper

Purpose: mean-reversion and stationarity state from rolling AR(1)/OU behavior.

| Feature Template | Purpose | Regression Treatment |
|---|---|---|
| `H_*_ou_phi` | AR(1) coefficient | Mean-reversion versus persistence context. |
| `H_*_ou_kappa` | mean-reversion speed | Helps estimate whether stretched moves may revert. |
| `H_*_ou_halflife` | bars to decay 50% | Persistence/reversion timing context. |
| `H_*_ou_zscore`, `H_*_ou_zscore_abs` | deviation from mean | Stretch context; clip and audit outliers. |
| `H_*_ou_is_stationary` | stationarity flag | Gate for mean-reversion features. |
| `H_*_ou_halflife_regime` | fast/optimal/slow reversion regime | Context for persistence targets. |
| `H_*_ou_reverting` | currently moving toward mean | Rejection/reversion context. |

### GARCH Helper

Purpose: conditional volatility and volatility clustering state.

| Feature Template | Purpose | Regression Treatment |
|---|---|---|
| `H_*_garch_cond_vol` | conditional volatility | Denominator-quality and future range context. |
| `H_*_garch_vol_forecast` | next-step volatility forecast | Vol expansion context. |
| `H_*_garch_vol_zscore` | vol relative to history | Compression/expansion context. |
| `H_*_garch_vol_shock` | standardized residual | Shock/tail context. |
| `H_*_garch_persistence` | fitted persistence | Audit for constants before use. |
| `H_*_garch_vol_regime` | low/medium/high vol regime | Regime gate for all targets. |
| `H_*_garch_vol_change` | conditional vol change | Expansion/exhaustion signal. |
| `H_*_garch_vol_ratio` | current versus long-run vol | Vol denominator quality context. |

### CUSUM Helper

Purpose: return and volatility change-point detection.

| Feature Template | Purpose | Regression Treatment |
|---|---|---|
| `H_*_cusum_ret_pos`, `H_*_cusum_ret_neg` | positive/negative return CUSUM | Breakout/breakdown pressure context. |
| `H_*_cusum_vol_pos`, `H_*_cusum_vol_neg` | positive/negative volatility CUSUM | Volatility regime transition context. |
| `H_*_cp_ret_up`, `H_*_cp_ret_down` | return changepoint flags | Spike/breakdown event context. |
| `H_*_cp_vol_up`, `H_*_cp_vol_down` | volatility changepoint flags | Expansion trigger context. |
| `H_*_cp_any` | any changepoint | General regime shift flag. |
| `H_*_cp_magnitude` | detected change magnitude | Tail-risk context. |
| `H_*_days_since_cp` | recency of last changepoint | Persistence/exhaustion timing. |
| `H_*_cp_count_21` | recent changepoint density | Chop/unstable regime context. |

### Kalman Helper

Purpose: streaming state estimate of price level, velocity, acceleration, and
innovation.

| Feature Template | Purpose | Regression Treatment |
|---|---|---|
| `H_*_kalman_filtered_dev` | distance from filtered state | Structural stretch context. |
| `H_*_kalman_velocity` | estimated trend velocity | Directional pressure context. |
| `H_*_kalman_acceleration` | velocity change | Impulse and exhaustion context. |
| `H_*_kalman_pred_error` | model prediction error | Shock/rejection context. |
| `H_*_kalman_innovation` | filter innovation | Unexpected move context. |
| `H_*_kalman_zscore` | innovation/velocity z-score | Clip and audit for outliers. |
| `H_*_kalman_regime` | velocity regime | Persistence gate. |

### EGARCH Helper

Purpose: streaming asymmetric volatility and leverage/shock state.

| Feature Template | Purpose | Regression Treatment |
|---|---|---|
| `H_*_egarch_vol`, `H_*_egarch_log_vol` | asymmetric conditional volatility | Denominator-quality and future range context. |
| `H_*_egarch_news_impact` | effect of latest standardized shock | Spike/tail context. |
| `H_*_egarch_vol_zscore` | vol relative to running state | Compression/expansion context. |
| `H_*_egarch_vol_regime` | low/medium/high vol regime | Regime gate for all targets. |
| `H_*_egarch_leverage_active` | recent downside shock state | Downside extreme and risk-off context. |

`H_*_egarch_asymmetry` and `H_*_egarch_persistence` are intentionally excluded
from current helper outputs because previous audits found them degenerate in the
model-facing helper contract.

## Regression Optimization Guidance

Current HTF/helper features should be treated as context, not as the final
regression feature design. Optimization should answer these questions per
target:

- Does the feature explain rank ordering of future path distance?
- Does it help the high-distance tail instead of only predicting the middle?
- Is it stable across chronological windows?
- Is it unique after deduplication against similar volatility/helper features?
- Does it represent a target-needed concept: volatility state, structural room,
  acceptance, persistence, spike capacity, rejection, chop, or cross-asset
  pressure?

For regression review, `cross_asset_context` should be summarized as
cross-asset pressure only when it adds information beyond the target asset's
own volatility, room, and path-shape state.

Features that fail these checks can remain valid classification context, but
should not be promoted into `regression_path_features_v1`.

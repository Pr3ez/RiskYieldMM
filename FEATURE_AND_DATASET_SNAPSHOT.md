# Feature and Dataset Snapshot

Last verified: 2026-04-30

The raw and model-facing datasets are generated locally and are ignored by Git. This keeps the repository reviewable without uploading large market-data artifacts, while this page gives enough structure for a reviewer to understand what the pipeline builds.

This is a documentation snapshot, not a trading claim. The representative rows below come from local `8h/B` artifacts used by the walk-forward analysis snapshot.

## Why The Data Is Not Uploaded

The `data/` directory contains generated Parquet batches, helper caches, model runs, and backtest artifacts. These files are large, frequently regenerated, and tied to local experiment state. The repository therefore tracks code, tests, audits, and selected `test_output/` summaries instead of the raw generated dataset.

The important review surface is still visible:

- how the data is shaped,
- what columns are present,
- how temporal metadata prevents accidental mixing of regimes,
- which features are model-facing,
- and what a real row looks like.

## Local Artifact Layout

The active model-facing HTF path has six regime/family roots. Each root has helper-enriched features and labels:

| Root | Feature path | Label path | Full entry-window rows per batch |
|---|---|---|---:|
| `8h/B` | `data/htf_with_helpers/1m/target_4class` | `data/htf_4class_labels/1m` | 240 |
| `8h/C` | `data/htf_with_helpers_shift4h/1m/target_4class` | `data/htf_4class_labels_shift4h/1m` | 240 |
| `24h/B` | `data/htf_with_helpers_24h/1m/target_4class` | `data/htf_4class_labels_24h/1m` | 720 |
| `24h/C` | `data/htf_with_helpers_24h_shift12h/1m/target_4class` | `data/htf_4class_labels_24h_shift12h/1m` | 720 |
| `7d/B` | `data/htf_with_helpers_7d/1m/target_4class` | `data/htf_4class_labels_7d/1m` | 5,040 |
| `7d/C` | `data/htf_with_helpers_7d_shift84h/1m/target_4class` | `data/htf_4class_labels_7d_shift84h/1m` | 5,040 |

For `1m` data, the label files contain the full regime duration (`8h = 480 rows`, `24h = 1,440 rows`, `7d = 10,080 rows`). Model-facing helper files keep the valid entry-window rows only. For `8h/B`, that is the first 4 hours of each 8 hour batch.

## Schema Summary

Representative file inspected:

`data/htf_with_helpers/1m/target_4class/batch_5170.parquet`

Shape:

| Component | Count | Notes |
|---|---:|---|
| Base engineered features | 123 | Technical, derivatives, funding, sentiment, and interaction features |
| Helper features | 41 | OU, GARCH, CUSUM/change-point, Kalman, EGARCH |
| OHLCV columns | 5 | Present in model-facing output after final transformation |
| Position column | 1 | `bar_in_batch_norm` |
| Batch/family metadata | 17 | Regime, family, batch, anchor, and entry-window context |
| Total model-facing columns | 187 | Current `8h/B` helper-enriched schema |

Representative label file:

`data/htf_4class_labels/1m/batch_5170.parquet`

Shape:

| Component | Count | Notes |
|---|---:|---|
| Raw OHLCV and batch positions | 10 | `timestamp`, OHLCV, batch id, bar positions |
| Distance/target support columns | 14 | Bollinger position, forward-distance metrics, end return, labels |
| Batch/family metadata | 16 | Family, source base batch, regime, entry-window context |
| Total label columns | 40 | Full-batch label schema |

## Feature Naming Convention

Feature names use compact prefixes:

| Prefix | Meaning |
|---|---|
| `M` | Momentum or return behavior |
| `V` | Volatility or risk shape |
| `T` | Trend |
| `N` | Normalized, bounded, or z-score context |
| `L` | Liquidity, volume, or open interest |
| `D` | Derivatives, basis, mark, or premium context |
| `F` | Funding |
| `S` | Sentiment or long/short positioning |
| `B` | Binary or simple pattern state |
| `C` | Candlestick structure |
| `P` | Price |
| `X` | Cross/interactions |
| `H` | Helper-model feature |

Common suffixes:

| Suffix | Meaning |
|---|---|
| `_pct` | Percent or percent-like scale |
| `_rat` | Ratio |
| `_zsc` | Z-score |
| `_bnd` | Bounded value |
| `_bin` | Binary/categorical indicator |

## Feature Inventory

The current `8h/B` model-facing schema has 123 base engineered feature columns and 41 helper feature columns.

| Group | Count | Examples |
|---|---:|---|
| Momentum/returns `M` | 29 | log return, ROC, PPO, RSI, stochastic, win rate, Sharpe/Sortino |
| Volatility/risk `V` | 27 | ATR percent, return std, Parkinson/Garman-Klass/Yang-Zhang, skew/kurtosis, drawdown |
| Liquidity/volume `L` | 17 | volume ROC, volume ratio, OBV, MFI, CMF, open-interest change |
| Normalized context `N` | 15 | Bollinger bandwidth/%B, price SMA/EMA deviation, CCI, price z-score |
| Cross interactions `X` | 10 | OI-return pressure, basis-return pressure, funding-basis pressure |
| Derivatives `D` | 8 | basis, mark-close deviation, premium moving averages/z-scores, distance metric |
| Funding `F` | 6 | funding cumulative and funding moving average features |
| Sentiment `S` | 5 | long/short ratio, changes, z-scores |
| Binary/pattern `B` | 3 | candle direction, consecutive up/down |
| Candlestick `C` | 3 | body size, upper shadow, lower shadow |
| Helper models `H` | 41 | OU, GARCH, CUSUM/change-point, Kalman, EGARCH |

### Base Engineered Features

```text
M_P_logReturn_pct
M_P_roc_short_pct
M_P_V_momAtr_short_rat
M_P_roc_med_pct
M_P_V_momAtr_med_rat
M_P_roc_long_pct
M_P_V_momAtr_long_rat
V_atrPct_short_pct
V_returnStd_short_pct
V_parkinson_short_pct
V_garmanKlass_short_pct
V_yangZhang_short_pct
V_atrPct_med_pct
V_returnStd_med_pct
V_parkinson_med_pct
V_garmanKlass_med_pct
V_yangZhang_med_pct
V_atrPct_long_pct
V_returnStd_long_pct
V_parkinson_long_pct
V_garmanKlass_long_pct
V_yangZhang_long_pct
N_V_bollingerBW_long_pct
N_V_bollingerBW_xlong_pct
N_P_V_pctB_short_bnd
N_P_V_pctB_med_bnd
N_P_V_pctB_long_bnd
M_T_ppo_short_long_pct
M_T_ppo_med_xlong_pct
N_P_T_priceSmaDeviation_short_pct
N_P_T_priceEmaDeviation_short_pct
N_P_T_priceSmaDeviation_med_pct
N_P_T_priceEmaDeviation_med_pct
N_P_T_priceSmaDeviation_long_pct
N_P_T_priceEmaDeviation_long_pct
M_N_rsi_short_bnd
M_N_stochasticK_short_bnd
M_N_T_stochasticD_short_bnd
M_N_rsi_med_bnd
M_N_stochasticK_med_bnd
M_N_T_stochasticD_med_bnd
M_N_rsi_long_bnd
M_N_stochasticK_long_bnd
M_N_T_stochasticD_long_bnd
L_M_N_volumeRoc_short_pct
L_N_volumeRatio_short_rat
L_M_N_volumeRoc_med_pct
L_N_volumeRatio_med_rat
L_M_N_volumeRoc_long_pct
L_N_volumeRatio_long_rat
L_M_S_obv_long_zsc
L_M_S_mfi_long_bnd
L_M_S_cmf_long_bnd
L_M_S_obv_xlong_zsc
L_M_S_mfi_xlong_bnd
L_M_S_cmf_xlong_bnd
M_T_V_adx_short_bnd
M_T_V_diDiff_short_bnd
N_M_cci_short_zsc
M_T_V_adx_med_bnd
M_T_V_diDiff_med_bnd
N_M_cci_med_zsc
V_autocorr_med_bnd
N_P_zScore_med_zsc
V_volMomentum_med_pct
V_autocorr_long_bnd
N_P_zScore_long_zsc
V_volMomentum_long_pct
V_skew_med_rat
V_kurtosis_med_rat
V_skew_long_rat
V_kurtosis_long_rat
V_skew_xlong_rat
V_kurtosis_xlong_rat
V_maxDrawdown_long_pct
M_V_sharpe_long_rat
M_V_sortino_long_rat
V_maxDrawdown_xlong_pct
M_V_sharpe_xlong_rat
M_V_sortino_xlong_rat
C_N_bodySize_bnd
C_N_upperShadow_bnd
C_N_lowerShadow_bnd
B_C_candleDirection_bin
B_consecutiveUp_bnd
B_consecutiveDown_bnd
M_winRate_short_bnd
M_winRate_med_bnd
M_winRate_long_bnd
L_M_N_S_oiPctChange_pct
L_N_volOiRatio_rat
L_M_N_S_oiRoc_short_pct
L_M_N_S_oiRoc_med_pct
L_M_N_S_oiRoc_long_pct
F_I_fundingCumulative_short_pct
F_I_T_fundingMa_short_pct
F_I_fundingCumulative_med_pct
F_I_T_fundingMa_med_pct
F_I_fundingCumulative_long_pct
F_I_T_fundingMa_long_pct
S_longShortRatio_rat
S_M_longShortChange_short_pct
S_M_longShortChange_med_pct
S_N_longShortZscore_long_zsc
S_N_longShortZscore_xlong_zsc
D_F_basis_pct
D_N_markCloseDeviation_pct
D_F_T_premiumMa_short_pct
D_F_T_premiumMa_med_pct
D_F_T_premiumMa_long_pct
D_F_N_S_premiumZscore_long_zsc
D_F_N_S_premiumZscore_xlong_zsc
X_D_oiRetPressure_short_pct
X_D_oiRetPressure_med_pct
X_D_oiRetPressure_long_pct
X_D_basisRetPressure_short_pct
X_D_basisRetPressure_med_pct
X_D_basisRetPressure_long_pct
X_D_fundingBasisPressure_long_pct
X_D_fundingBasisPressure_xlong_pct
X_D_longShortRetPressure_long_pct
X_D_longShortRetPressure_xlong_pct
D_dist_bot5_low_w120
```

### Helper Features

```text
H_4class_1_ou_phi
H_4class_1_ou_kappa
H_4class_1_ou_halflife
H_4class_1_ou_zscore
H_4class_1_ou_zscore_abs
H_4class_1_ou_is_stationary
H_4class_1_ou_halflife_regime
H_4class_1_ou_reverting
H_4cl_1_garch_cond_vol
H_4cl_1_garch_vol_forecast
H_4cl_1_garch_vol_zscore
H_4cl_1_garch_vol_shock
H_4cl_1_garch_persistence
H_4cl_1_garch_vol_regime
H_4cl_1_garch_vol_change
H_4cl_1_garch_vol_ratio
H_4cl_1_cusum_ret_pos
H_4cl_1_cusum_ret_neg
H_4cl_1_cusum_vol_pos
H_4cl_1_cusum_vol_neg
H_4cl_1_cp_ret_up
H_4cl_1_cp_ret_down
H_4cl_1_cp_vol_up
H_4cl_1_cp_vol_down
H_4cl_1_cp_any
H_4cl_1_cp_magnitude
H_4cl_1_days_since_cp
H_4cl_1_cp_count_21
H_4class_1_kalman_filtered_dev
H_4class_1_kalman_velocity
H_4class_1_kalman_acceleration
H_4class_1_kalman_pred_error
H_4class_1_kalman_innovation
H_4class_1_kalman_zscore
H_4class_1_kalman_regime
H_4class_1_egarch_vol
H_4class_1_egarch_log_vol
H_4class_1_egarch_news_impact
H_4class_1_egarch_vol_zscore
H_4class_1_egarch_vol_regime
H_4class_1_egarch_leverage_active
```

## Representative Dataset Snippet

Source:

`data/htf_4class_labels/1m/batch_5170.parquet`

This is a raw label/target view for `8h/B`, batch `5170`, starting `2025-09-20 00:00:00 UTC`. The first five rows shown are inside the 4h entry window. The final row shown is the first row outside the entry window, where `target_4class` is set to `-1`.

| timestamp | batch_id | bar_pos_1m | open | high | low | close | volume | bb_position_pct | dist_top5_high | dist_bot5_low | end_return | target_4class | target_name | target_breakfree | is_label_half | batch_regime | batch_duration_hours | entry_window_hours |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2025-09-20 00:00:00Z | 5170 | 0 | 115573 | 115573 | 115538 | 115550 | 18.219 | 67.1141 | 0.339247 | 0.164431 | 0.0032765 | 3 | UP_EXPANSION | 0 | True | 8h | 8 | 4 |
| 2025-09-20 01:00:00Z | 5170 | 60 | 115677 | 115686 | 115670 | 115670 | 14.991 | 61.5276 | 0.235152 | 0.268004 | 0.00223567 | 0 | DOWN_BALANCED | 2 | True | 8h | 8 | 4 |
| 2025-09-20 02:00:00Z | 5170 | 120 | 115562 | 115563 | 115521 | 115522 | 66.525 | -24.8936 | 0.363828 | 0.139974 | 0.00352228 | 3 | UP_EXPANSION | 0 | True | 8h | 8 | 4 |
| 2025-09-20 03:00:00Z | 5170 | 180 | 115551 | 115560 | 115551 | 115560 | 4.213 | 78.404 | 0.330911 | 0.172725 | 0.00319316 | 3 | UP_EXPANSION | 0 | True | 8h | 8 | 4 |
| 2025-09-20 03:59:00Z | 5170 | 239 | 115406 | 115406 | 115406 | 115406 | 2.375 | 38.0207 | 0.464273 | 0.0347468 | 0.00452662 | 2 | UP_BALANCED | 0 | True | 8h | 8 | 4 |
| 2025-09-20 04:00:00Z | 5170 | 240 | 115406 | 115406 | 115399 | 115399 | 10.129 | 34.8663 | 0.470454 | 0.0285964 | 0.00458842 | -1 | UP_BALANCED | -1 | False | 8h | 8 | 4 |

## Model-Facing Row Excerpt

Source:

`data/htf_with_helpers/1m/target_4class/batch_5170.parquet`

This view is what the Stage-1 model consumes after final feature preparation. Several values, including OHLCV, are transformed by the feature pipeline and should not be read as raw exchange prices.

| timestamp | batch_id | family_bar_pos | bar_in_batch_norm | open | close | M_P_logReturn_pct | V_atrPct_med_pct | M_N_rsi_med_bnd | D_F_basis_pct | S_longShortRatio_rat | H_4class_1_ou_zscore | H_4cl_1_garch_cond_vol | H_4class_1_kalman_velocity | target_4class | target_name |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2025-09-20 00:00:00Z | 5170 | 0 | -0.98 | -0.729167 | -0.735417 | -0.55625 | -0.98 | 0.8125 | -0.691667 | 0.98 | -1.41133 | 0.000316285 | -0.0000721599 | 3 | UP_EXPANSION |
| 2025-09-20 01:00:00Z | 5170 | 60 | -0.491667 | -0.575 | -0.579167 | -0.147917 | -0.98 | 0.754167 | -0.158333 | 0.98 | -0.767624 | 0.000282334 | -0.0000314156 | 0 | DOWN_BALANCED |
| 2025-09-20 02:00:00Z | 5170 | 120 | 0.00833333 | -0.685417 | -0.729167 | -0.81875 | -0.85 | 0.0520833 | -0.58125 | 0.98 | -2.1889 | 0.000335323 | -0.000114668 | 3 | UP_EXPANSION |
| 2025-09-20 03:00:00Z | 5170 | 180 | 0.508333 | -0.585417 | -0.558333 | 0.3875 | -0.98 | -0.147917 | 0.741667 | 0.875 | 0.49648 | 0.000279333 | 0.0000196111 | 3 | UP_EXPANSION |
| 2025-09-20 03:59:00Z | 5170 | 239 | 0.98 | -0.80625 | -0.802083 | 0.11875 | -0.98 | -0.4125 | 0.8625 | 0.875 | 0.137251 | 0.000316057 | 0.0000360981 | 2 | UP_BALANCED |

## Label Semantics

`target_4class` is the primary Stage-1 target:

| Class | Name | Meaning |
|---:|---|---|
| `0` | `DOWN_BALANCED` | Downward move with balanced distance/risk profile |
| `1` | `DOWN_EXPANSION` | Downward move with expansion/breakout profile |
| `2` | `UP_BALANCED` | Upward move with balanced distance/risk profile |
| `3` | `UP_EXPANSION` | Upward move with expansion/breakout profile |
| `-1` | ignored row | Outside the valid regime entry window |

`target_breakfree` is a secondary target derived from the same target-generation pass. It is also set to `-1` outside the valid entry window.

## Related Code

- `scripts/feature_engineering/compute_htf_features.py`
- `scripts/feature_engineering/htf_multiregime_pipeline.py`
- `scripts/feature_engineering/optimize_htf_features.py`
- `scripts/feature_engineering/htf_helper_cache.py`
- `scripts/target_models/helpers/`
- `scripts/analysis/htf_stage1_regime_family_walkforward.py`

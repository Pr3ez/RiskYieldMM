# HTF Pre-Fit Null Feature Inventory — 2026-04-13

## Scope

This inventory is based on the actual CatBoost loader-visible feature set for:

- `1m / target_4class`
- roots:
  - `8h/B`, `8h/C`
  - `24h/B`, `24h/C`
  - `7d/B`, `7d/C`

Audit artifact:

- `test_output/htf_feature_null_constant_audit/20260413_full_null_feature_union_safe.json`

## Bottom Line

Current state of model-facing CatBoost inputs:

- constant columns: `0`
- all-null columns: `0`
- features with at least one null somewhere in the saved trainable rows: `170 / 170`

This does **not** mean 170 feature formulas are broken.

It means the current pipeline still exposes three different null mechanisms to fitting:

1. one real feature-design defect
2. one helper warmup / eligibility defect affecting all helper columns
3. one general start-of-history warmup leakage affecting many rolling / lagged / ratio features

## Category A — Real Feature-Specific Defect

This feature needs a direct implementation change before fitting if the goal is null-free model inputs.

- `D_dist_bot5_low_w120`

Why:

- distance metrics gate on `family_bar_pos`, so the feature resets every batch instead of using continuous causal family history
- code path:
  - `scripts/feature_engineering/htf_kernels.py`
  - `scripts/feature_engineering/htf_multiregime_pipeline.py`

## Category B — Helper Warmup / Eligibility Defect

These features are not individually broken now.  
They all inherit nulls because helper cache explicitly writes null rows before helper warmup is complete.

Affected helper features (`41`):

- `H_4cl_1_cp_any`
- `H_4cl_1_cp_count_21`
- `H_4cl_1_cp_magnitude`
- `H_4cl_1_cp_ret_down`
- `H_4cl_1_cp_ret_up`
- `H_4cl_1_cp_vol_down`
- `H_4cl_1_cp_vol_up`
- `H_4cl_1_cusum_ret_neg`
- `H_4cl_1_cusum_ret_pos`
- `H_4cl_1_cusum_vol_neg`
- `H_4cl_1_cusum_vol_pos`
- `H_4cl_1_days_since_cp`
- `H_4cl_1_garch_cond_vol`
- `H_4cl_1_garch_persistence`
- `H_4cl_1_garch_vol_change`
- `H_4cl_1_garch_vol_forecast`
- `H_4cl_1_garch_vol_ratio`
- `H_4cl_1_garch_vol_regime`
- `H_4cl_1_garch_vol_shock`
- `H_4cl_1_garch_vol_zscore`
- `H_4class_1_egarch_leverage_active`
- `H_4class_1_egarch_log_vol`
- `H_4class_1_egarch_news_impact`
- `H_4class_1_egarch_vol`
- `H_4class_1_egarch_vol_regime`
- `H_4class_1_egarch_vol_zscore`
- `H_4class_1_kalman_acceleration`
- `H_4class_1_kalman_filtered_dev`
- `H_4class_1_kalman_innovation`
- `H_4class_1_kalman_pred_error`
- `H_4class_1_kalman_regime`
- `H_4class_1_kalman_velocity`
- `H_4class_1_kalman_zscore`
- `H_4class_1_ou_halflife`
- `H_4class_1_ou_halflife_regime`
- `H_4class_1_ou_is_stationary`
- `H_4class_1_ou_kappa`
- `H_4class_1_ou_phi`
- `H_4class_1_ou_reverting`
- `H_4class_1_ou_zscore`
- `H_4class_1_ou_zscore_abs`

Required fix:

- do not expose helper-warmup batches to fitting
- or make fitting start at the first helper-clean batch per root:
  - `8h`: batch `43`
  - `24h`: batch `15`
  - `7d`: batch `4`

## Category C — General Start-of-History Warmup Leakage

These features are mostly causal rolling / lagged / shifted features.  
They are not feature-formula defects by themselves, but they still require handling before fitting because the current dataset includes rows where their warmup is incomplete.

Affected non-helper features (`128`):

- `B_C_candleDirection_bin`
- `B_consecutiveDown_bnd`
- `B_consecutiveUp_bnd`
- `C_N_bodySize_bnd`
- `C_N_lowerShadow_bnd`
- `C_N_upperShadow_bnd`
- `D_F_N_S_premiumZscore_long_zsc`
- `D_F_N_S_premiumZscore_xlong_zsc`
- `D_F_T_premiumMa_long_pct`
- `D_F_T_premiumMa_med_pct`
- `D_F_T_premiumMa_short_pct`
- `D_F_basis_pct`
- `D_N_markCloseDeviation_pct`
- `F_I_T_fundingMa_long_pct`
- `F_I_T_fundingMa_med_pct`
- `F_I_T_fundingMa_short_pct`
- `F_I_fundingCumulative_long_pct`
- `F_I_fundingCumulative_med_pct`
- `F_I_fundingCumulative_short_pct`
- `L_M_N_S_oiPctChange_pct`
- `L_M_N_S_oiRoc_long_pct`
- `L_M_N_S_oiRoc_med_pct`
- `L_M_N_S_oiRoc_short_pct`
- `L_M_N_volumeRoc_long_pct`
- `L_M_N_volumeRoc_med_pct`
- `L_M_N_volumeRoc_short_pct`
- `L_M_S_cmf_long_bnd`
- `L_M_S_cmf_xlong_bnd`
- `L_M_S_mfi_long_bnd`
- `L_M_S_mfi_xlong_bnd`
- `L_M_S_obv_long_zsc`
- `L_M_S_obv_xlong_zsc`
- `L_N_volOiRatio_rat`
- `L_N_volumeRatio_long_rat`
- `L_N_volumeRatio_med_rat`
- `L_N_volumeRatio_short_rat`
- `M_N_T_stochasticD_long_bnd`
- `M_N_T_stochasticD_med_bnd`
- `M_N_T_stochasticD_short_bnd`
- `M_N_rsi_long_bnd`
- `M_N_rsi_med_bnd`
- `M_N_rsi_short_bnd`
- `M_N_stochasticK_long_bnd`
- `M_N_stochasticK_med_bnd`
- `M_N_stochasticK_short_bnd`
- `M_P_V_momAtr_long_rat`
- `M_P_V_momAtr_med_rat`
- `M_P_V_momAtr_short_rat`
- `M_P_logReturn_pct`
- `M_P_roc_long_pct`
- `M_P_roc_med_pct`
- `M_P_roc_short_pct`
- `M_T_V_adx_med_bnd`
- `M_T_V_adx_short_bnd`
- `M_T_V_diDiff_med_bnd`
- `M_T_V_diDiff_short_bnd`
- `M_T_ppo_med_xlong_pct`
- `M_T_ppo_short_long_pct`
- `M_V_sharpe_long_rat`
- `M_V_sharpe_xlong_rat`
- `M_V_sortino_long_rat`
- `M_V_sortino_xlong_rat`
- `M_winRate_long_bnd`
- `M_winRate_med_bnd`
- `M_winRate_short_bnd`
- `N_M_cci_med_zsc`
- `N_M_cci_short_zsc`
- `N_P_T_priceEmaDeviation_long_pct`
- `N_P_T_priceEmaDeviation_med_pct`
- `N_P_T_priceEmaDeviation_short_pct`
- `N_P_T_priceSmaDeviation_long_pct`
- `N_P_T_priceSmaDeviation_med_pct`
- `N_P_T_priceSmaDeviation_short_pct`
- `N_P_V_pctB_long_bnd`
- `N_P_V_pctB_med_bnd`
- `N_P_V_pctB_short_bnd`
- `N_P_zScore_long_zsc`
- `N_P_zScore_med_zsc`
- `N_V_bollingerBW_long_pct`
- `N_V_bollingerBW_xlong_pct`
- `S_M_longShortChange_med_pct`
- `S_M_longShortChange_short_pct`
- `S_N_longShortZscore_long_zsc`
- `S_N_longShortZscore_xlong_zsc`
- `S_longShortRatio_rat`
- `V_atrPct_long_pct`
- `V_atrPct_med_pct`
- `V_atrPct_short_pct`
- `V_autocorr_long_bnd`
- `V_autocorr_med_bnd`
- `V_garmanKlass_long_pct`
- `V_garmanKlass_med_pct`
- `V_garmanKlass_short_pct`
- `V_kurtosis_long_rat`
- `V_kurtosis_med_rat`
- `V_kurtosis_xlong_rat`
- `V_maxDrawdown_long_pct`
- `V_maxDrawdown_xlong_pct`
- `V_parkinson_long_pct`
- `V_parkinson_med_pct`
- `V_parkinson_short_pct`
- `V_returnStd_long_pct`
- `V_returnStd_med_pct`
- `V_returnStd_short_pct`
- `V_skew_long_rat`
- `V_skew_med_rat`
- `V_skew_xlong_rat`
- `V_volMomentum_long_pct`
- `V_volMomentum_med_pct`
- `V_yangZhang_long_pct`
- `V_yangZhang_med_pct`
- `V_yangZhang_short_pct`
- `X_D_basisRetPressure_long_pct`
- `X_D_basisRetPressure_med_pct`
- `X_D_basisRetPressure_short_pct`
- `X_D_fundingBasisPressure_long_pct`
- `X_D_fundingBasisPressure_xlong_pct`
- `X_D_longShortRetPressure_long_pct`
- `X_D_longShortRetPressure_xlong_pct`
- `X_D_oiRetPressure_long_pct`
- `X_D_oiRetPressure_med_pct`
- `X_D_oiRetPressure_short_pct`
- `bar_in_batch_norm`
- `close`
- `high`
- `low`
- `open`
- `volume`

## What Needs Fix Before Fitting

If the acceptance bar is strict zero-null model-facing features, then fitting should wait for:

1. direct fix of `D_dist_bot5_low_w120`
2. helper-eligibility fix so helper warmup rows are not trainable
3. global feature-stage eligibility fix so early warmup rows from rolling / lagged features are not trainable

So the required work is **not** 170 independent feature rewrites.

It is:

- `1` feature-specific repair
- `1` helper-warmup gating repair
- `1` global start-of-history gating repair

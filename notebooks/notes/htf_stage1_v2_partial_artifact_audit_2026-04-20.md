# HTF Stage-1-v2 Partial Artifact Audit — 8h/B

Generated: 2026-04-20T13:01:08.943937+00:00

## Scope

- Source run: `data/htf_backtest_results/stage1_catboost_8h_b_v2_live`
- Included only completed steps with `batch_metadata.json` plus required v2 artifacts.
- Completed steps analyzed: **186**
- Pred-batch coverage: `5170` .. `5355`
- Combo-step rows: **1488**
- Unique combos: **8**
- Unique features observed in selector diagnostics: **170**

## Headline Findings

- Feature selection was applied on **100.00%** of combo-steps.
- Combo-step improvement rate (`improved_step=true`): **32.93%**.
- Mean accuracy change from baseline to selected mask: **+0.0284**.
- Mean cross-direction-error improvement: **+0.0229**. Positive means lower error after selection.
- Winner changed on **23.66%** of completed steps.
- Comparing selected winner vs baseline winner, mean winner accuracy gain was **+0.0347** and mean cross-direction-error improvement was **+0.0201**.
- Correlation between accuracy gain and cross-direction-error improvement across combo-steps: **+0.6729**.

## Combo-Level Summary

| action_key | combo_steps | baseline_accuracy_mean | filtered_accuracy_mean | delta_accuracy_mean | delta_cross_direction_error_improve_mean | improved_step_rate | n_features_used_mean | baseline_winner_steps | selected_winner_steps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| f7_v1_t4 | 186 | 0.264606 | 0.307975 | 0.043369 | 0.032930 | 0.456989 | 89.876344 | 14 | 15 |
| f2_v1_t3 | 186 | 0.284767 | 0.319131 | 0.034364 | 0.025269 | 0.365591 | 97.682796 | 27 | 28 |
| f2_v2_t4 | 186 | 0.286402 | 0.315681 | 0.029279 | 0.030959 | 0.349462 | 104.247312 | 25 | 28 |
| f2_v1_t6 | 186 | 0.288015 | 0.316779 | 0.028763 | 0.015793 | 0.365591 | 99.510753 | 22 | 19 |
| f2_v2_t8 | 186 | 0.248073 | 0.276703 | 0.028629 | 0.031676 | 0.333333 | 99.016129 | 23 | 24 |
| f2_v3_t9 | 186 | 0.278047 | 0.301322 | 0.023275 | 0.020228 | 0.225806 | 106.693548 | 24 | 23 |
| f2_v2_t10 | 186 | 0.273365 | 0.294400 | 0.021035 | 0.016913 | 0.263441 | 102.725806 | 30 | 29 |
| f2_v1_t5 | 186 | 0.280914 | 0.299798 | 0.018884 | 0.009565 | 0.274194 | 103.639785 | 21 | 20 |


## Best Features For Accuracy Lift

| feature | selected_combo_steps | selection_rate | delta_accuracy_selected_lift | delta_cross_direction_error_improve_selected_lift | importance_mean_selected | combo_majority_selected_count |
| --- | --- | --- | --- | --- | --- | --- |
| close | 1153 | 0.774866 | 0.004356 | 0.005048 | 6.898305 | 8 |
| high | 791 | 0.531586 | 0.003566 | 0.006359 | 3.766840 | 4 |
| X_D_fundingBasisPressure_long_pct | 649 | 0.436156 | 0.003173 | 0.005107 | 2.556967 | 1 |
| bar_in_batch_norm | 861 | 0.578629 | 0.002172 | -0.003577 | 3.428723 | 6 |
| X_D_longShortRetPressure_xlong_pct | 744 | 0.500000 | 0.001971 | 0.005679 | 5.308768 | 5 |
| D_dist_bot5_low_w120 | 852 | 0.572581 | 0.001448 | -0.000240 | 3.509336 | 5 |
| X_D_longShortRetPressure_long_pct | 643 | 0.432124 | -0.000084 | -0.002105 | 4.161497 | 1 |
| low | 850 | 0.571237 | -0.000260 | 0.002458 | 3.464447 | 5 |
| H_4class_1_ou_zscore | 103 | 0.069220 | -0.001055 | 0.001326 | 0.033907 | 0 |
| H_4cl_1_garch_cond_vol | 209 | 0.140457 | -0.001717 | -0.002029 | 0.126535 | 0 |


## Worst Features For Accuracy Lift

| feature | selected_combo_steps | selection_rate | delta_accuracy_selected_lift | delta_cross_direction_error_improve_selected_lift | importance_mean_selected | combo_majority_selected_count |
| --- | --- | --- | --- | --- | --- | --- |
| M_N_stochasticK_long_bnd | 1411 | 0.948253 | -0.067865 | -0.053841 | 2.697611 | 8 |
| M_T_V_adx_short_bnd | 1243 | 0.835349 | -0.064235 | -0.055407 | 0.473371 | 8 |
| N_P_T_priceSmaDeviation_med_pct | 1330 | 0.893817 | -0.063911 | -0.049036 | 0.878508 | 8 |
| N_M_cci_short_zsc | 1241 | 0.834005 | -0.063339 | -0.054946 | 0.434662 | 8 |
| L_M_S_obv_long_zsc | 1271 | 0.854167 | -0.061759 | -0.044498 | 1.131826 | 8 |
| N_P_V_pctB_short_bnd | 1279 | 0.859543 | -0.060976 | -0.049925 | 0.374318 | 8 |
| M_T_V_diDiff_med_bnd | 1271 | 0.854167 | -0.060590 | -0.053153 | 0.794682 | 8 |
| L_M_S_mfi_xlong_bnd | 1273 | 0.855511 | -0.060438 | -0.047333 | 2.748591 | 8 |
| M_N_stochasticK_med_bnd | 1320 | 0.887097 | -0.060331 | -0.044929 | 0.987508 | 8 |
| M_N_stochasticK_short_bnd | 1289 | 0.866263 | -0.060263 | -0.037936 | 0.546162 | 8 |


## Best Features For Cross-Direction-Error Reduction

| feature | selected_combo_steps | selection_rate | delta_cross_direction_error_improve_selected_lift | delta_accuracy_selected_lift | importance_mean_selected | combo_majority_selected_count |
| --- | --- | --- | --- | --- | --- | --- |
| high | 791 | 0.531586 | 0.006359 | 0.003566 | 3.766840 | 4 |
| X_D_longShortRetPressure_xlong_pct | 744 | 0.500000 | 0.005679 | 0.001971 | 5.308768 | 5 |
| X_D_fundingBasisPressure_long_pct | 649 | 0.436156 | 0.005107 | 0.003173 | 2.556967 | 1 |
| close | 1153 | 0.774866 | 0.005048 | 0.004356 | 6.898305 | 8 |
| low | 850 | 0.571237 | 0.002458 | -0.000260 | 3.464447 | 5 |
| H_4class_1_ou_zscore | 103 | 0.069220 | 0.001326 | -0.001055 | 0.033907 | 0 |
| H_4class_1_egarch_vol | 213 | 0.143145 | 0.000628 | -0.004391 | 0.472532 | 0 |
| H_4cl_1_cp_count_21 | 108 | 0.072581 | -0.000208 | -0.006299 | 0.164510 | 0 |
| D_dist_bot5_low_w120 | 852 | 0.572581 | -0.000240 | 0.001448 | 3.509336 | 5 |
| H_4cl_1_garch_cond_vol | 209 | 0.140457 | -0.002029 | -0.001717 | 0.126535 | 0 |


## Worst Features For Cross-Direction-Error Reduction

| feature | selected_combo_steps | selection_rate | delta_cross_direction_error_improve_selected_lift | delta_accuracy_selected_lift | importance_mean_selected | combo_majority_selected_count |
| --- | --- | --- | --- | --- | --- | --- |
| M_T_V_adx_short_bnd | 1243 | 0.835349 | -0.055407 | -0.064235 | 0.473371 | 8 |
| N_M_cci_short_zsc | 1241 | 0.834005 | -0.054946 | -0.063339 | 0.434662 | 8 |
| M_N_stochasticK_long_bnd | 1411 | 0.948253 | -0.053841 | -0.067865 | 2.697611 | 8 |
| M_T_V_diDiff_med_bnd | 1271 | 0.854167 | -0.053153 | -0.060590 | 0.794682 | 8 |
| L_M_S_cmf_long_bnd | 1262 | 0.848118 | -0.051433 | -0.058365 | 1.351363 | 8 |
| M_V_sharpe_xlong_rat | 1203 | 0.808468 | -0.051077 | -0.059061 | 0.806983 | 8 |
| N_P_V_pctB_short_bnd | 1279 | 0.859543 | -0.049925 | -0.060976 | 0.374318 | 8 |
| M_winRate_long_bnd | 1191 | 0.800403 | -0.049314 | -0.058246 | 0.817766 | 8 |
| V_skew_med_rat | 1226 | 0.823925 | -0.049104 | -0.060146 | 0.668876 | 8 |
| N_P_T_priceSmaDeviation_med_pct | 1330 | 0.893817 | -0.049036 | -0.063911 | 0.878508 | 8 |


## Cross-Combo Feature Structure

Features selected by majority in at least 6 combos:
| feature | selected_combo_steps | selection_rate | combo_majority_selected_count | delta_accuracy_selected_lift | delta_cross_direction_error_improve_selected_lift |
| --- | --- | --- | --- | --- | --- |
| M_N_stochasticK_long_bnd | 1411 | 0.948253 | 8 | -0.067865 | -0.053841 |
| N_P_T_priceSmaDeviation_long_pct | 1360 | 0.913978 | 8 | -0.051323 | -0.043487 |
| N_P_T_priceEmaDeviation_long_pct | 1354 | 0.909946 | 8 | -0.047637 | -0.034548 |
| N_P_V_pctB_long_bnd | 1349 | 0.906586 | 8 | -0.043279 | -0.039033 |
| N_P_T_priceSmaDeviation_med_pct | 1330 | 0.893817 | 8 | -0.063911 | -0.049036 |
| M_N_stochasticK_med_bnd | 1320 | 0.887097 | 8 | -0.060331 | -0.044929 |
| V_kurtosis_xlong_rat | 1315 | 0.883737 | 8 | -0.058561 | -0.036370 |
| N_P_T_priceEmaDeviation_short_pct | 1302 | 0.875000 | 8 | -0.054813 | -0.038991 |
| N_V_bollingerBW_xlong_pct | 1299 | 0.872984 | 8 | -0.044434 | -0.028524 |
| L_M_S_cmf_xlong_bnd | 1299 | 0.872984 | 8 | -0.046934 | -0.041075 |
| N_P_T_priceEmaDeviation_med_pct | 1299 | 0.872984 | 8 | -0.057515 | -0.043070 |
| N_V_bollingerBW_long_pct | 1295 | 0.870296 | 8 | -0.048278 | -0.035089 |
| N_P_T_priceSmaDeviation_short_pct | 1292 | 0.868280 | 8 | -0.053490 | -0.040055 |
| N_P_V_pctB_med_bnd | 1290 | 0.866935 | 8 | -0.056268 | -0.041120 |
| M_N_stochasticK_short_bnd | 1289 | 0.866263 | 8 | -0.060263 | -0.037936 |


Features that are highly selected in only one combo (combo-specific candidates):
| feature | selected_combo_steps | selection_rate | combo_highly_selected_count | delta_accuracy_selected_lift | delta_cross_direction_error_improve_selected_lift |
| --- | --- | --- | --- | --- | --- |
| high | 791 | 0.531586 | 1 | 0.003566 | 0.006359 |
| bar_in_batch_norm | 861 | 0.578629 | 1 | 0.002172 | -0.003577 |
| D_dist_bot5_low_w120 | 852 | 0.572581 | 1 | 0.001448 | -0.000240 |
| low | 850 | 0.571237 | 1 | -0.000260 | 0.002458 |
| D_F_T_premiumMa_med_pct | 1126 | 0.756720 | 1 | -0.042913 | -0.028398 |
| D_F_T_premiumMa_short_pct | 1117 | 0.750672 | 1 | -0.043549 | -0.032294 |
| N_P_zScore_med_zsc | 1007 | 0.676747 | 1 | -0.044439 | -0.035796 |
| L_M_N_S_oiPctChange_pct | 1004 | 0.674731 | 1 | -0.049355 | -0.038417 |
| N_P_zScore_long_zsc | 1042 | 0.700269 | 1 | -0.049945 | -0.035460 |
| B_C_candleDirection_bin | 977 | 0.656586 | 1 | -0.050245 | -0.038442 |
| C_N_bodySize_bnd | 1033 | 0.694220 | 1 | -0.050394 | -0.037021 |
| C_N_upperShadow_bnd | 1050 | 0.705645 | 1 | -0.051098 | -0.038839 |
| B_consecutiveUp_bnd | 1038 | 0.697581 | 1 | -0.053219 | -0.040829 |
| C_N_lowerShadow_bnd | 1056 | 0.709677 | 1 | -0.054191 | -0.042960 |
| M_V_sharpe_long_rat | 1073 | 0.721102 | 1 | -0.054850 | -0.040538 |


## Winner Changes Observed

| pred_batch | baseline_winner_action_key | selected_winner_action_key | winner_accuracy_gain_vs_baseline_winner | winner_cross_direction_error_improve_vs_baseline_winner | selected_winner_n_features_used |
| --- | --- | --- | --- | --- | --- |
| 5319 | f2_v3_t9 | f2_v1_t3 | 0.725000 | 0.816667 | 110 |
| 5208 | f2_v3_t9 | f7_v1_t4 | 0.404167 | 0.458333 | 24 |
| 5322 | f2_v1_t5 | f7_v1_t4 | 0.375000 | 0.000000 | 110 |
| 5209 | f2_v1_t6 | f2_v2_t4 | 0.337500 | 0.404167 | 24 |
| 5181 | f2_v2_t4 | f2_v2_t8 | 0.320833 | 0.233333 | 119 |
| 5229 | f2_v1_t3 | f2_v2_t4 | 0.237500 | 0.245833 | 76 |
| 5222 | f2_v1_t3 | f2_v1_t5 | 0.225000 | 0.120833 | 110 |
| 5347 | f2_v2_t8 | f2_v1_t3 | 0.204167 | 0.137500 | 24 |
| 5345 | f2_v1_t3 | f2_v3_t9 | 0.183333 | 0.325000 | 119 |
| 5326 | f2_v1_t5 | f2_v2_t4 | 0.154167 | -0.112500 | 24 |
| 5261 | f2_v3_t9 | f2_v1_t3 | 0.141667 | 0.079167 | 59 |
| 5257 | f2_v1_t6 | f2_v2_t4 | 0.112500 | 0.037500 | 59 |


## Top Selected Features By Combo

### f7_v1_t4
| feature | selected_combo_steps | selection_rate_within_combo | importance_mean_selected | delta_accuracy_mean_selected | delta_cross_direction_error_improve_mean_selected |
| --- | --- | --- | --- | --- | --- |
| close | 182 | 0.978495 | 6.154567 | 0.043567 | 0.035302 |
| M_N_stochasticK_long_bnd | 178 | 0.956989 | 3.749506 | 0.039607 | 0.034808 |
| bar_in_batch_norm | 168 | 0.903226 | 2.717813 | 0.037996 | 0.031275 |
| N_P_T_priceEmaDeviation_long_pct | 163 | 0.876344 | 2.326264 | 0.042127 | 0.033896 |
| D_dist_bot5_low_w120 | 162 | 0.870968 | 2.981156 | 0.035237 | 0.027315 |
| N_P_V_pctB_long_bnd | 161 | 0.865591 | 2.712361 | 0.039208 | 0.030797 |
| F_I_fundingCumulative_short_pct | 160 | 0.860215 | 3.744701 | 0.044323 | 0.034036 |
| low | 158 | 0.849462 | 2.752466 | 0.044198 | 0.032885 |

### f2_v1_t3
| feature | selected_combo_steps | selection_rate_within_combo | importance_mean_selected | delta_accuracy_mean_selected | delta_cross_direction_error_improve_mean_selected |
| --- | --- | --- | --- | --- | --- |
| M_N_stochasticK_long_bnd | 175 | 0.940860 | 3.697760 | 0.029548 | 0.020476 |
| N_P_T_priceSmaDeviation_long_pct | 173 | 0.930108 | 2.922654 | 0.031936 | 0.025241 |
| N_P_T_priceEmaDeviation_long_pct | 171 | 0.919355 | 2.606287 | 0.029873 | 0.026486 |
| N_P_V_pctB_long_bnd | 164 | 0.881720 | 2.882583 | 0.030996 | 0.026626 |
| N_P_T_priceEmaDeviation_short_pct | 164 | 0.881720 | 1.092946 | 0.024289 | 0.019309 |
| M_N_stochasticK_med_bnd | 163 | 0.876344 | 1.322567 | 0.026738 | 0.021651 |
| N_P_V_pctB_med_bnd | 163 | 0.876344 | 1.058689 | 0.026534 | 0.020680 |
| N_P_T_priceEmaDeviation_med_pct | 161 | 0.865591 | 1.305124 | 0.027381 | 0.023706 |

### f2_v2_t4
| feature | selected_combo_steps | selection_rate_within_combo | importance_mean_selected | delta_accuracy_mean_selected | delta_cross_direction_error_improve_mean_selected |
| --- | --- | --- | --- | --- | --- |
| M_N_stochasticK_long_bnd | 177 | 0.951613 | 3.883417 | 0.029237 | 0.030956 |
| N_P_T_priceSmaDeviation_long_pct | 176 | 0.946237 | 1.847390 | 0.026113 | 0.026184 |
| N_P_T_priceEmaDeviation_long_pct | 172 | 0.924731 | 2.338494 | 0.023522 | 0.024637 |
| V_returnStd_long_pct | 171 | 0.919355 | 1.080688 | 0.027217 | 0.031969 |
| N_P_V_pctB_long_bnd | 170 | 0.913978 | 2.819445 | 0.023897 | 0.024167 |
| N_P_T_priceSmaDeviation_med_pct | 169 | 0.908602 | 1.058404 | 0.022929 | 0.025271 |
| N_V_bollingerBW_long_pct | 168 | 0.903226 | 1.239692 | 0.025025 | 0.028398 |
| V_returnStd_short_pct | 168 | 0.903226 | 0.407674 | 0.023611 | 0.025794 |

### f2_v1_t6
| feature | selected_combo_steps | selection_rate_within_combo | importance_mean_selected | delta_accuracy_mean_selected | delta_cross_direction_error_improve_mean_selected |
| --- | --- | --- | --- | --- | --- |
| M_N_stochasticK_long_bnd | 180 | 0.967742 | 2.663323 | 0.025486 | 0.014560 |
| M_N_stochasticK_med_bnd | 171 | 0.919355 | 0.847563 | 0.024366 | 0.012695 |
| V_kurtosis_xlong_rat | 171 | 0.919355 | 3.297778 | 0.023514 | 0.014888 |
| N_P_V_pctB_long_bnd | 170 | 0.913978 | 2.357796 | 0.025760 | 0.012941 |
| N_P_T_priceSmaDeviation_med_pct | 170 | 0.913978 | 0.827295 | 0.023701 | 0.014608 |
| N_P_T_priceSmaDeviation_long_pct | 169 | 0.908602 | 1.454010 | 0.024803 | 0.012623 |
| N_P_T_priceEmaDeviation_long_pct | 168 | 0.903226 | 1.529951 | 0.025298 | 0.012574 |
| N_P_T_priceSmaDeviation_short_pct | 163 | 0.876344 | 0.340772 | 0.021396 | 0.012935 |

### f2_v2_t8
| feature | selected_combo_steps | selection_rate_within_combo | importance_mean_selected | delta_accuracy_mean_selected | delta_cross_direction_error_improve_mean_selected |
| --- | --- | --- | --- | --- | --- |
| N_P_T_priceSmaDeviation_long_pct | 171 | 0.919355 | 1.403748 | 0.022539 | 0.024708 |
| M_N_stochasticK_long_bnd | 171 | 0.919355 | 1.761204 | 0.021418 | 0.020736 |
| V_kurtosis_xlong_rat | 170 | 0.913978 | 3.941495 | 0.019706 | 0.024461 |
| N_P_T_priceEmaDeviation_long_pct | 169 | 0.908602 | 1.548829 | 0.022510 | 0.024926 |
| N_V_bollingerBW_xlong_pct | 167 | 0.897849 | 2.115092 | 0.025050 | 0.026597 |
| N_P_V_pctB_long_bnd | 166 | 0.892473 | 2.327739 | 0.021486 | 0.023469 |
| N_P_V_pctB_med_bnd | 165 | 0.887097 | 0.906772 | 0.023737 | 0.024672 |
| M_P_roc_med_pct | 164 | 0.881720 | 0.036445 | 0.025991 | 0.028455 |

### f2_v3_t9
| feature | selected_combo_steps | selection_rate_within_combo | importance_mean_selected | delta_accuracy_mean_selected | delta_cross_direction_error_improve_mean_selected |
| --- | --- | --- | --- | --- | --- |
| N_V_bollingerBW_xlong_pct | 179 | 0.962366 | 1.858655 | 0.020484 | 0.016713 |
| N_V_bollingerBW_long_pct | 179 | 0.962366 | 0.410586 | 0.017668 | 0.015689 |
| M_N_stochasticK_long_bnd | 176 | 0.946237 | 1.437094 | 0.019010 | 0.014607 |
| V_garmanKlass_long_pct | 175 | 0.940860 | 1.563742 | 0.020357 | 0.017952 |
| N_P_V_pctB_long_bnd | 175 | 0.940860 | 1.799166 | 0.019024 | 0.014571 |
| N_P_T_priceEmaDeviation_med_pct | 175 | 0.940860 | 0.945904 | 0.018048 | 0.012905 |
| V_skew_xlong_rat | 174 | 0.935484 | 2.956717 | 0.018846 | 0.016068 |
| M_P_roc_short_pct | 174 | 0.935484 | 0.004186 | 0.018654 | 0.012428 |

### f2_v2_t10
| feature | selected_combo_steps | selection_rate_within_combo | importance_mean_selected | delta_accuracy_mean_selected | delta_cross_direction_error_improve_mean_selected |
| --- | --- | --- | --- | --- | --- |
| V_kurtosis_xlong_rat | 174 | 0.935484 | 4.213704 | 0.020091 | 0.016307 |
| M_N_stochasticK_long_bnd | 174 | 0.935484 | 1.359731 | 0.017002 | 0.014823 |
| N_P_T_priceSmaDeviation_long_pct | 173 | 0.930108 | 1.623621 | 0.015077 | 0.012115 |
| N_V_bollingerBW_xlong_pct | 170 | 0.913978 | 1.587998 | 0.015147 | 0.014779 |
| N_P_V_pctB_long_bnd | 169 | 0.908602 | 3.047392 | 0.019379 | 0.016248 |
| V_volMomentum_long_pct | 169 | 0.908602 | 1.181509 | 0.018984 | 0.013511 |
| L_M_S_cmf_xlong_bnd | 169 | 0.908602 | 2.289761 | 0.018343 | 0.016889 |
| S_longShortRatio_rat | 169 | 0.908602 | 4.769936 | 0.017875 | 0.010158 |

### f2_v1_t5
| feature | selected_combo_steps | selection_rate_within_combo | importance_mean_selected | delta_accuracy_mean_selected | delta_cross_direction_error_improve_mean_selected |
| --- | --- | --- | --- | --- | --- |
| M_N_stochasticK_long_bnd | 180 | 0.967742 | 2.968657 | 0.017986 | 0.010162 |
| N_P_T_priceSmaDeviation_long_pct | 175 | 0.940860 | 1.399275 | 0.017833 | 0.008238 |
| N_P_T_priceEmaDeviation_long_pct | 174 | 0.935484 | 1.729190 | 0.017672 | 0.009363 |
| N_P_V_pctB_long_bnd | 174 | 0.935484 | 2.610914 | 0.016762 | 0.006729 |
| N_P_T_priceSmaDeviation_med_pct | 173 | 0.930108 | 0.936673 | 0.016522 | 0.007779 |
| M_N_stochasticK_short_bnd | 171 | 0.919355 | 0.641034 | 0.017739 | 0.010599 |
| M_P_V_momAtr_long_rat | 169 | 0.908602 | 0.173449 | 0.017012 | 0.006361 |
| M_N_stochasticK_med_bnd | 169 | 0.908602 | 1.127124 | 0.016075 | 0.009591 |

## Caveats

- This is a **partial-run** audit. Only `8h/B` has completed batches in the current `*_v2_live` run so far; no conclusions here should be generalized yet to `8h/C`, `24h/*`, or `7d/*`.
- Feature-level effects here are **associations**, not isolated causal effects. The selector chooses masks jointly, so a feature can look good or bad partly because of the mask context around it.
- The current Stage-1-v2 implementation still treats these artifacts as diagnostic evidence; it is not yet the final canonical winner-selection contract for all downstream stages.

## Artifacts

- Summary JSON: `test_output/stage1_v2_partial_audit_20260420_8h_b/summary.json`
- Combo stats: `test_output/stage1_v2_partial_audit_20260420_8h_b/combo_stats.csv`
- Winner transitions: `test_output/stage1_v2_partial_audit_20260420_8h_b/winner_transitions.csv`
- Feature stats: `test_output/stage1_v2_partial_audit_20260420_8h_b/feature_stats.csv`
- Combo-feature selection stats: `test_output/stage1_v2_partial_audit_20260420_8h_b/combo_feature_selection.csv`

# HTF Stage-1-v2 Per-Action-Key Feature Recurrence Audit

Generated: 2026-04-20T14:54:16.105744+00:00

## Short Answer

- Yes, each `action_key` uses repeating feature patterns. The masks are stable enough to analyze.
- No, we still cannot claim a strict causal “this combo needs exactly these features” set from partial diagnostics alone.
- What we can identify now is: shared core repeaters, combo-specific repeaters, improvement-linked features, and over-kept repeaters.

## Global Repeat Structure

- Completed steps: **186**
- Mean Jaccard overlap between combo core sets (`selection_rate_all >= 0.80`): **0.550**
- Min / max Jaccard overlap: **0.119 / 0.892**

## Repeating Across All 8 Combos

| feature | mean_acc_lift | mean_cde_lift |
| --- | --- | --- |
| N_P_V_pctB_long_bnd | -0.043280 | -0.042467 |
| L_M_S_cmf_xlong_bnd | -0.046176 | -0.039892 |
| N_P_T_priceEmaDeviation_long_pct | -0.048346 | -0.036573 |
| N_P_T_priceSmaDeviation_long_pct | -0.052598 | -0.049117 |
| L_M_S_obv_xlong_zsc | -0.058622 | -0.051430 |
| M_N_stochasticK_med_bnd | -0.059176 | -0.046488 |
| L_M_S_obv_long_zsc | -0.060702 | -0.043880 |
| L_M_S_mfi_xlong_bnd | -0.061130 | -0.050055 |
| N_P_T_priceSmaDeviation_med_pct | -0.062136 | -0.045270 |
| M_N_stochasticK_long_bnd | -0.066308 | -0.041222 |

## f2_v1_t3

Stable repeaters:
| feature | selection_rate_all | selected_steps | delta_accuracy_mean_selected | delta_cde_mean_selected | delta_accuracy_selected_lift | delta_cde_selected_lift |
| --- | --- | --- | --- | --- | --- | --- |
| M_N_stochasticK_long_bnd | 0.941 | 175 | 0.029548 | 0.020476 | -0.081437 | -0.081039 |
| N_P_T_priceSmaDeviation_long_pct | 0.930 | 173 | 0.031936 | 0.025241 | -0.034730 | -0.000400 |
| N_P_T_priceEmaDeviation_long_pct | 0.919 | 171 | 0.029873 | 0.026486 | -0.055682 | 0.015097 |
| N_P_V_pctB_long_bnd | 0.882 | 164 | 0.030996 | 0.026626 | -0.028474 | 0.011475 |
| N_P_T_priceEmaDeviation_short_pct | 0.882 | 164 | 0.024289 | 0.019309 | -0.085181 | -0.050388 |
| M_N_stochasticK_med_bnd | 0.876 | 163 | 0.026738 | 0.021651 | -0.061668 | -0.029254 |
| N_P_V_pctB_med_bnd | 0.876 | 163 | 0.026534 | 0.020680 | -0.063321 | -0.037110 |
| N_P_T_priceEmaDeviation_med_pct | 0.866 | 161 | 0.027381 | 0.023706 | -0.051952 | -0.011627 |
| M_N_stochasticK_short_bnd | 0.866 | 161 | 0.023602 | 0.018271 | -0.080064 | -0.052062 |
| N_P_T_priceSmaDeviation_med_pct | 0.860 | 160 | 0.027656 | 0.021146 | -0.047985 | -0.029495 |

Improvement-linked features:
| feature | improved_selection_lift | selection_rate_improved | selection_rate_non_improved | selected_improved_steps | delta_accuracy_selected_lift | delta_cde_selected_lift |
| --- | --- | --- | --- | --- | --- | --- |
| high | 0.234 | 0.691 | 0.458 | 47 | 0.005509 | 0.010967 |
| bar_in_batch_norm | 0.177 | 0.618 | 0.441 | 42 | -0.002442 | -0.014165 |
| close | 0.174 | 0.912 | 0.737 | 62 | 0.001989 | -0.009364 |
| low | 0.168 | 0.676 | 0.508 | 46 | -0.017841 | -0.015705 |
| D_dist_bot5_low_w120 | 0.068 | 0.721 | 0.653 | 49 | -0.012626 | -0.017543 |
| X_D_longShortRetPressure_xlong_pct | 0.060 | 0.382 | 0.322 | 26 | 0.007362 | 0.005347 |
| H_4class_1_ou_phi | 0.013 | 0.191 | 0.178 | 13 | -0.012208 | -0.012326 |
| X_D_longShortRetPressure_long_pct | 0.012 | 0.309 | 0.297 | 21 | -0.013397 | -0.024550 |
| open | 0.008 | 0.279 | 0.271 | 19 | -0.019542 | -0.021757 |
| H_4cl_1_garch_cond_vol | 0.002 | 0.206 | 0.203 | 14 | 0.001599 | -0.007917 |

Over-kept repeaters:
| feature | selection_rate_all | selected_steps | delta_accuracy_selected_lift | delta_cde_selected_lift |
| --- | --- | --- | --- | --- |
| N_P_T_priceEmaDeviation_short_pct | 0.882 | 164 | -0.085181 | -0.050388 |
| M_N_stochasticK_long_bnd | 0.941 | 175 | -0.081437 | -0.081039 |
| M_N_stochasticK_short_bnd | 0.866 | 161 | -0.080064 | -0.052062 |
| M_T_V_adx_short_bnd | 0.812 | 151 | -0.079090 | -0.052460 |
| M_T_V_diDiff_short_bnd | 0.817 | 152 | -0.068921 | -0.046459 |
| N_P_T_priceSmaDeviation_short_pct | 0.823 | 153 | -0.068127 | -0.032521 |
| M_T_V_diDiff_med_bnd | 0.833 | 155 | -0.065054 | -0.043710 |
| L_M_S_cmf_xlong_bnd | 0.839 | 156 | -0.064845 | -0.034786 |
| L_M_S_obv_xlong_zsc | 0.833 | 155 | -0.064086 | -0.036129 |
| N_P_V_pctB_med_bnd | 0.876 | 163 | -0.063321 | -0.037110 |

## f2_v1_t5

Stable repeaters:
| feature | selection_rate_all | selected_steps | delta_accuracy_mean_selected | delta_cde_mean_selected | delta_accuracy_selected_lift | delta_cde_selected_lift |
| --- | --- | --- | --- | --- | --- | --- |
| M_N_stochasticK_long_bnd | 0.968 | 180 | 0.017986 | 0.010162 | -0.027847 | 0.018495 |
| N_P_T_priceSmaDeviation_long_pct | 0.941 | 175 | 0.017833 | 0.008238 | -0.017773 | -0.022444 |
| N_P_V_pctB_long_bnd | 0.935 | 174 | 0.016762 | 0.006729 | -0.032890 | -0.043966 |
| N_P_T_priceEmaDeviation_long_pct | 0.935 | 174 | 0.017672 | 0.009363 | -0.018786 | -0.003137 |
| N_P_T_priceSmaDeviation_med_pct | 0.930 | 173 | 0.016522 | 0.007779 | -0.033798 | -0.025554 |
| M_N_stochasticK_short_bnd | 0.919 | 171 | 0.017739 | 0.010599 | -0.014206 | 0.012822 |
| M_N_stochasticK_med_bnd | 0.909 | 169 | 0.016075 | 0.009591 | -0.030739 | 0.000277 |
| M_P_V_momAtr_long_rat | 0.909 | 169 | 0.017012 | 0.006361 | -0.020488 | -0.035061 |
| V_kurtosis_xlong_rat | 0.898 | 167 | 0.013473 | 0.006088 | -0.052974 | -0.034044 |
| N_P_T_priceEmaDeviation_med_pct | 0.898 | 167 | 0.014346 | 0.006387 | -0.044426 | -0.031113 |

Improvement-linked features:
| feature | improved_selection_lift | selection_rate_improved | selection_rate_non_improved | selected_improved_steps | delta_accuracy_selected_lift | delta_cde_selected_lift |
| --- | --- | --- | --- | --- | --- | --- |
| high | 0.232 | 0.706 | 0.474 | 36 | 0.011515 | -0.004016 |
| low | 0.195 | 0.647 | 0.452 | 33 | 0.002865 | 0.007815 |
| bar_in_batch_norm | 0.185 | 0.667 | 0.481 | 34 | -0.006361 | 0.000875 |
| D_dist_bot5_low_w120 | 0.185 | 0.725 | 0.541 | 37 | 0.001062 | 0.009407 |
| open | 0.155 | 0.392 | 0.237 | 20 | 0.008822 | 0.003517 |
| X_D_fundingBasisPressure_xlong_pct | 0.136 | 0.588 | 0.452 | 30 | -0.006314 | -0.000440 |
| X_D_longShortRetPressure_xlong_pct | 0.134 | 0.608 | 0.474 | 31 | -0.001485 | -0.001263 |
| H_4class_1_ou_phi | 0.082 | 0.275 | 0.193 | 14 | 0.001819 | 0.002544 |
| close | 0.078 | 0.863 | 0.785 | 44 | 0.005907 | -0.002060 |
| X_D_longShortRetPressure_long_pct | 0.031 | 0.431 | 0.400 | 22 | 0.002276 | -0.007089 |

Over-kept repeaters:
| feature | selection_rate_all | selected_steps | delta_accuracy_selected_lift | delta_cde_selected_lift |
| --- | --- | --- | --- | --- |
| V_kurtosis_xlong_rat | 0.898 | 167 | -0.052974 | -0.034044 |
| N_M_cci_short_zsc | 0.887 | 165 | -0.050732 | -0.033950 |
| N_P_T_priceEmaDeviation_short_pct | 0.892 | 166 | -0.048637 | -0.035735 |
| V_maxDrawdown_long_pct | 0.806 | 150 | -0.046046 | -0.037940 |
| N_P_T_priceEmaDeviation_med_pct | 0.898 | 167 | -0.044426 | -0.031113 |
| V_autocorr_med_bnd | 0.849 | 158 | -0.042936 | -0.027980 |
| V_skew_long_rat | 0.855 | 159 | -0.042718 | -0.042427 |
| L_M_S_obv_long_zsc | 0.876 | 163 | -0.042328 | -0.034564 |
| L_M_S_mfi_xlong_bnd | 0.871 | 162 | -0.042303 | -0.041043 |
| V_skew_med_rat | 0.866 | 161 | -0.041916 | -0.043247 |

## f2_v1_t6

Stable repeaters:
| feature | selection_rate_all | selected_steps | delta_accuracy_mean_selected | delta_cde_mean_selected | delta_accuracy_selected_lift | delta_cde_selected_lift |
| --- | --- | --- | --- | --- | --- | --- |
| M_N_stochasticK_long_bnd | 0.968 | 180 | 0.025486 | 0.014560 | -0.101597 | -0.038218 |
| V_kurtosis_xlong_rat | 0.919 | 171 | 0.023514 | 0.014888 | -0.065097 | -0.011223 |
| M_N_stochasticK_med_bnd | 0.919 | 171 | 0.024366 | 0.012695 | -0.054522 | -0.038416 |
| N_P_V_pctB_long_bnd | 0.914 | 170 | 0.025760 | 0.012941 | -0.034917 | -0.033153 |
| N_P_T_priceSmaDeviation_med_pct | 0.914 | 170 | 0.023701 | 0.014608 | -0.058851 | -0.013778 |
| N_P_T_priceSmaDeviation_long_pct | 0.909 | 169 | 0.024803 | 0.012623 | -0.043334 | -0.034681 |
| N_P_T_priceEmaDeviation_long_pct | 0.903 | 168 | 0.025298 | 0.012574 | -0.035813 | -0.033259 |
| N_P_V_pctB_short_bnd | 0.876 | 163 | 0.020552 | 0.011043 | -0.066404 | -0.038414 |
| N_P_T_priceSmaDeviation_short_pct | 0.876 | 163 | 0.021396 | 0.012935 | -0.059583 | -0.023116 |
| N_V_bollingerBW_long_pct | 0.871 | 162 | 0.022891 | 0.010725 | -0.045512 | -0.039275 |

Improvement-linked features:
| feature | improved_selection_lift | selection_rate_improved | selection_rate_non_improved | selected_improved_steps | delta_accuracy_selected_lift | delta_cde_selected_lift |
| --- | --- | --- | --- | --- | --- | --- |
| X_D_fundingBasisPressure_xlong_pct | 0.203 | 0.779 | 0.576 | 53 | 0.009332 | -0.002624 |
| X_D_longShortRetPressure_long_pct | 0.167 | 0.574 | 0.407 | 39 | -0.001312 | 0.005511 |
| D_dist_bot5_low_w120 | 0.131 | 0.750 | 0.619 | 51 | 0.004133 | 0.001109 |
| open | 0.126 | 0.397 | 0.271 | 27 | -0.003443 | 0.009140 |
| close | 0.107 | 0.912 | 0.805 | 62 | -0.009499 | -0.005631 |
| high | 0.099 | 0.574 | 0.475 | 39 | -0.014864 | 0.001606 |
| bar_in_batch_norm | 0.097 | 0.750 | 0.653 | 51 | -0.018541 | -0.023505 |
| H_4class_1_ou_halflife | 0.085 | 0.162 | 0.076 | 11 | -0.003283 | -0.005557 |
| H_4cl_1_cusum_ret_neg | 0.079 | 0.206 | 0.127 | 14 | -0.001224 | -0.000667 |
| X_D_fundingBasisPressure_long_pct | 0.076 | 0.500 | 0.424 | 34 | 0.012042 | 0.013623 |

Over-kept repeaters:
| feature | selection_rate_all | selected_steps | delta_accuracy_selected_lift | delta_cde_selected_lift |
| --- | --- | --- | --- | --- |
| M_N_stochasticK_long_bnd | 0.968 | 180 | -0.101597 | -0.038218 |
| L_M_S_obv_long_zsc | 0.866 | 161 | -0.066894 | -0.033742 |
| N_P_V_pctB_short_bnd | 0.876 | 163 | -0.066404 | -0.038414 |
| V_kurtosis_xlong_rat | 0.919 | 171 | -0.065097 | -0.011223 |
| V_yangZhang_short_pct | 0.817 | 152 | -0.059878 | -0.021614 |
| N_P_V_pctB_med_bnd | 0.828 | 154 | -0.059619 | -0.017883 |
| N_P_T_priceSmaDeviation_short_pct | 0.876 | 163 | -0.059583 | -0.023116 |
| V_kurtosis_med_rat | 0.855 | 159 | -0.058962 | -0.022324 |
| N_P_T_priceSmaDeviation_med_pct | 0.914 | 170 | -0.058851 | -0.013778 |
| M_N_stochasticK_short_bnd | 0.871 | 162 | -0.058668 | -0.006784 |

## f2_v2_t10

Stable repeaters:
| feature | selection_rate_all | selected_steps | delta_accuracy_mean_selected | delta_cde_mean_selected | delta_accuracy_selected_lift | delta_cde_selected_lift |
| --- | --- | --- | --- | --- | --- | --- |
| V_kurtosis_xlong_rat | 0.935 | 174 | 0.020091 | 0.016307 | -0.014631 | -0.009387 |
| M_N_stochasticK_long_bnd | 0.935 | 174 | 0.017002 | 0.014823 | -0.062512 | -0.032399 |
| N_P_T_priceSmaDeviation_long_pct | 0.930 | 173 | 0.015077 | 0.012115 | -0.085243 | -0.068655 |
| N_V_bollingerBW_xlong_pct | 0.914 | 170 | 0.015147 | 0.014779 | -0.068447 | -0.024804 |
| S_longShortRatio_rat | 0.909 | 169 | 0.017875 | 0.010158 | -0.034576 | -0.073911 |
| N_P_V_pctB_long_bnd | 0.909 | 169 | 0.019379 | 0.016248 | -0.018121 | -0.007282 |
| L_M_S_cmf_xlong_bnd | 0.909 | 169 | 0.018343 | 0.016889 | -0.029451 | -0.000268 |
| V_volMomentum_long_pct | 0.909 | 169 | 0.018984 | 0.013511 | -0.022437 | -0.037224 |
| V_skew_xlong_rat | 0.903 | 168 | 0.014385 | 0.007812 | -0.068717 | -0.094039 |
| F_I_fundingCumulative_short_pct | 0.898 | 167 | 0.019012 | 0.013648 | -0.019804 | -0.031966 |

Improvement-linked features:
| feature | improved_selection_lift | selection_rate_improved | selection_rate_non_improved | selected_improved_steps | delta_accuracy_selected_lift | delta_cde_selected_lift |
| --- | --- | --- | --- | --- | --- | --- |
| D_dist_bot5_low_w120 | 0.211 | 0.612 | 0.401 | 30 | 0.016329 | 0.007310 |
| bar_in_batch_norm | 0.138 | 0.612 | 0.474 | 30 | 0.007925 | -0.005345 |
| close | 0.117 | 0.796 | 0.679 | 39 | 0.006590 | 0.014047 |
| X_D_longShortRetPressure_xlong_pct | 0.085 | 0.633 | 0.547 | 31 | 0.010133 | 0.025291 |
| high | 0.078 | 0.531 | 0.453 | 26 | 0.010491 | 0.021280 |
| X_D_fundingBasisPressure_long_pct | 0.055 | 0.449 | 0.394 | 22 | 0.011618 | 0.010244 |
| low | 0.021 | 0.510 | 0.489 | 25 | 0.006233 | 0.010625 |
| X_D_longShortRetPressure_long_pct | 0.007 | 0.408 | 0.401 | 20 | 0.000500 | 0.004800 |
| open | -0.009 | 0.224 | 0.234 | 11 | 0.006292 | 0.012409 |
| X_D_fundingBasisPressure_xlong_pct | -0.030 | 0.714 | 0.745 | 35 | 0.004892 | -0.004861 |

Over-kept repeaters:
| feature | selection_rate_all | selected_steps | delta_accuracy_selected_lift | delta_cde_selected_lift |
| --- | --- | --- | --- | --- |
| V_atrPct_med_pct | 0.844 | 157 | -0.092019 | -0.062008 |
| V_yangZhang_short_pct | 0.839 | 156 | -0.089348 | -0.058825 |
| N_P_T_priceSmaDeviation_long_pct | 0.930 | 173 | -0.085243 | -0.068655 |
| M_P_roc_med_pct | 0.855 | 159 | -0.083709 | -0.064521 |
| L_M_N_volumeRoc_long_pct | 0.812 | 151 | -0.081724 | -0.046475 |
| M_P_V_momAtr_med_rat | 0.833 | 155 | -0.081532 | -0.055833 |
| N_P_T_priceSmaDeviation_med_pct | 0.898 | 167 | -0.081110 | -0.032699 |
| M_N_rsi_med_bnd | 0.828 | 154 | -0.080905 | -0.044366 |
| M_V_sharpe_xlong_rat | 0.839 | 156 | -0.078253 | -0.074225 |
| M_P_logReturn_pct | 0.844 | 157 | -0.077210 | -0.057582 |

## f2_v2_t4

Stable repeaters:
| feature | selection_rate_all | selected_steps | delta_accuracy_mean_selected | delta_cde_mean_selected | delta_accuracy_selected_lift | delta_cde_selected_lift |
| --- | --- | --- | --- | --- | --- | --- |
| M_N_stochasticK_long_bnd | 0.952 | 177 | 0.029237 | 0.030956 | -0.000855 | -0.000063 |
| N_P_T_priceSmaDeviation_long_pct | 0.946 | 176 | 0.026113 | 0.026184 | -0.058887 | -0.088816 |
| N_P_T_priceEmaDeviation_long_pct | 0.925 | 172 | 0.023522 | 0.024637 | -0.076478 | -0.083994 |
| V_returnStd_long_pct | 0.919 | 171 | 0.027217 | 0.031969 | -0.025560 | 0.012524 |
| N_P_V_pctB_long_bnd | 0.914 | 170 | 0.023897 | 0.024167 | -0.062561 | -0.078958 |
| N_P_T_priceSmaDeviation_med_pct | 0.909 | 169 | 0.022929 | 0.025271 | -0.069473 | -0.062229 |
| N_V_bollingerBW_long_pct | 0.903 | 168 | 0.025025 | 0.028398 | -0.043957 | -0.026463 |
| N_P_T_priceEmaDeviation_short_pct | 0.903 | 168 | 0.023338 | 0.024008 | -0.061384 | -0.071825 |
| V_returnStd_short_pct | 0.903 | 168 | 0.023611 | 0.025794 | -0.058565 | -0.053373 |
| M_P_roc_med_pct | 0.903 | 168 | 0.022247 | 0.025645 | -0.072660 | -0.054911 |

Improvement-linked features:
| feature | improved_selection_lift | selection_rate_improved | selection_rate_non_improved | selected_improved_steps | delta_accuracy_selected_lift | delta_cde_selected_lift |
| --- | --- | --- | --- | --- | --- | --- |
| D_dist_bot5_low_w120 | 0.204 | 0.708 | 0.504 | 46 | 0.002945 | 0.015584 |
| high | 0.171 | 0.585 | 0.413 | 38 | 0.006707 | 0.018706 |
| X_D_fundingBasisPressure_long_pct | 0.163 | 0.477 | 0.314 | 31 | 0.014606 | 0.011359 |
| low | 0.159 | 0.646 | 0.488 | 42 | -0.000696 | 0.012508 |
| bar_in_batch_norm | 0.134 | 0.646 | 0.512 | 42 | 0.007834 | -0.004247 |
| X_D_longShortRetPressure_long_pct | 0.116 | 0.446 | 0.331 | 29 | 0.007214 | 0.019807 |
| open | 0.106 | 0.354 | 0.248 | 23 | -0.007303 | 0.004530 |
| H_4cl_1_garch_vol_shock | 0.104 | 0.154 | 0.050 | 10 | -0.005821 | -0.005950 |
| H_4cl_1_cusum_ret_neg | 0.103 | 0.169 | 0.066 | 11 | -0.003544 | 0.002400 |
| H_4cl_1_garch_cond_vol | 0.102 | 0.185 | 0.083 | 12 | -0.005067 | -0.000314 |

Over-kept repeaters:
| feature | selection_rate_all | selected_steps | delta_accuracy_selected_lift | delta_cde_selected_lift |
| --- | --- | --- | --- | --- |
| V_skew_long_rat | 0.882 | 164 | -0.095459 | -0.086036 |
| M_V_sharpe_xlong_rat | 0.844 | 157 | -0.088891 | -0.097284 |
| V_maxDrawdown_long_pct | 0.866 | 161 | -0.087864 | -0.097861 |
| M_V_sortino_xlong_rat | 0.849 | 158 | -0.087459 | -0.095641 |
| V_skew_xlong_rat | 0.855 | 159 | -0.085077 | -0.052603 |
| V_volMomentum_long_pct | 0.855 | 159 | -0.079842 | -0.062713 |
| L_M_S_mfi_long_bnd | 0.887 | 165 | -0.079722 | -0.078947 |
| M_N_stochasticK_med_bnd | 0.898 | 167 | -0.078523 | -0.087887 |
| M_P_V_momAtr_long_rat | 0.903 | 168 | -0.078042 | -0.054911 |
| N_M_cci_med_zsc | 0.887 | 165 | -0.077038 | -0.085657 |

## f2_v2_t8

Stable repeaters:
| feature | selection_rate_all | selected_steps | delta_accuracy_mean_selected | delta_cde_mean_selected | delta_accuracy_selected_lift | delta_cde_selected_lift |
| --- | --- | --- | --- | --- | --- | --- |
| M_N_stochasticK_long_bnd | 0.919 | 171 | 0.021418 | 0.020736 | -0.089415 | -0.135653 |
| N_P_T_priceSmaDeviation_long_pct | 0.919 | 171 | 0.022539 | 0.024708 | -0.075517 | -0.086404 |
| V_kurtosis_xlong_rat | 0.914 | 170 | 0.019706 | 0.024461 | -0.103732 | -0.083873 |
| N_P_T_priceEmaDeviation_long_pct | 0.909 | 169 | 0.022510 | 0.024926 | -0.066951 | -0.073848 |
| N_V_bollingerBW_xlong_pct | 0.898 | 167 | 0.025050 | 0.026597 | -0.035038 | -0.049719 |
| N_P_V_pctB_long_bnd | 0.892 | 166 | 0.021486 | 0.023469 | -0.066431 | -0.076323 |
| N_P_V_pctB_med_bnd | 0.887 | 165 | 0.023737 | 0.024672 | -0.043326 | -0.062035 |
| N_P_T_priceSmaDeviation_med_pct | 0.882 | 164 | 0.021443 | 0.021824 | -0.060754 | -0.083289 |
| N_V_bollingerBW_long_pct | 0.882 | 164 | 0.025407 | 0.026778 | -0.027245 | -0.041403 |
| M_P_roc_long_pct | 0.882 | 164 | 0.023323 | 0.025711 | -0.044859 | -0.050425 |

Improvement-linked features:
| feature | improved_selection_lift | selection_rate_improved | selection_rate_non_improved | selected_improved_steps | delta_accuracy_selected_lift | delta_cde_selected_lift |
| --- | --- | --- | --- | --- | --- | --- |
| close | 0.266 | 0.839 | 0.573 | 52 | 0.002887 | 0.002194 |
| bar_in_batch_norm | 0.194 | 0.581 | 0.387 | 36 | 0.002699 | 0.006008 |
| X_D_fundingBasisPressure_xlong_pct | 0.129 | 0.645 | 0.516 | 40 | -0.011594 | -0.009235 |
| high | 0.113 | 0.565 | 0.452 | 35 | 0.002397 | 0.008266 |
| D_dist_bot5_low_w120 | 0.048 | 0.435 | 0.387 | 27 | -0.016694 | -0.019844 |
| low | 0.032 | 0.484 | 0.452 | 30 | -0.021439 | -0.030710 |
| X_D_longShortRetPressure_long_pct | 0.008 | 0.452 | 0.444 | 28 | -0.000480 | -0.009335 |
| X_D_longShortRetPressure_xlong_pct | -0.016 | 0.435 | 0.452 | 27 | -0.012809 | -0.015228 |
| open | -0.016 | 0.177 | 0.194 | 11 | -0.025147 | -0.033299 |
| X_D_fundingBasisPressure_long_pct | -0.073 | 0.355 | 0.427 | 22 | -0.000216 | 0.013670 |

Over-kept repeaters:
| feature | selection_rate_all | selected_steps | delta_accuracy_selected_lift | delta_cde_selected_lift |
| --- | --- | --- | --- | --- |
| V_kurtosis_xlong_rat | 0.914 | 170 | -0.103732 | -0.083873 |
| L_M_S_mfi_long_bnd | 0.849 | 158 | -0.100661 | -0.111965 |
| F_I_fundingCumulative_short_pct | 0.871 | 162 | -0.097293 | -0.116519 |
| M_T_V_adx_med_bnd | 0.849 | 158 | -0.089625 | -0.087615 |
| M_N_stochasticK_long_bnd | 0.919 | 171 | -0.089415 | -0.135653 |
| M_T_V_diDiff_med_bnd | 0.817 | 152 | -0.086586 | -0.103702 |
| M_T_V_adx_short_bnd | 0.812 | 151 | -0.081462 | -0.096919 |
| L_M_S_obv_long_zsc | 0.817 | 152 | -0.081187 | -0.084057 |
| V_autocorr_long_bnd | 0.866 | 161 | -0.080143 | -0.113977 |
| L_M_S_cmf_long_bnd | 0.823 | 153 | -0.079704 | -0.095494 |

## f2_v3_t9

Stable repeaters:
| feature | selection_rate_all | selected_steps | delta_accuracy_mean_selected | delta_cde_mean_selected | delta_accuracy_selected_lift | delta_cde_selected_lift |
| --- | --- | --- | --- | --- | --- | --- |
| N_V_bollingerBW_xlong_pct | 0.962 | 179 | 0.020484 | 0.016713 | -0.074159 | -0.093406 |
| N_V_bollingerBW_long_pct | 0.962 | 179 | 0.017668 | 0.015689 | -0.148999 | -0.120621 |
| M_N_stochasticK_long_bnd | 0.946 | 176 | 0.019010 | 0.014607 | -0.079323 | -0.104560 |
| N_P_V_pctB_long_bnd | 0.941 | 175 | 0.019024 | 0.014571 | -0.071885 | -0.095656 |
| V_garmanKlass_long_pct | 0.941 | 175 | 0.020357 | 0.017952 | -0.049340 | -0.038487 |
| N_P_T_priceEmaDeviation_med_pct | 0.941 | 175 | 0.018048 | 0.012905 | -0.088392 | -0.123838 |
| V_skew_xlong_rat | 0.935 | 174 | 0.018846 | 0.016068 | -0.068654 | -0.064488 |
| N_P_T_priceSmaDeviation_long_pct | 0.935 | 174 | 0.018367 | 0.014990 | -0.076078 | -0.081190 |
| M_P_V_momAtr_med_rat | 0.935 | 174 | 0.018630 | 0.012787 | -0.071995 | -0.115338 |
| M_P_roc_short_pct | 0.935 | 174 | 0.018654 | 0.012428 | -0.071624 | -0.120905 |

Improvement-linked features:
| feature | improved_selection_lift | selection_rate_improved | selection_rate_non_improved | selected_improved_steps | delta_accuracy_selected_lift | delta_cde_selected_lift |
| --- | --- | --- | --- | --- | --- | --- |
| bar_in_batch_norm | 0.305 | 0.714 | 0.410 | 30 | 0.019287 | 0.005828 |
| low | 0.175 | 0.619 | 0.444 | 26 | 0.005226 | 0.018304 |
| high | 0.163 | 0.524 | 0.361 | 22 | 0.002491 | 0.003623 |
| D_dist_bot5_low_w120 | 0.085 | 0.405 | 0.319 | 17 | 0.016910 | 0.012116 |
| X_D_fundingBasisPressure_long_pct | 0.082 | 0.381 | 0.299 | 16 | 0.017213 | 0.020434 |
| X_D_longShortRetPressure_long_pct | 0.061 | 0.429 | 0.368 | 18 | 0.007536 | 0.005724 |
| close | 0.036 | 0.619 | 0.583 | 26 | -0.004215 | 0.010009 |
| X_D_longShortRetPressure_xlong_pct | -0.014 | 0.500 | 0.514 | 21 | 0.003257 | -0.001812 |
| X_D_fundingBasisPressure_xlong_pct | -0.019 | 0.571 | 0.590 | 24 | -0.002297 | 0.005155 |
| N_V_bollingerBW_xlong_pct | -0.167 | 0.833 | 1.000 | 35 | -0.074159 | -0.093406 |

Over-kept repeaters:
| feature | selection_rate_all | selected_steps | delta_accuracy_selected_lift | delta_cde_selected_lift |
| --- | --- | --- | --- | --- |
| N_V_bollingerBW_long_pct | 0.962 | 179 | -0.148999 | -0.120621 |
| V_atrPct_med_pct | 0.925 | 172 | -0.094556 | -0.100426 |
| L_M_S_cmf_long_bnd | 0.914 | 170 | -0.094203 | -0.068189 |
| M_T_V_adx_short_bnd | 0.887 | 165 | -0.093647 | -0.073597 |
| V_parkinson_med_pct | 0.925 | 172 | -0.090372 | -0.098816 |
| L_M_S_obv_xlong_zsc | 0.903 | 168 | -0.089302 | -0.099082 |
| N_P_T_priceEmaDeviation_med_pct | 0.941 | 175 | -0.088392 | -0.123838 |
| V_volMomentum_med_pct | 0.871 | 162 | -0.087693 | -0.061291 |
| V_kurtosis_xlong_rat | 0.914 | 170 | -0.087080 | -0.056792 |
| L_M_S_mfi_xlong_bnd | 0.914 | 170 | -0.086225 | -0.056792 |

## f7_v1_t4

Stable repeaters:
| feature | selection_rate_all | selected_steps | delta_accuracy_mean_selected | delta_cde_mean_selected | delta_accuracy_selected_lift | delta_cde_selected_lift |
| --- | --- | --- | --- | --- | --- | --- |
| close | 0.978 | 182 | 0.043567 | 0.035302 | 0.009192 | 0.110302 |
| M_N_stochasticK_long_bnd | 0.957 | 178 | 0.039607 | 0.034808 | -0.087477 | 0.043662 |
| bar_in_batch_norm | 0.903 | 168 | 0.037996 | 0.031275 | -0.055522 | -0.017105 |
| N_P_T_priceEmaDeviation_long_pct | 0.876 | 163 | 0.042127 | 0.033896 | -0.010047 | 0.007809 |
| D_dist_bot5_low_w120 | 0.871 | 162 | 0.035237 | 0.027315 | -0.063027 | -0.043519 |
| N_P_V_pctB_long_bnd | 0.866 | 161 | 0.039208 | 0.030797 | -0.030959 | -0.015870 |
| F_I_fundingCumulative_short_pct | 0.860 | 160 | 0.044323 | 0.034036 | 0.006823 | 0.007915 |

Improvement-linked features:
| feature | improved_selection_lift | selection_rate_improved | selection_rate_non_improved | selected_improved_steps | delta_accuracy_selected_lift | delta_cde_selected_lift |
| --- | --- | --- | --- | --- | --- | --- |
| close | -0.047 | 0.953 | 1.000 | 81 | 0.009192 | 0.110302 |
| volume | -0.088 | 0.129 | 0.218 | 11 | -0.029238 | -0.012250 |
| M_N_stochasticK_long_bnd | -0.094 | 0.906 | 1.000 | 77 | -0.087477 | 0.043662 |
| bar_in_batch_norm | -0.103 | 0.847 | 0.950 | 72 | -0.055522 | -0.017105 |
| F_I_T_fundingMa_long_pct | -0.106 | 0.141 | 0.248 | 12 | -0.033333 | -0.014820 |
| F_I_fundingCumulative_short_pct | -0.111 | 0.800 | 0.911 | 68 | 0.006823 | 0.007915 |
| F_I_T_fundingMa_med_pct | -0.129 | 0.188 | 0.317 | 16 | -0.026045 | -0.010454 |
| F_I_fundingCumulative_med_pct | -0.138 | 0.565 | 0.703 | 48 | -0.015808 | 0.000536 |
| X_D_fundingBasisPressure_xlong_pct | -0.144 | 0.718 | 0.861 | 61 | -0.023216 | 0.000182 |
| H_4class_1_ou_halflife | -0.146 | 0.141 | 0.287 | 12 | -0.017567 | 0.007035 |

Over-kept repeaters:
| feature | selection_rate_all | selected_steps | delta_accuracy_selected_lift | delta_cde_selected_lift |
| --- | --- | --- | --- | --- |
| N_P_T_priceSmaDeviation_med_pct | 0.828 | 154 | -0.067455 | -0.066224 |
| D_dist_bot5_low_w120 | 0.871 | 162 | -0.063027 | -0.043519 |
| L_M_S_mfi_xlong_bnd | 0.812 | 151 | -0.062425 | -0.046249 |
| M_N_stochasticK_med_bnd | 0.801 | 149 | -0.059588 | -0.017232 |
| bar_in_batch_norm | 0.903 | 168 | -0.055522 | -0.017105 |
| L_M_S_obv_long_zsc | 0.812 | 151 | -0.053333 | -0.027919 |
| V_kurtosis_xlong_rat | 0.817 | 152 | -0.047404 | -0.020588 |
| V_maxDrawdown_xlong_pct | 0.812 | 151 | -0.036909 | -0.001816 |
| L_M_S_cmf_xlong_bnd | 0.812 | 151 | -0.032217 | -0.045222 |
| N_P_V_pctB_long_bnd | 0.866 | 161 | -0.030959 | -0.015870 |

## Interpretation

- Stable repeater + positive lift = strongest candidate for a combo-specific core feature.
- High repeat but negative lift = probably over-kept by the current selector, not clearly needed.
- Improvement-linked features are the best current proxy for “this combo tends to need this when it is working well”.

## Artifacts

- Summary: `test_output/stage1_v2_action_key_feature_need_20260420_8h_b/summary.json`
- Per-combo feature stats: `test_output/stage1_v2_action_key_feature_need_20260420_8h_b/per_combo_feature_stats.csv`
- Core-positive: `test_output/stage1_v2_action_key_feature_need_20260420_8h_b/core_positive_features.csv`
- Improvement-linked: `test_output/stage1_v2_action_key_feature_need_20260420_8h_b/improvement_linked_features.csv`
- Over-kept repeaters: `test_output/stage1_v2_action_key_feature_need_20260420_8h_b/overkept_repeating_features.csv`
- Core-overlap matrix: `test_output/stage1_v2_action_key_feature_need_20260420_8h_b/combo_core_jaccard.csv`
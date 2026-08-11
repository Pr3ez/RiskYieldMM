# Volatility-Normalized Distance Target Validation

Generated: 2026-05-28T22:37:38.126525+00:00

| Asset | Root | Status | Rows | Valid Rows | Unique Label Windows |
|---|---|---|---:|---:|---:|
| BTCUSDT | 8h/B | PASS | 2,810,755 | 1,405,427 | 5,856 |
| BTCUSDT | 8h/C | PASS | 2,810,400 | 1,405,187 | 5,855 |
| BTCUSDT | 24h/B | PASS | 2,810,755 | 1,405,427 | 1,952 |
| BTCUSDT | 24h/C | PASS | 2,809,440 | 1,404,707 | 1,951 |
| BTCUSDT | 7d/B | PASS | 2,802,240 | 1,401,107 | 278 |
| BTCUSDT | 7d/C | PASS | 2,810,755 | 1,405,427 | 279 |
| ETHUSDT | 8h/B | PASS | 2,705,635 | 1,352,867 | 5,637 |
| ETHUSDT | 8h/C | PASS | 2,705,280 | 1,352,627 | 5,636 |
| ETHUSDT | 24h/B | PASS | 2,705,635 | 1,352,867 | 1,879 |
| ETHUSDT | 24h/C | PASS | 2,704,320 | 1,352,147 | 1,878 |
| ETHUSDT | 7d/B | PASS | 2,701,440 | 1,350,707 | 268 |
| ETHUSDT | 7d/C | PASS | 2,700,595 | 1,350,707 | 268 |
| EURUSD | 8h/B | PASS | 1,871,346 | 990,000 | 4,129 |
| EURUSD | 8h/C | PASS | 1,877,661 | 886,220 | 4,138 |
| EURUSD | 24h/B | PASS | 1,872,911 | 993,710 | 1,381 |
| EURUSD | 24h/C | PASS | 1,744,506 | 750,770 | 1,381 |
| EURUSD | 7d/B | PASS | 1,896,377 | 1,339,876 | 278 |
| EURUSD | 7d/C | PASS | 1,900,457 | 556,535 | 279 |
| USDJPY | 8h/B | PASS | 1,871,195 | 989,986 | 4,129 |
| USDJPY | 8h/C | PASS | 1,877,582 | 886,156 | 4,138 |
| USDJPY | 24h/B | PASS | 1,872,759 | 993,695 | 1,381 |
| USDJPY | 24h/C | PASS | 1,744,427 | 750,706 | 1,381 |
| USDJPY | 7d/B | PASS | 1,896,268 | 1,339,864 | 278 |
| USDJPY | 7d/C | PASS | 1,900,348 | 556,438 | 279 |
| GC | 8h/B | PASS | 1,862,144 | 986,488 | 4,124 |
| GC | 8h/C | PASS | 1,869,182 | 881,164 | 4,133 |
| GC | 24h/B | PASS | 1,863,798 | 990,657 | 1,378 |
| GC | 24h/C | PASS | 1,734,017 | 743,334 | 1,378 |
| GC | 7d/B | PASS | 1,887,369 | 1,335,202 | 278 |
| GC | 7d/C | PASS | 1,891,449 | 552,201 | 279 |
| CL | 8h/B | PASS | 1,863,859 | 987,077 | 4,124 |
| CL | 8h/C | PASS | 1,870,913 | 882,307 | 4,133 |
| CL | 24h/B | PASS | 1,865,512 | 991,595 | 1,378 |
| CL | 24h/C | PASS | 1,735,748 | 744,127 | 1,378 |
| CL | 7d/B | PASS | 1,889,150 | 1,336,120 | 278 |
| CL | 7d/C | PASS | 1,893,230 | 553,064 | 279 |
| ES | 8h/B | PASS | 1,863,301 | 985,172 | 4,129 |
| ES | 8h/C | PASS | 1,869,886 | 883,518 | 4,138 |
| ES | 24h/B | PASS | 1,864,681 | 993,752 | 1,381 |
| ES | 24h/C | PASS | 1,736,641 | 742,863 | 1,381 |
| ES | 7d/B | PASS | 1,888,321 | 1,333,848 | 278 |
| ES | 7d/C | PASS | 1,342,966 | 393,152 | 199 |
| NQ | 8h/B | PASS | 1,863,298 | 985,172 | 4,129 |
| NQ | 8h/C | PASS | 1,869,883 | 883,515 | 4,138 |
| NQ | 24h/B | PASS | 1,864,678 | 993,752 | 1,381 |
| NQ | 24h/C | PASS | 1,736,638 | 742,860 | 1,381 |
| NQ | 7d/B | PASS | 1,888,318 | 1,333,845 | 278 |
| NQ | 7d/C | PASS | 1,892,398 | 554,507 | 279 |

## BTCUSDT 8h/B

Label root: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/btcusdt/htf_4class_labels_reg_distance_horizon_vol_v2/1m`
Window source: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/btcusdt/htf_backtest_shift4h/15m_HTF_combined.parquet`

Invariant counters:

- `rows`: 2810755
- `unique_ts_batch`: 2810755
- `valid_rows`: 1405427
- `invalid_rows`: 1405328
- `valid_not_label_half`: 0
- `valid_reason_not_ok`: 0
- `invalid_reason_ok`: 0
- `valid_bad_vol`: 0
- `valid_bad_future_bars`: 0
- `valid_bad_offsets`: 0
- `valid_null_extreme_ts`: 0
- `extreme_less_than_mean`: 0
- `negative_targets`: 0
- `nonfinite_targets`: 0
- `invalid_nonnull_targets`: 0
- `invalid_nonnull_raw`: 0
- `bad_variant`: 0
- `bad_policy`: 0
- `target_reg_distance_up_extreme_hvol_v2_bad_norm`: 0
- `target_reg_distance_up_mean_high_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_mean_low_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_extreme_hvol_v2_bad_norm`: 0
- `horizon_minutes_mismatch`: 0
- `horizon_vol_mismatch`: 0

Window metadata counters:

- `unique_label_windows_used`: 5856
- `missing_window_stats`: 0
- `future_bars_mismatch`: 0
- `max_high_offset_mismatch`: 0
- `max_high_ts_mismatch`: 0
- `min_low_offset_mismatch`: 0
- `min_low_ts_mismatch`: 0
- `source_window_count`: 5856

Independent raw-distance recomputation:

- `target_reg_distance_up_extreme_pct_v2`: rows=1,405,427, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_up_mean_high_pct_v2`: rows=1,405,427, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_mean_low_pct_v2`: rows=1,405,427, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_extreme_pct_v2`: rows=1,405,427, max_abs_error=0.000e+00, violations_gt_1e_12=0

## BTCUSDT 8h/C

Label root: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/btcusdt/htf_4class_labels_shift4h_reg_distance_horizon_vol_v2/1m`
Window source: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/btcusdt/htf_backtest/15m_HTF_combined.parquet`

Invariant counters:

- `rows`: 2810400
- `unique_ts_batch`: 2810400
- `valid_rows`: 1405187
- `invalid_rows`: 1405213
- `valid_not_label_half`: 0
- `valid_reason_not_ok`: 0
- `invalid_reason_ok`: 0
- `valid_bad_vol`: 0
- `valid_bad_future_bars`: 0
- `valid_bad_offsets`: 0
- `valid_null_extreme_ts`: 0
- `extreme_less_than_mean`: 0
- `negative_targets`: 0
- `nonfinite_targets`: 0
- `invalid_nonnull_targets`: 0
- `invalid_nonnull_raw`: 0
- `bad_variant`: 0
- `bad_policy`: 0
- `target_reg_distance_up_extreme_hvol_v2_bad_norm`: 0
- `target_reg_distance_up_mean_high_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_mean_low_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_extreme_hvol_v2_bad_norm`: 0
- `horizon_minutes_mismatch`: 0
- `horizon_vol_mismatch`: 0

Window metadata counters:

- `unique_label_windows_used`: 5855
- `missing_window_stats`: 0
- `future_bars_mismatch`: 0
- `max_high_offset_mismatch`: 0
- `max_high_ts_mismatch`: 0
- `min_low_offset_mismatch`: 0
- `min_low_ts_mismatch`: 0
- `source_window_count`: 5856

Independent raw-distance recomputation:

- `target_reg_distance_up_extreme_pct_v2`: rows=1,405,187, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_up_mean_high_pct_v2`: rows=1,405,187, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_mean_low_pct_v2`: rows=1,405,187, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_extreme_pct_v2`: rows=1,405,187, max_abs_error=0.000e+00, violations_gt_1e_12=0

## BTCUSDT 24h/B

Label root: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/btcusdt/htf_4class_labels_24h_reg_distance_horizon_vol_v2/1m`
Window source: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/btcusdt/htf_backtest_24h_shift12h/15m_HTF_combined.parquet`

Invariant counters:

- `rows`: 2810755
- `unique_ts_batch`: 2810755
- `valid_rows`: 1405427
- `invalid_rows`: 1405328
- `valid_not_label_half`: 0
- `valid_reason_not_ok`: 0
- `invalid_reason_ok`: 0
- `valid_bad_vol`: 0
- `valid_bad_future_bars`: 0
- `valid_bad_offsets`: 0
- `valid_null_extreme_ts`: 0
- `extreme_less_than_mean`: 0
- `negative_targets`: 0
- `nonfinite_targets`: 0
- `invalid_nonnull_targets`: 0
- `invalid_nonnull_raw`: 0
- `bad_variant`: 0
- `bad_policy`: 0
- `target_reg_distance_up_extreme_hvol_v2_bad_norm`: 0
- `target_reg_distance_up_mean_high_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_mean_low_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_extreme_hvol_v2_bad_norm`: 0
- `horizon_minutes_mismatch`: 0
- `horizon_vol_mismatch`: 0

Window metadata counters:

- `unique_label_windows_used`: 1952
- `missing_window_stats`: 0
- `future_bars_mismatch`: 0
- `max_high_offset_mismatch`: 0
- `max_high_ts_mismatch`: 0
- `min_low_offset_mismatch`: 0
- `min_low_ts_mismatch`: 0
- `source_window_count`: 1952

Independent raw-distance recomputation:

- `target_reg_distance_up_extreme_pct_v2`: rows=1,405,427, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_up_mean_high_pct_v2`: rows=1,405,427, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_mean_low_pct_v2`: rows=1,405,427, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_extreme_pct_v2`: rows=1,405,427, max_abs_error=0.000e+00, violations_gt_1e_12=0

## BTCUSDT 24h/C

Label root: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/btcusdt/htf_4class_labels_24h_shift12h_reg_distance_horizon_vol_v2/1m`
Window source: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/btcusdt/htf_backtest_24h/15m_HTF_combined.parquet`

Invariant counters:

- `rows`: 2809440
- `unique_ts_batch`: 2809440
- `valid_rows`: 1404707
- `invalid_rows`: 1404733
- `valid_not_label_half`: 0
- `valid_reason_not_ok`: 0
- `invalid_reason_ok`: 0
- `valid_bad_vol`: 0
- `valid_bad_future_bars`: 0
- `valid_bad_offsets`: 0
- `valid_null_extreme_ts`: 0
- `extreme_less_than_mean`: 0
- `negative_targets`: 0
- `nonfinite_targets`: 0
- `invalid_nonnull_targets`: 0
- `invalid_nonnull_raw`: 0
- `bad_variant`: 0
- `bad_policy`: 0
- `target_reg_distance_up_extreme_hvol_v2_bad_norm`: 0
- `target_reg_distance_up_mean_high_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_mean_low_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_extreme_hvol_v2_bad_norm`: 0
- `horizon_minutes_mismatch`: 0
- `horizon_vol_mismatch`: 0

Window metadata counters:

- `unique_label_windows_used`: 1951
- `missing_window_stats`: 0
- `future_bars_mismatch`: 0
- `max_high_offset_mismatch`: 0
- `max_high_ts_mismatch`: 0
- `min_low_offset_mismatch`: 0
- `min_low_ts_mismatch`: 0
- `source_window_count`: 1952

Independent raw-distance recomputation:

- `target_reg_distance_up_extreme_pct_v2`: rows=1,404,707, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_up_mean_high_pct_v2`: rows=1,404,707, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_mean_low_pct_v2`: rows=1,404,707, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_extreme_pct_v2`: rows=1,404,707, max_abs_error=0.000e+00, violations_gt_1e_12=0

## BTCUSDT 7d/B

Label root: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/btcusdt/htf_4class_labels_7d_reg_distance_horizon_vol_v2/1m`
Window source: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/btcusdt/htf_backtest_7d_shift84h/15m_HTF_combined.parquet`

Invariant counters:

- `rows`: 2802240
- `unique_ts_batch`: 2802240
- `valid_rows`: 1401107
- `invalid_rows`: 1401133
- `valid_not_label_half`: 0
- `valid_reason_not_ok`: 0
- `invalid_reason_ok`: 0
- `valid_bad_vol`: 0
- `valid_bad_future_bars`: 0
- `valid_bad_offsets`: 0
- `valid_null_extreme_ts`: 0
- `extreme_less_than_mean`: 0
- `negative_targets`: 0
- `nonfinite_targets`: 0
- `invalid_nonnull_targets`: 0
- `invalid_nonnull_raw`: 0
- `bad_variant`: 0
- `bad_policy`: 0
- `target_reg_distance_up_extreme_hvol_v2_bad_norm`: 0
- `target_reg_distance_up_mean_high_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_mean_low_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_extreme_hvol_v2_bad_norm`: 0
- `horizon_minutes_mismatch`: 0
- `horizon_vol_mismatch`: 0

Window metadata counters:

- `unique_label_windows_used`: 278
- `missing_window_stats`: 0
- `future_bars_mismatch`: 0
- `max_high_offset_mismatch`: 0
- `max_high_ts_mismatch`: 0
- `min_low_offset_mismatch`: 0
- `min_low_ts_mismatch`: 0
- `source_window_count`: 279

Independent raw-distance recomputation:

- `target_reg_distance_up_extreme_pct_v2`: rows=1,401,107, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_up_mean_high_pct_v2`: rows=1,401,107, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_mean_low_pct_v2`: rows=1,401,107, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_extreme_pct_v2`: rows=1,401,107, max_abs_error=0.000e+00, violations_gt_1e_12=0

## BTCUSDT 7d/C

Label root: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/btcusdt/htf_4class_labels_7d_shift84h_reg_distance_horizon_vol_v2/1m`
Window source: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/btcusdt/htf_backtest_7d/15m_HTF_combined.parquet`

Invariant counters:

- `rows`: 2810755
- `unique_ts_batch`: 2810755
- `valid_rows`: 1405427
- `invalid_rows`: 1405328
- `valid_not_label_half`: 0
- `valid_reason_not_ok`: 0
- `invalid_reason_ok`: 0
- `valid_bad_vol`: 0
- `valid_bad_future_bars`: 0
- `valid_bad_offsets`: 0
- `valid_null_extreme_ts`: 0
- `extreme_less_than_mean`: 0
- `negative_targets`: 0
- `nonfinite_targets`: 0
- `invalid_nonnull_targets`: 0
- `invalid_nonnull_raw`: 0
- `bad_variant`: 0
- `bad_policy`: 0
- `target_reg_distance_up_extreme_hvol_v2_bad_norm`: 0
- `target_reg_distance_up_mean_high_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_mean_low_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_extreme_hvol_v2_bad_norm`: 0
- `horizon_minutes_mismatch`: 0
- `horizon_vol_mismatch`: 0

Window metadata counters:

- `unique_label_windows_used`: 279
- `missing_window_stats`: 0
- `future_bars_mismatch`: 0
- `max_high_offset_mismatch`: 0
- `max_high_ts_mismatch`: 0
- `min_low_offset_mismatch`: 0
- `min_low_ts_mismatch`: 0
- `source_window_count`: 279

Independent raw-distance recomputation:

- `target_reg_distance_up_extreme_pct_v2`: rows=1,405,427, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_up_mean_high_pct_v2`: rows=1,405,427, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_mean_low_pct_v2`: rows=1,405,427, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_extreme_pct_v2`: rows=1,405,427, max_abs_error=0.000e+00, violations_gt_1e_12=0

## ETHUSDT 8h/B

Label root: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/ethusdt/htf_4class_labels_reg_distance_horizon_vol_v2/1m`
Window source: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/ethusdt/htf_backtest_shift4h/15m_HTF_combined.parquet`

Invariant counters:

- `rows`: 2705635
- `unique_ts_batch`: 2705635
- `valid_rows`: 1352867
- `invalid_rows`: 1352768
- `valid_not_label_half`: 0
- `valid_reason_not_ok`: 0
- `invalid_reason_ok`: 0
- `valid_bad_vol`: 0
- `valid_bad_future_bars`: 0
- `valid_bad_offsets`: 0
- `valid_null_extreme_ts`: 0
- `extreme_less_than_mean`: 0
- `negative_targets`: 0
- `nonfinite_targets`: 0
- `invalid_nonnull_targets`: 0
- `invalid_nonnull_raw`: 0
- `bad_variant`: 0
- `bad_policy`: 0
- `target_reg_distance_up_extreme_hvol_v2_bad_norm`: 0
- `target_reg_distance_up_mean_high_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_mean_low_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_extreme_hvol_v2_bad_norm`: 0
- `horizon_minutes_mismatch`: 0
- `horizon_vol_mismatch`: 0

Window metadata counters:

- `unique_label_windows_used`: 5637
- `missing_window_stats`: 0
- `future_bars_mismatch`: 0
- `max_high_offset_mismatch`: 0
- `max_high_ts_mismatch`: 0
- `min_low_offset_mismatch`: 0
- `min_low_ts_mismatch`: 0
- `source_window_count`: 5637

Independent raw-distance recomputation:

- `target_reg_distance_up_extreme_pct_v2`: rows=1,352,867, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_up_mean_high_pct_v2`: rows=1,352,867, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_mean_low_pct_v2`: rows=1,352,867, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_extreme_pct_v2`: rows=1,352,867, max_abs_error=0.000e+00, violations_gt_1e_12=0

## ETHUSDT 8h/C

Label root: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/ethusdt/htf_4class_labels_shift4h_reg_distance_horizon_vol_v2/1m`
Window source: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/ethusdt/htf_backtest/15m_HTF_combined.parquet`

Invariant counters:

- `rows`: 2705280
- `unique_ts_batch`: 2705280
- `valid_rows`: 1352627
- `invalid_rows`: 1352653
- `valid_not_label_half`: 0
- `valid_reason_not_ok`: 0
- `invalid_reason_ok`: 0
- `valid_bad_vol`: 0
- `valid_bad_future_bars`: 0
- `valid_bad_offsets`: 0
- `valid_null_extreme_ts`: 0
- `extreme_less_than_mean`: 0
- `negative_targets`: 0
- `nonfinite_targets`: 0
- `invalid_nonnull_targets`: 0
- `invalid_nonnull_raw`: 0
- `bad_variant`: 0
- `bad_policy`: 0
- `target_reg_distance_up_extreme_hvol_v2_bad_norm`: 0
- `target_reg_distance_up_mean_high_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_mean_low_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_extreme_hvol_v2_bad_norm`: 0
- `horizon_minutes_mismatch`: 0
- `horizon_vol_mismatch`: 0

Window metadata counters:

- `unique_label_windows_used`: 5636
- `missing_window_stats`: 0
- `future_bars_mismatch`: 0
- `max_high_offset_mismatch`: 0
- `max_high_ts_mismatch`: 0
- `min_low_offset_mismatch`: 0
- `min_low_ts_mismatch`: 0
- `source_window_count`: 5637

Independent raw-distance recomputation:

- `target_reg_distance_up_extreme_pct_v2`: rows=1,352,627, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_up_mean_high_pct_v2`: rows=1,352,627, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_mean_low_pct_v2`: rows=1,352,627, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_extreme_pct_v2`: rows=1,352,627, max_abs_error=0.000e+00, violations_gt_1e_12=0

## ETHUSDT 24h/B

Label root: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/ethusdt/htf_4class_labels_24h_reg_distance_horizon_vol_v2/1m`
Window source: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/ethusdt/htf_backtest_24h_shift12h/15m_HTF_combined.parquet`

Invariant counters:

- `rows`: 2705635
- `unique_ts_batch`: 2705635
- `valid_rows`: 1352867
- `invalid_rows`: 1352768
- `valid_not_label_half`: 0
- `valid_reason_not_ok`: 0
- `invalid_reason_ok`: 0
- `valid_bad_vol`: 0
- `valid_bad_future_bars`: 0
- `valid_bad_offsets`: 0
- `valid_null_extreme_ts`: 0
- `extreme_less_than_mean`: 0
- `negative_targets`: 0
- `nonfinite_targets`: 0
- `invalid_nonnull_targets`: 0
- `invalid_nonnull_raw`: 0
- `bad_variant`: 0
- `bad_policy`: 0
- `target_reg_distance_up_extreme_hvol_v2_bad_norm`: 0
- `target_reg_distance_up_mean_high_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_mean_low_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_extreme_hvol_v2_bad_norm`: 0
- `horizon_minutes_mismatch`: 0
- `horizon_vol_mismatch`: 0

Window metadata counters:

- `unique_label_windows_used`: 1879
- `missing_window_stats`: 0
- `future_bars_mismatch`: 0
- `max_high_offset_mismatch`: 0
- `max_high_ts_mismatch`: 0
- `min_low_offset_mismatch`: 0
- `min_low_ts_mismatch`: 0
- `source_window_count`: 1879

Independent raw-distance recomputation:

- `target_reg_distance_up_extreme_pct_v2`: rows=1,352,867, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_up_mean_high_pct_v2`: rows=1,352,867, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_mean_low_pct_v2`: rows=1,352,867, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_extreme_pct_v2`: rows=1,352,867, max_abs_error=0.000e+00, violations_gt_1e_12=0

## ETHUSDT 24h/C

Label root: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/ethusdt/htf_4class_labels_24h_shift12h_reg_distance_horizon_vol_v2/1m`
Window source: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/ethusdt/htf_backtest_24h/15m_HTF_combined.parquet`

Invariant counters:

- `rows`: 2704320
- `unique_ts_batch`: 2704320
- `valid_rows`: 1352147
- `invalid_rows`: 1352173
- `valid_not_label_half`: 0
- `valid_reason_not_ok`: 0
- `invalid_reason_ok`: 0
- `valid_bad_vol`: 0
- `valid_bad_future_bars`: 0
- `valid_bad_offsets`: 0
- `valid_null_extreme_ts`: 0
- `extreme_less_than_mean`: 0
- `negative_targets`: 0
- `nonfinite_targets`: 0
- `invalid_nonnull_targets`: 0
- `invalid_nonnull_raw`: 0
- `bad_variant`: 0
- `bad_policy`: 0
- `target_reg_distance_up_extreme_hvol_v2_bad_norm`: 0
- `target_reg_distance_up_mean_high_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_mean_low_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_extreme_hvol_v2_bad_norm`: 0
- `horizon_minutes_mismatch`: 0
- `horizon_vol_mismatch`: 0

Window metadata counters:

- `unique_label_windows_used`: 1878
- `missing_window_stats`: 0
- `future_bars_mismatch`: 0
- `max_high_offset_mismatch`: 0
- `max_high_ts_mismatch`: 0
- `min_low_offset_mismatch`: 0
- `min_low_ts_mismatch`: 0
- `source_window_count`: 1879

Independent raw-distance recomputation:

- `target_reg_distance_up_extreme_pct_v2`: rows=1,352,147, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_up_mean_high_pct_v2`: rows=1,352,147, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_mean_low_pct_v2`: rows=1,352,147, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_extreme_pct_v2`: rows=1,352,147, max_abs_error=0.000e+00, violations_gt_1e_12=0

## ETHUSDT 7d/B

Label root: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/ethusdt/htf_4class_labels_7d_reg_distance_horizon_vol_v2/1m`
Window source: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/ethusdt/htf_backtest_7d_shift84h/15m_HTF_combined.parquet`

Invariant counters:

- `rows`: 2701440
- `unique_ts_batch`: 2701440
- `valid_rows`: 1350707
- `invalid_rows`: 1350733
- `valid_not_label_half`: 0
- `valid_reason_not_ok`: 0
- `invalid_reason_ok`: 0
- `valid_bad_vol`: 0
- `valid_bad_future_bars`: 0
- `valid_bad_offsets`: 0
- `valid_null_extreme_ts`: 0
- `extreme_less_than_mean`: 0
- `negative_targets`: 0
- `nonfinite_targets`: 0
- `invalid_nonnull_targets`: 0
- `invalid_nonnull_raw`: 0
- `bad_variant`: 0
- `bad_policy`: 0
- `target_reg_distance_up_extreme_hvol_v2_bad_norm`: 0
- `target_reg_distance_up_mean_high_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_mean_low_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_extreme_hvol_v2_bad_norm`: 0
- `horizon_minutes_mismatch`: 0
- `horizon_vol_mismatch`: 0

Window metadata counters:

- `unique_label_windows_used`: 268
- `missing_window_stats`: 0
- `future_bars_mismatch`: 0
- `max_high_offset_mismatch`: 0
- `max_high_ts_mismatch`: 0
- `min_low_offset_mismatch`: 0
- `min_low_ts_mismatch`: 0
- `source_window_count`: 268

Independent raw-distance recomputation:

- `target_reg_distance_up_extreme_pct_v2`: rows=1,350,707, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_up_mean_high_pct_v2`: rows=1,350,707, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_mean_low_pct_v2`: rows=1,350,707, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_extreme_pct_v2`: rows=1,350,707, max_abs_error=0.000e+00, violations_gt_1e_12=0

## ETHUSDT 7d/C

Label root: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/ethusdt/htf_4class_labels_7d_shift84h_reg_distance_horizon_vol_v2/1m`
Window source: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/ethusdt/htf_backtest_7d/15m_HTF_combined.parquet`

Invariant counters:

- `rows`: 2700595
- `unique_ts_batch`: 2700595
- `valid_rows`: 1350707
- `invalid_rows`: 1349888
- `valid_not_label_half`: 0
- `valid_reason_not_ok`: 0
- `invalid_reason_ok`: 0
- `valid_bad_vol`: 0
- `valid_bad_future_bars`: 0
- `valid_bad_offsets`: 0
- `valid_null_extreme_ts`: 0
- `extreme_less_than_mean`: 0
- `negative_targets`: 0
- `nonfinite_targets`: 0
- `invalid_nonnull_targets`: 0
- `invalid_nonnull_raw`: 0
- `bad_variant`: 0
- `bad_policy`: 0
- `target_reg_distance_up_extreme_hvol_v2_bad_norm`: 0
- `target_reg_distance_up_mean_high_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_mean_low_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_extreme_hvol_v2_bad_norm`: 0
- `horizon_minutes_mismatch`: 0
- `horizon_vol_mismatch`: 0

Window metadata counters:

- `unique_label_windows_used`: 268
- `missing_window_stats`: 0
- `future_bars_mismatch`: 0
- `max_high_offset_mismatch`: 0
- `max_high_ts_mismatch`: 0
- `min_low_offset_mismatch`: 0
- `min_low_ts_mismatch`: 0
- `source_window_count`: 269

Independent raw-distance recomputation:

- `target_reg_distance_up_extreme_pct_v2`: rows=1,350,707, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_up_mean_high_pct_v2`: rows=1,350,707, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_mean_low_pct_v2`: rows=1,350,707, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_extreme_pct_v2`: rows=1,350,707, max_abs_error=0.000e+00, violations_gt_1e_12=0

## EURUSD 8h/B

Label root: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/eurusd/htf_4class_labels_reg_distance_horizon_vol_v2/1m`
Window source: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/eurusd/htf_backtest_shift4h/15m_HTF_combined.parquet`

Invariant counters:

- `rows`: 1871346
- `unique_ts_batch`: 1871346
- `valid_rows`: 990000
- `invalid_rows`: 881346
- `valid_not_label_half`: 0
- `valid_reason_not_ok`: 0
- `invalid_reason_ok`: 0
- `valid_bad_vol`: 0
- `valid_bad_future_bars`: 0
- `valid_bad_offsets`: 0
- `valid_null_extreme_ts`: 0
- `extreme_less_than_mean`: 0
- `negative_targets`: 0
- `nonfinite_targets`: 0
- `invalid_nonnull_targets`: 0
- `invalid_nonnull_raw`: 0
- `bad_variant`: 0
- `bad_policy`: 0
- `target_reg_distance_up_extreme_hvol_v2_bad_norm`: 0
- `target_reg_distance_up_mean_high_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_mean_low_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_extreme_hvol_v2_bad_norm`: 0
- `horizon_minutes_mismatch`: 0
- `horizon_vol_mismatch`: 0

Window metadata counters:

- `unique_label_windows_used`: 4129
- `missing_window_stats`: 0
- `future_bars_mismatch`: 0
- `max_high_offset_mismatch`: 0
- `max_high_ts_mismatch`: 0
- `min_low_offset_mismatch`: 0
- `min_low_ts_mismatch`: 0
- `source_window_count`: 4413

Independent raw-distance recomputation:

- `target_reg_distance_up_extreme_pct_v2`: rows=990,000, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_up_mean_high_pct_v2`: rows=990,000, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_mean_low_pct_v2`: rows=990,000, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_extreme_pct_v2`: rows=990,000, max_abs_error=0.000e+00, violations_gt_1e_12=0

## EURUSD 8h/C

Label root: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/eurusd/htf_4class_labels_shift4h_reg_distance_horizon_vol_v2/1m`
Window source: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/eurusd/htf_backtest/15m_HTF_combined.parquet`

Invariant counters:

- `rows`: 1877661
- `unique_ts_batch`: 1877661
- `valid_rows`: 886220
- `invalid_rows`: 991441
- `valid_not_label_half`: 0
- `valid_reason_not_ok`: 0
- `invalid_reason_ok`: 0
- `valid_bad_vol`: 0
- `valid_bad_future_bars`: 0
- `valid_bad_offsets`: 0
- `valid_null_extreme_ts`: 0
- `extreme_less_than_mean`: 0
- `negative_targets`: 0
- `nonfinite_targets`: 0
- `invalid_nonnull_targets`: 0
- `invalid_nonnull_raw`: 0
- `bad_variant`: 0
- `bad_policy`: 0
- `target_reg_distance_up_extreme_hvol_v2_bad_norm`: 0
- `target_reg_distance_up_mean_high_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_mean_low_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_extreme_hvol_v2_bad_norm`: 0
- `horizon_minutes_mismatch`: 0
- `horizon_vol_mismatch`: 0

Window metadata counters:

- `unique_label_windows_used`: 4138
- `missing_window_stats`: 0
- `future_bars_mismatch`: 0
- `max_high_offset_mismatch`: 0
- `max_high_ts_mismatch`: 0
- `min_low_offset_mismatch`: 0
- `min_low_ts_mismatch`: 0
- `source_window_count`: 4138

Independent raw-distance recomputation:

- `target_reg_distance_up_extreme_pct_v2`: rows=886,220, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_up_mean_high_pct_v2`: rows=886,220, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_mean_low_pct_v2`: rows=886,220, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_extreme_pct_v2`: rows=886,220, max_abs_error=0.000e+00, violations_gt_1e_12=0

## EURUSD 24h/B

Label root: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/eurusd/htf_4class_labels_24h_reg_distance_horizon_vol_v2/1m`
Window source: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/eurusd/htf_backtest_24h_shift12h/15m_HTF_combined.parquet`

Invariant counters:

- `rows`: 1872911
- `unique_ts_batch`: 1872911
- `valid_rows`: 993710
- `invalid_rows`: 879201
- `valid_not_label_half`: 0
- `valid_reason_not_ok`: 0
- `invalid_reason_ok`: 0
- `valid_bad_vol`: 0
- `valid_bad_future_bars`: 0
- `valid_bad_offsets`: 0
- `valid_null_extreme_ts`: 0
- `extreme_less_than_mean`: 0
- `negative_targets`: 0
- `nonfinite_targets`: 0
- `invalid_nonnull_targets`: 0
- `invalid_nonnull_raw`: 0
- `bad_variant`: 0
- `bad_policy`: 0
- `target_reg_distance_up_extreme_hvol_v2_bad_norm`: 0
- `target_reg_distance_up_mean_high_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_mean_low_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_extreme_hvol_v2_bad_norm`: 0
- `horizon_minutes_mismatch`: 0
- `horizon_vol_mismatch`: 0

Window metadata counters:

- `unique_label_windows_used`: 1381
- `missing_window_stats`: 0
- `future_bars_mismatch`: 0
- `max_high_offset_mismatch`: 0
- `max_high_ts_mismatch`: 0
- `min_low_offset_mismatch`: 0
- `min_low_ts_mismatch`: 0
- `source_window_count`: 1664

Independent raw-distance recomputation:

- `target_reg_distance_up_extreme_pct_v2`: rows=993,710, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_up_mean_high_pct_v2`: rows=993,710, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_mean_low_pct_v2`: rows=993,710, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_extreme_pct_v2`: rows=993,710, max_abs_error=0.000e+00, violations_gt_1e_12=0

## EURUSD 24h/C

Label root: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/eurusd/htf_4class_labels_24h_shift12h_reg_distance_horizon_vol_v2/1m`
Window source: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/eurusd/htf_backtest_24h/15m_HTF_combined.parquet`

Invariant counters:

- `rows`: 1744506
- `unique_ts_batch`: 1744506
- `valid_rows`: 750770
- `invalid_rows`: 993736
- `valid_not_label_half`: 0
- `valid_reason_not_ok`: 0
- `invalid_reason_ok`: 0
- `valid_bad_vol`: 0
- `valid_bad_future_bars`: 0
- `valid_bad_offsets`: 0
- `valid_null_extreme_ts`: 0
- `extreme_less_than_mean`: 0
- `negative_targets`: 0
- `nonfinite_targets`: 0
- `invalid_nonnull_targets`: 0
- `invalid_nonnull_raw`: 0
- `bad_variant`: 0
- `bad_policy`: 0
- `target_reg_distance_up_extreme_hvol_v2_bad_norm`: 0
- `target_reg_distance_up_mean_high_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_mean_low_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_extreme_hvol_v2_bad_norm`: 0
- `horizon_minutes_mismatch`: 0
- `horizon_vol_mismatch`: 0

Window metadata counters:

- `unique_label_windows_used`: 1381
- `missing_window_stats`: 0
- `future_bars_mismatch`: 0
- `max_high_offset_mismatch`: 0
- `max_high_ts_mismatch`: 0
- `min_low_offset_mismatch`: 0
- `min_low_ts_mismatch`: 0
- `source_window_count`: 1381

Independent raw-distance recomputation:

- `target_reg_distance_up_extreme_pct_v2`: rows=750,770, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_up_mean_high_pct_v2`: rows=750,770, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_mean_low_pct_v2`: rows=750,770, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_extreme_pct_v2`: rows=750,770, max_abs_error=0.000e+00, violations_gt_1e_12=0

## EURUSD 7d/B

Label root: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/eurusd/htf_4class_labels_7d_reg_distance_horizon_vol_v2/1m`
Window source: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/eurusd/htf_backtest_7d_shift84h/15m_HTF_combined.parquet`

Invariant counters:

- `rows`: 1896377
- `unique_ts_batch`: 1896377
- `valid_rows`: 1339876
- `invalid_rows`: 556501
- `valid_not_label_half`: 0
- `valid_reason_not_ok`: 0
- `invalid_reason_ok`: 0
- `valid_bad_vol`: 0
- `valid_bad_future_bars`: 0
- `valid_bad_offsets`: 0
- `valid_null_extreme_ts`: 0
- `extreme_less_than_mean`: 0
- `negative_targets`: 0
- `nonfinite_targets`: 0
- `invalid_nonnull_targets`: 0
- `invalid_nonnull_raw`: 0
- `bad_variant`: 0
- `bad_policy`: 0
- `target_reg_distance_up_extreme_hvol_v2_bad_norm`: 0
- `target_reg_distance_up_mean_high_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_mean_low_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_extreme_hvol_v2_bad_norm`: 0
- `horizon_minutes_mismatch`: 0
- `horizon_vol_mismatch`: 0

Window metadata counters:

- `unique_label_windows_used`: 278
- `missing_window_stats`: 0
- `future_bars_mismatch`: 0
- `max_high_offset_mismatch`: 0
- `max_high_ts_mismatch`: 0
- `min_low_offset_mismatch`: 0
- `min_low_ts_mismatch`: 0
- `source_window_count`: 279

Independent raw-distance recomputation:

- `target_reg_distance_up_extreme_pct_v2`: rows=1,339,876, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_up_mean_high_pct_v2`: rows=1,339,876, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_mean_low_pct_v2`: rows=1,339,876, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_extreme_pct_v2`: rows=1,339,876, max_abs_error=0.000e+00, violations_gt_1e_12=0

## EURUSD 7d/C

Label root: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/eurusd/htf_4class_labels_7d_shift84h_reg_distance_horizon_vol_v2/1m`
Window source: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/eurusd/htf_backtest_7d/15m_HTF_combined.parquet`

Invariant counters:

- `rows`: 1900457
- `unique_ts_batch`: 1900457
- `valid_rows`: 556535
- `invalid_rows`: 1343922
- `valid_not_label_half`: 0
- `valid_reason_not_ok`: 0
- `invalid_reason_ok`: 0
- `valid_bad_vol`: 0
- `valid_bad_future_bars`: 0
- `valid_bad_offsets`: 0
- `valid_null_extreme_ts`: 0
- `extreme_less_than_mean`: 0
- `negative_targets`: 0
- `nonfinite_targets`: 0
- `invalid_nonnull_targets`: 0
- `invalid_nonnull_raw`: 0
- `bad_variant`: 0
- `bad_policy`: 0
- `target_reg_distance_up_extreme_hvol_v2_bad_norm`: 0
- `target_reg_distance_up_mean_high_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_mean_low_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_extreme_hvol_v2_bad_norm`: 0
- `horizon_minutes_mismatch`: 0
- `horizon_vol_mismatch`: 0

Window metadata counters:

- `unique_label_windows_used`: 279
- `missing_window_stats`: 0
- `future_bars_mismatch`: 0
- `max_high_offset_mismatch`: 0
- `max_high_ts_mismatch`: 0
- `min_low_offset_mismatch`: 0
- `min_low_ts_mismatch`: 0
- `source_window_count`: 279

Independent raw-distance recomputation:

- `target_reg_distance_up_extreme_pct_v2`: rows=556,535, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_up_mean_high_pct_v2`: rows=556,535, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_mean_low_pct_v2`: rows=556,535, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_extreme_pct_v2`: rows=556,535, max_abs_error=0.000e+00, violations_gt_1e_12=0

## USDJPY 8h/B

Label root: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/usdjpy/htf_4class_labels_reg_distance_horizon_vol_v2/1m`
Window source: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/usdjpy/htf_backtest_shift4h/15m_HTF_combined.parquet`

Invariant counters:

- `rows`: 1871195
- `unique_ts_batch`: 1871195
- `valid_rows`: 989986
- `invalid_rows`: 881209
- `valid_not_label_half`: 0
- `valid_reason_not_ok`: 0
- `invalid_reason_ok`: 0
- `valid_bad_vol`: 0
- `valid_bad_future_bars`: 0
- `valid_bad_offsets`: 0
- `valid_null_extreme_ts`: 0
- `extreme_less_than_mean`: 0
- `negative_targets`: 0
- `nonfinite_targets`: 0
- `invalid_nonnull_targets`: 0
- `invalid_nonnull_raw`: 0
- `bad_variant`: 0
- `bad_policy`: 0
- `target_reg_distance_up_extreme_hvol_v2_bad_norm`: 0
- `target_reg_distance_up_mean_high_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_mean_low_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_extreme_hvol_v2_bad_norm`: 0
- `horizon_minutes_mismatch`: 0
- `horizon_vol_mismatch`: 0

Window metadata counters:

- `unique_label_windows_used`: 4129
- `missing_window_stats`: 0
- `future_bars_mismatch`: 0
- `max_high_offset_mismatch`: 0
- `max_high_ts_mismatch`: 0
- `min_low_offset_mismatch`: 0
- `min_low_ts_mismatch`: 0
- `source_window_count`: 4413

Independent raw-distance recomputation:

- `target_reg_distance_up_extreme_pct_v2`: rows=989,986, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_up_mean_high_pct_v2`: rows=989,986, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_mean_low_pct_v2`: rows=989,986, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_extreme_pct_v2`: rows=989,986, max_abs_error=0.000e+00, violations_gt_1e_12=0

## USDJPY 8h/C

Label root: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/usdjpy/htf_4class_labels_shift4h_reg_distance_horizon_vol_v2/1m`
Window source: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/usdjpy/htf_backtest/15m_HTF_combined.parquet`

Invariant counters:

- `rows`: 1877582
- `unique_ts_batch`: 1877582
- `valid_rows`: 886156
- `invalid_rows`: 991426
- `valid_not_label_half`: 0
- `valid_reason_not_ok`: 0
- `invalid_reason_ok`: 0
- `valid_bad_vol`: 0
- `valid_bad_future_bars`: 0
- `valid_bad_offsets`: 0
- `valid_null_extreme_ts`: 0
- `extreme_less_than_mean`: 0
- `negative_targets`: 0
- `nonfinite_targets`: 0
- `invalid_nonnull_targets`: 0
- `invalid_nonnull_raw`: 0
- `bad_variant`: 0
- `bad_policy`: 0
- `target_reg_distance_up_extreme_hvol_v2_bad_norm`: 0
- `target_reg_distance_up_mean_high_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_mean_low_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_extreme_hvol_v2_bad_norm`: 0
- `horizon_minutes_mismatch`: 0
- `horizon_vol_mismatch`: 0

Window metadata counters:

- `unique_label_windows_used`: 4138
- `missing_window_stats`: 0
- `future_bars_mismatch`: 0
- `max_high_offset_mismatch`: 0
- `max_high_ts_mismatch`: 0
- `min_low_offset_mismatch`: 0
- `min_low_ts_mismatch`: 0
- `source_window_count`: 4138

Independent raw-distance recomputation:

- `target_reg_distance_up_extreme_pct_v2`: rows=886,156, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_up_mean_high_pct_v2`: rows=886,156, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_mean_low_pct_v2`: rows=886,156, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_extreme_pct_v2`: rows=886,156, max_abs_error=0.000e+00, violations_gt_1e_12=0

## USDJPY 24h/B

Label root: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/usdjpy/htf_4class_labels_24h_reg_distance_horizon_vol_v2/1m`
Window source: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/usdjpy/htf_backtest_24h_shift12h/15m_HTF_combined.parquet`

Invariant counters:

- `rows`: 1872759
- `unique_ts_batch`: 1872759
- `valid_rows`: 993695
- `invalid_rows`: 879064
- `valid_not_label_half`: 0
- `valid_reason_not_ok`: 0
- `invalid_reason_ok`: 0
- `valid_bad_vol`: 0
- `valid_bad_future_bars`: 0
- `valid_bad_offsets`: 0
- `valid_null_extreme_ts`: 0
- `extreme_less_than_mean`: 0
- `negative_targets`: 0
- `nonfinite_targets`: 0
- `invalid_nonnull_targets`: 0
- `invalid_nonnull_raw`: 0
- `bad_variant`: 0
- `bad_policy`: 0
- `target_reg_distance_up_extreme_hvol_v2_bad_norm`: 0
- `target_reg_distance_up_mean_high_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_mean_low_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_extreme_hvol_v2_bad_norm`: 0
- `horizon_minutes_mismatch`: 0
- `horizon_vol_mismatch`: 0

Window metadata counters:

- `unique_label_windows_used`: 1381
- `missing_window_stats`: 0
- `future_bars_mismatch`: 0
- `max_high_offset_mismatch`: 0
- `max_high_ts_mismatch`: 0
- `min_low_offset_mismatch`: 0
- `min_low_ts_mismatch`: 0
- `source_window_count`: 1664

Independent raw-distance recomputation:

- `target_reg_distance_up_extreme_pct_v2`: rows=993,695, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_up_mean_high_pct_v2`: rows=993,695, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_mean_low_pct_v2`: rows=993,695, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_extreme_pct_v2`: rows=993,695, max_abs_error=0.000e+00, violations_gt_1e_12=0

## USDJPY 24h/C

Label root: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/usdjpy/htf_4class_labels_24h_shift12h_reg_distance_horizon_vol_v2/1m`
Window source: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/usdjpy/htf_backtest_24h/15m_HTF_combined.parquet`

Invariant counters:

- `rows`: 1744427
- `unique_ts_batch`: 1744427
- `valid_rows`: 750706
- `invalid_rows`: 993721
- `valid_not_label_half`: 0
- `valid_reason_not_ok`: 0
- `invalid_reason_ok`: 0
- `valid_bad_vol`: 0
- `valid_bad_future_bars`: 0
- `valid_bad_offsets`: 0
- `valid_null_extreme_ts`: 0
- `extreme_less_than_mean`: 0
- `negative_targets`: 0
- `nonfinite_targets`: 0
- `invalid_nonnull_targets`: 0
- `invalid_nonnull_raw`: 0
- `bad_variant`: 0
- `bad_policy`: 0
- `target_reg_distance_up_extreme_hvol_v2_bad_norm`: 0
- `target_reg_distance_up_mean_high_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_mean_low_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_extreme_hvol_v2_bad_norm`: 0
- `horizon_minutes_mismatch`: 0
- `horizon_vol_mismatch`: 0

Window metadata counters:

- `unique_label_windows_used`: 1381
- `missing_window_stats`: 0
- `future_bars_mismatch`: 0
- `max_high_offset_mismatch`: 0
- `max_high_ts_mismatch`: 0
- `min_low_offset_mismatch`: 0
- `min_low_ts_mismatch`: 0
- `source_window_count`: 1381

Independent raw-distance recomputation:

- `target_reg_distance_up_extreme_pct_v2`: rows=750,706, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_up_mean_high_pct_v2`: rows=750,706, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_mean_low_pct_v2`: rows=750,706, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_extreme_pct_v2`: rows=750,706, max_abs_error=0.000e+00, violations_gt_1e_12=0

## USDJPY 7d/B

Label root: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/usdjpy/htf_4class_labels_7d_reg_distance_horizon_vol_v2/1m`
Window source: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/usdjpy/htf_backtest_7d_shift84h/15m_HTF_combined.parquet`

Invariant counters:

- `rows`: 1896268
- `unique_ts_batch`: 1896268
- `valid_rows`: 1339864
- `invalid_rows`: 556404
- `valid_not_label_half`: 0
- `valid_reason_not_ok`: 0
- `invalid_reason_ok`: 0
- `valid_bad_vol`: 0
- `valid_bad_future_bars`: 0
- `valid_bad_offsets`: 0
- `valid_null_extreme_ts`: 0
- `extreme_less_than_mean`: 0
- `negative_targets`: 0
- `nonfinite_targets`: 0
- `invalid_nonnull_targets`: 0
- `invalid_nonnull_raw`: 0
- `bad_variant`: 0
- `bad_policy`: 0
- `target_reg_distance_up_extreme_hvol_v2_bad_norm`: 0
- `target_reg_distance_up_mean_high_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_mean_low_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_extreme_hvol_v2_bad_norm`: 0
- `horizon_minutes_mismatch`: 0
- `horizon_vol_mismatch`: 0

Window metadata counters:

- `unique_label_windows_used`: 278
- `missing_window_stats`: 0
- `future_bars_mismatch`: 0
- `max_high_offset_mismatch`: 0
- `max_high_ts_mismatch`: 0
- `min_low_offset_mismatch`: 0
- `min_low_ts_mismatch`: 0
- `source_window_count`: 279

Independent raw-distance recomputation:

- `target_reg_distance_up_extreme_pct_v2`: rows=1,339,864, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_up_mean_high_pct_v2`: rows=1,339,864, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_mean_low_pct_v2`: rows=1,339,864, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_extreme_pct_v2`: rows=1,339,864, max_abs_error=0.000e+00, violations_gt_1e_12=0

## USDJPY 7d/C

Label root: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/usdjpy/htf_4class_labels_7d_shift84h_reg_distance_horizon_vol_v2/1m`
Window source: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/usdjpy/htf_backtest_7d/15m_HTF_combined.parquet`

Invariant counters:

- `rows`: 1900348
- `unique_ts_batch`: 1900348
- `valid_rows`: 556438
- `invalid_rows`: 1343910
- `valid_not_label_half`: 0
- `valid_reason_not_ok`: 0
- `invalid_reason_ok`: 0
- `valid_bad_vol`: 0
- `valid_bad_future_bars`: 0
- `valid_bad_offsets`: 0
- `valid_null_extreme_ts`: 0
- `extreme_less_than_mean`: 0
- `negative_targets`: 0
- `nonfinite_targets`: 0
- `invalid_nonnull_targets`: 0
- `invalid_nonnull_raw`: 0
- `bad_variant`: 0
- `bad_policy`: 0
- `target_reg_distance_up_extreme_hvol_v2_bad_norm`: 0
- `target_reg_distance_up_mean_high_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_mean_low_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_extreme_hvol_v2_bad_norm`: 0
- `horizon_minutes_mismatch`: 0
- `horizon_vol_mismatch`: 0

Window metadata counters:

- `unique_label_windows_used`: 279
- `missing_window_stats`: 0
- `future_bars_mismatch`: 0
- `max_high_offset_mismatch`: 0
- `max_high_ts_mismatch`: 0
- `min_low_offset_mismatch`: 0
- `min_low_ts_mismatch`: 0
- `source_window_count`: 279

Independent raw-distance recomputation:

- `target_reg_distance_up_extreme_pct_v2`: rows=556,438, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_up_mean_high_pct_v2`: rows=556,438, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_mean_low_pct_v2`: rows=556,438, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_extreme_pct_v2`: rows=556,438, max_abs_error=0.000e+00, violations_gt_1e_12=0

## GC 8h/B

Label root: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/gc/htf_4class_labels_reg_distance_horizon_vol_v2/1m`
Window source: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/gc/htf_backtest_shift4h/15m_HTF_combined.parquet`

Invariant counters:

- `rows`: 1862144
- `unique_ts_batch`: 1862144
- `valid_rows`: 986488
- `invalid_rows`: 875656
- `valid_not_label_half`: 0
- `valid_reason_not_ok`: 0
- `invalid_reason_ok`: 0
- `valid_bad_vol`: 0
- `valid_bad_future_bars`: 0
- `valid_bad_offsets`: 0
- `valid_null_extreme_ts`: 0
- `extreme_less_than_mean`: 0
- `negative_targets`: 0
- `nonfinite_targets`: 0
- `invalid_nonnull_targets`: 0
- `invalid_nonnull_raw`: 0
- `bad_variant`: 0
- `bad_policy`: 0
- `target_reg_distance_up_extreme_hvol_v2_bad_norm`: 0
- `target_reg_distance_up_mean_high_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_mean_low_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_extreme_hvol_v2_bad_norm`: 0
- `horizon_minutes_mismatch`: 0
- `horizon_vol_mismatch`: 0

Window metadata counters:

- `unique_label_windows_used`: 4124
- `missing_window_stats`: 0
- `future_bars_mismatch`: 0
- `max_high_offset_mismatch`: 0
- `max_high_ts_mismatch`: 0
- `min_low_offset_mismatch`: 0
- `min_low_ts_mismatch`: 0
- `source_window_count`: 4408

Independent raw-distance recomputation:

- `target_reg_distance_up_extreme_pct_v2`: rows=986,488, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_up_mean_high_pct_v2`: rows=986,488, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_mean_low_pct_v2`: rows=986,488, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_extreme_pct_v2`: rows=986,488, max_abs_error=0.000e+00, violations_gt_1e_12=0

## GC 8h/C

Label root: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/gc/htf_4class_labels_shift4h_reg_distance_horizon_vol_v2/1m`
Window source: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/gc/htf_backtest/15m_HTF_combined.parquet`

Invariant counters:

- `rows`: 1869182
- `unique_ts_batch`: 1869182
- `valid_rows`: 881164
- `invalid_rows`: 988018
- `valid_not_label_half`: 0
- `valid_reason_not_ok`: 0
- `invalid_reason_ok`: 0
- `valid_bad_vol`: 0
- `valid_bad_future_bars`: 0
- `valid_bad_offsets`: 0
- `valid_null_extreme_ts`: 0
- `extreme_less_than_mean`: 0
- `negative_targets`: 0
- `nonfinite_targets`: 0
- `invalid_nonnull_targets`: 0
- `invalid_nonnull_raw`: 0
- `bad_variant`: 0
- `bad_policy`: 0
- `target_reg_distance_up_extreme_hvol_v2_bad_norm`: 0
- `target_reg_distance_up_mean_high_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_mean_low_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_extreme_hvol_v2_bad_norm`: 0
- `horizon_minutes_mismatch`: 0
- `horizon_vol_mismatch`: 0

Window metadata counters:

- `unique_label_windows_used`: 4133
- `missing_window_stats`: 0
- `future_bars_mismatch`: 0
- `max_high_offset_mismatch`: 0
- `max_high_ts_mismatch`: 0
- `min_low_offset_mismatch`: 0
- `min_low_ts_mismatch`: 0
- `source_window_count`: 4133

Independent raw-distance recomputation:

- `target_reg_distance_up_extreme_pct_v2`: rows=881,164, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_up_mean_high_pct_v2`: rows=881,164, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_mean_low_pct_v2`: rows=881,164, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_extreme_pct_v2`: rows=881,164, max_abs_error=0.000e+00, violations_gt_1e_12=0

## GC 24h/B

Label root: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/gc/htf_4class_labels_24h_reg_distance_horizon_vol_v2/1m`
Window source: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/gc/htf_backtest_24h_shift12h/15m_HTF_combined.parquet`

Invariant counters:

- `rows`: 1863798
- `unique_ts_batch`: 1863798
- `valid_rows`: 990657
- `invalid_rows`: 873141
- `valid_not_label_half`: 0
- `valid_reason_not_ok`: 0
- `invalid_reason_ok`: 0
- `valid_bad_vol`: 0
- `valid_bad_future_bars`: 0
- `valid_bad_offsets`: 0
- `valid_null_extreme_ts`: 0
- `extreme_less_than_mean`: 0
- `negative_targets`: 0
- `nonfinite_targets`: 0
- `invalid_nonnull_targets`: 0
- `invalid_nonnull_raw`: 0
- `bad_variant`: 0
- `bad_policy`: 0
- `target_reg_distance_up_extreme_hvol_v2_bad_norm`: 0
- `target_reg_distance_up_mean_high_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_mean_low_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_extreme_hvol_v2_bad_norm`: 0
- `horizon_minutes_mismatch`: 0
- `horizon_vol_mismatch`: 0

Window metadata counters:

- `unique_label_windows_used`: 1378
- `missing_window_stats`: 0
- `future_bars_mismatch`: 0
- `max_high_offset_mismatch`: 0
- `max_high_ts_mismatch`: 0
- `min_low_offset_mismatch`: 0
- `min_low_ts_mismatch`: 0
- `source_window_count`: 1661

Independent raw-distance recomputation:

- `target_reg_distance_up_extreme_pct_v2`: rows=990,657, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_up_mean_high_pct_v2`: rows=990,657, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_mean_low_pct_v2`: rows=990,657, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_extreme_pct_v2`: rows=990,657, max_abs_error=0.000e+00, violations_gt_1e_12=0

## GC 24h/C

Label root: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/gc/htf_4class_labels_24h_shift12h_reg_distance_horizon_vol_v2/1m`
Window source: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/gc/htf_backtest_24h/15m_HTF_combined.parquet`

Invariant counters:

- `rows`: 1734017
- `unique_ts_batch`: 1734017
- `valid_rows`: 743334
- `invalid_rows`: 990683
- `valid_not_label_half`: 0
- `valid_reason_not_ok`: 0
- `invalid_reason_ok`: 0
- `valid_bad_vol`: 0
- `valid_bad_future_bars`: 0
- `valid_bad_offsets`: 0
- `valid_null_extreme_ts`: 0
- `extreme_less_than_mean`: 0
- `negative_targets`: 0
- `nonfinite_targets`: 0
- `invalid_nonnull_targets`: 0
- `invalid_nonnull_raw`: 0
- `bad_variant`: 0
- `bad_policy`: 0
- `target_reg_distance_up_extreme_hvol_v2_bad_norm`: 0
- `target_reg_distance_up_mean_high_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_mean_low_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_extreme_hvol_v2_bad_norm`: 0
- `horizon_minutes_mismatch`: 0
- `horizon_vol_mismatch`: 0

Window metadata counters:

- `unique_label_windows_used`: 1378
- `missing_window_stats`: 0
- `future_bars_mismatch`: 0
- `max_high_offset_mismatch`: 0
- `max_high_ts_mismatch`: 0
- `min_low_offset_mismatch`: 0
- `min_low_ts_mismatch`: 0
- `source_window_count`: 1378

Independent raw-distance recomputation:

- `target_reg_distance_up_extreme_pct_v2`: rows=743,334, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_up_mean_high_pct_v2`: rows=743,334, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_mean_low_pct_v2`: rows=743,334, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_extreme_pct_v2`: rows=743,334, max_abs_error=0.000e+00, violations_gt_1e_12=0

## GC 7d/B

Label root: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/gc/htf_4class_labels_7d_reg_distance_horizon_vol_v2/1m`
Window source: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/gc/htf_backtest_7d_shift84h/15m_HTF_combined.parquet`

Invariant counters:

- `rows`: 1887369
- `unique_ts_batch`: 1887369
- `valid_rows`: 1335202
- `invalid_rows`: 552167
- `valid_not_label_half`: 0
- `valid_reason_not_ok`: 0
- `invalid_reason_ok`: 0
- `valid_bad_vol`: 0
- `valid_bad_future_bars`: 0
- `valid_bad_offsets`: 0
- `valid_null_extreme_ts`: 0
- `extreme_less_than_mean`: 0
- `negative_targets`: 0
- `nonfinite_targets`: 0
- `invalid_nonnull_targets`: 0
- `invalid_nonnull_raw`: 0
- `bad_variant`: 0
- `bad_policy`: 0
- `target_reg_distance_up_extreme_hvol_v2_bad_norm`: 0
- `target_reg_distance_up_mean_high_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_mean_low_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_extreme_hvol_v2_bad_norm`: 0
- `horizon_minutes_mismatch`: 0
- `horizon_vol_mismatch`: 0

Window metadata counters:

- `unique_label_windows_used`: 278
- `missing_window_stats`: 0
- `future_bars_mismatch`: 0
- `max_high_offset_mismatch`: 0
- `max_high_ts_mismatch`: 0
- `min_low_offset_mismatch`: 0
- `min_low_ts_mismatch`: 0
- `source_window_count`: 279

Independent raw-distance recomputation:

- `target_reg_distance_up_extreme_pct_v2`: rows=1,335,202, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_up_mean_high_pct_v2`: rows=1,335,202, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_mean_low_pct_v2`: rows=1,335,202, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_extreme_pct_v2`: rows=1,335,202, max_abs_error=0.000e+00, violations_gt_1e_12=0

## GC 7d/C

Label root: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/gc/htf_4class_labels_7d_shift84h_reg_distance_horizon_vol_v2/1m`
Window source: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/gc/htf_backtest_7d/15m_HTF_combined.parquet`

Invariant counters:

- `rows`: 1891449
- `unique_ts_batch`: 1891449
- `valid_rows`: 552201
- `invalid_rows`: 1339248
- `valid_not_label_half`: 0
- `valid_reason_not_ok`: 0
- `invalid_reason_ok`: 0
- `valid_bad_vol`: 0
- `valid_bad_future_bars`: 0
- `valid_bad_offsets`: 0
- `valid_null_extreme_ts`: 0
- `extreme_less_than_mean`: 0
- `negative_targets`: 0
- `nonfinite_targets`: 0
- `invalid_nonnull_targets`: 0
- `invalid_nonnull_raw`: 0
- `bad_variant`: 0
- `bad_policy`: 0
- `target_reg_distance_up_extreme_hvol_v2_bad_norm`: 0
- `target_reg_distance_up_mean_high_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_mean_low_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_extreme_hvol_v2_bad_norm`: 0
- `horizon_minutes_mismatch`: 0
- `horizon_vol_mismatch`: 0

Window metadata counters:

- `unique_label_windows_used`: 279
- `missing_window_stats`: 0
- `future_bars_mismatch`: 0
- `max_high_offset_mismatch`: 0
- `max_high_ts_mismatch`: 0
- `min_low_offset_mismatch`: 0
- `min_low_ts_mismatch`: 0
- `source_window_count`: 279

Independent raw-distance recomputation:

- `target_reg_distance_up_extreme_pct_v2`: rows=552,201, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_up_mean_high_pct_v2`: rows=552,201, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_mean_low_pct_v2`: rows=552,201, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_extreme_pct_v2`: rows=552,201, max_abs_error=0.000e+00, violations_gt_1e_12=0

## CL 8h/B

Label root: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/cl/htf_4class_labels_reg_distance_horizon_vol_v2/1m`
Window source: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/cl/htf_backtest_shift4h/15m_HTF_combined.parquet`

Invariant counters:

- `rows`: 1863859
- `unique_ts_batch`: 1863859
- `valid_rows`: 987077
- `invalid_rows`: 876782
- `valid_not_label_half`: 0
- `valid_reason_not_ok`: 0
- `invalid_reason_ok`: 0
- `valid_bad_vol`: 0
- `valid_bad_future_bars`: 0
- `valid_bad_offsets`: 0
- `valid_null_extreme_ts`: 0
- `extreme_less_than_mean`: 0
- `negative_targets`: 0
- `nonfinite_targets`: 0
- `invalid_nonnull_targets`: 0
- `invalid_nonnull_raw`: 0
- `bad_variant`: 0
- `bad_policy`: 0
- `target_reg_distance_up_extreme_hvol_v2_bad_norm`: 0
- `target_reg_distance_up_mean_high_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_mean_low_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_extreme_hvol_v2_bad_norm`: 0
- `horizon_minutes_mismatch`: 0
- `horizon_vol_mismatch`: 0

Window metadata counters:

- `unique_label_windows_used`: 4124
- `missing_window_stats`: 0
- `future_bars_mismatch`: 0
- `max_high_offset_mismatch`: 0
- `max_high_ts_mismatch`: 0
- `min_low_offset_mismatch`: 0
- `min_low_ts_mismatch`: 0
- `source_window_count`: 4408

Independent raw-distance recomputation:

- `target_reg_distance_up_extreme_pct_v2`: rows=987,077, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_up_mean_high_pct_v2`: rows=987,077, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_mean_low_pct_v2`: rows=987,077, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_extreme_pct_v2`: rows=987,077, max_abs_error=0.000e+00, violations_gt_1e_12=0

## CL 8h/C

Label root: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/cl/htf_4class_labels_shift4h_reg_distance_horizon_vol_v2/1m`
Window source: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/cl/htf_backtest/15m_HTF_combined.parquet`

Invariant counters:

- `rows`: 1870913
- `unique_ts_batch`: 1870913
- `valid_rows`: 882307
- `invalid_rows`: 988606
- `valid_not_label_half`: 0
- `valid_reason_not_ok`: 0
- `invalid_reason_ok`: 0
- `valid_bad_vol`: 0
- `valid_bad_future_bars`: 0
- `valid_bad_offsets`: 0
- `valid_null_extreme_ts`: 0
- `extreme_less_than_mean`: 0
- `negative_targets`: 0
- `nonfinite_targets`: 0
- `invalid_nonnull_targets`: 0
- `invalid_nonnull_raw`: 0
- `bad_variant`: 0
- `bad_policy`: 0
- `target_reg_distance_up_extreme_hvol_v2_bad_norm`: 0
- `target_reg_distance_up_mean_high_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_mean_low_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_extreme_hvol_v2_bad_norm`: 0
- `horizon_minutes_mismatch`: 0
- `horizon_vol_mismatch`: 0

Window metadata counters:

- `unique_label_windows_used`: 4133
- `missing_window_stats`: 0
- `future_bars_mismatch`: 0
- `max_high_offset_mismatch`: 0
- `max_high_ts_mismatch`: 0
- `min_low_offset_mismatch`: 0
- `min_low_ts_mismatch`: 0
- `source_window_count`: 4133

Independent raw-distance recomputation:

- `target_reg_distance_up_extreme_pct_v2`: rows=882,307, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_up_mean_high_pct_v2`: rows=882,307, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_mean_low_pct_v2`: rows=882,307, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_extreme_pct_v2`: rows=882,307, max_abs_error=0.000e+00, violations_gt_1e_12=0

## CL 24h/B

Label root: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/cl/htf_4class_labels_24h_reg_distance_horizon_vol_v2/1m`
Window source: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/cl/htf_backtest_24h_shift12h/15m_HTF_combined.parquet`

Invariant counters:

- `rows`: 1865512
- `unique_ts_batch`: 1865512
- `valid_rows`: 991595
- `invalid_rows`: 873917
- `valid_not_label_half`: 0
- `valid_reason_not_ok`: 0
- `invalid_reason_ok`: 0
- `valid_bad_vol`: 0
- `valid_bad_future_bars`: 0
- `valid_bad_offsets`: 0
- `valid_null_extreme_ts`: 0
- `extreme_less_than_mean`: 0
- `negative_targets`: 0
- `nonfinite_targets`: 0
- `invalid_nonnull_targets`: 0
- `invalid_nonnull_raw`: 0
- `bad_variant`: 0
- `bad_policy`: 0
- `target_reg_distance_up_extreme_hvol_v2_bad_norm`: 0
- `target_reg_distance_up_mean_high_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_mean_low_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_extreme_hvol_v2_bad_norm`: 0
- `horizon_minutes_mismatch`: 0
- `horizon_vol_mismatch`: 0

Window metadata counters:

- `unique_label_windows_used`: 1378
- `missing_window_stats`: 0
- `future_bars_mismatch`: 0
- `max_high_offset_mismatch`: 0
- `max_high_ts_mismatch`: 0
- `min_low_offset_mismatch`: 0
- `min_low_ts_mismatch`: 0
- `source_window_count`: 1661

Independent raw-distance recomputation:

- `target_reg_distance_up_extreme_pct_v2`: rows=991,595, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_up_mean_high_pct_v2`: rows=991,595, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_mean_low_pct_v2`: rows=991,595, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_extreme_pct_v2`: rows=991,595, max_abs_error=0.000e+00, violations_gt_1e_12=0

## CL 24h/C

Label root: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/cl/htf_4class_labels_24h_shift12h_reg_distance_horizon_vol_v2/1m`
Window source: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/cl/htf_backtest_24h/15m_HTF_combined.parquet`

Invariant counters:

- `rows`: 1735748
- `unique_ts_batch`: 1735748
- `valid_rows`: 744127
- `invalid_rows`: 991621
- `valid_not_label_half`: 0
- `valid_reason_not_ok`: 0
- `invalid_reason_ok`: 0
- `valid_bad_vol`: 0
- `valid_bad_future_bars`: 0
- `valid_bad_offsets`: 0
- `valid_null_extreme_ts`: 0
- `extreme_less_than_mean`: 0
- `negative_targets`: 0
- `nonfinite_targets`: 0
- `invalid_nonnull_targets`: 0
- `invalid_nonnull_raw`: 0
- `bad_variant`: 0
- `bad_policy`: 0
- `target_reg_distance_up_extreme_hvol_v2_bad_norm`: 0
- `target_reg_distance_up_mean_high_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_mean_low_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_extreme_hvol_v2_bad_norm`: 0
- `horizon_minutes_mismatch`: 0
- `horizon_vol_mismatch`: 0

Window metadata counters:

- `unique_label_windows_used`: 1378
- `missing_window_stats`: 0
- `future_bars_mismatch`: 0
- `max_high_offset_mismatch`: 0
- `max_high_ts_mismatch`: 0
- `min_low_offset_mismatch`: 0
- `min_low_ts_mismatch`: 0
- `source_window_count`: 1378

Independent raw-distance recomputation:

- `target_reg_distance_up_extreme_pct_v2`: rows=744,127, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_up_mean_high_pct_v2`: rows=744,127, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_mean_low_pct_v2`: rows=744,127, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_extreme_pct_v2`: rows=744,127, max_abs_error=0.000e+00, violations_gt_1e_12=0

## CL 7d/B

Label root: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/cl/htf_4class_labels_7d_reg_distance_horizon_vol_v2/1m`
Window source: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/cl/htf_backtest_7d_shift84h/15m_HTF_combined.parquet`

Invariant counters:

- `rows`: 1889150
- `unique_ts_batch`: 1889150
- `valid_rows`: 1336120
- `invalid_rows`: 553030
- `valid_not_label_half`: 0
- `valid_reason_not_ok`: 0
- `invalid_reason_ok`: 0
- `valid_bad_vol`: 0
- `valid_bad_future_bars`: 0
- `valid_bad_offsets`: 0
- `valid_null_extreme_ts`: 0
- `extreme_less_than_mean`: 0
- `negative_targets`: 0
- `nonfinite_targets`: 0
- `invalid_nonnull_targets`: 0
- `invalid_nonnull_raw`: 0
- `bad_variant`: 0
- `bad_policy`: 0
- `target_reg_distance_up_extreme_hvol_v2_bad_norm`: 0
- `target_reg_distance_up_mean_high_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_mean_low_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_extreme_hvol_v2_bad_norm`: 0
- `horizon_minutes_mismatch`: 0
- `horizon_vol_mismatch`: 0

Window metadata counters:

- `unique_label_windows_used`: 278
- `missing_window_stats`: 0
- `future_bars_mismatch`: 0
- `max_high_offset_mismatch`: 0
- `max_high_ts_mismatch`: 0
- `min_low_offset_mismatch`: 0
- `min_low_ts_mismatch`: 0
- `source_window_count`: 279

Independent raw-distance recomputation:

- `target_reg_distance_up_extreme_pct_v2`: rows=1,336,120, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_up_mean_high_pct_v2`: rows=1,336,120, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_mean_low_pct_v2`: rows=1,336,120, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_extreme_pct_v2`: rows=1,336,120, max_abs_error=0.000e+00, violations_gt_1e_12=0

## CL 7d/C

Label root: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/cl/htf_4class_labels_7d_shift84h_reg_distance_horizon_vol_v2/1m`
Window source: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/cl/htf_backtest_7d/15m_HTF_combined.parquet`

Invariant counters:

- `rows`: 1893230
- `unique_ts_batch`: 1893230
- `valid_rows`: 553064
- `invalid_rows`: 1340166
- `valid_not_label_half`: 0
- `valid_reason_not_ok`: 0
- `invalid_reason_ok`: 0
- `valid_bad_vol`: 0
- `valid_bad_future_bars`: 0
- `valid_bad_offsets`: 0
- `valid_null_extreme_ts`: 0
- `extreme_less_than_mean`: 0
- `negative_targets`: 0
- `nonfinite_targets`: 0
- `invalid_nonnull_targets`: 0
- `invalid_nonnull_raw`: 0
- `bad_variant`: 0
- `bad_policy`: 0
- `target_reg_distance_up_extreme_hvol_v2_bad_norm`: 0
- `target_reg_distance_up_mean_high_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_mean_low_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_extreme_hvol_v2_bad_norm`: 0
- `horizon_minutes_mismatch`: 0
- `horizon_vol_mismatch`: 0

Window metadata counters:

- `unique_label_windows_used`: 279
- `missing_window_stats`: 0
- `future_bars_mismatch`: 0
- `max_high_offset_mismatch`: 0
- `max_high_ts_mismatch`: 0
- `min_low_offset_mismatch`: 0
- `min_low_ts_mismatch`: 0
- `source_window_count`: 279

Independent raw-distance recomputation:

- `target_reg_distance_up_extreme_pct_v2`: rows=553,064, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_up_mean_high_pct_v2`: rows=553,064, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_mean_low_pct_v2`: rows=553,064, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_extreme_pct_v2`: rows=553,064, max_abs_error=0.000e+00, violations_gt_1e_12=0

## ES 8h/B

Label root: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/es/htf_4class_labels_reg_distance_horizon_vol_v2/1m`
Window source: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/es/htf_backtest_shift4h/15m_HTF_combined.parquet`

Invariant counters:

- `rows`: 1863301
- `unique_ts_batch`: 1863301
- `valid_rows`: 985172
- `invalid_rows`: 878129
- `valid_not_label_half`: 0
- `valid_reason_not_ok`: 0
- `invalid_reason_ok`: 0
- `valid_bad_vol`: 0
- `valid_bad_future_bars`: 0
- `valid_bad_offsets`: 0
- `valid_null_extreme_ts`: 0
- `extreme_less_than_mean`: 0
- `negative_targets`: 0
- `nonfinite_targets`: 0
- `invalid_nonnull_targets`: 0
- `invalid_nonnull_raw`: 0
- `bad_variant`: 0
- `bad_policy`: 0
- `target_reg_distance_up_extreme_hvol_v2_bad_norm`: 0
- `target_reg_distance_up_mean_high_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_mean_low_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_extreme_hvol_v2_bad_norm`: 0
- `horizon_minutes_mismatch`: 0
- `horizon_vol_mismatch`: 0

Window metadata counters:

- `unique_label_windows_used`: 4129
- `missing_window_stats`: 0
- `future_bars_mismatch`: 0
- `max_high_offset_mismatch`: 0
- `max_high_ts_mismatch`: 0
- `min_low_offset_mismatch`: 0
- `min_low_ts_mismatch`: 0
- `source_window_count`: 4414

Independent raw-distance recomputation:

- `target_reg_distance_up_extreme_pct_v2`: rows=985,172, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_up_mean_high_pct_v2`: rows=985,172, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_mean_low_pct_v2`: rows=985,172, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_extreme_pct_v2`: rows=985,172, max_abs_error=0.000e+00, violations_gt_1e_12=0

## ES 8h/C

Label root: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/es/htf_4class_labels_shift4h_reg_distance_horizon_vol_v2/1m`
Window source: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/es/htf_backtest/15m_HTF_combined.parquet`

Invariant counters:

- `rows`: 1869886
- `unique_ts_batch`: 1869886
- `valid_rows`: 883518
- `invalid_rows`: 986368
- `valid_not_label_half`: 0
- `valid_reason_not_ok`: 0
- `invalid_reason_ok`: 0
- `valid_bad_vol`: 0
- `valid_bad_future_bars`: 0
- `valid_bad_offsets`: 0
- `valid_null_extreme_ts`: 0
- `extreme_less_than_mean`: 0
- `negative_targets`: 0
- `nonfinite_targets`: 0
- `invalid_nonnull_targets`: 0
- `invalid_nonnull_raw`: 0
- `bad_variant`: 0
- `bad_policy`: 0
- `target_reg_distance_up_extreme_hvol_v2_bad_norm`: 0
- `target_reg_distance_up_mean_high_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_mean_low_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_extreme_hvol_v2_bad_norm`: 0
- `horizon_minutes_mismatch`: 0
- `horizon_vol_mismatch`: 0

Window metadata counters:

- `unique_label_windows_used`: 4138
- `missing_window_stats`: 0
- `future_bars_mismatch`: 0
- `max_high_offset_mismatch`: 0
- `max_high_ts_mismatch`: 0
- `min_low_offset_mismatch`: 0
- `min_low_ts_mismatch`: 0
- `source_window_count`: 4138

Independent raw-distance recomputation:

- `target_reg_distance_up_extreme_pct_v2`: rows=883,518, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_up_mean_high_pct_v2`: rows=883,518, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_mean_low_pct_v2`: rows=883,518, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_extreme_pct_v2`: rows=883,518, max_abs_error=0.000e+00, violations_gt_1e_12=0

## ES 24h/B

Label root: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/es/htf_4class_labels_24h_reg_distance_horizon_vol_v2/1m`
Window source: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/es/htf_backtest_24h_shift12h/15m_HTF_combined.parquet`

Invariant counters:

- `rows`: 1864681
- `unique_ts_batch`: 1864681
- `valid_rows`: 993752
- `invalid_rows`: 870929
- `valid_not_label_half`: 0
- `valid_reason_not_ok`: 0
- `invalid_reason_ok`: 0
- `valid_bad_vol`: 0
- `valid_bad_future_bars`: 0
- `valid_bad_offsets`: 0
- `valid_null_extreme_ts`: 0
- `extreme_less_than_mean`: 0
- `negative_targets`: 0
- `nonfinite_targets`: 0
- `invalid_nonnull_targets`: 0
- `invalid_nonnull_raw`: 0
- `bad_variant`: 0
- `bad_policy`: 0
- `target_reg_distance_up_extreme_hvol_v2_bad_norm`: 0
- `target_reg_distance_up_mean_high_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_mean_low_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_extreme_hvol_v2_bad_norm`: 0
- `horizon_minutes_mismatch`: 0
- `horizon_vol_mismatch`: 0

Window metadata counters:

- `unique_label_windows_used`: 1381
- `missing_window_stats`: 0
- `future_bars_mismatch`: 0
- `max_high_offset_mismatch`: 0
- `max_high_ts_mismatch`: 0
- `min_low_offset_mismatch`: 0
- `min_low_ts_mismatch`: 0
- `source_window_count`: 1664

Independent raw-distance recomputation:

- `target_reg_distance_up_extreme_pct_v2`: rows=993,752, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_up_mean_high_pct_v2`: rows=993,752, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_mean_low_pct_v2`: rows=993,752, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_extreme_pct_v2`: rows=993,752, max_abs_error=0.000e+00, violations_gt_1e_12=0

## ES 24h/C

Label root: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/es/htf_4class_labels_24h_shift12h_reg_distance_horizon_vol_v2/1m`
Window source: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/es/htf_backtest_24h/15m_HTF_combined.parquet`

Invariant counters:

- `rows`: 1736641
- `unique_ts_batch`: 1736641
- `valid_rows`: 742863
- `invalid_rows`: 993778
- `valid_not_label_half`: 0
- `valid_reason_not_ok`: 0
- `invalid_reason_ok`: 0
- `valid_bad_vol`: 0
- `valid_bad_future_bars`: 0
- `valid_bad_offsets`: 0
- `valid_null_extreme_ts`: 0
- `extreme_less_than_mean`: 0
- `negative_targets`: 0
- `nonfinite_targets`: 0
- `invalid_nonnull_targets`: 0
- `invalid_nonnull_raw`: 0
- `bad_variant`: 0
- `bad_policy`: 0
- `target_reg_distance_up_extreme_hvol_v2_bad_norm`: 0
- `target_reg_distance_up_mean_high_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_mean_low_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_extreme_hvol_v2_bad_norm`: 0
- `horizon_minutes_mismatch`: 0
- `horizon_vol_mismatch`: 0

Window metadata counters:

- `unique_label_windows_used`: 1381
- `missing_window_stats`: 0
- `future_bars_mismatch`: 0
- `max_high_offset_mismatch`: 0
- `max_high_ts_mismatch`: 0
- `min_low_offset_mismatch`: 0
- `min_low_ts_mismatch`: 0
- `source_window_count`: 1381

Independent raw-distance recomputation:

- `target_reg_distance_up_extreme_pct_v2`: rows=742,863, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_up_mean_high_pct_v2`: rows=742,863, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_mean_low_pct_v2`: rows=742,863, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_extreme_pct_v2`: rows=742,863, max_abs_error=0.000e+00, violations_gt_1e_12=0

## ES 7d/B

Label root: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/es/htf_4class_labels_7d_reg_distance_horizon_vol_v2/1m`
Window source: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/es/htf_backtest_7d_shift84h/15m_HTF_combined.parquet`

Invariant counters:

- `rows`: 1888321
- `unique_ts_batch`: 1888321
- `valid_rows`: 1333848
- `invalid_rows`: 554473
- `valid_not_label_half`: 0
- `valid_reason_not_ok`: 0
- `invalid_reason_ok`: 0
- `valid_bad_vol`: 0
- `valid_bad_future_bars`: 0
- `valid_bad_offsets`: 0
- `valid_null_extreme_ts`: 0
- `extreme_less_than_mean`: 0
- `negative_targets`: 0
- `nonfinite_targets`: 0
- `invalid_nonnull_targets`: 0
- `invalid_nonnull_raw`: 0
- `bad_variant`: 0
- `bad_policy`: 0
- `target_reg_distance_up_extreme_hvol_v2_bad_norm`: 0
- `target_reg_distance_up_mean_high_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_mean_low_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_extreme_hvol_v2_bad_norm`: 0
- `horizon_minutes_mismatch`: 0
- `horizon_vol_mismatch`: 0

Window metadata counters:

- `unique_label_windows_used`: 278
- `missing_window_stats`: 0
- `future_bars_mismatch`: 0
- `max_high_offset_mismatch`: 0
- `max_high_ts_mismatch`: 0
- `min_low_offset_mismatch`: 0
- `min_low_ts_mismatch`: 0
- `source_window_count`: 279

Independent raw-distance recomputation:

- `target_reg_distance_up_extreme_pct_v2`: rows=1,333,848, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_up_mean_high_pct_v2`: rows=1,333,848, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_mean_low_pct_v2`: rows=1,333,848, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_extreme_pct_v2`: rows=1,333,848, max_abs_error=0.000e+00, violations_gt_1e_12=0

## ES 7d/C

Label root: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/es/htf_4class_labels_7d_shift84h_reg_distance_horizon_vol_v2/1m`
Window source: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/es/htf_backtest_7d/15m_HTF_combined.parquet`

Invariant counters:

- `rows`: 1342966
- `unique_ts_batch`: 1342966
- `valid_rows`: 393152
- `invalid_rows`: 949814
- `valid_not_label_half`: 0
- `valid_reason_not_ok`: 0
- `invalid_reason_ok`: 0
- `valid_bad_vol`: 0
- `valid_bad_future_bars`: 0
- `valid_bad_offsets`: 0
- `valid_null_extreme_ts`: 0
- `extreme_less_than_mean`: 0
- `negative_targets`: 0
- `nonfinite_targets`: 0
- `invalid_nonnull_targets`: 0
- `invalid_nonnull_raw`: 0
- `bad_variant`: 0
- `bad_policy`: 0
- `target_reg_distance_up_extreme_hvol_v2_bad_norm`: 0
- `target_reg_distance_up_mean_high_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_mean_low_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_extreme_hvol_v2_bad_norm`: 0
- `horizon_minutes_mismatch`: 0
- `horizon_vol_mismatch`: 0

Window metadata counters:

- `unique_label_windows_used`: 199
- `missing_window_stats`: 0
- `future_bars_mismatch`: 0
- `max_high_offset_mismatch`: 0
- `max_high_ts_mismatch`: 0
- `min_low_offset_mismatch`: 0
- `min_low_ts_mismatch`: 0
- `source_window_count`: 279

Independent raw-distance recomputation:

- `target_reg_distance_up_extreme_pct_v2`: rows=393,152, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_up_mean_high_pct_v2`: rows=393,152, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_mean_low_pct_v2`: rows=393,152, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_extreme_pct_v2`: rows=393,152, max_abs_error=0.000e+00, violations_gt_1e_12=0

## NQ 8h/B

Label root: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/nq/htf_4class_labels_reg_distance_horizon_vol_v2/1m`
Window source: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/nq/htf_backtest_shift4h/15m_HTF_combined.parquet`

Invariant counters:

- `rows`: 1863298
- `unique_ts_batch`: 1863298
- `valid_rows`: 985172
- `invalid_rows`: 878126
- `valid_not_label_half`: 0
- `valid_reason_not_ok`: 0
- `invalid_reason_ok`: 0
- `valid_bad_vol`: 0
- `valid_bad_future_bars`: 0
- `valid_bad_offsets`: 0
- `valid_null_extreme_ts`: 0
- `extreme_less_than_mean`: 0
- `negative_targets`: 0
- `nonfinite_targets`: 0
- `invalid_nonnull_targets`: 0
- `invalid_nonnull_raw`: 0
- `bad_variant`: 0
- `bad_policy`: 0
- `target_reg_distance_up_extreme_hvol_v2_bad_norm`: 0
- `target_reg_distance_up_mean_high_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_mean_low_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_extreme_hvol_v2_bad_norm`: 0
- `horizon_minutes_mismatch`: 0
- `horizon_vol_mismatch`: 0

Window metadata counters:

- `unique_label_windows_used`: 4129
- `missing_window_stats`: 0
- `future_bars_mismatch`: 0
- `max_high_offset_mismatch`: 0
- `max_high_ts_mismatch`: 0
- `min_low_offset_mismatch`: 0
- `min_low_ts_mismatch`: 0
- `source_window_count`: 4414

Independent raw-distance recomputation:

- `target_reg_distance_up_extreme_pct_v2`: rows=985,172, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_up_mean_high_pct_v2`: rows=985,172, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_mean_low_pct_v2`: rows=985,172, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_extreme_pct_v2`: rows=985,172, max_abs_error=0.000e+00, violations_gt_1e_12=0

## NQ 8h/C

Label root: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/nq/htf_4class_labels_shift4h_reg_distance_horizon_vol_v2/1m`
Window source: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/nq/htf_backtest/15m_HTF_combined.parquet`

Invariant counters:

- `rows`: 1869883
- `unique_ts_batch`: 1869883
- `valid_rows`: 883515
- `invalid_rows`: 986368
- `valid_not_label_half`: 0
- `valid_reason_not_ok`: 0
- `invalid_reason_ok`: 0
- `valid_bad_vol`: 0
- `valid_bad_future_bars`: 0
- `valid_bad_offsets`: 0
- `valid_null_extreme_ts`: 0
- `extreme_less_than_mean`: 0
- `negative_targets`: 0
- `nonfinite_targets`: 0
- `invalid_nonnull_targets`: 0
- `invalid_nonnull_raw`: 0
- `bad_variant`: 0
- `bad_policy`: 0
- `target_reg_distance_up_extreme_hvol_v2_bad_norm`: 0
- `target_reg_distance_up_mean_high_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_mean_low_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_extreme_hvol_v2_bad_norm`: 0
- `horizon_minutes_mismatch`: 0
- `horizon_vol_mismatch`: 0

Window metadata counters:

- `unique_label_windows_used`: 4138
- `missing_window_stats`: 0
- `future_bars_mismatch`: 0
- `max_high_offset_mismatch`: 0
- `max_high_ts_mismatch`: 0
- `min_low_offset_mismatch`: 0
- `min_low_ts_mismatch`: 0
- `source_window_count`: 4138

Independent raw-distance recomputation:

- `target_reg_distance_up_extreme_pct_v2`: rows=883,515, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_up_mean_high_pct_v2`: rows=883,515, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_mean_low_pct_v2`: rows=883,515, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_extreme_pct_v2`: rows=883,515, max_abs_error=0.000e+00, violations_gt_1e_12=0

## NQ 24h/B

Label root: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/nq/htf_4class_labels_24h_reg_distance_horizon_vol_v2/1m`
Window source: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/nq/htf_backtest_24h_shift12h/15m_HTF_combined.parquet`

Invariant counters:

- `rows`: 1864678
- `unique_ts_batch`: 1864678
- `valid_rows`: 993752
- `invalid_rows`: 870926
- `valid_not_label_half`: 0
- `valid_reason_not_ok`: 0
- `invalid_reason_ok`: 0
- `valid_bad_vol`: 0
- `valid_bad_future_bars`: 0
- `valid_bad_offsets`: 0
- `valid_null_extreme_ts`: 0
- `extreme_less_than_mean`: 0
- `negative_targets`: 0
- `nonfinite_targets`: 0
- `invalid_nonnull_targets`: 0
- `invalid_nonnull_raw`: 0
- `bad_variant`: 0
- `bad_policy`: 0
- `target_reg_distance_up_extreme_hvol_v2_bad_norm`: 0
- `target_reg_distance_up_mean_high_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_mean_low_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_extreme_hvol_v2_bad_norm`: 0
- `horizon_minutes_mismatch`: 0
- `horizon_vol_mismatch`: 0

Window metadata counters:

- `unique_label_windows_used`: 1381
- `missing_window_stats`: 0
- `future_bars_mismatch`: 0
- `max_high_offset_mismatch`: 0
- `max_high_ts_mismatch`: 0
- `min_low_offset_mismatch`: 0
- `min_low_ts_mismatch`: 0
- `source_window_count`: 1664

Independent raw-distance recomputation:

- `target_reg_distance_up_extreme_pct_v2`: rows=993,752, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_up_mean_high_pct_v2`: rows=993,752, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_mean_low_pct_v2`: rows=993,752, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_extreme_pct_v2`: rows=993,752, max_abs_error=0.000e+00, violations_gt_1e_12=0

## NQ 24h/C

Label root: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/nq/htf_4class_labels_24h_shift12h_reg_distance_horizon_vol_v2/1m`
Window source: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/nq/htf_backtest_24h/15m_HTF_combined.parquet`

Invariant counters:

- `rows`: 1736638
- `unique_ts_batch`: 1736638
- `valid_rows`: 742860
- `invalid_rows`: 993778
- `valid_not_label_half`: 0
- `valid_reason_not_ok`: 0
- `invalid_reason_ok`: 0
- `valid_bad_vol`: 0
- `valid_bad_future_bars`: 0
- `valid_bad_offsets`: 0
- `valid_null_extreme_ts`: 0
- `extreme_less_than_mean`: 0
- `negative_targets`: 0
- `nonfinite_targets`: 0
- `invalid_nonnull_targets`: 0
- `invalid_nonnull_raw`: 0
- `bad_variant`: 0
- `bad_policy`: 0
- `target_reg_distance_up_extreme_hvol_v2_bad_norm`: 0
- `target_reg_distance_up_mean_high_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_mean_low_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_extreme_hvol_v2_bad_norm`: 0
- `horizon_minutes_mismatch`: 0
- `horizon_vol_mismatch`: 0

Window metadata counters:

- `unique_label_windows_used`: 1381
- `missing_window_stats`: 0
- `future_bars_mismatch`: 0
- `max_high_offset_mismatch`: 0
- `max_high_ts_mismatch`: 0
- `min_low_offset_mismatch`: 0
- `min_low_ts_mismatch`: 0
- `source_window_count`: 1381

Independent raw-distance recomputation:

- `target_reg_distance_up_extreme_pct_v2`: rows=742,860, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_up_mean_high_pct_v2`: rows=742,860, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_mean_low_pct_v2`: rows=742,860, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_extreme_pct_v2`: rows=742,860, max_abs_error=0.000e+00, violations_gt_1e_12=0

## NQ 7d/B

Label root: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/nq/htf_4class_labels_7d_reg_distance_horizon_vol_v2/1m`
Window source: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/nq/htf_backtest_7d_shift84h/15m_HTF_combined.parquet`

Invariant counters:

- `rows`: 1888318
- `unique_ts_batch`: 1888318
- `valid_rows`: 1333845
- `invalid_rows`: 554473
- `valid_not_label_half`: 0
- `valid_reason_not_ok`: 0
- `invalid_reason_ok`: 0
- `valid_bad_vol`: 0
- `valid_bad_future_bars`: 0
- `valid_bad_offsets`: 0
- `valid_null_extreme_ts`: 0
- `extreme_less_than_mean`: 0
- `negative_targets`: 0
- `nonfinite_targets`: 0
- `invalid_nonnull_targets`: 0
- `invalid_nonnull_raw`: 0
- `bad_variant`: 0
- `bad_policy`: 0
- `target_reg_distance_up_extreme_hvol_v2_bad_norm`: 0
- `target_reg_distance_up_mean_high_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_mean_low_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_extreme_hvol_v2_bad_norm`: 0
- `horizon_minutes_mismatch`: 0
- `horizon_vol_mismatch`: 0

Window metadata counters:

- `unique_label_windows_used`: 278
- `missing_window_stats`: 0
- `future_bars_mismatch`: 0
- `max_high_offset_mismatch`: 0
- `max_high_ts_mismatch`: 0
- `min_low_offset_mismatch`: 0
- `min_low_ts_mismatch`: 0
- `source_window_count`: 279

Independent raw-distance recomputation:

- `target_reg_distance_up_extreme_pct_v2`: rows=1,333,845, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_up_mean_high_pct_v2`: rows=1,333,845, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_mean_low_pct_v2`: rows=1,333,845, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_extreme_pct_v2`: rows=1,333,845, max_abs_error=0.000e+00, violations_gt_1e_12=0

## NQ 7d/C

Label root: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/nq/htf_4class_labels_7d_shift84h_reg_distance_horizon_vol_v2/1m`
Window source: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/nq/htf_backtest_7d/15m_HTF_combined.parquet`

Invariant counters:

- `rows`: 1892398
- `unique_ts_batch`: 1892398
- `valid_rows`: 554507
- `invalid_rows`: 1337891
- `valid_not_label_half`: 0
- `valid_reason_not_ok`: 0
- `invalid_reason_ok`: 0
- `valid_bad_vol`: 0
- `valid_bad_future_bars`: 0
- `valid_bad_offsets`: 0
- `valid_null_extreme_ts`: 0
- `extreme_less_than_mean`: 0
- `negative_targets`: 0
- `nonfinite_targets`: 0
- `invalid_nonnull_targets`: 0
- `invalid_nonnull_raw`: 0
- `bad_variant`: 0
- `bad_policy`: 0
- `target_reg_distance_up_extreme_hvol_v2_bad_norm`: 0
- `target_reg_distance_up_mean_high_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_mean_low_hvol_v2_bad_norm`: 0
- `target_reg_distance_down_extreme_hvol_v2_bad_norm`: 0
- `horizon_minutes_mismatch`: 0
- `horizon_vol_mismatch`: 0

Window metadata counters:

- `unique_label_windows_used`: 279
- `missing_window_stats`: 0
- `future_bars_mismatch`: 0
- `max_high_offset_mismatch`: 0
- `max_high_ts_mismatch`: 0
- `min_low_offset_mismatch`: 0
- `min_low_ts_mismatch`: 0
- `source_window_count`: 279

Independent raw-distance recomputation:

- `target_reg_distance_up_extreme_pct_v2`: rows=554,507, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_up_mean_high_pct_v2`: rows=554,507, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_mean_low_pct_v2`: rows=554,507, max_abs_error=0.000e+00, violations_gt_1e_12=0
- `target_reg_distance_down_extreme_pct_v2`: rows=554,507, max_abs_error=0.000e+00, violations_gt_1e_12=0

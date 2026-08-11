# Volatility-Normalized Distance Target Validation

Generated: 2026-06-04T07:49:00.922430+00:00

| Asset | Root | Status | Rows | Valid Rows | Unique Label Windows |
|---|---|---|---:|---:|---:|
| BTCUSDT | 8h/B | PASS | 2,810,755 | 1,405,427 | 5,856 |

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
- `direction_share_out_of_bounds`: 0
- `direction_share_nonfinite`: 0
- `target_reg_direction_extreme_up_share_hvol_v2_bad_share`: 0
- `target_reg_direction_mean_up_share_hvol_v2_bad_share`: 0
- `invalid_nonnull_direction_shares`: 0
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

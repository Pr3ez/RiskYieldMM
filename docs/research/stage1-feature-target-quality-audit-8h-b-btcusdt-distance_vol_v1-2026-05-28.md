# Stage-1 Feature And Regression Target Quality Audit

Generated: 2026-05-28T12:56:37.093725+00:00
Status: **PASS_WITH_WARNINGS**

## Scope

- Asset/root: `BTCUSDT 8h/B`
- Regression variant: `distance_vol_v1`
- Merged target column: `target_reg_distance_up_extreme_vol_v1`
- Feature rows seen: 923,240
- Feature columns: 1,162
- Source manifest: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset_merged/btcusdt/corexself/target_reg_distance_up_extreme_vol_v1/8h_b/manifest.json`
- Machine outputs: `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/test_output/stage1_feature_target_quality_audit/btcusdt_8h_b_distance_vol_v1`

## Important Target-Scale Warning

`distance_vol_v1` is arithmetically validated, but it normalizes a multi-hour future distance by a short-horizon volatility denominator. Large values can therefore be valid arithmetic while still being a poor modeling scale. This audit does not create or promote a corrected target.

## Manifest Snapshot

- Manifest output rows: 923240
- Manifest batches: 3942
- Manifest duplicate count: 0
- Manifest null feature count: 0

## Issues

| Severity | Category | Check | Detail |
|---|---|---|---|
| warning | feature | `duplicate_or_near_duplicate_feature_groups` | 32 |
| warning | feature | `extreme_feature_scale_count` | 6 |
| warning | feature | `near_constant_feature_count` | 78 |
| warning | target | `distance_vol_v1_scale_design` | distance_vol_v1 divides multi-hour future excursions by short-horizon prediction-time volatility; large normalized values can be arithmetically valid but poorly scaled. |
| warning | target | `large_target_max` | target_reg_distance_up_extreme_vol_v1 max=213.4226 |
| warning | target | `large_target_max` | target_reg_distance_up_mean_high_vol_v1 max=152.7920 |
| warning | target | `large_target_max` | target_reg_distance_down_mean_low_vol_v1 max=133.4804 |
| warning | target | `large_target_max` | target_reg_distance_down_extreme_vol_v1 max=383.5800 |
| warning | target | `large_target_p99` | target_reg_distance_up_extreme_vol_v1 p99=70.2133 |
| warning | target | `large_target_p99` | target_reg_distance_down_extreme_vol_v1 p99=69.4328 |

## Target Summary

| Target | Valid Rows | p50 | p95 | p99 | p999 | Max | Raw p99 | Vol p50 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `target_reg_distance_up_extreme_vol_v1` | 923,240 | 8.18121 | 40.8486 | 70.2133 | 131.298 | 213.423 | 0.0571384 | 0.00074651 |
| `target_reg_distance_up_mean_high_vol_v1` | 923,240 | 2.95515 | 23.2035 | 43.3993 | 79.2146 | 152.792 | 0.0376791 | 0.00074651 |
| `target_reg_distance_down_mean_low_vol_v1` | 923,240 | 2.85251 | 22.998 | 41.5646 | 83.758 | 133.48 | 0.040015 | 0.00074651 |
| `target_reg_distance_down_extreme_vol_v1` | 923,240 | 8.27409 | 41.0472 | 69.4328 | 139.063 | 383.58 | 0.0643657 | 0.00074651 |

## Feature Summary

- Constant features: 0
- Near-constant features: 78
- Duplicate/near-duplicate sample groups: 32
- Asset-role counts: `{'unprefixed': 1, 'T_BTCUSDT': 169, 'C_ETHUSDT': 170, 'C_EURUSD': 137, 'C_USDJPY': 137, 'C_GC': 137, 'C_CL': 137, 'C_ES': 137, 'C_NQ': 137}`
- Top feature families: `{'H': 328, 'M': 232, 'V': 216, 'N': 120, 'L': 106, 'C': 24, 'B': 24, 'D': 22, 'X': 20, 'F': 12, 'S': 10, 'bar': 8}`

Top feature quality issues:

- None

## Top Feature-Target Correlations

| Target | Feature | Pearson | Spearman sample | n |
|---|---|---:|---:|---:|
| `target_reg_distance_up_extreme_vol_v1` | `T_BTCUSDT__V_atrPct_med_pct` | -0.190962 | -0.291037 | 923240 |
| `target_reg_distance_up_extreme_vol_v1` | `T_BTCUSDT__V_atrPct_long_pct` | -0.190409 | -0.281906 | 923240 |
| `target_reg_distance_up_extreme_vol_v1` | `T_BTCUSDT__V_atrPct_short_pct` | -0.189395 | -0.28618 | 923240 |
| `target_reg_distance_up_extreme_vol_v1` | `T_BTCUSDT__V_returnStd_med_pct` | -0.183753 | -0.253665 | 923240 |
| `target_reg_distance_up_extreme_vol_v1` | `T_BTCUSDT__V_parkinson_med_pct` | -0.183056 | -0.280663 | 923240 |
| `target_reg_distance_up_extreme_vol_v1` | `C_ETHUSDT__V_atrPct_long_pct` | -0.182953 | -0.320599 | 923240 |
| `target_reg_distance_down_extreme_vol_v1` | `T_BTCUSDT__V_atrPct_short_pct` | -0.181717 | -0.0992751 | 923240 |
| `target_reg_distance_up_extreme_vol_v1` | `C_ETHUSDT__V_atrPct_med_pct` | -0.181591 | -0.324972 | 923240 |
| `target_reg_distance_up_extreme_vol_v1` | `T_BTCUSDT__V_garmanKlass_med_pct` | -0.180904 | -0.300976 | 923240 |
| `target_reg_distance_up_extreme_vol_v1` | `T_BTCUSDT__V_yangZhang_med_pct` | -0.180792 | -0.299432 | 923240 |
| `target_reg_distance_down_extreme_vol_v1` | `T_BTCUSDT__V_atrPct_med_pct` | -0.179677 | -0.101582 | 923240 |
| `target_reg_distance_down_extreme_vol_v1` | `T_BTCUSDT__V_atrPct_long_pct` | -0.178985 | -0.100392 | 923240 |
| `target_reg_distance_down_extreme_vol_v1` | `T_BTCUSDT__V_returnStd_med_pct` | -0.17805 | -0.144376 | 923240 |
| `target_reg_distance_up_extreme_vol_v1` | `C_ETHUSDT__V_atrPct_short_pct` | -0.177729 | -0.311721 | 923240 |
| `target_reg_distance_up_extreme_vol_v1` | `T_BTCUSDT__V_parkinson_short_pct` | -0.17686 | -0.26917 | 923240 |
| `target_reg_distance_up_extreme_vol_v1` | `T_BTCUSDT__V_garmanKlass_short_pct` | -0.175134 | -0.286839 | 923240 |
| `target_reg_distance_up_extreme_vol_v1` | `T_BTCUSDT__V_returnStd_long_pct` | -0.174881 | -0.20155 | 923240 |
| `target_reg_distance_down_extreme_vol_v1` | `T_BTCUSDT__V_returnStd_short_pct` | -0.174492 | -0.123663 | 923240 |
| `target_reg_distance_up_extreme_vol_v1` | `T_BTCUSDT__V_yangZhang_short_pct` | -0.174457 | -0.289131 | 923240 |
| `target_reg_distance_up_extreme_vol_v1` | `T_BTCUSDT__V_returnStd_short_pct` | -0.173894 | -0.240058 | 923240 |

## Output Tables

- `feature_quality.parquet`
- `target_quality.parquet`
- `feature_target_correlations.parquet`
- `correlation_stability.parquet`
- `duplicate_feature_groups.parquet`
- `issues.parquet`
- `audit_summary.json`

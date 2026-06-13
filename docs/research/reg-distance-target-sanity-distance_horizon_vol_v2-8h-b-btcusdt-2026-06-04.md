# Volatility-Normalized Distance Target Sanity

Generated: 2026-06-04T07:48:26.593975+00:00

These targets are label-only research artifacts. They are normalized by
prediction-time volatility and must not be joined as model features.

| Asset | Root | Rows | Eligible | Valid | Invalid Ratio | Output |
|---|---|---:|---:|---:|---:|---|
| BTCUSDT | 8h/B | 2,810,755 | 1,405,440 | 1,405,427 | 0.00% | `/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/data/htf_multiasset/btcusdt/htf_4class_labels_reg_distance_horizon_vol_v2/1m` |

## BTCUSDT 8h/B

Reason counts:

- `ok`: 1,405,427
- `invalid_volatility`: 13

Target quantiles:

| Column | P50 | P95 | P99 | Max | Mean |
|---|---:|---:|---:|---:|---:|
| `target_reg_distance_up_extreme_hvol_v2` | 0.499343 | 2.45142 | 4.27382 | 13.7764 | 0.755186 |
| `target_reg_distance_up_mean_high_hvol_v2` | 0.181165 | 1.39534 | 2.6682 | 9.86268 | 0.375435 |
| `target_reg_distance_down_mean_low_hvol_v2` | 0.163792 | 1.39524 | 2.55278 | 8.61612 | 0.367246 |
| `target_reg_distance_down_extreme_hvol_v2` | 0.493119 | 2.50905 | 4.28785 | 24.76 | 0.767795 |
| `target_reg_direction_extreme_up_share_hvol_v2` | 0.504104 | 1 | 1 | 1 | 0.504103 |
| `target_reg_direction_mean_up_share_hvol_v2` | 0.524098 | 1 | 1 | 1 | 0.50882 |

Prediction-time volatility:

- p50: 0.000679885
- p95: 0.00213155
- max: 0.0231088

Horizon-adjusted volatility:

- p50: 0.0105317
- p95: 0.0330218
- max: 0.358

# 1m/target_4class Directional Pattern Audit

- Run dir: `/media/przem/linux_data/RiskYieldMM (Copy)/prediction_analysis/multitimeframe_ensemble_outputs/20260225_173235_all6_3500_current_periodclose_nolive_ram`
- Batches: 3500 | Configs: 12 | Threshold: 0.70
- Mean directional accuracy across all config-batch points: 0.5076
- Mean opposite-direction rate across all config-batch points: 0.4924

## Top Configs By Mean Directional Accuracy

| action_key   |   directional_accuracy_mean |   opposite_rate_mean |   high_acc_share |   lag1_accuracy_autocorr |
|:-------------|----------------------------:|---------------------:|-----------------:|-------------------------:|
| f3_v2_t4     |                    0.513402 |             0.486598 |         0.286857 |               -0.0184745 |
| f2_v2_t4     |                    0.512954 |             0.487046 |         0.286571 |               -0.0177026 |
| f2_v1_t5     |                    0.509898 |             0.490102 |         0.288    |               -0.0153407 |
| f2_v1_t3     |                    0.509098 |             0.490902 |         0.299429 |               -0.0207792 |
| f3_v1_t3     |                    0.509096 |             0.490904 |         0.299429 |               -0.0207474 |
| f2_v2_t8     |                    0.508971 |             0.491029 |         0.266286 |               -0.0249883 |

## Drift (Last Segment - First Segment)

| action_key   |   acc_seg_first |   acc_seg_last |   acc_drift_last_minus_first |
|:-------------|----------------:|---------------:|-----------------------------:|
| f7_v1_t4     |        0.490131 |       0.530095 |                  0.0399643   |
| f2_v1_t4     |        0.490131 |       0.529976 |                  0.0398452   |
| f2_v2_t10    |        0.493607 |       0.515107 |                  0.0215      |
| f2_v1_t6     |        0.516917 |       0.533143 |                  0.0162262   |
| f2_v3_t9     |        0.505738 |       0.518036 |                  0.0122976   |
| f2_v2_t8     |        0.501333 |       0.513238 |                  0.0119048   |
| f2_v2_t6     |        0.509452 |       0.5155   |                  0.00604762  |
| f2_v1_t3     |        0.509429 |       0.51469  |                  0.0052619   |
| f3_v1_t3     |        0.509429 |       0.51469  |                  0.0052619   |
| f3_v2_t4     |        0.516155 |       0.519726 |                  0.00357143  |
| f2_v2_t4     |        0.516155 |       0.515238 |                 -0.000916667 |
| f2_v1_t5     |        0.527643 |       0.511655 |                 -0.0159881   |

## High-Accuracy Availability Per Batch

|   configs_ge_threshold |   batches |   batch_share |
|-----------------------:|----------:|--------------:|
|                      0 |       925 |     0.264286  |
|                      1 |       369 |     0.105429  |
|                      2 |       455 |     0.13      |
|                      3 |       337 |     0.0962857 |
|                      4 |       318 |     0.0908571 |
|                      5 |       257 |     0.0734286 |
|                      6 |       181 |     0.0517143 |
|                      7 |       180 |     0.0514286 |
|                      8 |       166 |     0.0474286 |
|                      9 |       103 |     0.0294286 |
|                     10 |        95 |     0.0271429 |
|                     11 |        63 |     0.018     |
|                     12 |        51 |     0.0145714 |

## Strongest Repeating High-Accuracy Lags

| action_key   |   lag |   corr_high_acc_indicator |
|:-------------|------:|--------------------------:|
| f2_v1_t4     |    30 |                 0.0568407 |
| f7_v1_t4     |    30 |                 0.0568407 |
| f2_v2_t10    |    27 |                 0.049494  |
| f2_v1_t5     |    26 |                 0.0472604 |
| f2_v1_t6     |    20 |                 0.0446136 |
| f2_v1_t3     |    22 |                 0.0431775 |

## Notes

- Repeating lags are descriptive diagnostics only; they are not direct trading signals.
- Any future config-selection policy must use only history `< t`.

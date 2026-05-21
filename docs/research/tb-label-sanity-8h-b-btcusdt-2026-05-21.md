# Triple-Barrier Label Sanity Report

Generated: 2026-05-21T12:36:53.710447+00:00

Acceptance gates are evaluated on label-eligible entry-window rows only: eligible invalid ratio <= 35%, same-bar both-hit ratio <= 10%, and each valid class share >= 5%. Non-entry rows remain `-1` by design and are filtered out by Stage-1 before training.

## Summary

| Asset | Root | Variant | Rows | Eligible | Valid Eligible | Eligible Invalid % | All-Row Invalid % | Same-Bar Both-Hit % | Model Ready | Reasons |
|---|---|---|---:|---:|---:|---:|---:|---:|---|---|
| BTCUSDT | 8h/B | tb_atr_v1 | 2,810,755 | 1,405,440 | 1,316,618 | 6.32% | 53.16% | 6.30% | no | class_share<5%:[0, 2] |
| BTCUSDT | 8h/B | tb_bollinger_v1 | 2,810,755 | 1,405,440 | 1,301,447 | 7.40% | 53.70% | 7.38% | no | class_share<5%:[0, 2] |
| BTCUSDT | 8h/B | tb_keltner_v1 | 2,810,755 | 1,405,440 | 1,301,318 | 7.41% | 53.70% | 7.39% | no | class_share<5%:[0, 2] |
| BTCUSDT | 8h/B | tb_atr_wide_v2 | 2,810,755 | 1,405,440 | 1,404,118 | 0.09% | 50.04% | 0.09% | yes | - |

## Class Share

### BTCUSDT 8h/B tb_atr_v1

| Class | Name | Share |
|---:|---|---:|
| 0 | DOWN_BALANCED | 0.02% |
| 1 | DOWN_EXPANSION | 50.82% |
| 2 | UP_BALANCED | 0.06% |
| 3 | UP_EXPANSION | 49.10% |

### BTCUSDT 8h/B tb_bollinger_v1

| Class | Name | Share |
|---:|---|---:|
| 0 | DOWN_BALANCED | 0.01% |
| 1 | DOWN_EXPANSION | 50.31% |
| 2 | UP_BALANCED | 0.05% |
| 3 | UP_EXPANSION | 49.63% |

### BTCUSDT 8h/B tb_keltner_v1

| Class | Name | Share |
|---:|---|---:|
| 0 | DOWN_BALANCED | 0.01% |
| 1 | DOWN_EXPANSION | 50.29% |
| 2 | UP_BALANCED | 0.05% |
| 3 | UP_EXPANSION | 49.64% |

### BTCUSDT 8h/B tb_atr_wide_v2

| Class | Name | Share |
|---:|---|---:|
| 0 | DOWN_BALANCED | 22.95% |
| 1 | DOWN_EXPANSION | 25.77% |
| 2 | UP_BALANCED | 26.25% |
| 3 | UP_EXPANSION | 25.02% |


## Class Diagnostics

### BTCUSDT 8h/B tb_atr_v1

| Class | Rows | Mean Terminal Return | Median Terminal Z | Mean MFE | Mean MAE | Median Hit Offset |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 243 | -0.001129 | -0.625828 | 0.002198 | -0.002222 | -1.000000 |
| 1 | 669,136 | - | - | 0.003043 | -0.014717 | 0.000000 |
| 2 | 797 | 0.001774 | 0.863796 | 0.002935 | -0.001674 | -1.000000 |
| 3 | 646,442 | - | - | 0.014414 | -0.002863 | 0.000000 |

Barrier distance quantiles:

| Metric | p05 | p50 | p95 |
|---|---:|---:|---:|
| tb_upper_distance_pct | 0.001000 | 0.001360 | 0.004263 |
| tb_lower_distance_pct | 0.000750 | 0.001020 | 0.003197 |

First-hit distribution:

both_same_bar=88,550, invalid=13, lower=669,136, terminal=1,299, upper=646,442

### BTCUSDT 8h/B tb_bollinger_v1

| Class | Rows | Mean Terminal Return | Median Terminal Z | Mean MFE | Mean MAE | Median Hit Offset |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 180 | -0.001202 | -0.634400 | 0.002218 | -0.002235 | -1.000000 |
| 1 | 654,713 | - | - | 0.002941 | -0.014793 | 0.000000 |
| 2 | 628 | 0.001565 | 0.856991 | 0.002503 | -0.001250 | -1.000000 |
| 3 | 645,926 | - | - | 0.014364 | -0.002864 | 0.000000 |

Barrier distance quantiles:

| Metric | p05 | p50 | p95 |
|---|---:|---:|---:|
| tb_upper_distance_pct | 0.000634 | 0.001166 | 0.003786 |
| tb_lower_distance_pct | 0.000634 | 0.000936 | 0.002949 |

First-hit distribution:

both_same_bar=103,787, invalid=13, lower=654,713, terminal=1,001, upper=645,926

### BTCUSDT 8h/B tb_keltner_v1

| Class | Rows | Mean Terminal Return | Median Terminal Z | Mean MFE | Mean MAE | Median Hit Offset |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 190 | -0.000856 | -0.639940 | 0.001422 | -0.001549 | -1.000000 |
| 1 | 654,465 | - | - | 0.002937 | -0.014788 | 0.000000 |
| 2 | 656 | 0.001569 | 0.863796 | 0.002473 | -0.001345 | -1.000000 |
| 3 | 646,007 | - | - | 0.014365 | -0.002869 | 0.000000 |

Barrier distance quantiles:

| Metric | p05 | p50 | p95 |
|---|---:|---:|---:|
| tb_upper_distance_pct | 0.000633 | 0.001162 | 0.003777 |
| tb_lower_distance_pct | 0.000636 | 0.000937 | 0.002952 |

First-hit distribution:

both_same_bar=103,915, invalid=13, lower=654,465, terminal=1,040, upper=646,007

### BTCUSDT 8h/B tb_atr_wide_v2

| Class | Rows | Mean Terminal Return | Median Terminal Z | Mean MFE | Mean MAE | Median Hit Offset |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 322,284 | -0.004197 | -3.781699 | 0.003201 | -0.008297 | -1.000000 |
| 1 | 361,897 | - | - | 0.000574 | -0.023723 | 5.000000 |
| 2 | 368,580 | 0.004613 | 3.964694 | 0.008509 | -0.003177 | -1.000000 |
| 3 | 351,357 | - | - | 0.022656 | -0.000616 | 5.000000 |

Barrier distance quantiles:

| Metric | p05 | p50 | p95 |
|---|---:|---:|---:|
| tb_upper_distance_pct | 0.007500 | 0.010198 | 0.031973 |
| tb_lower_distance_pct | 0.007500 | 0.010198 | 0.031973 |

First-hit distribution:

both_same_bar=1,309, invalid=13, lower=361,897, terminal=690,864, upper=351,357

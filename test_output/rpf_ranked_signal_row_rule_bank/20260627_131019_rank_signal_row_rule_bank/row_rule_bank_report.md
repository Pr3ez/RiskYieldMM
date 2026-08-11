# RPF Ranked Signal Row Rule Bank

## Scope

- row diagnostic run: `test_output/rpf_ranked_signal_row_diagnostic/20260627_125952_rank_signal_row_diagnostic`
- blocks: `offset420, offset360, offset300, offset240, offset180, middle, offset60, latest`
- folds: `7`
- eligible rules: `6`

## Fold Summary

| Fold | Train | Test | Side | Candidate | Signals | TP | FP | Precision | FDR |
|---:|---|---|---|---|---:|---:|---:|---:|---:|
| 1 | offset360 | offset300 | down | down_rocket_16_diag_v1 | 3 | 3 | 0 | 1 | 0 |
| 2 | offset300 | offset240 | down | down_rocket_16_diag_v1 | 22 | 11 | 11 | 0.5 | 0.5 |
| 3 | offset240 | offset180 | down | down_rocket_16_diag_v1 | 6 | 3 | 3 | 0.5 | 0.5 |
| 4 | offset180 | middle | down | down_rocket_16_diag_v1 | 42 | 24 | 18 | 0.571429 | 0.428571 |
| 5 | middle | offset60 | down | down_rocket_16_diag_v1 | 21 | 15 | 6 | 0.714286 | 0.285714 |
| 6 | offset60 | latest | down | down_rocket_16_diag_v1 | 22 | 10 | 12 | 0.454545 | 0.545455 |

## Fold Raw Comparison

| Fold | Test | Side | Candidate | Filtered Signals | Filtered Precision | Raw Signals | Raw Precision | Precision Lift | Signal Retention |
|---:|---|---|---|---:|---:|---:|---:|---:|---:|
| 1 | offset300 | down | down_rocket_16_diag_v1 | 3 | 1 | 93 | 0.516129 | 1.9375 | 0.0322581 |
| 2 | offset240 | down | down_rocket_16_diag_v1 | 22 | 0.5 | 107 | 0.439252 | 1.1383 | 0.205607 |
| 3 | offset180 | down | down_rocket_16_diag_v1 | 6 | 0.5 | 106 | 0.54717 | 0.913793 | 0.0566038 |
| 4 | middle | down | down_rocket_16_diag_v1 | 42 | 0.571429 | 102 | 0.441176 | 1.29524 | 0.411765 |
| 5 | offset60 | down | down_rocket_16_diag_v1 | 21 | 0.714286 | 80 | 0.375 | 1.90476 | 0.2625 |
| 6 | latest | down | down_rocket_16_diag_v1 | 22 | 0.454545 | 92 | 0.413043 | 1.10048 | 0.23913 |

## Overall Summary

| Side | Candidate | Signals | TP | FP | Precision | FDR |
|---|---|---:|---:|---:|---:|---:|
| down | down_rocket_16_diag_v1 | 116 | 66 | 50 | 0.568966 | 0.431034 |

## Overall Raw Comparison

| Side | Candidate | Filtered Signals | Filtered Precision | Raw Signals | Raw Precision | Precision Lift | Signal Retention |
|---|---|---:|---:|---:|---:|---:|---:|
| down | down_rocket_16_diag_v1 | 116 | 0.568966 | 580 | 0.458621 | 1.2406 | 0.2 |

## Interpretation Rules

- Rules are trained on prior matured signal rows only.
- Replayed rows are next-block signal rows accepted by at least one eligible filter.
- This is still diagnostic evidence; it does not modify router decisions.

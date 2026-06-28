# RPF Ranked Signal Row Rule Bank

## Scope

- row diagnostic run: `test_output/rpf_ranked_signal_row_diagnostic/20260627_125952_rank_signal_row_diagnostic`
- blocks: `offset420, offset360, offset300, offset240, offset180, middle, offset60, latest`
- folds: `7`
- eligible rules: `5`

## Fold Summary

| Fold | Train | Test | Side | Candidate | Signals | TP | FP | Precision | FDR |
|---:|---|---|---|---|---:|---:|---:|---:|---:|
| 2 | offset300 | offset240 | down | down_rocket_16_diag_v1 | 24 | 15 | 9 | 0.625 | 0.375 |
| 3 | offset240 | offset180 | down | down_rocket_16_diag_v1 | 8 | 5 | 3 | 0.625 | 0.375 |
| 4 | offset180 | middle | down | down_rocket_16_diag_v1 | 11 | 8 | 3 | 0.727273 | 0.272727 |
| 5 | middle | offset60 | down | down_rocket_16_diag_v1 | 4 | 2 | 2 | 0.5 | 0.5 |
| 6 | offset60 | latest | down | down_rocket_16_diag_v1 | 22 | 10 | 12 | 0.454545 | 0.545455 |

## Fold Raw Comparison

| Fold | Test | Side | Candidate | Filtered Signals | Filtered Precision | Raw Signals | Raw Precision | Precision Lift | Signal Retention |
|---:|---|---|---|---:|---:|---:|---:|---:|---:|
| 2 | offset240 | down | down_rocket_16_diag_v1 | 24 | 0.625 | 107 | 0.439252 | 1.42287 | 0.224299 |
| 3 | offset180 | down | down_rocket_16_diag_v1 | 8 | 0.625 | 106 | 0.54717 | 1.14224 | 0.0754717 |
| 4 | middle | down | down_rocket_16_diag_v1 | 11 | 0.727273 | 102 | 0.441176 | 1.64848 | 0.107843 |
| 5 | offset60 | down | down_rocket_16_diag_v1 | 4 | 0.5 | 80 | 0.375 | 1.33333 | 0.05 |
| 6 | latest | down | down_rocket_16_diag_v1 | 22 | 0.454545 | 92 | 0.413043 | 1.10048 | 0.23913 |

## Overall Summary

| Side | Candidate | Signals | TP | FP | Precision | FDR |
|---|---|---:|---:|---:|---:|---:|
| down | down_rocket_16_diag_v1 | 69 | 40 | 29 | 0.57971 | 0.42029 |

## Overall Raw Comparison

| Side | Candidate | Filtered Signals | Filtered Precision | Raw Signals | Raw Precision | Precision Lift | Signal Retention |
|---|---|---:|---:|---:|---:|---:|---:|
| down | down_rocket_16_diag_v1 | 69 | 0.57971 | 487 | 0.447639 | 1.29504 | 0.141684 |

## Interpretation Rules

- Rules are trained on prior matured signal rows only.
- Replayed rows are next-block signal rows accepted by at least one eligible filter.
- This is still diagnostic evidence; it does not modify router decisions.

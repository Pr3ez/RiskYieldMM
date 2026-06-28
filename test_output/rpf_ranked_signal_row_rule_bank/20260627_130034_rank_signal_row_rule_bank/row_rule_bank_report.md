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

## Overall Summary

| Side | Candidate | Signals | TP | FP | Precision | FDR |
|---|---|---:|---:|---:|---:|---:|
| down | down_rocket_16_diag_v1 | 116 | 66 | 50 | 0.568966 | 0.431034 |

## Interpretation Rules

- Rules are trained on prior matured signal rows only.
- Replayed rows are next-block signal rows accepted by at least one eligible filter.
- This is still diagnostic evidence; it does not modify router decisions.

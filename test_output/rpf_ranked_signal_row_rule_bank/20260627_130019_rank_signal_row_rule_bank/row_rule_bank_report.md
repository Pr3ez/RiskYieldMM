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

## Overall Summary

| Side | Candidate | Signals | TP | FP | Precision | FDR |
|---|---|---:|---:|---:|---:|---:|
| down | down_rocket_16_diag_v1 | 69 | 40 | 29 | 0.57971 | 0.42029 |

## Interpretation Rules

- Rules are trained on prior matured signal rows only.
- Replayed rows are next-block signal rows accepted by at least one eligible filter.
- This is still diagnostic evidence; it does not modify router decisions.

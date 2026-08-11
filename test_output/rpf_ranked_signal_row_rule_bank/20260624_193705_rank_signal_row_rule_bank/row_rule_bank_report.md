# RPF Ranked Signal Row Rule Bank

## Scope

- row diagnostic run: `test_output/rpf_ranked_signal_row_diagnostic/20260624_193124_rank_signal_row_diagnostic`
- blocks: `offset240, middle, latest`
- folds: `2`
- eligible rules: `2`

## Fold Summary

| Fold | Train | Test | Side | Candidate | Signals | TP | FP | Precision | FDR |
|---:|---|---|---|---|---:|---:|---:|---:|---:|
| 0 | offset240 | middle | down | down_rocket_16_diag_v1 | 21 | 13 | 8 | 0.619048 | 0.380952 |
| 1 | middle | latest | down | down_rocket_16_diag_v1 | 9 | 6 | 3 | 0.666667 | 0.333333 |

## Overall Summary

| Side | Candidate | Signals | TP | FP | Precision | FDR |
|---|---|---:|---:|---:|---:|---:|
| down | down_rocket_16_diag_v1 | 30 | 19 | 11 | 0.633333 | 0.366667 |

## Interpretation Rules

- Rules are trained on prior matured signal rows only.
- Replayed rows are next-block signal rows accepted by at least one eligible filter.
- This is still diagnostic evidence; it does not modify router decisions.

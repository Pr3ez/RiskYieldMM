# RPF Ranked Signal Row Rule Bank

## Scope

- row diagnostic run: `test_output/rpf_ranked_signal_row_diagnostic/20260624_233918_rank_signal_row_diagnostic`
- blocks: `offset360, offset240, middle, latest`
- folds: `3`
- eligible rules: `3`

## Fold Summary

| Fold | Train | Test | Side | Candidate | Signals | TP | FP | Precision | FDR |
|---:|---|---|---|---|---:|---:|---:|---:|---:|
| 0 | offset360 | offset240 | down | down_rocket_16_diag_v1 | 39 | 20 | 19 | 0.512821 | 0.487179 |
| 1 | offset240 | middle | down | down_rocket_16_diag_v1 | 53 | 35 | 18 | 0.660377 | 0.339623 |
| 2 | middle | latest | down | down_rocket_16_diag_v1 | 49 | 14 | 35 | 0.285714 | 0.714286 |

## Overall Summary

| Side | Candidate | Signals | TP | FP | Precision | FDR |
|---|---|---:|---:|---:|---:|---:|
| down | down_rocket_16_diag_v1 | 141 | 69 | 72 | 0.489362 | 0.510638 |

## Interpretation Rules

- Rules are trained on prior matured signal rows only.
- Replayed rows are next-block signal rows accepted by at least one eligible filter.
- This is still diagnostic evidence; it does not modify router decisions.

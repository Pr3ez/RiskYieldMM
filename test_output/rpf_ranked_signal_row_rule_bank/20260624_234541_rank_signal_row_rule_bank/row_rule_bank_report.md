# RPF Ranked Signal Row Rule Bank

## Scope

- row diagnostic run: `test_output/rpf_ranked_signal_row_diagnostic/20260624_233918_rank_signal_row_diagnostic`
- blocks: `offset360, offset240, middle, latest`
- folds: `3`
- eligible rules: `32`

## Fold Summary

| Fold | Train | Test | Side | Candidate | Signals | TP | FP | Precision | FDR |
|---:|---|---|---|---|---:|---:|---:|---:|---:|
| 0 | offset360 | offset240 | down | down_rocket_16_diag_v1 | 39 | 20 | 19 | 0.512821 | 0.487179 |
| 1 | offset240 | middle | down | down_rocket_16_diag_v1 | 124 | 66 | 58 | 0.532258 | 0.467742 |
| 2 | middle | latest | down | down_rocket_16_diag_v1 | 148 | 60 | 88 | 0.405405 | 0.594595 |

## Overall Summary

| Side | Candidate | Signals | TP | FP | Precision | FDR |
|---|---|---:|---:|---:|---:|---:|
| down | down_rocket_16_diag_v1 | 311 | 146 | 165 | 0.469453 | 0.530547 |

## Interpretation Rules

- Rules are trained on prior matured signal rows only.
- Replayed rows are next-block signal rows accepted by at least one eligible filter.
- This is still diagnostic evidence; it does not modify router decisions.

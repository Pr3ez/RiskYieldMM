# RPF Ranked Signal Row Rule Bank

## Scope

- row diagnostic run: `test_output/rpf_ranked_signal_row_diagnostic/20260624_193124_rank_signal_row_diagnostic`
- blocks: `offset240, middle, latest`
- folds: `2`
- eligible rules: `41`

## Fold Summary

| Fold | Train | Test | Side | Candidate | Signals | TP | FP | Precision | FDR |
|---:|---|---|---|---|---:|---:|---:|---:|---:|
| 0 | offset240 | middle | down | down_rocket_16_diag_v1 | 64 | 35 | 29 | 0.546875 | 0.453125 |
| 1 | middle | latest | down | down_rocket_16_diag_v1 | 69 | 26 | 43 | 0.376812 | 0.623188 |

## Overall Summary

| Side | Candidate | Signals | TP | FP | Precision | FDR |
|---|---|---:|---:|---:|---:|---:|
| down | down_rocket_16_diag_v1 | 133 | 61 | 72 | 0.458647 | 0.541353 |

## Interpretation Rules

- Rules are trained on prior matured signal rows only.
- Replayed rows are next-block signal rows accepted by at least one eligible filter.
- This is still diagnostic evidence; it does not modify router decisions.

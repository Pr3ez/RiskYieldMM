# RPF Ranked Signal Meta-Router Simulator

## Scope

- diagnostic run: `test_output/rpf_ranked_signal_transfer_diagnostic/20260623_183857_rank_signal_transfer_diagnostic`
- train source block: `older`
- test source block: `latest`
- trained candidate rules: `4`

## Rules

| Side | Candidate | Feature | Direction | Threshold | Train Signals | Train Precision | Train Lift |
|---|---|---|---|---:|---:|---:|---:|
| down | down_none_v1 | `reliability_reliability_score` | lower_good | -1.34539 | 5 | 1 | 3.24094 |
| down | down_rocket_16_diag_v1 | `reliability_selected_window_row_lift` | lower_good | 0.969697 | 3 | 1 | 4.89796 |
| up | up_none_v1 | `threshold` | higher_good | 0.0215847 | 3 | 1 | 2.75269 |
| up | up_rocket_64_v1 | `score_mean` | lower_good | -0.00188434 | 6 | 1 | 1.99511 |

## Candidate Acceptance Summary

| Source | Side | Candidate | Windows | Signals | TP | FP | Precision | Base Rate | Lift | FDR |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| latest | down | down_none_v1 | 89 | 38 | 9 | 29 | 0.236842 | 0.322004 | 0.735526 | 0.763158 |
| latest | down | down_rocket_16_diag_v1 | 2 | 2 | 2 | 0 | 1 | 0.295833 | 3.38028 | 0 |
| latest | up | up_none_v1 | 3 | 0 | 0 | 0 | - | 0.522222 | - | - |
| latest | up | up_rocket_64_v1 | 20 | 3 | 3 | 0 | 1 | 0.582083 | 1.71797 | 0 |
| older | down | down_none_v1 | 19 | 5 | 5 | 0 | 1 | 0.308553 | 3.24094 | 0 |
| older | down | down_rocket_16_diag_v1 | 4 | 3 | 3 | 0 | 1 | 0.204167 | 4.89796 | 0 |
| older | up | up_none_v1 | 16 | 3 | 3 | 0 | 1 | 0.363281 | 2.75269 | 0 |
| older | up | up_rocket_64_v1 | 17 | 6 | 6 | 0 | 1 | 0.501225 | 1.99511 | 0 |

## Side Router Summary

| Source | Side | Candidate | Windows | Signals | TP | FP | Precision | Base Rate | Lift | FDR |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| latest | down | selected_side_router | 120 | 38 | 9 | 29 | 0.236842 | 0.333333 | 0.710526 | 0.763158 |
| latest | up | selected_side_router | 120 | 3 | 3 | 0 | 1 | 0.429896 | 2.32614 | 0 |
| older | down | selected_side_router | 120 | 8 | 8 | 0 | 1 | 0.417257 | 2.3966 | 0 |
| older | up | selected_side_router | 120 | 9 | 9 | 0 | 1 | 0.362222 | 2.76074 | 0 |

## Interpretation

- This is an offline dry-run only.
- Rules are fit on the configured train source block and replayed on other blocks.
- Current prediction labels are used only for matured outcome scoring, never for fitting test-block rules.

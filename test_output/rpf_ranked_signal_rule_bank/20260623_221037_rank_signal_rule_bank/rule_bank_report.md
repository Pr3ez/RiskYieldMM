# RPF Ranked Signal Rule Bank

## Purpose

Train context rules on prior matured router blocks and replay them on the next chronological block.

## Input Blocks

| Order | Block | Run |
|---:|---|---|
| 0 | `offset240` | `test_output/rpf_ranked_signal_router/20260623_214859_rank_signal_router_btcusdt_8h_b` |
| 1 | `middle` | `test_output/rpf_ranked_signal_router/20260623_174040_rank_signal_router_btcusdt_8h_b` |
| 2 | `latest` | `test_output/rpf_ranked_signal_router/20260623_213215_rank_signal_router_btcusdt_8h_b` |

## Forward Folds

| Fold | Train Blocks | Test Block |
|---:|---|---|
| 0 | `offset240` | `middle` |
| 1 | `middle` | `latest` |

## Rules

| Fold | Side | Candidate | Feature | Direction | Threshold | Train Signals | Train Precision | Train Lift |
|---:|---|---|---|---|---:|---:|---:|---:|
| 0 | down | down_rocket_16_diag_v1 | `score_mean` | lower_good | -0.00596586 | 18 | 0.888889 | 1.51689 |
| 0 | up | up_none_v1 | `current_validation_signal_rate` | higher_good | 0.00791667 | 39 | 0.487179 | 1.7783 |
| 0 | up | up_rocket_64_v1 | `score_mean` | lower_good | -0.00133522 | 32 | 0.625 | 1.28425 |
| 1 | down | down_rocket_16_diag_v1 | `reliability_selected_window_row_lift` | lower_good | 0.969697 | 3 | 1 | 4.89796 |
| 1 | up | up_none_v1 | `threshold` | higher_good | 0.0215847 | 3 | 1 | 2.75269 |
| 1 | up | up_rocket_64_v1 | `score_mean` | lower_good | -0.00188434 | 6 | 1 | 1.99511 |

## Fold Side Summary

| Fold | Test Block | Side | Signals | TP | FP | Precision | Base Rate | Lift | FDR | Active Rate |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | middle | down | 6 | 3 | 3 | 0.5 | 0.417257 | 1.1983 | 0.5 | 0.0166667 |
| 0 | middle | up | 10 | 8 | 2 | 0.8 | 0.362222 | 2.20859 | 0.2 | 0.0416667 |
| 1 | latest | down | 9 | 6 | 3 | 0.666667 | 0.333333 | 2 | 0.333333 | 0.025 |
| 1 | latest | up | 17 | 14 | 3 | 0.823529 | 0.429896 | 1.91565 | 0.176471 | 0.0833333 |

## Overall Side Summary

| Side | Signals | TP | FP | Precision | Base Rate | Lift | FDR | Active Rate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| down | 15 | 9 | 6 | 0.6 | 0.375295 | 1.59874 | 0.4 | 0.0208333 |
| up | 27 | 22 | 5 | 0.814815 | 0.396059 | 2.05731 | 0.185185 | 0.0625 |

## Interpretation

- This is an offline diagnostic only.
- Each fold trains rules from prior matured blocks only.
- Current test-block labels are used only for post-hoc scoring.
- Rules that fail forward blocks should not be wired into the live router.

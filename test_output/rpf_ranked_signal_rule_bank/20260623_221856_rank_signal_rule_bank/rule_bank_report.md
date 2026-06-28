# RPF Ranked Signal Rule Bank

## Purpose

Train context rules on prior matured router blocks and replay them on the next chronological block.

## Input Blocks

| Order | Block | Run |
|---:|---|---|
| 0 | `offset360` | `test_output/rpf_ranked_signal_router/20260623_221301_rank_signal_router_btcusdt_8h_b` |
| 1 | `offset240` | `test_output/rpf_ranked_signal_router/20260623_214859_rank_signal_router_btcusdt_8h_b` |
| 2 | `middle` | `test_output/rpf_ranked_signal_router/20260623_174040_rank_signal_router_btcusdt_8h_b` |
| 3 | `latest` | `test_output/rpf_ranked_signal_router/20260623_213215_rank_signal_router_btcusdt_8h_b` |

## Forward Folds

| Fold | Train Blocks | Test Block |
|---:|---|---|
| 0 | `offset360` | `offset240` |
| 1 | `offset240` | `middle` |
| 2 | `middle` | `latest` |

## Rules

| Fold | Side | Candidate | Feature | Direction | Threshold | Train Signals | Train Precision | Train Lift |
|---:|---|---|---|---|---:|---:|---:|---:|
| 0 | down | down_rocket_16_diag_v1 | `current_validation_positive_rate` | lower_good | 0.2575 | 3 | 1 | 2.29117 |
| 0 | up | up_rocket_64_v1 | `score_mean` | lower_good | -0.00277446 | 3 | 1 | 3.20856 |
| 1 | down | down_rocket_16_diag_v1 | `score_mean` | lower_good | -0.00596586 | 18 | 0.888889 | 1.51689 |
| 1 | up | up_none_v1 | `current_validation_signal_rate` | higher_good | 0.00791667 | 39 | 0.487179 | 1.7783 |
| 1 | up | up_rocket_64_v1 | `score_mean` | lower_good | -0.00133522 | 32 | 0.625 | 1.28425 |
| 2 | down | down_rocket_16_diag_v1 | `reliability_selected_window_row_lift` | lower_good | 0.969697 | 3 | 1 | 4.89796 |
| 2 | up | up_none_v1 | `threshold` | higher_good | 0.0215847 | 3 | 1 | 2.75269 |
| 2 | up | up_rocket_64_v1 | `score_mean` | lower_good | -0.00188434 | 6 | 1 | 1.99511 |

## Fold Side Summary

| Fold | Test Block | Side | Signals | TP | FP | Precision | Base Rate | Lift | FDR | Active Rate |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | offset240 | down | 12 | 12 | 0 | 1 | 0.456076 | 2.19262 | 0 | 0.0333333 |
| 0 | offset240 | up | 8 | 4 | 4 | 0.5 | 0.312674 | 1.59911 | 0.5 | 0.0333333 |
| 1 | middle | down | 6 | 3 | 3 | 0.5 | 0.417257 | 1.1983 | 0.5 | 0.0166667 |
| 1 | middle | up | 10 | 8 | 2 | 0.8 | 0.362222 | 2.20859 | 0.2 | 0.0416667 |
| 2 | latest | down | 9 | 6 | 3 | 0.666667 | 0.333333 | 2 | 0.333333 | 0.025 |
| 2 | latest | up | 17 | 14 | 3 | 0.823529 | 0.429896 | 1.91565 | 0.176471 | 0.0833333 |

## Overall Side Summary

| Side | Signals | TP | FP | Precision | Base Rate | Lift | FDR | Active Rate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| down | 27 | 21 | 6 | 0.777778 | 0.402222 | 1.9337 | 0.222222 | 0.025 |
| up | 35 | 26 | 9 | 0.742857 | 0.368264 | 2.01719 | 0.257143 | 0.0527778 |

## Interpretation

- This is an offline diagnostic only.
- Each fold trains rules from prior matured blocks only.
- Current test-block labels are used only for post-hoc scoring.
- Rules that fail forward blocks should not be wired into the live router.

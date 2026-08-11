# RPF Ranked Signal Rule Bank

## Purpose

Train context rules on prior matured router blocks and replay them on the next chronological block.

## Input Blocks

| Order | Block | Run |
|---:|---|---|
| 0 | `offset360` | `test_output/rpf_ranked_signal_router/20260623_222640_rank_signal_router_btcusdt_8h_b` |
| 1 | `offset240` | `test_output/rpf_ranked_signal_router/20260623_224001_rank_signal_router_btcusdt_8h_b` |
| 2 | `middle` | `test_output/rpf_ranked_signal_router/20260623_225326_rank_signal_router_btcusdt_8h_b` |
| 3 | `latest` | `test_output/rpf_ranked_signal_router/20260623_230650_rank_signal_router_btcusdt_8h_b` |

## Forward Folds

| Fold | Train Blocks | Test Block |
|---:|---|---|
| 0 | `offset360` | `offset240` |
| 1 | `offset240` | `middle` |
| 2 | `middle` | `latest` |

## Rules

| Fold | Side | Candidate | Feature | Direction | Threshold | Train Signals | Train Precision | Train Lift |
|---:|---|---|---|---|---:|---:|---:|---:|
| 0 | down | down_rocket_16_diag_v1 | `past_20_batch_positive_rate_mean` | lower_good | 0.352292 | 51 | 0.588235 | 1.33944 |
| 0 | up | up_none_v1 | `score_std` | higher_good | 0.00838042 | 6 | 0.833333 | 3.2345 |
| 0 | up | up_rocket_64_v1 | `score_mean` | lower_good | -0.00277446 | 4 | 1 | 3.97516 |
| 1 | down | down_rocket_16_diag_v1 | `score_mean` | lower_good | -0.00596586 | 18 | 0.888889 | 1.51689 |
| 1 | up | up_none_v1 | `current_validation_signal_rate` | higher_good | 0.00791667 | 39 | 0.487179 | 1.7783 |
| 1 | up | up_rocket_64_v1 | `score_mean` | lower_good | -0.00133522 | 32 | 0.625 | 1.28425 |
| 2 | down | down_rocket_16_diag_v1 | `reliability_selected_window_row_lift` | lower_good | 1.12004 | 6 | 0.833333 | 2.00501 |
| 2 | up | up_none_v1 | `past_60_batch_positive_rate_std` | higher_good | 0.408929 | 3 | 1 | 5.52995 |
| 2 | up | up_rocket_64_v1 | `score_mean` | lower_good | 2.56714e-05 | 52 | 0.711538 | 1.54149 |

## Fold Side Summary

| Fold | Test Block | Side | Signals | TP | FP | Precision | Base Rate | Lift | FDR | Active Rate |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | offset240 | down | 9 | 4 | 5 | 0.444444 | 0.456076 | 0.974496 | 0.555556 | 0.025 |
| 0 | offset240 | up | 23 | 10 | 13 | 0.434783 | 0.312674 | 1.39053 | 0.565217 | 0.075 |
| 1 | middle | down | 31 | 22 | 9 | 0.709677 | 0.417257 | 1.70082 | 0.290323 | 0.0916667 |
| 1 | middle | up | 49 | 20 | 29 | 0.408163 | 0.362222 | 1.12683 | 0.591837 | 0.175 |
| 2 | latest | down | 53 | 23 | 30 | 0.433962 | 0.333333 | 1.30189 | 0.566038 | 0.15 |
| 2 | latest | up | 58 | 41 | 17 | 0.706897 | 0.429896 | 1.64434 | 0.293103 | 0.258333 |

## Overall Side Summary

| Side | Signals | TP | FP | Precision | Base Rate | Lift | FDR | Active Rate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| down | 93 | 49 | 44 | 0.526882 | 0.402222 | 1.30993 | 0.473118 | 0.0888889 |
| up | 130 | 71 | 59 | 0.546154 | 0.368264 | 1.48305 | 0.453846 | 0.169444 |

## Interpretation

- This is an offline diagnostic only.
- Each fold trains rules from prior matured blocks only.
- Current test-block labels are used only for post-hoc scoring.
- Rules that fail forward blocks should not be wired into the live router.

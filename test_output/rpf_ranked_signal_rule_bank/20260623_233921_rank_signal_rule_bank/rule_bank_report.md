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

| Fold | Side | Candidate | Feature | Direction | Threshold | Train Signals | Train Precision | Train Precision LCB | Train Lift | Train FDR | Active Rate |
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| 0 | up | up_none_v1 | `score_std` | higher_good | 0.00838042 | 6 | 0.833333 | 0.637024 | 3.2345 | 0.166667 | 0.05 |
| 0 | up | up_rocket_64_v1 | `score_mean` | lower_good | -0.00277446 | 4 | 1 | 0.8 | 3.97516 | 0 | 0.0666667 |
| 1 | down | down_rocket_16_diag_v1 | `score_mean` | lower_good | -0.00596586 | 18 | 0.888889 | 0.793474 | 1.51689 | 0.111111 | 0.3 |
| 2 | up | up_none_v1 | `past_60_batch_positive_rate_std` | higher_good | 0.408929 | 3 | 1 | 0.75 | 5.52995 | 0 | 0.0416667 |
| 2 | up | up_rocket_64_v1 | `score_mean` | lower_good | 2.56714e-05 | 52 | 0.711538 | 0.645189 | 1.54149 | 0.288462 | 0.458333 |

## Fold Side Summary

| Fold | Test Block | Side | Signals | TP | FP | Precision | Base Rate | Lift | FDR | Active Rate |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | offset240 | down | 0 | 0 | 0 | - | 0.456076 | - | - | 0 |
| 0 | offset240 | up | 23 | 10 | 13 | 0.434783 | 0.312674 | 1.39053 | 0.565217 | 0.075 |
| 1 | middle | down | 31 | 22 | 9 | 0.709677 | 0.417257 | 1.70082 | 0.290323 | 0.0916667 |
| 1 | middle | up | 0 | 0 | 0 | - | 0.362222 | - | - | 0 |
| 2 | latest | down | 0 | 0 | 0 | - | 0.333333 | - | - | 0 |
| 2 | latest | up | 58 | 41 | 17 | 0.706897 | 0.429896 | 1.64434 | 0.293103 | 0.258333 |

## Overall Side Summary

| Side | Signals | TP | FP | Precision | Base Rate | Lift | FDR | Active Rate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| down | 31 | 22 | 9 | 0.709677 | 0.402222 | 1.76439 | 0.290323 | 0.0305556 |
| up | 81 | 51 | 30 | 0.62963 | 0.368264 | 1.70972 | 0.37037 | 0.111111 |

## Interpretation

- This is an offline diagnostic only.
- Each fold trains rules from prior matured blocks only.
- Current test-block labels are used only for post-hoc scoring.
- Rules that fail forward blocks should not be wired into the live router.

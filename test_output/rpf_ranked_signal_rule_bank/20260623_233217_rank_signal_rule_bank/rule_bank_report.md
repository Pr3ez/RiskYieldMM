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
| 1 | down | down_rocket_16_diag_v1 | `score_mean` | lower_good | -0.00596586 | 18 | 0.888889 | 0.793474 | 1.51689 | 0.111111 | 0.3 |
| 2 | down | down_rocket_16_diag_v1 | `reliability_selected_window_row_lift` | lower_good | 1.12004 | 6 | 0.833333 | 0.637024 | 2.00501 | 0.166667 | 0.0333333 |
| 2 | up | up_rocket_64_v1 | `score_mean` | lower_good | 2.56714e-05 | 52 | 0.711538 | 0.645189 | 1.54149 | 0.288462 | 0.458333 |

## Fold Side Summary

| Fold | Test Block | Side | Signals | TP | FP | Precision | Base Rate | Lift | FDR | Active Rate |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | offset240 | down | 0 | 0 | 0 | - | 0.456076 | - | - | 0 |
| 0 | offset240 | up | 15 | 6 | 9 | 0.4 | 0.312674 | 1.27929 | 0.6 | 0.0416667 |
| 1 | middle | down | 31 | 22 | 9 | 0.709677 | 0.417257 | 1.70082 | 0.290323 | 0.0916667 |
| 1 | middle | up | 0 | 0 | 0 | - | 0.362222 | - | - | 0 |
| 2 | latest | down | 53 | 23 | 30 | 0.433962 | 0.333333 | 1.30189 | 0.566038 | 0.15 |
| 2 | latest | up | 57 | 38 | 19 | 0.666667 | 0.429896 | 1.55076 | 0.333333 | 0.258333 |

## Overall Side Summary

| Side | Signals | TP | FP | Precision | Base Rate | Lift | FDR | Active Rate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| down | 84 | 45 | 39 | 0.535714 | 0.402222 | 1.33189 | 0.464286 | 0.0805556 |
| up | 72 | 44 | 28 | 0.611111 | 0.368264 | 1.65944 | 0.388889 | 0.1 |

## Interpretation

- This is an offline diagnostic only.
- Each fold trains rules from prior matured blocks only.
- Current test-block labels are used only for post-hoc scoring.
- Rules that fail forward blocks should not be wired into the live router.

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
| 1 | `offset240, middle` | `latest` |

## Rules

| Fold | Side | Candidate | Feature | Direction | Threshold | Train Signals | Train Precision | Train Lift |
|---:|---|---|---|---|---:|---:|---:|---:|
| 0 | down | down_rocket_16_diag_v1 | `score_mean` | lower_good | -0.00596586 | 18 | 0.888889 | 1.51689 |
| 0 | up | up_none_v1 | `current_validation_signal_rate` | higher_good | 0.00791667 | 39 | 0.487179 | 1.7783 |
| 0 | up | up_rocket_64_v1 | `score_mean` | lower_good | -0.00133522 | 32 | 0.625 | 1.28425 |
| 1 | down | down_rocket_16_diag_v1 | `batch_state_gate_probability` | lower_good | 0.753455 | 3 | 1 | 2.29299 |
| 1 | up | up_none_v1 | `reliability_base_rate` | higher_good | 0.378299 | 3 | 1 | 5.49618 |
| 1 | up | up_rocket_64_v1 | `score_mean` | lower_good | -0.00175583 | 28 | 0.678571 | 1.32842 |

## Fold Side Summary

| Fold | Test Block | Side | Signals | TP | FP | Precision | Base Rate | Lift | FDR | Active Rate |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | middle | down | 6 | 3 | 3 | 0.5 | 0.417257 | 1.1983 | 0.5 | 0.0166667 |
| 0 | middle | up | 10 | 8 | 2 | 0.8 | 0.362222 | 2.20859 | 0.2 | 0.0416667 |
| 1 | latest | down | 0 | 0 | 0 | - | 0.333333 | - | - | 0 |
| 1 | latest | up | 113 | 56 | 57 | 0.495575 | 0.429896 | 1.15278 | 0.504425 | 0.316667 |

## Overall Side Summary

| Side | Signals | TP | FP | Precision | Base Rate | Lift | FDR | Active Rate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| down | 6 | 3 | 3 | 0.5 | 0.375295 | 1.33228 | 0.5 | 0.00833333 |
| up | 123 | 64 | 59 | 0.520325 | 0.396059 | 1.31376 | 0.479675 | 0.179167 |

## Interpretation

- This is an offline diagnostic only.
- Each fold trains rules from prior matured blocks only.
- Current test-block labels are used only for post-hoc scoring.
- Rules that fail forward blocks should not be wired into the live router.

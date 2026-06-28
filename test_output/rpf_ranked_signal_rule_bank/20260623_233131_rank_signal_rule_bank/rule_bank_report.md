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

## Fold Side Summary

| Fold | Test Block | Side | Signals | TP | FP | Precision | Base Rate | Lift | FDR | Active Rate |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | offset240 | down | 0 | 0 | 0 | - | 0.456076 | - | - | 0 |
| 0 | offset240 | up | 0 | 0 | 0 | - | 0.312674 | - | - | 0 |
| 1 | middle | down | 0 | 0 | 0 | - | 0.417257 | - | - | 0 |
| 1 | middle | up | 0 | 0 | 0 | - | 0.362222 | - | - | 0 |
| 2 | latest | down | 0 | 0 | 0 | - | 0.333333 | - | - | 0 |
| 2 | latest | up | 0 | 0 | 0 | - | 0.429896 | - | - | 0 |

## Overall Side Summary

| Side | Signals | TP | FP | Precision | Base Rate | Lift | FDR | Active Rate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| down | 0 | 0 | 0 | - | 0.402222 | - | - | 0 |
| up | 0 | 0 | 0 | - | 0.368264 | - | - | 0 |

## Interpretation

- This is an offline diagnostic only.
- Each fold trains rules from prior matured blocks only.
- Current test-block labels are used only for post-hoc scoring.
- Rules that fail forward blocks should not be wired into the live router.

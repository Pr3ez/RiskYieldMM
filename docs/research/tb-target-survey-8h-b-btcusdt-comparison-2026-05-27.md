# BTCUSDT 8h/B Target Survey: Completed-Run Metrics

Generated: 2026-05-28T07:39:04.065658+00:00

Scope: Stage-1 held-out selected-action prediction payloads, no TA flags, no anomaly overlay, `core-ex-target` context.

## Coverage

| Run | Target | Steps | Batch Range | Rows |
|---|---|---:|---|---:|
| Baseline | `target_4class` | 250 | 5498..5856 | 59,583 |
| Candidate | `target_4class_tb_atr_wide_v2` | 250 | 5498..5856 | 59,583 |

Executed/scorable coverage:

| Run | Executed Steps | Scorable Selected-Model Steps | No-Winner Steps |
|---|---:|---:|---:|
| Baseline | 250 | 250 | 0 |
| Candidate | 250 | 250 | 0 |

The full runs cover identical prediction batches and are directly comparable.

## Candidate Scorable Full-Scope Metrics

| Run | Steps | Rows | Accuracy | Macro F1 | Direction Accuracy | Cross-Direction Error | Logloss | Brier |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| target_4class_tb_atr_wide_v2 | 250 | 59,583 | 0.5046 | 0.5036 | 0.6711 | 0.3289 | 1.5254 | 0.6897 |

Candidate confusion matrix, rows=true class and columns=predicted class:

```text
[9738, 1646, 3013, 1527]
[4059, 6753, 1685, 2316]
[4007, 1267, 7082, 2023]
[4055, 1728, 2192, 6492]
```

Candidate direction confusion matrix, rows=true direction `[DOWN, UP]`:

```text
[22196, 8541]
[11057, 17789]
```

Candidate step stability:

- Mean step direction accuracy: `0.6711`
- Median step direction accuracy: `0.6979`
- Minimum step direction accuracy: `0.0000`
- Steps below 50% direction accuracy: `61/250`

Worst five candidate steps by direction accuracy:

| Batch | Rows | Accuracy | Macro F1 | Direction Accuracy | Cross-Direction Error |
|---:|---:|---:|---:|---:|---:|
| 5517 | 239 | 0.0000 | 0.0000 | 0.0000 | 1.0000 |
| 5516 | 240 | 0.0042 | 0.0185 | 0.0042 | 0.9958 |
| 5666 | 240 | 0.0000 | 0.0000 | 0.0125 | 0.9875 |
| 5797 | 238 | 0.0630 | 0.0318 | 0.0672 | 0.9328 |
| 5691 | 240 | 0.0708 | 0.0350 | 0.0875 | 0.9125 |

## Direct Overlap Comparison

| Target | Steps | Rows | Accuracy | Macro F1 | Direction Accuracy | Cross-Direction Error | Logloss | Brier |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| target_4class | 250 | 59,583 | 0.4608 | 0.4361 | 0.6794 | 0.3206 | 1.4135 | 0.7126 |
| target_4class_tb_atr_wide_v2 | 250 | 59,583 | 0.5046 | 0.5036 | 0.6711 | 0.3289 | 1.5254 | 0.6897 |

Metric deltas on overlapping prediction batches:

| Comparison | Accuracy | Macro F1 | Direction Accuracy | Cross-Direction Error | Logloss | Brier |
|---|---:|---:|---:|---:|---:|---:|
| Candidate - baseline | +0.0438 | +0.0675 | -0.0083 | +0.0083 | +0.1120 | -0.0229 |

## Decision

Do not promote the candidate as the default Stage-1 target yet. The full runs are directly comparable, and the candidate improves plain four-class accuracy and macro F1, but it does not pass the direction-sensitive acceptance gate.

Required acceptance gate:

- accuracy up
- macro F1 stable or up
- direction accuracy stable or up
- cross-direction error stable or down

Use this result as evidence that `tb_atr_wide_v2` improves class separability, then continue with target diagnostics focused on direction mistakes before applying anomaly overlays or expanding to other roots.

# BTCUSDT 8h/B Target Survey: Completed-Run Metrics

Generated: 2026-05-26T09:22:49.939640+00:00

Scope: Stage-1 held-out selected-action prediction payloads, no TA flags, no anomaly overlay, `core-ex-target` context.

## Coverage

| Run | Target | Steps | Batch Range | Rows |
|---|---|---:|---|---:|
| Baseline | `target_4class` | 2 | 5855..5856 | 480 |
| Candidate | `target_4class_tb_atr_wide_v2` | 134 | 5498..5856 | 31,843 |

Executed/scorable coverage:

| Run | Executed Steps | Scorable Selected-Model Steps | No-Winner Steps |
|---|---:|---:|---:|
| Baseline | 2 | 2 | 0 |
| Candidate | 250 | 134 | 116 |

**Full-run comparison is not yet fair:** the baseline does not cover the candidate's full prediction-batch set. Only the overlapping batches below are a direct comparison.

Common prediction batches: `[5855, 5856]`

**Pre-fix candidate coverage warning:** this report was generated before sparse-batch Stage-1 window handling was implemented. Some requested steps produced no winner because fold windows still assumed numeric `batch_id` continuity and failed on missing merged-batch ids.

Candidate no-winner steps: `116`

Most frequent recorded failure reasons:

- `missing_batch:5511:train`: 12
- `missing_batch:5532:train`: 12
- `missing_batch:5553:train`: 12
- `missing_batch:5574:train`: 12
- `missing_batch:5595:train`: 12

## Candidate Scorable Full-Scope Metrics

| Run | Steps | Rows | Accuracy | Macro F1 | Direction Accuracy | Cross-Direction Error | Logloss | Brier |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| target_4class_tb_atr_wide_v2 | 134 | 31,843 | 0.3047 | 0.2999 | 0.5266 | 0.4734 | 2.7856 | 0.8365 |

Candidate confusion matrix, rows=true class and columns=predicted class:

```text
[3716, 1752, 1217, 2170]
[2787, 2026, 1383, 2405]
[2365, 1672, 2171, 1630]
[1779, 2084, 898, 1788]
```

Candidate direction confusion matrix, rows=true direction `[DOWN, UP]`:

```text
[10281, 7175]
[7900, 6487]
```

Candidate step stability:

- Mean step direction accuracy: `0.5269`
- Median step direction accuracy: `0.5407`
- Minimum step direction accuracy: `0.0000`
- Steps below 50% direction accuracy: `62/134`

Worst five candidate steps by direction accuracy:

| Batch | Rows | Accuracy | Macro F1 | Direction Accuracy | Cross-Direction Error |
|---:|---:|---:|---:|---:|---:|
| 5586 | 240 | 0.0000 | 0.0000 | 0.0000 | 1.0000 |
| 5588 | 240 | 0.0000 | 0.0000 | 0.0000 | 1.0000 |
| 5626 | 239 | 0.0000 | 0.0000 | 0.0000 | 1.0000 |
| 5645 | 240 | 0.0000 | 0.0000 | 0.0000 | 1.0000 |
| 5666 | 240 | 0.0000 | 0.0000 | 0.0000 | 1.0000 |

## Direct Overlap Comparison

| Target | Steps | Rows | Accuracy | Macro F1 | Direction Accuracy | Cross-Direction Error | Logloss | Brier |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| target_4class | 2 | 480 | 0.2188 | 0.1146 | 0.4229 | 0.5771 | 1.9903 | 1.0278 |
| target_4class_tb_atr_wide_v2 | 2 | 480 | 0.3125 | 0.3242 | 0.5271 | 0.4729 | 1.2433 | 0.7121 |

## Decision

Do not promote the candidate based on this comparison yet. The candidate run is a useful pre-fix diagnostic, but the fair comparison must be rerun after the sparse-batch window fix so both legacy and `tb_atr_wide_v2` evaluate the same number of available prediction steps.

Required post-fix commands:

```bash
python scripts/analysis/htf_stage1_regime_family_walkforward.py \
  --build-merged-dataset \
  --stage1-target-col target_4class \
  --target-assets BTCUSDT \
  --context-assets core-ex-target \
  --roots 8h/B \
  --n-steps 250 \
  --resume-mode skip_completed \
  --runtime-mode routine
```

```bash
python scripts/analysis/htf_stage1_regime_family_walkforward.py \
  --build-merged-dataset \
  --stage1-target-col target_4class_tb_atr_wide_v2 \
  --target-assets BTCUSDT \
  --context-assets core-ex-target \
  --roots 8h/B \
  --n-steps 250 \
  --resume-mode skip_completed \
  --runtime-mode routine
```

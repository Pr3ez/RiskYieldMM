# BTCUSDT 8h/B Triple-Barrier Target Survey Smoke

Date: 2026-05-21
Scope: BTCUSDT, `8h/B`, all-core exact-timestamp context, no TA flags, no anomaly overlay
Purpose: first sanity-gated Stage-1 comparison of an experimental triple-barrier parent target against legacy `target_4class`.

## Inputs

Label materialization command:

```bash
python scripts/analysis/materialize_stage1_target_variants.py \
  --assets BTCUSDT \
  --roots 8h/B \
  --variants tb_atr_v1,tb_bollinger_v1,tb_keltner_v1,tb_atr_wide_v2 \
  --write-sanity-report
```

Stage-1 smoke command:

```bash
python scripts/analysis/htf_stage1_regime_family_walkforward.py \
  --build-merged-dataset \
  --stage1-target-col target_4class_tb_atr_wide_v2 \
  --target-assets BTCUSDT \
  --context-assets core-ex-target \
  --roots 8h/B \
  --n-steps 2 \
  --resume-mode skip_completed \
  --runtime-mode routine
```

The legacy baseline used the existing no-TA two-step run:

```text
data/htf_backtest_results/stage1_catboost_btcusdt_8h_b_ctx_corexself_live/
```

The triple-barrier candidate run is:

```text
data/htf_backtest_results/stage1_catboost_btcusdt_8h_b_ctx_corexself_target_tb_atr_wide_v2_live/
```

## Label Sanity

The original v1 ATR/Bollinger/Keltner variants remain diagnostic only. They
pass the eligible invalid-rate gate after excluding non-entry rows from the
denominator, but fail the class-share gate because balanced classes are almost
absent.

`target_4class_tb_atr_wide_v2` is the first model-ready candidate:

```text
eligible rows: 1,405,440
valid eligible rows: 1,404,118
eligible invalid ratio: 0.09%
same-bar both-hit ratio: 0.09%
class shares:
  DOWN_BALANCED  22.95%
  DOWN_EXPANSION 25.77%
  UP_BALANCED    26.25%
  UP_EXPANSION   25.02%
```

Interpretation: wider symmetric ATR barriers create a usable four-class parent
distribution for BTCUSDT `8h/B`. Non-entry rows remain `-1` by design and are
filtered before Stage-1 training.

## Two-Step Stage-1 Smoke

This is a tiny smoke comparison, not strategy evidence. It is useful only for
checking that the target can be trained and that obvious direction-sensitive
metrics do not immediately collapse.

| Target | Rows | Accuracy | Macro F1 | Direction Accuracy | Cross-Direction Error |
|---|---:|---:|---:|---:|---:|
| legacy `target_4class` | 480 | 0.2188 | 0.1146 | 0.4229 | 0.5771 |
| `target_4class_tb_atr_wide_v2` | 480 | 0.3125 | 0.3242 | 0.5271 | 0.4729 |

Step-level metrics:

| Target | Batch | Accuracy | Macro F1 | Direction Accuracy | Cross-Direction Error |
|---|---:|---:|---:|---:|---:|
| legacy | 5855 | 0.1708 | 0.1197 | 0.3500 | 0.6500 |
| legacy | 5856 | 0.2667 | 0.1053 | 0.4958 | 0.5042 |
| tb_atr_wide_v2 | 5855 | 0.3792 | 0.3037 | 0.7917 | 0.2083 |
| tb_atr_wide_v2 | 5856 | 0.2458 | 0.1227 | 0.2625 | 0.7375 |

Aggregate confusion matrices use rows as true labels and columns as predicted labels.

Legacy:

```text
[[  2   0 172   0]
 [  0   0 105   0]
 [  0   0  98   9]
 [  0   0  89   5]]
```

`tb_atr_wide_v2`:

```text
[[ 76   0  30   9]
 [ 92   0  29   0]
 [147   0  36  11]
 [ 12   0   0  38]]
```

## Decision

Continue with `target_4class_tb_atr_wide_v2`; do not promote it yet.

Reasons:

- It passes label sanity and improves the tiny aggregate smoke versus legacy.
- Step 5856 has poor direction accuracy, so the result is not stable enough for promotion.
- The run used only two prediction batches and the fallback manual triplet grid.

Next validation:

```bash
python scripts/analysis/htf_stage1_regime_family_walkforward.py \
  --build-merged-dataset \
  --stage1-target-col target_4class_tb_atr_wide_v2 \
  --target-assets BTCUSDT \
  --context-assets core-ex-target \
  --roots 8h/B \
  --n-steps 25 \
  --resume-mode skip_completed \
  --runtime-mode routine
```

Promotion gate for the next run:

```text
accuracy stable or higher than legacy
macro F1 stable or higher than legacy
direction accuracy higher than legacy
cross-direction error lower than legacy
no single-window direction collapse hidden by aggregate metrics
```

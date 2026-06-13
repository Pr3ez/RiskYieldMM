# RPF SHAP Panel Selection

## Purpose

Define the controlled way to try CatBoost recursive SHAP feature selection on
RPF features without turning full-dataset correlations into a leaked final
feature list.

## Current Status

Status: implemented as an experimental panel builder.

Command surface:

```bash
python -m regression_feature_engineering.walkforward.panel_select
```

The command writes frozen panel artifacts under:

```text
test_output/rpf_feature_panels/
```

The clean RPF walk-forward runner can consume the result through:

```bash
--frozen-panel-path test_output/rpf_feature_panels/<run_id>/selected_panel_<n>.json
```

## Scope

First scope:

```text
asset:  BTCUSDT
root:   8h/B
target: target_reg_direction_extreme_up_share_hvol_v2
```

The panel builder is target-agnostic, but every selected panel is target/root
specific and must be confirmed with later walk-forward windows.

## Source Of Truth

- Panel CLI: `regression_feature_engineering/walkforward/panel_select.py`
- Frozen panel policy: `regression_feature_engineering/walkforward/policy.py`
- Clean optimizer: `regression_feature_engineering/walkforward/optimize.py`
- Existing diagnostics:
  `test_output/regression_feature_engineering_*/**/feature_target_correlations.parquet`
- CatBoost feature selection docs:
  `https://catboost.ai/docs/en/concepts/python-reference_catboost_select_features`

## What This Does Not Decide

This does not promote a feature panel, replace walk-forward confirmation, or
allow full-timeline feature selection. It only creates a candidate panel for
controlled confirmation.

## Selection Contract

The panel builder uses two stages:

1. Diagnostic prefilter:
   - read existing `feature_target_correlations.parquet`;
   - read existing `feature_bin_spreads.parquet`;
   - keep only model-facing manifest features;
   - rank candidates by diagnostic Spearman/bin-spread evidence;
   - cap candidates per family so one feature family cannot dominate.

2. Model-aware recursive selection:
   - load one frozen development train/validation window;
   - run CatBoost `RecursiveByShapValues`;
   - default `shap_calc_type=Exact`;
   - select a fixed feature count;
   - write `selected_panel_<n>.json`.

The frozen panel is then used as a fixed feature policy in walk-forward. The
prediction window is not used for panel selection.

## Default Command

```bash
PY="/media/przem/linux_data/conda/envs/ml_env/bin/python"
READINESS_RUN="$(ls -td test_output/rpf_clean_walkforward/*_readiness_* | head -1)"

"$PY" -m regression_feature_engineering.walkforward.panel_select \
  --asset BTCUSDT \
  --root 8h/B \
  --target-col target_reg_direction_extreme_up_share_hvol_v2 \
  --config regression_feature_engineering/configs/rpf_clean_walkforward_v1.json \
  --base-run "$READINESS_RUN" \
  --candidate-limit 240 \
  --per-family-limit 40 \
  --num-features-to-select 80 \
  --selection-steps 3 \
  --shap-calc-type Exact \
  --task-type GPU
```

## Confirmation Command

```bash
PANEL="$(ls -td test_output/rpf_feature_panels/*/selected_panel_80.json | head -1)"

"$PY" -m regression_feature_engineering.walkforward.optimize \
  --stage baseline_probe \
  --asset BTCUSDT \
  --root 8h/B \
  --target-col target_reg_direction_extreme_up_share_hvol_v2 \
  --config regression_feature_engineering/configs/rpf_clean_walkforward_v1.json \
  --base-run "$READINESS_RUN" \
  --frozen-panel-path "$PANEL" \
  --n-steps 15 \
  --n-trials 12 \
  --task-type GPU
```

## Pass Criteria

The panel is useful only if later walk-forward runs improve validation RMSE and
reduce collapse versus the same-window `all_manifest_features` and family
ablation runs.

Minimum checks:

- validation RMSE beats train-mean baseline;
- prediction collapse rate does not exceed the configured gate;
- prediction dispersion improves;
- selected panel is not dominated by one duplicated feature family;
- confirmation windows were not used to select the panel.

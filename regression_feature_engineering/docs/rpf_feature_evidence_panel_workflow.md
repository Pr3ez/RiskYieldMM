# RPF Feature Evidence Panel Workflow

## Purpose

Turn the RPF feature diagnostics already collected into explicit, reusable
candidate panels before running more ElasticNet/CNN/CatBoost walk-forward
experiments.

This is the active bridge between feature analysis and model optimization.

## Current Status

Status: `implemented_unvalidated`.

2026-06-22 correction:

- panel scoring now includes side-aware signed direction evidence;
- feature-name side tokens receive a small bonus and opposite-side tokens
  receive a penalty;
- classification runs should use `--selector-refit-mode validation_mask` so
  validation threshold calibration and prediction refit use the same
  ElasticNet-selected feature mask;
- do not repeat the failed unlimited-signal evidence-panel shape without
  caps; use bounded `--max-signals-grid` values first.

The command surface is:

```bash
python -m regression_feature_engineering.walkforward.evidence_panel
```

It writes candidate panel artifacts under:

```text
test_output/rpf_feature_panels/
```

The classifier can now consume a panel as a candidate universe with:

```text
--candidate-panel-path <selected_panel.json>
```

This is different from:

```text
--frozen-panel-path <selected_panel.json>
```

`--candidate-panel-path` narrows the columns ElasticNet may inspect. ElasticNet
still fits inside each train fold and CatBoost still makes final predictions.

`--frozen-panel-path` uses exactly the panel features and bypasses ElasticNet.

## Evidence Inputs

The current evidence inventory is:

```text
test_output/rpf_feature_diagnostic_inventory/feature_signal_inventory.md
test_output/rpf_feature_diagnostic_inventory/binary_selected_feature_inventory.md
```

The first inventory was built from:

```text
158 feature_target_correlations.parquet files
158 feature_bin_spreads.parquet files
55,733 finite feature/target correlation rows
22,212 finite bin-spread rows
```

The second inventory was built from binary classifier selected-feature
artifacts:

```text
652,808 selected-feature rows
27 scanned classifier runs
```

## Evidence Read

The evidence says:

- `volatility_state` and `temporal_memory_volatility` are strongest for total
  path width.
- `acceptance_persistence`, especially `12h` and `8h`, is strongest for
  up-vs-down direction diagnostics.
- Binary ElasticNet runs repeatedly selected `interaction_confluence`,
  `structural_room`, and `liquidity_volume_pressure`.
- `cross_asset_context`, `temporal_memory_acceptance`, and
  `temporal_memory_structural_room` are weak in current evidence.

This mismatch is important: raw diagnostic signal and binary selected-feature
frequency do not point to the exact same families. That is why panels should be
tested as controlled candidate universes, not promoted directly.

## Panel Kinds

Implemented panel kinds:

```text
direction_core
binary_selected
hybrid_direction_binary
width_context
```

`direction_core` favors features with direct up-vs-down diagnostic evidence.

`binary_selected` favors features repeatedly selected by train-only ElasticNet
in previous binary walk-forward runs.

`hybrid_direction_binary` combines directional diagnostics, bin spreads,
binary selected-feature frequency, and a small amount of width context.
For UP/DOWN binary targets it is side-aware: signed direction diagnostics and
feature-name side tokens are aligned to the requested target side.

`width_context` is for volatility/path-size context, not direct trade
direction.

## First Panel Build Commands

Build an UP hybrid panel:

```bash
export PY="/media/przem/linux_data/conda/envs/ml_env/bin/python"

"$PY" -m regression_feature_engineering.walkforward.evidence_panel \
  --asset BTCUSDT \
  --root 8h/B \
  --target-col target_cls_extreme_up_ge_2x_down_hvol_v2 \
  --config regression_feature_engineering/configs/rpf_clean_walkforward_v1.json \
  --panel-kind hybrid_direction_binary \
  --selected-count 160 \
  --per-family-limit 45
```

Build a DOWN hybrid panel:

```bash
"$PY" -m regression_feature_engineering.walkforward.evidence_panel \
  --asset BTCUSDT \
  --root 8h/B \
  --target-col target_cls_extreme_down_ge_2x_up_hvol_v2 \
  --config regression_feature_engineering/configs/rpf_clean_walkforward_v1.json \
  --panel-kind hybrid_direction_binary \
  --selected-count 160 \
  --per-family-limit 45
```

## Validation Command Shape

Use the panel as a candidate universe while keeping ElasticNet, optional CNN,
and CatBoost in the fold-safe pipeline:

```bash
READINESS_RUN="$(ls -td test_output/rpf_clean_walkforward/*_readiness_* | head -1)"
PANEL="$(ls -td test_output/rpf_feature_panels/*hybrid_direction_binary*up_ge_2x_down*/selected_panel_160.json | head -1)"

"$PY" -m regression_feature_engineering.walkforward.classify_optuna \
  --asset BTCUSDT \
  --root 8h/B \
  --target-col target_cls_extreme_up_ge_2x_down_hvol_v2 \
  --config regression_feature_engineering/configs/rpf_clean_walkforward_v1.json \
  --base-run "$READINESS_RUN" \
  --candidate-panel-path "$PANEL" \
  --feature-policy elasticnet_logistic_v1 \
  --selector-refit-mode validation_mask \
  --sequence-embedding-mode none \
  --n-steps 30 \
  --holdout-steps 10 \
  --n-trials 8 \
  --objective-metric stable_signal_quality \
  --trial-objective-split prediction \
  --threshold-mode validation_sweep \
  --decision-policy causal_signal_budget \
  --threshold-grid 0.50,0.55,0.60,0.65,0.70 \
  --max-signals-grid 5,10,20 \
  --fp-cost 5 \
  --fn-cost 1 \
  --min-threshold-pass-rate 0.50 \
  --max-prediction-zero-positive-window-rate 0.90 \
  --max-prediction-all-positive-window-rate 0.10 \
  --max-prediction-high-fpr-window-rate 0.35 \
  --max-prediction-window-false-positive-rate 0.30 \
  --iterations-choices 200,400 \
  --depth-choices 2,3 \
  --learning-rate-choices 0.005,0.01 \
  --l2-leaf-reg-choices 30,100 \
  --early-stopping-rounds-choices 50,100 \
  --od-wait-choices 50,100 \
  --elasticnet-c-choices 0.03,0.1 \
  --elasticnet-l1-ratio-choices 0.25,0.5,0.75 \
  --elasticnet-max-features-choices 40,80 \
  --elasticnet-prefilter-features-choices 80,160 \
  --task-type CPU
```

## Validation Rule

The panel improves the process only if it beats the matching previous
same-target baseline on held-out windows.

Check:

- holdout precision;
- holdout false positives;
- active signal window count;
- repeated active signal windows;
- prediction positive rate;
- selected feature stability;
- whether high precision appears outside the tuning windows.

Do not promote a panel from tuning-window precision alone.

## Why This Exists

Running broad Optuna over all 2,530 features made the process noisy and hard to
interpret. This workflow makes the next experiment explicit:

```text
diagnostics -> evidence panel -> train-only ElasticNet inside panel -> optional CNN -> CatBoost -> held-out confirmation
```

That gives us a clean way to test whether feature evidence actually improves
stable high-precision binary signals.

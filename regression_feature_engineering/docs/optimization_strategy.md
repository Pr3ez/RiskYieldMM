# Regression Feature Optimization Strategy

## Purpose

Define how future regression features should be accepted, rejected, and compared.

## Current Status

Phase 1/2 feature materialization and validation are available across all core
assets and roots. Phase 3 structural room and Phase 4 acceptance/persistence
are technically clean on `BTCUSDT 8h/B`, but directional evidence remains early
and requires walk-forward ablation. Phase 5 temporal-memory validation is clean
on the sliced `BTCUSDT 8h/B` reports.

The active RPF optimization command surface is now the clean RPF-native runner:

```text
python -m regression_feature_engineering.walkforward.optimize
```

It loads RPF features directly and does not tune old HTF/helper features. The
first clean target is `target_reg_direction_extreme_up_share_hvol_v2`.

The active decision-layer experiment is now binary UP/DOWN classification with
regime-conditioned evaluation:

```text
target_cls_extreme_up_ge_2x_down_hvol_v2
target_cls_extreme_down_ge_2x_up_hvol_v2
```

These targets are not replacements for the distance/share regression targets.
They are an experimental trading-decision layer. Current evidence requires
keeping both sides and evaluating performance by regime rather than choosing a
single global winner.

The first corrected validation-led smoke did not support promotion of the
current `rpf_*` set:

```text
target: target_reg_distance_up_extreme_hvol_v2
root:   BTCUSDT 8h/B
steps:  5

htf_only validation Spearman:            0.304247
regression_only validation Spearman:     0.059750
htf_plus_regression validation Spearman: 0.095225
```

Treat this as a warning, not final proof. The current RPF features are
engineering-valid candidates, not accepted predictive features.

## Scope

Applies to `regression_path_features_v1` and `distance_horizon_vol_v2`.

## Source Of Truth

- Clean RPF runner: `regression_feature_engineering/walkforward/`
- Clean RPF reset contract: `clean_rpf_walkforward_reset.md`
- Default clean config:
  `regression_feature_engineering/configs/rpf_clean_walkforward_v1.json`
- Feature taxonomy: `feature_taxonomy.md`
- Feature coverage: `feature_coverage_matrix.md`
- Feature implementation TODO: `feature_implementation_todo.md`

## What This Does Not Decide

This document does not choose final CatBoost hyperparameters, binary decision
thresholds, or live regime gates.

## Clean RPF Optimization Rule

New RPF model optimization must use the RPF-native runner, not the old Stage-1
regression scripts.

Clean RPF rules:

- feature source is `regression_only`;
- feature policy is fixed at the config value during the current pass;
- Optuna tunes only walk-forward window geometry, CatBoost parameters, and
  explicit selector settings when `elasticnet_logistic_v1` is selected;
- the baseline feature policy is `all_manifest_features`, so every
  model-facing RPF manifest column is used;
- the active dynamic-selection experiment is `elasticnet_logistic_v1`: per
  walk-forward step it computes train-only feature mean/std, fits a sparse
  logistic ElasticNet selector on scaled train rows, then CatBoost trains on
  the selected scaled train panel and scores validation;
- `elasticnet_logistic_v1` may use a train-only prefilter candidate cap before
  the sparse ElasticNet fit. This is a runtime control, not a look-ahead
  shortcut: candidates are ranked using train rows only, and validation or
  prediction rows never affect the candidate list;
- after validation chooses early stopping and threshold behavior, the
  validation-selected feature mask is frozen by default; the selector scaler
  and CatBoost model are refit on train+validation rows for that same mask
  before scoring the held-out prediction batch;
- `--selector-refit-mode train_val_reselect` is available only as an explicit
  diagnostic mode because it reruns ElasticNet after threshold calibration and
  can change the prediction model boundary;
- selector tuning is limited to `C`, `l1_ratio`, `max_selected_features`,
  `coef_eps`, and `elasticnet_prefilter_features`; scaler type is fixed to
  train-only standardization until the selector baseline is understood;
- `frozen_panel` is available for explicit panel-confirmation runs after a
  panel is written by `python -m regression_feature_engineering.walkforward.panel_select`;
- `feature_ablation=all` is the default; family-level ablation is fixed before
  a run and does not select individual features;
- do not optimize feature policy and gates together. Compare CatBoost with
  `all_manifest_features` versus CatBoost with `elasticnet_logistic_v1` on
  chronological recent windows only; EMA, gate, signal-bank, and decision-bank
  paths are historical/deferred diagnostics for now;
- model features come only from the RPF manifest `feature_columns`;
- diagnostic `rpf_align_*` columns are excluded;
- labels are exact-joined by `timestamp,batch_id`;
- valid rows require `target_reg_distance_valid_v2=true`;
- readiness validates `label_window_start`, `label_window_end`,
  `label_window_batch_id`, and `target_reg_distance_horizon_minutes_v2` to
  reject overlapping train/validation/prediction label windows;
- sparse windows count available RPF/label batch intersections;
- clean regression/share optimization chooses configs by minimizing validation
  RMSE only;
- binary trading-decision experiments use validation inside each fold and score
  grid/Optuna trials with aggregate prediction-batch metrics by default;
- binary trading-decision experiments must reserve untouched confirmation
  windows with `--holdout-steps` once a run is larger than a smoke test;
- every trial compares model RMSE with constant `0.5`, train-target-mean,
  validation-target-mean, and previous-prediction-batch-mean baselines;
- non-confirmation stages reject severe per-window prediction collapse and
  under-dispersion;
- every stage writes `events.jsonl`, `trials.parquet`,
  `window_metrics.parquet`, `best_config.json`, `stage_status.json`, and a
  Markdown report under
  `test_output/rpf_clean_walkforward/`.
- `geometry`, `baseline_probe`, and `core_model` use Optuna `GridSampler` over
  explicit finite choice lists to avoid repeated duplicate trials.

SHAP panel-selection rule:

- existing Spearman/bin-spread diagnostics may define a candidate pool;
- CatBoost `RecursiveByShapValues` with `shap_calc_type=Exact` may refine that
  pool on a frozen development train/validation window;
- the selected panel must be frozen to JSON and passed with
  `--frozen-panel-path`;
- prediction/confirmation windows must not be used to choose the panel.

Clean stage order:

```text
readiness -> baseline_probe -> geometry -> core_model -> sampling -> confirmation
```

First clean readiness command:

```bash
/media/przem/linux_data/conda/envs/ml_env/bin/python \
  -m regression_feature_engineering.walkforward.optimize \
  --stage readiness \
  --asset BTCUSDT \
  --root 8h/B \
  --target-col target_reg_direction_extreme_up_share_hvol_v2 \
  --config regression_feature_engineering/configs/rpf_clean_walkforward_v1.json \
  --n-steps 20
```

First clean baseline probe command:

```bash
/media/przem/linux_data/conda/envs/ml_env/bin/python \
  -m regression_feature_engineering.walkforward.optimize \
  --stage baseline_probe \
  --asset BTCUSDT \
  --root 8h/B \
  --target-col target_reg_direction_extreme_up_share_hvol_v2 \
  --config regression_feature_engineering/configs/rpf_clean_walkforward_v1.json \
  --base-run test_output/rpf_clean_walkforward/<readiness_run_id> \
  --n-steps 1 \
  --n-trials 18 \
  --task-type GPU
```

## Historical Comparison Sets

Every benchmark should compare:

- current HTF-only features;
- regression-path-only features;
- HTF plus regression-path features.

The current Stage-1 regression runner implements these as:

```text
--feature-source-mode htf_only
--feature-source-mode regression_only
--feature-source-mode htf_plus_regression
```

Regression-path features are joined for the target asset by exact
`timestamp,batch_id`. The merged HTF dataset remains the row authority, so
closed-session/context availability behavior remains unchanged.

This comparison set is useful for final baseline reporting only. It is not the
active RPF optimization path.

## Primary Evidence

Features are useful when they improve:

- Spearman rank correlation;
- high-distance quantile separation;
- prediction p95 coverage versus target p95;
- MAE/RMSE without materially worsening tail ranking;
- chronological stability across walk-forward steps.

For binary decision-layer experiments, also evaluate:

- false-positive rate;
- precision;
- recall;
- predicted-positive rate;
- validation-selected threshold stability;
- decision cost with an explicit false-positive penalty;
- performance by trend, volatility/range, and structural-location buckets.

Global binary metrics are insufficient. A target can be useful only in a
specific live-safe regime.

## Rejection Rules

Reject or quarantine features that are:

- nonfinite or null-heavy;
- constant or near-constant;
- raw unscaled OHLCV;
- label or future diagnostics;
- duplicated or near-duplicated without added evidence;
- strong in-sample but unstable across chronological windows.

Formula validation starts with `BTCUSDT 8h/B`, then expands to all core assets
and all six root IDs. Promotion still requires stable walk-forward evidence.

## Parameter Sweeps

Rolling-window features should be tuned through report-only sweeps before any
default parameter is changed. A sweep may compute candidate features in memory
and write diagnostics under `test_output/`, but it must not rewrite promoted
feature roots under `data/`.

Memory rule for sweeps and diagnostics:

- full-root materialization is chunked and safe to run with
  `--batch-chunk-size`;
- full-root validation should keep expensive signal diagnostics narrow by using
  `--diagnostic-feature-prefix`, for example `rpf_accept_15m_`;
- validation defaults to `25,000` sampled valid rows and refuses more than `80`
  diagnostic feature columns unless `--allow-wide-diagnostics` is passed;
- report-only lookback sweeps default to `--batch-limit 200`; use `--full-root`
  only for planned high-memory runs;
- if a run OOMs, first reduce diagnostic columns, then reduce sample rows, then
  reduce batch count. Do not change formulas before confirming the OOM is not
  just a diagnostic-width problem.

Legacy Stage-1 grid-search rule:

The following Stage-1 grid runner is retained for historical comparison and
same-window HTF baseline reporting. Do not use it to tune RPF-native windows,
RPF feature policy, or RPF CatBoost parameters.

- use `scripts/analysis/htf_stage1_regression_grid_search.py` for controlled
  comparisons of feature source, lookback, validation width, selected feature
  count, strict Spearman threshold, dedupe threshold, and CatBoost
  hyperparameters;
- every grid row writes an isolated walk-forward run suffix so outputs are not
  overwritten;
- historical Stage-1 searches used `target_specific_v2`; do not copy that
  feature-selection policy into the clean RPF binary pass. Use
  `elasticnet_logistic_v1` when testing dynamic binary feature selection;
- grid summaries choose candidates from validation metrics. Prediction-batch
  metrics are confirmation evidence only;
- use `--max-configs-per-target` for bounded per-target searches and
  `--max-runs-total` for a true global cap. Do not use deprecated `--max-runs`
  for new work;
- do not choose global feature lists from full-dataset correlations. Use global
  diagnostics only to define candidate families and sanity checks.

Legacy Stage-1 Optuna note:

`scripts/analysis/htf_stage1_regression_optuna.py` is retained only for
historical artifact inspection. New RPF work must use the clean RPF-native CLI.
Do not use the legacy Stage-1 Optuna wrapper to tune RPF windows, RPF feature
policy, or RPF CatBoost parameters.

Clean RPF command sequence:

1. Readiness and frozen windows:

```bash
/media/przem/linux_data/conda/envs/ml_env/bin/python \
  -m regression_feature_engineering.walkforward.optimize \
  --stage readiness \
  --asset BTCUSDT \
  --root 8h/B \
  --target-col target_reg_direction_extreme_up_share_hvol_v2 \
  --config regression_feature_engineering/configs/rpf_clean_walkforward_v1.json \
  --n-steps 20
```

2. Baseline CatBoost probe:

```bash
/media/przem/linux_data/conda/envs/ml_env/bin/python \
  -m regression_feature_engineering.walkforward.optimize \
  --stage baseline_probe \
  --asset BTCUSDT \
  --root 8h/B \
  --target-col target_reg_direction_extreme_up_share_hvol_v2 \
  --config regression_feature_engineering/configs/rpf_clean_walkforward_v1.json \
  --base-run test_output/rpf_clean_walkforward/<readiness_run_id> \
  --iterations-choices 400,800,1200 \
  --depth-choices 3,4 \
  --learning-rate-choices 0.005,0.01,0.02 \
  --l2-leaf-reg-choices 100,200,300 \
  --early-stopping-rounds-choices 50,100,150 \
  --od-wait-choices 50,100,150 \
  --n-steps 1 \
  --n-trials 18 \
  --task-type GPU
```

3. Walk-forward geometry:

```bash
/media/przem/linux_data/conda/envs/ml_env/bin/python \
  -m regression_feature_engineering.walkforward.optimize \
  --stage geometry \
  --asset BTCUSDT \
  --root 8h/B \
  --target-col target_reg_direction_extreme_up_share_hvol_v2 \
  --config regression_feature_engineering/configs/rpf_clean_walkforward_v1.json \
  --base-run test_output/rpf_clean_walkforward/<baseline_probe_run_id> \
  --lookback-choices 80,120,160,180 \
  --val-choices 8,10,12 \
  --embargo-choices 0 \
  --n-steps 15 \
  --n-trials 12 \
  --task-type GPU
```

Feature-source and feature-selection policy tuning is explicitly deferred.
Do not run a feature-policy stage in the clean RPF pass.

Before geometry/core-model tuning, run fixed feature-family ablations on the
same frozen windows. Candidate scopes must beat the train-target-mean baseline
by validation RMSE and pass collapse diagnostics before they become tuning
inputs.

4. Core CatBoost capacity, using the geometry lock as base config:

```bash
/media/przem/linux_data/conda/envs/ml_env/bin/python \
  -m regression_feature_engineering.walkforward.optimize \
  --stage core_model \
  --asset BTCUSDT \
  --root 8h/B \
  --target-col target_reg_direction_extreme_up_share_hvol_v2 \
  --config regression_feature_engineering/configs/rpf_clean_walkforward_v1.json \
  --base-run test_output/rpf_clean_walkforward/<geometry_run_id> \
  --iterations-choices 400,800,1200 \
  --depth-choices 3,4 \
  --learning-rate-choices 0.005,0.01,0.02 \
  --l2-leaf-reg-choices 100,200,300 \
  --early-stopping-rounds-choices 50,100,150 \
  --od-wait-choices 50,100,150 \
  --n-steps 15 \
  --n-trials 18 \
  --task-type GPU
```

Only after core-model tuning beats the same-window baseline should the
workflow run `sampling` and full `confirmation` stages across the six
`distance_horizon_vol_v2` targets.

First structural-room sweep evidence for `BTCUSDT 8h/B`:

- candidate lookback sets tested: `2,4,8`, `4,8,16`, `4,16,48`,
  `8,24,72`, `16,48,144`, and `24,72,240`;
- directional imbalance evidence remained weak, with best absolute Spearman
  around `0.0489`;
- path-width evidence improved modestly, with best absolute Spearman around
  `0.2521` for wider lookbacks;
- conclusion: parameter sweeps are useful, but static structural-room windows
  should not be expected to provide the missing directional signal by
  themselves.

## Full-Matrix Optimization Order

After `distance_horizon_vol_v2` labels exist for all core assets and root IDs,
feature optimization should be matrix-aware:

- evaluate all six target columns for the same asset/root together;
- keep shared causal formulas across assets and roots;
- let the walk-forward runner select target-specific subsets using train rows
  only;
- compare feature families by ablation before promotion;
- reject features that improve one target while consistently damaging the
  opposite-direction target.

This keeps the workflow simple enough to maintain while still letting each
regression target use the features that fit its path-shape objective.

## Regime-Gated Binary Direction Rule

Binary UP/DOWN classification experiments must preserve both target sides:

```text
target_cls_extreme_up_ge_2x_down_hvol_v2
target_cls_extreme_down_ge_2x_up_hvol_v2
```

The purpose is not to drop the weaker global side. The purpose is to identify
where each side has usable conditional precision/recall.

Diagnostic labels may define research buckets such as:

```text
future_up_dominant
future_down_dominant
future_two_sided
future_low_edge
```

but those labels must not enter live feature matrices. Live gates must use
current/prior RPF features only. The active gate plan is
`rpf_regime_gated_prediction_plan.md`.

## Coverage-Gate Rule

Before adding another complex model layer, confirm the deterministic feature
coverage matrix has been tested in order:

1. base causal state: alignment, volatility, structural room, acceptance;
2. temporal memory transforms: lags, EWM, slopes, percentile ranks;
3. rejection/chop, spike/breakout, liquidity/volume pressure;
4. regime/calendar state and interaction/confluence;
5. cross-asset context;
6. deterministic factor and sequence-shape proxies;
7. train-window-only learned factor or sequence embeddings.

Do not use learned CNN/sequence embeddings to compensate for missing
deterministic features. Learned encoders remain deferred until the causal
feature surface is validated.

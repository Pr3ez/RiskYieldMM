# HTF Stage-1 Step-2 Plan (CatBoost)

## Purpose
Stage-1 Step-2 is an offline refinement pass over Stage-1 Step-1 artifacts.

It does not replace Step-1 and does not run standard backtest/Optuna logic.

Primary goals:
- identify noisy features per combo
- identify noisy features globally per timeframe/target
- compare baseline vs filtered prediction behavior on the same step set
- store reproducible artifacts for later policy/RL training decisions

## Scope and Isolation Rules
- Step-1 remains the data-collection engine (`run_walk_forward_stage1_grid`).
- Step-2 runs in a separate output root:
  - `data/htf_backtest_results/{run_id}/stage1_step2/{model}/...`
- Step-2 never overwrites Step-1 payload files under:
  - `.../{model}/{tf}/{target}/batch_xxxx/stage1/`
- Standard backtest (Optuna/final training path) is out of scope.

## Inputs Required from Step-1
Per step/unit:
- `stage1_combo_index.parquet`
- `stage1_fold_windows.parquet`
- `stage1_pred_batch_predictions.parquet`

From current config map:
- allowed combo set for this unit (triplet grid)
- target class metadata and feature source mapping
- baseline CatBoost params and fixed boosting rounds

## Step-2 Processing Flow (Per `timeframe/target`)
1. Discover Stage-1 step folders (`batch_*`), optionally cap by `max_steps_per_unit`.
2. Load Stage-1 combo metadata and prediction payloads for each step.
3. Recompute baseline combo scores from prediction payloads using current selection metric:
   - `macro_f1` or `cross_direction_error` (from unit config).
4. Select processing scope:
   - default: `winner_only` (one best combo per step)
   - optional: `all_combos` (evaluate every combo each step)
5. For each selected combo:
   - recover train window from `stage1_fold_windows.parquet`
   - retrain baseline CatBoost for that window
   - extract feature importance (`PredictionValuesChange` by default)
   - mark step-level noisy features (`importance <= quantile(noisy_bottom_quantile)`).
6. Aggregate noisy-feature frequency across processed steps:
   - feature is drop candidate if `noisy_step_freq >= noisy_presence_threshold`.
7. Build filtered feature mask:
   - keep all non-drop features
   - enforce `min_features_keep` floor.
8. Re-run per-step prediction with filtered mask and compare baseline vs filtered metrics.
9. Compute reward-style summary fields:
   - baseline/filtered reward
   - reward delta
   - promotion gate pass/fail using configured thresholds.
10. Persist combo-level outputs and unit-level global mask.
11. Persist `step2_step_winners.parquet` (winner trace per step) when winner mode is used.

## Artifact Layout (Step-2)
Root:
- `data/htf_backtest_results/{run_id}/stage1_step2/{model}/`

Per unit:
- `{tf}/{target}/step2_summary.json`
- `{tf}/{target}/step2_feature_importance_global.parquet`
- `{tf}/{target}/step2_feature_noise_summary_global.parquet`
- `{tf}/{target}/step2_feature_mask_global.json`

Per combo:
- `{tf}/{target}/combos/{action_key}/step2_baseline_steps.parquet`
- `{tf}/{target}/combos/{action_key}/step2_feature_importance_steps.parquet`
- `{tf}/{target}/combos/{action_key}/step2_feature_noise_summary.parquet`
- `{tf}/{target}/combos/{action_key}/step2_filtered_steps.parquet`
- `{tf}/{target}/combos/{action_key}/step2_baseline_vs_filtered.parquet`
- `{tf}/{target}/combos/{action_key}/step2_feature_mask.json`
- `{tf}/{target}/combos/{action_key}/step2_summary.json`

Run-level:
- `step2_global_summary.parquet`
- `step2_run_summary.json`

## Decision Objects Produced
For each combo (`action_key`) per unit:
- baseline mean metric
- filtered mean metric
- delta (filtered minus baseline)
- reward delta and promotion gate status
- combo-specific kept/removed features

For each unit:
- global kept/removed feature mask across all combos
- step-level winner table (`step2_step_winners.parquet`)

This creates:
- 1 mask per combo
- 1 global mask per timeframe/target

## Promotion Gate Semantics
A combo passes promotion gate only if all are satisfied:
- `reward_delta >= promotion_min_reward_delta`
- `macro_f1_delta >= promotion_min_macro_f1_delta`
- `cross_direction_error_delta <= promotion_max_cross_direction_error_delta`

Defaults are conservative; gate criteria are for offline screening, not runtime forcing.

## Cell Mapping in `notebooks/htf_pythonscript.py`
- Cell 14: Stage-1 Step-1 only (payload collection, resume-in-place, fixed run id).
- Cell 15: Stage-1 Step-2 only (feature pruning/evaluation from Step-1 artifacts).

## Recommended Operating Cycle
1. Run Cell 14 to extend Step-1 dataset.
2. Run Cell 15 to refresh Step-2 masks and baseline-vs-filtered comparisons.
3. Review `step2_global_summary.parquet` and combo summaries.
4. Promote only masks/combos that pass gate consistently.
5. Feed selected artifacts into reward/policy dataset builders.

## Non-Goals
- no runtime final model deployment inside Step-2
- no mutation of historical Step-1 raw payloads
- no Optuna trial loop in Step-2

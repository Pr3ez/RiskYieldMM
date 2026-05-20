# HTF Stage-1 Artifacts (CatBoost, Isolated)

> Current scope
>
> These artifact paths describe the legacy regime/family Stage-1 outputs. The
> multi-asset HTF layer writes per-asset feature and label roots under
> `data/htf_multiasset/{asset}/`. The Stage-1 launcher can now assemble
> target/context feature and label roots under `data/htf_multiasset_merged/`
> and then write normal CatBoost Stage-1 run artifacts.

Merged dataset artifacts are written before training:

```text
data/htf_multiasset_merged/{target_asset}/{context_hash}/{root_id}/features/1m/target_4class/batch_*.parquet
data/htf_multiasset_merged/{target_asset}/{context_hash}/{root_id}/labels/1m/batch_*.parquet
data/htf_multiasset_merged/{target_asset}/{context_hash}/{root_id}/manifest.json
```

The manifest records target/context assets, source roots, output roots, input
rows, output rows, `rows_dropped_by_missing_context`,
`rows_dropped_by_null_features`, `duplicate_count`, `null_feature_count`,
schema hash, feature count, and timestamp range. Merged feature outputs are
valid only when `duplicate_count=0` and `null_feature_count=0`.

Merged multi-asset roots may have sparse batch ids. This is expected when exact
timestamp context coverage begins later than the target asset history. Stage-1
validity scanning supports those sparse ids; per-combo missing-batch failures
near local gaps are recorded in `stage1_step_summary.json`.

Stage-1 step artifacts are written under:

`data/htf_backtest_results/{run_id}/catboost/{timeframe}/{target}/batch_{pred_batch}/stage1/`

Step-2 artifacts are written under a separate tree:

`data/htf_backtest_results/{run_id}/{output_subdir}/catboost/{timeframe}/{target}/...`

Default `output_subdir` is `stage1_step2`.

## Required Files Per Step

1. `stage1_step_summary.json`
- lightweight run summary for this step/unit
- includes:
  - combo/fold counts
  - payload row counts
  - cache counters
  - leakage guard status
  - fail reason counts
  - runtime

2. `stage1_combo_index.parquet`
- one row per combo
- columns:
  - `combo_id`
  - `action_key` (`f{fold}_v{val}_t{train}`)
  - `fold_count`
  - `val_batches_per_fold`
  - `train_batches_per_fold`
  - `status` (`complete`/`failed`)
  - `fail_reason`
  - `folds_expected`
  - `folds_completed`
  - `runtime_s`

3. `stage1_fold_windows.parquet`
- fold window definitions per combo
- columns:
  - `combo_id`
  - `action_key` (`f{fold}_v{val}_t{train}`)
  - `fold_id`
  - `train_start_batch`, `train_end_batch`
  - `val_start_batch`, `val_end_batch`, `val_batch`

4. `stage1_val_predictions.parquet`
- raw validation predictions across all combos/folds
- columns:
  - `combo_id`, `fold_id`, `scope`
  - `timestamp`, `batch_id`
  - `y_true`, `y_pred`
  - `prob_class_0 ... prob_class_{n-1}`

5. `stage1_pred_batch_predictions.parquet`
- raw prediction-batch outputs across all combos
- columns:
  - `combo_id`, `fold_id` (`0`), `scope` (`pred_batch`)
  - `timestamp`, `batch_id`
  - `y_true`, `y_pred`
  - `prob_class_0 ... prob_class_{n-1}`

6. `stage1_runtime_profile.json`
- top slow combos and copied summary block for quick profiling

7. `stage1_config_snapshot.json`
- serialized config/window/feature/model search spaces used for the step

8. `stage1_predecision_context.json`
- leakage-safe context snapshot captured before combo scoring
- includes:
  - lookback batch/row geometry
  - class distribution in lookback window
  - class distribution in recent window (`recent_ref_batches`)
  - prediction-batch timestamp bounds and row count

9. `stage1_predecision_context.parquet`
- same context in one-row tabular form
- flattened class fields for direct ML dataset assembly:
  - `lookback_class_count_{c}`, `lookback_class_pct_{c}`
  - `recent_class_count_{c}`, `recent_class_pct_{c}`

## Parent Step Metadata
Under parent step folder:

`data/htf_backtest_results/{run_id}/catboost/{timeframe}/{target}/batch_{pred_batch}/`

- `batch_metadata.json` (links Stage-1 artifacts and summary)

## Step-2 Artifacts (Separate Output Tree)
Under:

`data/htf_backtest_results/{run_id}/stage1_step2/catboost/{timeframe}/{target}/`

Unit-level:
- `step2_summary.json`
- `step2_step_winners.parquet`
- `step2_feature_importance_global.parquet`
- `step2_feature_noise_summary_global.parquet`
- `step2_feature_mask_global.json`

Per combo:
- `combos/{action_key}/step2_baseline_steps.parquet`
- `combos/{action_key}/step2_feature_importance_steps.parquet`
- `combos/{action_key}/step2_selected_features_per_step.parquet`
- `combos/{action_key}/step2_feature_noise_summary.parquet`
- `combos/{action_key}/step2_filtered_steps.parquet`
- `combos/{action_key}/step2_baseline_vs_filtered.parquet`
- `combos/{action_key}/step2_feature_mask.json`
- `combos/{action_key}/step2_summary.json`

Run-level:
- `data/htf_backtest_results/{run_id}/stage1_step2/catboost/step2_global_summary.parquet`
- `data/htf_backtest_results/{run_id}/stage1_step2/catboost/step2_run_summary.json`

## Run-Level Robustness Metadata
Under:

`data/htf_backtest_results/{run_id}/`

- `stage1_collection_plan.json`
  - written by Cell 14 preflight
  - tracks discovered complete/incomplete step folders and required files
- `stage1_run_state.json`
  - written by Stage-1 runner
  - tracks selected step batches, execution units, resume mode, progress artifact path
- `stage1_progress.parquet`
  - one row per attempted/skipped unit-step in current run invocation
  - statuses: `completed`, `error`, `skipped_completed`

## Auto-Pruning Metadata (Run-Level)
Offline analyzer output for candidate grid reduction:

`data/htf_backtest_results/stage1_meta/catboost/{source_run_id}/`

Files:
- `candidate_selection.json`
- `pair_stats.parquet`
- `fold_stats.parquet`
- `combo_stats.parquet`
- `reward_metadata.json`
- `reward_table.parquet`
- `reward_combo_stats.parquet`
- `reward_unit_stats.parquet`
- `policy_dataset_metadata.json`
- `policy_events.parquet`
- `policy_step_best.parquet`

Latest convenience copy:
- `data/htf_backtest_results/stage1_meta/catboost/latest_candidate_selection.json`

This metadata is used to auto-build reduced `stage1_pair_grid` and
optional `stage1_fold_grid` for future Stage-1 runs.

`reward_*` and `policy_*` files are used for RL/autoregressive policy training.

### `reward_table.parquet` key columns
- `unit`, `timeframe`, `target`, `step`
- `combo_id`, `action_key`, `fold_count`, `val_batches_per_fold`, `train_batches_per_fold`
- validation metrics: `val_accuracy`, `val_macro_f1`, `val_cross_direction_error`, `val_logloss`
- prediction metrics: `pred_accuracy`, `pred_macro_f1`, `pred_cross_direction_error`, `pred_logloss`
- reward fields: `reward_validation`, `reward_prediction`, `selected_reward`
- ranking labels: `reward_rank`, `is_step_best`

### `policy_events.parquet` key columns
- all `reward_table.parquet` fields
- pre-decision state columns from `stage1_predecision_context.parquet`
- lagged best-action features (`lag{n}_*`) from previous steps

## Offline Metric Computation
Stage-1 stores raw labels and probabilities so any metric can be computed later:
- accuracy / macro-F1 / logloss
- per-class precision/recall
- directional metrics / cross-direction error
- calibration and threshold studies
- stability across folds and steps
- and now also stores explicit pre-decision context needed for
  autoregressive/RL policy datasets.

## Stage-1 Offline Modules
- `scripts/htf_backtest/catboost/stage1_reward.py`
  - builds combo-level reward table from raw validation + prediction payloads
  - reward can mix `macro_f1`, `cross_direction_error`, `accuracy`, `logloss`
- `scripts/htf_backtest/catboost/stage1_policy_dataset.py`
  - joins reward table with `stage1_predecision_context.parquet`
  - exports state/action/reward events for policy learning
  - exports per-step best-action table with lag features

Step-2 pruning/evaluation module:
- `scripts/htf_backtest/catboost/stage1_step2.py`
  - reads Step-1 artifacts
  - writes separate Step-2 artifacts
  - does not overwrite Step-1 payload parquet files

Step-2 design/operating plan:
- `docs/htf/stage1-step2-plan.md`

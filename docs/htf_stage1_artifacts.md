# HTF Stage-1 Artifacts (CatBoost, Isolated)

Stage-1 step artifacts are written under:

`data/htf_backtest_results/{run_id}/catboost/{timeframe}/{target}/batch_{pred_batch}/stage1/`

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

## Parent Step Metadata
Under parent step folder:

`data/htf_backtest_results/{run_id}/catboost/{timeframe}/{target}/batch_{pred_batch}/`

- `batch_metadata.json` (links Stage-1 artifacts and summary)

## Offline Metric Computation
Stage-1 stores raw labels and probabilities so any metric can be computed later:
- accuracy / macro-F1 / logloss
- per-class precision/recall
- directional metrics / cross-direction error
- calibration and threshold studies
- stability across folds and steps

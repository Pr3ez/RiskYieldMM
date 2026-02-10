# HTF Stage-1 Logic (CatBoost, Isolated)

## Purpose
Stage-1 is an offline dataset-generation run profile for fold-grid analysis.  
It is not the standard Optuna/runtime model-selection path.

Primary objective:
- generate raw validation and prediction-batch payloads for every Stage-1 combo
- compute selection/quality metrics later in analysis scripts
- keep optimization leakage-safe

## Entrypoints
- Stage-1 runner: `scripts/htf_backtest/catboost/stage1_runner.py`
  - `run_walk_forward_stage1_grid(...)`
- Stage-1 evaluator: `scripts/htf_backtest/catboost/stage1_optimizer.py`
  - `evaluate_stage1_grid(...)`

## High-Level Flow
For each walk-forward step and each execution unit (`model/timeframe/target`):
1. Build full Stage-1 combo grid from:
   - `fold_count`
   - `val_batches_per_fold`
   - `train_batches_per_fold`
2. Build leakage-safe fold windows:
   - each fold uses contiguous train window and contiguous validation window
   - validation windows move backward from `train_end`
3. Train baseline CatBoost for each required train window.
4. Save raw fold validation predictions:
   - `y_true`, `y_pred`, `prob_class_*`, `timestamp`, `batch_id`
5. Save raw prediction-batch payload per combo:
   - same schema as above
6. Save lightweight combo index/fold-window metadata.

No heavy runtime confusion/per-class table generation is performed in Stage-1.

## Leakage Constraints
Leakage guard enforced in Stage-1:
- fold train batches and fold validation batches must satisfy `batch_id <= train_end`
- prediction batch is inference-only payload generation
- prediction batch rows are not used in fold fitting or fold validation

## Stage-1 vs Standard Backtest
Stage-1 (`catboost_stage1` profile):
- uses isolated runner/evaluator
- writes Stage-1 payload artifacts under `.../stage1/`
- does not run standard final per-step training/prediction reporting path

Standard profile:
- uses `scripts/htf_backtest/catboost/runner.py`
- performs optimization + final train + prediction metrics output each step

## What Stage-1 Intentionally Does Not Do
- no online best-combo deployment decision per step
- no runtime heavy metric tables
- no standard `prediction_metrics.json` as primary artifact source

Stage-1 artifacts are designed for later offline analysis and model selection.

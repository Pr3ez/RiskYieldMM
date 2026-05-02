# HTF Stage-1 Logic (CatBoost, Isolated)

## Purpose
Stage-1 is an offline dataset-generation run profile for fold-grid analysis.  
It is not the standard Optuna/runtime model-selection path.

Primary objective:
- generate raw validation and prediction-batch payloads for every Stage-1 combo
- compute selection/quality metrics later in analysis scripts
- keep optimization leakage-safe

## Stage Split (Step-1 vs Step-2)
- Step-1:
  - module: `scripts/htf_backtest/catboost/stage1_runner.py`
  - function: `run_walk_forward_stage1_grid(...)`
  - output root: `data/htf_backtest_results/{run_id}/catboost/{tf}/{target}/batch_xxxx/stage1/`
  - responsibility: collect raw payloads for all configured combos quickly and safely.
- Step-2:
  - module: `scripts/htf_backtest/catboost/stage1_step2.py`
  - function: `run_stage1_step2_feature_pruning(...)`
  - output root: `data/htf_backtest_results/{run_id}/{output_subdir}/catboost/...`
  - responsibility: offline feature-noise pruning and baseline-vs-filtered comparisons.

Step-2 reads Step-1 artifacts but writes to a separate tree and does not overwrite Step-1 payloads.

## Entrypoints
- Stage-1 runner: `scripts/htf_backtest/catboost/stage1_runner.py`
  - `run_walk_forward_stage1_grid(...)`
- Stage-1 evaluator: `scripts/htf_backtest/catboost/stage1_optimizer.py`
  - `evaluate_stage1_grid(...)`
- Stage-1 Step-2 feature pruning:
  - `scripts/htf_backtest/catboost/stage1_step2.py`
  - `run_stage1_step2_feature_pruning(...)`
- Stage-1 analyzer (offline candidate pruning):
  - `scripts/htf_backtest/catboost/stage1_analysis.py`
  - `analyze_stage1_run(...)`
- Stage-1 reward builder (offline reward table):
  - `scripts/htf_backtest/catboost/stage1_reward.py`
  - `build_stage1_reward_table(...)`
- Stage-1 policy dataset builder (offline state/action/reward):
  - `scripts/htf_backtest/catboost/stage1_policy_dataset.py`
  - `build_stage1_policy_dataset(...)`

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
7. Save leakage-safe pre-decision context snapshot for policy-learning datasets.

No heavy runtime confusion/per-class table generation is performed in Stage-1.

## Step-2 High-Level Flow
For each unit (`timeframe/target`) and configured combo set:
1. Read Step-1 combo index, fold windows, and prediction payloads.
2. Re-score combos from prediction payloads using unit metric (`macro_f1` or `cross_direction_error`).
3. Select combo processing mode:
   - default `winner_only`: process one best combo per step
   - optional `all_combos`: process every combo per step
4. Refit baseline CatBoost on selected combo windows and compute feature importances.
5. Build combo-specific noisy-feature masks and evaluate filtered-vs-baseline prediction metrics.
6. Build one global mask across processed combos for the same unit.
7. Write Step-2 summaries, winner traces, and mask artifacts under `output_subdir` (default `stage1_step2`).

Detailed Step-2 plan: `docs/htf/stage1-step2-plan.md`.

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
- can optionally auto-prune next-run grid from previous Stage-1 artifacts
  (`stage1_pair_grid` and optional `stage1_fold_grid`)

Standard profile:
- uses `scripts/htf_backtest/catboost/runner.py`
- performs optimization + final train + prediction metrics output each step

Notebook split:
- Cell 14 = Step-1 collection only.
- Cell 15 = Step-2 pruning/evaluation only.

## What Stage-1 Intentionally Does Not Do
- no online best-combo deployment decision per step
- no runtime heavy metric tables
- no standard `prediction_metrics.json` as primary artifact source

Stage-1 artifacts are designed for later offline analysis and model selection.
They now also include explicit `action_key` and pre-decision context payloads
for autoregressive / RL optimizer-policy training.

## Offline Pipeline (Recommended Order)
1. Run isolated Stage-1 collection (`run_walk_forward_stage1_grid`).
2. Build reward table from stored payloads (`build_stage1_reward_table`).
3. Build policy dataset for sequence/policy models (`build_stage1_policy_dataset`).
4. Run candidate pruning (`analyze_stage1_run`) and reuse reduced grids in next Stage-1 run.

This keeps runtime fast and moves heavy metric logic to post-run offline steps.

## Quick Usage (Python)
```python
from scripts.htf_backtest.catboost.stage1_reward import build_stage1_reward_table
from scripts.htf_backtest.catboost.stage1_policy_dataset import build_stage1_policy_dataset
from scripts.htf_backtest.catboost.stage1_analysis import analyze_stage1_run

reward_meta = build_stage1_reward_table(
    run_id_or_path="stage1_catboost_live",
    selection_source="prediction",
)

policy_meta = build_stage1_policy_dataset(
    run_id_or_path="stage1_catboost_live",
    selection_source="prediction",
    context_lags=3,
)

candidate_meta = analyze_stage1_run(
    run_id_or_path="stage1_catboost_live",
    selection_source="prediction",
)
```

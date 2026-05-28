# HTF Stage-1 Logic (CatBoost, Isolated)

> Current scope
>
> This document describes the legacy regime/family Stage-1 analysis layer. The
> multi-asset branch already prepares per-asset HTF roots under
> `data/htf_multiasset/{asset}/`. The Stage-1 launcher can now build merged
> target/context dataset roots under `data/htf_multiasset_merged/` before
> calling the existing CatBoost walk-forward engine.

## Purpose
Stage-1 is an offline dataset-generation run profile for fold-grid analysis.  
It is not the standard Optuna/runtime model-selection path.

Primary objective:
- generate raw validation and prediction-batch payloads for every Stage-1 combo
- compute selection/quality metrics later in analysis scripts
- keep optimization leakage-safe

## Multi-Asset Assembly Layer

The launcher option `--build-merged-dataset` prepares Stage-1-compatible roots
without changing the CatBoost runner internals.

Current v1 rules:
- one prediction target asset per run
- labels come only from the target asset
- context features are exact `timestamp` joins only
- rows missing any selected context asset are dropped
- rows with null model feature values after the merge are dropped
- target feature columns are prefixed as `T_<asset>__*`
- context feature columns are prefixed as `C_<asset>__*`
- `timestamp`, `batch_id`, `bar_in_batch_norm`, and `target_4class` keep the
  existing Stage-1-compatible names
- context `target_*` label columns are never joined as features

Merged roots are written below:

```text
data/htf_multiasset_merged/{target_asset}/{context_hash}/{root_id}/features/1m/target_4class/
data/htf_multiasset_merged/{target_asset}/{context_hash}/{root_id}/labels/1m/
```

Each root also writes `manifest.json` with source paths, row counts, dropped-row
counts, schema hash, duplicate count, null-feature count, and timestamp range.
Written merged feature batches must have `duplicate_count=0` and
`null_feature_count=0`.

Merged roots can be sparse because exact context alignment can start later than
the target asset history or skip periods where any selected context asset has no
usable row. Sparse roots are valid inputs. Stage-1 keeps the original `batch_id`
for traceability, but train/validation fold windows are planned over dense
available-batch positions. Merged roots write `stage1_batch_index.parquet`, and
fold artifacts store explicit `train_batch_ids` and `val_batch_ids`.

Current local smoke status:

```text
root: 8h/B
target: BTCUSDT
context: core-ex-target
common rows: 413,652
stage1 smoke: steps_ok=1, steps_error=0
quality signal: weak smoke only, winner_accuracy=0.2667, macro_f1=0.1053
```

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
   - each fold uses contiguous available-batch train and validation windows
   - validation windows move backward from the previous available batch before
     prediction
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
- fold train batches and fold validation batches must be earlier than the
  prediction batch by dense available-batch position
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

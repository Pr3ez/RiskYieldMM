# HTF Stage-1-v2 Slice 2: Step Artifacts + Nested Selector Smoke

Date: 2026-04-20

## Scope

This slice extends the Stage-1-v2 foundation with:

1. shared selector-step execution extracted into a reusable module
2. Stage-1-v2 step artifact writers
3. parity-mode Stage-1-v2 step artifacts
4. one-root, one-step nested-selector smoke execution

## Code Changes

### New

- [stage1_selector_step.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/htf_backtest/catboost/stage1_selector_step.py)

This module now owns:

- `Stage1SelectorUnitConfig`
- `process_stage1_selector_step(...)`
- `collect_stage1_v2_step_artifacts(...)`

It is the shared callable selector execution path for:

- Stage-1-v2 nested-selector step analysis
- delegated Step-2 selector replay

### Updated

- [stage1_runner.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/htf_backtest/catboost/stage1_runner.py)
- [stage1_step2.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/htf_backtest/catboost/stage1_step2.py)

Runner changes:

- Stage-1-v2 no longer hard-fails on `execution_mode=nested_selector`
- execution units now carry `selector_unit` config
- per-step Stage-1-v2 artifacts are written after Stage-1 payload generation
- root-level Stage-1-v2 summaries/parquet outputs are emitted

Step-2 changes:

- `_process_unit_step(...)` now delegates to the shared selector callable
- state initialization includes:
  - `selected_prediction_rows_by_combo`
  - `selected_feature_masks_by_combo`

## New Stage-1-v2 Outputs

### Root level

- `stage1_v2_run_summary.json`
- `stage1_v2_progress.parquet`
- `stage1_v2_baseline_vs_selected_root.parquet`
- `stage1_v2_winner_change_summary.parquet`
- `stage1_v2_feature_importance_global.parquet`
- `stage1_v2_feature_mask_global.parquet`
- `stage1_v2_feature_stability.parquet`

### Step level

Written under each step at:

- `.../batch_xxxx/stage1_v2/`

Files:

- `stage1_v2_step_summary.json`
- `stage1_v2_combo_metrics.parquet`
- `stage1_v2_feature_importance_steps.parquet`
- `stage1_v2_selected_features.json`
- `stage1_v2_selector_fold_outputs.parquet`
- `stage1_v2_pred_batch_predictions_baseline.parquet`
- `stage1_v2_pred_batch_predictions_selected.parquet`

## Verification

### Compile

Passed:

```bash
python -m py_compile \
  scripts/htf_backtest/catboost/stage1_selector_step.py \
  scripts/htf_backtest/catboost/stage1_step2.py \
  scripts/htf_backtest/catboost/stage1_runner.py \
  scripts/analysis/htf_stage1_regime_family_walkforward.py
```

### Parity Smoke

Run:

- [stage1_catboost_8h_b_v2_smoke_parity](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_8h_b_v2_smoke_parity)

Result:

- 1 root, 1 step, success
- Stage-1 runtime about `12.8s`
- Stage-1-v2 parity step artifacts written successfully

Key files:

- [stage1_v2_run_summary.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_8h_b_v2_smoke_parity/stage1_v2_run_summary.json)
- [stage1_v2_step_summary.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_8h_b_v2_smoke_parity/catboost/1m/target_4class/batch_5669/stage1_v2/stage1_v2_step_summary.json)

### Nested Selector Smoke

Run:

- [stage1_catboost_8h_b_v2_smoke_nested](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_8h_b_v2_smoke_nested)

Result:

- 1 root, 1 step, success
- full nested selector replay for all 8 combos
- total runtime about `238.2s`
- Stage-1-v2 nested artifacts written successfully

Key files:

- [stage1_v2_run_summary.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_8h_b_v2_smoke_nested/stage1_v2_run_summary.json)
- [stage1_v2_step_summary.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_8h_b_v2_smoke_nested/catboost/1m/target_4class/batch_5669/stage1_v2/stage1_v2_step_summary.json)
- [stage1_v2_selected_features.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_8h_b_v2_smoke_nested/catboost/1m/target_4class/batch_5669/stage1_v2/stage1_v2_selected_features.json)

Nested smoke counts:

- `feature_importance_rows = 1360`
- `feature_mask_rows = 1360`
- `selection_applied_combo_count = 8`

### Step-2 Delegation Smoke

Run summary:

- [step2_run_summary.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_8h_b_v2_smoke_parity/stage1_step2_smoke_after_v2slice2/catboost/step2_run_summary.json)

Result:

- Step-2 executed successfully after delegation to shared selector callable
- smoke scope: `winner_only`, `1m`, `target_4class`, `max_steps_per_unit=1`

## Current Boundary

This slice adds reusable step execution and persistent v2 artifacts, but it does **not** yet replace the core Stage-1 winner-selection contract with selected-feature winners.

Current v2 nested behavior:

- baseline Stage-1 still decides the canonical run winner
- Stage-1-v2 nested artifacts now persist the selected-feature evidence needed for the next rollout slice


# HTF Stage-1-v2 Fixed-Policy Execution

Date: 2026-04-20

## What Was Added

Stage-1-v2 now supports a third execution mode:

- `parity`
- `nested_selector`
- `fixed_policy`

`fixed_policy` replays each combo using the root-level feature mask already built for that combo's `action_key`.

## Source Registry

The fixed-policy run does not build its own masks during the step.

Instead, for each root, it reads:

- `data/htf_backtest_results/<nested_run_id>/stage1_v2_fixed_policy_registry.json`

Example for `8h/B`:

- source nested-selector run:
  `stage1_catboost_8h_b_v2_live`
- source registry:
  `data/htf_backtest_results/stage1_catboost_8h_b_v2_live/stage1_v2_fixed_policy_registry.json`

## Run ID Convention

Fixed-policy replay uses a separate run id so it does not overwrite the nested-selector source run.

Examples:

- nested-selector: `stage1_catboost_8h_b_v2_live`
- fixed-policy: `stage1_catboost_8h_b_v2_fixed_policy_live`
- parity: `stage1_catboost_8h_b_v2_parity_live`

## Runtime Constraint

`fixed_policy` must be run with:

- `--runtime-mode routine`

Reason:

- adaptive probing/promoted combos can introduce combos that do not exist in the fixed-policy registry
- fixed-policy replay is intended to compare the stable base combo grid using fixed masks

## Single-Root Smoke Command

```bash
cd "/media/przem/linux_data/RiskYieldMM (Copy)"

PYTHONUNBUFFERED=1 PYTHONPATH=. \
/media/przem/linux_data/conda/envs/ml_env/bin/python \
scripts/analysis/htf_stage1_regime_family_walkforward.py \
  --roots 8h/B \
  --n-steps 1 \
  --resume-mode skip_completed \
  --runtime-mode routine \
  --stage1-version v2 \
  --stage1-v2-execution-mode fixed_policy
```

Smoke result:

- new run id: `stage1_catboost_8h_b_v2_fixed_policy_live`
- step completed: `batch_5669`
- fixed-policy combos applied: `8/8`

## Full Multi-Root Command

```bash
cd "/media/przem/linux_data/RiskYieldMM (Copy)"

PYTHONUNBUFFERED=1 PYTHONPATH=. \
/media/przem/linux_data/conda/envs/ml_env/bin/python \
scripts/analysis/htf_stage1_regime_family_walkforward.py \
  --roots 8h/B 8h/C 24h/B 24h/C 7d/B 7d/C \
  --n-steps 500 \
  --resume-mode skip_completed \
  --runtime-mode routine \
  --stage1-version v2 \
  --stage1-v2-execution-mode fixed_policy
```

## Available-Step-Only 8h/B Command

If you want to compare preselection only on the currently available nested-selector step window from `8h/B`, run:

```bash
cd "/media/przem/linux_data/RiskYieldMM (Copy)"

PYTHONUNBUFFERED=1 PYTHONPATH=. \
/media/przem/linux_data/conda/envs/ml_env/bin/python \
scripts/analysis/htf_stage1_regime_family_walkforward.py \
  --roots 8h/B \
  --n-steps 500 \
  --resume-mode skip_completed \
  --runtime-mode routine \
  --stage1-version v2 \
  --stage1-v2-execution-mode fixed_policy \
  --pred-batch-min 5170 \
  --pred-batch-max 5355
```

Why `--n-steps 500` is still fine here:

- the explicit batch filter reduces the eligible window to `5170..5355`
- the runner then caps `n_steps` to the filtered maximum automatically
- so this run targets exactly the available `186` completed `8h/B` steps

This command resolves to a separate run id:

- `stage1_catboost_8h_b_v2_fixed_policy_pb5170_5355_live`

## Step Artifacts

Each completed fixed-policy step writes the normal `stage1_v2` step artifact family, but with:

- `execution_mode = "fixed_policy"`
- fixed-policy registry metadata embedded in `stage1_v2_step_summary.json`
- per-combo mask metadata embedded in `stage1_v2_selected_features.json`
- selector fold rows marked with `selector_method = "fixed_policy"`

Example smoke step:

- [stage1_v2_step_summary.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_8h_b_v2_fixed_policy_live/catboost/1m/target_4class/batch_5669/stage1_v2/stage1_v2_step_summary.json)
- [stage1_v2_selected_features.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_8h_b_v2_fixed_policy_live/catboost/1m/target_4class/batch_5669/stage1_v2/stage1_v2_selected_features.json)

## Root Artifacts

The run also writes the standard Stage-1-v2 root artifacts under the new fixed-policy run directory:

- `stage1_v2_progress.parquet`
- `stage1_v2_baseline_vs_selected_root.parquet`
- `stage1_v2_winner_change_summary.parquet`
- `stage1_v2_feature_importance_global.parquet`
- `stage1_v2_feature_mask_global.parquet`
- `stage1_v2_feature_stability.parquet`
- `stage1_v2_run_summary.json`

Example:

- [run_summary.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_8h_b_v2_fixed_policy_live/run_summary.json)

## Current Purpose

This mode gives you the direct comparison path you asked for:

- same combo grid as Stage-1
- each combo replayed with its own precomputed fixed feature set
- per-step metrics preserved for every combo
- winner selection observed after feature preselection, not before

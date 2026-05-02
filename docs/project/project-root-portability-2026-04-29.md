# Project Root Portability - 2026-04-29

## Purpose

This note documents the first P0 portability pass from the deep research report.
The goal was to remove machine-local project-root assumptions from active runtime
entrypoints without rewriting historical reports, notebook outputs, or backup
files.

## Runtime Convention

Active code should resolve the repository root through:

- `scripts.project_paths.resolve_project_root(...)`
- `scripts.project_paths.ensure_project_root_on_path(...)`

Resolution order:

1. `RISKYIELDMM_PROJECT_ROOT`, when set.
2. Upward marker search from the caller path.
3. Upward marker search from the current working directory.

The marker search expects a directory containing `pyproject.toml`, `README.md`,
and `scripts/`.

Example override:

```bash
export RISKYIELDMM_PROJECT_ROOT="/path/to/RiskYieldMM"
```

## Files Updated

Shared resolver:

- `scripts/project_paths.py`
- `scripts/workflow/config.py`

Model/backtest helpers:

- `scripts/htf_backtest/catboost/utils.py`
- `scripts/htf_backtest/lightgbm/utils.py`
- `scripts/htf_backtest/catboost/stage1_reward.py`
- `scripts/htf_backtest/catboost/stage1_policy_dataset.py`
- `scripts/htf_backtest/catboost/stage1_analysis.py`
- `scripts/htf_backtest/catboost/stage1_step2.py`

Analysis and experiment entrypoints:

- `scripts/analysis/config.py`
- `scripts/analysis/htf_stage1_regime_family_walkforward.py`
- `scripts/analysis/htf_walkforward_diagnostics.py`
- `scripts/analysis/merge_htf_walkforward_diagnostics_runs.py`
- `scripts/analysis/htf_complete_batch_readiness_audit.py`
- `scripts/analysis/htf_catboost_regime_family_benchmark.py`
- `scripts/analysis/htf_helper_feature_audit.py`
- `scripts/analysis/htf_underused_feature_audit.py`
- `scripts/experiments/window_grid_search.py`
- `scripts/experiments/analyze_window_results.py`

Prediction-analysis entrypoints:

- `prediction_analysis/candidate_directional_quality_audit.py`
- `prediction_analysis/ewaf_sparse_param_sweep.py`
- `prediction_analysis/multitimeframe_causal_ensemble_benchmark.py`
- `prediction_analysis/multitimeframe_cross_target_ensemble_search.py`
- `prediction_analysis/multitimeframe_cross_target_ensemble_search_v2.py`
- `prediction_analysis/multitimeframe_direction_ensemble_analysis.py`
- `prediction_analysis/multitimeframe_subset_pruning_analysis.py`
- `prediction_analysis/multitimeframe_updown_specialist_search.py`

Exported notebook script:

- `notebooks/htf_stage1.py`

## Intentional Non-Scope

The following still contain absolute paths and should be handled separately:

- Historical docs and notebook note files that cite old artifact paths.
- Notebook output cells in `.ipynb` files.
- Any temporary local backup files, which should remain untracked.
- Older notebook/script exports not in this first active Stage-1 slice
  (`notebooks/Fetch_data.py`, `notebooks/main_wf.py`,
  `notebooks/htf_cell_14_backtest.py`, `notebooks/regime_trend_wf_tf_8h.py`).

## Follow-Up Research Needed

- Decide which notebook exports are still operational entrypoints and should be
  migrated next (`notebooks/main_wf.py`, `notebooks/Fetch_data.py`,
  `notebooks/htf_cell_14_backtest.py`, and related `.ipynb` files).
- Decide whether historical artifact-path references should be preserved as
  provenance or rewritten to relative paths.
- Audit command snippets in docs for outdated checkout paths before publishing
  reproducibility instructions.

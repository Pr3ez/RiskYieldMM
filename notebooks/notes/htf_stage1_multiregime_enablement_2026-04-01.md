# HTF Stage-1 Multiregime Enablement 2026-04-01

## Scope

Enable the real CatBoost Stage-1 walk-forward workflow for the latest HTF production roots:

- `8h/B`
- `8h/C`
- `24h/B`
- `24h/C`
- `7d/B`
- `7d/C`

using current `1m/target_4class` helper/label artifacts from the new production workflow.

## What Changed

### 1. Stage-1 config can now target non-default HTF roots

Updated:

- [scripts/htf_backtest/catboost/utils.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/htf_backtest/catboost/utils.py)

Changes:

- added `features_dir_override`
- added `labels_dir_override`
- `BaseOptimizerConfig.features_dir` now resolves override if present
- `BaseOptimizerConfig.labels_dir` now resolves override if present

### 2. Stage-1 runner now accepts root overrides

Updated:

- [scripts/htf_backtest/catboost/stage1_runner.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/htf_backtest/catboost/stage1_runner.py)

Changes:

- added `features_dir_override` and `labels_dir_override` to Stage-1 override handling
- persisted per-unit `features_dir` and `labels_dir` into:
  - `run_config.json`
  - `stage1_run_state.json`

This makes each run self-describing and prevents the root from being implicit.

### 3. Step-2 compatibility path was updated

Updated:

- [scripts/htf_backtest/catboost/stage1_step2.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/htf_backtest/catboost/stage1_step2.py)

Changes:

- added the same root override keys to Step-2 config resolution

This does not run Step-2 yet, but keeps the follow-up path compatible with the new root-aware Stage-1 runs.

### 4. Dedicated multiregime launcher added

Added:

- [scripts/analysis/htf_stage1_regime_family_walkforward.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/analysis/htf_stage1_regime_family_walkforward.py)

Behavior:

- runs one Stage-1 job per regime/family root
- keeps one batch universe per run
- reuses the earlier `1m/target_4class` Stage-1 winner triplet portfolio from `stage1_catboost_live`
- targets current live helper/label roots
- uses separate run IDs:
  - `stage1_catboost_8h_b_live`
  - `stage1_catboost_8h_c_live`
  - `stage1_catboost_24h_b_live`
  - `stage1_catboost_24h_c_live`
  - `stage1_catboost_7d_b_live`
  - `stage1_catboost_7d_c_live`

## Validation

### Compile checks

Passed with `ml_env`:

```bash
/media/przem/linux_data/conda/envs/ml_env/bin/python -m py_compile \
  scripts/htf_backtest/catboost/utils.py \
  scripts/htf_backtest/catboost/stage1_runner.py \
  scripts/htf_backtest/catboost/stage1_step2.py \
  scripts/analysis/htf_stage1_regime_family_walkforward.py
```

### Plan-only dry run

Passed:

```bash
/media/przem/linux_data/conda/envs/ml_env/bin/python \
  scripts/analysis/htf_stage1_regime_family_walkforward.py --plan-only
```

Artifacts:

- [plan_20260401_212647.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/htf_stage1_regime_family_walkforward/plan_20260401_212647.json)

Resolved triplet grid for `1m/target_4class`:

- `(2,1,3)`
- `(2,3,9)`
- `(2,1,6)`
- `(2,2,8)`
- `(2,1,5)`
- `(2,2,4)`
- `(2,2,10)`
- `(7,1,4)`

### Real smoke run

Executed:

```bash
/media/przem/linux_data/conda/envs/ml_env/bin/python \
  scripts/analysis/htf_stage1_regime_family_walkforward.py \
  --roots 8h/B \
  --n-steps 1
```

Result:

- run ID: `stage1_catboost_8h_b_live`
- `1/1` step completed successfully
- run metadata correctly points at:
  - `data/htf_with_helpers`
  - `data/htf_4class_labels`

Artifacts:

- [run_config.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_8h_b_live/run_config.json)
- [stage1_run_state.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_8h_b_live/stage1_run_state.json)
- [summary_20260401_212758.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/test_output/htf_stage1_regime_family_walkforward/summary_20260401_212758.json)

## Blocker Found And Fixed

The first full-run attempt exposed a pre-existing Stage-1 feature-selection bug:

- `get_feature_columns()` was allowing datetime/string metadata into CatBoost input
- example offending columns from current helper parquets:
  - `period_8h_start`
  - `family_period_start`
  - `family_period_end`
  - `batch_family`
  - `anchor_utc`

Observed failure:

- CatBoost fold training failed with:
  - `Cannot convert obj 2025-09-18 00:00:00 to float`

Fix:

- tightened [scripts/htf_backtest/catboost/utils.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/htf_backtest/catboost/utils.py) so `get_feature_columns()` now keeps only numeric/boolean columns and excludes target/meta columns explicitly

Validation after fix:

- metadata columns are excluded
- helper/model numeric columns remain present
- rerun smoke on clean `8h/B` now trains successfully and returns a real winner:
  - `winner=f2_v3_t9`
  - `winner_acc=0.3375`

Because the first broken `8h/B` run had already written invalid partial artifacts, it was rotated aside:

- [stage1_catboost_8h_b_live_pre_numeric_feature_fix_20260401_213253](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_8h_b_live_pre_numeric_feature_fix_20260401_213253)

## Live Run

Active full run command:

```bash
/media/przem/linux_data/conda/envs/ml_env/bin/python -u \
  scripts/analysis/htf_stage1_regime_family_walkforward.py \
  --n-steps 500 \
  --resume-mode skip_completed
```

Current observed state at launch:

- root: `8h/B`
- valid batches: `5669/5670`
- walk-forward range: prediction batches `5170..5669`
- total requested steps: `500`
- Stage-1 smoke-created run was reused/resumed correctly

Current observed state after the metadata feature fix:

- `8h/B` is actively running from the corrected code path
- the first full-run step after relaunch produced:
  - `winner=f2_v3_t9`
  - `winner_acc=0.5083`
- note: `resume_mode=skip_completed` still recomputed the already-smoked first step even though coverage reported it as complete, so there is a separate Stage-1 resume inconsistency to audit later

## Conclusion

The full walk-forward path is now structurally enabled for all six HTF roots without mixing incompatible batch universes into one run.

The key architectural change is:

- one Stage-1 run = one regime/family root = one helper root = one label root

That matches the real HTF dataset layout and avoids the invalid cross-regime batch intersection that the old shared runner shape would impose.

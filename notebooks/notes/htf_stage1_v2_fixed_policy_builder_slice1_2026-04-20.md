# HTF Stage-1-v2 Fixed-Policy Builder Slice 1

Date: 2026-04-20

## Goal

This slice implements the first usable part of the fixed-policy replay design:

1. Read completed `stage1_v2` nested-selector step artifacts from an existing root run.
2. Aggregate per-combo and per-feature behavior across completed steps.
3. Build one fixed feature policy per `action_key`.
4. Persist a root-level registry and build artifacts that later replay code can consume.

This slice does **not** yet replay steps with the fixed masks. It only builds the policy registry.

## Code Added

- [stage1_feature_policy.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/htf_backtest/catboost/stage1_feature_policy.py)
- [htf_stage1_v2_policy_replay.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/analysis/htf_stage1_v2_policy_replay.py)

## Code Updated

- [stage1_v2_contract.py](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/scripts/htf_backtest/catboost/stage1_v2_contract.py)

## What The Builder Reads

For each completed step under a root run, the builder requires:

- `batch_metadata.json`
- `stage1_v2/stage1_v2_combo_metrics.parquet`
- `stage1_v2/stage1_v2_feature_importance_steps.parquet`
- `stage1_v2/stage1_v2_selected_features.json`
- `stage1_v2/stage1_v2_step_summary.json`

If a step is missing any of those files, it is marked incomplete and excluded from policy construction.

## Policy Construction Logic

For each `action_key`, the builder computes per-feature statistics such as:

- step support
- selected-step support
- improved-step support
- overall selection rate
- improved-step selection lift
- selected-vs-not-selected accuracy lift
- selected-vs-not-selected cross-direction-error lift
- selected-step importance mean

Each feature is then bucketed into one of:

- `core_keep`
- `conditional_keep`
- `neutral`
- `avoid`

The final mask for each combo is ordered by:

1. bucket priority
2. improved-step selection lift
3. accuracy lift
4. cross-direction-error lift
5. overall selection rate
6. mean selected-step importance

The builder then keeps up to the combo-specific target mask size inferred from historical accepted/pruned mask sizes.

## Root Artifacts Written

The builder writes the following root-level artifacts:

- `stage1_v2_fixed_policy_registry.json`
- `stage1_v2_fixed_policy_build_summary.json`
- `stage1_v2_fixed_policy_build/per_combo_feature_stats.parquet`
- `stage1_v2_fixed_policy_build/per_combo_feature_stats.csv`
- `stage1_v2_fixed_policy_build/combo_policy_summary.parquet`
- `stage1_v2_fixed_policy_build/combo_policy_summary.csv`
- `stage1_v2_fixed_policy_build/final_mask_features.parquet`
- `stage1_v2_fixed_policy_build/final_mask_features.csv`

The contract version for this artifact family is:

- `2026-04-20-stage1-v2-fixed-policy-v1`

## CLI

Build a registry from an existing v2 live run:

```bash
cd "/media/przem/linux_data/RiskYieldMM (Copy)"

PYTHONPATH=. /media/przem/linux_data/conda/envs/ml_env/bin/python \
scripts/analysis/htf_stage1_v2_policy_replay.py \
  --run-id stage1_catboost_8h_b_v2_live
```

You can also point it directly at a run directory:

```bash
cd "/media/przem/linux_data/RiskYieldMM (Copy)"

PYTHONPATH=. /media/przem/linux_data/conda/envs/ml_env/bin/python \
scripts/analysis/htf_stage1_v2_policy_replay.py \
  --run-path data/htf_backtest_results/stage1_catboost_8h_b_v2_live
```

## Smoke Result

Smoke-tested against:

- [stage1_catboost_8h_b_v2_live](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_8h_b_v2_live)

Observed result:

- completed steps used: `186`
- incomplete steps excluded: `1`
- combos covered: `8`
- distinct features covered: `170`

Written artifacts:

- [stage1_v2_fixed_policy_registry.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_8h_b_v2_live/stage1_v2_fixed_policy_registry.json)
- [stage1_v2_fixed_policy_build_summary.json](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_8h_b_v2_live/stage1_v2_fixed_policy_build_summary.json)
- [combo_policy_summary.parquet](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_8h_b_v2_live/stage1_v2_fixed_policy_build/combo_policy_summary.parquet)
- [final_mask_features.parquet](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_8h_b_v2_live/stage1_v2_fixed_policy_build/final_mask_features.parquet)

The one excluded step was the interrupted tail step:

- [batch_5669](/media/przem/linux_data/RiskYieldMM%20%28Copy%29/data/htf_backtest_results/stage1_catboost_8h_b_v2_live/catboost/1m/target_4class/batch_5669)

## Next Slice

The next implementation slice should consume `stage1_v2_fixed_policy_registry.json` inside Stage-1-v2 execution so each combo can be replayed with its fixed mask and evaluated on the same step without rerunning nested feature selection.

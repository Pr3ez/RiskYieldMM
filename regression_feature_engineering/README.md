# Regression Feature Engineering

## Purpose

This workspace is the active contract for regression-optimized feature
engineering in RiskYieldMM.

## Current Status

Scaffold only. No feature formulas are implemented here yet, and no existing
HTF, TA, Stage-1, or regression target artifacts are modified by this package.

## Scope

The workflow targets the `regression_path_features_v1` feature set for
`distance_horizon_vol_v2` regression labels. The first benchmark is
`BTCUSDT 8h/B`; the full design covers core assets across root IDs `8h_b`,
`8h_c`, `24h_b`, `24h_c`, `7d_b`, and `7d_c`.

## Source Of Truth

Read the docs in this order:

1. `README.md`
2. `docs/architecture.md`
3. `docs/workflow.md`
4. `docs/data_contract.md`
5. `docs/feature_taxonomy.md`
6. `docs/htf_feature_helper_inventory.md`
7. `docs/research_feature_signal_backlog.md`
8. `docs/feature_implementation_todo.md`
9. `docs/regression_target_rollout.md`
10. `docs/zero_target_validation.md`
11. `docs/optimization_strategy.md`
12. `docs/metadata_and_lineage.md`
13. `docs/current_htf_feature_inventory.md`

`organization_example.md` is retained as reference research, not as the active
implementation contract.

## What This Does Not Decide

This workspace does not yet choose final formulas, thresholds, model
hyperparameters, or promotion criteria beyond the documented validation gates.

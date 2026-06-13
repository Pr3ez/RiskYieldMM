# Regression Feature Engineering

## Purpose

This workspace is the active contract for regression-optimized feature
engineering in RiskYieldMM.

## Current Status

This workspace has technically valid feature artifacts, but the current
`regression_path_features_v1` feature set is **not predictively promoted**.

For `BTCUSDT 8h/B`, the package materialized `2,530` model-facing `rpf_*`
features with duplicate count `0` and null feature count `0`. The current
generated root contains Phase 1 through Phase 13 families, including `180`
`rpf_chop_*` rejection/chop features, `288` `rpf_spike_*` spike/breakout
features, `162` `rpf_liq_*` liquidity/volume-pressure features, and `209`
`rpf_regime_*` regime/calendar-state features, plus `270` `rpf_conf_*`
interaction/confluence features and `144` `rpf_xasset_*` cross-asset-context
features, `144` `rpf_factor_*` deterministic factor proxies, and `30`
`rpf_seq_*` deterministic sequence-shape proxies. That proves the data
engineering path works. It does not prove the features improve prediction.

Phase 12/13 full-root materialization is complete. All `rpf_factor_*`
timeframe-prefix validations and the `rpf_seq_*` validation passed after the
validator path slug fix. These features are engineering-valid, but they are not
predictively promoted.

A 2026-06-04 scale audit found that some older materialized model-facing
features were not practically bounded. The code now enforces causal bounded
scaling for rolling z-scores and volatility-unit distance features; rerun
materialization before using the corrected contract in walk-forward.

An earlier validation-led comparison for
`target_reg_distance_up_extreme_hvol_v2` favored the old HTF/helper features:

```text
htf_only validation Spearman:            0.304247
regression_only validation Spearman:     0.059750
htf_plus_regression validation Spearman: 0.095225
```

Read `docs/current_feature_state.md` before using or extending this workspace.
It records the current artifact layout, what came from this package, what is
technically valid, and what has not worked predictively.

The active next step is **clean RPF-native staged walk-forward optimization**.
Use `python -m regression_feature_engineering.walkforward.optimize` and
`docs/clean_rpf_walkforward_reset.md` for new RPF model work. Old
`scripts/analysis/htf_stage1_regression_*` outputs are historical comparison
evidence only; they are not the RPF optimization command surface.

## Scope

The workflow targets the `regression_path_features_v1` feature set for
`distance_horizon_vol_v2` regression labels. The first benchmark is
`BTCUSDT 8h/B`; the current Phase 1/2 feature baseline now covers all core
assets across root IDs `8h_b`, `8h_c`, `24h_b`, `24h_c`, `7d_b`, and `7d_c`.

## Source Of Truth

Read the docs in this order:

1. `README.md`
2. `docs/current_feature_state.md`
3. `docs/architecture.md`
4. `docs/workflow.md`
5. `docs/data_contract.md`
6. `docs/feature_scaling_contract.md`
7. `docs/feature_taxonomy.md`
8. `docs/feature_coverage_matrix.md`
9. `docs/htf_feature_helper_inventory.md`
10. `docs/research_feature_signal_backlog.md`
11. `docs/feature_implementation_todo.md`
12. `reports/code_vs_plan_status_2026-06-02.md`
13. `docs/regression_target_rollout.md`
14. `docs/zero_target_validation.md`
15. `docs/clean_rpf_walkforward_reset.md`
16. `docs/rpf_walkforward_optimization_report.md`
17. `docs/rpf_shap_panel_selection.md`
18. `docs/rpf_binary_classification_experiment.md`
19. `docs/rpf_walkforward_research_alignment.md`
20. `docs/optimization_strategy.md`
21. `docs/metadata_and_lineage.md`
22. `docs/current_htf_feature_inventory.md`

`organization_example.md` is retained as reference research, not as the active
implementation contract.

## What This Does Not Decide

This workspace does not yet choose final formulas, thresholds, model
hyperparameters, or promotion criteria beyond the documented validation gates.

## Memory Policy

Full regression roots are large. Materialization writes by batch chunks, while
validation separates full-root safety checks from sampled signal diagnostics.
Use narrow diagnostic prefixes such as `rpf_accept_15m_` and the default
bounded sweep settings before trying any full-family or full-root experiment.
# Documentation Index

## Purpose

Define the reading order and ownership of the regression feature engineering
docs.

## Current Status

Active documentation map for `regression_path_features_v1`. The current
feature state is documented separately because technical validation and
predictive promotion are different gates.

## Scope

This index covers documentation inside `regression_feature_engineering/`.

## Source Of Truth

The active workspace is `regression_feature_engineering/README.md` plus this
docs directory. `organization_example.md` is reference material only.

## What This Does Not Decide

This index does not define formulas or model promotion rules.

## Reading Order

1. `../README.md` - workspace overview and status.
2. `current_feature_state.md` - what was built here, what validates, and what has not improved prediction.
3. `architecture.md` - system boundaries and data layers.
4. `workflow.md` - execution order from inputs to Stage-1 regression.
5. `data_contract.md` - schemas, naming, and artifact paths.
6. `feature_scaling_contract.md` - causal model-facing normalization and scale limits.
7. `feature_taxonomy.md` - feature meaning by target.
8. `feature_coverage_matrix.md` - complete feature-type coverage map.
9. `htf_feature_helper_inventory.md` - current HTF feature/helper list and regression use.
10. `research_feature_signal_backlog.md` - research-derived candidate signals for later implementation.
11. `feature_implementation_todo.md` - phase-by-phase feature implementation tracking.
12. `../reports/code_vs_plan_status_2026-06-02.md` - actual code and generated artifact coverage versus the expanded plan.
13. `regression_target_rollout.md` - target materialization coverage and full-matrix rollout commands.
14. `zero_target_validation.md` - zero target interpretation and checks.
15. `clean_rpf_walkforward_reset.md` - clean RPF-native optimizer contract and stage order.
16. `rpf_walkforward_optimization_report.md` - detailed current clean RPF backtest and optimization mechanics.
17. `rpf_shap_panel_selection.md` - experimental SHAP RFE panel selection from existing diagnostics.
18. `rpf_binary_classification_experiment.md` - first RPF-native directional classification target.
19. `rpf_walkforward_research_alignment.md` - research suggestions mapped to active RPF implementation decisions.
20. `optimization_strategy.md` - feature acceptance and model comparison.
21. `metadata_and_lineage.md` - manifests, catalogs, and reproducibility.
22. `current_htf_feature_inventory.md` - evidence from existing HTF features.

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
3. `rpf_current_experiment_summary.md` - one current map of binary/regime experiments and best completed evidence.
4. `rpf_adaptive_walkforward_research_direction.md` - current research-backed direction after ranked-signal transfer failures.
5. `rpf_binary_walkforward_audit_summary.md` - blunt summary of completed binary backtests, usable evidence, and failed branches.
6. `rpf_ranked_signal_plan.md` - active ranked-signal replacement for widening probability-threshold classifiers.
7. `rpf_dual_target_tracking.md` - active UP/DOWN tracking contract and next commands for side-symmetric router runs.
8. `rpf_binary_walkforward_process.md` - historical binary UP/DOWN run loop, evidence checkpoints, and commands.
9. `rpf_feature_evidence_panel_workflow.md` - active bridge from existing feature diagnostics to controlled candidate panels.
10. `rpf_walkforward_code_review_cleanup.md` - code review, active module map, and cleanup plan for walk-forward.
11. `architecture.md` - system boundaries and data layers.
12. `workflow.md` - execution order from inputs to Stage-1 regression.
13. `data_contract.md` - schemas, naming, and artifact paths.
14. `feature_scaling_contract.md` - causal model-facing normalization and scale limits.
15. `feature_taxonomy.md` - feature meaning by target.
16. `feature_coverage_matrix.md` - complete feature-type coverage map.
17. `htf_feature_helper_inventory.md` - current HTF feature/helper list and regression use.
18. `research_feature_signal_backlog.md` - research-derived candidate signals for later implementation.
19. `feature_implementation_todo.md` - phase-by-phase feature implementation tracking.
20. `../reports/code_vs_plan_status_2026-06-02.md` - actual code and generated artifact coverage versus the expanded plan.
21. `regression_target_rollout.md` - target materialization coverage and full-matrix rollout commands.
22. `zero_target_validation.md` - zero target interpretation and checks.
23. `clean_rpf_walkforward_reset.md` - clean RPF-native optimizer contract and stage order.
24. `rpf_walkforward_optimization_report.md` - detailed current clean RPF backtest and optimization mechanics.
25. `rpf_shap_panel_selection.md` - experimental SHAP RFE panel selection from existing diagnostics.
26. `rpf_binary_classification_experiment.md` - RPF-native UP/DOWN `2x` directional classification targets and objective sweeps.
27. `rpf_binary_prediction_pipeline_contract.md` - causal labeled-row, ElasticNet, CNN-embedding, CatBoost, and stability-gate contract.
28. `rpf_cnn_feature_diagnostic.md` - post-hoc evidence for which RPF families/timeframes are worth feeding into a causal CNN sequence branch.
29. `rpf_overfit_control_protocol.md` - validation/threshold/tuning/holdout protocol for stable prediction research.
30. `rpf_regime_gated_prediction_plan.md` - historical/deferred plan for stable regime-gated UP/DOWN prediction.
31. `rpf_regime_gate_implementation_todo.md` - implementation tracker for regime-gate commands, artifacts, and acceptance status.
32. `rpf_signal_bank_batch_selection.md` - historical/deferred causal clean-signal batch selection.
33. `rpf_separate_decision_banks.md` - historical/deferred target-event and classifier-trust bank planning.
34. `rpf_walkforward_research_alignment.md` - research suggestions mapped to active RPF implementation decisions.
35. `optimization_strategy.md` - feature acceptance and model comparison.
36. `metadata_and_lineage.md` - manifests, catalogs, and reproducibility.
37. `current_htf_feature_inventory.md` - evidence from existing HTF features.
38. `rpf_ema_regime_batch_selection.md` - abandoned active path; historical EMA200 train/validation-bank reference only.

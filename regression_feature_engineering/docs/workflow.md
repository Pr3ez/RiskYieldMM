# Regression Feature Workflow

## Purpose

Describe the intended step-by-step workflow for regression feature production.

## Current Status

Planned workflow only. No feature materializer exists in this workspace yet.

## Scope

The workflow targets `regression_path_features_v1` for
`distance_horizon_vol_v2`.

## Source Of Truth

- Architecture: `architecture.md`
- Data contract: `data_contract.md`
- Implementation TODO: `feature_implementation_todo.md`
- Optimization: `optimization_strategy.md`

## What This Does Not Decide

This document does not choose feature formulas or final CatBoost parameters.

## Workflow Steps

1. Materialize `distance_horizon_vol_v2` labels for selected assets and roots.
2. Validate generated target roots before feature optimization.
3. Load canonical local inputs for one asset/root.
4. Load matching `distance_horizon_vol_v2` labels and diagnostics.
5. Run zero-target validation before feature optimization.
6. Build causal candidate features by family:
   - volatility state;
   - structural room;
   - acceptance and persistence;
   - spike and breakout;
   - rejection and chop;
   - cross-asset context.
7. Validate feature quality and temporal safety.
8. Write Silver regression features with a manifest and feature catalog.
9. Assemble Gold regression features for Stage-1 exact timestamp joins.
10. Run target-specific feature selection inside walk-forward training only.
11. Compare HTF-only, regression-only, and HTF-plus-regression feature sets.
12. Promote only after target-specific stability and tail coverage improve.

The full rollout repeats the same workflow for each core asset and each root ID.
Target materialization and validation details are tracked in
`regression_target_rollout.md`.
Feature implementation status is tracked in `feature_implementation_todo.md`.

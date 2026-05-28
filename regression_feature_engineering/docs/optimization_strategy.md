# Regression Feature Optimization Strategy

## Purpose

Define how future regression features should be accepted, rejected, and compared.

## Current Status

Design scaffold only. Existing `target_specific_v1` walk-forward policy remains
the current runner-side selection policy.

## Scope

Applies to `regression_path_features_v1` and `distance_horizon_vol_v2`.

## Source Of Truth

- Current runner: `scripts/analysis/htf_stage1_regression_walkforward.py`
- Feature taxonomy: `feature_taxonomy.md`
- Feature implementation TODO: `feature_implementation_todo.md`

## What This Does Not Decide

This document does not choose final CatBoost hyperparameters.

## Comparison Sets

Every benchmark should compare:

- current HTF-only features;
- regression-path-only features;
- HTF plus regression-path features.

## Primary Evidence

Features are useful when they improve:

- Spearman rank correlation;
- high-distance quantile separation;
- prediction p95 coverage versus target p95;
- MAE/RMSE without materially worsening tail ranking;
- chronological stability across walk-forward steps.

## Rejection Rules

Reject or quarantine features that are:

- nonfinite or null-heavy;
- constant or near-constant;
- raw unscaled OHLCV;
- label or future diagnostics;
- duplicated or near-duplicated without added evidence;
- strong in-sample but unstable across chronological windows.

Promotion starts with `BTCUSDT 8h/B`, then expands to all core assets and all
six root IDs only after stable evidence.

## Full-Matrix Optimization Order

After `distance_horizon_vol_v2` labels exist for all core assets and root IDs,
feature optimization should be matrix-aware:

- evaluate all four target columns for the same asset/root together;
- keep shared causal formulas across assets and roots;
- let the walk-forward runner select target-specific subsets using train rows
  only;
- compare feature families by ablation before promotion;
- reject features that improve one target while consistently damaging the
  opposite-direction target.

This keeps the workflow simple enough to maintain while still letting each
regression target use the features that fit its path-shape objective.

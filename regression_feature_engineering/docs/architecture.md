# Regression Feature Architecture

## Purpose

Define the separate regression feature workflow that will later generate
`regression_path_features_v1`.

## Current Status

Design scaffold only. Existing HTF, TA, Stage-1, and regression target scripts
are unchanged.

## Scope

The design covers core assets, root IDs `8h_b`, `8h_c`, `24h_b`, `24h_c`,
`7d_b`, `7d_c`, and the `distance_horizon_vol_v2` regression targets.

## Source Of Truth

- Config: `regression_feature_engineering/configs/regression_feature_engineering_v1.json`
- Data contract: `regression_feature_engineering/docs/data_contract.md`
- Feature taxonomy: `regression_feature_engineering/docs/feature_taxonomy.md`

## What This Does Not Decide

This document does not promote formulas or change model training defaults.

## System Shape

The workflow is intentionally separate from `notebooks/htf_pythonscript.py`.
It reads existing local artifacts and writes new regression-specific feature
artifacts only after validation gates are satisfied.

Layer responsibilities:

- **Input layer:** canonical OHLCV, TA raw/compact flags, existing HTF/helper
  features, and `distance_horizon_vol_v2` labels.
- **Silver regression layer:** causal per-asset path-shape features aligned to
  `1m` timestamps.
- **Gold regression layer:** root/family-ready feature batches for Stage-1
  regression, with manifests and feature catalog.
- **Validation layer:** zero-target checks, feature quality, temporal safety,
  and target-relationship diagnostics.

The first benchmark is `BTCUSDT 8h/B`. Full rollout is core assets times six
roots after the benchmark passes.


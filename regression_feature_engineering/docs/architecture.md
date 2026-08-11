# Regression Feature Architecture

## Purpose

Define the separate regression feature workflow that will later generate
`regression_path_features_v1`.

## Current Status

Phase 1 through Phase 13 are implemented, materialized, and
engineering-validated on `BTCUSDT 8h/B`. Phase 12 deterministic factor proxies
and Phase 13 deterministic sequence-shape proxies passed prefix validation but
are not predictively promoted. The Stage-1 regression runner can compare
HTF-only, regression-only, and HTF-plus-regression feature sources with
fold-local strict feature selection. Existing HTF, TA, Stage-1 classification,
and regression target artifacts remain unchanged unless their explicit commands
are run.

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

The first benchmark was `BTCUSDT 8h/B`. The current Phase 1/2 rollout covers
core assets times six roots, with one independent feature root and manifest per
asset/root. Phase 3 through Phase 13 are currently materialized and
engineering-validated for `BTCUSDT 8h/B`. Promotion still requires
walk-forward ablation after the static feature surface validates.

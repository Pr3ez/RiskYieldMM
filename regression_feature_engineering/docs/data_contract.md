# Regression Feature Data Contract

## Purpose

Define naming, input/output roots, and model-facing safety rules.

## Current Status

Contract scaffold only. The output root does not need to exist until feature
materialization is implemented.

## Scope

Applies to `regression_path_features_v1` and `distance_horizon_vol_v2`.

## Source Of Truth

- Config: `../configs/regression_feature_engineering_v1.json`
- Existing labels: `data/htf_multiasset/{asset}/{layout_label_root}_reg_distance_horizon_vol_v2/1m/`
- Target rollout: `regression_target_rollout.md`

## What This Does Not Decide

This document does not define formulas or choose which features pass selection.

## Canonical Names

- Feature set: `regression_path_features_v1`
- Target variant: `distance_horizon_vol_v2`
- First benchmark: `BTCUSDT 8h/B`
- Root IDs: `8h_b`, `8h_c`, `24h_b`, `24h_c`, `7d_b`, `7d_c`

Canonical output root:

```text
data/htf_multiasset/{asset}/regression_path_features_v1/{root_id}/1m/
```

## Target Columns

```text
target_reg_distance_up_extreme_hvol_v2
target_reg_distance_up_mean_high_hvol_v2
target_reg_distance_down_mean_low_hvol_v2
target_reg_distance_down_extreme_hvol_v2
```

## Target Matrix

The full target matrix is:

```text
8 core assets x 6 root IDs x 4 target columns = 192 target series
```

`distance_horizon_vol_v2` targets are generated beside each root's existing
Stage-1 label root. Current local coverage and rollout commands are documented
in `regression_target_rollout.md`.

## Required Output Columns

Every future batch must include:

- `timestamp`
- `batch_id`
- `asset_id`
- `root_id`
- `feature_set`
- model-facing feature columns

Model-facing feature columns must be numeric, finite, causal, and free of label
or future diagnostics.

## Blocked Model-Facing Inputs

Gold regression features must exclude raw unscaled OHLCV and any column matching
target, `tb_`, `future`, `label_window`, or diagnostic semantics.

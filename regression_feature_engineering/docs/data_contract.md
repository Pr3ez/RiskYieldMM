# Regression Feature Data Contract

## Purpose

Define naming, input/output roots, and model-facing safety rules.

## Current Status

Contract with Phase 1-9 materialization support. The output root is written
only when `regression_feature_engineering.materialize_features` is run. The
current full `BTCUSDT 8h/B` root includes foundation alignment diagnostics plus
`rpf_vol_`, `rpf_room_`, `rpf_accept_`, `rpf_mem_`, `rpf_chop_`, `rpf_spike_`,
`rpf_liq_`, and `rpf_regime_` model-facing features.

## Scope

Applies to `regression_path_features_v1` and `distance_horizon_vol_v2`.

## Source Of Truth

- Config: `../configs/regression_feature_engineering_v1.json`
- Existing labels: `data/htf_multiasset/{asset}/{layout_label_root}_reg_distance_horizon_vol_v2/1m/`
- Target rollout: `regression_target_rollout.md`
- Scaling contract: `feature_scaling_contract.md`

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
target_reg_direction_extreme_up_share_hvol_v2
target_reg_direction_mean_up_share_hvol_v2
```

The two `target_reg_direction_*_up_share_hvol_v2` columns are bounded
directional-share labels. `0.0` means the corresponding future path was fully
downside-dominant, `0.5` means balanced or flat, and `1.0` means fully
upside-dominant.

## Target Matrix

The full target matrix is:

```text
8 core assets x 6 root IDs x 6 target columns = 288 target series
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

Model-facing features must also obey the causal scaling contract:

- no full-dataset fitted scaler;
- no future-aware quantile or rank transform;
- rolling normalization uses prior rows only;
- raw unbounded volatility-unit and z-score values are not model-facing;
- positive volatility-unit distances are fixed-compressed to `[0,1]`;
- signed volatility-unit distances are fixed-compressed to `[-1,1]`;
- rolling z-scores are clipped to a fixed finite range.

Generated sidecar files:

- `manifest.json`
- `feature_catalog.json`

Each asset/root is independent. Tuning and validation must reference the
specific root path, manifest, and feature catalog for that asset/root.

Phase 1 diagnostic columns use `rpf_align_` and are listed in the manifest as
diagnostics, not model-facing feature columns. Phase 2 model features use
`rpf_vol_`. Phase 3 structural-room model features use `rpf_room_`. Phase 4
acceptance/persistence model features use `rpf_accept_`. Phase 5 temporal
memory features use `rpf_mem_`. Phase 6 rejection/chop model features use
`rpf_chop_`. Phase 7 spike/breakout model features use `rpf_spike_`.
Phase 8 liquidity/volume-pressure model features use `rpf_liq_`.
Phase 9 regime/calendar-state model features use `rpf_regime_`.

Remaining planned model-facing prefixes:

- `rpf_conf_`: interaction and confluence features;
- `rpf_xasset_`: cross-asset relative context;
- `rpf_factor_`: deterministic factor/anomaly proxy context derived from
  causal component features;
- `rpf_seq_`: deterministic multi-timeframe sequence-shape proxy context
  derived from causal factor proxies.

## Blocked Model-Facing Inputs

Gold regression features must exclude raw unscaled OHLCV and any column matching
target, `tb_`, `future`, `label_window`, or diagnostic semantics.

## Stage-1 Walk-Forward Visibility

The regression walk-forward runner can currently compare three feature-source
modes:

```text
htf_only
regression_only
htf_plus_regression
```

In v1, `regression_only` and `htf_plus_regression` join the target asset's
`regression_path_features_v1` root by exact `timestamp,batch_id`. Context-asset
regression-path features are not joined yet; existing HTF merged context
features remain available through `htf_only` and `htf_plus_regression`.

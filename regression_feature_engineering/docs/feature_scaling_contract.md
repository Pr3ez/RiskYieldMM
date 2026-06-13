# RPF Feature Scaling Contract

## Purpose

Define how `regression_path_features_v1` model-facing features are normalized
without look-ahead bias.

## Current Status

Active contract after the 2026-06-04 scale audit. Model-facing RPF features
must be finite and causally bounded before they are listed in
`manifest.json` `feature_columns`.

## Scope

Applies to static RPF materialization and clean RPF walk-forward use for
`distance_horizon_vol_v2` targets.

## Source Of Truth

- Safe math helpers: `regression_feature_engineering/core/math.py`
- Feature formulas: `regression_feature_engineering/features/`
- Manifest writer: `regression_feature_engineering/materialize_features.py`
- Scale audit artifact:
  `test_output/rpf_feature_scale_audit/btcusdt_8h_b_recent200_feature_scale_audit.parquet`

## What This Does Not Decide

This document does not choose final feature families or CatBoost parameters.
It only defines the model-facing scaling policy.

## Scaling Rules

RPF does not use a global full-dataset scaler. Any normalization that needs
state must be computed from current or prior rows only.

Allowed model-facing normalization patterns:

- fixed bounded ratios such as `[0,1]` or `[-1,1]`;
- prior rolling z-scores clipped to a fixed range;
- prior rolling rank or min/max position;
- percent changes or relative ratios with finite defaults and fixed clipping
  when needed;
- fixed monotonic compression of volatility-unit distances.

Blocked model-facing patterns:

- global mean/std fit across the full dataset;
- quantile/rank transforms fit using future rows;
- raw unbounded volatility-unit distance columns;
- raw unbounded rolling z-scores;
- temporal-memory transforms fed by unbounded source features.

## Fixed Causal Transforms

Rolling z-scores are clipped:

```text
z_clipped = clip(z, -8, 8)
```

Positive volatility-unit magnitudes are compressed:

```text
x_bounded = x / (x + 8), for x >= 0
```

Signed volatility-unit values are compressed:

```text
x_bounded = x / (abs(x) + 8)
```

These transforms are deterministic. They do not need training data, validation
data, prediction data, or future rows.

## Why This Matters

The scale audit found that a tiny rolling denominator could produce volatility
z-scores in the millions, and temporal-memory EWM/residual features propagated
those values. That violates the RPF all-manifest model contract and can make
CatBoost split conservatively around a few extreme columns.

The corrected contract keeps the semantic ordering while preventing one
feature family from dominating due to scale alone.

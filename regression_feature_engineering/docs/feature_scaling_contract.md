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

This document does not choose final feature families, CatBoost parameters, or
binary decision thresholds. It only defines the model-facing scaling policy.

## Scaling Rules

RPF materialization does not use a global full-dataset scaler. Any
materialized normalization that needs state must be computed from current or
prior rows only.

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

## Walk-Forward Selector Scalers

Fitted statistical scalers are allowed only inside walk-forward folds for
feature selection. They must not be written into the static RPF feature root
and they must not become the final prediction model boundary.

For each fold:

```text
Train | Validation | Prediction
```

Validation model feature selection:

```text
selector_scaler.fit(X_train)
X_train_scaled = selector_scaler.transform(X_train)
elasticnet_selector.fit(X_train_scaled, y_train)
validation_selected_features = nonzero coefficient features
```

Validation model training and scoring:

```text
X_train_scaled = selector_scaler.transform(X_train)
X_val_scaled = selector_scaler.transform(X_val)

X_train_selected_scaled = X_train_scaled[:, validation_selected_feature_indexes]
X_val_selected_scaled = X_val_scaled[:, validation_selected_feature_indexes]

CatBoost.fit(X_train_selected_scaled, y_train, eval_set=X_val_selected_scaled)
validation_score = CatBoost.predict_proba(X_val_selected_scaled)
```

Prediction model refit after validation decisions are fixed:

```text
final_selector_scaler.fit(X_train_val)
X_train_val_scaled = final_selector_scaler.transform(X_train_val)
prediction_selected_features = validation_selected_features

X_pred_scaled = final_selector_scaler.transform(X_pred)
X_train_val_selected_scaled = X_train_val_scaled[:, validation_selected_feature_indexes]
X_pred_selected_scaled = X_pred_scaled[:, validation_selected_feature_indexes]

final_CatBoost.fit(X_train_val_selected_scaled, y_train_val)
prediction_score = final_CatBoost.predict_proba(X_pred_selected_scaled)
```

The active default is `--selector-refit-mode validation_mask`: validation
selects the feature mask and the final refit keeps that mask. This keeps the
threshold calibrated on validation probabilities tied to the same columns used
for prediction. `--selector-refit-mode train_val_reselect` exists only for
diagnostics because it reruns ElasticNet after threshold calibration and can
change the model boundary.

Validation rows may be used only after they have served their validation role:
early stopping, best iteration, threshold selection, and train+validation
refit for the next held-out prediction batch. Prediction rows never fit or
update a scaler, never select features, and never update the selected feature
list for that fold. CatBoost remains the final prediction model.

The active command shape is `feature_policy=elasticnet_logistic_v1` with
`model_family=catboost`. ElasticNet is used only to rank/select features from
train rows; CatBoost receives the selected train-standardized RPF columns and
makes all validation and prediction probabilities.

For practical runtimes, `elasticnet_logistic_v1` can prefilter the ElasticNet
candidate set with train-only standardized class-separation scores. This
prefilter is fit inside the same fold boundary as the scaler and selector:
train rows may rank candidates, validation rows may not, and prediction rows
may not.

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

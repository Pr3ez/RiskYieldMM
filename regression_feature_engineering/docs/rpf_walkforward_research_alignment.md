# RPF Walk-Forward Research Alignment

## Purpose

Compare `research/rpfwalkforwardsuggestions.md` with the clean RPF-native
walk-forward implementation and define which ideas are active now, deferred, or
out of scope for the current RPF pass.

## Current Status

The clean RPF runner is the active optimization path. It uses RPF-only features,
exact label joins, frozen sparse windows, CatBoost RMSE training, Optuna
validation-RMSE selection, and fixed all-manifest features by default.

## Scope

This document covers `regression_path_features_v1`,
`distance_horizon_vol_v2`, and the first clean target
`target_reg_direction_extreme_up_share_hvol_v2`.

## Source Of Truth

- Runner: `regression_feature_engineering/walkforward/`
- Suggestions: `regression_feature_engineering/research/rpfwalkforwardsuggestions.md`
- Current mechanics: `rpf_walkforward_optimization_report.md`
- Optimization rules: `optimization_strategy.md`

## What This Does Not Decide

This document does not promote a model, choose a final feature family, or add
per-feature selection.

## Alignment Matrix

| Suggestion | Current RPF Status | Decision |
|---|---|---|
| Preserve temporal order | implemented | Sparse windows are chronological and replayed from `frozen_windows.parquet`. |
| Rolling walk-forward | implemented | Current windows are fixed-lookback rolling windows. |
| Expanding windows | deferred | Add only after rolling RMSE baseline is stable. |
| Purging / embargo | partially implemented | `embargo_batches` exists; readiness now validates label-window overlap from label metadata. |
| Nested CV | deferred | Too expensive for first RPF baseline; staged Optuna is used instead. |
| CPCV | deferred | Keep as research-only until simple RPF baseline works. |
| RMSE model selection | implemented | CatBoost and Optuna both use validation RMSE. |
| Trading/PnL metrics | deferred | Future promotion diagnostics, not current Optuna objective. |
| CatBoost feature selection / SHAP | deferred | Not active until full all-manifest RPF and family ablations are evaluated. |
| Feature stability | partially implemented | Family-level ablation is supported; per-feature stability is deferred. |
| CatBoost `has_time=True` | implemented | Model config keeps `has_time=true`. |
| Border/sampling hyperparameter search | implemented | `sampling` stage covers bootstrap, subsample, random strength, and border count. |
| Per-window diagnostics | implemented | Runs write `window_metrics.parquet`. |

## Active Optimization Contract

- RPF features are loaded directly from the per-asset feature root.
- Model features come only from manifest `feature_columns`.
- Diagnostic `rpf_align_*` columns are not model features.
- Labels are exact-joined on `timestamp,batch_id`.
- Valid rows require `target_reg_distance_valid_v2=true`.
- Readiness writes `label_window_index.parquet` and fails if train labels
  overlap validation/prediction windows.
- Optuna minimizes validation RMSE. Spearman, p95 coverage, tail RMSE,
  direction accuracy, and calibration remain diagnostics.
- Default `feature_ablation=all` uses every model-facing RPF feature.

## Feature Optimization Bridge

Feature optimization is fixed-family ablation, not per-feature selection:

```text
all
only_volatility_state
minus_volatility_state
group_volatility_state+structural_room
```

Promotion path:

1. Run all manifest features.
2. Run one-family and minus-family ablations.
3. Select candidate families by validation RMSE.
4. Confirm no collapse in prediction diagnostics.
5. Defer CatBoost `select_features` / SHAP until family evidence is useful.

## External References

- CatBoost training parameters and `eval_metric`:
  https://catboost.ai/docs/en/references/training-parameters/
- CatBoost `select_features`:
  https://catboost.ai/docs/en/concepts/python-reference_catboost_select_features
- scikit-learn time-series split gap:
  https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html
- Optuna study direction:
  https://optuna.readthedocs.io/en/stable/_modules/optuna/study/study.html

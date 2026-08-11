# RPF Ranked Signal Report

## Scope

- `asset`: `BTCUSDT`
- `root`: `8h/B`
- `side`: `up`

## Best Trial

- `trial_number`: `0`
- `status`: `error`
- `objective_value`: `-1e+09`
- `train_batches`: `20`
- `val_batches`: `5`
- `sequence_mode`: `none`
- `rank_loss`: `YetiRank`
- `selected_feature_count_mean`: `-`
- `prediction_precision`: `-`
- `prediction_precision_lift`: `-`
- `prediction_recall`: `-`
- `prediction_false_positive_rate`: `-`
- `prediction_false_discovery_rate`: `-`
- `prediction_active_window_rate`: `-`
- `prediction_zero_signal_window_rate`: `-`
- `prediction_high_target_window_capture_rate`: `-`
- `prediction_missed_high_target_window_rate`: `-`
- `prediction_decision_cost_per_row`: `-`
- `trial_config_json`: `{"decision": {"fn_cost": 1.0, "fp_cost": 5.0, "high_false_positive_rate_threshold": 0.3, "high_target_positive_rate_threshold": 0.2, "max_signals_per_batch": 5, "threshold_quantile": 0.95}, "elasticnet": {"alpha": 0.01, "coef_eps": 1e-08, "l1_ratio": 0.5, "max_features": 20, "max_iter": 2000, "min_features": 5, "prefilter_features": 80, "tol": 0.001}, "model": {"depth": 2, "early_stopping_rounds": 100, "iterations": 10, "l2_leaf_reg": 30.0, "learning_rate": 0.03, "od_wait": 100, "random_strength": 1.0, "rank_loss": "YetiRank"}, "sequence": {"cnn_batch_size": 512, "cnn_conv_channels": 16, "cnn_device": "cpu", "cnn_embedding_dim": 8, "cnn_epochs": 1, "cnn_kernel_size": 3, "cnn_max_train_rows": 8000, "mode": "none", "n_kernels": 128, "seed": 42, "sequence_length": 16}, "train_batches": 20, "val_batches": 5}`
- `error_type`: `TypeError`
- `error_message`: `float() argument must be a string or a real number, not 'NoneType'`
- `error_traceback`: `Traceback (most recent call last):
  File "/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/regression_feature_engineering/walkforward/rank_signal.py", line 215, in objective
    payload = run_rank_windows(
              ^^^^^^^^^^^^^^^^^
  File "/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/regression_feature_engineering/walkforward/rank_signal.py", line 420, in run_rank_windows
    window_row = window_metric_row(
                 ^^^^^^^^^^^^^^^^^^
  File "/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/regression_feature_engineering/walkforward/rank_signal.py", line 1014, in window_metric_row
    row = simple_window_metric_row(
          ^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/regression_feature_engineering/walkforward/rank_signal.py", line 1050, in simple_window_metric_row
    metrics = binary_decision_metrics(y_binary, decision, fp_cost=fp_cost, fn_cost=fn_cost)
              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/regression_feature_engineering/walkforward/rank_signal.py", line 1097, in binary_decision_metrics
    "precision_lift": safe_div(precision, base) if base > 0 else None,
                      ^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/run/media/przem/linux_data/risk_yield_multi-asset_dataset/RiskYieldMM/regression_feature_engineering/walkforward/rank_signal.py", line 1507, in safe_div
    return None if float(den) == 0.0 else float(num) / float(den)
                                          ^^^^^^^^^^
TypeError: float() argument must be a string or a real number, not 'NoneType'
`
- `optuna_params_json`: `{"depth": 2, "elasticnet_alpha": 0.01, "elasticnet_coef_eps": 1e-08, "elasticnet_l1_ratio": 0.5, "elasticnet_max_features": 20, "elasticnet_prefilter_features": 80, "iterations": 10, "l2_leaf_reg": 30.0, "learning_rate": 0.03, "max_signals_per_batch": 5, "random_strength": 1.0, "rank_loss": "YetiRank", "threshold_quantile": 0.95, "train_batches": 20, "val_batches": 5}`

## Holdout

- `status`: `skipped:no_holdout_windows`
- `objective_value`: `-`
- `prediction_metrics`: `{}`

## Decision Contract

- CatBoostRanker learns continuous up/down relevance grouped by batch_id.
- Prediction decisions use a validation-calibrated threshold and causal timestamp-order signal budget.
- Full prediction-batch top-k sorting is not used for live decisions.

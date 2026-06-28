# RPF Ranked Signal Report

## Scope

- `asset`: `BTCUSDT`
- `root`: `8h/B`
- `side`: `up`

## Best Trial

- `trial_number`: `4`
- `status`: `ok`
- `objective_value`: `0.116985`
- `train_batches`: `40`
- `val_batches`: `5`
- `sequence_mode`: `causal_rocket_v1`
- `rank_loss`: `YetiRank`
- `selected_feature_count_mean`: `20`
- `prediction_precision`: `0.435294`
- `prediction_precision_lift`: `0.931526`
- `prediction_recall`: `0.0164958`
- `prediction_false_positive_rate`: `0.018772`
- `prediction_false_discovery_rate`: `0.564706`
- `prediction_active_window_rate`: `0.85`
- `prediction_zero_signal_window_rate`: `0.15`
- `prediction_high_target_window_capture_rate`: `0.75`
- `prediction_missed_high_target_window_rate`: `0.25`
- `prediction_decision_cost_per_row`: `0.509583`
- `trial_config_json`: `{"decision": {"fn_cost": 1.0, "fp_cost": 5.0, "high_false_positive_rate_threshold": 0.3, "high_target_positive_rate_threshold": 0.2, "max_signals_per_batch": 5, "threshold_quantile": 0.9}, "elasticnet": {"alpha": 0.01, "coef_eps": 1e-08, "l1_ratio": 0.5, "max_features": 20, "max_iter": 2000, "min_features": 5, "prefilter_features": 160, "tol": 0.001}, "model": {"depth": 2, "early_stopping_rounds": 100, "iterations": 50, "l2_leaf_reg": 100.0, "learning_rate": 0.01, "od_wait": 100, "random_strength": 1.0, "rank_loss": "YetiRank"}, "sequence": {"cnn_batch_size": 512, "cnn_conv_channels": 16, "cnn_device": "cpu", "cnn_embedding_dim": 8, "cnn_epochs": 1, "cnn_kernel_size": 3, "cnn_max_train_rows": 8000, "mode": "causal_rocket_v1", "n_kernels": 128, "seed": 42, "sequence_length": 16}, "train_batches": 40, "val_batches": 5}`
- `error_type`: `-`
- `error_message`: `-`
- `error_traceback`: `-`
- `optuna_params_json`: `{"depth": 2, "elasticnet_alpha": 0.01, "elasticnet_coef_eps": 1e-08, "elasticnet_l1_ratio": 0.5, "elasticnet_max_features": 20, "elasticnet_prefilter_features": 160, "iterations": 50, "l2_leaf_reg": 100.0, "learning_rate": 0.01, "max_signals_per_batch": 5, "random_strength": 1.0, "rank_loss": "YetiRank", "rocket_kernels": 128, "sequence_length": 16, "threshold_quantile": 0.9, "train_batches": 40, "val_batches": 5}`

## Holdout

- `status`: `ok`
- `objective_value`: `0.69265`
- `prediction_metrics`: `{'rows': 2400, 'positive_count': 1226, 'negative_count': 1174, 'predicted_positive_count': 37, 'true_positive_count': 21, 'false_positive_count': 16, 'false_negative_count': 1205, 'true_negative_count': 1158, 'precision': 0.5675675675675675, 'recall': 0.017128874388254486, 'false_positive_rate': 0.013628620102214651, 'false_discovery_rate': 0.43243243243243246, 'predicted_positive_rate': 0.015416666666666667, 'base_positive_rate': 0.5108333333333334, 'precision_lift': 1.111062122481372, 'decision_cost': 1285.0, 'decision_cost_per_row': 0.5354166666666667, 'decision_cost_per_signal': 34.729729729729726, 'active_window_rate': 0.9, 'zero_signal_window_rate': 0.09999999999999998, 'high_target_window_count': 7, 'high_target_window_capture_rate': 0.7142857142857143, 'missed_high_target_window_rate': 0.2857142857142857, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 20.0, 'ranked_signal_quality': 0.6926503067388058}`

## Decision Contract

- CatBoostRanker learns continuous up/down relevance grouped by batch_id.
- Prediction decisions use a validation-calibrated threshold and causal timestamp-order signal budget.
- Full prediction-batch top-k sorting is not used for live decisions.

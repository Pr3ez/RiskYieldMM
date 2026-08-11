# RPF Ranked Signal Report

## Scope

- `asset`: `BTCUSDT`
- `root`: `8h/B`
- `side`: `up`

## Best Trial

- `trial_number`: `3`
- `status`: `ok`
- `objective_value`: `0.205408`
- `train_batches`: `40`
- `val_batches`: `5`
- `sequence_mode`: `causal_rocket_v1`
- `rank_loss`: `YetiRank`
- `selected_feature_count_mean`: `20`
- `prediction_precision`: `0.5`
- `prediction_precision_lift`: `1.07`
- `prediction_recall`: `0.00356665`
- `prediction_false_positive_rate`: `0.00312867`
- `prediction_false_discovery_rate`: `0.5`
- `prediction_active_window_rate`: `0.8`
- `prediction_zero_signal_window_rate`: `0.2`
- `prediction_high_target_window_capture_rate`: `0.666667`
- `prediction_missed_high_target_window_rate`: `0.333333`
- `prediction_decision_cost_per_row`: `0.473958`
- `trial_config_json`: `{"decision": {"fn_cost": 1.0, "fp_cost": 5.0, "high_false_positive_rate_threshold": 0.3, "high_target_positive_rate_threshold": 0.2, "max_signals_per_batch": 1, "threshold_quantile": 0.95}, "elasticnet": {"alpha": 0.01, "coef_eps": 1e-08, "l1_ratio": 0.5, "max_features": 20, "max_iter": 2000, "min_features": 5, "prefilter_features": 160, "tol": 0.001}, "model": {"depth": 2, "early_stopping_rounds": 100, "iterations": 50, "l2_leaf_reg": 100.0, "learning_rate": 0.01, "od_wait": 100, "random_strength": 1.0, "rank_loss": "YetiRank"}, "sequence": {"cnn_batch_size": 512, "cnn_conv_channels": 16, "cnn_device": "cpu", "cnn_embedding_dim": 8, "cnn_epochs": 1, "cnn_kernel_size": 3, "cnn_max_train_rows": 8000, "mode": "causal_rocket_v1", "n_kernels": 128, "seed": 42, "sequence_length": 16}, "train_batches": 40, "val_batches": 5}`
- `error_type`: `-`
- `error_message`: `-`
- `error_traceback`: `-`
- `optuna_params_json`: `{"depth": 2, "elasticnet_alpha": 0.01, "elasticnet_coef_eps": 1e-08, "elasticnet_l1_ratio": 0.5, "elasticnet_max_features": 20, "elasticnet_prefilter_features": 160, "iterations": 50, "l2_leaf_reg": 100.0, "learning_rate": 0.01, "max_signals_per_batch": 1, "random_strength": 1.0, "rank_loss": "YetiRank", "rocket_kernels": 128, "sequence_length": 16, "threshold_quantile": 0.95, "train_batches": 40, "val_batches": 5}`

## Holdout

- `status`: `ok`
- `objective_value`: `0.38702`
- `prediction_metrics`: `{'rows': 2400, 'positive_count': 1226, 'negative_count': 1174, 'predicted_positive_count': 9, 'true_positive_count': 5, 'false_positive_count': 4, 'false_negative_count': 1221, 'true_negative_count': 1170, 'precision': 0.5555555555555556, 'recall': 0.004078303425774877, 'false_positive_rate': 0.0034071550255536627, 'false_discovery_rate': 0.4444444444444444, 'predicted_positive_rate': 0.00375, 'base_positive_rate': 0.5108333333333334, 'precision_lift': 1.0875475802066341, 'decision_cost': 1241.0, 'decision_cost_per_row': 0.5170833333333333, 'decision_cost_per_signal': 137.88888888888889, 'active_window_rate': 0.9, 'zero_signal_window_rate': 0.09999999999999998, 'high_target_window_count': 7, 'high_target_window_capture_rate': 0.5714285714285714, 'missed_high_target_window_rate': 0.42857142857142855, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 20.0, 'ranked_signal_quality': 0.38701976358787143}`

## Decision Contract

- CatBoostRanker learns continuous up/down relevance grouped by batch_id.
- Prediction decisions use a validation-calibrated threshold and causal timestamp-order signal budget.
- Full prediction-batch top-k sorting is not used for live decisions.

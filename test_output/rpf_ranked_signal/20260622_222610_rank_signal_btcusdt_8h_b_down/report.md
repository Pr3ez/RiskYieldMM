# RPF Ranked Signal Report

## Scope

- `asset`: `BTCUSDT`
- `root`: `8h/B`
- `side`: `down`

## Best Trial

- `trial_number`: `3`
- `status`: `ok`
- `objective_value`: `0.699481`
- `train_batches`: `80`
- `val_batches`: `10`
- `sequence_mode`: `none`
- `rank_loss`: `YetiRank`
- `selected_feature_count_mean`: `39.35`
- `prediction_precision`: `0.666667`
- `prediction_precision_lift`: `1.81715`
- `prediction_recall`: `0.00227144`
- `prediction_false_positive_rate`: `0.000658111`
- `prediction_false_discovery_rate`: `0.333333`
- `prediction_active_window_rate`: `0.3`
- `prediction_zero_signal_window_rate`: `0.7`
- `prediction_high_target_window_capture_rate`: `0.3`
- `prediction_missed_high_target_window_rate`: `0.7`
- `prediction_decision_cost_per_row`: `0.368125`
- `trial_config_json`: `{"decision": {"fn_cost": 1.0, "fp_cost": 5.0, "high_false_positive_rate_threshold": 0.3, "high_target_positive_rate_threshold": 0.2, "max_signals_per_batch": 1, "threshold_quantile": 0.95}, "elasticnet": {"alpha": 0.01, "coef_eps": 1e-08, "l1_ratio": 0.5, "max_features": 40, "max_iter": 2000, "min_features": 5, "prefilter_features": 80, "tol": 0.001}, "model": {"depth": 3, "early_stopping_rounds": 100, "iterations": 50, "l2_leaf_reg": 100.0, "learning_rate": 0.03, "od_wait": 100, "random_strength": 1.0, "rank_loss": "YetiRank"}, "sequence": {"cnn_batch_size": 512, "cnn_conv_channels": 16, "cnn_device": "cpu", "cnn_embedding_dim": 8, "cnn_epochs": 1, "cnn_kernel_size": 3, "cnn_max_train_rows": 8000, "mode": "none", "n_kernels": 128, "seed": 42, "sequence_length": 16}, "train_batches": 80, "val_batches": 10}`
- `error_type`: `-`
- `error_message`: `-`
- `error_traceback`: `-`
- `optuna_params_json`: `{"depth": 3, "elasticnet_alpha": 0.01, "elasticnet_coef_eps": 1e-08, "elasticnet_l1_ratio": 0.5, "elasticnet_max_features": 40, "elasticnet_prefilter_features": 80, "iterations": 50, "l2_leaf_reg": 100.0, "learning_rate": 0.03, "max_signals_per_batch": 1, "random_strength": 1.0, "rank_loss": "YetiRank", "threshold_quantile": 0.95, "train_batches": 80, "val_batches": 10}`

## Holdout

- `status`: `ok`
- `objective_value`: `2.68031`
- `prediction_metrics`: `{'rows': 2400, 'positive_count': 475, 'negative_count': 1925, 'predicted_positive_count': 9, 'true_positive_count': 4, 'false_positive_count': 5, 'false_negative_count': 471, 'true_negative_count': 1920, 'precision': 0.4444444444444444, 'recall': 0.008421052631578947, 'false_positive_rate': 0.0025974025974025974, 'false_discovery_rate': 0.5555555555555556, 'predicted_positive_rate': 0.00375, 'base_positive_rate': 0.19791666666666666, 'precision_lift': 2.245614035087719, 'decision_cost': 496.0, 'decision_cost_per_row': 0.20666666666666667, 'decision_cost_per_signal': 55.111111111111114, 'active_window_rate': 0.9, 'zero_signal_window_rate': 0.09999999999999998, 'high_target_window_count': 4, 'high_target_window_capture_rate': 0.75, 'missed_high_target_window_rate': 0.25, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 39.7, 'ranked_signal_quality': 2.6803079312865496}`

## Decision Contract

- CatBoostRanker learns continuous up/down relevance grouped by batch_id.
- Prediction decisions use a validation-calibrated threshold and causal timestamp-order signal budget.
- Full prediction-batch top-k sorting is not used for live decisions.

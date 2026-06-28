# RPF Ranked Signal Report

## Scope

- `asset`: `BTCUSDT`
- `root`: `8h/B`
- `side`: `down`

## Best Trial

- `trial_number`: `4`
- `status`: `ok`
- `objective_value`: `0.196513`
- `train_batches`: `40`
- `val_batches`: `5`
- `sequence_mode`: `causal_rocket_v1`
- `rank_loss`: `YetiRank`
- `selected_feature_count_mean`: `20`
- `prediction_precision`: `0.428571`
- `prediction_precision_lift`: `1.16817`
- `prediction_recall`: `0.011925`
- `prediction_false_positive_rate`: `0.00921356`
- `prediction_false_discovery_rate`: `0.571429`
- `prediction_active_window_rate`: `0.75`
- `prediction_zero_signal_window_rate`: `0.25`
- `prediction_high_target_window_capture_rate`: `0.7`
- `prediction_missed_high_target_window_rate`: `0.3`
- `prediction_decision_cost_per_row`: `0.391667`
- `trial_config_json`: `{"decision": {"fn_cost": 1.0, "fp_cost": 5.0, "high_false_positive_rate_threshold": 0.3, "high_target_positive_rate_threshold": 0.2, "max_signals_per_batch": 5, "threshold_quantile": 0.9}, "elasticnet": {"alpha": 0.01, "coef_eps": 1e-08, "l1_ratio": 0.5, "max_features": 20, "max_iter": 2000, "min_features": 5, "prefilter_features": 160, "tol": 0.001}, "model": {"depth": 2, "early_stopping_rounds": 100, "iterations": 50, "l2_leaf_reg": 100.0, "learning_rate": 0.01, "od_wait": 100, "random_strength": 1.0, "rank_loss": "YetiRank"}, "sequence": {"cnn_batch_size": 512, "cnn_conv_channels": 16, "cnn_device": "cpu", "cnn_embedding_dim": 8, "cnn_epochs": 1, "cnn_kernel_size": 3, "cnn_max_train_rows": 8000, "mode": "causal_rocket_v1", "n_kernels": 128, "seed": 42, "sequence_length": 16}, "train_batches": 40, "val_batches": 5}`
- `error_type`: `-`
- `error_message`: `-`
- `error_traceback`: `-`
- `optuna_params_json`: `{"depth": 2, "elasticnet_alpha": 0.01, "elasticnet_coef_eps": 1e-08, "elasticnet_l1_ratio": 0.5, "elasticnet_max_features": 20, "elasticnet_prefilter_features": 160, "iterations": 50, "l2_leaf_reg": 100.0, "learning_rate": 0.01, "max_signals_per_batch": 5, "random_strength": 1.0, "rank_loss": "YetiRank", "rocket_kernels": 128, "sequence_length": 16, "threshold_quantile": 0.9, "train_batches": 40, "val_batches": 5}`

## Holdout

- `status`: `ok`
- `objective_value`: `-1.50403`
- `prediction_metrics`: `{'rows': 2400, 'positive_count': 475, 'negative_count': 1925, 'predicted_positive_count': 36, 'true_positive_count': 5, 'false_positive_count': 31, 'false_negative_count': 470, 'true_negative_count': 1894, 'precision': 0.1388888888888889, 'recall': 0.010526315789473684, 'false_positive_rate': 0.016103896103896103, 'false_discovery_rate': 0.8611111111111112, 'predicted_positive_rate': 0.015, 'base_positive_rate': 0.19791666666666666, 'precision_lift': 0.7017543859649124, 'decision_cost': 625.0, 'decision_cost_per_row': 0.2604166666666667, 'decision_cost_per_signal': 17.36111111111111, 'active_window_rate': 0.8, 'zero_signal_window_rate': 0.19999999999999996, 'high_target_window_count': 4, 'high_target_window_capture_rate': 0.25, 'missed_high_target_window_rate': 0.75, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 20.0, 'ranked_signal_quality': -1.504027777777778}`

## Decision Contract

- CatBoostRanker learns continuous up/down relevance grouped by batch_id.
- Prediction decisions use a validation-calibrated threshold and causal timestamp-order signal budget.
- Full prediction-batch top-k sorting is not used for live decisions.

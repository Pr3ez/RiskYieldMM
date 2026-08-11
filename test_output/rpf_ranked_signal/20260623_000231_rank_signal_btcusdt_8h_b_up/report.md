# RPF Ranked Signal Report

## Scope

- `asset`: `BTCUSDT`
- `root`: `8h/B`
- `side`: `up`

## Best Trial

- `trial_number`: `8`
- `status`: `ok`
- `objective_value`: `-0.0149478`
- `train_batches`: `40`
- `val_batches`: `5`
- `sequence_mode`: `causal_rocket_v1`
- `rank_loss`: `YetiRank`
- `selected_feature_count_mean`: `20`
- `prediction_precision`: `0.428571`
- `prediction_precision_lift`: `1.02244`
- `prediction_recall`: `0.00695825`
- `prediction_false_positive_rate`: `0.00669536`
- `prediction_false_discovery_rate`: `0.571429`
- `prediction_active_window_rate`: `0.833333`
- `prediction_zero_signal_window_rate`: `0.166667`
- `prediction_high_target_window_capture_rate`: `0.666667`
- `prediction_missed_high_target_window_rate`: `0.333333`
- `prediction_decision_cost_per_row`: `0.435694`
- `trial_config_json`: `{"decision": {"fn_cost": 1.0, "fp_cost": 5.0, "high_false_positive_rate_threshold": 0.3, "high_target_positive_rate_threshold": 0.2, "max_signals_per_batch": 2, "threshold_quantile": 0.95}, "elasticnet": {"alpha": 0.01, "coef_eps": 1e-08, "l1_ratio": 0.5, "max_features": 20, "max_iter": 2000, "min_features": 5, "prefilter_features": 160, "tol": 0.001}, "model": {"depth": 2, "early_stopping_rounds": 100, "iterations": 50, "l2_leaf_reg": 100.0, "learning_rate": 0.01, "od_wait": 100, "random_strength": 1.0, "rank_loss": "YetiRank"}, "sequence": {"cnn_batch_size": 512, "cnn_conv_channels": 16, "cnn_device": "cpu", "cnn_embedding_dim": 8, "cnn_epochs": 1, "cnn_kernel_size": 3, "cnn_max_train_rows": 8000, "mode": "causal_rocket_v1", "n_kernels": 32, "seed": 42, "sequence_length": 16}, "train_batches": 40, "val_batches": 5}`
- `error_type`: `-`
- `error_message`: `-`
- `error_traceback`: `-`
- `optuna_params_json`: `{"depth": 2, "elasticnet_alpha": 0.01, "elasticnet_coef_eps": 1e-08, "elasticnet_l1_ratio": 0.5, "elasticnet_max_features": 20, "elasticnet_prefilter_features": 160, "iterations": 50, "l2_leaf_reg": 100.0, "learning_rate": 0.01, "max_signals_per_batch": 2, "random_strength": 1.0, "rank_loss": "YetiRank", "rocket_kernels": 32, "sequence_length": 16, "threshold_quantile": 0.95, "train_batches": 40, "val_batches": 5}`

## Holdout

- `status`: `ok`
- `objective_value`: `0.619529`
- `prediction_metrics`: `{'rows': 4800, 'positive_count': 2648, 'negative_count': 2152, 'predicted_positive_count': 17, 'true_positive_count': 13, 'false_positive_count': 4, 'false_negative_count': 2635, 'true_negative_count': 2148, 'precision': 0.7647058823529411, 'recall': 0.004909365558912387, 'false_positive_rate': 0.0018587360594795538, 'false_discovery_rate': 0.23529411764705882, 'predicted_positive_rate': 0.0035416666666666665, 'base_positive_rate': 0.5516666666666666, 'precision_lift': 1.3861738048693797, 'decision_cost': 2655.0, 'decision_cost_per_row': 0.553125, 'decision_cost_per_signal': 156.1764705882353, 'active_window_rate': 0.45, 'zero_signal_window_rate': 0.55, 'high_target_window_count': 15, 'high_target_window_capture_rate': 0.4666666666666667, 'missed_high_target_window_rate': 0.5333333333333333, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 20.0, 'ranked_signal_quality': 0.6195289822877786}`

## Decision Contract

- CatBoostRanker learns continuous up/down relevance grouped by batch_id.
- Prediction decisions use a validation-calibrated threshold and causal timestamp-order signal budget.
- Full prediction-batch top-k sorting is not used for live decisions.

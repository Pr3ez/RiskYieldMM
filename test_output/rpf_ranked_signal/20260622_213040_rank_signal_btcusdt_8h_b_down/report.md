# RPF Ranked Signal Report

## Scope

- `asset`: `BTCUSDT`
- `root`: `8h/B`
- `side`: `down`

## Best Trial

- `trial_number`: `6`
- `status`: `ok`
- `objective_value`: `0.392686`
- `train_batches`: `80`
- `val_batches`: `10`
- `sequence_mode`: `none`
- `rank_loss`: `YetiRank`
- `selected_feature_count_mean`: `39.35`
- `prediction_precision`: `0.577778`
- `prediction_precision_lift`: `1.57486`
- `prediction_recall`: `0.0295287`
- `prediction_false_positive_rate`: `0.0125041`
- `prediction_false_discovery_rate`: `0.422222`
- `prediction_active_window_rate`: `0.45`
- `prediction_zero_signal_window_rate`: `0.55`
- `prediction_high_target_window_capture_rate`: `0.4`
- `prediction_missed_high_target_window_rate`: `0.6`
- `prediction_decision_cost_per_row`: `0.395625`
- `trial_config_json`: `{"decision": {"fn_cost": 1.0, "fp_cost": 5.0, "high_false_positive_rate_threshold": 0.3, "high_target_positive_rate_threshold": 0.2, "max_signals_per_batch": 10, "threshold_quantile": 0.9}, "elasticnet": {"alpha": 0.01, "coef_eps": 1e-08, "l1_ratio": 0.5, "max_features": 40, "max_iter": 2000, "min_features": 5, "prefilter_features": 80, "tol": 0.001}, "model": {"depth": 3, "early_stopping_rounds": 100, "iterations": 50, "l2_leaf_reg": 100.0, "learning_rate": 0.03, "od_wait": 100, "random_strength": 1.0, "rank_loss": "YetiRank"}, "sequence": {"cnn_batch_size": 512, "cnn_conv_channels": 16, "cnn_device": "cpu", "cnn_embedding_dim": 8, "cnn_epochs": 1, "cnn_kernel_size": 3, "cnn_max_train_rows": 8000, "mode": "none", "n_kernels": 128, "seed": 42, "sequence_length": 16}, "train_batches": 80, "val_batches": 10}`
- `error_type`: `-`
- `error_message`: `-`
- `error_traceback`: `-`
- `optuna_params_json`: `{"depth": 3, "elasticnet_alpha": 0.01, "elasticnet_coef_eps": 1e-08, "elasticnet_l1_ratio": 0.5, "elasticnet_max_features": 40, "elasticnet_prefilter_features": 80, "iterations": 50, "l2_leaf_reg": 100.0, "learning_rate": 0.03, "max_signals_per_batch": 10, "random_strength": 1.0, "rank_loss": "YetiRank", "threshold_quantile": 0.9, "train_batches": 80, "val_batches": 10}`

## Holdout

- `status`: `ok`
- `objective_value`: `2.52889`
- `prediction_metrics`: `{'rows': 2400, 'positive_count': 475, 'negative_count': 1925, 'predicted_positive_count': 74, 'true_positive_count': 32, 'false_positive_count': 42, 'false_negative_count': 443, 'true_negative_count': 1883, 'precision': 0.43243243243243246, 'recall': 0.06736842105263158, 'false_positive_rate': 0.02181818181818182, 'false_discovery_rate': 0.5675675675675675, 'predicted_positive_rate': 0.030833333333333334, 'base_positive_rate': 0.19791666666666666, 'precision_lift': 2.1849217638691325, 'decision_cost': 653.0, 'decision_cost_per_row': 0.27208333333333334, 'decision_cost_per_signal': 8.824324324324325, 'active_window_rate': 0.9, 'zero_signal_window_rate': 0.09999999999999998, 'high_target_window_count': 4, 'high_target_window_capture_rate': 0.75, 'missed_high_target_window_rate': 0.25, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 39.7, 'ranked_signal_quality': 2.5288933588193463}`

## Decision Contract

- CatBoostRanker learns continuous up/down relevance grouped by batch_id.
- Prediction decisions use a validation-calibrated threshold and causal timestamp-order signal budget.
- Full prediction-batch top-k sorting is not used for live decisions.

# RPF Ranked Signal Report

## Scope

- `asset`: `BTCUSDT`
- `root`: `8h/B`
- `side`: `up`

## Best Trial

- `trial_number`: `2`
- `status`: `ok`
- `objective_value`: `-0.816276`
- `train_batches`: `40`
- `val_batches`: `5`
- `sequence_mode`: `none`
- `rank_loss`: `YetiRank`
- `selected_feature_count_mean`: `23.3`
- `prediction_precision`: `0.5`
- `prediction_precision_lift`: `1.19284`
- `prediction_recall`: `0.00596421`
- `prediction_false_positive_rate`: `0.00430416`
- `prediction_false_discovery_rate`: `0.5`
- `prediction_active_window_rate`: `0.4`
- `prediction_zero_signal_window_rate`: `0.6`
- `prediction_high_target_window_capture_rate`: `0.277778`
- `prediction_missed_high_target_window_rate`: `0.722222`
- `prediction_decision_cost_per_row`: `0.429167`
- `trial_config_json`: `{"decision": {"fn_cost": 1.0, "fp_cost": 5.0, "high_false_positive_rate_threshold": 0.3, "high_target_positive_rate_threshold": 0.2, "max_signals_per_batch": 3, "threshold_quantile": 0.975}, "elasticnet": {"alpha": 0.03, "coef_eps": 1e-08, "l1_ratio": 0.5, "max_features": 40, "max_iter": 2000, "min_features": 5, "prefilter_features": 80, "tol": 0.001}, "model": {"depth": 3, "early_stopping_rounds": 100, "iterations": 100, "l2_leaf_reg": 30.0, "learning_rate": 0.01, "od_wait": 100, "random_strength": 1.0, "rank_loss": "YetiRank"}, "sequence": {"cnn_batch_size": 512, "cnn_conv_channels": 16, "cnn_device": "cpu", "cnn_embedding_dim": 8, "cnn_epochs": 1, "cnn_kernel_size": 3, "cnn_max_train_rows": 8000, "mode": "none", "n_kernels": 128, "seed": 42, "sequence_length": 16}, "train_batches": 40, "val_batches": 5}`
- `error_type`: `-`
- `error_message`: `-`
- `error_traceback`: `-`
- `optuna_params_json`: `{"depth": 3, "elasticnet_alpha": 0.03, "elasticnet_coef_eps": 1e-08, "elasticnet_l1_ratio": 0.5, "elasticnet_max_features": 40, "elasticnet_prefilter_features": 80, "iterations": 100, "l2_leaf_reg": 30.0, "learning_rate": 0.01, "max_signals_per_batch": 3, "random_strength": 1.0, "rank_loss": "YetiRank", "threshold_quantile": 0.975, "train_batches": 40, "val_batches": 5}`

## Holdout

- `status`: `ok`
- `objective_value`: `-1.04476`
- `prediction_metrics`: `{'rows': 4800, 'positive_count': 2648, 'negative_count': 2152, 'predicted_positive_count': 21, 'true_positive_count': 12, 'false_positive_count': 9, 'false_negative_count': 2636, 'true_negative_count': 2143, 'precision': 0.5714285714285714, 'recall': 0.004531722054380665, 'false_positive_rate': 0.004182156133828996, 'false_discovery_rate': 0.42857142857142855, 'predicted_positive_rate': 0.004375, 'base_positive_rate': 0.5516666666666666, 'precision_lift': 1.0358221838584376, 'decision_cost': 2681.0, 'decision_cost_per_row': 0.5585416666666667, 'decision_cost_per_signal': 127.66666666666667, 'active_window_rate': 0.35, 'zero_signal_window_rate': 0.65, 'high_target_window_count': 15, 'high_target_window_capture_rate': 0.26666666666666666, 'missed_high_target_window_rate': 0.7333333333333333, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 20.25, 'ranked_signal_quality': -1.0447581620450297}`

## Decision Contract

- CatBoostRanker learns continuous up/down relevance grouped by batch_id.
- Prediction decisions use a validation-calibrated threshold and causal timestamp-order signal budget.
- Full prediction-batch top-k sorting is not used for live decisions.

# RPF Ranked Signal Report

## Scope

- `asset`: `BTCUSDT`
- `root`: `8h/B`
- `side`: `down`

## Best Trial

- `trial_number`: `8`
- `status`: `ok`
- `objective_value`: `-0.0299217`
- `train_batches`: `80`
- `val_batches`: `10`
- `sequence_mode`: `none`
- `rank_loss`: `YetiRank`
- `selected_feature_count_mean`: `38.3`
- `prediction_precision`: `0.592593`
- `prediction_precision_lift`: `1.53422`
- `prediction_recall`: `0.00575333`
- `prediction_false_positive_rate`: `0.00248925`
- `prediction_false_discovery_rate`: `0.407407`
- `prediction_active_window_rate`: `0.3`
- `prediction_zero_signal_window_rate`: `0.7`
- `prediction_high_target_window_capture_rate`: `0.3125`
- `prediction_missed_high_target_window_rate`: `0.6875`
- `prediction_decision_cost_per_row`: `0.391667`
- `trial_config_json`: `{"decision": {"fn_cost": 1.0, "fp_cost": 5.0, "high_false_positive_rate_threshold": 0.3, "high_target_positive_rate_threshold": 0.2, "max_signals_per_batch": 3, "threshold_quantile": 0.95}, "elasticnet": {"alpha": 0.01, "coef_eps": 1e-08, "l1_ratio": 0.5, "max_features": 40, "max_iter": 2000, "min_features": 5, "prefilter_features": 80, "tol": 0.001}, "model": {"depth": 3, "early_stopping_rounds": 100, "iterations": 50, "l2_leaf_reg": 100.0, "learning_rate": 0.03, "od_wait": 100, "random_strength": 1.0, "rank_loss": "YetiRank"}, "sequence": {"cnn_batch_size": 512, "cnn_conv_channels": 16, "cnn_device": "cpu", "cnn_embedding_dim": 8, "cnn_epochs": 1, "cnn_kernel_size": 3, "cnn_max_train_rows": 8000, "mode": "none", "n_kernels": 128, "seed": 42, "sequence_length": 16}, "train_batches": 80, "val_batches": 10}`
- `error_type`: `-`
- `error_message`: `-`
- `error_traceback`: `-`
- `optuna_params_json`: `{"depth": 3, "elasticnet_alpha": 0.01, "elasticnet_coef_eps": 1e-08, "elasticnet_l1_ratio": 0.5, "elasticnet_max_features": 40, "elasticnet_prefilter_features": 80, "iterations": 50, "l2_leaf_reg": 100.0, "learning_rate": 0.03, "max_signals_per_batch": 3, "random_strength": 1.0, "rank_loss": "YetiRank", "threshold_quantile": 0.95, "train_batches": 80, "val_batches": 10}`

## Holdout

- `status`: `ok`
- `objective_value`: `2.08797`
- `prediction_metrics`: `{'rows': 4800, 'positive_count': 970, 'negative_count': 3830, 'predicted_positive_count': 37, 'true_positive_count': 17, 'false_positive_count': 20, 'false_negative_count': 953, 'true_negative_count': 3810, 'precision': 0.4594594594594595, 'recall': 0.01752577319587629, 'false_positive_rate': 0.005221932114882507, 'false_discovery_rate': 0.5405405405405406, 'predicted_positive_rate': 0.0077083333333333335, 'base_positive_rate': 0.20208333333333334, 'precision_lift': 2.273613820005573, 'decision_cost': 1053.0, 'decision_cost_per_row': 0.219375, 'decision_cost_per_signal': 28.45945945945946, 'active_window_rate': 0.65, 'zero_signal_window_rate': 0.35, 'high_target_window_count': 7, 'high_target_window_capture_rate': 0.5714285714285714, 'missed_high_target_window_rate': 0.42857142857142855, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 39.8, 'ranked_signal_quality': 2.0879745029455092}`

## Decision Contract

- CatBoostRanker learns continuous up/down relevance grouped by batch_id.
- Prediction decisions use a validation-calibrated threshold and causal timestamp-order signal budget.
- Full prediction-batch top-k sorting is not used for live decisions.

# RPF Ranked Signal Report

## Scope

- `asset`: `BTCUSDT`
- `root`: `8h/B`
- `side`: `up`

## Best Trial

- `trial_number`: `5`
- `status`: `ok`
- `objective_value`: `-0.969332`
- `train_batches`: `40`
- `val_batches`: `5`
- `sequence_mode`: `none`
- `rank_loss`: `YetiRank`
- `selected_feature_count_mean`: `20.9`
- `prediction_precision`: `0.5`
- `prediction_precision_lift`: `1.07`
- `prediction_recall`: `0.00891663`
- `prediction_false_positive_rate`: `0.00782167`
- `prediction_false_discovery_rate`: `0.5`
- `prediction_active_window_rate`: `0.4`
- `prediction_zero_signal_window_rate`: `0.6`
- `prediction_high_target_window_capture_rate`: `0.333333`
- `prediction_missed_high_target_window_rate`: `0.666667`
- `prediction_decision_cost_per_row`: `0.483958`
- `trial_config_json`: `{"decision": {"fn_cost": 1.0, "fp_cost": 5.0, "high_false_positive_rate_threshold": 0.3, "high_target_positive_rate_threshold": 0.2, "max_signals_per_batch": 5, "threshold_quantile": 0.95}, "elasticnet": {"alpha": 0.03, "coef_eps": 1e-08, "l1_ratio": 0.5, "max_features": 40, "max_iter": 2000, "min_features": 5, "prefilter_features": 80, "tol": 0.001}, "model": {"depth": 3, "early_stopping_rounds": 100, "iterations": 100, "l2_leaf_reg": 30.0, "learning_rate": 0.01, "od_wait": 100, "random_strength": 1.0, "rank_loss": "YetiRank"}, "sequence": {"cnn_batch_size": 512, "cnn_conv_channels": 16, "cnn_device": "cpu", "cnn_embedding_dim": 8, "cnn_epochs": 1, "cnn_kernel_size": 3, "cnn_max_train_rows": 8000, "mode": "none", "n_kernels": 128, "seed": 42, "sequence_length": 16}, "train_batches": 40, "val_batches": 5}`
- `error_type`: `-`
- `error_message`: `-`
- `error_traceback`: `-`
- `optuna_params_json`: `{"depth": 3, "elasticnet_alpha": 0.03, "elasticnet_coef_eps": 1e-08, "elasticnet_l1_ratio": 0.5, "elasticnet_max_features": 40, "elasticnet_prefilter_features": 80, "iterations": 100, "l2_leaf_reg": 30.0, "learning_rate": 0.01, "max_signals_per_batch": 5, "random_strength": 1.0, "rank_loss": "YetiRank", "threshold_quantile": 0.95, "train_batches": 40, "val_batches": 5}`

## Holdout

- `status`: `ok`
- `objective_value`: `0.546133`
- `prediction_metrics`: `{'rows': 2400, 'positive_count': 1226, 'negative_count': 1174, 'predicted_positive_count': 25, 'true_positive_count': 17, 'false_positive_count': 8, 'false_negative_count': 1209, 'true_negative_count': 1166, 'precision': 0.68, 'recall': 0.013866231647634585, 'false_positive_rate': 0.0068143100511073255, 'false_discovery_rate': 0.32, 'predicted_positive_rate': 0.010416666666666666, 'base_positive_rate': 0.5108333333333334, 'precision_lift': 1.3311582381729201, 'decision_cost': 1249.0, 'decision_cost_per_row': 0.5204166666666666, 'decision_cost_per_signal': 49.96, 'active_window_rate': 0.5, 'zero_signal_window_rate': 0.5, 'high_target_window_count': 7, 'high_target_window_capture_rate': 0.5714285714285714, 'missed_high_target_window_rate': 0.42857142857142855, 'high_false_positive_window_rate': 0.0, 'selected_feature_count_mean': 19.5, 'ranked_signal_quality': 0.5461334406315546}`

## Decision Contract

- CatBoostRanker learns continuous up/down relevance grouped by batch_id.
- Prediction decisions use a validation-calibrated threshold and causal timestamp-order signal budget.
- Full prediction-batch top-k sorting is not used for live decisions.

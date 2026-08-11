# RPF Ranked Signal Report

## Scope

- `asset`: `BTCUSDT`
- `root`: `8h/B`
- `side`: `down`

## Best Trial

- `trial_number`: `0`
- `status`: `ok`
- `objective_value`: `1.19274`
- `train_batches`: `20`
- `val_batches`: `5`
- `sequence_mode`: `none`
- `rank_loss`: `YetiRank`
- `selected_feature_count_mean`: `20`
- `prediction_precision`: `0.4`
- `prediction_precision_lift`: `1.52866`
- `prediction_recall`: `0.0318471`
- `prediction_false_positive_rate`: `0.01693`
- `prediction_false_discovery_rate`: `0.6`
- `prediction_active_window_rate`: `1`
- `prediction_zero_signal_window_rate`: `0`
- `prediction_high_target_window_capture_rate`: `0.666667`
- `prediction_missed_high_target_window_rate`: `0.333333`
- `prediction_decision_cost_per_row`: `0.315833`
- `trial_config_json`: `{"decision": {"fn_cost": 1.0, "fp_cost": 5.0, "high_false_positive_rate_threshold": 0.3, "high_target_positive_rate_threshold": 0.2, "max_signals_per_batch": 5, "threshold_quantile": 0.95}, "elasticnet": {"alpha": 0.01, "coef_eps": 1e-08, "l1_ratio": 0.5, "max_features": 20, "max_iter": 2000, "min_features": 5, "prefilter_features": 80, "tol": 0.001}, "model": {"depth": 2, "early_stopping_rounds": 100, "iterations": 10, "l2_leaf_reg": 30.0, "learning_rate": 0.03, "od_wait": 100, "random_strength": 1.0, "rank_loss": "YetiRank"}, "sequence": {"cnn_batch_size": 512, "cnn_conv_channels": 16, "cnn_device": "cpu", "cnn_embedding_dim": 8, "cnn_epochs": 1, "cnn_kernel_size": 3, "cnn_max_train_rows": 8000, "mode": "none", "n_kernels": 128, "seed": 42, "sequence_length": 16}, "train_batches": 20, "val_batches": 5}`
- `error_type`: `-`
- `error_message`: `-`
- `error_traceback`: `-`
- `optuna_params_json`: `{"depth": 2, "elasticnet_alpha": 0.01, "elasticnet_coef_eps": 1e-08, "elasticnet_l1_ratio": 0.5, "elasticnet_max_features": 20, "elasticnet_prefilter_features": 80, "iterations": 10, "l2_leaf_reg": 30.0, "learning_rate": 0.03, "max_signals_per_batch": 5, "random_strength": 1.0, "rank_loss": "YetiRank", "threshold_quantile": 0.95, "train_batches": 20, "val_batches": 5}`

## Holdout

- `status`: `skipped:no_holdout_windows`
- `objective_value`: `-`
- `prediction_metrics`: `{}`

## Decision Contract

- CatBoostRanker learns continuous up/down relevance grouped by batch_id.
- Prediction decisions use a validation-calibrated threshold and causal timestamp-order signal budget.
- Full prediction-batch top-k sorting is not used for live decisions.

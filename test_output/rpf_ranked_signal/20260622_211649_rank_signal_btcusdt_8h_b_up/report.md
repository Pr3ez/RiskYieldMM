# RPF Ranked Signal Report

## Scope

- `asset`: `BTCUSDT`
- `root`: `8h/B`
- `side`: `up`

## Best Trial

- `trial_number`: `1`
- `status`: `ok`
- `objective_value`: `0.668766`
- `train_batches`: `20`
- `val_batches`: `5`
- `sequence_mode`: `none`
- `rank_loss`: `YetiRank`
- `selected_feature_count_mean`: `19.8`
- `prediction_precision`: `0.5`
- `prediction_precision_lift`: `1.30152`
- `prediction_recall`: `0.021692`
- `prediction_false_positive_rate`: `0.0135318`
- `prediction_false_discovery_rate`: `0.5`
- `prediction_active_window_rate`: `0.8`
- `prediction_zero_signal_window_rate`: `0.2`
- `prediction_high_target_window_capture_rate`: `0.666667`
- `prediction_missed_high_target_window_rate`: `0.333333`
- `prediction_decision_cost_per_row`: `0.4175`
- `trial_config_json`: `{"decision": {"fn_cost": 1.0, "fp_cost": 5.0, "high_false_positive_rate_threshold": 0.3, "high_target_positive_rate_threshold": 0.2, "max_signals_per_batch": 5, "threshold_quantile": 0.95}, "elasticnet": {"alpha": 0.03, "coef_eps": 1e-08, "l1_ratio": 0.5, "max_features": 20, "max_iter": 2000, "min_features": 5, "prefilter_features": 80, "tol": 0.001}, "model": {"depth": 2, "early_stopping_rounds": 100, "iterations": 10, "l2_leaf_reg": 30.0, "learning_rate": 0.03, "od_wait": 100, "random_strength": 1.0, "rank_loss": "YetiRank"}, "sequence": {"cnn_batch_size": 512, "cnn_conv_channels": 16, "cnn_device": "cpu", "cnn_embedding_dim": 8, "cnn_epochs": 1, "cnn_kernel_size": 3, "cnn_max_train_rows": 8000, "mode": "none", "n_kernels": 128, "seed": 42, "sequence_length": 16}, "train_batches": 20, "val_batches": 5}`
- `error_type`: `-`
- `error_message`: `-`
- `error_traceback`: `-`
- `optuna_params_json`: `{"depth": 2, "elasticnet_alpha": 0.03, "elasticnet_coef_eps": 1e-08, "elasticnet_l1_ratio": 0.5, "elasticnet_max_features": 20, "elasticnet_prefilter_features": 80, "iterations": 10, "l2_leaf_reg": 30.0, "learning_rate": 0.03, "max_signals_per_batch": 5, "random_strength": 1.0, "rank_loss": "YetiRank", "threshold_quantile": 0.95, "train_batches": 20, "val_batches": 5}`

## Holdout

- `status`: `skipped:no_holdout_windows`
- `objective_value`: `-`
- `prediction_metrics`: `{}`

## Decision Contract

- CatBoostRanker learns continuous up/down relevance grouped by batch_id.
- Prediction decisions use a validation-calibrated threshold and causal timestamp-order signal budget.
- Full prediction-batch top-k sorting is not used for live decisions.

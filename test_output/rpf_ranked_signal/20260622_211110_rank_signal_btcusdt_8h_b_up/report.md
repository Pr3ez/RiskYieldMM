# RPF Ranked Signal Report

## Scope

- `asset`: `BTCUSDT`
- `root`: `8h/B`
- `side`: `up`

## Best Trial

- `trial_number`: `0`
- `status`: `error`
- `objective_value`: `-1e+09`
- `train_batches`: `120`
- `val_batches`: `10`
- `sequence_mode`: `none`
- `rank_loss`: `YetiRank`
- `selected_feature_count_mean`: `-`
- `prediction_precision`: `-`
- `prediction_precision_lift`: `-`
- `prediction_recall`: `-`
- `prediction_false_positive_rate`: `-`
- `prediction_false_discovery_rate`: `-`
- `prediction_active_window_rate`: `-`
- `prediction_zero_signal_window_rate`: `-`
- `prediction_high_target_window_capture_rate`: `-`
- `prediction_missed_high_target_window_rate`: `-`
- `prediction_decision_cost_per_row`: `-`
- `trial_config_json`: `{"decision": {"fn_cost": 1.0, "fp_cost": 5.0, "high_false_positive_rate_threshold": 0.3, "high_target_positive_rate_threshold": 0.2, "max_signals_per_batch": 10, "threshold_quantile": 0.9}, "elasticnet": {"alpha": 0.001, "coef_eps": 1e-08, "l1_ratio": 0.75, "max_features": 160, "max_iter": 2000, "min_features": 10, "prefilter_features": 160, "tol": 0.001}, "model": {"depth": 3, "early_stopping_rounds": 100, "iterations": 200, "l2_leaf_reg": 30.0, "learning_rate": 0.005, "od_wait": 100, "random_strength": 5.0, "rank_loss": "YetiRank"}, "sequence": {"cnn_batch_size": 512, "cnn_conv_channels": 16, "cnn_device": "cpu", "cnn_embedding_dim": 8, "cnn_epochs": 1, "cnn_kernel_size": 3, "cnn_max_train_rows": 8000, "mode": "none", "n_kernels": 128, "seed": 42, "sequence_length": 16}, "train_batches": 120, "val_batches": 10}`
- `optuna_params_json`: `{"depth": 3, "elasticnet_alpha": 0.001, "elasticnet_coef_eps": 1e-08, "elasticnet_l1_ratio": 0.75, "elasticnet_max_features": 160, "elasticnet_prefilter_features": 160, "iterations": 200, "l2_leaf_reg": 30.0, "learning_rate": 0.005, "max_signals_per_batch": 10, "random_strength": 5.0, "rank_loss": "YetiRank", "threshold_quantile": 0.9, "train_batches": 120, "val_batches": 10}`

## Holdout

- `status`: `skipped:no_holdout_windows`
- `objective_value`: `-`
- `prediction_metrics`: `{}`

## Decision Contract

- CatBoostRanker learns continuous up/down relevance grouped by batch_id.
- Prediction decisions use a validation-calibrated threshold and causal timestamp-order signal budget.
- Full prediction-batch top-k sorting is not used for live decisions.

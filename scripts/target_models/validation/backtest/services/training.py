"""
Training services for per-model ensemble learning.

REFACTORED VERSION: Uses new model modules instead of inline training.

Each model module (catboost_model, lightgbm_model, lstm_model, linear_model)
handles its own:
- Configuration
- Optuna tuning
- Training
- Prediction

This module orchestrates:
- Per-model split extraction
- Per-model feature selection
- Calling each model module
- Ensemble combination
- Conformal prediction
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd
from backtest.adapters.data_loader import get_embargo_for_horizon
from backtest.core.features import extract_per_model_splits
from backtest.domain.config import SyncBacktestConfig
from backtest.models.catboost_model import (
    CatBoostModelConfig,
    optimize_catboost_config,
    select_features_catboost,
    select_features_catboost_regression,
)
from backtest.models.catboost_model import (
    train_and_predict_classifier as cb_train_predict_cls,
)
from backtest.models.catboost_model import (
    train_and_predict_regressor as cb_train_predict_reg,
)
from backtest.models.lightgbm_model import (
    LightGBMModelConfig,
    optimize_lightgbm_config,
    select_features_lightgbm,
    select_features_lightgbm_regression,
)
from backtest.models.lightgbm_model import (
    train_and_predict_classifier as lgb_train_predict_cls,
)
from backtest.models.lightgbm_model import (
    train_and_predict_regressor as lgb_train_predict_reg,
)
from backtest.models.linear_model import (
    LinearModelConfig,
    optimize_linear_config,
    select_features_linear,
)
from backtest.models.linear_model import (
    train_and_predict_classifier as linear_train_predict_cls,
)
from backtest.models.linear_model import (
    train_and_predict_regressor as linear_train_predict_reg,
)
from backtest.models.lstm_model import (
    LSTMModelConfig,
    optimize_lstm_config,
    select_features_lstm,
)
from backtest.models.lstm_model import (
    train_and_predict_classifier as lstm_train_predict_cls,
)
from backtest.models.lstm_model import (
    train_and_predict_regressor as lstm_train_predict_reg,
)

if TYPE_CHECKING:
    pass


__all__ = [
    "train_predict_classification_permodel",
    "train_predict_regression_permodel",
    "_get_model_configs",
]


def _get_model_configs(
    config: SyncBacktestConfig, horizon: int
) -> tuple[
    CatBoostModelConfig, LightGBMModelConfig, LSTMModelConfig, LinearModelConfig
]:
    """Create model configs with dynamic embargo based on horizon.

    NOTE: This function creates configs from SyncBacktestConfig's PerModelConfig.
    If no PerModelConfig is set (config.*_config is None), it uses BASELINE values.

    These baseline values will be REPLACED by optimize_*_config() functions
    that analyze actual data to determine optimal parameters.

    Args:
        config: Backtest configuration
        horizon: Target horizon for dynamic embargo

    Returns:
        Tuple of (cb_config, lgb_config, lstm_config, linear_config)
    """
    dynamic_embargo = get_embargo_for_horizon(horizon)

    # BASELINE values - used only when no optimizer has run
    # These will be replaced by optimize_*_config() in Phase 2
    BASELINE_CB = {
        "train_window": 400,
        "train_ratio": 0.60,
        "val_ratio": 0.20,
        "cal_ratio": 0.20,
        "feature_selection": "importance",
        "feature_selection_ratio": 0.6,
        "min_features": 30,
    }
    BASELINE_LGB = BASELINE_CB.copy()  # Same as CatBoost
    BASELINE_LSTM = {
        "train_window": 600,
        "train_ratio": 0.70,
        "val_ratio": 0.15,
        "cal_ratio": 0.15,
        "feature_selection": "variance",
        "feature_selection_ratio": 0.8,
        "min_features": 40,
    }
    BASELINE_LINEAR = {
        "train_window": 800,
        "train_ratio": 0.50,
        "val_ratio": 0.20,
        "cal_ratio": 0.30,
        "feature_selection": "variance",  # Changed from icir (not implemented)
        "feature_selection_ratio": 0.5,
        "min_features": 20,
    }

    # Create configs - use explicit config if provided, else baseline
    cb_cfg = CatBoostModelConfig(
        train_window=config.cb_config.train_window
        if config.cb_config
        else BASELINE_CB["train_window"],
        train_ratio=config.cb_config.train_ratio
        if config.cb_config
        else BASELINE_CB["train_ratio"],
        val_ratio=config.cb_config.val_ratio
        if config.cb_config
        else BASELINE_CB["val_ratio"],
        cal_ratio=config.cb_config.cal_ratio
        if config.cb_config
        else BASELINE_CB["cal_ratio"],
        embargo_bars=dynamic_embargo,
        feature_selection=config.cb_config.feature_selection
        if config.cb_config
        else BASELINE_CB["feature_selection"],
        feature_selection_ratio=config.cb_config.feature_selection_ratio
        if config.cb_config
        else BASELINE_CB["feature_selection_ratio"],
        min_features=config.cb_config.min_features
        if config.cb_config
        else BASELINE_CB["min_features"],
        random_state=config.random_state,
        # CatBoost-specific from SyncBacktestConfig
        n_estimators=config.n_estimators,
        max_depth=config.max_depth,
        learning_rate=config.cb_learning_rate,
        l2_leaf_reg=config.cb_l2_leaf_reg,
        use_gpu=True,
        enable_tuning=config.enable_optuna,
        n_optuna_trials=config.n_optuna_trials,
        optuna_timeout=config.optuna_timeout,
    )

    lgb_cfg = LightGBMModelConfig(
        train_window=config.lgb_config.train_window
        if config.lgb_config
        else BASELINE_LGB["train_window"],
        train_ratio=config.lgb_config.train_ratio
        if config.lgb_config
        else BASELINE_LGB["train_ratio"],
        val_ratio=config.lgb_config.val_ratio
        if config.lgb_config
        else BASELINE_LGB["val_ratio"],
        cal_ratio=config.lgb_config.cal_ratio
        if config.lgb_config
        else BASELINE_LGB["cal_ratio"],
        embargo_bars=dynamic_embargo,
        feature_selection=config.lgb_config.feature_selection
        if config.lgb_config
        else BASELINE_LGB["feature_selection"],
        feature_selection_ratio=config.lgb_config.feature_selection_ratio
        if config.lgb_config
        else BASELINE_LGB["feature_selection_ratio"],
        min_features=config.lgb_config.min_features
        if config.lgb_config
        else BASELINE_LGB["min_features"],
        random_state=config.random_state,
        # LightGBM-specific
        n_estimators=config.n_estimators,
        max_depth=config.max_depth,
        learning_rate=config.lgb_learning_rate,
        reg_lambda=config.lgb_reg_lambda,
        min_child_samples=config.lgb_min_child_samples,
        use_gpu=True,
        enable_tuning=config.enable_optuna,
        n_optuna_trials=config.n_optuna_trials,
        optuna_timeout=config.optuna_timeout,
    )

    lstm_cfg = LSTMModelConfig(
        train_window=config.lstm_config.train_window
        if config.lstm_config
        else BASELINE_LSTM["train_window"],
        train_ratio=config.lstm_config.train_ratio
        if config.lstm_config
        else BASELINE_LSTM["train_ratio"],
        val_ratio=config.lstm_config.val_ratio
        if config.lstm_config
        else BASELINE_LSTM["val_ratio"],
        cal_ratio=config.lstm_config.cal_ratio
        if config.lstm_config
        else BASELINE_LSTM["cal_ratio"],
        embargo_bars=dynamic_embargo,
        feature_selection=config.lstm_config.feature_selection
        if config.lstm_config
        else BASELINE_LSTM["feature_selection"],
        feature_selection_ratio=config.lstm_config.feature_selection_ratio
        if config.lstm_config
        else BASELINE_LSTM["feature_selection_ratio"],
        min_features=config.lstm_config.min_features
        if config.lstm_config
        else BASELINE_LSTM["min_features"],
        random_state=config.random_state,
        # LSTM-specific
        hidden_size=config.lstm_hidden_size,
        num_layers=config.lstm_num_layers,
        learning_rate=config.lstm_lr,
        epochs=config.lstm_epochs,
        batch_size=config.lstm_batch_size,
        dropout=config.lstm_dropout,
        seq_len=config.lstm_seq_len,
        enable_tuning=config.enable_optuna,
        n_optuna_trials=min(config.n_optuna_trials, 10),  # Fewer for LSTM
        optuna_timeout=config.optuna_timeout * 2 if config.optuna_timeout else 60.0,
    )

    linear_cfg = LinearModelConfig(
        train_window=config.linear_config.train_window
        if config.linear_config
        else BASELINE_LINEAR["train_window"],
        train_ratio=config.linear_config.train_ratio
        if config.linear_config
        else BASELINE_LINEAR["train_ratio"],
        val_ratio=config.linear_config.val_ratio
        if config.linear_config
        else BASELINE_LINEAR["val_ratio"],
        cal_ratio=config.linear_config.cal_ratio
        if config.linear_config
        else BASELINE_LINEAR["cal_ratio"],
        embargo_bars=dynamic_embargo,
        feature_selection=config.linear_config.feature_selection
        if config.linear_config
        else BASELINE_LINEAR["feature_selection"],
        feature_selection_ratio=config.linear_config.feature_selection_ratio
        if config.linear_config
        else BASELINE_LINEAR["feature_selection_ratio"],
        min_features=config.linear_config.min_features
        if config.linear_config
        else BASELINE_LINEAR["min_features"],
        random_state=config.random_state,
        enable_tuning=config.enable_optuna,
        n_optuna_trials=config.n_optuna_trials,
        optuna_timeout=config.optuna_timeout,
    )

    return cb_cfg, lgb_cfg, lstm_cfg, linear_cfg


def train_predict_classification_permodel(
    X_full: pd.DataFrame,
    y_full: pd.Series,
    X_pred: pd.DataFrame,
    config: SyncBacktestConfig,
    n_classes: int,
    horizon: int,
    previous_best: dict[str, dict[str, Any]] | None = None,
    target_name: str = "",
    timestamps: np.ndarray | None = None,
    pred_timestamp: Any = None,
    target_timestamp: Any = None,
) -> tuple[
    int, np.ndarray | None, np.ndarray | None, dict[str, Any], dict[str, dict[str, Any]]
]:
    """Train 4-model ensemble classifier with TRUE per-model windows and features.

    Uses new model modules for each model's training/prediction pipeline.

    Args:
        X_full: Full feature window (max window size, typically 800)
        y_full: Full target window
        X_pred: Single row to predict
        config: Backtest configuration
        n_classes: Number of classes
        horizon: Target horizon (for dynamic embargo)
        previous_best: Previous best hyperparameters for warm-starting
        timestamps: Timestamps array for the window (for date printing)
        pred_timestamp: Timestamp of prediction point
        target_timestamp: Timestamp of target (horizon bars ahead)

    Returns:
        y_pred: Predicted class
        y_prob: Class probabilities
        prediction_set: Conformal prediction set
        components: Individual model predictions + metadata
        tuned_params: Best hyperparameters (for warm-starting next step)
    """
    full_window_size = len(X_full)
    is_binary = n_classes == 2

    # Print config header for this target with dates
    print(f"\n{'~' * 70}")
    print(f"  CONFIG: {target_name} (classification, horizon={horizon})")
    print(f"  Window: {full_window_size} samples, Features: {len(X_full.columns)}")
    if timestamps is not None and len(timestamps) > 0:
        print(f"  Window Dates: {timestamps[0]} → {timestamps[-1]}")
    if pred_timestamp is not None:
        print(f"  Prediction Date: {pred_timestamp}")
    if target_timestamp is not None:
        print(f"  Target Date: {target_timestamp} (+{horizon} bars)")
    print(f"{'~' * 70}")

    # =========================================================================
    # CATBOOST CONFIG: Use dynamic optimization (ALL 4 STAGES)
    # =========================================================================
    # CatBoost gets optimized config based on data characteristics
    prev_cb_params = previous_best.get("catboost", {}) if previous_best else {}
    cb_cfg = optimize_catboost_config(
        X_full=X_full,
        y_full=y_full,
        target_name=target_name,
        task_type="classification",
        horizon=horizon,
        base_config=config.cb_config,  # Use explicit config if provided
        enable_holdout_validation=len(X_full) >= 300,
        enable_hyperparameter_refinement=True,  # Stage 4: quality over speed
        previous_best=prev_cb_params,  # Warm-start from previous step
    )
    # Apply dynamic embargo
    cb_cfg.embargo_bars = get_embargo_for_horizon(horizon)

    # =========================================================================
    # LIGHTGBM CONFIG: Use dynamic optimization
    # =========================================================================
    lgb_cfg = optimize_lightgbm_config(
        X_full=X_full,
        y_full=y_full,
        target_name=target_name,
        task_type="classification",
        horizon=horizon,
        base_config=config.lgb_config,  # Use explicit config if provided
    )
    lgb_cfg.embargo_bars = get_embargo_for_horizon(horizon)

    # =========================================================================
    # LSTM CONFIG: Use dynamic optimization
    # =========================================================================
    lstm_cfg = optimize_lstm_config(
        X_full=X_full,
        y_full=y_full,
        target_name=target_name,
        task_type="classification",
        horizon=horizon,
        base_config=config.lstm_config,  # Use explicit config if provided
    )
    lstm_cfg.embargo_bars = get_embargo_for_horizon(horizon)

    # =========================================================================
    # LINEAR CONFIG: Use dynamic optimization
    # =========================================================================
    linear_cfg = optimize_linear_config(
        X_full=X_full,
        y_full=y_full,
        target_name=target_name,
        task_type="classification",
        horizon=horizon,
        base_config=config.linear_config,  # Use explicit config if provided
    )
    linear_cfg.embargo_bars = get_embargo_for_horizon(horizon)

    # =========================================================================
    # EXTRACT PER-MODEL SPLITS
    # =========================================================================
    cb_X_train, cb_y_train, cb_X_val, cb_y_val, cb_X_cal, cb_y_cal = (
        extract_per_model_splits(X_full, y_full, cb_cfg, full_window_size)
    )
    lgb_X_train, lgb_y_train, lgb_X_val, lgb_y_val, lgb_X_cal, lgb_y_cal = (
        extract_per_model_splits(X_full, y_full, lgb_cfg, full_window_size)
    )
    lstm_X_train, lstm_y_train, lstm_X_val, lstm_y_val, lstm_X_cal, lstm_y_cal = (
        extract_per_model_splits(X_full, y_full, lstm_cfg, full_window_size)
    )
    (
        linear_X_train,
        linear_y_train,
        linear_X_val,
        linear_y_val,
        linear_X_cal,
        linear_y_cal,
    ) = extract_per_model_splits(X_full, y_full, linear_cfg, full_window_size)

    # =========================================================================
    # CHECK FOR SUFFICIENT DATA
    # =========================================================================
    min_classes = min(
        len(np.unique(cb_y_train)),
        len(np.unique(lgb_y_train)),
        len(np.unique(lstm_y_train)),
        len(np.unique(linear_y_train)),
    )
    if min_classes < 2:
        majority_class = int(linear_y_train.mode().iloc[0])
        return (
            majority_class,
            None,
            None,
            {"models_trained": False, "n_train_classes": min_classes},
            previous_best or {},
        )

    # =========================================================================
    # APPLY PER-MODEL FEATURE SELECTION (each model uses its own method)
    # =========================================================================
    cb_features = select_features_catboost(
        cb_X_train,
        cb_y_train,
        cb_cfg,
        n_classes,
    )
    lgb_features = select_features_lightgbm(
        lgb_X_train,
        lgb_y_train,
        lgb_cfg,
        n_classes,
    )
    lstm_features = select_features_lstm(
        lstm_X_train,
        lstm_y_train,
        lstm_cfg,
        n_classes,
    )
    linear_features = select_features_linear(
        linear_X_train,
        linear_y_train,
        linear_cfg,
        n_classes,
    )

    # Apply feature selection to all splits
    cb_X_train_sel = cb_X_train[cb_features]
    cb_X_val_sel = cb_X_val[cb_features]
    cb_X_cal_sel = cb_X_cal[cb_features]
    X_pred_cb = X_pred[cb_features]

    lgb_X_train_sel = lgb_X_train[lgb_features]
    lgb_X_val_sel = lgb_X_val[lgb_features]
    lgb_X_cal_sel = lgb_X_cal[lgb_features]
    X_pred_lgb = X_pred[lgb_features]

    lstm_X_train_sel = lstm_X_train[lstm_features]
    lstm_X_val_sel = lstm_X_val[lstm_features]
    lstm_X_cal_sel = lstm_X_cal[lstm_features]
    X_pred_lstm = X_pred[lstm_features]

    linear_X_train_sel = linear_X_train[linear_features]
    linear_X_val_sel = linear_X_val[linear_features]
    linear_X_cal_sel = linear_X_cal[linear_features]
    X_pred_linear = X_pred[linear_features]

    # =========================================================================
    # TRAIN AND PREDICT USING NEW MODEL MODULES
    # =========================================================================
    prev_cb = previous_best.get("catboost", {}) if previous_best else {}
    prev_lgb = previous_best.get("lightgbm", {}) if previous_best else {}
    prev_lstm = previous_best.get("lstm", {}) if previous_best else {}
    prev_linear = previous_best.get("linear", {}) if previous_best else {}

    cb_result = cb_train_predict_cls(
        cb_X_train_sel,
        cb_y_train,
        cb_X_val_sel,
        cb_y_val,
        cb_X_cal_sel,
        cb_y_cal,
        X_pred_cb,
        config=cb_cfg,
        n_classes=n_classes,
        tune=config.enable_optuna,
        previous_best=prev_cb,
    )

    lgb_result = lgb_train_predict_cls(
        lgb_X_train_sel,
        lgb_y_train,
        lgb_X_val_sel,
        lgb_y_val,
        lgb_X_cal_sel,
        lgb_y_cal,
        X_pred_lgb,
        config=lgb_cfg,
        n_classes=n_classes,
        tune=config.enable_optuna,
        previous_best=prev_lgb,
    )

    lstm_result = lstm_train_predict_cls(
        lstm_X_train_sel,
        lstm_y_train,
        lstm_X_val_sel,
        lstm_y_val,
        lstm_X_cal_sel,
        lstm_y_cal,
        X_pred_lstm,
        config=lstm_cfg,
        n_classes=n_classes,
        tune=config.enable_optuna,
        previous_best=prev_lstm,
    )

    linear_result = linear_train_predict_cls(
        linear_X_train_sel,
        linear_y_train,
        linear_X_val_sel,
        linear_y_val,
        linear_X_cal_sel,
        linear_y_cal,
        X_pred_linear,
        config=linear_cfg,
        n_classes=n_classes,
        tune=config.enable_optuna,
        previous_best=prev_linear,
    )

    # =========================================================================
    # ENSEMBLE PREDICTIONS
    # =========================================================================
    linear_weight = max(
        0.0, 1.0 - config.cb_weight - config.lgb_weight - config.lstm_weight
    )

    # Get probabilities from each model
    cb_probs = cb_result.probabilities
    lgb_probs = lgb_result.probabilities
    lstm_probs = lstm_result.probabilities
    linear_probs = linear_result.probabilities

    # Ensure all probability arrays have same shape
    max_classes = max(
        len(cb_probs) if cb_probs is not None else 0,
        len(lgb_probs) if lgb_probs is not None else 0,
        len(lstm_probs) if lstm_probs is not None else 0,
        len(linear_probs) if linear_probs is not None else 0,
        n_classes,
    )

    def _pad_probs(probs: np.ndarray | None, target_len: int) -> np.ndarray:
        if probs is None:
            return np.ones(target_len) / target_len  # Uniform
        if len(probs) < target_len:
            padded = np.zeros(target_len)
            padded[: len(probs)] = probs
            return padded
        return probs[:target_len]

    cb_probs = _pad_probs(cb_probs, max_classes)
    lgb_probs = _pad_probs(lgb_probs, max_classes)
    lstm_probs = _pad_probs(lstm_probs, max_classes)
    linear_probs = _pad_probs(linear_probs, max_classes)

    # Weighted ensemble
    ensemble_probs = (
        config.cb_weight * cb_probs
        + config.lgb_weight * lgb_probs
        + config.lstm_weight * lstm_probs
        + linear_weight * linear_probs
    )

    y_pred = int(np.argmax(ensemble_probs))
    y_prob = ensemble_probs

    # =========================================================================
    # CONFORMAL PREDICTION
    # =========================================================================
    prediction_set = None
    conformal_threshold = None

    if is_binary and len(linear_X_cal_sel) > 10:
        try:
            # Use trained models' calibration predictions
            cb_cal_probs = cb_result.trained_model.predict_proba(cb_X_cal_sel)[:, 1]
            lgb_cal_probs = lgb_result.trained_model.predict_proba(lgb_X_cal_sel)[:, 1]
            linear_cal_probs = linear_result.trained_model.predict_proba(
                linear_X_cal_sel
            )[:, 1]

            n_cal = min(len(cb_X_cal_sel), len(lgb_X_cal_sel), len(linear_X_cal_sel))
            ensemble_cal_probs = (
                config.cb_weight * cb_cal_probs[:n_cal]
                + config.lgb_weight * lgb_cal_probs[:n_cal]
                + linear_weight * linear_cal_probs[:n_cal]
            )
            ensemble_cal_probs = ensemble_cal_probs / (1 - config.lstm_weight)

            cal_probs_full = np.column_stack(
                [1 - ensemble_cal_probs, ensemble_cal_probs]
            )
            y_cal_use = linear_y_cal.iloc[:n_cal].astype(int)
            y_cal_clipped = np.clip(y_cal_use, 0, 1)
            scores = 1 - cal_probs_full[np.arange(n_cal), y_cal_clipped]
            conformal_threshold = float(np.quantile(scores, 1 - config.conformal_alpha))
            prediction_set = (1 - y_prob) <= conformal_threshold
        except Exception:
            pass

    # =========================================================================
    # BUILD COMPONENTS DICT
    # =========================================================================
    model_agreement = int(
        cb_result.prediction
        == lgb_result.prediction
        == lstm_result.prediction
        == linear_result.prediction
    )
    ensemble_confidence = (
        float(np.max(y_prob)) if len(y_prob) > 2 else abs(y_prob[1] - 0.5) * 2
    )

    components = {
        "models_trained": True,
        "per_model_training": True,
        # Individual predictions
        "cb_pred": cb_result.prediction,
        "lgb_pred": lgb_result.prediction,
        "lstm_pred": lstm_result.prediction,
        "linear_pred": linear_result.prediction,
        # Ensemble metrics
        "y_prob": float(y_prob[1]) if is_binary else None,
        "ensemble_confidence": ensemble_confidence,
        "model_agreement": model_agreement,
        "conformal_threshold": conformal_threshold,
        # Weights used
        "cb_weight_used": config.cb_weight,
        "lgb_weight_used": config.lgb_weight,
        "lstm_weight_used": config.lstm_weight,
        "linear_weight_used": linear_weight,
        # Per-model metadata
        "cb_n_features": len(cb_features),
        "lgb_n_features": len(lgb_features),
        "lstm_n_features": len(lstm_features),
        "linear_n_features": len(linear_features),
        "cb_train_time": cb_result.metrics.get("train_time", 0),
        "lgb_train_time": lgb_result.metrics.get("train_time", 0),
        "lstm_train_time": lstm_result.metrics.get("train_time", 0),
        "linear_train_time": linear_result.metrics.get("train_time", 0),
        "cb_n_train": cb_result.train_size,
        "lgb_n_train": lgb_result.train_size,
        "lstm_n_train": lstm_result.train_size,
        "linear_n_train": linear_result.train_size,
    }

    # Tuned params for warm-starting
    tuned_params = {
        "catboost": cb_result.best_params,
        "lightgbm": lgb_result.best_params,
        "lstm": lstm_result.best_params,
        "linear": linear_result.best_params,
    }

    return y_pred, y_prob, prediction_set, components, tuned_params


def train_predict_regression_permodel(
    X_full: pd.DataFrame,
    y_full: pd.Series,
    X_pred: pd.DataFrame,
    y_true: float,
    config: SyncBacktestConfig,
    horizon: int,
    previous_best: dict[str, dict[str, Any]] | None = None,
    target_name: str = "",
    timestamps: np.ndarray | None = None,
    pred_timestamp: Any = None,
    target_timestamp: Any = None,
) -> tuple[
    float, tuple[float, float] | None, bool, dict[str, Any], dict[str, dict[str, Any]]
]:
    """Train 4-model ensemble regressor with TRUE per-model windows and features.

    Uses new model modules for each model's training/prediction pipeline.

    Args:
        X_full: Full feature window (max window size)
        y_full: Full target window
        X_pred: Single row to predict
        y_true: True value (for conformal coverage check)
        config: Backtest configuration
        horizon: Target horizon (for dynamic embargo)
        previous_best: Previous best hyperparameters
        target_name: Target identifier (e.g., 'volatility_1bar')
        timestamps: Timestamps array for the window (for date printing)
        pred_timestamp: Timestamp of prediction point
        target_timestamp: Timestamp of target (horizon bars ahead)

    Returns:
        y_pred: Predicted value
        interval: Conformal prediction interval (lower, upper)
        covered: Whether y_true is in interval
        components: Individual model predictions + metadata
        tuned_params: Best hyperparameters
    """
    full_window_size = len(X_full)

    # Print config header for this target with dates
    print(f"\n{'~' * 70}")
    print(f"  CONFIG: {target_name} (regression, horizon={horizon})")
    print(f"  Window: {full_window_size} samples, Features: {len(X_full.columns)}")
    if timestamps is not None and len(timestamps) > 0:
        print(f"  Window Dates: {timestamps[0]} → {timestamps[-1]}")
    if pred_timestamp is not None:
        print(f"  Prediction Date: {pred_timestamp}")
    if target_timestamp is not None:
        print(f"  Target Date: {target_timestamp} (+{horizon} bars)")
    print(f"{'~' * 70}")

    # =========================================================================
    # CATBOOST CONFIG: Use dynamic optimization (ALL 4 STAGES)
    # =========================================================================
    prev_cb_params = previous_best.get("catboost", {}) if previous_best else {}
    cb_cfg = optimize_catboost_config(
        X_full=X_full,
        y_full=y_full,
        target_name=target_name,
        task_type="regression",
        horizon=horizon,
        base_config=config.cb_config,
        enable_holdout_validation=len(X_full) >= 300,
        enable_hyperparameter_refinement=True,  # Stage 4: quality over speed
        previous_best=prev_cb_params,  # Warm-start from previous step
    )
    cb_cfg.embargo_bars = get_embargo_for_horizon(horizon)

    # =========================================================================
    # LIGHTGBM CONFIG: Use dynamic optimization
    # =========================================================================
    lgb_cfg = optimize_lightgbm_config(
        X_full=X_full,
        y_full=y_full,
        target_name=target_name,
        task_type="regression",
        horizon=horizon,
        base_config=config.lgb_config,
    )
    lgb_cfg.embargo_bars = get_embargo_for_horizon(horizon)

    # =========================================================================
    # LSTM CONFIG: Use dynamic optimization
    # =========================================================================
    lstm_cfg = optimize_lstm_config(
        X_full=X_full,
        y_full=y_full,
        target_name=target_name,
        task_type="regression",
        horizon=horizon,
        base_config=config.lstm_config,
    )
    lstm_cfg.embargo_bars = get_embargo_for_horizon(horizon)

    # =========================================================================
    # LINEAR CONFIG: Use dynamic optimization
    # =========================================================================
    linear_cfg = optimize_linear_config(
        X_full=X_full,
        y_full=y_full,
        target_name=target_name,
        task_type="regression",
        horizon=horizon,
        base_config=config.linear_config,
    )
    linear_cfg.embargo_bars = get_embargo_for_horizon(horizon)

    # =========================================================================
    # EXTRACT PER-MODEL SPLITS
    # =========================================================================
    cb_X_train, cb_y_train, cb_X_val, cb_y_val, cb_X_cal, cb_y_cal = (
        extract_per_model_splits(X_full, y_full, cb_cfg, full_window_size)
    )
    lgb_X_train, lgb_y_train, lgb_X_val, lgb_y_val, lgb_X_cal, lgb_y_cal = (
        extract_per_model_splits(X_full, y_full, lgb_cfg, full_window_size)
    )
    lstm_X_train, lstm_y_train, lstm_X_val, lstm_y_val, lstm_X_cal, lstm_y_cal = (
        extract_per_model_splits(X_full, y_full, lstm_cfg, full_window_size)
    )
    (
        linear_X_train,
        linear_y_train,
        linear_X_val,
        linear_y_val,
        linear_X_cal,
        linear_y_cal,
    ) = extract_per_model_splits(X_full, y_full, linear_cfg, full_window_size)

    # =========================================================================
    # APPLY PER-MODEL FEATURE SELECTION (each model uses its own method)
    # =========================================================================
    cb_features = select_features_catboost_regression(
        cb_X_train,
        cb_y_train,
        cb_cfg,
    )
    lgb_features = select_features_lightgbm_regression(
        lgb_X_train,
        lgb_y_train,
        lgb_cfg,
    )
    # LSTM and Linear use same method for classification and regression
    lstm_features = select_features_lstm(
        lstm_X_train,
        lstm_y_train,
        lstm_cfg,
        n_classes=2,  # Not used for LSTM but keep API consistent
    )
    linear_features = select_features_linear(
        linear_X_train,
        linear_y_train,
        linear_cfg,
        n_classes=2,  # Not used for Linear but keep API consistent
    )

    # Apply selection
    cb_X_train_sel, cb_X_val_sel = cb_X_train[cb_features], cb_X_val[cb_features]
    cb_X_cal_sel, X_pred_cb = cb_X_cal[cb_features], X_pred[cb_features]

    lgb_X_train_sel, lgb_X_val_sel = lgb_X_train[lgb_features], lgb_X_val[lgb_features]
    lgb_X_cal_sel, X_pred_lgb = lgb_X_cal[lgb_features], X_pred[lgb_features]

    lstm_X_train_sel, lstm_X_val_sel = (
        lstm_X_train[lstm_features],
        lstm_X_val[lstm_features],
    )
    lstm_X_cal_sel, X_pred_lstm = lstm_X_cal[lstm_features], X_pred[lstm_features]

    linear_X_train_sel, linear_X_val_sel = (
        linear_X_train[linear_features],
        linear_X_val[linear_features],
    )
    linear_X_cal_sel, X_pred_linear = (
        linear_X_cal[linear_features],
        X_pred[linear_features],
    )

    # =========================================================================
    # TRAIN AND PREDICT USING NEW MODEL MODULES
    # =========================================================================
    prev_cb = previous_best.get("catboost", {}) if previous_best else {}
    prev_lgb = previous_best.get("lightgbm", {}) if previous_best else {}
    prev_lstm = previous_best.get("lstm", {}) if previous_best else {}
    prev_linear = previous_best.get("linear", {}) if previous_best else {}

    cb_result = cb_train_predict_reg(
        cb_X_train_sel,
        cb_y_train,
        cb_X_val_sel,
        cb_y_val,
        cb_X_cal_sel,
        cb_y_cal,
        X_pred_cb,
        config=cb_cfg,
        tune=config.enable_optuna,
        previous_best=prev_cb,
    )

    lgb_result = lgb_train_predict_reg(
        lgb_X_train_sel,
        lgb_y_train,
        lgb_X_val_sel,
        lgb_y_val,
        lgb_X_cal_sel,
        lgb_y_cal,
        X_pred_lgb,
        config=lgb_cfg,
        tune=config.enable_optuna,
        previous_best=prev_lgb,
    )

    lstm_result = lstm_train_predict_reg(
        lstm_X_train_sel,
        lstm_y_train,
        lstm_X_val_sel,
        lstm_y_val,
        lstm_X_cal_sel,
        lstm_y_cal,
        X_pred_lstm,
        config=lstm_cfg,
        tune=config.enable_optuna,
        previous_best=prev_lstm,
    )

    linear_result = linear_train_predict_reg(
        linear_X_train_sel,
        linear_y_train,
        linear_X_val_sel,
        linear_y_val,
        linear_X_cal_sel,
        linear_y_cal,
        X_pred_linear,
        config=linear_cfg,
        tune=config.enable_optuna,
        previous_best=prev_linear,
    )

    # =========================================================================
    # ENSEMBLE PREDICTIONS
    # =========================================================================
    linear_weight = max(
        0.0, 1.0 - config.cb_weight - config.lgb_weight - config.lstm_weight
    )

    y_pred = (
        config.cb_weight * cb_result.prediction
        + config.lgb_weight * lgb_result.prediction
        + config.lstm_weight * lstm_result.prediction
        + linear_weight * linear_result.prediction
    )

    # =========================================================================
    # CONFORMAL PREDICTION
    # =========================================================================
    interval = None
    covered = False

    if len(linear_X_cal_sel) > 10:
        try:
            cb_cal_preds = cb_result.trained_model.predict(cb_X_cal_sel)
            lgb_cal_preds = lgb_result.trained_model.predict(lgb_X_cal_sel)
            linear_cal_preds = linear_result.trained_model.predict(linear_X_cal_sel)

            n_cal = min(len(cb_X_cal_sel), len(lgb_X_cal_sel), len(linear_X_cal_sel))
            ensemble_cal_preds = (
                config.cb_weight * cb_cal_preds[:n_cal]
                + config.lgb_weight * lgb_cal_preds[:n_cal]
                + linear_weight * linear_cal_preds[:n_cal]
            )
            ensemble_cal_preds = ensemble_cal_preds / (1 - config.lstm_weight)

            y_cal_use = linear_y_cal.iloc[:n_cal].values
            residuals = np.abs(y_cal_use - ensemble_cal_preds)
            threshold = float(np.quantile(residuals, 1 - config.conformal_alpha))
            interval = (float(y_pred - threshold), float(y_pred + threshold))
            covered = interval[0] <= y_true <= interval[1]
        except Exception:
            pass

    # =========================================================================
    # BUILD COMPONENTS DICT
    # =========================================================================
    components = {
        "models_trained": True,
        "per_model_training": True,
        "cb_pred": float(cb_result.prediction),
        "lgb_pred": float(lgb_result.prediction),
        "lstm_pred": float(lstm_result.prediction),
        "linear_pred": float(linear_result.prediction),
        "cb_weight_used": config.cb_weight,
        "lgb_weight_used": config.lgb_weight,
        "lstm_weight_used": config.lstm_weight,
        "linear_weight_used": linear_weight,
        "cb_n_features": len(cb_features),
        "lgb_n_features": len(lgb_features),
        "lstm_n_features": len(lstm_features),
        "linear_n_features": len(linear_features),
        "cb_train_time": cb_result.metrics.get("train_time", 0),
        "lgb_train_time": lgb_result.metrics.get("train_time", 0),
        "lstm_train_time": lstm_result.metrics.get("train_time", 0),
        "linear_train_time": linear_result.metrics.get("train_time", 0),
        "cb_n_train": cb_result.train_size,
        "lgb_n_train": lgb_result.train_size,
        "lstm_n_train": lstm_result.train_size,
        "linear_n_train": linear_result.train_size,
    }

    tuned_params = {
        "catboost": cb_result.best_params,
        "lightgbm": lgb_result.best_params,
        "lstm": lstm_result.best_params,
        "linear": linear_result.best_params,
    }

    return y_pred, interval, covered, components, tuned_params

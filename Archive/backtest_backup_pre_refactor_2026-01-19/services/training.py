"""
Training services for per-model ensemble learning.

Contains the main training functions that implement the per-model architecture
where each model (CatBoost, LightGBM, LSTM, Linear) gets its own:
- Training window (different sizes)
- Train/val/cal splits
- Feature selection
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd
import torch
from backtest.adapters.data_loader import get_embargo_for_horizon
from backtest.domain.config import PerModelConfig, SyncBacktestConfig
from backtest.models.lstm import train_lstm_classifier, train_lstm_regressor
from backtest.services.tuning import (
    tune_cb_classifier,
    tune_cb_regressor,
    tune_lgb_classifier,
    tune_lgb_regressor,
)
from catboost import CatBoostClassifier, CatBoostRegressor
from lightgbm import LGBMClassifier, LGBMRegressor
from sklearn.linear_model import LogisticRegression, Ridge

if TYPE_CHECKING:
    pass


__all__ = [
    "extract_per_model_splits",
    "train_predict_classification_permodel",
    "train_predict_regression_permodel",
]


def apply_feature_selection(
    X: pd.DataFrame,
    method: str,
    model: Any = None,
    ratio: float = 0.5,
    min_features: int = 20,
) -> tuple[pd.DataFrame, list[str]]:
    """Apply feature selection to reduce feature set.

    Args:
        X: Feature DataFrame
        method: Selection method ('variance', 'importance')
        model: Trained model for importance-based selection
        ratio: Fraction of features to keep
        min_features: Minimum number of features to keep

    Returns:
        Tuple of (selected X, selected feature names)
    """
    n_features = len(X.columns)
    n_keep = max(min_features, int(n_features * ratio))

    if method == "variance":
        variances = X.var()
        selected_features = variances.nlargest(n_keep).index.tolist()
    elif method == "importance" and model is not None:
        if hasattr(model, "feature_importances_"):
            importances = model.feature_importances_
        elif hasattr(model, "get_feature_importance"):
            importances = model.get_feature_importance()
        else:
            # Fallback to variance
            variances = X.var()
            selected_features = variances.nlargest(n_keep).index.tolist()
            return X[selected_features], selected_features

        # Get top features by importance
        feature_names = X.columns.tolist()
        sorted_idx = np.argsort(importances)[::-1]
        selected_features = [feature_names[i] for i in sorted_idx[:n_keep]]
    else:
        # No selection - keep all
        selected_features = X.columns.tolist()

    return X[selected_features], selected_features


def extract_per_model_splits(
    X_full: pd.DataFrame,
    y_full: pd.Series,
    model_config: PerModelConfig,
    full_window_size: int,
) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series, pd.DataFrame, pd.Series]:
    """Extract train/val/cal splits for a specific model from full window.

    The full window has `full_window_size` rows. The model's config specifies
    a (potentially smaller) `train_window`. We take the MOST RECENT data
    to respect temporal ordering.

    Args:
        X_full: Full feature window (full_window_size rows)
        y_full: Full target window (full_window_size rows)
        model_config: Configuration for this specific model
        full_window_size: Size of the full window (should match len(X_full))

    Returns:
        X_train, y_train, X_val, y_val, X_cal, y_cal - per-model splits
    """
    model_window = model_config.train_window

    # If model window equals full window, use all data
    # Otherwise, use the MOST RECENT `model_window` rows
    if model_window >= full_window_size:
        start_offset = 0
    else:
        start_offset = full_window_size - model_window

    # Extract model's window
    X_model = X_full.iloc[start_offset:]
    y_model = y_full.iloc[start_offset:]

    # Calculate split sizes with embargo
    total_embargo = 2 * model_config.embargo_bars
    usable_window = len(X_model) - total_embargo
    train_size = int(usable_window * model_config.train_ratio)
    val_size = int(usable_window * model_config.val_ratio)
    cal_size = usable_window - train_size - val_size

    # Split with embargo gaps
    train_end = train_size
    val_start = train_end + model_config.embargo_bars
    val_end = val_start + val_size
    cal_start = val_end + model_config.embargo_bars
    cal_end = cal_start + cal_size

    X_train = X_model.iloc[:train_end]
    y_train = y_model.iloc[:train_end]
    X_val = X_model.iloc[val_start:val_end]
    y_val = y_model.iloc[val_start:val_end]
    X_cal = X_model.iloc[cal_start:cal_end]
    y_cal = y_model.iloc[cal_start:cal_end]

    return X_train, y_train, X_val, y_val, X_cal, y_cal


def train_predict_classification_permodel(
    X_full: pd.DataFrame,
    y_full: pd.Series,
    X_pred: pd.DataFrame,
    config: SyncBacktestConfig,
    n_classes: int,
    horizon: int,
    previous_best: dict[str, dict[str, Any]] | None = None,
) -> tuple[
    int, np.ndarray | None, np.ndarray | None, dict[str, Any], dict[str, dict[str, Any]]
]:
    """Train 4-model ensemble classifier with TRUE per-model windows and features.

    Each model (CatBoost, LightGBM, LSTM, Linear) gets:
    - Its own training window (extracted from X_full based on model config)
    - Its own train/val/cal splits (based on model-specific ratios)
    - Its own feature selection (based on model-specific method)

    All models predict the same X_pred point (alignment guaranteed).

    Architecture:
    - X_full has 800 rows (Linear's window = max window)
    - CB/LGB extract their 400-row window from end of X_full
    - LSTM extracts its 600-row window from end of X_full
    - Linear uses full 800 rows
    - All predict the same next bar (X_pred)

    Args:
        X_full: Full feature window (max window size)
        y_full: Full target window
        X_pred: Single row to predict
        config: Backtest configuration
        n_classes: Number of classes
        horizon: Target horizon (for dynamic embargo)
        previous_best: Previous best hyperparameters for warm-starting

    Returns:
        y_pred: Predicted class
        y_prob: Class probabilities
        prediction_set: Conformal prediction set
        components: Individual model predictions + metadata
        tuned_params: Best hyperparameters (for warm-starting next step)
    """
    import time as time_module

    full_window_size = len(X_full)
    feature_cols = X_full.columns.tolist()

    # Get per-model configs
    cb_cfg = config.get_model_config("cb")
    lgb_cfg = config.get_model_config("lgb")
    lstm_cfg = config.get_model_config("lstm")
    linear_cfg = config.get_model_config("linear")

    # Override embargo_bars based on target horizon (dynamic embargo)
    # Formula: embargo = 3 * horizon, capped at 36
    dynamic_embargo = get_embargo_for_horizon(horizon)
    cb_cfg.embargo_bars = dynamic_embargo
    lgb_cfg.embargo_bars = dynamic_embargo
    lstm_cfg.embargo_bars = dynamic_embargo
    linear_cfg.embargo_bars = dynamic_embargo

    # Default params for tuning/warm-start
    default_params = {
        "catboost": {
            "iterations": config.n_estimators,
            "depth": config.max_depth,
            "learning_rate": config.cb_learning_rate,
            "l2_leaf_reg": config.cb_l2_leaf_reg,
        },
        "lightgbm": {
            "n_estimators": config.n_estimators,
            "max_depth": config.max_depth,
            "learning_rate": config.lgb_learning_rate,
            "reg_lambda": config.lgb_reg_lambda,
        },
    }

    # =========================================================================
    # EXTRACT PER-MODEL SPLITS
    # =========================================================================
    # Each model gets its own window extracted from end of X_full

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
    unique_classes_cb = np.unique(cb_y_train)
    unique_classes_lgb = np.unique(lgb_y_train)
    unique_classes_lstm = np.unique(lstm_y_train)
    unique_classes_linear = np.unique(linear_y_train)

    # Early exit if any model has single class
    min_classes = min(
        len(unique_classes_cb),
        len(unique_classes_lgb),
        len(unique_classes_lstm),
        len(unique_classes_linear),
    )
    if min_classes < 2:
        # Use majority class from largest window (most data)
        majority_class = int(linear_y_train.mode().iloc[0])
        return (
            majority_class,
            None,
            None,
            {
                "models_trained": False,
                "n_train_classes": min_classes,
                "cb_pred": majority_class,
                "lgb_pred": majority_class,
                "lstm_pred": majority_class,
                "linear_pred": majority_class,
            },
            previous_best or default_params,
        )

    is_binary = n_classes == 2

    # =========================================================================
    # APPLY PER-MODEL FEATURE SELECTION
    # =========================================================================
    # Train a quick model to get importances for CB/LGB, use variance for LSTM

    cb_features = feature_cols  # Start with all features
    lgb_features = feature_cols
    lstm_features = feature_cols
    linear_features = feature_cols

    # CatBoost feature selection (importance-based after quick fit)
    if cb_cfg.feature_selection == "importance":
        # Train a quick CatBoost to get feature importances
        quick_cb = CatBoostClassifier(
            iterations=50,
            depth=4,
            learning_rate=0.1,
            loss_function="Logloss" if is_binary else "MultiClass",
            task_type="GPU",
            devices="0",
            verbose=False,
            random_seed=config.random_state,
        )
        quick_cb.fit(cb_X_train, cb_y_train)
        cb_features = apply_feature_selection(
            cb_X_train,
            "importance",
            model=quick_cb,
            ratio=cb_cfg.feature_selection_ratio,
            min_features=20,
        )[1]
    elif cb_cfg.feature_selection == "variance":
        _, cb_features = apply_feature_selection(
            cb_X_train,
            "variance",
            ratio=cb_cfg.feature_selection_ratio,
            min_features=20,
        )

    # LightGBM feature selection (importance-based after quick fit)
    if lgb_cfg.feature_selection == "importance":
        quick_lgb = LGBMClassifier(
            n_estimators=50,
            max_depth=4,
            learning_rate=0.1,
            objective="binary" if is_binary else "multiclass",
            device="gpu",
            verbose=-1,
            random_state=config.random_state,
        )
        quick_lgb.fit(lgb_X_train, lgb_y_train)
        lgb_features = apply_feature_selection(
            lgb_X_train,
            "importance",
            model=quick_lgb,
            ratio=lgb_cfg.feature_selection_ratio,
            min_features=20,
        )[1]
    elif lgb_cfg.feature_selection == "variance":
        _, lgb_features = apply_feature_selection(
            lgb_X_train,
            "variance",
            ratio=lgb_cfg.feature_selection_ratio,
            min_features=20,
        )

    # LSTM feature selection (variance-based - sensitive to scale)
    if lstm_cfg.feature_selection == "variance":
        _, lstm_features = apply_feature_selection(
            lstm_X_train,
            "variance",
            ratio=lstm_cfg.feature_selection_ratio,
            min_features=20,
        )

    # Linear feature selection (variance-based)
    if linear_cfg.feature_selection == "variance":
        _, linear_features = apply_feature_selection(
            linear_X_train,
            "variance",
            ratio=linear_cfg.feature_selection_ratio,
            min_features=20,
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
    # TUNE HYPERPARAMETERS (using each model's own validation set)
    # =========================================================================
    # Note: Tuning uses each model's own train/val split

    tuned_params = previous_best or default_params.copy()

    if config.enable_optuna:
        # Tune CatBoost on CB's train/val
        cb_params = tune_cb_classifier(
            cb_X_train_sel,
            cb_y_train,
            cb_X_val_sel,
            cb_y_val,
            config,
            is_binary,
            previous_best.get("catboost") if previous_best else None,
        )
        tuned_params["catboost"] = cb_params

        # Tune LightGBM on LGB's train/val
        lgb_params = tune_lgb_classifier(
            lgb_X_train_sel,
            lgb_y_train,
            lgb_X_val_sel,
            lgb_y_val,
            config,
            is_binary,
            previous_best.get("lightgbm") if previous_best else None,
        )
        tuned_params["lightgbm"] = lgb_params
    else:
        cb_params = tuned_params.get("catboost", default_params["catboost"])
        lgb_params = tuned_params.get("lightgbm", default_params["lightgbm"])

    # =========================================================================
    # TRAIN MODELS (each on its own train+val combined)
    # =========================================================================
    train_times = {}

    # Combine train + val for final training (more data after tuning)
    cb_X_full = pd.concat([cb_X_train_sel, cb_X_val_sel], ignore_index=True)
    cb_y_full = pd.concat([cb_y_train, cb_y_val], ignore_index=True)

    lgb_X_full = pd.concat([lgb_X_train_sel, lgb_X_val_sel], ignore_index=True)
    lgb_y_full = pd.concat([lgb_y_train, lgb_y_val], ignore_index=True)

    lstm_X_full = pd.concat([lstm_X_train_sel, lstm_X_val_sel], ignore_index=True)
    lstm_y_full = pd.concat([lstm_y_train, lstm_y_val], ignore_index=True)
    # LSTM-ONLY FIX: Extended sequence for prediction includes cal FEATURES
    # This reduces the gap from ~93 bars to ~3 bars (embargo only)
    # Training still uses only train+val (lstm_X_full/lstm_y_full)
    # No target leakage: we only use X_cal features, never y_cal
    lstm_X_full_for_seq = pd.concat(
        [lstm_X_train_sel, lstm_X_val_sel, lstm_X_cal_sel], ignore_index=True
    )

    linear_X_full = pd.concat([linear_X_train_sel, linear_X_val_sel], ignore_index=True)
    linear_y_full = pd.concat([linear_y_train, linear_y_val], ignore_index=True)

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*GPU memory available.*")
        warnings.filterwarnings("ignore", category=UserWarning)

        # --- CatBoost ---
        t0 = time_module.time()
        cb_model = CatBoostClassifier(
            iterations=cb_params.get("iterations", config.n_estimators),
            depth=cb_params.get("depth", config.max_depth),
            learning_rate=cb_params.get("learning_rate", config.cb_learning_rate),
            l2_leaf_reg=cb_params.get("l2_leaf_reg", config.cb_l2_leaf_reg),
            loss_function="Logloss" if is_binary else "MultiClass",
            task_type="GPU",
            devices="0",
            verbose=False,
            random_seed=config.random_state,
        )
        cb_model.fit(cb_X_full, cb_y_full)
        train_times["cb"] = time_module.time() - t0

        # --- LightGBM ---
        t0 = time_module.time()
        if is_binary:
            lgb_model = LGBMClassifier(
                n_estimators=lgb_params.get("n_estimators", config.n_estimators),
                max_depth=lgb_params.get("max_depth", config.max_depth),
                learning_rate=lgb_params.get("learning_rate", config.lgb_learning_rate),
                reg_lambda=lgb_params.get("reg_lambda", config.lgb_reg_lambda),
                min_child_samples=config.lgb_min_child_samples,
                objective="binary",
                metric="auc",
                device="gpu",
                verbose=-1,
                random_state=config.random_state,
            )
        else:
            n_actual_classes = len(np.unique(lgb_y_full))
            lgb_model = LGBMClassifier(
                n_estimators=lgb_params.get("n_estimators", config.n_estimators),
                max_depth=lgb_params.get("max_depth", config.max_depth),
                learning_rate=lgb_params.get("learning_rate", config.lgb_learning_rate),
                reg_lambda=lgb_params.get("reg_lambda", config.lgb_reg_lambda),
                min_child_samples=config.lgb_min_child_samples,
                objective="multiclass",
                metric="multi_logloss",
                num_class=n_actual_classes,
                device="gpu",
                verbose=-1,
                random_state=config.random_state,
            )
        lgb_model.fit(lgb_X_full, lgb_y_full)
        train_times["lgb"] = time_module.time() - t0

        # --- Linear ---
        t0 = time_module.time()
        linear_model = LogisticRegression(
            max_iter=1000, random_state=config.random_state, n_jobs=-1
        )
        linear_model.fit(linear_X_full, linear_y_full)
        train_times["linear"] = time_module.time() - t0

        # --- LSTM ---
        t0 = time_module.time()
        lstm_model, lstm_scaler, lstm_seq_len = train_lstm_classifier(
            lstm_X_full.values,
            lstm_y_full.values,
            n_classes=n_classes,
            hidden_size=config.lstm_hidden_size,
            num_layers=config.lstm_num_layers,
            lr=config.lstm_lr,
            epochs=config.lstm_epochs,
            batch_size=config.lstm_batch_size,
            device="cuda" if torch.cuda.is_available() else "cpu",
            seq_len=config.lstm_seq_len,
        )
        train_times["lstm"] = time_module.time() - t0

    # =========================================================================
    # GET PREDICTIONS
    # =========================================================================
    if is_binary:
        cb_prob = cb_model.predict_proba(X_pred_cb)[0, 1]
        lgb_prob = lgb_model.predict_proba(X_pred_lgb)[0, 1]
        linear_prob = linear_model.predict_proba(X_pred_linear)[0, 1]

        # LSTM prediction with proper sequence (using extended sequence for continuity)
        with torch.no_grad():
            # Use lstm_X_full_for_seq (train+val+cal features) for sequence building
            # This reduces gap from ~93 bars to ~3 bars (embargo only)
            if len(lstm_X_full_for_seq) >= lstm_seq_len - 1:
                X_pred_seq = np.vstack(
                    [
                        lstm_X_full_for_seq.values[-(lstm_seq_len - 1) :],
                        X_pred_lstm.values,
                    ]
                )
            else:
                n_hist = len(lstm_X_full_for_seq)
                n_pad = lstm_seq_len - 1 - n_hist
                X_pred_seq = np.vstack(
                    [
                        np.zeros((n_pad, X_pred_lstm.shape[1])),
                        lstm_X_full_for_seq.values,
                        X_pred_lstm.values,
                    ]
                )
            X_pred_scaled = lstm_scaler.transform(X_pred_seq)
            X_pred_tensor = torch.tensor(
                X_pred_scaled.reshape(1, lstm_seq_len, -1), dtype=torch.float32
            ).to(next(lstm_model.parameters()).device)
            lstm_logits = lstm_model(X_pred_tensor)
            lstm_probs_full = torch.softmax(lstm_logits, dim=1).cpu().numpy()[0]
            lstm_prob = float(lstm_probs_full[1])

        # Weighted ensemble
        linear_weight = max(
            0.0, 1.0 - config.cb_weight - config.lgb_weight - config.lstm_weight
        )
        ensemble_prob = (
            config.cb_weight * cb_prob
            + config.lgb_weight * lgb_prob
            + config.lstm_weight * lstm_prob
            + linear_weight * linear_prob
        )
        y_pred = int(ensemble_prob > 0.5)
        y_prob = np.array([1 - ensemble_prob, ensemble_prob])

        # Model predictions for components
        cb_pred_val = int(cb_prob > 0.5)
        lgb_pred_val = int(lgb_prob > 0.5)
        lstm_pred_val = int(lstm_prob > 0.5)
        linear_pred_val = int(linear_prob > 0.5)

        # Conformal prediction using Linear's calibration set (largest)
        prediction_set = None
        conformal_threshold = None
        if len(linear_X_cal_sel) > 10:
            try:
                cb_cal_probs = cb_model.predict_proba(cb_X_cal_sel)[:, 1]
                lgb_cal_probs = lgb_model.predict_proba(lgb_X_cal_sel)[:, 1]
                linear_cal_probs = linear_model.predict_proba(linear_X_cal_sel)[:, 1]

                # LSTM cal probs (simplified - use Linear's cal set size)
                # Note: This is an approximation since cal sets have different sizes
                n_cal = min(
                    len(cb_X_cal_sel), len(lgb_X_cal_sel), len(linear_X_cal_sel)
                )
                ensemble_cal_probs = (
                    config.cb_weight * cb_cal_probs[:n_cal]
                    + config.lgb_weight * lgb_cal_probs[:n_cal]
                    + linear_weight * linear_cal_probs[:n_cal]
                )
                # Approximate with LSTM weight redistributed
                ensemble_cal_probs = ensemble_cal_probs / (1 - config.lstm_weight)

                cal_probs_full = np.column_stack(
                    [1 - ensemble_cal_probs, ensemble_cal_probs]
                )
                y_cal_use = linear_y_cal.iloc[:n_cal].astype(int)
                y_cal_clipped = np.clip(y_cal_use, 0, 1)
                scores = 1 - cal_probs_full[np.arange(n_cal), y_cal_clipped]
                conformal_threshold = float(
                    np.quantile(scores, 1 - config.conformal_alpha)
                )
                prediction_set = (1 - y_prob) <= conformal_threshold
            except Exception:
                pass

    else:
        # Multiclass
        cb_probs = cb_model.predict_proba(X_pred_cb)[0]
        lgb_probs = lgb_model.predict_proba(X_pred_lgb)[0]
        linear_probs = linear_model.predict_proba(X_pred_linear)[0]

        # LSTM probs for multiclass (using extended sequence for continuity)
        with torch.no_grad():
            # Use lstm_X_full_for_seq (train+val+cal features) for sequence building
            if len(lstm_X_full_for_seq) >= lstm_seq_len - 1:
                X_pred_seq = np.vstack(
                    [
                        lstm_X_full_for_seq.values[-(lstm_seq_len - 1) :],
                        X_pred_lstm.values,
                    ]
                )
            else:
                n_hist = len(lstm_X_full_for_seq)
                n_pad = lstm_seq_len - 1 - n_hist
                X_pred_seq = np.vstack(
                    [
                        np.zeros((n_pad, X_pred_lstm.shape[1])),
                        lstm_X_full_for_seq.values,
                        X_pred_lstm.values,
                    ]
                )
            X_pred_scaled = lstm_scaler.transform(X_pred_seq)
            X_pred_tensor = torch.tensor(
                X_pred_scaled.reshape(1, lstm_seq_len, -1), dtype=torch.float32
            ).to(next(lstm_model.parameters()).device)
            lstm_logits = lstm_model(X_pred_tensor)
            lstm_probs = torch.softmax(lstm_logits, dim=1).cpu().numpy()[0]
            # Ensure same shape
            if len(lstm_probs) < len(cb_probs):
                lstm_probs = np.pad(lstm_probs, (0, len(cb_probs) - len(lstm_probs)))
            elif len(lstm_probs) > len(cb_probs):
                lstm_probs = lstm_probs[: len(cb_probs)]

        # Weighted ensemble
        linear_weight = max(
            0.0, 1.0 - config.cb_weight - config.lgb_weight - config.lstm_weight
        )
        ensemble_probs = (
            config.cb_weight * cb_probs
            + config.lgb_weight * lgb_probs
            + config.lstm_weight * lstm_probs
            + linear_weight * linear_probs
        )
        y_pred = int(np.argmax(ensemble_probs))
        y_prob = ensemble_probs

        cb_pred_val = int(np.argmax(cb_probs))
        lgb_pred_val = int(np.argmax(lgb_probs))
        lstm_pred_val = int(np.argmax(lstm_probs))
        linear_pred_val = int(np.argmax(linear_probs))

        prediction_set = None
        conformal_threshold = None

    # Model agreement
    model_agreement = int(
        cb_pred_val == lgb_pred_val == lstm_pred_val == linear_pred_val
    )
    ensemble_confidence = (
        float(np.max(y_prob)) if len(y_prob) > 2 else abs(y_prob[1] - 0.5) * 2
    )

    components = {
        "models_trained": True,
        "per_model_training": True,  # Flag indicating per-model mode
        # Individual model predictions
        "cb_pred": cb_pred_val,
        "lgb_pred": lgb_pred_val,
        "lstm_pred": lstm_pred_val,
        "linear_pred": linear_pred_val,
        # Ensemble metrics
        "y_prob": float(y_prob[1]) if is_binary else None,
        "ensemble_confidence": ensemble_confidence,
        "model_agreement": model_agreement,
        "conformal_threshold": conformal_threshold,
        # Per-model weights used
        "cb_weight_used": config.cb_weight,
        "lgb_weight_used": config.lgb_weight,
        "lstm_weight_used": config.lstm_weight,
        "linear_weight_used": linear_weight,
        # Per-model window sizes
        "cb_n_train": len(cb_X_train),
        "lgb_n_train": len(lgb_X_train),
        "lstm_n_train": len(lstm_X_train),
        "linear_n_train": len(linear_X_train),
        # Per-model feature counts
        "cb_n_features": len(cb_features),
        "lgb_n_features": len(lgb_features),
        "lstm_n_features": len(lstm_features),
        "linear_n_features": len(linear_features),
        # Training times
        "cb_train_time": train_times.get("cb", 0),
        "lgb_train_time": train_times.get("lgb", 0),
        "lstm_train_time": train_times.get("lstm", 0),
        "linear_train_time": train_times.get("linear", 0),
        # Tuned hyperparameters
        "cb_iterations": cb_params.get("iterations"),
        "cb_depth": cb_params.get("depth"),
        "lgb_n_estimators": lgb_params.get("n_estimators"),
        "lgb_max_depth": lgb_params.get("max_depth"),
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
) -> tuple[
    float, tuple[float, float] | None, bool, dict[str, Any], dict[str, dict[str, Any]]
]:
    """Train 4-model ensemble regressor with TRUE per-model windows and features.

    Each model (CatBoost, LightGBM, LSTM, Linear) gets:
    - Its own training window (extracted from X_full based on model config)
    - Its own train/val/cal splits (based on model-specific ratios)
    - Its own feature selection (based on model-specific method)

    All models predict the same X_pred point (alignment guaranteed).

    Args:
        X_full: Full feature window (max window size)
        y_full: Full target window
        X_pred: Single row to predict
        y_true: Actual target value (for coverage calculation)
        config: Backtest configuration
        horizon: Target horizon (for dynamic embargo)
        previous_best: Previous best hyperparameters for warm-starting

    Returns:
        y_pred: Predicted value
        interval: Conformal interval (lower, upper)
        covered: Whether y_true is in interval
        components: Individual model predictions + metadata
        tuned_params: Best hyperparameters (for warm-starting next step)
    """
    import time as time_module

    full_window_size = len(X_full)
    feature_cols = X_full.columns.tolist()

    # Get per-model configs
    cb_cfg = config.get_model_config("cb")
    lgb_cfg = config.get_model_config("lgb")
    lstm_cfg = config.get_model_config("lstm")
    linear_cfg = config.get_model_config("linear")

    # Override embargo_bars based on target horizon (dynamic embargo)
    # Formula: embargo = 3 * horizon, capped at 36
    dynamic_embargo = get_embargo_for_horizon(horizon)
    cb_cfg.embargo_bars = dynamic_embargo
    lgb_cfg.embargo_bars = dynamic_embargo
    lstm_cfg.embargo_bars = dynamic_embargo
    linear_cfg.embargo_bars = dynamic_embargo

    # Default params
    default_params = {
        "catboost": {
            "iterations": config.n_estimators,
            "depth": config.max_depth,
            "learning_rate": config.cb_learning_rate,
            "l2_leaf_reg": config.cb_l2_leaf_reg,
        },
        "lightgbm": {
            "n_estimators": config.n_estimators,
            "max_depth": config.max_depth,
            "learning_rate": config.lgb_learning_rate,
            "reg_lambda": config.lgb_reg_lambda,
        },
    }

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
    # APPLY PER-MODEL FEATURE SELECTION
    # =========================================================================
    cb_features = feature_cols
    lgb_features = feature_cols
    lstm_features = feature_cols
    linear_features = feature_cols

    # CatBoost feature selection
    if cb_cfg.feature_selection == "importance":
        quick_cb = CatBoostRegressor(
            iterations=50,
            depth=4,
            learning_rate=0.1,
            task_type="GPU",
            devices="0",
            verbose=False,
            random_seed=config.random_state,
        )
        quick_cb.fit(cb_X_train, cb_y_train)
        cb_features = apply_feature_selection(
            cb_X_train,
            "importance",
            model=quick_cb,
            ratio=cb_cfg.feature_selection_ratio,
            min_features=20,
        )[1]
    elif cb_cfg.feature_selection == "variance":
        _, cb_features = apply_feature_selection(
            cb_X_train,
            "variance",
            ratio=cb_cfg.feature_selection_ratio,
            min_features=20,
        )

    # LightGBM feature selection
    if lgb_cfg.feature_selection == "importance":
        quick_lgb = LGBMRegressor(
            n_estimators=50,
            max_depth=4,
            learning_rate=0.1,
            device="gpu",
            verbose=-1,
            random_state=config.random_state,
        )
        quick_lgb.fit(lgb_X_train, lgb_y_train)
        lgb_features = apply_feature_selection(
            lgb_X_train,
            "importance",
            model=quick_lgb,
            ratio=lgb_cfg.feature_selection_ratio,
            min_features=20,
        )[1]
    elif lgb_cfg.feature_selection == "variance":
        _, lgb_features = apply_feature_selection(
            lgb_X_train,
            "variance",
            ratio=lgb_cfg.feature_selection_ratio,
            min_features=20,
        )

    # LSTM/Linear feature selection (variance)
    if lstm_cfg.feature_selection == "variance":
        _, lstm_features = apply_feature_selection(
            lstm_X_train,
            "variance",
            ratio=lstm_cfg.feature_selection_ratio,
            min_features=20,
        )
    if linear_cfg.feature_selection == "variance":
        _, linear_features = apply_feature_selection(
            linear_X_train,
            "variance",
            ratio=linear_cfg.feature_selection_ratio,
            min_features=20,
        )

    # Apply feature selection
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
    lstm_X_cal_sel = lstm_X_cal[lstm_features]  # LSTM-ONLY FIX: needed for sequence
    X_pred_lstm = X_pred[lstm_features]

    linear_X_train_sel = linear_X_train[linear_features]
    linear_X_val_sel = linear_X_val[linear_features]
    linear_X_cal_sel = linear_X_cal[linear_features]
    X_pred_linear = X_pred[linear_features]

    # =========================================================================
    # TUNE HYPERPARAMETERS
    # =========================================================================
    tuned_params = previous_best or default_params.copy()

    if config.enable_optuna:
        cb_params = tune_cb_regressor(
            cb_X_train_sel,
            cb_y_train,
            cb_X_val_sel,
            cb_y_val,
            config,
            previous_best.get("catboost") if previous_best else None,
        )
        tuned_params["catboost"] = cb_params

        lgb_params = tune_lgb_regressor(
            lgb_X_train_sel,
            lgb_y_train,
            lgb_X_val_sel,
            lgb_y_val,
            config,
            previous_best.get("lightgbm") if previous_best else None,
        )
        tuned_params["lightgbm"] = lgb_params
    else:
        cb_params = tuned_params.get("catboost", default_params["catboost"])
        lgb_params = tuned_params.get("lightgbm", default_params["lightgbm"])

    # =========================================================================
    # TRAIN MODELS
    # =========================================================================
    train_times = {}

    cb_X_full = pd.concat([cb_X_train_sel, cb_X_val_sel], ignore_index=True)
    cb_y_full = pd.concat([cb_y_train, cb_y_val], ignore_index=True)

    lgb_X_full = pd.concat([lgb_X_train_sel, lgb_X_val_sel], ignore_index=True)
    lgb_y_full = pd.concat([lgb_y_train, lgb_y_val], ignore_index=True)

    lstm_X_full = pd.concat([lstm_X_train_sel, lstm_X_val_sel], ignore_index=True)
    lstm_y_full = pd.concat([lstm_y_train, lstm_y_val], ignore_index=True)
    # LSTM-ONLY FIX: Extended sequence for prediction includes cal FEATURES
    # This reduces the gap from ~93 bars to ~3 bars (embargo only)
    # Training still uses only train+val (lstm_X_full/lstm_y_full)
    # No target leakage: we only use X_cal features, never y_cal
    lstm_X_full_for_seq = pd.concat(
        [lstm_X_train_sel, lstm_X_val_sel, lstm_X_cal_sel], ignore_index=True
    )

    linear_X_full = pd.concat([linear_X_train_sel, linear_X_val_sel], ignore_index=True)
    linear_y_full = pd.concat([linear_y_train, linear_y_val], ignore_index=True)

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*GPU memory available.*")
        warnings.filterwarnings("ignore", category=UserWarning)

        # CatBoost
        t0 = time_module.time()
        cb_model = CatBoostRegressor(
            iterations=cb_params.get("iterations", config.n_estimators),
            depth=cb_params.get("depth", config.max_depth),
            learning_rate=cb_params.get("learning_rate", config.cb_learning_rate),
            l2_leaf_reg=cb_params.get("l2_leaf_reg", config.cb_l2_leaf_reg),
            task_type="GPU",
            devices="0",
            verbose=False,
            random_seed=config.random_state,
        )
        cb_model.fit(cb_X_full, cb_y_full)
        train_times["cb"] = time_module.time() - t0

        # LightGBM
        t0 = time_module.time()
        lgb_model = LGBMRegressor(
            n_estimators=lgb_params.get("n_estimators", config.n_estimators),
            max_depth=lgb_params.get("max_depth", config.max_depth),
            learning_rate=lgb_params.get("learning_rate", config.lgb_learning_rate),
            reg_lambda=lgb_params.get("reg_lambda", config.lgb_reg_lambda),
            min_child_samples=config.lgb_min_child_samples,
            device="gpu",
            verbose=-1,
            random_seed=config.random_state,
        )
        lgb_model.fit(lgb_X_full, lgb_y_full)
        train_times["lgb"] = time_module.time() - t0

        # Linear (Ridge)
        t0 = time_module.time()
        linear_model = Ridge(alpha=1.0, random_state=config.random_state)
        linear_model.fit(linear_X_full, linear_y_full)
        train_times["linear"] = time_module.time() - t0

        # LSTM
        t0 = time_module.time()
        lstm_model, lstm_scaler, lstm_seq_len = train_lstm_regressor(
            lstm_X_full.values,
            lstm_y_full.values,
            hidden_size=config.lstm_hidden_size,
            num_layers=config.lstm_num_layers,
            lr=config.lstm_lr,
            epochs=config.lstm_epochs,
            batch_size=config.lstm_batch_size,
            device="cuda" if torch.cuda.is_available() else "cpu",
            seq_len=config.lstm_seq_len,
        )
        train_times["lstm"] = time_module.time() - t0

    # =========================================================================
    # GET PREDICTIONS
    # =========================================================================
    cb_pred = float(cb_model.predict(X_pred_cb)[0])
    lgb_pred = float(lgb_model.predict(X_pred_lgb)[0])
    linear_pred = float(linear_model.predict(X_pred_linear)[0])

    # LSTM prediction (using extended sequence for continuity)
    with torch.no_grad():
        # Use lstm_X_full_for_seq (train+val+cal features) for sequence building
        # This reduces gap from ~93 bars to ~3 bars (embargo only)
        if len(lstm_X_full_for_seq) >= lstm_seq_len - 1:
            X_pred_seq = np.vstack(
                [lstm_X_full_for_seq.values[-(lstm_seq_len - 1) :], X_pred_lstm.values]
            )
        else:
            n_hist = len(lstm_X_full_for_seq)
            n_pad = lstm_seq_len - 1 - n_hist
            X_pred_seq = np.vstack(
                [
                    np.zeros((n_pad, X_pred_lstm.shape[1])),
                    lstm_X_full_for_seq.values,
                    X_pred_lstm.values,
                ]
            )
        X_pred_scaled = lstm_scaler.transform(X_pred_seq)
        X_pred_tensor = torch.tensor(
            X_pred_scaled.reshape(1, lstm_seq_len, -1), dtype=torch.float32
        ).to(next(lstm_model.parameters()).device)
        lstm_pred = float(lstm_model(X_pred_tensor).cpu().numpy()[0, 0])

    # Clip predictions using training statistics (no leakage)
    y_train_mean = float(linear_y_full.mean())
    y_train_std = float(linear_y_full.std())
    clip_lower = y_train_mean - 5.0 * y_train_std
    clip_upper = y_train_mean + 5.0 * y_train_std

    cb_pred = float(np.clip(cb_pred, clip_lower, clip_upper))
    lgb_pred = float(np.clip(lgb_pred, clip_lower, clip_upper))
    lstm_pred = float(np.clip(lstm_pred, clip_lower, clip_upper))
    linear_pred = float(np.clip(linear_pred, clip_lower, clip_upper))

    # Weighted ensemble
    linear_weight = max(
        0.0, 1.0 - config.cb_weight - config.lgb_weight - config.lstm_weight
    )
    y_pred = (
        config.cb_weight * cb_pred
        + config.lgb_weight * lgb_pred
        + config.lstm_weight * lstm_pred
        + linear_weight * linear_pred
    )
    y_pred = float(np.clip(y_pred, clip_lower, clip_upper))

    # Conformal interval using Linear's calibration set
    interval = None
    covered = False
    if len(linear_X_cal_sel) > 10:
        try:
            cb_cal_preds = cb_model.predict(cb_X_cal_sel)
            lgb_cal_preds = lgb_model.predict(lgb_X_cal_sel)
            linear_cal_preds = linear_model.predict(linear_X_cal_sel)

            n_cal = min(len(cb_cal_preds), len(lgb_cal_preds), len(linear_cal_preds))
            ensemble_cal_preds = (
                config.cb_weight * cb_cal_preds[:n_cal]
                + config.lgb_weight * lgb_cal_preds[:n_cal]
                + linear_weight * linear_cal_preds[:n_cal]
            ) / (1 - config.lstm_weight)

            y_cal_use = linear_y_cal.iloc[:n_cal].values
            residuals = np.abs(y_cal_use - ensemble_cal_preds)
            q = np.quantile(residuals, 1 - config.conformal_alpha)
            interval = (y_pred - q, y_pred + q)
            covered = interval[0] <= y_true <= interval[1]
        except Exception:
            pass

    components = {
        "models_trained": True,
        "per_model_training": True,
        "cb_pred": cb_pred,
        "lgb_pred": lgb_pred,
        "lstm_pred": lstm_pred,
        "linear_pred": linear_pred,
        # Per-model weights used
        "cb_weight_used": config.cb_weight,
        "lgb_weight_used": config.lgb_weight,
        "lstm_weight_used": config.lstm_weight,
        "linear_weight_used": linear_weight,
        # Per-model training sizes
        "cb_n_train": len(cb_X_train),
        "lgb_n_train": len(lgb_X_train),
        "lstm_n_train": len(lstm_X_train),
        "linear_n_train": len(linear_X_train),
        "cb_n_features": len(cb_features),
        "lgb_n_features": len(lgb_features),
        "lstm_n_features": len(lstm_features),
        "linear_n_features": len(linear_features),
        "cb_train_time": train_times.get("cb", 0),
        "lgb_train_time": train_times.get("lgb", 0),
        "lstm_train_time": train_times.get("lstm", 0),
        "linear_train_time": train_times.get("linear", 0),
    }

    return y_pred, interval, covered, components, tuned_params

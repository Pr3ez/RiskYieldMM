"""
Hyperparameter tuning services using Optuna.

Contains tuning functions for CatBoost and LightGBM models,
both classification and regression variants.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np
import optuna
import pandas as pd
from catboost import CatBoostClassifier, CatBoostRegressor
from lightgbm import LGBMClassifier, LGBMRegressor
from sklearn.metrics import accuracy_score

if TYPE_CHECKING:
    from backtest.domain.config import SyncBacktestConfig


__all__ = [
    "tune_cb_classifier",
    "tune_lgb_classifier",
    "tune_cb_regressor",
    "tune_lgb_regressor",
]


def tune_cb_classifier(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: pd.DataFrame,
    y_val: pd.Series,
    config: SyncBacktestConfig,
    is_binary: bool,
    previous_best: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Tune CatBoost classifier hyperparameters using Optuna.

    Args:
        X_train: Training features
        y_train: Training labels
        X_val: Validation features
        y_val: Validation labels
        config: Backtest configuration
        is_binary: Whether this is binary classification
        previous_best: Previous best params to use as starting point

    Returns:
        Best hyperparameters found by Optuna
    """

    def objective(trial):
        params = {
            "iterations": trial.suggest_int("iterations", 50, 300),
            "depth": trial.suggest_int("depth", 3, 8),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "l2_leaf_reg": trial.suggest_float("l2_leaf_reg", 1.0, 10.0),
        }
        model = CatBoostClassifier(
            **params,
            loss_function="Logloss" if is_binary else "MultiClass",
            task_type="GPU",
            devices="0",
            verbose=False,
            random_seed=config.random_state,
        )
        model.fit(X_train, y_train)
        y_pred = model.predict(X_val)
        return accuracy_score(y_val, y_pred)

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study = optuna.create_study(direction="maximize")

    if previous_best:
        study.enqueue_trial(previous_best)

    study.optimize(
        objective, n_trials=config.n_optuna_trials, timeout=config.optuna_timeout
    )
    return study.best_params


def tune_lgb_classifier(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: pd.DataFrame,
    y_val: pd.Series,
    config: SyncBacktestConfig,
    is_binary: bool,
    previous_best: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Tune LightGBM classifier hyperparameters using Optuna.

    Args:
        X_train: Training features
        y_train: Training labels
        X_val: Validation features
        y_val: Validation labels
        config: Backtest configuration
        is_binary: Whether this is binary classification
        previous_best: Previous best params to use as starting point

    Returns:
        Best hyperparameters found by Optuna
    """

    def objective(trial):
        params = {
            "n_estimators": trial.suggest_int("n_estimators", 50, 300),
            "max_depth": trial.suggest_int("max_depth", 3, 8),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 0.1, 10.0),
        }
        if is_binary:
            model = LGBMClassifier(
                **params,
                min_child_samples=config.lgb_min_child_samples,
                objective="binary",
                device="gpu",
                verbose=-1,
                random_state=config.random_state,
            )
        else:
            n_classes = len(np.unique(y_train))
            model = LGBMClassifier(
                **params,
                min_child_samples=config.lgb_min_child_samples,
                objective="multiclass",
                num_class=n_classes,
                device="gpu",
                verbose=-1,
                random_state=config.random_state,
            )
        model.fit(X_train, y_train)
        y_pred = model.predict(X_val)
        return accuracy_score(y_val, y_pred)

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study = optuna.create_study(direction="maximize")

    if previous_best:
        study.enqueue_trial(previous_best)

    study.optimize(
        objective, n_trials=config.n_optuna_trials, timeout=config.optuna_timeout
    )
    return study.best_params


def tune_cb_regressor(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: pd.DataFrame,
    y_val: pd.Series,
    config: SyncBacktestConfig,
    previous_best: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Tune CatBoost regressor hyperparameters using Optuna.

    Args:
        X_train: Training features
        y_train: Training targets
        X_val: Validation features
        y_val: Validation targets
        config: Backtest configuration
        previous_best: Previous best params to use as starting point

    Returns:
        Best hyperparameters found by Optuna
    """

    def objective(trial):
        params = {
            "iterations": trial.suggest_int("iterations", 50, 300),
            "depth": trial.suggest_int("depth", 3, 8),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "l2_leaf_reg": trial.suggest_float("l2_leaf_reg", 1.0, 10.0),
        }
        model = CatBoostRegressor(
            **params,
            task_type="GPU",
            devices="0",
            verbose=False,
            random_seed=config.random_state,
        )
        model.fit(X_train, y_train)
        y_pred = model.predict(X_val)
        # Use negative MSE (Optuna maximizes)
        return -float(np.mean((y_val - y_pred) ** 2))

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study = optuna.create_study(direction="maximize")
    if previous_best:
        study.enqueue_trial(previous_best)
    study.optimize(
        objective, n_trials=config.n_optuna_trials, timeout=config.optuna_timeout
    )
    return study.best_params


def tune_lgb_regressor(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: pd.DataFrame,
    y_val: pd.Series,
    config: SyncBacktestConfig,
    previous_best: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Tune LightGBM regressor hyperparameters using Optuna.

    Args:
        X_train: Training features
        y_train: Training targets
        X_val: Validation features
        y_val: Validation targets
        config: Backtest configuration
        previous_best: Previous best params to use as starting point

    Returns:
        Best hyperparameters found by Optuna
    """

    def objective(trial):
        params = {
            "n_estimators": trial.suggest_int("n_estimators", 50, 300),
            "max_depth": trial.suggest_int("max_depth", 3, 8),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 0.1, 10.0),
        }
        model = LGBMRegressor(
            **params,
            min_child_samples=config.lgb_min_child_samples,
            device="gpu",
            verbose=-1,
            random_seed=config.random_state,
        )
        model.fit(X_train, y_train)
        y_pred = model.predict(X_val)
        return -float(np.mean((y_val - y_pred) ** 2))

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study = optuna.create_study(direction="maximize")
    if previous_best:
        study.enqueue_trial(previous_best)
    study.optimize(
        objective, n_trials=config.n_optuna_trials, timeout=config.optuna_timeout
    )
    return study.best_params

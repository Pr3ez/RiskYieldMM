"""
ARCHIVED FUNCTIONS FROM l2_backtest_sync.py
============================================

Date: 2026-01-19
Updated: 2026-01-20

NOTE: These implementations served as REFERENCE for the modularized versions in backtest/

ACTIVE VERSIONS (in backtest/ package):
---------------------------------------
1. compute_sample_weights() → backtest/core/ensemble.py (ACTIVE - used in training)
2. update_adaptive_weights() → backtest/core/ensemble.py (ACTIVE - MWU in backtest loop)
3. AdaptiveWeightTracker → backtest/core/ensemble.py (ACTIVE - tracks per-model accuracy)

ARCHIVED (not used - for reference only):
-----------------------------------------
4. _tune_classification_params() - Legacy Optuna tuning (replaced by per-model tuners)
5. _tune_regression_params() - Legacy Optuna tuning (replaced by per-model tuners)
6. PerModelConfig.validate() - Config validation method (never wired up)

The implementations below are COPIES/ORIGINALS - do not modify.
Active code lives in backtest/ package.

DEPENDENCIES:
-------------
- numpy as np
- optuna
- CatBoostClassifier, CatBoostRegressor
- LGBMClassifier, LGBMRegressor
- sklearn.metrics (roc_auc_score, accuracy_score)
- warnings
"""

from __future__ import annotations

import warnings
from typing import Any

import numpy as np
import optuna
import pandas as pd
from catboost import CatBoostClassifier, CatBoostRegressor
from lightgbm import LGBMClassifier, LGBMRegressor
from sklearn.metrics import accuracy_score, roc_auc_score

# ============================================================================
# SAMPLE WEIGHTING (CONCEPT DRIFT MITIGATION)
# ============================================================================
# STATUS: Active version in backtest/core/ensemble.py
# USAGE: compute_sample_weights() is called by train_predict_* functions
# RELATED CONFIG: use_sample_weights, sample_decay_halflife
# ============================================================================


def _compute_sample_weights(
    n_samples: int,
    halflife_fraction: float = 0.3,
) -> np.ndarray:
    """Compute exponential decay sample weights.

    Based on research from:
    - de Prado (2018) "Advances in Financial Machine Learning"
    - arXiv 2103.14079 "Domain Specific Concept Drift Detectors"

    Recent samples get higher weights, older samples decay exponentially.

    Args:
        n_samples: Number of training samples
        halflife_fraction: Fraction of window where weight decays to 50%
                          e.g., 0.3 means at 70% through the window, weight = 50%

    Returns:
        Array of sample weights, normalized to sum to n_samples
    """
    if n_samples <= 0:
        return np.array([])

    # Halflife in samples (from the end)
    halflife = int(n_samples * halflife_fraction)
    halflife = max(halflife, 1)  # At least 1

    # Create time indices (0 = oldest, n_samples-1 = newest)
    t = np.arange(n_samples)

    # Exponential decay: w(t) = 2^((t - n_samples) / halflife)
    # At t = n_samples - halflife: w = 0.5
    # At t = n_samples - 1: w = ~1.0
    weights = np.power(2.0, (t - n_samples + 1) / halflife)

    # Normalize so weights sum to n_samples (equivalent to uniform mean)
    weights = weights * (n_samples / weights.sum())

    return weights


# ============================================================================
# ADAPTIVE ENSEMBLE WEIGHTS (arXiv 2304.09947 - Multiplicative Weights Update)
# ============================================================================
# STATUS: NEVER CALLED
# WHERE IT SHOULD BE USED: After each fold, update weights based on recent model accuracy
# RELATED CONFIG: use_adaptive_weights, adaptive_lookback, adaptive_learning_rate, adaptive_min_weight
# CURRENT PROBLEM: Code uses static config.cb_weight, config.lgb_weight, etc. everywhere
# ============================================================================


def _update_adaptive_weights(
    current_weights: dict[str, float],
    recent_accuracies: dict[str, list[float]],
    learning_rate: float = 0.1,
    min_weight: float = 0.05,
) -> dict[str, float]:
    """Update ensemble weights using Multiplicative Weights Update algorithm.

    Based on arXiv 2304.09947 "Online Ensemble Learning for Sector Rotation"
    and standard MWU theory (Freund & Schapire).

    Models with better recent performance get higher weights.

    Args:
        current_weights: Current model weights (cb, lgb, lstm, linear)
        recent_accuracies: Dict of model_name -> list of recent correct predictions (0/1)
        learning_rate: How fast to adjust (eta in MWU)
        min_weight: Minimum weight to prevent zeroing out

    Returns:
        Updated weights dictionary
    """
    models = ["cb", "lgb", "lstm", "linear"]

    # Compute recent accuracy for each model
    model_scores = {}
    for model in models:
        accs = recent_accuracies.get(model, [])
        if len(accs) > 0:
            # Recent accuracy (0 to 1)
            model_scores[model] = np.mean(accs)
        else:
            # No data yet, use neutral score
            model_scores[model] = 0.5

    # MWU update: w_new = w_old * exp(eta * reward)
    # Reward = accuracy - 0.5 (centered so random = 0)
    new_weights = {}
    for model in models:
        reward = model_scores[model] - 0.5  # -0.5 to +0.5
        old_w = current_weights.get(f"{model}_weight", 0.25)
        new_w = old_w * np.exp(learning_rate * reward)
        new_weights[f"{model}_weight"] = new_w

    # Normalize to sum to 1.0
    total = sum(new_weights.values())
    for model in models:
        key = f"{model}_weight"
        new_weights[key] = new_weights[key] / total
        # Apply minimum weight constraint
        new_weights[key] = max(new_weights[key], min_weight)

    # Re-normalize after applying minimums
    total = sum(new_weights.values())
    for model in models:
        key = f"{model}_weight"
        new_weights[key] = new_weights[key] / total

    return new_weights


# ============================================================================
# LEGACY OPTUNA HYPERPARAMETER TUNING
# ============================================================================
# STATUS: REPLACED by per-model tuners inside _train_predict_*_permodel functions
# THESE ARE LIKELY NOT NEEDED - the per-model approach tunes during training
# ============================================================================


def _tune_classification_params(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: pd.DataFrame,
    y_val: pd.Series,
    config: Any,  # SyncBacktestConfig
    n_classes: int,
    previous_best: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """
    Tune hyperparameters for classification models using Optuna.

    Uses train set for fitting, val set for evaluation.
    Warm-starts with previous_best params if provided.
    Returns best params for CatBoost and LightGBM.

    NOTE: This is the OLD shared tuner. Per-model training functions now
    have their own Optuna tuning built-in.
    """
    unique_classes = np.unique(y_train)
    is_binary = n_classes == 2

    # Suppress Optuna logging
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    best_params = {
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

    if not config.enable_optuna or len(X_val) < 10:
        return best_params

    # CatBoost tuning
    def cb_objective(trial: optuna.Trial) -> float:
        params = {
            "iterations": trial.suggest_int("iterations", 50, 200),
            "depth": trial.suggest_int("depth", 3, 8),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.1, log=True),
            "l2_leaf_reg": trial.suggest_float("l2_leaf_reg", 1.0, 10.0),
        }

        with warnings.catch_warnings():
            warnings.filterwarnings("ignore")
            model = CatBoostClassifier(
                **params,
                loss_function="Logloss" if is_binary else "MultiClass",
                task_type="GPU",
                devices="0",
                verbose=False,
                random_seed=config.random_state,
            )
            model.fit(X_train, y_train)

            if is_binary:
                val_probs = model.predict_proba(X_val)[:, 1]
                if not np.all(np.isfinite(val_probs)):
                    return 0.5
                try:
                    auc = roc_auc_score(y_val, val_probs)
                    return auc if np.isfinite(auc) else 0.5
                except ValueError:
                    return 0.5
            else:
                val_preds = model.predict(X_val).flatten()
                return accuracy_score(y_val, val_preds)

    # LightGBM tuning
    def lgb_objective(trial: optuna.Trial) -> float:
        params = {
            "n_estimators": trial.suggest_int("n_estimators", 50, 200),
            "max_depth": trial.suggest_int("max_depth", 3, 8),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.1, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 0.1, 10.0, log=True),
        }

        with warnings.catch_warnings():
            warnings.filterwarnings("ignore")
            if is_binary:
                model = LGBMClassifier(
                    **params,
                    objective="binary",
                    metric="auc",
                    device="gpu",
                    verbose=-1,
                    random_state=config.random_state,
                )
            else:
                n_actual_classes = len(unique_classes)
                model = LGBMClassifier(
                    **params,
                    objective="multiclass",
                    metric="multi_logloss",
                    num_class=n_actual_classes,
                    device="gpu",
                    verbose=-1,
                    random_state=config.random_state,
                )

            model.fit(X_train, y_train)

            if is_binary:
                val_probs = model.predict_proba(X_val)[:, 1]
                if not np.all(np.isfinite(val_probs)):
                    return 0.5
                try:
                    auc = roc_auc_score(y_val, val_probs)
                    return auc if np.isfinite(auc) else 0.5
                except ValueError:
                    return 0.5
            else:
                val_preds = model.predict(X_val)
                return accuracy_score(y_val, val_preds)

    # Run Optuna studies with warm-starting
    try:
        cb_study = optuna.create_study(direction="maximize")
        # Warm-start: enqueue previous best params as first trial
        if previous_best and "catboost" in previous_best:
            cb_study.enqueue_trial(previous_best["catboost"])
        cb_study.optimize(
            cb_objective,
            n_trials=config.n_optuna_trials,
            timeout=config.optuna_timeout,
            show_progress_bar=False,
        )
        best_params["catboost"] = cb_study.best_params
    except Exception:
        pass  # Keep defaults

    try:
        lgb_study = optuna.create_study(direction="maximize")
        # Warm-start: enqueue previous best params as first trial
        if previous_best and "lightgbm" in previous_best:
            lgb_study.enqueue_trial(previous_best["lightgbm"])
        lgb_study.optimize(
            lgb_objective,
            n_trials=config.n_optuna_trials,
            timeout=config.optuna_timeout,
            show_progress_bar=False,
        )
        best_params["lightgbm"] = lgb_study.best_params
    except Exception:
        pass  # Keep defaults

    return best_params


def _tune_regression_params(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: pd.DataFrame,
    y_val: pd.Series,
    config: Any,  # SyncBacktestConfig
    previous_best: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """
    Tune hyperparameters for regression models using Optuna.

    Uses train set for fitting, val set for evaluation.
    Warm-starts with previous_best params if provided.
    Returns best params for CatBoost and LightGBM.

    NOTE: This is the OLD shared tuner. Per-model training functions now
    have their own Optuna tuning built-in.
    """
    # Suppress Optuna logging
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    best_params = {
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

    if not config.enable_optuna or len(X_val) < 10:
        return best_params

    # CatBoost tuning - minimize RMSE (negative for maximization)
    def cb_objective(trial: optuna.Trial) -> float:
        params = {
            "iterations": trial.suggest_int("iterations", 50, 200),
            "depth": trial.suggest_int("depth", 3, 8),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.1, log=True),
            "l2_leaf_reg": trial.suggest_float("l2_leaf_reg", 1.0, 10.0),
        }

        with warnings.catch_warnings():
            warnings.filterwarnings("ignore")
            model = CatBoostRegressor(
                **params,
                loss_function="RMSE",
                task_type="GPU",
                devices="0",
                verbose=False,
                random_seed=config.random_state,
            )
            model.fit(X_train, y_train)
            val_preds = model.predict(X_val)
            # Check for NaN/Inf in predictions
            if not np.all(np.isfinite(val_preds)):
                return 0.0
            # Correlation as metric (higher is better)
            if np.std(val_preds) > 1e-10 and np.std(y_val) > 1e-10:
                corr = np.corrcoef(val_preds, y_val)[0, 1]
                return corr if np.isfinite(corr) else 0.0
            return 0.0

    # LightGBM tuning
    def lgb_objective(trial: optuna.Trial) -> float:
        params = {
            "n_estimators": trial.suggest_int("n_estimators", 50, 200),
            "max_depth": trial.suggest_int("max_depth", 3, 8),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.1, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 0.1, 10.0, log=True),
        }

        with warnings.catch_warnings():
            warnings.filterwarnings("ignore")
            model = LGBMRegressor(
                **params,
                objective="regression",
                metric="rmse",
                device="gpu",
                verbose=-1,
                random_state=config.random_state,
            )
            model.fit(X_train, y_train)
            val_preds = model.predict(X_val)
            # Check for NaN/Inf in predictions
            if not np.all(np.isfinite(val_preds)):
                return 0.0
            # Correlation as metric (higher is better)
            if np.std(val_preds) > 1e-10 and np.std(y_val) > 1e-10:
                corr = np.corrcoef(val_preds, y_val)[0, 1]
                return corr if np.isfinite(corr) else 0.0
            return 0.0

    # Run Optuna studies with warm-starting
    try:
        cb_study = optuna.create_study(direction="maximize")
        # Warm-start: enqueue previous best params as first trial
        if previous_best and "catboost" in previous_best:
            cb_study.enqueue_trial(previous_best["catboost"])
        cb_study.optimize(
            cb_objective,
            n_trials=config.n_optuna_trials,
            timeout=config.optuna_timeout,
            show_progress_bar=False,
        )
        best_params["catboost"] = cb_study.best_params
    except Exception:
        pass  # Keep defaults

    try:
        lgb_study = optuna.create_study(direction="maximize")
        # Warm-start: enqueue previous best params as first trial
        if previous_best and "lightgbm" in previous_best:
            lgb_study.enqueue_trial(previous_best["lightgbm"])
        lgb_study.optimize(
            lgb_objective,
            n_trials=config.n_optuna_trials,
            timeout=config.optuna_timeout,
            show_progress_bar=False,
        )
        best_params["lightgbm"] = lgb_study.best_params
    except Exception:
        pass  # Keep defaults

    return best_params


# ============================================================================
# PerModelConfig.validate() METHOD
# ============================================================================
# STATUS: Defined in dataclass but NEVER called
# WHERE IT SHOULD BE USED: In PerModelConfig.__post_init__ or at SyncBacktestConfig init
# ============================================================================

# NOTE: This is a METHOD that belongs to the PerModelConfig dataclass.
# It cannot be moved here directly - it needs to stay in the class.
#
# The issue is that the method EXISTS but is NEVER CALLED.
#
# Current PerModelConfig definition has validate() but:
# - No __post_init__ that calls validate()
# - SyncBacktestConfig doesn't call it when receiving configs
#
# SOLUTION: Add to PerModelConfig:
#     def __post_init__(self):
#         self.validate()
#
# The validate() method code (for reference):
"""
def validate(self) -> None:
    '''Validate configuration values.'''
    if self.train_window < 100:
        raise ValueError(f"train_window must be >= 100, got {self.train_window}")
    if not (0.3 <= self.train_ratio <= 0.8):
        raise ValueError(f"train_ratio must be 0.3-0.8, got {self.train_ratio}")
    if self.feature_selection not in ("none", "icir", "importance", "variance"):
        raise ValueError(f"Invalid feature_selection: {self.feature_selection}")
    if not (0.1 <= self.feature_selection_ratio <= 1.0):
        raise ValueError("feature_selection_ratio must be 0.1-1.0")
"""

"""
Model Training and Evaluation Module
====================================

Model operations:
- Direction model training (CatBoost + LightGBM)
- Volatility model training (CatBoostRegressor)
- Returns regression (Ridge)
- Cross-validation utilities
- Calibration helpers
"""

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import Ridge
from sklearn.metrics import (
    accuracy_score,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    roc_auc_score,
)
from sklearn.model_selection import TimeSeriesSplit

from . import config, data

# =============================================================================
# MODEL AVAILABILITY CHECKS
# =============================================================================

try:
    from catboost import CatBoostClassifier, CatBoostRegressor

    HAS_CATBOOST = True
except ImportError:
    HAS_CATBOOST = False
    CatBoostClassifier = None
    CatBoostRegressor = None

try:
    from lightgbm import LGBMClassifier

    HAS_LIGHTGBM = True
except ImportError:
    HAS_LIGHTGBM = False
    LGBMClassifier = None


# =============================================================================
# RESULT DATACLASSES
# =============================================================================


@dataclass
class ModelResult:
    """Result from model training."""

    model_name: str
    model: Any
    probabilities: np.ndarray | None = None
    predictions: np.ndarray | None = None
    auc: float = np.nan
    accuracy: float = np.nan
    rmse: float = np.nan
    mae: float = np.nan
    r2: float = np.nan


@dataclass
class CVResult:
    """Result from cross-validation."""

    model_name: str
    fold_results: list[ModelResult] = field(default_factory=list)

    @property
    def mean_auc(self) -> float:
        aucs = [r.auc for r in self.fold_results if not np.isnan(r.auc)]
        return np.mean(aucs) if aucs else np.nan

    @property
    def std_auc(self) -> float:
        aucs = [r.auc for r in self.fold_results if not np.isnan(r.auc)]
        return np.std(aucs) if aucs else np.nan

    @property
    def mean_accuracy(self) -> float:
        accs = [r.accuracy for r in self.fold_results if not np.isnan(r.accuracy)]
        return np.mean(accs) if accs else np.nan


# =============================================================================
# PURGED K-FOLD CROSS-VALIDATION
# =============================================================================


class PurgedKFold:
    """
    Purged K-Fold cross-validation for time-series data.

    Implements Lopez de Prado's purged CV concept (AFML Chapter 7) with a
    simplified fixed-gap approach suitable for our fixed-horizon targets.

    The purge gap removes training samples that could have features computed
    using data from the test period. The embargo gap removes training samples
    whose target labels overlap with the test period.

    Academic Reference:
        Lopez de Prado, M. (2018). Advances in Financial Machine Learning.
        Chapter 7: Cross-Validation in Finance.

    Args:
        n_splits: Number of folds
        purge_gap: Number of samples to remove BEFORE test set
                   (should be >= max feature lookback window)
        embargo_gap: Number of samples to remove AFTER test set
                     (should be >= max target horizon)

    Example:
        >>> cv = PurgedKFold(n_splits=5, purge_gap=21, embargo_gap=12)
        >>> for train_idx, test_idx in cv.split(X):
        ...     X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
    """

    def __init__(
        self,
        n_splits: int = 5,
        purge_gap: int = 21,
        embargo_gap: int = 12,
    ):
        self.n_splits = n_splits
        self.purge_gap = purge_gap
        self.embargo_gap = embargo_gap

    def get_n_splits(self, X=None, y=None, groups=None) -> int:
        """Return the number of splitting iterations."""
        return self.n_splits

    def split(self, X, y=None, groups=None):
        """
        Generate indices to split data into training and test sets.

        The splits are made such that:
        1. Test sets are contiguous blocks moving forward in time
        2. Training sets exclude samples in the purge zone (before test)
        3. Training sets exclude samples in the embargo zone (after test)

        Yields:
            train_indices: ndarray of training set indices
            test_indices: ndarray of test set indices
        """
        n_samples = len(X)
        indices = np.arange(n_samples)

        # Calculate test fold size (equal-sized folds)
        fold_size = n_samples // self.n_splits

        for fold_idx in range(self.n_splits):
            # Define test boundaries
            test_start = fold_idx * fold_size
            test_end = (
                (fold_idx + 1) * fold_size
                if fold_idx < self.n_splits - 1
                else n_samples
            )

            test_indices = indices[test_start:test_end]

            # Define purge zone (before test set)
            purge_start = max(0, test_start - self.purge_gap)

            # Define embargo zone (after test set)
            embargo_end = min(n_samples, test_end + self.embargo_gap)

            # Training indices: everything except test + purge + embargo zones
            train_mask = np.ones(n_samples, dtype=bool)
            train_mask[purge_start:embargo_end] = (
                False  # Exclude purge + test + embargo
            )

            train_indices = indices[train_mask]

            yield train_indices, test_indices


# =============================================================================
# DIRECTION MODELS
# =============================================================================


def train_catboost_classifier(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: pd.DataFrame | None = None,
    y_val: pd.Series | None = None,
    sample_weights: np.ndarray | None = None,
    cfg: config.ModelConfig | None = None,
) -> ModelResult:
    """Train CatBoost classifier for direction prediction."""
    if not HAS_CATBOOST:
        return ModelResult(model_name="catboost", model=None)

    cfg = cfg or config.MODEL_CONFIG

    model = CatBoostClassifier(
        iterations=cfg.cb_iterations,
        depth=cfg.cb_depth,
        learning_rate=cfg.cb_learning_rate,
        l2_leaf_reg=cfg.cb_l2_reg,
        early_stopping_rounds=cfg.cb_early_stopping if X_val is not None else None,
        verbose=False,
        random_state=cfg.random_state,
    )

    eval_set = (X_val, y_val) if X_val is not None else None
    model.fit(X_train, y_train, eval_set=eval_set, sample_weight=sample_weights)

    result = ModelResult(model_name="catboost", model=model)

    if X_val is not None and y_val is not None:
        probs = model.predict_proba(X_val)[:, 1]
        result.probabilities = probs
        result.predictions = (probs > 0.5).astype(int)
        result.auc = roc_auc_score(y_val, probs)
        result.accuracy = accuracy_score(y_val, result.predictions)

    return result


def train_lightgbm_classifier(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: pd.DataFrame | None = None,
    y_val: pd.Series | None = None,
    sample_weights: np.ndarray | None = None,
    cfg: config.ModelConfig | None = None,
) -> ModelResult:
    """Train LightGBM classifier for direction prediction."""
    if not HAS_LIGHTGBM:
        return ModelResult(model_name="lightgbm", model=None)

    cfg = cfg or config.MODEL_CONFIG

    model = LGBMClassifier(
        n_estimators=cfg.lgb_n_estimators,
        max_depth=cfg.lgb_max_depth,
        learning_rate=cfg.lgb_learning_rate,
        reg_lambda=cfg.lgb_reg_lambda,
        verbose=-1,
        random_state=cfg.random_state,
    )

    eval_set = [(X_val, y_val)] if X_val is not None else None
    model.fit(X_train, y_train, eval_set=eval_set, sample_weight=sample_weights)

    result = ModelResult(model_name="lightgbm", model=model)

    if X_val is not None and y_val is not None:
        probs = model.predict_proba(X_val)[:, 1]
        result.probabilities = probs
        result.predictions = (probs > 0.5).astype(int)
        result.auc = roc_auc_score(y_val, probs)
        result.accuracy = accuracy_score(y_val, result.predictions)

    return result


def train_direction_ensemble(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: pd.DataFrame,
    y_val: pd.Series,
    sample_weights: np.ndarray | None = None,
) -> dict[str, ModelResult]:
    """
    Train full direction ensemble (CatBoost + LightGBM).

    Returns:
        Dict with 'catboost', 'lightgbm', 'ensemble' results
    """
    results = {}

    # Train individual models
    if HAS_CATBOOST:
        results["catboost"] = train_catboost_classifier(
            X_train, y_train, X_val, y_val, sample_weights
        )

    if HAS_LIGHTGBM:
        results["lightgbm"] = train_lightgbm_classifier(
            X_train, y_train, X_val, y_val, sample_weights
        )

    # Ensemble (simple average)
    if "catboost" in results and "lightgbm" in results:
        cb_probs = results["catboost"].probabilities
        lgb_probs = results["lightgbm"].probabilities

        if cb_probs is not None and lgb_probs is not None:
            ensemble_probs = (cb_probs + lgb_probs) / 2
            ensemble_preds = (ensemble_probs > 0.5).astype(int)

            results["ensemble"] = ModelResult(
                model_name="ensemble",
                model=None,
                probabilities=ensemble_probs,
                predictions=ensemble_preds,
                auc=roc_auc_score(y_val, ensemble_probs),
                accuracy=accuracy_score(y_val, ensemble_preds),
            )

    return results


# =============================================================================
# VOLATILITY MODEL
# =============================================================================


def train_volatility_model(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: pd.DataFrame | None = None,
    y_val: pd.Series | None = None,
    sample_weights: np.ndarray | None = None,
    cfg: config.ModelConfig | None = None,
) -> ModelResult:
    """Train CatBoost regressor for volatility prediction."""
    if not HAS_CATBOOST:
        return ModelResult(model_name="volatility", model=None)

    cfg = cfg or config.MODEL_CONFIG

    model = CatBoostRegressor(
        iterations=cfg.vol_iterations,
        depth=cfg.vol_depth,
        learning_rate=cfg.vol_learning_rate,
        l2_leaf_reg=cfg.cb_l2_reg,
        loss_function="RMSE",
        early_stopping_rounds=cfg.cb_early_stopping if X_val is not None else None,
        verbose=False,
        random_state=cfg.random_state,
    )

    eval_set = (X_val, y_val) if X_val is not None else None
    model.fit(X_train, y_train, eval_set=eval_set, sample_weight=sample_weights)

    result = ModelResult(model_name="volatility", model=model)

    if X_val is not None and y_val is not None:
        preds = model.predict(X_val)
        result.predictions = preds
        result.rmse = np.sqrt(mean_squared_error(y_val, preds))
        result.mae = mean_absolute_error(y_val, preds)
        result.r2 = r2_score(y_val, preds)

    return result


# =============================================================================
# RETURNS REGRESSION
# =============================================================================


def train_returns_model(
    X_train: pd.DataFrame,
    y_train: np.ndarray,
    X_val: pd.DataFrame | None = None,
    y_val: np.ndarray | None = None,
    cfg: config.ModelConfig | None = None,
) -> ModelResult:
    """Train Ridge regression for returns prediction."""
    cfg = cfg or config.MODEL_CONFIG

    model = Ridge(alpha=cfg.returns_alpha)
    model.fit(X_train, y_train)

    result = ModelResult(model_name="returns", model=model)

    if X_val is not None and y_val is not None:
        preds = model.predict(X_val)
        result.predictions = preds
        result.rmse = np.sqrt(mean_squared_error(y_val, preds))
        result.mae = mean_absolute_error(y_val, preds)
        # Directional accuracy
        result.accuracy = np.mean(np.sign(preds) == np.sign(y_val))

    return result


# =============================================================================
# CALIBRATION
# =============================================================================


def calibrate_probabilities(
    train_probs: np.ndarray,
    train_labels: np.ndarray,
    test_probs: np.ndarray,
) -> np.ndarray:
    """
    Calibrate probabilities using isotonic regression.

    Returns:
        Calibrated probabilities for test set
    """
    calibrator = IsotonicRegression(out_of_bounds="clip")
    calibrator.fit(train_probs, train_labels)
    return calibrator.predict(test_probs)


# =============================================================================
# CROSS-VALIDATION
# =============================================================================


def run_direction_cv(
    X: pd.DataFrame,
    y: pd.Series,
    n_splits: int | None = None,
    gap: int | None = None,
    use_purged: bool = False,
) -> dict[str, CVResult]:
    """
    Run time-series cross-validation for direction models.

    Args:
        X: Feature DataFrame
        y: Target Series
        n_splits: Number of CV folds
        gap: Gap between train and test (for TimeSeriesSplit)
        use_purged: If True, use PurgedKFold with purge/embargo gaps

    Returns:
        Dict mapping model name to CVResult
    """
    n_splits = n_splits or config.MODEL_CONFIG.n_cv_splits
    gap = gap or config.WF_CONFIG.cal_size

    if use_purged:
        cv_splitter = PurgedKFold(
            n_splits=n_splits,
            purge_gap=config.MAX_LOOKBACK_BARS,
            embargo_gap=config.MAX_HORIZON_BARS,
        )
    else:
        cv_splitter = TimeSeriesSplit(n_splits=n_splits, gap=gap)

    cv_results: dict[str, CVResult] = {
        "catboost": CVResult(model_name="catboost"),
        "lightgbm": CVResult(model_name="lightgbm"),
        "ensemble": CVResult(model_name="ensemble"),
    }

    for _fold, (train_idx, val_idx) in enumerate(cv_splitter.split(X)):
        X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
        y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]

        weights = data.compute_sample_weights(len(X_train))
        fold_results = train_direction_ensemble(X_train, y_train, X_val, y_val, weights)

        for model_name, result in fold_results.items():
            if model_name in cv_results:
                cv_results[model_name].fold_results.append(result)

    return cv_results


def run_volatility_cv(
    X: pd.DataFrame,
    y: pd.Series,
    n_splits: int | None = None,
    gap: int | None = None,
    use_purged: bool = False,
) -> CVResult:
    """
    Run time-series cross-validation for volatility model.

    Args:
        X: Feature DataFrame
        y: Target Series
        n_splits: Number of CV folds
        gap: Gap between train and test (for TimeSeriesSplit)
        use_purged: If True, use PurgedKFold with purge/embargo gaps

    Returns:
        CVResult with fold results
    """
    n_splits = n_splits or config.MODEL_CONFIG.n_cv_splits
    gap = gap or config.WF_CONFIG.cal_size

    if use_purged:
        cv_splitter = PurgedKFold(
            n_splits=n_splits,
            purge_gap=config.MAX_LOOKBACK_BARS,
            embargo_gap=config.MAX_HORIZON_BARS,
        )
    else:
        cv_splitter = TimeSeriesSplit(n_splits=n_splits, gap=gap)

    cv_result = CVResult(model_name="volatility")

    for _fold, (train_idx, val_idx) in enumerate(cv_splitter.split(X)):
        X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
        y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]

        weights = data.compute_sample_weights(len(X_train))
        result = train_volatility_model(X_train, y_train, X_val, y_val, weights)
        cv_result.fold_results.append(result)

    return cv_result

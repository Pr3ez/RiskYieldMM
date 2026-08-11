"""Train-only transformed L2 logistic baseline and walk-forward evaluation."""

from __future__ import annotations

import math
import warnings
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np
import sklearn
from sklearn.exceptions import ConvergenceWarning
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .splits import (
    ExpandingWalkForwardConfig,
    TimestampLike,
    WalkForwardFold,
    build_expanding_walk_forward,
)

_PROBABILITY_EPSILON = 1e-12


@dataclass(frozen=True)
class LogisticBaselineConfig:
    """Fixed, naturally weighted binary logistic-regression configuration."""

    C: float = 1.0
    max_iter: int = 2_000
    tol: float = 1e-8
    random_state: int = 42

    def __post_init__(self) -> None:
        if not math.isfinite(float(self.C)) or float(self.C) <= 0.0:
            raise ValueError("C must be finite and positive")
        if int(self.max_iter) < 1:
            raise ValueError("max_iter must be at least 1")
        if not math.isfinite(float(self.tol)) or float(self.tol) <= 0.0:
            raise ValueError("tol must be finite and positive")


@dataclass(frozen=True)
class FittedLogisticBaseline:
    """JSON-serializable parameters extracted from an sklearn pipeline."""

    feature_names: tuple[str, ...]
    imputer_statistics: tuple[float, ...]
    scaler_mean: tuple[float, ...]
    scaler_scale: tuple[float, ...]
    coefficients: tuple[float, ...]
    intercept: float
    config: LogisticBaselineConfig
    training_rows: int
    positive_rows: int
    training_prevalence: float
    n_iter: int
    sklearn_version: str

    def transform(self, X: Any) -> np.ndarray:
        """Apply the frozen train-only imputation and scaling parameters."""

        matrix = _as_feature_matrix(X, feature_names=self.feature_names)
        statistics = np.asarray(self.imputer_statistics, dtype=float)
        means = np.asarray(self.scaler_mean, dtype=float)
        scales = np.asarray(self.scaler_scale, dtype=float)
        imputed = np.where(np.isnan(matrix), statistics, matrix)
        return (imputed - means) / scales

    def predict_proba(self, X: Any) -> np.ndarray:
        """Return deterministic positive-class probabilities."""

        transformed = self.transform(X)
        logits = transformed @ np.asarray(self.coefficients, dtype=float)
        logits = logits + float(self.intercept)
        return _stable_sigmoid(logits)


@dataclass(frozen=True)
class WalkForwardFoldEvaluation:
    fold_index: int
    status: str
    reason: str | None
    train_rows: int
    validation_rows: int
    training_positive_rows: int
    training_prevalence: float
    validation_decision_start: datetime
    validation_decision_end: datetime
    training_label_known_through: datetime
    metrics: dict[str, int | float | None] | None
    base_rate_metrics: dict[str, int | float | None] | None


@dataclass(frozen=True)
class WalkForwardEvaluation:
    """Out-of-fold probabilities and causal base-rate controls."""

    folds: tuple[WalkForwardFold, ...]
    fold_evaluations: tuple[WalkForwardFoldEvaluation, ...]
    oof_probabilities: tuple[float | None, ...]
    oof_base_rate_probabilities: tuple[float | None, ...]
    metrics: dict[str, int | float | None]
    base_rate_metrics: dict[str, int | float | None]
    controls: dict[str, int | float | None]


def fit_logistic_baseline(
    X: Any,
    y: Any,
    *,
    feature_names: Sequence[str] | None = None,
    config: LogisticBaselineConfig | None = None,
) -> FittedLogisticBaseline:
    """Fit median imputation, scaling, and L2 logistic regression on one split.

    The pipeline intentionally uses natural class prevalence: no resampling and
    ``class_weight=None``.  Imputation and scaling are fitted only on ``X``.
    """

    resolved_names = _resolve_feature_names(feature_names)
    matrix = _as_feature_matrix(X, feature_names=resolved_names)
    target = _as_binary_target(y, expected_rows=len(matrix))
    if len(matrix) < 2:
        raise ValueError("at least two training rows are required")
    classes = np.unique(target)
    if not np.array_equal(classes, np.array([0, 1])):
        raise ValueError("training target must contain both binary classes")
    missing_columns = np.flatnonzero(np.all(np.isnan(matrix), axis=0))
    if missing_columns.size:
        names = ", ".join(resolved_names[idx] for idx in missing_columns)
        raise ValueError(f"training features are entirely missing: {names}")

    resolved_config = config or LogisticBaselineConfig()
    pipeline = Pipeline(
        steps=[
            (
                "imputer",
                SimpleImputer(
                    strategy="median",
                    copy=True,
                    keep_empty_features=True,
                ),
            ),
            ("scaler", StandardScaler(copy=True, with_mean=True, with_std=True)),
            (
                "classifier",
                LogisticRegression(
                    penalty="l2",
                    C=float(resolved_config.C),
                    class_weight=None,
                    solver="lbfgs",
                    fit_intercept=True,
                    max_iter=int(resolved_config.max_iter),
                    tol=float(resolved_config.tol),
                    random_state=int(resolved_config.random_state),
                ),
            ),
        ]
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ConvergenceWarning)
        pipeline.fit(matrix, target)
    if any(issubclass(item.category, ConvergenceWarning) for item in caught):
        raise RuntimeError(
            "L2 logistic regression did not converge; do not publish this model"
        )

    imputer = pipeline.named_steps["imputer"]
    scaler = pipeline.named_steps["scaler"]
    classifier = pipeline.named_steps["classifier"]
    if not np.array_equal(classifier.classes_, np.array([0, 1])):
        raise RuntimeError("unexpected sklearn class ordering")
    return FittedLogisticBaseline(
        feature_names=resolved_names,
        imputer_statistics=_finite_tuple(
            imputer.statistics_, field="imputer_statistics"
        ),
        scaler_mean=_finite_tuple(scaler.mean_, field="scaler_mean"),
        scaler_scale=_positive_finite_tuple(scaler.scale_, field="scaler_scale"),
        coefficients=_finite_tuple(classifier.coef_[0], field="coefficients"),
        intercept=float(classifier.intercept_[0]),
        config=resolved_config,
        training_rows=int(len(target)),
        positive_rows=int(np.sum(target)),
        training_prevalence=float(np.mean(target)),
        n_iter=int(classifier.n_iter_[0]),
        sklearn_version=str(sklearn.__version__),
    )


def evaluate_walk_forward(
    X: Any,
    y: Any,
    decision_times: Sequence[TimestampLike],
    label_known_times: Sequence[TimestampLike],
    *,
    split_config: ExpandingWalkForwardConfig,
    feature_names: Sequence[str] | None = None,
    model_config: LogisticBaselineConfig | None = None,
) -> WalkForwardEvaluation:
    """Generate leakage-safe OOF predictions and causal prevalence controls."""

    resolved_names = _resolve_feature_names(feature_names)
    matrix = _as_feature_matrix(X, feature_names=resolved_names)
    target = _as_binary_target(y, expected_rows=len(matrix))
    if len(decision_times) != len(matrix) or len(label_known_times) != len(matrix):
        raise ValueError("event timestamps must have one entry per feature row")
    folds = build_expanding_walk_forward(
        decision_times,
        label_known_times,
        config=split_config,
    )
    if not folds:
        raise ValueError("walk-forward configuration produced no validation folds")

    oof_probability = np.full(len(matrix), np.nan, dtype=float)
    oof_base_rate = np.full(len(matrix), np.nan, dtype=float)
    fold_evaluations: list[WalkForwardFoldEvaluation] = []
    fitted_fold_count = 0

    for fold in folds:
        train_idx = np.asarray(fold.train_indices, dtype=int)
        validation_idx = np.asarray(fold.validation_indices, dtype=int)
        y_train = target[train_idx]
        train_prevalence = float(np.mean(y_train))
        training_positive_rows = int(np.sum(y_train))
        if len(np.unique(y_train)) < 2:
            fold_evaluations.append(
                WalkForwardFoldEvaluation(
                    fold_index=fold.fold_index,
                    status="skipped",
                    reason="single_class_training_target",
                    train_rows=int(len(train_idx)),
                    validation_rows=int(len(validation_idx)),
                    training_positive_rows=training_positive_rows,
                    training_prevalence=train_prevalence,
                    validation_decision_start=fold.validation_decision_start,
                    validation_decision_end=fold.validation_decision_end,
                    training_label_known_through=fold.training_label_known_through,
                    metrics=None,
                    base_rate_metrics=None,
                )
            )
            continue

        model = fit_logistic_baseline(
            matrix[train_idx],
            y_train,
            feature_names=resolved_names,
            config=model_config,
        )
        probability = model.predict_proba(matrix[validation_idx])
        base_probability = np.full(len(validation_idx), train_prevalence, dtype=float)
        if np.any(np.isfinite(oof_probability[validation_idx])):
            raise RuntimeError("walk-forward validation windows overlap")
        oof_probability[validation_idx] = probability
        oof_base_rate[validation_idx] = base_probability
        fold_evaluations.append(
            WalkForwardFoldEvaluation(
                fold_index=fold.fold_index,
                status="fitted",
                reason=None,
                train_rows=int(len(train_idx)),
                validation_rows=int(len(validation_idx)),
                training_positive_rows=training_positive_rows,
                training_prevalence=train_prevalence,
                validation_decision_start=fold.validation_decision_start,
                validation_decision_end=fold.validation_decision_end,
                training_label_known_through=fold.training_label_known_through,
                metrics=probability_metrics(target[validation_idx], probability),
                base_rate_metrics=probability_metrics(
                    target[validation_idx], base_probability
                ),
            )
        )
        fitted_fold_count += 1

    scored_mask = np.isfinite(oof_probability)
    if not np.any(scored_mask):
        raise ValueError("no fold had both target classes in its training history")
    metrics = probability_metrics(target[scored_mask], oof_probability[scored_mask])
    base_metrics = probability_metrics(target[scored_mask], oof_base_rate[scored_mask])
    controls = _base_rate_controls(
        metrics=metrics,
        base_rate_metrics=base_metrics,
        total_rows=len(matrix),
        fitted_fold_count=fitted_fold_count,
    )
    return WalkForwardEvaluation(
        folds=folds,
        fold_evaluations=tuple(fold_evaluations),
        oof_probabilities=tuple(
            None if not math.isfinite(value) else float(value)
            for value in oof_probability
        ),
        oof_base_rate_probabilities=tuple(
            None if not math.isfinite(value) else float(value)
            for value in oof_base_rate
        ),
        metrics=metrics,
        base_rate_metrics=base_metrics,
        controls=controls,
    )


def probability_metrics(
    y_true: Any,
    probability: Any,
) -> dict[str, int | float | None]:
    """Proper scoring rules plus PR-AUC for a binary probability forecast."""

    target = _as_binary_target(y_true)
    values = np.asarray(probability, dtype=float)
    if values.ndim != 1 or len(values) != len(target):
        raise ValueError("probability must be one-dimensional and align with y_true")
    if not np.all(np.isfinite(values)):
        raise ValueError("probability contains a non-finite value")
    if np.any((values < 0.0) | (values > 1.0)):
        raise ValueError("probability values must be within [0, 1]")
    clipped = np.clip(values, _PROBABILITY_EPSILON, 1.0 - _PROBABILITY_EPSILON)
    positive_rate = float(np.mean(target)) if len(target) else None
    pr_auc: float | None = None
    if len(target) and len(np.unique(target)) == 2:
        pr_auc = float(average_precision_score(target, values))
    return {
        "rows": int(len(target)),
        "positive_rows": int(np.sum(target)),
        "positive_rate": positive_rate,
        "probability_mean": float(np.mean(values)) if len(values) else None,
        "brier": float(np.mean((values - target) ** 2)) if len(values) else None,
        "log_loss": (
            float(
                -np.mean(
                    target * np.log(clipped) + (1 - target) * np.log(1.0 - clipped)
                )
            )
            if len(values)
            else None
        ),
        "pr_auc": pr_auc,
    }


def _base_rate_controls(
    *,
    metrics: dict[str, int | float | None],
    base_rate_metrics: dict[str, int | float | None],
    total_rows: int,
    fitted_fold_count: int,
) -> dict[str, int | float | None]:
    model_brier = _optional_metric(metrics, "brier")
    base_brier = _optional_metric(base_rate_metrics, "brier")
    model_log_loss = _optional_metric(metrics, "log_loss")
    base_log_loss = _optional_metric(base_rate_metrics, "log_loss")
    model_pr_auc = _optional_metric(metrics, "pr_auc")
    positive_rate = _optional_metric(metrics, "positive_rate")
    return {
        "total_rows": int(total_rows),
        "scored_rows": int(metrics["rows"]),
        "fitted_folds": int(fitted_fold_count),
        "brier_improvement_vs_causal_base_rate": _difference(base_brier, model_brier),
        "log_loss_improvement_vs_causal_base_rate": _difference(
            base_log_loss, model_log_loss
        ),
        "pr_auc_prevalence_baseline": positive_rate,
        "pr_auc_lift_over_prevalence": _ratio(model_pr_auc, positive_rate),
    }


def _resolve_feature_names(feature_names: Sequence[str] | None) -> tuple[str, ...]:
    if feature_names is None:
        from .features import META_FEATURE_NAMES

        resolved = tuple(META_FEATURE_NAMES)
    else:
        resolved = tuple(str(name) for name in feature_names)
    if not resolved:
        raise ValueError("feature_names must not be empty")
    if any(not name.strip() for name in resolved):
        raise ValueError("feature_names cannot contain empty names")
    if len(set(resolved)) != len(resolved):
        raise ValueError("feature_names must be unique and ordered")
    return resolved


def _as_feature_matrix(X: Any, *, feature_names: Sequence[str]) -> np.ndarray:
    try:
        matrix = np.asarray(X, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError("X must be coercible to a numeric matrix") from exc
    if matrix.ndim == 1:
        matrix = matrix.reshape(1, -1)
    if matrix.ndim != 2:
        raise ValueError("X must be a two-dimensional feature matrix")
    if matrix.shape[1] != len(feature_names):
        raise ValueError(
            f"X has {matrix.shape[1]} columns but feature_names has {len(feature_names)}"
        )
    if np.any(np.isinf(matrix)):
        raise ValueError("X contains an infinite feature value")
    return matrix


def _as_binary_target(y: Any, *, expected_rows: int | None = None) -> np.ndarray:
    try:
        values = np.asarray(y, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError("y must be coercible to a binary numeric vector") from exc
    if values.ndim != 1:
        raise ValueError("y must be one-dimensional")
    if expected_rows is not None and len(values) != int(expected_rows):
        raise ValueError("X and y must have equal row counts")
    if not np.all(np.isfinite(values)):
        raise ValueError("y contains a non-finite value")
    if np.any((values != 0.0) & (values != 1.0)):
        raise ValueError("y must contain only binary values 0 and 1")
    return values.astype(int)


def _finite_tuple(values: Any, *, field: str) -> tuple[float, ...]:
    array = np.asarray(values, dtype=float)
    if array.ndim != 1 or not np.all(np.isfinite(array)):
        raise RuntimeError(f"{field} is not a finite one-dimensional vector")
    return tuple(float(value) for value in array)


def _positive_finite_tuple(values: Any, *, field: str) -> tuple[float, ...]:
    result = _finite_tuple(values, field=field)
    if any(value <= 0.0 for value in result):
        raise RuntimeError(f"{field} must be strictly positive")
    return result


def _stable_sigmoid(logits: np.ndarray) -> np.ndarray:
    values = np.asarray(logits, dtype=float)
    result = np.empty_like(values, dtype=float)
    positive = values >= 0.0
    result[positive] = 1.0 / (1.0 + np.exp(-values[positive]))
    exponent = np.exp(values[~positive])
    result[~positive] = exponent / (1.0 + exponent)
    return result


def _optional_metric(metrics: dict[str, int | float | None], key: str) -> float | None:
    value = metrics.get(key)
    return None if value is None else float(value)


def _difference(left: float | None, right: float | None) -> float | None:
    return None if left is None or right is None else float(left - right)


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0.0:
        return None
    return float(numerator / denominator)


__all__ = [
    "FittedLogisticBaseline",
    "LogisticBaselineConfig",
    "WalkForwardEvaluation",
    "WalkForwardFoldEvaluation",
    "evaluate_walk_forward",
    "fit_logistic_baseline",
    "probability_metrics",
]

"""Model boundary for RPF binary classification."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

MODEL_CATBOOST = "catboost"
MODEL_FAMILIES = (MODEL_CATBOOST,)


@dataclass
class FittedClassifier:
    """Classifier plus split-specific prediction boundary."""

    model_family: str
    validation_model: Any
    prediction_model: Any
    validation_rows: int | None = None
    prediction_train_rows: int | None = None
    feature_names: tuple[str, ...] = ()


def fit_classifier(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    *,
    model_family: str,
    feature_names: tuple[str, ...],
    model_updates: dict[str, Any],
    task_type: str,
    thread_count: int,
) -> FittedClassifier:
    if model_family != MODEL_CATBOOST:
        raise ValueError(f"Unsupported classifier model family: {model_family}")
    model = fit_catboost_classifier(
        X_train,
        y_train,
        X_val,
        y_val,
        model_updates=model_updates,
        task_type=task_type,
        thread_count=thread_count,
    )
    return FittedClassifier(
        model_family=MODEL_CATBOOST,
        validation_model=model,
        prediction_model=model,
        feature_names=feature_names,
        validation_rows=int(len(y_train)),
        prediction_train_rows=int(len(y_train)),
    )


def fit_catboost_classifier(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    *,
    model_updates: dict[str, Any],
    task_type: str,
    thread_count: int,
) -> Any:
    try:
        from catboost import CatBoostClassifier
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("CatBoost is required for RPF classification") from exc
    params = catboost_classifier_params(
        model_updates=model_updates,
        task_type=task_type,
        thread_count=thread_count,
        iterations=int(model_updates["iterations"]),
        include_overfit_detector=True,
    )
    model = CatBoostClassifier(**params)
    try:
        model.fit(
            X_train,
            y_train,
            eval_set=(X_val, y_val),
            use_best_model=True,
            early_stopping_rounds=int(model_updates["early_stopping_rounds"]),
            verbose=False,
        )
    except Exception:
        if params["task_type"] != "GPU":
            raise
        params["task_type"] = "CPU"
        params.pop("devices", None)
        model = CatBoostClassifier(**params)
        model.fit(
            X_train,
            y_train,
            eval_set=(X_val, y_val),
            use_best_model=True,
            early_stopping_rounds=int(model_updates["early_stopping_rounds"]),
            verbose=False,
        )
    return model


def fit_prediction_classifier(
    X_train_val: np.ndarray,
    y_train_val: np.ndarray,
    *,
    validation_fit: FittedClassifier,
    model_family: str,
    feature_names: tuple[str, ...],
    model_updates: dict[str, Any],
    task_type: str,
    thread_count: int,
) -> FittedClassifier:
    if model_family != MODEL_CATBOOST:
        raise ValueError(f"Unsupported classifier model family: {model_family}")
    final_model = fit_catboost_final_classifier(
        X_train_val,
        y_train_val,
        validation_model=validation_fit.validation_model,
        model_updates=model_updates,
        task_type=task_type,
        thread_count=thread_count,
    )
    return FittedClassifier(
        model_family=MODEL_CATBOOST,
        validation_model=validation_fit.validation_model,
        prediction_model=final_model,
        feature_names=feature_names,
        validation_rows=validation_fit.validation_rows,
        prediction_train_rows=int(len(y_train_val)),
    )


def fit_catboost_final_classifier(
    X_train_val: np.ndarray,
    y_train_val: np.ndarray,
    *,
    validation_model: Any,
    model_updates: dict[str, Any],
    task_type: str,
    thread_count: int,
) -> Any:
    try:
        from catboost import CatBoostClassifier
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("CatBoost is required for RPF classification") from exc
    iterations = validation_best_iteration(validation_model)
    if iterations is None:
        iterations = int(model_updates["iterations"])
    else:
        iterations = max(1, int(iterations) + 1)
    params = catboost_classifier_params(
        model_updates=model_updates,
        task_type=task_type,
        thread_count=thread_count,
        iterations=iterations,
        include_overfit_detector=False,
    )
    model = CatBoostClassifier(**params)
    try:
        model.fit(X_train_val, y_train_val, verbose=False)
    except Exception:
        if params["task_type"] != "GPU":
            raise
        params["task_type"] = "CPU"
        params.pop("devices", None)
        model = CatBoostClassifier(**params)
        model.fit(X_train_val, y_train_val, verbose=False)
    return model


def catboost_classifier_params(
    *,
    model_updates: dict[str, Any],
    task_type: str,
    thread_count: int,
    iterations: int,
    include_overfit_detector: bool,
) -> dict[str, Any]:
    params = {
        "loss_function": "Logloss",
        "eval_metric": "Logloss",
        "iterations": int(iterations),
        "depth": int(model_updates["depth"]),
        "learning_rate": float(model_updates["learning_rate"]),
        "l2_leaf_reg": float(model_updates["l2_leaf_reg"]),
        "random_seed": 42,
        "allow_writing_files": False,
        "verbose": False,
        "thread_count": int(thread_count),
        "task_type": str(task_type).upper(),
        "has_time": True,
    }
    if include_overfit_detector:
        params["od_type"] = "Iter"
        params["od_wait"] = int(model_updates["od_wait"])
    if str(task_type).upper() == "GPU":
        params["devices"] = "0"
    return params


def validation_probability(model: FittedClassifier, X: np.ndarray) -> np.ndarray:
    return _positive_probability(model.validation_model, X)


def prediction_probability(model: FittedClassifier, X: np.ndarray) -> np.ndarray:
    return _positive_probability(model.prediction_model, X)


def model_diagnostics(model: FittedClassifier) -> dict[str, int | float | str | None]:
    catboost_model = model.validation_model
    best_iteration = validation_best_iteration(catboost_model)
    tree_count = getattr(catboost_model, "tree_count_", None)
    prediction_tree_count = getattr(model.prediction_model, "tree_count_", None)
    validation_params = catboost_model.get_params() if hasattr(catboost_model, "get_params") else {}
    prediction_params = model.prediction_model.get_params() if hasattr(model.prediction_model, "get_params") else {}
    return {
        "model_family": model.model_family,
        "validation_model_task_type": validation_params.get("task_type"),
        "prediction_model_task_type": prediction_params.get("task_type"),
        "model_best_iteration": best_iteration,
        "model_tree_count": None if tree_count is None else int(tree_count),
        "prediction_model_tree_count": None if prediction_tree_count is None else int(prediction_tree_count),
        "prediction_model_fit_rows": model.prediction_train_rows,
        "stat_scaler_policy": None,
        "validation_scaler_fit_rows": None,
        "prediction_scaler_fit_rows": None,
        "elasticnet_nonzero_feature_count": None,
        "elasticnet_coef_abs_mean": None,
        "elasticnet_coef_abs_max": None,
    }


def model_feature_rows(
    model: FittedClassifier,
    *,
    target_col: str,
    step_idx: int,
    pred_batch_id: int,
) -> list[dict[str, Any]]:
    return []


def validation_best_iteration(model: Any) -> int | None:
    get_best_iteration = getattr(model, "get_best_iteration", None)
    if not callable(get_best_iteration):
        return None
    value = get_best_iteration()
    return None if value is None else int(value)


def _positive_probability(model: Any, X: np.ndarray) -> np.ndarray:
    proba = np.asarray(model.predict_proba(X), dtype=float)
    return proba[:, 1]

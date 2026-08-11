"""CatBoost model boundary for clean RPF walk-forward optimization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CatBoostConfig:
    iterations: int = 200
    depth: int = 4
    learning_rate: float = 0.03
    l2_leaf_reg: float = 30.0
    loss_function: str = "RMSE"
    eval_metric: str = "RMSE"
    early_stopping_rounds: int = 50
    od_type: str = "Iter"
    od_wait: int | None = 50
    random_strength: float | None = None
    bootstrap_type: str | None = None
    bagging_temperature: float | None = None
    subsample: float | None = None
    border_count: int | None = None
    has_time: bool = True


def build_catboost_params(config: CatBoostConfig, *, task_type: str, thread_count: int = -1) -> dict[str, Any]:
    task = str(task_type).upper()
    if task not in {"CPU", "GPU"}:
        raise ValueError(f"Unsupported task_type: {task_type}")
    if int(config.iterations) <= 0:
        raise ValueError("iterations must be positive")
    if int(config.depth) <= 0:
        raise ValueError("depth must be positive")
    if float(config.learning_rate) <= 0:
        raise ValueError("learning_rate must be positive")
    if int(config.early_stopping_rounds) <= 0:
        raise ValueError("early_stopping_rounds must be positive")
    params: dict[str, Any] = {
        "loss_function": str(config.loss_function),
        "eval_metric": str(config.eval_metric),
        "iterations": int(config.iterations),
        "depth": int(config.depth),
        "learning_rate": float(config.learning_rate),
        "l2_leaf_reg": float(config.l2_leaf_reg),
        "random_seed": 42,
        "allow_writing_files": False,
        "verbose": False,
        "thread_count": int(thread_count),
        "task_type": task,
        "has_time": bool(config.has_time),
    }
    if config.od_type is not None:
        params["od_type"] = str(config.od_type)
    if config.od_wait is not None:
        params["od_wait"] = int(config.od_wait)
    if config.random_strength is not None:
        params["random_strength"] = float(config.random_strength)
    if config.border_count is not None:
        params["border_count"] = int(config.border_count)
    bootstrap_type = str(config.bootstrap_type) if config.bootstrap_type else None
    if bootstrap_type:
        params["bootstrap_type"] = bootstrap_type
    if config.bagging_temperature is not None:
        if bootstrap_type != "Bayesian":
            raise ValueError("bagging_temperature is valid only with bootstrap_type=Bayesian")
        params["bagging_temperature"] = float(config.bagging_temperature)
    if config.subsample is not None:
        if bootstrap_type not in {"Bernoulli", "Poisson"}:
            raise ValueError("subsample requires bootstrap_type Bernoulli or Poisson")
        if bootstrap_type == "Poisson" and task != "GPU":
            raise ValueError("bootstrap_type=Poisson is GPU-only")
        params["subsample"] = float(config.subsample)
    if task == "GPU":
        params["devices"] = "0"
    return params


def fit_catboost(
    X_train: Any,
    y_train: Any,
    X_val: Any,
    y_val: Any,
    *,
    config: CatBoostConfig,
    task_type: str,
    thread_count: int = -1,
) -> Any:
    try:
        from catboost import CatBoostRegressor
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("CatBoost is required for clean RPF walk-forward") from exc
    params = build_catboost_params(config, task_type=task_type, thread_count=thread_count)
    model = CatBoostRegressor(**params)
    try:
        model.fit(
            X_train,
            y_train,
            eval_set=(X_val, y_val),
            use_best_model=True,
            early_stopping_rounds=int(config.early_stopping_rounds),
            verbose=False,
        )
        return model
    except Exception:
        if params["task_type"] != "GPU":
            raise
        params["task_type"] = "CPU"
        params.pop("devices", None)
        model = CatBoostRegressor(**params)
        model.fit(
            X_train,
            y_train,
            eval_set=(X_val, y_val),
            use_best_model=True,
            early_stopping_rounds=int(config.early_stopping_rounds),
            verbose=False,
        )
        return model


def model_diagnostics(model: Any) -> dict[str, int | None]:
    best_iteration = None
    get_best_iteration = getattr(model, "get_best_iteration", None)
    if callable(get_best_iteration):
        try:
            value = get_best_iteration()
            best_iteration = None if value is None else int(value)
        except Exception:
            best_iteration = None
    tree_count = getattr(model, "tree_count_", None)
    try:
        tree_count = None if tree_count is None else int(tree_count)
    except Exception:
        tree_count = None
    return {"model_best_iteration": best_iteration, "model_tree_count": tree_count}

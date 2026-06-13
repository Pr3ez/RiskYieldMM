"""Metrics for RPF walk-forward regression targets."""

from __future__ import annotations

import math
from typing import Any

import numpy as np


def regression_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float | int | str | None]:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    mask = np.isfinite(y_true) & np.isfinite(y_pred)
    y_true = y_true[mask]
    y_pred = y_pred[mask]
    n = int(len(y_true))
    if n == 0:
        return _empty_metrics("too_few_rows")
    error = y_pred - y_true
    ss_res = float(np.sum(error**2))
    ss_tot = float(np.sum((y_true - np.mean(y_true)) ** 2))
    target_std = float(np.std(y_true))
    pred_std = float(np.std(y_pred))
    target_unique = int(len(np.unique(np.round(y_true, 12))))
    pred_unique = int(len(np.unique(np.round(y_pred, 12))))
    spearman = _correlation(_rankdata_average(y_true), _rankdata_average(y_pred))
    pearson = _correlation(y_true, y_pred)
    target_p95 = float(np.quantile(y_true, 0.95))
    pred_p95 = float(np.quantile(y_pred, 0.95))
    tail_cut = float(np.quantile(y_true, 0.80))
    tail_error = error[y_true >= tail_cut]
    out: dict[str, float | int | str | None] = {
        "rows": n,
        "mae": _safe_float(np.mean(np.abs(error))),
        "rmse": _safe_float(math.sqrt(np.mean(error**2))),
        "median_abs_error": _safe_float(np.median(np.abs(error))),
        "r2": _safe_float(1.0 - ss_res / ss_tot) if ss_tot > 0 else None,
        "pearson": pearson,
        "spearman": spearman,
        "spearman_null_reason": _correlation_null_reason(y_true, y_pred) if spearman is None else None,
        "bias": _safe_float(np.mean(error)),
        "target_mean": _safe_float(np.mean(y_true)),
        "pred_mean": _safe_float(np.mean(y_pred)),
        "target_std": _safe_float(target_std),
        "pred_std": _safe_float(pred_std),
        "target_unique": target_unique,
        "pred_unique": pred_unique,
        "target_p50": _safe_float(np.quantile(y_true, 0.50)),
        "pred_p50": _safe_float(np.quantile(y_pred, 0.50)),
        "target_p95": _safe_float(target_p95),
        "pred_p95": _safe_float(pred_p95),
        "p95_coverage_ratio": _safe_float(pred_p95 / target_p95) if target_p95 > 0 else None,
        "tail_rows": int((y_true >= tail_cut).sum()),
        "tail_mae": _safe_float(np.mean(np.abs(tail_error))) if len(tail_error) else None,
        "tail_rmse": _safe_float(math.sqrt(np.mean(tail_error**2))) if len(tail_error) else None,
        **share_target_metrics(y_true, y_pred),
    }
    return out


def share_target_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float | int | None]:
    if len(y_true) == 0:
        return {
            "direction_accuracy_0p5": None,
            "balanced_direction_accuracy_0p5": None,
            "calibration_error_0p5": None,
            "high_confidence_rows": 0,
            "high_confidence_accuracy": None,
        }
    true_up = y_true >= 0.5
    pred_up = y_pred >= 0.5
    accuracy = float(np.mean(true_up == pred_up))
    recalls: list[float] = []
    for flag in (False, True):
        mask = true_up == flag
        if mask.any():
            recalls.append(float(np.mean(pred_up[mask] == flag)))
    high_conf = (y_pred >= 0.6) | (y_pred <= 0.4)
    return {
        "direction_accuracy_0p5": _safe_float(accuracy),
        "balanced_direction_accuracy_0p5": _safe_float(np.mean(recalls)) if recalls else None,
        "calibration_error_0p5": _safe_float(abs(np.mean(y_pred) - np.mean(y_true))),
        "high_confidence_rows": int(high_conf.sum()),
        "high_confidence_accuracy": _safe_float(np.mean(true_up[high_conf] == pred_up[high_conf])) if high_conf.any() else None,
    }


def objective_score(metrics: dict[str, Any]) -> float:
    rmse = metrics.get("rmse")
    if rmse is None:
        return 1e9
    return float(rmse)


def prediction_collapse_reason(metrics: dict[str, Any], *, min_unique: int = 10, min_std: float = 1e-6) -> str | None:
    if int(metrics.get("rows") or 0) == 0:
        return "no_prediction_rows"
    if int(metrics.get("pred_unique") or 0) <= int(min_unique):
        return "low_prediction_unique"
    if float(metrics.get("pred_std") or 0.0) <= float(min_std):
        return "low_prediction_std"
    if metrics.get("spearman_null_reason") == "constant_prediction":
        return "constant_prediction"
    return None


def _empty_metrics(reason: str) -> dict[str, float | int | str | None]:
    return {
        "rows": 0,
        "mae": None,
        "rmse": None,
        "median_abs_error": None,
        "r2": None,
        "pearson": None,
        "spearman": None,
        "spearman_null_reason": reason,
        "bias": None,
        "target_mean": None,
        "pred_mean": None,
        "target_std": None,
        "pred_std": None,
        "target_unique": 0,
        "pred_unique": 0,
        "target_p50": None,
        "pred_p50": None,
        "target_p95": None,
        "pred_p95": None,
        "p95_coverage_ratio": None,
        "tail_rows": 0,
        "tail_mae": None,
        "tail_rmse": None,
        **share_target_metrics(np.array([]), np.array([])),
    }


def _rankdata_average(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=float)
    if len(values) == 0:
        return ranks
    sorted_values = values[order]
    _, first_idx, counts = np.unique(sorted_values, return_index=True, return_counts=True)
    average_ranks = first_idx.astype(float) + (counts.astype(float) - 1.0) / 2.0
    ranks[order] = np.repeat(average_ranks, counts)
    return ranks


def _correlation_null_reason(a: np.ndarray, b: np.ndarray) -> str | None:
    if len(a) < 2:
        return "too_few_rows"
    if np.std(a) <= 1e-12:
        return "constant_target"
    if np.std(b) <= 1e-12:
        return "constant_prediction"
    return None


def _correlation(a: np.ndarray, b: np.ndarray) -> float | None:
    if _correlation_null_reason(a, b) is not None:
        return None
    return _safe_float(np.corrcoef(a, b)[0, 1])


def _safe_float(value: Any) -> float | None:
    value = float(value)
    if math.isnan(value) or math.isinf(value):
        return None
    return value

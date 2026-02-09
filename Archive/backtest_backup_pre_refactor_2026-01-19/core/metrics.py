"""
Core Metrics Module

Contains metrics computation functions for backtest evaluation:
- build_step_metrics: Build classification and regression metrics for a step
- compute_config_metrics: Compute final metrics for a single config

Dependencies:
- ConfigData dataclass (from services for type hints only)
- sklearn metrics (accuracy, precision, recall, f1, roc_auc)
- scipy stats (spearmanr)
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

# Type-only import to avoid circular dependency
if TYPE_CHECKING:
    pass


def build_step_metrics(
    all_data: dict[str, Any],  # dict[str, ConfigData]
    step: int,
    elapsed: float,
) -> tuple[list[dict], list[dict]]:
    """Build classification and regression metrics dicts for current step.

    Args:
        all_data: Dict mapping config_name to ConfigData
        step: Current step number
        elapsed: Elapsed time in seconds

    Returns:
        Tuple of (classification_metrics_list, regression_metrics_list)
    """
    cls_metrics = []
    reg_metrics = []

    for config_name, data in all_data.items():
        if len(data.predictions) == 0:
            continue

        preds = pd.DataFrame(data.predictions)
        y_true_arr = preds["y_true"].values
        y_pred_arr = preds["y_pred"].values
        n_samples = len(preds)

        if data.task_type == "classification":
            # Compute classification metrics
            acc = accuracy_score(y_true_arr, y_pred_arr)

            # Individual model accuracy
            cb_preds = (
                preds["cb_pred"].values if "cb_pred" in preds.columns else y_pred_arr
            )
            lgb_preds = (
                preds["lgb_pred"].values if "lgb_pred" in preds.columns else y_pred_arr
            )
            lin_preds = (
                preds["linear_pred"].values
                if "linear_pred" in preds.columns
                else y_pred_arr
            )

            cb_acc = accuracy_score(y_true_arr, cb_preds)
            lgb_acc = accuracy_score(y_true_arr, lgb_preds)
            lin_acc = accuracy_score(y_true_arr, lin_preds)

            # AUC for binary
            is_binary = data.n_classes == 2
            if (
                is_binary
                and "y_prob" in preds.columns
                and len(np.unique(y_true_arr)) == 2
            ):
                try:
                    auc = roc_auc_score(y_true_arr, preds["y_prob"].values)
                except ValueError:
                    auc = 0.0
            else:
                auc = 0.0

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                prec = precision_score(
                    y_true_arr, y_pred_arr, average="macro", zero_division=0
                )
                rec = recall_score(
                    y_true_arr, y_pred_arr, average="macro", zero_division=0
                )
                f1 = f1_score(y_true_arr, y_pred_arr, average="macro", zero_division=0)

            cov_pct = (
                preds["covered"].mean() * 100 if preds["covered"].notna().any() else 0.0
            )

            cls_metrics.append(
                {
                    "step": step,
                    "elapsed_s": elapsed,
                    "config": config_name,
                    "n_samples": n_samples,
                    "ens_acc": acc,
                    "cb_acc": cb_acc,
                    "lgb_acc": lgb_acc,
                    "lin_acc": lin_acc,
                    "auc": auc,
                    "precision": prec,
                    "recall": rec,
                    "f1": f1,
                    "coverage_pct": cov_pct,
                    "is_binary": is_binary,
                }
            )

        else:  # regression
            y_true_f = y_true_arr.astype(float)
            y_pred_f = y_pred_arr.astype(float)

            cb_preds = (
                preds["cb_pred"].values.astype(float)
                if "cb_pred" in preds.columns
                else y_pred_f
            )
            lgb_preds = (
                preds["lgb_pred"].values.astype(float)
                if "lgb_pred" in preds.columns
                else y_pred_f
            )
            lin_preds = (
                preds["linear_pred"].values.astype(float)
                if "linear_pred" in preds.columns
                else y_pred_f
            )

            if n_samples > 1:
                ic, _ = stats.spearmanr(y_true_f, y_pred_f)
                cb_ic, _ = stats.spearmanr(y_true_f, cb_preds)
                lgb_ic, _ = stats.spearmanr(y_true_f, lgb_preds)
                lin_ic, _ = stats.spearmanr(y_true_f, lin_preds)
                ic = ic if not np.isnan(ic) else 0.0
                cb_ic = cb_ic if not np.isnan(cb_ic) else 0.0
                lgb_ic = lgb_ic if not np.isnan(lgb_ic) else 0.0
                lin_ic = lin_ic if not np.isnan(lin_ic) else 0.0
            else:
                ic = cb_ic = lgb_ic = lin_ic = 0.0

            rmse = np.sqrt(np.mean((y_true_f - y_pred_f) ** 2))
            mae = np.mean(np.abs(y_true_f - y_pred_f))
            cov_pct = (
                preds["covered"].mean() * 100 if preds["covered"].notna().any() else 0.0
            )

            reg_metrics.append(
                {
                    "step": step,
                    "elapsed_s": elapsed,
                    "config": config_name,
                    "n_samples": n_samples,
                    "ens_ic": ic,
                    "cb_ic": cb_ic,
                    "lgb_ic": lgb_ic,
                    "lin_ic": lin_ic,
                    "rmse": rmse,
                    "mae": mae,
                    "coverage_pct": cov_pct,
                }
            )

    return cls_metrics, reg_metrics


def compute_config_metrics(data: Any) -> dict[str, float]:  # data: ConfigData
    """Compute metrics for a single config from its predictions.

    Args:
        data: ConfigData with predictions

    Returns:
        Dict of metric name -> value
    """
    if not data.predictions:
        return {}

    df = pd.DataFrame(data.predictions)
    y_true = df["y_true"].dropna()
    y_pred = df.loc[y_true.index, "y_pred"]

    if len(y_true) == 0:
        return {}

    metrics = {}

    if data.task_type == "regression":
        # IC
        ic, _ = stats.spearmanr(y_true, y_pred)
        metrics["ic"] = ic if not np.isnan(ic) else 0.0

        # RMSE
        rmse = np.sqrt(np.mean((y_true - y_pred) ** 2))
        metrics["rmse"] = rmse

        # MAE
        mae = np.mean(np.abs(y_true - y_pred))
        metrics["mae"] = mae

        # Coverage
        covered = df["covered"].dropna()
        if len(covered) > 0:
            metrics["coverage"] = covered.mean()

        # Mean interval width
        widths = df["interval_width"].dropna()
        if len(widths) > 0:
            metrics["mean_interval_width"] = widths.mean()

    else:
        # Accuracy
        metrics["accuracy"] = accuracy_score(y_true, y_pred)

        # F1
        metrics["f1_weighted"] = f1_score(
            y_true, y_pred, average="weighted", zero_division=0
        )

        # Coverage
        covered = df["covered"].dropna()
        if len(covered) > 0:
            metrics["coverage"] = covered.mean()

        # Mean set size
        sizes = df["set_size"].dropna()
        if len(sizes) > 0:
            metrics["mean_set_size"] = sizes.mean()

    metrics["n_predictions"] = len(df)

    return metrics


# Exports
__all__ = [
    "build_step_metrics",
    "compute_config_metrics",
]

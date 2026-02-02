"""
Core Metrics Module

Contains metrics computation functions for backtest evaluation:
- build_step_metrics: Build classification and regression metrics for a step
- compute_config_metrics: Compute final metrics for a single config
- compute_direction_weighted_accuracy: Weighted accuracy for direction targets

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


# =============================================================================
# WEIGHTED ACCURACY SCORING MATRICES
# =============================================================================
# For ordinal targets, gives partial credit for predictions that are
# "close" to the correct class in the ordered space.
#
# Scoring logic:
#   - Exact match: 1.0
#   - Adjacent class (1 step away): 0.75
#   - 2 steps away: 0.25
#   - Opposite direction: 0.0

# -----------------------------------------------------------------------------
# DIRECTION (5-class): STRONG_BULLISH, BULLISH, NEUTRAL, BEARISH, STRONG_BEARISH
# -----------------------------------------------------------------------------
DIRECTION_SCORE = {
    0: {0: 1.0, 1: 0.75, 2: 0.25, 3: 0.0, 4: 0.0},  # STRONG_BULLISH
    1: {0: 0.75, 1: 1.0, 2: 0.25, 3: 0.0, 4: 0.0},  # BULLISH
    2: {0: 0.25, 1: 0.25, 2: 1.0, 3: 0.25, 4: 0.25},  # NEUTRAL
    3: {0: 0.0, 1: 0.0, 2: 0.25, 3: 1.0, 4: 0.75},  # BEARISH
    4: {0: 0.0, 1: 0.0, 2: 0.25, 3: 0.75, 4: 1.0},  # STRONG_BEARISH
}

# -----------------------------------------------------------------------------
# TRADE_SETUP (4-class): STRONG_LONG, LONG_SETUP, SHORT_SETUP, STRONG_SHORT
# -----------------------------------------------------------------------------
TRADE_SETUP_SCORE = {
    0: {0: 1.0, 1: 0.75, 2: 0.0, 3: 0.0},  # STRONG_LONG
    1: {0: 0.75, 1: 1.0, 2: 0.25, 3: 0.0},  # LONG_SETUP (adjacent to both)
    2: {0: 0.0, 1: 0.25, 2: 1.0, 3: 0.75},  # SHORT_SETUP (adjacent to both)
    3: {0: 0.0, 1: 0.0, 2: 0.75, 3: 1.0},  # STRONG_SHORT
}

# -----------------------------------------------------------------------------
# TREND_REGIME (3-class): UP, SIDEWAYS, DOWN
# -----------------------------------------------------------------------------
TREND_REGIME_SCORE = {
    0: {0: 1.0, 1: 0.5, 2: 0.0},  # UP
    1: {0: 0.5, 1: 1.0, 2: 0.5},  # SIDEWAYS (middle ground)
    2: {0: 0.0, 1: 0.5, 2: 1.0},  # DOWN
}

# -----------------------------------------------------------------------------
# PATH_LABEL_5 (5-class): STRONG_TREND_UP, WEAK_TREND_UP, SIDEWAYS, WEAK_TREND_DOWN, STRONG_TREND_DOWN
# -----------------------------------------------------------------------------
PATH_LABEL_5_SCORE = {
    0: {0: 1.0, 1: 0.75, 2: 0.25, 3: 0.0, 4: 0.0},  # STRONG_TREND_UP
    1: {0: 0.75, 1: 1.0, 2: 0.5, 3: 0.0, 4: 0.0},  # WEAK_TREND_UP
    2: {0: 0.25, 1: 0.5, 2: 1.0, 3: 0.5, 4: 0.25},  # SIDEWAYS
    3: {0: 0.0, 1: 0.0, 2: 0.5, 3: 1.0, 4: 0.75},  # WEAK_TREND_DOWN
    4: {0: 0.0, 1: 0.0, 2: 0.25, 3: 0.75, 4: 1.0},  # STRONG_TREND_DOWN
}

# -----------------------------------------------------------------------------
# STRATEGY_LABEL (5-class): FLAT, TREND_FOLLOW_LONG, TREND_FOLLOW_SHORT, MEAN_REVERT_LONG, MEAN_REVERT_SHORT
# Strategy labels are not strictly ordinal - give partial credit for same action type
# -----------------------------------------------------------------------------
STRATEGY_LABEL_SCORE = {
    # FLAT (0) - partial credit for any non-aggressive
    0: {0: 1.0, 1: 0.25, 2: 0.25, 3: 0.25, 4: 0.25},
    # TREND_FOLLOW_LONG (1) - partial credit for LONG actions
    1: {0: 0.25, 1: 1.0, 2: 0.0, 3: 0.5, 4: 0.0},
    # TREND_FOLLOW_SHORT (2) - partial credit for SHORT actions
    2: {0: 0.25, 1: 0.0, 2: 1.0, 3: 0.0, 4: 0.5},
    # MEAN_REVERT_LONG (3) - partial credit for LONG actions
    3: {0: 0.25, 1: 0.5, 2: 0.0, 3: 1.0, 4: 0.0},
    # MEAN_REVERT_SHORT (4) - partial credit for SHORT actions
    4: {0: 0.25, 1: 0.0, 2: 0.5, 3: 0.0, 4: 1.0},
}

# Map target prefix to scoring matrix
WEIGHTED_SCORE_MATRICES = {
    "direction": DIRECTION_SCORE,
    "trade_setup": TRADE_SETUP_SCORE,
    "trend_regime": TREND_REGIME_SCORE,
    "path_label_5": PATH_LABEL_5_SCORE,
    "strategy_label": STRATEGY_LABEL_SCORE,
}


def compute_weighted_accuracy(
    y_true: np.ndarray | list,
    y_pred: np.ndarray | list,
    score_matrix: dict[int, dict[int, float]],
) -> float:
    """
    Compute weighted accuracy using a scoring matrix.

    Gives partial credit based on the score_matrix[pred][actual] values.

    Args:
        y_true: Array of actual class labels
        y_pred: Array of predicted class labels
        score_matrix: Dict of {pred: {actual: score}} mappings

    Returns:
        Weighted accuracy score (0.0 to 1.0)
    """
    y_true = np.asarray(y_true).astype(int)
    y_pred = np.asarray(y_pred).astype(int)

    if len(y_true) == 0:
        return 0.0

    total_score = 0.0
    for pred, actual in zip(y_pred, y_true):
        # Handle out-of-range values gracefully
        if pred in score_matrix and actual in score_matrix[pred]:
            total_score += score_matrix[pred][actual]
        elif pred == actual:
            total_score += 1.0  # Exact match fallback

    return total_score / len(y_true)


def compute_direction_weighted_accuracy(
    y_true: np.ndarray | list,
    y_pred: np.ndarray | list,
) -> float:
    """
    Compute weighted accuracy for direction targets with partial credit.

    Gives partial credit when prediction is directionally correct but
    intensity is wrong (e.g., pred=BULLISH, actual=STRONG_BULLISH = 0.75).

    Args:
        y_true: Array of actual class labels (0-4)
        y_pred: Array of predicted class labels (0-4)

    Returns:
        Weighted accuracy score (0.0 to 1.0)

    Example:
        >>> y_true = [0, 1, 2, 3, 4]  # STRONG_BULL, BULL, NEUTRAL, BEAR, STRONG_BEAR
        >>> y_pred = [1, 1, 2, 3, 3]  # BULL, BULL, NEUTRAL, BEAR, BEAR
        >>> compute_direction_weighted_accuracy(y_true, y_pred)
        0.9  # (0.75 + 1.0 + 1.0 + 1.0 + 0.75) / 5
    """
    return compute_weighted_accuracy(y_true, y_pred, DIRECTION_SCORE)


def get_weighted_accuracy_for_config(
    config_name: str,
    y_true: np.ndarray | list,
    y_pred: np.ndarray | list,
) -> float | None:
    """
    Get weighted accuracy for a config if it supports weighted scoring.

    Args:
        config_name: Config name (e.g., "direction_1bar", "trade_setup_1bar")
        y_true: Array of actual class labels
        y_pred: Array of predicted class labels

    Returns:
        Weighted accuracy score (0.0 to 1.0) or None if not supported
    """
    # Find matching score matrix by prefix
    for prefix, score_matrix in WEIGHTED_SCORE_MATRICES.items():
        if config_name.startswith(prefix):
            return compute_weighted_accuracy(y_true, y_pred, score_matrix)
    return None


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

            # Weighted accuracy for direction targets (partial credit for directionally correct)
            is_direction = config_name.startswith("direction")
            if is_direction:
                weighted_acc = compute_direction_weighted_accuracy(
                    y_true_arr, y_pred_arr
                )
                cb_weighted_acc = compute_direction_weighted_accuracy(
                    y_true_arr, cb_preds
                )
                lgb_weighted_acc = compute_direction_weighted_accuracy(
                    y_true_arr, lgb_preds
                )
                lin_weighted_acc = compute_direction_weighted_accuracy(
                    y_true_arr, lin_preds
                )
            else:
                weighted_acc = acc  # Same as strict accuracy for non-direction
                cb_weighted_acc = cb_acc
                lgb_weighted_acc = lgb_acc
                lin_weighted_acc = lin_acc

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
                    "ens_weighted_acc": weighted_acc,
                    "cb_weighted_acc": cb_weighted_acc,
                    "lgb_weighted_acc": lgb_weighted_acc,
                    "lin_weighted_acc": lin_weighted_acc,
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

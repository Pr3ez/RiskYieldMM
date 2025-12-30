"""
Validation functions for training window quality.

This module provides validators for:
1. Class balance checking (t1-1-i1, t1-1-i2)
2. Look-ahead bias prevention (t1-3-i1)

Research basis: docs/validation/ADAPTIVE_OPTIMIZATION_RESEARCH.md
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass
from math import log

import numpy as np

logger = logging.getLogger(__name__)


# =============================================================================
# CLASS BALANCE VALIDATION (Tier 1.1)
# =============================================================================


@dataclass
class ClassBalanceMetrics:
    """Metrics from class balance validation.

    Attributes:
        n_classes: Number of unique classes in target
        class_counts: Dict mapping class label to count
        min_class_count: Count of smallest class
        balance_score: Normalized entropy (0-1, 1=perfect balance)
        majority_class: Label of the most frequent class
        minority_class: Label of the least frequent class
    """

    n_classes: int
    class_counts: dict[int, int]
    min_class_count: int
    balance_score: float
    majority_class: int
    minority_class: int

    def __repr__(self) -> str:
        return (
            f"ClassBalanceMetrics(n_classes={self.n_classes}, "
            f"min_count={self.min_class_count}, "
            f"balance={self.balance_score:.3f})"
        )


def compute_class_entropy(class_counts: dict[int, int]) -> tuple[float, float]:
    """Compute Shannon entropy and normalized balance score.

    Args:
        class_counts: Dict mapping class labels to counts

    Returns:
        (entropy, balance_score) where balance_score is normalized 0-1

    Research basis:
        - Normalized entropy = entropy / max_entropy
        - max_entropy = log(n_classes) for uniform distribution
        - balance_score=1.0 means perfect balance
        - balance_score=0.5 allows up to ~80/10/10 split (3-class)
    """
    if len(class_counts) < 2:
        return 0.0, 0.0

    total = sum(class_counts.values())
    if total == 0:
        return 0.0, 0.0

    # Compute Shannon entropy
    entropy = 0.0
    for count in class_counts.values():
        if count > 0:
            p = count / total
            entropy -= p * log(p)

    # Normalize by maximum entropy (uniform distribution)
    n_classes = len(class_counts)
    max_entropy = log(n_classes)

    if max_entropy == 0:
        return 0.0, 0.0

    balance_score = entropy / max_entropy
    return entropy, balance_score


def validate_class_balance(
    y_train: np.ndarray,
    min_samples_per_class: int = 30,
    min_balance_score: float = 0.5,
    warn_samples_per_class: int = 50,
) -> tuple[bool, str, ClassBalanceMetrics]:
    """Validate class balance for training data.

    Checks:
    1. At least 2 classes present (hard requirement)
    2. Minority class has >= min_samples_per_class (soft requirement)
    3. Balance score >= min_balance_score (entropy-based check)

    Args:
        y_train: Training target array
        min_samples_per_class: Minimum samples required per class (default 30)
        min_balance_score: Minimum normalized entropy (default 0.5)
        warn_samples_per_class: Warn if minority below this (default 50)

    Returns:
        (is_valid, message, metrics)

    Research basis:
        - Silvey & Liu 2024: XGBoost needs ~205 EPV for AUC stability
        - Abdelhamid & Desai 2024: Use class weights, avoid SMOTE
        - Entropy-based balance scoring from HMM quality functions

    Example:
        >>> y = np.array([0, 0, 0, 1, 1, 2])  # 3 classes
        >>> is_valid, msg, metrics = validate_class_balance(y, min_samples_per_class=2)
        >>> print(f"Valid: {is_valid}, Balance: {metrics.balance_score:.2f}")
    """
    # Handle edge cases
    if y_train is None or len(y_train) == 0:
        metrics = ClassBalanceMetrics(
            n_classes=0,
            class_counts={},
            min_class_count=0,
            balance_score=0.0,
            majority_class=-1,
            minority_class=-1,
        )
        return False, "FAIL: Empty training data", metrics

    # Count classes
    class_counts = dict(Counter(y_train))
    n_classes = len(class_counts)

    # Find majority/minority classes
    if n_classes > 0:
        majority_class = max(class_counts, key=class_counts.get)
        minority_class = min(class_counts, key=class_counts.get)
        min_class_count = class_counts[minority_class]
    else:
        majority_class = -1
        minority_class = -1
        min_class_count = 0

    # Compute entropy-based balance score
    _, balance_score = compute_class_entropy(class_counts)

    # Build metrics object
    metrics = ClassBalanceMetrics(
        n_classes=n_classes,
        class_counts=class_counts,
        min_class_count=min_class_count,
        balance_score=balance_score,
        majority_class=majority_class,
        minority_class=minority_class,
    )

    # Validation checks

    # Check 1: At least 2 classes (hard requirement)
    if n_classes < 2:
        return False, "FAIL: Single class window - cannot train classifier", metrics

    # Check 2: Minimum samples per class
    if min_class_count < min_samples_per_class:
        return (
            False,
            (
                f"FAIL: Minority class {minority_class} has {min_class_count} samples "
                f"(need {min_samples_per_class})"
            ),
            metrics,
        )

    # Check 3: Balance score (entropy-based)
    if balance_score < min_balance_score:
        return (
            False,
            (
                f"FAIL: Severe imbalance, balance_score={balance_score:.3f} "
                f"(need {min_balance_score})"
            ),
            metrics,
        )

    # All checks passed - build success message
    warning = ""
    if min_class_count < warn_samples_per_class:
        warning = (
            f" (WARNING: minority class {min_class_count} < {warn_samples_per_class})"
        )

    return (
        True,
        (
            f"PASS: {n_classes} classes, min={min_class_count}, "
            f"balance={balance_score:.3f}{warning}"
        ),
        metrics,
    )


# =============================================================================
# LOOK-AHEAD BIAS VALIDATION (Tier 1.3)
# =============================================================================


@dataclass
class LookaheadMetrics:
    """Metrics from look-ahead bias validation.

    Attributes:
        pred_idx: Index where prediction will be made
        train_end_idx: Last index in training set
        cal_start_idx: First index in calibration set
        actual_gap: Actual gap between train end and cal start
        required_gap: Minimum required gap (horizon)
        horizon: Forecast horizon in bars
    """

    pred_idx: int
    train_end_idx: int
    cal_start_idx: int
    actual_gap: int
    required_gap: int
    horizon: int

    def __repr__(self) -> str:
        return (
            f"LookaheadMetrics(gap={self.actual_gap}, "
            f"required={self.required_gap}, "
            f"margin={self.actual_gap - self.required_gap})"
        )


def compute_purge_gap(horizon: int, safety_buffer: int = 10) -> int:
    """Compute appropriate purge gap for given horizon.

    Formula: gap = horizon + max(10, horizon * 0.5)

    Args:
        horizon: Forecast horizon in bars
        safety_buffer: Minimum buffer to add (default 10)

    Returns:
        Recommended purge gap

    Research basis:
        - López de Prado 2018: Purge >= horizon, embargo 1-5%
        - Safety buffer accounts for feature memory (GARCH, MAs)

    Examples:
        horizon=1  → gap=11 (1 + 10)
        horizon=4  → gap=14 (4 + 10)
        horizon=8  → gap=18 (8 + 10)
        horizon=12 → gap=22 (12 + 10)
        horizon=20 → gap=30 (20 + 10)
    """
    buffer = max(safety_buffer, int(horizon * 0.5))
    return horizon + buffer


def validate_no_lookahead(
    pred_idx: int,
    train_end_idx: int,
    cal_start_idx: int,
    horizon: int,
    purge_gap: int,
) -> tuple[bool, str, LookaheadMetrics]:
    """Validate that window configuration prevents look-ahead bias.

    Checks:
    1. Train set ends before prediction index
    2. Actual gap between train and cal >= horizon
    3. Purge gap has safety buffer (warning if < horizon + 10)

    Args:
        pred_idx: Index where prediction will be made
        train_end_idx: Last index in training set
        cal_start_idx: First index in calibration set
        horizon: Forecast horizon in bars
        purge_gap: Configured purge gap

    Returns:
        (is_valid, message, metrics)

    Research basis:
        - López de Prado 2018: Purged Cross-Validation
        - Purge removes observations whose labels overlap with test
        - Embargo adds buffer for market reaction lag

    Example:
        >>> is_valid, msg, metrics = validate_no_lookahead(
        ...     pred_idx=500, train_end_idx=274, cal_start_idx=296,
        ...     horizon=12, purge_gap=21
        ... )
    """
    # Compute actual gap
    actual_gap = cal_start_idx - train_end_idx - 1

    # Build metrics
    metrics = LookaheadMetrics(
        pred_idx=pred_idx,
        train_end_idx=train_end_idx,
        cal_start_idx=cal_start_idx,
        actual_gap=actual_gap,
        required_gap=horizon,
        horizon=horizon,
    )

    # Check 1: Train must end before prediction
    if train_end_idx >= pred_idx:
        return (
            False,
            (f"FAIL: Train ends at {train_end_idx} >= pred at {pred_idx}"),
            metrics,
        )

    # Check 2: Gap must be at least horizon
    if actual_gap < horizon:
        return False, (f"FAIL: Gap ({actual_gap}) < horizon ({horizon})"), metrics

    # Check 3: Purge gap should have safety buffer (warning only)
    min_purge = horizon + 10
    if purge_gap < min_purge:
        warning = f" (WARNING: purge_gap {purge_gap} < recommended {min_purge})"
    else:
        warning = ""

    return (
        True,
        (
            f"PASS: train_end={train_end_idx}, gap={actual_gap}, "
            f"horizon={horizon}{warning}"
        ),
        metrics,
    )


# =============================================================================
# COMBINED VALIDATION
# =============================================================================


def validate_training_window(
    y_train: np.ndarray,
    pred_idx: int,
    train_end_idx: int,
    cal_start_idx: int,
    horizon: int,
    purge_gap: int,
    min_samples_per_class: int = 30,
    min_balance_score: float = 0.5,
) -> tuple[bool, str, dict]:
    """Validate both class balance and look-ahead bias for a training window.

    Combines validate_class_balance() and validate_no_lookahead() into
    a single validation pass.

    Args:
        y_train: Training target array
        pred_idx: Index where prediction will be made
        train_end_idx: Last index in training set
        cal_start_idx: First index in calibration set
        horizon: Forecast horizon in bars
        purge_gap: Configured purge gap
        min_samples_per_class: Minimum samples per class
        min_balance_score: Minimum entropy-based balance score

    Returns:
        (is_valid, message, metrics_dict)
        metrics_dict contains 'class_balance' and 'lookahead' keys
    """
    # Validate class balance
    class_valid, class_msg, class_metrics = validate_class_balance(
        y_train,
        min_samples_per_class=min_samples_per_class,
        min_balance_score=min_balance_score,
    )

    # Validate look-ahead bias
    la_valid, la_msg, la_metrics = validate_no_lookahead(
        pred_idx=pred_idx,
        train_end_idx=train_end_idx,
        cal_start_idx=cal_start_idx,
        horizon=horizon,
        purge_gap=purge_gap,
    )

    # Combine results
    is_valid = class_valid and la_valid
    messages = []
    if not class_valid:
        messages.append(f"ClassBalance: {class_msg}")
    if not la_valid:
        messages.append(f"Lookahead: {la_msg}")

    if is_valid:
        message = f"PASS: {class_metrics.n_classes} classes, balance={class_metrics.balance_score:.3f}"
    else:
        message = " | ".join(messages)

    metrics = {
        "class_balance": class_metrics,
        "lookahead": la_metrics,
    }

    return is_valid, message, metrics


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "ClassBalanceMetrics",
    "LookaheadMetrics",
    "compute_class_entropy",
    "compute_purge_gap",
    "validate_class_balance",
    "validate_no_lookahead",
    "validate_training_window",
]

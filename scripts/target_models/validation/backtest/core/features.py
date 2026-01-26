"""
Feature selection utilities for per-model architecture.

Provides:
- apply_feature_selection(): Select top features by variance, importance, or ICIR
- extract_per_model_splits(): Extract train/val/cal splits from full window

These are shared utilities used by all model modules.
Extracted from services/training.py for modularity.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from backtest.core.base import ModelConfig


__all__ = [
    "apply_feature_selection",
    "extract_per_model_splits",
]


def apply_feature_selection(
    X: pd.DataFrame,
    method: str,
    model: Any = None,
    ratio: float = 0.5,
    min_features: int = 20,
) -> tuple[pd.DataFrame, list[str]]:
    """Apply feature selection to reduce feature set.

    Methods:
    - 'variance': Keep features with highest variance
    - 'importance': Use model's feature_importances_ (requires trained model)
    - 'icir': Information Coefficient / Information Ratio (for linear models)
    - 'none': Keep all features

    Args:
        X: Feature DataFrame
        method: Selection method ('variance', 'importance', 'icir', 'none')
        model: Trained model for importance-based selection
        ratio: Fraction of features to keep (0.0-1.0)
        min_features: Minimum number of features to keep

    Returns:
        Tuple of (selected X, selected feature names)

    Example:
        # After training a CatBoost model
        X_selected, features = apply_feature_selection(
            X_full, method="importance", model=cb_model, ratio=0.6
        )
    """
    # Handle 'none' case first
    if method == "none" or ratio >= 1.0:
        return X, X.columns.tolist()

    n_features = len(X.columns)
    n_keep = max(min_features, int(n_features * ratio))

    # Ensure we don't try to keep more features than exist
    n_keep = min(n_keep, n_features)

    if method == "variance":
        # Keep features with highest variance
        variances = X.var()
        selected_features = variances.nlargest(n_keep).index.tolist()

    elif method == "importance" and model is not None:
        # Use model's feature importance
        if hasattr(model, "feature_importances_"):
            importances = model.feature_importances_
        elif hasattr(model, "get_feature_importance"):
            # CatBoost uses this method
            importances = model.get_feature_importance()
        else:
            # Fallback to variance if model doesn't support importance
            variances = X.var()
            selected_features = variances.nlargest(n_keep).index.tolist()
            return X[selected_features], selected_features

        # Get top features by importance
        feature_names = X.columns.tolist()
        sorted_idx = np.argsort(importances)[::-1]
        selected_features = [feature_names[i] for i in sorted_idx[:n_keep]]

    elif method == "icir":
        # Information Coefficient / Information Ratio
        # For now, use correlation with target as proxy
        # TODO: Implement proper ICIR calculation
        variances = X.var()
        selected_features = variances.nlargest(n_keep).index.tolist()

    else:
        # Unknown method or no model for importance - keep all
        selected_features = X.columns.tolist()

    return X[selected_features], selected_features


def extract_per_model_splits(
    X_full: pd.DataFrame,
    y_full: pd.Series,
    model_config: ModelConfig,
    full_window_size: int,
) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series, pd.DataFrame, pd.Series]:
    """Extract train/val/cal splits for a specific model from full window.

    The full window has `full_window_size` rows. The model's config specifies
    a (potentially smaller) `train_window`. We take the MOST RECENT data
    to respect temporal ordering.

    Example with Linear window=800 (full window) and CB window=400:
    - Linear uses all 800 rows
    - CB uses rows 400-800 (most recent 400)

    Split structure within model window (with embargo gaps):
    [train] [embargo] [val] [embargo] [cal]

    Args:
        X_full: Full feature window (full_window_size rows)
        y_full: Full target window (full_window_size rows)
        model_config: Configuration for this specific model
        full_window_size: Size of the full window (should match len(X_full))

    Returns:
        X_train, y_train, X_val, y_val, X_cal, y_cal - per-model splits

    Example:
        X_train, y_train, X_val, y_val, X_cal, y_cal = extract_per_model_splits(
            X_full=X_window,
            y_full=y_window,
            model_config=cb_config,
            full_window_size=800,
        )
    """
    model_window = model_config.train_window

    # If model window equals full window, use all data
    # Otherwise, use the MOST RECENT `model_window` rows
    if model_window >= full_window_size:
        start_offset = 0
    else:
        start_offset = full_window_size - model_window

    # Extract model's window
    X_model = X_full.iloc[start_offset:]
    y_model = y_full.iloc[start_offset:]

    # Calculate split sizes with embargo
    total_embargo = 2 * model_config.embargo_bars
    usable_window = len(X_model) - total_embargo
    train_size = int(usable_window * model_config.train_ratio)
    val_size = int(usable_window * model_config.val_ratio)
    cal_size = usable_window - train_size - val_size

    # Split with embargo gaps
    train_end = train_size
    val_start = train_end + model_config.embargo_bars
    val_end = val_start + val_size
    cal_start = val_end + model_config.embargo_bars
    cal_end = cal_start + cal_size

    X_train = X_model.iloc[:train_end]
    y_train = y_model.iloc[:train_end]
    X_val = X_model.iloc[val_start:val_end]
    y_val = y_model.iloc[val_start:val_end]
    X_cal = X_model.iloc[cal_start:cal_end]
    y_cal = y_model.iloc[cal_start:cal_end]

    return X_train, y_train, X_val, y_val, X_cal, y_cal

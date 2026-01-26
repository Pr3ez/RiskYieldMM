"""
Multi-Class Signal Labeling for Trading ML.

Research-backed signal labeling based on:
1. Lopez de Prado - Triple Barrier Method (AFML Ch. 3)
2. Dezhkam et al. (2022) - Bayesian tri-state labeling
3. Hudson & Thames - Meta-labeling approach

Key Principles:
- Binary labeling (ret > 0) is WRONG - can't distinguish signal from noise
- Multi-class separates STRONG signals, WEAK signals, and NO SIGNAL
- Threshold should be volatility-scaled for adaptivity
- Training labels should align with economic outcomes (barrier hits)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Literal

import numpy as np
import pandas as pd

# Import centralized targets module for consistency
from scripts.workflow.targets import (
    compute_target_pandas,
    get_config_horizon,
    get_config_target,
)


class Signal3Class(IntEnum):
    """3-class signal labels (research-backed tri-state approach)."""

    DOWN = 0  # Clear short signal
    UP = 1  # Clear long signal
    NEUTRAL = 2  # No clear signal - do not trade


class Signal5Class(IntEnum):
    """5-class signal labels with strength gradation."""

    STRONG_SHORT = 0  # SL barrier hit - high confidence short
    WEAK_SHORT = 1  # Negative return but no barrier - low confidence short
    NO_SIGNAL = 2  # Neutral - no tradeable signal
    WEAK_LONG = 3  # Positive return but no barrier - low confidence long
    STRONG_LONG = 4  # TP barrier hit - high confidence long


class Signal4Class(IntEnum):
    """4-class actionable signals only (no neutral)."""

    STRONG_SHORT = 0
    WEAK_SHORT = 1
    WEAK_LONG = 2
    STRONG_LONG = 3


@dataclass
class LabelingConfig:
    """Configuration for signal labeling."""

    # Threshold as multiple of rolling volatility
    threshold_sigma: float = 0.5

    # Minimum threshold (to avoid noise in low-vol periods)
    min_threshold: float = 0.005  # 0.5%

    # Maximum threshold (to capture signals in high-vol periods)
    max_threshold: float = 0.05  # 5%

    # Rolling window for volatility estimation
    vol_lookback: int = 21

    # Whether to use triple barrier info when available
    use_triple_barrier: bool = True

    # Warmup period (exclude from training to avoid leakage)
    warmup_bars: int = 100


def compute_adaptive_threshold(
    returns: pd.Series,
    config: LabelingConfig | None = None,
) -> pd.Series:
    """
    Compute volatility-adaptive threshold for signal classification.

    Key insight from research: Fixed thresholds fail during regime changes.
    Adaptive thresholds adjust to current market volatility.

    Args:
        returns: Series of returns (e.g., forward returns)
        config: Labeling configuration

    Returns:
        Series of adaptive thresholds (same index as returns)
    """
    if config is None:
        config = LabelingConfig()

    # Rolling volatility (standard deviation)
    rolling_vol = returns.rolling(
        window=config.vol_lookback,
        min_periods=config.vol_lookback // 2,
    ).std()

    # Threshold = sigma_multiple * volatility
    threshold = config.threshold_sigma * rolling_vol

    # Clip to reasonable bounds
    threshold = threshold.clip(lower=config.min_threshold, upper=config.max_threshold)

    # Forward fill NaN (for early bars before window fills)
    threshold = threshold.bfill()

    return threshold


def compute_tristate_labels(
    df: pd.DataFrame,
    config: LabelingConfig | None = None,
    return_col: str = "y_tb_return",
    barrier_col: str = "y_tb_barrier",
) -> pd.Series:
    """
    Compute 3-class (tri-state) signal labels.

    Based on Dezhkam et al. (2022) Bayesian framework:
    - UP (+1): Clear upward signal - trade long
    - DOWN (0): Clear downward signal - trade short
    - NEUTRAL (2): No clear signal - do not trade

    Research Result: This approach achieved SR=2.82 vs binary SR~0.5

    Args:
        df: DataFrame with returns and optionally barrier info
        config: Labeling configuration
        return_col: Column name for forward returns
        barrier_col: Column name for triple barrier type (optional)

    Returns:
        Series of Signal3Class labels
    """
    if config is None:
        config = LabelingConfig()

    # Get returns
    if return_col not in df.columns:
        raise ValueError(f"Return column '{return_col}' not found in DataFrame")

    ret = df[return_col].copy()

    # Compute adaptive threshold
    threshold = compute_adaptive_threshold(ret, config)

    # Initialize as NEUTRAL (default when unclear)
    labels = pd.Series(Signal3Class.NEUTRAL, index=df.index)

    # Use triple barrier if available and enabled
    if config.use_triple_barrier and barrier_col in df.columns:
        barrier = df[barrier_col]

        # Strong signals from barrier hits
        labels[barrier == "TP"] = Signal3Class.UP
        labels[barrier == "SL"] = Signal3Class.DOWN

        # TIME barrier: classify by magnitude vs threshold
        time_mask = barrier == "TIME"
        labels.loc[time_mask & (ret > threshold)] = Signal3Class.UP
        labels.loc[time_mask & (ret < -threshold)] = Signal3Class.DOWN
        # TIME + |ret| < threshold → remains NEUTRAL
    else:
        # No barrier info: use pure threshold approach
        labels[ret > threshold] = Signal3Class.UP
        labels[ret < -threshold] = Signal3Class.DOWN

    return labels.astype(np.int64)


def compute_multiclass_labels(
    df: pd.DataFrame,
    config: LabelingConfig | None = None,
    return_col: str = "y_tb_return",
    barrier_col: str = "y_tb_barrier",
) -> pd.Series:
    """
    Compute 5-class signal labels with strength gradation.

    Classes:
    - STRONG_SHORT (0): SL barrier hit - high confidence short
    - WEAK_SHORT (1): Negative return, no barrier - low confidence short
    - NO_SIGNAL (2): Small return - no tradeable signal
    - WEAK_LONG (3): Positive return, no barrier - low confidence long
    - STRONG_LONG (4): TP barrier hit - high confidence long

    Args:
        df: DataFrame with returns and barrier info
        config: Labeling configuration
        return_col: Column name for forward returns
        barrier_col: Column name for triple barrier type

    Returns:
        Series of Signal5Class labels
    """
    if config is None:
        config = LabelingConfig()

    ret = df[return_col].copy()
    threshold = compute_adaptive_threshold(ret, config)

    # Initialize as NO_SIGNAL
    labels = pd.Series(Signal5Class.NO_SIGNAL, index=df.index)

    if barrier_col in df.columns:
        barrier = df[barrier_col]

        # Strong signals from barrier hits (high confidence)
        labels[barrier == "TP"] = Signal5Class.STRONG_LONG
        labels[barrier == "SL"] = Signal5Class.STRONG_SHORT

        # TIME barrier: classify by magnitude
        time_mask = barrier == "TIME"
        labels.loc[time_mask & (ret > threshold)] = Signal5Class.WEAK_LONG
        labels.loc[time_mask & (ret < -threshold)] = Signal5Class.WEAK_SHORT
        # TIME + |ret| < threshold → NO_SIGNAL
    else:
        # Fallback: use return magnitude only
        labels[ret > 2 * threshold] = Signal5Class.STRONG_LONG
        labels[(ret > threshold) & (ret <= 2 * threshold)] = Signal5Class.WEAK_LONG
        labels[(ret < -threshold) & (ret >= -2 * threshold)] = Signal5Class.WEAK_SHORT
        labels[ret < -2 * threshold] = Signal5Class.STRONG_SHORT

    return labels.astype(np.int64)


def compute_actionable_labels(
    df: pd.DataFrame,
    config: LabelingConfig | None = None,
    return_col: str = "y_tb_return",
    barrier_col: str = "y_tb_barrier",
) -> pd.Series:
    """
    Compute 4-class actionable signal labels (no neutral class).

    For trading systems that act on all samples:
    - STRONG_SHORT (0): High confidence short
    - WEAK_SHORT (1): Low confidence short
    - WEAK_LONG (2): Low confidence long
    - STRONG_LONG (3): High confidence long

    Note: Samples that would be NEUTRAL are assigned to nearest weak class.

    Args:
        df: DataFrame with returns and barrier info
        config: Labeling configuration
        return_col: Column name for forward returns
        barrier_col: Column name for triple barrier type

    Returns:
        Series of Signal4Class labels
    """
    if config is None:
        config = LabelingConfig()

    ret = df[return_col].copy()
    threshold = compute_adaptive_threshold(ret, config)

    # Initialize based on sign of return (no neutral)
    labels = pd.Series(Signal4Class.WEAK_LONG, index=df.index)
    labels[ret < 0] = Signal4Class.WEAK_SHORT

    if barrier_col in df.columns:
        barrier = df[barrier_col]

        # Strong signals from barrier hits
        labels[barrier == "TP"] = Signal4Class.STRONG_LONG
        labels[barrier == "SL"] = Signal4Class.STRONG_SHORT

        # For TIME, assign to weak classes based on sign
        time_mask = barrier == "TIME"
        labels.loc[time_mask & (ret >= 0)] = Signal4Class.WEAK_LONG
        labels.loc[time_mask & (ret < 0)] = Signal4Class.WEAK_SHORT
    else:
        # No barrier: use return magnitude
        labels[ret > 2 * threshold] = Signal4Class.STRONG_LONG
        labels[ret < -2 * threshold] = Signal4Class.STRONG_SHORT

    return labels.astype(np.int64)


def add_signal_labels_to_df(
    df: pd.DataFrame,
    config: LabelingConfig | None = None,
    schemes: list[Literal["3class", "5class", "4class"]] | None = None,
    return_col: str = "y_tb_return",
    barrier_col: str = "y_tb_barrier",
) -> pd.DataFrame:
    """
    Add signal label columns to DataFrame.

    Args:
        df: Input DataFrame
        config: Labeling configuration
        schemes: Which labeling schemes to add. Default: all
        return_col: Column name for forward returns
        barrier_col: Column name for triple barrier type

    Returns:
        DataFrame with new label columns added
    """
    if schemes is None:
        schemes = ["3class", "5class", "4class"]

    if config is None:
        config = LabelingConfig()

    df = df.copy()

    if "3class" in schemes:
        df["y_signal_3c"] = compute_tristate_labels(df, config, return_col, barrier_col)

    if "5class" in schemes:
        df["y_signal_5c"] = compute_multiclass_labels(
            df, config, return_col, barrier_col
        )

    if "4class" in schemes:
        df["y_signal_4c"] = compute_actionable_labels(
            df, config, return_col, barrier_col
        )

    return df


def get_class_weights(
    labels: pd.Series,
    method: Literal["balanced", "sqrt_balanced", "custom"] = "balanced",
) -> dict[int, float]:
    """
    Compute class weights for imbalanced multi-class classification.

    Args:
        labels: Series of class labels
        method: Weighting method
            - 'balanced': Inverse frequency (sklearn default)
            - 'sqrt_balanced': Square root of inverse frequency (smoother)
            - 'custom': Custom weights (not implemented)

    Returns:
        Dictionary mapping class label to weight
    """
    value_counts = labels.value_counts()
    n_samples = len(labels)
    n_classes = len(value_counts)

    if method == "balanced":
        # weight = n_samples / (n_classes * n_class)
        weights = {
            cls: n_samples / (n_classes * count) for cls, count in value_counts.items()
        }
    elif method == "sqrt_balanced":
        # Smoother weighting - less extreme for rare classes
        weights = {
            cls: np.sqrt(n_samples / (n_classes * count))
            for cls, count in value_counts.items()
        }
    else:
        raise ValueError(f"Unknown method: {method}")

    return weights


def analyze_label_distribution(
    labels: pd.Series,
    label_names: dict[int, str] | None = None,
) -> pd.DataFrame:
    """
    Analyze the distribution of signal labels.

    Args:
        labels: Series of class labels
        label_names: Optional mapping from label to name

    Returns:
        DataFrame with distribution statistics
    """
    counts = labels.value_counts().sort_index()

    if label_names is None:
        label_names = {i: f"Class {i}" for i in counts.index}

    result = pd.DataFrame(
        {
            "label": counts.index,
            "name": [label_names.get(i, f"Unknown {i}") for i in counts.index],
            "count": counts.values,
            "percentage": (counts.values / len(labels) * 100).round(1),
        }
    )

    return result


# Label name mappings for display
LABEL_NAMES_3C = {
    0: "DOWN",
    1: "UP",
    2: "NEUTRAL",
}

LABEL_NAMES_5C = {
    0: "STRONG_SHORT",
    1: "WEAK_SHORT",
    2: "NO_SIGNAL",
    3: "WEAK_LONG",
    4: "STRONG_LONG",
}

LABEL_NAMES_4C = {
    0: "STRONG_SHORT",
    1: "WEAK_SHORT",
    2: "WEAK_LONG",
    3: "STRONG_LONG",
}

# Target type to labeling strategy mapping
TARGET_LABELING_STRATEGY = {
    # Direction targets: Use triple-barrier based 3-class
    "direction": "tristate_tb",
    # Returns targets: DEPRECATED - kept for backwards compatibility
    # (returns ≈ sign(direction) × volatility, so redundant)
    "returns": "regression",
    # Volatility targets: Regression - use continuous target directly
    "volatility": "regression",
    # Volatility regime: Binary (0=DECREASE, 1=INCREASE) - will vol increase or decrease?
    "volatility_regime": "existing_binary",
    # Trend regime: Binary (0=down, 1=up) - use existing
    "trend_regime": "existing_binary",
    # First extreme: Binary (0=low first, 1=high first) - 15m analysis
    "first_extreme": "existing_binary",
    # Vol to extreme: Regression (magnitude) - 15m analysis
    "vol_to_extreme": "regression",
}


def get_target_type_from_config(config_name: str) -> str:
    """
    Extract target type from config name.

    Args:
        config_name: e.g., 'direction_1bar', 'volatility_regime_3bar'

    Returns:
        Target type: 'direction', 'returns', 'volatility', 'volatility_regime', 'trend_regime'
    """
    # Handle underscore-separated names
    parts = config_name.rsplit("_", 1)  # Split from right to handle 'vol_regime_1bar'
    if len(parts) == 2 and parts[1].endswith("bar"):
        base = parts[0]
    else:
        base = config_name

    # Match known target types - check exact match first to avoid
    # 'volatility_regime' matching 'volatility' via startswith
    if base in TARGET_LABELING_STRATEGY:
        return base

    # Fallback: check startswith for backward compatibility
    for target_type in TARGET_LABELING_STRATEGY:
        if base.startswith(target_type):
            return target_type

    raise ValueError(f"Unknown config name: {config_name}")


def get_optimal_target_for_config(
    df: pd.DataFrame,
    config_name: str,
    horizon: int | None = None,
) -> tuple[str, pd.Series]:
    """
    Get the optimal target column and labels for a given config.

    IMPORTANT: This function uses the centralized targets module
    (scripts.workflow.targets) as the single source of truth.

    The target column naming is:
    - direction: y_direction_3c (3-class)
    - volatility: y_volatility (regression)
    - volatility_regime: y_volatility_regime (binary: DECREASE/INCREASE)
    - trend_regime: y_trend_regime (binary)

    Args:
        df: DataFrame with all target columns
        config_name: Config name like 'direction_1bar'
        horizon: Optional horizon (extracted from config_name if not provided)

    Returns:
        Tuple of (target_column_name, target_series)
    """
    # Use centralized target configuration
    target_config = get_config_target(config_name)
    target_col = target_config.target_column

    # Extract horizon if not provided
    if horizon is None:
        horizon = get_config_horizon(config_name)

    # Check if target column already exists in DataFrame
    if target_col in df.columns:
        return target_col, df[target_col]

    # For backward compatibility: check legacy column names
    legacy_mappings = {
        "y_direction_3c": ["y_signal_3c", "y_direction"],
        "y_volatility": ["y_volatility", f"y_forward_return_{horizon}"],
        "y_volatility_regime": ["y_volatility_regime"],
        "y_trend_regime": ["y_trend_regime"],
    }

    for legacy_col in legacy_mappings.get(target_col, []):
        if legacy_col in df.columns:
            return legacy_col, df[legacy_col]

    # If not found, compute the target
    # Need OHLC data - check if available
    close_col = "RAW_P_close_abs_NN" if "RAW_P_close_abs_NN" in df.columns else "close"
    high_col = "RAW_P_high_abs_NN" if "RAW_P_high_abs_NN" in df.columns else "high"
    low_col = "RAW_P_low_abs_NN" if "RAW_P_low_abs_NN" in df.columns else "low"

    if close_col not in df.columns:
        raise ValueError(
            f"Target column {target_col} not found in DataFrame and "
            "cannot compute - no price data available. "
            f"Available columns: {df.columns.tolist()[:20]}..."
        )

    target_series = compute_target_pandas(
        target_name=target_config.name,
        close=df[close_col],
        high=df[high_col] if high_col in df.columns else df[close_col],
        low=df[low_col] if low_col in df.columns else df[close_col],
        horizon=horizon,
    )

    return target_col, target_series


def add_all_signal_labels(
    df: pd.DataFrame,
    config: LabelingConfig | None = None,
) -> pd.DataFrame:
    """
    Add all signal label columns needed for the 20 target configurations.

    This adds:
    - y_signal_3c: 3-class tristate for direction targets
    - y_signal_5c: 5-class with strength gradation
    - y_signal_4c: 4-class actionable (no neutral)

    Note: vol_regime and trend_regime don't need additional labels
    as they already have proper multi-class/binary labels.

    Args:
        df: Input DataFrame with y_tb_return, y_tb_barrier columns
        config: Labeling configuration

    Returns:
        DataFrame with signal label columns added
    """
    if config is None:
        config = LabelingConfig(threshold_sigma=0.5)

    df = df.copy()

    # Only add if triple barrier columns exist
    if "y_tb_return" in df.columns and "y_tb_barrier" in df.columns:
        df["y_signal_3c"] = compute_tristate_labels(
            df, config, return_col="y_tb_return", barrier_col="y_tb_barrier"
        )
        df["y_signal_5c"] = compute_multiclass_labels(
            df, config, return_col="y_tb_return", barrier_col="y_tb_barrier"
        )
        df["y_signal_4c"] = compute_actionable_labels(
            df, config, return_col="y_tb_return", barrier_col="y_tb_barrier"
        )

    return df


def get_config_task_type(config_name: str) -> Literal["classification", "regression"]:
    """
    Determine if a config is classification or regression task.

    Uses centralized targets module as source of truth.

    Args:
        config_name: e.g., 'direction_1bar', 'volatility_3bar'

    Returns:
        'classification' or 'regression'
    """
    target_config = get_config_target(config_name)
    return target_config.task_type


def get_config_n_classes(config_name: str) -> int | None:
    """
    Get number of classes for a classification config.

    Uses centralized targets module as source of truth.

    Args:
        config_name: e.g., 'direction_1bar', 'vol_regime_3bar'

    Returns:
        Number of classes (2, 3, etc.) or None for regression
    """
    target_config = get_config_target(config_name)
    return target_config.n_classes


if __name__ == "__main__":
    # Demo/test usage
    import pandas as pd

    # Load analysis data
    df = pd.read_parquet("data/analysis_8h.parquet")

    print("=== Signal Labeling Analysis ===\n")

    # Check required columns
    print(f"Return column 'y_tb_return' present: {'y_tb_return' in df.columns}")
    print(f"Barrier column 'y_tb_barrier' present: {'y_tb_barrier' in df.columns}")
    print()

    # Apply labeling
    config = LabelingConfig(threshold_sigma=0.5)
    df = add_signal_labels_to_df(df, config)

    # Show distributions
    print("=== 3-Class Distribution ===")
    dist_3c = analyze_label_distribution(df["y_signal_3c"], LABEL_NAMES_3C)
    print(dist_3c.to_string(index=False))
    print()

    print("=== 5-Class Distribution ===")
    dist_5c = analyze_label_distribution(df["y_signal_5c"], LABEL_NAMES_5C)
    print(dist_5c.to_string(index=False))
    print()

    print("=== 4-Class Distribution ===")
    dist_4c = analyze_label_distribution(df["y_signal_4c"], LABEL_NAMES_4C)
    print(dist_4c.to_string(index=False))
    print()

    # Show class weights
    print("=== Balanced Class Weights (3-class) ===")
    weights = get_class_weights(df["y_signal_3c"], method="balanced")
    for cls, weight in sorted(weights.items()):
        print(f"  {LABEL_NAMES_3C[cls]}: {weight:.3f}")

"""
Data Loader Adapter Module

Contains data loading and preprocessing functions:
- ConfigData: Preloaded data container for a single config
- parse_config: Parse config name to get target specification
- get_embargo_for_horizon: Compute embargo bars based on horizon
- clip_features: Clip extreme feature values
- load_timestamps_for_config: Load timestamp array for a config
- load_config_data: Load and prepare data for a single config

Dependencies:
- scripts.analysis.signal_labels (target type functions)
- scripts.target_models.validation.combined_datasets (data loading)
- numpy, pandas, polars
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd
import polars as pl

from scripts.analysis.signal_labels import (
    get_config_n_classes,
    get_config_task_type,
    get_optimal_target_for_config,
)
from scripts.target_models.validation.combined_datasets import (
    load_combined_dataset,
    load_combined_dataset_aligned,
)

# Type-only import to avoid circular dependency
if TYPE_CHECKING:
    pass


@dataclass
class ConfigData:
    """Preloaded data for a single config."""

    config_name: str
    task_type: str  # regression | classification
    target_name: str
    horizon: int
    n_classes: int | None

    X_features: pd.DataFrame  # L1 features (aligned, clipped)
    y_target: pd.Series  # Aligned targets
    pred_idx: np.ndarray  # Original pred_idx for reference
    timestamps: np.ndarray | None  # Timestamps for each pred_idx (for reporting)

    # Per-step results storage
    predictions: list[dict] = field(default_factory=list)


def parse_config(config_name: str) -> dict[str, Any]:
    """Parse config name to get target specification.

    Uses signal_labels.py for correct n_classes:
    - direction: 3 (DOWN/UP/NEUTRAL tristate from triple barrier)
    - vol_regime: 3 (LOW/MED/HIGH)
    - trend_regime: 2 (binary)
    - volatility: None (regression)

    Args:
        config_name: Configuration name (e.g., 'direction_1bar')

    Returns:
        Dict with target, horizon, task_type, n_classes
    """
    parts = config_name.rsplit("_", 1)
    target_name = parts[0]
    horizon = int(parts[1].replace("bar", ""))

    # Use signal_labels for consistent task type and n_classes
    task_type = get_config_task_type(config_name)
    n_classes = get_config_n_classes(config_name)

    return {
        "target": target_name,
        "horizon": horizon,
        "task_type": task_type,
        "n_classes": n_classes,
    }


def get_embargo_for_horizon(horizon: int, base_embargo: int = 3) -> int:
    """Compute embargo bars based on target horizon.

    Longer horizons need more embargo because target labels use data
    further into the future.

    Formula: embargo = base_embargo * horizon, capped at 36

    Args:
        horizon: Target horizon in bars (1, 3, 6, 12)
        base_embargo: Base embargo multiplier (default 3)

    Returns:
        Number of embargo bars to use

    Examples:
        1bar: 3 * 1 = 3 bars
        3bar: 3 * 3 = 9 bars
        6bar: 3 * 6 = 18 bars
        12bar: 3 * 12 = 36 bars (capped)
    """
    embargo = base_embargo * horizon
    return min(embargo, 36)  # Cap at 36 (reasonable maximum)


def clip_features(df: pd.DataFrame, duration_max: float = 1000.0) -> pd.DataFrame:
    """Clip extreme feature values.

    Args:
        df: Feature DataFrame
        duration_max: Maximum value for duration columns

    Returns:
        DataFrame with clipped features
    """
    df = df.copy()
    duration_cols = [c for c in df.columns if "duration" in c.lower()]
    for col in duration_cols:
        if col in df.columns:
            df[col] = df[col].clip(upper=duration_max)
    return df


# Cache for timestamp mapping (loaded once per config)
_TIMESTAMP_CACHE: dict[str, np.ndarray] = {}


def load_timestamps_for_config(
    config_name: str,
    datasets_dir: Path | str = "data/datasets",
) -> np.ndarray:
    """Load timestamp array for a config from raw dataset.

    Timestamps are loaded once and cached for reuse.
    Uses polars for efficient column-only loading.

    Args:
        config_name: Configuration name (e.g., 'direction_1bar')
        datasets_dir: Directory containing raw datasets

    Returns:
        Array of timestamps (dtype=datetime64[ms] or int64 epoch ms)
    """
    if config_name in _TIMESTAMP_CACHE:
        return _TIMESTAMP_CACHE[config_name]

    datasets_dir = Path(datasets_dir)
    raw_path = datasets_dir / f"{config_name}.parquet"

    if not raw_path.exists():
        # Return empty array if no raw dataset
        return np.array([], dtype="datetime64[ms]")

    # Load only the timestamp column for efficiency
    timestamps = pl.read_parquet(raw_path, columns=["timestamp"])[
        "timestamp"
    ].to_numpy()

    _TIMESTAMP_CACHE[config_name] = timestamps
    return timestamps


def load_config_data(
    config_name: str,
    config: Any,  # SyncBacktestConfig - use Any to avoid circular import
    common_range: dict | None = None,
) -> ConfigData:
    """Load and prepare data for a single config.

    Uses combined_datasets which include:
    - Raw features (170 base features)
    - Helper features (91 L1 helper-derived features)
    - Interaction features (2-5 per config, target-optimized)
    - Target column (y_*)

    Each of 16 configs has its own combined dataset with target-specific
    interaction features and the correct target column.

    Args:
        config_name: Configuration name (e.g., 'direction_1bar')
        config: Backtest configuration (SyncBacktestConfig)
        common_range: Result from compute_common_pred_idx_range(). If provided, loads
                     aligned dataset (all configs same length/pred_idx). If None, loads
                     full dataset (legacy behavior).

    Returns:
        ConfigData with loaded and preprocessed data
    """
    spec = parse_config(config_name)

    # Load combined dataset (raw + helper + interactions + target)
    # Use aligned loading if common_range provided (synchronized backtest)
    if common_range is not None:
        combined_df = load_combined_dataset_aligned(
            config_name, common_range=common_range
        )
    else:
        combined_df = load_combined_dataset(config_name)

    pred_idx = combined_df["pred_idx"].values

    # Get optimal target column using signal_labels logic:
    # - direction_*: uses y_signal_3c (3-class tristate from triple barrier)
    # - vol_regime_*: uses y_vol_regime (existing 3-class)
    # - trend_regime_*: uses y_trend_regime (existing binary)
    # - volatility_*: uses continuous regression targets
    target_col, target_series = get_optimal_target_for_config(combined_df, config_name)

    # Extract features (everything except pred_idx and target columns)
    feature_cols = [
        c for c in combined_df.columns if c != "pred_idx" and not c.startswith("y_")
    ]
    X_features = combined_df[feature_cols].copy()

    # Use the target series from get_optimal_target_for_config
    y_aligned = target_series.copy()

    # Clip extreme features
    X_features = clip_features(X_features, config.duration_max)

    # Fill NaN in features with forward fill then backward fill
    # (handles edge cases like MFI, RSI that may have NaN at boundaries)
    if X_features.isna().any().any():
        X_features = X_features.ffill().bfill()
        # If still NaN (entire column missing), fill with 0
        X_features = X_features.fillna(0.0)

    # Filter out NaN in target (should be minimal after alignment)
    valid_mask = y_aligned.notna().values
    X_valid = X_features.iloc[valid_mask].reset_index(drop=True)
    y_valid = y_aligned[valid_mask].reset_index(drop=True)
    pred_idx_valid = pred_idx[valid_mask]

    # Load timestamps from raw dataset for datetime mapping
    # pred_idx values are indices into the raw dataset
    all_timestamps = load_timestamps_for_config(config_name)
    if len(all_timestamps) > 0 and len(pred_idx_valid) > 0:
        # Map pred_idx to timestamps
        timestamps_valid = all_timestamps[pred_idx_valid]
    else:
        timestamps_valid = None

    return ConfigData(
        config_name=config_name,
        task_type=spec["task_type"],
        target_name=spec["target"],
        horizon=spec["horizon"],
        n_classes=spec["n_classes"],
        X_features=X_valid,
        y_target=y_valid,
        pred_idx=pred_idx_valid,
        timestamps=timestamps_valid,
        predictions=[],
    )


# Exports
__all__ = [
    "ConfigData",
    "parse_config",
    "get_embargo_for_horizon",
    "clip_features",
    "load_timestamps_for_config",
    "load_config_data",
]

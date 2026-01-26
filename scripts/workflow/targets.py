"""
Centralized Target Configuration for RiskYieldMM Workflow.

SINGLE SOURCE OF TRUTH for all target definitions used across:
- Step 3: Feature optimization (parallel_optimize.py)
- Step 4: Dataset building (run.py cmd_build_datasets)
- Step 8: L1 precompute (l1_precompute.py)
- Step 9: Dataset assembly (dataset_assembly.py)
- Step 10: L2 backtest (l2_backtest_sync.py)

================================================================================
HOW TO ADD A NEW TARGET:
================================================================================

1. Create a Label enum (if classification):
   ```python
   class MyNewLabel(IntEnum):
       CLASS_A = 0
       CLASS_B = 1
   ```

2. Register the target using the @register_target decorator:
   ```python
   @register_target(
       name="my_new_target",
       task_type="classification",
       n_classes=2,
       target_column="y_my_new_target",
       description="My new target description",
   )
   def compute_my_new_target(
       close: pd.Series,
       high: pd.Series,
       low: pd.Series,
       horizon: int,
       **kwargs,
   ) -> pd.Series:
       # Your computation logic here
       return labels
   ```

That's it! The target is now available everywhere in the workflow.

================================================================================
HOW TO MODIFY AN EXISTING TARGET:
================================================================================

Just edit the compute function - all modules automatically use the new logic.

================================================================================
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import IntEnum
from typing import TYPE_CHECKING, Any, Literal

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    import polars as pl

# =============================================================================
# TARGET ENUMS (Label Values)
# =============================================================================


class DirectionLabel(IntEnum):
    """3-class direction labels (tristate from triple barrier)."""

    DOWN = 0  # Clear short signal (SL hit or strong negative)
    UP = 1  # Clear long signal (TP hit or strong positive)
    NEUTRAL = 2  # No clear signal (TIME barrier, weak move)


class VolatilityRegimeLabel(IntEnum):
    """Binary volatility regime labels (will vol increase or decrease?)."""

    DECREASE = 0  # Future volatility will be lower than current
    INCREASE = 1  # Future volatility will be higher than current


class TrendRegimeLabel(IntEnum):
    """Binary trend regime labels."""

    DOWN = 0  # Fast SMA below slow SMA
    UP = 1  # Fast SMA above slow SMA


# =============================================================================
# TARGET REGISTRY SYSTEM
# =============================================================================

# Type alias for compute functions
ComputeFunc = Callable[..., pd.Series]


@dataclass
class TargetConfig:
    """Configuration for a target type."""

    name: str  # e.g., "direction", "volatility"
    task_type: Literal["classification", "regression"]
    n_classes: int | None  # None for regression
    target_column: str  # Column name in datasets
    description: str
    compute_func: ComputeFunc | None = field(default=None, repr=False)
    label_enum: type[IntEnum] | None = field(default=None, repr=False)

    @property
    def is_classification(self) -> bool:
        return self.task_type == "classification"

    @property
    def is_regression(self) -> bool:
        return self.task_type == "regression"

    @property
    def is_multiclass(self) -> bool:
        return (
            self.is_classification and self.n_classes is not None and self.n_classes > 2
        )


# Global registry
_TARGET_REGISTRY: dict[str, TargetConfig] = {}


def register_target(
    name: str,
    task_type: Literal["classification", "regression"],
    n_classes: int | None,
    target_column: str,
    description: str,
    label_enum: type[IntEnum] | None = None,
) -> Callable[[ComputeFunc], ComputeFunc]:
    """
    Decorator to register a new target type.

    Example:
        @register_target(
            name="direction",
            task_type="classification",
            n_classes=3,
            target_column="y_direction_3c",
            description="3-class direction from triple barrier",
            label_enum=DirectionLabel,
        )
        def compute_direction(close, high, low, horizon, **kwargs):
            ...
    """

    def decorator(func: ComputeFunc) -> ComputeFunc:
        config = TargetConfig(
            name=name,
            task_type=task_type,
            n_classes=n_classes,
            target_column=target_column,
            description=description,
            compute_func=func,
            label_enum=label_enum,
        )
        _TARGET_REGISTRY[name] = config
        return func

    return decorator


# =============================================================================
# REGISTERED TARGETS - Add new targets here using @register_target
# =============================================================================


@register_target(
    name="direction",
    task_type="classification",
    n_classes=3,
    target_column="y_direction_3c",
    description="3-class direction from triple barrier (DOWN/UP/NEUTRAL)",
    label_enum=DirectionLabel,
)
def compute_direction(
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    horizon: int,
    tb_barrier: pd.Series | None = None,
    tb_return: pd.Series | None = None,
    **kwargs: Any,
) -> pd.Series:
    """
    Compute 3-class direction target.

    Uses triple-barrier information if available, otherwise falls back
    to return magnitude thresholds.

    Labels:
        0 (DOWN): Clear short signal (SL hit or strong negative)
        1 (UP): Clear long signal (TP hit or strong positive)
        2 (NEUTRAL): No clear signal (TIME barrier, weak move)
    """
    # Compute net candle return
    future_high = high.shift(-horizon)
    future_low = low.shift(-horizon)
    up_move = (future_high - close) / close
    down_move = (close - future_low) / close
    net_candle_ret = up_move - down_move

    # Initialize as NEUTRAL
    labels = pd.Series(DirectionLabel.NEUTRAL, index=close.index, dtype=np.int8)

    if tb_barrier is not None and tb_return is not None:
        # Use triple-barrier information (most accurate)
        labels[tb_barrier == "TP"] = DirectionLabel.UP
        labels[tb_barrier == "SL"] = DirectionLabel.DOWN

        # TIME barrier: only classify if move is significant
        rolling_vol = net_candle_ret.rolling(21, min_periods=10).std()
        threshold = 0.5 * rolling_vol.clip(lower=0.005, upper=0.05)
        threshold = threshold.bfill()

        time_mask = tb_barrier == "TIME"
        labels.loc[time_mask & (tb_return > threshold)] = DirectionLabel.UP
        labels.loc[time_mask & (tb_return < -threshold)] = DirectionLabel.DOWN
    else:
        # Fallback: use return magnitude thresholds
        rolling_vol = net_candle_ret.rolling(21, min_periods=10).std()
        threshold = 0.5 * rolling_vol.clip(lower=0.005, upper=0.05)
        threshold = threshold.bfill()

        labels[net_candle_ret > threshold] = DirectionLabel.UP
        labels[net_candle_ret < -threshold] = DirectionLabel.DOWN

    # Set NaN for rows where we can't compute (last horizon rows due to shift)
    # Convert to float to allow NaN values
    labels = labels.astype(float)
    labels[net_candle_ret.isna()] = np.nan

    return labels


@register_target(
    name="volatility",
    task_type="regression",
    n_classes=None,
    target_column="y_volatility",
    description="Absolute forward return (continuous regression target)",
    label_enum=None,
)
def compute_volatility(
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    horizon: int,
    **kwargs: Any,
) -> pd.Series:
    """
    Compute volatility target (absolute forward return).

    This is a regression target - predicts magnitude of price movement.
    """
    fwd_ret = (close.shift(-horizon) - close) / close
    return fwd_ret.abs()


@register_target(
    name="volatility_regime",
    task_type="classification",
    n_classes=2,
    target_column="y_volatility_regime",
    description="Binary: will price volatility INCREASE or DECREASE vs current?",
    label_enum=VolatilityRegimeLabel,
)
def compute_volatility_regime(
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    horizon: int,
    vol_window: int = 21,
    **kwargs: Any,
) -> pd.Series:
    """
    Compute volatility regime target (binary change direction).

    Predicts whether future volatility will be HIGHER or LOWER than current.
    Guaranteed ~50/50 class balance due to mean-reversion of volatility.

    Formula: INCREASE if future_vol > current_vol, else DECREASE

    Labels:
        0 (DECREASE): Future volatility will be lower than current
        1 (INCREASE): Future volatility will be higher than current

    Note: "Volatility" here means price volatility (std of log returns),
    NOT trading volume.
    """
    log_returns = np.log(close / close.shift(1))
    rolling_vol = log_returns.rolling(vol_window).std()

    # Future volatility (shifted back to align with current timestamp)
    future_vol = rolling_vol.shift(-horizon)

    # Simple comparison: will vol increase or decrease?
    labels = (future_vol > rolling_vol).astype(float)

    # Preserve NaN for rows where we can't compute
    labels[rolling_vol.isna() | future_vol.isna()] = np.nan

    return labels


@register_target(
    name="trend_regime",
    task_type="classification",
    n_classes=2,
    target_column="y_trend_regime",
    description="Binary trend regime from SMA crossover",
    label_enum=TrendRegimeLabel,
)
def compute_trend_regime(
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    horizon: int,
    **kwargs: Any,
) -> pd.Series:
    """
    Compute trend regime target (binary SMA crossover).

    Labels:
        0 (DOWN): Fast SMA below slow SMA (downtrend)
        1 (UP): Fast SMA above slow SMA (uptrend)
    """
    fast_window = max(21, horizon * 5)
    slow_window = max(63, horizon * 15)
    sma_fast = close.rolling(fast_window).mean()
    sma_slow = close.rolling(slow_window).mean()
    # Keep as float to preserve NaN values from rolling warmup
    result = (sma_fast > sma_slow).astype(float)
    # NaN propagates automatically from sma_slow (longer window)
    return result


# =============================================================================
# ADD NEW TARGETS BELOW (just copy the pattern above)
# =============================================================================


class FirstExtremeLabel(IntEnum):
    """Binary first-extreme labels from 15m intrabar analysis."""

    LOW_FIRST = 0  # 8h low was touched before 8h high
    HIGH_FIRST = 1  # 8h high was touched before 8h low


def _load_15m_data_for_8h(
    timestamps_8h: pd.DatetimeIndex,
    data_dir: str = "fetchingByBit/sorted-15m-bybit-linear",
) -> pd.DataFrame:
    """
    Load 15m OHLCV data and align to 8h periods.

    For each 8h timestamp, loads the 32 subsequent 15m bars
    to analyze intrabar price action.

    Returns DataFrame with columns:
        - timestamp_8h: The 8h bar timestamp
        - bars_15m: List of 32 15m OHLCV dicts for that period
        - high_8h: Max high across 32 bars
        - low_8h: Min low across 32 bars
        - first_extreme: 'high' or 'low' (which was hit first)
        - time_to_first: Bars until first extreme (0-31)
        - vol_to_first: |price move| to first extreme
    """
    from pathlib import Path

    import polars as pl

    data_path = Path(data_dir)
    if not data_path.exists():
        raise FileNotFoundError(f"15m data directory not found: {data_path}")

    # Load all 15m data
    files = sorted(data_path.glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"No parquet files in {data_path}")

    df_15m = pl.concat([pl.read_parquet(f) for f in files])
    df_15m = df_15m.sort("timestamp")

    # Convert to pandas for easier manipulation
    df_15m_pd = df_15m.to_pandas()
    df_15m_pd["timestamp"] = pd.to_datetime(df_15m_pd["timestamp"], utc=True)
    df_15m_pd = df_15m_pd.set_index("timestamp")

    # Ensure timestamps_8h is UTC timezone-aware for comparison
    # (15m data is loaded with UTC, must match)
    if timestamps_8h.tz is None:
        timestamps_8h = timestamps_8h.tz_localize("UTC")
    elif str(timestamps_8h.tz) != "UTC":
        timestamps_8h = timestamps_8h.tz_convert("UTC")

    results = []
    for ts_8h in timestamps_8h:
        # Get 32 15m bars starting from this 8h timestamp
        ts_end = ts_8h + pd.Timedelta(hours=8)
        mask = (df_15m_pd.index >= ts_8h) & (df_15m_pd.index < ts_end)
        bars = df_15m_pd.loc[mask]

        if len(bars) < 16:  # Need at least half the bars
            results.append(
                {
                    "timestamp_8h": ts_8h,
                    "first_extreme": np.nan,
                    "time_to_first": np.nan,
                    "vol_to_first": np.nan,
                }
            )
            continue

        # Find 8h high and low
        high_8h = bars["high"].max()
        low_8h = bars["low"].min()
        open_8h = bars["open"].iloc[0]

        # Scan through bars to find which extreme was hit first
        first_extreme = None
        time_to_first = np.nan
        vol_to_first = np.nan

        for i, (_, bar) in enumerate(bars.iterrows()):
            if bar["high"] >= high_8h * 0.9999:  # Allow tiny tolerance
                first_extreme = "high"
                time_to_first = i
                vol_to_first = abs(high_8h - open_8h) / open_8h
                break
            elif bar["low"] <= low_8h * 1.0001:  # Allow tiny tolerance
                first_extreme = "low"
                time_to_first = i
                vol_to_first = abs(open_8h - low_8h) / open_8h
                break

        results.append(
            {
                "timestamp_8h": ts_8h,
                "first_extreme": 1
                if first_extreme == "high"
                else 0
                if first_extreme == "low"
                else np.nan,
                "time_to_first": time_to_first,
                "vol_to_first": vol_to_first,
            }
        )

    return pd.DataFrame(results).set_index("timestamp_8h")


# Cache for 15m analysis results (expensive to compute)
_15M_ANALYSIS_CACHE: dict[str, pd.DataFrame] = {}


def _get_15m_analysis(
    close: pd.Series,
    data_dir: str = "fetchingByBit/sorted-15m-bybit-linear",
) -> pd.DataFrame:
    """Get cached 15m analysis or compute if not available."""
    cache_key = f"{close.index[0]}_{close.index[-1]}_{len(close)}"

    if cache_key not in _15M_ANALYSIS_CACHE:
        timestamps = pd.DatetimeIndex(close.index)
        _15M_ANALYSIS_CACHE[cache_key] = _load_15m_data_for_8h(timestamps, data_dir)

    # Get analysis and ensure index matches close.index timezone
    analysis = _15M_ANALYSIS_CACHE[cache_key].copy()

    # Match index timezone to close.index for proper reindex
    close_tz = getattr(close.index, "tz", None)
    analysis_tz = getattr(analysis.index, "tz", None)

    if close_tz is None and analysis_tz is not None:
        # close is tz-naive, analysis is tz-aware: remove tz from analysis
        analysis.index = analysis.index.tz_localize(None)
    elif close_tz is not None and analysis_tz is None:
        # close is tz-aware, analysis is tz-naive: localize analysis
        analysis.index = analysis.index.tz_localize(close_tz)
    elif (
        close_tz is not None
        and analysis_tz is not None
        and str(close_tz) != str(analysis_tz)
    ):
        # Both have tz but different: convert analysis to close's tz
        analysis.index = analysis.index.tz_convert(close_tz)

    return analysis


@register_target(
    name="first_extreme",
    task_type="classification",
    n_classes=2,
    target_column="y_first_extreme",
    description="Binary: which 8h extreme was hit first (0=low, 1=high) from 15m analysis",
    label_enum=FirstExtremeLabel,
)
def compute_first_extreme(
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    horizon: int,
    **kwargs: Any,
) -> pd.Series:
    """
    Compute first-extreme target using 15m intrabar analysis.

    Scans 15m bars within each 8h period to determine whether
    the period's high or low was reached first.

    Labels:
        0 (LOW_FIRST): 8h low was touched before 8h high (bearish momentum)
        1 (HIGH_FIRST): 8h high was touched before 8h low (bullish momentum)

    The target is shifted by -horizon to predict the NEXT bar(s), consistent
    with how other targets like 'direction' work.
    """
    analysis = _get_15m_analysis(close)
    result = analysis["first_extreme"].reindex(close.index)
    # Shift by -horizon to make it a forward-looking target
    # At timestamp T, this gives the first_extreme of the bar at T+horizon
    result = result.shift(-horizon)
    return result


@register_target(
    name="time_to_extreme",
    task_type="regression",
    n_classes=None,
    target_column="y_time_to_extreme",
    description="Number of 15m bars until first extreme is hit (0-31)",
    label_enum=None,
)
def compute_time_to_extreme(
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    horizon: int,
    **kwargs: Any,
) -> pd.Series:
    """
    Compute time-to-first-extreme target.

    Returns the number of 15m bars (0-31) until the first
    8h extreme (high or low) is reached.

    Lower values = faster momentum, higher values = slower development.

    The target is shifted by -horizon to predict the NEXT bar(s).
    """
    analysis = _get_15m_analysis(close)
    result = analysis["time_to_first"].reindex(close.index)
    # Shift by -horizon to make it a forward-looking target
    result = result.shift(-horizon)
    return result


@register_target(
    name="vol_to_extreme",
    task_type="regression",
    n_classes=None,
    target_column="y_vol_to_extreme",
    description="Absolute return from open to first extreme hit",
    label_enum=None,
)
def compute_vol_to_extreme(
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    horizon: int,
    **kwargs: Any,
) -> pd.Series:
    """
    Compute volatility-to-first-extreme target.

    Returns |open - first_extreme| / open, measuring the
    magnitude of the move to whichever extreme was hit first.

    Useful for position sizing: larger moves = larger profit potential.

    The target is shifted by -horizon to predict the NEXT bar(s).
    """
    analysis = _get_15m_analysis(close)
    result = analysis["vol_to_first"].reindex(close.index)
    # Shift by -horizon to make it a forward-looking target
    result = result.shift(-horizon)
    return result


# =============================================================================
# PUBLIC API - These functions are used by other modules
# =============================================================================


# Alias for backward compatibility
TARGETS = _TARGET_REGISTRY


def get_target_config(target_name: str) -> TargetConfig:
    """Get target configuration by name."""
    if target_name not in _TARGET_REGISTRY:
        available = list(_TARGET_REGISTRY.keys())
        raise ValueError(f"Unknown target: {target_name}. Available: {available}")
    return _TARGET_REGISTRY[target_name]


def get_config_target(config_name: str) -> TargetConfig:
    """Get target config from a config name like 'direction_1bar'."""
    parts = config_name.rsplit("_", 1)
    if len(parts) == 2 and parts[1].endswith("bar"):
        target_name = parts[0]
    else:
        target_name = config_name
    return get_target_config(target_name)


def get_config_horizon(config_name: str) -> int:
    """Extract horizon from config name like 'direction_1bar' -> 1."""
    parts = config_name.rsplit("_", 1)
    if len(parts) == 2 and parts[1].endswith("bar"):
        return int(parts[1].replace("bar", ""))
    return 1  # Default


class TargetTaskType(IntEnum):
    """Task type enum for compatibility with other modules."""

    CLASSIFICATION = 1
    REGRESSION = 2


def get_config_task_type(config_name: str) -> TargetTaskType:
    """
    Get task type from config name like 'direction_1bar'.

    Returns TargetTaskType enum for compatibility with signal_labels.py
    and other modules.
    """
    config = get_config_target(config_name)
    if config.task_type == "classification":
        return TargetTaskType.CLASSIFICATION
    return TargetTaskType.REGRESSION


def get_config_n_classes(config_name: str) -> int | None:
    """
    Get number of classes from config name like 'direction_1bar'.

    Returns None for regression targets.
    """
    config = get_config_target(config_name)
    return config.n_classes


def compute_target_pandas(
    target_name: str,
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    horizon: int,
    **kwargs: Any,
) -> pd.Series:
    """
    Compute target series for any target type (pandas version).

    This is the SINGLE function to call for target computation.
    All target logic is centralized in registered compute functions.

    Args:
        target_name: One of the registered target names
        close: Close prices
        high: High prices
        low: Low prices
        horizon: Forward horizon in bars
        **kwargs: Additional arguments passed to compute function

    Returns:
        Target series with appropriate dtype
    """
    config = get_target_config(target_name)
    if config.compute_func is None:
        raise ValueError(f"Target {target_name} has no compute function registered")
    return config.compute_func(close, high, low, horizon, **kwargs)


def compute_target_polars(
    target_name: str,
    close: pl.Series,
    high: pl.Series,
    low: pl.Series,
    horizon: int,
    timestamp: pl.Series | None = None,
    **kwargs: Any,
) -> pl.Series:
    """
    Compute target series for any target type (polars version).

    Converts to pandas, computes, converts back. This ensures consistency
    with pandas implementation and simplifies maintenance.

    Args:
        target_name: Name of the target (e.g., 'direction', 'first_extreme')
        close: Close prices
        high: High prices
        low: Low prices
        horizon: Forecast horizon (1=next bar)
        timestamp: Optional timestamp series for 15m-based targets
        **kwargs: Additional arguments passed to compute function
    """
    import polars as pl

    # Convert to pandas
    close_pd = close.to_pandas()
    high_pd = high.to_pandas()
    low_pd = low.to_pandas()

    # For 15m-based targets, we need timestamps as the index
    # Otherwise the 15m analysis lookup fails
    if timestamp is not None:
        ts_pd = timestamp.to_pandas()
        close_pd.index = pd.DatetimeIndex(ts_pd)
        high_pd.index = pd.DatetimeIndex(ts_pd)
        low_pd.index = pd.DatetimeIndex(ts_pd)

    # Compute using pandas implementation
    result_pd = compute_target_pandas(
        target_name, close_pd, high_pd, low_pd, horizon, **kwargs
    )

    # Convert back to polars
    # For classification targets, keep as float to preserve NaN, then cast
    config = get_target_config(target_name)
    if config.is_classification:
        # Use Float64 to preserve NaN values (Int64 can't hold NaN in polars)
        return pl.Series(config.target_column, result_pd.values, dtype=pl.Float64)
    else:
        return pl.Series(config.target_column, result_pd.values)


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================


def get_all_target_names() -> list[str]:
    """Get list of all registered target names."""
    return list(_TARGET_REGISTRY.keys())


def get_classification_targets() -> list[str]:
    """Get list of classification target names."""
    return [name for name, cfg in _TARGET_REGISTRY.items() if cfg.is_classification]


def get_regression_targets() -> list[str]:
    """Get list of regression target names."""
    return [name for name, cfg in _TARGET_REGISTRY.items() if cfg.is_regression]


def print_target_summary() -> None:
    """Print summary of all registered target configurations."""
    print("=" * 70)
    print("TARGET CONFIGURATION SUMMARY")
    print("=" * 70)
    print(f"{'Target':<15} {'Type':<15} {'Classes':<10} {'Column':<20}")
    print("-" * 70)
    for name, cfg in _TARGET_REGISTRY.items():
        classes = str(cfg.n_classes) if cfg.n_classes else "N/A"
        print(f"{name:<15} {cfg.task_type:<15} {classes:<10} {cfg.target_column:<20}")
    print("=" * 70)


def validate_target_registry() -> dict[str, bool]:
    """
    Validate all registered targets.

    Returns dict of {target_name: is_valid}
    """
    results = {}
    for name, config in _TARGET_REGISTRY.items():
        is_valid = True
        issues = []

        if config.compute_func is None:
            is_valid = False
            issues.append("No compute function")

        if config.is_classification and config.n_classes is None:
            is_valid = False
            issues.append("Classification target missing n_classes")

        if config.is_classification and config.label_enum is None:
            issues.append("Warning: No label enum defined")

        results[name] = is_valid
        if issues:
            print(f"  {name}: {', '.join(issues)}")

    return results


# =============================================================================
# BACKWARD COMPATIBILITY
# =============================================================================


def get_optimal_target_for_config(
    df: pd.DataFrame,
    config_name: str,
    horizon: int | None = None,
) -> tuple[str, pd.Series]:
    """
    DEPRECATED: Use compute_target_pandas() instead.

    Kept for backward compatibility with existing code.
    Returns (target_column_name, target_series).
    """
    import warnings

    warnings.warn(
        "get_optimal_target_for_config is deprecated. "
        "Use compute_target_pandas() from scripts.workflow.targets instead.",
        DeprecationWarning,
        stacklevel=2,
    )

    config = get_config_target(config_name)
    if horizon is None:
        horizon = get_config_horizon(config_name)

    # Check if target column already exists
    if config.target_column in df.columns:
        return config.target_column, df[config.target_column]

    # Legacy column names for direction
    if config.name == "direction" and "y_signal_3c" in df.columns:
        return "y_signal_3c", df["y_signal_3c"]

    # Check other legacy columns
    for possible_col in [config.target_column, f"y_{config.name}"]:
        if possible_col in df.columns:
            return possible_col, df[possible_col]

    raise ValueError(
        f"Target column for {config.name} not found in DataFrame. "
        f"Expected: {config.target_column}"
    )


# =============================================================================
# MODULE INITIALIZATION
# =============================================================================

# Validate on import (development mode check)
if __name__ == "__main__":
    print("Validating target registry...")
    results = validate_target_registry()
    all_valid = all(results.values())
    print(f"\nAll targets valid: {all_valid}")
    print()
    print_target_summary()

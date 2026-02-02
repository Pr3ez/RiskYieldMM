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


class PathLabel7Class(IntEnum):
    """7-class path characterization labels using 15m intrabar analysis.

    Captures HOW price moved within the 8h candle, not just WHERE it ended.
    Based on Kaufman Efficiency Ratio + retracement analysis.

    Classes ordered by bullish → bearish for intuitive label values.

    NOTE: Consider using PathLabel5Class instead - STRONG_* classes are <1% each,
    too rare to predict reliably.
    """

    STRONG_BULLISH = 0  # Clean rally: UP + trending (ER>0.22) + big move (>1.5%)
    BULLISH = 1  # Normal up: UP + decent efficiency
    MEAN_REVERT_UP = 2  # Dip bought: UP + went DOWN first + retraced >50%
    SIDEWAYS = 3  # Range-bound: FLAT net movement
    MEAN_REVERT_DOWN = 4  # Rally sold: DOWN + went UP first + retraced >50%
    BEARISH = 5  # Normal down: DOWN + decent efficiency
    STRONG_BEARISH = 6  # Clean selloff: DOWN + trending (ER>0.22) + big move


class PathLabel5Class(IntEnum):
    """5-class path characterization labels (merged from 7-class).

    Merges rare STRONG_* classes into BULLISH/BEARISH for stable training.
    STRONG_BULLISH (<1%) → BULLISH, STRONG_BEARISH (<1%) → BEARISH.

    Classes ordered by bullish → bearish for intuitive label values.
    """

    BULLISH = 0  # UP direction (includes strong bullish)
    MEAN_REVERT_UP = 1  # Dip bought: UP + went DOWN first + retraced >65%
    SIDEWAYS = 2  # Range-bound: FLAT net movement (<0.1%)
    MEAN_REVERT_DOWN = 3  # Rally sold: DOWN + went UP first + retraced >65%
    BEARISH = 4  # DOWN direction (includes strong bearish)


class StrategyLabel(IntEnum):
    """5-class prescriptive strategy labels.

    Answers: "Should I trade, and how?"

    Unlike path_label which describes WHAT happened, strategy_label
    prescribes WHAT TO DO based on regime + direction + risk.

    The key insight: different regimes require different strategies.
    - Trending → trend-follow (ride momentum)
    - Mean-reverting → counter-trend (fade moves)
    - Sideways/uncertain → stay flat (preserve capital)
    """

    FLAT = 0  # Don't trade - sideways, uncertain, or high risk
    TREND_FOLLOW_LONG = 1  # Strong uptrend - ride momentum long
    TREND_FOLLOW_SHORT = 2  # Strong downtrend - ride momentum short
    MEAN_REVERT_LONG = 3  # Oversold + reverting - counter-trend long
    MEAN_REVERT_SHORT = 4  # Overbought + reverting - counter-trend short


class TripleBarrierLabel(IntEnum):
    """3-class triple barrier outcome labels.

    Answers: "What's my expected risk/reward?"

    Based on de Prado's triple barrier method:
    - Upper barrier (take-profit)
    - Lower barrier (stop-loss)
    - Vertical barrier (time limit)

    Encodes which barrier was hit first → direct risk/reward signal.
    """

    STOP_LOSS = 0  # Hit lower barrier first → losing trade
    TIME_EXIT = 1  # Neither barrier hit → uncertain outcome
    TAKE_PROFIT = 2  # Hit upper barrier first → winning trade


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

    Predicts what the trend regime will be at time T+horizon.

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
    # Shift by -horizon to predict FUTURE trend regime
    result = result.shift(-horizon)
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
        - efficiency_ratio: Kaufman ER = |net move| / sum(|bar moves|)
        - retracement: Max retracement from first extreme (0-1)
        - high_time_idx: Bar index when high was hit (0-31)
        - low_time_idx: Bar index when low was hit (0-31)
        - net_return: (close - open) / open for the 8h period
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
                    "efficiency_ratio": np.nan,
                    "retracement": np.nan,
                    "high_time_idx": np.nan,
                    "low_time_idx": np.nan,
                    "net_return": np.nan,
                }
            )
            continue

        # Find 8h high and low
        high_8h = bars["high"].max()
        low_8h = bars["low"].min()
        open_8h = bars["open"].iloc[0]
        close_8h = bars["close"].iloc[-1]

        # Find which bar index hit the high and low
        high_time_idx = bars["high"].idxmax()
        low_time_idx = bars["low"].idxmin()
        # Convert to integer position (0-31)
        high_time_idx = bars.index.get_loc(high_time_idx)
        low_time_idx = bars.index.get_loc(low_time_idx)

        # Net return for the 8h period
        net_return = (close_8h - open_8h) / open_8h

        # Calculate Kaufman Efficiency Ratio
        # ER = |net price change| / sum of |individual bar changes|
        net_change = abs(close_8h - open_8h)
        sum_abs_changes = abs(bars["close"].diff().fillna(0)).sum()
        if sum_abs_changes > 0:
            efficiency_ratio = net_change / sum_abs_changes
        else:
            efficiency_ratio = 0.0

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

        # Calculate retracement from first extreme
        # Measures how much the price moved back toward the opposite extreme
        # Relative to the candle's total range (high - low)
        # 0 = no retracement, 1 = full retracement to opposite extreme
        candle_range = high_8h - low_8h
        retracement = 0.0
        if candle_range > 0:
            if first_extreme == "high":
                # Went up first - measure how much it came back down
                # 0 = closed at high, 1 = closed at low
                retracement = (high_8h - close_8h) / candle_range
            elif first_extreme == "low":
                # Went down first - measure how much it came back up
                # 0 = closed at low, 1 = closed at high
                retracement = (close_8h - low_8h) / candle_range

        # Clamp retracement to [0, 1] for edge cases
        retracement = max(0.0, min(1.0, retracement))

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
                "efficiency_ratio": efficiency_ratio,
                "retracement": retracement,
                "high_time_idx": high_time_idx,
                "low_time_idx": low_time_idx,
                "net_return": net_return,
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


@register_target(
    name="path_label_7",
    task_type="classification",
    n_classes=7,
    target_column="y_path_label_7",
    description="7-class path characterization using 15m intrabar analysis",
    label_enum=PathLabel7Class,
)
def compute_path_label_7(
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    horizon: int,
    **kwargs: Any,
) -> pd.Series:
    """
    Compute 7-class path characterization target using 15m intrabar analysis.

    Labels how price moved within the 8h candle, not just where it ended.
    Uses Kaufman Efficiency Ratio + retracement analysis to distinguish:

    - STRONG_BULLISH (0): Clean rally - UP + trending (ER>0.224) + big move (>1.52%)
    - BULLISH (1): Normal up - UP direction, not mean-reverting, not strong
    - MEAN_REVERT_UP (2): Dip bought - UP but went DOWN first + retraced >50%
    - SIDEWAYS (3): Range-bound - FLAT net movement (|return| < 0.1%)
    - MEAN_REVERT_DOWN (4): Rally sold - DOWN but went UP first + retraced >50%
    - BEARISH (5): Normal down - DOWN direction, not mean-reverting, not strong
    - STRONG_BEARISH (6): Clean selloff - DOWN + trending (ER>0.224) + big move

    Thresholds derived from empirical analysis of 5,546 8h periods:
    - FLAT_THRESHOLD = 0.001 (0.1% - defines SIDEWAYS)
    - ER_HIGH = 0.224 (70th percentile of efficiency ratios)
    - RETURN_75 = 0.0152 (75th percentile of |net returns| - for STRONG class)
    - RETRACEMENT_THRESHOLD = 0.5 (50% retracement = mean-reverting)

    The target is shifted by -horizon to predict the NEXT bar(s).
    """
    # Thresholds from empirical analysis
    FLAT_THRESHOLD = 0.001  # 0.1% - defines SIDEWAYS (~9% of samples)
    ER_HIGH = 0.224  # 70th percentile ER
    RETURN_75 = 0.0152  # 75th percentile |net return| (1.52%) - for STRONG
    RETRACEMENT_THRESHOLD = 0.65  # Calibrated to match ~55% mean-reverting

    analysis = _get_15m_analysis(close)
    analysis = analysis.reindex(close.index)

    # Extract needed columns
    net_return = analysis["net_return"]
    efficiency_ratio = analysis["efficiency_ratio"]
    retracement = analysis["retracement"]
    high_time_idx = analysis["high_time_idx"]
    low_time_idx = analysis["low_time_idx"]

    # Initialize result with NaN
    result = pd.Series(np.nan, index=close.index, dtype=float)

    # Step 1: Determine direction using FLAT_THRESHOLD (0.1%)
    is_up = net_return > FLAT_THRESHOLD
    is_down = net_return < -FLAT_THRESHOLD
    is_flat = ~is_up & ~is_down  # SIDEWAYS: |net_return| <= 0.1%

    # Step 2: Determine if STRONG (trending + big move)
    is_trending = efficiency_ratio >= ER_HIGH
    is_big_move = net_return.abs() >= RETURN_75

    # Step 3: Determine if mean-reverting
    # Mean-revert UP: went DOWN first (low_time_idx < high_time_idx) + ended UP + retraced >50%
    is_mean_revert_up = (
        is_up & (low_time_idx < high_time_idx) & (retracement > RETRACEMENT_THRESHOLD)
    )
    # Mean-revert DOWN: went UP first (high_time_idx < low_time_idx) + ended DOWN + retraced >50%
    is_mean_revert_down = (
        is_down & (high_time_idx < low_time_idx) & (retracement > RETRACEMENT_THRESHOLD)
    )

    # Assign labels (order matters - MEAN_REVERT first, then STRONG, then catch-all)

    # SIDEWAYS (3): FLAT net movement (|return| < 0.1%)
    result[is_flat] = PathLabel7Class.SIDEWAYS

    # MEAN_REVERT_UP (2): UP + mean-reverting (went down first, came back up)
    result[is_mean_revert_up] = PathLabel7Class.MEAN_REVERT_UP

    # MEAN_REVERT_DOWN (4): DOWN + mean-reverting (went up first, came back down)
    result[is_mean_revert_down] = PathLabel7Class.MEAN_REVERT_DOWN

    # STRONG_BULLISH (0): Clean rally - UP + trending + big move + NOT mean-reverting
    strong_bullish_mask = is_up & is_trending & is_big_move & ~is_mean_revert_up
    result[strong_bullish_mask] = PathLabel7Class.STRONG_BULLISH

    # STRONG_BEARISH (6): Clean selloff - DOWN + trending + big move + NOT mean-reverting
    strong_bearish_mask = is_down & is_trending & is_big_move & ~is_mean_revert_down
    result[strong_bearish_mask] = PathLabel7Class.STRONG_BEARISH

    # BULLISH (1): UP but not strong, not mean-reverting (catch-all for remaining UP)
    bullish_mask = is_up & ~is_mean_revert_up & ~strong_bullish_mask
    result[bullish_mask] = PathLabel7Class.BULLISH

    # BEARISH (5): DOWN but not strong, not mean-reverting (catch-all for remaining DOWN)
    bearish_mask = is_down & ~is_mean_revert_down & ~strong_bearish_mask
    result[bearish_mask] = PathLabel7Class.BEARISH

    # Shift by -horizon to make it a forward-looking target
    result = result.shift(-horizon)
    return result


@register_target(
    name="path_label_5",
    task_type="classification",
    n_classes=5,
    target_column="y_path_label_5",
    description="5-class path characterization (merged STRONG_* into BULLISH/BEARISH)",
    label_enum=PathLabel5Class,
)
def compute_path_label_5(
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    horizon: int,
    **kwargs: Any,
) -> pd.Series:
    """
    Compute 5-class path characterization target.

    Simplified version of path_label_7 that merges rare STRONG_* classes:
    - BULLISH (0): All UP moves (was STRONG_BULLISH + BULLISH)
    - MEAN_REVERT_UP (1): Dip bought - UP but went DOWN first
    - SIDEWAYS (2): Range-bound - FLAT net movement (<0.1%)
    - MEAN_REVERT_DOWN (3): Rally sold - DOWN but went UP first
    - BEARISH (4): All DOWN moves (was BEARISH + STRONG_BEARISH)

    This gives more balanced classes (~18% bullish, 28% mean-revert up,
    9% sideways, 25% mean-revert down, 20% bearish) for stable training.
    """
    # Thresholds from empirical analysis
    FLAT_THRESHOLD = 0.001  # 0.1% - defines SIDEWAYS
    RETRACEMENT_THRESHOLD = 0.65  # Calibrated to match ~55% mean-reverting

    analysis = _get_15m_analysis(close)
    analysis = analysis.reindex(close.index)

    # Extract needed columns
    net_return = analysis["net_return"]
    retracement = analysis["retracement"]
    high_time_idx = analysis["high_time_idx"]
    low_time_idx = analysis["low_time_idx"]

    # Initialize result with NaN
    result = pd.Series(np.nan, index=close.index, dtype=float)

    # Step 1: Determine direction using FLAT_THRESHOLD (0.1%)
    is_up = net_return > FLAT_THRESHOLD
    is_down = net_return < -FLAT_THRESHOLD
    is_flat = ~is_up & ~is_down  # SIDEWAYS

    # Step 2: Determine if mean-reverting
    is_mean_revert_up = (
        is_up & (low_time_idx < high_time_idx) & (retracement > RETRACEMENT_THRESHOLD)
    )
    is_mean_revert_down = (
        is_down & (high_time_idx < low_time_idx) & (retracement > RETRACEMENT_THRESHOLD)
    )

    # Assign labels (5 classes)
    result[is_flat] = PathLabel5Class.SIDEWAYS
    result[is_mean_revert_up] = PathLabel5Class.MEAN_REVERT_UP
    result[is_mean_revert_down] = PathLabel5Class.MEAN_REVERT_DOWN
    result[is_up & ~is_mean_revert_up] = PathLabel5Class.BULLISH
    result[is_down & ~is_mean_revert_down] = PathLabel5Class.BEARISH

    # Shift by -horizon to make it a forward-looking target
    result = result.shift(-horizon)
    return result


@register_target(
    name="strategy_label",
    task_type="classification",
    n_classes=5,
    target_column="y_strategy_label",
    description="5-class prescriptive: FLAT, TREND_LONG, TREND_SHORT, MR_LONG, MR_SHORT",
    label_enum=StrategyLabel,
)
def compute_strategy_label(
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    horizon: int,
    **kwargs: Any,
) -> pd.Series:
    """
    Compute 5-class prescriptive strategy label.

    Answers: "Should I trade, and how?"

    This is PRESCRIPTIVE (what to do) not DESCRIPTIVE (what happened).
    Combines regime detection + path analysis + risk assessment.

    Labels:
        0 (FLAT): Don't trade - sideways, uncertain, high vol regime
        1 (TREND_FOLLOW_LONG): Strong uptrend - ride momentum
        2 (TREND_FOLLOW_SHORT): Strong downtrend - ride momentum
        3 (MEAN_REVERT_LONG): Oversold + reverting - fade the dip
        4 (MEAN_REVERT_SHORT): Overbought + reverting - fade the rally

    Logic:
    1. If sideways (|net_return| < threshold) → FLAT
    2. If high volatility regime + uncertain → FLAT (risk management)
    3. If trending (high ER) + continuing momentum → TREND_FOLLOW
    4. If mean-reverting (high retracement) → MEAN_REVERT
    5. Otherwise → FLAT (no clear edge)

    Key difference from path_label_5:
    - path_label_5: "Price went UP via mean-reversion" (past)
    - strategy_label: "You should go LONG using MR strategy" (action)
    """
    # Thresholds
    FLAT_THRESHOLD = 0.001  # 0.1% - defines SIDEWAYS
    ER_TREND_THRESHOLD = 0.20  # Efficiency ratio for "trending"
    RETRACEMENT_THRESHOLD = 0.65  # For mean-reversion detection
    VOL_SPIKE_THRESHOLD = 1.5  # Vol > 1.5x rolling avg → cautious

    analysis = _get_15m_analysis(close)
    analysis = analysis.reindex(close.index)

    # Extract needed columns
    net_return = analysis["net_return"]
    efficiency_ratio = analysis["efficiency_ratio"]
    retracement = analysis["retracement"]
    high_time_idx = analysis["high_time_idx"]
    low_time_idx = analysis["low_time_idx"]

    # Calculate volatility regime (for risk filter)
    log_returns = np.log(close / close.shift(1))
    rolling_vol = log_returns.rolling(21).std()
    vol_ratio = rolling_vol / rolling_vol.rolling(63).mean()

    # Initialize as FLAT (default: don't trade)
    result = pd.Series(StrategyLabel.FLAT, index=close.index, dtype=float)

    # Direction determination
    is_up = net_return > FLAT_THRESHOLD
    is_down = net_return < -FLAT_THRESHOLD
    # is_flat implicitly handled by default FLAT assignment

    # Regime characteristics
    is_trending = efficiency_ratio >= ER_TREND_THRESHOLD
    is_high_vol = vol_ratio > VOL_SPIKE_THRESHOLD

    # Mean-reversion detection (went opposite direction first, then reversed)
    is_mean_revert_up = (
        is_up & (low_time_idx < high_time_idx) & (retracement > RETRACEMENT_THRESHOLD)
    )
    is_mean_revert_down = (
        is_down & (high_time_idx < low_time_idx) & (retracement > RETRACEMENT_THRESHOLD)
    )

    # Pure trend (efficient path, not mean-reverting)
    is_pure_trend_up = is_up & is_trending & ~is_mean_revert_up
    is_pure_trend_down = is_down & is_trending & ~is_mean_revert_down

    # Assign strategies (order matters)
    # FLAT stays as default for: sideways, high vol, or unclear

    # High volatility → stay FLAT (risk management override)
    # (This is already the default, but explicit for clarity)

    # TREND_FOLLOW: Clear trending moves with efficient path
    result[is_pure_trend_up & ~is_high_vol] = StrategyLabel.TREND_FOLLOW_LONG
    result[is_pure_trend_down & ~is_high_vol] = StrategyLabel.TREND_FOLLOW_SHORT

    # MEAN_REVERT: Counter-trend opportunities
    result[is_mean_revert_up & ~is_high_vol] = StrategyLabel.MEAN_REVERT_LONG
    result[is_mean_revert_down & ~is_high_vol] = StrategyLabel.MEAN_REVERT_SHORT

    # Shift by -horizon to make it a forward-looking target
    result = result.shift(-horizon)
    return result


@register_target(
    name="triple_barrier",
    task_type="classification",
    n_classes=3,
    target_column="y_triple_barrier",
    description="3-class triple barrier outcome: STOP_LOSS, TIME_EXIT, TAKE_PROFIT",
    label_enum=TripleBarrierLabel,
)
def compute_triple_barrier(
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    horizon: int,
    tp_mult: float = 1.5,  # Take-profit at 1.5x volatility
    sl_mult: float = 1.0,  # Stop-loss at 1.0x volatility
    **kwargs: Any,
) -> pd.Series:
    """
    Compute 3-class triple barrier outcome.

    Answers: "What's my expected risk/reward?"

    Based on Marcos López de Prado's triple barrier method from
    "Advances in Financial Machine Learning".

    Three barriers:
    1. Upper barrier (take-profit): price rises by tp_mult * volatility
    2. Lower barrier (stop-loss): price falls by sl_mult * volatility
    3. Vertical barrier (time): horizon bars pass (1 bar = 8h)

    Labels:
        0 (STOP_LOSS): Hit lower barrier first → losing trade
        1 (TIME_EXIT): Neither horizontal barrier hit → uncertain
        2 (TAKE_PROFIT): Hit upper barrier first → winning trade

    Default asymmetric barriers (TP > SL) reflect typical trading:
    - Let winners run (wider TP)
    - Cut losers quickly (tighter SL)

    Uses 15m data (32 bars per 8h) for precise barrier touch detection.
    At timestamp T, we predict the outcome for the bar starting at T+horizon.
    """
    # Volatility for barrier sizing (using range-based for efficiency)
    hl_range = np.log(high / low)
    volatility = hl_range.rolling(21).mean()

    # Calculate barriers relative to entry price (current close = next bar's open)
    tp_barrier = close * (1 + tp_mult * volatility)
    sl_barrier = close * (1 - sl_mult * volatility)

    # Initialize result
    result = pd.Series(np.nan, index=close.index, dtype=float)

    # Get 15m analysis - this is indexed by 8h timestamps
    # analysis[T] contains 15m data for bar T to T+8h
    analysis = _get_15m_analysis(close)
    analysis = analysis.reindex(close.index)

    # Shift analysis by -horizon so that at time T we get the FUTURE bar's 15m info
    # This aligns timing: analysis_shifted[T] = analysis[T+horizon] = bar T+horizon to T+horizon+8h
    analysis_shifted = analysis.shift(-horizon)

    # For each bar, determine which barrier was hit first in the FUTURE bar
    for i, ts in enumerate(close.index):
        if pd.isna(volatility.iloc[i]):
            continue

        # Skip if no future analysis available
        if pd.isna(analysis_shifted.loc[ts, "high_time_idx"]):
            continue

        tp = tp_barrier.iloc[i]
        sl = sl_barrier.iloc[i]

        # Get timing from the FUTURE bar's 15m analysis (correctly shifted)
        high_time = analysis_shifted.loc[ts, "high_time_idx"]
        low_time = analysis_shifted.loc[ts, "low_time_idx"]

        # Get the future bar's high/low from 8h data
        future_idx = i + horizon
        if future_idx >= len(close):
            continue

        future_high = high.iloc[future_idx]
        future_low = low.iloc[future_idx]

        if pd.isna(future_high) or pd.isna(future_low):
            continue

        # Check if barriers were touched
        hit_tp = future_high >= tp
        hit_sl = future_low <= sl

        if hit_tp and hit_sl:
            # Both barriers touched - use 15m timing to determine which first
            if high_time < low_time:
                result.iloc[i] = TripleBarrierLabel.TAKE_PROFIT
            else:
                result.iloc[i] = TripleBarrierLabel.STOP_LOSS
        elif hit_tp:
            result.iloc[i] = TripleBarrierLabel.TAKE_PROFIT
        elif hit_sl:
            result.iloc[i] = TripleBarrierLabel.STOP_LOSS
        else:
            result.iloc[i] = TripleBarrierLabel.TIME_EXIT

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

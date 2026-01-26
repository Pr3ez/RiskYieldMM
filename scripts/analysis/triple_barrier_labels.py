"""
Triple-Barrier Labels for Training (AFML Ch.3)
==============================================

Creates y_tb_direction column using López de Prado's triple-barrier method:
- Take profit barrier: entry + tp_mult × ATR
- Stop loss barrier: entry - sl_mult × ATR

References:
- López de Prado: "Advances in Financial Machine Learning" (Ch. 3)
- Reuses barrier math from scripts/strategy/exit_manager.py
"""

from typing import Literal

import numpy as np
import polars as pl

__all__ = ["compute_triple_barrier_labels", "get_barrier_touch", "BarrierTouch"]


class BarrierTouch:
    """Result of barrier touch detection for a single entry."""

    __slots__ = ("barrier_type", "bars_to_touch", "exit_price", "return_pct")

    def __init__(
        self,
        barrier_type: Literal["TP", "SL", "TIME"],
        bars_to_touch: int,
        exit_price: float,
        return_pct: float,
    ):
        self.barrier_type = barrier_type
        self.bars_to_touch = bars_to_touch
        self.exit_price = exit_price
        self.return_pct = return_pct

    def to_label(self) -> int:
        """
        Convert barrier touch to binary label.

        Returns:
            1 if profitable (TP hit), 0 if unprofitable (SL hit)
            For TIME barrier: 1 if return > 0, else 0
        """
        if self.barrier_type == "TP":
            return 1
        elif self.barrier_type == "SL":
            return 0
        else:  # TIME barrier
            return 1 if self.return_pct > 0 else 0


def get_barrier_touch(
    entry_price: float,
    tp_price: float,
    sl_price: float,
    future_highs: np.ndarray,
    future_lows: np.ndarray,
    future_closes: np.ndarray,
    max_bars: int,
) -> BarrierTouch | None:
    """
    Determine which barrier is touched first for a single entry.

    Assumes LONG position (TP > entry > SL). For SHORT, caller should
    swap tp_price and sl_price before calling.

    Args:
        entry_price: Entry price
        tp_price: Take profit price level (above entry for LONG)
        sl_price: Stop loss price level (below entry for LONG)
        future_highs: Array of high prices for next max_bars bars
        future_lows: Array of low prices for next max_bars bars
        future_closes: Array of close prices for next max_bars bars
        max_bars: Maximum holding period (time barrier)

    Returns:
        BarrierTouch with barrier_type, bars_to_touch, exit_price, return_pct
        Returns None if insufficient data (less than 1 future bar)
    """
    n_future = len(future_highs)
    if n_future == 0:
        return None

    actual_bars = min(n_future, max_bars)

    # Check each bar for barrier touch
    for bar_idx in range(actual_bars):
        high = future_highs[bar_idx]
        low = future_lows[bar_idx]
        close = future_closes[bar_idx]

        # Check if any barrier hit (using high/low to detect intrabar touches)
        tp_hit = high >= tp_price
        sl_hit = low <= sl_price

        if tp_hit and sl_hit:
            # Both barriers touched in same bar - use close to decide
            # This is a simplification; in reality we'd need tick data
            return_pct = (close - entry_price) / entry_price
            if return_pct >= 0:
                return BarrierTouch("TP", bar_idx + 1, tp_price, return_pct)
            else:
                return BarrierTouch("SL", bar_idx + 1, sl_price, return_pct)

        if tp_hit:
            return_pct = (tp_price - entry_price) / entry_price
            return BarrierTouch("TP", bar_idx + 1, tp_price, return_pct)

        if sl_hit:
            return_pct = (sl_price - entry_price) / entry_price
            return BarrierTouch("SL", bar_idx + 1, sl_price, return_pct)

    # Time barrier hit - use final close
    if actual_bars > 0:
        exit_price = future_closes[actual_bars - 1]
        return_pct = (exit_price - entry_price) / entry_price
        return BarrierTouch("TIME", actual_bars, exit_price, return_pct)

    return None


def _compute_atr(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    window: int = 21,
) -> np.ndarray:
    """
    Compute Average True Range (ATR).

    Args:
        high: High prices
        low: Low prices
        close: Close prices
        window: ATR lookback window

    Returns:
        ATR array (same length, first `window` values are NaN)
    """
    n = len(close)
    tr = np.zeros(n)

    # True range for first bar
    tr[0] = high[0] - low[0]

    # True range for subsequent bars
    for i in range(1, n):
        hl = high[i] - low[i]
        hc = abs(high[i] - close[i - 1])
        lc = abs(low[i] - close[i - 1])
        tr[i] = max(hl, hc, lc)

    # Simple moving average of TR
    atr = np.full(n, np.nan)
    for i in range(window - 1, n):
        atr[i] = np.mean(tr[i - window + 1 : i + 1])

    return atr


def compute_triple_barrier_labels(
    df: pl.DataFrame,
    tp_mult: float = 2.0,
    sl_mult: float = 2.0,
    max_bars: int = 3,
    atr_window: int = 21,
    high_col: str = "RAW_P_high_abs_NN",
    low_col: str = "RAW_P_low_abs_NN",
    close_col: str = "RAW_P_close_abs_NN",
    verbose: bool = True,
) -> pl.DataFrame:
    """
    Compute triple-barrier labels for entire dataset.

    For each bar, simulates entering a LONG position at close and determines
    which barrier (TP, SL, or TIME) is hit first over the next max_bars.

    Args:
        df: DataFrame with OHLC data (must have high, low, close columns)
        tp_mult: ATR multiplier for take profit (TP = close + tp_mult × ATR)
        sl_mult: ATR multiplier for stop loss (SL = close - sl_mult × ATR)
        max_bars: Maximum holding period (time barrier)
        atr_window: Window for ATR calculation
        high_col: Column name for high prices
        low_col: Column name for low prices
        close_col: Column name for close prices
        verbose: Print progress information

    Returns:
        DataFrame with added columns:
        - y_tb_direction: Binary label (1=profitable, 0=unprofitable)
        - y_tb_barrier: Which barrier was hit ("TP", "SL", "TIME")
        - y_tb_bars: Bars until barrier touch
        - y_tb_return: Return at exit
    """
    # Extract OHLC as numpy for speed
    if high_col not in df.columns:
        # Fallback to features file column names
        high_col = "RAW_P_high_abs_NN"
        low_col = "RAW_P_low_abs_NN"
        close_col = "RAW_P_close_abs_NN"

    # Check if raw columns exist, if not try to find them
    if high_col not in df.columns:
        # Try alternative naming
        available = [c for c in df.columns if "high" in c.lower()]
        if available:
            high_col = available[0]
        available = [
            c for c in df.columns if "low" in c.lower() and "close" not in c.lower()
        ]
        if available:
            low_col = available[0]
        available = [c for c in df.columns if "close" in c.lower()]
        if available:
            close_col = available[0]

    high = df[high_col].to_numpy()
    low = df[low_col].to_numpy()
    close = df[close_col].to_numpy()
    n = len(close)

    if verbose:
        print("\nComputing triple-barrier labels...")
        print(f"  TP multiplier: {tp_mult}×ATR")
        print(f"  SL multiplier: {sl_mult}×ATR")
        print(f"  Max holding: {max_bars} bars")
        print(f"  ATR window: {atr_window}")
        print(f"  Total rows: {n:,}")

    # Compute ATR
    atr = _compute_atr(high, low, close, atr_window)

    # Initialize output arrays
    tb_direction = np.full(n, np.nan)
    tb_barrier = np.full(n, "", dtype=object)
    tb_bars = np.full(n, np.nan)
    tb_return = np.full(n, np.nan)

    # Process each row
    valid_count = 0
    tp_count = 0
    sl_count = 0
    time_count = 0

    for i in range(n):
        # Skip if ATR not available
        if np.isnan(atr[i]):
            continue

        # Skip if not enough future data
        if i + 1 >= n:
            continue

        entry_price = close[i]
        current_atr = atr[i]

        # Compute barriers (LONG position)
        tp_price = entry_price + tp_mult * current_atr
        sl_price = entry_price - sl_mult * current_atr

        # Get future OHLC (up to max_bars ahead)
        end_idx = min(i + 1 + max_bars, n)
        future_highs = high[i + 1 : end_idx]
        future_lows = low[i + 1 : end_idx]
        future_closes = close[i + 1 : end_idx]

        # Determine which barrier is hit first
        result = get_barrier_touch(
            entry_price=entry_price,
            tp_price=tp_price,
            sl_price=sl_price,
            future_highs=future_highs,
            future_lows=future_lows,
            future_closes=future_closes,
            max_bars=max_bars,
        )

        if result is not None:
            tb_direction[i] = result.to_label()
            tb_barrier[i] = result.barrier_type
            tb_bars[i] = result.bars_to_touch
            tb_return[i] = result.return_pct
            valid_count += 1

            if result.barrier_type == "TP":
                tp_count += 1
            elif result.barrier_type == "SL":
                sl_count += 1
            else:
                time_count += 1

    # Add columns to DataFrame (handle NaN for Int8 by using nullable type)
    # Convert NaN to None for proper polars null handling
    tb_direction_series = pl.Series("y_tb_direction", tb_direction)
    tb_direction_series = tb_direction_series.fill_nan(None).cast(pl.Int8)

    df = df.with_columns(
        [
            tb_direction_series,
            pl.Series("y_tb_barrier", tb_barrier).cast(pl.Utf8),
            pl.Series("y_tb_bars", tb_bars),
            pl.Series("y_tb_return", tb_return),
        ]
    )

    if verbose:
        print(f"\n  Valid labels: {valid_count:,} ({100 * valid_count / n:.1f}%)")
        print(f"  TP exits: {tp_count:,} ({100 * tp_count / valid_count:.1f}%)")
        print(f"  SL exits: {sl_count:,} ({100 * sl_count / valid_count:.1f}%)")
        print(f"  TIME exits: {time_count:,} ({100 * time_count / valid_count:.1f}%)")

        # Label distribution
        label_1 = int(np.nansum(tb_direction == 1))
        label_0 = int(np.nansum(tb_direction == 0))
        print(
            f"\n  y_tb_direction=1 (profitable): {label_1:,} ({100 * label_1 / valid_count:.1f}%)"
        )
        print(
            f"  y_tb_direction=0 (unprofitable): {label_0:,} ({100 * label_0 / valid_count:.1f}%)"
        )

    return df


def validate_triple_barrier_labels(df: pl.DataFrame) -> dict:
    """
    Validate triple-barrier labels and return summary statistics.

    Args:
        df: DataFrame with y_tb_* columns

    Returns:
        Dictionary with validation metrics
    """
    if "y_tb_direction" not in df.columns:
        return {"error": "y_tb_direction column not found"}

    tb_dir = df["y_tb_direction"].to_numpy()
    valid_mask = ~np.isnan(tb_dir)
    valid_count = int(np.sum(valid_mask))
    total_count = len(tb_dir)

    if valid_count == 0:
        return {"error": "No valid labels"}

    label_1 = int(np.nansum(tb_dir == 1))
    label_0 = int(np.nansum(tb_dir == 0))

    # Compare with simple direction if available
    correlation = None
    if "y_direction" in df.columns:
        y_dir = df["y_direction"].to_numpy()
        both_valid = valid_mask & ~np.isnan(y_dir)
        if np.sum(both_valid) > 100:
            from scipy.stats import pearsonr

            correlation = pearsonr(tb_dir[both_valid], y_dir[both_valid])[0]

    # Barrier distribution
    barrier_dist = {}
    if "y_tb_barrier" in df.columns:
        barrier_col = df["y_tb_barrier"]
        for barrier_type in ["TP", "SL", "TIME"]:
            count = int((barrier_col == barrier_type).sum())
            barrier_dist[barrier_type] = count

    return {
        "total_rows": total_count,
        "valid_labels": valid_count,
        "valid_pct": 100 * valid_count / total_count,
        "label_1_count": label_1,
        "label_0_count": label_0,
        "label_1_pct": 100 * label_1 / valid_count,
        "label_0_pct": 100 * label_0 / valid_count,
        "class_balance": min(label_1, label_0) / max(label_1, label_0),
        "correlation_with_y_direction": correlation,
        "barrier_distribution": barrier_dist,
    }


if __name__ == "__main__":
    # Quick test
    import sys

    sys.path.insert(0, str(__file__).split("scripts")[0])

    from pathlib import Path

    data_dir = Path(__file__).parent.parent.parent / "data"
    raw_file = data_dir / "merged_8h_raw.parquet"

    if raw_file.exists():
        print("Loading raw data for testing...")
        df = pl.read_parquet(raw_file)
        print(f"Loaded: {df.shape}")

        # Compute labels
        df = compute_triple_barrier_labels(
            df,
            tp_mult=2.0,
            sl_mult=2.0,
            max_bars=3,
        )

        # Validate
        print("\n" + "=" * 60)
        print("VALIDATION RESULTS")
        print("=" * 60)
        validation = validate_triple_barrier_labels(df)
        for key, value in validation.items():
            print(f"  {key}: {value}")
    else:
        print(f"Raw data file not found: {raw_file}")
        print("Run this after Step 1a in main_wf.py")

from __future__ import annotations

import numpy as np
import polars as pl

try:
    from numba import njit
except ImportError:  # pragma: no cover - lightweight verification/runtime fallback
    def njit(*args, **kwargs):
        if args and callable(args[0]) and len(args) == 1 and not kwargs:
            return args[0]

        def decorator(func):
            return func

        return decorator


@njit
def compute_distance_metrics(
    close,
    high,
    low,
    batch_id,
    bar_pos,
    bars_per_batch,
    min_remaining,
):
    n = len(close)
    dist_avg_high = np.full(n, np.nan, dtype=np.float64)
    dist_avg_low = np.full(n, np.nan, dtype=np.float64)
    dist_top5_high = np.full(n, np.nan, dtype=np.float64)
    dist_bot5_low = np.full(n, np.nan, dtype=np.float64)
    remaining_bars_out = np.full(n, 0, dtype=np.int32)

    outlier_pct = 0.05
    for i in range(n):
        entry = close[i]
        current_batch = batch_id[i]
        batch_end = i + 1
        while batch_end < n and batch_id[batch_end] == current_batch:
            batch_end += 1

        count = batch_end - (i + 1)
        remaining_bars_out[i] = count
        if count < min_remaining:
            continue

        highs = np.zeros(count, dtype=np.float64)
        lows = np.zeros(count, dtype=np.float64)
        for j in range(count):
            highs[j] = high[i + 1 + j]
            lows[j] = low[i + 1 + j]

        sorted_highs = np.sort(highs)
        sorted_lows = np.sort(lows)
        top_n = max(1, int(count * outlier_pct))

        avg_high = np.mean(highs)
        avg_low = np.mean(lows)
        avg_top_high = np.mean(sorted_highs[-top_n:])
        avg_bot_low = np.mean(sorted_lows[:top_n])

        dist_avg_high[i] = 100.0 * (avg_high - entry) / entry
        dist_avg_low[i] = 100.0 * (entry - avg_low) / entry
        dist_top5_high[i] = 100.0 * (avg_top_high - entry) / entry
        dist_bot5_low[i] = 100.0 * (entry - avg_bot_low) / entry

    return (
        dist_avg_high,
        dist_avg_low,
        dist_top5_high,
        dist_bot5_low,
        remaining_bars_out,
    )


@njit
def compute_hybrid_distance_metrics(
    close_entry,
    batch_id_entry,
    bar_pos_15m_for_entry,
    high_15m,
    low_15m,
    batch_id_15m,
    bar_pos_15m,
    min_remaining,
    outlier_pct,
):
    n = len(close_entry)
    dist_avg_high = np.full(n, np.nan, dtype=np.float64)
    dist_avg_low = np.full(n, np.nan, dtype=np.float64)
    dist_top5_high = np.full(n, np.nan, dtype=np.float64)
    dist_bot5_low = np.full(n, np.nan, dtype=np.float64)
    remaining_bars_out = np.full(n, 0, dtype=np.int32)

    n_15m = len(high_15m)
    for i in range(n):
        entry = close_entry[i]
        current_batch = batch_id_entry[i]
        current_15m_pos = bar_pos_15m_for_entry[i]

        highs = []
        lows = []
        for j in range(n_15m):
            if batch_id_15m[j] == current_batch and bar_pos_15m[j] > current_15m_pos:
                highs.append(high_15m[j])
                lows.append(low_15m[j])

        count = len(highs)
        remaining_bars_out[i] = count
        if count < min_remaining:
            continue

        highs_arr = np.array(highs, dtype=np.float64)
        lows_arr = np.array(lows, dtype=np.float64)
        sorted_highs = np.sort(highs_arr)
        sorted_lows = np.sort(lows_arr)
        top_n = max(1, int(count * outlier_pct))

        avg_high = np.mean(highs_arr)
        avg_low = np.mean(lows_arr)
        avg_top_high = np.mean(sorted_highs[-top_n:])
        avg_bot_low = np.mean(sorted_lows[:top_n])

        dist_avg_high[i] = 100.0 * (avg_high - entry) / entry
        dist_avg_low[i] = 100.0 * (entry - avg_low) / entry
        dist_top5_high[i] = 100.0 * (avg_top_high - entry) / entry
        dist_bot5_low[i] = 100.0 * (entry - avg_bot_low) / entry

    return (
        dist_avg_high,
        dist_avg_low,
        dist_top5_high,
        dist_bot5_low,
        remaining_bars_out,
    )


@njit
def _compute_past_distance_metrics(close, high, low, bar_pos, window, outlier_pct):
    n = len(close)
    dist_avg_high = np.full(n, np.nan, dtype=np.float64)
    dist_avg_low = np.full(n, np.nan, dtype=np.float64)
    dist_top5_high = np.full(n, np.nan, dtype=np.float64)
    dist_bot5_low = np.full(n, np.nan, dtype=np.float64)

    top_n = max(1, int(window * outlier_pct))
    for i in range(n):
        # Use continuous family-stream history rather than batch-local bar
        # position. Resetting at every batch leaves the first `window` rows of
        # every batch null even when enough causal history already exists.
        if i < window:
            continue
        entry = close[i]
        if entry == 0:
            continue
        start = i - window
        highs = high[start:i]
        lows = low[start:i]
        avg_high = np.mean(highs)
        avg_low = np.mean(lows)
        sorted_highs = np.sort(highs)
        sorted_lows = np.sort(lows)
        avg_top_high = np.mean(sorted_highs[-top_n:])
        avg_bot_low = np.mean(sorted_lows[:top_n])
        dist_avg_high[i] = 100.0 * (avg_high - entry) / entry
        dist_avg_low[i] = 100.0 * (entry - avg_low) / entry
        dist_top5_high[i] = 100.0 * (avg_top_high - entry) / entry
        dist_bot5_low[i] = 100.0 * (entry - avg_bot_low) / entry

    return dist_avg_high, dist_avg_low, dist_top5_high, dist_bot5_low


def compute_4class_labels(
    df: pl.DataFrame,
    breakout_thresh: float,
    risk_thresh: float,
) -> pl.DataFrame:
    eps = 1e-10
    class_names = {
        0: "DOWN_BALANCED",
        1: "DOWN_EXPANSION",
        2: "UP_BALANCED",
        3: "UP_EXPANSION",
    }
    df = df.with_columns(
        [
            (pl.col("dist_avg_low") < 0).alias("is_breakout_up"),
            (pl.col("dist_avg_high") < 0).alias("is_breakout_down"),
        ]
    )
    df = df.with_columns(
        [
            pl.when(pl.col("is_breakout_up"))
            .then(pl.lit(True))
            .when(pl.col("is_breakout_down"))
            .then(pl.lit(False))
            .otherwise(pl.col("dist_avg_high") > pl.col("dist_avg_low"))
            .alias("is_up")
        ]
    )
    df = df.with_columns(
        [
            pl.when(pl.col("is_breakout_up"))
            .then(pl.col("dist_top5_high") > breakout_thresh)
            .when(pl.col("is_breakout_down"))
            .then(pl.lit(False))
            .otherwise(
                (pl.col("dist_top5_high") / (pl.col("dist_avg_high") + eps))
                > risk_thresh
            )
            .alias("high_risk_up"),
            pl.when(pl.col("is_breakout_down"))
            .then(pl.col("dist_bot5_low") > breakout_thresh)
            .when(pl.col("is_breakout_up"))
            .then(pl.lit(False))
            .otherwise(
                (pl.col("dist_bot5_low") / (pl.col("dist_avg_low") + eps))
                > risk_thresh
            )
            .alias("high_risk_down"),
        ]
    )
    df = df.with_columns(
        [
            pl.when(pl.col("dist_avg_high").is_nan())
            .then(pl.lit(-1))
            .when(
                pl.col("is_up")
                & (pl.col("high_risk_up") | pl.col("high_risk_down"))
            )
            .then(pl.lit(3))
            .when(pl.col("is_up"))
            .then(pl.lit(2))
            .when(
                ~pl.col("is_up")
                & (pl.col("high_risk_up") | pl.col("high_risk_down"))
            )
            .then(pl.lit(1))
            .when(~pl.col("is_up"))
            .then(pl.lit(0))
            .otherwise(pl.lit(-1))
            .alias("target_4class")
        ]
    )
    df = df.with_columns(
        pl.col("target_4class")
        .replace_strict({i: name for i, name in class_names.items()}, default="INVALID")
        .alias("target_name")
    )

    drop_cols = [
        col
        for col in [
            "is_breakout_up",
            "is_breakout_down",
            "is_up",
            "high_risk_up",
            "high_risk_down",
            "batch_id_check",
        ]
        if col in df.columns
    ]
    return df.drop(drop_cols)

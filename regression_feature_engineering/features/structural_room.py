"""Structural room and prior-level context feature family.

The formulas in this module are deterministic and causal. Channel levels are
computed on canonical higher-timeframe bars with `.shift(1)` before the rolling
window, so a source bar never contributes its own high/low to the channel used
at its close.
"""

from __future__ import annotations

import polars as pl

from regression_feature_engineering.core.alignment import source_prefix
from regression_feature_engineering.core.math import (
    bounded_expr,
    positive_part_expr,
    positive_vol_unit_bnd_expr,
    safe_div_expr,
    signed_vol_unit_bnd_expr,
)


FEATURE_FAMILY = "structural_room"
TARGET_INTENT = (
    "up_extreme",
    "down_extreme",
    "room_asymmetry",
    "price_location",
)
DEFAULT_ROOM_LOOKBACKS: tuple[int, ...] = (4, 16, 48)
SOURCE_PREFIX = "_rpf_room_"


def source_columns(*, lookbacks: tuple[int, ...] = DEFAULT_ROOM_LOOKBACKS) -> tuple[str, ...]:
    """Return structural source columns produced on canonical bars."""

    columns: list[str] = []
    for lookback in lookbacks:
        columns.extend(
            [
                f"{SOURCE_PREFIX}channel_high_l{lookback}",
                f"{SOURCE_PREFIX}channel_low_l{lookback}",
                f"{SOURCE_PREFIX}value_l{lookback}",
            ]
        )
    return tuple(columns)


def feature_columns(
    *,
    timeframes: tuple[str, ...],
    lookbacks: tuple[int, ...] = DEFAULT_ROOM_LOOKBACKS,
) -> tuple[str, ...]:
    """Return the model-facing structural-room feature columns."""

    columns: list[str] = []
    for timeframe in timeframes:
        for lookback in lookbacks:
            columns.extend(
                [
                    f"rpf_room_{timeframe}_up_to_high_l{lookback}_vol",
                    f"rpf_room_{timeframe}_down_to_low_l{lookback}_vol",
                    f"rpf_room_{timeframe}_asym_l{lookback}_bnd",
                    f"rpf_room_{timeframe}_up_room_share_l{lookback}_bnd",
                    f"rpf_room_{timeframe}_room_balance_l{lookback}_vol",
                    f"rpf_room_{timeframe}_donchian_pos_l{lookback}_bnd",
                    f"rpf_room_{timeframe}_breakout_above_l{lookback}_vol",
                    f"rpf_room_{timeframe}_breakdown_below_l{lookback}_vol",
                    f"rpf_room_{timeframe}_break_balance_l{lookback}_vol",
                    f"rpf_room_{timeframe}_value_dist_l{lookback}_vol",
                ]
            )
    return tuple(columns)


def enrich_structural_room_sources(
    bars: pl.DataFrame,
    *,
    lookbacks: tuple[int, ...] = DEFAULT_ROOM_LOOKBACKS,
) -> pl.DataFrame:
    """Add prior rolling channel/value columns to canonical bars.

    All derived source columns are based on bars strictly before the source bar
    by shifting each input before rolling. This lets the aligned prediction row
    use the latest closed bar without exposing that bar's own high/low as its
    prior channel.
    """

    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = required - set(bars.columns)
    if missing:
        raise ValueError(f"Structural source bars missing columns: {sorted(missing)}")

    out = bars.sort("timestamp").with_columns(
        [
            ((pl.col("high") + pl.col("low") + pl.col("close")) / 3.0).alias("_rpf_room_typical"),
            pl.col("volume").cast(pl.Float64).clip(0.0, None).alias("_rpf_room_volume"),
        ]
    )
    out = out.with_columns(
        (pl.col("_rpf_room_typical") * pl.col("_rpf_room_volume")).alias("_rpf_room_typical_volume")
    )

    for lookback in lookbacks:
        min_samples = min(int(lookback), max(2, int(lookback) // 4))
        vol_sum = (
            pl.col("_rpf_room_volume")
            .shift(1)
            .rolling_sum(window_size=int(lookback), min_samples=min_samples)
        )
        tv_sum = (
            pl.col("_rpf_room_typical_volume")
            .shift(1)
            .rolling_sum(window_size=int(lookback), min_samples=min_samples)
        )
        typical_mean = (
            pl.col("_rpf_room_typical")
            .shift(1)
            .rolling_mean(window_size=int(lookback), min_samples=min_samples)
        )
        out = out.with_columns(
            [
                pl.col("high")
                .shift(1)
                .rolling_max(window_size=int(lookback), min_samples=min_samples)
                .alias(f"{SOURCE_PREFIX}channel_high_l{lookback}"),
                pl.col("low")
                .shift(1)
                .rolling_min(window_size=int(lookback), min_samples=min_samples)
                .alias(f"{SOURCE_PREFIX}channel_low_l{lookback}"),
                pl.when(vol_sum.is_finite() & (vol_sum > 0))
                .then(tv_sum / vol_sum)
                .otherwise(typical_mean)
                .alias(f"{SOURCE_PREFIX}value_l{lookback}"),
            ]
        )

    keep_source_cols = set(source_columns(lookbacks=lookbacks))
    return out.drop(
        [
            col
            for col in out.columns
            if col.startswith("_rpf_room_") and col not in keep_source_cols
        ]
    )


def add_structural_room_features(
    df: pl.DataFrame,
    *,
    timeframes: tuple[str, ...],
    lookbacks: tuple[int, ...] = DEFAULT_ROOM_LOOKBACKS,
) -> pl.DataFrame:
    """Add structural room features from aligned prior channels."""

    required = {"close", "tb_volatility_pct"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing structural row source columns: {sorted(missing)}")

    out = df.with_columns(
        [
            pl.col("close").cast(pl.Float64).alias("_rpf_room_close"),
            pl.col("tb_volatility_pct").cast(pl.Float64).alias("_rpf_room_vol"),
        ]
    )

    for timeframe in timeframes:
        src = source_prefix(timeframe)
        for lookback in lookbacks:
            high = pl.col(f"{src}{SOURCE_PREFIX}channel_high_l{lookback}")
            low = pl.col(f"{src}{SOURCE_PREFIX}channel_low_l{lookback}")
            value = pl.col(f"{src}{SOURCE_PREFIX}value_l{lookback}")
            close = pl.col("_rpf_room_close")
            vol = pl.col("_rpf_room_vol")
            up_room_pct = safe_div_expr(positive_part_expr(high - close), close)
            down_room_pct = safe_div_expr(positive_part_expr(close - low), close)
            breakout_pct = safe_div_expr(positive_part_expr(close - high), close)
            breakdown_pct = safe_div_expr(positive_part_expr(low - close), close)
            channel_width = high - low
            up_room_vol = safe_div_expr(up_room_pct, vol)
            down_room_vol = safe_div_expr(down_room_pct, vol)
            breakout_vol = safe_div_expr(breakout_pct, vol)
            breakdown_vol = safe_div_expr(breakdown_pct, vol)

            out = out.with_columns(
                [
                    positive_vol_unit_bnd_expr(up_room_vol)
                    .alias(f"rpf_room_{timeframe}_up_to_high_l{lookback}_vol"),
                    positive_vol_unit_bnd_expr(down_room_vol)
                    .alias(f"rpf_room_{timeframe}_down_to_low_l{lookback}_vol"),
                    bounded_expr(
                        safe_div_expr(up_room_pct - down_room_pct, up_room_pct + down_room_pct),
                        lower=-1.0,
                        upper=1.0,
                    )
                    .fill_null(0.0)
                    .alias(f"rpf_room_{timeframe}_asym_l{lookback}_bnd"),
                    bounded_expr(safe_div_expr(up_room_pct, up_room_pct + down_room_pct), lower=0.0, upper=1.0)
                    .fill_null(0.5)
                    .alias(f"rpf_room_{timeframe}_up_room_share_l{lookback}_bnd"),
                    signed_vol_unit_bnd_expr(up_room_vol - down_room_vol)
                    .alias(f"rpf_room_{timeframe}_room_balance_l{lookback}_vol"),
                    bounded_expr(safe_div_expr(close - low, channel_width), lower=0.0, upper=1.0)
                    .fill_null(0.0)
                    .alias(f"rpf_room_{timeframe}_donchian_pos_l{lookback}_bnd"),
                    positive_vol_unit_bnd_expr(breakout_vol)
                    .alias(f"rpf_room_{timeframe}_breakout_above_l{lookback}_vol"),
                    positive_vol_unit_bnd_expr(breakdown_vol)
                    .alias(f"rpf_room_{timeframe}_breakdown_below_l{lookback}_vol"),
                    signed_vol_unit_bnd_expr(breakout_vol - breakdown_vol)
                    .alias(f"rpf_room_{timeframe}_break_balance_l{lookback}_vol"),
                    signed_vol_unit_bnd_expr(safe_div_expr(safe_div_expr(close - value, close), vol))
                    .alias(f"rpf_room_{timeframe}_value_dist_l{lookback}_vol"),
                ]
            )

    return out.drop(["_rpf_room_close", "_rpf_room_vol"])

"""Spike, breakout, and breakdown capacity feature family.

This family targets one-sided reach capacity for the extreme distance targets.
Breakout levels are previous closed rolling channels. Source impulse/release
statistics are computed on closed canonical bars and later joined by the
closed-bar as-of contract.
"""

from __future__ import annotations

import polars as pl

from regression_feature_engineering.core.alignment import source_prefix
from regression_feature_engineering.core.math import (
    bounded_expr,
    pct_change_expr,
    positive_part_expr,
    positive_vol_unit_bnd_expr,
    safe_div_expr,
    signed_vol_unit_bnd_expr,
)


FEATURE_FAMILY = "spike_breakout"
TARGET_INTENT = (
    "target_reg_distance_up_extreme_hvol_v2",
    "target_reg_distance_down_extreme_hvol_v2",
    "one_sided_reach_capacity",
)
DEFAULT_SPIKE_LOOKBACKS: tuple[int, ...] = (4, 16, 48)
SOURCE_PREFIX = "_rpf_spike_"


def source_columns(*, lookbacks: tuple[int, ...] = DEFAULT_SPIKE_LOOKBACKS) -> tuple[str, ...]:
    """Return spike/breakout source columns produced on canonical bars."""

    columns: list[str] = []
    for lookback in lookbacks:
        columns.extend(
            [
                f"{SOURCE_PREFIX}prior_high_l{lookback}",
                f"{SOURCE_PREFIX}prior_low_l{lookback}",
                f"{SOURCE_PREFIX}squeeze_l{lookback}",
                f"{SOURCE_PREFIX}release_l{lookback}",
                f"{SOURCE_PREFIX}squeeze_release_l{lookback}",
                f"{SOURCE_PREFIX}up_impulse_l{lookback}",
                f"{SOURCE_PREFIX}down_impulse_l{lookback}",
                f"{SOURCE_PREFIX}impulse_balance_l{lookback}",
                f"{SOURCE_PREFIX}up_volume_impulse_l{lookback}",
                f"{SOURCE_PREFIX}down_volume_impulse_l{lookback}",
                f"{SOURCE_PREFIX}volume_impulse_balance_l{lookback}",
                f"{SOURCE_PREFIX}tail_asym_l{lookback}",
            ]
        )
    return tuple(columns)


def feature_columns(
    *,
    timeframes: tuple[str, ...],
    lookbacks: tuple[int, ...] = DEFAULT_SPIKE_LOOKBACKS,
) -> tuple[str, ...]:
    """Return model-facing spike/breakout feature columns."""

    columns: list[str] = []
    for timeframe in timeframes:
        for lookback in lookbacks:
            columns.extend(
                [
                    f"rpf_spike_{timeframe}_up_break_prox_l{lookback}_vol",
                    f"rpf_spike_{timeframe}_down_break_prox_l{lookback}_vol",
                    f"rpf_spike_{timeframe}_break_prox_balance_l{lookback}_vol",
                    f"rpf_spike_{timeframe}_up_breakout_l{lookback}_vol",
                    f"rpf_spike_{timeframe}_down_breakdown_l{lookback}_vol",
                    f"rpf_spike_{timeframe}_breakout_balance_l{lookback}_vol",
                    f"rpf_spike_{timeframe}_squeeze_l{lookback}_bnd",
                    f"rpf_spike_{timeframe}_release_l{lookback}_bnd",
                    f"rpf_spike_{timeframe}_squeeze_release_l{lookback}_bnd",
                    f"rpf_spike_{timeframe}_up_impulse_l{lookback}_bnd",
                    f"rpf_spike_{timeframe}_down_impulse_l{lookback}_bnd",
                    f"rpf_spike_{timeframe}_impulse_balance_l{lookback}_bnd",
                    f"rpf_spike_{timeframe}_up_volume_impulse_l{lookback}_bnd",
                    f"rpf_spike_{timeframe}_down_volume_impulse_l{lookback}_bnd",
                    f"rpf_spike_{timeframe}_volume_impulse_balance_l{lookback}_bnd",
                    f"rpf_spike_{timeframe}_tail_asym_l{lookback}_bnd",
                ]
            )
    return tuple(columns)


def enrich_spike_breakout_sources(
    bars: pl.DataFrame,
    *,
    lookbacks: tuple[int, ...] = DEFAULT_SPIKE_LOOKBACKS,
) -> pl.DataFrame:
    """Add rolling spike/breakout source columns to canonical bars."""

    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = required - set(bars.columns)
    if missing:
        raise ValueError(f"Spike/breakout source bars missing columns: {sorted(missing)}")

    out = bars.sort("timestamp").with_columns(
        [
            pl.col("open").cast(pl.Float64),
            pl.col("high").cast(pl.Float64),
            pl.col("low").cast(pl.Float64),
            pl.col("close").cast(pl.Float64),
            pl.col("volume").cast(pl.Float64).clip(0.0, None).alias("_rpf_spike_volume"),
            (pl.col("high").cast(pl.Float64) - pl.col("low").cast(pl.Float64)).alias("_rpf_spike_range"),
        ]
    )
    out = out.with_columns(
        [
            safe_div_expr(pl.col("_rpf_spike_range"), pl.col("close")).alias("_rpf_spike_range_pct"),
            pct_change_expr(pl.col("close"), pl.col("close").shift(1)).alias("_rpf_spike_ret_pct"),
            bounded_expr(
                safe_div_expr(pl.col("close") - pl.col("low"), pl.col("_rpf_spike_range"), default=0.5),
                lower=0.0,
                upper=1.0,
            ).alias("_rpf_spike_close_loc"),
            bounded_expr(
                safe_div_expr(pl.col("close") - pl.col("open"), pl.col("_rpf_spike_range")),
                lower=-1.0,
                upper=1.0,
            ).alias("_rpf_spike_body_signed"),
        ]
    )
    out = out.with_columns(
        [
            bounded_expr(
                positive_part_expr(pl.col("_rpf_spike_body_signed")) * pl.col("_rpf_spike_close_loc"),
                lower=0.0,
                upper=1.0,
            ).alias("_rpf_spike_up_bar_impulse"),
            bounded_expr(
                positive_part_expr(-pl.col("_rpf_spike_body_signed")) * (1.0 - pl.col("_rpf_spike_close_loc")),
                lower=0.0,
                upper=1.0,
            ).alias("_rpf_spike_down_bar_impulse"),
        ]
    )

    for lookback in lookbacks:
        lookback = int(lookback)
        long_lookback = max(lookback * 4, lookback + 1)
        min_samples = min(lookback, max(2, lookback // 4))
        long_min_samples = min(long_lookback, max(4, long_lookback // 4))

        prior_high_col = f"{SOURCE_PREFIX}prior_high_l{lookback}"
        prior_low_col = f"{SOURCE_PREFIX}prior_low_l{lookback}"
        short_range_col = f"_rpf_spike_short_range_l{lookback}"
        long_range_col = f"_rpf_spike_long_range_l{lookback}"
        vol_rel_col = f"_rpf_spike_volume_rel_l{lookback}"
        release_raw_col = f"_rpf_spike_release_raw_l{lookback}"
        release_bnd_col = f"{SOURCE_PREFIX}release_l{lookback}"
        squeeze_col = f"{SOURCE_PREFIX}squeeze_l{lookback}"
        up_impulse_col = f"{SOURCE_PREFIX}up_impulse_l{lookback}"
        down_impulse_col = f"{SOURCE_PREFIX}down_impulse_l{lookback}"
        up_vol_impulse_col = f"{SOURCE_PREFIX}up_volume_impulse_l{lookback}"
        down_vol_impulse_col = f"{SOURCE_PREFIX}down_volume_impulse_l{lookback}"

        out = out.with_columns(
            [
                pl.col("high")
                .shift(1)
                .rolling_max(window_size=lookback, min_samples=min_samples)
                .alias(prior_high_col),
                pl.col("low")
                .shift(1)
                .rolling_min(window_size=lookback, min_samples=min_samples)
                .alias(prior_low_col),
                pl.col("_rpf_spike_range_pct")
                .shift(1)
                .rolling_mean(window_size=lookback, min_samples=min_samples)
                .alias(short_range_col),
                pl.col("_rpf_spike_range_pct")
                .shift(1)
                .rolling_mean(window_size=long_lookback, min_samples=long_min_samples)
                .alias(long_range_col),
                safe_div_expr(
                    pl.col("_rpf_spike_volume"),
                    pl.col("_rpf_spike_volume")
                    .shift(1)
                    .rolling_median(window_size=lookback, min_samples=min_samples),
                    default=0.0,
                ).alias(vol_rel_col),
            ]
        )
        out = out.with_columns(
            [
                safe_div_expr(pl.col("_rpf_spike_range_pct"), pl.col(short_range_col), default=0.0).alias(release_raw_col),
            ]
        )
        out = out.with_columns(
            [
                bounded_expr(
                    1.0 - safe_div_expr(pl.col(short_range_col), pl.col(long_range_col), default=1.0),
                    lower=0.0,
                    upper=1.0,
                )
                .fill_null(0.0)
                .alias(squeeze_col),
                bounded_expr(
                    safe_div_expr(pl.col(release_raw_col), 1.0 + pl.col(release_raw_col), default=0.0),
                    lower=0.0,
                    upper=1.0,
                )
                .fill_null(0.0)
                .alias(release_bnd_col),
            ]
        )
        out = out.with_columns(
            [
                (
                    pl.col("_rpf_spike_up_bar_impulse")
                    * pl.col(release_bnd_col)
                )
                .rolling_mean(window_size=lookback, min_samples=min_samples)
                .clip(0.0, 1.0)
                .fill_null(0.0)
                .alias(up_impulse_col),
                (
                    pl.col("_rpf_spike_down_bar_impulse")
                    * pl.col(release_bnd_col)
                )
                .rolling_mean(window_size=lookback, min_samples=min_samples)
                .clip(0.0, 1.0)
                .fill_null(0.0)
                .alias(down_impulse_col),
                (
                    pl.col("_rpf_spike_up_bar_impulse")
                    * pl.col(release_bnd_col)
                    * bounded_expr(safe_div_expr(pl.col(vol_rel_col), 1.0 + pl.col(vol_rel_col)), lower=0.0, upper=1.0)
                )
                .rolling_mean(window_size=lookback, min_samples=min_samples)
                .clip(0.0, 1.0)
                .fill_null(0.0)
                .alias(up_vol_impulse_col),
                (
                    pl.col("_rpf_spike_down_bar_impulse")
                    * pl.col(release_bnd_col)
                    * bounded_expr(safe_div_expr(pl.col(vol_rel_col), 1.0 + pl.col(vol_rel_col)), lower=0.0, upper=1.0)
                )
                .rolling_mean(window_size=lookback, min_samples=min_samples)
                .clip(0.0, 1.0)
                .fill_null(0.0)
                .alias(down_vol_impulse_col),
            ]
        )
        out = out.with_columns(
            [
                (pl.col(squeeze_col) * pl.col(release_bnd_col))
                .clip(0.0, 1.0)
                .fill_null(0.0)
                .alias(f"{SOURCE_PREFIX}squeeze_release_l{lookback}"),
                (pl.col(up_impulse_col) - pl.col(down_impulse_col))
                .clip(-1.0, 1.0)
                .fill_null(0.0)
                .alias(f"{SOURCE_PREFIX}impulse_balance_l{lookback}"),
                (pl.col(up_vol_impulse_col) - pl.col(down_vol_impulse_col))
                .clip(-1.0, 1.0)
                .fill_null(0.0)
                .alias(f"{SOURCE_PREFIX}volume_impulse_balance_l{lookback}"),
                (
                    0.5 * (pl.col(up_impulse_col) - pl.col(down_impulse_col))
                    + 0.5 * (pl.col(up_vol_impulse_col) - pl.col(down_vol_impulse_col))
                )
                .clip(-1.0, 1.0)
                .fill_null(0.0)
                .alias(f"{SOURCE_PREFIX}tail_asym_l{lookback}"),
            ]
        )

    keep_source_cols = set(source_columns(lookbacks=lookbacks))
    return out.drop(
        [
            col
            for col in out.columns
            if col.startswith("_rpf_spike_") and col not in keep_source_cols
        ]
    )


def add_spike_breakout_features(
    df: pl.DataFrame,
    *,
    timeframes: tuple[str, ...],
    lookbacks: tuple[int, ...] = DEFAULT_SPIKE_LOOKBACKS,
) -> pl.DataFrame:
    """Add model-facing spike/breakout features from aligned source columns."""

    required = {"close", "tb_volatility_pct"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing spike/breakout row source columns: {sorted(missing)}")

    out = df.with_columns(
        [
            pl.col("close").cast(pl.Float64).alias("_rpf_spike_row_close"),
            pl.col("tb_volatility_pct").cast(pl.Float64).alias("_rpf_spike_row_vol"),
        ]
    )
    for timeframe in timeframes:
        src = source_prefix(timeframe)
        for lookback in lookbacks:
            high = pl.col(f"{src}{SOURCE_PREFIX}prior_high_l{lookback}")
            low = pl.col(f"{src}{SOURCE_PREFIX}prior_low_l{lookback}")
            close = pl.col("_rpf_spike_row_close")
            vol = pl.col("_rpf_spike_row_vol")
            up_prox_pct = safe_div_expr(positive_part_expr(high - close), close)
            down_prox_pct = safe_div_expr(positive_part_expr(close - low), close)
            up_break_pct = safe_div_expr(positive_part_expr(close - high), close)
            down_break_pct = safe_div_expr(positive_part_expr(low - close), close)
            up_prox_vol = safe_div_expr(up_prox_pct, vol)
            down_prox_vol = safe_div_expr(down_prox_pct, vol)
            up_break_vol = safe_div_expr(up_break_pct, vol)
            down_break_vol = safe_div_expr(down_break_pct, vol)

            out = out.with_columns(
                [
                    positive_vol_unit_bnd_expr(up_prox_vol)
                    .alias(f"rpf_spike_{timeframe}_up_break_prox_l{lookback}_vol"),
                    positive_vol_unit_bnd_expr(down_prox_vol)
                    .alias(f"rpf_spike_{timeframe}_down_break_prox_l{lookback}_vol"),
                    signed_vol_unit_bnd_expr(down_prox_vol - up_prox_vol)
                    .alias(f"rpf_spike_{timeframe}_break_prox_balance_l{lookback}_vol"),
                    positive_vol_unit_bnd_expr(up_break_vol)
                    .alias(f"rpf_spike_{timeframe}_up_breakout_l{lookback}_vol"),
                    positive_vol_unit_bnd_expr(down_break_vol)
                    .alias(f"rpf_spike_{timeframe}_down_breakdown_l{lookback}_vol"),
                    signed_vol_unit_bnd_expr(up_break_vol - down_break_vol)
                    .alias(f"rpf_spike_{timeframe}_breakout_balance_l{lookback}_vol"),
                ]
            )
            for suffix in (
                "squeeze",
                "release",
                "squeeze_release",
                "up_impulse",
                "down_impulse",
                "impulse_balance",
                "up_volume_impulse",
                "down_volume_impulse",
                "volume_impulse_balance",
                "tail_asym",
            ):
                source_col = f"{src}{SOURCE_PREFIX}{suffix}_l{lookback}"
                if source_col not in out.columns:
                    raise ValueError(f"Missing spike/breakout row source column: {source_col}")
                out = out.with_columns(
                    pl.col(source_col)
                    .cast(pl.Float64)
                    .fill_null(0.0)
                    .alias(f"rpf_spike_{timeframe}_{suffix}_l{lookback}_bnd")
                )
    return out.drop(["_rpf_spike_row_close", "_rpf_spike_row_vol"])

"""Regime, session, and calendar-state feature family.

This family contains only information known at prediction time:

- UTC calendar encodings from the prediction timestamp;
- metadata from the latest closed canonical bar;
- rolling volatility/trend/range regime summaries from closed canonical bars.

It does not create rows for closed sessions and does not infer unavailable
context from future bars.
"""

from __future__ import annotations

import math

import polars as pl

from regression_feature_engineering.core.alignment import source_prefix
from regression_feature_engineering.core.math import bounded_expr, pct_change_expr, safe_div_expr


FEATURE_FAMILY = "regime_calendar_state"
TARGET_INTENT = (
    "all_targets",
    "known_calendar_state",
    "session_state",
    "trend_range_regime",
    "volatility_regime",
)
DEFAULT_REGIME_LOOKBACKS: tuple[int, ...] = (4, 16, 48)
SOURCE_PREFIX = "_rpf_regime_"

SESSION_SOURCE_COLUMNS: tuple[str, ...] = (
    f"{SOURCE_PREFIX}market_open",
    f"{SOURCE_PREFIX}synthetic_no_trade",
    f"{SOURCE_PREFIX}gap_fill",
    f"{SOURCE_PREFIX}minutes_since_prev_real_bar",
    f"{SOURCE_PREFIX}session_progress",
    f"{SOURCE_PREFIX}minutes_to_close",
    f"{SOURCE_PREFIX}session_open",
    f"{SOURCE_PREFIX}session_close",
    f"{SOURCE_PREFIX}weekly_open",
    f"{SOURCE_PREFIX}weekly_close",
)


def source_columns(*, lookbacks: tuple[int, ...] = DEFAULT_REGIME_LOOKBACKS) -> tuple[str, ...]:
    """Return regime/session source columns produced on canonical bars."""

    columns: list[str] = list(SESSION_SOURCE_COLUMNS)
    for lookback in lookbacks:
        columns.extend(
            [
                f"{SOURCE_PREFIX}vol_rel_l{lookback}",
                f"{SOURCE_PREFIX}vol_expanding_l{lookback}",
                f"{SOURCE_PREFIX}trend_eff_l{lookback}",
                f"{SOURCE_PREFIX}trend_sign_l{lookback}",
                f"{SOURCE_PREFIX}trend_alignment_l{lookback}",
                f"{SOURCE_PREFIX}range_chop_l{lookback}",
                f"{SOURCE_PREFIX}bull_trend_l{lookback}",
                f"{SOURCE_PREFIX}bear_trend_l{lookback}",
            ]
        )
    return tuple(columns)


def feature_columns(
    *,
    timeframes: tuple[str, ...],
    lookbacks: tuple[int, ...] = DEFAULT_REGIME_LOOKBACKS,
) -> tuple[str, ...]:
    """Return model-facing regime/calendar feature columns."""

    columns: list[str] = [
        "rpf_regime_utc_hour_sin",
        "rpf_regime_utc_hour_cos",
        "rpf_regime_utc_dow_sin",
        "rpf_regime_utc_dow_cos",
        "rpf_regime_utc_is_weekend_bnd",
    ]
    for timeframe in timeframes:
        columns.extend(
            [
                f"rpf_regime_{timeframe}_market_open_bnd",
                f"rpf_regime_{timeframe}_synthetic_no_trade_bnd",
                f"rpf_regime_{timeframe}_gap_fill_bnd",
                f"rpf_regime_{timeframe}_minutes_since_prev_real_bar_bnd",
                f"rpf_regime_{timeframe}_session_progress_bnd",
                f"rpf_regime_{timeframe}_minutes_to_close_bnd",
                f"rpf_regime_{timeframe}_session_open_bnd",
                f"rpf_regime_{timeframe}_session_close_bnd",
                f"rpf_regime_{timeframe}_weekly_open_bnd",
                f"rpf_regime_{timeframe}_weekly_close_bnd",
            ]
        )
        for lookback in lookbacks:
            columns.extend(
                [
                    f"rpf_regime_{timeframe}_vol_rel_l{lookback}_bnd",
                    f"rpf_regime_{timeframe}_vol_expanding_l{lookback}_bnd",
                    f"rpf_regime_{timeframe}_trend_eff_l{lookback}_bnd",
                    f"rpf_regime_{timeframe}_trend_sign_l{lookback}_bnd",
                    f"rpf_regime_{timeframe}_trend_alignment_l{lookback}_bnd",
                    f"rpf_regime_{timeframe}_range_chop_l{lookback}_bnd",
                    f"rpf_regime_{timeframe}_bull_trend_l{lookback}_bnd",
                    f"rpf_regime_{timeframe}_bear_trend_l{lookback}_bnd",
                ]
            )
    return tuple(columns)


def enrich_regime_calendar_state_sources(
    bars: pl.DataFrame,
    *,
    lookbacks: tuple[int, ...] = DEFAULT_REGIME_LOOKBACKS,
) -> pl.DataFrame:
    """Add rolling regime/session source columns to canonical bars."""

    required = {"timestamp", "open", "high", "low", "close"}
    missing = required - set(bars.columns)
    if missing:
        raise ValueError(f"Regime/calendar source bars missing columns: {sorted(missing)}")

    out = _with_optional_metadata_defaults(bars.sort("timestamp")).with_columns(
        [
            pl.col("open").cast(pl.Float64),
            pl.col("high").cast(pl.Float64),
            pl.col("low").cast(pl.Float64),
            pl.col("close").cast(pl.Float64),
            (pl.col("high").cast(pl.Float64) - pl.col("low").cast(pl.Float64)).alias("_rpf_regime_range"),
        ]
    )
    out = out.with_columns(
        [
            safe_div_expr(pl.col("_rpf_regime_range"), pl.col("close")).alias("_rpf_regime_range_pct"),
            pct_change_expr(pl.col("close"), pl.col("close").shift(1)).alias("_rpf_regime_ret_pct"),
        ]
    )
    out = out.with_columns(
        [
            pl.when(pl.col("_rpf_regime_ret_pct") > 0.0)
            .then(1.0)
            .when(pl.col("_rpf_regime_ret_pct") < 0.0)
            .then(-1.0)
            .otherwise(0.0)
            .alias("_rpf_regime_ret_sign"),
            pl.col("_rpf_regime_ret_pct").abs().alias("_rpf_regime_abs_ret_pct"),
        ]
    )
    out = out.with_columns(
        [
            pl.col("is_market_open")
            .cast(pl.Float64)
            .fill_null(0.0)
            .clip(0.0, 1.0)
            .alias(f"{SOURCE_PREFIX}market_open"),
            pl.col("is_synthetic_no_trade")
            .cast(pl.Float64)
            .fill_null(0.0)
            .clip(0.0, 1.0)
            .alias(f"{SOURCE_PREFIX}synthetic_no_trade"),
            pl.col("is_open_session_gap_fill")
            .cast(pl.Float64)
            .fill_null(0.0)
            .clip(0.0, 1.0)
            .alias(f"{SOURCE_PREFIX}gap_fill"),
            bounded_expr(
                safe_div_expr(
                    pl.col("minutes_since_prev_real_bar").cast(pl.Float64).clip(0.0, None),
                    pl.col("minutes_since_prev_real_bar").cast(pl.Float64).clip(0.0, None) + 1440.0,
                ),
                lower=0.0,
                upper=1.0,
            )
            .fill_null(0.0)
            .alias(f"{SOURCE_PREFIX}minutes_since_prev_real_bar"),
            bounded_expr(
                safe_div_expr(
                    pl.col("session_bar_pos").cast(pl.Float64).clip(0.0, None),
                    pl.col("session_bar_pos").cast(pl.Float64).clip(0.0, None)
                    + pl.col("session_minutes_to_close").cast(pl.Float64).clip(0.0, None)
                    + 1.0,
                ),
                lower=0.0,
                upper=1.0,
            )
            .fill_null(0.0)
            .alias(f"{SOURCE_PREFIX}session_progress"),
            bounded_expr(
                safe_div_expr(
                    pl.col("session_minutes_to_close").cast(pl.Float64).clip(0.0, None),
                    pl.col("session_minutes_to_close").cast(pl.Float64).clip(0.0, None) + 1440.0,
                ),
                lower=0.0,
                upper=1.0,
            )
            .fill_null(0.0)
            .alias(f"{SOURCE_PREFIX}minutes_to_close"),
            pl.col("is_session_open_bar")
            .cast(pl.Float64)
            .fill_null(0.0)
            .clip(0.0, 1.0)
            .alias(f"{SOURCE_PREFIX}session_open"),
            pl.col("is_session_close_bar")
            .cast(pl.Float64)
            .fill_null(0.0)
            .clip(0.0, 1.0)
            .alias(f"{SOURCE_PREFIX}session_close"),
            pl.col("is_weekly_open_bar")
            .cast(pl.Float64)
            .fill_null(0.0)
            .clip(0.0, 1.0)
            .alias(f"{SOURCE_PREFIX}weekly_open"),
            pl.col("is_weekly_close_bar")
            .cast(pl.Float64)
            .fill_null(0.0)
            .clip(0.0, 1.0)
            .alias(f"{SOURCE_PREFIX}weekly_close"),
        ]
    )

    for lookback in lookbacks:
        lookback = int(lookback)
        min_samples = min(lookback, max(2, lookback // 4))
        range_median = f"_rpf_regime_range_median_l{lookback}"
        path_col = f"_rpf_regime_path_l{lookback}"
        net_col = f"_rpf_regime_net_l{lookback}"
        trend_eff_col = f"{SOURCE_PREFIX}trend_eff_l{lookback}"
        trend_sign_col = f"{SOURCE_PREFIX}trend_sign_l{lookback}"

        out = out.with_columns(
            [
                pl.col("_rpf_regime_range_pct")
                .shift(1)
                .rolling_median(window_size=lookback, min_samples=min_samples)
                .alias(range_median),
                pl.col("_rpf_regime_abs_ret_pct")
                .rolling_sum(window_size=lookback, min_samples=min_samples)
                .alias(path_col),
                pl.col("_rpf_regime_ret_sign")
                .rolling_mean(window_size=lookback, min_samples=min_samples)
                .fill_null(0.0)
                .clip(-1.0, 1.0)
                .alias(trend_sign_col),
                pct_change_expr(pl.col("close"), pl.col("close").shift(lookback)).alias(net_col),
            ]
        )
        vol_rel_raw = safe_div_expr(pl.col("_rpf_regime_range_pct"), pl.col(range_median), default=0.0)
        trend_eff = bounded_expr(safe_div_expr(pl.col(net_col), pl.col(path_col), default=0.0), lower=-1.0, upper=1.0)
        out = out.with_columns(
            [
                bounded_expr(safe_div_expr(vol_rel_raw, 1.0 + vol_rel_raw, default=0.0), lower=0.0, upper=1.0)
                .fill_null(0.0)
                .alias(f"{SOURCE_PREFIX}vol_rel_l{lookback}"),
                (pl.col("_rpf_regime_range_pct") > pl.col(range_median))
                .cast(pl.Float64)
                .fill_null(0.0)
                .alias(f"{SOURCE_PREFIX}vol_expanding_l{lookback}"),
                trend_eff.fill_null(0.0).alias(trend_eff_col),
            ]
        )
        out = out.with_columns(
            [
                bounded_expr((pl.col(trend_eff_col) + pl.col(trend_sign_col)) / 2.0, lower=-1.0, upper=1.0)
                .fill_null(0.0)
                .alias(f"{SOURCE_PREFIX}trend_alignment_l{lookback}"),
                (1.0 - pl.col(trend_eff_col).abs())
                .clip(0.0, 1.0)
                .fill_null(0.0)
                .alias(f"{SOURCE_PREFIX}range_chop_l{lookback}"),
                ((pl.col(trend_eff_col) > 0.35) & (pl.col(trend_sign_col) > 0.25))
                .cast(pl.Float64)
                .fill_null(0.0)
                .alias(f"{SOURCE_PREFIX}bull_trend_l{lookback}"),
                ((pl.col(trend_eff_col) < -0.35) & (pl.col(trend_sign_col) < -0.25))
                .cast(pl.Float64)
                .fill_null(0.0)
                .alias(f"{SOURCE_PREFIX}bear_trend_l{lookback}"),
            ]
        )

    keep_source_cols = set(source_columns(lookbacks=lookbacks))
    return out.drop(
        [
            col
            for col in out.columns
            if col.startswith("_rpf_regime_") and col not in keep_source_cols
        ]
    )


def add_regime_calendar_state_features(
    df: pl.DataFrame,
    *,
    timeframes: tuple[str, ...],
    lookbacks: tuple[int, ...] = DEFAULT_REGIME_LOOKBACKS,
) -> pl.DataFrame:
    """Add model-facing regime/calendar features from timestamps and sources."""

    if "timestamp" not in df.columns:
        raise ValueError("Regime/calendar features require timestamp")

    minute_of_day = (pl.col("timestamp").dt.hour().cast(pl.Float64) * 60.0) + pl.col("timestamp").dt.minute().cast(pl.Float64)
    day_of_week = (pl.col("timestamp").dt.weekday().cast(pl.Float64) - 1.0).clip(0.0, 6.0)
    out = df.with_columns(
        [
            ((minute_of_day / 1440.0) * (2.0 * math.pi)).sin().alias("rpf_regime_utc_hour_sin"),
            ((minute_of_day / 1440.0) * (2.0 * math.pi)).cos().alias("rpf_regime_utc_hour_cos"),
            ((day_of_week / 7.0) * (2.0 * math.pi)).sin().alias("rpf_regime_utc_dow_sin"),
            ((day_of_week / 7.0) * (2.0 * math.pi)).cos().alias("rpf_regime_utc_dow_cos"),
            (day_of_week >= 5.0).cast(pl.Float64).alias("rpf_regime_utc_is_weekend_bnd"),
        ]
    )
    for timeframe in timeframes:
        src = source_prefix(timeframe)
        for suffix in (
            "market_open",
            "synthetic_no_trade",
            "gap_fill",
            "minutes_since_prev_real_bar",
            "session_progress",
            "minutes_to_close",
            "session_open",
            "session_close",
            "weekly_open",
            "weekly_close",
        ):
            source_col = f"{src}{SOURCE_PREFIX}{suffix}"
            if source_col not in out.columns:
                raise ValueError(f"Missing regime/calendar row source column: {source_col}")
            out = out.with_columns(
                pl.col(source_col)
                .cast(pl.Float64)
                .fill_null(0.0)
                .clip(0.0, 1.0)
                .alias(f"rpf_regime_{timeframe}_{suffix}_bnd")
            )
        for lookback in lookbacks:
            for suffix, lower in (
                ("vol_rel", 0.0),
                ("vol_expanding", 0.0),
                ("trend_eff", -1.0),
                ("trend_sign", -1.0),
                ("trend_alignment", -1.0),
                ("range_chop", 0.0),
                ("bull_trend", 0.0),
                ("bear_trend", 0.0),
            ):
                source_col = f"{src}{SOURCE_PREFIX}{suffix}_l{lookback}"
                if source_col not in out.columns:
                    raise ValueError(f"Missing regime/calendar row source column: {source_col}")
                out = out.with_columns(
                    pl.col(source_col)
                    .cast(pl.Float64)
                    .fill_null(0.0)
                    .clip(lower, 1.0)
                    .alias(f"rpf_regime_{timeframe}_{suffix}_l{lookback}_bnd")
                )
    return out


def _with_optional_metadata_defaults(bars: pl.DataFrame) -> pl.DataFrame:
    """Add canonical metadata defaults when a fixture omits optional columns."""

    defaults: dict[str, pl.Expr] = {
        "is_market_open": pl.lit(True),
        "is_synthetic_no_trade": pl.lit(False),
        "is_open_session_gap_fill": pl.lit(False),
        "minutes_since_prev_real_bar": pl.lit(0),
        "session_bar_pos": pl.lit(0),
        "session_minutes_to_close": pl.lit(0),
        "is_session_open_bar": pl.lit(False),
        "is_session_close_bar": pl.lit(False),
        "is_weekly_open_bar": pl.lit(False),
        "is_weekly_close_bar": pl.lit(False),
    }
    additions = [expr.alias(name) for name, expr in defaults.items() if name not in bars.columns]
    return bars.with_columns(additions) if additions else bars

"""Rejection and two-sided chop feature family.

This family targets path shape, not direction alone. It helps distinguish a
clean accepted move from a wick/rejection or two-sided path where extremes can
be high while mean-distance targets remain weaker.
"""

from __future__ import annotations

import polars as pl

from regression_feature_engineering.core.alignment import source_prefix
from regression_feature_engineering.core.math import bounded_expr, pct_change_expr, safe_div_expr


FEATURE_FAMILY = "rejection_chop"
TARGET_INTENT = (
    "all_targets",
    "wick_rejection",
    "two_sided_noise_vs_directional_acceptance",
    "extreme_vs_mean_separation",
)
DEFAULT_CHOP_LOOKBACKS: tuple[int, ...] = (4, 16, 48)
SOURCE_PREFIX = "_rpf_chop_"


def source_columns(*, lookbacks: tuple[int, ...] = DEFAULT_CHOP_LOOKBACKS) -> tuple[str, ...]:
    """Return rejection/chop source columns produced on canonical bars."""

    columns: list[str] = []
    for lookback in lookbacks:
        columns.extend(
            [
                f"{SOURCE_PREFIX}upper_reject_l{lookback}",
                f"{SOURCE_PREFIX}lower_reject_l{lookback}",
                f"{SOURCE_PREFIX}reject_balance_l{lookback}",
                f"{SOURCE_PREFIX}two_sided_l{lookback}",
                f"{SOURCE_PREFIX}reversal_rate_l{lookback}",
                f"{SOURCE_PREFIX}path_eff_l{lookback}",
                f"{SOURCE_PREFIX}path_chop_l{lookback}",
                f"{SOURCE_PREFIX}failed_up_break_l{lookback}",
                f"{SOURCE_PREFIX}failed_down_break_l{lookback}",
                f"{SOURCE_PREFIX}failed_break_balance_l{lookback}",
            ]
        )
    return tuple(columns)


def feature_columns(
    *,
    timeframes: tuple[str, ...],
    lookbacks: tuple[int, ...] = DEFAULT_CHOP_LOOKBACKS,
) -> tuple[str, ...]:
    """Return model-facing rejection/chop feature columns."""

    columns: list[str] = []
    for timeframe in timeframes:
        for lookback in lookbacks:
            columns.extend(
                [
                    f"rpf_chop_{timeframe}_upper_reject_l{lookback}_bnd",
                    f"rpf_chop_{timeframe}_lower_reject_l{lookback}_bnd",
                    f"rpf_chop_{timeframe}_reject_balance_l{lookback}_bnd",
                    f"rpf_chop_{timeframe}_two_sided_l{lookback}_bnd",
                    f"rpf_chop_{timeframe}_reversal_rate_l{lookback}_bnd",
                    f"rpf_chop_{timeframe}_path_eff_l{lookback}_bnd",
                    f"rpf_chop_{timeframe}_path_chop_l{lookback}_bnd",
                    f"rpf_chop_{timeframe}_failed_up_break_l{lookback}_bnd",
                    f"rpf_chop_{timeframe}_failed_down_break_l{lookback}_bnd",
                    f"rpf_chop_{timeframe}_failed_break_balance_l{lookback}_bnd",
                ]
            )
    return tuple(columns)


def enrich_rejection_chop_sources(
    bars: pl.DataFrame,
    *,
    lookbacks: tuple[int, ...] = DEFAULT_CHOP_LOOKBACKS,
) -> pl.DataFrame:
    """Add rolling rejection/chop source columns to canonical bars."""

    required = {"timestamp", "open", "high", "low", "close"}
    missing = required - set(bars.columns)
    if missing:
        raise ValueError(f"Rejection/chop source bars missing columns: {sorted(missing)}")

    out = bars.sort("timestamp").with_columns(
        [
            pl.col("open").cast(pl.Float64),
            pl.col("high").cast(pl.Float64),
            pl.col("low").cast(pl.Float64),
            pl.col("close").cast(pl.Float64),
            (pl.col("high").cast(pl.Float64) - pl.col("low").cast(pl.Float64)).alias("_rpf_chop_range"),
        ]
    )
    out = out.with_columns(
        [
            bounded_expr(
                safe_div_expr(
                    pl.col("high") - pl.max_horizontal("open", "close"),
                    pl.col("_rpf_chop_range"),
                ),
                lower=0.0,
                upper=1.0,
            ).alias("_rpf_chop_upper_wick"),
            bounded_expr(
                safe_div_expr(
                    pl.min_horizontal("open", "close") - pl.col("low"),
                    pl.col("_rpf_chop_range"),
                ),
                lower=0.0,
                upper=1.0,
            ).alias("_rpf_chop_lower_wick"),
            pct_change_expr(pl.col("close"), pl.col("close").shift(1)).alias("_rpf_chop_ret_pct"),
        ]
    )
    out = out.with_columns(
        [
            pl.when(pl.col("_rpf_chop_ret_pct") > 0)
            .then(1.0)
            .when(pl.col("_rpf_chop_ret_pct") < 0)
            .then(-1.0)
            .otherwise(0.0)
            .alias("_rpf_chop_ret_sign"),
            pl.col("_rpf_chop_ret_pct").abs().alias("_rpf_chop_abs_ret"),
        ]
    )
    out = out.with_columns(
        [
            pl.when(
                (pl.col("_rpf_chop_ret_sign") != 0.0)
                & (pl.col("_rpf_chop_ret_sign").shift(1) != 0.0)
                & (pl.col("_rpf_chop_ret_sign") != pl.col("_rpf_chop_ret_sign").shift(1))
            )
            .then(1.0)
            .otherwise(0.0)
            .alias("_rpf_chop_reversal"),
        ]
    )

    for lookback in lookbacks:
        min_samples = min(int(lookback), max(2, int(lookback) // 4))
        prior_high_col = f"_rpf_chop_prior_high_l{lookback}"
        prior_low_col = f"_rpf_chop_prior_low_l{lookback}"
        prior_close_col = f"_rpf_chop_prior_close_l{lookback}"
        path_col = f"_rpf_chop_path_l{lookback}"
        net_col = f"_rpf_chop_net_l{lookback}"
        return_persist_col = f"_rpf_chop_return_persist_l{lookback}"
        failed_up_col = f"_rpf_chop_failed_up_l{lookback}"
        failed_down_col = f"_rpf_chop_failed_down_l{lookback}"

        out = out.with_columns(
            [
                pl.col("high")
                .shift(1)
                .rolling_max(window_size=int(lookback), min_samples=min_samples)
                .alias(prior_high_col),
                pl.col("low")
                .shift(1)
                .rolling_min(window_size=int(lookback), min_samples=min_samples)
                .alias(prior_low_col),
                pl.col("close").shift(int(lookback)).alias(prior_close_col),
                pl.col("_rpf_chop_abs_ret")
                .rolling_sum(window_size=int(lookback), min_samples=min_samples)
                .alias(path_col),
                pl.col("_rpf_chop_ret_sign")
                .rolling_mean(window_size=int(lookback), min_samples=min_samples)
                .fill_null(0.0)
                .alias(return_persist_col),
            ]
        )
        out = out.with_columns(
            [
                pct_change_expr(pl.col("close"), pl.col(prior_close_col)).alias(net_col),
                (
                    (pl.col("high") > pl.col(prior_high_col))
                    & (pl.col("close") <= pl.col(prior_high_col))
                )
                .cast(pl.Float64)
                .fill_null(0.0)
                .alias(failed_up_col),
                (
                    (pl.col("low") < pl.col(prior_low_col))
                    & (pl.col("close") >= pl.col(prior_low_col))
                )
                .cast(pl.Float64)
                .fill_null(0.0)
                .alias(failed_down_col),
            ]
        )
        path_eff = bounded_expr(
            safe_div_expr(pl.col(net_col).abs(), pl.col(path_col)),
            lower=0.0,
            upper=1.0,
        )
        out = out.with_columns(
            [
                pl.col("_rpf_chop_upper_wick")
                .rolling_mean(window_size=int(lookback), min_samples=min_samples)
                .fill_null(0.0)
                .alias(f"{SOURCE_PREFIX}upper_reject_l{lookback}"),
                pl.col("_rpf_chop_lower_wick")
                .rolling_mean(window_size=int(lookback), min_samples=min_samples)
                .fill_null(0.0)
                .alias(f"{SOURCE_PREFIX}lower_reject_l{lookback}"),
                (
                    pl.col("_rpf_chop_upper_wick").rolling_mean(window_size=int(lookback), min_samples=min_samples)
                    - pl.col("_rpf_chop_lower_wick").rolling_mean(window_size=int(lookback), min_samples=min_samples)
                )
                .clip(-1.0, 1.0)
                .fill_null(0.0)
                .alias(f"{SOURCE_PREFIX}reject_balance_l{lookback}"),
                (1.0 - pl.col(return_persist_col).abs())
                .clip(0.0, 1.0)
                .fill_null(0.0)
                .alias(f"{SOURCE_PREFIX}two_sided_l{lookback}"),
                pl.col("_rpf_chop_reversal")
                .rolling_mean(window_size=int(lookback), min_samples=min_samples)
                .fill_null(0.0)
                .alias(f"{SOURCE_PREFIX}reversal_rate_l{lookback}"),
                path_eff.fill_null(0.0).alias(f"{SOURCE_PREFIX}path_eff_l{lookback}"),
                (1.0 - path_eff)
                .clip(0.0, 1.0)
                .fill_null(0.0)
                .alias(f"{SOURCE_PREFIX}path_chop_l{lookback}"),
                pl.col(failed_up_col)
                .rolling_mean(window_size=int(lookback), min_samples=min_samples)
                .fill_null(0.0)
                .alias(f"{SOURCE_PREFIX}failed_up_break_l{lookback}"),
                pl.col(failed_down_col)
                .rolling_mean(window_size=int(lookback), min_samples=min_samples)
                .fill_null(0.0)
                .alias(f"{SOURCE_PREFIX}failed_down_break_l{lookback}"),
                (
                    pl.col(failed_up_col).rolling_mean(window_size=int(lookback), min_samples=min_samples)
                    - pl.col(failed_down_col).rolling_mean(window_size=int(lookback), min_samples=min_samples)
                )
                .clip(-1.0, 1.0)
                .fill_null(0.0)
                .alias(f"{SOURCE_PREFIX}failed_break_balance_l{lookback}"),
            ]
        )

    keep_source_cols = set(source_columns(lookbacks=lookbacks))
    return out.drop(
        [
            col
            for col in out.columns
            if col.startswith("_rpf_chop_") and col not in keep_source_cols
        ]
    )


def add_rejection_chop_features(
    df: pl.DataFrame,
    *,
    timeframes: tuple[str, ...],
    lookbacks: tuple[int, ...] = DEFAULT_CHOP_LOOKBACKS,
) -> pl.DataFrame:
    """Add model-facing rejection/chop features from aligned source columns."""

    out = df
    for timeframe in timeframes:
        src = source_prefix(timeframe)
        for lookback in lookbacks:
            for suffix in (
                "upper_reject",
                "lower_reject",
                "reject_balance",
                "two_sided",
                "reversal_rate",
                "path_eff",
                "path_chop",
                "failed_up_break",
                "failed_down_break",
                "failed_break_balance",
            ):
                source_col = f"{src}{SOURCE_PREFIX}{suffix}_l{lookback}"
                if source_col not in out.columns:
                    raise ValueError(f"Missing rejection/chop row source column: {source_col}")
                out = out.with_columns(
                    pl.col(source_col)
                    .cast(pl.Float64)
                    .fill_null(0.0)
                    .alias(f"rpf_chop_{timeframe}_{suffix}_l{lookback}_bnd")
                )
    return out


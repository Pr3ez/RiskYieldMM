"""Acceptance and path-persistence feature family.

This family targets directional staying power rather than static room. Source
statistics are computed on canonical bars that are later joined with the
closed-bar as-of contract, so no forming higher-timeframe candle is exposed to
the 1m prediction rows.
"""

from __future__ import annotations

import polars as pl

from regression_feature_engineering.core.alignment import align_prefix, source_prefix
from regression_feature_engineering.core.math import (
    bounded_expr,
    pct_change_expr,
    positive_part_expr,
    safe_div_expr,
    signed_vol_unit_bnd_expr,
)


FEATURE_FAMILY = "acceptance_persistence"
TARGET_INTENT = (
    "target_reg_distance_up_mean_high_hvol_v2",
    "target_reg_distance_down_mean_low_hvol_v2",
    "sustained_path_pressure",
    "directional_acceptance",
)
DEFAULT_ACCEPT_LOOKBACKS: tuple[int, ...] = (4, 16, 48)
SOURCE_PREFIX = "_rpf_accept_"


def source_columns(*, lookbacks: tuple[int, ...] = DEFAULT_ACCEPT_LOOKBACKS) -> tuple[str, ...]:
    """Return acceptance source columns produced on canonical bars."""

    columns: list[str] = []
    for lookback in lookbacks:
        columns.extend(
            [
                f"{SOURCE_PREFIX}close_loc_avg_l{lookback}",
                f"{SOURCE_PREFIX}close_loc_balance_l{lookback}",
                f"{SOURCE_PREFIX}body_persist_l{lookback}",
                f"{SOURCE_PREFIX}return_persist_l{lookback}",
                f"{SOURCE_PREFIX}above_value_share_l{lookback}",
                f"{SOURCE_PREFIX}below_value_share_l{lookback}",
                f"{SOURCE_PREFIX}value_accept_balance_l{lookback}",
                f"{SOURCE_PREFIX}value_l{lookback}",
                f"{SOURCE_PREFIX}trend_eff_l{lookback}",
                f"{SOURCE_PREFIX}up_pullback_shallow_l{lookback}",
                f"{SOURCE_PREFIX}down_pullback_shallow_l{lookback}",
            ]
        )
    return tuple(columns)


def feature_columns(
    *,
    timeframes: tuple[str, ...],
    lookbacks: tuple[int, ...] = DEFAULT_ACCEPT_LOOKBACKS,
) -> tuple[str, ...]:
    """Return the model-facing acceptance/persistence feature columns."""

    columns: list[str] = []
    for timeframe in timeframes:
        for lookback in lookbacks:
            columns.extend(
                [
                    f"rpf_accept_{timeframe}_close_loc_avg_l{lookback}_bnd",
                    f"rpf_accept_{timeframe}_close_loc_balance_l{lookback}_bnd",
                    f"rpf_accept_{timeframe}_body_persist_l{lookback}_bnd",
                    f"rpf_accept_{timeframe}_return_persist_l{lookback}_bnd",
                    f"rpf_accept_{timeframe}_above_value_share_l{lookback}_bnd",
                    f"rpf_accept_{timeframe}_below_value_share_l{lookback}_bnd",
                    f"rpf_accept_{timeframe}_value_accept_balance_l{lookback}_bnd",
                    f"rpf_accept_{timeframe}_value_dist_l{lookback}_vol",
                    f"rpf_accept_{timeframe}_trend_eff_l{lookback}_bnd",
                    f"rpf_accept_{timeframe}_up_pullback_shallow_l{lookback}_bnd",
                    f"rpf_accept_{timeframe}_down_pullback_shallow_l{lookback}_bnd",
                ]
            )
    columns.extend(
        [
            "rpf_accept_tf_bull_agreement_share_bnd",
            "rpf_accept_tf_bear_agreement_share_bnd",
            "rpf_accept_tf_direction_agreement_bnd",
        ]
    )
    return tuple(columns)


def enrich_acceptance_persistence_sources(
    bars: pl.DataFrame,
    *,
    lookbacks: tuple[int, ...] = DEFAULT_ACCEPT_LOOKBACKS,
) -> pl.DataFrame:
    """Add rolling acceptance/persistence source columns to canonical bars."""

    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = required - set(bars.columns)
    if missing:
        raise ValueError(f"Acceptance source bars missing columns: {sorted(missing)}")

    out = bars.sort("timestamp").with_columns(
        [
            pl.col("open").cast(pl.Float64),
            pl.col("high").cast(pl.Float64),
            pl.col("low").cast(pl.Float64),
            pl.col("close").cast(pl.Float64),
            (pl.col("high").cast(pl.Float64) - pl.col("low").cast(pl.Float64)).alias("_rpf_accept_range"),
            ((pl.col("high").cast(pl.Float64) + pl.col("low").cast(pl.Float64) + pl.col("close").cast(pl.Float64)) / 3.0).alias(
                "_rpf_accept_typical"
            ),
        ]
    )
    out = out.with_columns(
        [
            bounded_expr(
                safe_div_expr(pl.col("close") - pl.col("low"), pl.col("_rpf_accept_range"), default=0.5),
                lower=0.0,
                upper=1.0,
            ).alias("_rpf_accept_close_loc"),
            bounded_expr(
                safe_div_expr(pl.col("close") - pl.col("open"), pl.col("_rpf_accept_range")),
                lower=-1.0,
                upper=1.0,
            ).alias("_rpf_accept_body_signed"),
            pct_change_expr(pl.col("close"), pl.col("close").shift(1)).alias("_rpf_accept_ret_pct"),
        ]
    )
    out = out.with_columns(
        [
            pl.when(pl.col("_rpf_accept_ret_pct") > 0)
            .then(1.0)
            .when(pl.col("_rpf_accept_ret_pct") < 0)
            .then(-1.0)
            .otherwise(0.0)
            .alias("_rpf_accept_ret_sign"),
            pl.col("_rpf_accept_ret_pct").abs().alias("_rpf_accept_abs_ret"),
        ]
    )

    for lookback in lookbacks:
        min_samples = min(int(lookback), max(2, int(lookback) // 4))
        value_col = f"{SOURCE_PREFIX}value_l{lookback}"
        above_col = f"_rpf_accept_above_value_l{lookback}"
        below_col = f"_rpf_accept_below_value_l{lookback}"
        prior_close_col = f"_rpf_accept_prior_close_l{lookback}"
        path_col = f"_rpf_accept_path_l{lookback}"
        net_col = f"_rpf_accept_net_l{lookback}"
        high_col = f"_rpf_accept_high_l{lookback}"
        low_col = f"_rpf_accept_low_l{lookback}"
        up_progress_col = f"_rpf_accept_up_progress_l{lookback}"
        down_progress_col = f"_rpf_accept_down_progress_l{lookback}"
        up_adverse_col = f"_rpf_accept_up_adverse_l{lookback}"
        down_adverse_col = f"_rpf_accept_down_adverse_l{lookback}"

        out = out.with_columns(
            [
                pl.col("_rpf_accept_typical")
                .shift(1)
                .rolling_mean(window_size=int(lookback), min_samples=min_samples)
                .alias(value_col),
                pl.col("close").shift(int(lookback)).alias(prior_close_col),
                pl.col("_rpf_accept_abs_ret")
                .rolling_sum(window_size=int(lookback), min_samples=min_samples)
                .alias(path_col),
                pl.col("high")
                .rolling_max(window_size=int(lookback), min_samples=min_samples)
                .alias(high_col),
                pl.col("low")
                .rolling_min(window_size=int(lookback), min_samples=min_samples)
                .alias(low_col),
            ]
        )
        out = out.with_columns(
            [
                (pl.col("close") > pl.col(value_col)).cast(pl.Float64).fill_null(0.0).alias(above_col),
                (pl.col("close") < pl.col(value_col)).cast(pl.Float64).fill_null(0.0).alias(below_col),
                pct_change_expr(pl.col("close"), pl.col(prior_close_col)).alias(net_col),
                safe_div_expr(positive_part_expr(pl.col("close") - pl.col(prior_close_col)), pl.col(prior_close_col)).alias(
                    up_progress_col
                ),
                safe_div_expr(positive_part_expr(pl.col(prior_close_col) - pl.col("close")), pl.col(prior_close_col)).alias(
                    down_progress_col
                ),
                safe_div_expr(positive_part_expr(pl.col(prior_close_col) - pl.col(low_col)), pl.col(prior_close_col)).alias(
                    up_adverse_col
                ),
                safe_div_expr(positive_part_expr(pl.col(high_col) - pl.col(prior_close_col)), pl.col(prior_close_col)).alias(
                    down_adverse_col
                ),
            ]
        )
        out = out.with_columns(
            [
                pl.col("_rpf_accept_close_loc")
                .rolling_mean(window_size=int(lookback), min_samples=min_samples)
                .fill_null(0.5)
                .alias(f"{SOURCE_PREFIX}close_loc_avg_l{lookback}"),
                ((pl.col("_rpf_accept_close_loc").rolling_mean(window_size=int(lookback), min_samples=min_samples) * 2.0) - 1.0)
                .clip(-1.0, 1.0)
                .fill_null(0.0)
                .alias(f"{SOURCE_PREFIX}close_loc_balance_l{lookback}"),
                pl.col("_rpf_accept_body_signed")
                .rolling_mean(window_size=int(lookback), min_samples=min_samples)
                .clip(-1.0, 1.0)
                .fill_null(0.0)
                .alias(f"{SOURCE_PREFIX}body_persist_l{lookback}"),
                pl.col("_rpf_accept_ret_sign")
                .rolling_mean(window_size=int(lookback), min_samples=min_samples)
                .clip(-1.0, 1.0)
                .fill_null(0.0)
                .alias(f"{SOURCE_PREFIX}return_persist_l{lookback}"),
                pl.col(above_col)
                .rolling_mean(window_size=int(lookback), min_samples=min_samples)
                .fill_null(0.0)
                .alias(f"{SOURCE_PREFIX}above_value_share_l{lookback}"),
                pl.col(below_col)
                .rolling_mean(window_size=int(lookback), min_samples=min_samples)
                .fill_null(0.0)
                .alias(f"{SOURCE_PREFIX}below_value_share_l{lookback}"),
                (
                    pl.col(above_col).rolling_mean(window_size=int(lookback), min_samples=min_samples)
                    - pl.col(below_col).rolling_mean(window_size=int(lookback), min_samples=min_samples)
                )
                .clip(-1.0, 1.0)
                .fill_null(0.0)
                .alias(f"{SOURCE_PREFIX}value_accept_balance_l{lookback}"),
                bounded_expr(safe_div_expr(pl.col(net_col), pl.col(path_col)), lower=-1.0, upper=1.0)
                .fill_null(0.0)
                .alias(f"{SOURCE_PREFIX}trend_eff_l{lookback}"),
                bounded_expr(
                    safe_div_expr(pl.col(up_progress_col), pl.col(up_progress_col) + pl.col(up_adverse_col)),
                    lower=0.0,
                    upper=1.0,
                )
                .fill_null(0.0)
                .alias(f"{SOURCE_PREFIX}up_pullback_shallow_l{lookback}"),
                bounded_expr(
                    safe_div_expr(pl.col(down_progress_col), pl.col(down_progress_col) + pl.col(down_adverse_col)),
                    lower=0.0,
                    upper=1.0,
                )
                .fill_null(0.0)
                .alias(f"{SOURCE_PREFIX}down_pullback_shallow_l{lookback}"),
            ]
        )

    keep_source_cols = set(source_columns(lookbacks=lookbacks))
    return out.drop(
        [
            col
            for col in out.columns
            if col.startswith("_rpf_accept_") and col not in keep_source_cols
        ]
    )


def add_acceptance_persistence_features(
    df: pl.DataFrame,
    *,
    timeframes: tuple[str, ...],
    lookbacks: tuple[int, ...] = DEFAULT_ACCEPT_LOOKBACKS,
) -> pl.DataFrame:
    """Add model-facing acceptance/persistence features from aligned sources."""

    required = {"close", "tb_volatility_pct"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing acceptance row source columns: {sorted(missing)}")

    out = df.with_columns(
        [
            pl.col("close").cast(pl.Float64).alias("_rpf_accept_row_close"),
            pl.col("tb_volatility_pct").cast(pl.Float64).alias("_rpf_accept_row_vol"),
        ]
    )

    for timeframe in timeframes:
        src = source_prefix(timeframe)
        for lookback in lookbacks:
            value = pl.col(f"{src}{SOURCE_PREFIX}value_l{lookback}")
            value_dist_pct = safe_div_expr(pl.col("_rpf_accept_row_close") - value, pl.col("_rpf_accept_row_close"))
            out = out.with_columns(
                [
                    pl.col(f"{src}{SOURCE_PREFIX}close_loc_avg_l{lookback}")
                    .fill_null(0.5)
                    .alias(f"rpf_accept_{timeframe}_close_loc_avg_l{lookback}_bnd"),
                    pl.col(f"{src}{SOURCE_PREFIX}close_loc_balance_l{lookback}")
                    .fill_null(0.0)
                    .alias(f"rpf_accept_{timeframe}_close_loc_balance_l{lookback}_bnd"),
                    pl.col(f"{src}{SOURCE_PREFIX}body_persist_l{lookback}")
                    .fill_null(0.0)
                    .alias(f"rpf_accept_{timeframe}_body_persist_l{lookback}_bnd"),
                    pl.col(f"{src}{SOURCE_PREFIX}return_persist_l{lookback}")
                    .fill_null(0.0)
                    .alias(f"rpf_accept_{timeframe}_return_persist_l{lookback}_bnd"),
                    pl.col(f"{src}{SOURCE_PREFIX}above_value_share_l{lookback}")
                    .fill_null(0.0)
                    .alias(f"rpf_accept_{timeframe}_above_value_share_l{lookback}_bnd"),
                    pl.col(f"{src}{SOURCE_PREFIX}below_value_share_l{lookback}")
                    .fill_null(0.0)
                    .alias(f"rpf_accept_{timeframe}_below_value_share_l{lookback}_bnd"),
                    pl.col(f"{src}{SOURCE_PREFIX}value_accept_balance_l{lookback}")
                    .fill_null(0.0)
                    .alias(f"rpf_accept_{timeframe}_value_accept_balance_l{lookback}_bnd"),
                    signed_vol_unit_bnd_expr(safe_div_expr(value_dist_pct, pl.col("_rpf_accept_row_vol")))
                    .alias(f"rpf_accept_{timeframe}_value_dist_l{lookback}_vol"),
                    pl.col(f"{src}{SOURCE_PREFIX}trend_eff_l{lookback}")
                    .fill_null(0.0)
                    .alias(f"rpf_accept_{timeframe}_trend_eff_l{lookback}_bnd"),
                    pl.col(f"{src}{SOURCE_PREFIX}up_pullback_shallow_l{lookback}")
                    .fill_null(0.0)
                    .alias(f"rpf_accept_{timeframe}_up_pullback_shallow_l{lookback}_bnd"),
                    pl.col(f"{src}{SOURCE_PREFIX}down_pullback_shallow_l{lookback}")
                    .fill_null(0.0)
                    .alias(f"rpf_accept_{timeframe}_down_pullback_shallow_l{lookback}_bnd"),
                ]
            )

    out = out.with_columns(_timeframe_agreement_exprs(timeframes))
    return out.drop(["_rpf_accept_row_close", "_rpf_accept_row_vol"])


def _timeframe_agreement_exprs(timeframes: tuple[str, ...]) -> list[pl.Expr]:
    bull_exprs: list[pl.Expr] = []
    bear_exprs: list[pl.Expr] = []
    closed_exprs: list[pl.Expr] = []
    for timeframe in timeframes:
        src = source_prefix(timeframe)
        has_col = f"{align_prefix(timeframe)}has_closed_bar"
        open_col = pl.col(f"{src}open")
        close_col = pl.col(f"{src}close")
        has_closed = pl.col(has_col).fill_null(False)
        bull_exprs.append(pl.when(has_closed & (close_col > open_col)).then(1.0).otherwise(0.0))
        bear_exprs.append(pl.when(has_closed & (close_col < open_col)).then(1.0).otherwise(0.0))
        closed_exprs.append(pl.when(has_closed).then(1.0).otherwise(0.0))

    bull_count = pl.sum_horizontal(bull_exprs)
    bear_count = pl.sum_horizontal(bear_exprs)
    closed_count = pl.sum_horizontal(closed_exprs)
    return [
        bounded_expr(safe_div_expr(bull_count, closed_count), lower=0.0, upper=1.0)
        .fill_null(0.0)
        .alias("rpf_accept_tf_bull_agreement_share_bnd"),
        bounded_expr(safe_div_expr(bear_count, closed_count), lower=0.0, upper=1.0)
        .fill_null(0.0)
        .alias("rpf_accept_tf_bear_agreement_share_bnd"),
        bounded_expr(safe_div_expr(bull_count - bear_count, closed_count), lower=-1.0, upper=1.0)
        .fill_null(0.0)
        .alias("rpf_accept_tf_direction_agreement_bnd"),
    ]

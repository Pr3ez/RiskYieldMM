"""Liquidity and volume-pressure feature family.

This family describes whether closed-bar movement has real participation
behind it. It uses only local OHLCV-derived proxies, keeps every model-facing
output normalized, and treats zero-volume rows as explicit information instead
of an error.
"""

from __future__ import annotations

import polars as pl

from regression_feature_engineering.core.alignment import source_prefix
from regression_feature_engineering.core.math import bounded_expr, pct_change_expr, safe_div_expr


FEATURE_FAMILY = "liquidity_volume_pressure"
TARGET_INTENT = (
    "all_targets",
    "participation",
    "volume_confirmed_pressure",
    "volume_wakeup_after_compression",
)
DEFAULT_LIQ_LOOKBACKS: tuple[int, ...] = (4, 16, 48)
SOURCE_PREFIX = "_rpf_liq_"


def source_columns(*, lookbacks: tuple[int, ...] = DEFAULT_LIQ_LOOKBACKS) -> tuple[str, ...]:
    """Return liquidity/volume source columns produced on canonical bars."""

    columns: list[str] = []
    for lookback in lookbacks:
        columns.extend(
            [
                f"{SOURCE_PREFIX}volume_z_l{lookback}",
                f"{SOURCE_PREFIX}dollar_volume_rel_l{lookback}",
                f"{SOURCE_PREFIX}volume_wakeup_l{lookback}",
                f"{SOURCE_PREFIX}up_volume_share_l{lookback}",
                f"{SOURCE_PREFIX}down_volume_share_l{lookback}",
                f"{SOURCE_PREFIX}volume_pressure_balance_l{lookback}",
                f"{SOURCE_PREFIX}obv_slope_l{lookback}",
                f"{SOURCE_PREFIX}money_flow_balance_l{lookback}",
                f"{SOURCE_PREFIX}zero_volume_share_l{lookback}",
            ]
        )
    return tuple(columns)


def feature_columns(
    *,
    timeframes: tuple[str, ...],
    lookbacks: tuple[int, ...] = DEFAULT_LIQ_LOOKBACKS,
) -> tuple[str, ...]:
    """Return model-facing liquidity/volume-pressure feature columns."""

    columns: list[str] = []
    for timeframe in timeframes:
        for lookback in lookbacks:
            columns.extend(
                [
                    f"rpf_liq_{timeframe}_volume_z_l{lookback}",
                    f"rpf_liq_{timeframe}_dollar_volume_rel_l{lookback}_bnd",
                    f"rpf_liq_{timeframe}_volume_wakeup_l{lookback}_bnd",
                    f"rpf_liq_{timeframe}_up_volume_share_l{lookback}_bnd",
                    f"rpf_liq_{timeframe}_down_volume_share_l{lookback}_bnd",
                    f"rpf_liq_{timeframe}_volume_pressure_balance_l{lookback}_bnd",
                    f"rpf_liq_{timeframe}_obv_slope_l{lookback}_bnd",
                    f"rpf_liq_{timeframe}_money_flow_balance_l{lookback}_bnd",
                    f"rpf_liq_{timeframe}_zero_volume_share_l{lookback}_bnd",
                ]
            )
    return tuple(columns)


def enrich_liquidity_volume_pressure_sources(
    bars: pl.DataFrame,
    *,
    lookbacks: tuple[int, ...] = DEFAULT_LIQ_LOOKBACKS,
) -> pl.DataFrame:
    """Add rolling liquidity/volume-pressure source columns to canonical bars."""

    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = required - set(bars.columns)
    if missing:
        raise ValueError(f"Liquidity/volume source bars missing columns: {sorted(missing)}")

    out = bars.sort("timestamp").with_columns(
        [
            pl.col("open").cast(pl.Float64),
            pl.col("high").cast(pl.Float64),
            pl.col("low").cast(pl.Float64),
            pl.col("close").cast(pl.Float64),
            pl.col("volume").cast(pl.Float64).clip(0.0, None).fill_null(0.0).alias("_rpf_liq_volume"),
            (pl.col("high").cast(pl.Float64) - pl.col("low").cast(pl.Float64)).alias("_rpf_liq_range"),
        ]
    )
    out = out.with_columns(
        [
            ((pl.col("high") + pl.col("low") + pl.col("close")) / 3.0).alias("_rpf_liq_typical_price"),
            safe_div_expr(pl.col("_rpf_liq_range"), pl.col("close")).alias("_rpf_liq_range_pct"),
            pct_change_expr(pl.col("close"), pl.col("close").shift(1)).alias("_rpf_liq_ret_pct"),
            bounded_expr(
                safe_div_expr(
                    (2.0 * pl.col("close")) - pl.col("high") - pl.col("low"),
                    pl.col("_rpf_liq_range"),
                ),
                lower=-1.0,
                upper=1.0,
            ).alias("_rpf_liq_money_flow_mult"),
        ]
    )
    out = out.with_columns(
        [
            pl.when(pl.col("_rpf_liq_ret_pct") > 0.0)
            .then(1.0)
            .when(pl.col("_rpf_liq_ret_pct") < 0.0)
            .then(-1.0)
            .otherwise(0.0)
            .alias("_rpf_liq_ret_sign"),
            (pl.col("_rpf_liq_typical_price").abs() * pl.col("_rpf_liq_volume"))
            .fill_null(0.0)
            .alias("_rpf_liq_dollar_volume"),
            (pl.col("_rpf_liq_volume") <= 0.0).cast(pl.Float64).alias("_rpf_liq_zero_volume"),
        ]
    )
    out = out.with_columns(
        [
            pl.when(pl.col("_rpf_liq_ret_sign") > 0.0)
            .then(pl.col("_rpf_liq_volume"))
            .otherwise(0.0)
            .alias("_rpf_liq_up_volume"),
            pl.when(pl.col("_rpf_liq_ret_sign") < 0.0)
            .then(pl.col("_rpf_liq_volume"))
            .otherwise(0.0)
            .alias("_rpf_liq_down_volume"),
            (pl.col("_rpf_liq_ret_sign") * pl.col("_rpf_liq_volume")).alias("_rpf_liq_obv_step"),
            (pl.col("_rpf_liq_money_flow_mult") * pl.col("_rpf_liq_volume")).alias("_rpf_liq_money_flow_volume"),
        ]
    )

    for lookback in lookbacks:
        lookback = int(lookback)
        min_samples = min(lookback, max(2, lookback // 4))
        prior_volume_mean = f"_rpf_liq_prior_volume_mean_l{lookback}"
        prior_volume_std = f"_rpf_liq_prior_volume_std_l{lookback}"
        prior_dollar_median = f"_rpf_liq_prior_dollar_median_l{lookback}"
        prior_range_median = f"_rpf_liq_prior_range_median_l{lookback}"
        volume_total = f"_rpf_liq_volume_total_l{lookback}"
        up_volume_total = f"_rpf_liq_up_volume_total_l{lookback}"
        down_volume_total = f"_rpf_liq_down_volume_total_l{lookback}"
        obv_total = f"_rpf_liq_obv_total_l{lookback}"
        money_flow_total = f"_rpf_liq_money_flow_total_l{lookback}"
        volume_rel_raw = f"_rpf_liq_volume_rel_raw_l{lookback}"
        dollar_rel_raw = f"_rpf_liq_dollar_rel_raw_l{lookback}"
        range_rel_raw = f"_rpf_liq_range_rel_raw_l{lookback}"

        out = out.with_columns(
            [
                pl.col("_rpf_liq_volume")
                .shift(1)
                .rolling_mean(window_size=lookback, min_samples=min_samples)
                .alias(prior_volume_mean),
                pl.col("_rpf_liq_volume")
                .shift(1)
                .rolling_std(window_size=lookback, min_samples=min_samples)
                .alias(prior_volume_std),
                pl.col("_rpf_liq_dollar_volume")
                .shift(1)
                .rolling_median(window_size=lookback, min_samples=min_samples)
                .alias(prior_dollar_median),
                pl.col("_rpf_liq_range_pct")
                .shift(1)
                .rolling_median(window_size=lookback, min_samples=min_samples)
                .alias(prior_range_median),
                pl.col("_rpf_liq_volume")
                .rolling_sum(window_size=lookback, min_samples=min_samples)
                .alias(volume_total),
                pl.col("_rpf_liq_up_volume")
                .rolling_sum(window_size=lookback, min_samples=min_samples)
                .alias(up_volume_total),
                pl.col("_rpf_liq_down_volume")
                .rolling_sum(window_size=lookback, min_samples=min_samples)
                .alias(down_volume_total),
                pl.col("_rpf_liq_obv_step")
                .rolling_sum(window_size=lookback, min_samples=min_samples)
                .alias(obv_total),
                pl.col("_rpf_liq_money_flow_volume")
                .rolling_sum(window_size=lookback, min_samples=min_samples)
                .alias(money_flow_total),
            ]
        )
        out = out.with_columns(
            [
                safe_div_expr(pl.col("_rpf_liq_volume"), pl.col(prior_volume_mean), default=0.0).alias(volume_rel_raw),
                safe_div_expr(pl.col("_rpf_liq_dollar_volume"), pl.col(prior_dollar_median), default=0.0).alias(dollar_rel_raw),
                safe_div_expr(pl.col("_rpf_liq_range_pct"), pl.col(prior_range_median), default=0.0).alias(range_rel_raw),
            ]
        )
        out = out.with_columns(
            [
                safe_div_expr(
                    pl.col("_rpf_liq_volume") - pl.col(prior_volume_mean),
                    pl.col(prior_volume_std),
                    default=0.0,
                )
                .clip(-8.0, 8.0)
                .fill_null(0.0)
                .alias(f"{SOURCE_PREFIX}volume_z_l{lookback}"),
                bounded_expr(
                    safe_div_expr(pl.col(dollar_rel_raw), 1.0 + pl.col(dollar_rel_raw), default=0.0),
                    lower=0.0,
                    upper=1.0,
                )
                .fill_null(0.0)
                .alias(f"{SOURCE_PREFIX}dollar_volume_rel_l{lookback}"),
                (
                    bounded_expr(
                        safe_div_expr(pl.col(volume_rel_raw), 1.0 + pl.col(volume_rel_raw), default=0.0),
                        lower=0.0,
                        upper=1.0,
                    )
                    * bounded_expr(
                        safe_div_expr(pl.col(range_rel_raw), 1.0 + pl.col(range_rel_raw), default=0.0),
                        lower=0.0,
                        upper=1.0,
                    )
                )
                .fill_null(0.0)
                .alias(f"{SOURCE_PREFIX}volume_wakeup_l{lookback}"),
                bounded_expr(
                    safe_div_expr(pl.col(up_volume_total), pl.col(volume_total), default=0.0),
                    lower=0.0,
                    upper=1.0,
                )
                .fill_null(0.0)
                .alias(f"{SOURCE_PREFIX}up_volume_share_l{lookback}"),
                bounded_expr(
                    safe_div_expr(pl.col(down_volume_total), pl.col(volume_total), default=0.0),
                    lower=0.0,
                    upper=1.0,
                )
                .fill_null(0.0)
                .alias(f"{SOURCE_PREFIX}down_volume_share_l{lookback}"),
                bounded_expr(
                    safe_div_expr(pl.col(obv_total), pl.col(volume_total), default=0.0),
                    lower=-1.0,
                    upper=1.0,
                )
                .fill_null(0.0)
                .alias(f"{SOURCE_PREFIX}obv_slope_l{lookback}"),
                bounded_expr(
                    safe_div_expr(pl.col(money_flow_total), pl.col(volume_total), default=0.0),
                    lower=-1.0,
                    upper=1.0,
                )
                .fill_null(0.0)
                .alias(f"{SOURCE_PREFIX}money_flow_balance_l{lookback}"),
                pl.col("_rpf_liq_zero_volume")
                .rolling_mean(window_size=lookback, min_samples=min_samples)
                .fill_null(0.0)
                .clip(0.0, 1.0)
                .alias(f"{SOURCE_PREFIX}zero_volume_share_l{lookback}"),
            ]
        )
        out = out.with_columns(
            (
                pl.col(f"{SOURCE_PREFIX}up_volume_share_l{lookback}")
                - pl.col(f"{SOURCE_PREFIX}down_volume_share_l{lookback}")
            )
            .clip(-1.0, 1.0)
            .fill_null(0.0)
            .alias(f"{SOURCE_PREFIX}volume_pressure_balance_l{lookback}")
        )

    keep_source_cols = set(source_columns(lookbacks=lookbacks))
    return out.drop(
        [
            col
            for col in out.columns
            if col.startswith("_rpf_liq_") and col not in keep_source_cols
        ]
    )


def add_liquidity_volume_pressure_features(
    df: pl.DataFrame,
    *,
    timeframes: tuple[str, ...],
    lookbacks: tuple[int, ...] = DEFAULT_LIQ_LOOKBACKS,
) -> pl.DataFrame:
    """Add model-facing liquidity/volume-pressure features from aligned sources."""

    out = df
    for timeframe in timeframes:
        src = source_prefix(timeframe)
        for lookback in lookbacks:
            for suffix, bounded in (
                ("volume_z", False),
                ("dollar_volume_rel", True),
                ("volume_wakeup", True),
                ("up_volume_share", True),
                ("down_volume_share", True),
                ("volume_pressure_balance", True),
                ("obv_slope", True),
                ("money_flow_balance", True),
                ("zero_volume_share", True),
            ):
                source_col = f"{src}{SOURCE_PREFIX}{suffix}_l{lookback}"
                if source_col not in out.columns:
                    raise ValueError(f"Missing liquidity/volume row source column: {source_col}")
                feature = pl.col(source_col).cast(pl.Float64).fill_null(0.0)
                if suffix == "volume_z":
                    feature = feature.clip(-8.0, 8.0)
                    name = f"rpf_liq_{timeframe}_{suffix}_l{lookback}"
                else:
                    lower = -1.0 if suffix in {"volume_pressure_balance", "obv_slope", "money_flow_balance"} else 0.0
                    feature = feature.clip(lower, 1.0)
                    name = f"rpf_liq_{timeframe}_{suffix}_l{lookback}_bnd"
                out = out.with_columns(feature.alias(name))
    return out

"""Volatility denominator and expansion-state feature family.

These features are intentionally deterministic and causal. They use
prediction-time volatility diagnostics plus already-closed higher-timeframe
OHLCV bars aligned by `core.alignment`.
"""

from __future__ import annotations

import polars as pl

from regression_feature_engineering.core.alignment import source_prefix
from regression_feature_engineering.core.math import (
    bounded_expr,
    clipped_zscore_expr,
    pct_change_expr,
    positive_vol_unit_bnd_expr,
    safe_div_expr,
    safe_log_ratio_expr,
)

FEATURE_FAMILY = "volatility_state"
TARGET_INTENT = (
    "all_targets",
    "volatility_denominator_quality",
    "future_range_expansion_potential",
)
DEFAULT_VOL_LOOKBACKS: tuple[int, ...] = (120, 480, 1440)
REQUIRED_SOURCE_COLUMNS: tuple[str, ...] = (
    "tb_volatility_pct",
    "tb_atr_pct_14",
    "tb_realized_vol_120",
)


def feature_columns(
    *,
    timeframes: tuple[str, ...],
    lookbacks: tuple[int, ...] = DEFAULT_VOL_LOOKBACKS,
) -> tuple[str, ...]:
    """Return the model-facing volatility-state feature columns."""

    cols = [
        "rpf_vol_atr_std_dominance_bnd",
        "rpf_vol_atr_std_log_ratio",
    ]
    for lookback in lookbacks:
        cols.extend(
            [
                f"rpf_vol_tb_vol_z_l{lookback}",
                f"rpf_vol_tb_vol_rel_median_l{lookback}",
                f"rpf_vol_tb_vol_chg_l{lookback}",
            ]
        )
    for timeframe in timeframes:
        cols.extend(
            [
                f"rpf_vol_{timeframe}_range_to_tb_vol",
                f"rpf_vol_{timeframe}_abs_ret_to_tb_vol",
                f"rpf_vol_{timeframe}_range_efficiency_bnd",
            ]
        )
    return tuple(cols)


def add_volatility_state_features(
    df: pl.DataFrame,
    *,
    timeframes: tuple[str, ...],
    lookbacks: tuple[int, ...] = DEFAULT_VOL_LOOKBACKS,
) -> pl.DataFrame:
    """Add initial causal volatility-state features.

    Rolling reference statistics use `.shift(1)` before the rolling window so
    the current row is not included in its own normalization baseline.
    """

    missing = [col for col in REQUIRED_SOURCE_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"Missing volatility source columns: {missing}")

    out = df.with_columns(
        [
            pl.col("tb_volatility_pct").cast(pl.Float64),
            pl.col("tb_atr_pct_14").cast(pl.Float64),
            pl.col("tb_realized_vol_120").cast(pl.Float64),
            safe_div_expr(
                pl.col("tb_atr_pct_14") - pl.col("tb_realized_vol_120"),
                pl.col("tb_atr_pct_14") + pl.col("tb_realized_vol_120"),
            )
            .fill_null(0.0)
            .alias("rpf_vol_atr_std_dominance_bnd"),
            safe_log_ratio_expr(
                pl.col("tb_atr_pct_14"),
                pl.col("tb_realized_vol_120"),
            )
            .fill_null(0.0)
            .alias("rpf_vol_atr_std_log_ratio"),
            pl.col("tb_volatility_pct").shift(1).alias("_rpf_prior_tb_vol"),
        ]
    )

    for lookback in lookbacks:
        min_samples = min(int(lookback), max(1, int(lookback) // 10))
        mean_col = f"_rpf_vol_mean_l{lookback}"
        std_col = f"_rpf_vol_std_l{lookback}"
        median_col = f"_rpf_vol_median_l{lookback}"
        lag_col = f"_rpf_vol_lag_l{lookback}"
        out = out.with_columns(
            [
                pl.col("_rpf_prior_tb_vol")
                .rolling_mean(window_size=int(lookback), min_samples=min_samples)
                .alias(mean_col),
                pl.col("_rpf_prior_tb_vol")
                .rolling_std(window_size=int(lookback), min_samples=min_samples)
                .alias(std_col),
                pl.col("_rpf_prior_tb_vol")
                .rolling_median(window_size=int(lookback), min_samples=min_samples)
                .alias(median_col),
                pl.col("tb_volatility_pct").shift(int(lookback)).alias(lag_col),
            ]
        ).with_columns(
            [
                clipped_zscore_expr(
                    safe_div_expr(pl.col("tb_volatility_pct") - pl.col(mean_col), pl.col(std_col))
                ).alias(f"rpf_vol_tb_vol_z_l{lookback}"),
                pct_change_expr(pl.col("tb_volatility_pct"), pl.col(median_col))
                .fill_null(0.0)
                .alias(f"rpf_vol_tb_vol_rel_median_l{lookback}"),
                pct_change_expr(pl.col("tb_volatility_pct"), pl.col(lag_col))
                .fill_null(0.0)
                .alias(f"rpf_vol_tb_vol_chg_l{lookback}"),
            ]
        )

    for timeframe in timeframes:
        src = source_prefix(timeframe)
        open_col = pl.col(f"{src}open")
        high_col = pl.col(f"{src}high")
        low_col = pl.col(f"{src}low")
        close_col = pl.col(f"{src}close")
        range_pct = safe_div_expr(high_col - low_col, close_col)
        abs_ret_pct = pct_change_expr(close_col, open_col).abs()
        out = out.with_columns(
            [
                positive_vol_unit_bnd_expr(
                    safe_div_expr(range_pct, pl.col("tb_volatility_pct"))
                ).alias(f"rpf_vol_{timeframe}_range_to_tb_vol"),
                positive_vol_unit_bnd_expr(
                    safe_div_expr(abs_ret_pct, pl.col("tb_volatility_pct"))
                ).alias(f"rpf_vol_{timeframe}_abs_ret_to_tb_vol"),
                bounded_expr(safe_div_expr(abs_ret_pct, range_pct), lower=0.0, upper=1.0)
                .fill_null(0.0)
                .alias(f"rpf_vol_{timeframe}_range_efficiency_bnd"),
            ]
        )

    return out.drop([col for col in out.columns if col.startswith("_rpf_vol_") or col == "_rpf_prior_tb_vol"])

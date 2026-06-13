"""Deterministic cross-asset context feature family.

This family builds pair features from exact timestamp-matched canonical bars,
then the materializer aligns those pair bars to prediction rows through the
same closed-bar as-of contract as other higher-timeframe features.

No raw foreign price or volume columns are emitted as model-facing features.
"""

from __future__ import annotations

import polars as pl

from regression_feature_engineering.core.alignment import source_prefix
from regression_feature_engineering.core.math import bounded_expr, pct_change_expr, safe_div_expr


FEATURE_FAMILY = "cross_asset_context"
TARGET_INTENT = (
    "all_targets",
    "relative_pressure",
    "common_risk_state",
    "correlated_asset_volatility_and_pressure",
)
DEFAULT_XASSET_LOOKBACKS: tuple[int, ...] = (4, 16, 48)
SOURCE_PREFIX = "_rpf_xasset_"
DEFAULT_CROSS_ASSET_PEERS: dict[str, tuple[str, ...]] = {
    "BTCUSDT": ("ETHUSDT",),
    "ETHUSDT": ("BTCUSDT",),
    "EURUSD": ("USDJPY",),
    "USDJPY": ("EURUSD",),
    "ES": ("NQ",),
    "NQ": ("ES",),
    "GC": ("CL",),
    "CL": ("GC",),
}


def context_slug(asset_id: str) -> str:
    """Return a stable lowercase slug for context feature names."""

    return asset_id.strip().lower()


def source_columns(*, lookbacks: tuple[int, ...] = DEFAULT_XASSET_LOOKBACKS) -> tuple[str, ...]:
    """Return private pair-source columns computed on canonical pair bars."""

    columns: list[str] = []
    for lookback in lookbacks:
        columns.extend(
            [
                f"{SOURCE_PREFIX}ret_spread_l{lookback}",
                f"{SOURCE_PREFIX}rel_strength_l{lookback}",
                f"{SOURCE_PREFIX}range_spread_l{lookback}",
                f"{SOURCE_PREFIX}corr_l{lookback}",
                f"{SOURCE_PREFIX}context_pressure_l{lookback}",
                f"{SOURCE_PREFIX}common_direction_l{lookback}",
                f"{SOURCE_PREFIX}context_range_share_l{lookback}",
                f"{SOURCE_PREFIX}volume_rel_spread_l{lookback}",
            ]
        )
    return tuple(columns)


def feature_columns(
    *,
    context_assets: tuple[str, ...],
    timeframes: tuple[str, ...],
    lookbacks: tuple[int, ...] = DEFAULT_XASSET_LOOKBACKS,
) -> tuple[str, ...]:
    """Return model-facing cross-asset feature columns."""

    columns: list[str] = []
    for context_asset in context_assets:
        slug = context_slug(context_asset)
        for timeframe in timeframes:
            for lookback in lookbacks:
                columns.extend(
                    [
                        f"rpf_xasset_{slug}_{timeframe}_ret_spread_l{lookback}_bnd",
                        f"rpf_xasset_{slug}_{timeframe}_rel_strength_l{lookback}_bnd",
                        f"rpf_xasset_{slug}_{timeframe}_range_spread_l{lookback}_bnd",
                        f"rpf_xasset_{slug}_{timeframe}_corr_l{lookback}_bnd",
                        f"rpf_xasset_{slug}_{timeframe}_context_pressure_l{lookback}_bnd",
                        f"rpf_xasset_{slug}_{timeframe}_common_direction_l{lookback}_bnd",
                        f"rpf_xasset_{slug}_{timeframe}_context_range_share_l{lookback}_bnd",
                        f"rpf_xasset_{slug}_{timeframe}_volume_rel_spread_l{lookback}_bnd",
                    ]
                )
    return tuple(columns)


def build_cross_asset_pair_sources(
    target_bars: pl.DataFrame,
    context_bars: pl.DataFrame,
    *,
    context_asset: str,
    lookbacks: tuple[int, ...] = DEFAULT_XASSET_LOOKBACKS,
) -> pl.DataFrame:
    """Build exact-timestamp matched pair source features on canonical bars."""

    required = {"timestamp", "open", "high", "low", "close", "volume"}
    target_missing = required - set(target_bars.columns)
    context_missing = required - set(context_bars.columns)
    if target_missing:
        raise ValueError(f"Target canonical bars missing columns: {sorted(target_missing)}")
    if context_missing:
        raise ValueError(f"Context canonical bars for {context_asset} missing columns: {sorted(context_missing)}")

    target = target_bars.sort("timestamp").select(
        [
            "timestamp",
            pl.col("high").cast(pl.Float64).alias("_rpf_xasset_t_high"),
            pl.col("low").cast(pl.Float64).alias("_rpf_xasset_t_low"),
            pl.col("close").cast(pl.Float64).alias("_rpf_xasset_t_close"),
            pl.col("volume").cast(pl.Float64).clip(0.0, None).fill_null(0.0).alias("_rpf_xasset_t_volume"),
        ]
    )
    context = context_bars.sort("timestamp").select(
        [
            "timestamp",
            pl.col("high").cast(pl.Float64).alias("_rpf_xasset_c_high"),
            pl.col("low").cast(pl.Float64).alias("_rpf_xasset_c_low"),
            pl.col("close").cast(pl.Float64).alias("_rpf_xasset_c_close"),
            pl.col("volume").cast(pl.Float64).clip(0.0, None).fill_null(0.0).alias("_rpf_xasset_c_volume"),
        ]
    )
    out = target.join(context, on="timestamp", how="inner").sort("timestamp")
    if out.is_empty():
        raise ValueError(f"No exact timestamp overlap with context asset {context_asset}")

    out = out.with_columns(
        [
            pct_change_expr(pl.col("_rpf_xasset_t_close"), pl.col("_rpf_xasset_t_close").shift(1)).alias(
                "_rpf_xasset_t_ret"
            ),
            pct_change_expr(pl.col("_rpf_xasset_c_close"), pl.col("_rpf_xasset_c_close").shift(1)).alias(
                "_rpf_xasset_c_ret"
            ),
            safe_div_expr(pl.col("_rpf_xasset_t_high") - pl.col("_rpf_xasset_t_low"), pl.col("_rpf_xasset_t_close")).alias(
                "_rpf_xasset_t_range"
            ),
            safe_div_expr(pl.col("_rpf_xasset_c_high") - pl.col("_rpf_xasset_c_low"), pl.col("_rpf_xasset_c_close")).alias(
                "_rpf_xasset_c_range"
            ),
        ]
    )
    out = out.with_columns(
        [
            pl.col("_rpf_xasset_t_ret").abs().alias("_rpf_xasset_t_abs_ret"),
            pl.col("_rpf_xasset_c_ret").abs().alias("_rpf_xasset_c_abs_ret"),
            _sign_expr(pl.col("_rpf_xasset_t_ret")).alias("_rpf_xasset_t_sign"),
            _sign_expr(pl.col("_rpf_xasset_c_ret")).alias("_rpf_xasset_c_sign"),
        ]
    )

    for lookback in lookbacks:
        lookback = int(lookback)
        min_samples = min(lookback, max(2, lookback // 4))
        t_ret_sum = f"_rpf_xasset_t_ret_sum_l{lookback}"
        c_ret_sum = f"_rpf_xasset_c_ret_sum_l{lookback}"
        t_abs_sum = f"_rpf_xasset_t_abs_sum_l{lookback}"
        c_abs_sum = f"_rpf_xasset_c_abs_sum_l{lookback}"
        t_range_mean = f"_rpf_xasset_t_range_mean_l{lookback}"
        c_range_mean = f"_rpf_xasset_c_range_mean_l{lookback}"
        t_volume_rel = f"_rpf_xasset_t_volume_rel_l{lookback}"
        c_volume_rel = f"_rpf_xasset_c_volume_rel_l{lookback}"

        out = out.with_columns(
            [
                pl.col("_rpf_xasset_t_ret").rolling_sum(window_size=lookback, min_samples=min_samples).alias(t_ret_sum),
                pl.col("_rpf_xasset_c_ret").rolling_sum(window_size=lookback, min_samples=min_samples).alias(c_ret_sum),
                pl.col("_rpf_xasset_t_abs_ret").rolling_sum(window_size=lookback, min_samples=min_samples).alias(t_abs_sum),
                pl.col("_rpf_xasset_c_abs_ret").rolling_sum(window_size=lookback, min_samples=min_samples).alias(c_abs_sum),
                pl.col("_rpf_xasset_t_range").rolling_mean(window_size=lookback, min_samples=min_samples).alias(t_range_mean),
                pl.col("_rpf_xasset_c_range").rolling_mean(window_size=lookback, min_samples=min_samples).alias(c_range_mean),
                safe_div_expr(
                    pl.col("_rpf_xasset_t_volume"),
                    pl.col("_rpf_xasset_t_volume").shift(1).rolling_median(window_size=lookback, min_samples=min_samples),
                    default=0.0,
                ).alias(t_volume_rel),
                safe_div_expr(
                    pl.col("_rpf_xasset_c_volume"),
                    pl.col("_rpf_xasset_c_volume").shift(1).rolling_median(window_size=lookback, min_samples=min_samples),
                    default=0.0,
                ).alias(c_volume_rel),
            ]
        )
        out = out.with_columns(
            [
                bounded_expr(
                    safe_div_expr(pl.col(t_ret_sum) - pl.col(c_ret_sum), pl.col(t_abs_sum) + pl.col(c_abs_sum)),
                    lower=-1.0,
                    upper=1.0,
                )
                .fill_null(0.0)
                .alias(f"{SOURCE_PREFIX}ret_spread_l{lookback}"),
                bounded_expr(
                    safe_div_expr(pl.col(t_abs_sum) - pl.col(c_abs_sum), pl.col(t_abs_sum) + pl.col(c_abs_sum)),
                    lower=-1.0,
                    upper=1.0,
                )
                .fill_null(0.0)
                .alias(f"{SOURCE_PREFIX}rel_strength_l{lookback}"),
                bounded_expr(
                    safe_div_expr(pl.col(t_range_mean) - pl.col(c_range_mean), pl.col(t_range_mean) + pl.col(c_range_mean)),
                    lower=-1.0,
                    upper=1.0,
                )
                .fill_null(0.0)
                .alias(f"{SOURCE_PREFIX}range_spread_l{lookback}"),
                pl.rolling_corr(
                    pl.col("_rpf_xasset_t_ret"),
                    pl.col("_rpf_xasset_c_ret"),
                    window_size=lookback,
                    min_samples=min_samples,
                )
                .clip(-1.0, 1.0)
                .fill_null(0.0)
                .alias(f"{SOURCE_PREFIX}corr_l{lookback}"),
                pl.col("_rpf_xasset_c_sign")
                .rolling_mean(window_size=lookback, min_samples=min_samples)
                .clip(-1.0, 1.0)
                .fill_null(0.0)
                .alias(f"{SOURCE_PREFIX}context_pressure_l{lookback}"),
                (pl.col("_rpf_xasset_t_sign") * pl.col("_rpf_xasset_c_sign"))
                .rolling_mean(window_size=lookback, min_samples=min_samples)
                .clip(-1.0, 1.0)
                .fill_null(0.0)
                .alias(f"{SOURCE_PREFIX}common_direction_l{lookback}"),
                bounded_expr(
                    safe_div_expr(pl.col(c_range_mean), pl.col(t_range_mean) + pl.col(c_range_mean)),
                    lower=0.0,
                    upper=1.0,
                )
                .fill_null(0.0)
                .alias(f"{SOURCE_PREFIX}context_range_share_l{lookback}"),
                bounded_expr(
                    safe_div_expr(pl.col(t_volume_rel) - pl.col(c_volume_rel), pl.col(t_volume_rel) + pl.col(c_volume_rel)),
                    lower=-1.0,
                    upper=1.0,
                )
                .fill_null(0.0)
                .alias(f"{SOURCE_PREFIX}volume_rel_spread_l{lookback}"),
            ]
        )

    keep_source_cols = {"timestamp", *source_columns(lookbacks=lookbacks)}
    return out.select([col for col in out.columns if col in keep_source_cols])


def add_cross_asset_context_features(
    df: pl.DataFrame,
    *,
    context_asset: str,
    timeframes: tuple[str, ...],
    lookbacks: tuple[int, ...] = DEFAULT_XASSET_LOOKBACKS,
) -> pl.DataFrame:
    """Add model-facing cross-asset features from aligned pair source columns."""

    slug = context_slug(context_asset)
    out = df
    for timeframe in timeframes:
        src = source_prefix(timeframe)
        for lookback in lookbacks:
            for suffix in (
                "ret_spread",
                "rel_strength",
                "range_spread",
                "corr",
                "context_pressure",
                "common_direction",
                "context_range_share",
                "volume_rel_spread",
            ):
                source_col = f"{src}{SOURCE_PREFIX}{suffix}_l{lookback}"
                if source_col not in out.columns:
                    raise ValueError(f"Missing cross-asset source column: {source_col}")
                out = out.with_columns(
                    pl.col(source_col)
                    .cast(pl.Float64)
                    .fill_null(0.0)
                    .clip(-1.0, 1.0)
                    .alias(f"rpf_xasset_{slug}_{timeframe}_{suffix}_l{lookback}_bnd")
                )
            range_share_col = f"rpf_xasset_{slug}_{timeframe}_context_range_share_l{lookback}_bnd"
            out = out.with_columns(pl.col(range_share_col).clip(0.0, 1.0).fill_null(0.0).alias(range_share_col))
    return out


def _sign_expr(expr: pl.Expr) -> pl.Expr:
    return pl.when(expr > 0.0).then(1.0).when(expr < 0.0).then(-1.0).otherwise(0.0)

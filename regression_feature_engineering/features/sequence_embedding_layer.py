"""Deterministic multi-timeframe sequence-shape proxies.

This is not a learned CNN/encoder. Learned sequence embeddings must be fitted
inside walk-forward train windows. These static features summarize the ordered
multi-timeframe shape of causal Phase 12 factor proxies.
"""

from __future__ import annotations

import polars as pl

from regression_feature_engineering.core.math import bounded_expr, safe_div_expr


FEATURE_FAMILY = "sequence_embedding_layer"
TARGET_INTENT = (
    "sequence_shape",
    "multi_timeframe_stack",
    "local_path_embedding_proxy",
)
DEFAULT_SEQUENCE_LOOKBACKS: tuple[int, ...] = (4, 16, 48)


def feature_columns(*, lookbacks: tuple[int, ...] = DEFAULT_SEQUENCE_LOOKBACKS) -> tuple[str, ...]:
    """Return deterministic sequence-shape feature columns."""

    columns: list[str] = []
    for lookback in lookbacks:
        columns.extend(
            [
                f"rpf_seq_direction_mean_l{lookback}_bnd",
                f"rpf_seq_direction_slope_l{lookback}_bnd",
                f"rpf_seq_direction_dispersion_l{lookback}_bnd",
                f"rpf_seq_direction_consensus_l{lookback}_bnd",
                f"rpf_seq_width_mean_l{lookback}_bnd",
                f"rpf_seq_width_slope_l{lookback}_bnd",
                f"rpf_seq_width_dispersion_l{lookback}_bnd",
                f"rpf_seq_shock_mean_l{lookback}_bnd",
                f"rpf_seq_persistence_mean_l{lookback}_bnd",
                f"rpf_seq_clean_direction_l{lookback}_bnd",
            ]
        )
    return tuple(columns)


def add_sequence_embedding_layer_features(
    df: pl.DataFrame,
    *,
    timeframes: tuple[str, ...],
    lookbacks: tuple[int, ...] = DEFAULT_SEQUENCE_LOOKBACKS,
) -> pl.DataFrame:
    """Add deterministic ordered-timeframe shape features from factor proxies."""

    missing = [
        f"rpf_factor_{timeframe}_direction_l{lookback}_bnd"
        for timeframe in timeframes
        for lookback in lookbacks
        if f"rpf_factor_{timeframe}_direction_l{lookback}_bnd" not in df.columns
    ]
    if missing:
        raise ValueError(f"Sequence layer requires factor features first; missing: {missing[:20]}")

    out = df
    short_count = max(1, len(timeframes) // 2)
    for lookback in lookbacks:
        direction = [_signed(pl.col(f"rpf_factor_{tf}_direction_l{lookback}_bnd")) for tf in timeframes]
        width = [_b01(pl.col(f"rpf_factor_{tf}_path_width_l{lookback}_bnd")) for tf in timeframes]
        shock = [_b01(pl.col(f"rpf_factor_{tf}_shock_l{lookback}_bnd")) for tf in timeframes]
        persistence = [_signed(pl.col(f"rpf_factor_{tf}_persistence_l{lookback}_bnd")) for tf in timeframes]
        clean = [_signed(pl.col(f"rpf_factor_{tf}_clean_direction_l{lookback}_bnd")) for tf in timeframes]

        direction_mean = _mean_signed(direction)
        width_mean = _mean_01(width)
        shock_mean = _mean_01(shock)
        persistence_mean = _mean_signed(persistence)
        clean_mean = _mean_signed(clean)

        short_direction = _mean_signed(direction[:short_count])
        long_direction = _mean_signed(direction[short_count:]) if direction[short_count:] else short_direction
        short_width = _mean_01(width[:short_count])
        long_width = _mean_01(width[short_count:]) if width[short_count:] else short_width
        abs_direction_mean = _mean_01([expr.abs() for expr in direction])

        out = out.with_columns(
            [
                direction_mean.alias(f"rpf_seq_direction_mean_l{lookback}_bnd"),
                _signed(short_direction - long_direction).alias(f"rpf_seq_direction_slope_l{lookback}_bnd"),
                _dispersion_signed(direction).alias(f"rpf_seq_direction_dispersion_l{lookback}_bnd"),
                _signed(safe_div_expr(direction_mean, abs_direction_mean, default=0.0)).alias(
                    f"rpf_seq_direction_consensus_l{lookback}_bnd"
                ),
                width_mean.alias(f"rpf_seq_width_mean_l{lookback}_bnd"),
                _signed(short_width - long_width).alias(f"rpf_seq_width_slope_l{lookback}_bnd"),
                _dispersion_01(width).alias(f"rpf_seq_width_dispersion_l{lookback}_bnd"),
                shock_mean.alias(f"rpf_seq_shock_mean_l{lookback}_bnd"),
                persistence_mean.alias(f"rpf_seq_persistence_mean_l{lookback}_bnd"),
                clean_mean.alias(f"rpf_seq_clean_direction_l{lookback}_bnd"),
            ]
        )
    return out


def _b01(expr: pl.Expr) -> pl.Expr:
    return bounded_expr(expr.cast(pl.Float64).fill_null(0.0), lower=0.0, upper=1.0).fill_null(0.0)


def _signed(expr: pl.Expr) -> pl.Expr:
    return bounded_expr(expr.cast(pl.Float64).fill_null(0.0), lower=-1.0, upper=1.0).fill_null(0.0)


def _mean_01(expressions: list[pl.Expr]) -> pl.Expr:
    if not expressions:
        return pl.lit(0.0)
    return _b01(pl.sum_horizontal(expressions) / float(len(expressions)))


def _mean_signed(expressions: list[pl.Expr]) -> pl.Expr:
    if not expressions:
        return pl.lit(0.0)
    return _signed(pl.sum_horizontal(expressions) / float(len(expressions)))


def _dispersion_01(expressions: list[pl.Expr]) -> pl.Expr:
    if not expressions:
        return pl.lit(0.0)
    return _b01(pl.max_horizontal(expressions) - pl.min_horizontal(expressions))


def _dispersion_signed(expressions: list[pl.Expr]) -> pl.Expr:
    if not expressions:
        return pl.lit(0.0)
    return _b01((pl.max_horizontal(expressions) - pl.min_horizontal(expressions)) / 2.0)

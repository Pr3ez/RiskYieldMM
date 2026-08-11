"""Causal factor-proxy feature family.

This phase intentionally avoids a globally fitted PCA or clustering model.
Those transforms must be fitted inside walk-forward train windows. For the
static RPF artifact we emit deterministic, bounded factor proxies built only
from already causal RPF component features.
"""

from __future__ import annotations

import polars as pl

from regression_feature_engineering.core.math import bounded_expr, safe_div_expr


FEATURE_FAMILY = "unsupervised_factor_layer"
TARGET_INTENT = (
    "derived_context",
    "path_regime",
    "factor_proxy",
)
DEFAULT_FACTOR_LOOKBACKS: tuple[int, ...] = (4, 16, 48)


def feature_columns(
    *,
    timeframes: tuple[str, ...],
    lookbacks: tuple[int, ...] = DEFAULT_FACTOR_LOOKBACKS,
) -> tuple[str, ...]:
    """Return deterministic factor-proxy feature columns."""

    columns: list[str] = []
    for timeframe in timeframes:
        for lookback in lookbacks:
            columns.extend(
                [
                    f"rpf_factor_{timeframe}_path_width_l{lookback}_bnd",
                    f"rpf_factor_{timeframe}_direction_l{lookback}_bnd",
                    f"rpf_factor_{timeframe}_persistence_l{lookback}_bnd",
                    f"rpf_factor_{timeframe}_shock_l{lookback}_bnd",
                    f"rpf_factor_{timeframe}_rejection_l{lookback}_bnd",
                    f"rpf_factor_{timeframe}_context_l{lookback}_bnd",
                    f"rpf_factor_{timeframe}_anomaly_l{lookback}_bnd",
                    f"rpf_factor_{timeframe}_clean_direction_l{lookback}_bnd",
                ]
            )
    return tuple(columns)


def required_component_families() -> tuple[str, ...]:
    """Return component families required before Phase 12 can be requested."""

    return (
        "volatility_state",
        "structural_room",
        "acceptance_persistence",
        "rejection_chop",
        "spike_breakout",
        "liquidity_volume_pressure",
        "regime_calendar_state",
        "interaction_confluence",
        "cross_asset_context",
    )


def add_unsupervised_factor_layer_features(
    df: pl.DataFrame,
    *,
    timeframes: tuple[str, ...],
    lookbacks: tuple[int, ...] = DEFAULT_FACTOR_LOOKBACKS,
    context_assets: tuple[str, ...] = (),
) -> pl.DataFrame:
    """Add deterministic factor proxies from existing causal RPF features."""

    out = df
    for timeframe in timeframes:
        for lookback in lookbacks:
            prefix = f"rpf_factor_{timeframe}"
            path_width = _mean_01(
                [
                    _vol_units_01(_col(out, f"rpf_vol_{timeframe}_range_to_tb_vol")),
                    _b01(_col(out, f"rpf_spike_{timeframe}_squeeze_release_l{lookback}_bnd")),
                    _b01(_col(out, f"rpf_chop_{timeframe}_two_sided_l{lookback}_bnd")),
                    _b01(_col(out, f"rpf_regime_{timeframe}_range_chop_l{lookback}_bnd")),
                    _abs_signed_01(_col(out, f"rpf_conf_{timeframe}_squeeze_break_balance_l{lookback}_bnd")),
                ]
            )
            direction = _mean_signed(
                [
                    _signed(_col(out, f"rpf_accept_{timeframe}_return_persist_l{lookback}_bnd")),
                    _signed(_col(out, f"rpf_accept_{timeframe}_value_accept_balance_l{lookback}_bnd")),
                    _signed(_col(out, f"rpf_accept_{timeframe}_trend_eff_l{lookback}_bnd")),
                    _signed(_col(out, f"rpf_spike_{timeframe}_impulse_balance_l{lookback}_bnd")),
                    _signed(_col(out, f"rpf_liq_{timeframe}_volume_pressure_balance_l{lookback}_bnd")),
                    _signed(_col(out, f"rpf_regime_{timeframe}_trend_alignment_l{lookback}_bnd")),
                    _signed(_col(out, f"rpf_conf_{timeframe}_trend_accept_balance_l{lookback}_bnd")),
                    _signed(_context_signed(out, context_assets, timeframe, lookback)),
                ]
            )
            persistence = _mean_signed(
                [
                    _signed(_col(out, f"rpf_accept_{timeframe}_trend_eff_l{lookback}_bnd")),
                    _signed(_col(out, f"rpf_regime_{timeframe}_trend_alignment_l{lookback}_bnd")),
                    _signed(_col(out, f"rpf_conf_{timeframe}_clean_persist_balance_l{lookback}_bnd")),
                    _signed(_col(out, f"rpf_conf_{timeframe}_trend_accept_balance_l{lookback}_bnd")),
                ]
            )
            shock = _mean_01(
                [
                    _b01(_col(out, f"rpf_spike_{timeframe}_release_l{lookback}_bnd")),
                    _b01(_col(out, f"rpf_spike_{timeframe}_squeeze_release_l{lookback}_bnd")),
                    _b01(_col(out, f"rpf_liq_{timeframe}_volume_wakeup_l{lookback}_bnd")),
                    _abs_signed_01(_col(out, f"rpf_spike_{timeframe}_tail_asym_l{lookback}_bnd")),
                    _abs_signed_01(_col(out, f"rpf_conf_{timeframe}_volume_impulse_balance_l{lookback}_bnd")),
                ]
            )
            rejection = _mean_signed(
                [
                    _signed(_col(out, f"rpf_chop_{timeframe}_reject_balance_l{lookback}_bnd")),
                    _signed(_col(out, f"rpf_chop_{timeframe}_failed_break_balance_l{lookback}_bnd")),
                    _signed(_col(out, f"rpf_chop_{timeframe}_upper_reject_l{lookback}_bnd"))
                    - _signed(_col(out, f"rpf_chop_{timeframe}_lower_reject_l{lookback}_bnd")),
                ]
            )
            context = _signed(_context_signed(out, context_assets, timeframe, lookback))
            anomaly = _b01(
                (
                    path_width
                    + shock
                    + _b01(_col(out, f"rpf_chop_{timeframe}_path_chop_l{lookback}_bnd"))
                    + _abs_signed_01(direction - context)
                )
                / 4.0
            )
            clean_direction = _signed(direction * (1.0 - _b01(_col(out, f"rpf_chop_{timeframe}_path_chop_l{lookback}_bnd"))))

            out = out.with_columns(
                [
                    path_width.alias(f"{prefix}_path_width_l{lookback}_bnd"),
                    direction.alias(f"{prefix}_direction_l{lookback}_bnd"),
                    persistence.alias(f"{prefix}_persistence_l{lookback}_bnd"),
                    shock.alias(f"{prefix}_shock_l{lookback}_bnd"),
                    rejection.alias(f"{prefix}_rejection_l{lookback}_bnd"),
                    context.alias(f"{prefix}_context_l{lookback}_bnd"),
                    anomaly.alias(f"{prefix}_anomaly_l{lookback}_bnd"),
                    clean_direction.alias(f"{prefix}_clean_direction_l{lookback}_bnd"),
                ]
            )
    return out


def _col(df: pl.DataFrame, name: str, *, default: float = 0.0) -> pl.Expr:
    if name in df.columns:
        return pl.col(name).cast(pl.Float64).fill_null(default)
    return pl.lit(float(default))


def _b01(expr: pl.Expr) -> pl.Expr:
    return bounded_expr(expr.cast(pl.Float64).fill_null(0.0), lower=0.0, upper=1.0).fill_null(0.0)


def _signed(expr: pl.Expr) -> pl.Expr:
    return bounded_expr(expr.cast(pl.Float64).fill_null(0.0), lower=-1.0, upper=1.0).fill_null(0.0)


def _abs_signed_01(expr: pl.Expr) -> pl.Expr:
    return _b01(expr.cast(pl.Float64).fill_null(0.0).abs())


def _vol_units_01(expr: pl.Expr) -> pl.Expr:
    value = expr.cast(pl.Float64).fill_null(0.0).abs()
    return _b01(safe_div_expr(value, 1.0 + value, default=0.0))


def _mean_01(expressions: list[pl.Expr]) -> pl.Expr:
    if not expressions:
        return pl.lit(0.0)
    return _b01(pl.sum_horizontal(expressions) / float(len(expressions)))


def _mean_signed(expressions: list[pl.Expr]) -> pl.Expr:
    if not expressions:
        return pl.lit(0.0)
    return _signed(pl.sum_horizontal(expressions) / float(len(expressions)))


def _context_signed(
    df: pl.DataFrame,
    context_assets: tuple[str, ...],
    timeframe: str,
    lookback: int,
) -> pl.Expr:
    expressions: list[pl.Expr] = []
    for asset in context_assets:
        slug = asset.lower()
        expressions.extend(
            [
                _col(df, f"rpf_xasset_{slug}_{timeframe}_ret_spread_l{lookback}_bnd"),
                _col(df, f"rpf_xasset_{slug}_{timeframe}_rel_strength_l{lookback}_bnd"),
                _col(df, f"rpf_xasset_{slug}_{timeframe}_context_pressure_l{lookback}_bnd"),
                _col(df, f"rpf_xasset_{slug}_{timeframe}_common_direction_l{lookback}_bnd"),
            ]
        )
    return _mean_signed(expressions) if expressions else pl.lit(0.0)

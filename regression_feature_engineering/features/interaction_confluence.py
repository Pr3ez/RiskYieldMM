"""Interaction and confluence feature family.

This family combines already-generated causal `rpf_*` component features. It
does not read raw OHLCV, target diagnostics, labels, or future-window data.
Each output is bounded so it can be safely used by the target-specific feature
policy without raw-scale leakage.
"""

from __future__ import annotations

import polars as pl

from regression_feature_engineering.core.math import bounded_expr, positive_part_expr, safe_div_expr


FEATURE_FAMILY = "interaction_confluence"
TARGET_INTENT = (
    "signal_confluence",
    "conditional_context",
    "component_interaction",
)
DEFAULT_CONFLUENCE_LOOKBACKS: tuple[int, ...] = (4, 16, 48)


def feature_columns(
    *,
    timeframes: tuple[str, ...],
    lookbacks: tuple[int, ...] = DEFAULT_CONFLUENCE_LOOKBACKS,
) -> tuple[str, ...]:
    """Return model-facing interaction/confluence feature columns."""

    columns: list[str] = []
    for timeframe in timeframes:
        for lookback in lookbacks:
            columns.extend(
                [
                    f"rpf_conf_{timeframe}_up_squeeze_break_l{lookback}_bnd",
                    f"rpf_conf_{timeframe}_down_squeeze_break_l{lookback}_bnd",
                    f"rpf_conf_{timeframe}_squeeze_break_balance_l{lookback}_bnd",
                    f"rpf_conf_{timeframe}_up_trend_accept_l{lookback}_bnd",
                    f"rpf_conf_{timeframe}_down_trend_accept_l{lookback}_bnd",
                    f"rpf_conf_{timeframe}_trend_accept_balance_l{lookback}_bnd",
                    f"rpf_conf_{timeframe}_up_volume_impulse_l{lookback}_bnd",
                    f"rpf_conf_{timeframe}_down_volume_impulse_l{lookback}_bnd",
                    f"rpf_conf_{timeframe}_volume_impulse_balance_l{lookback}_bnd",
                    f"rpf_conf_{timeframe}_up_clean_persist_l{lookback}_bnd",
                    f"rpf_conf_{timeframe}_down_clean_persist_l{lookback}_bnd",
                    f"rpf_conf_{timeframe}_clean_persist_balance_l{lookback}_bnd",
                    f"rpf_conf_{timeframe}_up_room_pressure_l{lookback}_bnd",
                    f"rpf_conf_{timeframe}_down_room_pressure_l{lookback}_bnd",
                    f"rpf_conf_{timeframe}_room_pressure_balance_l{lookback}_bnd",
                ]
            )
    return tuple(columns)


def required_component_columns(
    *,
    timeframes: tuple[str, ...],
    lookbacks: tuple[int, ...] = DEFAULT_CONFLUENCE_LOOKBACKS,
) -> tuple[str, ...]:
    """Return component feature columns required by Phase 10 formulas."""

    columns: list[str] = []
    for timeframe in timeframes:
        for lookback in lookbacks:
            columns.extend(
                [
                    f"rpf_spike_{timeframe}_squeeze_l{lookback}_bnd",
                    f"rpf_spike_{timeframe}_up_break_prox_l{lookback}_vol",
                    f"rpf_spike_{timeframe}_down_break_prox_l{lookback}_vol",
                    f"rpf_spike_{timeframe}_up_volume_impulse_l{lookback}_bnd",
                    f"rpf_spike_{timeframe}_down_volume_impulse_l{lookback}_bnd",
                    f"rpf_accept_{timeframe}_return_persist_l{lookback}_bnd",
                    f"rpf_accept_{timeframe}_value_accept_balance_l{lookback}_bnd",
                    f"rpf_accept_{timeframe}_trend_eff_l{lookback}_bnd",
                    f"rpf_room_{timeframe}_up_room_share_l{lookback}_bnd",
                    f"rpf_chop_{timeframe}_upper_reject_l{lookback}_bnd",
                    f"rpf_chop_{timeframe}_lower_reject_l{lookback}_bnd",
                    f"rpf_chop_{timeframe}_path_chop_l{lookback}_bnd",
                    f"rpf_liq_{timeframe}_volume_wakeup_l{lookback}_bnd",
                    f"rpf_liq_{timeframe}_volume_pressure_balance_l{lookback}_bnd",
                    f"rpf_regime_{timeframe}_trend_alignment_l{lookback}_bnd",
                ]
            )
    return tuple(dict.fromkeys(columns))


def add_interaction_confluence_features(
    df: pl.DataFrame,
    *,
    timeframes: tuple[str, ...],
    lookbacks: tuple[int, ...] = DEFAULT_CONFLUENCE_LOOKBACKS,
) -> pl.DataFrame:
    """Add bounded confluence features from existing causal components."""

    missing = [col for col in required_component_columns(timeframes=timeframes, lookbacks=lookbacks) if col not in df.columns]
    if missing:
        raise ValueError(f"Interaction/confluence component columns missing: {missing[:20]}")

    out = df
    for timeframe in timeframes:
        for lookback in lookbacks:
            prefix = f"rpf_conf_{timeframe}"
            spike_prefix = f"rpf_spike_{timeframe}"
            accept_prefix = f"rpf_accept_{timeframe}"
            room_prefix = f"rpf_room_{timeframe}"
            chop_prefix = f"rpf_chop_{timeframe}"
            liq_prefix = f"rpf_liq_{timeframe}"
            regime_prefix = f"rpf_regime_{timeframe}"

            up_prox_close = _bounded_closeness(pl.col(f"{spike_prefix}_up_break_prox_l{lookback}_vol"))
            down_prox_close = _bounded_closeness(pl.col(f"{spike_prefix}_down_break_prox_l{lookback}_vol"))
            squeeze = _bounded_01(pl.col(f"{spike_prefix}_squeeze_l{lookback}_bnd"))
            up_volume_impulse = _bounded_01(pl.col(f"{spike_prefix}_up_volume_impulse_l{lookback}_bnd"))
            down_volume_impulse = _bounded_01(pl.col(f"{spike_prefix}_down_volume_impulse_l{lookback}_bnd"))
            volume_wakeup = _bounded_01(pl.col(f"{liq_prefix}_volume_wakeup_l{lookback}_bnd"))
            volume_balance = pl.col(f"{liq_prefix}_volume_pressure_balance_l{lookback}_bnd").cast(pl.Float64).fill_null(0.0)

            return_persist = pl.col(f"{accept_prefix}_return_persist_l{lookback}_bnd").cast(pl.Float64).fill_null(0.0)
            value_accept = pl.col(f"{accept_prefix}_value_accept_balance_l{lookback}_bnd").cast(pl.Float64).fill_null(0.0)
            trend_eff = pl.col(f"{accept_prefix}_trend_eff_l{lookback}_bnd").cast(pl.Float64).fill_null(0.0)
            trend_alignment = pl.col(f"{regime_prefix}_trend_alignment_l{lookback}_bnd").cast(pl.Float64).fill_null(0.0)
            up_accept = _bounded_01(
                (
                    positive_part_expr(return_persist)
                    + positive_part_expr(value_accept)
                    + positive_part_expr(trend_eff)
                    + positive_part_expr(trend_alignment)
                )
                / 4.0
            )
            down_accept = _bounded_01(
                (
                    positive_part_expr(-return_persist)
                    + positive_part_expr(-value_accept)
                    + positive_part_expr(-trend_eff)
                    + positive_part_expr(-trend_alignment)
                )
                / 4.0
            )

            path_chop = _bounded_01(pl.col(f"{chop_prefix}_path_chop_l{lookback}_bnd"))
            upper_reject = _bounded_01(pl.col(f"{chop_prefix}_upper_reject_l{lookback}_bnd"))
            lower_reject = _bounded_01(pl.col(f"{chop_prefix}_lower_reject_l{lookback}_bnd"))
            up_room_share = _bounded_01(pl.col(f"{room_prefix}_up_room_share_l{lookback}_bnd"))
            down_room_share = _bounded_01(1.0 - up_room_share)

            up_squeeze_break = _bounded_01(squeeze * up_prox_close)
            down_squeeze_break = _bounded_01(squeeze * down_prox_close)
            up_trend_accept = _bounded_01(up_accept)
            down_trend_accept = _bounded_01(down_accept)
            up_vol_impulse = _bounded_01(volume_wakeup * up_volume_impulse * positive_part_expr(volume_balance))
            down_vol_impulse = _bounded_01(volume_wakeup * down_volume_impulse * positive_part_expr(-volume_balance))
            up_clean_persist = _bounded_01(up_accept * (1.0 - path_chop) * (1.0 - upper_reject))
            down_clean_persist = _bounded_01(down_accept * (1.0 - path_chop) * (1.0 - lower_reject))
            up_room_pressure = _bounded_01(up_room_share * up_accept)
            down_room_pressure = _bounded_01(down_room_share * down_accept)

            out = out.with_columns(
                [
                    up_squeeze_break.alias(f"{prefix}_up_squeeze_break_l{lookback}_bnd"),
                    down_squeeze_break.alias(f"{prefix}_down_squeeze_break_l{lookback}_bnd"),
                    _signed_balance(up_squeeze_break, down_squeeze_break).alias(
                        f"{prefix}_squeeze_break_balance_l{lookback}_bnd"
                    ),
                    up_trend_accept.alias(f"{prefix}_up_trend_accept_l{lookback}_bnd"),
                    down_trend_accept.alias(f"{prefix}_down_trend_accept_l{lookback}_bnd"),
                    _signed_balance(up_trend_accept, down_trend_accept).alias(
                        f"{prefix}_trend_accept_balance_l{lookback}_bnd"
                    ),
                    up_vol_impulse.alias(f"{prefix}_up_volume_impulse_l{lookback}_bnd"),
                    down_vol_impulse.alias(f"{prefix}_down_volume_impulse_l{lookback}_bnd"),
                    _signed_balance(up_vol_impulse, down_vol_impulse).alias(
                        f"{prefix}_volume_impulse_balance_l{lookback}_bnd"
                    ),
                    up_clean_persist.alias(f"{prefix}_up_clean_persist_l{lookback}_bnd"),
                    down_clean_persist.alias(f"{prefix}_down_clean_persist_l{lookback}_bnd"),
                    _signed_balance(up_clean_persist, down_clean_persist).alias(
                        f"{prefix}_clean_persist_balance_l{lookback}_bnd"
                    ),
                    up_room_pressure.alias(f"{prefix}_up_room_pressure_l{lookback}_bnd"),
                    down_room_pressure.alias(f"{prefix}_down_room_pressure_l{lookback}_bnd"),
                    _signed_balance(up_room_pressure, down_room_pressure).alias(
                        f"{prefix}_room_pressure_balance_l{lookback}_bnd"
                    ),
                ]
            )
    return out


def _bounded_01(expr: pl.Expr) -> pl.Expr:
    return bounded_expr(expr.cast(pl.Float64).fill_null(0.0), lower=0.0, upper=1.0).fill_null(0.0)


def _bounded_closeness(distance_vol: pl.Expr) -> pl.Expr:
    """Convert nonnegative volatility-unit distance into close-to-level score."""

    distance = distance_vol.cast(pl.Float64).fill_null(0.0).clip(0.0, None)
    return _bounded_01(1.0 - safe_div_expr(distance, 1.0 + distance, default=1.0))


def _signed_balance(up: pl.Expr, down: pl.Expr) -> pl.Expr:
    return bounded_expr((up - down).cast(pl.Float64).fill_null(0.0), lower=-1.0, upper=1.0).fill_null(0.0)

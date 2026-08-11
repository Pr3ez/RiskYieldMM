from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import polars as pl
import pytest

from regression_feature_engineering.core.alignment import join_closed_bar_context
from regression_feature_engineering.core.math import pct_change_expr, safe_div_expr
from regression_feature_engineering.features.acceptance_persistence import (
    add_acceptance_persistence_features,
    enrich_acceptance_persistence_sources,
)
from regression_feature_engineering.features.acceptance_persistence import (
    feature_columns as acceptance_feature_columns,
)
from regression_feature_engineering.features.cross_asset_context import (
    add_cross_asset_context_features,
    build_cross_asset_pair_sources,
)
from regression_feature_engineering.features.cross_asset_context import (
    feature_columns as cross_asset_feature_columns,
)
from regression_feature_engineering.features.interaction_confluence import (
    add_interaction_confluence_features,
)
from regression_feature_engineering.features.interaction_confluence import (
    feature_columns as interaction_confluence_feature_columns,
)
from regression_feature_engineering.features.liquidity_volume_pressure import (
    add_liquidity_volume_pressure_features,
    enrich_liquidity_volume_pressure_sources,
)
from regression_feature_engineering.features.liquidity_volume_pressure import (
    feature_columns as liquidity_feature_columns,
)
from regression_feature_engineering.features.regime_calendar_state import (
    add_regime_calendar_state_features,
    enrich_regime_calendar_state_sources,
)
from regression_feature_engineering.features.regime_calendar_state import (
    feature_columns as regime_calendar_feature_columns,
)
from regression_feature_engineering.features.rejection_chop import (
    add_rejection_chop_features,
    enrich_rejection_chop_sources,
)
from regression_feature_engineering.features.rejection_chop import (
    feature_columns as rejection_chop_feature_columns,
)
from regression_feature_engineering.features.sequence_embedding_layer import (
    add_sequence_embedding_layer_features,
)
from regression_feature_engineering.features.sequence_embedding_layer import (
    feature_columns as sequence_embedding_feature_columns,
)
from regression_feature_engineering.features.spike_breakout import (
    add_spike_breakout_features,
    enrich_spike_breakout_sources,
)
from regression_feature_engineering.features.spike_breakout import (
    feature_columns as spike_breakout_feature_columns,
)
from regression_feature_engineering.features.structural_room import (
    add_structural_room_features,
    enrich_structural_room_sources,
)
from regression_feature_engineering.features.structural_room import (
    feature_columns as structural_feature_columns,
)
from regression_feature_engineering.features.temporal_memory_transforms import (
    TemporalMemoryState,
)
from regression_feature_engineering.features.temporal_memory_transforms import (
    feature_columns as temporal_memory_feature_columns,
)
from regression_feature_engineering.features.temporal_memory_transforms import (
    selected_source_columns as temporal_memory_source_columns,
)
from regression_feature_engineering.features.unsupervised_factor_layer import (
    add_unsupervised_factor_layer_features,
)
from regression_feature_engineering.features.unsupervised_factor_layer import (
    feature_columns as unsupervised_factor_feature_columns,
)
from regression_feature_engineering.features.volatility_state import (
    add_volatility_state_features,
    feature_columns,
)
from regression_feature_engineering.materialize_features import (
    materialize_regression_feature_roots,
    parse_families,
)


def _positive_vol_unit_bnd(value: float, *, scale: float = 8.0) -> float:
    value = max(float(value), 0.0)
    return value / (value + scale) if value > 0.0 else 0.0


def _signed_vol_unit_bnd(value: float, *, scale: float = 8.0) -> float:
    value = float(value)
    return value / (abs(value) + scale) if value != 0.0 else 0.0


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def test_closed_bar_alignment_waits_until_bar_close() -> None:
    rows = pl.DataFrame(
        {
            "timestamp": [
                _ts("2026-01-01T00:14:00"),
                _ts("2026-01-01T00:15:00"),
                _ts("2026-01-01T00:29:00"),
            ],
            "batch_id": [1, 1, 1],
        }
    )
    bars = pl.DataFrame(
        {
            "timestamp": [_ts("2026-01-01T00:00:00"), _ts("2026-01-01T00:15:00")],
            "open": [100.0, 105.0],
            "high": [110.0, 115.0],
            "low": [99.0, 104.0],
            "close": [105.0, 114.0],
            "volume": [10.0, 20.0],
        }
    )

    out = join_closed_bar_context(rows, bars, timeframe="15m")

    assert out["rpf_align_15m_has_closed_bar"].to_list() == [False, True, True]
    assert out["rpf_align_15m_bar_open_ts"].to_list()[0] is None
    assert out["rpf_align_15m_bar_open_ts"].to_list()[1] == _ts("2026-01-01T00:00:00")
    assert out["_rpf_src_15m_open"].to_list()[2] == 100.0


def test_safe_math_helpers_return_defaults_for_bad_denominators() -> None:
    df = pl.DataFrame({"a": [1.0, 2.0, float("nan")], "b": [2.0, 0.0, 1.0]})

    out = df.select(
        safe_div_expr(pl.col("a"), pl.col("b")).alias("div"),
        pct_change_expr(pl.col("a"), pl.col("b")).alias("pct"),
    )

    assert out["div"].to_list() == [0.5, 0.0, 0.0]
    assert out["pct"].to_list() == [-0.5, 0.0, 0.0]


def test_volatility_state_features_are_finite_and_causal() -> None:
    rows = pl.DataFrame(
        {
            "timestamp": [_ts(f"2026-01-01T00:0{i}:00") for i in range(6)],
            "batch_id": [1] * 6,
            "tb_volatility_pct": [0.01, 0.011, 0.012, 0.013, 0.014, 0.015],
            "tb_atr_pct_14": [0.012] * 6,
            "tb_realized_vol_120": [0.006] * 6,
            "_rpf_src_15m_open": [100.0] * 6,
            "_rpf_src_15m_high": [103.0] * 6,
            "_rpf_src_15m_low": [99.0] * 6,
            "_rpf_src_15m_close": [102.0] * 6,
        }
    )

    out = add_volatility_state_features(rows, timeframes=("15m",), lookbacks=(3,))
    cols = feature_columns(timeframes=("15m",), lookbacks=(3,))

    assert set(cols).issubset(out.columns)
    assert (
        out.select(pl.all_horizontal([pl.col(col).is_finite() for col in cols]))
        .to_series()
        .all()
    )
    assert out["rpf_vol_15m_range_to_tb_vol"][0] == pytest.approx(
        _positive_vol_unit_bnd(((103.0 - 99.0) / 102.0) / 0.01)
    )
    assert out["rpf_vol_15m_abs_ret_to_tb_vol"][0] == pytest.approx(
        _positive_vol_unit_bnd(((102.0 - 100.0) / 100.0) / 0.01)
    )
    assert round(out["rpf_vol_atr_std_dominance_bnd"][0], 6) == 0.333333
    assert out["rpf_vol_tb_vol_chg_l3"][3] == pytest.approx(0.3)


def test_scale_sensitive_features_are_causally_bounded() -> None:
    rows = pl.DataFrame(
        {
            "timestamp": [_ts(f"2026-01-01T00:{i:02d}:00") for i in range(8)],
            "batch_id": [1] * 8,
            "close": [100.0] * 8,
            "tb_volatility_pct": [
                0.01,
                0.010000001,
                0.010000002,
                0.010000003,
                0.010000004,
                0.5,
                0.01,
                0.01,
            ],
            "tb_atr_pct_14": [0.012] * 8,
            "tb_realized_vol_120": [0.006] * 8,
            "_rpf_src_15m_open": [100.0] * 8,
            "_rpf_src_15m_high": [1000.0] * 8,
            "_rpf_src_15m_low": [1.0] * 8,
            "_rpf_src_15m_close": [100.0] * 8,
            "_rpf_src_15m__rpf_room_channel_high_l2": [1000.0] * 8,
            "_rpf_src_15m__rpf_room_channel_low_l2": [1.0] * 8,
            "_rpf_src_15m__rpf_room_value_l2": [1.0] * 8,
        }
    )

    vol = add_volatility_state_features(rows, timeframes=("15m",), lookbacks=(3,))
    room = add_structural_room_features(vol, timeframes=("15m",), lookbacks=(2,))

    assert room["rpf_vol_tb_vol_z_l3"].abs().max() <= 8.0
    assert room["rpf_vol_15m_range_to_tb_vol"].min() >= 0.0
    assert room["rpf_vol_15m_range_to_tb_vol"].max() <= 1.0
    assert room["rpf_room_15m_up_to_high_l2_vol"].min() >= 0.0
    assert room["rpf_room_15m_up_to_high_l2_vol"].max() <= 1.0
    assert room["rpf_room_15m_value_dist_l2_vol"].abs().max() <= 1.0


def test_structural_room_sources_use_prior_bars_only() -> None:
    bars = pl.DataFrame(
        {
            "timestamp": [
                _ts("2026-01-01T00:00:00"),
                _ts("2026-01-01T00:15:00"),
                _ts("2026-01-01T00:30:00"),
            ],
            "open": [100.0, 100.0, 100.0],
            "high": [110.0, 120.0, 150.0],
            "low": [90.0, 80.0, 70.0],
            "close": [100.0, 100.0, 100.0],
            "volume": [1.0, 1.0, 1.0],
        }
    )

    out = enrich_structural_room_sources(bars, lookbacks=(2,))

    assert out["_rpf_room_channel_high_l2"].to_list() == [None, None, 120.0]
    assert out["_rpf_room_channel_low_l2"].to_list() == [None, None, 80.0]


def test_structural_room_features_are_finite_and_directional() -> None:
    rows = pl.DataFrame(
        {
            "timestamp": [_ts("2026-01-01T00:30:00")],
            "batch_id": [1],
            "close": [100.0],
            "tb_volatility_pct": [0.01],
            "_rpf_src_15m__rpf_room_channel_high_l2": [110.0],
            "_rpf_src_15m__rpf_room_channel_low_l2": [90.0],
            "_rpf_src_15m__rpf_room_value_l2": [95.0],
        }
    )

    out = add_structural_room_features(rows, timeframes=("15m",), lookbacks=(2,))
    cols = structural_feature_columns(timeframes=("15m",), lookbacks=(2,))

    assert set(cols).issubset(out.columns)
    assert (
        out.select(pl.all_horizontal([pl.col(col).is_finite() for col in cols]))
        .to_series()
        .all()
    )
    assert out["rpf_room_15m_up_to_high_l2_vol"][0] == pytest.approx(
        _positive_vol_unit_bnd(10.0)
    )
    assert out["rpf_room_15m_down_to_low_l2_vol"][0] == pytest.approx(
        _positive_vol_unit_bnd(10.0)
    )
    assert out["rpf_room_15m_room_balance_l2_vol"][0] == pytest.approx(0.0)
    assert out["rpf_room_15m_up_room_share_l2_bnd"][0] == pytest.approx(0.5)
    assert out["rpf_room_15m_donchian_pos_l2_bnd"][0] == pytest.approx(0.5)
    assert out["rpf_room_15m_value_dist_l2_vol"][0] == pytest.approx(
        _signed_vol_unit_bnd(5.0)
    )


def test_acceptance_sources_use_closed_bar_history() -> None:
    bars = pl.DataFrame(
        {
            "timestamp": [
                _ts("2026-01-01T00:00:00"),
                _ts("2026-01-01T00:15:00"),
                _ts("2026-01-01T00:30:00"),
                _ts("2026-01-01T00:45:00"),
            ],
            "open": [100.0, 100.0, 101.0, 102.0],
            "high": [102.0, 103.0, 104.0, 105.0],
            "low": [99.0, 100.0, 101.0, 102.0],
            "close": [101.0, 102.0, 103.0, 104.0],
            "volume": [1.0, 1.0, 1.0, 1.0],
        }
    )

    out = enrich_acceptance_persistence_sources(bars, lookbacks=(2,))

    prior_value = (
        ((102.0 + 99.0 + 101.0) / 3.0) + ((103.0 + 100.0 + 102.0) / 3.0)
    ) / 2.0
    assert out["_rpf_accept_value_l2"].to_list()[2] == pytest.approx(prior_value)
    assert out["_rpf_accept_close_loc_avg_l2"].to_list()[2] == pytest.approx(2.0 / 3.0)
    assert out["_rpf_accept_body_persist_l2"].to_list()[2] > 0
    assert out["_rpf_accept_return_persist_l2"].to_list()[2] > 0


def test_acceptance_features_are_finite_and_directional() -> None:
    rows = pl.DataFrame(
        {
            "timestamp": [_ts("2026-01-01T00:30:00")],
            "batch_id": [1],
            "close": [105.0],
            "tb_volatility_pct": [0.01],
            "rpf_align_15m_has_closed_bar": [True],
            "_rpf_src_15m_open": [100.0],
            "_rpf_src_15m_close": [103.0],
            "_rpf_src_15m__rpf_accept_close_loc_avg_l2": [0.75],
            "_rpf_src_15m__rpf_accept_close_loc_balance_l2": [0.5],
            "_rpf_src_15m__rpf_accept_body_persist_l2": [0.4],
            "_rpf_src_15m__rpf_accept_return_persist_l2": [1.0],
            "_rpf_src_15m__rpf_accept_above_value_share_l2": [1.0],
            "_rpf_src_15m__rpf_accept_below_value_share_l2": [0.0],
            "_rpf_src_15m__rpf_accept_value_accept_balance_l2": [1.0],
            "_rpf_src_15m__rpf_accept_value_l2": [100.0],
            "_rpf_src_15m__rpf_accept_trend_eff_l2": [0.8],
            "_rpf_src_15m__rpf_accept_up_pullback_shallow_l2": [0.9],
            "_rpf_src_15m__rpf_accept_down_pullback_shallow_l2": [0.0],
        }
    )

    out = add_acceptance_persistence_features(rows, timeframes=("15m",), lookbacks=(2,))
    cols = acceptance_feature_columns(timeframes=("15m",), lookbacks=(2,))

    assert set(cols).issubset(out.columns)
    assert (
        out.select(pl.all_horizontal([pl.col(col).is_finite() for col in cols]))
        .to_series()
        .all()
    )
    assert out["rpf_accept_15m_value_dist_l2_vol"][0] == pytest.approx(
        _signed_vol_unit_bnd(((105.0 - 100.0) / 105.0) / 0.01)
    )
    assert out["rpf_accept_tf_bull_agreement_share_bnd"][0] == pytest.approx(1.0)
    assert out["rpf_accept_tf_direction_agreement_bnd"][0] == pytest.approx(1.0)


def test_rejection_chop_sources_detect_wicks_and_failed_breaks() -> None:
    bars = pl.DataFrame(
        {
            "timestamp": [
                _ts("2026-01-01T00:00:00"),
                _ts("2026-01-01T00:15:00"),
                _ts("2026-01-01T00:30:00"),
                _ts("2026-01-01T00:45:00"),
            ],
            "open": [100.0, 100.0, 101.0, 101.0],
            "high": [101.0, 102.0, 104.0, 102.0],
            "low": [99.0, 99.0, 100.0, 98.0],
            "close": [100.0, 101.0, 101.0, 101.0],
            "volume": [1.0, 1.0, 1.0, 1.0],
        }
    )

    out = enrich_rejection_chop_sources(bars, lookbacks=(2,))

    assert "_rpf_chop_upper_reject_l2" in out.columns
    assert "_rpf_chop_lower_reject_l2" in out.columns
    assert out["_rpf_chop_failed_up_break_l2"].to_list()[2] == pytest.approx(0.5)
    assert out["_rpf_chop_failed_down_break_l2"].to_list()[3] == pytest.approx(0.5)
    assert (
        out["_rpf_chop_upper_reject_l2"].to_list()[2]
        > out["_rpf_chop_lower_reject_l2"].to_list()[2]
    )


def test_rejection_chop_features_are_finite_and_bounded() -> None:
    rows = pl.DataFrame(
        {
            "timestamp": [_ts("2026-01-01T00:30:00")],
            "batch_id": [1],
            "_rpf_src_15m__rpf_chop_upper_reject_l2": [0.7],
            "_rpf_src_15m__rpf_chop_lower_reject_l2": [0.2],
            "_rpf_src_15m__rpf_chop_reject_balance_l2": [0.5],
            "_rpf_src_15m__rpf_chop_two_sided_l2": [0.6],
            "_rpf_src_15m__rpf_chop_reversal_rate_l2": [0.5],
            "_rpf_src_15m__rpf_chop_path_eff_l2": [0.3],
            "_rpf_src_15m__rpf_chop_path_chop_l2": [0.7],
            "_rpf_src_15m__rpf_chop_failed_up_break_l2": [0.25],
            "_rpf_src_15m__rpf_chop_failed_down_break_l2": [0.0],
            "_rpf_src_15m__rpf_chop_failed_break_balance_l2": [0.25],
        }
    )

    out = add_rejection_chop_features(rows, timeframes=("15m",), lookbacks=(2,))
    cols = rejection_chop_feature_columns(timeframes=("15m",), lookbacks=(2,))

    assert set(cols).issubset(out.columns)
    assert (
        out.select(pl.all_horizontal([pl.col(col).is_finite() for col in cols]))
        .to_series()
        .all()
    )
    assert out["rpf_chop_15m_upper_reject_l2_bnd"][0] == pytest.approx(0.7)
    assert out["rpf_chop_15m_failed_break_balance_l2_bnd"][0] == pytest.approx(0.25)


def test_spike_breakout_sources_use_prior_channels_and_volume_impulse() -> None:
    bars = pl.DataFrame(
        {
            "timestamp": [
                _ts("2026-01-01T00:00:00"),
                _ts("2026-01-01T00:15:00"),
                _ts("2026-01-01T00:30:00"),
                _ts("2026-01-01T00:45:00"),
            ],
            "open": [100.0, 100.0, 101.0, 103.0],
            "high": [101.0, 102.0, 104.0, 108.0],
            "low": [99.0, 99.0, 100.0, 102.0],
            "close": [100.0, 101.0, 103.0, 107.0],
            "volume": [10.0, 12.0, 30.0, 50.0],
        }
    )

    out = enrich_spike_breakout_sources(bars, lookbacks=(2,))

    assert out["_rpf_spike_prior_high_l2"].to_list()[2] == pytest.approx(102.0)
    assert out["_rpf_spike_prior_low_l2"].to_list()[2] == pytest.approx(99.0)
    assert (
        out["_rpf_spike_up_impulse_l2"].to_list()[3]
        > out["_rpf_spike_down_impulse_l2"].to_list()[3]
    )
    assert out["_rpf_spike_up_volume_impulse_l2"].to_list()[3] > 0.0
    assert out["_rpf_spike_tail_asym_l2"].to_list()[3] > 0.0


def test_spike_breakout_features_are_finite_and_directional() -> None:
    rows = pl.DataFrame(
        {
            "timestamp": [_ts("2026-01-01T00:30:00")],
            "batch_id": [1],
            "close": [105.0],
            "tb_volatility_pct": [0.01],
            "_rpf_src_15m__rpf_spike_prior_high_l2": [104.0],
            "_rpf_src_15m__rpf_spike_prior_low_l2": [95.0],
            "_rpf_src_15m__rpf_spike_squeeze_l2": [0.4],
            "_rpf_src_15m__rpf_spike_release_l2": [0.7],
            "_rpf_src_15m__rpf_spike_squeeze_release_l2": [0.28],
            "_rpf_src_15m__rpf_spike_up_impulse_l2": [0.6],
            "_rpf_src_15m__rpf_spike_down_impulse_l2": [0.1],
            "_rpf_src_15m__rpf_spike_impulse_balance_l2": [0.5],
            "_rpf_src_15m__rpf_spike_up_volume_impulse_l2": [0.4],
            "_rpf_src_15m__rpf_spike_down_volume_impulse_l2": [0.05],
            "_rpf_src_15m__rpf_spike_volume_impulse_balance_l2": [0.35],
            "_rpf_src_15m__rpf_spike_tail_asym_l2": [0.425],
        }
    )

    out = add_spike_breakout_features(rows, timeframes=("15m",), lookbacks=(2,))
    cols = spike_breakout_feature_columns(timeframes=("15m",), lookbacks=(2,))

    assert set(cols).issubset(out.columns)
    assert (
        out.select(pl.all_horizontal([pl.col(col).is_finite() for col in cols]))
        .to_series()
        .all()
    )
    assert out["rpf_spike_15m_up_breakout_l2_vol"][0] == pytest.approx(
        _positive_vol_unit_bnd(((105.0 - 104.0) / 105.0) / 0.01)
    )
    assert out["rpf_spike_15m_down_breakdown_l2_vol"][0] == pytest.approx(0.0)
    assert out["rpf_spike_15m_tail_asym_l2_bnd"][0] == pytest.approx(0.425)


def test_liquidity_sources_handle_zero_volume_and_directional_pressure() -> None:
    bars = pl.DataFrame(
        {
            "timestamp": [
                _ts("2026-01-01T00:00:00"),
                _ts("2026-01-01T00:15:00"),
                _ts("2026-01-01T00:30:00"),
                _ts("2026-01-01T00:45:00"),
            ],
            "open": [100.0, 100.0, 101.0, 102.0],
            "high": [101.0, 102.0, 103.0, 103.0],
            "low": [99.0, 99.0, 100.0, 99.0],
            "close": [100.0, 101.0, 102.0, 100.0],
            "volume": [0.0, 10.0, 30.0, 5.0],
        }
    )

    out = enrich_liquidity_volume_pressure_sources(bars, lookbacks=(2,))

    for col in (
        "_rpf_liq_volume_z_l2",
        "_rpf_liq_dollar_volume_rel_l2",
        "_rpf_liq_volume_wakeup_l2",
        "_rpf_liq_volume_pressure_balance_l2",
        "_rpf_liq_obv_slope_l2",
        "_rpf_liq_money_flow_balance_l2",
        "_rpf_liq_zero_volume_share_l2",
    ):
        assert col in out.columns
        assert out[col].is_finite().all()

    assert out["_rpf_liq_up_volume_share_l2"].to_list()[2] == pytest.approx(1.0)
    assert out["_rpf_liq_down_volume_share_l2"].to_list()[2] == pytest.approx(0.0)
    assert out["_rpf_liq_volume_pressure_balance_l2"].to_list()[2] == pytest.approx(1.0)
    assert out["_rpf_liq_volume_pressure_balance_l2"].to_list()[3] < 1.0
    assert out["_rpf_liq_zero_volume_share_l2"].to_list()[1] == pytest.approx(0.5)


def test_liquidity_features_are_finite_and_bounded() -> None:
    rows = pl.DataFrame(
        {
            "timestamp": [_ts("2026-01-01T00:30:00")],
            "batch_id": [1],
            "_rpf_src_15m__rpf_liq_volume_z_l2": [12.0],
            "_rpf_src_15m__rpf_liq_dollar_volume_rel_l2": [0.7],
            "_rpf_src_15m__rpf_liq_volume_wakeup_l2": [0.4],
            "_rpf_src_15m__rpf_liq_up_volume_share_l2": [0.8],
            "_rpf_src_15m__rpf_liq_down_volume_share_l2": [0.2],
            "_rpf_src_15m__rpf_liq_volume_pressure_balance_l2": [0.6],
            "_rpf_src_15m__rpf_liq_obv_slope_l2": [0.6],
            "_rpf_src_15m__rpf_liq_money_flow_balance_l2": [-0.3],
            "_rpf_src_15m__rpf_liq_zero_volume_share_l2": [0.0],
        }
    )

    out = add_liquidity_volume_pressure_features(
        rows, timeframes=("15m",), lookbacks=(2,)
    )
    cols = liquidity_feature_columns(timeframes=("15m",), lookbacks=(2,))

    assert set(cols).issubset(out.columns)
    assert (
        out.select(pl.all_horizontal([pl.col(col).is_finite() for col in cols]))
        .to_series()
        .all()
    )
    assert out["rpf_liq_15m_volume_z_l2"][0] == pytest.approx(8.0)
    assert out["rpf_liq_15m_volume_pressure_balance_l2_bnd"][0] == pytest.approx(0.6)
    assert out["rpf_liq_15m_money_flow_balance_l2_bnd"][0] == pytest.approx(-0.3)


def test_regime_sources_use_metadata_and_closed_bar_history() -> None:
    bars = pl.DataFrame(
        {
            "timestamp": [
                _ts("2026-01-01T00:00:00"),
                _ts("2026-01-01T00:15:00"),
                _ts("2026-01-01T00:30:00"),
                _ts("2026-01-01T00:45:00"),
            ],
            "open": [100.0, 100.0, 101.0, 102.0],
            "high": [101.0, 102.0, 103.0, 105.0],
            "low": [99.0, 99.0, 100.0, 101.0],
            "close": [100.0, 101.0, 102.0, 104.0],
            "volume": [1.0, 1.0, 1.0, 1.0],
            "is_market_open": [True, True, True, True],
            "is_synthetic_no_trade": [False, False, False, False],
            "is_open_session_gap_fill": [False, False, True, False],
            "minutes_since_prev_real_bar": [1, 1, 15, 1],
            "session_bar_pos": [0, 1, 2, 3],
            "session_minutes_to_close": [45, 30, 15, 0],
            "is_session_open_bar": [True, False, False, False],
            "is_session_close_bar": [False, False, False, True],
            "is_weekly_open_bar": [True, False, False, False],
            "is_weekly_close_bar": [False, False, False, True],
        }
    )

    out = enrich_regime_calendar_state_sources(bars, lookbacks=(2,))

    assert out["_rpf_regime_market_open"].to_list() == [1.0, 1.0, 1.0, 1.0]
    assert out["_rpf_regime_gap_fill"].to_list()[2] == pytest.approx(1.0)
    assert out["_rpf_regime_session_open"].to_list()[0] == pytest.approx(1.0)
    assert out["_rpf_regime_weekly_open"].to_list()[0] == pytest.approx(1.0)
    assert "_rpf_regime_session_progress" not in out.columns
    assert "_rpf_regime_minutes_to_close" not in out.columns
    assert "_rpf_regime_session_close" not in out.columns
    assert "_rpf_regime_weekly_close" not in out.columns
    assert out["_rpf_regime_trend_eff_l2"].to_list()[3] > 0.0
    assert out["_rpf_regime_bull_trend_l2"].to_list()[3] == pytest.approx(1.0)
    assert (
        out.select(
            pl.all_horizontal(
                [
                    pl.col(col).is_finite()
                    for col in out.columns
                    if col.startswith("_rpf_regime_")
                ]
            )
        )
        .to_series()
        .all()
    )


def test_regime_calendar_features_are_known_finite_and_bounded() -> None:
    rows = pl.DataFrame(
        {
            "timestamp": [_ts("2026-01-03T12:00:00")],
            "batch_id": [1],
            "_rpf_src_15m__rpf_regime_market_open": [1.0],
            "_rpf_src_15m__rpf_regime_synthetic_no_trade": [0.0],
            "_rpf_src_15m__rpf_regime_gap_fill": [0.0],
            "_rpf_src_15m__rpf_regime_minutes_since_prev_real_bar": [0.1],
            "_rpf_src_15m__rpf_regime_session_open": [0.0],
            "_rpf_src_15m__rpf_regime_weekly_open": [0.0],
            "_rpf_src_15m__rpf_regime_vol_rel_l2": [0.7],
            "_rpf_src_15m__rpf_regime_vol_expanding_l2": [1.0],
            "_rpf_src_15m__rpf_regime_trend_eff_l2": [0.8],
            "_rpf_src_15m__rpf_regime_trend_sign_l2": [1.0],
            "_rpf_src_15m__rpf_regime_trend_alignment_l2": [0.9],
            "_rpf_src_15m__rpf_regime_range_chop_l2": [0.2],
            "_rpf_src_15m__rpf_regime_bull_trend_l2": [1.0],
            "_rpf_src_15m__rpf_regime_bear_trend_l2": [0.0],
        }
    )

    out = add_regime_calendar_state_features(rows, timeframes=("15m",), lookbacks=(2,))
    cols = regime_calendar_feature_columns(timeframes=("15m",), lookbacks=(2,))

    assert set(cols).issubset(out.columns)
    assert all(
        retired not in cols
        for retired in (
            "rpf_regime_15m_session_progress_bnd",
            "rpf_regime_15m_minutes_to_close_bnd",
            "rpf_regime_15m_session_close_bnd",
            "rpf_regime_15m_weekly_close_bnd",
        )
    )
    assert (
        out.select(pl.all_horizontal([pl.col(col).is_finite() for col in cols]))
        .to_series()
        .all()
    )
    assert out["rpf_regime_utc_is_weekend_bnd"][0] == pytest.approx(1.0)
    assert out["rpf_regime_15m_bull_trend_l2_bnd"][0] == pytest.approx(1.0)
    assert out["rpf_regime_15m_trend_alignment_l2_bnd"][0] == pytest.approx(0.9)


def test_interaction_confluence_features_combine_causal_components() -> None:
    rows = pl.DataFrame(
        {
            "timestamp": [_ts("2026-01-01T00:30:00")],
            "batch_id": [1],
            "rpf_spike_15m_squeeze_l2_bnd": [0.8],
            "rpf_spike_15m_up_break_prox_l2_vol": [0.25],
            "rpf_spike_15m_down_break_prox_l2_vol": [2.0],
            "rpf_spike_15m_up_volume_impulse_l2_bnd": [0.6],
            "rpf_spike_15m_down_volume_impulse_l2_bnd": [0.1],
            "rpf_accept_15m_return_persist_l2_bnd": [0.7],
            "rpf_accept_15m_value_accept_balance_l2_bnd": [0.5],
            "rpf_accept_15m_trend_eff_l2_bnd": [0.4],
            "rpf_room_15m_up_room_share_l2_bnd": [0.75],
            "rpf_chop_15m_upper_reject_l2_bnd": [0.2],
            "rpf_chop_15m_lower_reject_l2_bnd": [0.7],
            "rpf_chop_15m_path_chop_l2_bnd": [0.1],
            "rpf_liq_15m_volume_wakeup_l2_bnd": [0.5],
            "rpf_liq_15m_volume_pressure_balance_l2_bnd": [0.6],
            "rpf_regime_15m_trend_alignment_l2_bnd": [0.3],
        }
    )

    out = add_interaction_confluence_features(rows, timeframes=("15m",), lookbacks=(2,))
    cols = interaction_confluence_feature_columns(timeframes=("15m",), lookbacks=(2,))

    assert set(cols).issubset(out.columns)
    assert (
        out.select(pl.all_horizontal([pl.col(col).is_finite() for col in cols]))
        .to_series()
        .all()
    )
    assert out["rpf_conf_15m_up_squeeze_break_l2_bnd"][0] == pytest.approx(0.64)
    assert out["rpf_conf_15m_down_squeeze_break_l2_bnd"][0] == pytest.approx(
        0.2666666667
    )
    assert out["rpf_conf_15m_up_trend_accept_l2_bnd"][0] == pytest.approx(0.475)
    assert out["rpf_conf_15m_down_trend_accept_l2_bnd"][0] == pytest.approx(0.0)
    assert out["rpf_conf_15m_up_volume_impulse_l2_bnd"][0] == pytest.approx(0.18)
    assert out["rpf_conf_15m_down_volume_impulse_l2_bnd"][0] == pytest.approx(0.0)
    assert out["rpf_conf_15m_up_clean_persist_l2_bnd"][0] == pytest.approx(0.342)
    assert out["rpf_conf_15m_up_room_pressure_l2_bnd"][0] == pytest.approx(0.35625)


def test_cross_asset_pair_sources_use_exact_timestamp_matches() -> None:
    target = pl.DataFrame(
        {
            "timestamp": [
                _ts("2026-01-01T00:00:00"),
                _ts("2026-01-01T00:15:00"),
                _ts("2026-01-01T00:30:00"),
            ],
            "open": [100.0, 101.0, 102.0],
            "high": [102.0, 103.0, 104.0],
            "low": [99.0, 100.0, 101.0],
            "close": [101.0, 102.0, 103.0],
            "volume": [10.0, 20.0, 30.0],
        }
    )
    context = pl.DataFrame(
        {
            "timestamp": [
                _ts("2026-01-01T00:00:00"),
                _ts("2026-01-01T00:15:00"),
                _ts("2026-01-01T00:45:00"),
            ],
            "open": [200.0, 199.0, 198.0],
            "high": [201.0, 200.0, 199.0],
            "low": [198.0, 197.0, 196.0],
            "close": [199.0, 198.0, 197.0],
            "volume": [20.0, 10.0, 20.0],
        }
    )

    out = build_cross_asset_pair_sources(
        target, context, context_asset="ETHUSDT", lookbacks=(2,)
    )

    assert out["timestamp"].to_list() == [
        _ts("2026-01-01T00:00:00"),
        _ts("2026-01-01T00:15:00"),
    ]
    assert "_rpf_xasset_ret_spread_l2" in out.columns
    assert out["_rpf_xasset_ret_spread_l2"].to_list()[1] > 0.0
    assert out["_rpf_xasset_context_pressure_l2"].to_list()[1] < 0.0
    assert out["_rpf_xasset_common_direction_l2"].to_list()[1] < 0.0
    assert (
        out.select(
            pl.all_horizontal(
                [
                    pl.col(col).is_finite()
                    for col in out.columns
                    if col.startswith("_rpf_xasset_")
                ]
            )
        )
        .to_series()
        .all()
    )


def test_cross_asset_context_features_are_finite_and_prefixed_by_context_asset() -> (
    None
):
    rows = pl.DataFrame(
        {
            "timestamp": [_ts("2026-01-01T00:30:00")],
            "batch_id": [1],
            "_rpf_src_15m__rpf_xasset_ret_spread_l2": [0.8],
            "_rpf_src_15m__rpf_xasset_rel_strength_l2": [0.2],
            "_rpf_src_15m__rpf_xasset_range_spread_l2": [-0.3],
            "_rpf_src_15m__rpf_xasset_corr_l2": [0.7],
            "_rpf_src_15m__rpf_xasset_context_pressure_l2": [-0.5],
            "_rpf_src_15m__rpf_xasset_common_direction_l2": [-0.4],
            "_rpf_src_15m__rpf_xasset_context_range_share_l2": [1.2],
            "_rpf_src_15m__rpf_xasset_volume_rel_spread_l2": [0.6],
        }
    )

    out = add_cross_asset_context_features(
        rows, context_asset="ETHUSDT", timeframes=("15m",), lookbacks=(2,)
    )
    cols = cross_asset_feature_columns(
        context_assets=("ETHUSDT",), timeframes=("15m",), lookbacks=(2,)
    )

    assert set(cols).issubset(out.columns)
    assert (
        out.select(pl.all_horizontal([pl.col(col).is_finite() for col in cols]))
        .to_series()
        .all()
    )
    assert out["rpf_xasset_ethusdt_15m_ret_spread_l2_bnd"][0] == pytest.approx(0.8)
    assert out["rpf_xasset_ethusdt_15m_context_pressure_l2_bnd"][0] == pytest.approx(
        -0.5
    )
    assert out["rpf_xasset_ethusdt_15m_context_range_share_l2_bnd"][0] == pytest.approx(
        1.0
    )


def test_unsupervised_factor_layer_features_are_bounded_and_causal_component_derived() -> (
    None
):
    rows = pl.DataFrame(
        {
            "timestamp": [_ts("2026-01-01T00:30:00")],
            "batch_id": [1],
            "rpf_vol_15m_range_to_tb_vol": [2.0],
            "rpf_spike_15m_squeeze_release_l2_bnd": [0.6],
            "rpf_chop_15m_two_sided_l2_bnd": [0.5],
            "rpf_regime_15m_range_chop_l2_bnd": [0.4],
            "rpf_conf_15m_squeeze_break_balance_l2_bnd": [0.3],
            "rpf_accept_15m_return_persist_l2_bnd": [0.8],
            "rpf_accept_15m_value_accept_balance_l2_bnd": [0.6],
            "rpf_accept_15m_trend_eff_l2_bnd": [0.5],
            "rpf_spike_15m_impulse_balance_l2_bnd": [0.4],
            "rpf_liq_15m_volume_pressure_balance_l2_bnd": [0.7],
            "rpf_regime_15m_trend_alignment_l2_bnd": [0.6],
            "rpf_conf_15m_trend_accept_balance_l2_bnd": [0.5],
            "rpf_xasset_ethusdt_15m_ret_spread_l2_bnd": [0.2],
            "rpf_xasset_ethusdt_15m_rel_strength_l2_bnd": [0.1],
            "rpf_xasset_ethusdt_15m_context_pressure_l2_bnd": [0.3],
            "rpf_xasset_ethusdt_15m_common_direction_l2_bnd": [0.4],
            "rpf_spike_15m_release_l2_bnd": [0.7],
            "rpf_liq_15m_volume_wakeup_l2_bnd": [0.8],
            "rpf_spike_15m_tail_asym_l2_bnd": [-0.6],
            "rpf_conf_15m_volume_impulse_balance_l2_bnd": [0.5],
            "rpf_chop_15m_reject_balance_l2_bnd": [-0.2],
            "rpf_chop_15m_failed_break_balance_l2_bnd": [0.1],
            "rpf_chop_15m_upper_reject_l2_bnd": [0.3],
            "rpf_chop_15m_lower_reject_l2_bnd": [0.1],
            "rpf_chop_15m_path_chop_l2_bnd": [0.2],
        }
    )

    out = add_unsupervised_factor_layer_features(
        rows,
        timeframes=("15m",),
        lookbacks=(2,),
        context_assets=("ETHUSDT",),
    )
    cols = unsupervised_factor_feature_columns(timeframes=("15m",), lookbacks=(2,))

    assert set(cols).issubset(out.columns)
    assert (
        out.select(pl.all_horizontal([pl.col(col).is_finite() for col in cols]))
        .to_series()
        .all()
    )
    assert out["rpf_factor_15m_direction_l2_bnd"][0] > 0.0
    assert 0.0 <= out["rpf_factor_15m_path_width_l2_bnd"][0] <= 1.0
    assert 0.0 <= out["rpf_factor_15m_anomaly_l2_bnd"][0] <= 1.0


def test_sequence_embedding_layer_summarizes_factor_stack() -> None:
    rows = pl.DataFrame(
        {
            "timestamp": [_ts("2026-01-01T00:30:00")],
            "batch_id": [1],
            "rpf_factor_15m_direction_l2_bnd": [0.8],
            "rpf_factor_1h_direction_l2_bnd": [0.4],
            "rpf_factor_15m_path_width_l2_bnd": [0.7],
            "rpf_factor_1h_path_width_l2_bnd": [0.3],
            "rpf_factor_15m_shock_l2_bnd": [0.6],
            "rpf_factor_1h_shock_l2_bnd": [0.2],
            "rpf_factor_15m_persistence_l2_bnd": [0.5],
            "rpf_factor_1h_persistence_l2_bnd": [0.1],
            "rpf_factor_15m_clean_direction_l2_bnd": [0.7],
            "rpf_factor_1h_clean_direction_l2_bnd": [0.2],
        }
    )

    out = add_sequence_embedding_layer_features(
        rows, timeframes=("15m", "1h"), lookbacks=(2,)
    )
    cols = sequence_embedding_feature_columns(lookbacks=(2,))

    assert set(cols).issubset(out.columns)
    assert (
        out.select(pl.all_horizontal([pl.col(col).is_finite() for col in cols]))
        .to_series()
        .all()
    )
    assert out["rpf_seq_direction_mean_l2_bnd"][0] == pytest.approx(0.6)
    assert out["rpf_seq_direction_slope_l2_bnd"][0] == pytest.approx(0.4)
    assert out["rpf_seq_width_mean_l2_bnd"][0] == pytest.approx(0.5)


def test_materializer_writes_manifest_and_feature_catalog(tmp_path: Path) -> None:
    project = tmp_path
    label_dir = (
        project
        / "data/htf_multiasset/btcusdt/htf_4class_labels_reg_distance_horizon_vol_v2/1m"
    )
    canonical_dir = project / "data/htf_multiasset/btcusdt/htf_canonical_ohlcv/15m"
    label_dir.mkdir(parents=True)
    canonical_dir.mkdir(parents=True)

    labels = pl.DataFrame(
        {
            "timestamp": [_ts("2026-01-01T00:15:00"), _ts("2026-01-01T00:16:00")],
            "batch_id": [1, 1],
            "close": [101.0, 101.5],
            "tb_volatility_pct": [0.01, 0.011],
            "tb_atr_pct_14": [0.012, 0.012],
            "tb_realized_vol_120": [0.006, 0.006],
        }
    )
    labels.write_parquet(label_dir / "batch_0001.parquet")

    bars = pl.DataFrame(
        {
            "timestamp": [_ts("2026-01-01T00:00:00")],
            "open": [100.0],
            "high": [103.0],
            "low": [99.0],
            "close": [102.0],
            "volume": [10.0],
        }
    )
    bars.write_parquet(canonical_dir / "btcusdt_15m_canonical.parquet")

    result = materialize_regression_feature_roots(
        project_root=project,
        assets=("BTCUSDT",),
        roots=("8h/B",),
        families=(
            "foundation_alignment",
            "volatility_state",
            "structural_room",
            "acceptance_persistence",
            "rejection_chop",
            "spike_breakout",
            "liquidity_volume_pressure",
            "regime_calendar_state",
            "interaction_confluence",
        ),
        timeframes=("15m",),
        lookbacks=(3,),
        room_lookbacks=(2,),
        accept_lookbacks=(2,),
        chop_lookbacks=(2,),
        spike_lookbacks=(2,),
        liq_lookbacks=(2,),
        regime_lookbacks=(2,),
        confluence_lookbacks=(2,),
    )[0]

    assert result.rows == 2
    assert result.feature_count == len(
        feature_columns(timeframes=("15m",), lookbacks=(3,))
    ) + len(structural_feature_columns(timeframes=("15m",), lookbacks=(2,))) + len(
        acceptance_feature_columns(timeframes=("15m",), lookbacks=(2,))
    ) + len(rejection_chop_feature_columns(timeframes=("15m",), lookbacks=(2,))) + len(
        spike_breakout_feature_columns(timeframes=("15m",), lookbacks=(2,))
    ) + len(liquidity_feature_columns(timeframes=("15m",), lookbacks=(2,))) + len(
        regime_calendar_feature_columns(timeframes=("15m",), lookbacks=(2,))
    ) + len(interaction_confluence_feature_columns(timeframes=("15m",), lookbacks=(2,)))
    assert result.duplicate_count == 0
    assert result.null_feature_count == 0

    manifest = json.loads((result.output_dir / "manifest.json").read_text())
    catalog = json.loads((result.output_dir / "feature_catalog.json").read_text())
    written = pl.read_parquet(result.output_dir / "batch_0001.parquet")

    assert manifest["feature_set"] == "regression_path_features_v1"
    assert manifest["families"] == [
        "foundation_alignment",
        "volatility_state",
        "structural_room",
        "acceptance_persistence",
        "rejection_chop",
        "spike_breakout",
        "liquidity_volume_pressure",
        "regime_calendar_state",
        "interaction_confluence",
    ]
    assert len(catalog) == result.feature_count
    catalog_names = {entry["name"] for entry in catalog}
    assert {
        "rpf_regime_15m_session_progress_bnd",
        "rpf_regime_15m_minutes_to_close_bnd",
        "rpf_regime_15m_session_close_bnd",
        "rpf_regime_15m_weekly_close_bnd",
    }.isdisjoint(catalog_names)
    assert "rpf_vol_atr_std_dominance_bnd" in written.columns
    assert "rpf_room_15m_donchian_pos_l2_bnd" in written.columns
    assert "rpf_accept_15m_trend_eff_l2_bnd" in written.columns
    assert "rpf_chop_15m_path_chop_l2_bnd" in written.columns
    assert "rpf_spike_15m_tail_asym_l2_bnd" in written.columns
    assert "rpf_liq_15m_volume_pressure_balance_l2_bnd" in written.columns
    assert "rpf_regime_15m_trend_alignment_l2_bnd" in written.columns
    assert "rpf_conf_15m_up_clean_persist_l2_bnd" in written.columns
    assert "_rpf_src_15m_open" not in written.columns


def test_materializer_writes_cross_asset_context_features(tmp_path: Path) -> None:
    project = tmp_path
    label_dir = (
        project
        / "data/htf_multiasset/btcusdt/htf_4class_labels_reg_distance_horizon_vol_v2/1m"
    )
    btc_canonical_dir = project / "data/htf_multiasset/btcusdt/htf_canonical_ohlcv/15m"
    eth_canonical_dir = project / "data/htf_multiasset/ethusdt/htf_canonical_ohlcv/15m"
    label_dir.mkdir(parents=True)
    btc_canonical_dir.mkdir(parents=True)
    eth_canonical_dir.mkdir(parents=True)

    labels = pl.DataFrame(
        {
            "timestamp": [_ts("2026-01-01T00:15:00"), _ts("2026-01-01T00:30:00")],
            "batch_id": [1, 2],
            "close": [101.0, 102.0],
            "tb_volatility_pct": [0.01, 0.011],
            "tb_atr_pct_14": [0.012, 0.012],
            "tb_realized_vol_120": [0.006, 0.006],
        }
    )
    labels.filter(pl.col("batch_id") == 1).write_parquet(
        label_dir / "batch_0001.parquet"
    )
    labels.filter(pl.col("batch_id") == 2).write_parquet(
        label_dir / "batch_0002.parquet"
    )

    btc_bars = pl.DataFrame(
        {
            "timestamp": [_ts("2026-01-01T00:00:00"), _ts("2026-01-01T00:15:00")],
            "open": [100.0, 101.0],
            "high": [102.0, 103.0],
            "low": [99.0, 100.0],
            "close": [101.0, 102.0],
            "volume": [10.0, 20.0],
        }
    )
    eth_bars = pl.DataFrame(
        {
            "timestamp": [_ts("2026-01-01T00:00:00"), _ts("2026-01-01T00:15:00")],
            "open": [200.0, 199.0],
            "high": [201.0, 200.0],
            "low": [198.0, 197.0],
            "close": [199.0, 198.0],
            "volume": [20.0, 10.0],
        }
    )
    btc_bars.write_parquet(btc_canonical_dir / "btcusdt_15m_canonical.parquet")
    eth_bars.write_parquet(eth_canonical_dir / "ethusdt_15m_canonical.parquet")

    result = materialize_regression_feature_roots(
        project_root=project,
        assets=("BTCUSDT",),
        roots=("8h/B",),
        families=("foundation_alignment", "volatility_state", "cross_asset_context"),
        timeframes=("15m",),
        lookbacks=(3,),
        xasset_lookbacks=(2,),
        batch_chunk_size=1,
    )[0]

    manifest = json.loads((result.output_dir / "manifest.json").read_text())
    catalog = json.loads((result.output_dir / "feature_catalog.json").read_text())
    written = pl.read_parquet(result.output_dir / "batch_0002.parquet")

    assert result.rows == 2
    assert result.feature_count == len(
        feature_columns(timeframes=("15m",), lookbacks=(3,))
    ) + len(
        cross_asset_feature_columns(
            context_assets=("ETHUSDT",), timeframes=("15m",), lookbacks=(2,)
        )
    )
    assert result.duplicate_count == 0
    assert result.null_feature_count == 0
    assert "cross_asset_context" in manifest["families"]
    assert any(item["family"] == "cross_asset_context" for item in catalog)
    assert "rpf_xasset_ethusdt_15m_ret_spread_l2_bnd" in written.columns
    assert "rpf_xasset_ethusdt_15m_context_pressure_l2_bnd" in written.columns
    assert "_rpf_src_15m__rpf_xasset_ret_spread_l2" not in written.columns


def test_materializer_writes_temporal_memory_features(tmp_path: Path) -> None:
    project = tmp_path
    label_dir = (
        project
        / "data/htf_multiasset/btcusdt/htf_4class_labels_reg_distance_horizon_vol_v2/1m"
    )
    canonical_dir = project / "data/htf_multiasset/btcusdt/htf_canonical_ohlcv/15m"
    label_dir.mkdir(parents=True)
    canonical_dir.mkdir(parents=True)

    labels = pl.DataFrame(
        {
            "timestamp": [
                _ts("2026-01-01T00:15:00"),
                _ts("2026-01-01T00:16:00"),
                _ts("2026-01-01T00:17:00"),
            ],
            "batch_id": [1, 1, 2],
            "close": [101.0, 101.5, 102.0],
            "tb_volatility_pct": [0.01, 0.011, 0.012],
            "tb_atr_pct_14": [0.012, 0.012, 0.013],
            "tb_realized_vol_120": [0.006, 0.006, 0.007],
        }
    )
    labels.filter(pl.col("batch_id") == 1).write_parquet(
        label_dir / "batch_0001.parquet"
    )
    labels.filter(pl.col("batch_id") == 2).write_parquet(
        label_dir / "batch_0002.parquet"
    )

    bars = pl.DataFrame(
        {
            "timestamp": [_ts("2026-01-01T00:00:00")],
            "open": [100.0],
            "high": [103.0],
            "low": [99.0],
            "close": [102.0],
            "volume": [10.0],
        }
    )
    bars.write_parquet(canonical_dir / "btcusdt_15m_canonical.parquet")

    result = materialize_regression_feature_roots(
        project_root=project,
        assets=("BTCUSDT",),
        roots=("8h/B",),
        families=(
            "foundation_alignment",
            "volatility_state",
            "temporal_memory_transforms",
        ),
        timeframes=("15m",),
        lookbacks=(3,),
        memory_lags=(1,),
        memory_ewm_spans=(2,),
        memory_rank_windows=(3,),
        memory_diff_lags=(1,),
        batch_chunk_size=1,
    )[0]

    manifest = json.loads((result.output_dir / "manifest.json").read_text())
    memory_cols = [
        col for col in manifest["feature_columns"] if col.startswith("rpf_mem_")
    ]
    expected_sources = temporal_memory_source_columns(
        tuple(feature_columns(timeframes=("15m",), lookbacks=(3,))),
        timeframes=("15m",),
        room_lookbacks=(4, 16, 48),
        accept_lookbacks=(4, 16, 48),
    )
    expected_memory_cols = temporal_memory_feature_columns(
        source_columns=expected_sources,
        lags=(1,),
        ewm_spans=(2,),
        rank_windows=(3,),
        diff_lags=(1,),
    )
    written = pl.read_parquet(result.output_dir / "batch_0002.parquet")

    assert result.rows == 3
    assert memory_cols == list(expected_memory_cols)
    assert result.null_feature_count == 0
    assert "temporal_memory_transforms" in manifest["families"]
    assert "rpf_mem_vol_atr_std_dominance_bnd_lag1" in written.columns
    assert written["rpf_mem_vol_atr_std_dominance_bnd_lag1"][0] != 0.0


def test_materializer_rejects_unknown_families() -> None:
    with pytest.raises(ValueError, match="Unknown feature family"):
        parse_families("foundation_alignment,not_a_real_family")


def test_temporal_memory_state_is_prior_row_and_chunk_safe() -> None:
    source = "rpf_vol_atr_std_dominance_bnd"
    state = TemporalMemoryState(
        source_columns=(source,),
        lags=(1,),
        ewm_spans=(2,),
        rank_windows=(3,),
        diff_lags=(1,),
    )

    first = state.transform_frame(pl.DataFrame({source: [1.0, 2.0]}))
    second = state.transform_frame(pl.DataFrame({source: [3.0, 4.0]}))

    assert first["rpf_mem_vol_atr_std_dominance_bnd_lag1"].to_list() == [0.0, 1.0]
    assert second["rpf_mem_vol_atr_std_dominance_bnd_lag1"].to_list() == [2.0, 3.0]
    assert second["rpf_mem_vol_atr_std_dominance_bnd_diff1"].to_list() == [1.0, 1.0]
    assert second["rpf_mem_vol_atr_std_dominance_bnd_rankpos3_bnd"].to_list()[
        0
    ] == pytest.approx(1.0)
    assert second["rpf_mem_vol_atr_std_dominance_bnd_ewm2"].to_list()[
        0
    ] == pytest.approx(1.6666666667)


def test_temporal_memory_source_selection_is_curated() -> None:
    available = (
        "rpf_vol_atr_std_dominance_bnd",
        "rpf_vol_tb_vol_z_l120",
        "rpf_vol_15m_range_to_tb_vol",
        "rpf_room_15m_room_balance_l16_vol",
        "rpf_accept_15m_return_persist_l16_bnd",
        "rpf_accept_tf_direction_agreement_bnd",
        "rpf_accept_15m_return_persist_l48_bnd",
    )

    selected = temporal_memory_source_columns(
        available,
        timeframes=("15m",),
        room_lookbacks=(4, 16, 48),
        accept_lookbacks=(4, 16, 48),
    )

    assert "rpf_vol_atr_std_dominance_bnd" in selected
    assert "rpf_vol_15m_range_to_tb_vol" in selected
    assert "rpf_room_15m_room_balance_l16_vol" in selected
    assert "rpf_accept_15m_return_persist_l16_bnd" in selected
    assert "rpf_accept_tf_direction_agreement_bnd" in selected
    assert "rpf_accept_15m_return_persist_l48_bnd" not in selected

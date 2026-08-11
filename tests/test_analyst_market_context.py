from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import polars as pl
import pytest
from polars.testing import assert_frame_equal

ANALYST_ROOT = (
    Path(__file__).resolve().parents[1] / "Risk_Yield_Meta_Model_Analyst_0_0_1"
)
if str(ANALYST_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYST_ROOT))

from market_context import (  # noqa: E402
    COMPARABLE_VOLATILITY_ID,
    MARKET_CONTEXT_IDS,
    PARTICIPATION_REFERENCE_OCCURRENCES,
    PHASE_ADJUSTED_PARTICIPATION_ID,
    PRIOR_STRUCTURE_ID,
    STRUCTURE_LOOKBACKS,
    VOLATILITY_PERCENTILE_LOOKBACK,
    build_market_context_overlays,
    compute_market_context_frame,
)


def _hourly_frame(rows: int = 320) -> pl.DataFrame:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    values = []
    for index in range(rows):
        base = 100.0 * math.exp((0.0004 * index) + (0.0025 * math.sin(index / 9.0)))
        open_value = base * 0.9997
        close = base * 1.0003
        values.append(
            {
                "timestamp": start + timedelta(hours=index),
                "open": open_value,
                "high": max(open_value, close) * 1.002,
                "low": min(open_value, close) * 0.998,
                "close": close,
                "volume": 100.0 + (index % 24),
            }
        )
    return pl.DataFrame(values)


def _same_phase_daily_frame(
    volumes: list[float],
    *,
    synthetic_index: int | None = None,
    partial_index: int | None = None,
    with_session_phase: bool = False,
) -> pl.DataFrame:
    start = datetime(2026, 1, 1, 10, tzinfo=timezone.utc)
    rows = []
    for index, volume in enumerate(volumes):
        close = 100.0 + (0.1 * index)
        row = {
            "timestamp": start + timedelta(days=index),
            "open": close - 0.1,
            "high": close + 0.4,
            "low": close - 0.4,
            "close": close,
            "volume": volume,
            "is_synthetic_no_trade": index == synthetic_index,
            "is_open_session_gap_fill": False,
            "is_bar_final": index != partial_index,
        }
        if with_session_phase:
            row["session_bar_pos"] = 120
        rows.append(row)
    return pl.DataFrame(rows)


def test_prior_channels_are_strictly_shifted_and_fully_mature() -> None:
    frame = (
        _hourly_frame(70)
        .with_row_index("row_number")
        .with_columns(
            pl.when(pl.col("row_number") == 55)
            .then(pl.lit(500.0))
            .otherwise(pl.col("high"))
            .alias("high")
        )
        .drop("row_number")
    )

    result = compute_market_context_frame(
        frame,
        asset="BTCUSDT",
        timeframe="1h",
    )

    assert result[f"structure_mature_{STRUCTURE_LOOKBACKS[-1]}"][47] is False
    assert result[f"structure_mature_{STRUCTURE_LOOKBACKS[-1]}"][48] is True
    assert result["prior_high_48"][55] < 500.0
    assert result["prior_high_48"][56] == 500.0


def test_structure_position_uses_bounded_log_location() -> None:
    frame = _hourly_frame(90)
    result = compute_market_context_frame(
        frame,
        asset="BTCUSDT",
        timeframe="1h",
    )
    row = result.row(80, named=True)
    expected = math.log(frame["close"][80] / row["prior_low_48"]) / math.log(
        row["prior_high_48"] / row["prior_low_48"]
    )

    assert row["structure_mature"] is True
    assert row["channel_position"] == pytest.approx(min(1.0, max(0.0, expected)))
    assert 0.0 <= row["channel_position"] <= 1.0


def test_structure_classification_and_marker_use_next_observed_bar() -> None:
    base = _hourly_frame(75)
    reference = compute_market_context_frame(base, asset="BTCUSDT", timeframe="1h").row(
        60, named=True
    )
    lower = reference["prior_low_48"]
    upper = reference["prior_high_48"]
    frame = (
        base.with_row_index("row_number")
        .with_columns(
            pl.when(pl.col("row_number") == 60)
            .then(pl.lit((lower + upper) / 2.0))
            .otherwise(pl.col("open"))
            .alias("open"),
            pl.when(pl.col("row_number") == 60)
            .then(pl.lit(upper * 1.51))
            .otherwise(pl.col("high"))
            .alias("high"),
            pl.when(pl.col("row_number") == 60)
            .then(pl.lit(lower * 0.99))
            .otherwise(pl.col("low"))
            .alias("low"),
            pl.when(pl.col("row_number") == 60)
            .then(pl.lit(upper * 1.50))
            .otherwise(pl.col("close"))
            .alias("close"),
        )
        .drop("row_number")
    )
    overlays = build_market_context_overlays(
        frame,
        asset="BTCUSDT",
        timeframe="1h",
    )
    structure = overlays[PRIOR_STRUCTURE_ID]
    source_time = int(frame["timestamp"][60].timestamp())
    action_time = int(frame["timestamp"][61].timestamp())

    marker = next(
        item for item in structure["markers"] if item["source_time"] == source_time
    )
    assert marker["time"] == action_time
    assert marker["state"] == "closed_above_prior_channel"
    assert "Buy" not in marker["text"] and "Sell" not in marker["text"]
    assert any(
        point["time"] == source_time for point in structure["channels"]["48"]["upper"]
    )


def test_degraded_prior_window_suppresses_unqualified_structure_marker() -> None:
    frame = (
        _hourly_frame(75)
        .with_columns(pl.arange(0, pl.len()).eq(20).alias("is_synthetic_no_trade"))
        .with_row_index("row_number")
        .with_columns(
            pl.when(pl.col("row_number") == 60)
            .then(pl.lit(100.0))
            .otherwise(pl.col("open"))
            .alias("open"),
            pl.when(pl.col("row_number") == 60)
            .then(pl.lit(151.0))
            .otherwise(pl.col("high"))
            .alias("high"),
            pl.when(pl.col("row_number") == 60)
            .then(pl.lit(99.0))
            .otherwise(pl.col("low"))
            .alias("low"),
            pl.when(pl.col("row_number") == 60)
            .then(pl.lit(150.0))
            .otherwise(pl.col("close"))
            .alias("close"),
        )
        .drop("row_number")
    )
    result = compute_market_context_frame(frame, asset="BTCUSDT", timeframe="1h")
    assert result["structure_quality"][60] == "degraded_prior_synthetic_or_gap"

    structure = build_market_context_overlays(frame, asset="BTCUSDT", timeframe="1h")[
        PRIOR_STRUCTURE_ID
    ]
    source_time = int(frame["timestamp"][60].timestamp())
    assert all(item["source_time"] != source_time for item in structure["markers"])


def test_rogers_satchell_formula_is_not_absolute_value_repair() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    frame = pl.DataFrame(
        {
            "timestamp": [start, start + timedelta(hours=1)],
            "open": [100.0, 100.0],
            "high": [112.0, 101.0],
            "low": [95.0, 99.0],
            "close": [108.0, 105.0],
            "volume": [10.0, 10.0],
        }
    )
    result = compute_market_context_frame(frame, asset="BTCUSDT", timeframe="1h")
    h = math.log(112.0 / 100.0)
    low = math.log(95.0 / 100.0)
    close = math.log(108.0 / 100.0)

    assert result["rs_variance"][0] == pytest.approx(
        h * (h - close) + low * (low - close)
    )
    assert result["rs_variance"][1] is None
    assert result["volatility_quality"][1] == "invalid_ohlc_or_rs"


def test_volatility_percentile_is_prior_only_and_bounded() -> None:
    frame = _hourly_frame(VOLATILITY_PERCENTILE_LOOKBACK + 80)
    result = compute_market_context_frame(frame, asset="ETHUSDT", timeframe="1h")
    mature = result.filter(pl.col("volatility_mature"))

    assert mature.height > 0
    assert mature["volatility_reference_count"].min() == VOLATILITY_PERCENTILE_LOOKBACK
    assert mature["rs_percentile"].min() >= 0.0
    assert mature["rs_percentile"].max() <= 1.0
    assert mature["rs_fast_slow_ratio_score"].min() >= -1.0
    assert mature["rs_fast_slow_ratio_score"].max() <= 1.0


def test_explicit_session_gap_return_is_separate_from_rs_range() -> None:
    frame = (
        _hourly_frame(80)
        .with_columns(pl.arange(0, pl.len()).eq(60).alias("is_session_open_bar"))
        .with_row_index("row_number")
        .with_columns(
            pl.when(pl.col("row_number") == 60)
            .then(pl.col("open") * 1.03)
            .otherwise(pl.col("open"))
            .alias("open"),
            pl.when(pl.col("row_number") == 60)
            .then(pl.col("high") * 1.04)
            .otherwise(pl.col("high"))
            .alias("high"),
        )
        .drop("row_number")
    )
    result = compute_market_context_frame(frame, asset="ES", timeframe="1h")
    expected = math.log(frame["open"][60] / frame["close"][59])

    assert result["known_session_gap"][60] is True
    assert result["gap_return"][60] == pytest.approx(expected)
    assert result["rs_variance"][60] is not None


def test_phase_adjusted_rvol_uses_twenty_strictly_prior_occurrences() -> None:
    volumes = [100.0] * PARTICIPATION_REFERENCE_OCCURRENCES + [200.0, 100.0]
    frame = _same_phase_daily_frame(volumes)
    result = compute_market_context_frame(frame, asset="BTCUSDT", timeframe="1h")
    row = result.row(PARTICIPATION_REFERENCE_OCCURRENCES, named=True)

    assert row["phase_basis"] == "utc_slot_of_day"
    assert row["participation_reference_count"] == 20
    assert row["participation_expected_volume"] == 100.0
    assert row["participation_rvol"] == 2.0
    assert row["participation_mature"] is True
    assert row["participation_quality"] == "mature"


def test_sessioned_participation_uses_session_bar_position() -> None:
    frame = _same_phase_daily_frame([100.0] * 21, with_session_phase=True)
    result = compute_market_context_frame(frame, asset="ES", timeframe="1h")

    assert result["phase_basis"][0] == "session_bar_pos"
    assert result["participation_phase"][20] == 120
    assert result["participation_mature"][20] is True


def test_crypto_phase_ignores_session_bar_position() -> None:
    frame = _same_phase_daily_frame([100.0] * 21, with_session_phase=True)
    result = compute_market_context_frame(frame, asset="BTCUSDT", timeframe="1h")

    assert result["phase_basis"][0] == "utc_slot_of_day"
    assert result["participation_phase"][0] == 10


def test_synthetic_and_partial_rows_do_not_enter_phase_reference() -> None:
    volumes = [100.0] * 22
    synthetic = compute_market_context_frame(
        _same_phase_daily_frame(volumes, synthetic_index=5),
        asset="BTCUSDT",
        timeframe="1h",
    )
    partial = compute_market_context_frame(
        _same_phase_daily_frame(volumes, partial_index=20),
        asset="BTCUSDT",
        timeframe="1h",
    )

    assert synthetic["participation_reference_count"][20] == 19
    assert synthetic["participation_mature"][20] is False
    assert synthetic["participation_quality"][20] == "provisional_reference_19_of_20"
    assert partial["participation_rvol"][20] is None
    assert partial["participation_quality"][20] == "partial_bar_excluded"
    assert partial["participation_reference_count"][21] == 20


def test_higher_timeframe_constituent_gap_flag_degrades_but_does_not_discard_bar() -> (
    None
):
    frame = _same_phase_daily_frame([100.0] * 260).with_columns(
        pl.lit(True).alias("is_open_session_gap_fill")
    )
    minute = compute_market_context_frame(
        frame,
        asset="EURUSD",
        timeframe="1m",
    )
    daily = compute_market_context_frame(
        frame,
        asset="EURUSD",
        timeframe="1d",
    )

    assert minute["source_quality"][0] == "known_open_session_gap_fill"
    assert minute["rs_variance"].drop_nulls().is_empty()
    assert daily["source_quality"][0] == "observed_with_constituent_gap_fill"
    assert daily["rs_variance"].drop_nulls().len() == daily.height
    assert daily["rs_percentile"].drop_nulls().len() > 0
    assert daily["participation_reference_count"][-1] == 20
    assert "constituent_gap_fill" in daily["volatility_quality"][-1]


def test_market_context_prefix_is_invariant_to_future_ohlcv_mutation() -> None:
    frame = _hourly_frame(340)
    prefix_rows = 275
    mutated = (
        frame.with_row_index("row_number")
        .with_columns(
            pl.when(pl.col("row_number") >= prefix_rows)
            .then(pl.col(column) * 7.0)
            .otherwise(pl.col(column))
            .alias(column)
            for column in ("open", "high", "low", "close", "volume")
        )
        .drop("row_number")
    )
    expected = compute_market_context_frame(
        frame.head(prefix_rows), asset="BTCUSDT", timeframe="1h"
    ).drop("next_action_observed")
    actual = (
        compute_market_context_frame(mutated, asset="BTCUSDT", timeframe="1h")
        .head(prefix_rows)
        .drop("next_action_observed")
    )

    assert_frame_equal(actual, expected, check_exact=True)


def test_overlay_schema_is_json_safe_and_series_are_visibly_bounded() -> None:
    frame = _hourly_frame(340)
    start = frame["timestamp"][300]
    end = frame["timestamp"][330]
    overlays = build_market_context_overlays(
        frame,
        asset="BTCUSDT",
        timeframe="1h",
        visible_start=start,
        visible_end=end,
    )

    assert tuple(overlays) == MARKET_CONTEXT_IDS
    assert len(overlays[PRIOR_STRUCTURE_ID]["channels"]["48"]["upper"]) == 31
    assert all(
        int(start.timestamp())
        <= point["time"]
        <= int((end + timedelta(hours=1)).timestamp())
        for point in overlays[COMPARABLE_VOLATILITY_ID]["volatility_percentile"]
    )
    assert "status" in overlays[PRIOR_STRUCTURE_ID]["last"]
    assert "mature" in overlays[COMPARABLE_VOLATILITY_ID]["last"]
    assert "quality" in overlays[PHASE_ADJUSTED_PARTICIPATION_ID]["last"]
    json.dumps(overlays, allow_nan=False)

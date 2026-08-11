from __future__ import annotations

import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import polars as pl

ANALYST_ROOT = (
    Path(__file__).resolve().parents[1] / "Risk_Yield_Meta_Model_Analyst_0_0_1"
)
if str(ANALYST_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYST_ROOT))

from chart_config import (  # noqa: E402
    CANONICAL_SOURCE,
    CANONICAL_TIMEFRAMES,
    CORE_ASSETS,
    resolve_ohlcv_files,
)
from chart_export import (  # noqa: E402
    INDICATOR_CROSS_TIMEFRAME_CONTEXT,
    build_lightweight_charts_payload,
)
from multi_timeframe_context import (  # noqa: E402
    MTF_CONTEXT_MAPPING,
    build_causal_mtf_context,
    context_timeframes,
)


def _frame(minutes: int, rows: int = 360) -> pl.DataFrame:
    end = datetime(2026, 1, 10, tzinfo=timezone.utc)
    start = end - timedelta(minutes=minutes * rows)
    values = []
    for index in range(rows):
        price = 100.0 * math.exp((0.00025 * index) + (0.002 * math.sin(index / 17.0)))
        values.append(
            {
                "timestamp": start + timedelta(minutes=minutes * index),
                "open": price * 0.999,
                "high": price * 1.002,
                "low": price * 0.998,
                "close": price,
                "volume": 100.0 + index,
                "is_session_open_bar": False,
            }
        )
    return pl.DataFrame(values)


def _synthetic_frames() -> dict[str, pl.DataFrame]:
    return {"1m": _frame(1), "15m": _frame(15), "1h": _frame(60)}


def test_frozen_context_mapping_never_fabricates_a_weekly_bar() -> None:
    assert MTF_CONTEXT_MAPPING == {
        "1m": ("15m", "1h"),
        "15m": ("1h", "4h"),
        "1h": ("4h", "1d"),
        "4h": ("8h", "1d"),
        "8h": ("12h", "1d"),
        "12h": ("1d",),
        "1d": (),
    }
    assert context_timeframes("1d") == ()


def test_context_alignment_never_selects_a_future_higher_timeframe_value() -> None:
    frames = _synthetic_frames()
    overlay = build_causal_mtf_context(
        asset="BTCUSDT",
        chart_timeframe="1m",
        visible_frame=frames["1m"].tail(120),
        calculation_frames=frames,
        now=datetime(2030, 1, 1, tzinfo=timezone.utc),
    )

    assert overlay["status"] == "ok"
    assert overlay["alignment"] == "backward_asof_on_post_close_available_at"
    assert overlay["diagnostic_only"] is True
    assert overlay["usable_as_trading_gate"] is False
    for source in overlay["sources"]:
        for point in source["trend_score"]:
            if "value" in point:
                assert point["available_time"] <= point["time"]
                assert point["source_time"] < point["available_time"]


def test_first_seen_delay_is_part_of_context_availability() -> None:
    frames = _synthetic_frames()
    for timeframe, minutes in (("1m", 1), ("15m", 15), ("1h", 60)):
        frames[timeframe] = frames[timeframe].with_columns(
            (pl.col("timestamp") + pl.duration(minutes=minutes, seconds=5)).alias(
                "live_observed_at"
            )
        )

    overlay = build_causal_mtf_context(
        asset="BTCUSDT",
        chart_timeframe="1m",
        visible_frame=frames["1m"].tail(120),
        calculation_frames=frames,
        now=datetime(2030, 1, 1, tzinfo=timezone.utc),
    )

    assert "append_only_first_seen_tail" in overlay["data_vintage"]
    for source in overlay["sources"]:
        latest = source["latest"]
        assert latest["first_seen_at"] is not None
        assert latest["available_at"] == latest["first_seen_at"]
        assert latest["available_at"] > latest["source_bar_close"]
        assert all(
            point.get("available_time", point["time"]) <= point["time"]
            for point in source["trend_score"]
        )


def test_context_prefix_is_invariant_to_future_higher_timeframe_mutation() -> None:
    frames = _synthetic_frames()
    visible = frames["1m"].slice(240, 60)
    expected = build_causal_mtf_context(
        asset="BTCUSDT",
        chart_timeframe="1m",
        visible_frame=visible,
        calculation_frames=frames,
        now=datetime(2030, 1, 1, tzinfo=timezone.utc),
    )
    cutoff = visible["timestamp"].max() + timedelta(minutes=1)
    mutated = dict(frames)
    for timeframe in ("15m", "1h"):
        mutated[timeframe] = frames[timeframe].with_columns(
            pl.when(pl.col("timestamp") > cutoff)
            .then(pl.col("close") * 9.0)
            .otherwise(pl.col("close"))
            .alias("close")
        )
    actual = build_causal_mtf_context(
        asset="BTCUSDT",
        chart_timeframe="1m",
        visible_frame=visible,
        calculation_frames=mutated,
        now=datetime(2030, 1, 1, tzinfo=timezone.utc),
    )

    assert actual["context_score"] == expected["context_score"]
    assert actual["agreement"] == expected["agreement"]
    assert actual["latest"] == expected["latest"]


def test_one_day_context_reports_no_higher_timeframe_honestly() -> None:
    daily = _frame(24 * 60)
    overlay = build_causal_mtf_context(
        asset="BTCUSDT",
        chart_timeframe="1d",
        visible_frame=daily.tail(100),
        calculation_frames={"1d": daily},
        now=datetime(2030, 1, 1, tzinfo=timezone.utc),
    )

    assert overlay["status"] == "no_higher_timeframe"
    assert overlay["context_timeframes"] == []
    assert "No higher canonical timeframe" in overlay["reason"]
    assert [source["timeframe"] for source in overlay["sources"]] == ["1d"]


def test_chart_payload_exposes_context_as_an_independent_layer() -> None:
    frames = _synthetic_frames()
    visible = frames["1m"].tail(120)
    overlay = build_causal_mtf_context(
        asset="BTCUSDT",
        chart_timeframe="1m",
        visible_frame=visible,
        calculation_frames=frames,
        now=datetime(2030, 1, 1, tzinfo=timezone.utc),
    )
    payload = build_lightweight_charts_payload(
        visible,
        {
            "asset": "BTCUSDT",
            "timeframe": "1m",
            "source": CANONICAL_SOURCE,
            "provider": "test",
        },
        indicators=INDICATOR_CROSS_TIMEFRAME_CONTEXT,
        mtf_context_overlay=overlay,
        calculation_now=datetime(2030, 1, 1, tzinfo=timezone.utc),
    )

    assert payload["overlays"][INDICATOR_CROSS_TIMEFRAME_CONTEXT] == overlay
    assert payload["metadata"]["indicator_labels"] == ["Cross-Timeframe Context"]


def test_all_56_canonical_selections_build_a_bounded_context_contract() -> None:
    now = datetime(2030, 1, 1, tzinfo=timezone.utc)
    checked = 0
    for asset in CORE_ASSETS:
        frames: dict[str, pl.DataFrame] = {}
        for timeframe in CANONICAL_TIMEFRAMES:
            resolution = resolve_ohlcv_files(asset, timeframe, CANONICAL_SOURCE)
            frames[timeframe] = (
                pl.scan_parquet(resolution.files[0])
                .select(
                    "timestamp",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "is_session_open_bar",
                )
                .tail(400)
                .collect()
            )
        for timeframe in CANONICAL_TIMEFRAMES:
            selected = {
                key: frames[key] for key in (timeframe, *context_timeframes(timeframe))
            }
            overlay = build_causal_mtf_context(
                asset=asset,
                chart_timeframe=timeframe,
                visible_frame=frames[timeframe].tail(100),
                calculation_frames=selected,
                now=now,
            )
            assert overlay["status"] in {"ok", "no_higher_timeframe"}
            assert len(overlay["context_score"]) <= 101
            for source in overlay["sources"]:
                assert len(source["trend_score"]) <= 101
                assert all(
                    point.get("available_time", point["time"]) <= point["time"]
                    for point in source["trend_score"]
                )
            checked += 1

    assert checked == 56

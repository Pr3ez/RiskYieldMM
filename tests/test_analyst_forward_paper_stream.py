from __future__ import annotations

import copy
import hashlib
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ANALYST_ROOT = (
    Path(__file__).resolve().parents[1] / "Risk_Yield_Meta_Model_Analyst_0_0_1"
)
if str(ANALYST_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYST_ROOT))

from chart_config import CANONICAL_TIMEFRAMES  # noqa: E402
from forward_paper.stream import (  # noqa: E402
    ForwardPaperStateError,
    ForwardPaperStream,
)
from minute_replay import IndicatorStrategyConfig  # noqa: E402


def _minute(timestamp: datetime, price: float, idx: int = 0) -> dict[str, object]:
    close = price * math.exp(0.001 + 0.0003 * math.sin(idx / 5.0))
    return {
        "timestamp": timestamp,
        "open": price,
        "high": max(price, close) * 1.0005,
        "low": min(price, close) * 0.9995,
        "close": close,
        "volume": 100.0 + idx,
        "is_session_open_bar": False,
    }


def _minutes(rows: int = 180) -> list[dict[str, object]]:
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    output: list[dict[str, object]] = []
    price = 100.0
    for idx in range(rows):
        row = _minute(start + timedelta(minutes=idx), price, idx)
        output.append(row)
        price = float(row["close"])
    return output


def _fast_strategy() -> IndicatorStrategyConfig:
    return IndicatorStrategyConfig(
        cusum_sensitivity="Fast (Day Trade)",
        horizons=(2, 4, 8),
        aligned_score=0.03,
        aligned_quality=0.01,
        developing_score=0.005,
        change_risk_threshold=1.0,
        max_fast_slow_ratio=100.0,
        minimum_path_quality=0.0,
        require_cusum_agreement=False,
        minimum_volatility_scale=1.0,
    )


def _consume_rows(
    stream: ForwardPaperStream,
    rows: list[dict[str, object]],
    *,
    delay_minutes: int = 0,
    delay_seconds: int = 0,
    mode: str = "forward",
) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for row in rows:
        observed_at = row["timestamp"] + timedelta(  # type: ignore[operator]
            minutes=1 + delay_minutes,
            seconds=delay_seconds,
        )
        events.extend(
            stream.consume(
                row,
                observed_at=observed_at,
                mode=mode,  # type: ignore[arg-type]
            )
        )
    return events


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@pytest.mark.parametrize("timeframe", CANONICAL_TIMEFRAMES)
def test_forward_stream_accepts_all_canonical_timeframes(timeframe: str) -> None:
    stream = ForwardPaperStream(asset="BTCUSDT", timeframe=timeframe)

    assert stream.timeframe == timeframe
    assert stream.builder.timeframe == timeframe
    assert stream.costs.execution_latency_minutes == 1


def test_forward_signal_and_fill_never_use_an_already_passed_open() -> None:
    stream = ForwardPaperStream(
        asset="BTCUSDT", timeframe="1m", strategy=_fast_strategy()
    )
    events = _consume_rows(stream, _minutes(), delay_seconds=5)
    orders = {
        event["order_id"]: event
        for event in events
        if event["event_type"] == "paper_order_created"
    }
    fills = [event for event in events if event["event_type"] == "paper_fill"]

    assert orders
    assert fills
    for fill in fills:
        order = orders[fill["order_id"]]
        fill_open = _parse(fill["fill_minute_open"])
        eligible_at = _parse(order["eligible_at"])
        observed_at = _parse(order["observed_at"])
        assert fill_open >= eligible_at
        assert eligible_at > observed_at
        assert fill_open > _parse(order["scheduled_close"])


def test_delayed_first_seen_time_moves_eligibility_instead_of_backfilling() -> None:
    stream = ForwardPaperStream(
        asset="BTCUSDT", timeframe="1m", strategy=_fast_strategy()
    )
    events = _consume_rows(
        stream,
        _minutes(220),
        delay_minutes=10,
        delay_seconds=17,
    )
    order = next(
        event for event in events if event["event_type"] == "paper_order_created"
    )
    observed = _parse(order["observed_at"])
    scheduled = _parse(order["scheduled_close"])
    base = max(observed, scheduled) + timedelta(minutes=1)
    expected_epoch = math.ceil(base.timestamp() / 60.0) * 60
    expected = datetime.fromtimestamp(expected_epoch, tz=timezone.utc)

    assert _parse(order["eligible_at"]) == expected
    assert _parse(order["eligible_at"]) > scheduled + timedelta(minutes=10)
    matching_fill = next(
        event
        for event in events
        if event["event_type"] == "paper_fill"
        and event["order_id"] == order["order_id"]
    )
    assert _parse(matching_fill["fill_minute_open"]) >= expected


@pytest.mark.parametrize("mode", ["bootstrap", "catchup"])
def test_historical_modes_emit_audit_suppression_but_never_trade(mode: str) -> None:
    stream = ForwardPaperStream(
        asset="BTCUSDT", timeframe="1m", strategy=_fast_strategy()
    )
    events = _consume_rows(stream, _minutes(30), mode=mode)
    event_types = [event["event_type"] for event in events]

    assert "target_bar_closed" in event_types
    assert "signal_suppressed_catchup" in event_types
    assert "signal_issued" not in event_types
    assert "paper_order_created" not in event_types
    assert "paper_fill" not in event_types
    assert event_types.count("paper_mark") == 30
    assert stream.ledger.fill_count == 0
    assert stream.ledger.equity == pytest.approx(1.0)


def test_direct_target_bootstrap_keeps_builder_empty_and_waits_for_boundary() -> None:
    stream = ForwardPaperStream(
        asset="BTCUSDT", timeframe="1h", strategy=_fast_strategy()
    )
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    bars = []
    price = 100.0
    for idx in range(40):
        row = _minute(start + timedelta(hours=idx), price, idx)
        bars.append(row)
        price = float(row["close"])

    result = stream.bootstrap_target_bars(bars)
    next_boundary = start + timedelta(hours=40)

    assert result["added_target_bars"] == 40
    assert result["signals_created"] == 0
    assert result["fills_created"] == 0
    assert result["builder_empty"] is True
    assert stream.builder.bucket_end is None
    assert stream.online_engine.bars_seen == 40
    assert stream.cusum_engine.bars_seen == 40
    assert stream.clean_start_at == next_boundary

    partial = _minute(next_boundary + timedelta(minutes=5), price, 41)
    suppressed = stream.consume(
        partial,
        observed_at=next_boundary + timedelta(minutes=6),
        mode="forward",
    )
    assert [event["event_type"] for event in suppressed] == [
        "minute_suppressed_partial_bucket"
    ]
    assert stream.builder.bucket_end is None

    another_partial = _minute(next_boundary + timedelta(minutes=6), price, 42)
    assert (
        stream.consume(
            another_partial,
            observed_at=next_boundary + timedelta(minutes=7),
            mode="forward",
        )
        == []
    )
    assert stream.cursor is not None
    assert stream.cursor.timestamp == next_boundary + timedelta(minutes=6)
    assert stream.builder.bucket_end is None

    clean = _minute(next_boundary + timedelta(hours=1), price, 43)
    events = stream.consume(
        clean,
        observed_at=next_boundary + timedelta(hours=1, minutes=1),
        mode="forward",
    )
    assert [event["event_type"] for event in events] == [
        "paper_stream_incident",
        "paper_mark",
    ]
    assert events[0]["incident_type"] == "source_gap"
    assert stream.builder.bucket_end == next_boundary + timedelta(hours=2)


def test_snapshot_restore_matches_uninterrupted_stream_exactly() -> None:
    rows = _minutes(180)
    original = ForwardPaperStream(
        asset="BTCUSDT", timeframe="15m", strategy=_fast_strategy()
    )
    _consume_rows(original, rows[:73], delay_seconds=7)
    snapshot = original.snapshot()
    json.dumps(snapshot, allow_nan=False)
    restored = ForwardPaperStream.restore(copy.deepcopy(snapshot))

    uninterrupted_events = _consume_rows(original, rows[73:], delay_seconds=7)
    restored_events = _consume_rows(restored, rows[73:], delay_seconds=7)

    assert restored_events == uninterrupted_events
    assert restored.snapshot() == original.snapshot()


def test_duplicate_revision_and_late_rows_never_rewrite_retained_state() -> None:
    rows = _minutes(8)
    stream = ForwardPaperStream(asset="BTCUSDT", timeframe="1m")
    _consume_rows(stream, rows)
    retained = stream.snapshot()
    last = rows[-1]
    last_observed = last["timestamp"] + timedelta(minutes=1)  # type: ignore[operator]

    assert stream.consume(last, observed_at=last_observed) == []
    assert stream.snapshot() == retained

    revised = dict(last)
    revised["close"] = float(revised["close"]) * 1.001
    revised["high"] = max(float(revised["high"]), float(revised["close"]))
    revision = stream.consume(
        revised,
        observed_at=last_observed + timedelta(seconds=10),
    )
    assert revision[0]["event_type"] == "paper_stream_incident"
    assert revision[0]["incident_type"] == "source_revision"
    assert revision[0]["state_mutated"] is False
    assert len(revision[0]["event_id"]) == 64
    assert stream.snapshot() == retained

    late = stream.consume(
        rows[-3],
        observed_at=last_observed + timedelta(seconds=20),
    )
    assert late[0]["incident_type"] == "late_row"
    assert stream.snapshot() == retained


def test_snapshot_checksum_rejects_mutation() -> None:
    stream = ForwardPaperStream(asset="BTCUSDT", timeframe="1m")
    _consume_rows(stream, _minutes(3))
    snapshot = stream.snapshot()
    snapshot["asset"] = "ETHUSDT"

    with pytest.raises(ForwardPaperStateError, match="checksum mismatch"):
        ForwardPaperStream.restore(snapshot)


def test_v2_stream_snapshot_is_rejected_even_with_a_valid_checksum() -> None:
    stream = ForwardPaperStream(asset="BTCUSDT", timeframe="1m")
    _consume_rows(stream, _minutes(3))
    snapshot = stream.snapshot()
    snapshot.pop("checksum")
    snapshot["algorithm_version"] = "forward_paper_stream_v2"
    encoded = json.dumps(
        snapshot,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    snapshot["checksum"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    with pytest.raises(ForwardPaperStateError, match="version mismatch"):
        ForwardPaperStream.restore(snapshot)

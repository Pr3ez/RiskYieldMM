from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import polars as pl
import pytest

ANALYST_ROOT = (
    Path(__file__).resolve().parents[1] / "Risk_Yield_Meta_Model_Analyst_0_0_1"
)
if str(ANALYST_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYST_ROOT))

from chart_config import CANONICAL_TIMEFRAMES, CORE_ASSETS  # noqa: E402
from forward_paper.chart_overlay import (  # noqa: E402
    aggregate_causal_live_minutes,
    load_live_chart_overlay,
    read_first_seen_minutes,
)
from forward_paper.event_store import (  # noqa: E402
    EventInput,
    EventStore,
    RunInput,
)
from forward_paper.runtime import atomic_write_json  # noqa: E402

UTC = timezone.utc


def _minute(
    timestamp: datetime,
    *,
    close: float = 100.5,
    observed_at: datetime | None = None,
    provider: str = "bybit",
    quality: str = "live",
) -> dict[str, Any]:
    return {
        "timestamp": timestamp,
        "open": 100.0,
        "high": max(101.0, close),
        "low": min(99.0, close),
        "close": close,
        "volume": 10.0,
        "is_session_open_bar": False,
        "overlay_observed_at": observed_at
        or timestamp + timedelta(minutes=1, seconds=5),
        "overlay_provider": provider,
        "overlay_quality": quality,
    }


def _frame(rows: list[dict[str, Any]]) -> pl.DataFrame:
    return pl.DataFrame(
        rows,
        schema_overrides={
            "timestamp": pl.Datetime("us", "UTC"),
            "overlay_observed_at": pl.Datetime("us", "UTC"),
        },
    )


def _canonical(rows: list[dict[str, Any]]) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                key: value
                for key, value in row.items()
                if key
                in {
                    "timestamp",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "is_session_open_bar",
                }
            }
            for row in rows
        ],
        schema_overrides={"timestamp": pl.Datetime("us", "UTC")},
    )


def _journal_event(
    asset: str,
    timestamp: datetime,
    *,
    event_id: str,
    close: float = 100.5,
    observed_at: datetime | None = None,
    provider: str = "bybit",
    quality: str = "live",
) -> EventInput:
    observed = observed_at or timestamp + timedelta(minutes=1, seconds=5)
    return EventInput(
        event_id=event_id,
        stream_id=f"source:{asset}",
        event_type="source_bar_observed",
        occurred_at=timestamp + timedelta(minutes=1),
        observed_at=observed,
        payload={
            "asset": asset,
            "provider": provider,
            "quality": quality,
            "expected_delay_seconds": 5 if quality == "live" else 600,
            "processing_mode": "forward",
            "row": {
                "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
                "open": 100.0,
                "high": max(101.0, close),
                "low": min(99.0, close),
                "close": close,
                "volume": 10.0,
                "interval": "1m",
            },
        },
    )


def _create_run(store: EventStore, run_id: str, created_at: datetime) -> None:
    store.create_run(
        RunInput(
            run_id=run_id,
            created_at=created_at,
            metadata={"source_vintage": "append_only_first_seen"},
        )
    )


def test_reader_selects_status_run_and_reads_committed_wal_with_freshness(
    tmp_path: Path,
) -> None:
    database = tmp_path / "forward_paper.sqlite3"
    status = tmp_path / "status.json"
    base = datetime(2026, 7, 12, 10, 0, tzinfo=UTC)
    with EventStore(database) as store:
        _create_run(store, "old-run", base - timedelta(hours=1))
        store.append_batch(
            "old-run",
            [_journal_event("BTCUSDT", base, event_id="old-event", close=90.0)],
        )
        _create_run(store, "active-run", base)
        first = store.append_batch(
            "active-run",
            [_journal_event("BTCUSDT", base, event_id="active-1", close=110.0)],
        ).events[0]
        atomic_write_json(
            status,
            {
                "run_id": "active-run",
                "status": "running",
                "heartbeat_at": "2026-07-12T10:01:06Z",
                "poll_interval_seconds": 60,
                "feeds": {
                    "BTCUSDT": {
                        "status": "ok",
                        "last_observed_at": "2026-07-12T10:01:05Z",
                        "measured_lag_seconds": 5.0,
                    }
                },
            },
        )

        snapshot = read_first_seen_minutes(
            asset="BTCUSDT",
            database_path=database,
            status_path=status,
            as_of="2026-07-12T10:01:10Z",
        )
        assert snapshot.frame["close"].to_list() == [110.0]
        assert snapshot.metadata["run_id"] == "active-run"
        assert snapshot.metadata["latest_source_sequence_no"] == 1
        assert snapshot.metadata["latest_source_event_hash"] == first.event_hash
        assert snapshot.metadata["provider"] == "bybit"
        assert snapshot.metadata["quality"] == "live"
        assert snapshot.metadata["service_status"] == "running"
        assert snapshot.metadata["feed_status"] == "ok"
        assert snapshot.metadata["service_heartbeat_age_seconds"] == 4.0
        assert snapshot.metadata["freshness"] == "fresh"
        # There is no supervisor PID record in this isolated state directory.
        assert snapshot.metadata["service_running"] is False


def test_reader_keeps_feed_grade_when_active_run_has_no_new_market_bar(
    tmp_path: Path,
) -> None:
    database = tmp_path / "forward_paper.sqlite3"
    status = tmp_path / "status.json"
    now = datetime(2026, 7, 12, 10, 0, tzinfo=UTC)
    with EventStore(database) as store:
        _create_run(store, "weekend-run", now)
    atomic_write_json(
        status,
        {
            "run_id": "weekend-run",
            "status": "running",
            "heartbeat_at": "2026-07-12T10:00:00Z",
            "poll_interval_seconds": 60,
            "feeds": {
                "ES": {
                    "status": "waiting_delayed_provider_interval",
                    "provider": "yfinance",
                    "quality": "delayed",
                    "expected_delay_seconds": 600,
                    "last_source_timestamp": "2026-07-10T20:59:00Z",
                }
            },
        },
    )

    snapshot = read_first_seen_minutes(
        asset="ES",
        database_path=database,
        status_path=status,
        as_of=now,
    )

    assert snapshot.frame.is_empty()
    assert snapshot.metadata["status"] == "no_source_rows_as_of"
    assert snapshot.metadata["provider"] == "yfinance"
    assert snapshot.metadata["quality"] == "delayed"
    assert snapshot.metadata["expected_delay_seconds"] == 600


def test_one_minute_overlay_wins_timestamp_collision_without_mutating_canonical(
    tmp_path: Path,
) -> None:
    database = tmp_path / "forward_paper.sqlite3"
    status = tmp_path / "status.json"
    base = datetime(2026, 7, 12, 10, 0, tzinfo=UTC)
    canonical = _canonical([_minute(base, close=99.0)])
    original = canonical.to_dicts()
    with EventStore(database) as store:
        _create_run(store, "active-run", base)
        store.append_batch(
            "active-run",
            [
                _journal_event("BTCUSDT", base, event_id="live-overlap", close=111.0),
                _journal_event(
                    "BTCUSDT",
                    base + timedelta(minutes=1),
                    event_id="live-tail",
                    close=112.0,
                ),
            ],
        )
        atomic_write_json(status, {"run_id": "active-run", "status": "running"})
        result = load_live_chart_overlay(
            canonical,
            asset="BTCUSDT",
            timeframe="1m",
            database_path=database,
            status_path=status,
            as_of=base + timedelta(minutes=2, seconds=10),
        )

    assert canonical.to_dicts() == original
    assert result.frame["timestamp"].to_list() == [
        base,
        base + timedelta(minutes=1),
    ]
    assert result.frame["close"].to_list() == [111.0, 112.0]
    assert result.metadata["canonical_rows_replaced"] == 1
    assert result.metadata["live_rows_appended"] == 1
    assert result.metadata["canonical_mutated"] is False


def test_crypto_higher_timeframe_requires_complete_closed_bucket() -> None:
    base = datetime(2026, 7, 12, 10, 0, tzinfo=UTC)
    first_bucket = _frame(
        [_minute(base + timedelta(minutes=index)) for index in range(15)]
    )
    before_close = aggregate_causal_live_minutes(
        first_bucket,
        asset="BTCUSDT",
        timeframe="15m",
        as_of=base + timedelta(minutes=14, seconds=59),
    )
    assert before_close.is_empty()

    after_close = aggregate_causal_live_minutes(
        first_bucket,
        asset="BTCUSDT",
        timeframe="15m",
        as_of=base + timedelta(minutes=15, seconds=5),
    )
    assert after_close["timestamp"].to_list() == [base]
    assert after_close["source_minute_count"].to_list() == [15]

    partial_then_complete = _frame(
        [_minute(base + timedelta(minutes=index)) for index in range(5, 30)]
    )
    completed = aggregate_causal_live_minutes(
        partial_then_complete,
        asset="BTCUSDT",
        timeframe="15m",
        as_of=base + timedelta(minutes=30, seconds=5),
    )
    assert completed["timestamp"].to_list() == [base + timedelta(minutes=15)]


def test_canonical_minutes_complete_transition_bucket_but_live_rows_win() -> None:
    base = datetime(2026, 7, 12, 10, 0, tzinfo=UTC)
    canonical_minutes = _canonical(
        [
            _minute(base + timedelta(minutes=index), close=100 + index)
            for index in range(5)
        ]
    )
    live = _frame(
        [
            _minute(
                base + timedelta(minutes=index),
                close=200 + index,
                observed_at=base + timedelta(minutes=index + 1, seconds=5),
            )
            for index in range(5, 15)
        ]
    )
    result = aggregate_causal_live_minutes(
        live,
        asset="BTCUSDT",
        timeframe="15m",
        as_of=base + timedelta(minutes=15, seconds=5),
        canonical_minutes=canonical_minutes,
    )
    assert result["timestamp"].to_list() == [base]
    assert result["open"].to_list() == [100.0]
    assert result["close"].to_list() == [214.0]
    assert result["source_minute_count"].to_list() == [15]
    assert result["live_source_minute_count"].to_list() == [10]


def test_session_asset_canonical_boundary_rows_keep_transition_bucket() -> None:
    base = datetime(2026, 7, 12, 10, 0, tzinfo=UTC)
    canonical_minutes = _canonical(
        [
            _minute(base + timedelta(minutes=index), close=100 + index)
            for index in range(5)
        ]
    )
    live = _frame(
        [
            _minute(base + timedelta(minutes=index), close=200 + index)
            for index in range(5, 10)
        ]
    )
    result = aggregate_causal_live_minutes(
        live,
        asset="ES",
        timeframe="15m",
        as_of=base + timedelta(minutes=15, seconds=5),
        canonical_minutes=canonical_minutes,
    )
    assert result["timestamp"].to_list() == [base]
    assert result["open"].to_list() == [100.0]
    assert result["close"].to_list() == [209.0]
    assert result["source_minute_count"].to_list() == [10]
    assert result["live_source_minute_count"].to_list() == [5]


def test_session_open_flag_proves_sparse_transition_bucket_is_complete() -> None:
    base = datetime(2026, 7, 12, 10, 0, tzinfo=UTC)
    rows = [
        _minute(base + timedelta(minutes=index), close=200 + index)
        for index in range(5, 10)
    ]
    rows[-1]["is_session_open_bar"] = True
    unproven = aggregate_causal_live_minutes(
        _frame(rows),
        asset="ES",
        timeframe="15m",
        as_of=base + timedelta(minutes=15, seconds=5),
    )
    assert unproven.is_empty()

    rows[-1]["is_session_open_bar"] = False
    rows[0]["is_session_open_bar"] = True

    result = aggregate_causal_live_minutes(
        _frame(rows),
        asset="ES",
        timeframe="15m",
        as_of=base + timedelta(minutes=15, seconds=5),
    )

    assert result["timestamp"].to_list() == [base]
    assert result["open"].to_list() == [100.0]
    assert result["close"].to_list() == [209.0]
    assert result["source_minute_count"].to_list() == [5]
    assert result["is_session_open_bar"].to_list() == [True]


@pytest.mark.parametrize("asset", CORE_ASSETS)
@pytest.mark.parametrize("timeframe", CANONICAL_TIMEFRAMES)
def test_aggregation_supports_every_configured_asset_and_timeframe(
    asset: str,
    timeframe: str,
) -> None:
    seconds = {
        "1m": 60,
        "15m": 15 * 60,
        "1h": 60 * 60,
        "4h": 4 * 60 * 60,
        "8h": 8 * 60 * 60,
        "12h": 12 * 60 * 60,
        "1d": 24 * 60 * 60,
    }[timeframe]
    base = datetime(2026, 7, 12, tzinfo=UTC)
    minute_count = seconds // 60 if asset in {"BTCUSDT", "ETHUSDT"} else 1
    live = _frame(
        [_minute(base + timedelta(minutes=index)) for index in range(minute_count)]
    )
    result = aggregate_causal_live_minutes(
        live,
        asset=asset,
        timeframe=timeframe,
        as_of=base + timedelta(seconds=seconds + 5),
    )
    assert result["timestamp"].to_list() == [base]


def test_generation_changes_on_source_head_and_target_close_boundary(
    tmp_path: Path,
) -> None:
    database = tmp_path / "forward_paper.sqlite3"
    status = tmp_path / "status.json"
    base = datetime(2026, 7, 12, 10, 0, tzinfo=UTC)
    canonical = _canonical([_minute(base - timedelta(hours=1))])
    with EventStore(database) as store:
        _create_run(store, "active-run", base)
        store.append_batch(
            "active-run",
            [_journal_event("ES", base, event_id="source-1", quality="delayed")],
        )
        atomic_write_json(status, {"run_id": "active-run", "status": "running"})
        first = load_live_chart_overlay(
            canonical,
            asset="ES",
            timeframe="1h",
            database_path=database,
            status_path=status,
            as_of=base + timedelta(hours=1, seconds=5),
        )
        assert (
            first.metadata["indicator_observation_semantics"]
            == "retrospective_delayed_observation"
        )
        assert first.metadata["as_was_backtest_safe"] is False
        boundary_advanced = load_live_chart_overlay(
            canonical,
            asset="ES",
            timeframe="1h",
            database_path=database,
            status_path=status,
            as_of=base + timedelta(hours=2, seconds=5),
        )
        store.append_batch(
            "active-run",
            [
                _journal_event(
                    "ES",
                    base + timedelta(hours=2),
                    event_id="source-2",
                    quality="delayed",
                )
            ],
        )
        source_advanced = load_live_chart_overlay(
            canonical,
            asset="ES",
            timeframe="1h",
            database_path=database,
            status_path=status,
            as_of=base + timedelta(hours=3, seconds=5),
        )

    assert first.metadata["generation"] != boundary_advanced.metadata["generation"]
    assert (
        boundary_advanced.metadata["generation"]
        != source_advanced.metadata["generation"]
    )


def test_missing_journal_is_nonfatal_and_keeps_canonical(tmp_path: Path) -> None:
    base = datetime(2026, 7, 12, 10, 0, tzinfo=UTC)
    canonical = _canonical([_minute(base), _minute(base + timedelta(minutes=1))])
    result = load_live_chart_overlay(
        canonical,
        asset="BTCUSDT",
        timeframe="1m",
        database_path=tmp_path / "missing.sqlite3",
        as_of=base + timedelta(minutes=2),
        max_bars=1,
    )
    assert result.frame.to_dicts() == canonical.tail(1).to_dicts()
    assert result.metadata["available"] is False
    assert result.metadata["reason"] == "journal_not_found"
    assert result.metadata["result_row_count"] == 1

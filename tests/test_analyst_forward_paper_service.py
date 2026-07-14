from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

ANALYST_ROOT = (
    Path(__file__).resolve().parents[1] / "Risk_Yield_Meta_Model_Analyst_0_0_1"
)
if str(ANALYST_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYST_ROOT))

from forward_paper.service import (  # noqa: E402
    ForwardPaperConfig,
    ForwardPaperCoordinator,
)
from forward_paper.sources import FinalizedMinuteBatch  # noqa: E402


def _row(timestamp: datetime, close: float = 100.5) -> dict[str, Any]:
    return {
        "timestamp": timestamp,
        "open": 100.0,
        "high": max(101.0, close),
        "low": min(99.0, close),
        "close": close,
        "volume": 10.0,
        "turnover": 1_000.0,
        "interval": "1m",
    }


def _batch(
    asset: str,
    observed_at: datetime,
    rows: list[dict[str, Any]],
    *,
    quality: str = "live",
) -> FinalizedMinuteBatch:
    return FinalizedMinuteBatch(
        asset=asset,
        provider="bybit" if quality == "live" else "yfinance",
        quality=quality,  # type: ignore[arg-type]
        expected_delay_seconds=5 if quality == "live" else 600,
        observed_at=observed_at,
        rows=tuple(rows),
    )


class _QueuedRouter:
    def __init__(self, batches: list[FinalizedMinuteBatch | Exception]) -> None:
        self.batches = list(batches)
        self.calls: list[tuple[str, datetime | None, datetime | None]] = []

    def fetch(
        self,
        asset: str,
        after_timestamp: datetime | None = None,
        now: datetime | None = None,
    ) -> FinalizedMinuteBatch:
        self.calls.append((asset, after_timestamp, now))
        if not self.batches:
            raise AssertionError("unexpected source fetch")
        value = self.batches.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def _config(tmp_path: Path, **kwargs: Any) -> ForwardPaperConfig:
    return ForwardPaperConfig(
        assets=("BTCUSDT",),
        timeframes=("1m", "1h"),
        state_dir=tmp_path,
        poll_interval_seconds=5,
        **kwargs,
    )


def test_service_journals_first_seen_rows_filters_overlap_and_restores(
    tmp_path: Path,
) -> None:
    started = datetime(2026, 7, 11, 12, 4, tzinfo=timezone.utc)
    first_rows = [_row(started.replace(minute=minute)) for minute in (0, 1, 2, 3)]
    second_rows = [first_rows[-1], _row(started.replace(minute=4), 101.0)]
    router = _QueuedRouter(
        [
            _batch("BTCUSDT", started + timedelta(minutes=1), first_rows),
            _batch("BTCUSDT", started + timedelta(minutes=3), second_rows),
        ]
    )
    coordinator = ForwardPaperCoordinator(
        _config(tmp_path),
        source_router=router,  # type: ignore[arg-type]
        bootstrap_loader=lambda *_args: [],
        anchor_loader=lambda *_args: None,
        started_at=started,
    )

    first_status = coordinator.poll_once(now=started + timedelta(minutes=1))
    second_status = coordinator.poll_once(now=started + timedelta(minutes=3))
    events = coordinator.store.events(coordinator.run_id)
    source_events = [
        event for event in events if event.event_type == "source_bar_observed"
    ]

    assert len(source_events) == 5
    assert [event.payload["processing_mode"] for event in source_events[:4]] == [
        "catchup"
    ] * 4
    assert source_events[-1].payload["processing_mode"] == "forward"
    assert "BTCUSDT" in coordinator.activated_assets
    assert first_status["feeds"]["BTCUSDT"]["quality"] == "live"
    assert second_status["feeds"]["BTCUSDT"]["last_source_timestamp"] == (
        "2026-07-11T12:04:00Z"
    )
    assert set(second_status["streams"]) == {"BTCUSDT|1m", "BTCUSDT|1h"}
    saved_run_id = coordinator.run_id
    saved_cursor = coordinator.streams["BTCUSDT|1m"].cursor
    coordinator.close()

    restored = ForwardPaperCoordinator(
        _config(tmp_path),
        source_router=_QueuedRouter([]),  # type: ignore[arg-type]
        bootstrap_loader=lambda *_args: pytest.fail("must restore snapshots"),
        anchor_loader=lambda *_args: pytest.fail("must restore source cursor"),
        started_at=started + timedelta(hours=1),
    )
    try:
        assert restored.run_id == saved_run_id
        assert restored.streams["BTCUSDT|1m"].cursor == saved_cursor
        verification = restored.store.verify_chain(restored.run_id)
        assert verification.event_count > len(source_events)
    finally:
        restored.close()


def test_service_catchup_pages_advance_cursor_without_skips_or_duplicate_events(
    tmp_path: Path,
) -> None:
    anchor = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)
    available = [_row(anchor + timedelta(minutes=offset)) for offset in range(15)]

    class _PagedRouter:
        def __init__(self) -> None:
            self.calls: list[datetime | None] = []

        def fetch(
            self,
            asset: str,
            after_timestamp: datetime | None = None,
            now: datetime | None = None,
        ) -> FinalizedMinuteBatch:
            assert after_timestamp is not None
            assert now is not None
            self.calls.append(after_timestamp)
            start = after_timestamp - timedelta(minutes=1)
            end = start + timedelta(minutes=4)
            rows = [row for row in available if start <= row["timestamp"] <= end]
            return _batch(asset, now, rows)

    router = _PagedRouter()
    started = anchor + timedelta(minutes=20)
    with ForwardPaperCoordinator(
        _config(tmp_path),
        source_router=router,  # type: ignore[arg-type]
        bootstrap_loader=lambda *_args: [],
        anchor_loader=lambda *_args: anchor,
        started_at=started,
    ) as coordinator:
        status: dict[str, Any] = {}
        for poll_offset in range(5):
            status = coordinator.poll_once(now=started + timedelta(minutes=poll_offset))

        source_events = [
            event
            for event in coordinator.store.events(coordinator.run_id)
            if event.event_type == "source_bar_observed"
        ]
        observed_timestamps = [
            event.payload["row"]["timestamp"] for event in source_events
        ]
        event_types = [
            event.event_type for event in coordinator.store.events(coordinator.run_id)
        ]

        assert router.calls == [
            anchor + timedelta(minutes=offset) for offset in (0, 3, 6, 9, 12)
        ]
        assert observed_timestamps == [
            (anchor + timedelta(minutes=offset)).isoformat().replace("+00:00", "Z")
            for offset in range(1, 15)
        ]
        assert len(observed_timestamps) == len(set(observed_timestamps))
        assert event_types.count("late_source_bar_observed") == 1
        assert status["feeds"]["BTCUSDT"]["last_source_timestamp"] == (
            "2026-07-11T12:14:00Z"
        )


def test_service_records_revision_without_rewriting_stream_state(
    tmp_path: Path,
) -> None:
    started = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)
    original = _row(started)
    revised = _row(started, 100.75)
    router = _QueuedRouter(
        [
            _batch("BTCUSDT", started + timedelta(minutes=2), [original]),
            _batch("BTCUSDT", started + timedelta(minutes=3), [revised]),
        ]
    )
    with ForwardPaperCoordinator(
        _config(tmp_path),
        source_router=router,  # type: ignore[arg-type]
        bootstrap_loader=lambda *_args: [],
        anchor_loader=lambda *_args: None,
        started_at=started + timedelta(minutes=1),
    ) as coordinator:
        coordinator.poll_once(now=started + timedelta(minutes=2))
        cursor_before = coordinator.streams["BTCUSDT|1m"].cursor
        coordinator.poll_once(now=started + timedelta(minutes=3))
        cursor_after = coordinator.streams["BTCUSDT|1m"].cursor
        event_types = [
            event.event_type for event in coordinator.store.events(coordinator.run_id)
        ]

        assert cursor_after == cursor_before
        assert event_types.count("source_bar_observed") == 1
        assert event_types.count("source_revision_observed") == 1


def test_durable_journal_failure_aborts_poll_instead_of_failing_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)
    coordinator = ForwardPaperCoordinator(
        _config(tmp_path),
        source_router=_QueuedRouter(
            [_batch("BTCUSDT", started + timedelta(minutes=2), [_row(started)])]
        ),  # type: ignore[arg-type]
        bootstrap_loader=lambda *_args: [],
        anchor_loader=lambda *_args: None,
        started_at=started,
    )
    try:
        with monkeypatch.context() as patcher:

            def fail_append(*_args: Any, **_kwargs: Any) -> None:
                raise RuntimeError("durable journal unavailable")

            patcher.setattr(coordinator.store, "append_batch", fail_append)
            with pytest.raises(RuntimeError, match="durable journal unavailable"):
                coordinator.poll_once(now=started + timedelta(minutes=2))
    finally:
        coordinator.closed = True
        coordinator.store.close()


def test_service_persists_fetch_failure_and_honest_status(tmp_path: Path) -> None:
    started = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)
    coordinator = ForwardPaperCoordinator(
        _config(tmp_path),
        source_router=_QueuedRouter([RuntimeError("provider unavailable")]),  # type: ignore[arg-type]
        bootstrap_loader=lambda *_args: [],
        anchor_loader=lambda *_args: None,
        started_at=started,
    )
    try:
        status = coordinator.poll_once(now=started + timedelta(minutes=1))
        feed = status["feeds"]["BTCUSDT"]
        assert feed["status"] == "fetch_error"
        assert feed["consecutive_failures"] == 1
        assert "provider unavailable" in feed["error"]
        assert status["real_order_routing"] is False
        assert status["profitability_guaranteed"] is False
        assert status["research_status"] == (
            "historical_optimizer_rejected_observe_only"
        )
        assert any(
            event.event_type == "source_fetch_failed"
            for event in coordinator.store.events(coordinator.run_id)
        )
    finally:
        coordinator.close()


def test_require_live_feeds_rejects_yahoo_fallback_assets(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Databento Live entitlement"):
        ForwardPaperConfig(
            assets=("BTCUSDT", "ES"),
            timeframes=("1m",),
            state_dir=tmp_path,
            require_live_feeds=True,
        )


def test_delayed_source_uses_provider_cadence_while_service_heartbeats(
    tmp_path: Path,
) -> None:
    started = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)
    router = _QueuedRouter(
        [_batch("ES", started + timedelta(minutes=1), [], quality="delayed")]
    )
    coordinator = ForwardPaperCoordinator(
        ForwardPaperConfig(
            assets=("ES",),
            timeframes=("1m",),
            state_dir=tmp_path,
            poll_interval_seconds=5,
        ),
        source_router=router,  # type: ignore[arg-type]
        bootstrap_loader=lambda *_args: [],
        anchor_loader=lambda *_args: None,
        started_at=started,
    )
    try:
        coordinator.poll_once(now=started + timedelta(minutes=1))
        status = coordinator.poll_once(now=started + timedelta(minutes=2))
        assert len(router.calls) == 1
        assert status["feeds"]["ES"]["status"] == ("waiting_delayed_provider_interval")
        assert status["feeds"]["ES"]["next_attempt_at"] == ("2026-07-11T12:11:00Z")
    finally:
        coordinator.close()


def test_default_config_covers_all_56_streams_without_network(tmp_path: Path) -> None:
    assets = (
        "BTCUSDT",
        "ETHUSDT",
        "CL",
        "ES",
        "EURUSD",
        "GC",
        "NQ",
        "USDJPY",
    )
    config = ForwardPaperConfig(
        assets=assets,
        state_dir=tmp_path,
        poll_interval_seconds=5,
    )
    coordinator = ForwardPaperCoordinator(
        config,
        source_router=_QueuedRouter([]),  # type: ignore[arg-type]
        bootstrap_loader=lambda *_args: [],
        anchor_loader=lambda *_args: None,
        started_at=datetime(2026, 7, 11, tzinfo=timezone.utc),
    )
    try:
        assert len(coordinator.streams) == 8 * 7
        assert set(config.timeframes) == {
            "1m",
            "15m",
            "1h",
            "4h",
            "8h",
            "12h",
            "1d",
        }
    finally:
        coordinator.close()

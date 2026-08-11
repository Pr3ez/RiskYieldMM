from __future__ import annotations

import copy
import json
import sys
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ANALYST_ROOT = (
    Path(__file__).resolve().parents[1] / "Risk_Yield_Meta_Model_Analyst_0_0_1"
)
if str(ANALYST_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYST_ROOT))

from trade_ml import (  # noqa: E402
    BarrierConfig,
    BarrierOutcome,
    ShadowBookCapacityError,
    ShadowCandidate,
    ShadowEventBook,
    ShadowEventState,
    ShadowGapPolicy,
    TradeSide,
    build_feature_snapshot,
)

BASE = datetime(2026, 1, 5, 12, 0, tzinfo=timezone.utc)


def _candidate(
    event_id: str,
    *,
    eligible_minute: int = 1,
    side: TradeSide = TradeSide.LONG,
    risk_unit: float = 1.0,
    timeout_target_bars: int = 3,
    target_interval_seconds: int = 900,
    target_units: float = 2.0,
    cost_bps: float = 5.0,
    adverse_bps: float = 0.0,
    gap_policy: ShadowGapPolicy = ShadowGapPolicy.CONTINUOUS_CANCEL,
) -> ShadowCandidate:
    setup_id = f"setup-{event_id}"
    config = BarrierConfig(
        stop_risk_units=1.0,
        target_risk_units=target_units,
        timeout_target_bars=timeout_target_bars,
        target_interval_seconds=target_interval_seconds,
    )
    features = build_feature_snapshot(
        setup_id=setup_id,
        side=side,
        decision_at=BASE,
        online={
            "source_timestamp": BASE,
            "available_at": BASE,
            "status": "ok",
            "trend_score": 0.5,
        },
        cusum={
            "timestamp": BASE,
            "available_at": BASE,
            "status": "ok",
            "regime": side.multiplier,
            "bull_start": side is TradeSide.LONG,
            "bear_start": side is TradeSide.SHORT,
            "scale_ready": True,
        },
        entry_reference=100.0,
        risk_unit=risk_unit,
        stop_risk_units=config.stop_risk_units,
        target_risk_units=config.target_risk_units,
        timeout_target_bars=config.timeout_target_bars,
        target_interval_seconds=config.target_interval_seconds,
        estimated_roundtrip_cost_bps=cost_bps,
    )
    return ShadowCandidate(
        event_id=event_id,
        setup_id=setup_id,
        asset="btcusdt",
        timeframe="15M",
        decision_at=BASE,
        eligible_at=BASE + timedelta(minutes=eligible_minute),
        side=side,
        entry_reference=100.0,
        risk_unit=risk_unit,
        features=features,
        barrier_config=config,
        policy_digest="locked-indicator-policy-v1",
        estimated_roundtrip_cost_bps=cost_bps,
        adverse_entry_bps=adverse_bps,
        gap_policy=gap_policy,
    )


def _minute(
    minute: int,
    *,
    open: float = 100.0,
    high: float = 101.0,
    low: float = 99.5,
    close: float = 100.0,
    is_real: bool = True,
    observed_at: datetime | None = None,
    scheduled_session_gap_verified: bool = False,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "asset": "BTCUSDT",
        "timestamp": BASE + timedelta(minutes=minute),
        "open": open,
        "high": high,
        "low": low,
        "close": close,
        "is_real": is_real,
        "scheduled_session_gap_verified": scheduled_session_gap_verified,
    }
    if observed_at is not None:
        payload["observed_at"] = observed_at
    return payload


def test_candidate_is_frozen_json_safe_and_duplicate_schedule_is_digest_idempotent() -> (
    None
):
    candidate = _candidate("event-1")
    payload = candidate.as_dict()
    json.dumps(payload, allow_nan=False)
    assert payload["asset"] == "BTCUSDT"
    assert payload["timeframe"] == "15m"
    assert payload["barrier_config_digest"] == candidate.barrier_config.digest()
    with pytest.raises(FrozenInstanceError):
        candidate.risk_unit = 2.0  # type: ignore[misc]

    book = ShadowEventBook(max_open_events=2, max_resolved_records=2)
    first = book.schedule(candidate)
    duplicate = book.schedule(candidate)
    assert first.as_dict() == duplicate.as_dict()
    assert book.total_scheduled == 1

    conflicting = _candidate("event-1", cost_bps=6.0)
    with pytest.raises(ValueError, match="different candidate digest"):
        book.schedule(conflicting)

    book.schedule(_candidate("event-2", eligible_minute=2))
    with pytest.raises(ShadowBookCapacityError):
        book.schedule(_candidate("event-3", eligible_minute=3))


@pytest.mark.parametrize(
    ("bar", "expected"),
    [
        ({"high": 103.0}, BarrierOutcome.TARGET),
        ({"low": 98.0}, BarrierOutcome.STOP),
        ({"high": 103.0, "low": 98.0}, BarrierOutcome.AMBIGUOUS),
    ],
)
def test_shadow_preserves_every_barrier_tracker_outcome_and_actual_plan(
    bar: dict[str, float],
    expected: BarrierOutcome,
) -> None:
    book = ShadowEventBook()
    candidate = _candidate(
        f"outcome-{expected.value.lower()}",
        cost_bps=20.0,
        adverse_bps=10.0,
    )
    book.schedule(candidate)
    changed = book.update(_minute(1, **bar))
    assert len(changed) == 1
    record = changed[0]

    assert record.state is ShadowEventState.RESOLVED
    assert record.outcome is expected
    assert record.fill is not None
    assert record.plan is not None
    assert record.evaluation is not None
    assert record.fill.source_open == 100.0
    assert record.fill.fill_price == pytest.approx(100.1)
    assert record.plan.fill_price == record.fill.fill_price
    assert record.plan.activated_at == BASE + timedelta(minutes=1)
    assert record.label_known_at == BASE + timedelta(minutes=2)
    assert record.economic_binary_target == int(expected is BarrierOutcome.TARGET)
    json.dumps(record.as_dict(), allow_nan=False)


def test_shadow_timeout_counts_accepted_target_bars_not_execution_minutes() -> None:
    book = ShadowEventBook()
    book.schedule(
        _candidate(
            "target-clock-timeout",
            risk_unit=10.0,
            timeout_target_bars=2,
        )
    )

    for minute in range(1, 15):
        changed = book.update(_minute(minute))
        assert changed[0].state is ShadowEventState.ACTIVE
    assert book.get("target-clock-timeout").target_bars_elapsed == 0  # type: ignore[union-attr]

    first = book.advance_target_bar(
        asset="BTCUSDT",
        timeframe="15m",
        bar_open=BASE,
        close_price=100.0,
        observed_at=BASE + timedelta(minutes=15),
    )
    assert len(first) == 1
    assert first[0].state is ShadowEventState.ACTIVE
    assert first[0].target_bars_elapsed == 1

    for minute in range(15, 30):
        changed = book.update(_minute(minute))
        assert changed[0].state is ShadowEventState.ACTIVE
    timeout = book.advance_target_bar(
        asset="BTCUSDT",
        timeframe="15m",
        bar_open=BASE + timedelta(minutes=15),
        close_price=100.2,
        observed_at=BASE + timedelta(minutes=30, seconds=9),
    )[0]
    assert timeout.outcome is BarrierOutcome.TIMEOUT
    assert timeout.target_bars_elapsed == 2
    assert timeout.occurred_at == BASE + timedelta(minutes=30)
    assert timeout.label_known_at == BASE + timedelta(minutes=30, seconds=9)
    assert timeout.observed_bars == 29


def test_shadow_last_constituent_touch_resolves_before_timeout_advance() -> None:
    book = ShadowEventBook()
    book.schedule(_candidate("last-touch", timeout_target_bars=1))
    for minute in range(1, 14):
        book.update(_minute(minute))

    target = book.update(_minute(14, high=103.0, close=102.0))[0]
    assert target.outcome is BarrierOutcome.TARGET
    assert target.label_known_at == BASE + timedelta(minutes=15)
    assert (
        book.advance_target_bar(
            asset="BTCUSDT",
            timeframe="15m",
            bar_open=BASE,
            close_price=102.0,
            observed_at=BASE + timedelta(minutes=15),
        )
        == ()
    )


def test_shadow_barrier_label_uses_actual_delayed_observation_time() -> None:
    book = ShadowEventBook()
    book.schedule(_candidate("delayed-label"))
    observed_at = BASE + timedelta(minutes=2, seconds=41)
    target = book.update(_minute(1, high=103.0, observed_at=observed_at))[0]

    assert target.outcome is BarrierOutcome.TARGET
    assert target.occurred_at == BASE + timedelta(minutes=1)
    assert target.label_known_at == observed_at
    assert target.last_observation_at == observed_at


def test_economic_target_requires_target_first_and_positive_net_after_costs() -> None:
    book = ShadowEventBook()
    candidate = _candidate("expensive-target", cost_bps=250.0)
    book.schedule(candidate)
    record = book.update(_minute(1, high=103.0))[0]

    assert record.outcome is BarrierOutcome.TARGET
    assert record.gross_return_bps == pytest.approx(200.0)
    assert record.net_return_bps == pytest.approx(-50.0)
    assert record.economic_binary_target == 0
    assert record.evaluation is not None
    assert record.evaluation.default_binary_label == 1


def test_adverse_entry_cost_is_not_deducted_twice_from_shadow_return() -> None:
    book = ShadowEventBook()
    book.schedule(
        _candidate(
            "non-double-counted-cost",
            cost_bps=30.0,
            adverse_bps=10.0,
        )
    )
    record = book.update(_minute(1, high=103.0))[0]

    assert record.outcome is BarrierOutcome.TARGET
    assert record.gross_return_bps == pytest.approx(2.0 / 100.1 * 10_000.0)
    assert record.embedded_entry_execution_bps == 10.0
    assert record.deducted_cost_bps == 20.0
    assert record.net_return_bps == pytest.approx(record.gross_return_bps - 20.0)
    assert record.net_return_bps != pytest.approx(record.gross_return_bps - 30.0)


def test_batch_matches_incremental_prefix_restore_with_overlapping_candidates() -> None:
    candidates = (
        _candidate("fast", eligible_minute=1, risk_unit=1.0),
        _candidate("wide", eligible_minute=2, risk_unit=2.0),
    )
    bars = [
        _minute(1),
        _minute(2, high=102.5, low=99.5, close=102.0),
        _minute(3, open=100.0, high=101.0, low=97.0, close=98.0),
    ]

    batch = ShadowEventBook()
    prefix = ShadowEventBook()
    for candidate in candidates:
        batch.schedule(candidate)
        prefix.schedule(candidate)
    batch.update_batch(bars)

    prefix.update_batch(bars[:2])
    restored = ShadowEventBook.from_snapshot(prefix.snapshot())
    restored.update_batch(bars[2:])

    assert batch.snapshot() == restored.snapshot()
    assert batch.get("fast").outcome is BarrierOutcome.TARGET  # type: ignore[union-attr]
    assert batch.get("wide").outcome is BarrierOutcome.STOP  # type: ignore[union-attr]
    assert batch.total_resolved == 2
    assert batch.total_filled == 2


def test_unverified_gap_cancels_both_markets_and_verified_session_gap_can_fill() -> (
    None
):
    continuous = _candidate("continuous")
    session = _candidate("session", gap_policy=ShadowGapPolicy.SESSION_NEXT_OPEN)
    book = ShadowEventBook()
    book.schedule(continuous)
    book.schedule(session)

    cancelled = book.update(_minute(1, is_real=False))
    assert len(cancelled) == 2
    assert {record.outcome for record in cancelled} == {BarrierOutcome.CANCELLED}
    assert all(record.fill is None for record in cancelled)
    assert all(record.plan is None for record in cancelled)
    assert all(record.economic_binary_target is None for record in cancelled)
    assert all(
        record.label_known_at == BASE + timedelta(minutes=2) for record in cancelled
    )

    verified = ShadowEventBook()
    verified.schedule(
        _candidate("verified-session", gap_policy=ShadowGapPolicy.SESSION_NEXT_OPEN)
    )
    filled = verified.update(_minute(2, scheduled_session_gap_verified=True))[0]
    assert filled.candidate.event_id == "verified-session"
    assert filled.state is ShadowEventState.ACTIVE
    assert filled.fill is not None
    assert filled.fill.filled_at == BASE + timedelta(minutes=2)

    direct_gap = ShadowEventBook()
    direct_gap.schedule(_candidate("direct-gap"))
    late = direct_gap.update(_minute(3))[0]
    assert late.outcome is BarrierOutcome.CANCELLED
    assert "missing_eligible" in str(late.reason)


def test_active_events_cancel_on_unknown_path_but_verified_session_gap_survives() -> (
    None
):
    continuous = _candidate("active-continuous", timeout_target_bars=5)
    session = _candidate(
        "active-session",
        timeout_target_bars=5,
        gap_policy=ShadowGapPolicy.SESSION_NEXT_OPEN,
    )
    book = ShadowEventBook()
    book.schedule(continuous)
    book.schedule(session)
    first = book.update(_minute(1))
    assert {record.state for record in first} == {ShadowEventState.ACTIVE}

    changed = book.update(_minute(3))
    continuous_record = next(
        record for record in changed if record.candidate.event_id == "active-continuous"
    )
    session_record = next(
        record for record in changed if record.candidate.event_id == "active-session"
    )
    assert continuous_record.outcome is BarrierOutcome.CANCELLED
    assert continuous_record.fill is not None
    assert continuous_record.plan is not None
    assert continuous_record.observed_bars == 1
    assert continuous_record.last_observed_at == BASE + timedelta(minutes=1)
    assert continuous_record.occurred_at == BASE + timedelta(minutes=2)
    assert continuous_record.label_known_at == BASE + timedelta(minutes=4)
    assert continuous_record.economic_binary_target is None
    assert session_record.outcome is BarrierOutcome.CANCELLED
    assert session_record.reason == "session_market_unverified_data_gap_unknown_path"

    verified = ShadowEventBook()
    verified.schedule(
        _candidate(
            "active-verified-session",
            timeout_target_bars=5,
            gap_policy=ShadowGapPolicy.SESSION_NEXT_OPEN,
        )
    )
    verified.update(_minute(1))
    survived = verified.update(_minute(3, scheduled_session_gap_verified=True))[0]
    assert survived.state is ShadowEventState.ACTIVE
    assert survived.observed_bars == 2


def test_resolved_deque_is_bounded_while_lifetime_counters_are_retained() -> None:
    book = ShadowEventBook(max_open_events=3, max_resolved_records=2)
    for minute in range(1, 4):
        book.schedule(
            _candidate(
                f"timeout-{minute}",
                eligible_minute=minute,
                risk_unit=10.0,
                timeout_target_bars=1,
            )
        )
    for minute in range(1, 15):
        book.update(_minute(minute))
    resolved = book.advance_target_bar(
        asset="BTCUSDT",
        timeframe="15m",
        bar_open=BASE,
        close_price=100.0,
        observed_at=BASE + timedelta(minutes=15),
    )
    assert len(resolved) == 3

    view = book.view(resolved_limit=1)
    json.dumps(view, allow_nan=False)
    assert book.total_resolved == 3
    assert book.outcome_counts[BarrierOutcome.TIMEOUT.value] == 3
    assert view["resolved_retained_count"] == 2
    assert view["resolved_returned_count"] == 1
    assert view["resolved_truncated_count"] == 2
    assert book.get("timeout-1") is None
    assert [row["event_id"] for row in view["resolved"]] == ["timeout-3"]


def test_snapshot_restores_pending_active_and_resolved_records_and_rejects_tampering() -> (
    None
):
    book = ShadowEventBook(max_open_events=4, max_resolved_records=4)
    book.schedule(_candidate("resolved", risk_unit=1.0))
    book.schedule(_candidate("active", risk_unit=10.0, timeout_target_bars=4))
    book.schedule(_candidate("pending", eligible_minute=3, risk_unit=10.0))
    book.update(_minute(1, high=103.0))

    before = book.snapshot()
    json.dumps(before, allow_nan=False)
    restored = ShadowEventBook.from_snapshot(before)
    assert restored.snapshot() == before
    assert restored.get("resolved").state is ShadowEventState.RESOLVED  # type: ignore[union-attr]
    assert restored.get("active").state is ShadowEventState.ACTIVE  # type: ignore[union-attr]
    assert restored.get("pending").state is ShadowEventState.PENDING  # type: ignore[union-attr]

    original_active_bars = restored.get("active").observed_bars  # type: ignore[union-attr]
    restored.update(_minute(2))
    assert restored.get("active").observed_bars == original_active_bars + 1  # type: ignore[union-attr]

    tampered = copy.deepcopy(before)
    tampered["total_filled"] = 99
    with pytest.raises(ValueError, match="checksum"):
        ShadowEventBook.from_snapshot(tampered)


def test_shadow_candidate_rejects_versionless_nested_barrier_config() -> None:
    payload = _candidate("versionless-config").as_dict()
    payload["barrier_config"].pop("schema_version")

    with pytest.raises(ValueError, match="unsupported barrier config schema_version"):
        ShadowCandidate.from_dict(payload)


def test_pending_and_active_records_are_visible_in_bounded_json_view() -> None:
    book = ShadowEventBook(max_open_events=3, max_resolved_records=2)
    book.schedule(_candidate("active-view", risk_unit=10.0))
    book.schedule(_candidate("pending-view", eligible_minute=3, risk_unit=10.0))
    book.update(_minute(1))

    view = book.view()
    assert view["active_count"] == 1
    assert view["pending_count"] == 1
    assert view["active"][0]["event_id"] == "active-view"
    assert view["pending"][0]["event_id"] == "pending-view"
    json.dumps(view, allow_nan=False)

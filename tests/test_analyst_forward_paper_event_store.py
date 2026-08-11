from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ANALYST_ROOT = (
    Path(__file__).resolve().parents[1] / "Risk_Yield_Meta_Model_Analyst_0_0_1"
)
if str(ANALYST_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYST_ROOT))

from forward_paper.event_store import (  # noqa: E402
    GENESIS_HASH,
    ChainIntegrityError,
    EventConflictError,
    EventInput,
    EventStore,
    RunConflictError,
    RunInput,
    ServiceStateConflictError,
    ServiceStateInput,
    SnapshotInput,
    StoreLockError,
)

RUN_TIME = "2026-07-11T20:00:00Z"
EVENT_TIME = "2026-07-11T20:01:00Z"
OBSERVED_TIME = "2026-07-11T20:01:05Z"


def _run(run_id: str = "paper-run-001") -> RunInput:
    return RunInput(
        run_id=run_id,
        created_at=RUN_TIME,
        metadata={"mode": "paper", "starting_cash": 10_000.0},
    )


def _event(
    event_id: str,
    *,
    payload: dict[str, object] | None = None,
    expected_hash: str | None = None,
) -> EventInput:
    return EventInput(
        event_id=event_id,
        stream_id="BTCUSDT:1m",
        event_type="final_bar_observed",
        occurred_at=EVENT_TIME,
        observed_at=OBSERVED_TIME,
        payload=payload or {"close": 117_500.25, "is_final": True},
        expected_hash=expected_hash,
    )


def test_wal_safety_settings_and_deterministic_idempotent_batch(tmp_path: Path) -> None:
    path = tmp_path / "paper.db"
    with EventStore(path) as store:
        created = store.create_run(_run())
        same_run = store.create_run(_run())
        assert same_run == created
        assert len(created.run_hash) == 64
        assert store.settings() == {
            "journal_mode": "wal",
            "synchronous": 2,
            "foreign_keys": 1,
            "schema_version": 1,
        }

        first = _event("bar-001")
        second = _event("bar-002", payload={"close": 117_510.0})
        snapshot = SnapshotInput(
            snapshot_id="engine-snapshot-002",
            stream_id="BTCUSDT:1m",
            captured_at=OBSERVED_TIME,
            after_event_id="bar-002",
            payload={"bars_seen": 2},
        )
        service_state = ServiceStateInput(
            checkpoint_id="service-checkpoint-002",
            service_id="minute-poller",
            recorded_at=OBSERVED_TIME,
            after_event_id="bar-002",
            payload={"cycle": 2},
        )
        inserted = store.append_batch(
            "paper-run-001",
            [first, second],
            snapshots=[snapshot],
            service_states=[service_state],
        )
        assert inserted.inserted_event_count == 2
        assert inserted.inserted_snapshot_count == 1
        assert inserted.inserted_service_state_count == 1
        assert inserted.events[0].prior_hash == GENESIS_HASH
        assert inserted.events[1].prior_hash == inserted.events[0].event_hash
        assert all(len(event.event_hash) == 64 for event in inserted.events)

        retried = store.append_batch(
            "paper-run-001",
            [first, second],
            snapshots=[snapshot],
            service_states=[service_state],
        )
        assert retried.events == inserted.events
        assert retried.inserted_event_count == 0
        assert retried.snapshots == inserted.snapshots
        assert retried.service_states == inserted.service_states
        assert retried.inserted_snapshot_count == 0
        assert retried.inserted_service_state_count == 0
        assert (
            store.verify_chain("paper-run-001").head_hash
            == inserted.events[-1].event_hash
        )

    with EventStore(tmp_path / "identical-input.db") as second_store:
        second_store.create_run(_run())
        deterministic = second_store.append_batch(
            "paper-run-001", [first, second]
        ).events
        assert [event.event_hash for event in deterministic] == [
            event.event_hash for event in inserted.events
        ]


def test_immutable_identifier_conflicts_are_fatal(tmp_path: Path) -> None:
    with EventStore(tmp_path / "paper.db") as store:
        store.create_run(_run())
        with pytest.raises(RunConflictError, match="different immutable content"):
            store.create_run(
                RunInput(
                    run_id="paper-run-001",
                    created_at=RUN_TIME,
                    metadata={"mode": "live"},
                )
            )

        stored = store.append_batch("paper-run-001", [_event("bar-001")]).events[0]
        exact_hash_retry = _event("bar-001", expected_hash=stored.event_hash)
        assert (
            store.append_batch("paper-run-001", [exact_hash_retry]).events[0] == stored
        )

        with pytest.raises(EventConflictError, match="different immutable content"):
            store.append_batch(
                "paper-run-001",
                [_event("bar-001", payload={"close": 1.0})],
            )


def test_atomic_batch_rolls_back_events_snapshots_and_checkpoint(
    tmp_path: Path,
) -> None:
    path = tmp_path / "paper.db"
    with EventStore(path) as store:
        store.create_run(_run())
        store.append_batch(
            "paper-run-001",
            service_states=[
                ServiceStateInput(
                    checkpoint_id="service-checkpoint-existing",
                    service_id="minute-poller",
                    recorded_at=EVENT_TIME,
                    payload={"cycle": 1},
                )
            ],
        )

        with pytest.raises(ServiceStateConflictError):
            store.append_batch(
                "paper-run-001",
                [_event("bar-rollback")],
                snapshots=[
                    SnapshotInput(
                        snapshot_id="engine-rollback",
                        stream_id="BTCUSDT:1m",
                        captured_at=OBSERVED_TIME,
                        after_event_id="bar-rollback",
                        payload={"bars_seen": 1},
                    )
                ],
                service_states=[
                    ServiceStateInput(
                        checkpoint_id="service-checkpoint-existing",
                        service_id="minute-poller",
                        recorded_at=OBSERVED_TIME,
                        payload={"cycle": 999},
                    )
                ],
            )

        assert store.events("paper-run-001") == ()
        assert store.latest_snapshot("BTCUSDT:1m") is None
        state = store.latest_service_state("minute-poller")
        assert state is not None
        assert state.payload == {"cycle": 1}


def test_restart_restores_latest_snapshot_state_and_chain(tmp_path: Path) -> None:
    path = tmp_path / "paper.db"
    with EventStore(path) as store:
        store.create_run(_run())
        result = store.append_batch(
            "paper-run-001",
            [_event("bar-001")],
            snapshots=[
                SnapshotInput(
                    snapshot_id="engine-snapshot-001",
                    stream_id="BTCUSDT:1m",
                    captured_at=OBSERVED_TIME,
                    after_event_id="bar-001",
                    payload={"bars_seen": 401, "position": 0.4},
                )
            ],
            service_states=[
                ServiceStateInput(
                    checkpoint_id="service-checkpoint-001",
                    service_id="minute-poller",
                    recorded_at=OBSERVED_TIME,
                    after_event_id="bar-001",
                    payload={"last_cycle": EVENT_TIME, "healthy": True},
                )
            ],
        )
        event_hash = result.events[0].event_hash

    with EventStore(path) as restored:
        event = restored.events("paper-run-001")[0]
        snapshot = restored.latest_snapshot("BTCUSDT:1m")
        state = restored.latest_service_state("minute-poller")

        assert event.event_hash == event_hash
        assert snapshot is not None
        assert snapshot.payload == {"bars_seen": 401, "position": 0.4}
        assert snapshot.after_event_hash == event_hash
        assert snapshot.after_sequence_no == 1
        assert state is not None
        assert state.payload == {"healthy": True, "last_cycle": EVENT_TIME}
        assert state.after_event_hash == event_hash
        assert restored.verify_chain("paper-run-001").event_count == 1


def test_verify_chain_detects_out_of_band_corruption(tmp_path: Path) -> None:
    path = tmp_path / "paper.db"
    with EventStore(path) as store:
        store.create_run(_run())
        store.append_batch(
            "paper-run-001",
            [_event("bar-001"), _event("bar-002", payload={"close": 117_510.0})],
        )

    # Simulate hostile/out-of-band database tampering.  The production trigger
    # has to be removed first because ordinary UPDATE/DELETE operations are
    # deliberately rejected by the schema.
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TRIGGER events_no_update")
        connection.execute(
            """
            UPDATE events
            SET payload_json = '{"close":1.0}'
            WHERE run_id = 'paper-run-001' AND sequence_no = 1
            """
        )

    with EventStore(path) as store:
        with pytest.raises(ChainIntegrityError, match="hash mismatch"):
            store.verify_chain("paper-run-001")


def test_process_lock_allows_only_one_writer_and_releases_on_close(
    tmp_path: Path,
) -> None:
    path = tmp_path / "paper.db"
    first = EventStore(path)
    try:
        with pytest.raises(StoreLockError, match="another writer"):
            EventStore(path)
    finally:
        first.close()

    with EventStore(path) as reopened:
        reopened.create_run(_run())
        assert reopened.get_run("paper-run-001") is not None


def test_json_and_timestamp_inputs_are_strictly_restart_safe(tmp_path: Path) -> None:
    with EventStore(tmp_path / "paper.db") as store:
        store.create_run(_run())
        with pytest.raises(ValueError, match="non-finite"):
            store.append_batch(
                "paper-run-001",
                [_event("bad-json", payload={"price": float("nan")})],
            )
        with pytest.raises(ValueError, match="include a timezone"):
            store.append_batch(
                "paper-run-001",
                [
                    EventInput(
                        event_id="bad-time",
                        stream_id="BTCUSDT:1m",
                        event_type="bar",
                        occurred_at="2026-07-11T20:01:00",
                        payload={},
                    )
                ],
            )
        with pytest.raises(ValueError, match="must not precede occurred_at"):
            store.append_batch(
                "paper-run-001",
                [
                    EventInput(
                        event_id="observation-before-event",
                        stream_id="BTCUSDT:1m",
                        event_type="bar",
                        occurred_at=EVENT_TIME,
                        observed_at=RUN_TIME,
                        payload={},
                    )
                ],
            )

        assert store.events("paper-run-001") == ()

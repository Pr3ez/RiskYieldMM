"""Restart-safe append-only journal for forward paper trading.

The database records what the live service observed at that point in time.  A
single writer owns a separate advisory lock file, while SQLite WAL permits
readers to inspect committed history.  Events are chained independently per
run so a later integrity pass can detect reordered, edited, or missing rows.

Only standard-library modules are used intentionally.  Callers should keep the
``EventStore`` open for the lifetime of the writer process and close it during
an orderly shutdown.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import sqlite3
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from types import TracebackType
from typing import Any, TypeAlias

GENESIS_HASH = "0" * 64
HASH_ALGORITHM = "sha256"
HASH_FORMAT_VERSION = 1
SCHEMA_VERSION = 1

JsonScalar: TypeAlias = None | bool | int | float | str
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
TimestampLike: TypeAlias = str | datetime


class EventStoreError(RuntimeError):
    """Base class for durable-journal failures."""


class StoreLockError(EventStoreError):
    """Raised when another writer already owns the store lock."""


class ClosedStoreError(EventStoreError):
    """Raised when an operation is attempted after closing the store."""


class RunConflictError(EventStoreError):
    """Raised when an immutable run identifier is reused with other content."""


class EventConflictError(EventStoreError):
    """Raised when an immutable event identifier is reused with another hash."""


class SnapshotConflictError(EventStoreError):
    """Raised when an immutable snapshot identifier is reused."""


class ServiceStateConflictError(EventStoreError):
    """Raised when an immutable checkpoint identifier is reused."""


class ChainIntegrityError(EventStoreError):
    """Raised when a stored event chain no longer verifies."""


@dataclass(frozen=True, slots=True)
class RunInput:
    """Immutable identity and metadata for one forward paper run."""

    run_id: str
    created_at: TimestampLike
    metadata: JsonValue


@dataclass(frozen=True, slots=True)
class EventInput:
    """One authoritative observation or paper-trading decision."""

    event_id: str
    stream_id: str
    event_type: str
    occurred_at: TimestampLike
    payload: JsonValue
    observed_at: TimestampLike | None = None
    expected_hash: str | None = None


@dataclass(frozen=True, slots=True)
class SnapshotInput:
    """Append-only engine snapshot optionally anchored to an event."""

    snapshot_id: str
    stream_id: str
    captured_at: TimestampLike
    payload: JsonValue
    run_id: str | None = None
    after_event_id: str | None = None


@dataclass(frozen=True, slots=True)
class ServiceStateInput:
    """Append-only service checkpoint used to resume orchestration state."""

    checkpoint_id: str
    service_id: str
    recorded_at: TimestampLike
    payload: JsonValue
    run_id: str | None = None
    after_event_id: str | None = None


@dataclass(frozen=True, slots=True)
class StoredRun:
    run_id: str
    created_at: str
    metadata: JsonValue
    run_hash: str

    def as_dict(self) -> dict[str, JsonValue]:
        return {
            "run_id": self.run_id,
            "created_at": self.created_at,
            "metadata": _copy_json(self.metadata),
            "run_hash": self.run_hash,
        }


@dataclass(frozen=True, slots=True)
class StoredEvent:
    run_id: str
    sequence_no: int
    event_id: str
    stream_id: str
    event_type: str
    occurred_at: str
    observed_at: str
    payload: JsonValue
    prior_hash: str
    event_hash: str

    def as_dict(self) -> dict[str, JsonValue]:
        return {
            "run_id": self.run_id,
            "sequence_no": self.sequence_no,
            "event_id": self.event_id,
            "stream_id": self.stream_id,
            "event_type": self.event_type,
            "occurred_at": self.occurred_at,
            "observed_at": self.observed_at,
            "payload": _copy_json(self.payload),
            "prior_hash": self.prior_hash,
            "event_hash": self.event_hash,
        }


@dataclass(frozen=True, slots=True)
class StoredSnapshot:
    ordinal: int
    snapshot_id: str
    run_id: str
    stream_id: str
    captured_at: str
    after_event_id: str | None
    after_sequence_no: int | None
    after_event_hash: str | None
    payload: JsonValue
    snapshot_hash: str

    def as_dict(self) -> dict[str, JsonValue]:
        return {
            "ordinal": self.ordinal,
            "snapshot_id": self.snapshot_id,
            "run_id": self.run_id,
            "stream_id": self.stream_id,
            "captured_at": self.captured_at,
            "after_event_id": self.after_event_id,
            "after_sequence_no": self.after_sequence_no,
            "after_event_hash": self.after_event_hash,
            "payload": _copy_json(self.payload),
            "snapshot_hash": self.snapshot_hash,
        }


@dataclass(frozen=True, slots=True)
class StoredServiceState:
    ordinal: int
    checkpoint_id: str
    run_id: str
    service_id: str
    recorded_at: str
    after_event_id: str | None
    after_sequence_no: int | None
    after_event_hash: str | None
    payload: JsonValue
    checkpoint_hash: str

    def as_dict(self) -> dict[str, JsonValue]:
        return {
            "ordinal": self.ordinal,
            "checkpoint_id": self.checkpoint_id,
            "run_id": self.run_id,
            "service_id": self.service_id,
            "recorded_at": self.recorded_at,
            "after_event_id": self.after_event_id,
            "after_sequence_no": self.after_sequence_no,
            "after_event_hash": self.after_event_hash,
            "payload": _copy_json(self.payload),
            "checkpoint_hash": self.checkpoint_hash,
        }


@dataclass(frozen=True, slots=True)
class BatchResult:
    events: tuple[StoredEvent, ...]
    snapshots: tuple[StoredSnapshot, ...]
    service_states: tuple[StoredServiceState, ...]
    inserted_event_count: int
    inserted_snapshot_count: int
    inserted_service_state_count: int

    def as_dict(self) -> dict[str, JsonValue]:
        return {
            "events": [event.as_dict() for event in self.events],
            "snapshots": [snapshot.as_dict() for snapshot in self.snapshots],
            "service_states": [state.as_dict() for state in self.service_states],
            "inserted_event_count": self.inserted_event_count,
            "inserted_snapshot_count": self.inserted_snapshot_count,
            "inserted_service_state_count": self.inserted_service_state_count,
        }


@dataclass(frozen=True, slots=True)
class ChainVerification:
    run_id: str
    event_count: int
    head_sequence_no: int
    head_hash: str

    def as_dict(self) -> dict[str, JsonValue]:
        return {
            "run_id": self.run_id,
            "event_count": self.event_count,
            "head_sequence_no": self.head_sequence_no,
            "head_hash": self.head_hash,
        }


class EventStore:
    """Single-writer SQLite WAL journal with immutable authoritative rows."""

    def __init__(self, database_path: str | Path, *, timeout_seconds: float = 5.0):
        self.database_path = Path(database_path).expanduser().resolve()
        self.lock_path = Path(f"{self.database_path}.lock")
        self._mutex = RLock()
        self._lock_fd: int | None = None
        self._connection: sqlite3.Connection | None = None

        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._acquire_process_lock()
            self._connection = sqlite3.connect(
                self.database_path,
                timeout=timeout_seconds,
                isolation_level=None,
                check_same_thread=False,
            )
            self._connection.row_factory = sqlite3.Row
            self._configure_connection(timeout_seconds)
            self._create_schema()
        except BaseException:
            self.close()
            raise

    def __enter__(self) -> EventStore:
        self._require_open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Close SQLite and release the one-writer advisory lock."""

        with self._mutex:
            connection, self._connection = self._connection, None
            if connection is not None:
                connection.close()
            lock_fd, self._lock_fd = self._lock_fd, None
            if lock_fd is not None:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                finally:
                    os.close(lock_fd)

    def settings(self) -> dict[str, JsonValue]:
        """Return the safety-critical SQLite settings for diagnostics."""

        with self._mutex:
            connection = self._require_open()
            return {
                "journal_mode": str(
                    connection.execute("PRAGMA journal_mode").fetchone()[0]
                ).lower(),
                "synchronous": int(
                    connection.execute("PRAGMA synchronous").fetchone()[0]
                ),
                "foreign_keys": int(
                    connection.execute("PRAGMA foreign_keys").fetchone()[0]
                ),
                "schema_version": int(
                    connection.execute("PRAGMA user_version").fetchone()[0]
                ),
            }

    def create_run(self, run: RunInput) -> StoredRun:
        """Insert an immutable run, or return an identical prior insertion."""

        run_id = _identifier(run.run_id, "run_id")
        created_at = _timestamp(run.created_at, "created_at")
        metadata_json = _canonical_json(run.metadata)
        run_hash = _hash_json(
            {
                "created_at": created_at,
                "metadata": json.loads(metadata_json),
                "run_id": run_id,
            }
        )
        with self._mutex, self._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if row is not None:
                stored = _stored_run(row)
                if (
                    stored.run_hash != run_hash
                    or stored.created_at != created_at
                    or _canonical_json(stored.metadata) != metadata_json
                ):
                    raise RunConflictError(
                        f"run_id {run_id!r} already exists with different immutable content"
                    )
                return stored
            connection.execute(
                """
                INSERT INTO runs (run_id, created_at, metadata_json, run_hash)
                VALUES (?, ?, ?, ?)
                """,
                (run_id, created_at, metadata_json, run_hash),
            )
            return StoredRun(
                run_id=run_id,
                created_at=created_at,
                metadata=json.loads(metadata_json),
                run_hash=run_hash,
            )

    def get_run(self, run_id: str) -> StoredRun | None:
        with self._mutex:
            connection = self._require_open()
            row = connection.execute(
                "SELECT * FROM runs WHERE run_id = ?",
                (_identifier(run_id, "run_id"),),
            ).fetchone()
            return None if row is None else _stored_run(row)

    def append_batch(
        self,
        run_id: str,
        events: Sequence[EventInput] = (),
        *,
        snapshots: Sequence[SnapshotInput] = (),
        service_states: Sequence[ServiceStateInput] = (),
    ) -> BatchResult:
        """Atomically append events, snapshots, and service checkpoints.

        Existing identifiers are accepted only if their deterministic content
        hash is identical.  A conflict anywhere in the batch rolls back every
        earlier insertion made by that call.
        """

        normalized_run_id = _identifier(run_id, "run_id")
        with self._mutex, self._transaction() as connection:
            if (
                connection.execute(
                    "SELECT 1 FROM runs WHERE run_id = ?", (normalized_run_id,)
                ).fetchone()
                is None
            ):
                raise EventStoreError(f"unknown run_id {normalized_run_id!r}")

            tail = connection.execute(
                """
                SELECT sequence_no, event_hash
                FROM events
                WHERE run_id = ?
                ORDER BY sequence_no DESC
                LIMIT 1
                """,
                (normalized_run_id,),
            ).fetchone()
            next_sequence = 1 if tail is None else int(tail["sequence_no"]) + 1
            prior_hash = GENESIS_HASH if tail is None else str(tail["event_hash"])

            stored_events: list[StoredEvent] = []
            inserted_events = 0
            for event in events:
                existing = connection.execute(
                    """
                    SELECT * FROM events
                    WHERE run_id = ? AND event_id = ?
                    """,
                    (
                        normalized_run_id,
                        _identifier(event.event_id, "event_id"),
                    ),
                ).fetchone()
                if existing is not None:
                    stored = _match_existing_event(existing, normalized_run_id, event)
                    stored_events.append(stored)
                    continue

                normalized = _normalize_event(
                    run_id=normalized_run_id,
                    sequence_no=next_sequence,
                    prior_hash=prior_hash,
                    event=event,
                )
                if (
                    event.expected_hash is not None
                    and _sha256(event.expected_hash, "expected_hash")
                    != normalized.event_hash
                ):
                    raise EventConflictError(
                        f"event_id {normalized.event_id!r} expected hash does not "
                        "match its chain position and content"
                    )
                connection.execute(
                    """
                    INSERT INTO events (
                        run_id, sequence_no, event_id, stream_id, event_type,
                        occurred_at, observed_at, payload_json, prior_hash,
                        event_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        normalized.run_id,
                        normalized.sequence_no,
                        normalized.event_id,
                        normalized.stream_id,
                        normalized.event_type,
                        normalized.occurred_at,
                        normalized.observed_at,
                        _canonical_json(normalized.payload),
                        normalized.prior_hash,
                        normalized.event_hash,
                    ),
                )
                stored_events.append(normalized)
                inserted_events += 1
                next_sequence += 1
                prior_hash = normalized.event_hash

            stored_snapshots: list[StoredSnapshot] = []
            inserted_snapshots = 0
            for snapshot in snapshots:
                stored, inserted = self._append_snapshot(
                    connection, normalized_run_id, snapshot
                )
                stored_snapshots.append(stored)
                inserted_snapshots += int(inserted)

            stored_states: list[StoredServiceState] = []
            inserted_states = 0
            for service_state in service_states:
                stored, inserted = self._append_service_state(
                    connection, normalized_run_id, service_state
                )
                stored_states.append(stored)
                inserted_states += int(inserted)

            return BatchResult(
                events=tuple(stored_events),
                snapshots=tuple(stored_snapshots),
                service_states=tuple(stored_states),
                inserted_event_count=inserted_events,
                inserted_snapshot_count=inserted_snapshots,
                inserted_service_state_count=inserted_states,
            )

    def events(
        self,
        run_id: str,
        *,
        after_sequence_no: int = 0,
        limit: int | None = None,
    ) -> tuple[StoredEvent, ...]:
        """Read committed events in authoritative chain order."""

        if after_sequence_no < 0:
            raise ValueError("after_sequence_no must be non-negative")
        if limit is not None and limit <= 0:
            raise ValueError("limit must be positive")
        query = """
            SELECT * FROM events
            WHERE run_id = ? AND sequence_no > ?
            ORDER BY sequence_no
        """
        params: tuple[Any, ...] = (
            _identifier(run_id, "run_id"),
            after_sequence_no,
        )
        if limit is not None:
            query += " LIMIT ?"
            params += (limit,)
        with self._mutex:
            connection = self._require_open()
            return tuple(
                _stored_event(row) for row in connection.execute(query, params)
            )

    def latest_snapshot(self, stream_id: str) -> StoredSnapshot | None:
        """Return the most recently committed snapshot for a stream."""

        with self._mutex:
            connection = self._require_open()
            row = connection.execute(
                """
                SELECT * FROM snapshots
                WHERE stream_id = ?
                ORDER BY ordinal DESC
                LIMIT 1
                """,
                (_identifier(stream_id, "stream_id"),),
            ).fetchone()
            return None if row is None else _stored_snapshot(row)

    def latest_service_state(self, service_id: str) -> StoredServiceState | None:
        """Return the latest restart checkpoint for a service instance."""

        with self._mutex:
            connection = self._require_open()
            row = connection.execute(
                """
                SELECT * FROM service_state
                WHERE service_id = ?
                ORDER BY ordinal DESC
                LIMIT 1
                """,
                (_identifier(service_id, "service_id"),),
            ).fetchone()
            return None if row is None else _stored_service_state(row)

    def verify_chain(self, run_id: str) -> ChainVerification:
        """Recompute and validate every link in a run's event chain."""

        normalized_run_id = _identifier(run_id, "run_id")
        with self._mutex:
            connection = self._require_open()
            if (
                connection.execute(
                    "SELECT 1 FROM runs WHERE run_id = ?", (normalized_run_id,)
                ).fetchone()
                is None
            ):
                raise ChainIntegrityError(f"unknown run_id {normalized_run_id!r}")
            rows = connection.execute(
                "SELECT * FROM events WHERE run_id = ? ORDER BY sequence_no",
                (normalized_run_id,),
            ).fetchall()

        expected_prior = GENESIS_HASH
        expected_sequence = 1
        for row in rows:
            try:
                payload = json.loads(str(row["payload_json"]))
                canonical_payload = _canonical_json(payload)
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ChainIntegrityError(
                    f"run {normalized_run_id!r} event sequence {expected_sequence} "
                    "contains invalid JSON"
                ) from exc
            if canonical_payload != str(row["payload_json"]):
                raise ChainIntegrityError(
                    f"run {normalized_run_id!r} event sequence {expected_sequence} "
                    "payload is not canonical JSON"
                )
            if int(row["sequence_no"]) != expected_sequence:
                raise ChainIntegrityError(
                    f"run {normalized_run_id!r} has a sequence gap at "
                    f"{expected_sequence}"
                )
            if str(row["prior_hash"]) != expected_prior:
                raise ChainIntegrityError(
                    f"run {normalized_run_id!r} event sequence {expected_sequence} "
                    "has the wrong prior hash"
                )
            expected_hash = _event_hash(
                run_id=normalized_run_id,
                sequence_no=expected_sequence,
                event_id=str(row["event_id"]),
                stream_id=str(row["stream_id"]),
                event_type=str(row["event_type"]),
                occurred_at=str(row["occurred_at"]),
                observed_at=str(row["observed_at"]),
                payload=payload,
                prior_hash=expected_prior,
            )
            if str(row["event_hash"]) != expected_hash:
                raise ChainIntegrityError(
                    f"run {normalized_run_id!r} event sequence {expected_sequence} "
                    "hash mismatch"
                )
            expected_prior = expected_hash
            expected_sequence += 1

        return ChainVerification(
            run_id=normalized_run_id,
            event_count=len(rows),
            head_sequence_no=len(rows),
            head_hash=expected_prior,
        )

    def _append_snapshot(
        self,
        connection: sqlite3.Connection,
        batch_run_id: str,
        snapshot: SnapshotInput,
    ) -> tuple[StoredSnapshot, bool]:
        snapshot_id = _identifier(snapshot.snapshot_id, "snapshot_id")
        run_id = _batch_item_run_id(batch_run_id, snapshot.run_id)
        stream_id = _identifier(snapshot.stream_id, "stream_id")
        captured_at = _timestamp(snapshot.captured_at, "captured_at")
        payload_json = _canonical_json(snapshot.payload)
        anchor = _resolve_anchor(connection, run_id, snapshot.after_event_id)
        snapshot_hash = _hash_json(
            {
                "after_event_hash": anchor[2],
                "after_event_id": anchor[0],
                "after_sequence_no": anchor[1],
                "captured_at": captured_at,
                "payload": json.loads(payload_json),
                "run_id": run_id,
                "snapshot_id": snapshot_id,
                "stream_id": stream_id,
            }
        )
        existing = connection.execute(
            "SELECT * FROM snapshots WHERE snapshot_id = ?", (snapshot_id,)
        ).fetchone()
        if existing is not None:
            stored = _stored_snapshot(existing)
            if stored.snapshot_hash != snapshot_hash:
                raise SnapshotConflictError(
                    f"snapshot_id {snapshot_id!r} already exists with different content"
                )
            return stored, False
        cursor = connection.execute(
            """
            INSERT INTO snapshots (
                snapshot_id, run_id, stream_id, captured_at, after_event_id,
                after_sequence_no, after_event_hash, payload_json, snapshot_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot_id,
                run_id,
                stream_id,
                captured_at,
                anchor[0],
                anchor[1],
                anchor[2],
                payload_json,
                snapshot_hash,
            ),
        )
        row = connection.execute(
            "SELECT * FROM snapshots WHERE ordinal = ?", (cursor.lastrowid,)
        ).fetchone()
        if row is None:  # pragma: no cover - SQLite guarantees RETURNED row
            raise EventStoreError("snapshot insert could not be read back")
        return _stored_snapshot(row), True

    def _append_service_state(
        self,
        connection: sqlite3.Connection,
        batch_run_id: str,
        state: ServiceStateInput,
    ) -> tuple[StoredServiceState, bool]:
        checkpoint_id = _identifier(state.checkpoint_id, "checkpoint_id")
        run_id = _batch_item_run_id(batch_run_id, state.run_id)
        service_id = _identifier(state.service_id, "service_id")
        recorded_at = _timestamp(state.recorded_at, "recorded_at")
        payload_json = _canonical_json(state.payload)
        anchor = _resolve_anchor(connection, run_id, state.after_event_id)
        checkpoint_hash = _hash_json(
            {
                "after_event_hash": anchor[2],
                "after_event_id": anchor[0],
                "after_sequence_no": anchor[1],
                "checkpoint_id": checkpoint_id,
                "payload": json.loads(payload_json),
                "recorded_at": recorded_at,
                "run_id": run_id,
                "service_id": service_id,
            }
        )
        existing = connection.execute(
            "SELECT * FROM service_state WHERE checkpoint_id = ?",
            (checkpoint_id,),
        ).fetchone()
        if existing is not None:
            stored = _stored_service_state(existing)
            if stored.checkpoint_hash != checkpoint_hash:
                raise ServiceStateConflictError(
                    f"checkpoint_id {checkpoint_id!r} already exists with different content"
                )
            return stored, False
        cursor = connection.execute(
            """
            INSERT INTO service_state (
                checkpoint_id, run_id, service_id, recorded_at,
                after_event_id, after_sequence_no, after_event_hash,
                payload_json, checkpoint_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                checkpoint_id,
                run_id,
                service_id,
                recorded_at,
                anchor[0],
                anchor[1],
                anchor[2],
                payload_json,
                checkpoint_hash,
            ),
        )
        row = connection.execute(
            "SELECT * FROM service_state WHERE ordinal = ?", (cursor.lastrowid,)
        ).fetchone()
        if row is None:  # pragma: no cover - SQLite guarantees RETURNED row
            raise EventStoreError("service-state insert could not be read back")
        return _stored_service_state(row), True

    def _acquire_process_lock(self) -> None:
        lock_fd = os.open(self.lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            os.close(lock_fd)
            raise StoreLockError(
                f"another writer owns event-store lock {self.lock_path}"
            ) from exc
        self._lock_fd = lock_fd
        owner = _canonical_json(
            {
                "database_path": str(self.database_path),
                "locked_at": _timestamp(datetime.now(timezone.utc), "locked_at"),
                "pid": os.getpid(),
            }
        ).encode("utf-8")
        os.ftruncate(lock_fd, 0)
        os.write(lock_fd, owner)
        os.fsync(lock_fd)

    def _configure_connection(self, timeout_seconds: float) -> None:
        connection = self._require_open()
        connection.execute(
            f"PRAGMA busy_timeout = {max(1, int(timeout_seconds * 1000))}"
        )
        journal_mode = str(
            connection.execute("PRAGMA journal_mode = WAL").fetchone()[0]
        ).lower()
        if journal_mode != "wal":
            raise EventStoreError(f"SQLite refused WAL mode: {journal_mode!r}")
        connection.execute("PRAGMA synchronous = FULL")
        connection.execute("PRAGMA foreign_keys = ON")
        if int(connection.execute("PRAGMA foreign_keys").fetchone()[0]) != 1:
            raise EventStoreError("SQLite foreign-key enforcement is unavailable")

    def _create_schema(self) -> None:
        connection = self._require_open()
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                run_hash TEXT NOT NULL CHECK(length(run_hash) = 64)
            ) STRICT;

            CREATE TABLE IF NOT EXISTS events (
                run_id TEXT NOT NULL,
                sequence_no INTEGER NOT NULL CHECK(sequence_no > 0),
                event_id TEXT NOT NULL,
                stream_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                prior_hash TEXT NOT NULL CHECK(length(prior_hash) = 64),
                event_hash TEXT NOT NULL CHECK(length(event_hash) = 64),
                PRIMARY KEY (run_id, sequence_no),
                UNIQUE (run_id, event_id),
                FOREIGN KEY (run_id) REFERENCES runs(run_id)
            ) STRICT;

            CREATE INDEX IF NOT EXISTS events_live_source_scan
                ON events(run_id, stream_id, event_type, sequence_no);

            CREATE TABLE IF NOT EXISTS snapshots (
                ordinal INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id TEXT NOT NULL UNIQUE,
                run_id TEXT NOT NULL,
                stream_id TEXT NOT NULL,
                captured_at TEXT NOT NULL,
                after_event_id TEXT,
                after_sequence_no INTEGER,
                after_event_hash TEXT,
                payload_json TEXT NOT NULL,
                snapshot_hash TEXT NOT NULL CHECK(length(snapshot_hash) = 64),
                FOREIGN KEY (run_id) REFERENCES runs(run_id),
                FOREIGN KEY (run_id, after_event_id)
                    REFERENCES events(run_id, event_id)
            ) STRICT;

            CREATE INDEX IF NOT EXISTS snapshots_stream_ordinal
                ON snapshots(stream_id, ordinal DESC);

            CREATE TABLE IF NOT EXISTS service_state (
                ordinal INTEGER PRIMARY KEY AUTOINCREMENT,
                checkpoint_id TEXT NOT NULL UNIQUE,
                run_id TEXT NOT NULL,
                service_id TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                after_event_id TEXT,
                after_sequence_no INTEGER,
                after_event_hash TEXT,
                payload_json TEXT NOT NULL,
                checkpoint_hash TEXT NOT NULL CHECK(length(checkpoint_hash) = 64),
                FOREIGN KEY (run_id) REFERENCES runs(run_id),
                FOREIGN KEY (run_id, after_event_id)
                    REFERENCES events(run_id, event_id)
            ) STRICT;

            CREATE INDEX IF NOT EXISTS service_state_service_ordinal
                ON service_state(service_id, ordinal DESC);

            CREATE TRIGGER IF NOT EXISTS runs_no_update
            BEFORE UPDATE ON runs BEGIN
                SELECT RAISE(ABORT, 'runs are immutable');
            END;
            CREATE TRIGGER IF NOT EXISTS runs_no_delete
            BEFORE DELETE ON runs BEGIN
                SELECT RAISE(ABORT, 'runs are immutable');
            END;
            CREATE TRIGGER IF NOT EXISTS events_no_update
            BEFORE UPDATE ON events BEGIN
                SELECT RAISE(ABORT, 'events are immutable');
            END;
            CREATE TRIGGER IF NOT EXISTS events_no_delete
            BEFORE DELETE ON events BEGIN
                SELECT RAISE(ABORT, 'events are immutable');
            END;
            CREATE TRIGGER IF NOT EXISTS snapshots_no_update
            BEFORE UPDATE ON snapshots BEGIN
                SELECT RAISE(ABORT, 'snapshots are append-only');
            END;
            CREATE TRIGGER IF NOT EXISTS snapshots_no_delete
            BEFORE DELETE ON snapshots BEGIN
                SELECT RAISE(ABORT, 'snapshots are append-only');
            END;
            CREATE TRIGGER IF NOT EXISTS service_state_no_update
            BEFORE UPDATE ON service_state BEGIN
                SELECT RAISE(ABORT, 'service_state is append-only');
            END;
            CREATE TRIGGER IF NOT EXISTS service_state_no_delete
            BEFORE DELETE ON service_state BEGIN
                SELECT RAISE(ABORT, 'service_state is append-only');
            END;
            """
        )
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    @contextmanager
    def _transaction(self) -> Any:
        connection = self._require_open()
        connection.execute("BEGIN IMMEDIATE")
        try:
            yield connection
        except BaseException:
            connection.rollback()
            raise
        else:
            connection.commit()

    def _require_open(self) -> sqlite3.Connection:
        if self._connection is None:
            raise ClosedStoreError("event store is closed")
        return self._connection


def _normalize_event(
    *,
    run_id: str,
    sequence_no: int,
    prior_hash: str,
    event: EventInput,
) -> StoredEvent:
    event_id = _identifier(event.event_id, "event_id")
    stream_id = _identifier(event.stream_id, "stream_id")
    event_type = _identifier(event.event_type, "event_type")
    occurred_at = _timestamp(event.occurred_at, "occurred_at")
    observed_at = _timestamp(
        event.observed_at if event.observed_at is not None else event.occurred_at,
        "observed_at",
    )
    if observed_at < occurred_at:
        raise ValueError("observed_at must not precede occurred_at")
    payload_json = _canonical_json(event.payload)
    payload = json.loads(payload_json)
    event_hash = _event_hash(
        run_id=run_id,
        sequence_no=sequence_no,
        event_id=event_id,
        stream_id=stream_id,
        event_type=event_type,
        occurred_at=occurred_at,
        observed_at=observed_at,
        payload=payload,
        prior_hash=prior_hash,
    )
    return StoredEvent(
        run_id=run_id,
        sequence_no=sequence_no,
        event_id=event_id,
        stream_id=stream_id,
        event_type=event_type,
        occurred_at=occurred_at,
        observed_at=observed_at,
        payload=payload,
        prior_hash=prior_hash,
        event_hash=event_hash,
    )


def _match_existing_event(
    row: sqlite3.Row, run_id: str, event: EventInput
) -> StoredEvent:
    stored = _stored_event(row)
    incoming = _normalize_event(
        run_id=run_id,
        sequence_no=stored.sequence_no,
        prior_hash=stored.prior_hash,
        event=event,
    )
    if event.expected_hash is not None:
        expected_hash = _sha256(event.expected_hash, "expected_hash")
        if expected_hash != incoming.event_hash:
            raise EventConflictError(
                f"event_id {incoming.event_id!r} expected hash does not match content"
            )
    if incoming != stored:
        raise EventConflictError(
            f"event_id {incoming.event_id!r} already exists with different "
            "immutable content or hash"
        )
    return stored


def _event_hash(
    *,
    run_id: str,
    sequence_no: int,
    event_id: str,
    stream_id: str,
    event_type: str,
    occurred_at: str,
    observed_at: str,
    payload: JsonValue,
    prior_hash: str,
) -> str:
    return _hash_json(
        {
            "event_id": event_id,
            "event_type": event_type,
            "hash_algorithm": HASH_ALGORITHM,
            "hash_format_version": HASH_FORMAT_VERSION,
            "observed_at": observed_at,
            "occurred_at": occurred_at,
            "payload": payload,
            "prior_hash": prior_hash,
            "run_id": run_id,
            "sequence_no": sequence_no,
            "stream_id": stream_id,
        }
    )


def _resolve_anchor(
    connection: sqlite3.Connection,
    run_id: str,
    after_event_id: str | None,
) -> tuple[str | None, int | None, str | None]:
    if after_event_id is None:
        return None, None, None
    normalized_event_id = _identifier(after_event_id, "after_event_id")
    row = connection.execute(
        """
        SELECT event_id, sequence_no, event_hash
        FROM events
        WHERE run_id = ? AND event_id = ?
        """,
        (run_id, normalized_event_id),
    ).fetchone()
    if row is None:
        raise EventStoreError(
            f"snapshot/checkpoint anchor event {normalized_event_id!r} does not "
            f"exist in run {run_id!r}"
        )
    return str(row["event_id"]), int(row["sequence_no"]), str(row["event_hash"])


def _batch_item_run_id(batch_run_id: str, item_run_id: str | None) -> str:
    if item_run_id is None:
        return batch_run_id
    normalized = _identifier(item_run_id, "run_id")
    if normalized != batch_run_id:
        raise EventStoreError(
            f"batch run_id {batch_run_id!r} does not match item run_id {normalized!r}"
        )
    return normalized


def _stored_run(row: sqlite3.Row) -> StoredRun:
    return StoredRun(
        run_id=str(row["run_id"]),
        created_at=str(row["created_at"]),
        metadata=json.loads(str(row["metadata_json"])),
        run_hash=str(row["run_hash"]),
    )


def _stored_event(row: sqlite3.Row) -> StoredEvent:
    return StoredEvent(
        run_id=str(row["run_id"]),
        sequence_no=int(row["sequence_no"]),
        event_id=str(row["event_id"]),
        stream_id=str(row["stream_id"]),
        event_type=str(row["event_type"]),
        occurred_at=str(row["occurred_at"]),
        observed_at=str(row["observed_at"]),
        payload=json.loads(str(row["payload_json"])),
        prior_hash=str(row["prior_hash"]),
        event_hash=str(row["event_hash"]),
    )


def _stored_snapshot(row: sqlite3.Row) -> StoredSnapshot:
    return StoredSnapshot(
        ordinal=int(row["ordinal"]),
        snapshot_id=str(row["snapshot_id"]),
        run_id=str(row["run_id"]),
        stream_id=str(row["stream_id"]),
        captured_at=str(row["captured_at"]),
        after_event_id=(
            None if row["after_event_id"] is None else str(row["after_event_id"])
        ),
        after_sequence_no=(
            None if row["after_sequence_no"] is None else int(row["after_sequence_no"])
        ),
        after_event_hash=(
            None if row["after_event_hash"] is None else str(row["after_event_hash"])
        ),
        payload=json.loads(str(row["payload_json"])),
        snapshot_hash=str(row["snapshot_hash"]),
    )


def _stored_service_state(row: sqlite3.Row) -> StoredServiceState:
    return StoredServiceState(
        ordinal=int(row["ordinal"]),
        checkpoint_id=str(row["checkpoint_id"]),
        run_id=str(row["run_id"]),
        service_id=str(row["service_id"]),
        recorded_at=str(row["recorded_at"]),
        after_event_id=(
            None if row["after_event_id"] is None else str(row["after_event_id"])
        ),
        after_sequence_no=(
            None if row["after_sequence_no"] is None else int(row["after_sequence_no"])
        ),
        after_event_hash=(
            None if row["after_event_hash"] is None else str(row["after_event_hash"])
        ),
        payload=json.loads(str(row["payload_json"])),
        checkpoint_hash=str(row["checkpoint_hash"]),
    )


def _identifier(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    normalized = value.strip()
    if "\x00" in normalized:
        raise ValueError(f"{name} must not contain a NUL byte")
    return normalized


def _timestamp(value: TimestampLike, name: str) -> str:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        candidate = value.strip()
        try:
            parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{name} must be an ISO-8601 timestamp") from exc
    else:
        raise ValueError(f"{name} must be a timezone-aware datetime or string")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return (
        parsed.astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _canonical_json(value: JsonValue) -> str:
    normalized = _normalize_json(value, path="$", seen=set())
    return json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _normalize_json(value: Any, *, path: str, seen: set[int]) -> JsonValue:
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} contains a non-finite float")
        return value
    if isinstance(value, Mapping):
        object_id = id(value)
        if object_id in seen:
            raise ValueError(f"{path} contains a cyclic mapping")
        seen.add(object_id)
        try:
            normalized: dict[str, JsonValue] = {}
            for key, child in value.items():
                if not isinstance(key, str):
                    raise ValueError(f"{path} contains a non-string object key")
                normalized[key] = _normalize_json(
                    child, path=f"{path}.{key}", seen=seen
                )
            return normalized
        finally:
            seen.remove(object_id)
    if isinstance(value, (list, tuple)):
        object_id = id(value)
        if object_id in seen:
            raise ValueError(f"{path} contains a cyclic sequence")
        seen.add(object_id)
        try:
            return [
                _normalize_json(child, path=f"{path}[{index}]", seen=seen)
                for index, child in enumerate(value)
            ]
        finally:
            seen.remove(object_id)
    raise ValueError(f"{path} contains non-JSON value of type {type(value).__name__}")


def _copy_json(value: JsonValue) -> JsonValue:
    return json.loads(_canonical_json(value))


def _hash_json(value: JsonValue) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _sha256(value: str, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be a lowercase full SHA-256 hex digest")
    return value

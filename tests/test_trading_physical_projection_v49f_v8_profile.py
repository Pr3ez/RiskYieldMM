from __future__ import annotations

import concurrent.futures
import hashlib
import os
import sqlite3
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

import riskyieldmm.trading as trading_public
from riskyieldmm.trading import physical_projection_v4
from riskyieldmm.trading import physical_projection_v49f_v8 as projection_v8


def teardown_module() -> None:
    """Return the shared pytest process to the accepted Raw-V7 import profile."""

    sys.modules.pop(projection_v8.__name__, None)
    if getattr(trading_public, "physical_projection_v49f_v8", None) is projection_v8:
        delattr(trading_public, "physical_projection_v49f_v8")


class _InjectedInitializationFault(RuntimeError):
    pass


def _application_schema_object_count(path: Path) -> int:
    if not path.exists():
        return 0
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        row = connection.execute(
            """
            SELECT count(*)
            FROM sqlite_schema
            WHERE name NOT LIKE 'sqlite_%' AND sql IS NOT NULL
            """
        ).fetchone()
        assert row is not None
        return int(row[0])
    finally:
        connection.close()


def _raise_at(expected_stage: str):
    def inject(stage: str) -> None:
        if stage == expected_stage:
            raise _InjectedInitializationFault(stage)

    return inject


def test_raw_v8_schema_is_exact_v7_base_plus_exact_extension() -> None:
    base = physical_projection_v4._FULL_SCHEMA_SQL  # noqa: SLF001
    extension = projection_v8._RAW_V8_SCHEMA_EXTENSION_SQL_V49F  # noqa: SLF001
    full = projection_v8._RAW_V8_FULL_SCHEMA_SQL_V49F  # noqa: SLF001

    assert base.endswith("\n")
    assert not extension.startswith("\n")
    assert full == base + extension
    assert full[: len(base)] == base
    assert hashlib.sha256(base.encode()).hexdigest() == (
        "d4b311050f20f03159cd7d121421535e36f45a1d56d42022345ab9fdfcf088e5"
    )
    assert projection_v8._RAW_V8_SCHEMA_PROFILE_V49F.schema_sql is full  # noqa: SLF001
    assert (
        projection_v8._RAW_V8_SCHEMA_PROFILE_V49F  # noqa: SLF001
        is not physical_projection_v4._RAW_V7_SCHEMA_PROFILE_V4  # noqa: SLF001
    )

    connection = sqlite3.connect(":memory:", isolation_level=None)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(full)
        independently_replayed = physical_projection_v4._schema_fingerprint(  # noqa: SLF001
            connection,
            fingerprint_domain=(
                projection_v8.PHYSICAL_PROJECTION_V49F_V8_SCHEMA_FINGERPRINT_DOMAIN
            ),
        )
    finally:
        connection.close()
    assert independently_replayed == (
        physical_projection_v4._expected_schema_fingerprint_for_profile(  # noqa: SLF001
            projection_v8._RAW_V8_SCHEMA_PROFILE_V49F  # noqa: SLF001
        )
    )


def test_raw_v8_fresh_initialize_reopen_and_exact_empty_surface(
    tmp_path: Path,
) -> None:
    path = tmp_path / "projection-v8.sqlite"
    with projection_v8.PhysicalProjectionStoreV49FV8(path) as store:
        ledger_id = store.ledger_id
        fingerprint = store.schema_fingerprint
        report = store.verify()
        assert report.receipt_count == 0
        assert report.canonical_record_count == 0
        assert (
            fingerprint != physical_projection_v4._expected_schema_fingerprint().hex()
        )  # noqa: SLF001

        tables = {
            str(row[0])
            for row in store._connection.execute(  # noqa: SLF001
                "SELECT name FROM sqlite_schema WHERE type = 'table'"
            )
        }
        assert set(projection_v8._RAW_V8_TABLES_V49F) <= tables  # noqa: SLF001
        assert set(projection_v8._RAW_V7_LIFECYCLE_TABLES_V49F) <= tables  # noqa: SLF001
        for table in (
            *projection_v8._RAW_V8_TABLES_V49F,  # noqa: SLF001
            *projection_v8._RAW_V7_LIFECYCLE_TABLES_V49F,  # noqa: SLF001
        ):
            assert store._connection.execute(  # noqa: SLF001
                f"SELECT count(*) FROM {table}"
            ).fetchone() == (0,)

    with projection_v8.PhysicalProjectionStoreV49FV8(path) as reopened:
        assert reopened.ledger_id == ledger_id
        assert reopened.schema_fingerprint == fingerprint
        assert reopened.verify().receipt_count == 0


def test_raw_v8_profile_is_private_and_rejects_raw_v7_lifecycle_entry(
    tmp_path: Path,
) -> None:
    assert not hasattr(trading_public, "PhysicalProjectionStoreV49FV8")
    assert not hasattr(
        trading_public,
        "CAPACITY_MEASUREMENT_OPERATION_CANDIDATE_V49F_V8",
    )

    with projection_v8.PhysicalProjectionStoreV49FV8(
        tmp_path / "v8-private.sqlite"
    ) as store:
        with pytest.raises(
            physical_projection_v4.PhysicalProjectionV4ConfigurationError,
            match="exact Raw V7 schema profile",
        ):
            store._claim_capacity_measurement_startup_recovery_v49f()  # noqa: SLF001


def test_raw_v7_and_raw_v8_profiles_reject_substitution_both_ways(
    tmp_path: Path,
) -> None:
    v8_path = tmp_path / "v8.sqlite"
    with projection_v8.PhysicalProjectionStoreV49FV8(v8_path) as v8_store:
        v8_ledger = v8_store.ledger_id
    with pytest.raises(
        physical_projection_v4.PhysicalProjectionV4ConfigurationError,
        match="metadata versions are unsupported",
    ):
        physical_projection_v4.PhysicalProjectionStoreV4(v8_path)
    with projection_v8.PhysicalProjectionStoreV49FV8(v8_path) as v8_reopened:
        assert v8_reopened.ledger_id == v8_ledger

    v7_path = tmp_path / "v7.sqlite"
    with physical_projection_v4.PhysicalProjectionStoreV4(v7_path) as v7_store:
        v7_ledger = v7_store.ledger_id
    with pytest.raises(
        physical_projection_v4.PhysicalProjectionV4ConfigurationError,
        match="metadata versions are unsupported",
    ):
        projection_v8.PhysicalProjectionStoreV49FV8(v7_path)
    with physical_projection_v4.PhysicalProjectionStoreV4(v7_path) as v7_reopened:
        assert v7_reopened.ledger_id == v7_ledger


@pytest.mark.parametrize(
    "stage",
    (
        "raw_v8_initialize_before_schema_script",
        "raw_v8_initialize_after_schema_script",
        "raw_v8_initialize_after_metadata_insert",
        "raw_v8_initialize_before_commit",
    ),
)
def test_raw_v8_precommit_initialization_fault_has_no_committed_state_and_retries(
    tmp_path: Path,
    stage: str,
) -> None:
    path = tmp_path / f"{stage}.sqlite"
    with pytest.raises(_InjectedInitializationFault, match=stage):
        projection_v8.PhysicalProjectionStoreV49FV8(
            path,
            fault_injector=_raise_at(stage),
        )

    assert _application_schema_object_count(path) == 0
    lock_path = path.with_name(f".{path.name}.riskyieldmm-projection-provision.lock")
    lock_stat = lock_path.stat(follow_symlinks=False)
    assert stat.S_ISREG(lock_stat.st_mode)
    assert stat.S_IMODE(lock_stat.st_mode) & 0o077 == 0

    with projection_v8.PhysicalProjectionStoreV49FV8(path) as store:
        assert store.verify().receipt_count == 0


def test_raw_v8_after_commit_acknowledgement_fault_resolves_by_replay(
    tmp_path: Path,
) -> None:
    path = tmp_path / "after-commit.sqlite"
    with projection_v8.PhysicalProjectionStoreV49FV8(
        path,
        fault_injector=_raise_at("raw_v8_initialize_after_commit"),
    ) as store:
        ledger_id = store.ledger_id
        assert store.verify().receipt_count == 0

    with projection_v8.PhysicalProjectionStoreV49FV8(path) as reopened:
        assert reopened.ledger_id == ledger_id


def test_raw_v8_lost_commit_ack_reopens_an_unusable_connection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "lost-commit-ack.sqlite"
    real_connect = sqlite3.connect
    issued_fault_connection = False
    fault_connection: sqlite3.Connection | None = None

    class LostAcknowledgementConnection(sqlite3.Connection):
        acknowledgement_lost = False
        close_observed = False

        @property
        def in_transaction(self) -> bool:
            if self.acknowledgement_lost:
                raise sqlite3.ProgrammingError("connection became unusable")
            return super().in_transaction

        def execute(self, *args: object, **kwargs: object) -> sqlite3.Cursor:
            if self.acknowledgement_lost:
                raise sqlite3.ProgrammingError("connection became unusable")
            return super().execute(*args, **kwargs)

        def commit(self) -> None:
            super().commit()
            self.acknowledgement_lost = True
            raise sqlite3.OperationalError("simulated lost commit acknowledgement")

        def close(self) -> None:
            self.close_observed = True
            super().close()

    def connect(
        database: object,
        *args: object,
        **kwargs: object,
    ) -> sqlite3.Connection:
        nonlocal issued_fault_connection, fault_connection
        if str(database) == str(path) and not issued_fault_connection:
            issued_fault_connection = True
            kwargs["factory"] = LostAcknowledgementConnection
        connection = real_connect(database, *args, **kwargs)
        if isinstance(connection, LostAcknowledgementConnection):
            fault_connection = connection
        return connection

    monkeypatch.setattr(sqlite3, "connect", connect)
    with projection_v8.PhysicalProjectionStoreV49FV8(path) as store:
        ledger_id = store.ledger_id
        assert store.verify().receipt_count == 0

    assert fault_connection is not None
    assert fault_connection.close_observed
    with projection_v8.PhysicalProjectionStoreV49FV8(path) as reopened:
        assert reopened.ledger_id == ledger_id


def test_raw_v8_busy_commit_rolls_back_and_cleanly_retries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "busy-commit.sqlite"
    real_connect = sqlite3.connect
    issued_fault_connection = False
    fault_connection: BusyCommitConnection | None = None

    class BusyCommitConnection(sqlite3.Connection):
        rollback_observed = False

        def commit(self) -> None:
            assert self.in_transaction
            raise sqlite3.OperationalError("database is locked")

        def rollback(self) -> None:
            self.rollback_observed = True
            super().rollback()

    def connect(
        database: object,
        *args: object,
        **kwargs: object,
    ) -> sqlite3.Connection:
        nonlocal issued_fault_connection, fault_connection
        if str(database) == str(path) and not issued_fault_connection:
            issued_fault_connection = True
            kwargs["factory"] = BusyCommitConnection
        connection = real_connect(database, *args, **kwargs)
        if isinstance(connection, BusyCommitConnection):
            fault_connection = connection
        return connection

    monkeypatch.setattr(sqlite3, "connect", connect)
    with pytest.raises(
        physical_projection_v4.PhysicalProjectionV4ConfigurationError,
        match="initialization commit failed and was rolled back",
    ) as raised:
        projection_v8.PhysicalProjectionStoreV49FV8(path)
    assert isinstance(raised.value.__cause__, sqlite3.OperationalError)
    assert fault_connection is not None
    assert fault_connection.rollback_observed
    assert _application_schema_object_count(path) == 0

    with projection_v8.PhysicalProjectionStoreV49FV8(path) as retried:
        assert retried.verify().receipt_count == 0


@pytest.mark.parametrize(
    "stage",
    (
        "raw_v8_initialize_before_schema_script",
        "raw_v8_initialize_after_schema_script",
        "raw_v8_initialize_after_metadata_insert",
        "raw_v8_initialize_before_commit",
        "raw_v8_initialize_after_commit",
    ),
)
def test_raw_v8_process_death_during_initialization_reopens_deterministically(
    tmp_path: Path,
    stage: str,
) -> None:
    path = tmp_path / f"crash-{stage}.sqlite"
    child = """
import os
import sys
from riskyieldmm.trading.physical_projection_v49f_v8 import (
    PhysicalProjectionStoreV49FV8,
)

path, expected = sys.argv[1:]

def crash(stage):
    if stage == expected:
        os._exit(91)

PhysicalProjectionStoreV49FV8(path, fault_injector=crash)
"""
    result = subprocess.run(
        (sys.executable, "-c", child, str(path), stage),
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
        timeout=20.0,
    )
    assert result.returncode == 91, (result.stdout, result.stderr)

    with projection_v8.PhysicalProjectionStoreV49FV8(path) as reopened:
        assert reopened.verify().receipt_count == 0
        ledger_id = reopened.ledger_id
    with projection_v8.PhysicalProjectionStoreV49FV8(path) as reopened_again:
        assert reopened_again.ledger_id == ledger_id


def test_raw_v8_concurrent_creators_converge_on_one_ledger(tmp_path: Path) -> None:
    path = tmp_path / "racing-creators.sqlite"
    barrier = threading.Barrier(2)

    def create(*, delay: bool) -> str:
        barrier.wait(timeout=5.0)

        def injector(stage: str) -> None:
            if delay and stage == "raw_v8_initialize_before_schema_script":
                time.sleep(0.1)

        with projection_v8.PhysicalProjectionStoreV49FV8(
            path,
            fault_injector=injector,
        ) as store:
            assert store.verify().receipt_count == 0
            return store.ledger_id

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(
            future.result(timeout=10.0)
            for future in (
                executor.submit(create, delay=True),
                executor.submit(create, delay=False),
            )
        )

    assert len(set(results)) == 1
    with projection_v8.PhysicalProjectionStoreV49FV8(path) as reopened:
        assert reopened.ledger_id == results[0]


def test_cross_profile_concurrent_creators_select_exactly_one_profile(
    tmp_path: Path,
) -> None:
    path = tmp_path / "cross-profile-race.sqlite"
    barrier = threading.Barrier(2)

    def create(profile: str) -> tuple[str, str, str]:
        barrier.wait(timeout=5.0)
        store_type = (
            physical_projection_v4.PhysicalProjectionStoreV4
            if profile == "v7"
            else projection_v8.PhysicalProjectionStoreV49FV8
        )
        try:
            with store_type(path) as store:
                return ("accepted", profile, store.ledger_id)
        except physical_projection_v4.PhysicalProjectionV4ConfigurationError:
            return ("rejected", profile, "")

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(
            future.result(timeout=10.0)
            for future in (
                executor.submit(create, "v7"),
                executor.submit(create, "v8"),
            )
        )

    accepted = tuple(result for result in results if result[0] == "accepted")
    rejected = tuple(result for result in results if result[0] == "rejected")
    assert len(accepted) == 1
    assert len(rejected) == 1
    winner = accepted[0]
    store_type = (
        physical_projection_v4.PhysicalProjectionStoreV4
        if winner[1] == "v7"
        else projection_v8.PhysicalProjectionStoreV49FV8
    )
    with store_type(path) as reopened:
        assert reopened.ledger_id == winner[2]


def test_raw_v8_preserves_partial_or_wrong_profile_database_for_diagnosis(
    tmp_path: Path,
) -> None:
    path = tmp_path / "partial.sqlite"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE partial_state(value INTEGER)")
    connection.commit()
    connection.close()

    with pytest.raises(
        physical_projection_v4.PhysicalProjectionV4ConfigurationError,
        match="metadata/schema is absent or unreadable",
    ):
        projection_v8.PhysicalProjectionStoreV49FV8(path)

    assert path.exists()
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        assert connection.execute(
            "SELECT name FROM sqlite_schema WHERE name = 'partial_state'"
        ).fetchone() == ("partial_state",)
    finally:
        connection.close()


def test_raw_v8_preserves_non_sqlite_bytes_and_raises_typed_configuration_error(
    tmp_path: Path,
) -> None:
    path = tmp_path / "not-sqlite.sqlite"
    original = b"not a SQLite database\x00with retained forensic bytes"
    path.write_bytes(original)

    with pytest.raises(
        physical_projection_v4.PhysicalProjectionV4ConfigurationError,
        match="corrupt, unreadable, or not a SQLite database",
    ) as raised:
        projection_v8.PhysicalProjectionStoreV49FV8(path)
    assert isinstance(raised.value.__cause__, sqlite3.DatabaseError)
    assert path.read_bytes() == original


def test_raw_v8_cleanup_never_unlinks_replaced_main_inode(tmp_path: Path) -> None:
    path = tmp_path / "replaced.sqlite"
    replacement = tmp_path / "replacement.sqlite"
    connection = sqlite3.connect(replacement)
    connection.execute("CREATE TABLE replacement_witness(value INTEGER)")
    connection.commit()
    connection.close()

    def replace_then_fail(stage: str) -> None:
        if stage == "raw_v8_initialize_before_schema_script":
            os.replace(replacement, path)
            raise _InjectedInitializationFault(stage)

    with pytest.raises(
        _InjectedInitializationFault,
        match="raw_v8_initialize_before_schema_script",
    ):
        projection_v8.PhysicalProjectionStoreV49FV8(
            path,
            fault_injector=replace_then_fail,
        )

    assert path.exists()
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        assert connection.execute(
            "SELECT name FROM sqlite_schema WHERE name = 'replacement_witness'"
        ).fetchone() == ("replacement_witness",)
    finally:
        connection.close()


def test_raw_v8_rejects_database_path_replacement_after_existing_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "existing-a.sqlite"
    replacement = tmp_path / "existing-b.sqlite"
    displaced = tmp_path / "displaced-a.sqlite"
    with projection_v8.PhysicalProjectionStoreV49FV8(path) as first:
        first_ledger_id = first.ledger_id
    with projection_v8.PhysicalProjectionStoreV49FV8(replacement) as second:
        second_ledger_id = second.ledger_id
    assert first_ledger_id != second_ledger_id

    original_verify = projection_v8.PhysicalProjectionStoreV49FV8.verify
    replaced = False

    def replace_after_replay(
        store: projection_v8.PhysicalProjectionStoreV49FV8,
    ) -> physical_projection_v4.PhysicalProjectionVerificationReportV4:
        nonlocal replaced
        report = original_verify(store)
        if store.path == path and not replaced:
            replaced = True
            os.replace(path, displaced)
            os.replace(replacement, path)
        return report

    monkeypatch.setattr(
        projection_v8.PhysicalProjectionStoreV49FV8,
        "verify",
        replace_after_replay,
    )
    with pytest.raises(
        physical_projection_v4.PhysicalProjectionV4ConfigurationError,
        match="pathname device/inode changed after open",
    ):
        projection_v8.PhysicalProjectionStoreV49FV8(path)
    assert replaced
    assert path.exists()
    assert displaced.exists()

    monkeypatch.setattr(
        projection_v8.PhysicalProjectionStoreV49FV8,
        "verify",
        original_verify,
    )
    with projection_v8.PhysicalProjectionStoreV49FV8(path) as current:
        assert current.ledger_id == second_ledger_id
    with projection_v8.PhysicalProjectionStoreV49FV8(displaced) as original:
        assert original.ledger_id == first_ledger_id


def test_raw_v8_rejects_hard_link_alias_for_one_database_inode(
    tmp_path: Path,
) -> None:
    path = tmp_path / "canonical.sqlite"
    alias = tmp_path / "hard-link-alias.sqlite"
    with projection_v8.PhysicalProjectionStoreV49FV8(path) as initialized:
        ledger_id = initialized.ledger_id
    os.link(path, alias)

    with pytest.raises(
        physical_projection_v4.PhysicalProjectionV4ConfigurationError,
        match="must identify one unaliased regular file",
    ):
        projection_v8.PhysicalProjectionStoreV49FV8(alias)

    alias.unlink()
    with projection_v8.PhysicalProjectionStoreV49FV8(path) as reopened:
        assert reopened.ledger_id == ledger_id


def test_raw_v8_rejects_symlink_alias_for_database_path(tmp_path: Path) -> None:
    path = tmp_path / "canonical-symlink-target.sqlite"
    alias = tmp_path / "database-symlink.sqlite"
    with projection_v8.PhysicalProjectionStoreV49FV8(path) as initialized:
        ledger_id = initialized.ledger_id
    alias.symlink_to(path.name)

    with pytest.raises(
        physical_projection_v4.PhysicalProjectionV4ConfigurationError,
        match="main database path differs",
    ):
        projection_v8.PhysicalProjectionStoreV49FV8(alias)

    assert alias.is_symlink()
    with projection_v8.PhysicalProjectionStoreV49FV8(path) as reopened:
        assert reopened.ledger_id == ledger_id


def test_projection_provisioning_lease_rejects_broad_permissions(
    tmp_path: Path,
) -> None:
    path = tmp_path / "unsafe-lock.sqlite"
    lock_path = path.with_name(f".{path.name}.riskyieldmm-projection-provision.lock")
    lock_path.touch(mode=0o600)
    os.chmod(lock_path, 0o644)

    with pytest.raises(
        physical_projection_v4.PhysicalProjectionV4ConfigurationError,
        match="permissions are too broad",
    ):
        projection_v8.PhysicalProjectionStoreV49FV8(path)
    assert not path.exists()


def test_projection_provisioning_rejects_writable_parent_directory(
    tmp_path: Path,
) -> None:
    unsafe_parent = tmp_path / "unsafe-parent"
    unsafe_parent.mkdir(mode=0o700)
    os.chmod(unsafe_parent, 0o770)
    try:
        with pytest.raises(
            physical_projection_v4.PhysicalProjectionV4ConfigurationError,
            match="not group/world writable",
        ):
            projection_v8.PhysicalProjectionStoreV49FV8(
                unsafe_parent / "projection.sqlite"
            )
    finally:
        os.chmod(unsafe_parent, 0o700)


def test_projection_provisioning_detects_lock_inode_replacement(
    tmp_path: Path,
) -> None:
    path = tmp_path / "replaced-lock.sqlite"
    entered = threading.Event()
    release = threading.Event()
    outcomes: list[tuple[str, str]] = []

    def hold_before_schema(stage: str) -> None:
        if stage == "raw_v8_initialize_before_schema_script":
            entered.set()
            assert release.wait(timeout=5.0)

    def first_creator() -> None:
        try:
            with projection_v8.PhysicalProjectionStoreV49FV8(
                path,
                fault_injector=hold_before_schema,
            ):
                outcomes.append(("first", "accepted"))
        except BaseException as exc:
            outcomes.append(("first", f"{type(exc).__name__}:{exc}"))

    first = threading.Thread(target=first_creator)
    first.start()
    assert entered.wait(timeout=5.0)
    lock_path = path.with_name(f".{path.name}.riskyieldmm-projection-provision.lock")
    displaced_lock = tmp_path / "displaced-lock"
    os.replace(lock_path, displaced_lock)
    lock_path.touch(mode=0o600)

    try:
        with projection_v8.PhysicalProjectionStoreV49FV8(path) as second:
            outcomes.append(("second", second.ledger_id))
    finally:
        release.set()
        first.join(timeout=10.0)

    assert not first.is_alive()
    assert any(
        owner == "first" and "lease identity changed" in outcome
        for owner, outcome in outcomes
    )
    second_results = tuple(outcome for owner, outcome in outcomes if owner == "second")
    assert len(second_results) == 1
    with projection_v8.PhysicalProjectionStoreV49FV8(path) as reopened:
        assert reopened.ledger_id == second_results[0]


def test_projection_provisioning_revalidates_replaced_lock_when_body_raises(
    tmp_path: Path,
) -> None:
    path = tmp_path / "replaced-lock-and-body-failure.sqlite"
    lock_path = path.with_name(f".{path.name}.riskyieldmm-projection-provision.lock")
    displaced_lock = tmp_path / "displaced-lock-after-body-failure"

    def replace_lock_then_raise(stage: str) -> None:
        if stage == "raw_v8_initialize_before_schema_script":
            os.replace(lock_path, displaced_lock)
            lock_path.touch(mode=0o600)
            raise _InjectedInitializationFault(stage)

    with pytest.raises(
        physical_projection_v4.PhysicalProjectionV4ConfigurationError,
        match="lease identity changed",
    ) as raised:
        projection_v8.PhysicalProjectionStoreV49FV8(
            path,
            fault_injector=replace_lock_then_raise,
        )
    assert isinstance(raised.value.__cause__, _InjectedInitializationFault)
    assert displaced_lock.exists()
    assert lock_path.exists()

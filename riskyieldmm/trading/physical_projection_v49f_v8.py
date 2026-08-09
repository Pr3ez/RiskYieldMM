"""Private Raw V8 projection schema profile.

This module adds only the fresh, empty-store Raw V8 schema boundary.  It does
not implement V8 lifecycle records or permit V8 candidate receipts.  The
accepted Raw V7 store remains pinned to its original schema profile.
"""

from __future__ import annotations

import os
import secrets
import sqlite3
import stat
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from .canonical import CANONICALIZATION_VERSION, sha256_digest, utc_iso
from .physical_evidence_v4 import PHYSICAL_EVIDENCE_V4_SCHEMA_VERSION
from .physical_projection_v4 import (
    _FULL_SCHEMA_SQL,
    PhysicalProjectionStoreV4,
    PhysicalProjectionV4ConfigurationError,
    PhysicalProjectionV4VerificationError,
    _PhysicalProjectionSchemaProfileV4,
)

PHYSICAL_PROJECTION_V49F_V8_SCHEMA_VERSION = (
    "riskyieldmm_physical_projection_v4_9f_raw_v8"
)
PHYSICAL_PROJECTION_V49F_V8_VALIDATION_VERSION = (
    "riskyieldmm_physical_projection_validation_v4_9f_raw_v8"
)
PHYSICAL_PROJECTION_V49F_V8_SCHEMA_FINGERPRINT_DOMAIN = (
    "RiskYieldMMPhysicalProjectionSchemaFingerprintV4_9F_RawV8"
)
PHYSICAL_PROJECTION_V49F_V8_MAX_OBJECT_BYTES = 25_165_824

_RAW_V8_RECORD_KINDS_V49F = (
    "CAPACITY_MEASUREMENT_OPERATION_CANDIDATE_V49F_V8",
    "CAPACITY_MEASUREMENT_OPERATION_ATTEMPT_V49F_V8",
    "CAPACITY_MEASUREMENT_OPERATION_TERMINAL_V49F_V8",
    "CAPACITY_MEASUREMENT_MARKER_CLOSURE_V49F_V8",
)
_RAW_V7_RECORD_KINDS_V49F = (
    "CAPACITY_MEASUREMENT_OPERATION_ATTEMPT_V49F_V7",
    "CAPACITY_MEASUREMENT_OPERATION_TERMINAL_V49F_V7",
)
_RAW_V7_BATCH_OPERATIONS_V49F = (
    "APPEND_CAPACITY_MEASUREMENT_OPERATION_ATTEMPT_V49F_V7",
    "APPEND_CAPACITY_MEASUREMENT_OPERATION_TERMINAL_V49F_V7",
    "RECOVER_CAPACITY_MEASUREMENT_OPERATION_TERMINAL_V49F_V7",
)
_RAW_V8_TABLES_V49F = (
    "capacity_measurement_operation_candidates_v49f_v8",
    "capacity_measurement_operation_attempts_v49f_v8",
    "capacity_measurement_operation_terminals_v49f_v8",
    "capacity_measurement_marker_closures_v49f_v8",
    "capacity_measurement_open_candidates_v49f_v8",
)
_RAW_V7_LIFECYCLE_TABLES_V49F = (
    "capacity_measurement_operation_attempts_v49f",
    "capacity_measurement_operation_terminals_v49f",
    "capacity_measurement_open_attempts_v49f",
)

_RAW_V8_SCHEMA_EXTENSION_SQL_V49F = """CREATE TABLE capacity_measurement_operation_candidates_v49f_v8 (
    candidate_id BLOB PRIMARY KEY
        CHECK(typeof(candidate_id) = 'blob' AND length(candidate_id) = 32),
    declaration_id BLOB NOT NULL UNIQUE
        CHECK(typeof(declaration_id) = 'blob' AND length(declaration_id) = 32),
    campaign_manifest_id BLOB NOT NULL
        CHECK(typeof(campaign_manifest_id) = 'blob' AND
              length(campaign_manifest_id) = 32),
    transport_session_id BLOB NOT NULL
        CHECK(typeof(transport_session_id) = 'blob' AND
              length(transport_session_id) = 32),
    sample_sequence INTEGER NOT NULL CHECK(sample_sequence > 0),
    operation_sequence INTEGER NOT NULL CHECK(operation_sequence > 0),
    operation_kind TEXT NOT NULL CHECK(operation_kind IN (
        'ACK_DEADLINE_EXPIRY',
        'INGRESS',
        'LOCAL_SHUTDOWN',
        'SUBSCRIPTION_DISPATCH'
    )),
    previous_operation_terminal_id BLOB UNIQUE CHECK(
        previous_operation_terminal_id IS NULL OR
        (typeof(previous_operation_terminal_id) = 'blob' AND
         length(previous_operation_terminal_id) = 32)
    ),
    source_receipt_sequence INTEGER NOT NULL UNIQUE
        CHECK(source_receipt_sequence > 0),
    UNIQUE(campaign_manifest_id, sample_sequence, operation_sequence),
    FOREIGN KEY(candidate_id) REFERENCES canonical_records(identity_id),
    FOREIGN KEY(transport_session_id)
        REFERENCES transport_session_attestations(transport_session_id),
    FOREIGN KEY(previous_operation_terminal_id)
        REFERENCES capacity_measurement_operation_terminals_v49f_v8(terminal_id),
    FOREIGN KEY(source_receipt_sequence) REFERENCES receipts(global_sequence)
) STRICT;

CREATE UNIQUE INDEX capacity_measurement_first_candidate_session_v49f_v8
ON capacity_measurement_operation_candidates_v49f_v8(transport_session_id)
WHERE previous_operation_terminal_id IS NULL;

CREATE INDEX capacity_measurement_candidates_campaign_v49f_v8
ON capacity_measurement_operation_candidates_v49f_v8(
    campaign_manifest_id, operation_sequence, source_receipt_sequence
);

CREATE TABLE capacity_measurement_operation_attempts_v49f_v8 (
    attempt_id BLOB PRIMARY KEY
        CHECK(typeof(attempt_id) = 'blob' AND length(attempt_id) = 32),
    candidate_id BLOB NOT NULL UNIQUE
        CHECK(typeof(candidate_id) = 'blob' AND length(candidate_id) = 32),
    source_receipt_sequence INTEGER NOT NULL UNIQUE
        CHECK(source_receipt_sequence > 0),
    FOREIGN KEY(attempt_id) REFERENCES canonical_records(identity_id),
    FOREIGN KEY(candidate_id)
        REFERENCES capacity_measurement_operation_candidates_v49f_v8(candidate_id),
    FOREIGN KEY(source_receipt_sequence) REFERENCES receipts(global_sequence)
) STRICT;

CREATE TABLE capacity_measurement_operation_terminals_v49f_v8 (
    terminal_id BLOB PRIMARY KEY
        CHECK(typeof(terminal_id) = 'blob' AND length(terminal_id) = 32),
    candidate_id BLOB NOT NULL UNIQUE
        CHECK(typeof(candidate_id) = 'blob' AND length(candidate_id) = 32),
    attempt_id BLOB UNIQUE CHECK(
        attempt_id IS NULL OR
        (typeof(attempt_id) = 'blob' AND length(attempt_id) = 32)
    ),
    source_receipt_sequence INTEGER NOT NULL UNIQUE
        CHECK(source_receipt_sequence > 0),
    FOREIGN KEY(terminal_id) REFERENCES canonical_records(identity_id),
    FOREIGN KEY(candidate_id)
        REFERENCES capacity_measurement_operation_candidates_v49f_v8(candidate_id),
    FOREIGN KEY(attempt_id)
        REFERENCES capacity_measurement_operation_attempts_v49f_v8(attempt_id),
    FOREIGN KEY(source_receipt_sequence) REFERENCES receipts(global_sequence)
) STRICT;

CREATE TABLE capacity_measurement_marker_closures_v49f_v8 (
    closure_id BLOB PRIMARY KEY
        CHECK(typeof(closure_id) = 'blob' AND length(closure_id) = 32),
    candidate_id BLOB NOT NULL UNIQUE
        CHECK(typeof(candidate_id) = 'blob' AND length(candidate_id) = 32),
    attempt_id BLOB UNIQUE CHECK(
        attempt_id IS NULL OR
        (typeof(attempt_id) = 'blob' AND length(attempt_id) = 32)
    ),
    terminal_id BLOB NOT NULL UNIQUE
        CHECK(typeof(terminal_id) = 'blob' AND length(terminal_id) = 32),
    source_receipt_sequence INTEGER NOT NULL UNIQUE
        CHECK(source_receipt_sequence > 0),
    FOREIGN KEY(closure_id) REFERENCES canonical_records(identity_id),
    FOREIGN KEY(candidate_id)
        REFERENCES capacity_measurement_operation_candidates_v49f_v8(candidate_id),
    FOREIGN KEY(attempt_id)
        REFERENCES capacity_measurement_operation_attempts_v49f_v8(attempt_id),
    FOREIGN KEY(terminal_id)
        REFERENCES capacity_measurement_operation_terminals_v49f_v8(terminal_id),
    FOREIGN KEY(source_receipt_sequence) REFERENCES receipts(global_sequence)
) STRICT;

CREATE TABLE capacity_measurement_open_candidates_v49f_v8 (
    candidate_id BLOB PRIMARY KEY
        CHECK(typeof(candidate_id) = 'blob' AND length(candidate_id) = 32),
    transport_session_id BLOB NOT NULL UNIQUE
        CHECK(typeof(transport_session_id) = 'blob' AND
              length(transport_session_id) = 32),
    campaign_manifest_id BLOB NOT NULL
        CHECK(typeof(campaign_manifest_id) = 'blob' AND
              length(campaign_manifest_id) = 32),
    sample_sequence INTEGER NOT NULL CHECK(sample_sequence > 0),
    operation_sequence INTEGER NOT NULL CHECK(operation_sequence > 0),
    operation_kind TEXT NOT NULL CHECK(operation_kind IN (
        'ACK_DEADLINE_EXPIRY',
        'INGRESS',
        'LOCAL_SHUTDOWN',
        'SUBSCRIPTION_DISPATCH'
    )),
    candidate_receipt_sequence INTEGER NOT NULL UNIQUE
        CHECK(candidate_receipt_sequence > 0),
    UNIQUE(campaign_manifest_id, sample_sequence, operation_sequence),
    FOREIGN KEY(candidate_id)
        REFERENCES capacity_measurement_operation_candidates_v49f_v8(candidate_id),
    FOREIGN KEY(transport_session_id)
        REFERENCES transport_session_attestations(transport_session_id),
    FOREIGN KEY(candidate_receipt_sequence) REFERENCES receipts(global_sequence)
) STRICT;

CREATE TRIGGER capacity_measurement_operation_candidates_v49f_v8_no_update
BEFORE UPDATE ON capacity_measurement_operation_candidates_v49f_v8
BEGIN
    SELECT RAISE(
        ABORT,
        'capacity_measurement_operation_candidates_v49f_v8 is immutable'
    );
END;

CREATE TRIGGER capacity_measurement_operation_candidates_v49f_v8_no_delete
BEFORE DELETE ON capacity_measurement_operation_candidates_v49f_v8
BEGIN
    SELECT RAISE(
        ABORT,
        'capacity_measurement_operation_candidates_v49f_v8 is immutable'
    );
END;

CREATE TRIGGER capacity_measurement_operation_attempts_v49f_v8_no_update
BEFORE UPDATE ON capacity_measurement_operation_attempts_v49f_v8
BEGIN
    SELECT RAISE(
        ABORT,
        'capacity_measurement_operation_attempts_v49f_v8 is immutable'
    );
END;

CREATE TRIGGER capacity_measurement_operation_attempts_v49f_v8_no_delete
BEFORE DELETE ON capacity_measurement_operation_attempts_v49f_v8
BEGIN
    SELECT RAISE(
        ABORT,
        'capacity_measurement_operation_attempts_v49f_v8 is immutable'
    );
END;

CREATE TRIGGER capacity_measurement_operation_terminals_v49f_v8_no_update
BEFORE UPDATE ON capacity_measurement_operation_terminals_v49f_v8
BEGIN
    SELECT RAISE(
        ABORT,
        'capacity_measurement_operation_terminals_v49f_v8 is immutable'
    );
END;

CREATE TRIGGER capacity_measurement_operation_terminals_v49f_v8_no_delete
BEFORE DELETE ON capacity_measurement_operation_terminals_v49f_v8
BEGIN
    SELECT RAISE(
        ABORT,
        'capacity_measurement_operation_terminals_v49f_v8 is immutable'
    );
END;

CREATE TRIGGER capacity_measurement_marker_closures_v49f_v8_no_update
BEFORE UPDATE ON capacity_measurement_marker_closures_v49f_v8
BEGIN
    SELECT RAISE(
        ABORT,
        'capacity_measurement_marker_closures_v49f_v8 is immutable'
    );
END;

CREATE TRIGGER capacity_measurement_marker_closures_v49f_v8_no_delete
BEFORE DELETE ON capacity_measurement_marker_closures_v49f_v8
BEGIN
    SELECT RAISE(
        ABORT,
        'capacity_measurement_marker_closures_v49f_v8 is immutable'
    );
END;

CREATE TRIGGER capacity_measurement_open_candidates_v49f_v8_no_update
BEFORE UPDATE ON capacity_measurement_open_candidates_v49f_v8
BEGIN
    SELECT RAISE(
        ABORT,
        'capacity_measurement_open_candidates_v49f_v8 cannot be updated'
    );
END;
"""

_RAW_V8_FULL_SCHEMA_SQL_V49F = _FULL_SCHEMA_SQL + _RAW_V8_SCHEMA_EXTENSION_SQL_V49F
_RAW_V8_SCHEMA_PROFILE_V49F = _PhysicalProjectionSchemaProfileV4(
    schema_sql=_RAW_V8_FULL_SCHEMA_SQL_V49F,
    schema_version=PHYSICAL_PROJECTION_V49F_V8_SCHEMA_VERSION,
    validation_version=PHYSICAL_PROJECTION_V49F_V8_VALIDATION_VERSION,
    canonicalization_version=CANONICALIZATION_VERSION,
    physical_evidence_schema_version=PHYSICAL_EVIDENCE_V4_SCHEMA_VERSION,
    fingerprint_domain=PHYSICAL_PROJECTION_V49F_V8_SCHEMA_FINGERPRINT_DOMAIN,
)


def _projection_ledger_id_v49f_v8(
    *,
    nonce: bytes,
    created_at: str,
    schema_fingerprint: bytes,
) -> bytes:
    return bytes.fromhex(
        sha256_digest(
            {
                "canonicalization_version": (
                    _RAW_V8_SCHEMA_PROFILE_V49F.canonicalization_version
                ),
                "created_at": created_at,
                "domain": "RiskYieldMMPhysicalProjectionLedgerIdentityV4",
                "nonce": nonce.hex(),
                "physical_evidence_schema_version": (
                    _RAW_V8_SCHEMA_PROFILE_V49F.physical_evidence_schema_version
                ),
                "projection_schema_fingerprint": schema_fingerprint.hex(),
                "projection_schema_version": (
                    _RAW_V8_SCHEMA_PROFILE_V49F.schema_version
                ),
                "validation_version": (_RAW_V8_SCHEMA_PROFILE_V49F.validation_version),
            }
        )
    )


class PhysicalProjectionStoreV49FV8(PhysicalProjectionStoreV4):
    """Fresh, store-pinned Raw V8 projection profile without lifecycle writes."""

    _PINNED_SCHEMA_PROFILE_V4 = _RAW_V8_SCHEMA_PROFILE_V49F

    def __init__(
        self,
        path: str | Path,
        *,
        clock: Callable[[], datetime] | None = None,
        fault_injector: Callable[[str], None] | None = None,
    ) -> None:
        try:
            super().__init__(
                path,
                clock=clock,
                fault_injector=fault_injector,
                max_object_bytes=PHYSICAL_PROJECTION_V49F_V8_MAX_OBJECT_BYTES,
            )
        except sqlite3.OperationalError as exc:
            sqlite_error_code = getattr(exc, "sqlite_errorcode", None)
            primary_error_code = (
                int(sqlite_error_code) & 0xFF
                if isinstance(sqlite_error_code, int)
                else None
            )
            if primary_error_code in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
                raise PhysicalProjectionV4ConfigurationError(
                    "Raw V8 projection initialization was blocked by SQLite contention"
                ) from exc
            raise PhysicalProjectionV4ConfigurationError(
                "Raw V8 projection is corrupt, unreadable, or not a SQLite database"
            ) from exc
        except sqlite3.Error as exc:
            raise PhysicalProjectionV4ConfigurationError(
                "Raw V8 projection is corrupt, unreadable, or not a SQLite database"
            ) from exc

    def _derive_projection_ledger_id_v4(
        self,
        *,
        nonce: bytes,
        created_at: str,
        schema_fingerprint: bytes,
    ) -> bytes:
        if self._projection_schema_profile_v4() is not _RAW_V8_SCHEMA_PROFILE_V49F:
            raise PhysicalProjectionV4ConfigurationError(
                "Raw V8 store left its exact pinned schema profile"
            )
        return _projection_ledger_id_v49f_v8(
            nonce=nonce,
            created_at=created_at,
            schema_fingerprint=schema_fingerprint,
        )

    def _existing_projection_is_uninitialized_v4(self) -> bool:
        if self._projection_provisioning_lease_fd_v4 is None:
            raise PhysicalProjectionV4ConfigurationError(
                "Raw V8 committed-state classification requires the provisioning lease"
            )
        if self._connection.in_transaction:
            raise PhysicalProjectionV4ConfigurationError(
                "Raw V8 committed-state classification requires transaction quiescence"
            )
        try:
            row = self._connection.execute(
                """
                SELECT count(*)
                FROM sqlite_schema
                WHERE name NOT LIKE 'sqlite_%' AND sql IS NOT NULL
                """
            ).fetchone()
        except sqlite3.Error as exc:
            raise PhysicalProjectionV4ConfigurationError(
                "Raw V8 committed-state classification failed"
            ) from exc
        if row is None:
            raise PhysicalProjectionV4ConfigurationError(
                "Raw V8 committed-state classification returned no result"
            )
        return int(row[0]) == 0

    def _projection_requires_protected_parent_v4(self) -> bool:
        return True

    def _assert_projection_database_path_stable_v4(self) -> None:
        try:
            observed_path = self._main_database_path_from_connection_v49f()
            observed = os.stat(observed_path, follow_symlinks=True)
        except OSError as exc:
            raise PhysicalProjectionV4ConfigurationError(
                "Raw V8 database pathname identity cannot be revalidated"
            ) from exc
        if not stat.S_ISREG(observed.st_mode) or observed.st_nlink != 1:
            raise PhysicalProjectionV4ConfigurationError(
                "Raw V8 database pathname must identify one unaliased regular file"
            )
        if (
            self._database_device_v49f is None
            or self._database_inode_v49f is None
            or (observed.st_dev, observed.st_ino)
            != (self._database_device_v49f, self._database_inode_v49f)
        ):
            raise PhysicalProjectionV4ConfigurationError(
                "Raw V8 database pathname device/inode changed after open"
            )

    def _validate_meta(self, *, expected_max_object_bytes: int) -> None:
        try:
            super()._validate_meta(expected_max_object_bytes=expected_max_object_bytes)
        except sqlite3.Error as exc:
            raise PhysicalProjectionV4ConfigurationError(
                "Raw V8 projection metadata/schema is absent or unreadable"
            ) from exc

    def _initialize_schema(self, *, max_object_bytes: int) -> None:
        profile = self._projection_schema_profile_v4()
        if (
            profile is not _RAW_V8_SCHEMA_PROFILE_V49F
            or max_object_bytes != PHYSICAL_PROJECTION_V49F_V8_MAX_OBJECT_BYTES
        ):
            raise PhysicalProjectionV4ConfigurationError(
                "Raw V8 initialization requires its exact profile and 24-MiB limit"
            )
        if self._connection.in_transaction:
            raise PhysicalProjectionV4ConfigurationError(
                "Raw V8 initialization requires transaction quiescence"
            )

        created_at = utc_iso(self._now())
        nonce = secrets.token_bytes(32)
        fingerprint = self._projection_schema_fingerprint_bytes_v4()
        ledger_id = self._derive_projection_ledger_id_v4(
            nonce=nonce,
            created_at=created_at,
            schema_fingerprint=fingerprint,
        )
        try:
            self._fault("raw_v8_initialize_before_schema_script")
            self._assert_projection_provisioning_lease_v4()
            # ``executescript`` commits a transaction that was opened before
            # the call.  Starting BEGIN inside this static script instead keeps
            # every DDL statement and the following parameterized metadata
            # insert in one transaction.
            self._connection.executescript("BEGIN IMMEDIATE;\n" + profile.schema_sql)
            if not self._connection.in_transaction:
                raise PhysicalProjectionV4ConfigurationError(
                    "Raw V8 schema script did not retain its write transaction"
                )
            self._fault("raw_v8_initialize_after_schema_script")
            self._connection.execute(
                """
                INSERT INTO projection_meta(
                    singleton, ledger_id, ledger_nonce, schema_version,
                    validation_version, canonicalization_version,
                    physical_evidence_schema_version, schema_fingerprint,
                    created_at, max_object_bytes
                ) VALUES(1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ledger_id,
                    nonce,
                    profile.schema_version,
                    profile.validation_version,
                    profile.canonicalization_version,
                    profile.physical_evidence_schema_version,
                    fingerprint,
                    created_at,
                    max_object_bytes,
                ),
            )
            if not self._connection.in_transaction:
                raise PhysicalProjectionV4ConfigurationError(
                    "Raw V8 metadata insert escaped its schema transaction"
                )
            self._fault("raw_v8_initialize_after_metadata_insert")
            self._fault("raw_v8_initialize_before_commit")
            self._assert_projection_provisioning_lease_v4()
            try:
                self._connection.commit()
            except BaseException as commit_error:
                if self._raw_v8_connection_transaction_state_v49f() is True:
                    try:
                        self._connection.rollback()
                    except sqlite3.Error as rollback_error:
                        raise PhysicalProjectionV4ConfigurationError(
                            "Raw V8 initialization commit and rollback both failed"
                        ) from rollback_error
                    raise PhysicalProjectionV4ConfigurationError(
                        "Raw V8 initialization commit failed and was rolled back"
                    ) from commit_error
                try:
                    self._resolve_raw_v8_initialization_commit_v49f(
                        reopen_connection=True
                    )
                except BaseException as replay_error:
                    raise commit_error from replay_error
                return
            acknowledgement_error: BaseException | None = None
            try:
                if self._connection.in_transaction:
                    raise PhysicalProjectionV4ConfigurationError(
                        "Raw V8 initialization commit left a transaction active"
                    )
                self._fault("raw_v8_initialize_after_commit")
            except BaseException as exc:
                acknowledgement_error = exc
            try:
                self._resolve_raw_v8_initialization_commit_v49f(reopen_connection=True)
            except BaseException as replay_error:
                if acknowledgement_error is not None:
                    raise acknowledgement_error from replay_error
                raise
        except BaseException:
            if self._raw_v8_connection_transaction_state_v49f() is True:
                try:
                    self._connection.rollback()
                except sqlite3.Error:
                    pass
            raise

    def _raw_v8_connection_transaction_state_v49f(self) -> bool | None:
        try:
            return bool(self._connection.in_transaction)
        except sqlite3.Error:
            return None

    def _resolve_raw_v8_initialization_commit_v49f(
        self,
        *,
        reopen_connection: bool,
    ) -> None:
        """Resolve an acknowledgement-uncertain initialization by full replay."""

        self._assert_projection_provisioning_lease_v4()
        if (
            not reopen_connection
            and self._raw_v8_connection_transaction_state_v49f() is not False
        ):
            raise PhysicalProjectionV4ConfigurationError(
                "Raw V8 initialization outcome is unresolved inside a transaction"
            )
        if reopen_connection:
            try:
                self._connection.close()
            except sqlite3.Error:
                pass
            self._connection = sqlite3.connect(
                self.path,
                isolation_level=None,
                timeout=5.0,
            )
            self._configure_connection()
            observed_path = self._main_database_path_from_connection_v49f()
            observed = observed_path.stat()
            if (
                self._database_device_v49f is None
                or self._database_inode_v49f is None
                or (observed.st_dev, observed.st_ino)
                != (self._database_device_v49f, self._database_inode_v49f)
            ):
                raise PhysicalProjectionV4ConfigurationError(
                    "Raw V8 database inode changed during initialization replay"
                )
            self._assert_projection_provisioning_lease_v4()
        self._validate_meta(
            expected_max_object_bytes=PHYSICAL_PROJECTION_V49F_V8_MAX_OBJECT_BYTES
        )
        self.verify()

    def _cleanup_failed_new_projection_v4(self) -> None:
        """Leave uncertain V8 files for the next lease-held classifier."""

    def _verify_schema_profile_extensions_v4(self) -> None:
        if self._projection_schema_profile_v4() is not _RAW_V8_SCHEMA_PROFILE_V49F:
            raise PhysicalProjectionV4VerificationError(
                "Raw V8 verification left its pinned schema profile"
            )

        for table in (*_RAW_V7_LIFECYCLE_TABLES_V49F, *_RAW_V8_TABLES_V49F):
            count = int(
                self._connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            )
            if count:
                raise PhysicalProjectionV4VerificationError(
                    f"empty Raw V8 schema profile contains forbidden rows in {table}"
                )

        placeholders = ",".join("?" for _ in _RAW_V7_RECORD_KINDS_V49F)
        v7_record_count = int(
            self._connection.execute(
                f"""
                SELECT count(*) FROM canonical_records
                WHERE record_kind IN ({placeholders})
                """,
                _RAW_V7_RECORD_KINDS_V49F,
            ).fetchone()[0]
        )
        if v7_record_count:
            raise PhysicalProjectionV4VerificationError(
                "Raw V8 projection contains forbidden Raw V7 lifecycle records"
            )

        placeholders = ",".join("?" for _ in _RAW_V8_RECORD_KINDS_V49F)
        v8_record_count = int(
            self._connection.execute(
                f"""
                SELECT count(*) FROM canonical_records
                WHERE record_kind IN ({placeholders})
                """,
                _RAW_V8_RECORD_KINDS_V49F,
            ).fetchone()[0]
        )
        if v8_record_count:
            raise PhysicalProjectionV4VerificationError(
                "empty Raw V8 schema profile cannot contain V8 lifecycle records"
            )

        placeholders = ",".join("?" for _ in _RAW_V7_BATCH_OPERATIONS_V49F)
        v7_batch_count = int(
            self._connection.execute(
                f"""
                SELECT count(*) FROM operation_batches
                WHERE operation IN ({placeholders})
                """,
                _RAW_V7_BATCH_OPERATIONS_V49F,
            ).fetchone()[0]
        )
        if v7_batch_count:
            raise PhysicalProjectionV4VerificationError(
                "Raw V8 projection contains forbidden Raw V7 lifecycle batches"
            )


__all__ = [
    "PHYSICAL_PROJECTION_V49F_V8_MAX_OBJECT_BYTES",
    "PHYSICAL_PROJECTION_V49F_V8_SCHEMA_FINGERPRINT_DOMAIN",
    "PHYSICAL_PROJECTION_V49F_V8_SCHEMA_VERSION",
    "PHYSICAL_PROJECTION_V49F_V8_VALIDATION_VERSION",
    "PhysicalProjectionStoreV49FV8",
]

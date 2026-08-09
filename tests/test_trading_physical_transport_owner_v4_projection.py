from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import timedelta
from pathlib import Path

import pytest

from riskyieldmm.trading.ledger_signing import Ed25519CheckpointSigner
from riskyieldmm.trading.physical_projection_v4 import (
    PhysicalProjectionStoreV4,
    PhysicalProjectionV4ConflictError,
    PhysicalProjectionV4IdempotencyError,
    PhysicalProjectionV4VerificationError,
    PhysicalRecordKindV4,
)
from tests.test_trading_physical_authority_v4_projection import (
    authority_scope,
    receipt_count,
)
from tests.test_trading_physical_market_data_v3 import (
    T0,
    bar_policy,
    digest,
    status_policy,
)
from tests.test_trading_physical_transport_control_v4_projection import (
    ControlAuthority,
    _heartbeat_intent,
    _raw_ingress,
)
from tests.test_trading_physical_transport_v4_projection import (
    FixedClock,
    TransportFixture,
    append_test_operational_deployment,
    signed_session,
    signed_test_socket_owner_binding,
    transport_policy,
)


class InjectedOwnerProjectionFailure(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class UncommittedOwnerFixture:
    fixture: TransportFixture

    @property
    def authority(self) -> ControlAuthority:
        return ControlAuthority(
            fixture=self.fixture,
            socket_lease_id=self.fixture.socket_owner_binding.socket_lease_id,
            writer_fence_token_sha256=self.fixture.writer_fence_token_sha256,
            writer_fence_generation=self.fixture.writer_fence_generation,
        )


def _prepare_uncommitted_owner_fixture(
    store: PhysicalProjectionStoreV4,
    *,
    clock: FixedClock,
    label: str,
) -> UncommittedOwnerFixture:
    primary = bar_policy(requires_status=True)
    required_status = status_policy()
    scope = authority_scope(primary, required_status)
    signer = Ed25519CheckpointSigner.generate()
    clock.value = scope.frozen_at
    _, deployment_capability = append_test_operational_deployment(
        store,
        signer=signer,
        verified_at=scope.frozen_at,
        valid_until=T0 + timedelta(days=1),
        idempotency_prefix=f"{label}-deployment",
    )
    policy = transport_policy(
        signer=signer,
        frozen_at=scope.frozen_at,
        deployment_capability=deployment_capability,
    )
    store.append_health_policy(idempotency_key=f"{label}-health-policy")
    store.append_adapter_policy(primary, idempotency_key=f"{label}-primary-policy")
    store.append_adapter_policy(
        required_status,
        idempotency_key=f"{label}-status-policy",
    )
    store.append_scope(scope, idempotency_key=f"{label}-scope")
    store.append_transport_subscription_policy(
        policy,
        idempotency_key=f"{label}-transport-policy",
    )
    session = signed_session(
        fixture_policy=policy,
        scope=scope,
        primary=primary,
        signer=signer,
        deployment_capability=deployment_capability,
        session_nonce_label=f"{label}-session",
    )
    writer_fence_token_sha256 = digest(f"{label}-writer-fence")
    writer_fence_generation = store.claim_transport_runtime_writer_fence(
        lease_token_sha256=writer_fence_token_sha256,
        holder_id=f"{label}-writer",
    )
    binding = signed_test_socket_owner_binding(
        session=session,
        signer=signer,
        writer_fence_token_sha256=writer_fence_token_sha256,
        writer_fence_generation=writer_fence_generation,
        label=label,
    )
    return UncommittedOwnerFixture(
        fixture=TransportFixture(
            primary=primary,
            required_status=required_status,
            scope=scope,
            signer=signer,
            deployment_capability=deployment_capability,
            policy=policy,
            session=session,
            socket_owner_binding=binding,
            writer_fence_token_sha256=writer_fence_token_sha256,
            writer_fence_generation=writer_fence_generation,
            intent=None,
        )
    )


def _append_bound_fixture(
    store: PhysicalProjectionStoreV4,
    *,
    fixture: TransportFixture,
    idempotency_key: str,
) -> object:
    return store.append_transport_session_attestation(
        fixture.session,
        socket_owner_binding=fixture.socket_owner_binding,
        idempotency_key=idempotency_key,
    )


def test_bound_session_commit_is_atomic_ordered_and_idempotent(
    tmp_path: Path,
) -> None:
    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(
        tmp_path / "owner-happy.sqlite3",
        clock=clock,
    ) as store:
        prepared = _prepare_uncommitted_owner_fixture(
            store,
            clock=clock,
            label="owner-happy",
        )
        fixture = prepared.fixture
        before_receipts = receipt_count(store)
        clock.value = T0 - timedelta(milliseconds=500)

        committed = _append_bound_fixture(
            store,
            fixture=fixture,
            idempotency_key="bound-session",
        )

        assert committed.session == fixture.session
        assert committed.binding == fixture.socket_owner_binding
        rows = store._connection.execute(  # noqa: SLF001
            """
            SELECT global_sequence, record_kind, identity_id, committed_at
            FROM receipts WHERE global_sequence > ? ORDER BY global_sequence
            """,
            (before_receipts,),
        ).fetchall()
        assert [int(row[0]) for row in rows] == [
            before_receipts + 1,
            before_receipts + 2,
        ]
        assert [str(row[1]) for row in rows] == [
            PhysicalRecordKindV4.TRANSPORT_SESSION_ATTESTATION.value,
            PhysicalRecordKindV4.TRANSPORT_SOCKET_OWNER_BINDING.value,
        ]
        assert [bytes(row[2]).hex() for row in rows] == [
            fixture.session.transport_session_id,
            fixture.socket_owner_binding.transport_socket_owner_binding_id,
        ]
        assert rows[0][3] == rows[1][3]
        assert store._connection.execute(  # noqa: SLF001
            """
            SELECT operation, first_receipt_sequence, last_receipt_sequence
            FROM operation_batches WHERE idempotency_key = ?
            """,
            ("bound-session",),
        ).fetchone() == (
            "APPEND_BOUND_TRANSPORT_SESSION_V4_7",
            before_receipts + 1,
            before_receipts + 2,
        )

        before_replay = receipt_count(store)
        replayed = _append_bound_fixture(
            store,
            fixture=fixture,
            idempotency_key="bound-session",
        )
        assert replayed == committed
        assert receipt_count(store) == before_replay

        alternate_binding = signed_test_socket_owner_binding(
            session=fixture.session,
            signer=fixture.signer,
            writer_fence_token_sha256=fixture.writer_fence_token_sha256,
            writer_fence_generation=fixture.writer_fence_generation,
            label="owner-happy-alternate",
        )
        with pytest.raises(
            PhysicalProjectionV4IdempotencyError,
            match="another request",
        ):
            store.append_transport_session_attestation(
                fixture.session,
                socket_owner_binding=alternate_binding,
                idempotency_key="bound-session",
            )

        report = store.verify()
        assert report.transport_session_attestation_count == 1
        assert report.transport_socket_owner_binding_count == 1
        assert receipt_count(store) == before_replay


@pytest.mark.parametrize(
    ("fault_stage", "matching_occurrence"),
    (
        ("after_canonical_record_insert", 1),
        ("after_canonical_record_insert", 2),
        ("after_receipt_insert", 1),
        ("after_receipt_insert", 2),
        ("after_transport_session_attestation_insert", 1),
        ("after_transport_socket_owner_binding_insert", 1),
        ("after_operation_batch_insert", 1),
        ("before_commit", 1),
    ),
)
def test_every_bound_session_fault_boundary_rolls_back_both_records(
    tmp_path: Path,
    fault_stage: str,
    matching_occurrence: int,
) -> None:
    armed = False
    occurrences = 0

    def fail_target(stage: str) -> None:
        nonlocal occurrences
        if armed and stage == fault_stage:
            occurrences += 1
            if occurrences == matching_occurrence:
                raise InjectedOwnerProjectionFailure(f"{stage}:{matching_occurrence}")

    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(
        tmp_path / f"owner-rollback-{fault_stage}-{matching_occurrence}.sqlite3",
        clock=clock,
        fault_injector=fail_target,
    ) as store:
        prepared = _prepare_uncommitted_owner_fixture(
            store,
            clock=clock,
            label=f"rollback-{fault_stage}-{matching_occurrence}",
        )
        fixture = prepared.fixture
        before = store.verify()
        before_receipts = receipt_count(store)
        clock.value = T0 - timedelta(milliseconds=500)
        armed = True

        with pytest.raises(
            InjectedOwnerProjectionFailure,
            match=f"{fault_stage}:{matching_occurrence}",
        ):
            _append_bound_fixture(
                store,
                fixture=fixture,
                idempotency_key="faulted-bound-session",
            )
        armed = False

        report = store.verify()
        assert receipt_count(store) == before_receipts
        assert report.receipt_count == before.receipt_count
        assert report.canonical_record_count == before.canonical_record_count
        assert report.transport_session_attestation_count == 0
        assert report.transport_socket_owner_binding_count == 0
        assert store._connection.execute(  # noqa: SLF001
            """
            SELECT count(*) FROM canonical_records
            WHERE identity_id IN (?, ?)
            """,
            (
                bytes.fromhex(fixture.session.transport_session_id),
                bytes.fromhex(
                    fixture.socket_owner_binding.transport_socket_owner_binding_id
                ),
            ),
        ).fetchone() == (0,)
        assert store._connection.execute(  # noqa: SLF001
            """
            SELECT count(*) FROM operation_batches WHERE idempotency_key = ?
            """,
            ("faulted-bound-session",),
        ).fetchone() == (0,)


def test_owner_and_kernel_socket_identity_cannot_be_reused(
    tmp_path: Path,
) -> None:
    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(
        tmp_path / "owner-reuse.sqlite3",
        clock=clock,
    ) as store:
        prepared = _prepare_uncommitted_owner_fixture(
            store,
            clock=clock,
            label="consumed-owner",
        )
        fixture = prepared.fixture
        clock.value = T0 - timedelta(milliseconds=500)
        _append_bound_fixture(
            store,
            fixture=fixture,
            idempotency_key="first-bound-session",
        )

        with pytest.raises(
            PhysicalProjectionV4ConflictError,
            match="socket owner or lease identity was already consumed",
        ):
            _append_bound_fixture(
                store,
                fixture=fixture,
                idempotency_key="same-owner-new-batch",
            )

        second_session = signed_session(
            fixture_policy=fixture.policy,
            scope=fixture.scope,
            primary=fixture.primary,
            signer=fixture.signer,
            deployment_capability=fixture.deployment_capability,
            session_nonce_label="second-session-same-kernel-owner",
            collector_instance_id="collector-b",
            collector_boot_id=fixture.session.collector_boot_id,
        )
        second_binding = signed_test_socket_owner_binding(
            session=second_session,
            signer=fixture.signer,
            writer_fence_token_sha256=fixture.writer_fence_token_sha256,
            writer_fence_generation=fixture.writer_fence_generation,
            label="consumed-owner",
        )
        assert second_binding.socket_lease_id != (
            fixture.socket_owner_binding.socket_lease_id
        )
        assert second_binding.kernel_socket_identity == (
            fixture.socket_owner_binding.kernel_socket_identity
        )

        with pytest.raises(
            PhysicalProjectionV4ConflictError,
            match="socket owner or lease identity was already consumed",
        ):
            store.append_transport_session_attestation(
                second_session,
                socket_owner_binding=second_binding,
                idempotency_key="second-session-reused-kernel-owner",
            )

        report = store.verify()
        assert report.transport_session_attestation_count == 1
        assert report.transport_socket_owner_binding_count == 1


@pytest.mark.parametrize(
    "tamper",
    ("delete_typed_owner", "corrupt_typed_owner", "reorder_bound_receipt_types"),
)
def test_owner_deletion_corruption_and_reordering_are_detected(
    tmp_path: Path,
    tamper: str,
) -> None:
    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(
        tmp_path / f"owner-tamper-{tamper}.sqlite3",
        clock=clock,
    ) as store:
        prepared = _prepare_uncommitted_owner_fixture(
            store,
            clock=clock,
            label=f"tamper-{tamper}",
        )
        fixture = prepared.fixture
        clock.value = T0 - timedelta(milliseconds=500)
        _append_bound_fixture(
            store,
            fixture=fixture,
            idempotency_key="bound-session",
        )
        store.verify()

        owner_id = bytes.fromhex(
            fixture.socket_owner_binding.transport_socket_owner_binding_id
        )
        if tamper == "delete_typed_owner":
            store._connection.execute(  # noqa: SLF001
                "DROP TRIGGER transport_control_socket_bindings_no_delete"
            )
            store._connection.execute(  # noqa: SLF001
                """
                DELETE FROM transport_control_socket_bindings
                WHERE transport_socket_owner_binding_id = ?
                """,
                (owner_id,),
            )
            store._connection.execute(  # noqa: SLF001
                "CREATE TRIGGER transport_control_socket_bindings_no_delete "
                "BEFORE DELETE ON transport_control_socket_bindings "
                "BEGIN SELECT RAISE(ABORT, "
                "'transport_control_socket_bindings is immutable'); END;"
            )
        elif tamper == "corrupt_typed_owner":
            store._connection.execute(  # noqa: SLF001
                "DROP TRIGGER transport_control_socket_bindings_no_update"
            )
            store._connection.execute(  # noqa: SLF001
                """
                UPDATE transport_control_socket_bindings
                SET clock_resolution_ns = clock_resolution_ns + 1
                WHERE transport_socket_owner_binding_id = ?
                """,
                (owner_id,),
            )
            store._connection.execute(  # noqa: SLF001
                "CREATE TRIGGER transport_control_socket_bindings_no_update "
                "BEFORE UPDATE ON transport_control_socket_bindings "
                "BEGIN SELECT RAISE(ABORT, "
                "'transport_control_socket_bindings is immutable'); END;"
            )
        else:
            session_sequence = store._connection.execute(  # noqa: SLF001
                """
                SELECT first_receipt_sequence FROM canonical_records
                WHERE identity_id = ?
                """,
                (bytes.fromhex(fixture.session.transport_session_id),),
            ).fetchone()[0]
            owner_sequence = store._connection.execute(  # noqa: SLF001
                """
                SELECT first_receipt_sequence FROM canonical_records
                WHERE identity_id = ?
                """,
                (owner_id,),
            ).fetchone()[0]
            store._connection.execute(  # noqa: SLF001
                "DROP TRIGGER receipts_no_update"
            )
            store._connection.execute(  # noqa: SLF001
                """
                UPDATE receipts SET record_kind = CASE global_sequence
                    WHEN ? THEN ?
                    WHEN ? THEN ?
                    ELSE record_kind END
                WHERE global_sequence IN (?, ?)
                """,
                (
                    session_sequence,
                    PhysicalRecordKindV4.TRANSPORT_SOCKET_OWNER_BINDING.value,
                    owner_sequence,
                    PhysicalRecordKindV4.TRANSPORT_SESSION_ATTESTATION.value,
                    session_sequence,
                    owner_sequence,
                ),
            )
            store._connection.execute(  # noqa: SLF001
                "CREATE TRIGGER receipts_no_update BEFORE UPDATE ON receipts "
                "BEGIN SELECT RAISE(ABORT, 'receipts is immutable'); END;"
            )
        store._connection.commit()  # noqa: SLF001
        store._verify_schema()  # noqa: SLF001 -- prove schema itself is intact

        with pytest.raises(PhysicalProjectionV4VerificationError):
            store.verify()


def test_session_only_raw_and_heartbeat_paths_cannot_create_or_change_owner(
    tmp_path: Path,
) -> None:
    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(
        tmp_path / "owner-no-lazy-binding.sqlite3",
        clock=clock,
    ) as store:
        prepared = _prepare_uncommitted_owner_fixture(
            store,
            clock=clock,
            label="no-lazy-owner",
        )
        fixture = prepared.fixture
        authority = prepared.authority

        with pytest.raises(TypeError, match="socket_owner_binding"):
            store.append_transport_session_attestation(  # type: ignore[call-arg]
                fixture.session,
                idempotency_key="session-only-bypass",
            )
        assert store._connection.execute(  # noqa: SLF001
            "SELECT count(*) FROM transport_session_attestations"
        ).fetchone() == (0,)
        assert store._connection.execute(  # noqa: SLF001
            "SELECT count(*) FROM transport_control_socket_bindings"
        ).fetchone() == (0,)

        raw = _raw_ingress(authority)
        heartbeat = _heartbeat_intent(authority)
        clock.value = T0 + timedelta(milliseconds=10)
        with pytest.raises(PhysicalProjectionV4ConflictError, match="missing"):
            store.append_raw_ingress_commit(
                raw,
                idempotency_key="raw-before-owner",
            )
        with pytest.raises(PhysicalProjectionV4ConflictError, match="missing"):
            store.append_outbound_control_intent(
                heartbeat,
                idempotency_key="heartbeat-before-owner",
            )
        assert store._connection.execute(  # noqa: SLF001
            "SELECT count(*) FROM transport_control_socket_bindings"
        ).fetchone() == (0,)

        _append_bound_fixture(
            store,
            fixture=fixture,
            idempotency_key="eager-bound-session",
        )
        owner_before = store._connection.execute(  # noqa: SLF001
            "SELECT * FROM transport_control_socket_bindings"
        ).fetchone()
        assert owner_before is not None

        assert (
            store.append_raw_ingress_commit(
                raw,
                idempotency_key="raw-after-owner",
            )
            == raw
        )
        assert (
            store.append_outbound_control_intent(
                heartbeat,
                idempotency_key="heartbeat-after-owner",
            )
            == heartbeat
        )

        alternate_lease = digest("alternate-lazy-owner")
        second_raw = _raw_ingress(
            authority,
            ingress_sequence=2,
            received_offset_ms=1,
            received_monotonic_ns=301_000_000,
        )
        with pytest.raises(PhysicalProjectionV4ConflictError):
            store.append_raw_ingress_commit(
                replace(second_raw, socket_lease_id=alternate_lease),
                idempotency_key="raw-owner-mutation",
            )
        second_heartbeat = _heartbeat_intent(
            authority,
            control_sequence=2,
            previous_intent_id=heartbeat.outbound_control_intent_id,
            authorized_offset_ms=1,
            authorized_monotonic_ns=301_000_000,
            label="second",
        )
        with pytest.raises(PhysicalProjectionV4ConflictError):
            store.append_outbound_control_intent(
                replace(second_heartbeat, socket_lease_id=alternate_lease),
                idempotency_key="heartbeat-owner-mutation",
            )

        owner_after = store._connection.execute(  # noqa: SLF001
            "SELECT * FROM transport_control_socket_bindings"
        ).fetchone()
        assert owner_after == owner_before
        report = store.verify()
        assert report.transport_socket_owner_binding_count == 1
        assert report.raw_ingress_commit_count == 1
        assert report.outbound_control_intent_count == 1

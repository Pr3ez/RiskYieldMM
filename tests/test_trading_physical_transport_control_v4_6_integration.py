from __future__ import annotations

import asyncio
import base64
import hashlib
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from riskyieldmm.trading.physical_projection_v4 import (
    PhysicalProjectionStoreV4,
    PhysicalProjectionV4ConflictError,
    PhysicalRecordKindV4,
)
from riskyieldmm.trading.physical_transport_control_runtime_v4 import (
    PhysicalTransportControlMediatorV4,
    PhysicalTransportControlRuntimeStateV4,
    PhysicalTransportControlRuntimeV4FaultLatched,
)
from riskyieldmm.trading.physical_transport_control_v4 import (
    OutboundControlDispatchDispositionV4,
    OutboundControlWirePreparedV4,
    OutboundControlWritePermitConsumedV4,
)
from riskyieldmm.trading.physical_transport_v4 import (
    TransportSessionTerminationReasonV4,
)
from tests.test_trading_physical_authority_v4_projection import FixedClock
from tests.test_trading_physical_market_data_v3 import T0
from tests.test_trading_physical_transport_control_v4_projection import (
    ControlAuthority,
    _control_authority,
    _heartbeat_intent,
    _wire,
    _wire_batch_hash,
)
from tests.test_trading_physical_transport_v4_projection import (
    append_test_bound_session,
    prepare_transport_fixture,
    signed_session,
)


@dataclass
class CoupledControlClock:
    """Advance the mediator clocks and the projection clock together."""

    projection_clock: FixedClock
    wall: datetime
    monotonic_ns: int

    def __call__(self) -> tuple[datetime, int]:
        self.wall += timedelta(milliseconds=1)
        self.monotonic_ns += 1_000_000
        self.projection_clock.value = self.wall
        return self.wall, self.monotonic_ns


class ExactDurablePermitWriter:
    """Fake only the reviewed exact-chunk TLS submission boundary."""

    def __init__(
        self,
        *,
        store: PhysicalProjectionStoreV4,
        transport_session_id: str,
        expected_output: bytes,
        raise_after_call: bool = False,
    ) -> None:
        self._store = store
        self._transport_session_id = transport_session_id
        self._expected_output = expected_output
        self._raise_after_call = raise_after_call
        self.calls = 0
        self.permit_seen: OutboundControlWritePermitConsumedV4 | None = None

    async def submit_permitted_chunks(
        self,
        *,
        permit: OutboundControlWritePermitConsumedV4,
        ordered_chunks: tuple[bytes, ...],
    ) -> int:
        self.calls += 1
        assert self.calls == 1
        assert ordered_chunks == (self._expected_output,)

        # The real store must already expose a durable permit crash prefix at
        # the precise point where the external writer is first invoked.
        orphans = self._store.classify_outbound_control_orphans(
            self._transport_session_id
        )
        assert orphans.prepared_without_permit_ids == ()
        assert orphans.permit_without_result_ids == (permit.permit_id,)
        self.permit_seen = permit

        if self._raise_after_call:
            raise OSError("injected uncertain TLS submission")
        return len(self._expected_output)


class InjectedDispatchResultPersistenceFailure(RuntimeError):
    pass


@dataclass
class DispatchResultFaultInjector:
    armed: bool = False

    def __call__(self, stage: str) -> None:
        if self.armed and stage == "after_outbound_control_dispatch_result_insert":
            raise InjectedDispatchResultPersistenceFailure(
                "dispatch result failed before commit"
            )


def _single_output_wire(authority: ControlAuthority) -> OutboundControlWirePreparedV4:
    intent = _heartbeat_intent(authority)
    split_wire = _wire(intent)
    exact_output = b"".join(
        base64.b64decode(chunk, validate=True)
        for chunk in split_wire.wire_chunks_base64
    )
    encoded_output = base64.b64encode(exact_output).decode("ascii")
    return replace(
        split_wire,
        wire_chunks_base64=(encoded_output,),
        wire_chunks_sha256=(hashlib.sha256(exact_output).hexdigest(),),
        wire_batch_sha256=_wire_batch_hash((encoded_output,)),
    )


def _append_fresh_heartbeat_wire(
    store: PhysicalProjectionStoreV4,
    projection_clock: FixedClock,
) -> tuple[ControlAuthority, OutboundControlWirePreparedV4]:
    fixture = prepare_transport_fixture(
        store,
        clock=projection_clock,
        authorize=False,
    )
    authority = _control_authority(store, fixture, label="runtime-integration")
    wire = _single_output_wire(authority)
    intent = _heartbeat_intent(authority)
    assert wire.outbound_control_intent_id == intent.outbound_control_intent_id

    projection_clock.value = intent.authorized_at
    assert (
        store.append_outbound_control_intent(
            intent,
            idempotency_key="runtime-integration-intent",
        )
        == intent
    )
    projection_clock.value = wire.prepared_at
    assert (
        store.append_outbound_control_wire_prepared(
            wire,
            idempotency_key="runtime-integration-wire",
        )
        == wire
    )
    return authority, wire


def _runtime(
    *,
    store: PhysicalProjectionStoreV4,
    authority: ControlAuthority,
    wire: OutboundControlWirePreparedV4,
    projection_clock: FixedClock,
    writer: ExactDurablePermitWriter,
) -> PhysicalTransportControlMediatorV4:
    coupled_clock = CoupledControlClock(
        projection_clock=projection_clock,
        wall=wire.prepared_at,
        monotonic_ns=wire.prepared_monotonic_ns,
    )
    return PhysicalTransportControlMediatorV4.for_test(
        journal=store,
        writer=writer,
        clock=coupled_clock,
        signer=authority.fixture.signer,
        expected_socket_lease_id=authority.socket_lease_id,
        expected_connection_generation=(
            authority.fixture.session.connection_generation
        ),
        assert_writer_authority=lambda: store.assert_transport_runtime_writer_fence(
            lease_token_sha256=authority.writer_fence_token_sha256,
            generation=authority.writer_fence_generation,
        ),
    )


def _dispatch(
    runtime: PhysicalTransportControlMediatorV4,
    authority: ControlAuthority,
    wire: OutboundControlWirePreparedV4,
):
    return asyncio.run(
        runtime.dispatch_prepared(
            wire,
            socket_lease_id=authority.socket_lease_id,
            connection_generation=authority.fixture.session.connection_generation,
            idempotency_prefix="runtime-integration",
        )
    )


def _assert_control_receipt_order(
    store: PhysicalProjectionStoreV4,
    *,
    wire: OutboundControlWirePreparedV4,
    permit: OutboundControlWritePermitConsumedV4,
    result_id: str,
) -> None:
    report = store.verify()
    relevant_kinds = {
        PhysicalRecordKindV4.OUTBOUND_CONTROL_INTENT,
        PhysicalRecordKindV4.OUTBOUND_CONTROL_WIRE_PREPARED,
        PhysicalRecordKindV4.OUTBOUND_CONTROL_WRITE_PERMIT_CONSUMED,
        PhysicalRecordKindV4.OUTBOUND_CONTROL_DISPATCH_RESULT,
    }
    receipts = tuple(
        receipt
        for sequence in range(1, report.receipt_count + 1)
        if (receipt := store.get_receipt(sequence)).record_kind in relevant_kinds
    )
    assert tuple(receipt.record_kind for receipt in receipts) == (
        PhysicalRecordKindV4.OUTBOUND_CONTROL_INTENT,
        PhysicalRecordKindV4.OUTBOUND_CONTROL_WIRE_PREPARED,
        PhysicalRecordKindV4.OUTBOUND_CONTROL_WRITE_PERMIT_CONSUMED,
        PhysicalRecordKindV4.OUTBOUND_CONTROL_DISPATCH_RESULT,
    )
    assert tuple(receipt.identity_id for receipt in receipts) == (
        wire.outbound_control_intent_id,
        wire.outbound_control_wire_prepared_id,
        permit.permit_id,
        result_id,
    )


def test_real_store_mediator_persists_permit_before_exact_successful_write(
    tmp_path: Path,
) -> None:
    path = tmp_path / "runtime-control-success.sqlite3"
    projection_clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(path, clock=projection_clock) as store:
        authority, wire = _append_fresh_heartbeat_wire(store, projection_clock)
        exact_output = base64.b64decode(wire.wire_chunks_base64[0], validate=True)
        writer = ExactDurablePermitWriter(
            store=store,
            transport_session_id=wire.transport_session_id,
            expected_output=exact_output,
        )
        runtime = _runtime(
            store=store,
            authority=authority,
            wire=wire,
            projection_clock=projection_clock,
            writer=writer,
        )

        result = _dispatch(runtime, authority, wire)

        assert writer.calls == 1
        assert writer.permit_seen is not None
        assert result.disposition is OutboundControlDispatchDispositionV4.SENT
        assert result.bytes_submitted_to_tls == wire.wire_octet_length
        assert runtime.state is PhysicalTransportControlRuntimeStateV4.OPEN
        _assert_control_receipt_order(
            store,
            wire=wire,
            permit=writer.permit_seen,
            result_id=result.outbound_control_dispatch_result_id,
        )
        report = store.verify()
        assert report.outbound_control_intent_count == 1
        assert report.outbound_control_wire_prepared_count == 1
        assert report.outbound_control_write_permit_consumed_count == 1
        assert report.outbound_control_dispatch_result_count == 1
        assert not store.classify_outbound_control_orphans(
            wire.transport_session_id
        ).has_active_unresolved_control

    with PhysicalProjectionStoreV4(path, clock=projection_clock) as reopened:
        report = reopened.verify()
        assert report.outbound_control_write_permit_consumed_count == 1
        assert report.outbound_control_dispatch_result_count == 1
        assert not reopened.classify_outbound_control_orphans(
            wire.transport_session_id
        ).has_active_unresolved_control


def test_real_store_round_trips_unknown_result_after_writer_exception(
    tmp_path: Path,
) -> None:
    path = tmp_path / "runtime-control-unknown.sqlite3"
    projection_clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(path, clock=projection_clock) as store:
        authority, wire = _append_fresh_heartbeat_wire(store, projection_clock)
        exact_output = base64.b64decode(wire.wire_chunks_base64[0], validate=True)
        writer = ExactDurablePermitWriter(
            store=store,
            transport_session_id=wire.transport_session_id,
            expected_output=exact_output,
            raise_after_call=True,
        )
        runtime = _runtime(
            store=store,
            authority=authority,
            wire=wire,
            projection_clock=projection_clock,
            writer=writer,
        )

        result = _dispatch(runtime, authority, wire)

        assert writer.calls == 1
        assert writer.permit_seen is not None
        assert result.disposition is (
            OutboundControlDispatchDispositionV4.UNKNOWN_DELIVERY
        )
        assert result.bytes_submitted_to_tls is None
        assert result.error_class_digest is not None
        assert runtime.state is PhysicalTransportControlRuntimeStateV4.FAULT_LATCHED
        _assert_control_receipt_order(
            store,
            wire=wire,
            permit=writer.permit_seen,
            result_id=result.outbound_control_dispatch_result_id,
        )
        assert not store.classify_outbound_control_orphans(
            wire.transport_session_id
        ).has_active_unresolved_control

    with PhysicalProjectionStoreV4(path, clock=projection_clock) as reopened:
        report = reopened.verify()
        assert report.outbound_control_write_permit_consumed_count == 1
        assert report.outbound_control_dispatch_result_count == 1
        row = reopened._connection.execute(  # noqa: SLF001
            """
            SELECT disposition, bytes_submitted_to_tls, error_class_digest
            FROM outbound_control_dispatch_results
            """
        ).fetchone()
        assert row is not None
        assert row[0] == OutboundControlDispatchDispositionV4.UNKNOWN_DELIVERY.value
        assert row[1] is None
        assert bytes(row[2]).hex() == result.error_class_digest
        assert not reopened.classify_outbound_control_orphans(
            wire.transport_session_id
        ).has_active_unresolved_control


def test_restart_never_reuses_permit_after_result_persistence_failure(
    tmp_path: Path,
) -> None:
    path = tmp_path / "runtime-control-result-persistence-failure.sqlite3"
    projection_clock = FixedClock(T0 - timedelta(hours=1))
    fault = DispatchResultFaultInjector()
    with PhysicalProjectionStoreV4(
        path,
        clock=projection_clock,
        fault_injector=fault,
    ) as store:
        authority, wire = _append_fresh_heartbeat_wire(store, projection_clock)
        exact_output = base64.b64decode(wire.wire_chunks_base64[0], validate=True)
        writer = ExactDurablePermitWriter(
            store=store,
            transport_session_id=wire.transport_session_id,
            expected_output=exact_output,
        )
        runtime = _runtime(
            store=store,
            authority=authority,
            wire=wire,
            projection_clock=projection_clock,
            writer=writer,
        )
        fault.armed = True

        with pytest.raises(PhysicalTransportControlRuntimeV4FaultLatched):
            _dispatch(runtime, authority, wire)

        assert writer.calls == 1
        assert writer.permit_seen is not None
        assert runtime.state is PhysicalTransportControlRuntimeStateV4.FAULT_LATCHED
        report = store.verify()
        assert report.outbound_control_write_permit_consumed_count == 1
        assert report.outbound_control_dispatch_result_count == 0
        old_orphans = store.classify_outbound_control_orphans(wire.transport_session_id)
        assert old_orphans.prepared_without_permit_ids == ()
        assert old_orphans.permit_without_result_ids == (writer.permit_seen.permit_id,)
        assert old_orphans.has_active_unresolved_control

    # Reopening inspects durable evidence only. It does not construct a
    # mediator, invoke a recovery writer, or synthesize the missing result.
    with PhysicalProjectionStoreV4(path, clock=projection_clock) as reopened:
        restart_writer_token = hashlib.sha256(
            b"runtime-integration-restart-writer"
        ).hexdigest()
        generation = reopened.claim_transport_runtime_writer_fence(
            lease_token_sha256=restart_writer_token,
            holder_id="runtime-integration-writer",
        )
        assert generation == authority.writer_fence_generation + 1
        assert writer.calls == 1
        assert writer.permit_seen is not None

        permit = writer.permit_seen
        permit_key = (
            "runtime-integration:control-permit:"
            f"{wire.outbound_control_wire_prepared_id}"
        )
        for idempotency_key in (permit_key, "restart-must-not-reauthorize"):
            with pytest.raises(
                PhysicalProjectionV4ConflictError,
                match="write permit is already consumed",
            ):
                reopened.consume_outbound_control_write_permit(
                    wire.outbound_control_wire_prepared_id,
                    permit_consumed_at=permit.permit_consumed_at,
                    permit_consumed_monotonic_ns=(permit.permit_consumed_monotonic_ns),
                    idempotency_key=idempotency_key,
                )
        assert writer.calls == 1

        detected_at = T0 + timedelta(milliseconds=10)
        projection_clock.value = detected_at + timedelta(milliseconds=1)
        reopened.append_transport_session_termination(
            transport_session_id=wire.transport_session_id,
            reason=TransportSessionTerminationReasonV4.PROCESS_RESTART,
            detected_at=detected_at,
            detected_monotonic_ns=310_000_000,
            detected_monotonic_clock_domain_id=(
                authority.fixture.session.monotonic_clock_domain_id
            ),
            signer=authority.fixture.signer,
            idempotency_key="runtime-integration-old-session-terminal",
        )
        successor = signed_session(
            fixture_policy=authority.fixture.policy,
            scope=authority.fixture.scope,
            primary=authority.fixture.primary,
            signer=authority.fixture.signer,
            deployment_capability=authority.fixture.deployment_capability,
            session_nonce_label="runtime-integration-successor",
            connection_generation=2,
            parent_transport_session_id=wire.transport_session_id,
            handshake_started_at=T0 + timedelta(milliseconds=20),
            handshake_completed_at=T0 + timedelta(milliseconds=30),
            handshake_started_monotonic_ns=320_000_000,
            handshake_completed_monotonic_ns=330_000_000,
        )
        projection_clock.value = T0 + timedelta(milliseconds=40)
        successor_commit = append_test_bound_session(
            reopened,
            session=successor,
            signer=authority.fixture.signer,
            writer_fence_token_sha256=restart_writer_token,
            writer_fence_generation=generation,
            idempotency_key="runtime-integration-successor-session",
            label="runtime-integration-successor",
        )

        old_classification = reopened.classify_outbound_control_orphans(
            wire.transport_session_id
        )
        assert old_classification.session_is_terminal
        assert old_classification.permit_without_result_ids == (permit.permit_id,)
        successor_classification = reopened.classify_outbound_control_orphans(
            successor.transport_session_id
        )
        assert successor_classification.connection_generation == 2
        assert successor_classification.socket_lease_id == (
            successor_commit.binding.socket_lease_id
        )
        assert successor_classification.prepared_without_permit_ids == ()
        assert successor_classification.permit_without_result_ids == ()
        assert not successor_classification.has_active_unresolved_control
        report = reopened.verify()
        assert report.transport_session_attestation_count == 2
        assert report.transport_session_termination_count == 1
        assert report.outbound_control_write_permit_consumed_count == 1
        assert report.outbound_control_dispatch_result_count == 0
        assert writer.calls == 1


def test_prepared_without_permit_remains_evidence_only_after_reopen(
    tmp_path: Path,
) -> None:
    path = tmp_path / "runtime-control-prepared-only.sqlite3"
    projection_clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(path, clock=projection_clock) as store:
        authority, wire = _append_fresh_heartbeat_wire(store, projection_clock)
        exact_output = base64.b64decode(wire.wire_chunks_base64[0], validate=True)
        never_connected_writer = ExactDurablePermitWriter(
            store=store,
            transport_session_id=wire.transport_session_id,
            expected_output=exact_output,
        )
        classification = store.classify_outbound_control_orphans(
            wire.transport_session_id
        )
        assert classification.prepared_without_permit_ids == (
            wire.outbound_control_wire_prepared_id,
        )
        assert classification.permit_without_result_ids == ()
        assert classification.has_active_unresolved_control
        assert never_connected_writer.calls == 0
        report = store.verify()
        assert report.outbound_control_wire_prepared_count == 1
        assert report.outbound_control_write_permit_consumed_count == 0
        assert report.outbound_control_dispatch_result_count == 0

    # Store recovery is classification-only for this prefix. There is no
    # implicit call into the deliberately unconnected writer and no permit is
    # fabricated on reopen.
    with PhysicalProjectionStoreV4(path, clock=projection_clock) as reopened:
        classification = reopened.classify_outbound_control_orphans(
            wire.transport_session_id
        )
        assert classification.prepared_without_permit_ids == (
            wire.outbound_control_wire_prepared_id,
        )
        assert classification.permit_without_result_ids == ()
        assert classification.has_active_unresolved_control
        assert never_connected_writer.calls == 0
        report = reopened.verify()
        assert report.outbound_control_wire_prepared_count == 1
        assert report.outbound_control_write_permit_consumed_count == 0
        assert report.outbound_control_dispatch_result_count == 0

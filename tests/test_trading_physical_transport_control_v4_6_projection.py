from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from riskyieldmm.trading.physical_projection_v4 import (
    PhysicalProjectionStoreV4,
    PhysicalProjectionV4ConfigurationError,
    PhysicalProjectionV4ConflictError,
    PhysicalProjectionV4VerificationError,
    PhysicalProjectionV4WriterFenceError,
)
from riskyieldmm.trading.physical_transport_control_v4 import (
    V4_INCORRECT_MASKING_CLOSE_PAYLOAD,
    V4_INCORRECT_MASKING_PARSER_EXCEPTION_CLASS_DIGEST,
    V4_INCORRECT_MASKING_PARSER_EXCEPTION_MESSAGE_DIGEST,
    InboundRfcControlOpcodeV4,
    InboundWebSocketProtocolFailureKindV4,
    InboundWebSocketProtocolFailureV4,
    OutboundControlDispatchDispositionV4,
    OutboundControlDispatchResultV4,
    OutboundControlIntentV4,
    OutboundControlKindV4,
    OutboundWebSocketOpcodeV4,
    RawIngressCommitV4,
)
from riskyieldmm.trading.physical_transport_v4 import (
    TransportSessionTerminationReasonV4,
)
from tests.test_trading_physical_market_data_v3 import T0, digest
from tests.test_trading_physical_transport_control_v4_projection import (
    _client_frame,
    _common,
    _control_authority,
    _heartbeat_intent,
    _ingress_batch_hash,
    _raw_ingress,
    _trigger,
    _wire,
)
from tests.test_trading_physical_transport_v4_projection import (
    FixedClock,
    append_test_bound_session,
    prepare_transport_fixture,
    signed_session,
)


class InjectedV46ProjectionFailure(RuntimeError):
    pass


def _masked_server_raw(authority: object) -> RawIngressCommitV4:
    frame = _client_frame(0x9, b"masked-server-ping")
    chunks = (
        base64.b64encode(frame[:4]).decode("ascii"),
        base64.b64encode(frame[4:]).decode("ascii"),
    )
    return RawIngressCommitV4(
        **_common(authority),  # type: ignore[arg-type]
        ingress_sequence=1,
        raw_ingress_chunks_base64=chunks,
        raw_ingress_chunks_sha256=tuple(
            hashlib.sha256(base64.b64decode(chunk)).hexdigest() for chunk in chunks
        ),
        raw_ingress_batch_sha256=_ingress_batch_hash(chunks),
        received_at=T0,
        monotonic_clock_domain_id=(authority.fixture.session.monotonic_clock_domain_id),  # type: ignore[attr-defined]
        received_monotonic_ns=300_000_000,
    )


def _masked_then_valid_server_raw(
    authority: object,
) -> tuple[RawIngressCommitV4, int, bytes]:
    masked = _client_frame(0x9, b"invalid-first-frame")
    later_payload = b"unreachable-ping"
    later = bytes((0x89, len(later_payload))) + later_payload
    exact = masked + later
    chunks = (
        base64.b64encode(exact[:5]).decode("ascii"),
        base64.b64encode(exact[5:]).decode("ascii"),
    )
    raw = RawIngressCommitV4(
        **_common(authority),  # type: ignore[arg-type]
        ingress_sequence=1,
        raw_ingress_chunks_base64=chunks,
        raw_ingress_chunks_sha256=tuple(
            hashlib.sha256(base64.b64decode(chunk)).hexdigest() for chunk in chunks
        ),
        raw_ingress_batch_sha256=_ingress_batch_hash(chunks),
        received_at=T0,
        monotonic_clock_domain_id=(authority.fixture.session.monotonic_clock_domain_id),  # type: ignore[attr-defined]
        received_monotonic_ns=300_000_000,
    )
    return raw, len(masked), later_payload


def _failure(raw: RawIngressCommitV4) -> InboundWebSocketProtocolFailureV4:
    payload = V4_INCORRECT_MASKING_CLOSE_PAYLOAD
    return InboundWebSocketProtocolFailureV4(
        transport_subscription_policy_id=raw.transport_subscription_policy_id,
        transport_session_id=raw.transport_session_id,
        physical_scope_manifest_id=raw.physical_scope_manifest_id,
        adapter_policy_id=raw.adapter_policy_id,
        capture_partition_id=raw.capture_partition_id,
        socket_lease_id=raw.socket_lease_id,
        connection_generation=raw.connection_generation,
        deployment_bundle_id=raw.deployment_bundle_id,
        writer_fence_token_sha256=raw.writer_fence_token_sha256,
        writer_fence_generation=raw.writer_fence_generation,
        ingress_sequence=raw.ingress_sequence,
        raw_ingress_commit_id=raw.raw_ingress_commit_id,
        raw_ingress_chunks_base64=raw.raw_ingress_chunks_base64,
        raw_ingress_chunks_sha256=raw.raw_ingress_chunks_sha256,
        raw_ingress_batch_sha256=raw.raw_ingress_batch_sha256,
        frame_offset=0,
        protocol_failure_kind=(InboundWebSocketProtocolFailureKindV4.INCORRECT_MASKING),
        parser_exception_class_digest=(
            V4_INCORRECT_MASKING_PARSER_EXCEPTION_CLASS_DIGEST
        ),
        parser_exception_message_digest=(
            V4_INCORRECT_MASKING_PARSER_EXCEPTION_MESSAGE_DIGEST
        ),
        logical_close_payload_base64=base64.b64encode(payload).decode("ascii"),
        logical_close_payload_sha256=hashlib.sha256(payload).hexdigest(),
        detected_at=raw.received_at + timedelta(milliseconds=1),
        monotonic_clock_domain_id=raw.monotonic_clock_domain_id,
        detected_monotonic_ns=raw.received_monotonic_ns + 1_000_000,
        fences_session_authority=True,
    )


def _failure_intent(
    authority: object,
    failure: InboundWebSocketProtocolFailureV4,
) -> OutboundControlIntentV4:
    authorized_at = failure.detected_at + timedelta(milliseconds=1)
    authorized_ns = failure.detected_monotonic_ns + 1_000_000
    return OutboundControlIntentV4(
        **_common(authority),  # type: ignore[arg-type]
        control_sequence=1,
        previous_outbound_control_intent_id=None,
        control_kind=OutboundControlKindV4.RFC_PROTOCOL_FAILURE_CLOSE,
        scheduled_heartbeat_id=None,
        inbound_rfc_control_trigger_id=None,
        inbound_rfc_opcode=None,
        inbound_rfc_payload_base64=None,
        protocol_failure_evidence_id=(failure.inbound_websocket_protocol_failure_id),
        logical_websocket_opcode=OutboundWebSocketOpcodeV4.CLOSE,
        logical_payload_base64=failure.logical_close_payload_base64,
        logical_payload_sha256=failure.logical_close_payload_sha256,
        request_id=None,
        fences_session_authority=True,
        authorized_at=authorized_at,
        monotonic_clock_domain_id=failure.monotonic_clock_domain_id,
        authorized_monotonic_ns=authorized_ns,
        send_not_after=authorized_at + timedelta(seconds=1),
        send_not_after_monotonic_ns=authorized_ns + 1_000_000_000,
    )


def _late_dispatch(
    *,
    fixture: object,
    wire: object,
    permit: object,
    outcome_at: datetime | None = None,
    outcome_monotonic_ns: int | None = None,
) -> OutboundControlDispatchResultV4:
    started_at = permit.permit_consumed_at + timedelta(microseconds=1)  # type: ignore[attr-defined]
    started_ns = permit.permit_consumed_monotonic_ns + 1_000  # type: ignore[attr-defined]
    resolved_outcome_at = (
        fixture.deployment_capability.valid_until + timedelta(seconds=1)  # type: ignore[attr-defined]
        if outcome_at is None
        else outcome_at
    )
    resolved_outcome_ns = (
        started_ns + 1_000 if outcome_monotonic_ns is None else outcome_monotonic_ns
    )
    return OutboundControlDispatchResultV4.create_signed(
        signer=fixture.signer,  # type: ignore[attr-defined]
        outbound_control_intent_id=wire.outbound_control_intent_id,  # type: ignore[attr-defined]
        outbound_control_wire_prepared_id=(wire.outbound_control_wire_prepared_id),  # type: ignore[attr-defined]
        transport_session_id=wire.transport_session_id,  # type: ignore[attr-defined]
        socket_lease_id=wire.socket_lease_id,  # type: ignore[attr-defined]
        connection_generation=wire.connection_generation,  # type: ignore[attr-defined]
        deployment_bundle_id=wire.deployment_bundle_id,  # type: ignore[attr-defined]
        writer_fence_token_sha256=wire.writer_fence_token_sha256,  # type: ignore[attr-defined]
        writer_fence_generation=wire.writer_fence_generation,  # type: ignore[attr-defined]
        control_kind=wire.control_kind,  # type: ignore[attr-defined]
        wire_batch_sha256=wire.wire_batch_sha256,  # type: ignore[attr-defined]
        wire_octet_length=wire.wire_octet_length,  # type: ignore[attr-defined]
        permit_id=permit.permit_id,  # type: ignore[attr-defined]
        permit_consumed=True,
        one_shot_attempt_ordinal=1,
        disposition=OutboundControlDispatchDispositionV4.UNKNOWN_DELIVERY,
        wire_prepared_at=wire.prepared_at,  # type: ignore[attr-defined]
        monotonic_clock_domain_id=wire.monotonic_clock_domain_id,  # type: ignore[attr-defined]
        wire_prepared_monotonic_ns=wire.prepared_monotonic_ns,  # type: ignore[attr-defined]
        dispatch_started_at=started_at,
        dispatch_started_monotonic_ns=started_ns,
        dispatch_outcome_at=resolved_outcome_at,
        dispatch_outcome_monotonic_ns=resolved_outcome_ns,
        send_not_after=wire.send_not_after,  # type: ignore[attr-defined]
        send_not_after_monotonic_ns=wire.send_not_after_monotonic_ns,  # type: ignore[attr-defined]
        bytes_submitted_to_tls=None,
        error_class_digest=digest("v46-unknown-local-submission-count"),
    )


def test_typed_failure_permit_orphans_and_late_result_reopen_cleanly(
    tmp_path: Path,
) -> None:
    path = tmp_path / "v4-6-control-prefix.sqlite3"
    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(path, clock=clock) as store:
        fixture = prepare_transport_fixture(store, clock=clock, authorize=False)
        authority = _control_authority(store, fixture, label="v46-prefix")
        raw = _masked_server_raw(authority)
        failure = _failure(raw)
        intent = _failure_intent(authority, failure)
        wire = _wire(intent)

        clock.value = raw.received_at
        store.append_raw_ingress_commit(raw, idempotency_key="v46-raw")
        clock.value = failure.detected_at
        store.append_inbound_websocket_protocol_failure(
            failure,
            idempotency_key="v46-failure",
        )

        with pytest.raises(PhysicalProjectionV4ConflictError):
            store.append_raw_ingress_commit(
                _raw_ingress(
                    authority,
                    ingress_sequence=2,
                    received_offset_ms=2,
                    received_monotonic_ns=302_000_000,
                ),
                idempotency_key="v46-fenced-raw",
            )
        clock.value = intent.authorized_at
        store.append_outbound_control_intent(intent, idempotency_key="v46-intent")
        clock.value = wire.prepared_at
        store.append_outbound_control_wire_prepared(
            wire,
            idempotency_key="v46-wire",
        )
        prepared_orphan = store.classify_outbound_control_orphans(
            fixture.session.transport_session_id
        )
        assert prepared_orphan.prepared_without_permit_ids == (
            wire.outbound_control_wire_prepared_id,
        )
        assert prepared_orphan.permit_without_result_ids == ()
        assert prepared_orphan.has_active_unresolved_control

        consumed_at = wire.prepared_at + timedelta(microseconds=500)
        consumed_ns = wire.prepared_monotonic_ns + 500_000
        clock.value = consumed_at
        permit = store.consume_outbound_control_write_permit(
            wire.outbound_control_wire_prepared_id,
            permit_consumed_at=consumed_at,
            permit_consumed_monotonic_ns=consumed_ns,
            idempotency_key="v46-permit",
        )
        with pytest.raises(
            PhysicalProjectionV4ConflictError,
            match="replay is evidence only",
        ):
            store.consume_outbound_control_write_permit(
                wire.outbound_control_wire_prepared_id,
                permit_consumed_at=consumed_at,
                permit_consumed_monotonic_ns=consumed_ns,
                idempotency_key="v46-permit",
            )
        with pytest.raises(
            PhysicalProjectionV4ConflictError,
            match="replay is evidence only",
        ):
            store.consume_outbound_control_write_permit(
                wire.outbound_control_wire_prepared_id,
                permit_consumed_at=consumed_at + timedelta(microseconds=1),
                permit_consumed_monotonic_ns=consumed_ns + 1,
                idempotency_key="v46-second-permit",
            )
        orphan = store.classify_outbound_control_orphans(
            fixture.session.transport_session_id
        )
        assert orphan.prepared_without_permit_ids == ()
        assert orphan.permit_without_result_ids == (permit.permit_id,)
        report = store.verify()
        assert report.inbound_websocket_protocol_failure_count == 1
        assert report.outbound_control_write_permit_consumed_count == 1
        assert report.outbound_control_dispatch_result_count == 0
        dispatch = _late_dispatch(fixture=fixture, wire=wire, permit=permit)
        clock.value = dispatch.dispatch_outcome_at
        store.append_outbound_control_dispatch_result(
            dispatch,
            idempotency_key="v46-late-result",
        )
        assert (
            store.classify_outbound_control_orphans(
                fixture.session.transport_session_id
            ).permit_without_result_ids
            == ()
        )
        report = store.verify()
        assert report.outbound_control_dispatch_result_count == 1
        assert dispatch.bytes_submitted_to_tls is None

    with PhysicalProjectionStoreV4(path, clock=clock) as reopened:
        assert (
            reopened.classify_outbound_control_orphans(
                fixture.session.transport_session_id
            ).permit_without_result_ids
            == ()
        )
        assert reopened.verify().outbound_control_dispatch_result_count == 1


def test_external_memory_alias_is_rejected_without_creating_a_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(
        PhysicalProjectionV4ConfigurationError,
        match="requires a durable filesystem path",
    ):
        PhysicalProjectionStoreV4(":memory:")
    assert not (tmp_path / ":memory:").exists()


@pytest.mark.parametrize("outcome_after_terminal", (False, True))
def test_late_result_must_prove_writer_observation_predates_terminal_detection(
    tmp_path: Path,
    outcome_after_terminal: bool,
) -> None:
    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(
        tmp_path / f"v4-6-terminal-result-{outcome_after_terminal}.sqlite3",
        clock=clock,
    ) as store:
        fixture = prepare_transport_fixture(store, clock=clock, authorize=False)
        authority = _control_authority(store, fixture, label="v46-terminal-result")
        intent = _heartbeat_intent(authority, label="v46-terminal-result")
        wire = _wire(intent)
        clock.value = intent.authorized_at
        store.append_outbound_control_intent(
            intent,
            idempotency_key="v46-terminal-result-intent",
        )
        clock.value = wire.prepared_at
        store.append_outbound_control_wire_prepared(
            wire,
            idempotency_key="v46-terminal-result-wire",
        )
        consumed_at = wire.prepared_at + timedelta(microseconds=500)
        consumed_ns = wire.prepared_monotonic_ns + 500_000
        clock.value = consumed_at
        permit = store.consume_outbound_control_write_permit(
            wire.outbound_control_wire_prepared_id,
            permit_consumed_at=consumed_at,
            permit_consumed_monotonic_ns=consumed_ns,
            idempotency_key="v46-terminal-result-permit",
        )

        started_at = consumed_at + timedelta(microseconds=1)
        started_ns = consumed_ns + 1_000
        terminal_at = started_at + timedelta(microseconds=10)
        terminal_ns = started_ns + 10_000
        outcome_delta = 15 if outcome_after_terminal else 5
        outcome_at = started_at + timedelta(microseconds=outcome_delta)
        outcome_ns = started_ns + outcome_delta * 1_000
        dispatch = _late_dispatch(
            fixture=fixture,
            wire=wire,
            permit=permit,
            outcome_at=outcome_at,
            outcome_monotonic_ns=outcome_ns,
        )

        clock.value = terminal_at + timedelta(microseconds=1)
        store.append_transport_session_termination(
            transport_session_id=fixture.session.transport_session_id,
            reason=TransportSessionTerminationReasonV4.LOCAL_CLOSE,
            detected_at=terminal_at,
            detected_monotonic_ns=terminal_ns,
            detected_monotonic_clock_domain_id=(
                fixture.session.monotonic_clock_domain_id
            ),
            signer=fixture.signer,
            idempotency_key="v46-terminal-result-termination",
        )
        clock.value = max(clock.value, outcome_at + timedelta(microseconds=1))

        if outcome_after_terminal:
            with pytest.raises(
                PhysicalProjectionV4ConflictError,
                match="predates terminal session detection",
            ):
                store.append_outbound_control_dispatch_result(
                    dispatch,
                    idempotency_key="v46-terminal-result-dispatch",
                )
            assert store.classify_outbound_control_orphans(
                fixture.session.transport_session_id
            ).permit_without_result_ids == (permit.permit_id,)
            assert store.verify().outbound_control_dispatch_result_count == 0
        else:
            persisted = store.append_outbound_control_dispatch_result(
                dispatch,
                idempotency_key="v46-terminal-result-dispatch",
            )
            assert persisted == dispatch
            assert (
                store.append_outbound_control_dispatch_result(
                    dispatch,
                    idempotency_key="v46-terminal-result-dispatch",
                )
                == dispatch
            )
            assert store.verify().outbound_control_dispatch_result_count == 1


def test_termination_detection_cannot_be_backdated_before_durable_dispatch(
    tmp_path: Path,
) -> None:
    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(
        tmp_path / "v4-6-backdated-termination.sqlite3",
        clock=clock,
    ) as store:
        fixture = prepare_transport_fixture(store, clock=clock, authorize=False)
        authority = _control_authority(store, fixture, label="v46-backdated-terminal")
        intent = _heartbeat_intent(authority, label="v46-backdated-terminal")
        wire = _wire(intent)
        clock.value = intent.authorized_at
        store.append_outbound_control_intent(
            intent,
            idempotency_key="v46-backdated-intent",
        )
        clock.value = wire.prepared_at
        store.append_outbound_control_wire_prepared(
            wire,
            idempotency_key="v46-backdated-wire",
        )
        consumed_at = wire.prepared_at + timedelta(microseconds=500)
        consumed_ns = wire.prepared_monotonic_ns + 500_000
        clock.value = consumed_at
        permit = store.consume_outbound_control_write_permit(
            wire.outbound_control_wire_prepared_id,
            permit_consumed_at=consumed_at,
            permit_consumed_monotonic_ns=consumed_ns,
            idempotency_key="v46-backdated-permit",
        )
        outcome_at = consumed_at + timedelta(microseconds=5)
        outcome_ns = consumed_ns + 5_000
        dispatch = _late_dispatch(
            fixture=fixture,
            wire=wire,
            permit=permit,
            outcome_at=outcome_at,
            outcome_monotonic_ns=outcome_ns,
        )
        clock.value = outcome_at + timedelta(microseconds=1)
        store.append_outbound_control_dispatch_result(
            dispatch,
            idempotency_key="v46-backdated-dispatch",
        )

        clock.value = outcome_at + timedelta(microseconds=3)
        with pytest.raises(
            PhysicalProjectionV4ConflictError,
            match="does not follow the last durable control dispatch",
        ):
            store.append_transport_session_termination(
                transport_session_id=fixture.session.transport_session_id,
                reason=TransportSessionTerminationReasonV4.LOCAL_CLOSE,
                detected_at=outcome_at,
                detected_monotonic_ns=outcome_ns,
                detected_monotonic_clock_domain_id=(
                    fixture.session.monotonic_clock_domain_id
                ),
                signer=fixture.signer,
                idempotency_key="v46-backdated-termination",
            )
        assert store.verify().outbound_control_dispatch_result_count == 1


def test_first_frame_protocol_failure_invalidates_later_trigger_in_same_raw_batch(
    tmp_path: Path,
) -> None:
    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(
        tmp_path / "v4-6-protocol-frame-exclusion.sqlite3",
        clock=clock,
    ) as store:
        fixture = prepare_transport_fixture(store, clock=clock, authorize=False)
        authority = _control_authority(store, fixture, label="v46-frame")
        raw, later_offset, later_payload = _masked_then_valid_server_raw(authority)
        failure = _failure(raw)
        clock.value = raw.received_at
        store.append_raw_ingress_commit(raw, idempotency_key="v46-frame-raw")
        trigger = _trigger(
            raw,
            opcode=InboundRfcControlOpcodeV4.PING,
            payload=later_payload,
            frame_offset=later_offset,
            frame_length=2 + len(later_payload),
        )
        store.append_inbound_rfc_control_trigger(
            trigger,
            idempotency_key="v46-frame-trigger",
        )
        clock.value = failure.detected_at
        with pytest.raises(
            PhysicalProjectionV4ConflictError,
            match="invalidates every later RFC control view",
        ):
            store.append_inbound_websocket_protocol_failure(
                failure,
                idempotency_key="v46-impossible-late-failure",
            )
        assert store.verify().inbound_websocket_protocol_failure_count == 0

        # Corrupt only the canonical stream to ensure full replay independently
        # rejects the impossible trigger-then-first-frame-failure history.
        with store._transaction():
            store._append_record(failure, committed_at=failure.detected_at)
        with pytest.raises(PhysicalProjectionV4VerificationError):
            store.verify()


@pytest.mark.parametrize(
    ("record_kind", "mutation"),
    (
        ("protocol_failure", "delete"),
        ("protocol_failure", "content_hash"),
        ("permit", "delete"),
        ("permit", "content_hash"),
    ),
)
def test_verify_rejects_missing_or_tampered_v4_6_typed_rows(
    tmp_path: Path,
    record_kind: str,
    mutation: str,
) -> None:
    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(
        tmp_path / f"v4-6-bijection-{record_kind}-{mutation}.sqlite3",
        clock=clock,
    ) as store:
        fixture = prepare_transport_fixture(store, clock=clock, authorize=False)
        authority = _control_authority(
            store,
            fixture,
            label=f"v46-bijection-{record_kind}-{mutation}",
        )
        if record_kind == "protocol_failure":
            raw = _masked_server_raw(authority)
            record = _failure(raw)
            clock.value = raw.received_at
            store.append_raw_ingress_commit(
                raw,
                idempotency_key=f"v46-bijection-{mutation}-raw",
            )
            clock.value = record.detected_at
            store.append_inbound_websocket_protocol_failure(
                record,
                idempotency_key=f"v46-bijection-{mutation}-failure",
            )
            table = "inbound_websocket_protocol_failures"
            identity_column = "inbound_websocket_protocol_failure_id"
            identity = record.inbound_websocket_protocol_failure_id
        else:
            intent = _heartbeat_intent(
                authority,
                label=f"bij-{mutation}",
            )
            wire = _wire(intent)
            clock.value = intent.authorized_at
            store.append_outbound_control_intent(
                intent,
                idempotency_key=f"v46-bijection-{mutation}-intent",
            )
            clock.value = wire.prepared_at
            store.append_outbound_control_wire_prepared(
                wire,
                idempotency_key=f"v46-bijection-{mutation}-wire",
            )
            consumed_at = wire.prepared_at + timedelta(microseconds=500)
            clock.value = consumed_at
            record = store.consume_outbound_control_write_permit(
                wire.outbound_control_wire_prepared_id,
                permit_consumed_at=consumed_at,
                permit_consumed_monotonic_ns=(wire.prepared_monotonic_ns + 500_000),
                idempotency_key=f"v46-bijection-{mutation}-permit",
            )
            table = "outbound_control_write_permits_consumed"
            identity_column = "permit_id"
            identity = record.permit_id

        if mutation == "delete":
            store._connection.execute(f"DROP TRIGGER {table}_no_delete")
            store._connection.execute(
                f"DELETE FROM {table} WHERE {identity_column} = ?",
                (bytes.fromhex(identity),),
            )
            store._connection.execute(
                f"CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table} "
                f"BEGIN SELECT RAISE(ABORT, '{table} is immutable'); END;"
            )
        else:
            store._connection.execute(f"DROP TRIGGER {table}_no_update")
            store._connection.execute(
                f"UPDATE {table} SET source_content_hash = ? "
                f"WHERE {identity_column} = ?",
                (
                    bytes.fromhex(digest("v46-tampered-content-hash")),
                    bytes.fromhex(identity),
                ),
            )
            store._connection.execute(
                f"CREATE TRIGGER {table}_no_update BEFORE UPDATE ON {table} "
                f"BEGIN SELECT RAISE(ABORT, '{table} is immutable'); END;"
            )
        with pytest.raises(PhysicalProjectionV4VerificationError):
            store.verify()


def test_replaced_writer_fence_cannot_append_old_permit_result(
    tmp_path: Path,
) -> None:
    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(
        tmp_path / "v4-6-stale-result.sqlite3",
        clock=clock,
    ) as store:
        fixture = prepare_transport_fixture(store, clock=clock, authorize=False)
        authority = _control_authority(store, fixture, label="v46-stale")
        intent = _heartbeat_intent(authority, label="v46-stale")
        wire = _wire(intent)
        clock.value = intent.authorized_at
        store.append_outbound_control_intent(
            intent,
            idempotency_key="v46-stale-intent",
        )
        clock.value = wire.prepared_at
        store.append_outbound_control_wire_prepared(
            wire,
            idempotency_key="v46-stale-wire",
        )
        consumed_at = wire.prepared_at + timedelta(microseconds=500)
        consumed_ns = wire.prepared_monotonic_ns + 500_000
        clock.value = consumed_at
        permit = store.consume_outbound_control_write_permit(
            wire.outbound_control_wire_prepared_id,
            permit_consumed_at=consumed_at,
            permit_consumed_monotonic_ns=consumed_ns,
            idempotency_key="v46-stale-permit",
        )
        successor_writer_token = digest("v46-successor-writer")
        successor_writer_generation = store.claim_transport_runtime_writer_fence(
            lease_token_sha256=successor_writer_token,
            holder_id="v46-successor",
        )
        dispatch = _late_dispatch(fixture=fixture, wire=wire, permit=permit)
        clock.value = permit.permit_consumed_at + timedelta(microseconds=10)
        with pytest.raises(
            PhysicalProjectionV4WriterFenceError,
            match="lost its original writer fence",
        ):
            store.append_outbound_control_dispatch_result(
                dispatch,
                idempotency_key="v46-stale-result",
            )
        orphan = store.classify_outbound_control_orphans(
            fixture.session.transport_session_id
        )
        assert orphan.permit_without_result_ids == (permit.permit_id,)
        assert orphan.has_active_unresolved_control
        restart_domain = fixture.session.monotonic_clock_domain_id
        clock.value = T0 + timedelta(milliseconds=10)
        store.append_transport_session_termination(
            transport_session_id=fixture.session.transport_session_id,
            reason=TransportSessionTerminationReasonV4.PROCESS_RESTART,
            detected_at=T0 + timedelta(milliseconds=9),
            detected_monotonic_ns=350_000_000,
            detected_monotonic_clock_domain_id=restart_domain,
            signer=fixture.signer,
            idempotency_key="v46-stale-restart",
        )
        historical = store.classify_outbound_control_orphans(
            fixture.session.transport_session_id
        )
        assert historical.permit_without_result_ids == (permit.permit_id,)
        assert historical.session_is_terminal
        assert not historical.has_active_unresolved_control

        successor_session = signed_session(
            fixture_policy=fixture.policy,
            scope=fixture.scope,
            primary=fixture.primary,
            signer=fixture.signer,
            deployment_capability=fixture.deployment_capability,
            session_nonce_label="v46-successor-session",
            connection_generation=2,
            parent_transport_session_id=fixture.session.transport_session_id,
            handshake_started_at=T0 + timedelta(milliseconds=11),
            handshake_completed_at=T0 + timedelta(milliseconds=12),
            handshake_started_monotonic_ns=400_000_000,
            handshake_completed_monotonic_ns=500_000_000,
            monotonic_clock_domain_id=restart_domain,
        )
        clock.value = T0 + timedelta(milliseconds=13)
        append_test_bound_session(
            store,
            session=successor_session,
            signer=fixture.signer,
            writer_fence_token_sha256=successor_writer_token,
            writer_fence_generation=successor_writer_generation,
            idempotency_key="v46-successor-session",
            label="v46-successor-session",
        )
        successor_orphan = store.classify_outbound_control_orphans(
            successor_session.transport_session_id
        )
        assert successor_orphan.prepared_without_permit_ids == ()
        assert successor_orphan.permit_without_result_ids == ()
        assert not successor_orphan.session_is_terminal
        assert not successor_orphan.has_active_unresolved_control
        assert store.verify().outbound_control_dispatch_result_count == 0


@pytest.mark.parametrize(
    "fault_stage",
    (
        "after_canonical_record_insert",
        "after_inbound_websocket_protocol_failure_insert",
        "after_operation_batch_insert",
        "before_commit",
    ),
)
def test_protocol_failure_faults_roll_back_canonical_typed_and_batch_layers(
    tmp_path: Path,
    fault_stage: str,
) -> None:
    armed = False

    def fail_target(stage: str) -> None:
        if armed and stage == fault_stage:
            raise InjectedV46ProjectionFailure(stage)

    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(
        tmp_path / f"v4-6-failure-rollback-{fault_stage}.sqlite3",
        clock=clock,
        fault_injector=fail_target,
    ) as store:
        fixture = prepare_transport_fixture(store, clock=clock, authorize=False)
        authority = _control_authority(store, fixture, label=f"failure-{fault_stage}")
        raw = _masked_server_raw(authority)
        failure = _failure(raw)
        clock.value = raw.received_at
        store.append_raw_ingress_commit(
            raw,
            idempotency_key=f"failure-{fault_stage}-raw",
        )
        clock.value = failure.detected_at
        armed = True
        with pytest.raises(InjectedV46ProjectionFailure, match=fault_stage):
            store.append_inbound_websocket_protocol_failure(
                failure,
                idempotency_key=f"failure-{fault_stage}",
            )
        armed = False
        report = store.verify()
        assert report.inbound_websocket_protocol_failure_count == 0
        assert (
            store.append_inbound_websocket_protocol_failure(
                failure,
                idempotency_key=f"failure-{fault_stage}",
            )
            == failure
        )
        assert store.verify().inbound_websocket_protocol_failure_count == 1


@pytest.mark.parametrize(
    "fault_stage",
    (
        "after_canonical_record_insert",
        "after_outbound_control_write_permit_consumed_insert",
        "after_operation_batch_insert",
        "before_commit",
    ),
)
def test_write_permit_faults_leave_prepared_wire_definitely_unattempted(
    tmp_path: Path,
    fault_stage: str,
) -> None:
    armed = False

    def fail_target(stage: str) -> None:
        if armed and stage == fault_stage:
            raise InjectedV46ProjectionFailure(stage)

    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(
        tmp_path / f"v4-6-permit-rollback-{fault_stage}.sqlite3",
        clock=clock,
        fault_injector=fail_target,
    ) as store:
        fixture = prepare_transport_fixture(store, clock=clock, authorize=False)
        authority = _control_authority(store, fixture, label=f"permit-{fault_stage}")
        intent = _heartbeat_intent(authority, label="permit-fault")
        wire = _wire(intent)
        clock.value = intent.authorized_at
        store.append_outbound_control_intent(
            intent,
            idempotency_key=f"permit-{fault_stage}-intent",
        )
        clock.value = wire.prepared_at
        store.append_outbound_control_wire_prepared(
            wire,
            idempotency_key=f"permit-{fault_stage}-wire",
        )
        consumed_at = wire.prepared_at + timedelta(microseconds=500)
        consumed_ns = wire.prepared_monotonic_ns + 500_000
        clock.value = consumed_at
        armed = True
        with pytest.raises(InjectedV46ProjectionFailure, match=fault_stage):
            store.consume_outbound_control_write_permit(
                wire.outbound_control_wire_prepared_id,
                permit_consumed_at=consumed_at,
                permit_consumed_monotonic_ns=consumed_ns,
                idempotency_key=f"permit-{fault_stage}",
            )
        armed = False
        report = store.verify()
        assert report.outbound_control_write_permit_consumed_count == 0
        orphan = store.classify_outbound_control_orphans(
            fixture.session.transport_session_id
        )
        assert orphan.prepared_without_permit_ids == (
            wire.outbound_control_wire_prepared_id,
        )
        permit = store.consume_outbound_control_write_permit(
            wire.outbound_control_wire_prepared_id,
            permit_consumed_at=consumed_at,
            permit_consumed_monotonic_ns=consumed_ns,
            idempotency_key=f"permit-{fault_stage}",
        )
        assert store.classify_outbound_control_orphans(
            fixture.session.transport_session_id
        ).permit_without_result_ids == (permit.permit_id,)

from __future__ import annotations

import base64
import copy
import hashlib
import socket
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from riskyieldmm.trading.canonical import CanonicalizationError, sha256_digest
from riskyieldmm.trading.physical_projection_v4 import (
    PhysicalProjectionReceiptV4,
    PhysicalRecordKindV4,
)
from riskyieldmm.trading.physical_transport_actor_v49c import (
    CommittedRawChunkV49C,
    CommittedRawIngressV49C,
    DelineatedServerFrameV49C,
    KernelSendAttemptPayloadV49C,
    KernelSendResultPayloadV49C,
    LocalShutdownCommandStartedPayloadV49E,
    LocalShutdownDeadlineClassificationV49E,
    OutboundDispatchCompletedPayloadV49C,
    OutboundDispatchDispositionV49C,
    OutboundWireOriginV49C,
    OutboundWirePreparedPayloadV49C,
    ParserFeedUnitKindV49C,
    ParserTransitionPayloadV49C,
    RawIngressCommittedPayloadV49C,
    RetainedIngressTailV49C,
    TcpHalfCloseAttemptPayloadV49E,
    TcpHalfCloseResultKindV49E,
    TcpHalfCloseResultPayloadV49E,
    TerminalTransitionPayloadV49C,
    TlsCiphertextPreparedPayloadV49C,
    TlsControlCiphertextPreparedPayloadV49E,
    TlsControlKernelSendAttemptPayloadV49E,
    TlsControlKernelSendResultPayloadV49E,
    TlsControlOutputKindV49E,
    TlsProtocolOperationFailedPayloadV49E,
    TlsProtocolOperationFailureKindV49E,
    TlsProtocolOperationPurposeV49E,
    TlsProtocolOperationStartedPayloadV49E,
    TlsShutdownObservationKindV49E,
    TlsShutdownObservedPayloadV49E,
    TransportActorEventKindV49C,
    TransportActorEventV49C,
    WebSocketOpcodeV49C,
    WebSocketParserCursorV49C,
    WebSocketParserStateV49C,
    WritePermitConsumedPayloadV49C,
    delineate_next_server_frame_v49c,
    derive_actor_write_permit_id_v49c,
    derive_local_shutdown_command_id_v49e,
    validate_transport_actor_chain_v49c,
)
from riskyieldmm.trading.physical_transport_terminal_v49c import (
    V49E_TCP_HALF_CLOSE_ERROR_CAUSE,
    V49E_TCP_HALF_CLOSE_OUTCOME_UNKNOWN_CAUSE,
    V49E_TLS_CONTROL_SEND_OUTCOME_UNKNOWN_CAUSE,
    V49E_TLS_OPERATION_DRIVER_ERROR_CAUSE,
    V49E_TLS_POST_HANDSHAKE_OUTPUT_AFTER_SHUT_WR_CAUSE,
    V49E_TLS_SHUTDOWN_DEADLINE_EXPIRED_CAUSE,
    OutboundObligationLayerV49C,
    TerminalOutcomeV49C,
    TerminalStateV49C,
    TerminalTransitionKindV49C,
    advance_terminal_state_v49c,
    initial_terminal_state_v49c,
)

UTC = timezone.utc
T0 = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _encoded(chunks: tuple[bytes, ...]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    return (
        tuple(base64.b64encode(chunk).decode("ascii") for chunk in chunks),
        tuple(hashlib.sha256(chunk).hexdigest() for chunk in chunks),
    )


def _batch(domain: str, encoded: tuple[str, ...]) -> str:
    return sha256_digest({"domain": domain, "ordered_chunks_base64": list(encoded)})


AUTHORITY = {
    "transport_subscription_policy_id": _digest("subscription"),
    "transport_session_id": _digest("session"),
    "physical_scope_manifest_id": _digest("scope"),
    "adapter_policy_id": _digest("adapter"),
    "capture_partition_id": _digest("partition"),
    "socket_lease_id": _digest("lease"),
    "connection_generation": 1,
    "deployment_bundle_id": _digest("deployment"),
    "writer_fence_token_sha256": _digest("fence"),
    "writer_fence_generation": 1,
    "monotonic_clock_domain_id": _digest("clock"),
    "driver_policy_id": _digest("driver"),
}


def _payload_clock(payload: Any) -> tuple[datetime, int] | None:
    for wall_name, ns_name in (
        ("received_at", "received_monotonic_ns"),
        ("processed_at", "processed_monotonic_ns"),
        ("prepared_at", "prepared_monotonic_ns"),
        ("consumed_at", "consumed_monotonic_ns"),
        ("attempted_at", "attempted_monotonic_ns"),
        ("observed_at", "observed_monotonic_ns"),
        ("completed_at", "completed_monotonic_ns"),
        ("started_at", "started_monotonic_ns"),
    ):
        if hasattr(payload, wall_name):
            return getattr(payload, wall_name), getattr(payload, ns_name)
    return None


def _next_clock(
    events: list[TransportActorEventV49C],
) -> tuple[datetime, int]:
    if not events:
        return T0, 10
    return (
        events[-1].recorded_at + timedelta(milliseconds=1),
        events[-1].recorded_monotonic_ns + 10,
    )


def _append(
    events: list[TransportActorEventV49C],
    kind: TransportActorEventKindV49C,
    payload: Any,
) -> TransportActorEventV49C:
    clock = _payload_clock(payload)
    if type(payload) in {
        RawIngressCommittedPayloadV49C,
        LocalShutdownCommandStartedPayloadV49E,
    }:
        assert clock is not None
        recorded_at, recorded_ns = clock
    else:
        prior_at, prior_ns = _next_clock(events)
        if clock is None:
            recorded_at, recorded_ns = prior_at, prior_ns
        else:
            observed_at, observed_ns = clock
            recorded_at = max(prior_at, observed_at + timedelta(microseconds=1))
            recorded_ns = max(prior_ns, observed_ns + 1)
    event = TransportActorEventV49C.create(
        **AUTHORITY,
        recorded_at=recorded_at,
        recorded_monotonic_ns=recorded_ns,
        actor_sequence=len(events) + 1,
        previous_event_id=(None if not events else events[-1].transport_actor_event_id),
        event_kind=kind,
        payload=payload,
    )
    events.append(event)
    return event


def _append_local_shutdown_command(
    events: list[TransportActorEventV49C],
    *,
    timeout_seconds: int = 60,
) -> TransportActorEventV49C:
    started_at, started_ns = _next_clock(events)
    deadline_at = started_at + timedelta(seconds=timeout_seconds)
    deadline_ns = started_ns + timeout_seconds * 1_000_000_000
    predecessor_id = None if not events else events[-1].transport_actor_event_id
    return _append(
        events,
        TransportActorEventKindV49C.LOCAL_SHUTDOWN_COMMAND_STARTED,
        LocalShutdownCommandStartedPayloadV49E(
            local_shutdown_command_id=derive_local_shutdown_command_id_v49e(
                transport_session_id=AUTHORITY["transport_session_id"],
                actor_predecessor_event_id=predecessor_id,
                timeout_seconds=timeout_seconds,
                started_at=started_at,
                started_monotonic_ns=started_ns,
                deadline_at=deadline_at,
                deadline_monotonic_ns=deadline_ns,
            ),
            websocket_close_code=1000,
            websocket_close_reason_sha256=hashlib.sha256(b"").hexdigest(),
            websocket_close_reason_octets=0,
            websocket_close_payload_sha256=hashlib.sha256(b"\x03\xe8").hexdigest(),
            websocket_close_payload_octets=2,
            timeout_seconds=timeout_seconds,
            started_at=started_at,
            started_monotonic_ns=started_ns,
            shutdown_deadline_at=deadline_at,
            shutdown_deadline_monotonic_ns=deadline_ns,
        ),
    )


def _terminal(
    events: list[TransportActorEventV49C],
    state: TerminalStateV49C,
    kind: TerminalTransitionKindV49C,
    *,
    layer: OutboundObligationLayerV49C | None = None,
    obligation_id: str | None = None,
    send_attempt_id: str | None = None,
    cause_code: str | None = None,
) -> tuple[TerminalStateV49C, TransportActorEventV49C]:
    payload = TerminalTransitionPayloadV49C(
        transport_session_id=AUTHORITY["transport_session_id"],
        transition_sequence=state.transition_sequence + 1,
        parent_terminal_state_id=state.terminal_state_id,
        kind=kind,
        obligation_layer=layer,
        obligation_id=obligation_id,
        send_attempt_id=send_attempt_id,
        cause_code=cause_code,
    )
    event = _append(events, TransportActorEventKindV49C.TERMINAL_TRANSITION, payload)
    return advance_terminal_state_v49c(state, payload), event


def _raw_close_payload() -> tuple[RawIngressCommittedPayloadV49C, bytes]:
    frame = b"\x88\x00"
    raw_id = _digest("raw-close")
    ledger_id = _digest("ledger")
    content_hash = _digest("raw-close-content")
    previous = _digest("receipt-genesis")
    receipt_hash = sha256_digest(
        {
            "content_hash": content_hash,
            "domain": "RiskYieldMMPhysicalProjectionReceiptV4",
            "global_sequence": 1,
            "identity_id": raw_id,
            "ledger_id": ledger_id,
            "previous_receipt_hash": previous,
            "record_kind": PhysicalRecordKindV4.RAW_INGRESS_COMMIT.value,
        }
    )
    receipt = PhysicalProjectionReceiptV4(
        global_sequence=1,
        receipt_hash=receipt_hash,
        previous_receipt_hash=previous,
        record_kind=PhysicalRecordKindV4.RAW_INGRESS_COMMIT,
        identity_id=raw_id,
        content_hash=content_hash,
        committed_at=T0 + timedelta(milliseconds=1),
    )
    committed = CommittedRawIngressV49C.from_projection_receipt(
        ledger_id=ledger_id, receipt=receipt
    )
    encoded, _ = _encoded((frame,))
    return (
        RawIngressCommittedPayloadV49C(
            raw_ingress_commit_id=raw_id,
            receipt=committed,
            ingress_sequence=1,
            previous_raw_ingress_commit_id=None,
            stream_start_octet=0,
            stream_end_octet=len(frame),
            ordered_chunk_octet_lengths=(len(frame),),
            ordered_chunk_sha256=(hashlib.sha256(frame).hexdigest(),),
            raw_ingress_batch_sha256=_batch(
                "RiskYieldMMExactOrderedDecryptedIngressChunksV4_5", encoded
            ),
            received_at=T0,
            received_monotonic_ns=10,
        ),
        frame,
    )


def _websocket_close_prefix() -> tuple[
    list[TransportActorEventV49C], TerminalStateV49C, TransportActorEventV49C
]:
    events: list[TransportActorEventV49C] = []
    state = initial_terminal_state_v49c(AUTHORITY["transport_session_id"])
    raw, inbound = _raw_close_payload()
    _append(events, TransportActorEventKindV49C.RAW_INGRESS_COMMITTED, raw)
    delineated = delineate_next_server_frame_v49c(
        prior_tail=RetainedIngressTailV49C(),
        committed_raw_chunks=(
            CommittedRawChunkV49C(
                raw_ingress_commit_id=raw.raw_ingress_commit_id,
                projection_receipt_sequence=raw.receipt.global_sequence,
                projection_receipt_hash=raw.receipt.receipt_hash,
                raw_local_start_octet=0,
                stream_start_octet=0,
                data=inbound,
            ),
        ),
    )
    assert type(delineated.unit) is DelineatedServerFrameV49C
    outbound = b"\x88\x80\x01\x02\x03\x04"
    output_encoded, output_hashes = _encoded((outbound,))
    parser = ParserTransitionPayloadV49C(
        cursor_before=WebSocketParserCursorV49C(
            cursor_sequence=0,
            next_stream_octet=0,
            websocket_state=WebSocketParserStateV49C.OPEN,
        ),
        cursor_after=WebSocketParserCursorV49C(
            cursor_sequence=1,
            next_stream_octet=len(inbound),
            websocket_state=WebSocketParserStateV49C.CLOSING,
        ),
        feed_unit_kind=ParserFeedUnitKindV49C.COMPLETE_FRAME,
        source_slices=delineated.unit.source_slices,
        frame=delineated.unit.metadata,
        parser_error=None,
        ordered_protocol_output_chunks_base64=output_encoded,
        ordered_protocol_output_chunks_sha256=output_hashes,
        protocol_output_batch_sha256=_batch(
            "RiskYieldMMActorOrderedProtocolOutputV4_9C", output_encoded
        ),
        send_eof_after_output=True,
        processed_at=T0 + timedelta(milliseconds=2),
        processed_monotonic_ns=20,
    )
    parser_event = _append(
        events, TransportActorEventKindV49C.PARSER_TRANSITION, parser
    )
    state, _ = _terminal(events, state, TerminalTransitionKindV49C.WS_CLOSE_RECEIVED)
    prepared_at, prepared_ns = _next_clock(events)
    wire = OutboundWirePreparedPayloadV49C(
        outbound_operation_id=_digest("ws-close-operation"),
        wire_origin=OutboundWireOriginV49C.AUTOMATIC_PROTOCOL,
        source_parser_event_id=parser_event.transport_actor_event_id,
        logical_opcode=WebSocketOpcodeV49C.CLOSE,
        logical_payload_sha256=hashlib.sha256(b"").hexdigest(),
        logical_payload_octets=0,
        ordered_wire_chunks_base64=output_encoded,
        ordered_wire_chunks_sha256=output_hashes,
        wire_batch_sha256=_batch(
            "RiskYieldMMActorOrderedProtocolOutputV4_9C", output_encoded
        ),
        wire_octets=len(outbound),
        prepared_at=prepared_at,
        prepared_monotonic_ns=prepared_ns,
        send_not_after=prepared_at + timedelta(minutes=1),
        send_not_after_monotonic_ns=prepared_ns + 100_000,
    )
    wire_event = _append(
        events, TransportActorEventKindV49C.OUTBOUND_WIRE_PREPARED, wire
    )
    state, _ = _terminal(
        events,
        state,
        TerminalTransitionKindV49C.WS_CLOSE_SENT,
        layer=OutboundObligationLayerV49C.WEBSOCKET_CLOSE,
        obligation_id=wire.outbound_operation_id,
    )
    consumed_at, consumed_ns = _next_clock(events)
    permit = WritePermitConsumedPayloadV49C(
        outbound_wire_prepared_event_id=wire_event.transport_actor_event_id,
        permit_id=derive_actor_write_permit_id_v49c(
            outbound_operation_id=wire.outbound_operation_id,
            outbound_wire_prepared_event_id=wire_event.transport_actor_event_id,
            socket_lease_id=wire_event.socket_lease_id,
            writer_fence_token_sha256=wire_event.writer_fence_token_sha256,
            writer_fence_generation=wire_event.writer_fence_generation,
        ),
        one_shot_attempt_ordinal=1,
        wire_batch_sha256=wire.wire_batch_sha256,
        wire_octets=wire.wire_octets,
        consumed_at=consumed_at,
        consumed_monotonic_ns=consumed_ns,
        send_not_after=wire.send_not_after,
        send_not_after_monotonic_ns=wire.send_not_after_monotonic_ns,
    )
    permit_event = _append(
        events, TransportActorEventKindV49C.WRITE_PERMIT_CONSUMED, permit
    )
    ciphertext = b"websocket-close-ciphertext"
    cipher_encoded, cipher_hashes = _encoded((ciphertext,))
    tls_at, tls_ns = _next_clock(events)
    tls = TlsCiphertextPreparedPayloadV49C(
        outbound_wire_prepared_event_id=wire_event.transport_actor_event_id,
        write_permit_consumed_event_id=permit_event.transport_actor_event_id,
        plaintext_batch_sha256=wire.wire_batch_sha256,
        plaintext_octets=wire.wire_octets,
        ordered_ciphertext_chunks_base64=cipher_encoded,
        ordered_ciphertext_chunks_sha256=cipher_hashes,
        ciphertext_batch_sha256=_batch(
            "RiskYieldMMActorOrderedTlsCiphertextV4_9C", cipher_encoded
        ),
        ciphertext_octets=len(ciphertext),
        prepared_at=tls_at,
        prepared_monotonic_ns=tls_ns,
    )
    tls_event = _append(
        events, TransportActorEventKindV49C.TLS_CIPHERTEXT_PREPARED, tls
    )
    attempt_at, attempt_ns = _next_clock(events)
    attempt = KernelSendAttemptPayloadV49C(
        tls_ciphertext_prepared_event_id=tls_event.transport_actor_event_id,
        kernel_attempt_ordinal=1,
        ciphertext_batch_sha256=tls.ciphertext_batch_sha256,
        ciphertext_octets=tls.ciphertext_octets,
        ciphertext_start_octet=0,
        requested_octets=tls.ciphertext_octets,
        attempted_at=attempt_at,
        attempted_monotonic_ns=attempt_ns,
    )
    attempt_event = _append(
        events, TransportActorEventKindV49C.KERNEL_SEND_ATTEMPT, attempt
    )
    state, _ = _terminal(
        events,
        state,
        TerminalTransitionKindV49C.SEND_ATTEMPT_STARTED,
        layer=OutboundObligationLayerV49C.WEBSOCKET_CLOSE,
        obligation_id=wire.outbound_operation_id,
        send_attempt_id=attempt_event.transport_actor_event_id,
    )
    result_at, result_ns = _next_clock(events)
    result = KernelSendResultPayloadV49C(
        kernel_send_attempt_event_id=attempt_event.transport_actor_event_id,
        tls_ciphertext_prepared_event_id=tls_event.transport_actor_event_id,
        kernel_attempt_ordinal=1,
        ciphertext_batch_sha256=tls.ciphertext_batch_sha256,
        ciphertext_octets=tls.ciphertext_octets,
        ciphertext_start_octet=0,
        requested_octets=tls.ciphertext_octets,
        accepted_octets=tls.ciphertext_octets,
        resulting_ciphertext_offset=tls.ciphertext_octets,
        observed_at=result_at,
        observed_monotonic_ns=result_ns,
    )
    result_event = _append(
        events, TransportActorEventKindV49C.KERNEL_SEND_RESULT, result
    )
    state, _ = _terminal(
        events,
        state,
        TerminalTransitionKindV49C.SEND_ATTEMPT_RESOLVED,
        layer=OutboundObligationLayerV49C.WEBSOCKET_CLOSE,
        obligation_id=wire.outbound_operation_id,
        send_attempt_id=attempt_event.transport_actor_event_id,
    )
    completed_at, completed_ns = _next_clock(events)
    dispatch = OutboundDispatchCompletedPayloadV49C(
        outbound_wire_prepared_event_id=wire_event.transport_actor_event_id,
        write_permit_consumed_event_id=permit_event.transport_actor_event_id,
        tls_ciphertext_prepared_event_id=tls_event.transport_actor_event_id,
        kernel_send_result_event_ids=(result_event.transport_actor_event_id,),
        ciphertext_batch_sha256=tls.ciphertext_batch_sha256,
        ciphertext_octets=tls.ciphertext_octets,
        submitted_ciphertext_octets=tls.ciphertext_octets,
        disposition=OutboundDispatchDispositionV49C.COMPLETE_LOCAL_SUBMISSION,
        completed_at=completed_at,
        completed_monotonic_ns=completed_ns,
    )
    _append(events, TransportActorEventKindV49C.OUTBOUND_DISPATCH_COMPLETED, dispatch)
    state, accepted_event = _terminal(
        events,
        state,
        TerminalTransitionKindV49C.OUTBOUND_OBLIGATION_FULLY_KERNEL_ACCEPTED,
        layer=OutboundObligationLayerV49C.WEBSOCKET_CLOSE,
        obligation_id=wire.outbound_operation_id,
    )
    _append_local_shutdown_command(events)
    return events, state, accepted_event


def _start_tls_operation(
    events: list[TransportActorEventV49C],
    *,
    sequence: int,
    purpose: TlsProtocolOperationPurposeV49E,
    cause_event_id: str,
) -> TransportActorEventV49C:
    command_event = next(
        event
        for event in reversed(events)
        if event.event_kind
        is TransportActorEventKindV49C.LOCAL_SHUTDOWN_COMMAND_STARTED
    )
    driver_nonce = _digest("driver-evidence-nonce")
    operation_id = sha256_digest(
        {
            "domain": "RiskYieldMMTlsProtocolOperationV4_9E",
            "transport_session_id": AUTHORITY["transport_session_id"],
            "operation_sequence": sequence,
            "local_shutdown_command_started_event_id": (
                command_event.transport_actor_event_id
            ),
            "purpose": purpose.value,
            "cause_actor_event_id": cause_event_id,
            "driver_evidence_nonce_sha256": driver_nonce,
        }
    )
    started_at, started_ns = _next_clock(events)
    return _append(
        events,
        TransportActorEventKindV49C.TLS_PROTOCOL_OPERATION_STARTED,
        TlsProtocolOperationStartedPayloadV49E(
            operation_sequence=sequence,
            tls_operation_id=operation_id,
            local_shutdown_command_started_event_id=(
                command_event.transport_actor_event_id
            ),
            purpose=purpose,
            cause_actor_event_id=cause_event_id,
            driver_evidence_nonce_sha256=driver_nonce,
            started_at=started_at,
            started_monotonic_ns=started_ns,
        ),
    )


def _prepare_control(
    events: list[TransportActorEventV49C],
    operation_event: TransportActorEventV49C,
    *,
    control_sequence: int = 1,
    kind: TlsControlOutputKindV49E = TlsControlOutputKindV49E.LOCAL_CLOSE_NOTIFY,
    peer_close_notify_received_during_preparation: bool = False,
) -> TransportActorEventV49C:
    operation = operation_event.payload
    assert type(operation) is TlsProtocolOperationStartedPayloadV49E
    ciphertext = (
        b"close-notify"
        if kind is TlsControlOutputKindV49E.LOCAL_CLOSE_NOTIFY
        else b"opaque-post-handshake-response"
    )
    encoded, hashes = _encoded((ciphertext,))
    prepared_at, prepared_ns = _next_clock(events)
    return _append(
        events,
        TransportActorEventKindV49C.TLS_CONTROL_CIPHERTEXT_PREPARED,
        TlsControlCiphertextPreparedPayloadV49E(
            tls_protocol_operation_started_event_id=(
                operation_event.transport_actor_event_id
            ),
            tls_operation_id=operation.tls_operation_id,
            control_sequence=control_sequence,
            control_kind=kind,
            driver_evidence_nonce_sha256=operation.driver_evidence_nonce_sha256,
            ordered_ciphertext_chunks_base64=encoded,
            ordered_ciphertext_chunks_sha256=hashes,
            ciphertext_batch_sha256=_batch(
                "RiskYieldMMActorOrderedTlsControlCiphertextV4_9E", encoded
            ),
            ciphertext_octets=len(ciphertext),
            peer_close_notify_received_during_preparation=(
                peer_close_notify_received_during_preparation
            ),
            prepared_at=prepared_at,
            prepared_monotonic_ns=prepared_ns,
        ),
    )


def _fail_tls_operation(
    events: list[TransportActorEventV49C],
    operation_event: TransportActorEventV49C,
    failure_kind: TlsProtocolOperationFailureKindV49E,
) -> TransportActorEventV49C:
    operation = operation_event.payload
    assert type(operation) is TlsProtocolOperationStartedPayloadV49E
    unsendable = (
        failure_kind
        is TlsProtocolOperationFailureKindV49E.UNSENDABLE_POST_HANDSHAKE_OUTPUT_AFTER_SHUT_WR
    )
    unsendable_digest = _digest("unsendable-post-handshake-output")
    unsendable_sequence = 1
    unsendable_driver_id = (
        sha256_digest(
            {
                "domain": "RiskYieldMMUnsendableTlsPostHandshakeOutputV4_9E",
                "output_sequence": unsendable_sequence,
                "driver_evidence_nonce_sha256": (
                    operation.driver_evidence_nonce_sha256
                ),
                "ciphertext_sha256": unsendable_digest,
                "ciphertext_octets": 17,
            }
        )
        if unsendable
        else None
    )
    unsendable_socket = _digest("unsendable-owner-socket")
    unsendable_owner_id = (
        sha256_digest(
            {
                "domain": "RiskYieldMMOwnerUnsendableTlsPostHandshakeOutputV4_9E",
                "transport_session_id": AUTHORITY["transport_session_id"],
                "kernel_socket_identity": unsendable_socket,
                "driver_unsendable_output_id": unsendable_driver_id,
                "driver_output_sequence": unsendable_sequence,
                "driver_evidence_nonce_sha256": (
                    operation.driver_evidence_nonce_sha256
                ),
                "ciphertext_sha256": unsendable_digest,
                "ciphertext_octets": 17,
            }
        )
        if unsendable
        else None
    )
    command_event = next(
        event
        for event in events
        if event.transport_actor_event_id
        == operation.local_shutdown_command_started_event_id
    )
    command = command_event.payload
    assert type(command) is LocalShutdownCommandStartedPayloadV49E
    no_observation = (
        failure_kind
        is TlsProtocolOperationFailureKindV49E.DEADLINE_EXPIRED_NO_OBSERVATION
    )
    kernel_socket_identity = _digest("owner-kernel-socket")
    deadline_operation = (
        "LOCAL_TLS_CLOSE_NOTIFY_PREPARATION"
        if operation.purpose is TlsProtocolOperationPurposeV49E.LOCAL_CLOSE_NOTIFY
        else "TLS_SHUTDOWN_POLL"
    )
    no_observation_owner_evidence_id = (
        sha256_digest(
            {
                "domain": "RiskYieldMMOwnerDeadlineExpiredNoObservationV4_9E",
                "transport_session_id": AUTHORITY["transport_session_id"],
                "kernel_socket_identity": kernel_socket_identity,
                "driver_evidence_nonce_sha256": (
                    operation.driver_evidence_nonce_sha256
                ),
                "operation": deadline_operation,
                "deadline_ns": command.shutdown_deadline_monotonic_ns,
            }
        )
        if no_observation
        else None
    )
    observed_at, observed_ns = (
        (
            command.shutdown_deadline_at,
            command.shutdown_deadline_monotonic_ns,
        )
        if no_observation
        else _next_clock(events)
    )
    return _append(
        events,
        TransportActorEventKindV49C.TLS_PROTOCOL_OPERATION_FAILED,
        TlsProtocolOperationFailedPayloadV49E(
            tls_protocol_operation_started_event_id=(
                operation_event.transport_actor_event_id
            ),
            tls_operation_id=operation.tls_operation_id,
            purpose=operation.purpose,
            driver_evidence_nonce_sha256=operation.driver_evidence_nonce_sha256,
            failure_kind=failure_kind,
            deadline_classification=(
                LocalShutdownDeadlineClassificationV49E.BOTH_DUE
                if no_observation
                else None
            ),
            shutdown_deadline_monotonic_ns=(command.shutdown_deadline_monotonic_ns),
            unsendable_driver_output_sequence=(
                unsendable_sequence if unsendable else None
            ),
            unsendable_driver_evidence_id=unsendable_driver_id,
            unsendable_owner_evidence_id=unsendable_owner_id,
            unsendable_kernel_socket_identity=(
                unsendable_socket if unsendable else None
            ),
            unsendable_ciphertext_sha256=(unsendable_digest if unsendable else None),
            unsendable_ciphertext_octets=17 if unsendable else None,
            deadline_no_observation_owner_evidence_id=(
                no_observation_owner_evidence_id
            ),
            deadline_no_observation_kernel_socket_identity=(
                kernel_socket_identity if no_observation else None
            ),
            deadline_no_observation_operation=(
                deadline_operation if no_observation else None
            ),
            deadline_after_progress_owner_evidence_id=None,
            deadline_after_progress_driver_evidence_id=None,
            deadline_after_progress_kernel_socket_identity=None,
            deadline_after_progress_operation=None,
            deadline_after_progress_ciphertext_sha256=None,
            deadline_after_progress_ciphertext_octets=None,
            observed_at=observed_at,
            observed_monotonic_ns=observed_ns,
        ),
    )


def _append_control_attempt(
    events: list[TransportActorEventV49C],
    control_event: TransportActorEventV49C,
    *,
    start_octet: int = 0,
    attempt_ordinal: int = 1,
    requested_octets: int | None = None,
) -> TransportActorEventV49C:
    control = control_event.payload
    assert type(control) is TlsControlCiphertextPreparedPayloadV49E
    requested = (
        control.ciphertext_octets - start_octet
        if requested_octets is None
        else requested_octets
    )
    attempted_at, attempted_ns = _next_clock(events)
    command_event = next(
        event
        for event in reversed(events)
        if event.event_kind
        is TransportActorEventKindV49C.LOCAL_SHUTDOWN_COMMAND_STARTED
    )
    command = command_event.payload
    assert type(command) is LocalShutdownCommandStartedPayloadV49E
    return _append(
        events,
        TransportActorEventKindV49C.TLS_CONTROL_KERNEL_SEND_ATTEMPT,
        TlsControlKernelSendAttemptPayloadV49E(
            tls_control_ciphertext_prepared_event_id=(
                control_event.transport_actor_event_id
            ),
            local_shutdown_command_started_event_id=(
                command_event.transport_actor_event_id
            ),
            shutdown_deadline_monotonic_ns=(command.shutdown_deadline_monotonic_ns),
            kernel_attempt_ordinal=attempt_ordinal,
            ciphertext_batch_sha256=control.ciphertext_batch_sha256,
            ciphertext_octets=control.ciphertext_octets,
            ciphertext_start_octet=start_octet,
            requested_octets=requested,
            attempted_at=attempted_at,
            attempted_monotonic_ns=attempted_ns,
        ),
    )


def _append_control_result(
    events: list[TransportActorEventV49C],
    control_event: TransportActorEventV49C,
    attempt_event: TransportActorEventV49C,
    *,
    accepted_octets: int | None = None,
) -> TransportActorEventV49C:
    control = control_event.payload
    attempt = attempt_event.payload
    assert type(control) is TlsControlCiphertextPreparedPayloadV49E
    assert type(attempt) is TlsControlKernelSendAttemptPayloadV49E
    accepted = attempt.requested_octets if accepted_octets is None else accepted_octets
    observed_at, observed_ns = _next_clock(events)
    return _append(
        events,
        TransportActorEventKindV49C.TLS_CONTROL_KERNEL_SEND_RESULT,
        TlsControlKernelSendResultPayloadV49E(
            tls_control_kernel_send_attempt_event_id=(
                attempt_event.transport_actor_event_id
            ),
            tls_control_ciphertext_prepared_event_id=(
                control_event.transport_actor_event_id
            ),
            kernel_attempt_ordinal=attempt.kernel_attempt_ordinal,
            ciphertext_batch_sha256=control.ciphertext_batch_sha256,
            ciphertext_octets=control.ciphertext_octets,
            ciphertext_start_octet=attempt.ciphertext_start_octet,
            requested_octets=attempt.requested_octets,
            accepted_octets=accepted,
            resulting_ciphertext_offset=(attempt.ciphertext_start_octet + accepted),
            observed_at=observed_at,
            observed_monotonic_ns=observed_ns,
        ),
    )


def _send_control(
    events: list[TransportActorEventV49C],
    state: TerminalStateV49C,
    control_event: TransportActorEventV49C,
    *,
    start_octet: int = 0,
    attempt_ordinal: int = 1,
    requested_octets: int | None = None,
) -> tuple[
    TerminalStateV49C,
    TransportActorEventV49C,
    TransportActorEventV49C,
]:
    control = control_event.payload
    assert type(control) is TlsControlCiphertextPreparedPayloadV49E
    attempt_event = _append_control_attempt(
        events,
        control_event,
        start_octet=start_octet,
        attempt_ordinal=attempt_ordinal,
        requested_octets=requested_octets,
    )
    layer = (
        OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY
        if control.control_kind is TlsControlOutputKindV49E.LOCAL_CLOSE_NOTIFY
        else OutboundObligationLayerV49C.TLS_OPAQUE_CONTROL
    )
    state, _ = _terminal(
        events,
        state,
        TerminalTransitionKindV49C.SEND_ATTEMPT_STARTED,
        layer=layer,
        obligation_id=control_event.transport_actor_event_id,
        send_attempt_id=attempt_event.transport_actor_event_id,
    )
    result_event = _append_control_result(
        events,
        control_event,
        attempt_event,
    )
    state, _ = _terminal(
        events,
        state,
        TerminalTransitionKindV49C.SEND_ATTEMPT_RESOLVED,
        layer=layer,
        obligation_id=control_event.transport_actor_event_id,
        send_attempt_id=attempt_event.transport_actor_event_id,
    )
    return state, result_event, attempt_event


def _local_control_prepared_prefix(
    *, peer_close_notify_received_during_preparation: bool = False
) -> tuple[
    list[TransportActorEventV49C],
    TerminalStateV49C,
    TransportActorEventV49C,
]:
    events, state, ws_accepted = _websocket_close_prefix()
    operation = _start_tls_operation(
        events,
        sequence=1,
        purpose=TlsProtocolOperationPurposeV49E.LOCAL_CLOSE_NOTIFY,
        cause_event_id=ws_accepted.transport_actor_event_id,
    )
    control_event = _prepare_control(
        events,
        operation,
        peer_close_notify_received_during_preparation=(
            peer_close_notify_received_during_preparation
        ),
    )
    state, _ = _terminal(
        events,
        state,
        TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_PREPARED,
        layer=OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY,
        obligation_id=control_event.transport_actor_event_id,
    )
    return events, state, control_event


def _local_tls_accepted_prefix(
    *, peer_close_notify_received_during_preparation: bool = False
) -> tuple[
    list[TransportActorEventV49C],
    TerminalStateV49C,
    TransportActorEventV49C,
    TransportActorEventV49C,
]:
    events, state, control_event = _local_control_prepared_prefix(
        peer_close_notify_received_during_preparation=(
            peer_close_notify_received_during_preparation
        )
    )
    state, _, _ = _send_control(events, state, control_event)
    state, tls_marker = _terminal(
        events,
        state,
        TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_SENT,
        layer=OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY,
        obligation_id=control_event.transport_actor_event_id,
    )
    state, _ = _terminal(
        events,
        state,
        TerminalTransitionKindV49C.OUTBOUND_OBLIGATION_FULLY_KERNEL_ACCEPTED,
        layer=OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY,
        obligation_id=control_event.transport_actor_event_id,
    )
    return events, state, tls_marker, control_event


def _local_tls_and_half_close_prefix(
    *, peer_close_notify_received_during_preparation: bool = False
) -> tuple[
    list[TransportActorEventV49C],
    TerminalStateV49C,
    TransportActorEventV49C,
    TransportActorEventV49C,
]:
    events, state, tls_marker, control_event = _local_tls_accepted_prefix(
        peer_close_notify_received_during_preparation=(
            peer_close_notify_received_during_preparation
        )
    )
    half_attempt = _append_half_close_attempt(
        events,
        tls_marker,
        control_event,
    )
    _append_half_close_result(
        events,
        half_attempt,
        result_kind=TcpHalfCloseResultKindV49E.KERNEL_ACCEPTED,
    )
    state, fin_marker = _terminal(
        events, state, TerminalTransitionKindV49C.TCP_FIN_SENT
    )
    return events, state, fin_marker, control_event


def _append_half_close_attempt(
    events: list[TransportActorEventV49C],
    tls_marker: TransportActorEventV49C,
    control_event: TransportActorEventV49C,
    *,
    shutdown_token_id_override: str | None = None,
) -> TransportActorEventV49C:
    control = control_event.payload
    assert type(control) is TlsControlCiphertextPreparedPayloadV49E
    command_event = next(
        event
        for event in reversed(events)
        if event.event_kind
        is TransportActorEventKindV49C.LOCAL_SHUTDOWN_COMMAND_STARTED
    )
    command = command_event.payload
    assert type(command) is LocalShutdownCommandStartedPayloadV49E
    shutdown_token_id = sha256_digest(
        {
            "domain": "RiskYieldMMTcpWriteShutdownTokenV4_9E",
            "token_sequence": 1,
            "transport_session_id": AUTHORITY["transport_session_id"],
            "tls_control_sequence": control.control_sequence,
            "tls_ciphertext_batch_sha256": control.ciphertext_batch_sha256,
            "tls_ciphertext_octets": control.ciphertext_octets,
            "shutdown_deadline_monotonic_ns": (command.shutdown_deadline_monotonic_ns),
        }
    )
    attempted_at, attempted_ns = _next_clock(events)
    return _append(
        events,
        TransportActorEventKindV49C.TCP_HALF_CLOSE_ATTEMPT,
        TcpHalfCloseAttemptPayloadV49E(
            tls_close_notify_sent_event_id=tls_marker.transport_actor_event_id,
            tls_control_ciphertext_prepared_event_id=(
                control_event.transport_actor_event_id
            ),
            local_shutdown_command_started_event_id=(
                command_event.transport_actor_event_id
            ),
            shutdown_token_id=(
                shutdown_token_id
                if shutdown_token_id_override is None
                else shutdown_token_id_override
            ),
            shutdown_deadline_monotonic_ns=(command.shutdown_deadline_monotonic_ns),
            token_sequence=1,
            tls_control_sequence=control.control_sequence,
            tls_ciphertext_batch_sha256=control.ciphertext_batch_sha256,
            tls_ciphertext_octets=control.ciphertext_octets,
            shutdown_how="SHUT_WR",
            attempted_at=attempted_at,
            attempted_monotonic_ns=attempted_ns,
        ),
    )


def _append_half_close_result(
    events: list[TransportActorEventV49C],
    half_attempt: TransportActorEventV49C,
    *,
    result_kind: TcpHalfCloseResultKindV49E,
    shutdown_result_id_override: str | None = None,
) -> TransportActorEventV49C:
    attempt = half_attempt.payload
    assert type(attempt) is TcpHalfCloseAttemptPayloadV49E
    error_code = (
        None
        if result_kind is TcpHalfCloseResultKindV49E.KERNEL_ACCEPTED
        else "ENOTCONN"
    )
    shutdown_result_id = sha256_digest(
        {
            "domain": "RiskYieldMMTcpWriteShutdownResultV4_9E",
            "shutdown_token_id": attempt.shutdown_token_id,
            "shutdown_how": 1,
            "kernel_accepted": (
                result_kind is TcpHalfCloseResultKindV49E.KERNEL_ACCEPTED
            ),
            "error_code": error_code,
        }
    )
    observed_at, observed_ns = _next_clock(events)
    return _append(
        events,
        TransportActorEventKindV49C.TCP_HALF_CLOSE_RESULT,
        TcpHalfCloseResultPayloadV49E(
            tcp_half_close_attempt_event_id=half_attempt.transport_actor_event_id,
            shutdown_token_id=attempt.shutdown_token_id,
            shutdown_result_id=(
                shutdown_result_id
                if shutdown_result_id_override is None
                else shutdown_result_id_override
            ),
            shutdown_how="SHUT_WR",
            result_kind=result_kind,
            error_code=error_code,
            observed_at=observed_at,
            observed_monotonic_ns=observed_ns,
        ),
    )


def _observe_shutdown(
    events: list[TransportActorEventV49C],
    state: TerminalStateV49C,
    *,
    operation_sequence: int,
    observation_sequence: int,
    kind: TlsShutdownObservationKindV49E,
    cause_event_id: str,
    peer_received: bool,
    ciphertext_octets_received: int = 17,
) -> tuple[TerminalStateV49C, TransportActorEventV49C]:
    operation = _start_tls_operation(
        events,
        sequence=operation_sequence,
        purpose=TlsProtocolOperationPurposeV49E.PEER_SHUTDOWN_POLL,
        cause_event_id=cause_event_id,
    )
    operation_payload = operation.payload
    assert type(operation_payload) is TlsProtocolOperationStartedPayloadV49E
    observation_id = sha256_digest(
        {
            "domain": "RiskYieldMMTlsShutdownObservationV4_9E",
            "observation_sequence": observation_sequence,
            "observation_kind": kind.value,
            "driver_evidence_nonce_sha256": (
                operation_payload.driver_evidence_nonce_sha256
            ),
            "peer_close_notify_received": peer_received,
            "tcp_eof_received": kind is TlsShutdownObservationKindV49E.TCP_EOF,
            "truncated": (
                kind is TlsShutdownObservationKindV49E.TCP_EOF and not peer_received
            ),
            "ciphertext_octets_received": ciphertext_octets_received,
        }
    )
    owner_kernel_socket_identity = _digest("owner-kernel-socket")
    owner_observation_id = sha256_digest(
        {
            "domain": "RiskYieldMMOwnerTlsShutdownObservationV4_9E",
            "transport_session_id": AUTHORITY["transport_session_id"],
            "kernel_socket_identity": owner_kernel_socket_identity,
            "driver_observation_id": observation_id,
            "driver_observation_sequence": observation_sequence,
            "driver_observation_kind": kind.value,
        }
    )
    observed_at, observed_ns = _next_clock(events)
    _append(
        events,
        TransportActorEventKindV49C.TLS_SHUTDOWN_OBSERVED,
        TlsShutdownObservedPayloadV49E(
            tls_protocol_operation_started_event_id=(
                operation.transport_actor_event_id
            ),
            tls_operation_id=operation_payload.tls_operation_id,
            observation_sequence=observation_sequence,
            observation_kind=kind,
            driver_evidence_nonce_sha256=(
                operation_payload.driver_evidence_nonce_sha256
            ),
            peer_close_notify_received=peer_received,
            tcp_eof_received=kind is TlsShutdownObservationKindV49E.TCP_EOF,
            truncated=(
                kind is TlsShutdownObservationKindV49E.TCP_EOF and not peer_received
            ),
            ciphertext_octets_received=ciphertext_octets_received,
            observation_id=observation_id,
            owner_observation_id=owner_observation_id,
            owner_kernel_socket_identity=owner_kernel_socket_identity,
            observed_at=observed_at,
            observed_monotonic_ns=observed_ns,
        ),
    )
    terminal_kind = (
        TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_RECEIVED
        if kind is TlsShutdownObservationKindV49E.PEER_CLOSE_NOTIFY
        else TerminalTransitionKindV49C.TCP_EOF_RECEIVED
    )
    return _terminal(events, state, terminal_kind)


def test_v49e_actor_accepts_exact_clean_layered_shutdown_and_roundtrips() -> None:
    events, state, fin_marker, _ = _local_tls_and_half_close_prefix()
    state, peer_marker = _observe_shutdown(
        events,
        state,
        operation_sequence=2,
        observation_sequence=1,
        kind=TlsShutdownObservationKindV49E.PEER_CLOSE_NOTIFY,
        cause_event_id=fin_marker.transport_actor_event_id,
        peer_received=True,
    )
    state, _ = _observe_shutdown(
        events,
        state,
        operation_sequence=3,
        observation_sequence=2,
        kind=TlsShutdownObservationKindV49E.TCP_EOF,
        cause_event_id=peer_marker.transport_actor_event_id,
        peer_received=True,
    )
    state, _ = _terminal(events, state, TerminalTransitionKindV49C.CLEAN_ALL_LAYERS)

    actor_state = validate_transport_actor_chain_v49c(events)
    assert actor_state == state
    assert state.is_terminal
    assert all(
        TransportActorEventV49C.from_mapping(event.as_dict()) == event
        for event in events
    )


def test_peer_close_received_during_local_preparation_is_incorporated_once() -> None:
    events, state, fin_marker, _ = _local_tls_and_half_close_prefix(
        peer_close_notify_received_during_preparation=True
    )
    state, peer_marker = _observe_shutdown(
        events,
        state,
        operation_sequence=2,
        observation_sequence=1,
        kind=TlsShutdownObservationKindV49E.PEER_CLOSE_NOTIFY,
        cause_event_id=fin_marker.transport_actor_event_id,
        peer_received=True,
        ciphertext_octets_received=0,
    )
    state, _ = _observe_shutdown(
        events,
        state,
        operation_sequence=3,
        observation_sequence=2,
        kind=TlsShutdownObservationKindV49E.TCP_EOF,
        cause_event_id=peer_marker.transport_actor_event_id,
        peer_received=True,
        ciphertext_octets_received=0,
    )
    state, _ = _terminal(events, state, TerminalTransitionKindV49C.CLEAN_ALL_LAYERS)

    assert validate_transport_actor_chain_v49c(events) == state
    assert state.is_terminal


def test_peer_close_received_during_local_preparation_rejects_later_byte_claim() -> (
    None
):
    events, state, fin_marker, _ = _local_tls_and_half_close_prefix(
        peer_close_notify_received_during_preparation=True
    )
    _observe_shutdown(
        events,
        state,
        operation_sequence=2,
        observation_sequence=1,
        kind=TlsShutdownObservationKindV49E.PEER_CLOSE_NOTIFY,
        cause_event_id=fin_marker.transport_actor_event_id,
        peer_received=True,
        ciphertext_octets_received=1,
    )

    with pytest.raises(CanonicalizationError, match="one zero-byte poll observation"):
        validate_transport_actor_chain_v49c(events)


def test_local_close_notify_marker_rejects_partial_control_acceptance() -> None:
    events, state, ws_accepted = _websocket_close_prefix()
    operation = _start_tls_operation(
        events,
        sequence=1,
        purpose=TlsProtocolOperationPurposeV49E.LOCAL_CLOSE_NOTIFY,
        cause_event_id=ws_accepted.transport_actor_event_id,
    )
    control_event = _prepare_control(events, operation)
    control = control_event.payload
    assert type(control) is TlsControlCiphertextPreparedPayloadV49E
    state, _ = _terminal(
        events,
        state,
        TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_PREPARED,
        layer=OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY,
        obligation_id=control_event.transport_actor_event_id,
    )
    state, _, _ = _send_control(
        events,
        state,
        control_event,
        requested_octets=control.ciphertext_octets - 1,
    )
    _terminal(
        events,
        state,
        TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_SENT,
        layer=OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY,
        obligation_id=control_event.transport_actor_event_id,
    )

    with pytest.raises(CanonicalizationError, match="full kernel acceptance"):
        validate_transport_actor_chain_v49c(events)


def test_local_close_notify_accepts_only_gap_free_multi_attempt_coverage() -> None:
    events, state, ws_accepted = _websocket_close_prefix()
    operation = _start_tls_operation(
        events,
        sequence=1,
        purpose=TlsProtocolOperationPurposeV49E.LOCAL_CLOSE_NOTIFY,
        cause_event_id=ws_accepted.transport_actor_event_id,
    )
    control_event = _prepare_control(events, operation)
    control = control_event.payload
    assert type(control) is TlsControlCiphertextPreparedPayloadV49E
    first_count = control.ciphertext_octets // 2
    state, _ = _terminal(
        events,
        state,
        TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_PREPARED,
        layer=OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY,
        obligation_id=control_event.transport_actor_event_id,
    )
    state, _, _ = _send_control(
        events,
        state,
        control_event,
        requested_octets=first_count,
    )
    state, _, _ = _send_control(
        events,
        state,
        control_event,
        start_octet=first_count,
        attempt_ordinal=2,
    )
    state, _ = _terminal(
        events,
        state,
        TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_SENT,
        layer=OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY,
        obligation_id=control_event.transport_actor_event_id,
    )
    state, _ = _terminal(
        events,
        state,
        TerminalTransitionKindV49C.OUTBOUND_OBLIGATION_FULLY_KERNEL_ACCEPTED,
        layer=OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY,
        obligation_id=control_event.transport_actor_event_id,
    )

    actor_state = validate_transport_actor_chain_v49c(events)
    assert actor_state.tls_close_notify_sent
    assert actor_state.tls_close_notify_fully_kernel_accepted
    assert actor_state.tls_send_attempts_resolved == 2
    assert actor_state == state


def test_tls_control_attempt_requires_exact_send_started_successor() -> None:
    events, _, control_event = _local_control_prepared_prefix()
    attempt_event = _append_control_attempt(events, control_event)
    _append_control_result(events, control_event, attempt_event)

    with pytest.raises(CanonicalizationError, match="SEND_ATTEMPT_STARTED next"):
        validate_transport_actor_chain_v49c(events)


def test_tls_control_result_requires_exact_send_resolved_successor() -> None:
    events, state, control_event = _local_control_prepared_prefix()
    attempt_event = _append_control_attempt(events, control_event)
    state, _ = _terminal(
        events,
        state,
        TerminalTransitionKindV49C.SEND_ATTEMPT_STARTED,
        layer=OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY,
        obligation_id=control_event.transport_actor_event_id,
        send_attempt_id=attempt_event.transport_actor_event_id,
    )
    result_event = _append_control_result(events, control_event, attempt_event)
    _start_tls_operation(
        events,
        sequence=2,
        purpose=TlsProtocolOperationPurposeV49E.OPAQUE_POST_HANDSHAKE_RESPONSE,
        cause_event_id=result_event.transport_actor_event_id,
    )

    with pytest.raises(CanonicalizationError, match="SEND_ATTEMPT_RESOLVED next"):
        validate_transport_actor_chain_v49c(events)
    assert state.has_pending_send_attempt


def test_unresolved_tls_control_send_uses_only_fixed_unknown_outcome() -> None:
    events, state, control_event = _local_control_prepared_prefix()
    attempt_event = _append_control_attempt(events, control_event)
    state, _ = _terminal(
        events,
        state,
        TerminalTransitionKindV49C.SEND_ATTEMPT_STARTED,
        layer=OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY,
        obligation_id=control_event.transport_actor_event_id,
        send_attempt_id=attempt_event.transport_actor_event_id,
    )
    state, _ = _terminal(
        events,
        state,
        TerminalTransitionKindV49C.UNKNOWN_SEND,
        layer=OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY,
        obligation_id=control_event.transport_actor_event_id,
        send_attempt_id=attempt_event.transport_actor_event_id,
        cause_code=V49E_TLS_CONTROL_SEND_OUTCOME_UNKNOWN_CAUSE,
    )

    actor_state = validate_transport_actor_chain_v49c(events)
    assert actor_state == state
    assert actor_state.terminal_outcome is TerminalOutcomeV49C.UNKNOWN_SEND
    assert (
        actor_state.terminal_cause_code == V49E_TLS_CONTROL_SEND_OUTCOME_UNKNOWN_CAUSE
    )

    bad_events, bad_state, bad_control = _local_control_prepared_prefix()
    bad_attempt = _append_control_attempt(bad_events, bad_control)
    bad_state, _ = _terminal(
        bad_events,
        bad_state,
        TerminalTransitionKindV49C.SEND_ATTEMPT_STARTED,
        layer=OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY,
        obligation_id=bad_control.transport_actor_event_id,
        send_attempt_id=bad_attempt.transport_actor_event_id,
    )
    _terminal(
        bad_events,
        bad_state,
        TerminalTransitionKindV49C.UNKNOWN_SEND,
        layer=OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY,
        obligation_id=bad_control.transport_actor_event_id,
        send_attempt_id=bad_attempt.transport_actor_event_id,
        cause_code="MUTATED_TLS_CONTROL_UNKNOWN_CAUSE",
    )
    with pytest.raises(CanonicalizationError, match="UNKNOWN_SEND"):
        validate_transport_actor_chain_v49c(bad_events)


def test_tls_operation_failures_have_fixed_terminal_mappings() -> None:
    cases = (
        (
            TlsProtocolOperationFailureKindV49E.DRIVER_ERROR,
            TerminalTransitionKindV49C.FATAL,
            V49E_TLS_OPERATION_DRIVER_ERROR_CAUSE,
            TerminalOutcomeV49C.FATAL,
        ),
        (
            TlsProtocolOperationFailureKindV49E.DEADLINE_EXPIRED_NO_OBSERVATION,
            TerminalTransitionKindV49C.TIMEOUT,
            V49E_TLS_SHUTDOWN_DEADLINE_EXPIRED_CAUSE,
            TerminalOutcomeV49C.TIMEOUT,
        ),
        (
            TlsProtocolOperationFailureKindV49E.UNSENDABLE_POST_HANDSHAKE_OUTPUT_AFTER_SHUT_WR,
            TerminalTransitionKindV49C.FATAL,
            V49E_TLS_POST_HANDSHAKE_OUTPUT_AFTER_SHUT_WR_CAUSE,
            TerminalOutcomeV49C.FATAL,
        ),
    )
    for failure_kind, terminal_kind, cause, outcome in cases:
        if failure_kind is TlsProtocolOperationFailureKindV49E.DRIVER_ERROR:
            events, state, cause_event = _websocket_close_prefix()
            purpose = TlsProtocolOperationPurposeV49E.LOCAL_CLOSE_NOTIFY
            operation_sequence = 1
        else:
            events, state, cause_event, _ = _local_tls_and_half_close_prefix()
            purpose = TlsProtocolOperationPurposeV49E.PEER_SHUTDOWN_POLL
            operation_sequence = 2
        operation = _start_tls_operation(
            events,
            sequence=operation_sequence,
            purpose=purpose,
            cause_event_id=cause_event.transport_actor_event_id,
        )
        _fail_tls_operation(events, operation, failure_kind)
        state, _ = _terminal(
            events,
            state,
            terminal_kind,
            cause_code=cause,
        )

        actor_state = validate_transport_actor_chain_v49c(events)
        assert actor_state == state
        assert actor_state.terminal_outcome is outcome
        assert actor_state.terminal_cause_code == cause


def test_tls_operation_failure_rejects_mutated_terminal_mapping() -> None:
    events, state, ws_accepted = _websocket_close_prefix()
    operation = _start_tls_operation(
        events,
        sequence=1,
        purpose=TlsProtocolOperationPurposeV49E.LOCAL_CLOSE_NOTIFY,
        cause_event_id=ws_accepted.transport_actor_event_id,
    )
    _fail_tls_operation(
        events,
        operation,
        TlsProtocolOperationFailureKindV49E.DRIVER_ERROR,
    )
    _terminal(
        events,
        state,
        TerminalTransitionKindV49C.TIMEOUT,
        cause_code=V49E_TLS_SHUTDOWN_DEADLINE_EXPIRED_CAUSE,
    )

    with pytest.raises(CanonicalizationError, match="fixed terminal outcome"):
        validate_transport_actor_chain_v49c(events)


def test_tcp_half_close_error_and_unknown_outcomes_are_fixed() -> None:
    events, state, tls_marker, control_event = _local_tls_accepted_prefix()
    attempt = _append_half_close_attempt(events, tls_marker, control_event)
    _append_half_close_result(
        events,
        attempt,
        result_kind=TcpHalfCloseResultKindV49E.ERROR,
    )
    state, _ = _terminal(
        events,
        state,
        TerminalTransitionKindV49C.FATAL,
        cause_code=V49E_TCP_HALF_CLOSE_ERROR_CAUSE,
    )
    actor_state = validate_transport_actor_chain_v49c(events)
    assert actor_state == state
    assert actor_state.terminal_cause_code == V49E_TCP_HALF_CLOSE_ERROR_CAUSE

    unknown_events, unknown_state, unknown_tls, unknown_control = (
        _local_tls_accepted_prefix()
    )
    _append_half_close_attempt(unknown_events, unknown_tls, unknown_control)
    unknown_state, _ = _terminal(
        unknown_events,
        unknown_state,
        TerminalTransitionKindV49C.FATAL,
        cause_code=V49E_TCP_HALF_CLOSE_OUTCOME_UNKNOWN_CAUSE,
    )
    unknown_actor_state = validate_transport_actor_chain_v49c(unknown_events)
    assert unknown_actor_state == unknown_state
    assert (
        unknown_actor_state.terminal_cause_code
        == V49E_TCP_HALF_CLOSE_OUTCOME_UNKNOWN_CAUSE
    )

    bad_events, bad_state, bad_tls, bad_control = _local_tls_accepted_prefix()
    bad_attempt = _append_half_close_attempt(bad_events, bad_tls, bad_control)
    _append_half_close_result(
        bad_events,
        bad_attempt,
        result_kind=TcpHalfCloseResultKindV49E.ERROR,
    )
    _terminal(
        bad_events,
        bad_state,
        TerminalTransitionKindV49C.FATAL,
        cause_code=V49E_TCP_HALF_CLOSE_OUTCOME_UNKNOWN_CAUSE,
    )
    with pytest.raises(CanonicalizationError, match="exact terminal outcome"):
        validate_transport_actor_chain_v49c(bad_events)


def test_tcp_half_close_actor_recomputes_owner_token_and_result_ids() -> None:
    assert socket.SHUT_WR == 1  # V4.9E pins the supported Linux ABI profile.
    token_events, _, token_tls, token_control = _local_tls_accepted_prefix()
    _append_half_close_attempt(
        token_events,
        token_tls,
        token_control,
        shutdown_token_id_override=_digest("forged-shutdown-token"),
    )
    with pytest.raises(CanonicalizationError, match="half-close attempt"):
        validate_transport_actor_chain_v49c(token_events)

    result_events, _, result_tls, result_control = _local_tls_accepted_prefix()
    result_attempt = _append_half_close_attempt(
        result_events,
        result_tls,
        result_control,
    )
    _append_half_close_result(
        result_events,
        result_attempt,
        result_kind=TcpHalfCloseResultKindV49E.KERNEL_ACCEPTED,
        shutdown_result_id_override=_digest("forged-shutdown-result"),
    )
    with pytest.raises(CanonicalizationError, match="differs from its exact"):
        validate_transport_actor_chain_v49c(result_events)


def test_opaque_post_handshake_output_cannot_mint_close_authority() -> None:
    events, state, ws_accepted = _websocket_close_prefix()
    operation = _start_tls_operation(
        events,
        sequence=1,
        purpose=TlsProtocolOperationPurposeV49E.OPAQUE_POST_HANDSHAKE_RESPONSE,
        cause_event_id=ws_accepted.transport_actor_event_id,
    )
    control_event = _prepare_control(
        events,
        operation,
        kind=TlsControlOutputKindV49E.OPAQUE_POST_HANDSHAKE_RESPONSE,
    )
    state, _, _ = _send_control(events, state, control_event)
    _terminal(
        events,
        state,
        TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_SENT,
        layer=OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY,
        obligation_id=control_event.transport_actor_event_id,
    )

    with pytest.raises(CanonicalizationError, match="full kernel acceptance"):
        validate_transport_actor_chain_v49c(events)


def test_peer_shutdown_poll_requires_successful_shut_wr_marker() -> None:
    events, state, ws_accepted = _websocket_close_prefix()
    operation = _start_tls_operation(
        events,
        sequence=1,
        purpose=TlsProtocolOperationPurposeV49E.LOCAL_CLOSE_NOTIFY,
        cause_event_id=ws_accepted.transport_actor_event_id,
    )
    control_event = _prepare_control(events, operation)
    state, _ = _terminal(
        events,
        state,
        TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_PREPARED,
        layer=OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY,
        obligation_id=control_event.transport_actor_event_id,
    )
    state, _, _ = _send_control(events, state, control_event)
    state, tls_marker = _terminal(
        events,
        state,
        TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_SENT,
        layer=OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY,
        obligation_id=control_event.transport_actor_event_id,
    )
    state, _ = _terminal(
        events,
        state,
        TerminalTransitionKindV49C.OUTBOUND_OBLIGATION_FULLY_KERNEL_ACCEPTED,
        layer=OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY,
        obligation_id=control_event.transport_actor_event_id,
    )
    _start_tls_operation(
        events,
        sequence=2,
        purpose=TlsProtocolOperationPurposeV49E.PEER_SHUTDOWN_POLL,
        cause_event_id=tls_marker.transport_actor_event_id,
    )

    with pytest.raises(CanonicalizationError, match="successful local SHUT_WR"):
        validate_transport_actor_chain_v49c(events)


def test_tcp_fin_marker_requires_exact_successful_half_close_result() -> None:
    events, state, fin_marker, _ = _local_tls_and_half_close_prefix()
    mapping = copy.deepcopy(events[-2].as_dict())
    assert mapping["event_kind"] == TransportActorEventKindV49C.TCP_HALF_CLOSE_RESULT
    mapping["payload"]["shutdown_token_id"] = _digest("forged-token")
    mapping["transport_actor_event_id"] = sha256_digest(
        {
            "canonicalization_version": mapping["canonicalization_version"],
            "domain": "RiskYieldMMTransportActorEventV4_9C",
            "payload": {
                key: value
                for key, value in mapping.items()
                if key
                not in {
                    "canonicalization_version",
                    "schema_version",
                    "transport_actor_event_id",
                }
            },
            "schema_version": mapping["schema_version"],
        }
    )
    forged_result = TransportActorEventV49C.from_mapping(mapping)
    events[-2] = forged_result
    fin_payload = fin_marker.payload
    assert type(fin_payload) is TerminalTransitionPayloadV49C
    events[-1] = TransportActorEventV49C.create(
        **AUTHORITY,
        recorded_at=fin_marker.recorded_at,
        recorded_monotonic_ns=fin_marker.recorded_monotonic_ns,
        actor_sequence=fin_marker.actor_sequence,
        previous_event_id=forged_result.transport_actor_event_id,
        event_kind=TransportActorEventKindV49C.TERMINAL_TRANSITION,
        payload=fin_payload,
    )

    with pytest.raises(CanonicalizationError, match="differs from its exact"):
        validate_transport_actor_chain_v49c(events)
    assert state.tcp_fin_sent


def test_tcp_eof_payload_requires_exact_owner_observation_identity() -> None:
    events, state, fin_marker, _ = _local_tls_and_half_close_prefix()
    state, peer_marker = _observe_shutdown(
        events,
        state,
        operation_sequence=2,
        observation_sequence=1,
        kind=TlsShutdownObservationKindV49E.PEER_CLOSE_NOTIFY,
        cause_event_id=fin_marker.transport_actor_event_id,
        peer_received=True,
    )
    operation = _start_tls_operation(
        events,
        sequence=3,
        purpose=TlsProtocolOperationPurposeV49E.PEER_SHUTDOWN_POLL,
        cause_event_id=peer_marker.transport_actor_event_id,
    )
    operation_payload = operation.payload
    assert type(operation_payload) is TlsProtocolOperationStartedPayloadV49E
    observation_id = sha256_digest(
        {
            "domain": "RiskYieldMMTlsShutdownObservationV4_9E",
            "observation_sequence": 2,
            "observation_kind": TlsShutdownObservationKindV49E.TCP_EOF.value,
            "driver_evidence_nonce_sha256": (
                operation_payload.driver_evidence_nonce_sha256
            ),
            "peer_close_notify_received": True,
            "tcp_eof_received": True,
            "truncated": False,
            "ciphertext_octets_received": 0,
        }
    )
    observed_at, observed_ns = _next_clock(events)
    _append(
        events,
        TransportActorEventKindV49C.TLS_SHUTDOWN_OBSERVED,
        TlsShutdownObservedPayloadV49E(
            tls_protocol_operation_started_event_id=(
                operation.transport_actor_event_id
            ),
            tls_operation_id=operation_payload.tls_operation_id,
            observation_sequence=2,
            observation_kind=TlsShutdownObservationKindV49E.TCP_EOF,
            driver_evidence_nonce_sha256=(
                operation_payload.driver_evidence_nonce_sha256
            ),
            peer_close_notify_received=True,
            tcp_eof_received=True,
            truncated=False,
            ciphertext_octets_received=0,
            observation_id=observation_id,
            owner_observation_id=_digest("forged-owner-observation"),
            owner_kernel_socket_identity=_digest("owner-kernel-socket"),
            observed_at=observed_at,
            observed_monotonic_ns=observed_ns,
        ),
    )

    with pytest.raises(CanonicalizationError, match="owner-derived identity"):
        validate_transport_actor_chain_v49c(events)


def test_shutdown_observations_cannot_change_owner_socket_identity() -> None:
    events, state, fin_marker, _ = _local_tls_and_half_close_prefix()
    _state, peer_marker = _observe_shutdown(
        events,
        state,
        operation_sequence=2,
        observation_sequence=1,
        kind=TlsShutdownObservationKindV49E.PEER_CLOSE_NOTIFY,
        cause_event_id=fin_marker.transport_actor_event_id,
        peer_received=True,
    )
    operation = _start_tls_operation(
        events,
        sequence=3,
        purpose=TlsProtocolOperationPurposeV49E.PEER_SHUTDOWN_POLL,
        cause_event_id=peer_marker.transport_actor_event_id,
    )
    operation_payload = operation.payload
    assert type(operation_payload) is TlsProtocolOperationStartedPayloadV49E
    observation_id = sha256_digest(
        {
            "domain": "RiskYieldMMTlsShutdownObservationV4_9E",
            "observation_sequence": 2,
            "observation_kind": TlsShutdownObservationKindV49E.TCP_EOF.value,
            "driver_evidence_nonce_sha256": (
                operation_payload.driver_evidence_nonce_sha256
            ),
            "peer_close_notify_received": True,
            "tcp_eof_received": True,
            "truncated": False,
            "ciphertext_octets_received": 0,
        }
    )
    replacement_socket_identity = _digest("replacement-owner-kernel-socket")
    owner_observation_id = sha256_digest(
        {
            "domain": "RiskYieldMMOwnerTlsShutdownObservationV4_9E",
            "transport_session_id": AUTHORITY["transport_session_id"],
            "kernel_socket_identity": replacement_socket_identity,
            "driver_observation_id": observation_id,
            "driver_observation_sequence": 2,
            "driver_observation_kind": TlsShutdownObservationKindV49E.TCP_EOF.value,
        }
    )
    observed_at, observed_ns = _next_clock(events)
    _append(
        events,
        TransportActorEventKindV49C.TLS_SHUTDOWN_OBSERVED,
        TlsShutdownObservedPayloadV49E(
            tls_protocol_operation_started_event_id=(
                operation.transport_actor_event_id
            ),
            tls_operation_id=operation_payload.tls_operation_id,
            observation_sequence=2,
            observation_kind=TlsShutdownObservationKindV49E.TCP_EOF,
            driver_evidence_nonce_sha256=(
                operation_payload.driver_evidence_nonce_sha256
            ),
            peer_close_notify_received=True,
            tcp_eof_received=True,
            truncated=False,
            ciphertext_octets_received=0,
            observation_id=observation_id,
            owner_observation_id=owner_observation_id,
            owner_kernel_socket_identity=replacement_socket_identity,
            observed_at=observed_at,
            observed_monotonic_ns=observed_ns,
        ),
    )

    with pytest.raises(CanonicalizationError, match="retained owner socket"):
        validate_transport_actor_chain_v49c(events)


def test_shutdown_payload_recomputes_exact_driver_observation_identity() -> None:
    events, state, fin_marker, _ = _local_tls_and_half_close_prefix()
    _observe_shutdown(
        events,
        state,
        operation_sequence=2,
        observation_sequence=1,
        kind=TlsShutdownObservationKindV49E.PEER_CLOSE_NOTIFY,
        cause_event_id=fin_marker.transport_actor_event_id,
        peer_received=True,
    )
    observed_index = next(
        index
        for index, event in enumerate(events)
        if event.event_kind is TransportActorEventKindV49C.TLS_SHUTDOWN_OBSERVED
    )
    observed_mapping = copy.deepcopy(events[observed_index].as_dict())
    observed_mapping["payload"]["ciphertext_octets_received"] += 1
    observed_mapping["transport_actor_event_id"] = sha256_digest(
        {
            "canonicalization_version": observed_mapping["canonicalization_version"],
            "domain": "RiskYieldMMTransportActorEventV4_9C",
            "payload": {
                key: value
                for key, value in observed_mapping.items()
                if key
                not in {
                    "canonicalization_version",
                    "schema_version",
                    "transport_actor_event_id",
                }
            },
            "schema_version": observed_mapping["schema_version"],
        }
    )
    forged_observation = TransportActorEventV49C.from_mapping(observed_mapping)
    events[observed_index] = forged_observation
    successor = events[observed_index + 1]
    events[observed_index + 1] = TransportActorEventV49C.create(
        **AUTHORITY,
        recorded_at=successor.recorded_at,
        recorded_monotonic_ns=successor.recorded_monotonic_ns,
        actor_sequence=successor.actor_sequence,
        previous_event_id=forged_observation.transport_actor_event_id,
        event_kind=successor.event_kind,
        payload=successor.payload,
    )

    with pytest.raises(CanonicalizationError, match="driver-derived identity"):
        validate_transport_actor_chain_v49c(events)


def test_recomputed_shutdown_hashes_cannot_rewrite_committed_chain_link() -> None:
    events, state, fin_marker, _ = _local_tls_and_half_close_prefix()
    _observe_shutdown(
        events,
        state,
        operation_sequence=2,
        observation_sequence=1,
        kind=TlsShutdownObservationKindV49E.PEER_CLOSE_NOTIFY,
        cause_event_id=fin_marker.transport_actor_event_id,
        peer_received=True,
    )
    observed_index = next(
        index
        for index, event in enumerate(events)
        if event.event_kind is TransportActorEventKindV49C.TLS_SHUTDOWN_OBSERVED
    )
    observed_mapping = copy.deepcopy(events[observed_index].as_dict())
    payload = observed_mapping["payload"]
    payload["ciphertext_octets_received"] += 1
    payload["observation_id"] = sha256_digest(
        {
            "domain": "RiskYieldMMTlsShutdownObservationV4_9E",
            "observation_sequence": payload["observation_sequence"],
            "observation_kind": payload["observation_kind"],
            "driver_evidence_nonce_sha256": (payload["driver_evidence_nonce_sha256"]),
            "peer_close_notify_received": payload["peer_close_notify_received"],
            "tcp_eof_received": payload["tcp_eof_received"],
            "truncated": payload["truncated"],
            "ciphertext_octets_received": payload["ciphertext_octets_received"],
        }
    )
    payload["owner_observation_id"] = sha256_digest(
        {
            "domain": "RiskYieldMMOwnerTlsShutdownObservationV4_9E",
            "transport_session_id": AUTHORITY["transport_session_id"],
            "kernel_socket_identity": payload["owner_kernel_socket_identity"],
            "driver_observation_id": payload["observation_id"],
            "driver_observation_sequence": payload["observation_sequence"],
            "driver_observation_kind": payload["observation_kind"],
        }
    )
    observed_mapping["transport_actor_event_id"] = sha256_digest(
        {
            "canonicalization_version": observed_mapping["canonicalization_version"],
            "domain": "RiskYieldMMTransportActorEventV4_9C",
            "payload": {
                key: value
                for key, value in observed_mapping.items()
                if key
                not in {
                    "canonicalization_version",
                    "schema_version",
                    "transport_actor_event_id",
                }
            },
            "schema_version": observed_mapping["schema_version"],
        }
    )
    events[observed_index] = TransportActorEventV49C.from_mapping(observed_mapping)

    with pytest.raises(
        CanonicalizationError,
        match="actor sequence or predecessor chain is broken",
    ):
        validate_transport_actor_chain_v49c(events)

from __future__ import annotations

import base64
import copy
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from riskyieldmm.trading.canonical import CanonicalizationError, sha256_digest
from riskyieldmm.trading.physical_market_data import MessageDispositionKind
from riskyieldmm.trading.physical_projection_v4 import (
    PhysicalProjectionReceiptV4,
    PhysicalRecordKindV4,
)
from riskyieldmm.trading.physical_transport_actor_v49c import (
    V49E_WEBSOCKET_CLOSE_DEADLINE_EXPIRED_CAUSE,
    AckDeadlineExpiredPayloadV49E,
    ApplicationMessageCommittedPayloadV49E,
    CommittedRawChunkV49C,
    CommittedRawIngressV49C,
    DelineatedServerFrameV49C,
    FrameDelineationErrorV49C,
    KernelSendAttemptPayloadV49C,
    KernelSendResultPayloadV49C,
    LocalShutdownCommandStartedPayloadV49E,
    OutboundDispatchCompletedPayloadV49C,
    OutboundDispatchDispositionV49C,
    OutboundWireOriginV49C,
    OutboundWirePreparedPayloadV49C,
    ParserErrorKindV49C,
    ParserFeedUnitKindV49C,
    ParserTransitionPayloadV49C,
    RawIngressCommittedPayloadV49C,
    RetainedIngressTailV49C,
    SubscriptionAckBoundPayloadV49E,
    TerminalTransitionPayloadV49C,
    TlsCiphertextPreparedPayloadV49C,
    TransportActorEventKindV49C,
    TransportActorEventV49C,
    WebSocketOpcodeV49C,
    WebSocketParserCursorV49C,
    WebSocketParserStateV49C,
    WritePermitConsumedPayloadV49C,
    delineate_next_server_frame_v49c,
    derive_actor_write_permit_id_v49c,
    derive_local_shutdown_command_id_v49e,
    derive_local_terminal_command_operation_id_v49e,
    validate_transport_actor_chain_v49c,
)
from riskyieldmm.trading.physical_transport_terminal_v49c import (
    OutboundObligationLayerV49C,
    TerminalTransitionKindV49C,
    advance_terminal_state_v49c,
    initial_terminal_state_v49c,
)

UTC = timezone.utc
T0 = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _encoded_chunks(
    chunks: tuple[bytes, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    return (
        tuple(base64.b64encode(chunk).decode("ascii") for chunk in chunks),
        tuple(hashlib.sha256(chunk).hexdigest() for chunk in chunks),
    )


def _ordered_batch(domain: str, encoded: tuple[str, ...]) -> str:
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


def _actor_event(
    *,
    kind: TransportActorEventKindV49C,
    payload: Any,
    sequence: int,
    previous_event_id: str | None,
) -> TransportActorEventV49C:
    if type(payload) is RawIngressCommittedPayloadV49C:
        recorded_at = payload.received_at
        recorded_monotonic_ns = payload.received_monotonic_ns
    else:
        recorded_at = T0 + timedelta(seconds=10 * sequence)
        recorded_monotonic_ns = 1_000 * sequence
    return TransportActorEventV49C.create(
        **AUTHORITY,
        recorded_at=recorded_at,
        recorded_monotonic_ns=recorded_monotonic_ns,
        actor_sequence=sequence,
        previous_event_id=previous_event_id,
        event_kind=kind,
        payload=payload,
    )


def _append_event(
    events: list[TransportActorEventV49C],
    kind: TransportActorEventKindV49C,
    payload: Any,
) -> TransportActorEventV49C:
    event = _actor_event(
        kind=kind,
        payload=payload,
        sequence=len(events) + 1,
        previous_event_id=(None if not events else events[-1].transport_actor_event_id),
    )
    events.append(event)
    return event


def _projection_receipt(
    raw_id: str,
    *,
    ledger_id: str,
    sequence: int = 1,
    committed_at: datetime = T0 + timedelta(seconds=1),
) -> PhysicalProjectionReceiptV4:
    previous_receipt_hash = _digest(f"receipt-{sequence - 1}")
    content_hash = _digest(f"raw-content-{sequence}")
    receipt_hash = sha256_digest(
        {
            "content_hash": content_hash,
            "domain": "RiskYieldMMPhysicalProjectionReceiptV4",
            "global_sequence": sequence,
            "identity_id": raw_id,
            "ledger_id": ledger_id,
            "previous_receipt_hash": previous_receipt_hash,
            "record_kind": PhysicalRecordKindV4.RAW_INGRESS_COMMIT.value,
        }
    )
    return PhysicalProjectionReceiptV4(
        global_sequence=sequence,
        receipt_hash=receipt_hash,
        previous_receipt_hash=previous_receipt_hash,
        record_kind=PhysicalRecordKindV4.RAW_INGRESS_COMMIT,
        identity_id=raw_id,
        content_hash=content_hash,
        committed_at=committed_at,
    )


def _raw_payload(
    data: bytes,
    *,
    raw_id: str | None = None,
    ingress_sequence: int = 1,
    previous_raw_id: str | None = None,
    stream_start: int = 0,
    receipt_sequence: int = 1,
    received_at: datetime = T0,
    received_monotonic_ns: int = 10,
) -> RawIngressCommittedPayloadV49C:
    identity = _digest("raw-1") if raw_id is None else raw_id
    ledger_id = _digest("projection-ledger")
    receipt = CommittedRawIngressV49C.from_projection_receipt(
        ledger_id=ledger_id,
        receipt=_projection_receipt(
            identity,
            ledger_id=ledger_id,
            sequence=receipt_sequence,
            committed_at=received_at + timedelta(milliseconds=1),
        ),
    )
    chunk_hash = hashlib.sha256(data).hexdigest()
    raw_batch_hash = sha256_digest(
        {
            "domain": "RiskYieldMMExactOrderedDecryptedIngressChunksV4_5",
            "ordered_chunks_base64": [base64.b64encode(data).decode("ascii")],
        }
    )
    return RawIngressCommittedPayloadV49C(
        raw_ingress_commit_id=identity,
        receipt=receipt,
        ingress_sequence=ingress_sequence,
        previous_raw_ingress_commit_id=previous_raw_id,
        stream_start_octet=stream_start,
        stream_end_octet=stream_start + len(data),
        ordered_chunk_octet_lengths=(len(data),),
        ordered_chunk_sha256=(chunk_hash,),
        raw_ingress_batch_sha256=raw_batch_hash,
        received_at=received_at,
        received_monotonic_ns=received_monotonic_ns,
    )


def _chunk(
    data: bytes,
    *,
    stream_start: int,
    raw_label: str,
    receipt_sequence: int,
    raw_local_start: int = 0,
) -> CommittedRawChunkV49C:
    return CommittedRawChunkV49C(
        raw_ingress_commit_id=_digest(raw_label),
        projection_receipt_sequence=receipt_sequence,
        projection_receipt_hash=_digest(f"{raw_label}-receipt"),
        raw_local_start_octet=raw_local_start,
        stream_start_octet=stream_start,
        data=data,
    )


def _wire_payload(
    label: str, *, prepared_ns: int = 100
) -> OutboundWirePreparedPayloadV49C:
    payload = label.encode()
    mask = b"\x01\x02\x03\x04"
    masked = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
    wire = b"\x81" + bytes((0x80 | len(payload),)) + mask + masked
    encoded, hashes = _encoded_chunks((wire,))
    return OutboundWirePreparedPayloadV49C(
        outbound_operation_id=_digest(f"operation-{label}"),
        wire_origin=OutboundWireOriginV49C.APPLICATION_INTENT,
        source_parser_event_id=None,
        logical_opcode=WebSocketOpcodeV49C.TEXT,
        logical_payload_sha256=hashlib.sha256(payload).hexdigest(),
        logical_payload_octets=len(payload),
        ordered_wire_chunks_base64=encoded,
        ordered_wire_chunks_sha256=hashes,
        wire_batch_sha256=_ordered_batch(
            "RiskYieldMMActorOrderedProtocolOutputV4_9C", encoded
        ),
        wire_octets=len(wire),
        prepared_at=T0,
        prepared_monotonic_ns=prepared_ns,
        send_not_after=T0 + timedelta(minutes=1),
        send_not_after_monotonic_ns=10_000,
    )


def _local_terminal_wire_payload(
    events: list[TransportActorEventV49C],
    *,
    mask: bytes = b"\x05\x06\x07\x08",
    logical_payload: bytes = b"\x03\xe8",
    opcode: WebSocketOpcodeV49C = WebSocketOpcodeV49C.CLOSE,
    origin: OutboundWireOriginV49C = (OutboundWireOriginV49C.LOCAL_TERMINAL_COMMAND),
    source_parser_event_id: str | None = None,
    outbound_operation_id: str | None = None,
    send_not_after_monotonic_ns: int = 10_000,
) -> OutboundWirePreparedPayloadV49C:
    opcode_number = {
        WebSocketOpcodeV49C.TEXT: 0x1,
        WebSocketOpcodeV49C.CLOSE: 0x8,
    }[opcode]
    masked = bytes(
        value ^ mask[index % 4] for index, value in enumerate(logical_payload)
    )
    wire = bytes((0x80 | opcode_number, 0x80 | len(logical_payload))) + mask + masked
    encoded, hashes = _encoded_chunks((wire,))
    predecessor = None if not events else events[-1].transport_actor_event_id
    wire_batch_sha256 = _ordered_batch(
        "RiskYieldMMActorOrderedProtocolOutputV4_9C", encoded
    )
    command = (
        events[-1].payload
        if events and type(events[-1].payload) is LocalShutdownCommandStartedPayloadV49E
        else None
    )
    operation_id = outbound_operation_id
    if operation_id is None:
        operation_id = derive_local_terminal_command_operation_id_v49e(
            transport_session_id=AUTHORITY["transport_session_id"],
            actor_predecessor_event_id=predecessor,
            logical_payload_sha256=hashlib.sha256(logical_payload).hexdigest(),
            logical_payload_octets=len(logical_payload),
            ordered_wire_chunks_sha256=hashes,
            wire_batch_sha256=wire_batch_sha256,
            wire_octets=len(wire),
        )
    return OutboundWirePreparedPayloadV49C(
        outbound_operation_id=operation_id,
        wire_origin=origin,
        source_parser_event_id=source_parser_event_id,
        logical_opcode=opcode,
        logical_payload_sha256=hashlib.sha256(logical_payload).hexdigest(),
        logical_payload_octets=len(logical_payload),
        ordered_wire_chunks_base64=encoded,
        ordered_wire_chunks_sha256=hashes,
        wire_batch_sha256=wire_batch_sha256,
        wire_octets=len(wire),
        prepared_at=(
            T0 if command is None else command.started_at + timedelta(microseconds=1)
        ),
        prepared_monotonic_ns=(
            100 if command is None else command.started_monotonic_ns + 1
        ),
        send_not_after=(
            T0 + timedelta(minutes=1)
            if command is None
            else command.shutdown_deadline_at
        ),
        send_not_after_monotonic_ns=(
            send_not_after_monotonic_ns
            if command is None
            else command.shutdown_deadline_monotonic_ns
        ),
    )


def _append_local_shutdown_command(
    events: list[TransportActorEventV49C],
    *,
    timeout_seconds: int = 60,
) -> TransportActorEventV49C:
    sequence = len(events) + 1
    started_at = T0 + timedelta(seconds=10 * sequence)
    started_ns = 1_000 * sequence
    deadline_at = started_at + timedelta(seconds=timeout_seconds)
    deadline_ns = started_ns + timeout_seconds * 1_000_000_000
    predecessor = None if not events else events[-1].transport_actor_event_id
    payload = LocalShutdownCommandStartedPayloadV49E(
        local_shutdown_command_id=derive_local_shutdown_command_id_v49e(
            transport_session_id=AUTHORITY["transport_session_id"],
            actor_predecessor_event_id=predecessor,
            timeout_seconds=timeout_seconds,
            started_at=started_at,
            started_monotonic_ns=started_ns,
            deadline_at=deadline_at,
            deadline_monotonic_ns=deadline_ns,
        ),
        websocket_close_code=1000,
        websocket_close_reason_sha256=hashlib.sha256(b"").hexdigest(),
        websocket_close_reason_octets=0,
        websocket_close_payload_sha256=hashlib.sha256(
            (1000).to_bytes(2, "big")
        ).hexdigest(),
        websocket_close_payload_octets=2,
        timeout_seconds=timeout_seconds,
        started_at=started_at,
        started_monotonic_ns=started_ns,
        shutdown_deadline_at=deadline_at,
        shutdown_deadline_monotonic_ns=deadline_ns,
    )
    return _append_event(
        events,
        TransportActorEventKindV49C.LOCAL_SHUTDOWN_COMMAND_STARTED,
        payload,
    )


def _masked_client_text_frame(
    payload: bytes,
    *,
    first_octet: int = 0x81,
    mask: bytes = b"\x01\x02\x03\x04",
) -> bytes:
    assert len(payload) < 126
    masked = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
    return bytes((first_octet, 0x80 | len(payload))) + mask + masked


def _masked_client_control_frame(
    opcode: WebSocketOpcodeV49C,
    payload: bytes,
    *,
    mask: bytes = b"\x01\x02\x03\x04",
) -> bytes:
    opcode_number = {
        WebSocketOpcodeV49C.CLOSE: 0x8,
        WebSocketOpcodeV49C.PONG: 0xA,
    }[opcode]
    assert len(mask) == 4
    assert len(payload) <= 125
    masked = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
    return bytes((0x80 | opcode_number, 0x80 | len(payload))) + mask + masked


def _parser_payload_for_raw(
    raw: RawIngressCommittedPayloadV49C,
    inbound_frame: bytes,
    *,
    cursor_sequence: int,
    protocol_output_chunks: tuple[bytes, ...],
) -> ParserTransitionPayloadV49C:
    delineated = delineate_next_server_frame_v49c(
        prior_tail=RetainedIngressTailV49C(),
        committed_raw_chunks=(
            CommittedRawChunkV49C(
                raw_ingress_commit_id=raw.raw_ingress_commit_id,
                projection_receipt_sequence=raw.receipt.global_sequence,
                projection_receipt_hash=raw.receipt.receipt_hash,
                raw_local_start_octet=0,
                stream_start_octet=raw.stream_start_octet,
                data=inbound_frame,
            ),
        ),
    )
    assert type(delineated.unit) is DelineatedServerFrameV49C
    encoded, hashes = _encoded_chunks(protocol_output_chunks)
    return ParserTransitionPayloadV49C(
        cursor_before=WebSocketParserCursorV49C(
            cursor_sequence=cursor_sequence,
            next_stream_octet=raw.stream_start_octet,
            websocket_state=WebSocketParserStateV49C.OPEN,
        ),
        cursor_after=WebSocketParserCursorV49C(
            cursor_sequence=cursor_sequence + 1,
            next_stream_octet=raw.stream_end_octet,
            websocket_state=WebSocketParserStateV49C.OPEN,
        ),
        feed_unit_kind=ParserFeedUnitKindV49C.COMPLETE_FRAME,
        source_slices=delineated.unit.source_slices,
        frame=delineated.unit.metadata,
        parser_error=None,
        ordered_protocol_output_chunks_base64=encoded,
        ordered_protocol_output_chunks_sha256=hashes,
        protocol_output_batch_sha256=(
            None
            if not encoded
            else _ordered_batch("RiskYieldMMActorOrderedProtocolOutputV4_9C", encoded)
        ),
        send_eof_after_output=False,
        processed_at=raw.receipt.committed_at + timedelta(milliseconds=1),
        processed_monotonic_ns=raw.received_monotonic_ns + 10,
    )


def _automatic_wire_payload(
    parser_event: TransportActorEventV49C,
    *,
    label: str,
    wire_chunks: tuple[bytes, ...],
    logical_opcode: WebSocketOpcodeV49C,
    logical_payload: bytes,
) -> OutboundWirePreparedPayloadV49C:
    parser = parser_event.payload
    assert type(parser) is ParserTransitionPayloadV49C
    encoded, hashes = _encoded_chunks(wire_chunks)
    return OutboundWirePreparedPayloadV49C(
        outbound_operation_id=_digest(f"automatic-operation-{label}"),
        wire_origin=OutboundWireOriginV49C.AUTOMATIC_PROTOCOL,
        source_parser_event_id=parser_event.transport_actor_event_id,
        logical_opcode=logical_opcode,
        logical_payload_sha256=hashlib.sha256(logical_payload).hexdigest(),
        logical_payload_octets=len(logical_payload),
        ordered_wire_chunks_base64=encoded,
        ordered_wire_chunks_sha256=hashes,
        wire_batch_sha256=_ordered_batch(
            "RiskYieldMMActorOrderedProtocolOutputV4_9C", encoded
        ),
        wire_octets=sum(map(len, wire_chunks)),
        prepared_at=parser.processed_at + timedelta(milliseconds=1),
        prepared_monotonic_ns=parser.processed_monotonic_ns + 100,
        send_not_after=parser.processed_at + timedelta(minutes=1),
        send_not_after_monotonic_ns=parser.processed_monotonic_ns + 10_000,
    )


def _automatic_output_prefix(
    *, payload: bytes = b"x", split_output: bool = False
) -> tuple[
    list[TransportActorEventV49C],
    TransportActorEventV49C,
    tuple[bytes, ...],
]:
    inbound = b"\x89" + bytes((len(payload),)) + payload
    outbound = _masked_client_control_frame(WebSocketOpcodeV49C.PONG, payload)
    output_chunks = (outbound[:3], outbound[3:]) if split_output else (outbound,)
    raw = _raw_payload(inbound)
    events: list[TransportActorEventV49C] = []
    _append_event(events, TransportActorEventKindV49C.RAW_INGRESS_COMMITTED, raw)
    parser_event = _append_event(
        events,
        TransportActorEventKindV49C.PARSER_TRANSITION,
        _parser_payload_for_raw(
            raw,
            inbound,
            cursor_sequence=0,
            protocol_output_chunks=output_chunks,
        ),
    )
    return events, parser_event, output_chunks


def _permit_payload(
    wire_event: TransportActorEventV49C,
    *,
    consumed_ns: int = 200,
) -> WritePermitConsumedPayloadV49C:
    wire = wire_event.payload
    assert type(wire) is OutboundWirePreparedPayloadV49C
    return WritePermitConsumedPayloadV49C(
        outbound_wire_prepared_event_id=wire_event.transport_actor_event_id,
        permit_id=derive_actor_write_permit_id_v49c(
            outbound_operation_id=wire.outbound_operation_id,
            outbound_wire_prepared_event_id=(wire_event.transport_actor_event_id),
            socket_lease_id=wire_event.socket_lease_id,
            writer_fence_token_sha256=wire_event.writer_fence_token_sha256,
            writer_fence_generation=wire_event.writer_fence_generation,
        ),
        one_shot_attempt_ordinal=1,
        wire_batch_sha256=wire.wire_batch_sha256,
        wire_octets=wire.wire_octets,
        consumed_at=T0 + timedelta(seconds=1),
        consumed_monotonic_ns=consumed_ns,
        send_not_after=wire.send_not_after,
        send_not_after_monotonic_ns=wire.send_not_after_monotonic_ns,
    )


def _tls_payload(
    wire_event: TransportActorEventV49C,
    permit_event: TransportActorEventV49C,
    *,
    prepared_ns: int = 300,
) -> TlsCiphertextPreparedPayloadV49C:
    wire = wire_event.payload
    assert type(wire) is OutboundWirePreparedPayloadV49C
    ciphertext = b"tls-ciphertext"
    encoded, hashes = _encoded_chunks((ciphertext,))
    return TlsCiphertextPreparedPayloadV49C(
        outbound_wire_prepared_event_id=wire_event.transport_actor_event_id,
        write_permit_consumed_event_id=permit_event.transport_actor_event_id,
        plaintext_batch_sha256=wire.wire_batch_sha256,
        plaintext_octets=wire.wire_octets,
        ordered_ciphertext_chunks_base64=encoded,
        ordered_ciphertext_chunks_sha256=hashes,
        ciphertext_batch_sha256=_ordered_batch(
            "RiskYieldMMActorOrderedTlsCiphertextV4_9C", encoded
        ),
        ciphertext_octets=len(ciphertext),
        prepared_at=T0 + timedelta(seconds=2),
        prepared_monotonic_ns=prepared_ns,
    )


def _attempt_payload(
    tls_event: TransportActorEventV49C,
    *,
    attempted_ns: int = 400,
) -> KernelSendAttemptPayloadV49C:
    tls = tls_event.payload
    assert type(tls) is TlsCiphertextPreparedPayloadV49C
    return KernelSendAttemptPayloadV49C(
        tls_ciphertext_prepared_event_id=tls_event.transport_actor_event_id,
        kernel_attempt_ordinal=1,
        ciphertext_batch_sha256=tls.ciphertext_batch_sha256,
        ciphertext_octets=tls.ciphertext_octets,
        ciphertext_start_octet=0,
        requested_octets=tls.ciphertext_octets,
        attempted_at=T0 + timedelta(seconds=3),
        attempted_monotonic_ns=attempted_ns,
    )


def _result_payload(
    attempt_event: TransportActorEventV49C,
    *,
    observed_ns: int = 500,
) -> KernelSendResultPayloadV49C:
    attempt = attempt_event.payload
    assert type(attempt) is KernelSendAttemptPayloadV49C
    return KernelSendResultPayloadV49C(
        kernel_send_attempt_event_id=attempt_event.transport_actor_event_id,
        tls_ciphertext_prepared_event_id=attempt.tls_ciphertext_prepared_event_id,
        kernel_attempt_ordinal=attempt.kernel_attempt_ordinal,
        ciphertext_batch_sha256=attempt.ciphertext_batch_sha256,
        ciphertext_octets=attempt.ciphertext_octets,
        ciphertext_start_octet=attempt.ciphertext_start_octet,
        requested_octets=attempt.requested_octets,
        accepted_octets=attempt.requested_octets,
        resulting_ciphertext_offset=attempt.requested_octets,
        observed_at=T0 + timedelta(seconds=4),
        observed_monotonic_ns=observed_ns,
    )


def _valid_outbound_chain() -> list[TransportActorEventV49C]:
    events: list[TransportActorEventV49C] = []
    wire = _append_event(
        events, TransportActorEventKindV49C.OUTBOUND_WIRE_PREPARED, _wire_payload("a")
    )
    permit = _append_event(
        events, TransportActorEventKindV49C.WRITE_PERMIT_CONSUMED, _permit_payload(wire)
    )
    tls = _append_event(
        events,
        TransportActorEventKindV49C.TLS_CIPHERTEXT_PREPARED,
        _tls_payload(wire, permit),
    )
    attempt = _append_event(
        events,
        TransportActorEventKindV49C.KERNEL_SEND_ATTEMPT,
        _attempt_payload(tls),
    )
    terminal_state = initial_terminal_state_v49c(AUTHORITY["transport_session_id"])
    started = TerminalTransitionPayloadV49C(
        transport_session_id=AUTHORITY["transport_session_id"],
        transition_sequence=1,
        parent_terminal_state_id=terminal_state.terminal_state_id,
        kind=TerminalTransitionKindV49C.SEND_ATTEMPT_STARTED,
        obligation_layer=OutboundObligationLayerV49C.APPLICATION_DATA,
        obligation_id=wire.payload.outbound_operation_id,
        send_attempt_id=attempt.transport_actor_event_id,
    )
    _append_event(events, TransportActorEventKindV49C.TERMINAL_TRANSITION, started)
    terminal_state = advance_terminal_state_v49c(terminal_state, started)
    result = _append_event(
        events,
        TransportActorEventKindV49C.KERNEL_SEND_RESULT,
        _result_payload(attempt),
    )
    resolved = TerminalTransitionPayloadV49C(
        transport_session_id=AUTHORITY["transport_session_id"],
        transition_sequence=2,
        parent_terminal_state_id=terminal_state.terminal_state_id,
        kind=TerminalTransitionKindV49C.SEND_ATTEMPT_RESOLVED,
        obligation_layer=OutboundObligationLayerV49C.APPLICATION_DATA,
        obligation_id=wire.payload.outbound_operation_id,
        send_attempt_id=attempt.transport_actor_event_id,
    )
    _append_event(events, TransportActorEventKindV49C.TERMINAL_TRANSITION, resolved)
    tls_payload = tls.payload
    assert type(tls_payload) is TlsCiphertextPreparedPayloadV49C
    dispatch = OutboundDispatchCompletedPayloadV49C(
        outbound_wire_prepared_event_id=wire.transport_actor_event_id,
        write_permit_consumed_event_id=permit.transport_actor_event_id,
        tls_ciphertext_prepared_event_id=tls.transport_actor_event_id,
        kernel_send_result_event_ids=(result.transport_actor_event_id,),
        ciphertext_batch_sha256=tls_payload.ciphertext_batch_sha256,
        ciphertext_octets=tls_payload.ciphertext_octets,
        submitted_ciphertext_octets=tls_payload.ciphertext_octets,
        disposition=OutboundDispatchDispositionV49C.COMPLETE_LOCAL_SUBMISSION,
        completed_at=T0 + timedelta(seconds=5),
        completed_monotonic_ns=600,
    )
    _append_event(
        events, TransportActorEventKindV49C.OUTBOUND_DISPATCH_COMPLETED, dispatch
    )
    return events


def _append_ack_application_message(
    events: list[TransportActorEventV49C],
) -> TransportActorEventV49C:
    frame = b"\x81\x03ack"
    raw = _raw_payload(
        frame,
        raw_id=_digest("ack-raw"),
        received_at=T0 + timedelta(seconds=90),
        received_monotonic_ns=9_000,
    )
    _append_event(events, TransportActorEventKindV49C.RAW_INGRESS_COMMITTED, raw)
    parser_event = _append_event(
        events,
        TransportActorEventKindV49C.PARSER_TRANSITION,
        _parser_payload_for_raw(
            raw,
            frame,
            cursor_sequence=0,
            protocol_output_chunks=(),
        ),
    )
    return _append_event(
        events,
        TransportActorEventKindV49C.APPLICATION_MESSAGE_COMMITTED,
        ApplicationMessageCommittedPayloadV49E(
            source_parser_event_ids=(parser_event.transport_actor_event_id,),
            message_opcode=WebSocketOpcodeV49C.TEXT,
            message_payload_octets=3,
            message_payload_sha256=hashlib.sha256(b"ack").hexdigest(),
            capture_segment_id=_digest("ack-capture"),
            message_receipt_id=_digest("ack-receipt"),
            physical_message_id=_digest("ack-message"),
            provider_message_disposition_id=_digest("ack-provider-disposition"),
            message_disposition_id=_digest("ack-v4-disposition"),
            disposition_kind=MessageDispositionKind.CONTROL_SUBSCRIPTION_ACK,
            received_at=T0 + timedelta(seconds=91),
            received_monotonic_ns=9_020,
            classified_at=T0 + timedelta(seconds=101),
            classified_monotonic_ns=10_020,
        ),
    )


def _ack_payload_for_prefix(
    events: list[TransportActorEventV49C],
    application_event: TransportActorEventV49C,
) -> SubscriptionAckBoundPayloadV49E:
    wire_event = next(
        event
        for event in events
        if event.event_kind is TransportActorEventKindV49C.OUTBOUND_WIRE_PREPARED
    )
    attempt_event = next(
        event
        for event in events
        if event.event_kind is TransportActorEventKindV49C.KERNEL_SEND_ATTEMPT
    )
    dispatch_event = next(
        event
        for event in events
        if event.event_kind is TransportActorEventKindV49C.OUTBOUND_DISPATCH_COMPLETED
    )
    wire = wire_event.payload
    attempt = attempt_event.payload
    dispatch = dispatch_event.payload
    application = application_event.payload
    assert type(wire) is OutboundWirePreparedPayloadV49C
    assert type(attempt) is KernelSendAttemptPayloadV49C
    assert type(dispatch) is OutboundDispatchCompletedPayloadV49C
    assert type(application) is ApplicationMessageCommittedPayloadV49E
    return SubscriptionAckBoundPayloadV49E(
        source_application_message_event_id=(
            application_event.transport_actor_event_id
        ),
        outbound_subscription_intent_id=wire.outbound_operation_id,
        subscription_dispatch_completed_event_id=(
            dispatch_event.transport_actor_event_id
        ),
        subscription_ack_binding_id=_digest("ack-binding"),
        provider_message_disposition_id=(application.provider_message_disposition_id),
        message_disposition_id=application.message_disposition_id,
        echoed_request_id="req-1",
        provider_connection_id="conn-1",
        request_command_sha256=wire.logical_payload_sha256,
        raw_ack_sha256=application.message_payload_sha256,
        dispatch_started_at=attempt.attempted_at,
        dispatch_completed_at=dispatch.completed_at,
        dispatch_started_monotonic_ns=attempt.attempted_monotonic_ns,
        dispatch_completed_monotonic_ns=dispatch.completed_monotonic_ns,
        ack_received_at=application.received_at,
        ack_received_monotonic_ns=application.received_monotonic_ns,
        ack_not_after=T0 + timedelta(seconds=115),
        ack_not_after_monotonic_ns=11_500,
        bound_at=T0 + timedelta(seconds=105),
        bound_monotonic_ns=10_500,
    )


def test_committed_raw_ingress_is_token_restricted_and_store_receipt_minted() -> None:
    raw_id = _digest("raw-authority")
    ledger_id = _digest("ledger")
    receipt = _projection_receipt(raw_id, ledger_id=ledger_id)
    committed = CommittedRawIngressV49C.from_projection_receipt(
        ledger_id=ledger_id, receipt=receipt
    )
    replayed = CommittedRawIngressV49C.from_mapping(committed.as_dict())

    assert committed.identity_id == raw_id
    assert committed.is_store_minted
    assert replayed == committed
    assert not replayed.is_store_minted
    forged = committed.as_dict()
    forged["receipt_hash"] = _digest("forged-receipt")
    with pytest.raises(CanonicalizationError, match="semantic fields"):
        CommittedRawIngressV49C.from_mapping(forged)
    with pytest.raises(TypeError, match="projection-constructed"):
        CommittedRawIngressV49C(_token=object())
    with pytest.raises(TypeError, match="exact PhysicalProjectionReceiptV4"):
        CommittedRawIngressV49C.from_projection_receipt(
            ledger_id=_digest("ledger"), receipt=object()
        )


def test_raw_and_parser_events_round_trip_and_validate_exact_receipt_slices() -> None:
    frame = b"\x81\x01x"
    raw = _raw_payload(frame)
    events: list[TransportActorEventV49C] = []
    raw_event = _append_event(
        events, TransportActorEventKindV49C.RAW_INGRESS_COMMITTED, raw
    )
    delineated = delineate_next_server_frame_v49c(
        prior_tail=RetainedIngressTailV49C(),
        committed_raw_chunks=(
            CommittedRawChunkV49C(
                raw_ingress_commit_id=raw.raw_ingress_commit_id,
                projection_receipt_sequence=raw.receipt.global_sequence,
                projection_receipt_hash=raw.receipt.receipt_hash,
                raw_local_start_octet=0,
                stream_start_octet=0,
                data=frame,
            ),
        ),
    )
    assert type(delineated.unit) is DelineatedServerFrameV49C
    parser = ParserTransitionPayloadV49C(
        cursor_before=WebSocketParserCursorV49C(
            cursor_sequence=0,
            next_stream_octet=0,
            websocket_state=WebSocketParserStateV49C.OPEN,
        ),
        cursor_after=WebSocketParserCursorV49C(
            cursor_sequence=1,
            next_stream_octet=len(frame),
            websocket_state=WebSocketParserStateV49C.OPEN,
        ),
        feed_unit_kind=ParserFeedUnitKindV49C.COMPLETE_FRAME,
        source_slices=delineated.unit.source_slices,
        frame=delineated.unit.metadata,
        parser_error=None,
        ordered_protocol_output_chunks_base64=(),
        ordered_protocol_output_chunks_sha256=(),
        protocol_output_batch_sha256=None,
        send_eof_after_output=False,
        processed_at=T0 + timedelta(seconds=2),
        processed_monotonic_ns=20,
    )
    parser_event = _append_event(
        events, TransportActorEventKindV49C.PARSER_TRANSITION, parser
    )

    validate_transport_actor_chain_v49c(events)
    assert TransportActorEventV49C.from_mapping(raw_event.as_dict()) == raw_event
    assert TransportActorEventV49C.from_mapping(parser_event.as_dict()) == parser_event


def test_automatic_wire_consumes_exact_oldest_parser_output_once() -> None:
    events, parser_event, output_chunks = _automatic_output_prefix(split_output=True)
    automatic = _automatic_wire_payload(
        parser_event,
        label="exact",
        wire_chunks=output_chunks,
        logical_opcode=WebSocketOpcodeV49C.PONG,
        logical_payload=b"x",
    )
    _append_event(events, TransportActorEventKindV49C.OUTBOUND_WIRE_PREPARED, automatic)

    validate_transport_actor_chain_v49c(events)
    for event in events:
        assert TransportActorEventV49C.from_mapping(event.as_dict()) == event


@pytest.mark.parametrize("mutation", ["bytes", "chunk_boundaries"])
def test_automatic_wire_rejects_parser_output_mutation(mutation: str) -> None:
    events, parser_event, output_chunks = _automatic_output_prefix(split_output=True)
    if mutation == "bytes":
        changed_payload = b"y"
        wire_chunks = (
            _masked_client_control_frame(WebSocketOpcodeV49C.PONG, changed_payload),
        )
    else:
        changed_payload = b"x"
        wire_chunks = (b"".join(output_chunks),)
    automatic = _automatic_wire_payload(
        parser_event,
        label=f"mutated-{mutation}",
        wire_chunks=wire_chunks,
        logical_opcode=WebSocketOpcodeV49C.PONG,
        logical_payload=changed_payload,
    )
    _append_event(events, TransportActorEventKindV49C.OUTBOUND_WIRE_PREPARED, automatic)

    with pytest.raises(CanonicalizationError, match="differs from its exact"):
        validate_transport_actor_chain_v49c(events)


def test_parser_output_cannot_authorize_duplicate_automatic_wires() -> None:
    events, parser_event, output_chunks = _automatic_output_prefix()
    for label in ("first", "duplicate"):
        _append_event(
            events,
            TransportActorEventKindV49C.OUTBOUND_WIRE_PREPARED,
            _automatic_wire_payload(
                parser_event,
                label=label,
                wire_chunks=output_chunks,
                logical_opcode=WebSocketOpcodeV49C.PONG,
                logical_payload=b"x",
            ),
        )

    with pytest.raises(CanonicalizationError, match="oldest unconsumed"):
        validate_transport_actor_chain_v49c(events)


def test_parser_event_without_output_cannot_authorize_automatic_wire() -> None:
    inbound = b"\x81\x01x"
    raw = _raw_payload(inbound)
    events: list[TransportActorEventV49C] = []
    _append_event(events, TransportActorEventKindV49C.RAW_INGRESS_COMMITTED, raw)
    parser_event = _append_event(
        events,
        TransportActorEventKindV49C.PARSER_TRANSITION,
        _parser_payload_for_raw(
            raw,
            inbound,
            cursor_sequence=0,
            protocol_output_chunks=(),
        ),
    )
    invented = _masked_client_control_frame(WebSocketOpcodeV49C.PONG, b"x")
    _append_event(
        events,
        TransportActorEventKindV49C.OUTBOUND_WIRE_PREPARED,
        _automatic_wire_payload(
            parser_event,
            label="invented",
            wire_chunks=(invented,),
            logical_opcode=WebSocketOpcodeV49C.PONG,
            logical_payload=b"x",
        ),
    )

    with pytest.raises(CanonicalizationError, match="oldest unconsumed"):
        validate_transport_actor_chain_v49c(events)


@pytest.mark.parametrize(
    ("inbound", "required_output"),
    ((b"\x89\x01x", "Pong"), (b"\x88\x00", "Close")),
)
def test_open_ping_and_close_cannot_omit_mandatory_automatic_output(
    inbound: bytes,
    required_output: str,
) -> None:
    raw = _raw_payload(inbound)

    with pytest.raises(
        CanonicalizationError,
        match=rf"OPEN parser .* requires one automatic {required_output}",
    ):
        _parser_payload_for_raw(
            raw,
            inbound,
            cursor_sequence=0,
            protocol_output_chunks=(),
        )


def test_chain_rejects_tampered_open_ping_with_removed_pong() -> None:
    events, parser_event, _ = _automatic_output_prefix()
    parser = parser_event.payload
    assert type(parser) is ParserTransitionPayloadV49C
    object.__setattr__(parser, "ordered_protocol_output_chunks_base64", ())

    with pytest.raises(CanonicalizationError, match="omits its mandatory"):
        validate_transport_actor_chain_v49c(events)


def test_application_wire_cannot_reorder_pending_automatic_output() -> None:
    events, _, _ = _automatic_output_prefix()
    _append_event(
        events,
        TransportActorEventKindV49C.OUTBOUND_WIRE_PREPARED,
        _wire_payload("application-before-pong"),
    )

    with pytest.raises(CanonicalizationError, match="cannot reorder"):
        validate_transport_actor_chain_v49c(events)


def test_application_origin_rejects_non_text_wire() -> None:
    with pytest.raises(
        CanonicalizationError, match="application wire must be one subscription Text"
    ):
        _local_terminal_wire_payload(
            [],
            origin=OutboundWireOriginV49C.APPLICATION_INTENT,
        )


@pytest.mark.parametrize(
    ("mutation", "expected"),
    (
        ("source", "non-automatic wire origin forbids"),
        ("opcode", "local terminal command must be one normal Close"),
        ("status", "local terminal command must be one normal Close"),
        ("reason", "local terminal command must be one normal Close"),
    ),
)
def test_local_terminal_command_rejects_non_fixed_close_payload(
    mutation: str,
    expected: str,
) -> None:
    values: dict[str, Any] = {}
    if mutation == "source":
        values["source_parser_event_id"] = _digest("forged-parser-source")
    elif mutation == "opcode":
        values["opcode"] = WebSocketOpcodeV49C.TEXT
        values["logical_payload"] = b"x"
    elif mutation == "status":
        values["logical_payload"] = (1001).to_bytes(2, "big")
    else:
        values["logical_payload"] = (1000).to_bytes(2, "big") + b"reason"

    with pytest.raises(CanonicalizationError, match=expected):
        _local_terminal_wire_payload([], **values)


def test_local_terminal_command_identity_binds_predecessor_and_wire() -> None:
    events: list[TransportActorEventV49C] = []
    payload = _local_terminal_wire_payload(
        events,
        outbound_operation_id=_digest("unbound-local-close"),
    )
    _append_event(
        events,
        TransportActorEventKindV49C.OUTBOUND_WIRE_PREPARED,
        payload,
    )

    with pytest.raises(CanonicalizationError, match="operation identity differs"):
        validate_transport_actor_chain_v49c(events)


def test_actor_chain_rejects_second_local_terminal_command() -> None:
    events: list[TransportActorEventV49C] = []
    _append_local_shutdown_command(events)
    _append_event(
        events,
        TransportActorEventKindV49C.OUTBOUND_WIRE_PREPARED,
        _local_terminal_wire_payload(events),
    )
    _append_local_shutdown_command(events)

    with pytest.raises(CanonicalizationError, match="second local terminal command"):
        validate_transport_actor_chain_v49c(events)


def test_local_terminal_command_cannot_reorder_pending_automatic_output() -> None:
    events, _, _ = _automatic_output_prefix()
    _append_local_shutdown_command(events)

    with pytest.raises(CanonicalizationError, match="cannot reorder"):
        validate_transport_actor_chain_v49c(events)


def test_local_terminal_marker_moves_derived_parser_cursor_to_closing() -> None:
    inbound = b"\x88\x00"
    raw = _raw_payload(inbound)
    events: list[TransportActorEventV49C] = []
    _append_event(events, TransportActorEventKindV49C.RAW_INGRESS_COMMITTED, raw)
    _append_local_shutdown_command(events)
    local_wire = _local_terminal_wire_payload(events)
    _append_event(
        events,
        TransportActorEventKindV49C.OUTBOUND_WIRE_PREPARED,
        local_wire,
    )
    state = initial_terminal_state_v49c(AUTHORITY["transport_session_id"])
    close_sent = TerminalTransitionPayloadV49C(
        transport_session_id=AUTHORITY["transport_session_id"],
        transition_sequence=1,
        parent_terminal_state_id=state.terminal_state_id,
        kind=TerminalTransitionKindV49C.WS_CLOSE_SENT,
        obligation_layer=OutboundObligationLayerV49C.WEBSOCKET_CLOSE,
        obligation_id=local_wire.outbound_operation_id,
        send_attempt_id=None,
        cause_code=None,
    )
    _append_event(
        events,
        TransportActorEventKindV49C.TERMINAL_TRANSITION,
        close_sent,
    )
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
    parser = ParserTransitionPayloadV49C(
        cursor_before=WebSocketParserCursorV49C(
            cursor_sequence=0,
            next_stream_octet=0,
            websocket_state=WebSocketParserStateV49C.CLOSING,
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
        ordered_protocol_output_chunks_base64=(),
        ordered_protocol_output_chunks_sha256=(),
        protocol_output_batch_sha256=None,
        send_eof_after_output=True,
        processed_at=T0 + timedelta(seconds=31),
        processed_monotonic_ns=3_100,
    )
    _append_event(
        events,
        TransportActorEventKindV49C.PARSER_TRANSITION,
        parser,
    )

    validate_transport_actor_chain_v49c(events)


def test_local_terminal_marker_rejects_fragmented_parser_cursor() -> None:
    inbound = b"\x01\x03hel"
    raw = _raw_payload(inbound)
    events: list[TransportActorEventV49C] = []
    _append_event(events, TransportActorEventKindV49C.RAW_INGRESS_COMMITTED, raw)
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
    _append_event(
        events,
        TransportActorEventKindV49C.PARSER_TRANSITION,
        ParserTransitionPayloadV49C(
            cursor_before=WebSocketParserCursorV49C(
                cursor_sequence=0,
                next_stream_octet=0,
                websocket_state=WebSocketParserStateV49C.OPEN,
            ),
            cursor_after=WebSocketParserCursorV49C(
                cursor_sequence=1,
                next_stream_octet=len(inbound),
                websocket_state=WebSocketParserStateV49C.OPEN,
                fragmented_message_opcode=WebSocketOpcodeV49C.TEXT,
                fragmented_message_octets=3,
                fragmented_message_sha256=hashlib.sha256(b"hel").hexdigest(),
            ),
            feed_unit_kind=ParserFeedUnitKindV49C.COMPLETE_FRAME,
            source_slices=delineated.unit.source_slices,
            frame=delineated.unit.metadata,
            parser_error=None,
            ordered_protocol_output_chunks_base64=(),
            ordered_protocol_output_chunks_sha256=(),
            protocol_output_batch_sha256=None,
            send_eof_after_output=False,
            processed_at=raw.receipt.committed_at + timedelta(milliseconds=1),
            processed_monotonic_ns=raw.received_monotonic_ns + 10,
        ),
    )
    _append_local_shutdown_command(events)

    with pytest.raises(CanonicalizationError, match="cannot close a fragmented"):
        validate_transport_actor_chain_v49c(events)


def test_websocket_close_timeout_rejects_predeadline_actor_clock() -> None:
    events: list[TransportActorEventV49C] = []
    _append_local_shutdown_command(events)
    local_wire = _local_terminal_wire_payload(events)
    _append_event(
        events,
        TransportActorEventKindV49C.OUTBOUND_WIRE_PREPARED,
        local_wire,
    )
    state = initial_terminal_state_v49c(AUTHORITY["transport_session_id"])
    close_sent = TerminalTransitionPayloadV49C(
        transport_session_id=AUTHORITY["transport_session_id"],
        transition_sequence=1,
        parent_terminal_state_id=state.terminal_state_id,
        kind=TerminalTransitionKindV49C.WS_CLOSE_SENT,
        obligation_layer=OutboundObligationLayerV49C.WEBSOCKET_CLOSE,
        obligation_id=local_wire.outbound_operation_id,
        send_attempt_id=None,
        cause_code=None,
    )
    _append_event(
        events,
        TransportActorEventKindV49C.TERMINAL_TRANSITION,
        close_sent,
    )
    state = advance_terminal_state_v49c(state, close_sent)
    _append_event(
        events,
        TransportActorEventKindV49C.TERMINAL_TRANSITION,
        TerminalTransitionPayloadV49C(
            transport_session_id=AUTHORITY["transport_session_id"],
            transition_sequence=2,
            parent_terminal_state_id=state.terminal_state_id,
            kind=TerminalTransitionKindV49C.TIMEOUT,
            obligation_layer=None,
            obligation_id=None,
            send_attempt_id=None,
            cause_code=V49E_WEBSOCKET_CLOSE_DEADLINE_EXPIRED_CAUSE,
        ),
    )

    with pytest.raises(CanonicalizationError, match="both due clocks"):
        validate_transport_actor_chain_v49c(events)


@pytest.mark.parametrize(
    "mutation",
    (
        "unmasked",
        "substituted-payload",
        "opcode",
        "fragmented",
        "rsv",
        "non-minimal-length",
        "concatenated",
        "trailing-byte",
    ),
)
def test_application_wire_metadata_is_bound_to_one_exact_masked_frame(
    mutation: str,
) -> None:
    item = _wire_payload("wire-adversary")
    logical = b"wire-adversary"
    valid = _masked_client_text_frame(logical)
    if mutation == "unmasked":
        wire = bytes((0x81, len(logical))) + logical
    elif mutation == "substituted-payload":
        wire = _masked_client_text_frame(b"wire-adversarx")
    elif mutation == "opcode":
        wire = _masked_client_text_frame(logical, first_octet=0x82)
    elif mutation == "fragmented":
        wire = _masked_client_text_frame(logical, first_octet=0x01)
    elif mutation == "rsv":
        wire = _masked_client_text_frame(logical, first_octet=0xC1)
    elif mutation == "non-minimal-length":
        mask = b"\x01\x02\x03\x04"
        masked = bytes(value ^ mask[index % 4] for index, value in enumerate(logical))
        wire = b"\x81\xfe" + len(logical).to_bytes(2, "big") + mask + masked
    elif mutation == "concatenated":
        wire = valid + valid
    else:
        wire = valid + b"\x00"
    encoded, hashes = _encoded_chunks((wire,))
    mapping = item.as_dict()
    mapping.update(
        ordered_wire_chunks_base64=list(encoded),
        ordered_wire_chunks_sha256=list(hashes),
        wire_batch_sha256=_ordered_batch(
            "RiskYieldMMActorOrderedProtocolOutputV4_9C", encoded
        ),
        wire_octets=len(wire),
    )

    with pytest.raises(CanonicalizationError):
        OutboundWirePreparedPayloadV49C.from_mapping(mapping)


def test_automatic_wire_cannot_reorder_two_parser_outputs() -> None:
    events, first_parser, _ = _automatic_output_prefix(payload=b"x")
    first_raw = events[0].payload
    assert type(first_raw) is RawIngressCommittedPayloadV49C
    inbound = b"\x89\x01y"
    second_raw = _raw_payload(
        inbound,
        raw_id=_digest("raw-2"),
        ingress_sequence=2,
        previous_raw_id=first_raw.raw_ingress_commit_id,
        stream_start=first_raw.stream_end_octet,
        receipt_sequence=2,
        received_at=T0 + timedelta(seconds=30),
        received_monotonic_ns=3_000,
    )
    _append_event(
        events,
        TransportActorEventKindV49C.RAW_INGRESS_COMMITTED,
        second_raw,
    )
    second_output = _masked_client_control_frame(WebSocketOpcodeV49C.PONG, b"y")
    second_parser = _append_event(
        events,
        TransportActorEventKindV49C.PARSER_TRANSITION,
        _parser_payload_for_raw(
            second_raw,
            inbound,
            cursor_sequence=1,
            protocol_output_chunks=(second_output,),
        ),
    )
    _append_event(
        events,
        TransportActorEventKindV49C.OUTBOUND_WIRE_PREPARED,
        _automatic_wire_payload(
            second_parser,
            label="second-before-first",
            wire_chunks=(second_output,),
            logical_opcode=WebSocketOpcodeV49C.PONG,
            logical_payload=b"y",
        ),
    )

    assert (
        first_parser.transport_actor_event_id != second_parser.transport_actor_event_id
    )
    with pytest.raises(CanonicalizationError, match="oldest unconsumed"):
        validate_transport_actor_chain_v49c(events)


def test_aggregate_parser_output_with_multiple_obligations_fails_closed() -> None:
    inbound = b"\x89\x01x"
    raw = _raw_payload(inbound)
    first = _masked_client_control_frame(WebSocketOpcodeV49C.PONG, b"x")
    second = _masked_client_control_frame(WebSocketOpcodeV49C.PONG, b"x")

    with pytest.raises(
        CanonicalizationError, match="exactly one obligation|partial or concatenated"
    ):
        _parser_payload_for_raw(
            raw,
            inbound,
            cursor_sequence=0,
            protocol_output_chunks=(first, second),
        )


def test_actor_event_rejects_direct_construction_extra_keys_and_identity_mutation() -> (
    None
):
    event = _valid_outbound_chain()[0]
    with pytest.raises(TypeError, match="factory-constructed"):
        TransportActorEventV49C(_token=object())

    extra = event.as_dict()
    extra["unexpected"] = True
    with pytest.raises(CanonicalizationError):
        TransportActorEventV49C.from_mapping(extra)

    mutated = event.as_dict()
    mutated["transport_actor_event_id"] = _digest("wrong-event-id")
    with pytest.raises(CanonicalizationError, match="differs from canonical content"):
        TransportActorEventV49C.from_mapping(mutated)


def test_complete_outbound_chain_replays_terminal_reducer_and_all_event_schemas() -> (
    None
):
    events = _valid_outbound_chain()

    validate_transport_actor_chain_v49c(events)
    assert {event.event_kind for event in events} == {
        TransportActorEventKindV49C.OUTBOUND_WIRE_PREPARED,
        TransportActorEventKindV49C.WRITE_PERMIT_CONSUMED,
        TransportActorEventKindV49C.TLS_CIPHERTEXT_PREPARED,
        TransportActorEventKindV49C.KERNEL_SEND_ATTEMPT,
        TransportActorEventKindV49C.KERNEL_SEND_RESULT,
        TransportActorEventKindV49C.OUTBOUND_DISPATCH_COMPLETED,
        TransportActorEventKindV49C.TERMINAL_TRANSITION,
    }
    for event in events:
        assert TransportActorEventV49C.from_mapping(event.as_dict()) == event


def test_kernel_result_requires_durable_terminal_send_start() -> None:
    events = _valid_outbound_chain()
    without_start = events[:4] + [events[5]]
    rebuilt: list[TransportActorEventV49C] = []
    for event in without_start:
        _append_event(rebuilt, event.event_kind, event.payload)

    with pytest.raises(CanonicalizationError, match="SEND_ATTEMPT_STARTED"):
        validate_transport_actor_chain_v49c(rebuilt)


def test_unresolved_kernel_attempt_blocks_unrelated_actor_progress() -> None:
    events = _valid_outbound_chain()[:4]
    _append_event(
        events,
        TransportActorEventKindV49C.OUTBOUND_WIRE_PREPARED,
        _wire_payload("blocked", prepared_ns=450),
    )

    with pytest.raises(CanonicalizationError, match="unresolved kernel attempt"):
        validate_transport_actor_chain_v49c(events)


def test_one_total_fifo_prevents_second_permit_before_oldest_dispatch() -> None:
    events: list[TransportActorEventV49C] = []
    first = _append_event(
        events,
        TransportActorEventKindV49C.OUTBOUND_WIRE_PREPARED,
        _wire_payload("first"),
    )
    second = _append_event(
        events,
        TransportActorEventKindV49C.OUTBOUND_WIRE_PREPARED,
        _wire_payload("second", prepared_ns=110),
    )
    _append_event(
        events,
        TransportActorEventKindV49C.WRITE_PERMIT_CONSUMED,
        _permit_payload(first),
    )
    _append_event(
        events,
        TransportActorEventKindV49C.WRITE_PERMIT_CONSUMED,
        _permit_payload(second, consumed_ns=210),
    )

    with pytest.raises(CanonicalizationError, match="oldest unresolved wire"):
        validate_transport_actor_chain_v49c(events)


def test_actor_chain_rejects_self_asserted_write_permit_identity() -> None:
    events: list[TransportActorEventV49C] = []
    wire = _append_event(
        events,
        TransportActorEventKindV49C.OUTBOUND_WIRE_PREPARED,
        _wire_payload("forged-permit"),
    )
    valid_permit = _permit_payload(wire)
    forged_permit_id = _digest("self-asserted-write-permit")
    assert forged_permit_id != valid_permit.permit_id
    forged_permit = WritePermitConsumedPayloadV49C.from_mapping(
        {
            **valid_permit.as_dict(),
            "permit_id": forged_permit_id,
        }
    )
    _append_event(
        events,
        TransportActorEventKindV49C.WRITE_PERMIT_CONSUMED,
        forged_permit,
    )

    with pytest.raises(CanonicalizationError, match="oldest unresolved wire"):
        validate_transport_actor_chain_v49c(events)


def test_actor_chain_rejects_authority_and_predecessor_mutations() -> None:
    events = _valid_outbound_chain()
    mapping = events[1].as_dict()
    mapping["adapter_policy_id"] = _digest("different-adapter")
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
    changed = TransportActorEventV49C.from_mapping(mapping)
    with pytest.raises(CanonicalizationError):
        validate_transport_actor_chain_v49c([events[0], changed])


def test_actor_chain_requires_strict_top_level_monotonic_clock_progress() -> None:
    first = _valid_outbound_chain()[0]
    second = TransportActorEventV49C.create(
        **AUTHORITY,
        recorded_at=first.recorded_at,
        recorded_monotonic_ns=first.recorded_monotonic_ns,
        actor_sequence=2,
        previous_event_id=first.transport_actor_event_id,
        event_kind=TransportActorEventKindV49C.OUTBOUND_WIRE_PREPARED,
        payload=_wire_payload("same-clock", prepared_ns=110),
    )

    with pytest.raises(CanonicalizationError, match="fail to advance"):
        validate_transport_actor_chain_v49c([first, second])


def test_raw_actor_top_level_clocks_equal_raw_observation() -> None:
    raw = _raw_payload(b"\x89\x00")
    event = TransportActorEventV49C.create(
        **AUTHORITY,
        recorded_at=raw.received_at + timedelta(microseconds=1),
        recorded_monotonic_ns=raw.received_monotonic_ns + 1,
        actor_sequence=1,
        previous_event_id=None,
        event_kind=TransportActorEventKindV49C.RAW_INGRESS_COMMITTED,
        payload=raw,
    )

    with pytest.raises(CanonicalizationError, match="must equal"):
        validate_transport_actor_chain_v49c([event])


def test_false_frame_header_inside_payload_is_not_delineated() -> None:
    payload = b"a\x89\x00b"
    text = b"\x81" + bytes((len(payload),)) + payload
    ping = b"\x89\x00"
    result = delineate_next_server_frame_v49c(
        prior_tail=RetainedIngressTailV49C(),
        committed_raw_chunks=(
            _chunk(
                text + ping,
                stream_start=0,
                raw_label="false-header",
                receipt_sequence=1,
            ),
        ),
    )

    assert type(result.unit) is DelineatedServerFrameV49C
    assert result.unit.frame_bytes == text
    assert result.unit.payload == payload
    assert result.retained_tail.data == ping


def test_cross_commit_frame_has_exact_slices_and_retains_second_frame() -> None:
    first = b"\x89\x01x"
    second = b"\x81\x01y"
    chunks = (
        _chunk(first[:1], stream_start=0, raw_label="raw-a", receipt_sequence=1),
        _chunk(
            first[1:] + second[:1],
            stream_start=1,
            raw_label="raw-b",
            receipt_sequence=2,
        ),
        _chunk(
            second[1:],
            stream_start=4,
            raw_label="raw-c",
            receipt_sequence=3,
        ),
    )

    result = delineate_next_server_frame_v49c(
        prior_tail=RetainedIngressTailV49C(), committed_raw_chunks=chunks
    )
    assert type(result.unit) is DelineatedServerFrameV49C
    assert result.unit.frame_bytes == first
    assert [
        (value.stream_start_octet, value.stream_end_octet)
        for value in result.unit.source_slices
    ] == [
        (0, 1),
        (1, 3),
    ]
    assert result.retained_tail.data == second

    next_result = delineate_next_server_frame_v49c(
        prior_tail=result.retained_tail, committed_raw_chunks=()
    )
    assert type(next_result.unit) is DelineatedServerFrameV49C
    assert next_result.unit.frame_bytes == second
    assert next_result.retained_tail.total_octets == 0


def test_delineator_preserves_incomplete_extended_frame_at_every_split() -> None:
    payload = bytes(range(126))
    frame = b"\x82\x7e\x00\x7e" + payload

    for split in range(1, len(frame)):
        first = _chunk(
            frame[:split],
            stream_start=0,
            raw_label=f"split-a-{split}",
            receipt_sequence=1,
        )
        incomplete = delineate_next_server_frame_v49c(
            prior_tail=RetainedIngressTailV49C(), committed_raw_chunks=(first,)
        )
        assert incomplete.unit is None
        assert incomplete.retained_tail.data == frame[:split]
        completed = delineate_next_server_frame_v49c(
            prior_tail=incomplete.retained_tail,
            committed_raw_chunks=(
                _chunk(
                    frame[split:],
                    stream_start=split,
                    raw_label=f"split-b-{split}",
                    receipt_sequence=2,
                ),
            ),
        )
        assert type(completed.unit) is DelineatedServerFrameV49C
        assert completed.unit.frame_bytes == frame
        assert completed.retained_tail.total_octets == 0


@pytest.mark.parametrize(
    ("header", "kind", "examined_octets"),
    [
        (b"\xc1\x00", ParserErrorKindV49C.RESERVED_BITS, 2),
        (b"\x83\x00", ParserErrorKindV49C.INVALID_OPCODE, 2),
        (b"\x81\x80", ParserErrorKindV49C.INCORRECT_MASKING, 2),
        (b"\x09\x00", ParserErrorKindV49C.FRAGMENTED_CONTROL, 2),
        (b"\x89\x7e", ParserErrorKindV49C.CONTROL_TOO_LARGE, 2),
        (b"\x81\x7e\x00\x7d", ParserErrorKindV49C.NON_MINIMAL_LENGTH, 4),
        (
            b"\x82\x7f" + (65_535).to_bytes(8, "big"),
            ParserErrorKindV49C.NON_MINIMAL_LENGTH,
            10,
        ),
        (
            b"\x82\x7f" + (2**63).to_bytes(8, "big"),
            ParserErrorKindV49C.INVALID_64BIT_LENGTH,
            10,
        ),
    ],
)
def test_invalid_server_headers_fail_deterministically(
    header: bytes, kind: ParserErrorKindV49C, examined_octets: int
) -> None:
    suffix = b"tail"
    result = delineate_next_server_frame_v49c(
        prior_tail=RetainedIngressTailV49C(),
        committed_raw_chunks=(
            _chunk(
                header + suffix,
                stream_start=7,
                raw_label=f"invalid-{kind.value}",
                receipt_sequence=1,
            ),
        ),
    )

    assert type(result.unit) is FrameDelineationErrorV49C
    assert result.unit.error_kind is kind
    assert result.unit.error_stream_offset == 7
    assert result.unit.examined_bytes == header[:examined_octets]
    assert result.retained_tail.data == header[examined_octets:] + suffix


def test_delineator_enforces_configured_payload_bound_from_header_only() -> None:
    result = delineate_next_server_frame_v49c(
        prior_tail=RetainedIngressTailV49C(),
        committed_raw_chunks=(
            _chunk(
                b"\x82\x05unread",
                stream_start=0,
                raw_label="oversize",
                receipt_sequence=1,
            ),
        ),
        maximum_payload_octets=4,
    )

    assert type(result.unit) is FrameDelineationErrorV49C
    assert result.unit.error_kind is ParserErrorKindV49C.FRAME_TOO_LARGE
    assert result.unit.examined_bytes == b"\x82\x05"
    assert result.retained_tail.data == b"unread"


def test_delineator_coalesces_same_receipt_slices_and_rejects_local_gaps() -> None:
    frame = b"\x81\x01x"
    first = _chunk(frame[:1], stream_start=0, raw_label="same", receipt_sequence=1)
    second = _chunk(
        frame[1:],
        stream_start=1,
        raw_label="same",
        receipt_sequence=1,
        raw_local_start=1,
    )
    result = delineate_next_server_frame_v49c(
        prior_tail=RetainedIngressTailV49C(), committed_raw_chunks=(first, second)
    )
    assert type(result.unit) is DelineatedServerFrameV49C
    assert len(result.unit.source_slices) == 1

    bad = _chunk(
        frame[1:],
        stream_start=1,
        raw_label="same",
        receipt_sequence=1,
        raw_local_start=2,
    )
    with pytest.raises(CanonicalizationError, match="local offsets"):
        delineate_next_server_frame_v49c(
            prior_tail=RetainedIngressTailV49C(),
            committed_raw_chunks=(first, bad),
        )


def test_delineator_rejects_noncontiguous_stream_chunks() -> None:
    with pytest.raises(CanonicalizationError, match="stream-contiguous"):
        delineate_next_server_frame_v49c(
            prior_tail=RetainedIngressTailV49C(),
            committed_raw_chunks=(
                _chunk(b"\x81", stream_start=0, raw_label="gap-a", receipt_sequence=1),
                _chunk(b"\x00", stream_start=2, raw_label="gap-b", receipt_sequence=2),
            ),
        )


def test_payload_and_event_mappings_reject_nested_extra_fields() -> None:
    event = _valid_outbound_chain()[0]
    mapping = copy.deepcopy(event.as_dict())
    mapping["payload"]["unknown"] = "field"

    with pytest.raises(CanonicalizationError):
        TransportActorEventV49C.from_mapping(mapping)


@pytest.mark.parametrize(
    ("submitted_delta", "disposition"),
    [
        (-1, OutboundDispatchDispositionV49C.UNKNOWN_DELIVERY.value),
        (0, OutboundDispatchDispositionV49C.UNKNOWN_DELIVERY.value),
    ],
)
def test_dispatch_completion_cannot_abandon_or_relabel_tls_suffix(
    submitted_delta: int,
    disposition: str,
) -> None:
    dispatch = _valid_outbound_chain()[-1].payload
    assert type(dispatch) is OutboundDispatchCompletedPayloadV49C
    mapping = dispatch.as_dict()
    mapping["submitted_ciphertext_octets"] = (
        dispatch.ciphertext_octets + submitted_delta
    )
    mapping["disposition"] = disposition

    with pytest.raises(CanonicalizationError, match="full local submission"):
        OutboundDispatchCompletedPayloadV49C.from_mapping(mapping)


def test_actor_chain_rejects_unbound_positive_tls_terminal_fact() -> None:
    events = _valid_outbound_chain()
    state = initial_terminal_state_v49c(AUTHORITY["transport_session_id"])
    for event in events:
        if event.event_kind is TransportActorEventKindV49C.TERMINAL_TRANSITION:
            state = advance_terminal_state_v49c(state, event.payload)
    fabricated = TerminalTransitionPayloadV49C(
        transport_session_id=AUTHORITY["transport_session_id"],
        transition_sequence=state.transition_sequence + 1,
        parent_terminal_state_id=state.terminal_state_id,
        kind=TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_RECEIVED,
    )
    _append_event(
        events,
        TransportActorEventKindV49C.TERMINAL_TRANSITION,
        fabricated,
    )

    with pytest.raises(CanonicalizationError, match="isn't actor-integrated"):
        validate_transport_actor_chain_v49c(events)


def test_v49e_application_commit_and_ack_bind_exact_parser_and_dispatch() -> None:
    events = _valid_outbound_chain()
    application_event = _append_ack_application_message(events)
    ack_event = _append_event(
        events,
        TransportActorEventKindV49C.SUBSCRIPTION_ACK_BOUND,
        _ack_payload_for_prefix(events, application_event),
    )

    validate_transport_actor_chain_v49c(events)
    assert (
        TransportActorEventV49C.from_mapping(application_event.as_dict())
        == application_event
    )
    assert TransportActorEventV49C.from_mapping(ack_event.as_dict()) == ack_event

    changed = application_event.payload.as_dict()
    changed["message_payload_sha256"] = _digest("wrong-message")
    changed_event = _actor_event(
        kind=TransportActorEventKindV49C.APPLICATION_MESSAGE_COMMITTED,
        payload=ApplicationMessageCommittedPayloadV49E.from_mapping(changed),
        sequence=application_event.actor_sequence,
        previous_event_id=application_event.previous_event_id,
    )
    with pytest.raises(CanonicalizationError, match="oldest complete parser message"):
        validate_transport_actor_chain_v49c(
            [*events[: application_event.actor_sequence - 1], changed_event]
        )


def test_v49e_fragmented_message_excludes_interleaved_control_source() -> None:
    events: list[TransportActorEventV49C] = []

    def parser_payload(
        *,
        raw: RawIngressCommittedPayloadV49C,
        frame_bytes: bytes,
        before: WebSocketParserCursorV49C,
        after: WebSocketParserCursorV49C,
    ) -> ParserTransitionPayloadV49C:
        delineated = delineate_next_server_frame_v49c(
            prior_tail=RetainedIngressTailV49C(),
            committed_raw_chunks=(
                CommittedRawChunkV49C(
                    raw_ingress_commit_id=raw.raw_ingress_commit_id,
                    projection_receipt_sequence=raw.receipt.global_sequence,
                    projection_receipt_hash=raw.receipt.receipt_hash,
                    raw_local_start_octet=0,
                    stream_start_octet=raw.stream_start_octet,
                    data=frame_bytes,
                ),
            ),
        )
        assert type(delineated.unit) is DelineatedServerFrameV49C
        return ParserTransitionPayloadV49C(
            cursor_before=before,
            cursor_after=after,
            feed_unit_kind=ParserFeedUnitKindV49C.COMPLETE_FRAME,
            source_slices=delineated.unit.source_slices,
            frame=delineated.unit.metadata,
            parser_error=None,
            ordered_protocol_output_chunks_base64=(),
            ordered_protocol_output_chunks_sha256=(),
            protocol_output_batch_sha256=None,
            send_eof_after_output=False,
            processed_at=raw.receipt.committed_at + timedelta(milliseconds=1),
            processed_monotonic_ns=raw.received_monotonic_ns + 10,
        )

    first_frame = b"\x01\x03hel"
    raw_one = _raw_payload(first_frame)
    _append_event(events, TransportActorEventKindV49C.RAW_INGRESS_COMMITTED, raw_one)
    cursor_zero = WebSocketParserCursorV49C(
        cursor_sequence=0,
        next_stream_octet=0,
        websocket_state=WebSocketParserStateV49C.OPEN,
    )
    cursor_one = WebSocketParserCursorV49C(
        cursor_sequence=1,
        next_stream_octet=len(first_frame),
        websocket_state=WebSocketParserStateV49C.OPEN,
        fragmented_message_opcode=WebSocketOpcodeV49C.TEXT,
        fragmented_message_octets=3,
        fragmented_message_sha256=hashlib.sha256(b"hel").hexdigest(),
    )
    first_parser = _append_event(
        events,
        TransportActorEventKindV49C.PARSER_TRANSITION,
        parser_payload(
            raw=raw_one,
            frame_bytes=first_frame,
            before=cursor_zero,
            after=cursor_one,
        ),
    )

    pong_frame = b"\x8a\x01x"
    raw_two = _raw_payload(
        pong_frame,
        raw_id=_digest("raw-2"),
        ingress_sequence=2,
        previous_raw_id=raw_one.raw_ingress_commit_id,
        stream_start=len(first_frame),
        receipt_sequence=2,
        received_at=T0 + timedelta(seconds=21),
        received_monotonic_ns=2_100,
    )
    _append_event(events, TransportActorEventKindV49C.RAW_INGRESS_COMMITTED, raw_two)
    cursor_two = WebSocketParserCursorV49C(
        cursor_sequence=2,
        next_stream_octet=len(first_frame) + len(pong_frame),
        websocket_state=WebSocketParserStateV49C.OPEN,
        fragmented_message_opcode=WebSocketOpcodeV49C.TEXT,
        fragmented_message_octets=3,
        fragmented_message_sha256=hashlib.sha256(b"hel").hexdigest(),
    )
    control_parser = _append_event(
        events,
        TransportActorEventKindV49C.PARSER_TRANSITION,
        parser_payload(
            raw=raw_two,
            frame_bytes=pong_frame,
            before=cursor_one,
            after=cursor_two,
        ),
    )

    final_frame = b"\x80\x02lo"
    stream_start = len(first_frame) + len(pong_frame)
    raw_three = _raw_payload(
        final_frame,
        raw_id=_digest("raw-3"),
        ingress_sequence=3,
        previous_raw_id=raw_two.raw_ingress_commit_id,
        stream_start=stream_start,
        receipt_sequence=3,
        received_at=T0 + timedelta(seconds=41),
        received_monotonic_ns=4_100,
    )
    _append_event(events, TransportActorEventKindV49C.RAW_INGRESS_COMMITTED, raw_three)
    cursor_three = WebSocketParserCursorV49C(
        cursor_sequence=3,
        next_stream_octet=stream_start + len(final_frame),
        websocket_state=WebSocketParserStateV49C.OPEN,
    )
    final_parser = _append_event(
        events,
        TransportActorEventKindV49C.PARSER_TRANSITION,
        parser_payload(
            raw=raw_three,
            frame_bytes=final_frame,
            before=cursor_two,
            after=cursor_three,
        ),
    )
    application_payload = ApplicationMessageCommittedPayloadV49E(
        source_parser_event_ids=(
            first_parser.transport_actor_event_id,
            final_parser.transport_actor_event_id,
        ),
        message_opcode=WebSocketOpcodeV49C.TEXT,
        message_payload_octets=5,
        message_payload_sha256=hashlib.sha256(b"hello").hexdigest(),
        capture_segment_id=_digest("fragment-capture"),
        message_receipt_id=_digest("fragment-receipt"),
        physical_message_id=_digest("fragment-message"),
        provider_message_disposition_id=_digest("fragment-provider-disposition"),
        message_disposition_id=_digest("fragment-v4-disposition"),
        disposition_kind=MessageDispositionKind.NORMALIZED_OBSERVATION,
        received_at=T0 + timedelta(seconds=42),
        received_monotonic_ns=4_200,
        classified_at=T0 + timedelta(seconds=61),
        classified_monotonic_ns=6_100,
    )
    _append_event(
        events,
        TransportActorEventKindV49C.APPLICATION_MESSAGE_COMMITTED,
        application_payload,
    )

    validate_transport_actor_chain_v49c(events)

    wrong_sources = application_payload.as_dict()
    wrong_sources["source_parser_event_ids"] = [
        first_parser.transport_actor_event_id,
        control_parser.transport_actor_event_id,
        final_parser.transport_actor_event_id,
    ]
    events[-1] = _actor_event(
        kind=TransportActorEventKindV49C.APPLICATION_MESSAGE_COMMITTED,
        payload=ApplicationMessageCommittedPayloadV49E.from_mapping(wrong_sources),
        sequence=events[-1].actor_sequence,
        previous_event_id=events[-1].previous_event_id,
    )
    with pytest.raises(CanonicalizationError, match="oldest complete parser message"):
        validate_transport_actor_chain_v49c(events)


def test_v49e_ack_and_deadline_are_mutually_exclusive() -> None:
    ack_events = _valid_outbound_chain()
    application_event = _append_ack_application_message(ack_events)
    _append_event(
        ack_events,
        TransportActorEventKindV49C.SUBSCRIPTION_ACK_BOUND,
        _ack_payload_for_prefix(ack_events, application_event),
    )
    dispatch_event = next(
        event
        for event in ack_events
        if event.event_kind is TransportActorEventKindV49C.OUTBOUND_DISPATCH_COMPLETED
    )
    wire_event = ack_events[0]
    dispatch = dispatch_event.payload
    wire = wire_event.payload
    assert type(dispatch) is OutboundDispatchCompletedPayloadV49C
    assert type(wire) is OutboundWirePreparedPayloadV49C
    deadline = AckDeadlineExpiredPayloadV49E(
        outbound_subscription_intent_id=wire.outbound_operation_id,
        subscription_dispatch_completed_event_id=(
            dispatch_event.transport_actor_event_id
        ),
        dispatch_completed_at=dispatch.completed_at,
        dispatch_completed_monotonic_ns=dispatch.completed_monotonic_ns,
        ack_not_after=T0 + timedelta(seconds=115),
        ack_not_after_monotonic_ns=11_500,
        observed_at=T0 + timedelta(seconds=116),
        observed_monotonic_ns=11_600,
    )
    _append_event(
        ack_events,
        TransportActorEventKindV49C.ACK_DEADLINE_EXPIRED,
        deadline,
    )
    with pytest.raises(CanonicalizationError, match="already has an ACK or timeout"):
        validate_transport_actor_chain_v49c(ack_events)

    timeout_events = _valid_outbound_chain()
    application_event = _append_ack_application_message(timeout_events)
    _append_event(
        timeout_events,
        TransportActorEventKindV49C.ACK_DEADLINE_EXPIRED,
        deadline,
    )
    validate_transport_actor_chain_v49c(timeout_events)
    _append_event(
        timeout_events,
        TransportActorEventKindV49C.SUBSCRIPTION_ACK_BOUND,
        _ack_payload_for_prefix(timeout_events, application_event),
    )
    with pytest.raises(CanonicalizationError, match="terminal TIMEOUT"):
        validate_transport_actor_chain_v49c(timeout_events)

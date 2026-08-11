from __future__ import annotations

import asyncio
import base64
import hashlib
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from functools import wraps
from typing import Any

import pytest

from riskyieldmm.trading.canonical import sha256_digest
from riskyieldmm.trading.physical_projection_v4 import (
    CommittedActorRawIngressV49C,
    PhysicalProjectionReceiptV4,
    PhysicalRecordKindV4,
)
from riskyieldmm.trading.physical_transport_actor_v49c import (
    CommittedRawIngressV49C,
    OutboundDispatchCompletedPayloadV49C,
    OutboundWireOriginV49C,
    OutboundWirePreparedPayloadV49C,
    ParserFeedUnitKindV49C,
    ParserTransitionPayloadV49C,
    RawIngressCommittedPayloadV49C,
    RawSourceSliceV49C,
    TlsCiphertextPreparedPayloadV49C,
    TransportActorEventKindV49C,
    TransportActorEventV49C,
    WebSocketFrameMetadataV49C,
    WebSocketOpcodeV49C,
    WebSocketParserCursorV49C,
    WebSocketParserStateV49C,
    WritePermitConsumedPayloadV49C,
    derive_actor_write_permit_id_v49c,
)
from riskyieldmm.trading.physical_transport_control_v4 import RawIngressCommitV4
from riskyieldmm.trading.physical_transport_session_actor_v49c import (
    PhysicalTransportSessionActorV49C,
    PhysicalTransportSessionActorV49CFaultLatched,
    PhysicalTransportSessionActorV49CJournalError,
    PhysicalTransportSessionActorV49COwnerError,
    PhysicalTransportSessionActorV49CQueueError,
    TransportActorAuthorityV49C,
)
from riskyieldmm.trading.physical_transport_terminal_v49c import (
    TerminalOutcomeV49C,
    TerminalTransitionKindV49C,
)
from riskyieldmm.trading.physical_transport_tls_v49 import PreparedWebSocketWireV49C

_NOW = datetime(2026, 7, 17, 10, 0, tzinfo=UTC)
_OUTPUT_DOMAIN = "RiskYieldMMActorOrderedProtocolOutputV4_9C"
_CIPHERTEXT_DOMAIN = "RiskYieldMMActorOrderedTlsCiphertextV4_9C"


def _run_async(function: Any) -> Any:
    @wraps(function)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return asyncio.run(function(*args, **kwargs))

    return wrapper


def _hash(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _batch_hash(domain: str, chunks: tuple[bytes, ...]) -> str:
    return sha256_digest(
        {
            "domain": domain,
            "ordered_chunks_base64": [
                base64.b64encode(chunk).decode("ascii") for chunk in chunks
            ],
        }
    )


class _Clock:
    def __init__(self, *, monotonic_ns: int = 10_000) -> None:
        self.value = monotonic_ns

    def observation(self) -> tuple[datetime, int]:
        self.value += 10
        return (
            _NOW + timedelta(seconds=10, microseconds=self.value),
            self.value,
        )


class _StrictJournal:
    def __init__(self) -> None:
        self.events: list[TransportActorEventV49C] = []
        self._raw_capabilities: set[int] = set()
        self.fail_before: Callable[[TransportActorEventV49C], BaseException | None] = (
            lambda _event: None
        )
        self.fail_after: Callable[[TransportActorEventV49C], BaseException | None] = (
            lambda _event: None
        )
        self.batch_fail_insert_at: int | None = None

    def commit_raw(self, event: TransportActorEventV49C) -> None:
        assert event.event_kind is TransportActorEventKindV49C.RAW_INGRESS_COMMITTED
        self.events.append(event)
        self._raw_capabilities.add(id(event))

    async def append_actor_raw_ingress_v49c(
        self, *, raw: RawIngressCommitV4
    ) -> CommittedActorRawIngressV49C:
        assert type(raw) is RawIngressCommitV4
        ledger_id = _hash("strict-journal-ledger")
        prior_raw = next(
            (
                event.payload
                for event in reversed(self.events)
                if event.event_kind is TransportActorEventKindV49C.RAW_INGRESS_COMMITTED
            ),
            None,
        )
        assert prior_raw is None or type(prior_raw) is RawIngressCommittedPayloadV49C
        previous_receipt_hash = (
            "0" * 64 if prior_raw is None else prior_raw.receipt.receipt_hash
        )
        global_sequence = (
            1 if prior_raw is None else prior_raw.receipt.global_sequence + 1
        )
        content_hash = sha256_digest(raw.as_dict())
        receipt_hash = sha256_digest(
            {
                "content_hash": content_hash,
                "domain": "RiskYieldMMPhysicalProjectionReceiptV4",
                "global_sequence": global_sequence,
                "identity_id": raw.raw_ingress_commit_id,
                "ledger_id": ledger_id,
                "previous_receipt_hash": previous_receipt_hash,
                "record_kind": "RAW_INGRESS_COMMIT_V4",
            }
        )
        projection_receipt = PhysicalProjectionReceiptV4(
            global_sequence=global_sequence,
            receipt_hash=receipt_hash,
            previous_receipt_hash=previous_receipt_hash,
            record_kind=PhysicalRecordKindV4.RAW_INGRESS_COMMIT,
            identity_id=raw.raw_ingress_commit_id,
            content_hash=content_hash,
            committed_at=raw.received_at + timedelta(microseconds=1),
        )
        receipt = CommittedRawIngressV49C.from_projection_receipt(
            ledger_id=ledger_id,
            receipt=projection_receipt,
        )
        chunks = tuple(
            base64.b64decode(value, validate=True)
            for value in raw.raw_ingress_chunks_base64
        )
        stream_start = 0 if prior_raw is None else prior_raw.stream_end_octet
        payload = RawIngressCommittedPayloadV49C(
            raw_ingress_commit_id=raw.raw_ingress_commit_id,
            receipt=receipt,
            ingress_sequence=raw.ingress_sequence,
            previous_raw_ingress_commit_id=(
                None if prior_raw is None else prior_raw.raw_ingress_commit_id
            ),
            stream_start_octet=stream_start,
            stream_end_octet=stream_start + sum(map(len, chunks)),
            ordered_chunk_octet_lengths=tuple(map(len, chunks)),
            ordered_chunk_sha256=raw.raw_ingress_chunks_sha256,
            raw_ingress_batch_sha256=raw.raw_ingress_batch_sha256,
            received_at=raw.received_at,
            received_monotonic_ns=raw.received_monotonic_ns,
        )
        event = TransportActorEventV49C.create(
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
            monotonic_clock_domain_id=raw.monotonic_clock_domain_id,
            driver_policy_id=_hash("driver"),
            recorded_at=raw.received_at,
            recorded_monotonic_ns=raw.received_monotonic_ns,
            actor_sequence=len(self.events) + 1,
            previous_event_id=(
                None if not self.events else self.events[-1].transport_actor_event_id
            ),
            event_kind=TransportActorEventKindV49C.RAW_INGRESS_COMMITTED,
            payload=payload,
        )
        before = self.fail_before(event)
        if before is not None:
            raise before
        self.events.append(event)
        self._raw_capabilities.add(id(event))
        after = self.fail_after(event)
        if after is not None:
            raise after
        return CommittedActorRawIngressV49C(
            raw=raw,
            receipt=receipt,
            event=event,
        )

    async def read_transport_actor_prefix_v49c(
        self, *, transport_session_id: str
    ) -> tuple[TransportActorEventV49C, ...]:
        assert all(
            item.transport_session_id == transport_session_id for item in self.events
        )
        return tuple(self.events)

    async def resolve_exact_committed_raw_actor_event_v49c(
        self, *, event: TransportActorEventV49C
    ) -> TransportActorEventV49C:
        if id(event) not in self._raw_capabilities:
            raise RuntimeError("not the projection-returned RAW capability")
        self._raw_capabilities.remove(id(event))
        return event

    async def append_transport_actor_event_v49c(
        self, *, event: TransportActorEventV49C
    ) -> TransportActorEventV49C:
        before = self.fail_before(event)
        if before is not None:
            raise before
        self.events.append(event)
        after = self.fail_after(event)
        if after is not None:
            raise after
        return event

    async def append_transport_actor_events_v49c(
        self, *, events: tuple[TransportActorEventV49C, ...]
    ) -> tuple[TransportActorEventV49C, ...]:
        staged: list[TransportActorEventV49C] = []
        for position, event in enumerate(events, start=1):
            before = self.fail_before(event)
            if before is not None:
                raise before
            staged.append(event)
            if self.batch_fail_insert_at == position:
                raise RuntimeError(f"batch insert {position} failed")
        self.events.extend(staged)
        for event in events:
            after = self.fail_after(event)
            if after is not None:
                raise after
        return events


def _raw_event(
    *,
    driver_policy_id: str = _hash("driver"),
    actor_sequence: int = 1,
    previous_event_id: str | None = None,
) -> TransportActorEventV49C:
    raw = b"\x89\x01x"
    ledger_id = _hash("ledger")
    previous_receipt_hash = "0" * 64
    identity_id = _hash("raw-commit")
    content_hash = _hash("raw-record-content")
    receipt_hash = sha256_digest(
        {
            "content_hash": content_hash,
            "domain": "RiskYieldMMPhysicalProjectionReceiptV4",
            "global_sequence": 1,
            "identity_id": identity_id,
            "ledger_id": ledger_id,
            "previous_receipt_hash": previous_receipt_hash,
            "record_kind": "RAW_INGRESS_COMMIT_V4",
        }
    )
    projection_receipt = PhysicalProjectionReceiptV4(
        global_sequence=1,
        receipt_hash=receipt_hash,
        previous_receipt_hash=previous_receipt_hash,
        record_kind=PhysicalRecordKindV4.RAW_INGRESS_COMMIT,
        identity_id=identity_id,
        content_hash=content_hash,
        committed_at=_NOW + timedelta(seconds=1),
    )
    receipt = CommittedRawIngressV49C.from_projection_receipt(
        ledger_id=ledger_id,
        receipt=projection_receipt,
    )
    payload = RawIngressCommittedPayloadV49C(
        raw_ingress_commit_id=_hash("raw-commit"),
        receipt=receipt,
        ingress_sequence=1,
        previous_raw_ingress_commit_id=None,
        stream_start_octet=0,
        stream_end_octet=len(raw),
        ordered_chunk_octet_lengths=(len(raw),),
        ordered_chunk_sha256=(hashlib.sha256(raw).hexdigest(),),
        raw_ingress_batch_sha256=_hash("raw-batch"),
        received_at=_NOW,
        received_monotonic_ns=10,
    )
    return TransportActorEventV49C.create(
        transport_subscription_policy_id=_hash("subscription-policy"),
        transport_session_id=_hash("session"),
        physical_scope_manifest_id=_hash("scope"),
        adapter_policy_id=_hash("adapter"),
        capture_partition_id=_hash("partition"),
        socket_lease_id=_hash("lease"),
        connection_generation=1,
        deployment_bundle_id=_hash("deployment"),
        writer_fence_token_sha256=_hash("writer-fence"),
        writer_fence_generation=1,
        monotonic_clock_domain_id=_hash("clock-domain"),
        driver_policy_id=driver_policy_id,
        recorded_at=_NOW,
        recorded_monotonic_ns=10,
        actor_sequence=actor_sequence,
        previous_event_id=previous_event_id,
        event_kind=TransportActorEventKindV49C.RAW_INGRESS_COMMITTED,
        payload=payload,
    )


def _raw_commit() -> RawIngressCommitV4:
    chunks = (b"\x89\x01x",)
    encoded = tuple(base64.b64encode(chunk).decode("ascii") for chunk in chunks)
    return RawIngressCommitV4(
        transport_subscription_policy_id=_hash("subscription-policy"),
        transport_session_id=_hash("session"),
        physical_scope_manifest_id=_hash("scope"),
        adapter_policy_id=_hash("adapter"),
        capture_partition_id=_hash("partition"),
        socket_lease_id=_hash("lease"),
        connection_generation=1,
        deployment_bundle_id=_hash("deployment"),
        writer_fence_token_sha256=_hash("writer-fence"),
        writer_fence_generation=1,
        ingress_sequence=1,
        raw_ingress_chunks_base64=encoded,
        raw_ingress_chunks_sha256=tuple(
            hashlib.sha256(chunk).hexdigest() for chunk in chunks
        ),
        raw_ingress_batch_sha256=sha256_digest(
            {
                "domain": "RiskYieldMMExactOrderedDecryptedIngressChunksV4_5",
                "ordered_chunks_base64": list(encoded),
            }
        ),
        received_at=_NOW,
        monotonic_clock_domain_id=_hash("clock-domain"),
        received_monotonic_ns=10,
    )


async def _empty_actor(
    journal: _StrictJournal,
    raw: TransportActorEventV49C,
    *,
    clock: _Clock | None = None,
) -> PhysicalTransportSessionActorV49C:
    clock = clock or _Clock()
    return await PhysicalTransportSessionActorV49C._restore(
        journal=journal,
        authority=TransportActorAuthorityV49C._from_event(raw),
        observation_clock=clock.observation,
    )


async def _actor_with_raw(
    *, clock: _Clock | None = None
) -> tuple[PhysicalTransportSessionActorV49C, _StrictJournal, TransportActorEventV49C]:
    journal = _StrictJournal()
    raw = _raw_event()
    actor = await _empty_actor(journal, raw, clock=clock)
    journal.commit_raw(raw)
    await actor.adopt_committed_raw_event(raw)
    return actor, journal, raw


def _parser_payload(raw_event: TransportActorEventV49C) -> ParserTransitionPayloadV49C:
    raw = raw_event.payload
    assert type(raw) is RawIngressCommittedPayloadV49C
    frame_bytes = b"\x89\x01x"
    mask = b"\x01\x02\x03\x04"
    pong = b"\x8a\x81" + mask + bytes((ord("x") ^ mask[0],))
    output_chunks = (pong[:3], pong[3:])
    output_encoded = tuple(
        base64.b64encode(chunk).decode("ascii") for chunk in output_chunks
    )
    frame = WebSocketFrameMetadataV49C(
        stream_start_octet=0,
        stream_end_octet=3,
        header_octets=2,
        payload_octets=1,
        opcode=WebSocketOpcodeV49C.PING,
        fin=True,
        masked=False,
        frame_sha256=hashlib.sha256(frame_bytes).hexdigest(),
        payload_sha256=hashlib.sha256(b"x").hexdigest(),
    )
    return ParserTransitionPayloadV49C(
        cursor_before=WebSocketParserCursorV49C(
            cursor_sequence=0,
            next_stream_octet=0,
            websocket_state=WebSocketParserStateV49C.OPEN,
        ),
        cursor_after=WebSocketParserCursorV49C(
            cursor_sequence=1,
            next_stream_octet=3,
            websocket_state=WebSocketParserStateV49C.OPEN,
        ),
        feed_unit_kind=ParserFeedUnitKindV49C.COMPLETE_FRAME,
        source_slices=(
            RawSourceSliceV49C(
                raw_ingress_commit_id=raw.raw_ingress_commit_id,
                projection_receipt_sequence=raw.receipt.global_sequence,
                projection_receipt_hash=raw.receipt.receipt_hash,
                stream_start_octet=0,
                stream_end_octet=3,
                raw_local_start_octet=0,
                raw_local_end_octet=3,
            ),
        ),
        frame=frame,
        parser_error=None,
        ordered_protocol_output_chunks_base64=output_encoded,
        ordered_protocol_output_chunks_sha256=tuple(
            hashlib.sha256(chunk).hexdigest() for chunk in output_chunks
        ),
        protocol_output_batch_sha256=sha256_digest(
            {
                "domain": _OUTPUT_DOMAIN,
                "ordered_chunks_base64": list(output_encoded),
            }
        ),
        send_eof_after_output=False,
        processed_at=_NOW + timedelta(seconds=2),
        processed_monotonic_ns=20,
    )


def _close_parser_payload(
    raw_event: TransportActorEventV49C,
) -> ParserTransitionPayloadV49C:
    raw = raw_event.payload
    assert type(raw) is RawIngressCommittedPayloadV49C
    frame_bytes = b"\x88\x00"
    mask = b"\x01\x02\x03\x04"
    close = b"\x88\x80" + mask
    encoded = (base64.b64encode(close).decode("ascii"),)
    return ParserTransitionPayloadV49C(
        cursor_before=WebSocketParserCursorV49C(
            cursor_sequence=0,
            next_stream_octet=0,
            websocket_state=WebSocketParserStateV49C.OPEN,
        ),
        cursor_after=WebSocketParserCursorV49C(
            cursor_sequence=1,
            next_stream_octet=len(frame_bytes),
            websocket_state=WebSocketParserStateV49C.CLOSING,
        ),
        feed_unit_kind=ParserFeedUnitKindV49C.COMPLETE_FRAME,
        source_slices=(
            RawSourceSliceV49C(
                raw_ingress_commit_id=raw.raw_ingress_commit_id,
                projection_receipt_sequence=raw.receipt.global_sequence,
                projection_receipt_hash=raw.receipt.receipt_hash,
                stream_start_octet=0,
                stream_end_octet=len(frame_bytes),
                raw_local_start_octet=0,
                raw_local_end_octet=len(frame_bytes),
            ),
        ),
        frame=WebSocketFrameMetadataV49C(
            stream_start_octet=0,
            stream_end_octet=len(frame_bytes),
            header_octets=2,
            payload_octets=0,
            opcode=WebSocketOpcodeV49C.CLOSE,
            fin=True,
            masked=False,
            frame_sha256=hashlib.sha256(frame_bytes).hexdigest(),
            payload_sha256=hashlib.sha256(b"").hexdigest(),
        ),
        parser_error=None,
        ordered_protocol_output_chunks_base64=encoded,
        ordered_protocol_output_chunks_sha256=(hashlib.sha256(close).hexdigest(),),
        protocol_output_batch_sha256=sha256_digest(
            {
                "domain": _OUTPUT_DOMAIN,
                "ordered_chunks_base64": list(encoded),
            }
        ),
        send_eof_after_output=False,
        processed_at=_NOW + timedelta(seconds=2),
        processed_monotonic_ns=20,
    )


def _automatic_wire_from_parser(
    parser_event: TransportActorEventV49C,
    *,
    label: str,
) -> OutboundWirePreparedPayloadV49C:
    parser = parser_event.payload
    assert type(parser) is ParserTransitionPayloadV49C
    assert parser.frame is not None
    logical_opcode = (
        WebSocketOpcodeV49C.PONG
        if parser.frame.opcode is WebSocketOpcodeV49C.PING
        else WebSocketOpcodeV49C.CLOSE
    )
    logical_payload = b"x" if logical_opcode is WebSocketOpcodeV49C.PONG else b""
    chunks = tuple(
        base64.b64decode(value, validate=True)
        for value in parser.ordered_protocol_output_chunks_base64
    )
    return OutboundWirePreparedPayloadV49C(
        outbound_operation_id=_hash(f"automatic-operation:{label}"),
        wire_origin=OutboundWireOriginV49C.AUTOMATIC_PROTOCOL,
        source_parser_event_id=parser_event.transport_actor_event_id,
        logical_opcode=logical_opcode,
        logical_payload_sha256=hashlib.sha256(logical_payload).hexdigest(),
        logical_payload_octets=len(logical_payload),
        ordered_wire_chunks_base64=(parser.ordered_protocol_output_chunks_base64),
        ordered_wire_chunks_sha256=(parser.ordered_protocol_output_chunks_sha256),
        wire_batch_sha256=parser.protocol_output_batch_sha256,
        wire_octets=sum(map(len, chunks)),
        prepared_at=_NOW + timedelta(seconds=3),
        prepared_monotonic_ns=100,
        send_not_after=_NOW + timedelta(seconds=30),
        send_not_after_monotonic_ns=30_000,
    )


def _wire_payload(
    label: str,
    *,
    parser_event_id: str | None = None,
) -> OutboundWirePreparedPayloadV49C:
    if parser_event_id is None:
        mask = b"\x01\x02\x03\x04"
        logical = label.encode()
        masked = bytes(value ^ mask[index % 4] for index, value in enumerate(logical))
        wire = bytes((0x81, 0x80 | len(logical))) + mask + masked
        chunks = (wire,)
        logical_opcode = WebSocketOpcodeV49C.TEXT
    else:
        mask = b"\x01\x02\x03\x04"
        logical = b"x"
        wire = b"\x8a\x81" + mask + bytes((logical[0] ^ mask[0],))
        chunks = (wire[:3], wire[3:])
        logical_opcode = WebSocketOpcodeV49C.PONG
    return OutboundWirePreparedPayloadV49C(
        outbound_operation_id=_hash(f"operation:{label}"),
        wire_origin=(
            OutboundWireOriginV49C.AUTOMATIC_PROTOCOL
            if parser_event_id is not None
            else OutboundWireOriginV49C.APPLICATION_INTENT
        ),
        source_parser_event_id=parser_event_id,
        logical_opcode=logical_opcode,
        logical_payload_sha256=hashlib.sha256(logical).hexdigest(),
        logical_payload_octets=len(logical),
        ordered_wire_chunks_base64=tuple(
            base64.b64encode(chunk).decode("ascii") for chunk in chunks
        ),
        ordered_wire_chunks_sha256=tuple(
            hashlib.sha256(chunk).hexdigest() for chunk in chunks
        ),
        wire_batch_sha256=_batch_hash(_OUTPUT_DOMAIN, chunks),
        wire_octets=len(wire),
        prepared_at=_NOW + timedelta(seconds=3),
        prepared_monotonic_ns=100,
        send_not_after=_NOW + timedelta(seconds=30),
        send_not_after_monotonic_ns=30_000,
    )


def _prepared_normal_close_wire() -> PreparedWebSocketWireV49C:
    logical = (1000).to_bytes(2, "big")
    mask = b"\x01\x02\x03\x04"
    masked = bytes(value ^ mask[index % 4] for index, value in enumerate(logical))
    frame = b"\x88\x82" + mask + masked
    prepared = object.__new__(PreparedWebSocketWireV49C)
    values = {
        "outbound_sequence": 1,
        "logical_opcode": 0x8,
        "logical_payload_sha256": hashlib.sha256(logical).hexdigest(),
        "logical_payload_octets": len(logical),
        "ordered_wire_chunks": (frame,),
        "ordered_wire_chunks_sha256": (hashlib.sha256(frame).hexdigest(),),
        "wire_batch_sha256": _batch_hash(_OUTPUT_DOMAIN, (frame,)),
        "wire_octets": len(frame),
    }
    for name, value in values.items():
        object.__setattr__(prepared, name, value)
    return prepared


def _permit_payload(
    wire_event: TransportActorEventV49C,
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
        consumed_at=_NOW + timedelta(seconds=4),
        consumed_monotonic_ns=200,
        send_not_after=wire.send_not_after,
        send_not_after_monotonic_ns=wire.send_not_after_monotonic_ns,
    )


def _tls_payload(
    wire_event: TransportActorEventV49C,
    permit_event: TransportActorEventV49C,
) -> TlsCiphertextPreparedPayloadV49C:
    wire = wire_event.payload
    assert type(wire) is OutboundWirePreparedPayloadV49C
    ciphertext = (b"0123456789",)
    return TlsCiphertextPreparedPayloadV49C(
        outbound_wire_prepared_event_id=wire_event.transport_actor_event_id,
        write_permit_consumed_event_id=permit_event.transport_actor_event_id,
        plaintext_batch_sha256=wire.wire_batch_sha256,
        plaintext_octets=wire.wire_octets,
        ordered_ciphertext_chunks_base64=tuple(
            base64.b64encode(chunk).decode("ascii") for chunk in ciphertext
        ),
        ordered_ciphertext_chunks_sha256=tuple(
            hashlib.sha256(chunk).hexdigest() for chunk in ciphertext
        ),
        ciphertext_batch_sha256=_batch_hash(_CIPHERTEXT_DOMAIN, ciphertext),
        ciphertext_octets=10,
        prepared_at=_NOW + timedelta(seconds=5),
        prepared_monotonic_ns=300,
    )


async def _actor_with_tls(
    *, clock: _Clock | None = None
) -> tuple[
    PhysicalTransportSessionActorV49C,
    _StrictJournal,
    TransportActorEventV49C,
    TransportActorEventV49C,
    TransportActorEventV49C,
]:
    actor, journal, _ = await _actor_with_raw(clock=clock)
    wire = await actor.prepare_outbound_wire(_wire_payload("application"))
    permit = await actor.consume_write_permit(_permit_payload(wire))
    tls = await actor.prepare_tls_ciphertext(_tls_payload(wire, permit))
    return actor, journal, wire, permit, tls


def test_actor_authority_cannot_be_caller_constructed() -> None:
    raw = _raw_event()
    values = {
        name: getattr(raw, name)
        for name in (
            "transport_subscription_policy_id",
            "transport_session_id",
            "physical_scope_manifest_id",
            "adapter_policy_id",
            "capture_partition_id",
            "socket_lease_id",
            "connection_generation",
            "deployment_bundle_id",
            "writer_fence_token_sha256",
            "writer_fence_generation",
            "monotonic_clock_domain_id",
            "driver_policy_id",
        )
    }
    with pytest.raises(TypeError, match="bound-session-derived"):
        TransportActorAuthorityV49C(**values)


@_run_async
async def test_raw_adoption_requires_projection_returned_object_not_copy() -> None:
    journal = _StrictJournal()
    raw = _raw_event()
    actor = await _empty_actor(journal, raw)
    journal.commit_raw(raw)
    copied = TransportActorEventV49C.from_mapping(raw.as_dict())
    assert copied == raw and copied is not raw

    with pytest.raises(PhysicalTransportSessionActorV49CJournalError):
        await actor.adopt_committed_raw_event(copied)

    assert not actor.is_fault_latched
    assert await actor.adopt_committed_raw_event(raw) is raw


@_run_async
async def test_v49d_raw_commit_and_adoption_is_one_locked_capability_sink() -> None:
    journal = _StrictJournal()
    authority_template = _raw_event()
    actor = await _empty_actor(journal, authority_template)
    raw = _raw_commit()

    result = await actor.commit_and_adopt_raw_ingress_v49d(raw)

    assert result is None
    assert len(actor.events) == len(journal.events) == 1
    committed_event = journal.events[0]
    assert actor.events[0] == committed_event
    assert committed_event.payload.raw_ingress_commit_id == raw.raw_ingress_commit_id
    with pytest.raises(RuntimeError, match="not the projection-returned"):
        await journal.resolve_exact_committed_raw_actor_event_v49c(
            event=committed_event
        )


@_run_async
async def test_v49d_raw_commit_rejects_authority_change_before_journal() -> None:
    journal = _StrictJournal()
    actor = await _empty_actor(journal, _raw_event())
    original = _raw_commit()
    altered = RawIngressCommitV4(
        **{
            **{name: getattr(original, name) for name in original.__dataclass_fields__},
            "capture_partition_id": _hash("other-partition"),
        }
    )

    with pytest.raises(
        PhysicalTransportSessionActorV49CJournalError,
        match="bound actor authority",
    ):
        await actor.commit_and_adopt_raw_ingress_v49d(altered)

    assert journal.events == []
    assert not actor.is_fault_latched


@_run_async
async def test_actor_rejects_nonadvancing_owner_event_clock_before_journal() -> None:
    journal = _StrictJournal()
    raw = _raw_event()
    actor = await PhysicalTransportSessionActorV49C._restore(
        journal=journal,
        authority=TransportActorAuthorityV49C._from_event(raw),
        observation_clock=lambda: (_NOW, 10),
    )
    journal.commit_raw(raw)
    await actor.adopt_committed_raw_event(raw)

    with pytest.raises(PhysicalTransportSessionActorV49COwnerError, match="clock"):
        await actor.prepare_outbound_wire(_wire_payload("regressed-clock"))

    assert journal.events == [raw]


@_run_async
async def test_raw_adoption_rejects_authority_override() -> None:
    journal = _StrictJournal()
    raw = _raw_event()
    actor = await _empty_actor(journal, raw)
    altered = _raw_event(driver_policy_id=_hash("forged-driver"))

    with pytest.raises(PhysicalTransportSessionActorV49CJournalError):
        await actor.adopt_committed_raw_event(altered)

    assert journal.events == []


@_run_async
async def test_automatic_and_application_wires_share_one_fifo() -> None:
    actor, _, raw = await _actor_with_raw()
    parser = await actor.append_parser_transition(_parser_payload(raw))
    automatic = await actor.prepare_outbound_wire(
        _wire_payload("automatic-pong", parser_event_id=parser.transport_actor_event_id)
    )
    application = await actor.prepare_outbound_wire(_wire_payload("application"))

    assert actor.outbound_queue_event_ids == (
        automatic.transport_actor_event_id,
        application.transport_actor_event_id,
    )
    assert actor.wire_queue_event_count_v49f == 2
    assert actor.wire_queue_octet_count_v49f == (
        automatic.payload.wire_octets + application.payload.wire_octets
    )
    with pytest.raises(PhysicalTransportSessionActorV49CQueueError):
        await actor.consume_write_permit(_permit_payload(application))

    permit = await actor.consume_write_permit(_permit_payload(automatic))
    assert permit.payload.outbound_wire_prepared_event_id == (
        automatic.transport_actor_event_id
    )


@_run_async
async def test_v49d_ordinary_parser_transition_remains_one_event() -> None:
    actor, journal, raw = await _actor_with_raw()
    before = len(journal.events)

    parser = await actor.append_parser_transition_v49d(_parser_payload(raw))

    assert len(journal.events) == before + 1
    assert journal.events[-1] is parser
    assert parser.event_kind is TransportActorEventKindV49C.PARSER_TRANSITION


@_run_async
async def test_v49d_close_parser_and_received_marker_are_one_ordered_batch() -> None:
    actor, journal, raw = await _actor_with_raw()

    parser = await actor.append_parser_transition_v49d(_close_parser_payload(raw))

    assert tuple(event.event_kind for event in journal.events[-2:]) == (
        TransportActorEventKindV49C.PARSER_TRANSITION,
        TransportActorEventKindV49C.TERMINAL_TRANSITION,
    )
    assert journal.events[-2] is parser
    assert journal.events[-1].payload.kind is (
        TerminalTransitionKindV49C.WS_CLOSE_RECEIVED
    )
    assert actor.terminal_state.ws_close_received


@pytest.mark.parametrize("failure_position", (1, 2))
@_run_async
async def test_v49d_close_parser_batch_rolls_back_at_every_insert_position(
    failure_position: int,
) -> None:
    actor, journal, raw = await _actor_with_raw()
    before_journal = tuple(journal.events)
    before_actor = actor.events
    journal.batch_fail_insert_at = failure_position

    with pytest.raises(
        PhysicalTransportSessionActorV49CJournalError,
        match="actor-batch append outcome is unknown",
    ):
        await actor.append_parser_transition_v49d(_close_parser_payload(raw))

    assert tuple(journal.events) == before_journal
    assert actor.events == before_actor
    assert actor.is_fault_latched


@_run_async
async def test_v49d_automatic_pong_and_permit_are_atomic_fifo_head() -> None:
    actor, journal, raw = await _actor_with_raw()
    parser = await actor.append_parser_transition_v49d(_parser_payload(raw))
    wire_payload = _automatic_wire_from_parser(parser, label="pong")

    wire, permit = await actor.prepare_automatic_wire_and_permit_v49d(
        wire_payload,
        permit_consumed_at=_NOW + timedelta(seconds=4),
        permit_consumed_monotonic_ns=200,
    )

    assert journal.events[-2:] == [wire, permit]
    assert wire.payload.wire_origin is OutboundWireOriginV49C.AUTOMATIC_PROTOCOL
    assert permit.payload.permit_id == derive_actor_write_permit_id_v49c(
        outbound_operation_id=wire.payload.outbound_operation_id,
        outbound_wire_prepared_event_id=wire.transport_actor_event_id,
        socket_lease_id=wire.socket_lease_id,
        writer_fence_token_sha256=wire.writer_fence_token_sha256,
        writer_fence_generation=wire.writer_fence_generation,
    )
    assert actor.oldest_outbound_wire_event_id == wire.transport_actor_event_id
    assert not actor.has_pending_automatic_protocol_output


@_run_async
async def test_v49d_automatic_preparation_rejects_nonautomatic_or_busy_fifo() -> None:
    actor, journal, raw = await _actor_with_raw()
    await actor.append_parser_transition_v49d(_parser_payload(raw))
    before = tuple(journal.events)

    with pytest.raises(PhysicalTransportSessionActorV49CQueueError):
        await actor.prepare_automatic_wire_and_permit_v49d(
            _wire_payload("not-automatic"),
            permit_consumed_at=_NOW + timedelta(seconds=4),
            permit_consumed_monotonic_ns=200,
        )
    assert tuple(journal.events) == before

    other_actor, other_journal, other_raw = await _actor_with_raw()
    await other_actor.prepare_outbound_wire(_wire_payload("existing-head"))
    other_parser = await other_actor.append_parser_transition_v49d(
        _parser_payload(other_raw)
    )
    other_before = tuple(other_journal.events)
    with pytest.raises(PhysicalTransportSessionActorV49CQueueError):
        await other_actor.prepare_automatic_wire_and_permit_v49d(
            _automatic_wire_from_parser(other_parser, label="busy"),
            permit_consumed_at=_NOW + timedelta(seconds=4),
            permit_consumed_monotonic_ns=200,
        )
    assert tuple(other_journal.events) == other_before


@_run_async
async def test_v49d_automatic_close_orders_sent_marker_before_permit() -> None:
    actor, journal, raw = await _actor_with_raw()
    parser = await actor.append_parser_transition_v49d(_close_parser_payload(raw))
    wire_payload = _automatic_wire_from_parser(parser, label="close")

    wire, permit = await actor.prepare_automatic_wire_and_permit_v49d(
        wire_payload,
        permit_consumed_at=_NOW + timedelta(seconds=4),
        permit_consumed_monotonic_ns=200,
    )

    assert journal.events[-3] is wire
    assert journal.events[-2].payload.kind is TerminalTransitionKindV49C.WS_CLOSE_SENT
    assert journal.events[-1] is permit
    assert permit.payload.outbound_wire_prepared_event_id == (
        wire.transport_actor_event_id
    )
    assert actor.terminal_state.ws_close_received
    assert actor.terminal_state.ws_close_sent


@pytest.mark.parametrize(
    ("close", "failure_position"),
    ((False, 1), (False, 2), (True, 1), (True, 2), (True, 3)),
)
@_run_async
async def test_v49d_automatic_batch_rolls_back_at_every_insert_position(
    close: bool,
    failure_position: int,
) -> None:
    actor, journal, raw = await _actor_with_raw()
    parser = await actor.append_parser_transition_v49d(
        _close_parser_payload(raw) if close else _parser_payload(raw)
    )
    before_journal = tuple(journal.events)
    before_actor = actor.events
    journal.batch_fail_insert_at = failure_position
    with pytest.raises(
        PhysicalTransportSessionActorV49CJournalError,
        match="actor-batch append outcome is unknown",
    ):
        await actor.prepare_automatic_wire_and_permit_v49d(
            _automatic_wire_from_parser(parser, label=f"failure-{failure_position}"),
            permit_consumed_at=_NOW + timedelta(seconds=4),
            permit_consumed_monotonic_ns=200,
        )

    assert tuple(journal.events) == before_journal
    assert actor.events == before_actor
    assert actor.is_fault_latched


@_run_async
async def test_close_wire_atomically_latches_obligation_and_blocks_application() -> (
    None
):
    actor, journal, _ = await _actor_with_raw()
    command = await actor.start_local_shutdown_command_v49e(timeout_seconds=30)
    prepared = _prepared_normal_close_wire()
    close, marker, permit = await actor.authorize_local_websocket_close_v49e(
        command,
        driver_evidence_nonce_sha256=_hash("local-close-driver-evidence"),
        prepare_effect=lambda **_values: prepared,
        signer=object(),
    )

    assert actor.terminal_state.ws_close_sent
    assert actor.terminal_state.ws_output_obligation_id == (
        close.payload.outbound_operation_id
    )
    assert marker.payload.kind is TerminalTransitionKindV49C.WS_CLOSE_SENT
    assert journal.events[-1] is permit
    with pytest.raises(PhysicalTransportSessionActorV49CQueueError, match="forbidden"):
        await actor.prepare_outbound_wire(_wire_payload("late-application"))


@_run_async
async def test_local_close_batch_failure_never_exposes_an_unmarked_wire() -> None:
    clock = _Clock()
    actor, journal, _ = await _actor_with_raw(clock=clock)
    command = await actor.start_local_shutdown_command_v49e(timeout_seconds=30)
    prepared = _prepared_normal_close_wire()
    journal.batch_fail_insert_at = 2
    with pytest.raises(PhysicalTransportSessionActorV49CJournalError):
        await actor.authorize_local_websocket_close_v49e(
            command,
            driver_evidence_nonce_sha256=_hash("failed-close-driver-evidence"),
            prepare_effect=lambda **_values: prepared,
            signer=object(),
        )
    wire_events_before = sum(
        event.event_kind is TransportActorEventKindV49C.OUTBOUND_WIRE_PREPARED
        for event in journal.events
    )

    journal.batch_fail_insert_at = None
    recovered = await PhysicalTransportSessionActorV49C._restore(
        journal=journal,
        authority=actor.authority,
        observation_clock=clock.observation,
    )
    wire_events_after = sum(
        event.event_kind is TransportActorEventKindV49C.OUTBOUND_WIRE_PREPARED
        for event in journal.events
    )
    assert wire_events_before == wire_events_after == 0
    assert not recovered.terminal_state.ws_close_sent


@_run_async
async def test_partial_send_records_exact_positive_count_and_never_reorders() -> None:
    actor, _, wire, permit, tls = await _actor_with_tls(clock=_Clock())
    observed: list[bytes] = []

    outcome = await actor.send_oldest_ciphertext(
        requested_octets=4,
        send_effect=lambda chunk: observed.append(chunk) or 3,
    )

    assert observed == [b"0123"]
    assert outcome.accepted_octets == 3
    assert actor.oldest_outbound_wire_event_id == wire.transport_actor_event_id
    assert outcome.result_event.payload.resulting_ciphertext_offset == 3
    assert outcome.attempt_event.payload.tls_ciphertext_prepared_event_id == (
        tls.transport_actor_event_id
    )
    assert outcome.result_event.payload.kernel_send_attempt_event_id == (
        outcome.attempt_event.transport_actor_event_id
    )
    assert outcome.attempt_started_event.event_kind is (
        TransportActorEventKindV49C.TERMINAL_TRANSITION
    )
    assert outcome.attempt_resolved_event.payload.kind is (
        TerminalTransitionKindV49C.SEND_ATTEMPT_RESOLVED
    )
    assert permit.transport_actor_event_id == (
        tls.payload.write_permit_consumed_event_id
    )


@_run_async
async def test_recovery_fences_known_partial_prefix_without_advancing_fifo() -> None:
    clock = _Clock()
    actor, journal, wire, _, _ = await _actor_with_tls(clock=clock)
    await actor.send_oldest_ciphertext(
        requested_octets=4,
        send_effect=lambda _chunk: 3,
    )

    recovered = await PhysicalTransportSessionActorV49C._restore(
        journal=journal,
        authority=actor.authority,
        observation_clock=clock.observation,
    )

    assert recovered.terminal_state.terminal_outcome is TerminalOutcomeV49C.FATAL
    assert recovered.oldest_outbound_wire_event_id == wire.transport_actor_event_id
    assert journal.events[-1].payload.kind is TerminalTransitionKindV49C.FATAL
    with pytest.raises(PhysicalTransportSessionActorV49CFaultLatched):
        await recovered.prepare_outbound_wire(_wire_payload("must-not-advance"))


@_run_async
async def test_recovery_materializes_full_local_dispatch_without_resend() -> None:
    clock = _Clock()
    actor, journal, wire, _, _ = await _actor_with_tls(clock=clock)
    calls = 0

    def send_once(chunk: bytes) -> int:
        nonlocal calls
        calls += 1
        return len(chunk)

    await actor.send_oldest_ciphertext(send_effect=send_once)
    recovered = await PhysicalTransportSessionActorV49C._restore(
        journal=journal,
        authority=actor.authority,
        observation_clock=clock.observation,
    )

    assert calls == 1
    assert recovered.oldest_outbound_wire_event_id is None
    assert recovered.wire_queue_event_count_v49f == 0
    assert recovered.wire_queue_octet_count_v49f == 0
    assert journal.events[-1].event_kind is (
        TransportActorEventKindV49C.OUTBOUND_DISPATCH_COMPLETED
    )
    assert journal.events[-1].payload.outbound_wire_prepared_event_id == (
        wire.transport_actor_event_id
    )


@_run_async
async def test_elapsed_wire_deadline_prevents_attempt_and_kernel_effect() -> None:
    actor, journal, _, _, _ = await _actor_with_tls(clock=_Clock(monotonic_ns=29_970))
    before = len(journal.events)
    called = False

    def forbidden_send(_chunk: bytes) -> int:
        nonlocal called
        called = True
        return 1

    with pytest.raises(PhysicalTransportSessionActorV49CQueueError, match="deadline"):
        await actor.send_oldest_ciphertext(send_effect=forbidden_send)

    assert not called
    assert len(journal.events) == before


@_run_async
async def test_send_cancellation_terminalizes_unknown_and_latches() -> None:
    actor, journal, _, _, _ = await _actor_with_tls(clock=_Clock())
    calls = 0
    entered = asyncio.Event()

    async def cancel_after_attempt(_chunk: bytes) -> int:
        nonlocal calls
        calls += 1
        entered.set()
        await asyncio.Future()
        raise AssertionError("unreachable")

    task = asyncio.create_task(
        actor.send_oldest_ciphertext(send_effect=cancel_after_attempt)
    )
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert calls == 1
    assert actor.terminal_state.terminal_outcome is TerminalOutcomeV49C.UNKNOWN_SEND
    assert actor.is_fault_latched
    assert journal.events[-1].payload.kind is TerminalTransitionKindV49C.UNKNOWN_SEND
    with pytest.raises(PhysicalTransportSessionActorV49CFaultLatched):
        await actor.prepare_outbound_wire(_wire_payload("forbidden"))


@_run_async
async def test_result_resolution_batch_commit_then_crash_recovers_without_resend() -> (
    None
):
    clock = _Clock()
    actor, journal, _, _, _ = await _actor_with_tls(clock=clock)
    calls = 0

    def fail_resolution(
        event: TransportActorEventV49C,
    ) -> BaseException | None:
        payload = event.payload
        if (
            event.event_kind is TransportActorEventKindV49C.TERMINAL_TRANSITION
            and payload.kind is TerminalTransitionKindV49C.SEND_ATTEMPT_RESOLVED
        ):
            return RuntimeError("crash after exact result")
        return None

    journal.fail_after = fail_resolution

    def send_once(chunk: bytes) -> int:
        nonlocal calls
        calls += 1
        return len(chunk)

    with pytest.raises(PhysicalTransportSessionActorV49CJournalError):
        await actor.send_oldest_ciphertext(send_effect=send_once)

    assert calls == 1
    assert journal.events[-1].payload.kind is (
        TerminalTransitionKindV49C.SEND_ATTEMPT_RESOLVED
    )
    journal.fail_after = lambda _event: None
    recovered = await PhysicalTransportSessionActorV49C._restore(
        journal=journal,
        authority=actor.authority,
        observation_clock=clock.observation,
    )
    assert not recovered.terminal_state.has_pending_send_attempt
    assert recovered.terminal_state.terminal_outcome is None
    assert journal.events[-2].payload.kind is (
        TerminalTransitionKindV49C.SEND_ATTEMPT_RESOLVED
    )
    assert journal.events[-1].event_kind is (
        TransportActorEventKindV49C.OUTBOUND_DISPATCH_COMPLETED
    )
    assert calls == 1


@_run_async
async def test_storage_failure_after_kernel_effect_recovers_unknown_without_replay() -> (
    None
):
    clock = _Clock()
    actor, journal, _, _, _ = await _actor_with_tls(clock=clock)
    calls = 0

    journal.fail_before = lambda event: (
        RuntimeError("disk unavailable")
        if event.event_kind is TransportActorEventKindV49C.KERNEL_SEND_RESULT
        else None
    )

    def send_once(chunk: bytes) -> int:
        nonlocal calls
        calls += 1
        return len(chunk)

    with pytest.raises(PhysicalTransportSessionActorV49CJournalError):
        await actor.send_oldest_ciphertext(send_effect=send_once)

    assert calls == 1
    assert actor.is_fault_latched
    assert journal.events[-1].payload.kind is (
        TerminalTransitionKindV49C.SEND_ATTEMPT_STARTED
    )

    journal.fail_before = lambda _event: None
    recovered = await PhysicalTransportSessionActorV49C._restore(
        journal=journal,
        authority=actor.authority,
        observation_clock=clock.observation,
    )
    assert recovered.terminal_state.terminal_outcome is (
        TerminalOutcomeV49C.UNKNOWN_SEND
    )
    assert journal.events[-1].payload.kind is TerminalTransitionKindV49C.UNKNOWN_SEND
    assert calls == 1


@_run_async
async def test_recovery_terminalizes_committed_attempt_start_batch_before_effect() -> (
    None
):
    clock = _Clock()
    actor, journal, _, _, _ = await _actor_with_tls(clock=clock)
    send_called = False
    failed = False

    def fail_first_terminal(event: TransportActorEventV49C) -> BaseException | None:
        nonlocal failed
        if (
            not failed
            and event.event_kind is TransportActorEventKindV49C.TERMINAL_TRANSITION
        ):
            failed = True
            return RuntimeError("crash before send-start marker")
        return None

    journal.fail_after = fail_first_terminal

    def must_not_send(_chunk: bytes) -> int:
        nonlocal send_called
        send_called = True
        return 1

    with pytest.raises(PhysicalTransportSessionActorV49CJournalError):
        await actor.send_oldest_ciphertext(send_effect=must_not_send)

    assert not send_called
    assert journal.events[-1].payload.kind is (
        TerminalTransitionKindV49C.SEND_ATTEMPT_STARTED
    )
    journal.fail_after = lambda _event: None
    recovered = await PhysicalTransportSessionActorV49C._restore(
        journal=journal,
        authority=actor.authority,
        observation_clock=clock.observation,
    )
    assert recovered.terminal_state.terminal_outcome is (
        TerminalOutcomeV49C.UNKNOWN_SEND
    )
    assert [event.payload.kind for event in journal.events[-2:]] == [
        TerminalTransitionKindV49C.SEND_ATTEMPT_STARTED,
        TerminalTransitionKindV49C.UNKNOWN_SEND,
    ]


@_run_async
async def test_cancellation_after_journal_commit_latches_ambiguous_storage() -> None:
    actor, journal, _ = await _actor_with_raw()
    journal.fail_after = lambda event: (
        asyncio.CancelledError()
        if event.event_kind is TransportActorEventKindV49C.OUTBOUND_WIRE_PREPARED
        else None
    )

    with pytest.raises(asyncio.CancelledError):
        await actor.prepare_outbound_wire(_wire_payload("committed-then-cancelled"))

    assert actor.is_fault_latched
    assert journal.events[-1].event_kind is (
        TransportActorEventKindV49C.OUTBOUND_WIRE_PREPARED
    )
    with pytest.raises(PhysicalTransportSessionActorV49CFaultLatched):
        await actor.prepare_outbound_wire(_wire_payload("must-not-continue"))


@_run_async
async def test_process_identity_change_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor, _, _ = await _actor_with_raw()
    monkeypatch.setattr(
        "riskyieldmm.trading.physical_transport_session_actor_v49c.os.getpid",
        lambda: actor._pid + 1,
    )

    with pytest.raises(PhysicalTransportSessionActorV49COwnerError, match="process"):
        await actor.prepare_outbound_wire(_wire_payload("forked"))


@_run_async
async def test_thread_identity_change_is_rejected() -> None:
    actor, _, _ = await _actor_with_raw()
    captured: list[BaseException] = []

    def run_in_thread() -> None:
        try:
            asyncio.run(actor.prepare_outbound_wire(_wire_payload("thread")))
        except BaseException as exc:
            captured.append(exc)

    thread = threading.Thread(target=run_in_thread)
    thread.start()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert len(captured) == 1
    assert isinstance(captured[0], PhysicalTransportSessionActorV49COwnerError)
    assert "thread" in str(captured[0])


def test_event_loop_identity_change_is_rejected() -> None:
    journal = _StrictJournal()
    raw = _raw_event()

    async def construct() -> PhysicalTransportSessionActorV49C:
        actor = await _empty_actor(journal, raw)
        journal.commit_raw(raw)
        await actor.adopt_committed_raw_event(raw)
        return actor

    first_loop = asyncio.new_event_loop()
    try:
        actor = first_loop.run_until_complete(construct())
    finally:
        first_loop.close()

    with pytest.raises(PhysicalTransportSessionActorV49COwnerError, match="event-loop"):
        asyncio.run(actor.prepare_outbound_wire(_wire_payload("new-loop")))


@_run_async
async def test_dispatch_cannot_complete_a_later_wire() -> None:
    actor, _, raw = await _actor_with_raw()
    parser = await actor.append_parser_transition(_parser_payload(raw))
    first = await actor.prepare_outbound_wire(
        _wire_payload("first", parser_event_id=parser.transport_actor_event_id)
    )
    second = await actor.prepare_outbound_wire(_wire_payload("second"))
    fake = OutboundDispatchCompletedPayloadV49C(
        outbound_wire_prepared_event_id=second.transport_actor_event_id,
        write_permit_consumed_event_id=_hash("permit"),
        tls_ciphertext_prepared_event_id=_hash("tls"),
        kernel_send_result_event_ids=(_hash("result"),),
        ciphertext_batch_sha256=_hash("ciphertext"),
        ciphertext_octets=1,
        submitted_ciphertext_octets=1,
        disposition="COMPLETE_LOCAL_SUBMISSION",
        completed_at=_NOW + timedelta(seconds=9),
        completed_monotonic_ns=900,
    )

    with pytest.raises(PhysicalTransportSessionActorV49CQueueError):
        await actor.complete_outbound_dispatch(fake)
    assert actor.oldest_outbound_wire_event_id == first.transport_actor_event_id

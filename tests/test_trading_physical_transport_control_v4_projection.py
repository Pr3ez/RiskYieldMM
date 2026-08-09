from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass, replace
from datetime import timedelta
from pathlib import Path

import pytest

from riskyieldmm.trading.canonical import sha256_digest
from riskyieldmm.trading.ledger_signing import Ed25519CheckpointSigner
from riskyieldmm.trading.physical_market_data import (
    PhysicalGateStage,
    PhysicalGateVerdict,
    PrefixHealth,
)
from riskyieldmm.trading.physical_projection_v4 import (
    PhysicalProjectionStoreV4,
    PhysicalProjectionV4ConflictError,
    PhysicalProjectionV4IdempotencyError,
    PhysicalProjectionV4WriterFenceError,
)
from riskyieldmm.trading.physical_transport_control_v4 import (
    InboundRfcControlOpcodeV4,
    InboundRfcControlTriggerV4,
    OutboundControlDispatchDispositionV4,
    OutboundControlDispatchResultV4,
    OutboundControlIntentV4,
    OutboundControlKindV4,
    OutboundControlWirePreparedV4,
    OutboundControlWritePermitConsumedV4,
    OutboundWebSocketOpcodeV4,
    RawIngressCommitV4,
    build_bybit_json_heartbeat_intent_v4,
)
from tests.test_trading_physical_authority_v4_projection import (
    append_one_message,
    exact_event_binding,
    fresh_status_bytes,
    live_information_set,
    receipt_count,
)
from tests.test_trading_physical_market_data_v3 import T0, digest, segment
from tests.test_trading_physical_transport_v4_projection import (
    FixedClock,
    TransportFixture,
    ack_payload,
    append_ack_occurrence,
    append_classified_capture,
    bind_ack,
    prepare_transport_fixture,
    primary_bar_capture,
)


class InjectedControlProjectionFailure(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ControlAuthority:
    fixture: TransportFixture
    socket_lease_id: str
    writer_fence_token_sha256: str
    writer_fence_generation: int


@dataclass(frozen=True, slots=True)
class ControlChain:
    raw: RawIngressCommitV4
    trigger: InboundRfcControlTriggerV4
    intent: OutboundControlIntentV4
    wire: OutboundControlWirePreparedV4
    permit: OutboundControlWritePermitConsumedV4
    dispatch: OutboundControlDispatchResultV4


def _b64(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _ingress_batch_hash(chunks: tuple[str, ...]) -> str:
    return sha256_digest(
        {
            "domain": "RiskYieldMMExactOrderedDecryptedIngressChunksV4_5",
            "ordered_chunks_base64": list(chunks),
        }
    )


def _wire_batch_hash(chunks: tuple[str, ...]) -> str:
    return sha256_digest(
        {
            "domain": "RiskYieldMMExactOrderedPreTlsWebSocketChunksV4_5",
            "ordered_chunks_base64": list(chunks),
        }
    )


def _server_control_frame(opcode: int, payload: bytes) -> bytes:
    assert len(payload) <= 125
    return bytes((0x80 | opcode, len(payload))) + payload


def _client_frame(
    opcode: int,
    payload: bytes,
    *,
    mask: bytes = b"\x01\x23\x45\x67",
) -> bytes:
    assert len(payload) <= 125
    masked = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
    return bytes((0x80 | opcode, 0x80 | len(payload))) + mask + masked


def _control_authority(
    store: PhysicalProjectionStoreV4,
    fixture: TransportFixture,
    *,
    label: str = "control",
) -> ControlAuthority:
    del label
    store.assert_transport_runtime_writer_fence(
        lease_token_sha256=fixture.writer_fence_token_sha256,
        generation=fixture.writer_fence_generation,
    )
    return ControlAuthority(
        fixture=fixture,
        socket_lease_id=fixture.socket_owner_binding.socket_lease_id,
        writer_fence_token_sha256=fixture.writer_fence_token_sha256,
        writer_fence_generation=fixture.writer_fence_generation,
    )


def _common(authority: ControlAuthority) -> dict[str, object]:
    fixture = authority.fixture
    return {
        "transport_subscription_policy_id": (
            fixture.policy.transport_subscription_policy_id
        ),
        "transport_session_id": fixture.session.transport_session_id,
        "physical_scope_manifest_id": fixture.scope.physical_scope_manifest_id,
        "adapter_policy_id": fixture.primary.adapter_policy_id,
        "capture_partition_id": fixture.session.capture_partition_id,
        "socket_lease_id": authority.socket_lease_id,
        "connection_generation": fixture.session.connection_generation,
        "deployment_bundle_id": fixture.session.deployment_bundle_id,
        "writer_fence_token_sha256": authority.writer_fence_token_sha256,
        "writer_fence_generation": authority.writer_fence_generation,
    }


def _raw_ingress(
    authority: ControlAuthority,
    *,
    ingress_sequence: int = 1,
    opcode: InboundRfcControlOpcodeV4 = InboundRfcControlOpcodeV4.PING,
    payload: bytes = b"projection-ping",
    received_offset_ms: int = 0,
    received_monotonic_ns: int = 300_000_000,
) -> RawIngressCommitV4:
    opcode_number = {
        InboundRfcControlOpcodeV4.CLOSE: 0x8,
        InboundRfcControlOpcodeV4.PING: 0x9,
        InboundRfcControlOpcodeV4.PONG: 0xA,
    }[opcode]
    frame = _server_control_frame(opcode_number, payload)
    split = min(3, len(frame))
    chunks = (_b64(frame[:split]), _b64(frame[split:]))
    return RawIngressCommitV4(
        **_common(authority),
        ingress_sequence=ingress_sequence,
        raw_ingress_chunks_base64=chunks,
        raw_ingress_chunks_sha256=tuple(
            hashlib.sha256(base64.b64decode(chunk)).hexdigest() for chunk in chunks
        ),
        raw_ingress_batch_sha256=_ingress_batch_hash(chunks),
        received_at=T0 + timedelta(milliseconds=received_offset_ms),
        monotonic_clock_domain_id=(authority.fixture.session.monotonic_clock_domain_id),
        received_monotonic_ns=received_monotonic_ns,
    )


def _trigger(
    raw: RawIngressCommitV4,
    *,
    opcode: InboundRfcControlOpcodeV4,
    payload: bytes,
    frame_offset: int = 0,
    frame_length: int | None = None,
) -> InboundRfcControlTriggerV4:
    return InboundRfcControlTriggerV4(
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
        frame_offset=frame_offset,
        frame_length=len(raw.raw_bytes) if frame_length is None else frame_length,
        opcode=opcode,
        payload_base64=_b64(payload),
        payload_sha256=hashlib.sha256(payload).hexdigest(),
        received_at=raw.received_at,
        monotonic_clock_domain_id=raw.monotonic_clock_domain_id,
        received_monotonic_ns=raw.received_monotonic_ns,
    )


def _reactive_intent(
    authority: ControlAuthority,
    trigger: InboundRfcControlTriggerV4,
    *,
    kind: OutboundControlKindV4 = OutboundControlKindV4.RFC_PONG,
    control_sequence: int = 1,
    previous_intent_id: str | None = None,
) -> OutboundControlIntentV4:
    authorized_at = trigger.received_at + timedelta(milliseconds=1)
    authorized_ns = trigger.received_monotonic_ns + 1_000_000
    return OutboundControlIntentV4(
        **_common(authority),
        control_sequence=control_sequence,
        previous_outbound_control_intent_id=previous_intent_id,
        control_kind=kind,
        scheduled_heartbeat_id=None,
        inbound_rfc_control_trigger_id=trigger.inbound_rfc_control_trigger_id,
        inbound_rfc_opcode=trigger.opcode,
        inbound_rfc_payload_base64=trigger.payload_base64,
        protocol_failure_evidence_id=None,
        logical_websocket_opcode=(
            OutboundWebSocketOpcodeV4.PONG
            if kind is OutboundControlKindV4.RFC_PONG
            else OutboundWebSocketOpcodeV4.CLOSE
        ),
        logical_payload_base64=trigger.payload_base64,
        logical_payload_sha256=trigger.payload_sha256,
        request_id=None,
        fences_session_authority=(kind is OutboundControlKindV4.RFC_CLOSE_REPLY),
        authorized_at=authorized_at,
        monotonic_clock_domain_id=trigger.monotonic_clock_domain_id,
        authorized_monotonic_ns=authorized_ns,
        send_not_after=authorized_at + timedelta(seconds=1),
        send_not_after_monotonic_ns=authorized_ns + 1_000_000_000,
    )


def _heartbeat_intent(
    authority: ControlAuthority,
    *,
    control_sequence: int = 1,
    previous_intent_id: str | None = None,
    authorized_offset_ms: int = 0,
    authorized_monotonic_ns: int = 300_000_000,
    label: str = "first",
    request_id: str | None = None,
) -> OutboundControlIntentV4:
    authorized_at = T0 + timedelta(milliseconds=authorized_offset_ms)
    return build_bybit_json_heartbeat_intent_v4(
        **_common(authority),
        control_sequence=control_sequence,
        previous_outbound_control_intent_id=previous_intent_id,
        scheduled_heartbeat_id=digest(f"{label}-heartbeat-schedule"),
        request_id=f"heartbeat-{label}" if request_id is None else request_id,
        authorized_at=authorized_at,
        monotonic_clock_domain_id=(authority.fixture.session.monotonic_clock_domain_id),
        authorized_monotonic_ns=authorized_monotonic_ns,
        send_not_after=authorized_at + timedelta(seconds=1),
        send_not_after_monotonic_ns=authorized_monotonic_ns + 1_000_000_000,
    )


def _protocol_failure_intent(
    authority: ControlAuthority,
    raw: RawIngressCommitV4,
) -> OutboundControlIntentV4:
    payload = (1002).to_bytes(2, "big") + b"untyped protocol failure"
    authorized_at = raw.received_at + timedelta(milliseconds=1)
    authorized_ns = raw.received_monotonic_ns + 1_000_000
    return OutboundControlIntentV4(
        **_common(authority),
        control_sequence=1,
        previous_outbound_control_intent_id=None,
        control_kind=OutboundControlKindV4.RFC_PROTOCOL_FAILURE_CLOSE,
        scheduled_heartbeat_id=None,
        inbound_rfc_control_trigger_id=None,
        inbound_rfc_opcode=None,
        inbound_rfc_payload_base64=None,
        protocol_failure_evidence_id=raw.raw_ingress_commit_id,
        logical_websocket_opcode=OutboundWebSocketOpcodeV4.CLOSE,
        logical_payload_base64=_b64(payload),
        logical_payload_sha256=hashlib.sha256(payload).hexdigest(),
        request_id=None,
        fences_session_authority=True,
        authorized_at=authorized_at,
        monotonic_clock_domain_id=raw.monotonic_clock_domain_id,
        authorized_monotonic_ns=authorized_ns,
        send_not_after=authorized_at + timedelta(seconds=1),
        send_not_after_monotonic_ns=authorized_ns + 1_000_000_000,
    )


def _wire(intent: OutboundControlIntentV4) -> OutboundControlWirePreparedV4:
    opcode = {
        OutboundWebSocketOpcodeV4.TEXT: 0x1,
        OutboundWebSocketOpcodeV4.PONG: 0xA,
        OutboundWebSocketOpcodeV4.CLOSE: 0x8,
    }[intent.logical_websocket_opcode]
    frame = _client_frame(opcode, intent.logical_payload_bytes)
    chunks = (_b64(frame[:4]), _b64(frame[4:]))
    return OutboundControlWirePreparedV4(
        outbound_control_intent_id=intent.outbound_control_intent_id,
        transport_session_id=intent.transport_session_id,
        socket_lease_id=intent.socket_lease_id,
        connection_generation=intent.connection_generation,
        deployment_bundle_id=intent.deployment_bundle_id,
        writer_fence_token_sha256=intent.writer_fence_token_sha256,
        writer_fence_generation=intent.writer_fence_generation,
        control_kind=intent.control_kind,
        logical_websocket_opcode=intent.logical_websocket_opcode,
        logical_payload_base64=intent.logical_payload_base64,
        logical_payload_sha256=intent.logical_payload_sha256,
        wire_chunks_base64=chunks,
        wire_chunks_sha256=tuple(
            hashlib.sha256(base64.b64decode(chunk)).hexdigest() for chunk in chunks
        ),
        wire_batch_sha256=_wire_batch_hash(chunks),
        wire_octet_length=len(frame),
        prepared_at=intent.authorized_at + timedelta(milliseconds=1),
        monotonic_clock_domain_id=intent.monotonic_clock_domain_id,
        prepared_monotonic_ns=intent.authorized_monotonic_ns + 1_000_000,
        send_not_after=intent.send_not_after,
        send_not_after_monotonic_ns=intent.send_not_after_monotonic_ns,
    )


def _permit(
    wire: OutboundControlWirePreparedV4,
) -> OutboundControlWritePermitConsumedV4:
    return OutboundControlWritePermitConsumedV4(
        outbound_control_intent_id=wire.outbound_control_intent_id,
        outbound_control_wire_prepared_id=(wire.outbound_control_wire_prepared_id),
        transport_session_id=wire.transport_session_id,
        socket_lease_id=wire.socket_lease_id,
        connection_generation=wire.connection_generation,
        deployment_bundle_id=wire.deployment_bundle_id,
        writer_fence_token_sha256=wire.writer_fence_token_sha256,
        writer_fence_generation=wire.writer_fence_generation,
        control_kind=wire.control_kind,
        wire_batch_sha256=wire.wire_batch_sha256,
        wire_octet_length=wire.wire_octet_length,
        one_shot_attempt_ordinal=1,
        wire_prepared_at=wire.prepared_at,
        monotonic_clock_domain_id=wire.monotonic_clock_domain_id,
        wire_prepared_monotonic_ns=wire.prepared_monotonic_ns,
        permit_consumed_at=wire.prepared_at + timedelta(milliseconds=1),
        permit_consumed_monotonic_ns=wire.prepared_monotonic_ns + 1_000_000,
        send_not_after=wire.send_not_after,
        send_not_after_monotonic_ns=wire.send_not_after_monotonic_ns,
    )


def _dispatch(
    permit: OutboundControlWritePermitConsumedV4,
    *,
    signer: Ed25519CheckpointSigner,
    disposition: OutboundControlDispatchDispositionV4 = (
        OutboundControlDispatchDispositionV4.SENT
    ),
) -> OutboundControlDispatchResultV4:
    unknown = disposition is OutboundControlDispatchDispositionV4.UNKNOWN_DELIVERY
    return OutboundControlDispatchResultV4.create_signed(
        signer=signer,
        outbound_control_intent_id=permit.outbound_control_intent_id,
        outbound_control_wire_prepared_id=(permit.outbound_control_wire_prepared_id),
        transport_session_id=permit.transport_session_id,
        socket_lease_id=permit.socket_lease_id,
        connection_generation=permit.connection_generation,
        deployment_bundle_id=permit.deployment_bundle_id,
        writer_fence_token_sha256=permit.writer_fence_token_sha256,
        writer_fence_generation=permit.writer_fence_generation,
        control_kind=permit.control_kind,
        wire_batch_sha256=permit.wire_batch_sha256,
        wire_octet_length=permit.wire_octet_length,
        permit_id=permit.permit_id,
        permit_consumed=True,
        one_shot_attempt_ordinal=permit.one_shot_attempt_ordinal,
        disposition=disposition,
        wire_prepared_at=permit.wire_prepared_at,
        monotonic_clock_domain_id=permit.monotonic_clock_domain_id,
        wire_prepared_monotonic_ns=permit.wire_prepared_monotonic_ns,
        dispatch_started_at=permit.permit_consumed_at + timedelta(milliseconds=1),
        dispatch_started_monotonic_ns=permit.permit_consumed_monotonic_ns + 1_000_000,
        dispatch_outcome_at=permit.permit_consumed_at + timedelta(milliseconds=2),
        dispatch_outcome_monotonic_ns=permit.permit_consumed_monotonic_ns + 2_000_000,
        send_not_after=permit.send_not_after,
        send_not_after_monotonic_ns=permit.send_not_after_monotonic_ns,
        bytes_submitted_to_tls=(
            permit.wire_octet_length // 2 if unknown else permit.wire_octet_length
        ),
        error_class_digest=digest("tls-write-uncertain") if unknown else None,
    )


def _build_reactive_chain(
    authority: ControlAuthority,
    *,
    opcode: InboundRfcControlOpcodeV4 = InboundRfcControlOpcodeV4.PING,
    kind: OutboundControlKindV4 = OutboundControlKindV4.RFC_PONG,
    payload: bytes = b"projection-ping",
    disposition: OutboundControlDispatchDispositionV4 = (
        OutboundControlDispatchDispositionV4.SENT
    ),
    received_offset_ms: int = 0,
    received_monotonic_ns: int = 300_000_000,
) -> ControlChain:
    raw = _raw_ingress(
        authority,
        opcode=opcode,
        payload=payload,
        received_offset_ms=received_offset_ms,
        received_monotonic_ns=received_monotonic_ns,
    )
    trigger = _trigger(raw, opcode=opcode, payload=payload)
    intent = _reactive_intent(authority, trigger, kind=kind)
    wire = _wire(intent)
    permit = _permit(wire)
    dispatch = _dispatch(
        permit,
        signer=authority.fixture.signer,
        disposition=disposition,
    )
    return ControlChain(raw, trigger, intent, wire, permit, dispatch)


def _append_chain(
    store: PhysicalProjectionStoreV4,
    clock: FixedClock,
    chain: ControlChain,
    *,
    prefix: str,
) -> None:
    clock.value = chain.raw.received_at
    assert (
        store.append_raw_ingress_commit(
            chain.raw,
            idempotency_key=f"{prefix}-raw",
        )
        == chain.raw
    )
    clock.value = chain.intent.authorized_at
    assert (
        store.append_inbound_rfc_control_trigger(
            chain.trigger,
            idempotency_key=f"{prefix}-trigger",
        )
        == chain.trigger
    )
    assert (
        store.append_outbound_control_intent(
            chain.intent,
            idempotency_key=f"{prefix}-intent",
        )
        == chain.intent
    )
    clock.value = chain.wire.prepared_at
    assert (
        store.append_outbound_control_wire_prepared(
            chain.wire,
            idempotency_key=f"{prefix}-wire",
        )
        == chain.wire
    )
    clock.value = chain.permit.permit_consumed_at
    assert (
        store.consume_outbound_control_write_permit(
            chain.wire.outbound_control_wire_prepared_id,
            permit_consumed_at=chain.permit.permit_consumed_at,
            permit_consumed_monotonic_ns=(chain.permit.permit_consumed_monotonic_ns),
            idempotency_key=f"{prefix}-permit",
        )
        == chain.permit
    )
    clock.value = chain.dispatch.dispatch_outcome_at
    assert (
        store.append_outbound_control_dispatch_result(
            chain.dispatch,
            idempotency_key=f"{prefix}-dispatch",
        )
        == chain.dispatch
    )


def test_full_control_chain_is_idempotent_verified_and_reopens(
    tmp_path: Path,
) -> None:
    path = tmp_path / "full-control-chain.sqlite3"
    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(path, clock=clock) as store:
        fixture = prepare_transport_fixture(store, clock=clock, authorize=False)
        authority = _control_authority(store, fixture)
        chain = _build_reactive_chain(authority)

        clock.value = chain.raw.received_at
        assert (
            store.append_raw_ingress_commit(
                chain.raw,
                idempotency_key="full-raw",
            )
            == chain.raw
        )
        with pytest.raises(PhysicalProjectionV4IdempotencyError):
            store.append_raw_ingress_commit(
                replace(
                    chain.raw,
                    received_at=chain.raw.received_at + timedelta(microseconds=1),
                    received_monotonic_ns=chain.raw.received_monotonic_ns + 1,
                ),
                idempotency_key="full-raw",
            )
        clock.value = chain.intent.authorized_at
        assert (
            store.append_inbound_rfc_control_trigger(
                chain.trigger,
                idempotency_key="full-trigger",
            )
            == chain.trigger
        )
        assert (
            store.append_outbound_control_intent(
                chain.intent,
                idempotency_key="full-intent",
            )
            == chain.intent
        )
        clock.value = chain.wire.prepared_at
        assert (
            store.append_outbound_control_wire_prepared(
                chain.wire,
                idempotency_key="full-wire",
            )
            == chain.wire
        )
        clock.value = chain.permit.permit_consumed_at
        assert (
            store.consume_outbound_control_write_permit(
                chain.wire.outbound_control_wire_prepared_id,
                permit_consumed_at=chain.permit.permit_consumed_at,
                permit_consumed_monotonic_ns=(
                    chain.permit.permit_consumed_monotonic_ns
                ),
                idempotency_key="full-permit",
            )
            == chain.permit
        )

        foreign_dispatch = _dispatch(
            chain.permit,
            signer=Ed25519CheckpointSigner.generate(),
        )
        clock.value = foreign_dispatch.dispatch_outcome_at
        with pytest.raises(PhysicalProjectionV4ConflictError):
            store.append_outbound_control_dispatch_result(
                foreign_dispatch,
                idempotency_key="foreign-key-dispatch",
            )
        assert store.verify().outbound_control_dispatch_result_count == 0

        assert (
            store.append_outbound_control_dispatch_result(
                chain.dispatch,
                idempotency_key="full-dispatch",
            )
            == chain.dispatch
        )
        before_retry = receipt_count(store)
        assert (
            store.append_raw_ingress_commit(
                chain.raw,
                idempotency_key="full-raw",
            )
            == chain.raw
        )
        assert (
            store.append_inbound_rfc_control_trigger(
                chain.trigger,
                idempotency_key="full-trigger",
            )
            == chain.trigger
        )
        assert (
            store.append_outbound_control_intent(
                chain.intent,
                idempotency_key="full-intent",
            )
            == chain.intent
        )
        assert (
            store.append_outbound_control_wire_prepared(
                chain.wire,
                idempotency_key="full-wire",
            )
            == chain.wire
        )
        with pytest.raises(PhysicalProjectionV4ConflictError):
            store.consume_outbound_control_write_permit(
                chain.wire.outbound_control_wire_prepared_id,
                permit_consumed_at=chain.permit.permit_consumed_at,
                permit_consumed_monotonic_ns=(
                    chain.permit.permit_consumed_monotonic_ns
                ),
                idempotency_key="full-permit",
            )
        assert (
            store.append_outbound_control_dispatch_result(
                chain.dispatch,
                idempotency_key="full-dispatch",
            )
            == chain.dispatch
        )
        assert receipt_count(store) == before_retry

        report = store.verify()
        assert report.raw_ingress_commit_count == 1
        assert report.inbound_rfc_control_trigger_count == 1
        assert report.outbound_control_intent_count == 1
        assert report.outbound_control_wire_prepared_count == 1
        assert report.outbound_control_write_permit_consumed_count == 1
        assert report.outbound_control_dispatch_result_count == 1

    with PhysicalProjectionStoreV4(path, clock=clock) as reopened:
        report = reopened.verify()
        assert report.raw_ingress_commit_count == 1
        assert report.inbound_rfc_control_trigger_count == 1
        assert report.outbound_control_intent_count == 1
        assert report.outbound_control_wire_prepared_count == 1
        assert report.outbound_control_write_permit_consumed_count == 1
        assert report.outbound_control_dispatch_result_count == 1


def test_raw_sequence_orphan_trigger_socket_and_writer_fence_rejections(
    tmp_path: Path,
) -> None:
    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(
        tmp_path / "control-authority-rejections.sqlite3",
        clock=clock,
    ) as store:
        fixture = prepare_transport_fixture(store, clock=clock, authorize=False)
        authority = _control_authority(store, fixture, label="authority-rejections")
        clock.value = T0 + timedelta(milliseconds=10)

        with pytest.raises(PhysicalProjectionV4ConflictError):
            store.append_raw_ingress_commit(
                _raw_ingress(authority, ingress_sequence=2),
                idempotency_key="raw-gap",
            )

        raw = _raw_ingress(authority)
        store.append_raw_ingress_commit(raw, idempotency_key="authority-raw")
        trigger = _trigger(
            raw,
            opcode=InboundRfcControlOpcodeV4.PING,
            payload=b"projection-ping",
        )
        with pytest.raises(PhysicalProjectionV4ConflictError):
            store.append_inbound_rfc_control_trigger(
                replace(trigger, raw_ingress_commit_id=digest("orphan-raw")),
                idempotency_key="orphan-trigger",
            )

        raw_two = _raw_ingress(
            authority,
            ingress_sequence=2,
            received_offset_ms=1,
            received_monotonic_ns=301_000_000,
        )
        with pytest.raises(PhysicalProjectionV4ConflictError):
            store.append_raw_ingress_commit(
                replace(raw_two, socket_lease_id=digest("another-socket")),
                idempotency_key="cross-socket-raw",
            )
        with pytest.raises(PhysicalProjectionV4WriterFenceError):
            store.append_raw_ingress_commit(
                replace(
                    raw_two,
                    writer_fence_token_sha256=digest("stale-writer-fence"),
                ),
                idempotency_key="stale-fence-raw",
            )

        report = store.verify()
        assert report.raw_ingress_commit_count == 1
        assert report.inbound_rfc_control_trigger_count == 0


def test_heartbeat_uses_precommitted_socket_owner_without_mutating_it(
    tmp_path: Path,
) -> None:
    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(
        tmp_path / "heartbeat-first.sqlite3",
        clock=clock,
    ) as store:
        fixture = prepare_transport_fixture(store, clock=clock, authorize=False)
        authority = _control_authority(store, fixture, label="heartbeat-first")
        owner_before = store._connection.execute(  # noqa: SLF001
            "SELECT * FROM transport_control_socket_bindings"
        ).fetchone()
        assert owner_before is not None
        heartbeat = _heartbeat_intent(authority)
        clock.value = T0 + timedelta(milliseconds=10)

        assert (
            store.append_outbound_control_intent(
                heartbeat,
                idempotency_key="heartbeat-first-intent",
            )
            == heartbeat
        )
        raw = _raw_ingress(
            authority,
            received_offset_ms=2,
            received_monotonic_ns=302_000_000,
        )
        assert (
            store.append_raw_ingress_commit(
                raw,
                idempotency_key="heartbeat-first-raw",
            )
            == raw
        )

        report = store.verify()
        assert report.outbound_control_intent_count == 1
        assert report.raw_ingress_commit_count == 1
        assert (
            store._connection.execute(  # noqa: SLF001
                "SELECT * FROM transport_control_socket_bindings"
            ).fetchone()
            == owner_before
        )
        assert store._connection.execute(  # noqa: SLF001
            "SELECT count(*) FROM transport_control_socket_bindings"
        ).fetchone() == (1,)


def test_heartbeat_request_id_cannot_reuse_subscription_request_id(
    tmp_path: Path,
) -> None:
    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(
        tmp_path / "heartbeat-subscription-request-collision.sqlite3",
        clock=clock,
    ) as store:
        fixture = prepare_transport_fixture(store, clock=clock, authorize=True)
        assert fixture.intent is not None
        authority = _control_authority(store, fixture, label="request-collision")
        heartbeat = _heartbeat_intent(
            authority,
            label="subscription-collision",
            request_id=fixture.intent.request_id,
        )
        clock.value = heartbeat.authorized_at

        with pytest.raises(PhysicalProjectionV4ConflictError):
            store.append_outbound_control_intent(
                heartbeat,
                idempotency_key="heartbeat-subscription-request-collision",
            )
        assert store.verify().outbound_control_intent_count == 0


def test_close_intent_allows_its_dispatch_then_fences_later_control(
    tmp_path: Path,
) -> None:
    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(
        tmp_path / "close-fence.sqlite3",
        clock=clock,
    ) as store:
        fixture = prepare_transport_fixture(store, clock=clock, authorize=False)
        authority = _control_authority(store, fixture, label="close-fence")
        payload = (1000).to_bytes(2, "big") + b"normal"
        chain = _build_reactive_chain(
            authority,
            opcode=InboundRfcControlOpcodeV4.CLOSE,
            kind=OutboundControlKindV4.RFC_CLOSE_REPLY,
            payload=payload,
        )
        _append_chain(store, clock, chain, prefix="close")

        later_raw = _raw_ingress(
            authority,
            ingress_sequence=2,
            payload=b"too-late",
            received_offset_ms=10,
            received_monotonic_ns=400_000_000,
        )
        clock.value = later_raw.received_at + timedelta(milliseconds=1)
        with pytest.raises(PhysicalProjectionV4ConflictError):
            store.append_raw_ingress_commit(
                later_raw,
                idempotency_key="after-close-raw",
            )
        with pytest.raises(PhysicalProjectionV4ConflictError):
            store.authorize_outbound_subscription_intent(
                fixture.session.transport_session_id,
                idempotency_key="after-close-subscription-intent",
            )
        assert store.verify().outbound_control_dispatch_result_count == 1


def test_inbound_close_trigger_fences_but_allows_exact_reply_continuation(
    tmp_path: Path,
) -> None:
    path = tmp_path / "inbound-close-crash-prefix.sqlite3"
    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(path, clock=clock) as store:
        fixture = prepare_transport_fixture(store, clock=clock, authorize=False)
        authority = _control_authority(store, fixture, label="close-prefix")
        close_payload = (1000).to_bytes(2, "big") + b"normal"
        ping_payload = b"must-not-continue"
        close_frame = _server_control_frame(0x8, close_payload)
        ping_frame = _server_control_frame(0x9, ping_payload)
        raw_chunks = (_b64(close_frame), _b64(ping_frame))
        raw = replace(
            _raw_ingress(
                authority,
                opcode=InboundRfcControlOpcodeV4.CLOSE,
                payload=close_payload,
            ),
            raw_ingress_chunks_base64=raw_chunks,
            raw_ingress_chunks_sha256=tuple(
                hashlib.sha256(base64.b64decode(chunk)).hexdigest()
                for chunk in raw_chunks
            ),
            raw_ingress_batch_sha256=_ingress_batch_hash(raw_chunks),
        )
        close_trigger = _trigger(
            raw,
            opcode=InboundRfcControlOpcodeV4.CLOSE,
            payload=close_payload,
            frame_length=len(close_frame),
        )
        ping_trigger = _trigger(
            raw,
            opcode=InboundRfcControlOpcodeV4.PING,
            payload=ping_payload,
            frame_offset=len(close_frame),
            frame_length=len(ping_frame),
        )
        intent = _reactive_intent(
            authority,
            close_trigger,
            kind=OutboundControlKindV4.RFC_CLOSE_REPLY,
        )
        wire = _wire(intent)
        permit = _permit(wire)
        dispatch = _dispatch(permit, signer=fixture.signer)

        clock.value = raw.received_at
        store.append_raw_ingress_commit(raw, idempotency_key="close-prefix-raw")
        clock.value = intent.authorized_at
        store.append_inbound_rfc_control_trigger(
            close_trigger,
            idempotency_key="close-prefix-trigger",
        )

        with pytest.raises(PhysicalProjectionV4ConflictError):
            store.authorize_outbound_subscription_intent(
                fixture.session.transport_session_id,
                idempotency_key="close-prefix-subscription",
            )
        with pytest.raises(PhysicalProjectionV4ConflictError):
            store.append_raw_ingress_commit(
                _raw_ingress(
                    authority,
                    ingress_sequence=2,
                    payload=b"after-close",
                    received_offset_ms=1,
                    received_monotonic_ns=400_000_000,
                ),
                idempotency_key="close-prefix-later-raw",
            )
        with pytest.raises(PhysicalProjectionV4ConflictError):
            store.append_inbound_rfc_control_trigger(
                ping_trigger,
                idempotency_key="close-prefix-ping-trigger",
            )

        prefix_report = store.verify()
        assert prefix_report.raw_ingress_commit_count == 1
        assert prefix_report.inbound_rfc_control_trigger_count == 1
        assert prefix_report.outbound_control_intent_count == 0

        assert (
            store.append_outbound_control_intent(
                intent,
                idempotency_key="close-prefix-reply-intent",
            )
            == intent
        )
        clock.value = wire.prepared_at
        assert (
            store.append_outbound_control_wire_prepared(
                wire,
                idempotency_key="close-prefix-reply-wire",
            )
            == wire
        )
        clock.value = permit.permit_consumed_at
        assert (
            store.consume_outbound_control_write_permit(
                wire.outbound_control_wire_prepared_id,
                permit_consumed_at=permit.permit_consumed_at,
                permit_consumed_monotonic_ns=permit.permit_consumed_monotonic_ns,
                idempotency_key="close-prefix-reply-permit",
            )
            == permit
        )
        clock.value = dispatch.dispatch_outcome_at
        assert (
            store.append_outbound_control_dispatch_result(
                dispatch,
                idempotency_key="close-prefix-reply-dispatch",
            )
            == dispatch
        )
        report = store.verify()
        assert report.raw_ingress_commit_count == 1
        assert report.inbound_rfc_control_trigger_count == 1
        assert report.outbound_control_intent_count == 1
        assert report.outbound_control_wire_prepared_count == 1
        assert report.outbound_control_write_permit_consumed_count == 1
        assert report.outbound_control_dispatch_result_count == 1

    with PhysicalProjectionStoreV4(path, clock=clock) as reopened:
        report = reopened.verify()
        assert report.raw_ingress_commit_count == 1
        assert report.inbound_rfc_control_trigger_count == 1
        assert report.outbound_control_intent_count == 1
        assert report.outbound_control_wire_prepared_count == 1
        assert report.outbound_control_write_permit_consumed_count == 1
        assert report.outbound_control_dispatch_result_count == 1


def test_unknown_delivery_fences_all_later_control(tmp_path: Path) -> None:
    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(
        tmp_path / "unknown-delivery-fence.sqlite3",
        clock=clock,
    ) as store:
        fixture = prepare_transport_fixture(store, clock=clock, authorize=False)
        authority = _control_authority(store, fixture, label="unknown-fence")
        chain = _build_reactive_chain(
            authority,
            disposition=OutboundControlDispatchDispositionV4.UNKNOWN_DELIVERY,
        )
        _append_chain(store, clock, chain, prefix="unknown")

        later_raw = _raw_ingress(
            authority,
            ingress_sequence=2,
            payload=b"do-not-retry",
            received_offset_ms=10,
            received_monotonic_ns=400_000_000,
        )
        clock.value = later_raw.received_at + timedelta(milliseconds=1)
        with pytest.raises(PhysicalProjectionV4ConflictError):
            store.append_raw_ingress_commit(
                later_raw,
                idempotency_key="after-unknown-raw",
            )
        with pytest.raises(PhysicalProjectionV4ConflictError):
            store.authorize_outbound_subscription_intent(
                fixture.session.transport_session_id,
                idempotency_key="after-unknown-subscription-intent",
            )
        assert store.verify().outbound_control_dispatch_result_count == 1


@pytest.mark.parametrize(
    ("fence_kind", "expected_fence_message"),
    (
        ("CLOSE", "durable inbound Close fenced general authority"),
        ("UNKNOWN_DELIVERY", "unknown control delivery fenced"),
    ),
)
def test_control_fence_rejects_pending_ack_and_prospective_primary_capture(
    tmp_path: Path,
    fence_kind: str,
    expected_fence_message: str,
) -> None:
    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(
        tmp_path / f"cross-path-{fence_kind.lower()}.sqlite3",
        clock=clock,
    ) as store:
        fixture = prepare_transport_fixture(store, clock=clock, authorize=True)
        assert fixture.intent is not None
        ack = append_ack_occurrence(
            store,
            clock=clock,
            fixture=fixture,
            intent=fixture.intent,
            payload=ack_payload(
                request_id=fixture.intent.request_id,
                provider_connection_id=f"provider-{fence_kind.lower()}",
            ),
            sequence=1,
            received_at=T0 + timedelta(milliseconds=10),
            idempotency_suffix=f"cross-path-{fence_kind.lower()}-ack",
        )
        authority = _control_authority(
            store,
            fixture,
            label=f"cross-path-{fence_kind.lower()}",
        )
        received_offset_ms = (
            int(
                (max(clock.value, T0 + timedelta(seconds=1)) - T0).total_seconds()
                * 1000
            )
            + 1
        )
        if fence_kind == "CLOSE":
            close_payload = (1000).to_bytes(2, "big") + b"normal"
            chain = _build_reactive_chain(
                authority,
                opcode=InboundRfcControlOpcodeV4.CLOSE,
                kind=OutboundControlKindV4.RFC_CLOSE_REPLY,
                payload=close_payload,
                received_offset_ms=received_offset_ms,
                received_monotonic_ns=4_000_000_000,
            )
            clock.value = chain.raw.received_at
            store.append_raw_ingress_commit(
                chain.raw,
                idempotency_key="cross-path-close-raw",
            )
            clock.value = chain.intent.authorized_at
            store.append_inbound_rfc_control_trigger(
                chain.trigger,
                idempotency_key="cross-path-close-trigger",
            )
        else:
            chain = _build_reactive_chain(
                authority,
                disposition=(OutboundControlDispatchDispositionV4.UNKNOWN_DELIVERY),
                received_offset_ms=received_offset_ms,
                received_monotonic_ns=4_000_000_000,
            )
            _append_chain(store, clock, chain, prefix="cross-path-unknown")

        with pytest.raises(
            PhysicalProjectionV4ConflictError,
            match=expected_fence_message,
        ):
            bind_ack(
                store,
                clock=clock,
                fixture=fixture,
                intent=fixture.intent,
                occurrence=ack,
                idempotency_key=f"ack-after-{fence_kind.lower()}",
            )

        if fence_kind == "CLOSE":
            assert (
                store.append_outbound_control_intent(
                    chain.intent,
                    idempotency_key="cross-path-close-intent",
                )
                == chain.intent
            )

        capture_received_at = clock.value + timedelta(milliseconds=1)
        prospective_capture = primary_bar_capture(
            fixture=fixture,
            intent=fixture.intent,
            sequence=2,
            bar_start=T0,
            received_at=capture_received_at,
            parent=ack.capture,
        )
        clock.value = capture_received_at + timedelta(milliseconds=100)
        with pytest.raises(
            PhysicalProjectionV4ConflictError,
            match=expected_fence_message,
        ):
            append_one_message(
                store,
                scope=fixture.scope,
                capture=prospective_capture,
                idempotency_key=f"capture-after-{fence_kind.lower()}",
            )

        report = store.verify()
        assert report.subscription_ack_binding_count == 0
        assert report.message_count == 1


def test_healthy_decision_gate_abstains_after_durable_close_trigger(
    tmp_path: Path,
) -> None:
    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(
        tmp_path / "healthy-gate-after-close.sqlite3",
        clock=clock,
    ) as store:
        fixture = prepare_transport_fixture(store, clock=clock, authorize=True)
        assert fixture.intent is not None
        ack = append_ack_occurrence(
            store,
            clock=clock,
            fixture=fixture,
            intent=fixture.intent,
            payload=ack_payload(
                request_id=fixture.intent.request_id,
                provider_connection_id="provider-healthy-close",
            ),
            sequence=1,
            received_at=T0 + timedelta(milliseconds=10),
            idempotency_suffix="healthy-close-ack",
        )
        bind_ack(
            store,
            clock=clock,
            fixture=fixture,
            intent=fixture.intent,
            occurrence=ack,
            idempotency_key="healthy-close-binding",
        )

        parent = ack.capture
        latest_classification = None
        for index in range(2):
            capture = primary_bar_capture(
                fixture=fixture,
                intent=fixture.intent,
                sequence=index + 2,
                bar_start=T0 + timedelta(minutes=index),
                received_at=T0 + timedelta(minutes=index + 1, milliseconds=200),
                parent=parent,
            )
            latest_classification = append_classified_capture(
                store,
                clock=clock,
                fixture=fixture,
                policy=fixture.primary,
                capture=capture,
                idempotency_suffix=f"healthy-close-bar-{index}",
            )
            parent = capture
        assert latest_classification is not None
        selected_revision = latest_classification.revision
        assert selected_revision is not None

        status_published = T0 + timedelta(minutes=2, milliseconds=700)
        append_classified_capture(
            store,
            clock=clock,
            fixture=fixture,
            policy=fixture.required_status,
            capture=segment(
                fixture.required_status,
                fresh_status_bytes(published_at=status_published),
                received_at=status_published + timedelta(milliseconds=100),
            ),
            idempotency_suffix="healthy-close-status",
        )

        healthy_at = T0 + timedelta(minutes=2, seconds=4)
        clock.value = healthy_at
        cutoff, transition = store.append_derived_health_cutoff(
            physical_scope_manifest_id=fixture.scope.physical_scope_manifest_id,
            knowledge_cutoff_ts=healthy_at,
            idempotency_key="healthy-close-cutoff",
        )
        assert cutoff.health is PrefixHealth.HEALTHY
        assert transition.current_health is PrefixHealth.HEALTHY

        protocol_binding = exact_event_binding(fixture.scope)
        store.append_protocol_binding(
            protocol_binding,
            idempotency_key="healthy-close-protocol-binding",
        )
        proof_at = healthy_at + timedelta(milliseconds=100)
        clock.value = proof_at
        _, chunk = store.select_observations(
            physical_protocol_binding_id=(
                protocol_binding.physical_protocol_binding_id
            ),
            evidence_cutoff_id=cutoff.evidence_cutoff_id,
            observation_cutoff_ts=healthy_at,
            computed_at=proof_at,
            idempotency_key="healthy-close-selection",
        )
        assert chunk is not None
        assert chunk.ordered_observation_revision_ids == (
            selected_revision.observation_revision_id,
        )

        assembled_at = healthy_at + timedelta(milliseconds=200)
        information_set = live_information_set(
            scope=fixture.scope,
            binding=protocol_binding,
            revision=selected_revision,
            observation_cutoff_ts=healthy_at,
            assembled_at=assembled_at,
        )
        clock.value = assembled_at
        store.append_information_set(
            information_set,
            idempotency_key="healthy-close-information-set",
        )

        clock.value = healthy_at + timedelta(milliseconds=300)
        passing_gate = store.evaluate_physical_gate(
            information_set_id=information_set.information_set_id,
            gate_stage=PhysicalGateStage.DECISION_INPUT,
            idempotency_key="healthy-close-passing-gate",
        )
        assert passing_gate.verdict is PhysicalGateVerdict.PASS
        assert passing_gate.abstention_reason_codes == ()

        authority = _control_authority(store, fixture, label="healthy-close")
        close_payload = (1000).to_bytes(2, "big") + b"normal"
        raw = _raw_ingress(
            authority,
            opcode=InboundRfcControlOpcodeV4.CLOSE,
            payload=close_payload,
            received_offset_ms=124_400,
            received_monotonic_ns=4_000_000_000,
        )
        trigger = _trigger(
            raw,
            opcode=InboundRfcControlOpcodeV4.CLOSE,
            payload=close_payload,
        )
        clock.value = raw.received_at
        store.append_raw_ingress_commit(
            raw,
            idempotency_key="healthy-close-raw",
        )
        clock.value = raw.received_at + timedelta(milliseconds=1)
        store.append_inbound_rfc_control_trigger(
            trigger,
            idempotency_key="healthy-close-trigger",
        )

        clock.value = healthy_at + timedelta(milliseconds=500)
        fenced_gate = store.evaluate_physical_gate(
            information_set_id=information_set.information_set_id,
            gate_stage=PhysicalGateStage.DECISION_INPUT,
            idempotency_key="healthy-close-fenced-gate",
        )
        assert fenced_gate.verdict is PhysicalGateVerdict.ABSTAIN
        assert "TRANSPORT_CONTROL_FENCED" in fenced_gate.abstention_reason_codes
        assert "CURRENT_HEALTH_LAGS_PROVIDER_EVIDENCE" in (
            fenced_gate.abstention_reason_codes
        )


def test_control_operation_clock_must_be_inside_current_deployment(
    tmp_path: Path,
) -> None:
    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(
        tmp_path / "control-clock-validity.sqlite3",
        clock=clock,
    ) as store:
        fixture = prepare_transport_fixture(store, clock=clock, authorize=False)
        authority = _control_authority(store, fixture, label="expired-deployment")
        raw = _raw_ingress(authority)
        clock.value = T0 + timedelta(days=2)

        with pytest.raises(
            PhysicalProjectionV4ConflictError,
            match="projection clock falls outside",
        ):
            store.append_raw_ingress_commit(
                raw,
                idempotency_key="expired-deployment-raw",
            )


def test_raw_ingress_is_not_a_typed_protocol_failure_cause(tmp_path: Path) -> None:
    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(
        tmp_path / "untyped-protocol-failure.sqlite3",
        clock=clock,
    ) as store:
        fixture = prepare_transport_fixture(store, clock=clock, authorize=False)
        authority = _control_authority(store, fixture, label="protocol-failure")
        raw = _raw_ingress(authority)
        clock.value = raw.received_at
        store.append_raw_ingress_commit(raw, idempotency_key="protocol-raw")
        intent = _protocol_failure_intent(authority, raw)
        clock.value = intent.authorized_at

        with pytest.raises(PhysicalProjectionV4ConflictError):
            store.append_outbound_control_intent(
                intent,
                idempotency_key="untyped-protocol-failure-intent",
            )
        assert store.verify().outbound_control_intent_count == 0


def test_intent_and_wire_append_reject_at_exact_send_deadline(
    tmp_path: Path,
) -> None:
    intent_clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(
        tmp_path / "intent-at-deadline.sqlite3",
        clock=intent_clock,
    ) as store:
        fixture = prepare_transport_fixture(
            store,
            clock=intent_clock,
            authorize=False,
        )
        authority = _control_authority(store, fixture, label="intent-deadline")
        raw = _raw_ingress(authority)
        trigger = _trigger(
            raw,
            opcode=InboundRfcControlOpcodeV4.PING,
            payload=b"projection-ping",
        )
        intent = _reactive_intent(authority, trigger)
        intent_clock.value = raw.received_at
        store.append_raw_ingress_commit(raw, idempotency_key="intent-deadline-raw")
        intent_clock.value = intent.authorized_at
        store.append_inbound_rfc_control_trigger(
            trigger,
            idempotency_key="intent-deadline-trigger",
        )

        intent_clock.value = intent.send_not_after
        with pytest.raises(PhysicalProjectionV4ConflictError):
            store.append_outbound_control_intent(
                intent,
                idempotency_key="intent-at-deadline",
            )

    wire_clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(
        tmp_path / "wire-at-deadline.sqlite3",
        clock=wire_clock,
    ) as store:
        fixture = prepare_transport_fixture(
            store,
            clock=wire_clock,
            authorize=False,
        )
        authority = _control_authority(store, fixture, label="wire-deadline")
        raw = _raw_ingress(authority)
        trigger = _trigger(
            raw,
            opcode=InboundRfcControlOpcodeV4.PING,
            payload=b"projection-ping",
        )
        intent = _reactive_intent(authority, trigger)
        wire = _wire(intent)
        wire_clock.value = raw.received_at
        store.append_raw_ingress_commit(raw, idempotency_key="wire-deadline-raw")
        wire_clock.value = intent.authorized_at
        store.append_inbound_rfc_control_trigger(
            trigger,
            idempotency_key="wire-deadline-trigger",
        )
        store.append_outbound_control_intent(
            intent,
            idempotency_key="wire-deadline-intent",
        )

        wire_clock.value = wire.send_not_after
        with pytest.raises(PhysicalProjectionV4ConflictError):
            store.append_outbound_control_wire_prepared(
                wire,
                idempotency_key="wire-at-deadline",
            )


def test_intent_rejects_trigger_receipt_after_authorization(tmp_path: Path) -> None:
    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(
        tmp_path / "late-trigger-receipt.sqlite3",
        clock=clock,
    ) as store:
        fixture = prepare_transport_fixture(store, clock=clock, authorize=False)
        authority = _control_authority(store, fixture, label="late-trigger")
        chain = _build_reactive_chain(authority)

        clock.value = chain.raw.received_at
        store.append_raw_ingress_commit(
            chain.raw,
            idempotency_key="late-trigger-raw",
        )
        clock.value = chain.intent.authorized_at + timedelta(microseconds=1)
        store.append_inbound_rfc_control_trigger(
            chain.trigger,
            idempotency_key="late-trigger-trigger",
        )

        with pytest.raises(PhysicalProjectionV4ConflictError):
            store.append_outbound_control_intent(
                chain.intent,
                idempotency_key="intent-after-late-trigger",
            )
        assert store.verify().outbound_control_intent_count == 0


def test_wire_rejects_intent_receipt_after_preparation(tmp_path: Path) -> None:
    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(
        tmp_path / "late-intent-receipt.sqlite3",
        clock=clock,
    ) as store:
        fixture = prepare_transport_fixture(store, clock=clock, authorize=False)
        authority = _control_authority(store, fixture, label="late-intent")
        chain = _build_reactive_chain(authority)

        clock.value = chain.raw.received_at
        store.append_raw_ingress_commit(
            chain.raw,
            idempotency_key="late-intent-raw",
        )
        clock.value = chain.intent.authorized_at
        store.append_inbound_rfc_control_trigger(
            chain.trigger,
            idempotency_key="late-intent-trigger",
        )
        clock.value = chain.wire.prepared_at + timedelta(microseconds=1)
        store.append_outbound_control_intent(
            chain.intent,
            idempotency_key="late-intent-intent",
        )

        with pytest.raises(PhysicalProjectionV4ConflictError):
            store.append_outbound_control_wire_prepared(
                chain.wire,
                idempotency_key="wire-after-late-intent",
            )
        assert store.verify().outbound_control_wire_prepared_count == 0


def test_permit_rejects_wire_receipt_after_consumption_clock(tmp_path: Path) -> None:
    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(
        tmp_path / "late-wire-receipt.sqlite3",
        clock=clock,
    ) as store:
        fixture = prepare_transport_fixture(store, clock=clock, authorize=False)
        authority = _control_authority(store, fixture, label="late-wire")
        chain = _build_reactive_chain(authority)

        clock.value = chain.raw.received_at
        store.append_raw_ingress_commit(
            chain.raw,
            idempotency_key="late-wire-raw",
        )
        clock.value = chain.intent.authorized_at
        store.append_inbound_rfc_control_trigger(
            chain.trigger,
            idempotency_key="late-wire-trigger",
        )
        store.append_outbound_control_intent(
            chain.intent,
            idempotency_key="late-wire-intent",
        )
        clock.value = chain.dispatch.dispatch_started_at + timedelta(microseconds=1)
        store.append_outbound_control_wire_prepared(
            chain.wire,
            idempotency_key="late-wire-wire",
        )
        with pytest.raises(PhysicalProjectionV4ConflictError):
            store.consume_outbound_control_write_permit(
                chain.wire.outbound_control_wire_prepared_id,
                permit_consumed_at=chain.permit.permit_consumed_at,
                permit_consumed_monotonic_ns=(
                    chain.permit.permit_consumed_monotonic_ns
                ),
                idempotency_key="permit-after-late-wire",
            )
        assert store.verify().outbound_control_write_permit_consumed_count == 0
        assert store.verify().outbound_control_dispatch_result_count == 0
        assert store.classify_outbound_control_orphans(
            fixture.session.transport_session_id
        ).prepared_without_permit_ids == (chain.wire.outbound_control_wire_prepared_id,)


@pytest.mark.parametrize(
    "fault_stage",
    (
        "after_canonical_record_insert",
        "after_raw_ingress_commit_insert",
        "after_operation_batch_insert",
        "before_commit",
    ),
)
def test_raw_ingress_faults_roll_back_every_projection_layer(
    tmp_path: Path,
    fault_stage: str,
) -> None:
    armed = False

    def fail_target(stage: str) -> None:
        if armed and stage == fault_stage:
            raise InjectedControlProjectionFailure(stage)

    clock = FixedClock(T0 - timedelta(hours=1))
    with PhysicalProjectionStoreV4(
        tmp_path / f"control-rollback-{fault_stage}.sqlite3",
        clock=clock,
        fault_injector=fail_target,
    ) as store:
        fixture = prepare_transport_fixture(store, clock=clock, authorize=False)
        authority = _control_authority(store, fixture, label=fault_stage)
        raw = _raw_ingress(authority)
        clock.value = raw.received_at + timedelta(milliseconds=1)
        before_receipts = receipt_count(store)
        before_canonical = store.verify().canonical_record_count
        before_batches = store.verify().batch_count

        armed = True
        with pytest.raises(InjectedControlProjectionFailure, match=fault_stage):
            store.append_raw_ingress_commit(
                raw,
                idempotency_key=f"faulted-{fault_stage}",
            )
        armed = False

        report = store.verify()
        assert receipt_count(store) == before_receipts
        assert report.canonical_record_count == before_canonical
        assert report.batch_count == before_batches
        assert report.raw_ingress_commit_count == 0
        assert store._connection.execute(  # noqa: SLF001
            "SELECT count(*) FROM transport_control_socket_bindings"
        ).fetchone() == (1,)
        assert store._connection.execute(  # noqa: SLF001
            "SELECT count(*) FROM operation_batches WHERE idempotency_key = ?",
            (f"faulted-{fault_stage}",),
        ).fetchone() == (0,)

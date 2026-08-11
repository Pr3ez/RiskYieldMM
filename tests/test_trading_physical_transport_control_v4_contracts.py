from __future__ import annotations

import base64
import hashlib
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from riskyieldmm.trading.canonical import (
    CANONICALIZATION_VERSION,
    CanonicalizationError,
    canonical_json_bytes,
    sha256_digest,
)
from riskyieldmm.trading.ledger_signing import Ed25519CheckpointSigner
from riskyieldmm.trading.physical_transport_control_v4 import (
    PHYSICAL_TRANSPORT_CONTROL_V4_SCHEMA_VERSION,
    InboundRfcControlOpcodeV4,
    InboundRfcControlTriggerV4,
    OutboundControlDispatchDispositionV4,
    OutboundControlDispatchResultV4,
    OutboundControlIntentV4,
    OutboundControlKindV4,
    OutboundControlWirePreparedV4,
    OutboundWebSocketOpcodeV4,
    RawIngressCommitV4,
    build_bybit_json_heartbeat_intent_v4,
)

T0 = datetime(2026, 7, 15, 12, tzinfo=timezone.utc)


def digest(label: str) -> str:
    return sha256_digest({"label": label})


def b64(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def ingress_batch_hash(chunks: tuple[str, ...]) -> str:
    return sha256_digest(
        {
            "domain": "RiskYieldMMExactOrderedDecryptedIngressChunksV4_5",
            "ordered_chunks_base64": list(chunks),
        }
    )


def wire_batch_hash(chunks: tuple[str, ...]) -> str:
    return sha256_digest(
        {
            "domain": "RiskYieldMMExactOrderedPreTlsWebSocketChunksV4_5",
            "ordered_chunks_base64": list(chunks),
        }
    )


def server_control_frame(opcode: int, payload: bytes) -> bytes:
    assert len(payload) <= 125
    return bytes((0x80 | opcode, len(payload))) + payload


def client_frame(
    opcode: int, payload: bytes, *, mask: bytes = b"\x01\x23\x45\x67"
) -> bytes:
    assert len(mask) == 4
    assert len(payload) <= 125
    masked = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
    return bytes((0x80 | opcode, 0x80 | len(payload))) + mask + masked


COMMON = {
    "transport_subscription_policy_id": digest("policy"),
    "transport_session_id": digest("session"),
    "physical_scope_manifest_id": digest("scope"),
    "adapter_policy_id": digest("adapter"),
    "capture_partition_id": digest("partition"),
    "socket_lease_id": digest("socket"),
    "connection_generation": 1,
    "deployment_bundle_id": digest("deployment"),
    "writer_fence_token_sha256": digest("writer-fence-token"),
    "writer_fence_generation": 3,
}


def raw_ingress_commit(
    opcode: InboundRfcControlOpcodeV4 = InboundRfcControlOpcodeV4.PING,
    payload: bytes = b"probe-1",
) -> RawIngressCommitV4:
    opcode_number = {
        InboundRfcControlOpcodeV4.CLOSE: 0x8,
        InboundRfcControlOpcodeV4.PING: 0x9,
        InboundRfcControlOpcodeV4.PONG: 0xA,
    }[opcode]
    frame = server_control_frame(opcode_number, payload)
    # A control frame may span transport reads.  The record preserves both
    # chunk boundaries while verifying the frame over their concatenation.
    chunks = (b64(frame[:3]), b64(frame[3:]))
    return RawIngressCommitV4(
        **COMMON,
        ingress_sequence=7,
        raw_ingress_chunks_base64=chunks,
        raw_ingress_chunks_sha256=tuple(
            hashlib.sha256(base64.b64decode(chunk)).hexdigest() for chunk in chunks
        ),
        raw_ingress_batch_sha256=ingress_batch_hash(chunks),
        received_at=T0,
        monotonic_clock_domain_id=digest("monotonic-domain"),
        received_monotonic_ns=1_000,
    )


def inbound_trigger(
    opcode: InboundRfcControlOpcodeV4 = InboundRfcControlOpcodeV4.PING,
    payload: bytes = b"probe-1",
) -> InboundRfcControlTriggerV4:
    raw = raw_ingress_commit(opcode, payload)
    frame = raw.raw_bytes
    return InboundRfcControlTriggerV4(
        **COMMON,
        ingress_sequence=raw.ingress_sequence,
        raw_ingress_commit_id=raw.raw_ingress_commit_id,
        raw_ingress_chunks_base64=raw.raw_ingress_chunks_base64,
        raw_ingress_chunks_sha256=raw.raw_ingress_chunks_sha256,
        raw_ingress_batch_sha256=raw.raw_ingress_batch_sha256,
        frame_offset=0,
        frame_length=len(frame),
        opcode=opcode,
        payload_base64=b64(payload),
        payload_sha256=hashlib.sha256(payload).hexdigest(),
        received_at=raw.received_at,
        monotonic_clock_domain_id=raw.monotonic_clock_domain_id,
        received_monotonic_ns=raw.received_monotonic_ns,
    )


def heartbeat_intent() -> OutboundControlIntentV4:
    return build_bybit_json_heartbeat_intent_v4(
        **COMMON,
        control_sequence=1,
        previous_outbound_control_intent_id=None,
        scheduled_heartbeat_id=digest("heartbeat-schedule-1"),
        request_id="riskyieldmm-heartbeat-1",
        authorized_at=T0 + timedelta(milliseconds=1),
        monotonic_clock_domain_id=digest("monotonic-domain"),
        authorized_monotonic_ns=2_000,
        send_not_after=T0 + timedelta(seconds=1),
        send_not_after_monotonic_ns=1_002_000_000,
    )


def reactive_intent(
    kind: OutboundControlKindV4,
    trigger: InboundRfcControlTriggerV4,
) -> OutboundControlIntentV4:
    opcode = (
        OutboundWebSocketOpcodeV4.PONG
        if kind is OutboundControlKindV4.RFC_PONG
        else OutboundWebSocketOpcodeV4.CLOSE
    )
    return OutboundControlIntentV4(
        **COMMON,
        control_sequence=1,
        previous_outbound_control_intent_id=None,
        control_kind=kind,
        scheduled_heartbeat_id=None,
        inbound_rfc_control_trigger_id=trigger.inbound_rfc_control_trigger_id,
        inbound_rfc_opcode=trigger.opcode,
        inbound_rfc_payload_base64=trigger.payload_base64,
        protocol_failure_evidence_id=None,
        logical_websocket_opcode=opcode,
        logical_payload_base64=trigger.payload_base64,
        logical_payload_sha256=trigger.payload_sha256,
        request_id=None,
        fences_session_authority=(kind is OutboundControlKindV4.RFC_CLOSE_REPLY),
        authorized_at=T0 + timedelta(milliseconds=1),
        monotonic_clock_domain_id=digest("monotonic-domain"),
        authorized_monotonic_ns=2_000,
        send_not_after=T0 + timedelta(seconds=1),
        send_not_after_monotonic_ns=1_002_000_000,
    )


def protocol_failure_intent() -> OutboundControlIntentV4:
    payload = (1002).to_bytes(2, "big") + b"incorrect masking"
    return OutboundControlIntentV4(
        **COMMON,
        control_sequence=1,
        previous_outbound_control_intent_id=None,
        control_kind=OutboundControlKindV4.RFC_PROTOCOL_FAILURE_CLOSE,
        scheduled_heartbeat_id=None,
        inbound_rfc_control_trigger_id=None,
        inbound_rfc_opcode=None,
        inbound_rfc_payload_base64=None,
        protocol_failure_evidence_id=digest("protocol-failure"),
        logical_websocket_opcode=OutboundWebSocketOpcodeV4.CLOSE,
        logical_payload_base64=b64(payload),
        logical_payload_sha256=hashlib.sha256(payload).hexdigest(),
        request_id=None,
        fences_session_authority=True,
        authorized_at=T0 + timedelta(milliseconds=1),
        monotonic_clock_domain_id=digest("monotonic-domain"),
        authorized_monotonic_ns=2_000,
        send_not_after=T0 + timedelta(seconds=1),
        send_not_after_monotonic_ns=1_002_000_000,
    )


def wire_prepared(intent: OutboundControlIntentV4) -> OutboundControlWirePreparedV4:
    opcode = {
        OutboundWebSocketOpcodeV4.TEXT: 0x1,
        OutboundWebSocketOpcodeV4.PONG: 0xA,
        OutboundWebSocketOpcodeV4.CLOSE: 0x8,
    }[intent.logical_websocket_opcode]
    wire = client_frame(opcode, intent.logical_payload_bytes)
    chunks = (b64(wire[:4]), b64(wire[4:]))
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
        wire_batch_sha256=wire_batch_hash(chunks),
        wire_octet_length=len(wire),
        prepared_at=T0 + timedelta(milliseconds=2),
        monotonic_clock_domain_id=intent.monotonic_clock_domain_id,
        prepared_monotonic_ns=3_000,
        send_not_after=intent.send_not_after,
        send_not_after_monotonic_ns=intent.send_not_after_monotonic_ns,
    )


def dispatch_fields(
    wire: OutboundControlWirePreparedV4,
    *,
    disposition: OutboundControlDispatchDispositionV4 = (
        OutboundControlDispatchDispositionV4.SENT
    ),
) -> dict[str, object]:
    unknown = disposition is OutboundControlDispatchDispositionV4.UNKNOWN_DELIVERY
    return {
        "outbound_control_intent_id": wire.outbound_control_intent_id,
        "outbound_control_wire_prepared_id": (wire.outbound_control_wire_prepared_id),
        "transport_session_id": wire.transport_session_id,
        "socket_lease_id": wire.socket_lease_id,
        "connection_generation": wire.connection_generation,
        "deployment_bundle_id": wire.deployment_bundle_id,
        "writer_fence_token_sha256": wire.writer_fence_token_sha256,
        "writer_fence_generation": wire.writer_fence_generation,
        "control_kind": wire.control_kind,
        "wire_batch_sha256": wire.wire_batch_sha256,
        "wire_octet_length": wire.wire_octet_length,
        "permit_id": digest("one-shot-permit"),
        "permit_consumed": True,
        "one_shot_attempt_ordinal": 1,
        "disposition": disposition,
        "wire_prepared_at": wire.prepared_at,
        "monotonic_clock_domain_id": wire.monotonic_clock_domain_id,
        "wire_prepared_monotonic_ns": wire.prepared_monotonic_ns,
        "dispatch_started_at": T0 + timedelta(milliseconds=3),
        "dispatch_started_monotonic_ns": 4_000,
        "dispatch_outcome_at": T0 + timedelta(milliseconds=4),
        "dispatch_outcome_monotonic_ns": 5_000,
        "send_not_after": wire.send_not_after,
        "send_not_after_monotonic_ns": wire.send_not_after_monotonic_ns,
        "bytes_submitted_to_tls": (
            wire.wire_octet_length // 2 if unknown else wire.wire_octet_length
        ),
        "error_class_digest": digest("tls-write-error") if unknown else None,
    }


def test_schema_and_all_contracts_round_trip_exactly() -> None:
    signer = Ed25519CheckpointSigner.generate()
    raw = raw_ingress_commit()
    trigger = inbound_trigger()
    intent = heartbeat_intent()
    wire = wire_prepared(intent)
    dispatch = OutboundControlDispatchResultV4.create_signed(
        signer=signer, **dispatch_fields(wire)
    )

    assert PHYSICAL_TRANSPORT_CONTROL_V4_SCHEMA_VERSION == (
        "riskyieldmm_physical_transport_control_v4_6"
    )
    assert RawIngressCommitV4.from_mapping(raw.as_dict()) == raw
    assert InboundRfcControlTriggerV4.from_mapping(trigger.as_dict()) == trigger
    assert OutboundControlIntentV4.from_mapping(intent.as_dict()) == intent
    assert OutboundControlWirePreparedV4.from_mapping(wire.as_dict()) == wire
    assert OutboundControlDispatchResultV4.from_mapping(dispatch.as_dict()) == dispatch
    dispatch.verify_signature()
    assert dispatch.as_dict()["canonicalization_version"] == CANONICALIZATION_VERSION


def test_split_raw_ingress_chunks_still_prove_exact_ping_frame() -> None:
    trigger = inbound_trigger(payload=b"split-across-reads")

    assert trigger.opcode is InboundRfcControlOpcodeV4.PING
    assert trigger.payload_bytes == b"split-across-reads"
    assert len(trigger.raw_ingress_chunks_base64) == 2


def test_raw_ingress_commit_detects_chunk_hash_order_and_identity_tampering() -> None:
    raw = raw_ingress_commit(payload=b"raw-first")
    assert raw.raw_bytes == server_control_frame(0x9, b"raw-first")

    with pytest.raises(CanonicalizationError, match="chunk hashes"):
        replace(
            raw,
            raw_ingress_chunks_sha256=tuple(reversed(raw.raw_ingress_chunks_sha256)),
        )

    mapping = raw.as_dict()
    mapping["raw_ingress_commit_id"] = digest("substituted-raw-identity")
    with pytest.raises(CanonicalizationError, match="raw_ingress_commit_id"):
        RawIngressCommitV4.from_mapping(mapping)


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        ({"payload_sha256": digest("wrong")}, "payload_sha256"),
        ({"frame_length": 1}, "declared inbound frame"),
        ({"opcode": InboundRfcControlOpcodeV4.PONG}, "opcode"),
    ],
)
def test_inbound_trigger_rejects_claims_not_proven_by_raw_ingress(
    mutation: dict[str, object], match: str
) -> None:
    with pytest.raises(CanonicalizationError, match=match):
        replace(inbound_trigger(), **mutation)


def test_inbound_trigger_rejects_masked_or_fragmented_server_control() -> None:
    trigger = inbound_trigger()
    payload = trigger.payload_bytes
    masked = client_frame(0x9, payload)
    chunks = (b64(masked),)
    kwargs = {
        "raw_ingress_chunks_base64": chunks,
        "raw_ingress_chunks_sha256": (hashlib.sha256(masked).hexdigest(),),
        "raw_ingress_batch_sha256": ingress_batch_hash(chunks),
        "frame_length": len(masked),
    }
    with pytest.raises(CanonicalizationError, match="unmasked"):
        replace(trigger, **kwargs)

    fragmented = bytes((0x09, len(payload))) + payload
    chunks = (b64(fragmented),)
    kwargs = {
        "raw_ingress_chunks_base64": chunks,
        "raw_ingress_chunks_sha256": (hashlib.sha256(fragmented).hexdigest(),),
        "raw_ingress_batch_sha256": ingress_batch_hash(chunks),
        "frame_length": len(fragmented),
    }
    with pytest.raises(CanonicalizationError, match="unfragmented"):
        replace(trigger, **kwargs)


def test_bybit_heartbeat_builder_freezes_exact_text_json_and_request_id() -> None:
    intent = heartbeat_intent()

    assert intent.control_kind is OutboundControlKindV4.APPLICATION_JSON_HEARTBEAT
    assert intent.logical_websocket_opcode is OutboundWebSocketOpcodeV4.TEXT
    assert intent.logical_payload_bytes == canonical_json_bytes(
        {"op": "ping", "req_id": "riskyieldmm-heartbeat-1"}
    )
    assert not intent.fences_session_authority

    noncanonical = b'{"req_id":"riskyieldmm-heartbeat-1","op":"ping"}'
    with pytest.raises(CanonicalizationError, match="exact reviewed JSON"):
        replace(
            intent,
            logical_payload_base64=b64(noncanonical),
            logical_payload_sha256=hashlib.sha256(noncanonical).hexdigest(),
        )


def test_proactive_rfc_ping_is_not_representable() -> None:
    intent = heartbeat_intent()
    with pytest.raises(CanonicalizationError, match="logical_websocket_opcode"):
        replace(intent, logical_websocket_opcode="PING")
    with pytest.raises(CanonicalizationError, match="control_kind"):
        replace(intent, control_kind="RFC_PING")


def test_rfc_pong_must_exactly_echo_a_durable_ping_without_fencing() -> None:
    trigger = inbound_trigger(payload=b"opaque-ping-payload")
    intent = reactive_intent(OutboundControlKindV4.RFC_PONG, trigger)

    assert intent.logical_payload_bytes == trigger.payload_bytes
    assert not intent.fences_session_authority

    changed = b"different"
    with pytest.raises(CanonicalizationError, match="exactly echo"):
        replace(
            intent,
            logical_payload_base64=b64(changed),
            logical_payload_sha256=hashlib.sha256(changed).hexdigest(),
        )


def test_remote_close_reply_must_echo_payload_and_fence_session_authority() -> None:
    payload = (1000).to_bytes(2, "big") + b"normal"
    trigger = inbound_trigger(InboundRfcControlOpcodeV4.CLOSE, payload)
    intent = reactive_intent(OutboundControlKindV4.RFC_CLOSE_REPLY, trigger)

    assert intent.fences_session_authority
    assert intent.logical_payload_bytes == payload

    with pytest.raises(CanonicalizationError, match="fence"):
        replace(intent, fences_session_authority=False)


def test_protocol_failure_close_requires_1002_and_fences() -> None:
    intent = protocol_failure_intent()
    assert intent.logical_payload_bytes[:2] == (1002).to_bytes(2, "big")
    assert intent.fences_session_authority

    wrong = (1000).to_bytes(2, "big") + b"normal"
    with pytest.raises(CanonicalizationError, match="1002"):
        replace(
            intent,
            logical_payload_base64=b64(wrong),
            logical_payload_sha256=hashlib.sha256(wrong).hexdigest(),
        )


def test_close_payload_rejects_reserved_or_invalid_wire_codes() -> None:
    for code in (999, 1004, 1005, 1006, 1015, 2000, 5000):
        payload = code.to_bytes(2, "big")
        with pytest.raises(CanonicalizationError, match="status code"):
            inbound_trigger(InboundRfcControlOpcodeV4.CLOSE, payload)


def test_control_intent_chain_is_strict_and_session_local() -> None:
    first = heartbeat_intent()
    second = replace(
        first,
        control_sequence=2,
        previous_outbound_control_intent_id=first.outbound_control_intent_id,
        scheduled_heartbeat_id=digest("heartbeat-schedule-2"),
        request_id="riskyieldmm-heartbeat-2",
        logical_payload_base64=b64(
            canonical_json_bytes({"op": "ping", "req_id": "riskyieldmm-heartbeat-2"})
        ),
        logical_payload_sha256=hashlib.sha256(
            canonical_json_bytes({"op": "ping", "req_id": "riskyieldmm-heartbeat-2"})
        ).hexdigest(),
    )
    assert (
        second.previous_outbound_control_intent_id == first.outbound_control_intent_id
    )

    with pytest.raises(CanonicalizationError, match="predecessor"):
        replace(first, control_sequence=2)
    with pytest.raises(CanonicalizationError, match="predecessor"):
        replace(first, previous_outbound_control_intent_id=digest("impossible"))


def test_wire_prepared_commits_exact_masked_single_frame_and_chunk_order() -> None:
    intent = heartbeat_intent()
    wire = wire_prepared(intent)

    assert wire.wire_bytes[1] & 0x80
    assert wire.wire_octet_length == len(wire.wire_bytes)

    reversed_chunks = tuple(reversed(wire.wire_chunks_base64))
    with pytest.raises(CanonicalizationError):
        replace(
            wire,
            wire_chunks_base64=reversed_chunks,
            wire_chunks_sha256=tuple(reversed(wire.wire_chunks_sha256)),
            wire_batch_sha256=wire_batch_hash(reversed_chunks),
        )


def test_wire_prepared_rejects_unmasked_wrong_opcode_payload_and_extra_frame() -> None:
    intent = heartbeat_intent()
    wire = wire_prepared(intent)
    payload = intent.logical_payload_bytes

    invalid_frames = (
        server_control_frame(0x1, payload),
        client_frame(0x2, payload),
        client_frame(0x1, payload + b"x"),
        client_frame(0x1, payload) + client_frame(0xA, b""),
    )
    for invalid in invalid_frames:
        chunks = (b64(invalid),)
        with pytest.raises(CanonicalizationError):
            replace(
                wire,
                wire_chunks_base64=chunks,
                wire_chunks_sha256=(hashlib.sha256(invalid).hexdigest(),),
                wire_batch_sha256=wire_batch_hash(chunks),
                wire_octet_length=len(invalid),
            )

    with pytest.raises(CanonicalizationError, match="incompatible"):
        replace(wire, control_kind=OutboundControlKindV4.RFC_PONG)


def test_signed_dispatch_sent_and_unknown_delivery_are_distinct() -> None:
    signer = Ed25519CheckpointSigner.generate()
    wire = wire_prepared(heartbeat_intent())
    sent = OutboundControlDispatchResultV4.create_signed(
        signer=signer, **dispatch_fields(wire)
    )
    unknown = OutboundControlDispatchResultV4.create_signed(
        signer=signer,
        **dispatch_fields(
            wire,
            disposition=OutboundControlDispatchDispositionV4.UNKNOWN_DELIVERY,
        ),
    )
    unknown_prefix_length = OutboundControlDispatchResultV4.create_signed(
        signer=signer,
        **{
            **dispatch_fields(
                wire,
                disposition=OutboundControlDispatchDispositionV4.UNKNOWN_DELIVERY,
            ),
            "bytes_submitted_to_tls": None,
        },
    )

    assert sent.disposition is OutboundControlDispatchDispositionV4.SENT
    assert sent.bytes_submitted_to_tls == sent.wire_octet_length
    assert unknown.disposition is OutboundControlDispatchDispositionV4.UNKNOWN_DELIVERY
    assert unknown.error_class_digest is not None
    assert unknown_prefix_length.bytes_submitted_to_tls is None
    assert (
        OutboundControlDispatchResultV4.from_mapping(unknown_prefix_length.as_dict())
        == unknown_prefix_length
    )
    sent.verify_signature()
    unknown.verify_signature()


def test_dispatch_rejects_retry_partial_sent_missing_error_and_expired_start() -> None:
    signer = Ed25519CheckpointSigner.generate()
    wire = wire_prepared(heartbeat_intent())
    fields = dispatch_fields(wire)

    with pytest.raises(CanonicalizationError, match="one-shot"):
        OutboundControlDispatchResultV4.create_signed(
            signer=signer, **{**fields, "one_shot_attempt_ordinal": 2}
        )
    with pytest.raises(CanonicalizationError, match="full batch"):
        OutboundControlDispatchResultV4.create_signed(
            signer=signer, **{**fields, "bytes_submitted_to_tls": 1}
        )
    with pytest.raises(CanonicalizationError, match="full batch"):
        OutboundControlDispatchResultV4.create_signed(
            signer=signer, **{**fields, "bytes_submitted_to_tls": None}
        )
    with pytest.raises(CanonicalizationError, match="error_class_digest"):
        OutboundControlDispatchResultV4.create_signed(
            signer=signer,
            **{
                **fields,
                "disposition": OutboundControlDispatchDispositionV4.UNKNOWN_DELIVERY,
                "bytes_submitted_to_tls": 1,
                "error_class_digest": None,
            },
        )
    with pytest.raises(CanonicalizationError, match="deadline"):
        OutboundControlDispatchResultV4.create_signed(
            signer=signer,
            **{
                **fields,
                "dispatch_started_at": wire.send_not_after,
                "dispatch_started_monotonic_ns": wire.send_not_after_monotonic_ns,
                "dispatch_outcome_at": wire.send_not_after + timedelta(milliseconds=1),
                "dispatch_outcome_monotonic_ns": (wire.send_not_after_monotonic_ns + 1),
            },
        )


def test_dispatch_signature_and_identity_detect_tampering() -> None:
    signer = Ed25519CheckpointSigner.generate()
    wire = wire_prepared(heartbeat_intent())
    dispatch = OutboundControlDispatchResultV4.create_signed(
        signer=signer, **dispatch_fields(wire)
    )
    mapping = dispatch.as_dict()
    mapping["socket_lease_id"] = digest("other-socket")

    with pytest.raises(CanonicalizationError, match="signature"):
        OutboundControlDispatchResultV4.from_mapping(mapping)


def test_all_mappings_reject_unknown_or_missing_fields() -> None:
    records = (
        raw_ingress_commit(),
        inbound_trigger(),
        heartbeat_intent(),
        wire_prepared(heartbeat_intent()),
    )
    for record in records:
        mapping = record.as_dict()
        mapping["unknown"] = "value"
        with pytest.raises(CanonicalizationError, match="keys do not match"):
            type(record).from_mapping(mapping)

from __future__ import annotations

import base64
import hashlib
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

import riskyieldmm.trading as trading
from riskyieldmm.trading.canonical import CanonicalizationError, sha256_digest
from riskyieldmm.trading.physical_transport_control_v4 import (
    PHYSICAL_TRANSPORT_CONTROL_V4_SCHEMA_VERSION,
    V4_INCORRECT_MASKING_CLOSE_PAYLOAD,
    V4_INCORRECT_MASKING_PARSER_EXCEPTION_CLASS_DIGEST,
    V4_INCORRECT_MASKING_PARSER_EXCEPTION_MESSAGE_DIGEST,
    InboundWebSocketProtocolFailureKindV4,
    InboundWebSocketProtocolFailureV4,
    OutboundControlKindV4,
    OutboundControlWritePermitConsumedV4,
    RawIngressCommitV4,
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


def inbound_frame(payload: bytes, *, masked: bool) -> bytes:
    if not masked:
        return bytes((0x89, len(payload))) + payload
    mask = b"\x01\x23\x45\x67"
    masked_payload = bytes(
        value ^ mask[index % 4] for index, value in enumerate(payload)
    )
    return bytes((0x89, 0x80 | len(payload))) + mask + masked_payload


def raw_ingress(*, masked: bool = True) -> tuple[RawIngressCommitV4, int]:
    frame = inbound_frame(b"probe", masked=masked)
    exact = frame
    chunks = (b64(exact[:4]), b64(exact[4:]))
    raw = RawIngressCommitV4(
        **COMMON,
        ingress_sequence=1,
        raw_ingress_chunks_base64=chunks,
        raw_ingress_chunks_sha256=tuple(
            hashlib.sha256(base64.b64decode(chunk)).hexdigest() for chunk in chunks
        ),
        raw_ingress_batch_sha256=ingress_batch_hash(chunks),
        received_at=T0,
        monotonic_clock_domain_id=digest("monotonic-domain"),
        received_monotonic_ns=1_000,
    )
    return raw, 0


def protocol_failure(*, masked: bool = True) -> InboundWebSocketProtocolFailureV4:
    raw, offset = raw_ingress(masked=masked)
    return InboundWebSocketProtocolFailureV4(
        **COMMON,
        ingress_sequence=raw.ingress_sequence,
        raw_ingress_commit_id=raw.raw_ingress_commit_id,
        raw_ingress_chunks_base64=raw.raw_ingress_chunks_base64,
        raw_ingress_chunks_sha256=raw.raw_ingress_chunks_sha256,
        raw_ingress_batch_sha256=raw.raw_ingress_batch_sha256,
        frame_offset=offset,
        protocol_failure_kind=(InboundWebSocketProtocolFailureKindV4.INCORRECT_MASKING),
        parser_exception_class_digest=(
            V4_INCORRECT_MASKING_PARSER_EXCEPTION_CLASS_DIGEST
        ),
        parser_exception_message_digest=(
            V4_INCORRECT_MASKING_PARSER_EXCEPTION_MESSAGE_DIGEST
        ),
        logical_close_payload_base64=b64(V4_INCORRECT_MASKING_CLOSE_PAYLOAD),
        logical_close_payload_sha256=hashlib.sha256(
            V4_INCORRECT_MASKING_CLOSE_PAYLOAD
        ).hexdigest(),
        detected_at=T0 + timedelta(microseconds=1),
        monotonic_clock_domain_id=raw.monotonic_clock_domain_id,
        detected_monotonic_ns=1_001,
        fences_session_authority=True,
    )


def permit() -> OutboundControlWritePermitConsumedV4:
    return OutboundControlWritePermitConsumedV4(
        outbound_control_intent_id=digest("intent"),
        outbound_control_wire_prepared_id=digest("wire-prepared"),
        transport_session_id=COMMON["transport_session_id"],
        socket_lease_id=COMMON["socket_lease_id"],
        connection_generation=COMMON["connection_generation"],
        deployment_bundle_id=COMMON["deployment_bundle_id"],
        writer_fence_token_sha256=COMMON["writer_fence_token_sha256"],
        writer_fence_generation=COMMON["writer_fence_generation"],
        control_kind=OutboundControlKindV4.APPLICATION_JSON_HEARTBEAT,
        wire_batch_sha256=digest("wire-batch"),
        wire_octet_length=31,
        one_shot_attempt_ordinal=1,
        wire_prepared_at=T0 + timedelta(milliseconds=1),
        monotonic_clock_domain_id=digest("monotonic-domain"),
        wire_prepared_monotonic_ns=2_000,
        permit_consumed_at=T0 + timedelta(milliseconds=2),
        permit_consumed_monotonic_ns=3_000,
        send_not_after=T0 + timedelta(seconds=1),
        send_not_after_monotonic_ns=1_001_000_000,
    )


def test_v4_6_protocol_failure_and_permit_round_trip_strictly() -> None:
    failure = protocol_failure()
    consumed = permit()

    assert InboundWebSocketProtocolFailureV4.from_mapping(failure.as_dict()) == failure
    assert (
        OutboundControlWritePermitConsumedV4.from_mapping(consumed.as_dict())
        == consumed
    )
    assert failure.as_dict()["schema_version"] == (
        PHYSICAL_TRANSPORT_CONTROL_V4_SCHEMA_VERSION
    )
    assert failure.logical_close_payload_bytes == (V4_INCORRECT_MASKING_CLOSE_PAYLOAD)
    assert consumed.as_dict()["permit_id"] == consumed.permit_id


def test_v4_6_contracts_are_exported_from_the_trading_package() -> None:
    for name in (
        "InboundWebSocketProtocolFailureKindV4",
        "InboundWebSocketProtocolFailureV4",
        "OutboundControlWritePermitConsumedV4",
        "PhysicalTransportControlMediatorV4",
    ):
        assert name in trading.__all__
        assert getattr(trading, name) is not None


def test_protocol_failure_rejects_raw_without_server_mask_bit() -> None:
    with pytest.raises(CanonicalizationError, match="MASK bit"):
        protocol_failure(masked=False)


def test_protocol_failure_rejects_unproven_offset_sequence_and_raw_hashes() -> None:
    failure = protocol_failure()

    with pytest.raises(CanonicalizationError, match="offset zero"):
        replace(failure, frame_offset=failure.frame_offset + 1)
    with pytest.raises(CanonicalizationError, match="sequence one"):
        replace(failure, ingress_sequence=2)
    with pytest.raises(CanonicalizationError, match="chunk hashes"):
        replace(
            failure,
            raw_ingress_chunks_sha256=(
                digest("wrong-first-chunk"),
                *failure.raw_ingress_chunks_sha256[1:],
            ),
        )


def test_protocol_failure_rejects_mask_like_bytes_inside_payload_as_a_boundary() -> (
    None
):
    failure = protocol_failure()
    raw = inbound_frame(b"prefix\x89\x80payload", masked=False)
    chunks = (b64(raw),)

    with pytest.raises(CanonicalizationError, match="offset zero"):
        replace(
            failure,
            raw_ingress_chunks_base64=chunks,
            raw_ingress_chunks_sha256=(hashlib.sha256(raw).hexdigest(),),
            raw_ingress_batch_sha256=ingress_batch_hash(chunks),
            frame_offset=8,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("protocol_failure_kind", "UNREVIEWED_FAILURE"),
        ("parser_exception_class_digest", digest("wrong-parser-class")),
        ("parser_exception_message_digest", digest("wrong-parser-message")),
    ),
)
def test_protocol_failure_rejects_unreviewed_or_mutated_cause(
    field: str, value: object
) -> None:
    failure = protocol_failure()

    with pytest.raises(CanonicalizationError):
        replace(failure, **{field: value})


@pytest.mark.parametrize(
    "payload",
    (
        (1000).to_bytes(2, "big") + b"incorrect masking",
        (1002).to_bytes(2, "big") + b"different reason",
    ),
)
def test_protocol_failure_rejects_wrong_close_code_or_payload(payload: bytes) -> None:
    failure = protocol_failure()

    with pytest.raises(CanonicalizationError, match="code-1002"):
        replace(
            failure,
            logical_close_payload_base64=b64(payload),
            logical_close_payload_sha256=hashlib.sha256(payload).hexdigest(),
        )


def test_protocol_failure_rejects_false_fence_and_mutated_mapping_binding() -> None:
    failure = protocol_failure()
    with pytest.raises(CanonicalizationError, match="must fence"):
        replace(failure, fences_session_authority=False)

    mapping = failure.as_dict()
    mapping["transport_session_id"] = digest("other-session")
    with pytest.raises(CanonicalizationError, match="does not match"):
        InboundWebSocketProtocolFailureV4.from_mapping(mapping)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        (
            "permit_consumed_at",
            T0 + timedelta(milliseconds=1),
            "wall clocks",
        ),
        ("permit_consumed_monotonic_ns", 2_000, "monotonic clocks"),
        ("permit_consumed_at", T0 + timedelta(seconds=1), "wall clocks"),
        ("permit_consumed_monotonic_ns", 1_001_000_000, "monotonic clocks"),
    ),
)
def test_permit_rejects_consumption_outside_open_prewrite_interval(
    field: str, value: object, message: str
) -> None:
    consumed = permit()

    with pytest.raises(CanonicalizationError, match=message):
        replace(consumed, **{field: value})


def test_permit_rejects_retry_ordinal_and_mutated_mapping_binding() -> None:
    consumed = permit()
    with pytest.raises(CanonicalizationError, match="ordinal one"):
        replace(consumed, one_shot_attempt_ordinal=2)

    mapping = consumed.as_dict()
    mapping["wire_batch_sha256"] = digest("different-wire")
    with pytest.raises(CanonicalizationError, match="does not match"):
        OutboundControlWritePermitConsumedV4.from_mapping(mapping)

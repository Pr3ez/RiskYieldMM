"""Immutable V4.6 outbound WebSocket-control evidence contracts.

This module is intentionally isolated from the live transport runtime.  It
defines the evidence boundary required before the pinned Sans-I/O adapter may
emit Bybit application heartbeats or RFC 6455 Pong / Close frames.  Creating a
record never performs network I/O and never grants market-data or trading
authority.

The core ordering claim is narrow and explicit::

    durable raw ingress (for reactive controls)
    -> exact typed RFC trigger or bounded parser failure
    -> exact logical control intent
    -> exact masked pre-TLS WebSocket octets prepared in memory
    -> immutable durable attempt-one write permit
    -> one signed, one-shot dispatch result

There is no distributed transaction with the peer.  Once a write begins, a
failure is ``UNKNOWN_DELIVERY`` and the same intent must never be replayed. A
permit may remain without a result when truthful dispatch clocks or outcome
evidence cannot be persisted; recovery never invents that evidence.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from .canonical import (
    CANONICALIZATION_VERSION,
    CanonicalizationError,
    canonical_hash,
    canonical_identifier,
    canonical_json_bytes,
    canonical_safe_int,
    require_exact_keys,
    sha256_digest,
    strict_json_loads,
    utc_datetime,
    utc_iso,
)
from .ledger_signing import (
    Ed25519CheckpointVerifier,
    ed25519_public_key_is_valid,
)
from .physical_transport_v4 import derive_transport_attestation_key_id

PHYSICAL_TRANSPORT_CONTROL_V4_SCHEMA_VERSION = (
    "riskyieldmm_physical_transport_control_v4_6"
)
# Existing V4.5 identity, batch, and signature domains remain unchanged so the
# V4.6 schema can extend the record graph without silently redefining their
# domain semantics.  New record kinds below use explicit V4.6 identity domains.

V4_CONTROL_MAXIMUM_REQUEST_ID_LENGTH = 36
V4_CONTROL_MAXIMUM_INGRESS_CHUNKS = 128
V4_CONTROL_MAXIMUM_INGRESS_BYTES = 65_536
V4_CONTROL_MAXIMUM_WIRE_CHUNKS = 16
V4_CONTROL_MAXIMUM_WIRE_BYTES = 4_096
V4_CONTROL_MAXIMUM_CONTROL_PAYLOAD_BYTES = 125
V4_CONTROL_PROTOCOL_ERROR_CLOSE_CODE = 1002
V4_INCORRECT_MASKING_PARSER_EXCEPTION_CLASS_DIGEST = hashlib.sha256(
    b"websockets.exceptions.ProtocolError"
).hexdigest()
V4_INCORRECT_MASKING_PARSER_EXCEPTION_MESSAGE_DIGEST = hashlib.sha256(
    b"incorrect masking"
).hexdigest()
V4_INCORRECT_MASKING_CLOSE_PAYLOAD = (
    V4_CONTROL_PROTOCOL_ERROR_CLOSE_CODE.to_bytes(2, "big") + b"incorrect masking"
)

_PUBLIC_KEY_RE = re.compile(r"^[0-9a-f]{64}$")
_SIGNATURE_RE = re.compile(r"^[0-9a-f]{128}$")
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class InboundRfcControlOpcodeV4(str, Enum):
    CLOSE = "CLOSE"
    PING = "PING"
    PONG = "PONG"


class InboundWebSocketProtocolFailureKindV4(str, Enum):
    """Closed causes whose exact parser behavior has been reviewed."""

    INCORRECT_MASKING = "INCORRECT_MASKING"


class OutboundControlKindV4(str, Enum):
    APPLICATION_JSON_HEARTBEAT = "APPLICATION_JSON_HEARTBEAT"
    RFC_PONG = "RFC_PONG"
    RFC_CLOSE_REPLY = "RFC_CLOSE_REPLY"
    RFC_PROTOCOL_FAILURE_CLOSE = "RFC_PROTOCOL_FAILURE_CLOSE"


class OutboundWebSocketOpcodeV4(str, Enum):
    """Closed outbound opcode set; proactive RFC Ping is deliberately absent."""

    TEXT = "TEXT"
    PONG = "PONG"
    CLOSE = "CLOSE"


class OutboundControlDispatchDispositionV4(str, Enum):
    SENT = "SENT"
    UNKNOWN_DELIVERY = "UNKNOWN_DELIVERY"


_INBOUND_OPCODE_NUMBER = {
    InboundRfcControlOpcodeV4.CLOSE: 0x8,
    InboundRfcControlOpcodeV4.PING: 0x9,
    InboundRfcControlOpcodeV4.PONG: 0xA,
}
_OUTBOUND_OPCODE_NUMBER = {
    OutboundWebSocketOpcodeV4.TEXT: 0x1,
    OutboundWebSocketOpcodeV4.CLOSE: 0x8,
    OutboundWebSocketOpcodeV4.PONG: 0xA,
}


def _enum(value: Any, enum_type: type[Enum], *, field: str) -> Enum:
    try:
        return value if isinstance(value, enum_type) else enum_type(value)
    except (TypeError, ValueError) as exc:
        choices = ", ".join(item.value for item in enum_type)
        raise CanonicalizationError(f"{field} must be one of: {choices}") from exc


def _strict_bool(value: Any, *, field: str) -> bool:
    if type(value) is not bool:
        raise CanonicalizationError(f"{field} must be a boolean")
    return value


def _optional_hash(value: Any, *, field: str) -> str | None:
    return None if value is None else canonical_hash(value, field=field)


def _optional_identifier(value: Any, *, field: str) -> str | None:
    return None if value is None else canonical_identifier(value, field=field)


def _request_id(value: Any) -> str:
    checked = canonical_identifier(
        value,
        field="request_id",
        maximum=V4_CONTROL_MAXIMUM_REQUEST_ID_LENGTH,
    )
    if _REQUEST_ID_RE.fullmatch(checked) is None:
        raise CanonicalizationError(
            "request_id must contain only ASCII letters, digits, underscore, or hyphen"
        )
    return checked


def _canonical_base64(value: Any, *, field: str, allow_empty: bool = True) -> bytes:
    if not isinstance(value, str):
        raise CanonicalizationError(f"{field} must be a string")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise CanonicalizationError(f"{field} is not canonical base64") from exc
    if base64.b64encode(decoded).decode("ascii") != value:
        raise CanonicalizationError(f"{field} is not canonical base64")
    if not allow_empty and not decoded:
        raise CanonicalizationError(f"{field} must not be empty")
    return decoded


def _base64_sequence(
    values: Sequence[Any],
    *,
    field: str,
    maximum_items: int,
    maximum_total_bytes: int,
) -> tuple[tuple[str, ...], tuple[bytes, ...]]:
    if isinstance(values, (str, bytes, bytearray)) or not isinstance(values, Sequence):
        raise CanonicalizationError(f"{field} must be a sequence")
    if not values or len(values) > maximum_items:
        raise CanonicalizationError(
            f"{field} must contain between 1 and {maximum_items} chunks"
        )
    encoded: list[str] = []
    decoded: list[bytes] = []
    total = 0
    for index, value in enumerate(values):
        item = _canonical_base64(value, field=f"{field}[{index}]", allow_empty=False)
        total += len(item)
        if total > maximum_total_bytes:
            raise CanonicalizationError(
                f"{field} exceeds {maximum_total_bytes} decoded bytes"
            )
        encoded.append(value)
        decoded.append(item)
    return tuple(encoded), tuple(decoded)


def _hash_sequence(values: Sequence[Any], *, field: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)) or not isinstance(values, Sequence):
        raise CanonicalizationError(f"{field} must be a sequence")
    return tuple(
        canonical_hash(value, field=f"{field}[{index}]")
        for index, value in enumerate(values)
    )


def _identity(domain: str, payload: Mapping[str, Any]) -> str:
    return sha256_digest(
        {
            "canonicalization_version": CANONICALIZATION_VERSION,
            "domain": domain,
            "payload": dict(payload),
            "schema_version": PHYSICAL_TRANSPORT_CONTROL_V4_SCHEMA_VERSION,
        }
    )


def _signature_payload(domain: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "canonicalization_version": CANONICALIZATION_VERSION,
        "domain": domain,
        "payload": dict(payload),
        "schema_version": PHYSICAL_TRANSPORT_CONTROL_V4_SCHEMA_VERSION,
    }


def _record_mapping(
    record: Any, *, identity_field: str, identity: str
) -> dict[str, Any]:
    return {
        "canonicalization_version": CANONICALIZATION_VERSION,
        **record.identity_payload(),
        identity_field: identity,
        "schema_version": PHYSICAL_TRANSPORT_CONTROL_V4_SCHEMA_VERSION,
    }


def _require_versions(payload: Mapping[str, Any]) -> None:
    if payload["canonicalization_version"] != CANONICALIZATION_VERSION:
        raise CanonicalizationError("unsupported canonicalization_version")
    if payload["schema_version"] != PHYSICAL_TRANSPORT_CONTROL_V4_SCHEMA_VERSION:
        raise CanonicalizationError(
            "unsupported physical-transport-control V4.6 schema_version"
        )


def _require_identity(provided: Any, expected: str, *, field: str) -> None:
    if canonical_hash(provided, field=field) != expected:
        raise CanonicalizationError(f"{field} does not match canonical content")


def _public_key_bytes(value: Any, *, field: str) -> bytes:
    if not isinstance(value, str) or _PUBLIC_KEY_RE.fullmatch(value) is None:
        raise CanonicalizationError(
            f"{field} has invalid lowercase hexadecimal encoding"
        )
    public_key = bytes.fromhex(value)
    if not ed25519_public_key_is_valid(public_key):
        raise CanonicalizationError(
            f"{field} is not a canonical Ed25519 main-subgroup public key"
        )
    return public_key


def _key_pair(key_id: Any, public_key_hex: Any) -> tuple[str, str, bytes]:
    public_key = _public_key_bytes(
        public_key_hex, field="collector_attestation_public_key_hex"
    )
    derived = derive_transport_attestation_key_id(public_key)
    supplied = canonical_hash(key_id, field="collector_attestation_key_id")
    if supplied != derived:
        raise CanonicalizationError(
            "collector_attestation_key_id differs from its transport public key"
        )
    return supplied, public_key.hex(), public_key


def _signer_key(signer: Any) -> tuple[str, str]:
    public_key = getattr(signer, "public_key_bytes", None)
    if not isinstance(public_key, bytes):
        raise CanonicalizationError("transport signer must expose public_key_bytes")
    return derive_transport_attestation_key_id(public_key), public_key.hex()


def _sign(signer: Any, payload: Mapping[str, Any]) -> str:
    sign = getattr(signer, "sign", None)
    if not callable(sign):
        raise CanonicalizationError("transport signer must provide sign(payload)")
    signature = sign(canonical_json_bytes(payload))
    if not isinstance(signature, bytes) or len(signature) != 64:
        raise CanonicalizationError(
            "transport signer must return exactly 64 Ed25519 signature bytes"
        )
    return signature.hex()


def _verify_signature(
    *, public_key: bytes, signature_hex: Any, payload: Mapping[str, Any]
) -> str:
    if (
        not isinstance(signature_hex, str)
        or _SIGNATURE_RE.fullmatch(signature_hex) is None
    ):
        raise CanonicalizationError(
            "signature_hex has invalid lowercase hexadecimal encoding"
        )
    try:
        Ed25519CheckpointVerifier.from_public_bytes(public_key).verify(
            canonical_json_bytes(payload), bytes.fromhex(signature_hex)
        )
    except Exception as exc:
        raise CanonicalizationError(
            "transport-control Ed25519 signature is invalid"
        ) from exc
    return signature_hex


def _wire_batch_sha256(chunks_base64: Sequence[str]) -> str:
    return sha256_digest(
        {
            "domain": "RiskYieldMMExactOrderedPreTlsWebSocketChunksV4_5",
            "ordered_chunks_base64": list(chunks_base64),
        }
    )


def _ingress_batch_sha256(chunks_base64: Sequence[str]) -> str:
    return sha256_digest(
        {
            "domain": "RiskYieldMMExactOrderedDecryptedIngressChunksV4_5",
            "ordered_chunks_base64": list(chunks_base64),
        }
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class RawIngressCommitV4:
    """Exact durable decrypted-TLS ingress batch preceding frame parsing.

    The content identity closes the raw-first edge referenced by RFC control
    triggers.  It commits bytes and read boundaries; it does not by itself
    prove kernel-read, TLS-library, or peer provenance.
    """

    transport_subscription_policy_id: str
    transport_session_id: str
    physical_scope_manifest_id: str
    adapter_policy_id: str
    capture_partition_id: str
    socket_lease_id: str
    connection_generation: int
    deployment_bundle_id: str
    writer_fence_token_sha256: str
    writer_fence_generation: int
    ingress_sequence: int
    raw_ingress_chunks_base64: tuple[str, ...]
    raw_ingress_chunks_sha256: tuple[str, ...]
    raw_ingress_batch_sha256: str
    received_at: datetime
    monotonic_clock_domain_id: str
    received_monotonic_ns: int

    def __post_init__(self) -> None:
        for field_name in (
            "transport_subscription_policy_id",
            "transport_session_id",
            "physical_scope_manifest_id",
            "adapter_policy_id",
            "capture_partition_id",
            "socket_lease_id",
            "deployment_bundle_id",
            "writer_fence_token_sha256",
            "raw_ingress_batch_sha256",
            "monotonic_clock_domain_id",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        for field_name in (
            "connection_generation",
            "writer_fence_generation",
            "ingress_sequence",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_safe_int(
                    getattr(self, field_name), field=field_name, minimum=1
                ),
            )
        object.__setattr__(
            self,
            "received_monotonic_ns",
            canonical_safe_int(
                self.received_monotonic_ns,
                field="received_monotonic_ns",
                minimum=0,
            ),
        )
        chunks_base64, chunks = _base64_sequence(
            self.raw_ingress_chunks_base64,
            field="raw_ingress_chunks_base64",
            maximum_items=V4_CONTROL_MAXIMUM_INGRESS_CHUNKS,
            maximum_total_bytes=V4_CONTROL_MAXIMUM_INGRESS_BYTES,
        )
        object.__setattr__(self, "raw_ingress_chunks_base64", chunks_base64)
        hashes = _hash_sequence(
            self.raw_ingress_chunks_sha256,
            field="raw_ingress_chunks_sha256",
        )
        expected_hashes = tuple(hashlib.sha256(chunk).hexdigest() for chunk in chunks)
        if hashes != expected_hashes:
            raise CanonicalizationError(
                "raw ingress chunk hashes differ from exact bytes"
            )
        object.__setattr__(self, "raw_ingress_chunks_sha256", hashes)
        if self.raw_ingress_batch_sha256 != _ingress_batch_sha256(chunks_base64):
            raise CanonicalizationError(
                "raw_ingress_batch_sha256 differs from exact chunk order"
            )
        object.__setattr__(
            self,
            "received_at",
            utc_datetime(self.received_at, field="received_at"),
        )

    def identity_payload(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if name == "received_at":
                result[name] = utc_iso(value)
            elif name in {
                "raw_ingress_chunks_base64",
                "raw_ingress_chunks_sha256",
            }:
                result[name] = list(value)
            else:
                result[name] = value
        return result

    @property
    def raw_ingress_commit_id(self) -> str:
        return _identity("RawIngressCommitV4_5", self.identity_payload())

    @property
    def raw_bytes(self) -> bytes:
        return b"".join(
            base64.b64decode(value, validate=True)
            for value in self.raw_ingress_chunks_base64
        )

    def as_dict(self) -> dict[str, Any]:
        return _record_mapping(
            self,
            identity_field="raw_ingress_commit_id",
            identity=self.raw_ingress_commit_id,
        )

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> RawIngressCommitV4:
        expected = set(cls.__dataclass_fields__) | {
            "canonicalization_version",
            "schema_version",
            "raw_ingress_commit_id",
        }
        require_exact_keys(payload, expected=expected, context=cls.__name__)
        _require_versions(payload)
        item = cls(**{name: payload[name] for name in cls.__dataclass_fields__})
        _require_identity(
            payload["raw_ingress_commit_id"],
            item.raw_ingress_commit_id,
            field="raw_ingress_commit_id",
        )
        return item


def _parse_frame_at(
    data: bytes, *, offset: int, require_mask: bool
) -> tuple[int, int, bytes]:
    """Return ``(opcode, frame_length, payload)`` for one exact RFC 6455 frame."""

    if offset < 0 or offset + 2 > len(data):
        raise CanonicalizationError("frame_offset does not identify a complete header")
    first, second = data[offset], data[offset + 1]
    if first & 0x70:
        raise CanonicalizationError("WebSocket frame reserves unsupported RSV bits")
    if not first & 0x80:
        raise CanonicalizationError("WebSocket control evidence must be unfragmented")
    masked = bool(second & 0x80)
    if masked is not require_mask:
        direction = "masked" if require_mask else "unmasked"
        raise CanonicalizationError(f"WebSocket frame must be {direction}")
    payload_length = second & 0x7F
    cursor = offset + 2
    if payload_length == 126:
        if cursor + 2 > len(data):
            raise CanonicalizationError("WebSocket frame has a truncated 16-bit length")
        payload_length = int.from_bytes(data[cursor : cursor + 2], "big")
        cursor += 2
        if payload_length < 126:
            raise CanonicalizationError(
                "WebSocket frame length is not minimally encoded"
            )
    elif payload_length == 127:
        if cursor + 8 > len(data):
            raise CanonicalizationError("WebSocket frame has a truncated 64-bit length")
        payload_length = int.from_bytes(data[cursor : cursor + 8], "big")
        cursor += 8
        if payload_length < 65_536 or payload_length >= 2**63:
            raise CanonicalizationError(
                "WebSocket frame length is invalid or non-minimal"
            )
    mask = b""
    if masked:
        if cursor + 4 > len(data):
            raise CanonicalizationError("WebSocket frame has a truncated masking key")
        mask = data[cursor : cursor + 4]
        cursor += 4
    end = cursor + payload_length
    if end > len(data):
        raise CanonicalizationError("WebSocket frame payload is truncated")
    payload = data[cursor:end]
    if masked:
        payload = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
    return first & 0x0F, end - offset, payload


def _validate_close_payload(payload: bytes, *, protocol_failure: bool = False) -> None:
    if len(payload) > V4_CONTROL_MAXIMUM_CONTROL_PAYLOAD_BYTES:
        raise CanonicalizationError("Close payload exceeds the RFC 6455 limit")
    if len(payload) == 1:
        raise CanonicalizationError(
            "Close payload cannot contain a one-byte status code"
        )
    if not payload:
        if protocol_failure:
            raise CanonicalizationError(
                "protocol-failure Close requires status code 1002"
            )
        return
    code = int.from_bytes(payload[:2], "big")
    registered_codes = {
        1000,
        1001,
        1002,
        1003,
        1007,
        1008,
        1009,
        1010,
        1011,
        1012,
        1013,
        1014,
    }
    if code not in registered_codes and not 3000 <= code < 5000:
        raise CanonicalizationError("Close payload contains a prohibited status code")
    try:
        payload[2:].decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise CanonicalizationError("Close reason must contain valid UTF-8") from exc
    if protocol_failure and code != V4_CONTROL_PROTOCOL_ERROR_CLOSE_CODE:
        raise CanonicalizationError("protocol-failure Close must use status code 1002")


@dataclass(frozen=True, slots=True, kw_only=True)
class InboundWebSocketProtocolFailureV4:
    """Typed evidence for one reviewed, byte-provable parser failure.

    This V4.6 record deliberately admits only the pinned ``websockets==16.0``
    incorrect-masking failure.  It validates the cause from durable raw bytes;
    arbitrary exception strings cannot authorize a protocol Close.
    """

    transport_subscription_policy_id: str
    transport_session_id: str
    physical_scope_manifest_id: str
    adapter_policy_id: str
    capture_partition_id: str
    socket_lease_id: str
    connection_generation: int
    deployment_bundle_id: str
    writer_fence_token_sha256: str
    writer_fence_generation: int
    ingress_sequence: int
    raw_ingress_commit_id: str
    raw_ingress_chunks_base64: tuple[str, ...]
    raw_ingress_chunks_sha256: tuple[str, ...]
    raw_ingress_batch_sha256: str
    frame_offset: int
    protocol_failure_kind: InboundWebSocketProtocolFailureKindV4
    parser_exception_class_digest: str
    parser_exception_message_digest: str
    logical_close_payload_base64: str
    logical_close_payload_sha256: str
    detected_at: datetime
    monotonic_clock_domain_id: str
    detected_monotonic_ns: int
    fences_session_authority: bool

    def __post_init__(self) -> None:
        for field_name in (
            "transport_subscription_policy_id",
            "transport_session_id",
            "physical_scope_manifest_id",
            "adapter_policy_id",
            "capture_partition_id",
            "socket_lease_id",
            "deployment_bundle_id",
            "writer_fence_token_sha256",
            "raw_ingress_commit_id",
            "raw_ingress_batch_sha256",
            "parser_exception_class_digest",
            "parser_exception_message_digest",
            "logical_close_payload_sha256",
            "monotonic_clock_domain_id",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        for field_name in (
            "connection_generation",
            "writer_fence_generation",
            "ingress_sequence",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_safe_int(
                    getattr(self, field_name), field=field_name, minimum=1
                ),
            )
        frame_offset = canonical_safe_int(
            self.frame_offset, field="frame_offset", minimum=0
        )
        detected_monotonic_ns = canonical_safe_int(
            self.detected_monotonic_ns,
            field="detected_monotonic_ns",
            minimum=0,
        )
        object.__setattr__(self, "frame_offset", frame_offset)
        object.__setattr__(self, "detected_monotonic_ns", detected_monotonic_ns)

        # V4.6 doesn't yet persist the Sans-I/O parser cursor or a source-span
        # proof across ingress commits.  Consequently, the only byte boundary
        # this record can prove without trusting a caller-selected offset is
        # the first post-handshake WebSocket header.  Broader admission must
        # wait for durable parser-state / cross-read span evidence.
        if self.ingress_sequence != 1 or frame_offset != 0:
            raise CanonicalizationError(
                "V4.6 incorrect-masking evidence requires ingress sequence one "
                "at frame offset zero"
            )

        chunks_base64, chunks = _base64_sequence(
            self.raw_ingress_chunks_base64,
            field="raw_ingress_chunks_base64",
            maximum_items=V4_CONTROL_MAXIMUM_INGRESS_CHUNKS,
            maximum_total_bytes=V4_CONTROL_MAXIMUM_INGRESS_BYTES,
        )
        object.__setattr__(self, "raw_ingress_chunks_base64", chunks_base64)
        chunk_hashes = _hash_sequence(
            self.raw_ingress_chunks_sha256,
            field="raw_ingress_chunks_sha256",
        )
        expected_hashes = tuple(hashlib.sha256(chunk).hexdigest() for chunk in chunks)
        if chunk_hashes != expected_hashes:
            raise CanonicalizationError(
                "raw ingress chunk hashes differ from exact bytes"
            )
        object.__setattr__(self, "raw_ingress_chunks_sha256", chunk_hashes)
        if self.raw_ingress_batch_sha256 != _ingress_batch_sha256(chunks_base64):
            raise CanonicalizationError(
                "raw_ingress_batch_sha256 differs from exact chunk order"
            )

        raw = b"".join(chunks)
        if frame_offset + 2 > len(raw):
            raise CanonicalizationError(
                "frame_offset does not identify a complete WebSocket header"
            )
        if raw[frame_offset + 1] & 0x80 == 0:
            raise CanonicalizationError(
                "incorrect-masking evidence requires the server frame MASK bit"
            )

        kind = _enum(
            self.protocol_failure_kind,
            InboundWebSocketProtocolFailureKindV4,
            field="protocol_failure_kind",
        )
        object.__setattr__(self, "protocol_failure_kind", kind)
        if (
            kind is not InboundWebSocketProtocolFailureKindV4.INCORRECT_MASKING
            or self.parser_exception_class_digest
            != V4_INCORRECT_MASKING_PARSER_EXCEPTION_CLASS_DIGEST
            or self.parser_exception_message_digest
            != V4_INCORRECT_MASKING_PARSER_EXCEPTION_MESSAGE_DIGEST
        ):
            raise CanonicalizationError(
                "protocol failure differs from the pinned incorrect-masking cause"
            )

        close_payload = _canonical_base64(
            self.logical_close_payload_base64,
            field="logical_close_payload_base64",
            allow_empty=False,
        )
        if (
            close_payload != V4_INCORRECT_MASKING_CLOSE_PAYLOAD
            or self.logical_close_payload_sha256
            != hashlib.sha256(close_payload).hexdigest()
        ):
            raise CanonicalizationError(
                "protocol failure requires the exact code-1002 incorrect-masking Close payload"
            )
        _validate_close_payload(close_payload, protocol_failure=True)

        detected = utc_datetime(self.detected_at, field="detected_at")
        object.__setattr__(self, "detected_at", detected)
        fenced = _strict_bool(
            self.fences_session_authority, field="fences_session_authority"
        )
        if not fenced:
            raise CanonicalizationError(
                "inbound WebSocket protocol failure must fence session authority"
            )
        object.__setattr__(self, "fences_session_authority", True)

    def identity_payload(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if name == "detected_at":
                result[name] = utc_iso(value)
            elif name in {
                "raw_ingress_chunks_base64",
                "raw_ingress_chunks_sha256",
            }:
                result[name] = list(value)
            elif name == "protocol_failure_kind":
                result[name] = value.value
            else:
                result[name] = value
        return result

    @property
    def inbound_websocket_protocol_failure_id(self) -> str:
        return _identity("InboundWebSocketProtocolFailureV4_6", self.identity_payload())

    @property
    def raw_bytes(self) -> bytes:
        return b"".join(
            base64.b64decode(value, validate=True)
            for value in self.raw_ingress_chunks_base64
        )

    @property
    def logical_close_payload_bytes(self) -> bytes:
        return base64.b64decode(self.logical_close_payload_base64, validate=True)

    def as_dict(self) -> dict[str, Any]:
        return _record_mapping(
            self,
            identity_field="inbound_websocket_protocol_failure_id",
            identity=self.inbound_websocket_protocol_failure_id,
        )

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> InboundWebSocketProtocolFailureV4:
        expected = set(cls.__dataclass_fields__) | {
            "canonicalization_version",
            "schema_version",
            "inbound_websocket_protocol_failure_id",
        }
        require_exact_keys(payload, expected=expected, context=cls.__name__)
        _require_versions(payload)
        item = cls(**{name: payload[name] for name in cls.__dataclass_fields__})
        _require_identity(
            payload["inbound_websocket_protocol_failure_id"],
            item.inbound_websocket_protocol_failure_id,
            field="inbound_websocket_protocol_failure_id",
        )
        return item


@dataclass(frozen=True, slots=True, kw_only=True)
class InboundRfcControlTriggerV4:
    transport_subscription_policy_id: str
    transport_session_id: str
    physical_scope_manifest_id: str
    adapter_policy_id: str
    capture_partition_id: str
    socket_lease_id: str
    connection_generation: int
    deployment_bundle_id: str
    writer_fence_token_sha256: str
    writer_fence_generation: int
    ingress_sequence: int
    raw_ingress_commit_id: str
    raw_ingress_chunks_base64: tuple[str, ...]
    raw_ingress_chunks_sha256: tuple[str, ...]
    raw_ingress_batch_sha256: str
    frame_offset: int
    frame_length: int
    opcode: InboundRfcControlOpcodeV4
    payload_base64: str
    payload_sha256: str
    received_at: datetime
    monotonic_clock_domain_id: str
    received_monotonic_ns: int

    def __post_init__(self) -> None:
        for field_name in (
            "transport_subscription_policy_id",
            "transport_session_id",
            "physical_scope_manifest_id",
            "adapter_policy_id",
            "capture_partition_id",
            "socket_lease_id",
            "deployment_bundle_id",
            "writer_fence_token_sha256",
            "raw_ingress_commit_id",
            "raw_ingress_batch_sha256",
            "payload_sha256",
            "monotonic_clock_domain_id",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        for field_name in (
            "connection_generation",
            "writer_fence_generation",
            "ingress_sequence",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_safe_int(
                    getattr(self, field_name), field=field_name, minimum=1
                ),
            )
        for field_name in ("frame_offset", "frame_length", "received_monotonic_ns"):
            object.__setattr__(
                self,
                field_name,
                canonical_safe_int(
                    getattr(self, field_name), field=field_name, minimum=0
                ),
            )
        chunks_base64, chunks = _base64_sequence(
            self.raw_ingress_chunks_base64,
            field="raw_ingress_chunks_base64",
            maximum_items=V4_CONTROL_MAXIMUM_INGRESS_CHUNKS,
            maximum_total_bytes=V4_CONTROL_MAXIMUM_INGRESS_BYTES,
        )
        object.__setattr__(self, "raw_ingress_chunks_base64", chunks_base64)
        chunk_hashes = _hash_sequence(
            self.raw_ingress_chunks_sha256, field="raw_ingress_chunks_sha256"
        )
        expected_hashes = tuple(hashlib.sha256(chunk).hexdigest() for chunk in chunks)
        if chunk_hashes != expected_hashes:
            raise CanonicalizationError(
                "raw ingress chunk hashes differ from exact bytes"
            )
        object.__setattr__(self, "raw_ingress_chunks_sha256", chunk_hashes)
        if self.raw_ingress_batch_sha256 != _ingress_batch_sha256(chunks_base64):
            raise CanonicalizationError(
                "raw_ingress_batch_sha256 differs from exact chunk order"
            )
        opcode = _enum(self.opcode, InboundRfcControlOpcodeV4, field="opcode")
        object.__setattr__(self, "opcode", opcode)
        payload = _canonical_base64(self.payload_base64, field="payload_base64")
        if len(payload) > V4_CONTROL_MAXIMUM_CONTROL_PAYLOAD_BYTES:
            raise CanonicalizationError("RFC control payload exceeds 125 bytes")
        if self.payload_sha256 != hashlib.sha256(payload).hexdigest():
            raise CanonicalizationError(
                "payload_sha256 differs from exact control payload"
            )
        raw = b"".join(chunks)
        frame_opcode, frame_length, frame_payload = _parse_frame_at(
            raw, offset=self.frame_offset, require_mask=False
        )
        if frame_opcode != _INBOUND_OPCODE_NUMBER[opcode]:
            raise CanonicalizationError(
                "declared inbound opcode differs from raw frame"
            )
        if frame_length != self.frame_length or frame_payload != payload:
            raise CanonicalizationError(
                "declared inbound frame differs from durable raw ingress"
            )
        if opcode is InboundRfcControlOpcodeV4.CLOSE:
            _validate_close_payload(payload)
        received = utc_datetime(self.received_at, field="received_at")
        object.__setattr__(self, "received_at", received)

    def identity_payload(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if name == "received_at":
                result[name] = utc_iso(value)
            elif name in {"raw_ingress_chunks_base64", "raw_ingress_chunks_sha256"}:
                result[name] = list(value)
            elif name == "opcode":
                result[name] = value.value
            else:
                result[name] = value
        return result

    @property
    def inbound_rfc_control_trigger_id(self) -> str:
        return _identity("InboundRfcControlTriggerV4_5", self.identity_payload())

    @property
    def payload_bytes(self) -> bytes:
        return base64.b64decode(self.payload_base64, validate=True)

    def as_dict(self) -> dict[str, Any]:
        return _record_mapping(
            self,
            identity_field="inbound_rfc_control_trigger_id",
            identity=self.inbound_rfc_control_trigger_id,
        )

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> InboundRfcControlTriggerV4:
        expected = set(cls.__dataclass_fields__) | {
            "canonicalization_version",
            "schema_version",
            "inbound_rfc_control_trigger_id",
        }
        require_exact_keys(payload, expected=expected, context=cls.__name__)
        _require_versions(payload)
        item = cls(**{name: payload[name] for name in cls.__dataclass_fields__})
        _require_identity(
            payload["inbound_rfc_control_trigger_id"],
            item.inbound_rfc_control_trigger_id,
            field="inbound_rfc_control_trigger_id",
        )
        return item


@dataclass(frozen=True, slots=True, kw_only=True)
class OutboundControlIntentV4:
    transport_subscription_policy_id: str
    transport_session_id: str
    physical_scope_manifest_id: str
    adapter_policy_id: str
    capture_partition_id: str
    socket_lease_id: str
    connection_generation: int
    deployment_bundle_id: str
    writer_fence_token_sha256: str
    writer_fence_generation: int
    control_sequence: int
    previous_outbound_control_intent_id: str | None
    control_kind: OutboundControlKindV4
    scheduled_heartbeat_id: str | None
    inbound_rfc_control_trigger_id: str | None
    inbound_rfc_opcode: InboundRfcControlOpcodeV4 | None
    inbound_rfc_payload_base64: str | None
    protocol_failure_evidence_id: str | None
    logical_websocket_opcode: OutboundWebSocketOpcodeV4
    logical_payload_base64: str
    logical_payload_sha256: str
    request_id: str | None
    fences_session_authority: bool
    authorized_at: datetime
    monotonic_clock_domain_id: str
    authorized_monotonic_ns: int
    send_not_after: datetime
    send_not_after_monotonic_ns: int

    def __post_init__(self) -> None:
        for field_name in (
            "transport_subscription_policy_id",
            "transport_session_id",
            "physical_scope_manifest_id",
            "adapter_policy_id",
            "capture_partition_id",
            "socket_lease_id",
            "deployment_bundle_id",
            "writer_fence_token_sha256",
            "logical_payload_sha256",
            "monotonic_clock_domain_id",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "previous_outbound_control_intent_id",
            _optional_hash(
                self.previous_outbound_control_intent_id,
                field="previous_outbound_control_intent_id",
            ),
        )
        object.__setattr__(
            self,
            "scheduled_heartbeat_id",
            _optional_hash(self.scheduled_heartbeat_id, field="scheduled_heartbeat_id"),
        )
        object.__setattr__(
            self,
            "inbound_rfc_control_trigger_id",
            _optional_hash(
                self.inbound_rfc_control_trigger_id,
                field="inbound_rfc_control_trigger_id",
            ),
        )
        object.__setattr__(
            self,
            "protocol_failure_evidence_id",
            _optional_hash(
                self.protocol_failure_evidence_id, field="protocol_failure_evidence_id"
            ),
        )
        for field_name in (
            "connection_generation",
            "writer_fence_generation",
            "control_sequence",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_safe_int(
                    getattr(self, field_name), field=field_name, minimum=1
                ),
            )
        if (self.control_sequence == 1) != (
            self.previous_outbound_control_intent_id is None
        ):
            raise CanonicalizationError(
                "only control sequence one may omit the predecessor intent"
            )
        kind = _enum(self.control_kind, OutboundControlKindV4, field="control_kind")
        opcode = _enum(
            self.logical_websocket_opcode,
            OutboundWebSocketOpcodeV4,
            field="logical_websocket_opcode",
        )
        inbound_opcode = (
            None
            if self.inbound_rfc_opcode is None
            else _enum(
                self.inbound_rfc_opcode,
                InboundRfcControlOpcodeV4,
                field="inbound_rfc_opcode",
            )
        )
        object.__setattr__(self, "control_kind", kind)
        object.__setattr__(self, "logical_websocket_opcode", opcode)
        object.__setattr__(self, "inbound_rfc_opcode", inbound_opcode)
        logical_payload = _canonical_base64(
            self.logical_payload_base64, field="logical_payload_base64"
        )
        if self.logical_payload_sha256 != hashlib.sha256(logical_payload).hexdigest():
            raise CanonicalizationError(
                "logical_payload_sha256 differs from exact payload"
            )
        inbound_payload = (
            None
            if self.inbound_rfc_payload_base64 is None
            else _canonical_base64(
                self.inbound_rfc_payload_base64, field="inbound_rfc_payload_base64"
            )
        )
        request_id = None if self.request_id is None else _request_id(self.request_id)
        object.__setattr__(self, "request_id", request_id)
        fenced = _strict_bool(
            self.fences_session_authority, field="fences_session_authority"
        )
        object.__setattr__(self, "fences_session_authority", fenced)

        if kind is OutboundControlKindV4.APPLICATION_JSON_HEARTBEAT:
            if (
                opcode is not OutboundWebSocketOpcodeV4.TEXT
                or self.scheduled_heartbeat_id is None
                or self.inbound_rfc_control_trigger_id is not None
                or inbound_opcode is not None
                or inbound_payload is not None
                or self.protocol_failure_evidence_id is not None
                or request_id is None
                or fenced
            ):
                raise CanonicalizationError(
                    "application heartbeat has invalid causal fields"
                )
            expected = canonical_json_bytes({"op": "ping", "req_id": request_id})
            if logical_payload != expected or strict_json_loads(logical_payload) != {
                "op": "ping",
                "req_id": request_id,
            }:
                raise CanonicalizationError(
                    "Bybit heartbeat payload is not the exact reviewed JSON command"
                )
        elif kind is OutboundControlKindV4.RFC_PONG:
            if (
                opcode is not OutboundWebSocketOpcodeV4.PONG
                or self.inbound_rfc_control_trigger_id is None
                or inbound_opcode is not InboundRfcControlOpcodeV4.PING
                or inbound_payload is None
                or logical_payload != inbound_payload
                or self.scheduled_heartbeat_id is not None
                or self.protocol_failure_evidence_id is not None
                or request_id is not None
                or fenced
            ):
                raise CanonicalizationError(
                    "RFC Pong must exactly echo one durable inbound Ping"
                )
            if len(logical_payload) > V4_CONTROL_MAXIMUM_CONTROL_PAYLOAD_BYTES:
                raise CanonicalizationError("RFC Pong payload exceeds 125 bytes")
        elif kind is OutboundControlKindV4.RFC_CLOSE_REPLY:
            if (
                opcode is not OutboundWebSocketOpcodeV4.CLOSE
                or self.inbound_rfc_control_trigger_id is None
                or inbound_opcode is not InboundRfcControlOpcodeV4.CLOSE
                or inbound_payload is None
                or logical_payload != inbound_payload
                or self.scheduled_heartbeat_id is not None
                or self.protocol_failure_evidence_id is not None
                or request_id is not None
                or not fenced
            ):
                raise CanonicalizationError(
                    "RFC Close reply must exactly echo and fence one inbound Close"
                )
            _validate_close_payload(logical_payload)
        else:
            if (
                opcode is not OutboundWebSocketOpcodeV4.CLOSE
                or self.protocol_failure_evidence_id is None
                or self.scheduled_heartbeat_id is not None
                or self.inbound_rfc_control_trigger_id is not None
                or inbound_opcode is not None
                or inbound_payload is not None
                or request_id is not None
                or not fenced
            ):
                raise CanonicalizationError(
                    "protocol-failure Close has invalid causal fields"
                )
            _validate_close_payload(logical_payload, protocol_failure=True)

        authorized = utc_datetime(self.authorized_at, field="authorized_at")
        send_by = utc_datetime(self.send_not_after, field="send_not_after")
        authorized_ns = canonical_safe_int(
            self.authorized_monotonic_ns, field="authorized_monotonic_ns", minimum=0
        )
        send_by_ns = canonical_safe_int(
            self.send_not_after_monotonic_ns,
            field="send_not_after_monotonic_ns",
            minimum=0,
        )
        if authorized >= send_by or authorized_ns >= send_by_ns:
            raise CanonicalizationError(
                "control send deadline must follow authorization"
            )
        object.__setattr__(self, "authorized_at", authorized)
        object.__setattr__(self, "send_not_after", send_by)
        object.__setattr__(self, "authorized_monotonic_ns", authorized_ns)
        object.__setattr__(self, "send_not_after_monotonic_ns", send_by_ns)

    def identity_payload(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if name in {"authorized_at", "send_not_after"}:
                result[name] = utc_iso(value)
            elif name in {"control_kind", "logical_websocket_opcode"}:
                result[name] = value.value
            elif name == "inbound_rfc_opcode":
                result[name] = None if value is None else value.value
            else:
                result[name] = value
        return result

    @property
    def outbound_control_intent_id(self) -> str:
        return _identity("OutboundControlIntentV4_5", self.identity_payload())

    @property
    def logical_payload_bytes(self) -> bytes:
        return base64.b64decode(self.logical_payload_base64, validate=True)

    def as_dict(self) -> dict[str, Any]:
        return _record_mapping(
            self,
            identity_field="outbound_control_intent_id",
            identity=self.outbound_control_intent_id,
        )

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> OutboundControlIntentV4:
        expected = set(cls.__dataclass_fields__) | {
            "canonicalization_version",
            "schema_version",
            "outbound_control_intent_id",
        }
        require_exact_keys(payload, expected=expected, context=cls.__name__)
        _require_versions(payload)
        item = cls(**{name: payload[name] for name in cls.__dataclass_fields__})
        _require_identity(
            payload["outbound_control_intent_id"],
            item.outbound_control_intent_id,
            field="outbound_control_intent_id",
        )
        return item


def build_bybit_json_heartbeat_intent_v4(
    *,
    transport_subscription_policy_id: str,
    transport_session_id: str,
    physical_scope_manifest_id: str,
    adapter_policy_id: str,
    capture_partition_id: str,
    socket_lease_id: str,
    connection_generation: int,
    deployment_bundle_id: str,
    writer_fence_token_sha256: str,
    writer_fence_generation: int,
    control_sequence: int,
    previous_outbound_control_intent_id: str | None,
    scheduled_heartbeat_id: str,
    request_id: str,
    authorized_at: datetime | str,
    monotonic_clock_domain_id: str,
    authorized_monotonic_ns: int,
    send_not_after: datetime | str,
    send_not_after_monotonic_ns: int,
) -> OutboundControlIntentV4:
    checked_request_id = _request_id(request_id)
    payload = canonical_json_bytes({"op": "ping", "req_id": checked_request_id})
    return OutboundControlIntentV4(
        transport_subscription_policy_id=transport_subscription_policy_id,
        transport_session_id=transport_session_id,
        physical_scope_manifest_id=physical_scope_manifest_id,
        adapter_policy_id=adapter_policy_id,
        capture_partition_id=capture_partition_id,
        socket_lease_id=socket_lease_id,
        connection_generation=connection_generation,
        deployment_bundle_id=deployment_bundle_id,
        writer_fence_token_sha256=writer_fence_token_sha256,
        writer_fence_generation=writer_fence_generation,
        control_sequence=control_sequence,
        previous_outbound_control_intent_id=previous_outbound_control_intent_id,
        control_kind=OutboundControlKindV4.APPLICATION_JSON_HEARTBEAT,
        scheduled_heartbeat_id=scheduled_heartbeat_id,
        inbound_rfc_control_trigger_id=None,
        inbound_rfc_opcode=None,
        inbound_rfc_payload_base64=None,
        protocol_failure_evidence_id=None,
        logical_websocket_opcode=OutboundWebSocketOpcodeV4.TEXT,
        logical_payload_base64=base64.b64encode(payload).decode("ascii"),
        logical_payload_sha256=hashlib.sha256(payload).hexdigest(),
        request_id=checked_request_id,
        fences_session_authority=False,
        authorized_at=authorized_at,
        monotonic_clock_domain_id=monotonic_clock_domain_id,
        authorized_monotonic_ns=authorized_monotonic_ns,
        send_not_after=send_not_after,
        send_not_after_monotonic_ns=send_not_after_monotonic_ns,
    )


@dataclass(frozen=True, slots=True, kw_only=True)
class OutboundControlWirePreparedV4:
    outbound_control_intent_id: str
    transport_session_id: str
    socket_lease_id: str
    connection_generation: int
    deployment_bundle_id: str
    writer_fence_token_sha256: str
    writer_fence_generation: int
    control_kind: OutboundControlKindV4
    logical_websocket_opcode: OutboundWebSocketOpcodeV4
    logical_payload_base64: str
    logical_payload_sha256: str
    wire_chunks_base64: tuple[str, ...]
    wire_chunks_sha256: tuple[str, ...]
    wire_batch_sha256: str
    wire_octet_length: int
    prepared_at: datetime
    monotonic_clock_domain_id: str
    prepared_monotonic_ns: int
    send_not_after: datetime
    send_not_after_monotonic_ns: int

    def __post_init__(self) -> None:
        for field_name in (
            "outbound_control_intent_id",
            "transport_session_id",
            "socket_lease_id",
            "deployment_bundle_id",
            "writer_fence_token_sha256",
            "logical_payload_sha256",
            "wire_batch_sha256",
            "monotonic_clock_domain_id",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        for field_name in ("connection_generation", "writer_fence_generation"):
            object.__setattr__(
                self,
                field_name,
                canonical_safe_int(
                    getattr(self, field_name), field=field_name, minimum=1
                ),
            )
        kind = _enum(self.control_kind, OutboundControlKindV4, field="control_kind")
        opcode = _enum(
            self.logical_websocket_opcode,
            OutboundWebSocketOpcodeV4,
            field="logical_websocket_opcode",
        )
        object.__setattr__(self, "control_kind", kind)
        object.__setattr__(self, "logical_websocket_opcode", opcode)
        expected_opcode = {
            OutboundControlKindV4.APPLICATION_JSON_HEARTBEAT: (
                OutboundWebSocketOpcodeV4.TEXT
            ),
            OutboundControlKindV4.RFC_PONG: OutboundWebSocketOpcodeV4.PONG,
            OutboundControlKindV4.RFC_CLOSE_REPLY: OutboundWebSocketOpcodeV4.CLOSE,
            OutboundControlKindV4.RFC_PROTOCOL_FAILURE_CLOSE: (
                OutboundWebSocketOpcodeV4.CLOSE
            ),
        }[kind]
        if opcode is not expected_opcode:
            raise CanonicalizationError(
                "wire control kind and logical WebSocket opcode are incompatible"
            )
        payload = _canonical_base64(
            self.logical_payload_base64, field="logical_payload_base64"
        )
        if self.logical_payload_sha256 != hashlib.sha256(payload).hexdigest():
            raise CanonicalizationError(
                "logical payload hash differs from exact payload"
            )
        chunks_base64, chunks = _base64_sequence(
            self.wire_chunks_base64,
            field="wire_chunks_base64",
            maximum_items=V4_CONTROL_MAXIMUM_WIRE_CHUNKS,
            maximum_total_bytes=V4_CONTROL_MAXIMUM_WIRE_BYTES,
        )
        object.__setattr__(self, "wire_chunks_base64", chunks_base64)
        chunk_hashes = _hash_sequence(
            self.wire_chunks_sha256, field="wire_chunks_sha256"
        )
        expected_hashes = tuple(hashlib.sha256(chunk).hexdigest() for chunk in chunks)
        if chunk_hashes != expected_hashes:
            raise CanonicalizationError("wire chunk hashes differ from exact bytes")
        object.__setattr__(self, "wire_chunks_sha256", chunk_hashes)
        if self.wire_batch_sha256 != _wire_batch_sha256(chunks_base64):
            raise CanonicalizationError(
                "wire_batch_sha256 differs from exact chunk order"
            )
        wire = b"".join(chunks)
        wire_length = canonical_safe_int(
            self.wire_octet_length, field="wire_octet_length", minimum=1
        )
        if wire_length != len(wire):
            raise CanonicalizationError("wire_octet_length differs from exact chunks")
        object.__setattr__(self, "wire_octet_length", wire_length)
        frame_opcode, frame_length, frame_payload = _parse_frame_at(
            wire, offset=0, require_mask=True
        )
        if frame_length != len(wire):
            raise CanonicalizationError(
                "wire chunks must contain exactly one WebSocket frame"
            )
        if frame_opcode != _OUTBOUND_OPCODE_NUMBER[opcode] or frame_payload != payload:
            raise CanonicalizationError(
                "masked frame differs from the logical control intent"
            )
        if opcode is OutboundWebSocketOpcodeV4.TEXT:
            try:
                payload.decode("utf-8", errors="strict")
            except UnicodeDecodeError as exc:
                raise CanonicalizationError(
                    "Text frame payload must be valid UTF-8"
                ) from exc
        else:
            if len(payload) > V4_CONTROL_MAXIMUM_CONTROL_PAYLOAD_BYTES:
                raise CanonicalizationError("RFC control payload exceeds 125 bytes")
            if opcode is OutboundWebSocketOpcodeV4.CLOSE:
                _validate_close_payload(
                    payload,
                    protocol_failure=(
                        kind is OutboundControlKindV4.RFC_PROTOCOL_FAILURE_CLOSE
                    ),
                )
        prepared = utc_datetime(self.prepared_at, field="prepared_at")
        send_by = utc_datetime(self.send_not_after, field="send_not_after")
        prepared_ns = canonical_safe_int(
            self.prepared_monotonic_ns, field="prepared_monotonic_ns", minimum=0
        )
        send_by_ns = canonical_safe_int(
            self.send_not_after_monotonic_ns,
            field="send_not_after_monotonic_ns",
            minimum=0,
        )
        if prepared >= send_by or prepared_ns >= send_by_ns:
            raise CanonicalizationError(
                "wire preparation must precede the send deadline"
            )
        object.__setattr__(self, "prepared_at", prepared)
        object.__setattr__(self, "send_not_after", send_by)
        object.__setattr__(self, "prepared_monotonic_ns", prepared_ns)
        object.__setattr__(self, "send_not_after_monotonic_ns", send_by_ns)

    def identity_payload(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if name in {"prepared_at", "send_not_after"}:
                result[name] = utc_iso(value)
            elif name in {"control_kind", "logical_websocket_opcode"}:
                result[name] = value.value
            elif name in {"wire_chunks_base64", "wire_chunks_sha256"}:
                result[name] = list(value)
            else:
                result[name] = value
        return result

    @property
    def outbound_control_wire_prepared_id(self) -> str:
        return _identity("OutboundControlWirePreparedV4_5", self.identity_payload())

    @property
    def wire_bytes(self) -> bytes:
        return b"".join(
            base64.b64decode(item, validate=True) for item in self.wire_chunks_base64
        )

    def as_dict(self) -> dict[str, Any]:
        return _record_mapping(
            self,
            identity_field="outbound_control_wire_prepared_id",
            identity=self.outbound_control_wire_prepared_id,
        )

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> OutboundControlWirePreparedV4:
        expected = set(cls.__dataclass_fields__) | {
            "canonicalization_version",
            "schema_version",
            "outbound_control_wire_prepared_id",
        }
        require_exact_keys(payload, expected=expected, context=cls.__name__)
        _require_versions(payload)
        item = cls(**{name: payload[name] for name in cls.__dataclass_fields__})
        _require_identity(
            payload["outbound_control_wire_prepared_id"],
            item.outbound_control_wire_prepared_id,
            field="outbound_control_wire_prepared_id",
        )
        return item


@dataclass(frozen=True, slots=True, kw_only=True)
class OutboundControlWritePermitConsumedV4:
    """Durable one-shot authority consumed before a TLS write may begin."""

    outbound_control_intent_id: str
    outbound_control_wire_prepared_id: str
    transport_session_id: str
    socket_lease_id: str
    connection_generation: int
    deployment_bundle_id: str
    writer_fence_token_sha256: str
    writer_fence_generation: int
    control_kind: OutboundControlKindV4
    wire_batch_sha256: str
    wire_octet_length: int
    one_shot_attempt_ordinal: int
    wire_prepared_at: datetime
    monotonic_clock_domain_id: str
    wire_prepared_monotonic_ns: int
    permit_consumed_at: datetime
    permit_consumed_monotonic_ns: int
    send_not_after: datetime
    send_not_after_monotonic_ns: int

    def __post_init__(self) -> None:
        for field_name in (
            "outbound_control_intent_id",
            "outbound_control_wire_prepared_id",
            "transport_session_id",
            "socket_lease_id",
            "deployment_bundle_id",
            "writer_fence_token_sha256",
            "wire_batch_sha256",
            "monotonic_clock_domain_id",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        for field_name in ("connection_generation", "writer_fence_generation"):
            object.__setattr__(
                self,
                field_name,
                canonical_safe_int(
                    getattr(self, field_name), field=field_name, minimum=1
                ),
            )
        kind = _enum(self.control_kind, OutboundControlKindV4, field="control_kind")
        object.__setattr__(self, "control_kind", kind)
        wire_length = canonical_safe_int(
            self.wire_octet_length, field="wire_octet_length", minimum=1
        )
        attempt = canonical_safe_int(
            self.one_shot_attempt_ordinal,
            field="one_shot_attempt_ordinal",
            minimum=1,
        )
        if attempt != 1:
            raise CanonicalizationError(
                "control write permit must consume attempt ordinal one"
            )
        object.__setattr__(self, "wire_octet_length", wire_length)
        object.__setattr__(self, "one_shot_attempt_ordinal", attempt)

        prepared = utc_datetime(self.wire_prepared_at, field="wire_prepared_at")
        consumed = utc_datetime(self.permit_consumed_at, field="permit_consumed_at")
        send_by = utc_datetime(self.send_not_after, field="send_not_after")
        prepared_ns = canonical_safe_int(
            self.wire_prepared_monotonic_ns,
            field="wire_prepared_monotonic_ns",
            minimum=0,
        )
        consumed_ns = canonical_safe_int(
            self.permit_consumed_monotonic_ns,
            field="permit_consumed_monotonic_ns",
            minimum=0,
        )
        send_by_ns = canonical_safe_int(
            self.send_not_after_monotonic_ns,
            field="send_not_after_monotonic_ns",
            minimum=0,
        )
        if not prepared < consumed < send_by:
            raise CanonicalizationError(
                "permit wall clocks must place consumption after preparation and before deadline"
            )
        if not prepared_ns < consumed_ns < send_by_ns:
            raise CanonicalizationError(
                "permit monotonic clocks must place consumption after preparation and before deadline"
            )
        object.__setattr__(self, "wire_prepared_at", prepared)
        object.__setattr__(self, "permit_consumed_at", consumed)
        object.__setattr__(self, "send_not_after", send_by)
        object.__setattr__(self, "wire_prepared_monotonic_ns", prepared_ns)
        object.__setattr__(self, "permit_consumed_monotonic_ns", consumed_ns)
        object.__setattr__(self, "send_not_after_monotonic_ns", send_by_ns)

    def identity_payload(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if name in {
                "wire_prepared_at",
                "permit_consumed_at",
                "send_not_after",
            }:
                result[name] = utc_iso(value)
            elif name == "control_kind":
                result[name] = value.value
            else:
                result[name] = value
        return result

    @property
    def permit_id(self) -> str:
        return _identity(
            "OutboundControlWritePermitConsumedV4_6", self.identity_payload()
        )

    def as_dict(self) -> dict[str, Any]:
        return _record_mapping(
            self,
            identity_field="permit_id",
            identity=self.permit_id,
        )

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> OutboundControlWritePermitConsumedV4:
        expected = set(cls.__dataclass_fields__) | {
            "canonicalization_version",
            "schema_version",
            "permit_id",
        }
        require_exact_keys(payload, expected=expected, context=cls.__name__)
        _require_versions(payload)
        item = cls(**{name: payload[name] for name in cls.__dataclass_fields__})
        _require_identity(payload["permit_id"], item.permit_id, field="permit_id")
        return item


_DISPATCH_SIGNING_DOMAIN = "RiskYieldMMOutboundControlDispatchResultSignatureV4_5"


@dataclass(frozen=True, slots=True, kw_only=True)
class OutboundControlDispatchResultV4:
    outbound_control_intent_id: str
    outbound_control_wire_prepared_id: str
    transport_session_id: str
    socket_lease_id: str
    connection_generation: int
    deployment_bundle_id: str
    writer_fence_token_sha256: str
    writer_fence_generation: int
    control_kind: OutboundControlKindV4
    wire_batch_sha256: str
    wire_octet_length: int
    permit_id: str
    permit_consumed: bool
    one_shot_attempt_ordinal: int
    disposition: OutboundControlDispatchDispositionV4
    wire_prepared_at: datetime
    monotonic_clock_domain_id: str
    wire_prepared_monotonic_ns: int
    dispatch_started_at: datetime
    dispatch_started_monotonic_ns: int
    dispatch_outcome_at: datetime
    dispatch_outcome_monotonic_ns: int
    send_not_after: datetime
    send_not_after_monotonic_ns: int
    bytes_submitted_to_tls: int | None
    error_class_digest: str | None
    collector_attestation_key_id: str
    collector_attestation_public_key_hex: str
    signature_hex: str

    def __post_init__(self) -> None:
        for field_name in (
            "outbound_control_intent_id",
            "outbound_control_wire_prepared_id",
            "transport_session_id",
            "socket_lease_id",
            "deployment_bundle_id",
            "writer_fence_token_sha256",
            "wire_batch_sha256",
            "permit_id",
            "monotonic_clock_domain_id",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "error_class_digest",
            _optional_hash(self.error_class_digest, field="error_class_digest"),
        )
        for field_name in ("connection_generation", "writer_fence_generation"):
            object.__setattr__(
                self,
                field_name,
                canonical_safe_int(
                    getattr(self, field_name), field=field_name, minimum=1
                ),
            )
        wire_length = canonical_safe_int(
            self.wire_octet_length, field="wire_octet_length", minimum=1
        )
        bytes_submitted = (
            None
            if self.bytes_submitted_to_tls is None
            else canonical_safe_int(
                self.bytes_submitted_to_tls,
                field="bytes_submitted_to_tls",
                minimum=0,
                maximum=wire_length,
            )
        )
        attempt = canonical_safe_int(
            self.one_shot_attempt_ordinal, field="one_shot_attempt_ordinal", minimum=1
        )
        if attempt != 1 or not _strict_bool(
            self.permit_consumed, field="permit_consumed"
        ):
            raise CanonicalizationError(
                "control dispatch must consume exactly one one-shot attempt"
            )
        object.__setattr__(self, "wire_octet_length", wire_length)
        object.__setattr__(self, "bytes_submitted_to_tls", bytes_submitted)
        object.__setattr__(self, "one_shot_attempt_ordinal", attempt)
        object.__setattr__(self, "permit_consumed", True)
        kind = _enum(self.control_kind, OutboundControlKindV4, field="control_kind")
        disposition = _enum(
            self.disposition, OutboundControlDispatchDispositionV4, field="disposition"
        )
        object.__setattr__(self, "control_kind", kind)
        object.__setattr__(self, "disposition", disposition)
        if disposition is OutboundControlDispatchDispositionV4.SENT:
            if bytes_submitted != wire_length or self.error_class_digest is not None:
                raise CanonicalizationError(
                    "SENT requires the full batch and no error digest"
                )
        elif self.error_class_digest is None:
            raise CanonicalizationError(
                "UNKNOWN_DELIVERY requires an error_class_digest"
            )
        prepared = utc_datetime(self.wire_prepared_at, field="wire_prepared_at")
        started = utc_datetime(self.dispatch_started_at, field="dispatch_started_at")
        outcome = utc_datetime(self.dispatch_outcome_at, field="dispatch_outcome_at")
        send_by = utc_datetime(self.send_not_after, field="send_not_after")
        prepared_ns = canonical_safe_int(
            self.wire_prepared_monotonic_ns,
            field="wire_prepared_monotonic_ns",
            minimum=0,
        )
        started_ns = canonical_safe_int(
            self.dispatch_started_monotonic_ns,
            field="dispatch_started_monotonic_ns",
            minimum=0,
        )
        outcome_ns = canonical_safe_int(
            self.dispatch_outcome_monotonic_ns,
            field="dispatch_outcome_monotonic_ns",
            minimum=0,
        )
        send_by_ns = canonical_safe_int(
            self.send_not_after_monotonic_ns,
            field="send_not_after_monotonic_ns",
            minimum=0,
        )
        if not prepared < started < outcome or not started < send_by:
            raise CanonicalizationError(
                "dispatch wall clocks violate preparation/deadline order"
            )
        if not prepared_ns < started_ns < outcome_ns or not started_ns < send_by_ns:
            raise CanonicalizationError(
                "dispatch monotonic clocks violate preparation/deadline order"
            )
        object.__setattr__(self, "wire_prepared_at", prepared)
        object.__setattr__(self, "dispatch_started_at", started)
        object.__setattr__(self, "dispatch_outcome_at", outcome)
        object.__setattr__(self, "send_not_after", send_by)
        object.__setattr__(self, "wire_prepared_monotonic_ns", prepared_ns)
        object.__setattr__(self, "dispatch_started_monotonic_ns", started_ns)
        object.__setattr__(self, "dispatch_outcome_monotonic_ns", outcome_ns)
        object.__setattr__(self, "send_not_after_monotonic_ns", send_by_ns)
        key_id, public_hex, public_key = _key_pair(
            self.collector_attestation_key_id,
            self.collector_attestation_public_key_hex,
        )
        object.__setattr__(self, "collector_attestation_key_id", key_id)
        object.__setattr__(self, "collector_attestation_public_key_hex", public_hex)
        signature = _verify_signature(
            public_key=public_key,
            signature_hex=self.signature_hex,
            payload=self.signing_payload(),
        )
        object.__setattr__(self, "signature_hex", signature)

    def identity_payload(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for name in self.__dataclass_fields__:
            if name == "signature_hex":
                continue
            value = getattr(self, name)
            if name in {
                "wire_prepared_at",
                "dispatch_started_at",
                "dispatch_outcome_at",
                "send_not_after",
            }:
                result[name] = utc_iso(value)
            elif name in {"control_kind", "disposition"}:
                result[name] = value.value
            else:
                result[name] = value
        return result

    def signing_payload(self) -> dict[str, Any]:
        return _signature_payload(_DISPATCH_SIGNING_DOMAIN, self.identity_payload())

    @property
    def outbound_control_dispatch_result_id(self) -> str:
        return _identity("OutboundControlDispatchResultV4_5", self.identity_payload())

    def verify_signature(self) -> None:
        _, _, public_key = _key_pair(
            self.collector_attestation_key_id,
            self.collector_attestation_public_key_hex,
        )
        _verify_signature(
            public_key=public_key,
            signature_hex=self.signature_hex,
            payload=self.signing_payload(),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            **_record_mapping(
                self,
                identity_field="outbound_control_dispatch_result_id",
                identity=self.outbound_control_dispatch_result_id,
            ),
            "signature_hex": self.signature_hex,
        }

    @classmethod
    def create_signed(
        cls, *, signer: Any, **fields: Any
    ) -> OutboundControlDispatchResultV4:
        key_id, public_hex = _signer_key(signer)
        forbidden = {
            "collector_attestation_key_id",
            "collector_attestation_public_key_hex",
            "signature_hex",
        }
        if forbidden.intersection(fields):
            raise CanonicalizationError(
                "signed dispatch key/signature fields are derived"
            )
        unsigned = _dispatch_identity_payload(
            {
                **fields,
                "collector_attestation_key_id": key_id,
                "collector_attestation_public_key_hex": public_hex,
            }
        )
        signature = _sign(
            signer, _signature_payload(_DISPATCH_SIGNING_DOMAIN, unsigned)
        )
        return cls(
            **fields,
            collector_attestation_key_id=key_id,
            collector_attestation_public_key_hex=public_hex,
            signature_hex=signature,
        )

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> OutboundControlDispatchResultV4:
        expected = set(cls.__dataclass_fields__) | {
            "canonicalization_version",
            "schema_version",
            "outbound_control_dispatch_result_id",
        }
        require_exact_keys(payload, expected=expected, context=cls.__name__)
        _require_versions(payload)
        item = cls(**{name: payload[name] for name in cls.__dataclass_fields__})
        _require_identity(
            payload["outbound_control_dispatch_result_id"],
            item.outbound_control_dispatch_result_id,
            field="outbound_control_dispatch_result_id",
        )
        return item


def _dispatch_identity_payload(values: Mapping[str, Any]) -> dict[str, Any]:
    hash_fields = {
        "outbound_control_intent_id",
        "outbound_control_wire_prepared_id",
        "transport_session_id",
        "socket_lease_id",
        "deployment_bundle_id",
        "writer_fence_token_sha256",
        "wire_batch_sha256",
        "permit_id",
        "monotonic_clock_domain_id",
        "collector_attestation_key_id",
    }
    integer_fields = {
        "connection_generation",
        "writer_fence_generation",
        "wire_octet_length",
        "one_shot_attempt_ordinal",
        "wire_prepared_monotonic_ns",
        "dispatch_started_monotonic_ns",
        "dispatch_outcome_monotonic_ns",
        "send_not_after_monotonic_ns",
        "bytes_submitted_to_tls",
    }
    timestamp_fields = {
        "wire_prepared_at",
        "dispatch_started_at",
        "dispatch_outcome_at",
        "send_not_after",
    }
    result: dict[str, Any] = {}
    for name in OutboundControlDispatchResultV4.__dataclass_fields__:
        if name == "signature_hex":
            continue
        if name not in values:
            raise CanonicalizationError(f"signed control dispatch is missing {name}")
        value = values[name]
        if name in hash_fields:
            result[name] = canonical_hash(value, field=name)
        elif name == "bytes_submitted_to_tls":
            result[name] = (
                None
                if value is None
                else canonical_safe_int(value, field=name, minimum=0)
            )
        elif name in integer_fields:
            result[name] = canonical_safe_int(value, field=name, minimum=0)
        elif name in timestamp_fields:
            result[name] = utc_iso(value, field=name)
        elif name == "control_kind":
            result[name] = _enum(value, OutboundControlKindV4, field=name).value
        elif name == "disposition":
            result[name] = _enum(
                value, OutboundControlDispatchDispositionV4, field=name
            ).value
        elif name == "permit_consumed":
            result[name] = _strict_bool(value, field=name)
        elif name == "error_class_digest":
            result[name] = _optional_hash(value, field=name)
        elif name == "collector_attestation_public_key_hex":
            result[name] = _public_key_bytes(value, field=name).hex()
        else:
            result[name] = canonical_identifier(value, field=name)
    return result


__all__ = [
    "PHYSICAL_TRANSPORT_CONTROL_V4_SCHEMA_VERSION",
    "V4_CONTROL_PROTOCOL_ERROR_CLOSE_CODE",
    "V4_INCORRECT_MASKING_CLOSE_PAYLOAD",
    "V4_INCORRECT_MASKING_PARSER_EXCEPTION_CLASS_DIGEST",
    "V4_INCORRECT_MASKING_PARSER_EXCEPTION_MESSAGE_DIGEST",
    "InboundRfcControlOpcodeV4",
    "InboundRfcControlTriggerV4",
    "InboundWebSocketProtocolFailureKindV4",
    "InboundWebSocketProtocolFailureV4",
    "OutboundControlDispatchDispositionV4",
    "OutboundControlDispatchResultV4",
    "OutboundControlIntentV4",
    "OutboundControlKindV4",
    "OutboundControlWritePermitConsumedV4",
    "OutboundControlWirePreparedV4",
    "OutboundWebSocketOpcodeV4",
    "RawIngressCommitV4",
    "build_bybit_json_heartbeat_intent_v4",
]

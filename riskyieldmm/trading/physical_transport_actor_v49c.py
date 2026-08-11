"""Canonical V4.9C transport-actor events and frame delineation primitives.

This module is deliberately a contract-only slice.  It doesn't own a socket,
open a SQLite transaction, call the WebSocket parser, or grant live authority.
It provides two small building blocks for the later owner-bound actor:

* one closed, append-only event vocabulary for raw receipt, parser, output,
  TLS, kernel-send, dispatch, and terminal observations; and
* a pure RFC 6455 frame-boundary delineator which preserves exact provenance
  when one unmasked server frame crosses several durable raw-ingress commits.

The delineator identifies frame boundaries only.  Protocol state, fragmented
message validity, UTF-8, Close payload semantics, and automatic responses must
still be decided by the pinned ``websockets==16.0`` Sans-I/O parser.  A fresh
actor must never treat these structural contracts as proof that a network or
projection side effect occurred.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Final, TypeAlias

from .canonical import (
    CANONICALIZATION_VERSION,
    CanonicalizationError,
    canonical_hash,
    canonical_identifier,
    canonical_safe_int,
    require_exact_keys,
    sha256_digest,
    utc_datetime,
    utc_iso,
)
from .physical_market_data import MessageDispositionKind
from .physical_transport_terminal_v49c import (
    V49E_LOCAL_SHUTDOWN_CLOCK_DISAGREEMENT_CAUSE,
    V49E_LOCAL_SHUTDOWN_COMMAND_DEADLINE_EXPIRED_CAUSE,
    V49E_TCP_HALF_CLOSE_DEADLINE_EXPIRED_BEFORE_SYSCALL_CAUSE,
    V49E_TCP_HALF_CLOSE_ERROR_CAUSE,
    V49E_TCP_HALF_CLOSE_OUTCOME_UNKNOWN_CAUSE,
    V49E_TERMINAL_CLOSE_INGRESS_DEADLINE_EXPIRED_AFTER_PROGRESS_CAUSE,
    V49E_TLS_CONTROL_SEND_OUTCOME_UNKNOWN_CAUSE,
    V49E_TLS_OPERATION_DRIVER_ERROR_CAUSE,
    V49E_TLS_POST_HANDSHAKE_OUTPUT_AFTER_SHUT_WR_CAUSE,
    V49E_TLS_SHUTDOWN_DEADLINE_EXPIRED_AFTER_PROGRESS_CAUSE,
    V49E_TLS_SHUTDOWN_DEADLINE_EXPIRED_CAUSE,
    OutboundObligationLayerV49C,
    PhysicalTransportTerminalV49CError,
    TerminalStateV49C,
    TerminalTransitionKindV49C,
    TerminalTransitionPayloadV49C,
    advance_terminal_state_v49c,
    initial_terminal_state_v49c,
)

PHYSICAL_TRANSPORT_ACTOR_V49C_SCHEMA_VERSION: Final = (
    "riskyieldmm_physical_transport_actor_v4_9c"
)
V49C_MAX_RAW_CHUNKS: Final = 128
V49C_MAX_RAW_COMMIT_OCTETS: Final = 65_536
V49C_MAX_FRAME_PAYLOAD_OCTETS: Final = 1_048_576
V49C_MAX_FRAME_SOURCE_SLICES: Final = 64
V49C_MAX_PROTOCOL_OUTPUT_CHUNKS: Final = 32
V49C_MAX_PROTOCOL_OUTPUT_OCTETS: Final = 65_536
V49C_MAX_TLS_CIPHERTEXT_CHUNKS: Final = 256
V49C_MAX_TLS_CIPHERTEXT_OCTETS: Final = 4 * 1_048_576
V49E_MAX_APPLICATION_MESSAGE_FRAMES: Final = 4096
V49E_MAX_LOCAL_SHUTDOWN_TIMEOUT_SECONDS: Final = 300
V49E_WEBSOCKET_CLOSE_DEADLINE_EXPIRED_CAUSE: Final = "WEBSOCKET_CLOSE_DEADLINE_EXPIRED"

_EVENT_TOKEN: Final = object()
_COMMITTED_RAW_INGRESS_TOKEN: Final = object()
_EVENT_ID_DOMAIN: Final = "RiskYieldMMTransportActorEventV4_9C"
_CURSOR_ID_DOMAIN: Final = "RiskYieldMMWebSocketParserCursorV4_9C"
_ORDERED_OUTPUT_DOMAIN: Final = "RiskYieldMMActorOrderedProtocolOutputV4_9C"
_ORDERED_CIPHERTEXT_DOMAIN: Final = "RiskYieldMMActorOrderedTlsCiphertextV4_9C"
_ORDERED_TLS_CONTROL_CIPHERTEXT_DOMAIN: Final = (
    "RiskYieldMMActorOrderedTlsControlCiphertextV4_9E"
)
_WRITE_PERMIT_ID_DOMAIN: Final = "RiskYieldMMActorWritePermitV4_9C"
_LOCAL_TERMINAL_COMMAND_ID_DOMAIN: Final = (
    "RiskYieldMMLocalTerminalCommandOperationV4_9E"
)
_LOCAL_SHUTDOWN_COMMAND_ID_DOMAIN: Final = "RiskYieldMMLocalShutdownCommandStartedV4_9E"
_LOCAL_NORMAL_CLOSE_PAYLOAD_V49E: Final = (1000).to_bytes(2, "big")
_LOCAL_NORMAL_CLOSE_REASON_V49E: Final = b""
_LOCAL_NORMAL_CLOSE_REASON_SHA256_V49E: Final = hashlib.sha256(
    _LOCAL_NORMAL_CLOSE_REASON_V49E
).hexdigest()
_LOCAL_NORMAL_CLOSE_PAYLOAD_SHA256_V49E: Final = hashlib.sha256(
    _LOCAL_NORMAL_CLOSE_PAYLOAD_V49E
).hexdigest()
_RAW_RECORD_KIND: Final = "RAW_INGRESS_COMMIT_V4"
# V4.9E is a Linux-owner profile.  The owner hashes ``socket.SHUT_WR`` as its
# Linux ABI integer (1), while the actor payload deliberately exposes the
# portable semantic spelling ``SHUT_WR``.
_V49E_LINUX_SHUT_WR_ABI_VALUE: Final = 1
_V49E_LINUX_SHUT_WR_ERROR_CODES: Final = frozenset(
    {
        "DEADLINE_EXPIRED_BEFORE_SYSCALL",
        "EBADF",
        "EINVAL",
        "ENOTCONN",
        "ENOTSOCK",
    }
)
_V49E_LOCAL_SHUTDOWN_NO_OBSERVATION_OPERATIONS: Final = frozenset(
    {
        "LOCAL_WEBSOCKET_CLOSE_PREPARATION",
        "LOCAL_WEBSOCKET_CLOSE_TLS_PREPARATION",
        "TERMINAL_CLOSE_INGRESS",
        "TCP_WRITE_SHUTDOWN_TOKEN_PREPARATION",
    }
)


class TransportActorEventKindV49C(str, Enum):
    RAW_INGRESS_COMMITTED = "RAW_INGRESS_COMMITTED"
    PARSER_TRANSITION = "PARSER_TRANSITION"
    OUTBOUND_WIRE_PREPARED = "OUTBOUND_WIRE_PREPARED"
    WRITE_PERMIT_CONSUMED = "WRITE_PERMIT_CONSUMED"
    TLS_CIPHERTEXT_PREPARED = "TLS_CIPHERTEXT_PREPARED"
    KERNEL_SEND_ATTEMPT = "KERNEL_SEND_ATTEMPT"
    KERNEL_SEND_RESULT = "KERNEL_SEND_RESULT"
    KERNEL_SEND_FAILURE = "KERNEL_SEND_FAILURE"
    OUTBOUND_DISPATCH_COMPLETED = "OUTBOUND_DISPATCH_COMPLETED"
    APPLICATION_MESSAGE_COMMITTED = "APPLICATION_MESSAGE_COMMITTED"
    SUBSCRIPTION_ACK_BOUND = "SUBSCRIPTION_ACK_BOUND"
    ACK_DEADLINE_EXPIRED = "ACK_DEADLINE_EXPIRED"
    LOCAL_SHUTDOWN_COMMAND_STARTED = "LOCAL_SHUTDOWN_COMMAND_STARTED"
    LOCAL_SHUTDOWN_DEADLINE_EVIDENCE = "LOCAL_SHUTDOWN_DEADLINE_EVIDENCE"
    TERMINAL_INGRESS_FAILURE = "TERMINAL_INGRESS_FAILURE"
    TLS_PROTOCOL_OPERATION_STARTED = "TLS_PROTOCOL_OPERATION_STARTED"
    TLS_PROTOCOL_OPERATION_FAILED = "TLS_PROTOCOL_OPERATION_FAILED"
    TLS_CONTROL_CIPHERTEXT_PREPARED = "TLS_CONTROL_CIPHERTEXT_PREPARED"
    TLS_CONTROL_KERNEL_SEND_ATTEMPT = "TLS_CONTROL_KERNEL_SEND_ATTEMPT"
    TLS_CONTROL_KERNEL_SEND_RESULT = "TLS_CONTROL_KERNEL_SEND_RESULT"
    TLS_CONTROL_KERNEL_SEND_FAILURE = "TLS_CONTROL_KERNEL_SEND_FAILURE"
    TLS_SHUTDOWN_OBSERVED = "TLS_SHUTDOWN_OBSERVED"
    TCP_HALF_CLOSE_ATTEMPT = "TCP_HALF_CLOSE_ATTEMPT"
    TCP_HALF_CLOSE_RESULT = "TCP_HALF_CLOSE_RESULT"
    TERMINAL_TRANSITION = "TERMINAL_TRANSITION"


class ParserFeedUnitKindV49C(str, Enum):
    COMPLETE_FRAME = "COMPLETE_FRAME"
    PARSER_ERROR = "PARSER_ERROR"


class WebSocketParserStateV49C(str, Enum):
    OPEN = "OPEN"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"
    FAILED = "FAILED"


class WebSocketOpcodeV49C(str, Enum):
    CONTINUATION = "CONTINUATION"
    TEXT = "TEXT"
    BINARY = "BINARY"
    CLOSE = "CLOSE"
    PING = "PING"
    PONG = "PONG"


class ParserErrorKindV49C(str, Enum):
    INCORRECT_MASKING = "INCORRECT_MASKING"
    RESERVED_BITS = "RESERVED_BITS"
    INVALID_OPCODE = "INVALID_OPCODE"
    NON_MINIMAL_LENGTH = "NON_MINIMAL_LENGTH"
    INVALID_64BIT_LENGTH = "INVALID_64BIT_LENGTH"
    FRAGMENTED_CONTROL = "FRAGMENTED_CONTROL"
    CONTROL_TOO_LARGE = "CONTROL_TOO_LARGE"
    FRAME_TOO_LARGE = "FRAME_TOO_LARGE"
    PROTOCOL_STATE = "PROTOCOL_STATE"
    INVALID_TEXT = "INVALID_TEXT"
    INVALID_CLOSE = "INVALID_CLOSE"
    TRUNCATED_TERMINAL = "TRUNCATED_TERMINAL"
    INTERNAL_PARSER_ERROR = "INTERNAL_PARSER_ERROR"


class OutboundWireOriginV49C(str, Enum):
    AUTOMATIC_PROTOCOL = "AUTOMATIC_PROTOCOL"
    APPLICATION_INTENT = "APPLICATION_INTENT"
    LOCAL_TERMINAL_COMMAND = "LOCAL_TERMINAL_COMMAND"


class OutboundDispatchDispositionV49C(str, Enum):
    COMPLETE_LOCAL_SUBMISSION = "COMPLETE_LOCAL_SUBMISSION"
    UNKNOWN_DELIVERY = "UNKNOWN_DELIVERY"


class TlsProtocolOperationPurposeV49E(str, Enum):
    """Exact purpose of one write-ahead retained-driver operation."""

    LOCAL_CLOSE_NOTIFY = "LOCAL_CLOSE_NOTIFY"
    OPAQUE_POST_HANDSHAKE_RESPONSE = "OPAQUE_POST_HANDSHAKE_RESPONSE"
    PEER_SHUTDOWN_POLL = "PEER_SHUTDOWN_POLL"


class TlsControlOutputKindV49E(str, Enum):
    """Honest semantic claim for retained TLS-control output."""

    LOCAL_CLOSE_NOTIFY = "LOCAL_CLOSE_NOTIFY"
    OPAQUE_POST_HANDSHAKE_RESPONSE = "OPAQUE_POST_HANDSHAKE_RESPONSE"


class TlsProtocolOperationFailureKindV49E(str, Enum):
    """Exact physical negative results for one retained TLS operation."""

    DRIVER_ERROR = "DRIVER_ERROR"
    DEADLINE_EXPIRED_NO_OBSERVATION = "DEADLINE_EXPIRED_NO_OBSERVATION"
    DEADLINE_EXPIRED_AFTER_PROGRESS = "DEADLINE_EXPIRED_AFTER_PROGRESS"
    UNSENDABLE_POST_HANDSHAKE_OUTPUT_AFTER_SHUT_WR = (
        "UNSENDABLE_POST_HANDSHAKE_OUTPUT_AFTER_SHUT_WR"
    )


class TlsShutdownObservationKindV49E(str, Enum):
    """Keep authenticated TLS closure distinct from raw transport EOF."""

    PEER_CLOSE_NOTIFY = "PEER_CLOSE_NOTIFY"
    TCP_EOF = "TCP_EOF"


class TerminalIngressFailureKindV49E(str, Enum):
    DEADLINE_EXPIRED_AFTER_PROGRESS = "DEADLINE_EXPIRED_AFTER_PROGRESS"
    CLOCK_DISAGREEMENT = "CLOCK_DISAGREEMENT"


class LocalShutdownDeadlineClassificationV49E(str, Enum):
    """Actor classification of one consumed owner no-observation capability."""

    BOTH_DUE = "BOTH_DUE"
    CLOCK_DISAGREEMENT = "CLOCK_DISAGREEMENT"
    OWNER_EVIDENCE_BEFORE_BOTH_CLOCKS = "OWNER_EVIDENCE_BEFORE_BOTH_CLOCKS"


class TcpHalfCloseResultKindV49E(str, Enum):
    """Closed result vocabulary for the one-shot ``shutdown(SHUT_WR)``."""

    KERNEL_ACCEPTED = "KERNEL_ACCEPTED"
    DEADLINE_EXPIRED_BEFORE_SYSCALL = "DEADLINE_EXPIRED_BEFORE_SYSCALL"
    CLOCK_DISAGREEMENT = "CLOCK_DISAGREEMENT"
    ERROR = "ERROR"


class KernelSendFailureKindV49E(str, Enum):
    """Conclusive deadline outcomes which prove zero kernel acceptance."""

    DEADLINE_EXPIRED_BEFORE_CALLBACK = "DEADLINE_EXPIRED_BEFORE_CALLBACK"
    DEADLINE_EXPIRED_BEFORE_SYSCALL = "DEADLINE_EXPIRED_BEFORE_SYSCALL"
    CLOCK_DISAGREEMENT = "CLOCK_DISAGREEMENT"
    DEADLINE_EXPIRED_NO_KERNEL_ACCEPTANCE = "DEADLINE_EXPIRED_NO_KERNEL_ACCEPTANCE"


def derive_actor_write_permit_id_v49c(
    *,
    outbound_operation_id: str,
    outbound_wire_prepared_event_id: str,
    socket_lease_id: str,
    writer_fence_token_sha256: str,
    writer_fence_generation: int,
) -> str:
    """Derive the sole durable permit identity from actor-owned authority."""

    return sha256_digest(
        {
            "domain": _WRITE_PERMIT_ID_DOMAIN,
            "outbound_operation_id": canonical_hash(
                outbound_operation_id, field="outbound_operation_id"
            ),
            "outbound_wire_prepared_event_id": canonical_hash(
                outbound_wire_prepared_event_id,
                field="outbound_wire_prepared_event_id",
            ),
            "socket_lease_id": canonical_hash(socket_lease_id, field="socket_lease_id"),
            "writer_fence_generation": canonical_safe_int(
                writer_fence_generation,
                field="writer_fence_generation",
                minimum=1,
            ),
            "writer_fence_token_sha256": canonical_hash(
                writer_fence_token_sha256,
                field="writer_fence_token_sha256",
            ),
        }
    )


def derive_local_shutdown_command_id_v49e(
    *,
    transport_session_id: str,
    actor_predecessor_event_id: str | None,
    timeout_seconds: int,
    started_at: datetime,
    started_monotonic_ns: int,
    deadline_at: datetime,
    deadline_monotonic_ns: int,
) -> str:
    """Bind one local shutdown horizon before any owner mutation.

    The fixed WebSocket Close commitment is part of the identity even when a
    peer-first Close means no local WebSocket wire is required.  Both clocks
    describe the same bounded duration; BOOTTIME remains the authoritative
    expiry clock while wall time is retained for auditability.
    """

    timeout = canonical_safe_int(
        timeout_seconds,
        field="timeout_seconds",
        minimum=1,
        maximum=V49E_MAX_LOCAL_SHUTDOWN_TIMEOUT_SECONDS,
    )
    started = utc_datetime(started_at, field="started_at")
    deadline = utc_datetime(deadline_at, field="deadline_at")
    started_ns = canonical_safe_int(
        started_monotonic_ns,
        field="started_monotonic_ns",
        minimum=0,
    )
    deadline_ns = canonical_safe_int(
        deadline_monotonic_ns,
        field="deadline_monotonic_ns",
        minimum=1,
    )
    if (
        deadline != started + timedelta(seconds=timeout)
        or deadline_ns != started_ns + timeout * 1_000_000_000
    ):
        raise CanonicalizationError(
            "local shutdown wall and BOOTTIME deadlines must share one duration"
        )
    return sha256_digest(
        {
            "actor_predecessor_event_id": _optional_hash(
                actor_predecessor_event_id,
                field="actor_predecessor_event_id",
            ),
            "deadline_at": utc_iso(deadline),
            "deadline_monotonic_ns": deadline_ns,
            "domain": _LOCAL_SHUTDOWN_COMMAND_ID_DOMAIN,
            "started_at": utc_iso(started),
            "started_monotonic_ns": started_ns,
            "timeout_seconds": timeout,
            "transport_session_id": canonical_hash(
                transport_session_id,
                field="transport_session_id",
            ),
            "websocket_close_code": 1000,
            "websocket_close_payload_octets": len(_LOCAL_NORMAL_CLOSE_PAYLOAD_V49E),
            "websocket_close_payload_sha256": (_LOCAL_NORMAL_CLOSE_PAYLOAD_SHA256_V49E),
            "websocket_close_reason_octets": len(_LOCAL_NORMAL_CLOSE_REASON_V49E),
            "websocket_close_reason_sha256": (_LOCAL_NORMAL_CLOSE_REASON_SHA256_V49E),
        }
    )


def _derive_driver_send_deadline_evidence_id_v49e(
    *,
    driver_evidence_nonce_sha256: str,
    send_kind: str,
    transport_sequence: int,
    ciphertext_batch_sha256: str,
    ciphertext_octets: int,
    ciphertext_start_octet: int,
    requested_octets: int,
    exact_slice_sha256: str,
    deadline_ns: int,
    would_block_count: int,
) -> str:
    return sha256_digest(
        {
            "domain": "RiskYieldMMTlsSendDeadlineNoKernelAcceptanceV4_9E",
            "driver_evidence_nonce_sha256": driver_evidence_nonce_sha256,
            "send_kind": send_kind,
            "transport_sequence": transport_sequence,
            "ciphertext_batch_sha256": ciphertext_batch_sha256,
            "ciphertext_octets": ciphertext_octets,
            "ciphertext_start_octet": ciphertext_start_octet,
            "requested_octets": requested_octets,
            "exact_slice_sha256": exact_slice_sha256,
            "deadline_ns": deadline_ns,
            "would_block_count": would_block_count,
        }
    )


def _derive_owner_send_deadline_evidence_id_v49e(
    *,
    transport_session_id: str,
    kernel_socket_identity: str,
    driver_evidence_nonce_sha256: str,
    send_kind: str,
    transport_sequence: int,
    ciphertext_batch_sha256: str,
    ciphertext_octets: int,
    ciphertext_start_octet: int,
    requested_octets: int,
    exact_slice_sha256: str,
    deadline_ns: int,
    would_block_count: int,
    driver_evidence_id: str,
) -> str:
    return sha256_digest(
        {
            "domain": "RiskYieldMMOwnerTlsSendDeadlineNoKernelAcceptanceV4_9E",
            "transport_session_id": transport_session_id,
            "kernel_socket_identity": kernel_socket_identity,
            "driver_evidence_nonce_sha256": driver_evidence_nonce_sha256,
            "send_kind": send_kind,
            "transport_sequence": transport_sequence,
            "ciphertext_batch_sha256": ciphertext_batch_sha256,
            "ciphertext_octets": ciphertext_octets,
            "ciphertext_start_octet": ciphertext_start_octet,
            "requested_octets": requested_octets,
            "exact_slice_sha256": exact_slice_sha256,
            "deadline_ns": deadline_ns,
            "would_block_count": would_block_count,
            "driver_evidence_id": driver_evidence_id,
        }
    )


def _derive_owner_deadline_no_observation_evidence_id_v49e(
    *,
    transport_session_id: str,
    kernel_socket_identity: str,
    driver_evidence_nonce_sha256: str,
    operation: str,
    deadline_ns: int,
) -> str:
    return sha256_digest(
        {
            "domain": "RiskYieldMMOwnerDeadlineExpiredNoObservationV4_9E",
            "transport_session_id": transport_session_id,
            "kernel_socket_identity": kernel_socket_identity,
            "driver_evidence_nonce_sha256": driver_evidence_nonce_sha256,
            "operation": operation,
            "deadline_ns": deadline_ns,
        }
    )


def _derive_driver_deadline_after_progress_evidence_id_v49e(
    *,
    driver_evidence_nonce_sha256: str,
    operation: str,
    deadline_ns: int,
    ciphertext_octets_received: int,
    ciphertext_sha256: str,
) -> str:
    return sha256_digest(
        {
            "domain": "RiskYieldMMDeadlineExpiredAfterProgressV4_9E",
            "driver_evidence_nonce_sha256": driver_evidence_nonce_sha256,
            "operation": operation,
            "deadline_ns": deadline_ns,
            "ciphertext_octets_received": ciphertext_octets_received,
            "ciphertext_sha256": ciphertext_sha256,
        }
    )


def _derive_owner_deadline_after_progress_evidence_id_v49e(
    *,
    transport_session_id: str,
    kernel_socket_identity: str,
    driver_evidence_nonce_sha256: str,
    operation: str,
    deadline_ns: int,
    ciphertext_octets_received: int,
    ciphertext_sha256: str,
    driver_evidence_id: str,
) -> str:
    return sha256_digest(
        {
            "domain": "RiskYieldMMOwnerDeadlineExpiredAfterProgressV4_9E",
            "transport_session_id": transport_session_id,
            "kernel_socket_identity": kernel_socket_identity,
            "driver_evidence_nonce_sha256": driver_evidence_nonce_sha256,
            "operation": operation,
            "deadline_ns": deadline_ns,
            "ciphertext_octets_received": ciphertext_octets_received,
            "ciphertext_sha256": ciphertext_sha256,
            "driver_evidence_id": driver_evidence_id,
        }
    )


def derive_local_terminal_command_operation_id_v49e(
    *,
    transport_session_id: str,
    actor_predecessor_event_id: str | None,
    logical_payload_sha256: str,
    logical_payload_octets: int,
    ordered_wire_chunks_sha256: Sequence[str],
    wire_batch_sha256: str,
    wire_octets: int,
) -> str:
    """Derive the fixed local-Close identity from durable actor commitments.

    The retained WebSocket driver's outbound sequence is intentionally absent:
    it isn't persisted in the actor journal and therefore cannot be verified by
    replay.  The actor predecessor and every exact wire commitment used here
    are durable in the enclosing prepared-wire event.
    """

    payload_sha256 = canonical_hash(
        logical_payload_sha256, field="logical_payload_sha256"
    )
    payload_octets = canonical_safe_int(
        logical_payload_octets,
        field="logical_payload_octets",
        minimum=0,
        maximum=V49C_MAX_FRAME_PAYLOAD_OCTETS,
    )
    chunk_hashes = _hashes(
        ordered_wire_chunks_sha256,
        field="ordered_wire_chunks_sha256",
        allow_empty=False,
        maximum=V49C_MAX_PROTOCOL_OUTPUT_CHUNKS,
    )
    return sha256_digest(
        {
            "actor_predecessor_event_id": _optional_hash(
                actor_predecessor_event_id,
                field="actor_predecessor_event_id",
            ),
            "domain": _LOCAL_TERMINAL_COMMAND_ID_DOMAIN,
            "logical_opcode": WebSocketOpcodeV49C.CLOSE.value,
            "logical_payload_octets": payload_octets,
            "logical_payload_sha256": payload_sha256,
            "ordered_wire_chunks_sha256": list(chunk_hashes),
            "transport_session_id": canonical_hash(
                transport_session_id, field="transport_session_id"
            ),
            "wire_batch_sha256": canonical_hash(
                wire_batch_sha256, field="wire_batch_sha256"
            ),
            "wire_octets": canonical_safe_int(
                wire_octets, field="wire_octets", minimum=1
            ),
        }
    )


def _enum(value: Any, enum_type: type[Enum], *, field: str) -> Enum:
    try:
        return value if isinstance(value, enum_type) else enum_type(value)
    except (TypeError, ValueError) as exc:
        choices = ", ".join(item.value for item in enum_type)
        raise CanonicalizationError(f"{field} must be one of: {choices}") from exc


def _strict_bool(value: Any, *, field: str) -> bool:
    if type(value) is not bool:
        raise CanonicalizationError(f"{field} must be an exact boolean")
    return value


def _optional_hash(value: Any, *, field: str) -> str | None:
    return None if value is None else canonical_hash(value, field=field)


def _hashes(
    values: Sequence[Any],
    *,
    field: str,
    allow_empty: bool,
    maximum: int,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)) or not isinstance(values, Sequence):
        raise CanonicalizationError(f"{field} must be a sequence")
    result = tuple(canonical_hash(value, field=field) for value in values)
    if (not allow_empty and not result) or len(result) > maximum:
        raise CanonicalizationError(f"{field} has an invalid item count")
    return result


def _positive_ints(
    values: Sequence[Any], *, field: str, maximum: int
) -> tuple[int, ...]:
    if isinstance(values, (str, bytes, bytearray)) or not isinstance(values, Sequence):
        raise CanonicalizationError(f"{field} must be a sequence")
    result = tuple(
        canonical_safe_int(value, field=field, minimum=1) for value in values
    )
    if not result or len(result) > maximum:
        raise CanonicalizationError(f"{field} has an invalid item count")
    return result


def _canonical_base64(value: Any, *, field: str, allow_empty: bool = False) -> bytes:
    text = canonical_identifier(value, field=field, maximum=16 * 1_048_576)
    try:
        decoded = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise CanonicalizationError(f"{field} must be canonical base64") from exc
    if base64.b64encode(decoded).decode("ascii") != text:
        raise CanonicalizationError(f"{field} must use canonical padded base64")
    if not allow_empty and not decoded:
        raise CanonicalizationError(f"{field} must not encode empty bytes")
    return decoded


def _base64_chunks(
    values: Sequence[Any],
    *,
    field: str,
    allow_empty: bool,
    maximum_items: int,
    maximum_octets: int,
) -> tuple[tuple[str, ...], tuple[bytes, ...]]:
    if isinstance(values, (str, bytes, bytearray)) or not isinstance(values, Sequence):
        raise CanonicalizationError(f"{field} must be a sequence")
    encoded = tuple(values)
    if len(encoded) > maximum_items or (not allow_empty and not encoded):
        raise CanonicalizationError(f"{field} has an invalid item count")
    decoded = tuple(
        _canonical_base64(value, field=field, allow_empty=False) for value in encoded
    )
    if sum(map(len, decoded)) > maximum_octets:
        raise CanonicalizationError(f"{field} exceeds its octet bound")
    return tuple(str(value) for value in encoded), decoded


def _ordered_batch_sha256(domain: str, chunks_base64: Sequence[str]) -> str:
    return sha256_digest(
        {"domain": domain, "ordered_chunks_base64": list(chunks_base64)}
    )


def _as_payload_mapping(payload: Any) -> dict[str, Any]:
    as_dict = getattr(payload, "as_dict", None)
    if not callable(as_dict):
        raise CanonicalizationError("actor payload must provide as_dict()")
    result = as_dict()
    if not isinstance(result, dict):
        raise CanonicalizationError("actor payload as_dict() must return a mapping")
    return result


@dataclass(frozen=True, slots=True, kw_only=True, init=False)
class CommittedRawIngressV49C:
    """Store-returned proof that one raw-ingress record is durably committed.

    Direct construction is deliberately unavailable.  Live code must convert
    the exact receipt returned by ``PhysicalProjectionStoreV4``; canonical
    replay may reconstruct the serialized proof with :meth:`from_mapping` but
    that reconstruction is data, not renewed live-write authority.
    """

    ledger_id: str
    global_sequence: int
    receipt_hash: str
    previous_receipt_hash: str
    record_kind: str
    identity_id: str
    content_hash: str
    committed_at: datetime
    _store_minted: bool = field(repr=False, compare=False)

    def __init__(
        self, *, _token: object, _store_minted: bool = False, **values: Any
    ) -> None:
        if _token is not _COMMITTED_RAW_INGRESS_TOKEN:
            raise TypeError("committed raw ingress is projection-constructed only")
        for name in self.__dataclass_fields__:
            if name != "_store_minted":
                object.__setattr__(self, name, values[name])
        object.__setattr__(
            self, "_store_minted", _strict_bool(_store_minted, field="_store_minted")
        )
        self._validate()

    def _validate(self) -> None:
        for name in (
            "ledger_id",
            "receipt_hash",
            "previous_receipt_hash",
            "identity_id",
            "content_hash",
        ):
            object.__setattr__(
                self, name, canonical_hash(getattr(self, name), field=name)
            )
        object.__setattr__(
            self,
            "global_sequence",
            canonical_safe_int(
                self.global_sequence, field="global_sequence", minimum=1
            ),
        )
        record_kind = canonical_identifier(
            self.record_kind, field="record_kind", maximum=128
        )
        if record_kind != _RAW_RECORD_KIND:
            raise CanonicalizationError(
                "raw receipt proof must identify RAW_INGRESS_COMMIT_V4"
            )
        object.__setattr__(self, "record_kind", record_kind)
        expected_receipt_hash = sha256_digest(
            {
                "content_hash": self.content_hash,
                "domain": "RiskYieldMMPhysicalProjectionReceiptV4",
                "global_sequence": self.global_sequence,
                "identity_id": self.identity_id,
                "ledger_id": self.ledger_id,
                "previous_receipt_hash": self.previous_receipt_hash,
                "record_kind": self.record_kind,
            }
        )
        if self.receipt_hash != expected_receipt_hash:
            raise CanonicalizationError(
                "raw projection receipt hash differs from its semantic fields"
            )
        object.__setattr__(
            self,
            "committed_at",
            utc_datetime(self.committed_at, field="committed_at"),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "committed_at": utc_iso(self.committed_at),
            "content_hash": self.content_hash,
            "global_sequence": self.global_sequence,
            "identity_id": self.identity_id,
            "ledger_id": self.ledger_id,
            "previous_receipt_hash": self.previous_receipt_hash,
            "receipt_hash": self.receipt_hash,
            "record_kind": self.record_kind,
        }

    @property
    def is_store_minted(self) -> bool:
        """Whether this in-memory proof came directly from a store receipt."""

        return self._store_minted

    @classmethod
    def from_projection_receipt(
        cls, *, ledger_id: str, receipt: Any
    ) -> CommittedRawIngressV49C:
        """Mint live ingress authority from an exact projection-store receipt."""

        # Local import avoids a projection -> actor -> projection import cycle
        # when the store integrates this hand-off.
        from .physical_projection_v4 import PhysicalProjectionReceiptV4

        if type(receipt) is not PhysicalProjectionReceiptV4:
            raise TypeError("receipt must be exact PhysicalProjectionReceiptV4")
        return cls(
            _token=_COMMITTED_RAW_INGRESS_TOKEN,
            _store_minted=True,
            ledger_id=ledger_id,
            global_sequence=receipt.global_sequence,
            receipt_hash=receipt.receipt_hash,
            previous_receipt_hash=receipt.previous_receipt_hash,
            record_kind=receipt.record_kind.value,
            identity_id=receipt.identity_id,
            content_hash=receipt.content_hash,
            committed_at=receipt.committed_at,
        )

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> CommittedRawIngressV49C:
        require_exact_keys(
            payload,
            expected={
                "committed_at",
                "content_hash",
                "global_sequence",
                "identity_id",
                "ledger_id",
                "previous_receipt_hash",
                "receipt_hash",
                "record_kind",
            },
            context=cls.__name__,
        )
        return cls(
            _token=_COMMITTED_RAW_INGRESS_TOKEN,
            _store_minted=False,
            **dict(payload),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class RawIngressCommittedPayloadV49C:
    raw_ingress_commit_id: str
    receipt: CommittedRawIngressV49C
    ingress_sequence: int
    previous_raw_ingress_commit_id: str | None
    stream_start_octet: int
    stream_end_octet: int
    ordered_chunk_octet_lengths: tuple[int, ...]
    ordered_chunk_sha256: tuple[str, ...]
    raw_ingress_batch_sha256: str
    received_at: datetime
    received_monotonic_ns: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "raw_ingress_commit_id",
            canonical_hash(self.raw_ingress_commit_id, field="raw_ingress_commit_id"),
        )
        if type(self.receipt) is not CommittedRawIngressV49C:
            raise CanonicalizationError(
                "receipt must be an exact CommittedRawIngressV49C"
            )
        if self.receipt.identity_id != self.raw_ingress_commit_id:
            raise CanonicalizationError(
                "raw receipt identity differs from raw_ingress_commit_id"
            )
        sequence = canonical_safe_int(
            self.ingress_sequence, field="ingress_sequence", minimum=1
        )
        previous = _optional_hash(
            self.previous_raw_ingress_commit_id,
            field="previous_raw_ingress_commit_id",
        )
        if (sequence == 1) != (previous is None):
            raise CanonicalizationError(
                "ingress genesis and previous raw identity are inconsistent"
            )
        start = canonical_safe_int(
            self.stream_start_octet, field="stream_start_octet", minimum=0
        )
        end = canonical_safe_int(
            self.stream_end_octet, field="stream_end_octet", minimum=1
        )
        if end <= start:
            raise CanonicalizationError("raw stream interval must be non-empty")
        lengths = _positive_ints(
            self.ordered_chunk_octet_lengths,
            field="ordered_chunk_octet_lengths",
            maximum=V49C_MAX_RAW_CHUNKS,
        )
        hashes = _hashes(
            self.ordered_chunk_sha256,
            field="ordered_chunk_sha256",
            allow_empty=False,
            maximum=V49C_MAX_RAW_CHUNKS,
        )
        if len(lengths) != len(hashes):
            raise CanonicalizationError("raw chunk lengths and hashes differ in count")
        total = sum(lengths)
        if total != end - start or total > V49C_MAX_RAW_COMMIT_OCTETS:
            raise CanonicalizationError(
                "raw chunk lengths differ from the bounded stream interval"
            )
        object.__setattr__(
            self,
            "raw_ingress_batch_sha256",
            canonical_hash(
                self.raw_ingress_batch_sha256, field="raw_ingress_batch_sha256"
            ),
        )
        object.__setattr__(self, "ingress_sequence", sequence)
        object.__setattr__(self, "previous_raw_ingress_commit_id", previous)
        object.__setattr__(self, "stream_start_octet", start)
        object.__setattr__(self, "stream_end_octet", end)
        object.__setattr__(self, "ordered_chunk_octet_lengths", lengths)
        object.__setattr__(self, "ordered_chunk_sha256", hashes)
        object.__setattr__(
            self,
            "received_at",
            utc_datetime(self.received_at, field="received_at"),
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

    def as_dict(self) -> dict[str, Any]:
        return {
            "ingress_sequence": self.ingress_sequence,
            "ordered_chunk_octet_lengths": list(self.ordered_chunk_octet_lengths),
            "ordered_chunk_sha256": list(self.ordered_chunk_sha256),
            "previous_raw_ingress_commit_id": self.previous_raw_ingress_commit_id,
            "raw_ingress_batch_sha256": self.raw_ingress_batch_sha256,
            "raw_ingress_commit_id": self.raw_ingress_commit_id,
            "receipt": self.receipt.as_dict(),
            "received_at": utc_iso(self.received_at),
            "received_monotonic_ns": self.received_monotonic_ns,
            "stream_end_octet": self.stream_end_octet,
            "stream_start_octet": self.stream_start_octet,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> RawIngressCommittedPayloadV49C:
        expected = {
            "ingress_sequence",
            "ordered_chunk_octet_lengths",
            "ordered_chunk_sha256",
            "previous_raw_ingress_commit_id",
            "raw_ingress_batch_sha256",
            "raw_ingress_commit_id",
            "receipt",
            "received_at",
            "received_monotonic_ns",
            "stream_end_octet",
            "stream_start_octet",
        }
        require_exact_keys(payload, expected=expected, context=cls.__name__)
        receipt = payload["receipt"]
        if not isinstance(receipt, Mapping):
            raise CanonicalizationError("receipt must be a mapping")
        return cls(
            **{
                name: payload[name]
                for name in expected
                if name
                not in {
                    "receipt",
                    "ordered_chunk_octet_lengths",
                    "ordered_chunk_sha256",
                }
            },
            receipt=CommittedRawIngressV49C.from_mapping(receipt),
            ordered_chunk_octet_lengths=tuple(payload["ordered_chunk_octet_lengths"]),
            ordered_chunk_sha256=tuple(payload["ordered_chunk_sha256"]),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class RawSourceSliceV49C:
    raw_ingress_commit_id: str
    projection_receipt_sequence: int
    projection_receipt_hash: str
    stream_start_octet: int
    stream_end_octet: int
    raw_local_start_octet: int
    raw_local_end_octet: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "raw_ingress_commit_id",
            canonical_hash(self.raw_ingress_commit_id, field="raw_ingress_commit_id"),
        )
        object.__setattr__(
            self,
            "projection_receipt_hash",
            canonical_hash(
                self.projection_receipt_hash, field="projection_receipt_hash"
            ),
        )
        object.__setattr__(
            self,
            "projection_receipt_sequence",
            canonical_safe_int(
                self.projection_receipt_sequence,
                field="projection_receipt_sequence",
                minimum=1,
            ),
        )
        start = canonical_safe_int(
            self.stream_start_octet, field="stream_start_octet", minimum=0
        )
        end = canonical_safe_int(
            self.stream_end_octet, field="stream_end_octet", minimum=1
        )
        local_start = canonical_safe_int(
            self.raw_local_start_octet,
            field="raw_local_start_octet",
            minimum=0,
        )
        local_end = canonical_safe_int(
            self.raw_local_end_octet, field="raw_local_end_octet", minimum=1
        )
        if (
            end <= start
            or local_end <= local_start
            or end - start != local_end - local_start
        ):
            raise CanonicalizationError("source slice intervals are inconsistent")
        object.__setattr__(self, "stream_start_octet", start)
        object.__setattr__(self, "stream_end_octet", end)
        object.__setattr__(self, "raw_local_start_octet", local_start)
        object.__setattr__(self, "raw_local_end_octet", local_end)

    def as_dict(self) -> dict[str, Any]:
        return {
            "projection_receipt_hash": self.projection_receipt_hash,
            "projection_receipt_sequence": self.projection_receipt_sequence,
            "raw_ingress_commit_id": self.raw_ingress_commit_id,
            "raw_local_end_octet": self.raw_local_end_octet,
            "raw_local_start_octet": self.raw_local_start_octet,
            "stream_end_octet": self.stream_end_octet,
            "stream_start_octet": self.stream_start_octet,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> RawSourceSliceV49C:
        require_exact_keys(
            payload,
            expected=set(cls.__dataclass_fields__),
            context=cls.__name__,
        )
        return cls(**dict(payload))


def _validate_contiguous_slices(
    values: Sequence[RawSourceSliceV49C],
) -> tuple[RawSourceSliceV49C, ...]:
    slices = tuple(values)
    if (
        not slices
        or len(slices) > V49C_MAX_FRAME_SOURCE_SLICES
        or any(type(value) is not RawSourceSliceV49C for value in slices)
    ):
        raise CanonicalizationError("source_slices has an invalid item set")
    if any(
        right.stream_start_octet != left.stream_end_octet
        for left, right in zip(slices, slices[1:])
    ):
        raise CanonicalizationError("source_slices are not stream-contiguous")
    return slices


@dataclass(frozen=True, slots=True, kw_only=True)
class WebSocketParserCursorV49C:
    cursor_sequence: int
    next_stream_octet: int
    websocket_state: WebSocketParserStateV49C
    fragmented_message_opcode: WebSocketOpcodeV49C | None = None
    fragmented_message_octets: int = 0
    fragmented_message_sha256: str | None = None

    def __post_init__(self) -> None:
        sequence = canonical_safe_int(
            self.cursor_sequence, field="cursor_sequence", minimum=0
        )
        offset = canonical_safe_int(
            self.next_stream_octet, field="next_stream_octet", minimum=0
        )
        state = _enum(
            self.websocket_state,
            WebSocketParserStateV49C,
            field="websocket_state",
        )
        opcode = (
            None
            if self.fragmented_message_opcode is None
            else _enum(
                self.fragmented_message_opcode,
                WebSocketOpcodeV49C,
                field="fragmented_message_opcode",
            )
        )
        fragment_octets = canonical_safe_int(
            self.fragmented_message_octets,
            field="fragmented_message_octets",
            minimum=0,
        )
        fragment_hash = _optional_hash(
            self.fragmented_message_sha256,
            field="fragmented_message_sha256",
        )
        if opcode is not None and opcode not in {
            WebSocketOpcodeV49C.TEXT,
            WebSocketOpcodeV49C.BINARY,
        }:
            raise CanonicalizationError(
                "fragmented_message_opcode must be TEXT or BINARY"
            )
        if (opcode is None) != (fragment_octets == 0 and fragment_hash is None):
            raise CanonicalizationError(
                "fragmented-message cursor fields must be absent or complete"
            )
        if (
            state in {WebSocketParserStateV49C.CLOSED, WebSocketParserStateV49C.FAILED}
            and opcode is not None
        ):
            raise CanonicalizationError(
                "terminal parser cursor cannot retain a fragmented message"
            )
        object.__setattr__(self, "cursor_sequence", sequence)
        object.__setattr__(self, "next_stream_octet", offset)
        object.__setattr__(self, "websocket_state", state)
        object.__setattr__(self, "fragmented_message_opcode", opcode)
        object.__setattr__(self, "fragmented_message_octets", fragment_octets)
        object.__setattr__(self, "fragmented_message_sha256", fragment_hash)

    def identity_payload(self) -> dict[str, Any]:
        return {
            "cursor_sequence": self.cursor_sequence,
            "fragmented_message_octets": self.fragmented_message_octets,
            "fragmented_message_opcode": (
                None
                if self.fragmented_message_opcode is None
                else self.fragmented_message_opcode.value
            ),
            "fragmented_message_sha256": self.fragmented_message_sha256,
            "next_stream_octet": self.next_stream_octet,
            "websocket_state": self.websocket_state.value,
        }

    @property
    def parser_cursor_id(self) -> str:
        return sha256_digest(
            {"domain": _CURSOR_ID_DOMAIN, "payload": self.identity_payload()}
        )

    def as_dict(self) -> dict[str, Any]:
        return {**self.identity_payload(), "parser_cursor_id": self.parser_cursor_id}

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> WebSocketParserCursorV49C:
        expected = set(cls.__dataclass_fields__) | {"parser_cursor_id"}
        require_exact_keys(payload, expected=expected, context=cls.__name__)
        item = cls(**{name: payload[name] for name in cls.__dataclass_fields__})
        if (
            canonical_hash(payload["parser_cursor_id"], field="parser_cursor_id")
            != item.parser_cursor_id
        ):
            raise CanonicalizationError("parser_cursor_id differs from cursor content")
        return item


_OPCODE_NUMBER_TO_ENUM: Final = {
    0x0: WebSocketOpcodeV49C.CONTINUATION,
    0x1: WebSocketOpcodeV49C.TEXT,
    0x2: WebSocketOpcodeV49C.BINARY,
    0x8: WebSocketOpcodeV49C.CLOSE,
    0x9: WebSocketOpcodeV49C.PING,
    0xA: WebSocketOpcodeV49C.PONG,
}


@dataclass(frozen=True, slots=True, kw_only=True)
class WebSocketFrameMetadataV49C:
    stream_start_octet: int
    stream_end_octet: int
    header_octets: int
    payload_octets: int
    opcode: WebSocketOpcodeV49C
    fin: bool
    masked: bool
    frame_sha256: str
    payload_sha256: str

    def __post_init__(self) -> None:
        start = canonical_safe_int(
            self.stream_start_octet, field="stream_start_octet", minimum=0
        )
        end = canonical_safe_int(
            self.stream_end_octet, field="stream_end_octet", minimum=1
        )
        header = canonical_safe_int(
            self.header_octets, field="header_octets", minimum=2, maximum=14
        )
        payload = canonical_safe_int(
            self.payload_octets,
            field="payload_octets",
            minimum=0,
            maximum=V49C_MAX_FRAME_PAYLOAD_OCTETS,
        )
        if end - start != header + payload:
            raise CanonicalizationError(
                "frame interval differs from header and payload"
            )
        opcode = _enum(self.opcode, WebSocketOpcodeV49C, field="opcode")
        fin = _strict_bool(self.fin, field="fin")
        masked = _strict_bool(self.masked, field="masked")
        if masked:
            raise CanonicalizationError("server frame metadata must be unmasked")
        if opcode in {
            WebSocketOpcodeV49C.CLOSE,
            WebSocketOpcodeV49C.PING,
            WebSocketOpcodeV49C.PONG,
        } and (not fin or payload > 125):
            raise CanonicalizationError("control frame metadata violates RFC 6455")
        object.__setattr__(self, "stream_start_octet", start)
        object.__setattr__(self, "stream_end_octet", end)
        object.__setattr__(self, "header_octets", header)
        object.__setattr__(self, "payload_octets", payload)
        object.__setattr__(self, "opcode", opcode)
        object.__setattr__(self, "fin", fin)
        object.__setattr__(self, "masked", False)
        for name in ("frame_sha256", "payload_sha256"):
            object.__setattr__(
                self, name, canonical_hash(getattr(self, name), field=name)
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "fin": self.fin,
            "frame_sha256": self.frame_sha256,
            "header_octets": self.header_octets,
            "masked": self.masked,
            "opcode": self.opcode.value,
            "payload_octets": self.payload_octets,
            "payload_sha256": self.payload_sha256,
            "stream_end_octet": self.stream_end_octet,
            "stream_start_octet": self.stream_start_octet,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> WebSocketFrameMetadataV49C:
        require_exact_keys(
            payload, expected=set(cls.__dataclass_fields__), context=cls.__name__
        )
        return cls(**dict(payload))


@dataclass(frozen=True, slots=True, kw_only=True)
class ParserErrorMetadataV49C:
    error_kind: ParserErrorKindV49C
    error_stream_offset: int
    exception_class_digest: str
    exception_message_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "error_kind",
            _enum(self.error_kind, ParserErrorKindV49C, field="error_kind"),
        )
        object.__setattr__(
            self,
            "error_stream_offset",
            canonical_safe_int(
                self.error_stream_offset,
                field="error_stream_offset",
                minimum=0,
            ),
        )
        for name in ("exception_class_digest", "exception_message_digest"):
            object.__setattr__(
                self, name, canonical_hash(getattr(self, name), field=name)
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "error_kind": self.error_kind.value,
            "error_stream_offset": self.error_stream_offset,
            "exception_class_digest": self.exception_class_digest,
            "exception_message_digest": self.exception_message_digest,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> ParserErrorMetadataV49C:
        require_exact_keys(
            payload, expected=set(cls.__dataclass_fields__), context=cls.__name__
        )
        return cls(**dict(payload))


def _decode_single_client_frame_v49c(
    chunks: Sequence[bytes],
) -> tuple[WebSocketOpcodeV49C, bytes]:
    """Independently decode one complete, final, masked client frame."""

    wire = b"".join(chunks)
    if len(wire) < 6:
        raise CanonicalizationError(
            "outbound wire must contain one complete masked client frame"
        )
    first, second = wire[0], wire[1]
    opcode = _OPCODE_NUMBER_TO_ENUM.get(first & 0x0F)
    if first & 0x70 or not first & 0x80 or opcode is None or not second & 0x80:
        raise CanonicalizationError(
            "outbound wire has RSV, fragmentation, opcode, or masking mismatch"
        )
    length_marker = second & 0x7F
    cursor = 2
    is_control = opcode in {
        WebSocketOpcodeV49C.CLOSE,
        WebSocketOpcodeV49C.PING,
        WebSocketOpcodeV49C.PONG,
    }
    if is_control and length_marker >= 126:
        raise CanonicalizationError(
            "outbound control frame cannot use an extended payload length"
        )
    if length_marker < 126:
        payload_octets = length_marker
    elif length_marker == 126:
        if len(wire) < cursor + 2 + 4:
            raise CanonicalizationError("outbound wire has a truncated 16-bit length")
        payload_octets = int.from_bytes(wire[cursor : cursor + 2], "big")
        cursor += 2
        if payload_octets < 126:
            raise CanonicalizationError(
                "outbound wire payload length isn't minimally encoded"
            )
    else:
        if len(wire) < cursor + 8 + 4:
            raise CanonicalizationError("outbound wire has a truncated 64-bit length")
        payload_octets = int.from_bytes(wire[cursor : cursor + 8], "big")
        cursor += 8
        if payload_octets < 65_536 or payload_octets >= 2**63:
            raise CanonicalizationError(
                "outbound wire 64-bit payload length is invalid or non-minimal"
            )
    if payload_octets > V49C_MAX_FRAME_PAYLOAD_OCTETS:
        raise CanonicalizationError("outbound wire exceeds the V4.9C payload bound")
    mask = wire[cursor : cursor + 4]
    if len(mask) != 4:
        raise CanonicalizationError("outbound wire has a truncated client mask")
    cursor += 4
    if len(wire) != cursor + payload_octets:
        raise CanonicalizationError(
            "outbound wire contains a partial or concatenated client frame"
        )
    masked_payload = wire[cursor:]
    payload = bytes(
        value ^ mask[index % 4] for index, value in enumerate(masked_payload)
    )
    if opcode is WebSocketOpcodeV49C.TEXT:
        try:
            payload.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise CanonicalizationError(
                "outbound Text payload must be valid UTF-8"
            ) from exc
    if opcode is WebSocketOpcodeV49C.CLOSE:
        if len(payload) == 1:
            raise CanonicalizationError(
                "outbound Close frame has a truncated status code"
            )
        if len(payload) >= 2:
            code = int.from_bytes(payload[:2], "big")
            valid_code = (
                code
                in {
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
                or 3000 <= code <= 4999
            )
            if not valid_code:
                raise CanonicalizationError(
                    "outbound Close frame contains a reserved status code"
                )
            try:
                payload[2:].decode("utf-8", errors="strict")
            except UnicodeDecodeError as exc:
                raise CanonicalizationError(
                    "outbound Close reason must be valid UTF-8"
                ) from exc
    return opcode, payload


def _decode_single_automatic_protocol_output_v49c(
    chunks: Sequence[bytes],
) -> tuple[WebSocketOpcodeV49C, bytes]:
    """Decode one exact masked automatic Close or Pong frame."""

    opcode, payload = _decode_single_client_frame_v49c(chunks)
    if opcode not in {WebSocketOpcodeV49C.CLOSE, WebSocketOpcodeV49C.PONG}:
        raise CanonicalizationError(
            "automatic protocol output must be one final masked Close or Pong frame"
        )
    return opcode, payload


@dataclass(frozen=True, slots=True, kw_only=True)
class ParserTransitionPayloadV49C:
    cursor_before: WebSocketParserCursorV49C
    cursor_after: WebSocketParserCursorV49C
    feed_unit_kind: ParserFeedUnitKindV49C
    source_slices: tuple[RawSourceSliceV49C, ...]
    frame: WebSocketFrameMetadataV49C | None
    parser_error: ParserErrorMetadataV49C | None
    ordered_protocol_output_chunks_base64: tuple[str, ...]
    ordered_protocol_output_chunks_sha256: tuple[str, ...]
    protocol_output_batch_sha256: str | None
    send_eof_after_output: bool
    processed_at: datetime
    processed_monotonic_ns: int

    def __post_init__(self) -> None:
        if (
            type(self.cursor_before) is not WebSocketParserCursorV49C
            or type(self.cursor_after) is not WebSocketParserCursorV49C
        ):
            raise CanonicalizationError("parser cursors must use the exact V4.9C type")
        if self.cursor_after.cursor_sequence != self.cursor_before.cursor_sequence + 1:
            raise CanonicalizationError("parser cursor sequence must advance by one")
        if self.cursor_before.websocket_state in {
            WebSocketParserStateV49C.CLOSED,
            WebSocketParserStateV49C.FAILED,
        }:
            raise CanonicalizationError("terminal parser cursor cannot transition")
        kind = _enum(
            self.feed_unit_kind, ParserFeedUnitKindV49C, field="feed_unit_kind"
        )
        slices = _validate_contiguous_slices(self.source_slices)
        if (
            slices[0].stream_start_octet != self.cursor_before.next_stream_octet
            or slices[-1].stream_end_octet != self.cursor_after.next_stream_octet
        ):
            raise CanonicalizationError(
                "parser cursor movement differs from exact source slices"
            )
        if kind is ParserFeedUnitKindV49C.COMPLETE_FRAME:
            if (
                type(self.frame) is not WebSocketFrameMetadataV49C
                or self.parser_error is not None
            ):
                raise CanonicalizationError(
                    "complete feed unit requires one frame only"
                )
            if (
                self.frame.stream_start_octet != slices[0].stream_start_octet
                or self.frame.stream_end_octet != slices[-1].stream_end_octet
            ):
                raise CanonicalizationError("frame interval differs from source slices")
            if self.cursor_after.websocket_state is WebSocketParserStateV49C.FAILED:
                raise CanonicalizationError(
                    "complete frame cannot produce FAILED cursor"
                )
        else:
            if (
                type(self.parser_error) is not ParserErrorMetadataV49C
                or self.frame is not None
            ):
                raise CanonicalizationError(
                    "error feed unit requires one parser error only"
                )
            if not (
                slices[0].stream_start_octet
                <= self.parser_error.error_stream_offset
                < slices[-1].stream_end_octet
            ):
                raise CanonicalizationError(
                    "parser error offset is outside source slices"
                )
            if self.cursor_after.websocket_state is not WebSocketParserStateV49C.FAILED:
                raise CanonicalizationError("parser error must produce FAILED cursor")
        encoded, chunks = _base64_chunks(
            self.ordered_protocol_output_chunks_base64,
            field="ordered_protocol_output_chunks_base64",
            allow_empty=True,
            maximum_items=V49C_MAX_PROTOCOL_OUTPUT_CHUNKS,
            maximum_octets=V49C_MAX_PROTOCOL_OUTPUT_OCTETS,
        )
        hashes = _hashes(
            self.ordered_protocol_output_chunks_sha256,
            field="ordered_protocol_output_chunks_sha256",
            allow_empty=True,
            maximum=V49C_MAX_PROTOCOL_OUTPUT_CHUNKS,
        )
        expected_hashes = tuple(hashlib.sha256(chunk).hexdigest() for chunk in chunks)
        if hashes != expected_hashes:
            raise CanonicalizationError(
                "protocol output hashes differ from exact bytes"
            )
        batch_hash = _optional_hash(
            self.protocol_output_batch_sha256,
            field="protocol_output_batch_sha256",
        )
        expected_batch = (
            None
            if not encoded
            else _ordered_batch_sha256(_ORDERED_OUTPUT_DOMAIN, encoded)
        )
        if batch_hash != expected_batch:
            raise CanonicalizationError(
                "protocol output batch hash differs from chunks"
            )
        if (
            kind is ParserFeedUnitKindV49C.COMPLETE_FRAME
            and self.cursor_before.websocket_state is WebSocketParserStateV49C.OPEN
            and self.frame is not None
            and self.frame.opcode
            in {WebSocketOpcodeV49C.PING, WebSocketOpcodeV49C.CLOSE}
            and not chunks
        ):
            required = (
                "Pong" if self.frame.opcode is WebSocketOpcodeV49C.PING else "Close"
            )
            raise CanonicalizationError(
                f"OPEN parser {self.frame.opcode.value} requires one automatic "
                f"{required} output"
            )
        if chunks:
            output_opcode, output_payload = (
                _decode_single_automatic_protocol_output_v49c(chunks)
            )
            if kind is ParserFeedUnitKindV49C.COMPLETE_FRAME:
                assert type(self.frame) is WebSocketFrameMetadataV49C
                expected_opcode = {
                    WebSocketOpcodeV49C.PING: WebSocketOpcodeV49C.PONG,
                    WebSocketOpcodeV49C.CLOSE: WebSocketOpcodeV49C.CLOSE,
                }.get(self.frame.opcode)
                if output_opcode is not expected_opcode:
                    raise CanonicalizationError(
                        "complete parser frame cannot cause this automatic output"
                    )
                if self.frame.opcode is WebSocketOpcodeV49C.PING and (
                    len(output_payload) != self.frame.payload_octets
                    or hashlib.sha256(output_payload).hexdigest()
                    != self.frame.payload_sha256
                ):
                    raise CanonicalizationError(
                        "automatic Pong payload differs from the triggering Ping"
                    )
            elif output_opcode is not WebSocketOpcodeV49C.CLOSE:
                raise CanonicalizationError(
                    "parser failure may automatically produce only one Close frame"
                )
        send_eof = _strict_bool(
            self.send_eof_after_output, field="send_eof_after_output"
        )
        if send_eof and self.cursor_after.websocket_state not in {
            WebSocketParserStateV49C.CLOSING,
            WebSocketParserStateV49C.CLOSED,
            WebSocketParserStateV49C.FAILED,
        }:
            raise CanonicalizationError("SEND_EOF requires a non-open parser cursor")
        object.__setattr__(self, "feed_unit_kind", kind)
        object.__setattr__(self, "source_slices", slices)
        object.__setattr__(self, "ordered_protocol_output_chunks_base64", encoded)
        object.__setattr__(self, "ordered_protocol_output_chunks_sha256", hashes)
        object.__setattr__(self, "protocol_output_batch_sha256", batch_hash)
        object.__setattr__(self, "send_eof_after_output", send_eof)
        object.__setattr__(
            self,
            "processed_at",
            utc_datetime(self.processed_at, field="processed_at"),
        )
        object.__setattr__(
            self,
            "processed_monotonic_ns",
            canonical_safe_int(
                self.processed_monotonic_ns,
                field="processed_monotonic_ns",
                minimum=0,
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "cursor_after": self.cursor_after.as_dict(),
            "cursor_before": self.cursor_before.as_dict(),
            "feed_unit_kind": self.feed_unit_kind.value,
            "frame": None if self.frame is None else self.frame.as_dict(),
            "ordered_protocol_output_chunks_base64": list(
                self.ordered_protocol_output_chunks_base64
            ),
            "ordered_protocol_output_chunks_sha256": list(
                self.ordered_protocol_output_chunks_sha256
            ),
            "parser_error": (
                None if self.parser_error is None else self.parser_error.as_dict()
            ),
            "processed_at": utc_iso(self.processed_at),
            "processed_monotonic_ns": self.processed_monotonic_ns,
            "protocol_output_batch_sha256": self.protocol_output_batch_sha256,
            "send_eof_after_output": self.send_eof_after_output,
            "source_slices": [value.as_dict() for value in self.source_slices],
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> ParserTransitionPayloadV49C:
        expected = {
            "cursor_after",
            "cursor_before",
            "feed_unit_kind",
            "frame",
            "ordered_protocol_output_chunks_base64",
            "ordered_protocol_output_chunks_sha256",
            "parser_error",
            "processed_at",
            "processed_monotonic_ns",
            "protocol_output_batch_sha256",
            "send_eof_after_output",
            "source_slices",
        }
        require_exact_keys(payload, expected=expected, context=cls.__name__)
        for name in ("cursor_before", "cursor_after"):
            if not isinstance(payload[name], Mapping):
                raise CanonicalizationError(f"{name} must be a mapping")
        raw_slices = payload["source_slices"]
        if not isinstance(raw_slices, list):
            raise CanonicalizationError("source_slices must be a JSON array")
        raw_frame = payload["frame"]
        raw_error = payload["parser_error"]
        if raw_frame is not None and not isinstance(raw_frame, Mapping):
            raise CanonicalizationError("frame must be null or a mapping")
        if raw_error is not None and not isinstance(raw_error, Mapping):
            raise CanonicalizationError("parser_error must be null or a mapping")
        return cls(
            cursor_before=WebSocketParserCursorV49C.from_mapping(
                payload["cursor_before"]
            ),
            cursor_after=WebSocketParserCursorV49C.from_mapping(
                payload["cursor_after"]
            ),
            feed_unit_kind=payload["feed_unit_kind"],
            source_slices=tuple(
                RawSourceSliceV49C.from_mapping(value) for value in raw_slices
            ),
            frame=(
                None
                if raw_frame is None
                else WebSocketFrameMetadataV49C.from_mapping(raw_frame)
            ),
            parser_error=(
                None
                if raw_error is None
                else ParserErrorMetadataV49C.from_mapping(raw_error)
            ),
            ordered_protocol_output_chunks_base64=tuple(
                payload["ordered_protocol_output_chunks_base64"]
            ),
            ordered_protocol_output_chunks_sha256=tuple(
                payload["ordered_protocol_output_chunks_sha256"]
            ),
            protocol_output_batch_sha256=payload["protocol_output_batch_sha256"],
            send_eof_after_output=payload["send_eof_after_output"],
            processed_at=payload["processed_at"],
            processed_monotonic_ns=payload["processed_monotonic_ns"],
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class OutboundWirePreparedPayloadV49C:
    outbound_operation_id: str
    wire_origin: OutboundWireOriginV49C
    source_parser_event_id: str | None
    logical_opcode: WebSocketOpcodeV49C
    logical_payload_sha256: str
    logical_payload_octets: int
    ordered_wire_chunks_base64: tuple[str, ...]
    ordered_wire_chunks_sha256: tuple[str, ...]
    wire_batch_sha256: str
    wire_octets: int
    prepared_at: datetime
    prepared_monotonic_ns: int
    send_not_after: datetime
    send_not_after_monotonic_ns: int

    def __post_init__(self) -> None:
        for name in (
            "outbound_operation_id",
            "logical_payload_sha256",
            "wire_batch_sha256",
        ):
            object.__setattr__(
                self, name, canonical_hash(getattr(self, name), field=name)
            )
        origin = _enum(self.wire_origin, OutboundWireOriginV49C, field="wire_origin")
        source = _optional_hash(
            self.source_parser_event_id, field="source_parser_event_id"
        )
        if origin is OutboundWireOriginV49C.AUTOMATIC_PROTOCOL and source is None:
            raise CanonicalizationError(
                "automatic wire origin requires one source parser event"
            )
        if (
            origin is not OutboundWireOriginV49C.AUTOMATIC_PROTOCOL
            and source is not None
        ):
            raise CanonicalizationError(
                "non-automatic wire origin forbids a source parser event"
            )
        opcode = _enum(self.logical_opcode, WebSocketOpcodeV49C, field="logical_opcode")
        logical_octets = canonical_safe_int(
            self.logical_payload_octets,
            field="logical_payload_octets",
            minimum=0,
            maximum=V49C_MAX_FRAME_PAYLOAD_OCTETS,
        )
        encoded, chunks = _base64_chunks(
            self.ordered_wire_chunks_base64,
            field="ordered_wire_chunks_base64",
            allow_empty=False,
            maximum_items=V49C_MAX_PROTOCOL_OUTPUT_CHUNKS,
            maximum_octets=V49C_MAX_PROTOCOL_OUTPUT_OCTETS,
        )
        hashes = _hashes(
            self.ordered_wire_chunks_sha256,
            field="ordered_wire_chunks_sha256",
            allow_empty=False,
            maximum=V49C_MAX_PROTOCOL_OUTPUT_CHUNKS,
        )
        if hashes != tuple(hashlib.sha256(chunk).hexdigest() for chunk in chunks):
            raise CanonicalizationError("wire chunk hashes differ from exact bytes")
        wire_octets = canonical_safe_int(
            self.wire_octets, field="wire_octets", minimum=1
        )
        if wire_octets != sum(map(len, chunks)):
            raise CanonicalizationError("wire_octets differs from exact wire chunks")
        if self.wire_batch_sha256 != _ordered_batch_sha256(
            _ORDERED_OUTPUT_DOMAIN, encoded
        ):
            raise CanonicalizationError("wire batch hash differs from exact chunks")
        decoded_opcode, decoded_payload = _decode_single_client_frame_v49c(chunks)
        if (
            decoded_opcode is not opcode
            or len(decoded_payload) != logical_octets
            or hashlib.sha256(decoded_payload).hexdigest()
            != self.logical_payload_sha256
        ):
            raise CanonicalizationError(
                "logical outbound metadata differs from the exact masked client frame"
            )
        if (
            origin is OutboundWireOriginV49C.APPLICATION_INTENT
            and opcode is not WebSocketOpcodeV49C.TEXT
        ):
            raise CanonicalizationError(
                "application wire must be one subscription Text frame"
            )
        if origin is OutboundWireOriginV49C.LOCAL_TERMINAL_COMMAND and (
            opcode is not WebSocketOpcodeV49C.CLOSE
            or decoded_payload != _LOCAL_NORMAL_CLOSE_PAYLOAD_V49E
        ):
            raise CanonicalizationError(
                "local terminal command must be one normal Close with empty reason"
            )
        prepared_at = utc_datetime(self.prepared_at, field="prepared_at")
        deadline = utc_datetime(self.send_not_after, field="send_not_after")
        prepared_ns = canonical_safe_int(
            self.prepared_monotonic_ns,
            field="prepared_monotonic_ns",
            minimum=0,
        )
        deadline_ns = canonical_safe_int(
            self.send_not_after_monotonic_ns,
            field="send_not_after_monotonic_ns",
            minimum=1,
        )
        if deadline <= prepared_at or deadline_ns <= prepared_ns:
            raise CanonicalizationError("wire send deadline must follow preparation")
        object.__setattr__(self, "wire_origin", origin)
        object.__setattr__(self, "source_parser_event_id", source)
        object.__setattr__(self, "logical_opcode", opcode)
        object.__setattr__(self, "logical_payload_octets", logical_octets)
        object.__setattr__(self, "ordered_wire_chunks_base64", encoded)
        object.__setattr__(self, "ordered_wire_chunks_sha256", hashes)
        object.__setattr__(self, "wire_octets", wire_octets)
        object.__setattr__(self, "prepared_at", prepared_at)
        object.__setattr__(self, "prepared_monotonic_ns", prepared_ns)
        object.__setattr__(self, "send_not_after", deadline)
        object.__setattr__(self, "send_not_after_monotonic_ns", deadline_ns)

    def as_dict(self) -> dict[str, Any]:
        return {
            "logical_opcode": self.logical_opcode.value,
            "logical_payload_octets": self.logical_payload_octets,
            "logical_payload_sha256": self.logical_payload_sha256,
            "ordered_wire_chunks_base64": list(self.ordered_wire_chunks_base64),
            "ordered_wire_chunks_sha256": list(self.ordered_wire_chunks_sha256),
            "outbound_operation_id": self.outbound_operation_id,
            "prepared_at": utc_iso(self.prepared_at),
            "prepared_monotonic_ns": self.prepared_monotonic_ns,
            "send_not_after": utc_iso(self.send_not_after),
            "send_not_after_monotonic_ns": self.send_not_after_monotonic_ns,
            "source_parser_event_id": self.source_parser_event_id,
            "wire_batch_sha256": self.wire_batch_sha256,
            "wire_octets": self.wire_octets,
            "wire_origin": self.wire_origin.value,
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> OutboundWirePreparedPayloadV49C:
        expected = set(cls.__dataclass_fields__)
        require_exact_keys(payload, expected=expected, context=cls.__name__)
        return cls(
            **{
                name: payload[name]
                for name in expected
                if name
                not in {"ordered_wire_chunks_base64", "ordered_wire_chunks_sha256"}
            },
            ordered_wire_chunks_base64=tuple(payload["ordered_wire_chunks_base64"]),
            ordered_wire_chunks_sha256=tuple(payload["ordered_wire_chunks_sha256"]),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class WritePermitConsumedPayloadV49C:
    outbound_wire_prepared_event_id: str
    permit_id: str
    one_shot_attempt_ordinal: int
    wire_batch_sha256: str
    wire_octets: int
    consumed_at: datetime
    consumed_monotonic_ns: int
    send_not_after: datetime
    send_not_after_monotonic_ns: int

    def __post_init__(self) -> None:
        for name in (
            "outbound_wire_prepared_event_id",
            "permit_id",
            "wire_batch_sha256",
        ):
            object.__setattr__(
                self, name, canonical_hash(getattr(self, name), field=name)
            )
        ordinal = canonical_safe_int(
            self.one_shot_attempt_ordinal,
            field="one_shot_attempt_ordinal",
            minimum=1,
            maximum=1,
        )
        wire_octets = canonical_safe_int(
            self.wire_octets, field="wire_octets", minimum=1
        )
        consumed = utc_datetime(self.consumed_at, field="consumed_at")
        deadline = utc_datetime(self.send_not_after, field="send_not_after")
        consumed_ns = canonical_safe_int(
            self.consumed_monotonic_ns,
            field="consumed_monotonic_ns",
            minimum=0,
        )
        deadline_ns = canonical_safe_int(
            self.send_not_after_monotonic_ns,
            field="send_not_after_monotonic_ns",
            minimum=1,
        )
        if consumed >= deadline or consumed_ns >= deadline_ns:
            raise CanonicalizationError(
                "write permit was consumed at or after deadline"
            )
        object.__setattr__(self, "one_shot_attempt_ordinal", ordinal)
        object.__setattr__(self, "wire_octets", wire_octets)
        object.__setattr__(self, "consumed_at", consumed)
        object.__setattr__(self, "consumed_monotonic_ns", consumed_ns)
        object.__setattr__(self, "send_not_after", deadline)
        object.__setattr__(self, "send_not_after_monotonic_ns", deadline_ns)

    def as_dict(self) -> dict[str, Any]:
        return {
            "consumed_at": utc_iso(self.consumed_at),
            "consumed_monotonic_ns": self.consumed_monotonic_ns,
            "one_shot_attempt_ordinal": self.one_shot_attempt_ordinal,
            "outbound_wire_prepared_event_id": self.outbound_wire_prepared_event_id,
            "permit_id": self.permit_id,
            "send_not_after": utc_iso(self.send_not_after),
            "send_not_after_monotonic_ns": self.send_not_after_monotonic_ns,
            "wire_batch_sha256": self.wire_batch_sha256,
            "wire_octets": self.wire_octets,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> WritePermitConsumedPayloadV49C:
        require_exact_keys(
            payload, expected=set(cls.__dataclass_fields__), context=cls.__name__
        )
        return cls(**dict(payload))


@dataclass(frozen=True, slots=True, kw_only=True)
class TlsCiphertextPreparedPayloadV49C:
    outbound_wire_prepared_event_id: str
    write_permit_consumed_event_id: str
    plaintext_batch_sha256: str
    plaintext_octets: int
    ordered_ciphertext_chunks_base64: tuple[str, ...]
    ordered_ciphertext_chunks_sha256: tuple[str, ...]
    ciphertext_batch_sha256: str
    ciphertext_octets: int
    prepared_at: datetime
    prepared_monotonic_ns: int

    def __post_init__(self) -> None:
        for name in (
            "outbound_wire_prepared_event_id",
            "write_permit_consumed_event_id",
            "plaintext_batch_sha256",
            "ciphertext_batch_sha256",
        ):
            object.__setattr__(
                self, name, canonical_hash(getattr(self, name), field=name)
            )
        plaintext = canonical_safe_int(
            self.plaintext_octets, field="plaintext_octets", minimum=1
        )
        encoded, chunks = _base64_chunks(
            self.ordered_ciphertext_chunks_base64,
            field="ordered_ciphertext_chunks_base64",
            allow_empty=False,
            maximum_items=V49C_MAX_TLS_CIPHERTEXT_CHUNKS,
            maximum_octets=V49C_MAX_TLS_CIPHERTEXT_OCTETS,
        )
        hashes = _hashes(
            self.ordered_ciphertext_chunks_sha256,
            field="ordered_ciphertext_chunks_sha256",
            allow_empty=False,
            maximum=V49C_MAX_TLS_CIPHERTEXT_CHUNKS,
        )
        if hashes != tuple(hashlib.sha256(chunk).hexdigest() for chunk in chunks):
            raise CanonicalizationError("ciphertext hashes differ from exact bytes")
        ciphertext = canonical_safe_int(
            self.ciphertext_octets, field="ciphertext_octets", minimum=1
        )
        if ciphertext != sum(map(len, chunks)):
            raise CanonicalizationError("ciphertext_octets differs from exact chunks")
        if self.ciphertext_batch_sha256 != _ordered_batch_sha256(
            _ORDERED_CIPHERTEXT_DOMAIN, encoded
        ):
            raise CanonicalizationError("ciphertext batch hash differs from chunks")
        object.__setattr__(self, "plaintext_octets", plaintext)
        object.__setattr__(self, "ordered_ciphertext_chunks_base64", encoded)
        object.__setattr__(self, "ordered_ciphertext_chunks_sha256", hashes)
        object.__setattr__(self, "ciphertext_octets", ciphertext)
        object.__setattr__(
            self,
            "prepared_at",
            utc_datetime(self.prepared_at, field="prepared_at"),
        )
        object.__setattr__(
            self,
            "prepared_monotonic_ns",
            canonical_safe_int(
                self.prepared_monotonic_ns,
                field="prepared_monotonic_ns",
                minimum=0,
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "ciphertext_batch_sha256": self.ciphertext_batch_sha256,
            "ciphertext_octets": self.ciphertext_octets,
            "ordered_ciphertext_chunks_base64": list(
                self.ordered_ciphertext_chunks_base64
            ),
            "ordered_ciphertext_chunks_sha256": list(
                self.ordered_ciphertext_chunks_sha256
            ),
            "outbound_wire_prepared_event_id": self.outbound_wire_prepared_event_id,
            "plaintext_batch_sha256": self.plaintext_batch_sha256,
            "plaintext_octets": self.plaintext_octets,
            "prepared_at": utc_iso(self.prepared_at),
            "prepared_monotonic_ns": self.prepared_monotonic_ns,
            "write_permit_consumed_event_id": self.write_permit_consumed_event_id,
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> TlsCiphertextPreparedPayloadV49C:
        expected = set(cls.__dataclass_fields__)
        require_exact_keys(payload, expected=expected, context=cls.__name__)
        return cls(
            **{
                name: payload[name]
                for name in expected
                if name
                not in {
                    "ordered_ciphertext_chunks_base64",
                    "ordered_ciphertext_chunks_sha256",
                }
            },
            ordered_ciphertext_chunks_base64=tuple(
                payload["ordered_ciphertext_chunks_base64"]
            ),
            ordered_ciphertext_chunks_sha256=tuple(
                payload["ordered_ciphertext_chunks_sha256"]
            ),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class KernelSendAttemptPayloadV49C:
    tls_ciphertext_prepared_event_id: str
    kernel_attempt_ordinal: int
    ciphertext_batch_sha256: str
    ciphertext_octets: int
    ciphertext_start_octet: int
    requested_octets: int
    attempted_at: datetime
    attempted_monotonic_ns: int

    def __post_init__(self) -> None:
        for name in ("tls_ciphertext_prepared_event_id", "ciphertext_batch_sha256"):
            object.__setattr__(
                self, name, canonical_hash(getattr(self, name), field=name)
            )
        ordinal = canonical_safe_int(
            self.kernel_attempt_ordinal,
            field="kernel_attempt_ordinal",
            minimum=1,
        )
        total = canonical_safe_int(
            self.ciphertext_octets, field="ciphertext_octets", minimum=1
        )
        start = canonical_safe_int(
            self.ciphertext_start_octet,
            field="ciphertext_start_octet",
            minimum=0,
        )
        requested = canonical_safe_int(
            self.requested_octets, field="requested_octets", minimum=1
        )
        if start >= total or start + requested > total:
            raise CanonicalizationError("kernel send request exceeds ciphertext range")
        object.__setattr__(self, "kernel_attempt_ordinal", ordinal)
        object.__setattr__(self, "ciphertext_octets", total)
        object.__setattr__(self, "ciphertext_start_octet", start)
        object.__setattr__(self, "requested_octets", requested)
        object.__setattr__(
            self,
            "attempted_at",
            utc_datetime(self.attempted_at, field="attempted_at"),
        )
        object.__setattr__(
            self,
            "attempted_monotonic_ns",
            canonical_safe_int(
                self.attempted_monotonic_ns,
                field="attempted_monotonic_ns",
                minimum=0,
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "attempted_at": utc_iso(self.attempted_at),
            "attempted_monotonic_ns": self.attempted_monotonic_ns,
            "ciphertext_batch_sha256": self.ciphertext_batch_sha256,
            "ciphertext_octets": self.ciphertext_octets,
            "ciphertext_start_octet": self.ciphertext_start_octet,
            "kernel_attempt_ordinal": self.kernel_attempt_ordinal,
            "requested_octets": self.requested_octets,
            "tls_ciphertext_prepared_event_id": self.tls_ciphertext_prepared_event_id,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> KernelSendAttemptPayloadV49C:
        require_exact_keys(
            payload, expected=set(cls.__dataclass_fields__), context=cls.__name__
        )
        return cls(**dict(payload))


@dataclass(frozen=True, slots=True, kw_only=True)
class KernelSendResultPayloadV49C:
    kernel_send_attempt_event_id: str
    tls_ciphertext_prepared_event_id: str
    kernel_attempt_ordinal: int
    ciphertext_batch_sha256: str
    ciphertext_octets: int
    ciphertext_start_octet: int
    requested_octets: int
    accepted_octets: int
    resulting_ciphertext_offset: int
    observed_at: datetime
    observed_monotonic_ns: int

    def __post_init__(self) -> None:
        for name in (
            "kernel_send_attempt_event_id",
            "tls_ciphertext_prepared_event_id",
            "ciphertext_batch_sha256",
        ):
            object.__setattr__(
                self, name, canonical_hash(getattr(self, name), field=name)
            )
        ordinal = canonical_safe_int(
            self.kernel_attempt_ordinal,
            field="kernel_attempt_ordinal",
            minimum=1,
        )
        total = canonical_safe_int(
            self.ciphertext_octets, field="ciphertext_octets", minimum=1
        )
        start = canonical_safe_int(
            self.ciphertext_start_octet,
            field="ciphertext_start_octet",
            minimum=0,
        )
        requested = canonical_safe_int(
            self.requested_octets, field="requested_octets", minimum=1
        )
        accepted = canonical_safe_int(
            self.accepted_octets, field="accepted_octets", minimum=1
        )
        resulting = canonical_safe_int(
            self.resulting_ciphertext_offset,
            field="resulting_ciphertext_offset",
            minimum=1,
        )
        if accepted > requested or resulting != start + accepted or resulting > total:
            raise CanonicalizationError(
                "kernel send result has an invalid positive count"
            )
        object.__setattr__(self, "kernel_attempt_ordinal", ordinal)
        object.__setattr__(self, "ciphertext_octets", total)
        object.__setattr__(self, "ciphertext_start_octet", start)
        object.__setattr__(self, "requested_octets", requested)
        object.__setattr__(self, "accepted_octets", accepted)
        object.__setattr__(self, "resulting_ciphertext_offset", resulting)
        object.__setattr__(
            self,
            "observed_at",
            utc_datetime(self.observed_at, field="observed_at"),
        )
        object.__setattr__(
            self,
            "observed_monotonic_ns",
            canonical_safe_int(
                self.observed_monotonic_ns,
                field="observed_monotonic_ns",
                minimum=0,
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            result[name] = utc_iso(value) if name == "observed_at" else value
        return result

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> KernelSendResultPayloadV49C:
        require_exact_keys(
            payload, expected=set(cls.__dataclass_fields__), context=cls.__name__
        )
        return cls(**dict(payload))


@dataclass(frozen=True, slots=True, kw_only=True)
class KernelSendFailurePayloadV49E:
    """Durable zero-acceptance result for one write-ahead send attempt."""

    kernel_send_attempt_event_id: str
    tls_ciphertext_prepared_event_id: str
    kernel_attempt_ordinal: int
    ciphertext_batch_sha256: str
    ciphertext_octets: int
    ciphertext_start_octet: int
    requested_octets: int
    local_shutdown_command_started_event_id: str | None
    shutdown_deadline_monotonic_ns: int
    failure_kind: KernelSendFailureKindV49E
    owner_evidence_id: str | None
    kernel_socket_identity: str | None
    driver_evidence_nonce_sha256: str | None
    owner_deadline_operation: str | None
    send_kind: str | None
    transport_sequence: int | None
    exact_slice_sha256: str | None
    would_block_count: int | None
    driver_evidence_id: str | None
    observed_at: datetime
    observed_monotonic_ns: int

    def __post_init__(self) -> None:
        for name in (
            "kernel_send_attempt_event_id",
            "tls_ciphertext_prepared_event_id",
            "ciphertext_batch_sha256",
        ):
            object.__setattr__(
                self,
                name,
                canonical_hash(getattr(self, name), field=name),
            )
        object.__setattr__(
            self,
            "local_shutdown_command_started_event_id",
            _optional_hash(
                self.local_shutdown_command_started_event_id,
                field="local_shutdown_command_started_event_id",
            ),
        )
        ordinal = canonical_safe_int(
            self.kernel_attempt_ordinal,
            field="kernel_attempt_ordinal",
            minimum=1,
        )
        total = canonical_safe_int(
            self.ciphertext_octets,
            field="ciphertext_octets",
            minimum=1,
        )
        start = canonical_safe_int(
            self.ciphertext_start_octet,
            field="ciphertext_start_octet",
            minimum=0,
        )
        requested = canonical_safe_int(
            self.requested_octets,
            field="requested_octets",
            minimum=1,
        )
        if start >= total or start + requested > total:
            raise CanonicalizationError(
                "non-invoked kernel send differs from its requested range"
            )
        object.__setattr__(self, "kernel_attempt_ordinal", ordinal)
        object.__setattr__(self, "ciphertext_octets", total)
        object.__setattr__(self, "ciphertext_start_octet", start)
        object.__setattr__(self, "requested_octets", requested)
        deadline_ns = canonical_safe_int(
            self.shutdown_deadline_monotonic_ns,
            field="shutdown_deadline_monotonic_ns",
            minimum=1,
        )
        failure_kind = _enum(
            self.failure_kind,
            KernelSendFailureKindV49E,
            field="failure_kind",
        )
        evidence_hash_names = (
            "owner_evidence_id",
            "kernel_socket_identity",
            "driver_evidence_nonce_sha256",
            "exact_slice_sha256",
            "driver_evidence_id",
        )
        evidence_hashes = tuple(
            _optional_hash(getattr(self, name), field=name)
            for name in evidence_hash_names
        )
        owner_deadline_operation = (
            None
            if self.owner_deadline_operation is None
            else canonical_identifier(
                self.owner_deadline_operation,
                field="owner_deadline_operation",
                maximum=64,
            )
        )
        send_kind = (
            None
            if self.send_kind is None
            else canonical_identifier(self.send_kind, field="send_kind", maximum=64)
        )
        transport_sequence = (
            None
            if self.transport_sequence is None
            else canonical_safe_int(
                self.transport_sequence,
                field="transport_sequence",
                minimum=1,
            )
        )
        would_block_count = (
            None
            if self.would_block_count is None
            else canonical_safe_int(
                self.would_block_count,
                field="would_block_count",
                minimum=1,
            )
        )
        owner_before_syscall = (
            failure_kind is KernelSendFailureKindV49E.DEADLINE_EXPIRED_BEFORE_SYSCALL
        )
        sealed_no_acceptance = (
            failure_kind
            is KernelSendFailureKindV49E.DEADLINE_EXPIRED_NO_KERNEL_ACCEPTANCE
        )
        owner_common_evidence = all(value is not None for value in evidence_hashes[:3])
        complete_no_acceptance_evidence = (
            all(value is not None for value in evidence_hashes)
            and send_kind is not None
            and transport_sequence is not None
            and would_block_count is not None
            and owner_deadline_operation is None
        )
        complete_before_syscall_evidence = (
            owner_common_evidence
            and owner_deadline_operation == "WEBSOCKET_CLOSE_SEND_BEFORE_SYSCALL"
            and all(value is None for value in evidence_hashes[3:])
            and send_kind is None
            and transport_sequence is None
            and would_block_count is None
        )
        actor_without_owner_evidence = failure_kind in {
            KernelSendFailureKindV49E.DEADLINE_EXPIRED_BEFORE_CALLBACK,
            KernelSendFailureKindV49E.CLOCK_DISAGREEMENT,
        }
        if sealed_no_acceptance != complete_no_acceptance_evidence:
            raise CanonicalizationError(
                "only sealed no-kernel-acceptance carries owner evidence"
            )
        if owner_before_syscall != complete_before_syscall_evidence:
            raise CanonicalizationError(
                "owner pre-syscall expiry requires exact no-observation evidence"
            )
        if actor_without_owner_evidence and any(
            value is not None
            for value in (
                *evidence_hashes,
                owner_deadline_operation,
                send_kind,
                transport_sequence,
                would_block_count,
            )
        ):
            raise CanonicalizationError(
                "actor-proven pre-callback expiry cannot carry owner evidence"
            )
        if sealed_no_acceptance and send_kind not in {
            "LOCAL_WEBSOCKET_CLOSE",
            "AUTOMATIC_WEBSOCKET_CLOSE",
        }:
            raise CanonicalizationError(
                "ordinary kernel send failure requires exact WebSocket Close evidence"
            )
        if sealed_no_acceptance:
            expected_driver_evidence_id = _derive_driver_send_deadline_evidence_id_v49e(
                driver_evidence_nonce_sha256=evidence_hashes[2],
                send_kind=send_kind,
                transport_sequence=transport_sequence,
                ciphertext_batch_sha256=self.ciphertext_batch_sha256,
                ciphertext_octets=total,
                ciphertext_start_octet=start,
                requested_octets=requested,
                exact_slice_sha256=evidence_hashes[3],
                deadline_ns=deadline_ns,
                would_block_count=would_block_count,
            )
            if evidence_hashes[4] != expected_driver_evidence_id:
                raise CanonicalizationError(
                    "kernel send driver evidence ID differs from exact fields"
                )
        object.__setattr__(self, "shutdown_deadline_monotonic_ns", deadline_ns)
        object.__setattr__(self, "failure_kind", failure_kind)
        for name, value in zip(evidence_hash_names, evidence_hashes):
            object.__setattr__(self, name, value)
        object.__setattr__(
            self,
            "owner_deadline_operation",
            owner_deadline_operation,
        )
        object.__setattr__(self, "send_kind", send_kind)
        object.__setattr__(self, "transport_sequence", transport_sequence)
        object.__setattr__(self, "would_block_count", would_block_count)
        object.__setattr__(
            self,
            "observed_at",
            utc_datetime(self.observed_at, field="observed_at"),
        )
        object.__setattr__(
            self,
            "observed_monotonic_ns",
            canonical_safe_int(
                self.observed_monotonic_ns,
                field="observed_monotonic_ns",
                minimum=0,
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if name == "observed_at":
                value = utc_iso(value)
            elif name == "failure_kind":
                value = value.value
            result[name] = value
        return result

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
    ) -> KernelSendFailurePayloadV49E:
        require_exact_keys(
            payload,
            expected=set(cls.__dataclass_fields__),
            context=cls.__name__,
        )
        return cls(**dict(payload))


@dataclass(frozen=True, slots=True, kw_only=True)
class OutboundDispatchCompletedPayloadV49C:
    outbound_wire_prepared_event_id: str
    write_permit_consumed_event_id: str
    tls_ciphertext_prepared_event_id: str
    kernel_send_result_event_ids: tuple[str, ...]
    ciphertext_batch_sha256: str
    ciphertext_octets: int
    submitted_ciphertext_octets: int
    disposition: OutboundDispatchDispositionV49C
    completed_at: datetime
    completed_monotonic_ns: int

    def __post_init__(self) -> None:
        for name in (
            "outbound_wire_prepared_event_id",
            "write_permit_consumed_event_id",
            "tls_ciphertext_prepared_event_id",
            "ciphertext_batch_sha256",
        ):
            object.__setattr__(
                self, name, canonical_hash(getattr(self, name), field=name)
            )
        result_ids = _hashes(
            self.kernel_send_result_event_ids,
            field="kernel_send_result_event_ids",
            allow_empty=False,
            maximum=V49C_MAX_TLS_CIPHERTEXT_CHUNKS,
        )
        if len(set(result_ids)) != len(result_ids):
            raise CanonicalizationError("kernel send result IDs must be unique")
        total = canonical_safe_int(
            self.ciphertext_octets, field="ciphertext_octets", minimum=1
        )
        submitted = canonical_safe_int(
            self.submitted_ciphertext_octets,
            field="submitted_ciphertext_octets",
            minimum=1,
        )
        disposition = _enum(
            self.disposition,
            OutboundDispatchDispositionV49C,
            field="disposition",
        )
        if (
            submitted != total
            or disposition
            is not OutboundDispatchDispositionV49C.COMPLETE_LOCAL_SUBMISSION
        ):
            raise CanonicalizationError(
                "dispatch completion requires exact full local submission"
            )
        object.__setattr__(self, "kernel_send_result_event_ids", result_ids)
        object.__setattr__(self, "ciphertext_octets", total)
        object.__setattr__(self, "submitted_ciphertext_octets", submitted)
        object.__setattr__(self, "disposition", disposition)
        object.__setattr__(
            self,
            "completed_at",
            utc_datetime(self.completed_at, field="completed_at"),
        )
        object.__setattr__(
            self,
            "completed_monotonic_ns",
            canonical_safe_int(
                self.completed_monotonic_ns,
                field="completed_monotonic_ns",
                minimum=0,
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "ciphertext_batch_sha256": self.ciphertext_batch_sha256,
            "ciphertext_octets": self.ciphertext_octets,
            "completed_at": utc_iso(self.completed_at),
            "completed_monotonic_ns": self.completed_monotonic_ns,
            "disposition": self.disposition.value,
            "kernel_send_result_event_ids": list(self.kernel_send_result_event_ids),
            "outbound_wire_prepared_event_id": self.outbound_wire_prepared_event_id,
            "submitted_ciphertext_octets": self.submitted_ciphertext_octets,
            "tls_ciphertext_prepared_event_id": self.tls_ciphertext_prepared_event_id,
            "write_permit_consumed_event_id": self.write_permit_consumed_event_id,
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> OutboundDispatchCompletedPayloadV49C:
        expected = set(cls.__dataclass_fields__)
        require_exact_keys(payload, expected=expected, context=cls.__name__)
        return cls(
            **{
                name: payload[name]
                for name in expected
                if name != "kernel_send_result_event_ids"
            },
            kernel_send_result_event_ids=tuple(payload["kernel_send_result_event_ids"]),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class ApplicationMessageCommittedPayloadV49E:
    """Canonical provider-message evidence sourced from exact parser frames."""

    source_parser_event_ids: tuple[str, ...]
    message_opcode: WebSocketOpcodeV49C
    message_payload_octets: int
    message_payload_sha256: str
    capture_segment_id: str
    message_receipt_id: str
    physical_message_id: str
    provider_message_disposition_id: str
    message_disposition_id: str
    disposition_kind: MessageDispositionKind
    received_at: datetime
    received_monotonic_ns: int
    classified_at: datetime
    classified_monotonic_ns: int

    def __post_init__(self) -> None:
        source_ids = _hashes(
            self.source_parser_event_ids,
            field="source_parser_event_ids",
            allow_empty=False,
            maximum=V49E_MAX_APPLICATION_MESSAGE_FRAMES,
        )
        if len(set(source_ids)) != len(source_ids):
            raise CanonicalizationError("source parser event IDs must be unique")
        opcode = _enum(self.message_opcode, WebSocketOpcodeV49C, field="message_opcode")
        if opcode not in {WebSocketOpcodeV49C.TEXT, WebSocketOpcodeV49C.BINARY}:
            raise CanonicalizationError(
                "application message opcode must be TEXT or BINARY"
            )
        octets = canonical_safe_int(
            self.message_payload_octets,
            field="message_payload_octets",
            minimum=0,
            maximum=V49C_MAX_FRAME_PAYLOAD_OCTETS,
        )
        for name in (
            "message_payload_sha256",
            "capture_segment_id",
            "message_receipt_id",
            "physical_message_id",
            "provider_message_disposition_id",
            "message_disposition_id",
        ):
            object.__setattr__(
                self, name, canonical_hash(getattr(self, name), field=name)
            )
        disposition = _enum(
            self.disposition_kind,
            MessageDispositionKind,
            field="disposition_kind",
        )
        received = utc_datetime(self.received_at, field="received_at")
        classified = utc_datetime(self.classified_at, field="classified_at")
        received_ns = canonical_safe_int(
            self.received_monotonic_ns,
            field="received_monotonic_ns",
            minimum=0,
        )
        classified_ns = canonical_safe_int(
            self.classified_monotonic_ns,
            field="classified_monotonic_ns",
            minimum=0,
        )
        if classified < received or classified_ns < received_ns:
            raise CanonicalizationError("classification predates message receipt")
        object.__setattr__(self, "source_parser_event_ids", source_ids)
        object.__setattr__(self, "message_opcode", opcode)
        object.__setattr__(self, "message_payload_octets", octets)
        object.__setattr__(self, "disposition_kind", disposition)
        object.__setattr__(self, "received_at", received)
        object.__setattr__(self, "received_monotonic_ns", received_ns)
        object.__setattr__(self, "classified_at", classified)
        object.__setattr__(self, "classified_monotonic_ns", classified_ns)

    def as_dict(self) -> dict[str, Any]:
        return {
            "capture_segment_id": self.capture_segment_id,
            "classified_at": utc_iso(self.classified_at),
            "classified_monotonic_ns": self.classified_monotonic_ns,
            "disposition_kind": self.disposition_kind.value,
            "message_disposition_id": self.message_disposition_id,
            "message_opcode": self.message_opcode.value,
            "message_payload_octets": self.message_payload_octets,
            "message_payload_sha256": self.message_payload_sha256,
            "message_receipt_id": self.message_receipt_id,
            "physical_message_id": self.physical_message_id,
            "provider_message_disposition_id": (self.provider_message_disposition_id),
            "received_at": utc_iso(self.received_at),
            "received_monotonic_ns": self.received_monotonic_ns,
            "source_parser_event_ids": list(self.source_parser_event_ids),
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> ApplicationMessageCommittedPayloadV49E:
        expected = set(cls.__dataclass_fields__)
        require_exact_keys(payload, expected=expected, context=cls.__name__)
        return cls(
            **{
                name: payload[name]
                for name in expected
                if name != "source_parser_event_ids"
            },
            source_parser_event_ids=tuple(payload["source_parser_event_ids"]),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class SubscriptionAckBoundPayloadV49E:
    """Exact ACK binding to one application message and completed dispatch."""

    source_application_message_event_id: str
    outbound_subscription_intent_id: str
    subscription_dispatch_completed_event_id: str
    subscription_ack_binding_id: str
    provider_message_disposition_id: str
    message_disposition_id: str
    echoed_request_id: str
    provider_connection_id: str
    request_command_sha256: str
    raw_ack_sha256: str
    dispatch_started_at: datetime
    dispatch_completed_at: datetime
    dispatch_started_monotonic_ns: int
    dispatch_completed_monotonic_ns: int
    ack_received_at: datetime
    ack_received_monotonic_ns: int
    ack_not_after: datetime
    ack_not_after_monotonic_ns: int
    bound_at: datetime
    bound_monotonic_ns: int

    def __post_init__(self) -> None:
        for name in (
            "source_application_message_event_id",
            "outbound_subscription_intent_id",
            "subscription_dispatch_completed_event_id",
            "subscription_ack_binding_id",
            "provider_message_disposition_id",
            "message_disposition_id",
            "request_command_sha256",
            "raw_ack_sha256",
        ):
            object.__setattr__(
                self, name, canonical_hash(getattr(self, name), field=name)
            )
        for name in ("echoed_request_id", "provider_connection_id"):
            object.__setattr__(
                self,
                name,
                canonical_identifier(getattr(self, name), field=name, maximum=256),
            )
        started = utc_datetime(self.dispatch_started_at, field="dispatch_started_at")
        completed = utc_datetime(
            self.dispatch_completed_at, field="dispatch_completed_at"
        )
        received = utc_datetime(self.ack_received_at, field="ack_received_at")
        deadline = utc_datetime(self.ack_not_after, field="ack_not_after")
        bound = utc_datetime(self.bound_at, field="bound_at")
        started_ns = canonical_safe_int(
            self.dispatch_started_monotonic_ns,
            field="dispatch_started_monotonic_ns",
            minimum=0,
        )
        completed_ns = canonical_safe_int(
            self.dispatch_completed_monotonic_ns,
            field="dispatch_completed_monotonic_ns",
            minimum=0,
        )
        received_ns = canonical_safe_int(
            self.ack_received_monotonic_ns,
            field="ack_received_monotonic_ns",
            minimum=0,
        )
        deadline_ns = canonical_safe_int(
            self.ack_not_after_monotonic_ns,
            field="ack_not_after_monotonic_ns",
            minimum=1,
        )
        bound_ns = canonical_safe_int(
            self.bound_monotonic_ns,
            field="bound_monotonic_ns",
            minimum=0,
        )
        if not started <= completed < received <= bound:
            raise CanonicalizationError(
                "dispatch, ACK, and binding wall clocks are not causally ordered"
            )
        if received > deadline:
            raise CanonicalizationError("ACK receipt exceeds its durable deadline")
        if not (
            started_ns <= completed_ns < received_ns <= bound_ns
            and received_ns <= deadline_ns
        ):
            raise CanonicalizationError(
                "dispatch, ACK, and deadline monotonic clocks are not causally ordered"
            )
        object.__setattr__(self, "dispatch_started_at", started)
        object.__setattr__(self, "dispatch_completed_at", completed)
        object.__setattr__(self, "ack_received_at", received)
        object.__setattr__(self, "ack_not_after", deadline)
        object.__setattr__(self, "bound_at", bound)
        object.__setattr__(self, "dispatch_started_monotonic_ns", started_ns)
        object.__setattr__(self, "dispatch_completed_monotonic_ns", completed_ns)
        object.__setattr__(self, "ack_received_monotonic_ns", received_ns)
        object.__setattr__(self, "ack_not_after_monotonic_ns", deadline_ns)
        object.__setattr__(self, "bound_monotonic_ns", bound_ns)

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        wall_clock_names = {
            "ack_not_after",
            "ack_received_at",
            "bound_at",
            "dispatch_completed_at",
            "dispatch_started_at",
        }
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            result[name] = utc_iso(value) if name in wall_clock_names else value
        return result

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> SubscriptionAckBoundPayloadV49E:
        require_exact_keys(
            payload, expected=set(cls.__dataclass_fields__), context=cls.__name__
        )
        return cls(**dict(payload))


@dataclass(frozen=True, slots=True, kw_only=True)
class AckDeadlineExpiredPayloadV49E:
    """Durable proof that one dispatched subscription missed its ACK deadline."""

    outbound_subscription_intent_id: str
    subscription_dispatch_completed_event_id: str
    dispatch_completed_at: datetime
    dispatch_completed_monotonic_ns: int
    ack_not_after: datetime
    ack_not_after_monotonic_ns: int
    observed_at: datetime
    observed_monotonic_ns: int

    def __post_init__(self) -> None:
        for name in (
            "outbound_subscription_intent_id",
            "subscription_dispatch_completed_event_id",
        ):
            object.__setattr__(
                self, name, canonical_hash(getattr(self, name), field=name)
            )
        completed = utc_datetime(
            self.dispatch_completed_at, field="dispatch_completed_at"
        )
        deadline = utc_datetime(self.ack_not_after, field="ack_not_after")
        observed = utc_datetime(self.observed_at, field="observed_at")
        completed_ns = canonical_safe_int(
            self.dispatch_completed_monotonic_ns,
            field="dispatch_completed_monotonic_ns",
            minimum=0,
        )
        deadline_ns = canonical_safe_int(
            self.ack_not_after_monotonic_ns,
            field="ack_not_after_monotonic_ns",
            minimum=1,
        )
        observed_ns = canonical_safe_int(
            self.observed_monotonic_ns,
            field="observed_monotonic_ns",
            minimum=0,
        )
        if not completed < deadline <= observed:
            raise CanonicalizationError(
                "ACK deadline observation wall clocks are not causally ordered"
            )
        if not completed_ns < deadline_ns <= observed_ns:
            raise CanonicalizationError(
                "ACK deadline observation monotonic clocks are not causally ordered"
            )
        object.__setattr__(self, "dispatch_completed_at", completed)
        object.__setattr__(self, "ack_not_after", deadline)
        object.__setattr__(self, "observed_at", observed)
        object.__setattr__(self, "dispatch_completed_monotonic_ns", completed_ns)
        object.__setattr__(self, "ack_not_after_monotonic_ns", deadline_ns)
        object.__setattr__(self, "observed_monotonic_ns", observed_ns)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ack_not_after": utc_iso(self.ack_not_after),
            "ack_not_after_monotonic_ns": self.ack_not_after_monotonic_ns,
            "dispatch_completed_at": utc_iso(self.dispatch_completed_at),
            "dispatch_completed_monotonic_ns": (self.dispatch_completed_monotonic_ns),
            "observed_at": utc_iso(self.observed_at),
            "observed_monotonic_ns": self.observed_monotonic_ns,
            "outbound_subscription_intent_id": (self.outbound_subscription_intent_id),
            "subscription_dispatch_completed_event_id": (
                self.subscription_dispatch_completed_event_id
            ),
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> AckDeadlineExpiredPayloadV49E:
        require_exact_keys(
            payload, expected=set(cls.__dataclass_fields__), context=cls.__name__
        )
        return cls(**dict(payload))


@dataclass(frozen=True, slots=True, kw_only=True)
class LocalShutdownCommandStartedPayloadV49E:
    """Durable local shutdown authority fixed before any owner mutation."""

    local_shutdown_command_id: str
    websocket_close_code: int
    websocket_close_reason_sha256: str
    websocket_close_reason_octets: int
    websocket_close_payload_sha256: str
    websocket_close_payload_octets: int
    timeout_seconds: int
    started_at: datetime
    started_monotonic_ns: int
    shutdown_deadline_at: datetime
    shutdown_deadline_monotonic_ns: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "local_shutdown_command_id",
            canonical_hash(
                self.local_shutdown_command_id,
                field="local_shutdown_command_id",
            ),
        )
        code = canonical_safe_int(
            self.websocket_close_code,
            field="websocket_close_code",
            minimum=1000,
            maximum=1000,
        )
        reason_sha256 = canonical_hash(
            self.websocket_close_reason_sha256,
            field="websocket_close_reason_sha256",
        )
        reason_octets = canonical_safe_int(
            self.websocket_close_reason_octets,
            field="websocket_close_reason_octets",
            minimum=0,
            maximum=0,
        )
        payload_sha256 = canonical_hash(
            self.websocket_close_payload_sha256,
            field="websocket_close_payload_sha256",
        )
        payload_octets = canonical_safe_int(
            self.websocket_close_payload_octets,
            field="websocket_close_payload_octets",
            minimum=2,
            maximum=2,
        )
        timeout = canonical_safe_int(
            self.timeout_seconds,
            field="timeout_seconds",
            minimum=1,
            maximum=V49E_MAX_LOCAL_SHUTDOWN_TIMEOUT_SECONDS,
        )
        started = utc_datetime(self.started_at, field="started_at")
        started_ns = canonical_safe_int(
            self.started_monotonic_ns,
            field="started_monotonic_ns",
            minimum=0,
        )
        deadline = utc_datetime(
            self.shutdown_deadline_at,
            field="shutdown_deadline_at",
        )
        deadline_ns = canonical_safe_int(
            self.shutdown_deadline_monotonic_ns,
            field="shutdown_deadline_monotonic_ns",
            minimum=1,
        )
        if (
            reason_sha256 != _LOCAL_NORMAL_CLOSE_REASON_SHA256_V49E
            or reason_octets != len(_LOCAL_NORMAL_CLOSE_REASON_V49E)
            or payload_sha256 != _LOCAL_NORMAL_CLOSE_PAYLOAD_SHA256_V49E
            or payload_octets != len(_LOCAL_NORMAL_CLOSE_PAYLOAD_V49E)
            or deadline != started + timedelta(seconds=timeout)
            or deadline_ns != started_ns + timeout * 1_000_000_000
        ):
            raise CanonicalizationError(
                "local shutdown command differs from fixed Close or clock horizon"
            )
        object.__setattr__(self, "websocket_close_code", code)
        object.__setattr__(self, "websocket_close_reason_sha256", reason_sha256)
        object.__setattr__(self, "websocket_close_reason_octets", reason_octets)
        object.__setattr__(self, "websocket_close_payload_sha256", payload_sha256)
        object.__setattr__(self, "websocket_close_payload_octets", payload_octets)
        object.__setattr__(self, "timeout_seconds", timeout)
        object.__setattr__(self, "started_at", started)
        object.__setattr__(self, "started_monotonic_ns", started_ns)
        object.__setattr__(self, "shutdown_deadline_at", deadline)
        object.__setattr__(self, "shutdown_deadline_monotonic_ns", deadline_ns)

    def as_dict(self) -> dict[str, Any]:
        return {
            "local_shutdown_command_id": self.local_shutdown_command_id,
            "shutdown_deadline_at": utc_iso(self.shutdown_deadline_at),
            "shutdown_deadline_monotonic_ns": self.shutdown_deadline_monotonic_ns,
            "started_at": utc_iso(self.started_at),
            "started_monotonic_ns": self.started_monotonic_ns,
            "timeout_seconds": self.timeout_seconds,
            "websocket_close_code": self.websocket_close_code,
            "websocket_close_payload_octets": self.websocket_close_payload_octets,
            "websocket_close_payload_sha256": self.websocket_close_payload_sha256,
            "websocket_close_reason_octets": self.websocket_close_reason_octets,
            "websocket_close_reason_sha256": self.websocket_close_reason_sha256,
        }

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
    ) -> LocalShutdownCommandStartedPayloadV49E:
        require_exact_keys(
            payload,
            expected=set(cls.__dataclass_fields__),
            context=cls.__name__,
        )
        return cls(**dict(payload))


@dataclass(frozen=True, slots=True, kw_only=True)
class LocalShutdownDeadlineEvidencePayloadV49E:
    """Consumed owner-A evidence bound to one shutdown command clock pair."""

    local_shutdown_command_started_event_id: str
    shutdown_deadline_monotonic_ns: int
    operation: str
    classification: LocalShutdownDeadlineClassificationV49E
    owner_evidence_id: str
    kernel_socket_identity: str
    driver_evidence_nonce_sha256: str
    observed_at: datetime
    observed_monotonic_ns: int

    def __post_init__(self) -> None:
        for name in (
            "local_shutdown_command_started_event_id",
            "owner_evidence_id",
            "kernel_socket_identity",
            "driver_evidence_nonce_sha256",
        ):
            object.__setattr__(
                self,
                name,
                canonical_hash(getattr(self, name), field=name),
            )
        object.__setattr__(
            self,
            "shutdown_deadline_monotonic_ns",
            canonical_safe_int(
                self.shutdown_deadline_monotonic_ns,
                field="shutdown_deadline_monotonic_ns",
                minimum=1,
            ),
        )
        operation = canonical_identifier(self.operation, field="operation", maximum=64)
        if operation not in _V49E_LOCAL_SHUTDOWN_NO_OBSERVATION_OPERATIONS:
            raise CanonicalizationError(
                "local shutdown deadline evidence has unsupported operation"
            )
        object.__setattr__(self, "operation", operation)
        object.__setattr__(
            self,
            "classification",
            _enum(
                self.classification,
                LocalShutdownDeadlineClassificationV49E,
                field="classification",
            ),
        )
        object.__setattr__(
            self,
            "observed_at",
            utc_datetime(self.observed_at, field="observed_at"),
        )
        object.__setattr__(
            self,
            "observed_monotonic_ns",
            canonical_safe_int(
                self.observed_monotonic_ns,
                field="observed_monotonic_ns",
                minimum=0,
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "classification": self.classification.value,
            "driver_evidence_nonce_sha256": self.driver_evidence_nonce_sha256,
            "kernel_socket_identity": self.kernel_socket_identity,
            "local_shutdown_command_started_event_id": (
                self.local_shutdown_command_started_event_id
            ),
            "observed_at": utc_iso(self.observed_at),
            "observed_monotonic_ns": self.observed_monotonic_ns,
            "operation": self.operation,
            "owner_evidence_id": self.owner_evidence_id,
            "shutdown_deadline_monotonic_ns": (self.shutdown_deadline_monotonic_ns),
        }

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
    ) -> LocalShutdownDeadlineEvidencePayloadV49E:
        require_exact_keys(
            payload,
            expected=set(cls.__dataclass_fields__),
            context=cls.__name__,
        )
        return cls(**dict(payload))


@dataclass(frozen=True, slots=True, kw_only=True)
class TerminalIngressFailurePayloadV49E:
    """Owner-sealed partial terminal ingress classified under one command."""

    local_shutdown_command_started_event_id: str
    shutdown_deadline_monotonic_ns: int
    failure_kind: TerminalIngressFailureKindV49E
    operation: str
    owner_evidence_id: str
    driver_evidence_id: str
    kernel_socket_identity: str
    driver_evidence_nonce_sha256: str
    ciphertext_sha256: str
    ciphertext_octets_received: int
    observed_at: datetime
    observed_monotonic_ns: int

    def __post_init__(self) -> None:
        for name in (
            "local_shutdown_command_started_event_id",
            "owner_evidence_id",
            "driver_evidence_id",
            "kernel_socket_identity",
            "driver_evidence_nonce_sha256",
            "ciphertext_sha256",
        ):
            object.__setattr__(
                self,
                name,
                canonical_hash(getattr(self, name), field=name),
            )
        object.__setattr__(
            self,
            "shutdown_deadline_monotonic_ns",
            canonical_safe_int(
                self.shutdown_deadline_monotonic_ns,
                field="shutdown_deadline_monotonic_ns",
                minimum=1,
            ),
        )
        object.__setattr__(
            self,
            "failure_kind",
            _enum(
                self.failure_kind,
                TerminalIngressFailureKindV49E,
                field="failure_kind",
            ),
        )
        operation = canonical_identifier(self.operation, field="operation", maximum=64)
        if operation != "TERMINAL_CLOSE_INGRESS":
            raise CanonicalizationError(
                "terminal ingress evidence requires exact owner operation"
            )
        object.__setattr__(self, "operation", operation)
        object.__setattr__(
            self,
            "ciphertext_octets_received",
            canonical_safe_int(
                self.ciphertext_octets_received,
                field="ciphertext_octets_received",
                minimum=1,
                maximum=V49C_MAX_TLS_CIPHERTEXT_OCTETS,
            ),
        )
        expected_driver_evidence_id = (
            _derive_driver_deadline_after_progress_evidence_id_v49e(
                driver_evidence_nonce_sha256=(self.driver_evidence_nonce_sha256),
                operation=operation,
                deadline_ns=self.shutdown_deadline_monotonic_ns,
                ciphertext_octets_received=self.ciphertext_octets_received,
                ciphertext_sha256=self.ciphertext_sha256,
            )
        )
        if self.driver_evidence_id != expected_driver_evidence_id:
            raise CanonicalizationError(
                "terminal ingress driver evidence ID differs from exact fields"
            )
        object.__setattr__(
            self,
            "observed_at",
            utc_datetime(self.observed_at, field="observed_at"),
        )
        object.__setattr__(
            self,
            "observed_monotonic_ns",
            canonical_safe_int(
                self.observed_monotonic_ns,
                field="observed_monotonic_ns",
                minimum=0,
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if name == "observed_at":
                value = utc_iso(value)
            elif name == "failure_kind":
                value = value.value
            result[name] = value
        return result

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> TerminalIngressFailurePayloadV49E:
        require_exact_keys(
            payload,
            expected=set(cls.__dataclass_fields__),
            context=cls.__name__,
        )
        return cls(**dict(payload))


@dataclass(frozen=True, slots=True, kw_only=True)
class TlsProtocolOperationStartedPayloadV49E:
    """Write-ahead authority for exactly one retained TLS-driver operation."""

    operation_sequence: int
    tls_operation_id: str
    local_shutdown_command_started_event_id: str
    purpose: TlsProtocolOperationPurposeV49E
    cause_actor_event_id: str
    driver_evidence_nonce_sha256: str
    started_at: datetime
    started_monotonic_ns: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "operation_sequence",
            canonical_safe_int(
                self.operation_sequence,
                field="operation_sequence",
                minimum=1,
            ),
        )
        for name in (
            "tls_operation_id",
            "local_shutdown_command_started_event_id",
            "cause_actor_event_id",
            "driver_evidence_nonce_sha256",
        ):
            object.__setattr__(
                self, name, canonical_hash(getattr(self, name), field=name)
            )
        object.__setattr__(
            self,
            "purpose",
            _enum(self.purpose, TlsProtocolOperationPurposeV49E, field="purpose"),
        )
        object.__setattr__(
            self,
            "started_at",
            utc_datetime(self.started_at, field="started_at"),
        )
        object.__setattr__(
            self,
            "started_monotonic_ns",
            canonical_safe_int(
                self.started_monotonic_ns,
                field="started_monotonic_ns",
                minimum=0,
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "cause_actor_event_id": self.cause_actor_event_id,
            "driver_evidence_nonce_sha256": self.driver_evidence_nonce_sha256,
            "local_shutdown_command_started_event_id": (
                self.local_shutdown_command_started_event_id
            ),
            "operation_sequence": self.operation_sequence,
            "purpose": self.purpose.value,
            "started_at": utc_iso(self.started_at),
            "started_monotonic_ns": self.started_monotonic_ns,
            "tls_operation_id": self.tls_operation_id,
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> TlsProtocolOperationStartedPayloadV49E:
        require_exact_keys(
            payload, expected=set(cls.__dataclass_fields__), context=cls.__name__
        )
        return cls(**dict(payload))


@dataclass(frozen=True, slots=True, kw_only=True)
class TlsProtocolOperationFailedPayloadV49E:
    """Physical TLS failure plus its independent actor-clock classification."""

    tls_protocol_operation_started_event_id: str
    tls_operation_id: str
    purpose: TlsProtocolOperationPurposeV49E
    driver_evidence_nonce_sha256: str
    failure_kind: TlsProtocolOperationFailureKindV49E
    deadline_classification: LocalShutdownDeadlineClassificationV49E | None
    shutdown_deadline_monotonic_ns: int
    unsendable_driver_output_sequence: int | None
    unsendable_driver_evidence_id: str | None
    unsendable_owner_evidence_id: str | None
    unsendable_kernel_socket_identity: str | None
    unsendable_ciphertext_sha256: str | None
    unsendable_ciphertext_octets: int | None
    deadline_no_observation_owner_evidence_id: str | None
    deadline_no_observation_kernel_socket_identity: str | None
    deadline_no_observation_operation: str | None
    deadline_after_progress_owner_evidence_id: str | None
    deadline_after_progress_driver_evidence_id: str | None
    deadline_after_progress_kernel_socket_identity: str | None
    deadline_after_progress_operation: str | None
    deadline_after_progress_ciphertext_sha256: str | None
    deadline_after_progress_ciphertext_octets: int | None
    observed_at: datetime
    observed_monotonic_ns: int

    def __post_init__(self) -> None:
        for name in (
            "tls_protocol_operation_started_event_id",
            "tls_operation_id",
            "driver_evidence_nonce_sha256",
        ):
            object.__setattr__(
                self, name, canonical_hash(getattr(self, name), field=name)
            )
        purpose = _enum(self.purpose, TlsProtocolOperationPurposeV49E, field="purpose")
        failure_kind = _enum(
            self.failure_kind,
            TlsProtocolOperationFailureKindV49E,
            field="failure_kind",
        )
        deadline_failure = failure_kind in {
            TlsProtocolOperationFailureKindV49E.DEADLINE_EXPIRED_NO_OBSERVATION,
            TlsProtocolOperationFailureKindV49E.DEADLINE_EXPIRED_AFTER_PROGRESS,
        }
        deadline_classification = (
            None
            if self.deadline_classification is None
            else _enum(
                self.deadline_classification,
                LocalShutdownDeadlineClassificationV49E,
                field="deadline_classification",
            )
        )
        if deadline_failure != (deadline_classification is not None):
            raise CanonicalizationError(
                "only physical TLS deadline failures carry actor clock classification"
            )
        shutdown_deadline_ns = canonical_safe_int(
            self.shutdown_deadline_monotonic_ns,
            field="shutdown_deadline_monotonic_ns",
            minimum=1,
        )
        digest = _optional_hash(
            self.unsendable_ciphertext_sha256,
            field="unsendable_ciphertext_sha256",
        )
        unsendable_hash_names = (
            "unsendable_driver_evidence_id",
            "unsendable_owner_evidence_id",
            "unsendable_kernel_socket_identity",
        )
        unsendable_hashes = tuple(
            _optional_hash(getattr(self, name), field=name)
            for name in unsendable_hash_names
        )
        output_sequence = (
            None
            if self.unsendable_driver_output_sequence is None
            else canonical_safe_int(
                self.unsendable_driver_output_sequence,
                field="unsendable_driver_output_sequence",
                minimum=1,
            )
        )
        octets = (
            None
            if self.unsendable_ciphertext_octets is None
            else canonical_safe_int(
                self.unsendable_ciphertext_octets,
                field="unsendable_ciphertext_octets",
                minimum=1,
                maximum=V49C_MAX_TLS_CIPHERTEXT_OCTETS,
            )
        )
        unsendable = (
            failure_kind
            is TlsProtocolOperationFailureKindV49E.UNSENDABLE_POST_HANDSHAKE_OUTPUT_AFTER_SHUT_WR
        )
        if unsendable != (
            digest is not None
            and octets is not None
            and output_sequence is not None
            and all(value is not None for value in unsendable_hashes)
        ):
            raise CanonicalizationError(
                "only unsendable post-handshake output carries nested owner evidence"
            )
        if (
            unsendable
            and purpose is not TlsProtocolOperationPurposeV49E.PEER_SHUTDOWN_POLL
        ):
            raise CanonicalizationError(
                "unsendable post-handshake output must result from shutdown polling"
            )
        if unsendable:
            expected_driver_id = sha256_digest(
                {
                    "domain": "RiskYieldMMUnsendableTlsPostHandshakeOutputV4_9E",
                    "output_sequence": output_sequence,
                    "driver_evidence_nonce_sha256": self.driver_evidence_nonce_sha256,
                    "ciphertext_sha256": digest,
                    "ciphertext_octets": octets,
                }
            )
            if unsendable_hashes[0] != expected_driver_id:
                raise CanonicalizationError(
                    "unsendable TLS driver evidence ID differs from exact fields"
                )
        no_observation_hash_names = (
            "deadline_no_observation_owner_evidence_id",
            "deadline_no_observation_kernel_socket_identity",
        )
        no_observation_hashes = tuple(
            _optional_hash(getattr(self, name), field=name)
            for name in no_observation_hash_names
        )
        no_observation_operation = (
            None
            if self.deadline_no_observation_operation is None
            else canonical_identifier(
                self.deadline_no_observation_operation,
                field="deadline_no_observation_operation",
                maximum=64,
            )
        )
        no_observation = (
            failure_kind
            is TlsProtocolOperationFailureKindV49E.DEADLINE_EXPIRED_NO_OBSERVATION
        )
        expected_no_observation_operation = {
            TlsProtocolOperationPurposeV49E.LOCAL_CLOSE_NOTIFY: (
                "LOCAL_TLS_CLOSE_NOTIFY_PREPARATION"
            ),
            TlsProtocolOperationPurposeV49E.PEER_SHUTDOWN_POLL: "TLS_SHUTDOWN_POLL",
        }.get(purpose)
        if no_observation != (
            all(value is not None for value in no_observation_hashes)
            and expected_no_observation_operation is not None
            and no_observation_operation == expected_no_observation_operation
        ):
            raise CanonicalizationError(
                "only no-observation expiry carries exact owner deadline evidence"
            )
        if not no_observation and any(
            value is not None
            for value in (*no_observation_hashes, no_observation_operation)
        ):
            raise CanonicalizationError(
                "non-deadline TLS failures cannot carry no-observation evidence"
            )
        progress_hash_names = (
            "deadline_after_progress_owner_evidence_id",
            "deadline_after_progress_driver_evidence_id",
            "deadline_after_progress_kernel_socket_identity",
            "deadline_after_progress_ciphertext_sha256",
        )
        progress_hashes = tuple(
            _optional_hash(getattr(self, name), field=name)
            for name in progress_hash_names
        )
        progress_operation = (
            None
            if self.deadline_after_progress_operation is None
            else canonical_identifier(
                self.deadline_after_progress_operation,
                field="deadline_after_progress_operation",
                maximum=64,
            )
        )
        progress_octets = (
            None
            if self.deadline_after_progress_ciphertext_octets is None
            else canonical_safe_int(
                self.deadline_after_progress_ciphertext_octets,
                field="deadline_after_progress_ciphertext_octets",
                minimum=1,
                maximum=V49C_MAX_TLS_CIPHERTEXT_OCTETS,
            )
        )
        after_progress = (
            failure_kind
            is TlsProtocolOperationFailureKindV49E.DEADLINE_EXPIRED_AFTER_PROGRESS
        )
        if after_progress != (
            all(value is not None for value in progress_hashes)
            and progress_octets is not None
            and progress_operation == "TLS_SHUTDOWN_POLL"
        ):
            raise CanonicalizationError(
                "only deadline-after-progress carries sealed positive evidence"
            )
        if not after_progress and any(
            value is not None
            for value in (*progress_hashes, progress_operation, progress_octets)
        ):
            raise CanonicalizationError(
                "other TLS failures cannot carry deadline-after-progress evidence"
            )
        if after_progress and (
            purpose is not TlsProtocolOperationPurposeV49E.PEER_SHUTDOWN_POLL
            or unsendable
        ):
            raise CanonicalizationError(
                "deadline-after-progress must result from one shutdown poll"
            )
        if after_progress:
            expected_driver_evidence_id = (
                _derive_driver_deadline_after_progress_evidence_id_v49e(
                    driver_evidence_nonce_sha256=(self.driver_evidence_nonce_sha256),
                    operation=progress_operation,
                    deadline_ns=shutdown_deadline_ns,
                    ciphertext_octets_received=progress_octets,
                    ciphertext_sha256=progress_hashes[3],
                )
            )
            if progress_hashes[1] != expected_driver_evidence_id:
                raise CanonicalizationError(
                    "TLS after-progress driver evidence ID differs from exact fields"
                )
        object.__setattr__(self, "purpose", purpose)
        object.__setattr__(self, "failure_kind", failure_kind)
        object.__setattr__(
            self,
            "deadline_classification",
            deadline_classification,
        )
        object.__setattr__(
            self,
            "shutdown_deadline_monotonic_ns",
            shutdown_deadline_ns,
        )
        object.__setattr__(self, "unsendable_ciphertext_sha256", digest)
        object.__setattr__(self, "unsendable_ciphertext_octets", octets)
        object.__setattr__(
            self,
            "unsendable_driver_output_sequence",
            output_sequence,
        )
        for name, value in zip(unsendable_hash_names, unsendable_hashes):
            object.__setattr__(self, name, value)
        for name, value in zip(no_observation_hash_names, no_observation_hashes):
            object.__setattr__(self, name, value)
        object.__setattr__(
            self,
            "deadline_no_observation_operation",
            no_observation_operation,
        )
        for name, value in zip(progress_hash_names, progress_hashes):
            object.__setattr__(self, name, value)
        object.__setattr__(
            self,
            "deadline_after_progress_operation",
            progress_operation,
        )
        object.__setattr__(
            self,
            "deadline_after_progress_ciphertext_octets",
            progress_octets,
        )
        object.__setattr__(
            self,
            "observed_at",
            utc_datetime(self.observed_at, field="observed_at"),
        )
        object.__setattr__(
            self,
            "observed_monotonic_ns",
            canonical_safe_int(
                self.observed_monotonic_ns,
                field="observed_monotonic_ns",
                minimum=0,
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "deadline_classification": (
                None
                if self.deadline_classification is None
                else self.deadline_classification.value
            ),
            "driver_evidence_nonce_sha256": self.driver_evidence_nonce_sha256,
            "failure_kind": self.failure_kind.value,
            "deadline_no_observation_kernel_socket_identity": (
                self.deadline_no_observation_kernel_socket_identity
            ),
            "deadline_no_observation_operation": (
                self.deadline_no_observation_operation
            ),
            "deadline_no_observation_owner_evidence_id": (
                self.deadline_no_observation_owner_evidence_id
            ),
            "deadline_after_progress_ciphertext_octets": (
                self.deadline_after_progress_ciphertext_octets
            ),
            "deadline_after_progress_ciphertext_sha256": (
                self.deadline_after_progress_ciphertext_sha256
            ),
            "deadline_after_progress_driver_evidence_id": (
                self.deadline_after_progress_driver_evidence_id
            ),
            "deadline_after_progress_kernel_socket_identity": (
                self.deadline_after_progress_kernel_socket_identity
            ),
            "deadline_after_progress_owner_evidence_id": (
                self.deadline_after_progress_owner_evidence_id
            ),
            "deadline_after_progress_operation": (
                self.deadline_after_progress_operation
            ),
            "observed_at": utc_iso(self.observed_at),
            "observed_monotonic_ns": self.observed_monotonic_ns,
            "purpose": self.purpose.value,
            "shutdown_deadline_monotonic_ns": (self.shutdown_deadline_monotonic_ns),
            "tls_operation_id": self.tls_operation_id,
            "tls_protocol_operation_started_event_id": (
                self.tls_protocol_operation_started_event_id
            ),
            "unsendable_driver_evidence_id": self.unsendable_driver_evidence_id,
            "unsendable_driver_output_sequence": (
                self.unsendable_driver_output_sequence
            ),
            "unsendable_kernel_socket_identity": (
                self.unsendable_kernel_socket_identity
            ),
            "unsendable_owner_evidence_id": self.unsendable_owner_evidence_id,
            "unsendable_ciphertext_octets": self.unsendable_ciphertext_octets,
            "unsendable_ciphertext_sha256": self.unsendable_ciphertext_sha256,
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> TlsProtocolOperationFailedPayloadV49E:
        require_exact_keys(
            payload, expected=set(cls.__dataclass_fields__), context=cls.__name__
        )
        return cls(**dict(payload))


def classify_tls_protocol_operation_failure_v49e(
    payload: TlsProtocolOperationFailedPayloadV49E,
) -> tuple[TerminalTransitionKindV49C, str]:
    """Map preserved physical evidence and actor clocks to one terminal outcome."""

    if type(payload) is not TlsProtocolOperationFailedPayloadV49E:
        raise TypeError("payload must be exact TlsProtocolOperationFailedPayloadV49E")
    if payload.failure_kind in {
        TlsProtocolOperationFailureKindV49E.DEADLINE_EXPIRED_NO_OBSERVATION,
        TlsProtocolOperationFailureKindV49E.DEADLINE_EXPIRED_AFTER_PROGRESS,
    }:
        if (
            payload.deadline_classification
            is LocalShutdownDeadlineClassificationV49E.CLOCK_DISAGREEMENT
        ):
            return (
                TerminalTransitionKindV49C.FATAL,
                V49E_LOCAL_SHUTDOWN_CLOCK_DISAGREEMENT_CAUSE,
            )
        if (
            payload.deadline_classification
            is LocalShutdownDeadlineClassificationV49E.OWNER_EVIDENCE_BEFORE_BOTH_CLOCKS
        ):
            return (
                TerminalTransitionKindV49C.FATAL,
                V49E_TLS_OPERATION_DRIVER_ERROR_CAUSE,
            )
        if (
            payload.deadline_classification
            is not LocalShutdownDeadlineClassificationV49E.BOTH_DUE
        ):  # pragma: no cover - payload constructor closes this state
            raise CanonicalizationError(
                "TLS deadline failure lacks exact actor clock classification"
            )
        if (
            payload.failure_kind
            is TlsProtocolOperationFailureKindV49E.DEADLINE_EXPIRED_NO_OBSERVATION
        ):
            return (
                TerminalTransitionKindV49C.TIMEOUT,
                V49E_TLS_SHUTDOWN_DEADLINE_EXPIRED_CAUSE,
            )
        return (
            TerminalTransitionKindV49C.TIMEOUT,
            V49E_TLS_SHUTDOWN_DEADLINE_EXPIRED_AFTER_PROGRESS_CAUSE,
        )
    if payload.failure_kind is TlsProtocolOperationFailureKindV49E.DRIVER_ERROR:
        return (
            TerminalTransitionKindV49C.FATAL,
            V49E_TLS_OPERATION_DRIVER_ERROR_CAUSE,
        )
    if (
        payload.failure_kind
        is TlsProtocolOperationFailureKindV49E.UNSENDABLE_POST_HANDSHAKE_OUTPUT_AFTER_SHUT_WR
    ):
        return (
            TerminalTransitionKindV49C.FATAL,
            V49E_TLS_POST_HANDSHAKE_OUTPUT_AFTER_SHUT_WR_CAUSE,
        )
    raise CanonicalizationError("unsupported TLS protocol failure kind")


@dataclass(frozen=True, slots=True, kw_only=True)
class TlsControlCiphertextPreparedPayloadV49E:
    """Exact retained control ciphertext produced by one started TLS operation."""

    tls_protocol_operation_started_event_id: str
    tls_operation_id: str
    control_sequence: int
    control_kind: TlsControlOutputKindV49E
    driver_evidence_nonce_sha256: str
    ordered_ciphertext_chunks_base64: tuple[str, ...]
    ordered_ciphertext_chunks_sha256: tuple[str, ...]
    ciphertext_batch_sha256: str
    ciphertext_octets: int
    peer_close_notify_received_during_preparation: bool
    prepared_at: datetime
    prepared_monotonic_ns: int

    def __post_init__(self) -> None:
        for name in (
            "tls_protocol_operation_started_event_id",
            "tls_operation_id",
            "driver_evidence_nonce_sha256",
            "ciphertext_batch_sha256",
        ):
            object.__setattr__(
                self, name, canonical_hash(getattr(self, name), field=name)
            )
        object.__setattr__(
            self,
            "control_sequence",
            canonical_safe_int(
                self.control_sequence, field="control_sequence", minimum=1
            ),
        )
        object.__setattr__(
            self,
            "control_kind",
            _enum(self.control_kind, TlsControlOutputKindV49E, field="control_kind"),
        )
        encoded, chunks = _base64_chunks(
            self.ordered_ciphertext_chunks_base64,
            field="ordered_ciphertext_chunks_base64",
            allow_empty=False,
            maximum_items=V49C_MAX_TLS_CIPHERTEXT_CHUNKS,
            maximum_octets=V49C_MAX_TLS_CIPHERTEXT_OCTETS,
        )
        hashes = _hashes(
            self.ordered_ciphertext_chunks_sha256,
            field="ordered_ciphertext_chunks_sha256",
            allow_empty=False,
            maximum=V49C_MAX_TLS_CIPHERTEXT_CHUNKS,
        )
        if hashes != tuple(hashlib.sha256(chunk).hexdigest() for chunk in chunks):
            raise CanonicalizationError(
                "TLS-control ciphertext hashes differ from exact bytes"
            )
        octets = canonical_safe_int(
            self.ciphertext_octets, field="ciphertext_octets", minimum=1
        )
        if octets != sum(map(len, chunks)):
            raise CanonicalizationError(
                "TLS-control ciphertext_octets differs from exact chunks"
            )
        if self.ciphertext_batch_sha256 != _ordered_batch_sha256(
            _ORDERED_TLS_CONTROL_CIPHERTEXT_DOMAIN, encoded
        ):
            raise CanonicalizationError(
                "TLS-control ciphertext batch hash differs from chunks"
            )
        peer_during_preparation = _strict_bool(
            self.peer_close_notify_received_during_preparation,
            field="peer_close_notify_received_during_preparation",
        )
        if (
            self.control_kind is TlsControlOutputKindV49E.OPAQUE_POST_HANDSHAKE_RESPONSE
            and peer_during_preparation
        ):
            raise CanonicalizationError(
                "opaque TLS output cannot claim a peer close observation"
            )
        object.__setattr__(self, "ordered_ciphertext_chunks_base64", encoded)
        object.__setattr__(self, "ordered_ciphertext_chunks_sha256", hashes)
        object.__setattr__(self, "ciphertext_octets", octets)
        object.__setattr__(
            self,
            "peer_close_notify_received_during_preparation",
            peer_during_preparation,
        )
        object.__setattr__(
            self,
            "prepared_at",
            utc_datetime(self.prepared_at, field="prepared_at"),
        )
        object.__setattr__(
            self,
            "prepared_monotonic_ns",
            canonical_safe_int(
                self.prepared_monotonic_ns,
                field="prepared_monotonic_ns",
                minimum=0,
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "ciphertext_batch_sha256": self.ciphertext_batch_sha256,
            "ciphertext_octets": self.ciphertext_octets,
            "control_kind": self.control_kind.value,
            "control_sequence": self.control_sequence,
            "driver_evidence_nonce_sha256": self.driver_evidence_nonce_sha256,
            "ordered_ciphertext_chunks_base64": list(
                self.ordered_ciphertext_chunks_base64
            ),
            "ordered_ciphertext_chunks_sha256": list(
                self.ordered_ciphertext_chunks_sha256
            ),
            "peer_close_notify_received_during_preparation": (
                self.peer_close_notify_received_during_preparation
            ),
            "prepared_at": utc_iso(self.prepared_at),
            "prepared_monotonic_ns": self.prepared_monotonic_ns,
            "tls_operation_id": self.tls_operation_id,
            "tls_protocol_operation_started_event_id": (
                self.tls_protocol_operation_started_event_id
            ),
        }

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> TlsControlCiphertextPreparedPayloadV49E:
        expected = set(cls.__dataclass_fields__)
        require_exact_keys(payload, expected=expected, context=cls.__name__)
        return cls(
            **{
                name: payload[name]
                for name in expected
                if name
                not in {
                    "ordered_ciphertext_chunks_base64",
                    "ordered_ciphertext_chunks_sha256",
                }
            },
            ordered_ciphertext_chunks_base64=tuple(
                payload["ordered_ciphertext_chunks_base64"]
            ),
            ordered_ciphertext_chunks_sha256=tuple(
                payload["ordered_ciphertext_chunks_sha256"]
            ),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class TlsControlKernelSendAttemptPayloadV49E:
    """Write-ahead declaration of one bounded TLS-control ``socket.send``."""

    tls_control_ciphertext_prepared_event_id: str
    local_shutdown_command_started_event_id: str
    shutdown_deadline_monotonic_ns: int
    kernel_attempt_ordinal: int
    ciphertext_batch_sha256: str
    ciphertext_octets: int
    ciphertext_start_octet: int
    requested_octets: int
    attempted_at: datetime
    attempted_monotonic_ns: int

    def __post_init__(self) -> None:
        for name in (
            "tls_control_ciphertext_prepared_event_id",
            "local_shutdown_command_started_event_id",
            "ciphertext_batch_sha256",
        ):
            object.__setattr__(
                self, name, canonical_hash(getattr(self, name), field=name)
            )
        ordinal = canonical_safe_int(
            self.kernel_attempt_ordinal,
            field="kernel_attempt_ordinal",
            minimum=1,
        )
        total = canonical_safe_int(
            self.ciphertext_octets, field="ciphertext_octets", minimum=1
        )
        start = canonical_safe_int(
            self.ciphertext_start_octet,
            field="ciphertext_start_octet",
            minimum=0,
        )
        requested = canonical_safe_int(
            self.requested_octets, field="requested_octets", minimum=1
        )
        if start >= total or start + requested > total:
            raise CanonicalizationError(
                "TLS-control kernel send request exceeds ciphertext range"
            )
        object.__setattr__(self, "kernel_attempt_ordinal", ordinal)
        object.__setattr__(self, "ciphertext_octets", total)
        object.__setattr__(self, "ciphertext_start_octet", start)
        object.__setattr__(self, "requested_octets", requested)
        deadline_ns = canonical_safe_int(
            self.shutdown_deadline_monotonic_ns,
            field="shutdown_deadline_monotonic_ns",
            minimum=1,
        )
        attempted_ns = canonical_safe_int(
            self.attempted_monotonic_ns,
            field="attempted_monotonic_ns",
            minimum=0,
        )
        if attempted_ns >= deadline_ns:
            raise CanonicalizationError(
                "TLS-control send authorization must precede shutdown deadline"
            )
        object.__setattr__(self, "shutdown_deadline_monotonic_ns", deadline_ns)
        object.__setattr__(
            self,
            "attempted_at",
            utc_datetime(self.attempted_at, field="attempted_at"),
        )
        object.__setattr__(
            self,
            "attempted_monotonic_ns",
            attempted_ns,
        )

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            result[name] = utc_iso(value) if name == "attempted_at" else value
        return result

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> TlsControlKernelSendAttemptPayloadV49E:
        require_exact_keys(
            payload, expected=set(cls.__dataclass_fields__), context=cls.__name__
        )
        return cls(**dict(payload))


@dataclass(frozen=True, slots=True, kw_only=True)
class TlsControlKernelSendResultPayloadV49E:
    """Exact positive local-kernel result for one control send attempt."""

    tls_control_kernel_send_attempt_event_id: str
    tls_control_ciphertext_prepared_event_id: str
    kernel_attempt_ordinal: int
    ciphertext_batch_sha256: str
    ciphertext_octets: int
    ciphertext_start_octet: int
    requested_octets: int
    accepted_octets: int
    resulting_ciphertext_offset: int
    observed_at: datetime
    observed_monotonic_ns: int

    def __post_init__(self) -> None:
        for name in (
            "tls_control_kernel_send_attempt_event_id",
            "tls_control_ciphertext_prepared_event_id",
            "ciphertext_batch_sha256",
        ):
            object.__setattr__(
                self, name, canonical_hash(getattr(self, name), field=name)
            )
        ordinal = canonical_safe_int(
            self.kernel_attempt_ordinal,
            field="kernel_attempt_ordinal",
            minimum=1,
        )
        total = canonical_safe_int(
            self.ciphertext_octets, field="ciphertext_octets", minimum=1
        )
        start = canonical_safe_int(
            self.ciphertext_start_octet,
            field="ciphertext_start_octet",
            minimum=0,
        )
        requested = canonical_safe_int(
            self.requested_octets, field="requested_octets", minimum=1
        )
        accepted = canonical_safe_int(
            self.accepted_octets, field="accepted_octets", minimum=1
        )
        resulting = canonical_safe_int(
            self.resulting_ciphertext_offset,
            field="resulting_ciphertext_offset",
            minimum=1,
        )
        if accepted > requested or resulting != start + accepted or resulting > total:
            raise CanonicalizationError(
                "TLS-control kernel result has an invalid positive count"
            )
        object.__setattr__(self, "kernel_attempt_ordinal", ordinal)
        object.__setattr__(self, "ciphertext_octets", total)
        object.__setattr__(self, "ciphertext_start_octet", start)
        object.__setattr__(self, "requested_octets", requested)
        object.__setattr__(self, "accepted_octets", accepted)
        object.__setattr__(self, "resulting_ciphertext_offset", resulting)
        object.__setattr__(
            self,
            "observed_at",
            utc_datetime(self.observed_at, field="observed_at"),
        )
        object.__setattr__(
            self,
            "observed_monotonic_ns",
            canonical_safe_int(
                self.observed_monotonic_ns,
                field="observed_monotonic_ns",
                minimum=0,
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            result[name] = utc_iso(value) if name == "observed_at" else value
        return result

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, Any]
    ) -> TlsControlKernelSendResultPayloadV49E:
        require_exact_keys(
            payload, expected=set(cls.__dataclass_fields__), context=cls.__name__
        )
        return cls(**dict(payload))


@dataclass(frozen=True, slots=True, kw_only=True)
class TlsControlKernelSendFailurePayloadV49E:
    """Conclusive zero-acceptance result for one TLS-control send attempt."""

    tls_control_kernel_send_attempt_event_id: str
    tls_control_ciphertext_prepared_event_id: str
    local_shutdown_command_started_event_id: str
    shutdown_deadline_monotonic_ns: int
    kernel_attempt_ordinal: int
    ciphertext_batch_sha256: str
    ciphertext_octets: int
    ciphertext_start_octet: int
    requested_octets: int
    failure_kind: KernelSendFailureKindV49E
    owner_evidence_id: str | None
    kernel_socket_identity: str | None
    driver_evidence_nonce_sha256: str | None
    owner_deadline_operation: str | None
    send_kind: str | None
    transport_sequence: int | None
    exact_slice_sha256: str | None
    would_block_count: int | None
    driver_evidence_id: str | None
    observed_at: datetime
    observed_monotonic_ns: int

    def __post_init__(self) -> None:
        for name in (
            "tls_control_kernel_send_attempt_event_id",
            "tls_control_ciphertext_prepared_event_id",
            "local_shutdown_command_started_event_id",
            "ciphertext_batch_sha256",
        ):
            object.__setattr__(
                self,
                name,
                canonical_hash(getattr(self, name), field=name),
            )
        object.__setattr__(
            self,
            "shutdown_deadline_monotonic_ns",
            canonical_safe_int(
                self.shutdown_deadline_monotonic_ns,
                field="shutdown_deadline_monotonic_ns",
                minimum=1,
            ),
        )
        for name in (
            "kernel_attempt_ordinal",
            "ciphertext_octets",
            "requested_octets",
        ):
            object.__setattr__(
                self,
                name,
                canonical_safe_int(getattr(self, name), field=name, minimum=1),
            )
        object.__setattr__(
            self,
            "ciphertext_start_octet",
            canonical_safe_int(
                self.ciphertext_start_octet,
                field="ciphertext_start_octet",
                minimum=0,
            ),
        )
        if (
            self.ciphertext_start_octet >= self.ciphertext_octets
            or self.ciphertext_start_octet + self.requested_octets
            > self.ciphertext_octets
        ):
            raise CanonicalizationError(
                "TLS-control failure differs from its requested range"
            )
        failure_kind = _enum(
            self.failure_kind,
            KernelSendFailureKindV49E,
            field="failure_kind",
        )
        evidence_hash_names = (
            "owner_evidence_id",
            "kernel_socket_identity",
            "driver_evidence_nonce_sha256",
            "exact_slice_sha256",
            "driver_evidence_id",
        )
        evidence_hashes = tuple(
            _optional_hash(getattr(self, name), field=name)
            for name in evidence_hash_names
        )
        owner_deadline_operation = (
            None
            if self.owner_deadline_operation is None
            else canonical_identifier(
                self.owner_deadline_operation,
                field="owner_deadline_operation",
                maximum=64,
            )
        )
        send_kind = (
            None
            if self.send_kind is None
            else canonical_identifier(self.send_kind, field="send_kind", maximum=64)
        )
        transport_sequence = (
            None
            if self.transport_sequence is None
            else canonical_safe_int(
                self.transport_sequence,
                field="transport_sequence",
                minimum=1,
            )
        )
        would_block_count = (
            None
            if self.would_block_count is None
            else canonical_safe_int(
                self.would_block_count,
                field="would_block_count",
                minimum=1,
            )
        )
        owner_before_syscall = (
            failure_kind is KernelSendFailureKindV49E.DEADLINE_EXPIRED_BEFORE_SYSCALL
        )
        sealed_no_acceptance = (
            failure_kind
            is KernelSendFailureKindV49E.DEADLINE_EXPIRED_NO_KERNEL_ACCEPTANCE
        )
        owner_common_evidence = all(value is not None for value in evidence_hashes[:3])
        complete_no_acceptance_evidence = (
            all(value is not None for value in evidence_hashes)
            and send_kind is not None
            and transport_sequence is not None
            and would_block_count is not None
            and owner_deadline_operation is None
        )
        complete_before_syscall_evidence = (
            owner_common_evidence
            and owner_deadline_operation == "TLS_CONTROL_SEND_BEFORE_SYSCALL"
            and all(value is None for value in evidence_hashes[3:])
            and send_kind is None
            and transport_sequence is None
            and would_block_count is None
        )
        actor_without_owner_evidence = failure_kind in {
            KernelSendFailureKindV49E.DEADLINE_EXPIRED_BEFORE_CALLBACK,
            KernelSendFailureKindV49E.CLOCK_DISAGREEMENT,
        }
        if sealed_no_acceptance != complete_no_acceptance_evidence:
            raise CanonicalizationError(
                "only sealed TLS no-acceptance carries owner evidence"
            )
        if owner_before_syscall != complete_before_syscall_evidence:
            raise CanonicalizationError(
                "TLS owner pre-syscall expiry requires exact no-observation evidence"
            )
        if actor_without_owner_evidence and any(
            value is not None
            for value in (
                *evidence_hashes,
                owner_deadline_operation,
                send_kind,
                transport_sequence,
                would_block_count,
            )
        ):
            raise CanonicalizationError(
                "actor-proven TLS pre-callback expiry cannot carry owner evidence"
            )
        if sealed_no_acceptance and send_kind != "TLS_CONTROL":
            raise CanonicalizationError(
                "TLS-control failure requires exact TLS_CONTROL owner evidence"
            )
        if sealed_no_acceptance:
            expected_driver_evidence_id = _derive_driver_send_deadline_evidence_id_v49e(
                driver_evidence_nonce_sha256=evidence_hashes[2],
                send_kind=send_kind,
                transport_sequence=transport_sequence,
                ciphertext_batch_sha256=self.ciphertext_batch_sha256,
                ciphertext_octets=self.ciphertext_octets,
                ciphertext_start_octet=self.ciphertext_start_octet,
                requested_octets=self.requested_octets,
                exact_slice_sha256=evidence_hashes[3],
                deadline_ns=self.shutdown_deadline_monotonic_ns,
                would_block_count=would_block_count,
            )
            if evidence_hashes[4] != expected_driver_evidence_id:
                raise CanonicalizationError(
                    "TLS-control driver evidence ID differs from exact fields"
                )
        object.__setattr__(self, "failure_kind", failure_kind)
        for name, value in zip(evidence_hash_names, evidence_hashes):
            object.__setattr__(self, name, value)
        object.__setattr__(
            self,
            "owner_deadline_operation",
            owner_deadline_operation,
        )
        object.__setattr__(self, "send_kind", send_kind)
        object.__setattr__(self, "transport_sequence", transport_sequence)
        object.__setattr__(self, "would_block_count", would_block_count)
        object.__setattr__(
            self,
            "observed_at",
            utc_datetime(self.observed_at, field="observed_at"),
        )
        object.__setattr__(
            self,
            "observed_monotonic_ns",
            canonical_safe_int(
                self.observed_monotonic_ns,
                field="observed_monotonic_ns",
                minimum=0,
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if name == "observed_at":
                value = utc_iso(value)
            elif name == "failure_kind":
                value = value.value
            result[name] = value
        return result

    @classmethod
    def from_mapping(
        cls,
        payload: Mapping[str, Any],
    ) -> TlsControlKernelSendFailurePayloadV49E:
        require_exact_keys(
            payload,
            expected=set(cls.__dataclass_fields__),
            context=cls.__name__,
        )
        return cls(**dict(payload))


@dataclass(frozen=True, slots=True, kw_only=True)
class TlsShutdownObservedPayloadV49E:
    """Exact sealed-driver shutdown observation produced by one started poll."""

    tls_protocol_operation_started_event_id: str
    tls_operation_id: str
    observation_sequence: int
    observation_kind: TlsShutdownObservationKindV49E
    driver_evidence_nonce_sha256: str
    peer_close_notify_received: bool
    tcp_eof_received: bool
    truncated: bool
    ciphertext_octets_received: int
    observation_id: str
    owner_observation_id: str
    owner_kernel_socket_identity: str
    observed_at: datetime
    observed_monotonic_ns: int

    def __post_init__(self) -> None:
        for name in (
            "tls_protocol_operation_started_event_id",
            "tls_operation_id",
            "driver_evidence_nonce_sha256",
            "observation_id",
        ):
            object.__setattr__(
                self, name, canonical_hash(getattr(self, name), field=name)
            )
        owner_observation_id = canonical_hash(
            self.owner_observation_id, field="owner_observation_id"
        )
        owner_kernel_socket_identity = canonical_hash(
            self.owner_kernel_socket_identity,
            field="owner_kernel_socket_identity",
        )
        sequence = canonical_safe_int(
            self.observation_sequence,
            field="observation_sequence",
            minimum=1,
        )
        kind = _enum(
            self.observation_kind,
            TlsShutdownObservationKindV49E,
            field="observation_kind",
        )
        peer = _strict_bool(
            self.peer_close_notify_received, field="peer_close_notify_received"
        )
        eof = _strict_bool(self.tcp_eof_received, field="tcp_eof_received")
        truncated = _strict_bool(self.truncated, field="truncated")
        octets = canonical_safe_int(
            self.ciphertext_octets_received,
            field="ciphertext_octets_received",
            minimum=0,
        )
        if kind is TlsShutdownObservationKindV49E.PEER_CLOSE_NOTIFY:
            if not peer or eof or truncated:
                raise CanonicalizationError(
                    "peer close_notify observation has inconsistent evidence"
                )
        elif not eof or truncated != (not peer):
            raise CanonicalizationError(
                "TCP EOF observation lacks distinct owner/socket evidence"
            )
        if owner_observation_id == self.observation_id:
            raise CanonicalizationError(
                "TLS shutdown observation lacks distinct owner evidence"
            )
        object.__setattr__(self, "owner_observation_id", owner_observation_id)
        object.__setattr__(
            self,
            "owner_kernel_socket_identity",
            owner_kernel_socket_identity,
        )
        object.__setattr__(self, "observation_sequence", sequence)
        object.__setattr__(self, "observation_kind", kind)
        object.__setattr__(self, "peer_close_notify_received", peer)
        object.__setattr__(self, "tcp_eof_received", eof)
        object.__setattr__(self, "truncated", truncated)
        object.__setattr__(self, "ciphertext_octets_received", octets)
        object.__setattr__(
            self,
            "observed_at",
            utc_datetime(self.observed_at, field="observed_at"),
        )
        object.__setattr__(
            self,
            "observed_monotonic_ns",
            canonical_safe_int(
                self.observed_monotonic_ns,
                field="observed_monotonic_ns",
                minimum=0,
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if name == "observed_at":
                value = utc_iso(value)
            elif name == "observation_kind":
                value = value.value
            result[name] = value
        return result

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> TlsShutdownObservedPayloadV49E:
        require_exact_keys(
            payload, expected=set(cls.__dataclass_fields__), context=cls.__name__
        )
        return cls(**dict(payload))


@dataclass(frozen=True, slots=True, kw_only=True)
class TcpHalfCloseAttemptPayloadV49E:
    """Durable one-shot owner token recorded before ``shutdown(SHUT_WR)``."""

    tls_close_notify_sent_event_id: str
    tls_control_ciphertext_prepared_event_id: str
    local_shutdown_command_started_event_id: str
    shutdown_token_id: str
    shutdown_deadline_monotonic_ns: int
    token_sequence: int
    tls_control_sequence: int
    tls_ciphertext_batch_sha256: str
    tls_ciphertext_octets: int
    shutdown_how: str
    attempted_at: datetime
    attempted_monotonic_ns: int

    def __post_init__(self) -> None:
        for name in (
            "tls_close_notify_sent_event_id",
            "tls_control_ciphertext_prepared_event_id",
            "local_shutdown_command_started_event_id",
            "shutdown_token_id",
            "tls_ciphertext_batch_sha256",
        ):
            object.__setattr__(
                self, name, canonical_hash(getattr(self, name), field=name)
            )
        for name in ("token_sequence", "tls_control_sequence"):
            object.__setattr__(
                self,
                name,
                canonical_safe_int(getattr(self, name), field=name, minimum=1),
            )
        object.__setattr__(
            self,
            "tls_ciphertext_octets",
            canonical_safe_int(
                self.tls_ciphertext_octets,
                field="tls_ciphertext_octets",
                minimum=1,
            ),
        )
        deadline_ns = canonical_safe_int(
            self.shutdown_deadline_monotonic_ns,
            field="shutdown_deadline_monotonic_ns",
            minimum=1,
        )
        shutdown_how = canonical_identifier(
            self.shutdown_how, field="shutdown_how", maximum=16
        )
        if shutdown_how != "SHUT_WR":
            raise CanonicalizationError("TCP half-close must be exact SHUT_WR")
        object.__setattr__(self, "shutdown_how", shutdown_how)
        object.__setattr__(
            self,
            "attempted_at",
            utc_datetime(self.attempted_at, field="attempted_at"),
        )
        attempted_ns = canonical_safe_int(
            self.attempted_monotonic_ns,
            field="attempted_monotonic_ns",
            minimum=0,
        )
        if attempted_ns >= deadline_ns:
            raise CanonicalizationError(
                "TCP half-close authorization must precede shutdown deadline"
            )
        object.__setattr__(self, "shutdown_deadline_monotonic_ns", deadline_ns)
        object.__setattr__(
            self,
            "attempted_monotonic_ns",
            attempted_ns,
        )

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            result[name] = utc_iso(value) if name == "attempted_at" else value
        return result

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> TcpHalfCloseAttemptPayloadV49E:
        require_exact_keys(
            payload, expected=set(cls.__dataclass_fields__), context=cls.__name__
        )
        return cls(**dict(payload))


@dataclass(frozen=True, slots=True, kw_only=True)
class TcpHalfCloseResultPayloadV49E:
    """Exact result of the one-shot owner-bound write-half-close syscall."""

    tcp_half_close_attempt_event_id: str
    shutdown_token_id: str
    shutdown_result_id: str
    shutdown_how: str
    result_kind: TcpHalfCloseResultKindV49E
    error_code: str | None
    observed_at: datetime
    observed_monotonic_ns: int

    def __post_init__(self) -> None:
        for name in (
            "tcp_half_close_attempt_event_id",
            "shutdown_token_id",
            "shutdown_result_id",
        ):
            object.__setattr__(
                self, name, canonical_hash(getattr(self, name), field=name)
            )
        shutdown_how = canonical_identifier(
            self.shutdown_how, field="shutdown_how", maximum=16
        )
        if shutdown_how != "SHUT_WR":
            raise CanonicalizationError("TCP half-close result must be exact SHUT_WR")
        result_kind = _enum(
            self.result_kind,
            TcpHalfCloseResultKindV49E,
            field="result_kind",
        )
        error_code = (
            None
            if self.error_code is None
            else canonical_identifier(self.error_code, field="error_code", maximum=128)
        )
        if (result_kind is TcpHalfCloseResultKindV49E.KERNEL_ACCEPTED) != (
            error_code is None
        ):
            raise CanonicalizationError(
                "TCP half-close success and error evidence are inconsistent"
            )
        deadline_expired = error_code == "DEADLINE_EXPIRED_BEFORE_SYSCALL"
        if (
            result_kind
            in {
                TcpHalfCloseResultKindV49E.DEADLINE_EXPIRED_BEFORE_SYSCALL,
                TcpHalfCloseResultKindV49E.CLOCK_DISAGREEMENT,
            }
        ) != deadline_expired and not (
            result_kind is TcpHalfCloseResultKindV49E.ERROR and deadline_expired
        ):
            raise CanonicalizationError(
                "TCP half-close deadline kind requires its exact owner error code"
            )
        if error_code is not None and error_code not in _V49E_LINUX_SHUT_WR_ERROR_CODES:
            raise CanonicalizationError(
                "TCP half-close error_code is outside the Linux owner vocabulary"
            )
        object.__setattr__(self, "shutdown_how", shutdown_how)
        object.__setattr__(self, "result_kind", result_kind)
        object.__setattr__(self, "error_code", error_code)
        object.__setattr__(
            self,
            "observed_at",
            utc_datetime(self.observed_at, field="observed_at"),
        )
        object.__setattr__(
            self,
            "observed_monotonic_ns",
            canonical_safe_int(
                self.observed_monotonic_ns,
                field="observed_monotonic_ns",
                minimum=0,
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if name == "observed_at":
                value = utc_iso(value)
            elif name == "result_kind":
                value = value.value
            result[name] = value
        return result

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> TcpHalfCloseResultPayloadV49E:
        require_exact_keys(
            payload, expected=set(cls.__dataclass_fields__), context=cls.__name__
        )
        return cls(**dict(payload))


ActorPayloadV49C: TypeAlias = (
    RawIngressCommittedPayloadV49C
    | ParserTransitionPayloadV49C
    | OutboundWirePreparedPayloadV49C
    | WritePermitConsumedPayloadV49C
    | TlsCiphertextPreparedPayloadV49C
    | KernelSendAttemptPayloadV49C
    | KernelSendResultPayloadV49C
    | KernelSendFailurePayloadV49E
    | OutboundDispatchCompletedPayloadV49C
    | ApplicationMessageCommittedPayloadV49E
    | SubscriptionAckBoundPayloadV49E
    | AckDeadlineExpiredPayloadV49E
    | LocalShutdownCommandStartedPayloadV49E
    | LocalShutdownDeadlineEvidencePayloadV49E
    | TerminalIngressFailurePayloadV49E
    | TlsProtocolOperationStartedPayloadV49E
    | TlsProtocolOperationFailedPayloadV49E
    | TlsControlCiphertextPreparedPayloadV49E
    | TlsControlKernelSendAttemptPayloadV49E
    | TlsControlKernelSendResultPayloadV49E
    | TlsControlKernelSendFailurePayloadV49E
    | TlsShutdownObservedPayloadV49E
    | TcpHalfCloseAttemptPayloadV49E
    | TcpHalfCloseResultPayloadV49E
    | TerminalTransitionPayloadV49C
)

_PAYLOAD_TYPES: Final = {
    TransportActorEventKindV49C.RAW_INGRESS_COMMITTED: RawIngressCommittedPayloadV49C,
    TransportActorEventKindV49C.PARSER_TRANSITION: ParserTransitionPayloadV49C,
    TransportActorEventKindV49C.OUTBOUND_WIRE_PREPARED: OutboundWirePreparedPayloadV49C,
    TransportActorEventKindV49C.WRITE_PERMIT_CONSUMED: WritePermitConsumedPayloadV49C,
    TransportActorEventKindV49C.TLS_CIPHERTEXT_PREPARED: TlsCiphertextPreparedPayloadV49C,
    TransportActorEventKindV49C.KERNEL_SEND_ATTEMPT: KernelSendAttemptPayloadV49C,
    TransportActorEventKindV49C.KERNEL_SEND_RESULT: KernelSendResultPayloadV49C,
    TransportActorEventKindV49C.KERNEL_SEND_FAILURE: KernelSendFailurePayloadV49E,
    TransportActorEventKindV49C.OUTBOUND_DISPATCH_COMPLETED: OutboundDispatchCompletedPayloadV49C,
    TransportActorEventKindV49C.APPLICATION_MESSAGE_COMMITTED: ApplicationMessageCommittedPayloadV49E,
    TransportActorEventKindV49C.SUBSCRIPTION_ACK_BOUND: SubscriptionAckBoundPayloadV49E,
    TransportActorEventKindV49C.ACK_DEADLINE_EXPIRED: AckDeadlineExpiredPayloadV49E,
    TransportActorEventKindV49C.LOCAL_SHUTDOWN_COMMAND_STARTED: LocalShutdownCommandStartedPayloadV49E,
    TransportActorEventKindV49C.LOCAL_SHUTDOWN_DEADLINE_EVIDENCE: LocalShutdownDeadlineEvidencePayloadV49E,
    TransportActorEventKindV49C.TERMINAL_INGRESS_FAILURE: TerminalIngressFailurePayloadV49E,
    TransportActorEventKindV49C.TLS_PROTOCOL_OPERATION_STARTED: TlsProtocolOperationStartedPayloadV49E,
    TransportActorEventKindV49C.TLS_PROTOCOL_OPERATION_FAILED: TlsProtocolOperationFailedPayloadV49E,
    TransportActorEventKindV49C.TLS_CONTROL_CIPHERTEXT_PREPARED: TlsControlCiphertextPreparedPayloadV49E,
    TransportActorEventKindV49C.TLS_CONTROL_KERNEL_SEND_ATTEMPT: TlsControlKernelSendAttemptPayloadV49E,
    TransportActorEventKindV49C.TLS_CONTROL_KERNEL_SEND_RESULT: TlsControlKernelSendResultPayloadV49E,
    TransportActorEventKindV49C.TLS_CONTROL_KERNEL_SEND_FAILURE: TlsControlKernelSendFailurePayloadV49E,
    TransportActorEventKindV49C.TLS_SHUTDOWN_OBSERVED: TlsShutdownObservedPayloadV49E,
    TransportActorEventKindV49C.TCP_HALF_CLOSE_ATTEMPT: TcpHalfCloseAttemptPayloadV49E,
    TransportActorEventKindV49C.TCP_HALF_CLOSE_RESULT: TcpHalfCloseResultPayloadV49E,
    TransportActorEventKindV49C.TERMINAL_TRANSITION: TerminalTransitionPayloadV49C,
}


@dataclass(frozen=True, slots=True, kw_only=True, init=False)
class TransportActorEventV49C:
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
    monotonic_clock_domain_id: str
    driver_policy_id: str
    recorded_at: datetime
    recorded_monotonic_ns: int
    actor_sequence: int
    previous_event_id: str | None
    event_kind: TransportActorEventKindV49C
    payload: ActorPayloadV49C

    def __init__(self, *, _token: object, **values: Any) -> None:
        if _token is not _EVENT_TOKEN:
            raise TypeError("transport actor events are factory-constructed only")
        for name in self.__dataclass_fields__:
            object.__setattr__(self, name, values[name])
        self._validate()

    def _validate(self) -> None:
        for name in (
            "transport_subscription_policy_id",
            "transport_session_id",
            "physical_scope_manifest_id",
            "adapter_policy_id",
            "capture_partition_id",
            "socket_lease_id",
            "deployment_bundle_id",
            "writer_fence_token_sha256",
            "monotonic_clock_domain_id",
            "driver_policy_id",
        ):
            object.__setattr__(
                self, name, canonical_hash(getattr(self, name), field=name)
            )
        for name in (
            "connection_generation",
            "writer_fence_generation",
            "actor_sequence",
        ):
            object.__setattr__(
                self,
                name,
                canonical_safe_int(getattr(self, name), field=name, minimum=1),
            )
        object.__setattr__(
            self,
            "recorded_at",
            utc_datetime(self.recorded_at, field="recorded_at"),
        )
        object.__setattr__(
            self,
            "recorded_monotonic_ns",
            canonical_safe_int(
                self.recorded_monotonic_ns,
                field="recorded_monotonic_ns",
                minimum=0,
            ),
        )
        previous = _optional_hash(self.previous_event_id, field="previous_event_id")
        if (self.actor_sequence == 1) != (previous is None):
            raise CanonicalizationError(
                "actor genesis and previous event identity are inconsistent"
            )
        kind = _enum(self.event_kind, TransportActorEventKindV49C, field="event_kind")
        expected_type = _PAYLOAD_TYPES[kind]
        if type(self.payload) is not expected_type:
            raise CanonicalizationError(
                f"{kind.value} requires exact {expected_type.__name__} payload"
            )
        object.__setattr__(self, "previous_event_id", previous)
        object.__setattr__(self, "event_kind", kind)

    @classmethod
    def create(cls, **values: Any) -> TransportActorEventV49C:
        return cls(_token=_EVENT_TOKEN, **values)

    def identity_payload(self) -> dict[str, Any]:
        return {
            "actor_sequence": self.actor_sequence,
            "adapter_policy_id": self.adapter_policy_id,
            "capture_partition_id": self.capture_partition_id,
            "connection_generation": self.connection_generation,
            "deployment_bundle_id": self.deployment_bundle_id,
            "driver_policy_id": self.driver_policy_id,
            "event_kind": self.event_kind.value,
            "monotonic_clock_domain_id": self.monotonic_clock_domain_id,
            "payload": _as_payload_mapping(self.payload),
            "physical_scope_manifest_id": self.physical_scope_manifest_id,
            "previous_event_id": self.previous_event_id,
            "recorded_at": utc_iso(self.recorded_at),
            "recorded_monotonic_ns": self.recorded_monotonic_ns,
            "socket_lease_id": self.socket_lease_id,
            "transport_session_id": self.transport_session_id,
            "transport_subscription_policy_id": self.transport_subscription_policy_id,
            "writer_fence_generation": self.writer_fence_generation,
            "writer_fence_token_sha256": self.writer_fence_token_sha256,
        }

    @property
    def transport_actor_event_id(self) -> str:
        return sha256_digest(
            {
                "canonicalization_version": CANONICALIZATION_VERSION,
                "domain": _EVENT_ID_DOMAIN,
                "payload": self.identity_payload(),
                "schema_version": PHYSICAL_TRANSPORT_ACTOR_V49C_SCHEMA_VERSION,
            }
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            **self.identity_payload(),
            "schema_version": PHYSICAL_TRANSPORT_ACTOR_V49C_SCHEMA_VERSION,
            "transport_actor_event_id": self.transport_actor_event_id,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> TransportActorEventV49C:
        expected = set(cls.__dataclass_fields__) | {
            "canonicalization_version",
            "schema_version",
            "transport_actor_event_id",
        }
        require_exact_keys(payload, expected=expected, context=cls.__name__)
        if payload["canonicalization_version"] != CANONICALIZATION_VERSION:
            raise CanonicalizationError("unsupported canonicalization_version")
        if payload["schema_version"] != PHYSICAL_TRANSPORT_ACTOR_V49C_SCHEMA_VERSION:
            raise CanonicalizationError("unsupported transport actor schema_version")
        kind = _enum(
            payload["event_kind"], TransportActorEventKindV49C, field="event_kind"
        )
        raw_payload = payload["payload"]
        if not isinstance(raw_payload, Mapping):
            raise CanonicalizationError("actor payload must be a mapping")
        parsed_payload = _PAYLOAD_TYPES[kind].from_mapping(raw_payload)
        item = cls.create(
            **{
                name: payload[name]
                for name in cls.__dataclass_fields__
                if name not in {"payload", "event_kind"}
            },
            event_kind=kind,
            payload=parsed_payload,
        )
        if (
            canonical_hash(
                payload["transport_actor_event_id"], field="transport_actor_event_id"
            )
            != item.transport_actor_event_id
        ):
            raise CanonicalizationError(
                "transport_actor_event_id differs from canonical content"
            )
        return item


@dataclass(frozen=True, slots=True)
class _CompletedApplicationMessageV49E:
    source_parser_event_ids: tuple[str, ...]
    message_opcode: WebSocketOpcodeV49C
    message_payload_octets: int
    directly_verifiable_payload_sha256: str | None


def _authority_tuple(event: TransportActorEventV49C) -> tuple[Any, ...]:
    return tuple(
        getattr(event, name)
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
    )


def _actor_observation_time_v49c(
    payload: ActorPayloadV49C,
) -> tuple[datetime, int] | None:
    if type(payload) is RawIngressCommittedPayloadV49C:
        return payload.received_at, payload.received_monotonic_ns
    if type(payload) is ParserTransitionPayloadV49C:
        return payload.processed_at, payload.processed_monotonic_ns
    if type(payload) is OutboundWirePreparedPayloadV49C:
        return payload.prepared_at, payload.prepared_monotonic_ns
    if type(payload) is WritePermitConsumedPayloadV49C:
        return payload.consumed_at, payload.consumed_monotonic_ns
    if type(payload) is TlsCiphertextPreparedPayloadV49C:
        return payload.prepared_at, payload.prepared_monotonic_ns
    if type(payload) is KernelSendAttemptPayloadV49C:
        return payload.attempted_at, payload.attempted_monotonic_ns
    if type(payload) is KernelSendResultPayloadV49C:
        return payload.observed_at, payload.observed_monotonic_ns
    if type(payload) is KernelSendFailurePayloadV49E:
        return payload.observed_at, payload.observed_monotonic_ns
    if type(payload) is OutboundDispatchCompletedPayloadV49C:
        return payload.completed_at, payload.completed_monotonic_ns
    if type(payload) is ApplicationMessageCommittedPayloadV49E:
        return payload.classified_at, payload.classified_monotonic_ns
    if type(payload) is SubscriptionAckBoundPayloadV49E:
        return payload.bound_at, payload.bound_monotonic_ns
    if type(payload) is AckDeadlineExpiredPayloadV49E:
        return payload.observed_at, payload.observed_monotonic_ns
    if type(payload) is LocalShutdownCommandStartedPayloadV49E:
        return payload.started_at, payload.started_monotonic_ns
    if type(payload) is LocalShutdownDeadlineEvidencePayloadV49E:
        return payload.observed_at, payload.observed_monotonic_ns
    if type(payload) is TerminalIngressFailurePayloadV49E:
        return payload.observed_at, payload.observed_monotonic_ns
    if type(payload) is TlsProtocolOperationStartedPayloadV49E:
        return payload.started_at, payload.started_monotonic_ns
    if type(payload) is TlsProtocolOperationFailedPayloadV49E:
        return payload.observed_at, payload.observed_monotonic_ns
    if type(payload) is TlsControlCiphertextPreparedPayloadV49E:
        return payload.prepared_at, payload.prepared_monotonic_ns
    if type(payload) is TlsControlKernelSendAttemptPayloadV49E:
        return payload.attempted_at, payload.attempted_monotonic_ns
    if type(payload) is TlsControlKernelSendResultPayloadV49E:
        return payload.observed_at, payload.observed_monotonic_ns
    if type(payload) is TlsControlKernelSendFailurePayloadV49E:
        return payload.observed_at, payload.observed_monotonic_ns
    if type(payload) is TlsShutdownObservedPayloadV49E:
        return payload.observed_at, payload.observed_monotonic_ns
    if type(payload) is TcpHalfCloseAttemptPayloadV49E:
        return payload.attempted_at, payload.attempted_monotonic_ns
    if type(payload) is TcpHalfCloseResultPayloadV49E:
        return payload.observed_at, payload.observed_monotonic_ns
    return None


def validate_transport_actor_chain_v49c(
    events: Sequence[TransportActorEventV49C],
) -> TerminalStateV49C:
    """Validate one finite actor prefix and return its actor-derived terminal state."""

    chain = tuple(events)
    if not chain or any(type(event) is not TransportActorEventV49C for event in chain):
        raise CanonicalizationError("actor chain requires exact V4.9C events")
    authority = _authority_tuple(chain[0])
    terminal_state: TerminalStateV49C = initial_terminal_state_v49c(
        chain[0].transport_session_id
    )
    events_by_id: dict[str, TransportActorEventV49C] = {}
    raw_events: dict[str, RawIngressCommittedPayloadV49C] = {}
    wire_events: dict[str, OutboundWirePreparedPayloadV49C] = {}
    permit_events: dict[str, WritePermitConsumedPayloadV49C] = {}
    tls_events: dict[str, TlsCiphertextPreparedPayloadV49C] = {}
    attempt_events: dict[str, KernelSendAttemptPayloadV49C] = {}
    result_events: dict[str, KernelSendResultPayloadV49C] = {}
    kernel_send_failure_events: dict[str, KernelSendFailurePayloadV49E] = {}
    tls_protocol_operation_events: dict[
        str, TlsProtocolOperationStartedPayloadV49E
    ] = {}
    tls_control_events: dict[str, TlsControlCiphertextPreparedPayloadV49E] = {}
    tls_control_attempt_events: dict[str, TlsControlKernelSendAttemptPayloadV49E] = {}
    tls_control_result_events: dict[str, TlsControlKernelSendResultPayloadV49E] = {}
    tls_control_failure_events: dict[str, TlsControlKernelSendFailurePayloadV49E] = {}
    tcp_half_close_attempt_events: dict[str, TcpHalfCloseAttemptPayloadV49E] = {}
    application_message_events: dict[str, ApplicationMessageCommittedPayloadV49E] = {}
    pending_application_messages: list[_CompletedApplicationMessageV49E] = []
    application_message_receipt_ids: set[str] = set()
    physical_message_ids: set[str] = set()
    provider_message_disposition_ids: set[str] = set()
    message_disposition_ids: set[str] = set()
    bound_ack_application_event_ids: set[str] = set()
    subscription_ack_binding_ids: set[str] = set()
    fragmented_message_parser_event_ids: list[str] = []
    fragmented_message_opcode: WebSocketOpcodeV49C | None = None
    fragmented_message_octets = 0
    subscription_outcomes: dict[str, TransportActorEventKindV49C] = {}
    awaiting_ack_timeout_terminal = False
    unmatched_attempts: set[str] = set()
    wire_queue: list[str] = []
    outbound_operation_ids: set[str] = set()
    local_shutdown_command_event_id: str | None = None
    local_shutdown_command: LocalShutdownCommandStartedPayloadV49E | None = None
    pending_local_shutdown_deadline_evidence: (
        tuple[LocalShutdownDeadlineClassificationV49E, str] | None
    ) = None
    pending_terminal_ingress_failure: (
        tuple[TerminalIngressFailureKindV49E, str] | None
    ) = None
    local_terminal_wire_event_id: str | None = None
    pending_parser_output_event_ids: list[str] = []
    unmarked_ws_close_wires: set[str] = set()
    unmarked_ws_close_parser_events: list[str] = []
    ws_close_sent_marker_event_id: str | None = None
    ws_close_received_marker_event_id: str | None = None
    ws_close_fully_accepted_marker_event_id: str | None = None
    fully_dispatched_close_obligations: set[tuple[OutboundObligationLayerV49C, str]] = (
        set()
    )
    active_permit_event_id: str | None = None
    active_tls_event_id: str | None = None
    tls_offsets: dict[str, int] = {}
    tls_attempt_ordinals: dict[str, int] = {}
    tls_result_ids: dict[str, list[str]] = {}
    awaiting_terminal_resolution: str | None = None
    kernel_send_failure_awaiting_resolution: tuple[str, str] | None = None
    pending_kernel_send_failure_timeout: tuple[str, str] | None = None
    pending_tls_protocol_operation_event_id: str | None = None
    pending_tls_operation_failure_marker: (
        tuple[TlsProtocolOperationFailedPayloadV49E, str] | None
    ) = None
    last_tls_protocol_operation_sequence = 0
    tls_driver_evidence_nonce_sha256: str | None = None
    active_tls_control_event_id: str | None = None
    last_tls_control_sequence = 0
    tls_control_offsets: dict[str, int] = {}
    tls_control_attempt_ordinals: dict[str, int] = {}
    tls_control_result_ids: dict[str, list[str]] = {}
    unmatched_tls_control_attempts: set[str] = set()
    pending_tls_control_prepared_marker_event_id: str | None = None
    local_tls_prepared_marker_event_id: str | None = None
    peer_close_received_during_local_tls_preparation = False
    tls_control_attempt_awaiting_started_marker: str | None = None
    tls_control_result_awaiting_resolved_marker: tuple[str, str] | None = None
    tls_control_failure_awaiting_resolved_marker: tuple[str, str] | None = None
    pending_tls_control_failure_timeout_event_id: str | None = None
    completed_local_tls_control_event_id: str | None = None
    pending_local_tls_sent_control_id: str | None = None
    pending_local_tls_full_acceptance_control_id: str | None = None
    local_tls_marker_event_id: str | None = None
    local_tls_fully_accepted_marker_event_id: str | None = None
    last_tls_shutdown_observation_sequence = 0
    tls_shutdown_observation_ids: set[str] = set()
    tls_shutdown_owner_kernel_socket_identity: str | None = None
    pending_shutdown_observation_marker: (
        tuple[TlsShutdownObservationKindV49E, str] | None
    ) = None
    peer_tls_marker_event_id: str | None = None
    tcp_eof_marker_event_id: str | None = None
    last_tls_shutdown_marker_event_id: str | None = None
    tcp_half_close_attempt_event_id: str | None = None
    tcp_half_close_result_event_id: str | None = None
    pending_tcp_half_close_marker_result_event_id: str | None = None
    pending_tcp_half_close_failure_marker: (
        tuple[TcpHalfCloseResultKindV49E, str, str] | None
    ) = None
    tcp_half_close_marker_event_id: str | None = None
    parser_cursor: WebSocketParserCursorV49C | None = None
    raw_tail: RawIngressCommittedPayloadV49C | None = None
    receipt_ledger_id: str | None = None
    last_receipt_sequence = 0
    last_receipt_committed_at: datetime | None = None
    last_recorded_at: datetime | None = None
    last_recorded_monotonic_ns: int | None = None

    def subscription_dispatch(
        *, intent_id: str, dispatch_event_id: str
    ) -> tuple[
        OutboundDispatchCompletedPayloadV49C,
        OutboundWirePreparedPayloadV49C,
        KernelSendAttemptPayloadV49C,
    ]:
        dispatch_event = events_by_id.get(dispatch_event_id)
        if (
            dispatch_event is None
            or dispatch_event.event_kind
            is not TransportActorEventKindV49C.OUTBOUND_DISPATCH_COMPLETED
            or type(dispatch_event.payload) is not OutboundDispatchCompletedPayloadV49C
        ):
            raise CanonicalizationError(
                "subscription outcome lacks its exact completed dispatch"
            )
        dispatch = dispatch_event.payload
        wire = wire_events.get(dispatch.outbound_wire_prepared_event_id)
        first_result = result_events.get(dispatch.kernel_send_result_event_ids[0])
        first_attempt = (
            None
            if first_result is None
            else attempt_events.get(first_result.kernel_send_attempt_event_id)
        )
        if (
            wire is None
            or first_attempt is None
            or wire.wire_origin is not OutboundWireOriginV49C.APPLICATION_INTENT
            or wire.logical_opcode is not WebSocketOpcodeV49C.TEXT
            or wire.outbound_operation_id != intent_id
        ):
            raise CanonicalizationError(
                "subscription outcome differs from its application Text dispatch"
            )
        return dispatch, wire, first_attempt

    for index, event in enumerate(chain, start=1):
        if terminal_state.is_terminal:
            raise CanonicalizationError("actor chain continues after terminal state")
        if _authority_tuple(event) != authority:
            raise CanonicalizationError("actor chain changes session authority")
        expected_previous = (
            None if index == 1 else chain[index - 2].transport_actor_event_id
        )
        if (
            event.actor_sequence != index
            or event.previous_event_id != expected_previous
        ):
            raise CanonicalizationError("actor sequence or predecessor chain is broken")
        if last_recorded_at is not None and (
            event.recorded_at < last_recorded_at
            or event.recorded_monotonic_ns <= last_recorded_monotonic_ns
        ):
            raise CanonicalizationError("actor event clocks regress or fail to advance")
        event_id = event.transport_actor_event_id
        if event_id in events_by_id:
            raise CanonicalizationError("actor event identity is duplicated")
        payload = event.payload
        if awaiting_ack_timeout_terminal and not (
            event.event_kind is TransportActorEventKindV49C.TERMINAL_TRANSITION
            and type(payload) is TerminalTransitionPayloadV49C
            and payload.kind is TerminalTransitionKindV49C.TIMEOUT
        ):
            raise CanonicalizationError(
                "expired ACK deadline must transition directly to terminal TIMEOUT"
            )
        if pending_kernel_send_failure_timeout is not None:
            _, failure_timeout_cause = pending_kernel_send_failure_timeout
            failure_terminal_kind = (
                TerminalTransitionKindV49C.FATAL
                if failure_timeout_cause == V49E_LOCAL_SHUTDOWN_CLOCK_DISAGREEMENT_CAUSE
                else TerminalTransitionKindV49C.TIMEOUT
            )
            if not (
                event.event_kind is TransportActorEventKindV49C.TERMINAL_TRANSITION
                and type(payload) is TerminalTransitionPayloadV49C
                and payload.kind is failure_terminal_kind
                and payload.cause_code == failure_timeout_cause
            ):
                raise CanonicalizationError(
                    "conclusive zero-acceptance send failure must terminalize next"
                )
        if pending_terminal_ingress_failure is not None:
            ingress_failure_kind, _ = pending_terminal_ingress_failure
            expected_ingress_terminal_kind = (
                TerminalTransitionKindV49C.FATAL
                if ingress_failure_kind
                is TerminalIngressFailureKindV49E.CLOCK_DISAGREEMENT
                else TerminalTransitionKindV49C.TIMEOUT
            )
            expected_ingress_cause = (
                V49E_LOCAL_SHUTDOWN_CLOCK_DISAGREEMENT_CAUSE
                if ingress_failure_kind
                is TerminalIngressFailureKindV49E.CLOCK_DISAGREEMENT
                else V49E_TERMINAL_CLOSE_INGRESS_DEADLINE_EXPIRED_AFTER_PROGRESS_CAUSE
            )
            if not (
                event.event_kind is TransportActorEventKindV49C.TERMINAL_TRANSITION
                and type(payload) is TerminalTransitionPayloadV49C
                and payload.kind is expected_ingress_terminal_kind
                and payload.cause_code == expected_ingress_cause
            ):
                raise CanonicalizationError(
                    "terminal-ingress failure must terminalize next"
                )
        if pending_local_shutdown_deadline_evidence is not None:
            deadline_classification, _ = pending_local_shutdown_deadline_evidence
            expected_deadline_terminal_kind = (
                TerminalTransitionKindV49C.TIMEOUT
                if deadline_classification
                is LocalShutdownDeadlineClassificationV49E.BOTH_DUE
                else TerminalTransitionKindV49C.FATAL
            )
            expected_deadline_cause = {
                LocalShutdownDeadlineClassificationV49E.BOTH_DUE: (
                    V49E_LOCAL_SHUTDOWN_COMMAND_DEADLINE_EXPIRED_CAUSE
                ),
                LocalShutdownDeadlineClassificationV49E.CLOCK_DISAGREEMENT: (
                    V49E_LOCAL_SHUTDOWN_CLOCK_DISAGREEMENT_CAUSE
                ),
                LocalShutdownDeadlineClassificationV49E.OWNER_EVIDENCE_BEFORE_BOTH_CLOCKS: (
                    V49E_TLS_OPERATION_DRIVER_ERROR_CAUSE
                ),
            }[deadline_classification]
            if not (
                event.event_kind is TransportActorEventKindV49C.TERMINAL_TRANSITION
                and type(payload) is TerminalTransitionPayloadV49C
                and payload.kind is expected_deadline_terminal_kind
                and payload.cause_code == expected_deadline_cause
            ):
                raise CanonicalizationError(
                    "local shutdown deadline evidence must terminalize next"
                )
        if pending_tls_control_failure_timeout_event_id is not None:
            pending_tls_failure = tls_control_failure_events[
                pending_tls_control_failure_timeout_event_id
            ]
            pending_tls_terminal_kind = (
                TerminalTransitionKindV49C.FATAL
                if pending_tls_failure.failure_kind
                is KernelSendFailureKindV49E.CLOCK_DISAGREEMENT
                else TerminalTransitionKindV49C.TIMEOUT
            )
            pending_tls_cause = (
                V49E_LOCAL_SHUTDOWN_CLOCK_DISAGREEMENT_CAUSE
                if pending_tls_failure.failure_kind
                is KernelSendFailureKindV49E.CLOCK_DISAGREEMENT
                else V49E_LOCAL_SHUTDOWN_COMMAND_DEADLINE_EXPIRED_CAUSE
            )
            if not (
                event.event_kind is TransportActorEventKindV49C.TERMINAL_TRANSITION
                and type(payload) is TerminalTransitionPayloadV49C
                and payload.kind is pending_tls_terminal_kind
                and payload.cause_code == pending_tls_cause
            ):
                raise CanonicalizationError(
                    "conclusive TLS zero-acceptance failure must terminalize next"
                )
        if pending_tls_protocol_operation_event_id is not None:
            expected_kind = TransportActorEventKindV49C.TLS_CONTROL_CIPHERTEXT_PREPARED
            operation = tls_protocol_operation_events[
                pending_tls_protocol_operation_event_id
            ]
            if operation.purpose is TlsProtocolOperationPurposeV49E.PEER_SHUTDOWN_POLL:
                expected_kind = TransportActorEventKindV49C.TLS_SHUTDOWN_OBSERVED
            if event.event_kind not in {
                expected_kind,
                TransportActorEventKindV49C.TLS_PROTOCOL_OPERATION_FAILED,
            }:
                raise CanonicalizationError(
                    "started TLS operation must record its exact next result"
                )
        if pending_tls_operation_failure_marker is not None:
            failure_payload, _ = pending_tls_operation_failure_marker
            required_kind, required_cause = (
                classify_tls_protocol_operation_failure_v49e(failure_payload)
            )
            if not (
                event.event_kind is TransportActorEventKindV49C.TERMINAL_TRANSITION
                and type(payload) is TerminalTransitionPayloadV49C
                and payload.kind is required_kind
                and payload.cause_code == required_cause
            ):
                raise CanonicalizationError(
                    "TLS operation failure must emit its fixed terminal outcome next"
                )
        if pending_tls_control_prepared_marker_event_id is not None and not (
            event.event_kind is TransportActorEventKindV49C.TERMINAL_TRANSITION
            and type(payload) is TerminalTransitionPayloadV49C
            and payload.kind is TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_PREPARED
        ):
            raise CanonicalizationError(
                "local close_notify artifact must emit its prepared marker next"
            )
        if tls_control_attempt_awaiting_started_marker is not None and not (
            event.event_kind is TransportActorEventKindV49C.TERMINAL_TRANSITION
            and type(payload) is TerminalTransitionPayloadV49C
            and payload.kind is TerminalTransitionKindV49C.SEND_ATTEMPT_STARTED
        ):
            raise CanonicalizationError(
                "TLS-control attempt must emit SEND_ATTEMPT_STARTED next"
            )
        if (
            unmatched_tls_control_attempts
            and tls_control_attempt_awaiting_started_marker is None
            and not (
                event.event_kind
                in {
                    TransportActorEventKindV49C.TLS_CONTROL_KERNEL_SEND_RESULT,
                    TransportActorEventKindV49C.TLS_CONTROL_KERNEL_SEND_FAILURE,
                }
                or (
                    event.event_kind is TransportActorEventKindV49C.TERMINAL_TRANSITION
                    and type(payload) is TerminalTransitionPayloadV49C
                    and payload.kind is TerminalTransitionKindV49C.UNKNOWN_SEND
                    and payload.cause_code
                    == V49E_TLS_CONTROL_SEND_OUTCOME_UNKNOWN_CAUSE
                )
            )
        ):
            raise CanonicalizationError(
                "started TLS-control send permits only exact result or UNKNOWN_SEND"
            )
        if tls_control_result_awaiting_resolved_marker is not None and not (
            event.event_kind is TransportActorEventKindV49C.TERMINAL_TRANSITION
            and type(payload) is TerminalTransitionPayloadV49C
            and payload.kind is TerminalTransitionKindV49C.SEND_ATTEMPT_RESOLVED
        ):
            raise CanonicalizationError(
                "TLS-control result must emit SEND_ATTEMPT_RESOLVED next"
            )
        if tls_control_failure_awaiting_resolved_marker is not None and not (
            event.event_kind is TransportActorEventKindV49C.TERMINAL_TRANSITION
            and type(payload) is TerminalTransitionPayloadV49C
            and payload.kind is TerminalTransitionKindV49C.SEND_ATTEMPT_RESOLVED
        ):
            raise CanonicalizationError(
                "TLS-control failure must emit SEND_ATTEMPT_RESOLVED next"
            )
        if pending_local_tls_sent_control_id is not None and not (
            event.event_kind is TransportActorEventKindV49C.TERMINAL_TRANSITION
            and type(payload) is TerminalTransitionPayloadV49C
            and payload.kind is TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_SENT
        ):
            raise CanonicalizationError(
                "resolved local close_notify must emit its sent marker next"
            )
        if pending_local_tls_full_acceptance_control_id is not None and not (
            event.event_kind is TransportActorEventKindV49C.TERMINAL_TRANSITION
            and type(payload) is TerminalTransitionPayloadV49C
            and payload.kind
            is TerminalTransitionKindV49C.OUTBOUND_OBLIGATION_FULLY_KERNEL_ACCEPTED
            and payload.obligation_layer is OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY
        ):
            raise CanonicalizationError(
                "sent local close_notify must emit full kernel acceptance next"
            )
        if pending_shutdown_observation_marker is not None:
            observation_kind, _ = pending_shutdown_observation_marker
            required_transition = (
                TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_RECEIVED
                if observation_kind is TlsShutdownObservationKindV49E.PEER_CLOSE_NOTIFY
                else TerminalTransitionKindV49C.TCP_EOF_RECEIVED
            )
            if not (
                event.event_kind is TransportActorEventKindV49C.TERMINAL_TRANSITION
                and type(payload) is TerminalTransitionPayloadV49C
                and payload.kind is required_transition
            ):
                raise CanonicalizationError(
                    "TLS shutdown observation must emit its exact terminal marker next"
                )
        if (
            tcp_half_close_attempt_event_id is not None
            and tcp_half_close_result_event_id is None
            and not (
                event.event_kind is TransportActorEventKindV49C.TCP_HALF_CLOSE_RESULT
                or (
                    event.event_kind is TransportActorEventKindV49C.TERMINAL_TRANSITION
                    and type(payload) is TerminalTransitionPayloadV49C
                    and payload.kind is TerminalTransitionKindV49C.FATAL
                    and payload.cause_code == V49E_TCP_HALF_CLOSE_OUTCOME_UNKNOWN_CAUSE
                )
            )
        ):
            raise CanonicalizationError(
                "TCP half-close attempt permits only exact result or fixed ambiguity"
            )
        if pending_tcp_half_close_marker_result_event_id is not None and not (
            event.event_kind is TransportActorEventKindV49C.TERMINAL_TRANSITION
            and type(payload) is TerminalTransitionPayloadV49C
            and payload.kind is TerminalTransitionKindV49C.TCP_FIN_SENT
        ):
            raise CanonicalizationError(
                "successful SHUT_WR must emit its compatibility marker next"
            )
        if pending_tcp_half_close_failure_marker is not None:
            failure_result_kind, _, _ = pending_tcp_half_close_failure_marker
            expected_terminal_kind = (
                TerminalTransitionKindV49C.TIMEOUT
                if failure_result_kind
                is TcpHalfCloseResultKindV49E.DEADLINE_EXPIRED_BEFORE_SYSCALL
                else TerminalTransitionKindV49C.FATAL
            )
            expected_terminal_cause = (
                V49E_TCP_HALF_CLOSE_DEADLINE_EXPIRED_BEFORE_SYSCALL_CAUSE
                if failure_result_kind
                is TcpHalfCloseResultKindV49E.DEADLINE_EXPIRED_BEFORE_SYSCALL
                else (
                    V49E_LOCAL_SHUTDOWN_CLOCK_DISAGREEMENT_CAUSE
                    if failure_result_kind
                    is TcpHalfCloseResultKindV49E.CLOCK_DISAGREEMENT
                    else V49E_TCP_HALF_CLOSE_ERROR_CAUSE
                )
            )
            if not (
                event.event_kind is TransportActorEventKindV49C.TERMINAL_TRANSITION
                and type(payload) is TerminalTransitionPayloadV49C
                and payload.kind is expected_terminal_kind
                and payload.cause_code == expected_terminal_cause
            ):
                raise CanonicalizationError(
                    "failed SHUT_WR must emit its exact terminal outcome next"
                )
        observation = _actor_observation_time_v49c(payload)
        if observation is not None:
            observed_at, observed_ns = observation
            if (
                event.recorded_at < observed_at
                or event.recorded_monotonic_ns < observed_ns
            ):
                raise CanonicalizationError(
                    "actor event predates the physical observation it records"
                )
            if type(payload) in {
                RawIngressCommittedPayloadV49C,
                LocalShutdownCommandStartedPayloadV49E,
            } and (
                event.recorded_at != observed_at
                or event.recorded_monotonic_ns != observed_ns
            ):
                raise CanonicalizationError(
                    "RAW and shutdown-command actor clocks must equal their "
                    "governed observation clocks"
                )
        last_recorded_at = event.recorded_at
        last_recorded_monotonic_ns = event.recorded_monotonic_ns

        if unmatched_attempts:
            allowed = event.event_kind in {
                TransportActorEventKindV49C.KERNEL_SEND_RESULT,
                TransportActorEventKindV49C.KERNEL_SEND_FAILURE,
            }
            if event.event_kind is TransportActorEventKindV49C.TERMINAL_TRANSITION:
                assert type(payload) is TerminalTransitionPayloadV49C
                allowed = payload.kind in {
                    TerminalTransitionKindV49C.SEND_ATTEMPT_STARTED,
                    TerminalTransitionKindV49C.UNKNOWN_SEND,
                }
            if not allowed:
                raise CanonicalizationError(
                    "an unresolved kernel attempt blocks every unrelated actor event"
                )
        elif terminal_state.has_pending_send_attempt:
            allowed = (
                event.event_kind is TransportActorEventKindV49C.KERNEL_SEND_FAILURE
                or (
                    event.event_kind is TransportActorEventKindV49C.TERMINAL_TRANSITION
                    and type(payload) is TerminalTransitionPayloadV49C
                    and payload.kind
                    in {
                        TerminalTransitionKindV49C.SEND_ATTEMPT_RESOLVED,
                        TerminalTransitionKindV49C.UNKNOWN_SEND,
                    }
                )
            )
            if terminal_state.pending_send_attempt_id in unmatched_tls_control_attempts:
                allowed = (
                    event.event_kind
                    in {
                        TransportActorEventKindV49C.TLS_CONTROL_KERNEL_SEND_RESULT,
                        TransportActorEventKindV49C.TLS_CONTROL_KERNEL_SEND_FAILURE,
                    }
                ) or (
                    event.event_kind is TransportActorEventKindV49C.TERMINAL_TRANSITION
                    and type(payload) is TerminalTransitionPayloadV49C
                    and payload.kind is TerminalTransitionKindV49C.UNKNOWN_SEND
                )
            if not allowed:
                raise CanonicalizationError(
                    "terminal send state must resolve before actor progress"
                )

        if event.event_kind is TransportActorEventKindV49C.RAW_INGRESS_COMMITTED:
            assert type(payload) is RawIngressCommittedPayloadV49C
            if raw_tail is None:
                if payload.ingress_sequence != 1 or payload.stream_start_octet != 0:
                    raise CanonicalizationError(
                        "raw actor stream must start at genesis zero"
                    )
            elif (
                payload.ingress_sequence != raw_tail.ingress_sequence + 1
                or payload.previous_raw_ingress_commit_id
                != raw_tail.raw_ingress_commit_id
                or payload.stream_start_octet != raw_tail.stream_end_octet
                or payload.received_monotonic_ns <= raw_tail.received_monotonic_ns
            ):
                raise CanonicalizationError(
                    "raw actor stream isn't contiguous and ordered"
                )
            receipt = payload.receipt
            if receipt_ledger_id is None:
                receipt_ledger_id = receipt.ledger_id
            if (
                receipt.ledger_id != receipt_ledger_id
                or receipt.global_sequence <= last_receipt_sequence
                or (
                    last_receipt_committed_at is not None
                    and receipt.committed_at < last_receipt_committed_at
                )
                or receipt.committed_at < payload.received_at
            ):
                raise CanonicalizationError(
                    "raw receipts don't form one forward projection observation"
                )
            raw_events[payload.raw_ingress_commit_id] = payload
            raw_tail = payload
            last_receipt_sequence = receipt.global_sequence
            last_receipt_committed_at = receipt.committed_at
        elif event.event_kind is TransportActorEventKindV49C.PARSER_TRANSITION:
            assert type(payload) is ParserTransitionPayloadV49C
            if (
                payload.feed_unit_kind is ParserFeedUnitKindV49C.COMPLETE_FRAME
                and payload.cursor_before.websocket_state
                is WebSocketParserStateV49C.OPEN
                and payload.frame is not None
                and payload.frame.opcode
                in {WebSocketOpcodeV49C.PING, WebSocketOpcodeV49C.CLOSE}
                and not payload.ordered_protocol_output_chunks_base64
            ):
                raise CanonicalizationError(
                    "OPEN parser Ping/Close event omits its mandatory automatic output"
                )
            if parser_cursor is None:
                if (
                    payload.cursor_before.cursor_sequence != 0
                    or payload.cursor_before.next_stream_octet != 0
                ):
                    raise CanonicalizationError(
                        "parser chain must start at cursor genesis"
                    )
            elif payload.cursor_before != parser_cursor:
                raise CanonicalizationError(
                    "parser transition changes its prior cursor"
                )
            for source in payload.source_slices:
                raw = raw_events.get(source.raw_ingress_commit_id)
                if raw is None:
                    raise CanonicalizationError("parser source lacks a prior raw event")
                if (
                    source.projection_receipt_sequence != raw.receipt.global_sequence
                    or source.projection_receipt_hash != raw.receipt.receipt_hash
                    or source.stream_start_octet
                    != raw.stream_start_octet + source.raw_local_start_octet
                    or source.stream_end_octet
                    != raw.stream_start_octet + source.raw_local_end_octet
                    or source.raw_local_end_octet
                    > raw.stream_end_octet - raw.stream_start_octet
                ):
                    raise CanonicalizationError(
                        "parser source differs from raw receipt interval"
                    )
                if (
                    payload.processed_at < raw.receipt.committed_at
                    or payload.processed_monotonic_ns < raw.received_monotonic_ns
                ):
                    raise CanonicalizationError(
                        "parser transition predates its durable raw source"
                    )
            cursor_before = payload.cursor_before
            cursor_after = payload.cursor_after
            if fragmented_message_opcode is None:
                if (
                    cursor_before.fragmented_message_opcode is not None
                    or cursor_before.fragmented_message_octets != 0
                    or cursor_before.fragmented_message_sha256 is not None
                ):
                    raise CanonicalizationError(
                        "parser cursor invents an untracked fragmented message"
                    )
            elif (
                cursor_before.fragmented_message_opcode is not fragmented_message_opcode
                or cursor_before.fragmented_message_octets != fragmented_message_octets
                or cursor_before.fragmented_message_sha256 is None
            ):
                raise CanonicalizationError(
                    "parser cursor differs from the active fragmented message"
                )

            if payload.feed_unit_kind is ParserFeedUnitKindV49C.PARSER_ERROR:
                fragmented_message_parser_event_ids.clear()
                fragmented_message_opcode = None
                fragmented_message_octets = 0
            else:
                assert payload.frame is not None
                frame = payload.frame
                if frame.opcode in {
                    WebSocketOpcodeV49C.TEXT,
                    WebSocketOpcodeV49C.BINARY,
                }:
                    if fragmented_message_opcode is not None:
                        raise CanonicalizationError(
                            "new data frame interrupts a fragmented message"
                        )
                    if frame.fin:
                        if (
                            cursor_after.fragmented_message_opcode is not None
                            or cursor_after.fragmented_message_octets != 0
                            or cursor_after.fragmented_message_sha256 is not None
                        ):
                            raise CanonicalizationError(
                                "final data frame leaves fragmented cursor state"
                            )
                        pending_application_messages.append(
                            _CompletedApplicationMessageV49E(
                                source_parser_event_ids=(event_id,),
                                message_opcode=frame.opcode,
                                message_payload_octets=frame.payload_octets,
                                directly_verifiable_payload_sha256=(
                                    frame.payload_sha256
                                ),
                            )
                        )
                    else:
                        if (
                            cursor_after.fragmented_message_opcode is not frame.opcode
                            or cursor_after.fragmented_message_octets
                            != frame.payload_octets
                            or cursor_after.fragmented_message_sha256
                            != frame.payload_sha256
                        ):
                            raise CanonicalizationError(
                                "initial fragment differs from parser cursor state"
                            )
                        fragmented_message_parser_event_ids[:] = [event_id]
                        fragmented_message_opcode = frame.opcode
                        fragmented_message_octets = frame.payload_octets
                elif frame.opcode is WebSocketOpcodeV49C.CONTINUATION:
                    if fragmented_message_opcode is None:
                        raise CanonicalizationError(
                            "continuation lacks an active fragmented message"
                        )
                    total_octets = fragmented_message_octets + frame.payload_octets
                    if total_octets > V49C_MAX_FRAME_PAYLOAD_OCTETS:
                        raise CanonicalizationError(
                            "fragmented application message exceeds its octet bound"
                        )
                    fragment_ids = (
                        *fragmented_message_parser_event_ids,
                        event_id,
                    )
                    if len(fragment_ids) > V49E_MAX_APPLICATION_MESSAGE_FRAMES:
                        raise CanonicalizationError(
                            "fragmented application message exceeds its frame bound"
                        )
                    if frame.fin:
                        if (
                            cursor_after.fragmented_message_opcode is not None
                            or cursor_after.fragmented_message_octets != 0
                            or cursor_after.fragmented_message_sha256 is not None
                        ):
                            raise CanonicalizationError(
                                "final continuation leaves fragmented cursor state"
                            )
                        pending_application_messages.append(
                            _CompletedApplicationMessageV49E(
                                source_parser_event_ids=tuple(fragment_ids),
                                message_opcode=fragmented_message_opcode,
                                message_payload_octets=total_octets,
                                directly_verifiable_payload_sha256=None,
                            )
                        )
                        fragmented_message_parser_event_ids.clear()
                        fragmented_message_opcode = None
                        fragmented_message_octets = 0
                    else:
                        if (
                            cursor_after.fragmented_message_opcode
                            is not fragmented_message_opcode
                            or cursor_after.fragmented_message_octets != total_octets
                            or cursor_after.fragmented_message_sha256 is None
                        ):
                            raise CanonicalizationError(
                                "continuation differs from parser cursor state"
                            )
                        fragmented_message_parser_event_ids[:] = fragment_ids
                        fragmented_message_octets = total_octets
                elif frame.opcode in {
                    WebSocketOpcodeV49C.PING,
                    WebSocketOpcodeV49C.PONG,
                }:
                    if (
                        cursor_after.fragmented_message_opcode
                        is not cursor_before.fragmented_message_opcode
                        or cursor_after.fragmented_message_octets
                        != cursor_before.fragmented_message_octets
                        or cursor_after.fragmented_message_sha256
                        != cursor_before.fragmented_message_sha256
                    ):
                        raise CanonicalizationError(
                            "interleaved control frame changes fragmented state"
                        )
                else:
                    assert frame.opcode is WebSocketOpcodeV49C.CLOSE
                    if (
                        cursor_after.fragmented_message_opcode is not None
                        or cursor_after.fragmented_message_octets != 0
                        or cursor_after.fragmented_message_sha256 is not None
                    ):
                        raise CanonicalizationError(
                            "Close frame retains fragmented cursor state"
                        )
                    fragmented_message_parser_event_ids.clear()
                    fragmented_message_opcode = None
                    fragmented_message_octets = 0
            parser_cursor = payload.cursor_after
            if payload.ordered_protocol_output_chunks_base64:
                pending_parser_output_event_ids.append(event_id)
            if (
                payload.frame is not None
                and payload.frame.opcode is WebSocketOpcodeV49C.CLOSE
            ):
                unmarked_ws_close_parser_events.append(event_id)
        elif (
            event.event_kind
            is TransportActorEventKindV49C.LOCAL_SHUTDOWN_COMMAND_STARTED
        ):
            assert type(payload) is LocalShutdownCommandStartedPayloadV49E
            current_cursor = (
                WebSocketParserCursorV49C(
                    cursor_sequence=0,
                    next_stream_octet=0,
                    websocket_state=WebSocketParserStateV49C.OPEN,
                )
                if parser_cursor is None
                else parser_cursor
            )
            no_fragments = (
                current_cursor.fragmented_message_opcode is None
                and current_cursor.fragmented_message_octets == 0
                and current_cursor.fragmented_message_sha256 is None
                and fragmented_message_opcode is None
                and not fragmented_message_parser_event_ids
                and fragmented_message_octets == 0
            )
            open_profile = (
                current_cursor.websocket_state is WebSocketParserStateV49C.OPEN
                and not terminal_state.ws_close_sent
                and not terminal_state.ws_close_received
                and not terminal_state.ws_output_fully_kernel_accepted
            )
            peer_first_profile = (
                current_cursor.websocket_state is WebSocketParserStateV49C.CLOSING
                and terminal_state.ws_close_sent
                and terminal_state.ws_close_received
                and terminal_state.ws_output_fully_kernel_accepted
            )
            expected_command_id = derive_local_shutdown_command_id_v49e(
                transport_session_id=event.transport_session_id,
                actor_predecessor_event_id=event.previous_event_id,
                timeout_seconds=payload.timeout_seconds,
                started_at=payload.started_at,
                started_monotonic_ns=payload.started_monotonic_ns,
                deadline_at=payload.shutdown_deadline_at,
                deadline_monotonic_ns=payload.shutdown_deadline_monotonic_ns,
            )
            if local_shutdown_command_event_id is not None:
                raise CanonicalizationError(
                    "actor chain contains a second local terminal command"
                )
            if not no_fragments:
                raise CanonicalizationError(
                    "local shutdown command cannot close a fragmented message"
                )
            if pending_parser_output_event_ids:
                raise CanonicalizationError(
                    "local shutdown command cannot reorder an unconsumed "
                    "automatic output"
                )
            if (
                payload.local_shutdown_command_id != expected_command_id
                or payload.started_at != event.recorded_at
                or payload.started_monotonic_ns != event.recorded_monotonic_ns
                or not (open_profile or peer_first_profile)
                or wire_queue
                or active_permit_event_id is not None
                or active_tls_event_id is not None
                or unmatched_attempts
                or terminal_state.has_pending_send_attempt
                or pending_tls_protocol_operation_event_id is not None
                or active_tls_control_event_id is not None
                or unmatched_tls_control_attempts
                or local_tls_marker_event_id is not None
                or local_tls_fully_accepted_marker_event_id is not None
                or peer_tls_marker_event_id is not None
                or tcp_half_close_attempt_event_id is not None
                or tcp_half_close_result_event_id is not None
                or tcp_half_close_marker_event_id is not None
                or tcp_eof_marker_event_id is not None
            ):
                raise CanonicalizationError(
                    "local shutdown command requires one quiescent OPEN or "
                    "completed peer-first WebSocket state"
                )
            local_shutdown_command_event_id = event_id
            local_shutdown_command = payload
        elif (
            event.event_kind
            is TransportActorEventKindV49C.LOCAL_SHUTDOWN_DEADLINE_EVIDENCE
        ):
            assert type(payload) is LocalShutdownDeadlineEvidencePayloadV49E
            expected_owner_evidence_id = sha256_digest(
                {
                    "domain": "RiskYieldMMOwnerDeadlineExpiredNoObservationV4_9E",
                    "transport_session_id": event.transport_session_id,
                    "kernel_socket_identity": payload.kernel_socket_identity,
                    "driver_evidence_nonce_sha256": (
                        payload.driver_evidence_nonce_sha256
                    ),
                    "operation": payload.operation,
                    "deadline_ns": payload.shutdown_deadline_monotonic_ns,
                }
            )
            wall_due = (
                local_shutdown_command is not None
                and payload.observed_at >= local_shutdown_command.shutdown_deadline_at
            )
            monotonic_due = (
                local_shutdown_command is not None
                and payload.observed_monotonic_ns
                >= local_shutdown_command.shutdown_deadline_monotonic_ns
            )
            expected_classification = (
                LocalShutdownDeadlineClassificationV49E.BOTH_DUE
                if wall_due and monotonic_due
                else (
                    LocalShutdownDeadlineClassificationV49E.CLOCK_DISAGREEMENT
                    if wall_due != monotonic_due
                    else LocalShutdownDeadlineClassificationV49E.OWNER_EVIDENCE_BEFORE_BOTH_CLOCKS
                )
            )
            if (
                local_shutdown_command_event_id is None
                or local_shutdown_command is None
                or payload.local_shutdown_command_started_event_id
                != local_shutdown_command_event_id
                or payload.shutdown_deadline_monotonic_ns
                != local_shutdown_command.shutdown_deadline_monotonic_ns
                or payload.owner_evidence_id != expected_owner_evidence_id
                or payload.classification is not expected_classification
                or payload.observed_at != event.recorded_at
                or payload.observed_monotonic_ns != event.recorded_monotonic_ns
                or pending_local_shutdown_deadline_evidence is not None
            ):
                raise CanonicalizationError(
                    "local shutdown deadline evidence differs from command/owner"
                )
            pending_local_shutdown_deadline_evidence = (
                payload.classification,
                event_id,
            )
        elif event.event_kind is TransportActorEventKindV49C.TERMINAL_INGRESS_FAILURE:
            assert type(payload) is TerminalIngressFailurePayloadV49E
            expected_driver_evidence_id = (
                _derive_driver_deadline_after_progress_evidence_id_v49e(
                    driver_evidence_nonce_sha256=(payload.driver_evidence_nonce_sha256),
                    operation=payload.operation,
                    deadline_ns=payload.shutdown_deadline_monotonic_ns,
                    ciphertext_octets_received=payload.ciphertext_octets_received,
                    ciphertext_sha256=payload.ciphertext_sha256,
                )
            )
            expected_owner_evidence_id = (
                _derive_owner_deadline_after_progress_evidence_id_v49e(
                    transport_session_id=event.transport_session_id,
                    kernel_socket_identity=payload.kernel_socket_identity,
                    driver_evidence_nonce_sha256=(payload.driver_evidence_nonce_sha256),
                    operation=payload.operation,
                    deadline_ns=payload.shutdown_deadline_monotonic_ns,
                    ciphertext_octets_received=payload.ciphertext_octets_received,
                    ciphertext_sha256=payload.ciphertext_sha256,
                    driver_evidence_id=expected_driver_evidence_id,
                )
            )
            wall_due = (
                local_shutdown_command is not None
                and payload.observed_at >= local_shutdown_command.shutdown_deadline_at
            )
            monotonic_due = (
                local_shutdown_command is not None
                and payload.observed_monotonic_ns
                >= local_shutdown_command.shutdown_deadline_monotonic_ns
            )
            if (
                local_shutdown_command_event_id is None
                or local_shutdown_command is None
                or payload.local_shutdown_command_started_event_id
                != local_shutdown_command_event_id
                or payload.shutdown_deadline_monotonic_ns
                != local_shutdown_command.shutdown_deadline_monotonic_ns
                or payload.driver_evidence_id != expected_driver_evidence_id
                or payload.owner_evidence_id != expected_owner_evidence_id
                or (
                    payload.failure_kind
                    is TerminalIngressFailureKindV49E.DEADLINE_EXPIRED_AFTER_PROGRESS
                    and not (wall_due and monotonic_due)
                )
                or (
                    payload.failure_kind
                    is TerminalIngressFailureKindV49E.CLOCK_DISAGREEMENT
                    and wall_due == monotonic_due
                )
                or pending_terminal_ingress_failure is not None
            ):
                raise CanonicalizationError(
                    "terminal-ingress failure differs from command/owner evidence"
                )
            pending_terminal_ingress_failure = (payload.failure_kind, event_id)
        elif event.event_kind is TransportActorEventKindV49C.OUTBOUND_WIRE_PREPARED:
            assert type(payload) is OutboundWirePreparedPayloadV49C
            if payload.outbound_operation_id in outbound_operation_ids:
                raise CanonicalizationError("outbound operation identity is duplicated")
            if payload.wire_origin is OutboundWireOriginV49C.AUTOMATIC_PROTOCOL:
                if (
                    not pending_parser_output_event_ids
                    or payload.source_parser_event_id
                    != pending_parser_output_event_ids[0]
                ):
                    raise CanonicalizationError(
                        "automatic wire doesn't consume the oldest unconsumed parser output"
                    )
                assert payload.source_parser_event_id is not None
                source = events_by_id.get(payload.source_parser_event_id)
                if (
                    source is None
                    or source.event_kind
                    is not TransportActorEventKindV49C.PARSER_TRANSITION
                ):
                    raise CanonicalizationError(
                        "automatic wire lacks prior parser source"
                    )
                source_payload = source.payload
                assert type(source_payload) is ParserTransitionPayloadV49C
                source_chunks = tuple(
                    base64.b64decode(value, validate=True)
                    for value in source_payload.ordered_protocol_output_chunks_base64
                )
                output_opcode, output_payload = (
                    _decode_single_automatic_protocol_output_v49c(source_chunks)
                )
                if (
                    payload.prepared_at < source_payload.processed_at
                    or payload.prepared_monotonic_ns
                    < source_payload.processed_monotonic_ns
                    or payload.ordered_wire_chunks_base64
                    != source_payload.ordered_protocol_output_chunks_base64
                    or payload.ordered_wire_chunks_sha256
                    != source_payload.ordered_protocol_output_chunks_sha256
                    or payload.wire_batch_sha256
                    != source_payload.protocol_output_batch_sha256
                    or payload.logical_opcode is not output_opcode
                    or payload.logical_payload_octets != len(output_payload)
                    or payload.logical_payload_sha256
                    != hashlib.sha256(output_payload).hexdigest()
                ):
                    raise CanonicalizationError(
                        "automatic wire differs from its exact parser output"
                    )
                pending_parser_output_event_ids.pop(0)
            else:
                if pending_parser_output_event_ids:
                    raise CanonicalizationError(
                        "non-automatic wire cannot reorder an unconsumed "
                        "automatic output"
                    )
                if (
                    local_shutdown_command_event_id is not None
                    and payload.wire_origin
                    is not OutboundWireOriginV49C.LOCAL_TERMINAL_COMMAND
                ):
                    raise CanonicalizationError(
                        "local shutdown command forbids later application output"
                    )
                if payload.wire_origin is (
                    OutboundWireOriginV49C.LOCAL_TERMINAL_COMMAND
                ):
                    current_cursor = (
                        WebSocketParserCursorV49C(
                            cursor_sequence=0,
                            next_stream_octet=0,
                            websocket_state=WebSocketParserStateV49C.OPEN,
                        )
                        if parser_cursor is None
                        else parser_cursor
                    )
                    expected_operation_id = (
                        derive_local_terminal_command_operation_id_v49e(
                            transport_session_id=event.transport_session_id,
                            actor_predecessor_event_id=event.previous_event_id,
                            logical_payload_sha256=(payload.logical_payload_sha256),
                            logical_payload_octets=payload.logical_payload_octets,
                            ordered_wire_chunks_sha256=(
                                payload.ordered_wire_chunks_sha256
                            ),
                            wire_batch_sha256=payload.wire_batch_sha256,
                            wire_octets=payload.wire_octets,
                        )
                    )
                    if payload.outbound_operation_id != expected_operation_id:
                        raise CanonicalizationError(
                            "local terminal command operation identity differs "
                            "from its actor predecessor and exact wire"
                        )
                    if (
                        local_shutdown_command_event_id is None
                        or local_shutdown_command is None
                        or local_terminal_wire_event_id is not None
                        or event.previous_event_id != local_shutdown_command_event_id
                        or terminal_state.ws_close_sent
                        or terminal_state.ws_close_received
                        or terminal_state.ws_output_fully_kernel_accepted
                        or current_cursor.websocket_state
                        is not WebSocketParserStateV49C.OPEN
                        or payload.prepared_at < local_shutdown_command.started_at
                        or payload.prepared_monotonic_ns
                        <= local_shutdown_command.started_monotonic_ns
                        or payload.send_not_after
                        != local_shutdown_command.shutdown_deadline_at
                        or payload.send_not_after_monotonic_ns
                        != local_shutdown_command.shutdown_deadline_monotonic_ns
                    ):
                        raise CanonicalizationError(
                            "local Close wire differs from its exact durable "
                            "shutdown command and deadline"
                        )
                    local_terminal_wire_event_id = event_id
            wire_events[event_id] = payload
            wire_queue.append(event_id)
            outbound_operation_ids.add(payload.outbound_operation_id)
            if payload.logical_opcode is WebSocketOpcodeV49C.CLOSE:
                unmarked_ws_close_wires.add(payload.outbound_operation_id)
        elif event.event_kind is TransportActorEventKindV49C.WRITE_PERMIT_CONSUMED:
            assert type(payload) is WritePermitConsumedPayloadV49C
            wire = wire_events.get(payload.outbound_wire_prepared_event_id)
            wire_event = events_by_id.get(payload.outbound_wire_prepared_event_id)
            if (
                wire is None
                or wire_event is None
                or not wire_queue
                or payload.outbound_wire_prepared_event_id != wire_queue[0]
                or active_permit_event_id is not None
                or active_tls_event_id is not None
                or payload.permit_id
                != derive_actor_write_permit_id_v49c(
                    outbound_operation_id=wire.outbound_operation_id,
                    outbound_wire_prepared_event_id=(
                        payload.outbound_wire_prepared_event_id
                    ),
                    socket_lease_id=event.socket_lease_id,
                    writer_fence_token_sha256=(event.writer_fence_token_sha256),
                    writer_fence_generation=event.writer_fence_generation,
                )
                or payload.wire_batch_sha256 != wire.wire_batch_sha256
                or payload.wire_octets != wire.wire_octets
                or payload.send_not_after != wire.send_not_after
                or payload.send_not_after_monotonic_ns
                != wire.send_not_after_monotonic_ns
                or payload.consumed_monotonic_ns <= wire.prepared_monotonic_ns
            ):
                raise CanonicalizationError(
                    "write permit doesn't consume the oldest unresolved wire"
                )
            permit_events[event_id] = payload
            active_permit_event_id = event_id
        elif event.event_kind is TransportActorEventKindV49C.TLS_CIPHERTEXT_PREPARED:
            assert type(payload) is TlsCiphertextPreparedPayloadV49C
            wire = wire_events.get(payload.outbound_wire_prepared_event_id)
            permit = permit_events.get(payload.write_permit_consumed_event_id)
            if (
                wire is None
                or permit is None
                or not wire_queue
                or payload.outbound_wire_prepared_event_id != wire_queue[0]
                or payload.write_permit_consumed_event_id != active_permit_event_id
                or active_tls_event_id is not None
                or permit.outbound_wire_prepared_event_id
                != payload.outbound_wire_prepared_event_id
                or payload.plaintext_batch_sha256 != wire.wire_batch_sha256
                or payload.plaintext_octets != wire.wire_octets
                or payload.prepared_monotonic_ns <= permit.consumed_monotonic_ns
            ):
                raise CanonicalizationError("TLS preparation differs from wire/permit")
            tls_events[event_id] = payload
            tls_offsets[event_id] = 0
            tls_attempt_ordinals[event_id] = 0
            tls_result_ids[event_id] = []
            active_tls_event_id = event_id
        elif event.event_kind is TransportActorEventKindV49C.KERNEL_SEND_ATTEMPT:
            assert type(payload) is KernelSendAttemptPayloadV49C
            tls = tls_events.get(payload.tls_ciphertext_prepared_event_id)
            tls_id = payload.tls_ciphertext_prepared_event_id
            previous_results = tls_result_ids.get(tls_id, [])
            prior_monotonic_ns = (
                -1
                if tls is None
                else (
                    tls.prepared_monotonic_ns
                    if not previous_results
                    else result_events[previous_results[-1]].observed_monotonic_ns
                )
            )
            if (
                tls is None
                or tls_id != active_tls_event_id
                or payload.ciphertext_batch_sha256 != tls.ciphertext_batch_sha256
                or payload.ciphertext_octets != tls.ciphertext_octets
                or payload.ciphertext_start_octet != tls_offsets[tls_id]
                or payload.kernel_attempt_ordinal != tls_attempt_ordinals[tls_id] + 1
                or unmatched_attempts
                or terminal_state.has_pending_send_attempt
                or awaiting_terminal_resolution is not None
                or payload.attempted_monotonic_ns <= prior_monotonic_ns
            ):
                raise CanonicalizationError("kernel attempt isn't the next exact send")
            tls_attempt_ordinals[tls_id] = payload.kernel_attempt_ordinal
            attempt_events[event_id] = payload
            unmatched_attempts.add(event_id)
        elif event.event_kind is TransportActorEventKindV49C.KERNEL_SEND_RESULT:
            assert type(payload) is KernelSendResultPayloadV49C
            attempt = attempt_events.get(payload.kernel_send_attempt_event_id)
            if (
                attempt is None
                or payload.kernel_send_attempt_event_id not in unmatched_attempts
            ):
                raise CanonicalizationError("kernel result lacks one unmatched attempt")
            exact_names = (
                "tls_ciphertext_prepared_event_id",
                "kernel_attempt_ordinal",
                "ciphertext_batch_sha256",
                "ciphertext_octets",
                "ciphertext_start_octet",
                "requested_octets",
            )
            if any(
                getattr(payload, name) != getattr(attempt, name) for name in exact_names
            ):
                raise CanonicalizationError(
                    "kernel result differs from its exact attempt"
                )
            if payload.observed_monotonic_ns <= attempt.attempted_monotonic_ns:
                raise CanonicalizationError("kernel result doesn't follow its attempt")
            if (
                terminal_state.pending_send_attempt_id
                != payload.kernel_send_attempt_event_id
            ):
                raise CanonicalizationError(
                    "kernel result lacks its durable terminal SEND_ATTEMPT_STARTED"
                )
            unmatched_attempts.remove(payload.kernel_send_attempt_event_id)
            tls_offsets[payload.tls_ciphertext_prepared_event_id] = (
                payload.resulting_ciphertext_offset
            )
            result_events[event_id] = payload
            tls_result_ids[payload.tls_ciphertext_prepared_event_id].append(event_id)
            awaiting_terminal_resolution = payload.kernel_send_attempt_event_id
        elif event.event_kind is TransportActorEventKindV49C.KERNEL_SEND_FAILURE:
            assert type(payload) is KernelSendFailurePayloadV49E
            attempt = attempt_events.get(payload.kernel_send_attempt_event_id)
            tls = (
                None
                if attempt is None
                else tls_events.get(attempt.tls_ciphertext_prepared_event_id)
            )
            wire = (
                None
                if tls is None
                else wire_events.get(tls.outbound_wire_prepared_event_id)
            )
            exact_names = (
                "tls_ciphertext_prepared_event_id",
                "kernel_attempt_ordinal",
                "ciphertext_batch_sha256",
                "ciphertext_octets",
                "ciphertext_start_octet",
                "requested_octets",
            )
            exact_slice_sha256 = (
                None
                if tls is None
                else hashlib.sha256(
                    b"".join(
                        base64.b64decode(chunk, validate=True)
                        for chunk in tls.ordered_ciphertext_chunks_base64
                    )[
                        payload.ciphertext_start_octet : payload.ciphertext_start_octet
                        + payload.requested_octets
                    ]
                ).hexdigest()
            )
            owner_before_syscall = (
                payload.failure_kind
                is KernelSendFailureKindV49E.DEADLINE_EXPIRED_BEFORE_SYSCALL
            )
            sealed_no_acceptance = (
                payload.failure_kind
                is KernelSendFailureKindV49E.DEADLINE_EXPIRED_NO_KERNEL_ACCEPTANCE
            )
            clock_disagreement = (
                payload.failure_kind is KernelSendFailureKindV49E.CLOCK_DISAGREEMENT
            )
            expected_owner_no_observation_evidence_id = (
                None
                if not owner_before_syscall
                else _derive_owner_deadline_no_observation_evidence_id_v49e(
                    transport_session_id=event.transport_session_id,
                    kernel_socket_identity=payload.kernel_socket_identity,
                    driver_evidence_nonce_sha256=(payload.driver_evidence_nonce_sha256),
                    operation=payload.owner_deadline_operation,
                    deadline_ns=payload.shutdown_deadline_monotonic_ns,
                )
            )
            expected_driver_send_evidence_id = (
                None
                if not sealed_no_acceptance
                else _derive_driver_send_deadline_evidence_id_v49e(
                    driver_evidence_nonce_sha256=(payload.driver_evidence_nonce_sha256),
                    send_kind=payload.send_kind,
                    transport_sequence=payload.transport_sequence,
                    ciphertext_batch_sha256=payload.ciphertext_batch_sha256,
                    ciphertext_octets=payload.ciphertext_octets,
                    ciphertext_start_octet=payload.ciphertext_start_octet,
                    requested_octets=payload.requested_octets,
                    exact_slice_sha256=payload.exact_slice_sha256,
                    deadline_ns=payload.shutdown_deadline_monotonic_ns,
                    would_block_count=payload.would_block_count,
                )
            )
            expected_owner_send_evidence_id = (
                None
                if not sealed_no_acceptance
                else _derive_owner_send_deadline_evidence_id_v49e(
                    transport_session_id=event.transport_session_id,
                    kernel_socket_identity=payload.kernel_socket_identity,
                    driver_evidence_nonce_sha256=(payload.driver_evidence_nonce_sha256),
                    send_kind=payload.send_kind,
                    transport_sequence=payload.transport_sequence,
                    ciphertext_batch_sha256=payload.ciphertext_batch_sha256,
                    ciphertext_octets=payload.ciphertext_octets,
                    ciphertext_start_octet=payload.ciphertext_start_octet,
                    requested_octets=payload.requested_octets,
                    exact_slice_sha256=payload.exact_slice_sha256,
                    deadline_ns=payload.shutdown_deadline_monotonic_ns,
                    would_block_count=payload.would_block_count,
                    driver_evidence_id=expected_driver_send_evidence_id,
                )
            )
            local_command_profile = (
                wire is not None
                and wire.wire_origin is OutboundWireOriginV49C.LOCAL_TERMINAL_COMMAND
                and local_shutdown_command_event_id is not None
                and local_shutdown_command is not None
            )
            peer_first_profile = (
                wire is not None
                and wire.wire_origin is OutboundWireOriginV49C.AUTOMATIC_PROTOCOL
                and wire.logical_opcode is WebSocketOpcodeV49C.CLOSE
                and local_shutdown_command_event_id is None
            )
            expected_deadline_ns = (
                local_shutdown_command.shutdown_deadline_monotonic_ns
                if local_command_profile
                else None
                if wire is None
                else wire.send_not_after_monotonic_ns
            )
            expected_deadline_at = (
                local_shutdown_command.shutdown_deadline_at
                if local_command_profile
                else None
                if wire is None
                else wire.send_not_after
            )
            expected_command_event_id = (
                local_shutdown_command_event_id if local_command_profile else None
            )
            failure_timeout_cause = (
                V49E_LOCAL_SHUTDOWN_CLOCK_DISAGREEMENT_CAUSE
                if clock_disagreement
                else (
                    V49E_LOCAL_SHUTDOWN_COMMAND_DEADLINE_EXPIRED_CAUSE
                    if local_command_profile
                    else V49E_WEBSOCKET_CLOSE_DEADLINE_EXPIRED_CAUSE
                )
            )
            if (
                attempt is None
                or tls is None
                or wire is None
                or not (local_command_profile or peer_first_profile)
                or payload.local_shutdown_command_started_event_id
                != expected_command_event_id
                or payload.shutdown_deadline_monotonic_ns != expected_deadline_ns
                or payload.kernel_send_attempt_event_id not in unmatched_attempts
                or terminal_state.pending_send_attempt_id
                != payload.kernel_send_attempt_event_id
                or any(
                    getattr(payload, name) != getattr(attempt, name)
                    for name in exact_names
                )
                or expected_deadline_at is None
                or (
                    not clock_disagreement
                    and (
                        payload.observed_monotonic_ns
                        < payload.shutdown_deadline_monotonic_ns
                        or payload.observed_at < expected_deadline_at
                    )
                )
                or (
                    clock_disagreement
                    and (
                        payload.observed_monotonic_ns
                        >= payload.shutdown_deadline_monotonic_ns
                    )
                    == (payload.observed_at >= expected_deadline_at)
                )
                or payload.observed_monotonic_ns <= attempt.attempted_monotonic_ns
                or (
                    sealed_no_acceptance
                    and payload.exact_slice_sha256 != exact_slice_sha256
                )
                or (
                    owner_before_syscall
                    and payload.owner_evidence_id
                    != expected_owner_no_observation_evidence_id
                )
                or (
                    sealed_no_acceptance
                    and (
                        payload.driver_evidence_id != expected_driver_send_evidence_id
                        or payload.owner_evidence_id != expected_owner_send_evidence_id
                    )
                )
                or (
                    sealed_no_acceptance
                    and payload.send_kind
                    != (
                        "LOCAL_WEBSOCKET_CLOSE"
                        if local_command_profile
                        else "AUTOMATIC_WEBSOCKET_CLOSE"
                    )
                )
            ):
                raise CanonicalizationError(
                    "kernel send failure differs from exact local or peer-first Close"
                )
            unmatched_attempts.remove(payload.kernel_send_attempt_event_id)
            kernel_send_failure_events[event_id] = payload
            awaiting_terminal_resolution = payload.kernel_send_attempt_event_id
            kernel_send_failure_awaiting_resolution = (
                event_id,
                failure_timeout_cause,
            )
        elif (
            event.event_kind is TransportActorEventKindV49C.OUTBOUND_DISPATCH_COMPLETED
        ):
            assert type(payload) is OutboundDispatchCompletedPayloadV49C
            wire = wire_events.get(payload.outbound_wire_prepared_event_id)
            permit = permit_events.get(payload.write_permit_consumed_event_id)
            tls = tls_events.get(payload.tls_ciphertext_prepared_event_id)
            results = tuple(
                result_events.get(result_id)
                for result_id in payload.kernel_send_result_event_ids
            )
            if (
                wire is None
                or permit is None
                or tls is None
                or not wire_queue
                or payload.outbound_wire_prepared_event_id != wire_queue[0]
                or payload.write_permit_consumed_event_id != active_permit_event_id
                or payload.tls_ciphertext_prepared_event_id != active_tls_event_id
                or any(result is None for result in results)
                or payload.kernel_send_result_event_ids
                != tuple(tls_result_ids[payload.tls_ciphertext_prepared_event_id])
                or permit.outbound_wire_prepared_event_id
                != payload.outbound_wire_prepared_event_id
                or tls.outbound_wire_prepared_event_id
                != payload.outbound_wire_prepared_event_id
                or tls.write_permit_consumed_event_id
                != payload.write_permit_consumed_event_id
                or payload.ciphertext_batch_sha256 != tls.ciphertext_batch_sha256
                or payload.ciphertext_octets != tls.ciphertext_octets
                or payload.submitted_ciphertext_octets
                != tls_offsets[payload.tls_ciphertext_prepared_event_id]
                or unmatched_attempts
                or terminal_state.has_pending_send_attempt
                or awaiting_terminal_resolution is not None
                or payload.completed_monotonic_ns <= results[-1].observed_monotonic_ns
            ):
                raise CanonicalizationError(
                    "dispatch completion differs from send chain"
                )
            wire_queue.pop(0)
            active_permit_event_id = None
            active_tls_event_id = None
            if wire.logical_opcode is WebSocketOpcodeV49C.CLOSE:
                fully_dispatched_close_obligations.add(
                    (
                        OutboundObligationLayerV49C.WEBSOCKET_CLOSE,
                        wire.outbound_operation_id,
                    )
                )
        elif (
            event.event_kind
            is TransportActorEventKindV49C.APPLICATION_MESSAGE_COMMITTED
        ):
            assert type(payload) is ApplicationMessageCommittedPayloadV49E
            if not pending_application_messages:
                raise CanonicalizationError(
                    "application commit lacks one uncommitted parser message"
                )
            expected_message = pending_application_messages[0]
            if (
                payload.source_parser_event_ids
                != expected_message.source_parser_event_ids
                or payload.message_opcode is not expected_message.message_opcode
                or payload.message_payload_octets
                != expected_message.message_payload_octets
                or (
                    expected_message.directly_verifiable_payload_sha256 is not None
                    and payload.message_payload_sha256
                    != expected_message.directly_verifiable_payload_sha256
                )
            ):
                raise CanonicalizationError(
                    "application commit differs from the oldest complete parser message"
                )
            source_payloads: list[ParserTransitionPayloadV49C] = []
            for source_event_id in payload.source_parser_event_ids:
                source_event = events_by_id.get(source_event_id)
                if (
                    source_event is None
                    or source_event.event_kind
                    is not TransportActorEventKindV49C.PARSER_TRANSITION
                    or type(source_event.payload) is not ParserTransitionPayloadV49C
                ):
                    raise CanonicalizationError(
                        "application commit source is not a prior parser event"
                    )
                source_payloads.append(source_event.payload)
            if any(
                payload.classified_at < source.processed_at
                or payload.classified_monotonic_ns < source.processed_monotonic_ns
                for source in source_payloads
            ):
                raise CanonicalizationError(
                    "application classification predates parser completion"
                )
            source_raws = (
                raw_events[source.raw_ingress_commit_id]
                for source in source_payloads
                for source in source.source_slices
            )
            if any(
                payload.received_at < raw.received_at
                or payload.received_monotonic_ns < raw.received_monotonic_ns
                for raw in source_raws
            ):
                raise CanonicalizationError(
                    "application receipt predates its raw parser source"
                )
            identities = (
                (payload.message_receipt_id, application_message_receipt_ids),
                (payload.physical_message_id, physical_message_ids),
                (
                    payload.provider_message_disposition_id,
                    provider_message_disposition_ids,
                ),
                (payload.message_disposition_id, message_disposition_ids),
            )
            if any(identity in seen for identity, seen in identities):
                raise CanonicalizationError(
                    "application message or disposition identity is duplicated"
                )
            for identity, seen in identities:
                seen.add(identity)
            pending_application_messages.pop(0)
            application_message_events[event_id] = payload
        elif event.event_kind is TransportActorEventKindV49C.SUBSCRIPTION_ACK_BOUND:
            assert type(payload) is SubscriptionAckBoundPayloadV49E
            source_application = application_message_events.get(
                payload.source_application_message_event_id
            )
            if (
                source_application is None
                or source_application.disposition_kind
                is not MessageDispositionKind.CONTROL_SUBSCRIPTION_ACK
                or source_application.message_opcode is not WebSocketOpcodeV49C.TEXT
                or payload.provider_message_disposition_id
                != source_application.provider_message_disposition_id
                or payload.message_disposition_id
                != source_application.message_disposition_id
                or payload.raw_ack_sha256 != source_application.message_payload_sha256
                or payload.ack_received_at != source_application.received_at
                or payload.ack_received_monotonic_ns
                != source_application.received_monotonic_ns
                or payload.bound_at < source_application.classified_at
                or payload.bound_monotonic_ns
                < source_application.classified_monotonic_ns
            ):
                raise CanonicalizationError(
                    "subscription ACK differs from its exact classified Text message"
                )
            dispatch, wire, first_attempt = subscription_dispatch(
                intent_id=payload.outbound_subscription_intent_id,
                dispatch_event_id=(payload.subscription_dispatch_completed_event_id),
            )
            if (
                payload.request_command_sha256 != wire.logical_payload_sha256
                or payload.dispatch_started_at != first_attempt.attempted_at
                or payload.dispatch_started_monotonic_ns
                != first_attempt.attempted_monotonic_ns
                or payload.dispatch_completed_at != dispatch.completed_at
                or payload.dispatch_completed_monotonic_ns
                != dispatch.completed_monotonic_ns
            ):
                raise CanonicalizationError(
                    "subscription ACK differs from its exact dispatch evidence"
                )
            if (
                payload.outbound_subscription_intent_id in subscription_outcomes
                or payload.source_application_message_event_id
                in bound_ack_application_event_ids
                or payload.subscription_ack_binding_id in subscription_ack_binding_ids
            ):
                raise CanonicalizationError(
                    "subscription ACK message, binding, or intent is already consumed"
                )
            subscription_outcomes[payload.outbound_subscription_intent_id] = (
                TransportActorEventKindV49C.SUBSCRIPTION_ACK_BOUND
            )
            bound_ack_application_event_ids.add(
                payload.source_application_message_event_id
            )
            subscription_ack_binding_ids.add(payload.subscription_ack_binding_id)
        elif event.event_kind is TransportActorEventKindV49C.ACK_DEADLINE_EXPIRED:
            assert type(payload) is AckDeadlineExpiredPayloadV49E
            dispatch, _, _ = subscription_dispatch(
                intent_id=payload.outbound_subscription_intent_id,
                dispatch_event_id=(payload.subscription_dispatch_completed_event_id),
            )
            if (
                payload.dispatch_completed_at != dispatch.completed_at
                or payload.dispatch_completed_monotonic_ns
                != dispatch.completed_monotonic_ns
            ):
                raise CanonicalizationError(
                    "ACK deadline differs from its exact completed dispatch"
                )
            if payload.outbound_subscription_intent_id in subscription_outcomes:
                raise CanonicalizationError(
                    "subscription already has an ACK or timeout outcome"
                )
            subscription_outcomes[payload.outbound_subscription_intent_id] = (
                TransportActorEventKindV49C.ACK_DEADLINE_EXPIRED
            )
            awaiting_ack_timeout_terminal = True
        elif (
            event.event_kind
            is TransportActorEventKindV49C.TLS_PROTOCOL_OPERATION_STARTED
        ):
            assert type(payload) is TlsProtocolOperationStartedPayloadV49E
            expected_tls_operation_id = sha256_digest(
                {
                    "domain": "RiskYieldMMTlsProtocolOperationV4_9E",
                    "transport_session_id": event.transport_session_id,
                    "operation_sequence": payload.operation_sequence,
                    "local_shutdown_command_started_event_id": (
                        payload.local_shutdown_command_started_event_id
                    ),
                    "purpose": payload.purpose.value,
                    "cause_actor_event_id": payload.cause_actor_event_id,
                    "driver_evidence_nonce_sha256": (
                        payload.driver_evidence_nonce_sha256
                    ),
                }
            )
            if (
                local_shutdown_command_event_id is None
                or local_shutdown_command is None
                or payload.local_shutdown_command_started_event_id
                != local_shutdown_command_event_id
                or payload.cause_actor_event_id not in events_by_id
                or pending_tls_protocol_operation_event_id is not None
                or active_tls_control_event_id is not None
                or unmatched_tls_control_attempts
                or payload.operation_sequence
                != last_tls_protocol_operation_sequence + 1
                or payload.tls_operation_id != expected_tls_operation_id
                or payload.started_monotonic_ns
                >= local_shutdown_command.shutdown_deadline_monotonic_ns
                or payload.started_at >= local_shutdown_command.shutdown_deadline_at
                or payload.tls_operation_id
                in {
                    item.tls_operation_id
                    for item in tls_protocol_operation_events.values()
                }
            ):
                raise CanonicalizationError(
                    "TLS operation is not the next exact write-ahead operation"
                )
            if (
                tls_driver_evidence_nonce_sha256 is not None
                and payload.driver_evidence_nonce_sha256
                != tls_driver_evidence_nonce_sha256
            ):
                raise CanonicalizationError(
                    "TLS operation changes retained-driver evidence"
                )
            if payload.purpose is TlsProtocolOperationPurposeV49E.LOCAL_CLOSE_NOTIFY:
                websocket_causes = tuple(
                    marker_id
                    for marker_id in (
                        ws_close_received_marker_event_id,
                        ws_close_fully_accepted_marker_event_id,
                    )
                    if marker_id is not None
                )
                latest_websocket_cause = (
                    None
                    if len(websocket_causes) != 2
                    else max(
                        websocket_causes,
                        key=lambda marker_id: events_by_id[marker_id].actor_sequence,
                    )
                )
                if (
                    local_tls_marker_event_id is not None
                    or completed_local_tls_control_event_id is not None
                    or not terminal_state.ws_close_sent
                    or not terminal_state.ws_close_received
                    or not terminal_state.ws_output_fully_kernel_accepted
                    or ws_close_sent_marker_event_id is None
                    or payload.cause_actor_event_id != latest_websocket_cause
                ):
                    raise CanonicalizationError(
                        "local close_notify operation lacks complete WebSocket Close evidence"
                    )
            elif payload.purpose is TlsProtocolOperationPurposeV49E.PEER_SHUTDOWN_POLL:
                expected_poll_cause = (
                    tcp_half_close_marker_event_id
                    if last_tls_shutdown_observation_sequence == 0
                    else last_tls_shutdown_marker_event_id
                )
                if (
                    local_tls_marker_event_id is None
                    or tcp_half_close_marker_event_id is None
                    or expected_poll_cause is None
                    or payload.cause_actor_event_id != expected_poll_cause
                ):
                    raise CanonicalizationError(
                        "peer TLS shutdown poll must follow successful local SHUT_WR "
                        "or the immediately preceding retained shutdown marker"
                    )
            tls_protocol_operation_events[event_id] = payload
            pending_tls_protocol_operation_event_id = event_id
            last_tls_protocol_operation_sequence = payload.operation_sequence
            if tls_driver_evidence_nonce_sha256 is None:
                tls_driver_evidence_nonce_sha256 = payload.driver_evidence_nonce_sha256
        elif (
            event.event_kind
            is TransportActorEventKindV49C.TLS_PROTOCOL_OPERATION_FAILED
        ):
            assert type(payload) is TlsProtocolOperationFailedPayloadV49E
            operation = tls_protocol_operation_events.get(
                payload.tls_protocol_operation_started_event_id
            )
            after_progress = (
                payload.failure_kind
                is TlsProtocolOperationFailureKindV49E.DEADLINE_EXPIRED_AFTER_PROGRESS
            )
            no_observation = (
                payload.failure_kind
                is TlsProtocolOperationFailureKindV49E.DEADLINE_EXPIRED_NO_OBSERVATION
            )
            unsendable = (
                payload.failure_kind
                is TlsProtocolOperationFailureKindV49E.UNSENDABLE_POST_HANDSHAKE_OUTPUT_AFTER_SHUT_WR
            )
            deadline_failure = no_observation or after_progress
            wall_due = (
                local_shutdown_command is not None
                and payload.observed_at >= local_shutdown_command.shutdown_deadline_at
            )
            monotonic_due = (
                local_shutdown_command is not None
                and payload.observed_monotonic_ns
                >= local_shutdown_command.shutdown_deadline_monotonic_ns
            )
            expected_classification = (
                None
                if not deadline_failure
                else (
                    LocalShutdownDeadlineClassificationV49E.BOTH_DUE
                    if wall_due and monotonic_due
                    else (
                        LocalShutdownDeadlineClassificationV49E.CLOCK_DISAGREEMENT
                        if wall_due != monotonic_due
                        else LocalShutdownDeadlineClassificationV49E.OWNER_EVIDENCE_BEFORE_BOTH_CLOCKS
                    )
                )
            )
            expected_no_observation_owner_evidence_id = (
                None
                if not no_observation
                else _derive_owner_deadline_no_observation_evidence_id_v49e(
                    transport_session_id=event.transport_session_id,
                    kernel_socket_identity=(
                        payload.deadline_no_observation_kernel_socket_identity
                    ),
                    driver_evidence_nonce_sha256=(payload.driver_evidence_nonce_sha256),
                    operation=payload.deadline_no_observation_operation,
                    deadline_ns=payload.shutdown_deadline_monotonic_ns,
                )
            )
            expected_driver_evidence_id = (
                None
                if not after_progress
                else _derive_driver_deadline_after_progress_evidence_id_v49e(
                    driver_evidence_nonce_sha256=(payload.driver_evidence_nonce_sha256),
                    operation=payload.deadline_after_progress_operation,
                    deadline_ns=payload.shutdown_deadline_monotonic_ns,
                    ciphertext_octets_received=(
                        payload.deadline_after_progress_ciphertext_octets
                    ),
                    ciphertext_sha256=(
                        payload.deadline_after_progress_ciphertext_sha256
                    ),
                )
            )
            expected_owner_evidence_id = (
                None
                if not after_progress
                else _derive_owner_deadline_after_progress_evidence_id_v49e(
                    transport_session_id=event.transport_session_id,
                    kernel_socket_identity=(
                        payload.deadline_after_progress_kernel_socket_identity
                    ),
                    driver_evidence_nonce_sha256=(payload.driver_evidence_nonce_sha256),
                    operation=payload.deadline_after_progress_operation,
                    deadline_ns=payload.shutdown_deadline_monotonic_ns,
                    ciphertext_octets_received=(
                        payload.deadline_after_progress_ciphertext_octets
                    ),
                    ciphertext_sha256=(
                        payload.deadline_after_progress_ciphertext_sha256
                    ),
                    driver_evidence_id=expected_driver_evidence_id,
                )
            )
            expected_unsendable_driver_evidence_id = (
                None
                if not unsendable
                else sha256_digest(
                    {
                        "domain": "RiskYieldMMUnsendableTlsPostHandshakeOutputV4_9E",
                        "output_sequence": (payload.unsendable_driver_output_sequence),
                        "driver_evidence_nonce_sha256": (
                            payload.driver_evidence_nonce_sha256
                        ),
                        "ciphertext_sha256": (payload.unsendable_ciphertext_sha256),
                        "ciphertext_octets": payload.unsendable_ciphertext_octets,
                    }
                )
            )
            expected_unsendable_owner_evidence_id = (
                None
                if not unsendable
                else sha256_digest(
                    {
                        "domain": "RiskYieldMMOwnerUnsendableTlsPostHandshakeOutputV4_9E",
                        "transport_session_id": event.transport_session_id,
                        "kernel_socket_identity": (
                            payload.unsendable_kernel_socket_identity
                        ),
                        "driver_unsendable_output_id": (
                            expected_unsendable_driver_evidence_id
                        ),
                        "driver_output_sequence": (
                            payload.unsendable_driver_output_sequence
                        ),
                        "driver_evidence_nonce_sha256": (
                            payload.driver_evidence_nonce_sha256
                        ),
                        "ciphertext_sha256": (payload.unsendable_ciphertext_sha256),
                        "ciphertext_octets": payload.unsendable_ciphertext_octets,
                    }
                )
            )
            if (
                operation is None
                or local_shutdown_command is None
                or payload.tls_protocol_operation_started_event_id
                != pending_tls_protocol_operation_event_id
                or payload.tls_operation_id != operation.tls_operation_id
                or payload.purpose is not operation.purpose
                or payload.driver_evidence_nonce_sha256
                != operation.driver_evidence_nonce_sha256
                or payload.shutdown_deadline_monotonic_ns
                != local_shutdown_command.shutdown_deadline_monotonic_ns
                or payload.deadline_classification is not expected_classification
                or (
                    no_observation
                    and payload.deadline_no_observation_owner_evidence_id
                    != expected_no_observation_owner_evidence_id
                )
                or (
                    after_progress
                    and (
                        payload.deadline_after_progress_driver_evidence_id
                        != expected_driver_evidence_id
                        or payload.deadline_after_progress_owner_evidence_id
                        != expected_owner_evidence_id
                    )
                )
                or (
                    unsendable
                    and (
                        payload.unsendable_driver_evidence_id
                        != expected_unsendable_driver_evidence_id
                        or payload.unsendable_owner_evidence_id
                        != expected_unsendable_owner_evidence_id
                    )
                )
                or payload.observed_at < operation.started_at
                or payload.observed_monotonic_ns <= operation.started_monotonic_ns
                or pending_tls_operation_failure_marker is not None
            ):
                raise CanonicalizationError(
                    "TLS operation failure differs from its exact started operation"
                )
            pending_tls_protocol_operation_event_id = None
            pending_tls_operation_failure_marker = (payload, event_id)
        elif (
            event.event_kind
            is TransportActorEventKindV49C.TLS_CONTROL_CIPHERTEXT_PREPARED
        ):
            assert type(payload) is TlsControlCiphertextPreparedPayloadV49E
            operation = tls_protocol_operation_events.get(
                payload.tls_protocol_operation_started_event_id
            )
            expected_purpose = (
                TlsProtocolOperationPurposeV49E.LOCAL_CLOSE_NOTIFY
                if payload.control_kind is TlsControlOutputKindV49E.LOCAL_CLOSE_NOTIFY
                else TlsProtocolOperationPurposeV49E.OPAQUE_POST_HANDSHAKE_RESPONSE
            )
            if (
                operation is None
                or payload.tls_protocol_operation_started_event_id
                != pending_tls_protocol_operation_event_id
                or operation.purpose is not expected_purpose
                or payload.tls_operation_id != operation.tls_operation_id
                or payload.driver_evidence_nonce_sha256
                != operation.driver_evidence_nonce_sha256
                or payload.control_sequence != last_tls_control_sequence + 1
                or payload.prepared_at < operation.started_at
                or payload.prepared_monotonic_ns <= operation.started_monotonic_ns
                or active_tls_control_event_id is not None
            ):
                raise CanonicalizationError(
                    "TLS-control preparation differs from its exact started operation"
                )
            if (
                payload.control_kind is TlsControlOutputKindV49E.LOCAL_CLOSE_NOTIFY
                and completed_local_tls_control_event_id is not None
            ):
                raise CanonicalizationError("local close_notify was already prepared")
            tls_control_events[event_id] = payload
            tls_control_offsets[event_id] = 0
            tls_control_attempt_ordinals[event_id] = 0
            tls_control_result_ids[event_id] = []
            active_tls_control_event_id = event_id
            last_tls_control_sequence = payload.control_sequence
            pending_tls_protocol_operation_event_id = None
            if payload.control_kind is TlsControlOutputKindV49E.LOCAL_CLOSE_NOTIFY:
                pending_tls_control_prepared_marker_event_id = event_id
                peer_close_received_during_local_tls_preparation = (
                    payload.peer_close_notify_received_during_preparation
                )
        elif (
            event.event_kind
            is TransportActorEventKindV49C.TLS_CONTROL_KERNEL_SEND_ATTEMPT
        ):
            assert type(payload) is TlsControlKernelSendAttemptPayloadV49E
            control_id = payload.tls_control_ciphertext_prepared_event_id
            control = tls_control_events.get(control_id)
            previous_result_ids = tls_control_result_ids.get(control_id, [])
            prior_monotonic_ns = (
                -1
                if control is None
                else (
                    control.prepared_monotonic_ns
                    if not previous_result_ids
                    else tls_control_result_events[
                        previous_result_ids[-1]
                    ].observed_monotonic_ns
                )
            )
            if (
                control is None
                or local_shutdown_command_event_id is None
                or local_shutdown_command is None
                or payload.local_shutdown_command_started_event_id
                != local_shutdown_command_event_id
                or payload.shutdown_deadline_monotonic_ns
                != local_shutdown_command.shutdown_deadline_monotonic_ns
                or control_id != active_tls_control_event_id
                or payload.ciphertext_batch_sha256 != control.ciphertext_batch_sha256
                or payload.ciphertext_octets != control.ciphertext_octets
                or payload.ciphertext_start_octet != tls_control_offsets[control_id]
                or payload.kernel_attempt_ordinal
                != tls_control_attempt_ordinals[control_id] + 1
                or unmatched_tls_control_attempts
                or terminal_state.has_pending_send_attempt
                or payload.attempted_monotonic_ns <= prior_monotonic_ns
                or (
                    control.control_kind is TlsControlOutputKindV49E.LOCAL_CLOSE_NOTIFY
                    and local_tls_prepared_marker_event_id is None
                )
            ):
                raise CanonicalizationError(
                    "TLS-control attempt is not the next exact suffix send"
                )
            tls_control_attempt_ordinals[control_id] = payload.kernel_attempt_ordinal
            tls_control_attempt_events[event_id] = payload
            unmatched_tls_control_attempts.add(event_id)
            tls_control_attempt_awaiting_started_marker = event_id
        elif (
            event.event_kind
            is TransportActorEventKindV49C.TLS_CONTROL_KERNEL_SEND_RESULT
        ):
            assert type(payload) is TlsControlKernelSendResultPayloadV49E
            attempt = tls_control_attempt_events.get(
                payload.tls_control_kernel_send_attempt_event_id
            )
            if (
                attempt is None
                or payload.tls_control_kernel_send_attempt_event_id
                not in unmatched_tls_control_attempts
                or tls_control_attempt_awaiting_started_marker is not None
                or terminal_state.pending_send_attempt_id
                != payload.tls_control_kernel_send_attempt_event_id
            ):
                raise CanonicalizationError(
                    "TLS-control result lacks one unmatched write-ahead attempt"
                )
            exact_names = (
                "tls_control_ciphertext_prepared_event_id",
                "kernel_attempt_ordinal",
                "ciphertext_batch_sha256",
                "ciphertext_octets",
                "ciphertext_start_octet",
                "requested_octets",
            )
            if (
                any(
                    getattr(payload, name) != getattr(attempt, name)
                    for name in exact_names
                )
                or payload.observed_monotonic_ns <= attempt.attempted_monotonic_ns
            ):
                raise CanonicalizationError(
                    "TLS-control result differs from its exact attempt"
                )
            control_id = payload.tls_control_ciphertext_prepared_event_id
            control = tls_control_events[control_id]
            unmatched_tls_control_attempts.remove(
                payload.tls_control_kernel_send_attempt_event_id
            )
            tls_control_offsets[control_id] = payload.resulting_ciphertext_offset
            tls_control_result_events[event_id] = payload
            tls_control_result_ids[control_id].append(event_id)
            tls_control_result_awaiting_resolved_marker = (
                payload.tls_control_kernel_send_attempt_event_id,
                event_id,
            )
            if payload.resulting_ciphertext_offset == control.ciphertext_octets:
                active_tls_control_event_id = None
                if control.control_kind is TlsControlOutputKindV49E.LOCAL_CLOSE_NOTIFY:
                    completed_local_tls_control_event_id = control_id
        elif (
            event.event_kind
            is TransportActorEventKindV49C.TLS_CONTROL_KERNEL_SEND_FAILURE
        ):
            assert type(payload) is TlsControlKernelSendFailurePayloadV49E
            attempt = tls_control_attempt_events.get(
                payload.tls_control_kernel_send_attempt_event_id
            )
            control = (
                None
                if attempt is None
                else tls_control_events.get(
                    attempt.tls_control_ciphertext_prepared_event_id
                )
            )
            exact_names = (
                "tls_control_ciphertext_prepared_event_id",
                "kernel_attempt_ordinal",
                "ciphertext_batch_sha256",
                "ciphertext_octets",
                "ciphertext_start_octet",
                "requested_octets",
            )
            exact_slice_sha256 = (
                None
                if control is None
                else hashlib.sha256(
                    b"".join(
                        base64.b64decode(chunk, validate=True)
                        for chunk in control.ordered_ciphertext_chunks_base64
                    )[
                        payload.ciphertext_start_octet : payload.ciphertext_start_octet
                        + payload.requested_octets
                    ]
                ).hexdigest()
            )
            owner_before_syscall = (
                payload.failure_kind
                is KernelSendFailureKindV49E.DEADLINE_EXPIRED_BEFORE_SYSCALL
            )
            sealed_no_acceptance = (
                payload.failure_kind
                is KernelSendFailureKindV49E.DEADLINE_EXPIRED_NO_KERNEL_ACCEPTANCE
            )
            clock_disagreement = (
                payload.failure_kind is KernelSendFailureKindV49E.CLOCK_DISAGREEMENT
            )
            expected_owner_no_observation_evidence_id = (
                None
                if not owner_before_syscall
                else _derive_owner_deadline_no_observation_evidence_id_v49e(
                    transport_session_id=event.transport_session_id,
                    kernel_socket_identity=payload.kernel_socket_identity,
                    driver_evidence_nonce_sha256=(payload.driver_evidence_nonce_sha256),
                    operation=payload.owner_deadline_operation,
                    deadline_ns=payload.shutdown_deadline_monotonic_ns,
                )
            )
            expected_driver_send_evidence_id = (
                None
                if not sealed_no_acceptance
                else _derive_driver_send_deadline_evidence_id_v49e(
                    driver_evidence_nonce_sha256=(payload.driver_evidence_nonce_sha256),
                    send_kind=payload.send_kind,
                    transport_sequence=payload.transport_sequence,
                    ciphertext_batch_sha256=payload.ciphertext_batch_sha256,
                    ciphertext_octets=payload.ciphertext_octets,
                    ciphertext_start_octet=payload.ciphertext_start_octet,
                    requested_octets=payload.requested_octets,
                    exact_slice_sha256=payload.exact_slice_sha256,
                    deadline_ns=payload.shutdown_deadline_monotonic_ns,
                    would_block_count=payload.would_block_count,
                )
            )
            expected_owner_send_evidence_id = (
                None
                if not sealed_no_acceptance
                else _derive_owner_send_deadline_evidence_id_v49e(
                    transport_session_id=event.transport_session_id,
                    kernel_socket_identity=payload.kernel_socket_identity,
                    driver_evidence_nonce_sha256=(payload.driver_evidence_nonce_sha256),
                    send_kind=payload.send_kind,
                    transport_sequence=payload.transport_sequence,
                    ciphertext_batch_sha256=payload.ciphertext_batch_sha256,
                    ciphertext_octets=payload.ciphertext_octets,
                    ciphertext_start_octet=payload.ciphertext_start_octet,
                    requested_octets=payload.requested_octets,
                    exact_slice_sha256=payload.exact_slice_sha256,
                    deadline_ns=payload.shutdown_deadline_monotonic_ns,
                    would_block_count=payload.would_block_count,
                    driver_evidence_id=expected_driver_send_evidence_id,
                )
            )
            if (
                attempt is None
                or control is None
                or local_shutdown_command_event_id is None
                or local_shutdown_command is None
                or payload.local_shutdown_command_started_event_id
                != local_shutdown_command_event_id
                or payload.shutdown_deadline_monotonic_ns
                != local_shutdown_command.shutdown_deadline_monotonic_ns
                or payload.tls_control_kernel_send_attempt_event_id
                not in unmatched_tls_control_attempts
                or tls_control_attempt_awaiting_started_marker is not None
                or terminal_state.pending_send_attempt_id
                != payload.tls_control_kernel_send_attempt_event_id
                or any(
                    getattr(payload, name) != getattr(attempt, name)
                    for name in exact_names
                )
                or (
                    not clock_disagreement
                    and (
                        payload.observed_monotonic_ns
                        < local_shutdown_command.shutdown_deadline_monotonic_ns
                        or payload.observed_at
                        < local_shutdown_command.shutdown_deadline_at
                    )
                )
                or (
                    clock_disagreement
                    and (
                        payload.observed_monotonic_ns
                        >= local_shutdown_command.shutdown_deadline_monotonic_ns
                    )
                    == (
                        payload.observed_at
                        >= local_shutdown_command.shutdown_deadline_at
                    )
                )
                or payload.observed_monotonic_ns <= attempt.attempted_monotonic_ns
                or (
                    sealed_no_acceptance
                    and (
                        payload.exact_slice_sha256 != exact_slice_sha256
                        or payload.transport_sequence != control.control_sequence
                        or payload.driver_evidence_nonce_sha256
                        != control.driver_evidence_nonce_sha256
                        or payload.driver_evidence_id
                        != expected_driver_send_evidence_id
                        or payload.owner_evidence_id != expected_owner_send_evidence_id
                    )
                )
                or (
                    owner_before_syscall
                    and (
                        payload.driver_evidence_nonce_sha256
                        != control.driver_evidence_nonce_sha256
                        or payload.owner_evidence_id
                        != expected_owner_no_observation_evidence_id
                    )
                )
            ):
                raise CanonicalizationError(
                    "TLS-control send failure differs from exact shutdown attempt"
                )
            unmatched_tls_control_attempts.remove(
                payload.tls_control_kernel_send_attempt_event_id
            )
            tls_control_failure_events[event_id] = payload
            tls_control_failure_awaiting_resolved_marker = (
                payload.tls_control_kernel_send_attempt_event_id,
                event_id,
            )
        elif event.event_kind is TransportActorEventKindV49C.TLS_SHUTDOWN_OBSERVED:
            assert type(payload) is TlsShutdownObservedPayloadV49E
            operation = tls_protocol_operation_events.get(
                payload.tls_protocol_operation_started_event_id
            )
            if (
                peer_close_received_during_local_tls_preparation
                and peer_tls_marker_event_id is None
                and (
                    payload.observation_kind
                    is not TlsShutdownObservationKindV49E.PEER_CLOSE_NOTIFY
                    or payload.ciphertext_octets_received != 0
                )
            ):
                raise CanonicalizationError(
                    "peer close_notify received during local preparation requires "
                    "one zero-byte poll observation before later TLS/TCP facts"
                )
            if (
                operation is None
                or payload.tls_protocol_operation_started_event_id
                != pending_tls_protocol_operation_event_id
                or operation.purpose
                is not TlsProtocolOperationPurposeV49E.PEER_SHUTDOWN_POLL
                or payload.tls_operation_id != operation.tls_operation_id
                or payload.driver_evidence_nonce_sha256
                != operation.driver_evidence_nonce_sha256
                or payload.observation_sequence
                != last_tls_shutdown_observation_sequence + 1
                or payload.observation_id in tls_shutdown_observation_ids
                or payload.observed_at < operation.started_at
                or payload.observed_monotonic_ns <= operation.started_monotonic_ns
                or pending_shutdown_observation_marker is not None
            ):
                raise CanonicalizationError(
                    "TLS shutdown observation differs from its exact driver poll"
                )
            if (
                (
                    payload.observation_kind
                    is TlsShutdownObservationKindV49E.PEER_CLOSE_NOTIFY
                    and peer_tls_marker_event_id is not None
                )
                or (
                    payload.observation_kind is TlsShutdownObservationKindV49E.TCP_EOF
                    and tcp_eof_marker_event_id is not None
                )
                or (
                    payload.observation_kind is TlsShutdownObservationKindV49E.TCP_EOF
                    and payload.peer_close_notify_received
                    != (peer_tls_marker_event_id is not None)
                )
            ):
                raise CanonicalizationError(
                    "TLS shutdown fact is duplicate or contradicts prior peer evidence"
                )
            expected_driver_observation_id = sha256_digest(
                {
                    "domain": "RiskYieldMMTlsShutdownObservationV4_9E",
                    "observation_sequence": payload.observation_sequence,
                    "observation_kind": payload.observation_kind.value,
                    "driver_evidence_nonce_sha256": (
                        payload.driver_evidence_nonce_sha256
                    ),
                    "peer_close_notify_received": (payload.peer_close_notify_received),
                    "tcp_eof_received": payload.tcp_eof_received,
                    "truncated": payload.truncated,
                    "ciphertext_octets_received": (payload.ciphertext_octets_received),
                }
            )
            if payload.observation_id != expected_driver_observation_id:
                raise CanonicalizationError(
                    "TLS shutdown observation lacks its exact driver-derived identity"
                )
            expected_owner_observation_id = sha256_digest(
                {
                    "domain": "RiskYieldMMOwnerTlsShutdownObservationV4_9E",
                    "transport_session_id": event.transport_session_id,
                    "kernel_socket_identity": payload.owner_kernel_socket_identity,
                    "driver_observation_id": expected_driver_observation_id,
                    "driver_observation_sequence": payload.observation_sequence,
                    "driver_observation_kind": payload.observation_kind.value,
                }
            )
            if payload.owner_observation_id != expected_owner_observation_id:
                raise CanonicalizationError(
                    "TLS shutdown observation lacks its exact owner-derived identity"
                )
            if tls_shutdown_owner_kernel_socket_identity is None:
                tls_shutdown_owner_kernel_socket_identity = (
                    payload.owner_kernel_socket_identity
                )
            elif (
                payload.owner_kernel_socket_identity
                != tls_shutdown_owner_kernel_socket_identity
            ):
                raise CanonicalizationError(
                    "TLS shutdown observations change retained owner socket identity"
                )
            last_tls_shutdown_observation_sequence = payload.observation_sequence
            tls_shutdown_observation_ids.add(payload.observation_id)
            pending_shutdown_observation_marker = (
                payload.observation_kind,
                event_id,
            )
            pending_tls_protocol_operation_event_id = None
        elif event.event_kind is TransportActorEventKindV49C.TCP_HALF_CLOSE_ATTEMPT:
            assert type(payload) is TcpHalfCloseAttemptPayloadV49E
            control = tls_control_events.get(
                payload.tls_control_ciphertext_prepared_event_id
            )
            marker = events_by_id.get(payload.tls_close_notify_sent_event_id)
            expected_shutdown_token_id = sha256_digest(
                {
                    "domain": "RiskYieldMMTcpWriteShutdownTokenV4_9E",
                    "token_sequence": payload.token_sequence,
                    "transport_session_id": event.transport_session_id,
                    "tls_control_sequence": payload.tls_control_sequence,
                    "tls_ciphertext_batch_sha256": (
                        payload.tls_ciphertext_batch_sha256
                    ),
                    "tls_ciphertext_octets": payload.tls_ciphertext_octets,
                    "shutdown_deadline_monotonic_ns": (
                        payload.shutdown_deadline_monotonic_ns
                    ),
                }
            )
            if (
                tcp_half_close_attempt_event_id is not None
                or local_shutdown_command_event_id is None
                or local_shutdown_command is None
                or payload.local_shutdown_command_started_event_id
                != local_shutdown_command_event_id
                or payload.shutdown_deadline_monotonic_ns
                != local_shutdown_command.shutdown_deadline_monotonic_ns
                or payload.token_sequence != 1
                or payload.shutdown_token_id != expected_shutdown_token_id
                or local_tls_marker_event_id is None
                or local_tls_fully_accepted_marker_event_id is None
                or not terminal_state.tls_close_notify_fully_kernel_accepted
                or payload.tls_close_notify_sent_event_id != local_tls_marker_event_id
                or marker is None
                or marker.event_kind
                is not TransportActorEventKindV49C.TERMINAL_TRANSITION
                or type(marker.payload) is not TerminalTransitionPayloadV49C
                or marker.payload.kind
                is not TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_SENT
                or control is None
                or control.control_kind
                is not TlsControlOutputKindV49E.LOCAL_CLOSE_NOTIFY
                or payload.tls_control_ciphertext_prepared_event_id
                != completed_local_tls_control_event_id
                or payload.tls_control_sequence != control.control_sequence
                or payload.tls_ciphertext_batch_sha256
                != control.ciphertext_batch_sha256
                or payload.tls_ciphertext_octets != control.ciphertext_octets
                or payload.attempted_at >= local_shutdown_command.shutdown_deadline_at
                or payload.attempted_monotonic_ns <= marker.recorded_monotonic_ns
            ):
                raise CanonicalizationError(
                    "TCP half-close attempt lacks accepted local close_notify authority"
                )
            tcp_half_close_attempt_events[event_id] = payload
            tcp_half_close_attempt_event_id = event_id
        elif event.event_kind is TransportActorEventKindV49C.TCP_HALF_CLOSE_RESULT:
            assert type(payload) is TcpHalfCloseResultPayloadV49E
            attempt = tcp_half_close_attempt_events.get(
                payload.tcp_half_close_attempt_event_id
            )
            expected_shutdown_result_id = sha256_digest(
                {
                    "domain": "RiskYieldMMTcpWriteShutdownResultV4_9E",
                    "shutdown_token_id": payload.shutdown_token_id,
                    "shutdown_how": _V49E_LINUX_SHUT_WR_ABI_VALUE,
                    "kernel_accepted": (
                        payload.result_kind
                        is TcpHalfCloseResultKindV49E.KERNEL_ACCEPTED
                    ),
                    "error_code": payload.error_code,
                }
            )
            if (
                attempt is None
                or payload.tcp_half_close_attempt_event_id
                != tcp_half_close_attempt_event_id
                or tcp_half_close_result_event_id is not None
                or payload.shutdown_token_id != attempt.shutdown_token_id
                or payload.shutdown_how != attempt.shutdown_how
                or payload.shutdown_result_id != expected_shutdown_result_id
                or payload.observed_monotonic_ns <= attempt.attempted_monotonic_ns
                or (
                    payload.result_kind
                    is TcpHalfCloseResultKindV49E.DEADLINE_EXPIRED_BEFORE_SYSCALL
                    and (
                        local_shutdown_command is None
                        or payload.observed_at
                        < local_shutdown_command.shutdown_deadline_at
                        or payload.observed_monotonic_ns
                        < attempt.shutdown_deadline_monotonic_ns
                    )
                )
                or (
                    payload.result_kind is TcpHalfCloseResultKindV49E.CLOCK_DISAGREEMENT
                    and (
                        local_shutdown_command is None
                        or (
                            payload.observed_at
                            >= local_shutdown_command.shutdown_deadline_at
                        )
                        == (
                            payload.observed_monotonic_ns
                            >= attempt.shutdown_deadline_monotonic_ns
                        )
                    )
                )
            ):
                raise CanonicalizationError(
                    "TCP half-close result differs from its exact one-shot attempt"
                )
            tcp_half_close_result_event_id = event_id
            if payload.result_kind is TcpHalfCloseResultKindV49E.KERNEL_ACCEPTED:
                pending_tcp_half_close_marker_result_event_id = event_id
            else:
                pending_tcp_half_close_failure_marker = (
                    payload.result_kind,
                    payload.tcp_half_close_attempt_event_id,
                    event_id,
                )
        else:
            assert event.event_kind is TransportActorEventKindV49C.TERMINAL_TRANSITION
            assert type(payload) is TerminalTransitionPayloadV49C
            terminal_deadline_wire = next(
                (
                    candidate
                    for candidate in wire_events.values()
                    if candidate.logical_opcode is WebSocketOpcodeV49C.CLOSE
                    and candidate.outbound_operation_id
                    == terminal_state.ws_output_obligation_id
                ),
                None,
            )
            terminal_deadline_at = (
                local_shutdown_command.shutdown_deadline_at
                if local_shutdown_command is not None
                else (
                    None
                    if terminal_deadline_wire is None
                    else terminal_deadline_wire.send_not_after
                )
            )
            terminal_deadline_monotonic_ns = (
                local_shutdown_command.shutdown_deadline_monotonic_ns
                if local_shutdown_command is not None
                else (
                    None
                    if terminal_deadline_wire is None
                    else terminal_deadline_wire.send_not_after_monotonic_ns
                )
            )
            if (
                payload.kind is TerminalTransitionKindV49C.FATAL
                and payload.cause_code == V49E_LOCAL_SHUTDOWN_CLOCK_DISAGREEMENT_CAUSE
            ):
                disagreement_at = event.recorded_at
                disagreement_monotonic_ns = event.recorded_monotonic_ns
                if (
                    pending_tls_operation_failure_marker is not None
                    and pending_tls_operation_failure_marker[0].deadline_classification
                    is LocalShutdownDeadlineClassificationV49E.CLOCK_DISAGREEMENT
                ):
                    failure_event = events_by_id.get(
                        pending_tls_operation_failure_marker[1]
                    )
                    if (
                        failure_event is None
                        or type(failure_event.payload)
                        is not TlsProtocolOperationFailedPayloadV49E
                    ):
                        raise CanonicalizationError(
                            "clock disagreement lacks its TLS failure evidence"
                        )
                    disagreement_at = failure_event.payload.observed_at
                    disagreement_monotonic_ns = (
                        failure_event.payload.observed_monotonic_ns
                    )
                elif pending_kernel_send_failure_timeout is not None:
                    failure_event = events_by_id.get(
                        pending_kernel_send_failure_timeout[0]
                    )
                    if (
                        failure_event is None
                        or type(failure_event.payload)
                        is not KernelSendFailurePayloadV49E
                        or failure_event.payload.failure_kind
                        is not KernelSendFailureKindV49E.CLOCK_DISAGREEMENT
                    ):
                        raise CanonicalizationError(
                            "clock disagreement lacks its kernel-send failure evidence"
                        )
                    disagreement_at = failure_event.payload.observed_at
                    disagreement_monotonic_ns = (
                        failure_event.payload.observed_monotonic_ns
                    )
                elif pending_tls_control_failure_timeout_event_id is not None:
                    failure_event = events_by_id.get(
                        pending_tls_control_failure_timeout_event_id
                    )
                    if (
                        failure_event is None
                        or type(failure_event.payload)
                        is not TlsControlKernelSendFailurePayloadV49E
                        or failure_event.payload.failure_kind
                        is not KernelSendFailureKindV49E.CLOCK_DISAGREEMENT
                    ):
                        raise CanonicalizationError(
                            "clock disagreement lacks its TLS-send failure evidence"
                        )
                    disagreement_at = failure_event.payload.observed_at
                    disagreement_monotonic_ns = (
                        failure_event.payload.observed_monotonic_ns
                    )
                elif pending_terminal_ingress_failure is not None:
                    failure_event = events_by_id.get(
                        pending_terminal_ingress_failure[1]
                    )
                    if (
                        failure_event is None
                        or type(failure_event.payload)
                        is not TerminalIngressFailurePayloadV49E
                        or failure_event.payload.failure_kind
                        is not TerminalIngressFailureKindV49E.CLOCK_DISAGREEMENT
                    ):
                        raise CanonicalizationError(
                            "clock disagreement lacks terminal-ingress evidence"
                        )
                    disagreement_at = failure_event.payload.observed_at
                    disagreement_monotonic_ns = (
                        failure_event.payload.observed_monotonic_ns
                    )
                elif pending_local_shutdown_deadline_evidence is not None:
                    failure_event = events_by_id.get(
                        pending_local_shutdown_deadline_evidence[1]
                    )
                    if (
                        failure_event is None
                        or type(failure_event.payload)
                        is not LocalShutdownDeadlineEvidencePayloadV49E
                        or failure_event.payload.classification
                        is not LocalShutdownDeadlineClassificationV49E.CLOCK_DISAGREEMENT
                    ):
                        raise CanonicalizationError(
                            "clock disagreement lacks local deadline evidence"
                        )
                    disagreement_at = failure_event.payload.observed_at
                    disagreement_monotonic_ns = (
                        failure_event.payload.observed_monotonic_ns
                    )
                elif (
                    pending_tcp_half_close_failure_marker is not None
                    and pending_tcp_half_close_failure_marker[0]
                    is TcpHalfCloseResultKindV49E.CLOCK_DISAGREEMENT
                ):
                    failure_event = events_by_id.get(
                        pending_tcp_half_close_failure_marker[2]
                    )
                    if (
                        failure_event is None
                        or type(failure_event.payload)
                        is not TcpHalfCloseResultPayloadV49E
                    ):
                        raise CanonicalizationError(
                            "clock disagreement lacks its SHUT_WR result evidence"
                        )
                    disagreement_at = failure_event.payload.observed_at
                    disagreement_monotonic_ns = (
                        failure_event.payload.observed_monotonic_ns
                    )
                if (
                    terminal_deadline_at is None
                    or terminal_deadline_monotonic_ns is None
                    or (disagreement_at >= terminal_deadline_at)
                    == (disagreement_monotonic_ns >= terminal_deadline_monotonic_ns)
                ):
                    raise CanonicalizationError(
                        "shutdown clock-disagreement FATAL requires an exact XOR "
                        "deadline observation"
                    )
            if (
                payload.kind is TerminalTransitionKindV49C.TIMEOUT
                and payload.cause_code == V49E_WEBSOCKET_CLOSE_DEADLINE_EXPIRED_CAUSE
            ):
                if (
                    terminal_deadline_wire is None
                    or not terminal_state.ws_close_sent
                    or terminal_state.ws_output_obligation_id
                    != terminal_deadline_wire.outbound_operation_id
                    or event.recorded_monotonic_ns
                    < terminal_deadline_wire.send_not_after_monotonic_ns
                    or event.recorded_at < terminal_deadline_wire.send_not_after
                ):
                    raise CanonicalizationError(
                        "WebSocket Close deadline expiry requires its exact "
                        "unresolved Close wire and both due clocks"
                    )
            if (
                payload.kind is TerminalTransitionKindV49C.TIMEOUT
                and payload.cause_code
                in {
                    V49E_LOCAL_SHUTDOWN_COMMAND_DEADLINE_EXPIRED_CAUSE,
                    V49E_TCP_HALF_CLOSE_DEADLINE_EXPIRED_BEFORE_SYSCALL_CAUSE,
                    V49E_TLS_SHUTDOWN_DEADLINE_EXPIRED_CAUSE,
                    V49E_TLS_SHUTDOWN_DEADLINE_EXPIRED_AFTER_PROGRESS_CAUSE,
                    V49E_TERMINAL_CLOSE_INGRESS_DEADLINE_EXPIRED_AFTER_PROGRESS_CAUSE,
                }
                and (
                    local_shutdown_command_event_id is None
                    or local_shutdown_command is None
                    or (
                        events_by_id[
                            pending_terminal_ingress_failure[1]
                        ].payload.observed_at
                        if pending_terminal_ingress_failure is not None
                        and payload.cause_code
                        == V49E_TERMINAL_CLOSE_INGRESS_DEADLINE_EXPIRED_AFTER_PROGRESS_CAUSE
                        else event.recorded_at
                    )
                    < local_shutdown_command.shutdown_deadline_at
                    or (
                        events_by_id[
                            pending_terminal_ingress_failure[1]
                        ].payload.observed_monotonic_ns
                        if pending_terminal_ingress_failure is not None
                        and payload.cause_code
                        == V49E_TERMINAL_CLOSE_INGRESS_DEADLINE_EXPIRED_AFTER_PROGRESS_CAUSE
                        else event.recorded_monotonic_ns
                    )
                    < local_shutdown_command.shutdown_deadline_monotonic_ns
                )
            ):
                raise CanonicalizationError(
                    "shutdown TIMEOUT requires its exact due durable command"
                )
            if payload.kind is TerminalTransitionKindV49C.SEND_ATTEMPT_STARTED:
                if tls_control_attempt_awaiting_started_marker is not None:
                    attempt_id = tls_control_attempt_awaiting_started_marker
                    attempt = tls_control_attempt_events[attempt_id]
                    control_id = attempt.tls_control_ciphertext_prepared_event_id
                    control = tls_control_events[control_id]
                    expected_layer = (
                        OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY
                        if control.control_kind
                        is TlsControlOutputKindV49E.LOCAL_CLOSE_NOTIFY
                        else OutboundObligationLayerV49C.TLS_OPAQUE_CONTROL
                    )
                    if (
                        payload.send_attempt_id != attempt_id
                        or payload.obligation_layer is not expected_layer
                        or payload.obligation_id != control_id
                    ):
                        raise CanonicalizationError(
                            "TLS-control SEND_ATTEMPT_STARTED differs from exact attempt"
                        )
                elif (
                    len(unmatched_attempts) != 1
                    or payload.send_attempt_id not in unmatched_attempts
                ):
                    raise CanonicalizationError(
                        "terminal send start doesn't identify the unresolved kernel attempt"
                    )
            elif payload.kind is TerminalTransitionKindV49C.SEND_ATTEMPT_RESOLVED:
                if tls_control_failure_awaiting_resolved_marker is not None:
                    attempt_id, failure_id = (
                        tls_control_failure_awaiting_resolved_marker
                    )
                    failure = tls_control_failure_events[failure_id]
                    control_id = failure.tls_control_ciphertext_prepared_event_id
                    control = tls_control_events[control_id]
                    expected_layer = (
                        OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY
                        if control.control_kind
                        is TlsControlOutputKindV49E.LOCAL_CLOSE_NOTIFY
                        else OutboundObligationLayerV49C.TLS_OPAQUE_CONTROL
                    )
                    if (
                        payload.send_attempt_id != attempt_id
                        or payload.obligation_layer is not expected_layer
                        or payload.obligation_id != control_id
                    ):
                        raise CanonicalizationError(
                            "TLS-control SEND_ATTEMPT_RESOLVED differs from failure"
                        )
                elif tls_control_result_awaiting_resolved_marker is not None:
                    attempt_id, result_id = tls_control_result_awaiting_resolved_marker
                    result = tls_control_result_events[result_id]
                    control_id = result.tls_control_ciphertext_prepared_event_id
                    control = tls_control_events[control_id]
                    expected_layer = (
                        OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY
                        if control.control_kind
                        is TlsControlOutputKindV49E.LOCAL_CLOSE_NOTIFY
                        else OutboundObligationLayerV49C.TLS_OPAQUE_CONTROL
                    )
                    if (
                        payload.send_attempt_id != attempt_id
                        or payload.obligation_layer is not expected_layer
                        or payload.obligation_id != control_id
                    ):
                        raise CanonicalizationError(
                            "TLS-control SEND_ATTEMPT_RESOLVED differs from exact result"
                        )
                elif payload.send_attempt_id != awaiting_terminal_resolution:
                    raise CanonicalizationError(
                        "terminal send resolution doesn't identify the kernel result"
                    )
            elif payload.kind is TerminalTransitionKindV49C.UNKNOWN_SEND:
                if payload.send_attempt_id in unmatched_tls_control_attempts:
                    assert payload.send_attempt_id is not None
                    attempt = tls_control_attempt_events[payload.send_attempt_id]
                    control_id = attempt.tls_control_ciphertext_prepared_event_id
                    control = tls_control_events[control_id]
                    expected_layer = (
                        OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY
                        if control.control_kind
                        is TlsControlOutputKindV49E.LOCAL_CLOSE_NOTIFY
                        else OutboundObligationLayerV49C.TLS_OPAQUE_CONTROL
                    )
                    if (
                        payload.obligation_layer is not expected_layer
                        or payload.obligation_id != control_id
                        or payload.cause_code
                        != V49E_TLS_CONTROL_SEND_OUTCOME_UNKNOWN_CAUSE
                    ):
                        raise CanonicalizationError(
                            "TLS-control UNKNOWN_SEND differs from exact unresolved attempt"
                        )
                elif (
                    len(unmatched_attempts) != 1
                    or payload.send_attempt_id not in unmatched_attempts
                ):
                    raise CanonicalizationError(
                        "UNKNOWN_SEND doesn't identify the unresolved kernel attempt"
                    )
            elif payload.kind is TerminalTransitionKindV49C.WS_CLOSE_SENT:
                if payload.obligation_id not in unmarked_ws_close_wires:
                    raise CanonicalizationError(
                        "WS_CLOSE_SENT lacks one exact unmarked Close wire"
                    )
                unmarked_ws_close_wires.remove(payload.obligation_id)
                local_terminal_wire = (
                    None
                    if local_terminal_wire_event_id is None
                    else wire_events.get(local_terminal_wire_event_id)
                )
                if (
                    local_terminal_wire is not None
                    and payload.obligation_id
                    == local_terminal_wire.outbound_operation_id
                ):
                    current_cursor = (
                        WebSocketParserCursorV49C(
                            cursor_sequence=0,
                            next_stream_octet=0,
                            websocket_state=WebSocketParserStateV49C.OPEN,
                        )
                        if parser_cursor is None
                        else parser_cursor
                    )
                    if (
                        current_cursor.websocket_state
                        is not WebSocketParserStateV49C.OPEN
                        or current_cursor.fragmented_message_opcode is not None
                        or current_cursor.fragmented_message_octets != 0
                        or current_cursor.fragmented_message_sha256 is not None
                        or fragmented_message_opcode is not None
                        or fragmented_message_parser_event_ids
                        or fragmented_message_octets != 0
                    ):
                        raise CanonicalizationError(
                            "local terminal command cannot close a fragmented or "
                            "non-open parser cursor"
                        )
                    parser_cursor = WebSocketParserCursorV49C(
                        cursor_sequence=current_cursor.cursor_sequence,
                        next_stream_octet=current_cursor.next_stream_octet,
                        websocket_state=WebSocketParserStateV49C.CLOSING,
                    )
            elif payload.kind is TerminalTransitionKindV49C.WS_CLOSE_RECEIVED:
                if not unmarked_ws_close_parser_events:
                    raise CanonicalizationError(
                        "WS_CLOSE_RECEIVED lacks one exact unmarked parser Close"
                    )
                unmarked_ws_close_parser_events.pop(0)
            elif payload.kind is (
                TerminalTransitionKindV49C.OUTBOUND_OBLIGATION_FULLY_KERNEL_ACCEPTED
            ):
                if (
                    payload.obligation_layer
                    is OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY
                ):
                    if (
                        pending_local_tls_full_acceptance_control_id is None
                        or payload.obligation_id
                        != pending_local_tls_full_acceptance_control_id
                    ):
                        raise CanonicalizationError(
                            "TLS full acceptance lacks exact sent notify"
                        )
                else:
                    key = (payload.obligation_layer, payload.obligation_id)
                    if key not in fully_dispatched_close_obligations:
                        raise CanonicalizationError(
                            "full close acceptance lacks exact completed dispatch"
                        )
                    fully_dispatched_close_obligations.remove(key)
            elif payload.kind is TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_PREPARED:
                control_id = pending_tls_control_prepared_marker_event_id
                if (
                    control_id is None
                    or payload.obligation_layer
                    is not OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY
                    or payload.obligation_id != control_id
                    or local_tls_prepared_marker_event_id is not None
                ):
                    raise CanonicalizationError(
                        "TLS prepared marker lacks exact local control artifact"
                    )
            elif payload.kind is TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_SENT:
                control_id = completed_local_tls_control_event_id
                if control_id is None:
                    raise CanonicalizationError(
                        "TLS close_notify marker lacks exact control-ciphertext "
                        "full kernel acceptance"
                    )
                control = tls_control_events[control_id]
                result_ids = tls_control_result_ids[control_id]
                if (
                    pending_local_tls_sent_control_id != control_id
                    or not result_ids
                    or tls_control_offsets[control_id] != control.ciphertext_octets
                    or payload.obligation_layer
                    is not OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY
                    or payload.obligation_id != control_id
                    or local_tls_marker_event_id is not None
                ):
                    raise CanonicalizationError(
                        "TLS close_notify marker precedes gap-free full kernel acceptance"
                    )
            elif payload.kind is TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_RECEIVED:
                if (
                    pending_shutdown_observation_marker is None
                    or pending_shutdown_observation_marker[0]
                    is not TlsShutdownObservationKindV49E.PEER_CLOSE_NOTIFY
                    or peer_tls_marker_event_id is not None
                ):
                    raise CanonicalizationError(
                        "positive TLS/TCP terminal evidence isn't actor-integrated: "
                        "peer close_notify marker lacks its exact driver observation"
                    )
            elif payload.kind is TerminalTransitionKindV49C.TCP_FIN_SENT:
                if (
                    pending_tcp_half_close_marker_result_event_id is None
                    or tcp_half_close_result_event_id
                    != pending_tcp_half_close_marker_result_event_id
                    or tcp_half_close_marker_event_id is not None
                ):
                    raise CanonicalizationError(
                        "TCP write-half-close marker lacks successful SHUT_WR evidence"
                    )
            elif payload.kind is TerminalTransitionKindV49C.TCP_EOF_RECEIVED:
                if (
                    pending_shutdown_observation_marker is None
                    or pending_shutdown_observation_marker[0]
                    is not TlsShutdownObservationKindV49E.TCP_EOF
                    or tcp_eof_marker_event_id is not None
                ):
                    raise CanonicalizationError(
                        "TCP EOF marker lacks its exact retained-owner observation"
                    )
            elif payload.kind is TerminalTransitionKindV49C.CLEAN_ALL_LAYERS:
                if (
                    local_tls_marker_event_id is None
                    or local_tls_fully_accepted_marker_event_id is None
                    or peer_tls_marker_event_id is None
                    or tcp_half_close_marker_event_id is None
                    or tcp_eof_marker_event_id is None
                    or pending_tls_protocol_operation_event_id is not None
                    or active_tls_control_event_id is not None
                    or unmatched_tls_control_attempts
                    or pending_tls_operation_failure_marker is not None
                    or pending_tls_control_prepared_marker_event_id is not None
                    or tls_control_attempt_awaiting_started_marker is not None
                    or tls_control_result_awaiting_resolved_marker is not None
                    or pending_local_tls_sent_control_id is not None
                    or pending_local_tls_full_acceptance_control_id is not None
                    or pending_shutdown_observation_marker is not None
                    or pending_tcp_half_close_marker_result_event_id is not None
                    or pending_tcp_half_close_failure_marker is not None
                ):
                    raise CanonicalizationError(
                        "clean terminal marker lacks complete actor-bound layer evidence"
                    )
            try:
                terminal_state = advance_terminal_state_v49c(terminal_state, payload)
            except PhysicalTransportTerminalV49CError as exc:
                raise CanonicalizationError(
                    "terminal transition violates layered actor state"
                ) from exc
            if payload.kind is TerminalTransitionKindV49C.SEND_ATTEMPT_STARTED:
                if tls_control_attempt_awaiting_started_marker is not None:
                    tls_control_attempt_awaiting_started_marker = None
            elif payload.kind is TerminalTransitionKindV49C.SEND_ATTEMPT_RESOLVED:
                if tls_control_failure_awaiting_resolved_marker is not None:
                    _, failure_id = tls_control_failure_awaiting_resolved_marker
                    tls_control_failure_awaiting_resolved_marker = None
                    pending_tls_control_failure_timeout_event_id = failure_id
                elif tls_control_result_awaiting_resolved_marker is not None:
                    _, result_id = tls_control_result_awaiting_resolved_marker
                    result = tls_control_result_events[result_id]
                    control_id = result.tls_control_ciphertext_prepared_event_id
                    control = tls_control_events[control_id]
                    tls_control_result_awaiting_resolved_marker = None
                    if (
                        result.resulting_ciphertext_offset == control.ciphertext_octets
                        and control.control_kind
                        is TlsControlOutputKindV49E.LOCAL_CLOSE_NOTIFY
                    ):
                        pending_local_tls_sent_control_id = control_id
                else:
                    awaiting_terminal_resolution = None
                    if kernel_send_failure_awaiting_resolution is not None:
                        pending_kernel_send_failure_timeout = (
                            kernel_send_failure_awaiting_resolution
                        )
                        kernel_send_failure_awaiting_resolution = None
            elif payload.kind is TerminalTransitionKindV49C.WS_CLOSE_SENT:
                ws_close_sent_marker_event_id = event_id
            elif payload.kind is TerminalTransitionKindV49C.WS_CLOSE_RECEIVED:
                ws_close_received_marker_event_id = event_id
            elif (
                payload.kind
                is TerminalTransitionKindV49C.OUTBOUND_OBLIGATION_FULLY_KERNEL_ACCEPTED
                and payload.obligation_layer
                is OutboundObligationLayerV49C.WEBSOCKET_CLOSE
            ):
                ws_close_fully_accepted_marker_event_id = event_id
            elif (
                payload.kind
                is TerminalTransitionKindV49C.OUTBOUND_OBLIGATION_FULLY_KERNEL_ACCEPTED
                and payload.obligation_layer
                is OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY
            ):
                pending_local_tls_full_acceptance_control_id = None
                local_tls_fully_accepted_marker_event_id = event_id
            elif payload.kind is TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_PREPARED:
                local_tls_prepared_marker_event_id = event_id
                pending_tls_control_prepared_marker_event_id = None
            elif payload.kind is TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_SENT:
                assert pending_local_tls_sent_control_id is not None
                pending_local_tls_full_acceptance_control_id = (
                    pending_local_tls_sent_control_id
                )
                pending_local_tls_sent_control_id = None
                local_tls_marker_event_id = event_id
            elif payload.kind is TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_RECEIVED:
                pending_shutdown_observation_marker = None
                peer_tls_marker_event_id = event_id
                last_tls_shutdown_marker_event_id = event_id
            elif payload.kind is TerminalTransitionKindV49C.TCP_FIN_SENT:
                pending_tcp_half_close_marker_result_event_id = None
                tcp_half_close_marker_event_id = event_id
            elif payload.kind is TerminalTransitionKindV49C.TCP_EOF_RECEIVED:
                pending_shutdown_observation_marker = None
                tcp_eof_marker_event_id = event_id
                last_tls_shutdown_marker_event_id = event_id
            elif pending_tls_operation_failure_marker is not None and payload.kind in {
                TerminalTransitionKindV49C.FATAL,
                TerminalTransitionKindV49C.TIMEOUT,
            }:
                pending_tls_operation_failure_marker = None
            if pending_tcp_half_close_failure_marker is not None and payload.kind in {
                TerminalTransitionKindV49C.FATAL,
                TerminalTransitionKindV49C.TIMEOUT,
            }:
                pending_tcp_half_close_failure_marker = None
            if pending_kernel_send_failure_timeout is not None and payload.kind in {
                TerminalTransitionKindV49C.TIMEOUT,
                TerminalTransitionKindV49C.FATAL,
            }:
                pending_kernel_send_failure_timeout = None
            if (
                pending_tls_control_failure_timeout_event_id is not None
                and payload.kind
                in {
                    TerminalTransitionKindV49C.TIMEOUT,
                    TerminalTransitionKindV49C.FATAL,
                }
            ):
                pending_tls_control_failure_timeout_event_id = None
            if pending_terminal_ingress_failure is not None and payload.kind in {
                TerminalTransitionKindV49C.TIMEOUT,
                TerminalTransitionKindV49C.FATAL,
            }:
                pending_terminal_ingress_failure = None
            if (
                pending_local_shutdown_deadline_evidence is not None
                and payload.kind
                in {
                    TerminalTransitionKindV49C.TIMEOUT,
                    TerminalTransitionKindV49C.FATAL,
                }
            ):
                pending_local_shutdown_deadline_evidence = None

        events_by_id[event_id] = event

    return terminal_state


def reduce_transport_actor_chain_v49e(
    events: Sequence[TransportActorEventV49C],
) -> TerminalStateV49C:
    """Replay V4.9E evidence through the canonical terminal reducer."""

    return validate_transport_actor_chain_v49c(events)


@dataclass(frozen=True, slots=True, kw_only=True)
class CommittedRawChunkV49C:
    """One exact in-memory chunk already covered by a raw projection receipt."""

    raw_ingress_commit_id: str
    projection_receipt_sequence: int
    projection_receipt_hash: str
    raw_local_start_octet: int
    stream_start_octet: int
    data: bytes

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "raw_ingress_commit_id",
            canonical_hash(self.raw_ingress_commit_id, field="raw_ingress_commit_id"),
        )
        object.__setattr__(
            self,
            "projection_receipt_sequence",
            canonical_safe_int(
                self.projection_receipt_sequence,
                field="projection_receipt_sequence",
                minimum=1,
            ),
        )
        object.__setattr__(
            self,
            "projection_receipt_hash",
            canonical_hash(
                self.projection_receipt_hash, field="projection_receipt_hash"
            ),
        )
        object.__setattr__(
            self,
            "raw_local_start_octet",
            canonical_safe_int(
                self.raw_local_start_octet,
                field="raw_local_start_octet",
                minimum=0,
            ),
        )
        object.__setattr__(
            self,
            "stream_start_octet",
            canonical_safe_int(
                self.stream_start_octet, field="stream_start_octet", minimum=0
            ),
        )
        if (
            type(self.data) is not bytes
            or not self.data
            or len(self.data) > V49C_MAX_RAW_COMMIT_OCTETS
        ):
            raise CanonicalizationError("committed raw chunk must contain exact bytes")
        canonical_safe_int(
            self.stream_start_octet + len(self.data),
            field="stream_end_octet",
            minimum=1,
        )
        canonical_safe_int(
            self.raw_local_start_octet + len(self.data),
            field="raw_local_end_octet",
            minimum=1,
            maximum=V49C_MAX_RAW_COMMIT_OCTETS,
        )

    @property
    def stream_end_octet(self) -> int:
        return self.stream_start_octet + len(self.data)

    @property
    def raw_local_end_octet(self) -> int:
        return self.raw_local_start_octet + len(self.data)


@dataclass(frozen=True, slots=True, kw_only=True)
class RetainedIngressTailV49C:
    chunks: tuple[CommittedRawChunkV49C, ...] = ()

    def __post_init__(self) -> None:
        chunks = tuple(self.chunks)
        if any(type(chunk) is not CommittedRawChunkV49C for chunk in chunks):
            raise CanonicalizationError("retained tail contains an unsupported chunk")
        if any(
            right.stream_start_octet != left.stream_end_octet
            for left, right in zip(chunks, chunks[1:])
        ):
            raise CanonicalizationError("retained tail chunks aren't contiguous")
        object.__setattr__(self, "chunks", chunks)

    @property
    def total_octets(self) -> int:
        return sum(len(chunk.data) for chunk in self.chunks)

    @property
    def data(self) -> bytes:
        return b"".join(chunk.data for chunk in self.chunks)


@dataclass(frozen=True, slots=True, kw_only=True)
class DelineatedServerFrameV49C:
    metadata: WebSocketFrameMetadataV49C
    source_slices: tuple[RawSourceSliceV49C, ...]
    frame_bytes: bytes
    payload: bytes

    def __post_init__(self) -> None:
        if type(self.metadata) is not WebSocketFrameMetadataV49C:
            raise CanonicalizationError("delineated frame requires exact metadata")
        slices = _validate_contiguous_slices(self.source_slices)
        if type(self.frame_bytes) is not bytes or type(self.payload) is not bytes:
            raise CanonicalizationError("delineated frame bytes must be exact bytes")
        if (
            slices[0].stream_start_octet != self.metadata.stream_start_octet
            or slices[-1].stream_end_octet != self.metadata.stream_end_octet
            or len(self.frame_bytes)
            != self.metadata.stream_end_octet - self.metadata.stream_start_octet
            or len(self.payload) != self.metadata.payload_octets
            or hashlib.sha256(self.frame_bytes).hexdigest()
            != self.metadata.frame_sha256
            or hashlib.sha256(self.payload).hexdigest() != self.metadata.payload_sha256
        ):
            raise CanonicalizationError("delineated frame differs from metadata/slices")
        object.__setattr__(self, "source_slices", slices)


@dataclass(frozen=True, slots=True, kw_only=True)
class FrameDelineationErrorV49C:
    error_kind: ParserErrorKindV49C
    error_stream_offset: int
    source_slices: tuple[RawSourceSliceV49C, ...]
    examined_bytes: bytes

    def __post_init__(self) -> None:
        kind = _enum(self.error_kind, ParserErrorKindV49C, field="error_kind")
        offset = canonical_safe_int(
            self.error_stream_offset,
            field="error_stream_offset",
            minimum=0,
        )
        slices = _validate_contiguous_slices(self.source_slices)
        if type(self.examined_bytes) is not bytes or not self.examined_bytes:
            raise CanonicalizationError("delineation error requires examined bytes")
        if (
            not slices[0].stream_start_octet <= offset < slices[-1].stream_end_octet
            or len(self.examined_bytes)
            != slices[-1].stream_end_octet - slices[0].stream_start_octet
        ):
            raise CanonicalizationError("delineation error differs from source span")
        object.__setattr__(self, "error_kind", kind)
        object.__setattr__(self, "error_stream_offset", offset)
        object.__setattr__(self, "source_slices", slices)


DelineatedUnitV49C: TypeAlias = DelineatedServerFrameV49C | FrameDelineationErrorV49C


@dataclass(frozen=True, slots=True, kw_only=True)
class FrameDelineationResultV49C:
    unit: DelineatedUnitV49C | None
    retained_tail: RetainedIngressTailV49C

    def __post_init__(self) -> None:
        if self.unit is not None and type(self.unit) not in {
            DelineatedServerFrameV49C,
            FrameDelineationErrorV49C,
        }:
            raise CanonicalizationError("delineated unit has an unsupported type")
        if type(self.retained_tail) is not RetainedIngressTailV49C:
            raise CanonicalizationError("retained_tail has an unsupported type")


def _validate_fragment_chain(
    prior_tail: RetainedIngressTailV49C,
    new_chunks: Sequence[CommittedRawChunkV49C],
) -> tuple[CommittedRawChunkV49C, ...]:
    if type(prior_tail) is not RetainedIngressTailV49C:
        raise CanonicalizationError("prior_tail must be exact RetainedIngressTailV49C")
    added = tuple(new_chunks)
    if any(type(chunk) is not CommittedRawChunkV49C for chunk in added):
        raise CanonicalizationError("committed_raw_chunks contains an invalid chunk")
    combined = prior_tail.chunks + added
    if not combined:
        return ()
    if any(
        right.stream_start_octet != left.stream_end_octet
        for left, right in zip(combined, combined[1:])
    ):
        raise CanonicalizationError("raw frame fragments aren't stream-contiguous")
    closed_raw_ids: set[str] = set()
    for left, right in zip(combined, combined[1:]):
        if left.raw_ingress_commit_id == right.raw_ingress_commit_id:
            if (
                left.projection_receipt_sequence != right.projection_receipt_sequence
                or left.projection_receipt_hash != right.projection_receipt_hash
                or left.raw_local_end_octet != right.raw_local_start_octet
            ):
                raise CanonicalizationError(
                    "one raw-ingress commit has inconsistent receipt or local offsets"
                )
            continue
        closed_raw_ids.add(left.raw_ingress_commit_id)
        if (
            right.raw_ingress_commit_id in closed_raw_ids
            or right.projection_receipt_sequence <= left.projection_receipt_sequence
        ):
            raise CanonicalizationError(
                "cross-ingress fragments don't follow projection receipt order"
            )
    return combined


def _take_prefix(
    chunks: tuple[CommittedRawChunkV49C, ...], octets: int
) -> tuple[tuple[CommittedRawChunkV49C, ...], tuple[CommittedRawChunkV49C, ...]]:
    remaining = octets
    prefix: list[CommittedRawChunkV49C] = []
    suffix: list[CommittedRawChunkV49C] = []
    for chunk in chunks:
        if remaining <= 0:
            suffix.append(chunk)
            continue
        if len(chunk.data) <= remaining:
            prefix.append(chunk)
            remaining -= len(chunk.data)
            continue
        prefix.append(
            CommittedRawChunkV49C(
                raw_ingress_commit_id=chunk.raw_ingress_commit_id,
                projection_receipt_sequence=chunk.projection_receipt_sequence,
                projection_receipt_hash=chunk.projection_receipt_hash,
                raw_local_start_octet=chunk.raw_local_start_octet,
                stream_start_octet=chunk.stream_start_octet,
                data=chunk.data[:remaining],
            )
        )
        suffix.append(
            CommittedRawChunkV49C(
                raw_ingress_commit_id=chunk.raw_ingress_commit_id,
                projection_receipt_sequence=chunk.projection_receipt_sequence,
                projection_receipt_hash=chunk.projection_receipt_hash,
                raw_local_start_octet=chunk.raw_local_start_octet + remaining,
                stream_start_octet=chunk.stream_start_octet + remaining,
                data=chunk.data[remaining:],
            )
        )
        remaining = 0
    if remaining:
        raise CanonicalizationError("requested prefix exceeds raw fragments")
    return tuple(prefix), tuple(suffix)


def _slices_for_chunks(
    chunks: Sequence[CommittedRawChunkV49C],
) -> tuple[RawSourceSliceV49C, ...]:
    slices: list[RawSourceSliceV49C] = []
    for chunk in chunks:
        if slices:
            prior = slices[-1]
            if (
                prior.raw_ingress_commit_id == chunk.raw_ingress_commit_id
                and prior.projection_receipt_sequence
                == chunk.projection_receipt_sequence
                and prior.projection_receipt_hash == chunk.projection_receipt_hash
                and prior.stream_end_octet == chunk.stream_start_octet
                and prior.raw_local_end_octet == chunk.raw_local_start_octet
            ):
                slices[-1] = RawSourceSliceV49C(
                    raw_ingress_commit_id=prior.raw_ingress_commit_id,
                    projection_receipt_sequence=prior.projection_receipt_sequence,
                    projection_receipt_hash=prior.projection_receipt_hash,
                    stream_start_octet=prior.stream_start_octet,
                    stream_end_octet=chunk.stream_end_octet,
                    raw_local_start_octet=prior.raw_local_start_octet,
                    raw_local_end_octet=chunk.raw_local_end_octet,
                )
                continue
        slices.append(
            RawSourceSliceV49C(
                raw_ingress_commit_id=chunk.raw_ingress_commit_id,
                projection_receipt_sequence=chunk.projection_receipt_sequence,
                projection_receipt_hash=chunk.projection_receipt_hash,
                stream_start_octet=chunk.stream_start_octet,
                stream_end_octet=chunk.stream_end_octet,
                raw_local_start_octet=chunk.raw_local_start_octet,
                raw_local_end_octet=chunk.raw_local_end_octet,
            )
        )
    if len(slices) > V49C_MAX_FRAME_SOURCE_SLICES:
        raise CanonicalizationError("frame spans too many raw-ingress commits")
    return tuple(slices)


def delineate_next_server_frame_v49c(
    *,
    prior_tail: RetainedIngressTailV49C,
    committed_raw_chunks: Sequence[CommittedRawChunkV49C],
    maximum_payload_octets: int = V49C_MAX_FRAME_PAYLOAD_OCTETS,
) -> FrameDelineationResultV49C:
    """Return at most one frame/error and preserve every unconsumed raw byte.

    The input is an already-durable, contiguous plaintext stream suffix.  The
    function doesn't mutate its inputs and never calls a protocol object.
    Incomplete headers or payloads return ``unit=None`` with the exact combined
    tail.  Deterministically invalid headers return an error unit covering the
    minimum bytes required to establish the error plus the untouched suffix.
    """

    maximum = canonical_safe_int(
        maximum_payload_octets,
        field="maximum_payload_octets",
        minimum=1,
        maximum=V49C_MAX_FRAME_PAYLOAD_OCTETS,
    )
    chunks = _validate_fragment_chain(prior_tail, committed_raw_chunks)
    if not chunks:
        return FrameDelineationResultV49C(
            unit=None, retained_tail=RetainedIngressTailV49C()
        )
    data = b"".join(chunk.data for chunk in chunks)
    if len(data) < 2:
        return FrameDelineationResultV49C(
            unit=None, retained_tail=RetainedIngressTailV49C(chunks=chunks)
        )

    first, second = data[0], data[1]

    def error(
        kind: ParserErrorKindV49C, examined_octets: int
    ) -> FrameDelineationResultV49C:
        prefix, suffix = _take_prefix(chunks, examined_octets)
        return FrameDelineationResultV49C(
            unit=FrameDelineationErrorV49C(
                error_kind=kind,
                error_stream_offset=chunks[0].stream_start_octet,
                source_slices=_slices_for_chunks(prefix),
                examined_bytes=b"".join(chunk.data for chunk in prefix),
            ),
            retained_tail=RetainedIngressTailV49C(chunks=suffix),
        )

    if first & 0x70:
        return error(ParserErrorKindV49C.RESERVED_BITS, 2)
    opcode_number = first & 0x0F
    opcode = _OPCODE_NUMBER_TO_ENUM.get(opcode_number)
    if opcode is None:
        return error(ParserErrorKindV49C.INVALID_OPCODE, 2)
    if second & 0x80:
        return error(ParserErrorKindV49C.INCORRECT_MASKING, 2)
    fin = bool(first & 0x80)
    is_control = opcode_number >= 0x8
    if is_control and not fin:
        return error(ParserErrorKindV49C.FRAGMENTED_CONTROL, 2)

    length_marker = second & 0x7F
    header_octets = 2
    if is_control and length_marker >= 126:
        return error(ParserErrorKindV49C.CONTROL_TOO_LARGE, header_octets)
    if length_marker < 126:
        payload_octets = length_marker
    elif length_marker == 126:
        header_octets = 4
        if len(data) < header_octets:
            return FrameDelineationResultV49C(
                unit=None, retained_tail=RetainedIngressTailV49C(chunks=chunks)
            )
        payload_octets = int.from_bytes(data[2:4], "big")
        if payload_octets < 126:
            return error(ParserErrorKindV49C.NON_MINIMAL_LENGTH, header_octets)
    else:
        header_octets = 10
        if len(data) < header_octets:
            return FrameDelineationResultV49C(
                unit=None, retained_tail=RetainedIngressTailV49C(chunks=chunks)
            )
        payload_octets = int.from_bytes(data[2:10], "big")
        if payload_octets >= 2**63:
            return error(ParserErrorKindV49C.INVALID_64BIT_LENGTH, header_octets)
        if payload_octets < 65_536:
            return error(ParserErrorKindV49C.NON_MINIMAL_LENGTH, header_octets)

    if is_control and payload_octets > 125:
        return error(ParserErrorKindV49C.CONTROL_TOO_LARGE, header_octets)
    if payload_octets > maximum:
        return error(ParserErrorKindV49C.FRAME_TOO_LARGE, header_octets)
    frame_octets = header_octets + payload_octets
    if len(data) < frame_octets:
        return FrameDelineationResultV49C(
            unit=None, retained_tail=RetainedIngressTailV49C(chunks=chunks)
        )

    prefix, suffix = _take_prefix(chunks, frame_octets)
    frame_bytes = data[:frame_octets]
    payload = frame_bytes[header_octets:]
    stream_start = prefix[0].stream_start_octet
    metadata = WebSocketFrameMetadataV49C(
        stream_start_octet=stream_start,
        stream_end_octet=stream_start + frame_octets,
        header_octets=header_octets,
        payload_octets=payload_octets,
        opcode=opcode,
        fin=fin,
        masked=False,
        frame_sha256=hashlib.sha256(frame_bytes).hexdigest(),
        payload_sha256=hashlib.sha256(payload).hexdigest(),
    )
    return FrameDelineationResultV49C(
        unit=DelineatedServerFrameV49C(
            metadata=metadata,
            source_slices=_slices_for_chunks(prefix),
            frame_bytes=frame_bytes,
            payload=payload,
        ),
        retained_tail=RetainedIngressTailV49C(chunks=suffix),
    )


__all__ = [
    "AckDeadlineExpiredPayloadV49E",
    "ApplicationMessageCommittedPayloadV49E",
    "CommittedRawIngressV49C",
    "CommittedRawChunkV49C",
    "DelineatedServerFrameV49C",
    "FrameDelineationErrorV49C",
    "FrameDelineationResultV49C",
    "KernelSendAttemptPayloadV49C",
    "KernelSendFailureKindV49E",
    "KernelSendFailurePayloadV49E",
    "KernelSendResultPayloadV49C",
    "LocalShutdownDeadlineClassificationV49E",
    "LocalShutdownDeadlineEvidencePayloadV49E",
    "LocalShutdownCommandStartedPayloadV49E",
    "OutboundDispatchCompletedPayloadV49C",
    "OutboundDispatchDispositionV49C",
    "OutboundWireOriginV49C",
    "OutboundWirePreparedPayloadV49C",
    "PHYSICAL_TRANSPORT_ACTOR_V49C_SCHEMA_VERSION",
    "ParserErrorKindV49C",
    "ParserErrorMetadataV49C",
    "ParserFeedUnitKindV49C",
    "ParserTransitionPayloadV49C",
    "RawIngressCommittedPayloadV49C",
    "RawSourceSliceV49C",
    "RetainedIngressTailV49C",
    "SubscriptionAckBoundPayloadV49E",
    "TcpHalfCloseAttemptPayloadV49E",
    "TcpHalfCloseResultKindV49E",
    "TcpHalfCloseResultPayloadV49E",
    "TerminalIngressFailureKindV49E",
    "TerminalIngressFailurePayloadV49E",
    "TerminalTransitionPayloadV49C",
    "TlsControlCiphertextPreparedPayloadV49E",
    "TlsControlKernelSendAttemptPayloadV49E",
    "TlsControlKernelSendFailurePayloadV49E",
    "TlsControlKernelSendResultPayloadV49E",
    "TlsControlOutputKindV49E",
    "TlsCiphertextPreparedPayloadV49C",
    "TlsProtocolOperationFailedPayloadV49E",
    "TlsProtocolOperationFailureKindV49E",
    "TlsProtocolOperationPurposeV49E",
    "TlsProtocolOperationStartedPayloadV49E",
    "TlsShutdownObservationKindV49E",
    "TlsShutdownObservedPayloadV49E",
    "TransportActorEventKindV49C",
    "TransportActorEventV49C",
    "V49C_MAX_FRAME_PAYLOAD_OCTETS",
    "V49C_MAX_RAW_COMMIT_OCTETS",
    "V49E_MAX_APPLICATION_MESSAGE_FRAMES",
    "V49E_WEBSOCKET_CLOSE_DEADLINE_EXPIRED_CAUSE",
    "WebSocketFrameMetadataV49C",
    "WebSocketOpcodeV49C",
    "WebSocketParserCursorV49C",
    "WebSocketParserStateV49C",
    "WritePermitConsumedPayloadV49C",
    "classify_tls_protocol_operation_failure_v49e",
    "delineate_next_server_frame_v49c",
    "derive_actor_write_permit_id_v49c",
    "derive_local_shutdown_command_id_v49e",
    "derive_local_terminal_command_operation_id_v49e",
    "reduce_transport_actor_chain_v49e",
    "validate_transport_actor_chain_v49c",
]

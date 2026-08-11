"""Bounded V4.9A TLS 1.3 and WebSocket Sans-I/O engine.

This module is intentionally *not* a live-provider activation.  It implements
the exact local protocol engine that the later live owner will retain, while
the V4.8B Linux factory remains deny-gated.  The separation is deliberate:
driver-derived session commitment, ordered multi-output durability, exact
partial-kernel-send evidence, and the complete WebSocket/TLS close lifecycle
must be connected and falsified before this engine may grant authority.

The important boundary implemented here is raw-before-parse.  Decrypted
post-upgrade bytes become an opaque ``PendingRawIngressV49``.  The
``websockets`` parser cannot consume them until the caller presents the exact
durable ``RawIngressCommitV4`` containing the same chunk boundaries and bytes.
Automatically generated Pong/Close output is drained into owned memory and is
never written by the receive path.
"""

from __future__ import annotations

import asyncio
import base64
import codecs
import errno
import hashlib
import importlib.metadata
import inspect
import os
import secrets
import socket
import ssl
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any, Final, TypeAlias

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from websockets.client import ClientProtocol
from websockets.frames import CloseCode, Frame, Opcode
from websockets.http11 import Response
from websockets.protocol import State
from websockets.uri import parse_uri

from .canonical import (
    CanonicalizationError,
    canonical_hash,
    canonical_identifier,
    canonical_safe_int,
    sha256_digest,
)
from .operational_runtime_artifacts_v49b import (
    PinnedTlsWebSocketRuntimeArtifactsV49B,
)
from .physical_transport_control_v4 import (
    V4_CONTROL_MAXIMUM_INGRESS_BYTES,
    V4_CONTROL_MAXIMUM_INGRESS_CHUNKS,
    OutboundControlWritePermitConsumedV4,
    RawIngressCommitV4,
)
from .physical_transport_v4 import (
    BYBIT_V5_LINEAR_ENDPOINT_V4,
    BYBIT_V5_LINEAR_TLS_SERVER_NAME_V4,
    TransportSubscriptionPolicyV4,
)
from .tls_trust_store_v49 import (
    PinnedTlsTrustStoreV49,
    derive_tls_ca_der_set_root_v49,
)

V49_WEBSOCKETS_VERSION: Final = "16.0"
V49_HANDSHAKE_TIMEOUT_SECONDS: Final = 10
V49_MAXIMUM_HTTP_RESPONSE_HEAD_BYTES: Final = 32 * 1024
# A pending driver batch must be constructible as one RawIngressCommitV4.
# Larger already-decrypted streams remain in SSLObject and become later batches.
V49_MAXIMUM_POST_UPGRADE_PENDING_BYTES: Final = V4_CONTROL_MAXIMUM_INGRESS_BYTES
V49_MAXIMUM_TLS_OPERATION_CIPHERTEXT_BYTES: Final = 4 * 1024 * 1024
V49_MAXIMUM_WEBSOCKET_MESSAGE_BYTES: Final = 1 * 1024 * 1024
V49_TLS_CIPHERTEXT_READ_BYTES: Final = 64 * 1024
V49_TLS_PLAINTEXT_READ_BYTES: Final = 64 * 1024
V49_MAXIMUM_RAW_SEND_ATTEMPTS: Final = 65_536
V49_WRITABLE_DEADLINE_POLL_SECONDS: Final = 0.050
V49_READABLE_DEADLINE_POLL_SECONDS: Final = 0.050
V49C_MAXIMUM_STAGED_WIRE_CHUNKS: Final = 32
V49C_MAXIMUM_STAGED_WIRE_OCTETS: Final = 64 * 1024
V49C_MAXIMUM_STAGED_TLS_CIPHERTEXT_CHUNKS: Final = 256
# One complete maximum-size server frame plus the suffix of the raw batch that
# completed it.  The runtime must delineate and drain units before admitting
# another batch once a complete unit is available.
V49D_MAXIMUM_DURABLE_INGRESS_BUFFER_BYTES: Final = (
    V49_MAXIMUM_WEBSOCKET_MESSAGE_BYTES + V49_MAXIMUM_POST_UPGRADE_PENDING_BYTES + 14
)

_HTTP_END: Final = b"\r\n\r\n"
_WIRE_BATCH_DOMAIN: Final = "RiskYieldMMExactOrderedPreTlsWebSocketChunksV4_5"
_V49C_WIRE_BATCH_DOMAIN: Final = "RiskYieldMMActorOrderedProtocolOutputV4_9C"
_V49C_CIPHERTEXT_BATCH_DOMAIN: Final = "RiskYieldMMActorOrderedTlsCiphertextV4_9C"
_V49E_TLS_CONTROL_CIPHERTEXT_BATCH_DOMAIN: Final = (
    "RiskYieldMMActorOrderedTlsControlCiphertextV4_9E"
)
_EVIDENCE_TOKEN: Final = object()
_RAW_TOKEN: Final = object()
_PARSE_TOKEN: Final = object()
_RAW_SEND_TOKEN: Final = object()
_STAGED_SEND_TOKEN: Final = object()
_DURABLE_INGRESS_TOKEN: Final = object()
_DURABLE_PARSER_TOKEN: Final = object()
_TLS_CONTROL_TOKEN: Final = object()
_TLS_SHUTDOWN_OBSERVATION_TOKEN: Final = object()
_UNSENDABLE_TLS_OUTPUT_TOKEN: Final = object()
_UNSENDABLE_TLS_OUTPUT_EXCEPTION_TOKEN: Final = object()
_DEADLINE_EXPIRED_NO_OBSERVATION_TOKEN: Final = object()
_DEADLINE_EXPIRED_AFTER_PROGRESS_TOKEN: Final = object()
_SEND_DEADLINE_NO_KERNEL_ACCEPTANCE_TOKEN: Final = object()

_V49E_DEADLINE_OPERATIONS: Final = frozenset(
    {
        "TERMINAL_CLOSE_INGRESS",
        "LOCAL_WEBSOCKET_CLOSE_PREPARATION",
        "LOCAL_WEBSOCKET_CLOSE_TLS_PREPARATION",
        "WEBSOCKET_CLOSE_SEND_BEFORE_SYSCALL",
        "LOCAL_TLS_CLOSE_NOTIFY_PREPARATION",
        "TCP_WRITE_SHUTDOWN_TOKEN_PREPARATION",
        "TLS_SHUTDOWN_POLL",
        "TLS_CONTROL_SEND_BEFORE_SYSCALL",
    }
)


class PhysicalTlsWebSocketV49Error(RuntimeError):
    """Base error for the bounded V4.9A protocol engine."""


class PhysicalTlsWebSocketV49StateError(PhysicalTlsWebSocketV49Error):
    """The requested operation doesn't follow the one-owner state machine."""


class PhysicalTlsWebSocketV49DependencyError(PhysicalTlsWebSocketV49Error):
    """The exact reviewed transport dependency isn't installed."""


class PhysicalTlsWebSocketV49ProtocolError(PhysicalTlsWebSocketV49Error):
    """TLS, HTTP upgrade, or WebSocket behavior differs from the frozen profile."""


class PhysicalTlsWebSocketV49TruncatedEof(PhysicalTlsWebSocketV49ProtocolError):
    """The TCP stream ended without an authenticated TLS close."""


class PhysicalTlsWebSocketV49CleanTlsClose(PhysicalTlsWebSocketV49ProtocolError):
    """The peer sent TLS close_notify while an operation required more data."""


class PhysicalTlsWebSocketV49PostHandshakeOutputRequired(
    PhysicalTlsWebSocketV49ProtocolError
):
    """TLS requested post-handshake output outside the actor-ordered seam."""


class PhysicalTlsWebSocketV49DeadlineExpiredNoObservation(TimeoutError):
    """Exact V4.9E deadline expiry before this driver seam made progress."""

    __slots__ = ("_deadline_ns", "_operation")

    _deadline_ns: int
    _operation: str

    def __init__(
        self,
        *,
        _token: object,
        operation: str,
        deadline_ns: int,
    ) -> None:
        if _token is not _DEADLINE_EXPIRED_NO_OBSERVATION_TOKEN:
            raise TypeError(
                "no-observation deadline errors are driver-constructed only"
            )
        if (
            type(operation) is not str
            or operation not in _V49E_DEADLINE_OPERATIONS
            or type(deadline_ns) is not int
            or deadline_ns < 1
        ):
            raise TypeError("no-observation deadline evidence is invalid")
        self._operation = operation
        self._deadline_ns = deadline_ns
        super().__init__(
            f"V4.9E {operation} deadline expired before observable progress"
        )

    @property
    def operation(self) -> str:
        return self._operation

    @property
    def deadline_ns(self) -> int:
        return self._deadline_ns


class PhysicalTlsWebSocketV49DeadlineExpiredAfterProgress(TimeoutError):
    """Sealed partial-ciphertext fact from one expired terminal operation."""

    __slots__ = (
        "_ciphertext_octets_received",
        "_ciphertext_sha256",
        "_deadline_ns",
        "_driver_evidence_nonce_sha256",
        "_evidence_id",
        "_operation",
    )

    def __init__(
        self,
        *,
        _token: object,
        driver_evidence_nonce_sha256: str,
        operation: str,
        deadline_ns: int,
        ciphertext_octets_received: int,
        ciphertext_sha256: str,
        evidence_id: str,
    ) -> None:
        if _token is not _DEADLINE_EXPIRED_AFTER_PROGRESS_TOKEN:
            raise TypeError(
                "partial-progress deadline errors are driver-constructed only"
            )
        self._driver_evidence_nonce_sha256 = driver_evidence_nonce_sha256
        self._operation = operation
        self._deadline_ns = deadline_ns
        self._ciphertext_octets_received = ciphertext_octets_received
        self._ciphertext_sha256 = ciphertext_sha256
        self._evidence_id = evidence_id
        super().__init__(
            f"V4.9E {operation} deadline expired after positive ciphertext"
        )

    @property
    def driver_evidence_nonce_sha256(self) -> str:
        return self._driver_evidence_nonce_sha256

    @property
    def operation(self) -> str:
        return self._operation

    @property
    def deadline_ns(self) -> int:
        return self._deadline_ns

    @property
    def ciphertext_octets_received(self) -> int:
        return self._ciphertext_octets_received

    @property
    def ciphertext_sha256(self) -> str:
        return self._ciphertext_sha256

    @property
    def evidence_id(self) -> str:
        return self._evidence_id


class PhysicalTlsWebSocketV49SendDeadlineExpiredNoKernelAcceptance(TimeoutError):
    """Sealed send deadline fact after only conclusive would-block results."""

    __slots__ = tuple(
        f"_{name}"
        for name in (
            "driver_evidence_nonce_sha256",
            "send_kind",
            "transport_sequence",
            "ciphertext_batch_sha256",
            "ciphertext_octets",
            "ciphertext_start_octet",
            "requested_octets",
            "exact_slice_sha256",
            "deadline_ns",
            "would_block_count",
            "evidence_id",
        )
    )

    def __init__(self, *, _token: object, **values: Any) -> None:
        if _token is not _SEND_DEADLINE_NO_KERNEL_ACCEPTANCE_TOKEN:
            raise TypeError("send-deadline evidence is driver-constructed only")
        for name in (
            "driver_evidence_nonce_sha256",
            "send_kind",
            "transport_sequence",
            "ciphertext_batch_sha256",
            "ciphertext_octets",
            "ciphertext_start_octet",
            "requested_octets",
            "exact_slice_sha256",
            "deadline_ns",
            "would_block_count",
            "evidence_id",
        ):
            object.__setattr__(self, f"_{name}", values[name])
        super().__init__(
            "V4.9E send deadline expired after no kernel-accepted ciphertext"
        )

    @property
    def driver_evidence_nonce_sha256(self) -> str:
        return self._driver_evidence_nonce_sha256

    @property
    def send_kind(self) -> str:
        return self._send_kind

    @property
    def transport_sequence(self) -> int:
        return self._transport_sequence

    @property
    def ciphertext_batch_sha256(self) -> str:
        return self._ciphertext_batch_sha256

    @property
    def ciphertext_octets(self) -> int:
        return self._ciphertext_octets

    @property
    def ciphertext_start_octet(self) -> int:
        return self._ciphertext_start_octet

    @property
    def requested_octets(self) -> int:
        return self._requested_octets

    @property
    def exact_slice_sha256(self) -> str:
        return self._exact_slice_sha256

    @property
    def deadline_ns(self) -> int:
        return self._deadline_ns

    @property
    def would_block_count(self) -> int:
        return self._would_block_count

    @property
    def evidence_id(self) -> str:
        return self._evidence_id


class PhysicalTlsWebSocketV49UnsendablePostHandshakeOutput(
    PhysicalTlsWebSocketV49PostHandshakeOutputRequired
):
    """Post-SHUT_WR output was drained into exact negative evidence only."""

    evidence: UnsendableTlsPostHandshakeOutputV49E

    def __init__(
        self,
        *,
        _token: object,
        evidence: UnsendableTlsPostHandshakeOutputV49E,
        message: str,
    ) -> None:
        if _token is not _UNSENDABLE_TLS_OUTPUT_EXCEPTION_TOKEN:
            raise TypeError(
                "unsendable TLS-output exceptions are driver-constructed only"
            )
        if type(evidence) is not UnsendableTlsPostHandshakeOutputV49E:
            raise TypeError(
                "evidence must be exact UnsendableTlsPostHandshakeOutputV49E"
            )
        self.evidence = evidence
        super().__init__(message)


class RawSocketSendOutcomeV49(str, Enum):
    """One exact local ``socket.send`` syscall outcome.

    ``KERNEL_ACCEPTED`` means only that the local kernel accepted the returned
    number of ciphertext octets.  It is never evidence of peer receipt.
    """

    KERNEL_ACCEPTED = "KERNEL_ACCEPTED"
    WOULD_BLOCK = "WOULD_BLOCK"
    ERROR = "ERROR"
    INVALID_COUNT = "INVALID_COUNT"


class TlsControlOutputKindV49E(str, Enum):
    """Semantic origin of one exact, retained TLS-control ciphertext batch.

    Python's ``SSLObject`` doesn't expose the TLS handshake-message type that
    caused output while processing post-handshake input.  Such bytes are
    therefore deliberately opaque; callers must never relabel them as a Key
    Update or another more specific TLS message.
    """

    LOCAL_CLOSE_NOTIFY = "LOCAL_CLOSE_NOTIFY"
    OPAQUE_POST_HANDSHAKE_RESPONSE = "OPAQUE_POST_HANDSHAKE_RESPONSE"


class TlsShutdownObservationKindV49E(str, Enum):
    """One authenticated TLS or unauthenticated TCP shutdown observation."""

    PEER_CLOSE_NOTIFY = "PEER_CLOSE_NOTIFY"
    TCP_EOF = "TCP_EOF"


class TlsWebSocketDriverStateV49(str, Enum):
    DORMANT = "DORMANT"
    TLS_HANDSHAKING = "TLS_HANDSHAKING"
    WS_RESPONSE_BUFFERING = "WS_RESPONSE_BUFFERING"
    WS_OPEN_UNBOUND = "WS_OPEN_UNBOUND"
    RAW_INGRESS_PENDING = "RAW_INGRESS_PENDING"
    WS_OPEN_BOUND = "WS_OPEN_BOUND"
    OUTBOUND_WIRE_PREPARED_V49C = "OUTBOUND_WIRE_PREPARED_V49C"
    TLS_CIPHERTEXT_PREPARED_V49C = "TLS_CIPHERTEXT_PREPARED_V49C"
    TLS_CONTROL_CIPHERTEXT_PREPARED_V49E = "TLS_CONTROL_CIPHERTEXT_PREPARED_V49E"
    TLS_SHUTDOWN_V49E = "TLS_SHUTDOWN_V49E"
    PROTOCOL_OUTPUT_PENDING = "PROTOCOL_OUTPUT_PENDING"
    WS_CLOSING = "WS_CLOSING"
    FAULT_LATCHED = "FAULT_LATCHED"
    CLOSED = "CLOSED"


@dataclass(frozen=True, slots=True, kw_only=True)
class TlsWebSocketDriverFlowSnapshotV49F:
    """Immutable count-only view of one driver's retained transport work.

    This is local observability, not durability or transport authority.  It
    deliberately contains no plaintext, ciphertext, parser token, or staged
    send artifact.
    """

    driver_state: TlsWebSocketDriverStateV49
    memory_bio_incoming_pending_octets: int
    memory_bio_outgoing_pending_octets: int
    ssl_plaintext_pending_octets: int
    pending_raw_chunks: int
    pending_raw_octets: int
    durable_ingress_buffer_octets: int
    has_complete_durable_unit: bool
    protocol_output_chunks: int
    protocol_output_octets: int
    pending_send_eof: bool
    staged_websocket_wire_chunks: int
    staged_websocket_wire_octets: int
    pending_tls_ciphertext_octets: int
    remaining_pending_tls_ciphertext_octets: int
    staged_tls_ciphertext_octets: int
    remaining_staged_tls_ciphertext_octets: int
    staged_tls_control_ciphertext_octets: int
    remaining_staged_tls_control_ciphertext_octets: int

    def __post_init__(self) -> None:
        if type(self.driver_state) is not TlsWebSocketDriverStateV49:
            raise CanonicalizationError(
                "driver_state must be an exact TlsWebSocketDriverStateV49"
            )
        if type(self.has_complete_durable_unit) is not bool:
            raise CanonicalizationError(
                "has_complete_durable_unit must be an exact boolean"
            )
        if type(self.pending_send_eof) is not bool:
            raise CanonicalizationError("pending_send_eof must be an exact boolean")
        count_fields = (
            "memory_bio_incoming_pending_octets",
            "memory_bio_outgoing_pending_octets",
            "ssl_plaintext_pending_octets",
            "pending_raw_chunks",
            "pending_raw_octets",
            "durable_ingress_buffer_octets",
            "protocol_output_chunks",
            "protocol_output_octets",
            "staged_websocket_wire_chunks",
            "staged_websocket_wire_octets",
            "pending_tls_ciphertext_octets",
            "remaining_pending_tls_ciphertext_octets",
            "staged_tls_ciphertext_octets",
            "remaining_staged_tls_ciphertext_octets",
            "staged_tls_control_ciphertext_octets",
            "remaining_staged_tls_control_ciphertext_octets",
        )
        for field_name in count_fields:
            value = getattr(self, field_name)
            if type(value) is not int:
                raise CanonicalizationError(f"{field_name} must be an exact integer")
            object.__setattr__(
                self,
                field_name,
                canonical_safe_int(value, field=field_name, minimum=0),
            )
        if (
            self.pending_raw_chunks > V4_CONTROL_MAXIMUM_INGRESS_CHUNKS
            or self.pending_raw_octets > V49_MAXIMUM_POST_UPGRADE_PENDING_BYTES
            or (self.pending_raw_chunks == 0) != (self.pending_raw_octets == 0)
        ):
            raise CanonicalizationError(
                "pending RAW flow counts differ from the bounded ingress profile"
            )
        if (
            self.durable_ingress_buffer_octets
            > V49D_MAXIMUM_DURABLE_INGRESS_BUFFER_BYTES
            or (
                self.has_complete_durable_unit
                and self.durable_ingress_buffer_octets == 0
            )
        ):
            raise CanonicalizationError(
                "durable ingress flow counts differ from the bounded FIFO"
            )
        if (self.protocol_output_chunks == 0) != (self.protocol_output_octets == 0):
            raise CanonicalizationError(
                "protocol-output chunk and octet counts must be paired"
            )
        if (self.staged_websocket_wire_chunks == 0) != (
            self.staged_websocket_wire_octets == 0
        ) or (
            self.staged_websocket_wire_chunks > V49C_MAXIMUM_STAGED_WIRE_CHUNKS
            or self.staged_websocket_wire_octets > V49C_MAXIMUM_STAGED_WIRE_OCTETS
        ):
            raise CanonicalizationError(
                "staged WebSocket-wire chunk and octet counts must be paired"
            )
        for total_field, remaining_field in (
            (
                "pending_tls_ciphertext_octets",
                "remaining_pending_tls_ciphertext_octets",
            ),
            (
                "staged_tls_ciphertext_octets",
                "remaining_staged_tls_ciphertext_octets",
            ),
            (
                "staged_tls_control_ciphertext_octets",
                "remaining_staged_tls_control_ciphertext_octets",
            ),
        ):
            total = getattr(self, total_field)
            remaining = getattr(self, remaining_field)
            if (
                total > V49_MAXIMUM_TLS_OPERATION_CIPHERTEXT_BYTES
                or remaining > total
                or (total == 0) != (remaining == 0)
            ):
                raise CanonicalizationError(
                    f"{remaining_field} differs from its retained ciphertext total"
                )


@dataclass(frozen=True, slots=True, kw_only=True, init=False)
class RawSocketSendAttemptV49:
    """Ephemeral immutable description passed immediately before ``send``."""

    ciphertext_sha256: str
    ciphertext_octets: int
    attempt_sequence: int
    suffix_offset: int
    suffix_octets: int

    def __init__(self, *, _token: object, **values: Any) -> None:
        if _token is not _RAW_SEND_TOKEN:
            raise TypeError("raw socket send attempts are driver-constructed only")
        for name in self.__dataclass_fields__:
            object.__setattr__(self, name, values[name])


@dataclass(frozen=True, slots=True, kw_only=True, init=False)
class RawSocketSendResultV49:
    """Ephemeral result emitted synchronously after one ``send`` syscall."""

    attempt: RawSocketSendAttemptV49
    outcome: RawSocketSendOutcomeV49
    kernel_accepted_octets: int | None
    next_suffix_offset: int
    error_class: str | None
    error_errno: int | None

    def __init__(self, *, _token: object, **values: Any) -> None:
        if _token is not _RAW_SEND_TOKEN:
            raise TypeError("raw socket send results are driver-constructed only")
        for name in self.__dataclass_fields__:
            object.__setattr__(self, name, values[name])


@dataclass(frozen=True, slots=True, kw_only=True, init=False)
class RawSocketSendTraceV49:
    """Successful local send trace; this does not claim peer receipt."""

    ciphertext_sha256: str
    ciphertext_octets: int
    initial_suffix_offset: int
    final_suffix_offset: int
    positive_send_offsets: tuple[int, ...]
    positive_send_counts: tuple[int, ...]
    would_block_count: int
    attempt_count: int

    def __init__(self, *, _token: object, **values: Any) -> None:
        if _token is not _RAW_SEND_TOKEN:
            raise TypeError("raw socket send traces are driver-constructed only")
        for name in self.__dataclass_fields__:
            object.__setattr__(self, name, values[name])


@dataclass(frozen=True, slots=True, kw_only=True, init=False)
class PreparedWebSocketWireV49C:
    """One exact Sans-I/O client wire retained before any TLS or socket effect.

    Construction is module-restricted.  Possession of this value isn't send
    authority: the originating driver additionally requires the exact same
    object to be its one active FIFO head.
    """

    outbound_sequence: int
    logical_opcode: int
    logical_payload_sha256: str
    logical_payload_octets: int
    ordered_wire_chunks: tuple[bytes, ...]
    ordered_wire_chunks_sha256: tuple[str, ...]
    wire_batch_sha256: str
    wire_octets: int

    def __init__(self, *, _token: object, **values: Any) -> None:
        if _token is not _STAGED_SEND_TOKEN:
            raise TypeError("prepared WebSocket wire is driver-constructed only")
        for name in self.__dataclass_fields__:
            object.__setattr__(self, name, values[name])


@dataclass(frozen=True, slots=True, kw_only=True, init=False)
class PreparedTlsCiphertextV49C:
    """Exact TLS ciphertext retained until positive local kernel acceptance.

    ``ciphertext_batch_sha256`` uses the same ordered-chunk domain as the
    V4.9C actor contract.  It is not proof that a peer received any octet.
    """

    outbound_sequence: int
    prepared_wire: PreparedWebSocketWireV49C
    plaintext_batch_sha256: str
    plaintext_octets: int
    ordered_ciphertext_chunks: tuple[bytes, ...]
    ordered_ciphertext_chunks_sha256: tuple[str, ...]
    ciphertext_batch_sha256: str
    ciphertext_octets: int

    def __init__(self, *, _token: object, **values: Any) -> None:
        if _token is not _STAGED_SEND_TOKEN:
            raise TypeError("prepared TLS ciphertext is driver-constructed only")
        for name in self.__dataclass_fields__:
            object.__setattr__(self, name, values[name])

    @property
    def exact_ciphertext(self) -> bytes:
        """Return the exact immutable concatenated kernel-submission stream."""

        return b"".join(self.ordered_ciphertext_chunks)


@dataclass(frozen=True, slots=True, kw_only=True, init=False)
class PreparedTlsControlCiphertextV49E:
    """One exact TLS-control output batch retained until kernel acceptance.

    The semantic kind records only what the local operation can prove.  In
    particular, output caused while processing peer post-handshake traffic is
    intentionally opaque because CPython exposes bytes but no authenticated
    public API for the underlying TLS handshake-message type.
    """

    control_sequence: int
    control_kind: TlsControlOutputKindV49E
    driver_evidence_nonce_sha256: str
    ordered_ciphertext_chunks: tuple[bytes, ...]
    ordered_ciphertext_chunks_sha256: tuple[str, ...]
    ciphertext_batch_sha256: str
    ciphertext_octets: int
    peer_close_notify_received_during_preparation: bool

    def __init__(self, *, _token: object, **values: Any) -> None:
        if _token is not _TLS_CONTROL_TOKEN:
            raise TypeError("prepared TLS control is driver-constructed only")
        for name in self.__dataclass_fields__:
            object.__setattr__(self, name, values[name])

    @property
    def exact_ciphertext(self) -> bytes:
        """Return the exact immutable concatenated kernel-submission stream."""

        return b"".join(self.ordered_ciphertext_chunks)


@dataclass(frozen=True, slots=True, kw_only=True, init=False)
class TlsShutdownObservationV49E:
    """A sealed distinction between authenticated TLS close and raw TCP EOF."""

    observation_sequence: int
    observation_kind: TlsShutdownObservationKindV49E
    driver_evidence_nonce_sha256: str
    peer_close_notify_received: bool
    tcp_eof_received: bool
    truncated: bool
    ciphertext_octets_received: int
    observation_id: str

    def __init__(self, *, _token: object, **values: Any) -> None:
        if _token is not _TLS_SHUTDOWN_OBSERVATION_TOKEN:
            raise TypeError("TLS shutdown observations are driver-constructed only")
        for name in self.__dataclass_fields__:
            object.__setattr__(self, name, values[name])


@dataclass(frozen=True, slots=True, kw_only=True, init=False)
class UnsendableTlsPostHandshakeOutputV49E:
    """Exact summary of TLS output that cannot be sent after ``SHUT_WR``.

    The value deliberately retains no ciphertext bytes and exposes no send
    method or conversion to a positive TLS-control artifact.  It is negative
    replay evidence only.
    """

    output_sequence: int
    driver_evidence_nonce_sha256: str
    ciphertext_sha256: str
    ciphertext_octets: int
    unsendable_output_id: str

    def __init__(self, *, _token: object, **values: Any) -> None:
        if _token is not _UNSENDABLE_TLS_OUTPUT_TOKEN:
            raise TypeError("unsendable TLS output is driver-constructed only")
        for name in self.__dataclass_fields__:
            object.__setattr__(self, name, values[name])


RawSocketSendBeforeAttemptV49: TypeAlias = Callable[[RawSocketSendAttemptV49], None]
RawSocketSendAfterResultV49: TypeAlias = Callable[[RawSocketSendResultV49], None]


def _boottime_ns() -> int:
    clock_id = getattr(time, "CLOCK_BOOTTIME", None)
    if clock_id is None or not hasattr(time, "clock_gettime_ns"):
        raise PhysicalTlsWebSocketV49Error("Linux CLOCK_BOOTTIME is unavailable")
    value = time.clock_gettime_ns(clock_id)
    if type(value) is not int or value < 0:
        raise PhysicalTlsWebSocketV49Error("CLOCK_BOOTTIME returned an invalid value")
    return value


def split_http_upgrade_prefix_v49(buffer: bytes) -> tuple[bytes, bytes] | None:
    """Split one exact HTTP response head from any coalesced WebSocket suffix.

    ``None`` means that the four-byte delimiter isn't complete yet.  The
    function never normalizes, decodes, or reconstructs the transcript.
    """

    if type(buffer) is not bytes:
        raise TypeError("HTTP upgrade buffer must be exact bytes")
    marker = buffer.find(_HTTP_END)
    if marker < 0:
        return None
    boundary = marker + len(_HTTP_END)
    return buffer[:boundary], buffer[boundary:]


def _ordered_wire_batch_sha256(chunks: tuple[bytes, ...]) -> str:
    return sha256_digest(
        {
            "domain": _WIRE_BATCH_DOMAIN,
            "ordered_chunks_base64": [
                base64.b64encode(chunk).decode("ascii") for chunk in chunks
            ],
        }
    )


def _ordered_v49c_batch_sha256(domain: str, chunks: tuple[bytes, ...]) -> str:
    """Hash exact chunks with the V4.9C actor's frozen canonical domains."""

    if domain not in {_V49C_WIRE_BATCH_DOMAIN, _V49C_CIPHERTEXT_BATCH_DOMAIN}:
        raise PhysicalTlsWebSocketV49ProtocolError(
            "staged batch hash domain is outside the V4.9C contract"
        )
    return sha256_digest(
        {
            "domain": domain,
            "ordered_chunks_base64": [
                base64.b64encode(chunk).decode("ascii") for chunk in chunks
            ],
        }
    )


def _ordered_v49e_tls_control_batch_sha256(chunks: tuple[bytes, ...]) -> str:
    """Hash exact TLS-control chunks in their retained submission order."""

    return sha256_digest(
        {
            "domain": _V49E_TLS_CONTROL_CIPHERTEXT_BATCH_DOMAIN,
            "ordered_chunks_base64": [
                base64.b64encode(chunk).decode("ascii") for chunk in chunks
            ],
        }
    )


def _remote_address(value: Any) -> str:
    if not isinstance(value, tuple) or len(value) < 2:
        raise PhysicalTlsWebSocketV49ProtocolError(
            "connected socket returned an unsupported remote address"
        )
    host = value[0]
    port = value[1]
    if not isinstance(host, str) or type(port) is not int or not 1 <= port <= 65535:
        raise PhysicalTlsWebSocketV49ProtocolError(
            "connected socket returned an invalid remote address"
        )
    rendered = f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
    return canonical_identifier(rendered, field="remote_address", maximum=512)


def _decode_exact_client_frame(data: bytes) -> tuple[int, bytes]:
    """Validate and decode one complete canonical client WebSocket frame."""

    if type(data) is not bytes or len(data) < 6:
        raise PhysicalTlsWebSocketV49ProtocolError(
            "Sans-I/O output isn't a complete masked client frame"
        )
    first, second = data[0], data[1]
    if first & 0x70 or not first & 0x80 or not second & 0x80:
        raise PhysicalTlsWebSocketV49ProtocolError(
            "Sans-I/O client frame has RSV, fragmentation, or masking mismatch"
        )
    opcode = first & 0x0F
    length = second & 0x7F
    cursor = 2
    if length == 126:
        if len(data) < 8:
            raise PhysicalTlsWebSocketV49ProtocolError(
                "Sans-I/O client frame has a truncated 16-bit length"
            )
        length = int.from_bytes(data[cursor : cursor + 2], "big")
        cursor += 2
        if length < 126:
            raise PhysicalTlsWebSocketV49ProtocolError(
                "Sans-I/O client frame length isn't minimally encoded"
            )
    elif length == 127:
        if len(data) < 14:
            raise PhysicalTlsWebSocketV49ProtocolError(
                "Sans-I/O client frame has a truncated 64-bit length"
            )
        length = int.from_bytes(data[cursor : cursor + 8], "big")
        cursor += 8
        if length < 65536 or length >= 2**63:
            raise PhysicalTlsWebSocketV49ProtocolError(
                "Sans-I/O client frame length is invalid or non-minimal"
            )
    if length > V49_MAXIMUM_WEBSOCKET_MESSAGE_BYTES:
        raise PhysicalTlsWebSocketV49ProtocolError(
            "Sans-I/O client frame exceeds the reviewed bound"
        )
    mask = data[cursor : cursor + 4]
    if len(mask) != 4:
        raise PhysicalTlsWebSocketV49ProtocolError(
            "Sans-I/O client frame has a truncated mask"
        )
    cursor += 4
    if len(data) != cursor + length:
        raise PhysicalTlsWebSocketV49ProtocolError(
            "Sans-I/O output contains a partial or concatenated client frame"
        )
    payload = bytes(
        value ^ mask[index % 4] for index, value in enumerate(data[cursor:])
    )
    if opcode >= 0x8 and length > 125:
        raise PhysicalTlsWebSocketV49ProtocolError(
            "Sans-I/O control output exceeds 125 bytes"
        )
    return opcode, payload


def _next_server_parser_unit_octets_v49d(data: bytes) -> int | None:
    """Return the exact oldest complete frame/error prefix, or ``None``.

    This is only a structural boundary detector.  The pinned Sans-I/O parser
    remains authoritative for protocol state, fragmentation, Close payloads,
    and automatic output.  Deterministically invalid headers are returned at
    the minimum prefix that establishes the error so parser state never
    advances on an incomplete valid frame.
    """

    if type(data) is not bytes:
        raise TypeError("durable ingress buffer must be exact bytes")
    if len(data) < 2:
        return None
    first, second = data[0], data[1]
    opcode = first & 0x0F
    if (
        first & 0x70
        or opcode not in {0x0, 0x1, 0x2, 0x8, 0x9, 0xA}
        or second & 0x80
        or (opcode >= 0x8 and not first & 0x80)
    ):
        return 2

    marker = second & 0x7F
    header_octets = 2
    if opcode >= 0x8 and marker >= 126:
        return header_octets
    if marker < 126:
        payload_octets = marker
    elif marker == 126:
        header_octets = 4
        if len(data) < header_octets:
            return None
        payload_octets = int.from_bytes(data[2:4], "big")
        if payload_octets < 126:
            return header_octets
    else:
        header_octets = 10
        if len(data) < header_octets:
            return None
        payload_octets = int.from_bytes(data[2:10], "big")
        if payload_octets < 65_536 or payload_octets >= 2**63:
            return header_octets

    if opcode >= 0x8 and payload_octets > 125:
        return header_octets
    if payload_octets > V49_MAXIMUM_WEBSOCKET_MESSAGE_BYTES:
        return header_octets
    unit_octets = header_octets + payload_octets
    return unit_octets if len(data) >= unit_octets else None


@dataclass(frozen=True, slots=True, kw_only=True, init=False)
class DriverHandshakeEvidenceV49:
    """Noncanonical, one-driver handshake observation.

    Construction is restricted to this module.  This is evidence supplied to
    a future runtime record builder; it is not itself durable authority.
    """

    evidence_nonce_sha256: str
    remote_address: str
    tls_version: str
    tls_cipher: str
    alpn_protocol: str | None
    peer_certificate_sha256: str
    peer_spki_sha256: str
    certificate_verified: bool
    hostname_verified: bool
    websocket_http_status: int
    websocket_accept_verified: bool
    websocket_extensions: tuple[str, ...]
    handshake_request_sha256: str
    handshake_response_sha256: str
    handshake_request_octets: int
    handshake_response_octets: int
    coalesced_post_upgrade_octets: int
    trust_store_manifest_id: str
    websockets_version: str
    openssl_version: str

    def __init__(self, *, _token: object, **values: Any) -> None:
        if _token is not _EVIDENCE_TOKEN:
            raise TypeError("driver handshake evidence is engine-constructed only")
        for name in self.__dataclass_fields__:
            object.__setattr__(self, name, values[name])


@dataclass(frozen=True, slots=True, kw_only=True, init=False)
class PendingRawIngressV49:
    """Exact decrypted chunks which haven't reached the WebSocket parser."""

    driver_evidence_nonce_sha256: str
    ingress_sequence: int
    chunks: tuple[bytes, ...]
    total_octets: int

    def __init__(
        self,
        *,
        _token: object,
        driver_evidence_nonce_sha256: str,
        ingress_sequence: int,
        chunks: tuple[bytes, ...],
    ) -> None:
        if _token is not _RAW_TOKEN:
            raise TypeError("pending raw ingress is engine-constructed only")
        object.__setattr__(
            self,
            "driver_evidence_nonce_sha256",
            canonical_hash(
                driver_evidence_nonce_sha256,
                field="driver_evidence_nonce_sha256",
            ),
        )
        object.__setattr__(
            self,
            "ingress_sequence",
            canonical_safe_int(ingress_sequence, field="ingress_sequence", minimum=1),
        )
        if (
            type(chunks) is not tuple
            or not chunks
            or len(chunks) > V4_CONTROL_MAXIMUM_INGRESS_CHUNKS
            or any(type(chunk) is not bytes or not chunk for chunk in chunks)
        ):
            raise CanonicalizationError(
                "pending raw ingress requires exact non-empty byte chunks"
            )
        total = sum(len(chunk) for chunk in chunks)
        if total > V49_MAXIMUM_POST_UPGRADE_PENDING_BYTES:
            raise CanonicalizationError("pending raw ingress exceeds its byte bound")
        object.__setattr__(self, "chunks", chunks)
        object.__setattr__(self, "total_octets", total)


@dataclass(frozen=True, slots=True)
class WebSocketFrameEventV49:
    opcode: int
    fin: bool
    payload: bytes

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "opcode",
            canonical_safe_int(self.opcode, field="opcode", minimum=0, maximum=15),
        )
        if type(self.fin) is not bool or type(self.payload) is not bytes:
            raise CanonicalizationError("WebSocket frame event fields are invalid")


@dataclass(frozen=True, slots=True, kw_only=True, init=False)
class ParsedWebSocketIngressV49:
    """One raw-first parser transition and its held protocol output."""

    raw_ingress_commit_id: str
    ingress_sequence: int
    frame_events: tuple[WebSocketFrameEventV49, ...]
    protocol_output_chunks: tuple[bytes, ...]
    protocol_output_batch_sha256: str | None
    send_eof_after_output: bool
    parser_exception_class: str | None
    parser_exception_message: str | None

    def __init__(self, *, _token: object, **values: Any) -> None:
        if _token is not _PARSE_TOKEN:
            raise TypeError("parsed ingress evidence is engine-constructed only")
        for name in self.__dataclass_fields__:
            object.__setattr__(self, name, values[name])


@dataclass(frozen=True, slots=True, kw_only=True, init=False)
class DurableIngressAdoptionV49D:
    """Token-only proof that one pending RAW batch entered the durable buffer.

    This object does not prove storage durability by itself.  The caller may
    invoke the adoption boundary only after the exact ``RawIngressCommitV4``
    and its actor edge are durable.  Construction is restricted to the driver
    so copied record content cannot mint a parser capability.
    """

    raw_ingress_commit_id: str
    ingress_sequence: int
    adopted_octets: int
    durable_buffer_octets: int

    def __init__(self, *, _token: object, **values: Any) -> None:
        if _token is not _DURABLE_INGRESS_TOKEN:
            raise TypeError("durable ingress adoptions are driver-constructed only")
        for name in self.__dataclass_fields__:
            object.__setattr__(self, name, values[name])


@dataclass(frozen=True, slots=True, kw_only=True, init=False)
class ParsedDurableUnitV49D:
    """One token-only, frame-at-a-time Sans-I/O parser transition.

    ``consumed_unit`` is the exact oldest prefix of already-adopted durable
    plaintext.  A structurally invalid frame header may be the minimum prefix
    needed by ``websockets`` to produce its protocol failure and Close output.
    At most one frame event and one automatic Pong/Close frame are admitted.
    """

    parser_unit_sequence: int
    consumed_unit: bytes
    consumed_unit_sha256: str
    consumed_octets: int
    frame_event: WebSocketFrameEventV49 | None
    protocol_output_chunks: tuple[bytes, ...]
    protocol_output_chunks_sha256: tuple[str, ...]
    protocol_output_batch_sha256: str | None
    send_eof_after_output: bool
    parser_exception_class: str | None
    parser_exception_message: str | None
    remaining_durable_octets: int

    def __init__(self, *, _token: object, **values: Any) -> None:
        if _token is not _DURABLE_PARSER_TOKEN:
            raise TypeError("durable parser units are driver-constructed only")
        for name in self.__dataclass_fields__:
            object.__setattr__(self, name, values[name])


class ExactTlsWebSocketDriverV49:
    """One-shot TLS/WebSocket actor over one already-connected raw socket."""

    def __init__(
        self,
        *,
        trust_store: PinnedTlsTrustStoreV49,
        transport_policy: TransportSubscriptionPolicyV4,
    ) -> None:
        if type(self) is not ExactTlsWebSocketDriverV49:
            raise TypeError("V4.9A driver subclasses aren't promotion eligible")
        if type(trust_store) is not PinnedTlsTrustStoreV49:
            raise TypeError("trust_store must be an exact PinnedTlsTrustStoreV49")
        if type(transport_policy) is not TransportSubscriptionPolicyV4:
            raise TypeError(
                "transport_policy must be an exact TransportSubscriptionPolicyV4"
            )
        try:
            installed = importlib.metadata.version("websockets")
        except importlib.metadata.PackageNotFoundError as exc:
            raise PhysicalTlsWebSocketV49DependencyError(
                "websockets==16.0 isn't installed"
            ) from exc
        if installed != V49_WEBSOCKETS_VERSION:
            raise PhysicalTlsWebSocketV49DependencyError(
                "V4.9A requires exact websockets==16.0"
            )
        if (
            transport_policy.authoritative_endpoint != BYBIT_V5_LINEAR_ENDPOINT_V4
            or transport_policy.tls_server_name != BYBIT_V5_LINEAR_TLS_SERVER_NAME_V4
            or transport_policy.minimum_tls_version != "TLSv1.3"
            or transport_policy.allowed_websocket_extensions
            or transport_policy.allowed_subprotocols
        ):
            raise PhysicalTlsWebSocketV49ProtocolError(
                "transport policy differs from the reviewed V4.9A profile"
            )

        # Direct V4.9A construction remains useful for bounded protocol-engine
        # tests, but it deliberately carries no measured V4.9B runtime
        # authority and can never promote a Linux owner to a live profile.
        self._runtime_artifacts: PinnedTlsWebSocketRuntimeArtifactsV49B | None = None
        self._driver_policy_id: str | None = None
        self._runtime_observation_sha256: str | None = None
        self._runtime_environment_manifest_id: str | None = None
        self._trust_store = trust_store
        self._policy = transport_policy
        self._context = trust_store.build_context()
        self._context.hostname_checks_common_name = False
        self._context.post_handshake_auth = False
        self._context.keylog_filename = None
        self._context_options = self._context.options
        self._context_verify_flags = self._context.verify_flags
        self._context_cipher_profile = tuple(
            (
                item["name"],
                item["protocol"],
                item["strength_bits"],
            )
            for item in self._context.get_ciphers()
        )
        self._incoming = ssl.MemoryBIO()
        self._outgoing = ssl.MemoryBIO()
        self._tls = self._context.wrap_bio(
            self._incoming,
            self._outgoing,
            server_side=False,
            server_hostname=transport_policy.tls_server_name,
        )
        uri = parse_uri(transport_policy.authoritative_endpoint)
        if (
            not uri.secure
            or uri.host != transport_policy.tls_server_name
            or uri.port != transport_policy.port
            or uri.resource_name != transport_policy.websocket_path
        ):
            raise PhysicalTlsWebSocketV49ProtocolError(
                "signed endpoint doesn't map to the exact WebSocket URI"
            )
        self._protocol = ClientProtocol(
            uri,
            origin=None,
            extensions=None,
            subprotocols=None,
            max_size=V49_MAXIMUM_WEBSOCKET_MESSAGE_BYTES,
        )
        self._request = self._protocol.connect()
        self._validate_request()
        self._protocol.send_request(self._request)
        request_chunks = tuple(self._protocol.data_to_send())
        if (
            len(request_chunks) != 1
            or type(request_chunks[0]) is not bytes
            or not request_chunks[0]
        ):
            raise PhysicalTlsWebSocketV49ProtocolError(
                "Sans-I/O handshake request isn't one exact byte sequence"
            )
        self._request_bytes = request_chunks[0]
        self._state = TlsWebSocketDriverStateV49.DORMANT
        self._creator_pid = os.getpid()
        self._creator_thread_id = threading.get_ident()
        self._event_loop: asyncio.AbstractEventLoop | None = None
        self._actor_lock = asyncio.Lock()
        self._owned_socket: socket.socket | None = None
        self._socket_fd: int | None = None
        self._socket_stat: tuple[int, int] | None = None
        self._socket_peer: Any = None
        self._handshake_evidence: DriverHandshakeEvidenceV49 | None = None
        self._handshake_evidence_values: tuple[Any, ...] | None = None
        self._handshake_evidence_bound = False
        self._coalesced_tail: tuple[bytes, ...] = ()
        self._pending_raw: PendingRawIngressV49 | None = None
        self._durable_ingress_buffer_v49d = b""
        self._parser_unit_sequence_v49d = 0
        self._durable_ingress_mode_v49d = False
        self._fragmented_text_decoder_v49d: codecs.IncrementalDecoder | None = None
        self._pending_protocol_output: tuple[bytes, ...] = ()
        self._pending_send_eof = False
        self._ingress_sequence = 0
        self._operation_ciphertext_received = 0
        self._terminal_ingress_ciphertext_hasher_v49e: Any | None = None
        # MemoryBIO.read() consumes bytes.  Keep the exact immutable ciphertext
        # and suffix offset here until every octet has been accepted by local
        # socket.send() calls, including across exceptional exits.
        self._pending_tls_ciphertext = b""
        self._pending_tls_ciphertext_offset = 0
        self._staged_outbound_sequence_v49c = 0
        self._active_prepared_wire_v49c: PreparedWebSocketWireV49C | None = None
        self._active_prepared_wire_was_protocol_output_v49c = False
        self._active_prepared_tls_v49c: PreparedTlsCiphertextV49C | None = None
        self._active_prepared_tls_offset_v49c = 0
        self._tls_control_sequence_v49e = 0
        self._active_prepared_tls_control_v49e: (
            PreparedTlsControlCiphertextV49E | None
        ) = None
        self._active_prepared_tls_control_values_v49e: tuple[Any, ...] | None = None
        self._active_prepared_tls_control_offset_v49e = 0
        self._active_tls_control_prior_state_v49e: TlsWebSocketDriverStateV49 | None = (
            None
        )
        self._local_close_notify_prepared_v49e = False
        self._local_close_notify_fully_kernel_accepted_v49e = False
        self._peer_close_notify_received_v49e = False
        self._peer_close_notify_observation_emitted_v49e = False
        self._tcp_eof_received_v49e = False
        self._shutdown_observation_sequence_v49e = 0
        self._unsendable_tls_output_sequence_v49e = 0
        self._active_unsendable_tls_output_v49e: (
            UnsendableTlsPostHandshakeOutputV49E | None
        ) = None
        self._active_unsendable_tls_output_values_v49e: tuple[Any, ...] | None = None
        self._assert_tls_profile()

    @classmethod
    def from_measured_authority(
        cls,
        *,
        trust_store: PinnedTlsTrustStoreV49,
        transport_policy: TransportSubscriptionPolicyV4,
        runtime_artifacts: PinnedTlsWebSocketRuntimeArtifactsV49B,
    ) -> ExactTlsWebSocketDriverV49:
        """Construct the V4.9B candidate from one retained measured closure.

        The runtime-artifact authority is transferred to the driver.  Every
        exceptional exit closes both it and the trust-store authority; a
        caller cannot recover a half-constructed promotion candidate.
        """

        if cls is not ExactTlsWebSocketDriverV49:
            for resource in (trust_store, runtime_artifacts):
                closer = getattr(resource, "close", None)
                if callable(closer):
                    try:
                        closer()
                    except BaseException:
                        pass
            raise TypeError("V4.9B driver subclasses aren't promotion eligible")
        if type(runtime_artifacts) is not PinnedTlsWebSocketRuntimeArtifactsV49B:
            closer = getattr(trust_store, "close", None)
            if callable(closer):
                try:
                    closer()
                except BaseException:
                    pass
            raise TypeError(
                "runtime_artifacts must be an exact "
                "PinnedTlsWebSocketRuntimeArtifactsV49B"
            )
        driver: ExactTlsWebSocketDriverV49 | None = None
        try:
            runtime_artifacts.assert_current()
            driver = cls(
                trust_store=trust_store,
                transport_policy=transport_policy,
            )
            driver._runtime_artifacts = runtime_artifacts
            driver._driver_policy_id = runtime_artifacts.policy_id
            driver._runtime_observation_sha256 = (
                runtime_artifacts.runtime_observation_sha256
            )
            driver._runtime_environment_manifest_id = (
                runtime_artifacts.runtime_environment_manifest_id
            )
            driver.assert_current()
            return driver
        except BaseException:
            if driver is not None:
                driver.abort()
            else:
                for resource in (trust_store, runtime_artifacts):
                    closer = getattr(resource, "close", None)
                    if callable(closer):
                        try:
                            closer()
                        except BaseException:
                            pass
            raise

    @property
    def state(self) -> TlsWebSocketDriverStateV49:
        return self._state

    @property
    def durable_ingress_buffer_octets_v49d(self) -> int:
        """Return retained already-durable plaintext without exposing its bytes."""

        self._assert_context()
        return len(self._durable_ingress_buffer_v49d)

    @property
    def has_complete_durable_unit_v49d(self) -> bool:
        """Whether the oldest retained frame/error prefix is parser-ready."""

        self._assert_context()
        return (
            _next_server_parser_unit_octets_v49d(self._durable_ingress_buffer_v49d)
            is not None
        )

    async def transport_flow_snapshot_v49f(
        self,
    ) -> TlsWebSocketDriverFlowSnapshotV49F:
        """Observe retained driver work without exposing retained byte content.

        The driver actor lock makes all counts one local driver observation.
        The result is diagnostic only and grants no parser or send authority.
        """

        self._assert_context()
        loop = asyncio.get_running_loop()
        if self._event_loop is None or self._event_loop is not loop:
            raise PhysicalTlsWebSocketV49StateError(
                "V4.9F flow observation requires an already-bound event loop"
            )
        async with self._actor_lock:
            if (
                self._event_loop is not loop
                or not self._handshake_evidence_bound
                or self._state
                in {
                    TlsWebSocketDriverStateV49.DORMANT,
                    TlsWebSocketDriverStateV49.TLS_HANDSHAKING,
                    TlsWebSocketDriverStateV49.WS_RESPONSE_BUFFERING,
                    TlsWebSocketDriverStateV49.WS_OPEN_UNBOUND,
                    TlsWebSocketDriverStateV49.FAULT_LATCHED,
                    TlsWebSocketDriverStateV49.CLOSED,
                }
                or self._coalesced_tail
            ):
                raise PhysicalTlsWebSocketV49StateError(
                    "V4.9F flow observation requires one committed bound driver"
                )
            pending_raw = self._pending_raw
            if pending_raw is None:
                pending_raw_chunks = 0
                pending_raw_octets = 0
            else:
                if (
                    type(pending_raw) is not PendingRawIngressV49
                    or type(pending_raw.chunks) is not tuple
                    or not pending_raw.chunks
                    or any(
                        type(chunk) is not bytes or not chunk
                        for chunk in pending_raw.chunks
                    )
                    or type(pending_raw.total_octets) is not int
                    or pending_raw.total_octets != sum(map(len, pending_raw.chunks))
                ):
                    raise PhysicalTlsWebSocketV49StateError(
                        "retained pending RAW state is invalid"
                    )
                pending_raw_chunks = len(pending_raw.chunks)
                pending_raw_octets = pending_raw.total_octets

            protocol_output = self._pending_protocol_output
            if type(protocol_output) is not tuple or any(
                type(chunk) is not bytes or not chunk for chunk in protocol_output
            ):
                raise PhysicalTlsWebSocketV49StateError(
                    "retained protocol-output state is invalid"
                )

            staged_wire = self._active_prepared_wire_v49c
            if staged_wire is None:
                staged_wire_chunks = 0
                staged_wire_octets = 0
            else:
                if (
                    type(staged_wire) is not PreparedWebSocketWireV49C
                    or type(staged_wire.ordered_wire_chunks) is not tuple
                    or not staged_wire.ordered_wire_chunks
                    or any(
                        type(chunk) is not bytes or not chunk
                        for chunk in staged_wire.ordered_wire_chunks
                    )
                    or type(staged_wire.wire_octets) is not int
                    or staged_wire.wire_octets
                    != sum(map(len, staged_wire.ordered_wire_chunks))
                ):
                    raise PhysicalTlsWebSocketV49StateError(
                        "retained staged WebSocket wire state is invalid"
                    )
                staged_wire_chunks = len(staged_wire.ordered_wire_chunks)
                staged_wire_octets = staged_wire.wire_octets

            pending_tls = self._pending_tls_ciphertext
            pending_tls_offset = self._pending_tls_ciphertext_offset
            if (
                type(pending_tls) is not bytes
                or type(pending_tls_offset) is not int
                or pending_tls_offset < 0
                or pending_tls_offset > len(pending_tls)
                or (not pending_tls and pending_tls_offset != 0)
            ):
                raise PhysicalTlsWebSocketV49StateError(
                    "retained pending TLS ciphertext state is invalid"
                )
            pending_tls_octets = len(pending_tls)
            remaining_pending_tls_octets = pending_tls_octets - pending_tls_offset

            staged_tls = self._active_prepared_tls_v49c
            staged_tls_offset = self._active_prepared_tls_offset_v49c
            if staged_tls is None:
                if staged_tls_offset != 0:
                    raise PhysicalTlsWebSocketV49StateError(
                        "staged TLS offset exists without a retained artifact"
                    )
                staged_tls_octets = 0
                remaining_staged_tls_octets = 0
            else:
                if (
                    type(staged_tls) is not PreparedTlsCiphertextV49C
                    or type(staged_tls_offset) is not int
                    or type(staged_tls.ordered_ciphertext_chunks) is not tuple
                    or not staged_tls.ordered_ciphertext_chunks
                    or any(
                        type(chunk) is not bytes or not chunk
                        for chunk in staged_tls.ordered_ciphertext_chunks
                    )
                    or type(staged_tls.ciphertext_octets) is not int
                    or staged_tls.ciphertext_octets
                    != sum(map(len, staged_tls.ordered_ciphertext_chunks))
                    or not 0 <= staged_tls_offset < staged_tls.ciphertext_octets
                ):
                    raise PhysicalTlsWebSocketV49StateError(
                        "retained staged TLS ciphertext state is invalid"
                    )
                staged_tls_octets = staged_tls.ciphertext_octets
                remaining_staged_tls_octets = staged_tls_octets - staged_tls_offset

            staged_control = self._active_prepared_tls_control_v49e
            staged_control_offset = self._active_prepared_tls_control_offset_v49e
            if staged_control is None:
                if staged_control_offset != 0:
                    raise PhysicalTlsWebSocketV49StateError(
                        "TLS-control offset exists without a retained artifact"
                    )
                staged_control_octets = 0
                remaining_staged_control_octets = 0
            else:
                if (
                    type(staged_control) is not PreparedTlsControlCiphertextV49E
                    or type(staged_control_offset) is not int
                    or type(staged_control.ordered_ciphertext_chunks) is not tuple
                    or not staged_control.ordered_ciphertext_chunks
                    or any(
                        type(chunk) is not bytes or not chunk
                        for chunk in staged_control.ordered_ciphertext_chunks
                    )
                    or type(staged_control.ciphertext_octets) is not int
                    or staged_control.ciphertext_octets
                    != sum(map(len, staged_control.ordered_ciphertext_chunks))
                    or not 0 <= staged_control_offset < staged_control.ciphertext_octets
                ):
                    raise PhysicalTlsWebSocketV49StateError(
                        "retained staged TLS-control ciphertext state is invalid"
                    )
                staged_control_octets = staged_control.ciphertext_octets
                remaining_staged_control_octets = (
                    staged_control_octets - staged_control_offset
                )

            return TlsWebSocketDriverFlowSnapshotV49F(
                driver_state=self._state,
                memory_bio_incoming_pending_octets=self._incoming.pending,
                memory_bio_outgoing_pending_octets=self._outgoing.pending,
                ssl_plaintext_pending_octets=self._tls.pending(),
                pending_raw_chunks=pending_raw_chunks,
                pending_raw_octets=pending_raw_octets,
                durable_ingress_buffer_octets=len(self._durable_ingress_buffer_v49d),
                has_complete_durable_unit=(
                    _next_server_parser_unit_octets_v49d(
                        self._durable_ingress_buffer_v49d
                    )
                    is not None
                ),
                protocol_output_chunks=len(protocol_output),
                protocol_output_octets=sum(map(len, protocol_output)),
                pending_send_eof=self._pending_send_eof,
                staged_websocket_wire_chunks=staged_wire_chunks,
                staged_websocket_wire_octets=staged_wire_octets,
                pending_tls_ciphertext_octets=pending_tls_octets,
                remaining_pending_tls_ciphertext_octets=(remaining_pending_tls_octets),
                staged_tls_ciphertext_octets=staged_tls_octets,
                remaining_staged_tls_ciphertext_octets=(remaining_staged_tls_octets),
                staged_tls_control_ciphertext_octets=staged_control_octets,
                remaining_staged_tls_control_ciphertext_octets=(
                    remaining_staged_control_octets
                ),
            )

    @property
    def transport_policy(self) -> TransportSubscriptionPolicyV4:
        return self._policy

    @property
    def driver_policy_id(self) -> str | None:
        return self._driver_policy_id

    @property
    def runtime_observation_sha256(self) -> str | None:
        return self._runtime_observation_sha256

    @property
    def runtime_environment_manifest_id(self) -> str | None:
        return self._runtime_environment_manifest_id

    @property
    def is_exact_profile(self) -> bool:
        try:
            self.assert_current()
        except Exception:
            return False
        return type(self) is ExactTlsWebSocketDriverV49

    @property
    def is_v49b_measured_profile(self) -> bool:
        authority = self._runtime_artifacts
        if type(authority) is not PinnedTlsWebSocketRuntimeArtifactsV49B:
            return False
        try:
            self.assert_current()
        except Exception:
            return False
        return (
            type(self) is ExactTlsWebSocketDriverV49
            and self._driver_policy_id == authority.policy_id
            and self._runtime_observation_sha256 == authority.runtime_observation_sha256
            and self._runtime_environment_manifest_id
            == authority.runtime_environment_manifest_id
        )

    @property
    def is_v49b_promotion_eligible(self) -> bool:
        authority = self._runtime_artifacts
        return (
            self.is_v49b_measured_profile
            and type(authority) is PinnedTlsWebSocketRuntimeArtifactsV49B
            and authority.is_promotion_eligible
        )

    def _validate_request(self) -> None:
        if self._request.path != self._policy.websocket_path:
            raise PhysicalTlsWebSocketV49ProtocolError(
                "Sans-I/O request path differs from signed policy"
            )
        raw_headers = list(self._request.headers.raw_items())
        names = [name.lower() for name, _ in raw_headers]
        required = {
            "host",
            "upgrade",
            "connection",
            "sec-websocket-key",
            "sec-websocket-version",
        }
        if set(names) != required or len(names) != len(required):
            raise PhysicalTlsWebSocketV49ProtocolError(
                "Sans-I/O request headers differ from the exact profile"
            )
        if (
            self._request.headers["Host"] != self._policy.tls_server_name
            or self._request.headers["Upgrade"].lower() != "websocket"
            or self._request.headers["Connection"].lower() != "upgrade"
            or self._request.headers["Sec-WebSocket-Version"] != "13"
        ):
            raise PhysicalTlsWebSocketV49ProtocolError(
                "Sans-I/O request header values differ from the exact profile"
            )

    def _assert_context(self) -> None:
        if (
            os.getpid() != self._creator_pid
            or threading.get_ident() != self._creator_thread_id
        ):
            raise PhysicalTlsWebSocketV49StateError(
                "TLS/WebSocket engine left its creating process/thread"
            )
        if self._event_loop is not None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is not None and loop is not self._event_loop:
                raise PhysicalTlsWebSocketV49StateError(
                    "TLS/WebSocket engine moved to another event loop"
                )

    def _assert_tls_profile(self) -> None:
        self._trust_store.assert_current()
        no_compression = getattr(ssl, "OP_NO_COMPRESSION", 0)
        no_ticket = getattr(ssl, "OP_NO_TICKET", 0)
        loaded_der = tuple(self._context.get_ca_certs(binary_form=True))
        manifest = self._trust_store.manifest
        if (
            self._tls.context is not self._context
            or self._context.minimum_version is not ssl.TLSVersion.TLSv1_3
            or self._context.maximum_version is not ssl.TLSVersion.TLSv1_3
            or self._context.verify_mode is not ssl.CERT_REQUIRED
            or not self._context.check_hostname
            or self._context.hostname_checks_common_name
            or self._context.post_handshake_auth
            or self._context.keylog_filename is not None
            or self._context.options != self._context_options
            or self._context.verify_flags != self._context_verify_flags
            or tuple(
                (
                    item["name"],
                    item["protocol"],
                    item["strength_bits"],
                )
                for item in self._context.get_ciphers()
            )
            != self._context_cipher_profile
            or len(loaded_der) != manifest.ca_certificate_count
            or len(set(loaded_der)) != len(loaded_der)
            or derive_tls_ca_der_set_root_v49(loaded_der)
            != manifest.ca_der_set_root_sha256
            or (no_compression and not self._context.options & no_compression)
            or (no_ticket and not self._context.options & no_ticket)
        ):
            raise PhysicalTlsWebSocketV49StateError(
                "private TLS context changed from the V4.9A profile"
            )

    def assert_current(self) -> None:
        self._assert_context()
        if self._state in {
            TlsWebSocketDriverStateV49.FAULT_LATCHED,
            TlsWebSocketDriverStateV49.CLOSED,
        }:
            raise PhysicalTlsWebSocketV49StateError(
                "TLS/WebSocket engine isn't current"
            )
        self._assert_measured_authority_current_v49e()
        if self._owned_socket is not None:
            if self._state is TlsWebSocketDriverStateV49.TLS_SHUTDOWN_V49E:
                self._assert_shutdown_socket_v49e(self._owned_socket)
            else:
                self._assert_socket(self._owned_socket)

    def assert_terminal_journal_authority_v49e(self) -> None:
        """Revalidate exact identity after terminal I/O has fault-latched.

        This grants no driver or socket mutation.  It exists only so the
        retained actor can timestamp and journal exact owner evidence after a
        peer disconnect or terminal driver fault.  CLOSED and all pre-shutdown
        states remain inadmissible.
        """

        self._assert_context()
        if self._state not in {
            TlsWebSocketDriverStateV49.TLS_SHUTDOWN_V49E,
            TlsWebSocketDriverStateV49.FAULT_LATCHED,
        }:
            raise PhysicalTlsWebSocketV49StateError(
                "terminal journal authority requires shutdown or fault-latched state"
            )
        self._assert_measured_authority_current_v49e()
        if self._owned_socket is not None:
            self._assert_shutdown_socket_v49e(self._owned_socket)

    def _latch_terminal_journal_fault_v49e(self) -> None:
        """Irreversibly fence a bound driver for evidence-only journaling.

        Owner-side V4.9E evidence may become decisive before TLS shutdown is
        entered, for example while an already-sent WebSocket Close is waiting
        for its peer Close.  The exact consumed owner capability authorizes
        this private transition.  It never restores I/O: the only admitted
        successor is ``FAULT_LATCHED``, whose remaining authority is identity
        validation for durable terminal evidence.
        """

        self._assert_context()
        if self._state is TlsWebSocketDriverStateV49.FAULT_LATCHED:
            self.assert_terminal_journal_authority_v49e()
            return
        if self._state not in {
            TlsWebSocketDriverStateV49.WS_OPEN_BOUND,
            TlsWebSocketDriverStateV49.OUTBOUND_WIRE_PREPARED_V49C,
            TlsWebSocketDriverStateV49.TLS_CIPHERTEXT_PREPARED_V49C,
            TlsWebSocketDriverStateV49.TLS_CONTROL_CIPHERTEXT_PREPARED_V49E,
            TlsWebSocketDriverStateV49.TLS_SHUTDOWN_V49E,
            TlsWebSocketDriverStateV49.WS_CLOSING,
        }:
            raise PhysicalTlsWebSocketV49StateError(
                "terminal journal fault requires one bound post-upgrade state"
            )
        self._assert_measured_authority_current_v49e()
        if self._owned_socket is not None:
            if self._state is TlsWebSocketDriverStateV49.TLS_SHUTDOWN_V49E:
                self._assert_shutdown_socket_v49e(self._owned_socket)
            else:
                self._assert_socket(self._owned_socket)
        self._state = TlsWebSocketDriverStateV49.FAULT_LATCHED
        self.assert_terminal_journal_authority_v49e()

    def _assert_measured_authority_current_v49e(self) -> None:
        """Revalidate immutable measured-driver and handshake provenance."""

        authority = self._runtime_artifacts
        if authority is not None:
            if type(authority) is not PinnedTlsWebSocketRuntimeArtifactsV49B:
                raise PhysicalTlsWebSocketV49StateError(
                    "runtime artifact authority type changed"
                )
            authority.assert_current()
            if (
                self._driver_policy_id != authority.policy_id
                or self._runtime_observation_sha256
                != authority.runtime_observation_sha256
                or self._runtime_environment_manifest_id
                != authority.runtime_environment_manifest_id
            ):
                raise PhysicalTlsWebSocketV49StateError(
                    "measured runtime authority changed after driver construction"
                )
        elif any(
            value is not None
            for value in (
                self._driver_policy_id,
                self._runtime_observation_sha256,
                self._runtime_environment_manifest_id,
            )
        ):
            raise PhysicalTlsWebSocketV49StateError(
                "driver measurement identities exist without retained authority"
            )
        try:
            installed = importlib.metadata.version("websockets")
        except importlib.metadata.PackageNotFoundError as exc:
            raise PhysicalTlsWebSocketV49DependencyError(
                "websockets distribution disappeared"
            ) from exc
        if installed != V49_WEBSOCKETS_VERSION:
            raise PhysicalTlsWebSocketV49DependencyError(
                "websockets distribution changed after construction"
            )
        self._assert_tls_profile()
        if self._handshake_evidence is not None and (
            tuple(
                getattr(self._handshake_evidence, name)
                for name in DriverHandshakeEvidenceV49.__dataclass_fields__
            )
            != self._handshake_evidence_values
        ):
            raise PhysicalTlsWebSocketV49StateError(
                "retained handshake evidence changed after observation"
            )

    def _bind_socket(self, owned_socket: socket.socket) -> None:
        if type(owned_socket) is not socket.socket:
            raise TypeError("owned_socket must be an exact socket.socket")
        if owned_socket.family not in {socket.AF_INET, socket.AF_INET6}:
            raise PhysicalTlsWebSocketV49StateError(
                "V4.9A requires an AF_INET or AF_INET6 socket"
            )
        if (
            owned_socket.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE)
            != socket.SOCK_STREAM
        ):
            raise PhysicalTlsWebSocketV49StateError("V4.9A requires a stream socket")
        if owned_socket.getblocking() or owned_socket.gettimeout() != 0.0:
            raise PhysicalTlsWebSocketV49StateError(
                "V4.9A requires the retained socket to be nonblocking"
            )
        peer = owned_socket.getpeername()
        fd = owned_socket.fileno()
        stat_result = os.fstat(fd)
        self._owned_socket = owned_socket
        self._socket_fd = fd
        self._socket_stat = (stat_result.st_dev, stat_result.st_ino)
        self._socket_peer = peer

    def _assert_socket(self, owned_socket: socket.socket) -> None:
        if owned_socket is not self._owned_socket:
            raise PhysicalTlsWebSocketV49StateError(
                "operation presented a different socket object"
            )
        if (
            self._socket_fd is None
            or owned_socket.fileno() != self._socket_fd
            or owned_socket.getblocking()
            or owned_socket.gettimeout() != 0.0
            or owned_socket.getpeername() != self._socket_peer
        ):
            raise PhysicalTlsWebSocketV49StateError(
                "retained socket identity or mode changed"
            )
        stat_result = os.fstat(self._socket_fd)
        if (stat_result.st_dev, stat_result.st_ino) != self._socket_stat:
            raise PhysicalTlsWebSocketV49StateError(
                "retained socket descriptor was replaced"
            )

    def _assert_shutdown_socket_v49e(self, owned_socket: socket.socket) -> None:
        """Retain fd identity after peer FIN makes ``getpeername`` unavailable."""

        if owned_socket is not self._owned_socket:
            raise PhysicalTlsWebSocketV49StateError(
                "shutdown poll presented a different socket object"
            )
        if (
            self._socket_fd is None
            or owned_socket.fileno() != self._socket_fd
            or owned_socket.getblocking()
            or owned_socket.gettimeout() != 0.0
        ):
            raise PhysicalTlsWebSocketV49StateError(
                "shutdown socket identity or mode changed"
            )
        try:
            peer = owned_socket.getpeername()
        except OSError as exc:
            if exc.errno != errno.ENOTCONN:
                raise PhysicalTlsWebSocketV49StateError(
                    "shutdown socket peer identity failed unexpectedly"
                ) from exc
        else:
            if peer != self._socket_peer:
                raise PhysicalTlsWebSocketV49StateError(
                    "shutdown socket peer identity changed"
                )
        stat_result = os.fstat(self._socket_fd)
        if (stat_result.st_dev, stat_result.st_ino) != self._socket_stat:
            raise PhysicalTlsWebSocketV49StateError(
                "shutdown socket descriptor was replaced"
            )

    def _assert_async_context(self) -> None:
        self._assert_context()
        loop = asyncio.get_running_loop()
        if self._event_loop is None:
            self._event_loop = loop
        elif self._event_loop is not loop:
            raise PhysicalTlsWebSocketV49StateError(
                "TLS/WebSocket engine moved to another event loop"
            )

    @staticmethod
    def _remaining_seconds(deadline_ns: int) -> float:
        remaining_ns = deadline_ns - _boottime_ns()
        if remaining_ns <= 0:
            raise TimeoutError("V4.9A absolute CLOCK_BOOTTIME deadline elapsed")
        return remaining_ns / 1_000_000_000

    @staticmethod
    def _bounded_absolute_deadline_v49e(deadline_ns: int) -> int:
        if type(deadline_ns) is not int or deadline_ns < 1:
            raise PhysicalTlsWebSocketV49ProtocolError(
                "V4.9E deadline must be an absolute CLOCK_BOOTTIME integer"
            )
        remaining_ns = deadline_ns - _boottime_ns()
        if remaining_ns <= 0:
            raise TimeoutError("V4.9E absolute CLOCK_BOOTTIME deadline elapsed")
        if remaining_ns > 300 * 10**9:
            raise PhysicalTlsWebSocketV49ProtocolError(
                "V4.9E absolute deadline exceeds the bounded operation window"
            )
        return deadline_ns

    @staticmethod
    def _deadline_expired_no_observation_v49e(
        *, operation: str, deadline_ns: int
    ) -> PhysicalTlsWebSocketV49DeadlineExpiredNoObservation:
        return PhysicalTlsWebSocketV49DeadlineExpiredNoObservation(
            _token=_DEADLINE_EXPIRED_NO_OBSERVATION_TOKEN,
            operation=operation,
            deadline_ns=deadline_ns,
        )

    @staticmethod
    def _assert_deadline_expired_after_progress_integrity_v49e(
        exc: PhysicalTlsWebSocketV49DeadlineExpiredAfterProgress,
    ) -> None:
        if type(exc) is not PhysicalTlsWebSocketV49DeadlineExpiredAfterProgress:
            raise TypeError(
                "exc must be exact PhysicalTlsWebSocketV49DeadlineExpiredAfterProgress"
            )
        if (
            type(exc.driver_evidence_nonce_sha256) is not str
            or len(exc.driver_evidence_nonce_sha256) != 64
            or any(
                char not in "0123456789abcdef"
                for char in exc.driver_evidence_nonce_sha256
            )
            or exc.operation not in {"TERMINAL_CLOSE_INGRESS", "TLS_SHUTDOWN_POLL"}
            or type(exc.deadline_ns) is not int
            or exc.deadline_ns < 1
            or type(exc.ciphertext_octets_received) is not int
            or not 1
            <= exc.ciphertext_octets_received
            <= V49_MAXIMUM_TLS_OPERATION_CIPHERTEXT_BYTES
            or type(exc.ciphertext_sha256) is not str
            or len(exc.ciphertext_sha256) != 64
            or any(char not in "0123456789abcdef" for char in exc.ciphertext_sha256)
        ):
            raise PhysicalTlsWebSocketV49ProtocolError(
                "partial-progress deadline evidence has invalid exact fields"
            )
        values = {
            "domain": "RiskYieldMMDeadlineExpiredAfterProgressV4_9E",
            "driver_evidence_nonce_sha256": exc.driver_evidence_nonce_sha256,
            "operation": exc.operation,
            "deadline_ns": exc.deadline_ns,
            "ciphertext_octets_received": exc.ciphertext_octets_received,
            "ciphertext_sha256": exc.ciphertext_sha256,
        }
        if exc.evidence_id != sha256_digest(values):
            raise PhysicalTlsWebSocketV49ProtocolError(
                "partial-progress deadline evidence ID differs from exact fields"
            )

    def _deadline_expired_after_progress_v49e(
        self,
        *,
        operation: str,
        deadline_ns: int,
        ciphertext_octets_received: int,
        ciphertext_sha256: str,
    ) -> PhysicalTlsWebSocketV49DeadlineExpiredAfterProgress:
        evidence = self._handshake_evidence
        if (
            type(evidence) is not DriverHandshakeEvidenceV49
            or not self._handshake_evidence_bound
        ):
            raise PhysicalTlsWebSocketV49StateError(
                "partial deadline timeout lacks handshake authority"
            )
        values = {
            "domain": "RiskYieldMMDeadlineExpiredAfterProgressV4_9E",
            "driver_evidence_nonce_sha256": evidence.evidence_nonce_sha256,
            "operation": operation,
            "deadline_ns": deadline_ns,
            "ciphertext_octets_received": ciphertext_octets_received,
            "ciphertext_sha256": ciphertext_sha256,
        }
        progress = PhysicalTlsWebSocketV49DeadlineExpiredAfterProgress(
            _token=_DEADLINE_EXPIRED_AFTER_PROGRESS_TOKEN,
            driver_evidence_nonce_sha256=evidence.evidence_nonce_sha256,
            operation=operation,
            deadline_ns=deadline_ns,
            ciphertext_octets_received=ciphertext_octets_received,
            ciphertext_sha256=ciphertext_sha256,
            evidence_id=sha256_digest(values),
        )
        self._assert_deadline_expired_after_progress_integrity_v49e(progress)
        return progress

    @staticmethod
    def _assert_send_deadline_no_kernel_acceptance_integrity_v49e(
        exc: PhysicalTlsWebSocketV49SendDeadlineExpiredNoKernelAcceptance,
    ) -> None:
        if (
            type(exc)
            is not PhysicalTlsWebSocketV49SendDeadlineExpiredNoKernelAcceptance
        ):
            raise TypeError(
                "exc must be exact "
                "PhysicalTlsWebSocketV49SendDeadlineExpiredNoKernelAcceptance"
            )
        if (
            type(exc.driver_evidence_nonce_sha256) is not str
            or len(exc.driver_evidence_nonce_sha256) != 64
            or any(
                char not in "0123456789abcdef"
                for char in exc.driver_evidence_nonce_sha256
            )
            or exc.send_kind
            not in {
                "LOCAL_WEBSOCKET_CLOSE",
                "AUTOMATIC_WEBSOCKET_CLOSE",
                "TLS_CONTROL",
            }
            or type(exc.transport_sequence) is not int
            or exc.transport_sequence < 1
            or type(exc.ciphertext_batch_sha256) is not str
            or len(exc.ciphertext_batch_sha256) != 64
            or type(exc.ciphertext_octets) is not int
            or exc.ciphertext_octets < 1
            or type(exc.ciphertext_start_octet) is not int
            or not 0 <= exc.ciphertext_start_octet < exc.ciphertext_octets
            or type(exc.requested_octets) is not int
            or not 1
            <= exc.requested_octets
            <= exc.ciphertext_octets - exc.ciphertext_start_octet
            or type(exc.exact_slice_sha256) is not str
            or len(exc.exact_slice_sha256) != 64
            or type(exc.deadline_ns) is not int
            or exc.deadline_ns < 1
            or type(exc.would_block_count) is not int
            or not 1 <= exc.would_block_count <= V49_MAXIMUM_RAW_SEND_ATTEMPTS
        ):
            raise PhysicalTlsWebSocketV49ProtocolError(
                "send-deadline evidence has invalid exact fields"
            )
        values = {
            "domain": "RiskYieldMMTlsSendDeadlineNoKernelAcceptanceV4_9E",
            "driver_evidence_nonce_sha256": exc.driver_evidence_nonce_sha256,
            "send_kind": exc.send_kind,
            "transport_sequence": exc.transport_sequence,
            "ciphertext_batch_sha256": exc.ciphertext_batch_sha256,
            "ciphertext_octets": exc.ciphertext_octets,
            "ciphertext_start_octet": exc.ciphertext_start_octet,
            "requested_octets": exc.requested_octets,
            "exact_slice_sha256": exc.exact_slice_sha256,
            "deadline_ns": exc.deadline_ns,
            "would_block_count": exc.would_block_count,
        }
        if exc.evidence_id != sha256_digest(values):
            raise PhysicalTlsWebSocketV49ProtocolError(
                "send-deadline evidence ID differs from exact fields"
            )

    def _send_deadline_no_kernel_acceptance_v49e(
        self,
        *,
        send_kind: str,
        transport_sequence: int,
        ciphertext_batch_sha256: str,
        ciphertext_octets: int,
        ciphertext_start_octet: int,
        exact_slice: bytes,
        deadline_ns: int,
        would_block_count: int,
    ) -> PhysicalTlsWebSocketV49SendDeadlineExpiredNoKernelAcceptance:
        evidence = self._handshake_evidence
        if (
            type(evidence) is not DriverHandshakeEvidenceV49
            or not self._handshake_evidence_bound
        ):
            raise PhysicalTlsWebSocketV49StateError(
                "send-deadline evidence lacks bound handshake authority"
            )
        values = {
            "domain": "RiskYieldMMTlsSendDeadlineNoKernelAcceptanceV4_9E",
            "driver_evidence_nonce_sha256": evidence.evidence_nonce_sha256,
            "send_kind": send_kind,
            "transport_sequence": transport_sequence,
            "ciphertext_batch_sha256": ciphertext_batch_sha256,
            "ciphertext_octets": ciphertext_octets,
            "ciphertext_start_octet": ciphertext_start_octet,
            "requested_octets": len(exact_slice),
            "exact_slice_sha256": hashlib.sha256(exact_slice).hexdigest(),
            "deadline_ns": deadline_ns,
            "would_block_count": would_block_count,
        }
        exc = PhysicalTlsWebSocketV49SendDeadlineExpiredNoKernelAcceptance(
            _token=_SEND_DEADLINE_NO_KERNEL_ACCEPTANCE_TOKEN,
            **values,
            evidence_id=sha256_digest(values),
        )
        self._assert_send_deadline_no_kernel_acceptance_integrity_v49e(exc)
        return exc

    @staticmethod
    def _call_raw_send_callback(
        callback: Callable[[Any], Any] | None,
        value: RawSocketSendAttemptV49 | RawSocketSendResultV49,
        *,
        field: str,
    ) -> None:
        if callback is None:
            return
        returned = callback(value)
        if inspect.isawaitable(returned):
            # Avoid an un-awaited coroutine warning while still failing closed:
            # no scheduling point is permitted between the journal callback and
            # the corresponding raw syscall boundary.
            closer = getattr(returned, "close", None)
            if callable(closer):
                closer()
            raise TypeError(f"{field} must be synchronous, not awaitable")
        if returned is not None:
            raise TypeError(f"{field} must return None")

    async def _wait_socket_writable(
        self, owned_socket: socket.socket, *, deadline_ns: int
    ) -> None:
        """Wait for one writable notification against an absolute BOOTTIME cap."""

        if not self._actor_lock.locked():
            raise PhysicalTlsWebSocketV49StateError(
                "raw socket readiness wait requires the driver actor lock"
            )
        self._assert_socket(owned_socket)
        self._remaining_seconds(deadline_ns)
        loop = asyncio.get_running_loop()
        fd = self._socket_fd
        assert fd is not None
        ready = loop.create_future()

        def mark_ready() -> None:
            if not ready.done():
                ready.set_result(None)

        loop.add_writer(fd, mark_ready)
        try:
            while not ready.done():
                timeout = min(
                    self._remaining_seconds(deadline_ns),
                    V49_WRITABLE_DEADLINE_POLL_SECONDS,
                )
                try:
                    await asyncio.wait_for(asyncio.shield(ready), timeout=timeout)
                except TimeoutError:
                    # asyncio's timer uses its own monotonic clock.  Re-sample
                    # CLOCK_BOOTTIME after every short slice so suspend time is
                    # included in the authoritative absolute deadline.
                    self._remaining_seconds(deadline_ns)
        finally:
            loop.remove_writer(fd)

        # A cancellation queued by the readiness callback must win before the
        # next syscall.  This await is outside the before/send/after boundary.
        await asyncio.sleep(0)
        self._remaining_seconds(deadline_ns)
        self._assert_socket(owned_socket)

    async def _wait_socket_readable_v49e(
        self,
        owned_socket: socket.socket,
        *,
        deadline_ns: int,
        shutdown_socket_v49e: bool = False,
    ) -> None:
        """Wait without consuming bytes, then recheck BOOTTIME before recv."""

        if not self._actor_lock.locked():
            raise PhysicalTlsWebSocketV49StateError(
                "raw socket readiness wait requires the driver actor lock"
            )
        if shutdown_socket_v49e:
            self._assert_shutdown_socket_v49e(owned_socket)
        else:
            self._assert_socket(owned_socket)
        self._remaining_seconds(deadline_ns)
        loop = asyncio.get_running_loop()
        fd = self._socket_fd
        assert fd is not None
        ready = loop.create_future()

        def mark_ready() -> None:
            if not ready.done():
                ready.set_result(None)

        loop.add_reader(fd, mark_ready)
        try:
            while not ready.done():
                timeout = min(
                    self._remaining_seconds(deadline_ns),
                    V49_READABLE_DEADLINE_POLL_SECONDS,
                )
                try:
                    await asyncio.wait_for(asyncio.shield(ready), timeout=timeout)
                except TimeoutError:
                    self._remaining_seconds(deadline_ns)
        finally:
            loop.remove_reader(fd)

        # Cancellation and the authoritative deadline must win before recv.
        await asyncio.sleep(0)
        self._remaining_seconds(deadline_ns)
        if shutdown_socket_v49e:
            self._assert_shutdown_socket_v49e(owned_socket)
        else:
            self._assert_socket(owned_socket)

    async def _send_raw_ciphertext(
        self,
        owned_socket: socket.socket,
        ciphertext: bytes,
        *,
        initial_suffix_offset: int,
        deadline_ns: int,
        before_attempt: RawSocketSendBeforeAttemptV49 | None = None,
        after_result: RawSocketSendAfterResultV49 | None = None,
    ) -> RawSocketSendTraceV49:
        """Submit one immutable ciphertext suffix with explicit ``send`` calls.

        Every positive return is retained in the successful trace and emitted
        synchronously through ``after_result``.  A return value records local
        kernel acceptance only; this method makes no peer-delivery claim.
        """

        if not self._actor_lock.locked():
            raise PhysicalTlsWebSocketV49StateError(
                "raw socket send requires the driver actor lock"
            )
        if (
            type(ciphertext) is not bytes
            or not ciphertext
            or len(ciphertext) > V49_MAXIMUM_TLS_OPERATION_CIPHERTEXT_BYTES
        ):
            raise PhysicalTlsWebSocketV49ProtocolError(
                "raw socket send requires bounded exact non-empty ciphertext"
            )
        if (
            type(initial_suffix_offset) is not int
            or not 0 <= initial_suffix_offset < len(ciphertext)
            or type(deadline_ns) is not int
            or deadline_ns < 0
        ):
            raise PhysicalTlsWebSocketV49ProtocolError(
                "raw socket send offset or deadline is invalid"
            )
        for field, callback in (
            ("before_attempt", before_attempt),
            ("after_result", after_result),
        ):
            if callback is not None and not callable(callback):
                raise TypeError(f"{field} must be callable or None")
            if inspect.iscoroutinefunction(callback):
                raise TypeError(f"{field} must be synchronous")

        self._assert_socket(owned_socket)
        self._remaining_seconds(deadline_ns)
        digest = hashlib.sha256(ciphertext).hexdigest()
        offset = initial_suffix_offset
        attempt_count = 0
        would_block_count = 0
        positive_offsets: list[int] = []
        positive_counts: list[int] = []
        immutable_view = memoryview(ciphertext)
        try:
            while offset < len(ciphertext):
                self._remaining_seconds(deadline_ns)
                self._assert_socket(owned_socket)
                attempt_count += 1
                if attempt_count > V49_MAXIMUM_RAW_SEND_ATTEMPTS:
                    raise PhysicalTlsWebSocketV49ProtocolError(
                        "raw socket send exceeded its syscall-attempt bound"
                    )
                attempt = RawSocketSendAttemptV49(
                    _token=_RAW_SEND_TOKEN,
                    ciphertext_sha256=digest,
                    ciphertext_octets=len(ciphertext),
                    attempt_sequence=attempt_count,
                    suffix_offset=offset,
                    suffix_octets=len(ciphertext) - offset,
                )
                self._call_raw_send_callback(
                    before_attempt, attempt, field="before_attempt"
                )
                # Catch descriptor replacement performed by a callback before
                # entering the irrevocable syscall boundary.
                self._assert_socket(owned_socket)
                # A synchronous durable callback may itself take time.  Never
                # enter send() after the absolute BOOTTIME deadline it guarded.
                self._remaining_seconds(deadline_ns)
                suffix = immutable_view[offset:]
                try:
                    try:
                        count = owned_socket.send(suffix)
                    except BlockingIOError as exc:
                        ambiguous = getattr(exc, "characters_written", None)
                        if ambiguous not in {None, 0}:
                            raise PhysicalTlsWebSocketV49ProtocolError(
                                "BlockingIOError reported ambiguous positive progress"
                            ) from exc
                        result = RawSocketSendResultV49(
                            _token=_RAW_SEND_TOKEN,
                            attempt=attempt,
                            outcome=RawSocketSendOutcomeV49.WOULD_BLOCK,
                            kernel_accepted_octets=0,
                            next_suffix_offset=offset,
                            error_class=(
                                f"{type(exc).__module__}.{type(exc).__qualname__}"
                            ),
                            error_errno=exc.errno,
                        )
                        would_block_count += 1
                        self._call_raw_send_callback(
                            after_result, result, field="after_result"
                        )
                        await self._wait_socket_writable(
                            owned_socket, deadline_ns=deadline_ns
                        )
                        continue
                    except OSError as exc:
                        result = RawSocketSendResultV49(
                            _token=_RAW_SEND_TOKEN,
                            attempt=attempt,
                            outcome=RawSocketSendOutcomeV49.ERROR,
                            kernel_accepted_octets=None,
                            next_suffix_offset=offset,
                            error_class=(
                                f"{type(exc).__module__}.{type(exc).__qualname__}"
                            ),
                            error_errno=exc.errno,
                        )
                        self._call_raw_send_callback(
                            after_result, result, field="after_result"
                        )
                        raise
                finally:
                    suffix.release()

                if (
                    type(count) is not int
                    or count <= 0
                    or count > len(ciphertext) - offset
                ):
                    result = RawSocketSendResultV49(
                        _token=_RAW_SEND_TOKEN,
                        attempt=attempt,
                        outcome=RawSocketSendOutcomeV49.INVALID_COUNT,
                        kernel_accepted_octets=(count if type(count) is int else None),
                        next_suffix_offset=offset,
                        error_class=(
                            f"{type(count).__module__}.{type(count).__qualname__}"
                        ),
                        error_errno=None,
                    )
                    self._call_raw_send_callback(
                        after_result, result, field="after_result"
                    )
                    raise PhysicalTlsWebSocketV49ProtocolError(
                        "socket.send returned a zero or invalid byte count"
                    )

                prior_offset = offset
                offset += count
                positive_offsets.append(prior_offset)
                positive_counts.append(count)
                result = RawSocketSendResultV49(
                    _token=_RAW_SEND_TOKEN,
                    attempt=attempt,
                    outcome=RawSocketSendOutcomeV49.KERNEL_ACCEPTED,
                    kernel_accepted_octets=count,
                    next_suffix_offset=offset,
                    error_class=None,
                    error_errno=None,
                )
                self._call_raw_send_callback(after_result, result, field="after_result")
        finally:
            immutable_view.release()

        expected_offsets: list[int] = []
        expected_offset = initial_suffix_offset
        for count in positive_counts:
            expected_offsets.append(expected_offset)
            expected_offset += count
        if (
            not positive_counts
            or sum(positive_counts) != len(ciphertext) - initial_suffix_offset
            or positive_offsets != expected_offsets
            or attempt_count != len(positive_counts) + would_block_count
        ):
            raise PhysicalTlsWebSocketV49ProtocolError(
                "raw socket successful trace failed internal accounting"
            )
        return RawSocketSendTraceV49(
            _token=_RAW_SEND_TOKEN,
            ciphertext_sha256=digest,
            ciphertext_octets=len(ciphertext),
            initial_suffix_offset=initial_suffix_offset,
            final_suffix_offset=offset,
            positive_send_offsets=tuple(positive_offsets),
            positive_send_counts=tuple(positive_counts),
            would_block_count=would_block_count,
            attempt_count=attempt_count,
        )

    async def _flush_tls_output(
        self,
        owned_socket: socket.socket,
        *,
        deadline_ns: int,
        before_send_attempt: RawSocketSendBeforeAttemptV49 | None = None,
        after_send_result: RawSocketSendAfterResultV49 | None = None,
    ) -> None:
        if not self._actor_lock.locked():
            raise PhysicalTlsWebSocketV49StateError(
                "TLS output flush requires the driver actor lock"
            )
        while True:
            if not self._pending_tls_ciphertext:
                ciphertext = self._outgoing.read()
                if not ciphertext:
                    return
                if (
                    type(ciphertext) is not bytes
                    or len(ciphertext) > V49_MAXIMUM_TLS_OPERATION_CIPHERTEXT_BYTES
                ):
                    raise PhysicalTlsWebSocketV49ProtocolError(
                        "TLS output chunk exceeds its exact ciphertext bound"
                    )
                self._pending_tls_ciphertext = ciphertext
                self._pending_tls_ciphertext_offset = 0

            ciphertext = self._pending_tls_ciphertext
            starting_offset = self._pending_tls_ciphertext_offset
            expected_digest = hashlib.sha256(ciphertext).hexdigest()

            def retain_progress(
                result: RawSocketSendResultV49,
                *,
                _ciphertext: bytes = ciphertext,
                _expected_digest: str = expected_digest,
            ) -> Any:
                if (
                    result.attempt.ciphertext_sha256 != _expected_digest
                    or result.attempt.ciphertext_octets != len(_ciphertext)
                    or result.attempt.suffix_offset
                    != self._pending_tls_ciphertext_offset
                    or result.next_suffix_offset < self._pending_tls_ciphertext_offset
                ):
                    raise PhysicalTlsWebSocketV49ProtocolError(
                        "raw send callback result differs from retained TLS suffix"
                    )
                if result.outcome is RawSocketSendOutcomeV49.KERNEL_ACCEPTED:
                    self._pending_tls_ciphertext_offset = result.next_suffix_offset
                if after_send_result is None:
                    return None
                return after_send_result(result)

            trace = await self._send_raw_ciphertext(
                owned_socket,
                ciphertext,
                initial_suffix_offset=starting_offset,
                deadline_ns=deadline_ns,
                before_attempt=before_send_attempt,
                after_result=retain_progress,
            )
            if (
                trace.ciphertext_sha256 != expected_digest
                or trace.initial_suffix_offset != starting_offset
                or trace.final_suffix_offset != len(ciphertext)
                or self._pending_tls_ciphertext_offset != len(ciphertext)
            ):
                raise PhysicalTlsWebSocketV49ProtocolError(
                    "TLS ciphertext flush returned inconsistent local accounting"
                )
            self._pending_tls_ciphertext = b""
            self._pending_tls_ciphertext_offset = 0

    async def _receive_tls_ciphertext(
        self, owned_socket: socket.socket, *, deadline_ns: int
    ) -> None:
        loop = asyncio.get_running_loop()
        remaining_seconds = self._remaining_seconds(deadline_ns)
        ciphertext = await asyncio.wait_for(
            loop.sock_recv(owned_socket, V49_TLS_CIPHERTEXT_READ_BYTES),
            timeout=remaining_seconds,
        )
        if not ciphertext:
            self._incoming.write_eof()
            raise PhysicalTlsWebSocketV49TruncatedEof(
                "TCP EOF arrived before an authenticated TLS close"
            )
        self._operation_ciphertext_received += len(ciphertext)
        if (
            self._operation_ciphertext_received
            > V49_MAXIMUM_TLS_OPERATION_CIPHERTEXT_BYTES
        ):
            raise PhysicalTlsWebSocketV49ProtocolError(
                "TLS operation exceeded its ciphertext input bound"
            )
        self._incoming.write(ciphertext)

    async def _receive_tls_ciphertext_terminal_v49e(
        self, owned_socket: socket.socket, *, deadline_ns: int
    ) -> None:
        """Receive only after non-consuming readiness under the same deadline."""

        ciphertext = await self._recv_after_readiness_v49e(
            owned_socket,
            deadline_ns=deadline_ns,
        )
        if not ciphertext:
            self._incoming.write_eof()
            raise PhysicalTlsWebSocketV49TruncatedEof(
                "TCP EOF arrived before an authenticated TLS close"
            )
        self._operation_ciphertext_received += len(ciphertext)
        hasher = self._terminal_ingress_ciphertext_hasher_v49e
        if hasher is not None:
            hasher.update(ciphertext)
        if (
            self._operation_ciphertext_received
            > V49_MAXIMUM_TLS_OPERATION_CIPHERTEXT_BYTES
        ):
            raise PhysicalTlsWebSocketV49ProtocolError(
                "TLS operation exceeded its ciphertext input bound"
            )
        self._incoming.write(ciphertext)

    async def _recv_after_readiness_v49e(
        self,
        owned_socket: socket.socket,
        *,
        deadline_ns: int,
        shutdown_socket_v49e: bool = False,
    ) -> bytes:
        """Perform no recv until readable and BOOTTIME-current."""

        while True:
            await self._wait_socket_readable_v49e(
                owned_socket,
                deadline_ns=deadline_ns,
                shutdown_socket_v49e=shutdown_socket_v49e,
            )
            self._remaining_seconds(deadline_ns)
            try:
                ciphertext = owned_socket.recv(V49_TLS_CIPHERTEXT_READ_BYTES)
            except (BlockingIOError, InterruptedError):
                # Readiness may be stale.  No bytes or TLS/BIO state changed,
                # so waiting again under the same absolute deadline is safe.
                continue
            if type(ciphertext) is not bytes:
                raise PhysicalTlsWebSocketV49ProtocolError(
                    "nonblocking socket recv returned non-bytes ciphertext"
                )
            return ciphertext

    async def _drive_tls_handshake(
        self, owned_socket: socket.socket, *, deadline_ns: int
    ) -> None:
        while True:
            try:
                self._tls.do_handshake()
                await self._flush_tls_output(owned_socket, deadline_ns=deadline_ns)
                return
            except ssl.SSLWantReadError:
                await self._flush_tls_output(owned_socket, deadline_ns=deadline_ns)
                await self._receive_tls_ciphertext(
                    owned_socket, deadline_ns=deadline_ns
                )
            except ssl.SSLWantWriteError:
                await self._flush_tls_output(owned_socket, deadline_ns=deadline_ns)

    async def _write_plaintext(
        self,
        owned_socket: socket.socket,
        chunks: tuple[bytes, ...],
        *,
        deadline_ns: int,
        before_send_attempt: RawSocketSendBeforeAttemptV49 | None = None,
        after_send_result: RawSocketSendAfterResultV49 | None = None,
    ) -> int:
        accepted = 0
        for chunk in chunks:
            offset = 0
            while offset < len(chunk):
                try:
                    count = self._tls.write(chunk[offset:])
                    if type(count) is not int or count <= 0:
                        raise PhysicalTlsWebSocketV49ProtocolError(
                            "SSLObject.write returned an invalid byte count"
                        )
                    offset += count
                    accepted += count
                    await self._flush_tls_output(
                        owned_socket,
                        deadline_ns=deadline_ns,
                        before_send_attempt=before_send_attempt,
                        after_send_result=after_send_result,
                    )
                except ssl.SSLWantReadError:
                    await self._flush_tls_output(
                        owned_socket,
                        deadline_ns=deadline_ns,
                        before_send_attempt=before_send_attempt,
                        after_send_result=after_send_result,
                    )
                    await self._receive_tls_ciphertext(
                        owned_socket, deadline_ns=deadline_ns
                    )
                except ssl.SSLWantWriteError:
                    await self._flush_tls_output(
                        owned_socket,
                        deadline_ns=deadline_ns,
                        before_send_attempt=before_send_attempt,
                        after_send_result=after_send_result,
                    )
        await self._flush_tls_output(
            owned_socket,
            deadline_ns=deadline_ns,
            before_send_attempt=before_send_attempt,
            after_send_result=after_send_result,
        )
        return accepted

    async def _read_plaintext_chunk(
        self, owned_socket: socket.socket, *, deadline_ns: int
    ) -> bytes:
        while True:
            try:
                plaintext = self._tls.read(V49_TLS_PLAINTEXT_READ_BYTES)
                await self._flush_tls_output(owned_socket, deadline_ns=deadline_ns)
                if not plaintext:
                    raise PhysicalTlsWebSocketV49CleanTlsClose(
                        "TLS close_notify arrived while plaintext was required"
                    )
                return plaintext
            except ssl.SSLWantReadError:
                await self._flush_tls_output(owned_socket, deadline_ns=deadline_ns)
                await self._receive_tls_ciphertext(
                    owned_socket, deadline_ns=deadline_ns
                )
            except ssl.SSLWantWriteError:
                await self._flush_tls_output(owned_socket, deadline_ns=deadline_ns)
            except ssl.SSLZeroReturnError as exc:
                raise PhysicalTlsWebSocketV49CleanTlsClose(
                    "TLS close_notify arrived while plaintext was required"
                ) from exc
            except ssl.SSLEOFError as exc:
                raise PhysicalTlsWebSocketV49TruncatedEof(
                    "TLS stream ended without close_notify"
                ) from exc

    def _assert_no_post_handshake_tls_output_v49d(self) -> None:
        """Reject TLS output that isn't represented by the V4.9C actor FIFO.

        ``SSLObject.read`` may process TLS 1.3 post-handshake messages and
        generate response ciphertext.  The compatibility reader flushes such
        bytes directly.  The V4.9D causal reader must never do that: until a
        TLS-control actor vocabulary exists, the only safe behavior is to
        detect the output in owned memory and fault-latch before socket I/O.
        """

        if (
            self._outgoing.pending
            or self._pending_tls_ciphertext
            or self._pending_tls_ciphertext_offset != 0
            or self._active_prepared_wire_v49c is not None
            or self._active_prepared_tls_v49c is not None
            or self._active_prepared_tls_offset_v49c != 0
        ):
            raise PhysicalTlsWebSocketV49PostHandshakeOutputRequired(
                "post-handshake TLS output requires an actor-ordered extension"
            )

    async def _read_plaintext_chunk_v49d(
        self,
        owned_socket: socket.socket,
        *,
        deadline_ns: int,
        terminal_readiness_v49e: bool = False,
    ) -> bytes:
        """Read plaintext while permitting no implicit post-handshake write."""

        self._assert_no_post_handshake_tls_output_v49d()
        while True:
            try:
                plaintext = self._tls.read(V49_TLS_PLAINTEXT_READ_BYTES)
            except ssl.SSLWantReadError:
                self._assert_no_post_handshake_tls_output_v49d()
                if terminal_readiness_v49e:
                    await self._receive_tls_ciphertext_terminal_v49e(
                        owned_socket,
                        deadline_ns=deadline_ns,
                    )
                else:
                    await self._receive_tls_ciphertext(
                        owned_socket, deadline_ns=deadline_ns
                    )
                continue
            except ssl.SSLWantWriteError as exc:
                raise PhysicalTlsWebSocketV49PostHandshakeOutputRequired(
                    "SSLObject.read requested unjournaled post-handshake output"
                ) from exc
            except ssl.SSLZeroReturnError as exc:
                raise PhysicalTlsWebSocketV49CleanTlsClose(
                    "TLS close_notify arrived while plaintext was required"
                ) from exc
            except ssl.SSLEOFError as exc:
                raise PhysicalTlsWebSocketV49TruncatedEof(
                    "TLS stream ended without close_notify"
                ) from exc
            self._assert_no_post_handshake_tls_output_v49d()
            if not plaintext:
                raise PhysicalTlsWebSocketV49CleanTlsClose(
                    "TLS close_notify arrived while plaintext was required"
                )
            if type(plaintext) is not bytes:
                raise PhysicalTlsWebSocketV49ProtocolError(
                    "SSLObject.read returned non-bytes plaintext"
                )
            return plaintext

    def _validate_tls_result(self) -> tuple[str, str, str, str | None]:
        version = self._tls.version()
        cipher = self._tls.cipher()
        alpn = self._tls.selected_alpn_protocol()
        if (
            version != "TLSv1.3"
            or not isinstance(cipher, tuple)
            or len(cipher) != 3
            or not isinstance(cipher[0], str)
            or not cipher[0]
            or alpn is not None
            or self._tls.compression() is not None
            or self._tls.session_reused
        ):
            raise PhysicalTlsWebSocketV49ProtocolError(
                "negotiated TLS session differs from the exact V4.9A profile"
            )
        leaf = self._tls.getpeercert(binary_form=True)
        if type(leaf) is not bytes or not leaf:
            raise PhysicalTlsWebSocketV49ProtocolError(
                "verified TLS session lacks an exact leaf certificate"
            )
        certificate = x509.load_der_x509_certificate(leaf)
        spki = certificate.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return (
            version,
            cipher[0],
            hashlib.sha256(leaf).hexdigest(),
            hashlib.sha256(spki).hexdigest(),
        )

    @staticmethod
    def _validate_http_response(response_head: bytes, response: Response) -> None:
        if b"\x00" in response_head or b"\n" in response_head.replace(b"\r\n", b""):
            raise PhysicalTlsWebSocketV49ProtocolError(
                "HTTP upgrade response contains NUL or bare LF"
            )
        lines = response_head[:-4].split(b"\r\n")
        if not lines or len(lines) > 65:
            raise PhysicalTlsWebSocketV49ProtocolError(
                "HTTP upgrade response has an invalid header count"
            )
        if any(line[:1] in {b" ", b"\t"} for line in lines[1:]):
            raise PhysicalTlsWebSocketV49ProtocolError(
                "HTTP upgrade response contains obsolete line folding"
            )
        if response.status_code != 101 or response.body:
            raise PhysicalTlsWebSocketV49ProtocolError(
                "WebSocket upgrade didn't return an empty HTTP 101 response"
            )
        headers = response.headers
        for critical in (
            "Upgrade",
            "Connection",
            "Sec-WebSocket-Accept",
        ):
            if len(headers.get_all(critical)) != 1:
                raise PhysicalTlsWebSocketV49ProtocolError(
                    f"HTTP upgrade has duplicate or missing {critical}"
                )
        if headers.get_all("Content-Length") or headers.get_all("Transfer-Encoding"):
            raise PhysicalTlsWebSocketV49ProtocolError(
                "HTTP 101 response contains body-framing headers"
            )
        if headers.get_all("Sec-WebSocket-Extensions") or headers.get_all(
            "Sec-WebSocket-Protocol"
        ):
            raise PhysicalTlsWebSocketV49ProtocolError(
                "HTTP upgrade negotiated an unreviewed extension or subprotocol"
            )

    async def handshake(
        self, owned_socket: socket.socket
    ) -> DriverHandshakeEvidenceV49:
        """Complete TLS 1.3 and HTTP upgrade without parsing a coalesced frame."""

        self._assert_async_context()
        async with self._actor_lock:
            if self._state is not TlsWebSocketDriverStateV49.DORMANT:
                raise PhysicalTlsWebSocketV49StateError(
                    "TLS/WebSocket handshake is one-shot"
                )
            try:
                self._bind_socket(owned_socket)
                self.assert_current()
                deadline_ns = _boottime_ns() + V49_HANDSHAKE_TIMEOUT_SECONDS * 10**9
                self._operation_ciphertext_received = 0
                self._state = TlsWebSocketDriverStateV49.TLS_HANDSHAKING
                await self._drive_tls_handshake(owned_socket, deadline_ns=deadline_ns)
                self._assert_tls_profile()
                tls_version, tls_cipher, peer_cert_hash, peer_spki_hash = (
                    self._validate_tls_result()
                )
                accepted = await self._write_plaintext(
                    owned_socket,
                    (self._request_bytes,),
                    deadline_ns=deadline_ns,
                )
                if accepted != len(self._request_bytes):
                    raise PhysicalTlsWebSocketV49ProtocolError(
                        "TLS accepted an incomplete HTTP upgrade request"
                    )
                self._state = TlsWebSocketDriverStateV49.WS_RESPONSE_BUFFERING
                response_buffer = bytearray()
                split: tuple[bytes, bytes] | None = None
                while split is None:
                    response_buffer.extend(
                        await self._read_plaintext_chunk(
                            owned_socket, deadline_ns=deadline_ns
                        )
                    )
                    if len(response_buffer) > (
                        V49_MAXIMUM_HTTP_RESPONSE_HEAD_BYTES
                        + V49_MAXIMUM_POST_UPGRADE_PENDING_BYTES
                    ):
                        raise PhysicalTlsWebSocketV49ProtocolError(
                            "HTTP upgrade and coalesced suffix exceed their bounds"
                        )
                    split = split_http_upgrade_prefix_v49(bytes(response_buffer))
                    if (
                        split is None
                        and len(response_buffer) > V49_MAXIMUM_HTTP_RESPONSE_HEAD_BYTES
                    ):
                        raise PhysicalTlsWebSocketV49ProtocolError(
                            "HTTP upgrade response head exceeds its byte bound"
                        )
                response_head, post_upgrade = split
                if len(response_head) > V49_MAXIMUM_HTTP_RESPONSE_HEAD_BYTES:
                    raise PhysicalTlsWebSocketV49ProtocolError(
                        "HTTP upgrade response head exceeds its byte bound"
                    )
                if len(post_upgrade) > V49_MAXIMUM_POST_UPGRADE_PENDING_BYTES:
                    raise PhysicalTlsWebSocketV49ProtocolError(
                        "coalesced first WebSocket ingress exceeds its byte bound"
                    )

                # Critical ordering: feed only the HTTP response head.  Any
                # coalesced WebSocket suffix remains private, unparsed memory.
                self._protocol.receive_data(response_head)
                events = tuple(self._protocol.events_received())
                generated = tuple(self._protocol.data_to_send())
                if (
                    len(events) != 1
                    or type(events[0]) is not Response
                    or self._protocol.handshake_exc is not None
                    or self._protocol.state is not State.OPEN
                    or self._protocol.extensions
                    or self._protocol.subprotocol is not None
                    or generated
                ):
                    raise PhysicalTlsWebSocketV49ProtocolError(
                        "Sans-I/O HTTP upgrade transition differs from V4.9A"
                    )
                response = events[0]
                self._validate_http_response(response_head, response)
                nonce_hash = hashlib.sha256(secrets.token_bytes(32)).hexdigest()
                evidence = DriverHandshakeEvidenceV49(
                    _token=_EVIDENCE_TOKEN,
                    evidence_nonce_sha256=nonce_hash,
                    remote_address=_remote_address(owned_socket.getpeername()),
                    tls_version=tls_version,
                    tls_cipher=tls_cipher,
                    alpn_protocol=None,
                    peer_certificate_sha256=peer_cert_hash,
                    peer_spki_sha256=peer_spki_hash,
                    certificate_verified=True,
                    hostname_verified=True,
                    websocket_http_status=response.status_code,
                    websocket_accept_verified=True,
                    websocket_extensions=(),
                    handshake_request_sha256=hashlib.sha256(
                        self._request_bytes
                    ).hexdigest(),
                    handshake_response_sha256=hashlib.sha256(response_head).hexdigest(),
                    handshake_request_octets=len(self._request_bytes),
                    handshake_response_octets=len(response_head),
                    coalesced_post_upgrade_octets=len(post_upgrade),
                    trust_store_manifest_id=self._trust_store.manifest.manifest_id,
                    websockets_version=V49_WEBSOCKETS_VERSION,
                    openssl_version=ssl.OPENSSL_VERSION,
                )
                self._handshake_evidence = evidence
                self._handshake_evidence_values = tuple(
                    getattr(evidence, name)
                    for name in DriverHandshakeEvidenceV49.__dataclass_fields__
                )
                self._coalesced_tail = (post_upgrade,) if post_upgrade else ()
                self._state = TlsWebSocketDriverStateV49.WS_OPEN_UNBOUND
                return evidence
            except BaseException:
                self._state = TlsWebSocketDriverStateV49.FAULT_LATCHED
                raise

    def bind_handshake_evidence(
        self, evidence: DriverHandshakeEvidenceV49
    ) -> PendingRawIngressV49 | None:
        """Consume the exact evidence after its session/owner commit succeeds.

        The future runtime will keep this method private behind its atomic
        session commit.  V4.9A exposes it for deterministic engine tests while
        the live factory remains sealed.
        """

        self.assert_current()
        if (
            self._state is not TlsWebSocketDriverStateV49.WS_OPEN_UNBOUND
            or type(evidence) is not DriverHandshakeEvidenceV49
            or evidence is not self._handshake_evidence
            or self._handshake_evidence_bound
        ):
            raise PhysicalTlsWebSocketV49StateError(
                "handshake evidence isn't the exact unconsumed driver observation"
            )
        self._handshake_evidence_bound = True
        if self._coalesced_tail:
            pending = self._make_pending_raw(self._coalesced_tail)
            self._coalesced_tail = ()
            return pending
        self._state = TlsWebSocketDriverStateV49.WS_OPEN_BOUND
        return None

    def _make_pending_raw(self, chunks: tuple[bytes, ...]) -> PendingRawIngressV49:
        if self._pending_raw is not None:
            raise PhysicalTlsWebSocketV49StateError(
                "one decrypted ingress batch is already pending durability"
            )
        evidence = self._handshake_evidence
        assert evidence is not None
        self._ingress_sequence += 1
        pending = PendingRawIngressV49(
            _token=_RAW_TOKEN,
            driver_evidence_nonce_sha256=evidence.evidence_nonce_sha256,
            ingress_sequence=self._ingress_sequence,
            chunks=chunks,
        )
        self._pending_raw = pending
        self._state = TlsWebSocketDriverStateV49.RAW_INGRESS_PENDING
        return pending

    async def read_decrypted_ingress(
        self, owned_socket: socket.socket, *, timeout_seconds: int
    ) -> PendingRawIngressV49:
        """Read one bounded TLS-plaintext batch without parsing WebSocket bytes."""

        self._assert_async_context()
        timeout = canonical_safe_int(
            timeout_seconds, field="timeout_seconds", minimum=1, maximum=300
        )
        async with self._actor_lock:
            if getattr(self, "_durable_ingress_mode_v49d", False):
                raise PhysicalTlsWebSocketV49StateError(
                    "compatibility ingress cannot bypass active V4.9D ordering"
                )
            if self._state not in {
                TlsWebSocketDriverStateV49.WS_OPEN_BOUND,
                TlsWebSocketDriverStateV49.WS_CLOSING,
            }:
                raise PhysicalTlsWebSocketV49StateError(
                    "decrypted ingress read requires a bound open session"
                )
            try:
                self._assert_socket(owned_socket)
                self.assert_current()
                deadline_ns = _boottime_ns() + timeout * 10**9
                self._operation_ciphertext_received = 0
                first = await self._read_plaintext_chunk(
                    owned_socket, deadline_ns=deadline_ns
                )
                chunks = [first]
                total = len(first)
                # Drain plaintext already available in the SSLObject without
                # another kernel read.  Stop exactly at RawIngressCommitV4's
                # byte/chunk limits; unread plaintext remains in SSLObject for
                # the next durable batch rather than being dropped or merged.
                while (
                    self._tls.pending() > 0
                    and total < V49_MAXIMUM_POST_UPGRADE_PENDING_BYTES
                    and len(chunks) < V4_CONTROL_MAXIMUM_INGRESS_CHUNKS
                ):
                    remaining = V49_MAXIMUM_POST_UPGRADE_PENDING_BYTES - total
                    item = self._tls.read(min(V49_TLS_PLAINTEXT_READ_BYTES, remaining))
                    if not item:
                        break
                    chunks.append(item)
                    total += len(item)
                    if total > V49_MAXIMUM_POST_UPGRADE_PENDING_BYTES:
                        raise PhysicalTlsWebSocketV49ProtocolError(
                            "decrypted ingress batch exceeds its byte bound"
                        )
                await self._flush_tls_output(owned_socket, deadline_ns=deadline_ns)
                return self._make_pending_raw(tuple(chunks))
            except BaseException:
                self._state = TlsWebSocketDriverStateV49.FAULT_LATCHED
                raise

    def _begin_v49d_ingress_read(self) -> None:
        if self._state not in {
            TlsWebSocketDriverStateV49.WS_OPEN_BOUND,
            TlsWebSocketDriverStateV49.WS_CLOSING,
        }:
            raise PhysicalTlsWebSocketV49StateError(
                "V4.9D ingress read requires a bound session without pending RAW"
            )
        if (
            _next_server_parser_unit_octets_v49d(self._durable_ingress_buffer_v49d)
            is not None
        ):
            raise PhysicalTlsWebSocketV49StateError(
                "a complete durable parser unit must be consumed before more read"
            )
        self._durable_ingress_mode_v49d = True

    async def _read_decrypted_ingress_at_deadline_v49d(
        self,
        owned_socket: socket.socket,
        *,
        deadline_ns: int,
        terminal_readiness_v49e: bool = False,
    ) -> PendingRawIngressV49:
        if not self._actor_lock.locked():
            raise PhysicalTlsWebSocketV49StateError(
                "V4.9D ingress read requires the driver actor lock"
            )
        self._assert_socket(owned_socket)
        self.assert_current()
        self._assert_no_post_handshake_tls_output_v49d()
        self._operation_ciphertext_received = 0
        first = await self._read_plaintext_chunk_v49d(
            owned_socket,
            deadline_ns=deadline_ns,
            terminal_readiness_v49e=terminal_readiness_v49e,
        )
        chunks = [first]
        total = len(first)
        while (
            self._tls.pending() > 0
            and total < V49_MAXIMUM_POST_UPGRADE_PENDING_BYTES
            and len(chunks) < V4_CONTROL_MAXIMUM_INGRESS_CHUNKS
        ):
            remaining = V49_MAXIMUM_POST_UPGRADE_PENDING_BYTES - total
            try:
                item = self._tls.read(min(V49_TLS_PLAINTEXT_READ_BYTES, remaining))
            except ssl.SSLWantReadError:
                self._assert_no_post_handshake_tls_output_v49d()
                break
            except ssl.SSLWantWriteError as exc:
                raise PhysicalTlsWebSocketV49PostHandshakeOutputRequired(
                    "buffered TLS plaintext drain requested hidden output"
                ) from exc
            except ssl.SSLZeroReturnError as exc:
                raise PhysicalTlsWebSocketV49CleanTlsClose(
                    "TLS close_notify arrived during buffered plaintext drain"
                ) from exc
            except ssl.SSLEOFError as exc:
                raise PhysicalTlsWebSocketV49TruncatedEof(
                    "TLS stream ended during buffered plaintext drain"
                ) from exc
            self._assert_no_post_handshake_tls_output_v49d()
            if type(item) is not bytes or not item:
                raise PhysicalTlsWebSocketV49ProtocolError(
                    "TLS pending plaintext returned an invalid chunk"
                )
            chunks.append(item)
            total += len(item)
        self._assert_no_post_handshake_tls_output_v49d()
        return self._make_pending_raw(tuple(chunks))

    async def read_decrypted_ingress_v49d(
        self, owned_socket: socket.socket, *, timeout_seconds: int
    ) -> PendingRawIngressV49:
        """Read one RAW batch without any unjournaled post-handshake write.

        This compatibility entry point deliberately keeps its historical
        fail-latched timeout semantics.  Terminal-close waiting uses the
        absolute-deadline V4.9E entry point below.
        """

        self._assert_async_context()
        timeout = canonical_safe_int(
            timeout_seconds, field="timeout_seconds", minimum=1, maximum=300
        )
        async with self._actor_lock:
            self._begin_v49d_ingress_read()
            try:
                return await self._read_decrypted_ingress_at_deadline_v49d(
                    owned_socket,
                    deadline_ns=_boottime_ns() + timeout * 10**9,
                )
            except BaseException:
                self._state = TlsWebSocketDriverStateV49.FAULT_LATCHED
                raise

    async def read_terminal_close_ingress_v49e(
        self,
        owned_socket: socket.socket,
        *,
        deadline_ns: int,
    ) -> PendingRawIngressV49:
        """Read terminal ingress under one caller-frozen BOOTTIME deadline.

        A timeout is sealed either as no observation or as exact positive
        ciphertext progress.  Post-handshake output and every non-deadline
        protocol ambiguity remain fault-latched under distinct causes.
        """

        self._assert_async_context()
        try:
            exact_deadline_ns = self._bounded_absolute_deadline_v49e(deadline_ns)
        except TimeoutError as exc:
            raise self._deadline_expired_no_observation_v49e(
                operation="TERMINAL_CLOSE_INGRESS",
                deadline_ns=deadline_ns,
            ) from exc
        async with self._actor_lock:
            self._begin_v49d_ingress_read()
            state_before = self._state
            pure_no_observation_candidate = False
            ciphertext_hasher = hashlib.sha256()
            self._terminal_ingress_ciphertext_hasher_v49e = ciphertext_hasher
            try:
                self._assert_socket(owned_socket)
                self.assert_current()
                self._assert_no_post_handshake_tls_output_v49d()
                pure_no_observation_candidate = (
                    self._incoming.pending == 0 and self._tls.pending() == 0
                )
                return await self._read_decrypted_ingress_at_deadline_v49d(
                    owned_socket,
                    deadline_ns=exact_deadline_ns,
                    terminal_readiness_v49e=True,
                )
            except TimeoutError as exc:
                if self._operation_ciphertext_received > 0:
                    self._state = TlsWebSocketDriverStateV49.FAULT_LATCHED
                    raise self._deadline_expired_after_progress_v49e(
                        operation="TERMINAL_CLOSE_INGRESS",
                        deadline_ns=exact_deadline_ns,
                        ciphertext_octets_received=(
                            self._operation_ciphertext_received
                        ),
                        ciphertext_sha256=ciphertext_hasher.hexdigest(),
                    ) from exc
                if (
                    not pure_no_observation_candidate
                    or self._incoming.pending != 0
                    or self._tls.pending() != 0
                    or self._outgoing.pending != 0
                    or self._pending_raw is not None
                    or self._state is not state_before
                ):
                    self._state = TlsWebSocketDriverStateV49.FAULT_LATCHED
                    raise
                try:
                    self._assert_socket(owned_socket)
                    self.assert_current()
                    self._assert_no_post_handshake_tls_output_v49d()
                except BaseException:
                    self._state = TlsWebSocketDriverStateV49.FAULT_LATCHED
                    raise
                raise self._deadline_expired_no_observation_v49e(
                    operation="TERMINAL_CLOSE_INGRESS",
                    deadline_ns=exact_deadline_ns,
                ) from exc
            except BaseException:
                self._state = TlsWebSocketDriverStateV49.FAULT_LATCHED
                raise
            finally:
                self._terminal_ingress_ciphertext_hasher_v49e = None

    def adopt_durable_ingress_v49d(
        self, raw: RawIngressCommitV4
    ) -> DurableIngressAdoptionV49D:
        """Move exactly one pending RAW batch into the unparsed durable FIFO.

        The method performs no parser or network operation.  Content equality
        is necessary but isn't storage proof; the owner-bound runtime must call
        it only after receiving the exact store-minted RAW actor capability.
        """

        self._assert_context()
        pending = self._pending_raw
        if (
            self._state is not TlsWebSocketDriverStateV49.RAW_INGRESS_PENDING
            or pending is None
            or type(raw) is not RawIngressCommitV4
        ):
            raise PhysicalTlsWebSocketV49StateError(
                "durable adoption requires the exact pending RAW batch"
            )
        durable_chunks = tuple(
            base64.b64decode(value, validate=True)
            for value in raw.raw_ingress_chunks_base64
        )
        if (
            raw.transport_subscription_policy_id
            != self._policy.transport_subscription_policy_id
            or raw.ingress_sequence != pending.ingress_sequence
            or durable_chunks != pending.chunks
        ):
            self._state = TlsWebSocketDriverStateV49.FAULT_LATCHED
            raise PhysicalTlsWebSocketV49ProtocolError(
                "durable RAW authority or bytes differ from pending TLS plaintext"
            )
        combined = self._durable_ingress_buffer_v49d + b"".join(durable_chunks)
        if len(combined) > V49D_MAXIMUM_DURABLE_INGRESS_BUFFER_BYTES:
            self._state = TlsWebSocketDriverStateV49.FAULT_LATCHED
            raise PhysicalTlsWebSocketV49ProtocolError(
                "unparsed durable ingress exceeds its bounded FIFO"
            )
        self._pending_raw = None
        self._durable_ingress_buffer_v49d = combined
        self._durable_ingress_mode_v49d = True
        self._state = (
            TlsWebSocketDriverStateV49.WS_OPEN_BOUND
            if self._protocol.state is State.OPEN
            else TlsWebSocketDriverStateV49.WS_CLOSING
        )
        return DurableIngressAdoptionV49D(
            _token=_DURABLE_INGRESS_TOKEN,
            raw_ingress_commit_id=raw.raw_ingress_commit_id,
            ingress_sequence=raw.ingress_sequence,
            adopted_octets=sum(map(len, durable_chunks)),
            durable_buffer_octets=len(combined),
        )

    def _validate_text_utf8_v49d(self, frame: Frame) -> UnicodeDecodeError | None:
        """Apply the high-level assembler's UTF-8 rule frame by frame.

        ``websockets.protocol.Protocol`` deliberately exposes raw Text frame
        bytes; its asyncio message assembler normally performs UTF-8 decoding.
        V4.9D consumes Frames directly, so it retains an incremental strict
        decoder across Text continuations.  The decoder buffers at most one
        incomplete UTF-8 code point and never reassembles a message.
        """

        try:
            if frame.opcode is Opcode.TEXT:
                if frame.fin:
                    bytes(frame.data).decode("utf-8", errors="strict")
                else:
                    decoder = codecs.getincrementaldecoder("utf-8")(errors="strict")
                    decoder.decode(bytes(frame.data), final=False)
                    self._fragmented_text_decoder_v49d = decoder
            elif frame.opcode is Opcode.CONT:
                decoder = self._fragmented_text_decoder_v49d
                if decoder is not None:
                    decoder.decode(bytes(frame.data), final=frame.fin)
                    if frame.fin:
                        self._fragmented_text_decoder_v49d = None
            return None
        except UnicodeDecodeError as exc:
            self._fragmented_text_decoder_v49d = None
            self._protocol.fail(
                CloseCode.INVALID_DATA,
                f"{exc.reason} at position {exc.start}",
            )
            self._protocol.parser_exc = exc
            return exc

    def parse_next_durable_unit_v49d(self) -> ParsedDurableUnitV49D | None:
        """Parse at most one complete oldest durable frame/error prefix.

        ``None`` is a normal need-more-RAW outcome and doesn't touch parser
        state.  Once the parser is entered, every exceptional exit fault-
        latches the driver because Sans-I/O state cannot be replayed safely.
        """

        self._assert_context()
        if (
            self._state
            not in {
                TlsWebSocketDriverStateV49.WS_OPEN_BOUND,
                TlsWebSocketDriverStateV49.WS_CLOSING,
            }
            or self._pending_raw is not None
            or self._pending_protocol_output
            or self._active_prepared_wire_v49c is not None
            or self._active_prepared_tls_v49c is not None
            or self._protocol.parser_exc is not None
        ):
            raise PhysicalTlsWebSocketV49StateError(
                "durable parser requires an idle FIFO without pending output"
            )
        unit_octets = _next_server_parser_unit_octets_v49d(
            self._durable_ingress_buffer_v49d
        )
        if unit_octets is None:
            return None
        unit = self._durable_ingress_buffer_v49d[:unit_octets]
        try:
            self._protocol.receive_data(unit)
            raw_events = tuple(self._protocol.events_received())
            if len(raw_events) > 1 or any(
                type(event) is not Frame for event in raw_events
            ):
                raise PhysicalTlsWebSocketV49ProtocolError(
                    "one durable parser unit emitted an unsupported event set"
                )
            utf8_error = (
                None if not raw_events else self._validate_text_utf8_v49d(raw_events[0])
            )
            parser_error = self._protocol.parser_exc
            if parser_error is not None or (
                raw_events and raw_events[0].opcode is Opcode.CLOSE
            ):
                self._fragmented_text_decoder_v49d = None
            if parser_error is None and len(raw_events) != 1:
                raise PhysicalTlsWebSocketV49ProtocolError(
                    "one complete durable frame emitted no exact frame event"
                )
            frame_event = (
                None
                if not raw_events or utf8_error is not None
                else WebSocketFrameEventV49(
                    opcode=int(raw_events[0].opcode),
                    fin=raw_events[0].fin,
                    payload=bytes(raw_events[0].data),
                )
            )

            drained = tuple(self._protocol.data_to_send())
            send_eof = False
            if drained and drained[-1] == b"":
                send_eof = True
                drained = drained[:-1]
            if len(drained) > 1 or any(
                type(chunk) is not bytes or not chunk for chunk in drained
            ):
                raise PhysicalTlsWebSocketV49ProtocolError(
                    "one durable parser unit emitted multiple or invalid outputs"
                )
            if drained:
                output_opcode, output_payload = _decode_exact_client_frame(drained[0])
                if output_opcode not in {int(Opcode.PONG), int(Opcode.CLOSE)}:
                    raise PhysicalTlsWebSocketV49ProtocolError(
                        "durable parser output isn't one automatic Pong or Close"
                    )
                if output_opcode == int(Opcode.PONG) and (
                    frame_event is None
                    or frame_event.opcode != int(Opcode.PING)
                    or output_payload != frame_event.payload
                ):
                    raise PhysicalTlsWebSocketV49ProtocolError(
                        "automatic Pong differs from its exact Ping parser unit"
                    )

            self._parser_unit_sequence_v49d += 1
            remaining = self._durable_ingress_buffer_v49d[unit_octets:]
            result = ParsedDurableUnitV49D(
                _token=_DURABLE_PARSER_TOKEN,
                parser_unit_sequence=self._parser_unit_sequence_v49d,
                consumed_unit=unit,
                consumed_unit_sha256=hashlib.sha256(unit).hexdigest(),
                consumed_octets=len(unit),
                frame_event=frame_event,
                protocol_output_chunks=drained,
                protocol_output_chunks_sha256=tuple(
                    hashlib.sha256(chunk).hexdigest() for chunk in drained
                ),
                protocol_output_batch_sha256=(
                    None
                    if not drained
                    else _ordered_v49c_batch_sha256(_V49C_WIRE_BATCH_DOMAIN, drained)
                ),
                send_eof_after_output=send_eof,
                parser_exception_class=(
                    None
                    if parser_error is None
                    else (
                        f"{type(parser_error).__module__}."
                        f"{type(parser_error).__qualname__}"
                    )
                ),
                parser_exception_message=(
                    None if parser_error is None else str(parser_error)
                ),
                remaining_durable_octets=len(remaining),
            )
            self._durable_ingress_buffer_v49d = remaining
            self._pending_protocol_output = drained
            self._pending_send_eof = send_eof
            if drained:
                self._state = TlsWebSocketDriverStateV49.PROTOCOL_OUTPUT_PENDING
            elif self._protocol.state is State.OPEN:
                self._state = TlsWebSocketDriverStateV49.WS_OPEN_BOUND
            else:
                self._state = TlsWebSocketDriverStateV49.WS_CLOSING
            return result
        except BaseException:
            self._state = TlsWebSocketDriverStateV49.FAULT_LATCHED
            raise

    def parse_durable_ingress(
        self, raw: RawIngressCommitV4
    ) -> ParsedWebSocketIngressV49:
        """Feed exactly one already-durable raw batch to ``ClientProtocol``."""

        self._assert_context()
        pending = self._pending_raw
        if (
            self._state is not TlsWebSocketDriverStateV49.RAW_INGRESS_PENDING
            or pending is None
            or type(raw) is not RawIngressCommitV4
            or getattr(self, "_durable_ingress_mode_v49d", False)
        ):
            raise PhysicalTlsWebSocketV49StateError(
                "WebSocket parsing requires the exact pending durable ingress"
            )
        durable_chunks = tuple(
            base64.b64decode(value, validate=True)
            for value in raw.raw_ingress_chunks_base64
        )
        if (
            raw.ingress_sequence != pending.ingress_sequence
            or durable_chunks != pending.chunks
        ):
            self._state = TlsWebSocketDriverStateV49.FAULT_LATCHED
            raise PhysicalTlsWebSocketV49ProtocolError(
                "durable raw ingress differs from the pending TLS plaintext"
            )
        try:
            for chunk in pending.chunks:
                self._protocol.receive_data(chunk)
            raw_events = tuple(self._protocol.events_received())
            frame_events: list[WebSocketFrameEventV49] = []
            for event in raw_events:
                if type(event) is not Frame:
                    raise PhysicalTlsWebSocketV49ProtocolError(
                        "post-upgrade Sans-I/O emitted a non-frame event"
                    )
                frame_events.append(
                    WebSocketFrameEventV49(
                        opcode=int(event.opcode),
                        fin=event.fin,
                        payload=bytes(event.data),
                    )
                )
            drained = tuple(self._protocol.data_to_send())
            send_eof = False
            if drained and drained[-1] == b"":
                send_eof = True
                drained = drained[:-1]
            if any(type(chunk) is not bytes or not chunk for chunk in drained):
                raise PhysicalTlsWebSocketV49ProtocolError(
                    "Sans-I/O drain contains an invalid output chunk"
                )
            for chunk in drained:
                _decode_exact_client_frame(chunk)
            parser_error = self._protocol.parser_exc
            parser_class = (
                None
                if parser_error is None
                else f"{type(parser_error).__module__}.{type(parser_error).__qualname__}"
            )
            parser_message = None if parser_error is None else str(parser_error)
            result = ParsedWebSocketIngressV49(
                _token=_PARSE_TOKEN,
                raw_ingress_commit_id=raw.raw_ingress_commit_id,
                ingress_sequence=raw.ingress_sequence,
                frame_events=tuple(frame_events),
                protocol_output_chunks=drained,
                protocol_output_batch_sha256=(
                    None if not drained else _ordered_wire_batch_sha256(drained)
                ),
                send_eof_after_output=send_eof,
                parser_exception_class=parser_class,
                parser_exception_message=parser_message,
            )
            self._pending_raw = None
            if drained or send_eof:
                self._pending_protocol_output = drained
                self._pending_send_eof = send_eof
                self._state = TlsWebSocketDriverStateV49.PROTOCOL_OUTPUT_PENDING
            elif self._protocol.state is State.OPEN:
                self._state = TlsWebSocketDriverStateV49.WS_OPEN_BOUND
            else:
                self._state = TlsWebSocketDriverStateV49.WS_CLOSING
            return result
        except BaseException:
            self._state = TlsWebSocketDriverStateV49.FAULT_LATCHED
            raise

    async def send_exact_text_frame(
        self,
        owned_socket: socket.socket,
        payload: bytes,
        *,
        before_raw_send_attempt: RawSocketSendBeforeAttemptV49 | None = None,
        after_raw_send_result: RawSocketSendAfterResultV49 | None = None,
    ) -> None:
        """Implement the existing V4.4 logical subscription send boundary.

        This compatibility method validates the exact client Text frame
        generated by the retained protocol.  V4.9A does not claim the masked
        wire is durably prepared; migration to the control-style prepared-wire
        chain remains a release gate.
        """

        self._assert_async_context()
        if type(payload) is not bytes or not payload:
            raise PhysicalTlsWebSocketV49ProtocolError(
                "TEXT payload must be exact non-empty bytes"
            )
        async with self._actor_lock:
            if self._state is not TlsWebSocketDriverStateV49.WS_OPEN_BOUND or getattr(
                self, "_durable_ingress_buffer_v49d", b""
            ):
                raise PhysicalTlsWebSocketV49StateError(
                    "TEXT send requires an open session with no durable ingress/output"
                )
            try:
                self._assert_socket(owned_socket)
                self.assert_current()
                self._protocol.send_text(payload)
                chunks = tuple(self._protocol.data_to_send())
                if len(chunks) != 1 or not chunks[0]:
                    raise PhysicalTlsWebSocketV49ProtocolError(
                        "one logical TEXT send didn't produce one exact frame"
                    )
                opcode, decoded = _decode_exact_client_frame(chunks[0])
                if opcode != int(Opcode.TEXT) or decoded != payload:
                    raise PhysicalTlsWebSocketV49ProtocolError(
                        "Sans-I/O TEXT frame differs from the authorized payload"
                    )
                deadline_ns = (
                    _boottime_ns() + self._policy.send_deadline_seconds * 10**9
                )
                accepted = await self._write_plaintext(
                    owned_socket,
                    chunks,
                    deadline_ns=deadline_ns,
                    before_send_attempt=before_raw_send_attempt,
                    after_send_result=after_raw_send_result,
                )
                if accepted != len(chunks[0]):
                    raise PhysicalTlsWebSocketV49ProtocolError(
                        "TLS accepted an incomplete TEXT frame"
                    )
            except BaseException:
                self._state = TlsWebSocketDriverStateV49.FAULT_LATCHED
                raise

    @staticmethod
    def _assert_prepared_wire_integrity_v49c(
        prepared: PreparedWebSocketWireV49C,
    ) -> None:
        if type(prepared) is not PreparedWebSocketWireV49C:
            raise TypeError("prepared must be exact PreparedWebSocketWireV49C")
        chunks = prepared.ordered_wire_chunks
        if (
            type(prepared.outbound_sequence) is not int
            or prepared.outbound_sequence < 1
            or type(prepared.logical_opcode) is not int
            or prepared.logical_opcode
            not in {int(Opcode.TEXT), int(Opcode.PONG), int(Opcode.CLOSE)}
            or type(prepared.logical_payload_octets) is not int
            or not 0
            <= prepared.logical_payload_octets
            <= V49_MAXIMUM_WEBSOCKET_MESSAGE_BYTES
            or type(chunks) is not tuple
            or not chunks
            or len(chunks) > V49C_MAXIMUM_STAGED_WIRE_CHUNKS
            or any(type(chunk) is not bytes or not chunk for chunk in chunks)
            or sum(map(len, chunks)) != prepared.wire_octets
            or prepared.wire_octets > V49C_MAXIMUM_STAGED_WIRE_OCTETS
            or tuple(hashlib.sha256(chunk).hexdigest() for chunk in chunks)
            != prepared.ordered_wire_chunks_sha256
            or _ordered_v49c_batch_sha256(_V49C_WIRE_BATCH_DOMAIN, chunks)
            != prepared.wire_batch_sha256
        ):
            raise PhysicalTlsWebSocketV49ProtocolError(
                "prepared WebSocket wire differs from its exact hashes or bounds"
            )
        if len(chunks) != 1:
            raise PhysicalTlsWebSocketV49ProtocolError(
                "staged application TEXT requires one exact WebSocket frame"
            )
        opcode, payload = _decode_exact_client_frame(chunks[0])
        if (
            opcode != prepared.logical_opcode
            or len(payload) != prepared.logical_payload_octets
            or hashlib.sha256(payload).hexdigest() != prepared.logical_payload_sha256
        ):
            raise PhysicalTlsWebSocketV49ProtocolError(
                "prepared WebSocket wire differs from its logical payload"
            )

    @staticmethod
    def _assert_prepared_tls_integrity_v49c(
        prepared: PreparedTlsCiphertextV49C,
    ) -> None:
        if type(prepared) is not PreparedTlsCiphertextV49C:
            raise TypeError("prepared must be exact PreparedTlsCiphertextV49C")
        wire = prepared.prepared_wire
        ExactTlsWebSocketDriverV49._assert_prepared_wire_integrity_v49c(wire)
        chunks = prepared.ordered_ciphertext_chunks
        if (
            type(prepared.outbound_sequence) is not int
            or prepared.outbound_sequence < 1
            or type(prepared.plaintext_octets) is not int
            or prepared.plaintext_octets < 1
            or type(prepared.ciphertext_octets) is not int
            or prepared.ciphertext_octets < 1
            or type(chunks) is not tuple
            or not chunks
            or len(chunks) > V49C_MAXIMUM_STAGED_TLS_CIPHERTEXT_CHUNKS
            or any(type(chunk) is not bytes or not chunk for chunk in chunks)
            or sum(map(len, chunks)) != prepared.ciphertext_octets
            or prepared.ciphertext_octets > V49_MAXIMUM_TLS_OPERATION_CIPHERTEXT_BYTES
            or tuple(hashlib.sha256(chunk).hexdigest() for chunk in chunks)
            != prepared.ordered_ciphertext_chunks_sha256
            or _ordered_v49c_batch_sha256(_V49C_CIPHERTEXT_BATCH_DOMAIN, chunks)
            != prepared.ciphertext_batch_sha256
            or prepared.outbound_sequence != wire.outbound_sequence
            or prepared.plaintext_batch_sha256 != wire.wire_batch_sha256
            or prepared.plaintext_octets != wire.wire_octets
        ):
            raise PhysicalTlsWebSocketV49ProtocolError(
                "prepared TLS ciphertext differs from its exact plaintext link, "
                "hashes, or bounds"
            )

    async def prepare_exact_text_wire_v49c(
        self, payload: bytes
    ) -> PreparedWebSocketWireV49C:
        """Retain one exact client Text frame without touching the socket.

        This is the first V4.9C staged boundary.  The returned token-only
        artifact can be journaled before TLS accepts its plaintext.  Preparing
        another frame while this FIFO head is unresolved is forbidden.
        """

        self._assert_async_context()
        if (
            type(payload) is not bytes
            or not payload
            or len(payload) > V49C_MAXIMUM_STAGED_WIRE_OCTETS
        ):
            raise PhysicalTlsWebSocketV49ProtocolError(
                "staged TEXT payload must be bounded exact non-empty bytes"
            )
        async with self._actor_lock:
            if (
                self._state is not TlsWebSocketDriverStateV49.WS_OPEN_BOUND
                or getattr(self, "_durable_ingress_buffer_v49d", b"")
                or self._active_prepared_wire_v49c is not None
                or self._active_prepared_tls_v49c is not None
                or self._pending_tls_ciphertext
                or self._pending_tls_ciphertext_offset != 0
                or self._outgoing.pending
            ):
                raise PhysicalTlsWebSocketV49StateError(
                    "staged TEXT preparation requires one idle open FIFO"
                )
            try:
                self._protocol.send_text(payload)
                chunks = tuple(self._protocol.data_to_send())
                if (
                    len(chunks) != 1
                    or type(chunks[0]) is not bytes
                    or not chunks[0]
                    or len(chunks[0]) > V49C_MAXIMUM_STAGED_WIRE_OCTETS
                ):
                    raise PhysicalTlsWebSocketV49ProtocolError(
                        "one staged TEXT intent didn't produce one bounded frame"
                    )
                opcode, decoded = _decode_exact_client_frame(chunks[0])
                if opcode != int(Opcode.TEXT) or decoded != payload:
                    raise PhysicalTlsWebSocketV49ProtocolError(
                        "staged Sans-I/O TEXT wire differs from the exact payload"
                    )
                sequence = self._staged_outbound_sequence_v49c + 1
                prepared = PreparedWebSocketWireV49C(
                    _token=_STAGED_SEND_TOKEN,
                    outbound_sequence=sequence,
                    logical_opcode=opcode,
                    logical_payload_sha256=hashlib.sha256(payload).hexdigest(),
                    logical_payload_octets=len(payload),
                    ordered_wire_chunks=chunks,
                    ordered_wire_chunks_sha256=tuple(
                        hashlib.sha256(chunk).hexdigest() for chunk in chunks
                    ),
                    wire_batch_sha256=_ordered_v49c_batch_sha256(
                        _V49C_WIRE_BATCH_DOMAIN, chunks
                    ),
                    wire_octets=sum(map(len, chunks)),
                )
                self._assert_prepared_wire_integrity_v49c(prepared)
                self._staged_outbound_sequence_v49c = sequence
                self._active_prepared_wire_v49c = prepared
                self._active_prepared_wire_was_protocol_output_v49c = False
                self._state = TlsWebSocketDriverStateV49.OUTBOUND_WIRE_PREPARED_V49C
                return prepared
            except BaseException:
                # send_text mutates the Sans-I/O protocol before data_to_send
                # exposes its wire.  Any failure after entering that boundary
                # is non-recoverable and the logical intent must not be replayed.
                self._state = TlsWebSocketDriverStateV49.FAULT_LATCHED
                raise

    async def prepare_local_websocket_close_wire_v49e(
        self,
        *,
        deadline_ns: int,
    ) -> PreparedWebSocketWireV49C:
        """Retain the one admitted locally initiated WebSocket Close frame.

        V4.9E intentionally exposes no caller-selected close code or reason at
        this physical boundary.  The exact frame is always RFC 6455 normal
        closure (1000) with an empty reason.  Preparing it advances only the
        retained Sans-I/O protocol and the staged FIFO; it performs no TLS or
        socket operation.
        """

        self._assert_async_context()
        try:
            exact_deadline_ns = self._bounded_absolute_deadline_v49e(deadline_ns)
        except TimeoutError as exc:
            raise self._deadline_expired_no_observation_v49e(
                operation="LOCAL_WEBSOCKET_CLOSE_PREPARATION",
                deadline_ns=deadline_ns,
            ) from exc
        async with self._actor_lock:
            if self._state is not TlsWebSocketDriverStateV49.WS_OPEN_BOUND:
                raise PhysicalTlsWebSocketV49StateError(
                    "local WebSocket Close requires one idle open session"
                )
            self._assert_tls_control_fifo_idle_v49e()
            if self._outgoing.pending:
                raise PhysicalTlsWebSocketV49StateError(
                    "local WebSocket Close requires no unresolved TLS output"
                )
            try:
                self._remaining_seconds(exact_deadline_ns)
            except TimeoutError as exc:
                raise self._deadline_expired_no_observation_v49e(
                    operation="LOCAL_WEBSOCKET_CLOSE_PREPARATION",
                    deadline_ns=exact_deadline_ns,
                ) from exc
            try:
                self._protocol.send_close(CloseCode.NORMAL_CLOSURE, "")
                chunks = tuple(self._protocol.data_to_send())
                if (
                    len(chunks) != 1
                    or type(chunks[0]) is not bytes
                    or not chunks[0]
                    or len(chunks[0]) > V49C_MAXIMUM_STAGED_WIRE_OCTETS
                ):
                    raise PhysicalTlsWebSocketV49ProtocolError(
                        "local normal Close didn't produce one bounded frame"
                    )
                opcode, payload = _decode_exact_client_frame(chunks[0])
                expected_payload = int(CloseCode.NORMAL_CLOSURE).to_bytes(2, "big")
                if opcode != int(Opcode.CLOSE) or payload != expected_payload:
                    raise PhysicalTlsWebSocketV49ProtocolError(
                        "local Close differs from fixed normal closure with empty reason"
                    )
                sequence = self._staged_outbound_sequence_v49c + 1
                prepared = PreparedWebSocketWireV49C(
                    _token=_STAGED_SEND_TOKEN,
                    outbound_sequence=sequence,
                    logical_opcode=opcode,
                    logical_payload_sha256=hashlib.sha256(payload).hexdigest(),
                    logical_payload_octets=len(payload),
                    ordered_wire_chunks=chunks,
                    ordered_wire_chunks_sha256=tuple(
                        hashlib.sha256(chunk).hexdigest() for chunk in chunks
                    ),
                    wire_batch_sha256=_ordered_v49c_batch_sha256(
                        _V49C_WIRE_BATCH_DOMAIN, chunks
                    ),
                    wire_octets=sum(map(len, chunks)),
                )
                self._assert_prepared_wire_integrity_v49c(prepared)
                self._staged_outbound_sequence_v49c = sequence
                self._active_prepared_wire_v49c = prepared
                self._active_prepared_wire_was_protocol_output_v49c = False
                self._state = TlsWebSocketDriverStateV49.OUTBOUND_WIRE_PREPARED_V49C
                return prepared
            except BaseException:
                # send_close mutates the retained protocol.  Any uncertainty
                # after that boundary makes this session unreplayable.
                self._state = TlsWebSocketDriverStateV49.FAULT_LATCHED
                raise

    async def prepare_pending_protocol_output_wire_v49c(
        self, ordered_chunks: tuple[bytes, ...]
    ) -> PreparedWebSocketWireV49C:
        """Retain one exact automatic Pong/Close wire without socket I/O.

        The V4.9C actor records automatic output in the same FIFO as
        application Text frames.  This bounded seam accepts the oldest
        complete pending Sans-I/O control frame.  A coalesced drain is advanced
        one chunk at a time so the parser's exact FIFO order remains visible.
        """

        self._assert_async_context()
        async with self._actor_lock:
            if (
                self._state is not TlsWebSocketDriverStateV49.PROTOCOL_OUTPUT_PENDING
                or type(ordered_chunks) is not tuple
                or len(ordered_chunks) != 1
                or not self._pending_protocol_output
                or ordered_chunks[0] != self._pending_protocol_output[0]
                or self._active_prepared_wire_v49c is not None
                or self._active_prepared_tls_v49c is not None
                or self._pending_tls_ciphertext
                or self._pending_tls_ciphertext_offset != 0
                or self._outgoing.pending
            ):
                raise PhysicalTlsWebSocketV49StateError(
                    "automatic preparation requires one exact pending control frame"
                )
            try:
                chunk = ordered_chunks[0]
                if (
                    type(chunk) is not bytes
                    or not chunk
                    or len(chunk) > V49C_MAXIMUM_STAGED_WIRE_OCTETS
                ):
                    raise PhysicalTlsWebSocketV49ProtocolError(
                        "pending automatic wire is outside the V4.9C bound"
                    )
                opcode, payload = _decode_exact_client_frame(chunk)
                if opcode not in {int(Opcode.PONG), int(Opcode.CLOSE)}:
                    raise PhysicalTlsWebSocketV49ProtocolError(
                        "pending automatic wire isn't a Pong or Close frame"
                    )
                sequence = self._staged_outbound_sequence_v49c + 1
                prepared = PreparedWebSocketWireV49C(
                    _token=_STAGED_SEND_TOKEN,
                    outbound_sequence=sequence,
                    logical_opcode=opcode,
                    logical_payload_sha256=hashlib.sha256(payload).hexdigest(),
                    logical_payload_octets=len(payload),
                    ordered_wire_chunks=ordered_chunks,
                    ordered_wire_chunks_sha256=(hashlib.sha256(chunk).hexdigest(),),
                    wire_batch_sha256=_ordered_v49c_batch_sha256(
                        _V49C_WIRE_BATCH_DOMAIN, ordered_chunks
                    ),
                    wire_octets=len(chunk),
                )
                self._assert_prepared_wire_integrity_v49c(prepared)
                self._staged_outbound_sequence_v49c = sequence
                self._active_prepared_wire_v49c = prepared
                self._active_prepared_wire_was_protocol_output_v49c = True
                self._state = TlsWebSocketDriverStateV49.OUTBOUND_WIRE_PREPARED_V49C
                return prepared
            except BaseException:
                self._state = TlsWebSocketDriverStateV49.FAULT_LATCHED
                raise

    async def prepare_tls_ciphertext_v49c(
        self,
        prepared_wire: PreparedWebSocketWireV49C,
        *,
        deadline_ns: int | None = None,
    ) -> PreparedTlsCiphertextV49C:
        """Retain exact TLS ciphertext for the active wire without socket I/O.

        Only ``SSLObject.write`` and the driver's outgoing ``MemoryBIO`` are
        touched.  A TLS state that asks for network input/output during this
        bounded preparation fails closed instead of hiding a socket effect.
        """

        self._assert_async_context()
        exact_deadline_ns: int | None = None
        if deadline_ns is not None:
            try:
                exact_deadline_ns = self._bounded_absolute_deadline_v49e(deadline_ns)
            except TimeoutError as exc:
                raise self._deadline_expired_no_observation_v49e(
                    operation="LOCAL_WEBSOCKET_CLOSE_TLS_PREPARATION",
                    deadline_ns=deadline_ns,
                ) from exc
        async with self._actor_lock:
            if (
                self._state
                is not TlsWebSocketDriverStateV49.OUTBOUND_WIRE_PREPARED_V49C
                or prepared_wire is not self._active_prepared_wire_v49c
                or self._active_prepared_tls_v49c is not None
            ):
                raise PhysicalTlsWebSocketV49StateError(
                    "TLS preparation requires the exact active FIFO wire object"
                )
            mutation_started = False
            try:
                self._assert_prepared_wire_integrity_v49c(prepared_wire)
                if (
                    self._pending_tls_ciphertext
                    or self._pending_tls_ciphertext_offset != 0
                    or self._outgoing.pending
                ):
                    raise PhysicalTlsWebSocketV49StateError(
                        "TLS preparation found unresolved compatibility ciphertext"
                    )
                accepted = 0
                for chunk in prepared_wire.ordered_wire_chunks:
                    offset = 0
                    while offset < len(chunk):
                        if exact_deadline_ns is not None:
                            try:
                                self._remaining_seconds(exact_deadline_ns)
                            except TimeoutError as exc:
                                if mutation_started:
                                    raise
                                raise self._deadline_expired_no_observation_v49e(
                                    operation=("LOCAL_WEBSOCKET_CLOSE_TLS_PREPARATION"),
                                    deadline_ns=exact_deadline_ns,
                                ) from exc
                        try:
                            count = self._tls.write(chunk[offset:])
                        except (ssl.SSLWantReadError, ssl.SSLWantWriteError) as exc:
                            raise PhysicalTlsWebSocketV49ProtocolError(
                                "staged TLS preparation requires network progress"
                            ) from exc
                        if (
                            type(count) is not int
                            or count <= 0
                            or count > len(chunk) - offset
                        ):
                            raise PhysicalTlsWebSocketV49ProtocolError(
                                "SSLObject.write returned an invalid staged count"
                            )
                        offset += count
                        accepted += count
                        mutation_started = True
                if accepted != prepared_wire.wire_octets:
                    raise PhysicalTlsWebSocketV49ProtocolError(
                        "TLS didn't accept the complete staged WebSocket wire"
                    )

                ciphertext_chunks: list[bytes] = []
                ciphertext_octets = 0
                while self._outgoing.pending:
                    chunk = self._outgoing.read()
                    if type(chunk) is not bytes or not chunk:
                        raise PhysicalTlsWebSocketV49ProtocolError(
                            "outgoing MemoryBIO returned an invalid staged chunk"
                        )
                    ciphertext_chunks.append(chunk)
                    ciphertext_octets += len(chunk)
                    if (
                        len(ciphertext_chunks)
                        > V49C_MAXIMUM_STAGED_TLS_CIPHERTEXT_CHUNKS
                        or ciphertext_octets
                        > V49_MAXIMUM_TLS_OPERATION_CIPHERTEXT_BYTES
                    ):
                        raise PhysicalTlsWebSocketV49ProtocolError(
                            "staged TLS ciphertext exceeds its actor bounds"
                        )
                chunks = tuple(ciphertext_chunks)
                if not chunks:
                    raise PhysicalTlsWebSocketV49ProtocolError(
                        "TLS accepted staged plaintext without producing ciphertext"
                    )
                prepared = PreparedTlsCiphertextV49C(
                    _token=_STAGED_SEND_TOKEN,
                    outbound_sequence=prepared_wire.outbound_sequence,
                    prepared_wire=prepared_wire,
                    plaintext_batch_sha256=prepared_wire.wire_batch_sha256,
                    plaintext_octets=prepared_wire.wire_octets,
                    ordered_ciphertext_chunks=chunks,
                    ordered_ciphertext_chunks_sha256=tuple(
                        hashlib.sha256(chunk).hexdigest() for chunk in chunks
                    ),
                    ciphertext_batch_sha256=_ordered_v49c_batch_sha256(
                        _V49C_CIPHERTEXT_BATCH_DOMAIN, chunks
                    ),
                    ciphertext_octets=ciphertext_octets,
                )
                self._assert_prepared_tls_integrity_v49c(prepared)
                self._active_prepared_tls_v49c = prepared
                self._active_prepared_tls_offset_v49c = 0
                self._state = TlsWebSocketDriverStateV49.TLS_CIPHERTEXT_PREPARED_V49C
                return prepared
            except PhysicalTlsWebSocketV49DeadlineExpiredNoObservation:
                if mutation_started:
                    self._state = TlsWebSocketDriverStateV49.FAULT_LATCHED
                raise
            except BaseException:
                # SSLObject.write is an irreversible protocol-state transition,
                # even though it performs no socket syscall.
                self._state = TlsWebSocketDriverStateV49.FAULT_LATCHED
                raise

    async def send_prepared_tls_ciphertext_once_v49c(
        self,
        exact_ciphertext_slice: bytes,
        *,
        owned_socket: socket.socket,
        prepared: PreparedTlsCiphertextV49C,
        deadline_ns: int,
    ) -> int:
        """Return the first exact positive local ``socket.send`` count.

        ``BlockingIOError`` doesn't claim progress: the exact same suffix is
        retried after writable readiness under one absolute CLOCK_BOOTTIME
        deadline.  Every other exceptional exit fault-latches the artifact.
        A positive count advances the retained suffix exactly once and returns
        immediately; it is local kernel acceptance, never peer receipt.
        """

        self._assert_async_context()
        async with self._actor_lock:
            try:
                if (
                    self._state
                    is not TlsWebSocketDriverStateV49.TLS_CIPHERTEXT_PREPARED_V49C
                    or prepared is not self._active_prepared_tls_v49c
                    or prepared.prepared_wire is not self._active_prepared_wire_v49c
                ):
                    raise PhysicalTlsWebSocketV49StateError(
                        "send requires the exact active staged TLS artifact"
                    )
                self._assert_prepared_tls_integrity_v49c(prepared)
                offset = self._active_prepared_tls_offset_v49c
                ciphertext = prepared.exact_ciphertext
                if (
                    type(exact_ciphertext_slice) is not bytes
                    or not exact_ciphertext_slice
                    or len(exact_ciphertext_slice) > len(ciphertext) - offset
                    or exact_ciphertext_slice
                    != ciphertext[offset : offset + len(exact_ciphertext_slice)]
                ):
                    raise PhysicalTlsWebSocketV49ProtocolError(
                        "send slice isn't the exact retained ciphertext suffix prefix"
                    )
                if type(deadline_ns) is not int or deadline_ns < 0:
                    raise PhysicalTlsWebSocketV49ProtocolError(
                        "staged send deadline must be an absolute integer"
                    )
                terminal_close_send = prepared.prepared_wire.logical_opcode == 0x8
                close_send_kind = (
                    "AUTOMATIC_WEBSOCKET_CLOSE"
                    if (
                        terminal_close_send
                        and self._active_prepared_wire_was_protocol_output_v49c
                    )
                    else "LOCAL_WEBSOCKET_CLOSE"
                )
                self._assert_socket(owned_socket)
                try:
                    self._remaining_seconds(deadline_ns)
                except TimeoutError as exc:
                    if terminal_close_send:
                        raise self._deadline_expired_no_observation_v49e(
                            operation="WEBSOCKET_CLOSE_SEND_BEFORE_SYSCALL",
                            deadline_ns=deadline_ns,
                        ) from exc
                    raise

                attempts = 0
                would_block_count = 0
                while True:
                    attempts += 1
                    if attempts > V49_MAXIMUM_RAW_SEND_ATTEMPTS:
                        raise PhysicalTlsWebSocketV49ProtocolError(
                            "staged send exceeded its syscall-attempt bound"
                        )
                    self._assert_socket(owned_socket)
                    try:
                        self._remaining_seconds(deadline_ns)
                    except TimeoutError as exc:
                        if terminal_close_send and would_block_count:
                            raise self._send_deadline_no_kernel_acceptance_v49e(
                                send_kind=close_send_kind,
                                transport_sequence=prepared.outbound_sequence,
                                ciphertext_batch_sha256=(
                                    prepared.ciphertext_batch_sha256
                                ),
                                ciphertext_octets=prepared.ciphertext_octets,
                                ciphertext_start_octet=offset,
                                exact_slice=exact_ciphertext_slice,
                                deadline_ns=deadline_ns,
                                would_block_count=would_block_count,
                            ) from exc
                        if terminal_close_send:
                            raise self._deadline_expired_no_observation_v49e(
                                operation="WEBSOCKET_CLOSE_SEND_BEFORE_SYSCALL",
                                deadline_ns=deadline_ns,
                            ) from exc
                        raise
                    view = memoryview(exact_ciphertext_slice)
                    try:
                        try:
                            count = owned_socket.send(view)
                        except BlockingIOError as exc:
                            ambiguous = getattr(exc, "characters_written", None)
                            if ambiguous not in {None, 0}:
                                raise PhysicalTlsWebSocketV49ProtocolError(
                                    "would-block reported ambiguous positive progress"
                                ) from exc
                            would_block_count += 1
                            try:
                                await self._wait_socket_writable(
                                    owned_socket, deadline_ns=deadline_ns
                                )
                            except TimeoutError as timeout_exc:
                                if terminal_close_send:
                                    raise self._send_deadline_no_kernel_acceptance_v49e(
                                        send_kind=close_send_kind,
                                        transport_sequence=(prepared.outbound_sequence),
                                        ciphertext_batch_sha256=(
                                            prepared.ciphertext_batch_sha256
                                        ),
                                        ciphertext_octets=prepared.ciphertext_octets,
                                        ciphertext_start_octet=offset,
                                        exact_slice=exact_ciphertext_slice,
                                        deadline_ns=deadline_ns,
                                        would_block_count=would_block_count,
                                    ) from timeout_exc
                                raise
                            continue
                    finally:
                        view.release()
                    if (
                        type(count) is not int
                        or count <= 0
                        or count > len(exact_ciphertext_slice)
                    ):
                        raise PhysicalTlsWebSocketV49ProtocolError(
                            "socket.send returned an invalid staged byte count"
                        )

                    next_offset = offset + count
                    self._active_prepared_tls_offset_v49c = next_offset
                    if next_offset == prepared.ciphertext_octets:
                        was_protocol_output = (
                            self._active_prepared_wire_was_protocol_output_v49c
                        )
                        next_state = (
                            TlsWebSocketDriverStateV49.WS_OPEN_BOUND
                            if self._protocol.state is State.OPEN
                            else TlsWebSocketDriverStateV49.WS_CLOSING
                        )
                        self._active_prepared_tls_v49c = None
                        self._active_prepared_wire_v49c = None
                        self._active_prepared_wire_was_protocol_output_v49c = False
                        self._active_prepared_tls_offset_v49c = 0
                        if was_protocol_output:
                            pending = self._pending_protocol_output
                            wire_chunks = prepared.prepared_wire.ordered_wire_chunks
                            if not pending or pending[0] != wire_chunks[0]:
                                raise PhysicalTlsWebSocketV49ProtocolError(
                                    "automatic FIFO changed during staged send"
                                )
                            self._pending_protocol_output = pending[1:]
                            if self._pending_protocol_output:
                                next_state = (
                                    TlsWebSocketDriverStateV49.PROTOCOL_OUTPUT_PENDING
                                )
                            elif self._pending_send_eof:
                                self._pending_send_eof = False
                                next_state = TlsWebSocketDriverStateV49.WS_CLOSING
                        self._state = next_state
                    return count
            except (
                PhysicalTlsWebSocketV49DeadlineExpiredNoObservation,
                PhysicalTlsWebSocketV49SendDeadlineExpiredNoKernelAcceptance,
            ):
                raise
            except BaseException:
                self._state = TlsWebSocketDriverStateV49.FAULT_LATCHED
                raise

    @staticmethod
    def _assert_prepared_tls_control_integrity_v49e(
        prepared: PreparedTlsControlCiphertextV49E,
    ) -> None:
        """Validate every retained V4.9E byte, link, type, and bound."""

        if type(prepared) is not PreparedTlsControlCiphertextV49E:
            raise TypeError("prepared must be exact PreparedTlsControlCiphertextV49E")
        chunks = prepared.ordered_ciphertext_chunks
        if (
            type(prepared.control_sequence) is not int
            or prepared.control_sequence < 1
            or type(prepared.control_kind) is not TlsControlOutputKindV49E
            or type(prepared.driver_evidence_nonce_sha256) is not str
            or len(prepared.driver_evidence_nonce_sha256) != 64
            or any(
                char not in "0123456789abcdef"
                for char in prepared.driver_evidence_nonce_sha256
            )
            or type(chunks) is not tuple
            or not chunks
            or len(chunks) > V49C_MAXIMUM_STAGED_TLS_CIPHERTEXT_CHUNKS
            or any(type(chunk) is not bytes or not chunk for chunk in chunks)
            or type(prepared.ciphertext_octets) is not int
            or prepared.ciphertext_octets < 1
            or sum(map(len, chunks)) != prepared.ciphertext_octets
            or prepared.ciphertext_octets > V49_MAXIMUM_TLS_OPERATION_CIPHERTEXT_BYTES
            or tuple(hashlib.sha256(chunk).hexdigest() for chunk in chunks)
            != prepared.ordered_ciphertext_chunks_sha256
            or _ordered_v49e_tls_control_batch_sha256(chunks)
            != prepared.ciphertext_batch_sha256
            or type(prepared.peer_close_notify_received_during_preparation) is not bool
            or (
                prepared.control_kind
                is TlsControlOutputKindV49E.OPAQUE_POST_HANDSHAKE_RESPONSE
                and prepared.peer_close_notify_received_during_preparation
            )
        ):
            raise PhysicalTlsWebSocketV49ProtocolError(
                "prepared TLS control differs from its exact kind, hashes, or bounds"
            )

    @staticmethod
    def _prepared_tls_control_values_v49e(
        prepared: PreparedTlsControlCiphertextV49E,
    ) -> tuple[Any, ...]:
        return tuple(
            getattr(prepared, field)
            for field in PreparedTlsControlCiphertextV49E.__dataclass_fields__
        )

    def _drain_tls_control_output_v49e(
        self,
        *,
        control_kind: TlsControlOutputKindV49E,
        peer_close_notify_received_during_preparation: bool,
        prior_state: TlsWebSocketDriverStateV49,
    ) -> PreparedTlsControlCiphertextV49E:
        """Consume one bounded MemoryBIO batch into a sealed retained value."""

        evidence = self._handshake_evidence
        if (
            type(evidence) is not DriverHandshakeEvidenceV49
            or not self._handshake_evidence_bound
        ):
            raise PhysicalTlsWebSocketV49StateError(
                "TLS control preparation requires bound handshake evidence"
            )
        chunks_list: list[bytes] = []
        octets = 0
        while self._outgoing.pending:
            chunk = self._outgoing.read()
            if type(chunk) is not bytes or not chunk:
                raise PhysicalTlsWebSocketV49ProtocolError(
                    "outgoing MemoryBIO returned an invalid TLS-control chunk"
                )
            chunks_list.append(chunk)
            octets += len(chunk)
            if (
                len(chunks_list) > V49C_MAXIMUM_STAGED_TLS_CIPHERTEXT_CHUNKS
                or octets > V49_MAXIMUM_TLS_OPERATION_CIPHERTEXT_BYTES
            ):
                raise PhysicalTlsWebSocketV49ProtocolError(
                    "TLS-control ciphertext exceeds its exact retained bounds"
                )
        chunks = tuple(chunks_list)
        if not chunks:
            raise PhysicalTlsWebSocketV49ProtocolError(
                "TLS-control operation produced no exact ciphertext"
            )
        sequence = self._tls_control_sequence_v49e + 1
        prepared = PreparedTlsControlCiphertextV49E(
            _token=_TLS_CONTROL_TOKEN,
            control_sequence=sequence,
            control_kind=control_kind,
            driver_evidence_nonce_sha256=evidence.evidence_nonce_sha256,
            ordered_ciphertext_chunks=chunks,
            ordered_ciphertext_chunks_sha256=tuple(
                hashlib.sha256(chunk).hexdigest() for chunk in chunks
            ),
            ciphertext_batch_sha256=_ordered_v49e_tls_control_batch_sha256(chunks),
            ciphertext_octets=octets,
            peer_close_notify_received_during_preparation=(
                peer_close_notify_received_during_preparation
            ),
        )
        self._assert_prepared_tls_control_integrity_v49e(prepared)
        self._tls_control_sequence_v49e = sequence
        self._active_prepared_tls_control_v49e = prepared
        self._active_prepared_tls_control_values_v49e = (
            self._prepared_tls_control_values_v49e(prepared)
        )
        self._active_prepared_tls_control_offset_v49e = 0
        self._active_tls_control_prior_state_v49e = prior_state
        self._state = TlsWebSocketDriverStateV49.TLS_CONTROL_CIPHERTEXT_PREPARED_V49E
        return prepared

    def _assert_tls_control_fifo_idle_v49e(self) -> None:
        if (
            self._pending_raw is not None
            or self._durable_ingress_buffer_v49d
            or self._pending_protocol_output
            or self._pending_send_eof
            or self._pending_tls_ciphertext
            or self._pending_tls_ciphertext_offset != 0
            or self._active_prepared_wire_v49c is not None
            or self._active_prepared_tls_v49c is not None
            or self._active_prepared_tls_offset_v49c != 0
            or self._active_prepared_tls_control_v49e is not None
            or self._active_prepared_tls_control_values_v49e is not None
            or self._active_prepared_tls_control_offset_v49e != 0
            or self._active_tls_control_prior_state_v49e is not None
        ):
            raise PhysicalTlsWebSocketV49StateError(
                "TLS control requires one idle exact owner FIFO"
            )

    async def prepare_local_close_notify_v49e(
        self,
        *,
        deadline_ns: int,
    ) -> PreparedTlsControlCiphertextV49E:
        """Run ``SSLObject.unwrap`` once and retain its exact local alert bytes.

        This method performs no socket operation.  ``SSLWantReadError`` is the
        normal unilateral-shutdown result: the local alert is retained now and
        peer ``close_notify`` is observed later through the polling primitive.
        """

        self._assert_async_context()
        try:
            exact_deadline_ns = self._bounded_absolute_deadline_v49e(deadline_ns)
        except TimeoutError as exc:
            raise self._deadline_expired_no_observation_v49e(
                operation="LOCAL_TLS_CLOSE_NOTIFY_PREPARATION",
                deadline_ns=deadline_ns,
            ) from exc
        async with self._actor_lock:
            if (
                self._state is not TlsWebSocketDriverStateV49.WS_CLOSING
                or self._local_close_notify_prepared_v49e
                or self._local_close_notify_fully_kernel_accepted_v49e
            ):
                raise PhysicalTlsWebSocketV49StateError(
                    "local TLS close requires one completed WebSocket close state"
                )
            self._assert_tls_control_fifo_idle_v49e()
            if self._outgoing.pending or self._tls.pending():
                raise PhysicalTlsWebSocketV49StateError(
                    "local TLS close requires no unresolved TLS input or output"
                )
            try:
                self._remaining_seconds(exact_deadline_ns)
            except TimeoutError as exc:
                raise self._deadline_expired_no_observation_v49e(
                    operation="LOCAL_TLS_CLOSE_NOTIFY_PREPARATION",
                    deadline_ns=exact_deadline_ns,
                ) from exc
            try:
                peer_close_received = False
                try:
                    result = self._tls.unwrap()
                except (ssl.SSLWantReadError, ssl.SSLWantWriteError):
                    result = None
                except ssl.SSLZeroReturnError:
                    result = None
                    peer_close_received = True
                except ssl.SSLEOFError as exc:
                    raise PhysicalTlsWebSocketV49TruncatedEof(
                        "TLS stream ended while preparing local close_notify"
                    ) from exc
                else:
                    if result is not None:
                        raise PhysicalTlsWebSocketV49ProtocolError(
                            "SSLObject.unwrap returned an unexpected transport"
                        )
                    peer_close_received = True
                prepared = self._drain_tls_control_output_v49e(
                    control_kind=TlsControlOutputKindV49E.LOCAL_CLOSE_NOTIFY,
                    peer_close_notify_received_during_preparation=(peer_close_received),
                    prior_state=TlsWebSocketDriverStateV49.WS_CLOSING,
                )
                self._local_close_notify_prepared_v49e = True
                if peer_close_received:
                    self._peer_close_notify_received_v49e = True
                return prepared
            except BaseException:
                # unwrap advances OpenSSL's shutdown state even when it raises
                # WANT_READ/WANT_WRITE.  Any failed preparation is unreplayable.
                self._state = TlsWebSocketDriverStateV49.FAULT_LATCHED
                raise

    async def prepare_opaque_post_handshake_response_v49e(
        self,
    ) -> PreparedTlsControlCiphertextV49E:
        """Retain already-produced post-handshake output without overclaiming.

        This opt-in V4.9E seam is the only path that converts pending outgoing
        BIO bytes into a positive artifact.  Existing V4.9D reads continue to
        reject the same condition before any socket write.
        """

        self._assert_async_context()
        async with self._actor_lock:
            if self._state not in {
                TlsWebSocketDriverStateV49.WS_OPEN_BOUND,
                TlsWebSocketDriverStateV49.WS_CLOSING,
            }:
                raise PhysicalTlsWebSocketV49StateError(
                    "opaque TLS response requires a pre-SHUT_WR bound TLS state"
                )
            prior_state = self._state
            self._assert_tls_control_fifo_idle_v49e()
            if not self._outgoing.pending:
                raise PhysicalTlsWebSocketV49StateError(
                    "no post-handshake TLS output is pending"
                )
            try:
                return self._drain_tls_control_output_v49e(
                    control_kind=(
                        TlsControlOutputKindV49E.OPAQUE_POST_HANDSHAKE_RESPONSE
                    ),
                    peer_close_notify_received_during_preparation=False,
                    prior_state=prior_state,
                )
            except BaseException:
                self._state = TlsWebSocketDriverStateV49.FAULT_LATCHED
                raise

    # A spelling-compatible alias keeps the public meaning explicit for callers
    # that describe this as pending output rather than a response.
    async def prepare_pending_post_handshake_output_v49e(
        self,
    ) -> PreparedTlsControlCiphertextV49E:
        return await self.prepare_opaque_post_handshake_response_v49e()

    async def send_prepared_tls_control_ciphertext_once_v49e(
        self,
        exact_ciphertext_slice: bytes,
        *,
        owned_socket: socket.socket,
        prepared: PreparedTlsControlCiphertextV49E,
        deadline_ns: int,
    ) -> int:
        """Submit one exact retained TLS-control suffix prefix once."""

        self._assert_async_context()
        async with self._actor_lock:
            try:
                if (
                    self._state
                    is not (
                        TlsWebSocketDriverStateV49.TLS_CONTROL_CIPHERTEXT_PREPARED_V49E
                    )
                    or prepared is not self._active_prepared_tls_control_v49e
                    or self._prepared_tls_control_values_v49e(prepared)
                    != self._active_prepared_tls_control_values_v49e
                ):
                    raise PhysicalTlsWebSocketV49StateError(
                        "send requires the exact active TLS-control artifact"
                    )
                self._assert_prepared_tls_control_integrity_v49e(prepared)
                offset = self._active_prepared_tls_control_offset_v49e
                ciphertext = prepared.exact_ciphertext
                if (
                    type(exact_ciphertext_slice) is not bytes
                    or not exact_ciphertext_slice
                    or offset < 0
                    or offset >= len(ciphertext)
                    or len(exact_ciphertext_slice) > len(ciphertext) - offset
                    or exact_ciphertext_slice
                    != ciphertext[offset : offset + len(exact_ciphertext_slice)]
                ):
                    raise PhysicalTlsWebSocketV49ProtocolError(
                        "TLS-control send slice isn't the retained suffix prefix"
                    )
                if type(deadline_ns) is not int or deadline_ns < 0:
                    raise PhysicalTlsWebSocketV49ProtocolError(
                        "TLS-control send deadline must be an absolute integer"
                    )
                self._assert_socket(owned_socket)
                try:
                    self._remaining_seconds(deadline_ns)
                except TimeoutError as exc:
                    raise self._deadline_expired_no_observation_v49e(
                        operation="TLS_CONTROL_SEND_BEFORE_SYSCALL",
                        deadline_ns=deadline_ns,
                    ) from exc

                attempts = 0
                would_block_count = 0
                while True:
                    attempts += 1
                    if attempts > V49_MAXIMUM_RAW_SEND_ATTEMPTS:
                        raise PhysicalTlsWebSocketV49ProtocolError(
                            "TLS-control send exceeded its syscall-attempt bound"
                        )
                    self._assert_socket(owned_socket)
                    try:
                        self._remaining_seconds(deadline_ns)
                    except TimeoutError as exc:
                        if would_block_count:
                            raise self._send_deadline_no_kernel_acceptance_v49e(
                                send_kind="TLS_CONTROL",
                                transport_sequence=prepared.control_sequence,
                                ciphertext_batch_sha256=(
                                    prepared.ciphertext_batch_sha256
                                ),
                                ciphertext_octets=prepared.ciphertext_octets,
                                ciphertext_start_octet=offset,
                                exact_slice=exact_ciphertext_slice,
                                deadline_ns=deadline_ns,
                                would_block_count=would_block_count,
                            ) from exc
                        raise self._deadline_expired_no_observation_v49e(
                            operation="TLS_CONTROL_SEND_BEFORE_SYSCALL",
                            deadline_ns=deadline_ns,
                        ) from exc
                    view = memoryview(exact_ciphertext_slice)
                    try:
                        try:
                            count = owned_socket.send(view)
                        except BlockingIOError as exc:
                            ambiguous = getattr(exc, "characters_written", None)
                            if ambiguous not in {None, 0}:
                                raise PhysicalTlsWebSocketV49ProtocolError(
                                    "would-block reported ambiguous TLS-control progress"
                                ) from exc
                            would_block_count += 1
                            try:
                                await self._wait_socket_writable(
                                    owned_socket, deadline_ns=deadline_ns
                                )
                            except TimeoutError as timeout_exc:
                                raise self._send_deadline_no_kernel_acceptance_v49e(
                                    send_kind="TLS_CONTROL",
                                    transport_sequence=prepared.control_sequence,
                                    ciphertext_batch_sha256=(
                                        prepared.ciphertext_batch_sha256
                                    ),
                                    ciphertext_octets=prepared.ciphertext_octets,
                                    ciphertext_start_octet=offset,
                                    exact_slice=exact_ciphertext_slice,
                                    deadline_ns=deadline_ns,
                                    would_block_count=would_block_count,
                                ) from timeout_exc
                            continue
                    finally:
                        view.release()
                    if (
                        type(count) is not int
                        or count <= 0
                        or count > len(exact_ciphertext_slice)
                    ):
                        raise PhysicalTlsWebSocketV49ProtocolError(
                            "socket.send returned an invalid TLS-control byte count"
                        )
                    next_offset = offset + count
                    self._active_prepared_tls_control_offset_v49e = next_offset
                    if next_offset == prepared.ciphertext_octets:
                        prior_state = self._active_tls_control_prior_state_v49e
                        self._active_prepared_tls_control_v49e = None
                        self._active_prepared_tls_control_values_v49e = None
                        self._active_prepared_tls_control_offset_v49e = 0
                        self._active_tls_control_prior_state_v49e = None
                        if (
                            prepared.control_kind
                            is TlsControlOutputKindV49E.LOCAL_CLOSE_NOTIFY
                        ):
                            self._local_close_notify_fully_kernel_accepted_v49e = True
                            self._state = TlsWebSocketDriverStateV49.TLS_SHUTDOWN_V49E
                        elif prior_state in {
                            TlsWebSocketDriverStateV49.WS_OPEN_BOUND,
                            TlsWebSocketDriverStateV49.WS_CLOSING,
                            TlsWebSocketDriverStateV49.TLS_SHUTDOWN_V49E,
                        }:
                            self._state = prior_state
                        else:
                            raise PhysicalTlsWebSocketV49ProtocolError(
                                "opaque TLS-control artifact lost its prior state"
                            )
                    return count
            except (
                PhysicalTlsWebSocketV49DeadlineExpiredNoObservation,
                PhysicalTlsWebSocketV49SendDeadlineExpiredNoKernelAcceptance,
            ):
                raise
            except BaseException:
                self._state = TlsWebSocketDriverStateV49.FAULT_LATCHED
                raise

    @staticmethod
    def _assert_unsendable_tls_output_integrity_v49e(
        evidence: UnsendableTlsPostHandshakeOutputV49E,
    ) -> None:
        if type(evidence) is not UnsendableTlsPostHandshakeOutputV49E:
            raise TypeError(
                "evidence must be exact UnsendableTlsPostHandshakeOutputV49E"
            )
        if (
            type(evidence.output_sequence) is not int
            or evidence.output_sequence < 1
            or type(evidence.driver_evidence_nonce_sha256) is not str
            or len(evidence.driver_evidence_nonce_sha256) != 64
            or any(
                char not in "0123456789abcdef"
                for char in evidence.driver_evidence_nonce_sha256
            )
            or type(evidence.ciphertext_sha256) is not str
            or len(evidence.ciphertext_sha256) != 64
            or any(
                char not in "0123456789abcdef" for char in evidence.ciphertext_sha256
            )
            or type(evidence.ciphertext_octets) is not int
            or not 1
            <= evidence.ciphertext_octets
            <= V49_MAXIMUM_TLS_OPERATION_CIPHERTEXT_BYTES
        ):
            raise PhysicalTlsWebSocketV49ProtocolError(
                "unsendable TLS output has inconsistent exact fields"
            )
        values = {
            "domain": "RiskYieldMMUnsendableTlsPostHandshakeOutputV4_9E",
            "output_sequence": evidence.output_sequence,
            "driver_evidence_nonce_sha256": (evidence.driver_evidence_nonce_sha256),
            "ciphertext_sha256": evidence.ciphertext_sha256,
            "ciphertext_octets": evidence.ciphertext_octets,
        }
        if evidence.unsendable_output_id != sha256_digest(values):
            raise PhysicalTlsWebSocketV49ProtocolError(
                "unsendable TLS output ID differs from its exact fields"
            )

    def _assert_active_unsendable_tls_output_v49e(
        self, evidence: UnsendableTlsPostHandshakeOutputV49E
    ) -> None:
        self._assert_unsendable_tls_output_integrity_v49e(evidence)
        handshake = self._handshake_evidence
        if (
            evidence is not self._active_unsendable_tls_output_v49e
            or self._active_unsendable_tls_output_values_v49e
            != tuple(
                getattr(evidence, field)
                for field in UnsendableTlsPostHandshakeOutputV49E.__dataclass_fields__
            )
            or type(handshake) is not DriverHandshakeEvidenceV49
            or evidence.driver_evidence_nonce_sha256 != handshake.evidence_nonce_sha256
        ):
            raise PhysicalTlsWebSocketV49StateError(
                "unsendable TLS output is not the exact retained driver evidence"
            )

    def _drain_unsendable_tls_output_v49e(
        self,
    ) -> UnsendableTlsPostHandshakeOutputV49E:
        """Consume outgoing BIO bytes without creating any send capability."""

        handshake = self._handshake_evidence
        if (
            type(handshake) is not DriverHandshakeEvidenceV49
            or not self._handshake_evidence_bound
            or self._active_unsendable_tls_output_v49e is not None
            or self._active_unsendable_tls_output_values_v49e is not None
        ):
            raise PhysicalTlsWebSocketV49StateError(
                "unsendable TLS output requires one exact retained driver"
            )
        digest = hashlib.sha256()
        octets = 0
        chunks = 0
        while self._outgoing.pending:
            # Read no more than one bounded TLS chunk, and at most one octet
            # beyond the total evidence ceiling.  The latter is sufficient to
            # prove overflow without hashing or retaining an unbounded value.
            read_octets = min(
                V49_TLS_CIPHERTEXT_READ_BYTES,
                V49_MAXIMUM_TLS_OPERATION_CIPHERTEXT_BYTES - octets + 1,
            )
            chunk = self._outgoing.read(read_octets)
            if type(chunk) is not bytes or not chunk:
                raise PhysicalTlsWebSocketV49ProtocolError(
                    "outgoing MemoryBIO returned invalid unsendable TLS bytes"
                )
            chunks += 1
            octets += len(chunk)
            if (
                chunks > V49C_MAXIMUM_STAGED_TLS_CIPHERTEXT_CHUNKS
                or octets > V49_MAXIMUM_TLS_OPERATION_CIPHERTEXT_BYTES
            ):
                raise PhysicalTlsWebSocketV49ProtocolError(
                    "unsendable TLS output exceeds its exact evidence bounds"
                )
            digest.update(chunk)
        if octets < 1:
            raise PhysicalTlsWebSocketV49ProtocolError(
                "post-SHUT_WR TLS output requirement produced no evidence bytes"
            )
        sequence = self._unsendable_tls_output_sequence_v49e + 1
        values = {
            "domain": "RiskYieldMMUnsendableTlsPostHandshakeOutputV4_9E",
            "output_sequence": sequence,
            "driver_evidence_nonce_sha256": handshake.evidence_nonce_sha256,
            "ciphertext_sha256": digest.hexdigest(),
            "ciphertext_octets": octets,
        }
        evidence = UnsendableTlsPostHandshakeOutputV49E(
            _token=_UNSENDABLE_TLS_OUTPUT_TOKEN,
            output_sequence=sequence,
            driver_evidence_nonce_sha256=handshake.evidence_nonce_sha256,
            ciphertext_sha256=digest.hexdigest(),
            ciphertext_octets=octets,
            unsendable_output_id=sha256_digest(values),
        )
        self._assert_unsendable_tls_output_integrity_v49e(evidence)
        self._unsendable_tls_output_sequence_v49e = sequence
        self._active_unsendable_tls_output_v49e = evidence
        self._active_unsendable_tls_output_values_v49e = tuple(
            getattr(evidence, field)
            for field in UnsendableTlsPostHandshakeOutputV49E.__dataclass_fields__
        )
        return evidence

    def _raise_unsendable_tls_output_v49e(self, message: str) -> None:
        evidence = self._drain_unsendable_tls_output_v49e()
        raise PhysicalTlsWebSocketV49UnsendablePostHandshakeOutput(
            _token=_UNSENDABLE_TLS_OUTPUT_EXCEPTION_TOKEN,
            evidence=evidence,
            message=message,
        )

    def _make_tls_shutdown_observation_v49e(
        self,
        *,
        observation_kind: TlsShutdownObservationKindV49E,
        ciphertext_octets_received: int,
    ) -> TlsShutdownObservationV49E:
        evidence = self._handshake_evidence
        if type(evidence) is not DriverHandshakeEvidenceV49:
            raise PhysicalTlsWebSocketV49StateError(
                "TLS shutdown observation lacks bound handshake evidence"
            )
        sequence = self._shutdown_observation_sequence_v49e + 1
        peer_received = self._peer_close_notify_received_v49e
        tcp_eof = observation_kind is TlsShutdownObservationKindV49E.TCP_EOF
        truncated = tcp_eof and not peer_received
        values = {
            "domain": "RiskYieldMMTlsShutdownObservationV4_9E",
            "observation_sequence": sequence,
            "observation_kind": observation_kind.value,
            "driver_evidence_nonce_sha256": evidence.evidence_nonce_sha256,
            "peer_close_notify_received": peer_received,
            "tcp_eof_received": tcp_eof,
            "truncated": truncated,
            "ciphertext_octets_received": ciphertext_octets_received,
        }
        observation = TlsShutdownObservationV49E(
            _token=_TLS_SHUTDOWN_OBSERVATION_TOKEN,
            observation_sequence=sequence,
            observation_kind=observation_kind,
            driver_evidence_nonce_sha256=evidence.evidence_nonce_sha256,
            peer_close_notify_received=peer_received,
            tcp_eof_received=tcp_eof,
            truncated=truncated,
            ciphertext_octets_received=ciphertext_octets_received,
            observation_id=sha256_digest(values),
        )
        self._assert_tls_shutdown_observation_integrity_v49e(observation)
        self._shutdown_observation_sequence_v49e = sequence
        return observation

    @staticmethod
    def _assert_tls_shutdown_observation_integrity_v49e(
        observation: TlsShutdownObservationV49E,
    ) -> None:
        if type(observation) is not TlsShutdownObservationV49E:
            raise TypeError("observation must be exact TlsShutdownObservationV49E")
        kind = observation.observation_kind
        expected_peer = kind is TlsShutdownObservationKindV49E.PEER_CLOSE_NOTIFY
        expected_tcp_eof = kind is TlsShutdownObservationKindV49E.TCP_EOF
        if (
            type(kind) is not TlsShutdownObservationKindV49E
            or type(observation.observation_sequence) is not int
            or observation.observation_sequence < 1
            or type(observation.driver_evidence_nonce_sha256) is not str
            or len(observation.driver_evidence_nonce_sha256) != 64
            or any(
                char not in "0123456789abcdef"
                for char in observation.driver_evidence_nonce_sha256
            )
            or type(observation.peer_close_notify_received) is not bool
            or type(observation.tcp_eof_received) is not bool
            or type(observation.truncated) is not bool
            or type(observation.ciphertext_octets_received) is not int
            or not 0
            <= observation.ciphertext_octets_received
            <= V49_MAXIMUM_TLS_OPERATION_CIPHERTEXT_BYTES
            or observation.tcp_eof_received != expected_tcp_eof
            or (expected_peer and not observation.peer_close_notify_received)
            or (expected_peer and observation.truncated)
            or (
                expected_tcp_eof
                and observation.truncated
                != (not observation.peer_close_notify_received)
            )
        ):
            raise PhysicalTlsWebSocketV49ProtocolError(
                "TLS shutdown observation has inconsistent exact fields"
            )
        values = {
            "domain": "RiskYieldMMTlsShutdownObservationV4_9E",
            "observation_sequence": observation.observation_sequence,
            "observation_kind": kind.value,
            "driver_evidence_nonce_sha256": (observation.driver_evidence_nonce_sha256),
            "peer_close_notify_received": observation.peer_close_notify_received,
            "tcp_eof_received": observation.tcp_eof_received,
            "truncated": observation.truncated,
            "ciphertext_octets_received": observation.ciphertext_octets_received,
        }
        if observation.observation_id != sha256_digest(values):
            raise PhysicalTlsWebSocketV49ProtocolError(
                "TLS shutdown observation ID differs from its exact fields"
            )

    async def poll_tls_shutdown_v49e(
        self,
        owned_socket: socket.socket,
        *,
        timeout_seconds: int | None = None,
        deadline_ns: int | None = None,
    ) -> TlsShutdownObservationV49E:
        """Observe peer ``close_notify`` separately from TCP EOF/truncation.

        Once local alert ciphertext is fully kernel-accepted, continued
        ``unwrap`` drives only the retained TLS object.  EOF without prior
        authenticated peer alert is returned as a sealed truncation fact; it
        is never upgraded into a clean TLS close.
        """

        self._assert_async_context()
        if (timeout_seconds is None) == (deadline_ns is None):
            raise TypeError("exactly one of timeout_seconds or deadline_ns is required")
        if deadline_ns is None:
            timeout = canonical_safe_int(
                timeout_seconds,
                field="timeout_seconds",
                minimum=1,
                maximum=300,
            )
            operation_deadline_ns: int | None = None
        else:
            timeout = None
            try:
                operation_deadline_ns = self._bounded_absolute_deadline_v49e(
                    deadline_ns
                )
            except TimeoutError as exc:
                raise self._deadline_expired_no_observation_v49e(
                    operation="TLS_SHUTDOWN_POLL",
                    deadline_ns=deadline_ns,
                ) from exc
        async with self._actor_lock:
            if (
                self._state is not TlsWebSocketDriverStateV49.TLS_SHUTDOWN_V49E
                or not self._local_close_notify_fully_kernel_accepted_v49e
                or self._active_prepared_tls_control_v49e is not None
                or self._active_unsendable_tls_output_v49e is not None
                or self._tcp_eof_received_v49e
            ):
                raise PhysicalTlsWebSocketV49StateError(
                    "TLS shutdown polling requires accepted local close ciphertext"
                )
            positive_ciphertext_received = False
            ciphertext_hasher = hashlib.sha256()
            try:
                self._assert_shutdown_socket_v49e(owned_socket)
                self.assert_current()
                if operation_deadline_ns is None:
                    assert timeout is not None
                    operation_deadline_ns = _boottime_ns() + timeout * 10**9
                self._remaining_seconds(operation_deadline_ns)
                self._operation_ciphertext_received = 0
                if self._outgoing.pending:
                    self._raise_unsendable_tls_output_v49e(
                        "TLS shutdown began with unsendable post-SHUT_WR output"
                    )
                if (
                    self._peer_close_notify_received_v49e
                    and not self._peer_close_notify_observation_emitted_v49e
                ):
                    self._peer_close_notify_observation_emitted_v49e = True
                    return self._make_tls_shutdown_observation_v49e(
                        observation_kind=(
                            TlsShutdownObservationKindV49E.PEER_CLOSE_NOTIFY
                        ),
                        ciphertext_octets_received=0,
                    )

                if self._peer_close_notify_received_v49e:
                    trailing = await self._recv_after_readiness_v49e(
                        owned_socket,
                        deadline_ns=operation_deadline_ns,
                        shutdown_socket_v49e=True,
                    )
                    if trailing:
                        raise PhysicalTlsWebSocketV49ProtocolError(
                            "ciphertext arrived after completed peer TLS shutdown"
                        )
                    self._incoming.write_eof()
                    self._tcp_eof_received_v49e = True
                    return self._make_tls_shutdown_observation_v49e(
                        observation_kind=TlsShutdownObservationKindV49E.TCP_EOF,
                        ciphertext_octets_received=0,
                    )

                while True:
                    peer_close_received = False
                    try:
                        result = self._tls.unwrap()
                    except ssl.SSLWantReadError:
                        if self._outgoing.pending:
                            self._raise_unsendable_tls_output_v49e(
                                "TLS shutdown produced unsendable post-SHUT_WR output"
                            )
                        ciphertext = await self._recv_after_readiness_v49e(
                            owned_socket,
                            deadline_ns=operation_deadline_ns,
                            shutdown_socket_v49e=True,
                        )
                        if not ciphertext:
                            self._incoming.write_eof()
                            self._tcp_eof_received_v49e = True
                            return self._make_tls_shutdown_observation_v49e(
                                observation_kind=(
                                    TlsShutdownObservationKindV49E.TCP_EOF
                                ),
                                ciphertext_octets_received=(
                                    self._operation_ciphertext_received
                                ),
                            )
                        positive_ciphertext_received = True
                        ciphertext_hasher.update(ciphertext)
                        self._operation_ciphertext_received += len(ciphertext)
                        if (
                            self._operation_ciphertext_received
                            > V49_MAXIMUM_TLS_OPERATION_CIPHERTEXT_BYTES
                        ):
                            raise PhysicalTlsWebSocketV49ProtocolError(
                                "TLS shutdown input exceeded its ciphertext bound"
                            ) from None
                        self._incoming.write(ciphertext)
                        continue
                    except ssl.SSLWantWriteError as exc:
                        if not self._outgoing.pending:
                            raise PhysicalTlsWebSocketV49ProtocolError(
                                "TLS shutdown requested a write without evidence bytes"
                            ) from exc
                        self._raise_unsendable_tls_output_v49e(
                            "TLS shutdown requires unsendable post-SHUT_WR output"
                        )
                    except ssl.SSLZeroReturnError:
                        result = None
                        peer_close_received = True
                    except ssl.SSLEOFError:
                        if self._outgoing.pending:
                            self._raise_unsendable_tls_output_v49e(
                                "TLS shutdown EOF produced unsendable "
                                "post-SHUT_WR output"
                            )
                        self._tcp_eof_received_v49e = True
                        return self._make_tls_shutdown_observation_v49e(
                            observation_kind=TlsShutdownObservationKindV49E.TCP_EOF,
                            ciphertext_octets_received=(
                                self._operation_ciphertext_received
                            ),
                        )
                    except ssl.SSLError as exc:
                        if self._outgoing.pending:
                            try:
                                self._raise_unsendable_tls_output_v49e(
                                    "TLS shutdown failure produced unsendable "
                                    "post-SHUT_WR output"
                                )
                            except (
                                PhysicalTlsWebSocketV49UnsendablePostHandshakeOutput
                            ) as output_exc:
                                raise output_exc from exc
                        raise
                    else:
                        if result is not None:
                            raise PhysicalTlsWebSocketV49ProtocolError(
                                "continued SSLObject.unwrap returned a transport"
                            )
                        peer_close_received = True
                    if self._outgoing.pending:
                        self._raise_unsendable_tls_output_v49e(
                            "TLS shutdown retained unsendable post-SHUT_WR output"
                        )
                    if not peer_close_received:
                        raise PhysicalTlsWebSocketV49ProtocolError(
                            "TLS shutdown completed without peer-close evidence"
                        )
                    self._peer_close_notify_received_v49e = True
                    self._peer_close_notify_observation_emitted_v49e = True
                    return self._make_tls_shutdown_observation_v49e(
                        observation_kind=(
                            TlsShutdownObservationKindV49E.PEER_CLOSE_NOTIFY
                        ),
                        ciphertext_octets_received=(
                            self._operation_ciphertext_received
                        ),
                    )
            except TimeoutError as exc:
                if positive_ciphertext_received:
                    self._state = TlsWebSocketDriverStateV49.FAULT_LATCHED
                    raise self._deadline_expired_after_progress_v49e(
                        operation="TLS_SHUTDOWN_POLL",
                        deadline_ns=operation_deadline_ns,
                        ciphertext_octets_received=(
                            self._operation_ciphertext_received
                        ),
                        ciphertext_sha256=ciphertext_hasher.hexdigest(),
                    ) from exc
                raise self._deadline_expired_no_observation_v49e(
                    operation="TLS_SHUTDOWN_POLL",
                    deadline_ns=operation_deadline_ns,
                ) from exc
            except PhysicalTlsWebSocketV49PostHandshakeOutputRequired:
                # Explicit-control output is sealed separately and never
                # converted into retryable no-observation evidence.
                raise
            except BaseException:
                self._state = TlsWebSocketDriverStateV49.FAULT_LATCHED
                raise

    async def submit_permitted_chunks(
        self,
        owned_socket: socket.socket,
        *,
        permit: Any,
        ordered_chunks: tuple[bytes, ...],
        before_raw_send_attempt: RawSocketSendBeforeAttemptV49 | None = None,
        after_raw_send_result: RawSocketSendAfterResultV49 | None = None,
    ) -> int:
        """Submit only the exact pending Sans-I/O drain under a durable permit."""

        self._assert_async_context()
        async with self._actor_lock:
            if (
                self._state is not TlsWebSocketDriverStateV49.PROTOCOL_OUTPUT_PENDING
                or type(permit) is not OutboundControlWritePermitConsumedV4
                or type(ordered_chunks) is not tuple
                or ordered_chunks != self._pending_protocol_output
                or not ordered_chunks
            ):
                raise PhysicalTlsWebSocketV49StateError(
                    "control write isn't the exact permitted pending protocol drain"
                )
            if permit.wire_octet_length != sum(
                map(len, ordered_chunks)
            ) or permit.wire_batch_sha256 != _ordered_wire_batch_sha256(ordered_chunks):
                raise PhysicalTlsWebSocketV49ProtocolError(
                    "durable permit differs from the pending Sans-I/O output"
                )
            try:
                self._assert_socket(owned_socket)
                self.assert_current()
                deadline_ns = permit.send_not_after_monotonic_ns
                if _boottime_ns() >= deadline_ns:
                    raise TimeoutError("control permit expired before TLS submission")
                accepted = await self._write_plaintext(
                    owned_socket,
                    ordered_chunks,
                    deadline_ns=deadline_ns,
                    before_send_attempt=before_raw_send_attempt,
                    after_send_result=after_raw_send_result,
                )
                if accepted != permit.wire_octet_length:
                    raise PhysicalTlsWebSocketV49ProtocolError(
                        "TLS accepted an incomplete permitted protocol drain"
                    )
                self._pending_protocol_output = ()
                if self._pending_send_eof:
                    # Correct TLS close_notify/unwrap ordering is deliberately
                    # a subsequent gate.  Never substitute a raw TCP half-close.
                    self._pending_send_eof = False
                    self._state = TlsWebSocketDriverStateV49.WS_CLOSING
                elif self._protocol.state is State.OPEN:
                    self._state = TlsWebSocketDriverStateV49.WS_OPEN_BOUND
                else:
                    self._state = TlsWebSocketDriverStateV49.WS_CLOSING
                return accepted
            except BaseException:
                self._state = TlsWebSocketDriverStateV49.FAULT_LATCHED
                raise

    def abort(self) -> None:
        if self._state is TlsWebSocketDriverStateV49.CLOSED:
            return
        self._state = TlsWebSocketDriverStateV49.CLOSED
        self._terminal_ingress_ciphertext_hasher_v49e = None
        self._pending_raw = None
        self._durable_ingress_buffer_v49d = b""
        self._parser_unit_sequence_v49d = 0
        self._durable_ingress_mode_v49d = False
        self._fragmented_text_decoder_v49d = None
        self._pending_protocol_output = ()
        self._coalesced_tail = ()
        self._pending_tls_ciphertext = b""
        self._pending_tls_ciphertext_offset = 0
        self._active_prepared_wire_v49c = None
        self._active_prepared_wire_was_protocol_output_v49c = False
        self._active_prepared_tls_v49c = None
        self._active_prepared_tls_offset_v49c = 0
        self._active_prepared_tls_control_v49e = None
        self._active_prepared_tls_control_values_v49e = None
        self._active_prepared_tls_control_offset_v49e = 0
        self._active_tls_control_prior_state_v49e = None
        self._local_close_notify_prepared_v49e = False
        self._local_close_notify_fully_kernel_accepted_v49e = False
        self._peer_close_notify_received_v49e = False
        self._peer_close_notify_observation_emitted_v49e = False
        self._tcp_eof_received_v49e = False
        self._active_unsendable_tls_output_v49e = None
        self._active_unsendable_tls_output_values_v49e = None
        self._handshake_evidence_values = None
        try:
            self._trust_store.close()
        finally:
            if self._runtime_artifacts is not None:
                self._runtime_artifacts.close()

    def _invalidate_in_fork_child(self) -> None:
        """Invalidate inherited authority without taking any inherited lock."""

        self._state = TlsWebSocketDriverStateV49.CLOSED
        self._pending_raw = None
        self._durable_ingress_buffer_v49d = b""
        self._parser_unit_sequence_v49d = 0
        self._durable_ingress_mode_v49d = False
        self._fragmented_text_decoder_v49d = None
        self._pending_protocol_output = ()
        self._coalesced_tail = ()
        self._pending_tls_ciphertext = b""
        self._pending_tls_ciphertext_offset = 0
        self._active_prepared_wire_v49c = None
        self._active_prepared_wire_was_protocol_output_v49c = False
        self._active_prepared_tls_v49c = None
        self._active_prepared_tls_offset_v49c = 0
        self._active_prepared_tls_control_v49e = None
        self._active_prepared_tls_control_values_v49e = None
        self._active_prepared_tls_control_offset_v49e = 0
        self._active_tls_control_prior_state_v49e = None
        self._local_close_notify_prepared_v49e = False
        self._local_close_notify_fully_kernel_accepted_v49e = False
        self._peer_close_notify_received_v49e = False
        self._peer_close_notify_observation_emitted_v49e = False
        self._tcp_eof_received_v49e = False
        self._active_unsendable_tls_output_v49e = None
        self._active_unsendable_tls_output_values_v49e = None
        self._handshake_evidence_values = None
        authority = self._runtime_artifacts
        if type(authority) is PinnedTlsWebSocketRuntimeArtifactsV49B:
            authority._invalidate_in_fork_child()
        # PinnedRuntimeArtifactV4.close is intentionally lock-free.  Calling
        # PinnedTlsTrustStoreV49.close here would acquire an RLock inherited
        # from a potentially vanished thread and can deadlock after fork.
        artifact = getattr(self._trust_store, "_artifact", None)
        if artifact is not None:
            try:
                artifact.close()
            except OSError:
                pass


__all__ = [
    "DriverHandshakeEvidenceV49",
    "DurableIngressAdoptionV49D",
    "ExactTlsWebSocketDriverV49",
    "ParsedDurableUnitV49D",
    "ParsedWebSocketIngressV49",
    "PendingRawIngressV49",
    "PreparedTlsCiphertextV49C",
    "PreparedTlsControlCiphertextV49E",
    "PreparedWebSocketWireV49C",
    "PhysicalTlsWebSocketV49CleanTlsClose",
    "PhysicalTlsWebSocketV49DeadlineExpiredAfterProgress",
    "PhysicalTlsWebSocketV49DeadlineExpiredNoObservation",
    "PhysicalTlsWebSocketV49DependencyError",
    "PhysicalTlsWebSocketV49Error",
    "PhysicalTlsWebSocketV49PostHandshakeOutputRequired",
    "PhysicalTlsWebSocketV49ProtocolError",
    "PhysicalTlsWebSocketV49SendDeadlineExpiredNoKernelAcceptance",
    "PhysicalTlsWebSocketV49StateError",
    "PhysicalTlsWebSocketV49TruncatedEof",
    "PhysicalTlsWebSocketV49UnsendablePostHandshakeOutput",
    "RawSocketSendAfterResultV49",
    "RawSocketSendAttemptV49",
    "RawSocketSendBeforeAttemptV49",
    "RawSocketSendOutcomeV49",
    "RawSocketSendResultV49",
    "RawSocketSendTraceV49",
    "TlsControlOutputKindV49E",
    "TlsShutdownObservationKindV49E",
    "TlsShutdownObservationV49E",
    "TlsWebSocketDriverStateV49",
    "UnsendableTlsPostHandshakeOutputV49E",
    "V49_HANDSHAKE_TIMEOUT_SECONDS",
    "V49_MAXIMUM_HTTP_RESPONSE_HEAD_BYTES",
    "V49_MAXIMUM_POST_UPGRADE_PENDING_BYTES",
    "V49C_MAXIMUM_STAGED_TLS_CIPHERTEXT_CHUNKS",
    "V49C_MAXIMUM_STAGED_WIRE_CHUNKS",
    "V49C_MAXIMUM_STAGED_WIRE_OCTETS",
    "V49D_MAXIMUM_DURABLE_INGRESS_BUFFER_BYTES",
    "V49_WEBSOCKETS_VERSION",
    "WebSocketFrameEventV49",
    "split_http_upgrade_prefix_v49",
]

"""Pure layered terminal-state contracts for the V4.9C transport actor.

The live actor owns clocks, persistence, sockets, and top-level actor events.
This module deliberately owns none of those concerns.  It provides canonical
payloads and a deterministic reducer which the actor can embed in its
append-only event stream.

The reducer keeps the WebSocket, TLS, and TCP shutdown claims separate.  A
logical WebSocket Close or TLS ``close_notify`` isn't treated as physically
written until the matching obligation is known to be fully accepted by the
local kernel.  That claim still isn't peer delivery; peer observations remain
separate transitions.

One unavoidable uncertainty is explicit: after ``SEND_ATTEMPT_STARTED``, only
the exact matching durable outcome or ``UNKNOWN_SEND`` may follow.  Recovery
must never retry an unresolved attempt.  ``terminalize_pending_send_v49c``
constructs and applies the required append-only ``UNKNOWN_SEND`` transition.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Final

from .canonical import (
    CANONICALIZATION_VERSION,
    CanonicalizationError,
    canonical_hash,
    canonical_identifier,
    canonical_safe_int,
    require_exact_keys,
    sha256_digest,
)

PHYSICAL_TRANSPORT_TERMINAL_V49C_SCHEMA_VERSION: Final = (
    "riskyieldmm_physical_transport_terminal_v49c"
)
V49C_RECOVERY_UNKNOWN_SEND_CAUSE: Final = "RECOVERY_WITHOUT_SEND_OUTCOME"
V49C_TLS_TRUNCATION_CAUSE: Final = "TCP_EOF_BEFORE_TLS_CLOSE_NOTIFY"
V49C_WEBSOCKET_TRUNCATION_CAUSE: Final = "TLS_CLOSE_NOTIFY_BEFORE_WEBSOCKET_CLOSE"
V49E_TLS_CONTROL_SEND_OUTCOME_UNKNOWN_CAUSE: Final = "TLS_CONTROL_SEND_OUTCOME_UNKNOWN"
V49E_TLS_OPERATION_DRIVER_ERROR_CAUSE: Final = "TLS_OPERATION_DRIVER_ERROR"
V49E_TLS_SHUTDOWN_DEADLINE_EXPIRED_CAUSE: Final = "TLS_SHUTDOWN_DEADLINE_EXPIRED"
V49E_TLS_SHUTDOWN_DEADLINE_EXPIRED_AFTER_PROGRESS_CAUSE: Final = (
    "TLS_SHUTDOWN_DEADLINE_EXPIRED_AFTER_PROGRESS"
)
V49E_TLS_POST_HANDSHAKE_OUTPUT_AFTER_SHUT_WR_CAUSE: Final = (
    "TLS_POST_HANDSHAKE_OUTPUT_AFTER_SHUT_WR"
)
V49E_TCP_HALF_CLOSE_ERROR_CAUSE: Final = "TCP_HALF_CLOSE_ERROR"
V49E_TCP_HALF_CLOSE_OUTCOME_UNKNOWN_CAUSE: Final = "TCP_HALF_CLOSE_OUTCOME_UNKNOWN"
V49E_TCP_HALF_CLOSE_DEADLINE_EXPIRED_BEFORE_SYSCALL_CAUSE: Final = (
    "TCP_HALF_CLOSE_DEADLINE_EXPIRED_BEFORE_SYSCALL"
)
V49E_LOCAL_SHUTDOWN_COMMAND_DEADLINE_EXPIRED_CAUSE: Final = (
    "LOCAL_SHUTDOWN_COMMAND_DEADLINE_EXPIRED"
)
V49E_LOCAL_SHUTDOWN_CLOCK_DISAGREEMENT_CAUSE: Final = (
    "LOCAL_SHUTDOWN_CLOCK_DISAGREEMENT"
)
V49E_TERMINAL_CLOSE_INGRESS_DEADLINE_EXPIRED_AFTER_PROGRESS_CAUSE: Final = (
    "TERMINAL_CLOSE_INGRESS_DEADLINE_EXPIRED_AFTER_PROGRESS"
)


class PhysicalTransportTerminalV49CError(RuntimeError):
    """Base error for an invalid V4.9C terminal-state operation."""


class PhysicalTransportTerminalV49CStateError(PhysicalTransportTerminalV49CError):
    """A transition violates the append-only layered state machine."""


class TerminalTransitionKindV49C(str, Enum):
    """Closed transition vocabulary embedded by the V4.9C actor."""

    WS_CLOSE_SENT = "WS_CLOSE_SENT"
    WS_CLOSE_RECEIVED = "WS_CLOSE_RECEIVED"
    SEND_ATTEMPT_STARTED = "SEND_ATTEMPT_STARTED"
    SEND_ATTEMPT_RESOLVED = "SEND_ATTEMPT_RESOLVED"
    OUTBOUND_OBLIGATION_FULLY_KERNEL_ACCEPTED = (
        "OUTBOUND_OBLIGATION_FULLY_KERNEL_ACCEPTED"
    )
    TLS_CLOSE_NOTIFY_PREPARED = "TLS_CLOSE_NOTIFY_PREPARED"
    TLS_CLOSE_NOTIFY_SENT = "TLS_CLOSE_NOTIFY_SENT"
    TLS_CLOSE_NOTIFY_RECEIVED = "TLS_CLOSE_NOTIFY_RECEIVED"
    TCP_FIN_SENT = "TCP_FIN_SENT"
    TCP_EOF_RECEIVED = "TCP_EOF_RECEIVED"
    CLEAN_ALL_LAYERS = "CLEAN_ALL_LAYERS"
    TIMEOUT = "TIMEOUT"
    FATAL = "FATAL"
    STORAGE_FAILURE = "STORAGE_FAILURE"
    UNKNOWN_SEND = "UNKNOWN_SEND"


class OutboundObligationLayerV49C(str, Enum):
    """Wire layer targeted by one exact send attempt."""

    APPLICATION_DATA = "APPLICATION_DATA"
    WEBSOCKET_CLOSE = "WEBSOCKET_CLOSE"
    TLS_CLOSE_NOTIFY = "TLS_CLOSE_NOTIFY"
    TLS_OPAQUE_CONTROL = "TLS_OPAQUE_CONTROL"


class TerminalOutcomeV49C(str, Enum):
    """Mutually exclusive final session classifications."""

    CLEAN_ALL_LAYERS = "CLEAN_ALL_LAYERS"
    TRUNCATED = "TRUNCATED"
    TIMEOUT = "TIMEOUT"
    FATAL = "FATAL"
    STORAGE_FAILURE = "STORAGE_FAILURE"
    UNKNOWN_SEND = "UNKNOWN_SEND"


_EXPLICIT_FAILURE_OUTCOME: Final = {
    TerminalTransitionKindV49C.TIMEOUT: TerminalOutcomeV49C.TIMEOUT,
    TerminalTransitionKindV49C.FATAL: TerminalOutcomeV49C.FATAL,
    TerminalTransitionKindV49C.STORAGE_FAILURE: (TerminalOutcomeV49C.STORAGE_FAILURE),
}


def _enum_value(value: Any, enum_type: type[Enum], *, field: str) -> Enum:
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
    return (
        None if value is None else canonical_identifier(value, field=field, maximum=128)
    )


def _optional_layer(value: Any, *, field: str) -> OutboundObligationLayerV49C | None:
    if value is None:
        return None
    return _enum_value(  # type: ignore[return-value]
        value, OutboundObligationLayerV49C, field=field
    )


def _optional_outcome(value: Any, *, field: str) -> TerminalOutcomeV49C | None:
    if value is None:
        return None
    return _enum_value(value, TerminalOutcomeV49C, field=field)  # type: ignore[return-value]


def _identity(domain: str, payload: Mapping[str, Any]) -> str:
    return sha256_digest(
        {
            "canonicalization_version": CANONICALIZATION_VERSION,
            "domain": domain,
            "payload": dict(payload),
            "schema_version": PHYSICAL_TRANSPORT_TERMINAL_V49C_SCHEMA_VERSION,
        }
    )


def _require_versions(payload: Mapping[str, Any]) -> None:
    if payload["canonicalization_version"] != CANONICALIZATION_VERSION:
        raise CanonicalizationError("unsupported canonicalization_version")
    if payload["schema_version"] != PHYSICAL_TRANSPORT_TERMINAL_V49C_SCHEMA_VERSION:
        raise CanonicalizationError(
            "unsupported physical-transport-terminal V4.9C schema_version"
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class TerminalTransitionPayloadV49C:
    """Canonical reducer input, intended for a top-level actor-event payload."""

    transport_session_id: str
    transition_sequence: int
    parent_terminal_state_id: str
    kind: TerminalTransitionKindV49C
    obligation_layer: OutboundObligationLayerV49C | None = None
    obligation_id: str | None = None
    send_attempt_id: str | None = None
    cause_code: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "transport_session_id",
            canonical_hash(self.transport_session_id, field="transport_session_id"),
        )
        object.__setattr__(
            self,
            "transition_sequence",
            canonical_safe_int(
                self.transition_sequence, field="transition_sequence", minimum=1
            ),
        )
        object.__setattr__(
            self,
            "parent_terminal_state_id",
            canonical_hash(
                self.parent_terminal_state_id, field="parent_terminal_state_id"
            ),
        )
        kind = _enum_value(self.kind, TerminalTransitionKindV49C, field="kind")
        layer = _optional_layer(self.obligation_layer, field="obligation_layer")
        obligation_id = _optional_hash(self.obligation_id, field="obligation_id")
        send_attempt_id = _optional_hash(self.send_attempt_id, field="send_attempt_id")
        cause_code = _optional_identifier(self.cause_code, field="cause_code")
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "obligation_layer", layer)
        object.__setattr__(self, "obligation_id", obligation_id)
        object.__setattr__(self, "send_attempt_id", send_attempt_id)
        object.__setattr__(self, "cause_code", cause_code)
        self._validate_shape()

    def _validate_shape(self) -> None:
        kind = self.kind
        no_wire_fields = (
            self.obligation_layer is None
            and self.obligation_id is None
            and self.send_attempt_id is None
        )
        if kind is TerminalTransitionKindV49C.WS_CLOSE_SENT:
            if (
                self.obligation_layer is not OutboundObligationLayerV49C.WEBSOCKET_CLOSE
                or self.obligation_id is None
                or self.send_attempt_id is not None
                or self.cause_code is not None
            ):
                raise CanonicalizationError(
                    "WS_CLOSE_SENT requires only a WebSocket Close obligation"
                )
            return
        if kind is TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_SENT:
            if (
                self.obligation_layer
                is not OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY
                or self.obligation_id is None
                or self.send_attempt_id is not None
                or self.cause_code is not None
            ):
                raise CanonicalizationError(
                    "TLS_CLOSE_NOTIFY_SENT requires only a TLS notify obligation"
                )
            return
        if kind is TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_PREPARED:
            if (
                self.obligation_layer
                is not OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY
                or self.obligation_id is None
                or self.send_attempt_id is not None
                or self.cause_code is not None
            ):
                raise CanonicalizationError(
                    "TLS_CLOSE_NOTIFY_PREPARED requires only a TLS notify obligation"
                )
            return
        if kind in {
            TerminalTransitionKindV49C.SEND_ATTEMPT_STARTED,
            TerminalTransitionKindV49C.SEND_ATTEMPT_RESOLVED,
        }:
            if (
                self.obligation_layer is None
                or self.obligation_id is None
                or self.send_attempt_id is None
                or self.cause_code is not None
            ):
                raise CanonicalizationError(
                    f"{kind.value} requires layer, obligation, and attempt identities"
                )
            return
        if kind is (
            TerminalTransitionKindV49C.OUTBOUND_OBLIGATION_FULLY_KERNEL_ACCEPTED
        ):
            if (
                self.obligation_layer
                not in {
                    OutboundObligationLayerV49C.WEBSOCKET_CLOSE,
                    OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY,
                }
                or self.obligation_id is None
                or self.send_attempt_id is not None
                or self.cause_code is not None
            ):
                raise CanonicalizationError(
                    "kernel acceptance requires one close-layer obligation"
                )
            return
        if kind in _EXPLICIT_FAILURE_OUTCOME:
            if not no_wire_fields or self.cause_code is None:
                raise CanonicalizationError(
                    f"{kind.value} requires only a non-empty cause_code"
                )
            return
        if kind is TerminalTransitionKindV49C.UNKNOWN_SEND:
            if (
                self.obligation_layer is None
                or self.obligation_id is None
                or self.send_attempt_id is None
                or self.cause_code is None
            ):
                raise CanonicalizationError(
                    "UNKNOWN_SEND requires the unresolved attempt and a cause_code"
                )
            return
        if not no_wire_fields or self.cause_code is not None:
            raise CanonicalizationError(
                f"{kind.value} doesn't accept obligation, attempt, or cause fields"
            )

    def identity_payload(self) -> dict[str, Any]:
        return {
            "cause_code": self.cause_code,
            "kind": self.kind.value,
            "obligation_id": self.obligation_id,
            "obligation_layer": (
                None if self.obligation_layer is None else self.obligation_layer.value
            ),
            "parent_terminal_state_id": self.parent_terminal_state_id,
            "send_attempt_id": self.send_attempt_id,
            "transition_sequence": self.transition_sequence,
            "transport_session_id": self.transport_session_id,
        }

    @property
    def terminal_transition_payload_id(self) -> str:
        return _identity("TerminalTransitionPayloadV49C", self.identity_payload())

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            **self.identity_payload(),
            "schema_version": PHYSICAL_TRANSPORT_TERMINAL_V49C_SCHEMA_VERSION,
            "terminal_transition_payload_id": self.terminal_transition_payload_id,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> TerminalTransitionPayloadV49C:
        expected = set(cls.__dataclass_fields__) | {
            "canonicalization_version",
            "schema_version",
            "terminal_transition_payload_id",
        }
        require_exact_keys(
            payload, expected=expected, context="TerminalTransitionPayloadV49C"
        )
        _require_versions(payload)
        item = cls(**{field: payload[field] for field in cls.__dataclass_fields__})
        provided = canonical_hash(
            payload["terminal_transition_payload_id"],
            field="terminal_transition_payload_id",
        )
        if provided != item.terminal_transition_payload_id:
            raise CanonicalizationError(
                "terminal_transition_payload_id does not match canonical content"
            )
        return item


@dataclass(frozen=True, slots=True, kw_only=True)
class TerminalStateV49C:
    """Canonical snapshot derived from an append-only transition prefix."""

    transport_session_id: str
    transition_sequence: int
    last_transition_payload_id: str | None
    ws_close_sent: bool
    ws_close_received: bool
    ws_output_obligation_id: str | None
    ws_output_fully_kernel_accepted: bool
    ws_send_attempts_resolved: int
    tls_close_notify_sent: bool
    tls_close_notify_received: bool
    tls_close_notify_obligation_id: str | None
    tls_close_notify_fully_kernel_accepted: bool
    tls_send_attempts_resolved: int
    tcp_fin_sent: bool
    tcp_eof_received: bool
    pending_send_attempt_id: str | None
    pending_send_obligation_layer: OutboundObligationLayerV49C | None
    pending_send_obligation_id: str | None
    terminal_outcome: TerminalOutcomeV49C | None
    terminal_cause_code: str | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "transport_session_id",
            canonical_hash(self.transport_session_id, field="transport_session_id"),
        )
        sequence = canonical_safe_int(
            self.transition_sequence, field="transition_sequence", minimum=0
        )
        object.__setattr__(self, "transition_sequence", sequence)
        last_id = _optional_hash(
            self.last_transition_payload_id, field="last_transition_payload_id"
        )
        object.__setattr__(self, "last_transition_payload_id", last_id)
        for field_name in (
            "ws_close_sent",
            "ws_close_received",
            "ws_output_fully_kernel_accepted",
            "tls_close_notify_sent",
            "tls_close_notify_received",
            "tls_close_notify_fully_kernel_accepted",
            "tcp_fin_sent",
            "tcp_eof_received",
        ):
            object.__setattr__(
                self,
                field_name,
                _strict_bool(getattr(self, field_name), field=field_name),
            )
        for field_name in (
            "ws_send_attempts_resolved",
            "tls_send_attempts_resolved",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_safe_int(
                    getattr(self, field_name), field=field_name, minimum=0
                ),
            )
        for field_name in (
            "ws_output_obligation_id",
            "tls_close_notify_obligation_id",
            "pending_send_attempt_id",
            "pending_send_obligation_id",
        ):
            object.__setattr__(
                self,
                field_name,
                _optional_hash(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "pending_send_obligation_layer",
            _optional_layer(
                self.pending_send_obligation_layer,
                field="pending_send_obligation_layer",
            ),
        )
        object.__setattr__(
            self,
            "terminal_outcome",
            _optional_outcome(self.terminal_outcome, field="terminal_outcome"),
        )
        object.__setattr__(
            self,
            "terminal_cause_code",
            _optional_identifier(self.terminal_cause_code, field="terminal_cause_code"),
        )
        self._validate_invariants()

    def _validate_invariants(self) -> None:
        if (self.transition_sequence == 0) != (self.last_transition_payload_id is None):
            raise CanonicalizationError(
                "initial state alone has no last transition payload"
            )
        if self.transition_sequence == 0 and any(
            (
                self.ws_close_sent,
                self.ws_close_received,
                self.ws_output_obligation_id is not None,
                self.ws_output_fully_kernel_accepted,
                self.ws_send_attempts_resolved,
                self.tls_close_notify_sent,
                self.tls_close_notify_received,
                self.tls_close_notify_obligation_id is not None,
                self.tls_close_notify_fully_kernel_accepted,
                self.tls_send_attempts_resolved,
                self.tcp_fin_sent,
                self.tcp_eof_received,
                self.pending_send_attempt_id is not None,
                self.pending_send_obligation_layer is not None,
                self.pending_send_obligation_id is not None,
                self.terminal_outcome is not None,
                self.terminal_cause_code is not None,
            )
        ):
            raise CanonicalizationError(
                "sequence-zero terminal state must be the unique empty state"
            )
        pending_values = (
            self.pending_send_attempt_id,
            self.pending_send_obligation_layer,
            self.pending_send_obligation_id,
        )
        if any(value is None for value in pending_values) and any(
            value is not None for value in pending_values
        ):
            raise CanonicalizationError(
                "pending send attempt, layer, and obligation must be all present or absent"
            )
        if self.ws_close_sent != (self.ws_output_obligation_id is not None):
            raise CanonicalizationError(
                "WebSocket Close state and its output obligation disagree"
            )
        if self.ws_output_fully_kernel_accepted and (
            not self.ws_close_sent or self.ws_send_attempts_resolved < 1
        ):
            raise CanonicalizationError(
                "WebSocket output acceptance requires a resolved send attempt"
            )
        if not self.ws_close_sent and self.ws_send_attempts_resolved:
            raise CanonicalizationError(
                "WebSocket send-attempt evidence exists before Close"
            )
        if self.tls_close_notify_sent and self.tls_close_notify_obligation_id is None:
            raise CanonicalizationError(
                "sent TLS close_notify lacks its prepared output obligation"
            )
        if self.tls_close_notify_obligation_id is not None and not (
            self.ws_close_sent
            and self.ws_close_received
            and self.ws_output_fully_kernel_accepted
        ):
            raise CanonicalizationError(
                "local TLS close_notify preparation requires the completed "
                "WebSocket close handshake"
            )
        if self.tls_close_notify_fully_kernel_accepted and (
            not self.tls_close_notify_sent or self.tls_send_attempts_resolved < 1
        ):
            raise CanonicalizationError(
                "TLS notify acceptance requires a resolved send attempt"
            )
        if (
            self.tls_close_notify_obligation_id is None
            and self.tls_send_attempts_resolved
        ):
            raise CanonicalizationError(
                "TLS send-attempt evidence exists before close_notify preparation"
            )
        if self.tcp_fin_sent and not self.tls_close_notify_fully_kernel_accepted:
            raise CanonicalizationError(
                "TCP FIN requires fully kernel-accepted TLS close_notify ciphertext"
            )
        if self.pending_send_obligation_layer is (
            OutboundObligationLayerV49C.APPLICATION_DATA
        ) and (self.ws_close_sent or self.ws_close_received):
            raise CanonicalizationError(
                "application send cannot remain pending after WebSocket Close"
            )
        if self.pending_send_obligation_layer is (
            OutboundObligationLayerV49C.WEBSOCKET_CLOSE
        ) and (
            not self.ws_close_sent
            or self.pending_send_obligation_id != self.ws_output_obligation_id
            or self.ws_output_fully_kernel_accepted
        ):
            raise CanonicalizationError(
                "pending WebSocket send doesn't match its unaccepted obligation"
            )
        if self.pending_send_obligation_layer is (
            OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY
        ) and (
            self.tls_close_notify_obligation_id is None
            or self.pending_send_obligation_id != self.tls_close_notify_obligation_id
            or self.tls_close_notify_fully_kernel_accepted
        ):
            raise CanonicalizationError(
                "pending TLS send doesn't match its unaccepted obligation"
            )
        if self.tls_close_notify_received and not self.ws_close_received:
            if self.terminal_outcome is not TerminalOutcomeV49C.TRUNCATED:
                raise CanonicalizationError(
                    "peer TLS closure before WebSocket Close must be terminal truncation"
                )
        if self.tcp_eof_received and not self.tls_close_notify_received:
            if self.terminal_outcome is not TerminalOutcomeV49C.TRUNCATED:
                raise CanonicalizationError(
                    "TCP EOF before peer close_notify must be terminal truncation"
                )
        if self.terminal_outcome is None:
            if self.terminal_cause_code is not None:
                raise CanonicalizationError(
                    "nonterminal state cannot carry a terminal cause"
                )
        elif self.terminal_outcome is TerminalOutcomeV49C.CLEAN_ALL_LAYERS:
            if self.terminal_cause_code is not None:
                raise CanonicalizationError("clean state cannot carry a failure cause")
            if not all(
                (
                    self.ws_close_sent,
                    self.ws_close_received,
                    self.ws_output_fully_kernel_accepted,
                    self.tls_close_notify_sent,
                    self.tls_close_notify_received,
                    self.tls_close_notify_fully_kernel_accepted,
                    self.tcp_fin_sent,
                    self.tcp_eof_received,
                )
            ):
                raise CanonicalizationError(
                    "clean state requires complete WebSocket, TLS, and TCP closure"
                )
            if self.pending_send_attempt_id is not None:
                raise CanonicalizationError(
                    "clean state cannot retain an unresolved send attempt"
                )
        else:
            if self.terminal_cause_code is None:
                raise CanonicalizationError(
                    "non-clean terminal state requires a cause_code"
                )
            if (
                self.pending_send_attempt_id is not None
                and self.terminal_outcome is not TerminalOutcomeV49C.UNKNOWN_SEND
            ):
                raise CanonicalizationError(
                    "an unresolved send attempt must terminate as UNKNOWN_SEND"
                )
            if (
                self.terminal_outcome is TerminalOutcomeV49C.UNKNOWN_SEND
                and self.pending_send_attempt_id is None
            ):
                raise CanonicalizationError(
                    "UNKNOWN_SEND must retain the unresolved attempt identity"
                )
            if self.terminal_outcome is TerminalOutcomeV49C.TRUNCATED:
                if self.terminal_cause_code == V49C_TLS_TRUNCATION_CAUSE:
                    if not self.tcp_eof_received or self.tls_close_notify_received:
                        raise CanonicalizationError(
                            "TLS truncation cause requires EOF without close_notify"
                        )
                elif self.terminal_cause_code == V49C_WEBSOCKET_TRUNCATION_CAUSE:
                    if not self.tls_close_notify_received or self.ws_close_received:
                        raise CanonicalizationError(
                            "WebSocket truncation cause requires TLS close without WS Close"
                        )
                else:
                    raise CanonicalizationError(
                        "TRUNCATED state uses an unsupported deterministic cause"
                    )

    @property
    def is_terminal(self) -> bool:
        return self.terminal_outcome is not None

    @property
    def has_pending_send_attempt(self) -> bool:
        return self.pending_send_attempt_id is not None

    @property
    def send_retry_allowed(self) -> bool:
        """Always false after an unresolved attempt or any terminal outcome."""

        return not self.is_terminal and not self.has_pending_send_attempt

    def identity_payload(self) -> dict[str, Any]:
        return {
            "last_transition_payload_id": self.last_transition_payload_id,
            "pending_send_attempt_id": self.pending_send_attempt_id,
            "pending_send_obligation_id": self.pending_send_obligation_id,
            "pending_send_obligation_layer": (
                None
                if self.pending_send_obligation_layer is None
                else self.pending_send_obligation_layer.value
            ),
            "tcp_eof_received": self.tcp_eof_received,
            "tcp_fin_sent": self.tcp_fin_sent,
            "terminal_cause_code": self.terminal_cause_code,
            "terminal_outcome": (
                None if self.terminal_outcome is None else self.terminal_outcome.value
            ),
            "tls_close_notify_fully_kernel_accepted": (
                self.tls_close_notify_fully_kernel_accepted
            ),
            "tls_close_notify_obligation_id": self.tls_close_notify_obligation_id,
            "tls_close_notify_received": self.tls_close_notify_received,
            "tls_close_notify_sent": self.tls_close_notify_sent,
            "tls_send_attempts_resolved": self.tls_send_attempts_resolved,
            "transition_sequence": self.transition_sequence,
            "transport_session_id": self.transport_session_id,
            "ws_close_received": self.ws_close_received,
            "ws_close_sent": self.ws_close_sent,
            "ws_output_fully_kernel_accepted": (self.ws_output_fully_kernel_accepted),
            "ws_output_obligation_id": self.ws_output_obligation_id,
            "ws_send_attempts_resolved": self.ws_send_attempts_resolved,
        }

    @property
    def terminal_state_id(self) -> str:
        return _identity("TerminalStateV49C", self.identity_payload())

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            **self.identity_payload(),
            "schema_version": PHYSICAL_TRANSPORT_TERMINAL_V49C_SCHEMA_VERSION,
            "terminal_state_id": self.terminal_state_id,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> TerminalStateV49C:
        expected = set(cls.__dataclass_fields__) | {
            "canonicalization_version",
            "schema_version",
            "terminal_state_id",
        }
        require_exact_keys(payload, expected=expected, context="TerminalStateV49C")
        _require_versions(payload)
        item = cls(**{field: payload[field] for field in cls.__dataclass_fields__})
        provided = canonical_hash(
            payload["terminal_state_id"], field="terminal_state_id"
        )
        if provided != item.terminal_state_id:
            raise CanonicalizationError(
                "terminal_state_id does not match canonical content"
            )
        return item


def initial_terminal_state_v49c(transport_session_id: str) -> TerminalStateV49C:
    """Return the unique empty state for one canonical transport session."""

    return TerminalStateV49C(
        transport_session_id=transport_session_id,
        transition_sequence=0,
        last_transition_payload_id=None,
        ws_close_sent=False,
        ws_close_received=False,
        ws_output_obligation_id=None,
        ws_output_fully_kernel_accepted=False,
        ws_send_attempts_resolved=0,
        tls_close_notify_sent=False,
        tls_close_notify_received=False,
        tls_close_notify_obligation_id=None,
        tls_close_notify_fully_kernel_accepted=False,
        tls_send_attempts_resolved=0,
        tcp_fin_sent=False,
        tcp_eof_received=False,
        pending_send_attempt_id=None,
        pending_send_obligation_layer=None,
        pending_send_obligation_id=None,
        terminal_outcome=None,
        terminal_cause_code=None,
    )


def validate_application_output_allowed_v49c(state: TerminalStateV49C) -> None:
    """Reject application output once either WebSocket Close is observed."""

    if type(state) is not TerminalStateV49C:
        raise TypeError("state must be exact TerminalStateV49C")
    if state.is_terminal:
        raise PhysicalTransportTerminalV49CStateError(
            "application output is forbidden after terminal classification"
        )
    if state.has_pending_send_attempt:
        raise PhysicalTransportTerminalV49CStateError(
            "application output is forbidden while a send outcome is unresolved"
        )
    if state.ws_close_sent:
        raise PhysicalTransportTerminalV49CStateError(
            "application output is forbidden after WebSocket Close was sent"
        )
    if state.ws_close_received:
        raise PhysicalTransportTerminalV49CStateError(
            "application output is forbidden after WebSocket Close was received"
        )


def _require_matching_pending_attempt(
    state: TerminalStateV49C, transition: TerminalTransitionPayloadV49C
) -> None:
    if (
        transition.send_attempt_id != state.pending_send_attempt_id
        or transition.obligation_layer != state.pending_send_obligation_layer
        or transition.obligation_id != state.pending_send_obligation_id
    ):
        raise PhysicalTransportTerminalV49CStateError(
            "send outcome does not match the unresolved attempt exactly"
        )


def _validate_send_target(
    state: TerminalStateV49C, transition: TerminalTransitionPayloadV49C
) -> None:
    layer = transition.obligation_layer
    if layer is OutboundObligationLayerV49C.APPLICATION_DATA:
        validate_application_output_allowed_v49c(state)
        return
    if layer is OutboundObligationLayerV49C.WEBSOCKET_CLOSE:
        if (
            not state.ws_close_sent
            or transition.obligation_id != state.ws_output_obligation_id
            or state.ws_output_fully_kernel_accepted
        ):
            raise PhysicalTransportTerminalV49CStateError(
                "send attempt doesn't target the pending WebSocket Close obligation"
            )
        return
    if layer is OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY:
        if (
            state.tls_close_notify_obligation_id is None
            or transition.obligation_id != state.tls_close_notify_obligation_id
            or state.tls_close_notify_fully_kernel_accepted
        ):
            raise PhysicalTransportTerminalV49CStateError(
                "send attempt doesn't target the pending TLS notify obligation"
            )
        return
    if layer is OutboundObligationLayerV49C.TLS_OPAQUE_CONTROL:
        return
    raise AssertionError("canonical transition contains an unknown obligation layer")


def advance_terminal_state_v49c(
    state: TerminalStateV49C, transition: TerminalTransitionPayloadV49C
) -> TerminalStateV49C:
    """Apply exactly one canonical append-only transition without side effects."""

    if type(state) is not TerminalStateV49C:
        raise TypeError("state must be exact TerminalStateV49C")
    if type(transition) is not TerminalTransitionPayloadV49C:
        raise TypeError("transition must be exact TerminalTransitionPayloadV49C")
    if state.is_terminal:
        raise PhysicalTransportTerminalV49CStateError(
            "terminal state cannot accept another transition"
        )
    if transition.transport_session_id != state.transport_session_id:
        raise PhysicalTransportTerminalV49CStateError(
            "transition changes transport_session_id"
        )
    if transition.transition_sequence != state.transition_sequence + 1:
        raise PhysicalTransportTerminalV49CStateError(
            "transition_sequence must append exactly one event"
        )
    if transition.parent_terminal_state_id != state.terminal_state_id:
        raise PhysicalTransportTerminalV49CStateError(
            "transition parent doesn't match the current terminal state"
        )
    kind = transition.kind
    if state.has_pending_send_attempt:
        if kind not in {
            TerminalTransitionKindV49C.SEND_ATTEMPT_RESOLVED,
            TerminalTransitionKindV49C.UNKNOWN_SEND,
        }:
            raise PhysicalTransportTerminalV49CStateError(
                "unresolved send permits only its outcome or UNKNOWN_SEND"
            )
        _require_matching_pending_attempt(state, transition)

    changes: dict[str, Any] = {}
    if kind is TerminalTransitionKindV49C.WS_CLOSE_SENT:
        if state.ws_close_sent:
            raise PhysicalTransportTerminalV49CStateError(
                "WebSocket Close was already sent"
            )
        changes.update(
            ws_close_sent=True,
            ws_output_obligation_id=transition.obligation_id,
        )
    elif kind is TerminalTransitionKindV49C.WS_CLOSE_RECEIVED:
        if state.ws_close_received:
            raise PhysicalTransportTerminalV49CStateError(
                "WebSocket Close was already received"
            )
        if state.tls_close_notify_received or state.tcp_eof_received:
            raise PhysicalTransportTerminalV49CStateError(
                "WebSocket Close cannot arrive after peer TLS/TCP closure"
            )
        changes["ws_close_received"] = True
    elif kind is TerminalTransitionKindV49C.SEND_ATTEMPT_STARTED:
        if state.has_pending_send_attempt:
            raise PhysicalTransportTerminalV49CStateError(
                "a send attempt is already unresolved"
            )
        _validate_send_target(state, transition)
        changes.update(
            pending_send_attempt_id=transition.send_attempt_id,
            pending_send_obligation_layer=transition.obligation_layer,
            pending_send_obligation_id=transition.obligation_id,
        )
    elif kind is TerminalTransitionKindV49C.SEND_ATTEMPT_RESOLVED:
        if not state.has_pending_send_attempt:
            raise PhysicalTransportTerminalV49CStateError(
                "no send attempt is awaiting an outcome"
            )
        _require_matching_pending_attempt(state, transition)
        if transition.obligation_layer is OutboundObligationLayerV49C.WEBSOCKET_CLOSE:
            changes["ws_send_attempts_resolved"] = state.ws_send_attempts_resolved + 1
        elif (
            transition.obligation_layer is OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY
        ):
            changes["tls_send_attempts_resolved"] = state.tls_send_attempts_resolved + 1
        changes.update(
            pending_send_attempt_id=None,
            pending_send_obligation_layer=None,
            pending_send_obligation_id=None,
        )
    elif kind is (TerminalTransitionKindV49C.OUTBOUND_OBLIGATION_FULLY_KERNEL_ACCEPTED):
        layer = transition.obligation_layer
        if layer is OutboundObligationLayerV49C.WEBSOCKET_CLOSE:
            if (
                not state.ws_close_sent
                or transition.obligation_id != state.ws_output_obligation_id
                or state.ws_output_fully_kernel_accepted
                or state.ws_send_attempts_resolved < 1
            ):
                raise PhysicalTransportTerminalV49CStateError(
                    "WebSocket Close obligation lacks matching resolved send evidence"
                )
            changes["ws_output_fully_kernel_accepted"] = True
        elif layer is OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY:
            if (
                not state.tls_close_notify_sent
                or transition.obligation_id != state.tls_close_notify_obligation_id
                or state.tls_close_notify_fully_kernel_accepted
                or state.tls_send_attempts_resolved < 1
            ):
                raise PhysicalTransportTerminalV49CStateError(
                    "TLS notify obligation lacks matching resolved send evidence"
                )
            changes["tls_close_notify_fully_kernel_accepted"] = True
        else:
            raise AssertionError("canonical acceptance has an impossible layer")
    elif kind is TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_PREPARED:
        if state.tls_close_notify_obligation_id is not None:
            raise PhysicalTransportTerminalV49CStateError(
                "TLS close_notify was already prepared"
            )
        if not (
            state.ws_close_sent
            and state.ws_close_received
            and state.ws_output_fully_kernel_accepted
        ):
            raise PhysicalTransportTerminalV49CStateError(
                "TLS close_notify preparation requires completed WebSocket Close"
            )
        changes["tls_close_notify_obligation_id"] = transition.obligation_id
    elif kind is TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_SENT:
        if state.tls_close_notify_sent:
            raise PhysicalTransportTerminalV49CStateError(
                "TLS close_notify was already sent"
            )
        if not (
            state.ws_close_sent
            and state.ws_close_received
            and state.ws_output_fully_kernel_accepted
        ):
            raise PhysicalTransportTerminalV49CStateError(
                "TLS close_notify requires both WebSocket Closes and accepted output"
            )
        if state.tls_close_notify_obligation_id is not None:
            if (
                transition.obligation_id != state.tls_close_notify_obligation_id
                or state.tls_send_attempts_resolved < 1
            ):
                raise PhysicalTransportTerminalV49CStateError(
                    "prepared TLS close_notify lacks matching resolved sends"
                )
            changes["tls_close_notify_sent"] = True
        else:
            # Historical V4.9C order registered the obligation with this marker
            # before its send attempts. Keep that exact reducer path valid.
            changes.update(
                tls_close_notify_sent=True,
                tls_close_notify_obligation_id=transition.obligation_id,
            )
    elif kind is TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_RECEIVED:
        if state.tls_close_notify_received:
            raise PhysicalTransportTerminalV49CStateError(
                "TLS close_notify was already received"
            )
        changes["tls_close_notify_received"] = True
        if not state.ws_close_received:
            changes.update(
                terminal_outcome=TerminalOutcomeV49C.TRUNCATED,
                terminal_cause_code=V49C_WEBSOCKET_TRUNCATION_CAUSE,
            )
    elif kind is TerminalTransitionKindV49C.TCP_FIN_SENT:
        if state.tcp_fin_sent:
            raise PhysicalTransportTerminalV49CStateError("TCP FIN was already sent")
        if not state.tls_close_notify_fully_kernel_accepted:
            raise PhysicalTransportTerminalV49CStateError(
                "TCP FIN requires accepted TLS close_notify ciphertext"
            )
        changes["tcp_fin_sent"] = True
    elif kind is TerminalTransitionKindV49C.TCP_EOF_RECEIVED:
        if state.tcp_eof_received:
            raise PhysicalTransportTerminalV49CStateError(
                "TCP EOF was already received"
            )
        changes["tcp_eof_received"] = True
        if not state.tls_close_notify_received:
            changes.update(
                terminal_outcome=TerminalOutcomeV49C.TRUNCATED,
                terminal_cause_code=V49C_TLS_TRUNCATION_CAUSE,
            )
    elif kind is TerminalTransitionKindV49C.CLEAN_ALL_LAYERS:
        if not all(
            (
                state.ws_close_sent,
                state.ws_close_received,
                state.ws_output_fully_kernel_accepted,
                state.tls_close_notify_sent,
                state.tls_close_notify_received,
                state.tls_close_notify_fully_kernel_accepted,
                state.tcp_fin_sent,
                state.tcp_eof_received,
            )
        ):
            raise PhysicalTransportTerminalV49CStateError(
                "CLEAN_ALL_LAYERS requires complete WebSocket, TLS, and TCP closure"
            )
        changes["terminal_outcome"] = TerminalOutcomeV49C.CLEAN_ALL_LAYERS
    elif kind in _EXPLICIT_FAILURE_OUTCOME:
        changes.update(
            terminal_outcome=_EXPLICIT_FAILURE_OUTCOME[kind],
            terminal_cause_code=transition.cause_code,
        )
    elif kind is TerminalTransitionKindV49C.UNKNOWN_SEND:
        if not state.has_pending_send_attempt:
            raise PhysicalTransportTerminalV49CStateError(
                "UNKNOWN_SEND requires an unresolved send attempt"
            )
        _require_matching_pending_attempt(state, transition)
        changes.update(
            terminal_outcome=TerminalOutcomeV49C.UNKNOWN_SEND,
            terminal_cause_code=transition.cause_code,
        )
    else:  # pragma: no cover - enum exhaustiveness guard
        raise AssertionError(f"unhandled terminal transition: {kind.value}")

    return replace(
        state,
        transition_sequence=transition.transition_sequence,
        last_transition_payload_id=transition.terminal_transition_payload_id,
        **changes,
    )


def validate_terminal_transition_v49c(
    state: TerminalStateV49C, transition: TerminalTransitionPayloadV49C
) -> None:
    """Validate one successor edge without returning or mutating state."""

    advance_terminal_state_v49c(state, transition)


def reduce_terminal_transitions_v49c(
    initial_state: TerminalStateV49C,
    transitions: Sequence[TerminalTransitionPayloadV49C],
) -> TerminalStateV49C:
    """Replay an exact ordered transition prefix through the pure reducer."""

    if type(initial_state) is not TerminalStateV49C:
        raise TypeError("initial_state must be exact TerminalStateV49C")
    if isinstance(transitions, (str, bytes, bytearray)) or not isinstance(
        transitions, Sequence
    ):
        raise TypeError("transitions must be an ordered sequence")
    state = initial_state
    for transition in transitions:
        state = advance_terminal_state_v49c(state, transition)
    return state


def terminalize_pending_send_v49c(
    state: TerminalStateV49C,
    *,
    cause_code: str = V49C_RECOVERY_UNKNOWN_SEND_CAUSE,
) -> tuple[TerminalTransitionPayloadV49C, TerminalStateV49C]:
    """Create and apply the sole recovery-safe outcome for a pending send.

    The returned transition must be appended by the caller's durable actor
    journal.  Returning it alongside the state prevents this helper from
    inventing an unlogged state change.
    """

    if type(state) is not TerminalStateV49C:
        raise TypeError("state must be exact TerminalStateV49C")
    if state.is_terminal or not state.has_pending_send_attempt:
        raise PhysicalTransportTerminalV49CStateError(
            "only a nonterminal unresolved send attempt can become UNKNOWN_SEND"
        )
    transition = TerminalTransitionPayloadV49C(
        transport_session_id=state.transport_session_id,
        transition_sequence=state.transition_sequence + 1,
        parent_terminal_state_id=state.terminal_state_id,
        kind=TerminalTransitionKindV49C.UNKNOWN_SEND,
        obligation_layer=state.pending_send_obligation_layer,
        obligation_id=state.pending_send_obligation_id,
        send_attempt_id=state.pending_send_attempt_id,
        cause_code=cause_code,
    )
    return transition, advance_terminal_state_v49c(state, transition)


__all__ = [
    "OutboundObligationLayerV49C",
    "PHYSICAL_TRANSPORT_TERMINAL_V49C_SCHEMA_VERSION",
    "PhysicalTransportTerminalV49CError",
    "PhysicalTransportTerminalV49CStateError",
    "TerminalOutcomeV49C",
    "TerminalStateV49C",
    "TerminalTransitionKindV49C",
    "TerminalTransitionPayloadV49C",
    "V49C_RECOVERY_UNKNOWN_SEND_CAUSE",
    "V49C_TLS_TRUNCATION_CAUSE",
    "V49C_WEBSOCKET_TRUNCATION_CAUSE",
    "V49E_TCP_HALF_CLOSE_ERROR_CAUSE",
    "V49E_TCP_HALF_CLOSE_DEADLINE_EXPIRED_BEFORE_SYSCALL_CAUSE",
    "V49E_TCP_HALF_CLOSE_OUTCOME_UNKNOWN_CAUSE",
    "V49E_LOCAL_SHUTDOWN_COMMAND_DEADLINE_EXPIRED_CAUSE",
    "V49E_LOCAL_SHUTDOWN_CLOCK_DISAGREEMENT_CAUSE",
    "V49E_TERMINAL_CLOSE_INGRESS_DEADLINE_EXPIRED_AFTER_PROGRESS_CAUSE",
    "V49E_TLS_CONTROL_SEND_OUTCOME_UNKNOWN_CAUSE",
    "V49E_TLS_OPERATION_DRIVER_ERROR_CAUSE",
    "V49E_TLS_POST_HANDSHAKE_OUTPUT_AFTER_SHUT_WR_CAUSE",
    "V49E_TLS_SHUTDOWN_DEADLINE_EXPIRED_CAUSE",
    "V49E_TLS_SHUTDOWN_DEADLINE_EXPIRED_AFTER_PROGRESS_CAUSE",
    "advance_terminal_state_v49c",
    "initial_terminal_state_v49c",
    "reduce_terminal_transitions_v49c",
    "terminalize_pending_send_v49c",
    "validate_application_output_allowed_v49c",
    "validate_terminal_transition_v49c",
]

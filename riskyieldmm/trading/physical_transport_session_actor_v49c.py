"""Owner-bound V4.9C transport-session actor controller.

This module is the small serialization boundary between the V4.9C canonical
event contracts and a future live projection/socket adapter.  It deliberately
doesn't expose a socket factory and doesn't claim that constructing this class
grants live authority.  A live adapter must provide both:

* an exact signed ``CommittedBoundTransportSessionV4`` and the owner-minted
  ``DriverHandshakeTransitionV49B`` from the same retained socket; and
* one central journal implementing :class:`TransportActorJournalPortV49C`.

The controller contributes the invariants which cannot safely be split across
subscription and RFC-control paths: one process/thread/event-loop owner, one
``asyncio.Lock``, one append-only actor sequence, one FIFO outbound wire queue,
and a write-ahead kernel-send protocol.  It never retries an attempt whose
outcome wasn't durably recorded.  Recovery classifies that seam as
``UNKNOWN_SEND``.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import inspect
import os
import socket
import threading
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Final, Protocol, TypeAlias

from .canonical import canonical_hash, canonical_safe_int, sha256_digest
from .physical_transport_actor_v49c import (
    V49E_WEBSOCKET_CLOSE_DEADLINE_EXPIRED_CAUSE,
    ActorPayloadV49C,
    KernelSendAttemptPayloadV49C,
    KernelSendFailureKindV49E,
    KernelSendFailurePayloadV49E,
    KernelSendResultPayloadV49C,
    LocalShutdownCommandStartedPayloadV49E,
    LocalShutdownDeadlineClassificationV49E,
    LocalShutdownDeadlineEvidencePayloadV49E,
    OutboundDispatchCompletedPayloadV49C,
    OutboundDispatchDispositionV49C,
    OutboundWireOriginV49C,
    OutboundWirePreparedPayloadV49C,
    ParserTransitionPayloadV49C,
    RawIngressCommittedPayloadV49C,
    TcpHalfCloseAttemptPayloadV49E,
    TcpHalfCloseResultKindV49E,
    TcpHalfCloseResultPayloadV49E,
    TerminalIngressFailureKindV49E,
    TerminalIngressFailurePayloadV49E,
    TlsCiphertextPreparedPayloadV49C,
    TlsControlCiphertextPreparedPayloadV49E,
    TlsControlKernelSendAttemptPayloadV49E,
    TlsControlKernelSendFailurePayloadV49E,
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
    WritePermitConsumedPayloadV49C,
    classify_tls_protocol_operation_failure_v49e,
    derive_actor_write_permit_id_v49c,
    derive_local_shutdown_command_id_v49e,
    derive_local_terminal_command_operation_id_v49e,
    validate_transport_actor_chain_v49c,
)
from .physical_transport_control_v4 import RawIngressCommitV4
from .physical_transport_terminal_v49c import (
    V49C_RECOVERY_UNKNOWN_SEND_CAUSE,
    V49E_LOCAL_SHUTDOWN_CLOCK_DISAGREEMENT_CAUSE,
    V49E_LOCAL_SHUTDOWN_COMMAND_DEADLINE_EXPIRED_CAUSE,
    V49E_TCP_HALF_CLOSE_DEADLINE_EXPIRED_BEFORE_SYSCALL_CAUSE,
    V49E_TCP_HALF_CLOSE_ERROR_CAUSE,
    V49E_TCP_HALF_CLOSE_OUTCOME_UNKNOWN_CAUSE,
    V49E_TERMINAL_CLOSE_INGRESS_DEADLINE_EXPIRED_AFTER_PROGRESS_CAUSE,
    V49E_TLS_CONTROL_SEND_OUTCOME_UNKNOWN_CAUSE,
    V49E_TLS_OPERATION_DRIVER_ERROR_CAUSE,
    V49E_TLS_SHUTDOWN_DEADLINE_EXPIRED_AFTER_PROGRESS_CAUSE,
    V49E_TLS_SHUTDOWN_DEADLINE_EXPIRED_CAUSE,
    OutboundObligationLayerV49C,
    TerminalStateV49C,
    TerminalTransitionKindV49C,
    TerminalTransitionPayloadV49C,
    advance_terminal_state_v49c,
    initial_terminal_state_v49c,
    terminalize_pending_send_v49c,
)

if TYPE_CHECKING:
    from .physical_projection_v4 import (
        ActorAckDeadlineExpiryResultV49E,
        ActorProviderMessageCommitResultV49E,
        ActorTerminalConvergenceResultV49E,
        CommittedActorRawIngressV49C,
    )

_AUTHORITY_FIELDS: Final = (
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
_HASH_AUTHORITY_FIELDS: Final = frozenset(
    name
    for name in _AUTHORITY_FIELDS
    if name not in {"connection_generation", "writer_fence_generation"}
)
_RAW_AUTHORITY_FIELDS: Final = tuple(
    name for name in _AUTHORITY_FIELDS if name != "driver_policy_id"
)
_RECOVERY_RESOLVED_CAUSE: Final = "RECOVERY_RECORDED_SEND_RESULT"
_RECOVERY_PARTIAL_CIPHERTEXT_CAUSE: Final = "RECOVERY_AFTER_PARTIAL_KERNEL_ACCEPTANCE"
_SEND_EFFECT_FAILED_CAUSE: Final = "SEND_EFFECT_WITHOUT_DURABLE_RESULT"
_V49E_TCP_HALF_CLOSE_TOKEN_PREPARATION_ERROR_CAUSE: Final = (
    "TCP_HALF_CLOSE_TOKEN_PREPARATION_ERROR"
)
_AUTHORITY_TOKEN: Final = object()


class PhysicalTransportSessionActorV49CError(RuntimeError):
    """Base error for the bounded V4.9C actor controller."""


class PhysicalTransportSessionActorV49COwnerError(
    PhysicalTransportSessionActorV49CError
):
    """The actor migrated across its process, thread, or event loop."""


class PhysicalTransportSessionActorV49CJournalError(
    PhysicalTransportSessionActorV49CError
):
    """The central journal failed or returned a non-exact result."""


class PhysicalTransportSessionActorV49CFaultLatched(
    PhysicalTransportSessionActorV49CError
):
    """The actor cannot continue after an ambiguous durable/physical seam."""


class PhysicalTransportSessionActorV49CQueueError(
    PhysicalTransportSessionActorV49CError
):
    """An operation attempted to bypass the oldest unresolved wire."""


class LocalShutdownCommandDeadlineDueV49E(PhysicalTransportSessionActorV49CQueueError):
    """Typed, actor-observed command expiry before any requested side effect."""

    def __init__(
        self,
        *,
        local_shutdown_command_started_event_id: str,
        shutdown_deadline_at: datetime,
        shutdown_deadline_monotonic_ns: int,
        observed_at: datetime,
        observed_monotonic_ns: int,
    ) -> None:
        self.local_shutdown_command_started_event_id = canonical_hash(
            local_shutdown_command_started_event_id,
            field="local_shutdown_command_started_event_id",
        )
        self.shutdown_deadline_at = shutdown_deadline_at
        self.shutdown_deadline_monotonic_ns = canonical_safe_int(
            shutdown_deadline_monotonic_ns,
            field="shutdown_deadline_monotonic_ns",
            minimum=1,
        )
        self.observed_at = observed_at
        self.observed_monotonic_ns = canonical_safe_int(
            observed_monotonic_ns,
            field="observed_monotonic_ns",
            minimum=0,
        )
        super().__init__(
            "local shutdown command deadline is due before the requested side effect"
        )


class LocalShutdownCommandClockDisagreementV49E(PhysicalTransportSessionActorV49CError):
    """Wall and BOOTTIME disagree on whether one shutdown command is due."""

    def __init__(
        self,
        *,
        local_shutdown_command_started_event_id: str,
        wall_deadline_due: bool,
        monotonic_deadline_due: bool,
        observed_at: datetime,
        observed_monotonic_ns: int,
    ) -> None:
        self.local_shutdown_command_started_event_id = canonical_hash(
            local_shutdown_command_started_event_id,
            field="local_shutdown_command_started_event_id",
        )
        self.wall_deadline_due = wall_deadline_due
        self.monotonic_deadline_due = monotonic_deadline_due
        self.observed_at = observed_at
        self.observed_monotonic_ns = canonical_safe_int(
            observed_monotonic_ns,
            field="observed_monotonic_ns",
            minimum=0,
        )
        super().__init__(
            "local shutdown wall and BOOTTIME deadline observations disagree"
        )


@dataclass(frozen=True, slots=True, kw_only=True, init=False)
class TransportActorAuthorityV49C:
    """Immutable event authority derived once from the signed owner binding."""

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

    def __init__(self, *, _token: object | None = None, **values: Any) -> None:
        if _token is not _AUTHORITY_TOKEN:
            raise TypeError("actor authority is bound-session-derived only")
        for name in self.__dataclass_fields__:
            object.__setattr__(self, name, values[name])
        for name in _HASH_AUTHORITY_FIELDS:
            object.__setattr__(
                self, name, canonical_hash(getattr(self, name), field=name)
            )
        for name in ("connection_generation", "writer_fence_generation"):
            object.__setattr__(
                self,
                name,
                canonical_safe_int(getattr(self, name), field=name, minimum=1),
            )

    @classmethod
    def from_committed_bound_session(
        cls, *, committed_session: Any, handshake_transition: Any
    ) -> TransportActorAuthorityV49C:
        """Derive authority from the exact owner-committed session pair.

        The local import avoids making the contract-only actor event module
        depend on the Linux/socket implementation.  Exact-type and signature
        checks prevent a structurally similar caller object from granting
        authority.
        """

        from .physical_transport_linux_v4 import DriverHandshakeTransitionV49B
        from .physical_transport_owner_v4 import CommittedBoundTransportSessionV4

        if type(committed_session) is not CommittedBoundTransportSessionV4:
            raise TypeError(
                "committed_session must be exact CommittedBoundTransportSessionV4"
            )
        if type(handshake_transition) is not DriverHandshakeTransitionV49B:
            raise TypeError(
                "handshake_transition must be exact DriverHandshakeTransitionV49B"
            )
        binding = committed_session.binding
        binding.verify_signature()
        snapshot = handshake_transition.owner_snapshot
        snapshot_mismatches = tuple(
            name
            for name in (
                "kernel_boot_id",
                "time_namespace_id",
                "network_namespace_id",
                "socket_cookie_u64",
                "clock_resolution_ns",
                "socket_identity_profile",
                "clock_profile",
            )
            if getattr(binding, name) != getattr(snapshot, name)
        )
        if (
            snapshot_mismatches
            or binding.kernel_socket_identity != snapshot.kernel_socket_identity
            or binding.monotonic_clock_domain_id != snapshot.monotonic_clock_domain_id
        ):
            raise PhysicalTransportSessionActorV49COwnerError(
                "committed binding differs from exact handshake socket/clock owner"
            )
        return cls(
            _token=_AUTHORITY_TOKEN,
            transport_subscription_policy_id=(binding.transport_subscription_policy_id),
            transport_session_id=binding.transport_session_id,
            physical_scope_manifest_id=binding.physical_scope_manifest_id,
            adapter_policy_id=binding.adapter_policy_id,
            capture_partition_id=binding.capture_partition_id,
            socket_lease_id=binding.socket_lease_id,
            connection_generation=binding.connection_generation,
            deployment_bundle_id=binding.deployment_bundle_id,
            writer_fence_token_sha256=binding.writer_fence_token_sha256,
            writer_fence_generation=binding.writer_fence_generation,
            monotonic_clock_domain_id=binding.monotonic_clock_domain_id,
            driver_policy_id=handshake_transition.driver_policy_id,
        )

    @classmethod
    def _from_event(cls, event: TransportActorEventV49C) -> TransportActorAuthorityV49C:
        if type(event) is not TransportActorEventV49C:
            raise TypeError("event must be exact TransportActorEventV49C")
        return cls(
            _token=_AUTHORITY_TOKEN,
            **{name: getattr(event, name) for name in _AUTHORITY_FIELDS},
        )

    def event_fields(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in _AUTHORITY_FIELDS}

    def matches(self, event: TransportActorEventV49C) -> bool:
        return type(event) is TransportActorEventV49C and all(
            getattr(event, name) == getattr(self, name) for name in _AUTHORITY_FIELDS
        )


class TransportActorJournalPortV49C(Protocol):
    """Central durable journal required by the controller.

    ``resolve_exact_committed_raw_actor_event_v49c`` is a capability check, not
    a content lookup.  It must accept only the same in-process event returned by
    the projection transaction which atomically committed RAW ingress and its
    actor event.  Reconstructed/copy-equivalent events aren't live authority.
    """

    async def read_transport_actor_prefix_v49c(
        self, *, transport_session_id: str
    ) -> Sequence[TransportActorEventV49C]: ...

    async def append_actor_raw_ingress_v49c(
        self, *, raw: RawIngressCommitV4
    ) -> CommittedActorRawIngressV49C: ...

    async def resolve_exact_committed_raw_actor_event_v49c(
        self, *, event: TransportActorEventV49C
    ) -> TransportActorEventV49C: ...

    async def append_transport_actor_event_v49c(
        self, *, event: TransportActorEventV49C
    ) -> TransportActorEventV49C: ...

    async def append_transport_actor_events_v49c(
        self, *, events: tuple[TransportActorEventV49C, ...]
    ) -> tuple[TransportActorEventV49C, ...]: ...

    async def commit_actor_provider_message_v49e(
        self,
        *,
        source_parser_event_ids: Sequence[str],
        websocket_opcode: WebSocketOpcodeV49C | str,
        raw_payload: bytes,
        collector_received_at: datetime,
        collector_received_monotonic_ns: int,
        classified_monotonic_ns: int,
        signer: Any,
    ) -> ActorProviderMessageCommitResultV49E: ...

    async def expire_actor_ack_deadline_v49e(
        self,
        *,
        observed_at: datetime,
        observed_monotonic_ns: int,
        signer: Any,
    ) -> ActorAckDeadlineExpiryResultV49E: ...

    async def converge_actor_terminal_v49e(
        self,
        *,
        terminal_event: TransportActorEventV49C,
        signer: Any,
    ) -> ActorTerminalConvergenceResultV49E: ...


KernelSendEffectV49C: TypeAlias = Callable[..., int | Awaitable[int]]
TlsControlSendEffectV49E: TypeAlias = Callable[..., int | Awaitable[int]]
LocalWebSocketClosePrepareEffectV49E: TypeAlias = Callable[..., Any | Awaitable[Any]]
LocalCloseTlsPrepareEffectV49E: TypeAlias = Callable[..., Any | Awaitable[Any]]
TlsControlPrepareEffectV49E: TypeAlias = Callable[..., Any | Awaitable[Any]]
TcpHalfCloseTokenEffectV49E: TypeAlias = Callable[..., Any | Awaitable[Any]]
TcpHalfCloseEffectV49E: TypeAlias = Callable[..., Any | Awaitable[Any]]
TlsShutdownObservationEffectV49E: TypeAlias = Callable[..., Any | Awaitable[Any]]
ActorObservationClockV49C: TypeAlias = Callable[[], tuple[datetime, int]]
ActorObservationBatchClockV49C: TypeAlias = Callable[
    [int], tuple[tuple[datetime, int], ...]
]
ActorTerminalObservationBatchClockV49E: TypeAlias = Callable[
    [int], tuple[tuple[datetime, int], ...]
]
ActorTerminalClockAuthorizerV49E: TypeAlias = Callable[[Any], None]
ActorTerminalClockRestoreAuthorizerV49E: TypeAlias = Callable[
    [tuple[TransportActorEventV49C, ...]], None
]


@dataclass(frozen=True, slots=True, kw_only=True)
class KernelSendOutcomeV49C:
    """Exact durable evidence emitted around one positive ``socket.send``."""

    attempt_event: TransportActorEventV49C
    attempt_started_event: TransportActorEventV49C
    result_event: TransportActorEventV49C
    attempt_resolved_event: TransportActorEventV49C

    @property
    def accepted_octets(self) -> int:
        payload = self.result_event.payload
        assert type(payload) is KernelSendResultPayloadV49C
        return payload.accepted_octets


@dataclass(frozen=True, slots=True, kw_only=True)
class TlsControlSendOutcomeV49E:
    """One exact positive TLS-control write and all durable successors."""

    attempt_event: TransportActorEventV49C
    attempt_started_event: TransportActorEventV49C
    result_event: TransportActorEventV49C
    attempt_resolved_event: TransportActorEventV49C
    tls_close_notify_sent_event: TransportActorEventV49C | None = None
    fully_kernel_accepted_event: TransportActorEventV49C | None = None

    @property
    def accepted_octets(self) -> int:
        payload = self.result_event.payload
        assert type(payload) is TlsControlKernelSendResultPayloadV49E
        return payload.accepted_octets


@dataclass(frozen=True, slots=True, kw_only=True)
class TlsShutdownObservationOutcomeV49E:
    """Exact observation/marker tail and optional signed terminal pair."""

    observation_event: TransportActorEventV49C
    marker_event: TransportActorEventV49C
    terminal_convergence: ActorTerminalConvergenceResultV49E | None = None

    def __post_init__(self) -> None:
        from .physical_projection_v4 import ActorTerminalConvergenceResultV49E

        if (
            type(self.observation_event) is not TransportActorEventV49C
            or self.observation_event.event_kind
            is not TransportActorEventKindV49C.TLS_SHUTDOWN_OBSERVED
            or type(self.marker_event) is not TransportActorEventV49C
            or self.marker_event.event_kind
            is not TransportActorEventKindV49C.TERMINAL_TRANSITION
        ):
            raise TypeError("TLS shutdown outcome requires exact actor events")
        convergence = self.terminal_convergence
        if convergence is not None and (
            type(convergence) is not ActorTerminalConvergenceResultV49E
            or (
                convergence.terminal_event != self.marker_event
                and convergence.terminal_event.previous_event_id
                != self.marker_event.transport_actor_event_id
            )
        ):
            raise TypeError(
                "TLS shutdown terminal outcome requires its exact convergence pair"
            )

    @property
    def termination(self) -> Any | None:
        convergence = self.terminal_convergence
        return None if convergence is None else convergence.termination

    @property
    def terminal_event(self) -> TransportActorEventV49C | None:
        convergence = self.terminal_convergence
        return None if convergence is None else convergence.terminal_event


@dataclass(frozen=True, slots=True, kw_only=True)
class TerminalIngressReadOutcomeV49E:
    """One actor-admitted positive terminal read awaiting exact RAW commit."""

    pending_raw: Any
    received_at: datetime
    received_monotonic_ns: int

    def __post_init__(self) -> None:
        from .physical_transport_tls_v49 import PendingRawIngressV49

        if type(self.pending_raw) is not PendingRawIngressV49:
            raise TypeError("pending_raw must be exact PendingRawIngressV49")
        canonical_safe_int(
            self.received_monotonic_ns,
            field="received_monotonic_ns",
            minimum=0,
        )


class PhysicalTransportSessionActorV49C:
    """Single-owner, single-journal controller for one V4.9C session.

    Construction/restoration is intentionally separate from the live runtime.
    ``restore_bound`` validates an exact signed owner binding but does not open,
    retain, or authorize a socket by itself.
    """

    def __init__(
        self,
        *,
        journal: TransportActorJournalPortV49C,
        authority: TransportActorAuthorityV49C,
        events: Sequence[TransportActorEventV49C],
        observation_clock: ActorObservationClockV49C,
        observation_batch_clock: ActorObservationBatchClockV49C | None = None,
        terminal_observation_batch_clock: (
            ActorTerminalObservationBatchClockV49E | None
        ) = None,
        terminal_clock_authorizer: ActorTerminalClockAuthorizerV49E | None = None,
        terminal_clock_restore_authorizer: (
            ActorTerminalClockRestoreAuthorizerV49E | None
        ) = None,
    ) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError as exc:
            raise PhysicalTransportSessionActorV49COwnerError(
                "actor construction requires one running event loop"
            ) from exc
        if type(authority) is not TransportActorAuthorityV49C:
            raise TypeError("authority must be exact TransportActorAuthorityV49C")
        terminal_owner_seams = (
            terminal_observation_batch_clock,
            terminal_clock_authorizer,
            terminal_clock_restore_authorizer,
        )
        if any(seam is not None for seam in terminal_owner_seams) and not all(
            seam is not None for seam in terminal_owner_seams
        ):
            raise TypeError(
                "terminal owner clock, live authorizer, and restore authorizer "
                "must be supplied as one closed capability set"
            )
        self._journal = journal
        self._authority = authority
        self._observation_clock = observation_clock
        self._observation_batch_clock = observation_batch_clock
        self._terminal_observation_batch_clock = terminal_observation_batch_clock
        self._terminal_clock_authorizer = terminal_clock_authorizer
        self._terminal_clock_restore_authorizer = terminal_clock_restore_authorizer
        self._terminal_evidence_clock_authorized_v49e = False
        self._pid = os.getpid()
        self._thread_id = threading.get_ident()
        self._loop = loop
        self._lock = asyncio.Lock()
        self._storage_fault_latched = False
        self._side_effect_fault_latched = False
        self._fault_reason: str | None = None
        self._events: list[TransportActorEventV49C] = []
        self._events_by_id: dict[str, TransportActorEventV49C] = {}
        self._wire_queue: list[str] = []
        self._wire_queue_octets = 0
        self._terminal_state = initial_terminal_state_v49c(
            authority.transport_session_id
        )
        self._active_permit_event_id: str | None = None
        self._active_tls_event_id: str | None = None
        self._unresolved_attempt_event_id: str | None = None
        self._result_awaiting_terminal_resolution_id: str | None = None
        self._local_shutdown_command_event_id: str | None = None
        self._v49e_prepared_control_capabilities: dict[str, Any] = {}
        self._v49e_pending_terminal_ingress_read: (
            TerminalIngressReadOutcomeV49E | None
        ) = None
        self._last_terminal_convergence_v49e: (
            ActorTerminalConvergenceResultV49E | None
        ) = None
        self._replace_prefix(events)

    @classmethod
    async def restore_bound(
        cls,
        *,
        journal: TransportActorJournalPortV49C,
        committed_session: Any,
        handshake_transition: Any,
        socket_owner: Any,
        terminal_signer: Any | None = None,
        authority: TransportActorAuthorityV49C | None = None,
    ) -> PhysicalTransportSessionActorV49C:
        """Restore one journal prefix against exact retained-owner authority."""

        derived_authority = TransportActorAuthorityV49C.from_committed_bound_session(
            committed_session=committed_session,
            handshake_transition=handshake_transition,
        )
        if authority is None:
            authority = derived_authority
        elif (
            type(authority) is not TransportActorAuthorityV49C
            or authority != derived_authority
        ):
            raise PhysicalTransportSessionActorV49COwnerError(
                "retained actor authority differs from the bound session"
            )
        from .physical_transport_linux_v4 import (
            DriverHandshakeTransitionV49B,
            LinuxSocketOwnerV4,
        )

        if type(handshake_transition) is not DriverHandshakeTransitionV49B:
            raise TypeError(
                "handshake_transition must be exact DriverHandshakeTransitionV49B"
            )
        if type(socket_owner) is not LinuxSocketOwnerV4:
            raise TypeError("socket_owner must be exact LinuxSocketOwnerV4")
        if (
            socket_owner.snapshot() != handshake_transition.owner_snapshot
            or socket_owner.driver_policy_id != handshake_transition.driver_policy_id
        ):
            raise PhysicalTransportSessionActorV49COwnerError(
                "retained socket owner changed after the bound handshake"
            )

        def owner_observation_clock() -> tuple[datetime, int]:
            sample = socket_owner.sample_governed()
            return sample.wall_after_at, sample.boottime_after_ns

        def owner_observation_batch_clock(
            count: int,
        ) -> tuple[tuple[datetime, int], ...]:
            if type(count) is not int or not 2 <= count <= 8:
                raise PhysicalTransportSessionActorV49COwnerError(
                    "owner observation batch count is outside actor bounds"
                )
            sample = socket_owner.sample_governed()
            first = sample.boottime_after_ns - count + 1
            if first < sample.boottime_before_ns:
                raise PhysicalTransportSessionActorV49COwnerError(
                    "governed clock bracket cannot order the actor batch"
                )
            return tuple(
                (sample.wall_after_at, first + index) for index in range(count)
            )

        def owner_terminal_clock_authorizer(evidence: Any) -> None:
            socket_owner._authorize_terminal_actor_clock_from_evidence_v49e(  # noqa: SLF001
                evidence
            )

        def owner_terminal_clock_restore_authorizer(
            events: tuple[TransportActorEventV49C, ...],
        ) -> None:
            socket_owner._restore_terminal_actor_clock_from_chain_v49e(  # noqa: SLF001
                events=events,
            )

        def owner_terminal_observation_batch_clock(
            count: int,
        ) -> tuple[tuple[datetime, int], ...]:
            if type(count) is not int or not 1 <= count <= 8:
                raise PhysicalTransportSessionActorV49COwnerError(
                    "terminal owner observation batch count is outside actor bounds"
                )
            sample = socket_owner.sample_terminal_governed_v49e()
            first = sample.boottime_after_ns - count + 1
            if first < sample.boottime_before_ns:
                raise PhysicalTransportSessionActorV49COwnerError(
                    "terminal governed clock bracket cannot order the actor batch"
                )
            return tuple(
                (sample.wall_after_at, first + index) for index in range(count)
            )

        return await cls._restore(
            journal=journal,
            authority=authority,
            observation_clock=owner_observation_clock,
            observation_batch_clock=owner_observation_batch_clock,
            terminal_observation_batch_clock=(owner_terminal_observation_batch_clock),
            terminal_clock_authorizer=owner_terminal_clock_authorizer,
            terminal_clock_restore_authorizer=(owner_terminal_clock_restore_authorizer),
            terminal_signer=terminal_signer,
        )

    @classmethod
    async def _restore(
        cls,
        *,
        journal: TransportActorJournalPortV49C,
        authority: TransportActorAuthorityV49C,
        observation_clock: ActorObservationClockV49C,
        observation_batch_clock: ActorObservationBatchClockV49C | None = None,
        terminal_observation_batch_clock: (
            ActorTerminalObservationBatchClockV49E | None
        ) = None,
        terminal_clock_authorizer: ActorTerminalClockAuthorizerV49E | None = None,
        terminal_clock_restore_authorizer: (
            ActorTerminalClockRestoreAuthorizerV49E | None
        ) = None,
        terminal_signer: Any | None = None,
    ) -> PhysicalTransportSessionActorV49C:
        """Internal integration/test constructor using already-derived authority."""

        events = await journal.read_transport_actor_prefix_v49c(
            transport_session_id=authority.transport_session_id
        )
        actor = cls(
            journal=journal,
            authority=authority,
            events=events,
            observation_clock=observation_clock,
            observation_batch_clock=observation_batch_clock,
            terminal_observation_batch_clock=terminal_observation_batch_clock,
            terminal_clock_authorizer=terminal_clock_authorizer,
            terminal_clock_restore_authorizer=terminal_clock_restore_authorizer,
        )
        async with actor._lock:
            actor._assert_owner()
            actor._restore_terminal_clock_authorization_v49e()
            await actor._recover_websocket_close_markers_locked()
            await actor._recover_interrupted_send_locked(
                terminal_signer=terminal_signer
            )
            if terminal_signer is not None:
                await actor._recover_terminal_prefix_v49e_locked(signer=terminal_signer)
        return actor

    @property
    def authority(self) -> TransportActorAuthorityV49C:
        return self._authority

    @property
    def events(self) -> tuple[TransportActorEventV49C, ...]:
        return tuple(self._events)

    @property
    def event_count_v49f(self) -> int:
        """Return the constant-cost retained event count at a quiescent boundary."""

        self._assert_owner()
        return len(self._events)

    @property
    def tail_event_id_v49f(self) -> str | None:
        """Return the immutable actor tail identity without copying its history."""

        self._assert_owner()
        return None if not self._events else self._events[-1].transport_actor_event_id

    @property
    def wire_queue_event_count_v49f(self) -> int:
        """Return pending actor wire obligations without exposing their IDs."""

        self._assert_owner()
        return len(self._wire_queue)

    @property
    def wire_queue_octet_count_v49f(self) -> int:
        """Return exact pending WebSocket-wire octets in constant time."""

        self._assert_owner()
        return self._wire_queue_octets

    @property
    def unresolved_kernel_send_attempt_event_id_v49f(self) -> str | None:
        """Return only the actor's currently unresolved kernel attempt."""

        self._assert_owner()
        return self._unresolved_attempt_event_id

    @property
    def terminal_state(self) -> TerminalStateV49C:
        return self._terminal_state

    @property
    def last_terminal_convergence_v49e(
        self,
    ) -> ActorTerminalConvergenceResultV49E | None:
        """Return the exact signed pair produced by this live actor instance."""

        return self._last_terminal_convergence_v49e

    @property
    def oldest_outbound_wire_event_id(self) -> str | None:
        return None if not self._wire_queue else self._wire_queue[0]

    @property
    def outbound_queue_event_ids(self) -> tuple[str, ...]:
        return tuple(self._wire_queue)

    @property
    def local_shutdown_command_event_v49e(self) -> TransportActorEventV49C | None:
        event_id = self._local_shutdown_command_event_id
        return None if event_id is None else self._events_by_id[event_id]

    @property
    def has_pending_automatic_protocol_output(self) -> bool:
        """Whether parser output still owes an oldest-first Pong/Close wire."""

        return self._oldest_pending_automatic_parser_event() is not None

    def _oldest_pending_automatic_parser_event(
        self,
    ) -> TransportActorEventV49C | None:
        """Return the oldest parser output not yet represented by a wire."""

        consumed = {
            event.payload.source_parser_event_id
            for event in self._events
            if event.event_kind is TransportActorEventKindV49C.OUTBOUND_WIRE_PREPARED
            and type(event.payload) is OutboundWirePreparedPayloadV49C
            and event.payload.wire_origin is OutboundWireOriginV49C.AUTOMATIC_PROTOCOL
        }
        return next(
            (
                event
                for event in self._events
                if event.event_kind is TransportActorEventKindV49C.PARSER_TRANSITION
                and type(event.payload) is ParserTransitionPayloadV49C
                and bool(event.payload.ordered_protocol_output_chunks_base64)
                and event.transport_actor_event_id not in consumed
            ),
            None,
        )

    @property
    def is_fault_latched(self) -> bool:
        return (
            self._storage_fault_latched
            or self._side_effect_fault_latched
            or self._terminal_state.is_terminal
        )

    @property
    def fault_reason(self) -> str | None:
        return self._fault_reason

    def _assert_owner(self) -> None:
        if os.getpid() != self._pid:
            raise PhysicalTransportSessionActorV49COwnerError(
                "transport actor cannot migrate across process/fork identity"
            )
        if threading.get_ident() != self._thread_id:
            raise PhysicalTransportSessionActorV49COwnerError(
                "transport actor cannot migrate across thread identity"
            )
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError as exc:
            raise PhysicalTransportSessionActorV49COwnerError(
                "transport actor operation requires its running event loop"
            ) from exc
        if loop is not self._loop:
            raise PhysicalTransportSessionActorV49COwnerError(
                "transport actor cannot migrate across event-loop identity"
            )

    def _assert_progress_allowed(self) -> None:
        if self._storage_fault_latched or self._side_effect_fault_latched:
            raise PhysicalTransportSessionActorV49CFaultLatched(
                self._fault_reason or "transport actor is fault-latched"
            )
        if self._terminal_state.is_terminal:
            raise PhysicalTransportSessionActorV49CFaultLatched(
                "transport actor already has a canonical terminal outcome"
            )

    def _replace_prefix(self, events: Sequence[TransportActorEventV49C]) -> None:
        chain = tuple(events)
        if any(type(event) is not TransportActorEventV49C for event in chain):
            raise PhysicalTransportSessionActorV49CJournalError(
                "journal prefix contains a non-exact actor event"
            )
        retained_prefix = tuple(getattr(self, "_events", ()))
        if retained_prefix and (
            len(chain) < len(retained_prefix)
            or chain[: len(retained_prefix)] != retained_prefix
        ):
            raise PhysicalTransportSessionActorV49CJournalError(
                "journal prefix replacement is not an append-only extension"
            )
        if chain:
            validate_transport_actor_chain_v49c(chain)
            if not all(self._authority.matches(event) for event in chain):
                raise PhysicalTransportSessionActorV49CJournalError(
                    "journal prefix differs from bound actor authority"
                )
        retained_by_id = getattr(self, "_events_by_id", {})
        adopted: list[TransportActorEventV49C] = []
        for event in chain:
            retained = retained_by_id.get(event.transport_actor_event_id)
            if retained is not None:
                if retained != event:
                    raise PhysicalTransportSessionActorV49CJournalError(
                        "journal changed an already retained actor event"
                    )
                # Preserve the in-process capability identity of the unchanged
                # prefix.  Projection may deserialize old rows while appending
                # one fresh tail, but that must not revoke the actor's exact
                # command/cause capabilities.
                event = retained
            adopted.append(event)
        self._events = adopted
        self._rebuild_state()

    def _rebuild_state(self) -> None:
        terminal_clock_was_authorized = self._terminal_evidence_clock_authorized_v49e
        self._events_by_id = {
            event.transport_actor_event_id: event for event in self._events
        }
        self._wire_queue = []
        self._wire_queue_octets = 0
        self._terminal_state = initial_terminal_state_v49c(
            self._authority.transport_session_id
        )
        self._active_permit_event_id = None
        self._active_tls_event_id = None
        self._local_shutdown_command_event_id = None
        self._terminal_evidence_clock_authorized_v49e = terminal_clock_was_authorized
        attempts: dict[str, TransportActorEventV49C] = {}
        results_by_attempt: dict[str, TransportActorEventV49C] = {}

        for event in self._events:
            payload = event.payload
            if event.event_kind is TransportActorEventKindV49C.OUTBOUND_WIRE_PREPARED:
                assert type(payload) is OutboundWirePreparedPayloadV49C
                self._wire_queue.append(event.transport_actor_event_id)
                self._wire_queue_octets += payload.wire_octets
            elif event.event_kind is (
                TransportActorEventKindV49C.LOCAL_SHUTDOWN_COMMAND_STARTED
            ):
                self._local_shutdown_command_event_id = event.transport_actor_event_id
            elif (
                self._terminal_observation_batch_clock is not None
                and self._is_durable_terminal_clock_evidence_v49e(event)
            ):
                self._terminal_evidence_clock_authorized_v49e = True
            elif event.event_kind is TransportActorEventKindV49C.WRITE_PERMIT_CONSUMED:
                self._active_permit_event_id = event.transport_actor_event_id
            elif (
                event.event_kind is TransportActorEventKindV49C.TLS_CIPHERTEXT_PREPARED
            ):
                self._active_tls_event_id = event.transport_actor_event_id
            elif event.event_kind is TransportActorEventKindV49C.KERNEL_SEND_ATTEMPT:
                attempts[event.transport_actor_event_id] = event
            elif event.event_kind is TransportActorEventKindV49C.KERNEL_SEND_RESULT:
                assert type(payload) is KernelSendResultPayloadV49C
                results_by_attempt[payload.kernel_send_attempt_event_id] = event
            elif event.event_kind is TransportActorEventKindV49C.KERNEL_SEND_FAILURE:
                assert type(payload) is KernelSendFailurePayloadV49E
                results_by_attempt[payload.kernel_send_attempt_event_id] = event
            elif event.event_kind is (
                TransportActorEventKindV49C.OUTBOUND_DISPATCH_COMPLETED
            ):
                assert type(payload) is OutboundDispatchCompletedPayloadV49C
                if not self._wire_queue or self._wire_queue[0] != (
                    payload.outbound_wire_prepared_event_id
                ):
                    raise PhysicalTransportSessionActorV49CJournalError(
                        "validated actor chain produced an impossible FIFO state"
                    )
                completed_wire_id = self._wire_queue.pop(0)
                completed_wire = self._events_by_id[completed_wire_id].payload
                assert type(completed_wire) is OutboundWirePreparedPayloadV49C
                self._wire_queue_octets -= completed_wire.wire_octets
                if self._wire_queue_octets < 0:
                    raise PhysicalTransportSessionActorV49CJournalError(
                        "validated actor chain produced negative queued wire octets"
                    )
                self._active_permit_event_id = None
                self._active_tls_event_id = None
            elif event.event_kind is TransportActorEventKindV49C.TERMINAL_TRANSITION:
                assert type(payload) is TerminalTransitionPayloadV49C
                self._terminal_state = advance_terminal_state_v49c(
                    self._terminal_state, payload
                )

        if (not self._wire_queue) != (self._wire_queue_octets == 0):
            raise PhysicalTransportSessionActorV49CJournalError(
                "actor wire queue count and octets disagree"
            )

        unmatched = tuple(
            attempt_id
            for attempt_id in attempts
            if attempt_id not in results_by_attempt
        )
        if len(unmatched) > 1:
            raise PhysicalTransportSessionActorV49CJournalError(
                "journal contains more than one unresolved kernel attempt"
            )
        self._unresolved_attempt_event_id = unmatched[0] if unmatched else None
        self._result_awaiting_terminal_resolution_id = None
        if self._terminal_state.has_pending_send_attempt:
            pending = self._terminal_state.pending_send_attempt_id
            if pending in results_by_attempt:
                self._result_awaiting_terminal_resolution_id = pending
        durable_control_ids = {
            event.transport_actor_event_id
            for event in self._events
            if event.event_kind
            is TransportActorEventKindV49C.TLS_CONTROL_CIPHERTEXT_PREPARED
        }
        self._v49e_prepared_control_capabilities = {
            event_id: capability
            for event_id, capability in self._v49e_prepared_control_capabilities.items()
            if event_id in durable_control_ids
        }

    def _candidate_event_for_prefix(
        self,
        payload: ActorPayloadV49C,
        prefix: Sequence[TransportActorEventV49C],
        *,
        recorded_observation: tuple[datetime, int] | None = None,
    ) -> TransportActorEventV49C:
        kind_by_type = {
            RawIngressCommittedPayloadV49C: (
                TransportActorEventKindV49C.RAW_INGRESS_COMMITTED
            ),
            ParserTransitionPayloadV49C: TransportActorEventKindV49C.PARSER_TRANSITION,
            OutboundWirePreparedPayloadV49C: (
                TransportActorEventKindV49C.OUTBOUND_WIRE_PREPARED
            ),
            WritePermitConsumedPayloadV49C: (
                TransportActorEventKindV49C.WRITE_PERMIT_CONSUMED
            ),
            TlsCiphertextPreparedPayloadV49C: (
                TransportActorEventKindV49C.TLS_CIPHERTEXT_PREPARED
            ),
            KernelSendAttemptPayloadV49C: (
                TransportActorEventKindV49C.KERNEL_SEND_ATTEMPT
            ),
            KernelSendResultPayloadV49C: (
                TransportActorEventKindV49C.KERNEL_SEND_RESULT
            ),
            KernelSendFailurePayloadV49E: (
                TransportActorEventKindV49C.KERNEL_SEND_FAILURE
            ),
            LocalShutdownCommandStartedPayloadV49E: (
                TransportActorEventKindV49C.LOCAL_SHUTDOWN_COMMAND_STARTED
            ),
            LocalShutdownDeadlineEvidencePayloadV49E: (
                TransportActorEventKindV49C.LOCAL_SHUTDOWN_DEADLINE_EVIDENCE
            ),
            TlsProtocolOperationStartedPayloadV49E: (
                TransportActorEventKindV49C.TLS_PROTOCOL_OPERATION_STARTED
            ),
            TerminalIngressFailurePayloadV49E: (
                TransportActorEventKindV49C.TERMINAL_INGRESS_FAILURE
            ),
            TlsProtocolOperationFailedPayloadV49E: (
                TransportActorEventKindV49C.TLS_PROTOCOL_OPERATION_FAILED
            ),
            TlsControlCiphertextPreparedPayloadV49E: (
                TransportActorEventKindV49C.TLS_CONTROL_CIPHERTEXT_PREPARED
            ),
            TlsControlKernelSendAttemptPayloadV49E: (
                TransportActorEventKindV49C.TLS_CONTROL_KERNEL_SEND_ATTEMPT
            ),
            TlsControlKernelSendResultPayloadV49E: (
                TransportActorEventKindV49C.TLS_CONTROL_KERNEL_SEND_RESULT
            ),
            TlsControlKernelSendFailurePayloadV49E: (
                TransportActorEventKindV49C.TLS_CONTROL_KERNEL_SEND_FAILURE
            ),
            TlsShutdownObservedPayloadV49E: (
                TransportActorEventKindV49C.TLS_SHUTDOWN_OBSERVED
            ),
            TcpHalfCloseAttemptPayloadV49E: (
                TransportActorEventKindV49C.TCP_HALF_CLOSE_ATTEMPT
            ),
            TcpHalfCloseResultPayloadV49E: (
                TransportActorEventKindV49C.TCP_HALF_CLOSE_RESULT
            ),
            OutboundDispatchCompletedPayloadV49C: (
                TransportActorEventKindV49C.OUTBOUND_DISPATCH_COMPLETED
            ),
            TerminalTransitionPayloadV49C: (
                TransportActorEventKindV49C.TERMINAL_TRANSITION
            ),
        }
        try:
            event_kind = kind_by_type[type(payload)]
        except KeyError as exc:
            raise TypeError("payload must be an exact V4.9C actor payload") from exc
        prior = tuple(prefix)
        previous = None if not prior else prior[-1].transport_actor_event_id
        recorded_at, recorded_monotonic_ns = (
            self._sample_observation()
            if recorded_observation is None
            else recorded_observation
        )
        event = TransportActorEventV49C.create(
            **self._authority.event_fields(),
            recorded_at=recorded_at,
            recorded_monotonic_ns=recorded_monotonic_ns,
            actor_sequence=len(prior) + 1,
            previous_event_id=previous,
            event_kind=event_kind,
            payload=payload,
        )
        validate_transport_actor_chain_v49c((*prior, event))
        return event

    def _candidate_event(self, payload: ActorPayloadV49C) -> TransportActorEventV49C:
        return self._candidate_event_for_prefix(payload, self._events)

    def _sample_observation(self) -> tuple[datetime, int]:
        terminal_provider = self._terminal_observation_batch_clock
        if (
            self._terminal_evidence_clock_authorized_v49e
            and terminal_provider is not None
        ):
            samples = terminal_provider(1)
            if type(samples) is not tuple or len(samples) != 1:
                raise PhysicalTransportSessionActorV49COwnerError(
                    "terminal owner clock must return one exact observation"
                )
            sample = samples[0]
        else:
            sample = self._observation_clock()
        if type(sample) is not tuple or len(sample) != 2:
            raise PhysicalTransportSessionActorV49COwnerError(
                "owner clock must return one exact (wall, monotonic) pair"
            )
        recorded_at, recorded_monotonic_ns = sample
        if type(recorded_at) is not datetime or type(recorded_monotonic_ns) is not int:
            raise PhysicalTransportSessionActorV49COwnerError(
                "owner clock returned unsupported observation types"
            )
        if self._events:
            previous = self._events[-1]
            if (
                recorded_at < previous.recorded_at
                or recorded_monotonic_ns <= previous.recorded_monotonic_ns
            ):
                raise PhysicalTransportSessionActorV49COwnerError(
                    "owner event clock regressed or failed to advance"
                )
        return recorded_at, recorded_monotonic_ns

    def _sample_observation_batch(self, count: int) -> tuple[tuple[datetime, int], ...]:
        """Obtain bounded ordered event clocks from one governed bracket."""

        checked_count = canonical_safe_int(
            count, field="observation_batch_count", minimum=2, maximum=8
        )
        provider = (
            self._terminal_observation_batch_clock
            if self._terminal_evidence_clock_authorized_v49e
            and self._terminal_observation_batch_clock is not None
            else self._observation_batch_clock
        )
        observations = (
            tuple(self._observation_clock() for _ in range(checked_count))
            if provider is None
            else provider(checked_count)
        )
        if (
            type(observations) is not tuple
            or len(observations) != checked_count
            or any(
                type(item) is not tuple
                or len(item) != 2
                or type(item[0]) is not datetime
                or type(item[1]) is not int
                for item in observations
            )
        ):
            raise PhysicalTransportSessionActorV49COwnerError(
                "owner batch clock returned unsupported observations"
            )
        prior_wall = None if not self._events else self._events[-1].recorded_at
        prior_ns = None if not self._events else self._events[-1].recorded_monotonic_ns
        for wall, monotonic_ns in observations:
            if monotonic_ns < 0 or (
                prior_wall is not None
                and (wall < prior_wall or monotonic_ns <= prior_ns)
            ):
                raise PhysicalTransportSessionActorV49COwnerError(
                    "owner batch clock regressed or failed to advance"
                )
            prior_wall = wall
            prior_ns = monotonic_ns
        return observations

    def _authorize_terminal_clock_after_evidence_v49e(
        self,
        owner_evidence: Any,
    ) -> None:
        """Make terminal clock use irreversible after exact owner evidence."""

        authorizer = self._terminal_clock_authorizer
        if authorizer is not None:
            authorizer(owner_evidence)
        self._terminal_evidence_clock_authorized_v49e = (
            self._terminal_observation_batch_clock is not None
        )

    @staticmethod
    def _is_durable_terminal_clock_evidence_v49e(
        event: TransportActorEventV49C,
    ) -> bool:
        """Identify rows emitted only after live terminal-owner authorization."""

        payload = event.payload
        if type(payload) in {
            TlsShutdownObservedPayloadV49E,
            LocalShutdownDeadlineEvidencePayloadV49E,
            TerminalIngressFailurePayloadV49E,
            TcpHalfCloseResultPayloadV49E,
        }:
            return True
        if type(payload) is not TlsProtocolOperationFailedPayloadV49E:
            return False
        return (
            payload.failure_kind
            is TlsProtocolOperationFailureKindV49E.DEADLINE_EXPIRED_AFTER_PROGRESS
            or payload.failure_kind
            is TlsProtocolOperationFailureKindV49E.UNSENDABLE_POST_HANDSHAKE_OUTPUT_AFTER_SHUT_WR
            or (
                payload.failure_kind
                is TlsProtocolOperationFailureKindV49E.DEADLINE_EXPIRED_NO_OBSERVATION
                and payload.purpose
                is TlsProtocolOperationPurposeV49E.PEER_SHUTDOWN_POLL
            )
        )

    def _restore_terminal_clock_authorization_v49e(self) -> None:
        """Revalidate prior live authority against exact durable evidence."""

        if not self._terminal_evidence_clock_authorized_v49e:
            return
        authorizer = self._terminal_clock_restore_authorizer
        if authorizer is None:
            raise PhysicalTransportSessionActorV49CJournalError(
                "terminal owner clock lacks its exact restore authorizer"
            )
        if not any(
            self._is_durable_terminal_clock_evidence_v49e(event)
            for event in self._events
        ):
            raise PhysicalTransportSessionActorV49CJournalError(
                "terminal clock authorization lacks durable owner evidence"
            )
        authorizer(tuple(self._events))

    @staticmethod
    def _raise_if_local_shutdown_deadline_due_v49e(
        command_event: TransportActorEventV49C,
        observation: tuple[datetime, int],
    ) -> None:
        """Reject a side effect when either exact command clock is already due."""

        command = command_event.payload
        if type(command) is not LocalShutdownCommandStartedPayloadV49E:
            raise TypeError("command_event lacks exact local shutdown payload")
        observed_at, observed_monotonic_ns = observation
        wall_due = observed_at >= command.shutdown_deadline_at
        monotonic_due = observed_monotonic_ns >= command.shutdown_deadline_monotonic_ns
        if wall_due != monotonic_due:
            raise LocalShutdownCommandClockDisagreementV49E(
                local_shutdown_command_started_event_id=(
                    command_event.transport_actor_event_id
                ),
                wall_deadline_due=wall_due,
                monotonic_deadline_due=monotonic_due,
                observed_at=observed_at,
                observed_monotonic_ns=observed_monotonic_ns,
            )
        if wall_due:
            raise LocalShutdownCommandDeadlineDueV49E(
                local_shutdown_command_started_event_id=(
                    command_event.transport_actor_event_id
                ),
                shutdown_deadline_at=command.shutdown_deadline_at,
                shutdown_deadline_monotonic_ns=(command.shutdown_deadline_monotonic_ns),
                observed_at=observed_at,
                observed_monotonic_ns=observed_monotonic_ns,
            )

    async def _converge_local_shutdown_deadline_observation_locked_v49e(
        self,
        command_event: TransportActorEventV49C,
        observation: tuple[datetime, int],
        *,
        signer: Any,
    ) -> None:
        """Accept a before-deadline pair or terminalize its exact due/XOR pair."""

        try:
            self._raise_if_local_shutdown_deadline_due_v49e(
                command_event,
                observation,
            )
        except LocalShutdownCommandDeadlineDueV49E:
            await self._converge_terminal_payload_locked(
                self._terminal_payload(
                    TerminalTransitionKindV49C.TIMEOUT,
                    cause_code=(V49E_LOCAL_SHUTDOWN_COMMAND_DEADLINE_EXPIRED_CAUSE),
                ),
                signer=signer,
                recorded_observation=observation,
            )
            raise
        except LocalShutdownCommandClockDisagreementV49E:
            await self._converge_terminal_payload_locked(
                self._terminal_payload(
                    TerminalTransitionKindV49C.FATAL,
                    cause_code=V49E_LOCAL_SHUTDOWN_CLOCK_DISAGREEMENT_CAUSE,
                ),
                signer=signer,
                recorded_observation=observation,
            )
            raise

    async def _record_owner_no_observation_deadline_locked_v49e(
        self,
        command_event: TransportActorEventV49C,
        owner_evidence: Any,
        *,
        signer: Any,
    ) -> ActorTerminalConvergenceResultV49E:
        """Persist consumed owner-A identity before its deterministic terminal."""

        command = self._require_local_shutdown_command_v49e(command_event)
        self._authorize_terminal_clock_after_evidence_v49e(owner_evidence)
        observed_at, observed_monotonic_ns = self._sample_observation()
        wall_due = observed_at >= command.shutdown_deadline_at
        monotonic_due = observed_monotonic_ns >= command.shutdown_deadline_monotonic_ns
        classification = (
            LocalShutdownDeadlineClassificationV49E.BOTH_DUE
            if wall_due and monotonic_due
            else (
                LocalShutdownDeadlineClassificationV49E.CLOCK_DISAGREEMENT
                if wall_due != monotonic_due
                else LocalShutdownDeadlineClassificationV49E.OWNER_EVIDENCE_BEFORE_BOTH_CLOCKS
            )
        )
        evidence = LocalShutdownDeadlineEvidencePayloadV49E(
            local_shutdown_command_started_event_id=(
                command_event.transport_actor_event_id
            ),
            shutdown_deadline_monotonic_ns=(command.shutdown_deadline_monotonic_ns),
            operation=owner_evidence.operation,
            classification=classification,
            owner_evidence_id=owner_evidence.owner_evidence_id,
            kernel_socket_identity=owner_evidence.kernel_socket_identity,
            driver_evidence_nonce_sha256=(owner_evidence.driver_evidence_nonce_sha256),
            observed_at=observed_at,
            observed_monotonic_ns=observed_monotonic_ns,
        )
        evidence_event = self._candidate_event_for_prefix(
            evidence,
            self._events,
            recorded_observation=(observed_at, observed_monotonic_ns),
        )
        await self._append_candidate_locked(evidence_event)
        terminal_kind, cause = {
            LocalShutdownDeadlineClassificationV49E.BOTH_DUE: (
                TerminalTransitionKindV49C.TIMEOUT,
                V49E_LOCAL_SHUTDOWN_COMMAND_DEADLINE_EXPIRED_CAUSE,
            ),
            LocalShutdownDeadlineClassificationV49E.CLOCK_DISAGREEMENT: (
                TerminalTransitionKindV49C.FATAL,
                V49E_LOCAL_SHUTDOWN_CLOCK_DISAGREEMENT_CAUSE,
            ),
            LocalShutdownDeadlineClassificationV49E.OWNER_EVIDENCE_BEFORE_BOTH_CLOCKS: (
                TerminalTransitionKindV49C.FATAL,
                V49E_TLS_OPERATION_DRIVER_ERROR_CAUSE,
            ),
        }[classification]
        return await self._converge_terminal_payload_locked(
            self._terminal_payload(terminal_kind, cause_code=cause),
            signer=signer,
        )

    async def _append_payload_locked(
        self, payload: ActorPayloadV49C
    ) -> TransportActorEventV49C:
        self._assert_owner()
        self._assert_progress_allowed()
        event = self._candidate_event(payload)
        return await self._append_candidate_locked(event)

    async def _append_candidate_locked(
        self,
        event: TransportActorEventV49C,
    ) -> TransportActorEventV49C:
        """Append one already-clocked exact candidate without resampling time."""

        self._assert_owner()
        self._assert_progress_allowed()
        if type(event) is not TransportActorEventV49C:
            raise TypeError("event must be exact TransportActorEventV49C")
        validate_transport_actor_chain_v49c((*self._events, event))
        try:
            committed = await self._journal.append_transport_actor_event_v49c(
                event=event
            )
        except BaseException as exc:
            self._storage_fault_latched = True
            self._fault_reason = (
                f"journal append outcome is unknown for {event.event_kind.value}"
            )
            if isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)):
                raise
            raise PhysicalTransportSessionActorV49CJournalError(
                self._fault_reason
            ) from exc
        if committed is not event:
            self._storage_fault_latched = True
            self._fault_reason = "journal didn't return the exact appended event"
            raise PhysicalTransportSessionActorV49CJournalError(self._fault_reason)
        self._events.append(event)
        self._rebuild_state()
        return event

    async def _append_candidate_batch_locked(
        self, events: tuple[TransportActorEventV49C, ...]
    ) -> tuple[TransportActorEventV49C, ...]:
        """Commit exact consecutive candidates in one projection transaction."""

        self._assert_owner()
        self._assert_progress_allowed()
        if (
            type(events) is not tuple
            or not 2 <= len(events) <= 8
            or any(type(event) is not TransportActorEventV49C for event in events)
        ):
            raise TypeError("actor batch requires two through eight exact events")
        validate_transport_actor_chain_v49c((*self._events, *events))
        try:
            committed = await self._journal.append_transport_actor_events_v49c(
                events=events
            )
        except BaseException as exc:
            self._storage_fault_latched = True
            self._fault_reason = "journal actor-batch append outcome is unknown"
            if isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)):
                raise
            raise PhysicalTransportSessionActorV49CJournalError(
                self._fault_reason
            ) from exc
        if (
            type(committed) is not tuple
            or len(committed) != len(events)
            or any(
                actual is not expected for actual, expected in zip(committed, events)
            )
        ):
            self._storage_fault_latched = True
            self._fault_reason = "journal didn't return the exact appended actor batch"
            raise PhysicalTransportSessionActorV49CJournalError(self._fault_reason)
        self._events.extend(events)
        self._rebuild_state()
        return events

    async def _adopt_committed_raw_event_locked(
        self, event: TransportActorEventV49C
    ) -> TransportActorEventV49C:
        """Consume one exact RAW hand-off while the actor lock is already held."""

        self._assert_owner()
        self._assert_progress_allowed()
        raw_payload = (
            event.payload
            if type(event) is TransportActorEventV49C
            and event.event_kind is TransportActorEventKindV49C.RAW_INGRESS_COMMITTED
            else None
        )
        if (
            type(event) is not TransportActorEventV49C
            or event.event_kind is not TransportActorEventKindV49C.RAW_INGRESS_COMMITTED
            or type(raw_payload) is not RawIngressCommittedPayloadV49C
            or not raw_payload.receipt.is_store_minted
            or not self._authority.matches(event)
        ):
            raise PhysicalTransportSessionActorV49CJournalError(
                "RAW adoption differs from exact store-minted authority/type"
            )
        expected_sequence = len(self._events) + 1
        expected_previous = (
            None if not self._events else self._events[-1].transport_actor_event_id
        )
        if (
            event.actor_sequence != expected_sequence
            or event.previous_event_id != expected_previous
        ):
            raise PhysicalTransportSessionActorV49CJournalError(
                "RAW adoption isn't the exact next actor event"
            )
        try:
            resolved = await self._journal.resolve_exact_committed_raw_actor_event_v49c(
                event=event
            )
            prefix = tuple(
                await self._journal.read_transport_actor_prefix_v49c(
                    transport_session_id=self._authority.transport_session_id
                )
            )
        except BaseException as exc:
            self._storage_fault_latched = True
            self._fault_reason = "RAW projection adoption couldn't be verified"
            if isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)):
                raise
            raise PhysicalTransportSessionActorV49CJournalError(
                self._fault_reason
            ) from exc
        if resolved is not event:
            raise PhysicalTransportSessionActorV49CJournalError(
                "copied/reconstructed RAW event isn't a live commit capability"
            )
        if (
            not prefix
            or prefix[-1] != event
            or len(prefix) != len(self._events) + 1
            or any(
                reloaded != retained
                for reloaded, retained in zip(prefix[:-1], self._events)
            )
        ):
            self._storage_fault_latched = True
            self._fault_reason = "central journal moved across RAW adoption"
            raise PhysicalTransportSessionActorV49CJournalError(self._fault_reason)
        # The durable read may deserialize the unchanged prefix.  Equality is
        # evidence; object identity remains the actor's live capability.  Keep
        # every retained predecessor and append the exact store-resolved RAW
        # object instead of silently replacing command/cause capabilities.
        self._replace_prefix((*self._events, event))
        return event

    async def adopt_committed_raw_event(
        self, event: TransportActorEventV49C
    ) -> TransportActorEventV49C:
        """Adopt the exact RAW actor event returned by one projection commit."""

        self._assert_owner()
        async with self._lock:
            return await self._adopt_committed_raw_event_locked(event)

    async def commit_and_adopt_raw_ingress_v49d(self, raw: RawIngressCommitV4) -> None:
        """Commit RAW+actor and consume its one-shot hand-off under one lock.

        No RAW event capability escapes this method.  Callers can inspect the
        actor's immutable event snapshot after the exact projection result has
        been verified and adopted.
        """

        self._assert_owner()
        async with self._lock:
            self._assert_owner()
            self._assert_progress_allowed()
            await self._commit_and_adopt_raw_ingress_locked(raw)

    async def _commit_and_adopt_raw_ingress_locked(
        self,
        raw: RawIngressCommitV4,
    ) -> None:
        if type(raw) is not RawIngressCommitV4:
            raise TypeError("raw must be exact RawIngressCommitV4")
        if any(
            getattr(raw, name) != getattr(self._authority, name)
            for name in _RAW_AUTHORITY_FIELDS
        ):
            raise PhysicalTransportSessionActorV49CJournalError(
                "RAW commit differs from bound actor authority"
            )
        try:
            committed = await self._journal.append_actor_raw_ingress_v49c(raw=raw)
        except BaseException as exc:
            self._storage_fault_latched = True
            self._fault_reason = "journal RAW+actor append outcome is unknown"
            if isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)):
                raise
            raise PhysicalTransportSessionActorV49CJournalError(
                self._fault_reason
            ) from exc

        from .physical_projection_v4 import CommittedActorRawIngressV49C

        if (
            type(committed) is not CommittedActorRawIngressV49C
            or committed.raw is not raw
            or committed.event.payload.raw_ingress_commit_id
            != raw.raw_ingress_commit_id
            or committed.event.payload.receipt is not committed.receipt
        ):
            self._storage_fault_latched = True
            self._fault_reason = (
                "journal didn't return the exact fresh RAW+actor commit result"
            )
            raise PhysicalTransportSessionActorV49CJournalError(self._fault_reason)
        await self._adopt_committed_raw_event_locked(committed.event)

    async def read_terminal_close_ingress_v49e(
        self,
        command_event: TransportActorEventV49C,
        *,
        driver_evidence_nonce_sha256: str,
        read_effect: Callable[..., Any | Awaitable[Any]],
        signer: Any,
    ) -> TerminalIngressReadOutcomeV49E:
        """Perform one command-bound terminal read with actor-injected deadline."""

        from .physical_transport_linux_v4 import (
            LinuxSocketOwnerV4DeadlineExpiredAfterProgressV49E,
            LinuxSocketOwnerV4DeadlineExpiredNoObservationV49E,
        )
        from .physical_transport_tls_v49 import PendingRawIngressV49

        self._assert_owner()
        async with self._lock:
            self._assert_progress_allowed()
            command = self._require_local_shutdown_command_v49e(command_event)
            nonce = canonical_hash(
                driver_evidence_nonce_sha256,
                field="driver_evidence_nonce_sha256",
            )
            state = self._terminal_state
            if (
                not callable(read_effect)
                or self._v49e_pending_terminal_ingress_read is not None
                or not state.ws_close_sent
                or not state.ws_output_fully_kernel_accepted
                or state.ws_close_received
                or state.has_pending_send_attempt
            ):
                raise PhysicalTransportSessionActorV49CQueueError(
                    "terminal ingress requires one fully accepted local Close, "
                    "no peer Close, and no pending effect"
                )

            async def terminalize_deadline(
                observed: tuple[datetime, int],
            ) -> None:
                try:
                    self._raise_if_local_shutdown_deadline_due_v49e(
                        command_event,
                        observed,
                    )
                except LocalShutdownCommandDeadlineDueV49E:
                    await self._converge_terminal_payload_locked(
                        self._terminal_payload(
                            TerminalTransitionKindV49C.TIMEOUT,
                            cause_code=(
                                V49E_LOCAL_SHUTDOWN_COMMAND_DEADLINE_EXPIRED_CAUSE
                            ),
                        ),
                        signer=signer,
                        recorded_observation=observed,
                    )
                    raise
                except LocalShutdownCommandClockDisagreementV49E:
                    await self._converge_terminal_payload_locked(
                        self._terminal_payload(
                            TerminalTransitionKindV49C.FATAL,
                            cause_code=V49E_LOCAL_SHUTDOWN_CLOCK_DISAGREEMENT_CAUSE,
                        ),
                        signer=signer,
                        recorded_observation=observed,
                    )
                    raise

            await terminalize_deadline(self._sample_observation())
            try:
                observed = read_effect(
                    deadline_ns=command.shutdown_deadline_monotonic_ns
                )
                pending = await observed if inspect.isawaitable(observed) else observed
            except LinuxSocketOwnerV4DeadlineExpiredNoObservationV49E as exc:
                consumed = exc.consume_for_actor_v49e(
                    transport_session_id=self._authority.transport_session_id,
                    driver_evidence_nonce_sha256=nonce,
                    operation="TERMINAL_CLOSE_INGRESS",
                    deadline_ns=command.shutdown_deadline_monotonic_ns,
                )
                if consumed is not exc:
                    raise PhysicalTransportSessionActorV49CError(
                        "owner substituted terminal-ingress deadline evidence"
                    ) from exc
                await self._record_owner_no_observation_deadline_locked_v49e(
                    command_event,
                    exc,
                    signer=signer,
                )
                raise
            except LinuxSocketOwnerV4DeadlineExpiredAfterProgressV49E as exc:
                consumed = exc.consume_for_actor_v49e(
                    transport_session_id=self._authority.transport_session_id,
                    driver_evidence_nonce_sha256=nonce,
                    operation="TERMINAL_CLOSE_INGRESS",
                    deadline_ns=command.shutdown_deadline_monotonic_ns,
                )
                if consumed is not exc:
                    raise PhysicalTransportSessionActorV49CError(
                        "owner substituted partial terminal-ingress evidence"
                    ) from exc
                self._authorize_terminal_clock_after_evidence_v49e(exc)
                observed_at, observed_monotonic_ns = self._sample_observation()
                wall_due = observed_at >= command.shutdown_deadline_at
                monotonic_due = (
                    observed_monotonic_ns >= command.shutdown_deadline_monotonic_ns
                )
                if not wall_due and not monotonic_due:
                    raise PhysicalTransportSessionActorV49CError(
                        "partial terminal-ingress deadline evidence preceded both "
                        "command clocks"
                    ) from exc
                failure_kind = (
                    TerminalIngressFailureKindV49E.DEADLINE_EXPIRED_AFTER_PROGRESS
                    if wall_due and monotonic_due
                    else TerminalIngressFailureKindV49E.CLOCK_DISAGREEMENT
                )
                failure = TerminalIngressFailurePayloadV49E(
                    local_shutdown_command_started_event_id=(
                        command_event.transport_actor_event_id
                    ),
                    shutdown_deadline_monotonic_ns=(
                        command.shutdown_deadline_monotonic_ns
                    ),
                    failure_kind=failure_kind,
                    operation=exc.operation,
                    owner_evidence_id=exc.owner_evidence_id,
                    driver_evidence_id=exc.driver_evidence_id,
                    kernel_socket_identity=exc.kernel_socket_identity,
                    driver_evidence_nonce_sha256=exc.driver_evidence_nonce_sha256,
                    ciphertext_sha256=exc.ciphertext_sha256,
                    ciphertext_octets_received=exc.ciphertext_octets_received,
                    observed_at=observed_at,
                    observed_monotonic_ns=observed_monotonic_ns,
                )
                failure_event = self._candidate_event_for_prefix(
                    failure,
                    self._events,
                    recorded_observation=(observed_at, observed_monotonic_ns),
                )
                await self._append_candidate_locked(failure_event)
                clock_disagreement = (
                    failure_kind is TerminalIngressFailureKindV49E.CLOCK_DISAGREEMENT
                )
                await self._converge_terminal_payload_locked(
                    self._terminal_payload(
                        (
                            TerminalTransitionKindV49C.FATAL
                            if clock_disagreement
                            else TerminalTransitionKindV49C.TIMEOUT
                        ),
                        cause_code=(
                            V49E_LOCAL_SHUTDOWN_CLOCK_DISAGREEMENT_CAUSE
                            if clock_disagreement
                            else V49E_TERMINAL_CLOSE_INGRESS_DEADLINE_EXPIRED_AFTER_PROGRESS_CAUSE
                        ),
                    ),
                    signer=signer,
                )
                raise

            if (
                type(pending) is not PendingRawIngressV49
                or pending.driver_evidence_nonce_sha256 != nonce
            ):
                raise PhysicalTransportSessionActorV49CError(
                    "owner returned terminal RAW outside the bound driver evidence"
                )
            received = self._sample_observation()
            await terminalize_deadline(received)
            outcome = TerminalIngressReadOutcomeV49E(
                pending_raw=pending,
                received_at=received[0],
                received_monotonic_ns=received[1],
            )
            self._v49e_pending_terminal_ingress_read = outcome
            return outcome

    async def commit_and_adopt_terminal_raw_ingress_v49e(
        self,
        command_event: TransportActorEventV49C,
        outcome: TerminalIngressReadOutcomeV49E,
        raw: RawIngressCommitV4,
        *,
        signer: Any,
    ) -> None:
        """Commit only the exact positive terminal read admitted before cutoff."""

        self._assert_owner()
        async with self._lock:
            self._assert_progress_allowed()
            self._require_local_shutdown_command_v49e(command_event)
            retained = self._v49e_pending_terminal_ingress_read
            pending = None if retained is None else retained.pending_raw
            if (
                type(outcome) is not TerminalIngressReadOutcomeV49E
                or outcome is not retained
                or type(raw) is not RawIngressCommitV4
                or raw.received_at != outcome.received_at
                or raw.received_monotonic_ns != outcome.received_monotonic_ns
                or raw.ingress_sequence != pending.ingress_sequence
            ):
                raise PhysicalTransportSessionActorV49CQueueError(
                    "terminal RAW commit differs from the exact admitted read"
                )
            commit_ready = self._sample_observation()
            try:
                self._raise_if_local_shutdown_deadline_due_v49e(
                    command_event,
                    commit_ready,
                )
            except LocalShutdownCommandDeadlineDueV49E:
                self._v49e_pending_terminal_ingress_read = None
                await self._converge_terminal_payload_locked(
                    self._terminal_payload(
                        TerminalTransitionKindV49C.TIMEOUT,
                        cause_code=(V49E_LOCAL_SHUTDOWN_COMMAND_DEADLINE_EXPIRED_CAUSE),
                    ),
                    signer=signer,
                    recorded_observation=commit_ready,
                )
                raise
            except LocalShutdownCommandClockDisagreementV49E:
                self._v49e_pending_terminal_ingress_read = None
                await self._converge_terminal_payload_locked(
                    self._terminal_payload(
                        TerminalTransitionKindV49C.FATAL,
                        cause_code=V49E_LOCAL_SHUTDOWN_CLOCK_DISAGREEMENT_CAUSE,
                    ),
                    signer=signer,
                    recorded_observation=commit_ready,
                )
                raise
            await self._commit_and_adopt_raw_ingress_locked(raw)
            self._v49e_pending_terminal_ingress_read = None

    async def append_parser_transition(
        self, payload: ParserTransitionPayloadV49C
    ) -> TransportActorEventV49C:
        self._assert_owner()
        async with self._lock:
            event = await self._append_payload_locked(payload)
            if (
                payload.frame is not None
                and payload.frame.opcode is WebSocketOpcodeV49C.CLOSE
            ):
                await self._append_payload_locked(
                    self._terminal_payload(TerminalTransitionKindV49C.WS_CLOSE_RECEIVED)
                )
            return event

    async def append_parser_transition_v49d(
        self, payload: ParserTransitionPayloadV49C
    ) -> TransportActorEventV49C:
        """Append a parser transition and any Close marker atomically.

        Ordinary parser transitions remain a single journal event.  An inbound
        Close is one indivisible ``(parser, WS_CLOSE_RECEIVED)`` batch, so no
        crash prefix can expose a parsed Close without its terminal evidence.
        """

        self._assert_owner()
        async with self._lock:
            self._assert_owner()
            self._assert_progress_allowed()
            if type(payload) is not ParserTransitionPayloadV49C:
                raise TypeError("payload must be exact ParserTransitionPayloadV49C")
            if (
                payload.frame is None
                or payload.frame.opcode is not WebSocketOpcodeV49C.CLOSE
            ):
                return await self._append_payload_locked(payload)

            observations = self._sample_observation_batch(2)
            parser_event = self._candidate_event_for_prefix(
                payload,
                self._events,
                recorded_observation=observations[0],
            )
            close_received_event = self._candidate_event_for_prefix(
                self._terminal_payload(TerminalTransitionKindV49C.WS_CLOSE_RECEIVED),
                (*self._events, parser_event),
                recorded_observation=observations[1],
            )
            committed = await self._append_candidate_batch_locked(
                (parser_event, close_received_event)
            )
            return committed[0]

    async def commit_completed_application_message_v49e(
        self,
        *,
        source_parser_event_ids: Sequence[str],
        websocket_opcode: WebSocketOpcodeV49C | str,
        raw_payload: bytes,
        collector_received_at: datetime,
        collector_received_monotonic_ns: int,
        classified_monotonic_ns: int,
        signer: Any,
    ) -> ActorProviderMessageCommitResultV49E:
        """Atomically adopt projection-derived capture/classification/ACK edges."""

        self._assert_owner()
        async with self._lock:
            self._assert_owner()
            self._assert_progress_allowed()
            old_prefix = tuple(self._events)
            try:
                result = await self._journal.commit_actor_provider_message_v49e(
                    source_parser_event_ids=source_parser_event_ids,
                    websocket_opcode=websocket_opcode,
                    raw_payload=raw_payload,
                    collector_received_at=collector_received_at,
                    collector_received_monotonic_ns=(collector_received_monotonic_ns),
                    classified_monotonic_ns=classified_monotonic_ns,
                    signer=signer,
                )
                from .physical_projection_v4 import (
                    ActorProviderMessageCommitResultV49E,
                )

                if type(result) is not ActorProviderMessageCommitResultV49E:
                    raise PhysicalTransportSessionActorV49CJournalError(
                        "journal returned an unsupported V4.9E provider result"
                    )
                if result.ack_event is not None:
                    new_events = (result.application_event, result.ack_event)
                elif result.provider_failure_event is not None:
                    new_events = (
                        result.application_event,
                        result.provider_failure_event,
                    )
                else:
                    new_events = (result.application_event,)
                if any(
                    type(event) is not TransportActorEventV49C
                    or not self._authority.matches(event)
                    for event in new_events
                ) or (
                    result.termination is not None
                    and result.termination.transport_session_id
                    != self._authority.transport_session_id
                ):
                    raise PhysicalTransportSessionActorV49CJournalError(
                        "V4.9E provider result changes actor authority or type"
                    )
                durable_prefix = tuple(
                    await self._journal.read_transport_actor_prefix_v49c(
                        transport_session_id=self._authority.transport_session_id
                    )
                )
                if (
                    durable_prefix[: len(old_prefix)] != old_prefix
                    or durable_prefix[len(old_prefix) :] != new_events
                ):
                    raise PhysicalTransportSessionActorV49CJournalError(
                        "V4.9E provider result is not the exact durable actor tail"
                    )
                self._replace_prefix(durable_prefix)
                return result
            except BaseException as exc:
                self._storage_fault_latched = True
                self._fault_reason = (
                    "journal V4.9E provider-message transaction outcome is unknown"
                )
                if isinstance(
                    exc, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)
                ):
                    raise
                if isinstance(exc, PhysicalTransportSessionActorV49CJournalError):
                    raise
                raise PhysicalTransportSessionActorV49CJournalError(
                    self._fault_reason
                ) from exc

    async def expire_ack_deadline_v49e(
        self,
        *,
        observed_at: datetime,
        observed_monotonic_ns: int,
        signer: Any,
    ) -> ActorAckDeadlineExpiryResultV49E:
        """Atomically adopt the deadline, TIMEOUT and signed termination."""

        self._assert_owner()
        async with self._lock:
            self._assert_owner()
            self._assert_progress_allowed()
            old_prefix = tuple(self._events)
            try:
                result = await self._journal.expire_actor_ack_deadline_v49e(
                    observed_at=observed_at,
                    observed_monotonic_ns=observed_monotonic_ns,
                    signer=signer,
                )
                from .physical_projection_v4 import ActorAckDeadlineExpiryResultV49E

                if type(result) is not ActorAckDeadlineExpiryResultV49E:
                    raise PhysicalTransportSessionActorV49CJournalError(
                        "journal returned an unsupported V4.9E ACK-timeout result"
                    )
                new_events = (result.deadline_event, result.terminal_event)
                if any(
                    type(event) is not TransportActorEventV49C
                    or not self._authority.matches(event)
                    for event in new_events
                ):
                    raise PhysicalTransportSessionActorV49CJournalError(
                        "V4.9E ACK-timeout result changes actor authority or type"
                    )
                durable_prefix = tuple(
                    await self._journal.read_transport_actor_prefix_v49c(
                        transport_session_id=self._authority.transport_session_id
                    )
                )
                if (
                    durable_prefix[: len(old_prefix)] != old_prefix
                    or durable_prefix[len(old_prefix) :] != new_events
                ):
                    raise PhysicalTransportSessionActorV49CJournalError(
                        "V4.9E ACK-timeout result is not the exact durable tail"
                    )
                self._replace_prefix(durable_prefix)
                return result
            except BaseException as exc:
                self._storage_fault_latched = True
                self._fault_reason = (
                    "journal V4.9E ACK-timeout transaction outcome is unknown"
                )
                if isinstance(
                    exc, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)
                ):
                    raise
                if isinstance(exc, PhysicalTransportSessionActorV49CJournalError):
                    raise
                raise PhysicalTransportSessionActorV49CJournalError(
                    self._fault_reason
                ) from exc

    async def prepare_outbound_wire(
        self, payload: OutboundWirePreparedPayloadV49C
    ) -> TransportActorEventV49C:
        """Append one automatic or application wire to the shared FIFO."""

        self._assert_owner()
        async with self._lock:
            if payload.wire_origin is (OutboundWireOriginV49C.LOCAL_TERMINAL_COMMAND):
                raise PhysicalTransportSessionActorV49CQueueError(
                    "local terminal command requires atomic V4.9E authorization"
                )
            if payload.wire_origin is OutboundWireOriginV49C.APPLICATION_INTENT and (
                self._terminal_state.ws_close_sent
                or self._terminal_state.ws_close_received
            ):
                raise PhysicalTransportSessionActorV49CQueueError(
                    "application output is forbidden after WebSocket Close"
                )
            event = await self._append_payload_locked(payload)
            if payload.logical_opcode is WebSocketOpcodeV49C.CLOSE:
                await self._append_payload_locked(
                    self._terminal_payload(
                        TerminalTransitionKindV49C.WS_CLOSE_SENT,
                        obligation_layer=(OutboundObligationLayerV49C.WEBSOCKET_CLOSE),
                        obligation_id=payload.outbound_operation_id,
                    )
                )
            return event

    def _write_permit_for_wire(
        self,
        wire_event: TransportActorEventV49C,
        *,
        consumed_at: datetime,
        consumed_monotonic_ns: int,
    ) -> WritePermitConsumedPayloadV49C:
        """Derive the sole deterministic one-shot permit for a prepared wire."""

        wire_payload = wire_event.payload
        if (
            type(wire_event) is not TransportActorEventV49C
            or wire_event.event_kind
            is not TransportActorEventKindV49C.OUTBOUND_WIRE_PREPARED
            or type(wire_payload) is not OutboundWirePreparedPayloadV49C
        ):
            raise TypeError("wire_event must be one exact prepared-wire event")
        return WritePermitConsumedPayloadV49C(
            outbound_wire_prepared_event_id=wire_event.transport_actor_event_id,
            permit_id=derive_actor_write_permit_id_v49c(
                outbound_operation_id=wire_payload.outbound_operation_id,
                outbound_wire_prepared_event_id=(wire_event.transport_actor_event_id),
                socket_lease_id=self._authority.socket_lease_id,
                writer_fence_token_sha256=(self._authority.writer_fence_token_sha256),
                writer_fence_generation=self._authority.writer_fence_generation,
            ),
            one_shot_attempt_ordinal=1,
            wire_batch_sha256=wire_payload.wire_batch_sha256,
            wire_octets=wire_payload.wire_octets,
            consumed_at=consumed_at,
            consumed_monotonic_ns=consumed_monotonic_ns,
            send_not_after=wire_payload.send_not_after,
            send_not_after_monotonic_ns=(wire_payload.send_not_after_monotonic_ns),
        )

    async def prepare_application_wire_and_permit(
        self,
        wire_payload: OutboundWirePreparedPayloadV49C,
        *,
        permit_consumed_at: datetime,
        permit_consumed_monotonic_ns: int,
    ) -> tuple[
        TransportActorEventV49C,
        TransportActorEventV49C,
    ]:
        """Atomically persist an application wire and its one-shot permit.

        TLS state must not advance until this pair is durable.  A crash after
        this boundary can therefore abandon the permit without ever hiding a
        prepared TLS artifact or a kernel side effect.
        """

        self._assert_owner()
        async with self._lock:
            self._assert_owner()
            self._assert_progress_allowed()
            if (
                type(wire_payload) is not OutboundWirePreparedPayloadV49C
                or wire_payload.wire_origin
                is not OutboundWireOriginV49C.APPLICATION_INTENT
                or self.oldest_outbound_wire_event_id is not None
                or self.has_pending_automatic_protocol_output
                or self._terminal_state.ws_close_sent
                or self._terminal_state.ws_close_received
            ):
                raise PhysicalTransportSessionActorV49CQueueError(
                    "application preparation requires an idle open actor FIFO"
                )
            observations = self._sample_observation_batch(2)
            wire_event = self._candidate_event_for_prefix(
                wire_payload,
                self._events,
                recorded_observation=observations[0],
            )
            permit_payload = self._write_permit_for_wire(
                wire_event,
                consumed_at=permit_consumed_at,
                consumed_monotonic_ns=permit_consumed_monotonic_ns,
            )
            permit_event = self._candidate_event_for_prefix(
                permit_payload,
                (*self._events, wire_event),
                recorded_observation=observations[1],
            )
            committed = await self._append_candidate_batch_locked(
                (wire_event, permit_event)
            )
            return committed

    async def start_local_shutdown_command_v49e(
        self,
        *,
        timeout_seconds: int,
    ) -> TransportActorEventV49C:
        """Persist one shutdown horizon before any owner mutation is authorized."""

        self._assert_owner()
        async with self._lock:
            self._assert_progress_allowed()
            timeout = canonical_safe_int(
                timeout_seconds,
                field="timeout_seconds",
                minimum=1,
                maximum=300,
            )
            state = self._terminal_state
            peer_first = (
                state.ws_close_sent
                and state.ws_close_received
                and state.ws_output_fully_kernel_accepted
            )
            if (
                self._local_shutdown_command_event_id is not None
                or self.oldest_outbound_wire_event_id is not None
                or self.has_pending_automatic_protocol_output
                or state.pending_send_attempt_id is not None
                or (
                    any(
                        (
                            state.ws_close_sent,
                            state.ws_close_received,
                            state.ws_output_fully_kernel_accepted,
                        )
                    )
                    and not peer_first
                )
                or any(
                    (
                        state.tls_close_notify_sent,
                        state.tls_close_notify_received,
                        state.tls_close_notify_fully_kernel_accepted,
                        state.tcp_fin_sent,
                        state.tcp_eof_received,
                    )
                )
            ):
                raise PhysicalTransportSessionActorV49CQueueError(
                    "shutdown command requires one quiescent OPEN or completed "
                    "peer-first WebSocket state"
                )
            started_at, started_monotonic_ns = self._sample_observation()
            deadline_at = started_at + timedelta(seconds=timeout)
            deadline_ns = started_monotonic_ns + timeout * 1_000_000_000
            predecessor = (
                None if not self._events else self._events[-1].transport_actor_event_id
            )
            command_id = derive_local_shutdown_command_id_v49e(
                transport_session_id=self._authority.transport_session_id,
                actor_predecessor_event_id=predecessor,
                timeout_seconds=timeout,
                started_at=started_at,
                started_monotonic_ns=started_monotonic_ns,
                deadline_at=deadline_at,
                deadline_monotonic_ns=deadline_ns,
            )
            payload = LocalShutdownCommandStartedPayloadV49E(
                local_shutdown_command_id=command_id,
                websocket_close_code=1000,
                websocket_close_reason_sha256=hashlib.sha256(b"").hexdigest(),
                websocket_close_reason_octets=0,
                websocket_close_payload_sha256=hashlib.sha256(
                    (1000).to_bytes(2, "big")
                ).hexdigest(),
                websocket_close_payload_octets=2,
                timeout_seconds=timeout,
                started_at=started_at,
                started_monotonic_ns=started_monotonic_ns,
                shutdown_deadline_at=deadline_at,
                shutdown_deadline_monotonic_ns=deadline_ns,
            )
            event = self._candidate_event_for_prefix(
                payload,
                self._events,
                recorded_observation=(started_at, started_monotonic_ns),
            )
            return await self._append_candidate_locked(event)

    async def authorize_local_websocket_close_v49e(
        self,
        command_event: TransportActorEventV49C,
        *,
        driver_evidence_nonce_sha256: str,
        prepare_effect: LocalWebSocketClosePrepareEffectV49E,
        signer: Any,
    ) -> tuple[
        TransportActorEventV49C,
        TransportActorEventV49C,
        TransportActorEventV49C,
    ]:
        """Prepare and durably authorize the fixed local Close under one deadline.

        The caller supplies the retained-owner operation, not prepared bytes.
        The actor injects the sole command BOOTTIME deadline into that operation;
        therefore a caller closure cannot prepare the positive path under a
        different horizon and later present an otherwise matching artifact.
        """

        from .physical_transport_linux_v4 import (
            LinuxSocketOwnerV4DeadlineExpiredNoObservationV49E,
        )
        from .physical_transport_tls_v49 import PreparedWebSocketWireV49C

        self._assert_owner()
        async with self._lock:
            self._assert_progress_allowed()
            self._require_exact_actor_event(
                command_event,
                TransportActorEventKindV49C.LOCAL_SHUTDOWN_COMMAND_STARTED,
            )
            if (
                command_event.transport_actor_event_id
                != self._local_shutdown_command_event_id
            ):
                raise PhysicalTransportSessionActorV49CQueueError(
                    "local Close requires the exact retained shutdown command"
                )
            command = command_event.payload
            assert type(command) is LocalShutdownCommandStartedPayloadV49E
            nonce = canonical_hash(
                driver_evidence_nonce_sha256,
                field="driver_evidence_nonce_sha256",
            )
            normal_payload = (1000).to_bytes(2, "big")
            if (
                not callable(prepare_effect)
                or self.oldest_outbound_wire_event_id is not None
                or self.has_pending_automatic_protocol_output
                or not self._events
                or self._events[-1] is not command_event
                or self._terminal_state.ws_close_sent
                or self._terminal_state.ws_close_received
            ):
                raise PhysicalTransportSessionActorV49CQueueError(
                    "local fixed Close authorization requires exact owner output "
                    "and one idle open FIFO"
                )
            effect_ready = self._sample_observation()
            await self._converge_local_shutdown_deadline_observation_locked_v49e(
                command_event,
                effect_ready,
                signer=signer,
            )
            try:
                observed = prepare_effect(
                    deadline_ns=command.shutdown_deadline_monotonic_ns
                )
                prepared_wire = (
                    await observed if inspect.isawaitable(observed) else observed
                )
                if (
                    type(prepared_wire) is not PreparedWebSocketWireV49C
                    or prepared_wire.logical_opcode != 0x8
                    or prepared_wire.logical_payload_octets != len(normal_payload)
                    or prepared_wire.logical_payload_sha256
                    != hashlib.sha256(normal_payload).hexdigest()
                ):
                    raise PhysicalTransportSessionActorV49CQueueError(
                        "owner changed the fixed local normal Close artifact"
                    )
                observations = self._sample_observation_batch(3)
                # Authorization is still an actor mutation.  Reject the whole
                # batch before any durable positive evidence when it crosses.
                await self._converge_local_shutdown_deadline_observation_locked_v49e(
                    command_event,
                    observations[-1],
                    signer=signer,
                )
                if (
                    observations[0][0] < effect_ready[0]
                    or observations[0][1] <= effect_ready[1]
                ):
                    raise PhysicalTransportSessionActorV49COwnerError(
                        "local Close authorization clock didn't follow effect gate"
                    )
            except LinuxSocketOwnerV4DeadlineExpiredNoObservationV49E as exc:
                consumed = exc.consume_for_actor_v49e(
                    transport_session_id=self._authority.transport_session_id,
                    driver_evidence_nonce_sha256=nonce,
                    operation="LOCAL_WEBSOCKET_CLOSE_PREPARATION",
                    deadline_ns=command.shutdown_deadline_monotonic_ns,
                )
                if consumed is not exc:
                    raise PhysicalTransportSessionActorV49CError(
                        "owner substituted local-Close preparation evidence"
                    ) from exc
                await self._record_owner_no_observation_deadline_locked_v49e(
                    command_event,
                    exc,
                    signer=signer,
                )
                raise
            except (
                LocalShutdownCommandDeadlineDueV49E,
                LocalShutdownCommandClockDisagreementV49E,
            ):
                raise
            except BaseException:
                if not self._terminal_state.is_terminal:
                    await self._converge_terminal_payload_locked(
                        self._terminal_payload(
                            TerminalTransitionKindV49C.FATAL,
                            cause_code=V49E_TLS_OPERATION_DRIVER_ERROR_CAUSE,
                        ),
                        signer=signer,
                    )
                raise
            operation_id = derive_local_terminal_command_operation_id_v49e(
                transport_session_id=self._authority.transport_session_id,
                actor_predecessor_event_id=(
                    None
                    if not self._events
                    else self._events[-1].transport_actor_event_id
                ),
                logical_payload_sha256=prepared_wire.logical_payload_sha256,
                logical_payload_octets=prepared_wire.logical_payload_octets,
                ordered_wire_chunks_sha256=(prepared_wire.ordered_wire_chunks_sha256),
                wire_batch_sha256=prepared_wire.wire_batch_sha256,
                wire_octets=prepared_wire.wire_octets,
            )
            wire_payload = OutboundWirePreparedPayloadV49C(
                outbound_operation_id=operation_id,
                wire_origin=OutboundWireOriginV49C.LOCAL_TERMINAL_COMMAND,
                source_parser_event_id=None,
                logical_opcode=WebSocketOpcodeV49C.CLOSE,
                logical_payload_sha256=prepared_wire.logical_payload_sha256,
                logical_payload_octets=prepared_wire.logical_payload_octets,
                ordered_wire_chunks_base64=tuple(
                    base64.b64encode(chunk).decode("ascii")
                    for chunk in prepared_wire.ordered_wire_chunks
                ),
                ordered_wire_chunks_sha256=(prepared_wire.ordered_wire_chunks_sha256),
                wire_batch_sha256=prepared_wire.wire_batch_sha256,
                wire_octets=prepared_wire.wire_octets,
                prepared_at=observations[0][0],
                prepared_monotonic_ns=observations[0][1],
                send_not_after=command.shutdown_deadline_at,
                send_not_after_monotonic_ns=(command.shutdown_deadline_monotonic_ns),
            )
            wire_event = self._candidate_event_for_prefix(
                wire_payload,
                self._events,
                recorded_observation=observations[0],
            )
            close_payload = self._terminal_payload(
                TerminalTransitionKindV49C.WS_CLOSE_SENT,
                obligation_layer=OutboundObligationLayerV49C.WEBSOCKET_CLOSE,
                obligation_id=operation_id,
            )
            close_event = self._candidate_event_for_prefix(
                close_payload,
                (*self._events, wire_event),
                recorded_observation=observations[1],
            )
            permit_payload = self._write_permit_for_wire(
                wire_event,
                consumed_at=observations[2][0],
                consumed_monotonic_ns=observations[2][1],
            )
            permit_event = self._candidate_event_for_prefix(
                permit_payload,
                (*self._events, wire_event, close_event),
                recorded_observation=observations[2],
            )
            committed = await self._append_candidate_batch_locked(
                (wire_event, close_event, permit_event)
            )
            return committed

    async def prepare_automatic_wire_and_permit_v49d(
        self,
        wire_payload: OutboundWirePreparedPayloadV49C,
        *,
        permit_consumed_at: datetime,
        permit_consumed_monotonic_ns: int,
    ) -> tuple[TransportActorEventV49C, TransportActorEventV49C]:
        """Atomically persist the oldest automatic output and its permit.

        Pong uses ``(wire, permit)``.  Close uses
        ``(wire, WS_CLOSE_SENT, permit)`` while returning the wire and permit
        endpoints to the caller.  In either case TLS can only observe a fully
        durable FIFO head and deterministic one-shot permit.
        """

        self._assert_owner()
        async with self._lock:
            self._assert_owner()
            self._assert_progress_allowed()
            oldest_parser = self._oldest_pending_automatic_parser_event()
            if (
                type(wire_payload) is not OutboundWirePreparedPayloadV49C
                or wire_payload.wire_origin
                is not OutboundWireOriginV49C.AUTOMATIC_PROTOCOL
                or oldest_parser is None
                or wire_payload.source_parser_event_id
                != oldest_parser.transport_actor_event_id
                or self.oldest_outbound_wire_event_id is not None
            ):
                raise PhysicalTransportSessionActorV49CQueueError(
                    "automatic preparation requires the oldest pending parser "
                    "output and an idle actor FIFO"
                )

            is_close = wire_payload.logical_opcode is WebSocketOpcodeV49C.CLOSE
            observations = self._sample_observation_batch(3 if is_close else 2)
            wire_event = self._candidate_event_for_prefix(
                wire_payload,
                self._events,
                recorded_observation=observations[0],
            )
            prefix: tuple[TransportActorEventV49C, ...] = (
                *self._events,
                wire_event,
            )
            batch: tuple[TransportActorEventV49C, ...] = (wire_event,)
            observation_index = 1
            if is_close:
                close_sent_event = self._candidate_event_for_prefix(
                    self._terminal_payload(
                        TerminalTransitionKindV49C.WS_CLOSE_SENT,
                        obligation_layer=(OutboundObligationLayerV49C.WEBSOCKET_CLOSE),
                        obligation_id=wire_payload.outbound_operation_id,
                    ),
                    prefix,
                    recorded_observation=observations[observation_index],
                )
                prefix = (*prefix, close_sent_event)
                batch = (*batch, close_sent_event)
                observation_index += 1

            permit_payload = self._write_permit_for_wire(
                wire_event,
                consumed_at=permit_consumed_at,
                consumed_monotonic_ns=permit_consumed_monotonic_ns,
            )
            permit_event = self._candidate_event_for_prefix(
                permit_payload,
                prefix,
                recorded_observation=observations[observation_index],
            )
            committed = await self._append_candidate_batch_locked(
                (*batch, permit_event)
            )
            return committed[0], committed[-1]

    def _require_oldest(self, wire_event_id: str) -> None:
        expected = self.oldest_outbound_wire_event_id
        if expected is None or wire_event_id != expected:
            raise PhysicalTransportSessionActorV49CQueueError(
                "operation must target the oldest unresolved outbound wire"
            )

    async def consume_write_permit(
        self, payload: WritePermitConsumedPayloadV49C
    ) -> TransportActorEventV49C:
        self._assert_owner()
        async with self._lock:
            self._require_oldest(payload.outbound_wire_prepared_event_id)
            return await self._append_payload_locked(payload)

    async def prepare_tls_ciphertext(
        self, payload: TlsCiphertextPreparedPayloadV49C
    ) -> TransportActorEventV49C:
        self._assert_owner()
        async with self._lock:
            self._require_oldest(payload.outbound_wire_prepared_event_id)
            wire_event = self._events_by_id[payload.outbound_wire_prepared_event_id]
            wire = wire_event.payload
            assert type(wire) is OutboundWirePreparedPayloadV49C
            if wire.wire_origin is OutboundWireOriginV49C.LOCAL_TERMINAL_COMMAND:
                raise PhysicalTransportSessionActorV49CQueueError(
                    "local Close TLS preparation requires the actor-owned "
                    "command-deadline API"
                )
            return await self._append_payload_locked(payload)

    async def prepare_local_close_tls_ciphertext_v49e(
        self,
        command_event: TransportActorEventV49C,
        wire_event: TransportActorEventV49C,
        permit_event: TransportActorEventV49C,
        *,
        driver_evidence_nonce_sha256: str,
        prepare_effect: LocalCloseTlsPrepareEffectV49E,
        signer: Any,
    ) -> TransportActorEventV49C:
        """Advance the exact local Close into TLS under its command deadline."""

        from .physical_transport_linux_v4 import (
            LinuxSocketOwnerV4DeadlineExpiredNoObservationV49E,
        )
        from .physical_transport_tls_v49 import (
            PreparedTlsCiphertextV49C,
            PreparedWebSocketWireV49C,
        )

        self._assert_owner()
        async with self._lock:
            self._assert_progress_allowed()
            command = self._require_local_shutdown_command_v49e(command_event)
            nonce = canonical_hash(
                driver_evidence_nonce_sha256,
                field="driver_evidence_nonce_sha256",
            )
            self._require_exact_actor_event(
                wire_event,
                TransportActorEventKindV49C.OUTBOUND_WIRE_PREPARED,
            )
            self._require_exact_actor_event(
                permit_event,
                TransportActorEventKindV49C.WRITE_PERMIT_CONSUMED,
            )
            wire = wire_event.payload
            permit = permit_event.payload
            assert type(wire) is OutboundWirePreparedPayloadV49C
            assert type(permit) is WritePermitConsumedPayloadV49C
            self._require_oldest(wire_event.transport_actor_event_id)
            if (
                not callable(prepare_effect)
                or wire.wire_origin is not OutboundWireOriginV49C.LOCAL_TERMINAL_COMMAND
                or wire.logical_opcode is not WebSocketOpcodeV49C.CLOSE
                or wire.source_parser_event_id is not None
                or wire.send_not_after != command.shutdown_deadline_at
                or wire.send_not_after_monotonic_ns
                != command.shutdown_deadline_monotonic_ns
                or permit.outbound_wire_prepared_event_id
                != wire_event.transport_actor_event_id
                or permit_event.transport_actor_event_id != self._active_permit_event_id
                or self._active_tls_event_id is not None
            ):
                raise PhysicalTransportSessionActorV49CQueueError(
                    "local Close TLS preparation requires its exact command, "
                    "oldest wire, and one-shot permit"
                )
            effect_ready = self._sample_observation()
            await self._converge_local_shutdown_deadline_observation_locked_v49e(
                command_event,
                effect_ready,
                signer=signer,
            )
            try:
                observed = prepare_effect(
                    deadline_ns=command.shutdown_deadline_monotonic_ns
                )
                prepared = await observed if inspect.isawaitable(observed) else observed
                prepared_wire = (
                    None
                    if type(prepared) is not PreparedTlsCiphertextV49C
                    else prepared.prepared_wire
                )
                encoded_wire_chunks = tuple(
                    base64.b64encode(chunk).decode("ascii")
                    for chunk in (
                        ()
                        if type(prepared_wire) is not PreparedWebSocketWireV49C
                        else prepared_wire.ordered_wire_chunks
                    )
                )
                if (
                    type(prepared) is not PreparedTlsCiphertextV49C
                    or type(prepared_wire) is not PreparedWebSocketWireV49C
                    or prepared_wire.logical_opcode != 0x8
                    or prepared_wire.logical_payload_sha256
                    != wire.logical_payload_sha256
                    or prepared_wire.logical_payload_octets
                    != wire.logical_payload_octets
                    or encoded_wire_chunks != wire.ordered_wire_chunks_base64
                    or prepared_wire.ordered_wire_chunks_sha256
                    != wire.ordered_wire_chunks_sha256
                    or prepared_wire.wire_batch_sha256 != wire.wire_batch_sha256
                    or prepared_wire.wire_octets != wire.wire_octets
                    or prepared.plaintext_batch_sha256 != wire.wire_batch_sha256
                    or prepared.plaintext_octets != wire.wire_octets
                ):
                    raise PhysicalTransportSessionActorV49CQueueError(
                        "owner TLS artifact differs from the exact durable local Close"
                    )
                prepared_observation = self._sample_observation()
                await self._converge_local_shutdown_deadline_observation_locked_v49e(
                    command_event,
                    prepared_observation,
                    signer=signer,
                )
                if (
                    prepared_observation[0] < effect_ready[0]
                    or prepared_observation[1] <= effect_ready[1]
                    or prepared_observation[1] <= permit.consumed_monotonic_ns
                ):
                    raise PhysicalTransportSessionActorV49COwnerError(
                        "local Close TLS clock didn't follow permit/effect gates"
                    )
            except LinuxSocketOwnerV4DeadlineExpiredNoObservationV49E as exc:
                consumed = exc.consume_for_actor_v49e(
                    transport_session_id=self._authority.transport_session_id,
                    driver_evidence_nonce_sha256=nonce,
                    operation="LOCAL_WEBSOCKET_CLOSE_TLS_PREPARATION",
                    deadline_ns=command.shutdown_deadline_monotonic_ns,
                )
                if consumed is not exc:
                    raise PhysicalTransportSessionActorV49CError(
                        "owner substituted local-Close TLS preparation evidence"
                    ) from exc
                await self._record_owner_no_observation_deadline_locked_v49e(
                    command_event,
                    exc,
                    signer=signer,
                )
                raise
            except (
                LocalShutdownCommandDeadlineDueV49E,
                LocalShutdownCommandClockDisagreementV49E,
            ):
                raise
            except BaseException:
                if not self._terminal_state.is_terminal:
                    await self._converge_terminal_payload_locked(
                        self._terminal_payload(
                            TerminalTransitionKindV49C.FATAL,
                            cause_code=V49E_TLS_OPERATION_DRIVER_ERROR_CAUSE,
                        ),
                        signer=signer,
                    )
                raise
            payload = TlsCiphertextPreparedPayloadV49C(
                outbound_wire_prepared_event_id=(wire_event.transport_actor_event_id),
                write_permit_consumed_event_id=(permit_event.transport_actor_event_id),
                plaintext_batch_sha256=prepared.plaintext_batch_sha256,
                plaintext_octets=prepared.plaintext_octets,
                ordered_ciphertext_chunks_base64=tuple(
                    base64.b64encode(chunk).decode("ascii")
                    for chunk in prepared.ordered_ciphertext_chunks
                ),
                ordered_ciphertext_chunks_sha256=(
                    prepared.ordered_ciphertext_chunks_sha256
                ),
                ciphertext_batch_sha256=prepared.ciphertext_batch_sha256,
                ciphertext_octets=prepared.ciphertext_octets,
                prepared_at=prepared_observation[0],
                prepared_monotonic_ns=prepared_observation[1],
            )
            candidate = self._candidate_event_for_prefix(
                payload,
                self._events,
                recorded_observation=prepared_observation,
            )
            return await self._append_candidate_locked(candidate)

    def _active_tls(
        self,
    ) -> tuple[TransportActorEventV49C, TlsCiphertextPreparedPayloadV49C]:
        if self._active_tls_event_id is None:
            raise PhysicalTransportSessionActorV49CQueueError(
                "no oldest-wire TLS ciphertext is prepared"
            )
        event = self._events_by_id[self._active_tls_event_id]
        payload = event.payload
        assert type(payload) is TlsCiphertextPreparedPayloadV49C
        self._require_oldest(payload.outbound_wire_prepared_event_id)
        return event, payload

    def _send_progress(self, tls_event_id: str) -> tuple[int, int, tuple[str, ...]]:
        offset = 0
        ordinal = 0
        result_ids: list[str] = []
        for event in self._events:
            payload = event.payload
            if (
                event.event_kind is TransportActorEventKindV49C.KERNEL_SEND_ATTEMPT
                and type(payload) is KernelSendAttemptPayloadV49C
                and payload.tls_ciphertext_prepared_event_id == tls_event_id
            ):
                ordinal = payload.kernel_attempt_ordinal
            elif (
                event.event_kind is TransportActorEventKindV49C.KERNEL_SEND_RESULT
                and type(payload) is KernelSendResultPayloadV49C
                and payload.tls_ciphertext_prepared_event_id == tls_event_id
            ):
                offset = payload.resulting_ciphertext_offset
                result_ids.append(event.transport_actor_event_id)
        return offset, ordinal, tuple(result_ids)

    def _current_obligation(
        self, wire_event: TransportActorEventV49C
    ) -> tuple[OutboundObligationLayerV49C, str]:
        payload = wire_event.payload
        assert type(payload) is OutboundWirePreparedPayloadV49C
        operation_id = payload.outbound_operation_id
        state = self._terminal_state
        if (
            state.tls_close_notify_sent
            and not state.tls_close_notify_fully_kernel_accepted
            and state.tls_close_notify_obligation_id == operation_id
        ):
            return OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY, operation_id
        if (
            state.ws_close_sent
            and not state.ws_output_fully_kernel_accepted
            and state.ws_output_obligation_id == operation_id
        ):
            return OutboundObligationLayerV49C.WEBSOCKET_CLOSE, operation_id
        if payload.logical_opcode is WebSocketOpcodeV49C.CLOSE:
            raise PhysicalTransportSessionActorV49CQueueError(
                "Close wire requires its durable WS_CLOSE_SENT obligation first"
            )
        return OutboundObligationLayerV49C.APPLICATION_DATA, operation_id

    def _terminal_payload(
        self,
        kind: TerminalTransitionKindV49C,
        *,
        obligation_layer: OutboundObligationLayerV49C | None = None,
        obligation_id: str | None = None,
        send_attempt_id: str | None = None,
        cause_code: str | None = None,
    ) -> TerminalTransitionPayloadV49C:
        return TerminalTransitionPayloadV49C(
            transport_session_id=self._authority.transport_session_id,
            transition_sequence=self._terminal_state.transition_sequence + 1,
            parent_terminal_state_id=self._terminal_state.terminal_state_id,
            kind=kind,
            obligation_layer=obligation_layer,
            obligation_id=obligation_id,
            send_attempt_id=send_attempt_id,
            cause_code=cause_code,
        )

    def _terminal_payload_for_state(
        self,
        state: TerminalStateV49C,
        kind: TerminalTransitionKindV49C,
        *,
        obligation_layer: OutboundObligationLayerV49C | None = None,
        obligation_id: str | None = None,
        send_attempt_id: str | None = None,
        cause_code: str | None = None,
    ) -> TerminalTransitionPayloadV49C:
        return TerminalTransitionPayloadV49C(
            transport_session_id=self._authority.transport_session_id,
            transition_sequence=state.transition_sequence + 1,
            parent_terminal_state_id=state.terminal_state_id,
            kind=kind,
            obligation_layer=obligation_layer,
            obligation_id=obligation_id,
            send_attempt_id=send_attempt_id,
            cause_code=cause_code,
        )

    async def _converge_terminal_payload_locked(
        self,
        payload: TerminalTransitionPayloadV49C,
        *,
        signer: Any,
        recorded_observation: tuple[datetime, int] | None = None,
    ) -> ActorTerminalConvergenceResultV49E:
        """Adopt only the projection's indivisible final actor/legacy pair."""

        self._assert_owner()
        self._assert_progress_allowed()
        prospective = advance_terminal_state_v49c(self._terminal_state, payload)
        if prospective.terminal_outcome is None:
            raise PhysicalTransportSessionActorV49CError(
                "terminal convergence requires one decisive final transition"
            )
        terminal_event = self._candidate_event_for_prefix(
            payload,
            self._events,
            recorded_observation=recorded_observation,
        )
        try:
            result = await self._journal.converge_actor_terminal_v49e(
                terminal_event=terminal_event,
                signer=signer,
            )
        except BaseException as exc:
            self._storage_fault_latched = True
            self._fault_reason = "terminal convergence outcome is unknown"
            if isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)):
                raise
            raise PhysicalTransportSessionActorV49CJournalError(
                self._fault_reason
            ) from exc
        from .physical_projection_v4 import ActorTerminalConvergenceResultV49E

        if (
            type(result) is not ActorTerminalConvergenceResultV49E
            or result.terminal_event != terminal_event
            or not self._authority.matches(result.terminal_event)
            or result.termination.transport_session_id
            != self._authority.transport_session_id
        ):
            self._storage_fault_latched = True
            self._fault_reason = (
                "journal returned a non-exact terminal convergence pair"
            )
            raise PhysicalTransportSessionActorV49CJournalError(self._fault_reason)
        self._events.append(result.terminal_event)
        self._rebuild_state()
        if self._terminal_state.terminal_outcome is not prospective.terminal_outcome:
            self._storage_fault_latched = True
            self._fault_reason = (
                "terminal convergence adopted a different final outcome"
            )
            raise PhysicalTransportSessionActorV49CJournalError(self._fault_reason)
        self._last_terminal_convergence_v49e = result
        return result

    async def converge_local_shutdown_clock_disagreement_v49e(
        self,
        command_event: TransportActorEventV49C,
        disagreement: LocalShutdownCommandClockDisagreementV49E,
        *,
        signer: Any,
    ) -> ActorTerminalConvergenceResultV49E:
        """Persist the exact contradictory clock pair as a replayable FATAL."""

        self._assert_owner()
        async with self._lock:
            command = self._require_local_shutdown_command_v49e(command_event)
            if type(disagreement) is not LocalShutdownCommandClockDisagreementV49E:
                raise TypeError(
                    "disagreement must be exact "
                    "LocalShutdownCommandClockDisagreementV49E"
                )
            wall_due = disagreement.observed_at >= command.shutdown_deadline_at
            monotonic_due = (
                disagreement.observed_monotonic_ns
                >= command.shutdown_deadline_monotonic_ns
            )
            if (
                disagreement.local_shutdown_command_started_event_id
                != command_event.transport_actor_event_id
                or disagreement.wall_deadline_due != wall_due
                or disagreement.monotonic_deadline_due != monotonic_due
                or wall_due == monotonic_due
                or self._terminal_state.has_pending_send_attempt
            ):
                raise PhysicalTransportSessionActorV49CQueueError(
                    "clock disagreement differs from the exact idle command prefix"
                )
            return await self._converge_terminal_payload_locked(
                self._terminal_payload(
                    TerminalTransitionKindV49C.FATAL,
                    cause_code=V49E_LOCAL_SHUTDOWN_CLOCK_DISAGREEMENT_CAUSE,
                ),
                signer=signer,
                recorded_observation=(
                    disagreement.observed_at,
                    disagreement.observed_monotonic_ns,
                ),
            )

    async def converge_terminal_v49e(
        self,
        kind: TerminalTransitionKindV49C,
        *,
        signer: Any,
        obligation_layer: OutboundObligationLayerV49C | None = None,
        obligation_id: str | None = None,
        send_attempt_id: str | None = None,
        cause_code: str | None = None,
    ) -> ActorTerminalConvergenceResultV49E:
        """Write the sole E2 decisive final transition and signed bridge."""

        self._assert_owner()
        async with self._lock:
            if kind is TerminalTransitionKindV49C.TIMEOUT and cause_code in {
                V49E_WEBSOCKET_CLOSE_DEADLINE_EXPIRED_CAUSE,
                V49E_LOCAL_SHUTDOWN_COMMAND_DEADLINE_EXPIRED_CAUSE,
                V49E_TCP_HALF_CLOSE_DEADLINE_EXPIRED_BEFORE_SYSCALL_CAUSE,
                V49E_TLS_SHUTDOWN_DEADLINE_EXPIRED_CAUSE,
                V49E_TLS_SHUTDOWN_DEADLINE_EXPIRED_AFTER_PROGRESS_CAUSE,
            }:
                raise PhysicalTransportSessionActorV49CQueueError(
                    "shutdown deadline expiry requires its dedicated owner-clock API"
                )
            payload = self._terminal_payload(
                kind,
                obligation_layer=obligation_layer,
                obligation_id=obligation_id,
                send_attempt_id=send_attempt_id,
                cause_code=cause_code,
            )
            return await self._converge_terminal_payload_locked(
                payload,
                signer=signer,
            )

    async def expire_local_shutdown_command_v49e(
        self,
        command_event: TransportActorEventV49C,
        *,
        signer: Any,
    ) -> ActorTerminalConvergenceResultV49E:
        """Converge any unresolved shutdown layer after its durable BOOTTIME due."""

        self._assert_owner()
        async with self._lock:
            self._assert_progress_allowed()
            self._require_exact_actor_event(
                command_event,
                TransportActorEventKindV49C.LOCAL_SHUTDOWN_COMMAND_STARTED,
            )
            if (
                command_event.transport_actor_event_id
                != self._local_shutdown_command_event_id
            ):
                raise PhysicalTransportSessionActorV49CQueueError(
                    "shutdown expiry requires the exact retained command"
                )
            command = command_event.payload
            assert type(command) is LocalShutdownCommandStartedPayloadV49E
            observed = self._sample_observation()
            try:
                self._raise_if_local_shutdown_deadline_due_v49e(
                    command_event,
                    observed,
                )
            except LocalShutdownCommandDeadlineDueV49E:
                pass
            else:
                raise PhysicalTransportSessionActorV49CQueueError(
                    "local shutdown wall and BOOTTIME deadlines are not due"
                )
            if self._terminal_state.has_pending_send_attempt:
                raise PhysicalTransportSessionActorV49CQueueError(
                    "unresolved kernel effect must first resolve or become UNKNOWN"
                )
            return await self._converge_terminal_payload_locked(
                self._terminal_payload(
                    TerminalTransitionKindV49C.TIMEOUT,
                    cause_code=(V49E_LOCAL_SHUTDOWN_COMMAND_DEADLINE_EXPIRED_CAUSE),
                ),
                signer=signer,
            )

    async def expire_local_websocket_close_deadline_v49e(
        self,
        *,
        signer: Any,
    ) -> ActorTerminalConvergenceResultV49E:
        """Compatibility alias for a retained command's command-wide expiry."""

        command_event = self.local_shutdown_command_event_v49e
        if command_event is None:
            raise PhysicalTransportSessionActorV49CQueueError(
                "WebSocket Close expiry lacks a durable shutdown command"
            )
        return await self.expire_local_shutdown_command_v49e(
            command_event,
            signer=signer,
        )

    def _require_exact_actor_event(
        self,
        event: TransportActorEventV49C,
        kind: TransportActorEventKindV49C,
    ) -> TransportActorEventV49C:
        if (
            type(event) is not TransportActorEventV49C
            or event.event_kind is not kind
            or self._events_by_id.get(event.transport_actor_event_id) is not event
        ):
            raise PhysicalTransportSessionActorV49CQueueError(
                f"operation requires the exact retained {kind.value} event"
            )
        return event

    def _require_local_shutdown_command_v49e(
        self,
        command_event: TransportActorEventV49C,
    ) -> LocalShutdownCommandStartedPayloadV49E:
        self._require_exact_actor_event(
            command_event,
            TransportActorEventKindV49C.LOCAL_SHUTDOWN_COMMAND_STARTED,
        )
        if (
            command_event.transport_actor_event_id
            != self._local_shutdown_command_event_id
        ):
            raise PhysicalTransportSessionActorV49CQueueError(
                "operation requires the exact retained local shutdown command"
            )
        payload = command_event.payload
        assert type(payload) is LocalShutdownCommandStartedPayloadV49E
        return payload

    def _latest_terminal_marker_id(self, kind: TerminalTransitionKindV49C) -> str:
        for event in reversed(self._events):
            if (
                event.event_kind is TransportActorEventKindV49C.TERMINAL_TRANSITION
                and type(event.payload) is TerminalTransitionPayloadV49C
                and event.payload.kind is kind
            ):
                return event.transport_actor_event_id
        raise PhysicalTransportSessionActorV49CQueueError(
            f"actor prefix lacks required {kind.value} marker"
        )

    async def start_tls_protocol_operation_v49e(
        self,
        command_event: TransportActorEventV49C,
        *,
        purpose: TlsProtocolOperationPurposeV49E,
        cause_event: TransportActorEventV49C,
        driver_evidence_nonce_sha256: str,
    ) -> TransportActorEventV49C:
        """Durably write ahead one deterministic retained-driver operation."""

        self._assert_owner()
        async with self._lock:
            self._assert_progress_allowed()
            self._require_local_shutdown_command_v49e(command_event)
            if (
                type(cause_event) is not TransportActorEventV49C
                or self._events_by_id.get(cause_event.transport_actor_event_id)
                is not cause_event
            ):
                raise PhysicalTransportSessionActorV49CQueueError(
                    "TLS operation cause must be one exact retained actor event"
                )
            operation_sequence = 1 + max(
                (
                    event.payload.operation_sequence
                    for event in self._events
                    if type(event.payload) is TlsProtocolOperationStartedPayloadV49E
                ),
                default=0,
            )
            purpose = (
                purpose
                if type(purpose) is TlsProtocolOperationPurposeV49E
                else TlsProtocolOperationPurposeV49E(purpose)
            )
            nonce = canonical_hash(
                driver_evidence_nonce_sha256,
                field="driver_evidence_nonce_sha256",
            )
            operation_id = sha256_digest(
                {
                    "domain": "RiskYieldMMTlsProtocolOperationV4_9E",
                    "transport_session_id": self._authority.transport_session_id,
                    "operation_sequence": operation_sequence,
                    "local_shutdown_command_started_event_id": (
                        command_event.transport_actor_event_id
                    ),
                    "purpose": purpose.value,
                    "cause_actor_event_id": cause_event.transport_actor_event_id,
                    "driver_evidence_nonce_sha256": nonce,
                }
            )
            started_at, started_monotonic_ns = self._sample_observation()
            self._raise_if_local_shutdown_deadline_due_v49e(
                command_event,
                (started_at, started_monotonic_ns),
            )
            payload = TlsProtocolOperationStartedPayloadV49E(
                operation_sequence=operation_sequence,
                tls_operation_id=operation_id,
                local_shutdown_command_started_event_id=(
                    command_event.transport_actor_event_id
                ),
                purpose=purpose,
                cause_actor_event_id=cause_event.transport_actor_event_id,
                driver_evidence_nonce_sha256=nonce,
                started_at=started_at,
                started_monotonic_ns=started_monotonic_ns,
            )
            return await self._append_payload_locked(payload)

    async def _record_tls_operation_failure_locked(
        self,
        operation_event: TransportActorEventV49C,
        *,
        failure_kind: TlsProtocolOperationFailureKindV49E,
        signer: Any,
        unsendable_driver_output_sequence: int | None = None,
        unsendable_driver_evidence_id: str | None = None,
        unsendable_owner_evidence_id: str | None = None,
        unsendable_kernel_socket_identity: str | None = None,
        unsendable_ciphertext_sha256: str | None = None,
        unsendable_ciphertext_octets: int | None = None,
        deadline_no_observation_owner_evidence_id: str | None = None,
        deadline_no_observation_kernel_socket_identity: str | None = None,
        deadline_no_observation_operation: str | None = None,
        deadline_after_progress_owner_evidence_id: str | None = None,
        deadline_after_progress_driver_evidence_id: str | None = None,
        deadline_after_progress_kernel_socket_identity: str | None = None,
        deadline_after_progress_operation: str | None = None,
        deadline_after_progress_ciphertext_sha256: str | None = None,
        deadline_after_progress_ciphertext_octets: int | None = None,
    ) -> ActorTerminalConvergenceResultV49E:
        self._require_exact_actor_event(
            operation_event,
            TransportActorEventKindV49C.TLS_PROTOCOL_OPERATION_STARTED,
        )
        operation = operation_event.payload
        assert type(operation) is TlsProtocolOperationStartedPayloadV49E
        command_event = self._events_by_id[
            operation.local_shutdown_command_started_event_id
        ]
        command = command_event.payload
        assert type(command) is LocalShutdownCommandStartedPayloadV49E
        failure_kind = (
            failure_kind
            if type(failure_kind) is TlsProtocolOperationFailureKindV49E
            else TlsProtocolOperationFailureKindV49E(failure_kind)
        )
        observed_at, observed_monotonic_ns = self._sample_observation()
        deadline_classification = None
        if failure_kind in {
            TlsProtocolOperationFailureKindV49E.DEADLINE_EXPIRED_NO_OBSERVATION,
            TlsProtocolOperationFailureKindV49E.DEADLINE_EXPIRED_AFTER_PROGRESS,
        }:
            wall_due = observed_at >= command.shutdown_deadline_at
            monotonic_due = (
                observed_monotonic_ns >= command.shutdown_deadline_monotonic_ns
            )
            deadline_classification = (
                LocalShutdownDeadlineClassificationV49E.BOTH_DUE
                if wall_due and monotonic_due
                else (
                    LocalShutdownDeadlineClassificationV49E.CLOCK_DISAGREEMENT
                    if wall_due != monotonic_due
                    else LocalShutdownDeadlineClassificationV49E.OWNER_EVIDENCE_BEFORE_BOTH_CLOCKS
                )
            )
        failure = TlsProtocolOperationFailedPayloadV49E(
            tls_protocol_operation_started_event_id=(
                operation_event.transport_actor_event_id
            ),
            tls_operation_id=operation.tls_operation_id,
            purpose=operation.purpose,
            driver_evidence_nonce_sha256=operation.driver_evidence_nonce_sha256,
            failure_kind=failure_kind,
            deadline_classification=deadline_classification,
            shutdown_deadline_monotonic_ns=(command.shutdown_deadline_monotonic_ns),
            unsendable_driver_output_sequence=(unsendable_driver_output_sequence),
            unsendable_driver_evidence_id=unsendable_driver_evidence_id,
            unsendable_owner_evidence_id=unsendable_owner_evidence_id,
            unsendable_kernel_socket_identity=unsendable_kernel_socket_identity,
            unsendable_ciphertext_sha256=unsendable_ciphertext_sha256,
            unsendable_ciphertext_octets=unsendable_ciphertext_octets,
            deadline_no_observation_owner_evidence_id=(
                deadline_no_observation_owner_evidence_id
            ),
            deadline_no_observation_kernel_socket_identity=(
                deadline_no_observation_kernel_socket_identity
            ),
            deadline_no_observation_operation=(deadline_no_observation_operation),
            deadline_after_progress_owner_evidence_id=(
                deadline_after_progress_owner_evidence_id
            ),
            deadline_after_progress_driver_evidence_id=(
                deadline_after_progress_driver_evidence_id
            ),
            deadline_after_progress_kernel_socket_identity=(
                deadline_after_progress_kernel_socket_identity
            ),
            deadline_after_progress_operation=deadline_after_progress_operation,
            deadline_after_progress_ciphertext_sha256=(
                deadline_after_progress_ciphertext_sha256
            ),
            deadline_after_progress_ciphertext_octets=(
                deadline_after_progress_ciphertext_octets
            ),
            observed_at=observed_at,
            observed_monotonic_ns=observed_monotonic_ns,
        )
        await self._append_payload_locked(failure)
        terminal_kind, cause = classify_tls_protocol_operation_failure_v49e(failure)
        return await self._converge_terminal_payload_locked(
            self._terminal_payload(terminal_kind, cause_code=cause),
            signer=signer,
        )

    def _validate_tls_control_prepared_v49e(
        self,
        operation_event: TransportActorEventV49C,
        prepared_control: Any,
    ) -> tuple[
        TlsProtocolOperationStartedPayloadV49E,
        TlsControlOutputKindV49E,
    ]:
        from .physical_transport_tls_v49 import (
            ExactTlsWebSocketDriverV49,
            PreparedTlsControlCiphertextV49E,
        )

        self._require_exact_actor_event(
            operation_event,
            TransportActorEventKindV49C.TLS_PROTOCOL_OPERATION_STARTED,
        )
        operation = operation_event.payload
        assert type(operation) is TlsProtocolOperationStartedPayloadV49E
        if type(prepared_control) is not PreparedTlsControlCiphertextV49E:
            raise TypeError(
                "prepared_control must be exact PreparedTlsControlCiphertextV49E"
            )
        ExactTlsWebSocketDriverV49._assert_prepared_tls_control_integrity_v49e(  # noqa: SLF001
            prepared_control
        )
        actor_kind = TlsControlOutputKindV49E(prepared_control.control_kind.value)
        expected_purpose = (
            TlsProtocolOperationPurposeV49E.LOCAL_CLOSE_NOTIFY
            if actor_kind is TlsControlOutputKindV49E.LOCAL_CLOSE_NOTIFY
            else TlsProtocolOperationPurposeV49E.OPAQUE_POST_HANDSHAKE_RESPONSE
        )
        if (
            operation.purpose is not expected_purpose
            or prepared_control.driver_evidence_nonce_sha256
            != operation.driver_evidence_nonce_sha256
        ):
            raise PhysicalTransportSessionActorV49CQueueError(
                "prepared TLS control differs from its exact write-ahead operation"
            )
        return operation, actor_kind

    async def _record_tls_control_prepared_locked(
        self,
        operation_event: TransportActorEventV49C,
        prepared_control: Any,
    ) -> tuple[TransportActorEventV49C, TransportActorEventV49C | None]:
        operation, actor_kind = self._validate_tls_control_prepared_v49e(
            operation_event,
            prepared_control,
        )
        prepared_at, prepared_monotonic_ns = self._sample_observation()
        payload = TlsControlCiphertextPreparedPayloadV49E(
            tls_protocol_operation_started_event_id=(
                operation_event.transport_actor_event_id
            ),
            tls_operation_id=operation.tls_operation_id,
            control_sequence=prepared_control.control_sequence,
            control_kind=actor_kind,
            driver_evidence_nonce_sha256=(
                prepared_control.driver_evidence_nonce_sha256
            ),
            ordered_ciphertext_chunks_base64=tuple(
                base64.b64encode(chunk).decode("ascii")
                for chunk in prepared_control.ordered_ciphertext_chunks
            ),
            ordered_ciphertext_chunks_sha256=(
                prepared_control.ordered_ciphertext_chunks_sha256
            ),
            ciphertext_batch_sha256=prepared_control.ciphertext_batch_sha256,
            ciphertext_octets=prepared_control.ciphertext_octets,
            peer_close_notify_received_during_preparation=(
                prepared_control.peer_close_notify_received_during_preparation
            ),
            prepared_at=prepared_at,
            prepared_monotonic_ns=prepared_monotonic_ns,
        )
        if actor_kind is TlsControlOutputKindV49E.LOCAL_CLOSE_NOTIFY:
            observations = self._sample_observation_batch(2)
            control_event = self._candidate_event_for_prefix(
                payload,
                self._events,
                recorded_observation=observations[0],
            )
            marker_event = self._candidate_event_for_prefix(
                self._terminal_payload(
                    TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_PREPARED,
                    obligation_layer=OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY,
                    obligation_id=control_event.transport_actor_event_id,
                ),
                (*self._events, control_event),
                recorded_observation=observations[1],
            )
            await self._append_candidate_batch_locked((control_event, marker_event))
        else:
            control_event = await self._append_payload_locked(payload)
            marker_event = None
        self._v49e_prepared_control_capabilities[
            control_event.transport_actor_event_id
        ] = prepared_control
        return control_event, marker_event

    async def record_tls_control_prepared_v49e(
        self,
        operation_event: TransportActorEventV49C,
        prepared_control: Any,
    ) -> tuple[TransportActorEventV49C, TransportActorEventV49C | None]:
        self._assert_owner()
        async with self._lock:
            return await self._record_tls_control_prepared_locked(
                operation_event,
                prepared_control,
            )

    async def complete_tls_control_preparation_v49e(
        self,
        operation_event: TransportActorEventV49C,
        *,
        prepare_effect: TlsControlPrepareEffectV49E,
        signer: Any,
    ) -> tuple[TransportActorEventV49C, TransportActorEventV49C | None]:
        """Close one write-ahead TLS operation without leaving an open effect."""

        from .physical_transport_linux_v4 import (
            LinuxSocketOwnerV4DeadlineExpiredNoObservationV49E,
        )

        self._assert_owner()
        async with self._lock:
            self._require_exact_actor_event(
                operation_event,
                TransportActorEventKindV49C.TLS_PROTOCOL_OPERATION_STARTED,
            )
            operation = operation_event.payload
            assert type(operation) is TlsProtocolOperationStartedPayloadV49E
            command_event = self._events_by_id[
                operation.local_shutdown_command_started_event_id
            ]
            command = command_event.payload
            assert type(command) is LocalShutdownCommandStartedPayloadV49E
            try:
                observed = (
                    prepare_effect(deadline_ns=command.shutdown_deadline_monotonic_ns)
                    if operation.purpose
                    is TlsProtocolOperationPurposeV49E.LOCAL_CLOSE_NOTIFY
                    else prepare_effect()
                )
                prepared = await observed if inspect.isawaitable(observed) else observed
                self._validate_tls_control_prepared_v49e(
                    operation_event,
                    prepared,
                )
            except LinuxSocketOwnerV4DeadlineExpiredNoObservationV49E as exc:
                if (
                    exc.operation != "LOCAL_TLS_CLOSE_NOTIFY_PREPARATION"
                    or exc.deadline_ns != command.shutdown_deadline_monotonic_ns
                ):
                    if not self._terminal_state.is_terminal:
                        await self._record_tls_operation_failure_locked(
                            operation_event,
                            failure_kind=(
                                TlsProtocolOperationFailureKindV49E.DRIVER_ERROR
                            ),
                            signer=signer,
                        )
                    raise
                consumed = exc.consume_for_actor_v49e(
                    transport_session_id=self._authority.transport_session_id,
                    driver_evidence_nonce_sha256=(
                        operation.driver_evidence_nonce_sha256
                    ),
                    operation="LOCAL_TLS_CLOSE_NOTIFY_PREPARATION",
                    deadline_ns=command.shutdown_deadline_monotonic_ns,
                )
                if consumed is not exc:
                    raise PhysicalTransportSessionActorV49CError(
                        "owner substituted TLS preparation deadline evidence"
                    ) from exc
                await self._record_tls_operation_failure_locked(
                    operation_event,
                    failure_kind=(
                        TlsProtocolOperationFailureKindV49E.DEADLINE_EXPIRED_NO_OBSERVATION
                    ),
                    signer=signer,
                    deadline_no_observation_owner_evidence_id=(exc.owner_evidence_id),
                    deadline_no_observation_kernel_socket_identity=(
                        exc.kernel_socket_identity
                    ),
                    deadline_no_observation_operation=exc.operation,
                )
                raise
            except BaseException:
                if not self._terminal_state.is_terminal:
                    await self._record_tls_operation_failure_locked(
                        operation_event,
                        failure_kind=TlsProtocolOperationFailureKindV49E.DRIVER_ERROR,
                        signer=signer,
                    )
                raise
            return await self._record_tls_control_prepared_locked(
                operation_event,
                prepared,
            )

    async def append_terminal_transition(
        self,
        kind: TerminalTransitionKindV49C,
        *,
        obligation_layer: OutboundObligationLayerV49C | None = None,
        obligation_id: str | None = None,
        send_attempt_id: str | None = None,
        cause_code: str | None = None,
    ) -> TransportActorEventV49C:
        """Append a reducer input with session/sequence/parent derived internally."""

        self._assert_owner()
        async with self._lock:
            payload = self._terminal_payload(
                kind,
                obligation_layer=obligation_layer,
                obligation_id=obligation_id,
                send_attempt_id=send_attempt_id,
                cause_code=cause_code,
            )
            if advance_terminal_state_v49c(
                self._terminal_state,
                payload,
            ).is_terminal:
                raise PhysicalTransportSessionActorV49CError(
                    "decisive terminal transitions require converge_terminal_v49e"
                )
            return await self._append_payload_locked(payload)

    async def _append_send_started_locked(
        self,
        *,
        attempt_event_id: str,
        obligation_layer: OutboundObligationLayerV49C,
        obligation_id: str,
    ) -> TransportActorEventV49C:
        return await self._append_payload_locked(
            self._terminal_payload(
                TerminalTransitionKindV49C.SEND_ATTEMPT_STARTED,
                obligation_layer=obligation_layer,
                obligation_id=obligation_id,
                send_attempt_id=attempt_event_id,
            )
        )

    async def _append_send_resolved_locked(
        self,
        *,
        attempt_event_id: str,
        obligation_layer: OutboundObligationLayerV49C,
        obligation_id: str,
    ) -> TransportActorEventV49C:
        return await self._append_payload_locked(
            self._terminal_payload(
                TerminalTransitionKindV49C.SEND_ATTEMPT_RESOLVED,
                obligation_layer=obligation_layer,
                obligation_id=obligation_id,
                send_attempt_id=attempt_event_id,
            )
        )

    async def _append_unknown_send_locked(
        self, *, cause_code: str, signer: Any | None = None
    ) -> TransportActorEventV49C:
        transition, _ = terminalize_pending_send_v49c(
            self._terminal_state, cause_code=cause_code
        )
        if signer is not None:
            result = await self._converge_terminal_payload_locked(
                transition,
                signer=signer,
            )
            return result.terminal_event
        return await self._append_payload_locked(transition)

    def _tls_control_send_progress(
        self, control_event_id: str
    ) -> tuple[int, int, tuple[str, ...]]:
        offset = 0
        ordinal = 0
        result_ids: list[str] = []
        for event in self._events:
            payload = event.payload
            if (
                type(payload) is TlsControlKernelSendAttemptPayloadV49E
                and payload.tls_control_ciphertext_prepared_event_id == control_event_id
            ):
                ordinal = payload.kernel_attempt_ordinal
            elif (
                type(payload) is TlsControlKernelSendResultPayloadV49E
                and payload.tls_control_ciphertext_prepared_event_id == control_event_id
            ):
                offset = payload.resulting_ciphertext_offset
                result_ids.append(event.transport_actor_event_id)
        return offset, ordinal, tuple(result_ids)

    async def _converge_unknown_tls_control_send_locked(
        self,
        *,
        signer: Any,
    ) -> ActorTerminalConvergenceResultV49E:
        attempt_id = self._terminal_state.pending_send_attempt_id
        layer = self._terminal_state.pending_send_obligation_layer
        obligation_id = self._terminal_state.pending_send_obligation_id
        if attempt_id is None or layer not in {
            OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY,
            OutboundObligationLayerV49C.TLS_OPAQUE_CONTROL,
        }:
            raise PhysicalTransportSessionActorV49CJournalError(
                "TLS-control ambiguity lacks its exact pending attempt"
            )
        return await self._converge_terminal_payload_locked(
            self._terminal_payload(
                TerminalTransitionKindV49C.UNKNOWN_SEND,
                obligation_layer=layer,
                obligation_id=obligation_id,
                send_attempt_id=attempt_id,
                cause_code=V49E_TLS_CONTROL_SEND_OUTCOME_UNKNOWN_CAUSE,
            ),
            signer=signer,
        )

    async def _record_tls_control_send_failure_locked(
        self,
        *,
        command_event: TransportActorEventV49C,
        control_event: TransportActorEventV49C,
        attempt_event: TransportActorEventV49C,
        attempt: TlsControlKernelSendAttemptPayloadV49E,
        layer: OutboundObligationLayerV49C,
        failure_kind: KernelSendFailureKindV49E,
        observed_at: datetime,
        observed_monotonic_ns: int,
        signer: Any,
        owner_evidence_id: str | None = None,
        kernel_socket_identity: str | None = None,
        driver_evidence_nonce_sha256: str | None = None,
        owner_deadline_operation: str | None = None,
        send_kind: str | None = None,
        transport_sequence: int | None = None,
        exact_slice_sha256: str | None = None,
        would_block_count: int | None = None,
        driver_evidence_id: str | None = None,
    ) -> ActorTerminalConvergenceResultV49E:
        command = self._require_local_shutdown_command_v49e(command_event)
        failure = TlsControlKernelSendFailurePayloadV49E(
            tls_control_kernel_send_attempt_event_id=(
                attempt_event.transport_actor_event_id
            ),
            tls_control_ciphertext_prepared_event_id=(
                control_event.transport_actor_event_id
            ),
            local_shutdown_command_started_event_id=(
                command_event.transport_actor_event_id
            ),
            shutdown_deadline_monotonic_ns=(command.shutdown_deadline_monotonic_ns),
            kernel_attempt_ordinal=attempt.kernel_attempt_ordinal,
            ciphertext_batch_sha256=attempt.ciphertext_batch_sha256,
            ciphertext_octets=attempt.ciphertext_octets,
            ciphertext_start_octet=attempt.ciphertext_start_octet,
            requested_octets=attempt.requested_octets,
            failure_kind=failure_kind,
            owner_evidence_id=owner_evidence_id,
            kernel_socket_identity=kernel_socket_identity,
            driver_evidence_nonce_sha256=driver_evidence_nonce_sha256,
            owner_deadline_operation=owner_deadline_operation,
            send_kind=send_kind,
            transport_sequence=transport_sequence,
            exact_slice_sha256=exact_slice_sha256,
            would_block_count=would_block_count,
            driver_evidence_id=driver_evidence_id,
            observed_at=observed_at,
            observed_monotonic_ns=observed_monotonic_ns,
        )
        observations = self._sample_observation_batch(2)
        failure_event = self._candidate_event_for_prefix(
            failure,
            self._events,
            recorded_observation=observations[0],
        )
        resolved_event = self._candidate_event_for_prefix(
            self._terminal_payload(
                TerminalTransitionKindV49C.SEND_ATTEMPT_RESOLVED,
                obligation_layer=layer,
                obligation_id=control_event.transport_actor_event_id,
                send_attempt_id=attempt_event.transport_actor_event_id,
            ),
            (*self._events, failure_event),
            recorded_observation=observations[1],
        )
        await self._append_candidate_batch_locked((failure_event, resolved_event))
        clock_disagreement = (
            failure_kind is KernelSendFailureKindV49E.CLOCK_DISAGREEMENT
        )
        return await self._converge_terminal_payload_locked(
            self._terminal_payload(
                (
                    TerminalTransitionKindV49C.FATAL
                    if clock_disagreement
                    else TerminalTransitionKindV49C.TIMEOUT
                ),
                cause_code=(
                    V49E_LOCAL_SHUTDOWN_CLOCK_DISAGREEMENT_CAUSE
                    if clock_disagreement
                    else V49E_LOCAL_SHUTDOWN_COMMAND_DEADLINE_EXPIRED_CAUSE
                ),
            ),
            signer=signer,
        )

    async def send_tls_control_ciphertext_v49e(
        self,
        control_event: TransportActorEventV49C,
        prepared_control: Any,
        *,
        send_effect: TlsControlSendEffectV49E,
        signer: Any,
        requested_octets: int | None = None,
    ) -> TlsControlSendOutcomeV49E:
        """Submit one exact TLS-control suffix under durable write-ahead."""

        from .physical_transport_linux_v4 import (
            LinuxSocketOwnerV4DeadlineExpiredNoObservationV49E,
            LinuxSocketOwnerV4SendDeadlineExpiredNoKernelAcceptanceV49E,
        )
        from .physical_transport_tls_v49 import PreparedTlsControlCiphertextV49E

        self._assert_owner()
        async with self._lock:
            self._assert_progress_allowed()
            self._require_exact_actor_event(
                control_event,
                TransportActorEventKindV49C.TLS_CONTROL_CIPHERTEXT_PREPARED,
            )
            control = control_event.payload
            assert type(control) is TlsControlCiphertextPreparedPayloadV49E
            operation_event = self._events_by_id[
                control.tls_protocol_operation_started_event_id
            ]
            operation = operation_event.payload
            assert type(operation) is TlsProtocolOperationStartedPayloadV49E
            command_event = self._events_by_id[
                operation.local_shutdown_command_started_event_id
            ]
            command = self._require_local_shutdown_command_v49e(command_event)
            retained = self._v49e_prepared_control_capabilities.get(
                control_event.transport_actor_event_id
            )
            if (
                type(prepared_control) is not PreparedTlsControlCiphertextV49E
                or retained is not prepared_control
            ):
                raise PhysicalTransportSessionActorV49CQueueError(
                    "TLS-control send requires the exact retained sealed artifact"
                )
            offset, ordinal, _ = self._tls_control_send_progress(
                control_event.transport_actor_event_id
            )
            remaining = control.ciphertext_octets - offset
            if remaining <= 0:
                raise PhysicalTransportSessionActorV49CQueueError(
                    "TLS-control ciphertext is already fully submitted"
                )
            requested = (
                remaining
                if requested_octets is None
                else canonical_safe_int(
                    requested_octets,
                    field="requested_octets",
                    minimum=1,
                    maximum=remaining,
                )
            )
            deadline = command.shutdown_deadline_monotonic_ns
            attempted_at, attempted_monotonic_ns = self._sample_observation()
            try:
                self._raise_if_local_shutdown_deadline_due_v49e(
                    command_event,
                    (attempted_at, attempted_monotonic_ns),
                )
            except LocalShutdownCommandDeadlineDueV49E:
                await self._converge_terminal_payload_locked(
                    self._terminal_payload(
                        TerminalTransitionKindV49C.TIMEOUT,
                        cause_code=(V49E_LOCAL_SHUTDOWN_COMMAND_DEADLINE_EXPIRED_CAUSE),
                    ),
                    signer=signer,
                    recorded_observation=(attempted_at, attempted_monotonic_ns),
                )
                raise
            except LocalShutdownCommandClockDisagreementV49E:
                await self._converge_terminal_payload_locked(
                    self._terminal_payload(
                        TerminalTransitionKindV49C.FATAL,
                        cause_code=V49E_LOCAL_SHUTDOWN_CLOCK_DISAGREEMENT_CAUSE,
                    ),
                    signer=signer,
                    recorded_observation=(attempted_at, attempted_monotonic_ns),
                )
                raise
            attempt = TlsControlKernelSendAttemptPayloadV49E(
                tls_control_ciphertext_prepared_event_id=(
                    control_event.transport_actor_event_id
                ),
                local_shutdown_command_started_event_id=(
                    command_event.transport_actor_event_id
                ),
                shutdown_deadline_monotonic_ns=deadline,
                kernel_attempt_ordinal=ordinal + 1,
                ciphertext_batch_sha256=control.ciphertext_batch_sha256,
                ciphertext_octets=control.ciphertext_octets,
                ciphertext_start_octet=offset,
                requested_octets=requested,
                attempted_at=attempted_at,
                attempted_monotonic_ns=attempted_monotonic_ns,
            )
            layer = (
                OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY
                if control.control_kind is TlsControlOutputKindV49E.LOCAL_CLOSE_NOTIFY
                else OutboundObligationLayerV49C.TLS_OPAQUE_CONTROL
            )
            attempt_observations = self._sample_observation_batch(2)
            attempt_event = self._candidate_event_for_prefix(
                attempt,
                self._events,
                recorded_observation=attempt_observations[0],
            )
            started_event = self._candidate_event_for_prefix(
                self._terminal_payload(
                    TerminalTransitionKindV49C.SEND_ATTEMPT_STARTED,
                    obligation_layer=layer,
                    obligation_id=control_event.transport_actor_event_id,
                    send_attempt_id=attempt_event.transport_actor_event_id,
                ),
                (*self._events, attempt_event),
                recorded_observation=attempt_observations[1],
            )
            await self._append_candidate_batch_locked((attempt_event, started_event))

            try:
                effect_ready_at, effect_ready_ns = self._sample_observation()
                try:
                    self._raise_if_local_shutdown_deadline_due_v49e(
                        command_event,
                        (effect_ready_at, effect_ready_ns),
                    )
                except LocalShutdownCommandDeadlineDueV49E:
                    await self._record_tls_control_send_failure_locked(
                        command_event=command_event,
                        control_event=control_event,
                        attempt_event=attempt_event,
                        attempt=attempt,
                        layer=layer,
                        failure_kind=(
                            KernelSendFailureKindV49E.DEADLINE_EXPIRED_BEFORE_CALLBACK
                        ),
                        observed_at=effect_ready_at,
                        observed_monotonic_ns=effect_ready_ns,
                        signer=signer,
                    )
                    raise
                except LocalShutdownCommandClockDisagreementV49E:
                    await self._record_tls_control_send_failure_locked(
                        command_event=command_event,
                        control_event=control_event,
                        attempt_event=attempt_event,
                        attempt=attempt,
                        layer=layer,
                        failure_kind=KernelSendFailureKindV49E.CLOCK_DISAGREEMENT,
                        observed_at=effect_ready_at,
                        observed_monotonic_ns=effect_ready_ns,
                        signer=signer,
                    )
                    raise
                exact_slice = prepared_control.exact_ciphertext[
                    offset : offset + requested
                ]
                observed = send_effect(exact_slice, deadline_ns=deadline)
                accepted = await observed if inspect.isawaitable(observed) else observed
                if type(accepted) is not int or not 1 <= accepted <= requested:
                    raise PhysicalTransportSessionActorV49CError(
                        "TLS-control send must return one exact positive count"
                    )
                observed_at, observed_monotonic_ns = self._sample_observation()
                result = TlsControlKernelSendResultPayloadV49E(
                    tls_control_kernel_send_attempt_event_id=(
                        attempt_event.transport_actor_event_id
                    ),
                    tls_control_ciphertext_prepared_event_id=(
                        control_event.transport_actor_event_id
                    ),
                    kernel_attempt_ordinal=attempt.kernel_attempt_ordinal,
                    ciphertext_batch_sha256=attempt.ciphertext_batch_sha256,
                    ciphertext_octets=attempt.ciphertext_octets,
                    ciphertext_start_octet=attempt.ciphertext_start_octet,
                    requested_octets=attempt.requested_octets,
                    accepted_octets=accepted,
                    resulting_ciphertext_offset=offset + accepted,
                    observed_at=observed_at,
                    observed_monotonic_ns=observed_monotonic_ns,
                )
                is_complete_local = (
                    result.resulting_ciphertext_offset == control.ciphertext_octets
                    and control.control_kind
                    is TlsControlOutputKindV49E.LOCAL_CLOSE_NOTIFY
                )
                observations = self._sample_observation_batch(
                    4 if is_complete_local else 2
                )
                result_event = self._candidate_event_for_prefix(
                    result,
                    self._events,
                    recorded_observation=observations[0],
                )
                resolved_payload = self._terminal_payload(
                    TerminalTransitionKindV49C.SEND_ATTEMPT_RESOLVED,
                    obligation_layer=layer,
                    obligation_id=control_event.transport_actor_event_id,
                    send_attempt_id=attempt_event.transport_actor_event_id,
                )
                resolved_event = self._candidate_event_for_prefix(
                    resolved_payload,
                    (*self._events, result_event),
                    recorded_observation=observations[1],
                )
                batch: tuple[TransportActorEventV49C, ...] = (
                    result_event,
                    resolved_event,
                )
                sent_event = None
                accepted_event = None
                if is_complete_local:
                    resolved_state = advance_terminal_state_v49c(
                        self._terminal_state,
                        resolved_payload,
                    )
                    sent_payload = self._terminal_payload_for_state(
                        resolved_state,
                        TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_SENT,
                        obligation_layer=(OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY),
                        obligation_id=control_event.transport_actor_event_id,
                    )
                    sent_event = self._candidate_event_for_prefix(
                        sent_payload,
                        (*self._events, *batch),
                        recorded_observation=observations[2],
                    )
                    sent_state = advance_terminal_state_v49c(
                        resolved_state,
                        sent_payload,
                    )
                    accepted_payload = self._terminal_payload_for_state(
                        sent_state,
                        TerminalTransitionKindV49C.OUTBOUND_OBLIGATION_FULLY_KERNEL_ACCEPTED,
                        obligation_layer=(OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY),
                        obligation_id=control_event.transport_actor_event_id,
                    )
                    accepted_event = self._candidate_event_for_prefix(
                        accepted_payload,
                        (*self._events, *batch, sent_event),
                        recorded_observation=observations[3],
                    )
                    batch = (*batch, sent_event, accepted_event)
                await self._append_candidate_batch_locked(batch)
                if (
                    result.resulting_ciphertext_offset == control.ciphertext_octets
                    and control.control_kind
                    is TlsControlOutputKindV49E.OPAQUE_POST_HANDSHAKE_RESPONSE
                ):
                    self._v49e_prepared_control_capabilities.pop(
                        control_event.transport_actor_event_id,
                        None,
                    )
                return TlsControlSendOutcomeV49E(
                    attempt_event=attempt_event,
                    attempt_started_event=started_event,
                    result_event=result_event,
                    attempt_resolved_event=resolved_event,
                    tls_close_notify_sent_event=sent_event,
                    fully_kernel_accepted_event=accepted_event,
                )
            except LinuxSocketOwnerV4DeadlineExpiredNoObservationV49E as exc:
                consumed = exc.consume_for_actor_v49e(
                    transport_session_id=self._authority.transport_session_id,
                    driver_evidence_nonce_sha256=(control.driver_evidence_nonce_sha256),
                    operation="TLS_CONTROL_SEND_BEFORE_SYSCALL",
                    deadline_ns=deadline,
                )
                if consumed is not exc:
                    raise PhysicalTransportSessionActorV49CError(
                        "owner substituted TLS send pre-syscall evidence"
                    ) from exc
                observed_at, observed_monotonic_ns = self._sample_observation()
                wall_due = observed_at >= command.shutdown_deadline_at
                monotonic_due = observed_monotonic_ns >= deadline
                if wall_due != monotonic_due:
                    await self._record_tls_control_send_failure_locked(
                        command_event=command_event,
                        control_event=control_event,
                        attempt_event=attempt_event,
                        attempt=attempt,
                        layer=layer,
                        failure_kind=KernelSendFailureKindV49E.CLOCK_DISAGREEMENT,
                        observed_at=observed_at,
                        observed_monotonic_ns=observed_monotonic_ns,
                        signer=signer,
                    )
                elif wall_due:
                    await self._record_tls_control_send_failure_locked(
                        command_event=command_event,
                        control_event=control_event,
                        attempt_event=attempt_event,
                        attempt=attempt,
                        layer=layer,
                        failure_kind=(
                            KernelSendFailureKindV49E.DEADLINE_EXPIRED_BEFORE_SYSCALL
                        ),
                        observed_at=observed_at,
                        observed_monotonic_ns=observed_monotonic_ns,
                        signer=signer,
                        owner_evidence_id=exc.owner_evidence_id,
                        kernel_socket_identity=exc.kernel_socket_identity,
                        driver_evidence_nonce_sha256=(exc.driver_evidence_nonce_sha256),
                        owner_deadline_operation=exc.operation,
                    )
                else:
                    raise PhysicalTransportSessionActorV49CError(
                        "owner send deadline precedes both actor command clocks"
                    ) from exc
                raise
            except LinuxSocketOwnerV4SendDeadlineExpiredNoKernelAcceptanceV49E as exc:
                consumed = exc.consume_for_actor_v49e(
                    transport_session_id=self._authority.transport_session_id,
                    driver_evidence_nonce_sha256=(control.driver_evidence_nonce_sha256),
                    deadline_ns=deadline,
                    ciphertext_batch_sha256=attempt.ciphertext_batch_sha256,
                    ciphertext_start_octet=attempt.ciphertext_start_octet,
                    requested_octets=attempt.requested_octets,
                )
                if consumed is not exc:
                    raise PhysicalTransportSessionActorV49CError(
                        "owner substituted TLS send no-acceptance evidence"
                    ) from exc
                observed_at, observed_monotonic_ns = self._sample_observation()
                wall_due = observed_at >= command.shutdown_deadline_at
                monotonic_due = observed_monotonic_ns >= deadline
                if wall_due != monotonic_due:
                    failure_kind = KernelSendFailureKindV49E.CLOCK_DISAGREEMENT
                    evidence: dict[str, Any] = {}
                elif wall_due:
                    failure_kind = (
                        KernelSendFailureKindV49E.DEADLINE_EXPIRED_NO_KERNEL_ACCEPTANCE
                    )
                    evidence = {
                        "owner_evidence_id": exc.owner_evidence_id,
                        "kernel_socket_identity": exc.kernel_socket_identity,
                        "driver_evidence_nonce_sha256": (
                            exc.driver_evidence_nonce_sha256
                        ),
                        "send_kind": exc.send_kind,
                        "transport_sequence": exc.transport_sequence,
                        "exact_slice_sha256": exc.exact_slice_sha256,
                        "would_block_count": exc.would_block_count,
                        "driver_evidence_id": exc.driver_evidence_id,
                    }
                else:
                    raise PhysicalTransportSessionActorV49CError(
                        "owner send deadline precedes both actor command clocks"
                    ) from exc
                await self._record_tls_control_send_failure_locked(
                    command_event=command_event,
                    control_event=control_event,
                    attempt_event=attempt_event,
                    attempt=attempt,
                    layer=layer,
                    failure_kind=failure_kind,
                    observed_at=observed_at,
                    observed_monotonic_ns=observed_monotonic_ns,
                    signer=signer,
                    **evidence,
                )
                raise
            except (
                LocalShutdownCommandDeadlineDueV49E,
                LocalShutdownCommandClockDisagreementV49E,
            ):
                raise
            except BaseException:
                self._side_effect_fault_latched = True
                self._fault_reason = "TLS-control send outcome is ambiguous"
                if (
                    not self._storage_fault_latched
                    and self._terminal_state.pending_send_attempt_id
                    == attempt_event.transport_actor_event_id
                ):
                    try:
                        self._side_effect_fault_latched = False
                        await self._converge_unknown_tls_control_send_locked(
                            signer=signer
                        )
                    finally:
                        self._side_effect_fault_latched = True
                raise

    async def half_close_tcp_write_v49e(
        self,
        command_event: TransportActorEventV49C,
        control_event: TransportActorEventV49C,
        prepared_control: Any,
        *,
        prepare_token_effect: TcpHalfCloseTokenEffectV49E,
        shutdown_effect: TcpHalfCloseEffectV49E,
        signer: Any,
    ) -> TransportActorEventV49C:
        """Perform exactly one owner-tokenized ``shutdown(SHUT_WR)``."""

        from .physical_transport_linux_v4 import (
            LinuxSocketOwnerV4DeadlineExpiredNoObservationV49E,
            TcpWriteShutdownErrorCodeV49E,
            TcpWriteShutdownResultV49E,
            TcpWriteShutdownTokenV49E,
        )
        from .physical_transport_tls_v49 import PreparedTlsControlCiphertextV49E

        self._assert_owner()
        async with self._lock:
            self._assert_progress_allowed()
            command = self._require_local_shutdown_command_v49e(command_event)
            self._require_exact_actor_event(
                control_event,
                TransportActorEventKindV49C.TLS_CONTROL_CIPHERTEXT_PREPARED,
            )
            control = control_event.payload
            assert type(control) is TlsControlCiphertextPreparedPayloadV49E
            operation_event = self._events_by_id[
                control.tls_protocol_operation_started_event_id
            ]
            operation = operation_event.payload
            assert type(operation) is TlsProtocolOperationStartedPayloadV49E
            retained = self._v49e_prepared_control_capabilities.get(
                control_event.transport_actor_event_id
            )
            if (
                control.control_kind is not TlsControlOutputKindV49E.LOCAL_CLOSE_NOTIFY
                or operation.local_shutdown_command_started_event_id
                != command_event.transport_actor_event_id
                or not self._terminal_state.tls_close_notify_fully_kernel_accepted
                or type(prepared_control) is not PreparedTlsControlCiphertextV49E
                or retained is not prepared_control
            ):
                raise PhysicalTransportSessionActorV49CQueueError(
                    "TCP half-close requires the exact completed local TLS control"
                )
            effect_ready_at, effect_ready_monotonic_ns = self._sample_observation()
            try:
                self._raise_if_local_shutdown_deadline_due_v49e(
                    command_event,
                    (effect_ready_at, effect_ready_monotonic_ns),
                )
            except LocalShutdownCommandDeadlineDueV49E:
                await self._converge_terminal_payload_locked(
                    self._terminal_payload(
                        TerminalTransitionKindV49C.TIMEOUT,
                        cause_code=(V49E_LOCAL_SHUTDOWN_COMMAND_DEADLINE_EXPIRED_CAUSE),
                    ),
                    signer=signer,
                    recorded_observation=(
                        effect_ready_at,
                        effect_ready_monotonic_ns,
                    ),
                )
                raise
            except LocalShutdownCommandClockDisagreementV49E:
                await self._converge_terminal_payload_locked(
                    self._terminal_payload(
                        TerminalTransitionKindV49C.FATAL,
                        cause_code=V49E_LOCAL_SHUTDOWN_CLOCK_DISAGREEMENT_CAUSE,
                    ),
                    signer=signer,
                    recorded_observation=(
                        effect_ready_at,
                        effect_ready_monotonic_ns,
                    ),
                )
                raise
            try:
                observed_token = prepare_token_effect(
                    deadline_ns=command.shutdown_deadline_monotonic_ns
                )
                token = (
                    await observed_token
                    if inspect.isawaitable(observed_token)
                    else observed_token
                )
                if type(token) is not TcpWriteShutdownTokenV49E:
                    raise TypeError(
                        "prepare_token_effect must return exact "
                        "TcpWriteShutdownTokenV49E"
                    )
                consumed_token = token.consume_for_actor_v49e(
                    transport_session_id=self._authority.transport_session_id,
                    tls_control_sequence=control.control_sequence,
                    tls_ciphertext_batch_sha256=(control.ciphertext_batch_sha256),
                    tls_ciphertext_octets=control.ciphertext_octets,
                    shutdown_deadline_monotonic_ns=(
                        command.shutdown_deadline_monotonic_ns
                    ),
                )
                if consumed_token is not token:
                    raise PhysicalTransportSessionActorV49CError(
                        "owner returned a substituted SHUT_WR token"
                    )
                expected_token_id = sha256_digest(
                    {
                        "domain": "RiskYieldMMTcpWriteShutdownTokenV4_9E",
                        "token_sequence": token.token_sequence,
                        "transport_session_id": token.transport_session_id,
                        "tls_control_sequence": token.tls_control_sequence,
                        "tls_ciphertext_batch_sha256": (
                            token.tls_ciphertext_batch_sha256
                        ),
                        "tls_ciphertext_octets": token.tls_ciphertext_octets,
                        "shutdown_deadline_monotonic_ns": (
                            token.shutdown_deadline_monotonic_ns
                        ),
                    }
                )
                if (
                    token.token_sequence != 1
                    or token.transport_session_id
                    != self._authority.transport_session_id
                    or token.tls_control_sequence != control.control_sequence
                    or token.tls_ciphertext_batch_sha256
                    != control.ciphertext_batch_sha256
                    or token.tls_ciphertext_octets != control.ciphertext_octets
                    or token.shutdown_deadline_monotonic_ns
                    != command.shutdown_deadline_monotonic_ns
                    or token.shutdown_token_id != expected_token_id
                ):
                    raise PhysicalTransportSessionActorV49CQueueError(
                        "owner SHUT_WR token differs from durable local TLS evidence"
                    )
            except LinuxSocketOwnerV4DeadlineExpiredNoObservationV49E as exc:
                consumed = exc.consume_for_actor_v49e(
                    transport_session_id=self._authority.transport_session_id,
                    driver_evidence_nonce_sha256=(
                        operation.driver_evidence_nonce_sha256
                    ),
                    operation="TCP_WRITE_SHUTDOWN_TOKEN_PREPARATION",
                    deadline_ns=command.shutdown_deadline_monotonic_ns,
                )
                if consumed is not exc:
                    raise PhysicalTransportSessionActorV49CError(
                        "owner substituted SHUT_WR preparation deadline evidence"
                    ) from exc
                await self._record_owner_no_observation_deadline_locked_v49e(
                    command_event,
                    exc,
                    signer=signer,
                )
                raise
            except BaseException:
                if not self._terminal_state.is_terminal:
                    await self._converge_terminal_payload_locked(
                        self._terminal_payload(
                            TerminalTransitionKindV49C.FATAL,
                            cause_code=(
                                _V49E_TCP_HALF_CLOSE_TOKEN_PREPARATION_ERROR_CAUSE
                            ),
                        ),
                        signer=signer,
                    )
                raise
            attempted_at, attempted_monotonic_ns = self._sample_observation()
            try:
                self._raise_if_local_shutdown_deadline_due_v49e(
                    command_event,
                    (attempted_at, attempted_monotonic_ns),
                )
            except LocalShutdownCommandDeadlineDueV49E:
                await self._converge_terminal_payload_locked(
                    self._terminal_payload(
                        TerminalTransitionKindV49C.TIMEOUT,
                        cause_code=(V49E_LOCAL_SHUTDOWN_COMMAND_DEADLINE_EXPIRED_CAUSE),
                    ),
                    signer=signer,
                    recorded_observation=(attempted_at, attempted_monotonic_ns),
                )
                raise
            except LocalShutdownCommandClockDisagreementV49E:
                await self._converge_terminal_payload_locked(
                    self._terminal_payload(
                        TerminalTransitionKindV49C.FATAL,
                        cause_code=V49E_LOCAL_SHUTDOWN_CLOCK_DISAGREEMENT_CAUSE,
                    ),
                    signer=signer,
                    recorded_observation=(attempted_at, attempted_monotonic_ns),
                )
                raise
            attempt = TcpHalfCloseAttemptPayloadV49E(
                tls_close_notify_sent_event_id=self._latest_terminal_marker_id(
                    TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_SENT
                ),
                tls_control_ciphertext_prepared_event_id=(
                    control_event.transport_actor_event_id
                ),
                shutdown_token_id=token.shutdown_token_id,
                token_sequence=token.token_sequence,
                tls_control_sequence=token.tls_control_sequence,
                tls_ciphertext_batch_sha256=token.tls_ciphertext_batch_sha256,
                tls_ciphertext_octets=token.tls_ciphertext_octets,
                local_shutdown_command_started_event_id=(
                    command_event.transport_actor_event_id
                ),
                shutdown_deadline_monotonic_ns=(command.shutdown_deadline_monotonic_ns),
                shutdown_how="SHUT_WR",
                attempted_at=attempted_at,
                attempted_monotonic_ns=attempted_monotonic_ns,
            )
            attempt_event = await self._append_payload_locked(attempt)
            try:
                observed_result = shutdown_effect(
                    token,
                    deadline_ns=command.shutdown_deadline_monotonic_ns,
                )
                result = (
                    await observed_result
                    if inspect.isawaitable(observed_result)
                    else observed_result
                )
                if (
                    type(result) is not TcpWriteShutdownResultV49E
                    or result.shutdown_token is not token
                    or result.shutdown_how != socket.SHUT_WR
                ):
                    raise PhysicalTransportSessionActorV49CError(
                        "shutdown effect returned a wrong or copied owner result"
                    )
                consumed_result = result.consume_for_actor_v49e(
                    transport_session_id=self._authority.transport_session_id,
                    shutdown_token=token,
                )
                if consumed_result is not result:
                    raise PhysicalTransportSessionActorV49CError(
                        "owner returned a substituted SHUT_WR result"
                    )
                error_code = (
                    None if result.error_code is None else result.error_code.value
                )
                expected_result_id = sha256_digest(
                    {
                        "domain": "RiskYieldMMTcpWriteShutdownResultV4_9E",
                        "shutdown_token_id": token.shutdown_token_id,
                        "shutdown_how": socket.SHUT_WR,
                        "kernel_accepted": result.kernel_accepted,
                        "error_code": error_code,
                    }
                )
                if (
                    result.kernel_accepted != (error_code is None)
                    or result.shutdown_result_id != expected_result_id
                ):
                    raise PhysicalTransportSessionActorV49CError(
                        "owner SHUT_WR result differs from its exact identity"
                    )
                self._authorize_terminal_clock_after_evidence_v49e(result)
                observed_at, observed_monotonic_ns = self._sample_observation()
                if result.error_code is (
                    TcpWriteShutdownErrorCodeV49E.DEADLINE_EXPIRED_BEFORE_SYSCALL
                ):
                    wall_due = observed_at >= command.shutdown_deadline_at
                    monotonic_due = (
                        observed_monotonic_ns >= command.shutdown_deadline_monotonic_ns
                    )
                    if wall_due and monotonic_due:
                        negative_result_kind = (
                            TcpHalfCloseResultKindV49E.DEADLINE_EXPIRED_BEFORE_SYSCALL
                        )
                    elif wall_due != monotonic_due:
                        negative_result_kind = (
                            TcpHalfCloseResultKindV49E.CLOCK_DISAGREEMENT
                        )
                    else:
                        negative_result_kind = TcpHalfCloseResultKindV49E.ERROR
                else:
                    negative_result_kind = TcpHalfCloseResultKindV49E.ERROR
                result_payload = TcpHalfCloseResultPayloadV49E(
                    tcp_half_close_attempt_event_id=(
                        attempt_event.transport_actor_event_id
                    ),
                    shutdown_token_id=token.shutdown_token_id,
                    shutdown_result_id=result.shutdown_result_id,
                    shutdown_how="SHUT_WR",
                    result_kind=(
                        TcpHalfCloseResultKindV49E.KERNEL_ACCEPTED
                        if result.kernel_accepted
                        else negative_result_kind
                    ),
                    error_code=error_code,
                    observed_at=observed_at,
                    observed_monotonic_ns=observed_monotonic_ns,
                )
                if result.kernel_accepted:
                    observations = self._sample_observation_batch(2)
                    result_event = self._candidate_event_for_prefix(
                        result_payload,
                        self._events,
                        recorded_observation=observations[0],
                    )
                    marker_event = self._candidate_event_for_prefix(
                        self._terminal_payload(TerminalTransitionKindV49C.TCP_FIN_SENT),
                        (*self._events, result_event),
                        recorded_observation=observations[1],
                    )
                    await self._append_candidate_batch_locked(
                        (result_event, marker_event)
                    )
                    self._v49e_prepared_control_capabilities.pop(
                        control_event.transport_actor_event_id,
                        None,
                    )
                    return marker_event

                await self._append_payload_locked(result_payload)
                if (
                    result_payload.result_kind
                    is TcpHalfCloseResultKindV49E.DEADLINE_EXPIRED_BEFORE_SYSCALL
                ):
                    terminal_kind = TerminalTransitionKindV49C.TIMEOUT
                    terminal_cause = (
                        V49E_TCP_HALF_CLOSE_DEADLINE_EXPIRED_BEFORE_SYSCALL_CAUSE
                    )
                elif (
                    result_payload.result_kind
                    is TcpHalfCloseResultKindV49E.CLOCK_DISAGREEMENT
                ):
                    terminal_kind = TerminalTransitionKindV49C.FATAL
                    terminal_cause = V49E_LOCAL_SHUTDOWN_CLOCK_DISAGREEMENT_CAUSE
                else:
                    terminal_kind = TerminalTransitionKindV49C.FATAL
                    terminal_cause = V49E_TCP_HALF_CLOSE_ERROR_CAUSE
                await self._converge_terminal_payload_locked(
                    self._terminal_payload(
                        terminal_kind,
                        cause_code=terminal_cause,
                    ),
                    signer=signer,
                )
                return self._events[-1]
            except BaseException:
                if (
                    not self._storage_fault_latched
                    and not self._terminal_state.is_terminal
                    and self._events
                    and self._events[-1].transport_actor_event_id
                    == attempt_event.transport_actor_event_id
                ):
                    await self._converge_terminal_payload_locked(
                        self._terminal_payload(
                            TerminalTransitionKindV49C.FATAL,
                            cause_code=V49E_TCP_HALF_CLOSE_OUTCOME_UNKNOWN_CAUSE,
                        ),
                        signer=signer,
                    )
                raise

    def _validate_owner_unsendable_tls_output_v49e(
        self,
        operation_event: TransportActorEventV49C,
        sealed_evidence: Any,
    ) -> Any:
        from .physical_transport_linux_v4 import (
            LinuxSocketOwnerV4,
            OwnerUnsendableTlsPostHandshakeOutputV49E,
        )

        self._require_exact_actor_event(
            operation_event,
            TransportActorEventKindV49C.TLS_PROTOCOL_OPERATION_STARTED,
        )
        operation = operation_event.payload
        assert type(operation) is TlsProtocolOperationStartedPayloadV49E
        if operation.purpose is not TlsProtocolOperationPurposeV49E.PEER_SHUTDOWN_POLL:
            raise PhysicalTransportSessionActorV49CQueueError(
                "unsendable TLS output requires a peer-poll operation"
            )
        if type(sealed_evidence) is not OwnerUnsendableTlsPostHandshakeOutputV49E:
            raise TypeError(
                "sealed_evidence must be exact "
                "OwnerUnsendableTlsPostHandshakeOutputV49E"
            )
        LinuxSocketOwnerV4._assert_owner_unsendable_tls_output_integrity_v49e(  # noqa: SLF001
            sealed_evidence
        )
        if (
            sealed_evidence.transport_session_id != self._authority.transport_session_id
            or sealed_evidence.driver_evidence_nonce_sha256
            != operation.driver_evidence_nonce_sha256
        ):
            raise PhysicalTransportSessionActorV49CError(
                "owner unsendable TLS output differs from exact actor authority"
            )
        return sealed_evidence

    async def record_unsendable_tls_output_v49e(
        self,
        operation_event: TransportActorEventV49C,
        sealed_evidence: Any,
        *,
        signer: Any,
    ) -> ActorTerminalConvergenceResultV49E:
        """Terminalize exact owner-bound post-SHUT_WR negative evidence."""

        self._assert_owner()
        async with self._lock:
            self._require_exact_actor_event(
                operation_event,
                TransportActorEventKindV49C.TLS_PROTOCOL_OPERATION_STARTED,
            )
            operation = operation_event.payload
            assert type(operation) is TlsProtocolOperationStartedPayloadV49E
            try:
                consumed = sealed_evidence.consume_for_actor_v49e(
                    transport_session_id=self._authority.transport_session_id,
                    driver_evidence_nonce_sha256=(
                        operation.driver_evidence_nonce_sha256
                    ),
                )
                if consumed is not sealed_evidence:
                    raise PhysicalTransportSessionActorV49CError(
                        "owner returned substituted unsendable TLS evidence"
                    )
                evidence = self._validate_owner_unsendable_tls_output_v49e(
                    operation_event,
                    consumed,
                )
                self._authorize_terminal_clock_after_evidence_v49e(evidence)
            except BaseException:
                if not self._terminal_state.is_terminal:
                    await self._record_tls_operation_failure_locked(
                        operation_event,
                        failure_kind=(TlsProtocolOperationFailureKindV49E.DRIVER_ERROR),
                        signer=signer,
                    )
                raise
            return await self._record_tls_operation_failure_locked(
                operation_event,
                failure_kind=(
                    TlsProtocolOperationFailureKindV49E.UNSENDABLE_POST_HANDSHAKE_OUTPUT_AFTER_SHUT_WR
                ),
                signer=signer,
                unsendable_driver_output_sequence=(
                    evidence.driver_evidence.output_sequence
                ),
                unsendable_driver_evidence_id=(
                    evidence.driver_evidence.unsendable_output_id
                ),
                unsendable_owner_evidence_id=(evidence.owner_unsendable_output_id),
                unsendable_kernel_socket_identity=(evidence.kernel_socket_identity),
                unsendable_ciphertext_sha256=evidence.ciphertext_sha256,
                unsendable_ciphertext_octets=evidence.ciphertext_octets,
            )

    def _validate_owner_tls_shutdown_observation_v49e(
        self,
        operation_event: TransportActorEventV49C,
        owner_observation: Any,
    ) -> tuple[Any, TlsShutdownObservationKindV49E]:
        from .physical_transport_linux_v4 import (
            LinuxSocketOwnerV4,
            OwnerTlsShutdownObservationV49E,
        )

        if type(owner_observation) is not OwnerTlsShutdownObservationV49E:
            raise TypeError(
                "observation_effect must return exact OwnerTlsShutdownObservationV49E"
            )
        operation = operation_event.payload
        assert type(operation) is TlsProtocolOperationStartedPayloadV49E
        consumed = owner_observation.consume_for_actor_v49e(
            transport_session_id=self._authority.transport_session_id,
            driver_evidence_nonce_sha256=(operation.driver_evidence_nonce_sha256),
        )
        if consumed is not owner_observation:
            raise PhysicalTransportSessionActorV49CError(
                "owner returned a substituted TLS shutdown observation"
            )
        LinuxSocketOwnerV4._assert_owner_tls_shutdown_observation_integrity_v49e(  # noqa: SLF001
            owner_observation
        )
        driver_observation = owner_observation.driver_observation
        if (
            owner_observation.transport_session_id
            != self._authority.transport_session_id
            or driver_observation.driver_evidence_nonce_sha256
            != operation.driver_evidence_nonce_sha256
        ):
            raise PhysicalTransportSessionActorV49CError(
                "owner shutdown observation differs from exact actor authority"
            )
        return (
            driver_observation,
            TlsShutdownObservationKindV49E(driver_observation.observation_kind.value),
        )

    async def observe_tls_shutdown_v49e(
        self,
        operation_event: TransportActorEventV49C,
        *,
        observation_effect: TlsShutdownObservationEffectV49E,
        signer: Any,
    ) -> TlsShutdownObservationOutcomeV49E:
        """Record one owner-sealed TLS/EOF fact and its exact layer marker."""

        from .physical_transport_linux_v4 import (
            LinuxSocketOwnerV4DeadlineExpiredAfterProgressV49E,
            LinuxSocketOwnerV4DeadlineExpiredNoObservationV49E,
            LinuxSocketOwnerV4UnsendablePostHandshakeOutput,
        )

        self._assert_owner()
        async with self._lock:
            self._require_exact_actor_event(
                operation_event,
                TransportActorEventKindV49C.TLS_PROTOCOL_OPERATION_STARTED,
            )
            operation = operation_event.payload
            assert type(operation) is TlsProtocolOperationStartedPayloadV49E
            command_event = self._events_by_id[
                operation.local_shutdown_command_started_event_id
            ]
            command = command_event.payload
            assert type(command) is LocalShutdownCommandStartedPayloadV49E
            if operation.purpose is not (
                TlsProtocolOperationPurposeV49E.PEER_SHUTDOWN_POLL
            ):
                raise PhysicalTransportSessionActorV49CQueueError(
                    "shutdown observation requires a peer-poll operation"
                )

            # Only the physical effect and validation of its sealed return value
            # are classified as driver outcomes.  Persistence starts below this
            # block so a journal failure can never be rewritten as DRIVER_ERROR.
            try:
                observed = observation_effect(
                    deadline_ns=command.shutdown_deadline_monotonic_ns
                )
                owner_observation = (
                    await observed if inspect.isawaitable(observed) else observed
                )
                driver_observation, actor_kind = (
                    self._validate_owner_tls_shutdown_observation_v49e(
                        operation_event,
                        owner_observation,
                    )
                )
                self._authorize_terminal_clock_after_evidence_v49e(owner_observation)
            except LinuxSocketOwnerV4DeadlineExpiredNoObservationV49E as exc:
                if (
                    exc.operation != "TLS_SHUTDOWN_POLL"
                    or exc.deadline_ns != command.shutdown_deadline_monotonic_ns
                ):
                    if not self._terminal_state.is_terminal:
                        await self._record_tls_operation_failure_locked(
                            operation_event,
                            failure_kind=(
                                TlsProtocolOperationFailureKindV49E.DRIVER_ERROR
                            ),
                            signer=signer,
                        )
                    raise
                consumed = exc.consume_for_actor_v49e(
                    transport_session_id=self._authority.transport_session_id,
                    driver_evidence_nonce_sha256=(
                        operation.driver_evidence_nonce_sha256
                    ),
                    operation="TLS_SHUTDOWN_POLL",
                    deadline_ns=command.shutdown_deadline_monotonic_ns,
                )
                if consumed is not exc:
                    raise PhysicalTransportSessionActorV49CError(
                        "owner substituted shutdown-poll deadline evidence"
                    ) from exc
                self._authorize_terminal_clock_after_evidence_v49e(exc)
                if not self._terminal_state.is_terminal:
                    await self._record_tls_operation_failure_locked(
                        operation_event,
                        failure_kind=(
                            TlsProtocolOperationFailureKindV49E.DEADLINE_EXPIRED_NO_OBSERVATION
                        ),
                        signer=signer,
                        deadline_no_observation_owner_evidence_id=(
                            exc.owner_evidence_id
                        ),
                        deadline_no_observation_kernel_socket_identity=(
                            exc.kernel_socket_identity
                        ),
                        deadline_no_observation_operation=exc.operation,
                    )
                raise
            except LinuxSocketOwnerV4DeadlineExpiredAfterProgressV49E as exc:
                consumed = exc.consume_for_actor_v49e(
                    transport_session_id=self._authority.transport_session_id,
                    driver_evidence_nonce_sha256=(
                        operation.driver_evidence_nonce_sha256
                    ),
                    operation="TLS_SHUTDOWN_POLL",
                    deadline_ns=command.shutdown_deadline_monotonic_ns,
                )
                if consumed is not exc:
                    raise PhysicalTransportSessionActorV49CError(
                        "owner substituted partial shutdown deadline evidence"
                    ) from exc
                self._authorize_terminal_clock_after_evidence_v49e(exc)
                await self._record_tls_operation_failure_locked(
                    operation_event,
                    failure_kind=(
                        TlsProtocolOperationFailureKindV49E.DEADLINE_EXPIRED_AFTER_PROGRESS
                    ),
                    signer=signer,
                    deadline_after_progress_owner_evidence_id=(exc.owner_evidence_id),
                    deadline_after_progress_driver_evidence_id=(exc.driver_evidence_id),
                    deadline_after_progress_kernel_socket_identity=(
                        exc.kernel_socket_identity
                    ),
                    deadline_after_progress_operation=exc.operation,
                    deadline_after_progress_ciphertext_sha256=(exc.ciphertext_sha256),
                    deadline_after_progress_ciphertext_octets=(
                        exc.ciphertext_octets_received
                    ),
                )
                raise
            except LinuxSocketOwnerV4UnsendablePostHandshakeOutput as exc:
                try:
                    consumed = exc.consume_for_actor_v49e(
                        transport_session_id=(self._authority.transport_session_id),
                        driver_evidence_nonce_sha256=(
                            operation.driver_evidence_nonce_sha256
                        ),
                    )
                    if consumed is not exc.evidence:
                        raise PhysicalTransportSessionActorV49CError(
                            "owner returned substituted unsendable TLS evidence"
                        )
                    evidence = self._validate_owner_unsendable_tls_output_v49e(
                        operation_event,
                        consumed,
                    )
                    self._authorize_terminal_clock_after_evidence_v49e(evidence)
                except BaseException:
                    if not self._terminal_state.is_terminal:
                        await self._record_tls_operation_failure_locked(
                            operation_event,
                            failure_kind=(
                                TlsProtocolOperationFailureKindV49E.DRIVER_ERROR
                            ),
                            signer=signer,
                        )
                    raise
                await self._record_tls_operation_failure_locked(
                    operation_event,
                    failure_kind=(
                        TlsProtocolOperationFailureKindV49E.UNSENDABLE_POST_HANDSHAKE_OUTPUT_AFTER_SHUT_WR
                    ),
                    signer=signer,
                    unsendable_driver_output_sequence=(
                        evidence.driver_evidence.output_sequence
                    ),
                    unsendable_driver_evidence_id=(
                        evidence.driver_evidence.unsendable_output_id
                    ),
                    unsendable_owner_evidence_id=(evidence.owner_unsendable_output_id),
                    unsendable_kernel_socket_identity=(evidence.kernel_socket_identity),
                    unsendable_ciphertext_sha256=evidence.ciphertext_sha256,
                    unsendable_ciphertext_octets=evidence.ciphertext_octets,
                )
                raise
            except BaseException:
                if not self._terminal_state.is_terminal:
                    await self._record_tls_operation_failure_locked(
                        operation_event,
                        failure_kind=(TlsProtocolOperationFailureKindV49E.DRIVER_ERROR),
                        signer=signer,
                    )
                raise

            observations = self._sample_observation_batch(3)
            observed_at, observed_monotonic_ns = observations[0]
            payload = TlsShutdownObservedPayloadV49E(
                tls_protocol_operation_started_event_id=(
                    operation_event.transport_actor_event_id
                ),
                tls_operation_id=operation.tls_operation_id,
                observation_sequence=driver_observation.observation_sequence,
                observation_kind=actor_kind,
                driver_evidence_nonce_sha256=(
                    driver_observation.driver_evidence_nonce_sha256
                ),
                peer_close_notify_received=(
                    driver_observation.peer_close_notify_received
                ),
                tcp_eof_received=driver_observation.tcp_eof_received,
                truncated=driver_observation.truncated,
                ciphertext_octets_received=(
                    driver_observation.ciphertext_octets_received
                ),
                observation_id=driver_observation.observation_id,
                owner_observation_id=owner_observation.owner_observation_id,
                owner_kernel_socket_identity=(owner_observation.kernel_socket_identity),
                observed_at=observed_at,
                observed_monotonic_ns=observed_monotonic_ns,
            )
            marker_kind = (
                TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_RECEIVED
                if actor_kind is TlsShutdownObservationKindV49E.PEER_CLOSE_NOTIFY
                else TerminalTransitionKindV49C.TCP_EOF_RECEIVED
            )
            marker_payload = self._terminal_payload(marker_kind)
            prospective = advance_terminal_state_v49c(
                self._terminal_state,
                marker_payload,
            )
            observation_event = self._candidate_event_for_prefix(
                payload,
                self._events,
                recorded_observation=observations[0],
            )
            if prospective.is_terminal:
                await self._append_candidate_locked(observation_event)
                result = await self._converge_terminal_payload_locked(
                    self._terminal_payload(marker_kind),
                    signer=signer,
                    recorded_observation=observations[1],
                )
                return TlsShutdownObservationOutcomeV49E(
                    observation_event=observation_event,
                    marker_event=result.terminal_event,
                    terminal_convergence=result,
                )
            marker_event = self._candidate_event_for_prefix(
                marker_payload,
                (*self._events, observation_event),
                recorded_observation=observations[1],
            )
            await self._append_candidate_batch_locked((observation_event, marker_event))
            if all(
                (
                    self._terminal_state.ws_close_sent,
                    self._terminal_state.ws_close_received,
                    self._terminal_state.ws_output_fully_kernel_accepted,
                    self._terminal_state.tls_close_notify_sent,
                    self._terminal_state.tls_close_notify_received,
                    self._terminal_state.tls_close_notify_fully_kernel_accepted,
                    self._terminal_state.tcp_fin_sent,
                    self._terminal_state.tcp_eof_received,
                )
            ):
                convergence = await self._converge_terminal_payload_locked(
                    self._terminal_payload(TerminalTransitionKindV49C.CLEAN_ALL_LAYERS),
                    signer=signer,
                    recorded_observation=observations[2],
                )
                return TlsShutdownObservationOutcomeV49E(
                    observation_event=observation_event,
                    marker_event=marker_event,
                    terminal_convergence=convergence,
                )
            return TlsShutdownObservationOutcomeV49E(
                observation_event=observation_event,
                marker_event=marker_event,
            )

    async def _record_kernel_send_failure_locked(
        self,
        *,
        command_event: TransportActorEventV49C | None,
        wire_event: TransportActorEventV49C,
        tls_event: TransportActorEventV49C,
        attempt_event: TransportActorEventV49C,
        attempt: KernelSendAttemptPayloadV49C,
        obligation_layer: OutboundObligationLayerV49C,
        obligation_id: str,
        failure_kind: KernelSendFailureKindV49E,
        observed_at: datetime,
        observed_monotonic_ns: int,
        signer: Any,
        owner_evidence_id: str | None = None,
        kernel_socket_identity: str | None = None,
        driver_evidence_nonce_sha256: str | None = None,
        owner_deadline_operation: str | None = None,
        send_kind: str | None = None,
        transport_sequence: int | None = None,
        exact_slice_sha256: str | None = None,
        would_block_count: int | None = None,
        driver_evidence_id: str | None = None,
    ) -> ActorTerminalConvergenceResultV49E:
        wire = wire_event.payload
        assert type(wire) is OutboundWirePreparedPayloadV49C
        failure = KernelSendFailurePayloadV49E(
            kernel_send_attempt_event_id=attempt_event.transport_actor_event_id,
            tls_ciphertext_prepared_event_id=tls_event.transport_actor_event_id,
            kernel_attempt_ordinal=attempt.kernel_attempt_ordinal,
            ciphertext_batch_sha256=attempt.ciphertext_batch_sha256,
            ciphertext_octets=attempt.ciphertext_octets,
            ciphertext_start_octet=attempt.ciphertext_start_octet,
            requested_octets=attempt.requested_octets,
            local_shutdown_command_started_event_id=(
                None
                if command_event is None
                else command_event.transport_actor_event_id
            ),
            shutdown_deadline_monotonic_ns=wire.send_not_after_monotonic_ns,
            failure_kind=failure_kind,
            owner_evidence_id=owner_evidence_id,
            kernel_socket_identity=kernel_socket_identity,
            driver_evidence_nonce_sha256=driver_evidence_nonce_sha256,
            owner_deadline_operation=owner_deadline_operation,
            send_kind=send_kind,
            transport_sequence=transport_sequence,
            exact_slice_sha256=exact_slice_sha256,
            would_block_count=would_block_count,
            driver_evidence_id=driver_evidence_id,
            observed_at=observed_at,
            observed_monotonic_ns=observed_monotonic_ns,
        )
        observations = self._sample_observation_batch(2)
        failure_event = self._candidate_event_for_prefix(
            failure,
            self._events,
            recorded_observation=observations[0],
        )
        resolved_event = self._candidate_event_for_prefix(
            self._terminal_payload(
                TerminalTransitionKindV49C.SEND_ATTEMPT_RESOLVED,
                obligation_layer=obligation_layer,
                obligation_id=obligation_id,
                send_attempt_id=attempt_event.transport_actor_event_id,
            ),
            (*self._events, failure_event),
            recorded_observation=observations[1],
        )
        await self._append_candidate_batch_locked((failure_event, resolved_event))
        clock_disagreement = (
            failure_kind is KernelSendFailureKindV49E.CLOCK_DISAGREEMENT
        )
        return await self._converge_terminal_payload_locked(
            self._terminal_payload(
                (
                    TerminalTransitionKindV49C.FATAL
                    if clock_disagreement
                    else TerminalTransitionKindV49C.TIMEOUT
                ),
                cause_code=(
                    V49E_LOCAL_SHUTDOWN_CLOCK_DISAGREEMENT_CAUSE
                    if clock_disagreement
                    else (
                        V49E_LOCAL_SHUTDOWN_COMMAND_DEADLINE_EXPIRED_CAUSE
                        if command_event is not None
                        else V49E_WEBSOCKET_CLOSE_DEADLINE_EXPIRED_CAUSE
                    )
                ),
            ),
            signer=signer,
        )

    async def send_oldest_ciphertext(
        self,
        *,
        send_effect: KernelSendEffectV49C,
        requested_octets: int | None = None,
        terminal_signer: Any | None = None,
    ) -> KernelSendOutcomeV49C:
        """Perform one positive partial send under a durable write-ahead record.

        ``send_effect`` receives the exact remaining ciphertext slice and must
        return the positive count accepted by the local kernel.  Exceptions,
        cancellation, zero, and invalid counts are conservative UNKNOWN_SEND;
        the bytes are never replayed by this actor or by recovery.
        """

        from .physical_transport_linux_v4 import (
            LinuxSocketOwnerV4DeadlineExpiredNoObservationV49E,
            LinuxSocketOwnerV4SendDeadlineExpiredNoKernelAcceptanceV49E,
        )

        self._assert_owner()
        async with self._lock:
            self._assert_owner()
            self._assert_progress_allowed()
            tls_event, tls = self._active_tls()
            offset, ordinal, _ = self._send_progress(tls_event.transport_actor_event_id)
            remaining = tls.ciphertext_octets - offset
            if remaining <= 0:
                raise PhysicalTransportSessionActorV49CQueueError(
                    "prepared TLS ciphertext is already fully submitted"
                )
            requested = (
                remaining
                if requested_octets is None
                else canonical_safe_int(
                    requested_octets,
                    field="requested_octets",
                    minimum=1,
                    maximum=remaining,
                )
            )
            wire_event = self._events_by_id[tls.outbound_wire_prepared_event_id]
            wire = wire_event.payload
            assert type(wire) is OutboundWirePreparedPayloadV49C
            command_event = (
                self.local_shutdown_command_event_v49e
                if wire.wire_origin is OutboundWireOriginV49C.LOCAL_TERMINAL_COMMAND
                else None
            )
            command = (
                None
                if command_event is None
                else self._require_local_shutdown_command_v49e(command_event)
            )
            if command is not None and (
                wire.send_not_after != command.shutdown_deadline_at
                or wire.send_not_after_monotonic_ns
                != command.shutdown_deadline_monotonic_ns
            ):
                raise PhysicalTransportSessionActorV49CQueueError(
                    "local Close wire differs from its durable command deadline"
                )
            if wire.logical_opcode is WebSocketOpcodeV49C.CLOSE:
                if terminal_signer is None:
                    raise PhysicalTransportSessionActorV49CQueueError(
                        "WebSocket Close send requires V4.9E terminal_signer"
                    )
            elif terminal_signer is not None:
                raise PhysicalTransportSessionActorV49CQueueError(
                    "terminal_signer is reserved for WebSocket Close dispatch"
                )
            obligation_layer, obligation_id = self._current_obligation(wire_event)
            attempted_at, attempted_monotonic_ns = self._sample_observation()
            wall_due = attempted_at >= wire.send_not_after
            monotonic_due = attempted_monotonic_ns >= wire.send_not_after_monotonic_ns
            if wall_due or monotonic_due:
                if wire.logical_opcode is not WebSocketOpcodeV49C.CLOSE:
                    raise PhysicalTransportSessionActorV49CQueueError(
                        "oldest application wire deadline elapsed before send"
                    )
                kind = (
                    TerminalTransitionKindV49C.TIMEOUT
                    if wall_due == monotonic_due
                    else TerminalTransitionKindV49C.FATAL
                )
                cause = (
                    (
                        V49E_LOCAL_SHUTDOWN_COMMAND_DEADLINE_EXPIRED_CAUSE
                        if command_event is not None
                        else V49E_WEBSOCKET_CLOSE_DEADLINE_EXPIRED_CAUSE
                    )
                    if wall_due == monotonic_due
                    else V49E_LOCAL_SHUTDOWN_CLOCK_DISAGREEMENT_CAUSE
                )
                await self._converge_terminal_payload_locked(
                    self._terminal_payload(kind, cause_code=cause),
                    signer=terminal_signer,
                    recorded_observation=(attempted_at, attempted_monotonic_ns),
                )
                raise PhysicalTransportSessionActorV49CQueueError(
                    "oldest Close wire deadline is due or its clocks disagree"
                )
            attempt = KernelSendAttemptPayloadV49C(
                tls_ciphertext_prepared_event_id=tls_event.transport_actor_event_id,
                kernel_attempt_ordinal=ordinal + 1,
                ciphertext_batch_sha256=tls.ciphertext_batch_sha256,
                ciphertext_octets=tls.ciphertext_octets,
                ciphertext_start_octet=offset,
                requested_octets=requested,
                attempted_at=attempted_at,
                attempted_monotonic_ns=attempted_monotonic_ns,
            )
            attempt_observations = self._sample_observation_batch(2)
            attempt_event = self._candidate_event_for_prefix(
                attempt,
                self._events,
                recorded_observation=attempt_observations[0],
            )
            started_payload = self._terminal_payload(
                TerminalTransitionKindV49C.SEND_ATTEMPT_STARTED,
                obligation_layer=obligation_layer,
                obligation_id=obligation_id,
                send_attempt_id=attempt_event.transport_actor_event_id,
            )
            started_event = self._candidate_event_for_prefix(
                started_payload,
                (*self._events, attempt_event),
                recorded_observation=attempt_observations[1],
            )
            await self._append_candidate_batch_locked((attempt_event, started_event))

            effect_ready_at, effect_ready_monotonic_ns = self._sample_observation()
            wall_due = effect_ready_at >= wire.send_not_after
            monotonic_due = (
                effect_ready_monotonic_ns >= wire.send_not_after_monotonic_ns
            )
            if wall_due or monotonic_due:
                if wire.logical_opcode is not WebSocketOpcodeV49C.CLOSE:
                    await self._append_unknown_send_locked(
                        cause_code="SEND_DEADLINE_ELAPSED_AFTER_WRITE_AHEAD",
                        signer=terminal_signer,
                    )
                    raise PhysicalTransportSessionActorV49CQueueError(
                        "application wire deadline elapsed after write-ahead"
                    )
                await self._record_kernel_send_failure_locked(
                    command_event=command_event,
                    wire_event=wire_event,
                    tls_event=tls_event,
                    attempt_event=attempt_event,
                    attempt=attempt,
                    obligation_layer=obligation_layer,
                    obligation_id=obligation_id,
                    failure_kind=(
                        KernelSendFailureKindV49E.DEADLINE_EXPIRED_BEFORE_CALLBACK
                        if wall_due == monotonic_due
                        else KernelSendFailureKindV49E.CLOCK_DISAGREEMENT
                    ),
                    observed_at=effect_ready_at,
                    observed_monotonic_ns=effect_ready_monotonic_ns,
                    signer=terminal_signer,
                )
                raise PhysicalTransportSessionActorV49CQueueError(
                    "wire deadline elapsed after durable send write-ahead; "
                    "kernel effect was not invoked"
                )

            ciphertext = b"".join(
                base64.b64decode(chunk, validate=True)
                for chunk in tls.ordered_ciphertext_chunks_base64
            )
            exact_slice = ciphertext[offset : offset + requested]
            try:
                observed = (
                    send_effect(
                        exact_slice,
                        deadline_ns=wire.send_not_after_monotonic_ns,
                    )
                    if wire.logical_opcode is WebSocketOpcodeV49C.CLOSE
                    else send_effect(exact_slice)
                )
                accepted = await observed if inspect.isawaitable(observed) else observed
                if type(accepted) is not int or not 1 <= accepted <= requested:
                    raise PhysicalTransportSessionActorV49CError(
                        "kernel send must report one exact positive accepted count"
                    )
                observed_at, observed_monotonic_ns = self._sample_observation()
                result = KernelSendResultPayloadV49C(
                    kernel_send_attempt_event_id=(
                        attempt_event.transport_actor_event_id
                    ),
                    tls_ciphertext_prepared_event_id=(
                        tls_event.transport_actor_event_id
                    ),
                    kernel_attempt_ordinal=attempt.kernel_attempt_ordinal,
                    ciphertext_batch_sha256=attempt.ciphertext_batch_sha256,
                    ciphertext_octets=attempt.ciphertext_octets,
                    ciphertext_start_octet=attempt.ciphertext_start_octet,
                    requested_octets=attempt.requested_octets,
                    accepted_octets=accepted,
                    resulting_ciphertext_offset=offset + accepted,
                    observed_at=observed_at,
                    observed_monotonic_ns=observed_monotonic_ns,
                )
                result_observations = self._sample_observation_batch(2)
                result_event = self._candidate_event_for_prefix(
                    result,
                    self._events,
                    recorded_observation=result_observations[0],
                )
                resolved_payload = self._terminal_payload(
                    TerminalTransitionKindV49C.SEND_ATTEMPT_RESOLVED,
                    obligation_layer=obligation_layer,
                    obligation_id=obligation_id,
                    send_attempt_id=attempt_event.transport_actor_event_id,
                )
                resolved_event = self._candidate_event_for_prefix(
                    resolved_payload,
                    (*self._events, result_event),
                    recorded_observation=result_observations[1],
                )
                await self._append_candidate_batch_locked(
                    (result_event, resolved_event)
                )
            except LinuxSocketOwnerV4DeadlineExpiredNoObservationV49E as exc:
                if wire.logical_opcode is not WebSocketOpcodeV49C.CLOSE:
                    raise PhysicalTransportSessionActorV49CError(
                        "owner returned Close-only deadline evidence for data"
                    ) from exc
                consumed = exc.consume_for_actor_v49e(
                    transport_session_id=self._authority.transport_session_id,
                    driver_evidence_nonce_sha256=(exc.driver_evidence_nonce_sha256),
                    operation="WEBSOCKET_CLOSE_SEND_BEFORE_SYSCALL",
                    deadline_ns=wire.send_not_after_monotonic_ns,
                )
                if consumed is not exc:
                    raise PhysicalTransportSessionActorV49CError(
                        "owner substituted Close pre-syscall evidence"
                    ) from exc
                observed_at, observed_monotonic_ns = self._sample_observation()
                wall_due = observed_at >= wire.send_not_after
                monotonic_due = (
                    observed_monotonic_ns >= wire.send_not_after_monotonic_ns
                )
                if wall_due != monotonic_due:
                    failure_kind = KernelSendFailureKindV49E.CLOCK_DISAGREEMENT
                    evidence: dict[str, Any] = {}
                elif wall_due:
                    failure_kind = (
                        KernelSendFailureKindV49E.DEADLINE_EXPIRED_BEFORE_SYSCALL
                    )
                    evidence = {
                        "owner_evidence_id": exc.owner_evidence_id,
                        "kernel_socket_identity": exc.kernel_socket_identity,
                        "driver_evidence_nonce_sha256": (
                            exc.driver_evidence_nonce_sha256
                        ),
                        "owner_deadline_operation": exc.operation,
                    }
                else:
                    raise PhysicalTransportSessionActorV49CError(
                        "owner Close deadline precedes both actor wire clocks"
                    ) from exc
                await self._record_kernel_send_failure_locked(
                    command_event=command_event,
                    wire_event=wire_event,
                    tls_event=tls_event,
                    attempt_event=attempt_event,
                    attempt=attempt,
                    obligation_layer=obligation_layer,
                    obligation_id=obligation_id,
                    failure_kind=failure_kind,
                    observed_at=observed_at,
                    observed_monotonic_ns=observed_monotonic_ns,
                    signer=terminal_signer,
                    **evidence,
                )
                raise
            except LinuxSocketOwnerV4SendDeadlineExpiredNoKernelAcceptanceV49E as exc:
                if wire.logical_opcode is not WebSocketOpcodeV49C.CLOSE:
                    raise PhysicalTransportSessionActorV49CError(
                        "owner returned Close-only send evidence for data"
                    ) from exc
                consumed = exc.consume_for_actor_v49e(
                    transport_session_id=self._authority.transport_session_id,
                    driver_evidence_nonce_sha256=(exc.driver_evidence_nonce_sha256),
                    deadline_ns=wire.send_not_after_monotonic_ns,
                    ciphertext_batch_sha256=attempt.ciphertext_batch_sha256,
                    ciphertext_start_octet=attempt.ciphertext_start_octet,
                    requested_octets=attempt.requested_octets,
                )
                if consumed is not exc:
                    raise PhysicalTransportSessionActorV49CError(
                        "owner substituted Close no-acceptance evidence"
                    ) from exc
                observed_at, observed_monotonic_ns = self._sample_observation()
                wall_due = observed_at >= wire.send_not_after
                monotonic_due = (
                    observed_monotonic_ns >= wire.send_not_after_monotonic_ns
                )
                if wall_due != monotonic_due:
                    failure_kind = KernelSendFailureKindV49E.CLOCK_DISAGREEMENT
                    evidence = {}
                elif wall_due:
                    failure_kind = (
                        KernelSendFailureKindV49E.DEADLINE_EXPIRED_NO_KERNEL_ACCEPTANCE
                    )
                    evidence = {
                        "owner_evidence_id": exc.owner_evidence_id,
                        "kernel_socket_identity": exc.kernel_socket_identity,
                        "driver_evidence_nonce_sha256": (
                            exc.driver_evidence_nonce_sha256
                        ),
                        "send_kind": exc.send_kind,
                        "transport_sequence": exc.transport_sequence,
                        "exact_slice_sha256": exc.exact_slice_sha256,
                        "would_block_count": exc.would_block_count,
                        "driver_evidence_id": exc.driver_evidence_id,
                    }
                else:
                    raise PhysicalTransportSessionActorV49CError(
                        "owner Close deadline precedes both actor wire clocks"
                    ) from exc
                await self._record_kernel_send_failure_locked(
                    command_event=command_event,
                    wire_event=wire_event,
                    tls_event=tls_event,
                    attempt_event=attempt_event,
                    attempt=attempt,
                    obligation_layer=obligation_layer,
                    obligation_id=obligation_id,
                    failure_kind=failure_kind,
                    observed_at=observed_at,
                    observed_monotonic_ns=observed_monotonic_ns,
                    signer=terminal_signer,
                    **evidence,
                )
                raise
            except BaseException:
                self._side_effect_fault_latched = True
                self._fault_reason = "kernel send lacks a complete durable result chain"
                if (
                    not self._storage_fault_latched
                    and self._unresolved_attempt_event_id
                    == attempt_event.transport_actor_event_id
                    and self._terminal_state.pending_send_attempt_id
                    == attempt_event.transport_actor_event_id
                ):
                    try:
                        # UNKNOWN_SEND is the sole legal successor while the
                        # write-ahead attempt lacks an exact durable result.
                        self._side_effect_fault_latched = False
                        await self._append_unknown_send_locked(
                            cause_code=_SEND_EFFECT_FAILED_CAUSE,
                            signer=terminal_signer,
                        )
                    finally:
                        self._side_effect_fault_latched = True
                raise
            return KernelSendOutcomeV49C(
                attempt_event=attempt_event,
                attempt_started_event=started_event,
                result_event=result_event,
                attempt_resolved_event=resolved_event,
            )

    async def _complete_outbound_dispatch_locked(
        self, payload: OutboundDispatchCompletedPayloadV49C
    ) -> TransportActorEventV49C:
        self._require_oldest(payload.outbound_wire_prepared_event_id)
        wire_event = self._events_by_id[payload.outbound_wire_prepared_event_id]
        wire = wire_event.payload
        assert type(wire) is OutboundWirePreparedPayloadV49C
        event = await self._append_payload_locked(payload)
        if wire.logical_opcode is WebSocketOpcodeV49C.CLOSE:
            await self._append_payload_locked(
                self._terminal_payload(
                    TerminalTransitionKindV49C.OUTBOUND_OBLIGATION_FULLY_KERNEL_ACCEPTED,
                    obligation_layer=OutboundObligationLayerV49C.WEBSOCKET_CLOSE,
                    obligation_id=wire.outbound_operation_id,
                )
            )
        return event

    def _derive_complete_dispatch_payload_locked(
        self,
    ) -> OutboundDispatchCompletedPayloadV49C:
        tls_event, tls = self._active_tls()
        offset, _, result_ids = self._send_progress(tls_event.transport_actor_event_id)
        if offset != tls.ciphertext_octets or not result_ids:
            raise PhysicalTransportSessionActorV49CQueueError(
                "oldest TLS ciphertext isn't fully locally submitted"
            )
        permit_event = self._events_by_id[tls.write_permit_consumed_event_id]
        wire_event = self._events_by_id[tls.outbound_wire_prepared_event_id]
        assert type(permit_event.payload) is WritePermitConsumedPayloadV49C
        assert type(wire_event.payload) is OutboundWirePreparedPayloadV49C
        completed_at, completed_monotonic_ns = self._sample_observation()
        return OutboundDispatchCompletedPayloadV49C(
            outbound_wire_prepared_event_id=wire_event.transport_actor_event_id,
            write_permit_consumed_event_id=permit_event.transport_actor_event_id,
            tls_ciphertext_prepared_event_id=tls_event.transport_actor_event_id,
            kernel_send_result_event_ids=result_ids,
            ciphertext_batch_sha256=tls.ciphertext_batch_sha256,
            ciphertext_octets=tls.ciphertext_octets,
            submitted_ciphertext_octets=offset,
            disposition=OutboundDispatchDispositionV49C.COMPLETE_LOCAL_SUBMISSION,
            completed_at=completed_at,
            completed_monotonic_ns=completed_monotonic_ns,
        )

    async def complete_oldest_dispatch_from_chain(
        self,
    ) -> TransportActorEventV49C:
        """Derive completion only from exact durable positive send results."""

        self._assert_owner()
        async with self._lock:
            payload = self._derive_complete_dispatch_payload_locked()
            return await self._complete_outbound_dispatch_locked(payload)

    async def complete_outbound_dispatch(
        self, payload: OutboundDispatchCompletedPayloadV49C
    ) -> TransportActorEventV49C:
        self._assert_owner()
        async with self._lock:
            return await self._complete_outbound_dispatch_locked(payload)

    def _obligation_for_attempt(
        self, attempt_event_id: str
    ) -> tuple[OutboundObligationLayerV49C, str]:
        event = self._events_by_id.get(attempt_event_id)
        if event is None or event.event_kind is not (
            TransportActorEventKindV49C.KERNEL_SEND_ATTEMPT
        ):
            raise PhysicalTransportSessionActorV49CJournalError(
                "pending send attempt isn't present in the actor prefix"
            )
        payload = event.payload
        assert type(payload) is KernelSendAttemptPayloadV49C
        tls_event = self._events_by_id[payload.tls_ciphertext_prepared_event_id]
        tls = tls_event.payload
        assert type(tls) is TlsCiphertextPreparedPayloadV49C
        wire_event = self._events_by_id[tls.outbound_wire_prepared_event_id]
        return self._current_obligation(wire_event)

    async def _recover_interrupted_send_locked(
        self, *, terminal_signer: Any | None = None
    ) -> None:
        """Finish bookkeeping or terminalize; never invoke the send effect."""

        if self._terminal_state.is_terminal:
            return
        pending = self._terminal_state.pending_send_attempt_id
        if pending is not None and self._result_awaiting_terminal_resolution_id:
            matching_failure = next(
                (
                    event.payload
                    for event in reversed(self._events)
                    if type(event.payload) is KernelSendFailurePayloadV49E
                    and event.payload.kernel_send_attempt_event_id == pending
                ),
                None,
            )
            layer = self._terminal_state.pending_send_obligation_layer
            obligation = self._terminal_state.pending_send_obligation_id
            assert layer is not None and obligation is not None
            await self._append_send_resolved_locked(
                attempt_event_id=pending,
                obligation_layer=layer,
                obligation_id=obligation,
            )
            pending = None
            if matching_failure is not None:
                if terminal_signer is None:
                    raise PhysicalTransportSessionActorV49CJournalError(
                        "typed send-failure recovery requires terminal signer"
                    )
                clock_disagreement = (
                    matching_failure.failure_kind
                    is KernelSendFailureKindV49E.CLOCK_DISAGREEMENT
                )
                await self._converge_terminal_payload_locked(
                    self._terminal_payload(
                        (
                            TerminalTransitionKindV49C.FATAL
                            if clock_disagreement
                            else TerminalTransitionKindV49C.TIMEOUT
                        ),
                        cause_code=(
                            V49E_LOCAL_SHUTDOWN_CLOCK_DISAGREEMENT_CAUSE
                            if clock_disagreement
                            else (
                                V49E_LOCAL_SHUTDOWN_COMMAND_DEADLINE_EXPIRED_CAUSE
                                if matching_failure.local_shutdown_command_started_event_id
                                is not None
                                else V49E_WEBSOCKET_CLOSE_DEADLINE_EXPIRED_CAUSE
                            )
                        ),
                    ),
                    signer=terminal_signer,
                )
                return
        unresolved = self._unresolved_attempt_event_id
        if unresolved is not None:
            if pending is None:
                layer, obligation = self._obligation_for_attempt(unresolved)
                await self._append_send_started_locked(
                    attempt_event_id=unresolved,
                    obligation_layer=layer,
                    obligation_id=obligation,
                )
            elif pending != unresolved:
                raise PhysicalTransportSessionActorV49CJournalError(
                    "terminal pending attempt differs from kernel attempt"
                )
            await self._append_unknown_send_locked(
                cause_code=V49C_RECOVERY_UNKNOWN_SEND_CAUSE,
                signer=terminal_signer,
            )
            self._side_effect_fault_latched = True
            self._fault_reason = _RECOVERY_RESOLVED_CAUSE
            return

        try:
            tls_event, tls = self._active_tls()
        except PhysicalTransportSessionActorV49CQueueError:
            return
        offset, _, result_ids = self._send_progress(tls_event.transport_actor_event_id)
        if offset == 0:
            return
        if offset < tls.ciphertext_octets:
            transition = self._terminal_payload(
                TerminalTransitionKindV49C.FATAL,
                cause_code=_RECOVERY_PARTIAL_CIPHERTEXT_CAUSE,
            )
            if terminal_signer is None:
                await self._append_payload_locked(transition)
            else:
                await self._converge_terminal_payload_locked(
                    transition,
                    signer=terminal_signer,
                )
            self._side_effect_fault_latched = True
            self._fault_reason = _RECOVERY_PARTIAL_CIPHERTEXT_CAUSE
            return

        await self._complete_outbound_dispatch_locked(
            self._derive_complete_dispatch_payload_locked()
        )

    async def _recover_websocket_close_markers_locked(self) -> None:
        """Repair only actor-marker crashes; never regenerate protocol bytes."""

        if self._terminal_state.is_terminal:
            return
        markers = {
            payload.kind
            for event in self._events
            if event.event_kind is TransportActorEventKindV49C.TERMINAL_TRANSITION
            and type(payload := event.payload) is TerminalTransitionPayloadV49C
        }
        missing: list[tuple[int, TerminalTransitionKindV49C, str | None]] = []
        for event in self._events:
            payload = event.payload
            if (
                event.event_kind is TransportActorEventKindV49C.PARSER_TRANSITION
                and type(payload) is ParserTransitionPayloadV49C
                and payload.frame is not None
                and payload.frame.opcode is WebSocketOpcodeV49C.CLOSE
                and TerminalTransitionKindV49C.WS_CLOSE_RECEIVED not in markers
            ):
                missing.append(
                    (
                        event.actor_sequence,
                        TerminalTransitionKindV49C.WS_CLOSE_RECEIVED,
                        None,
                    )
                )
                markers.add(TerminalTransitionKindV49C.WS_CLOSE_RECEIVED)
            elif (
                event.event_kind is TransportActorEventKindV49C.OUTBOUND_WIRE_PREPARED
                and type(payload) is OutboundWirePreparedPayloadV49C
                and payload.logical_opcode is WebSocketOpcodeV49C.CLOSE
                and TerminalTransitionKindV49C.WS_CLOSE_SENT not in markers
            ):
                missing.append(
                    (
                        event.actor_sequence,
                        TerminalTransitionKindV49C.WS_CLOSE_SENT,
                        payload.outbound_operation_id,
                    )
                )
                markers.add(TerminalTransitionKindV49C.WS_CLOSE_SENT)
        for _, kind, obligation_id in sorted(missing):
            await self._append_payload_locked(
                self._terminal_payload(
                    kind,
                    obligation_layer=(
                        OutboundObligationLayerV49C.WEBSOCKET_CLOSE
                        if kind is TerminalTransitionKindV49C.WS_CLOSE_SENT
                        else None
                    ),
                    obligation_id=obligation_id,
                )
            )

    async def _recover_control_result_markers_v49e_locked(
        self,
        result_event: TransportActorEventV49C,
    ) -> None:
        result = result_event.payload
        assert type(result) is TlsControlKernelSendResultPayloadV49E
        control_event = self._events_by_id[
            result.tls_control_ciphertext_prepared_event_id
        ]
        control = control_event.payload
        assert type(control) is TlsControlCiphertextPreparedPayloadV49E
        layer = (
            OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY
            if control.control_kind is TlsControlOutputKindV49E.LOCAL_CLOSE_NOTIFY
            else OutboundObligationLayerV49C.TLS_OPAQUE_CONTROL
        )
        resolved_payload = self._terminal_payload(
            TerminalTransitionKindV49C.SEND_ATTEMPT_RESOLVED,
            obligation_layer=layer,
            obligation_id=control_event.transport_actor_event_id,
            send_attempt_id=result.tls_control_kernel_send_attempt_event_id,
        )
        is_complete_local = (
            result.resulting_ciphertext_offset == control.ciphertext_octets
            and control.control_kind is TlsControlOutputKindV49E.LOCAL_CLOSE_NOTIFY
        )
        if not is_complete_local:
            await self._append_payload_locked(resolved_payload)
            return
        observations = self._sample_observation_batch(3)
        resolved_event = self._candidate_event_for_prefix(
            resolved_payload,
            self._events,
            recorded_observation=observations[0],
        )
        resolved_state = advance_terminal_state_v49c(
            self._terminal_state,
            resolved_payload,
        )
        sent_payload = self._terminal_payload_for_state(
            resolved_state,
            TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_SENT,
            obligation_layer=OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY,
            obligation_id=control_event.transport_actor_event_id,
        )
        sent_event = self._candidate_event_for_prefix(
            sent_payload,
            (*self._events, resolved_event),
            recorded_observation=observations[1],
        )
        sent_state = advance_terminal_state_v49c(resolved_state, sent_payload)
        accepted_payload = self._terminal_payload_for_state(
            sent_state,
            TerminalTransitionKindV49C.OUTBOUND_OBLIGATION_FULLY_KERNEL_ACCEPTED,
            obligation_layer=OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY,
            obligation_id=control_event.transport_actor_event_id,
        )
        accepted_event = self._candidate_event_for_prefix(
            accepted_payload,
            (*self._events, resolved_event, sent_event),
            recorded_observation=observations[2],
        )
        await self._append_candidate_batch_locked(
            (resolved_event, sent_event, accepted_event)
        )

    async def _recover_terminal_prefix_v49e_locked(self, *, signer: Any) -> None:
        """Resolve durable E2 prefixes without repeating TLS or socket effects."""

        if self._terminal_state.is_terminal or not self._events:
            return
        last = self._events[-1]
        payload = last.payload

        if type(payload) is LocalShutdownDeadlineEvidencePayloadV49E:
            terminal_kind, cause = {
                LocalShutdownDeadlineClassificationV49E.BOTH_DUE: (
                    TerminalTransitionKindV49C.TIMEOUT,
                    V49E_LOCAL_SHUTDOWN_COMMAND_DEADLINE_EXPIRED_CAUSE,
                ),
                LocalShutdownDeadlineClassificationV49E.CLOCK_DISAGREEMENT: (
                    TerminalTransitionKindV49C.FATAL,
                    V49E_LOCAL_SHUTDOWN_CLOCK_DISAGREEMENT_CAUSE,
                ),
                LocalShutdownDeadlineClassificationV49E.OWNER_EVIDENCE_BEFORE_BOTH_CLOCKS: (
                    TerminalTransitionKindV49C.FATAL,
                    V49E_TLS_OPERATION_DRIVER_ERROR_CAUSE,
                ),
            }[payload.classification]
            await self._converge_terminal_payload_locked(
                self._terminal_payload(terminal_kind, cause_code=cause),
                signer=signer,
            )
            return
        if type(payload) is TerminalIngressFailurePayloadV49E:
            clock_disagreement = (
                payload.failure_kind
                is TerminalIngressFailureKindV49E.CLOCK_DISAGREEMENT
            )
            await self._converge_terminal_payload_locked(
                self._terminal_payload(
                    (
                        TerminalTransitionKindV49C.FATAL
                        if clock_disagreement
                        else TerminalTransitionKindV49C.TIMEOUT
                    ),
                    cause_code=(
                        V49E_LOCAL_SHUTDOWN_CLOCK_DISAGREEMENT_CAUSE
                        if clock_disagreement
                        else V49E_TERMINAL_CLOSE_INGRESS_DEADLINE_EXPIRED_AFTER_PROGRESS_CAUSE
                    ),
                ),
                signer=signer,
            )
            return
        if type(payload) is TlsProtocolOperationStartedPayloadV49E:
            await self._record_tls_operation_failure_locked(
                last,
                failure_kind=TlsProtocolOperationFailureKindV49E.DRIVER_ERROR,
                signer=signer,
            )
            return
        if type(payload) is TlsProtocolOperationFailedPayloadV49E:
            terminal_kind, cause = classify_tls_protocol_operation_failure_v49e(payload)
            await self._converge_terminal_payload_locked(
                self._terminal_payload(terminal_kind, cause_code=cause),
                signer=signer,
            )
            return
        if type(payload) is TlsControlCiphertextPreparedPayloadV49E:
            if payload.control_kind is TlsControlOutputKindV49E.LOCAL_CLOSE_NOTIFY:
                await self._append_payload_locked(
                    self._terminal_payload(
                        TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_PREPARED,
                        obligation_layer=(OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY),
                        obligation_id=last.transport_actor_event_id,
                    )
                )
            await self._converge_terminal_payload_locked(
                self._terminal_payload(
                    TerminalTransitionKindV49C.FATAL,
                    cause_code=V49E_TLS_OPERATION_DRIVER_ERROR_CAUSE,
                ),
                signer=signer,
            )
            return
        if (
            type(payload) is TerminalTransitionPayloadV49C
            and payload.kind is TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_PREPARED
        ):
            await self._converge_terminal_payload_locked(
                self._terminal_payload(
                    TerminalTransitionKindV49C.FATAL,
                    cause_code=V49E_TLS_OPERATION_DRIVER_ERROR_CAUSE,
                ),
                signer=signer,
            )
            return
        if type(payload) is TlsControlKernelSendAttemptPayloadV49E:
            control_event = self._events_by_id[
                payload.tls_control_ciphertext_prepared_event_id
            ]
            control = control_event.payload
            assert type(control) is TlsControlCiphertextPreparedPayloadV49E
            layer = (
                OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY
                if control.control_kind is TlsControlOutputKindV49E.LOCAL_CLOSE_NOTIFY
                else OutboundObligationLayerV49C.TLS_OPAQUE_CONTROL
            )
            await self._append_payload_locked(
                self._terminal_payload(
                    TerminalTransitionKindV49C.SEND_ATTEMPT_STARTED,
                    obligation_layer=layer,
                    obligation_id=control_event.transport_actor_event_id,
                    send_attempt_id=last.transport_actor_event_id,
                )
            )
            await self._converge_unknown_tls_control_send_locked(signer=signer)
            return
        if (
            self._terminal_state.has_pending_send_attempt
            and self._terminal_state.pending_send_obligation_layer
            in {
                OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY,
                OutboundObligationLayerV49C.TLS_OPAQUE_CONTROL,
            }
        ):
            pending_attempt_id = self._terminal_state.pending_send_attempt_id
            matching_failure = next(
                (
                    event
                    for event in reversed(self._events)
                    if type(event.payload) is TlsControlKernelSendFailurePayloadV49E
                    and event.payload.tls_control_kernel_send_attempt_event_id
                    == pending_attempt_id
                ),
                None,
            )
            if matching_failure is not None:
                failure = matching_failure.payload
                assert type(failure) is TlsControlKernelSendFailurePayloadV49E
                control_event = self._events_by_id[
                    failure.tls_control_ciphertext_prepared_event_id
                ]
                control = control_event.payload
                assert type(control) is TlsControlCiphertextPreparedPayloadV49E
                layer = (
                    OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY
                    if control.control_kind
                    is TlsControlOutputKindV49E.LOCAL_CLOSE_NOTIFY
                    else OutboundObligationLayerV49C.TLS_OPAQUE_CONTROL
                )
                await self._append_payload_locked(
                    self._terminal_payload(
                        TerminalTransitionKindV49C.SEND_ATTEMPT_RESOLVED,
                        obligation_layer=layer,
                        obligation_id=control_event.transport_actor_event_id,
                        send_attempt_id=pending_attempt_id,
                    )
                )
                clock_disagreement = (
                    failure.failure_kind is KernelSendFailureKindV49E.CLOCK_DISAGREEMENT
                )
                await self._converge_terminal_payload_locked(
                    self._terminal_payload(
                        (
                            TerminalTransitionKindV49C.FATAL
                            if clock_disagreement
                            else TerminalTransitionKindV49C.TIMEOUT
                        ),
                        cause_code=(
                            V49E_LOCAL_SHUTDOWN_CLOCK_DISAGREEMENT_CAUSE
                            if clock_disagreement
                            else V49E_LOCAL_SHUTDOWN_COMMAND_DEADLINE_EXPIRED_CAUSE
                        ),
                    ),
                    signer=signer,
                )
                return
            matching_result = next(
                (
                    event
                    for event in reversed(self._events)
                    if type(event.payload) is TlsControlKernelSendResultPayloadV49E
                    and event.payload.tls_control_kernel_send_attempt_event_id
                    == self._terminal_state.pending_send_attempt_id
                ),
                None,
            )
            if matching_result is None:
                await self._converge_unknown_tls_control_send_locked(signer=signer)
            else:
                await self._recover_control_result_markers_v49e_locked(matching_result)
            return
        if (
            type(payload) is TerminalTransitionPayloadV49C
            and payload.kind is TerminalTransitionKindV49C.SEND_ATTEMPT_RESOLVED
            and payload.obligation_layer is OutboundObligationLayerV49C.WEBSOCKET_CLOSE
        ):
            resolved_failure = next(
                (
                    event.payload
                    for event in reversed(self._events[:-1])
                    if type(event.payload) is KernelSendFailurePayloadV49E
                    and event.payload.kernel_send_attempt_event_id
                    == payload.send_attempt_id
                ),
                None,
            )
            if resolved_failure is not None:
                clock_disagreement = (
                    resolved_failure.failure_kind
                    is KernelSendFailureKindV49E.CLOCK_DISAGREEMENT
                )
                await self._converge_terminal_payload_locked(
                    self._terminal_payload(
                        (
                            TerminalTransitionKindV49C.FATAL
                            if clock_disagreement
                            else TerminalTransitionKindV49C.TIMEOUT
                        ),
                        cause_code=(
                            V49E_LOCAL_SHUTDOWN_CLOCK_DISAGREEMENT_CAUSE
                            if clock_disagreement
                            else (
                                V49E_LOCAL_SHUTDOWN_COMMAND_DEADLINE_EXPIRED_CAUSE
                                if resolved_failure.local_shutdown_command_started_event_id
                                is not None
                                else V49E_WEBSOCKET_CLOSE_DEADLINE_EXPIRED_CAUSE
                            )
                        ),
                    ),
                    signer=signer,
                )
                return
        if (
            type(payload) is TerminalTransitionPayloadV49C
            and payload.kind is TerminalTransitionKindV49C.SEND_ATTEMPT_RESOLVED
            and payload.obligation_layer
            in {
                OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY,
                OutboundObligationLayerV49C.TLS_OPAQUE_CONTROL,
            }
        ):
            resolved_failure = next(
                (
                    event.payload
                    for event in reversed(self._events[:-1])
                    if type(event.payload) is TlsControlKernelSendFailurePayloadV49E
                    and event.payload.tls_control_kernel_send_attempt_event_id
                    == payload.send_attempt_id
                ),
                None,
            )
            if resolved_failure is not None:
                clock_disagreement = (
                    resolved_failure.failure_kind
                    is KernelSendFailureKindV49E.CLOCK_DISAGREEMENT
                )
                await self._converge_terminal_payload_locked(
                    self._terminal_payload(
                        (
                            TerminalTransitionKindV49C.FATAL
                            if clock_disagreement
                            else TerminalTransitionKindV49C.TIMEOUT
                        ),
                        cause_code=(
                            V49E_LOCAL_SHUTDOWN_CLOCK_DISAGREEMENT_CAUSE
                            if clock_disagreement
                            else V49E_LOCAL_SHUTDOWN_COMMAND_DEADLINE_EXPIRED_CAUSE
                        ),
                    ),
                    signer=signer,
                )
                return
            result_event = next(
                event
                for event in reversed(self._events[:-1])
                if type(event.payload) is TlsControlKernelSendResultPayloadV49E
                and event.payload.tls_control_kernel_send_attempt_event_id
                == payload.send_attempt_id
            )
            result = result_event.payload
            assert type(result) is TlsControlKernelSendResultPayloadV49E
            control_event = self._events_by_id[
                result.tls_control_ciphertext_prepared_event_id
            ]
            control = control_event.payload
            assert type(control) is TlsControlCiphertextPreparedPayloadV49E
            if (
                result.resulting_ciphertext_offset == control.ciphertext_octets
                and control.control_kind is TlsControlOutputKindV49E.LOCAL_CLOSE_NOTIFY
            ):
                observations = self._sample_observation_batch(2)
                sent_event = self._candidate_event_for_prefix(
                    self._terminal_payload(
                        TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_SENT,
                        obligation_layer=(OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY),
                        obligation_id=control_event.transport_actor_event_id,
                    ),
                    self._events,
                    recorded_observation=observations[0],
                )
                sent_state = advance_terminal_state_v49c(
                    self._terminal_state,
                    sent_event.payload,
                )
                accepted_event = self._candidate_event_for_prefix(
                    self._terminal_payload_for_state(
                        sent_state,
                        TerminalTransitionKindV49C.OUTBOUND_OBLIGATION_FULLY_KERNEL_ACCEPTED,
                        obligation_layer=(OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY),
                        obligation_id=control_event.transport_actor_event_id,
                    ),
                    (*self._events, sent_event),
                    recorded_observation=observations[1],
                )
                await self._append_candidate_batch_locked((sent_event, accepted_event))
            elif result.resulting_ciphertext_offset < control.ciphertext_octets:
                await self._converge_terminal_payload_locked(
                    self._terminal_payload(
                        TerminalTransitionKindV49C.FATAL,
                        cause_code=V49E_TLS_OPERATION_DRIVER_ERROR_CAUSE,
                    ),
                    signer=signer,
                )
            return
        if type(payload) is TcpHalfCloseAttemptPayloadV49E:
            await self._converge_terminal_payload_locked(
                self._terminal_payload(
                    TerminalTransitionKindV49C.FATAL,
                    cause_code=V49E_TCP_HALF_CLOSE_OUTCOME_UNKNOWN_CAUSE,
                ),
                signer=signer,
            )
            return
        if type(payload) is TcpHalfCloseResultPayloadV49E:
            if payload.result_kind is TcpHalfCloseResultKindV49E.KERNEL_ACCEPTED:
                await self._append_payload_locked(
                    self._terminal_payload(TerminalTransitionKindV49C.TCP_FIN_SENT)
                )
            else:
                if (
                    payload.result_kind
                    is TcpHalfCloseResultKindV49E.DEADLINE_EXPIRED_BEFORE_SYSCALL
                ):
                    terminal_kind = TerminalTransitionKindV49C.TIMEOUT
                    cause = V49E_TCP_HALF_CLOSE_DEADLINE_EXPIRED_BEFORE_SYSCALL_CAUSE
                elif (
                    payload.result_kind is TcpHalfCloseResultKindV49E.CLOCK_DISAGREEMENT
                ):
                    terminal_kind = TerminalTransitionKindV49C.FATAL
                    cause = V49E_LOCAL_SHUTDOWN_CLOCK_DISAGREEMENT_CAUSE
                else:
                    terminal_kind = TerminalTransitionKindV49C.FATAL
                    cause = V49E_TCP_HALF_CLOSE_ERROR_CAUSE
                await self._converge_terminal_payload_locked(
                    self._terminal_payload(
                        terminal_kind,
                        cause_code=cause,
                    ),
                    signer=signer,
                )
            return
        if (
            type(payload) is TerminalTransitionPayloadV49C
            and payload.kind is TerminalTransitionKindV49C.TCP_EOF_RECEIVED
            and len(self._events) >= 2
            and type(self._events[-2].payload) is TlsShutdownObservedPayloadV49E
            and self._events[-2].payload.observation_kind
            is TlsShutdownObservationKindV49E.TCP_EOF
            and all(
                (
                    self._terminal_state.ws_close_sent,
                    self._terminal_state.ws_close_received,
                    self._terminal_state.ws_output_fully_kernel_accepted,
                    self._terminal_state.tls_close_notify_sent,
                    self._terminal_state.tls_close_notify_received,
                    self._terminal_state.tls_close_notify_fully_kernel_accepted,
                    self._terminal_state.tcp_fin_sent,
                    self._terminal_state.tcp_eof_received,
                )
            )
        ):
            recovered_observation = self._sample_observation()
            await self._converge_terminal_payload_locked(
                self._terminal_payload(TerminalTransitionKindV49C.CLEAN_ALL_LAYERS),
                signer=signer,
                recorded_observation=recovered_observation,
            )
            return
        if type(payload) is TlsShutdownObservedPayloadV49E:
            marker_kind = (
                TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_RECEIVED
                if payload.observation_kind
                is TlsShutdownObservationKindV49E.PEER_CLOSE_NOTIFY
                else TerminalTransitionKindV49C.TCP_EOF_RECEIVED
            )
            marker = self._terminal_payload(marker_kind)
            prospective = advance_terminal_state_v49c(self._terminal_state, marker)
            clean_after_marker = (
                not prospective.is_terminal
                and payload.observation_kind is TlsShutdownObservationKindV49E.TCP_EOF
                and all(
                    (
                        prospective.ws_close_sent,
                        prospective.ws_close_received,
                        prospective.ws_output_fully_kernel_accepted,
                        prospective.tls_close_notify_sent,
                        prospective.tls_close_notify_received,
                        prospective.tls_close_notify_fully_kernel_accepted,
                        prospective.tcp_fin_sent,
                        prospective.tcp_eof_received,
                    )
                )
            )
            recovered_observations = (
                self._sample_observation_batch(2)
                if clean_after_marker
                else (self._sample_observation(),)
            )
            marker_observation = recovered_observations[0]
            if prospective.is_terminal:
                await self._converge_terminal_payload_locked(
                    marker,
                    signer=signer,
                    recorded_observation=marker_observation,
                )
            else:
                marker_event = self._candidate_event_for_prefix(
                    marker,
                    self._events,
                    recorded_observation=marker_observation,
                )
                await self._append_candidate_locked(marker_event)
                if clean_after_marker:
                    await self._converge_terminal_payload_locked(
                        self._terminal_payload(
                            TerminalTransitionKindV49C.CLEAN_ALL_LAYERS
                        ),
                        signer=signer,
                        recorded_observation=recovered_observations[1],
                    )

    async def recover_terminal_prefix_v49e(self, *, signer: Any) -> None:
        """Public signer-aware recovery for an already restored actor prefix."""

        self._assert_owner()
        async with self._lock:
            await self._recover_terminal_prefix_v49e_locked(signer=signer)


__all__ = [
    "ActorObservationClockV49C",
    "KernelSendEffectV49C",
    "KernelSendOutcomeV49C",
    "LocalCloseTlsPrepareEffectV49E",
    "LocalShutdownCommandClockDisagreementV49E",
    "LocalShutdownCommandDeadlineDueV49E",
    "LocalWebSocketClosePrepareEffectV49E",
    "PhysicalTransportSessionActorV49C",
    "PhysicalTransportSessionActorV49CError",
    "PhysicalTransportSessionActorV49CFaultLatched",
    "PhysicalTransportSessionActorV49CJournalError",
    "PhysicalTransportSessionActorV49COwnerError",
    "PhysicalTransportSessionActorV49CQueueError",
    "TerminalIngressReadOutcomeV49E",
    "TlsControlPrepareEffectV49E",
    "TlsControlSendEffectV49E",
    "TlsControlSendOutcomeV49E",
    "TlsShutdownObservationOutcomeV49E",
    "TransportActorAuthorityV49C",
    "TransportActorJournalPortV49C",
]

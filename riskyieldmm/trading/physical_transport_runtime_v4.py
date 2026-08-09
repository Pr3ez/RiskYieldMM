"""Fenced V4.7 operational transport mediator.

This module is the non-network authority boundary between a reviewed socket
driver and :class:`PhysicalProjectionStoreV4`.  It makes the ordering that the
projection assumes executable: acquire one process lease, verify and reconcile
the journal, commit a signed session, durably authorize one exact command, and
only then issue a one-shot send permit.

The mediator deliberately contains no exchange client, automatic reconnect,
order path, or trading activation.  A successful local state transition proves
only the local ordering represented here.  It cannot prove remote delivery,
exactly-once subscription, profitable trading, or that a deployment is safe.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import os
import secrets
import threading
import time
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from .canonical import (
    CANONICALIZATION_VERSION,
    CanonicalizationError,
    canonical_hash,
    canonical_identifier,
    canonical_json_bytes,
    canonical_safe_int,
    sha256_digest,
    strict_json_loads,
    utc_datetime,
    utc_iso,
)
from .ledger_signing import Ed25519CheckpointVerifier
from .operational_manifests_v4 import (
    ClockSourcePolicyManifestV4,
    CollectorReleaseManifestV4,
    DeploymentBundleApprovalV4,
    DeploymentBundleV4,
    DeploymentTrustRootV4,
    OperationalChildManifestV4,
    RuntimeEnvironmentManifestV4,
    TlsWebSocketDriverPolicyV49B,
    VerifiedDeploymentCapabilityV4,
    verify_deployment_bundle_approval_v4,
)
from .physical_transport_capacity_v49f import (
    BoundedTransportAdmissionGateV49F,
    TransportAdmissionGrantV49F,
    TransportAdmissionSnapshotV49F,
    TransportCapacityPolicyV49F,
    TransportCommandKindV49F,
)
from .physical_transport_owner_v4 import (
    CommittedBoundTransportSessionV4,
    TransportSocketOwnerBindingV4,
    TransportSocketOwnerSnapshotV4,
    derive_transport_socket_lease_id,
    derive_transport_socket_lease_nonce_sha256,
)
from .physical_transport_v4 import (
    V4_TRANSPORT_HANDSHAKE_COMMITMENT_PROFILE,
    OutboundSubscriptionIntentV4,
    SubscriptionAckBindingV4,
    TransportSessionAttestationV4,
    TransportSessionTerminationReasonV4,
    TransportSessionTerminationV4,
    derive_transport_attestation_key_id,
)

if TYPE_CHECKING:
    from .physical_projection_v4 import (
        PhysicalProjectionSqliteEnvironmentObservationV49F,
    )

PHYSICAL_TRANSPORT_RUNTIME_V4_SCHEMA_VERSION = (
    "riskyieldmm_physical_transport_runtime_v4_9f_a1"
)
PHYSICAL_TRANSPORT_A2M_RAW_V49F_V6_SCHEMA_VERSION = (
    "riskyieldmm_physical_transport_a2m_raw_v49f_v6"
)
PHYSICAL_TRANSPORT_A2M_RAW_V49F_V7_SCHEMA_VERSION = (
    "riskyieldmm_physical_transport_a2m_raw_v49f_v7"
)
_A2M_MANIFEST_AUTHORITY_SIGNING_DOMAIN_V49F = (
    "RiskYieldMMA2MManifestAuthoritySubjectV4_9F_RawV6"
)
_A2M_MANIFEST_AUTHORITY_SIGNING_DOMAIN_V49F_V7 = (
    "RiskYieldMMA2MManifestAuthoritySubjectV4_9F_RawV7"
)
V4_RUNTIME_DEFAULT_MAXIMUM_CLOCK_UNCERTAINTY_MILLISECONDS = 250
V4_RUNTIME_DEFAULT_MAXIMUM_CLOCK_EVIDENCE_LIFETIME_SECONDS = 5

_CAPACITY_MEASUREMENT_AUTHORIZATION_TOKEN_V49F = object()
_CAPACITY_MEASUREMENT_FORK_GENERATION_V49F = 0


def _invalidate_capacity_measurement_authorizations_after_fork_v49f() -> None:
    global _CAPACITY_MEASUREMENT_FORK_GENERATION_V49F
    _CAPACITY_MEASUREMENT_FORK_GENERATION_V49F += 1


if hasattr(os, "register_at_fork"):
    os.register_at_fork(
        after_in_child=_invalidate_capacity_measurement_authorizations_after_fork_v49f
    )


class PhysicalTransportRuntimeV4Error(RuntimeError):
    """Base class for operational transport boundary failures."""


class PhysicalTransportRuntimeV4StateError(PhysicalTransportRuntimeV4Error):
    """Raised when an operation is invalid in the current lifecycle state."""


class PhysicalTransportClockEvidenceV4Error(PhysicalTransportRuntimeV4Error):
    """Raised when causal wall/monotonic clock evidence is not admissible."""


class PhysicalTransportSendPermitV4Error(PhysicalTransportRuntimeV4Error):
    """Raised when a send permit is stale, forged, expired, or already used."""


class PhysicalTransportStaleCallbackV4(PhysicalTransportRuntimeV4Error):
    """Raised without mutating the current session for an old socket callback."""


class PhysicalTransportDispatchUnknownV4(PhysicalTransportRuntimeV4Error):
    """Raised when dispatch may have begun but completion isn't authoritative."""


class PhysicalTransportAutomaticCloseTerminalFailureV49E(
    PhysicalTransportRuntimeV4Error
):
    """Expose a conclusive automatic-Close terminal pair without calling it unknown."""

    def __init__(
        self,
        *,
        termination: TransportSessionTerminationV4,
        terminal_outcome: str,
        cause_code: str | None,
        kernel_send_attempt_recorded: bool,
    ) -> None:
        if type(termination) is not TransportSessionTerminationV4:
            raise TypeError("termination must be exact TransportSessionTerminationV4")
        if type(terminal_outcome) is not str or not terminal_outcome:
            raise TypeError("terminal_outcome must be one non-empty string")
        if cause_code is not None and (type(cause_code) is not str or not cause_code):
            raise TypeError("cause_code must be None or one non-empty string")
        if type(kernel_send_attempt_recorded) is not bool:
            raise TypeError("kernel_send_attempt_recorded must be a boolean")
        self.termination = termination
        self.terminal_outcome = terminal_outcome
        self.cause_code = cause_code
        self.kernel_send_attempt_recorded = kernel_send_attempt_recorded
        super().__init__(
            "automatic WebSocket Close ended conclusively as "
            f"{terminal_outcome}" + ("" if cause_code is None else f" ({cause_code})")
        )


class PhysicalTransportAckBindingV4Error(PhysicalTransportRuntimeV4Error):
    """Raised after an ACK candidate cannot be bound fail-closed."""


class PhysicalTransportProviderIntegrityFailureV49E(PhysicalTransportRuntimeV4Error):
    """Raised after a durable pending-subscription response integrity failure."""


class PhysicalTransportRuntimeV4FaultLatched(PhysicalTransportRuntimeV4Error):
    """Raised when journal or clock uncertainty prevents a terminal claim."""


class CapacityMeasurementIngressAuthorizationV49FError(PhysicalTransportRuntimeV4Error):
    """A Raw-V7 operation authorization is stale, forged, or already consumed."""


class CapacityMeasurementTerminalPersistenceV49FError(PhysicalTransportRuntimeV4Error):
    """A durable attempt could not be closed before operation unwind."""


def _capacity_measurement_exception_chain_v49f(
    surfaced: BaseException,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return the exact bounded Python cause/context chain without message text."""

    if not isinstance(surfaced, BaseException):
        raise TypeError("surfaced must be one BaseException")
    classes: list[str] = []
    message_hashes: list[str] = []
    seen: set[int] = set()
    current: BaseException | None = surfaced
    while current is not None:
        if id(current) in seen:
            raise CapacityMeasurementTerminalPersistenceV49FError(
                "capacity exception evidence contains a cycle"
            )
        if len(classes) == 8:
            raise CapacityMeasurementTerminalPersistenceV49FError(
                "capacity exception evidence exceeds its exact depth bound"
            )
        seen.add(id(current))
        exception_type = type(current)
        module = type.__getattribute__(exception_type, "__module__")
        qualname = type.__getattribute__(exception_type, "__qualname__")
        if type(module) is not str or type(qualname) is not str:
            raise CapacityMeasurementTerminalPersistenceV49FError(
                "capacity exception class identity is not exact text"
            )
        if len(module) + len(qualname) + 1 > 256:
            raise CapacityMeasurementTerminalPersistenceV49FError(
                "capacity exception class identity exceeds its exact bound"
            )
        class_identity = f"{module}.{qualname}"
        classes.append(class_identity)
        uses_base_formatter = (
            type.__getattribute__(exception_type, "__str__") is BaseException.__str__
        )
        uses_trusted_primitive_digest = class_identity in {
            "ssl.SSLError",
            "ssl.SSLWantReadError",
            "ssl.SSLWantWriteError",
        }
        if not uses_base_formatter and not uses_trusted_primitive_digest:
            raise CapacityMeasurementTerminalPersistenceV49FError(
                "capacity exception has an unsupported message formatter: "
                f"{class_identity}"
            )
        args = BaseException.args.__get__(current, BaseException)
        if type(args) is not tuple or len(args) > 16:
            raise CapacityMeasurementTerminalPersistenceV49FError(
                "capacity exception args exceed their exact bound"
            )
        encoded_arg_octets = 0
        for arg in args:
            if type(arg) not in {type(None), bool, int, float, str, bytes}:
                raise CapacityMeasurementTerminalPersistenceV49FError(
                    "capacity exception contains an unsupported message argument"
                )
            if type(arg) is int and arg.bit_length() > 4096:
                raise CapacityMeasurementTerminalPersistenceV49FError(
                    "capacity exception integer argument exceeds its exact bound"
                )
            if type(arg) is str:
                if len(arg) > 4096:
                    raise CapacityMeasurementTerminalPersistenceV49FError(
                        "capacity exception message exceeds its exact bound"
                    )
                encoded_arg_octets += len(arg.encode("utf-8"))
            elif type(arg) is bytes:
                if len(arg) > 4096:
                    raise CapacityMeasurementTerminalPersistenceV49FError(
                        "capacity exception message exceeds its exact bound"
                    )
                encoded_arg_octets += len(arg)
            else:
                encoded_arg_octets += 32
            if encoded_arg_octets > 4096:
                raise CapacityMeasurementTerminalPersistenceV49FError(
                    "capacity exception message exceeds its exact bound"
                )
        if uses_trusted_primitive_digest:
            canonical_args: list[dict[str, Any]] = []
            for argument in args:
                if type(argument) is bytes:
                    value: Any = base64.b64encode(argument).decode("ascii")
                    value_type = "bytes_base64"
                else:
                    value = argument
                    value_type = type(argument).__name__
                canonical_args.append({"type": value_type, "value": value})
            encoded_message = canonical_json_bytes(
                {
                    "args": canonical_args,
                    "domain": ("RiskYieldMMCapacityExceptionPrimitiveArgsDigestV49F"),
                    "exception_class": class_identity,
                }
            )
        else:
            if not args:
                message = ""
            elif len(args) == 1:
                argument = args[0]
                message = argument if type(argument) is str else str(argument)
            else:
                message = tuple.__repr__(args)
            encoded_message = message.encode("utf-8")
        if len(encoded_message) > 16_384:
            raise CapacityMeasurementTerminalPersistenceV49FError(
                "capacity exception formatted message exceeds its exact bound"
            )
        message_hashes.append(hashlib.sha256(encoded_message).hexdigest())
        explicit_cause = BaseException.__cause__.__get__(current, BaseException)
        suppress_context = BaseException.__suppress_context__.__get__(
            current, BaseException
        )
        implicit_context = BaseException.__context__.__get__(current, BaseException)
        current = (
            explicit_cause
            if explicit_cause is not None
            else None
            if suppress_context
            else implicit_context
        )
    return tuple(classes), tuple(message_hashes)


class PhysicalTransportRuntimeStateV4(str, Enum):
    COLD = "COLD"
    STARTING = "STARTING"
    READY = "READY"
    SESSION_COMMITTED = "SESSION_COMMITTED"
    INTENT_COMMITTED = "INTENT_COMMITTED"
    DISPATCHING = "DISPATCHING"
    AWAITING_ACK = "AWAITING_ACK"
    ACK_BOUND = "ACK_BOUND"
    FENCED = "FENCED"
    FAULT_LATCHED = "FAULT_LATCHED"
    CLOSED = "CLOSED"


@dataclass(frozen=True, slots=True, kw_only=True)
class ClockEvidenceV4:
    """One bounded observation from a governed clock-discipline source.

    ``monotonic_clock_domain_id`` identifies the kernel boot / monotonic epoch.
    It must change across a reboot.  ``clock_source_manifest_id`` commits the
    configured source and its validation policy; the runtime does not invent a
    zero uncertainty when the source is unavailable.
    """

    clock_source_manifest_id: str
    monotonic_clock_domain_id: str
    sampled_at: datetime
    monotonic_ns: int
    uncertainty_milliseconds: int
    synchronized: bool
    valid_until: datetime
    monotonic_before_ns: int | None = None
    monotonic_after_ns: int | None = None
    wall_before_at: datetime | None = None
    wall_after_at: datetime | None = None
    clock_resolution_ns: int | None = None
    observation_sha256: str | None = None
    selectable_source_count: int | None = None
    chronyd_launch_id: str | None = None
    chronyd_runtime_observation_sha256: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "clock_source_manifest_id",
            canonical_hash(
                self.clock_source_manifest_id, field="clock_source_manifest_id"
            ),
        )
        object.__setattr__(
            self,
            "monotonic_clock_domain_id",
            canonical_hash(
                self.monotonic_clock_domain_id,
                field="monotonic_clock_domain_id",
            ),
        )
        object.__setattr__(
            self,
            "monotonic_ns",
            canonical_safe_int(self.monotonic_ns, field="monotonic_ns", minimum=0),
        )
        monotonic_before_ns = (
            self.monotonic_ns
            if self.monotonic_before_ns is None
            else canonical_safe_int(
                self.monotonic_before_ns,
                field="monotonic_before_ns",
                minimum=0,
            )
        )
        monotonic_after_ns = (
            self.monotonic_ns
            if self.monotonic_after_ns is None
            else canonical_safe_int(
                self.monotonic_after_ns,
                field="monotonic_after_ns",
                minimum=0,
            )
        )
        if not (monotonic_before_ns <= self.monotonic_ns <= monotonic_after_ns):
            raise CanonicalizationError(
                "monotonic_ns must lie inside its BOOTTIME observation bracket"
            )
        object.__setattr__(self, "monotonic_before_ns", monotonic_before_ns)
        object.__setattr__(self, "monotonic_after_ns", monotonic_after_ns)
        object.__setattr__(
            self,
            "uncertainty_milliseconds",
            canonical_safe_int(
                self.uncertainty_milliseconds,
                field="uncertainty_milliseconds",
                minimum=0,
                maximum=3_600_000,
            ),
        )
        if type(self.synchronized) is not bool:
            raise CanonicalizationError("synchronized must be a boolean")
        sampled = utc_datetime(self.sampled_at, field="sampled_at")
        valid_until = utc_datetime(self.valid_until, field="valid_until")
        wall_before = (
            sampled
            if self.wall_before_at is None
            else utc_datetime(self.wall_before_at, field="wall_before_at")
        )
        wall_after = (
            sampled
            if self.wall_after_at is None
            else utc_datetime(self.wall_after_at, field="wall_after_at")
        )
        if wall_after < wall_before or not wall_before <= sampled <= wall_after:
            raise CanonicalizationError(
                "sampled_at must lie inside a non-regressing wall-clock bracket"
            )
        if valid_until < sampled:
            raise CanonicalizationError("clock evidence expires before it is sampled")
        object.__setattr__(self, "sampled_at", sampled)
        object.__setattr__(self, "valid_until", valid_until)
        object.__setattr__(self, "wall_before_at", wall_before)
        object.__setattr__(self, "wall_after_at", wall_after)
        if self.clock_resolution_ns is not None:
            object.__setattr__(
                self,
                "clock_resolution_ns",
                canonical_safe_int(
                    self.clock_resolution_ns,
                    field="clock_resolution_ns",
                    minimum=1,
                ),
            )
        if self.observation_sha256 is not None:
            object.__setattr__(
                self,
                "observation_sha256",
                canonical_hash(self.observation_sha256, field="observation_sha256"),
            )
        if self.selectable_source_count is not None:
            object.__setattr__(
                self,
                "selectable_source_count",
                canonical_safe_int(
                    self.selectable_source_count,
                    field="selectable_source_count",
                    minimum=1,
                    maximum=64,
                ),
            )
        launch_values = (
            self.chronyd_launch_id,
            self.chronyd_runtime_observation_sha256,
        )
        if (launch_values[0] is None) != (launch_values[1] is None):
            raise CanonicalizationError(
                "chronyd launch and runtime-observation identities must be paired"
            )
        if launch_values[0] is not None:
            object.__setattr__(
                self,
                "chronyd_launch_id",
                canonical_hash(launch_values[0], field="chronyd_launch_id"),
            )
            object.__setattr__(
                self,
                "chronyd_runtime_observation_sha256",
                canonical_hash(
                    launch_values[1],
                    field="chronyd_runtime_observation_sha256",
                ),
            )


@dataclass(frozen=True, slots=True, kw_only=True)
class OperationalDeploymentAdmissionV4:
    """Out-of-band trust material required before runtime authority exists.

    The trust-root ID is deliberately supplied separately from the root object.
    A root file shipped beside a self-signed bundle therefore cannot bootstrap
    itself.  The runtime re-verifies the exact DSSE envelope at its governed
    startup clock rather than trusting a caller-constructed capability value.
    """

    trust_root: DeploymentTrustRootV4
    expected_trust_root_id: str
    approval: DeploymentBundleApprovalV4
    children: tuple[OperationalChildManifestV4, ...]
    expected_environment_id: str = "MAINNET"

    def __post_init__(self) -> None:
        if type(self.trust_root) is not DeploymentTrustRootV4:
            raise CanonicalizationError(
                "deployment admission requires an exact DeploymentTrustRootV4"
            )
        if type(self.approval) is not DeploymentBundleApprovalV4:
            raise CanonicalizationError(
                "deployment admission requires an exact DSSE approval"
            )
        if not isinstance(self.children, tuple) or len(self.children) != 6:
            raise CanonicalizationError(
                "deployment admission requires the exact six-child tuple"
            )
        object.__setattr__(
            self,
            "expected_trust_root_id",
            canonical_hash(
                self.expected_trust_root_id,
                field="expected_trust_root_id",
            ),
        )
        object.__setattr__(
            self,
            "expected_environment_id",
            canonical_identifier(
                self.expected_environment_id,
                field="expected_environment_id",
            ),
        )

    @property
    def bundle(self) -> DeploymentBundleV4:
        parsed = strict_json_loads(self.approval.payload_bytes)
        if not isinstance(parsed, dict):
            raise CanonicalizationError("signed deployment payload must be an object")
        return DeploymentBundleV4.from_mapping(parsed)

    @property
    def clock_policy(self) -> ClockSourcePolicyManifestV4:
        matches = [
            child
            for child in self.children
            if type(child) is ClockSourcePolicyManifestV4
        ]
        if len(matches) != 1:
            raise CanonicalizationError(
                "deployment admission requires one exact clock policy"
            )
        return matches[0]

    @property
    def tls_websocket_driver_policy(self) -> TlsWebSocketDriverPolicyV49B:
        """Return the exact nested V4.9B policy signed by this admission."""

        matches = [
            child
            for child in self.children
            if type(child) is RuntimeEnvironmentManifestV4
        ]
        if len(matches) != 1:
            raise CanonicalizationError(
                "deployment admission requires one exact runtime environment"
            )
        policy = matches[0].tls_websocket_driver_policy
        if type(policy) is not TlsWebSocketDriverPolicyV49B:
            raise CanonicalizationError(
                "deployment admission lacks the signed V4.9B driver policy"
            )
        return policy

    @property
    def tls_websocket_driver_policy_id(self) -> str:
        return self.tls_websocket_driver_policy.policy_id

    @property
    def transport_capacity_policy_v49f(self) -> TransportCapacityPolicyV49F | None:
        """Return the optional exact policy nested in the signed runtime child."""

        matches = [
            child
            for child in self.children
            if type(child) is RuntimeEnvironmentManifestV4
        ]
        if len(matches) != 1:
            raise CanonicalizationError(
                "deployment admission requires one exact runtime environment"
            )
        policy = matches[0].transport_capacity_policy_v49f
        if policy is not None and type(policy) is not TransportCapacityPolicyV49F:
            raise CanonicalizationError(
                "deployment admission contains an unsupported capacity policy"
            )
        return policy

    def verify(
        self,
        *,
        verified_at: datetime,
        signer: Any,
    ) -> VerifiedDeploymentCapabilityV4:
        public_key = getattr(signer, "public_key_bytes", None)
        if not isinstance(public_key, bytes):
            raise CanonicalizationError(
                "transport signer must expose exact Ed25519 public_key_bytes"
            )
        capability = verify_deployment_bundle_approval_v4(
            self.approval,
            trust_root=self.trust_root,
            expected_trust_root_id=self.expected_trust_root_id,
            children=self.children,
            verified_at=verified_at,
            expected_collector_attestation_key_id=(
                derive_transport_attestation_key_id(public_key)
            ),
        )
        if capability.environment_id != self.expected_environment_id:
            raise CanonicalizationError(
                "deployment environment differs from runtime admission"
            )
        if capability.collector_attestation_public_key_hex != public_key.hex():
            raise CanonicalizationError(
                "transport signer public key differs from deployment authorization"
            )
        return capability


@runtime_checkable
class ClockEvidenceSourceV4(Protocol):
    def sample(self) -> ClockEvidenceV4:
        """Return current, independently validated clock evidence."""


@runtime_checkable
class ExactTextFrameSenderV4(Protocol):
    async def send_exact_text_frame(
        self,
        payload: bytes,
        *,
        before_driver: Callable[[], None],
    ) -> None:
        """Write ``payload`` as one complete WebSocket TEXT frame.

        The method name is intentional: a generic high-level ``send(bytes)``
        often selects the Binary opcode and cannot satisfy this port.
        """


@runtime_checkable
class PhysicalTransportWriterLeasePortV4(Protocol):
    @property
    def holder_id(self) -> str:
        """Return the canonical operational writer identity."""

    @property
    def lease_token(self) -> str:
        """Return the in-process random lease capability while held."""

    def assert_held(self) -> None:
        """Fail if the process no longer owns the kernel-backed lease."""

    def release(self) -> None:
        """Release the kernel-backed lease idempotently."""


@runtime_checkable
class PhysicalTransportJournalPortV4(Protocol):
    def assert_current_operational_deployment(
        self,
        *,
        deployment_bundle_id: str,
        deployment_trust_root_id: str,
        deployment_sequence: int,
    ) -> None:
        """Require the projection's exact latest deployment before fencing."""

    def claim_transport_runtime_writer_fence(
        self, *, lease_token_sha256: str, holder_id: str
    ) -> int:
        """Transactionally supersede any older runtime epoch and bind this port."""

    def release_transport_runtime_writer_fence(
        self, *, lease_token_sha256: str
    ) -> None:
        """Mark this exact active application fence inactive."""

    def assert_transport_runtime_writer_fence(
        self, *, lease_token_sha256: str, generation: int
    ) -> None:
        """Validate the exact active application epoch in a read transaction."""

    def verify(self) -> Any:
        """Perform full local journal/projection verification."""

    def reconcile_unterminated_transport_sessions(
        self,
        *,
        detected_at: datetime,
        detected_monotonic_ns: int,
        detected_monotonic_clock_domain_id: str,
        signer: Any,
        idempotency_prefix: str,
    ) -> Sequence[TransportSessionTerminationV4]:
        """Durably terminate every prior open session before new authority."""

    def append_transport_session_attestation(
        self,
        session: TransportSessionAttestationV4,
        *,
        socket_owner_binding: TransportSocketOwnerBindingV4,
        idempotency_key: str,
    ) -> CommittedBoundTransportSessionV4:
        """Atomically commit one signed session and its eager socket owner."""

    def authorize_outbound_subscription_intent(
        self,
        transport_session_id: str,
        *,
        idempotency_key: str,
    ) -> OutboundSubscriptionIntentV4:
        """Commit and return the exact sole outbound subscription intent."""

    def bind_subscription_ack(
        self,
        *,
        outbound_subscription_intent_id: str,
        message_disposition_id: str,
        dispatch_started_at: datetime,
        dispatch_completed_at: datetime,
        dispatch_started_monotonic_ns: int,
        dispatch_completed_monotonic_ns: int,
        signer: Any,
        idempotency_key: str,
    ) -> SubscriptionAckBindingV4:
        """Bind one captured ACK to runtime-owned dispatch clocks."""

    def append_transport_session_termination(
        self,
        *,
        transport_session_id: str,
        reason: TransportSessionTerminationReasonV4,
        detected_at: datetime,
        detected_monotonic_ns: int,
        detected_monotonic_clock_domain_id: str,
        signer: Any,
        idempotency_key: str,
        close_code: int | None = None,
        close_reason_digest: str | None = None,
    ) -> TransportSessionTerminationV4:
        """Append the sole terminal event for the current session."""


@runtime_checkable
class TransportSocketOwnerPortV4(Protocol):
    """Private live capability for one already-connected transport socket.

    Production implementations must retain the socket and namespace handles
    needed to prove that every assertion describes the same live owner.  The
    signed journal stores only commitments; this port retains the capability.
    """

    def snapshot(self) -> TransportSocketOwnerSnapshotV4:
        """Return the current boot, namespace, clock, and kernel-socket identity."""

    def assert_same_owner(self, expected: TransportSocketOwnerSnapshotV4) -> None:
        """Fail unless this capability still controls the exact expected owner."""

    async def send_exact_text_frame(
        self,
        payload: bytes,
        *,
        before_driver: Callable[[], None],
    ) -> None:
        """Revalidate under the owner lock, then write one complete TEXT frame."""

    def abort(self) -> None:
        """Fail closed by making the owned socket unusable, idempotently."""


@dataclass(frozen=True, slots=True, kw_only=True)
class PhysicalTransportRuntimeConfigV4:
    maximum_clock_uncertainty_milliseconds: int = (
        V4_RUNTIME_DEFAULT_MAXIMUM_CLOCK_UNCERTAINTY_MILLISECONDS
    )
    maximum_clock_evidence_lifetime_seconds: int = (
        V4_RUNTIME_DEFAULT_MAXIMUM_CLOCK_EVIDENCE_LIFETIME_SECONDS
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "maximum_clock_uncertainty_milliseconds",
            canonical_safe_int(
                self.maximum_clock_uncertainty_milliseconds,
                field="maximum_clock_uncertainty_milliseconds",
                minimum=0,
                maximum=3_600_000,
            ),
        )
        object.__setattr__(
            self,
            "maximum_clock_evidence_lifetime_seconds",
            canonical_safe_int(
                self.maximum_clock_evidence_lifetime_seconds,
                field="maximum_clock_evidence_lifetime_seconds",
                minimum=1,
                maximum=3_600,
            ),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class PhysicalTransportRuntimeStartReportV4:
    recovered_capacity_measurement_attempt_ids: tuple[str, ...]
    reconciled_transport_session_ids: tuple[str, ...]
    deployment_bundle_id: str
    deployment_sequence: int
    deployment_trust_root_id: str
    clock_source_manifest_id: str
    monotonic_clock_domain_id: str
    writer_fence_generation: int


@dataclass(frozen=True, slots=True, kw_only=True)
class PhysicalTransportSendPermitV4:
    """One exact, one-shot capability issued only after durable intent commit."""

    permit_id: str
    writer_lease_token_sha256: str
    socket_lease_id: str
    transport_session_id: str
    outbound_subscription_intent_id: str
    connection_generation: int
    command_sha256: str
    command_bytes: bytes
    issued_at: datetime
    issued_monotonic_ns: int
    send_not_after: datetime
    send_not_after_monotonic_ns: int

    def __post_init__(self) -> None:
        for field_name in (
            "permit_id",
            "writer_lease_token_sha256",
            "socket_lease_id",
            "transport_session_id",
            "outbound_subscription_intent_id",
            "command_sha256",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        object.__setattr__(
            self,
            "connection_generation",
            canonical_safe_int(
                self.connection_generation,
                field="connection_generation",
                minimum=1,
            ),
        )
        if not isinstance(self.command_bytes, bytes) or not self.command_bytes:
            raise CanonicalizationError("command_bytes must be non-empty bytes")
        if hashlib.sha256(self.command_bytes).hexdigest() != self.command_sha256:
            raise CanonicalizationError("send permit command commitment differs")
        issued = utc_datetime(self.issued_at, field="issued_at")
        send_by = utc_datetime(self.send_not_after, field="send_not_after")
        if send_by <= issued:
            raise CanonicalizationError("send permit expires at or before issuance")
        object.__setattr__(self, "issued_at", issued)
        object.__setattr__(self, "send_not_after", send_by)
        object.__setattr__(
            self,
            "issued_monotonic_ns",
            canonical_safe_int(
                self.issued_monotonic_ns,
                field="issued_monotonic_ns",
                minimum=0,
            ),
        )
        object.__setattr__(
            self,
            "send_not_after_monotonic_ns",
            canonical_safe_int(
                self.send_not_after_monotonic_ns,
                field="send_not_after_monotonic_ns",
                minimum=self.issued_monotonic_ns + 1,
            ),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class PhysicalTransportDispatchWindowV4:
    transport_session_id: str
    outbound_subscription_intent_id: str
    socket_lease_id: str
    monotonic_clock_domain_id: str
    dispatch_started_at: datetime
    dispatch_completed_at: datetime
    dispatch_started_monotonic_ns: int
    dispatch_completed_monotonic_ns: int

    def __post_init__(self) -> None:
        for field_name in (
            "transport_session_id",
            "outbound_subscription_intent_id",
            "socket_lease_id",
            "monotonic_clock_domain_id",
        ):
            object.__setattr__(
                self,
                field_name,
                canonical_hash(getattr(self, field_name), field=field_name),
            )
        started = utc_datetime(self.dispatch_started_at, field="dispatch_started_at")
        completed = utc_datetime(
            self.dispatch_completed_at, field="dispatch_completed_at"
        )
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
        if completed < started or completed_ns <= started_ns:
            raise CanonicalizationError(
                "dispatch completion must causally follow dispatch start"
            )
        object.__setattr__(self, "dispatch_started_at", started)
        object.__setattr__(self, "dispatch_completed_at", completed)
        object.__setattr__(self, "dispatch_started_monotonic_ns", started_ns)
        object.__setattr__(self, "dispatch_completed_monotonic_ns", completed_ns)


@dataclass(frozen=True, slots=True, kw_only=True)
class PhysicalTransportIngressProgressV49D:
    """Non-capability summary of one causal RAW-ingress runtime step."""

    raw_ingress_commit_id: str
    ingress_sequence: int
    committed_raw_octets: int
    raw_ingress_batch_sha256: str
    parser_event_ids: tuple[str, ...]
    automatic_output_source_parser_event_ids: tuple[str, ...]
    automatic_dispatch_completion_event_ids: tuple[str, ...]
    automatic_protocol_output_chunks: tuple[bytes, ...]
    automatic_output_wire_chunk_counts: tuple[int, ...]
    automatic_protocol_output_frames: tuple[tuple[str, bytes], ...]
    actor_event_count_before: int
    actor_tail_event_id_before: str | None
    actor_event_count_after: int
    actor_tail_event_id_after: str | None
    retained_incomplete_octets: int
    used_initial_pending_ingress: bool
    websocket_parser_state: str
    admission_policy_id_v49f: str | None
    admission_epoch_v49f: int | None
    admission_sequence_v49f: int | None
    admission_queue_wait_nanoseconds_v49f: int | None
    admission_command_kind_v49f: str | None
    admission_reservation_work_units_v49f: int | None
    admission_admitted_loop_time_ns_v49f: int | None
    admission_started_loop_time_ns_v49f: int | None
    admission_start_deadline_loop_time_ns_v49f: int | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "raw_ingress_commit_id",
            canonical_hash(self.raw_ingress_commit_id, field="raw_ingress_commit_id"),
        )
        object.__setattr__(
            self,
            "ingress_sequence",
            canonical_safe_int(
                self.ingress_sequence, field="ingress_sequence", minimum=1
            ),
        )
        admission_values = (
            self.admission_policy_id_v49f,
            self.admission_epoch_v49f,
            self.admission_sequence_v49f,
            self.admission_queue_wait_nanoseconds_v49f,
            self.admission_command_kind_v49f,
            self.admission_reservation_work_units_v49f,
            self.admission_admitted_loop_time_ns_v49f,
            self.admission_started_loop_time_ns_v49f,
            self.admission_start_deadline_loop_time_ns_v49f,
        )
        if any(value is None for value in admission_values) and not all(
            value is None for value in admission_values
        ):
            raise CanonicalizationError(
                "V4.9F admission coordinates must be present together"
            )
        if self.admission_policy_id_v49f is not None:
            object.__setattr__(
                self,
                "admission_policy_id_v49f",
                canonical_hash(
                    self.admission_policy_id_v49f,
                    field="admission_policy_id_v49f",
                ),
            )
            for name, minimum in (
                ("admission_epoch_v49f", 1),
                ("admission_sequence_v49f", 1),
                ("admission_queue_wait_nanoseconds_v49f", 0),
                ("admission_reservation_work_units_v49f", 1),
                ("admission_admitted_loop_time_ns_v49f", 0),
                ("admission_started_loop_time_ns_v49f", 0),
                ("admission_start_deadline_loop_time_ns_v49f", 0),
            ):
                object.__setattr__(
                    self,
                    name,
                    canonical_safe_int(
                        getattr(self, name), field=name, minimum=minimum
                    ),
                )
            command_kind = canonical_identifier(
                self.admission_command_kind_v49f,
                field="admission_command_kind_v49f",
                maximum=32,
            )
            if command_kind != TransportCommandKindV49F.INGRESS.value:
                raise CanonicalizationError(
                    "ingress progress requires an INGRESS admission grant"
                )
            object.__setattr__(self, "admission_command_kind_v49f", command_kind)
            admitted_ns = self.admission_admitted_loop_time_ns_v49f
            started_ns = self.admission_started_loop_time_ns_v49f
            deadline_ns = self.admission_start_deadline_loop_time_ns_v49f
            queue_wait_ns = self.admission_queue_wait_nanoseconds_v49f
            assert admitted_ns is not None
            assert started_ns is not None
            assert deadline_ns is not None
            assert queue_wait_ns is not None
            if not admitted_ns <= started_ns <= deadline_ns:
                raise CanonicalizationError(
                    "V4.9F admission timing must satisfy admitted <= started <= deadline"
                )
            if queue_wait_ns != started_ns - admitted_ns:
                raise CanonicalizationError(
                    "V4.9F admission queue wait differs from grant timing"
                )
        object.__setattr__(
            self,
            "committed_raw_octets",
            canonical_safe_int(
                self.committed_raw_octets,
                field="committed_raw_octets",
                minimum=1,
            ),
        )
        object.__setattr__(
            self,
            "raw_ingress_batch_sha256",
            canonical_hash(
                self.raw_ingress_batch_sha256,
                field="raw_ingress_batch_sha256",
            ),
        )
        parser_ids = tuple(
            canonical_hash(value, field="parser_event_ids")
            for value in self.parser_event_ids
        )
        completion_ids = tuple(
            canonical_hash(value, field="automatic_dispatch_completion_event_ids")
            for value in self.automatic_dispatch_completion_event_ids
        )
        if len(set(parser_ids)) != len(parser_ids) or len(set(completion_ids)) != len(
            completion_ids
        ):
            raise CanonicalizationError(
                "parser and completion event IDs must each be unique"
            )
        source_ids = tuple(
            canonical_hash(value, field="automatic_output_source_parser_event_ids")
            for value in self.automatic_output_source_parser_event_ids
        )
        if len(set(source_ids)) != len(source_ids):
            raise CanonicalizationError(
                "automatic output source parser event IDs contain duplicates"
            )
        if any(value not in parser_ids for value in source_ids):
            raise CanonicalizationError(
                "automatic output source is absent from parser event IDs"
            )
        parser_positions = tuple(parser_ids.index(value) for value in source_ids)
        if parser_positions != tuple(sorted(parser_positions)):
            raise CanonicalizationError(
                "automatic output sources are not an ordered parser subsequence"
            )
        if set(parser_ids) & set(completion_ids):
            raise CanonicalizationError(
                "parser and dispatch completion event IDs must be disjoint"
            )
        object.__setattr__(
            self,
            "automatic_output_source_parser_event_ids",
            source_ids,
        )
        object.__setattr__(self, "parser_event_ids", parser_ids)
        object.__setattr__(
            self,
            "automatic_dispatch_completion_event_ids",
            completion_ids,
        )
        outputs = self.automatic_protocol_output_chunks
        if type(outputs) is not tuple or any(
            type(chunk) is not bytes or not chunk for chunk in outputs
        ):
            raise CanonicalizationError(
                "automatic_protocol_output_chunks must be exact non-empty byte chunks"
            )
        frames = self.automatic_protocol_output_frames
        chunk_counts = self.automatic_output_wire_chunk_counts
        if type(chunk_counts) is not tuple:
            raise CanonicalizationError(
                "automatic_output_wire_chunk_counts must be an exact tuple"
            )
        normalized_chunk_counts = tuple(
            canonical_safe_int(
                value, field="automatic_output_wire_chunk_counts", minimum=1
            )
            for value in chunk_counts
        )
        object.__setattr__(
            self, "automatic_output_wire_chunk_counts", normalized_chunk_counts
        )
        if type(frames) is not tuple:
            raise CanonicalizationError(
                "automatic_protocol_output_frames must be an exact tuple"
            )
        for frame in frames:
            if (
                type(frame) is not tuple
                or len(frame) != 2
                or frame[0] not in {"CLOSE", "PONG"}
                or type(frame[1]) is not bytes
            ):
                raise CanonicalizationError(
                    "automatic protocol output frames must be exact logical pairs"
                )
        if not (
            len(frames)
            == len(source_ids)
            == len(completion_ids)
            == len(normalized_chunk_counts)
        ) or sum(normalized_chunk_counts) != len(outputs):
            raise CanonicalizationError(
                "automatic logical, physical, source, and completion evidence differs"
            )
        for name in ("actor_event_count_before", "actor_event_count_after"):
            object.__setattr__(
                self,
                name,
                canonical_safe_int(getattr(self, name), field=name, minimum=0),
            )
        for count_name, tail_name in (
            ("actor_event_count_before", "actor_tail_event_id_before"),
            ("actor_event_count_after", "actor_tail_event_id_after"),
        ):
            tail = getattr(self, tail_name)
            if tail is not None:
                object.__setattr__(
                    self, tail_name, canonical_hash(tail, field=tail_name)
                )
            if (getattr(self, count_name) == 0) != (tail is None):
                raise CanonicalizationError(
                    f"{tail_name} must be present exactly when actor events exist"
                )
        if self.actor_event_count_after < self.actor_event_count_before:
            raise CanonicalizationError("actor event count regressed during ingress")
        object.__setattr__(
            self,
            "retained_incomplete_octets",
            canonical_safe_int(
                self.retained_incomplete_octets,
                field="retained_incomplete_octets",
                minimum=0,
            ),
        )
        if type(self.used_initial_pending_ingress) is not bool:
            raise CanonicalizationError(
                "used_initial_pending_ingress must be an exact boolean"
            )
        state = canonical_identifier(
            self.websocket_parser_state,
            field="websocket_parser_state",
            maximum=32,
        )
        if state not in {"OPEN", "CLOSING", "CLOSED", "FAILED"}:
            raise CanonicalizationError("unsupported websocket_parser_state")
        object.__setattr__(self, "websocket_parser_state", state)


class CapacityMeasurementIngressAuthorizationV49F:
    """Sealed, one-shot authority for exactly one Raw-V7 ingress operation.

    This object is deliberately noncanonical and process-local.  It binds the
    retained campaign object and declaration by identity as well as the exact
    runtime, task, process, thread, event loop, and fork generation.  It grants
    no socket effect by itself; the runtime must also hold the exact active A1
    admission grant.
    """

    __slots__ = (
        "_boottime_ns",
        "_boottime_origin_ns",
        "_campaign",
        "_consumed",
        "_declaration",
        "_fork_generation",
        "_grant",
        "_journal",
        "_loop",
        "_loop_origin_ns",
        "_observer_monotonic_ns",
        "_observer_origin_ns",
        "_attempt_commit_consumed",
        "_committed_attempt_id",
        "_attempt_offsets",
        "_pid",
        "_previous_operation_terminal_id",
        "_runtime",
        "_task",
        "_thread_id",
    )

    def __init__(
        self,
        *,
        _token: object,
        runtime: PhysicalTransportRuntimeV4,
        campaign: object,
        declaration: Any,
        previous_operation_terminal_id: str | None,
        observer_monotonic_ns: Callable[[], int],
        boottime_ns: Callable[[], int],
        observer_origin_ns: int,
        boottime_origin_ns: int,
        loop_origin_ns: int,
    ) -> None:
        from .physical_transport_capacity_lifecycle_v49f import (
            CapacityMeasurementOperationDeclarationV49F,
        )

        if _token is not _CAPACITY_MEASUREMENT_AUTHORIZATION_TOKEN_V49F:
            raise TypeError(
                "capacity measurement authorizations are runtime-issued only"
            )
        if type(runtime) is not PhysicalTransportRuntimeV4:
            raise TypeError("capacity authorization requires the exact runtime")
        if campaign is None:
            raise TypeError("capacity authorization requires one retained campaign")
        if type(declaration) is not CapacityMeasurementOperationDeclarationV49F:
            raise TypeError("capacity authorization requires one exact declaration")
        if not callable(observer_monotonic_ns) or not callable(boottime_ns):
            raise TypeError("capacity authorization clocks must be callable")
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError as exc:
            raise CapacityMeasurementIngressAuthorizationV49FError(
                "capacity authorization requires one running event loop"
            ) from exc
        task = asyncio.current_task()
        if task is None:
            raise CapacityMeasurementIngressAuthorizationV49FError(
                "capacity authorization requires one current task"
            )
        self._runtime = runtime
        self._campaign = campaign
        self._declaration = declaration
        journal = runtime._transport_actor_journal_v49c  # noqa: SLF001
        from .physical_transport_actor_journal_v49c import (
            PhysicalTransportActorProjectionJournalV49C,
        )

        if type(journal) is not PhysicalTransportActorProjectionJournalV49C:
            raise CapacityMeasurementIngressAuthorizationV49FError(
                "capacity authorization requires the exact active actor journal"
            )
        self._journal = journal
        self._previous_operation_terminal_id = (
            None
            if previous_operation_terminal_id is None
            else canonical_hash(
                previous_operation_terminal_id,
                field="previous_operation_terminal_id",
            )
        )
        self._observer_monotonic_ns = observer_monotonic_ns
        self._boottime_ns = boottime_ns
        self._observer_origin_ns = canonical_safe_int(
            observer_origin_ns, field="observer_origin_ns", minimum=0
        )
        self._boottime_origin_ns = canonical_safe_int(
            boottime_origin_ns, field="boottime_origin_ns", minimum=0
        )
        self._loop_origin_ns = canonical_safe_int(
            loop_origin_ns, field="loop_origin_ns", minimum=0
        )
        self._pid = os.getpid()
        self._thread_id = threading.get_ident()
        self._loop = loop
        self._task = task
        self._fork_generation = _CAPACITY_MEASUREMENT_FORK_GENERATION_V49F
        self._consumed = False
        self._grant: TransportAdmissionGrantV49F | None = None
        self._attempt_offsets: tuple[int, int, int] | None = None
        self._attempt_commit_consumed = False
        self._committed_attempt_id: str | None = None

    @property
    def declaration(self) -> Any:
        return self._declaration

    @property
    def campaign(self) -> object:
        return self._campaign

    @property
    def previous_operation_terminal_id(self) -> str | None:
        return self._previous_operation_terminal_id

    @property
    def loop_origin_nanoseconds(self) -> int:
        return self._loop_origin_ns

    @property
    def observer_origin_nanoseconds(self) -> int:
        return self._observer_origin_ns

    @property
    def boottime_origin_nanoseconds(self) -> int:
        return self._boottime_origin_ns

    @property
    def committed_attempt_id(self) -> str | None:
        """Expose only the durable attempt identity for postmortem sample recovery."""

        return self._committed_attempt_id

    def _assert_context(
        self,
        *,
        runtime: PhysicalTransportRuntimeV4,
        campaign: object,
        declaration: Any,
    ) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError as exc:
            raise CapacityMeasurementIngressAuthorizationV49FError(
                "capacity authorization left its event loop"
            ) from exc
        if (
            type(self) is not CapacityMeasurementIngressAuthorizationV49F
            or self._consumed
            or runtime is not self._runtime
            or campaign is not self._campaign
            or declaration is not self._declaration
            or os.getpid() != self._pid
            or threading.get_ident() != self._thread_id
            or loop is not self._loop
            or asyncio.current_task() is not self._task
            or self._fork_generation != _CAPACITY_MEASUREMENT_FORK_GENERATION_V49F
        ):
            raise CapacityMeasurementIngressAuthorizationV49FError(
                "capacity authorization is stale, substituted, migrated, or consumed"
            )

    def consume(
        self,
        *,
        runtime: PhysicalTransportRuntimeV4,
        campaign: object,
        declaration: Any,
        grant: TransportAdmissionGrantV49F,
    ) -> None:
        """Consume this authorization at the exact A1 STARTED boundary."""

        self._assert_context(
            runtime=runtime,
            campaign=campaign,
            declaration=declaration,
        )
        if (
            type(grant) is not TransportAdmissionGrantV49F
            or grant.command_kind is not TransportCommandKindV49F.INGRESS
        ):
            raise CapacityMeasurementIngressAuthorizationV49FError(
                "capacity authorization lacks the exact INGRESS admission grant"
            )
        self._consumed = True
        self._grant = grant

    def _assert_precommit_journal_v49f(self, journal: object) -> None:
        self._assert_context_after_consumption()
        if (
            journal is not self._journal
            or self._attempt_commit_consumed
            or self._grant is None
        ):
            raise CapacityMeasurementIngressAuthorizationV49FError(
                "capacity authorization left its exact precommit journal boundary"
            )

    @staticmethod
    def _read_clock(clock: Callable[[], int], *, field: str) -> int:
        value = clock()
        if type(value) is not int:
            raise CapacityMeasurementIngressAuthorizationV49FError(
                f"{field} clock returned a non-integer"
            )
        return canonical_safe_int(value, field=field, minimum=0)

    def _read_offsets(self, *, phase: str) -> tuple[int, int, int]:
        observer = self._read_clock(
            self._observer_monotonic_ns,
            field=f"observer_{phase}_nanoseconds",
        )
        boottime = self._read_clock(
            self._boottime_ns,
            field=f"boottime_{phase}_nanoseconds",
        )
        loop_now = int(self._loop.time() * 1_000_000_000)
        offsets = (
            observer - self._observer_origin_ns,
            boottime - self._boottime_origin_ns,
            loop_now - self._loop_origin_ns,
        )
        if any(value < 0 for value in offsets):
            raise CapacityMeasurementIngressAuthorizationV49FError(
                f"capacity {phase} clock precedes its retained campaign origin"
            )
        normalized = tuple(
            canonical_safe_int(
                value,
                field=f"capacity_{phase}_offset",
                minimum=0,
            )
            for value in offsets
        )
        return normalized[0], normalized[1], normalized[2]

    def attempt_offsets(self) -> tuple[int, int, int]:
        """Sample the actual attempt boundary after A1 STARTED, exactly once."""

        self._assert_precommit_journal_v49f(self._journal)
        if self._attempt_offsets is not None:
            raise CapacityMeasurementIngressAuthorizationV49FError(
                "capacity attempt offsets were already sampled"
            )
        self._attempt_offsets = self._read_offsets(phase="attempt")
        return self._attempt_offsets

    def terminal_offsets(self) -> tuple[int, int, int]:
        """Read terminal offsets synchronously without yielding cancellation."""

        self._assert_context_after_consumption()
        if self._attempt_offsets is None or not self._attempt_commit_consumed:
            raise CapacityMeasurementIngressAuthorizationV49FError(
                "capacity terminal offsets require one committed attempt"
            )
        offsets = self._read_offsets(phase="terminal")
        if any(value < start for value, start in zip(offsets, self._attempt_offsets)):
            raise CapacityMeasurementIngressAuthorizationV49FError(
                "capacity terminal clocks regress from the actual attempt"
            )
        return offsets

    def _consume_attempt_commit_v49f(self, *, journal: object, attempt: Any) -> None:
        from .physical_transport_capacity_lifecycle_v49f import (
            CapacityMeasurementOperationAttemptV49F,
        )

        self._assert_precommit_journal_v49f(journal)
        grant = self._grant
        offsets = self._attempt_offsets
        gate = self._runtime._transport_admission_gate_v49f  # noqa: SLF001
        if (
            type(attempt) is not CapacityMeasurementOperationAttemptV49F
            or grant is None
            or offsets is None
            or gate is None
            or attempt.transport_capacity_policy is not gate.policy
            or attempt.transport_capacity_policy_id != gate.policy.policy_id
            or attempt.declaration_id != self._declaration.declaration_id
            or attempt.campaign_manifest_id != self._declaration.campaign_manifest_id
            or attempt.manifest_authority_id != self._declaration.manifest_authority_id
            or attempt.measurement_design_id != self._declaration.measurement_design_id
            or (
                attempt.observer_start_offset_nanoseconds,
                attempt.boottime_start_offset_nanoseconds,
                attempt.loop_time_start_offset_nanoseconds,
            )
            != offsets
            or int(attempt.loop_time_origin_nanoseconds) != self._loop_origin_ns
            or self._observer_origin_ns + attempt.observer_start_offset_nanoseconds
            < int(attempt.started_monotonic_ns)
            or attempt.admission_policy_id != grant.policy_id
            or attempt.admission_command_kind.value != grant.command_kind.value
            or attempt.admission_epoch != grant.admission_epoch
            or attempt.admission_sequence != grant.admission_sequence
            or attempt.admission_reservation_work_units != grant.reservation_work_units
            or int(attempt.admission_admitted_loop_time_ns)
            != grant.admitted_loop_time_ns
            or int(attempt.admission_started_loop_time_ns) != grant.started_loop_time_ns
            or int(attempt.admission_start_deadline_loop_time_ns)
            != grant.start_deadline_loop_time_ns
            or attempt.admission_queue_wait_nanoseconds != grant.queue_wait_nanoseconds
        ):
            raise CapacityMeasurementIngressAuthorizationV49FError(
                "capacity attempt differs from its declaration, clocks, or A1 grant"
            )
        self._runtime._assert_actor_admission_v49f(  # noqa: SLF001
            grant,
            expected_kind=TransportCommandKindV49F.INGRESS,
        )
        self._attempt_commit_consumed = True
        self._committed_attempt_id = attempt.attempt_id

    def _assert_context_after_consumption(self) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError as exc:
            raise CapacityMeasurementIngressAuthorizationV49FError(
                "consumed capacity authorization left its event loop"
            ) from exc
        if (
            type(self) is not CapacityMeasurementIngressAuthorizationV49F
            or not self._consumed
            or os.getpid() != self._pid
            or threading.get_ident() != self._thread_id
            or loop is not self._loop
            or asyncio.current_task() is not self._task
            or self._runtime._transport_actor_journal_v49c  # noqa: SLF001
            is not self._journal
            or self._fork_generation != _CAPACITY_MEASUREMENT_FORK_GENERATION_V49F
        ):
            raise CapacityMeasurementIngressAuthorizationV49FError(
                "consumed capacity authorization left its exact owner"
            )


@dataclass(frozen=True, slots=True, kw_only=True)
class CapacityMeasurementIngressClosureV49F:
    """Noncanonical exact return from one successful Raw-V7 ingress."""

    committed_attempt: Any
    terminalized_prefix: Any
    returned_progress: PhysicalTransportIngressProgressV49D
    returned_progress_evidence: Any

    def __post_init__(self) -> None:
        from .physical_projection_v4 import (
            CommittedCapacityMeasurementOperationAttemptV49F,
        )
        from .physical_transport_capacity_lifecycle_v49f import (
            CapacityMeasurementLifecycleTerminalTriggerV49F,
            CapacityMeasurementOperationPrefixV49F,
        )
        from .physical_transport_capacity_measurement_v49f import (
            CapacityMeasurementIngressProgressEvidenceV49F,
        )

        prefix = self.terminalized_prefix
        terminal = getattr(prefix, "terminal", None)
        if (
            type(self.committed_attempt)
            is not CommittedCapacityMeasurementOperationAttemptV49F
            or type(prefix) is not CapacityMeasurementOperationPrefixV49F
            or prefix.attempt != self.committed_attempt.attempt
            or terminal is None
            or terminal.terminal_trigger
            is not CapacityMeasurementLifecycleTerminalTriggerV49F.RETURNED
            or type(self.returned_progress) is not PhysicalTransportIngressProgressV49D
            or type(self.returned_progress_evidence)
            is not CapacityMeasurementIngressProgressEvidenceV49F
            or terminal.returned_progress_evidence_id
            != self.returned_progress_evidence.ingress_progress_evidence_id
            or self.returned_progress.raw_ingress_commit_id
            != terminal.terminal_raw_ingress_commit_id
            or self.returned_progress.ingress_sequence
            != terminal.terminal_raw_ingress_sequence
        ):
            raise CanonicalizationError(
                "capacity ingress closure is not one exact returned operation"
            )


@dataclass(frozen=True, slots=True, kw_only=True)
class PhysicalTransportManifestAuthoritySnapshotV49F:
    """Immutable, non-capability runtime truth for one A2-M raw-V6 subject."""

    deployment_bundle_id: str
    deployment_trust_root_id: str
    deployment_sequence: int
    environment_id: str
    collector_release_manifest_id: str
    runtime_environment_manifest_id: str
    collector_key_authorization_manifest_id: str
    collector_attestation_key_id: str
    tls_websocket_driver_policy_id: str
    retained_driver_runtime_observation_sha256: str
    transport_session_id: str
    driver_evidence_nonce_sha256: str
    kernel_socket_identity: str
    kernel_boot_id: str
    time_namespace_id: str
    network_namespace_id: str
    monotonic_clock_domain_id: str
    clock_source_manifest_id: str
    chronyd_launch_id: str | None
    chronyd_runtime_observation_sha256: str | None
    transport_capacity_policy_id: str
    transport_runtime_schema_version: str
    authority_profile: str
    captured_at_utc: datetime
    captured_monotonic_ns: int
    release_name: str
    release_version: str
    release_source_tree_sha256: str
    release_build_artifact_sha256: str
    release_entrypoint: str

    def __post_init__(self) -> None:
        for name in (
            "deployment_bundle_id",
            "deployment_trust_root_id",
            "collector_release_manifest_id",
            "runtime_environment_manifest_id",
            "collector_key_authorization_manifest_id",
            "collector_attestation_key_id",
            "tls_websocket_driver_policy_id",
            "retained_driver_runtime_observation_sha256",
            "transport_session_id",
            "driver_evidence_nonce_sha256",
            "kernel_socket_identity",
            "time_namespace_id",
            "network_namespace_id",
            "monotonic_clock_domain_id",
            "clock_source_manifest_id",
            "transport_capacity_policy_id",
            "release_source_tree_sha256",
            "release_build_artifact_sha256",
        ):
            object.__setattr__(
                self,
                name,
                canonical_hash(getattr(self, name), field=name),
            )
        object.__setattr__(
            self,
            "deployment_sequence",
            canonical_safe_int(
                self.deployment_sequence,
                field="deployment_sequence",
                minimum=1,
            ),
        )
        for name, maximum in (
            ("environment_id", 128),
            ("kernel_boot_id", 128),
            ("release_name", 256),
            ("release_version", 256),
            ("release_entrypoint", 1024),
            ("transport_runtime_schema_version", 128),
            ("authority_profile", 32),
        ):
            object.__setattr__(
                self,
                name,
                canonical_identifier(
                    getattr(self, name),
                    field=name,
                    maximum=maximum,
                ),
            )
        if (
            self.transport_runtime_schema_version
            != PHYSICAL_TRANSPORT_RUNTIME_V4_SCHEMA_VERSION
        ):
            raise CanonicalizationError(
                "transport runtime schema version differs from the running authority"
            )
        if self.authority_profile not in {"LIVE_LINUX", "EXACT_TEST"}:
            raise CanonicalizationError("manifest authority profile is unsupported")
        chronyd_values = (
            self.chronyd_launch_id,
            self.chronyd_runtime_observation_sha256,
        )
        if (chronyd_values[0] is None) != (chronyd_values[1] is None):
            raise CanonicalizationError(
                "chronyd launch and runtime-observation IDs must be paired"
            )
        if chronyd_values[0] is not None:
            object.__setattr__(
                self,
                "chronyd_launch_id",
                canonical_hash(chronyd_values[0], field="chronyd_launch_id"),
            )
            object.__setattr__(
                self,
                "chronyd_runtime_observation_sha256",
                canonical_hash(
                    chronyd_values[1],
                    field="chronyd_runtime_observation_sha256",
                ),
            )
        object.__setattr__(
            self,
            "captured_at_utc",
            utc_datetime(self.captured_at_utc, field="captured_at_utc"),
        )
        object.__setattr__(
            self,
            "captured_monotonic_ns",
            canonical_safe_int(
                self.captured_monotonic_ns,
                field="captured_monotonic_ns",
                minimum=0,
            ),
        )

    def identity_payload(self) -> dict[str, Any]:
        return {
            name: (utc_iso(value) if name == "captured_at_utc" else value)
            for name in self.__dataclass_fields__
            for value in (getattr(self, name),)
        }

    def authority_binding_payload(self) -> dict[str, Any]:
        """Return exact recapturable fields, excluding observation chronology."""

        return {
            name: value
            for name, value in self.identity_payload().items()
            if name not in {"captured_at_utc", "captured_monotonic_ns"}
        }

    @property
    def snapshot_id(self) -> str:
        return sha256_digest(
            {
                "canonicalization_version": CANONICALIZATION_VERSION,
                "domain": "RiskYieldMMPhysicalTransportManifestAuthoritySnapshotV49F",
                "payload": self.identity_payload(),
                "schema_version": PHYSICAL_TRANSPORT_A2M_RAW_V49F_V6_SCHEMA_VERSION,
            }
        )

    def as_dict(self) -> dict[str, Any]:
        return {**self.identity_payload(), "snapshot_id": self.snapshot_id}


@dataclass(frozen=True, slots=True, kw_only=True)
class PhysicalTransportManifestAuthoritySignatureV49F:
    """Collector-key signature over one canonical A2-M authority subject."""

    authority_subject_id: str
    deployment_bundle_id: str
    collector_attestation_key_id: str
    collector_attestation_public_key_hex: str
    transport_session_id: str
    signature_hex: str

    def __post_init__(self) -> None:
        for name in (
            "authority_subject_id",
            "deployment_bundle_id",
            "collector_attestation_key_id",
            "transport_session_id",
        ):
            object.__setattr__(
                self,
                name,
                canonical_hash(getattr(self, name), field=name),
            )
        public_hex = self.collector_attestation_public_key_hex
        signature_hex = self.signature_hex
        if (
            type(public_hex) is not str
            or len(public_hex) != 64
            or public_hex.lower() != public_hex
        ):
            raise CanonicalizationError(
                "collector attestation public key must be 32-byte lowercase hex"
            )
        if (
            type(signature_hex) is not str
            or len(signature_hex) != 128
            or signature_hex.lower() != signature_hex
        ):
            raise CanonicalizationError(
                "manifest authority signature must be 64-byte lowercase hex"
            )
        try:
            public_key = bytes.fromhex(public_hex)
            signature = bytes.fromhex(signature_hex)
        except ValueError as exc:
            raise CanonicalizationError(
                "manifest authority key/signature is not hexadecimal"
            ) from exc
        derived_key_id = derive_transport_attestation_key_id(public_key)
        if derived_key_id != self.collector_attestation_key_id:
            raise CanonicalizationError(
                "manifest authority key ID differs from its public key"
            )
        try:
            Ed25519CheckpointVerifier.from_public_bytes(public_key).verify(
                canonical_json_bytes(self.signing_payload()),
                signature,
            )
        except Exception as exc:
            raise CanonicalizationError(
                "manifest authority signature is invalid"
            ) from exc

    def identity_payload(self) -> dict[str, Any]:
        return {
            "authority_subject_id": self.authority_subject_id,
            "deployment_bundle_id": self.deployment_bundle_id,
            "collector_attestation_key_id": self.collector_attestation_key_id,
            "transport_session_id": self.transport_session_id,
        }

    def signing_payload(self) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            "domain": _A2M_MANIFEST_AUTHORITY_SIGNING_DOMAIN_V49F,
            "payload": self.identity_payload(),
            "schema_version": PHYSICAL_TRANSPORT_A2M_RAW_V49F_V6_SCHEMA_VERSION,
        }

    def verify_signature(self) -> None:
        public_key = bytes.fromhex(self.collector_attestation_public_key_hex)
        Ed25519CheckpointVerifier.from_public_bytes(public_key).verify(
            canonical_json_bytes(self.signing_payload()),
            bytes.fromhex(self.signature_hex),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            **self.identity_payload(),
            "collector_attestation_public_key_hex": (
                self.collector_attestation_public_key_hex
            ),
            "signature_hex": self.signature_hex,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class PhysicalTransportManifestAuthoritySignatureV49FV7:
    """Runtime proof that the admitted collector key signed one Raw-V7 subject."""

    authority_subject_id: str
    deployment_bundle_id: str
    collector_attestation_key_id: str
    collector_attestation_public_key_hex: str
    transport_session_id: str
    signed_payload_sha256: str
    signature_hex: str

    def __post_init__(self) -> None:
        for name in (
            "authority_subject_id",
            "deployment_bundle_id",
            "collector_attestation_key_id",
            "transport_session_id",
            "signed_payload_sha256",
        ):
            object.__setattr__(
                self,
                name,
                canonical_hash(getattr(self, name), field=name),
            )
        public_hex = self.collector_attestation_public_key_hex
        signature_hex = self.signature_hex
        if (
            type(public_hex) is not str
            or len(public_hex) != 64
            or public_hex.lower() != public_hex
        ):
            raise CanonicalizationError(
                "Raw-V7 collector public key must be 32-byte lowercase hex"
            )
        if (
            type(signature_hex) is not str
            or len(signature_hex) != 128
            or signature_hex.lower() != signature_hex
        ):
            raise CanonicalizationError(
                "Raw-V7 manifest signature must be 64-byte lowercase hex"
            )
        try:
            public_key = bytes.fromhex(public_hex)
            bytes.fromhex(signature_hex)
        except ValueError as exc:
            raise CanonicalizationError(
                "Raw-V7 manifest key/signature is not hexadecimal"
            ) from exc
        if derive_transport_attestation_key_id(public_key) != (
            self.collector_attestation_key_id
        ):
            raise CanonicalizationError(
                "Raw-V7 manifest key ID differs from its public key"
            )


@dataclass(frozen=True, slots=True, kw_only=True)
class PhysicalTransportCapacityMeasurementBoundaryV49F:
    """Constant-cost quiescent runtime identity and actor counters.

    This value carries no owner, socket, driver, actor, journal, parser, grant,
    or effect capability.  It is diagnostic input for the closed A2-M runner.
    """

    transport_session_id: str
    driver_evidence_nonce_sha256: str
    kernel_socket_identity: str
    transport_capacity_policy_id: str
    admission_epoch: int
    admission_closed: bool
    admission_terminal_barrier_admission_sequence: int | None
    admission_terminal_barrier_committed: bool
    admission_active_admission_sequence: int | None
    admission_active_command_kind: str | None
    admission_waiting_admission_sequences: tuple[int, ...]
    admission_waiting_command_kinds: tuple[str, ...]
    admission_oldest_waiting_age_nanoseconds: int
    admission_reserved_work_units: int
    admission_maximum_observed_admitted_commands: int
    admission_maximum_observed_reserved_work_units: int
    admission_last_started_queue_wait_nanoseconds: int
    admission_maximum_observed_queue_wait_nanoseconds: int
    admission_released_commands: int
    admission_rejected_commands: int
    admission_duplicate_kind_rejections: int
    admission_terminal_barrier_rejections: int
    admission_capacity_rejections: int
    admission_closed_rejections: int
    admission_timed_out_commands: int
    admission_cancelled_before_entry_commands: int
    admission_closed_before_entry_commands: int
    actor_event_count: int
    actor_tail_event_id: str | None
    actor_wire_queue_events: int
    actor_wire_queue_octets: int
    runtime_state: str

    def __post_init__(self) -> None:
        for name in (
            "transport_session_id",
            "driver_evidence_nonce_sha256",
            "kernel_socket_identity",
            "transport_capacity_policy_id",
        ):
            object.__setattr__(
                self, name, canonical_hash(getattr(self, name), field=name)
            )
        if self.actor_tail_event_id is not None:
            object.__setattr__(
                self,
                "actor_tail_event_id",
                canonical_hash(self.actor_tail_event_id, field="actor_tail_event_id"),
            )
        for name in (
            "admission_closed",
            "admission_terminal_barrier_committed",
        ):
            if type(getattr(self, name)) is not bool:
                raise CanonicalizationError(f"{name} must be an exact boolean")
        for name in (
            "admission_terminal_barrier_admission_sequence",
            "admission_active_admission_sequence",
        ):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(
                    self,
                    name,
                    canonical_safe_int(value, field=name, minimum=1),
                )
        if self.admission_active_command_kind is not None:
            if type(self.admission_active_command_kind) is not str:
                raise CanonicalizationError(
                    "admission_active_command_kind must be None or an exact string"
                )
            active_kind = canonical_identifier(
                self.admission_active_command_kind,
                field="admission_active_command_kind",
                maximum=32,
            )
            if active_kind not in {item.value for item in TransportCommandKindV49F}:
                raise CanonicalizationError(
                    "admission_active_command_kind is unsupported"
                )
            object.__setattr__(self, "admission_active_command_kind", active_kind)
        if type(self.admission_waiting_admission_sequences) is not tuple:
            raise CanonicalizationError(
                "admission_waiting_admission_sequences must be an exact tuple"
            )
        waiting_sequences = tuple(
            canonical_safe_int(
                value, field="admission_waiting_admission_sequences", minimum=1
            )
            for value in self.admission_waiting_admission_sequences
        )
        if len(set(waiting_sequences)) != len(
            waiting_sequences
        ) or waiting_sequences != tuple(sorted(waiting_sequences)):
            raise CanonicalizationError(
                "admission waiting sequences must be unique and increasing"
            )
        object.__setattr__(
            self, "admission_waiting_admission_sequences", waiting_sequences
        )
        if type(self.admission_waiting_command_kinds) is not tuple or any(
            type(value) is not str for value in self.admission_waiting_command_kinds
        ):
            raise CanonicalizationError(
                "admission_waiting_command_kinds must be an exact tuple of strings"
            )
        waiting_kinds = tuple(
            canonical_identifier(
                value, field="admission_waiting_command_kinds", maximum=32
            )
            for value in self.admission_waiting_command_kinds
        )
        if any(
            value not in {item.value for item in TransportCommandKindV49F}
            for value in waiting_kinds
        ):
            raise CanonicalizationError(
                "admission_waiting_command_kinds contains an unsupported kind"
            )
        object.__setattr__(self, "admission_waiting_command_kinds", waiting_kinds)
        if len(waiting_sequences) != len(waiting_kinds):
            raise CanonicalizationError(
                "admission waiting sequence and kind counts differ"
            )
        for name, minimum in (
            ("admission_epoch", 1),
            ("admission_oldest_waiting_age_nanoseconds", 0),
            ("admission_reserved_work_units", 0),
            ("admission_maximum_observed_admitted_commands", 0),
            ("admission_maximum_observed_reserved_work_units", 0),
            ("admission_last_started_queue_wait_nanoseconds", 0),
            ("admission_maximum_observed_queue_wait_nanoseconds", 0),
            ("admission_released_commands", 0),
            ("admission_rejected_commands", 0),
            ("admission_duplicate_kind_rejections", 0),
            ("admission_terminal_barrier_rejections", 0),
            ("admission_capacity_rejections", 0),
            ("admission_closed_rejections", 0),
            ("admission_timed_out_commands", 0),
            ("admission_cancelled_before_entry_commands", 0),
            ("admission_closed_before_entry_commands", 0),
            ("actor_event_count", 0),
            ("actor_wire_queue_events", 0),
            ("actor_wire_queue_octets", 0),
        ):
            object.__setattr__(
                self,
                name,
                canonical_safe_int(getattr(self, name), field=name, minimum=minimum),
            )
        if (self.admission_active_admission_sequence is None) != (
            self.admission_active_command_kind is None
        ):
            raise CanonicalizationError(
                "admission active sequence and command kind must be present together"
            )
        if (
            self.admission_active_admission_sequence is not None
            or self.admission_active_command_kind is not None
            or waiting_sequences
            or waiting_kinds
            or self.admission_oldest_waiting_age_nanoseconds != 0
            or self.admission_reserved_work_units != 0
        ):
            raise CanonicalizationError(
                "capacity measurement boundary requires a quiescent admission snapshot"
            )
        barrier_sequence = self.admission_terminal_barrier_admission_sequence
        if self.admission_terminal_barrier_committed != (barrier_sequence is not None):
            raise CanonicalizationError(
                "a quiescent terminal barrier sequence must identify a committed barrier"
            )
        if (
            self.admission_last_started_queue_wait_nanoseconds
            > self.admission_maximum_observed_queue_wait_nanoseconds
        ):
            raise CanonicalizationError(
                "last admission queue wait exceeds the observed maximum"
            )
        rejection_components = (
            self.admission_duplicate_kind_rejections
            + self.admission_terminal_barrier_rejections
            + self.admission_capacity_rejections
            + self.admission_closed_rejections
        )
        if self.admission_rejected_commands != rejection_components:
            raise CanonicalizationError(
                "admission rejection total differs from its decomposition"
            )
        completed_admissions = (
            self.admission_released_commands
            + self.admission_timed_out_commands
            + self.admission_cancelled_before_entry_commands
            + self.admission_closed_before_entry_commands
        )
        if self.admission_maximum_observed_admitted_commands > completed_admissions:
            raise CanonicalizationError(
                "maximum admitted commands exceeds quiescent completed admissions"
            )
        if (
            self.admission_released_commands > 0
            and self.admission_maximum_observed_admitted_commands == 0
        ):
            raise CanonicalizationError(
                "released admissions require a non-zero historical admitted maximum"
            )
        if (self.admission_maximum_observed_admitted_commands == 0) != (
            self.admission_maximum_observed_reserved_work_units == 0
        ):
            raise CanonicalizationError(
                "admission maximum count and reserved work must have the same zero state"
            )
        if (self.actor_event_count == 0) != (self.actor_tail_event_id is None):
            raise CanonicalizationError(
                "actor tail identity must be present exactly when events exist"
            )
        if (self.actor_wire_queue_events == 0) != (self.actor_wire_queue_octets == 0):
            raise CanonicalizationError(
                "actor wire queue count and octets must have the same zero state"
            )
        state = canonical_identifier(
            self.runtime_state, field="runtime_state", maximum=64
        )
        if state not in {item.value for item in PhysicalTransportRuntimeStateV4}:
            raise CanonicalizationError("runtime_state is unsupported")
        object.__setattr__(self, "runtime_state", state)


@dataclass(frozen=True, slots=True, kw_only=True)
class _CompletedApplicationMessageV49E:
    """Runtime-private exact message assembled from durable parser events."""

    source_parser_event_ids: tuple[str, ...]
    websocket_opcode: str
    payload: bytes
    received_at: datetime
    received_monotonic_ns: int

    def __post_init__(self) -> None:
        ids = tuple(
            canonical_hash(value, field="source_parser_event_ids")
            for value in self.source_parser_event_ids
        )
        if not ids or len(set(ids)) != len(ids):
            raise CanonicalizationError(
                "completed application message requires unique parser events"
            )
        opcode = canonical_identifier(
            self.websocket_opcode, field="websocket_opcode", maximum=16
        )
        if opcode not in {"TEXT", "BINARY"}:
            raise CanonicalizationError(
                "completed application message must be TEXT or BINARY"
            )
        if type(self.payload) is not bytes:
            raise CanonicalizationError(
                "completed application message requires exact bytes"
            )
        received_at = utc_datetime(self.received_at, field="received_at")
        received_monotonic_ns = canonical_safe_int(
            self.received_monotonic_ns,
            field="received_monotonic_ns",
            minimum=0,
        )
        object.__setattr__(self, "source_parser_event_ids", ids)
        object.__setattr__(self, "websocket_opcode", opcode)
        object.__setattr__(self, "received_at", received_at)
        object.__setattr__(self, "received_monotonic_ns", received_monotonic_ns)


class PhysicalTransportRuntimeV4:
    """One-writer, one-current-session V4.7 transport authority mediator."""

    _TEST_CONSTRUCTION_TOKEN = object()
    _LIVE_LINUX_CONSTRUCTION_TOKEN = object()

    @classmethod
    def for_test(cls, **kwargs: Any) -> PhysicalTransportRuntimeV4:
        """Construct the explicit non-promotion deterministic port profile."""

        journal = kwargs.get("journal")
        clock_source = kwargs.get("clock_source")
        if (
            getattr(journal, "is_live_clock_profile", False) is True
            or getattr(clock_source, "is_live_profile", False) is True
        ):
            raise TypeError(
                "the test runtime cannot downgrade live projection or clock authority"
            )
        return cls(_construction_token=cls._TEST_CONSTRUCTION_TOKEN, **kwargs)

    @staticmethod
    def _validate_live_linux_components(
        *,
        journal: Any,
        writer_lease: Any,
        authority: Any,
    ) -> None:
        """Reject token and structural-typing bypasses of the sealed factory."""

        from .physical_projection_v4 import PhysicalProjectionStoreV4
        from .physical_transport_lease_v4 import PhysicalTransportWriterLeaseV4
        from .physical_transport_linux_v4 import LinuxSocketOwnerV4

        if type(authority) is not LinuxSocketOwnerV4 or not authority.is_live_profile:
            raise TypeError(
                "live runtime construction requires an exact sealed Linux authority"
            )
        if type(journal) is not PhysicalProjectionStoreV4:
            raise TypeError(
                "live runtime construction requires an exact physical projection"
            )
        if type(writer_lease) is not PhysicalTransportWriterLeaseV4:
            raise TypeError(
                "live runtime construction requires an exact physical writer lease"
            )
        owner_snapshot = authority.snapshot()
        expected_clock_identity = (
            authority.governed_clock.policy.manifest_id,
            owner_snapshot.monotonic_clock_domain_id,
        )
        if (
            not journal._is_bound_to_live_linux_authority(authority)  # noqa: SLF001
            or journal.governed_clock_identity != expected_clock_identity
        ):
            raise TypeError(
                "live runtime projection isn't bound to the exact Linux authority"
            )

    @classmethod
    def _from_live_linux_profile(cls, **kwargs: Any) -> PhysicalTransportRuntimeV4:
        """Construct only from a sealed live Linux owner/clock authority."""

        if "wall_clock" in kwargs or "random_bytes" in kwargs:
            raise TypeError(
                "live runtime construction forbids injected clock/entropy seams"
            )
        cls._validate_live_linux_components(
            journal=kwargs.get("journal"),
            writer_lease=kwargs.get("writer_lease"),
            authority=kwargs.get("clock_source"),
        )
        return cls(_construction_token=cls._LIVE_LINUX_CONSTRUCTION_TOKEN, **kwargs)

    def __init__(
        self,
        *,
        journal: PhysicalTransportJournalPortV4,
        writer_lease: PhysicalTransportWriterLeasePortV4,
        clock_source: ClockEvidenceSourceV4,
        signer: Any,
        deployment_admission: OperationalDeploymentAdmissionV4,
        idempotency_prefix: str,
        config: PhysicalTransportRuntimeConfigV4 | None = None,
        wall_clock: Callable[[], datetime] | None = None,
        random_bytes: Callable[[int], bytes] = secrets.token_bytes,
        _construction_token: object | None = None,
    ) -> None:
        if _construction_token not in {
            self._TEST_CONSTRUCTION_TOKEN,
            self._LIVE_LINUX_CONSTRUCTION_TOKEN,
        }:
            raise TypeError(
                "use for_test() or the sealed Linux runtime factory for construction"
            )
        self._is_live_profile = (
            _construction_token is self._LIVE_LINUX_CONSTRUCTION_TOKEN
        )
        if self._is_live_profile:
            if wall_clock is not None or random_bytes is not secrets.token_bytes:
                raise TypeError(
                    "live runtime construction forbids injected clock/entropy seams"
                )
            self._validate_live_linux_components(
                journal=journal,
                writer_lease=writer_lease,
                authority=clock_source,
            )
        elif (
            getattr(journal, "is_live_clock_profile", False) is True
            or getattr(clock_source, "is_live_profile", False) is True
        ):
            raise TypeError(
                "the test runtime cannot downgrade live projection or clock authority"
            )
        self._journal = journal
        self._writer_lease = writer_lease
        self._clock_source = clock_source
        self._signer = signer
        if type(deployment_admission) is not OperationalDeploymentAdmissionV4:
            raise CanonicalizationError(
                "runtime requires an exact OperationalDeploymentAdmissionV4"
            )
        self._deployment_admission = deployment_admission
        self._idempotency_prefix = canonical_identifier(
            idempotency_prefix, field="idempotency_prefix", maximum=96
        )
        if config is not None and type(config) is not PhysicalTransportRuntimeConfigV4:
            raise TypeError("config must be an exact PhysicalTransportRuntimeConfigV4")
        self._config = config or PhysicalTransportRuntimeConfigV4()
        self._wall_clock = wall_clock or (lambda: datetime.now(timezone.utc))
        self._random_bytes = random_bytes
        self._state = PhysicalTransportRuntimeStateV4.COLD
        self._session: TransportSessionAttestationV4 | None = None
        self._intent: OutboundSubscriptionIntentV4 | None = None
        self._socket_owner: TransportSocketOwnerPortV4 | None = None
        self._socket_owner_snapshot: TransportSocketOwnerSnapshotV4 | None = None
        self._socket_owner_binding: TransportSocketOwnerBindingV4 | None = None
        self._socket_lease_id: str | None = None
        self._used_socket_lease_ids: set[str] = set()
        self._used_kernel_socket_identities: set[str] = set()
        self._permit: PhysicalTransportSendPermitV4 | None = None
        self._permit_consumed = False
        self._dispatch_window: PhysicalTransportDispatchWindowV4 | None = None
        self._pending_ack_disposition_id: str | None = None
        self._binding: SubscriptionAckBindingV4 | None = None
        self._fault_cause: str | None = None
        self._last_clock_evidence: ClockEvidenceV4 | None = None
        self._writer_fence_token_sha256: str | None = None
        self._writer_fence_generation: int | None = None
        self._clock_source_manifest_id: str | None = None
        self._deployment_capability: VerifiedDeploymentCapabilityV4 | None = None
        self._deployment_bundle: DeploymentBundleV4 | None = None
        self._control_mediator_created = False
        self._driver_session_transition_active = False
        self._committed_bound_session_v49c: CommittedBoundTransportSessionV4 | None = (
            None
        )
        self._driver_handshake_transition_v49c: Any | None = None
        self._initial_pending_raw_ingress_v49c: Any | None = None
        self._transport_actor_journal_v49c: Any | None = None
        self._transport_session_actor_v49c: Any | None = None
        self._transport_actor_activation_v49c_in_progress = False
        self._transport_orchestration_lock_v49c = asyncio.Lock()
        capacity_policy_v49f = deployment_admission.transport_capacity_policy_v49f
        self._transport_admission_gate_v49f = (
            None
            if capacity_policy_v49f is None
            else BoundedTransportAdmissionGateV49F(capacity_policy_v49f)
        )
        self._retained_ingress_tail_v49d: Any | None = None
        self._parser_cursor_v49d: Any | None = None
        self._fragmented_message_bytes_v49d = b""
        self._fragmented_message_parser_event_ids_v49e: tuple[str, ...] = ()

    @property
    def state(self) -> PhysicalTransportRuntimeStateV4:
        return self._state

    @property
    def is_live_profile(self) -> bool:
        return self._is_live_profile

    @property
    def current_transport_session_id(self) -> str | None:
        return None if self._session is None else self._session.transport_session_id

    @property
    def current_socket_lease_id(self) -> str | None:
        return self._socket_lease_id

    @property
    def current_intent_id(self) -> str | None:
        return (
            None
            if self._intent is None
            else self._intent.outbound_subscription_intent_id
        )

    @property
    def fault_cause(self) -> str | None:
        return self._fault_cause

    def create_control_mediator(self) -> Any:
        """Create the sole control mediator from this exact bound authority.

        The method intentionally has no writer, clock, lease, generation, or
        authority callback arguments.  All of them are derived from the live
        owner and the atomic signed owner binding.  Generic point clocks are
        rejected here even though they remain useful in unit-only runtimes.
        """

        if (
            self._transport_session_actor_v49c is not None
            or self._transport_actor_activation_v49c_in_progress
        ):
            raise PhysicalTransportRuntimeV4StateError(
                "legacy control mediator is fenced after V4.9C actor activation"
            )
        allowed = {
            PhysicalTransportRuntimeStateV4.SESSION_COMMITTED,
            PhysicalTransportRuntimeStateV4.INTENT_COMMITTED,
            PhysicalTransportRuntimeStateV4.AWAITING_ACK,
            PhysicalTransportRuntimeStateV4.ACK_BOUND,
        }
        if self._state not in allowed:
            raise PhysicalTransportRuntimeV4StateError(
                "control mediator requires a live committed bound session"
            )
        if self._control_mediator_created:
            raise PhysicalTransportRuntimeV4StateError(
                "one control mediator was already created for this runtime epoch"
            )
        owner = self._socket_owner
        binding = self._socket_owner_binding
        if owner is None or binding is None or self._clock_source is not owner:
            self._abort_owner_best_effort(owner)
            self._fault_cause = "control authority is not the bound owner/clock object"
            self._state = PhysicalTransportRuntimeStateV4.FAULT_LATCHED
            raise PhysicalTransportRuntimeV4FaultLatched(
                "control authority must be the exact retained owner and governed clock"
            )
        self._assert_lease()
        self._assert_application_fence(context="before control mediator creation")
        self._assert_socket_owner(context="before control mediator creation")
        try:
            evidence = self._sample_clock(
                required_domain_id=binding.monotonic_clock_domain_id,
                strictly_after_monotonic_ns=binding.bound_monotonic_after_ns,
            )
            if (
                evidence.monotonic_before_ns >= evidence.monotonic_after_ns
                or evidence.clock_resolution_ns != binding.clock_resolution_ns
                or evidence.observation_sha256 is None
                or evidence.selectable_source_count is None
                or (
                    self._is_live_profile
                    and (
                        evidence.chronyd_launch_id is None
                        or evidence.chronyd_runtime_observation_sha256 is None
                    )
                )
            ):
                raise PhysicalTransportClockEvidenceV4Error(
                    "control promotion requires a concrete governed clock bracket"
                )
        except Exception as exc:
            self._abort_owner_best_effort(owner)
            self._fault_cause = f"control clock promotion failed: {type(exc).__name__}"
            self._state = PhysicalTransportRuntimeStateV4.FAULT_LATCHED
            raise PhysicalTransportRuntimeV4FaultLatched(
                "control clock promotion failed; shared owner was aborted"
            ) from exc
        from .physical_transport_control_runtime_v4 import (
            PhysicalTransportControlMediatorV4,
        )

        mediator = PhysicalTransportControlMediatorV4.from_bound_transport_authority(
            journal=self._journal,
            authority=owner,
            binding=binding,
            signer=self._signer,
        )
        if self._is_live_profile and not mediator.is_live_profile:
            self._abort_owner_best_effort(owner)
            self._fault_cause = (
                "live control mediator lost its sealed authority profile"
            )
            self._state = PhysicalTransportRuntimeStateV4.FAULT_LATCHED
            raise PhysicalTransportRuntimeV4FaultLatched(
                "live control mediator is not bound to the sealed Linux authority"
            )
        self._control_mediator_created = True
        return mediator

    def _require_state(self, *allowed: PhysicalTransportRuntimeStateV4) -> None:
        if self._state not in allowed:
            expected = ", ".join(item.value for item in allowed)
            raise PhysicalTransportRuntimeV4StateError(
                f"operation requires state {expected}; current state is {self._state.value}"
            )

    def _assert_lease(self) -> None:
        try:
            self._writer_lease.assert_held()
        except Exception as exc:
            self._fault_cause = f"writer lease lost: {type(exc).__name__}"
            self._state = PhysicalTransportRuntimeStateV4.FAULT_LATCHED
            raise PhysicalTransportRuntimeV4FaultLatched(
                "writer lease is not held; transport authority is latched off"
            ) from exc

    def _assert_application_fence(self, *, context: str) -> None:
        """Revalidate the exact projection epoch immediately before authority."""

        if (
            self._writer_fence_token_sha256 is None
            or self._writer_fence_generation is None
        ):
            self._fault_cause = "writer application fence is not bound"
            self._state = PhysicalTransportRuntimeStateV4.FAULT_LATCHED
            raise PhysicalTransportRuntimeV4FaultLatched(
                f"writer application fence disappeared {context}"
            )
        try:
            self._journal.assert_transport_runtime_writer_fence(
                lease_token_sha256=self._writer_fence_token_sha256,
                generation=self._writer_fence_generation,
            )
        except Exception as exc:
            self._fault_cause = f"writer application fence failed: {type(exc).__name__}"
            self._state = PhysicalTransportRuntimeStateV4.FAULT_LATCHED
            raise PhysicalTransportRuntimeV4FaultLatched(
                f"writer application fence changed {context}"
            ) from exc

    @staticmethod
    def _snapshot_owner_candidate(
        owner: TransportSocketOwnerPortV4,
    ) -> TransportSocketOwnerSnapshotV4:
        if not isinstance(owner, TransportSocketOwnerPortV4):
            raise CanonicalizationError(
                "socket_owner must implement the exact V4.7 owner capability port"
            )
        snapshot = owner.snapshot()
        if type(snapshot) is not TransportSocketOwnerSnapshotV4:
            raise CanonicalizationError(
                "socket owner returned an unsupported identity snapshot"
            )
        return snapshot

    @classmethod
    def _revalidate_owner_candidate(
        cls,
        owner: TransportSocketOwnerPortV4,
        expected: TransportSocketOwnerSnapshotV4,
    ) -> None:
        owner.assert_same_owner(expected)
        if cls._snapshot_owner_candidate(owner) != expected:
            raise PhysicalTransportRuntimeV4Error(
                "socket owner identity changed after its capability assertion"
            )

    @staticmethod
    def _abort_owner_best_effort(
        owner: TransportSocketOwnerPortV4 | None,
    ) -> BaseException | None:
        if owner is None:
            return None
        try:
            owner.abort()
        except Exception as exc:
            return exc
        return None

    def _assert_socket_owner(self, *, context: str) -> None:
        owner = self._socket_owner
        snapshot = self._socket_owner_snapshot
        binding = self._socket_owner_binding
        if owner is None or snapshot is None or binding is None:
            self._fault_cause = "socket owner capability is not bound"
            self._state = PhysicalTransportRuntimeStateV4.FAULT_LATCHED
            raise PhysicalTransportRuntimeV4FaultLatched(
                f"socket owner capability disappeared {context}"
            )
        try:
            self._revalidate_owner_candidate(owner, snapshot)
            if any(
                (
                    binding.kernel_boot_id != snapshot.kernel_boot_id,
                    binding.time_namespace_id != snapshot.time_namespace_id,
                    binding.network_namespace_id != snapshot.network_namespace_id,
                    binding.socket_cookie_u64 != snapshot.socket_cookie_u64,
                    binding.kernel_socket_identity != snapshot.kernel_socket_identity,
                    binding.monotonic_clock_domain_id
                    != snapshot.monotonic_clock_domain_id,
                    binding.clock_resolution_ns != snapshot.clock_resolution_ns,
                )
            ):
                raise PhysicalTransportRuntimeV4Error(
                    "retained owner snapshot differs from its signed binding"
                )
        except BaseException as exc:
            abort_failure = self._abort_owner_best_effort(owner)
            suffix = (
                ""
                if abort_failure is None
                else f"; abort failed: {type(abort_failure).__name__}"
            )
            self._fault_cause = (
                f"socket owner changed {context}: {type(exc).__name__}{suffix}"
            )
            self._state = PhysicalTransportRuntimeStateV4.FAULT_LATCHED
            raise PhysicalTransportRuntimeV4FaultLatched(
                f"socket owner changed {context}; transport authority is latched off"
            ) from exc

    def _writer_lease_token_digest(self) -> str:
        token = self._writer_lease.lease_token
        if not isinstance(token, str):
            raise PhysicalTransportRuntimeV4FaultLatched(
                "writer lease capability isn't text"
            )
        try:
            raw = bytes.fromhex(token)
        except ValueError as exc:
            raise PhysicalTransportRuntimeV4FaultLatched(
                "writer lease capability isn't canonical hexadecimal"
            ) from exc
        if len(raw) != 32 or raw.hex() != token:
            raise PhysicalTransportRuntimeV4FaultLatched(
                "writer lease capability must be 256-bit lowercase hexadecimal"
            )
        return hashlib.sha256(raw).hexdigest()

    def _sample_clock(
        self,
        *,
        required_domain_id: str | None = None,
        strictly_after_monotonic_ns: int | None = None,
    ) -> ClockEvidenceV4:
        try:
            evidence = self._clock_source.sample()
        except Exception as exc:
            raise PhysicalTransportClockEvidenceV4Error(
                "clock evidence source failed"
            ) from exc
        if not isinstance(evidence, ClockEvidenceV4):
            raise PhysicalTransportClockEvidenceV4Error(
                "clock evidence source returned an unsupported value"
            )
        now = utc_datetime(self._wall_clock(), field="runtime_wall_clock")
        tolerance = timedelta(milliseconds=evidence.uncertainty_milliseconds)
        maximum_lifetime = timedelta(
            seconds=self._config.maximum_clock_evidence_lifetime_seconds
        )
        if (
            not evidence.synchronized
            or evidence.uncertainty_milliseconds
            > self._config.maximum_clock_uncertainty_milliseconds
            or evidence.valid_until - evidence.sampled_at > maximum_lifetime
            or evidence.sampled_at > now + tolerance
            or evidence.valid_until < now - tolerance
        ):
            raise PhysicalTransportClockEvidenceV4Error(
                "clock evidence is unsynchronized, stale, over-broad, or too uncertain"
            )
        if (
            required_domain_id is not None
            and evidence.monotonic_clock_domain_id
            != canonical_hash(required_domain_id, field="required_domain_id")
        ):
            raise PhysicalTransportClockEvidenceV4Error(
                "monotonic clock domain changed during a live runtime"
            )
        if (
            self._clock_source_manifest_id is not None
            and evidence.clock_source_manifest_id != self._clock_source_manifest_id
        ):
            raise PhysicalTransportClockEvidenceV4Error(
                "clock source manifest changed during one runtime epoch"
            )
        if self._is_live_profile and (
            evidence.chronyd_launch_id is None
            or evidence.chronyd_runtime_observation_sha256 is None
        ):
            raise PhysicalTransportClockEvidenceV4Error(
                "live clock evidence lacks loaded-chronyd provenance"
            )
        if (
            strictly_after_monotonic_ns is not None
            and evidence.monotonic_before_ns <= strictly_after_monotonic_ns
        ):
            raise PhysicalTransportClockEvidenceV4Error(
                "clock evidence bracket does not begin strictly after prior evidence"
            )
        previous = self._last_clock_evidence
        if previous is not None and (
            evidence.chronyd_launch_id != previous.chronyd_launch_id
            or evidence.chronyd_runtime_observation_sha256
            != previous.chronyd_runtime_observation_sha256
        ):
            raise PhysicalTransportClockEvidenceV4Error(
                "loaded chronyd authority changed during one runtime epoch"
            )
        if (
            previous is not None
            and evidence.monotonic_clock_domain_id == previous.monotonic_clock_domain_id
            and evidence.monotonic_before_ns <= previous.monotonic_after_ns
        ):
            raise PhysicalTransportClockEvidenceV4Error(
                "clock evidence brackets overlap or regress within one monotonic domain"
            )
        self._last_clock_evidence = evidence
        return evidence

    def _latch_clock_failure(
        self, exc: BaseException, *, context: str
    ) -> PhysicalTransportRuntimeV4FaultLatched:
        self._fault_cause = f"{context}: {type(exc).__name__}"
        self._state = PhysicalTransportRuntimeStateV4.FAULT_LATCHED
        return PhysicalTransportRuntimeV4FaultLatched(
            f"{context}; transport authority is latched off"
        )

    def _verify_operational_deployment(
        self, evidence: ClockEvidenceV4
    ) -> tuple[VerifiedDeploymentCapabilityV4, DeploymentBundleV4]:
        capability = self._deployment_admission.verify(
            verified_at=evidence.sampled_at,
            signer=self._signer,
        )
        bundle = self._deployment_admission.bundle
        clock_policy = self._deployment_admission.clock_policy
        evidence_lifetime_ms = int(
            (evidence.valid_until - evidence.sampled_at).total_seconds() * 1000
        )
        if (
            evidence.clock_source_manifest_id != capability.clock_source_manifest_id
            or evidence.uncertainty_milliseconds
            > clock_policy.max_uncertainty_milliseconds
            or evidence_lifetime_ms > clock_policy.max_sample_age_milliseconds
            or self._config.maximum_clock_uncertainty_milliseconds
            > clock_policy.max_uncertainty_milliseconds
            or self._config.maximum_clock_evidence_lifetime_seconds * 1000
            > clock_policy.max_sample_age_milliseconds
        ):
            raise PhysicalTransportClockEvidenceV4Error(
                "runtime clock configuration exceeds the signed deployment policy"
            )
        self._journal.assert_current_operational_deployment(
            deployment_bundle_id=capability.deployment_bundle_id,
            deployment_trust_root_id=capability.deployment_trust_root_id,
            deployment_sequence=capability.deployment_sequence,
        )
        return capability, bundle

    def _sample_active_clock(
        self,
        *,
        context: str,
        strictly_after_monotonic_ns: int | None = None,
    ) -> ClockEvidenceV4:
        assert self._session is not None
        try:
            evidence = self._sample_clock(
                required_domain_id=self._session.monotonic_clock_domain_id,
                strictly_after_monotonic_ns=strictly_after_monotonic_ns,
            )
            if (
                self._deployment_capability is None
                or self._deployment_bundle is None
                or evidence.clock_source_manifest_id
                != self._deployment_capability.clock_source_manifest_id
                or evidence.sampled_at < self._deployment_bundle.valid_from
                or evidence.sampled_at >= self._deployment_bundle.valid_until
                or evidence.uncertainty_milliseconds
                > self._deployment_admission.clock_policy.max_uncertainty_milliseconds
            ):
                raise PhysicalTransportClockEvidenceV4Error(
                    "operational deployment is missing, expired, or clock-incompatible"
                )
            return evidence
        except PhysicalTransportClockEvidenceV4Error as exc:
            raise self._latch_clock_failure(exc, context=context) from exc

    def _reconcile_capacity_measurement_startup_orphans_v49f(
        self,
    ) -> tuple[str, ...]:
        """Close the store's frozen Raw-V7 orphan snapshot without retrying I/O.

        Exact production construction already requires ``PhysicalProjectionStoreV4``.
        Legacy protocol doubles cannot contain Raw-V7 tables or capabilities, so
        they retain their historical empty startup result.
        """

        from .physical_projection_v4 import (
            CapacityMeasurementStartupRecoveryCapabilityV49F,
            PhysicalProjectionStoreV4,
        )
        from .physical_transport_capacity_lifecycle_v49f import (
            CapacityMeasurementLifecycleCancellationV49F,
            CapacityMeasurementLifecycleTerminalTriggerV49F,
            CapacityMeasurementLifecycleTerminalWriterV49F,
            CapacityMeasurementOperationPrefixV49F,
            CapacityMeasurementSessionTerminalAuthorityV49F,
        )

        store = self._journal
        if type(store) is not PhysicalProjectionStoreV4:
            return ()
        capability = store._claim_capacity_measurement_startup_recovery_v49f()  # noqa: SLF001
        if capability is None:
            return ()
        if type(capability) is not CapacityMeasurementStartupRecoveryCapabilityV49F:
            raise PhysicalTransportRuntimeV4Error(
                "startup capacity recovery returned an unsupported capability"
            )
        recovered: list[str] = []
        for attempt_id in capability.open_attempt_ids:
            prefix = store.recover_capacity_measurement_operation_terminal_v49f(
                capability,
                attempt_id,
                idempotency_key=(
                    f"{self._idempotency_prefix}-capacity-recovery-{attempt_id}"
                ),
            )
            terminal = getattr(prefix, "terminal", None)
            if (
                type(prefix) is not CapacityMeasurementOperationPrefixV49F
                or prefix.attempt.attempt_id != attempt_id
                or terminal is None
                or terminal.attempt_id != attempt_id
                or terminal.terminal_writer
                is not CapacityMeasurementLifecycleTerminalWriterV49F.STARTUP_RECOVERY
                or terminal.terminal_trigger
                is not CapacityMeasurementLifecycleTerminalTriggerV49F.RECOVERED_ORPHAN
                or terminal.cancellation_classification
                is not CapacityMeasurementLifecycleCancellationV49F.PROCESS_LOSS_UNKNOWN
                or terminal.session_terminal_authority
                is not CapacityMeasurementSessionTerminalAuthorityV49F.UNAVAILABLE_AFTER_ORPHAN
                or terminal.returned_progress_evidence_id is not None
                or terminal.parser_cursor_id_after
                != prefix.attempt.parser_cursor_id_before
                or terminal.runtime_state_after is not None
                or terminal.observer_end_offset_nanoseconds is not None
                or terminal.boottime_end_offset_nanoseconds is not None
                or terminal.loop_time_end_offset_nanoseconds is not None
                or terminal.completed_monotonic_ns is not None
            ):
                raise PhysicalTransportRuntimeV4Error(
                    "startup capacity recovery returned a substituted terminal"
                )
            recovered.append(attempt_id)
        store.complete_capacity_measurement_startup_recovery_v49f(capability)
        if tuple(recovered) != capability.open_attempt_ids:
            raise PhysicalTransportRuntimeV4Error(
                "startup capacity recovery did not preserve receipt order"
            )
        return tuple(recovered)

    def start(self) -> PhysicalTransportRuntimeStartReportV4:
        """Verify the journal and terminate all old sessions before READY."""

        self._require_state(PhysicalTransportRuntimeStateV4.COLD)
        self._state = PhysicalTransportRuntimeStateV4.STARTING
        try:
            self._assert_lease()
            evidence = self._sample_clock()
            self._clock_source_manifest_id = evidence.clock_source_manifest_id
            capability, deployment_bundle = self._verify_operational_deployment(
                evidence
            )
            expected_capacity_policy_id_v49f = (
                capability.transport_capacity_policy_id_v49f
            )
            actual_capacity_policy_id_v49f = (
                None
                if self._transport_admission_gate_v49f is None
                else self._transport_admission_gate_v49f.policy.policy_id
            )
            if expected_capacity_policy_id_v49f != actual_capacity_policy_id_v49f:
                raise PhysicalTransportRuntimeV4Error(
                    "runtime admission gate differs from signed deployment policy"
                )
            self._deployment_capability = capability
            self._deployment_bundle = deployment_bundle
            token_sha256 = self._writer_lease_token_digest()
            # Publish the expected token locally before the claim so startup
            # cleanup can attempt exact release even if a port commits then
            # raises or returns a malformed generation.
            self._writer_fence_token_sha256 = token_sha256
            generation = self._journal.claim_transport_runtime_writer_fence(
                lease_token_sha256=token_sha256,
                holder_id=canonical_identifier(
                    self._writer_lease.holder_id,
                    field="writer_lease_holder_id",
                    maximum=256,
                ),
            )
            generation = canonical_safe_int(
                generation, field="writer_fence_generation", minimum=1
            )
            self._writer_fence_generation = generation
            self._journal.verify()
            recovered_capacity_attempt_ids = (
                self._reconcile_capacity_measurement_startup_orphans_v49f()
            )
            reconcile_evidence = self._sample_clock(
                required_domain_id=evidence.monotonic_clock_domain_id,
                strictly_after_monotonic_ns=evidence.monotonic_ns,
            )
            reconciled = self._journal.reconcile_unterminated_transport_sessions(
                detected_at=reconcile_evidence.sampled_at,
                detected_monotonic_ns=reconcile_evidence.monotonic_ns,
                detected_monotonic_clock_domain_id=(
                    reconcile_evidence.monotonic_clock_domain_id
                ),
                signer=self._signer,
                idempotency_prefix=f"{self._idempotency_prefix}-startup",
            )
            if not isinstance(reconciled, Sequence) or isinstance(
                reconciled, (str, bytes, bytearray)
            ):
                raise PhysicalTransportRuntimeV4Error(
                    "startup reconciliation returned an unsupported value"
                )
            reconciled_ids: list[str] = []
            for item in reconciled:
                if not isinstance(item, TransportSessionTerminationV4) or (
                    item.reason
                    is not TransportSessionTerminationReasonV4.PROCESS_RESTART
                    or item.close_code is not None
                    or item.close_reason_digest is not None
                    or item.detected_at != reconcile_evidence.sampled_at
                    or item.detected_monotonic_ns != reconcile_evidence.monotonic_ns
                    or item.detected_monotonic_clock_domain_id
                    != reconcile_evidence.monotonic_clock_domain_id
                ):
                    raise PhysicalTransportRuntimeV4Error(
                        "startup reconciliation returned an unrelated terminal record"
                    )
                reconciled_ids.append(item.transport_session_id)
            if len(reconciled_ids) != len(set(reconciled_ids)):
                raise PhysicalTransportRuntimeV4Error(
                    "startup reconciliation returned duplicate sessions"
                )
            ready_evidence = self._sample_clock(
                required_domain_id=reconcile_evidence.monotonic_clock_domain_id,
                strictly_after_monotonic_ns=reconcile_evidence.monotonic_ns,
            )
        except Exception as exc:
            self._fault_cause = f"startup failed: {type(exc).__name__}"
            self._state = PhysicalTransportRuntimeStateV4.FAULT_LATCHED
            cleanup_failure: BaseException | None = None
            if self._writer_fence_token_sha256 is not None:
                try:
                    self._journal.release_transport_runtime_writer_fence(
                        lease_token_sha256=self._writer_fence_token_sha256
                    )
                except BaseException as cleanup_exc:
                    cleanup_failure = cleanup_exc
                finally:
                    self._writer_fence_token_sha256 = None
                    self._writer_fence_generation = None
            try:
                self._writer_lease.release()
            except BaseException as cleanup_exc:
                cleanup_failure = cleanup_failure or cleanup_exc
            if cleanup_failure is not None:
                self._fault_cause += (
                    f"; cleanup failed: {type(cleanup_failure).__name__}"
                )
            if isinstance(exc, PhysicalTransportRuntimeV4FaultLatched):
                raise
            raise PhysicalTransportRuntimeV4FaultLatched(
                "operational deployment admission, journal verification, or "
                "orphan reconciliation failed"
            ) from exc
        session_ids = tuple(
            canonical_hash(item, field="transport_session_id")
            for item in reconciled_ids
        )
        self._state = PhysicalTransportRuntimeStateV4.READY
        return PhysicalTransportRuntimeStartReportV4(
            recovered_capacity_measurement_attempt_ids=(recovered_capacity_attempt_ids),
            reconciled_transport_session_ids=session_ids,
            deployment_bundle_id=capability.deployment_bundle_id,
            deployment_sequence=capability.deployment_sequence,
            deployment_trust_root_id=capability.deployment_trust_root_id,
            clock_source_manifest_id=ready_evidence.clock_source_manifest_id,
            monotonic_clock_domain_id=ready_evidence.monotonic_clock_domain_id,
            writer_fence_generation=generation,
        )

    def _create_socket_owner_binding(
        self,
        *,
        session: TransportSessionAttestationV4,
        owner_snapshot: TransportSocketOwnerSnapshotV4,
        evidence: ClockEvidenceV4,
    ) -> tuple[str, TransportSocketOwnerBindingV4]:
        nonce = self._random_bytes(32)
        if not isinstance(nonce, bytes) or len(nonce) != 32:
            raise PhysicalTransportRuntimeV4Error(
                "socket-owner randomness source must return exactly 32 bytes"
            )
        if (
            self._writer_fence_token_sha256 is None
            or self._writer_fence_generation is None
        ):
            raise PhysicalTransportRuntimeV4Error(
                "socket-owner binding requires an active writer fence"
            )
        nonce_sha256 = derive_transport_socket_lease_nonce_sha256(nonce)
        socket_id = derive_transport_socket_lease_id(
            transport_session_id=session.transport_session_id,
            kernel_socket_identity=owner_snapshot.kernel_socket_identity,
            socket_lease_nonce_sha256=nonce_sha256,
            writer_fence_token_sha256=self._writer_fence_token_sha256,
            writer_fence_generation=self._writer_fence_generation,
            socket_identity_profile=owner_snapshot.socket_identity_profile,
        )
        binding = TransportSocketOwnerBindingV4.create_signed(
            signer=self._signer,
            transport_session_id=session.transport_session_id,
            deployment_bundle_id=session.deployment_bundle_id,
            transport_subscription_policy_id=(session.transport_subscription_policy_id),
            physical_scope_manifest_id=session.physical_scope_manifest_id,
            adapter_policy_id=session.adapter_policy_id,
            capture_partition_id=session.capture_partition_id,
            socket_lease_id=socket_id,
            socket_lease_nonce_sha256=nonce_sha256,
            kernel_socket_identity=owner_snapshot.kernel_socket_identity,
            socket_identity_profile=owner_snapshot.socket_identity_profile,
            socket_cookie_u64=owner_snapshot.socket_cookie_u64,
            kernel_boot_id=owner_snapshot.kernel_boot_id,
            time_namespace_id=owner_snapshot.time_namespace_id,
            network_namespace_id=owner_snapshot.network_namespace_id,
            clock_source_manifest_id=session.clock_source_manifest_id,
            monotonic_clock_domain_id=(owner_snapshot.monotonic_clock_domain_id),
            clock_profile=owner_snapshot.clock_profile,
            clock_resolution_ns=owner_snapshot.clock_resolution_ns,
            connection_generation=session.connection_generation,
            writer_fence_token_sha256=self._writer_fence_token_sha256,
            writer_fence_generation=self._writer_fence_generation,
            bound_at=evidence.sampled_at,
            bound_monotonic_before_ns=evidence.monotonic_before_ns,
            bound_monotonic_after_ns=evidence.monotonic_after_ns,
            clock_uncertainty_milliseconds=evidence.uncertainty_milliseconds,
        )
        return socket_id, binding

    async def establish_driver_derived_session_v49b(
        self,
        *,
        physical_scope_manifest_id: str,
        adapter_policy_id: str,
        capture_partition_id: str,
        collector_instance_id: str,
        idempotency_key: str,
    ) -> CommittedBoundTransportSessionV4:
        """Derive and commit the initial session from the retained V4.9 engine.

        The method deliberately accepts no session, owner, socket, handshake
        evidence, clock value, generation, parent, or entropy seam.  The
        bounded V4.9B profile supports the initial generation only; reconnect
        remains a V4.9C gate.
        """

        self._require_state(PhysicalTransportRuntimeStateV4.READY)
        if self._driver_session_transition_active:
            raise PhysicalTransportRuntimeV4StateError(
                "a driver-derived session transition is already active"
            )

        from .physical_transport_linux_v4 import (
            DriverHandshakeTransitionV49B,
            LinuxSocketOwnerV4,
        )

        owner = self._clock_source
        if (
            type(owner) is not LinuxSocketOwnerV4
            or not owner.is_v49b_exact_profile
            or (self._is_live_profile and not owner.is_live_profile)
        ):
            self._abort_owner_best_effort(
                owner if isinstance(owner, TransportSocketOwnerPortV4) else None
            )
            self._fault_cause = (
                "driver-derived session requires the exact retained V4.9B owner"
            )
            self._state = PhysicalTransportRuntimeStateV4.FAULT_LATCHED
            raise PhysicalTransportRuntimeV4FaultLatched(
                "driver-derived session authority is unavailable"
            )

        capability = self._deployment_capability
        deployment_bundle = self._deployment_bundle
        if capability is None or deployment_bundle is None:
            owner.abort()
            self._fault_cause = "verified deployment capability is missing"
            self._state = PhysicalTransportRuntimeStateV4.FAULT_LATCHED
            raise PhysicalTransportRuntimeV4FaultLatched(
                "driver-derived session requires verified deployment authority"
            )
        try:
            required_driver_policy_id = (
                capability.require_tls_websocket_driver_policy_id_v49b()
            )
        except Exception as exc:
            owner.abort()
            self._fault_cause = "verified deployment lacks V4.9B driver policy"
            self._state = PhysicalTransportRuntimeStateV4.FAULT_LATCHED
            raise PhysicalTransportRuntimeV4FaultLatched(
                "driver-derived session requires signed measured-driver policy"
            ) from exc
        try:
            retained_driver_policy_id = owner.driver_policy_id
        except BaseException as exc:
            owner.abort()
            self._fault_cause = "retained driver policy identity is unavailable"
            self._state = PhysicalTransportRuntimeStateV4.FAULT_LATCHED
            if isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)):
                raise
            raise PhysicalTransportRuntimeV4FaultLatched(
                "driver-derived session policy identity could not be revalidated"
            ) from exc
        if retained_driver_policy_id != required_driver_policy_id:
            owner.abort()
            self._fault_cause = "retained driver policy differs from deployment"
            self._state = PhysicalTransportRuntimeStateV4.FAULT_LATCHED
            raise PhysicalTransportRuntimeV4FaultLatched(
                "driver-derived session policy is not deployment-authorized"
            )

        scope_id = canonical_hash(
            physical_scope_manifest_id, field="physical_scope_manifest_id"
        )
        adapter_id = canonical_hash(adapter_policy_id, field="adapter_policy_id")
        partition_id = canonical_hash(
            capture_partition_id, field="capture_partition_id"
        )
        collector_id = canonical_identifier(
            collector_instance_id,
            field="collector_instance_id",
            maximum=256,
        )
        commit_key = canonical_identifier(
            idempotency_key, field="idempotency_key", maximum=256
        )

        self._driver_session_transition_active = True
        try:
            self._assert_lease()
            self._assert_application_fence(context="before driver-derived handshake")
            transition = await owner.establish_v49b_handshake()
            if type(transition) is not DriverHandshakeTransitionV49B:
                raise PhysicalTransportRuntimeV4Error(
                    "exact owner returned an unsupported handshake transition"
                )
            evidence = transition.evidence
            pre_sample = transition.pre_sample
            post_sample = transition.post_sample
            owner_snapshot = transition.owner_snapshot
            if owner_snapshot != owner.snapshot():
                raise PhysicalTransportRuntimeV4Error(
                    "owner changed after its driver handshake"
                )
            self._assert_lease()
            self._assert_application_fence(context="after driver-derived handshake")
            binding_evidence = self._sample_clock(
                required_domain_id=owner_snapshot.monotonic_clock_domain_id,
                strictly_after_monotonic_ns=post_sample.boottime_after_ns,
            )
            uncertainty_ms = transition.clock_uncertainty_milliseconds
            policy = owner.transport_policy
            session = TransportSessionAttestationV4.create_signed(
                signer=self._signer,
                deployment_bundle_id=capability.deployment_bundle_id,
                clock_source_manifest_id=capability.clock_source_manifest_id,
                collector_key_authorization_manifest_id=(
                    capability.collector_key_authorization_manifest_id
                ),
                transport_subscription_policy_id=(
                    policy.transport_subscription_policy_id
                ),
                physical_scope_manifest_id=scope_id,
                adapter_policy_id=adapter_id,
                capture_partition_id=partition_id,
                collector_instance_id=collector_id,
                collector_boot_id=owner_snapshot.kernel_boot_id,
                connection_generation=1,
                session_nonce=evidence.evidence_nonce_sha256,
                parent_transport_session_id=None,
                authoritative_endpoint=policy.authoritative_endpoint,
                tls_server_name=policy.tls_server_name,
                remote_address=evidence.remote_address,
                tls_version=evidence.tls_version,
                tls_cipher=evidence.tls_cipher,
                alpn_protocol=evidence.alpn_protocol,
                websocket_extensions=evidence.websocket_extensions,
                peer_certificate_sha256=evidence.peer_certificate_sha256,
                peer_spki_sha256=evidence.peer_spki_sha256,
                trust_store_manifest_id=evidence.trust_store_manifest_id,
                certificate_verified=evidence.certificate_verified,
                hostname_verified=evidence.hostname_verified,
                websocket_http_status=evidence.websocket_http_status,
                websocket_accept_verified=evidence.websocket_accept_verified,
                handshake_commitment_profile=(
                    V4_TRANSPORT_HANDSHAKE_COMMITMENT_PROFILE
                ),
                handshake_request_sha256=evidence.handshake_request_sha256,
                handshake_response_sha256=evidence.handshake_response_sha256,
                handshake_started_at=pre_sample.wall_after_at,
                handshake_completed_at=post_sample.wall_before_at,
                monotonic_clock_domain_id=(owner_snapshot.monotonic_clock_domain_id),
                handshake_started_monotonic_ns=pre_sample.boottime_after_ns,
                handshake_completed_monotonic_ns=post_sample.boottime_before_ns,
                clock_uncertainty_milliseconds=uncertainty_ms,
                collector_release_hash=capability.collector_release_hash,
                collector_runtime_id=capability.collector_runtime_id,
            )
            owner._assert_driver_derived_session_v49b(session)  # noqa: SLF001
            return self._commit_bound_session_core(
                session,
                socket_owner=owner,
                idempotency_key=commit_key,
                prepared_clock_evidence=binding_evidence,
                driver_transition=transition,
            )
        except BaseException as exc:
            abort_failure = self._abort_owner_best_effort(owner)
            if self._state is not PhysicalTransportRuntimeStateV4.FAULT_LATCHED:
                self._state = PhysicalTransportRuntimeStateV4.FAULT_LATCHED
                self._fault_cause = (
                    f"driver-derived session failed: {type(exc).__name__}"
                )
            if abort_failure is not None and self._fault_cause is not None:
                self._fault_cause += (
                    f"; owner abort failed: {type(abort_failure).__name__}"
                )
            if isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)):
                raise
            if isinstance(exc, PhysicalTransportRuntimeV4FaultLatched):
                raise
            raise PhysicalTransportRuntimeV4FaultLatched(
                "driver-derived session did not establish send authority"
            ) from exc
        finally:
            self._driver_session_transition_active = False

    def commit_session(
        self,
        session: TransportSessionAttestationV4,
        *,
        socket_owner: TransportSocketOwnerPortV4,
        idempotency_key: str,
    ) -> CommittedBoundTransportSessionV4:
        """Atomically commit a session and its retained live socket capability."""

        self._require_state(PhysicalTransportRuntimeStateV4.READY)
        if self._is_live_profile:
            self._abort_owner_best_effort(self._clock_source)
            if socket_owner is not self._clock_source:
                self._abort_owner_best_effort(socket_owner)
            self._fault_cause = (
                "caller-authored live TLS/WebSocket session facts are forbidden"
            )
            self._state = PhysicalTransportRuntimeStateV4.FAULT_LATCHED
            raise PhysicalTransportRuntimeV4FaultLatched(
                "V4.9 must derive live session evidence from the exact retained "
                "TLS/Sans-I/O driver"
            )
        if getattr(socket_owner, "is_live_profile", False) is True:
            self._abort_owner_best_effort(socket_owner)
            self._fault_cause = "a test runtime cannot accept a live socket owner"
            self._state = PhysicalTransportRuntimeStateV4.FAULT_LATCHED
            raise PhysicalTransportRuntimeV4FaultLatched(
                "the non-live session path cannot downgrade live socket authority"
            )
        return self._commit_bound_session_core(
            session,
            socket_owner=socket_owner,
            idempotency_key=idempotency_key,
        )

    def _commit_bound_session_core(
        self,
        session: TransportSessionAttestationV4,
        *,
        socket_owner: TransportSocketOwnerPortV4,
        idempotency_key: str,
        prepared_clock_evidence: ClockEvidenceV4 | None = None,
        driver_transition: Any | None = None,
    ) -> CommittedBoundTransportSessionV4:
        """Shared authorized bound-session transition.

        V4.9B adds a separate driver-derived entry rather than an ``allow_live``
        switch.  Keeping this core private prevents the existing public method
        from becoming a caller-authored live-session bypass.
        """

        self._require_state(PhysicalTransportRuntimeStateV4.READY)
        try:
            self._assert_lease()
        except Exception:
            self._abort_owner_best_effort(socket_owner)
            raise
        if not isinstance(session, TransportSessionAttestationV4):
            self._abort_owner_best_effort(socket_owner)
            self._fault_cause = "unsupported transport session record"
            self._state = PhysicalTransportRuntimeStateV4.FAULT_LATCHED
            raise PhysicalTransportRuntimeV4FaultLatched(
                "session must be TransportSessionAttestationV4"
            )
        capability = self._deployment_capability
        if capability is None:
            self._abort_owner_best_effort(socket_owner)
            self._fault_cause = "verified deployment capability is missing"
            self._state = PhysicalTransportRuntimeStateV4.FAULT_LATCHED
            raise PhysicalTransportRuntimeV4FaultLatched(
                "session cannot be committed without verified deployment authority"
            )
        expected_bindings = capability.transport_session_bindings()
        if any(
            getattr(session, field_name) != expected_value
            for field_name, expected_value in expected_bindings.items()
        ) or (
            session.collector_attestation_key_id
            != capability.collector_attestation_key_id
            or session.collector_attestation_public_key_hex
            != capability.collector_attestation_public_key_hex
        ):
            self._fault_cause = "session differs from verified deployment authority"
            self._state = PhysicalTransportRuntimeStateV4.FAULT_LATCHED
            self._abort_owner_best_effort(socket_owner)
            raise PhysicalTransportRuntimeV4FaultLatched(
                "session manifest or collector-key binding is not deployment-authorized"
            )

        try:
            owner_snapshot = self._snapshot_owner_candidate(socket_owner)
        except Exception as exc:
            self._abort_owner_best_effort(socket_owner)
            self._fault_cause = f"socket owner snapshot failed: {type(exc).__name__}"
            self._state = PhysicalTransportRuntimeStateV4.FAULT_LATCHED
            raise PhysicalTransportRuntimeV4FaultLatched(
                "socket owner snapshot is unavailable; transport authority is latched off"
            ) from exc
        if (
            owner_snapshot.kernel_boot_id != session.collector_boot_id
            or owner_snapshot.monotonic_clock_domain_id
            != session.monotonic_clock_domain_id
        ):
            self._abort_owner_best_effort(socket_owner)
            self._fault_cause = "socket owner boot or clock domain differs from session"
            self._state = PhysicalTransportRuntimeStateV4.FAULT_LATCHED
            raise PhysicalTransportRuntimeV4FaultLatched(
                "socket owner is outside the signed session clock domain"
            )
        if owner_snapshot.kernel_socket_identity in self._used_kernel_socket_identities:
            self._abort_owner_best_effort(socket_owner)
            raise PhysicalTransportRuntimeV4StateError(
                "kernel socket identity was already consumed by this runtime epoch"
            )
        try:
            self._assert_application_fence(context="before bound session commit")
            if prepared_clock_evidence is None:
                evidence = self._sample_clock(
                    required_domain_id=session.monotonic_clock_domain_id,
                    strictly_after_monotonic_ns=(
                        session.handshake_completed_monotonic_ns
                    ),
                )
            else:
                if (
                    type(prepared_clock_evidence) is not ClockEvidenceV4
                    or self._last_clock_evidence is not prepared_clock_evidence
                    or prepared_clock_evidence.monotonic_clock_domain_id
                    != session.monotonic_clock_domain_id
                    or prepared_clock_evidence.monotonic_ns
                    <= session.handshake_completed_monotonic_ns
                ):
                    raise PhysicalTransportClockEvidenceV4Error(
                        "prepared driver-session clock evidence is not the exact "
                        "latest causal runtime sample"
                    )
                evidence = prepared_clock_evidence
        except PhysicalTransportClockEvidenceV4Error as exc:
            self._abort_owner_best_effort(socket_owner)
            raise self._latch_clock_failure(
                exc, context="session clock validation failed"
            ) from exc
        except PhysicalTransportRuntimeV4FaultLatched:
            self._abort_owner_best_effort(socket_owner)
            raise
        tolerance = timedelta(milliseconds=evidence.uncertainty_milliseconds)
        deployment_bundle = self._deployment_bundle
        if (
            deployment_bundle is None
            or evidence.sampled_at < deployment_bundle.valid_from
            or evidence.sampled_at >= deployment_bundle.valid_until
            or evidence.clock_source_manifest_id != session.clock_source_manifest_id
            or evidence.sampled_at + tolerance < session.handshake_completed_at
            or session.clock_uncertainty_milliseconds
            < evidence.uncertainty_milliseconds
            or session.clock_uncertainty_milliseconds
            > self._config.maximum_clock_uncertainty_milliseconds
            or session.clock_uncertainty_milliseconds
            > self._deployment_admission.clock_policy.max_uncertainty_milliseconds
            or (
                self._is_live_profile
                and (
                    evidence.chronyd_launch_id is None
                    or evidence.chronyd_launch_id != owner_snapshot.chronyd_launch_id
                    or evidence.chronyd_runtime_observation_sha256
                    != owner_snapshot.chronyd_runtime_observation_sha256
                )
            )
        ):
            error = PhysicalTransportClockEvidenceV4Error(
                "session clock source, wall time, or uncertainty violates runtime authority"
            )
            self._abort_owner_best_effort(socket_owner)
            raise self._latch_clock_failure(
                error, context="session clock validation failed"
            )

        bound_pending_ingress_v49c: Any | None = None
        try:
            socket_id, owner_binding = self._create_socket_owner_binding(
                session=session,
                owner_snapshot=owner_snapshot,
                evidence=evidence,
            )
            if socket_id in self._used_socket_lease_ids:
                raise PhysicalTransportRuntimeV4StateError(
                    "socket lease identity was already consumed by this runtime epoch"
                )
            self._revalidate_owner_candidate(socket_owner, owner_snapshot)
            self._assert_lease()
            self._assert_application_fence(context="at bound session commit")
            commit_key = canonical_identifier(
                idempotency_key, field="idempotency_key", maximum=256
            )
            if driver_transition is None:
                committed = self._journal.append_transport_session_attestation(
                    session,
                    socket_owner_binding=owner_binding,
                    idempotency_key=commit_key,
                )
            else:
                from .physical_transport_linux_v4 import (
                    DriverHandshakeTransitionV49B,
                    LinuxSocketOwnerV4,
                )

                if (
                    type(socket_owner) is not LinuxSocketOwnerV4
                    or type(driver_transition) is not DriverHandshakeTransitionV49B
                ):
                    raise PhysicalTransportRuntimeV4Error(
                        "driver-derived commit lost its exact owner or transition"
                    )
                socket_owner._assert_driver_derived_session_v49b(  # noqa: SLF001
                    session
                )
                if self._is_live_profile:
                    append_driver_session = getattr(
                        self._journal,
                        "_append_driver_derived_transport_session_attestation_v49b",
                        None,
                    )
                    if not callable(append_driver_session):
                        raise PhysicalTransportRuntimeV4Error(
                            "live journal lacks the exact driver-derived append core"
                        )
                    committed = append_driver_session(
                        session,
                        socket_owner_binding=owner_binding,
                        authority=socket_owner,
                        idempotency_key=commit_key,
                    )
                else:
                    committed = self._journal.append_transport_session_attestation(
                        session,
                        socket_owner_binding=owner_binding,
                        idempotency_key=commit_key,
                    )
            if (
                type(committed) is not CommittedBoundTransportSessionV4
                or committed.session != session
                or committed.binding != owner_binding
            ):
                raise PhysicalTransportRuntimeV4Error(
                    "journal returned a different bound transport session"
                )
            # The transaction can complete while the driver loses ownership.
            # Revalidate before the durable evidence becomes live authority.
            self._revalidate_owner_candidate(socket_owner, owner_snapshot)
            self._assert_lease()
            self._assert_application_fence(context="after bound session commit")
            self._sample_clock(
                required_domain_id=session.monotonic_clock_domain_id,
                strictly_after_monotonic_ns=evidence.monotonic_ns,
            )
            if driver_transition is not None:
                bound_pending_ingress_v49c = socket_owner.bind_committed_v49b_handshake(
                    driver_transition,
                    session,
                )
                self._revalidate_owner_candidate(socket_owner, owner_snapshot)
        except Exception as exc:
            abort_failure = self._abort_owner_best_effort(socket_owner)
            self._fault_cause = f"session commit failed: {type(exc).__name__}"
            if abort_failure is not None:
                self._fault_cause += (
                    f"; socket abort failed: {type(abort_failure).__name__}"
                )
            self._state = PhysicalTransportRuntimeStateV4.FAULT_LATCHED
            raise PhysicalTransportRuntimeV4FaultLatched(
                "bound session commit or post-commit revalidation failed; no send authority exists"
            ) from exc

        self._session = committed.session
        self._socket_owner = socket_owner
        self._socket_owner_snapshot = owner_snapshot
        self._socket_owner_binding = committed.binding
        self._socket_lease_id = socket_id
        self._committed_bound_session_v49c = committed
        self._driver_handshake_transition_v49c = driver_transition
        self._initial_pending_raw_ingress_v49c = bound_pending_ingress_v49c
        self._used_socket_lease_ids.add(socket_id)
        self._used_kernel_socket_identities.add(owner_snapshot.kernel_socket_identity)
        self._state = PhysicalTransportRuntimeStateV4.SESSION_COMMITTED
        return committed

    async def activate_causal_transport_actor_v49c(self) -> None:
        """Bind the V4.9C journal/controller to the exact V4.9B owner.

        Activation is deliberately one-way and never returns the actor, owner,
        permit, or staged driver artifacts.  It remains separate from
        subscription authorization so retained post-upgrade plaintext and its
        automatic protocol obligations cannot be bypassed.  Once activation
        begins, every legacy subscription/control writer path is fenced so it
        cannot create a second stream order.
        """

        self._require_state(PhysicalTransportRuntimeStateV4.SESSION_COMMITTED)
        if (
            self._transport_session_actor_v49c is not None
            or self._transport_actor_activation_v49c_in_progress
        ):
            raise PhysicalTransportRuntimeV4StateError(
                "one V4.9C transport actor is already active"
            )
        if self._control_mediator_created or self._intent is not None:
            raise PhysicalTransportRuntimeV4StateError(
                "V4.9C actor cannot activate after a legacy writer path"
            )
        committed = self._committed_bound_session_v49c
        transition = self._driver_handshake_transition_v49c
        owner = self._socket_owner

        from .physical_projection_v4 import PhysicalProjectionStoreV4
        from .physical_transport_actor_journal_v49c import (
            PhysicalTransportActorProjectionJournalV49C,
        )
        from .physical_transport_linux_v4 import (
            DriverHandshakeTransitionV49B,
            LinuxSocketOwnerV4,
        )
        from .physical_transport_session_actor_v49c import (
            PhysicalTransportSessionActorV49C,
            TransportActorAuthorityV49C,
        )

        self._transport_actor_activation_v49c_in_progress = True
        retained_tail_v49d: Any | None = None
        parser_cursor_v49d: Any | None = None
        try:
            if committed is None or transition is None or owner is None:
                raise PhysicalTransportRuntimeV4StateError(
                    "V4.9C activation requires a driver-derived bound session"
                )
            if (
                type(self._journal) is not PhysicalProjectionStoreV4
                or type(owner) is not LinuxSocketOwnerV4
                or type(transition) is not DriverHandshakeTransitionV49B
            ):
                raise PhysicalTransportRuntimeV4StateError(
                    "V4.9C activation requires exact projection/owner/transition types"
                )
            self._assert_lease()
            self._assert_socket_owner(context="before V4.9C actor activation")
            self._assert_application_fence(context="before V4.9C actor activation")
            authority = TransportActorAuthorityV49C.from_committed_bound_session(
                committed_session=committed,
                handshake_transition=transition,
            )
            if self._is_live_profile:
                journal = PhysicalTransportActorProjectionJournalV49C.from_live_linux_authority(
                    store=self._journal,
                    authority=authority,
                    socket_owner=owner,
                )
            else:
                journal = PhysicalTransportActorProjectionJournalV49C.for_test(
                    store=self._journal,
                    authority=authority,
                    socket_owner=owner,
                )
            actor = await PhysicalTransportSessionActorV49C.restore_bound(
                journal=journal,
                committed_session=committed,
                handshake_transition=transition,
                socket_owner=owner,
                authority=authority,
            )
            if actor.authority is not authority:
                raise PhysicalTransportRuntimeV4Error(
                    "V4.9C actor did not retain the exact bound authority"
                )
            if actor.is_fault_latched:
                raise PhysicalTransportRuntimeV4Error(
                    "V4.9C restored terminal actor cannot retain socket authority"
                )
            if actor.events:
                raise PhysicalTransportRuntimeV4Error(
                    "V4.9D cannot attach a live Sans-I/O parser to a restored "
                    "non-empty actor prefix"
                )
            from .physical_transport_actor_v49c import (
                RetainedIngressTailV49C,
                WebSocketParserCursorV49C,
                WebSocketParserStateV49C,
            )

            retained_tail_v49d = RetainedIngressTailV49C()
            parser_cursor_v49d = WebSocketParserCursorV49C(
                cursor_sequence=0,
                next_stream_octet=0,
                websocket_state=WebSocketParserStateV49C.OPEN,
            )
            self._assert_lease()
            self._assert_socket_owner(context="after V4.9C actor activation")
        except BaseException as exc:
            self._abort_owner_best_effort(owner)
            self._fault_cause = f"V4.9C actor activation failed: {type(exc).__name__}"
            self._state = PhysicalTransportRuntimeStateV4.FAULT_LATCHED
            if isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)):
                raise
            raise PhysicalTransportRuntimeV4FaultLatched(
                "V4.9C actor activation failed and transport authority was fenced"
            ) from exc
        finally:
            self._transport_actor_activation_v49c_in_progress = False
        self._transport_actor_journal_v49c = journal
        self._transport_session_actor_v49c = actor
        self._retained_ingress_tail_v49d = retained_tail_v49d
        self._parser_cursor_v49d = parser_cursor_v49d
        self._fragmented_message_bytes_v49d = b""
        self._fragmented_message_parser_event_ids_v49e = ()
        return None

    @property
    def causal_transport_actor_v49c_active(self) -> bool:
        return self._transport_session_actor_v49c is not None

    def _reject_legacy_terminal_bypass_v49e(self, *, operation: str) -> None:
        """Keep synchronous terminal APIs outside actor-owned causal order."""

        if (
            self._transport_session_actor_v49c is not None
            or self._transport_actor_activation_v49c_in_progress
        ) and self._state not in {
            PhysicalTransportRuntimeStateV4.FENCED,
            PhysicalTransportRuntimeStateV4.FAULT_LATCHED,
            PhysicalTransportRuntimeStateV4.CLOSED,
        }:
            raise PhysicalTransportRuntimeV4StateError(
                f"legacy {operation} is fenced while the V4.9C causal transport "
                "actor owns terminal order; use the actor-ordered asynchronous "
                "shutdown path"
            )

    @property
    def has_initial_pending_raw_ingress_v49c(self) -> bool:
        """Whether coalesced post-upgrade plaintext remains runtime-retained."""

        return self._initial_pending_raw_ingress_v49c is not None

    def _validate_committed_intent(self, intent: OutboundSubscriptionIntentV4) -> None:
        assert self._session is not None
        session = self._session
        if not isinstance(intent, OutboundSubscriptionIntentV4) or any(
            (
                intent.transport_subscription_policy_id
                != session.transport_subscription_policy_id,
                intent.transport_session_id != session.transport_session_id,
                intent.physical_scope_manifest_id != session.physical_scope_manifest_id,
                intent.adapter_policy_id != session.adapter_policy_id,
                intent.capture_partition_id != session.capture_partition_id,
                intent.connection_generation != session.connection_generation,
                intent.authorized_at < session.handshake_completed_at,
            )
        ):
            raise PhysicalTransportRuntimeV4Error(
                "journal returned an intent outside the committed session authority"
            )

    def authorize_send_permit(
        self, *, idempotency_key: str
    ) -> PhysicalTransportSendPermitV4:
        """Commit the exact intent first, then issue its sole send capability."""

        if (
            self._transport_session_actor_v49c is not None
            or self._transport_actor_activation_v49c_in_progress
        ):
            raise PhysicalTransportRuntimeV4StateError(
                "legacy subscription permit is fenced after V4.9C actor activation"
            )
        return self._authorize_send_permit_core(idempotency_key=idempotency_key)

    def _authorize_send_permit_core(
        self, *, idempotency_key: str
    ) -> PhysicalTransportSendPermitV4:
        """Internal exact authorization shared by legacy and actor-owned paths."""

        self._require_state(PhysicalTransportRuntimeStateV4.SESSION_COMMITTED)
        self._assert_lease()
        self._assert_socket_owner(context="before intent authorization")
        assert self._session is not None
        assert self._socket_lease_id is not None
        before_commit = self._sample_active_clock(
            context="intent authorization clock validation failed",
            strictly_after_monotonic_ns=(
                self._session.handshake_completed_monotonic_ns
            ),
        )
        try:
            intent = self._journal.authorize_outbound_subscription_intent(
                self._session.transport_session_id,
                idempotency_key=canonical_identifier(
                    idempotency_key, field="idempotency_key", maximum=256
                ),
            )
        except Exception as exc:
            try:
                detected = self._sample_active_clock(
                    context="failed intent commit clock validation failed",
                    strictly_after_monotonic_ns=before_commit.monotonic_ns,
                )
            except PhysicalTransportRuntimeV4FaultLatched:
                raise PhysicalTransportRuntimeV4FaultLatched(
                    "intent commit failed and fresh terminal clocks are unavailable"
                ) from exc
            self._terminate_or_latch(
                reason=TransportSessionTerminationReasonV4.STORAGE_FAILURE,
                evidence=detected,
                cause=exc,
            )
            if self._state is PhysicalTransportRuntimeStateV4.FAULT_LATCHED:
                raise PhysicalTransportRuntimeV4FaultLatched(
                    "intent commit and terminal persistence failed"
                ) from exc
            raise PhysicalTransportRuntimeV4Error(
                "intent commit failed; no permit was issued and the session was fenced"
            ) from exc
        self._state = PhysicalTransportRuntimeStateV4.INTENT_COMMITTED
        if isinstance(intent, OutboundSubscriptionIntentV4):
            self._intent = intent
        issued: ClockEvidenceV4 | None = None
        try:
            self._assert_lease()
            self._assert_socket_owner(context="after durable intent authorization")
            self._assert_application_fence(context="after durable intent authorization")
            self._validate_committed_intent(intent)
            issued = self._sample_active_clock(
                context="post-intent authorization clock validation failed",
                strictly_after_monotonic_ns=before_commit.monotonic_ns,
            )
            latest_possible_at = issued.sampled_at + timedelta(
                milliseconds=issued.uncertainty_milliseconds
            )
            remaining = intent.send_not_after - latest_possible_at
            remaining_ns = (
                remaining.days * 86_400 + remaining.seconds
            ) * 1_000_000_000 + remaining.microseconds * 1_000
            if remaining_ns <= 0:
                self._terminate_or_latch(
                    reason=TransportSessionTerminationReasonV4.TRANSPORT_ERROR,
                    evidence=issued,
                    cause=PhysicalTransportSendPermitV4Error(
                        "intent send deadline elapsed during durable authorization"
                    ),
                )
                raise PhysicalTransportSendPermitV4Error(
                    "intent expired before a send permit could be issued"
                )
            lease_token_sha256 = self._writer_lease_token_digest()
            random_material = self._random_bytes(32)
            if not isinstance(random_material, bytes) or len(random_material) != 32:
                raise PhysicalTransportRuntimeV4Error(
                    "permit randomness source must return exactly 32 bytes"
                )
            permit = PhysicalTransportSendPermitV4(
                permit_id=random_material.hex(),
                writer_lease_token_sha256=lease_token_sha256,
                socket_lease_id=self._socket_lease_id,
                transport_session_id=self._session.transport_session_id,
                outbound_subscription_intent_id=(
                    intent.outbound_subscription_intent_id
                ),
                connection_generation=intent.connection_generation,
                command_sha256=intent.command_sha256,
                command_bytes=intent.command_bytes,
                issued_at=issued.sampled_at,
                issued_monotonic_ns=issued.monotonic_ns,
                send_not_after=intent.send_not_after,
                send_not_after_monotonic_ns=(issued.monotonic_after_ns + remaining_ns),
            )
        except PhysicalTransportRuntimeV4FaultLatched:
            raise
        except Exception as exc:
            if self._state is not PhysicalTransportRuntimeStateV4.FENCED:
                detected = self._sample_active_clock(
                    context="failed permit issuance clock validation failed",
                    strictly_after_monotonic_ns=(
                        before_commit.monotonic_ns
                        if issued is None
                        else issued.monotonic_ns
                    ),
                )
                self._terminate_or_latch(
                    reason=TransportSessionTerminationReasonV4.TRANSPORT_ERROR,
                    evidence=detected,
                    cause=exc,
                )
            raise PhysicalTransportRuntimeV4Error(
                "durable intent couldn't produce a permit; session was fenced"
            ) from exc
        self._permit = permit
        self._permit_consumed = False
        return permit

    def _validate_permit(
        self,
        permit: PhysicalTransportSendPermitV4,
        *,
        socket_lease_id: str,
    ) -> None:
        if not isinstance(permit, PhysicalTransportSendPermitV4):
            raise PhysicalTransportSendPermitV4Error("unsupported send permit")
        socket_id = canonical_hash(socket_lease_id, field="socket_lease_id")
        if socket_id != self._socket_lease_id:
            raise PhysicalTransportStaleCallbackV4(
                "send callback belongs to a stale socket lease"
            )
        if self._permit is None or permit != self._permit:
            raise PhysicalTransportSendPermitV4Error(
                "send permit wasn't issued by the current runtime state"
            )
        if self._permit_consumed:
            raise PhysicalTransportSendPermitV4Error(
                "send permit has already been consumed"
            )
        expected_lease_hash = self._writer_lease_token_digest()
        if permit.writer_lease_token_sha256 != expected_lease_hash:
            raise PhysicalTransportSendPermitV4Error(
                "send permit belongs to a stale writer lease"
            )

    async def dispatch_text(
        self,
        permit: PhysicalTransportSendPermitV4,
        *,
        socket_lease_id: str,
        sender: ExactTextFrameSenderV4,
    ) -> PhysicalTransportDispatchWindowV4:
        """Consume a permit once and attempt its exact Text-frame payload.

        ``send_exact_text_frame`` must complete only after the owned transport
        has accepted the complete TEXT-frame bytes for writing. Once invoked,
        any exception or cancellation is unknown delivery and the intent is
        never replayed. Passing a generic WebSocket ``send(bytes)`` adapter is
        outside this port because many clients select the Binary opcode.
        """

        if (
            self._transport_session_actor_v49c is not None
            or self._transport_actor_activation_v49c_in_progress
        ):
            raise PhysicalTransportRuntimeV4StateError(
                "legacy TEXT dispatch is fenced after V4.9C actor activation"
            )

        self._require_state(PhysicalTransportRuntimeStateV4.INTENT_COMMITTED)
        self._assert_lease()
        self._validate_permit(permit, socket_lease_id=socket_lease_id)
        self._assert_socket_owner(context="before dispatch")
        if sender is not self._socket_owner:
            assert self._session is not None
            self._permit_consumed = True
            rejected = self._sample_active_clock(
                context="unbound sender rejection clock validation failed",
                strictly_after_monotonic_ns=permit.issued_monotonic_ns,
            )
            self._terminate_or_latch(
                reason=TransportSessionTerminationReasonV4.TRANSPORT_ERROR,
                evidence=rejected,
                cause=PhysicalTransportRuntimeV4Error(
                    "sender is not the retained socket-owner capability"
                ),
            )
            raise PhysicalTransportDispatchUnknownV4(
                "dispatch sender was not the retained socket-owner capability"
            )
        assert self._session is not None
        assert self._intent is not None
        self._assert_application_fence(context="before dispatch")
        preflight = self._sample_active_clock(
            context="pre-dispatch clock validation failed",
            strictly_after_monotonic_ns=permit.issued_monotonic_ns,
        )
        started: ClockEvidenceV4 | None = None
        driver_boundary_entered = False

        def before_driver() -> None:
            """Run under the exact owner's shared lock, with no intervening await."""

            nonlocal driver_boundary_entered, started
            if driver_boundary_entered or started is not None:
                raise PhysicalTransportRuntimeV4Error(
                    "TEXT driver-boundary guard was invoked more than once"
                )
            self._assert_lease()
            self._assert_socket_owner(context="inside exact writer lock")
            self._assert_application_fence(context="inside exact writer lock")
            candidate = self._sample_active_clock(
                context="locked pre-dispatch clock validation failed",
                strictly_after_monotonic_ns=preflight.monotonic_after_ns,
            )
            if (
                candidate.sampled_at
                + timedelta(milliseconds=candidate.uncertainty_milliseconds)
                >= permit.send_not_after
                or candidate.monotonic_after_ns >= permit.send_not_after_monotonic_ns
            ):
                self._terminate_or_latch(
                    reason=TransportSessionTerminationReasonV4.TRANSPORT_ERROR,
                    evidence=candidate,
                    cause=PhysicalTransportSendPermitV4Error("send permit expired"),
                )
                raise PhysicalTransportSendPermitV4Error(
                    "send permit expired inside the shared writer lock"
                )
            started = candidate
            driver_boundary_entered = True

        self._permit_consumed = True
        self._state = PhysicalTransportRuntimeStateV4.DISPATCHING
        try:
            await sender.send_exact_text_frame(
                permit.command_bytes,
                before_driver=before_driver,
            )
            if not driver_boundary_entered or started is None:
                raise PhysicalTransportDispatchUnknownV4(
                    "retained owner returned without invoking its locked guard"
                )
        except BaseException as exc:
            if (
                isinstance(exc, PhysicalTransportSendPermitV4Error)
                and not driver_boundary_entered
            ):
                raise
            if self._state is PhysicalTransportRuntimeStateV4.FAULT_LATCHED:
                raise
            try:
                self._assert_lease()
                self._assert_socket_owner(context="after failed or cancelled dispatch")
                self._assert_application_fence(
                    context="after failed or cancelled dispatch"
                )
                detected = self._sample_active_clock(
                    context="failed-dispatch clock validation failed",
                    strictly_after_monotonic_ns=(
                        preflight.monotonic_after_ns
                        if started is None
                        else started.monotonic_after_ns
                    ),
                )
                self._terminate_or_latch(
                    reason=TransportSessionTerminationReasonV4.TRANSPORT_ERROR,
                    evidence=detected,
                    cause=exc,
                )
            except PhysicalTransportRuntimeV4Error:
                if isinstance(exc, asyncio.CancelledError):
                    raise
                raise
            if isinstance(exc, asyncio.CancelledError):
                raise
            raise PhysicalTransportDispatchUnknownV4(
                "dispatch failed after the exact intent may have begun"
            ) from exc
        assert started is not None
        if self._state is not PhysicalTransportRuntimeStateV4.DISPATCHING:
            raise PhysicalTransportDispatchUnknownV4(
                "dispatch completed after another callback fenced the session"
            )
        self._assert_lease()
        self._assert_socket_owner(context="after dispatch completion")
        self._assert_application_fence(context="after dispatch completion")
        try:
            completed = self._sample_active_clock(
                context="post-dispatch clock validation failed",
                strictly_after_monotonic_ns=started.monotonic_ns,
            )
            window = PhysicalTransportDispatchWindowV4(
                transport_session_id=self._session.transport_session_id,
                outbound_subscription_intent_id=(
                    self._intent.outbound_subscription_intent_id
                ),
                socket_lease_id=permit.socket_lease_id,
                monotonic_clock_domain_id=(self._session.monotonic_clock_domain_id),
                dispatch_started_at=started.sampled_at,
                dispatch_completed_at=completed.sampled_at,
                dispatch_started_monotonic_ns=started.monotonic_ns,
                dispatch_completed_monotonic_ns=completed.monotonic_ns,
            )
        except Exception as exc:
            self._fault_cause = f"post-dispatch clock failure: {type(exc).__name__}"
            self._state = PhysicalTransportRuntimeStateV4.FAULT_LATCHED
            raise PhysicalTransportRuntimeV4FaultLatched(
                "dispatch may have completed but causal clocks are unavailable"
            ) from exc
        self._dispatch_window = window
        self._state = PhysicalTransportRuntimeStateV4.AWAITING_ACK
        if self._pending_ack_disposition_id is not None:
            self._bind_ack(self._pending_ack_disposition_id)
        return window

    def _v49d_actor_clock_floor(self, actor: Any) -> int:
        """Return the newest causal clock edge known to runtime or actor."""

        assert self._session is not None
        floor = self._session.handshake_completed_monotonic_ns
        events = actor.events
        if events:
            floor = max(floor, events[-1].recorded_monotonic_ns)
        if self._last_clock_evidence is not None:
            floor = max(floor, self._last_clock_evidence.monotonic_after_ns)
        return floor

    def _build_raw_ingress_v49d(
        self,
        *,
        actor: Any,
        pending: Any,
        received_at: datetime,
        received_monotonic_ns: int,
    ) -> Any:
        """Bind one driver-retained plaintext batch to actor authority."""

        from .physical_transport_control_v4 import RawIngressCommitV4

        authority = actor.authority
        encoded = tuple(
            base64.b64encode(chunk).decode("ascii") for chunk in pending.chunks
        )
        hashes = tuple(hashlib.sha256(chunk).hexdigest() for chunk in pending.chunks)
        return RawIngressCommitV4(
            transport_subscription_policy_id=(
                authority.transport_subscription_policy_id
            ),
            transport_session_id=authority.transport_session_id,
            physical_scope_manifest_id=authority.physical_scope_manifest_id,
            adapter_policy_id=authority.adapter_policy_id,
            capture_partition_id=authority.capture_partition_id,
            socket_lease_id=authority.socket_lease_id,
            connection_generation=authority.connection_generation,
            deployment_bundle_id=authority.deployment_bundle_id,
            writer_fence_token_sha256=authority.writer_fence_token_sha256,
            writer_fence_generation=authority.writer_fence_generation,
            ingress_sequence=pending.ingress_sequence,
            raw_ingress_chunks_base64=encoded,
            raw_ingress_chunks_sha256=hashes,
            raw_ingress_batch_sha256=sha256_digest(
                {
                    "domain": ("RiskYieldMMExactOrderedDecryptedIngressChunksV4_5"),
                    "ordered_chunks_base64": list(encoded),
                }
            ),
            received_at=received_at,
            monotonic_clock_domain_id=authority.monotonic_clock_domain_id,
            received_monotonic_ns=received_monotonic_ns,
        )

    @staticmethod
    def _last_contributing_raw_receipt_v49e(
        *, actor: Any, source_slices: Sequence[Any]
    ) -> tuple[datetime, int]:
        """Resolve message receipt from the final canonical RAW source slice.

        Parser processing can lag socket receipt arbitrarily.  The economic and
        ACK-deadline authority is therefore the receipt clock committed on the
        RAW batch containing the final contributing message octet, never a
        later parser/event-store clock.
        """

        from .physical_transport_actor_v49c import (
            RawIngressCommittedPayloadV49C,
            RawSourceSliceV49C,
            TransportActorEventKindV49C,
        )

        slices = tuple(source_slices)
        if not slices or any(type(value) is not RawSourceSliceV49C for value in slices):
            raise PhysicalTransportRuntimeV4Error(
                "V4.9E completed message lacks canonical RAW source slices"
            )
        source = slices[-1]
        matches = tuple(
            event
            for event in actor.events
            if event.event_kind is TransportActorEventKindV49C.RAW_INGRESS_COMMITTED
            and type(event.payload) is RawIngressCommittedPayloadV49C
            and event.payload.raw_ingress_commit_id == source.raw_ingress_commit_id
        )
        if len(matches) != 1:
            raise PhysicalTransportRuntimeV4Error(
                "V4.9E final RAW source does not resolve exactly once"
            )
        raw = matches[0].payload
        if (
            source.projection_receipt_sequence != raw.receipt.global_sequence
            or source.projection_receipt_hash != raw.receipt.receipt_hash
            or source.stream_start_octet
            != raw.stream_start_octet + source.raw_local_start_octet
            or source.stream_end_octet
            != raw.stream_start_octet + source.raw_local_end_octet
            or source.stream_start_octet < raw.stream_start_octet
            or source.stream_end_octet > raw.stream_end_octet
        ):
            raise PhysicalTransportRuntimeV4Error(
                "V4.9E final RAW source differs from its durable receipt"
            )
        return raw.received_at, raw.received_monotonic_ns

    def _advance_parser_cursor_v49d(
        self, *, unit: Any, parsed: Any
    ) -> tuple[Any, bytes, tuple[Any, bytes] | None]:
        """Derive the next durable cursor from one exact parser result."""

        from .physical_transport_actor_v49c import (
            DelineatedServerFrameV49C,
            WebSocketOpcodeV49C,
            WebSocketParserCursorV49C,
            WebSocketParserStateV49C,
        )

        before = self._parser_cursor_v49d
        if type(before) is not WebSocketParserCursorV49C:
            raise PhysicalTransportRuntimeV4StateError(
                "V4.9D parser cursor was not initialized by actor activation"
            )
        source_end = unit.source_slices[-1].stream_end_octet
        if parsed.parser_exception_class is not None:
            return (
                WebSocketParserCursorV49C(
                    cursor_sequence=before.cursor_sequence + 1,
                    next_stream_octet=source_end,
                    websocket_state=WebSocketParserStateV49C.FAILED,
                ),
                b"",
                None,
            )
        if type(unit) is not DelineatedServerFrameV49C:
            raise PhysicalTransportRuntimeV4Error(
                "structural delineation error produced no parser exception"
            )

        frame = unit.metadata
        fragment_opcode = before.fragmented_message_opcode
        fragment_bytes = self._fragmented_message_bytes_v49d
        completed_message: tuple[Any, bytes] | None = None
        if fragment_opcode is None and fragment_bytes:
            raise PhysicalTransportRuntimeV4Error(
                "fragment bytes exist without a fragmented parser cursor"
            )
        state = before.websocket_state
        if frame.opcode is WebSocketOpcodeV49C.CLOSE:
            state = WebSocketParserStateV49C.CLOSING
            fragment_opcode = None
            fragment_bytes = b""
        elif frame.opcode in {
            WebSocketOpcodeV49C.PING,
            WebSocketOpcodeV49C.PONG,
        }:
            pass
        elif frame.opcode in {
            WebSocketOpcodeV49C.TEXT,
            WebSocketOpcodeV49C.BINARY,
        }:
            if fragment_opcode is not None:
                raise PhysicalTransportRuntimeV4Error(
                    "parser accepted a new data frame inside a fragmented message"
                )
            if frame.fin:
                completed_message = (frame.opcode, unit.payload)
                fragment_opcode = None
                fragment_bytes = b""
            else:
                fragment_opcode = frame.opcode
                fragment_bytes = unit.payload
        elif frame.opcode is WebSocketOpcodeV49C.CONTINUATION:
            if fragment_opcode is None:
                raise PhysicalTransportRuntimeV4Error(
                    "parser accepted a continuation without a fragmented message"
                )
            fragment_bytes += unit.payload
            if frame.fin:
                completed_message = (fragment_opcode, fragment_bytes)
                fragment_opcode = None
                fragment_bytes = b""
        else:  # pragma: no cover - exhaustive enum guard
            raise PhysicalTransportRuntimeV4Error(
                "parser returned an unsupported WebSocket opcode"
            )

        cursor = WebSocketParserCursorV49C(
            cursor_sequence=before.cursor_sequence + 1,
            next_stream_octet=source_end,
            websocket_state=state,
            fragmented_message_opcode=fragment_opcode,
            fragmented_message_octets=len(fragment_bytes),
            fragmented_message_sha256=(
                None
                if fragment_opcode is None
                else hashlib.sha256(fragment_bytes).hexdigest()
            ),
        )
        return cursor, fragment_bytes, completed_message

    async def _commit_completed_application_message_v49e_locked(
        self,
        *,
        actor: Any,
        message: _CompletedApplicationMessageV49E,
        parser_event: Any,
        admission_grant_v49f: TransportAdmissionGrantV49F | None,
        admission_kind_v49f: TransportCommandKindV49F,
    ) -> None:
        """Commit classifier output and an exact ACK without a callback seam."""

        self._assert_actor_admission_v49f(
            admission_grant_v49f,
            expected_kind=admission_kind_v49f,
        )

        from .physical_projection_v4 import ActorProviderMessageCommitResultV49E
        from .physical_transport_actor_v49c import (
            ParserTransitionPayloadV49C,
            TransportActorEventKindV49C,
        )
        from .physical_transport_terminal_v49c import (
            TerminalTransitionKindV49C,
            TerminalTransitionPayloadV49C,
        )

        session = self._session
        if type(message) is not _CompletedApplicationMessageV49E or (
            type(parser_event.payload) is not ParserTransitionPayloadV49C
        ):
            raise PhysicalTransportRuntimeV4Error(
                "V4.9E application commit lacks exact parser-derived input"
            )
        if type(session) is not TransportSessionAttestationV4:
            raise PhysicalTransportRuntimeV4StateError(
                "V4.9E application commit requires one active session"
            )
        if (
            message.source_parser_event_ids[-1] != parser_event.transport_actor_event_id
            or message.received_at > parser_event.recorded_at
            or message.received_monotonic_ns > parser_event.recorded_monotonic_ns
        ):
            raise PhysicalTransportRuntimeV4Error(
                "V4.9E application receipt or lineage overtakes parser authority"
            )
        classified_clock = self._sample_active_clock(
            context="V4.9E provider-classification clock validation failed",
            strictly_after_monotonic_ns=parser_event.recorded_monotonic_ns,
        )
        first_actor_ns = classified_clock.monotonic_after_ns - 1
        if (
            first_actor_ns < classified_clock.monotonic_before_ns
            or first_actor_ns <= parser_event.recorded_monotonic_ns
        ):
            raise PhysicalTransportRuntimeV4Error(
                "V4.9E governed clock bracket cannot order atomic message/ACK edges"
            )
        result = await actor.commit_completed_application_message_v49e(
            source_parser_event_ids=message.source_parser_event_ids,
            websocket_opcode=message.websocket_opcode,
            raw_payload=message.payload,
            collector_received_at=message.received_at,
            collector_received_monotonic_ns=message.received_monotonic_ns,
            classified_monotonic_ns=first_actor_ns,
            signer=self._signer,
        )
        if type(result) is not ActorProviderMessageCommitResultV49E:
            raise PhysicalTransportRuntimeV4Error(
                "V4.9E actor returned an unsupported provider-message commit"
            )
        provider_failure_event = result.provider_failure_event
        if provider_failure_event is not None:
            termination = result.termination
            failure_payload = provider_failure_event.payload
            if (
                self._state is not PhysicalTransportRuntimeStateV4.AWAITING_ACK
                or result.ack_binding is not None
                or result.ack_event is not None
                or not isinstance(termination, TransportSessionTerminationV4)
                or provider_failure_event.event_kind
                is not TransportActorEventKindV49C.TERMINAL_TRANSITION
                or type(failure_payload) is not TerminalTransitionPayloadV49C
                or failure_payload.kind is not TerminalTransitionKindV49C.FATAL
                or failure_payload.cause_code != "SUBSCRIPTION_ACK_INTEGRITY_FAILURE"
                or not actor.terminal_state.is_terminal
                or termination.transport_subscription_policy_id
                != session.transport_subscription_policy_id
                or termination.transport_session_id != session.transport_session_id
                or termination.physical_scope_manifest_id
                != session.physical_scope_manifest_id
                or termination.capture_partition_id != session.capture_partition_id
                or termination.connection_generation != session.connection_generation
                or termination.reason
                is not TransportSessionTerminationReasonV4.TRANSPORT_ERROR
                or termination.close_code is not None
                or termination.close_reason_digest is not None
                or termination.detected_at != provider_failure_event.recorded_at
                or termination.detected_monotonic_ns
                != provider_failure_event.recorded_monotonic_ns
                or termination.detected_monotonic_clock_domain_id
                != session.monotonic_clock_domain_id
                or termination.collector_attestation_key_id
                != session.collector_attestation_key_id
                or termination.collector_attestation_public_key_hex
                != session.collector_attestation_public_key_hex
            ):
                raise PhysicalTransportRuntimeV4Error(
                    "V4.9E provider integrity failure changed its exact terminal pair"
                )
            abort_failure = self._abort_owner_best_effort(self._socket_owner)
            self._pending_ack_disposition_id = None
            self._fault_cause = "SUBSCRIPTION_ACK_INTEGRITY_FAILURE"
            self._state = PhysicalTransportRuntimeStateV4.FENCED
            if abort_failure is not None:
                self._fault_cause = (
                    "V4.9E owner abort failed after durable provider integrity "
                    f"failure: {type(abort_failure).__name__}"
                )
                self._state = PhysicalTransportRuntimeStateV4.FAULT_LATCHED
                raise PhysicalTransportRuntimeV4FaultLatched(
                    "durable provider integrity failure could not close socket authority"
                ) from abort_failure
            raise PhysicalTransportProviderIntegrityFailureV49E(
                "pending subscription received a non-bindable subscribe response; "
                "classification and terminal evidence are durable"
            )
        if result.termination is not None:
            raise PhysicalTransportRuntimeV4Error(
                "V4.9E provider result carries termination without its failure event"
            )
        binding = result.ack_binding
        if binding is None:
            return
        if self._state is not PhysicalTransportRuntimeStateV4.AWAITING_ACK:
            raise PhysicalTransportAckBindingV4Error(
                "actor-derived ACK arrived outside the awaiting-ACK state"
            )
        self._validate_ack_binding(
            binding,
            disposition_id=result.classification.disposition.message_disposition_id,
        )
        self._binding = binding
        self._pending_ack_disposition_id = None
        self._state = PhysicalTransportRuntimeStateV4.ACK_BOUND

    async def _dispatch_automatic_protocol_output_v49d_locked(
        self,
        *,
        actor: Any,
        owner: Any,
        parser_event: Any,
        admission_grant_v49f: TransportAdmissionGrantV49F | None,
        admission_kind_v49f: TransportCommandKindV49F,
    ) -> str:
        """Resolve one oldest automatic Pong/Close through the actor FIFO."""

        self._assert_actor_admission_v49f(
            admission_grant_v49f,
            expected_kind=admission_kind_v49f,
        )

        from .physical_transport_actor_v49c import (
            V49C_MAX_TLS_CIPHERTEXT_CHUNKS,
            KernelSendAttemptPayloadV49C,
            OutboundDispatchCompletedPayloadV49C,
            OutboundWireOriginV49C,
            OutboundWirePreparedPayloadV49C,
            ParserTransitionPayloadV49C,
            TlsCiphertextPreparedPayloadV49C,
            TransportActorEventKindV49C,
            WebSocketOpcodeV49C,
        )
        from .physical_transport_tls_v49 import (
            PreparedTlsCiphertextV49C,
            PreparedWebSocketWireV49C,
        )

        parser_payload = parser_event.payload
        if (
            type(parser_payload) is not ParserTransitionPayloadV49C
            or not parser_payload.ordered_protocol_output_chunks_base64
        ):
            raise PhysicalTransportRuntimeV4Error(
                "automatic dispatch lacks one exact parser output"
            )
        chunks = tuple(
            base64.b64decode(value, validate=True)
            for value in parser_payload.ordered_protocol_output_chunks_base64
        )
        policy_seconds = owner.transport_policy.send_deadline_seconds
        send_not_after = parser_payload.processed_at + timedelta(seconds=policy_seconds)
        send_not_after_ns = (
            parser_payload.processed_monotonic_ns + policy_seconds * 10**9
        )

        wire = await owner.prepare_pending_protocol_output_wire_v49c(chunks)
        if (
            type(wire) is not PreparedWebSocketWireV49C
            or wire.ordered_wire_chunks != chunks
            or wire.ordered_wire_chunks_sha256
            != parser_payload.ordered_protocol_output_chunks_sha256
            or wire.wire_batch_sha256 != parser_payload.protocol_output_batch_sha256
            or wire.wire_octets != sum(map(len, chunks))
        ):
            raise PhysicalTransportRuntimeV4Error(
                "owner automatic wire differs from durable parser output"
            )
        opcode = {
            0x8: WebSocketOpcodeV49C.CLOSE,
            0xA: WebSocketOpcodeV49C.PONG,
        }.get(wire.logical_opcode)
        if opcode is None:
            raise PhysicalTransportRuntimeV4Error(
                "owner automatic wire is not one Close or Pong"
            )
        prior_actor_floor = self._v49d_actor_clock_floor(actor)
        prepared_clock = self._sample_active_clock(
            context="V4.9D automatic wire clock validation failed",
            strictly_after_monotonic_ns=prior_actor_floor,
        )
        prepared_ns = prepared_clock.monotonic_after_ns - 1
        if (
            prepared_ns < prepared_clock.monotonic_before_ns
            or prepared_ns <= prior_actor_floor
            or prepared_clock.wall_after_at >= send_not_after
            or prepared_clock.monotonic_after_ns >= send_not_after_ns
        ):
            raise PhysicalTransportSendPermitV4Error(
                "automatic protocol-output deadline expired during wire preparation"
            )
        operation_id = sha256_digest(
            {
                "domain": "RiskYieldMMAutomaticProtocolOperationV4_9D",
                "source_parser_event_id": parser_event.transport_actor_event_id,
            }
        )
        wire_payload = OutboundWirePreparedPayloadV49C(
            outbound_operation_id=operation_id,
            wire_origin=OutboundWireOriginV49C.AUTOMATIC_PROTOCOL,
            source_parser_event_id=parser_event.transport_actor_event_id,
            logical_opcode=opcode,
            logical_payload_sha256=wire.logical_payload_sha256,
            logical_payload_octets=wire.logical_payload_octets,
            ordered_wire_chunks_base64=tuple(
                base64.b64encode(chunk).decode("ascii")
                for chunk in wire.ordered_wire_chunks
            ),
            ordered_wire_chunks_sha256=wire.ordered_wire_chunks_sha256,
            wire_batch_sha256=wire.wire_batch_sha256,
            wire_octets=wire.wire_octets,
            prepared_at=prepared_clock.wall_after_at,
            prepared_monotonic_ns=prepared_ns,
            send_not_after=send_not_after,
            send_not_after_monotonic_ns=send_not_after_ns,
        )
        wire_event, permit_event = await actor.prepare_automatic_wire_and_permit_v49d(
            wire_payload,
            permit_consumed_at=prepared_clock.wall_after_at,
            permit_consumed_monotonic_ns=prepared_ns + 1,
        )

        ciphertext = await owner.prepare_tls_ciphertext_v49c(wire)
        if (
            type(ciphertext) is not PreparedTlsCiphertextV49C
            or ciphertext.prepared_wire is not wire
            or ciphertext.plaintext_batch_sha256 != wire.wire_batch_sha256
            or ciphertext.plaintext_octets != wire.wire_octets
        ):
            raise PhysicalTransportRuntimeV4Error(
                "owner TLS artifact differs from automatic wire"
            )
        tls_clock = self._sample_active_clock(
            context="V4.9D automatic TLS clock validation failed",
            strictly_after_monotonic_ns=self._v49d_actor_clock_floor(actor),
        )
        if (
            tls_clock.wall_after_at >= send_not_after
            or tls_clock.monotonic_after_ns >= send_not_after_ns
        ):
            raise PhysicalTransportSendPermitV4Error(
                "automatic protocol-output deadline expired during TLS preparation"
            )
        await actor.prepare_tls_ciphertext(
            TlsCiphertextPreparedPayloadV49C(
                outbound_wire_prepared_event_id=(wire_event.transport_actor_event_id),
                write_permit_consumed_event_id=(permit_event.transport_actor_event_id),
                plaintext_batch_sha256=ciphertext.plaintext_batch_sha256,
                plaintext_octets=ciphertext.plaintext_octets,
                ordered_ciphertext_chunks_base64=tuple(
                    base64.b64encode(chunk).decode("ascii")
                    for chunk in ciphertext.ordered_ciphertext_chunks
                ),
                ordered_ciphertext_chunks_sha256=(
                    ciphertext.ordered_ciphertext_chunks_sha256
                ),
                ciphertext_batch_sha256=ciphertext.ciphertext_batch_sha256,
                ciphertext_octets=ciphertext.ciphertext_octets,
                prepared_at=tls_clock.wall_after_at,
                prepared_monotonic_ns=tls_clock.monotonic_after_ns,
            )
        )

        submitted = 0
        positive_results = 0
        while submitted < ciphertext.ciphertext_octets:
            if positive_results >= V49C_MAX_TLS_CIPHERTEXT_CHUNKS:
                raise PhysicalTransportRuntimeV4Error(
                    "automatic positive-send result bound was exhausted"
                )

            async def exact_owner_send(
                exact_slice: bytes,
                *,
                deadline_ns: int | None = None,
            ) -> int:
                exact_deadline_ns = (
                    send_not_after_ns if deadline_ns is None else deadline_ns
                )
                if exact_deadline_ns != send_not_after_ns:
                    raise PhysicalTransportRuntimeV4Error(
                        "actor changed the automatic protocol-output deadline"
                    )
                return await owner.send_prepared_tls_ciphertext_once_v49c(
                    exact_slice,
                    prepared=ciphertext,
                    deadline_ns=exact_deadline_ns,
                )

            outcome = await actor.send_oldest_ciphertext(
                send_effect=exact_owner_send,
                terminal_signer=(
                    self._signer if opcode is WebSocketOpcodeV49C.CLOSE else None
                ),
            )
            if type(outcome.attempt_event.payload) is not KernelSendAttemptPayloadV49C:
                raise PhysicalTransportRuntimeV4Error(
                    "actor returned an unsupported automatic kernel attempt"
                )
            submitted += outcome.accepted_octets
            positive_results += 1

        completed = await actor.complete_oldest_dispatch_from_chain()
        completed_payload = completed.payload
        if (
            completed.event_kind
            is not TransportActorEventKindV49C.OUTBOUND_DISPATCH_COMPLETED
            or type(completed_payload) is not OutboundDispatchCompletedPayloadV49C
            or completed_payload.outbound_wire_prepared_event_id
            != wire_event.transport_actor_event_id
            or completed_payload.submitted_ciphertext_octets
            != ciphertext.ciphertext_octets
        ):
            raise PhysicalTransportRuntimeV4Error(
                "actor returned an unsupported automatic completion"
            )
        return completed.transport_actor_event_id

    @asynccontextmanager
    async def _admit_actor_command_v49f(
        self,
        kind: TransportCommandKindV49F,
    ) -> AsyncIterator[TransportAdmissionGrantV49F | None]:
        """Bound public actor work before the existing execution mutex.

        A signed V4.9F policy activates the explicit ticket gate.  Older
        deterministic profiles retain their V4.9E lock behavior but are not
        promotion evidence for bounded admission.
        """

        gate = self._transport_admission_gate_v49f
        if gate is None:
            async with self._transport_orchestration_lock_v49c:
                yield None
            return
        async with gate.admit(kind) as grant:
            async with self._transport_orchestration_lock_v49c:
                yield grant

    def _assert_actor_admission_v49f(
        self,
        grant: TransportAdmissionGrantV49F | None,
        *,
        expected_kind: TransportCommandKindV49F,
    ) -> None:
        gate = self._transport_admission_gate_v49f
        if gate is None:
            if grant is not None:
                raise PhysicalTransportRuntimeV4StateError(
                    "unsigned runtime cannot accept a V4.9F admission grant"
                )
            return
        if grant is None:
            raise PhysicalTransportRuntimeV4StateError(
                "effect-capable helper cannot bypass signed V4.9F admission"
            )
        gate.assert_active_grant(grant, expected_kind=expected_kind)

    def transport_admission_snapshot_v49f(
        self,
    ) -> TransportAdmissionSnapshotV49F | None:
        """Return immutable local A1 diagnostics when signed policy enables it."""

        gate = self._transport_admission_gate_v49f
        return None if gate is None else gate.snapshot()

    def _manifest_authority_inputs_from_quiescent_v49f(
        self,
        admission: TransportAdmissionSnapshotV49F,
    ) -> tuple[
        PhysicalTransportManifestAuthoritySnapshotV49F,
        PhysicalProjectionSqliteEnvironmentObservationV49F,
    ]:
        """Recapture runtime and SQLite truth while orchestration is owned."""

        from .physical_projection_v4 import (
            PhysicalProjectionSqliteEnvironmentObservationV49F,
        )
        from .physical_transport_actor_journal_v49c import (
            PhysicalTransportActorProjectionJournalV49C,
        )
        from .physical_transport_linux_v4 import (
            LinuxSocketOwnerV4,
            LinuxTransportManifestAuthorityObservationV49F,
        )
        from .physical_transport_session_actor_v49c import (
            PhysicalTransportSessionActorV49C,
        )

        if admission.active_and_waiting_commands != 0:
            raise PhysicalTransportRuntimeV4StateError(
                "manifest authority requires a quiescent A1 admission gate"
            )
        self._require_state(
            PhysicalTransportRuntimeStateV4.SESSION_COMMITTED,
            PhysicalTransportRuntimeStateV4.INTENT_COMMITTED,
            PhysicalTransportRuntimeStateV4.AWAITING_ACK,
            PhysicalTransportRuntimeStateV4.ACK_BOUND,
        )
        self._assert_lease()
        self._assert_application_fence(context="before manifest authority capture")
        self._assert_socket_owner(context="before manifest authority capture")

        capability = self._deployment_capability
        bundle = self._deployment_bundle
        session = self._session
        owner = self._socket_owner
        owner_snapshot = self._socket_owner_snapshot
        actor = self._transport_session_actor_v49c
        journal = self._transport_actor_journal_v49c
        if (
            type(capability) is not VerifiedDeploymentCapabilityV4
            or type(bundle) is not DeploymentBundleV4
            or type(session) is not TransportSessionAttestationV4
            or type(owner) is not LinuxSocketOwnerV4
            or type(owner_snapshot) is not TransportSocketOwnerSnapshotV4
            or type(actor) is not PhysicalTransportSessionActorV49C
            or type(journal) is not PhysicalTransportActorProjectionJournalV49C
            or journal.authority is not actor.authority
        ):
            raise PhysicalTransportRuntimeV4StateError(
                "manifest authority requires one exact committed actor session"
            )
        self._journal.assert_current_operational_deployment(
            deployment_bundle_id=capability.deployment_bundle_id,
            deployment_trust_root_id=capability.deployment_trust_root_id,
            deployment_sequence=capability.deployment_sequence,
        )
        if (
            capability.deployment_bundle_id != bundle.deployment_bundle_id
            or capability.deployment_trust_root_id != bundle.deployment_trust_root_id
            or capability.deployment_sequence != bundle.deployment_sequence
        ):
            raise PhysicalTransportRuntimeV4StateError(
                "retained deployment capability differs from its signed bundle"
            )

        releases = tuple(
            child
            for child in self._deployment_admission.children
            if type(child) is CollectorReleaseManifestV4
        )
        environments = tuple(
            child
            for child in self._deployment_admission.children
            if type(child) is RuntimeEnvironmentManifestV4
        )
        if len(releases) != 1 or len(environments) != 1:
            raise PhysicalTransportRuntimeV4StateError(
                "manifest authority lacks one exact release/runtime child pair"
            )
        release = releases[0]
        runtime_environment = environments[0]
        owner_observation = owner.authoritative_manifest_observation_v49f()
        if (
            type(owner_observation)
            is not LinuxTransportManifestAuthorityObservationV49F
        ):
            raise PhysicalTransportRuntimeV4StateError(
                "Linux owner returned an unsupported manifest observation"
            )
        clock_evidence = self._sample_active_clock(
            context="manifest authority governed capture"
        )
        capacity_policy_id = capability.transport_capacity_policy_id_v49f
        driver_policy_id = capability.tls_websocket_driver_policy_id
        if capacity_policy_id is None or driver_policy_id is None:
            raise PhysicalTransportRuntimeV4StateError(
                "manifest authority requires signed driver and A1 capacity policies"
            )
        if (
            release.manifest_id != capability.collector_release_manifest_id
            or release.manifest_id != bundle.collector_release_manifest_id
            or runtime_environment.manifest_id
            != capability.runtime_environment_manifest_id
            or runtime_environment.manifest_id != bundle.runtime_environment_manifest_id
            or owner_observation.driver_policy_id != driver_policy_id
            or owner_observation.transport_session_id != session.transport_session_id
            or owner_observation.driver_evidence_nonce_sha256 != session.session_nonce
            or owner_observation.kernel_socket_identity
            != owner_snapshot.kernel_socket_identity
            or owner_observation.kernel_boot_id != session.collector_boot_id
            or owner_observation.monotonic_clock_domain_id
            != session.monotonic_clock_domain_id
            or owner_observation.clock_source_manifest_id
            != session.clock_source_manifest_id
            or session.collector_release_hash != release.manifest_id
            or session.collector_runtime_id != runtime_environment.manifest_id
            or session.collector_key_authorization_manifest_id
            != capability.collector_key_authorization_manifest_id
            or session.collector_attestation_key_id
            != capability.collector_attestation_key_id
            or admission.policy_id != capacity_policy_id
            or clock_evidence.clock_source_manifest_id
            != owner_observation.clock_source_manifest_id
            or clock_evidence.monotonic_clock_domain_id
            != owner_observation.monotonic_clock_domain_id
            or clock_evidence.chronyd_launch_id != owner_observation.chronyd_launch_id
            or clock_evidence.chronyd_runtime_observation_sha256
            != owner_observation.chronyd_runtime_observation_sha256
        ):
            raise PhysicalTransportRuntimeV4StateError(
                "manifest authority identities are not one exact causal closure"
            )

        snapshot = PhysicalTransportManifestAuthoritySnapshotV49F(
            deployment_bundle_id=capability.deployment_bundle_id,
            deployment_trust_root_id=capability.deployment_trust_root_id,
            deployment_sequence=capability.deployment_sequence,
            environment_id=capability.environment_id,
            collector_release_manifest_id=release.manifest_id,
            runtime_environment_manifest_id=runtime_environment.manifest_id,
            collector_key_authorization_manifest_id=(
                capability.collector_key_authorization_manifest_id
            ),
            collector_attestation_key_id=capability.collector_attestation_key_id,
            tls_websocket_driver_policy_id=driver_policy_id,
            retained_driver_runtime_observation_sha256=(
                owner_observation.driver_runtime_observation_sha256
            ),
            transport_session_id=session.transport_session_id,
            driver_evidence_nonce_sha256=(
                owner_observation.driver_evidence_nonce_sha256
            ),
            kernel_socket_identity=owner_observation.kernel_socket_identity,
            kernel_boot_id=owner_observation.kernel_boot_id,
            time_namespace_id=owner_observation.time_namespace_id,
            network_namespace_id=owner_observation.network_namespace_id,
            monotonic_clock_domain_id=owner_observation.monotonic_clock_domain_id,
            clock_source_manifest_id=owner_observation.clock_source_manifest_id,
            chronyd_launch_id=owner_observation.chronyd_launch_id,
            chronyd_runtime_observation_sha256=(
                owner_observation.chronyd_runtime_observation_sha256
            ),
            transport_capacity_policy_id=capacity_policy_id,
            transport_runtime_schema_version=(
                PHYSICAL_TRANSPORT_RUNTIME_V4_SCHEMA_VERSION
            ),
            authority_profile=("LIVE_LINUX" if self._is_live_profile else "EXACT_TEST"),
            captured_at_utc=clock_evidence.sampled_at,
            captured_monotonic_ns=clock_evidence.monotonic_ns,
            release_name=release.release_name,
            release_version=release.release_version,
            release_source_tree_sha256=release.source_tree_sha256,
            release_build_artifact_sha256=release.build_artifact_sha256,
            release_entrypoint=release.entrypoint,
        )
        sqlite_observation = journal.authoritative_sqlite_environment_observation_v49f()
        if (
            type(sqlite_observation)
            is not PhysicalProjectionSqliteEnvironmentObservationV49F
        ):
            raise PhysicalTransportRuntimeV4StateError(
                "actor journal returned an unsupported SQLite observation"
            )
        return snapshot, sqlite_observation

    def _capacity_measurement_v7_baselines_from_quiescent_v49f(
        self,
        admission: TransportAdmissionSnapshotV49F,
    ) -> tuple[Any, Any]:
        """Derive signed V7 projection/actor records at one quiescent boundary."""

        from .physical_projection_v4 import CapacityMeasurementAttemptAuthorityV49F
        from .physical_transport_actor_journal_v49c import (
            PhysicalTransportActorProjectionJournalV49C,
        )
        from .physical_transport_actor_v49c import WebSocketParserCursorV49C
        from .physical_transport_capacity_manifest_authority_v49f import (
            A2M_REQUIRED_PROJECTION_SCHEMA_VERSION_V49F_V7,
            A2M_REQUIRED_PROJECTION_VALIDATION_VERSION_V49F_V7,
            CapacityMeasurementActorBaselineV49FV7,
            CapacityMeasurementProjectionAuthorityV49FV7,
        )
        from .physical_transport_linux_v4 import LinuxSocketOwnerV4
        from .physical_transport_owner_v4 import TransportSocketOwnerSnapshotV4
        from .physical_transport_session_actor_v49c import (
            PhysicalTransportSessionActorV49C,
        )
        from .physical_transport_v4 import TransportSessionAttestationV4

        if admission.active_and_waiting_commands != 0:
            raise PhysicalTransportRuntimeV4StateError(
                "Raw-V7 baseline requires a quiescent A1 admission gate"
            )
        self._require_state(
            PhysicalTransportRuntimeStateV4.SESSION_COMMITTED,
            PhysicalTransportRuntimeStateV4.INTENT_COMMITTED,
            PhysicalTransportRuntimeStateV4.AWAITING_ACK,
            PhysicalTransportRuntimeStateV4.ACK_BOUND,
        )
        self._assert_lease()
        self._assert_application_fence(context="before Raw-V7 baseline capture")
        self._assert_socket_owner(context="before Raw-V7 baseline capture")

        session = self._session
        owner = self._socket_owner
        owner_snapshot = self._socket_owner_snapshot
        actor = self._transport_session_actor_v49c
        journal = self._transport_actor_journal_v49c
        cursor = self._parser_cursor_v49d
        if (
            type(session) is not TransportSessionAttestationV4
            or type(owner) is not LinuxSocketOwnerV4
            or type(owner_snapshot) is not TransportSocketOwnerSnapshotV4
            or type(actor) is not PhysicalTransportSessionActorV49C
            or type(journal) is not PhysicalTransportActorProjectionJournalV49C
            or type(cursor) is not WebSocketParserCursorV49C
            or journal.authority is not actor.authority
        ):
            raise PhysicalTransportRuntimeV4StateError(
                "Raw-V7 baseline requires one exact committed actor session"
            )
        coordinates, store_authority, projected_cursor = (
            journal.capacity_measurement_campaign_baseline_v49f(
                transport_session_id=session.transport_session_id
            )
        )
        if type(store_authority) is not CapacityMeasurementAttemptAuthorityV49F:
            raise PhysicalTransportRuntimeV4StateError(
                "Raw-V7 baseline returned an unsupported projection authority"
            )
        raw_sequence, raw_tail, actor_count, actor_tail = coordinates
        actor_authority = actor.authority
        if (
            projected_cursor != cursor
            or actor_count != actor.event_count_v49f
            or actor_tail != actor.tail_event_id_v49f
            or actor_authority.transport_session_id != session.transport_session_id
            or actor_authority.deployment_bundle_id != session.deployment_bundle_id
            or actor_authority.transport_subscription_policy_id
            != session.transport_subscription_policy_id
            or actor_authority.physical_scope_manifest_id
            != session.physical_scope_manifest_id
            or actor_authority.adapter_policy_id != session.adapter_policy_id
            or actor_authority.capture_partition_id != session.capture_partition_id
            or actor_authority.writer_fence_token_sha256
            != store_authority.writer_fence_token_sha256
            or actor_authority.writer_fence_generation
            != store_authority.writer_fence_generation
            or actor_authority.writer_fence_token_sha256
            != self._writer_fence_token_sha256
            or actor_authority.writer_fence_generation != self._writer_fence_generation
            or store_authority.projection_schema_version
            != A2M_REQUIRED_PROJECTION_SCHEMA_VERSION_V49F_V7
            or store_authority.projection_validation_version
            != A2M_REQUIRED_PROJECTION_VALIDATION_VERSION_V49F_V7
        ):
            raise PhysicalTransportRuntimeV4StateError(
                "Raw-V7 projection/actor/parser authority changed during capture"
            )
        projection = CapacityMeasurementProjectionAuthorityV49FV7(
            projection_ledger_id=store_authority.projection_ledger_id,
            projection_schema_version=store_authority.projection_schema_version,
            projection_validation_version=(
                store_authority.projection_validation_version
            ),
            projection_schema_fingerprint=(
                store_authority.projection_schema_fingerprint
            ),
            baseline_receipt_sequence=store_authority.pre_attempt_receipt_sequence,
            baseline_receipt_hash=store_authority.pre_attempt_receipt_hash,
        )
        baseline = CapacityMeasurementActorBaselineV49FV7(
            transport_subscription_policy_id=(
                actor_authority.transport_subscription_policy_id
            ),
            transport_session_id=actor_authority.transport_session_id,
            driver_evidence_nonce_sha256=(
                owner.capacity_measurement_driver_evidence_nonce_v49f
            ),
            kernel_socket_identity=owner_snapshot.kernel_socket_identity,
            transport_capacity_policy_id=admission.policy_id,
            physical_scope_manifest_id=actor_authority.physical_scope_manifest_id,
            adapter_policy_id=actor_authority.adapter_policy_id,
            capture_partition_id=actor_authority.capture_partition_id,
            socket_lease_id=actor_authority.socket_lease_id,
            connection_generation=actor_authority.connection_generation,
            deployment_bundle_id=actor_authority.deployment_bundle_id,
            writer_fence_token_sha256=(actor_authority.writer_fence_token_sha256),
            writer_fence_generation=actor_authority.writer_fence_generation,
            monotonic_clock_domain_id=actor_authority.monotonic_clock_domain_id,
            driver_policy_id=actor_authority.driver_policy_id,
            raw_ingress_sequence=raw_sequence,
            raw_ingress_commit_id=raw_tail,
            actor_event_count=actor_count,
            actor_tail_event_id=actor_tail,
            parser_cursor=projected_cursor,
            parser_cursor_id=projected_cursor.parser_cursor_id,
            runtime_state=self._state.value,
            projection_receipt_sequence=projection.baseline_receipt_sequence,
            projection_receipt_hash=projection.baseline_receipt_hash,
        )
        return projection, baseline

    async def capture_capacity_measurement_v7_baselines_v49f(
        self,
    ) -> tuple[Any, Any]:
        """Capture the production Raw-V7 signed baselines without caller seams."""

        gate = self._transport_admission_gate_v49f
        if gate is None:
            raise PhysicalTransportRuntimeV4StateError(
                "Raw-V7 baseline requires the signed V4.9F admission gate"
            )
        if self._transport_orchestration_lock_v49c.locked():
            raise PhysicalTransportRuntimeV4StateError(
                "Raw-V7 baseline requires quiescent orchestration"
            )
        async with self._transport_orchestration_lock_v49c:
            before = gate.snapshot()
            result = self._capacity_measurement_v7_baselines_from_quiescent_v49f(before)
            after = gate.snapshot()
            if before != after:
                raise PhysicalTransportRuntimeV4StateError(
                    "A1 admission state changed across Raw-V7 baseline capture"
                )
            return result

    async def capture_manifest_authority_inputs_v49f(
        self,
    ) -> tuple[
        PhysicalTransportManifestAuthoritySnapshotV49F,
        PhysicalProjectionSqliteEnvironmentObservationV49F,
    ]:
        """Atomically capture exact runtime and store observations for raw V6."""

        gate = self._transport_admission_gate_v49f
        if gate is None:
            raise PhysicalTransportRuntimeV4StateError(
                "manifest authority requires the signed V4.9F admission gate"
            )
        if self._transport_orchestration_lock_v49c.locked():
            raise PhysicalTransportRuntimeV4StateError(
                "manifest authority requires a quiescent orchestration lock"
            )
        async with self._transport_orchestration_lock_v49c:
            before = gate.snapshot()
            result = self._manifest_authority_inputs_from_quiescent_v49f(before)
            after = gate.snapshot()
            if before != after:
                raise PhysicalTransportRuntimeV4StateError(
                    "A1 admission state changed across manifest authority capture"
                )
            return result

    async def sign_manifest_authority_subject_v49f(
        self,
        *,
        authorization: Any,
    ) -> PhysicalTransportManifestAuthoritySignatureV49F:
        """Consume one exact collector authorization and sign its sole subject."""

        from .physical_transport_capacity_manifest_authority_v49f import (
            CapacityMeasurementManifestSigningAuthorizationV49F,
        )

        if (
            type(authorization)
            is not CapacityMeasurementManifestSigningAuthorizationV49F
        ):
            raise TypeError(
                "authorization must be an exact one-shot manifest signing authorization"
            )
        gate = self._transport_admission_gate_v49f
        if gate is None:
            raise PhysicalTransportRuntimeV4StateError(
                "manifest authority signing requires the signed V4.9F gate"
            )
        if self._transport_orchestration_lock_v49c.locked():
            raise PhysicalTransportRuntimeV4StateError(
                "manifest authority signing requires quiescent orchestration"
            )
        async with self._transport_orchestration_lock_v49c:
            before = gate.snapshot()
            actual_snapshot, actual_sqlite_observation = (
                self._manifest_authority_inputs_from_quiescent_v49f(before)
            )
            subject_id = authorization.consume(
                runtime_snapshot=actual_snapshot,
                sqlite_observation=actual_sqlite_observation,
            )
            after = gate.snapshot()
            if before != after:
                raise PhysicalTransportRuntimeV4StateError(
                    "A1 admission state changed across manifest authority signing"
                )

            public_key = getattr(self._signer, "public_key_bytes", None)
            sign = getattr(self._signer, "sign", None)
            if not isinstance(public_key, bytes) or not callable(sign):
                raise PhysicalTransportRuntimeV4StateError(
                    "authorized collector signer is no longer available"
                )
            key_id = derive_transport_attestation_key_id(public_key)
            if key_id != actual_snapshot.collector_attestation_key_id:
                raise PhysicalTransportRuntimeV4StateError(
                    "collector signer differs from retained deployment authority"
                )
            payload = {
                "canonicalization_version": CANONICALIZATION_VERSION,
                "domain": _A2M_MANIFEST_AUTHORITY_SIGNING_DOMAIN_V49F,
                "payload": {
                    "authority_subject_id": subject_id,
                    "deployment_bundle_id": actual_snapshot.deployment_bundle_id,
                    "collector_attestation_key_id": key_id,
                    "transport_session_id": actual_snapshot.transport_session_id,
                },
                "schema_version": (PHYSICAL_TRANSPORT_A2M_RAW_V49F_V6_SCHEMA_VERSION),
            }
            signature = sign(canonical_json_bytes(payload))
            if not isinstance(signature, bytes) or len(signature) != 64:
                raise PhysicalTransportRuntimeV4StateError(
                    "collector signer returned an invalid Ed25519 signature"
                )
            return PhysicalTransportManifestAuthoritySignatureV49F(
                authority_subject_id=subject_id,
                deployment_bundle_id=actual_snapshot.deployment_bundle_id,
                collector_attestation_key_id=key_id,
                collector_attestation_public_key_hex=public_key.hex(),
                transport_session_id=actual_snapshot.transport_session_id,
                signature_hex=signature.hex(),
            )

    async def sign_manifest_authority_subject_v49f_v7(
        self,
        *,
        authorization: Any,
    ) -> PhysicalTransportManifestAuthoritySignatureV49FV7:
        """Consume one V7-only authorization and sign its domain-separated subject."""

        from .physical_transport_capacity_manifest_authority_v49f import (
            CapacityMeasurementManifestSigningAuthorizationV49FV7,
        )

        if (
            type(authorization)
            is not CapacityMeasurementManifestSigningAuthorizationV49FV7
        ):
            raise TypeError(
                "authorization must be an exact one-shot Raw-V7 signing authorization"
            )
        gate = self._transport_admission_gate_v49f
        if gate is None:
            raise PhysicalTransportRuntimeV4StateError(
                "Raw-V7 signing requires the signed V4.9F admission gate"
            )
        if self._transport_orchestration_lock_v49c.locked():
            raise PhysicalTransportRuntimeV4StateError(
                "Raw-V7 signing requires quiescent orchestration"
            )
        async with self._transport_orchestration_lock_v49c:
            before = gate.snapshot()
            actual_snapshot, actual_sqlite_observation = (
                self._manifest_authority_inputs_from_quiescent_v49f(before)
            )
            actual_projection, actual_actor = (
                self._capacity_measurement_v7_baselines_from_quiescent_v49f(before)
            )
            subject_id, payload = authorization.consume(
                runtime=self,
                runtime_snapshot=actual_snapshot,
                sqlite_observation=actual_sqlite_observation,
                projection_authority=actual_projection,
                actor_baseline=actual_actor,
            )
            after = gate.snapshot()
            if before != after:
                raise PhysicalTransportRuntimeV4StateError(
                    "A1 admission state changed across Raw-V7 signing"
                )

            public_key = getattr(self._signer, "public_key_bytes", None)
            sign = getattr(self._signer, "sign", None)
            if not isinstance(public_key, bytes) or not callable(sign):
                raise PhysicalTransportRuntimeV4StateError(
                    "authorized Raw-V7 collector signer is no longer available"
                )
            key_id = derive_transport_attestation_key_id(public_key)
            if key_id != actual_snapshot.collector_attestation_key_id:
                raise PhysicalTransportRuntimeV4StateError(
                    "Raw-V7 signer differs from retained deployment authority"
                )
            if (
                payload.get("domain") != _A2M_MANIFEST_AUTHORITY_SIGNING_DOMAIN_V49F_V7
                or payload.get("schema_version")
                != PHYSICAL_TRANSPORT_A2M_RAW_V49F_V7_SCHEMA_VERSION
            ):
                raise PhysicalTransportRuntimeV4StateError(
                    "Raw-V7 signing authorization returned the wrong domain"
                )
            encoded = canonical_json_bytes(payload)
            signature = sign(encoded)
            if not isinstance(signature, bytes) or len(signature) != 64:
                raise PhysicalTransportRuntimeV4StateError(
                    "Raw-V7 collector signer returned an invalid Ed25519 signature"
                )
            try:
                Ed25519CheckpointVerifier.from_public_bytes(public_key).verify(
                    encoded, signature
                )
            except Exception as exc:
                raise PhysicalTransportRuntimeV4StateError(
                    "Raw-V7 collector signature failed immediate verification"
                ) from exc
            return PhysicalTransportManifestAuthoritySignatureV49FV7(
                authority_subject_id=subject_id,
                deployment_bundle_id=actual_snapshot.deployment_bundle_id,
                collector_attestation_key_id=key_id,
                collector_attestation_public_key_hex=public_key.hex(),
                transport_session_id=actual_snapshot.transport_session_id,
                signed_payload_sha256=hashlib.sha256(encoded).hexdigest(),
                signature_hex=signature.hex(),
            )

    def capacity_measurement_database_path_v49f(self) -> Path:
        """Derive the exact actor projection path for the closed A2-M sampler."""

        from .physical_transport_actor_journal_v49c import (
            PhysicalTransportActorProjectionJournalV49C,
        )

        journal = self._transport_actor_journal_v49c
        actor = self._transport_session_actor_v49c
        if (
            type(journal) is not PhysicalTransportActorProjectionJournalV49C
            or actor is None
            or journal.authority is not actor.authority
        ):
            raise PhysicalTransportRuntimeV4StateError(
                "capacity storage observation requires the exact actor journal"
            )
        return journal.capacity_measurement_database_path_v49f

    def capacity_measurement_admitted_expectation_v49f(self) -> Any:
        """Derive Raw-V6 replay trust only from the verified deployment."""

        from .physical_transport_capacity_manifest_authority_v49f import (
            AdmittedCapacityMeasurementAuthorityExpectationV49F,
        )

        capability = self._deployment_capability
        releases = tuple(
            child
            for child in self._deployment_admission.children
            if type(child) is CollectorReleaseManifestV4
        )
        if type(capability) is not VerifiedDeploymentCapabilityV4 or len(releases) != 1:
            raise PhysicalTransportRuntimeV4StateError(
                "capacity replay expectation requires one verified deployment release"
            )
        return AdmittedCapacityMeasurementAuthorityExpectationV49F.from_verified_deployment(
            capability=capability,
            collector_release=releases[0],
            authority_profile=("LIVE_LINUX" if self._is_live_profile else "EXACT_TEST"),
        )

    def _capacity_measurement_boundary_from_quiescent_v49f(
        self, admission: TransportAdmissionSnapshotV49F
    ) -> PhysicalTransportCapacityMeasurementBoundaryV49F:
        """Construct a boundary after the caller established quiescence."""

        if admission.active_and_waiting_commands != 0:
            raise PhysicalTransportRuntimeV4StateError(
                "capacity boundary requires a quiescent admission gate"
            )
        session = self._session
        owner_snapshot = self._socket_owner_snapshot
        actor = self._transport_session_actor_v49c
        owner = self._socket_owner
        from .physical_transport_linux_v4 import LinuxSocketOwnerV4
        from .physical_transport_owner_v4 import TransportSocketOwnerSnapshotV4
        from .physical_transport_session_actor_v49c import (
            PhysicalTransportSessionActorV49C,
        )
        from .physical_transport_v4 import TransportSessionAttestationV4

        if (
            type(session) is not TransportSessionAttestationV4
            or type(owner_snapshot) is not TransportSocketOwnerSnapshotV4
            or type(actor) is not PhysicalTransportSessionActorV49C
            or type(owner) is not LinuxSocketOwnerV4
        ):
            raise PhysicalTransportRuntimeV4StateError(
                "capacity boundary requires one committed exact actor session"
            )
        if actor.authority.transport_session_id != session.transport_session_id:
            raise PhysicalTransportRuntimeV4StateError(
                "capacity boundary actor differs from the committed session"
            )
        return PhysicalTransportCapacityMeasurementBoundaryV49F(
            transport_session_id=session.transport_session_id,
            driver_evidence_nonce_sha256=(
                owner.capacity_measurement_driver_evidence_nonce_v49f
            ),
            kernel_socket_identity=owner_snapshot.kernel_socket_identity,
            transport_capacity_policy_id=admission.policy_id,
            admission_epoch=admission.admission_epoch,
            admission_closed=admission.closed,
            admission_terminal_barrier_admission_sequence=(
                admission.terminal_barrier_admission_sequence
            ),
            admission_terminal_barrier_committed=(admission.terminal_barrier_committed),
            admission_active_admission_sequence=admission.active_admission_sequence,
            admission_active_command_kind=(
                None
                if admission.active_command_kind is None
                else admission.active_command_kind.value
            ),
            admission_waiting_admission_sequences=(
                admission.waiting_admission_sequences
            ),
            admission_waiting_command_kinds=tuple(
                value.value for value in admission.waiting_command_kinds
            ),
            admission_oldest_waiting_age_nanoseconds=(
                admission.oldest_waiting_age_nanoseconds
            ),
            admission_reserved_work_units=admission.reserved_work_units,
            admission_maximum_observed_admitted_commands=(
                admission.maximum_observed_admitted_commands
            ),
            admission_maximum_observed_reserved_work_units=(
                admission.maximum_observed_reserved_work_units
            ),
            admission_last_started_queue_wait_nanoseconds=(
                admission.last_started_queue_wait_nanoseconds
            ),
            admission_maximum_observed_queue_wait_nanoseconds=(
                admission.maximum_observed_queue_wait_nanoseconds
            ),
            admission_released_commands=admission.released_commands,
            admission_rejected_commands=admission.rejected_commands,
            admission_duplicate_kind_rejections=(admission.duplicate_kind_rejections),
            admission_terminal_barrier_rejections=(
                admission.terminal_barrier_rejections
            ),
            admission_capacity_rejections=admission.capacity_rejections,
            admission_closed_rejections=admission.closed_rejections,
            admission_timed_out_commands=admission.timed_out_commands,
            admission_cancelled_before_entry_commands=(
                admission.cancelled_before_entry_commands
            ),
            admission_closed_before_entry_commands=(
                admission.closed_before_entry_commands
            ),
            actor_event_count=actor.event_count_v49f,
            actor_tail_event_id=actor.tail_event_id_v49f,
            actor_wire_queue_events=actor.wire_queue_event_count_v49f,
            actor_wire_queue_octets=actor.wire_queue_octet_count_v49f,
            runtime_state=self._state.value,
        )

    def capacity_measurement_boundary_v49f(
        self,
    ) -> PhysicalTransportCapacityMeasurementBoundaryV49F:
        """Read one sole-caller, quiescent A2-M boundary without full replay.

        The method is deliberately unavailable while a runtime command owns or
        waits for admission.  It performs no I/O, hashing, SQLite query, actor
        history copy, or currentness revalidation.
        """

        if self._transport_orchestration_lock_v49c.locked():
            raise PhysicalTransportRuntimeV4StateError(
                "capacity boundary requires a quiescent orchestration lock"
            )
        gate = self._transport_admission_gate_v49f
        if gate is None:
            raise PhysicalTransportRuntimeV4StateError(
                "capacity boundary requires the signed V4.9F admission gate"
            )
        admission = gate.snapshot()
        if admission.active_and_waiting_commands != 0:
            raise PhysicalTransportRuntimeV4StateError(
                "capacity boundary requires a quiescent admission gate"
            )
        return self._capacity_measurement_boundary_from_quiescent_v49f(admission)

    async def capture_capacity_measurement_boundary_v49f(
        self,
    ) -> PhysicalTransportCapacityMeasurementBoundaryV49F:
        """Capture actor counters while owning the runtime orchestration seam."""

        gate = self._transport_admission_gate_v49f
        if gate is None:
            raise PhysicalTransportRuntimeV4StateError(
                "capacity boundary requires the signed V4.9F admission gate"
            )
        if self._transport_orchestration_lock_v49c.locked():
            raise PhysicalTransportRuntimeV4StateError(
                "capacity boundary requires a quiescent orchestration lock"
            )
        async with self._transport_orchestration_lock_v49c:
            return self._capacity_measurement_boundary_from_quiescent_v49f(
                gate.snapshot()
            )

    async def capacity_measurement_transport_flow_v49f(self) -> Any:
        """Observe the exact retained owner only at a quiescent A2-M boundary."""

        owner = self._socket_owner
        gate = self._transport_admission_gate_v49f
        from .physical_transport_linux_v4 import (
            LinuxSocketOwnerV4,
            LinuxSocketTransportFlowSnapshotV49F,
        )

        if type(owner) is not LinuxSocketOwnerV4 or gate is None:
            raise PhysicalTransportRuntimeV4StateError(
                "capacity flow requires the exact retained Linux owner"
            )
        if self._transport_orchestration_lock_v49c.locked():
            raise PhysicalTransportRuntimeV4StateError(
                "capacity flow requires a quiescent orchestration lock"
            )
        async with self._transport_orchestration_lock_v49c:
            before = gate.snapshot()
            if before.active_and_waiting_commands != 0:
                raise PhysicalTransportRuntimeV4StateError(
                    "capacity flow requires a sole-caller admission boundary"
                )
            boundary = self._capacity_measurement_boundary_from_quiescent_v49f(before)
            observed = await owner.transport_flow_snapshot_v49f()
            after = gate.snapshot()
            if (
                type(observed) is not LinuxSocketTransportFlowSnapshotV49F
                or observed.kernel_socket_identity != boundary.kernel_socket_identity
                or before != after
            ):
                raise PhysicalTransportRuntimeV4StateError(
                    "capacity flow changed across its quiescent runtime boundary"
                )
            return observed

    def issue_capacity_measurement_ingress_authorization_v49f_v7(
        self,
        *,
        campaign: object,
        runner_authority: object,
        runner: object,
    ) -> tuple[Any, CapacityMeasurementIngressAuthorizationV49F]:
        """Derive and seal the sole next operation from one retained V7 campaign."""

        from .physical_transport_actor_journal_v49c import (
            PhysicalTransportActorProjectionJournalV49C,
        )
        from .physical_transport_capacity_manifest_authority_v49f import (
            CapacityMeasurementCampaignRunnerAuthorizationV49FV7,
            CollectedCapacityMeasurementCampaignV49FV7,
        )

        if type(campaign) is not CollectedCapacityMeasurementCampaignV49FV7:
            raise CapacityMeasurementIngressAuthorizationV49FError(
                "production Raw-V7 issuance requires its exact retained campaign"
            )
        if (
            type(runner_authority)
            is not CapacityMeasurementCampaignRunnerAuthorizationV49FV7
        ):
            raise CapacityMeasurementIngressAuthorizationV49FError(
                "production Raw-V7 issuance requires its retained runner authority"
            )
        runner_authority.assert_owner(
            campaign=campaign,
            runtime=self,
            runner=runner,
        )
        if (
            campaign.runtime is not self
            or type(self._transport_actor_journal_v49c)
            is not PhysicalTransportActorProjectionJournalV49C
            or self._transport_admission_gate_v49f is None
            or self._transport_session_actor_v49c is None
        ):
            raise CapacityMeasurementIngressAuthorizationV49FError(
                "Raw-V7 issuance requires one exact active A1 actor session"
            )
        self._require_state(
            PhysicalTransportRuntimeStateV4.SESSION_COMMITTED,
            PhysicalTransportRuntimeStateV4.AWAITING_ACK,
            PhysicalTransportRuntimeStateV4.ACK_BOUND,
        )
        declaration: Any | None = None
        try:
            declaration, previous_terminal_id = campaign._begin_next_operation_v49f(  # noqa: SLF001
                runtime=self,
                runner_authority=runner_authority,
            )
            predecessor = campaign.manifest.predecessor_manifest_v6
            authorization = CapacityMeasurementIngressAuthorizationV49F(
                _token=_CAPACITY_MEASUREMENT_AUTHORIZATION_TOKEN_V49F,
                runtime=self,
                campaign=campaign,
                declaration=declaration,
                previous_operation_terminal_id=previous_terminal_id,
                observer_monotonic_ns=time.monotonic_ns,
                boottime_ns=lambda: time.clock_gettime_ns(time.CLOCK_BOOTTIME),
                observer_origin_ns=int(predecessor.monotonic_origin_nanoseconds),
                boottime_origin_ns=int(predecessor.boottime_origin_nanoseconds),
                loop_origin_ns=int(predecessor.loop_time_origin_nanoseconds),
            )
            return declaration, authorization
        except BaseException:
            if declaration is not None:
                campaign._abandon_uncommitted_operation_v49f(  # noqa: SLF001
                    declaration=declaration
                )
            raise

    def load_capacity_measurement_operation_prefix_v49f_v7(
        self,
        *,
        campaign: object,
        attempt_id: str,
    ) -> Any:
        """Load one closed prefix, constrained to the retained V7 campaign."""

        from .physical_transport_actor_journal_v49c import (
            PhysicalTransportActorProjectionJournalV49C,
        )
        from .physical_transport_capacity_lifecycle_v49f import (
            CapacityMeasurementOperationPrefixV49F,
        )
        from .physical_transport_capacity_manifest_authority_v49f import (
            CollectedCapacityMeasurementCampaignV49FV7,
        )

        journal = self._transport_actor_journal_v49c
        if (
            type(campaign) is not CollectedCapacityMeasurementCampaignV49FV7
            or campaign.runtime is not self
            or type(journal) is not PhysicalTransportActorProjectionJournalV49C
        ):
            raise CapacityMeasurementIngressAuthorizationV49FError(
                "Raw-V7 prefix recovery requires its exact retained campaign"
            )
        prefix = journal.load_capacity_measurement_operation_prefix_postmortem_v49f(
            attempt_id=attempt_id
        )
        if (
            type(prefix) is not CapacityMeasurementOperationPrefixV49F
            or prefix.terminal is None
            or prefix.attempt.campaign_manifest_id
            != campaign.manifest.campaign_manifest_id
            or prefix.attempt.manifest_authority_id
            != campaign.manifest.manifest_authority_v7.manifest_authority_id
        ):
            raise CapacityMeasurementIngressAuthorizationV49FError(
                "Raw-V7 recovered prefix differs from its retained campaign"
            )
        return prefix

    def _issue_capacity_measurement_ingress_authorization_v49f_for_test(
        self,
        *,
        campaign: object,
        declaration: Any,
        previous_operation_terminal_id: str | None,
        observer_monotonic_ns: Callable[[], int],
        boottime_ns: Callable[[], int],
        observer_origin_ns: int,
        boottime_origin_ns: int,
        loop_origin_ns: int,
    ) -> CapacityMeasurementIngressAuthorizationV49F:
        """Issue a sealed operation authority only for the exact test runtime.

        A caller-authored V7 manifest is intentionally insufficient to mint a
        production authority.  Production issuance remains fail-closed until
        the retained ``CollectedCapacityMeasurementCampaignV49FV7`` capability
        exists and can be checked here without trusting caller data.
        """

        from .physical_transport_actor_journal_v49c import (
            PhysicalTransportActorProjectionJournalV49C,
        )
        from .physical_transport_capacity_lifecycle_v49f import (
            CapacityMeasurementOperationDeclarationV49F,
        )

        if self._is_live_profile:
            raise CapacityMeasurementIngressAuthorizationV49FError(
                "production Raw-V7 issuance requires its retained campaign collector"
            )
        if (
            type(declaration) is not CapacityMeasurementOperationDeclarationV49F
            or campaign is None
            or type(self._transport_actor_journal_v49c)
            is not PhysicalTransportActorProjectionJournalV49C
            or self._transport_admission_gate_v49f is None
            or self._transport_session_actor_v49c is None
        ):
            raise CapacityMeasurementIngressAuthorizationV49FError(
                "test Raw-V7 issuance requires one exact active A1 actor session"
            )
        self._require_state(
            PhysicalTransportRuntimeStateV4.SESSION_COMMITTED,
            PhysicalTransportRuntimeStateV4.AWAITING_ACK,
            PhysicalTransportRuntimeStateV4.ACK_BOUND,
        )
        if (declaration.operation_sequence == 1) != (
            previous_operation_terminal_id is None
        ):
            raise CapacityMeasurementIngressAuthorizationV49FError(
                "capacity operation sequence differs from its prior terminal link"
            )
        return CapacityMeasurementIngressAuthorizationV49F(
            _token=_CAPACITY_MEASUREMENT_AUTHORIZATION_TOKEN_V49F,
            runtime=self,
            campaign=campaign,
            declaration=declaration,
            previous_operation_terminal_id=previous_operation_terminal_id,
            observer_monotonic_ns=observer_monotonic_ns,
            boottime_ns=boottime_ns,
            observer_origin_ns=observer_origin_ns,
            boottime_origin_ns=boottime_origin_ns,
            loop_origin_ns=loop_origin_ns,
        )

    def _capacity_measurement_operation_attempt_v49f(
        self,
        *,
        declaration: Any,
        authorization: CapacityMeasurementIngressAuthorizationV49F,
        admission_grant: TransportAdmissionGrantV49F,
    ) -> Any:
        """Build the exact attempt under A1 without performing target I/O."""

        from .physical_projection_v4 import CapacityMeasurementAttemptAuthorityV49F
        from .physical_transport_actor_journal_v49c import (
            PhysicalTransportActorProjectionJournalV49C,
        )
        from .physical_transport_actor_v49c import WebSocketParserCursorV49C
        from .physical_transport_capacity_lifecycle_v49f import (
            CapacityMeasurementLifecycleOperationV49F,
            CapacityMeasurementOperationAttemptV49F,
            CapacityMeasurementOperationDeclarationV49F,
        )
        from .physical_transport_linux_v4 import DriverHandshakeTransitionV49B
        from .physical_transport_session_actor_v49c import (
            PhysicalTransportSessionActorV49C,
        )
        from .physical_transport_v4 import TransportSessionAttestationV4

        journal = self._transport_actor_journal_v49c
        actor = self._transport_session_actor_v49c
        session = self._session
        owner_snapshot = self._socket_owner_snapshot
        owner_binding = self._socket_owner_binding
        transition = self._driver_handshake_transition_v49c
        cursor = self._parser_cursor_v49d
        gate = self._transport_admission_gate_v49f
        if (
            type(declaration) is not CapacityMeasurementOperationDeclarationV49F
            or type(authorization) is not CapacityMeasurementIngressAuthorizationV49F
            or type(admission_grant) is not TransportAdmissionGrantV49F
            or type(journal) is not PhysicalTransportActorProjectionJournalV49C
            or type(actor) is not PhysicalTransportSessionActorV49C
            or type(session) is not TransportSessionAttestationV4
            or type(owner_snapshot) is not TransportSocketOwnerSnapshotV4
            or type(owner_binding) is not TransportSocketOwnerBindingV4
            or type(transition) is not DriverHandshakeTransitionV49B
            or type(cursor) is not WebSocketParserCursorV49C
            or gate is None
        ):
            raise CapacityMeasurementIngressAuthorizationV49FError(
                "capacity attempt requires one exact retained runtime authority"
            )
        self._assert_actor_admission_v49f(
            admission_grant,
            expected_kind=TransportCommandKindV49F.INGRESS,
        )
        if (
            gate.policy.policy_id != admission_grant.policy_id
            or actor.authority.transport_session_id != session.transport_session_id
            or actor.authority.deployment_bundle_id != session.deployment_bundle_id
            or actor.authority.transport_subscription_policy_id
            != session.transport_subscription_policy_id
            or actor.authority.physical_scope_manifest_id
            != session.physical_scope_manifest_id
            or actor.authority.adapter_policy_id != session.adapter_policy_id
            or actor.authority.capture_partition_id != session.capture_partition_id
            or actor.authority.connection_generation != session.connection_generation
            or actor.authority.socket_lease_id != owner_binding.socket_lease_id
            or actor.authority.writer_fence_token_sha256
            != owner_binding.writer_fence_token_sha256
            or actor.authority.writer_fence_generation
            != owner_binding.writer_fence_generation
            or actor.authority.driver_policy_id != transition.driver_policy_id
            or owner_binding.kernel_socket_identity
            != owner_snapshot.kernel_socket_identity
        ):
            raise CapacityMeasurementIngressAuthorizationV49FError(
                "capacity attempt differs from its signed A1/session authority"
            )
        started_clock = self._sample_active_clock(
            context="Raw-V7 operation attempt clock validation failed"
        )
        raw_sequence, raw_tail, actor_count, actor_tail = (
            journal.capacity_measurement_projection_coordinates_v49f(
                transport_session_id=session.transport_session_id
            )
        )
        store_authority = journal.capacity_measurement_attempt_authority_v49f(
            authorization=authorization,
            transport_session_id=session.transport_session_id,
            baseline_actor_event_count=actor_count,
        )
        if type(store_authority) is not CapacityMeasurementAttemptAuthorityV49F:
            raise CapacityMeasurementIngressAuthorizationV49FError(
                "capacity journal returned an unsupported attempt authority"
            )
        if (
            actor_count != actor.event_count_v49f
            or actor_tail != actor.tail_event_id_v49f
            or store_authority.writer_fence_token_sha256
            != actor.authority.writer_fence_token_sha256
            or store_authority.writer_fence_generation
            != actor.authority.writer_fence_generation
            or store_authority.writer_fence_token_sha256
            != self._writer_fence_token_sha256
            or store_authority.writer_fence_generation != self._writer_fence_generation
            or session.monotonic_clock_domain_id
            != actor.authority.monotonic_clock_domain_id
        ):
            raise CapacityMeasurementIngressAuthorizationV49FError(
                "capacity projection/actor/writer authority changed before attempt"
            )
        observer_offset, boottime_offset, loop_offset = authorization.attempt_offsets()
        if (
            authorization.observer_origin_nanoseconds + observer_offset
            < started_clock.monotonic_ns
        ):
            raise CapacityMeasurementIngressAuthorizationV49FError(
                "capacity observer attempt boundary precedes governed runtime start"
            )
        declaration_values = {
            name: getattr(declaration, name)
            for name in (
                "campaign_manifest_id",
                "manifest_authority_id",
                "measurement_design_id",
                "declaration_id",
                "workload_id",
                "workload_sha256",
                "sample_sequence",
                "operation_sequence",
                "trial_index",
                "repetition_index",
                "is_warmup",
                "stage",
                "operation",
                "input_chunk_count",
                "input_octet_count",
                "input_sha256",
                "raw_ingress_batch_sha256",
                "timeout_seconds",
                "expected_output_frame_count",
                "expected_output_frames_sha256",
            )
        }
        return CapacityMeasurementOperationAttemptV49F(
            **declaration_values,
            previous_operation_terminal_id=(
                authorization.previous_operation_terminal_id
            ),
            transport_session_id=session.transport_session_id,
            driver_evidence_nonce_sha256=(transition.evidence.evidence_nonce_sha256),
            kernel_socket_identity=owner_snapshot.kernel_socket_identity,
            transport_capacity_policy_id=gate.policy.policy_id,
            transport_capacity_policy=gate.policy,
            projection_ledger_id=store_authority.projection_ledger_id,
            projection_schema_version=store_authority.projection_schema_version,
            projection_validation_version=(
                store_authority.projection_validation_version
            ),
            projection_schema_fingerprint=(
                store_authority.projection_schema_fingerprint
            ),
            projection_store_observation_id=(
                store_authority.projection_store_observation_id
            ),
            writer_fence_token_sha256=store_authority.writer_fence_token_sha256,
            writer_fence_generation=store_authority.writer_fence_generation,
            pre_attempt_receipt_sequence=(store_authority.pre_attempt_receipt_sequence),
            pre_attempt_receipt_hash=store_authority.pre_attempt_receipt_hash,
            retained_raw_dependencies=store_authority.retained_raw_dependencies,
            initial_pending_ingress_present_before=(
                self._initial_pending_raw_ingress_v49c is not None
            ),
            observer_start_offset_nanoseconds=observer_offset,
            boottime_start_offset_nanoseconds=boottime_offset,
            loop_time_start_offset_nanoseconds=loop_offset,
            loop_time_origin_nanoseconds=str(authorization.loop_origin_nanoseconds),
            admission_policy_id=admission_grant.policy_id,
            admission_epoch=admission_grant.admission_epoch,
            admission_sequence=admission_grant.admission_sequence,
            admission_command_kind=(CapacityMeasurementLifecycleOperationV49F.INGRESS),
            admission_reservation_work_units=(admission_grant.reservation_work_units),
            admission_admitted_loop_time_ns=str(admission_grant.admitted_loop_time_ns),
            admission_started_loop_time_ns=str(admission_grant.started_loop_time_ns),
            admission_start_deadline_loop_time_ns=str(
                admission_grant.start_deadline_loop_time_ns
            ),
            admission_queue_wait_nanoseconds=(admission_grant.queue_wait_nanoseconds),
            baseline_raw_ingress_sequence=raw_sequence,
            baseline_raw_ingress_commit_id=raw_tail,
            baseline_actor_event_count=actor_count,
            baseline_actor_tail_event_id=actor_tail,
            parser_cursor_before=cursor,
            parser_cursor_id_before=cursor.parser_cursor_id,
            runtime_state_before=self._state.value,
            started_at=started_clock.sampled_at,
            started_monotonic_ns=str(started_clock.monotonic_ns),
            monotonic_clock_domain_id=session.monotonic_clock_domain_id,
        )

    def _capacity_measurement_same_task_terminal_observation_v49f(
        self,
        *,
        committed_attempt: Any,
        authorization: CapacityMeasurementIngressAuthorizationV49F,
        terminal_trigger: Any,
        surfaced_exception: BaseException | None,
        returned_progress_evidence: Any | None,
    ) -> Any:
        """Capture bounded post-effect facts; the store derives the terminal."""

        from .physical_projection_v4 import (
            CommittedCapacityMeasurementOperationAttemptV49F,
        )
        from .physical_transport_capacity_lifecycle_v49f import (
            CapacityMeasurementLifecycleTerminalTriggerV49F,
            CapacityMeasurementSameTaskTerminalObservationV49F,
        )
        from .physical_transport_capacity_measurement_v49f import (
            CapacityMeasurementIngressProgressEvidenceV49F,
        )

        if (
            type(committed_attempt)
            is not CommittedCapacityMeasurementOperationAttemptV49F
            or type(authorization) is not CapacityMeasurementIngressAuthorizationV49F
            or type(terminal_trigger)
            is not CapacityMeasurementLifecycleTerminalTriggerV49F
            or (
                returned_progress_evidence is not None
                and type(returned_progress_evidence)
                is not CapacityMeasurementIngressProgressEvidenceV49F
            )
        ):
            raise CapacityMeasurementIngressAuthorizationV49FError(
                "capacity terminal requires one exact retained operation authority"
            )
        attempt = committed_attempt.attempt
        returned = (
            terminal_trigger is CapacityMeasurementLifecycleTerminalTriggerV49F.RETURNED
        )
        if returned != (returned_progress_evidence is not None) or returned != (
            surfaced_exception is None
        ):
            raise CapacityMeasurementIngressAuthorizationV49FError(
                "capacity terminal trigger differs from its exact outcome"
            )
        if returned:
            exception_classes: tuple[str, ...] = ()
            exception_messages: tuple[str, ...] = ()
        else:
            if (
                terminal_trigger
                not in {
                    CapacityMeasurementLifecycleTerminalTriggerV49F.CANCELLED,
                    CapacityMeasurementLifecycleTerminalTriggerV49F.INTERRUPTED,
                    CapacityMeasurementLifecycleTerminalTriggerV49F.RAISED_EXCEPTION,
                }
                or surfaced_exception is None
            ):
                raise CapacityMeasurementIngressAuthorizationV49FError(
                    "capacity failure terminal lacks its exact Python exception"
                )
            exception_classes, exception_messages = (
                _capacity_measurement_exception_chain_v49f(surfaced_exception)
            )
        observer_end, boottime_end, loop_end = authorization.terminal_offsets()
        if authorization.observer_origin_nanoseconds + observer_end < int(
            attempt.started_monotonic_ns
        ):
            raise CapacityMeasurementIngressAuthorizationV49FError(
                "capacity terminal observer clock precedes the governed attempt"
            )
        return CapacityMeasurementSameTaskTerminalObservationV49F(
            terminal_trigger=terminal_trigger,
            surfaced_exception_class=(
                None if not exception_classes else exception_classes[0]
            ),
            exception_class_chain=exception_classes,
            exception_message_sha256_chain=exception_messages,
            runtime_state_after=self._state.value,
            observer_end_offset_nanoseconds=observer_end,
            boottime_end_offset_nanoseconds=boottime_end,
            loop_time_end_offset_nanoseconds=loop_end,
        )

    def _close_capacity_measurement_operation_v49f(
        self,
        *,
        committed_attempt: Any,
        authorization: CapacityMeasurementIngressAuthorizationV49F,
        terminal_trigger: Any,
        surfaced_exception: BaseException | None,
        returned_progress_evidence: Any | None,
    ) -> Any:
        journal = self._transport_actor_journal_v49c
        from .physical_transport_actor_journal_v49c import (
            PhysicalTransportActorProjectionJournalV49C,
        )

        if type(journal) is not PhysicalTransportActorProjectionJournalV49C:
            raise CapacityMeasurementIngressAuthorizationV49FError(
                "capacity closure lost its exact actor journal"
            )
        observation = self._capacity_measurement_same_task_terminal_observation_v49f(
            committed_attempt=committed_attempt,
            authorization=authorization,
            terminal_trigger=terminal_trigger,
            surfaced_exception=surfaced_exception,
            returned_progress_evidence=returned_progress_evidence,
        )
        return journal.close_capacity_measurement_operation_v49f(
            committed_attempt=committed_attempt,
            observation=observation,
            returned_progress_evidence=returned_progress_evidence,
        )

    async def process_next_ingress_for_capacity_measurement_v49f(
        self,
        *,
        campaign: object,
        declaration: Any,
        authorization: CapacityMeasurementIngressAuthorizationV49F,
    ) -> CapacityMeasurementIngressClosureV49F:
        """Measure one unchanged ingress call with durable attempt/terminal closure."""

        from .physical_transport_capacity_lifecycle_v49f import (
            CapacityMeasurementLifecycleTerminalTriggerV49F,
            CapacityMeasurementOperationDeclarationV49F,
        )
        from .physical_transport_capacity_sampler_v49f import (
            _measurement_ingress_progress_evidence_v49f,
        )

        if (
            type(declaration) is not CapacityMeasurementOperationDeclarationV49F
            or type(authorization) is not CapacityMeasurementIngressAuthorizationV49F
        ):
            raise CapacityMeasurementIngressAuthorizationV49FError(
                "capacity ingress requires one exact declaration and authorization"
            )
        async with self._admit_actor_command_v49f(
            TransportCommandKindV49F.INGRESS
        ) as admission_grant:
            if type(admission_grant) is not TransportAdmissionGrantV49F:
                raise CapacityMeasurementIngressAuthorizationV49FError(
                    "capacity ingress requires the signed A1 admission gate"
                )
            authorization.consume(
                runtime=self,
                campaign=campaign,
                declaration=declaration,
                grant=admission_grant,
            )
            attempt = self._capacity_measurement_operation_attempt_v49f(
                declaration=declaration,
                authorization=authorization,
                admission_grant=admission_grant,
            )
            journal = self._transport_actor_journal_v49c
            committed_attempt = (
                journal.commit_capacity_measurement_operation_attempt_v49f(
                    attempt=attempt,
                    authorization=authorization,
                )
            )
            try:
                progress = await self._process_next_ingress_v49d_locked(
                    timeout_seconds=declaration.timeout_seconds,
                    admission_grant_v49f=admission_grant,
                )
                returned_progress_evidence = (
                    _measurement_ingress_progress_evidence_v49f(
                        progress,
                        loop_time_origin_nanoseconds=(
                            authorization.loop_origin_nanoseconds
                        ),
                    )
                )
            except asyncio.CancelledError as exc:
                try:
                    self._close_capacity_measurement_operation_v49f(
                        committed_attempt=committed_attempt,
                        authorization=authorization,
                        terminal_trigger=(
                            CapacityMeasurementLifecycleTerminalTriggerV49F.CANCELLED
                        ),
                        surfaced_exception=exc,
                        returned_progress_evidence=None,
                    )
                except BaseException as persistence_error:
                    BaseException.add_note(
                        exc,
                        "Raw-V7 terminal persistence failed; startup recovery owns "
                        "the durable open attempt",
                    )
                    raise exc from persistence_error
                raise
            except KeyboardInterrupt as exc:
                try:
                    self._close_capacity_measurement_operation_v49f(
                        committed_attempt=committed_attempt,
                        authorization=authorization,
                        terminal_trigger=(
                            CapacityMeasurementLifecycleTerminalTriggerV49F.INTERRUPTED
                        ),
                        surfaced_exception=exc,
                        returned_progress_evidence=None,
                    )
                except BaseException as persistence_error:
                    BaseException.add_note(
                        exc,
                        "Raw-V7 terminal persistence failed; startup recovery owns "
                        "the durable open attempt",
                    )
                    raise exc from persistence_error
                raise
            except SystemExit as exc:
                try:
                    self._close_capacity_measurement_operation_v49f(
                        committed_attempt=committed_attempt,
                        authorization=authorization,
                        terminal_trigger=(
                            CapacityMeasurementLifecycleTerminalTriggerV49F.INTERRUPTED
                        ),
                        surfaced_exception=exc,
                        returned_progress_evidence=None,
                    )
                except BaseException as persistence_error:
                    BaseException.add_note(
                        exc,
                        "Raw-V7 terminal persistence failed; startup recovery owns "
                        "the durable open attempt",
                    )
                    raise exc from persistence_error
                raise
            except Exception as exc:
                try:
                    self._close_capacity_measurement_operation_v49f(
                        committed_attempt=committed_attempt,
                        authorization=authorization,
                        terminal_trigger=(
                            CapacityMeasurementLifecycleTerminalTriggerV49F.RAISED_EXCEPTION
                        ),
                        surfaced_exception=exc,
                        returned_progress_evidence=None,
                    )
                except BaseException as persistence_error:
                    BaseException.add_note(
                        exc,
                        "Raw-V7 terminal persistence failed; startup recovery owns "
                        "the durable open attempt",
                    )
                    raise exc from persistence_error
                raise
            try:
                terminalized_prefix = self._close_capacity_measurement_operation_v49f(
                    committed_attempt=committed_attempt,
                    authorization=authorization,
                    terminal_trigger=(
                        CapacityMeasurementLifecycleTerminalTriggerV49F.RETURNED
                    ),
                    surfaced_exception=None,
                    returned_progress_evidence=returned_progress_evidence,
                )
            except BaseException as persistence_error:
                raise CapacityMeasurementTerminalPersistenceV49FError(
                    "Raw-V7 returned ingress lacks its durable terminal closure"
                ) from persistence_error
            return CapacityMeasurementIngressClosureV49F(
                committed_attempt=committed_attempt,
                terminalized_prefix=terminalized_prefix,
                returned_progress=progress,
                returned_progress_evidence=returned_progress_evidence,
            )

    async def process_next_ingress_v49d(
        self, *, timeout_seconds: int = 10
    ) -> PhysicalTransportIngressProgressV49D:
        """Commit and parse one owner-derived RAW batch without caller seams.

        One call adopts exactly one RAW batch, drains all complete frame units
        already covered by that durable prefix, and fully submits each automatic
        Pong/Close before the next parser mutation.  An incomplete oldest frame
        remains retained across calls with exact cross-RAW attribution.
        """

        async with self._admit_actor_command_v49f(
            TransportCommandKindV49F.INGRESS
        ) as admission_grant_v49f:
            return await self._process_next_ingress_v49d_locked(
                timeout_seconds=timeout_seconds,
                admission_grant_v49f=admission_grant_v49f,
            )

    async def _process_next_ingress_v49d_locked(
        self,
        *,
        timeout_seconds: int,
        terminal_close_command_event: Any | None = None,
        admission_grant_v49f: TransportAdmissionGrantV49F | None = None,
    ) -> PhysicalTransportIngressProgressV49D:
        admission_kind_v49f = (
            TransportCommandKindV49F.INGRESS
            if terminal_close_command_event is None
            else TransportCommandKindV49F.LOCAL_SHUTDOWN
        )
        self._assert_actor_admission_v49f(
            admission_grant_v49f,
            expected_kind=admission_kind_v49f,
        )
        self._require_state(
            PhysicalTransportRuntimeStateV4.SESSION_COMMITTED,
            PhysicalTransportRuntimeStateV4.AWAITING_ACK,
            PhysicalTransportRuntimeStateV4.ACK_BOUND,
        )
        timeout = canonical_safe_int(
            timeout_seconds, field="timeout_seconds", minimum=1, maximum=300
        )
        terminal_command_event = terminal_close_command_event
        actor = self._transport_session_actor_v49c
        owner = self._socket_owner
        transition = self._driver_handshake_transition_v49c
        tail = self._retained_ingress_tail_v49d
        cursor = self._parser_cursor_v49d

        from .physical_transport_actor_v49c import (
            CommittedRawChunkV49C,
            DelineatedServerFrameV49C,
            FrameDelineationErrorV49C,
            LocalShutdownCommandStartedPayloadV49E,
            ParserErrorKindV49C,
            ParserErrorMetadataV49C,
            ParserFeedUnitKindV49C,
            ParserTransitionPayloadV49C,
            RawIngressCommittedPayloadV49C,
            RetainedIngressTailV49C,
            TransportActorEventKindV49C,
            TransportActorEventV49C,
            WebSocketOpcodeV49C,
            WebSocketParserCursorV49C,
            WebSocketParserStateV49C,
            _decode_single_automatic_protocol_output_v49c,
            delineate_next_server_frame_v49c,
        )
        from .physical_transport_linux_v4 import (
            DriverHandshakeTransitionV49B,
            LinuxSocketOwnerV4,
        )
        from .physical_transport_session_actor_v49c import (
            PhysicalTransportSessionActorV49C,
            TerminalIngressReadOutcomeV49E,
        )
        from .physical_transport_tls_v49 import (
            DurableIngressAdoptionV49D,
            ParsedDurableUnitV49D,
            PendingRawIngressV49,
        )

        if (
            type(actor) is not PhysicalTransportSessionActorV49C
            or type(owner) is not LinuxSocketOwnerV4
            or type(transition) is not DriverHandshakeTransitionV49B
            or type(tail) is not RetainedIngressTailV49C
            or type(cursor) is not WebSocketParserCursorV49C
            or self._transport_actor_activation_v49c_in_progress
        ):
            raise PhysicalTransportRuntimeV4StateError(
                "V4.9D ingress requires one activated exact owner/actor/parser"
            )
        terminal_state = actor.terminal_state
        open_ingress = (
            terminal_command_event is None
            and cursor.websocket_state is WebSocketParserStateV49C.OPEN
        )
        local_close_ingress = (
            type(terminal_command_event) is TransportActorEventV49C
            and terminal_command_event.event_kind
            is TransportActorEventKindV49C.LOCAL_SHUTDOWN_COMMAND_STARTED
            and type(terminal_command_event.payload)
            is LocalShutdownCommandStartedPayloadV49E
            and actor.local_shutdown_command_event_v49e is terminal_command_event
            and cursor.websocket_state is WebSocketParserStateV49C.CLOSING
            and terminal_state.ws_close_sent
            and terminal_state.ws_output_fully_kernel_accepted
            and not terminal_state.ws_close_received
        )
        if (
            actor.is_fault_latched
            or actor.oldest_outbound_wire_event_id is not None
            or actor.has_pending_automatic_protocol_output
            or not (open_ingress or local_close_ingress)
        ):
            raise PhysicalTransportRuntimeV4StateError(
                "V4.9D ingress cannot overtake outbound or non-open actor state"
            )

        event_count_before = len(actor.events)
        actor_tail_event_id_before = actor.tail_event_id_v49f
        parser_event_ids: list[str] = []
        automatic_output_source_parser_event_ids: list[str] = []
        completion_event_ids: list[str] = []
        automatic_output_chunks: list[bytes] = []
        automatic_output_wire_chunk_counts: list[int] = []
        automatic_output_frames: list[tuple[str, bytes]] = []
        used_initial = self._initial_pending_raw_ingress_v49c is not None
        terminal_read_outcome: TerminalIngressReadOutcomeV49E | None = None
        try:
            self._assert_lease()
            self._assert_socket_owner(context="before V4.9D RAW ingress")
            self._assert_application_fence(context="before V4.9D RAW ingress")
            if terminal_command_event is None:
                pending = await owner.read_decrypted_ingress_v49d(
                    timeout_seconds=timeout
                )
            else:
                command = terminal_command_event.payload
                assert type(command) is LocalShutdownCommandStartedPayloadV49E

                async def read_terminal_ingress(*, deadline_ns: int) -> Any:
                    if deadline_ns != command.shutdown_deadline_monotonic_ns:
                        raise PhysicalTransportRuntimeV4Error(
                            "actor changed the terminal-ingress command deadline"
                        )
                    return await owner.read_terminal_close_ingress_v49e(
                        deadline_ns=deadline_ns
                    )

                terminal_read_outcome = await actor.read_terminal_close_ingress_v49e(
                    terminal_command_event,
                    driver_evidence_nonce_sha256=(
                        transition.evidence.evidence_nonce_sha256
                    ),
                    read_effect=read_terminal_ingress,
                    signer=self._signer,
                )
                if type(terminal_read_outcome) is not TerminalIngressReadOutcomeV49E:
                    raise PhysicalTransportRuntimeV4Error(
                        "actor returned an unsupported terminal-ingress outcome"
                    )
                pending = terminal_read_outcome.pending_raw
            if type(pending) is not PendingRawIngressV49:
                raise PhysicalTransportRuntimeV4Error(
                    "owner returned an unsupported V4.9D RAW batch"
                )
            if pending.driver_evidence_nonce_sha256 != (
                transition.evidence.evidence_nonce_sha256
            ):
                raise PhysicalTransportRuntimeV4Error(
                    "RAW batch differs from the bound handshake evidence"
                )
            if terminal_read_outcome is not None:
                if used_initial:
                    raise PhysicalTransportRuntimeV4Error(
                        "terminal ingress cannot consume retained upgrade bytes"
                    )
                received_at = terminal_read_outcome.received_at
                received_ns = terminal_read_outcome.received_monotonic_ns
            elif used_initial:
                if pending is not self._initial_pending_raw_ingress_v49c:
                    raise PhysicalTransportRuntimeV4Error(
                        "owner changed the initial post-upgrade RAW capability"
                    )
                received_at = transition.post_sample.wall_after_at
                received_ns = transition.post_sample.boottime_after_ns
            else:
                read_clock = self._sample_active_clock(
                    context="V4.9D RAW read clock validation failed",
                    strictly_after_monotonic_ns=self._v49d_actor_clock_floor(actor),
                )
                received_at = read_clock.wall_after_at
                received_ns = read_clock.monotonic_after_ns

            raw = self._build_raw_ingress_v49d(
                actor=actor,
                pending=pending,
                received_at=received_at,
                received_monotonic_ns=received_ns,
            )
            if terminal_read_outcome is None:
                await actor.commit_and_adopt_raw_ingress_v49d(raw)
            else:
                assert terminal_command_event is not None
                await actor.commit_and_adopt_terminal_raw_ingress_v49e(
                    terminal_command_event,
                    terminal_read_outcome,
                    raw,
                    signer=self._signer,
                )
            raw_event = actor.events[-1]
            raw_payload = raw_event.payload
            if (
                raw_event.event_kind
                is not TransportActorEventKindV49C.RAW_INGRESS_COMMITTED
                or type(raw_payload) is not RawIngressCommittedPayloadV49C
                or raw_payload.raw_ingress_commit_id != raw.raw_ingress_commit_id
            ):
                raise PhysicalTransportRuntimeV4Error(
                    "actor did not adopt the exact durable RAW event"
                )
            adopted = await owner.adopt_durable_ingress_v49d(raw)
            if (
                type(adopted) is not DurableIngressAdoptionV49D
                or adopted.raw_ingress_commit_id != raw.raw_ingress_commit_id
                or adopted.ingress_sequence != raw.ingress_sequence
                or adopted.adopted_octets != pending.total_octets
            ):
                raise PhysicalTransportRuntimeV4Error(
                    "owner adopted different durable RAW authority"
                )
            if used_initial:
                self._initial_pending_raw_ingress_v49c = None

            committed_chunks: list[CommittedRawChunkV49C] = []
            raw_local_start = 0
            for chunk in pending.chunks:
                committed_chunks.append(
                    CommittedRawChunkV49C(
                        raw_ingress_commit_id=raw.raw_ingress_commit_id,
                        projection_receipt_sequence=(
                            raw_payload.receipt.global_sequence
                        ),
                        projection_receipt_hash=raw_payload.receipt.receipt_hash,
                        raw_local_start_octet=raw_local_start,
                        stream_start_octet=(
                            raw_payload.stream_start_octet + raw_local_start
                        ),
                        data=chunk,
                    )
                )
                raw_local_start += len(chunk)

            new_chunks: tuple[CommittedRawChunkV49C, ...] = tuple(committed_chunks)
            while True:
                delineated = delineate_next_server_frame_v49c(
                    prior_tail=tail,
                    committed_raw_chunks=new_chunks,
                )
                new_chunks = ()
                parsed = await owner.parse_next_durable_unit_v49d()
                if delineated.unit is None:
                    if parsed is not None:
                        raise PhysicalTransportRuntimeV4Error(
                            "driver parsed an independently incomplete RAW prefix"
                        )
                    tail = delineated.retained_tail
                    self._retained_ingress_tail_v49d = tail
                    break
                if type(parsed) is not ParsedDurableUnitV49D:
                    raise PhysicalTransportRuntimeV4Error(
                        "driver did not parse one independently complete unit"
                    )
                unit = delineated.unit
                expected_unit = (
                    unit.frame_bytes
                    if type(unit) is DelineatedServerFrameV49C
                    else unit.examined_bytes
                )
                if (
                    parsed.consumed_unit != expected_unit
                    or parsed.consumed_octets != len(expected_unit)
                    or parsed.consumed_unit_sha256
                    != hashlib.sha256(expected_unit).hexdigest()
                    or parsed.remaining_durable_octets
                    != delineated.retained_tail.total_octets
                    or parsed.protocol_output_chunks_sha256
                    != tuple(
                        hashlib.sha256(chunk).hexdigest()
                        for chunk in parsed.protocol_output_chunks
                    )
                ):
                    raise PhysicalTransportRuntimeV4Error(
                        "driver parser result differs from RAW delineation"
                    )
                expected_output_batch = (
                    None
                    if not parsed.protocol_output_chunks
                    else sha256_digest(
                        {
                            "domain": ("RiskYieldMMActorOrderedProtocolOutputV4_9C"),
                            "ordered_chunks_base64": [
                                base64.b64encode(chunk).decode("ascii")
                                for chunk in parsed.protocol_output_chunks
                            ],
                        }
                    )
                )
                if parsed.protocol_output_batch_sha256 != expected_output_batch:
                    raise PhysicalTransportRuntimeV4Error(
                        "driver automatic-output commitment is noncanonical"
                    )

                parser_failed = parsed.parser_exception_class is not None
                if parser_failed != (parsed.parser_exception_message is not None):
                    raise PhysicalTransportRuntimeV4Error(
                        "driver parser exception metadata is incomplete"
                    )
                if type(unit) is FrameDelineationErrorV49C:
                    if not parser_failed or parsed.frame_event is not None:
                        raise PhysicalTransportRuntimeV4Error(
                            "structural error wasn't rejected by the pinned parser"
                        )
                    feed_kind = ParserFeedUnitKindV49C.PARSER_ERROR
                    error_kind = unit.error_kind
                    frame_metadata = None
                    error_offset = unit.error_stream_offset
                elif parser_failed:
                    if parsed.frame_event is not None:
                        raise PhysicalTransportRuntimeV4Error(
                            "semantic parser failure also exposed a frame event"
                        )
                    feed_kind = ParserFeedUnitKindV49C.PARSER_ERROR
                    error_kind = (
                        ParserErrorKindV49C.INVALID_CLOSE
                        if unit.metadata.opcode is WebSocketOpcodeV49C.CLOSE
                        else ParserErrorKindV49C.INVALID_TEXT
                        if parsed.parser_exception_class.endswith(".UnicodeDecodeError")
                        else ParserErrorKindV49C.PROTOCOL_STATE
                    )
                    frame_metadata = None
                    error_offset = unit.metadata.stream_start_octet
                else:
                    frame_event = parsed.frame_event
                    expected_opcode = {
                        WebSocketOpcodeV49C.CONTINUATION: 0x0,
                        WebSocketOpcodeV49C.TEXT: 0x1,
                        WebSocketOpcodeV49C.BINARY: 0x2,
                        WebSocketOpcodeV49C.CLOSE: 0x8,
                        WebSocketOpcodeV49C.PING: 0x9,
                        WebSocketOpcodeV49C.PONG: 0xA,
                    }[unit.metadata.opcode]
                    if (
                        frame_event is None
                        or frame_event.opcode != expected_opcode
                        or frame_event.fin is not unit.metadata.fin
                        or frame_event.payload != unit.payload
                    ):
                        raise PhysicalTransportRuntimeV4Error(
                            "pinned parser frame differs from independent RAW frame"
                        )
                    feed_kind = ParserFeedUnitKindV49C.COMPLETE_FRAME
                    error_kind = None
                    frame_metadata = unit.metadata
                    error_offset = None

                prior_fragment_event_ids = (
                    self._fragmented_message_parser_event_ids_v49e
                )
                after_cursor, fragment_bytes, completed_message = (
                    self._advance_parser_cursor_v49d(unit=unit, parsed=parsed)
                )
                parse_clock = self._sample_active_clock(
                    context="V4.9D parser clock validation failed",
                    strictly_after_monotonic_ns=self._v49d_actor_clock_floor(actor),
                )
                parser_payload = ParserTransitionPayloadV49C(
                    cursor_before=self._parser_cursor_v49d,
                    cursor_after=after_cursor,
                    feed_unit_kind=feed_kind,
                    source_slices=unit.source_slices,
                    frame=frame_metadata,
                    parser_error=(
                        None
                        if error_kind is None
                        else ParserErrorMetadataV49C(
                            error_kind=error_kind,
                            error_stream_offset=error_offset,
                            exception_class_digest=hashlib.sha256(
                                parsed.parser_exception_class.encode("utf-8")
                            ).hexdigest(),
                            exception_message_digest=hashlib.sha256(
                                parsed.parser_exception_message.encode("utf-8")
                            ).hexdigest(),
                        )
                    ),
                    ordered_protocol_output_chunks_base64=tuple(
                        base64.b64encode(chunk).decode("ascii")
                        for chunk in parsed.protocol_output_chunks
                    ),
                    ordered_protocol_output_chunks_sha256=(
                        parsed.protocol_output_chunks_sha256
                    ),
                    protocol_output_batch_sha256=(parsed.protocol_output_batch_sha256),
                    send_eof_after_output=parsed.send_eof_after_output,
                    processed_at=parse_clock.wall_after_at,
                    processed_monotonic_ns=parse_clock.monotonic_after_ns,
                )
                parser_event = await actor.append_parser_transition_v49d(parser_payload)
                parser_event_ids.append(parser_event.transport_actor_event_id)
                self._parser_cursor_v49d = after_cursor
                self._fragmented_message_bytes_v49d = fragment_bytes
                tail = delineated.retained_tail
                self._retained_ingress_tail_v49d = tail

                completed_application: _CompletedApplicationMessageV49E | None = None
                if completed_message is not None:
                    completed_opcode, completed_payload = completed_message
                    received_at, received_monotonic_ns = (
                        self._last_contributing_raw_receipt_v49e(
                            actor=actor,
                            source_slices=unit.source_slices,
                        )
                    )
                    source_ids = (
                        (
                            *prior_fragment_event_ids,
                            parser_event.transport_actor_event_id,
                        )
                        if unit.metadata.opcode is WebSocketOpcodeV49C.CONTINUATION
                        else (parser_event.transport_actor_event_id,)
                    )
                    completed_application = _CompletedApplicationMessageV49E(
                        source_parser_event_ids=source_ids,
                        websocket_opcode=completed_opcode.value,
                        payload=completed_payload,
                        received_at=received_at,
                        received_monotonic_ns=received_monotonic_ns,
                    )
                    self._fragmented_message_parser_event_ids_v49e = ()
                elif (
                    parsed.parser_exception_class is not None
                    or unit.metadata.opcode is WebSocketOpcodeV49C.CLOSE
                ):
                    self._fragmented_message_parser_event_ids_v49e = ()
                elif unit.metadata.opcode in {
                    WebSocketOpcodeV49C.TEXT,
                    WebSocketOpcodeV49C.BINARY,
                    WebSocketOpcodeV49C.CONTINUATION,
                }:
                    self._fragmented_message_parser_event_ids_v49e = (
                        *prior_fragment_event_ids,
                        parser_event.transport_actor_event_id,
                    )

                if completed_application is not None:
                    await self._commit_completed_application_message_v49e_locked(
                        actor=actor,
                        message=completed_application,
                        parser_event=parser_event,
                        admission_grant_v49f=admission_grant_v49f,
                        admission_kind_v49f=admission_kind_v49f,
                    )

                if parsed.protocol_output_chunks:
                    output_opcode, output_payload = (
                        _decode_single_automatic_protocol_output_v49c(
                            parsed.protocol_output_chunks
                        )
                    )
                    completion_event_id = (
                        await self._dispatch_automatic_protocol_output_v49d_locked(
                            actor=actor,
                            owner=owner,
                            parser_event=parser_event,
                            admission_grant_v49f=admission_grant_v49f,
                            admission_kind_v49f=admission_kind_v49f,
                        )
                    )
                    automatic_output_source_parser_event_ids.append(
                        parser_event.transport_actor_event_id
                    )
                    completion_event_ids.append(completion_event_id)
                    automatic_output_chunks.extend(parsed.protocol_output_chunks)
                    automatic_output_wire_chunk_counts.append(
                        len(parsed.protocol_output_chunks)
                    )
                    automatic_output_frames.append(
                        (output_opcode.value, output_payload)
                    )
                if after_cursor.websocket_state is not WebSocketParserStateV49C.OPEN:
                    break
                if tail.total_octets == 0:
                    break

            self._assert_lease()
            self._assert_socket_owner(context="after V4.9D RAW ingress")
            self._assert_application_fence(context="after V4.9D RAW ingress")
            return PhysicalTransportIngressProgressV49D(
                raw_ingress_commit_id=raw.raw_ingress_commit_id,
                ingress_sequence=raw.ingress_sequence,
                committed_raw_octets=pending.total_octets,
                raw_ingress_batch_sha256=raw.raw_ingress_batch_sha256,
                parser_event_ids=tuple(parser_event_ids),
                automatic_output_source_parser_event_ids=tuple(
                    automatic_output_source_parser_event_ids
                ),
                automatic_dispatch_completion_event_ids=tuple(completion_event_ids),
                automatic_protocol_output_chunks=tuple(automatic_output_chunks),
                automatic_output_wire_chunk_counts=tuple(
                    automatic_output_wire_chunk_counts
                ),
                automatic_protocol_output_frames=tuple(automatic_output_frames),
                actor_event_count_before=event_count_before,
                actor_tail_event_id_before=actor_tail_event_id_before,
                actor_event_count_after=actor.event_count_v49f,
                actor_tail_event_id_after=actor.tail_event_id_v49f,
                retained_incomplete_octets=tail.total_octets,
                used_initial_pending_ingress=used_initial,
                websocket_parser_state=(self._parser_cursor_v49d.websocket_state.value),
                admission_policy_id_v49f=(
                    None
                    if admission_grant_v49f is None
                    else admission_grant_v49f.policy_id
                ),
                admission_epoch_v49f=(
                    None
                    if admission_grant_v49f is None
                    else admission_grant_v49f.admission_epoch
                ),
                admission_sequence_v49f=(
                    None
                    if admission_grant_v49f is None
                    else admission_grant_v49f.admission_sequence
                ),
                admission_queue_wait_nanoseconds_v49f=(
                    None
                    if admission_grant_v49f is None
                    else admission_grant_v49f.queue_wait_nanoseconds
                ),
                admission_command_kind_v49f=(
                    None
                    if admission_grant_v49f is None
                    else admission_grant_v49f.command_kind.value
                ),
                admission_reservation_work_units_v49f=(
                    None
                    if admission_grant_v49f is None
                    else admission_grant_v49f.reservation_work_units
                ),
                admission_admitted_loop_time_ns_v49f=(
                    None
                    if admission_grant_v49f is None
                    else admission_grant_v49f.admitted_loop_time_ns
                ),
                admission_started_loop_time_ns_v49f=(
                    None
                    if admission_grant_v49f is None
                    else admission_grant_v49f.started_loop_time_ns
                ),
                admission_start_deadline_loop_time_ns_v49f=(
                    None
                    if admission_grant_v49f is None
                    else admission_grant_v49f.start_deadline_loop_time_ns
                ),
            )
        except BaseException as exc:
            if terminal_command_event is not None:
                # The enclosing durable shutdown command is the sole final
                # writer.  Its actor API has either committed a decisive pair
                # already or retained the exact failure for the outer command
                # to classify.  Never reclassify it as automatic-output UNKNOWN.
                raise
            terminal_convergence = actor.last_terminal_convergence_v49e
            if terminal_convergence is not None:
                # A Close write may fail only after the actor has atomically
                # classified its exact pending attempt and signed the legacy
                # bridge.  Preserve that stronger durable fact instead of
                # downgrading the runtime to an unpaired generic fault.
                termination = self._adopt_actor_terminal_convergence_v49e(
                    terminal_convergence,
                    actor=actor,
                    owner=owner,
                    require_clean=False,
                )
                if isinstance(
                    exc, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)
                ):
                    raise
                if isinstance(exc, PhysicalTransportProviderIntegrityFailureV49E):
                    raise
                from .physical_transport_terminal_v49c import (
                    TerminalOutcomeV49C,
                    TerminalTransitionPayloadV49C,
                )

                terminal_event = terminal_convergence.terminal_event
                terminal_payload = terminal_event.payload
                outcome = actor.terminal_state.terminal_outcome
                if (
                    type(terminal_payload) is not TerminalTransitionPayloadV49C
                    or outcome is None
                ):
                    raise PhysicalTransportRuntimeV4FaultLatched(
                        "automatic Close convergence lost its exact terminal payload"
                    ) from exc
                has_attempt = terminal_payload.send_attempt_id is not None
                if outcome is TerminalOutcomeV49C.UNKNOWN_SEND:
                    raise PhysicalTransportDispatchUnknownV4(
                        "V4.9E automatic Close has a paired UNKNOWN_SEND outcome"
                    ) from exc
                raise PhysicalTransportAutomaticCloseTerminalFailureV49E(
                    termination=termination,
                    terminal_outcome=outcome.value,
                    cause_code=terminal_payload.cause_code,
                    kernel_send_attempt_recorded=has_attempt,
                ) from exc
            unresolved_attempt_event_id = (
                actor.unresolved_kernel_send_attempt_event_id_v49f
            )
            pending_wire_event_id = actor.oldest_outbound_wire_event_id
            current_wire_result_event_ids: tuple[str, ...] = ()
            if pending_wire_event_id is not None:
                # Classify only evidence belonging to the current incomplete
                # FIFO head.  A completed Pong earlier in this same ingress
                # operation must not make a later parser failure look like a
                # post-send failure, while a positive result whose dispatch
                # completion append failed must not be called pre-attempt.
                from .physical_transport_actor_v49c import (
                    KernelSendResultPayloadV49C,
                    TlsCiphertextPreparedPayloadV49C,
                )

                current_wire_tls_event_ids = {
                    event.transport_actor_event_id
                    for event in actor.events
                    if event.event_kind
                    is TransportActorEventKindV49C.TLS_CIPHERTEXT_PREPARED
                    and type(event.payload) is TlsCiphertextPreparedPayloadV49C
                    and event.payload.outbound_wire_prepared_event_id
                    == pending_wire_event_id
                }
                current_wire_result_event_ids = tuple(
                    event.transport_actor_event_id
                    for event in actor.events
                    if event.event_kind
                    is TransportActorEventKindV49C.KERNEL_SEND_RESULT
                    and type(event.payload) is KernelSendResultPayloadV49C
                    and event.payload.tls_ciphertext_prepared_event_id
                    in current_wire_tls_event_ids
                )
            self._abort_owner_best_effort(owner)
            if self._state not in {
                PhysicalTransportRuntimeStateV4.FENCED,
                PhysicalTransportRuntimeStateV4.FAULT_LATCHED,
                PhysicalTransportRuntimeStateV4.CLOSED,
            }:
                self._fault_cause = f"V4.9D causal ingress failed: {type(exc).__name__}"
                self._state = PhysicalTransportRuntimeStateV4.FAULT_LATCHED
            if isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)):
                raise
            if isinstance(exc, PhysicalTransportProviderIntegrityFailureV49E):
                raise
            if unresolved_attempt_event_id is not None:
                raise PhysicalTransportDispatchUnknownV4(
                    "V4.9D automatic output failed with an unresolved durable "
                    "kernel attempt for the current outbound wire; peer delivery "
                    "is unknown and the owner was fenced"
                ) from exc
            if current_wire_result_event_ids:
                raise PhysicalTransportRuntimeV4FaultLatched(
                    "V4.9D automatic output failed after a conclusive kernel "
                    "send result for the current outbound wire but before "
                    "authoritative dispatch completion; the owner was fenced"
                ) from exc
            raise PhysicalTransportRuntimeV4FaultLatched(
                "V4.9D ingress failed before any durable kernel attempt belonging "
                "to a current incomplete outbound wire; the owner was fenced"
            ) from exc

    def _latest_terminal_marker_v49e(
        self,
        actor: Any,
        *,
        kinds: frozenset[Any],
        obligation_layer: Any | None = None,
    ) -> Any:
        """Return the newest exact retained terminal marker in one closed set."""

        from .physical_transport_actor_v49c import TransportActorEventKindV49C
        from .physical_transport_terminal_v49c import TerminalTransitionPayloadV49C

        matches = tuple(
            event
            for event in actor.events
            if event.event_kind is TransportActorEventKindV49C.TERMINAL_TRANSITION
            and type(event.payload) is TerminalTransitionPayloadV49C
            and event.payload.kind in kinds
            and (
                obligation_layer is None
                or event.payload.obligation_layer is obligation_layer
            )
        )
        if not matches:
            raise PhysicalTransportRuntimeV4StateError(
                "V4.9E shutdown lacks its exact causal terminal marker"
            )
        return max(matches, key=lambda event: event.actor_sequence)

    async def _send_local_websocket_close_v49e_locked(
        self,
        *,
        actor: Any,
        owner: Any,
        command_event: Any,
        driver_evidence_nonce_sha256: str,
        admission_grant_v49f: TransportAdmissionGrantV49F | None,
    ) -> None:
        """Submit the fixed local normal Close through the actor-owned FIFO."""

        self._assert_actor_admission_v49f(
            admission_grant_v49f,
            expected_kind=TransportCommandKindV49F.LOCAL_SHUTDOWN,
        )

        from .physical_transport_actor_v49c import (
            V49C_MAX_TLS_CIPHERTEXT_CHUNKS,
            KernelSendAttemptPayloadV49C,
            LocalShutdownCommandStartedPayloadV49E,
            OutboundDispatchCompletedPayloadV49C,
            TlsCiphertextPreparedPayloadV49C,
            TransportActorEventKindV49C,
            WebSocketParserCursorV49C,
            WebSocketParserStateV49C,
        )
        from .physical_transport_terminal_v49c import (
            TerminalTransitionKindV49C,
            TerminalTransitionPayloadV49C,
        )
        from .physical_transport_tls_v49 import (
            PreparedTlsCiphertextV49C,
            PreparedWebSocketWireV49C,
        )

        if (
            command_event.event_kind
            is not TransportActorEventKindV49C.LOCAL_SHUTDOWN_COMMAND_STARTED
            or type(command_event.payload) is not LocalShutdownCommandStartedPayloadV49E
            or actor.local_shutdown_command_event_v49e is not command_event
            or not actor.events
            or actor.events[-1] is not command_event
        ):
            raise PhysicalTransportRuntimeV4Error(
                "local Close lacks the exact durable V4.9E shutdown command"
            )
        command = command_event.payload
        wire_holder: list[PreparedWebSocketWireV49C] = []

        async def prepare_local_close_wire(*, deadline_ns: int) -> Any:
            if deadline_ns != command.shutdown_deadline_monotonic_ns:
                raise PhysicalTransportRuntimeV4Error(
                    "actor changed the durable local Close preparation deadline"
                )
            prepared = await owner.prepare_local_websocket_close_wire_v49e(
                deadline_ns=deadline_ns
            )
            wire_holder.append(prepared)
            return prepared

        (
            wire_event,
            close_event,
            permit_event,
        ) = await actor.authorize_local_websocket_close_v49e(
            command_event,
            driver_evidence_nonce_sha256=driver_evidence_nonce_sha256,
            prepare_effect=prepare_local_close_wire,
            signer=self._signer,
        )
        if len(wire_holder) != 1:
            raise PhysicalTransportRuntimeV4Error(
                "actor didn't invoke exactly one local Close preparation effect"
            )
        wire = wire_holder[0]
        if (
            type(wire) is not PreparedWebSocketWireV49C
            or wire.logical_opcode != 0x8
            or wire.logical_payload_octets != 2
            or wire.logical_payload_sha256
            != hashlib.sha256((1000).to_bytes(2, "big")).hexdigest()
        ):
            raise PhysicalTransportRuntimeV4Error(
                "owner changed the fixed V4.9E normal Close wire"
            )
        cursor = self._parser_cursor_v49d
        if (
            close_event.event_kind
            is not TransportActorEventKindV49C.TERMINAL_TRANSITION
            or type(close_event.payload) is not TerminalTransitionPayloadV49C
            or close_event.payload.kind is not TerminalTransitionKindV49C.WS_CLOSE_SENT
            or type(cursor) is not WebSocketParserCursorV49C
            or cursor.websocket_state is not WebSocketParserStateV49C.OPEN
            or cursor.fragmented_message_opcode is not None
            or cursor.fragmented_message_octets != 0
            or cursor.fragmented_message_sha256 is not None
        ):
            raise PhysicalTransportRuntimeV4Error(
                "local Close authorization didn't durably close one idle parser"
            )
        # `websockets.send_close()` has already moved the retained sans-I/O
        # protocol into CLOSING.  Mirror that durable WS_CLOSE_SENT fact in the
        # runtime cursor without consuming bytes or inventing a parser event;
        # the actor-chain reducer independently derives the same state change.
        self._parser_cursor_v49d = WebSocketParserCursorV49C(
            cursor_sequence=cursor.cursor_sequence,
            next_stream_octet=cursor.next_stream_octet,
            websocket_state=WebSocketParserStateV49C.CLOSING,
        )
        ciphertext_holder: list[PreparedTlsCiphertextV49C] = []

        async def prepare_local_close_tls(*, deadline_ns: int) -> Any:
            if deadline_ns != command.shutdown_deadline_monotonic_ns:
                raise PhysicalTransportRuntimeV4Error(
                    "actor changed the durable local Close TLS deadline"
                )
            prepared = await owner.prepare_tls_ciphertext_v49c(
                wire,
                deadline_ns=deadline_ns,
            )
            ciphertext_holder.append(prepared)
            return prepared

        tls_event = await actor.prepare_local_close_tls_ciphertext_v49e(
            command_event,
            wire_event,
            permit_event,
            driver_evidence_nonce_sha256=driver_evidence_nonce_sha256,
            prepare_effect=prepare_local_close_tls,
            signer=self._signer,
        )
        if len(ciphertext_holder) != 1:
            raise PhysicalTransportRuntimeV4Error(
                "actor didn't invoke exactly one local Close TLS effect"
            )
        ciphertext = ciphertext_holder[0]
        if (
            type(ciphertext) is not PreparedTlsCiphertextV49C
            or ciphertext.prepared_wire is not wire
            or ciphertext.plaintext_batch_sha256 != wire.wire_batch_sha256
            or ciphertext.plaintext_octets != wire.wire_octets
        ):
            raise PhysicalTransportRuntimeV4Error(
                "owner TLS artifact differs from the fixed local Close"
            )
        if (
            tls_event.event_kind
            is not TransportActorEventKindV49C.TLS_CIPHERTEXT_PREPARED
            or type(tls_event.payload) is not TlsCiphertextPreparedPayloadV49C
            or tls_event.payload.outbound_wire_prepared_event_id
            != wire_event.transport_actor_event_id
            or tls_event.payload.write_permit_consumed_event_id
            != permit_event.transport_actor_event_id
            or tls_event.payload.ciphertext_batch_sha256
            != ciphertext.ciphertext_batch_sha256
            or tls_event.payload.ciphertext_octets != ciphertext.ciphertext_octets
        ):
            raise PhysicalTransportRuntimeV4Error(
                "actor changed the exact local Close TLS artifact"
            )

        submitted = 0
        positive_results = 0
        while submitted < ciphertext.ciphertext_octets:
            if positive_results >= V49C_MAX_TLS_CIPHERTEXT_CHUNKS:
                raise PhysicalTransportRuntimeV4Error(
                    "local Close positive-send result bound was exhausted"
                )

            async def exact_owner_send(
                exact_slice: bytes,
                *,
                deadline_ns: int,
            ) -> int:
                if deadline_ns != command.shutdown_deadline_monotonic_ns:
                    raise PhysicalTransportRuntimeV4Error(
                        "actor changed the durable local Close send deadline"
                    )
                return await owner.send_prepared_tls_ciphertext_once_v49c(
                    exact_slice,
                    prepared=ciphertext,
                    deadline_ns=deadline_ns,
                )

            outcome = await actor.send_oldest_ciphertext(
                send_effect=exact_owner_send,
                terminal_signer=self._signer,
            )
            if type(outcome.attempt_event.payload) is not KernelSendAttemptPayloadV49C:
                raise PhysicalTransportRuntimeV4Error(
                    "actor returned an unsupported local Close kernel attempt"
                )
            submitted += outcome.accepted_octets
            positive_results += 1

        completed = await actor.complete_oldest_dispatch_from_chain()
        payload = completed.payload
        if (
            completed.event_kind
            is not TransportActorEventKindV49C.OUTBOUND_DISPATCH_COMPLETED
            or type(payload) is not OutboundDispatchCompletedPayloadV49C
            or payload.outbound_wire_prepared_event_id
            != wire_event.transport_actor_event_id
            or payload.submitted_ciphertext_octets != ciphertext.ciphertext_octets
        ):
            raise PhysicalTransportRuntimeV4Error(
                "actor returned an unsupported local Close completion"
            )

    async def shutdown_current_v49e(
        self, *, timeout_seconds: int = 10
    ) -> TransportSessionTerminationV4:
        """Causally close WebSocket, TLS, and TCP under one frozen deadline.

        The command intentionally exposes only a bounded timeout.  Close code,
        reason, socket, TLS artifacts, and effect callbacks remain owner-derived
        capabilities.  Every decisive actor outcome is atomically paired with
        the existing signed session-termination projection before I/O authority
        is released.
        """

        timeout = canonical_safe_int(
            timeout_seconds,
            field="timeout_seconds",
            minimum=1,
            maximum=300,
        )
        async with self._admit_actor_command_v49f(
            TransportCommandKindV49F.LOCAL_SHUTDOWN
        ) as admission_grant_v49f:
            self._require_state(
                PhysicalTransportRuntimeStateV4.SESSION_COMMITTED,
                PhysicalTransportRuntimeStateV4.AWAITING_ACK,
                PhysicalTransportRuntimeStateV4.ACK_BOUND,
            )

            from .physical_transport_actor_v49c import (
                LocalShutdownCommandStartedPayloadV49E,
                TlsControlCiphertextPreparedPayloadV49E,
                TlsControlOutputKindV49E,
                TlsProtocolOperationPurposeV49E,
                TransportActorEventKindV49C,
                TransportActorEventV49C,
                WebSocketParserStateV49C,
            )
            from .physical_transport_linux_v4 import (
                DriverHandshakeTransitionV49B,
                LinuxSocketOwnerV4,
            )
            from .physical_transport_session_actor_v49c import (
                LocalShutdownCommandClockDisagreementV49E,
                LocalShutdownCommandDeadlineDueV49E,
                PhysicalTransportSessionActorV49C,
                TlsShutdownObservationOutcomeV49E,
            )
            from .physical_transport_terminal_v49c import (
                OutboundObligationLayerV49C,
                TerminalOutcomeV49C,
                TerminalTransitionKindV49C,
                TerminalTransitionPayloadV49C,
            )
            from .physical_transport_tls_v49 import (
                PreparedTlsControlCiphertextV49E,
            )

            actor = self._transport_session_actor_v49c
            owner = self._socket_owner
            transition = self._driver_handshake_transition_v49c
            tail = self._retained_ingress_tail_v49d
            cursor = self._parser_cursor_v49d
            if (
                type(actor) is not PhysicalTransportSessionActorV49C
                or type(owner) is not LinuxSocketOwnerV4
                or type(transition) is not DriverHandshakeTransitionV49B
                or self._transport_actor_activation_v49c_in_progress
            ):
                raise PhysicalTransportRuntimeV4StateError(
                    "V4.9E shutdown requires one activated exact actor and owner"
                )
            state = actor.terminal_state
            if (
                actor.is_fault_latched
                or state.is_terminal
                or actor.last_terminal_convergence_v49e is not None
                or actor.oldest_outbound_wire_event_id is not None
                or actor.has_pending_automatic_protocol_output
                or state.pending_send_attempt_id is not None
            ):
                raise PhysicalTransportRuntimeV4StateError(
                    "V4.9E shutdown requires one quiescent nonterminal actor"
                )
            if (
                tail is None
                or cursor is None
                or tail.total_octets != 0
                or self._initial_pending_raw_ingress_v49c is not None
                or self._fragmented_message_bytes_v49d
                or self._fragmented_message_parser_event_ids_v49e
            ):
                raise PhysicalTransportRuntimeV4StateError(
                    "V4.9E shutdown cannot bypass retained or fragmented ingress"
                )
            peer_first = (
                state.ws_close_sent
                and state.ws_close_received
                and state.ws_output_fully_kernel_accepted
            )
            if (
                any(
                    (
                        state.ws_close_sent,
                        state.ws_close_received,
                        state.ws_output_fully_kernel_accepted,
                    )
                )
                and not peer_first
            ):
                raise PhysicalTransportRuntimeV4StateError(
                    "V4.9E shutdown found an incomplete WebSocket Close prefix"
                )
            expected_parser_state = (
                WebSocketParserStateV49C.CLOSING
                if peer_first
                else WebSocketParserStateV49C.OPEN
            )
            if cursor.websocket_state is not expected_parser_state:
                raise PhysicalTransportRuntimeV4StateError(
                    "V4.9E parser state differs from durable Close evidence"
                )
            if any(
                (
                    state.tls_close_notify_sent,
                    state.tls_close_notify_received,
                    state.tls_close_notify_fully_kernel_accepted,
                    state.tcp_fin_sent,
                    state.tcp_eof_received,
                )
            ):
                raise PhysicalTransportRuntimeV4StateError(
                    "V4.9E shutdown cannot resume a partially applied TLS/TCP prefix"
                )

            try:
                self._assert_lease()
                self._assert_socket_owner(context="before V4.9E shutdown")
                self._assert_application_fence(context="before V4.9E shutdown")
            except BaseException:
                # Lost writer, socket, or application-fence authority cannot
                # leave a still-live owner behind for a second caller.
                self._abort_owner_best_effort(owner)
                raise

            def exact_durable_shutdown_command(candidate: Any) -> bool:
                return (
                    type(candidate) is TransportActorEventV49C
                    and candidate.event_kind
                    is TransportActorEventKindV49C.LOCAL_SHUTDOWN_COMMAND_STARTED
                    and type(candidate.payload)
                    is LocalShutdownCommandStartedPayloadV49E
                    and actor.local_shutdown_command_event_v49e is candidate
                    and bool(actor.events)
                    and actor.events[-1] is candidate
                )

            def commit_barrier_if_durable(candidate: Any) -> None:
                if admission_grant_v49f is not None and exact_durable_shutdown_command(
                    candidate
                ):
                    assert self._transport_admission_gate_v49f is not None
                    self._transport_admission_gate_v49f.commit_terminal_barrier(
                        admission_grant_v49f
                    )

            try:
                try:
                    command_event = await actor.start_local_shutdown_command_v49e(
                        timeout_seconds=timeout
                    )
                except BaseException:
                    commit_barrier_if_durable(actor.local_shutdown_command_event_v49e)
                    raise
                if not exact_durable_shutdown_command(command_event):
                    commit_barrier_if_durable(actor.local_shutdown_command_event_v49e)
                    raise PhysicalTransportRuntimeV4Error(
                        "actor substituted the durable local shutdown command"
                    )
                commit_barrier_if_durable(command_event)
                command = command_event.payload
                if (
                    command.websocket_close_code != 1000
                    or command.websocket_close_reason_sha256
                    != hashlib.sha256(b"").hexdigest()
                    or command.websocket_close_reason_octets != 0
                    or command.websocket_close_payload_sha256
                    != hashlib.sha256((1000).to_bytes(2, "big")).hexdigest()
                    or command.websocket_close_payload_octets != 2
                    or command.timeout_seconds != timeout
                    or command.started_at != command_event.recorded_at
                    or command.started_monotonic_ns
                    != command_event.recorded_monotonic_ns
                    or command.shutdown_deadline_at
                    != command.started_at + timedelta(seconds=timeout)
                    or command.shutdown_deadline_monotonic_ns
                    != command.started_monotonic_ns + timeout * 10**9
                ):
                    raise PhysicalTransportRuntimeV4Error(
                        "actor changed the fixed V4.9E shutdown command"
                    )
            except BaseException as exc:
                self._abort_owner_best_effort(owner)
                self._fault_cause = (
                    "V4.9E durable shutdown command outcome is unusable: "
                    f"{type(exc).__name__}"
                )
                self._state = PhysicalTransportRuntimeStateV4.FAULT_LATCHED
                if isinstance(
                    exc, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)
                ):
                    raise
                raise PhysicalTransportRuntimeV4FaultLatched(
                    "V4.9E shutdown cannot mutate its owner without one exact "
                    "durable command"
                ) from exc

            try:
                if not peer_first:
                    await self._send_local_websocket_close_v49e_locked(
                        actor=actor,
                        owner=owner,
                        command_event=command_event,
                        driver_evidence_nonce_sha256=(
                            transition.evidence.evidence_nonce_sha256
                        ),
                        admission_grant_v49f=admission_grant_v49f,
                    )

                while not actor.terminal_state.ws_close_received:
                    await self._process_next_ingress_v49d_locked(
                        timeout_seconds=timeout,
                        terminal_close_command_event=command_event,
                        admission_grant_v49f=admission_grant_v49f,
                    )

                state = actor.terminal_state
                if not (
                    state.ws_close_sent
                    and state.ws_close_received
                    and state.ws_output_fully_kernel_accepted
                ):
                    raise PhysicalTransportRuntimeV4Error(
                        "WebSocket shutdown lacks complete actor evidence"
                    )
                websocket_cause = self._latest_terminal_marker_v49e(
                    actor,
                    kinds=frozenset(
                        {
                            TerminalTransitionKindV49C.WS_CLOSE_RECEIVED,
                            TerminalTransitionKindV49C.OUTBOUND_OBLIGATION_FULLY_KERNEL_ACCEPTED,
                        }
                    ),
                    obligation_layer=None,
                )
                # The generic FULLY_ACCEPTED transition also exists for TLS;
                # at this point TLS hasn't started, and the explicit assertion
                # below makes the intended WebSocket cause unambiguous.
                if type(
                    websocket_cause.payload
                ) is not TerminalTransitionPayloadV49C or (
                    websocket_cause.payload.kind
                    is TerminalTransitionKindV49C.OUTBOUND_OBLIGATION_FULLY_KERNEL_ACCEPTED
                    and websocket_cause.payload.obligation_layer
                    is not OutboundObligationLayerV49C.WEBSOCKET_CLOSE
                ):
                    raise PhysicalTransportRuntimeV4Error(
                        "local TLS start lacks the latest exact WebSocket marker"
                    )

                tls_operation = await actor.start_tls_protocol_operation_v49e(
                    command_event,
                    purpose=TlsProtocolOperationPurposeV49E.LOCAL_CLOSE_NOTIFY,
                    cause_event=websocket_cause,
                    driver_evidence_nonce_sha256=(
                        transition.evidence.evidence_nonce_sha256
                    ),
                )
                prepared_holder: list[PreparedTlsControlCiphertextV49E] = []

                async def prepare_local_tls_control(
                    *, deadline_ns: int
                ) -> PreparedTlsControlCiphertextV49E:
                    if deadline_ns != command.shutdown_deadline_monotonic_ns:
                        raise PhysicalTransportRuntimeV4Error(
                            "actor changed the local TLS preparation deadline"
                        )
                    prepared = await owner.prepare_local_close_notify_v49e(
                        deadline_ns=deadline_ns
                    )
                    prepared_holder.append(prepared)
                    return prepared

                control_event, _ = await actor.complete_tls_control_preparation_v49e(
                    tls_operation,
                    prepare_effect=prepare_local_tls_control,
                    signer=self._signer,
                )
                if len(prepared_holder) != 1:
                    raise PhysicalTransportRuntimeV4Error(
                        "local TLS preparation didn't retain one exact capability"
                    )
                prepared_control = prepared_holder[0]
                control_payload = control_event.payload
                if (
                    type(prepared_control) is not PreparedTlsControlCiphertextV49E
                    or type(control_payload)
                    is not TlsControlCiphertextPreparedPayloadV49E
                    or control_payload.control_kind
                    is not TlsControlOutputKindV49E.LOCAL_CLOSE_NOTIFY
                ):
                    raise PhysicalTransportRuntimeV4Error(
                        "local TLS preparation returned unsupported evidence"
                    )

                submitted = 0
                positive_results = 0
                while submitted < prepared_control.ciphertext_octets:
                    if positive_results >= 256:
                        raise PhysicalTransportRuntimeV4Error(
                            "TLS close_notify positive-send bound was exhausted"
                        )

                    async def exact_tls_control_send(
                        exact_slice: bytes,
                        *,
                        deadline_ns: int,
                    ) -> int:
                        if deadline_ns != command.shutdown_deadline_monotonic_ns:
                            raise PhysicalTransportRuntimeV4Error(
                                "actor changed the local TLS send deadline"
                            )
                        return (
                            await owner.send_prepared_tls_control_ciphertext_once_v49e(
                                exact_slice,
                                prepared=prepared_control,
                                deadline_ns=deadline_ns,
                            )
                        )

                    outcome = await actor.send_tls_control_ciphertext_v49e(
                        control_event,
                        prepared_control,
                        send_effect=exact_tls_control_send,
                        signer=self._signer,
                    )
                    submitted += outcome.accepted_octets
                    positive_results += 1

                tcp_marker = await actor.half_close_tcp_write_v49e(
                    command_event,
                    control_event,
                    prepared_control,
                    prepare_token_effect=(
                        lambda *, deadline_ns: (
                            owner.prepare_tcp_write_shutdown_token_v49e(
                                prepared_control,
                                deadline_ns=deadline_ns,
                            )
                        )
                    ),
                    shutdown_effect=(
                        lambda token, *, deadline_ns: owner.shutdown_tcp_write_v49e(
                            token,
                            deadline_ns=deadline_ns,
                        )
                    ),
                    signer=self._signer,
                )
                convergence = actor.last_terminal_convergence_v49e
                if convergence is not None:
                    return self._adopt_actor_terminal_convergence_v49e(
                        convergence,
                        actor=actor,
                        owner=owner,
                        require_clean=False,
                    )
                if (
                    tcp_marker.event_kind
                    is not TransportActorEventKindV49C.TERMINAL_TRANSITION
                    or type(tcp_marker.payload) is not TerminalTransitionPayloadV49C
                    or tcp_marker.payload.kind
                    is not TerminalTransitionKindV49C.TCP_FIN_SENT
                ):
                    raise PhysicalTransportRuntimeV4Error(
                        "successful SHUT_WR lacks the exact TCP_FIN_SENT marker"
                    )

                # The sealed owner can contribute at most the two still-missing
                # positive peer facts: authenticated TLS close_notify, then TCP
                # EOF.  Derive the bound from durable actor state and link each
                # follow-up poll to the immediately preceding observation.
                remaining_peer_facts = sum(
                    (
                        not actor.terminal_state.tls_close_notify_received,
                        not actor.terminal_state.tcp_eof_received,
                    )
                )
                poll_cause = tcp_marker
                for _ in range(remaining_peer_facts):
                    poll_operation = await actor.start_tls_protocol_operation_v49e(
                        command_event,
                        purpose=TlsProtocolOperationPurposeV49E.PEER_SHUTDOWN_POLL,
                        cause_event=poll_cause,
                        driver_evidence_nonce_sha256=(
                            transition.evidence.evidence_nonce_sha256
                        ),
                    )
                    observation = await actor.observe_tls_shutdown_v49e(
                        poll_operation,
                        observation_effect=(
                            lambda *, deadline_ns: owner.poll_tls_shutdown_v49e(
                                deadline_ns=deadline_ns
                            )
                        ),
                        signer=self._signer,
                    )
                    if type(observation) is not TlsShutdownObservationOutcomeV49E:
                        raise PhysicalTransportRuntimeV4Error(
                            "actor returned unsupported TLS shutdown evidence"
                        )
                    if observation.terminal_convergence is not None:
                        clean = (
                            actor.terminal_state.terminal_outcome
                            is TerminalOutcomeV49C.CLEAN_ALL_LAYERS
                        )
                        return self._adopt_actor_terminal_convergence_v49e(
                            observation.terminal_convergence,
                            actor=actor,
                            owner=owner,
                            require_clean=clean,
                        )
                    poll_cause = observation.marker_event
                raise PhysicalTransportRuntimeV4Error(
                    "bounded TLS shutdown observations did not converge"
                )
            except BaseException as exc:
                convergence = actor.last_terminal_convergence_v49e
                if convergence is not None:
                    termination = self._adopt_actor_terminal_convergence_v49e(
                        convergence,
                        actor=actor,
                        owner=owner,
                        require_clean=False,
                    )
                    if isinstance(
                        exc, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)
                    ):
                        raise
                    return termination
                if type(exc) is LocalShutdownCommandClockDisagreementV49E:
                    try:
                        convergence = (
                            await actor.converge_local_shutdown_clock_disagreement_v49e(
                                command_event,
                                exc,
                                signer=self._signer,
                            )
                        )
                    except BaseException as convergence_error:
                        self._abort_owner_best_effort(owner)
                        self._fault_cause = (
                            "V4.9E shutdown clock disagreement couldn't converge: "
                            f"{type(convergence_error).__name__}"
                        )
                        self._state = PhysicalTransportRuntimeStateV4.FAULT_LATCHED
                        raise PhysicalTransportRuntimeV4FaultLatched(
                            "V4.9E clock disagreement lacks its atomic terminal pair"
                        ) from exc
                    return self._adopt_actor_terminal_convergence_v49e(
                        convergence,
                        actor=actor,
                        owner=owner,
                        require_clean=False,
                    )
                if type(exc) is LocalShutdownCommandDeadlineDueV49E:
                    try:
                        convergence = await actor.expire_local_shutdown_command_v49e(
                            command_event,
                            signer=self._signer,
                        )
                    except BaseException as convergence_error:
                        self._abort_owner_best_effort(owner)
                        self._fault_cause = (
                            "V4.9E due shutdown command couldn't converge: "
                            f"{type(convergence_error).__name__}"
                        )
                        self._state = PhysicalTransportRuntimeStateV4.FAULT_LATCHED
                        raise PhysicalTransportRuntimeV4FaultLatched(
                            "V4.9E due command lacks its atomic terminal pair"
                        ) from exc
                    return self._adopt_actor_terminal_convergence_v49e(
                        convergence,
                        actor=actor,
                        owner=owner,
                        require_clean=False,
                    )
                try:
                    convergence = await actor.converge_terminal_v49e(
                        TerminalTransitionKindV49C.FATAL,
                        cause_code="V49E_SHUTDOWN_EFFECT_FAILURE",
                        signer=self._signer,
                    )
                except BaseException as convergence_error:
                    self._abort_owner_best_effort(owner)
                    self._fault_cause = (
                        "V4.9E shutdown failed without an atomic terminal pair: "
                        f"{type(exc).__name__}; convergence="
                        f"{type(convergence_error).__name__}"
                    )
                    self._state = PhysicalTransportRuntimeStateV4.FAULT_LATCHED
                    if isinstance(
                        exc, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)
                    ):
                        raise exc from convergence_error
                    raise PhysicalTransportRuntimeV4FaultLatched(
                        "V4.9E shutdown couldn't establish a signed terminal pair"
                    ) from exc
                termination = self._adopt_actor_terminal_convergence_v49e(
                    convergence,
                    actor=actor,
                    owner=owner,
                    require_clean=False,
                )
                if isinstance(
                    exc, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)
                ):
                    raise
                return termination

    async def dispatch_subscription_v49c(
        self, *, idempotency_key: str
    ) -> PhysicalTransportDispatchWindowV4:
        """Submit the privately retained subscription through the V4.9C actor.

        This method exposes only the durable-intent idempotency key: no sender,
        callback, socket, prepared artifact, or permit can be injected.  The
        exact V4.9B owner first prepares immutable WebSocket wire and TLS
        ciphertext.  The V4.9C actor durably records each boundary, writes
        ahead every kernel attempt, and records the exact positive local-
        acceptance count before the owner may advance again.

        Local kernel acceptance is not peer receipt.  Any exceptional or
        cancelled exit fences the owner and fault-latches this runtime.  In
        particular, failure to persist a positive result can never fall back
        to the legacy writer or replay the unresolved ciphertext suffix.
        """

        async with self._admit_actor_command_v49f(
            TransportCommandKindV49F.SUBSCRIPTION_DISPATCH
        ) as admission_grant_v49f:
            return await self._dispatch_subscription_v49c_locked(
                idempotency_key=idempotency_key,
                admission_grant_v49f=admission_grant_v49f,
            )

    async def _dispatch_subscription_v49c_locked(
        self,
        *,
        idempotency_key: str,
        admission_grant_v49f: TransportAdmissionGrantV49F | None = None,
    ) -> PhysicalTransportDispatchWindowV4:
        """Execute one application dispatch while holding the V4.9C seam lock."""

        self._assert_actor_admission_v49f(
            admission_grant_v49f,
            expected_kind=TransportCommandKindV49F.SUBSCRIPTION_DISPATCH,
        )
        self._require_state(PhysicalTransportRuntimeStateV4.SESSION_COMMITTED)
        actor = self._transport_session_actor_v49c
        owner = self._socket_owner
        session = self._session
        if actor is None or self._transport_actor_activation_v49c_in_progress:
            raise PhysicalTransportRuntimeV4StateError(
                "V4.9C subscription dispatch requires an active causal actor"
            )
        if self._initial_pending_raw_ingress_v49c is not None:
            raise PhysicalTransportRuntimeV4StateError(
                "V4.9C retained post-upgrade ingress must be committed and "
                "parsed before application dispatch"
            )

        from .physical_transport_actor_v49c import (
            V49C_MAX_TLS_CIPHERTEXT_CHUNKS,
            KernelSendAttemptPayloadV49C,
            OutboundDispatchCompletedPayloadV49C,
            OutboundWireOriginV49C,
            OutboundWirePreparedPayloadV49C,
            TlsCiphertextPreparedPayloadV49C,
            TransportActorEventKindV49C,
            WebSocketOpcodeV49C,
            WebSocketParserStateV49C,
        )
        from .physical_transport_linux_v4 import LinuxSocketOwnerV4
        from .physical_transport_session_actor_v49c import (
            PhysicalTransportSessionActorV49C,
        )
        from .physical_transport_tls_v49 import (
            PreparedTlsCiphertextV49C,
            PreparedWebSocketWireV49C,
        )

        if (
            type(actor) is not PhysicalTransportSessionActorV49C
            or type(owner) is not LinuxSocketOwnerV4
            or type(session) is not TransportSessionAttestationV4
        ):
            self._abort_owner_best_effort(owner)
            self._fault_cause = "V4.9C dispatch lost exact retained authority"
            self._state = PhysicalTransportRuntimeStateV4.FAULT_LATCHED
            raise PhysicalTransportRuntimeV4FaultLatched(
                "V4.9C dispatch requires exact runtime-retained authority"
            )
        if actor.is_fault_latched:
            self._abort_owner_best_effort(owner)
            self._fault_cause = "V4.9C actor restored or entered a terminal state"
            self._state = PhysicalTransportRuntimeStateV4.FAULT_LATCHED
            raise PhysicalTransportRuntimeV4FaultLatched(
                "V4.9C terminal actor authority cannot coexist with an open owner"
            )
        retained_tail = self._retained_ingress_tail_v49d
        parser_cursor = self._parser_cursor_v49d
        if (
            retained_tail is None
            or parser_cursor is None
            or retained_tail.total_octets != 0
            or parser_cursor.websocket_state is not WebSocketParserStateV49C.OPEN
        ):
            raise PhysicalTransportRuntimeV4StateError(
                "V4.9D application dispatch requires an OPEN parser with no "
                "incomplete durable ingress"
            )
        if (
            actor.has_pending_automatic_protocol_output
            or actor.oldest_outbound_wire_event_id is not None
        ):
            raise PhysicalTransportRuntimeV4StateError(
                "V4.9C application dispatch cannot overtake pending or terminal "
                "actor work"
            )

        first_attempt: KernelSendAttemptPayloadV49C | None = None
        try:
            permit = self._authorize_send_permit_core(idempotency_key=idempotency_key)
            intent = self._intent
            if type(intent) is not OutboundSubscriptionIntentV4:
                raise PhysicalTransportRuntimeV4Error(
                    "V4.9C authorization returned no exact durable intent"
                )

            assert self._socket_lease_id is not None
            self._assert_lease()
            self._validate_permit(permit, socket_lease_id=self._socket_lease_id)
            self._assert_socket_owner(context="before V4.9C subscription dispatch")
            self._assert_application_fence(context="before V4.9C subscription dispatch")
            preflight = self._sample_active_clock(
                context="V4.9C pre-dispatch clock validation failed",
                strictly_after_monotonic_ns=permit.issued_monotonic_ns,
            )
            if (
                preflight.sampled_at
                + timedelta(milliseconds=preflight.uncertainty_milliseconds)
                >= permit.send_not_after
                or preflight.monotonic_after_ns >= permit.send_not_after_monotonic_ns
            ):
                self._terminate_or_latch(
                    reason=TransportSessionTerminationReasonV4.TRANSPORT_ERROR,
                    evidence=preflight,
                    cause=PhysicalTransportSendPermitV4Error(
                        "V4.9C subscription permit expired before wire preparation"
                    ),
                )
                raise PhysicalTransportSendPermitV4Error(
                    "V4.9C subscription permit expired before wire preparation"
                )

            self._permit_consumed = True
            self._state = PhysicalTransportRuntimeStateV4.DISPATCHING
            wire = await owner.prepare_exact_text_wire_v49c(permit.command_bytes)
            if (
                type(wire) is not PreparedWebSocketWireV49C
                or wire.logical_opcode != 0x1
                or wire.logical_payload_sha256 != permit.command_sha256
                or wire.logical_payload_octets != len(permit.command_bytes)
            ):
                raise PhysicalTransportRuntimeV4Error(
                    "owner wire differs from the exact retained subscription"
                )
            preparation_clock = self._sample_active_clock(
                context="V4.9C wire-preparation clock validation failed",
                strictly_after_monotonic_ns=preflight.monotonic_after_ns,
            )
            first_preparation_ns = preparation_clock.monotonic_after_ns - 1
            if (
                first_preparation_ns < preparation_clock.monotonic_before_ns
                or first_preparation_ns <= preflight.monotonic_after_ns
                or preparation_clock.sampled_at >= permit.send_not_after
                or preparation_clock.monotonic_after_ns
                >= permit.send_not_after_monotonic_ns
            ):
                self._terminate_or_latch(
                    reason=TransportSessionTerminationReasonV4.TRANSPORT_ERROR,
                    evidence=preparation_clock,
                    cause=PhysicalTransportSendPermitV4Error(
                        "V4.9C subscription permit expired during wire preparation"
                    ),
                )
                raise PhysicalTransportSendPermitV4Error(
                    "V4.9C subscription permit expired or its governed clock "
                    "bracket cannot order atomic preparation: "
                    f"before={preparation_clock.monotonic_before_ns}, "
                    f"after={preparation_clock.monotonic_after_ns}, "
                    f"deadline={permit.send_not_after_monotonic_ns}"
                )
            wire_payload = OutboundWirePreparedPayloadV49C(
                outbound_operation_id=intent.outbound_subscription_intent_id,
                wire_origin=OutboundWireOriginV49C.APPLICATION_INTENT,
                source_parser_event_id=None,
                logical_opcode=WebSocketOpcodeV49C.TEXT,
                logical_payload_sha256=wire.logical_payload_sha256,
                logical_payload_octets=wire.logical_payload_octets,
                ordered_wire_chunks_base64=tuple(
                    base64.b64encode(chunk).decode("ascii")
                    for chunk in wire.ordered_wire_chunks
                ),
                ordered_wire_chunks_sha256=wire.ordered_wire_chunks_sha256,
                wire_batch_sha256=wire.wire_batch_sha256,
                wire_octets=wire.wire_octets,
                prepared_at=preparation_clock.sampled_at,
                prepared_monotonic_ns=first_preparation_ns,
                send_not_after=permit.send_not_after,
                send_not_after_monotonic_ns=(permit.send_not_after_monotonic_ns),
            )
            wire_event, permit_event = await actor.prepare_application_wire_and_permit(
                wire_payload,
                permit_consumed_at=preparation_clock.sampled_at,
                permit_consumed_monotonic_ns=first_preparation_ns + 1,
            )

            # Advancing SSLObject/MemoryBIO state is permitted only after the
            # exact wire and one-shot actor permit are durable.
            ciphertext = await owner.prepare_tls_ciphertext_v49c(wire)
            if (
                type(ciphertext) is not PreparedTlsCiphertextV49C
                or ciphertext.prepared_wire is not wire
                or ciphertext.plaintext_batch_sha256 != wire.wire_batch_sha256
                or ciphertext.plaintext_octets != wire.wire_octets
            ):
                raise PhysicalTransportRuntimeV4Error(
                    "owner TLS artifact differs from its exact retained wire"
                )
            tls_clock = self._sample_active_clock(
                context="V4.9C TLS-preparation clock validation failed",
                strictly_after_monotonic_ns=(preparation_clock.monotonic_after_ns),
            )
            if (
                tls_clock.sampled_at >= permit.send_not_after
                or tls_clock.monotonic_after_ns >= permit.send_not_after_monotonic_ns
            ):
                self._terminate_or_latch(
                    reason=TransportSessionTerminationReasonV4.TRANSPORT_ERROR,
                    evidence=tls_clock,
                    cause=PhysicalTransportSendPermitV4Error(
                        "V4.9C subscription permit expired during TLS preparation"
                    ),
                )
                raise PhysicalTransportSendPermitV4Error(
                    "V4.9C subscription permit expired during TLS preparation"
                )
            await actor.prepare_tls_ciphertext(
                TlsCiphertextPreparedPayloadV49C(
                    outbound_wire_prepared_event_id=(
                        wire_event.transport_actor_event_id
                    ),
                    write_permit_consumed_event_id=(
                        permit_event.transport_actor_event_id
                    ),
                    plaintext_batch_sha256=ciphertext.plaintext_batch_sha256,
                    plaintext_octets=ciphertext.plaintext_octets,
                    ordered_ciphertext_chunks_base64=tuple(
                        base64.b64encode(chunk).decode("ascii")
                        for chunk in ciphertext.ordered_ciphertext_chunks
                    ),
                    ordered_ciphertext_chunks_sha256=(
                        ciphertext.ordered_ciphertext_chunks_sha256
                    ),
                    ciphertext_batch_sha256=ciphertext.ciphertext_batch_sha256,
                    ciphertext_octets=ciphertext.ciphertext_octets,
                    prepared_at=tls_clock.sampled_at,
                    prepared_monotonic_ns=tls_clock.monotonic_after_ns,
                )
            )

            submitted = 0
            positive_result_count = 0
            while submitted < ciphertext.ciphertext_octets:
                if positive_result_count >= V49C_MAX_TLS_CIPHERTEXT_CHUNKS:
                    raise PhysicalTransportRuntimeV4Error(
                        "V4.9C positive-send result bound was exhausted"
                    )

                async def exact_owner_send(exact_slice: bytes) -> int:
                    return await owner.send_prepared_tls_ciphertext_once_v49c(
                        exact_slice,
                        prepared=ciphertext,
                        deadline_ns=permit.send_not_after_monotonic_ns,
                    )

                outcome = await actor.send_oldest_ciphertext(
                    send_effect=exact_owner_send
                )
                attempt_payload = outcome.attempt_event.payload
                if type(attempt_payload) is not KernelSendAttemptPayloadV49C:
                    raise PhysicalTransportRuntimeV4Error(
                        "actor returned an unsupported kernel attempt"
                    )
                if first_attempt is None:
                    first_attempt = attempt_payload
                submitted += outcome.accepted_octets
                positive_result_count += 1
            completed_event = await actor.complete_oldest_dispatch_from_chain()
            completed_payload = completed_event.payload
            self._assert_lease()
            self._assert_socket_owner(context="after V4.9C subscription dispatch")
            self._assert_application_fence(context="after V4.9C subscription dispatch")
            if (
                self._state is not PhysicalTransportRuntimeStateV4.DISPATCHING
                or self._socket_owner is not owner
                or self._session is not session
                or self._transport_session_actor_v49c is not actor
                or self._intent is not intent
                or self._permit is not permit
                or actor.is_fault_latched
            ):
                raise PhysicalTransportRuntimeV4StateError(
                    "V4.9C runtime authority changed while dispatch was in flight"
                )
            if (
                completed_event.event_kind
                is not TransportActorEventKindV49C.OUTBOUND_DISPATCH_COMPLETED
                or type(completed_payload) is not OutboundDispatchCompletedPayloadV49C
                or completed_payload.outbound_wire_prepared_event_id
                != wire_event.transport_actor_event_id
                or completed_payload.submitted_ciphertext_octets
                != ciphertext.ciphertext_octets
                or first_attempt is None
            ):
                raise PhysicalTransportRuntimeV4Error(
                    "actor returned an unsupported completed dispatch chain"
                )
            window = PhysicalTransportDispatchWindowV4(
                transport_session_id=session.transport_session_id,
                outbound_subscription_intent_id=(
                    intent.outbound_subscription_intent_id
                ),
                socket_lease_id=permit.socket_lease_id,
                monotonic_clock_domain_id=session.monotonic_clock_domain_id,
                dispatch_started_at=first_attempt.attempted_at,
                dispatch_completed_at=completed_payload.completed_at,
                dispatch_started_monotonic_ns=(first_attempt.attempted_monotonic_ns),
                dispatch_completed_monotonic_ns=(
                    completed_payload.completed_monotonic_ns
                ),
            )
        except BaseException as exc:
            self._abort_owner_best_effort(owner)
            if self._state not in {
                PhysicalTransportRuntimeStateV4.FENCED,
                PhysicalTransportRuntimeStateV4.FAULT_LATCHED,
                PhysicalTransportRuntimeStateV4.CLOSED,
            }:
                self._fault_cause = (
                    "V4.9C governed dispatch failed after authorization began: "
                    f"{type(exc).__name__}"
                )
                self._state = PhysicalTransportRuntimeStateV4.FAULT_LATCHED
            if isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)):
                raise
            has_durable_attempt = first_attempt is not None or any(
                event.event_kind is TransportActorEventKindV49C.KERNEL_SEND_ATTEMPT
                for event in actor.events
            )
            delivery = (
                "exact peer delivery is unknown"
                if has_durable_attempt
                else "no kernel attempt is durable"
            )
            raise PhysicalTransportDispatchUnknownV4(
                f"V4.9C dispatch failed; {delivery} and the owner was fenced"
            ) from exc

        self._dispatch_window = window
        self._state = PhysicalTransportRuntimeStateV4.AWAITING_ACK
        if self._pending_ack_disposition_id is not None:
            self._bind_ack(self._pending_ack_disposition_id)
        return window

    def observe_captured_ack(
        self,
        *,
        message_disposition_id: str,
        socket_lease_id: str,
    ) -> SubscriptionAckBindingV4 | None:
        """Buffer or bind one raw-first captured ACK candidate.

        A callback from a previous socket lease is rejected without fencing the
        new current socket.  A second different ACK candidate for one intent is
        ambiguous and fences the current session.
        """

        if self._transport_session_actor_v49c is not None:
            raise PhysicalTransportRuntimeV4StateError(
                "caller-presented ACK callbacks are fenced after V4.9E actor "
                "activation; ACK authority comes only from durable parser bytes"
            )

        self._require_state(
            PhysicalTransportRuntimeStateV4.DISPATCHING,
            PhysicalTransportRuntimeStateV4.AWAITING_ACK,
        )
        self._assert_lease()
        socket_id = canonical_hash(socket_lease_id, field="socket_lease_id")
        if socket_id != self._socket_lease_id:
            raise PhysicalTransportStaleCallbackV4(
                "ACK callback belongs to a stale socket lease"
            )
        self._assert_socket_owner(context="before accepting an ACK callback")
        self._assert_application_fence(context="before accepting an ACK callback")
        disposition_id = canonical_hash(
            message_disposition_id, field="message_disposition_id"
        )
        if (
            self._pending_ack_disposition_id is not None
            and self._pending_ack_disposition_id != disposition_id
        ):
            assert self._session is not None
            evidence = self._sample_active_clock(
                context="ambiguous ACK clock validation failed"
            )
            self._terminate_or_latch(
                reason=TransportSessionTerminationReasonV4.TRANSPORT_ERROR,
                evidence=evidence,
                cause=PhysicalTransportAckBindingV4Error(
                    "multiple ACK candidates were observed for one intent"
                ),
            )
            raise PhysicalTransportAckBindingV4Error(
                "multiple ACK candidates fenced the current session"
            )
        self._pending_ack_disposition_id = disposition_id
        if self._state is PhysicalTransportRuntimeStateV4.DISPATCHING:
            return None
        return self._bind_ack(disposition_id)

    def _bind_ack(self, disposition_id: str) -> SubscriptionAckBindingV4:
        assert self._intent is not None
        assert self._dispatch_window is not None
        assert self._session is not None
        try:
            self._assert_lease()
            self._assert_socket_owner(context="before ACK binding")
            self._assert_application_fence(context="before ACK binding")
            binding = self._journal.bind_subscription_ack(
                outbound_subscription_intent_id=(
                    self._intent.outbound_subscription_intent_id
                ),
                message_disposition_id=disposition_id,
                dispatch_started_at=self._dispatch_window.dispatch_started_at,
                dispatch_completed_at=self._dispatch_window.dispatch_completed_at,
                dispatch_started_monotonic_ns=(
                    self._dispatch_window.dispatch_started_monotonic_ns
                ),
                dispatch_completed_monotonic_ns=(
                    self._dispatch_window.dispatch_completed_monotonic_ns
                ),
                signer=self._signer,
                idempotency_key=(
                    f"{self._idempotency_prefix}-ack-"
                    f"{self._intent.outbound_subscription_intent_id}"
                ),
            )
            self._validate_ack_binding(binding, disposition_id=disposition_id)
            self._assert_lease()
            self._assert_socket_owner(context="after ACK binding")
            self._assert_application_fence(context="after ACK binding")
        except PhysicalTransportRuntimeV4FaultLatched:
            raise
        except Exception as exc:
            try:
                from .physical_projection_v4 import (
                    PhysicalProjectionV4ConflictError,
                )

                reason = (
                    TransportSessionTerminationReasonV4.TRANSPORT_ERROR
                    if isinstance(exc, PhysicalProjectionV4ConflictError)
                    else TransportSessionTerminationReasonV4.STORAGE_FAILURE
                )
            except ImportError:
                reason = TransportSessionTerminationReasonV4.STORAGE_FAILURE
            assert self._session is not None
            evidence = self._sample_active_clock(
                context="rejected ACK clock validation failed",
                strictly_after_monotonic_ns=(
                    self._dispatch_window.dispatch_completed_monotonic_ns
                ),
            )
            self._terminate_or_latch(reason=reason, evidence=evidence, cause=exc)
            raise PhysicalTransportAckBindingV4Error(
                "captured ACK couldn't be bound; the session was fenced"
            ) from exc
        self._binding = binding
        self._state = PhysicalTransportRuntimeStateV4.ACK_BOUND
        return binding

    def _validate_ack_binding(
        self,
        binding: SubscriptionAckBindingV4,
        *,
        disposition_id: str,
    ) -> None:
        assert self._session is not None
        assert self._intent is not None
        assert self._dispatch_window is not None
        session = self._session
        intent = self._intent
        window = self._dispatch_window
        if not isinstance(binding, SubscriptionAckBindingV4) or any(
            (
                binding.transport_subscription_policy_id
                != session.transport_subscription_policy_id,
                binding.transport_session_id != session.transport_session_id,
                binding.outbound_subscription_intent_id
                != intent.outbound_subscription_intent_id,
                binding.physical_scope_manifest_id
                != session.physical_scope_manifest_id,
                binding.adapter_policy_id != session.adapter_policy_id,
                binding.capture_partition_id != session.capture_partition_id,
                binding.connection_generation != session.connection_generation,
                binding.message_disposition_id != disposition_id,
                binding.echoed_request_id != intent.request_id,
                binding.request_command_sha256 != intent.command_sha256,
                binding.dispatch_started_at != window.dispatch_started_at,
                binding.dispatch_completed_at != window.dispatch_completed_at,
                binding.dispatch_started_monotonic_ns
                != window.dispatch_started_monotonic_ns,
                binding.dispatch_completed_monotonic_ns
                != window.dispatch_completed_monotonic_ns,
                binding.ack_received_at > intent.ack_not_after,
                binding.collector_attestation_key_id
                != session.collector_attestation_key_id,
                binding.collector_attestation_public_key_hex
                != session.collector_attestation_public_key_hex,
            )
        ):
            raise PhysicalTransportAckBindingV4Error(
                "journal returned an ACK binding outside the dispatched authority"
            )

    def expire_ack_if_due(self) -> bool:
        """Fence an unbound intent after its committed ACK deadline."""

        if self._transport_session_actor_v49c is not None:
            raise PhysicalTransportRuntimeV4StateError(
                "synchronous ACK expiry cannot bypass the V4.9E actor order"
            )

        self._require_state(PhysicalTransportRuntimeStateV4.AWAITING_ACK)
        self._assert_lease()
        assert self._session is not None
        assert self._intent is not None
        assert self._dispatch_window is not None
        evidence = self._sample_active_clock(
            context="ACK deadline clock validation failed",
            strictly_after_monotonic_ns=(
                self._dispatch_window.dispatch_completed_monotonic_ns
            ),
        )
        if evidence.sampled_at <= self._intent.ack_not_after:
            return False
        self._terminate_or_latch(
            reason=TransportSessionTerminationReasonV4.ACK_TIMEOUT,
            evidence=evidence,
            cause=PhysicalTransportAckBindingV4Error("ACK deadline expired"),
        )
        return True

    async def expire_ack_if_due_v49e(self) -> bool:
        """Commit the sole actor-ordered ACK timeout when both clocks are due.

        The orchestration lock is the deadline-race boundary.  A RAW ingress
        command that acquired it first is finalized through parser,
        classification, and possible ACK binding before this command can
        inspect the state.  Conversely, once the timeout transaction commits,
        no later ingress command can revive this session.
        """

        async with self._admit_actor_command_v49f(
            TransportCommandKindV49F.ACK_DEADLINE_EXPIRY
        ):
            self._require_state(PhysicalTransportRuntimeStateV4.AWAITING_ACK)
            actor = self._transport_session_actor_v49c
            owner = self._socket_owner
            session = self._session
            intent = self._intent
            window = self._dispatch_window

            from .physical_projection_v4 import ActorAckDeadlineExpiryResultV49E
            from .physical_transport_actor_v49c import (
                AckDeadlineExpiredPayloadV49E,
                TransportActorEventKindV49C,
                WebSocketParserStateV49C,
            )
            from .physical_transport_linux_v4 import LinuxSocketOwnerV4
            from .physical_transport_session_actor_v49c import (
                PhysicalTransportSessionActorV49C,
            )
            from .physical_transport_terminal_v49c import (
                TerminalTransitionKindV49C,
                TerminalTransitionPayloadV49C,
            )

            if (
                type(actor) is not PhysicalTransportSessionActorV49C
                or type(owner) is not LinuxSocketOwnerV4
                or type(session) is not TransportSessionAttestationV4
                or type(intent) is not OutboundSubscriptionIntentV4
                or type(window) is not PhysicalTransportDispatchWindowV4
                or self._transport_actor_activation_v49c_in_progress
            ):
                self._abort_owner_best_effort(owner)
                self._fault_cause = "V4.9E ACK timeout lost exact actor authority"
                self._state = PhysicalTransportRuntimeStateV4.FAULT_LATCHED
                raise PhysicalTransportRuntimeV4FaultLatched(
                    "V4.9E ACK timeout requires one exact active actor session"
                )
            parser_cursor = self._parser_cursor_v49d
            if (
                actor.is_fault_latched
                or actor.has_pending_automatic_protocol_output
                or actor.oldest_outbound_wire_event_id is not None
                or self._initial_pending_raw_ingress_v49c is not None
                or parser_cursor is None
                or parser_cursor.websocket_state is not WebSocketParserStateV49C.OPEN
            ):
                raise PhysicalTransportRuntimeV4StateError(
                    "V4.9E ACK timeout cannot overtake pending or closing actor work"
                )

            deadline_delta = intent.ack_not_after - window.dispatch_completed_at
            deadline_delta_ns = (
                deadline_delta.days * 86_400 + deadline_delta.seconds
            ) * 1_000_000_000 + deadline_delta.microseconds * 1_000
            if deadline_delta_ns <= 0:
                self._abort_owner_best_effort(owner)
                self._fault_cause = "V4.9E ACK deadline is not after dispatch"
                self._state = PhysicalTransportRuntimeStateV4.FAULT_LATCHED
                raise PhysicalTransportRuntimeV4FaultLatched(
                    "V4.9E ACK deadline cannot be derived from dispatch authority"
                )
            deadline_ns = window.dispatch_completed_monotonic_ns + deadline_delta_ns

            self._assert_lease()
            self._assert_socket_owner(context="before V4.9E ACK deadline sampling")
            self._assert_application_fence(context="before V4.9E ACK deadline sampling")
            evidence = self._sample_active_clock(
                context="V4.9E ACK deadline clock validation failed",
                strictly_after_monotonic_ns=self._v49d_actor_clock_floor(actor),
            )
            # Use the beginning of both governed brackets for the due decision.
            # This refuses to choose a favorable point inside an interval that
            # still overlaps the committed deadline.
            if (
                evidence.wall_before_at < intent.ack_not_after
                or evidence.monotonic_before_ns < deadline_ns
            ):
                return False

            self._assert_lease()
            self._assert_socket_owner(context="before V4.9E ACK timeout commit")
            self._assert_application_fence(context="before V4.9E ACK timeout commit")
            try:
                result = await actor.expire_ack_deadline_v49e(
                    observed_at=evidence.sampled_at,
                    observed_monotonic_ns=evidence.monotonic_ns,
                    signer=self._signer,
                )
                if type(result) is not ActorAckDeadlineExpiryResultV49E:
                    raise PhysicalTransportRuntimeV4Error(
                        "V4.9E actor returned an unsupported timeout result"
                    )
                deadline_payload = result.deadline_event.payload
                terminal_payload = result.terminal_event.payload
                if (
                    result.deadline_event.event_kind
                    is not TransportActorEventKindV49C.ACK_DEADLINE_EXPIRED
                    or type(deadline_payload) is not AckDeadlineExpiredPayloadV49E
                    or deadline_payload.outbound_subscription_intent_id
                    != intent.outbound_subscription_intent_id
                    or deadline_payload.ack_not_after != intent.ack_not_after
                    or deadline_payload.ack_not_after_monotonic_ns != deadline_ns
                    or deadline_payload.observed_at != evidence.sampled_at
                    or deadline_payload.observed_monotonic_ns != evidence.monotonic_ns
                    or result.terminal_event.event_kind
                    is not TransportActorEventKindV49C.TERMINAL_TRANSITION
                    or type(terminal_payload) is not TerminalTransitionPayloadV49C
                    or terminal_payload.kind is not TerminalTransitionKindV49C.TIMEOUT
                    or terminal_payload.cause_code != "ACK_DEADLINE_EXPIRED"
                ):
                    raise PhysicalTransportRuntimeV4Error(
                        "V4.9E timeout result differs from its exact deadline"
                    )
                self._validate_termination_result(
                    result.termination,
                    reason=TransportSessionTerminationReasonV4.ACK_TIMEOUT,
                    evidence=evidence,
                    close_code=None,
                    close_reason_digest=None,
                )
            except BaseException as exc:
                abort_failure = self._abort_owner_best_effort(owner)
                suffix = (
                    ""
                    if abort_failure is None
                    else f"; abort failed: {type(abort_failure).__name__}"
                )
                self._fault_cause = (
                    "V4.9E ACK-timeout transaction outcome is uncertain: "
                    f"{type(exc).__name__}{suffix}"
                )
                self._state = PhysicalTransportRuntimeStateV4.FAULT_LATCHED
                if isinstance(
                    exc, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)
                ):
                    raise
                raise PhysicalTransportRuntimeV4FaultLatched(
                    "V4.9E ACK timeout could not converge actor and session authority"
                ) from exc

            abort_failure = self._abort_owner_best_effort(owner)
            self._fault_cause = "ACK_DEADLINE_EXPIRED"
            self._state = PhysicalTransportRuntimeStateV4.FENCED
            if abort_failure is not None:
                self._fault_cause = (
                    "V4.9E owner abort failed after durable ACK timeout: "
                    f"{type(abort_failure).__name__}"
                )
                self._state = PhysicalTransportRuntimeStateV4.FAULT_LATCHED
                raise PhysicalTransportRuntimeV4FaultLatched(
                    "durable V4.9E ACK timeout could not close socket authority"
                ) from abort_failure
            return True

    def terminate_current(
        self,
        reason: TransportSessionTerminationReasonV4,
        *,
        close_code: int | None = None,
        close_reason_digest: str | None = None,
    ) -> TransportSessionTerminationV4:
        """Durably terminate the current session before allowing reconnect."""

        self._reject_legacy_terminal_bypass_v49e(operation="terminate_current")
        self._require_state(
            PhysicalTransportRuntimeStateV4.SESSION_COMMITTED,
            PhysicalTransportRuntimeStateV4.INTENT_COMMITTED,
            PhysicalTransportRuntimeStateV4.AWAITING_ACK,
            PhysicalTransportRuntimeStateV4.ACK_BOUND,
        )
        self._assert_lease()
        if not isinstance(reason, TransportSessionTerminationReasonV4):
            try:
                reason = TransportSessionTerminationReasonV4(reason)
            except (TypeError, ValueError) as exc:
                raise CanonicalizationError(
                    "unsupported transport termination reason"
                ) from exc
        assert self._session is not None
        floor = self._session.handshake_completed_monotonic_ns
        if self._dispatch_window is not None:
            floor = self._dispatch_window.dispatch_completed_monotonic_ns
        evidence = self._sample_active_clock(
            context="session termination clock validation failed",
            strictly_after_monotonic_ns=floor,
        )
        return self._terminate_or_latch(
            reason=reason,
            evidence=evidence,
            cause=None,
            close_code=close_code,
            close_reason_digest=close_reason_digest,
        )

    def fence_backpressure(
        self, *, socket_lease_id: str
    ) -> TransportSessionTerminationV4:
        """Fail closed without dropping/coalescing an inbound message."""

        self._reject_legacy_terminal_bypass_v49e(operation="fence_backpressure")
        self._require_state(
            PhysicalTransportRuntimeStateV4.SESSION_COMMITTED,
            PhysicalTransportRuntimeStateV4.INTENT_COMMITTED,
            PhysicalTransportRuntimeStateV4.DISPATCHING,
            PhysicalTransportRuntimeStateV4.AWAITING_ACK,
            PhysicalTransportRuntimeStateV4.ACK_BOUND,
        )
        self._assert_lease()
        socket_id = canonical_hash(socket_lease_id, field="socket_lease_id")
        if socket_id != self._socket_lease_id:
            raise PhysicalTransportStaleCallbackV4(
                "backpressure callback belongs to a stale socket lease"
            )
        self._assert_socket_owner(context="before backpressure fencing")
        assert self._session is not None
        floor = self._session.handshake_completed_monotonic_ns
        if self._dispatch_window is not None:
            floor = self._dispatch_window.dispatch_completed_monotonic_ns
        elif self._permit is not None:
            floor = self._permit.issued_monotonic_ns
        evidence = self._sample_active_clock(
            context="backpressure fencing clock validation failed",
            strictly_after_monotonic_ns=floor,
        )
        return self._terminate_or_latch(
            reason=TransportSessionTerminationReasonV4.BACKPRESSURE,
            evidence=evidence,
            cause=PhysicalTransportRuntimeV4Error("bounded capture queue overflow"),
        )

    def _terminate_or_latch(
        self,
        *,
        reason: TransportSessionTerminationReasonV4,
        evidence: ClockEvidenceV4,
        cause: BaseException | None,
        close_code: int | None = None,
        close_reason_digest: str | None = None,
    ) -> TransportSessionTerminationV4:
        if self._session is None:
            self._fault_cause = "terminal event requested without a committed session"
            self._state = PhysicalTransportRuntimeStateV4.FAULT_LATCHED
            raise PhysicalTransportRuntimeV4FaultLatched(
                "cannot write a terminal event without a committed session"
            )
        self._assert_lease()
        self._assert_application_fence(context="before terminal journal append")
        try:
            termination = self._journal.append_transport_session_termination(
                transport_session_id=self._session.transport_session_id,
                reason=reason,
                detected_at=evidence.sampled_at,
                detected_monotonic_ns=evidence.monotonic_ns,
                detected_monotonic_clock_domain_id=(evidence.monotonic_clock_domain_id),
                signer=self._signer,
                idempotency_key=(
                    f"{self._idempotency_prefix}-term-"
                    f"{self._session.transport_session_id}"
                ),
                close_code=close_code,
                close_reason_digest=close_reason_digest,
            )
            self._validate_termination_result(
                termination,
                reason=reason,
                evidence=evidence,
                close_code=close_code,
                close_reason_digest=close_reason_digest,
            )
        except Exception as exc:
            origin = "none" if cause is None else type(cause).__name__
            self._fault_cause = (
                f"terminal journal append failed after {origin}: {type(exc).__name__}"
            )
            self._state = PhysicalTransportRuntimeStateV4.FAULT_LATCHED
            raise PhysicalTransportRuntimeV4FaultLatched(
                "terminal state is uncertain; transport authority is latched off"
            ) from exc
        self._fault_cause = None if cause is None else type(cause).__name__
        self._state = PhysicalTransportRuntimeStateV4.FENCED
        if self._transport_session_actor_v49c is not None:
            abort_failure = self._abort_owner_best_effort(self._socket_owner)
            if abort_failure is not None:
                self._fault_cause = (
                    "V4.9C owner abort failed after durable termination: "
                    f"{type(abort_failure).__name__}"
                )
                self._state = PhysicalTransportRuntimeStateV4.FAULT_LATCHED
                raise PhysicalTransportRuntimeV4FaultLatched(
                    "durable V4.9C termination could not close socket authority"
                ) from abort_failure
        return termination

    def _validate_termination_result(
        self,
        termination: TransportSessionTerminationV4,
        *,
        reason: TransportSessionTerminationReasonV4,
        evidence: ClockEvidenceV4,
        close_code: int | None,
        close_reason_digest: str | None,
    ) -> None:
        assert self._session is not None
        session = self._session
        if not isinstance(termination, TransportSessionTerminationV4) or any(
            (
                termination.transport_subscription_policy_id
                != session.transport_subscription_policy_id,
                termination.transport_session_id != session.transport_session_id,
                termination.physical_scope_manifest_id
                != session.physical_scope_manifest_id,
                termination.capture_partition_id != session.capture_partition_id,
                termination.connection_generation != session.connection_generation,
                termination.reason is not reason,
                termination.close_code != close_code,
                termination.close_reason_digest != close_reason_digest,
                termination.detected_at != evidence.sampled_at,
                termination.detected_monotonic_ns != evidence.monotonic_ns,
                termination.detected_monotonic_clock_domain_id
                != evidence.monotonic_clock_domain_id,
                termination.collector_attestation_key_id
                != session.collector_attestation_key_id,
                termination.collector_attestation_public_key_hex
                != session.collector_attestation_public_key_hex,
            )
        ):
            raise PhysicalTransportRuntimeV4Error(
                "journal returned an unrelated transport termination"
            )

    def _adopt_actor_terminal_convergence_v49e(
        self,
        result: Any,
        *,
        actor: Any,
        owner: Any,
        require_clean: bool,
    ) -> TransportSessionTerminationV4:
        """Adopt one already-atomic actor/legacy terminal pair and fence I/O.

        This is deliberately an adoption boundary, not a terminal writer.  The
        projection transaction has already derived and signed the legacy row
        from the exact final actor event.  Runtime acceptance therefore checks
        retained object identity, session authority, and the reduced terminal
        outcome before aborting the socket owner.
        """

        from .physical_projection_v4 import ActorTerminalConvergenceResultV49E
        from .physical_transport_actor_v49c import TransportActorEventKindV49C
        from .physical_transport_session_actor_v49c import (
            PhysicalTransportSessionActorV49C,
        )
        from .physical_transport_terminal_v49c import (
            TerminalOutcomeV49C,
            TerminalTransitionPayloadV49C,
        )

        session = self._session
        if (
            type(result) is not ActorTerminalConvergenceResultV49E
            or type(actor) is not PhysicalTransportSessionActorV49C
            or type(session) is not TransportSessionAttestationV4
            or self._transport_session_actor_v49c is not actor
            or not actor.events
            or result is not actor.last_terminal_convergence_v49e
            or actor.events[-1] is not result.terminal_event
            or result.terminal_event.event_kind
            is not TransportActorEventKindV49C.TERMINAL_TRANSITION
            or type(result.terminal_event.payload) is not TerminalTransitionPayloadV49C
            or not actor.terminal_state.is_terminal
            or result.termination.transport_session_id != session.transport_session_id
            or result.termination.transport_subscription_policy_id
            != session.transport_subscription_policy_id
            or result.termination.physical_scope_manifest_id
            != session.physical_scope_manifest_id
            or result.termination.capture_partition_id != session.capture_partition_id
            or result.termination.connection_generation != session.connection_generation
            or result.termination.detected_monotonic_clock_domain_id
            != session.monotonic_clock_domain_id
            or result.termination.collector_attestation_key_id
            != session.collector_attestation_key_id
            or result.termination.collector_attestation_public_key_hex
            != session.collector_attestation_public_key_hex
        ):
            self._abort_owner_best_effort(owner)
            self._fault_cause = "V4.9E terminal convergence changed retained authority"
            self._state = PhysicalTransportRuntimeStateV4.FAULT_LATCHED
            raise PhysicalTransportRuntimeV4FaultLatched(
                "V4.9E actor terminal pair is outside retained runtime authority"
            )
        if require_clean and (
            actor.terminal_state.terminal_outcome
            is not TerminalOutcomeV49C.CLEAN_ALL_LAYERS
            or result.termination.reason
            not in {
                TransportSessionTerminationReasonV4.LOCAL_CLOSE,
                TransportSessionTerminationReasonV4.REMOTE_CLOSE,
            }
        ):
            self._abort_owner_best_effort(owner)
            self._fault_cause = "V4.9E clean shutdown returned a non-clean pair"
            self._state = PhysicalTransportRuntimeStateV4.FAULT_LATCHED
            raise PhysicalTransportRuntimeV4FaultLatched(
                "V4.9E clean terminal adoption requires all actor layers"
            )

        abort_failure = self._abort_owner_best_effort(owner)
        self._fault_cause = actor.terminal_state.terminal_cause_code
        self._state = PhysicalTransportRuntimeStateV4.FENCED
        if abort_failure is not None:
            self._fault_cause = (
                "V4.9E owner abort failed after durable terminal pair: "
                f"{type(abort_failure).__name__}"
            )
            self._state = PhysicalTransportRuntimeStateV4.FAULT_LATCHED
            raise PhysicalTransportRuntimeV4FaultLatched(
                "durable V4.9E terminal pair could not close socket authority"
            ) from abort_failure
        return result.termination

    def prepare_reconnect(self) -> None:
        """Clear only a durably fenced session; never reuse its intent or permit."""

        self._require_state(PhysicalTransportRuntimeStateV4.FENCED)
        self._assert_lease()
        admission = self.transport_admission_snapshot_v49f()
        if self._transport_orchestration_lock_v49c.locked() or (
            admission is not None
            and (
                admission.active_and_waiting_commands != 0
                or admission.reserved_work_units != 0
            )
        ):
            self._abort_owner_best_effort(self._socket_owner)
            self._fault_cause = "V4.9F admission remained active at reconnect"
            self._state = PhysicalTransportRuntimeStateV4.FAULT_LATCHED
            raise PhysicalTransportRuntimeV4FaultLatched(
                "V4.9F actor tickets and work must stop before reconnect"
            )
        abort_failure = self._abort_owner_best_effort(self._socket_owner)
        if abort_failure is not None:
            self._fault_cause = (
                f"socket owner abort failed before reconnect: "
                f"{type(abort_failure).__name__}"
            )
            self._state = PhysicalTransportRuntimeStateV4.FAULT_LATCHED
            raise PhysicalTransportRuntimeV4FaultLatched(
                "socket owner could not be aborted before reconnect"
            ) from abort_failure
        self._session = None
        self._intent = None
        self._socket_owner = None
        self._socket_owner_snapshot = None
        self._socket_owner_binding = None
        self._socket_lease_id = None
        self._permit = None
        self._permit_consumed = False
        self._dispatch_window = None
        self._pending_ack_disposition_id = None
        self._binding = None
        self._control_mediator_created = False
        self._driver_session_transition_active = False
        self._committed_bound_session_v49c = None
        self._driver_handshake_transition_v49c = None
        self._initial_pending_raw_ingress_v49c = None
        self._transport_actor_journal_v49c = None
        self._transport_session_actor_v49c = None
        self._transport_actor_activation_v49c_in_progress = False
        self._retained_ingress_tail_v49d = None
        self._parser_cursor_v49d = None
        self._fragmented_message_bytes_v49d = b""
        self._fragmented_message_parser_event_ids_v49e = ()
        if self._transport_admission_gate_v49f is not None:
            self._transport_admission_gate_v49f.advance_epoch()
        self._fault_cause = None
        self._state = PhysicalTransportRuntimeStateV4.READY

    def close(self) -> None:
        """Release the writer lease; an active session must be terminated first."""

        self._reject_legacy_terminal_bypass_v49e(operation="close")
        if self._state is PhysicalTransportRuntimeStateV4.CLOSED:
            return
        admission = self.transport_admission_snapshot_v49f()
        if admission is not None and admission.active_and_waiting_commands != 0:
            raise PhysicalTransportRuntimeV4StateError(
                "cannot close while V4.9F transport tickets remain admitted"
            )
        primary_failure: BaseException | None = None
        try:
            if self._state in {
                PhysicalTransportRuntimeStateV4.SESSION_COMMITTED,
                PhysicalTransportRuntimeStateV4.INTENT_COMMITTED,
                PhysicalTransportRuntimeStateV4.AWAITING_ACK,
                PhysicalTransportRuntimeStateV4.ACK_BOUND,
            }:
                self.terminate_current(TransportSessionTerminationReasonV4.LOCAL_CLOSE)
            elif self._state is PhysicalTransportRuntimeStateV4.DISPATCHING:
                raise PhysicalTransportRuntimeV4StateError(
                    "cannot synchronously close while dispatch is in progress"
                )
        except BaseException as exc:
            primary_failure = exc

        cleanup_failure: BaseException | None = None
        owner_abort_failure = self._abort_owner_best_effort(self._socket_owner)
        if owner_abort_failure is not None:
            cleanup_failure = owner_abort_failure
        if self._writer_fence_token_sha256 is not None:
            try:
                self._journal.release_transport_runtime_writer_fence(
                    lease_token_sha256=self._writer_fence_token_sha256
                )
            except BaseException as exc:
                cleanup_failure = cleanup_failure or exc
            else:
                self._writer_fence_token_sha256 = None
                self._writer_fence_generation = None
        try:
            self._writer_lease.release()
        except BaseException as exc:
            cleanup_failure = cleanup_failure or exc
        if self._transport_admission_gate_v49f is not None:
            try:
                self._transport_admission_gate_v49f.close()
            except BaseException as exc:
                cleanup_failure = cleanup_failure or exc
        self._state = PhysicalTransportRuntimeStateV4.CLOSED
        if primary_failure is not None:
            self._fault_cause = (
                f"close failed before cleanup: {type(primary_failure).__name__}"
            )
            raise primary_failure
        if cleanup_failure is not None:
            self._fault_cause = (
                f"writer cleanup failed: {type(cleanup_failure).__name__}"
            )
            raise PhysicalTransportRuntimeV4FaultLatched(
                "writer fences didn't release cleanly; startup reconciliation is required"
            ) from cleanup_failure

    def __enter__(self) -> PhysicalTransportRuntimeV4:
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


__all__ = [
    "PHYSICAL_TRANSPORT_A2M_RAW_V49F_V7_SCHEMA_VERSION",
    "PHYSICAL_TRANSPORT_RUNTIME_V4_SCHEMA_VERSION",
    "V4_RUNTIME_DEFAULT_MAXIMUM_CLOCK_EVIDENCE_LIFETIME_SECONDS",
    "V4_RUNTIME_DEFAULT_MAXIMUM_CLOCK_UNCERTAINTY_MILLISECONDS",
    "ClockEvidenceSourceV4",
    "ClockEvidenceV4",
    "ExactTextFrameSenderV4",
    "OperationalDeploymentAdmissionV4",
    "PhysicalTransportAutomaticCloseTerminalFailureV49E",
    "PhysicalTransportAckBindingV4Error",
    "PhysicalTransportClockEvidenceV4Error",
    "PhysicalTransportDispatchUnknownV4",
    "PhysicalTransportDispatchWindowV4",
    "PhysicalTransportIngressProgressV49D",
    "PhysicalTransportJournalPortV4",
    "PhysicalTransportManifestAuthoritySignatureV49FV7",
    "PhysicalTransportProviderIntegrityFailureV49E",
    "PhysicalTransportRuntimeConfigV4",
    "PhysicalTransportRuntimeStartReportV4",
    "PhysicalTransportRuntimeStateV4",
    "PhysicalTransportRuntimeV4",
    "PhysicalTransportRuntimeV4Error",
    "PhysicalTransportRuntimeV4FaultLatched",
    "PhysicalTransportRuntimeV4StateError",
    "PhysicalTransportSendPermitV4",
    "PhysicalTransportSendPermitV4Error",
    "PhysicalTransportStaleCallbackV4",
    "PhysicalTransportWriterLeasePortV4",
    "TransportSocketOwnerPortV4",
]

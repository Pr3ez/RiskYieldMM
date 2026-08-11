"""Serialized V4.7B mediator for durable outbound-control writes.

The mediator is deliberately below exchange logic and above a reviewed TLS
writer.  It consumes one durable permit before invoking the writer, invokes
that writer at most once for the exact prepared WebSocket octets, and persists
a signed result before allowing another control dispatch.  The promotion path
is constructed from the exact V4.7 bound socket/clock authority; the legacy
independent test ports remain only for deterministic V4.6 regression tests.
Neither path makes a claim about peer receipt.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from .canonical import (
    CanonicalizationError,
    canonical_hash,
    canonical_identifier,
    canonical_safe_int,
    utc_datetime,
)
from .physical_transport_control_v4 import (
    OutboundControlDispatchDispositionV4,
    OutboundControlDispatchResultV4,
    OutboundControlKindV4,
    OutboundControlWirePreparedV4,
    OutboundControlWritePermitConsumedV4,
)
from .physical_transport_owner_v4 import (
    TransportSocketOwnerBindingV4,
    TransportSocketOwnerSnapshotV4,
)
from .physical_transport_runtime_v4 import ClockEvidenceV4
from .physical_transport_v4 import derive_transport_attestation_key_id


class PhysicalTransportControlRuntimeV4Error(RuntimeError):
    """Base failure at the outbound-control side-effect boundary."""


class PhysicalTransportControlRuntimeV4StateError(
    PhysicalTransportControlRuntimeV4Error
):
    """The requested operation isn't valid in the current lifecycle state."""


class PhysicalTransportControlStaleCallbackV4(PhysicalTransportControlRuntimeV4Error):
    """A callback belongs to a different socket lease or generation."""


class PhysicalTransportControlPermitBindingV4Error(
    PhysicalTransportControlRuntimeV4Error
):
    """Durable permit evidence doesn't bind the exact prepared wire batch."""


class PhysicalTransportControlProtocolDrainV4Error(
    PhysicalTransportControlRuntimeV4Error
):
    """A serializer drain didn't contain exactly one non-empty output."""


class PhysicalTransportControlRuntimeV4FaultLatched(
    PhysicalTransportControlRuntimeV4Error
):
    """Uncertain authority or persistence permanently fenced this mediator."""


class PhysicalTransportControlRuntimeStateV4(str, Enum):
    OPEN = "OPEN"
    DISPATCHING = "DISPATCHING"
    FAULT_LATCHED = "FAULT_LATCHED"
    CLOSED = "CLOSED"


@runtime_checkable
class PhysicalTransportControlJournalPortV4(Protocol):
    def consume_outbound_control_write_permit(
        self,
        outbound_control_wire_prepared_id: str,
        *,
        permit_consumed_at: datetime,
        permit_consumed_monotonic_ns: int,
        idempotency_key: str,
    ) -> OutboundControlWritePermitConsumedV4:
        """Commit and return attempt-one authority before any TLS write."""

    def append_outbound_control_dispatch_result(
        self,
        dispatch: OutboundControlDispatchResultV4,
        *,
        idempotency_key: str,
    ) -> OutboundControlDispatchResultV4:
        """Persist the sole signed outcome for the consumed permit."""


@runtime_checkable
class PermittedControlChunkWriterV4(Protocol):
    async def submit_permitted_chunks(
        self,
        *,
        permit: OutboundControlWritePermitConsumedV4,
        ordered_chunks: tuple[bytes, ...],
    ) -> int:
        """Submit once and return the exact count accepted by the TLS layer."""


@runtime_checkable
class BoundTransportControlAuthorityV4(PermittedControlChunkWriterV4, Protocol):
    """The exact retained owner, governed clock, and sole stream writer."""

    def snapshot(self) -> TransportSocketOwnerSnapshotV4: ...

    def assert_same_owner(self, expected: TransportSocketOwnerSnapshotV4) -> None: ...

    def sample(self) -> ClockEvidenceV4: ...

    async def submit_permitted_chunks(
        self,
        *,
        permit: OutboundControlWritePermitConsumedV4,
        ordered_chunks: tuple[bytes, ...],
        before_driver: Callable[[], None],
    ) -> int: ...

    def abort(self) -> None: ...


ControlRuntimeClockV4 = Callable[[], tuple[datetime, int]]


@dataclass(frozen=True, slots=True)
class _ControlClockSampleV4:
    sampled_at: datetime
    monotonic_before_ns: int
    monotonic_after_ns: int
    uncertainty_milliseconds: int = 0

    @property
    def latest_possible_at(self) -> datetime:
        return self.sampled_at + timedelta(milliseconds=self.uncertainty_milliseconds)


def validate_protocol_drain(outputs: tuple[bytes, ...]) -> tuple[bytes, ...]:
    """Require one serializer output containing one non-empty prepared frame.

    The wire contract validates the RFC 6455 frame itself.  This check closes a
    separate adapter ambiguity: one logical control must correspond to exactly
    one item returned by the Sans-I/O protocol drain.
    """

    if type(outputs) is not tuple or len(outputs) != 1:
        raise PhysicalTransportControlProtocolDrainV4Error(
            "control protocol drain must contain exactly one output"
        )
    output = outputs[0]
    if type(output) is not bytes or not output:
        raise PhysicalTransportControlProtocolDrainV4Error(
            "control protocol drain output must be non-empty bytes"
        )
    return outputs


class _ShortOrInvalidControlWriteV4(RuntimeError):
    """Internal stable error class used for deterministic result evidence."""


class PhysicalTransportControlMediatorV4:
    """Single-owner, no-network mediator for one current physical socket.

    A successful ``SENT`` result means only that the reviewed local writer
    reported accepting every prepared octet.  Exceptions, cancellation, and
    short writes are persisted as ``UNKNOWN_DELIVERY`` and permanently latch
    the mediator so the same logical control cannot be retried.
    """

    _TEST_CONSTRUCTION_TOKEN = object()
    _BOUND_CONSTRUCTION_TOKEN = object()

    @classmethod
    def for_test(cls, **kwargs: Any) -> PhysicalTransportControlMediatorV4:
        """Construct the explicit legacy deterministic regression profile."""

        return cls(_construction_token=cls._TEST_CONSTRUCTION_TOKEN, **kwargs)

    def __init__(
        self,
        *,
        journal: PhysicalTransportControlJournalPortV4,
        writer: PermittedControlChunkWriterV4,
        clock: ControlRuntimeClockV4,
        signer: Any,
        expected_socket_lease_id: str,
        expected_connection_generation: int,
        assert_writer_authority: Callable[[], None],
        _bound_authority: BoundTransportControlAuthorityV4 | None = None,
        _bound_binding: TransportSocketOwnerBindingV4 | None = None,
        _bound_owner_snapshot: TransportSocketOwnerSnapshotV4 | None = None,
        _construction_token: object | None = None,
    ) -> None:
        has_bound_profile = any(
            item is not None
            for item in (_bound_authority, _bound_binding, _bound_owner_snapshot)
        )
        if (
            not has_bound_profile
            and _construction_token is not self._TEST_CONSTRUCTION_TOKEN
        ):
            raise TypeError(
                "use for_test() or from_bound_transport_authority() for construction"
            )
        if (
            has_bound_profile
            and _construction_token is not self._BOUND_CONSTRUCTION_TOKEN
        ):
            raise TypeError(
                "bound control construction requires the derived authority path"
            )
        if not callable(clock):
            raise TypeError("clock must be callable")
        if not callable(assert_writer_authority):
            raise TypeError("assert_writer_authority must be callable")
        self._journal = journal
        self._writer = writer
        self._clock = clock
        self._signer = signer
        self._expected_socket_lease_id = canonical_hash(
            expected_socket_lease_id, field="expected_socket_lease_id"
        )
        self._expected_connection_generation = canonical_safe_int(
            expected_connection_generation,
            field="expected_connection_generation",
            minimum=1,
        )
        self._assert_writer_authority = assert_writer_authority
        self._bound_authority = _bound_authority
        self._bound_binding = _bound_binding
        self._expected_owner_snapshot: TransportSocketOwnerSnapshotV4 | None = None
        if has_bound_profile:
            if (
                not isinstance(_bound_authority, BoundTransportControlAuthorityV4)
                or type(_bound_binding) is not TransportSocketOwnerBindingV4
                or type(_bound_owner_snapshot) is not TransportSocketOwnerSnapshotV4
                or writer is not _bound_authority
            ):
                raise TypeError(
                    "bound control construction requires one exact owner/clock/writer"
                )
            expected_snapshot = _bound_owner_snapshot
            _bound_authority.assert_same_owner(expected_snapshot)
            if _bound_authority.snapshot() != expected_snapshot:
                raise PhysicalTransportControlRuntimeV4Error(
                    "bound control authority changed during construction"
                )
            self._expected_owner_snapshot = expected_snapshot
        self._is_bound_profile = has_bound_profile
        self._is_live_profile = (
            has_bound_profile
            and getattr(_bound_authority, "is_live_profile", False) is True
        )
        self._lock = asyncio.Lock()
        self._state = PhysicalTransportControlRuntimeStateV4.OPEN
        self._fault_cause: str | None = None
        self._attempted_wire_ids: set[str] = set()

    @classmethod
    def from_bound_transport_authority(
        cls,
        *,
        journal: PhysicalTransportControlJournalPortV4,
        authority: BoundTransportControlAuthorityV4,
        binding: TransportSocketOwnerBindingV4,
        signer: Any,
    ) -> PhysicalTransportControlMediatorV4:
        """Derive every control authority field from one committed V4.7 binding."""

        if type(binding) is not TransportSocketOwnerBindingV4:
            raise TypeError("binding must be an exact TransportSocketOwnerBindingV4")
        signer_public_key = getattr(signer, "public_key_bytes", None)
        if (
            type(signer_public_key) is not bytes
            or signer_public_key.hex() != binding.collector_attestation_public_key_hex
            or derive_transport_attestation_key_id(signer_public_key)
            != binding.collector_attestation_key_id
        ):
            raise TypeError(
                "bound control signer differs from the committed collector key"
            )
        assert_fence = getattr(journal, "assert_transport_runtime_writer_fence", None)
        if not callable(assert_fence):
            raise TypeError(
                "bound control journal must expose the runtime writer-fence assertion"
            )

        expected_snapshot = authority.snapshot()
        if type(expected_snapshot) is not TransportSocketOwnerSnapshotV4:
            raise TypeError("bound authority returned an unsupported owner snapshot")
        if any(
            (
                expected_snapshot.kernel_boot_id != binding.kernel_boot_id,
                expected_snapshot.time_namespace_id != binding.time_namespace_id,
                expected_snapshot.network_namespace_id != binding.network_namespace_id,
                expected_snapshot.socket_cookie_u64 != binding.socket_cookie_u64,
                expected_snapshot.clock_resolution_ns != binding.clock_resolution_ns,
                expected_snapshot.socket_identity_profile
                != binding.socket_identity_profile,
                expected_snapshot.clock_profile != binding.clock_profile,
            )
        ):
            raise TypeError(
                "bound authority snapshot differs from canonical owner binding"
            )
        authority.assert_same_owner(expected_snapshot)

        def assert_bound_authority() -> None:
            assert_fence(
                lease_token_sha256=binding.writer_fence_token_sha256,
                generation=binding.writer_fence_generation,
            )
            authority.assert_same_owner(expected_snapshot)

        return cls(
            journal=journal,
            writer=authority,
            clock=lambda: (_ for _ in ()).throw(
                AssertionError("bound control must use governed clock evidence")
            ),
            signer=signer,
            expected_socket_lease_id=binding.socket_lease_id,
            expected_connection_generation=binding.connection_generation,
            assert_writer_authority=assert_bound_authority,
            _bound_authority=authority,
            _bound_binding=binding,
            _bound_owner_snapshot=expected_snapshot,
            _construction_token=cls._BOUND_CONSTRUCTION_TOKEN,
        )

    @property
    def state(self) -> PhysicalTransportControlRuntimeStateV4:
        return self._state

    @property
    def is_bound_profile(self) -> bool:
        return self._is_bound_profile

    @property
    def is_live_profile(self) -> bool:
        return self._is_live_profile

    @property
    def fault_cause(self) -> str | None:
        return self._fault_cause

    async def close(self) -> None:
        """Close after any in-flight dispatch; closing is idempotent."""

        async with self._lock:
            self._state = PhysicalTransportControlRuntimeStateV4.CLOSED
            if self._bound_authority is not None:
                self._bound_authority.abort()

    def _latch(self, *, context: str, cause: BaseException) -> None:
        self._fault_cause = (
            f"{context}: {type(cause).__module__}.{type(cause).__qualname__}"
        )
        self._state = PhysicalTransportControlRuntimeStateV4.FAULT_LATCHED
        if self._bound_authority is not None:
            try:
                self._bound_authority.abort()
            except BaseException as abort_error:
                self._fault_cause += (
                    "; abort="
                    f"{type(abort_error).__module__}.{type(abort_error).__qualname__}"
                )

    def _sample_clock(self) -> _ControlClockSampleV4:
        if self._bound_authority is not None:
            binding = self._bound_binding
            expected_snapshot = self._expected_owner_snapshot
            assert binding is not None and expected_snapshot is not None
            self._bound_authority.assert_same_owner(expected_snapshot)
            evidence = self._bound_authority.sample()
            if type(evidence) is not ClockEvidenceV4:
                raise CanonicalizationError(
                    "bound control clock returned unsupported evidence"
                )
            if (
                not evidence.synchronized
                or evidence.clock_source_manifest_id != binding.clock_source_manifest_id
                or evidence.monotonic_clock_domain_id
                != binding.monotonic_clock_domain_id
                or evidence.clock_resolution_ns != binding.clock_resolution_ns
                or evidence.observation_sha256 is None
                or evidence.selectable_source_count is None
                or (
                    self._is_live_profile
                    and (
                        evidence.chronyd_launch_id
                        != expected_snapshot.chronyd_launch_id
                        or evidence.chronyd_runtime_observation_sha256
                        != expected_snapshot.chronyd_runtime_observation_sha256
                        or evidence.chronyd_launch_id is None
                    )
                )
                or evidence.monotonic_before_ns >= evidence.monotonic_after_ns
                or evidence.valid_until < evidence.sampled_at
            ):
                raise CanonicalizationError(
                    "bound control clock evidence is synthetic, stale, or outside binding"
                )
            self._bound_authority.assert_same_owner(expected_snapshot)
            return _ControlClockSampleV4(
                sampled_at=evidence.sampled_at,
                monotonic_before_ns=evidence.monotonic_before_ns,
                monotonic_after_ns=evidence.monotonic_after_ns,
                uncertainty_milliseconds=evidence.uncertainty_milliseconds,
            )
        sample = self._clock()
        if type(sample) is not tuple or len(sample) != 2:
            raise CanonicalizationError(
                "control runtime clock must return a two-item tuple"
            )
        sampled_at = utc_datetime(sample[0], field="control_clock_sampled_at")
        monotonic_ns = canonical_safe_int(
            sample[1], field="control_clock_monotonic_ns", minimum=0
        )
        return _ControlClockSampleV4(
            sampled_at=sampled_at,
            monotonic_before_ns=monotonic_ns,
            monotonic_after_ns=monotonic_ns,
        )

    @staticmethod
    def _require_strictly_after(
        sample: _ControlClockSampleV4,
        *,
        prior_at: datetime,
        prior_monotonic_ns: int,
        context: str,
    ) -> _ControlClockSampleV4:
        if (
            sample.sampled_at <= prior_at
            or sample.monotonic_before_ns <= prior_monotonic_ns
        ):
            raise PhysicalTransportControlRuntimeV4Error(
                f"{context} must be strictly later in both clock domains"
            )
        return sample

    def _validate_callback(
        self, *, socket_lease_id: str, connection_generation: int
    ) -> None:
        try:
            socket_id = canonical_hash(socket_lease_id, field="socket_lease_id")
            generation = canonical_safe_int(
                connection_generation, field="connection_generation", minimum=1
            )
        except CanonicalizationError as exc:
            raise PhysicalTransportControlStaleCallbackV4(
                "control callback has invalid socket authority"
            ) from exc
        if (
            socket_id != self._expected_socket_lease_id
            or generation != self._expected_connection_generation
        ):
            raise PhysicalTransportControlStaleCallbackV4(
                "control callback belongs to a stale socket lease or generation"
            )

    def _require_open(self) -> None:
        if self._state is PhysicalTransportControlRuntimeStateV4.FAULT_LATCHED:
            raise PhysicalTransportControlRuntimeV4FaultLatched(
                "control runtime has latched an earlier uncertain outcome"
            )
        if self._state is not PhysicalTransportControlRuntimeStateV4.OPEN:
            raise PhysicalTransportControlRuntimeV4StateError(
                f"control dispatch requires OPEN state, found {self._state.value}"
            )

    def _validate_wire(self, wire: OutboundControlWirePreparedV4) -> tuple[bytes, ...]:
        if type(wire) is not OutboundControlWirePreparedV4:
            raise CanonicalizationError(
                "wire must be an exact OutboundControlWirePreparedV4"
            )
        if (
            wire.socket_lease_id != self._expected_socket_lease_id
            or wire.connection_generation != self._expected_connection_generation
        ):
            raise PhysicalTransportControlPermitBindingV4Error(
                "prepared wire differs from current socket authority"
            )
        binding = self._bound_binding
        if binding is not None and any(
            (
                wire.transport_session_id != binding.transport_session_id,
                wire.deployment_bundle_id != binding.deployment_bundle_id,
                wire.writer_fence_token_sha256 != binding.writer_fence_token_sha256,
                wire.writer_fence_generation != binding.writer_fence_generation,
                wire.monotonic_clock_domain_id != binding.monotonic_clock_domain_id,
            )
        ):
            raise PhysicalTransportControlPermitBindingV4Error(
                "prepared wire differs from its exact bound control authority"
            )
        chunks = tuple(
            base64.b64decode(item, validate=True) for item in wire.wire_chunks_base64
        )
        return validate_protocol_drain(chunks)

    @staticmethod
    def _validate_permit_binding(
        permit: OutboundControlWritePermitConsumedV4,
        wire: OutboundControlWirePreparedV4,
        *,
        consumed_at: datetime,
        consumed_monotonic_ns: int,
    ) -> None:
        if type(permit) is not OutboundControlWritePermitConsumedV4:
            raise PhysicalTransportControlPermitBindingV4Error(
                "journal returned an unsupported control permit"
            )
        exact_bindings = (
            (permit.outbound_control_intent_id, wire.outbound_control_intent_id),
            (
                permit.outbound_control_wire_prepared_id,
                wire.outbound_control_wire_prepared_id,
            ),
            (permit.transport_session_id, wire.transport_session_id),
            (permit.socket_lease_id, wire.socket_lease_id),
            (permit.connection_generation, wire.connection_generation),
            (permit.deployment_bundle_id, wire.deployment_bundle_id),
            (
                permit.writer_fence_token_sha256,
                wire.writer_fence_token_sha256,
            ),
            (permit.writer_fence_generation, wire.writer_fence_generation),
            (permit.control_kind, wire.control_kind),
            (permit.wire_batch_sha256, wire.wire_batch_sha256),
            (permit.wire_octet_length, wire.wire_octet_length),
            (permit.one_shot_attempt_ordinal, 1),
            (permit.wire_prepared_at, wire.prepared_at),
            (permit.monotonic_clock_domain_id, wire.monotonic_clock_domain_id),
            (permit.wire_prepared_monotonic_ns, wire.prepared_monotonic_ns),
            (permit.permit_consumed_at, consumed_at),
            (permit.permit_consumed_monotonic_ns, consumed_monotonic_ns),
            (permit.send_not_after, wire.send_not_after),
            (
                permit.send_not_after_monotonic_ns,
                wire.send_not_after_monotonic_ns,
            ),
        )
        if any(actual != expected for actual, expected in exact_bindings):
            raise PhysicalTransportControlPermitBindingV4Error(
                "durable permit doesn't bind the exact prepared wire and clocks"
            )

    @staticmethod
    def _error_class_digest(error: BaseException) -> str:
        qualified_name = f"{type(error).__module__}.{type(error).__qualname__}"
        return hashlib.sha256(qualified_name.encode("utf-8")).hexdigest()

    @staticmethod
    def _dispatch_fields(
        *,
        permit: OutboundControlWritePermitConsumedV4,
        disposition: OutboundControlDispatchDispositionV4,
        dispatch_started_at: datetime,
        dispatch_started_monotonic_ns: int,
        dispatch_outcome_at: datetime,
        dispatch_outcome_monotonic_ns: int,
        bytes_submitted_to_tls: int | None,
        error_class_digest: str | None,
    ) -> dict[str, Any]:
        return {
            "outbound_control_intent_id": permit.outbound_control_intent_id,
            "outbound_control_wire_prepared_id": (
                permit.outbound_control_wire_prepared_id
            ),
            "transport_session_id": permit.transport_session_id,
            "socket_lease_id": permit.socket_lease_id,
            "connection_generation": permit.connection_generation,
            "deployment_bundle_id": permit.deployment_bundle_id,
            "writer_fence_token_sha256": permit.writer_fence_token_sha256,
            "writer_fence_generation": permit.writer_fence_generation,
            "control_kind": permit.control_kind,
            "wire_batch_sha256": permit.wire_batch_sha256,
            "wire_octet_length": permit.wire_octet_length,
            "permit_id": permit.permit_id,
            "permit_consumed": True,
            "one_shot_attempt_ordinal": permit.one_shot_attempt_ordinal,
            "disposition": disposition,
            "wire_prepared_at": permit.wire_prepared_at,
            "monotonic_clock_domain_id": permit.monotonic_clock_domain_id,
            "wire_prepared_monotonic_ns": permit.wire_prepared_monotonic_ns,
            "dispatch_started_at": dispatch_started_at,
            "dispatch_started_monotonic_ns": dispatch_started_monotonic_ns,
            "dispatch_outcome_at": dispatch_outcome_at,
            "dispatch_outcome_monotonic_ns": dispatch_outcome_monotonic_ns,
            "send_not_after": permit.send_not_after,
            "send_not_after_monotonic_ns": permit.send_not_after_monotonic_ns,
            "bytes_submitted_to_tls": bytes_submitted_to_tls,
            "error_class_digest": error_class_digest,
        }

    async def dispatch_prepared(
        self,
        wire: OutboundControlWirePreparedV4,
        *,
        socket_lease_id: str,
        connection_generation: int,
        idempotency_prefix: str,
    ) -> OutboundControlDispatchResultV4:
        """Consume durable authority, write once, and persist the signed result."""

        # Stale callbacks never inspect or mutate current runtime state.
        self._validate_callback(
            socket_lease_id=socket_lease_id,
            connection_generation=connection_generation,
        )
        prefix = canonical_identifier(
            idempotency_prefix, field="idempotency_prefix", maximum=128
        )
        async with self._lock:
            # Recheck after waiting: the callback may have become stale while a
            # prior dispatch completed or closed this owner.
            self._validate_callback(
                socket_lease_id=socket_lease_id,
                connection_generation=connection_generation,
            )
            self._require_open()
            try:
                chunks = self._validate_wire(wire)
            except Exception as exc:
                # An unsupported drain shape or mismatched prepared batch is
                # an adapter invariant breach, not a retryable scheduling
                # condition. No permit exists yet, but this socket owner must
                # stop before later outputs can be reordered or dropped.
                self._latch(context="prepared control drain rejected", cause=exc)
                raise
            wire_id = wire.outbound_control_wire_prepared_id
            if wire_id in self._attempted_wire_ids:
                raise PhysicalTransportControlPermitBindingV4Error(
                    "prepared control wire has already consumed its one-shot attempt"
                )

            try:
                self._assert_writer_authority()
                consumed_sample = self._require_strictly_after(
                    self._sample_clock(),
                    prior_at=wire.prepared_at,
                    prior_monotonic_ns=wire.prepared_monotonic_ns,
                    context="permit consumption",
                )
                consumed_at = consumed_sample.sampled_at
                consumed_ns = consumed_sample.monotonic_after_ns
                if (
                    consumed_sample.latest_possible_at >= wire.send_not_after
                    or consumed_ns >= wire.send_not_after_monotonic_ns
                ):
                    raise PhysicalTransportControlRuntimeV4Error(
                        "prepared control expired before permit consumption"
                    )
                permit = self._journal.consume_outbound_control_write_permit(
                    wire_id,
                    permit_consumed_at=consumed_at,
                    permit_consumed_monotonic_ns=consumed_ns,
                    idempotency_key=f"{prefix}:control-permit:{wire_id}",
                )
            except Exception as exc:
                self._latch(context="control permit consumption failed", cause=exc)
                raise PhysicalTransportControlRuntimeV4FaultLatched(
                    "control permit couldn't be proven durable; writer wasn't invoked"
                ) from exc

            try:
                self._validate_permit_binding(
                    permit,
                    wire,
                    consumed_at=consumed_at,
                    consumed_monotonic_ns=consumed_ns,
                )
            except Exception as exc:
                self._latch(context="durable control permit mismatch", cause=exc)
                raise PhysicalTransportControlRuntimeV4FaultLatched(
                    "durable control permit mismatched; writer wasn't invoked"
                ) from exc

            self._attempted_wire_ids.add(wire_id)
            self._state = PhysicalTransportControlRuntimeStateV4.DISPATCHING
            started_at: datetime | None = None
            started_ns: int | None = None
            driver_boundary_entered = False

            def before_driver() -> None:
                """Run inside the bound owner's shared lock immediately pre-write."""

                nonlocal driver_boundary_entered, started_at, started_ns
                if driver_boundary_entered or started_at is not None:
                    raise PhysicalTransportControlRuntimeV4Error(
                        "control driver-boundary guard was invoked more than once"
                    )
                self._assert_writer_authority()
                started_sample = self._require_strictly_after(
                    self._sample_clock(),
                    prior_at=permit.permit_consumed_at,
                    prior_monotonic_ns=permit.permit_consumed_monotonic_ns,
                    context="dispatch start",
                )
                if (
                    started_sample.latest_possible_at >= permit.send_not_after
                    or started_sample.monotonic_after_ns
                    >= permit.send_not_after_monotonic_ns
                ):
                    raise PhysicalTransportControlRuntimeV4Error(
                        "control deadline elapsed inside the shared writer lock"
                    )
                started_at = started_sample.sampled_at
                started_ns = started_sample.monotonic_after_ns
                driver_boundary_entered = True

            # A consumed permit isn't evidence that a write started.  If
            # authority, clocks, or the deadline fail before the call boundary,
            # preserve a permit-without-result crash prefix and latch.  Never
            # invent dispatch clocks for an invocation that didn't happen.
            try:
                if self._bound_authority is None:
                    before_driver()
            except Exception as exc:
                self._latch(context="pre-writer dispatch admission failed", cause=exc)
                raise PhysicalTransportControlRuntimeV4FaultLatched(
                    "permit was consumed but the writer invocation never began"
                ) from exc

            writer_error: BaseException | None = None
            submitted: int | None
            try:
                if self._bound_authority is None:
                    writer_result = await self._writer.submit_permitted_chunks(
                        permit=permit,
                        ordered_chunks=chunks,
                    )
                else:
                    writer_result = await self._bound_authority.submit_permitted_chunks(
                        permit=permit,
                        ordered_chunks=chunks,
                        before_driver=before_driver,
                    )
                if (
                    not driver_boundary_entered
                    or started_at is None
                    or started_ns is None
                ):
                    raise PhysicalTransportControlRuntimeV4Error(
                        "bound owner returned without invoking its locked guard"
                    )
                if (
                    type(writer_result) is not int
                    or writer_result < 0
                    or writer_result > permit.wire_octet_length
                ):
                    writer_error = _ShortOrInvalidControlWriteV4(
                        "writer returned an invalid submitted-octet count"
                    )
                    submitted = None
                else:
                    submitted = writer_result
                    if submitted != permit.wire_octet_length:
                        writer_error = _ShortOrInvalidControlWriteV4(
                            "writer accepted fewer than all prepared octets"
                        )
            except BaseException as exc:
                if not driver_boundary_entered:
                    self._latch(
                        context="locked pre-writer dispatch admission failed",
                        cause=exc,
                    )
                    raise PhysicalTransportControlRuntimeV4FaultLatched(
                        "permit was consumed but the locked writer boundary rejected it"
                    ) from exc
                # Once awaited, an exception or cancellation cannot prove how
                # much of the prefix reached TLS.  ``None`` is evidence of that
                # uncertainty; zero would be a fabricated delivery fact.
                writer_error = exc
                submitted = None

            assert started_at is not None and started_ns is not None
            if writer_error is None:
                try:
                    self._assert_writer_authority()
                except Exception as exc:
                    writer_error = exc
            try:
                outcome_sample = self._require_strictly_after(
                    self._sample_clock(),
                    prior_at=started_at,
                    prior_monotonic_ns=started_ns,
                    context="dispatch outcome",
                )
                outcome_at = outcome_sample.sampled_at
                outcome_ns = outcome_sample.monotonic_after_ns
            except Exception as exc:
                self._latch(
                    context="post-writer dispatch clocks unavailable",
                    cause=exc,
                )
                raise PhysicalTransportControlRuntimeV4FaultLatched(
                    "writer was invoked but signed outcome clocks are unavailable"
                ) from exc

            disposition = (
                OutboundControlDispatchDispositionV4.SENT
                if writer_error is None
                else OutboundControlDispatchDispositionV4.UNKNOWN_DELIVERY
            )
            error_digest = (
                None if writer_error is None else self._error_class_digest(writer_error)
            )
            try:
                dispatch = OutboundControlDispatchResultV4.create_signed(
                    signer=self._signer,
                    **self._dispatch_fields(
                        permit=permit,
                        disposition=disposition,
                        dispatch_started_at=started_at,
                        dispatch_started_monotonic_ns=started_ns,
                        dispatch_outcome_at=outcome_at,
                        dispatch_outcome_monotonic_ns=outcome_ns,
                        bytes_submitted_to_tls=submitted,
                        error_class_digest=error_digest,
                    ),
                )
                persisted = self._journal.append_outbound_control_dispatch_result(
                    dispatch,
                    idempotency_key=f"{prefix}:control-result:{permit.permit_id}",
                )
                if (
                    type(persisted) is not OutboundControlDispatchResultV4
                    or persisted != dispatch
                ):
                    raise PhysicalTransportControlRuntimeV4Error(
                        "journal returned different control dispatch evidence"
                    )
            except BaseException as exc:
                self._latch(context="control result persistence failed", cause=exc)
                raise PhysicalTransportControlRuntimeV4FaultLatched(
                    "control write occurred but its signed result isn't durable"
                ) from exc

            if writer_error is not None:
                self._latch(context="control delivery is uncertain", cause=writer_error)
            elif permit.control_kind in {
                OutboundControlKindV4.RFC_CLOSE_REPLY,
                OutboundControlKindV4.RFC_PROTOCOL_FAILURE_CLOSE,
            }:
                self._state = PhysicalTransportControlRuntimeStateV4.CLOSED
            else:
                self._state = PhysicalTransportControlRuntimeStateV4.OPEN

            if isinstance(writer_error, asyncio.CancelledError):
                raise writer_error
            if writer_error is not None and not isinstance(writer_error, Exception):
                raise writer_error
            return persisted


__all__ = [
    "BoundTransportControlAuthorityV4",
    "ControlRuntimeClockV4",
    "PermittedControlChunkWriterV4",
    "PhysicalTransportControlJournalPortV4",
    "PhysicalTransportControlMediatorV4",
    "PhysicalTransportControlPermitBindingV4Error",
    "PhysicalTransportControlProtocolDrainV4Error",
    "PhysicalTransportControlRuntimeStateV4",
    "PhysicalTransportControlRuntimeV4Error",
    "PhysicalTransportControlRuntimeV4FaultLatched",
    "PhysicalTransportControlRuntimeV4StateError",
    "PhysicalTransportControlStaleCallbackV4",
    "validate_protocol_drain",
]

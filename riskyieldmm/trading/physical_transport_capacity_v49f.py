"""Bounded single-session transport admission contracts for V4.9F-A1.

This module replaces implicit, unbounded waiting on an ``asyncio.Lock`` with a
small explicit protocol: a deployment-bound policy, FIFO tickets, simultaneous
count/work reservations, an absolute start deadline, and cancellation-safe
capacity release.

The gate is deliberately local and in-memory.  It is not a durable overload
event, a cross-session scheduler, a parser work quantum, or proof of production
capacity.  A caller must enter the returned admission context before performing
any socket, TLS, journal, or send effect.
"""

from __future__ import annotations

import asyncio
import math
from collections import deque
from collections.abc import Mapping
from contextvars import ContextVar, Token
from dataclasses import dataclass
from enum import Enum
from typing import Any, ClassVar

from .canonical import (
    CANONICALIZATION_VERSION,
    CanonicalizationError,
    canonical_hash,
    canonical_safe_int,
    require_exact_keys,
    sha256_digest,
)

TRANSPORT_CAPACITY_POLICY_SCHEMA_VERSION_V49F = (
    "riskyieldmm_transport_capacity_policy_v4_9f_a1"
)
TRANSPORT_CAPACITY_PROFILE_V49F = "BOUNDED_SINGLE_SESSION_FIFO_TICKETS_V49F_A1"
_NANOSECONDS_PER_SECOND = 1_000_000_000


def _loop_time_nanoseconds(loop_time: float) -> int:
    """Canonicalize one event-loop timestamp before deriving durations."""

    return int(loop_time * _NANOSECONDS_PER_SECOND)


class TransportCommandKindV49F(str, Enum):
    """Actor-ordered commands admitted by the local V4.9F-A1 gate."""

    ACK_DEADLINE_EXPIRY = "ACK_DEADLINE_EXPIRY"
    INGRESS = "INGRESS"
    LOCAL_SHUTDOWN = "LOCAL_SHUTDOWN"
    SUBSCRIPTION_DISPATCH = "SUBSCRIPTION_DISPATCH"


class TransportAdmissionLifecycleV49F(str, Enum):
    """Exact in-memory ticket states; none is durable transport evidence."""

    WAITING = "WAITING"
    GRANTED = "GRANTED"
    ENTERED = "ENTERED"
    CANCELLED = "CANCELLED"
    RELEASED = "RELEASED"


class TransportAdmissionErrorV49F(RuntimeError):
    """Base class for local admission failures before transport effects."""


class TransportAdmissionRejectedV49F(TransportAdmissionErrorV49F):
    """Raised when an atomic count/work reservation cannot be admitted."""


class TransportAdmissionDeadlineExceededV49F(TransportAdmissionErrorV49F):
    """Raised when a queued command did not start by its absolute deadline."""


class TransportAdmissionClosedV49F(TransportAdmissionErrorV49F):
    """Raised when a command targets a gate that no longer accepts work."""


class TransportAdmissionTerminalBarrierV49F(TransportAdmissionErrorV49F):
    """Raised when a prior shutdown ticket closed this command epoch."""


class TransportAdmissionStateErrorV49F(TransportAdmissionErrorV49F):
    """Raised for cross-loop, reentrant, duplicate-release, or misuse paths."""


@dataclass(frozen=True, slots=True, kw_only=True)
class TransportCapacityPolicyV49F:
    """Versioned capacity limits nested in the signed runtime manifest.

    Work units are deliberately abstract in A1.  Each command reserves its
    frozen worst-case local admission cost.  Empirical byte/parser/database
    weights and cross-session scheduling belong to later V4.9F slices.
    """

    maximum_active_and_waiting_commands: int
    maximum_reserved_work_units: int
    maximum_queue_wait_milliseconds: int
    ingress_reservation_work_units: int
    subscription_dispatch_reservation_work_units: int
    ack_deadline_expiry_reservation_work_units: int
    local_shutdown_reservation_work_units: int
    profile: str = TRANSPORT_CAPACITY_PROFILE_V49F

    _FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            "ack_deadline_expiry_reservation_work_units",
            "ingress_reservation_work_units",
            "local_shutdown_reservation_work_units",
            "maximum_active_and_waiting_commands",
            "maximum_queue_wait_milliseconds",
            "maximum_reserved_work_units",
            "profile",
            "subscription_dispatch_reservation_work_units",
        }
    )

    def __post_init__(self) -> None:
        if self.profile != TRANSPORT_CAPACITY_PROFILE_V49F:
            raise CanonicalizationError("unsupported V4.9F transport capacity profile")
        object.__setattr__(self, "profile", TRANSPORT_CAPACITY_PROFILE_V49F)
        object.__setattr__(
            self,
            "maximum_active_and_waiting_commands",
            canonical_safe_int(
                self.maximum_active_and_waiting_commands,
                field="maximum_active_and_waiting_commands",
                minimum=1,
                maximum=65_536,
            ),
        )
        object.__setattr__(
            self,
            "maximum_reserved_work_units",
            canonical_safe_int(
                self.maximum_reserved_work_units,
                field="maximum_reserved_work_units",
                minimum=1,
                maximum=2**53 - 1,
            ),
        )
        object.__setattr__(
            self,
            "maximum_queue_wait_milliseconds",
            canonical_safe_int(
                self.maximum_queue_wait_milliseconds,
                field="maximum_queue_wait_milliseconds",
                minimum=1,
                maximum=300_000,
            ),
        )
        for field_name in (
            "ingress_reservation_work_units",
            "subscription_dispatch_reservation_work_units",
            "ack_deadline_expiry_reservation_work_units",
            "local_shutdown_reservation_work_units",
        ):
            value = canonical_safe_int(
                getattr(self, field_name),
                field=field_name,
                minimum=1,
                maximum=self.maximum_reserved_work_units,
            )
            object.__setattr__(self, field_name, value)
        if self.maximum_active_and_waiting_commands != len(TransportCommandKindV49F):
            raise CanonicalizationError(
                "V4.9F-A1 requires exactly one slot for each command kind"
            )
        total_reservation = sum(
            self.reservation_work_units(kind) for kind in TransportCommandKindV49F
        )
        if self.maximum_reserved_work_units != total_reservation:
            raise CanonicalizationError(
                "V4.9F-A1 work capacity must reserve every command kind exactly once"
            )

    def reservation_work_units(self, kind: TransportCommandKindV49F) -> int:
        """Return the exact signed reservation for one command class."""

        if type(kind) is not TransportCommandKindV49F:
            raise TypeError("kind must be an exact TransportCommandKindV49F")
        return {
            TransportCommandKindV49F.INGRESS: self.ingress_reservation_work_units,
            TransportCommandKindV49F.SUBSCRIPTION_DISPATCH: (
                self.subscription_dispatch_reservation_work_units
            ),
            TransportCommandKindV49F.ACK_DEADLINE_EXPIRY: (
                self.ack_deadline_expiry_reservation_work_units
            ),
            TransportCommandKindV49F.LOCAL_SHUTDOWN: (
                self.local_shutdown_reservation_work_units
            ),
        }[kind]

    def identity_payload(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self._FIELDS}

    @property
    def policy_id(self) -> str:
        return sha256_digest(
            {
                "canonicalization_version": CANONICALIZATION_VERSION,
                "domain": "RiskYieldMMTransportCapacityPolicyIdentityV4_9F_A1",
                "payload": self.identity_payload(),
                "schema_version": TRANSPORT_CAPACITY_POLICY_SCHEMA_VERSION_V49F,
            }
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonicalization_version": CANONICALIZATION_VERSION,
            **self.identity_payload(),
            "policy_id": self.policy_id,
            "schema_version": TRANSPORT_CAPACITY_POLICY_SCHEMA_VERSION_V49F,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> TransportCapacityPolicyV49F:
        require_exact_keys(
            payload,
            expected=cls._FIELDS
            | {
                "canonicalization_version",
                "policy_id",
                "schema_version",
            },
            context=cls.__name__,
        )
        if payload["canonicalization_version"] != CANONICALIZATION_VERSION:
            raise CanonicalizationError(
                "transport capacity canonicalization version differs"
            )
        if payload["schema_version"] != TRANSPORT_CAPACITY_POLICY_SCHEMA_VERSION_V49F:
            raise CanonicalizationError("transport capacity schema version differs")
        item = cls(**{name: payload[name] for name in cls._FIELDS})
        expected = canonical_hash(payload["policy_id"], field="policy_id")
        if expected != item.policy_id:
            raise CanonicalizationError(
                "transport capacity policy ID differs from canonical members"
            )
        return item


@dataclass(frozen=True, slots=True, kw_only=True)
class TransportAdmissionGrantV49F:
    """Immutable evidence that one in-memory ticket reached STARTED."""

    policy_id: str
    admission_epoch: int
    admission_sequence: int
    command_kind: TransportCommandKindV49F
    reservation_work_units: int
    admitted_loop_time_ns: int
    started_loop_time_ns: int
    start_deadline_loop_time_ns: int

    @property
    def queue_wait_nanoseconds(self) -> int:
        return self.started_loop_time_ns - self.admitted_loop_time_ns


@dataclass(frozen=True, slots=True, kw_only=True)
class TransportAdmissionSnapshotV49F:
    """Read-only local observability for the bounded admission gate."""

    policy_id: str
    admission_epoch: int
    closed: bool
    terminal_barrier_admission_sequence: int | None
    terminal_barrier_committed: bool
    active_admission_sequence: int | None
    active_command_kind: TransportCommandKindV49F | None
    waiting_admission_sequences: tuple[int, ...]
    waiting_command_kinds: tuple[TransportCommandKindV49F, ...]
    oldest_waiting_age_nanoseconds: int
    reserved_work_units: int
    maximum_observed_admitted_commands: int
    maximum_observed_reserved_work_units: int
    last_started_queue_wait_nanoseconds: int
    maximum_observed_queue_wait_nanoseconds: int
    rejected_commands: int
    duplicate_kind_rejections: int
    terminal_barrier_rejections: int
    capacity_rejections: int
    closed_rejections: int
    timed_out_commands: int
    cancelled_before_entry_commands: int
    closed_before_entry_commands: int
    released_commands: int

    @property
    def active_and_waiting_commands(self) -> int:
        return (1 if self.active_admission_sequence is not None else 0) + len(
            self.waiting_admission_sequences
        )


@dataclass(slots=True)
class _PendingAdmissionV49F:
    epoch: int
    sequence: int
    command_kind: TransportCommandKindV49F
    reservation_work_units: int
    admitted_loop_time: float
    start_deadline_loop_time: float
    owner_task: asyncio.Task[Any]
    ready: asyncio.Future[None]
    lifecycle: TransportAdmissionLifecycleV49F
    granted_loop_time: float | None = None
    started_loop_time: float | None = None
    grant: TransportAdmissionGrantV49F | None = None
    closed_before_start: bool = False
    released: bool = False


class _TransportAdmissionContextV49F:
    def __init__(
        self,
        gate: BoundedTransportAdmissionGateV49F,
        kind: TransportCommandKindV49F,
        absolute_start_deadline_loop_time: float | None,
    ) -> None:
        self._gate = gate
        self._kind = kind
        self._absolute_start_deadline_loop_time = absolute_start_deadline_loop_time
        self._pending: _PendingAdmissionV49F | None = None
        self._grant: TransportAdmissionGrantV49F | None = None
        self._context_token: Token[frozenset[object]] | None = None

    async def __aenter__(self) -> TransportAdmissionGrantV49F:
        if self._pending is not None:
            raise TransportAdmissionStateErrorV49F(
                "one admission context cannot be entered twice"
            )
        pending, grant = await self._gate._acquire(  # noqa: SLF001
            self._kind,
            absolute_start_deadline_loop_time=(self._absolute_start_deadline_loop_time),
        )
        self._pending = pending
        self._grant = grant
        if pending.lifecycle is not TransportAdmissionLifecycleV49F.GRANTED:
            self._gate._discard_without_caller_effect(pending)  # noqa: SLF001
            raise TransportAdmissionStateErrorV49F(
                "transport admission did not reach the exact GRANTED state"
            )
        pending.lifecycle = TransportAdmissionLifecycleV49F.ENTERED
        active_contexts = _ACTIVE_TRANSPORT_ADMISSION_CONTEXTS_V49F.get()
        self._context_token = _ACTIVE_TRANSPORT_ADMISSION_CONTEXTS_V49F.set(
            active_contexts | {self._gate._context_identity}  # noqa: SLF001
        )
        return grant

    async def __aexit__(self, *_: object) -> None:
        pending = self._pending
        if pending is None or self._grant is None or self._context_token is None:
            raise TransportAdmissionStateErrorV49F(
                "an admission context cannot exit before successful entry"
            )
        try:
            self._gate._release(pending)  # noqa: SLF001
        finally:
            _ACTIVE_TRANSPORT_ADMISSION_CONTEXTS_V49F.reset(self._context_token)
            self._context_token = None
            self._grant = None


_ACTIVE_TRANSPORT_ADMISSION_CONTEXTS_V49F: ContextVar[frozenset[object]] = ContextVar(
    "riskyieldmm_active_transport_admission_contexts_v49f", default=frozenset()
)


class BoundedTransportAdmissionGateV49F:
    """Loop-bound, cancellation-safe FIFO gate for one physical session.

    All mutations happen without an intervening ``await`` on one bound event
    loop.  This makes reservation/start/release transitions atomic with respect
    to other coroutines while keeping release non-cancellable.  Like asyncio's
    native primitives, this object is intentionally not thread-safe.
    """

    def __init__(self, policy: TransportCapacityPolicyV49F) -> None:
        if type(policy) is not TransportCapacityPolicyV49F:
            raise TypeError("policy must be an exact TransportCapacityPolicyV49F")
        self._policy = policy
        self._context_identity = object()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._waiting: deque[_PendingAdmissionV49F] = deque()
        self._active: _PendingAdmissionV49F | None = None
        self._next_sequence = 1
        self._epoch = 1
        self._reserved_work_units = 0
        self._closed = False
        self._terminal_barrier_admission_sequence: int | None = None
        self._terminal_barrier_committed = False
        self._maximum_observed_admitted_commands = 0
        self._maximum_observed_reserved_work_units = 0
        self._last_started_queue_wait_nanoseconds = 0
        self._maximum_observed_queue_wait_nanoseconds = 0
        self._rejected_commands = 0
        self._duplicate_kind_rejections = 0
        self._terminal_barrier_rejections = 0
        self._capacity_rejections = 0
        self._closed_rejections = 0
        self._timed_out_commands = 0
        self._cancelled_before_entry_commands = 0
        self._closed_before_entry_commands = 0
        self._released_commands = 0

    @property
    def policy(self) -> TransportCapacityPolicyV49F:
        return self._policy

    def _bind_running_loop(self) -> asyncio.AbstractEventLoop:
        loop = asyncio.get_running_loop()
        if self._loop is None:
            self._loop = loop
        elif self._loop is not loop:
            raise TransportAdmissionStateErrorV49F(
                "transport admission gate cannot cross event loops"
            )
        return loop

    def _admitted_count(self) -> int:
        return (1 if self._active is not None else 0) + len(self._waiting)

    def admit(
        self,
        kind: TransportCommandKindV49F,
        *,
        absolute_start_deadline_loop_time: float | None = None,
    ) -> _TransportAdmissionContextV49F:
        """Return a context that grants STARTED or fails before caller effects."""

        if type(kind) is not TransportCommandKindV49F:
            raise TypeError("kind must be an exact TransportCommandKindV49F")
        if absolute_start_deadline_loop_time is not None and (
            type(absolute_start_deadline_loop_time) not in {int, float}
            or not math.isfinite(float(absolute_start_deadline_loop_time))
        ):
            raise TypeError("absolute start deadline must be one finite loop time")
        return _TransportAdmissionContextV49F(
            self,
            kind,
            (
                None
                if absolute_start_deadline_loop_time is None
                else float(absolute_start_deadline_loop_time)
            ),
        )

    async def _acquire(
        self,
        kind: TransportCommandKindV49F,
        *,
        absolute_start_deadline_loop_time: float | None,
    ) -> tuple[_PendingAdmissionV49F, TransportAdmissionGrantV49F]:
        loop = self._bind_running_loop()
        owner_task = asyncio.current_task()
        if owner_task is None:
            raise TransportAdmissionStateErrorV49F(
                "transport admission requires one current asyncio task"
            )
        if self._active is not None and self._active.owner_task is owner_task:
            raise TransportAdmissionStateErrorV49F(
                "reentrant transport admission would deadlock its own FIFO"
            )
        if self._context_identity in _ACTIVE_TRANSPORT_ADMISSION_CONTEXTS_V49F.get():
            raise TransportAdmissionStateErrorV49F(
                "inherited transport admission context cannot re-enter this runtime"
            )
        if self._closed:
            self._rejected_commands += 1
            self._closed_rejections += 1
            raise TransportAdmissionClosedV49F(
                "transport admission gate no longer accepts commands"
            )
        if self._terminal_barrier_admission_sequence is not None:
            self._rejected_commands += 1
            self._terminal_barrier_rejections += 1
            raise TransportAdmissionTerminalBarrierV49F(
                "an admitted shutdown already closed this command epoch"
            )
        outstanding_kinds = {pending.command_kind for pending in self._waiting}
        if self._active is not None:
            outstanding_kinds.add(self._active.command_kind)
        if kind in outstanding_kinds:
            self._rejected_commands += 1
            self._duplicate_kind_rejections += 1
            raise TransportAdmissionRejectedV49F(
                "only one outstanding ticket per transport command kind is allowed"
            )

        reservation = self._policy.reservation_work_units(kind)
        if (
            self._admitted_count() >= self._policy.maximum_active_and_waiting_commands
            or self._reserved_work_units + reservation
            > self._policy.maximum_reserved_work_units
        ):
            self._rejected_commands += 1
            self._capacity_rejections += 1
            raise TransportAdmissionRejectedV49F(
                "transport command exceeds the signed count/work admission limits"
            )

        admitted = loop.time()
        policy_deadline = admitted + (
            self._policy.maximum_queue_wait_milliseconds / 1000
        )
        deadline = (
            policy_deadline
            if absolute_start_deadline_loop_time is None
            else min(policy_deadline, absolute_start_deadline_loop_time)
        )
        pending = _PendingAdmissionV49F(
            epoch=self._epoch,
            sequence=self._next_sequence,
            command_kind=kind,
            reservation_work_units=reservation,
            admitted_loop_time=admitted,
            start_deadline_loop_time=deadline,
            owner_task=owner_task,
            ready=loop.create_future(),
            lifecycle=TransportAdmissionLifecycleV49F.WAITING,
        )
        self._next_sequence += 1
        self._waiting.append(pending)
        if kind is TransportCommandKindV49F.LOCAL_SHUTDOWN:
            self._terminal_barrier_admission_sequence = pending.sequence
        self._reserved_work_units += reservation
        self._maximum_observed_admitted_commands = max(
            self._maximum_observed_admitted_commands,
            self._admitted_count(),
        )
        self._maximum_observed_reserved_work_units = max(
            self._maximum_observed_reserved_work_units,
            self._reserved_work_units,
        )
        self._start_next_if_idle()

        try:
            remaining = max(0.0, deadline - loop.time())
            done, _ = await asyncio.wait(
                (pending.ready,),
                timeout=remaining,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if pending.ready not in done:
                raise TransportAdmissionDeadlineExceededV49F(
                    "transport command did not start by its absolute admission deadline"
                )
            pending.ready.result()
            if pending.closed_before_start:
                raise TransportAdmissionClosedV49F(
                    "transport admission closed before this queued command started"
                )
        except asyncio.CancelledError:
            if self._discard_without_caller_effect(pending):
                self._cancelled_before_entry_commands += 1
            raise
        except TransportAdmissionDeadlineExceededV49F:
            if self._discard_without_caller_effect(pending):
                self._timed_out_commands += 1
            raise
        except BaseException:
            self._discard_without_caller_effect(pending)
            raise

        # GRANTED only transfers the local reservation to this caller task.  It
        # isn't permission to begin effects until the task actually resumes.
        # Recheck the absolute deadline at that final pre-effect boundary so a
        # stalled event loop cannot turn an on-time grant into a late effect.
        started = loop.time()
        if started > pending.start_deadline_loop_time:
            if self._discard_without_caller_effect(pending):
                self._timed_out_commands += 1
            raise TransportAdmissionDeadlineExceededV49F(
                "transport command resumed after its absolute admission deadline"
            )
        pending.started_loop_time = started
        admitted_loop_time_ns = _loop_time_nanoseconds(pending.admitted_loop_time)
        started_loop_time_ns = _loop_time_nanoseconds(started)
        start_deadline_loop_time_ns = _loop_time_nanoseconds(
            pending.start_deadline_loop_time
        )
        queue_wait_nanoseconds = started_loop_time_ns - admitted_loop_time_ns
        self._last_started_queue_wait_nanoseconds = queue_wait_nanoseconds
        self._maximum_observed_queue_wait_nanoseconds = max(
            self._maximum_observed_queue_wait_nanoseconds,
            queue_wait_nanoseconds,
        )
        grant = TransportAdmissionGrantV49F(
            policy_id=self._policy.policy_id,
            admission_epoch=pending.epoch,
            admission_sequence=pending.sequence,
            command_kind=pending.command_kind,
            reservation_work_units=pending.reservation_work_units,
            admitted_loop_time_ns=admitted_loop_time_ns,
            started_loop_time_ns=started_loop_time_ns,
            start_deadline_loop_time_ns=start_deadline_loop_time_ns,
        )
        pending.grant = grant
        return pending, grant

    def _start_next_if_idle(self) -> None:
        if self._active is not None or not self._waiting:
            return
        pending = self._waiting.popleft()
        loop = self._loop
        assert loop is not None
        pending.granted_loop_time = loop.time()
        pending.lifecycle = TransportAdmissionLifecycleV49F.GRANTED
        self._active = pending
        if not pending.ready.done():
            pending.ready.set_result(None)

    def _discard_without_caller_effect(self, pending: _PendingAdmissionV49F) -> bool:
        if pending.released:
            return False
        if self._active is pending:
            self._active = None
        else:
            try:
                self._waiting.remove(pending)
            except ValueError:
                pass
        if (
            pending.command_kind is TransportCommandKindV49F.LOCAL_SHUTDOWN
            and pending.lifecycle
            in {
                TransportAdmissionLifecycleV49F.WAITING,
                TransportAdmissionLifecycleV49F.GRANTED,
            }
            and self._terminal_barrier_admission_sequence == pending.sequence
        ):
            self._terminal_barrier_admission_sequence = None
        pending.lifecycle = TransportAdmissionLifecycleV49F.CANCELLED
        pending.released = True
        self._reserved_work_units -= pending.reservation_work_units
        if self._reserved_work_units < 0:
            raise TransportAdmissionStateErrorV49F(
                "transport admission reservation accounting underflowed"
            )
        self._start_next_if_idle()
        return True

    def _release(self, pending: _PendingAdmissionV49F) -> None:
        if pending.released or self._active is not pending:
            raise TransportAdmissionStateErrorV49F(
                "transport admission grant was released twice or out of order"
            )
        if pending.lifecycle is not TransportAdmissionLifecycleV49F.ENTERED:
            raise TransportAdmissionStateErrorV49F(
                "only an ENTERED transport admission may be released"
            )
        if (
            pending.command_kind is TransportCommandKindV49F.LOCAL_SHUTDOWN
            and not self._terminal_barrier_committed
            and self._terminal_barrier_admission_sequence == pending.sequence
        ):
            self._terminal_barrier_admission_sequence = None
        pending.lifecycle = TransportAdmissionLifecycleV49F.RELEASED
        pending.released = True
        self._active = None
        self._reserved_work_units -= pending.reservation_work_units
        if self._reserved_work_units < 0:
            raise TransportAdmissionStateErrorV49F(
                "transport admission reservation accounting underflowed"
            )
        self._released_commands += 1
        self._start_next_if_idle()

    def commit_terminal_barrier(self, grant: TransportAdmissionGrantV49F) -> None:
        """Make the shutdown barrier irreversible after durable command evidence."""

        if type(grant) is not TransportAdmissionGrantV49F:
            raise TypeError("grant must be an exact TransportAdmissionGrantV49F")
        self.assert_active_grant(
            grant,
            expected_kind=TransportCommandKindV49F.LOCAL_SHUTDOWN,
        )
        pending = self._active
        assert pending is not None
        if self._terminal_barrier_admission_sequence != pending.sequence:
            raise TransportAdmissionStateErrorV49F(
                "only the exact active shutdown admission may commit its barrier"
            )
        self._terminal_barrier_committed = True

    def assert_active_grant(
        self,
        grant: TransportAdmissionGrantV49F,
        *,
        expected_kind: TransportCommandKindV49F,
    ) -> None:
        """Reject direct effect-helper calls without the exact active lease."""

        if type(grant) is not TransportAdmissionGrantV49F:
            raise TransportAdmissionStateErrorV49F(
                "effect-capable helper requires an exact transport admission grant"
            )
        if type(expected_kind) is not TransportCommandKindV49F:
            raise TypeError("expected_kind must be an exact TransportCommandKindV49F")
        pending = self._active
        if (
            pending is None
            or pending.lifecycle is not TransportAdmissionLifecycleV49F.ENTERED
            or pending.owner_task is not asyncio.current_task()
            or pending.grant is not grant
            or pending.epoch != grant.admission_epoch
            or pending.sequence != grant.admission_sequence
            or pending.command_kind is not expected_kind
            or grant.command_kind is not expected_kind
            or grant.policy_id != self._policy.policy_id
            or grant.reservation_work_units != pending.reservation_work_units
            or grant.admitted_loop_time_ns
            != _loop_time_nanoseconds(pending.admitted_loop_time)
            or pending.started_loop_time is None
            or grant.started_loop_time_ns
            != _loop_time_nanoseconds(pending.started_loop_time)
            or grant.start_deadline_loop_time_ns
            != _loop_time_nanoseconds(pending.start_deadline_loop_time)
            or self._context_identity
            not in _ACTIVE_TRANSPORT_ADMISSION_CONTEXTS_V49F.get()
        ):
            raise TransportAdmissionStateErrorV49F(
                "transport admission grant is not active for this task, epoch, and kind"
            )

    def close(self) -> None:
        """Reject future work and settle every not-yet-started ticket.

        Already-started transport work is not cancelled here because only the
        actor's physical effect/outcome protocol can classify that boundary.
        Its context may finish and release normally.
        """

        self._closed = True
        waiting = tuple(self._waiting)
        self._waiting.clear()
        for pending in waiting:
            if (
                pending.command_kind is TransportCommandKindV49F.LOCAL_SHUTDOWN
                and self._terminal_barrier_admission_sequence == pending.sequence
                and not self._terminal_barrier_committed
            ):
                self._terminal_barrier_admission_sequence = None
            pending.closed_before_start = True
            pending.lifecycle = TransportAdmissionLifecycleV49F.CANCELLED
            pending.released = True
            self._closed_before_entry_commands += 1
            self._reserved_work_units -= pending.reservation_work_units
            if not pending.ready.done():
                pending.ready.set_result(None)
        if self._reserved_work_units < 0:
            raise TransportAdmissionStateErrorV49F(
                "transport admission reservation accounting underflowed"
            )

    def advance_epoch(self) -> int:
        """Reset a quiescent fenced session without allowing stale tickets."""

        if self._closed:
            raise TransportAdmissionClosedV49F(
                "a closed transport admission gate cannot advance epochs"
            )
        if self._active is not None or self._waiting or self._reserved_work_units:
            raise TransportAdmissionStateErrorV49F(
                "transport admission epoch can advance only while quiescent"
            )
        self._epoch += 1
        self._terminal_barrier_admission_sequence = None
        self._terminal_barrier_committed = False
        return self._epoch

    def snapshot(self) -> TransportAdmissionSnapshotV49F:
        active = self._active
        loop = self._loop
        oldest_waiting_age_nanoseconds = (
            0
            if not self._waiting or loop is None
            else max(
                0,
                _loop_time_nanoseconds(loop.time())
                - _loop_time_nanoseconds(self._waiting[0].admitted_loop_time),
            )
        )
        return TransportAdmissionSnapshotV49F(
            policy_id=self._policy.policy_id,
            admission_epoch=self._epoch,
            closed=self._closed,
            terminal_barrier_admission_sequence=(
                self._terminal_barrier_admission_sequence
            ),
            terminal_barrier_committed=self._terminal_barrier_committed,
            active_admission_sequence=(None if active is None else active.sequence),
            active_command_kind=(None if active is None else active.command_kind),
            waiting_admission_sequences=tuple(
                pending.sequence for pending in self._waiting
            ),
            waiting_command_kinds=tuple(
                pending.command_kind for pending in self._waiting
            ),
            oldest_waiting_age_nanoseconds=oldest_waiting_age_nanoseconds,
            reserved_work_units=self._reserved_work_units,
            maximum_observed_admitted_commands=(
                self._maximum_observed_admitted_commands
            ),
            maximum_observed_reserved_work_units=(
                self._maximum_observed_reserved_work_units
            ),
            last_started_queue_wait_nanoseconds=(
                self._last_started_queue_wait_nanoseconds
            ),
            maximum_observed_queue_wait_nanoseconds=(
                self._maximum_observed_queue_wait_nanoseconds
            ),
            rejected_commands=self._rejected_commands,
            duplicate_kind_rejections=self._duplicate_kind_rejections,
            terminal_barrier_rejections=self._terminal_barrier_rejections,
            capacity_rejections=self._capacity_rejections,
            closed_rejections=self._closed_rejections,
            timed_out_commands=self._timed_out_commands,
            cancelled_before_entry_commands=self._cancelled_before_entry_commands,
            closed_before_entry_commands=self._closed_before_entry_commands,
            released_commands=self._released_commands,
        )


__all__ = [
    "TRANSPORT_CAPACITY_POLICY_SCHEMA_VERSION_V49F",
    "TRANSPORT_CAPACITY_PROFILE_V49F",
    "BoundedTransportAdmissionGateV49F",
    "TransportAdmissionClosedV49F",
    "TransportAdmissionDeadlineExceededV49F",
    "TransportAdmissionErrorV49F",
    "TransportAdmissionGrantV49F",
    "TransportAdmissionLifecycleV49F",
    "TransportAdmissionRejectedV49F",
    "TransportAdmissionSnapshotV49F",
    "TransportAdmissionStateErrorV49F",
    "TransportAdmissionTerminalBarrierV49F",
    "TransportCapacityPolicyV49F",
    "TransportCommandKindV49F",
]

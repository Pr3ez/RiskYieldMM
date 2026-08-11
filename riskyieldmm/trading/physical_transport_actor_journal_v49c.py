"""Owner-local projection bridge for the V4.9C transport session actor.

The projection is intentionally synchronous: its SQLite connection and the
session actor live on the same process/thread/event-loop owner.  These async
methods contain no suspension point around a projection transaction.  That
keeps each append indivisible with respect to the actor while satisfying the
controller's journal port without moving a thread-bound SQLite connection.

This bridge does not grant socket authority and doesn't perform network I/O.
Its only capability-bearing hand-off is the exact in-memory RAW actor event
returned by the transaction which atomically committed the raw record and its
actor edge.  An idempotent replay returns canonical data, not renewed live RAW
adoption authority.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import threading
from pathlib import Path
from typing import Any, Final

from .canonical import canonical_hash, sha256_digest
from .physical_projection_v4 import (
    ActorAckDeadlineExpiryResultV49E,
    ActorProviderMessageCommitResultV49E,
    ActorTerminalConvergenceResultV49E,
    CommittedActorRawIngressV49C,
    PhysicalProjectionSqliteEnvironmentObservationV49F,
    PhysicalProjectionStoreV4,
)
from .physical_transport_actor_v49c import (
    RawIngressCommittedPayloadV49C,
    TlsProtocolOperationFailedPayloadV49E,
    TlsProtocolOperationPurposeV49E,
    TlsProtocolOperationStartedPayloadV49E,
    TransportActorEventKindV49C,
    TransportActorEventV49C,
)
from .physical_transport_control_v4 import RawIngressCommitV4
from .physical_transport_session_actor_v49c import TransportActorAuthorityV49C

_TEST_TOKEN: Final = object()
_LIVE_TOKEN: Final = object()


class PhysicalTransportActorJournalV49CError(RuntimeError):
    """Base failure for the owner-local projection bridge."""


class PhysicalTransportActorJournalV49COwnerError(
    PhysicalTransportActorJournalV49CError
):
    """The bridge migrated away from its construction owner."""


class PhysicalTransportActorJournalV49CCapabilityError(
    PhysicalTransportActorJournalV49CError
):
    """A caller presented data rather than the exact RAW commit capability."""


class PhysicalTransportActorProjectionJournalV49C:
    """Exact journal adapter for one projection, session, and actor authority."""

    def __init__(
        self,
        *,
        _token: object,
        store: PhysicalProjectionStoreV4,
        authority: TransportActorAuthorityV49C,
        socket_owner: Any | None = None,
    ) -> None:
        if _token not in {_TEST_TOKEN, _LIVE_TOKEN}:
            raise TypeError("use for_test() or from_live_linux_authority()")
        if type(store) is not PhysicalProjectionStoreV4:
            raise TypeError("store must be exact PhysicalProjectionStoreV4")
        if type(authority) is not TransportActorAuthorityV49C:
            raise TypeError("authority must be exact TransportActorAuthorityV49C")
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError as exc:
            raise PhysicalTransportActorJournalV49COwnerError(
                "projection bridge construction requires one running event loop"
            ) from exc

        is_live = _token is _LIVE_TOKEN
        if is_live:
            from .physical_transport_linux_v4 import LinuxSocketOwnerV4

            if (
                type(socket_owner) is not LinuxSocketOwnerV4
                or not socket_owner.is_live_profile
                or not store.is_live_clock_profile
                or not store._is_bound_to_live_linux_authority(  # noqa: SLF001
                    socket_owner
                )
                or socket_owner.driver_policy_id != authority.driver_policy_id
            ):
                raise TypeError(
                    "live bridge requires the exact projection-bound Linux owner"
                )
        elif store.is_live_clock_profile:
            raise TypeError("test bridge cannot downgrade live projection authority")
        elif socket_owner is not None:
            from .physical_transport_linux_v4 import LinuxSocketOwnerV4

            if (
                type(socket_owner) is not LinuxSocketOwnerV4
                or socket_owner.is_live_profile
                or socket_owner.driver_policy_id != authority.driver_policy_id
            ):
                raise TypeError(
                    "test bridge requires the exact non-live retained Linux owner"
                )

        self._store = store
        self._authority = authority
        self._socket_owner = socket_owner
        self._socket_owner_snapshot = (
            None if socket_owner is None else socket_owner.snapshot()
        )
        self._capacity_measurement_driver_evidence_nonce_v49f = (
            None
            if socket_owner is None
            else socket_owner.capacity_measurement_driver_evidence_nonce_v49f
        )
        self._capacity_measurement_kernel_socket_identity_v49f = (
            None
            if self._socket_owner_snapshot is None
            else self._socket_owner_snapshot.kernel_socket_identity
        )
        self._is_live = is_live
        self._pid = os.getpid()
        self._thread_id = threading.get_ident()
        self._loop = loop
        sqlite_observation = store.authoritative_sqlite_environment_observation_v49f()
        self._capacity_measurement_store_identity_v49f = (
            sqlite_observation.database_path,
            sqlite_observation.database_device,
            sqlite_observation.database_inode,
            store.ledger_id,
            store.schema_fingerprint,
        )
        self._raw_capabilities: dict[int, TransportActorEventV49C] = {}

    @classmethod
    def for_test(
        cls,
        *,
        store: PhysicalProjectionStoreV4,
        authority: TransportActorAuthorityV49C,
        socket_owner: Any | None = None,
    ) -> PhysicalTransportActorProjectionJournalV49C:
        """Construct an explicit non-live bridge for deterministic tests."""

        return cls(
            _token=_TEST_TOKEN,
            store=store,
            authority=authority,
            socket_owner=socket_owner,
        )

    @classmethod
    def from_live_linux_authority(
        cls,
        *,
        store: PhysicalProjectionStoreV4,
        authority: TransportActorAuthorityV49C,
        socket_owner: Any,
    ) -> PhysicalTransportActorProjectionJournalV49C:
        """Bind a live bridge to the already-retained exact Linux owner."""

        return cls(
            _token=_LIVE_TOKEN,
            store=store,
            authority=authority,
            socket_owner=socket_owner,
        )

    @property
    def authority(self) -> TransportActorAuthorityV49C:
        return self._authority

    @property
    def is_live_profile(self) -> bool:
        return self._is_live

    @property
    def capacity_measurement_database_path_v49f(self) -> Path:
        """Return the exact retained projection path without its connection."""

        self._assert_owner()
        path = self._store.path
        if not isinstance(path, Path) or not path.is_absolute():
            raise PhysicalTransportActorJournalV49COwnerError(
                "projection store returned an unsupported database path"
            )
        return path

    def authoritative_sqlite_environment_observation_v49f(
        self,
    ) -> PhysicalProjectionSqliteEnvironmentObservationV49F:
        """Observe the exact owner-local open store without exposing it."""

        self._assert_owner()
        observation = self._store.authoritative_sqlite_environment_observation_v49f()
        if type(observation) is not PhysicalProjectionSqliteEnvironmentObservationV49F:
            raise PhysicalTransportActorJournalV49COwnerError(
                "projection returned an unsupported SQLite environment observation"
            )
        return observation

    def _assert_execution_owner_v49f(self) -> None:
        """Require the bridge's process/thread/loop without socket authority.

        Raw-V7 terminal and postmortem reads must remain possible after the
        target ingress path has fenced or aborted the live socket owner.  This
        narrower assertion grants no network or actor-append capability.
        """

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError as exc:
            raise PhysicalTransportActorJournalV49COwnerError(
                "projection bridge requires its construction event loop"
            ) from exc
        if (
            os.getpid() != self._pid
            or threading.get_ident() != self._thread_id
            or loop is not self._loop
        ):
            raise PhysicalTransportActorJournalV49COwnerError(
                "projection bridge migrated across process/thread/event-loop owner"
            )

    def _assert_postmortem_store_identity_v49f(self) -> None:
        """Revalidate the exact retained projection without a live socket."""

        self._assert_execution_owner_v49f()
        try:
            observed = self._store.authoritative_sqlite_environment_observation_v49f()
            current = (
                observed.database_path,
                observed.database_device,
                observed.database_inode,
                self._store.ledger_id,
                self._store.schema_fingerprint,
            )
        except BaseException as exc:
            raise PhysicalTransportActorJournalV49COwnerError(
                "retained capacity projection is no longer current"
            ) from exc
        if current != self._capacity_measurement_store_identity_v49f:
            raise PhysicalTransportActorJournalV49COwnerError(
                "retained capacity projection identity changed"
            )

    def _assert_live_effect_owner_v49f(self) -> None:
        """Require execution locality plus the exact current live socket."""

        self._assert_execution_owner_v49f()
        owner = self._socket_owner
        snapshot = self._socket_owner_snapshot
        if owner is not None:
            try:
                owner.assert_same_owner(snapshot)
            except BaseException as exc:
                raise PhysicalTransportActorJournalV49COwnerError(
                    "retained live socket owner is no longer current"
                ) from exc

    def _assert_live_or_terminal_journal_owner_v49e(
        self, *, terminal_eligible: bool
    ) -> None:
        """Retain the live-peer rule except after sealed terminal evidence."""

        try:
            self._assert_live_effect_owner_v49f()
            return
        except PhysicalTransportActorJournalV49COwnerError:
            if not terminal_eligible:
                raise
        owner = self._socket_owner
        snapshot = self._socket_owner_snapshot
        if owner is None or snapshot is None:
            raise PhysicalTransportActorJournalV49COwnerError(
                "terminal journal owner is unavailable"
            )
        try:
            owner.assert_same_terminal_journal_owner_v49e(snapshot)
        except BaseException as exc:
            raise PhysicalTransportActorJournalV49COwnerError(
                "retained terminal journal owner is no longer current"
            ) from exc

    def _assert_owner(self) -> None:
        """Preserve the strong legacy owner assertion for every old API."""

        self._assert_live_effect_owner_v49f()

    def _assert_raw_authority(self, raw: RawIngressCommitV4) -> None:
        if type(raw) is not RawIngressCommitV4:
            raise TypeError("raw must be exact RawIngressCommitV4")
        for field_name in (
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
        ):
            if getattr(raw, field_name) != getattr(self._authority, field_name):
                raise PhysicalTransportActorJournalV49CCapabilityError(
                    f"raw ingress changes actor authority field {field_name}"
                )

    def _assert_capacity_attempt_authority_v49f(self, attempt: Any) -> None:
        """Cross-check every lifecycle field shared with retained authority."""

        from .physical_transport_capacity_lifecycle_v49f import (
            CapacityMeasurementOperationAttemptV49F,
        )

        if type(attempt) is not CapacityMeasurementOperationAttemptV49F:
            raise PhysicalTransportActorJournalV49CCapabilityError(
                "capacity attempt has an unsupported exact type"
            )
        for field_name in (
            "transport_session_id",
            "writer_fence_token_sha256",
            "writer_fence_generation",
            "monotonic_clock_domain_id",
        ):
            if getattr(attempt, field_name) != getattr(self._authority, field_name):
                raise PhysicalTransportActorJournalV49CCapabilityError(
                    f"capacity attempt changes actor authority field {field_name}"
                )
        kernel_socket_identity = self._capacity_measurement_kernel_socket_identity_v49f
        driver_nonce = self._capacity_measurement_driver_evidence_nonce_v49f
        if kernel_socket_identity is None or driver_nonce is None:
            raise PhysicalTransportActorJournalV49CCapabilityError(
                "capacity attempt lacks a retained immutable driver/socket identity"
            )
        if attempt.kernel_socket_identity != kernel_socket_identity:
            raise PhysicalTransportActorJournalV49CCapabilityError(
                "capacity attempt changes the retained kernel socket identity"
            )
        if attempt.driver_evidence_nonce_sha256 != driver_nonce:
            raise PhysicalTransportActorJournalV49CCapabilityError(
                "capacity attempt changes the retained driver identity"
            )

    async def read_transport_actor_prefix_v49c(
        self, *, transport_session_id: str
    ) -> tuple[TransportActorEventV49C, ...]:
        """Load one canonical actor prefix without minting live capabilities."""

        self._assert_owner()
        session_id = canonical_hash(transport_session_id, field="transport_session_id")
        if session_id != self._authority.transport_session_id:
            raise PhysicalTransportActorJournalV49CCapabilityError(
                "journal read requested a different transport session"
            )
        return self._store._load_transport_actor_chain_v49c(session_id)  # noqa: SLF001

    def capacity_measurement_projection_coordinates_v49f(
        self, *, transport_session_id: str
    ) -> tuple[int, str | None, int, str | None]:
        """Capture the exact pre-effect RAW/actor coordinates.

        This is an attempt-writing seam, so the live socket owner must still be
        current.  The returned tuple carries no append or socket capability.
        """

        self._assert_live_effect_owner_v49f()
        session_id = canonical_hash(transport_session_id, field="transport_session_id")
        if session_id != self._authority.transport_session_id:
            raise PhysicalTransportActorJournalV49CCapabilityError(
                "capacity coordinates requested a different transport session"
            )
        return self._store._capacity_measurement_projection_coordinates_v49f(  # noqa: SLF001
            session_id
        )

    def capacity_measurement_campaign_baseline_v49f(
        self, *, transport_session_id: str
    ) -> tuple[tuple[int, str | None, int, str | None], Any, Any]:
        """Capture one stable read-only Raw-V7 projection/parser baseline.

        The two store-authority reads bracket the parser and coordinate reads.
        Receipt anchors cannot move backwards, so equality proves that no
        projection append crossed the returned observation.  The result is
        evidence only: it contains no append, socket, or writer capability.
        """

        from .physical_projection_v4 import CapacityMeasurementAttemptAuthorityV49F
        from .physical_transport_actor_v49c import WebSocketParserCursorV49C

        self._assert_live_effect_owner_v49f()
        session_id = canonical_hash(transport_session_id, field="transport_session_id")
        if session_id != self._authority.transport_session_id:
            raise PhysicalTransportActorJournalV49CCapabilityError(
                "capacity baseline requested a different transport session"
            )

        coordinates_before = (
            self._store._capacity_measurement_projection_coordinates_v49f(  # noqa: SLF001
                session_id
            )
        )
        authority_before = self._store._capacity_measurement_attempt_authority_v49f(  # noqa: SLF001
            transport_session_id=session_id,
            baseline_actor_event_count=coordinates_before[2],
        )
        parser_cursor = self._store._capacity_measurement_parser_cursor_at_v49f(  # noqa: SLF001
            session_id,
            coordinates_before[2],
        )
        coordinates_after = (
            self._store._capacity_measurement_projection_coordinates_v49f(  # noqa: SLF001
                session_id
            )
        )
        authority_after = self._store._capacity_measurement_attempt_authority_v49f(  # noqa: SLF001
            transport_session_id=session_id,
            baseline_actor_event_count=coordinates_after[2],
        )
        if (
            coordinates_before != coordinates_after
            or authority_before != authority_after
            or type(authority_before) is not CapacityMeasurementAttemptAuthorityV49F
            or type(parser_cursor) is not WebSocketParserCursorV49C
        ):
            raise PhysicalTransportActorJournalV49CCapabilityError(
                "projection changed across capacity campaign baseline capture"
            )
        return coordinates_before, authority_before, parser_cursor

    def capacity_measurement_attempt_authority_v49f(
        self,
        *,
        authorization: Any,
        transport_session_id: str,
        baseline_actor_event_count: int,
    ) -> Any:
        """Capture the store/writer/receipt anchor under operation authority."""

        from .physical_projection_v4 import CapacityMeasurementAttemptAuthorityV49F
        from .physical_transport_runtime_v4 import (
            CapacityMeasurementIngressAuthorizationV49F,
        )

        self._assert_live_effect_owner_v49f()
        if type(authorization) is not CapacityMeasurementIngressAuthorizationV49F:
            raise PhysicalTransportActorJournalV49CCapabilityError(
                "capacity attempt authority requires the sealed operation authority"
            )
        authorization._assert_precommit_journal_v49f(self)  # noqa: SLF001
        session_id = canonical_hash(transport_session_id, field="transport_session_id")
        if session_id != self._authority.transport_session_id:
            raise PhysicalTransportActorJournalV49CCapabilityError(
                "capacity attempt authority requested a different session"
            )
        if type(baseline_actor_event_count) is not int:
            raise PhysicalTransportActorJournalV49CCapabilityError(
                "capacity attempt authority requires an exact actor count"
            )
        result = self._store._capacity_measurement_attempt_authority_v49f(  # noqa: SLF001
            transport_session_id=session_id,
            baseline_actor_event_count=baseline_actor_event_count,
        )
        if (
            type(result) is not CapacityMeasurementAttemptAuthorityV49F
            or result.projection_ledger_id
            != self._capacity_measurement_store_identity_v49f[3]
            or result.projection_schema_fingerprint
            != self._capacity_measurement_store_identity_v49f[4]
            or result.writer_fence_token_sha256
            != self._authority.writer_fence_token_sha256
            or result.writer_fence_generation != self._authority.writer_fence_generation
        ):
            raise PhysicalTransportActorJournalV49CCapabilityError(
                "capacity attempt store authority changed"
            )
        return result

    def commit_capacity_measurement_operation_attempt_v49f(
        self,
        *,
        attempt: Any,
        authorization: Any,
    ) -> Any:
        """Synchronously commit one Raw-V7 attempt before target effects."""

        from .physical_projection_v4 import (
            CommittedCapacityMeasurementOperationAttemptV49F,
        )
        from .physical_transport_runtime_v4 import (
            CapacityMeasurementIngressAuthorizationV49F,
        )

        self._assert_live_effect_owner_v49f()
        self._assert_capacity_attempt_authority_v49f(attempt)
        if type(authorization) is not CapacityMeasurementIngressAuthorizationV49F:
            raise PhysicalTransportActorJournalV49CCapabilityError(
                "capacity attempt commit requires its sealed operation authority"
            )
        authorization._consume_attempt_commit_v49f(  # noqa: SLF001
            journal=self,
            attempt=attempt,
        )
        key = f"v49f-capacity-attempt-{attempt.attempt_id}"
        if self._is_live:
            committed = (
                self._store._append_driver_capacity_measurement_operation_attempt_v49f(  # noqa: SLF001
                    attempt,
                    authority=self._socket_owner,
                    idempotency_key=key,
                )
            )
        else:
            committed = (
                self._store.append_capacity_measurement_operation_attempt_v49f_for_test(
                    attempt,
                    idempotency_key=key,
                )
            )
        if (
            type(committed) is not CommittedCapacityMeasurementOperationAttemptV49F
            or committed.attempt != attempt
            or committed.attempt.transport_session_id
            != self._authority.transport_session_id
        ):
            raise PhysicalTransportActorJournalV49CCapabilityError(
                "projection returned an invalid capacity-attempt capability"
            )
        return committed

    def close_capacity_measurement_operation_v49f(
        self,
        *,
        committed_attempt: Any,
        observation: Any,
        returned_progress_evidence: Any | None,
    ) -> Any:
        """Synchronously terminalize and reload one exact post-effect prefix.

        The committed-attempt object is the one-shot authority.  Socket
        currentness is deliberately not required: the ingress failure path may
        already have aborted the owner before this non-effect append runs.
        """

        from .physical_projection_v4 import (
            CommittedCapacityMeasurementOperationAttemptV49F,
        )
        from .physical_transport_capacity_lifecycle_v49f import (
            CapacityMeasurementOperationPrefixV49F,
            CapacityMeasurementSameTaskTerminalObservationV49F,
        )

        self._assert_postmortem_store_identity_v49f()
        if (
            type(committed_attempt)
            is not CommittedCapacityMeasurementOperationAttemptV49F
            or type(observation)
            is not CapacityMeasurementSameTaskTerminalObservationV49F
            or committed_attempt.attempt.transport_session_id
            != self._authority.transport_session_id
        ):
            raise PhysicalTransportActorJournalV49CCapabilityError(
                "capacity terminal lacks the retained committed-attempt authority"
            )
        self._assert_capacity_attempt_authority_v49f(committed_attempt.attempt)
        prefix = self._store.append_capacity_measurement_operation_terminal_v49f(
            committed_attempt,
            observation,
            idempotency_key=(
                f"v49f-capacity-terminal-{committed_attempt.attempt.attempt_id}"
            ),
            returned_progress_evidence=returned_progress_evidence,
        )
        if type(prefix) is not CapacityMeasurementOperationPrefixV49F:
            raise PhysicalTransportActorJournalV49CCapabilityError(
                "projection returned an invalid terminalized capacity prefix"
            )
        terminal = prefix.terminal
        if (
            prefix.attempt != committed_attempt.attempt
            or terminal is None
            or terminal.terminal_trigger is not observation.terminal_trigger
            or terminal.surfaced_exception_class != observation.surfaced_exception_class
            or terminal.exception_class_chain != observation.exception_class_chain
            or terminal.exception_message_sha256_chain
            != observation.exception_message_sha256_chain
            or terminal.runtime_state_after != observation.runtime_state_after
            or terminal.observer_end_offset_nanoseconds
            != observation.observer_end_offset_nanoseconds
            or terminal.boottime_end_offset_nanoseconds
            != observation.boottime_end_offset_nanoseconds
            or terminal.loop_time_end_offset_nanoseconds
            != observation.loop_time_end_offset_nanoseconds
        ):
            raise PhysicalTransportActorJournalV49CCapabilityError(
                "projection returned a substituted terminalized capacity prefix"
            )
        return prefix

    def load_capacity_measurement_operation_prefix_postmortem_v49f(
        self, *, attempt_id: str
    ) -> Any:
        """Read an exact Raw-V7 prefix after owner abort, minting no capability."""

        from .physical_transport_capacity_lifecycle_v49f import (
            CapacityMeasurementOperationPrefixV49F,
        )

        self._assert_postmortem_store_identity_v49f()
        prefix = self._store.load_capacity_measurement_operation_prefix_v49f(
            canonical_hash(attempt_id, field="attempt_id")
        )
        if (
            type(prefix) is not CapacityMeasurementOperationPrefixV49F
            or prefix.attempt.transport_session_id
            != self._authority.transport_session_id
        ):
            raise PhysicalTransportActorJournalV49CCapabilityError(
                "postmortem capacity prefix leaves the retained session"
            )
        self._assert_capacity_attempt_authority_v49f(prefix.attempt)
        return prefix

    async def append_actor_raw_ingress_v49c(
        self,
        *,
        raw: RawIngressCommitV4,
    ) -> CommittedActorRawIngressV49C:
        """Atomically append RAW+actor records and retain its one-shot hand-off."""

        self._assert_owner()
        self._assert_raw_authority(raw)
        key = f"v49c-actor-raw-{raw.raw_ingress_commit_id}"
        if self._is_live:
            result = self._store._append_driver_actor_raw_ingress_v49c(  # noqa: SLF001
                raw,
                authority=self._socket_owner,
                idempotency_key=key,
            )
        else:
            result = self._store.append_actor_raw_ingress_v49c_for_test(
                raw,
                driver_policy_id=self._authority.driver_policy_id,
                idempotency_key=key,
            )
        if (
            type(result) is not CommittedActorRawIngressV49C
            or not self._authority.matches(result.event)
            or result.event.event_kind
            is not TransportActorEventKindV49C.RAW_INGRESS_COMMITTED
            or type(result.event.payload) is not RawIngressCommittedPayloadV49C
        ):
            raise PhysicalTransportActorJournalV49CCapabilityError(
                "projection returned a RAW result outside actor authority"
            )
        if result.receipt.is_store_minted:
            self._raw_capabilities[id(result.event)] = result.event
        return result

    async def resolve_exact_committed_raw_actor_event_v49c(
        self, *, event: TransportActorEventV49C
    ) -> TransportActorEventV49C:
        """Consume only this bridge's exact one-shot projection return object."""

        self._assert_owner()
        exact = self._raw_capabilities.get(id(event))
        if exact is not event:
            raise PhysicalTransportActorJournalV49CCapabilityError(
                "RAW actor event is not this bridge's exact commit capability"
            )
        prefix = await self.read_transport_actor_prefix_v49c(
            transport_session_id=self._authority.transport_session_id
        )
        if (
            not prefix
            or prefix[-1].transport_actor_event_id != event.transport_actor_event_id
            or prefix[-1] != event
        ):
            raise PhysicalTransportActorJournalV49CCapabilityError(
                "RAW actor capability is no longer the exact durable tail"
            )
        del self._raw_capabilities[id(event)]
        return event

    async def append_transport_actor_event_v49c(
        self, *, event: TransportActorEventV49C
    ) -> TransportActorEventV49C:
        """Append one non-RAW event and return the exact input object."""

        if (
            type(event) is not TransportActorEventV49C
            or not self._authority.matches(event)
            or event.event_kind is TransportActorEventKindV49C.RAW_INGRESS_COMMITTED
        ):
            raise PhysicalTransportActorJournalV49CCapabilityError(
                "generic actor append changes authority/type or bypasses RAW atomicity"
            )
        terminal_operation_start = (
            event.event_kind
            is TransportActorEventKindV49C.TLS_PROTOCOL_OPERATION_STARTED
            and type(event.payload) is TlsProtocolOperationStartedPayloadV49E
            and event.payload.purpose
            in {
                TlsProtocolOperationPurposeV49E.LOCAL_CLOSE_NOTIFY,
                TlsProtocolOperationPurposeV49E.PEER_SHUTDOWN_POLL,
            }
        )
        terminal_operation_failure = (
            event.event_kind
            is TransportActorEventKindV49C.TLS_PROTOCOL_OPERATION_FAILED
            and type(event.payload) is TlsProtocolOperationFailedPayloadV49E
            and event.payload.purpose
            in {
                TlsProtocolOperationPurposeV49E.LOCAL_CLOSE_NOTIFY,
                TlsProtocolOperationPurposeV49E.PEER_SHUTDOWN_POLL,
            }
        )
        self._assert_live_or_terminal_journal_owner_v49e(
            terminal_eligible=(terminal_operation_start or terminal_operation_failure)
        )
        key = f"v49c-actor-event-{event.transport_actor_event_id}"
        if self._is_live:
            committed = self._store._append_driver_transport_actor_event_v49c(  # noqa: SLF001
                event,
                authority=self._socket_owner,
                idempotency_key=key,
            )
        else:
            committed = self._store.append_transport_actor_event_v49c_for_test(
                event,
                idempotency_key=key,
            )
        if committed is not event:
            raise PhysicalTransportActorJournalV49CCapabilityError(
                "projection append replay didn't return the exact input event"
            )
        return event

    async def append_transport_actor_events_v49c(
        self, *, events: tuple[TransportActorEventV49C, ...]
    ) -> tuple[TransportActorEventV49C, ...]:
        """Atomically append one exact consecutive non-RAW actor batch."""

        if (
            type(events) is not tuple
            or not 2 <= len(events) <= 8
            or any(
                type(event) is not TransportActorEventV49C
                or not self._authority.matches(event)
                or event.event_kind is TransportActorEventKindV49C.RAW_INGRESS_COMMITTED
                for event in events
            )
        ):
            raise PhysicalTransportActorJournalV49CCapabilityError(
                "actor batch changes authority/type or bypasses RAW atomicity"
            )
        self._assert_live_or_terminal_journal_owner_v49e(
            terminal_eligible=(
                events[-1].event_kind is TransportActorEventKindV49C.TERMINAL_TRANSITION
            )
        )
        batch_id = sha256_digest(
            {
                "domain": "RiskYieldMMActorProjectionBatchV4_9C",
                "transport_actor_event_ids": [
                    event.transport_actor_event_id for event in events
                ],
            }
        )
        key = f"v49c-actor-batch-{batch_id}"
        if self._is_live:
            committed = self._store._append_driver_transport_actor_event_batch_v49c(  # noqa: SLF001
                events,
                authority=self._socket_owner,
                idempotency_key=key,
            )
        else:
            committed = self._store.append_transport_actor_event_batch_v49c_for_test(
                events,
                idempotency_key=key,
            )
        if (
            type(committed) is not tuple
            or len(committed) != len(events)
            or any(
                actual is not expected for actual, expected in zip(committed, events)
            )
        ):
            raise PhysicalTransportActorJournalV49CCapabilityError(
                "projection batch append didn't return exact input events"
            )
        return events

    async def commit_actor_provider_message_v49e(
        self,
        *,
        source_parser_event_ids: Any,
        websocket_opcode: Any,
        raw_payload: bytes,
        collector_received_at: Any,
        collector_received_monotonic_ns: int,
        classified_monotonic_ns: int,
        signer: Any,
    ) -> ActorProviderMessageCommitResultV49E:
        """Commit one parser-derived provider message without caller event IDs."""

        self._assert_owner()
        source_ids = tuple(source_parser_event_ids)
        batch_id = sha256_digest(
            {
                "collector_received_at": str(collector_received_at),
                "collector_received_monotonic_ns": (collector_received_monotonic_ns),
                "domain": "RiskYieldMMActorProviderMessageV4_9E",
                "raw_payload_sha256": hashlib.sha256(raw_payload).hexdigest(),
                "source_parser_event_ids": list(source_ids),
                "transport_session_id": self._authority.transport_session_id,
                "websocket_opcode": getattr(
                    websocket_opcode, "value", websocket_opcode
                ),
            }
        )
        values = {
            "transport_session_id": self._authority.transport_session_id,
            "source_parser_event_ids": source_ids,
            "websocket_opcode": websocket_opcode,
            "raw_payload": raw_payload,
            "collector_received_at": collector_received_at,
            "collector_received_monotonic_ns": collector_received_monotonic_ns,
            "classified_monotonic_ns": classified_monotonic_ns,
            "signer": signer,
        }
        key = f"v49e-provider-{batch_id}"
        if self._is_live:
            result = self._store._commit_driver_actor_provider_message_v49e(  # noqa: SLF001
                authority=self._socket_owner,
                idempotency_key=key,
                **values,
            )
        else:
            result = self._store.commit_actor_provider_message_v49e_for_test(
                driver_policy_id=self._authority.driver_policy_id,
                idempotency_key=key,
                **values,
            )
        if (
            type(result) is not ActorProviderMessageCommitResultV49E
            or not self._authority.matches(result.application_event)
            or (
                result.ack_event is not None
                and not self._authority.matches(result.ack_event)
            )
            or (
                result.provider_failure_event is not None
                and not self._authority.matches(result.provider_failure_event)
            )
            or (
                result.termination is not None
                and result.termination.transport_session_id
                != self._authority.transport_session_id
            )
        ):
            raise PhysicalTransportActorJournalV49CCapabilityError(
                "projection returned a provider-message result outside actor authority"
            )
        return result

    async def converge_actor_terminal_v49e(
        self,
        *,
        terminal_event: TransportActorEventV49C,
        signer: Any,
    ) -> ActorTerminalConvergenceResultV49E:
        """Atomically append the decisive actor tail and signed legacy bridge."""

        if (
            type(terminal_event) is not TransportActorEventV49C
            or not self._authority.matches(terminal_event)
            or terminal_event.event_kind
            is not TransportActorEventKindV49C.TERMINAL_TRANSITION
        ):
            raise PhysicalTransportActorJournalV49CCapabilityError(
                "terminal convergence changes actor authority or event type"
            )
        self._assert_live_or_terminal_journal_owner_v49e(terminal_eligible=True)
        key = f"v49e-terminal-{terminal_event.transport_actor_event_id}"
        if self._is_live:
            result = self._store._converge_driver_actor_terminal_v49e(  # noqa: SLF001
                terminal_event,
                authority=self._socket_owner,
                signer=signer,
                idempotency_key=key,
            )
        else:
            result = self._store.converge_actor_terminal_v49e_for_test(
                terminal_event,
                signer=signer,
                idempotency_key=key,
            )
        if (
            type(result) is not ActorTerminalConvergenceResultV49E
            or result.terminal_event != terminal_event
            or not self._authority.matches(result.terminal_event)
            or result.termination.transport_session_id
            != self._authority.transport_session_id
        ):
            raise PhysicalTransportActorJournalV49CCapabilityError(
                "projection returned a terminal pair outside actor authority"
            )
        # The terminal owner was sealed above.  Requiring the ordinary reader
        # here would call getpeername() again after a valid peer EOF and reject
        # the exact terminal pair that was just committed.
        prefix = self._store._load_transport_actor_chain_v49c(  # noqa: SLF001
            self._authority.transport_session_id
        )
        if not prefix or prefix[-1] != result.terminal_event:
            raise PhysicalTransportActorJournalV49CCapabilityError(
                "terminal convergence result is not the exact durable actor tail"
            )
        return result

    async def expire_actor_ack_deadline_v49e(
        self,
        *,
        observed_at: Any,
        observed_monotonic_ns: int,
        signer: Any,
    ) -> ActorAckDeadlineExpiryResultV49E:
        """Commit the sole actor-ordered ACK timeout for this session."""

        self._assert_owner()
        values = {
            "transport_session_id": self._authority.transport_session_id,
            "observed_at": observed_at,
            "observed_monotonic_ns": observed_monotonic_ns,
            "signer": signer,
        }
        key = f"v49e-ack-timeout-{self._authority.transport_session_id}"
        if self._is_live:
            result = self._store._expire_driver_actor_ack_deadline_v49e(  # noqa: SLF001
                authority=self._socket_owner,
                idempotency_key=key,
                **values,
            )
        else:
            result = self._store.expire_actor_ack_deadline_v49e_for_test(
                driver_policy_id=self._authority.driver_policy_id,
                idempotency_key=key,
                **values,
            )
        if (
            type(result) is not ActorAckDeadlineExpiryResultV49E
            or not self._authority.matches(result.deadline_event)
            or not self._authority.matches(result.terminal_event)
            or result.termination.transport_session_id
            != self._authority.transport_session_id
        ):
            raise PhysicalTransportActorJournalV49CCapabilityError(
                "projection returned an ACK-timeout result outside actor authority"
            )
        return result


__all__ = [
    "PhysicalTransportActorJournalV49CCapabilityError",
    "PhysicalTransportActorJournalV49CError",
    "PhysicalTransportActorJournalV49COwnerError",
    "PhysicalTransportActorProjectionJournalV49C",
]

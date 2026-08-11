from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from riskyieldmm.trading.ledger_signing import Ed25519CheckpointSigner
from riskyieldmm.trading.physical_projection_v4 import PhysicalProjectionStoreV4
from riskyieldmm.trading.physical_transport_lease_v4 import (
    PhysicalTransportWriterLeaseV4,
)
from riskyieldmm.trading.physical_transport_owner_v4 import (
    TransportSocketOwnerSnapshotV4,
    derive_linux_boottime_clock_domain_id,
)
from riskyieldmm.trading.physical_transport_runtime_v4 import (
    ClockEvidenceV4,
    PhysicalTransportRuntimeStateV4,
    PhysicalTransportRuntimeV4,
    PhysicalTransportRuntimeV4FaultLatched,
)
from riskyieldmm.trading.physical_transport_v4 import (
    TransportSessionAttestationV4,
    TransportSessionTerminationReasonV4,
)
from tests.test_trading_physical_authority_v4_projection import authority_scope
from tests.test_trading_physical_market_data_v3 import (
    T0,
    bar_policy,
    digest,
    status_policy,
)
from tests.test_trading_physical_transport_v4_projection import (
    TransportFixture,
    ack_payload,
    append_ack_occurrence,
    append_test_bound_session,
    append_test_operational_deployment,
    signed_session,
    transport_policy,
)


def _test_boottime_domain(*, boot_id: str = "boot-a") -> str:
    return derive_linux_boottime_clock_domain_id(
        kernel_boot_id=boot_id,
        time_namespace_id=digest("test-time-namespace"),
    )


@dataclass(slots=True)
class IntegratedClock:
    value: datetime
    monotonic_ns: int
    domain_id: str
    source_id: str = digest("authority-clock-source-manifest")

    def __call__(self) -> datetime:
        return self.value

    def sample(self) -> ClockEvidenceV4:
        self.value += timedelta(milliseconds=1)
        self.monotonic_ns += 1_000_000
        return ClockEvidenceV4(
            clock_source_manifest_id=self.source_id,
            monotonic_clock_domain_id=self.domain_id,
            sampled_at=self.value,
            monotonic_ns=self.monotonic_ns,
            uncertainty_milliseconds=20,
            synchronized=True,
            valid_until=self.value + timedelta(seconds=1),
        )


@dataclass(slots=True)
class ExactTextSender:
    payloads: list[bytes]

    async def send_exact_text_frame(self, payload: bytes) -> None:
        self.payloads.append(payload)


@dataclass(slots=True)
class IntegratedSocketOwner:
    current_snapshot: TransportSocketOwnerSnapshotV4
    writer: Callable[[bytes], Awaitable[None]] | None = None
    aborted: bool = False

    def snapshot(self) -> TransportSocketOwnerSnapshotV4:
        return self.current_snapshot

    def assert_same_owner(self, expected: TransportSocketOwnerSnapshotV4) -> None:
        if self.aborted or self.current_snapshot != expected:
            raise RuntimeError("integrated socket owner changed")

    async def send_exact_text_frame(
        self,
        payload: bytes,
        *,
        before_driver: Callable[[], None],
    ) -> None:
        if self.writer is None:
            raise RuntimeError("integrated socket owner has no writer")
        before_driver()
        await self.writer(payload)

    def abort(self) -> None:
        self.aborted = True


def integrated_socket_owner(
    session: TransportSessionAttestationV4,
    *,
    label: str,
    writer: Callable[[bytes], Awaitable[None]] | None = None,
) -> IntegratedSocketOwner:
    cookie = digest(f"{label}-socket-cookie")[:16]
    if cookie == "0000000000000000":
        cookie = "0000000000000001"
    return IntegratedSocketOwner(
        current_snapshot=TransportSocketOwnerSnapshotV4(
            kernel_boot_id=session.collector_boot_id,
            time_namespace_id=digest("test-time-namespace"),
            network_namespace_id=digest("test-network-namespace"),
            socket_cookie_u64=cookie,
            clock_resolution_ns=1,
        ),
        writer=writer,
    )


def append_runtime_authority_foundation(
    store: PhysicalProjectionStoreV4,
    *,
    signer: Ed25519CheckpointSigner,
) -> tuple[object, object, object, object, object, object]:
    primary = bar_policy(requires_status=True)
    required_status = status_policy()
    scope = authority_scope(primary, required_status)
    admission, capability = append_test_operational_deployment(
        store,
        signer=signer,
        verified_at=scope.frozen_at,
        valid_until=T0 + timedelta(days=1),
        idempotency_prefix="integration-deployment",
    )
    policy = transport_policy(
        signer=signer,
        frozen_at=scope.frozen_at,
        deployment_capability=capability,
    )
    store.append_health_policy(idempotency_key="integration-health")
    store.append_adapter_policy(primary, idempotency_key="integration-primary")
    store.append_adapter_policy(
        required_status,
        idempotency_key="integration-status",
    )
    store.append_scope(scope, idempotency_key="integration-scope")
    store.append_transport_subscription_policy(
        policy,
        idempotency_key="integration-transport-policy",
    )
    return primary, required_status, scope, policy, admission, capability


def private_lease(tmp_path: Path, *, holder_id: str) -> PhysicalTransportWriterLeaseV4:
    runtime_dir = tmp_path / holder_id
    runtime_dir.mkdir(mode=0o700)
    runtime_dir.chmod(0o700)
    return PhysicalTransportWriterLeaseV4(
        runtime_dir / "transport.writer.lease",
        holder_id=holder_id,
    ).acquire()


def test_real_projection_lease_and_runtime_preserve_commit_before_exact_text_send(
    tmp_path: Path,
) -> None:
    domain_id = _test_boottime_domain()
    signer = Ed25519CheckpointSigner.generate()
    bootstrap_clock = IntegratedClock(
        value=T0 - timedelta(hours=1),
        monotonic_ns=200_000_000,
        domain_id=domain_id,
    )
    with PhysicalProjectionStoreV4(
        tmp_path / "runtime-integration.sqlite3",
        clock=bootstrap_clock,
    ) as store:
        (
            primary,
            _,
            scope,
            policy,
            admission,
            capability,
        ) = append_runtime_authority_foundation(
            store,
            signer=signer,
        )
        bootstrap_clock.source_id = capability.clock_source_manifest_id
        session = signed_session(
            fixture_policy=policy,
            scope=scope,
            primary=primary,
            signer=signer,
            monotonic_clock_domain_id=domain_id,
            deployment_capability=capability,
        )
        bootstrap_clock.value = T0 - timedelta(milliseconds=500)
        lease = private_lease(tmp_path, holder_id="integration-runtime")
        runtime = PhysicalTransportRuntimeV4.for_test(
            journal=store,
            writer_lease=lease,
            clock_source=bootstrap_clock,
            signer=signer,
            deployment_admission=admission,
            idempotency_prefix="integration-runtime",
            wall_clock=bootstrap_clock,
        )

        start = runtime.start()
        assert start.writer_fence_generation == 1
        assert start.deployment_bundle_id == capability.deployment_bundle_id
        assert start.deployment_sequence == capability.deployment_sequence
        assert start.deployment_trust_root_id == capability.deployment_trust_root_id
        assert start.clock_source_manifest_id == capability.clock_source_manifest_id
        sender = ExactTextSender(payloads=[])
        socket_owner = integrated_socket_owner(
            session,
            label="integration-socket",
            writer=sender.send_exact_text_frame,
        )
        runtime.commit_session(
            session,
            socket_owner=socket_owner,
            idempotency_key="integration-session",
        )
        socket_id = runtime.current_socket_lease_id
        assert socket_id is not None
        permit = runtime.authorize_send_permit(idempotency_key="integration-intent")

        window = asyncio.run(
            runtime.dispatch_text(
                permit,
                socket_lease_id=socket_id,
                sender=socket_owner,
            )
        )

        assert sender.payloads == [permit.command_bytes]
        assert window.outbound_subscription_intent_id == (
            permit.outbound_subscription_intent_id
        )
        assert runtime.state is PhysicalTransportRuntimeStateV4.AWAITING_ACK
        termination = runtime.terminate_current(
            TransportSessionTerminationReasonV4.LOCAL_CLOSE
        )
        assert termination.transport_session_id == session.transport_session_id
        runtime.close()
        assert runtime.state is PhysicalTransportRuntimeStateV4.CLOSED
        assert not lease.is_held

        report = store.verify()
        assert report.transport_session_attestation_count == 1
        assert report.transport_socket_owner_binding_count == 1
        assert report.outbound_subscription_intent_count == 1
        assert report.transport_session_termination_count == 1
        assert report.subscription_ack_binding_count == 0


def test_real_runtime_supersedes_stale_epoch_and_reconciles_cross_domain_orphan(
    tmp_path: Path,
) -> None:
    path = tmp_path / "runtime-restart.sqlite3"
    signer = Ed25519CheckpointSigner.generate()
    first_domain = _test_boottime_domain()
    clock = IntegratedClock(
        value=T0 - timedelta(hours=1),
        monotonic_ns=200_000_000,
        domain_id=first_domain,
    )
    with PhysicalProjectionStoreV4(path, clock=clock) as first_store:
        (
            primary,
            _,
            scope,
            policy,
            admission,
            capability,
        ) = append_runtime_authority_foundation(
            first_store,
            signer=signer,
        )
        clock.source_id = capability.clock_source_manifest_id
        crashed_writer_token = digest("crashed-runtime-token")
        crashed_writer_generation = first_store.claim_transport_runtime_writer_fence(
            lease_token_sha256=crashed_writer_token,
            holder_id="crashed-runtime",
        )
        session = signed_session(
            fixture_policy=policy,
            scope=scope,
            primary=primary,
            signer=signer,
            monotonic_clock_domain_id=first_domain,
            deployment_capability=capability,
        )
        clock.value = T0 - timedelta(milliseconds=500)
        append_test_bound_session(
            first_store,
            session=session,
            signer=signer,
            writer_fence_token_sha256=crashed_writer_token,
            writer_fence_generation=crashed_writer_generation,
            idempotency_key="crashed-runtime-session",
            label="crashed-runtime-session",
        )
        # Deliberately close without releasing the application fence or session.

    clock.domain_id = digest("restart-domain-after")
    clock.monotonic_ns = 0
    clock.value = T0 + timedelta(seconds=1)
    with PhysicalProjectionStoreV4(path, clock=clock) as restarted_store:
        lease = private_lease(tmp_path, holder_id="restarted-runtime")
        runtime = PhysicalTransportRuntimeV4.for_test(
            journal=restarted_store,
            writer_lease=lease,
            clock_source=clock,
            signer=signer,
            deployment_admission=admission,
            idempotency_prefix="restarted-runtime",
            wall_clock=clock,
        )

        report = runtime.start()

        assert report.writer_fence_generation == 2
        assert report.deployment_bundle_id == capability.deployment_bundle_id
        assert report.deployment_sequence == capability.deployment_sequence
        assert report.deployment_trust_root_id == capability.deployment_trust_root_id
        assert report.clock_source_manifest_id == capability.clock_source_manifest_id
        assert report.reconciled_transport_session_ids == (
            session.transport_session_id,
        )
        assert runtime.state is PhysicalTransportRuntimeStateV4.READY
        runtime.close()
        verification = restarted_store.verify()
        assert verification.transport_session_attestation_count == 1
        assert verification.transport_session_termination_count == 1


def test_real_early_ack_binds_after_dispatch_and_survives_reopen_and_reconnect(
    tmp_path: Path,
) -> None:
    path = tmp_path / "runtime-early-ack.sqlite3"
    signer = Ed25519CheckpointSigner.generate()
    domain_id = _test_boottime_domain()
    projection_clock = IntegratedClock(
        value=T0 - timedelta(hours=1),
        monotonic_ns=0,
        domain_id=domain_id,
    )
    runtime_clock = IntegratedClock(
        value=T0 - timedelta(milliseconds=500),
        monotonic_ns=200_000_000,
        domain_id=domain_id,
    )
    first_session_id: str
    second_session_id: str
    ack_disposition_id: str

    with PhysicalProjectionStoreV4(path, clock=projection_clock) as store:
        (
            primary,
            required_status,
            scope,
            policy,
            admission,
            capability,
        ) = append_runtime_authority_foundation(store, signer=signer)
        projection_clock.source_id = capability.clock_source_manifest_id
        runtime_clock.source_id = capability.clock_source_manifest_id
        first_session = signed_session(
            fixture_policy=policy,
            scope=scope,
            primary=primary,
            signer=signer,
            monotonic_clock_domain_id=domain_id,
            deployment_capability=capability,
        )
        first_session_id = first_session.transport_session_id
        projection_clock.value = T0 - timedelta(milliseconds=500)
        lease = private_lease(tmp_path, holder_id="early-ack-runtime")
        runtime = PhysicalTransportRuntimeV4.for_test(
            journal=store,
            writer_lease=lease,
            clock_source=runtime_clock,
            signer=signer,
            deployment_admission=admission,
            idempotency_prefix="early-ack-runtime",
            wall_clock=runtime_clock,
        )
        runtime.start()
        socket_owner = integrated_socket_owner(
            first_session,
            label="early-ack-socket-one",
        )
        runtime.commit_session(
            first_session,
            socket_owner=socket_owner,
            idempotency_key="early-ack-session-one",
        )
        socket_id = runtime.current_socket_lease_id
        assert socket_id is not None
        permit = runtime.authorize_send_permit(idempotency_key="early-ack-intent-one")
        intent = runtime._intent  # noqa: SLF001 - integration checks exact journal record
        assert intent is not None
        owner_binding = runtime._socket_owner_binding  # noqa: SLF001
        fence_token = runtime._writer_fence_token_sha256  # noqa: SLF001
        fence_generation = runtime._writer_fence_generation  # noqa: SLF001
        assert owner_binding is not None
        assert fence_token is not None
        assert fence_generation is not None
        fixture = TransportFixture(
            primary=primary,
            required_status=required_status,
            scope=scope,
            signer=signer,
            deployment_capability=capability,
            policy=policy,
            session=first_session,
            intent=intent,
            socket_owner_binding=owner_binding,
            writer_fence_token_sha256=fence_token,
            writer_fence_generation=fence_generation,
        )
        ack_received_at = T0 - timedelta(milliseconds=480)
        sent_payloads: list[bytes] = []
        disposition_ids: list[str] = []

        class EarlyAckSender:
            async def send_exact_text_frame(self, payload: bytes) -> None:
                sent_payloads.append(payload)
                occurrence = append_ack_occurrence(
                    store,
                    clock=projection_clock,
                    fixture=fixture,
                    intent=intent,
                    payload=ack_payload(
                        request_id=intent.request_id,
                        provider_connection_id="provider-connection-early-ack",
                    ),
                    sequence=1,
                    received_at=ack_received_at,
                    idempotency_suffix="runtime-early-ack",
                )
                disposition_id = (
                    occurrence.classification.disposition.message_disposition_id
                )
                disposition_ids.append(disposition_id)
                assert runtime.state is PhysicalTransportRuntimeStateV4.DISPATCHING
                assert (
                    runtime.observe_captured_ack(
                        message_disposition_id=disposition_id,
                        socket_lease_id=socket_id,
                    )
                    is None
                )
                assert store.verify().subscription_ack_binding_count == 0

        socket_owner.writer = EarlyAckSender().send_exact_text_frame
        dispatch = asyncio.run(
            runtime.dispatch_text(
                permit,
                socket_lease_id=socket_id,
                sender=socket_owner,
            )
        )

        assert sent_payloads == [permit.command_bytes]
        assert disposition_ids
        ack_disposition_id = disposition_ids[0]
        assert dispatch.dispatch_completed_at < ack_received_at
        assert runtime.state is PhysicalTransportRuntimeStateV4.ACK_BOUND
        binding = runtime._binding  # noqa: SLF001 - verify exact persisted binding
        assert binding is not None
        assert binding.message_disposition_id == ack_disposition_id
        assert binding.outbound_subscription_intent_id == (
            permit.outbound_subscription_intent_id
        )
        assert binding.ack_received_at == ack_received_at

        runtime_clock.value = ack_received_at + timedelta(milliseconds=1)
        runtime_clock.monotonic_ns = 1_001_000_000
        first_termination = runtime.terminate_current(
            TransportSessionTerminationReasonV4.LOCAL_CLOSE
        )
        runtime.prepare_reconnect()

        second_handshake_started_at = first_termination.detected_at + timedelta(
            milliseconds=1
        )
        second_handshake_completed_at = first_termination.detected_at + timedelta(
            milliseconds=2
        )
        second_handshake_started_ns = (
            first_termination.detected_monotonic_ns + 1_000_000
        )
        second_handshake_completed_ns = (
            first_termination.detected_monotonic_ns + 2_000_000
        )
        runtime_clock.value = second_handshake_completed_at
        runtime_clock.monotonic_ns = second_handshake_completed_ns
        projection_clock.value = max(
            projection_clock.value,
            second_handshake_completed_at + timedelta(milliseconds=100),
        ) + timedelta(milliseconds=1)
        second_session = signed_session(
            fixture_policy=policy,
            scope=scope,
            primary=primary,
            signer=signer,
            session_nonce_label="early-ack-session-two",
            connection_generation=2,
            parent_transport_session_id=first_session.transport_session_id,
            handshake_started_at=second_handshake_started_at,
            handshake_completed_at=second_handshake_completed_at,
            handshake_started_monotonic_ns=second_handshake_started_ns,
            handshake_completed_monotonic_ns=second_handshake_completed_ns,
            monotonic_clock_domain_id=domain_id,
            deployment_capability=capability,
        )
        second_session_id = second_session.transport_session_id
        second_socket_owner = integrated_socket_owner(
            second_session,
            label="early-ack-socket-two",
        )
        runtime.commit_session(
            second_session,
            socket_owner=second_socket_owner,
            idempotency_key="early-ack-session-two",
        )
        second_termination = runtime.terminate_current(
            TransportSessionTerminationReasonV4.LOCAL_CLOSE
        )
        assert second_termination.transport_session_id == second_session_id
        runtime.close()
        assert not lease.is_held

        live_report = store.verify()
        assert live_report.transport_session_attestation_count == 2
        assert live_report.transport_socket_owner_binding_count == 2
        assert live_report.outbound_subscription_intent_count == 1
        assert live_report.subscription_ack_binding_count == 1
        assert live_report.transport_session_termination_count == 2

    reopen_clock = IntegratedClock(
        value=T0 + timedelta(hours=1),
        monotonic_ns=2_000_000_000,
        domain_id=domain_id,
    )
    with PhysicalProjectionStoreV4(path, clock=reopen_clock) as reopened:
        reopened_report = reopened.verify()
        assert reopened_report.transport_session_attestation_count == 2
        assert reopened_report.outbound_subscription_intent_count == 1
        assert reopened_report.subscription_ack_binding_count == 1
        assert reopened_report.transport_session_termination_count == 2
        row = reopened._connection.execute(  # noqa: SLF001
            """
            SELECT hex(message_disposition_id), hex(transport_session_id)
            FROM subscription_ack_bindings
            """
        ).fetchone()
        assert row == (ack_disposition_id.upper(), first_session_id.upper())
        assert second_session_id != first_session_id


def test_real_lost_writer_lease_blocks_pending_ack_bind_and_recovery_reconciles(
    tmp_path: Path,
) -> None:
    path = tmp_path / "runtime-lost-lease-before-ack-bind.sqlite3"
    signer = Ed25519CheckpointSigner.generate()
    domain_id = _test_boottime_domain()
    projection_clock = IntegratedClock(
        value=T0 - timedelta(hours=1),
        monotonic_ns=0,
        domain_id=domain_id,
    )
    runtime_clock = IntegratedClock(
        value=T0 - timedelta(milliseconds=500),
        monotonic_ns=200_000_000,
        domain_id=domain_id,
    )

    with PhysicalProjectionStoreV4(path, clock=projection_clock) as store:
        (
            primary,
            required_status,
            scope,
            policy,
            admission,
            capability,
        ) = append_runtime_authority_foundation(store, signer=signer)
        projection_clock.source_id = capability.clock_source_manifest_id
        runtime_clock.source_id = capability.clock_source_manifest_id
        session = signed_session(
            fixture_policy=policy,
            scope=scope,
            primary=primary,
            signer=signer,
            monotonic_clock_domain_id=domain_id,
            deployment_capability=capability,
        )
        projection_clock.value = T0 - timedelta(milliseconds=500)
        lease = private_lease(tmp_path, holder_id="lost-lease-runtime")
        runtime = PhysicalTransportRuntimeV4.for_test(
            journal=store,
            writer_lease=lease,
            clock_source=runtime_clock,
            signer=signer,
            deployment_admission=admission,
            idempotency_prefix="lost-lease-runtime",
            wall_clock=runtime_clock,
        )
        runtime.start()
        socket_owner = integrated_socket_owner(
            session,
            label="lost-lease-socket",
        )
        runtime.commit_session(
            session,
            socket_owner=socket_owner,
            idempotency_key="lost-lease-session",
        )
        socket_id = runtime.current_socket_lease_id
        assert socket_id is not None
        permit = runtime.authorize_send_permit(idempotency_key="lost-lease-intent")
        intent = runtime._intent  # noqa: SLF001 - integration checks exact journal record
        assert intent is not None
        owner_binding = runtime._socket_owner_binding  # noqa: SLF001
        fence_token = runtime._writer_fence_token_sha256  # noqa: SLF001
        fence_generation = runtime._writer_fence_generation  # noqa: SLF001
        assert owner_binding is not None
        assert fence_token is not None
        assert fence_generation is not None
        fixture = TransportFixture(
            primary=primary,
            required_status=required_status,
            scope=scope,
            signer=signer,
            deployment_capability=capability,
            policy=policy,
            session=session,
            intent=intent,
            socket_owner_binding=owner_binding,
            writer_fence_token_sha256=fence_token,
            writer_fence_generation=fence_generation,
        )
        ack_received_at = T0 - timedelta(milliseconds=480)

        class LeaseLosingAckSender:
            async def send_exact_text_frame(self, _: bytes) -> None:
                occurrence = append_ack_occurrence(
                    store,
                    clock=projection_clock,
                    fixture=fixture,
                    intent=intent,
                    payload=ack_payload(
                        request_id=intent.request_id,
                        provider_connection_id="provider-connection-lost-lease",
                    ),
                    sequence=1,
                    received_at=ack_received_at,
                    idempotency_suffix="runtime-lost-lease-ack",
                )
                assert (
                    runtime.observe_captured_ack(
                        message_disposition_id=(
                            occurrence.classification.disposition.message_disposition_id
                        ),
                        socket_lease_id=socket_id,
                    )
                    is None
                )
                lease.release()

        socket_owner.writer = LeaseLosingAckSender().send_exact_text_frame
        try:
            with pytest.raises(PhysicalTransportRuntimeV4FaultLatched):
                asyncio.run(
                    runtime.dispatch_text(
                        permit,
                        socket_lease_id=socket_id,
                        sender=socket_owner,
                    )
                )
            assert runtime.state is PhysicalTransportRuntimeStateV4.FAULT_LATCHED
            failed_report = store.verify()
            assert failed_report.subscription_ack_binding_count == 0
            assert failed_report.transport_session_termination_count == 0
        finally:
            runtime.close()
        assert not lease.is_held

        runtime_clock.value = ack_received_at + timedelta(milliseconds=1)
        runtime_clock.monotonic_ns = 1_001_000_000
        projection_clock.value = max(
            projection_clock.value,
            ack_received_at + timedelta(milliseconds=100),
            runtime_clock.value,
        ) + timedelta(seconds=1)
        recovery_lease = private_lease(tmp_path, holder_id="lost-lease-recovery")
        recovery = PhysicalTransportRuntimeV4.for_test(
            journal=store,
            writer_lease=recovery_lease,
            clock_source=runtime_clock,
            signer=signer,
            deployment_admission=admission,
            idempotency_prefix="lost-lease-recovery",
            wall_clock=runtime_clock,
        )
        recovery_report = recovery.start()
        assert recovery_report.writer_fence_generation == 2
        assert recovery_report.deployment_bundle_id == capability.deployment_bundle_id
        assert recovery_report.deployment_sequence == capability.deployment_sequence
        assert (
            recovery_report.deployment_trust_root_id
            == capability.deployment_trust_root_id
        )
        assert (
            recovery_report.clock_source_manifest_id
            == capability.clock_source_manifest_id
        )
        assert recovery_report.reconciled_transport_session_ids == (
            session.transport_session_id,
        )
        recovery.close()
        assert not recovery_lease.is_held

        recovered_report = store.verify()
        assert recovered_report.transport_session_attestation_count == 1
        assert recovered_report.outbound_subscription_intent_count == 1
        assert recovered_report.subscription_ack_binding_count == 0
        assert recovered_report.transport_session_termination_count == 1

    with PhysicalProjectionStoreV4(
        path,
        clock=IntegratedClock(
            value=T0 + timedelta(hours=1),
            monotonic_ns=2_000_000_000,
            domain_id=domain_id,
        ),
    ) as reopened:
        reopened_report = reopened.verify()
        assert reopened_report.subscription_ack_binding_count == 0
        assert reopened_report.transport_session_termination_count == 1

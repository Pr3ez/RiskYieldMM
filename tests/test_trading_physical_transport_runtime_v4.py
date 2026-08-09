from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from riskyieldmm.trading.canonical import CanonicalizationError, sha256_digest
from riskyieldmm.trading.ledger_signing import Ed25519CheckpointSigner
from riskyieldmm.trading.operational_manifests_v4 import (
    CLOCK_SOURCE_KIND,
    COLLECTOR_KEY_USAGE,
    DEPENDENCY_LOCK_FORMAT,
    MONOTONIC_DOMAIN_PROFILE,
    TLS_TRUST_STORE_FORMAT,
    TLS_VERIFY_PURPOSE,
    ClockSourcePolicyManifestV4,
    CollectorKeyAuthorizationManifestV4,
    CollectorReleaseManifestV4,
    DependencyLockManifestV4,
    DeploymentAuthorityCeilingV4,
    DeploymentBundleV4,
    DeploymentRoleKeyV4,
    DeploymentTrustRootV4,
    RuntimeEnvironmentManifestV4,
    TlsTrustStoreManifestV4,
    VerifiedDeploymentCapabilityV4,
    approve_deployment_bundle_v4,
    derive_deployment_signing_key_id,
)
from riskyieldmm.trading.physical_projection_v4 import (
    PhysicalProjectionV4ConflictError,
)
from riskyieldmm.trading.physical_transport_control_runtime_v4 import (
    PhysicalTransportControlMediatorV4,
)
from riskyieldmm.trading.physical_transport_owner_v4 import (
    CommittedBoundTransportSessionV4,
    TransportSocketOwnerBindingV4,
    TransportSocketOwnerSnapshotV4,
    derive_linux_boottime_clock_domain_id,
)
from riskyieldmm.trading.physical_transport_runtime_v4 import (
    ClockEvidenceV4,
    OperationalDeploymentAdmissionV4,
    PhysicalTransportAckBindingV4Error,
    PhysicalTransportClockEvidenceV4Error,
    PhysicalTransportDispatchUnknownV4,
    PhysicalTransportRuntimeConfigV4,
    PhysicalTransportRuntimeStateV4,
    PhysicalTransportRuntimeV4,
    PhysicalTransportRuntimeV4Error,
    PhysicalTransportRuntimeV4FaultLatched,
    PhysicalTransportRuntimeV4StateError,
    PhysicalTransportSendPermitV4,
    PhysicalTransportSendPermitV4Error,
    PhysicalTransportStaleCallbackV4,
)
from riskyieldmm.trading.physical_transport_v4 import (
    BYBIT_V5_LINEAR_ENDPOINT_V4,
    BYBIT_V5_LINEAR_TLS_SERVER_NAME_V4,
    V4_TRANSPORT_HANDSHAKE_COMMITMENT_PROFILE,
    OutboundSubscriptionIntentV4,
    SubscriptionAckBindingV4,
    TransportSessionAttestationV4,
    TransportSessionTerminationReasonV4,
    TransportSessionTerminationV4,
    build_outbound_subscription_intent_v4,
    derive_transport_attestation_key_id,
)
from tests._chronyd_launch_policy_v48b import (
    make_test_chronyd_launch_policy_v48b,
)

T0 = datetime(2026, 7, 15, 10, tzinfo=timezone.utc)


def digest(label: str) -> str:
    return sha256_digest({"label": label})


def deployment_admission(
    signer: Ed25519CheckpointSigner,
    *,
    clock_source_manifest_id: str | None = None,
    valid_from: datetime = T0 - timedelta(days=1),
    valid_until: datetime = T0 + timedelta(days=1),
) -> OperationalDeploymentAdmissionV4:
    release = CollectorReleaseManifestV4(
        release_name="riskyieldmm-collector",
        release_version="0.1.0-test",
        source_tree_sha256=digest("source-tree"),
        build_artifact_sha256=digest("collector-wheel"),
        entrypoint="riskyieldmm.transport.collector",
        parser_policy_root_sha256=digest("parser-policy-root"),
    )
    lock = DependencyLockManifestV4(
        lock_format=DEPENDENCY_LOCK_FORMAT,
        lock_file_sha256=digest("requirements-lock"),
        wheelhouse_root_sha256=digest("wheelhouse-root"),
        distribution_count=3,
        require_hashes=True,
        only_binary=True,
        fully_pinned=True,
    )
    trust_store = TlsTrustStoreManifestV4(
        bundle_format=TLS_TRUST_STORE_FORMAT,
        ca_bundle_sha256=digest("ca-bundle"),
        ca_bundle_size_bytes=4096,
        ca_certificate_count=2,
        ca_der_set_root_sha256=digest("ca-der-set-root"),
        openssl_verify_purpose=TLS_VERIFY_PURPOSE,
    )
    clock_policy = ClockSourcePolicyManifestV4(
        source_kind=CLOCK_SOURCE_KIND,
        chrony_version="4.6-test",
        chronyc_executable_path="/usr/bin/chronyc",
        chronyc_executable_sha256=digest("chronyc-executable"),
        chrony_config_path="/etc/chrony/chrony.conf",
        chrony_config_sha256=digest("chrony-config"),
        chronyc_command_socket_path="/run/chrony/chronyd.sock",
        chronyc_command_timeout_milliseconds=2_000,
        chronyc_max_output_bytes=65_536,
        configured_source_set_root_sha256=digest("chrony-source-set"),
        min_selectable_sources=2,
        max_uncertainty_milliseconds=250,
        max_sample_age_milliseconds=5_000,
        require_synchronized=True,
        require_normal_leap=True,
        monotonic_domain_profile=MONOTONIC_DOMAIN_PROFILE,
        chronyd_launch_policy=make_test_chronyd_launch_policy_v48b(
            read_only_api_socket_path="/run/chrony/chronyd.sock"
        ),
    )
    if (
        clock_source_manifest_id is not None
        and clock_policy.manifest_id != clock_source_manifest_id
    ):
        raise AssertionError("test clock manifest identity differs")
    runtime = RuntimeEnvironmentManifestV4(
        python_implementation="CPython",
        python_version="3.12.0-test",
        python_executable_sha256=digest("python-executable"),
        platform_tag="linux_x86_64_test",
        openssl_version="OpenSSL_3_test",
        installed_distribution_root_sha256=digest("installed-distributions"),
        dependency_lock_manifest_id=lock.manifest_id,
        collector_release_manifest_id=release.manifest_id,
        tls_trust_store_manifest_id=trust_store.manifest_id,
        clock_source_policy_manifest_id=clock_policy.manifest_id,
        isolated_mode=True,
        user_site_enabled=False,
    )
    key_authorization = CollectorKeyAuthorizationManifestV4(
        collector_attestation_key_id=derive_transport_attestation_key_id(
            signer.public_key_bytes
        ),
        collector_attestation_public_key_hex=signer.public_key_bytes.hex(),
        usage=COLLECTOR_KEY_USAGE,
        collector_release_manifest_id=release.manifest_id,
        valid_from=valid_from,
        valid_until=valid_until,
    )
    deployment_signer = Ed25519CheckpointSigner.generate()
    deployment_key = DeploymentRoleKeyV4(
        key_id=derive_deployment_signing_key_id(deployment_signer.public_key_bytes),
        public_key_hex=deployment_signer.public_key_bytes.hex(),
    )
    trust_root = DeploymentTrustRootV4(
        root_version=1,
        deployment_role_threshold=1,
        deployment_keys=(deployment_key,),
    )
    bundle = DeploymentBundleV4(
        deployment_trust_root_id=trust_root.trust_root_id,
        deployment_sequence=1,
        parent_deployment_bundle_id=None,
        valid_from=valid_from,
        valid_until=valid_until,
        environment_id="MAINNET",
        authority_ceiling=(
            DeploymentAuthorityCeilingV4.PUBLIC_MARKET_DATA_CAPTURE_ONLY
        ),
        collector_release_manifest_id=release.manifest_id,
        dependency_lock_manifest_id=lock.manifest_id,
        tls_trust_store_manifest_id=trust_store.manifest_id,
        clock_source_policy_manifest_id=clock_policy.manifest_id,
        runtime_environment_manifest_id=runtime.manifest_id,
        collector_key_authorization_manifest_id=key_authorization.manifest_id,
    )
    approval = approve_deployment_bundle_v4(
        bundle,
        signers=(deployment_signer,),
    )
    return OperationalDeploymentAdmissionV4(
        trust_root=trust_root,
        expected_trust_root_id=trust_root.trust_root_id,
        approval=approval,
        children=(
            release,
            lock,
            trust_store,
            clock_policy,
            runtime,
            key_authorization,
        ),
    )


class DeterministicClock:
    def __init__(self, *, source_id: str | None = None) -> None:
        self.now = T0 + timedelta(milliseconds=10)
        self.monotonic_ns = 10_000
        self.domain_id = derive_linux_boottime_clock_domain_id(
            kernel_boot_id="boot-1",
            time_namespace_id=digest("runtime-test-time-namespace"),
        )
        self.source_id = source_id or digest("clock-source-manifest")
        self.synchronized = True
        self.uncertainty_milliseconds = 1
        self.evidence_lifetime = timedelta(seconds=1)
        self.last_sample: ClockEvidenceV4 | None = None
        self.samples: list[ClockEvidenceV4] = []
        self.chronyd_launch_id: str | None = None
        self.chronyd_runtime_observation_sha256: str | None = None

    def sample(self) -> ClockEvidenceV4:
        evidence = ClockEvidenceV4(
            clock_source_manifest_id=self.source_id,
            monotonic_clock_domain_id=self.domain_id,
            sampled_at=self.now,
            monotonic_ns=self.monotonic_ns,
            uncertainty_milliseconds=self.uncertainty_milliseconds,
            synchronized=self.synchronized,
            valid_until=self.now + self.evidence_lifetime,
            chronyd_launch_id=self.chronyd_launch_id,
            chronyd_runtime_observation_sha256=(
                self.chronyd_runtime_observation_sha256
            ),
        )
        self.last_sample = evidence
        self.samples.append(evidence)
        self.now += timedelta(milliseconds=1)
        self.monotonic_ns += 1_000
        return evidence

    def wall_clock(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta
        self.monotonic_ns += max(1, int(delta.total_seconds() * 1_000_000_000))


class DeterministicRandom:
    def __init__(self) -> None:
        self.counter = 0
        self.next_result: bytes | None = None

    def __call__(self, length: int) -> bytes:
        if self.next_result is not None:
            result = self.next_result
            self.next_result = None
            return result
        self.counter += 1
        return bytes([self.counter]) * length


def test_clock_evidence_requires_complete_loaded_chronyd_identity_pair() -> None:
    arguments = {
        "clock_source_manifest_id": digest("clock-source"),
        "monotonic_clock_domain_id": digest("clock-domain"),
        "sampled_at": T0,
        "monotonic_ns": 1_000,
        "uncertainty_milliseconds": 1,
        "synchronized": True,
        "valid_until": T0 + timedelta(seconds=1),
    }
    with pytest.raises(CanonicalizationError, match="must be paired"):
        ClockEvidenceV4(**arguments, chronyd_launch_id=digest("launch"))

    evidence = ClockEvidenceV4(
        **arguments,
        chronyd_launch_id=digest("launch"),
        chronyd_runtime_observation_sha256=digest("runtime-observation"),
    )
    assert evidence.chronyd_launch_id == digest("launch")


class FakeWriterLease:
    def __init__(self) -> None:
        self.token = "11" * 32
        self.holder_id = "collector-test-writer"
        self.held = True
        self.released = False
        self.events: list[str] | None = None

    @property
    def lease_token(self) -> str:
        return self.token

    def assert_held(self) -> None:
        if not self.held:
            raise RuntimeError("writer lease lost")

    def release(self) -> None:
        if self.events is not None:
            self.events.append("release-os-lease")
        self.held = False
        self.released = True


@dataclass
class FakeSocketOwner:
    current_snapshot: TransportSocketOwnerSnapshotV4
    aborted: bool = False
    abort_count: int = 0
    assertion_error: BaseException | None = None
    snapshot_error: BaseException | None = None
    assert_count: int = 0
    fail_on_assert_count: int | None = None
    abort_error: BaseException | None = None
    send_callback: Callable[[bytes], Awaitable[None]] | None = None

    def snapshot(self) -> TransportSocketOwnerSnapshotV4:
        if self.snapshot_error is not None:
            raise self.snapshot_error
        return self.current_snapshot

    def assert_same_owner(self, expected: TransportSocketOwnerSnapshotV4) -> None:
        self.assert_count += 1
        if self.assertion_error is not None:
            raise self.assertion_error
        if self.fail_on_assert_count == self.assert_count:
            raise RuntimeError("socket owner changed at configured assertion")
        if self.aborted or self.current_snapshot != expected:
            raise RuntimeError("socket owner changed")

    def abort(self) -> None:
        if self.abort_error is not None:
            raise self.abort_error
        if not self.aborted:
            self.abort_count += 1
        self.aborted = True

    async def send_exact_text_frame(
        self,
        payload: bytes,
        *,
        before_driver: Callable[[], None],
    ) -> None:
        if self.send_callback is None:
            raise RuntimeError("test socket owner has no exact-text writer")
        before_driver()
        await self.send_callback(payload)


class CoupledGovernedAuthority(DeterministicClock):
    """Rich test authority implementing the single V4.7B owner/clock/writer."""

    def __init__(
        self,
        *,
        source_id: str,
        chronyd_launch_id: str | None = None,
        chronyd_runtime_observation_sha256: str | None = None,
    ) -> None:
        super().__init__(source_id=source_id)
        self.aborted = False
        self.is_live_profile = False
        self.chronyd_launch_id = chronyd_launch_id
        self.chronyd_runtime_observation_sha256 = chronyd_runtime_observation_sha256
        self.current_snapshot = TransportSocketOwnerSnapshotV4(
            kernel_boot_id="boot-1",
            time_namespace_id=digest("runtime-test-time-namespace"),
            network_namespace_id=digest("runtime-test-network-namespace"),
            socket_cookie_u64="0000000000000042",
            clock_resolution_ns=1,
            chronyd_launch_id=chronyd_launch_id,
            chronyd_runtime_observation_sha256=(chronyd_runtime_observation_sha256),
        )

    def sample(self) -> ClockEvidenceV4:
        before_ns = self.monotonic_ns
        after_ns = before_ns + 10
        wall_before = self.now
        wall_after = wall_before + timedelta(microseconds=1)
        evidence = ClockEvidenceV4(
            clock_source_manifest_id=self.source_id,
            monotonic_clock_domain_id=self.domain_id,
            sampled_at=wall_after,
            monotonic_ns=after_ns,
            uncertainty_milliseconds=self.uncertainty_milliseconds,
            synchronized=self.synchronized,
            valid_until=wall_after + self.evidence_lifetime,
            monotonic_before_ns=before_ns,
            monotonic_after_ns=after_ns,
            wall_before_at=wall_before,
            wall_after_at=wall_after,
            clock_resolution_ns=1,
            observation_sha256=digest(f"clock-observation-{len(self.samples)}"),
            selectable_source_count=3,
            chronyd_launch_id=self.chronyd_launch_id,
            chronyd_runtime_observation_sha256=(
                self.chronyd_runtime_observation_sha256
            ),
        )
        self.last_sample = evidence
        self.samples.append(evidence)
        self.now = wall_after + timedelta(milliseconds=1)
        self.monotonic_ns = after_ns + 1_000
        return evidence

    def snapshot(self) -> TransportSocketOwnerSnapshotV4:
        if self.aborted:
            raise RuntimeError("coupled authority was aborted")
        return self.current_snapshot

    def assert_same_owner(self, expected: TransportSocketOwnerSnapshotV4) -> None:
        if self.aborted or expected != self.current_snapshot:
            raise RuntimeError("coupled authority changed")

    async def send_exact_text_frame(
        self,
        payload: bytes,
        *,
        before_driver: Callable[[], None],
    ) -> None:
        if self.aborted or not payload:
            raise RuntimeError("coupled authority cannot write")
        before_driver()

    async def submit_permitted_chunks(
        self,
        *,
        permit: Any,
        ordered_chunks: tuple[bytes, ...],
        before_driver: Callable[[], None],
    ) -> int:
        if self.aborted or permit is None:
            raise RuntimeError("coupled authority cannot write control")
        before_driver()
        return sum(len(item) for item in ordered_chunks)

    def abort(self) -> None:
        self.aborted = True


def fake_socket_owner(
    session: TransportSessionAttestationV4,
    *,
    label: str,
) -> FakeSocketOwner:
    cookie = digest(f"{label}-socket-cookie")[:16]
    if cookie == "0000000000000000":
        cookie = "0000000000000001"
    snapshot = TransportSocketOwnerSnapshotV4(
        kernel_boot_id=session.collector_boot_id,
        time_namespace_id=digest("runtime-test-time-namespace"),
        network_namespace_id=digest("runtime-test-network-namespace"),
        socket_cookie_u64=cookie,
        clock_resolution_ns=1,
    )
    return FakeSocketOwner(current_snapshot=snapshot)


def make_session(
    signer: Ed25519CheckpointSigner,
    *,
    deployment_capability: VerifiedDeploymentCapabilityV4 | None = None,
    generation: int = 1,
    parent_transport_session_id: str | None = None,
    domain_id: str | None = None,
    handshake_completed_at: datetime | None = None,
    clock_uncertainty_milliseconds: int = 1,
) -> TransportSessionAttestationV4:
    bindings = (
        {
            "deployment_bundle_id": digest("deployment-bundle"),
            "clock_source_manifest_id": digest("clock-source-manifest"),
            "collector_key_authorization_manifest_id": digest(
                "collector-key-authorization"
            ),
            "collector_release_hash": digest("collector-release"),
            "collector_runtime_id": digest("collector-runtime"),
            "trust_store_manifest_id": digest("trust-store"),
        }
        if deployment_capability is None
        else deployment_capability.transport_session_bindings()
    )
    started_ns = generation * 1_000
    completed_ns = started_ns + 500
    completed_at = handshake_completed_at or (
        T0 + timedelta(milliseconds=generation, microseconds=500)
    )
    return TransportSessionAttestationV4.create_signed(
        signer=signer,
        deployment_bundle_id=bindings["deployment_bundle_id"],
        clock_source_manifest_id=bindings["clock_source_manifest_id"],
        collector_key_authorization_manifest_id=(
            bindings["collector_key_authorization_manifest_id"]
        ),
        transport_subscription_policy_id=digest("policy"),
        physical_scope_manifest_id=digest("scope"),
        adapter_policy_id=digest("adapter"),
        capture_partition_id=digest("partition"),
        collector_instance_id="collector-1",
        collector_boot_id="boot-1",
        connection_generation=generation,
        session_nonce=digest(f"session-nonce-{generation}"),
        parent_transport_session_id=parent_transport_session_id,
        authoritative_endpoint=BYBIT_V5_LINEAR_ENDPOINT_V4,
        tls_server_name=BYBIT_V5_LINEAR_TLS_SERVER_NAME_V4,
        remote_address="203.0.113.10:443",
        tls_version="TLSv1.3",
        tls_cipher="TLS_AES_128_GCM_SHA256",
        alpn_protocol=None,
        websocket_extensions=(),
        peer_certificate_sha256=digest("leaf-certificate"),
        peer_spki_sha256=digest("leaf-spki"),
        trust_store_manifest_id=bindings["trust_store_manifest_id"],
        certificate_verified=True,
        hostname_verified=True,
        websocket_http_status=101,
        websocket_accept_verified=True,
        handshake_commitment_profile=V4_TRANSPORT_HANDSHAKE_COMMITMENT_PROFILE,
        handshake_request_sha256=digest(f"handshake-request-{generation}"),
        handshake_response_sha256=digest(f"handshake-response-{generation}"),
        handshake_started_at=completed_at - timedelta(microseconds=500),
        handshake_completed_at=completed_at,
        monotonic_clock_domain_id=(
            derive_linux_boottime_clock_domain_id(
                kernel_boot_id="boot-1",
                time_namespace_id=digest("runtime-test-time-namespace"),
            )
            if domain_id is None
            else domain_id
        ),
        handshake_started_monotonic_ns=started_ns,
        handshake_completed_monotonic_ns=completed_ns,
        clock_uncertainty_milliseconds=clock_uncertainty_milliseconds,
        collector_release_hash=bindings["collector_release_hash"],
        collector_runtime_id=bindings["collector_runtime_id"],
    )


class FakeJournal:
    def __init__(
        self,
        *,
        signer: Ed25519CheckpointSigner,
        clock: DeterministicClock,
    ) -> None:
        self.signer = signer
        self.clock = clock
        self.events: list[str] = []
        self.expected_deployment: tuple[str, str, int] | None = None
        self.session: TransportSessionAttestationV4 | None = None
        self.socket_owner_binding: TransportSocketOwnerBindingV4 | None = None
        self.intent: OutboundSubscriptionIntentV4 | None = None
        self.binding: SubscriptionAckBindingV4 | None = None
        self.terminations: list[TransportSessionTerminationV4] = []
        self.verify_error: BaseException | None = None
        self.verify_advance: timedelta | None = None
        self.reconcile_error: BaseException | None = None
        self.session_error: BaseException | None = None
        self.authorization_error: BaseException | None = None
        self.bind_error: BaseException | None = None
        self.termination_error: BaseException | None = None
        self.authorization_count = 0
        self.return_wrong_intent_session = False
        self.return_wrong_intent_scope = False
        self.return_wrong_session_record = False
        self.return_wrong_binding_disposition = False
        self.return_wrong_termination_reason = False
        self.authorization_advance: timedelta | None = None
        self.authorization_hook: Callable[[], None] | None = None
        self.claimed_fence_token_sha256: str | None = None
        self.released_fence_token_sha256: str | None = None
        self.reconcile_evidence: tuple[datetime, int, str] | None = None
        self.claim_fence_error: BaseException | None = None
        self.release_fence_error: BaseException | None = None
        self.assert_fence_error: BaseException | None = None
        self.assert_fence_advance: timedelta | None = None

    def assert_current_operational_deployment(
        self,
        *,
        deployment_bundle_id: str,
        deployment_trust_root_id: str,
        deployment_sequence: int,
    ) -> None:
        supplied = (
            deployment_bundle_id,
            deployment_trust_root_id,
            deployment_sequence,
        )
        if self.expected_deployment is None:
            raise RuntimeError("expected operational deployment is not configured")
        if supplied != self.expected_deployment:
            raise RuntimeError("operational deployment differs")

    def claim_transport_runtime_writer_fence(
        self, *, lease_token_sha256: str, holder_id: str
    ) -> int:
        self.events.append("claim-fence")
        if self.claim_fence_error is not None:
            raise self.claim_fence_error
        assert holder_id == "collector-test-writer"
        self.claimed_fence_token_sha256 = lease_token_sha256
        return 7

    def release_transport_runtime_writer_fence(
        self, *, lease_token_sha256: str
    ) -> None:
        self.events.append("release-fence")
        if self.release_fence_error is not None:
            raise self.release_fence_error
        assert lease_token_sha256 == self.claimed_fence_token_sha256
        self.released_fence_token_sha256 = lease_token_sha256

    def assert_transport_runtime_writer_fence(
        self, *, lease_token_sha256: str, generation: int
    ) -> None:
        self.events.append("assert-fence")
        if self.assert_fence_error is not None:
            raise self.assert_fence_error
        if self.assert_fence_advance is not None:
            self.clock.advance(self.assert_fence_advance)
        assert lease_token_sha256 == self.claimed_fence_token_sha256
        assert generation == 7

    def verify(self) -> None:
        self.events.append("verify")
        if self.verify_error is not None:
            raise self.verify_error
        if self.verify_advance is not None:
            self.clock.advance(self.verify_advance)

    def reconcile_unterminated_transport_sessions(
        self, **details: Any
    ) -> tuple[TransportSessionTerminationV4, ...]:
        self.events.append("reconcile")
        if self.reconcile_error is not None:
            raise self.reconcile_error
        self.reconcile_evidence = (
            details["detected_at"],
            details["detected_monotonic_ns"],
            details["detected_monotonic_clock_domain_id"],
        )
        return ()

    def append_transport_session_attestation(
        self,
        session: TransportSessionAttestationV4,
        *,
        socket_owner_binding: TransportSocketOwnerBindingV4,
        idempotency_key: str,
    ) -> CommittedBoundTransportSessionV4:
        del idempotency_key
        self.events.append("session")
        if self.session_error is not None:
            raise self.session_error
        self.session = session
        self.socket_owner_binding = socket_owner_binding
        if self.return_wrong_session_record:
            return object()  # type: ignore[return-value]
        return CommittedBoundTransportSessionV4(
            session=session,
            binding=socket_owner_binding,
        )

    def authorize_outbound_subscription_intent(
        self,
        transport_session_id: str,
        *,
        idempotency_key: str,
    ) -> OutboundSubscriptionIntentV4:
        del idempotency_key
        self.events.append("authorize")
        if self.authorization_advance is not None:
            self.clock.advance(self.authorization_advance)
        if self.authorization_error is not None:
            raise self.authorization_error
        assert self.session is not None
        assert transport_session_id == self.session.transport_session_id
        assert self.clock.last_sample is not None
        self.authorization_count += 1
        authorized_at = self.clock.last_sample.sampled_at
        intent = build_outbound_subscription_intent_v4(
            transport_subscription_policy_id=(
                self.session.transport_subscription_policy_id
            ),
            transport_session_id=(
                digest("wrong-session")
                if self.return_wrong_intent_session
                else self.session.transport_session_id
            ),
            physical_scope_manifest_id=(
                digest("wrong-scope")
                if self.return_wrong_intent_scope
                else self.session.physical_scope_manifest_id
            ),
            adapter_policy_id=self.session.adapter_policy_id,
            capture_partition_id=self.session.capture_partition_id,
            connection_generation=self.session.connection_generation,
            intent_nonce=digest(f"intent-{self.authorization_count}"),
            request_id=f"runtime-v45-{self.authorization_count}",
            topic="kline.1.BTCUSDT",
            authorized_at=authorized_at,
            send_not_after=authorized_at + timedelta(seconds=10),
            ack_not_after=authorized_at + timedelta(seconds=20),
        )
        self.intent = intent
        if self.authorization_hook is not None:
            self.authorization_hook()
        return intent

    def bind_subscription_ack(
        self,
        *,
        outbound_subscription_intent_id: str,
        message_disposition_id: str,
        dispatch_started_at: datetime,
        dispatch_completed_at: datetime,
        dispatch_started_monotonic_ns: int,
        dispatch_completed_monotonic_ns: int,
        signer: Ed25519CheckpointSigner,
        idempotency_key: str,
    ) -> SubscriptionAckBindingV4:
        del idempotency_key
        self.events.append("bind")
        if self.bind_error is not None:
            raise self.bind_error
        assert self.session is not None
        assert self.intent is not None
        assert outbound_subscription_intent_id == (
            self.intent.outbound_subscription_intent_id
        )
        binding = SubscriptionAckBindingV4.create_signed(
            signer=signer,
            transport_subscription_policy_id=(
                self.session.transport_subscription_policy_id
            ),
            transport_session_id=self.session.transport_session_id,
            outbound_subscription_intent_id=outbound_subscription_intent_id,
            physical_scope_manifest_id=self.session.physical_scope_manifest_id,
            adapter_policy_id=self.session.adapter_policy_id,
            capture_partition_id=self.session.capture_partition_id,
            connection_generation=self.session.connection_generation,
            capture_segment_id=digest("capture-segment"),
            physical_message_id=digest("physical-message"),
            message_receipt_id=digest("message-receipt"),
            scope_message_sequence=1,
            provider_message_disposition_id=digest("provider-disposition"),
            message_disposition_id=(
                digest("wrong-binding-disposition")
                if self.return_wrong_binding_disposition
                else message_disposition_id
            ),
            raw_ack_sha256=digest("raw-ack"),
            echoed_request_id=self.intent.request_id,
            provider_connection_id="bybit-connection-1",
            request_command_sha256=self.intent.command_sha256,
            dispatch_started_at=dispatch_started_at,
            dispatch_completed_at=dispatch_completed_at,
            dispatch_started_monotonic_ns=dispatch_started_monotonic_ns,
            dispatch_completed_monotonic_ns=dispatch_completed_monotonic_ns,
            ack_received_at=dispatch_completed_at + timedelta(milliseconds=1),
            ack_received_monotonic_ns=dispatch_completed_monotonic_ns + 1_000,
            bound_at=dispatch_completed_at + timedelta(milliseconds=2),
        )
        self.binding = binding
        return binding

    def append_transport_session_termination(
        self,
        *,
        transport_session_id: str,
        reason: TransportSessionTerminationReasonV4,
        detected_at: datetime,
        detected_monotonic_ns: int,
        detected_monotonic_clock_domain_id: str,
        signer: Ed25519CheckpointSigner,
        idempotency_key: str,
        close_code: int | None = None,
        close_reason_digest: str | None = None,
    ) -> TransportSessionTerminationV4:
        del idempotency_key
        self.events.append(f"terminate:{reason.value}")
        if self.termination_error is not None:
            raise self.termination_error
        assert self.session is not None
        assert transport_session_id == self.session.transport_session_id
        returned_reason = (
            (
                TransportSessionTerminationReasonV4.LOCAL_CLOSE
                if reason is TransportSessionTerminationReasonV4.SUPERSEDED
                else TransportSessionTerminationReasonV4.SUPERSEDED
            )
            if self.return_wrong_termination_reason
            else reason
        )
        termination = TransportSessionTerminationV4.create_signed(
            signer=signer,
            transport_subscription_policy_id=(
                self.session.transport_subscription_policy_id
            ),
            transport_session_id=self.session.transport_session_id,
            physical_scope_manifest_id=self.session.physical_scope_manifest_id,
            capture_partition_id=self.session.capture_partition_id,
            connection_generation=self.session.connection_generation,
            reason=returned_reason,
            close_code=close_code,
            close_reason_digest=close_reason_digest,
            detected_at=detected_at,
            detected_monotonic_clock_domain_id=(detected_monotonic_clock_domain_id),
            detected_monotonic_ns=detected_monotonic_ns,
            recorded_at=detected_at + timedelta(milliseconds=1),
        )
        self.terminations.append(termination)
        return termination


@dataclass
class Harness:
    signer: Ed25519CheckpointSigner
    admission: OperationalDeploymentAdmissionV4
    capability: VerifiedDeploymentCapabilityV4
    clock: DeterministicClock
    lease: FakeWriterLease
    journal: FakeJournal
    runtime: PhysicalTransportRuntimeV4
    random: DeterministicRandom
    socket_owners: list[FakeSocketOwner]

    def start_and_commit(
        self,
        *,
        generation: int = 1,
        parent_transport_session_id: str | None = None,
        socket_label: str = "socket-1",
    ) -> tuple[TransportSessionAttestationV4, str]:
        if self.runtime.state is PhysicalTransportRuntimeStateV4.COLD:
            self.runtime.start()
        session = make_session(
            self.signer,
            deployment_capability=self.capability,
            generation=generation,
            parent_transport_session_id=parent_transport_session_id,
            domain_id=self.clock.domain_id,
        )
        socket_owner = fake_socket_owner(session, label=socket_label)
        self.socket_owners.append(socket_owner)
        self.runtime.commit_session(
            session,
            socket_owner=socket_owner,
            idempotency_key=f"session-{generation}",
        )
        socket_id = self.runtime.current_socket_lease_id
        assert socket_id is not None
        return session, socket_id


def make_harness(*, config: PhysicalTransportRuntimeConfigV4 | None = None) -> Harness:
    signer = Ed25519CheckpointSigner.generate()
    admission = deployment_admission(signer)
    capability = admission.verify(verified_at=T0, signer=signer)
    clock = DeterministicClock(source_id=capability.clock_source_manifest_id)
    lease = FakeWriterLease()
    journal = FakeJournal(signer=signer, clock=clock)
    journal.expected_deployment = (
        capability.deployment_bundle_id,
        capability.deployment_trust_root_id,
        capability.deployment_sequence,
    )
    lease.events = journal.events
    deterministic_random = DeterministicRandom()
    runtime = PhysicalTransportRuntimeV4.for_test(
        journal=journal,
        writer_lease=lease,
        clock_source=clock,
        signer=signer,
        deployment_admission=admission,
        idempotency_prefix="runtime-test",
        config=config,
        wall_clock=clock.wall_clock,
        random_bytes=deterministic_random,
    )
    return Harness(
        signer=signer,
        admission=admission,
        capability=capability,
        clock=clock,
        lease=lease,
        journal=journal,
        runtime=runtime,
        random=deterministic_random,
        socket_owners=[],
    )


def test_control_mediator_is_created_only_from_one_coupled_rich_authority() -> None:
    signer = Ed25519CheckpointSigner.generate()
    admission = deployment_admission(signer)
    capability = admission.verify(verified_at=T0, signer=signer)
    authority = CoupledGovernedAuthority(source_id=capability.clock_source_manifest_id)
    lease = FakeWriterLease()
    journal = FakeJournal(signer=signer, clock=authority)
    journal.expected_deployment = (
        capability.deployment_bundle_id,
        capability.deployment_trust_root_id,
        capability.deployment_sequence,
    )
    runtime = PhysicalTransportRuntimeV4.for_test(
        journal=journal,
        writer_lease=lease,
        clock_source=authority,
        signer=signer,
        deployment_admission=admission,
        idempotency_prefix="coupled-v47b",
        wall_clock=authority.wall_clock,
        random_bytes=DeterministicRandom(),
    )
    runtime.start()
    session = make_session(
        signer,
        deployment_capability=capability,
        domain_id=authority.domain_id,
    )
    runtime.commit_session(
        session,
        socket_owner=authority,
        idempotency_key="coupled-v47b-session",
    )

    mediator = runtime.create_control_mediator()

    assert mediator._writer is authority  # noqa: SLF001
    assert mediator._bound_authority is authority  # noqa: SLF001
    assert mediator._bound_binding is runtime._socket_owner_binding  # noqa: SLF001
    with pytest.raises(PhysicalTransportRuntimeV4StateError, match="already created"):
        runtime.create_control_mediator()


@pytest.mark.parametrize(
    ("replacement_launch_id", "replacement_runtime_observation"),
    [
        (None, None),
        (
            digest("v48b-control-replacement-launch"),
            digest("v48b-control-replacement-runtime-observation"),
        ),
    ],
    ids=("missing", "changed"),
)
def test_live_control_mediator_rejects_missing_or_changed_chronyd_pair(
    replacement_launch_id: str | None,
    replacement_runtime_observation: str | None,
) -> None:
    signer = Ed25519CheckpointSigner.generate()
    admission = deployment_admission(signer)
    capability = admission.verify(verified_at=T0, signer=signer)
    launch_id = digest("v48b-control-launch")
    runtime_observation = digest("v48b-control-runtime-observation")
    authority = CoupledGovernedAuthority(
        source_id=capability.clock_source_manifest_id,
        chronyd_launch_id=launch_id,
        chronyd_runtime_observation_sha256=runtime_observation,
    )
    lease = FakeWriterLease()
    journal = FakeJournal(signer=signer, clock=authority)
    journal.expected_deployment = (
        capability.deployment_bundle_id,
        capability.deployment_trust_root_id,
        capability.deployment_sequence,
    )
    runtime = PhysicalTransportRuntimeV4.for_test(
        journal=journal,
        writer_lease=lease,
        clock_source=authority,
        signer=signer,
        deployment_admission=admission,
        idempotency_prefix="paired-v48b-control",
        wall_clock=authority.wall_clock,
        random_bytes=DeterministicRandom(),
    )
    runtime.start()
    session = make_session(
        signer,
        deployment_capability=capability,
        domain_id=authority.domain_id,
    )
    runtime.commit_session(
        session,
        socket_owner=authority,
        idempotency_key="paired-v48b-control-session",
    )
    # Commit remains a deterministic profile until V4.9 supplies the reviewed
    # live TLS/Sans-I/O driver. The retained authority can then exercise the
    # already-sealed live control-mediator pair checks without a forged writer.
    authority.is_live_profile = True
    mediator = runtime.create_control_mediator()
    assert isinstance(mediator, PhysicalTransportControlMediatorV4)
    assert mediator.is_live_profile

    accepted = mediator._sample_clock()  # noqa: SLF001
    assert accepted.monotonic_before_ns < accepted.monotonic_after_ns
    authority.chronyd_launch_id = replacement_launch_id
    authority.chronyd_runtime_observation_sha256 = replacement_runtime_observation

    with pytest.raises(CanonicalizationError, match="outside binding"):
        mediator._sample_clock()  # noqa: SLF001


def test_live_commit_session_stays_v49_gated_before_chronyd_pair_consumption() -> None:
    class PairedLiveOwner:
        is_live_profile = True

        def __init__(self) -> None:
            self.aborted = False
            self.snapshot_calls = 0
            self.current_snapshot = TransportSocketOwnerSnapshotV4(
                kernel_boot_id="boot-1",
                time_namespace_id=digest("runtime-test-time-namespace"),
                network_namespace_id=digest("runtime-test-network-namespace"),
                socket_cookie_u64="0000000000000042",
                clock_resolution_ns=1,
                chronyd_launch_id=digest("v48b-commit-launch"),
                chronyd_runtime_observation_sha256=digest(
                    "v48b-commit-runtime-observation"
                ),
            )

        def snapshot(self) -> TransportSocketOwnerSnapshotV4:
            self.snapshot_calls += 1
            return self.current_snapshot

        def abort(self) -> None:
            self.aborted = True

    owner = PairedLiveOwner()
    runtime = object.__new__(PhysicalTransportRuntimeV4)
    runtime._state = PhysicalTransportRuntimeStateV4.READY  # noqa: SLF001
    runtime._is_live_profile = True  # noqa: SLF001
    runtime._clock_source = owner  # noqa: SLF001
    runtime._fault_cause = None  # noqa: SLF001

    with pytest.raises(PhysicalTransportRuntimeV4FaultLatched, match="V4.9"):
        runtime.commit_session(
            object(),  # type: ignore[arg-type]
            socket_owner=owner,  # type: ignore[arg-type]
            idempotency_key="v48b-live-commit-driver-gate",
        )

    assert owner.aborted
    assert owner.snapshot_calls == 0
    assert runtime.state is PhysicalTransportRuntimeStateV4.FAULT_LATCHED


async def successful_sender(_: bytes) -> None:
    return None


def owned_sender(
    harness: Harness,
    callback: Callable[[bytes], Awaitable[None]],
) -> FakeSocketOwner:
    owner = harness.socket_owners[-1]
    owner.send_callback = callback
    return owner


def test_start_verifies_before_reconciliation_and_only_then_becomes_ready() -> None:
    harness = make_harness()

    report = harness.runtime.start()

    assert harness.journal.events == ["claim-fence", "verify", "reconcile"]
    assert report.reconciled_transport_session_ids == ()
    assert report.deployment_bundle_id == harness.capability.deployment_bundle_id
    assert report.deployment_sequence == harness.capability.deployment_sequence
    assert (
        report.deployment_trust_root_id == harness.capability.deployment_trust_root_id
    )
    assert (
        report.clock_source_manifest_id == harness.capability.clock_source_manifest_id
    )
    assert report.monotonic_clock_domain_id == harness.clock.domain_id
    assert report.writer_fence_generation == 7
    assert (
        harness.journal.claimed_fence_token_sha256
        == hashlib.sha256(bytes.fromhex(harness.lease.lease_token)).hexdigest()
    )
    assert harness.runtime.state is PhysicalTransportRuntimeStateV4.READY


def test_start_rejects_projection_deployment_mismatch_before_fence_claim() -> None:
    harness = make_harness()
    harness.journal.expected_deployment = (
        digest("unapproved-deployment"),
        harness.capability.deployment_trust_root_id,
        harness.capability.deployment_sequence,
    )

    with pytest.raises(PhysicalTransportRuntimeV4FaultLatched):
        harness.runtime.start()

    assert "claim-fence" not in harness.journal.events
    assert harness.lease.released


def test_start_rejects_clock_source_outside_signed_deployment() -> None:
    harness = make_harness()
    harness.clock.source_id = digest("substituted-clock-source")

    with pytest.raises(PhysicalTransportRuntimeV4FaultLatched):
        harness.runtime.start()

    assert "claim-fence" not in harness.journal.events


def test_start_rejects_runtime_clock_limits_looser_than_signed_policy() -> None:
    harness = make_harness(
        config=PhysicalTransportRuntimeConfigV4(
            maximum_clock_uncertainty_milliseconds=3_600_000,
            maximum_clock_evidence_lifetime_seconds=3_600,
        )
    )

    with pytest.raises(PhysicalTransportRuntimeV4FaultLatched):
        harness.runtime.start()

    assert "claim-fence" not in harness.journal.events


def test_start_rejects_unapproved_online_transport_signer() -> None:
    harness = make_harness()
    harness.runtime._signer = Ed25519CheckpointSigner.generate()

    with pytest.raises(PhysicalTransportRuntimeV4FaultLatched):
        harness.runtime.start()

    assert "claim-fence" not in harness.journal.events


def test_session_manifest_substitution_latches_before_journal_append() -> None:
    harness = make_harness()
    harness.runtime.start()
    substituted = make_session(
        harness.signer,
        domain_id=harness.clock.domain_id,
    )

    with pytest.raises(PhysicalTransportRuntimeV4FaultLatched):
        harness.runtime.commit_session(
            substituted,
            socket_owner=fake_socket_owner(
                substituted, label="substituted-session-socket"
            ),
            idempotency_key="substituted-session",
        )

    assert "session" not in harness.journal.events


def test_deployment_expiry_latches_before_session_commit() -> None:
    harness = make_harness()
    harness.runtime.start()
    harness.clock.advance(timedelta(days=2))
    session = make_session(
        harness.signer,
        deployment_capability=harness.capability,
        domain_id=harness.clock.domain_id,
    )

    with pytest.raises(PhysicalTransportRuntimeV4FaultLatched):
        harness.runtime.commit_session(
            session,
            socket_owner=fake_socket_owner(session, label="expired-deployment-socket"),
            idempotency_key="expired-deployment-session",
        )

    assert "session" not in harness.journal.events


def test_slow_verify_forces_fresh_reconcile_and_ready_clock_samples() -> None:
    harness = make_harness()
    harness.journal.verify_advance = timedelta(seconds=10)

    harness.runtime.start()

    assert len(harness.clock.samples) == 3
    startup, reconcile, ready = harness.clock.samples
    assert reconcile.sampled_at > startup.valid_until
    assert reconcile.monotonic_ns > startup.monotonic_ns
    assert ready.monotonic_ns > reconcile.monotonic_ns
    assert harness.journal.reconcile_evidence == (
        reconcile.sampled_at,
        reconcile.monotonic_ns,
        reconcile.monotonic_clock_domain_id,
    )
    assert harness.runtime.state is PhysicalTransportRuntimeStateV4.READY


@pytest.mark.parametrize("failure_point", ("claim", "verify", "reconcile"))
def test_startup_failure_latches_authority_and_never_skips_verification(
    failure_point: str,
) -> None:
    harness = make_harness()
    error = OSError(f"{failure_point} failed")
    if failure_point == "claim":
        harness.journal.claim_fence_error = error
    elif failure_point == "verify":
        harness.journal.verify_error = error
    else:
        harness.journal.reconcile_error = error

    with pytest.raises(PhysicalTransportRuntimeV4FaultLatched):
        harness.runtime.start()

    assert harness.runtime.state is PhysicalTransportRuntimeStateV4.FAULT_LATCHED
    expected_events = {
        "claim": ["claim-fence", "release-fence", "release-os-lease"],
        "verify": [
            "claim-fence",
            "verify",
            "release-fence",
            "release-os-lease",
        ],
        "reconcile": [
            "claim-fence",
            "verify",
            "reconcile",
            "release-fence",
            "release-os-lease",
        ],
    }
    assert harness.journal.events == expected_events[failure_point]
    assert harness.lease.released
    with pytest.raises(PhysicalTransportRuntimeV4StateError):
        harness.runtime.start()


def test_close_releases_projection_fence_before_os_lease() -> None:
    harness = make_harness()
    harness.runtime.start()

    harness.runtime.close()

    assert harness.journal.events[-2:] == ["release-fence", "release-os-lease"]
    assert harness.journal.released_fence_token_sha256 == (
        harness.journal.claimed_fence_token_sha256
    )
    assert harness.lease.released
    assert harness.runtime.state is PhysicalTransportRuntimeStateV4.CLOSED


def test_terminal_record_does_not_require_a_still_live_socket_owner() -> None:
    harness = make_harness()
    session, _ = harness.start_and_commit()
    owner = harness.socket_owners[-1]
    owner.assertion_error = RuntimeError("socket disappeared")

    termination = harness.runtime.terminate_current(
        TransportSessionTerminationReasonV4.TRANSPORT_ERROR
    )

    assert termination.transport_session_id == session.transport_session_id
    assert harness.runtime.state is PhysicalTransportRuntimeStateV4.FENCED
    harness.runtime.close()
    assert owner.aborted


def test_owner_abort_failure_still_releases_projection_and_os_fences() -> None:
    harness = make_harness()
    harness.start_and_commit()
    harness.runtime.terminate_current(TransportSessionTerminationReasonV4.LOCAL_CLOSE)
    owner = harness.socket_owners[-1]
    owner.abort_error = OSError("socket close failed")

    with pytest.raises(PhysicalTransportRuntimeV4FaultLatched, match="release cleanly"):
        harness.runtime.close()

    assert harness.journal.events[-2:] == ["release-fence", "release-os-lease"]
    assert harness.lease.released
    assert harness.runtime.state is PhysicalTransportRuntimeStateV4.CLOSED


def test_projection_fence_release_failure_releases_os_lease_and_reports_fault() -> None:
    harness = make_harness()
    harness.runtime.start()
    harness.journal.release_fence_error = OSError("projection unavailable")

    with pytest.raises(PhysicalTransportRuntimeV4FaultLatched):
        harness.runtime.close()

    assert harness.journal.events[-2:] == ["release-fence", "release-os-lease"]
    assert harness.lease.released
    assert harness.runtime.state is PhysicalTransportRuntimeStateV4.CLOSED


def test_future_dated_handshake_is_rejected_before_session_commit() -> None:
    harness = make_harness()
    harness.runtime.start()
    future_session = make_session(
        harness.signer,
        deployment_capability=harness.capability,
        domain_id=harness.clock.domain_id,
        handshake_completed_at=T0 + timedelta(minutes=1),
    )

    with pytest.raises(PhysicalTransportRuntimeV4FaultLatched):
        harness.runtime.commit_session(
            future_session,
            socket_owner=fake_socket_owner(future_session, label="socket-1"),
            idempotency_key="future-session",
        )

    assert harness.runtime.state is PhysicalTransportRuntimeStateV4.FAULT_LATCHED
    assert "session" not in harness.journal.events


def test_session_cannot_understate_observed_clock_uncertainty() -> None:
    harness = make_harness()
    harness.clock.uncertainty_milliseconds = 2
    harness.runtime.start()
    understated = make_session(
        harness.signer,
        deployment_capability=harness.capability,
        domain_id=harness.clock.domain_id,
        clock_uncertainty_milliseconds=1,
    )

    with pytest.raises(PhysicalTransportRuntimeV4FaultLatched):
        harness.runtime.commit_session(
            understated,
            socket_owner=fake_socket_owner(understated, label="socket-1"),
            idempotency_key="understated-clock",
        )

    assert harness.runtime.state is PhysicalTransportRuntimeStateV4.FAULT_LATCHED
    assert "session" not in harness.journal.events


def test_socket_owner_boot_domain_mismatch_aborts_before_session_persistence() -> None:
    harness = make_harness()
    harness.runtime.start()
    session = make_session(
        harness.signer,
        deployment_capability=harness.capability,
        domain_id=harness.clock.domain_id,
    )
    owner = fake_socket_owner(session, label="wrong-boot")
    owner.current_snapshot = replace(
        owner.current_snapshot,
        kernel_boot_id="different-boot",
    )

    with pytest.raises(PhysicalTransportRuntimeV4FaultLatched, match="clock domain"):
        harness.runtime.commit_session(
            session,
            socket_owner=owner,
            idempotency_key="wrong-owner-boot",
        )

    assert owner.aborted
    assert "session" not in harness.journal.events
    assert harness.runtime.current_socket_lease_id is None


def test_socket_owner_binding_construction_failure_aborts_and_latches() -> None:
    harness = make_harness()
    harness.runtime.start()
    session = make_session(
        harness.signer,
        deployment_capability=harness.capability,
        domain_id=harness.clock.domain_id,
    )
    owner = fake_socket_owner(session, label="invalid-owner-randomness")
    harness.random.next_result = b"too-short"

    with pytest.raises(
        PhysicalTransportRuntimeV4FaultLatched, match="no send authority"
    ):
        harness.runtime.commit_session(
            session,
            socket_owner=owner,
            idempotency_key="invalid-owner-randomness",
        )

    assert owner.aborted
    assert "session" not in harness.journal.events
    assert harness.runtime.state is PhysicalTransportRuntimeStateV4.FAULT_LATCHED


def test_owner_change_before_atomic_append_aborts_without_durable_pair() -> None:
    harness = make_harness()
    harness.runtime.start()
    session = make_session(
        harness.signer,
        deployment_capability=harness.capability,
        domain_id=harness.clock.domain_id,
    )
    owner = fake_socket_owner(session, label="owner-change-before-append")
    owner.assertion_error = RuntimeError("owner changed")

    with pytest.raises(PhysicalTransportRuntimeV4FaultLatched):
        harness.runtime.commit_session(
            session,
            socket_owner=owner,
            idempotency_key="owner-change-before-append",
        )

    assert owner.aborted
    assert harness.journal.session is None
    assert harness.journal.socket_owner_binding is None


def test_owner_change_after_atomic_append_leaves_evidence_but_no_authority() -> None:
    harness = make_harness()
    harness.runtime.start()
    session = make_session(
        harness.signer,
        deployment_capability=harness.capability,
        domain_id=harness.clock.domain_id,
    )
    owner = fake_socket_owner(session, label="owner-change-after-append")
    owner.fail_on_assert_count = 2

    with pytest.raises(PhysicalTransportRuntimeV4FaultLatched):
        harness.runtime.commit_session(
            session,
            socket_owner=owner,
            idempotency_key="owner-change-after-append",
        )

    assert harness.journal.session == session
    assert harness.journal.socket_owner_binding is not None
    assert owner.aborted
    assert harness.runtime.current_transport_session_id is None
    assert harness.runtime.current_socket_lease_id is None
    assert harness.runtime._permit is None  # noqa: SLF001 - negative authority proof


@pytest.mark.parametrize("change_phase", ("before-intent", "during-intent"))
def test_owner_change_around_intent_commit_never_issues_permit(
    change_phase: str,
) -> None:
    harness = make_harness()
    harness.start_and_commit()
    owner = harness.socket_owners[-1]
    if change_phase == "before-intent":
        owner.assertion_error = RuntimeError("owner changed")
    else:
        harness.journal.authorization_hook = lambda: setattr(
            owner,
            "assertion_error",
            RuntimeError("owner changed during intent commit"),
        )

    with pytest.raises(PhysicalTransportRuntimeV4FaultLatched):
        harness.runtime.authorize_send_permit(idempotency_key=change_phase)

    assert owner.aborted
    assert harness.runtime._permit is None  # noqa: SLF001 - negative authority proof
    if change_phase == "before-intent":
        assert harness.journal.intent is None
    else:
        assert harness.journal.intent is not None


def test_no_permit_or_dispatch_exists_before_session_and_intent_commits() -> None:
    harness = make_harness()
    harness.runtime.start()

    with pytest.raises(PhysicalTransportRuntimeV4StateError):
        harness.runtime.authorize_send_permit(idempotency_key="too-early")
    with pytest.raises(PhysicalTransportRuntimeV4StateError):
        asyncio.run(
            harness.runtime.dispatch_text(  # type: ignore[arg-type]
                object(),
                socket_lease_id=digest("socket-1"),
                sender=object(),
            )
        )

    harness.start_and_commit()
    permit = harness.runtime.authorize_send_permit(idempotency_key="intent-1")
    assert isinstance(permit, PhysicalTransportSendPermitV4)
    session_position = harness.journal.events.index("session")
    authorization_position = harness.journal.events.index("authorize")
    final_fence_position = max(
        index
        for index, event in enumerate(harness.journal.events)
        if event == "assert-fence"
    )
    assert session_position < authorization_position < final_fence_position


def test_intent_is_committed_before_exact_bytes_reach_sender() -> None:
    harness = make_harness()
    _, socket_id = harness.start_and_commit()
    permit = harness.runtime.authorize_send_permit(idempotency_key="intent-1")
    observed: list[bytes] = []

    async def sender(payload: bytes) -> None:
        assert harness.journal.events[-1] == "assert-fence"
        assert (
            harness.journal.events.index("authorize") < len(harness.journal.events) - 1
        )
        assert harness.runtime.state is PhysicalTransportRuntimeStateV4.DISPATCHING
        observed.append(payload)

    window = asyncio.run(
        harness.runtime.dispatch_text(
            permit,
            socket_lease_id=socket_id,
            sender=owned_sender(harness, sender),
        )
    )

    assert observed == [permit.command_bytes]
    assert hashlib.sha256(observed[0]).hexdigest() == permit.command_sha256
    assert (
        window.outbound_subscription_intent_id == permit.outbound_subscription_intent_id
    )
    assert harness.runtime.state is PhysicalTransportRuntimeStateV4.AWAITING_ACK


def test_generic_send_bytes_adapter_is_never_invoked_as_text_frame_port() -> None:
    harness = make_harness()
    _, socket_id = harness.start_and_commit()
    permit = harness.runtime.authorize_send_permit(idempotency_key="intent-1")

    class GenericSender:
        def __init__(self) -> None:
            self.calls = 0

        async def send(self, _: bytes) -> None:
            self.calls += 1

    generic = GenericSender()
    with pytest.raises(PhysicalTransportDispatchUnknownV4):
        asyncio.run(
            harness.runtime.dispatch_text(
                permit,
                socket_lease_id=socket_id,
                sender=generic,  # type: ignore[arg-type]
            )
        )

    assert generic.calls == 0
    assert harness.runtime.state is PhysicalTransportRuntimeStateV4.FENCED
    assert harness.journal.terminations[-1].reason is (
        TransportSessionTerminationReasonV4.TRANSPORT_ERROR
    )


def test_forged_stale_and_reused_permits_never_reach_sender() -> None:
    harness = make_harness()
    _, socket_id = harness.start_and_commit()
    permit = harness.runtime.authorize_send_permit(idempotency_key="intent-1")
    forged = replace(permit, permit_id=digest("forged-permit"))
    sent: list[bytes] = []

    async def sender(payload: bytes) -> None:
        sent.append(payload)

    with pytest.raises(PhysicalTransportSendPermitV4Error):
        asyncio.run(
            harness.runtime.dispatch_text(
                forged,
                socket_lease_id=socket_id,
                sender=owned_sender(harness, sender),
            )
        )
    with pytest.raises(PhysicalTransportStaleCallbackV4):
        asyncio.run(
            harness.runtime.dispatch_text(
                permit,
                socket_lease_id=digest("stale-socket"),
                sender=owned_sender(harness, sender),
            )
        )
    assert harness.runtime.state is PhysicalTransportRuntimeStateV4.INTENT_COMMITTED

    asyncio.run(
        harness.runtime.dispatch_text(
            permit,
            socket_lease_id=socket_id,
            sender=owned_sender(harness, sender),
        )
    )
    with pytest.raises(PhysicalTransportRuntimeV4StateError):
        asyncio.run(
            harness.runtime.dispatch_text(
                permit,
                socket_lease_id=socket_id,
                sender=owned_sender(harness, sender),
            )
        )
    assert sent == [permit.command_bytes]


def test_superseded_application_fence_blocks_sender_and_consumes_permit() -> None:
    harness = make_harness()
    _, socket_id = harness.start_and_commit()
    permit = harness.runtime.authorize_send_permit(idempotency_key="intent-1")
    harness.journal.assert_fence_error = RuntimeError("writer epoch superseded")
    sent: list[bytes] = []

    async def sender(payload: bytes) -> None:
        sent.append(payload)

    with pytest.raises(PhysicalTransportRuntimeV4FaultLatched):
        asyncio.run(
            harness.runtime.dispatch_text(
                permit,
                socket_lease_id=socket_id,
                sender=owned_sender(harness, sender),
            )
        )

    assert sent == []
    assert harness.runtime.state is PhysicalTransportRuntimeStateV4.FAULT_LATCHED
    with pytest.raises(PhysicalTransportRuntimeV4StateError):
        asyncio.run(
            harness.runtime.dispatch_text(
                permit,
                socket_lease_id=socket_id,
                sender=owned_sender(harness, sender),
            )
        )
    assert sent == []


def test_expired_permit_never_calls_sender_and_durably_fences_session() -> None:
    harness = make_harness()
    _, socket_id = harness.start_and_commit()
    permit = harness.runtime.authorize_send_permit(idempotency_key="intent-1")
    harness.clock.advance(timedelta(seconds=11))
    sent: list[bytes] = []

    async def sender(payload: bytes) -> None:
        sent.append(payload)

    with pytest.raises(PhysicalTransportSendPermitV4Error, match="expired"):
        asyncio.run(
            harness.runtime.dispatch_text(
                permit,
                socket_lease_id=socket_id,
                sender=owned_sender(harness, sender),
            )
        )

    assert sent == []
    assert harness.runtime.state is PhysicalTransportRuntimeStateV4.FENCED
    assert harness.journal.terminations[-1].reason is (
        TransportSessionTerminationReasonV4.TRANSPORT_ERROR
    )


def test_send_exception_is_unknown_delivery_terminal_and_never_retryable() -> None:
    harness = make_harness()
    _, socket_id = harness.start_and_commit()
    permit = harness.runtime.authorize_send_permit(idempotency_key="intent-1")
    attempts = 0

    async def sender(_: bytes) -> None:
        nonlocal attempts
        attempts += 1
        raise OSError("write status is unknown")

    with pytest.raises(PhysicalTransportDispatchUnknownV4):
        asyncio.run(
            harness.runtime.dispatch_text(
                permit,
                socket_lease_id=socket_id,
                sender=owned_sender(harness, sender),
            )
        )
    with pytest.raises(PhysicalTransportRuntimeV4StateError):
        asyncio.run(
            harness.runtime.dispatch_text(
                permit,
                socket_lease_id=socket_id,
                sender=owned_sender(harness, sender),
            )
        )

    assert attempts == 1
    assert harness.runtime.state is PhysicalTransportRuntimeStateV4.FENCED
    assert harness.journal.terminations[-1].reason is (
        TransportSessionTerminationReasonV4.TRANSPORT_ERROR
    )


def test_dispatch_cancellation_is_terminal_before_cancellation_propagates() -> None:
    harness = make_harness()
    _, socket_id = harness.start_and_commit()
    permit = harness.runtime.authorize_send_permit(idempotency_key="intent-1")

    async def cancelled_sender(_: bytes) -> None:
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            harness.runtime.dispatch_text(
                permit,
                socket_lease_id=socket_id,
                sender=owned_sender(harness, cancelled_sender),
            )
        )

    assert harness.runtime.state is PhysicalTransportRuntimeStateV4.FENCED
    assert harness.journal.terminations[-1].reason is (
        TransportSessionTerminationReasonV4.TRANSPORT_ERROR
    )


def test_ack_callback_during_dispatch_is_buffered_then_bound_after_completion() -> None:
    harness = make_harness()
    _, socket_id = harness.start_and_commit()
    permit = harness.runtime.authorize_send_permit(idempotency_key="intent-1")
    disposition_id = digest("ack-disposition")

    async def sender(_: bytes) -> None:
        assert (
            harness.runtime.observe_captured_ack(
                message_disposition_id=disposition_id,
                socket_lease_id=socket_id,
            )
            is None
        )
        assert "bind" not in harness.journal.events

    asyncio.run(
        harness.runtime.dispatch_text(
            permit,
            socket_lease_id=socket_id,
            sender=owned_sender(harness, sender),
        )
    )

    assert harness.runtime.state is PhysicalTransportRuntimeStateV4.ACK_BOUND
    assert harness.journal.binding is not None
    assert harness.journal.binding.message_disposition_id == disposition_id
    assert harness.journal.events[-2:] == ["bind", "assert-fence"]


def test_stale_old_socket_ack_cannot_mutate_new_current_session() -> None:
    harness = make_harness()
    first_session, first_socket = harness.start_and_commit()
    first_permit = harness.runtime.authorize_send_permit(idempotency_key="intent-1")
    asyncio.run(
        harness.runtime.dispatch_text(
            first_permit,
            socket_lease_id=first_socket,
            sender=owned_sender(harness, successful_sender),
        )
    )
    harness.runtime.terminate_current(TransportSessionTerminationReasonV4.LOCAL_CLOSE)
    harness.runtime.prepare_reconnect()

    second_session, second_socket = harness.start_and_commit(
        generation=2,
        parent_transport_session_id=first_session.transport_session_id,
        socket_label="socket-2",
    )
    second_permit = harness.runtime.authorize_send_permit(idempotency_key="intent-2")
    asyncio.run(
        harness.runtime.dispatch_text(
            second_permit,
            socket_lease_id=second_socket,
            sender=owned_sender(harness, successful_sender),
        )
    )
    before = (
        harness.runtime.state,
        harness.runtime.current_transport_session_id,
        harness.runtime.current_intent_id,
    )

    with pytest.raises(PhysicalTransportStaleCallbackV4):
        harness.runtime.observe_captured_ack(
            message_disposition_id=digest("old-ack"),
            socket_lease_id=first_socket,
        )

    assert before == (
        PhysicalTransportRuntimeStateV4.AWAITING_ACK,
        second_session.transport_session_id,
        second_permit.outbound_subscription_intent_id,
    )
    assert (
        harness.runtime.state,
        harness.runtime.current_transport_session_id,
        harness.runtime.current_intent_id,
    ) == before


def test_ack_timeout_only_fences_after_committed_deadline() -> None:
    harness = make_harness()
    _, socket_id = harness.start_and_commit()
    permit = harness.runtime.authorize_send_permit(idempotency_key="intent-1")
    asyncio.run(
        harness.runtime.dispatch_text(
            permit,
            socket_lease_id=socket_id,
            sender=owned_sender(harness, successful_sender),
        )
    )

    assert harness.runtime.expire_ack_if_due() is False
    harness.clock.advance(timedelta(seconds=21))
    assert harness.runtime.expire_ack_if_due() is True
    assert harness.runtime.state is PhysicalTransportRuntimeStateV4.FENCED
    assert harness.journal.terminations[-1].reason is (
        TransportSessionTerminationReasonV4.ACK_TIMEOUT
    )


def test_backpressure_during_dispatch_cannot_revive_state() -> None:
    harness = make_harness()
    _, socket_id = harness.start_and_commit()
    permit = harness.runtime.authorize_send_permit(idempotency_key="intent-1")

    async def sender(_: bytes) -> None:
        termination = harness.runtime.fence_backpressure(socket_lease_id=socket_id)
        assert termination.reason is TransportSessionTerminationReasonV4.BACKPRESSURE
        assert harness.runtime.state is PhysicalTransportRuntimeStateV4.FENCED

    with pytest.raises(PhysicalTransportDispatchUnknownV4):
        asyncio.run(
            harness.runtime.dispatch_text(
                permit,
                socket_lease_id=socket_id,
                sender=owned_sender(harness, sender),
            )
        )

    assert harness.runtime.state is PhysicalTransportRuntimeStateV4.FENCED
    assert harness.journal.terminations[-1].reason is (
        TransportSessionTerminationReasonV4.BACKPRESSURE
    )


@pytest.mark.parametrize(
    "mutation",
    ("unsynchronized", "uncertain", "domain-change"),
)
def test_active_clock_discipline_failure_latches_without_issuing_permit(
    mutation: str,
) -> None:
    harness = make_harness()
    harness.start_and_commit()
    if mutation == "unsynchronized":
        harness.clock.synchronized = False
    elif mutation == "uncertain":
        harness.clock.uncertainty_milliseconds = 251
    else:
        harness.clock.domain_id = digest("different-monotonic-domain")

    with pytest.raises(PhysicalTransportRuntimeV4FaultLatched):
        harness.runtime.authorize_send_permit(idempotency_key="intent-1")

    assert harness.runtime.state is PhysicalTransportRuntimeStateV4.FAULT_LATCHED
    assert "authorize" not in harness.journal.events


@pytest.mark.parametrize(
    ("bind_error", "expected_reason"),
    (
        (
            PhysicalProjectionV4ConflictError("conflicting ACK"),
            TransportSessionTerminationReasonV4.TRANSPORT_ERROR,
        ),
        (
            OSError("journal unavailable"),
            TransportSessionTerminationReasonV4.STORAGE_FAILURE,
        ),
    ),
)
def test_ack_bind_conflict_or_storage_failure_durably_fences(
    bind_error: BaseException,
    expected_reason: TransportSessionTerminationReasonV4,
) -> None:
    harness = make_harness()
    _, socket_id = harness.start_and_commit()
    permit = harness.runtime.authorize_send_permit(idempotency_key="intent-1")
    asyncio.run(
        harness.runtime.dispatch_text(
            permit,
            socket_lease_id=socket_id,
            sender=owned_sender(harness, successful_sender),
        )
    )
    harness.journal.bind_error = bind_error

    with pytest.raises(PhysicalTransportAckBindingV4Error):
        harness.runtime.observe_captured_ack(
            message_disposition_id=digest("ack-disposition"),
            socket_lease_id=socket_id,
        )

    assert harness.runtime.state is PhysicalTransportRuntimeStateV4.FENCED
    assert harness.journal.terminations[-1].reason is expected_reason


def test_ack_bind_and_terminal_storage_failure_fault_latches() -> None:
    harness = make_harness()
    _, socket_id = harness.start_and_commit()
    permit = harness.runtime.authorize_send_permit(idempotency_key="intent-1")
    asyncio.run(
        harness.runtime.dispatch_text(
            permit,
            socket_lease_id=socket_id,
            sender=owned_sender(harness, successful_sender),
        )
    )
    harness.journal.bind_error = OSError("binding journal unavailable")
    harness.journal.termination_error = OSError("termination journal unavailable")

    with pytest.raises(PhysicalTransportRuntimeV4FaultLatched):
        harness.runtime.observe_captured_ack(
            message_disposition_id=digest("ack-disposition"),
            socket_lease_id=socket_id,
        )

    assert harness.runtime.state is PhysicalTransportRuntimeStateV4.FAULT_LATCHED


def test_failed_intent_commit_never_issues_permit_and_fences_storage_failure() -> None:
    harness = make_harness()
    harness.start_and_commit()
    harness.journal.authorization_error = OSError("intent commit failed")

    with pytest.raises(PhysicalTransportRuntimeV4Error):
        harness.runtime.authorize_send_permit(idempotency_key="intent-1")

    assert harness.runtime.current_intent_id is None
    assert harness.runtime.state is PhysicalTransportRuntimeStateV4.FENCED
    assert harness.journal.terminations[-1].reason is (
        TransportSessionTerminationReasonV4.STORAGE_FAILURE
    )


@pytest.mark.parametrize("failure_mode", ("wrong-intent", "bad-randomness"))
def test_failure_after_durable_intent_never_reauthorizes_or_issues_permit(
    failure_mode: str,
) -> None:
    harness = make_harness()
    harness.start_and_commit()
    if failure_mode == "wrong-intent":
        harness.journal.return_wrong_intent_session = True
    else:
        harness.random.next_result = b"too-short"

    with pytest.raises(
        PhysicalTransportRuntimeV4Error,
        match="durable intent couldn't produce a permit",
    ):
        harness.runtime.authorize_send_permit(idempotency_key="intent-1")

    assert harness.journal.authorization_count == 1
    assert harness.runtime.current_intent_id is not None
    assert harness.runtime.state is PhysicalTransportRuntimeStateV4.FENCED
    assert harness.journal.terminations[-1].reason is (
        TransportSessionTerminationReasonV4.TRANSPORT_ERROR
    )
    with pytest.raises(PhysicalTransportRuntimeV4StateError):
        harness.runtime.authorize_send_permit(idempotency_key="intent-2")
    assert harness.journal.authorization_count == 1


def test_reconnect_uses_new_permit_and_rejects_every_old_capability() -> None:
    harness = make_harness()
    first_session, first_socket = harness.start_and_commit()
    first_permit = harness.runtime.authorize_send_permit(idempotency_key="intent-1")
    harness.runtime.terminate_current(TransportSessionTerminationReasonV4.SUPERSEDED)
    harness.runtime.prepare_reconnect()

    _, second_socket = harness.start_and_commit(
        generation=2,
        parent_transport_session_id=first_session.transport_session_id,
        socket_label="socket-2",
    )
    second_permit = harness.runtime.authorize_send_permit(idempotency_key="intent-2")
    sent: list[bytes] = []

    async def sender(payload: bytes) -> None:
        sent.append(payload)

    assert second_permit.permit_id != first_permit.permit_id
    assert second_permit.outbound_subscription_intent_id != (
        first_permit.outbound_subscription_intent_id
    )
    with pytest.raises(PhysicalTransportSendPermitV4Error):
        asyncio.run(
            harness.runtime.dispatch_text(
                first_permit,
                socket_lease_id=second_socket,
                sender=owned_sender(harness, sender),
            )
        )
    with pytest.raises(PhysicalTransportStaleCallbackV4):
        asyncio.run(
            harness.runtime.dispatch_text(
                first_permit,
                socket_lease_id=first_socket,
                sender=owned_sender(harness, sender),
            )
        )

    asyncio.run(
        harness.runtime.dispatch_text(
            second_permit,
            socket_lease_id=second_socket,
            sender=owned_sender(harness, sender),
        )
    )
    assert sent == [second_permit.command_bytes]


def test_kernel_socket_identity_cannot_be_reused_after_reconnect() -> None:
    harness = make_harness()
    first_session, _ = harness.start_and_commit()
    first_owner = harness.socket_owners[-1]
    harness.runtime.terminate_current(TransportSessionTerminationReasonV4.LOCAL_CLOSE)
    harness.runtime.prepare_reconnect()
    before_session_appends = harness.journal.events.count("session")
    successor = make_session(
        harness.signer,
        deployment_capability=harness.capability,
        generation=2,
        parent_transport_session_id=first_session.transport_session_id,
        domain_id=harness.clock.domain_id,
    )
    reused_kernel_socket = FakeSocketOwner(
        current_snapshot=first_owner.current_snapshot
    )

    with pytest.raises(PhysicalTransportRuntimeV4StateError, match="already consumed"):
        harness.runtime.commit_session(
            successor,
            socket_owner=reused_kernel_socket,
            idempotency_key="reused-socket-lease",
        )

    assert harness.runtime.state is PhysicalTransportRuntimeStateV4.READY
    assert reused_kernel_socket.aborted
    assert harness.journal.events.count("session") == before_session_appends


def test_slow_application_fence_check_cannot_backdate_dispatch() -> None:
    harness = make_harness()
    _, socket_id = harness.start_and_commit()
    permit = harness.runtime.authorize_send_permit(idempotency_key="intent-1")
    harness.journal.assert_fence_advance = timedelta(seconds=11)
    sent: list[bytes] = []

    async def sender(payload: bytes) -> None:
        sent.append(payload)

    with pytest.raises(PhysicalTransportSendPermitV4Error, match="expired"):
        asyncio.run(
            harness.runtime.dispatch_text(
                permit,
                socket_lease_id=socket_id,
                sender=owned_sender(harness, sender),
            )
        )

    assert sent == []
    assert harness.runtime.state is PhysicalTransportRuntimeStateV4.FENCED


def test_slow_intent_commit_expires_before_permit_issuance() -> None:
    harness = make_harness()
    harness.start_and_commit()
    harness.journal.authorization_advance = timedelta(seconds=11)

    with pytest.raises(PhysicalTransportRuntimeV4Error, match="couldn't produce"):
        harness.runtime.authorize_send_permit(idempotency_key="slow-intent")

    assert harness.journal.authorization_count == 1
    assert harness.runtime.state is PhysicalTransportRuntimeStateV4.FENCED
    assert harness.journal.terminations[-1].reason is (
        TransportSessionTerminationReasonV4.TRANSPORT_ERROR
    )


def test_failed_slow_intent_commit_uses_fresh_detection_clock() -> None:
    harness = make_harness()
    harness.start_and_commit()
    harness.journal.authorization_advance = timedelta(seconds=5)
    harness.journal.authorization_error = OSError("commit outcome failed")
    before = harness.clock.now

    with pytest.raises(PhysicalTransportRuntimeV4Error, match="intent commit failed"):
        harness.runtime.authorize_send_permit(idempotency_key="failed-intent")

    assert harness.journal.terminations[-1].detected_at >= before + timedelta(seconds=5)
    assert harness.journal.terminations[-1].reason is (
        TransportSessionTerminationReasonV4.STORAGE_FAILURE
    )


def test_permit_clock_is_sampled_after_durable_intent_commit() -> None:
    harness = make_harness()
    harness.start_and_commit()

    permit = harness.runtime.authorize_send_permit(idempotency_key="intent-1")

    assert harness.journal.intent is not None
    assert permit.issued_at > harness.journal.intent.authorized_at
    assert permit.issued_monotonic_ns == harness.clock.samples[-1].monotonic_ns


def test_clock_source_manifest_cannot_change_within_runtime_epoch() -> None:
    harness = make_harness()
    harness.start_and_commit()
    harness.clock.source_id = digest("replacement-clock-source")

    with pytest.raises(PhysicalTransportRuntimeV4FaultLatched, match="clock"):
        harness.runtime.authorize_send_permit(idempotency_key="intent-1")

    assert harness.runtime.state is PhysicalTransportRuntimeStateV4.FAULT_LATCHED
    assert "authorize" not in harness.journal.events


def test_live_runtime_accepts_one_stable_loaded_chronyd_pair() -> None:
    harness = make_harness()
    launch_id = digest("v48b-runtime-launch")
    runtime_observation = digest("v48b-runtime-observation")
    harness.clock.chronyd_launch_id = launch_id
    harness.clock.chronyd_runtime_observation_sha256 = runtime_observation
    harness.runtime._is_live_profile = True  # noqa: SLF001

    first = harness.runtime._sample_clock()  # noqa: SLF001
    second = harness.runtime._sample_clock()  # noqa: SLF001

    assert first.chronyd_launch_id == launch_id
    assert second.chronyd_launch_id == launch_id
    assert second.chronyd_runtime_observation_sha256 == runtime_observation


def test_live_runtime_rejects_missing_loaded_chronyd_pair() -> None:
    harness = make_harness()
    harness.runtime._is_live_profile = True  # noqa: SLF001

    with pytest.raises(
        PhysicalTransportClockEvidenceV4Error,
        match="lacks loaded-chronyd provenance",
    ):
        harness.runtime._sample_clock()  # noqa: SLF001

    assert harness.runtime._last_clock_evidence is None  # noqa: SLF001


def test_live_runtime_rejects_loaded_chronyd_pair_change_within_epoch() -> None:
    harness = make_harness()
    harness.clock.chronyd_launch_id = digest("v48b-runtime-launch")
    harness.clock.chronyd_runtime_observation_sha256 = digest(
        "v48b-runtime-observation"
    )
    harness.runtime._is_live_profile = True  # noqa: SLF001
    accepted = harness.runtime._sample_clock()  # noqa: SLF001
    harness.clock.chronyd_launch_id = digest("v48b-replacement-launch")
    harness.clock.chronyd_runtime_observation_sha256 = digest(
        "v48b-replacement-runtime-observation"
    )

    with pytest.raises(
        PhysicalTransportClockEvidenceV4Error,
        match="loaded chronyd authority changed",
    ):
        harness.runtime._sample_clock()  # noqa: SLF001

    assert harness.runtime._last_clock_evidence is accepted  # noqa: SLF001


@pytest.mark.parametrize("failure", ("type", "scope"))
def test_faulty_journal_session_or_intent_return_never_grants_authority(
    failure: str,
) -> None:
    harness = make_harness()
    if failure == "type":
        harness.journal.return_wrong_session_record = True
        harness.runtime.start()
        session = make_session(
            harness.signer,
            deployment_capability=harness.capability,
            domain_id=harness.clock.domain_id,
        )
        with pytest.raises(PhysicalTransportRuntimeV4FaultLatched):
            harness.runtime.commit_session(
                session,
                socket_owner=fake_socket_owner(session, label="socket-1"),
                idempotency_key="wrong-session-return",
            )
        assert harness.runtime.state is PhysicalTransportRuntimeStateV4.FAULT_LATCHED
        return

    harness.start_and_commit()
    harness.journal.return_wrong_intent_scope = True
    with pytest.raises(PhysicalTransportRuntimeV4Error, match="couldn't produce"):
        harness.runtime.authorize_send_permit(idempotency_key="wrong-intent-return")
    assert harness.runtime.state is PhysicalTransportRuntimeStateV4.FENCED


def test_faulty_journal_ack_binding_return_is_never_accepted() -> None:
    harness = make_harness()
    _, socket_id = harness.start_and_commit()
    permit = harness.runtime.authorize_send_permit(idempotency_key="intent-1")
    asyncio.run(
        harness.runtime.dispatch_text(
            permit,
            socket_lease_id=socket_id,
            sender=owned_sender(harness, successful_sender),
        )
    )
    harness.journal.return_wrong_binding_disposition = True

    with pytest.raises(PhysicalTransportAckBindingV4Error):
        harness.runtime.observe_captured_ack(
            message_disposition_id=digest("expected-disposition"),
            socket_lease_id=socket_id,
        )

    assert harness.runtime.state is PhysicalTransportRuntimeStateV4.FENCED
    assert harness.journal.terminations[-1].reason is (
        TransportSessionTerminationReasonV4.STORAGE_FAILURE
    )


def test_faulty_journal_termination_return_fault_latches() -> None:
    harness = make_harness()
    harness.start_and_commit()
    harness.journal.return_wrong_termination_reason = True

    with pytest.raises(PhysicalTransportRuntimeV4FaultLatched):
        harness.runtime.terminate_current(
            TransportSessionTerminationReasonV4.LOCAL_CLOSE
        )

    assert harness.runtime.state is PhysicalTransportRuntimeStateV4.FAULT_LATCHED


@pytest.mark.parametrize("lost_authority", ("os-lease", "application-fence"))
def test_pending_ack_cannot_bind_after_authority_is_lost_during_send(
    lost_authority: str,
) -> None:
    harness = make_harness()
    _, socket_id = harness.start_and_commit()
    permit = harness.runtime.authorize_send_permit(idempotency_key="intent-1")
    disposition_id = digest("early-ack")

    async def sender(_: bytes) -> None:
        assert (
            harness.runtime.observe_captured_ack(
                message_disposition_id=disposition_id,
                socket_lease_id=socket_id,
            )
            is None
        )
        if lost_authority == "os-lease":
            harness.lease.held = False
        else:
            harness.journal.assert_fence_error = RuntimeError("epoch superseded")

    with pytest.raises(PhysicalTransportRuntimeV4FaultLatched):
        asyncio.run(
            harness.runtime.dispatch_text(
                permit,
                socket_lease_id=socket_id,
                sender=owned_sender(harness, sender),
            )
        )

    assert harness.runtime.state is PhysicalTransportRuntimeStateV4.FAULT_LATCHED
    assert "bind" not in harness.journal.events


def test_stale_backpressure_callback_cannot_fence_new_socket() -> None:
    harness = make_harness()
    first_session, first_socket = harness.start_and_commit()
    harness.runtime.terminate_current(TransportSessionTerminationReasonV4.LOCAL_CLOSE)
    harness.runtime.prepare_reconnect()
    second_session, _ = harness.start_and_commit(
        generation=2,
        parent_transport_session_id=first_session.transport_session_id,
        socket_label="socket-2",
    )

    with pytest.raises(PhysicalTransportStaleCallbackV4):
        harness.runtime.fence_backpressure(socket_lease_id=first_socket)

    assert harness.runtime.state is PhysicalTransportRuntimeStateV4.SESSION_COMMITTED
    assert harness.runtime.current_transport_session_id == (
        second_session.transport_session_id
    )

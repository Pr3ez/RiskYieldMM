from __future__ import annotations

import asyncio
import copy
import inspect
import platform
import ssl
import sys
import sysconfig
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from websockets.frames import Frame, Opcode

from riskyieldmm.trading.canonical import sha256_digest
from riskyieldmm.trading.ledger_signing import Ed25519CheckpointSigner
from riskyieldmm.trading.operational_manifests_v4 import (
    COLLECTOR_KEY_USAGE,
    DEPENDENCY_LOCK_FORMAT,
    CollectorKeyAuthorizationManifestV4,
    CollectorReleaseManifestV4,
    DependencyLockManifestV4,
    DeploymentAuthorityCeilingV4,
    DeploymentBundleV4,
    DeploymentRoleKeyV4,
    DeploymentTrustRootV4,
    RuntimeEnvironmentManifestV4,
    TlsWebSocketDriverPolicyV49B,
    approve_deployment_bundle_v4,
    derive_deployment_signing_key_id,
)
from riskyieldmm.trading.operational_runtime_artifacts_v49b import (
    PinnedTlsWebSocketRuntimeArtifactsV49B,
    capture_current_tls_websocket_driver_policy_v49b,
)
from riskyieldmm.trading.physical_projection_v4 import (
    PhysicalProjectionStoreV4,
    _capture_partition_id_v3,
)
from riskyieldmm.trading.physical_transport_capacity_v49f import (
    TransportCapacityPolicyV49F,
)
from riskyieldmm.trading.physical_transport_linux_v4 import (
    DeterministicLinuxChronyClockV4,
    DriverHandshakeTransitionV49B,
    LinuxSocketOwnerV4,
    LinuxSocketOwnerV4Error,
    build_linux_physical_transport_runtime_v4,
)
from riskyieldmm.trading.physical_transport_runtime_v4 import (
    OperationalDeploymentAdmissionV4,
    PhysicalTransportRuntimeStateV4,
    PhysicalTransportRuntimeV4,
    PhysicalTransportRuntimeV4FaultLatched,
    PhysicalTransportRuntimeV4StateError,
)
from riskyieldmm.trading.physical_transport_tls_v49 import (
    ExactTlsWebSocketDriverV49,
    TlsWebSocketDriverStateV49,
)
from riskyieldmm.trading.physical_transport_v4 import (
    TransportSessionAttestationV4,
    derive_transport_attestation_key_id,
)
from tests.test_trading_physical_authority_v4_projection import authority_scope
from tests.test_trading_physical_market_data_v3 import bar_policy, status_policy
from tests.test_trading_physical_transport_runtime_integration_v4 import private_lease
from tests.test_trading_physical_transport_tls_v49 import (
    _certificates,
    _connected_socket,
    _server_context,
    _start_fake_server,
    _trust_store,
    _write_certificates,
)
from tests.test_trading_physical_transport_v4_projection import transport_policy
from tests.test_trading_physical_transport_v47b_sealing_adversarial import (
    DeterministicRunner,
    RecordingDriver,
    clock_policy_and_sources,
    connected_tcp_pair,
)

pytestmark = pytest.mark.skipif(
    sys.platform != "linux", reason="Linux-only exact V4.9B authority tests"
)

T0 = datetime(2026, 7, 15, 12, tzinfo=timezone.utc)


def _digest(label: str) -> str:
    return sha256_digest({"label": label})


def _deterministic_clock(tmp_path: Path) -> DeterministicLinuxChronyClockV4:
    tmp_path.mkdir(mode=0o700)
    policy, sources = clock_policy_and_sources(tmp_path)
    cursor = -1

    def wall_clock() -> datetime:
        nonlocal cursor
        cursor += 1
        return T0 + timedelta(milliseconds=cursor)

    return DeterministicLinuxChronyClockV4(
        policy=policy,
        configured_source_artifacts=sources,
        command_runner=DeterministicRunner(),
        wall_clock=wall_clock,
    )


def _runtime_environment(
    *,
    driver_policy: TlsWebSocketDriverPolicyV49B,
    dependency_lock_manifest_id: str,
    collector_release_manifest_id: str,
    tls_trust_store_manifest_id: str,
    clock_source_policy_manifest_id: str,
    include_driver_policy: bool = True,
    transport_capacity_policy_v49f: TransportCapacityPolicyV49F | None = None,
) -> RuntimeEnvironmentManifestV4:
    python_executable = next(
        member
        for member in driver_policy.runtime_artifacts
        if member.role == "PYTHON_EXECUTABLE"
    )
    return RuntimeEnvironmentManifestV4(
        python_implementation=driver_policy.python_implementation,
        python_version=driver_policy.python_version,
        python_executable_sha256=python_executable.sha256,
        platform_tag=sysconfig.get_platform(),
        openssl_version=driver_policy.openssl_version,
        installed_distribution_root_sha256=(
            driver_policy.installed_distribution_root_sha256
        ),
        dependency_lock_manifest_id=dependency_lock_manifest_id,
        collector_release_manifest_id=collector_release_manifest_id,
        tls_trust_store_manifest_id=tls_trust_store_manifest_id,
        clock_source_policy_manifest_id=clock_source_policy_manifest_id,
        isolated_mode=True,
        user_site_enabled=False,
        tls_websocket_driver_policy=(driver_policy if include_driver_policy else None),
        transport_capacity_policy_v49f=transport_capacity_policy_v49f,
    )


@dataclass(frozen=True, slots=True)
class _AdmissionMaterials:
    admission: OperationalDeploymentAdmissionV4
    measured_runtime_environment: RuntimeEnvironmentManifestV4


def _deployment_admission(
    *,
    collector_signer: Ed25519CheckpointSigner,
    clock_policy: Any,
    trust_store_manifest: Any,
    driver_policy: TlsWebSocketDriverPolicyV49B,
    include_signed_driver_policy: bool,
    measured_runtime_mismatch: bool,
    transport_capacity_policy_v49f: TransportCapacityPolicyV49F | None = None,
    release_source_tree_sha256: str | None = None,
) -> _AdmissionMaterials:
    release = CollectorReleaseManifestV4(
        release_name="riskyieldmm-collector",
        release_version="0.1.0-v49b-runtime-test",
        source_tree_sha256=(
            _digest("v49b-source-tree")
            if release_source_tree_sha256 is None
            else release_source_tree_sha256
        ),
        build_artifact_sha256=_digest("v49b-collector-wheel"),
        entrypoint="riskyieldmm.transport.collector",
        parser_policy_root_sha256=_digest("v49b-parser-policy-root"),
    )
    lock = DependencyLockManifestV4(
        lock_format=DEPENDENCY_LOCK_FORMAT,
        lock_file_sha256=_digest("v49b-requirements-lock"),
        wheelhouse_root_sha256=_digest("v49b-wheelhouse-root"),
        distribution_count=max(1, len(driver_policy.installed_distributions)),
        require_hashes=True,
        only_binary=True,
        fully_pinned=True,
    )
    signed_runtime = _runtime_environment(
        driver_policy=driver_policy,
        dependency_lock_manifest_id=lock.manifest_id,
        collector_release_manifest_id=release.manifest_id,
        tls_trust_store_manifest_id=trust_store_manifest.manifest_id,
        clock_source_policy_manifest_id=clock_policy.manifest_id,
        include_driver_policy=include_signed_driver_policy,
        transport_capacity_policy_v49f=transport_capacity_policy_v49f,
    )
    measured_runtime = (
        _runtime_environment(
            driver_policy=driver_policy,
            dependency_lock_manifest_id=_digest("foreign-measured-lock"),
            collector_release_manifest_id=_digest("foreign-measured-release"),
            tls_trust_store_manifest_id=trust_store_manifest.manifest_id,
            clock_source_policy_manifest_id=clock_policy.manifest_id,
            transport_capacity_policy_v49f=transport_capacity_policy_v49f,
        )
        if measured_runtime_mismatch
        else _runtime_environment(
            driver_policy=driver_policy,
            dependency_lock_manifest_id=lock.manifest_id,
            collector_release_manifest_id=release.manifest_id,
            tls_trust_store_manifest_id=trust_store_manifest.manifest_id,
            clock_source_policy_manifest_id=clock_policy.manifest_id,
            transport_capacity_policy_v49f=transport_capacity_policy_v49f,
        )
    )
    key_authorization = CollectorKeyAuthorizationManifestV4(
        collector_attestation_key_id=derive_transport_attestation_key_id(
            collector_signer.public_key_bytes
        ),
        collector_attestation_public_key_hex=(collector_signer.public_key_bytes.hex()),
        usage=COLLECTOR_KEY_USAGE,
        collector_release_manifest_id=release.manifest_id,
        valid_from=T0 - timedelta(days=7),
        valid_until=T0 + timedelta(days=1),
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
        valid_from=T0 - timedelta(days=7),
        valid_until=T0 + timedelta(days=1),
        environment_id="MAINNET",
        authority_ceiling=(
            DeploymentAuthorityCeilingV4.PUBLIC_MARKET_DATA_CAPTURE_ONLY
        ),
        collector_release_manifest_id=release.manifest_id,
        dependency_lock_manifest_id=lock.manifest_id,
        tls_trust_store_manifest_id=trust_store_manifest.manifest_id,
        clock_source_policy_manifest_id=clock_policy.manifest_id,
        runtime_environment_manifest_id=signed_runtime.manifest_id,
        collector_key_authorization_manifest_id=key_authorization.manifest_id,
    )
    approval = approve_deployment_bundle_v4(bundle, signers=(deployment_signer,))
    admission = OperationalDeploymentAdmissionV4(
        trust_root=trust_root,
        expected_trust_root_id=trust_root.trust_root_id,
        approval=approval,
        children=(
            release,
            lock,
            trust_store_manifest,
            clock_policy,
            signed_runtime,
            key_authorization,
        ),
    )
    assert measured_runtime.python_implementation == platform.python_implementation()
    assert measured_runtime.openssl_version == ssl.OPENSSL_VERSION
    return _AdmissionMaterials(admission, measured_runtime)


def _append_deployment(
    store: PhysicalProjectionStoreV4,
    admission: OperationalDeploymentAdmissionV4,
) -> Any:
    store.append_deployment_trust_root(
        admission.trust_root,
        idempotency_key="v49b-deployment-root",
    )
    for index, child in enumerate(admission.children):
        store.append_operational_child_manifest(
            child,
            idempotency_key=f"v49b-deployment-child-{index}",
        )
    return store.append_deployment_bundle_approval(
        admission.approval,
        verified_at=T0,
        idempotency_key="v49b-deployment-approval",
    )


@dataclass(slots=True)
class _Harness:
    store: PhysicalProjectionStoreV4
    runtime: PhysicalTransportRuntimeV4
    owner: LinuxSocketOwnerV4
    driver: ExactTlsWebSocketDriverV49
    server: Any
    scope: Any
    primary: Any
    capture_partition_id: str

    async def close(self) -> None:
        try:
            self.runtime.close()
        except BaseException:
            # Adversarial cases deliberately invalidate the retained owner.
            pass
        self.owner.abort()
        await self.server.close()
        self.store.close()


async def _build_harness(
    tmp_path: Path,
    *,
    fault_injector: Callable[[str], None] | None = None,
    include_signed_driver_policy: bool = True,
    measured_runtime_mismatch: bool = False,
    stall_response: bool = False,
    first_frame: bytes = b"",
    exact_candidate: bool = True,
    transport_capacity_policy_v49f: TransportCapacityPolicyV49F | None = None,
    release_source_tree_sha256: str | None = None,
) -> _Harness:
    tmp_path.mkdir(mode=0o700, exist_ok=True)
    certificates = _certificates()
    ca_path, cert_path, key_path = _write_certificates(tmp_path, certificates)
    trust_store = _trust_store(ca_path, certificates)
    clock = _deterministic_clock(tmp_path / "clock")
    driver_policy = capture_current_tls_websocket_driver_policy_v49b()
    materials = _deployment_admission(
        collector_signer=(collector_signer := Ed25519CheckpointSigner.generate()),
        clock_policy=clock.policy,
        trust_store_manifest=trust_store.manifest,
        driver_policy=driver_policy,
        include_signed_driver_policy=include_signed_driver_policy,
        measured_runtime_mismatch=measured_runtime_mismatch,
        transport_capacity_policy_v49f=transport_capacity_policy_v49f,
        release_source_tree_sha256=release_source_tree_sha256,
    )
    runtime_artifacts = PinnedTlsWebSocketRuntimeArtifactsV49B._open_verified_for_test(
        policy=driver_policy,
        runtime_environment=materials.measured_runtime_environment,
    )
    store = PhysicalProjectionStoreV4(
        tmp_path / "v49b-runtime.sqlite3",
        clock=lambda: T0 + timedelta(seconds=1),
        fault_injector=fault_injector,
    )
    server = await _start_fake_server(
        _server_context(cert_path, key_path),
        first_frame=first_frame,
        stall_response=stall_response,
    )
    owner: LinuxSocketOwnerV4 | None = None
    runtime: PhysicalTransportRuntimeV4 | None = None
    driver: ExactTlsWebSocketDriverV49 | None = None
    try:
        capability = _append_deployment(store, materials.admission)
        primary = bar_policy(requires_status=True)
        required_status = status_policy()
        scope = authority_scope(primary, required_status)
        policy = transport_policy(
            signer=collector_signer,
            frozen_at=scope.frozen_at,
            deployment_capability=capability,
        )
        store.append_health_policy(idempotency_key="v49b-health")
        store.append_adapter_policy(primary, idempotency_key="v49b-primary")
        store.append_adapter_policy(required_status, idempotency_key="v49b-status")
        store.append_scope(scope, idempotency_key="v49b-scope")
        store.append_transport_subscription_policy(
            policy,
            idempotency_key="v49b-transport-policy",
        )
        driver = ExactTlsWebSocketDriverV49.from_measured_authority(
            trust_store=trust_store,
            transport_policy=policy,
            runtime_artifacts=runtime_artifacts,
        )
        owned_socket = await _connected_socket(server.address)
        owner = (
            LinuxSocketOwnerV4._from_v49b_exact_profile_for_test(  # noqa: SLF001
                owned_socket=owned_socket,
                governed_clock=clock,
                driver=driver,
            )
            if exact_candidate
            else LinuxSocketOwnerV4(
                owned_socket=owned_socket,
                governed_clock=clock,
                driver=driver,
            )
        )
        lease = private_lease(tmp_path, holder_id="v49b-runtime")
        capture_partition_id = _capture_partition_id_v3(
            adapter_policy_id=primary.adapter_policy_id,
            collector_boot_id=owner.snapshot().kernel_boot_id,
            collector_instance_id="v49b-collector-instance",
            provider_native_key=primary.provider_native_key,
        )
        runtime = PhysicalTransportRuntimeV4.for_test(
            journal=store,
            writer_lease=lease,
            clock_source=owner,
            signer=collector_signer,
            deployment_admission=materials.admission,
            idempotency_prefix="v49b-runtime",
            wall_clock=lambda: T0 + timedelta(seconds=1),
            random_bytes=lambda length: bytes([0x49]) * length,
        )
        runtime.start()
        return _Harness(
            store,
            runtime,
            owner,
            driver,
            server,
            scope,
            primary,
            capture_partition_id,
        )
    except BaseException:
        if runtime is not None:
            try:
                runtime.close()
            except BaseException:
                pass
        if owner is not None:
            owner.abort()
        elif driver is not None:
            driver.abort()
            clock.close()
        else:
            trust_store.close()
            runtime_artifacts.close()
            clock.close()
        await server.close()
        store.close()
        raise


async def _establish(harness: _Harness, *, key: str = "v49b-session") -> Any:
    collector_instance_id = "v49b-collector-instance"
    return await harness.runtime.establish_driver_derived_session_v49b(
        physical_scope_manifest_id=harness.scope.physical_scope_manifest_id,
        adapter_policy_id=harness.primary.adapter_policy_id,
        capture_partition_id=harness.capture_partition_id,
        collector_instance_id=collector_instance_id,
        idempotency_key=key,
    )


def _typed_count(store: PhysicalProjectionStoreV4, table: str) -> int:
    row = store._connection.execute(  # noqa: SLF001
        f"SELECT count(*) FROM {table}"
    ).fetchone()
    assert row is not None
    return int(row[0])


def test_driver_derived_api_has_no_caller_authored_evidence_seams() -> None:
    signature = inspect.signature(
        PhysicalTransportRuntimeV4.establish_driver_derived_session_v49b
    )
    assert tuple(signature.parameters) == (
        "self",
        "physical_scope_manifest_id",
        "adapter_policy_id",
        "capture_partition_id",
        "collector_instance_id",
        "idempotency_key",
    )
    forbidden = {
        "session",
        "socket_owner",
        "owned_socket",
        "handshake_evidence",
        "transition",
        "wall_clock",
        "monotonic_ns",
        "random_bytes",
        "connection_generation",
        "parent_transport_session_id",
    }
    assert forbidden.isdisjoint(signature.parameters)

    transition_signature = inspect.signature(DriverHandshakeTransitionV49B)
    assert "_token" in transition_signature.parameters
    with pytest.raises(TypeError, match="owner-constructed only"):
        DriverHandshakeTransitionV49B(
            _token=object(),
            evidence=object(),
            pre_sample=object(),
            post_sample=object(),
            owner_snapshot=object(),
            owner_snapshot_after=object(),
            handshake_started_monotonic_ns=1,
            handshake_completed_monotonic_ns=2,
            driver_policy_id=_digest("policy"),
            runtime_observation_sha256=_digest("observation"),
        )


def test_exact_driver_owner_runtime_commit_preserves_causal_mapping_and_io_fence(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        observations: list[str] = []
        holder: dict[str, _Harness] = {}

        def inspect_precommit(stage: str) -> None:
            if stage != "after_transport_session_attestation_insert":
                return
            harness = holder["harness"]
            assert harness.server.application_reads.empty()
            with pytest.raises(LinuxSocketOwnerV4Error, match="before committed"):
                harness.owner._assert_v49b_io_bound()  # noqa: SLF001
            observations.append(stage)

        ping = Frame(Opcode.PING, b"v49b-ping").serialize(mask=False)
        harness = await _build_harness(
            tmp_path,
            fault_injector=inspect_precommit,
            first_frame=ping,
        )
        holder["harness"] = harness
        try:
            committed = await _establish(harness)
            transition = harness.owner._v49b_transition  # noqa: SLF001
            assert type(transition) is DriverHandshakeTransitionV49B
            session = committed.session
            evidence = transition.evidence
            assert type(session) is TransportSessionAttestationV4
            assert session.session_nonce == evidence.evidence_nonce_sha256
            assert session.remote_address == evidence.remote_address
            assert session.tls_version == evidence.tls_version == "TLSv1.3"
            assert session.tls_cipher == evidence.tls_cipher
            assert session.alpn_protocol == evidence.alpn_protocol
            assert session.websocket_extensions == evidence.websocket_extensions == ()
            assert session.peer_certificate_sha256 == evidence.peer_certificate_sha256
            assert session.peer_spki_sha256 == evidence.peer_spki_sha256
            assert session.trust_store_manifest_id == evidence.trust_store_manifest_id
            assert session.certificate_verified is evidence.certificate_verified is True
            assert session.hostname_verified is evidence.hostname_verified is True
            assert (
                session.websocket_http_status == evidence.websocket_http_status == 101
            )
            assert (
                session.websocket_accept_verified
                is evidence.websocket_accept_verified
                is True
            )
            assert session.handshake_request_sha256 == evidence.handshake_request_sha256
            assert (
                session.handshake_response_sha256 == evidence.handshake_response_sha256
            )
            assert session.handshake_started_at == transition.pre_sample.wall_after_at
            assert (
                session.handshake_completed_at == transition.post_sample.wall_before_at
            )
            assert (
                session.handshake_started_monotonic_ns
                == transition.pre_sample.boottime_after_ns
            )
            assert (
                session.handshake_completed_monotonic_ns
                == transition.post_sample.boottime_before_ns
            )
            assert session.connection_generation == 1
            assert session.parent_transport_session_id is None
            assert session.collector_boot_id == transition.owner_snapshot.kernel_boot_id
            assert (
                session.collector_runtime_id
                == harness.driver.runtime_environment_manifest_id
            )
            assert harness.owner.driver_policy_id == transition.driver_policy_id
            assert harness.driver.is_v49b_measured_profile
            assert not harness.driver.is_v49b_promotion_eligible
            assert (
                harness.runtime.state
                is PhysicalTransportRuntimeStateV4.SESSION_COMMITTED
            )
            assert (
                harness.runtime.current_transport_session_id
                == session.transport_session_id
            )
            assert observations == ["after_transport_session_attestation_insert"]
            harness.owner._assert_v49b_io_bound()  # noqa: SLF001
            assert harness.server.application_reads.empty()
            assert _typed_count(harness.store, "transport_session_attestations") == 1
            assert _typed_count(harness.store, "transport_control_socket_bindings") == 1

            with pytest.raises(
                PhysicalTransportRuntimeV4StateError, match="requires state READY"
            ):
                await _establish(harness, key="v49b-session-reuse")
        finally:
            await harness.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("attack", ["copied-transition", "tampered-session"])
def test_owner_rejects_copied_transition_and_tampered_signed_session(
    tmp_path: Path,
    attack: str,
) -> None:
    async def scenario() -> None:
        harness = await _build_harness(tmp_path)
        inspected = False

        def intercept(
            session: TransportSessionAttestationV4,
            *,
            socket_owner: LinuxSocketOwnerV4,
            idempotency_key: str,
            prepared_clock_evidence: Any,
            driver_transition: DriverHandshakeTransitionV49B,
        ) -> Any:
            nonlocal inspected
            del idempotency_key, prepared_clock_evidence
            inspected = True
            if attack == "copied-transition":
                copied = copy.copy(driver_transition)
                assert type(copied) is DriverHandshakeTransitionV49B
                assert copied is not driver_transition
                with pytest.raises(LinuxSocketOwnerV4Error, match="retained unbound"):
                    socket_owner.assert_v49b_session_mapping(copied, session)
            else:
                tampered = replace(session, remote_address="127.0.0.2:65535")
                with pytest.raises(Exception, match="signature|projection"):
                    socket_owner.assert_v49b_session_mapping(
                        driver_transition,
                        tampered,
                    )
            raise RuntimeError("stop after adversarial mapping check")

        harness.runtime._commit_bound_session_core = intercept  # type: ignore[method-assign] # noqa: SLF001
        try:
            with pytest.raises(PhysicalTransportRuntimeV4FaultLatched):
                await _establish(harness)
            assert inspected
            assert (
                harness.runtime.state is PhysicalTransportRuntimeStateV4.FAULT_LATCHED
            )
            assert harness.runtime.current_transport_session_id is None
            assert harness.driver.state is TlsWebSocketDriverStateV49.CLOSED
            assert _typed_count(harness.store, "transport_session_attestations") == 0
            assert _typed_count(harness.store, "transport_control_socket_bindings") == 0
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_unsigned_driver_capability_fails_before_network_io(tmp_path: Path) -> None:
    async def scenario() -> None:
        harness = await _build_harness(
            tmp_path,
            include_signed_driver_policy=False,
        )
        try:
            with pytest.raises(
                PhysicalTransportRuntimeV4FaultLatched,
                match="signed measured-driver policy",
            ):
                await _establish(harness)
            assert not harness.server.request_seen.is_set()
            assert (
                harness.runtime.state is PhysicalTransportRuntimeStateV4.FAULT_LATCHED
            )
            assert harness.driver.state is TlsWebSocketDriverStateV49.CLOSED
            assert _typed_count(harness.store, "transport_session_attestations") == 0
        finally:
            await harness.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("identity_failure", "expected_failure"),
    (
        (
            AttributeError("missing driver policy identity"),
            PhysicalTransportRuntimeV4FaultLatched,
        ),
        (KeyboardInterrupt("interrupted identity read"), KeyboardInterrupt),
    ),
)
def test_driver_policy_identity_read_failure_aborts_before_network_io(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    identity_failure: BaseException,
    expected_failure: type[BaseException],
) -> None:
    async def scenario() -> None:
        harness = await _build_harness(tmp_path)

        def fail_identity(_: LinuxSocketOwnerV4) -> str:
            raise identity_failure

        monkeypatch.setattr(
            LinuxSocketOwnerV4,
            "driver_policy_id",
            property(fail_identity),
        )
        try:
            with pytest.raises(expected_failure):
                await _establish(harness)
            assert not harness.server.request_seen.is_set()
            assert (
                harness.runtime.state is PhysicalTransportRuntimeStateV4.FAULT_LATCHED
            )
            assert harness.runtime.current_transport_session_id is None
            assert harness.driver.state is TlsWebSocketDriverStateV49.CLOSED
            assert _typed_count(harness.store, "transport_session_attestations") == 0
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_measured_runtime_identity_mismatch_fails_after_handshake_before_commit(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        harness = await _build_harness(tmp_path, measured_runtime_mismatch=True)
        try:
            with pytest.raises(PhysicalTransportRuntimeV4FaultLatched):
                await _establish(harness)
            assert harness.server.request_seen.is_set()
            assert (
                harness.runtime.state is PhysicalTransportRuntimeStateV4.FAULT_LATCHED
            )
            assert harness.runtime.current_transport_session_id is None
            assert harness.driver.state is TlsWebSocketDriverStateV49.CLOSED
            assert _typed_count(harness.store, "transport_session_attestations") == 0
            assert _typed_count(harness.store, "transport_control_socket_bindings") == 0
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_projection_failure_rolls_back_atomic_pair_and_latches_one_shot_owner(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        def fail_session(stage: str) -> None:
            if stage == "after_transport_socket_owner_binding_insert":
                raise RuntimeError("injected V4.9B projection failure")

        harness = await _build_harness(tmp_path, fault_injector=fail_session)
        try:
            with pytest.raises(PhysicalTransportRuntimeV4FaultLatched):
                await _establish(harness)
            assert (
                harness.runtime.state is PhysicalTransportRuntimeStateV4.FAULT_LATCHED
            )
            assert harness.runtime.current_transport_session_id is None
            assert harness.driver.state is TlsWebSocketDriverStateV49.CLOSED
            assert _typed_count(harness.store, "transport_session_attestations") == 0
            assert _typed_count(harness.store, "transport_control_socket_bindings") == 0
            with pytest.raises(
                PhysicalTransportRuntimeV4StateError, match="requires state READY"
            ):
                await _establish(harness, key="v49b-retry-forbidden")
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_postcommit_owner_loss_preserves_evidence_but_never_send_authority(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        armed = False
        holder: dict[str, _Harness] = {}

        def lose_owner_before_commit(stage: str) -> None:
            if armed and stage == "before_commit":
                holder["harness"].owner._socket.close()  # noqa: SLF001

        harness = await _build_harness(
            tmp_path, fault_injector=lose_owner_before_commit
        )
        holder["harness"] = harness
        armed = True
        try:
            with pytest.raises(PhysicalTransportRuntimeV4FaultLatched):
                await _establish(harness)
            assert (
                harness.runtime.state is PhysicalTransportRuntimeStateV4.FAULT_LATCHED
            )
            assert harness.runtime.current_transport_session_id is None
            assert harness.runtime.current_socket_lease_id is None
            assert harness.driver.state is TlsWebSocketDriverStateV49.CLOSED
            assert _typed_count(harness.store, "transport_session_attestations") == 1
            assert _typed_count(harness.store, "transport_control_socket_bindings") == 1
            harness.store.verify()
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_postcommit_evidence_bind_failure_keeps_pair_but_publishes_no_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        harness = await _build_harness(tmp_path)

        def fail_bind(
            _: LinuxSocketOwnerV4,
            transition: DriverHandshakeTransitionV49B,
            session: TransportSessionAttestationV4,
        ) -> None:
            assert type(transition) is DriverHandshakeTransitionV49B
            assert type(session) is TransportSessionAttestationV4
            raise RuntimeError("injected postcommit evidence bind failure")

        monkeypatch.setattr(
            LinuxSocketOwnerV4,
            "bind_committed_v49b_handshake",
            fail_bind,
        )
        try:
            with pytest.raises(PhysicalTransportRuntimeV4FaultLatched):
                await _establish(harness)
            assert (
                harness.runtime.state is PhysicalTransportRuntimeStateV4.FAULT_LATCHED
            )
            assert harness.runtime.current_transport_session_id is None
            assert harness.runtime.current_socket_lease_id is None
            assert harness.driver.state is TlsWebSocketDriverStateV49.CLOSED
            assert _typed_count(harness.store, "transport_session_attestations") == 1
            assert _typed_count(harness.store, "transport_control_socket_bindings") == 1
            harness.store.verify()
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_cancelled_handshake_closes_all_authority_without_durable_session(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        harness = await _build_harness(tmp_path, stall_response=True)
        try:
            task = asyncio.create_task(_establish(harness))
            await asyncio.wait_for(harness.server.request_seen.wait(), timeout=5)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert (
                harness.runtime.state is PhysicalTransportRuntimeStateV4.FAULT_LATCHED
            )
            assert harness.runtime.current_transport_session_id is None
            assert harness.driver.state is TlsWebSocketDriverStateV49.CLOSED
            assert _typed_count(harness.store, "transport_session_attestations") == 0
            assert _typed_count(harness.store, "transport_control_socket_bindings") == 0
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_baseexception_during_projection_rolls_back_and_closes_authority(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        def interrupt_session(stage: str) -> None:
            if stage == "after_transport_session_attestation_insert":
                raise KeyboardInterrupt("injected V4.9B BaseException")

        harness = await _build_harness(tmp_path, fault_injector=interrupt_session)
        try:
            with pytest.raises(KeyboardInterrupt, match="injected V4.9B"):
                await _establish(harness)
            assert (
                harness.runtime.state is PhysicalTransportRuntimeStateV4.FAULT_LATCHED
            )
            assert harness.runtime.current_transport_session_id is None
            assert harness.driver.state is TlsWebSocketDriverStateV49.CLOSED
            assert _typed_count(harness.store, "transport_session_attestations") == 0
            assert _typed_count(harness.store, "transport_control_socket_bindings") == 0
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_public_owner_constructor_remains_closed_to_v49b_candidate(
    tmp_path: Path,
) -> None:
    async def public_owner_scenario() -> None:
        harness = await _build_harness(tmp_path, exact_candidate=False)
        try:
            assert not harness.owner.is_v49b_exact_profile
            with pytest.raises(PhysicalTransportRuntimeV4FaultLatched):
                await _establish(harness)
            assert not harness.server.request_seen.is_set()
            assert harness.driver.state is TlsWebSocketDriverStateV49.CLOSED
        finally:
            await harness.close()

    asyncio.run(public_owner_scenario())


def test_live_factory_remains_closed_at_post_v49f_promotion_gate(
    tmp_path: Path,
) -> None:
    clock = _deterministic_clock(tmp_path / "c")
    signer = Ed25519CheckpointSigner.generate()
    certificates = _certificates()
    ca_path, _, _ = _write_certificates(tmp_path, certificates)
    trust_store = _trust_store(ca_path, certificates)
    driver_policy = capture_current_tls_websocket_driver_policy_v49b()
    materials = _deployment_admission(
        collector_signer=signer,
        clock_policy=clock.policy,
        trust_store_manifest=trust_store.manifest,
        driver_policy=driver_policy,
        include_signed_driver_policy=True,
        measured_runtime_mismatch=False,
    )
    trust_store.close()
    client, peer = connected_tcp_pair()
    store = PhysicalProjectionStoreV4(
        tmp_path / "closed-live-factory.sqlite3",
        clock=lambda: T0,
    )
    lease = private_lease(tmp_path, holder_id="closed-live-factory")
    try:
        with pytest.raises(
            Exception,
            match="post-V4.9F promotion validation and operational qualification",
        ):
            build_linux_physical_transport_runtime_v4(
                journal=store,
                writer_lease=lease,
                owned_socket=client,
                driver=RecordingDriver(),
                clock_policy=clock.policy,
                configured_source_artifacts=(),
                signer=signer,
                deployment_admission=materials.admission,
                idempotency_prefix="closed-live-factory",
            )
        assert client.fileno() == -1
    finally:
        peer.close()
        client.close()
        lease.release()
        store.close()
        clock.close()

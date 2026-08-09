from __future__ import annotations

import asyncio
import base64
import hashlib
import inspect
import socket
import subprocess
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

import riskyieldmm.trading.physical_transport_linux_v4 as linux_v4
from riskyieldmm.trading.canonical import sha256_digest
from riskyieldmm.trading.ledger_signing import Ed25519CheckpointSigner
from riskyieldmm.trading.operational_artifact_loading_v4 import (
    ConfiguredChronySourceArtifactV4,
    derive_configured_chrony_source_set_root_v4,
)
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
    approve_deployment_bundle_v4,
    derive_deployment_signing_key_id,
)
from riskyieldmm.trading.physical_projection_v4 import PhysicalProjectionStoreV4
from riskyieldmm.trading.physical_transport_control_runtime_v4 import (
    PhysicalTransportControlMediatorV4,
    PhysicalTransportControlPermitBindingV4Error,
    PhysicalTransportControlRuntimeStateV4,
)
from riskyieldmm.trading.physical_transport_control_v4 import (
    OutboundControlKindV4,
    OutboundControlWirePreparedV4,
    OutboundWebSocketOpcodeV4,
)
from riskyieldmm.trading.physical_transport_lease_v4 import (
    PhysicalTransportWriterLeaseV4,
)
from riskyieldmm.trading.physical_transport_linux_v4 import (
    BoundedCommandResultV4,
    DeterministicLinuxChronyClockV4,
    LinuxChronyClockV4,
    LinuxPhysicalTransportRuntimeBundleV4,
    LinuxSocketOwnerV4,
    LinuxTransportEvidenceV4Error,
    build_linux_physical_transport_runtime_v4,
    run_bounded_command_v4,
)
from riskyieldmm.trading.physical_transport_owner_v4 import (
    TransportSocketOwnerBindingV4,
    derive_transport_socket_lease_id,
    derive_transport_socket_lease_nonce_sha256,
)
from riskyieldmm.trading.physical_transport_runtime_v4 import (
    OperationalDeploymentAdmissionV4,
    PhysicalTransportRuntimeStateV4,
    PhysicalTransportRuntimeV4,
    PhysicalTransportRuntimeV4FaultLatched,
)
from riskyieldmm.trading.physical_transport_v4 import (
    derive_transport_attestation_key_id,
)
from tests._chronyd_launch_policy_v48b import (
    make_test_chronyd_launch_policy_v48b,
)

pytestmark = pytest.mark.skipif(
    sys.platform != "linux", reason="Linux-only V4.7B adversarial tests"
)

T0 = datetime(2026, 7, 15, 12, tzinfo=timezone.utc)


def digest(label: str) -> str:
    return sha256_digest({"label": label})


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clock_policy_and_sources(
    tmp_path: Path, *, live_executable: bool = False
) -> tuple[
    ClockSourcePolicyManifestV4,
    tuple[ConfiguredChronySourceArtifactV4, ...],
]:
    executable = tmp_path / "chronyc"
    executable.write_bytes(
        b"#!/bin/sh\nprintf 'chronyc (chrony) version 4.8\\n'\n"
        if live_executable
        else b"reviewed deterministic chronyc artifact\n"
    )
    executable.chmod(0o700)
    config = tmp_path / "chrony.conf"
    config.write_text("sourcedir /signed/sources\n", encoding="ascii")
    config.chmod(0o600)
    source = tmp_path / "source.sources"
    source.write_text("server time-a.example iburst\n", encoding="ascii")
    source.chmod(0o600)
    sources = (
        ConfiguredChronySourceArtifactV4(
            path=str(source),
            sha256=file_digest(source),
        ),
    )
    policy = ClockSourcePolicyManifestV4(
        source_kind=CLOCK_SOURCE_KIND,
        chrony_version="4.8",
        chronyc_executable_path=str(executable),
        chronyc_executable_sha256=file_digest(executable),
        chrony_config_path=str(config),
        chrony_config_sha256=file_digest(config),
        chronyc_command_socket_path=str(tmp_path / "chronyd.sock"),
        chronyc_command_timeout_milliseconds=1_000,
        chronyc_max_output_bytes=65_536,
        configured_source_set_root_sha256=(
            derive_configured_chrony_source_set_root_v4(sources)
        ),
        min_selectable_sources=1,
        max_uncertainty_milliseconds=1_000,
        max_sample_age_milliseconds=5_000,
        require_synchronized=True,
        require_normal_leap=True,
        monotonic_domain_profile=MONOTONIC_DOMAIN_PROFILE,
        chronyd_launch_policy=make_test_chronyd_launch_policy_v48b(
            read_only_api_socket_path=str(tmp_path / "chronyd.sock")
        ),
    )
    return policy, sources


class DeterministicRunner:
    def __call__(self, argv: tuple[str, ...], **_: Any) -> BoundedCommandResultV4:
        if argv[-1] == "--version":
            return BoundedCommandResultV4(
                returncode=0,
                stdout=b"chronyc (chrony) version 4.8\n",
                stderr=b"",
            )
        reference = f"{T0.timestamp():.6f}"
        output = (
            ".\n"
            ".\n"
            f"A1B2C3D4,time-a.example,2,{reference},0.000100,"
            "0.000010,0.000020,1.0,0.0,0.01,0.002000,0.000200,1.0,Normal\n"
            ".\n"
            "^,*,time-a.example,1,0,377,0,0.000100,0.000100,0.000200\n"
            ".\n"
        ).encode("ascii")
        return BoundedCommandResultV4(returncode=0, stdout=output, stderr=b"")


def deterministic_clock(
    tmp_path: Path,
) -> DeterministicLinuxChronyClockV4:
    policy, sources = clock_policy_and_sources(tmp_path)
    wall_values = iter((T0, T0 + timedelta(milliseconds=1)) * 16)
    return DeterministicLinuxChronyClockV4(
        policy=policy,
        configured_source_artifacts=sources,
        command_runner=DeterministicRunner(),
        wall_clock=lambda: next(wall_values),
    )


def connected_tcp_pair() -> tuple[socket.socket, socket.socket]:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.connect(listener.getsockname())
    server, _ = listener.accept()
    listener.close()
    return client, server


class RecordingDriver:
    def __init__(self) -> None:
        self.text_calls = 0
        self.control_calls = 0

    async def send_exact_text_frame(
        self, owned_socket: socket.socket, payload: bytes
    ) -> None:
        assert owned_socket.fileno() >= 0
        assert payload
        self.text_calls += 1

    async def submit_permitted_chunks(
        self,
        owned_socket: socket.socket,
        *,
        permit: Any,
        ordered_chunks: tuple[bytes, ...],
    ) -> int:
        assert owned_socket.fileno() >= 0
        assert permit is not None
        self.control_calls += 1
        return sum(len(chunk) for chunk in ordered_chunks)


def deterministic_owner(
    tmp_path: Path,
) -> tuple[LinuxSocketOwnerV4, socket.socket, RecordingDriver]:
    client, peer = connected_tcp_pair()
    driver = RecordingDriver()
    owner = LinuxSocketOwnerV4(
        owned_socket=client,
        governed_clock=deterministic_clock(tmp_path),
        driver=driver,
    )
    return owner, peer, driver


def binding_for_owner(
    owner: LinuxSocketOwnerV4,
    *,
    signer: Ed25519CheckpointSigner,
) -> TransportSocketOwnerBindingV4:
    snapshot = owner.snapshot()
    session_id = digest("session")
    nonce_sha256 = derive_transport_socket_lease_nonce_sha256(
        b"v47b-sealing-adversarial-nonce"
    )
    fence = digest("writer-fence")
    lease_id = derive_transport_socket_lease_id(
        transport_session_id=session_id,
        kernel_socket_identity=snapshot.kernel_socket_identity,
        socket_lease_nonce_sha256=nonce_sha256,
        writer_fence_token_sha256=fence,
        writer_fence_generation=3,
    )
    return TransportSocketOwnerBindingV4.create_signed(
        signer=signer,
        transport_session_id=session_id,
        deployment_bundle_id=digest("deployment"),
        transport_subscription_policy_id=digest("subscription-policy"),
        physical_scope_manifest_id=digest("scope"),
        adapter_policy_id=digest("adapter"),
        capture_partition_id=digest("partition"),
        socket_lease_id=lease_id,
        socket_lease_nonce_sha256=nonce_sha256,
        kernel_socket_identity=snapshot.kernel_socket_identity,
        socket_identity_profile=snapshot.socket_identity_profile,
        socket_cookie_u64=snapshot.socket_cookie_u64,
        kernel_boot_id=snapshot.kernel_boot_id,
        time_namespace_id=snapshot.time_namespace_id,
        network_namespace_id=snapshot.network_namespace_id,
        clock_source_manifest_id=owner.governed_clock.policy.manifest_id,
        monotonic_clock_domain_id=snapshot.monotonic_clock_domain_id,
        clock_profile=snapshot.clock_profile,
        clock_resolution_ns=snapshot.clock_resolution_ns,
        connection_generation=2,
        writer_fence_token_sha256=fence,
        writer_fence_generation=3,
        bound_at=T0 - timedelta(seconds=1),
        bound_monotonic_before_ns=1,
        bound_monotonic_after_ns=2,
        clock_uncertainty_milliseconds=1_000,
    )


def masked_text_frame(payload: bytes) -> bytes:
    assert len(payload) < 126
    mask = b"\x01\x23\x45\x67"
    masked = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
    return bytes((0x81, 0x80 | len(payload))) + mask + masked


def wire_for_binding(
    binding: TransportSocketOwnerBindingV4,
) -> OutboundControlWirePreparedV4:
    payload = b'{"op":"ping","req_id":"v47b-sealing"}'
    frame = masked_text_frame(payload)
    encoded = base64.b64encode(frame).decode("ascii")
    return OutboundControlWirePreparedV4(
        outbound_control_intent_id=digest("control-intent"),
        transport_session_id=binding.transport_session_id,
        socket_lease_id=binding.socket_lease_id,
        connection_generation=binding.connection_generation,
        deployment_bundle_id=binding.deployment_bundle_id,
        writer_fence_token_sha256=binding.writer_fence_token_sha256,
        writer_fence_generation=binding.writer_fence_generation,
        control_kind=OutboundControlKindV4.APPLICATION_JSON_HEARTBEAT,
        logical_websocket_opcode=OutboundWebSocketOpcodeV4.TEXT,
        logical_payload_base64=base64.b64encode(payload).decode("ascii"),
        logical_payload_sha256=hashlib.sha256(payload).hexdigest(),
        wire_chunks_base64=(encoded,),
        wire_chunks_sha256=(hashlib.sha256(frame).hexdigest(),),
        wire_batch_sha256=sha256_digest(
            {
                "domain": "RiskYieldMMExactOrderedPreTlsWebSocketChunksV4_5",
                "ordered_chunks_base64": [encoded],
            }
        ),
        wire_octet_length=len(frame),
        prepared_at=T0,
        monotonic_clock_domain_id=binding.monotonic_clock_domain_id,
        prepared_monotonic_ns=1_000,
        send_not_after=T0 + timedelta(seconds=1),
        send_not_after_monotonic_ns=1_001_000,
    )


class RejectBeforePermitJournal:
    def __init__(self) -> None:
        self.fence_calls = 0
        self.consume_calls = 0
        self.result_calls = 0

    def assert_transport_runtime_writer_fence(
        self, *, lease_token_sha256: str, generation: int
    ) -> None:
        assert lease_token_sha256 == digest("writer-fence")
        assert generation == 3
        self.fence_calls += 1

    def consume_outbound_control_write_permit(self, *_: Any, **__: Any) -> Any:
        self.consume_calls += 1
        raise AssertionError("cross-binding wire consumed a permit")

    def append_outbound_control_dispatch_result(self, *_: Any, **__: Any) -> Any:
        self.result_calls += 1
        raise AssertionError("cross-binding wire persisted a dispatch result")


def deployment_admission_for_clock(
    clock_policy: ClockSourcePolicyManifestV4,
    *,
    collector_signer: Ed25519CheckpointSigner,
) -> OperationalDeploymentAdmissionV4:
    valid_from = T0 - timedelta(days=1)
    valid_until = T0 + timedelta(days=1)
    release = CollectorReleaseManifestV4(
        release_name="riskyieldmm-collector",
        release_version="0.1.0-v47b-sealed-test",
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
    runtime = RuntimeEnvironmentManifestV4(
        python_implementation="CPython",
        python_version="3.12.0-v47b-test",
        python_executable_sha256=digest("python-executable"),
        platform_tag="linux_x86_64_v47b_test",
        openssl_version="OpenSSL_3_v47b_test",
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
            collector_signer.public_key_bytes
        ),
        collector_attestation_public_key_hex=collector_signer.public_key_bytes.hex(),
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
    approval = approve_deployment_bundle_v4(bundle, signers=(deployment_signer,))
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


@pytest.mark.parametrize("seam", ["command_runner", "wall_clock"])
def test_live_clock_public_constructor_rejects_injected_seams(seam: str) -> None:
    kwargs = {
        "policy": object(),
        "configured_source_artifacts": (),
        seam: lambda: None,
    }

    with pytest.raises(TypeError, match="unexpected keyword argument"):
        LinuxChronyClockV4(**kwargs)  # type: ignore[arg-type]


def test_deterministic_clock_and_owner_are_non_live_profiles(tmp_path: Path) -> None:
    clock = deterministic_clock(tmp_path)
    client, peer = connected_tcp_pair()
    owner = LinuxSocketOwnerV4(
        owned_socket=client,
        governed_clock=clock,
        driver=RecordingDriver(),
    )
    try:
        assert clock.is_live_profile is False
        assert owner.is_live_profile is False
        with pytest.raises(TypeError, match="exact sealed owner"):
            LinuxPhysicalTransportRuntimeBundleV4(
                authority=owner,
                runtime=object(),  # type: ignore[arg-type]
            )
    finally:
        owner.abort()
        peer.close()


def test_sealed_factory_exposes_no_prebuilt_authority_or_test_seams() -> None:
    signature = inspect.signature(build_linux_physical_transport_runtime_v4)
    forbidden = {
        "authority",
        "governed_clock",
        "clock_source",
        "command_runner",
        "wall_clock",
        "random_bytes",
        "launcher",
        "loaded_chronyd",
        "chronyd_authority",
        "launch_capability",
    }

    assert forbidden.isdisjoint(signature.parameters)
    for name in forbidden:
        with pytest.raises(TypeError, match="unexpected keyword argument"):
            signature.bind_partial(**{name: object()})


def test_sealed_factory_rejects_structural_driver_before_any_launch_until_v49(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy, sources = clock_policy_and_sources(tmp_path, live_executable=True)
    signer = Ed25519CheckpointSigner.generate()
    admission = deployment_admission_for_clock(policy, collector_signer=signer)
    client, peer = connected_tcp_pair()
    driver = RecordingDriver()
    tmp_path.chmod(0o700)
    lease = PhysicalTransportWriterLeaseV4(
        tmp_path / "writer.lock", holder_id="v48a-sealed-test"
    )
    clock_constructions: list[object] = []
    command_calls: list[object] = []

    def forbidden_clock(**_: Any) -> None:
        clock_constructions.append(object())
        raise AssertionError("clock construction crossed the V4.9 driver gate")

    def forbidden_command(*_: Any, **__: Any) -> None:
        command_calls.append(object())
        raise AssertionError("subprocess crossed the V4.9 driver gate")

    monkeypatch.setattr(linux_v4, "LinuxChronyClockV4", forbidden_clock)
    monkeypatch.setattr(linux_v4, "run_bounded_command_v4", forbidden_command)
    try:
        with PhysicalProjectionStoreV4(tmp_path / "projection.sqlite") as store:
            with pytest.raises(
                LinuxTransportEvidenceV4Error,
                match=("post-V4.9F promotion validation and operational qualification"),
            ):
                build_linux_physical_transport_runtime_v4(
                    journal=store,
                    writer_lease=lease,
                    owned_socket=client,
                    driver=driver,
                    clock_policy=policy,
                    configured_source_artifacts=sources,
                    signer=signer,
                    deployment_admission=admission,
                    idempotency_prefix="v48a-sealed-adversarial",
                )
            assert not store.is_governed_clock_bound
        assert clock_constructions == []
        assert command_calls == []
        assert client.fileno() == -1
    finally:
        if client.fileno() >= 0:
            client.close()
        peer.close()


def test_sealed_factory_rejects_fake_journal_before_socket_ownership(
    tmp_path: Path,
) -> None:
    policy, sources = clock_policy_and_sources(tmp_path, live_executable=True)
    signer = Ed25519CheckpointSigner.generate()
    admission = deployment_admission_for_clock(policy, collector_signer=signer)
    client, peer = connected_tcp_pair()
    tmp_path.chmod(0o700)
    lease = PhysicalTransportWriterLeaseV4(
        tmp_path / "writer.lock", holder_id="v48a-fake-journal"
    )
    try:
        with pytest.raises(TypeError, match="exact PhysicalProjectionStoreV4"):
            build_linux_physical_transport_runtime_v4(
                journal=object(),
                writer_lease=lease,
                owned_socket=client,
                driver=RecordingDriver(),
                clock_policy=policy,
                configured_source_artifacts=sources,
                signer=signer,
                deployment_admission=admission,
                idempotency_prefix="v48a-fake-journal",
            )

        assert client.fileno() >= 0
    finally:
        client.close()
        peer.close()


def test_sealed_factory_rejects_fake_lease_before_socket_ownership(
    tmp_path: Path,
) -> None:
    policy, sources = clock_policy_and_sources(tmp_path, live_executable=True)
    signer = Ed25519CheckpointSigner.generate()
    admission = deployment_admission_for_clock(policy, collector_signer=signer)
    client, peer = connected_tcp_pair()
    try:
        with PhysicalProjectionStoreV4(tmp_path / "projection.sqlite") as store:
            with pytest.raises(TypeError, match="exact PhysicalTransportWriterLeaseV4"):
                build_linux_physical_transport_runtime_v4(
                    journal=store,
                    writer_lease=object(),
                    owned_socket=client,
                    driver=RecordingDriver(),
                    clock_policy=policy,
                    configured_source_artifacts=sources,
                    signer=signer,
                    deployment_admission=admission,
                    idempotency_prefix="v48a-fake-lease",
                )

        assert client.fileno() >= 0
    finally:
        client.close()
        peer.close()


def test_bound_control_constructor_rejects_wrong_signer_before_authority_use(
    tmp_path: Path,
) -> None:
    owner, peer, _ = deterministic_owner(tmp_path)
    signer = Ed25519CheckpointSigner.generate()
    wrong_signer = Ed25519CheckpointSigner.generate()
    binding = binding_for_owner(owner, signer=signer)
    journal = RejectBeforePermitJournal()
    try:
        with pytest.raises(TypeError, match="signer differs"):
            PhysicalTransportControlMediatorV4.from_bound_transport_authority(
                journal=journal,  # type: ignore[arg-type]
                authority=owner,
                binding=binding,
                signer=wrong_signer,
            )

        assert journal.fence_calls == 0
        assert owner.snapshot().socket_cookie_u64 == binding.socket_cookie_u64
    finally:
        owner.abort()
        peer.close()


def test_direct_bound_control_constructor_cannot_bypass_derived_authority(
    tmp_path: Path,
) -> None:
    owner, peer, _ = deterministic_owner(tmp_path)
    signer = Ed25519CheckpointSigner.generate()
    wrong_signer = Ed25519CheckpointSigner.generate()
    binding = binding_for_owner(owner, signer=signer)
    journal = RejectBeforePermitJournal()
    try:
        with pytest.raises(TypeError, match="derived authority path"):
            PhysicalTransportControlMediatorV4(
                journal=journal,  # type: ignore[arg-type]
                writer=owner,
                clock=lambda: (T0, 1),
                signer=wrong_signer,
                expected_socket_lease_id=binding.socket_lease_id,
                expected_connection_generation=binding.connection_generation,
                assert_writer_authority=lambda: None,
                _bound_authority=owner,
                _bound_binding=binding,
            )

        assert journal.fence_calls == 0
        assert owner.snapshot().socket_cookie_u64 == binding.socket_cookie_u64
    finally:
        owner.abort()
        peer.close()


@pytest.mark.parametrize(
    ("field", "wrong_value"),
    [
        ("transport_session_id", digest("other-session")),
        ("deployment_bundle_id", digest("other-deployment")),
        ("writer_fence_token_sha256", digest("other-writer-fence")),
        ("monotonic_clock_domain_id", digest("other-clock-domain")),
    ],
)
def test_cross_binding_wire_is_rejected_before_permit_or_driver(
    tmp_path: Path,
    field: str,
    wrong_value: str,
) -> None:
    owner, peer, driver = deterministic_owner(tmp_path)
    signer = Ed25519CheckpointSigner.generate()
    binding = binding_for_owner(owner, signer=signer)
    journal = RejectBeforePermitJournal()
    mediator = PhysicalTransportControlMediatorV4.from_bound_transport_authority(
        journal=journal,  # type: ignore[arg-type]
        authority=owner,
        binding=binding,
        signer=signer,
    )
    wire = replace(wire_for_binding(binding), **{field: wrong_value})
    try:
        with pytest.raises(
            PhysicalTransportControlPermitBindingV4Error,
            match="exact bound control authority",
        ):
            asyncio.run(
                mediator.dispatch_prepared(
                    wire,
                    socket_lease_id=binding.socket_lease_id,
                    connection_generation=binding.connection_generation,
                    idempotency_prefix="v47b-cross-binding",
                )
            )

        assert mediator.state is PhysicalTransportControlRuntimeStateV4.FAULT_LATCHED
        assert journal.fence_calls == 0
        assert journal.consume_calls == 0
        assert journal.result_calls == 0
        assert driver.control_calls == 0
        assert driver.text_calls == 0
    finally:
        owner.abort()
        peer.close()


@pytest.mark.parametrize("failure_point", ["construct", "register"])
def test_bounded_runner_terminates_child_when_selector_setup_fails(
    monkeypatch: pytest.MonkeyPatch,
    failure_point: str,
) -> None:
    real_popen = subprocess.Popen
    spawned: list[subprocess.Popen[bytes]] = []

    def capture_popen(*args: Any, **kwargs: Any) -> subprocess.Popen[bytes]:
        proc = real_popen(*args, **kwargs)  # noqa: S603
        spawned.append(proc)
        return proc

    class ExplodingSelector:
        def __init__(self) -> None:
            self.closed = False
            if failure_point == "construct":
                raise RuntimeError("selector construction failed")

        def register(self, *_: Any, **__: Any) -> None:
            raise RuntimeError("selector registration failed")

        def close(self) -> None:
            self.closed = True

    monkeypatch.setattr(linux_v4.subprocess, "Popen", capture_popen)
    monkeypatch.setattr(linux_v4.selectors, "DefaultSelector", ExplodingSelector)

    with pytest.raises(RuntimeError, match="selector .* failed"):
        run_bounded_command_v4(
            (sys.executable, "-c", "import time; time.sleep(60)"),
            pass_fds=(),
            timeout_milliseconds=5_000,
            maximum_output_bytes=1_024,
        )

    assert len(spawned) == 1
    assert spawned[0].wait(timeout=1) != 0


def test_direct_runtime_constructor_cannot_bypass_sealed_profiles() -> None:
    with pytest.raises(TypeError, match="sealed Linux runtime factory"):
        PhysicalTransportRuntimeV4(
            journal=object(),  # type: ignore[arg-type]
            writer_lease=object(),  # type: ignore[arg-type]
            clock_source=object(),  # type: ignore[arg-type]
            signer=object(),
            deployment_admission=object(),  # type: ignore[arg-type]
            idempotency_prefix="v47b-direct-bypass",
        )

    class FakeLiveAuthority:
        is_live_profile = True

    with pytest.raises(TypeError, match="exact sealed Linux authority"):
        PhysicalTransportRuntimeV4._from_live_linux_profile(  # noqa: SLF001
            journal=object(),  # type: ignore[arg-type]
            writer_lease=object(),  # type: ignore[arg-type]
            clock_source=FakeLiveAuthority(),  # type: ignore[arg-type]
            signer=object(),
            deployment_admission=object(),  # type: ignore[arg-type]
            idempotency_prefix="v47b-forged-live-profile",
        )

    with pytest.raises(TypeError, match="exact sealed Linux authority"):
        PhysicalTransportRuntimeV4(
            journal=object(),  # type: ignore[arg-type]
            writer_lease=object(),  # type: ignore[arg-type]
            clock_source=FakeLiveAuthority(),  # type: ignore[arg-type]
            signer=object(),
            deployment_admission=object(),  # type: ignore[arg-type]
            idempotency_prefix="v48a-forged-live-token",
            _construction_token=(  # noqa: SLF001
                PhysicalTransportRuntimeV4._LIVE_LINUX_CONSTRUCTION_TOKEN
            ),
        )


def test_linux_socket_owner_rejects_non_clock_object(tmp_path: Path) -> None:
    client, peer = connected_tcp_pair()
    try:
        with pytest.raises(TypeError, match="LinuxChronyClockV4"):
            LinuxSocketOwnerV4(
                owned_socket=client,
                governed_clock=object(),  # type: ignore[arg-type]
                driver=RecordingDriver(),
            )
    finally:
        client.close()
        peer.close()


def test_linux_socket_owner_rejects_forged_clock_subclass() -> None:
    class ForgedClock(LinuxChronyClockV4):
        def __init__(self) -> None:
            pass

    client, peer = connected_tcp_pair()
    try:
        with pytest.raises(TypeError, match="exact LinuxChronyClockV4"):
            LinuxSocketOwnerV4(
                owned_socket=client,
                governed_clock=ForgedClock(),
                driver=RecordingDriver(),
            )
    finally:
        client.close()
        peer.close()


def test_test_runtime_cannot_downgrade_live_authority(tmp_path: Path) -> None:
    clock = deterministic_clock(tmp_path)
    with PhysicalProjectionStoreV4(tmp_path / "projection.sqlite") as store:
        store._governed_clock_source = clock  # noqa: SLF001
        store._governed_clock_live_profile = True  # noqa: SLF001
        with pytest.raises(TypeError, match="cannot downgrade live"):
            PhysicalTransportRuntimeV4.for_test(journal=store)

    class FakeLiveAuthority:
        is_live_profile = True

    with pytest.raises(TypeError, match="cannot downgrade live"):
        PhysicalTransportRuntimeV4.for_test(clock_source=FakeLiveAuthority())

    with pytest.raises(TypeError, match="cannot downgrade live"):
        PhysicalTransportRuntimeV4(
            journal=object(),  # type: ignore[arg-type]
            writer_lease=object(),  # type: ignore[arg-type]
            clock_source=FakeLiveAuthority(),  # type: ignore[arg-type]
            signer=object(),
            deployment_admission=object(),  # type: ignore[arg-type]
            idempotency_prefix="v48a-direct-test-token-downgrade",
            _construction_token=(  # noqa: SLF001
                PhysicalTransportRuntimeV4._TEST_CONSTRUCTION_TOKEN
            ),
        )


def test_live_runtime_token_rejects_injected_clock_and_entropy_seams() -> None:
    class FakeLiveAuthority:
        is_live_profile = True

    for field, value in (
        ("wall_clock", lambda: T0),
        ("random_bytes", lambda length: bytes(length)),
    ):
        kwargs = {
            "journal": object(),
            "writer_lease": object(),
            "clock_source": FakeLiveAuthority(),
            "signer": object(),
            "deployment_admission": object(),
            "idempotency_prefix": "v48a-live-seam-bypass",
            "_construction_token": (
                PhysicalTransportRuntimeV4._LIVE_LINUX_CONSTRUCTION_TOKEN
            ),
            field: value,
        }
        with pytest.raises(TypeError, match="forbids injected clock/entropy"):
            PhysicalTransportRuntimeV4(**kwargs)  # type: ignore[arg-type]


def test_live_session_rejection_aborts_retained_owner_and_decoy() -> None:
    class AbortOwner:
        def __init__(self) -> None:
            self.aborted = False

        def abort(self) -> None:
            self.aborted = True

    retained = AbortOwner()
    decoy = AbortOwner()
    runtime = object.__new__(PhysicalTransportRuntimeV4)
    runtime._state = PhysicalTransportRuntimeStateV4.READY  # noqa: SLF001
    runtime._is_live_profile = True  # noqa: SLF001
    runtime._clock_source = retained  # noqa: SLF001
    runtime._fault_cause = None  # noqa: SLF001

    with pytest.raises(PhysicalTransportRuntimeV4FaultLatched, match="exact retained"):
        runtime.commit_session(
            object(),  # type: ignore[arg-type]
            socket_owner=decoy,  # type: ignore[arg-type]
            idempotency_key="v48a-decoy-owner",
        )

    assert retained.aborted
    assert decoy.aborted
    assert runtime.state is PhysicalTransportRuntimeStateV4.FAULT_LATCHED


def test_non_live_session_path_rejects_late_live_owner() -> None:
    class LateLiveOwner:
        is_live_profile = True

        def __init__(self) -> None:
            self.aborted = False

        def abort(self) -> None:
            self.aborted = True

    owner = LateLiveOwner()
    runtime = object.__new__(PhysicalTransportRuntimeV4)
    runtime._state = PhysicalTransportRuntimeStateV4.READY  # noqa: SLF001
    runtime._is_live_profile = False  # noqa: SLF001
    runtime._fault_cause = None  # noqa: SLF001

    with pytest.raises(
        PhysicalTransportRuntimeV4FaultLatched, match="cannot downgrade"
    ):
        runtime.commit_session(
            object(),  # type: ignore[arg-type]
            socket_owner=owner,  # type: ignore[arg-type]
            idempotency_key="v48a-late-live-owner",
        )

    assert owner.aborted
    assert runtime.state is PhysicalTransportRuntimeStateV4.FAULT_LATCHED


def test_live_factory_v49_gate_precedes_invalid_clock_artifact_loading(
    tmp_path: Path,
) -> None:
    policy, sources = clock_policy_and_sources(tmp_path, live_executable=True)
    signer = Ed25519CheckpointSigner.generate()
    bad_policy = replace(policy, chronyc_executable_sha256=digest("wrong-executable"))
    admission = deployment_admission_for_clock(bad_policy, collector_signer=signer)
    client, peer = connected_tcp_pair()
    client_fd = client.fileno()
    tmp_path.chmod(0o700)
    lease = PhysicalTransportWriterLeaseV4(
        tmp_path / "writer.lock", holder_id="v48a-clock-failure"
    )
    try:
        with PhysicalProjectionStoreV4(tmp_path / "projection.sqlite") as store:
            with pytest.raises(
                LinuxTransportEvidenceV4Error,
                match=("post-V4.9F promotion validation and operational qualification"),
            ):
                build_linux_physical_transport_runtime_v4(
                    journal=store,
                    writer_lease=lease,
                    owned_socket=client,
                    driver=RecordingDriver(),
                    clock_policy=bad_policy,
                    configured_source_artifacts=sources,
                    signer=signer,
                    deployment_admission=admission,
                    idempotency_prefix="v47b-construction-failure",
                )

        assert client.fileno() == -1
        with pytest.raises(OSError):
            socket.socket(fileno=client_fd)
    finally:
        peer.close()

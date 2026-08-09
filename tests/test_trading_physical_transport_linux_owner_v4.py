from __future__ import annotations

import asyncio
import hashlib
import os
import select
import signal
import socket
import sys
import threading
import warnings
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from typing import Any

import pytest

from riskyieldmm.trading.canonical import sha256_digest
from riskyieldmm.trading.ledger_signing import Ed25519CheckpointSigner
from riskyieldmm.trading.operational_artifact_loading_v4 import (
    ConfiguredChronySourceArtifactV4,
    derive_configured_chrony_source_set_root_v4,
)
from riskyieldmm.trading.operational_manifests_v4 import (
    CLOCK_SOURCE_KIND,
    MONOTONIC_DOMAIN_PROFILE,
    ClockSourcePolicyManifestV4,
)
from riskyieldmm.trading.operational_runtime_artifacts_v49b import (
    RuntimeArtifactAuthorityV49BError,
)
from riskyieldmm.trading.physical_transport_control_runtime_v4 import (
    PhysicalTransportControlMediatorV4,
)
from riskyieldmm.trading.physical_transport_linux_v4 import (
    BoundedCommandResultV4,
    DeterministicLinuxChronyClockV4,
    DriverHandshakeTransitionV49B,
    LinuxSocketOwnerV4,
    LinuxSocketOwnerV4Error,
)
from riskyieldmm.trading.physical_transport_owner_v4 import (
    TransportSocketOwnerBindingV4,
    derive_transport_socket_lease_id,
    derive_transport_socket_lease_nonce_sha256,
)
from riskyieldmm.trading.physical_transport_tls_v49 import (
    ExactTlsWebSocketDriverV49,
    TlsWebSocketDriverStateV49,
)
from riskyieldmm.trading.physical_transport_v4 import (
    V4_TRANSPORT_HANDSHAKE_COMMITMENT_PROFILE,
    TransportSessionAttestationV4,
)
from tests._chronyd_launch_policy_v48b import (
    make_test_chronyd_launch_policy_v48b,
)
from tests.test_trading_physical_transport_tls_v49 import (
    _certificates,
    _connected_socket,
    _measured_runtime_artifacts,
    _server_context,
    _start_fake_server,
    _trust_store,
    _write_certificates,
)
from tests.test_trading_physical_transport_tls_v49 import (
    _policy as tls_transport_policy,
)

pytestmark = pytest.mark.skipif(
    sys.platform != "linux", reason="Linux-only V4.7B tests"
)

T0 = datetime(2026, 7, 15, 12, tzinfo=timezone.utc)


def digest(label: str) -> str:
    return sha256_digest({"label": label})


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_async(function: Any) -> Any:
    @wraps(function)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return asyncio.run(function(*args, **kwargs))

    return wrapper


class FakeChronycRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, argv: tuple[str, ...], **_: Any) -> BoundedCommandResultV4:
        self.calls.append(argv)
        if argv[-1] == "--version":
            return BoundedCommandResultV4(
                returncode=0,
                stdout=b"chronyc (chrony) version 4.8 (+IPV6)\n",
                stderr=b"",
            )
        reference = f"{T0.timestamp():.6f}"
        output = (
            ".\n"
            ".\n"
            f"A1B2C3D4,source.example,2,{reference},0.000100,"
            "0.000010,0.000020,1.0,0.0,0.01,0.002000,0.000200,1.0,Normal\n"
            ".\n"
            "^,*,source.example,1,0,377,0,0.000100,0.000100,0.000200\n"
            ".\n"
        ).encode("ascii")
        return BoundedCommandResultV4(returncode=0, stdout=output, stderr=b"")


def clock_fixture(
    tmp_path: Path,
) -> tuple[DeterministicLinuxChronyClockV4, FakeChronycRunner]:
    executable = tmp_path / "chronyc"
    executable.write_bytes(b"reviewed-fake-chronyc")
    executable.chmod(0o755)
    config = tmp_path / "chrony.conf"
    config.write_text("sourcedir /signed/sources\n", encoding="ascii")
    config.chmod(0o644)
    source = tmp_path / "source.sources"
    source.write_text("server source.example iburst\n", encoding="ascii")
    source.chmod(0o644)
    artifact = ConfiguredChronySourceArtifactV4(
        path=str(source), sha256=file_digest(source)
    )
    policy = ClockSourcePolicyManifestV4(
        source_kind=CLOCK_SOURCE_KIND,
        chrony_version="4.8",
        chronyc_executable_path=str(executable),
        chronyc_executable_sha256=file_digest(executable),
        chrony_config_path=str(config),
        chrony_config_sha256=file_digest(config),
        chronyc_command_socket_path="/run/chrony/chronyd.sock",
        chronyc_command_timeout_milliseconds=1_000,
        chronyc_max_output_bytes=65_536,
        configured_source_set_root_sha256=(
            derive_configured_chrony_source_set_root_v4((artifact,))
        ),
        min_selectable_sources=1,
        max_uncertainty_milliseconds=1_000,
        max_sample_age_milliseconds=5_000,
        require_synchronized=True,
        require_normal_leap=True,
        monotonic_domain_profile=MONOTONIC_DOMAIN_PROFILE,
        chronyd_launch_policy=make_test_chronyd_launch_policy_v48b(
            read_only_api_socket_path="/run/chrony/chronyd.sock"
        ),
    )
    wall_values = iter((T0, T0 + timedelta(milliseconds=1)) * 16)
    runner = FakeChronycRunner()
    clock = DeterministicLinuxChronyClockV4(
        policy=policy,
        configured_source_artifacts=(artifact,),
        command_runner=runner,
        wall_clock=lambda: next(wall_values),
    )
    return clock, runner


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
        self.sockets: list[socket.socket] = []
        self.events: list[str] = []
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.block_text = False

    async def send_exact_text_frame(
        self, owned_socket: socket.socket, payload: bytes
    ) -> None:
        assert payload
        self.sockets.append(owned_socket)
        self.events.append("text")
        self.entered.set()
        if self.block_text:
            await self.release.wait()

    async def submit_permitted_chunks(
        self,
        owned_socket: socket.socket,
        *,
        permit: Any,
        ordered_chunks: tuple[bytes, ...],
    ) -> int:
        assert permit is not None
        self.sockets.append(owned_socket)
        self.events.append("control")
        return sum(len(item) for item in ordered_chunks)


def owner_fixture(
    tmp_path: Path,
) -> tuple[LinuxSocketOwnerV4, socket.socket, RecordingDriver]:
    clock, _ = clock_fixture(tmp_path)
    client, server = connected_tcp_pair()
    driver = RecordingDriver()
    owner = LinuxSocketOwnerV4(owned_socket=client, governed_clock=clock, driver=driver)
    return owner, server, driver


def _driver_session(
    *,
    owner: LinuxSocketOwnerV4,
    transition: DriverHandshakeTransitionV49B,
    signer: Ed25519CheckpointSigner,
) -> TransportSessionAttestationV4:
    evidence = transition.evidence
    policy = owner.transport_policy
    runtime_environment_id = owner._driver.runtime_environment_manifest_id  # noqa: SLF001
    assert runtime_environment_id is not None
    return TransportSessionAttestationV4.create_signed(
        signer=signer,
        deployment_bundle_id=digest("deployment"),
        clock_source_manifest_id=(transition.pre_sample.clock_source_manifest_id),
        collector_key_authorization_manifest_id=digest("collector-key"),
        transport_subscription_policy_id=(policy.transport_subscription_policy_id),
        physical_scope_manifest_id=digest("scope"),
        adapter_policy_id=digest("adapter"),
        capture_partition_id=digest("partition"),
        collector_instance_id="collector-v49b-test",
        collector_boot_id=transition.owner_snapshot.kernel_boot_id,
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
        handshake_commitment_profile=(V4_TRANSPORT_HANDSHAKE_COMMITMENT_PROFILE),
        handshake_request_sha256=evidence.handshake_request_sha256,
        handshake_response_sha256=evidence.handshake_response_sha256,
        handshake_started_at=transition.handshake_started_at,
        handshake_completed_at=transition.handshake_completed_at,
        monotonic_clock_domain_id=(transition.pre_sample.monotonic_clock_domain_id),
        handshake_started_monotonic_ns=(transition.pre_sample.boottime_after_ns),
        handshake_completed_monotonic_ns=(transition.post_sample.boottime_before_ns),
        clock_uncertainty_milliseconds=(transition.clock_uncertainty_milliseconds),
        collector_release_hash=digest("collector-release"),
        collector_runtime_id=runtime_environment_id,
    )


def test_owner_snapshots_real_cookie_namespaces_and_rich_clock(tmp_path: Path) -> None:
    owner, peer, _ = owner_fixture(tmp_path)
    try:
        snapshot = owner.snapshot()
        evidence = owner.sample()

        assert snapshot.socket_cookie_u64 != "0000000000000000"
        assert snapshot.kernel_socket_identity
        assert snapshot.monotonic_clock_domain_id == evidence.monotonic_clock_domain_id
        assert evidence.monotonic_before_ns < evidence.monotonic_after_ns
        assert evidence.clock_resolution_ns == snapshot.clock_resolution_ns
        assert evidence.observation_sha256 is not None
        assert evidence.selectable_source_count == 1
        assert not owner.is_v49b_exact_profile
        assert not owner.is_live_profile
    finally:
        owner.abort()
        peer.close()


def test_v49b_exact_constructor_rejects_structural_and_owner_subclass_inputs(
    tmp_path: Path,
) -> None:
    clock, _ = clock_fixture(tmp_path)
    client, peer = connected_tcp_pair()
    with pytest.raises(TypeError, match="ExactTlsWebSocketDriverV49"):
        LinuxSocketOwnerV4._from_v49b_exact_profile_for_test(
            owned_socket=client,
            governed_clock=clock,
            driver=RecordingDriver(),  # type: ignore[arg-type]
        )
    assert client.fileno() == -1
    with pytest.raises(Exception, match="left its creating process/thread"):
        clock.sample()
    peer.close()

    class OwnerSubclass(LinuxSocketOwnerV4):
        pass

    second_clock, _ = clock_fixture(tmp_path)
    second_client, second_peer = connected_tcp_pair()
    with pytest.raises(TypeError, match="subclasses"):
        OwnerSubclass._from_v49b_exact_profile_for_test(
            owned_socket=second_client,
            governed_clock=second_clock,
            driver=RecordingDriver(),  # type: ignore[arg-type]
        )
    assert second_client.fileno() == -1
    second_peer.close()


@run_async
async def test_v49b_exact_candidate_brackets_maps_and_binds_identical_evidence(
    tmp_path: Path,
) -> None:
    clock, _ = clock_fixture(tmp_path)
    wall_values = iter(T0 + timedelta(milliseconds=index) for index in range(64))
    clock._wall_clock = lambda: next(wall_values)  # noqa: SLF001
    material = _certificates()
    ca_path, cert_path, key_path = _write_certificates(tmp_path, material)
    fake = await _start_fake_server(_server_context(cert_path, key_path))
    store = _trust_store(ca_path, material)
    runtime_artifacts = _measured_runtime_artifacts(
        tls_trust_store_manifest_id=store.manifest.manifest_id,
        clock_source_policy_manifest_id=clock.policy.manifest_id,
    )
    driver = ExactTlsWebSocketDriverV49.from_measured_authority(
        trust_store=store,
        transport_policy=tls_transport_policy(),
        runtime_artifacts=runtime_artifacts,
    )
    sock = await _connected_socket(fake.address)
    owner = LinuxSocketOwnerV4._from_v49b_exact_profile_for_test(
        owned_socket=sock,
        governed_clock=clock,
        driver=driver,
    )
    try:
        assert owner.is_v49b_exact_profile
        assert not owner.is_live_profile
        if hasattr(os, "fork"):
            read_fd, write_fd = os.pipe()
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message="This process .* is multi-threaded, use of fork.*",
                    category=DeprecationWarning,
                )
                child = os.fork()
            if child == 0:
                os.close(read_fd)
                results = bytearray()
                try:
                    try:
                        owner.snapshot()
                    except BaseException:
                        results.extend(b"1")
                    try:
                        driver.assert_current()
                    except BaseException:
                        results.extend(b"1")
                    os.write(write_fd, bytes(results))
                finally:
                    os.close(write_fd)
                    os._exit(0)
            os.close(write_fd)
            readable, _, _ = select.select((read_fd,), (), (), 3)
            if not readable:
                os.kill(child, signal.SIGKILL)
                os.waitpid(child, 0)
                pytest.fail("fork child deadlocked while invalidating V4.9B authority")
            assert os.read(read_fd, 2) == b"11"
            os.close(read_fd)
            _, status = os.waitpid(child, 0)
            assert os.waitstatus_to_exitcode(status) == 0
            assert owner.is_v49b_exact_profile
        transition = await owner.establish_v49b_handshake()
        assert transition.evidence is driver._handshake_evidence  # noqa: SLF001
        assert transition.owner_snapshot == transition.owner_snapshot_after
        assert (
            transition.pre_sample.boottime_after_ns
            < transition.handshake_started_monotonic_ns
            < transition.handshake_completed_monotonic_ns
            < transition.post_sample.boottime_before_ns
        )
        assert (
            transition.pre_sample.monotonic_clock_domain_id
            == transition.post_sample.monotonic_clock_domain_id
            == transition.owner_snapshot.monotonic_clock_domain_id
        )
        session = _driver_session(
            owner=owner,
            transition=transition,
            signer=Ed25519CheckpointSigner.generate(),
        )
        owner._assert_driver_derived_session_v49b(session)  # noqa: SLF001
        assert owner.bind_committed_v49b_handshake(transition, session) is None
        assert driver.state is TlsWebSocketDriverStateV49.WS_OPEN_BOUND
        with pytest.raises(LinuxSocketOwnerV4Error):
            owner.bind_committed_v49b_handshake(transition, session)
        assert driver.state is TlsWebSocketDriverStateV49.CLOSED
        with pytest.raises(RuntimeArtifactAuthorityV49BError):
            runtime_artifacts.assert_current()
    finally:
        owner.abort()
        await fake.close()


@run_async
async def test_v49b_owner_cancellation_aborts_driver_socket_and_measurement(
    tmp_path: Path,
) -> None:
    clock, _ = clock_fixture(tmp_path)
    wall_values = iter(T0 + timedelta(milliseconds=index) for index in range(64))
    clock._wall_clock = lambda: next(wall_values)  # noqa: SLF001
    material = _certificates()
    ca_path, cert_path, key_path = _write_certificates(tmp_path, material)
    fake = await _start_fake_server(
        _server_context(cert_path, key_path),
        stall_response=True,
    )
    store = _trust_store(ca_path, material)
    runtime_artifacts = _measured_runtime_artifacts(
        tls_trust_store_manifest_id=store.manifest.manifest_id,
        clock_source_policy_manifest_id=clock.policy.manifest_id,
    )
    driver = ExactTlsWebSocketDriverV49.from_measured_authority(
        trust_store=store,
        transport_policy=tls_transport_policy(),
        runtime_artifacts=runtime_artifacts,
    )
    sock = await _connected_socket(fake.address)
    owner = LinuxSocketOwnerV4._from_v49b_exact_profile_for_test(
        owned_socket=sock,
        governed_clock=clock,
        driver=driver,
    )
    try:
        task = asyncio.create_task(owner.establish_v49b_handshake())
        await asyncio.wait_for(fake.request_seen.wait(), timeout=2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert driver.state is TlsWebSocketDriverStateV49.CLOSED
        assert sock.fileno() == -1
        with pytest.raises(LinuxSocketOwnerV4Error):
            owner.snapshot()
        with pytest.raises(RuntimeArtifactAuthorityV49BError):
            runtime_artifacts.assert_current()
    finally:
        owner.abort()
        await fake.close()


@run_async
async def test_one_owner_lock_serializes_subscription_and_control(
    tmp_path: Path,
) -> None:
    owner, peer, driver = owner_fixture(tmp_path)
    driver.block_text = True
    try:
        text_task = asyncio.create_task(
            owner.send_exact_text_frame(b"subscribe", before_driver=lambda: None)
        )
        await driver.entered.wait()
        control_task = asyncio.create_task(
            owner.submit_permitted_chunks(
                permit=object(),
                ordered_chunks=(b"masked-control",),
                before_driver=lambda: None,
            )
        )
        await asyncio.sleep(0)
        assert driver.events == ["text"]

        driver.release.set()
        await text_task
        submitted = await control_task

        assert submitted == len(b"masked-control")
        assert driver.events == ["text", "control"]
        assert driver.sockets == [owner._socket, owner._socket]  # noqa: SLF001
    finally:
        owner.abort()
        peer.close()


def test_closed_socket_and_cross_thread_use_fail_closed(tmp_path: Path) -> None:
    owner, peer, _ = owner_fixture(tmp_path)
    errors: list[BaseException] = []

    def other_thread() -> None:
        try:
            owner.snapshot()
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=other_thread)
    thread.start()
    thread.join()
    assert isinstance(errors[0], LinuxSocketOwnerV4Error)

    owner._socket.close()  # noqa: SLF001 - adversarial descriptor loss
    with pytest.raises(LinuxSocketOwnerV4Error):
        owner.snapshot()
    owner.abort()
    owner.abort()
    peer.close()


@pytest.mark.skipif(not hasattr(os, "fork"), reason="fork is unavailable")
def test_forked_child_is_fenced_but_parent_owner_remains_live(tmp_path: Path) -> None:
    owner, peer, _ = owner_fixture(tmp_path)
    read_fd, write_fd = os.pipe()
    try:
        # This adversarial test deliberately forks the test runner to prove that
        # inherited authority is revoked. Keep Python's generic runner warning
        # scoped to this one intentional call; production code never forks.
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="This process .* is multi-threaded, use of fork.*",
                category=DeprecationWarning,
            )
            child = os.fork()
        if child == 0:
            os.close(read_fd)
            try:
                owner.snapshot()
            except BaseException:
                os.write(write_fd, b"fenced")
            else:
                os.write(write_fd, b"unsafe")
            os.close(write_fd)
            os._exit(0)
        os.close(write_fd)
        write_fd = -1
        result = os.read(read_fd, 16)
        _, status = os.waitpid(child, 0)
        assert os.waitstatus_to_exitcode(status) == 0
        assert result == b"fenced"
        assert owner.snapshot().socket_cookie_u64 != "0000000000000000"
    finally:
        if write_fd >= 0:
            os.close(write_fd)
        os.close(read_fd)
        owner.abort()
        peer.close()


def binding_for_owner(
    owner: LinuxSocketOwnerV4, *, signer: Ed25519CheckpointSigner
) -> TransportSocketOwnerBindingV4:
    snapshot = owner.snapshot()
    session_id = digest("session")
    nonce_sha256 = derive_transport_socket_lease_nonce_sha256(b"v47b-owner-nonce")
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


@dataclass
class FenceJournal:
    calls: int = 0

    def assert_transport_runtime_writer_fence(
        self, *, lease_token_sha256: str, generation: int
    ) -> None:
        assert lease_token_sha256 == digest("writer-fence")
        assert generation == 3
        self.calls += 1


def test_bound_control_derives_authority_and_requires_rich_clock(
    tmp_path: Path,
) -> None:
    owner, peer, _ = owner_fixture(tmp_path)
    signer = Ed25519CheckpointSigner.generate()
    binding = binding_for_owner(owner, signer=signer)
    journal = FenceJournal()
    try:
        mediator = PhysicalTransportControlMediatorV4.from_bound_transport_authority(
            journal=journal,  # type: ignore[arg-type]
            authority=owner,
            binding=binding,
            signer=signer,
        )

        sample = mediator._sample_clock()  # noqa: SLF001

        assert sample.monotonic_before_ns < sample.monotonic_after_ns
        assert mediator._writer is owner  # noqa: SLF001
        assert mediator._expected_socket_lease_id == binding.socket_lease_id  # noqa: SLF001
        assert mediator._expected_connection_generation == 2  # noqa: SLF001
    finally:
        owner.abort()
        peer.close()

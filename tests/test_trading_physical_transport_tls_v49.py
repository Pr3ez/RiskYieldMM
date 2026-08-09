from __future__ import annotations

import asyncio
import base64
import hashlib
import ipaddress
import platform
import socket
import ssl
import sysconfig
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from websockets.frames import Frame, Opcode
from websockets.utils import accept_key

from riskyieldmm.trading.canonical import sha256_digest
from riskyieldmm.trading.ledger_signing import Ed25519CheckpointSigner
from riskyieldmm.trading.operational_manifests_v4 import (
    TLS_TRUST_STORE_FORMAT,
    TLS_VERIFY_PURPOSE,
    RuntimeEnvironmentManifestV4,
    TlsTrustStoreManifestV4,
)
from riskyieldmm.trading.operational_runtime_artifacts_v49b import (
    PinnedTlsWebSocketRuntimeArtifactsV49B,
    RuntimeArtifactAuthorityV49BError,
    capture_current_tls_websocket_driver_policy_v49b,
)
from riskyieldmm.trading.physical_transport_control_v4 import RawIngressCommitV4
from riskyieldmm.trading.physical_transport_tls_v49 import (
    ExactTlsWebSocketDriverV49,
    PhysicalTlsWebSocketV49ProtocolError,
    PhysicalTlsWebSocketV49StateError,
    TlsWebSocketDriverStateV49,
    split_http_upgrade_prefix_v49,
)
from riskyieldmm.trading.physical_transport_v4 import (
    BYBIT_V5_LINEAR_ENDPOINT_V4,
    BYBIT_V5_LINEAR_TLS_SERVER_NAME_V4,
    BYBIT_V5_LINEAR_WEBSOCKET_PATH_V4,
    V4_TRANSPORT_SEND_DEADLINE_SECONDS,
    TransportSubscriptionPolicyV4,
    derive_transport_attestation_key_id,
)
from riskyieldmm.trading.tls_trust_store_v49 import (
    PinnedTlsTrustStoreV49,
    derive_tls_ca_der_set_root_v49,
)

T0 = datetime(2026, 7, 15, 12, tzinfo=timezone.utc)


def _digest(label: str) -> str:
    return sha256_digest({"label": label})


def _policy() -> TransportSubscriptionPolicyV4:
    signer = Ed25519CheckpointSigner.generate()
    return TransportSubscriptionPolicyV4(
        deployment_bundle_id=_digest("deployment"),
        collector_key_authorization_manifest_id=_digest("collector-key"),
        policy_name="RiskYieldMMBybitLinearSubscriptionV4_5",
        provider_id="BYBIT",
        venue_id="BYBIT",
        environment_id="MAINNET",
        authoritative_endpoint=BYBIT_V5_LINEAR_ENDPOINT_V4,
        tls_server_name=BYBIT_V5_LINEAR_TLS_SERVER_NAME_V4,
        port=443,
        websocket_path=BYBIT_V5_LINEAR_WEBSOCKET_PATH_V4,
        direct_connection_only=True,
        minimum_tls_version="TLSv1.3",
        certificate_verification_required=True,
        hostname_verification_required=True,
        websocket_http_status_required=101,
        websocket_accept_validation_required=True,
        allowed_websocket_extensions=(),
        allowed_subprotocols=(),
        single_topic_per_session=True,
        maximum_inflight_subscriptions=1,
        require_nonempty_echoed_request_id=True,
        maximum_request_id_length=36,
        send_deadline_seconds=V4_TRANSPORT_SEND_DEADLINE_SECONDS,
        ack_deadline_seconds=10,
        collector_attestation_key_id=derive_transport_attestation_key_id(
            signer.public_key_bytes
        ),
        collector_attestation_public_key_hex=signer.public_key_bytes.hex(),
        frozen_at=T0,
    )


@dataclass(frozen=True)
class _Certificates:
    ca_pem: bytes
    ca_der: bytes
    server_cert_pem: bytes
    server_key_pem: bytes


def _certificates(
    *, hostname: str = BYBIT_V5_LINEAR_TLS_SERVER_NAME_V4
) -> _Certificates:
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "RiskYieldMM V4.9 test CA")]
    )
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(T0 - timedelta(days=1))
        .not_valid_after(T0 + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=1), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    server_key = ec.generate_private_key(ec.SECP256R1())
    server_name = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "RiskYieldMM V4.9 fake server")]
    )
    server_cert = (
        x509.CertificateBuilder()
        .subject_name(server_name)
        .issuer_name(ca_name)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(T0 - timedelta(days=1))
        .not_valid_after(T0 + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName(hostname),
                    x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                ]
            ),
            critical=False,
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=True
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=True,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
            critical=False,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(server_key.public_key()),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    return _Certificates(
        ca_pem=ca_cert.public_bytes(serialization.Encoding.PEM),
        ca_der=ca_cert.public_bytes(serialization.Encoding.DER),
        server_cert_pem=server_cert.public_bytes(serialization.Encoding.PEM),
        server_key_pem=server_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
    )


def _write_certificates(
    tmp_path: Path, material: _Certificates
) -> tuple[Path, Path, Path]:
    ca_path = tmp_path / "ca.pem"
    cert_path = tmp_path / "server.pem"
    key_path = tmp_path / "server.key"
    ca_path.write_bytes(material.ca_pem)
    cert_path.write_bytes(material.server_cert_pem)
    key_path.write_bytes(material.server_key_pem)
    for path in (ca_path, cert_path, key_path):
        path.chmod(0o600)
    return ca_path, cert_path, key_path


def _trust_store(ca_path: Path, material: _Certificates) -> PinnedTlsTrustStoreV49:
    manifest = TlsTrustStoreManifestV4(
        bundle_format=TLS_TRUST_STORE_FORMAT,
        ca_bundle_sha256=hashlib.sha256(material.ca_pem).hexdigest(),
        ca_bundle_size_bytes=len(material.ca_pem),
        ca_certificate_count=1,
        ca_der_set_root_sha256=derive_tls_ca_der_set_root_v49((material.ca_der,)),
        openssl_verify_purpose=TLS_VERIFY_PURPOSE,
    )
    return PinnedTlsTrustStoreV49.open_verified(
        manifest=manifest,
        ca_bundle_path=ca_path,
    )


def _measured_runtime_artifacts(
    *,
    tls_trust_store_manifest_id: str,
    clock_source_policy_manifest_id: str,
) -> PinnedTlsWebSocketRuntimeArtifactsV49B:
    policy = capture_current_tls_websocket_driver_policy_v49b()
    python_executable = next(
        member
        for member in policy.runtime_artifacts
        if member.role == "PYTHON_EXECUTABLE"
    )
    runtime_environment = RuntimeEnvironmentManifestV4(
        python_implementation=policy.python_implementation,
        python_version=policy.python_version,
        python_executable_sha256=python_executable.sha256,
        platform_tag=sysconfig.get_platform(),
        openssl_version=policy.openssl_version,
        installed_distribution_root_sha256=(policy.installed_distribution_root_sha256),
        dependency_lock_manifest_id=_digest("dependency-lock"),
        collector_release_manifest_id=_digest("collector-release"),
        tls_trust_store_manifest_id=tls_trust_store_manifest_id,
        clock_source_policy_manifest_id=clock_source_policy_manifest_id,
        isolated_mode=True,
        user_site_enabled=False,
        tls_websocket_driver_policy=policy,
    )
    assert runtime_environment.python_implementation == platform.python_implementation()
    return PinnedTlsWebSocketRuntimeArtifactsV49B._open_verified_for_test(
        policy=policy,
        runtime_environment=runtime_environment,
    )


def _server_context(
    cert_path: Path, key_path: Path, *, tls13: bool = True
) -> ssl.SSLContext:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    if tls13:
        context.minimum_version = ssl.TLSVersion.TLSv1_3
        context.maximum_version = ssl.TLSVersion.TLSv1_3
    else:
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.maximum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(cert_path, key_path)
    return context


@dataclass
class _FakeServer:
    server: asyncio.AbstractServer
    application_reads: asyncio.Queue[bytes]
    request_seen: asyncio.Event
    writers: list[asyncio.StreamWriter]

    @property
    def address(self) -> tuple[str, int]:
        sockname = self.server.sockets[0].getsockname()
        return str(sockname[0]), int(sockname[1])

    async def close(self) -> None:
        self.server.close()
        await self.server.wait_closed()
        for writer in self.writers:
            writer.close()
        await asyncio.gather(
            *(writer.wait_closed() for writer in self.writers),
            return_exceptions=True,
        )


async def _start_fake_server(
    context: ssl.SSLContext,
    *,
    first_frame: bytes = b"",
    accept_valid: bool = True,
    stall_response: bool = False,
) -> _FakeServer:
    reads: asyncio.Queue[bytes] = asyncio.Queue()
    request_seen = asyncio.Event()
    writers: list[asyncio.StreamWriter] = []

    async def handler(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        writers.append(writer)
        try:
            request = await reader.readuntil(b"\r\n\r\n")
            request_seen.set()
            if stall_response:
                await asyncio.sleep(30)
                return
            key_lines = [
                line
                for line in request.split(b"\r\n")
                if line.lower().startswith(b"sec-websocket-key:")
            ]
            assert len(key_lines) == 1
            key = key_lines[0].split(b":", 1)[1].strip().decode("ascii")
            accepted = accept_key(key) if accept_valid else "invalid-accept"
            response = (
                b"HTTP/1.1 101 Switching Protocols\r\n"
                b"Upgrade: websocket\r\n"
                b"Connection: Upgrade\r\n"
                + f"Sec-WebSocket-Accept: {accepted}\r\n\r\n".encode("ascii")
            )
            writer.write(response + first_frame)
            await writer.drain()
            while True:
                item = await reader.read(65536)
                if not item:
                    break
                await reads.put(item)
        except (asyncio.IncompleteReadError, ConnectionError, ssl.SSLError):
            return
        finally:
            writer.close()

    server = await asyncio.start_server(
        handler,
        "127.0.0.1",
        0,
        ssl=context,
    )
    return _FakeServer(server, reads, request_seen, writers)


async def _connected_socket(address: tuple[str, int]) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setblocking(False)
    await asyncio.get_running_loop().sock_connect(sock, address)
    return sock


def _raw_record(pending) -> RawIngressCommitV4:
    encoded = tuple(base64.b64encode(item).decode("ascii") for item in pending.chunks)
    return RawIngressCommitV4(
        transport_subscription_policy_id=_digest("policy"),
        transport_session_id=_digest("session"),
        physical_scope_manifest_id=_digest("scope"),
        adapter_policy_id=_digest("adapter"),
        capture_partition_id=_digest("partition"),
        socket_lease_id=_digest("socket"),
        connection_generation=1,
        deployment_bundle_id=_digest("deployment"),
        writer_fence_token_sha256=_digest("fence"),
        writer_fence_generation=1,
        ingress_sequence=pending.ingress_sequence,
        raw_ingress_chunks_base64=encoded,
        raw_ingress_chunks_sha256=tuple(
            hashlib.sha256(item).hexdigest() for item in pending.chunks
        ),
        raw_ingress_batch_sha256=sha256_digest(
            {
                "domain": "RiskYieldMMExactOrderedDecryptedIngressChunksV4_5",
                "ordered_chunks_base64": list(encoded),
            }
        ),
        received_at=T0,
        monotonic_clock_domain_id=_digest("clock-domain"),
        received_monotonic_ns=1,
    )


def _decode_client_frame(data: bytes) -> tuple[int, bytes]:
    assert len(data) >= 6 and data[1] & 0x80
    length = data[1] & 0x7F
    cursor = 2
    if length == 126:
        length = int.from_bytes(data[cursor : cursor + 2], "big")
        cursor += 2
    elif length == 127:
        length = int.from_bytes(data[cursor : cursor + 8], "big")
        cursor += 8
    mask = data[cursor : cursor + 4]
    cursor += 4
    assert len(data) == cursor + length
    payload = bytes(
        value ^ mask[index % 4] for index, value in enumerate(data[cursor:])
    )
    return data[0] & 0x0F, payload


def test_http_upgrade_split_preserves_every_exact_byte() -> None:
    head = b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n\r\n"
    suffix = b"\x89\x03abc"
    for index in range(len(head)):
        assert split_http_upgrade_prefix_v49(head[:index]) is None
    assert split_http_upgrade_prefix_v49(head + suffix) == (head, suffix)
    assert split_http_upgrade_prefix_v49(b"") is None
    with pytest.raises(TypeError):
        split_http_upgrade_prefix_v49(bytearray(head))  # type: ignore[arg-type]


def test_direct_v49a_construction_is_never_measured_or_promotion_eligible(
    tmp_path: Path,
) -> None:
    material = _certificates()
    ca_path, _, _ = _write_certificates(tmp_path, material)
    driver = ExactTlsWebSocketDriverV49(
        trust_store=_trust_store(ca_path, material),
        transport_policy=_policy(),
    )
    try:
        assert driver.is_exact_profile
        assert not driver.is_v49b_measured_profile
        assert not driver.is_v49b_promotion_eligible
        assert driver.driver_policy_id is None
        assert driver.runtime_observation_sha256 is None
    finally:
        driver.abort()

    class DriverSubclass(ExactTlsWebSocketDriverV49):
        pass

    subclass_store = _trust_store(ca_path, material)
    try:
        with pytest.raises(TypeError, match="subclasses"):
            DriverSubclass(
                trust_store=subclass_store,
                transport_policy=_policy(),
            )
    finally:
        subclass_store.close()


def test_measured_driver_retains_exact_identities_and_closes_authority(
    tmp_path: Path,
) -> None:
    material = _certificates()
    ca_path, _, _ = _write_certificates(tmp_path, material)
    store = _trust_store(ca_path, material)
    authority = _measured_runtime_artifacts(
        tls_trust_store_manifest_id=store.manifest.manifest_id,
        clock_source_policy_manifest_id=_digest("clock-policy"),
    )
    driver = ExactTlsWebSocketDriverV49.from_measured_authority(
        trust_store=store,
        transport_policy=_policy(),
        runtime_artifacts=authority,
    )
    policy_id = authority.policy_id
    observation = authority.runtime_observation_sha256
    runtime_environment_id = authority.runtime_environment_manifest_id
    assert driver.is_v49b_measured_profile
    assert not driver.is_v49b_promotion_eligible
    assert driver.driver_policy_id == policy_id
    assert driver.runtime_observation_sha256 == observation
    assert driver.runtime_environment_manifest_id == runtime_environment_id

    driver.abort()
    with pytest.raises(RuntimeArtifactAuthorityV49BError):
        authority.assert_current()


def test_tls13_handshake_holds_coalesced_ping_until_raw_commit(tmp_path: Path) -> None:
    async def scenario() -> None:
        material = _certificates()
        ca_path, cert_path, key_path = _write_certificates(tmp_path, material)
        fake = await _start_fake_server(
            _server_context(cert_path, key_path),
            first_frame=Frame(Opcode.PING, b"probe").serialize(mask=False),
        )
        store = _trust_store(ca_path, material)
        driver = ExactTlsWebSocketDriverV49(
            trust_store=store, transport_policy=_policy()
        )
        sock = await _connected_socket(fake.address)
        try:
            evidence = await driver.handshake(sock)
            assert evidence.tls_version == "TLSv1.3"
            assert evidence.alpn_protocol is None
            assert evidence.websocket_http_status == 101
            assert evidence.websocket_accept_verified
            assert evidence.coalesced_post_upgrade_octets == 7
            assert driver.state is TlsWebSocketDriverStateV49.WS_OPEN_UNBOUND
            assert fake.application_reads.empty()

            pending = driver.bind_handshake_evidence(evidence)
            assert pending is not None
            assert driver.state is TlsWebSocketDriverStateV49.RAW_INGRESS_PENDING
            assert fake.application_reads.empty()
            raw = _raw_record(pending)
            parsed = driver.parse_durable_ingress(raw)
            assert [(item.opcode, item.payload) for item in parsed.frame_events] == [
                (int(Opcode.PING), b"probe")
            ]
            assert len(parsed.protocol_output_chunks) == 1
            opcode, payload = _decode_client_frame(parsed.protocol_output_chunks[0])
            assert opcode == int(Opcode.PONG)
            assert payload == b"probe"
            assert driver.state is TlsWebSocketDriverStateV49.PROTOCOL_OUTPUT_PENDING
            await asyncio.sleep(0.02)
            assert fake.application_reads.empty()
        finally:
            driver.abort()
            sock.close()
            await fake.close()

    asyncio.run(scenario())


def test_handshake_evidence_and_raw_ingress_are_one_shot(tmp_path: Path) -> None:
    async def scenario() -> None:
        material = _certificates()
        ca_path, cert_path, key_path = _write_certificates(tmp_path, material)
        fake = await _start_fake_server(_server_context(cert_path, key_path))
        driver = ExactTlsWebSocketDriverV49(
            trust_store=_trust_store(ca_path, material), transport_policy=_policy()
        )
        sock = await _connected_socket(fake.address)
        try:
            evidence = await driver.handshake(sock)
            assert driver.bind_handshake_evidence(evidence) is None
            assert driver.state is TlsWebSocketDriverStateV49.WS_OPEN_BOUND
            with pytest.raises(PhysicalTlsWebSocketV49StateError):
                driver.bind_handshake_evidence(evidence)
            with pytest.raises(PhysicalTlsWebSocketV49StateError):
                await driver.handshake(sock)
        finally:
            driver.abort()
            sock.close()
            await fake.close()

    asyncio.run(scenario())


def test_mismatched_raw_commit_fault_latches_before_parser_use(tmp_path: Path) -> None:
    async def scenario() -> None:
        material = _certificates()
        ca_path, cert_path, key_path = _write_certificates(tmp_path, material)
        ping = Frame(Opcode.PING, b"x").serialize(mask=False)
        fake = await _start_fake_server(
            _server_context(cert_path, key_path), first_frame=ping
        )
        driver = ExactTlsWebSocketDriverV49(
            trust_store=_trust_store(ca_path, material), transport_policy=_policy()
        )
        sock = await _connected_socket(fake.address)
        try:
            evidence = await driver.handshake(sock)
            pending = driver.bind_handshake_evidence(evidence)
            assert pending is not None
            wrong = replace(_raw_record(pending), ingress_sequence=2)
            with pytest.raises(PhysicalTlsWebSocketV49ProtocolError, match="differs"):
                driver.parse_durable_ingress(wrong)
            assert driver.state is TlsWebSocketDriverStateV49.FAULT_LATCHED
            assert fake.application_reads.empty()
        finally:
            driver.abort()
            sock.close()
            await fake.close()

    asyncio.run(scenario())


def test_multiple_automatic_outputs_are_held_in_exact_protocol_order(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        material = _certificates()
        ca_path, cert_path, key_path = _write_certificates(tmp_path, material)
        ingress = b"".join(
            (
                Frame(Opcode.PING, b"first").serialize(mask=False),
                Frame(Opcode.PING, b"second").serialize(mask=False),
            )
        )
        fake = await _start_fake_server(
            _server_context(cert_path, key_path), first_frame=ingress
        )
        driver = ExactTlsWebSocketDriverV49(
            trust_store=_trust_store(ca_path, material), transport_policy=_policy()
        )
        sock = await _connected_socket(fake.address)
        try:
            evidence = await driver.handshake(sock)
            pending = driver.bind_handshake_evidence(evidence)
            assert pending is not None
            parsed = driver.parse_durable_ingress(_raw_record(pending))
            assert [
                _decode_client_frame(item) for item in parsed.protocol_output_chunks
            ] == [
                (int(Opcode.PONG), b"first"),
                (int(Opcode.PONG), b"second"),
            ]
            assert driver.state is TlsWebSocketDriverStateV49.PROTOCOL_OUTPUT_PENDING
            await asyncio.sleep(0.02)
            assert fake.application_reads.empty()
        finally:
            driver.abort()
            sock.close()
            await fake.close()

    asyncio.run(scenario())


def test_subscription_text_is_exact_masked_client_frame(tmp_path: Path) -> None:
    async def scenario() -> None:
        material = _certificates()
        ca_path, cert_path, key_path = _write_certificates(tmp_path, material)
        fake = await _start_fake_server(_server_context(cert_path, key_path))
        driver = ExactTlsWebSocketDriverV49(
            trust_store=_trust_store(ca_path, material), transport_policy=_policy()
        )
        sock = await _connected_socket(fake.address)
        payload = b'{"args":["kline.1.BTCUSDT"],"op":"subscribe","req_id":"r1"}'
        try:
            evidence = await driver.handshake(sock)
            assert driver.bind_handshake_evidence(evidence) is None
            await driver.send_exact_text_frame(sock, payload)
            frame = await asyncio.wait_for(fake.application_reads.get(), timeout=1)
            opcode, decoded = _decode_client_frame(frame)
            assert opcode == int(Opcode.TEXT)
            assert decoded == payload
            assert driver.state is TlsWebSocketDriverStateV49.WS_OPEN_BOUND
        finally:
            driver.abort()
            sock.close()
            await fake.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("mode", ["bad-accept", "wrong-host", "untrusted", "tls12"])
def test_handshake_adversaries_fail_closed(tmp_path: Path, mode: str) -> None:
    async def scenario() -> None:
        server_material = _certificates(
            hostname=(
                "wrong.example"
                if mode == "wrong-host"
                else BYBIT_V5_LINEAR_TLS_SERVER_NAME_V4
            )
        )
        server_ca, cert_path, key_path = _write_certificates(tmp_path, server_material)
        client_material = _certificates() if mode == "untrusted" else server_material
        if mode == "untrusted":
            client_ca = tmp_path / "client-ca.pem"
            client_ca.write_bytes(client_material.ca_pem)
            client_ca.chmod(0o600)
        else:
            client_ca = server_ca
        fake = await _start_fake_server(
            _server_context(cert_path, key_path, tls13=mode != "tls12"),
            accept_valid=mode != "bad-accept",
        )
        driver = ExactTlsWebSocketDriverV49(
            trust_store=_trust_store(client_ca, client_material),
            transport_policy=_policy(),
        )
        sock = await _connected_socket(fake.address)
        try:
            with pytest.raises((ssl.SSLError, PhysicalTlsWebSocketV49ProtocolError)):
                await driver.handshake(sock)
            assert driver.state is TlsWebSocketDriverStateV49.FAULT_LATCHED
        finally:
            driver.abort()
            sock.close()
            await fake.close()

    asyncio.run(scenario())


def test_cancelled_handshake_fault_latches_and_cannot_resume(tmp_path: Path) -> None:
    async def scenario() -> None:
        material = _certificates()
        ca_path, cert_path, key_path = _write_certificates(tmp_path, material)
        fake = await _start_fake_server(
            _server_context(cert_path, key_path), stall_response=True
        )
        driver = ExactTlsWebSocketDriverV49(
            trust_store=_trust_store(ca_path, material), transport_policy=_policy()
        )
        sock = await _connected_socket(fake.address)
        try:
            task = asyncio.create_task(driver.handshake(sock))
            await asyncio.wait_for(fake.request_seen.wait(), timeout=1)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert driver.state is TlsWebSocketDriverStateV49.FAULT_LATCHED
            with pytest.raises(PhysicalTlsWebSocketV49StateError):
                await driver.handshake(sock)
        finally:
            driver.abort()
            sock.close()
            await fake.close()

    asyncio.run(scenario())

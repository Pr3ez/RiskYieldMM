from __future__ import annotations

import asyncio
import base64
import errno
import hashlib
import os
import socket
import ssl
import threading
from pathlib import Path
from typing import Any

import pytest
from websockets.frames import Opcode
from websockets.protocol import State

from riskyieldmm.trading import physical_transport_tls_v49 as tls_v49
from riskyieldmm.trading.canonical import sha256_digest
from riskyieldmm.trading.physical_transport_tls_v49 import (
    ExactTlsWebSocketDriverV49,
    PhysicalTlsWebSocketV49ProtocolError,
    PhysicalTlsWebSocketV49StateError,
    PreparedTlsCiphertextV49C,
    PreparedWebSocketWireV49C,
    TlsWebSocketDriverStateV49,
)
from tests.test_trading_physical_transport_tls_v49 import (
    _certificates,
    _connected_socket,
    _decode_client_frame,
    _policy,
    _server_context,
    _start_fake_server,
    _trust_store,
    _write_certificates,
)


def _masked_frame(opcode: int, payload: bytes) -> bytes:
    assert len(payload) < 126
    mask = b"\x01\x02\x03\x04"
    masked = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
    return bytes((0x80 | opcode, 0x80 | len(payload))) + mask + masked


def _masked_text_frame(payload: bytes) -> bytes:
    return _masked_frame(0x1, payload)


class _FakeProtocol:
    state = State.OPEN

    def __init__(self) -> None:
        self._pending: tuple[bytes, ...] = ()

    def send_text(self, payload: bytes) -> None:
        if self._pending:
            raise AssertionError("test protocol already has pending output")
        self._pending = (_masked_text_frame(payload),)

    def data_to_send(self) -> list[bytes]:
        result = list(self._pending)
        self._pending = ()
        return result


class _FakeOutgoingBio:
    def __init__(self) -> None:
        self._chunks: list[bytes] = []

    @property
    def pending(self) -> int:
        return sum(map(len, self._chunks))

    def append(self, chunk: bytes) -> None:
        self._chunks.append(chunk)

    def read(self) -> bytes:
        return self._chunks.pop(0)


class _FakeTls:
    def __init__(self, outgoing: _FakeOutgoingBio) -> None:
        self._outgoing = outgoing

    def write(self, plaintext: bytes) -> int:
        self._outgoing.append(b"tls13-record:" + plaintext)
        return len(plaintext)


class _WantReadTls:
    def write(self, _plaintext: bytes) -> int:
        raise ssl.SSLWantReadError()


class _ForbiddenSocket:
    def __getattribute__(self, name: str) -> Any:
        if name.startswith("__"):
            return object.__getattribute__(self, name)
        raise AssertionError(f"preparation touched socket attribute {name}")


class _ScriptedSocket:
    def __init__(self, owned: socket.socket, script: list[int | BaseException]) -> None:
        self.owned = owned
        self.script = list(script)
        self.send_calls: list[bytes] = []

    def fileno(self) -> int:
        return self.owned.fileno()

    def getblocking(self) -> bool:
        return self.owned.getblocking()

    def gettimeout(self) -> float | None:
        return self.owned.gettimeout()

    def getpeername(self) -> Any:
        return self.owned.getpeername()

    def send(self, suffix: memoryview) -> int:
        self.send_calls.append(bytes(suffix))
        if not self.script:
            raise BlockingIOError(errno.EAGAIN, "script exhausted")
        action = self.script.pop(0)
        if isinstance(action, BaseException):
            raise action
        return action


def _driver_harness() -> ExactTlsWebSocketDriverV49:
    driver = object.__new__(ExactTlsWebSocketDriverV49)
    driver._creator_pid = os.getpid()
    driver._creator_thread_id = threading.get_ident()
    driver._event_loop = None
    driver._actor_lock = asyncio.Lock()
    driver._state = TlsWebSocketDriverStateV49.WS_OPEN_BOUND
    driver._protocol = _FakeProtocol()
    outgoing = _FakeOutgoingBio()
    driver._outgoing = outgoing
    driver._tls = _FakeTls(outgoing)
    driver._pending_tls_ciphertext = b""
    driver._pending_tls_ciphertext_offset = 0
    driver._pending_protocol_output = ()
    driver._pending_send_eof = False
    driver._staged_outbound_sequence_v49c = 0
    driver._active_prepared_wire_v49c = None
    driver._active_prepared_wire_was_protocol_output_v49c = False
    driver._active_prepared_tls_v49c = None
    driver._active_prepared_tls_offset_v49c = 0
    driver._owned_socket = _ForbiddenSocket()
    driver._socket_fd = None
    driver._socket_stat = None
    driver._socket_peer = None
    return driver


def _bind_scripted_socket(
    driver: ExactTlsWebSocketDriverV49, scripted: _ScriptedSocket
) -> None:
    driver._owned_socket = scripted
    driver._socket_fd = scripted.fileno()
    stat_result = os.fstat(scripted.fileno())
    driver._socket_stat = (stat_result.st_dev, stat_result.st_ino)
    driver._socket_peer = scripted.getpeername()


async def _prepare(
    driver: ExactTlsWebSocketDriverV49, payload: bytes = b"subscribe"
) -> tuple[PreparedWebSocketWireV49C, PreparedTlsCiphertextV49C]:
    wire = await driver.prepare_exact_text_wire_v49c(payload)
    ciphertext = await driver.prepare_tls_ciphertext_v49c(wire)
    return wire, ciphertext


def _deadline_ns(seconds: float = 1.0) -> int:
    return tls_v49._boottime_ns() + int(seconds * 1_000_000_000)


def _fill_send_buffer(owned: socket.socket) -> None:
    payload = b"x" * 65_536
    while True:
        try:
            owned.send(payload)
        except BlockingIOError:
            return


def test_staged_artifacts_are_token_only() -> None:
    with pytest.raises(TypeError, match="driver-constructed"):
        PreparedWebSocketWireV49C(_token=object())
    with pytest.raises(TypeError, match="driver-constructed"):
        PreparedTlsCiphertextV49C(_token=object())


def test_wire_and_tls_preparation_are_socket_syscall_free_and_actor_hashed() -> None:
    async def scenario() -> None:
        driver = _driver_harness()
        payload = b"subscribe"
        wire = await driver.prepare_exact_text_wire_v49c(payload)
        assert driver.state is TlsWebSocketDriverStateV49.OUTBOUND_WIRE_PREPARED_V49C
        assert wire.logical_payload_sha256 == hashlib.sha256(payload).hexdigest()
        assert wire.wire_octets == sum(map(len, wire.ordered_wire_chunks))
        assert wire.wire_batch_sha256 == sha256_digest(
            {
                "domain": "RiskYieldMMActorOrderedProtocolOutputV4_9C",
                "ordered_chunks_base64": [
                    base64.b64encode(chunk).decode("ascii")
                    for chunk in wire.ordered_wire_chunks
                ],
            }
        )

        forged = object.__new__(PreparedWebSocketWireV49C)
        for field in PreparedWebSocketWireV49C.__dataclass_fields__:
            object.__setattr__(forged, field, getattr(wire, field))
        with pytest.raises(PhysicalTlsWebSocketV49StateError, match="exact active"):
            await driver.prepare_tls_ciphertext_v49c(forged)

        ciphertext = await driver.prepare_tls_ciphertext_v49c(wire)
        assert driver.state is TlsWebSocketDriverStateV49.TLS_CIPHERTEXT_PREPARED_V49C
        assert ciphertext.prepared_wire is wire
        assert ciphertext.plaintext_batch_sha256 == wire.wire_batch_sha256
        assert ciphertext.plaintext_octets == wire.wire_octets
        assert ciphertext.ciphertext_octets == len(ciphertext.exact_ciphertext)
        assert ciphertext.ciphertext_batch_sha256 == sha256_digest(
            {
                "domain": "RiskYieldMMActorOrderedTlsCiphertextV4_9C",
                "ordered_chunks_base64": [
                    base64.b64encode(chunk).decode("ascii")
                    for chunk in ciphertext.ordered_ciphertext_chunks
                ],
            }
        )
        with pytest.raises(PhysicalTlsWebSocketV49StateError, match="idle open FIFO"):
            await driver.prepare_exact_text_wire_v49c(b"second")

    asyncio.run(scenario())


def test_tls_preparation_that_needs_network_progress_fault_latches() -> None:
    async def scenario() -> None:
        driver = _driver_harness()
        wire = await driver.prepare_exact_text_wire_v49c(b"data")
        driver._tls = _WantReadTls()
        with pytest.raises(
            PhysicalTlsWebSocketV49ProtocolError, match="network progress"
        ):
            await driver.prepare_tls_ciphertext_v49c(wire)
        assert driver.state is TlsWebSocketDriverStateV49.FAULT_LATCHED
        with pytest.raises(PhysicalTlsWebSocketV49StateError, match="exact active"):
            await driver.prepare_tls_ciphertext_v49c(wire)

    asyncio.run(scenario())


def test_artifact_hash_and_length_are_revalidated_before_next_effect() -> None:
    async def scenario() -> None:
        driver = _driver_harness()
        wire = await driver.prepare_exact_text_wire_v49c(b"data")
        object.__setattr__(wire, "wire_octets", wire.wire_octets + 1)
        with pytest.raises(PhysicalTlsWebSocketV49ProtocolError, match="hashes"):
            await driver.prepare_tls_ciphertext_v49c(wire)
        assert driver.state is TlsWebSocketDriverStateV49.FAULT_LATCHED

        driver = _driver_harness()
        _wire, prepared = await _prepare(driver)
        object.__setattr__(
            prepared, "ciphertext_batch_sha256", hashlib.sha256(b"forged").hexdigest()
        )
        left, right = socket.socketpair()
        left.setblocking(False)
        right.setblocking(False)
        scripted = _ScriptedSocket(left, [1])
        _bind_scripted_socket(driver, scripted)
        try:
            with pytest.raises(PhysicalTlsWebSocketV49ProtocolError, match="hashes"):
                await driver.send_prepared_tls_ciphertext_once_v49c(
                    prepared.exact_ciphertext,
                    owned_socket=scripted,
                    prepared=prepared,
                    deadline_ns=_deadline_ns(),
                )
            assert scripted.send_calls == []
            assert driver.state is TlsWebSocketDriverStateV49.FAULT_LATCHED
        finally:
            left.close()
            right.close()

    asyncio.run(scenario())


def test_automatic_pong_uses_same_fifo_and_clears_only_after_full_submission() -> None:
    async def scenario() -> None:
        driver = _driver_harness()
        pong = _masked_frame(0xA, b"ping-one")
        second_pong = _masked_frame(0xA, b"ping-two")
        driver._pending_protocol_output = (pong, second_pong)
        driver._state = TlsWebSocketDriverStateV49.PROTOCOL_OUTPUT_PENDING
        wire = await driver.prepare_pending_protocol_output_wire_v49c((pong,))
        assert wire.logical_opcode == 0xA
        prepared = await driver.prepare_tls_ciphertext_v49c(wire)
        left, right = socket.socketpair()
        left.setblocking(False)
        right.setblocking(False)
        scripted = _ScriptedSocket(left, [prepared.ciphertext_octets])
        _bind_scripted_socket(driver, scripted)
        try:
            accepted = await driver.send_prepared_tls_ciphertext_once_v49c(
                prepared.exact_ciphertext,
                owned_socket=scripted,
                prepared=prepared,
                deadline_ns=_deadline_ns(),
            )
            assert accepted == prepared.ciphertext_octets
            assert driver._pending_protocol_output == (second_pong,)
            assert driver.state is TlsWebSocketDriverStateV49.PROTOCOL_OUTPUT_PENDING

            second_wire = await driver.prepare_pending_protocol_output_wire_v49c(
                (second_pong,)
            )
            assert second_wire.outbound_sequence == wire.outbound_sequence + 1
            second = await driver.prepare_tls_ciphertext_v49c(second_wire)
            scripted.script.append(second.ciphertext_octets)
            accepted = await driver.send_prepared_tls_ciphertext_once_v49c(
                second.exact_ciphertext,
                owned_socket=scripted,
                prepared=second,
                deadline_ns=_deadline_ns(),
            )
            assert accepted == second.ciphertext_octets
            assert driver._pending_protocol_output == ()
            assert driver.state is TlsWebSocketDriverStateV49.WS_OPEN_BOUND
        finally:
            left.close()
            right.close()

    asyncio.run(scenario())


def test_one_positive_send_advances_exact_suffix_and_completion_is_not_replayable() -> (
    None
):
    async def scenario() -> None:
        driver = _driver_harness()
        _wire, prepared = await _prepare(driver)
        ciphertext = prepared.exact_ciphertext
        assert len(ciphertext) > 2
        left, right = socket.socketpair()
        left.setblocking(False)
        right.setblocking(False)
        scripted = _ScriptedSocket(left, [2, len(ciphertext) - 2])
        _bind_scripted_socket(driver, scripted)
        try:
            accepted = await driver.send_prepared_tls_ciphertext_once_v49c(
                ciphertext,
                owned_socket=scripted,
                prepared=prepared,
                deadline_ns=_deadline_ns(),
            )
            assert accepted == 2
            assert driver._active_prepared_tls_offset_v49c == 2
            assert scripted.send_calls == [ciphertext]

            accepted = await driver.send_prepared_tls_ciphertext_once_v49c(
                ciphertext[2:],
                owned_socket=scripted,
                prepared=prepared,
                deadline_ns=_deadline_ns(),
            )
            assert accepted == len(ciphertext) - 2
            assert driver.state is TlsWebSocketDriverStateV49.WS_OPEN_BOUND
            assert driver._active_prepared_tls_v49c is None
            assert driver._active_prepared_wire_v49c is None

            with pytest.raises(
                PhysicalTlsWebSocketV49StateError, match="exact active staged"
            ):
                await driver.send_prepared_tls_ciphertext_once_v49c(
                    ciphertext,
                    owned_socket=scripted,
                    prepared=prepared,
                    deadline_ns=_deadline_ns(),
                )
            assert driver.state is TlsWebSocketDriverStateV49.FAULT_LATCHED
            assert scripted.send_calls == [ciphertext, ciphertext[2:]]
        finally:
            left.close()
            right.close()

    asyncio.run(scenario())


def test_would_block_retries_same_suffix_and_returns_first_positive_count() -> None:
    async def scenario() -> None:
        driver = _driver_harness()
        _wire, prepared = await _prepare(driver)
        ciphertext = prepared.exact_ciphertext
        left, right = socket.socketpair()
        left.setblocking(False)
        right.setblocking(False)
        scripted = _ScriptedSocket(
            left, [BlockingIOError(errno.EAGAIN, "not ready"), 3]
        )
        _bind_scripted_socket(driver, scripted)
        try:
            accepted = await driver.send_prepared_tls_ciphertext_once_v49c(
                ciphertext,
                owned_socket=scripted,
                prepared=prepared,
                deadline_ns=_deadline_ns(),
            )
            assert accepted == 3
            assert scripted.send_calls == [ciphertext, ciphertext]
            assert driver._active_prepared_tls_offset_v49c == 3
        finally:
            left.close()
            right.close()

    asyncio.run(scenario())


def test_wrong_suffix_fault_latches_before_socket_send() -> None:
    async def scenario() -> None:
        driver = _driver_harness()
        _wire, prepared = await _prepare(driver)
        left, right = socket.socketpair()
        left.setblocking(False)
        right.setblocking(False)
        scripted = _ScriptedSocket(left, [1])
        _bind_scripted_socket(driver, scripted)
        try:
            with pytest.raises(PhysicalTlsWebSocketV49ProtocolError, match="suffix"):
                await driver.send_prepared_tls_ciphertext_once_v49c(
                    b"not-the-retained-prefix",
                    owned_socket=scripted,
                    prepared=prepared,
                    deadline_ns=_deadline_ns(),
                )
            assert scripted.send_calls == []
            assert driver.state is TlsWebSocketDriverStateV49.FAULT_LATCHED
        finally:
            left.close()
            right.close()

    asyncio.run(scenario())


def test_would_block_obeys_absolute_deadline_without_claiming_progress() -> None:
    async def scenario() -> None:
        driver = _driver_harness()
        _wire, prepared = await _prepare(driver)
        left, right = socket.socketpair()
        left.setblocking(False)
        right.setblocking(False)
        _fill_send_buffer(left)
        scripted = _ScriptedSocket(left, [BlockingIOError(errno.EAGAIN, "not ready")])
        _bind_scripted_socket(driver, scripted)
        try:
            with pytest.raises(TimeoutError, match="CLOCK_BOOTTIME"):
                await driver.send_prepared_tls_ciphertext_once_v49c(
                    prepared.exact_ciphertext,
                    owned_socket=scripted,
                    prepared=prepared,
                    deadline_ns=_deadline_ns(0.025),
                )
            assert scripted.send_calls == [prepared.exact_ciphertext]
            assert driver._active_prepared_tls_offset_v49c == 0
            assert driver.state is TlsWebSocketDriverStateV49.FAULT_LATCHED
        finally:
            left.close()
            right.close()

    asyncio.run(scenario())


def test_staged_seams_drive_real_tls13_memory_bio_and_exact_websocket_wire(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        material = _certificates()
        ca_path, cert_path, key_path = _write_certificates(tmp_path, material)
        fake = await _start_fake_server(_server_context(cert_path, key_path))
        driver = ExactTlsWebSocketDriverV49(
            trust_store=_trust_store(ca_path, material), transport_policy=_policy()
        )
        sock = await _connected_socket(fake.address)
        payload = b'{"args":["kline.1.BTCUSDT"],"op":"subscribe","req_id":"v49c"}'
        try:
            evidence = await driver.handshake(sock)
            assert driver.bind_handshake_evidence(evidence) is None
            wire = await driver.prepare_exact_text_wire_v49c(payload)
            assert fake.application_reads.empty()
            prepared = await driver.prepare_tls_ciphertext_v49c(wire)
            assert prepared.exact_ciphertext
            assert fake.application_reads.empty()

            offset = 0
            while offset < prepared.ciphertext_octets:
                accepted = await driver.send_prepared_tls_ciphertext_once_v49c(
                    prepared.exact_ciphertext[offset:],
                    owned_socket=sock,
                    prepared=prepared,
                    deadline_ns=_deadline_ns(),
                )
                offset += accepted
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

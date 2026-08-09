from __future__ import annotations

import asyncio
import hashlib
import socket
import ssl
from pathlib import Path
from typing import Any

import pytest
from websockets.frames import Frame, Opcode

import riskyieldmm.trading.physical_transport_tls_v49 as tls_transport
from riskyieldmm.trading.canonical import sha256_digest
from riskyieldmm.trading.physical_transport_linux_v4 import (
    LinuxSocketOwnerV4,
    LinuxSocketOwnerV4Error,
    LinuxSocketOwnerV4UnsendablePostHandshakeOutput,
    OwnerUnsendableTlsPostHandshakeOutputV49E,
)
from riskyieldmm.trading.physical_transport_tls_v49 import (
    ExactTlsWebSocketDriverV49,
    PhysicalTlsWebSocketV49ProtocolError,
    PhysicalTlsWebSocketV49StateError,
    PhysicalTlsWebSocketV49UnsendablePostHandshakeOutput,
    TlsWebSocketDriverStateV49,
    UnsendableTlsPostHandshakeOutputV49E,
)
from tests.test_trading_physical_transport_linux_owner_v49c_staged import (
    _bound_owner,
)
from tests.test_trading_physical_transport_linux_owner_v49e_shutdown import (
    _advance_server_close_to_ws_closing,
)


async def _advance_through_successful_shut_wr(harness: Any) -> None:
    await _advance_server_close_to_ws_closing(harness)
    deadline_ns = harness.owner.monotonic_now_ns() + 10_000_000_000
    prepared = await harness.owner.prepare_local_close_notify_v49e(
        deadline_ns=deadline_ns
    )
    offset = 0
    while offset < prepared.ciphertext_octets:
        accepted = await harness.owner.send_prepared_tls_control_ciphertext_once_v49e(
            prepared.exact_ciphertext[offset:],
            prepared=prepared,
            deadline_ns=deadline_ns,
        )
        offset += accepted
    token = await harness.owner.prepare_tcp_write_shutdown_v49e(
        prepared,
        deadline_ns=deadline_ns,
    )
    result = await harness.owner.shutdown_tcp_write_v49e(
        token,
        deadline_ns=deadline_ns,
    )
    assert result.kernel_accepted
    assert result.error_code is None
    assert harness.driver.state is TlsWebSocketDriverStateV49.TLS_SHUTDOWN_V49E


def _copy_sealed_dataclass(value: Any) -> Any:
    copied = object.__new__(type(value))
    for field in type(value).__dataclass_fields__:
        object.__setattr__(copied, field, getattr(value, field))
    return copied


def _guard_owner_socket_send(
    monkeypatch: pytest.MonkeyPatch,
    owned_socket: socket.socket,
) -> list[bytes]:
    original_send = socket.socket.send
    attempted_payloads: list[bytes] = []

    def guarded_send(
        current: socket.socket, data: Any, *args: Any, **kwargs: Any
    ) -> int:
        if current is owned_socket:
            attempted_payloads.append(bytes(data))
            raise AssertionError("post-SHUT_WR owner socket send was attempted")
        return original_send(current, data, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "send", guarded_send)
    return attempted_payloads


def _script_shutdown_output(
    monkeypatch: pytest.MonkeyPatch,
    driver: ExactTlsWebSocketDriverV49,
    *,
    branch: str,
    payload: bytes,
) -> None:
    if branch == "preexisting":
        driver._outgoing.write(payload)  # noqa: SLF001
        return

    target_tls = driver._tls  # noqa: SLF001
    original_unwrap = ssl.SSLObject.unwrap

    def scripted_unwrap(current: ssl.SSLObject) -> Any:
        if current is not target_tls:
            return original_unwrap(current)
        driver._outgoing.write(payload)  # noqa: SLF001
        if branch == "want_read":
            raise ssl.SSLWantReadError(
                ssl.SSL_ERROR_WANT_READ, "scripted WANT_READ output"
            )
        if branch == "want_write":
            raise ssl.SSLWantWriteError(
                ssl.SSL_ERROR_WANT_WRITE, "scripted WANT_WRITE output"
            )
        if branch == "zero_return":
            raise ssl.SSLZeroReturnError(
                ssl.SSL_ERROR_ZERO_RETURN, "scripted ZERO_RETURN output"
            )
        if branch == "eof_error":
            raise ssl.SSLEOFError(ssl.SSL_ERROR_EOF, "scripted EOF output")
        if branch == "success":
            return None
        raise AssertionError(f"unsupported test branch: {branch}")

    monkeypatch.setattr(ssl.SSLObject, "unwrap", scripted_unwrap)


@pytest.mark.parametrize(
    "branch",
    [
        "preexisting",
        "want_read",
        "want_write",
        "zero_return",
        "eof_error",
        "success",
    ],
)
def test_post_shut_wr_tls_output_becomes_exact_negative_evidence_without_send(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    branch: str,
) -> None:
    async def scenario() -> None:
        close_frame = Frame(Opcode.CLOSE, b"").serialize(mask=False)
        harness = await _bound_owner(tmp_path, first_frame=close_frame)
        try:
            await _advance_through_successful_shut_wr(harness)
            owner_socket = harness.owner._socket  # noqa: SLF001
            session_id = harness.owner._v49b_bound_session_id  # noqa: SLF001
            kernel_socket_identity = (  # noqa: SLF001
                harness.owner._initial_snapshot.kernel_socket_identity
            )
            driver_nonce = (  # noqa: SLF001
                harness.driver._handshake_evidence.evidence_nonce_sha256
            )
            payload = f"post-shut-wr-{branch}".encode("ascii")
            attempted_sends = _guard_owner_socket_send(monkeypatch, owner_socket)
            _script_shutdown_output(
                monkeypatch,
                harness.driver,
                branch=branch,
                payload=payload,
            )

            with pytest.raises(
                LinuxSocketOwnerV4UnsendablePostHandshakeOutput
            ) as raised:
                await harness.owner.poll_tls_shutdown_v49e(timeout_seconds=1)

            owner_evidence = raised.value.evidence
            driver_evidence = owner_evidence.driver_evidence
            assert type(owner_evidence) is OwnerUnsendableTlsPostHandshakeOutputV49E
            assert type(driver_evidence) is UnsendableTlsPostHandshakeOutputV49E
            assert type(raised.value.__cause__) is (
                PhysicalTlsWebSocketV49UnsendablePostHandshakeOutput
            )
            assert raised.value.__cause__.evidence is driver_evidence
            assert driver_evidence.output_sequence == 1
            assert driver_evidence.driver_evidence_nonce_sha256 == driver_nonce
            assert (
                driver_evidence.ciphertext_sha256 == hashlib.sha256(payload).hexdigest()
            )
            assert driver_evidence.ciphertext_octets == len(payload)
            assert driver_evidence.unsendable_output_id == sha256_digest(
                {
                    "domain": "RiskYieldMMUnsendableTlsPostHandshakeOutputV4_9E",
                    "output_sequence": 1,
                    "driver_evidence_nonce_sha256": driver_nonce,
                    "ciphertext_sha256": hashlib.sha256(payload).hexdigest(),
                    "ciphertext_octets": len(payload),
                }
            )
            assert owner_evidence.transport_session_id == session_id
            assert owner_evidence.kernel_socket_identity == kernel_socket_identity
            assert owner_evidence.owner_unsendable_output_id == sha256_digest(
                {
                    "domain": ("RiskYieldMMOwnerUnsendableTlsPostHandshakeOutputV4_9E"),
                    "transport_session_id": session_id,
                    "kernel_socket_identity": kernel_socket_identity,
                    "driver_unsendable_output_id": (
                        driver_evidence.unsendable_output_id
                    ),
                    "driver_output_sequence": driver_evidence.output_sequence,
                    "driver_evidence_nonce_sha256": driver_nonce,
                    "ciphertext_sha256": hashlib.sha256(payload).hexdigest(),
                    "ciphertext_octets": len(payload),
                }
            )
            LinuxSocketOwnerV4._assert_owner_unsendable_tls_output_integrity_v49e(
                owner_evidence
            )
            copied_owner_evidence = _copy_sealed_dataclass(owner_evidence)
            with pytest.raises(LinuxSocketOwnerV4Error, match="copied, consumed"):
                copied_owner_evidence.consume_for_actor_v49e(
                    transport_session_id=session_id,
                    driver_evidence_nonce_sha256=driver_nonce,
                )
            copied_exception = LinuxSocketOwnerV4UnsendablePostHandshakeOutput.__new__(
                LinuxSocketOwnerV4UnsendablePostHandshakeOutput
            )
            copied_exception.evidence = owner_evidence
            with pytest.raises(LinuxSocketOwnerV4Error, match="capability pair"):
                copied_exception.consume_for_actor_v49e(
                    transport_session_id=session_id,
                    driver_evidence_nonce_sha256=driver_nonce,
                )
            assert (
                raised.value.consume_for_actor_v49e(
                    transport_session_id=session_id,
                    driver_evidence_nonce_sha256=driver_nonce,
                )
                is owner_evidence
            )
            with pytest.raises(LinuxSocketOwnerV4Error, match="capability pair"):
                raised.value.consume_for_actor_v49e(
                    transport_session_id=session_id,
                    driver_evidence_nonce_sha256=driver_nonce,
                )
            assert set(UnsendableTlsPostHandshakeOutputV49E.__dataclass_fields__) == {
                "output_sequence",
                "driver_evidence_nonce_sha256",
                "ciphertext_sha256",
                "ciphertext_octets",
                "unsendable_output_id",
            }
            assert not hasattr(driver_evidence, "exact_ciphertext")
            assert not hasattr(driver_evidence, "ordered_ciphertext_chunks")
            assert not hasattr(driver_evidence, "send")
            assert attempted_sends == []
            assert harness.driver._outgoing.pending == 0  # noqa: SLF001
            assert not harness.owner._closed  # noqa: SLF001
            assert harness.owner._v49e_terminal_io_fault_latched  # noqa: SLF001
            assert harness.driver.state is (
                TlsWebSocketDriverStateV49.TLS_SHUTDOWN_V49E
            )
            harness.owner.assert_same_owner(harness.owner._initial_snapshot)  # noqa: SLF001
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_unsendable_output_rejects_copies_forgeries_and_external_construction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        close_frame = Frame(Opcode.CLOSE, b"").serialize(mask=False)
        harness = await _bound_owner(tmp_path, first_frame=close_frame)
        try:
            await _advance_through_successful_shut_wr(harness)
            payload = b"identity-bound-post-shut-wr-output"
            harness.driver._outgoing.write(payload)  # noqa: SLF001
            attempted_sends = _guard_owner_socket_send(
                monkeypatch,
                harness.owner._socket,  # noqa: SLF001
            )
            with pytest.raises(
                PhysicalTlsWebSocketV49UnsendablePostHandshakeOutput
            ) as raised:
                await harness.driver.poll_tls_shutdown_v49e(
                    harness.owner._socket,
                    timeout_seconds=1,  # noqa: SLF001
                )
            driver_evidence = raised.value.evidence
            assert harness.driver.state is (
                TlsWebSocketDriverStateV49.TLS_SHUTDOWN_V49E
            )

            copied_driver = _copy_sealed_dataclass(driver_evidence)
            ExactTlsWebSocketDriverV49._assert_unsendable_tls_output_integrity_v49e(
                copied_driver
            )
            with pytest.raises(
                PhysicalTlsWebSocketV49StateError, match="exact retained"
            ):
                harness.driver._assert_active_unsendable_tls_output_v49e(  # noqa: SLF001
                    copied_driver
                )
            with pytest.raises(
                PhysicalTlsWebSocketV49StateError, match="exact retained"
            ):
                harness.owner._bind_unsendable_tls_output_v49e(  # noqa: SLF001
                    driver=harness.driver,
                    driver_evidence=copied_driver,
                )

            forged_driver = _copy_sealed_dataclass(driver_evidence)
            replacement = (
                "0" if driver_evidence.ciphertext_sha256[0] != "0" else "1"
            ) + driver_evidence.ciphertext_sha256[1:]
            object.__setattr__(forged_driver, "ciphertext_sha256", replacement)
            with pytest.raises(PhysicalTlsWebSocketV49ProtocolError, match="differs"):
                ExactTlsWebSocketDriverV49._assert_unsendable_tls_output_integrity_v49e(
                    forged_driver
                )

            owner_evidence = harness.owner._bind_unsendable_tls_output_v49e(  # noqa: SLF001
                driver=harness.driver,
                driver_evidence=driver_evidence,
            )
            forged_owner = _copy_sealed_dataclass(owner_evidence)
            object.__setattr__(forged_owner, "kernel_socket_identity", "0" * 64)
            with pytest.raises(LinuxSocketOwnerV4Error, match="differs"):
                LinuxSocketOwnerV4._assert_owner_unsendable_tls_output_integrity_v49e(
                    forged_owner
                )

            with pytest.raises(TypeError, match="driver-constructed"):
                UnsendableTlsPostHandshakeOutputV49E(_token=object())
            with pytest.raises(TypeError, match="driver-constructed"):
                PhysicalTlsWebSocketV49UnsendablePostHandshakeOutput(
                    _token=object(),
                    evidence=driver_evidence,
                    message="forged",
                )
            with pytest.raises(TypeError, match="owner-constructed"):
                OwnerUnsendableTlsPostHandshakeOutputV49E(_token=object())
            with pytest.raises(TypeError, match="owner-constructed"):
                LinuxSocketOwnerV4UnsendablePostHandshakeOutput(
                    _token=object(), evidence=owner_evidence
                )
            assert attempted_sends == []
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_unsendable_output_overflow_aborts_without_send_or_partial_capability(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        close_frame = Frame(Opcode.CLOSE, b"").serialize(mask=False)
        harness = await _bound_owner(tmp_path, first_frame=close_frame)
        try:
            await _advance_through_successful_shut_wr(harness)
            attempted_sends = _guard_owner_socket_send(
                monkeypatch,
                harness.owner._socket,  # noqa: SLF001
            )
            monkeypatch.setattr(
                tls_transport,
                "V49_MAXIMUM_TLS_OPERATION_CIPHERTEXT_BYTES",
                8,
            )
            harness.driver._outgoing.write(b"123456789")  # noqa: SLF001

            with pytest.raises(
                PhysicalTlsWebSocketV49ProtocolError, match="evidence bounds"
            ):
                await harness.owner.poll_tls_shutdown_v49e(timeout_seconds=1)

            assert attempted_sends == []
            assert harness.driver._outgoing.pending == 0  # noqa: SLF001
            assert (  # noqa: SLF001
                harness.driver._active_unsendable_tls_output_v49e is None
            )
            assert not harness.owner._closed  # noqa: SLF001
            assert harness.owner._v49e_terminal_io_fault_latched  # noqa: SLF001
            assert harness.driver.state is TlsWebSocketDriverStateV49.FAULT_LATCHED
            harness.owner.assert_same_owner(harness.owner._initial_snapshot)  # noqa: SLF001
        finally:
            await harness.close()

    asyncio.run(scenario())

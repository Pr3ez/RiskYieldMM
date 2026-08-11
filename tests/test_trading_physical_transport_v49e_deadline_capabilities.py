from __future__ import annotations

import asyncio
import copy
import errno
import hashlib
import os
import socket
import ssl
from pathlib import Path
from typing import Any

import pytest
from websockets.frames import Frame, Opcode

from riskyieldmm.trading.physical_transport_linux_v4 import (
    LinuxSocketOwnerV4DeadlineExpiredAfterProgressV49E,
    LinuxSocketOwnerV4DeadlineExpiredNoObservationV49E,
    LinuxSocketOwnerV4Error,
    LinuxSocketOwnerV4SendDeadlineExpiredNoKernelAcceptanceV49E,
    OwnerTlsShutdownObservationV49E,
    TcpWriteShutdownResultV49E,
    TcpWriteShutdownTokenV49E,
)
from riskyieldmm.trading.physical_transport_tls_v49 import (
    ExactTlsWebSocketDriverV49,
    PhysicalTlsWebSocketV49PostHandshakeOutputRequired,
    TlsShutdownObservationKindV49E,
    TlsWebSocketDriverStateV49,
)
from tests.test_trading_physical_transport_linux_owner_v49c_staged import (
    _bound_owner,
)
from tests.test_trading_physical_transport_linux_owner_v49d_ingress import (
    _owner_raw,
)
from tests.test_trading_physical_transport_linux_owner_v49e_shutdown import (
    _advance_server_close_to_ws_closing,
    _send_all_control,
)


def _copy_sealed_dataclass(value: Any) -> Any:
    copied = object.__new__(type(value))
    for field in type(value).__dataclass_fields__:
        object.__setattr__(copied, field, getattr(value, field))
    return copied


def _copy_sealed_exception(value: BaseException) -> BaseException:
    copied = type(value).__new__(type(value))
    BaseException.__init__(copied, *value.args)
    for field in type(value).__slots__:
        if field != "__weakref__":
            object.__setattr__(copied, field, getattr(value, field))
    return copied


async def _prepare_local_tls_close(harness: Any) -> tuple[Any, int]:
    deadline_ns = harness.owner.monotonic_now_ns() + 10_000_000_000
    await _advance_server_close_to_ws_closing(harness)
    prepared = await harness.owner.prepare_local_close_notify_v49e(
        deadline_ns=deadline_ns
    )
    await _send_all_control(harness.owner, prepared)
    return prepared, deadline_ns


async def _force_close_send_deadline_without_kernel_acceptance(
    harness: Any,
    prepared: Any,
    deadline_ns: int,
    monkeypatch: pytest.MonkeyPatch,
) -> LinuxSocketOwnerV4SendDeadlineExpiredNoKernelAcceptanceV49E:
    owner_socket = harness.owner._socket  # noqa: SLF001
    original_send = socket.socket.send
    send_calls = 0

    def would_block(current: socket.socket, *args: Any, **kwargs: Any) -> int:
        nonlocal send_calls
        if current is owner_socket:
            send_calls += 1
            raise BlockingIOError(errno.EAGAIN, "scripted would-block")
        return original_send(current, *args, **kwargs)

    async def deadline_while_waiting(
        current: ExactTlsWebSocketDriverV49,
        owned_socket: Any,
        *,
        deadline_ns: int,
    ) -> None:
        if current is harness.driver:
            raise TimeoutError("scripted writable deadline")
        raise AssertionError("unexpected driver in send deadline test")

    monkeypatch.setattr(socket.socket, "send", would_block)
    monkeypatch.setattr(
        ExactTlsWebSocketDriverV49,
        "_wait_socket_writable",
        deadline_while_waiting,
    )
    with pytest.raises(
        LinuxSocketOwnerV4SendDeadlineExpiredNoKernelAcceptanceV49E
    ) as captured:
        await harness.owner.send_prepared_tls_ciphertext_once_v49c(
            prepared.exact_ciphertext,
            prepared=prepared,
            deadline_ns=deadline_ns,
        )
    assert send_calls == 1
    return captured.value


def test_terminal_close_ingress_returns_retained_early_data_without_new_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        close_frame = Frame(Opcode.CLOSE, b"").serialize(mask=False)
        harness = await _bound_owner(tmp_path, first_frame=close_frame)
        try:
            assert harness.pending_raw is not None
            driver_calls = 0
            original = ExactTlsWebSocketDriverV49.read_terminal_close_ingress_v49e

            async def traced(
                current: ExactTlsWebSocketDriverV49,
                owned_socket: Any,
                *,
                deadline_ns: int,
            ) -> Any:
                nonlocal driver_calls
                if current is harness.driver:
                    driver_calls += 1
                return await original(
                    current,
                    owned_socket,
                    deadline_ns=deadline_ns,
                )

            monkeypatch.setattr(
                ExactTlsWebSocketDriverV49,
                "read_terminal_close_ingress_v49e",
                traced,
            )
            deadline_ns = harness.owner.monotonic_now_ns() + 2_000_000_000
            pending = await harness.owner.read_terminal_close_ingress_v49e(
                deadline_ns=deadline_ns
            )
            assert pending is harness.pending_raw
            assert b"".join(pending.chunks) == close_frame
            assert driver_calls == 0
            assert not harness.owner._closed  # noqa: SLF001
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_terminal_close_no_data_mints_one_shot_owner_bound_terminal_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        first_path = tmp_path / "first"
        second_path = tmp_path / "second"
        first_path.mkdir()
        second_path.mkdir()
        harness = await _bound_owner(first_path)
        other = await _bound_owner(second_path)
        try:
            seen_deadlines: list[int] = []
            readiness_deadlines: list[int] = []
            original = ExactTlsWebSocketDriverV49.read_terminal_close_ingress_v49e

            async def traced(
                current: ExactTlsWebSocketDriverV49,
                owned_socket: Any,
                *,
                deadline_ns: int,
            ) -> Any:
                if current is harness.driver:
                    seen_deadlines.append(deadline_ns)
                return await original(
                    current,
                    owned_socket,
                    deadline_ns=deadline_ns,
                )

            monkeypatch.setattr(
                ExactTlsWebSocketDriverV49,
                "read_terminal_close_ingress_v49e",
                traced,
            )

            async def immediate_timeout(
                current: ExactTlsWebSocketDriverV49,
                owned_socket: Any,
                *,
                deadline_ns: int,
                shutdown_socket_v49e: bool = False,
            ) -> None:
                if current is harness.driver:
                    readiness_deadlines.append(deadline_ns)
                    raise TimeoutError("scripted exact no-observation timeout")
                raise AssertionError("unexpected driver in deadline capability test")

            monkeypatch.setattr(
                ExactTlsWebSocketDriverV49,
                "_wait_socket_readable_v49e",
                immediate_timeout,
            )
            first_deadline_ns = harness.owner.monotonic_now_ns() + 5_000_000_000
            with pytest.raises(
                LinuxSocketOwnerV4DeadlineExpiredNoObservationV49E
            ) as captured:
                await harness.owner.read_terminal_close_ingress_v49e(
                    deadline_ns=first_deadline_ns
                )
            exc = captured.value
            assert seen_deadlines == [first_deadline_ns]
            assert readiness_deadlines == [first_deadline_ns]
            assert not harness.owner._closed  # noqa: SLF001
            assert harness.owner._v49e_terminal_io_fault_latched  # noqa: SLF001
            assert harness.driver.state is TlsWebSocketDriverStateV49.WS_OPEN_BOUND
            harness.owner.assert_same_owner(harness.owner._initial_snapshot)  # noqa: SLF001
            harness.driver.assert_current()
            assert exc.transport_session_id == harness.owner._v49b_bound_session_id  # noqa: SLF001
            assert exc.kernel_socket_identity == (  # noqa: SLF001
                harness.owner._initial_snapshot.kernel_socket_identity
            )
            assert exc.driver_evidence_nonce_sha256 == (  # noqa: SLF001
                harness.driver._handshake_evidence.evidence_nonce_sha256
            )
            assert exc.operation == "TERMINAL_CLOSE_INGRESS"
            assert exc.deadline_ns == first_deadline_ns

            context = {
                "transport_session_id": exc.transport_session_id,
                "driver_evidence_nonce_sha256": (exc.driver_evidence_nonce_sha256),
                "operation": exc.operation,
                "deadline_ns": exc.deadline_ns,
            }
            other_context = dict(context)
            other_context["transport_session_id"] = other.owner._v49b_bound_session_id  # noqa: SLF001
            other_context["driver_evidence_nonce_sha256"] = (  # noqa: SLF001
                other.driver._handshake_evidence.evidence_nonce_sha256
            )
            with pytest.raises(LinuxSocketOwnerV4Error, match="actor authority"):
                exc.consume_for_actor_v49e(**other_context)

            copied = _copy_sealed_exception(exc)
            with pytest.raises(LinuxSocketOwnerV4Error, match="copied, consumed"):
                copied.consume_for_actor_v49e(**context)  # type: ignore[attr-defined]
            for copier in (copy.copy, copy.deepcopy):
                try:
                    library_copy = copier(exc)
                except (TypeError, ValueError):
                    continue
                with pytest.raises(LinuxSocketOwnerV4Error, match="copied, consumed"):
                    library_copy.consume_for_actor_v49e(**context)

            if hasattr(os, "fork"):
                read_fd, write_fd = os.pipe()
                pid = os.fork()
                if pid == 0:
                    os.close(read_fd)
                    try:
                        exc.consume_for_actor_v49e(**context)
                    except LinuxSocketOwnerV4Error:
                        os.write(write_fd, b"rejected")
                    else:
                        os.write(write_fd, b"accepted")
                    finally:
                        os.close(write_fd)
                    os._exit(0)
                os.close(write_fd)
                child_result = os.read(read_fd, 32)
                os.close(read_fd)
                _, status = os.waitpid(pid, 0)
                assert os.waitstatus_to_exitcode(status) == 0
                assert child_result == b"rejected"

            assert exc.consume_for_actor_v49e(**context) is exc
            with pytest.raises(LinuxSocketOwnerV4Error, match="copied, consumed"):
                exc.consume_for_actor_v49e(**context)
            with pytest.raises(LinuxSocketOwnerV4Error, match="staged I/O"):
                await harness.owner.read_terminal_close_ingress_v49e(
                    deadline_ns=harness.owner.monotonic_now_ns() + 1_000_000_000
                )
        finally:
            await other.close()
            await harness.close()

    asyncio.run(scenario())


def test_local_close_send_deadline_preserves_local_origin_and_zero_acceptance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        harness = await _bound_owner(tmp_path)
        try:
            deadline_ns = harness.owner.monotonic_now_ns() + 5_000_000_000
            wire = await harness.owner.prepare_local_websocket_close_wire_v49e(
                deadline_ns=deadline_ns
            )
            prepared = await harness.owner.prepare_tls_ciphertext_v49c(
                wire,
                deadline_ns=deadline_ns,
            )
            exc = await _force_close_send_deadline_without_kernel_acceptance(
                harness,
                prepared,
                deadline_ns,
                monkeypatch,
            )
            assert exc.send_kind == "LOCAL_WEBSOCKET_CLOSE"
            assert exc.transport_sequence == prepared.outbound_sequence
            assert exc.ciphertext_batch_sha256 == prepared.ciphertext_batch_sha256
            assert exc.ciphertext_start_octet == 0
            assert exc.requested_octets == prepared.ciphertext_octets
            assert exc.would_block_count == 1
            assert not harness.owner._closed  # noqa: SLF001
            assert harness.owner._v49e_terminal_io_fault_latched  # noqa: SLF001
            harness.owner.assert_same_owner(harness.owner._initial_snapshot)  # noqa: SLF001
            harness.driver.assert_current()

            context = {
                "transport_session_id": exc.transport_session_id,
                "driver_evidence_nonce_sha256": (exc.driver_evidence_nonce_sha256),
                "deadline_ns": exc.deadline_ns,
                "ciphertext_batch_sha256": exc.ciphertext_batch_sha256,
                "ciphertext_start_octet": exc.ciphertext_start_octet,
                "requested_octets": exc.requested_octets,
            }
            copied = _copy_sealed_exception(exc)
            with pytest.raises(LinuxSocketOwnerV4Error, match="copied, consumed"):
                copied.consume_for_actor_v49e(**context)  # type: ignore[attr-defined]
            assert exc.consume_for_actor_v49e(**context) is exc
            with pytest.raises(LinuxSocketOwnerV4Error, match="copied, consumed"):
                exc.consume_for_actor_v49e(**context)
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_automatic_close_send_deadline_preserves_protocol_output_origin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        close_frame = Frame(Opcode.CLOSE, b"").serialize(mask=False)
        harness = await _bound_owner(tmp_path, first_frame=close_frame)
        try:
            pending = await harness.owner.read_decrypted_ingress_v49d(timeout_seconds=1)
            await harness.owner.adopt_durable_ingress_v49d(_owner_raw(harness, pending))
            parsed = await harness.owner.parse_next_durable_unit_v49d()
            assert parsed is not None
            assert parsed.frame_event is not None
            assert parsed.frame_event.opcode == int(Opcode.CLOSE)
            assert len(parsed.protocol_output_chunks) == 1
            wire = await harness.owner.prepare_pending_protocol_output_wire_v49c(
                parsed.protocol_output_chunks
            )
            assert wire.logical_opcode == int(Opcode.CLOSE)
            prepared = await harness.owner.prepare_tls_ciphertext_v49c(wire)
            deadline_ns = harness.owner.monotonic_now_ns() + 5_000_000_000
            exc = await _force_close_send_deadline_without_kernel_acceptance(
                harness,
                prepared,
                deadline_ns,
                monkeypatch,
            )
            assert exc.send_kind == "AUTOMATIC_WEBSOCKET_CLOSE"
            assert exc.transport_sequence == prepared.outbound_sequence
            assert exc.ciphertext_batch_sha256 == prepared.ciphertext_batch_sha256
            assert exc.ciphertext_start_octet == 0
            assert exc.requested_octets == prepared.ciphertext_octets
            assert exc.would_block_count == 1
            assert not harness.owner._closed  # noqa: SLF001
            assert harness.owner._v49e_terminal_io_fault_latched  # noqa: SLF001
            harness.owner.assert_same_owner(harness.owner._initial_snapshot)  # noqa: SLF001
            harness.driver.assert_current()
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_shutdown_polls_reuse_one_exact_absolute_deadline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        close_frame = Frame(Opcode.CLOSE, b"").serialize(mask=False)
        harness = await _bound_owner(tmp_path, first_frame=close_frame)
        try:
            prepared, command_deadline_ns = await _prepare_local_tls_close(harness)
            token = await harness.owner.prepare_tcp_write_shutdown_v49e(
                prepared,
                deadline_ns=command_deadline_ns,
            )
            result = await harness.owner.shutdown_tcp_write_v49e(
                token,
                deadline_ns=command_deadline_ns,
            )
            assert result.kernel_accepted

            seen: list[tuple[int | None, int | None]] = []
            readiness_deadlines: list[int] = []
            owner_recv_calls = 0
            original = ExactTlsWebSocketDriverV49.poll_tls_shutdown_v49e
            original_wait = ExactTlsWebSocketDriverV49._wait_socket_readable_v49e
            original_recv = socket.socket.recv
            owner_socket = harness.owner._socket  # noqa: SLF001

            async def traced(
                current: ExactTlsWebSocketDriverV49,
                owned_socket: Any,
                *,
                timeout_seconds: int | None = None,
                deadline_ns: int | None = None,
            ) -> Any:
                if current is harness.driver:
                    seen.append((timeout_seconds, deadline_ns))
                return await original(
                    current,
                    owned_socket,
                    timeout_seconds=timeout_seconds,
                    deadline_ns=deadline_ns,
                )

            monkeypatch.setattr(
                ExactTlsWebSocketDriverV49,
                "poll_tls_shutdown_v49e",
                traced,
            )

            async def first_stale_readiness(
                current: ExactTlsWebSocketDriverV49,
                owned_socket: Any,
                *,
                deadline_ns: int,
                shutdown_socket_v49e: bool = False,
            ) -> None:
                if current is harness.driver:
                    readiness_deadlines.append(deadline_ns)
                    if len(readiness_deadlines) == 1:
                        return
                await original_wait(
                    current,
                    owned_socket,
                    deadline_ns=deadline_ns,
                    shutdown_socket_v49e=shutdown_socket_v49e,
                )

            def first_eagain(
                current: socket.socket, *args: Any, **kwargs: Any
            ) -> bytes:
                nonlocal owner_recv_calls
                if current is owner_socket:
                    owner_recv_calls += 1
                    if owner_recv_calls == 1:
                        raise BlockingIOError
                return original_recv(current, *args, **kwargs)

            monkeypatch.setattr(
                ExactTlsWebSocketDriverV49,
                "_wait_socket_readable_v49e",
                first_stale_readiness,
            )
            monkeypatch.setattr(socket.socket, "recv", first_eagain)
            deadline_ns = harness.owner.monotonic_now_ns() + 10_000_000_000
            peer_close = await harness.owner.poll_tls_shutdown_v49e(
                deadline_ns=deadline_ns
            )
            tcp_eof = await harness.owner.poll_tls_shutdown_v49e(
                deadline_ns=deadline_ns
            )
            assert seen == [(None, deadline_ns), (None, deadline_ns)]
            assert len(readiness_deadlines) >= 2
            assert set(readiness_deadlines) == {deadline_ns}
            assert owner_recv_calls == len(readiness_deadlines)
            assert peer_close.observation_kind is (
                TlsShutdownObservationKindV49E.PEER_CLOSE_NOTIFY
            )
            assert tcp_eof.observation_kind is TlsShutdownObservationKindV49E.TCP_EOF
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_shutdown_want_read_cancellation_aborts_before_recv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        close_frame = Frame(Opcode.CLOSE, b"").serialize(mask=False)
        harness = await _bound_owner(tmp_path, first_frame=close_frame)
        try:
            prepared, command_deadline_ns = await _prepare_local_tls_close(harness)
            token = await harness.owner.prepare_tcp_write_shutdown_v49e(
                prepared,
                deadline_ns=command_deadline_ns,
            )
            result = await harness.owner.shutdown_tcp_write_v49e(
                token,
                deadline_ns=command_deadline_ns,
            )
            assert result.kernel_accepted
            harness.driver._peer_close_notify_received_v49e = False  # noqa: SLF001
            harness.driver._peer_close_notify_observation_emitted_v49e = (  # noqa: SLF001
                False
            )
            target_tls = harness.driver._tls  # noqa: SLF001
            original_unwrap = ssl.SSLObject.unwrap
            entered_readiness = asyncio.Event()
            owner_socket = harness.owner._socket  # noqa: SLF001
            original_recv = socket.socket.recv
            owner_recv_calls = 0

            def scripted_want_read(current: ssl.SSLObject) -> Any:
                if current is target_tls:
                    raise ssl.SSLWantReadError(
                        ssl.SSL_ERROR_WANT_READ,
                        "scripted shutdown WANT_READ",
                    )
                return original_unwrap(current)

            async def blocked_readiness(
                current: ExactTlsWebSocketDriverV49,
                owned_socket: Any,
                *,
                deadline_ns: int,
                shutdown_socket_v49e: bool = False,
            ) -> None:
                if current is harness.driver:
                    entered_readiness.set()
                    await asyncio.Future()
                raise AssertionError("unexpected driver in shutdown cancellation test")

            def counted_recv(
                current: socket.socket, *args: Any, **kwargs: Any
            ) -> bytes:
                nonlocal owner_recv_calls
                if current is owner_socket:
                    owner_recv_calls += 1
                return original_recv(current, *args, **kwargs)

            monkeypatch.setattr(ssl.SSLObject, "unwrap", scripted_want_read)
            monkeypatch.setattr(
                ExactTlsWebSocketDriverV49,
                "_wait_socket_readable_v49e",
                blocked_readiness,
            )
            monkeypatch.setattr(socket.socket, "recv", counted_recv)
            deadline_ns = harness.owner.monotonic_now_ns() + 10_000_000_000
            task = asyncio.create_task(
                harness.owner.poll_tls_shutdown_v49e(deadline_ns=deadline_ns)
            )
            await asyncio.wait_for(entered_readiness.wait(), timeout=1)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert owner_recv_calls == 0
            assert not harness.owner._closed  # noqa: SLF001
            assert harness.owner._v49e_terminal_io_fault_latched  # noqa: SLF001
            assert harness.driver.state is TlsWebSocketDriverStateV49.FAULT_LATCHED
            harness.owner._assert_terminal_socket_owner_v49e()  # noqa: SLF001
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_shutdown_partial_ciphertext_timeout_retains_operation_bound_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        close_frame = Frame(Opcode.CLOSE, b"").serialize(mask=False)
        harness = await _bound_owner(tmp_path, first_frame=close_frame)
        try:
            prepared, command_deadline_ns = await _prepare_local_tls_close(harness)
            token = await harness.owner.prepare_tcp_write_shutdown_v49e(
                prepared,
                deadline_ns=command_deadline_ns,
            )
            result = await harness.owner.shutdown_tcp_write_v49e(
                token,
                deadline_ns=command_deadline_ns,
            )
            assert result.kernel_accepted
            harness.driver._peer_close_notify_received_v49e = False  # noqa: SLF001
            harness.driver._peer_close_notify_observation_emitted_v49e = (  # noqa: SLF001
                False
            )
            target_tls = harness.driver._tls  # noqa: SLF001
            original_unwrap = ssl.SSLObject.unwrap
            partial_ciphertext = b"\x17\x03\x03\x00\x10"
            receive_calls = 0

            def want_read(current: ssl.SSLObject) -> Any:
                if current is target_tls:
                    raise ssl.SSLWantReadError(
                        ssl.SSL_ERROR_WANT_READ,
                        "scripted shutdown WANT_READ",
                    )
                return original_unwrap(current)

            async def partial_then_timeout(
                current: ExactTlsWebSocketDriverV49,
                owned_socket: Any,
                *,
                deadline_ns: int,
                shutdown_socket_v49e: bool = False,
            ) -> bytes:
                nonlocal receive_calls
                if current is harness.driver:
                    assert shutdown_socket_v49e
                    receive_calls += 1
                    if receive_calls == 1:
                        return partial_ciphertext
                    raise TimeoutError("scripted shutdown partial timeout")
                raise AssertionError("unexpected driver in shutdown partial test")

            monkeypatch.setattr(ssl.SSLObject, "unwrap", want_read)
            monkeypatch.setattr(
                ExactTlsWebSocketDriverV49,
                "_recv_after_readiness_v49e",
                partial_then_timeout,
            )
            with pytest.raises(
                LinuxSocketOwnerV4DeadlineExpiredAfterProgressV49E
            ) as captured:
                await harness.owner.poll_tls_shutdown_v49e(
                    deadline_ns=command_deadline_ns
                )
            exc = captured.value
            assert exc.operation == "TLS_SHUTDOWN_POLL"
            assert exc.deadline_ns == command_deadline_ns
            assert exc.ciphertext_octets_received == len(partial_ciphertext)
            assert (
                exc.ciphertext_sha256 == hashlib.sha256(partial_ciphertext).hexdigest()
            )
            assert not harness.owner._closed  # noqa: SLF001
            assert harness.owner._v49e_terminal_io_fault_latched  # noqa: SLF001
            assert harness.driver.state is TlsWebSocketDriverStateV49.FAULT_LATCHED
            harness.owner.assert_same_owner(harness.owner._initial_snapshot)  # noqa: SLF001
            context = {
                "transport_session_id": exc.transport_session_id,
                "driver_evidence_nonce_sha256": (exc.driver_evidence_nonce_sha256),
                "operation": exc.operation,
                "deadline_ns": exc.deadline_ns,
            }
            assert exc.consume_for_actor_v49e(**context) is exc
            with pytest.raises(LinuxSocketOwnerV4Error, match="copied, consumed"):
                exc.consume_for_actor_v49e(**context)
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_terminal_close_output_is_fatal_and_partial_timeout_is_typed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        output_path = tmp_path / "output"
        output_path.mkdir()
        output_harness = await _bound_owner(output_path)
        try:
            output_harness.driver._outgoing.write(  # noqa: SLF001
                b"unrepresented-terminal-output"
            )
            deadline_ns = output_harness.owner.monotonic_now_ns() + 2_000_000_000
            with pytest.raises(PhysicalTlsWebSocketV49PostHandshakeOutputRequired):
                await output_harness.owner.read_terminal_close_ingress_v49e(
                    deadline_ns=deadline_ns
                )
            assert not output_harness.owner._closed  # noqa: SLF001
            assert output_harness.owner._v49e_terminal_io_fault_latched  # noqa: SLF001
            assert output_harness.driver.state is (
                TlsWebSocketDriverStateV49.FAULT_LATCHED
            )
            output_harness.owner.assert_same_owner(  # noqa: SLF001
                output_harness.owner._initial_snapshot
            )
        finally:
            await output_harness.close()

        partial_path = tmp_path / "partial"
        partial_path.mkdir()
        partial_harness = await _bound_owner(partial_path)
        try:
            partial_ciphertext = b"\x17\x03\x03\x00\x10"
            receive_calls = 0

            async def partial_then_timeout(
                current: ExactTlsWebSocketDriverV49,
                owned_socket: Any,
                *,
                deadline_ns: int,
                shutdown_socket_v49e: bool = False,
            ) -> bytes:
                nonlocal receive_calls
                if current is partial_harness.driver:
                    receive_calls += 1
                    if receive_calls == 1:
                        return partial_ciphertext
                    raise TimeoutError("scripted partial TLS progress")
                raise AssertionError("unexpected driver in partial-ingress test")

            monkeypatch.setattr(
                ExactTlsWebSocketDriverV49,
                "_recv_after_readiness_v49e",
                partial_then_timeout,
            )
            deadline_ns = partial_harness.owner.monotonic_now_ns() + 2_000_000_000
            with pytest.raises(
                LinuxSocketOwnerV4DeadlineExpiredAfterProgressV49E
            ) as captured:
                await partial_harness.owner.read_terminal_close_ingress_v49e(
                    deadline_ns=deadline_ns
                )
            exc = captured.value
            assert exc.operation == "TERMINAL_CLOSE_INGRESS"
            assert exc.deadline_ns == deadline_ns
            assert exc.ciphertext_octets_received == len(partial_ciphertext)
            assert (
                exc.ciphertext_sha256 == hashlib.sha256(partial_ciphertext).hexdigest()
            )
            assert not partial_harness.owner._closed  # noqa: SLF001
            assert partial_harness.owner._v49e_terminal_io_fault_latched  # noqa: SLF001
            assert partial_harness.driver.state is (
                TlsWebSocketDriverStateV49.FAULT_LATCHED
            )
            partial_harness.owner.assert_same_owner(  # noqa: SLF001
                partial_harness.owner._initial_snapshot
            )
            context = {
                "transport_session_id": exc.transport_session_id,
                "driver_evidence_nonce_sha256": (exc.driver_evidence_nonce_sha256),
                "operation": exc.operation,
                "deadline_ns": exc.deadline_ns,
            }
            copied = _copy_sealed_exception(exc)
            with pytest.raises(LinuxSocketOwnerV4Error, match="copied, consumed"):
                copied.consume_for_actor_v49e(**context)  # type: ignore[attr-defined]
            assert exc.consume_for_actor_v49e(**context) is exc
            with pytest.raises(LinuxSocketOwnerV4Error, match="copied, consumed"):
                exc.consume_for_actor_v49e(**context)
        finally:
            await partial_harness.close()

    asyncio.run(scenario())


def test_terminal_close_cancellation_before_recv_aborts_without_consumption(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        harness = await _bound_owner(tmp_path)
        try:
            entered_readiness = asyncio.Event()
            owner_socket = harness.owner._socket  # noqa: SLF001
            original_recv = socket.socket.recv
            owner_recv_calls = 0

            async def blocked_readiness(
                current: ExactTlsWebSocketDriverV49,
                owned_socket: Any,
                *,
                deadline_ns: int,
                shutdown_socket_v49e: bool = False,
            ) -> None:
                if current is harness.driver:
                    entered_readiness.set()
                    await asyncio.Future()
                raise AssertionError("unexpected driver in cancellation test")

            def counted_recv(
                current: socket.socket, *args: Any, **kwargs: Any
            ) -> bytes:
                nonlocal owner_recv_calls
                if current is owner_socket:
                    owner_recv_calls += 1
                return original_recv(current, *args, **kwargs)

            monkeypatch.setattr(
                ExactTlsWebSocketDriverV49,
                "_wait_socket_readable_v49e",
                blocked_readiness,
            )
            monkeypatch.setattr(socket.socket, "recv", counted_recv)
            deadline_ns = harness.owner.monotonic_now_ns() + 2_000_000_000
            task = asyncio.create_task(
                harness.owner.read_terminal_close_ingress_v49e(deadline_ns=deadline_ns)
            )
            await asyncio.wait_for(entered_readiness.wait(), timeout=1)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert owner_recv_calls == 0
            assert not harness.owner._closed  # noqa: SLF001
            assert harness.owner._v49e_terminal_io_fault_latched  # noqa: SLF001
            assert harness.driver.state is TlsWebSocketDriverStateV49.FAULT_LATCHED
            harness.owner.assert_same_owner(harness.owner._initial_snapshot)  # noqa: SLF001
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_owner_terminal_capabilities_are_exact_identity_and_one_shot(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        close_frame = Frame(Opcode.CLOSE, b"").serialize(mask=False)
        harness = await _bound_owner(tmp_path, first_frame=close_frame)
        try:
            prepared, command_deadline_ns = await _prepare_local_tls_close(harness)
            session_id = harness.owner._v49b_bound_session_id  # noqa: SLF001
            driver_nonce = (  # noqa: SLF001
                harness.driver._handshake_evidence.evidence_nonce_sha256
            )
            token = await harness.owner.prepare_tcp_write_shutdown_v49e(
                prepared,
                deadline_ns=command_deadline_ns,
            )
            assert type(token) is TcpWriteShutdownTokenV49E
            copied_token = _copy_sealed_dataclass(token)
            token_context = {
                "transport_session_id": session_id,
                "tls_control_sequence": prepared.control_sequence,
                "tls_ciphertext_batch_sha256": prepared.ciphertext_batch_sha256,
                "tls_ciphertext_octets": prepared.ciphertext_octets,
                "shutdown_deadline_monotonic_ns": command_deadline_ns,
            }
            with pytest.raises(LinuxSocketOwnerV4Error, match="copied, consumed"):
                copied_token.consume_for_actor_v49e(**token_context)
            assert token.consume_for_actor_v49e(**token_context) is token
            with pytest.raises(LinuxSocketOwnerV4Error, match="copied, consumed"):
                token.consume_for_actor_v49e(**token_context)

            result = await harness.owner.shutdown_tcp_write_v49e(
                token,
                deadline_ns=command_deadline_ns,
            )
            assert type(result) is TcpWriteShutdownResultV49E
            copied_result = _copy_sealed_dataclass(result)
            with pytest.raises(LinuxSocketOwnerV4Error, match="copied, consumed"):
                copied_result.consume_for_actor_v49e(
                    transport_session_id=session_id,
                    shutdown_token=token,
                )
            assert (
                result.consume_for_actor_v49e(
                    transport_session_id=session_id,
                    shutdown_token=token,
                )
                is result
            )
            with pytest.raises(LinuxSocketOwnerV4Error, match="copied, consumed"):
                result.consume_for_actor_v49e(
                    transport_session_id=session_id,
                    shutdown_token=token,
                )

            observation = await harness.owner.poll_tls_shutdown_v49e(timeout_seconds=2)
            assert type(observation) is OwnerTlsShutdownObservationV49E
            copied_observation = _copy_sealed_dataclass(observation)
            observation_context = {
                "transport_session_id": session_id,
                "driver_evidence_nonce_sha256": driver_nonce,
            }
            with pytest.raises(LinuxSocketOwnerV4Error, match="copied, consumed"):
                copied_observation.consume_for_actor_v49e(**observation_context)
            assert (
                observation.consume_for_actor_v49e(**observation_context) is observation
            )
            with pytest.raises(LinuxSocketOwnerV4Error, match="copied, consumed"):
                observation.consume_for_actor_v49e(**observation_context)
        finally:
            await harness.close()

    asyncio.run(scenario())

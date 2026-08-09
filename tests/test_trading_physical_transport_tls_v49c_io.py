from __future__ import annotations

import asyncio
import errno
import inspect
import os
import socket
import threading
from types import SimpleNamespace
from typing import Any

import pytest

from riskyieldmm.trading import physical_transport_tls_v49 as tls_v49
from riskyieldmm.trading.physical_transport_control_v4 import (
    V4_CONTROL_MAXIMUM_INGRESS_BYTES,
)
from riskyieldmm.trading.physical_transport_tls_v49 import (
    ExactTlsWebSocketDriverV49,
    PhysicalTlsWebSocketV49ProtocolError,
    PhysicalTlsWebSocketV49StateError,
    RawSocketSendOutcomeV49,
    TlsWebSocketDriverStateV49,
)


class _ScriptedSocket:
    """Socket facade used only after bypassing the production exact-type bind."""

    def __init__(
        self, owned: socket.socket, script: list[int | BaseException] | None = None
    ) -> None:
        self.owned = owned
        self.script = [] if script is None else list(script)
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
            raise BlockingIOError(errno.EAGAIN, "scripted would-block")
        action = self.script.pop(0)
        if isinstance(action, BaseException):
            raise action
        return action


def _driver_harness(owned: _ScriptedSocket) -> ExactTlsWebSocketDriverV49:
    driver = object.__new__(ExactTlsWebSocketDriverV49)
    driver._actor_lock = asyncio.Lock()
    driver._owned_socket = owned
    driver._socket_fd = owned.fileno()
    stat_result = os.fstat(owned.fileno())
    driver._socket_stat = (stat_result.st_dev, stat_result.st_ino)
    driver._socket_peer = owned.getpeername()
    driver._pending_tls_ciphertext = b""
    driver._pending_tls_ciphertext_offset = 0
    return driver


def _deadline_ns(seconds: float = 1.0) -> int:
    return tls_v49._boottime_ns() + int(seconds * 1_000_000_000)


def _fill_send_buffer(owned: socket.socket) -> None:
    payload = b"x" * 65_536
    while True:
        try:
            owned.send(payload)
        except BlockingIOError:
            return


def test_partial_send_records_every_count_and_immutable_suffix_offset() -> None:
    async def scenario() -> None:
        left, right = socket.socketpair()
        left.setblocking(False)
        right.setblocking(False)
        scripted = _ScriptedSocket(left, [2, 1, 3])
        driver = _driver_harness(scripted)
        attempts = []
        results = []
        try:
            async with driver._actor_lock:
                trace = await driver._send_raw_ciphertext(
                    scripted,
                    b"abcdef",
                    initial_suffix_offset=0,
                    deadline_ns=_deadline_ns(),
                    before_attempt=attempts.append,
                    after_result=results.append,
                )
            assert scripted.send_calls == [b"abcdef", b"cdef", b"def"]
            assert [item.suffix_offset for item in attempts] == [0, 2, 3]
            assert [item.suffix_octets for item in attempts] == [6, 4, 3]
            assert [item.kernel_accepted_octets for item in results] == [2, 1, 3]
            assert all(
                item.outcome is RawSocketSendOutcomeV49.KERNEL_ACCEPTED
                for item in results
            )
            assert trace.positive_send_offsets == (0, 2, 3)
            assert trace.positive_send_counts == (2, 1, 3)
            assert trace.final_suffix_offset == 6
            assert trace.attempt_count == 3
        finally:
            left.close()
            right.close()

    asyncio.run(scenario())


def test_would_block_waits_for_readiness_without_advancing_suffix() -> None:
    async def scenario() -> None:
        left, right = socket.socketpair()
        left.setblocking(False)
        right.setblocking(False)
        scripted = _ScriptedSocket(
            left,
            [BlockingIOError(errno.EAGAIN, "not ready"), 4],
        )
        driver = _driver_harness(scripted)
        results = []
        try:
            async with driver._actor_lock:
                trace = await driver._send_raw_ciphertext(
                    scripted,
                    b"data",
                    initial_suffix_offset=0,
                    deadline_ns=_deadline_ns(),
                    after_result=results.append,
                )
            assert scripted.send_calls == [b"data", b"data"]
            assert [item.outcome for item in results] == [
                RawSocketSendOutcomeV49.WOULD_BLOCK,
                RawSocketSendOutcomeV49.KERNEL_ACCEPTED,
            ]
            assert [item.next_suffix_offset for item in results] == [0, 4]
            assert trace.would_block_count == 1
            assert trace.positive_send_counts == (4,)
        finally:
            left.close()
            right.close()

    asyncio.run(scenario())


def test_absolute_boottime_deadline_times_out_while_descriptor_is_not_writable() -> (
    None
):
    async def scenario() -> None:
        left, right = socket.socketpair()
        left.setblocking(False)
        right.setblocking(False)
        _fill_send_buffer(left)
        scripted = _ScriptedSocket(left)
        driver = _driver_harness(scripted)
        results = []
        try:
            async with driver._actor_lock:
                with pytest.raises(TimeoutError, match="CLOCK_BOOTTIME"):
                    await driver._send_raw_ciphertext(
                        scripted,
                        b"blocked",
                        initial_suffix_offset=0,
                        deadline_ns=_deadline_ns(0.025),
                        after_result=results.append,
                    )
            assert len(scripted.send_calls) == 1
            assert [item.outcome for item in results] == [
                RawSocketSendOutcomeV49.WOULD_BLOCK
            ]
            assert results[0].next_suffix_offset == 0
        finally:
            left.close()
            right.close()

    asyncio.run(scenario())


def test_before_callback_failure_prevents_the_socket_syscall() -> None:
    class JournalFailure(RuntimeError):
        pass

    async def scenario() -> None:
        left, right = socket.socketpair()
        left.setblocking(False)
        right.setblocking(False)
        scripted = _ScriptedSocket(left, [4])
        driver = _driver_harness(scripted)

        def fail_before(_attempt: Any) -> None:
            raise JournalFailure("before journal unavailable")

        try:
            async with driver._actor_lock:
                with pytest.raises(JournalFailure, match="before journal"):
                    await driver._send_raw_ciphertext(
                        scripted,
                        b"data",
                        initial_suffix_offset=0,
                        deadline_ns=_deadline_ns(),
                        before_attempt=fail_before,
                    )
            assert scripted.send_calls == []
        finally:
            left.close()
            right.close()

    asyncio.run(scenario())


def test_before_callback_cannot_run_past_absolute_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        left, right = socket.socketpair()
        left.setblocking(False)
        right.setblocking(False)
        scripted = _ScriptedSocket(left, [4])
        driver = _driver_harness(scripted)
        boottime = [100]
        monkeypatch.setattr(tls_v49, "_boottime_ns", lambda: boottime[0])

        def expire_during_journal(_attempt: Any) -> None:
            boottime[0] = 201

        try:
            async with driver._actor_lock:
                with pytest.raises(TimeoutError, match="CLOCK_BOOTTIME"):
                    await driver._send_raw_ciphertext(
                        scripted,
                        b"data",
                        initial_suffix_offset=0,
                        deadline_ns=200,
                        before_attempt=expire_during_journal,
                    )
            assert scripted.send_calls == []
        finally:
            left.close()
            right.close()

    asyncio.run(scenario())


def test_after_callback_failure_retains_positive_kernel_progress_and_suffix() -> None:
    class JournalFailure(RuntimeError):
        pass

    async def scenario() -> None:
        left, right = socket.socketpair()
        left.setblocking(False)
        right.setblocking(False)
        scripted = _ScriptedSocket(left, [2])
        driver = _driver_harness(scripted)
        driver._pending_tls_ciphertext = b"data"
        seen = []

        def fail_after(result: Any) -> None:
            seen.append(result)
            raise JournalFailure("result journal unavailable")

        try:
            async with driver._actor_lock:
                with pytest.raises(JournalFailure, match="result journal"):
                    await driver._flush_tls_output(
                        scripted,
                        deadline_ns=_deadline_ns(),
                        after_send_result=fail_after,
                    )
            assert len(seen) == 1
            assert seen[0].outcome is RawSocketSendOutcomeV49.KERNEL_ACCEPTED
            assert seen[0].kernel_accepted_octets == 2
            assert seen[0].next_suffix_offset == 2
            assert driver._pending_tls_ciphertext == b"data"
            assert driver._pending_tls_ciphertext_offset == 2
            assert scripted.send_calls == [b"data"]
        finally:
            left.close()
            right.close()

    asyncio.run(scenario())


def test_cancellation_before_writable_notification_never_retries() -> None:
    async def scenario() -> None:
        left, right = socket.socketpair()
        left.setblocking(False)
        right.setblocking(False)
        _fill_send_buffer(left)
        scripted = _ScriptedSocket(left)
        driver = _driver_harness(scripted)
        driver._pending_tls_ciphertext = b"cancel"
        waiting = asyncio.Event()

        def after(result: Any) -> None:
            if result.outcome is RawSocketSendOutcomeV49.WOULD_BLOCK:
                waiting.set()

        async def run_send() -> None:
            async with driver._actor_lock:
                await driver._flush_tls_output(
                    scripted,
                    deadline_ns=_deadline_ns(),
                    after_send_result=after,
                )

        try:
            task = asyncio.create_task(run_send())
            await asyncio.wait_for(waiting.wait(), timeout=1)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert len(scripted.send_calls) == 1
            assert driver._pending_tls_ciphertext == b"cancel"
            assert driver._pending_tls_ciphertext_offset == 0
        finally:
            left.close()
            right.close()

    asyncio.run(scenario())


def test_cancellation_after_real_readiness_never_enters_next_syscall() -> None:
    async def scenario() -> None:
        left, right = socket.socketpair()
        left.setblocking(False)
        right.setblocking(False)
        scripted = _ScriptedSocket(
            left,
            [2, BlockingIOError(errno.EAGAIN, "not ready"), 4],
        )
        driver = _driver_harness(scripted)
        driver._pending_tls_ciphertext = b"cancel"
        original_wait = driver._wait_socket_writable
        readiness_observed = asyncio.Event()
        hold_after_readiness = asyncio.Event()

        async def controlled_wait(
            owned_socket: socket.socket, *, deadline_ns: int
        ) -> None:
            await original_wait(owned_socket, deadline_ns=deadline_ns)
            readiness_observed.set()
            await hold_after_readiness.wait()

        driver._wait_socket_writable = controlled_wait

        async def run_send() -> None:
            async with driver._actor_lock:
                await driver._flush_tls_output(
                    scripted,
                    deadline_ns=_deadline_ns(),
                )

        try:
            task = asyncio.create_task(run_send())
            await asyncio.wait_for(readiness_observed.wait(), timeout=1)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert scripted.send_calls == [b"cancel", b"ncel"]
            assert driver._pending_tls_ciphertext == b"cancel"
            assert driver._pending_tls_ciphertext_offset == 2
        finally:
            left.close()
            right.close()

    asyncio.run(scenario())


def test_descriptor_replacement_in_before_callback_is_rejected_pre_syscall() -> None:
    async def scenario() -> None:
        left, right = socket.socketpair()
        replacement, replacement_peer = socket.socketpair()
        for item in (left, right, replacement, replacement_peer):
            item.setblocking(False)
        scripted = _ScriptedSocket(left, [4])
        driver = _driver_harness(scripted)

        def replace_descriptor(_attempt: Any) -> None:
            os.dup2(replacement.fileno(), left.fileno())

        try:
            async with driver._actor_lock:
                with pytest.raises(
                    PhysicalTlsWebSocketV49StateError,
                    match="descriptor was replaced",
                ):
                    await driver._send_raw_ciphertext(
                        scripted,
                        b"data",
                        initial_suffix_offset=0,
                        deadline_ns=_deadline_ns(),
                        before_attempt=replace_descriptor,
                    )
            assert scripted.send_calls == []
        finally:
            left.close()
            right.close()
            replacement.close()
            replacement_peer.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("invalid_count", [0, -1, True, 99, None])
def test_zero_or_invalid_socket_send_count_is_rejected(invalid_count: Any) -> None:
    async def scenario() -> None:
        left, right = socket.socketpair()
        left.setblocking(False)
        right.setblocking(False)
        scripted = _ScriptedSocket(left, [invalid_count])
        driver = _driver_harness(scripted)
        results = []
        try:
            async with driver._actor_lock:
                with pytest.raises(
                    PhysicalTlsWebSocketV49ProtocolError,
                    match="zero or invalid",
                ):
                    await driver._send_raw_ciphertext(
                        scripted,
                        b"data",
                        initial_suffix_offset=0,
                        deadline_ns=_deadline_ns(),
                        after_result=results.append,
                    )
            assert len(results) == 1
            assert results[0].outcome is RawSocketSendOutcomeV49.INVALID_COUNT
            assert results[0].next_suffix_offset == 0
        finally:
            left.close()
            right.close()

    asyncio.run(scenario())


def test_established_raw_batch_stops_at_commit_bound_without_dropping_tail() -> None:
    class BufferedPlaintext:
        def __init__(self, data: bytes) -> None:
            self.data = data

        def pending(self) -> int:
            return len(self.data)

        def read(self, maximum: int) -> bytes:
            result = self.data[:maximum]
            self.data = self.data[maximum:]
            return result

    async def scenario() -> None:
        left, right = socket.socketpair()
        left.setblocking(False)
        right.setblocking(False)
        scripted = _ScriptedSocket(left, [1])
        driver = _driver_harness(scripted)
        driver._creator_pid = os.getpid()
        driver._creator_thread_id = threading.get_ident()
        driver._event_loop = None
        driver._state = TlsWebSocketDriverStateV49.WS_OPEN_BOUND
        driver._tls = BufferedPlaintext(b"b" * 10_000)
        driver._handshake_evidence = SimpleNamespace(evidence_nonce_sha256="0" * 64)
        driver._pending_raw = None
        driver._ingress_sequence = 0

        async def first_plaintext(
            _owned_socket: socket.socket, *, deadline_ns: int
        ) -> bytes:
            del deadline_ns
            return b"a" * 60_000

        async def no_output(
            _owned_socket: socket.socket, *, deadline_ns: int, **_kwargs: Any
        ) -> None:
            del deadline_ns

        driver.assert_current = lambda: None
        driver._read_plaintext_chunk = first_plaintext
        driver._flush_tls_output = no_output
        try:
            pending = await driver.read_decrypted_ingress(scripted, timeout_seconds=1)
            assert tls_v49.V49_MAXIMUM_POST_UPGRADE_PENDING_BYTES == (
                V4_CONTROL_MAXIMUM_INGRESS_BYTES
            )
            assert pending.total_octets == V4_CONTROL_MAXIMUM_INGRESS_BYTES
            assert tuple(map(len, pending.chunks)) == (60_000, 5_536)
            assert driver._tls.pending() == 4_464
        finally:
            left.close()
            right.close()

    asyncio.run(scenario())


def test_transport_module_contains_no_sock_sendall_path() -> None:
    assert "sock_sendall" not in inspect.getsource(tls_v49)

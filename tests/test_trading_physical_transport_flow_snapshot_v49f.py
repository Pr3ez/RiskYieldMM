from __future__ import annotations

import asyncio
import os
import sys
import threading
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path
from typing import Any

import pytest
from websockets.frames import Frame, Opcode

from riskyieldmm.trading import physical_transport_linux_v4 as linux_v4
from riskyieldmm.trading.canonical import CanonicalizationError
from riskyieldmm.trading.physical_transport_linux_v4 import (
    LinuxSocketTransportFlowSnapshotV49F,
)
from riskyieldmm.trading.physical_transport_tls_v49 import (
    ExactTlsWebSocketDriverV49,
    PendingRawIngressV49,
    PhysicalTlsWebSocketV49StateError,
    PreparedTlsCiphertextV49C,
    PreparedTlsControlCiphertextV49E,
    TlsWebSocketDriverFlowSnapshotV49F,
    TlsWebSocketDriverStateV49,
)
from tests.test_trading_physical_transport_linux_owner_v49c_staged import (
    _bound_owner,
)


class _PendingBio:
    def __init__(self, pending: int) -> None:
        self.pending = pending


class _PendingTls:
    def __init__(self, pending: int) -> None:
        self._pending = pending

    def pending(self) -> int:
        return self._pending


def _pending_raw(*chunks: bytes) -> PendingRawIngressV49:
    pending = object.__new__(PendingRawIngressV49)
    object.__setattr__(pending, "driver_evidence_nonce_sha256", "1" * 64)
    object.__setattr__(pending, "ingress_sequence", 1)
    object.__setattr__(pending, "chunks", chunks)
    object.__setattr__(pending, "total_octets", sum(map(len, chunks)))
    return pending


def _prepared_tls(*chunks: bytes) -> PreparedTlsCiphertextV49C:
    prepared = object.__new__(PreparedTlsCiphertextV49C)
    object.__setattr__(prepared, "ordered_ciphertext_chunks", chunks)
    object.__setattr__(prepared, "ciphertext_octets", sum(map(len, chunks)))
    return prepared


def _prepared_control(*chunks: bytes) -> PreparedTlsControlCiphertextV49E:
    prepared = object.__new__(PreparedTlsControlCiphertextV49E)
    object.__setattr__(prepared, "ordered_ciphertext_chunks", chunks)
    object.__setattr__(prepared, "ciphertext_octets", sum(map(len, chunks)))
    return prepared


def _driver_harness() -> ExactTlsWebSocketDriverV49:
    driver = object.__new__(ExactTlsWebSocketDriverV49)
    driver._creator_pid = os.getpid()  # noqa: SLF001
    driver._creator_thread_id = threading.get_ident()  # noqa: SLF001
    driver._event_loop = asyncio.get_running_loop()  # noqa: SLF001
    driver._actor_lock = asyncio.Lock()  # noqa: SLF001
    driver._handshake_evidence_bound = True  # noqa: SLF001
    driver._coalesced_tail = ()  # noqa: SLF001
    driver._state = (  # noqa: SLF001
        TlsWebSocketDriverStateV49.TLS_CIPHERTEXT_PREPARED_V49C
    )
    driver._incoming = _PendingBio(7)  # noqa: SLF001
    driver._outgoing = _PendingBio(11)  # noqa: SLF001
    driver._tls = _PendingTls(13)  # noqa: SLF001
    driver._pending_raw = _pending_raw(b"r", b"aw")  # noqa: SLF001
    driver._durable_ingress_buffer_v49d = b"\x81\x00"  # noqa: SLF001
    driver._pending_protocol_output = (b"pong-a", b"pong-b")  # noqa: SLF001
    driver._pending_send_eof = False  # noqa: SLF001
    driver._active_prepared_wire_v49c = None  # noqa: SLF001
    driver._pending_tls_ciphertext = b""  # noqa: SLF001
    driver._pending_tls_ciphertext_offset = 0  # noqa: SLF001
    driver._active_prepared_tls_v49c = _prepared_tls(  # noqa: SLF001
        b"staged-",
        b"ciphertext",
    )
    driver._active_prepared_tls_offset_v49c = 3  # noqa: SLF001
    driver._active_prepared_tls_control_v49e = None  # noqa: SLF001
    driver._active_prepared_tls_control_offset_v49e = 0  # noqa: SLF001
    return driver


def _empty_driver_flow(**changes: Any) -> TlsWebSocketDriverFlowSnapshotV49F:
    values: dict[str, Any] = {
        "driver_state": TlsWebSocketDriverStateV49.WS_OPEN_BOUND,
        "memory_bio_incoming_pending_octets": 0,
        "memory_bio_outgoing_pending_octets": 0,
        "ssl_plaintext_pending_octets": 0,
        "pending_raw_chunks": 0,
        "pending_raw_octets": 0,
        "durable_ingress_buffer_octets": 0,
        "has_complete_durable_unit": False,
        "protocol_output_chunks": 0,
        "protocol_output_octets": 0,
        "pending_send_eof": False,
        "staged_websocket_wire_chunks": 0,
        "staged_websocket_wire_octets": 0,
        "pending_tls_ciphertext_octets": 0,
        "remaining_pending_tls_ciphertext_octets": 0,
        "staged_tls_ciphertext_octets": 0,
        "remaining_staged_tls_ciphertext_octets": 0,
        "staged_tls_control_ciphertext_octets": 0,
        "remaining_staged_tls_control_ciphertext_octets": 0,
    }
    values.update(changes)
    return TlsWebSocketDriverFlowSnapshotV49F(**values)


def test_v49f_flow_snapshot_contracts_are_exact_immutable_and_count_only() -> None:
    driver_flow = _empty_driver_flow()
    snapshot = LinuxSocketTransportFlowSnapshotV49F(
        kernel_socket_identity="2" * 64,
        effective_so_rcvbuf_octets=4096,
        effective_so_sndbuf_octets=8192,
        siocinq_queued_octets=3,
        siocoutq_queued_octets=5,
        driver_flow=driver_flow,
    )

    assert type(driver_flow) is TlsWebSocketDriverFlowSnapshotV49F
    assert type(snapshot) is LinuxSocketTransportFlowSnapshotV49F
    assert all(
        "capability" not in field.name and "content" not in field.name
        for field in fields(driver_flow) + fields(snapshot)
    )
    assert all(
        not isinstance(getattr(driver_flow, field.name), bytes)
        for field in fields(driver_flow)
    )
    assert all(
        not isinstance(getattr(snapshot, field.name), bytes)
        for field in fields(snapshot)
    )
    with pytest.raises(FrozenInstanceError):
        snapshot.siocinq_queued_octets = 6  # type: ignore[misc]
    with pytest.raises(CanonicalizationError, match="exact integer"):
        replace(driver_flow, ssl_plaintext_pending_octets=True)
    with pytest.raises(CanonicalizationError, match="pending RAW"):
        replace(driver_flow, pending_raw_chunks=1)
    with pytest.raises(CanonicalizationError, match="bounded FIFO"):
        replace(driver_flow, has_complete_durable_unit=True)
    with pytest.raises(CanonicalizationError, match="retained ciphertext total"):
        replace(
            driver_flow,
            staged_tls_ciphertext_octets=4,
            remaining_staged_tls_ciphertext_octets=5,
        )
    with pytest.raises(CanonicalizationError, match="exact TlsWebSocket"):
        LinuxSocketTransportFlowSnapshotV49F(
            kernel_socket_identity="2" * 64,
            effective_so_rcvbuf_octets=4096,
            effective_so_sndbuf_octets=8192,
            siocinq_queued_octets=0,
            siocoutq_queued_octets=0,
            driver_flow=object(),  # type: ignore[arg-type]
        )


def test_v49f_driver_snapshot_counts_each_retained_lane_under_actor_lock() -> None:
    async def scenario() -> None:
        driver = _driver_harness()
        staged = driver._active_prepared_tls_v49c  # noqa: SLF001
        assert type(staged) is PreparedTlsCiphertextV49C

        await driver._actor_lock.acquire()  # noqa: SLF001
        blocked = asyncio.create_task(driver.transport_flow_snapshot_v49f())
        await asyncio.sleep(0)
        assert not blocked.done()
        driver._actor_lock.release()  # noqa: SLF001
        snapshot = await blocked

        assert snapshot.driver_state is (
            TlsWebSocketDriverStateV49.TLS_CIPHERTEXT_PREPARED_V49C
        )
        assert snapshot.memory_bio_incoming_pending_octets == 7
        assert snapshot.memory_bio_outgoing_pending_octets == 11
        assert snapshot.ssl_plaintext_pending_octets == 13
        assert snapshot.pending_raw_chunks == 2
        assert snapshot.pending_raw_octets == 3
        assert snapshot.durable_ingress_buffer_octets == 2
        assert snapshot.has_complete_durable_unit
        assert snapshot.protocol_output_chunks == 2
        assert snapshot.protocol_output_octets == len(b"pong-apong-b")
        assert not snapshot.pending_send_eof
        assert snapshot.staged_websocket_wire_chunks == 0
        assert snapshot.staged_websocket_wire_octets == 0
        assert snapshot.pending_tls_ciphertext_octets == 0
        assert snapshot.remaining_pending_tls_ciphertext_octets == 0
        assert snapshot.staged_tls_ciphertext_octets == staged.ciphertext_octets
        assert snapshot.remaining_staged_tls_ciphertext_octets == (
            staged.ciphertext_octets - 3
        )
        assert snapshot.staged_tls_control_ciphertext_octets == 0

        driver._active_prepared_tls_v49c = None  # noqa: SLF001
        driver._active_prepared_tls_offset_v49c = 0  # noqa: SLF001
        driver._pending_tls_ciphertext = b"pending-ciphertext"  # noqa: SLF001
        driver._pending_tls_ciphertext_offset = 4  # noqa: SLF001
        driver._state = TlsWebSocketDriverStateV49.WS_OPEN_BOUND  # noqa: SLF001
        pending_snapshot = await driver.transport_flow_snapshot_v49f()
        assert pending_snapshot.pending_tls_ciphertext_octets == len(
            b"pending-ciphertext"
        )
        assert pending_snapshot.remaining_pending_tls_ciphertext_octets == (
            len(b"pending-ciphertext") - 4
        )

        driver._pending_tls_ciphertext = b""  # noqa: SLF001
        driver._pending_tls_ciphertext_offset = 0  # noqa: SLF001
        control = _prepared_control(b"tls-", b"control")
        driver._active_prepared_tls_control_v49e = control  # noqa: SLF001
        driver._active_prepared_tls_control_offset_v49e = 2  # noqa: SLF001
        driver._state = (  # noqa: SLF001
            TlsWebSocketDriverStateV49.TLS_CONTROL_CIPHERTEXT_PREPARED_V49E
        )
        control_snapshot = await driver.transport_flow_snapshot_v49f()
        assert control_snapshot.staged_tls_control_ciphertext_octets == (
            control.ciphertext_octets
        )
        assert control_snapshot.remaining_staged_tls_control_ciphertext_octets == (
            control.ciphertext_octets - 2
        )

    asyncio.run(scenario())


def test_v49f_driver_snapshot_never_binds_or_accepts_precommit_driver() -> None:
    async def scenario() -> None:
        driver = _driver_harness()
        driver._event_loop = None  # noqa: SLF001
        driver._handshake_evidence_bound = False  # noqa: SLF001
        driver._state = TlsWebSocketDriverStateV49.WS_OPEN_UNBOUND  # noqa: SLF001
        driver._coalesced_tail = (b"already-observed-unbound",)  # noqa: SLF001

        with pytest.raises(
            PhysicalTlsWebSocketV49StateError,
            match="already-bound event loop",
        ):
            await driver.transport_flow_snapshot_v49f()

        assert driver._event_loop is None  # noqa: SLF001
        assert driver._coalesced_tail == (b"already-observed-unbound",)  # noqa: SLF001

    asyncio.run(scenario())


def test_v49f_linux_snapshot_is_io_locked_owner_sealed_and_uses_queue_ioctls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        frame = Frame(Opcode.TEXT, b"flow-snapshot").serialize(mask=False)
        harness = await _bound_owner(tmp_path, first_frame=frame)
        try:
            owner = harness.owner
            expected_rcvbuf = owner._socket.getsockopt(  # noqa: SLF001
                linux_v4.socket.SOL_SOCKET,
                linux_v4.socket.SO_RCVBUF,
            )
            expected_sndbuf = owner._socket.getsockopt(  # noqa: SLF001
                linux_v4.socket.SOL_SOCKET,
                linux_v4.socket.SO_SNDBUF,
            )
            observed_requests: list[int] = []
            queue_values = {
                linux_v4._SIOCINQ: 123,  # noqa: SLF001
                linux_v4._SIOCOUTQ: 45,  # noqa: SLF001
            }
            original_ioctl = linux_v4.fcntl.ioctl

            def fake_ioctl(
                fd: int,
                request: int,
                *args: Any,
            ) -> Any:
                if request not in queue_values:
                    return original_ioctl(fd, request, *args)
                assert len(args) == 2
                buffer, mutate_flag = args
                assert fd == owner._socket.fileno()  # noqa: SLF001
                assert type(buffer) is bytearray and len(buffer) == 4
                assert mutate_flag is True
                observed_requests.append(request)
                buffer[:] = queue_values[request].to_bytes(
                    4,
                    byteorder=sys.byteorder,
                    signed=True,
                )
                return 0

            monkeypatch.setattr(linux_v4.fcntl, "ioctl", fake_ioctl)

            def forbidden_full_currentness_rehash() -> None:
                raise AssertionError(
                    "count-only observation invoked full driver currentness"
                )

            monkeypatch.setattr(
                harness.driver,
                "assert_current",
                forbidden_full_currentness_rehash,
            )
            await owner._io_lock.acquire()  # noqa: SLF001
            blocked = asyncio.create_task(owner.transport_flow_snapshot_v49f())
            await asyncio.sleep(0)
            assert not blocked.done()
            assert observed_requests == []
            owner._io_lock.release()  # noqa: SLF001
            snapshot = await blocked

            assert type(snapshot) is LinuxSocketTransportFlowSnapshotV49F
            assert snapshot.kernel_socket_identity == (
                owner._initial_snapshot.kernel_socket_identity  # noqa: SLF001
            )
            assert snapshot.effective_so_rcvbuf_octets == expected_rcvbuf
            assert snapshot.effective_so_sndbuf_octets == expected_sndbuf
            assert snapshot.siocinq_queued_octets == 123
            assert snapshot.siocoutq_queued_octets == 45
            assert observed_requests == [
                linux_v4._SIOCINQ,  # noqa: SLF001
                linux_v4._SIOCOUTQ,  # noqa: SLF001
            ]
            assert snapshot.driver_flow.driver_state is (
                TlsWebSocketDriverStateV49.RAW_INGRESS_PENDING
            )
            assert snapshot.driver_flow.pending_raw_chunks == 1
            assert snapshot.driver_flow.pending_raw_octets == len(frame)
            assert snapshot.driver_flow.durable_ingress_buffer_octets == 0
            assert not snapshot.driver_flow.has_complete_durable_unit
        finally:
            if owner._io_lock.locked():  # noqa: SLF001
                owner._io_lock.release()  # noqa: SLF001
            await harness.close()

    asyncio.run(scenario())


def test_v49f_owner_snapshot_reports_active_staged_tls_remaining_counts(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        harness = await _bound_owner(tmp_path)
        try:
            wire = await harness.owner.prepare_exact_text_wire_v49c(b"snapshot")
            prepared = await harness.owner.prepare_tls_ciphertext_v49c(wire)
            snapshot = await harness.owner.transport_flow_snapshot_v49f()

            assert snapshot.driver_flow.driver_state is (
                TlsWebSocketDriverStateV49.TLS_CIPHERTEXT_PREPARED_V49C
            )
            assert snapshot.driver_flow.staged_tls_ciphertext_octets == (
                prepared.ciphertext_octets
            )
            assert snapshot.driver_flow.staged_websocket_wire_chunks == len(
                wire.ordered_wire_chunks
            )
            assert snapshot.driver_flow.staged_websocket_wire_octets == wire.wire_octets
            assert snapshot.driver_flow.remaining_staged_tls_ciphertext_octets == (
                prepared.ciphertext_octets
            )
            assert snapshot.driver_flow.staged_tls_control_ciphertext_octets == 0
            assert (
                snapshot.driver_flow.remaining_staged_tls_control_ciphertext_octets == 0
            )
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_v49f_linux_snapshot_preserves_other_fields_when_one_ioctl_is_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        harness = await _bound_owner(tmp_path)
        original_ioctl = linux_v4.fcntl.ioctl

        def one_unavailable(fd: int, request: int, *args: Any) -> Any:
            if request == linux_v4._SIOCINQ:  # noqa: SLF001
                raise OSError("injected SIOCINQ observer failure")
            if request == linux_v4._SIOCOUTQ:  # noqa: SLF001
                buffer, mutate = args
                assert mutate is True
                buffer[:] = (17).to_bytes(4, byteorder=sys.byteorder, signed=True)
                return 0
            return original_ioctl(fd, request, *args)

        try:
            monkeypatch.setattr(linux_v4.fcntl, "ioctl", one_unavailable)
            snapshot = await harness.owner.transport_flow_snapshot_v49f()

            assert snapshot.siocinq_queued_octets is None
            assert snapshot.siocoutq_queued_octets == 17
            assert snapshot.effective_so_rcvbuf_octets is not None
            assert snapshot.effective_so_sndbuf_octets is not None
            assert snapshot.unavailable_fields == ("siocinq_queued_octets",)
            assert snapshot.unavailable_reason_codes == ("SIOCINQ_UNAVAILABLE",)
            assert snapshot.driver_flow.driver_state is (
                TlsWebSocketDriverStateV49.WS_OPEN_BOUND
            )
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_v49f_owner_snapshot_rejects_driver_transition_during_observation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_snapshot = ExactTlsWebSocketDriverV49.transport_flow_snapshot_v49f

    async def snapshot_then_transition(
        driver: ExactTlsWebSocketDriverV49,
    ) -> TlsWebSocketDriverFlowSnapshotV49F:
        snapshot = await original_snapshot(driver)
        driver._state = TlsWebSocketDriverStateV49.WS_CLOSING  # noqa: SLF001
        return snapshot

    async def scenario() -> None:
        harness = await _bound_owner(tmp_path)
        try:
            monkeypatch.setattr(
                ExactTlsWebSocketDriverV49,
                "transport_flow_snapshot_v49f",
                snapshot_then_transition,
            )
            with pytest.raises(
                linux_v4.LinuxSocketOwnerV4Error,
                match="changed during V4.9F flow observation",
            ):
                await harness.owner.transport_flow_snapshot_v49f()
        finally:
            await harness.close()

    asyncio.run(scenario())

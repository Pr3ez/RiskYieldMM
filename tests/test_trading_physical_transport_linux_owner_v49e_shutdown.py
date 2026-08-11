from __future__ import annotations

import asyncio
import socket
from pathlib import Path

import pytest
from websockets.frames import Frame, Opcode

from riskyieldmm.trading.physical_transport_linux_v4 import (
    TcpWriteShutdownResultV49E,
    TcpWriteShutdownTokenV49E,
)
from riskyieldmm.trading.physical_transport_tls_v49 import (
    PreparedTlsControlCiphertextV49E,
    TlsControlOutputKindV49E,
    TlsShutdownObservationKindV49E,
    TlsWebSocketDriverStateV49,
)
from tests.test_trading_physical_transport_linux_owner_v49c_staged import (
    _bound_owner,
    _deadline,
    _send_all,
)
from tests.test_trading_physical_transport_linux_owner_v49d_ingress import (
    _owner_raw,
)


async def _advance_server_close_to_ws_closing(harness) -> None:
    owner = harness.owner
    pending = await owner.read_decrypted_ingress_v49d(timeout_seconds=1)
    await owner.adopt_durable_ingress_v49d(_owner_raw(harness, pending))
    parsed = await owner.parse_next_durable_unit_v49d()
    assert parsed is not None
    assert parsed.frame_event is not None
    assert parsed.frame_event.opcode == int(Opcode.CLOSE)
    assert len(parsed.protocol_output_chunks) == 1
    wire = await owner.prepare_pending_protocol_output_wire_v49c(
        parsed.protocol_output_chunks
    )
    ciphertext = await owner.prepare_tls_ciphertext_v49c(wire)
    await _send_all(owner, ciphertext)
    assert harness.driver.state is TlsWebSocketDriverStateV49.WS_CLOSING


async def _send_all_control(owner, prepared: PreparedTlsControlCiphertextV49E) -> None:
    offset = 0
    while offset < prepared.ciphertext_octets:
        accepted = await owner.send_prepared_tls_control_ciphertext_once_v49e(
            prepared.exact_ciphertext[offset:],
            prepared=prepared,
            deadline_ns=_deadline(owner),
        )
        assert 0 < accepted <= prepared.ciphertext_octets - offset
        offset += accepted


def test_v49e_shutdown_artifacts_are_module_sealed() -> None:
    with pytest.raises(TypeError, match="driver-constructed"):
        PreparedTlsControlCiphertextV49E(_token=object())
    with pytest.raises(TypeError, match="owner-constructed"):
        TcpWriteShutdownTokenV49E(_token=object())
    with pytest.raises(TypeError, match="owner-constructed"):
        TcpWriteShutdownResultV49E(_token=object())


def test_owner_drives_clean_tls13_close_then_one_shot_shut_wr_and_tcp_eof(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        close_frame = Frame(Opcode.CLOSE, b"").serialize(mask=False)
        harness = await _bound_owner(tmp_path, first_frame=close_frame)
        try:
            await _advance_server_close_to_ws_closing(harness)
            deadline_ns = harness.owner.monotonic_now_ns() + 10_000_000_000
            prepared = await harness.owner.prepare_local_close_notify_v49e(
                deadline_ns=deadline_ns
            )
            assert type(prepared) is PreparedTlsControlCiphertextV49E
            assert prepared.control_kind is TlsControlOutputKindV49E.LOCAL_CLOSE_NOTIFY
            assert prepared.ciphertext_octets == len(prepared.exact_ciphertext)
            assert prepared.ciphertext_octets > 0

            await _send_all_control(harness.owner, prepared)
            assert harness.driver.state is TlsWebSocketDriverStateV49.TLS_SHUTDOWN_V49E

            token = await harness.owner.prepare_tcp_write_shutdown_v49e(
                prepared,
                deadline_ns=deadline_ns,
            )
            assert type(token) is TcpWriteShutdownTokenV49E
            result = await harness.owner.shutdown_tcp_write_v49e(
                token,
                deadline_ns=deadline_ns,
            )
            assert type(result) is TcpWriteShutdownResultV49E
            assert result.shutdown_token is token
            assert result.shutdown_how == socket.SHUT_WR
            assert result.kernel_accepted

            peer_close = await harness.owner.poll_tls_shutdown_v49e(timeout_seconds=2)
            assert peer_close.observation_kind is (
                TlsShutdownObservationKindV49E.PEER_CLOSE_NOTIFY
            )
            assert peer_close.peer_close_notify_received
            assert not peer_close.tcp_eof_received
            assert not peer_close.truncated

            tcp_eof = await harness.owner.poll_tls_shutdown_v49e(timeout_seconds=2)
            assert tcp_eof.observation_kind is TlsShutdownObservationKindV49E.TCP_EOF
            assert tcp_eof.peer_close_notify_received
            assert tcp_eof.tcp_eof_received
            assert not tcp_eof.truncated
            assert tcp_eof.observation_sequence == peer_close.observation_sequence + 1

            assert harness.driver.state is (
                TlsWebSocketDriverStateV49.TLS_SHUTDOWN_V49E
            )
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_owner_reports_tcp_eof_without_peer_close_notify_as_truncation(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        close_frame = Frame(Opcode.CLOSE, b"").serialize(mask=False)
        harness = await _bound_owner(tmp_path, first_frame=close_frame)
        try:
            await _advance_server_close_to_ws_closing(harness)
            deadline_ns = harness.owner.monotonic_now_ns() + 10_000_000_000
            prepared = await harness.owner.prepare_local_close_notify_v49e(
                deadline_ns=deadline_ns
            )
            await _send_all_control(harness.owner, prepared)

            # Bypass the server TLS layer deliberately: emit a TCP FIN without
            # an authenticated server close_notify while retaining its read half.
            transport_socket = harness.fake.writers[0].transport.get_extra_info(
                "socket"
            )
            raw_socket = getattr(transport_socket, "_sock", transport_socket)
            raw_socket.shutdown(socket.SHUT_WR)

            token = await harness.owner.prepare_tcp_write_shutdown_v49e(
                prepared,
                deadline_ns=deadline_ns,
            )
            await harness.owner.shutdown_tcp_write_v49e(
                token,
                deadline_ns=deadline_ns,
            )
            tcp_eof = await harness.owner.poll_tls_shutdown_v49e(timeout_seconds=2)
            assert tcp_eof.observation_kind is TlsShutdownObservationKindV49E.TCP_EOF
            assert not tcp_eof.peer_close_notify_received
            assert tcp_eof.tcp_eof_received
            assert tcp_eof.truncated
        finally:
            await harness.close()

    asyncio.run(scenario())

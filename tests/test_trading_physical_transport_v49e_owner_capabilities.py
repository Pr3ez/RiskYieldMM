from __future__ import annotations

import asyncio
import errno
import hashlib
import inspect
import socket
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from websockets.frames import CloseCode, Frame, Opcode

from riskyieldmm.trading.canonical import sha256_digest
from riskyieldmm.trading.physical_transport_actor_v49c import (
    LocalShutdownCommandStartedPayloadV49E,
    LocalShutdownDeadlineClassificationV49E,
    TcpHalfCloseResultPayloadV49E,
    TerminalIngressFailureKindV49E,
    TerminalIngressFailurePayloadV49E,
    TlsProtocolOperationFailedPayloadV49E,
    TlsProtocolOperationFailureKindV49E,
    TlsProtocolOperationPurposeV49E,
    TlsProtocolOperationStartedPayloadV49E,
    TransportActorEventKindV49C,
    TransportActorEventV49C,
    validate_transport_actor_chain_v49c,
)
from riskyieldmm.trading.physical_transport_actor_v49c import (
    TlsShutdownObservationKindV49E as ActorTlsShutdownObservationKindV49E,
)
from riskyieldmm.trading.physical_transport_linux_v4 import (
    LinuxSocketOwnerV4,
    LinuxSocketOwnerV4Error,
    OwnerTlsShutdownObservationV49E,
    TcpWriteShutdownErrorCodeV49E,
    TcpWriteShutdownResultV49E,
)
from riskyieldmm.trading.physical_transport_tls_v49 import (
    PreparedWebSocketWireV49C,
    TlsShutdownObservationV49E,
    TlsWebSocketDriverStateV49,
)
from tests.test_trading_physical_transport_actor_v49e_terminal_contract import (
    AUTHORITY,
    _append,
    _digest,
    _fail_tls_operation,
    _local_tls_and_half_close_prefix,
    _observe_shutdown,
    _start_tls_operation,
    _websocket_close_prefix,
)
from tests.test_trading_physical_transport_linux_owner_v49c_staged import (
    _bound_owner,
    _decode_client_frame,
)
from tests.test_trading_physical_transport_linux_owner_v49e_shutdown import (
    _advance_server_close_to_ws_closing,
)


class _ConclusiveShutdownErrorSocket:
    """Delegate exact identity probes but script one conclusive syscall error."""

    def __init__(self, wrapped: socket.socket, error_number: int) -> None:
        self._wrapped = wrapped
        self._error_number = error_number
        self.shutdown_calls: list[int] = []
        self.fileno_calls = 0
        self.fileno_calls_at_shutdown: int | None = None

    def __getattr__(self, name: str) -> Any:
        return getattr(self._wrapped, name)

    def fileno(self) -> int:
        self.fileno_calls += 1
        return self._wrapped.fileno()

    def shutdown(self, how: int) -> None:
        self.shutdown_calls.append(how)
        self.fileno_calls_at_shutdown = self.fileno_calls
        raise OSError(self._error_number, "scripted conclusive shutdown error")


class _IdentityLossAfterShutdownSocket:
    """Make the retained descriptor identity disappear after the syscall."""

    def __init__(self, wrapped: socket.socket) -> None:
        self._wrapped = wrapped
        self._identity_current = True
        self.shutdown_calls: list[int] = []

    def __getattr__(self, name: str) -> Any:
        return getattr(self._wrapped, name)

    def fileno(self) -> int:
        if not self._identity_current:
            return -1
        return self._wrapped.fileno()

    def shutdown(self, how: int) -> None:
        self.shutdown_calls.append(how)
        self._wrapped.shutdown(how)
        self._identity_current = False


async def _advance_to_tcp_shutdown_token(harness):
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
    return prepared, token, deadline_ns


def test_local_websocket_close_is_fixed_no_argument_and_uses_staged_fifo(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        harness = await _bound_owner(tmp_path)
        try:
            owner = harness.owner
            assert list(
                inspect.signature(
                    owner.prepare_local_websocket_close_wire_v49e
                ).parameters
            ) == ["deadline_ns"]

            deadline_ns = owner.monotonic_now_ns() + 10_000_000_000
            wire = await owner.prepare_local_websocket_close_wire_v49e(
                deadline_ns=deadline_ns
            )
            assert type(wire) is PreparedWebSocketWireV49C
            assert wire.logical_opcode == int(Opcode.CLOSE)
            expected_payload = int(CloseCode.NORMAL_CLOSURE).to_bytes(2, "big")
            assert wire.logical_payload_octets == len(expected_payload)
            assert (
                wire.logical_payload_sha256
                == hashlib.sha256(expected_payload).hexdigest()
            )
            assert harness.fake.application_reads.empty()
            assert harness.driver.state is (
                TlsWebSocketDriverStateV49.OUTBOUND_WIRE_PREPARED_V49C
            )

            prepared = await owner.prepare_tls_ciphertext_v49c(
                wire,
                deadline_ns=deadline_ns,
            )
            assert harness.fake.application_reads.empty()
            offset = 0
            while offset < prepared.ciphertext_octets:
                accepted = await owner.send_prepared_tls_ciphertext_once_v49c(
                    prepared.exact_ciphertext[offset:],
                    prepared=prepared,
                    deadline_ns=deadline_ns,
                )
                offset += accepted
            frame = await asyncio.wait_for(
                harness.fake.application_reads.get(), timeout=1
            )
            opcode, payload = _decode_client_frame(frame)
            assert opcode == int(Opcode.CLOSE)
            assert payload == expected_payload
            assert harness.driver.state is TlsWebSocketDriverStateV49.WS_CLOSING
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_conclusive_shutdown_oserror_is_sealed_and_consumes_token(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        close_frame = Frame(Opcode.CLOSE, b"").serialize(mask=False)
        harness = await _bound_owner(tmp_path, first_frame=close_frame)
        try:
            _prepared, token, deadline_ns = await _advance_to_tcp_shutdown_token(
                harness
            )
            raw_socket = harness.owner._socket  # noqa: SLF001
            scripted = _ConclusiveShutdownErrorSocket(raw_socket, errno.ENOTCONN)
            harness.owner._socket = scripted  # type: ignore[assignment]  # noqa: SLF001

            result = await harness.owner.shutdown_tcp_write_v49e(
                token,
                deadline_ns=deadline_ns,
            )
            assert type(result) is TcpWriteShutdownResultV49E
            assert not result.kernel_accepted
            assert result.error_code is TcpWriteShutdownErrorCodeV49E.NOT_CONNECTED
            assert scripted.shutdown_calls == [socket.SHUT_WR]
            assert scripted.fileno_calls_at_shutdown is not None
            assert scripted.fileno_calls > scripted.fileno_calls_at_shutdown
            assert harness.owner._v49e_tcp_write_shutdown_token is None  # noqa: SLF001
            assert (  # noqa: SLF001
                harness.owner._v49e_tcp_write_shutdown_token_values is None
            )
            LinuxSocketOwnerV4._assert_tcp_write_shutdown_result_integrity_v49e(result)

            forged = object.__new__(TcpWriteShutdownResultV49E)
            for field in TcpWriteShutdownResultV49E.__dataclass_fields__:
                object.__setattr__(forged, field, getattr(result, field))
            object.__setattr__(forged, "error_code", None)
            with pytest.raises(LinuxSocketOwnerV4Error, match="inconsistent"):
                LinuxSocketOwnerV4._assert_tcp_write_shutdown_result_integrity_v49e(
                    forged
                )

            assert harness.owner._v49e_terminal_io_fault_latched  # noqa: SLF001
            with pytest.raises(LinuxSocketOwnerV4Error):
                await harness.owner.poll_tls_shutdown_v49e(timeout_seconds=1)
            assert harness.driver.state is (
                TlsWebSocketDriverStateV49.TLS_SHUTDOWN_V49E
            )
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_shutdown_identity_loss_after_syscall_aborts_without_result(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        close_frame = Frame(Opcode.CLOSE, b"").serialize(mask=False)
        harness = await _bound_owner(tmp_path, first_frame=close_frame)
        try:
            _prepared, token, deadline_ns = await _advance_to_tcp_shutdown_token(
                harness
            )
            raw_socket = harness.owner._socket  # noqa: SLF001
            scripted = _IdentityLossAfterShutdownSocket(raw_socket)
            harness.owner._socket = scripted  # type: ignore[assignment]  # noqa: SLF001

            with pytest.raises(
                LinuxSocketOwnerV4Error,
                match="(terminal|owned) socket descriptor changed",
            ):
                await harness.owner.shutdown_tcp_write_v49e(
                    token,
                    deadline_ns=deadline_ns,
                )
            assert scripted.shutdown_calls == [socket.SHUT_WR]
            assert harness.owner._v49e_tcp_write_shutdown_result is None  # noqa: SLF001
            assert harness.owner._v49e_tcp_write_shutdown_token is None  # noqa: SLF001
            assert harness.driver.state is TlsWebSocketDriverStateV49.CLOSED
            with pytest.raises(LinuxSocketOwnerV4Error):
                harness.owner.snapshot()
        finally:
            await harness.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("error_number", "expected"),
    [
        (errno.EBADF, TcpWriteShutdownErrorCodeV49E.BAD_FILE_DESCRIPTOR),
        (errno.EINVAL, TcpWriteShutdownErrorCodeV49E.INVALID_SHUTDOWN_MODE),
        (errno.ENOTCONN, TcpWriteShutdownErrorCodeV49E.NOT_CONNECTED),
        (errno.ENOTSOCK, TcpWriteShutdownErrorCodeV49E.NOT_A_SOCKET),
    ],
)
def test_shutdown_error_vocabulary_is_closed(
    error_number: int, expected: TcpWriteShutdownErrorCodeV49E
) -> None:
    assert (
        LinuxSocketOwnerV4._canonical_tcp_write_shutdown_error_code_v49e(
            OSError(error_number, "reviewed")
        )
        is expected
    )
    with pytest.raises(LinuxSocketOwnerV4Error, match="unreviewed or ambiguous"):
        LinuxSocketOwnerV4._canonical_tcp_write_shutdown_error_code_v49e(
            OSError(errno.EIO, "unreviewed")
        )


def test_shutdown_cancellation_before_syscall_aborts_authority(tmp_path: Path) -> None:
    async def scenario() -> None:
        close_frame = Frame(Opcode.CLOSE, b"").serialize(mask=False)
        harness = await _bound_owner(tmp_path, first_frame=close_frame)
        try:
            _prepared, token, deadline_ns = await _advance_to_tcp_shutdown_token(
                harness
            )
            await harness.owner._io_lock.acquire()  # noqa: SLF001
            try:
                task = asyncio.create_task(
                    harness.owner.shutdown_tcp_write_v49e(
                        token,
                        deadline_ns=deadline_ns,
                    )
                )
                await asyncio.sleep(0)
                assert not task.done()
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            finally:
                harness.owner._io_lock.release()  # noqa: SLF001
            assert not harness.owner._closed  # noqa: SLF001
            assert harness.owner._v49e_terminal_io_fault_latched  # noqa: SLF001
            assert harness.driver.state is (
                TlsWebSocketDriverStateV49.TLS_SHUTDOWN_V49E
            )
            harness.owner.assert_same_owner(harness.owner._initial_snapshot)  # noqa: SLF001
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_unreviewed_shutdown_oserror_aborts_without_result(tmp_path: Path) -> None:
    async def scenario() -> None:
        close_frame = Frame(Opcode.CLOSE, b"").serialize(mask=False)
        harness = await _bound_owner(tmp_path, first_frame=close_frame)
        try:
            _prepared, token, deadline_ns = await _advance_to_tcp_shutdown_token(
                harness
            )
            raw_socket = harness.owner._socket  # noqa: SLF001
            scripted = _ConclusiveShutdownErrorSocket(raw_socket, errno.EIO)
            harness.owner._socket = scripted  # type: ignore[assignment]  # noqa: SLF001

            with pytest.raises(
                LinuxSocketOwnerV4Error, match="unreviewed or ambiguous"
            ):
                await harness.owner.shutdown_tcp_write_v49e(
                    token,
                    deadline_ns=deadline_ns,
                )
            assert scripted.shutdown_calls == [socket.SHUT_WR]
            assert harness.owner._v49e_tcp_write_shutdown_result is None  # noqa: SLF001
            assert not harness.owner._closed  # noqa: SLF001
            assert harness.owner._v49e_terminal_io_fault_latched  # noqa: SLF001
            assert harness.driver.state is (
                TlsWebSocketDriverStateV49.TLS_SHUTDOWN_V49E
            )
            harness.owner.assert_same_owner(harness.owner._initial_snapshot)  # noqa: SLF001
        finally:
            await harness.close()

    asyncio.run(scenario())


def test_shutdown_observation_is_owner_sealed_and_socket_session_bound(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        close_frame = Frame(Opcode.CLOSE, b"").serialize(mask=False)
        harness = await _bound_owner(tmp_path, first_frame=close_frame)
        try:
            _prepared, token, deadline_ns = await _advance_to_tcp_shutdown_token(
                harness
            )
            result = await harness.owner.shutdown_tcp_write_v49e(
                token,
                deadline_ns=deadline_ns,
            )
            assert result.kernel_accepted
            assert result.error_code is None

            observed = await harness.owner.poll_tls_shutdown_v49e(timeout_seconds=2)
            assert type(observed) is OwnerTlsShutdownObservationV49E
            assert type(observed.driver_observation) is TlsShutdownObservationV49E
            assert observed.transport_session_id == (
                harness.owner._v49b_bound_session_id  # noqa: SLF001
            )
            assert observed.kernel_socket_identity == (
                harness.owner._initial_snapshot.kernel_socket_identity  # noqa: SLF001
            )
            assert observed.owner_observation_id != observed.observation_id
            assert observed.observation_kind is (
                observed.driver_observation.observation_kind
            )
            LinuxSocketOwnerV4._assert_owner_tls_shutdown_observation_integrity_v49e(
                observed
            )

            # A valid public actor chain cannot mint owner-local terminal clock
            # authority for a fresh owner.  Only consuming the exact live
            # capability can open this seam.
            events, actor_state, fin_marker, _ = _local_tls_and_half_close_prefix()
            _observe_shutdown(
                events,
                actor_state,
                operation_sequence=2,
                observation_sequence=1,
                kind=ActorTlsShutdownObservationKindV49E.PEER_CLOSE_NOTIFY,
                cause_event_id=fin_marker.transport_actor_event_id,
                peer_received=True,
            )
            with pytest.raises(
                LinuxSocketOwnerV4Error,
                match="prior live owner authorization",
            ):
                harness.owner._restore_terminal_actor_clock_from_chain_v49e(  # noqa: SLF001
                    events=tuple(events)
                )
            with pytest.raises(
                LinuxSocketOwnerV4Error,
                match="copied, consumed, expired, or out of context",
            ):
                harness.owner._authorize_terminal_actor_clock_from_evidence_v49e(  # noqa: SLF001
                    observed
                )

            copied = object.__new__(OwnerTlsShutdownObservationV49E)
            for field in OwnerTlsShutdownObservationV49E.__dataclass_fields__:
                object.__setattr__(copied, field, getattr(observed, field))
            with pytest.raises(
                LinuxSocketOwnerV4Error,
                match="copied, consumed, expired, or out of context",
            ):
                copied.consume_for_actor_v49e(
                    transport_session_id=observed.transport_session_id,
                    driver_evidence_nonce_sha256=(
                        observed.driver_evidence_nonce_sha256
                    ),
                )

            consumed = observed.consume_for_actor_v49e(
                transport_session_id=observed.transport_session_id,
                driver_evidence_nonce_sha256=(observed.driver_evidence_nonce_sha256),
            )
            assert consumed is observed
            harness.owner._authorize_terminal_actor_clock_from_evidence_v49e(  # noqa: SLF001
                consumed
            )
            first_terminal_sample = harness.owner.sample_terminal_governed_v49e()
            second_terminal_sample = harness.owner.sample_terminal_governed_v49e()
            assert (
                second_terminal_sample.boottime_after_ns
                >= first_terminal_sample.boottime_after_ns
            )
            with pytest.raises(
                LinuxSocketOwnerV4Error,
                match="copied, consumed, expired, or out of context",
            ):
                harness.owner._authorize_terminal_actor_clock_from_evidence_v49e(  # noqa: SLF001
                    observed
                )

            tcp_eof = await harness.owner.poll_tls_shutdown_v49e(timeout_seconds=2)
            assert type(tcp_eof) is OwnerTlsShutdownObservationV49E
            assert tcp_eof.tcp_eof_received
            assert tcp_eof.owner_observation_id != tcp_eof.observation_id
            assert tcp_eof.owner_observation_id != observed.owner_observation_id
            assert tcp_eof.kernel_socket_identity == observed.kernel_socket_identity
            assert tcp_eof.transport_session_id == observed.transport_session_id
            consumed_eof = tcp_eof.consume_for_actor_v49e(
                transport_session_id=tcp_eof.transport_session_id,
                driver_evidence_nonce_sha256=(tcp_eof.driver_evidence_nonce_sha256),
            )
            assert consumed_eof is tcp_eof
            harness.owner._authorize_terminal_actor_clock_from_evidence_v49e(  # noqa: SLF001
                consumed_eof
            )
            harness.owner.sample_terminal_governed_v49e()
            with pytest.raises(
                LinuxSocketOwnerV4Error,
                match="copied, consumed, expired, or out of context",
            ):
                tcp_eof.consume_for_actor_v49e(
                    transport_session_id=tcp_eof.transport_session_id,
                    driver_evidence_nonce_sha256=(tcp_eof.driver_evidence_nonce_sha256),
                )

            with pytest.raises(TypeError, match="owner-constructed"):
                OwnerTlsShutdownObservationV49E(_token=object())
            forged = object.__new__(OwnerTlsShutdownObservationV49E)
            for field in OwnerTlsShutdownObservationV49E.__dataclass_fields__:
                object.__setattr__(forged, field, getattr(observed, field))
            object.__setattr__(forged, "kernel_socket_identity", "0" * 64)
            with pytest.raises(LinuxSocketOwnerV4Error, match="differs"):
                LinuxSocketOwnerV4._assert_owner_tls_shutdown_observation_integrity_v49e(
                    forged
                )
        finally:
            await harness.close()

    asyncio.run(scenario())


def _tls_poll_failure_restore_chain(
    failure_kind: TlsProtocolOperationFailureKindV49E,
) -> tuple[tuple[TransportActorEventV49C, ...], str, str, str | None]:
    events, _state, fin_marker, _ = _local_tls_and_half_close_prefix()
    half_close = next(
        event
        for event in reversed(events)
        if type(event.payload) is TcpHalfCloseResultPayloadV49E
    )
    half_close_payload = half_close.payload
    assert type(half_close_payload) is TcpHalfCloseResultPayloadV49E
    operation_event = _start_tls_operation(
        events,
        sequence=2,
        purpose=TlsProtocolOperationPurposeV49E.PEER_SHUTDOWN_POLL,
        cause_event_id=fin_marker.transport_actor_event_id,
    )
    operation = operation_event.payload
    command = next(
        event.payload
        for event in reversed(events)
        if type(event.payload) is LocalShutdownCommandStartedPayloadV49E
    )
    assert type(operation) is TlsProtocolOperationStartedPayloadV49E
    assert type(command) is LocalShutdownCommandStartedPayloadV49E
    if (
        failure_kind
        is TlsProtocolOperationFailureKindV49E.DEADLINE_EXPIRED_AFTER_PROGRESS
    ):
        ciphertext = b"authenticated-partial-tls-shutdown"
        ciphertext_sha256 = hashlib.sha256(ciphertext).hexdigest()
        driver_evidence_id = sha256_digest(
            {
                "domain": "RiskYieldMMDeadlineExpiredAfterProgressV4_9E",
                "driver_evidence_nonce_sha256": (
                    operation.driver_evidence_nonce_sha256
                ),
                "operation": "TLS_SHUTDOWN_POLL",
                "deadline_ns": command.shutdown_deadline_monotonic_ns,
                "ciphertext_octets_received": len(ciphertext),
                "ciphertext_sha256": ciphertext_sha256,
            }
        )
        kernel_socket_identity = _digest("owner-kernel-socket")
        owner_evidence_id = sha256_digest(
            {
                "domain": "RiskYieldMMOwnerDeadlineExpiredAfterProgressV4_9E",
                "transport_session_id": AUTHORITY["transport_session_id"],
                "kernel_socket_identity": kernel_socket_identity,
                "driver_evidence_nonce_sha256": (
                    operation.driver_evidence_nonce_sha256
                ),
                "operation": "TLS_SHUTDOWN_POLL",
                "deadline_ns": command.shutdown_deadline_monotonic_ns,
                "ciphertext_octets_received": len(ciphertext),
                "ciphertext_sha256": ciphertext_sha256,
                "driver_evidence_id": driver_evidence_id,
            }
        )
        _append(
            events,
            TransportActorEventKindV49C.TLS_PROTOCOL_OPERATION_FAILED,
            TlsProtocolOperationFailedPayloadV49E(
                tls_protocol_operation_started_event_id=(
                    operation_event.transport_actor_event_id
                ),
                tls_operation_id=operation.tls_operation_id,
                purpose=operation.purpose,
                driver_evidence_nonce_sha256=(operation.driver_evidence_nonce_sha256),
                failure_kind=failure_kind,
                deadline_classification=(
                    LocalShutdownDeadlineClassificationV49E.BOTH_DUE
                ),
                shutdown_deadline_monotonic_ns=(command.shutdown_deadline_monotonic_ns),
                unsendable_driver_output_sequence=None,
                unsendable_driver_evidence_id=None,
                unsendable_owner_evidence_id=None,
                unsendable_kernel_socket_identity=None,
                unsendable_ciphertext_sha256=None,
                unsendable_ciphertext_octets=None,
                deadline_no_observation_owner_evidence_id=None,
                deadline_no_observation_kernel_socket_identity=None,
                deadline_no_observation_operation=None,
                deadline_after_progress_owner_evidence_id=owner_evidence_id,
                deadline_after_progress_driver_evidence_id=driver_evidence_id,
                deadline_after_progress_kernel_socket_identity=(kernel_socket_identity),
                deadline_after_progress_operation="TLS_SHUTDOWN_POLL",
                deadline_after_progress_ciphertext_sha256=ciphertext_sha256,
                deadline_after_progress_ciphertext_octets=len(ciphertext),
                observed_at=command.shutdown_deadline_at,
                observed_monotonic_ns=(command.shutdown_deadline_monotonic_ns),
            ),
        )
    else:
        failure_event = _fail_tls_operation(events, operation_event, failure_kind)
        failure = failure_event.payload
        assert type(failure) is TlsProtocolOperationFailedPayloadV49E
        if (
            failure_kind
            is TlsProtocolOperationFailureKindV49E.DEADLINE_EXPIRED_NO_OBSERVATION
        ):
            owner_evidence_id = failure.deadline_no_observation_owner_evidence_id
            kernel_socket_identity = (
                failure.deadline_no_observation_kernel_socket_identity
            )
        else:
            owner_evidence_id = failure.unsendable_owner_evidence_id
            kernel_socket_identity = failure.unsendable_kernel_socket_identity
        assert type(owner_evidence_id) is str
        assert type(kernel_socket_identity) is str
    validate_transport_actor_chain_v49c(events)
    return (
        tuple(events),
        owner_evidence_id,
        kernel_socket_identity,
        half_close_payload.shutdown_result_id,
    )


def _terminal_ingress_restore_chain() -> tuple[
    tuple[TransportActorEventV49C, ...], str, str, None
]:
    events, _state, _accepted = _websocket_close_prefix()
    command_event = next(
        event
        for event in reversed(events)
        if type(event.payload) is LocalShutdownCommandStartedPayloadV49E
    )
    command = command_event.payload
    assert type(command) is LocalShutdownCommandStartedPayloadV49E
    ciphertext = b"authenticated-partial-terminal-ingress"
    ciphertext_sha256 = hashlib.sha256(ciphertext).hexdigest()
    nonce = _digest("driver-evidence-nonce")
    driver_evidence_id = sha256_digest(
        {
            "domain": "RiskYieldMMDeadlineExpiredAfterProgressV4_9E",
            "driver_evidence_nonce_sha256": nonce,
            "operation": "TERMINAL_CLOSE_INGRESS",
            "deadline_ns": command.shutdown_deadline_monotonic_ns,
            "ciphertext_octets_received": len(ciphertext),
            "ciphertext_sha256": ciphertext_sha256,
        }
    )
    kernel_socket_identity = _digest("owner-kernel-socket")
    owner_evidence_id = sha256_digest(
        {
            "domain": "RiskYieldMMOwnerDeadlineExpiredAfterProgressV4_9E",
            "transport_session_id": AUTHORITY["transport_session_id"],
            "kernel_socket_identity": kernel_socket_identity,
            "driver_evidence_nonce_sha256": nonce,
            "operation": "TERMINAL_CLOSE_INGRESS",
            "deadline_ns": command.shutdown_deadline_monotonic_ns,
            "ciphertext_octets_received": len(ciphertext),
            "ciphertext_sha256": ciphertext_sha256,
            "driver_evidence_id": driver_evidence_id,
        }
    )
    _append(
        events,
        TransportActorEventKindV49C.TERMINAL_INGRESS_FAILURE,
        TerminalIngressFailurePayloadV49E(
            local_shutdown_command_started_event_id=(
                command_event.transport_actor_event_id
            ),
            shutdown_deadline_monotonic_ns=(command.shutdown_deadline_monotonic_ns),
            failure_kind=(
                TerminalIngressFailureKindV49E.DEADLINE_EXPIRED_AFTER_PROGRESS
            ),
            operation="TERMINAL_CLOSE_INGRESS",
            owner_evidence_id=owner_evidence_id,
            driver_evidence_id=driver_evidence_id,
            kernel_socket_identity=kernel_socket_identity,
            driver_evidence_nonce_sha256=nonce,
            ciphertext_sha256=ciphertext_sha256,
            ciphertext_octets_received=len(ciphertext),
            observed_at=command.shutdown_deadline_at,
            observed_monotonic_ns=command.shutdown_deadline_monotonic_ns,
        ),
    )
    validate_transport_actor_chain_v49c(events)
    return tuple(events), owner_evidence_id, kernel_socket_identity, None


def _half_close_restore_chain() -> tuple[
    tuple[TransportActorEventV49C, ...], str, str, None
]:
    events, _state, _fin_marker, _ = _local_tls_and_half_close_prefix()
    result = next(
        event.payload
        for event in reversed(events)
        if type(event.payload) is TcpHalfCloseResultPayloadV49E
    )
    assert type(result) is TcpHalfCloseResultPayloadV49E
    validate_transport_actor_chain_v49c(events)
    return (
        tuple(events),
        result.shutdown_result_id,
        _digest("retained-owner-socket"),
        None,
    )


def _restore_probe_owner(
    *,
    kernel_socket_identity: str,
    evidence_ids: set[str],
    authorized: bool = True,
) -> LinuxSocketOwnerV4:
    owner = object.__new__(LinuxSocketOwnerV4)
    owner._v49b_bound_session_id = AUTHORITY[  # noqa: SLF001
        "transport_session_id"
    ]
    owner._initial_snapshot = SimpleNamespace(  # type: ignore[assignment]  # noqa: SLF001
        kernel_socket_identity=kernel_socket_identity
    )
    owner._v49e_terminal_actor_clock_authorized = authorized  # noqa: SLF001
    owner._v49e_terminal_actor_clock_evidence_ids = evidence_ids  # noqa: SLF001
    return owner


@pytest.mark.parametrize(
    "chain_factory",
    [
        lambda: _tls_poll_failure_restore_chain(
            TlsProtocolOperationFailureKindV49E.DEADLINE_EXPIRED_NO_OBSERVATION
        ),
        lambda: _tls_poll_failure_restore_chain(
            TlsProtocolOperationFailureKindV49E.DEADLINE_EXPIRED_AFTER_PROGRESS
        ),
        lambda: _tls_poll_failure_restore_chain(
            TlsProtocolOperationFailureKindV49E.UNSENDABLE_POST_HANDSHAKE_OUTPUT_AFTER_SHUT_WR
        ),
        _terminal_ingress_restore_chain,
        _half_close_restore_chain,
    ],
    ids=[
        "peer-poll-no-observation",
        "peer-poll-after-progress",
        "unsendable-post-shut-wr-output",
        "terminal-ingress-after-progress",
        "tcp-shut-wr-result",
    ],
)
def test_terminal_clock_restore_requires_exact_same_owner_live_evidence_id(
    monkeypatch: pytest.MonkeyPatch,
    chain_factory: Any,
) -> None:
    events, latest_evidence_id, kernel_socket_identity, older_evidence_id = (
        chain_factory()
    )
    monkeypatch.setattr(
        LinuxSocketOwnerV4,
        "_assert_terminal_actor_clock_base_v49e",
        lambda _owner: object(),
    )

    fresh_owner = _restore_probe_owner(
        kernel_socket_identity=kernel_socket_identity,
        evidence_ids=set(),
        authorized=False,
    )
    with pytest.raises(
        LinuxSocketOwnerV4Error,
        match="prior live owner authorization",
    ):
        fresh_owner._restore_terminal_actor_clock_from_chain_v49e(  # noqa: SLF001
            events=events
        )

    wrong_evidence_id = _digest("different-prior-live-owner-evidence")
    if older_evidence_id is not None:
        wrong_evidence_id = older_evidence_id
    same_owner_with_only_stale_evidence = _restore_probe_owner(
        kernel_socket_identity=kernel_socket_identity,
        evidence_ids={wrong_evidence_id},
    )
    with pytest.raises(
        LinuxSocketOwnerV4Error,
        match="prior live owner authorization",
    ):
        same_owner_with_only_stale_evidence._restore_terminal_actor_clock_from_chain_v49e(  # noqa: SLF001
            events=events
        )

    same_owner = _restore_probe_owner(
        kernel_socket_identity=kernel_socket_identity,
        evidence_ids={latest_evidence_id},
    )
    same_owner._restore_terminal_actor_clock_from_chain_v49e(  # noqa: SLF001
        events=events
    )

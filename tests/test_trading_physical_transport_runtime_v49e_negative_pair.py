from __future__ import annotations

import asyncio
import hashlib
import ssl
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pytest
from websockets.frames import Frame, Opcode

from riskyieldmm.trading.physical_transport_actor_v49c import (
    LocalShutdownCommandStartedPayloadV49E,
    LocalShutdownDeadlineClassificationV49E,
    TlsProtocolOperationFailedPayloadV49E,
    TlsProtocolOperationFailureKindV49E,
    TransportActorEventKindV49C,
    validate_transport_actor_chain_v49c,
)
from riskyieldmm.trading.physical_transport_runtime_v4 import (
    PhysicalTransportRuntimeStateV4,
    PhysicalTransportRuntimeV4StateError,
)
from riskyieldmm.trading.physical_transport_terminal_v49c import (
    V49E_TLS_SHUTDOWN_DEADLINE_EXPIRED_AFTER_PROGRESS_CAUSE,
    TerminalTransitionKindV49C,
    TerminalTransitionPayloadV49C,
)
from riskyieldmm.trading.physical_transport_tls_v49 import (
    ExactTlsWebSocketDriverV49,
)
from riskyieldmm.trading.physical_transport_v4 import (
    TransportSessionTerminationReasonV4,
)
from tests.test_trading_physical_transport_runtime_v49b import (
    _build_harness,
    _typed_count,
)
from tests.test_trading_physical_transport_runtime_v49d_ingress import (
    _establish_and_activate,
    _push_server_bytes,
    _read_client_frames,
)

pytestmark = pytest.mark.skipif(
    sys.platform != "linux", reason="Linux-only exact V4.9E negative-pair tests"
)


def _assert_one_terminal_pair(harness: Any) -> tuple[Any, ...]:
    actor = harness.runtime._transport_session_actor_v49c  # noqa: SLF001
    assert actor is not None
    events = actor.events
    validate_transport_actor_chain_v49c(events)

    convergence = actor.last_terminal_convergence_v49e
    assert convergence is not None
    assert events[-1] is convergence.terminal_event
    assert convergence.termination.transport_session_id == (
        actor.authority.transport_session_id
    )
    final_events = tuple(
        event
        for event in events
        if event.event_kind is TransportActorEventKindV49C.TERMINAL_TRANSITION
        and type(event.payload) is TerminalTransitionPayloadV49C
        and event.payload.kind
        in {
            TerminalTransitionKindV49C.CLEAN_ALL_LAYERS,
            TerminalTransitionKindV49C.FATAL,
            TerminalTransitionKindV49C.TIMEOUT,
            TerminalTransitionKindV49C.UNKNOWN_SEND,
        }
    )
    assert final_events == (convergence.terminal_event,)
    assert _typed_count(harness.store, "transport_session_terminations") == 1
    report = harness.store.verify()
    assert report.transport_actor_event_count == len(events)
    assert report.transport_session_termination_count == 1
    return events


def test_owner_tls_prepare_driver_failure_still_commits_one_terminal_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Projection fencing must preserve the actor's terminal clock until commit."""

    async def scenario() -> None:
        peer_close = Frame(
            Opcode.CLOSE,
            (1000).to_bytes(2, "big") + b"ack-before-tls-fault",
        ).serialize(mask=False)
        with TemporaryDirectory(prefix="ry-v49e-negative-prep-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                await _establish_and_activate(harness)
                original = ExactTlsWebSocketDriverV49._drain_tls_control_output_v49e
                effect_calls = 0

                def fail_after_driver_shutdown_mutation(
                    current: ExactTlsWebSocketDriverV49,
                    *,
                    control_kind: Any,
                    peer_close_notify_received_during_preparation: bool,
                    prior_state: Any,
                ) -> Any:
                    nonlocal effect_calls
                    if current is harness.driver:
                        effect_calls += 1
                        raise ssl.SSLError("scripted local close_notify driver fault")
                    return original(
                        current,
                        control_kind=control_kind,
                        peer_close_notify_received_during_preparation=(
                            peer_close_notify_received_during_preparation
                        ),
                        prior_state=prior_state,
                    )

                monkeypatch.setattr(
                    ExactTlsWebSocketDriverV49,
                    "_drain_tls_control_output_v49e",
                    fail_after_driver_shutdown_mutation,
                )

                async def answer_local_close() -> tuple[tuple[int, bytes], ...]:
                    frames = await _read_client_frames(harness, count=1)
                    await _push_server_bytes(harness, peer_close)
                    return frames

                answer = asyncio.create_task(answer_local_close())
                termination = await harness.runtime.shutdown_current_v49e(
                    timeout_seconds=30
                )

                assert await answer == ((int(Opcode.CLOSE), (1000).to_bytes(2, "big")),)
                assert effect_calls == 1
                assert termination.reason is (
                    TransportSessionTerminationReasonV4.TRANSPORT_ERROR
                )
                assert harness.runtime.state is PhysicalTransportRuntimeStateV4.FENCED
                events = _assert_one_terminal_pair(harness)

                failures = tuple(
                    event
                    for event in events
                    if event.event_kind
                    is TransportActorEventKindV49C.TLS_PROTOCOL_OPERATION_FAILED
                )
                assert len(failures) == 1
                failure = failures[0].payload
                assert type(failure) is TlsProtocolOperationFailedPayloadV49E
                assert failure.failure_kind is (
                    TlsProtocolOperationFailureKindV49E.DRIVER_ERROR
                )
                terminal = events[-1].payload
                assert type(terminal) is TerminalTransitionPayloadV49C
                assert terminal.kind is TerminalTransitionKindV49C.FATAL
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_partial_tls_recv_deadline_commits_one_typed_timeout_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A positive TLS recv prefix is terminal evidence, never a retryable timeout."""

    async def scenario() -> None:
        peer_close = Frame(
            Opcode.CLOSE,
            (1000).to_bytes(2, "big") + b"ack-before-partial-tls",
        ).serialize(mask=False)
        with TemporaryDirectory(prefix="ry-v49e-negative-partial-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                await _establish_and_activate(harness)
                actor = harness.runtime._transport_session_actor_v49c  # noqa: SLF001
                assert actor is not None
                owner_terminal_clock = (
                    actor._terminal_observation_batch_clock  # noqa: SLF001
                )
                assert owner_terminal_clock is not None
                force_both_due = False

                def both_due_terminal_clock(count: int) -> tuple[tuple[Any, int], ...]:
                    observations = owner_terminal_clock(count)
                    if not force_both_due:
                        return observations
                    command_event = next(
                        event
                        for event in reversed(actor.events)
                        if event.event_kind
                        is TransportActorEventKindV49C.LOCAL_SHUTDOWN_COMMAND_STARTED
                    )
                    command = command_event.payload
                    assert type(command) is LocalShutdownCommandStartedPayloadV49E
                    return tuple(
                        (command.shutdown_deadline_at, monotonic_ns)
                        for _, monotonic_ns in observations
                    )

                # Preserve the real owner terminal sample (and therefore its
                # fd/socket/driver/provenance checks), but align this
                # deterministic fixture's synthetic wall representation with
                # the committed cutoff.  The XOR branch is tested separately.
                actor._terminal_observation_batch_clock = (  # noqa: SLF001
                    both_due_terminal_clock
                )
                original = ExactTlsWebSocketDriverV49._recv_after_readiness_v49e
                captured_prefixes: list[bytes] = []
                terminal_recv_calls = 0

                async def split_peer_tls_then_expire(
                    current: ExactTlsWebSocketDriverV49,
                    owned_socket: Any,
                    *,
                    deadline_ns: int,
                    shutdown_socket_v49e: bool = False,
                ) -> bytes:
                    nonlocal force_both_due, terminal_recv_calls
                    if current is not harness.driver or not shutdown_socket_v49e:
                        return await original(
                            current,
                            owned_socket,
                            deadline_ns=deadline_ns,
                            shutdown_socket_v49e=shutdown_socket_v49e,
                        )
                    terminal_recv_calls += 1
                    if terminal_recv_calls == 1:
                        ciphertext = await original(
                            current,
                            owned_socket,
                            deadline_ns=deadline_ns,
                            shutdown_socket_v49e=True,
                        )
                        assert len(ciphertext) > 1
                        prefix = ciphertext[:1]
                        captured_prefixes.append(prefix)
                        return prefix

                    remaining_seconds = max(
                        0.0,
                        (deadline_ns - time.clock_gettime_ns(time.CLOCK_BOOTTIME))
                        / 1_000_000_000,
                    )
                    await asyncio.sleep(remaining_seconds + 0.01)
                    force_both_due = True
                    command_event = next(
                        event
                        for event in reversed(actor.events)
                        if event.event_kind
                        is TransportActorEventKindV49C.LOCAL_SHUTDOWN_COMMAND_STARTED
                    )
                    command = command_event.payload
                    assert type(command) is LocalShutdownCommandStartedPayloadV49E
                    harness.store._clock = (  # noqa: SLF001
                        lambda: command.shutdown_deadline_at
                    )
                    raise TimeoutError("scripted deadline after positive TLS recv")

                monkeypatch.setattr(
                    ExactTlsWebSocketDriverV49,
                    "_recv_after_readiness_v49e",
                    split_peer_tls_then_expire,
                )

                async def answer_local_close() -> tuple[tuple[int, bytes], ...]:
                    frames = await _read_client_frames(harness, count=1)
                    await _push_server_bytes(harness, peer_close)
                    return frames

                answer = asyncio.create_task(answer_local_close())
                termination = await harness.runtime.shutdown_current_v49e(
                    timeout_seconds=20
                )

                assert await answer == ((int(Opcode.CLOSE), (1000).to_bytes(2, "big")),)
                assert terminal_recv_calls == 2
                assert len(captured_prefixes) == 1
                assert termination.reason is (
                    TransportSessionTerminationReasonV4.TRANSPORT_ERROR
                )
                assert harness.runtime.state is PhysicalTransportRuntimeStateV4.FENCED
                events = _assert_one_terminal_pair(harness)

                failures = tuple(
                    event
                    for event in events
                    if event.event_kind
                    is TransportActorEventKindV49C.TLS_PROTOCOL_OPERATION_FAILED
                )
                assert len(failures) == 1
                failure = failures[0].payload
                assert type(failure) is TlsProtocolOperationFailedPayloadV49E
                assert failure.failure_kind is (
                    TlsProtocolOperationFailureKindV49E.DEADLINE_EXPIRED_AFTER_PROGRESS
                )
                assert failure.deadline_classification is (
                    LocalShutdownDeadlineClassificationV49E.BOTH_DUE
                )
                assert failure.deadline_after_progress_ciphertext_octets == 1
                assert failure.deadline_after_progress_ciphertext_sha256 == (
                    hashlib.sha256(captured_prefixes[0]).hexdigest()
                )
                assert failure.deadline_after_progress_owner_evidence_id is not None
                assert failure.deadline_after_progress_driver_evidence_id is not None
                assert (
                    failure.deadline_after_progress_kernel_socket_identity is not None
                )

                terminal = events[-1].payload
                assert type(terminal) is TerminalTransitionPayloadV49C
                assert terminal.kind is TerminalTransitionKindV49C.TIMEOUT
                assert terminal.cause_code == (
                    V49E_TLS_SHUTDOWN_DEADLINE_EXPIRED_AFTER_PROGRESS_CAUSE
                )
                with pytest.raises(PhysicalTransportRuntimeV4StateError):
                    await harness.runtime.shutdown_current_v49e(timeout_seconds=20)
                assert terminal_recv_calls == 2
                assert (
                    _typed_count(harness.store, "transport_session_terminations") == 1
                )
            finally:
                await harness.close()

    asyncio.run(scenario())

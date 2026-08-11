from __future__ import annotations

import asyncio
import hashlib
import inspect
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from websockets.frames import Frame, Opcode

from riskyieldmm.trading.physical_transport_actor_v49c import (
    LocalShutdownDeadlineClassificationV49E,
    LocalShutdownDeadlineEvidencePayloadV49E,
    TransportActorEventKindV49C,
    validate_transport_actor_chain_v49c,
)
from riskyieldmm.trading.physical_transport_runtime_v4 import (
    PhysicalTransportRuntimeStateV4,
    PhysicalTransportRuntimeV4,
    PhysicalTransportRuntimeV4StateError,
)
from riskyieldmm.trading.physical_transport_terminal_v49c import (
    V49E_LOCAL_SHUTDOWN_CLOCK_DISAGREEMENT_CAUSE,
    V49E_LOCAL_SHUTDOWN_COMMAND_DEADLINE_EXPIRED_CAUSE,
    OutboundObligationLayerV49C,
    TerminalOutcomeV49C,
    TerminalTransitionKindV49C,
    TerminalTransitionPayloadV49C,
)
from riskyieldmm.trading.physical_transport_v4 import (
    TransportSessionTerminationReasonV4,
    TransportSessionTerminationV4,
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
    sys.platform != "linux", reason="Linux-only exact V4.9E terminal tests"
)


def _actor(harness: object):
    actor = harness.runtime._transport_session_actor_v49c  # type: ignore[attr-defined]  # noqa: SLF001
    assert actor is not None
    return actor


def _assert_clean_layer_order(harness: object) -> None:
    actor = _actor(harness)
    events = actor.events
    validate_transport_actor_chain_v49c(events)
    state = actor.terminal_state
    assert state.terminal_outcome is TerminalOutcomeV49C.CLEAN_ALL_LAYERS
    assert state.ws_close_sent
    assert state.ws_close_received
    assert state.ws_output_fully_kernel_accepted
    assert state.tls_close_notify_sent
    assert state.tls_close_notify_received
    assert state.tls_close_notify_fully_kernel_accepted
    assert state.tcp_fin_sent
    assert state.tcp_eof_received

    transitions = [
        (event.actor_sequence, event.payload)
        for event in events
        if event.event_kind is TransportActorEventKindV49C.TERMINAL_TRANSITION
        and type(event.payload) is TerminalTransitionPayloadV49C
    ]

    def sequence(
        kind: TerminalTransitionKindV49C,
        *,
        layer: OutboundObligationLayerV49C | None = None,
    ) -> int:
        matches = [
            actor_sequence
            for actor_sequence, payload in transitions
            if payload.kind is kind
            and (layer is None or payload.obligation_layer is layer)
        ]
        assert len(matches) == 1
        return matches[0]

    ws_sent = sequence(TerminalTransitionKindV49C.WS_CLOSE_SENT)
    ws_received = sequence(TerminalTransitionKindV49C.WS_CLOSE_RECEIVED)
    ws_accepted = sequence(
        TerminalTransitionKindV49C.OUTBOUND_OBLIGATION_FULLY_KERNEL_ACCEPTED,
        layer=OutboundObligationLayerV49C.WEBSOCKET_CLOSE,
    )
    tls_prepared = sequence(TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_PREPARED)
    tls_sent = sequence(TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_SENT)
    tls_accepted = sequence(
        TerminalTransitionKindV49C.OUTBOUND_OBLIGATION_FULLY_KERNEL_ACCEPTED,
        layer=OutboundObligationLayerV49C.TLS_CLOSE_NOTIFY,
    )
    tcp_fin = sequence(TerminalTransitionKindV49C.TCP_FIN_SENT)
    tls_received = sequence(TerminalTransitionKindV49C.TLS_CLOSE_NOTIFY_RECEIVED)
    tcp_eof = sequence(TerminalTransitionKindV49C.TCP_EOF_RECEIVED)
    clean = sequence(TerminalTransitionKindV49C.CLEAN_ALL_LAYERS)

    assert max(ws_sent, ws_received, ws_accepted) < tls_prepared
    assert tls_prepared < tls_sent < tls_accepted < tcp_fin
    assert tcp_fin < tls_received < tcp_eof < clean


def _assert_one_signed_termination(harness: object) -> None:
    assert _typed_count(harness.store, "transport_session_terminations") == 1  # type: ignore[attr-defined]
    report = harness.store.verify()  # type: ignore[attr-defined]
    assert report.transport_session_termination_count == 1


def test_v49e_shutdown_api_exposes_only_one_bounded_timeout() -> None:
    assert tuple(
        inspect.signature(PhysicalTransportRuntimeV4.shutdown_current_v49e).parameters
    ) == ("self", "timeout_seconds")


def test_peer_first_close_converges_all_layers_once() -> None:
    async def scenario() -> None:
        peer_reason = b"peer-finished"
        peer_payload = (1000).to_bytes(2, "big") + peer_reason
        peer_close = Frame(Opcode.CLOSE, peer_payload).serialize(mask=False)
        with TemporaryDirectory(prefix="ry-v49e-peer-close-") as directory:
            harness = await _build_harness(
                Path(directory),
                first_frame=peer_close,
            )
            try:
                await _establish_and_activate(harness)
                progress = await harness.runtime.process_next_ingress_v49d(
                    timeout_seconds=1
                )
                assert len(progress.automatic_dispatch_completion_event_ids) == 1
                assert await _read_client_frames(harness, count=1) == (
                    (int(Opcode.CLOSE), peer_payload),
                )

                termination = await harness.runtime.shutdown_current_v49e(
                    timeout_seconds=30
                )
                assert type(termination) is TransportSessionTerminationV4
                assert termination.reason is (
                    TransportSessionTerminationReasonV4.REMOTE_CLOSE
                )
                assert termination.close_code == 1000
                assert (
                    termination.close_reason_digest
                    == hashlib.sha256(peer_reason).hexdigest()
                )
                assert harness.runtime.state is PhysicalTransportRuntimeStateV4.FENCED
                _assert_clean_layer_order(harness)
                _assert_one_signed_termination(harness)
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_local_first_close_waits_for_peer_then_converges() -> None:
    async def scenario() -> None:
        peer_close = Frame(
            Opcode.CLOSE,
            (1000).to_bytes(2, "big") + b"peer-ack",
        ).serialize(mask=False)
        with TemporaryDirectory(prefix="ry-v49e-local-close-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                await _establish_and_activate(harness)

                async def answer_local_close() -> tuple[tuple[int, bytes], ...]:
                    frames = await _read_client_frames(harness, count=1)
                    await _push_server_bytes(harness, peer_close)
                    return frames

                answer = asyncio.create_task(answer_local_close())
                termination = await harness.runtime.shutdown_current_v49e(
                    timeout_seconds=30
                )
                assert await answer == ((int(Opcode.CLOSE), (1000).to_bytes(2, "big")),)
                assert type(termination) is TransportSessionTerminationV4
                assert termination.reason is (
                    TransportSessionTerminationReasonV4.LOCAL_CLOSE
                )
                assert termination.close_code == 1000
                assert (
                    termination.close_reason_digest == hashlib.sha256(b"").hexdigest()
                )
                assert harness.runtime.state is PhysicalTransportRuntimeStateV4.FENCED
                _assert_clean_layer_order(harness)
                _assert_one_signed_termination(harness)
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_simultaneous_close_uses_first_durable_local_marker_and_sends_once() -> None:
    async def scenario() -> None:
        peer_close = Frame(
            Opcode.CLOSE,
            (1001).to_bytes(2, "big") + b"queued-before-local",
        ).serialize(mask=False)
        with TemporaryDirectory(prefix="ry-v49e-simultaneous-close-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                await _establish_and_activate(harness)
                # Bytes are already on the retained socket, but no peer parser
                # fact is durable.  The local actor command therefore wins the
                # causal race, after which ingress adopts the queued peer Close.
                await _push_server_bytes(harness, peer_close)
                termination = await harness.runtime.shutdown_current_v49e(
                    timeout_seconds=30
                )
                assert await _read_client_frames(harness, count=1) == (
                    (int(Opcode.CLOSE), (1000).to_bytes(2, "big")),
                )
                assert harness.server.application_reads.empty()
                assert termination.reason is (
                    TransportSessionTerminationReasonV4.LOCAL_CLOSE
                )
                assert termination.close_code == 1000
                assert (
                    termination.close_reason_digest == hashlib.sha256(b"").hexdigest()
                )
                assert harness.runtime.state is PhysicalTransportRuntimeStateV4.FENCED
                _assert_clean_layer_order(harness)
                _assert_one_signed_termination(harness)

                with pytest.raises(PhysicalTransportRuntimeV4StateError):
                    await harness.runtime.dispatch_subscription_v49c(
                        idempotency_key="v49e-after-close"
                    )
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_local_close_deadline_returns_one_signed_fail_closed_pair() -> None:
    async def scenario() -> None:
        with TemporaryDirectory(prefix="ry-v49e-close-timeout-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                await _establish_and_activate(harness)

                local_close = asyncio.create_task(_read_client_frames(harness, count=1))
                termination = await harness.runtime.shutdown_current_v49e(
                    timeout_seconds=3
                )
                assert await local_close == (
                    (int(Opcode.CLOSE), (1000).to_bytes(2, "big")),
                )
                assert termination.reason is (
                    TransportSessionTerminationReasonV4.TRANSPORT_ERROR
                )
                assert termination.close_code is None
                assert termination.close_reason_digest is None
                assert harness.runtime.state is PhysicalTransportRuntimeStateV4.FENCED

                actor = _actor(harness)
                deadline_evidence = [
                    event.payload
                    for event in actor.events
                    if event.event_kind
                    is TransportActorEventKindV49C.LOCAL_SHUTDOWN_DEADLINE_EVIDENCE
                ]
                assert len(deadline_evidence) == 1
                evidence = deadline_evidence[0]
                assert type(evidence) is LocalShutdownDeadlineEvidencePayloadV49E
                expected_outcome, expected_cause = {
                    LocalShutdownDeadlineClassificationV49E.BOTH_DUE: (
                        TerminalOutcomeV49C.TIMEOUT,
                        V49E_LOCAL_SHUTDOWN_COMMAND_DEADLINE_EXPIRED_CAUSE,
                    ),
                    LocalShutdownDeadlineClassificationV49E.CLOCK_DISAGREEMENT: (
                        TerminalOutcomeV49C.FATAL,
                        V49E_LOCAL_SHUTDOWN_CLOCK_DISAGREEMENT_CAUSE,
                    ),
                }[evidence.classification]
                assert actor.terminal_state.terminal_outcome is expected_outcome
                terminal = actor.events[-1]
                assert terminal.event_kind is (
                    TransportActorEventKindV49C.TERMINAL_TRANSITION
                )
                assert type(terminal.payload) is TerminalTransitionPayloadV49C
                assert terminal.payload.kind is TerminalTransitionKindV49C(
                    expected_outcome.value
                )
                assert terminal.payload.cause_code == expected_cause
                _assert_one_signed_termination(harness)

                # Synchronous close is cleanup-only after actor convergence;
                # it must release the writer fence without writing a second
                # terminal outcome or reopening any legacy terminal path.
                harness.runtime.close()
                assert harness.runtime.state is PhysicalTransportRuntimeStateV4.CLOSED
                _assert_one_signed_termination(harness)
            finally:
                await harness.close()

    asyncio.run(scenario())

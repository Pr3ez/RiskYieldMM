from __future__ import annotations

import asyncio
import hashlib
import sys
from collections import defaultdict
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pytest
from websockets.frames import Frame, Opcode

from riskyieldmm.trading.physical_transport_actor_v49c import (
    V49E_WEBSOCKET_CLOSE_DEADLINE_EXPIRED_CAUSE,
    LocalShutdownCommandStartedPayloadV49E,
    OutboundWireOriginV49C,
    OutboundWirePreparedPayloadV49C,
    TcpHalfCloseAttemptPayloadV49E,
    TlsCiphertextPreparedPayloadV49C,
    TlsControlKernelSendAttemptPayloadV49E,
    TlsProtocolOperationStartedPayloadV49E,
    TransportActorEventKindV49C,
    TransportActorEventV49C,
    WebSocketOpcodeV49C,
    WritePermitConsumedPayloadV49C,
    validate_transport_actor_chain_v49c,
)
from riskyieldmm.trading.physical_transport_linux_v4 import LinuxSocketOwnerV4
from riskyieldmm.trading.physical_transport_runtime_v4 import (
    PhysicalTransportAutomaticCloseTerminalFailureV49E,
    PhysicalTransportDispatchUnknownV4,
    PhysicalTransportRuntimeStateV4,
    PhysicalTransportRuntimeV4FaultLatched,
)
from riskyieldmm.trading.physical_transport_session_actor_v49c import (
    PhysicalTransportSessionActorV49C,
)
from riskyieldmm.trading.physical_transport_terminal_v49c import (
    V49E_LOCAL_SHUTDOWN_CLOCK_DISAGREEMENT_CAUSE,
    V49E_LOCAL_SHUTDOWN_COMMAND_DEADLINE_EXPIRED_CAUSE,
    TerminalOutcomeV49C,
    TerminalTransitionKindV49C,
    TerminalTransitionPayloadV49C,
)
from riskyieldmm.trading.physical_transport_v4 import (
    TransportSessionTerminationReasonV4,
)
from tests.test_trading_physical_transport_runtime_v49b import (
    T0,
    _build_harness,
    _typed_count,
)
from tests.test_trading_physical_transport_runtime_v49d_ingress import (
    _establish_and_activate,
    _push_server_bytes,
    _read_client_frames,
)

pytestmark = pytest.mark.skipif(
    sys.platform != "linux", reason="Linux-only exact V4.9E command tests"
)

_NORMAL_CLOSE_PAYLOAD = (1000).to_bytes(2, "big")
_OWNER_DEADLINE_METHODS = (
    "prepare_local_websocket_close_wire_v49e",
    "prepare_tls_ciphertext_v49c",
    "send_prepared_tls_ciphertext_once_v49c",
    "read_terminal_close_ingress_v49e",
    "prepare_local_close_notify_v49e",
    "send_prepared_tls_control_ciphertext_once_v49e",
    "prepare_tcp_write_shutdown_token_v49e",
    "shutdown_tcp_write_v49e",
    "poll_tls_shutdown_v49e",
)


def _actor(harness: Any) -> PhysicalTransportSessionActorV49C:
    actor = harness.runtime._transport_session_actor_v49c  # noqa: SLF001
    assert type(actor) is PhysicalTransportSessionActorV49C
    return actor


def _command_event(actor: PhysicalTransportSessionActorV49C) -> TransportActorEventV49C:
    matches = tuple(
        event
        for event in actor.events
        if event.event_kind
        is TransportActorEventKindV49C.LOCAL_SHUTDOWN_COMMAND_STARTED
    )
    assert len(matches) == 1
    return matches[0]


def _assert_command_shape(
    command_event: TransportActorEventV49C, *, timeout_seconds: int
) -> LocalShutdownCommandStartedPayloadV49E:
    payload = command_event.payload
    assert type(payload) is LocalShutdownCommandStartedPayloadV49E
    assert payload.websocket_close_code == 1000
    assert payload.websocket_close_reason_sha256 == hashlib.sha256(b"").hexdigest()
    assert payload.websocket_close_reason_octets == 0
    assert (
        payload.websocket_close_payload_sha256
        == hashlib.sha256(_NORMAL_CLOSE_PAYLOAD).hexdigest()
    )
    assert payload.websocket_close_payload_octets == len(_NORMAL_CLOSE_PAYLOAD)
    assert payload.timeout_seconds == timeout_seconds
    assert command_event.recorded_at == payload.started_at
    assert command_event.recorded_monotonic_ns == payload.started_monotonic_ns
    assert payload.shutdown_deadline_at == payload.started_at + timedelta(
        seconds=timeout_seconds
    )
    assert payload.shutdown_deadline_monotonic_ns == (
        payload.started_monotonic_ns + timeout_seconds * 1_000_000_000
    )
    return payload


def _assert_command_linkage(
    actor: PhysicalTransportSessionActorV49C,
    command_event: TransportActorEventV49C,
    *,
    local_first: bool,
) -> None:
    command = command_event.payload
    assert type(command) is LocalShutdownCommandStartedPayloadV49E
    events = actor.events
    validate_transport_actor_chain_v49c(events)
    by_id = {event.transport_actor_event_id: event for event in events}

    local_wires = tuple(
        event
        for event in events
        if type(event.payload) is OutboundWirePreparedPayloadV49C
        and event.payload.wire_origin is OutboundWireOriginV49C.LOCAL_TERMINAL_COMMAND
    )
    assert len(local_wires) == (1 if local_first else 0)
    if local_first:
        wire_event = local_wires[0]
        wire = wire_event.payload
        assert wire.logical_opcode is WebSocketOpcodeV49C.CLOSE
        assert wire.logical_payload_sha256 == command.websocket_close_payload_sha256
        assert wire.logical_payload_octets == command.websocket_close_payload_octets
        assert wire.send_not_after == command.shutdown_deadline_at
        assert (
            wire.send_not_after_monotonic_ns == command.shutdown_deadline_monotonic_ns
        )

        permits = tuple(
            event
            for event in events
            if type(event.payload) is WritePermitConsumedPayloadV49C
            and event.payload.outbound_wire_prepared_event_id
            == wire_event.transport_actor_event_id
        )
        assert len(permits) == 1
        permit_event = permits[0]
        permit = permit_event.payload
        assert permit.send_not_after == command.shutdown_deadline_at
        assert (
            permit.send_not_after_monotonic_ns == command.shutdown_deadline_monotonic_ns
        )

        ciphertext = tuple(
            event
            for event in events
            if type(event.payload) is TlsCiphertextPreparedPayloadV49C
            and event.payload.outbound_wire_prepared_event_id
            == wire_event.transport_actor_event_id
        )
        assert len(ciphertext) == 1
        assert ciphertext[0].payload.write_permit_consumed_event_id == (
            permit_event.transport_actor_event_id
        )

    tls_operations = tuple(
        event
        for event in events
        if type(event.payload) is TlsProtocolOperationStartedPayloadV49E
    )
    assert len(tls_operations) >= 2
    assert all(
        event.payload.local_shutdown_command_started_event_id
        == command_event.transport_actor_event_id
        for event in tls_operations
    )
    assert all(event.payload.cause_actor_event_id in by_id for event in tls_operations)

    tls_control_attempts = tuple(
        event
        for event in events
        if type(event.payload) is TlsControlKernelSendAttemptPayloadV49E
    )
    assert tls_control_attempts
    assert all(
        event.payload.local_shutdown_command_started_event_id
        == command_event.transport_actor_event_id
        and event.payload.shutdown_deadline_monotonic_ns
        == command.shutdown_deadline_monotonic_ns
        for event in tls_control_attempts
    )

    half_close_attempts = tuple(
        event
        for event in events
        if type(event.payload) is TcpHalfCloseAttemptPayloadV49E
    )
    assert len(half_close_attempts) == 1
    half_close = half_close_attempts[0].payload
    assert half_close.local_shutdown_command_started_event_id == (
        command_event.transport_actor_event_id
    )
    assert (
        half_close.shutdown_deadline_monotonic_ns
        == command.shutdown_deadline_monotonic_ns
    )


def _assert_one_terminal_pair(
    harness: Any,
    *,
    outcome: TerminalOutcomeV49C,
    cause_code: str | None = None,
) -> None:
    actor = _actor(harness)
    convergence = actor.last_terminal_convergence_v49e
    assert convergence is not None
    assert actor.events[-1] is convergence.terminal_event
    assert actor.terminal_state.terminal_outcome is outcome
    terminal_payload = convergence.terminal_event.payload
    assert type(terminal_payload) is TerminalTransitionPayloadV49C
    if cause_code is not None:
        assert terminal_payload.cause_code == cause_code
    final_events = tuple(
        event
        for event in actor.events
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


def _install_owner_deadline_spies(
    monkeypatch: pytest.MonkeyPatch,
    harness: Any,
) -> dict[str, list[int]]:
    calls: dict[str, list[int]] = defaultdict(list)

    for method_name in _OWNER_DEADLINE_METHODS:
        original = getattr(LinuxSocketOwnerV4, method_name)

        def wrapper_factory(name: str, effect: Any) -> Any:
            async def wrapper(
                current: LinuxSocketOwnerV4,
                *args: Any,
                deadline_ns: int,
                **kwargs: Any,
            ) -> Any:
                if current is harness.owner:
                    calls[name].append(deadline_ns)
                result = await effect(
                    current,
                    *args,
                    deadline_ns=deadline_ns,
                    **kwargs,
                )
                if name == "poll_tls_shutdown_v49e" and current is harness.owner:
                    print(
                        "V49E_DEBUG_OBSERVATION",
                        result.driver_observation.observation_kind,
                        result.driver_observation.peer_close_notify_received,
                        result.driver_observation.tcp_eof_received,
                        result.driver_observation.truncated,
                        current._assert_v49e_shutdown_io_bound()._tcp_eof_received_v49e,
                        flush=True,
                    )
                return result

            return wrapper

        monkeypatch.setattr(
            LinuxSocketOwnerV4,
            method_name,
            wrapper_factory(method_name, original),
        )
    return calls


def _assert_owner_deadline_calls(
    calls: dict[str, list[int]],
    *,
    deadline_ns: int,
    local_first: bool,
) -> None:
    local_only = {
        "prepare_local_websocket_close_wire_v49e",
        "prepare_tls_ciphertext_v49c",
        "send_prepared_tls_ciphertext_once_v49c",
        "read_terminal_close_ingress_v49e",
    }
    always = set(_OWNER_DEADLINE_METHODS) - local_only
    for name in always:
        assert calls[name], name
        assert set(calls[name]) == {deadline_ns}
    for name in local_only:
        if local_first:
            assert calls[name], name
            assert set(calls[name]) == {deadline_ns}
        else:
            assert calls[name] == []


def _install_post_command_clock(
    monkeypatch: pytest.MonkeyPatch,
    actor: PhysicalTransportSessionActorV49C,
    projection_store: Any,
    *,
    mode: str,
) -> None:
    original = PhysicalTransportSessionActorV49C.start_local_shutdown_command_v49e

    async def start_then_replace_clock(
        current: PhysicalTransportSessionActorV49C,
        *,
        timeout_seconds: int,
    ) -> TransportActorEventV49C:
        event = await original(current, timeout_seconds=timeout_seconds)
        if current is not actor:
            return event
        projection_store._clock = lambda: T0 + timedelta(minutes=10)  # noqa: SLF001
        command = event.payload
        assert type(command) is LocalShutdownCommandStartedPayloadV49E
        cursor = 0

        def next_observation() -> tuple[Any, int]:
            nonlocal cursor
            cursor += 1
            wall = command.shutdown_deadline_at + timedelta(microseconds=cursor)
            monotonic_ns = (
                command.shutdown_deadline_monotonic_ns + cursor
                if mode == "both_due"
                else command.shutdown_deadline_monotonic_ns - 10_000 + cursor
            )
            return wall, monotonic_ns

        def next_batch(count: int) -> tuple[tuple[Any, int], ...]:
            return tuple(next_observation() for _ in range(count))

        current._observation_clock = next_observation  # noqa: SLF001
        current._observation_batch_clock = next_batch  # noqa: SLF001
        return event

    monkeypatch.setattr(
        PhysicalTransportSessionActorV49C,
        "start_local_shutdown_command_v49e",
        start_then_replace_clock,
    )


@pytest.mark.parametrize("peer_first", [False, True], ids=["local-first", "peer-first"])
def test_shutdown_command_is_first_new_mutation_and_binds_every_deadline(
    monkeypatch: pytest.MonkeyPatch,
    peer_first: bool,
) -> None:
    async def scenario() -> None:
        peer_payload = _NORMAL_CLOSE_PAYLOAD + b"peer-ack"
        peer_close = Frame(Opcode.CLOSE, peer_payload).serialize(mask=False)
        with TemporaryDirectory(prefix="ry-v49e-command-order-") as directory:
            harness = await _build_harness(
                Path(directory),
                first_frame=peer_close if peer_first else b"",
            )
            try:
                await _establish_and_activate(harness)
                actor = _actor(harness)
                if peer_first:
                    await harness.runtime.process_next_ingress_v49d(timeout_seconds=1)
                    assert await _read_client_frames(harness, count=1) == (
                        (int(Opcode.CLOSE), peer_payload),
                    )

                prefix = actor.events
                deadline_calls = _install_owner_deadline_spies(monkeypatch, harness)
                generic_tls_calls = 0
                original_generic = (
                    PhysicalTransportSessionActorV49C.prepare_tls_ciphertext
                )

                async def reject_local_generic_tls(
                    current: PhysicalTransportSessionActorV49C,
                    payload: TlsCiphertextPreparedPayloadV49C,
                ) -> TransportActorEventV49C:
                    nonlocal generic_tls_calls
                    if current is actor:
                        generic_tls_calls += 1
                    return await original_generic(current, payload)

                monkeypatch.setattr(
                    PhysicalTransportSessionActorV49C,
                    "prepare_tls_ciphertext",
                    reject_local_generic_tls,
                )

                answer: asyncio.Task[tuple[tuple[int, bytes], ...]] | None = None
                if not peer_first:

                    async def answer_close() -> tuple[tuple[int, bytes], ...]:
                        frames = await _read_client_frames(harness, count=1)
                        await _push_server_bytes(harness, peer_close)
                        return frames

                    answer = asyncio.create_task(answer_close())

                termination = await harness.runtime.shutdown_current_v49e(
                    timeout_seconds=30
                )
                if answer is not None:
                    assert await answer == ((int(Opcode.CLOSE), _NORMAL_CLOSE_PAYLOAD),)

                assert actor.events[len(prefix)].event_kind is (
                    TransportActorEventKindV49C.LOCAL_SHUTDOWN_COMMAND_STARTED
                )
                command_event = _command_event(actor)
                command = _assert_command_shape(command_event, timeout_seconds=30)
                _assert_command_linkage(
                    actor,
                    command_event,
                    local_first=not peer_first,
                )
                _assert_owner_deadline_calls(
                    deadline_calls,
                    deadline_ns=command.shutdown_deadline_monotonic_ns,
                    local_first=not peer_first,
                )
                assert generic_tls_calls == 0
                assert termination.reason in {
                    TransportSessionTerminationReasonV4.LOCAL_CLOSE,
                    TransportSessionTerminationReasonV4.REMOTE_CLOSE,
                }
                assert harness.runtime.state is PhysicalTransportRuntimeStateV4.FENCED
                _assert_one_terminal_pair(
                    harness, outcome=TerminalOutcomeV49C.CLEAN_ALL_LAYERS
                )
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_command_journal_failure_rolls_back_and_fault_latches_before_effects() -> None:
    armed = False

    def fail(stage: str) -> None:
        if armed and stage == "after_transport_actor_event_v49c_insert":
            raise RuntimeError("scripted-command-journal-failure")

    async def scenario() -> None:
        nonlocal armed
        with TemporaryDirectory(prefix="ry-v49e-command-journal-") as directory:
            harness = await _build_harness(Path(directory), fault_injector=fail)
            try:
                await _establish_and_activate(harness)
                actor = _actor(harness)
                prefix = actor.events
                armed = True

                with pytest.raises(PhysicalTransportRuntimeV4FaultLatched):
                    await harness.runtime.shutdown_current_v49e(timeout_seconds=30)

                assert actor.events == prefix
                assert harness.runtime.state is (
                    PhysicalTransportRuntimeStateV4.FAULT_LATCHED
                )
                assert harness.owner._closed  # noqa: SLF001
                assert harness.server.application_reads.empty()
                assert (
                    _typed_count(harness.store, "transport_session_terminations") == 0
                )
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_command_start_cancellation_fault_latches_without_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        with TemporaryDirectory(prefix="ry-v49e-command-cancel-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                await _establish_and_activate(harness)
                actor = _actor(harness)
                prefix = actor.events

                async def cancel_start(
                    current: PhysicalTransportSessionActorV49C,
                    *,
                    timeout_seconds: int,
                ) -> TransportActorEventV49C:
                    assert current is actor
                    assert timeout_seconds == 30
                    raise asyncio.CancelledError

                monkeypatch.setattr(
                    PhysicalTransportSessionActorV49C,
                    "start_local_shutdown_command_v49e",
                    cancel_start,
                )
                with pytest.raises(asyncio.CancelledError):
                    await harness.runtime.shutdown_current_v49e(timeout_seconds=30)

                assert actor.events == prefix
                assert harness.runtime.state is (
                    PhysicalTransportRuntimeStateV4.FAULT_LATCHED
                )
                assert harness.owner._closed  # noqa: SLF001
                assert harness.server.application_reads.empty()
                assert (
                    _typed_count(harness.store, "transport_session_terminations") == 0
                )
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_equal_but_substituted_command_return_fault_latches_without_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = PhysicalTransportSessionActorV49C.start_local_shutdown_command_v49e

    async def scenario() -> None:
        with TemporaryDirectory(prefix="ry-v49e-command-substitute-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                await _establish_and_activate(harness)
                actor = _actor(harness)
                old_count = len(actor.events)

                async def substitute_result(
                    current: PhysicalTransportSessionActorV49C,
                    *,
                    timeout_seconds: int,
                ) -> TransportActorEventV49C:
                    committed = await original(
                        current,
                        timeout_seconds=timeout_seconds,
                    )
                    copied = TransportActorEventV49C.from_mapping(committed.as_dict())
                    assert copied == committed and copied is not committed
                    return copied

                monkeypatch.setattr(
                    PhysicalTransportSessionActorV49C,
                    "start_local_shutdown_command_v49e",
                    substitute_result,
                )
                with pytest.raises(PhysicalTransportRuntimeV4FaultLatched):
                    await harness.runtime.shutdown_current_v49e(timeout_seconds=30)

                assert len(actor.events) == old_count + 1
                assert actor.events[-1].event_kind is (
                    TransportActorEventKindV49C.LOCAL_SHUTDOWN_COMMAND_STARTED
                )
                assert harness.runtime.state is (
                    PhysicalTransportRuntimeStateV4.FAULT_LATCHED
                )
                assert harness.owner._closed  # noqa: SLF001
                assert harness.server.application_reads.empty()
                assert (
                    _typed_count(harness.store, "transport_session_terminations") == 0
                )
            finally:
                await harness.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("mode", "outcome", "cause_code"),
    [
        (
            "both_due",
            TerminalOutcomeV49C.TIMEOUT,
            V49E_LOCAL_SHUTDOWN_COMMAND_DEADLINE_EXPIRED_CAUSE,
        ),
        (
            "xor",
            TerminalOutcomeV49C.FATAL,
            V49E_LOCAL_SHUTDOWN_CLOCK_DISAGREEMENT_CAUSE,
        ),
    ],
)
def test_command_deadline_requires_both_clocks_and_xor_is_fatal(
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    outcome: TerminalOutcomeV49C,
    cause_code: str,
) -> None:
    async def scenario() -> None:
        with TemporaryDirectory(prefix=f"ry-v49e-command-{mode}-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                await _establish_and_activate(harness)
                actor = _actor(harness)
                prefix_count = len(actor.events)
                _install_post_command_clock(
                    monkeypatch,
                    actor,
                    harness.store,
                    mode=mode,
                )
                owner_prepare_calls = 0
                original_prepare = (
                    LinuxSocketOwnerV4.prepare_local_websocket_close_wire_v49e
                )

                async def forbidden_prepare(
                    current: LinuxSocketOwnerV4,
                    *,
                    deadline_ns: int,
                ) -> Any:
                    nonlocal owner_prepare_calls
                    if current is harness.owner:
                        owner_prepare_calls += 1
                    return await original_prepare(current, deadline_ns=deadline_ns)

                monkeypatch.setattr(
                    LinuxSocketOwnerV4,
                    "prepare_local_websocket_close_wire_v49e",
                    forbidden_prepare,
                )
                termination = await harness.runtime.shutdown_current_v49e(
                    timeout_seconds=1
                )

                assert actor.events[prefix_count].event_kind is (
                    TransportActorEventKindV49C.LOCAL_SHUTDOWN_COMMAND_STARTED
                )
                _assert_command_shape(_command_event(actor), timeout_seconds=1)
                assert owner_prepare_calls == 0
                assert termination.reason is (
                    TransportSessionTerminationReasonV4.TRANSPORT_ERROR
                )
                assert harness.runtime.state is PhysicalTransportRuntimeStateV4.FENCED
                _assert_one_terminal_pair(
                    harness,
                    outcome=outcome,
                    cause_code=cause_code,
                )
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_runtime_rejects_actor_callback_deadline_extension_before_owner_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_authorize = (
        PhysicalTransportSessionActorV49C.authorize_local_websocket_close_v49e
    )

    async def scenario() -> None:
        with TemporaryDirectory(prefix="ry-v49e-command-extend-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                await _establish_and_activate(harness)
                actor = _actor(harness)
                owner_calls = 0
                original_owner = (
                    LinuxSocketOwnerV4.prepare_local_websocket_close_wire_v49e
                )

                async def owner_prepare(
                    current: LinuxSocketOwnerV4,
                    *,
                    deadline_ns: int,
                ) -> Any:
                    nonlocal owner_calls
                    if current is harness.owner:
                        owner_calls += 1
                    return await original_owner(current, deadline_ns=deadline_ns)

                async def extend_deadline(
                    current: PhysicalTransportSessionActorV49C,
                    command_event: TransportActorEventV49C,
                    *,
                    prepare_effect: Any,
                ) -> tuple[
                    TransportActorEventV49C,
                    TransportActorEventV49C,
                    TransportActorEventV49C,
                ]:
                    async def hostile_effect(*, deadline_ns: int) -> Any:
                        return await prepare_effect(deadline_ns=deadline_ns + 1)

                    return await original_authorize(
                        current,
                        command_event,
                        prepare_effect=hostile_effect,
                    )

                monkeypatch.setattr(
                    LinuxSocketOwnerV4,
                    "prepare_local_websocket_close_wire_v49e",
                    owner_prepare,
                )
                monkeypatch.setattr(
                    PhysicalTransportSessionActorV49C,
                    "authorize_local_websocket_close_v49e",
                    extend_deadline,
                )
                termination = await harness.runtime.shutdown_current_v49e(
                    timeout_seconds=30
                )

                assert owner_calls == 0
                assert termination.reason is (
                    TransportSessionTerminationReasonV4.TRANSPORT_ERROR
                )
                assert all(
                    type(event.payload) is not OutboundWirePreparedPayloadV49C
                    for event in actor.events
                )
                _assert_one_terminal_pair(harness, outcome=TerminalOutcomeV49C.FATAL)
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_positive_terminal_ingress_returned_after_command_cutoff_is_not_committed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        peer_close = Frame(
            Opcode.CLOSE,
            _NORMAL_CLOSE_PAYLOAD + b"physically-late",
        ).serialize(mask=False)
        with TemporaryDirectory(prefix="ry-v49e-command-late-ingress-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                await _establish_and_activate(harness)
                actor = _actor(harness)
                original_read = LinuxSocketOwnerV4.read_terminal_close_ingress_v49e
                read_calls = 0

                async def return_after_cutoff(
                    current: LinuxSocketOwnerV4,
                    *,
                    deadline_ns: int,
                ) -> Any:
                    nonlocal read_calls
                    pending = await original_read(current, deadline_ns=deadline_ns)
                    if current is harness.owner:
                        read_calls += 1
                        harness.store._clock = (  # noqa: SLF001
                            lambda: T0 + timedelta(minutes=10)
                        )
                        command_event = actor.local_shutdown_command_event_v49e
                        assert command_event is not None
                        command = command_event.payload
                        assert type(command) is LocalShutdownCommandStartedPayloadV49E
                        cursor = 0

                        def due_observation() -> tuple[Any, int]:
                            nonlocal cursor
                            cursor += 1
                            return (
                                command.shutdown_deadline_at
                                + timedelta(microseconds=cursor),
                                command.shutdown_deadline_monotonic_ns + cursor,
                            )

                        actor._observation_clock = due_observation  # noqa: SLF001
                        actor._observation_batch_clock = (  # noqa: SLF001
                            lambda count: tuple(due_observation() for _ in range(count))
                        )
                    return pending

                monkeypatch.setattr(
                    LinuxSocketOwnerV4,
                    "read_terminal_close_ingress_v49e",
                    return_after_cutoff,
                )

                async def send_late_peer_close() -> tuple[tuple[int, bytes], ...]:
                    frames = await _read_client_frames(harness, count=1)
                    await _push_server_bytes(harness, peer_close)
                    return frames

                answer = asyncio.create_task(send_late_peer_close())
                termination = await harness.runtime.shutdown_current_v49e(
                    timeout_seconds=30
                )
                assert await answer == ((int(Opcode.CLOSE), _NORMAL_CLOSE_PAYLOAD),)

                assert read_calls == 1
                command = _command_event(actor)
                command_index = actor.events.index(command)
                assert all(
                    event.event_kind
                    not in {
                        TransportActorEventKindV49C.RAW_INGRESS_COMMITTED,
                        TransportActorEventKindV49C.PARSER_TRANSITION,
                    }
                    for event in actor.events[command_index + 1 :]
                )
                assert not actor.terminal_state.ws_close_received
                assert termination.reason is (
                    TransportSessionTerminationReasonV4.TRANSPORT_ERROR
                )
                _assert_one_terminal_pair(
                    harness,
                    outcome=TerminalOutcomeV49C.TIMEOUT,
                    cause_code=V49E_LOCAL_SHUTDOWN_COMMAND_DEADLINE_EXPIRED_CAUSE,
                )
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_automatic_close_conclusive_timeout_is_not_reported_as_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_send = PhysicalTransportSessionActorV49C.send_oldest_ciphertext

    async def scenario() -> None:
        peer_close = Frame(
            Opcode.CLOSE,
            _NORMAL_CLOSE_PAYLOAD + b"automatic-timeout",
        ).serialize(mask=False)
        with TemporaryDirectory(prefix="ry-v49e-auto-conclusive-") as directory:
            harness = await _build_harness(Path(directory), first_frame=peer_close)
            try:
                await _establish_and_activate(harness)
                actor = _actor(harness)

                async def force_due_before_send(
                    current: PhysicalTransportSessionActorV49C,
                    **kwargs: Any,
                ) -> Any:
                    if current is actor:
                        wire_id = current.oldest_outbound_wire_event_id
                        assert wire_id is not None
                        wire_event = next(
                            event
                            for event in current.events
                            if event.transport_actor_event_id == wire_id
                        )
                        wire = wire_event.payload
                        assert type(wire) is OutboundWirePreparedPayloadV49C
                        assert wire.wire_origin is (
                            OutboundWireOriginV49C.AUTOMATIC_PROTOCOL
                        )
                        assert wire.logical_opcode is WebSocketOpcodeV49C.CLOSE
                        harness.store._clock = (  # noqa: SLF001
                            lambda: T0 + timedelta(minutes=10)
                        )
                        cursor = 0

                        def due_observation() -> tuple[Any, int]:
                            nonlocal cursor
                            cursor += 1
                            return (
                                wire.send_not_after + timedelta(microseconds=cursor),
                                wire.send_not_after_monotonic_ns + cursor,
                            )

                        current._observation_clock = due_observation  # noqa: SLF001
                    return await original_send(current, **kwargs)

                monkeypatch.setattr(
                    PhysicalTransportSessionActorV49C,
                    "send_oldest_ciphertext",
                    force_due_before_send,
                )
                try:
                    await harness.runtime.process_next_ingress_v49d(timeout_seconds=1)
                except BaseException as exc:
                    assert type(exc) is (
                        PhysicalTransportAutomaticCloseTerminalFailureV49E
                    )
                    assert not isinstance(exc, PhysicalTransportDispatchUnknownV4)
                    assert exc.terminal_outcome == TerminalOutcomeV49C.TIMEOUT.value
                    assert exc.cause_code == (
                        V49E_WEBSOCKET_CLOSE_DEADLINE_EXPIRED_CAUSE
                    )
                    assert not exc.kernel_send_attempt_recorded
                else:
                    pytest.fail("conclusive automatic Close timeout was not surfaced")

                assert harness.runtime.state is PhysicalTransportRuntimeStateV4.FENCED
                _assert_one_terminal_pair(
                    harness,
                    outcome=TerminalOutcomeV49C.TIMEOUT,
                    cause_code=V49E_WEBSOCKET_CLOSE_DEADLINE_EXPIRED_CAUSE,
                )
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_automatic_close_ambiguous_post_wal_failure_remains_unknown_send(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        peer_close = Frame(
            Opcode.CLOSE,
            _NORMAL_CLOSE_PAYLOAD + b"automatic-unknown",
        ).serialize(mask=False)
        with TemporaryDirectory(prefix="ry-v49e-auto-unknown-") as directory:
            harness = await _build_harness(Path(directory), first_frame=peer_close)
            try:
                await _establish_and_activate(harness)
                original = LinuxSocketOwnerV4.send_prepared_tls_ciphertext_once_v49c

                async def ambiguous_send(
                    current: LinuxSocketOwnerV4,
                    *args: Any,
                    **kwargs: Any,
                ) -> int:
                    if current is harness.owner:
                        raise RuntimeError("scripted ambiguous post-WAL send failure")
                    return await original(current, *args, **kwargs)

                monkeypatch.setattr(
                    LinuxSocketOwnerV4,
                    "send_prepared_tls_ciphertext_once_v49c",
                    ambiguous_send,
                )
                with pytest.raises(PhysicalTransportDispatchUnknownV4):
                    await harness.runtime.process_next_ingress_v49d(timeout_seconds=1)

                assert harness.runtime.state is PhysicalTransportRuntimeStateV4.FENCED
                _assert_one_terminal_pair(
                    harness,
                    outcome=TerminalOutcomeV49C.UNKNOWN_SEND,
                )
            finally:
                await harness.close()

    asyncio.run(scenario())

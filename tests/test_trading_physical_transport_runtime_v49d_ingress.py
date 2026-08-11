from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from websockets.frames import Frame, Opcode

from riskyieldmm.trading.physical_transport_actor_v49c import (
    TransportActorEventKindV49C,
    WebSocketOpcodeV49C,
    validate_transport_actor_chain_v49c,
)
from riskyieldmm.trading.physical_transport_runtime_v4 import (
    PhysicalTransportDispatchUnknownV4,
    PhysicalTransportRuntimeStateV4,
    PhysicalTransportRuntimeV4,
    PhysicalTransportRuntimeV4FaultLatched,
    PhysicalTransportRuntimeV4StateError,
)
from tests.test_trading_physical_transport_runtime_v49b import (
    _build_harness,
    _establish,
)
from tests.test_trading_physical_transport_runtime_v49c_egress import (
    _bind_projection_clock_to_owner,
)

pytestmark = pytest.mark.skipif(
    sys.platform != "linux", reason="Linux-only exact V4.9D ingress tests"
)


def _actor_events(harness: object):
    actor = harness.runtime._transport_session_actor_v49c  # type: ignore[attr-defined]  # noqa: SLF001
    assert actor is not None
    return actor.events


async def _establish_and_activate(harness: object) -> None:
    await _establish(harness)  # type: ignore[arg-type]
    _bind_projection_clock_to_owner(harness)
    await harness.runtime.activate_causal_transport_actor_v49c()  # type: ignore[attr-defined]


async def _push_server_bytes(harness: object, data: bytes) -> None:
    writers = harness.server.writers  # type: ignore[attr-defined]
    assert len(writers) == 1
    writers[0].write(data)
    await writers[0].drain()


def _pop_client_frame(buffer: bytes) -> tuple[tuple[int, bytes], bytes] | None:
    """Decode one complete masked client frame from a TCP byte stream."""

    if len(buffer) < 2:
        return None
    assert buffer[1] & 0x80
    payload_length = buffer[1] & 0x7F
    cursor = 2
    if payload_length == 126:
        if len(buffer) < cursor + 2:
            return None
        payload_length = int.from_bytes(buffer[cursor : cursor + 2], "big")
        cursor += 2
    elif payload_length == 127:
        if len(buffer) < cursor + 8:
            return None
        payload_length = int.from_bytes(buffer[cursor : cursor + 8], "big")
        cursor += 8
    if len(buffer) < cursor + 4 + payload_length:
        return None
    mask = buffer[cursor : cursor + 4]
    cursor += 4
    end = cursor + payload_length
    payload = bytes(
        value ^ mask[index % 4] for index, value in enumerate(buffer[cursor:end])
    )
    return (buffer[0] & 0x0F, payload), buffer[end:]


async def _read_client_frames(
    harness: object, *, count: int
) -> tuple[tuple[int, bytes], ...]:
    frames: list[tuple[int, bytes]] = []
    buffered = b""
    while len(frames) < count:
        decoded = _pop_client_frame(buffered)
        if decoded is None:
            buffered += await asyncio.wait_for(
                harness.server.application_reads.get(),  # type: ignore[attr-defined]
                timeout=2,
            )
            continue
        frame, buffered = decoded
        frames.append(frame)
    assert buffered == b""
    return tuple(frames)


def test_v49d_ingress_api_exposes_only_timeout() -> None:
    assert tuple(
        inspect.signature(
            PhysicalTransportRuntimeV4.process_next_ingress_v49d
        ).parameters
    ) == ("self", "timeout_seconds")


def test_v49d_coalesced_ping_is_durable_and_precedes_subscription() -> None:
    async def scenario() -> None:
        ping_payload = b"durable-before-subscribe"
        ping = Frame(Opcode.PING, ping_payload).serialize(mask=False)
        with TemporaryDirectory(prefix="ry-v49d-ping-") as directory:
            harness = await _build_harness(Path(directory), first_frame=ping)
            try:
                await _establish_and_activate(harness)
                assert harness.runtime.has_initial_pending_raw_ingress_v49c

                progress = await harness.runtime.process_next_ingress_v49d(
                    timeout_seconds=1
                )

                assert progress.used_initial_pending_ingress
                assert progress.committed_raw_octets == len(ping)
                assert len(progress.parser_event_ids) == 1
                assert len(progress.automatic_dispatch_completion_event_ids) == 1
                assert progress.automatic_output_source_parser_event_ids == (
                    progress.parser_event_ids[0],
                )
                assert progress.automatic_output_wire_chunk_counts == (1,)
                assert progress.automatic_protocol_output_frames == (
                    ("PONG", ping_payload),
                )
                assert len(progress.automatic_protocol_output_chunks) == 1
                assert progress.retained_incomplete_octets == 0
                assert progress.websocket_parser_state == "OPEN"
                assert not harness.runtime.has_initial_pending_raw_ingress_v49c
                events_before_subscription = _actor_events(harness)
                assert events_before_subscription[0].event_kind is (
                    TransportActorEventKindV49C.RAW_INGRESS_COMMITTED
                )
                assert events_before_subscription[1].event_kind is (
                    TransportActorEventKindV49C.PARSER_TRANSITION
                )
                assert events_before_subscription[-1].event_kind is (
                    TransportActorEventKindV49C.OUTBOUND_DISPATCH_COMPLETED
                )
                validate_transport_actor_chain_v49c(events_before_subscription)

                await harness.runtime.dispatch_subscription_v49c(
                    idempotency_key="v49d-after-pong"
                )
                intent = harness.runtime._intent  # noqa: SLF001
                assert intent is not None
                assert await _read_client_frames(harness, count=2) == (
                    (int(Opcode.PONG), ping_payload),
                    (int(Opcode.TEXT), intent.command_bytes),
                )
                assert harness.runtime.state is (
                    PhysicalTransportRuntimeStateV4.AWAITING_ACK
                )

                report = harness.store.verify()
                assert report.raw_ingress_commit_count == 1
                assert report.transport_actor_event_count == len(_actor_events(harness))
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_v49d_two_coalesced_pings_emit_ordered_pongs() -> None:
    async def scenario() -> None:
        first_payload = b"first"
        second_payload = b"second"
        ingress = Frame(Opcode.PING, first_payload).serialize(mask=False) + Frame(
            Opcode.PING, second_payload
        ).serialize(mask=False)
        with TemporaryDirectory(prefix="ry-v49d-two-pings-") as directory:
            harness = await _build_harness(Path(directory), first_frame=ingress)
            try:
                await _establish_and_activate(harness)
                progress = await harness.runtime.process_next_ingress_v49d(
                    timeout_seconds=1
                )

                assert progress.committed_raw_octets == len(ingress)
                assert len(progress.parser_event_ids) == 2
                assert len(progress.automatic_dispatch_completion_event_ids) == 2
                assert progress.automatic_output_source_parser_event_ids == (
                    progress.parser_event_ids
                )
                assert progress.automatic_output_wire_chunk_counts == (1, 1)
                assert progress.automatic_protocol_output_frames == (
                    ("PONG", first_payload),
                    ("PONG", second_payload),
                )
                assert await _read_client_frames(harness, count=2) == (
                    (int(Opcode.PONG), first_payload),
                    (int(Opcode.PONG), second_payload),
                )
                events = _actor_events(harness)
                parser_indices = [
                    index
                    for index, event in enumerate(events)
                    if event.event_kind is TransportActorEventKindV49C.PARSER_TRANSITION
                ]
                completion_indices = [
                    index
                    for index, event in enumerate(events)
                    if event.event_kind
                    is TransportActorEventKindV49C.OUTBOUND_DISPATCH_COMPLETED
                ]
                assert len(parser_indices) == len(completion_indices) == 2
                assert (
                    parser_indices[0]
                    < completion_indices[0]
                    < parser_indices[1]
                    < completion_indices[1]
                )
                validate_transport_actor_chain_v49c(events)
                assert harness.store.verify().raw_ingress_commit_count == 1
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_v49d_failure_after_completed_pong_is_not_dispatch_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        first_payload = b"completed-before-failure"
        second_payload = b"must-not-dispatch"
        ingress = Frame(Opcode.PING, first_payload).serialize(mask=False) + Frame(
            Opcode.PING, second_payload
        ).serialize(mask=False)
        with TemporaryDirectory(prefix="ry-v49d-resolved-attempt-") as directory:
            harness = await _build_harness(Path(directory), first_frame=ingress)
            try:
                await _establish_and_activate(harness)
                original_parse = harness.owner.parse_next_durable_unit_v49d
                parse_calls = 0

                async def fail_second_parser_unit():
                    nonlocal parse_calls
                    parse_calls += 1
                    if parse_calls == 2:
                        assert (
                            sum(
                                event.event_kind
                                is TransportActorEventKindV49C.OUTBOUND_DISPATCH_COMPLETED
                                for event in _actor_events(harness)
                            )
                            == 1
                        )
                        raise RuntimeError("injected second parser unit failure")
                    return await original_parse()

                monkeypatch.setattr(
                    harness.owner,
                    "parse_next_durable_unit_v49d",
                    fail_second_parser_unit,
                )

                with pytest.raises(PhysicalTransportRuntimeV4FaultLatched) as caught:
                    await harness.runtime.process_next_ingress_v49d(timeout_seconds=1)

                assert type(caught.value) is PhysicalTransportRuntimeV4FaultLatched
                assert not isinstance(caught.value, PhysicalTransportDispatchUnknownV4)
                assert parse_calls == 2
                assert harness.runtime.state is (
                    PhysicalTransportRuntimeStateV4.FAULT_LATCHED
                )
                actor = harness.runtime._transport_session_actor_v49c  # noqa: SLF001
                assert actor is not None
                assert actor.unresolved_kernel_send_attempt_event_id_v49f is None
                assert actor.terminal_state.pending_send_attempt_id is None
                events = _actor_events(harness)
                assert (
                    sum(
                        event.event_kind
                        is TransportActorEventKindV49C.OUTBOUND_DISPATCH_COMPLETED
                        for event in events
                    )
                    == 1
                )
                assert await _read_client_frames(harness, count=1) == (
                    (int(Opcode.PONG), first_payload),
                )
                validate_transport_actor_chain_v49c(events)
                report = harness.store.verify()
                assert report.raw_ingress_commit_count == 1
                assert report.transport_actor_event_count == len(events)
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_v49d_post_send_completion_persistence_failure_is_resolved_not_unknown() -> (
    None
):
    async def scenario() -> None:
        actor_insert_count = 0

        def fault(stage: str) -> None:
            nonlocal actor_insert_count
            if stage != "after_transport_actor_event_v49c_insert":
                return
            actor_insert_count += 1
            if actor_insert_count == 10:
                raise RuntimeError("injected dispatch-completion persistence failure")

        payload = b"kernel-accepted-before-completion-fault"
        ping = Frame(Opcode.PING, payload).serialize(mask=False)
        with TemporaryDirectory(prefix="ry-v49d-post-send-fault-") as directory:
            harness = await _build_harness(
                Path(directory), first_frame=ping, fault_injector=fault
            )
            try:
                await _establish_and_activate(harness)

                with pytest.raises(
                    PhysicalTransportRuntimeV4FaultLatched,
                    match=(
                        "after a conclusive kernel send result.*before "
                        "authoritative dispatch completion"
                    ),
                ) as caught:
                    await harness.runtime.process_next_ingress_v49d(timeout_seconds=1)

                assert type(caught.value) is PhysicalTransportRuntimeV4FaultLatched
                assert not isinstance(caught.value, PhysicalTransportDispatchUnknownV4)
                assert actor_insert_count == 10
                assert harness.runtime.state is (
                    PhysicalTransportRuntimeStateV4.FAULT_LATCHED
                )
                actor = harness.runtime._transport_session_actor_v49c  # noqa: SLF001
                assert actor is not None
                assert actor.unresolved_kernel_send_attempt_event_id_v49f is None
                assert actor.terminal_state.pending_send_attempt_id is None
                assert actor.oldest_outbound_wire_event_id is not None
                assert actor.wire_queue_event_count_v49f == 1
                events = _actor_events(harness)
                assert (
                    sum(
                        event.event_kind
                        is TransportActorEventKindV49C.KERNEL_SEND_RESULT
                        for event in events
                    )
                    == 1
                )
                assert (
                    sum(
                        event.event_kind
                        is TransportActorEventKindV49C.OUTBOUND_DISPATCH_COMPLETED
                        for event in events
                    )
                    == 0
                )
                assert await _read_client_frames(harness, count=1) == (
                    (int(Opcode.PONG), payload),
                )
                validate_transport_actor_chain_v49c(events)
                report = harness.store.verify()
                assert report.raw_ingress_commit_count == 1
                assert report.transport_actor_event_count == len(events)
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_v49d_cross_raw_split_retains_then_parses_exactly_once() -> None:
    async def scenario() -> None:
        payload = b"cross-raw-runtime"
        ping = Frame(Opcode.PING, payload).serialize(mask=False)
        split_at = 5
        with TemporaryDirectory(prefix="ry-v49d-cross-raw-") as directory:
            harness = await _build_harness(Path(directory), first_frame=ping[:split_at])
            try:
                await _establish_and_activate(harness)
                first = await harness.runtime.process_next_ingress_v49d(
                    timeout_seconds=1
                )
                assert first.used_initial_pending_ingress
                assert first.parser_event_ids == ()
                assert first.automatic_dispatch_completion_event_ids == ()
                assert first.retained_incomplete_octets == split_at
                assert [event.event_kind for event in _actor_events(harness)] == [
                    TransportActorEventKindV49C.RAW_INGRESS_COMMITTED
                ]

                await _push_server_bytes(harness, ping[split_at:])
                second = await harness.runtime.process_next_ingress_v49d(
                    timeout_seconds=1
                )
                assert not second.used_initial_pending_ingress
                assert len(second.parser_event_ids) == 1
                assert len(second.automatic_dispatch_completion_event_ids) == 1
                assert second.retained_incomplete_octets == 0
                assert await _read_client_frames(harness, count=1) == (
                    (int(Opcode.PONG), payload),
                )
                events = _actor_events(harness)
                raw_ids = tuple(
                    event.payload.raw_ingress_commit_id
                    for event in events
                    if event.event_kind
                    is TransportActorEventKindV49C.RAW_INGRESS_COMMITTED
                )
                parser_events = tuple(
                    event
                    for event in events
                    if event.event_kind is TransportActorEventKindV49C.PARSER_TRANSITION
                )
                assert raw_ids == (
                    first.raw_ingress_commit_id,
                    second.raw_ingress_commit_id,
                )
                assert len(parser_events) == 1
                assert (
                    tuple(
                        source.raw_ingress_commit_id
                        for source in parser_events[0].payload.source_slices
                    )
                    == raw_ids
                )
                assert (
                    sum(
                        event.event_kind
                        is TransportActorEventKindV49C.RAW_INGRESS_COMMITTED
                        for event in events
                    )
                    == 2
                )
                assert (
                    sum(
                        event.event_kind
                        is TransportActorEventKindV49C.PARSER_TRANSITION
                        for event in events
                    )
                    == 1
                )
                validate_transport_actor_chain_v49c(events)
                report = harness.store.verify()
                assert report.raw_ingress_commit_count == 2
                assert report.transport_actor_event_count == len(events)
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_v49d_data_frame_produces_no_automatic_output() -> None:
    async def scenario() -> None:
        data_payload = b'{"topic":"orderbook.1.BTCUSDT"}'
        data = Frame(Opcode.TEXT, data_payload).serialize(mask=False)
        with TemporaryDirectory(prefix="ry-v49d-data-") as directory:
            harness = await _build_harness(Path(directory), first_frame=data)
            try:
                await _establish_and_activate(harness)
                progress = await harness.runtime.process_next_ingress_v49d(
                    timeout_seconds=1
                )

                assert len(progress.parser_event_ids) == 1
                assert progress.automatic_dispatch_completion_event_ids == ()
                assert progress.websocket_parser_state == "OPEN"
                await asyncio.sleep(0.02)
                assert harness.server.application_reads.empty()

                await harness.runtime.dispatch_subscription_v49c(
                    idempotency_key="v49d-after-data"
                )
                intent = harness.runtime._intent  # noqa: SLF001
                assert intent is not None
                assert await _read_client_frames(harness, count=1) == (
                    (int(Opcode.TEXT), intent.command_bytes),
                )
                validate_transport_actor_chain_v49c(_actor_events(harness))
                assert harness.store.verify().raw_ingress_commit_count == 1
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_v49e_ack_receipt_uses_final_raw_clock_despite_parser_backlog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        with TemporaryDirectory(prefix="ry-v49e-raw-receipt-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                await _establish_and_activate(harness)
                await harness.runtime.dispatch_subscription_v49c(
                    idempotency_key="v49e-raw-receipt-subscription"
                )
                intent = harness.runtime._intent  # noqa: SLF001
                assert intent is not None
                assert await _read_client_frames(harness, count=1) == (
                    (int(Opcode.TEXT), intent.command_bytes),
                )
                subscription_completion = next(
                    event
                    for event in reversed(_actor_events(harness))
                    if event.event_kind
                    is TransportActorEventKindV49C.OUTBOUND_DISPATCH_COMPLETED
                )
                deadline_delta = (
                    intent.ack_not_after - subscription_completion.payload.completed_at
                )
                ack_not_after_monotonic_ns = (
                    subscription_completion.payload.completed_monotonic_ns
                    + (
                        (deadline_delta.days * 86_400 + deadline_delta.seconds)
                        * 1_000_000_000
                    )
                    + deadline_delta.microseconds * 1_000
                )

                raw_ack = json.dumps(
                    {
                        "success": True,
                        "ret_msg": "",
                        "conn_id": "v49e-raw-clock-connection",
                        "req_id": intent.request_id,
                        "op": "subscribe",
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8")
                split_at = len(raw_ack) // 2
                ingress = b"".join(
                    (
                        Frame(
                            Opcode.TEXT,
                            raw_ack[:split_at],
                            fin=False,
                        ).serialize(mask=False),
                        Frame(Opcode.PING, b"interleaved").serialize(mask=False),
                        Frame(
                            Opcode.CONT,
                            raw_ack[split_at:],
                            fin=True,
                        ).serialize(mask=False),
                    )
                )

                original_parse = harness.owner.parse_next_durable_unit_v49d

                async def parse_after_backlog() -> object:
                    parsed = await original_parse()
                    await asyncio.sleep(0.05)
                    return parsed

                monkeypatch.setattr(
                    harness.owner,
                    "parse_next_durable_unit_v49d",
                    parse_after_backlog,
                )
                await _push_server_bytes(harness, ingress)
                progress = await harness.runtime.process_next_ingress_v49d(
                    timeout_seconds=1
                )

                assert harness.runtime.state is (
                    PhysicalTransportRuntimeStateV4.ACK_BOUND
                )
                assert len(progress.parser_event_ids) == 3
                assert len(progress.automatic_dispatch_completion_event_ids) == 1
                events = _actor_events(harness)
                raw_event = next(
                    event
                    for event in reversed(events)
                    if event.event_kind
                    is TransportActorEventKindV49C.RAW_INGRESS_COMMITTED
                )
                parser_events = tuple(
                    event
                    for event in events
                    if event.event_kind is TransportActorEventKindV49C.PARSER_TRANSITION
                )
                data_parser_events = tuple(
                    event
                    for event in parser_events
                    if event.payload.frame.opcode
                    in {
                        WebSocketOpcodeV49C.TEXT,
                        WebSocketOpcodeV49C.CONTINUATION,
                    }
                )
                ping_parser_event = next(
                    event
                    for event in parser_events
                    if event.payload.frame.opcode is WebSocketOpcodeV49C.PING
                )
                final_parser_event = data_parser_events[-1]
                application_event = next(
                    event
                    for event in events
                    if event.event_kind
                    is TransportActorEventKindV49C.APPLICATION_MESSAGE_COMMITTED
                )
                ack_event = next(
                    event
                    for event in events
                    if event.event_kind
                    is TransportActorEventKindV49C.SUBSCRIPTION_ACK_BOUND
                )
                application = application_event.payload
                ack = ack_event.payload

                assert application.source_parser_event_ids == tuple(
                    event.transport_actor_event_id for event in data_parser_events
                )
                assert ping_parser_event.transport_actor_event_id not in (
                    application.source_parser_event_ids
                )
                assert (
                    application.message_payload_sha256
                    == hashlib.sha256(raw_ack).hexdigest()
                )
                assert application.received_at == raw_event.payload.received_at
                assert application.received_monotonic_ns == (
                    raw_event.payload.received_monotonic_ns
                )
                assert ack.ack_received_at == raw_event.payload.received_at
                assert ack.ack_received_monotonic_ns == (
                    raw_event.payload.received_monotonic_ns
                )
                assert ack.ack_not_after == intent.ack_not_after
                assert ack.ack_not_after_monotonic_ns == (ack_not_after_monotonic_ns)
                assert raw_event.payload.received_at <= intent.ack_not_after
                assert raw_event.payload.received_monotonic_ns <= (
                    ack_not_after_monotonic_ns
                )
                assert final_parser_event.payload.processed_at > (
                    raw_event.payload.received_at
                )
                assert final_parser_event.recorded_at > raw_event.payload.received_at
                assert application.received_at != final_parser_event.recorded_at
                assert application.received_monotonic_ns < (
                    final_parser_event.recorded_monotonic_ns
                )
                assert (
                    final_parser_event.recorded_monotonic_ns
                    - application.received_monotonic_ns
                    >= 40_000_000
                )
                validate_transport_actor_chain_v49c(events)
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_v49d_close_is_answered_and_blocks_application_dispatch() -> None:
    async def scenario() -> None:
        close_payload = b"\x03\xe8normal"
        close = Frame(Opcode.CLOSE, close_payload).serialize(mask=False)
        with TemporaryDirectory(prefix="ry-v49d-close-") as directory:
            harness = await _build_harness(Path(directory), first_frame=close)
            try:
                await _establish_and_activate(harness)
                progress = await harness.runtime.process_next_ingress_v49d(
                    timeout_seconds=1
                )

                assert len(progress.parser_event_ids) == 1
                assert len(progress.automatic_dispatch_completion_event_ids) == 1
                assert progress.websocket_parser_state == "CLOSING"
                assert await _read_client_frames(harness, count=1) == (
                    (int(Opcode.CLOSE), close_payload),
                )
                with pytest.raises(
                    PhysicalTransportRuntimeV4StateError,
                    match="OPEN parser",
                ):
                    await harness.runtime.dispatch_subscription_v49c(
                        idempotency_key="v49d-after-close-forbidden"
                    )
                assert harness.runtime.state is (
                    PhysicalTransportRuntimeStateV4.SESSION_COMMITTED
                )
                events = _actor_events(harness)
                actor = harness.runtime._transport_session_actor_v49c  # noqa: SLF001
                assert actor is not None
                assert actor.terminal_state.ws_close_received
                assert actor.terminal_state.ws_close_sent
                validate_transport_actor_chain_v49c(events)
                report = harness.store.verify()
                assert report.raw_ingress_commit_count == 1
                assert report.transport_actor_event_count == len(events)
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_v49d_invalid_utf8_is_durable_close_1007_and_blocks_application() -> None:
    async def scenario() -> None:
        invalid_text = Frame(Opcode.TEXT, b"invalid:\xff").serialize(mask=False)
        with TemporaryDirectory(prefix="ry-v49d-invalid-utf8-") as directory:
            harness = await _build_harness(Path(directory), first_frame=invalid_text)
            try:
                await _establish_and_activate(harness)
                progress = await harness.runtime.process_next_ingress_v49d(
                    timeout_seconds=1
                )

                assert len(progress.parser_event_ids) == 1
                assert len(progress.automatic_dispatch_completion_event_ids) == 1
                assert progress.websocket_parser_state == "FAILED"
                ((opcode, close_payload),) = await _read_client_frames(harness, count=1)
                assert opcode == int(Opcode.CLOSE)
                assert int.from_bytes(close_payload[:2], "big") == 1007

                parser_events = tuple(
                    event
                    for event in _actor_events(harness)
                    if event.event_kind is TransportActorEventKindV49C.PARSER_TRANSITION
                )
                assert len(parser_events) == 1
                assert parser_events[0].payload.frame is None
                assert parser_events[0].payload.parser_error is not None
                with pytest.raises(
                    PhysicalTransportRuntimeV4StateError,
                    match="OPEN parser",
                ):
                    await harness.runtime.dispatch_subscription_v49c(
                        idempotency_key="v49d-after-invalid-utf8-forbidden"
                    )
                events = _actor_events(harness)
                validate_transport_actor_chain_v49c(events)
                report = harness.store.verify()
                assert report.raw_ingress_commit_count == 1
                assert report.transport_actor_event_count == len(events)
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_v49d_raw_storage_failure_occurs_before_parser_or_pong(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        def fault(stage: str) -> None:
            if stage == "after_raw_ingress_commit_insert":
                raise RuntimeError("injected RAW persistence failure")

        ping = Frame(Opcode.PING, b"must-not-parse").serialize(mask=False)
        with TemporaryDirectory(prefix="ry-v49d-raw-fault-") as directory:
            harness = await _build_harness(
                Path(directory), first_frame=ping, fault_injector=fault
            )
            try:
                await _establish_and_activate(harness)
                parse_calls = 0
                owner_type = type(harness.owner)
                original_parse = owner_type.parse_next_durable_unit_v49d

                async def observed_parse(self):
                    nonlocal parse_calls
                    parse_calls += 1
                    return await original_parse(self)

                monkeypatch.setattr(
                    owner_type,
                    "parse_next_durable_unit_v49d",
                    observed_parse,
                )
                with pytest.raises(
                    PhysicalTransportRuntimeV4FaultLatched,
                    match="before any durable kernel attempt",
                ):
                    await harness.runtime.process_next_ingress_v49d(timeout_seconds=1)

                assert parse_calls == 0
                assert harness.server.application_reads.empty()
                assert harness.runtime.state is (
                    PhysicalTransportRuntimeStateV4.FAULT_LATCHED
                )
                report = harness.store.verify()
                assert report.raw_ingress_commit_count == 0
                assert report.transport_actor_event_count == 0
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_v49d_parser_persistence_failure_occurs_before_socket_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        actor_insert_count = 0

        def fault(stage: str) -> None:
            nonlocal actor_insert_count
            if stage != "after_transport_actor_event_v49c_insert":
                return
            actor_insert_count += 1
            if actor_insert_count == 2:
                raise RuntimeError("injected parser persistence failure")

        ping = Frame(Opcode.PING, b"must-not-send").serialize(mask=False)
        with TemporaryDirectory(prefix="ry-v49d-parser-fault-") as directory:
            harness = await _build_harness(
                Path(directory), first_frame=ping, fault_injector=fault
            )
            try:
                await _establish_and_activate(harness)
                wire_calls = 0
                owner_type = type(harness.owner)
                original_wire = owner_type.prepare_pending_protocol_output_wire_v49c

                async def observed_wire(self, chunks):
                    nonlocal wire_calls
                    wire_calls += 1
                    return await original_wire(self, chunks)

                monkeypatch.setattr(
                    owner_type,
                    "prepare_pending_protocol_output_wire_v49c",
                    observed_wire,
                )
                with pytest.raises(
                    PhysicalTransportRuntimeV4FaultLatched,
                    match="before any durable kernel attempt",
                ):
                    await harness.runtime.process_next_ingress_v49d(timeout_seconds=1)

                assert actor_insert_count == 2
                assert wire_calls == 0
                assert harness.server.application_reads.empty()
                assert harness.runtime.state is (
                    PhysicalTransportRuntimeStateV4.FAULT_LATCHED
                )
                report = harness.store.verify()
                assert report.raw_ingress_commit_count == 1
                assert report.transport_actor_event_count == 1
            finally:
                await harness.close()

    asyncio.run(scenario())

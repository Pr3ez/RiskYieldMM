from __future__ import annotations

import asyncio
import base64
import hashlib
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Any

import pytest

from riskyieldmm.trading.canonical import sha256_digest
from riskyieldmm.trading.ledger_signing import Ed25519CheckpointSigner
from riskyieldmm.trading.physical_transport_control_runtime_v4 import (
    PhysicalTransportControlMediatorV4,
    PhysicalTransportControlProtocolDrainV4Error,
    PhysicalTransportControlRuntimeStateV4,
    PhysicalTransportControlRuntimeV4FaultLatched,
    PhysicalTransportControlStaleCallbackV4,
    validate_protocol_drain,
)
from riskyieldmm.trading.physical_transport_control_v4 import (
    OutboundControlDispatchDispositionV4,
    OutboundControlDispatchResultV4,
    OutboundControlKindV4,
    OutboundControlWirePreparedV4,
    OutboundControlWritePermitConsumedV4,
    OutboundWebSocketOpcodeV4,
)

T0 = datetime(2026, 7, 15, 12, tzinfo=timezone.utc)


def digest(label: str) -> str:
    return sha256_digest({"label": label})


def run_async(function: Any) -> Any:
    @wraps(function)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return asyncio.run(function(*args, **kwargs))

    return wrapper


SOCKET_ID = digest("socket")
GENERATION = 7


def masked_text_frame(payload: bytes) -> bytes:
    assert len(payload) < 126
    mask = b"\x01\x23\x45\x67"
    masked = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
    return bytes((0x81, 0x80 | len(payload))) + mask + masked


def wire_prepared(
    label: str, *, split_chunks: bool = False
) -> OutboundControlWirePreparedV4:
    payload = f'{{"op":"ping","req_id":"{label}"}}'.encode()
    frame = masked_text_frame(payload)
    raw_chunks = (frame[:4], frame[4:]) if split_chunks else (frame,)
    chunks = tuple(base64.b64encode(chunk).decode("ascii") for chunk in raw_chunks)
    return OutboundControlWirePreparedV4(
        outbound_control_intent_id=digest(f"intent-{label}"),
        transport_session_id=digest("session"),
        socket_lease_id=SOCKET_ID,
        connection_generation=GENERATION,
        deployment_bundle_id=digest("deployment"),
        writer_fence_token_sha256=digest("writer-fence"),
        writer_fence_generation=3,
        control_kind=OutboundControlKindV4.APPLICATION_JSON_HEARTBEAT,
        logical_websocket_opcode=OutboundWebSocketOpcodeV4.TEXT,
        logical_payload_base64=base64.b64encode(payload).decode("ascii"),
        logical_payload_sha256=hashlib.sha256(payload).hexdigest(),
        wire_chunks_base64=chunks,
        wire_chunks_sha256=tuple(
            hashlib.sha256(chunk).hexdigest() for chunk in raw_chunks
        ),
        wire_batch_sha256=sha256_digest(
            {
                "domain": "RiskYieldMMExactOrderedPreTlsWebSocketChunksV4_5",
                "ordered_chunks_base64": list(chunks),
            }
        ),
        wire_octet_length=len(frame),
        prepared_at=T0,
        monotonic_clock_domain_id=digest("monotonic-domain"),
        prepared_monotonic_ns=1_000,
        send_not_after=T0 + timedelta(seconds=1),
        send_not_after_monotonic_ns=1_001_000,
    )


class FakeClock:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> tuple[datetime, int]:
        self.calls += 1
        return T0 + timedelta(milliseconds=self.calls), 1_000 + self.calls * 1_000


class FakeJournal:
    def __init__(
        self,
        wires: tuple[OutboundControlWirePreparedV4, ...],
        *,
        events: list[str],
        mismatch_permit: bool = False,
        fail_consume: bool = False,
        fail_result: bool = False,
    ) -> None:
        self.wires = {wire.outbound_control_wire_prepared_id: wire for wire in wires}
        self.events = events
        self.mismatch_permit = mismatch_permit
        self.fail_consume = fail_consume
        self.fail_result = fail_result
        self.permits: list[OutboundControlWritePermitConsumedV4] = []
        self.results: list[OutboundControlDispatchResultV4] = []

    def consume_outbound_control_write_permit(
        self,
        outbound_control_wire_prepared_id: str,
        *,
        permit_consumed_at: datetime,
        permit_consumed_monotonic_ns: int,
        idempotency_key: str,
    ) -> OutboundControlWritePermitConsumedV4:
        assert idempotency_key.endswith(outbound_control_wire_prepared_id)
        self.events.append("permit")
        if self.fail_consume:
            raise OSError("durability unavailable")
        wire = self.wires[outbound_control_wire_prepared_id]
        permit = OutboundControlWritePermitConsumedV4(
            outbound_control_intent_id=wire.outbound_control_intent_id,
            outbound_control_wire_prepared_id=(wire.outbound_control_wire_prepared_id),
            transport_session_id=wire.transport_session_id,
            socket_lease_id=wire.socket_lease_id,
            connection_generation=wire.connection_generation,
            deployment_bundle_id=wire.deployment_bundle_id,
            writer_fence_token_sha256=wire.writer_fence_token_sha256,
            writer_fence_generation=wire.writer_fence_generation,
            control_kind=wire.control_kind,
            wire_batch_sha256=wire.wire_batch_sha256,
            wire_octet_length=wire.wire_octet_length,
            one_shot_attempt_ordinal=1,
            wire_prepared_at=wire.prepared_at,
            monotonic_clock_domain_id=wire.monotonic_clock_domain_id,
            wire_prepared_monotonic_ns=wire.prepared_monotonic_ns,
            permit_consumed_at=permit_consumed_at,
            permit_consumed_monotonic_ns=permit_consumed_monotonic_ns,
            send_not_after=wire.send_not_after,
            send_not_after_monotonic_ns=wire.send_not_after_monotonic_ns,
        )
        if self.mismatch_permit:
            permit = replace(permit, wire_batch_sha256=digest("mismatched-wire"))
        self.permits.append(permit)
        return permit

    def append_outbound_control_dispatch_result(
        self,
        dispatch: OutboundControlDispatchResultV4,
        *,
        idempotency_key: str,
    ) -> OutboundControlDispatchResultV4:
        assert idempotency_key.endswith(dispatch.permit_id)
        self.events.append("result")
        if self.fail_result:
            raise OSError("result fsync failed")
        self.results.append(dispatch)
        return dispatch


class FakeWriter:
    def __init__(
        self,
        journal: FakeJournal,
        *,
        events: list[str],
        mode: str = "full",
    ) -> None:
        self.journal = journal
        self.events = events
        self.mode = mode
        self.calls = 0
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def submit_permitted_chunks(
        self,
        *,
        permit: OutboundControlWritePermitConsumedV4,
        ordered_chunks: tuple[bytes, ...],
    ) -> int:
        assert self.journal.permits
        assert self.journal.permits[-1] == permit
        assert len(ordered_chunks) == 1 and ordered_chunks[0]
        self.calls += 1
        self.events.append("write")
        self.started.set()
        if self.mode == "exception":
            raise OSError("TLS write uncertain")
        if self.mode == "short":
            return permit.wire_octet_length - 1
        if self.mode == "block":
            await self.release.wait()
        return permit.wire_octet_length


def mediator(
    journal: FakeJournal,
    writer: FakeWriter,
    clock: FakeClock,
) -> PhysicalTransportControlMediatorV4:
    return PhysicalTransportControlMediatorV4.for_test(
        journal=journal,
        writer=writer,
        clock=clock,
        signer=Ed25519CheckpointSigner.generate(),
        expected_socket_lease_id=SOCKET_ID,
        expected_connection_generation=GENERATION,
        assert_writer_authority=lambda: None,
    )


async def dispatch(
    runtime: PhysicalTransportControlMediatorV4,
    wire: OutboundControlWirePreparedV4,
) -> OutboundControlDispatchResultV4:
    return await runtime.dispatch_prepared(
        wire,
        socket_lease_id=SOCKET_ID,
        connection_generation=GENERATION,
        idempotency_prefix="test-runtime",
    )


@run_async
async def test_durable_permit_precedes_the_single_exact_writer_call() -> None:
    wire = wire_prepared("success")
    events: list[str] = []
    journal = FakeJournal((wire,), events=events)
    writer = FakeWriter(journal, events=events)
    runtime = mediator(journal, writer, FakeClock())

    result = await dispatch(runtime, wire)

    assert events == ["permit", "write", "result"]
    assert writer.calls == 1
    assert result.disposition is OutboundControlDispatchDispositionV4.SENT
    assert result.bytes_submitted_to_tls == wire.wire_octet_length
    assert runtime.state is PhysicalTransportControlRuntimeStateV4.OPEN
    result.verify_signature()


@run_async
async def test_stale_callback_is_rejected_first_without_any_mutation() -> None:
    wire = wire_prepared("stale")
    events: list[str] = []
    clock = FakeClock()
    journal = FakeJournal((wire,), events=events)
    writer = FakeWriter(journal, events=events)
    runtime = mediator(journal, writer, clock)
    await runtime.close()

    with pytest.raises(PhysicalTransportControlStaleCallbackV4):
        await runtime.dispatch_prepared(
            wire,
            socket_lease_id=digest("old-socket"),
            connection_generation=GENERATION,
            idempotency_prefix="stale",
        )

    assert events == []
    assert clock.calls == 0
    assert runtime.state is PhysicalTransportControlRuntimeStateV4.CLOSED


@run_async
async def test_permit_mismatch_latches_without_invoking_writer() -> None:
    wire = wire_prepared("mismatch")
    events: list[str] = []
    journal = FakeJournal((wire,), events=events, mismatch_permit=True)
    writer = FakeWriter(journal, events=events)
    runtime = mediator(journal, writer, FakeClock())

    with pytest.raises(PhysicalTransportControlRuntimeV4FaultLatched):
        await dispatch(runtime, wire)

    assert events == ["permit"]
    assert writer.calls == 0
    assert runtime.state is PhysicalTransportControlRuntimeStateV4.FAULT_LATCHED


@run_async
async def test_permit_persistence_failure_never_reaches_writer() -> None:
    wire = wire_prepared("permit-failure")
    events: list[str] = []
    journal = FakeJournal((wire,), events=events, fail_consume=True)
    writer = FakeWriter(journal, events=events)
    runtime = mediator(journal, writer, FakeClock())

    with pytest.raises(PhysicalTransportControlRuntimeV4FaultLatched):
        await dispatch(runtime, wire)

    assert events == ["permit"]
    assert writer.calls == 0
    assert runtime.state is PhysicalTransportControlRuntimeStateV4.FAULT_LATCHED


@pytest.mark.parametrize("mode", ("exception", "short"))
@run_async
async def test_exception_or_short_write_persists_unknown_and_never_retries(
    mode: str,
) -> None:
    wire = wire_prepared(mode)
    events: list[str] = []
    journal = FakeJournal((wire,), events=events)
    writer = FakeWriter(journal, events=events, mode=mode)
    runtime = mediator(journal, writer, FakeClock())

    result = await dispatch(runtime, wire)

    assert result.disposition is (OutboundControlDispatchDispositionV4.UNKNOWN_DELIVERY)
    assert result.error_class_digest is not None
    assert result.bytes_submitted_to_tls == (
        None if mode == "exception" else wire.wire_octet_length - 1
    )
    assert runtime.state is PhysicalTransportControlRuntimeStateV4.FAULT_LATCHED
    with pytest.raises(PhysicalTransportControlRuntimeV4FaultLatched):
        await dispatch(runtime, wire)
    assert writer.calls == 1


@run_async
async def test_post_permit_pre_writer_failure_leaves_no_fabricated_result() -> None:
    wire = wire_prepared("lost-authority")
    events: list[str] = []
    journal = FakeJournal((wire,), events=events)
    writer = FakeWriter(journal, events=events)
    authority_checks = 0

    def assert_authority() -> None:
        nonlocal authority_checks
        authority_checks += 1
        if authority_checks == 2:
            raise RuntimeError("writer fence was superseded")

    runtime = PhysicalTransportControlMediatorV4.for_test(
        journal=journal,
        writer=writer,
        clock=FakeClock(),
        signer=Ed25519CheckpointSigner.generate(),
        expected_socket_lease_id=SOCKET_ID,
        expected_connection_generation=GENERATION,
        assert_writer_authority=assert_authority,
    )

    with pytest.raises(PhysicalTransportControlRuntimeV4FaultLatched):
        await dispatch(runtime, wire)

    assert events == ["permit"]
    assert len(journal.permits) == 1
    assert journal.results == []
    assert writer.calls == 0
    assert runtime.state is PhysicalTransportControlRuntimeStateV4.FAULT_LATCHED


@run_async
async def test_result_persistence_failure_latches_and_forbids_retry() -> None:
    wire = wire_prepared("result-failure")
    events: list[str] = []
    journal = FakeJournal((wire,), events=events, fail_result=True)
    writer = FakeWriter(journal, events=events)
    runtime = mediator(journal, writer, FakeClock())

    with pytest.raises(PhysicalTransportControlRuntimeV4FaultLatched):
        await dispatch(runtime, wire)
    with pytest.raises(PhysicalTransportControlRuntimeV4FaultLatched):
        await dispatch(runtime, wire)

    assert events == ["permit", "write", "result"]
    assert writer.calls == 1
    assert runtime.state is PhysicalTransportControlRuntimeStateV4.FAULT_LATCHED


@run_async
async def test_concurrent_dispatches_are_fully_serialized() -> None:
    first = wire_prepared("first")
    second = wire_prepared("second")
    events: list[str] = []
    journal = FakeJournal((first, second), events=events)
    writer = FakeWriter(journal, events=events, mode="block")
    runtime = mediator(journal, writer, FakeClock())

    first_task = asyncio.create_task(dispatch(runtime, first))
    await writer.started.wait()
    second_task = asyncio.create_task(dispatch(runtime, second))
    await asyncio.sleep(0)
    assert events == ["permit", "write"]
    writer.release.set()

    results = await asyncio.gather(first_task, second_task)

    assert [item.disposition for item in results] == [
        OutboundControlDispatchDispositionV4.SENT,
        OutboundControlDispatchDispositionV4.SENT,
    ]
    assert events == ["permit", "write", "result"] * 2
    assert writer.calls == 2


@run_async
async def test_multioutput_protocol_drain_is_rejected_before_permit() -> None:
    wire = wire_prepared("multi", split_chunks=True)
    events: list[str] = []
    clock = FakeClock()
    journal = FakeJournal((wire,), events=events)
    writer = FakeWriter(journal, events=events)
    runtime = mediator(journal, writer, clock)

    with pytest.raises(PhysicalTransportControlProtocolDrainV4Error):
        await dispatch(runtime, wire)
    with pytest.raises(PhysicalTransportControlProtocolDrainV4Error):
        validate_protocol_drain((b"one", b"two"))

    assert events == []
    assert clock.calls == 0
    assert runtime.state is PhysicalTransportControlRuntimeStateV4.FAULT_LATCHED


@run_async
async def test_cancellation_after_writer_invocation_persists_unknown_then_reraises() -> (
    None
):
    wire = wire_prepared("cancel")
    events: list[str] = []
    journal = FakeJournal((wire,), events=events)
    writer = FakeWriter(journal, events=events, mode="block")
    runtime = mediator(journal, writer, FakeClock())

    task = asyncio.create_task(dispatch(runtime, wire))
    await writer.started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert events == ["permit", "write", "result"]
    assert len(journal.results) == 1
    assert journal.results[0].disposition is (
        OutboundControlDispatchDispositionV4.UNKNOWN_DELIVERY
    )
    assert runtime.state is PhysicalTransportControlRuntimeStateV4.FAULT_LATCHED

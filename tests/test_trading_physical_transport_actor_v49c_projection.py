from __future__ import annotations

import asyncio
import base64
import hashlib
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from riskyieldmm.trading.canonical import sha256_digest
from riskyieldmm.trading.physical_projection_v4 import (
    PhysicalProjectionStoreV4,
    PhysicalProjectionV4ConflictError,
)
from riskyieldmm.trading.physical_transport_actor_v49c import (
    CommittedRawChunkV49C,
    DelineatedServerFrameV49C,
    ParserFeedUnitKindV49C,
    ParserTransitionPayloadV49C,
    RetainedIngressTailV49C,
    TransportActorEventKindV49C,
    TransportActorEventV49C,
    WebSocketParserCursorV49C,
    WebSocketParserStateV49C,
    delineate_next_server_frame_v49c,
)
from riskyieldmm.trading.physical_transport_control_v4 import RawIngressCommitV4
from tests.test_trading_physical_transport_runtime_v49b import (
    T0,
    _build_harness,
    _establish,
)


def _raw_record(committed, frame: bytes = b"\x81\x01x") -> RawIngressCommitV4:
    session = committed.session
    binding = committed.binding
    chunks = (frame[:1], frame[1:])
    encoded = tuple(base64.b64encode(chunk).decode("ascii") for chunk in chunks)
    return RawIngressCommitV4(
        transport_subscription_policy_id=(session.transport_subscription_policy_id),
        transport_session_id=session.transport_session_id,
        physical_scope_manifest_id=session.physical_scope_manifest_id,
        adapter_policy_id=session.adapter_policy_id,
        capture_partition_id=session.capture_partition_id,
        socket_lease_id=binding.socket_lease_id,
        connection_generation=session.connection_generation,
        deployment_bundle_id=session.deployment_bundle_id,
        writer_fence_token_sha256=binding.writer_fence_token_sha256,
        writer_fence_generation=binding.writer_fence_generation,
        ingress_sequence=1,
        raw_ingress_chunks_base64=encoded,
        raw_ingress_chunks_sha256=tuple(
            hashlib.sha256(chunk).hexdigest() for chunk in chunks
        ),
        raw_ingress_batch_sha256=sha256_digest(
            {
                "domain": "RiskYieldMMExactOrderedDecryptedIngressChunksV4_5",
                "ordered_chunks_base64": list(encoded),
            }
        ),
        received_at=T0 + timedelta(milliseconds=900),
        monotonic_clock_domain_id=session.monotonic_clock_domain_id,
        received_monotonic_ns=(session.handshake_completed_monotonic_ns + 1_000_000),
    )


def _parser_event(committed_raw) -> TransportActorEventV49C:
    raw = committed_raw.raw
    raw_event = committed_raw.event
    raw_payload = raw_event.payload
    frame = raw.raw_bytes
    delineated = delineate_next_server_frame_v49c(
        prior_tail=RetainedIngressTailV49C(),
        committed_raw_chunks=(
            CommittedRawChunkV49C(
                raw_ingress_commit_id=raw.raw_ingress_commit_id,
                projection_receipt_sequence=(committed_raw.receipt.global_sequence),
                projection_receipt_hash=committed_raw.receipt.receipt_hash,
                raw_local_start_octet=0,
                stream_start_octet=raw_payload.stream_start_octet,
                data=frame,
            ),
        ),
    )
    assert type(delineated.unit) is DelineatedServerFrameV49C
    processed_at = committed_raw.receipt.committed_at
    parser = ParserTransitionPayloadV49C(
        cursor_before=WebSocketParserCursorV49C(
            cursor_sequence=0,
            next_stream_octet=0,
            websocket_state=WebSocketParserStateV49C.OPEN,
        ),
        cursor_after=WebSocketParserCursorV49C(
            cursor_sequence=1,
            next_stream_octet=len(frame),
            websocket_state=WebSocketParserStateV49C.OPEN,
        ),
        feed_unit_kind=ParserFeedUnitKindV49C.COMPLETE_FRAME,
        source_slices=delineated.unit.source_slices,
        frame=delineated.unit.metadata,
        parser_error=None,
        ordered_protocol_output_chunks_base64=(),
        ordered_protocol_output_chunks_sha256=(),
        protocol_output_batch_sha256=None,
        send_eof_after_output=False,
        processed_at=processed_at,
        processed_monotonic_ns=raw.received_monotonic_ns + 1,
    )
    return TransportActorEventV49C.create(
        transport_subscription_policy_id=(raw_event.transport_subscription_policy_id),
        transport_session_id=raw_event.transport_session_id,
        physical_scope_manifest_id=raw_event.physical_scope_manifest_id,
        adapter_policy_id=raw_event.adapter_policy_id,
        capture_partition_id=raw_event.capture_partition_id,
        socket_lease_id=raw_event.socket_lease_id,
        connection_generation=raw_event.connection_generation,
        deployment_bundle_id=raw_event.deployment_bundle_id,
        writer_fence_token_sha256=raw_event.writer_fence_token_sha256,
        writer_fence_generation=raw_event.writer_fence_generation,
        monotonic_clock_domain_id=raw_event.monotonic_clock_domain_id,
        driver_policy_id=raw_event.driver_policy_id,
        recorded_at=processed_at,
        recorded_monotonic_ns=raw.received_monotonic_ns + 1,
        actor_sequence=2,
        previous_event_id=raw_event.transport_actor_event_id,
        event_kind=TransportActorEventKindV49C.PARSER_TRANSITION,
        payload=parser,
    )


def _parser_batch_events(
    committed_raw,
) -> tuple[TransportActorEventV49C, TransportActorEventV49C]:
    raw = committed_raw.raw
    raw_event = committed_raw.event
    raw_payload = raw_event.payload
    chunk = CommittedRawChunkV49C(
        raw_ingress_commit_id=raw.raw_ingress_commit_id,
        projection_receipt_sequence=committed_raw.receipt.global_sequence,
        projection_receipt_hash=committed_raw.receipt.receipt_hash,
        raw_local_start_octet=0,
        stream_start_octet=raw_payload.stream_start_octet,
        data=raw.raw_bytes,
    )
    first = delineate_next_server_frame_v49c(
        prior_tail=RetainedIngressTailV49C(),
        committed_raw_chunks=(chunk,),
    )
    second = delineate_next_server_frame_v49c(
        prior_tail=first.retained_tail,
        committed_raw_chunks=(),
    )
    assert type(first.unit) is DelineatedServerFrameV49C
    assert type(second.unit) is DelineatedServerFrameV49C
    assert not second.retained_tail.chunks

    result: list[TransportActorEventV49C] = []
    cursor = WebSocketParserCursorV49C(
        cursor_sequence=0,
        next_stream_octet=raw_payload.stream_start_octet,
        websocket_state=WebSocketParserStateV49C.OPEN,
    )
    previous_event_id = raw_event.transport_actor_event_id
    for ordinal, delineated in enumerate((first.unit, second.unit), start=1):
        cursor_after = WebSocketParserCursorV49C(
            cursor_sequence=ordinal,
            next_stream_octet=delineated.metadata.stream_end_octet,
            websocket_state=WebSocketParserStateV49C.OPEN,
        )
        monotonic_ns = raw.received_monotonic_ns + ordinal
        payload = ParserTransitionPayloadV49C(
            cursor_before=cursor,
            cursor_after=cursor_after,
            feed_unit_kind=ParserFeedUnitKindV49C.COMPLETE_FRAME,
            source_slices=delineated.source_slices,
            frame=delineated.metadata,
            parser_error=None,
            ordered_protocol_output_chunks_base64=(),
            ordered_protocol_output_chunks_sha256=(),
            protocol_output_batch_sha256=None,
            send_eof_after_output=False,
            processed_at=committed_raw.receipt.committed_at,
            processed_monotonic_ns=monotonic_ns,
        )
        event = TransportActorEventV49C.create(
            transport_subscription_policy_id=(
                raw_event.transport_subscription_policy_id
            ),
            transport_session_id=raw_event.transport_session_id,
            physical_scope_manifest_id=raw_event.physical_scope_manifest_id,
            adapter_policy_id=raw_event.adapter_policy_id,
            capture_partition_id=raw_event.capture_partition_id,
            socket_lease_id=raw_event.socket_lease_id,
            connection_generation=raw_event.connection_generation,
            deployment_bundle_id=raw_event.deployment_bundle_id,
            writer_fence_token_sha256=raw_event.writer_fence_token_sha256,
            writer_fence_generation=raw_event.writer_fence_generation,
            monotonic_clock_domain_id=raw_event.monotonic_clock_domain_id,
            driver_policy_id=raw_event.driver_policy_id,
            recorded_at=committed_raw.receipt.committed_at,
            recorded_monotonic_ns=monotonic_ns,
            actor_sequence=ordinal + 1,
            previous_event_id=previous_event_id,
            event_kind=TransportActorEventKindV49C.PARSER_TRANSITION,
            payload=payload,
        )
        result.append(event)
        cursor = cursor_after
        previous_event_id = event.transport_actor_event_id
    return result[0], result[1]


def test_projection_atomically_binds_raw_receipt_and_parser_chain() -> None:
    async def scenario() -> None:
        with TemporaryDirectory(prefix="ry-v49c-atomic-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                committed = await _establish(harness)
                raw = _raw_record(committed)
                result = harness.store.append_actor_raw_ingress_v49c_for_test(
                    raw,
                    driver_policy_id=harness.driver.driver_policy_id,
                    idempotency_key="actor-raw",
                )
                assert result.receipt.identity_id == raw.raw_ingress_commit_id
                assert (
                    result.receipt.global_sequence + 1
                    == (
                        harness.store._source_metadata(  # noqa: SLF001
                            result.event.transport_actor_event_id
                        )[0]
                    )
                )
                assert (
                    harness.store.append_actor_raw_ingress_v49c_for_test(
                        raw,
                        driver_policy_id=harness.driver.driver_policy_id,
                        idempotency_key="actor-raw",
                    )
                    == result
                )

                parser_event = _parser_event(result)
                assert (
                    harness.store.append_transport_actor_event_v49c_for_test(
                        parser_event,
                        idempotency_key="actor-parser",
                    )
                    == parser_event
                )
                report = harness.store.verify()
                assert report.raw_ingress_commit_count == 1
                assert report.transport_actor_event_count == 2
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_actor_batch_replays_exact_order_and_one_operation_clock() -> None:
    async def scenario() -> None:
        with TemporaryDirectory(prefix="ry-v49c-batch-replay-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                committed = await _establish(harness)
                raw = harness.store.append_actor_raw_ingress_v49c_for_test(
                    _raw_record(committed, b"\x81\x01x\x81\x01y"),
                    driver_policy_id=harness.driver.driver_policy_id,
                    idempotency_key="actor-raw-two-frames",
                )
                events = _parser_batch_events(raw)
                appended = (
                    harness.store.append_transport_actor_event_batch_v49c_for_test(
                        events,
                        idempotency_key="actor-parser-batch",
                    )
                )
                assert appended is events

                replayed = (
                    harness.store.append_transport_actor_event_batch_v49c_for_test(
                        events,
                        idempotency_key="actor-parser-batch",
                    )
                )
                assert replayed == events
                assert replayed is not events
                assert all(
                    actual is not expected
                    for actual, expected in zip(replayed, events, strict=True)
                )

                sequences = tuple(
                    harness.store._source_metadata(  # noqa: SLF001
                        event.transport_actor_event_id
                    )[0]
                    for event in events
                )
                assert sequences[1] == sequences[0] + 1
                receipt_clocks = tuple(
                    str(row[0])
                    for sequence in sequences
                    for row in harness.store._connection.execute(  # noqa: SLF001
                        "SELECT committed_at FROM receipts WHERE global_sequence = ?",
                        (sequence,),
                    )
                )
                assert len(receipt_clocks) == 2
                assert receipt_clocks[0] == receipt_clocks[1]
                batch_row = harness.store._connection.execute(  # noqa: SLF001
                    """
                    SELECT operation, first_receipt_sequence, last_receipt_sequence
                    FROM operation_batches WHERE idempotency_key = ?
                    """,
                    ("actor-parser-batch",),
                ).fetchone()
                assert batch_row == (
                    "APPEND_TRANSPORT_ACTOR_EVENT_BATCH_V49C",
                    sequences[0],
                    sequences[1],
                )
                report = harness.store.verify()
                assert report.transport_actor_event_count == 3
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_actor_batch_second_insert_fault_rolls_back_entire_batch() -> None:
    armed = False
    actor_inserts = 0

    def fail(stage: str) -> None:
        nonlocal actor_inserts
        if armed and stage == "after_transport_actor_event_v49c_insert":
            actor_inserts += 1
            if actor_inserts == 2:
                raise RuntimeError("second-actor-event-storage-failure")

    async def scenario() -> None:
        nonlocal armed
        with TemporaryDirectory(prefix="ry-v49c-batch-rollback-") as directory:
            harness = await _build_harness(Path(directory), fault_injector=fail)
            try:
                committed = await _establish(harness)
                raw = harness.store.append_actor_raw_ingress_v49c_for_test(
                    _raw_record(committed, b"\x81\x01x\x81\x01y"),
                    driver_policy_id=harness.driver.driver_policy_id,
                    idempotency_key="actor-raw-two-frames",
                )
                events = _parser_batch_events(raw)
                armed = True
                with pytest.raises(
                    RuntimeError, match="second-actor-event-storage-failure"
                ):
                    harness.store.append_transport_actor_event_batch_v49c_for_test(
                        events,
                        idempotency_key="actor-parser-batch-fault",
                    )

                chain = harness.store._load_transport_actor_chain_v49c(  # noqa: SLF001
                    committed.session.transport_session_id
                )
                assert chain == (raw.event,)
                assert (
                    harness.store._connection.execute(  # noqa: SLF001
                        "SELECT 1 FROM operation_batches WHERE idempotency_key = ?",
                        ("actor-parser-batch-fault",),
                    ).fetchone()
                    is None
                )
                report = harness.store.verify()
                assert report.raw_ingress_commit_count == 1
                assert report.transport_actor_event_count == 1
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_raw_actor_fault_rolls_back_both_canonical_records() -> None:
    armed = False

    def fail(stage: str) -> None:
        if armed and stage == "after_transport_actor_event_v49c_insert":
            raise RuntimeError("actor-event-storage-failure")

    async def scenario() -> None:
        nonlocal armed
        with TemporaryDirectory(prefix="ry-v49c-rollback-") as directory:
            harness = await _build_harness(
                Path(directory),
                fault_injector=fail,
            )
            try:
                committed = await _establish(harness)
                raw = _raw_record(committed)
                armed = True
                with pytest.raises(RuntimeError, match="actor-event-storage-failure"):
                    harness.store.append_actor_raw_ingress_v49c_for_test(
                        raw,
                        driver_policy_id=harness.driver.driver_policy_id,
                        idempotency_key="actor-raw-fault",
                    )
                assert harness.store.verify().transport_actor_event_count == 0
                assert harness.store.verify().raw_ingress_commit_count == 0
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_projection_rejects_raw_event_bypass_and_chain_fork() -> None:
    async def scenario() -> None:
        with TemporaryDirectory(prefix="ry-v49c-bypass-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                committed = await _establish(harness)
                result = harness.store.append_actor_raw_ingress_v49c_for_test(
                    _raw_record(committed),
                    driver_policy_id=harness.driver.driver_policy_id,
                    idempotency_key="actor-raw",
                )
                with pytest.raises(PhysicalProjectionV4ConflictError, match="atomic"):
                    harness.store.append_transport_actor_event_v49c_for_test(
                        result.event,
                        idempotency_key="raw-bypass",
                    )
                parser = _parser_event(result)
                fork = TransportActorEventV49C.create(
                    **{
                        name: getattr(parser, name)
                        for name in parser.__dataclass_fields__
                        if name not in {"actor_sequence", "previous_event_id"}
                    },
                    actor_sequence=3,
                    previous_event_id=parser.previous_event_id,
                )
                with pytest.raises(
                    PhysicalProjectionV4ConflictError, match="exact durable"
                ):
                    harness.store.append_transport_actor_event_v49c_for_test(
                        fork,
                        idempotency_key="fork",
                    )
                assert harness.store.verify().transport_actor_event_count == 1
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_fresh_projection_reports_zero_actor_events(tmp_path) -> None:
    with PhysicalProjectionStoreV4(tmp_path / "empty.sqlite3") as store:
        assert store.verify().transport_actor_event_count == 0

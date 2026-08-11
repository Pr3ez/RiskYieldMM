from __future__ import annotations

import asyncio
import base64
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from websockets.frames import Frame, Opcode

from riskyieldmm.trading.canonical import sha256_digest
from riskyieldmm.trading.physical_market_data import MessageDispositionKind
from riskyieldmm.trading.physical_projection_v4 import (
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
    WebSocketOpcodeV49C,
    WebSocketParserCursorV49C,
    WebSocketParserStateV49C,
    delineate_next_server_frame_v49c,
)
from riskyieldmm.trading.physical_transport_control_v4 import RawIngressCommitV4
from riskyieldmm.trading.physical_transport_terminal_v49c import (
    TerminalTransitionKindV49C,
)
from riskyieldmm.trading.physical_transport_v4 import (
    TransportSessionTerminationReasonV4,
)
from tests.test_trading_physical_transport_runtime_v49b import (
    _build_harness,
    _establish,
)
from tests.test_trading_physical_transport_runtime_v49c_egress import (
    _bind_projection_clock_to_owner,
)


def _ack_bytes(*, request_id: str, connection_id: str = "projection-v49e") -> bytes:
    return json.dumps(
        {
            "success": True,
            "ret_msg": "",
            "conn_id": connection_id,
            "req_id": request_id,
            "op": "subscribe",
        },
        separators=(",", ":"),
    ).encode("utf-8")


def _pong_bytes(*, connection_id: str) -> bytes:
    return json.dumps(
        {
            "success": True,
            "ret_msg": "pong",
            "conn_id": connection_id,
            "op": "ping",
        },
        separators=(",", ":"),
    ).encode("utf-8")


def _invalid_ack_case(
    case: str, *, request_id: str
) -> tuple[bytes, WebSocketOpcodeV49C]:
    base: dict[str, object] = {
        "success": True,
        "ret_msg": "",
        "conn_id": "projection-v49e",
        "req_id": request_id,
        "op": "subscribe",
    }
    opcode = WebSocketOpcodeV49C.TEXT
    if case == "malformed_fields":
        base["conn_id"] = []
        base["ret_msg"] = 7
    elif case == "provider_rejected":
        base["success"] = False
        base["ret_msg"] = "denied"
    elif case == "wrong_request_id":
        base["req_id"] = "wrong-request-id"
    elif case == "missing_request_id":
        del base["req_id"]
    elif case == "empty_request_id":
        base["req_id"] = ""
    elif case == "extra_schema":
        base["unexpected"] = True
    elif case == "binary_exact_json":
        opcode = WebSocketOpcodeV49C.BINARY
    elif case == "binary_near_miss":
        opcode = WebSocketOpcodeV49C.BINARY
        base["req_id"] = "wrong-request-id"
        base["unexpected"] = True
    else:  # pragma: no cover - parametrization exhaustiveness guard
        raise AssertionError(f"unsupported invalid ACK case: {case}")
    return json.dumps(base, separators=(",", ":")).encode("utf-8"), opcode


async def _prepare_dispatched_subscription(harness: object) -> object:
    await _establish(harness)  # type: ignore[arg-type]
    _bind_projection_clock_to_owner(harness)
    await harness.runtime.activate_causal_transport_actor_v49c()  # type: ignore[attr-defined]
    await harness.runtime.dispatch_subscription_v49c(  # type: ignore[attr-defined]
        idempotency_key="v49e-projection-subscription"
    )
    intent = harness.runtime._intent  # type: ignore[attr-defined]  # noqa: SLF001
    assert intent is not None
    return intent


def _append_raw(
    harness: object,
    data: bytes,
    *,
    ingress_sequence: int,
    received_at: datetime | None = None,
    received_monotonic_ns: int | None = None,
) -> object:
    store = harness.store  # type: ignore[attr-defined]
    runtime = harness.runtime  # type: ignore[attr-defined]
    session = runtime._session  # noqa: SLF001
    binding = runtime._socket_owner_binding  # noqa: SLF001
    assert session is not None and binding is not None
    chain = store._load_transport_actor_chain_v49c(  # noqa: SLF001
        session.transport_session_id
    )
    prior_monotonic_ns = (
        session.handshake_completed_monotonic_ns
        if not chain
        else chain[-1].recorded_monotonic_ns
    )
    encoded = (base64.b64encode(data).decode("ascii"),)
    raw = RawIngressCommitV4(
        transport_subscription_policy_id=session.transport_subscription_policy_id,
        transport_session_id=session.transport_session_id,
        physical_scope_manifest_id=session.physical_scope_manifest_id,
        adapter_policy_id=session.adapter_policy_id,
        capture_partition_id=session.capture_partition_id,
        socket_lease_id=binding.socket_lease_id,
        connection_generation=session.connection_generation,
        deployment_bundle_id=session.deployment_bundle_id,
        writer_fence_token_sha256=binding.writer_fence_token_sha256,
        writer_fence_generation=binding.writer_fence_generation,
        ingress_sequence=ingress_sequence,
        raw_ingress_chunks_base64=encoded,
        raw_ingress_chunks_sha256=(hashlib.sha256(data).hexdigest(),),
        raw_ingress_batch_sha256=sha256_digest(
            {
                "domain": "RiskYieldMMExactOrderedDecryptedIngressChunksV4_5",
                "ordered_chunks_base64": list(encoded),
            }
        ),
        received_at=(
            store._now()  # noqa: SLF001 - exact test observation
            if received_at is None
            else received_at
        ),
        monotonic_clock_domain_id=session.monotonic_clock_domain_id,
        received_monotonic_ns=(
            prior_monotonic_ns + 1_000
            if received_monotonic_ns is None
            else received_monotonic_ns
        ),
    )
    return store.append_actor_raw_ingress_v49c_for_test(
        raw,
        driver_policy_id=harness.driver.driver_policy_id,  # type: ignore[attr-defined]
        idempotency_key=f"v49e-projection-raw-{ingress_sequence}",
    )


def _append_parser_frame(
    harness: object,
    *,
    frame_bytes: bytes,
    ingress_sequence: int,
    cursor_before: WebSocketParserCursorV49C,
    fragmented_bytes_before: bytes,
    received_at: datetime | None = None,
    received_monotonic_ns: int | None = None,
) -> tuple[
    TransportActorEventV49C,
    WebSocketParserCursorV49C,
    bytes,
    object,
]:
    committed_raw = _append_raw(
        harness,
        frame_bytes,
        ingress_sequence=ingress_sequence,
        received_at=received_at,
        received_monotonic_ns=received_monotonic_ns,
    )
    raw = committed_raw.raw
    raw_event = committed_raw.event
    raw_payload = raw_event.payload
    delineated = delineate_next_server_frame_v49c(
        prior_tail=RetainedIngressTailV49C(),
        committed_raw_chunks=(
            CommittedRawChunkV49C(
                raw_ingress_commit_id=raw.raw_ingress_commit_id,
                projection_receipt_sequence=committed_raw.receipt.global_sequence,
                projection_receipt_hash=committed_raw.receipt.receipt_hash,
                raw_local_start_octet=0,
                stream_start_octet=raw_payload.stream_start_octet,
                data=raw.raw_bytes,
            ),
        ),
    )
    assert type(delineated.unit) is DelineatedServerFrameV49C
    assert delineated.retained_tail.total_octets == 0
    unit = delineated.unit
    frame = unit.metadata

    fragmented_bytes_after = fragmented_bytes_before
    fragmented_opcode = cursor_before.fragmented_message_opcode
    if frame.opcode in {WebSocketOpcodeV49C.TEXT, WebSocketOpcodeV49C.BINARY}:
        assert fragmented_opcode is None
        if frame.fin:
            fragmented_bytes_after = b""
        else:
            fragmented_opcode = frame.opcode
            fragmented_bytes_after = unit.payload
    elif frame.opcode is WebSocketOpcodeV49C.CONTINUATION:
        assert fragmented_opcode is not None
        fragmented_bytes_after += unit.payload
        if frame.fin:
            fragmented_opcode = None
            fragmented_bytes_after = b""
    else:  # pragma: no cover - helper is intentionally data-frame-only
        raise AssertionError("projection V4.9E helper requires a data frame")

    cursor_after = WebSocketParserCursorV49C(
        cursor_sequence=cursor_before.cursor_sequence + 1,
        next_stream_octet=frame.stream_end_octet,
        websocket_state=WebSocketParserStateV49C.OPEN,
        fragmented_message_opcode=fragmented_opcode,
        fragmented_message_octets=len(fragmented_bytes_after),
        fragmented_message_sha256=(
            None
            if fragmented_opcode is None
            else hashlib.sha256(fragmented_bytes_after).hexdigest()
        ),
    )
    parser_payload = ParserTransitionPayloadV49C(
        cursor_before=cursor_before,
        cursor_after=cursor_after,
        feed_unit_kind=ParserFeedUnitKindV49C.COMPLETE_FRAME,
        source_slices=unit.source_slices,
        frame=frame,
        parser_error=None,
        ordered_protocol_output_chunks_base64=(),
        ordered_protocol_output_chunks_sha256=(),
        protocol_output_batch_sha256=None,
        send_eof_after_output=False,
        processed_at=committed_raw.receipt.committed_at,
        processed_monotonic_ns=raw.received_monotonic_ns + 1,
    )
    parser_event = TransportActorEventV49C.create(
        **{
            name: getattr(raw_event, name)
            for name in (
                "transport_subscription_policy_id",
                "transport_session_id",
                "physical_scope_manifest_id",
                "adapter_policy_id",
                "capture_partition_id",
                "socket_lease_id",
                "connection_generation",
                "deployment_bundle_id",
                "writer_fence_token_sha256",
                "writer_fence_generation",
                "monotonic_clock_domain_id",
                "driver_policy_id",
            )
        },
        recorded_at=committed_raw.receipt.committed_at,
        recorded_monotonic_ns=raw.received_monotonic_ns + 1,
        actor_sequence=raw_event.actor_sequence + 1,
        previous_event_id=raw_event.transport_actor_event_id,
        event_kind=TransportActorEventKindV49C.PARSER_TRANSITION,
        payload=parser_payload,
    )
    appended = harness.store.append_transport_actor_event_v49c_for_test(  # type: ignore[attr-defined]
        parser_event,
        idempotency_key=f"v49e-projection-parser-{ingress_sequence}",
    )
    assert appended == parser_event
    return parser_event, cursor_after, fragmented_bytes_after, committed_raw


def _append_complete_message(
    harness: object,
    *,
    raw_payload: bytes,
    ingress_sequence: int,
    websocket_opcode: WebSocketOpcodeV49C = WebSocketOpcodeV49C.TEXT,
    cursor_before: WebSocketParserCursorV49C | None = None,
    received_at: datetime | None = None,
    received_monotonic_ns: int | None = None,
) -> tuple[TransportActorEventV49C, WebSocketParserCursorV49C, object]:
    frame_opcode = (
        Opcode.TEXT if websocket_opcode is WebSocketOpcodeV49C.TEXT else Opcode.BINARY
    )
    frame = Frame(frame_opcode, raw_payload).serialize(mask=False)
    parser, cursor, retained, committed_raw = _append_parser_frame(
        harness,
        frame_bytes=frame,
        ingress_sequence=ingress_sequence,
        cursor_before=(
            WebSocketParserCursorV49C(
                cursor_sequence=0,
                next_stream_octet=0,
                websocket_state=WebSocketParserStateV49C.OPEN,
            )
            if cursor_before is None
            else cursor_before
        ),
        fragmented_bytes_before=b"",
        received_at=received_at,
        received_monotonic_ns=received_monotonic_ns,
    )
    assert retained == b""
    return parser, cursor, committed_raw


def _commit(
    harness: object,
    *,
    parser_event_ids: tuple[str, ...],
    raw_payload: bytes,
    final_raw: object,
    classified_monotonic_ns: int,
    idempotency_key: str,
    websocket_opcode: WebSocketOpcodeV49C = WebSocketOpcodeV49C.TEXT,
) -> object:
    session = harness.runtime._session  # type: ignore[attr-defined]  # noqa: SLF001
    signer = harness.runtime._signer  # type: ignore[attr-defined]  # noqa: SLF001
    assert session is not None
    return harness.store.commit_actor_provider_message_v49e_for_test(  # type: ignore[attr-defined]
        transport_session_id=session.transport_session_id,
        source_parser_event_ids=parser_event_ids,
        websocket_opcode=websocket_opcode,
        raw_payload=raw_payload,
        collector_received_at=final_raw.raw.received_at,
        collector_received_monotonic_ns=final_raw.raw.received_monotonic_ns,
        classified_monotonic_ns=classified_monotonic_ns,
        driver_policy_id=harness.driver.driver_policy_id,  # type: ignore[attr-defined]
        signer=signer,
        idempotency_key=idempotency_key,
    )


def _projection_counts(store: object) -> tuple[int, ...]:
    tables = (
        "canonical_records",
        "receipts",
        "operation_batches",
        "capture_segments",
        "physical_messages",
        "message_dispositions",
        "disposition_provenance",
        "subscription_ack_bindings",
        "transport_session_terminations",
        "transport_actor_events_v49c",
    )
    return tuple(
        int(
            store._connection.execute(  # type: ignore[attr-defined]  # noqa: SLF001
                f"SELECT count(*) FROM {table}"
            ).fetchone()[0]
        )
        for table in tables
    )


def test_pre_intent_text_is_classified_without_inventing_ack_authority() -> None:
    async def scenario() -> None:
        with TemporaryDirectory(prefix="ry-v49e-projection-pre-intent-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                await _establish(harness)
                _bind_projection_clock_to_owner(harness)
                await harness.runtime.activate_causal_transport_actor_v49c()
                raw_payload = b'{"topic":"pre-intent","data":[]}'
                frame = Frame(Opcode.TEXT, raw_payload).serialize(mask=False)
                parser, cursor, _, committed_raw = _append_parser_frame(
                    harness,
                    frame_bytes=frame,
                    ingress_sequence=1,
                    cursor_before=WebSocketParserCursorV49C(
                        cursor_sequence=0,
                        next_stream_octet=0,
                        websocket_state=WebSocketParserStateV49C.OPEN,
                    ),
                    fragmented_bytes_before=b"",
                )
                assert (
                    harness.store._connection.execute(  # noqa: SLF001
                        "SELECT count(*) FROM outbound_subscription_intents"
                    ).fetchone()[0]
                    == 0
                )

                result = _commit(
                    harness,
                    parser_event_ids=(parser.transport_actor_event_id,),
                    raw_payload=raw_payload,
                    final_raw=committed_raw,
                    classified_monotonic_ns=parser.recorded_monotonic_ns + 1,
                    idempotency_key="v49e-pre-intent-text",
                )

                assert result.segment.envelopes[0].raw_payload == raw_payload
                assert result.application_event.payload.source_parser_event_ids == (
                    parser.transport_actor_event_id,
                )
                assert (
                    result.classification.provider_disposition.disposition_kind
                    is not (MessageDispositionKind.CONTROL_SUBSCRIPTION_ACK)
                )
                assert result.ack_binding is None
                assert result.ack_event is None
                assert result.provider_failure_event is None
                assert result.termination is None

                shaped_payload = _ack_bytes(request_id="pre-intent-request")
                shaped_parser, _, shaped_raw = _append_complete_message(
                    harness,
                    raw_payload=shaped_payload,
                    ingress_sequence=2,
                    cursor_before=cursor,
                )
                shaped = _commit(
                    harness,
                    parser_event_ids=(shaped_parser.transport_actor_event_id,),
                    raw_payload=shaped_payload,
                    final_raw=shaped_raw,
                    classified_monotonic_ns=(shaped_parser.recorded_monotonic_ns + 1),
                    idempotency_key="v49e-pre-intent-shaped",
                )
                assert shaped.classification.provider_disposition.disposition_kind is (
                    MessageDispositionKind.CONTROL_SUBSCRIPTION_ACK
                )
                assert shaped.ack_binding is None
                assert shaped.ack_event is None
                assert shaped.provider_failure_event is None
                assert shaped.termination is None
                harness.store.verify()
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_unfragmented_ack_uses_exact_parser_bytes_and_replays_idempotently() -> None:
    async def scenario() -> None:
        with TemporaryDirectory(prefix="ry-v49e-projection-unfragmented-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                intent = await _prepare_dispatched_subscription(harness)
                raw_payload = _ack_bytes(request_id=intent.request_id)
                frame = Frame(Opcode.TEXT, raw_payload).serialize(mask=False)
                parser, cursor, _, committed_raw = _append_parser_frame(
                    harness,
                    frame_bytes=frame,
                    ingress_sequence=1,
                    cursor_before=WebSocketParserCursorV49C(
                        cursor_sequence=0,
                        next_stream_octet=0,
                        websocket_state=WebSocketParserStateV49C.OPEN,
                    ),
                    fragmented_bytes_before=b"",
                )

                before_rejected_claim = _projection_counts(harness.store)
                with pytest.raises(
                    PhysicalProjectionV4ConflictError,
                    match="canonical parser/RAW evidence",
                ):
                    _commit(
                        harness,
                        parser_event_ids=(parser.transport_actor_event_id,),
                        raw_payload=raw_payload[:-1] + b" ",
                        final_raw=committed_raw,
                        classified_monotonic_ns=parser.recorded_monotonic_ns + 1,
                        idempotency_key="v49e-forged-unfragmented-payload",
                    )
                assert _projection_counts(harness.store) == before_rejected_claim

                result = _commit(
                    harness,
                    parser_event_ids=(parser.transport_actor_event_id,),
                    raw_payload=raw_payload,
                    final_raw=committed_raw,
                    classified_monotonic_ns=parser.recorded_monotonic_ns + 1,
                    idempotency_key="v49e-valid-unfragmented-ack",
                )
                assert (
                    result.physical_message.raw_payload_sha256
                    == hashlib.sha256(raw_payload).hexdigest()
                )
                assert result.segment.envelopes[0].raw_payload == raw_payload
                assert result.classification.provider_disposition.disposition_kind is (
                    MessageDispositionKind.CONTROL_SUBSCRIPTION_ACK
                )
                assert result.ack_binding is not None
                assert result.ack_event is not None
                assert result.provider_failure_event is None
                assert result.termination is None
                assert result.ack_binding.outbound_subscription_intent_id == (
                    intent.outbound_subscription_intent_id
                )
                assert result.ack_binding.echoed_request_id == intent.request_id
                assert result.application_event.payload.source_parser_event_ids == (
                    parser.transport_actor_event_id,
                )

                committed_counts = _projection_counts(harness.store)
                replay = _commit(
                    harness,
                    parser_event_ids=(parser.transport_actor_event_id,),
                    raw_payload=raw_payload,
                    final_raw=committed_raw,
                    classified_monotonic_ns=parser.recorded_monotonic_ns + 1,
                    idempotency_key="v49e-valid-unfragmented-ack",
                )
                assert replay == result
                assert replay is not result
                assert _projection_counts(harness.store) == committed_counts

                duplicate_parser, _, duplicate_raw = _append_complete_message(
                    harness,
                    raw_payload=raw_payload,
                    ingress_sequence=2,
                    cursor_before=cursor,
                )
                duplicate = _commit(
                    harness,
                    parser_event_ids=(duplicate_parser.transport_actor_event_id,),
                    raw_payload=raw_payload,
                    final_raw=duplicate_raw,
                    classified_monotonic_ns=(
                        duplicate_parser.recorded_monotonic_ns + 1
                    ),
                    idempotency_key="v49e-post-bind-duplicate",
                )
                assert (
                    duplicate.classification.provider_disposition.disposition_kind
                    is (MessageDispositionKind.CONTROL_SUBSCRIPTION_ACK)
                )
                assert duplicate.ack_binding is None
                assert duplicate.ack_event is None
                assert duplicate.provider_failure_event is None
                assert duplicate.termination is None
                harness.store.verify()
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_fragmented_ack_reconstructs_in_order_and_uses_final_raw_receipt() -> None:
    async def scenario() -> None:
        with TemporaryDirectory(prefix="ry-v49e-projection-fragmented-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                intent = await _prepare_dispatched_subscription(harness)
                raw_payload = _ack_bytes(request_id=intent.request_id)
                split = len(raw_payload) // 2
                first_payload, second_payload = raw_payload[:split], raw_payload[split:]
                first_frame = Frame(Opcode.TEXT, first_payload, fin=False).serialize(
                    mask=False
                )
                second_frame = Frame(Opcode.CONT, second_payload, fin=True).serialize(
                    mask=False
                )
                genesis = WebSocketParserCursorV49C(
                    cursor_sequence=0,
                    next_stream_octet=0,
                    websocket_state=WebSocketParserStateV49C.OPEN,
                )
                first, cursor, retained, first_raw = _append_parser_frame(
                    harness,
                    frame_bytes=first_frame,
                    ingress_sequence=1,
                    cursor_before=genesis,
                    fragmented_bytes_before=b"",
                )
                second, _, retained, second_raw = _append_parser_frame(
                    harness,
                    frame_bytes=second_frame,
                    ingress_sequence=2,
                    cursor_before=cursor,
                    fragmented_bytes_before=retained,
                )
                assert retained == b""
                parser_ids = (
                    first.transport_actor_event_id,
                    second.transport_actor_event_id,
                )

                before_wrong_receipt = _projection_counts(harness.store)
                session = harness.runtime._session  # noqa: SLF001
                signer = harness.runtime._signer  # noqa: SLF001
                assert session is not None
                with pytest.raises(
                    PhysicalProjectionV4ConflictError,
                    match="canonical parser/RAW evidence",
                ):
                    harness.store.commit_actor_provider_message_v49e_for_test(
                        transport_session_id=session.transport_session_id,
                        source_parser_event_ids=parser_ids,
                        websocket_opcode=WebSocketOpcodeV49C.TEXT,
                        raw_payload=raw_payload,
                        collector_received_at=first_raw.raw.received_at,
                        collector_received_monotonic_ns=(
                            first_raw.raw.received_monotonic_ns
                        ),
                        classified_monotonic_ns=(second.recorded_monotonic_ns + 1),
                        driver_policy_id=harness.driver.driver_policy_id,
                        signer=signer,
                        idempotency_key="v49e-forged-first-fragment-receipt",
                    )
                assert _projection_counts(harness.store) == before_wrong_receipt

                result = _commit(
                    harness,
                    parser_event_ids=parser_ids,
                    raw_payload=raw_payload,
                    final_raw=second_raw,
                    classified_monotonic_ns=second.recorded_monotonic_ns + 1,
                    idempotency_key="v49e-valid-fragmented-ack",
                )
                envelope = result.segment.envelopes[0]
                assert envelope.raw_payload == first_payload + second_payload
                assert envelope.collector_received_wall_ts == second_raw.raw.received_at
                assert envelope.collector_received_monotonic_ns == (
                    second_raw.raw.received_monotonic_ns
                )
                assert envelope.collector_received_wall_ts != first_raw.raw.received_at
                assert result.application_event.payload.source_parser_event_ids == (
                    parser_ids
                )
                assert result.ack_binding is not None
                assert result.ack_binding.echoed_request_id == intent.request_id
                harness.store.verify()
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_wrong_ack_request_id_retains_classification_and_terminalizes_atomically() -> (
    None
):
    async def scenario() -> None:
        with TemporaryDirectory(
            prefix="ry-v49e-projection-wrong-request-"
        ) as directory:
            harness = await _build_harness(Path(directory))
            try:
                intent = await _prepare_dispatched_subscription(harness)
                raw_payload = _ack_bytes(request_id="wrong-request-id")
                frame = Frame(Opcode.TEXT, raw_payload).serialize(mask=False)
                parser, _, _, committed_raw = _append_parser_frame(
                    harness,
                    frame_bytes=frame,
                    ingress_sequence=1,
                    cursor_before=WebSocketParserCursorV49C(
                        cursor_sequence=0,
                        next_stream_octet=0,
                        websocket_state=WebSocketParserStateV49C.OPEN,
                    ),
                    fragmented_bytes_before=b"",
                )
                assert intent.request_id != "wrong-request-id"
                result = _commit(
                    harness,
                    parser_event_ids=(parser.transport_actor_event_id,),
                    raw_payload=raw_payload,
                    final_raw=committed_raw,
                    classified_monotonic_ns=parser.recorded_monotonic_ns + 1,
                    idempotency_key="v49e-wrong-request-id",
                )
                assert result.classification.provider_disposition.disposition_kind is (
                    MessageDispositionKind.CONTROL_SUBSCRIPTION_ACK
                )
                assert result.ack_binding is None
                assert result.ack_event is None
                assert result.provider_failure_event is not None
                assert result.provider_failure_event.payload.kind is (
                    TerminalTransitionKindV49C.FATAL
                )
                assert result.provider_failure_event.payload.cause_code == (
                    "SUBSCRIPTION_ACK_INTEGRITY_FAILURE"
                )
                assert result.termination is not None
                assert result.termination.reason is (
                    TransportSessionTerminationReasonV4.TRANSPORT_ERROR
                )
                assert (
                    harness.store._connection.execute(  # noqa: SLF001
                        "SELECT 1 FROM operation_batches WHERE idempotency_key = ?",
                        ("v49e-wrong-request-id",),
                    ).fetchone()
                    is not None
                )
                committed_counts = _projection_counts(harness.store)
                replay = _commit(
                    harness,
                    parser_event_ids=(parser.transport_actor_event_id,),
                    raw_payload=raw_payload,
                    final_raw=committed_raw,
                    classified_monotonic_ns=parser.recorded_monotonic_ns + 1,
                    idempotency_key="v49e-wrong-request-id",
                )
                assert replay == result
                assert replay is not result
                assert _projection_counts(harness.store) == committed_counts
                harness.store.verify()
            finally:
                await harness.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "case",
    (
        "malformed_fields",
        "provider_rejected",
        "missing_request_id",
        "empty_request_id",
        "extra_schema",
        "binary_exact_json",
        "binary_near_miss",
    ),
)
def test_pending_subscribe_near_misses_fail_closed_after_classification(
    case: str,
) -> None:
    async def scenario() -> None:
        with TemporaryDirectory(prefix=f"ry-v49e-projection-{case}-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                intent = await _prepare_dispatched_subscription(harness)
                raw_payload, opcode = _invalid_ack_case(
                    case, request_id=intent.request_id
                )
                parser, _, committed_raw = _append_complete_message(
                    harness,
                    raw_payload=raw_payload,
                    ingress_sequence=1,
                    websocket_opcode=opcode,
                )
                result = _commit(
                    harness,
                    parser_event_ids=(parser.transport_actor_event_id,),
                    raw_payload=raw_payload,
                    final_raw=committed_raw,
                    classified_monotonic_ns=parser.recorded_monotonic_ns + 1,
                    idempotency_key=f"v49e-pending-near-miss-{case}",
                    websocket_opcode=opcode,
                )

                assert result.classification.disposition.message_disposition_id == (
                    result.application_event.payload.message_disposition_id
                )
                assert result.ack_binding is None
                assert result.ack_event is None
                assert result.provider_failure_event is not None
                assert result.provider_failure_event.payload.kind is (
                    TerminalTransitionKindV49C.FATAL
                )
                assert result.provider_failure_event.payload.cause_code == (
                    "SUBSCRIPTION_ACK_INTEGRITY_FAILURE"
                )
                assert result.termination is not None
                assert result.termination.reason is (
                    TransportSessionTerminationReasonV4.TRANSPORT_ERROR
                )
                assert (
                    harness.store._source_metadata(  # noqa: SLF001
                        result.termination.transport_session_termination_id
                    )[0]
                    == harness.store._source_metadata(  # noqa: SLF001
                        result.provider_failure_event.transport_actor_event_id
                    )[0]
                    + 1
                )
                harness.store.verify()
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_subscribe_shape_before_completed_dispatch_classifies_only() -> None:
    async def scenario() -> None:
        with TemporaryDirectory(prefix="ry-v49e-projection-pre-dispatch-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                await _establish(harness)
                _bind_projection_clock_to_owner(harness)
                await harness.runtime.activate_causal_transport_actor_v49c()
                harness.runtime._authorize_send_permit_core(  # noqa: SLF001
                    idempotency_key="v49e-pre-dispatch-intent"
                )
                intent = harness.runtime._intent  # noqa: SLF001
                assert intent is not None
                raw_payload = _ack_bytes(request_id="wrong-pre-dispatch-request")
                parser, _, committed_raw = _append_complete_message(
                    harness,
                    raw_payload=raw_payload,
                    ingress_sequence=1,
                )
                result = _commit(
                    harness,
                    parser_event_ids=(parser.transport_actor_event_id,),
                    raw_payload=raw_payload,
                    final_raw=committed_raw,
                    classified_monotonic_ns=parser.recorded_monotonic_ns + 1,
                    idempotency_key="v49e-pre-dispatch-response",
                )
                assert result.classification.provider_disposition.disposition_kind is (
                    MessageDispositionKind.CONTROL_SUBSCRIPTION_ACK
                )
                assert result.ack_binding is None
                assert result.ack_event is None
                assert result.provider_failure_event is None
                assert result.termination is None
                harness.store.verify()
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_exact_late_ack_classifies_only_and_never_retro_binds() -> None:
    async def scenario() -> None:
        with TemporaryDirectory(prefix="ry-v49e-projection-late-ack-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                intent = await _prepare_dispatched_subscription(harness)
                session = harness.runtime._session  # noqa: SLF001
                assert session is not None
                chain = harness.store._load_transport_actor_chain_v49c(  # noqa: SLF001
                    session.transport_session_id
                )
                _, _, completion_event = (
                    harness.store._actor_subscription_dispatch_v49e(  # noqa: SLF001
                        chain,
                        outbound_subscription_intent_id=(
                            intent.outbound_subscription_intent_id
                        ),
                    )
                )
                completion = completion_event.payload
                deadline_ns = completion.completed_monotonic_ns + (
                    harness.store._duration_nanoseconds_v49e(  # noqa: SLF001
                        intent.ack_not_after - completion.completed_at
                    )
                )
                late_received_at = intent.ack_not_after + timedelta(microseconds=1)
                harness.store._clock = lambda: (
                    late_received_at
                    + timedelta(  # noqa: SLF001
                        seconds=1
                    )
                )
                raw_payload = _ack_bytes(request_id=intent.request_id)
                parser, _, committed_raw = _append_complete_message(
                    harness,
                    raw_payload=raw_payload,
                    ingress_sequence=1,
                    received_at=late_received_at,
                    received_monotonic_ns=deadline_ns + 1,
                )
                result = _commit(
                    harness,
                    parser_event_ids=(parser.transport_actor_event_id,),
                    raw_payload=raw_payload,
                    final_raw=committed_raw,
                    classified_monotonic_ns=parser.recorded_monotonic_ns + 1,
                    idempotency_key="v49e-late-exact-ack",
                )
                assert result.classification.provider_disposition.disposition_kind is (
                    MessageDispositionKind.CONTROL_SUBSCRIPTION_ACK
                )
                assert result.ack_binding is None
                assert result.ack_event is None
                assert result.provider_failure_event is None
                assert result.termination is None
                harness.store.verify()
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_pending_ack_conflicting_with_prior_provider_pong_terminalizes() -> None:
    async def scenario() -> None:
        with TemporaryDirectory(
            prefix="ry-v49e-projection-conn-conflict-"
        ) as directory:
            harness = await _build_harness(Path(directory))
            try:
                intent = await _prepare_dispatched_subscription(harness)
                malformed_payload = b'{"op":"subscribe","success":true'
                malformed_parser, cursor, malformed_raw = _append_complete_message(
                    harness,
                    raw_payload=malformed_payload,
                    ingress_sequence=1,
                )
                malformed = _commit(
                    harness,
                    parser_event_ids=(malformed_parser.transport_actor_event_id,),
                    raw_payload=malformed_payload,
                    final_raw=malformed_raw,
                    classified_monotonic_ns=(
                        malformed_parser.recorded_monotonic_ns + 1
                    ),
                    idempotency_key="v49e-malformed-token-negative-control",
                )
                assert (
                    malformed.classification.provider_disposition.disposition_kind
                    is (MessageDispositionKind.MALFORMED_PAYLOAD)
                )
                assert malformed.ack_binding is None
                assert malformed.provider_failure_event is None
                assert malformed.termination is None

                pong_payload = _pong_bytes(connection_id="provider-connection-a")
                pong_parser, cursor, pong_raw = _append_complete_message(
                    harness,
                    raw_payload=pong_payload,
                    ingress_sequence=2,
                    cursor_before=cursor,
                )
                pong = _commit(
                    harness,
                    parser_event_ids=(pong_parser.transport_actor_event_id,),
                    raw_payload=pong_payload,
                    final_raw=pong_raw,
                    classified_monotonic_ns=pong_parser.recorded_monotonic_ns + 1,
                    idempotency_key="v49e-prior-provider-pong",
                )
                assert pong.classification.provider_disposition.disposition_kind is (
                    MessageDispositionKind.CONTROL_PONG
                )
                assert pong.ack_binding is None
                assert pong.provider_failure_event is None

                ack_payload = _ack_bytes(
                    request_id=intent.request_id,
                    connection_id="provider-connection-b",
                )
                ack_parser, _, ack_raw = _append_complete_message(
                    harness,
                    raw_payload=ack_payload,
                    ingress_sequence=3,
                    cursor_before=cursor,
                )
                result = _commit(
                    harness,
                    parser_event_ids=(ack_parser.transport_actor_event_id,),
                    raw_payload=ack_payload,
                    final_raw=ack_raw,
                    classified_monotonic_ns=ack_parser.recorded_monotonic_ns + 1,
                    idempotency_key="v49e-provider-connection-conflict",
                )
                assert result.ack_binding is None
                assert result.provider_failure_event is not None
                assert result.termination is not None
                assert result.termination.reason is (
                    TransportSessionTerminationReasonV4.TRANSPORT_ERROR
                )
                harness.store.verify()
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_provider_integrity_failure_fault_rolls_back_complete_composite() -> None:
    armed = False

    def fail(stage: str) -> None:
        if armed and stage == "after_transport_session_termination_insert":
            raise RuntimeError("injected-v49e-provider-failure")

    async def scenario() -> None:
        nonlocal armed
        with TemporaryDirectory(prefix="ry-v49e-provider-fault-") as directory:
            harness = await _build_harness(Path(directory), fault_injector=fail)
            try:
                await _prepare_dispatched_subscription(harness)
                raw_payload = _ack_bytes(request_id="wrong-request-id")
                parser, _, committed_raw = _append_complete_message(
                    harness,
                    raw_payload=raw_payload,
                    ingress_sequence=1,
                )
                before = _projection_counts(harness.store)
                armed = True
                with pytest.raises(
                    RuntimeError, match="injected-v49e-provider-failure"
                ):
                    _commit(
                        harness,
                        parser_event_ids=(parser.transport_actor_event_id,),
                        raw_payload=raw_payload,
                        final_raw=committed_raw,
                        classified_monotonic_ns=parser.recorded_monotonic_ns + 1,
                        idempotency_key="v49e-faulted-provider-failure",
                    )
                armed = False
                assert _projection_counts(harness.store) == before
                assert (
                    harness.store._connection.execute(  # noqa: SLF001
                        "SELECT 1 FROM operation_batches WHERE idempotency_key = ?",
                        ("v49e-faulted-provider-failure",),
                    ).fetchone()
                    is None
                )
                harness.store.verify()
            finally:
                armed = False
                await harness.close()

    asyncio.run(scenario())


def test_fault_after_ack_binding_rolls_back_complete_composite_command() -> None:
    armed = False

    def fail(stage: str) -> None:
        if armed and stage == "after_subscription_ack_binding_insert":
            raise RuntimeError("injected-v49e-ack-binding-failure")

    async def scenario() -> None:
        nonlocal armed
        with TemporaryDirectory(prefix="ry-v49e-projection-rollback-") as directory:
            harness = await _build_harness(Path(directory), fault_injector=fail)
            try:
                intent = await _prepare_dispatched_subscription(harness)
                raw_payload = _ack_bytes(request_id=intent.request_id)
                frame = Frame(Opcode.TEXT, raw_payload).serialize(mask=False)
                parser, _, _, committed_raw = _append_parser_frame(
                    harness,
                    frame_bytes=frame,
                    ingress_sequence=1,
                    cursor_before=WebSocketParserCursorV49C(
                        cursor_sequence=0,
                        next_stream_octet=0,
                        websocket_state=WebSocketParserStateV49C.OPEN,
                    ),
                    fragmented_bytes_before=b"",
                )
                before = _projection_counts(harness.store)
                armed = True

                with pytest.raises(
                    RuntimeError, match="injected-v49e-ack-binding-failure"
                ):
                    _commit(
                        harness,
                        parser_event_ids=(parser.transport_actor_event_id,),
                        raw_payload=raw_payload,
                        final_raw=committed_raw,
                        classified_monotonic_ns=parser.recorded_monotonic_ns + 1,
                        idempotency_key="v49e-faulted-composite",
                    )

                armed = False
                assert _projection_counts(harness.store) == before
                assert (
                    harness.store._connection.execute(  # noqa: SLF001
                        "SELECT 1 FROM operation_batches WHERE idempotency_key = ?",
                        ("v49e-faulted-composite",),
                    ).fetchone()
                    is None
                )
                harness.store.verify()
            finally:
                armed = False
                await harness.close()

    asyncio.run(scenario())

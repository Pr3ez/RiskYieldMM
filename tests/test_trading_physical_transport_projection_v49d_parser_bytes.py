from __future__ import annotations

import asyncio
import base64
import hashlib
import sqlite3
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from riskyieldmm.trading.canonical import canonical_json_bytes, sha256_digest
from riskyieldmm.trading.physical_projection_v4 import (
    PhysicalProjectionV4ConflictError,
)
from riskyieldmm.trading.physical_transport_actor_v49c import (
    CommittedRawChunkV49C,
    DelineatedServerFrameV49C,
    ParserFeedUnitKindV49C,
    ParserTransitionPayloadV49C,
    RawSourceSliceV49C,
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


def _raw_commit(
    committed: object,
    data: bytes,
    *,
    ingress_sequence: int,
) -> RawIngressCommitV4:
    session = committed.session
    binding = committed.binding
    encoded = (base64.b64encode(data).decode("ascii"),)
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
        ingress_sequence=ingress_sequence,
        raw_ingress_chunks_base64=encoded,
        raw_ingress_chunks_sha256=(hashlib.sha256(data).hexdigest(),),
        raw_ingress_batch_sha256=sha256_digest(
            {
                "domain": "RiskYieldMMExactOrderedDecryptedIngressChunksV4_5",
                "ordered_chunks_base64": list(encoded),
            }
        ),
        received_at=T0 + timedelta(milliseconds=900 + ingress_sequence),
        monotonic_clock_domain_id=session.monotonic_clock_domain_id,
        received_monotonic_ns=(
            session.handshake_completed_monotonic_ns + ingress_sequence * 1_000_000
        ),
    )


def _committed_chunk(committed_raw: object) -> CommittedRawChunkV49C:
    raw = committed_raw.raw
    payload = committed_raw.event.payload
    return CommittedRawChunkV49C(
        raw_ingress_commit_id=raw.raw_ingress_commit_id,
        projection_receipt_sequence=committed_raw.receipt.global_sequence,
        projection_receipt_hash=committed_raw.receipt.receipt_hash,
        raw_local_start_octet=0,
        stream_start_octet=payload.stream_start_octet,
        data=raw.raw_bytes,
    )


def _cross_raw_parser_event(
    first_raw: object,
    second_raw: object,
) -> TransportActorEventV49C:
    first = delineate_next_server_frame_v49c(
        prior_tail=RetainedIngressTailV49C(),
        committed_raw_chunks=(_committed_chunk(first_raw),),
    )
    assert first.unit is None
    assert first.retained_tail.total_octets == len(first_raw.raw.raw_bytes)

    second = delineate_next_server_frame_v49c(
        prior_tail=first.retained_tail,
        committed_raw_chunks=(_committed_chunk(second_raw),),
    )
    assert type(second.unit) is DelineatedServerFrameV49C
    assert second.retained_tail.total_octets == 0

    raw_event = second_raw.event
    raw = second_raw.raw
    payload = ParserTransitionPayloadV49C(
        cursor_before=WebSocketParserCursorV49C(
            cursor_sequence=0,
            next_stream_octet=0,
            websocket_state=WebSocketParserStateV49C.OPEN,
        ),
        cursor_after=WebSocketParserCursorV49C(
            cursor_sequence=1,
            next_stream_octet=second.unit.metadata.stream_end_octet,
            websocket_state=WebSocketParserStateV49C.OPEN,
        ),
        feed_unit_kind=ParserFeedUnitKindV49C.COMPLETE_FRAME,
        source_slices=second.unit.source_slices,
        frame=second.unit.metadata,
        parser_error=None,
        ordered_protocol_output_chunks_base64=(),
        ordered_protocol_output_chunks_sha256=(),
        protocol_output_batch_sha256=None,
        send_eof_after_output=False,
        processed_at=second_raw.receipt.committed_at,
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
        recorded_at=second_raw.receipt.committed_at,
        recorded_monotonic_ns=raw.received_monotonic_ns + 1,
        actor_sequence=3,
        previous_event_id=raw_event.transport_actor_event_id,
        event_kind=TransportActorEventKindV49C.PARSER_TRANSITION,
        payload=payload,
    )


def _event_with_payload(
    event: TransportActorEventV49C,
    payload: ParserTransitionPayloadV49C,
) -> TransportActorEventV49C:
    return TransportActorEventV49C.create(
        **{
            name: payload if name == "payload" else getattr(event, name)
            for name in event.__dataclass_fields__
        }
    )


async def _append_split_frame(harness: object) -> tuple[object, object, object]:
    committed = await _establish(harness)
    first_raw = harness.store.append_actor_raw_ingress_v49c_for_test(
        _raw_commit(committed, b"\x81", ingress_sequence=1),
        driver_policy_id=harness.driver.driver_policy_id,
        idempotency_key="v49d-parser-bytes-raw-1",
    )
    second_raw = harness.store.append_actor_raw_ingress_v49c_for_test(
        _raw_commit(committed, b"\x01x", ingress_sequence=2),
        driver_policy_id=harness.driver.driver_policy_id,
        idempotency_key="v49d-parser-bytes-raw-2",
    )
    parser_event = _cross_raw_parser_event(first_raw, second_raw)
    return first_raw, second_raw, parser_event


def test_projection_accepts_exact_cross_raw_frame_and_full_verify() -> None:
    async def scenario() -> None:
        with TemporaryDirectory(prefix="ry-v49d-cross-raw-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                _, _, parser_event = await _append_split_frame(harness)
                appended = harness.store.append_transport_actor_event_v49c_for_test(
                    parser_event,
                    idempotency_key="v49d-parser-bytes-valid",
                )
                assert appended == parser_event
                assert len(parser_event.payload.source_slices) == 2
                report = harness.store.verify()
                assert report.raw_ingress_commit_count == 2
                assert report.transport_actor_event_count == 3
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_projection_rejects_same_length_metadata_hash_from_other_bytes() -> None:
    async def scenario() -> None:
        with TemporaryDirectory(prefix="ry-v49d-forged-frame-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                _, _, valid = await _append_split_frame(harness)
                other_frame = b"\x81\x01y"
                forged_metadata = replace(
                    valid.payload.frame,
                    frame_sha256=hashlib.sha256(other_frame).hexdigest(),
                    payload_sha256=hashlib.sha256(b"y").hexdigest(),
                )
                forged_payload = replace(valid.payload, frame=forged_metadata)
                forged = _event_with_payload(valid, forged_payload)

                with pytest.raises(
                    PhysicalProjectionV4ConflictError,
                    match="metadata differs from exact RAW source bytes",
                ):
                    harness.store.append_transport_actor_event_v49c_for_test(
                        forged,
                        idempotency_key="v49d-parser-bytes-forged-frame",
                    )
                assert harness.store.verify().transport_actor_event_count == 2
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_projection_rejects_source_slice_rebound_to_unrelated_raw_commit() -> None:
    async def scenario() -> None:
        with TemporaryDirectory(prefix="ry-v49d-forged-source-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                first_raw, _, valid = await _append_split_frame(harness)
                first_source, second_source = valid.payload.source_slices
                unrelated = RawSourceSliceV49C(
                    raw_ingress_commit_id=first_raw.raw.raw_ingress_commit_id,
                    projection_receipt_sequence=(first_raw.receipt.global_sequence),
                    projection_receipt_hash=first_raw.receipt.receipt_hash,
                    stream_start_octet=second_source.stream_start_octet,
                    stream_end_octet=second_source.stream_end_octet,
                    raw_local_start_octet=0,
                    raw_local_end_octet=(
                        second_source.stream_end_octet
                        - second_source.stream_start_octet
                    ),
                )
                forged_payload = replace(
                    valid.payload,
                    source_slices=(first_source, unrelated),
                )
                forged = _event_with_payload(valid, forged_payload)

                with pytest.raises(
                    PhysicalProjectionV4ConflictError,
                    match="exact durable chain",
                ):
                    harness.store.append_transport_actor_event_v49c_for_test(
                        forged,
                        idempotency_key="v49d-parser-bytes-forged-source",
                    )
                assert harness.store.verify().transport_actor_event_count == 2
            finally:
                await harness.close()

    asyncio.run(scenario())


def test_database_rejects_direct_raw_projection_row_mutation() -> None:
    async def scenario() -> None:
        with TemporaryDirectory(prefix="ry-v49d-mutated-raw-") as directory:
            harness = await _build_harness(Path(directory))
            try:
                _, second_raw, parser_event = await _append_split_frame(harness)
                harness.store.append_transport_actor_event_v49c_for_test(
                    parser_event,
                    idempotency_key="v49d-parser-bytes-before-mutation",
                )
                harness.store.verify()

                with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                    harness.store._connection.execute(  # noqa: SLF001
                        """
                        UPDATE raw_ingress_commits
                        SET raw_ingress_chunks_blob = ?
                        WHERE raw_ingress_commit_id = ?
                        """,
                        (
                            canonical_json_bytes(
                                [base64.b64encode(b"\x01y").decode("ascii")]
                            ),
                            bytes.fromhex(second_raw.raw.raw_ingress_commit_id),
                        ),
                    )
                assert harness.store.verify().transport_actor_event_count == 3
            finally:
                await harness.close()

    asyncio.run(scenario())

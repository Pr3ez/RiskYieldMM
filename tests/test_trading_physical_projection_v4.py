from __future__ import annotations

import shutil
import sqlite3
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from riskyieldmm.trading.canonical import CanonicalizationError
from riskyieldmm.trading.physical_evidence_v4 import (
    PhysicalMessageV4,
    PhysicalScopeManifestV4,
    disposition_leaf_input_v4,
    message_disposition_from_v3,
)
from riskyieldmm.trading.physical_market_data import (
    BYBIT_V5_INSTRUMENT_INFO_CLASSIFIER_RELEASE_HASH,
    CaptureSegmentV3,
    MessageDispositionKind,
    PhysicalVintage,
    PrefixHealth,
    ProviderAdapterPolicyV3,
    ProviderMessageDispositionV3,
    ProviderMessageEnvelopeV3,
    ProviderMessageTypeV3,
    build_bybit_v5_message_disposition,
)
from riskyieldmm.trading.physical_projection_v4 import (
    ClassificationAppendV4,
    PhysicalProjectionStoreV4,
    PhysicalProjectionV4ConflictError,
    PhysicalProjectionV4IdempotencyError,
    PhysicalRecordKindV4,
)
from riskyieldmm.trading.transparency_log import rfc9162_tree_hash
from tests.test_trading_physical_market_data_v3 import (
    T0,
    bar_policy,
    digest,
    kline_bytes,
    source_member_placeholder,
)


@dataclass
class FixedClock:
    value: datetime

    def __call__(self) -> datetime:
        return self.value


def scope_for(policy: ProviderAdapterPolicyV3) -> PhysicalScopeManifestV4:
    member = source_member_placeholder(policy)
    return PhysicalScopeManifestV4(
        source_member_key=member.source_member_key,
        instrument_mapping_id=digest("bybit-btcusdt-mapping"),
        provider_id=policy.provider_id,
        venue_id=policy.venue_id,
        environment_id=policy.environment_id,
        asset_id=policy.asset_id,
        concrete_contract_id=policy.concrete_contract_id,
        timeframe_id=policy.timeframe_id,
        primary_adapter_policy_id=policy.adapter_policy_id,
        primary_classifier_release_hash=(policy.message_classifier_release_hash),
        required_status_adapter_policy_id=None,
        required_status_classifier_release_hash=None,
        calendar_manifest_id=policy.calendar_manifest_id,
        protocol_lineage_id=digest("physical-v4-protocol-lineage"),
        health_policy_id=policy.feed_health_policy_id,
        frozen_at=policy.frozen_at,
    )


def capture_segment(
    policy: ProviderAdapterPolicyV3,
    payloads: list[bytes],
) -> CaptureSegmentV3:
    envelopes = tuple(
        ProviderMessageEnvelopeV3.from_raw(
            collector_sequence=index,
            collector_received_wall_ts=T0 + timedelta(microseconds=index),
            collector_received_monotonic_ns=index * 1_000_000,
            message_type=ProviderMessageTypeV3.TEXT,
            raw_payload=payload,
        )
        for index, payload in enumerate(payloads, start=1)
    )
    return CaptureSegmentV3(
        adapter_policy_id=policy.adapter_policy_id,
        provider_native_key=policy.provider_native_key,
        collector_instance_id="collector-v4",
        collector_boot_id="boot-v4",
        connection_id="connection-v4",
        connection_generation=1,
        subscription_manifest_hash=digest("subscription-v4"),
        vintage=PhysicalVintage.REPLAY,
        envelopes=envelopes,
        closed_at=T0 + timedelta(seconds=1),
        clock_uncertainty_milliseconds=0,
    )


def classification_for(
    message: PhysicalMessageV4,
    *,
    classifier_release_hash: str,
    kind: MessageDispositionKind = MessageDispositionKind.CONTROL_PONG,
    duplicate_of: ClassificationAppendV4 | None = None,
) -> ClassificationAppendV4:
    provider = ProviderMessageDispositionV3(
        adapter_policy_id=message.adapter_policy_id,
        capture_segment_id=message.capture_segment_id,
        message_receipt_id=message.message_receipt_id,
        raw_payload_sha256=message.raw_payload_sha256,
        disposition_kind=kind,
        classifier_release_hash=classifier_release_hash,
        classified_at=T0 + timedelta(minutes=2),
        duplicate_of_message_receipt_id=(
            None
            if duplicate_of is None
            else duplicate_of.provider_disposition.message_receipt_id
        ),
        duplicate_of_disposition_id=(
            None
            if duplicate_of is None
            else duplicate_of.provider_disposition.provider_message_disposition_id
        ),
    )
    disposition = message_disposition_from_v3(
        message=message,
        disposition=provider,
        duplicate_of_v4_disposition_id=(
            None
            if duplicate_of is None
            else duplicate_of.disposition.message_disposition_id
        ),
    )
    return ClassificationAppendV4(
        disposition=disposition,
        provider_disposition=provider,
    )


def normalized_classification_for(
    *,
    policy: ProviderAdapterPolicyV3,
    scope: PhysicalScopeManifestV4,
    segment: CaptureSegmentV3,
    message: PhysicalMessageV4,
) -> ClassificationAppendV4:
    disposition, derivation, revision = build_bybit_v5_message_disposition(
        adapter_policy=policy,
        segment=segment,
        message_receipt_id=message.message_receipt_id,
        source_member_key=scope.source_member_key,
        instrument_mapping_id=scope.instrument_mapping_id,
        durably_appended_ts=T0 + timedelta(minutes=1, milliseconds=400),
        normalized_at=T0 + timedelta(minutes=1, milliseconds=500),
        available_at=T0 + timedelta(minutes=1, milliseconds=600),
        classified_at=T0 + timedelta(minutes=1, milliseconds=700),
    )
    assert derivation is not None and revision is not None
    projected = message_disposition_from_v3(
        message=message,
        disposition=disposition,
    )
    return ClassificationAppendV4(
        disposition=projected,
        provider_disposition=disposition,
        derivation=derivation,
        revision=revision,
    )


def test_projection_round_trip_idempotency_strictness_and_indexes(
    tmp_path: Path,
) -> None:
    policy = bar_policy(requires_status=False)
    scope = scope_for(policy)
    database = tmp_path / "physical-v4.sqlite3"
    clock = FixedClock(T0 + timedelta(minutes=2))

    with PhysicalProjectionStoreV4(database, clock=clock) as store:
        empty = store.verify()
        assert empty.receipt_count == empty.canonical_record_count == 0
        assert len(store.ledger_id) == len(store.schema_fingerprint) == 64

        assert store.append_scope(scope, idempotency_key="scope") == scope
        receipt_count = store.verify().receipt_count
        assert store.append_scope(scope, idempotency_key="scope") == scope
        assert store.verify().receipt_count == receipt_count

        rotated = PhysicalScopeManifestV4(
            **{
                **{name: getattr(scope, name) for name in scope.__dataclass_fields__},
                "source_member_key": digest("bybit-btcusdt-1m-rotated"),
            }
        )
        with pytest.raises(PhysicalProjectionV4IdempotencyError):
            store.append_scope(rotated, idempotency_key="scope")

        bootstrapping = store.append_cutoff(
            physical_scope_manifest_id=scope.physical_scope_manifest_id,
            knowledge_cutoff_ts=T0,
            vintage=PhysicalVintage.REPLAY,
            health=PrefixHealth.BOOTSTRAPPING,
            health_reason_codes=("EMPTY_EVIDENCE_PREFIX",),
            health_valid_until=T0 + timedelta(seconds=30),
            idempotency_key="empty-cutoff",
        )
        assert bootstrapping.tree_size == 0
        assert bootstrapping.evidence_tree_head_id is None

        control_payload = (
            b'{"success":true,"ret_msg":"pong","conn_id":"conn-1","op":"ping"}'
        )
        segment = capture_segment(
            policy,
            [kline_bytes(), control_payload, control_payload],
        )
        messages = store.append_messages(
            physical_scope_manifest_id=scope.physical_scope_manifest_id,
            segment=segment,
            idempotency_key="messages",
        )
        classifications = (
            normalized_classification_for(
                policy=policy,
                scope=scope,
                segment=segment,
                message=messages[0],
            ),
            *(
                classification_for(
                    message,
                    classifier_release_hash=(scope.primary_classifier_release_hash),
                )
                for message in messages[1:]
            ),
        )
        dispositions = tuple(item.disposition for item in classifications)
        pairs = store.append_classification_batch(
            classifications, idempotency_key="dispositions"
        )
        assert tuple(item for item, _ in pairs) == dispositions
        assert (
            pairs[-1][1].tree_root
            == rfc9162_tree_hash(
                [disposition_leaf_input_v4(item) for item in dispositions]
            ).hex()
        )

        with pytest.raises(
            PhysicalProjectionV4ConflictError,
            match="caller-selected HEALTHY is forbidden",
        ):
            store.append_cutoff(
                physical_scope_manifest_id=scope.physical_scope_manifest_id,
                knowledge_cutoff_ts=T0 + timedelta(minutes=1, seconds=1),
                vintage=PhysicalVintage.REPLAY,
                health=PrefixHealth.HEALTHY,
                health_reason_codes=(),
                event_time_watermark=T0 + timedelta(minutes=1),
                health_valid_until=T0 + timedelta(minutes=2),
                idempotency_key="forged-healthy-cutoff",
            )
        research_cutoff = store.append_cutoff(
            physical_scope_manifest_id=scope.physical_scope_manifest_id,
            knowledge_cutoff_ts=T0 + timedelta(minutes=1, seconds=1),
            vintage=PhysicalVintage.REPLAY,
            health=PrefixHealth.RECOVERING,
            health_reason_codes=("NON_AUTHORITATIVE_RESEARCH_CUTOFF",),
            event_time_watermark=T0 + timedelta(minutes=1),
            health_valid_until=T0 + timedelta(minutes=2),
            idempotency_key="research-cutoff",
        )
        assert research_cutoff.tree_size == len(dispositions)

        report = store.verify()
        assert report.receipt_count == report.canonical_record_count == 18
        assert report.scope_count == 1
        assert report.message_count == report.disposition_count == 3
        assert report.disposition_provenance_count == 3
        assert report.observation_derivation_count == 1
        assert report.observation_revision_count == 1
        assert report.tree_head_count == 3
        assert report.stored_hash_count == 4
        assert report.cutoff_count == 2
        assert report.batch_count == 5

        query_plan = store._connection.execute(  # noqa: SLF001
            """
            EXPLAIN QUERY PLAN
            SELECT scope_message_sequence FROM physical_messages
            WHERE physical_scope_manifest_id = ?
              AND source_receipt_sequence <= ?
            """,
            (bytes.fromhex(scope.physical_scope_manifest_id), 10_000),
        ).fetchall()
        assert "messages_scope_receipt_v4" in " ".join(str(row) for row in query_plan)

        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            store._connection.execute(  # noqa: SLF001
                "UPDATE physical_scopes SET source_member_key = ?",
                (sqlite3.Binary(bytes(32)),),
            )
        with pytest.raises(sqlite3.IntegrityError):
            store._connection.execute(  # noqa: SLF001
                """
                INSERT INTO canonical_records(
                    identity_id, record_kind, content_hash,
                    canonical_blob, first_receipt_sequence
                ) VALUES('not-a-blob', 'INVALID', zeroblob(32), x'00', 9999)
                """
            )

        ledger_id = store.ledger_id
        fingerprint = store.schema_fingerprint
        receipt_root = report.global_receipt_root

    with PhysicalProjectionStoreV4(database, clock=clock) as reopened:
        reopened_report = reopened.verify()
        assert reopened.ledger_id == ledger_id
        assert reopened.schema_fingerprint == fingerprint
        assert reopened_report.global_receipt_root == receipt_root


class InjectedFailure(RuntimeError):
    pass


def test_projection_fault_injection_rolls_back_the_complete_operation(
    tmp_path: Path,
) -> None:
    policy = bar_policy(requires_status=False)
    scope = scope_for(policy)
    database = tmp_path / "fault.sqlite3"

    def fail_after_receipt(stage: str) -> None:
        if stage == "after_receipt_insert":
            raise InjectedFailure(stage)

    with PhysicalProjectionStoreV4(
        database,
        clock=FixedClock(T0),
        fault_injector=fail_after_receipt,
    ) as store:
        with pytest.raises(InjectedFailure):
            store.append_scope(scope, idempotency_key="faulted-scope")
        report = store.verify()
        assert report.receipt_count == 0
        assert report.canonical_record_count == 0
        assert report.scope_count == 0
        assert report.batch_count == 0

    with PhysicalProjectionStoreV4(database, clock=FixedClock(T0)) as reopened:
        assert reopened.verify().receipt_count == 0
        reopened.append_scope(scope, idempotency_key="clean-scope")
        assert reopened.verify().scope_count == 1


def test_normalized_admission_requires_real_scoped_observation_outputs(
    tmp_path: Path,
) -> None:
    policy = bar_policy(requires_status=False)
    scope = scope_for(policy)
    segment = capture_segment(policy, [kline_bytes()])

    with PhysicalProjectionStoreV4(
        tmp_path / "normalized-output.sqlite3",
        clock=FixedClock(T0 + timedelta(minutes=2)),
    ) as store:
        store.append_scope(scope, idempotency_key="scope")
        (message,) = store.append_messages(
            physical_scope_manifest_id=scope.physical_scope_manifest_id,
            segment=segment,
            idempotency_key="messages",
        )
        valid = normalized_classification_for(
            policy=policy,
            scope=scope,
            segment=segment,
            message=message,
        )
        with pytest.raises(
            CanonicalizationError,
            match="requires a derivation and revision",
        ):
            ClassificationAppendV4(
                disposition=valid.disposition,
                provider_disposition=valid.provider_disposition,
            )

        assert valid.revision is not None
        wrong_revision = replace(
            valid.revision,
            observation_name="unregistered-bar-shape",
        )
        wrong_provider = replace(
            valid.provider_disposition,
            observation_revision_id=wrong_revision.observation_revision_id,
        )
        wrong_disposition = message_disposition_from_v3(
            message=message,
            disposition=wrong_provider,
        )
        wrong = ClassificationAppendV4(
            disposition=wrong_disposition,
            provider_disposition=wrong_provider,
            derivation=valid.derivation,
            revision=wrong_revision,
        )
        with pytest.raises(
            PhysicalProjectionV4ConflictError,
            match="primary V4 observation",
        ):
            store.append_classification_batch(
                (wrong,),
                idempotency_key="wrong-observation-shape",
            )
        report = store.verify()
        assert report.disposition_count == 0
        assert report.observation_revision_count == 0


def test_projection_enforces_release_and_exact_duplicate_lineage(
    tmp_path: Path,
) -> None:
    policy = bar_policy(requires_status=False)
    scope = scope_for(policy)
    database = tmp_path / "duplicate.sqlite3"
    first_raw = kline_bytes()
    segment = capture_segment(
        policy,
        [first_raw, first_raw, kline_bytes(close="101.25")],
    )

    with PhysicalProjectionStoreV4(
        database, clock=FixedClock(T0 + timedelta(minutes=2))
    ) as store:
        store.append_scope(scope, idempotency_key="scope")
        messages = store.append_messages(
            physical_scope_manifest_id=scope.physical_scope_manifest_id,
            segment=segment,
            idempotency_key="messages",
        )
        first = normalized_classification_for(
            policy=policy,
            scope=scope,
            segment=segment,
            message=messages[0],
        )
        store.append_classification_batch((first,), idempotency_key="first")

        wrong_release = classification_for(
            messages[1],
            classifier_release_hash=(BYBIT_V5_INSTRUMENT_INFO_CLASSIFIER_RELEASE_HASH),
            kind=MessageDispositionKind.EXACT_DUPLICATE,
            duplicate_of=first,
        )
        with pytest.raises(PhysicalProjectionV4ConflictError, match="release"):
            store.append_classification_batch(
                (wrong_release,), idempotency_key="wrong-release"
            )
        assert store.verify().disposition_count == 1

        duplicate = classification_for(
            messages[1],
            classifier_release_hash=scope.primary_classifier_release_hash,
            kind=MessageDispositionKind.EXACT_DUPLICATE,
            duplicate_of=first,
        )
        store.append_classification_batch((duplicate,), idempotency_key="duplicate")

        wrong_raw = classification_for(
            messages[2],
            classifier_release_hash=scope.primary_classifier_release_hash,
            kind=MessageDispositionKind.EXACT_DUPLICATE,
            duplicate_of=first,
        )
        with pytest.raises(PhysicalProjectionV4ConflictError, match="raw payload"):
            store.append_classification_batch((wrong_raw,), idempotency_key="wrong-raw")
        assert store.verify().disposition_count == 2


def test_projection_batching_does_not_change_semantic_receipts(
    tmp_path: Path,
) -> None:
    policy = bar_policy(requires_status=False)
    scope = scope_for(policy)
    baseline = tmp_path / "batch-base.sqlite3"
    # The semantic invariant is batch-boundary independence; the separate
    # selector contract suite exercises the hard 256/257 result boundary.
    message_count = 33
    clock = FixedClock(T0 + timedelta(minutes=5))

    with PhysicalProjectionStoreV4(baseline, clock=clock) as store:
        store.append_scope(scope, idempotency_key="scope")
        messages = store.append_messages(
            physical_scope_manifest_id=scope.physical_scope_manifest_id,
            segment=capture_segment(policy, [b"pong"] * message_count),
            idempotency_key="messages",
        )
    classifications = tuple(
        classification_for(
            message,
            classifier_release_hash=scope.primary_classifier_release_hash,
        )
        for message in messages
    )

    results = []
    for batch_size in (1, 17, 256):
        clone = tmp_path / f"batch-{batch_size}.sqlite3"
        shutil.copy2(baseline, clone)
        with PhysicalProjectionStoreV4(clone, clock=clock) as store:
            reloaded_messages = tuple(
                store._load_record(  # noqa: SLF001
                    PhysicalRecordKindV4.PHYSICAL_MESSAGE,
                    bytes(row[0]).hex(),
                )
                for row in store._connection.execute(  # noqa: SLF001
                    """
                    SELECT physical_message_id FROM physical_messages
                    WHERE physical_scope_manifest_id = ?
                    ORDER BY scope_message_sequence
                    """,
                    (bytes.fromhex(scope.physical_scope_manifest_id),),
                )
            )
            assert reloaded_messages == messages
            last_head = None
            for offset in range(0, len(classifications), batch_size):
                pairs = store.append_classification_batch(
                    classifications[offset : offset + batch_size],
                    idempotency_key=f"batch-{offset}",
                )
                last_head = pairs[-1][1]
            assert last_head is not None
            report = store.verify()
            results.append(
                (
                    last_head.evidence_tree_head_id,
                    last_head.tree_root,
                    report.global_receipt_root,
                    report.disposition_count,
                )
            )
    assert results[0] == results[1] == results[2]

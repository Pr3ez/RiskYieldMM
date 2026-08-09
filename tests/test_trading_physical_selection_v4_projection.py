from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from riskyieldmm.trading.evidence import DependencySelectionMode
from riskyieldmm.trading.physical_evidence_v4 import message_disposition_from_v3
from riskyieldmm.trading.physical_market_data import (
    ContinuityPolicy,
    PhysicalVintage,
    PrefixHealth,
    ProviderAdapterPolicyV3,
    SelectionStatus,
    build_bybit_v5_message_disposition,
)
from riskyieldmm.trading.physical_projection_v4 import (
    ClassificationAppendV4,
    PhysicalProjectionStoreV4,
    PhysicalProjectionV4IdempotencyError,
    PhysicalRecordKindV4,
)
from riskyieldmm.trading.physical_selection_v4 import PhysicalProtocolBindingV4
from tests.test_trading_physical_market_data_v3 import (
    T0,
    bar_policy,
    digest,
    kline_bytes,
)
from tests.test_trading_physical_market_data_v3 import (
    segment as market_segment,
)
from tests.test_trading_physical_projection_v4 import scope_for


@dataclass
class FixedClock:
    value: datetime

    def __call__(self) -> datetime:
        return self.value


def append_bar(
    store: PhysicalProjectionStoreV4,
    *,
    policy: ProviderAdapterPolicyV3,
    bar_start: datetime,
    close: str,
    operation_suffix: str,
    parent_revision_id: str | None = None,
    correction_reason: str | None = None,
    timing_offset: timedelta = timedelta(0),
):
    scope = scope_for(policy)
    parent_row = store._connection.execute(  # noqa: SLF001
        """
        SELECT capture_segment_id FROM capture_segments
        WHERE physical_scope_manifest_id = ? AND adapter_policy_id = ?
        ORDER BY source_receipt_sequence DESC LIMIT 1
        """,
        (
            bytes.fromhex(scope.physical_scope_manifest_id),
            bytes.fromhex(policy.adapter_policy_id),
        ),
    ).fetchone()
    parent = (
        None
        if parent_row is None
        else store._load_record(  # noqa: SLF001
            PhysicalRecordKindV4.CAPTURE_SEGMENT,
            bytes(parent_row[0]).hex(),
        )
    )
    collector_sequence = (
        1 if parent is None else parent.envelopes[-1].collector_sequence + 1
    )
    segment = market_segment(
        policy,
        kline_bytes(bar_start=bar_start, close=close),
        sequence=collector_sequence,
        received_at=bar_start + timedelta(minutes=1, milliseconds=200),
        parent=parent,
        vintage=PhysicalVintage.REPLAY,
    )
    (message,) = store.append_messages(
        physical_scope_manifest_id=scope.physical_scope_manifest_id,
        segment=segment,
        idempotency_key=f"messages-{operation_suffix}",
    )
    durable = bar_start + timedelta(minutes=1, milliseconds=400) + timing_offset
    provider, derivation, revision = build_bybit_v5_message_disposition(
        adapter_policy=policy,
        segment=segment,
        message_receipt_id=message.message_receipt_id,
        source_member_key=scope.source_member_key,
        instrument_mapping_id=scope.instrument_mapping_id,
        durably_appended_ts=durable,
        normalized_at=durable + timedelta(milliseconds=100),
        available_at=durable + timedelta(milliseconds=200),
        classified_at=durable + timedelta(milliseconds=300),
        parent_observation_revision_id=parent_revision_id,
        correction_reason=correction_reason,
    )
    assert derivation is not None and revision is not None
    projected = message_disposition_from_v3(
        message=message,
        disposition=provider,
    )
    store.append_classification_batch(
        (
            ClassificationAppendV4(
                disposition=projected,
                provider_disposition=provider,
                derivation=derivation,
                revision=revision,
            ),
        ),
        idempotency_key=f"classification-{operation_suffix}",
    )
    return revision


def append_cutoff(
    store: PhysicalProjectionStoreV4,
    *,
    knowledge: datetime,
    operation_suffix: str,
):
    scope = scope_for(bar_policy(requires_status=False))
    return store.append_cutoff(
        physical_scope_manifest_id=scope.physical_scope_manifest_id,
        knowledge_cutoff_ts=knowledge,
        vintage=PhysicalVintage.REPLAY,
        health=PrefixHealth.RECOVERING,
        health_reason_codes=("REPLAY_SELECTOR_TEST",),
        health_valid_until=knowledge + timedelta(minutes=5),
        idempotency_key=f"cutoff-{operation_suffix}",
    )


def binding_for(
    *,
    mode: DependencySelectionMode,
    requested_count: int,
    operation_suffix: str,
    maximum_age_seconds: int = 600,
) -> PhysicalProtocolBindingV4:
    policy = bar_policy(requires_status=False)
    scope = scope_for(policy)
    return PhysicalProtocolBindingV4(
        physical_scope_manifest_id=scope.physical_scope_manifest_id,
        protocol_manifest_id=digest("protocol-manifest-v4-1"),
        source_manifest_id=digest("source-manifest-v4-1"),
        calendar_manifest_id=scope.calendar_manifest_id,
        feature_schema_id=digest("feature-schema-v4-1"),
        dependency_slot_id=digest(f"dependency-slot-{operation_suffix}"),
        source_member_id=digest("source-member-v4-1"),
        source_member_key=scope.source_member_key,
        observation_selection_policy_id=digest(f"selection-policy-{operation_suffix}"),
        selection_mode=mode,
        anchor_lag_intervals=0,
        requested_count=requested_count,
        maximum_age_seconds=maximum_age_seconds,
        continuity_policy=ContinuityPolicy.STRICT_INTERVAL_GRID,
        frozen_at=T0,
    )


def test_projection_selects_exact_latest_and_trailing_with_full_replay(
    tmp_path: Path,
) -> None:
    policy = bar_policy(requires_status=False)
    scope = scope_for(policy)
    database = tmp_path / "selector.sqlite3"
    knowledge = T0 + timedelta(minutes=3, seconds=1)

    with PhysicalProjectionStoreV4(
        database,
        clock=FixedClock(knowledge + timedelta(seconds=5)),
    ) as store:
        store.append_scope(scope, idempotency_key="scope")
        revisions = tuple(
            append_bar(
                store,
                policy=policy,
                bar_start=T0 + timedelta(minutes=index),
                close=f"100.{index + 1}",
                operation_suffix=f"bar-{index}",
            )
            for index in range(3)
        )
        cutoff = append_cutoff(store, knowledge=knowledge, operation_suffix="three")

        bindings = {
            "exact": binding_for(
                mode=DependencySelectionMode.EXACT_EVENT,
                requested_count=1,
                operation_suffix="exact",
            ),
            "latest": binding_for(
                mode=DependencySelectionMode.LATEST_AVAILABLE_ASOF,
                requested_count=1,
                operation_suffix="latest",
            ),
            "trailing": binding_for(
                mode=DependencySelectionMode.TRAILING_COMPLETED_OBSERVATIONS,
                requested_count=3,
                operation_suffix="trailing",
            ),
        }
        for name, binding in bindings.items():
            store.append_protocol_binding(binding, idempotency_key=f"binding-{name}")

        results = {}
        for name, binding in bindings.items():
            results[name] = store.select_observations(
                physical_protocol_binding_id=(binding.physical_protocol_binding_id),
                evidence_cutoff_id=cutoff.evidence_cutoff_id,
                observation_cutoff_ts=knowledge,
                computed_at=knowledge + timedelta(seconds=1),
                idempotency_key=f"select-{name}",
            )

        exact_proof, exact_chunk = results["exact"]
        latest_proof, latest_chunk = results["latest"]
        trailing_proof, trailing_chunk = results["trailing"]
        assert exact_proof.status is latest_proof.status is SelectionStatus.SELECTED
        assert trailing_proof.status is SelectionStatus.SELECTED
        assert exact_chunk is not None and latest_chunk is not None
        assert trailing_chunk is not None
        assert exact_chunk.ordered_observation_revision_ids == (
            revisions[-1].observation_revision_id,
        )
        assert latest_chunk.ordered_observation_revision_ids == (
            revisions[-1].observation_revision_id,
        )
        assert trailing_chunk.ordered_observation_revision_ids == tuple(
            revision.observation_revision_id for revision in revisions
        )

        replayed = store.select_observations(
            physical_protocol_binding_id=(
                bindings["exact"].physical_protocol_binding_id
            ),
            evidence_cutoff_id=cutoff.evidence_cutoff_id,
            observation_cutoff_ts=knowledge,
            computed_at=knowledge + timedelta(seconds=1),
            idempotency_key="select-exact",
        )
        assert replayed == results["exact"]
        with pytest.raises(PhysicalProjectionV4IdempotencyError):
            store.select_observations(
                physical_protocol_binding_id=(
                    bindings["exact"].physical_protocol_binding_id
                ),
                evidence_cutoff_id=cutoff.evidence_cutoff_id,
                observation_cutoff_ts=knowledge,
                computed_at=knowledge + timedelta(seconds=2),
                idempotency_key="select-exact",
            )

        stale_binding = binding_for(
            mode=DependencySelectionMode.EXACT_EVENT,
            requested_count=1,
            operation_suffix="stale",
            maximum_age_seconds=0,
        )
        store.append_protocol_binding(
            stale_binding,
            idempotency_key="binding-stale",
        )
        stale_proof, stale_chunk = store.select_observations(
            physical_protocol_binding_id=(stale_binding.physical_protocol_binding_id),
            evidence_cutoff_id=cutoff.evidence_cutoff_id,
            observation_cutoff_ts=knowledge,
            computed_at=knowledge + timedelta(seconds=1),
            idempotency_key="select-stale",
        )
        assert stale_proof.status is SelectionStatus.ABSTAIN
        assert stale_proof.abstention_reason_codes == ("SELECTED_OBSERVATION_TOO_OLD",)
        assert stale_chunk is None

        plan = store._connection.execute(  # noqa: SLF001
            """
            EXPLAIN QUERY PLAN
            SELECT r.observation_revision_id
            FROM observation_revisions AS r
                 INDEXED BY observation_revision_select_complete_bar_v4
            WHERE r.physical_scope_manifest_id = ?
              AND r.source_member_key = ?
              AND r.observation_kind = 'BAR'
              AND r.completion_state = 'COMPLETE'
              AND r.timeframe_id = '1m'
              AND r.admission_receipt_sequence <= ?
              AND r.available_at_us <= ?
              AND r.bar_close_us <= ?
              AND NOT EXISTS (
                  SELECT 1 FROM observation_revisions AS successor
                  WHERE successor.parent_observation_revision_id =
                            r.observation_revision_id
                    AND successor.admission_receipt_sequence <= ?
                    AND successor.available_at_us <= ?
              )
            ORDER BY r.bar_close_us DESC, r.available_at_us DESC,
                     r.admission_receipt_sequence DESC,
                     r.observation_revision_id DESC
            LIMIT 3
            """,
            (
                bytes.fromhex(scope.physical_scope_manifest_id),
                bytes.fromhex(scope.source_member_key),
                cutoff.cutoff_global_sequence,
                int(knowledge.timestamp() * 1_000_000),
                int(knowledge.timestamp() * 1_000_000),
                cutoff.cutoff_global_sequence,
                int(knowledge.timestamp() * 1_000_000),
            ),
        ).fetchall()
        plan_text = " ".join(str(row) for row in plan)
        assert "observation_revision_select_complete_bar_v4" in plan_text
        assert "observation_revision_one_child_v4" in plan_text
        assert "TEMP B-TREE" not in plan_text

        missing_knowledge = T0 + timedelta(minutes=4, seconds=1)
        missing_cutoff = append_cutoff(
            store,
            knowledge=missing_knowledge,
            operation_suffix="missing",
        )
        abstain, chunk = store.select_observations(
            physical_protocol_binding_id=(
                bindings["exact"].physical_protocol_binding_id
            ),
            evidence_cutoff_id=missing_cutoff.evidence_cutoff_id,
            observation_cutoff_ts=missing_knowledge,
            computed_at=missing_knowledge + timedelta(seconds=1),
            idempotency_key="select-missing",
        )
        assert abstain.status is SelectionStatus.ABSTAIN
        assert abstain.abstention_reason_codes == ("EXACT_EVENT_MISSING_OR_AMBIGUOUS",)
        assert chunk is None

        report = store.verify()
        assert report.protocol_binding_count == 4
        assert report.selection_result_chunk_count == 3
        assert report.observation_selection_proof_count == 5

    with PhysicalProjectionStoreV4(
        database,
        clock=FixedClock(knowledge + timedelta(minutes=10)),
    ) as reopened:
        assert reopened.verify().observation_selection_proof_count == 5


def test_later_correction_does_not_change_historical_selection(
    tmp_path: Path,
) -> None:
    policy = bar_policy(requires_status=False)
    scope = scope_for(policy)
    database = tmp_path / "correction.sqlite3"
    first_knowledge = T0 + timedelta(minutes=1, milliseconds=750)

    with PhysicalProjectionStoreV4(
        database,
        clock=FixedClock(T0 + timedelta(minutes=3)),
    ) as store:
        store.append_scope(scope, idempotency_key="scope")
        original = append_bar(
            store,
            policy=policy,
            bar_start=T0,
            close="100.0",
            operation_suffix="original",
        )
        first_cutoff = append_cutoff(
            store,
            knowledge=first_knowledge,
            operation_suffix="first",
        )
        binding = binding_for(
            mode=DependencySelectionMode.LATEST_AVAILABLE_ASOF,
            requested_count=1,
            operation_suffix="correction",
        )
        store.append_protocol_binding(binding, idempotency_key="binding")
        first_proof, first_chunk = store.select_observations(
            physical_protocol_binding_id=binding.physical_protocol_binding_id,
            evidence_cutoff_id=first_cutoff.evidence_cutoff_id,
            observation_cutoff_ts=first_knowledge,
            computed_at=first_knowledge + timedelta(milliseconds=10),
            idempotency_key="select-first",
        )
        assert first_chunk is not None
        assert first_chunk.ordered_observation_revision_ids == (
            original.observation_revision_id,
        )

        corrected = append_bar(
            store,
            policy=policy,
            bar_start=T0,
            close="101.0",
            operation_suffix="corrected",
            parent_revision_id=original.observation_revision_id,
            correction_reason="PROVIDER_CORRECTION",
            # Availability precedes the first cutoff, but admission happens
            # after it; the receipt cutoff must keep the correction invisible.
            timing_offset=timedelta(milliseconds=50),
        )
        second_knowledge = T0 + timedelta(minutes=1, milliseconds=900)
        second_cutoff = append_cutoff(
            store,
            knowledge=second_knowledge,
            operation_suffix="second",
        )
        second_proof, second_chunk = store.select_observations(
            physical_protocol_binding_id=binding.physical_protocol_binding_id,
            evidence_cutoff_id=second_cutoff.evidence_cutoff_id,
            observation_cutoff_ts=second_knowledge,
            computed_at=second_knowledge + timedelta(milliseconds=10),
            idempotency_key="select-second",
        )
        assert second_chunk is not None
        assert second_chunk.ordered_observation_revision_ids == (
            corrected.observation_revision_id,
        )
        assert first_proof.observation_selection_proof_id != (
            second_proof.observation_selection_proof_id
        )
        store.verify()

        first_items = store._connection.execute(  # noqa: SLF001
            """
            SELECT observation_revision_id FROM selection_result_items
            WHERE selection_result_chunk_id = ? ORDER BY ordinal
            """,
            (bytes.fromhex(first_chunk.selection_result_chunk_id),),
        ).fetchall()
        assert first_items == [(bytes.fromhex(original.observation_revision_id),)]


class InjectedSelectionFailure(RuntimeError):
    pass


def test_selection_chunk_and_proof_roll_back_atomically(tmp_path: Path) -> None:
    policy = bar_policy(requires_status=False)
    scope = scope_for(policy)
    database = tmp_path / "selector-rollback.sqlite3"
    knowledge = T0 + timedelta(minutes=1, seconds=1)

    def fail_after_chunk(stage: str) -> None:
        if stage == "after_selection_result_chunk_insert":
            raise InjectedSelectionFailure(stage)

    with PhysicalProjectionStoreV4(
        database,
        clock=FixedClock(knowledge + timedelta(seconds=2)),
        fault_injector=fail_after_chunk,
    ) as store:
        store.append_scope(scope, idempotency_key="scope")
        append_bar(
            store,
            policy=policy,
            bar_start=T0,
            close="100.0",
            operation_suffix="bar",
        )
        cutoff = append_cutoff(store, knowledge=knowledge, operation_suffix="one")
        binding = binding_for(
            mode=DependencySelectionMode.EXACT_EVENT,
            requested_count=1,
            operation_suffix="rollback",
        )
        store.append_protocol_binding(binding, idempotency_key="binding")
        with pytest.raises(InjectedSelectionFailure):
            store.select_observations(
                physical_protocol_binding_id=binding.physical_protocol_binding_id,
                evidence_cutoff_id=cutoff.evidence_cutoff_id,
                observation_cutoff_ts=knowledge,
                computed_at=knowledge + timedelta(seconds=1),
                idempotency_key="select",
            )
        report = store.verify()
        assert report.selection_result_chunk_count == 0
        assert report.observation_selection_proof_count == 0
        assert store._connection.execute(  # noqa: SLF001
            "SELECT count(*) FROM selection_result_items"
        ).fetchone() == (0,)

    with PhysicalProjectionStoreV4(
        database,
        clock=FixedClock(knowledge + timedelta(seconds=3)),
    ) as reopened:
        proof, chunk = reopened.select_observations(
            physical_protocol_binding_id=binding.physical_protocol_binding_id,
            evidence_cutoff_id=cutoff.evidence_cutoff_id,
            observation_cutoff_ts=knowledge,
            computed_at=knowledge + timedelta(seconds=1),
            idempotency_key="select",
        )
        assert proof.status is SelectionStatus.SELECTED
        assert chunk is not None
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            reopened._connection.execute(  # noqa: SLF001
                "DELETE FROM selection_result_items"
            )
        reopened.verify()


def test_dual_cutoffs_and_strict_grid_abstain_fail_closed(tmp_path: Path) -> None:
    policy = bar_policy(requires_status=False)
    scope = scope_for(policy)

    availability_database = tmp_path / "availability-cutoff.sqlite3"
    early_knowledge = T0 + timedelta(minutes=1, milliseconds=500)
    late_knowledge = T0 + timedelta(minutes=1, milliseconds=600)
    with PhysicalProjectionStoreV4(
        availability_database,
        clock=FixedClock(T0 + timedelta(minutes=2)),
    ) as store:
        store.append_scope(scope, idempotency_key="scope")
        revision = append_bar(
            store,
            policy=policy,
            bar_start=T0,
            close="100.0",
            operation_suffix="bar",
        )
        assert revision.available_at > early_knowledge
        early_cutoff = append_cutoff(
            store,
            knowledge=early_knowledge,
            operation_suffix="early",
        )
        binding = binding_for(
            mode=DependencySelectionMode.EXACT_EVENT,
            requested_count=1,
            operation_suffix="availability",
        )
        store.append_protocol_binding(binding, idempotency_key="binding")
        early_proof, early_chunk = store.select_observations(
            physical_protocol_binding_id=binding.physical_protocol_binding_id,
            evidence_cutoff_id=early_cutoff.evidence_cutoff_id,
            observation_cutoff_ts=early_knowledge,
            computed_at=early_knowledge + timedelta(milliseconds=10),
            idempotency_key="select-early",
        )
        assert early_proof.status is SelectionStatus.ABSTAIN
        assert early_proof.abstention_reason_codes == (
            "EXACT_EVENT_MISSING_OR_AMBIGUOUS",
        )
        assert early_chunk is None

        late_cutoff = append_cutoff(
            store,
            knowledge=late_knowledge,
            operation_suffix="late",
        )
        late_proof, late_chunk = store.select_observations(
            physical_protocol_binding_id=binding.physical_protocol_binding_id,
            evidence_cutoff_id=late_cutoff.evidence_cutoff_id,
            observation_cutoff_ts=late_knowledge,
            computed_at=late_knowledge + timedelta(milliseconds=10),
            idempotency_key="select-late",
        )
        assert late_proof.status is SelectionStatus.SELECTED
        assert late_chunk is not None
        assert late_chunk.ordered_observation_revision_ids == (
            revision.observation_revision_id,
        )
        store.verify()

    gap_database = tmp_path / "strict-grid-gap.sqlite3"
    gap_knowledge = T0 + timedelta(minutes=3, seconds=1)
    with PhysicalProjectionStoreV4(
        gap_database,
        clock=FixedClock(gap_knowledge + timedelta(seconds=1)),
    ) as store:
        store.append_scope(scope, idempotency_key="scope")
        append_bar(
            store,
            policy=policy,
            bar_start=T0,
            close="100.0",
            operation_suffix="first",
        )
        append_bar(
            store,
            policy=policy,
            bar_start=T0 + timedelta(minutes=2),
            close="100.2",
            operation_suffix="third",
        )
        gap_cutoff = append_cutoff(
            store,
            knowledge=gap_knowledge,
            operation_suffix="gap",
        )
        trailing = binding_for(
            mode=DependencySelectionMode.TRAILING_COMPLETED_OBSERVATIONS,
            requested_count=2,
            operation_suffix="gap",
        )
        store.append_protocol_binding(trailing, idempotency_key="binding")
        gap_proof, gap_chunk = store.select_observations(
            physical_protocol_binding_id=trailing.physical_protocol_binding_id,
            evidence_cutoff_id=gap_cutoff.evidence_cutoff_id,
            observation_cutoff_ts=gap_knowledge,
            computed_at=gap_knowledge + timedelta(milliseconds=10),
            idempotency_key="select-gap",
        )
        assert gap_proof.status is SelectionStatus.ABSTAIN
        assert gap_proof.abstention_reason_codes == ("TRAILING_WINDOW_GAPPED",)
        assert gap_chunk is None
        store.verify()

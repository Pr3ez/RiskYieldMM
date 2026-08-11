from __future__ import annotations

import hashlib
import multiprocessing
import os
import sqlite3
import stat
import threading
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from riskyieldmm.trading import (
    GENESIS_HASH,
    CandidateFeatureMaterializationV3,
    CanonicalizationError,
    Ed25519CheckpointSigner,
    EligibilityVerdict,
    EntryScenario,
    EventDependenceAssignmentV3,
    HoldoutGrantConflictError,
    LedgerAlreadyRegisteredError,
    LedgerChannel,
    LedgerConfigurationError,
    LedgerConflictError,
    LedgerIdempotencyConflictError,
    LedgerNotFoundError,
    LedgerReceipt,
    LedgerRecordKind,
    LedgerSecurityError,
    LedgerVerificationError,
    LedgerWriterLockError,
    TradeSide,
    V3GovernanceLedger,
    derive_ed25519_key_id,
    ed25519_public_key_is_valid,
    encode_float64_be_hex_null_v1,
    sqlite_wal_runtime_is_safe,
)
from riskyieldmm.trading.calendar_actions import (
    ActionAbstentionReason,
    ActionProtocolV3,
    ActionResolutionStatus,
    CalendarScheduleSnapshotV3,
    CalendarSourceArtifactV3,
    InstrumentMappingV3,
    resolve_action_v3,
)
from riskyieldmm.trading.evidence import MissingInputPolicy
from tests.test_trading_event_contracts_v3 import barrier_activation, filled_outcome
from tests.test_trading_manifests_v3 import (
    governed_protocol_graph,
    governed_source_graph,
    missing_policy_graph,
    protocol_manifest,
    protocol_record_graph,
    source_manifest,
    split_manifest,
    trial_result_manifest,
    trial_spec_manifest,
)

LEDGER_NOW = datetime(2026, 7, 14, 12, 0, 0, tzinfo=timezone.utc)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def ledger_path(tmp_path: Path, name: str = "ledger.sqlite3") -> Path:
    tmp_path.chmod(0o700)
    return tmp_path / name


def open_ledger(
    path: Path,
    *,
    fault_injector: object | None = None,
) -> V3GovernanceLedger:
    return V3GovernanceLedger(
        path,
        clock=lambda: LEDGER_NOW,
        fault_injector=fault_injector,  # type: ignore[arg-type]
    )


def standalone_record(name: str):
    """Return an independently appendable record for storage-only tests."""

    _, member, _, _ = governed_source_graph(content_suffix=name)
    return replace(
        member,
        source_id=f"test.atomic.{digest(name)[:16]}",
        asset_id=None,
        venue_id=None,
        contract_id=None,
        timeframe_id=None,
    )


def governed_event_graph():
    source, member, bundle, evidence_registry = governed_source_graph()
    protocol, slot, definition, schema, evidence_registry = governed_protocol_graph(
        source,
        member,
        bundle,
        evidence_registry,
    )
    information, candidate, materialization, eligibility, decision, resolution = (
        protocol_record_graph(protocol, source, evidence_registry)
    )
    artifact = next(
        item
        for item in evidence_registry.values()
        if isinstance(item, CalendarSourceArtifactV3)
    )
    calendar = next(
        item
        for item in evidence_registry.values()
        if isinstance(item, CalendarScheduleSnapshotV3)
    )
    action_protocol = next(
        item
        for item in evidence_registry.values()
        if isinstance(item, ActionProtocolV3)
    )
    instrument_mapping = next(
        item
        for item in evidence_registry.values()
        if isinstance(item, InstrumentMappingV3)
    )
    return {
        "source": source,
        "protocol": protocol,
        "member": member,
        "bundle": bundle,
        "slot": slot,
        "definition": definition,
        "schema": schema,
        "information": information,
        "artifact": artifact,
        "calendar": calendar,
        "action_protocol": action_protocol,
        "instrument_mapping": instrument_mapping,
        "resolution": resolution,
        "candidate": candidate,
        "materialization": materialization,
        "eligibility": eligibility,
        "decision": decision,
        "records": (
            artifact,
            calendar,
            action_protocol,
            instrument_mapping,
            member,
            bundle,
            slot,
            definition,
            schema,
            source,
            protocol,
            information,
            resolution,
            candidate,
            materialization,
            eligibility,
            decision,
        ),
    }


def records_through(graph: dict[str, object], name: str) -> tuple[object, ...]:
    records = graph["records"]
    assert isinstance(records, tuple)
    terminal = {
        "protocol": 11,
        "information": 12,
        "resolution": 13,
        "candidate": 14,
        "materialization": 15,
        "eligibility": 16,
        "decision": 17,
    }[name]
    return records[:terminal]


def append_event_graph(
    ledger: V3GovernanceLedger,
):
    graph = governed_event_graph()
    receipts = tuple(
        ledger.append(record, idempotency_key=f"graph-{index}")
        for index, record in enumerate(graph["records"], start=1)
    )
    return (
        graph["source"],
        graph["protocol"],
        graph["information"],
        graph["eligibility"],
        graph["decision"],
        receipts,
    )


def final_holdout_graph():
    _, member, anchor_bundle, evidence_registry = governed_source_graph(
        content_suffix="live-holdout-anchor"
    )
    anchor = source_manifest(
        source_contract_id=anchor_bundle.source_contract_id,
        source_schema_id=anchor_bundle.source_schema_id,
        source_content_root=anchor_bundle.source_bundle_id,
        first_seen_policy_id=anchor_bundle.first_seen_policy_id,
        revision_policy_id=anchor_bundle.revision_policy_id,
        calendar_manifest_id=anchor_bundle.calendar_manifest_id,
        universe_manifest_id=anchor_bundle.universe_manifest_id,
        vintage_class=anchor_bundle.vintage_class,
        knowledge_cutoff_ts="2026-07-14T09:01:03Z",
    )
    protocol, slot, definition, schema, evidence_registry = governed_protocol_graph(
        anchor,
        member,
        anchor_bundle,
        evidence_registry,
    )
    forward_member = replace(
        member,
        semantic_content_root=digest("forward-first-seen-semantic-content"),
        artifact_hash=digest("forward-first-seen-artifact"),
        row_count=3,
        event_end_ts="2026-07-14T10:00:00Z",
        knowledge_cutoff_ts="2026-07-14T10:00:30Z",
        parent_source_member_id=member.source_member_id,
    )
    forward_bundle = replace(
        anchor_bundle,
        knowledge_cutoff_ts="2026-07-14T10:00:30Z",
        source_member_ids=(forward_member.source_member_id,),
        parent_source_bundle_id=anchor_bundle.source_bundle_id,
    )
    forward = source_manifest(
        parent_source_manifest_id=anchor.manifest_id,
        source_contract_id=forward_bundle.source_contract_id,
        source_schema_id=forward_bundle.source_schema_id,
        source_content_root=forward_bundle.source_bundle_id,
        first_seen_policy_id=forward_bundle.first_seen_policy_id,
        revision_policy_id=forward_bundle.revision_policy_id,
        calendar_manifest_id=forward_bundle.calendar_manifest_id,
        universe_manifest_id=forward_bundle.universe_manifest_id,
        vintage_class=forward_bundle.vintage_class,
        knowledge_cutoff_ts="2026-07-14T10:00:30Z",
    )
    final_split = split_manifest(
        protocol,
        forward,
        cohort_class="FINAL_HOLDOUT",
        event_ledger_root=GENESIS_HASH,
        label_ledger_root=GENESIS_HASH,
        as_of_ts="2026-07-14T10:01:00Z",
    )
    artifact = next(
        item
        for item in evidence_registry.values()
        if isinstance(item, CalendarSourceArtifactV3)
    )
    calendar = next(
        item
        for item in evidence_registry.values()
        if isinstance(item, CalendarScheduleSnapshotV3)
    )
    action_protocol = next(
        item
        for item in evidence_registry.values()
        if isinstance(item, ActionProtocolV3)
    )
    instrument_mapping = next(
        item
        for item in evidence_registry.values()
        if isinstance(item, InstrumentMappingV3)
    )
    records = (
        artifact,
        calendar,
        action_protocol,
        instrument_mapping,
        member,
        anchor_bundle,
        anchor,
        slot,
        definition,
        schema,
        protocol,
        forward_member,
        forward_bundle,
        forward,
        final_split,
    )
    return anchor, protocol, forward, final_split, records


def test_final_holdout_rejects_evidence_registered_before_protocol(
    tmp_path: Path,
) -> None:
    _, _, _, final_split, records = final_holdout_graph()
    reordered = (
        *records[:7],
        *records[11:14],
        *records[7:11],
    )
    with open_ledger(ledger_path(tmp_path)) as ledger:
        for index, record in enumerate(reordered, start=1):
            ledger.append(record, idempotency_key=f"precommit-bypass-{index}")
        with pytest.raises(LedgerConflictError, match="registered after"):
            ledger.append(final_split, idempotency_key="precommit-bypass-split")
        assert ledger.verify().receipt_count == 14


def grant_arguments(protocol_id: str, split_id: str, checkpoint_id: str):
    return {
        "protocol_manifest_id": protocol_id,
        "split_manifest_id": split_id,
        "checkpoint_id": checkpoint_id,
        "approval_hash": digest("holdout-approval"),
        "evidence_gate_hash": digest("evidence-gate"),
        "frozen_artifact_hash": digest("frozen-artifact"),
        "external_anchor_hash": digest("external-anchor"),
    }


def append_holdout_grant(ledger: V3GovernanceLedger):
    nominal, protocol, forward, final_split, records = final_holdout_graph()
    del nominal, forward
    for index, record in enumerate(records, start=1):
        ledger.append(record, idempotency_key=f"sealed-holdout-graph-{index}")
    signer = Ed25519CheckpointSigner.generate()
    checkpoint = ledger.create_checkpoint(
        signer,
        idempotency_key="sealed-holdout-checkpoint",
    )
    grant = ledger.grant_final_holdout_evaluation(
        **grant_arguments(
            protocol.manifest_id,
            final_split.manifest_id,
            checkpoint.checkpoint_id,
        ),
        idempotency_key="sealed-holdout-grant",
    )
    return protocol, final_split, signer, checkpoint, grant


_UPDATE_TRIGGER_SQL = {
    "objects": """
        CREATE TRIGGER objects_no_update BEFORE UPDATE ON objects
        BEGIN SELECT RAISE(ABORT, 'objects are immutable'); END
    """,
    "receipts": """
        CREATE TRIGGER receipts_no_update BEFORE UPDATE ON receipts
        BEGIN SELECT RAISE(ABORT, 'receipts are immutable'); END
    """,
    "checkpoints": """
        CREATE TRIGGER checkpoints_no_update BEFORE UPDATE ON checkpoints
        BEGIN SELECT RAISE(ABORT, 'checkpoints are immutable'); END
    """,
    "holdout_grants": """
        CREATE TRIGGER grants_no_update BEFORE UPDATE ON holdout_grants
        BEGIN SELECT RAISE(ABORT, 'holdout grants are immutable'); END
    """,
}

_UPDATE_TRIGGER_NAME = {
    "objects": "objects_no_update",
    "receipts": "receipts_no_update",
    "checkpoints": "checkpoints_no_update",
    "holdout_grants": "grants_no_update",
}

_DELETE_TRIGGER_SQL = {
    "objects": """
        CREATE TRIGGER objects_no_delete BEFORE DELETE ON objects
        BEGIN SELECT RAISE(ABORT, 'objects are immutable'); END
    """,
    "checkpoints": """
        CREATE TRIGGER checkpoints_no_delete BEFORE DELETE ON checkpoints
        BEGIN SELECT RAISE(ABORT, 'checkpoints are immutable'); END
    """,
    "holdout_grants": """
        CREATE TRIGGER grants_no_delete BEFORE DELETE ON holdout_grants
        BEGIN SELECT RAISE(ABORT, 'holdout grants are immutable'); END
    """,
}

_DELETE_TRIGGER_NAME = {
    "objects": "objects_no_delete",
    "checkpoints": "checkpoints_no_delete",
    "holdout_grants": "grants_no_delete",
}


def _crash_during_append(path_text: str) -> None:
    """Child-process target used to exercise real rollback-journal recovery."""

    def terminate(stage: str) -> None:
        if stage == "after_receipt_insert":
            os._exit(77)

    with V3GovernanceLedger(
        path_text,
        clock=lambda: LEDGER_NOW,
        fault_injector=terminate,
    ) as ledger:
        ledger.append(
            standalone_record("crashing-source"),
            idempotency_key="crashing-source",
        )


def test_private_storage_delete_extra_default_and_wal_runtime_guard(
    tmp_path: Path,
) -> None:
    path = ledger_path(tmp_path)
    with open_ledger(path) as ledger:
        assert ledger.journal_mode == "DELETE"
        assert ledger._connection.execute("PRAGMA journal_mode").fetchone()[0] == (
            "delete"
        )
        assert ledger._connection.execute("PRAGMA synchronous").fetchone()[0] == 3
        assert stat.S_IMODE(tmp_path.stat().st_mode) == 0o700
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert stat.S_IMODE(Path(f"{path}.writer.lock").stat().st_mode) == 0o600

    assert not sqlite_wal_runtime_is_safe((3, 51, 1))
    assert sqlite_wal_runtime_is_safe((3, 51, 3))
    assert not sqlite_wal_runtime_is_safe((3, 50, 6))
    assert sqlite_wal_runtime_is_safe((3, 50, 7))
    assert sqlite_wal_runtime_is_safe((3, 44, 6))

    unsafe_path = ledger_path(tmp_path, "unsafe-wal.sqlite3")
    with patch(
        "riskyieldmm.trading.ledger.sqlite_wal_runtime_is_safe",
        return_value=False,
    ):
        with pytest.raises(LedgerConfigurationError, match="WAL is not certified"):
            V3GovernanceLedger(unsafe_path, journal_mode="WAL")
    assert not unsafe_path.exists()


def test_append_graph_has_global_and_channel_chains_and_exact_receipt_replay(
    tmp_path: Path,
) -> None:
    with open_ledger(ledger_path(tmp_path)) as ledger:
        source, _, _, _, decision, receipts = append_event_graph(ledger)

        assert [receipt.global_sequence for receipt in receipts] == list(range(1, 18))
        assert [receipt.channel for receipt in receipts] == (
            [LedgerChannel.MANIFEST] * 11 + [LedgerChannel.EVENT] * 6
        )
        assert [receipt.channel_sequence for receipt in receipts] == (
            list(range(1, 12)) + list(range(1, 7))
        )
        for previous, current in zip(receipts[:-1], receipts[1:], strict=True):
            assert current.previous_global_receipt_hash == previous.receipt_hash
        assert receipts[0].previous_global_receipt_hash == GENESIS_HASH
        assert receipts[0].previous_channel_receipt_hash == GENESIS_HASH
        assert receipts[11].previous_channel_receipt_hash == GENESIS_HASH
        assert receipts[16].previous_channel_receipt_hash == receipts[15].receipt_hash

        for receipt in receipts:
            assert ledger.get_receipt(receipt.global_sequence) == receipt
            assert LedgerReceipt.from_mapping(receipt.as_dict()) == receipt
            assert (
                ledger.receipt_for_idempotency_key(receipt.idempotency_key) == receipt
            )

        assert (
            ledger.get_record(LedgerRecordKind.MANIFEST, source.manifest_id) == source
        )
        assert (
            ledger.get_record(
                LedgerRecordKind.DECISION_EVENT,
                decision.decision_event_id,
            )
            == decision
        )
        report = ledger.verify()
        assert report.object_count == 17
        assert report.receipt_count == 17
        assert report.head_transition_count == 17
        assert report.global_receipt_root == receipts[-1].receipt_hash


def test_complete_manifest_trial_graph_registers_in_dependency_order(
    tmp_path: Path,
) -> None:
    with open_ledger(ledger_path(tmp_path)) as ledger:
        source, member, bundle, evidence_registry = governed_source_graph()
        protocol, slot, definition, schema, evidence_registry = governed_protocol_graph(
            source,
            member,
            bundle,
            evidence_registry,
        )
        artifact = next(
            item
            for item in evidence_registry.values()
            if isinstance(item, CalendarSourceArtifactV3)
        )
        calendar = next(
            item
            for item in evidence_registry.values()
            if isinstance(item, CalendarScheduleSnapshotV3)
        )
        action_protocol = next(
            item
            for item in evidence_registry.values()
            if isinstance(item, ActionProtocolV3)
        )
        instrument_mapping = next(
            item
            for item in evidence_registry.values()
            if isinstance(item, InstrumentMappingV3)
        )
        split = split_manifest(
            protocol,
            source,
            event_ledger_root=GENESIS_HASH,
            label_ledger_root=GENESIS_HASH,
        )
        spec = trial_spec_manifest(protocol, split)
        result = trial_result_manifest(protocol, source, split, spec)
        for index, manifest in enumerate(
            (
                artifact,
                calendar,
                action_protocol,
                instrument_mapping,
                member,
                bundle,
                slot,
                definition,
                schema,
                source,
                protocol,
                split,
                spec,
                result,
            ),
            start=1,
        ):
            ledger.append(manifest, idempotency_key=f"manifest-{index}")

        report = ledger.verify()
        assert report.object_count == 14
        assert report.receipt_count == 14
        manifest_root = next(
            root
            for root in report.channel_roots
            if root.channel is LedgerChannel.MANIFEST
        )
        assert manifest_root.sequence == 14


def test_idempotency_object_and_semantic_conflicts_fail_closed(tmp_path: Path) -> None:
    with open_ledger(ledger_path(tmp_path)) as ledger:
        graph = governed_event_graph()
        source = graph["source"]
        protocol = graph["protocol"]
        for index, record in enumerate(
            (
                graph["artifact"],
                graph["calendar"],
                graph["action_protocol"],
                graph["instrument_mapping"],
                graph["member"],
                graph["bundle"],
                graph["slot"],
                graph["definition"],
                graph["schema"],
            ),
            start=1,
        ):
            ledger.append(record, idempotency_key=f"evidence-{index}")
        original = ledger.append(source, idempotency_key="source-once")
        assert ledger.append(source, idempotency_key="source-once") == original

        with pytest.raises(LedgerIdempotencyConflictError):
            ledger.append(protocol, idempotency_key="source-once")
        with pytest.raises(LedgerAlreadyRegisteredError):
            ledger.append(source, idempotency_key="source-again")

        ledger.append(protocol, idempotency_key="protocol-once")
        information = graph["information"]
        candidate = graph["candidate"]
        materialization = graph["materialization"]
        eligibility = graph["eligibility"]
        ledger.append(information, idempotency_key="information-once")
        ledger.append(graph["resolution"], idempotency_key="resolution-once")
        ledger.append(candidate, idempotency_key="candidate-once")
        ledger.append(materialization, idempotency_key="materialization-once")
        ledger.append(eligibility, idempotency_key="eligibility-once")
        competing = replace(
            eligibility,
            verdict=EligibilityVerdict.INELIGIBLE,
            reason_codes=("MINIMUM_EDGE_NOT_MET",),
        )
        assert competing.eligibility_key == eligibility.eligibility_key
        assert competing.eligibility_decision_id != eligibility.eligibility_decision_id
        with pytest.raises(LedgerConflictError, match="compare-and-swap"):
            ledger.append(competing, idempotency_key="eligibility-competing")

        assert ledger.verify().receipt_count == 16


def test_decision_event_semantic_head_rejects_second_decision_timestamp(
    tmp_path: Path,
) -> None:
    graph = governed_event_graph()
    with open_ledger(ledger_path(tmp_path)) as ledger:
        for index, record in enumerate(graph["records"], start=1):
            ledger.append(record, idempotency_key=f"decision-key-{index}")

        competing = replace(
            graph["decision"],
            decision_ts="2026-07-14T09:01:08.500000Z",
        )
        assert competing.decision_event_key == graph["decision"].decision_event_key
        assert competing.decision_event_id != graph["decision"].decision_event_id
        with pytest.raises(LedgerConflictError, match="compare-and-swap"):
            ledger.append(competing, idempotency_key="competing-decision-timestamp")

        assert ledger.verify().receipt_count == 17


def test_source_member_append_rejects_direct_lineage_regression(
    tmp_path: Path,
) -> None:
    parent = standalone_record("member-lineage-parent")
    regressed = replace(
        parent,
        semantic_content_root=digest("regressed-member-semantic-root"),
        artifact_hash=digest("regressed-member-artifact"),
        row_count=max(0, parent.row_count - 1),
        knowledge_cutoff_ts="2026-07-14T09:02:00Z",
        parent_source_member_id=parent.source_member_id,
    )
    with open_ledger(ledger_path(tmp_path)) as ledger:
        ledger.append(parent, idempotency_key="member-lineage-parent")
        with pytest.raises(CanonicalizationError, match="reduces row_count"):
            ledger.append(regressed, idempotency_key="member-lineage-regression")
        assert ledger.verify().receipt_count == 1


def test_source_member_append_accepts_empty_to_first_row_transition(
    tmp_path: Path,
) -> None:
    _, template_member, template_bundle, _ = governed_source_graph(
        content_suffix="empty-member-template"
    )
    parent = replace(
        template_member,
        semantic_content_root=digest("empty-member-semantic-root"),
        artifact_hash=digest("empty-member-artifact"),
        row_count=0,
        event_start_ts=None,
        event_end_ts=None,
        knowledge_cutoff_ts="2026-07-14T08:50:00Z",
    )
    parent_bundle = replace(
        template_bundle,
        knowledge_cutoff_ts="2026-07-14T08:50:00Z",
        source_member_ids=(parent.source_member_id,),
    )
    child = replace(
        parent,
        semantic_content_root=digest("first-row-semantic-root"),
        artifact_hash=digest("first-row-artifact"),
        row_count=1,
        event_start_ts="2026-07-14T08:51:00Z",
        event_end_ts="2026-07-14T08:51:00Z",
        knowledge_cutoff_ts="2026-07-14T08:52:00Z",
        parent_source_member_id=parent.source_member_id,
    )

    with open_ledger(ledger_path(tmp_path)) as ledger:
        ledger.append(parent, idempotency_key="empty-member-parent")
        ledger.append(parent_bundle, idempotency_key="empty-member-parent-bundle")
        ledger.append(child, idempotency_key="first-row-child")
        assert ledger.verify().receipt_count == 3


def test_member_bundle_cadence_rejects_head_poisoning_and_recovers(
    tmp_path: Path,
) -> None:
    _, root_member, initial_bundle, _ = governed_source_graph(
        content_suffix="bundle-cadence-root"
    )
    root_bundle = replace(
        initial_bundle,
        knowledge_cutoff_ts="2026-07-14T09:05:00Z",
    )
    invalid_child = replace(
        root_member,
        knowledge_cutoff_ts="2026-07-14T09:02:00Z",
        parent_source_member_id=root_member.source_member_id,
    )
    child = replace(
        root_member,
        semantic_content_root=digest("bundle-cadence-child-semantic"),
        artifact_hash=digest("bundle-cadence-child-artifact"),
        row_count=3,
        event_end_ts="2026-07-14T09:05:00Z",
        knowledge_cutoff_ts="2026-07-14T09:06:00Z",
        parent_source_member_id=root_member.source_member_id,
    )
    child_bundle = replace(
        root_bundle,
        knowledge_cutoff_ts="2026-07-14T09:06:00Z",
        source_member_ids=(child.source_member_id,),
        parent_source_bundle_id=root_bundle.source_bundle_id,
    )
    grandchild = replace(
        child,
        knowledge_cutoff_ts="2026-07-14T09:07:00Z",
        parent_source_member_id=child.source_member_id,
    )
    grandchild_bundle = replace(
        child_bundle,
        knowledge_cutoff_ts="2026-07-14T09:07:00Z",
        source_member_ids=(grandchild.source_member_id,),
        parent_source_bundle_id=child_bundle.source_bundle_id,
    )

    with open_ledger(ledger_path(tmp_path)) as ledger:
        ledger.append(root_member, idempotency_key="cadence-root-member")
        ledger.append(root_bundle, idempotency_key="cadence-root-bundle")
        with pytest.raises(LedgerConflictError, match="parent-bundle cutoff"):
            ledger.append(invalid_child, idempotency_key="cadence-invalid-child")
        with pytest.raises(LedgerNotFoundError):
            ledger.get_record(
                LedgerRecordKind.SOURCE_BUNDLE_MEMBER,
                invalid_child.source_member_id,
            )

        ledger.append(child, idempotency_key="cadence-child-member")
        with pytest.raises(LedgerConflictError, match="parent in an active"):
            ledger.append(grandchild, idempotency_key="cadence-early-grandchild")
        ledger.append(child_bundle, idempotency_key="cadence-child-bundle")
        ledger.append(grandchild, idempotency_key="cadence-grandchild-member")
        ledger.append(
            grandchild_bundle,
            idempotency_key="cadence-grandchild-bundle",
        )
        assert ledger.verify().receipt_count == 6


def test_staged_new_member_key_can_be_corrected_before_bundle_selection(
    tmp_path: Path,
) -> None:
    _, root_member, base_bundle, _ = governed_source_graph(
        content_suffix="new-key-staging-root"
    )
    root_bundle = replace(
        base_bundle,
        knowledge_cutoff_ts="2026-07-14T09:05:00Z",
    )
    premature = replace(
        root_member,
        source_id="bybit.linear.ETHUSDT.1m",
        asset_id="ETH",
        contract_id="ETHUSDT.LINEAR.PERP",
        source_schema_id=digest("eth-1m-member-schema"),
        semantic_content_root=digest("premature-eth-semantic"),
        artifact_hash=digest("premature-eth-artifact"),
        knowledge_cutoff_ts="2026-07-14T09:02:00Z",
    )
    corrected = replace(
        premature,
        semantic_content_root=digest("corrected-eth-semantic"),
        artifact_hash=digest("corrected-eth-artifact"),
        knowledge_cutoff_ts="2026-07-14T09:06:00Z",
    )
    selected_bundle = replace(
        root_bundle,
        knowledge_cutoff_ts="2026-07-14T09:06:00Z",
        source_member_ids=(root_member.source_member_id, corrected.source_member_id),
        parent_source_bundle_id=root_bundle.source_bundle_id,
    )

    with open_ledger(ledger_path(tmp_path)) as ledger:
        ledger.append(root_member, idempotency_key="new-key-root-member")
        ledger.append(root_bundle, idempotency_key="new-key-root-bundle")
        ledger.append(premature, idempotency_key="new-key-premature-stage")
        ledger.append(corrected, idempotency_key="new-key-corrected-stage")
        ledger.append(selected_bundle, idempotency_key="new-key-selected-bundle")
        assert ledger.verify().receipt_count == 5


def test_candidate_cannot_substitute_forward_execution_for_scheduled_resolution(
    tmp_path: Path,
) -> None:
    graph = governed_event_graph()
    forward_candidate = replace(
        graph["candidate"],
        entry_scenario=EntryScenario.FORWARD_MARKET_ORDER,
    )
    with open_ledger(ledger_path(tmp_path)) as ledger:
        for index, record in enumerate(records_through(graph, "resolution"), start=1):
            ledger.append(record, idempotency_key=f"forward-clock-{index}")
        with pytest.raises(
            CanonicalizationError,
            match="entry_scenario differs from its action resolution",
        ):
            ledger.append(
                forward_candidate,
                idempotency_key="backdated-forward-candidate",
            )
        assert ledger.verify().receipt_count == 13


def test_calendar_and_mapping_successor_clocks_cannot_move_backwards(
    tmp_path: Path,
) -> None:
    graph = governed_event_graph()
    calendar_parent = graph["calendar"]
    mapping_parent = graph["instrument_mapping"]
    backward_calendar = replace(
        calendar_parent,
        known_at=calendar_parent.known_at - timedelta(seconds=1),
        parent_calendar_snapshot_id=calendar_parent.calendar_snapshot_id,
    )
    backward_frozen_calendar = replace(
        calendar_parent,
        frozen_at=calendar_parent.frozen_at - timedelta(seconds=1),
        parent_calendar_snapshot_id=calendar_parent.calendar_snapshot_id,
    )
    backward_mapping = replace(
        mapping_parent,
        known_at=mapping_parent.known_at - timedelta(seconds=1),
        parent_instrument_mapping_id=mapping_parent.instrument_mapping_id,
    )

    with open_ledger(ledger_path(tmp_path)) as ledger:
        for index, record in enumerate(records_through(graph, "information"), start=1):
            ledger.append(record, idempotency_key=f"successor-clock-{index}")
        with pytest.raises(LedgerConflictError, match="must not move backwards"):
            ledger.append(backward_calendar, idempotency_key="backward-calendar")
        with pytest.raises(LedgerConflictError, match="must not move backwards"):
            ledger.append(
                backward_frozen_calendar,
                idempotency_key="backward-frozen-calendar",
            )
        with pytest.raises(LedgerConflictError, match="must not move backwards"):
            ledger.append(backward_mapping, idempotency_key="backward-mapping")


def test_equal_clock_applicable_calendar_successor_makes_parent_stale(
    tmp_path: Path,
) -> None:
    graph = governed_event_graph()
    parent = graph["calendar"]
    successor = replace(
        parent,
        parent_calendar_snapshot_id=parent.calendar_snapshot_id,
    )

    with open_ledger(ledger_path(tmp_path)) as ledger:
        for index, record in enumerate(records_through(graph, "information"), start=1):
            ledger.append(record, idempotency_key=f"calendar-stale-{index}")
        ledger.append(successor, idempotency_key="calendar-stale-successor")
        with pytest.raises(LedgerConflictError, match="latest applicable calendar"):
            ledger.append(graph["resolution"], idempotency_key="calendar-stale-action")


def test_calendar_cutover_after_cutoff_before_submission_makes_parent_stale(
    tmp_path: Path,
) -> None:
    graph = governed_event_graph()
    parent = graph["calendar"]
    successor_interval = replace(
        parent.intervals[0],
        open_ts="2026-07-14T09:02:00Z",
        source_schedule_key="post-cutoff-cutover",
    )
    successor = replace(
        parent,
        coverage_start_ts="2026-07-14T09:01:05Z",
        intervals=(successor_interval,),
        parent_calendar_snapshot_id=parent.calendar_snapshot_id,
    )

    with open_ledger(ledger_path(tmp_path)) as ledger:
        for index, record in enumerate(records_through(graph, "information"), start=1):
            ledger.append(record, idempotency_key=f"calendar-cutover-{index}")
        ledger.append(successor, idempotency_key="calendar-cutover-successor")
        with pytest.raises(LedgerConflictError, match="latest applicable calendar"):
            ledger.append(
                graph["resolution"], idempotency_key="calendar-cutover-action"
            )


def test_future_calendar_successor_does_not_stale_applicable_parent(
    tmp_path: Path,
) -> None:
    graph = governed_event_graph()
    parent_artifact = graph["artifact"]
    parent = graph["calendar"]
    future_artifact = replace(
        parent_artifact,
        source_document_id="bybit-linear-test-schedule-2026-07-15",
        content_hash=digest("future-calendar-source-bytes"),
        effective_start_ts="2026-07-15T00:00:00Z",
        effective_end_ts_exclusive="2026-07-16T00:00:00Z",
    )
    future_interval = replace(
        parent.intervals[0],
        session_label="BYBIT-2026-07-15",
        trade_date="2026-07-15",
        open_ts="2026-07-15T08:00:00Z",
        close_ts_exclusive="2026-07-15T12:00:00Z",
        source_schedule_key="bybit-linear-future",
    )
    successor = replace(
        parent,
        calendar_source_artifact_id=future_artifact.calendar_source_artifact_id,
        calendar_source_artifact_record_hash=future_artifact.record_hash,
        coverage_start_ts="2026-07-15T08:00:00Z",
        coverage_end_ts_exclusive="2026-07-15T12:00:00Z",
        intervals=(future_interval,),
        parent_calendar_snapshot_id=parent.calendar_snapshot_id,
    )

    with open_ledger(ledger_path(tmp_path)) as ledger:
        for index, record in enumerate(records_through(graph, "information"), start=1):
            ledger.append(record, idempotency_key=f"future-calendar-{index}")
        ledger.append(future_artifact, idempotency_key="future-calendar-artifact")
        ledger.append(successor, idempotency_key="future-calendar-successor")
        ledger.append(graph["resolution"], idempotency_key="future-calendar-action")
        assert ledger.verify().receipt_count == 15


def test_newer_blocking_mapping_cannot_fall_back_to_supported_parent(
    tmp_path: Path,
) -> None:
    graph = governed_event_graph()
    parent = graph["instrument_mapping"]
    blocked = replace(
        parent,
        execution_supported=False,
        blocker_codes=("EXECUTION_MAPPING_WITHDRAWN",),
        parent_instrument_mapping_id=parent.instrument_mapping_id,
    )

    with open_ledger(ledger_path(tmp_path)) as ledger:
        for index, record in enumerate(records_through(graph, "information"), start=1):
            ledger.append(record, idempotency_key=f"mapping-stale-{index}")
        ledger.append(blocked, idempotency_key="mapping-stale-successor")
        with pytest.raises(
            LedgerConflictError,
            match="latest applicable instrument mapping",
        ):
            ledger.append(graph["resolution"], idempotency_key="mapping-stale-action")


def test_mapping_not_known_diagnostic_cannot_cite_future_evidence_in_ledger(
    tmp_path: Path,
) -> None:
    graph = governed_event_graph()
    future_mapping = replace(
        graph["instrument_mapping"],
        known_at="2026-07-14T09:01:04Z",
    )
    diagnostic = resolve_action_v3(
        information_set=graph["information"],
        calendar_artifact=graph["artifact"],
        calendar=graph["calendar"],
        protocol=graph["action_protocol"],
        mapping=future_mapping,
        primary_signal_id=graph["resolution"].primary_signal_id,
        primary_signal_version=graph["resolution"].primary_signal_version,
        primary_signal_policy_id=graph["resolution"].primary_signal_policy_id,
        signal_ts=graph["resolution"].signal_ts,
        side=graph["resolution"].side,
        signal_available_ts=graph["resolution"].signal_available_ts,
        resolved_at=graph["resolution"].resolved_at,
    )
    assert diagnostic.status is ActionResolutionStatus.ABSTAINED
    assert diagnostic.abstention_reason is ActionAbstentionReason.MAPPING_NOT_KNOWN

    records = list(records_through(graph, "information"))
    records[3] = future_mapping
    with open_ledger(ledger_path(tmp_path)) as ledger:
        for index, record in enumerate(records, start=1):
            ledger.append(record, idempotency_key=f"mapping-not-known-{index}")
        with pytest.raises(
            LedgerConflictError,
            match="no instrument mapping was known by the information cutoff",
        ):
            ledger.append(diagnostic, idempotency_key="mapping-not-known-action")
        assert (
            ledger.active_head("ACTION_RESOLUTION", diagnostic.action_request_key)
            is None
        )
        assert ledger.verify().receipt_count == 12


def test_future_mapping_cannot_poison_action_key_with_false_abstention(
    tmp_path: Path,
) -> None:
    graph = governed_event_graph()
    parent = graph["instrument_mapping"]
    future_mapping = replace(
        parent,
        effective_start_ts="2026-07-14T10:00:00Z",
        parent_instrument_mapping_id=parent.instrument_mapping_id,
    )
    wrong = resolve_action_v3(
        information_set=graph["information"],
        calendar_artifact=graph["artifact"],
        calendar=graph["calendar"],
        protocol=graph["action_protocol"],
        mapping=future_mapping,
        primary_signal_id=graph["resolution"].primary_signal_id,
        primary_signal_version=graph["resolution"].primary_signal_version,
        primary_signal_policy_id=graph["resolution"].primary_signal_policy_id,
        signal_ts=graph["resolution"].signal_ts,
        side=graph["resolution"].side,
        signal_available_ts=graph["resolution"].signal_available_ts,
        resolved_at=graph["resolution"].resolved_at,
    )
    assert wrong.status is ActionResolutionStatus.ABSTAINED
    assert wrong.abstention_reason is ActionAbstentionReason.MAPPING_WINDOW_MISSING
    assert wrong.action_request_key == graph["resolution"].action_request_key

    with open_ledger(ledger_path(tmp_path)) as ledger:
        for index, record in enumerate(records_through(graph, "information"), start=1):
            ledger.append(record, idempotency_key=f"mapping-poison-{index}")
        ledger.append(future_mapping, idempotency_key="mapping-poison-future")
        with pytest.raises(
            LedgerConflictError,
            match="latest applicable instrument mapping",
        ):
            ledger.append(wrong, idempotency_key="mapping-poison-abstention")
        ledger.append(graph["resolution"], idempotency_key="mapping-poison-correct")
        assert ledger.verify().receipt_count == 14


def test_alternate_action_protocol_cannot_poison_frozen_action_key(
    tmp_path: Path,
) -> None:
    graph = governed_event_graph()
    alternate_protocol = replace(
        graph["action_protocol"],
        submission_delay_microseconds=4_000_000,
    )
    wrong = resolve_action_v3(
        information_set=graph["information"],
        calendar_artifact=graph["artifact"],
        calendar=graph["calendar"],
        protocol=alternate_protocol,
        mapping=graph["instrument_mapping"],
        primary_signal_id=graph["resolution"].primary_signal_id,
        primary_signal_version=graph["resolution"].primary_signal_version,
        primary_signal_policy_id=graph["resolution"].primary_signal_policy_id,
        signal_ts=graph["resolution"].signal_ts,
        side=graph["resolution"].side,
        signal_available_ts=graph["resolution"].signal_available_ts,
        resolved_at=graph["resolution"].resolved_at,
    )
    assert wrong.action_request_key == graph["resolution"].action_request_key

    with open_ledger(ledger_path(tmp_path)) as ledger:
        for index, record in enumerate(records_through(graph, "information"), start=1):
            ledger.append(record, idempotency_key=f"protocol-poison-{index}")
        ledger.append(alternate_protocol, idempotency_key="protocol-poison-alternate")
        with pytest.raises(LedgerConflictError, match="frozen action protocol"):
            ledger.append(wrong, idempotency_key="protocol-poison-action")
        ledger.append(graph["resolution"], idempotency_key="protocol-poison-correct")
        assert ledger.verify().receipt_count == 14


@pytest.mark.parametrize(
    "changes",
    (
        {
            "known_at": "2026-07-14T09:01:04Z",
        },
        {
            "effective_start_ts": "2026-07-14T10:00:00Z",
        },
    ),
)
def test_unavailable_mapping_successor_does_not_rewrite_historical_action(
    tmp_path: Path,
    changes: dict[str, str],
) -> None:
    graph = governed_event_graph()
    parent = graph["instrument_mapping"]
    successor = replace(
        parent,
        **changes,
        parent_instrument_mapping_id=parent.instrument_mapping_id,
    )

    with open_ledger(ledger_path(tmp_path)) as ledger:
        for index, record in enumerate(records_through(graph, "information"), start=1):
            ledger.append(record, idempotency_key=f"mapping-asof-{index}")
        ledger.append(successor, idempotency_key="mapping-asof-successor")
        ledger.append(graph["resolution"], idempotency_key="mapping-asof-action")
        assert ledger.verify().receipt_count == 14


def test_later_successors_do_not_invalidate_the_registered_action_prefix(
    tmp_path: Path,
) -> None:
    graph = governed_event_graph()
    calendar_parent = graph["calendar"]
    mapping_parent = graph["instrument_mapping"]
    later_calendar = replace(
        calendar_parent,
        parent_calendar_snapshot_id=calendar_parent.calendar_snapshot_id,
    )
    later_mapping = replace(
        mapping_parent,
        execution_supported=False,
        blocker_codes=("MAPPING_WITHDRAWN_AFTER_ACTION",),
        parent_instrument_mapping_id=mapping_parent.instrument_mapping_id,
    )

    with open_ledger(ledger_path(tmp_path)) as ledger:
        for index, record in enumerate(records_through(graph, "resolution"), start=1):
            ledger.append(record, idempotency_key=f"prefix-stability-{index}")
        ledger.append(later_calendar, idempotency_key="prefix-later-calendar")
        ledger.append(later_mapping, idempotency_key="prefix-later-mapping")
        assert ledger.verify().receipt_count == 15


def test_forward_source_receipt_guard_rejects_pre_protocol_registration(
    tmp_path: Path,
) -> None:
    _, protocol, forward, _, records = final_holdout_graph()
    reordered = (*records[:7], *records[11:14], *records[7:11])

    with open_ledger(ledger_path(tmp_path)) as ledger:
        for index, record in enumerate(reordered, start=1):
            ledger.append(record, idempotency_key=f"forward-receipt-{index}")
        with pytest.raises(LedgerConflictError, match="registered after"):
            ledger._validate_post_protocol_source_registration(
                protocol=protocol,
                effective_source=forward,
                registry=ledger._manifest_registry(),
                evidence_registry=ledger._evidence_registry(),
                before_sequence=None,
                context="forward/live",
            )
        assert ledger.verify().receipt_count == 14


def test_source_manifest_requires_registered_member_and_bundle(tmp_path: Path) -> None:
    graph = governed_event_graph()
    with open_ledger(ledger_path(tmp_path)) as ledger:
        with pytest.raises(
            CanonicalizationError,
            match="missing referenced SourceBundleV3 evidence",
        ):
            ledger.append(graph["source"], idempotency_key="source-before-evidence")

        ledger.append(graph["member"], idempotency_key="source-member")
        with pytest.raises(
            CanonicalizationError,
            match="missing referenced SourceBundleV3 evidence",
        ):
            ledger.append(graph["source"], idempotency_key="source-before-bundle")

        ledger.append(graph["bundle"], idempotency_key="source-bundle")
        receipt = ledger.append(graph["source"], idempotency_key="source-ready")
        assert receipt.record_kind == LedgerRecordKind.MANIFEST.value


def test_observation_revision_claim_is_globally_immutable(tmp_path: Path) -> None:
    graph = governed_event_graph()
    repeated_claim = replace(
        graph["information"],
        data_quality_flags=("repeated-claim-context",),
    )
    conflicting_dependency = replace(
        graph["information"].dependencies[0],
        value_digest=digest("conflicting-global-observation-value"),
    )
    conflicting_claim = replace(
        graph["information"],
        dependencies=(conflicting_dependency,),
        data_quality_flags=("conflicting-claim-context",),
    )

    with open_ledger(ledger_path(tmp_path)) as ledger:
        for index, record in enumerate(records_through(graph, "information"), start=1):
            ledger.append(record, idempotency_key=f"global-claim-{index}")
        ledger.append(repeated_claim, idempotency_key="global-claim-repeat")
        with pytest.raises(LedgerConflictError, match="conflicting value digests"):
            ledger.append(conflicting_claim, idempotency_key="global-claim-conflict")
        assert ledger.verify().receipt_count == 13


def test_protocol_requires_slot_definition_and_schema_registration(
    tmp_path: Path,
) -> None:
    graph = governed_event_graph()
    with open_ledger(ledger_path(tmp_path)) as ledger:
        for index, name in enumerate(
            (
                "artifact",
                "calendar",
                "action_protocol",
                "instrument_mapping",
                "member",
                "bundle",
                "source",
            ),
            start=1,
        ):
            ledger.append(graph[name], idempotency_key=f"protocol-base-{index}")

        with pytest.raises(CanonicalizationError, match="missing referenced feature"):
            ledger.append(graph["schema"], idempotency_key="schema-before-inputs")
        with pytest.raises(
            CanonicalizationError,
            match="missing referenced FeatureSchemaV3 evidence",
        ):
            ledger.append(graph["protocol"], idempotency_key="protocol-before-slot")

        ledger.append(graph["slot"], idempotency_key="protocol-slot")
        with pytest.raises(
            CanonicalizationError,
            match="missing referenced FeatureSchemaV3 evidence",
        ):
            ledger.append(
                graph["protocol"],
                idempotency_key="protocol-before-definition",
            )

        ledger.append(graph["definition"], idempotency_key="protocol-definition")
        with pytest.raises(
            CanonicalizationError,
            match="missing referenced FeatureSchemaV3 evidence",
        ):
            ledger.append(graph["protocol"], idempotency_key="protocol-before-schema")

        ledger.append(graph["schema"], idempotency_key="protocol-schema")
        receipt = ledger.append(graph["protocol"], idempotency_key="protocol-ready")
        assert receipt.record_kind == LedgerRecordKind.MANIFEST.value


def test_candidate_and_materialization_require_exact_registration_order(
    tmp_path: Path,
) -> None:
    graph = governed_event_graph()
    with open_ledger(ledger_path(tmp_path)) as ledger:
        for index, record in enumerate(records_through(graph, "protocol"), start=1):
            ledger.append(record, idempotency_key=f"candidate-base-{index}")

        with pytest.raises(LedgerNotFoundError, match="INFORMATION_SET"):
            ledger.append(graph["candidate"], idempotency_key="candidate-before-info")

        ledger.append(graph["information"], idempotency_key="candidate-info")
        with pytest.raises(LedgerNotFoundError, match="ACTION_RESOLUTION"):
            ledger.append(
                graph["candidate"],
                idempotency_key="candidate-before-resolution",
            )
        ledger.append(graph["resolution"], idempotency_key="candidate-resolution")
        with pytest.raises(LedgerNotFoundError, match="PRIMARY_SIGNAL_CANDIDATE"):
            ledger.append(
                graph["materialization"],
                idempotency_key="materialization-before-candidate",
            )

        ledger.append(graph["candidate"], idempotency_key="candidate-ready")
        receipt = ledger.append(
            graph["materialization"],
            idempotency_key="materialization-ready",
        )
        assert (
            receipt.record_kind
            == LedgerRecordKind.CANDIDATE_FEATURE_MATERIALIZATION.value
        )


def test_ledger_enforces_null_with_indicator_materialization_semantics(
    tmp_path: Path,
) -> None:
    invalid = missing_policy_graph(
        policy=MissingInputPolicy.NULL_WITH_INDICATOR,
        feature_values=(
            encode_float64_be_hex_null_v1(123.0),
            encode_float64_be_hex_null_v1(0.0),
        ),
    )
    invalid_records = (
        *invalid["evidence_records"],
        invalid["source"],
        invalid["protocol"],
        invalid["information"],
        invalid["action_resolution"],
        invalid["candidate"],
    )
    with open_ledger(ledger_path(tmp_path, "invalid-missing.sqlite3")) as ledger:
        for index, record in enumerate(invalid_records, start=1):
            ledger.append(record, idempotency_key=f"invalid-missing-{index}")
        with pytest.raises(CanonicalizationError, match="must be null"):
            ledger.append(
                invalid["materialization"],
                idempotency_key="invalid-missing-materialization",
            )

    valid = missing_policy_graph(
        policy=MissingInputPolicy.NULL_WITH_INDICATOR,
        feature_values=(None, encode_float64_be_hex_null_v1(1.0)),
    )
    valid_records = (
        *valid["evidence_records"],
        valid["source"],
        valid["protocol"],
        valid["information"],
        valid["action_resolution"],
        valid["candidate"],
        valid["materialization"],
        valid["eligibility"],
    )
    with open_ledger(ledger_path(tmp_path, "valid-missing.sqlite3")) as ledger:
        for index, record in enumerate(valid_records, start=1):
            ledger.append(record, idempotency_key=f"valid-missing-{index}")
        assert ledger.verify().receipt_count == len(valid_records)


def test_ledger_rejects_eligible_verdict_for_missing_abstain_input(
    tmp_path: Path,
) -> None:
    graph = missing_policy_graph(
        policy=MissingInputPolicy.ABSTAIN,
        feature_values=(None,),
    )
    records = (
        *graph["evidence_records"],
        graph["source"],
        graph["protocol"],
        graph["information"],
        graph["action_resolution"],
        graph["candidate"],
        graph["materialization"],
    )
    with open_ledger(ledger_path(tmp_path)) as ledger:
        for index, record in enumerate(records, start=1):
            ledger.append(record, idempotency_key=f"abstain-missing-{index}")
        with pytest.raises(CanonicalizationError, match="requires ABSTAIN_DATA"):
            ledger.append(
                graph["eligibility"],
                idempotency_key="abstain-missing-eligibility",
            )


def test_ledger_rejects_null_publish_clock_with_future_event(tmp_path: Path) -> None:
    graph = governed_event_graph()
    poisoned_dependency = replace(
        graph["information"].dependencies[0],
        source_publish_ts=None,
    )
    object.__setattr__(
        poisoned_dependency,
        "ingested_first_seen_ts",
        datetime(2026, 7, 14, 8, 59, tzinfo=timezone.utc),
    )
    poisoned_information = replace(
        graph["information"],
        dependencies=(poisoned_dependency,),
    )
    with open_ledger(ledger_path(tmp_path)) as ledger:
        for index, record in enumerate(records_through(graph, "protocol"), start=1):
            ledger.append(record, idempotency_key=f"null-publish-{index}")
        with pytest.raises(CanonicalizationError, match="ingested_first_seen_ts"):
            ledger.append(
                poisoned_information,
                idempotency_key="null-publish-information",
            )


def test_candidate_geometry_is_compare_and_swap_protected(tmp_path: Path) -> None:
    graph = governed_event_graph()
    with open_ledger(ledger_path(tmp_path)) as ledger:
        for index, record in enumerate(records_through(graph, "candidate"), start=1):
            ledger.append(record, idempotency_key=f"candidate-cas-{index}")

        competing = replace(graph["candidate"], target_r_multiple="3")
        assert (
            competing.primary_signal_candidate_key
            == graph["candidate"].primary_signal_candidate_key
        )
        assert (
            competing.primary_signal_candidate_id
            != graph["candidate"].primary_signal_candidate_id
        )
        with pytest.raises(LedgerConflictError, match="compare-and-swap"):
            ledger.append(competing, idempotency_key="candidate-conflicting-geometry")


def test_materialized_vector_is_compare_and_swap_protected(tmp_path: Path) -> None:
    graph = governed_event_graph()
    with open_ledger(ledger_path(tmp_path)) as ledger:
        for index, record in enumerate(
            records_through(graph, "materialization"), start=1
        ):
            ledger.append(record, idempotency_key=f"materialization-cas-{index}")

        competing = CandidateFeatureMaterializationV3.create(
            information_set=graph["information"],
            candidate=graph["candidate"],
            feature_values=(encode_float64_be_hex_null_v1(2.5),),
            feature_available_ts=graph["materialization"].feature_available_ts,
        )
        assert (
            competing.candidate_feature_materialization_key
            == graph["materialization"].candidate_feature_materialization_key
        )
        assert (
            competing.candidate_feature_materialization_id
            != graph["materialization"].candidate_feature_materialization_id
        )
        with pytest.raises(LedgerConflictError, match="compare-and-swap"):
            ledger.append(
                competing, idempotency_key="materialization-conflicting-vector"
            )


def test_candidate_neutral_projection_is_shared_across_candidates(
    tmp_path: Path,
) -> None:
    graph = governed_event_graph()
    long_resolution = graph["resolution"]
    short_resolution = resolve_action_v3(
        information_set=graph["information"],
        calendar_artifact=graph["artifact"],
        calendar=graph["calendar"],
        protocol=graph["action_protocol"],
        mapping=graph["instrument_mapping"],
        primary_signal_id=long_resolution.primary_signal_id,
        primary_signal_version=long_resolution.primary_signal_version,
        primary_signal_policy_id=long_resolution.primary_signal_policy_id,
        signal_ts=long_resolution.signal_ts,
        side=TradeSide.SHORT,
        signal_available_ts=long_resolution.signal_available_ts,
        resolved_at=long_resolution.resolved_at,
    )
    short_candidate = replace(
        graph["candidate"],
        side=TradeSide.SHORT,
        action_resolution_id=short_resolution.action_resolution_id,
        action_resolution_record_hash=short_resolution.record_hash,
    )

    accepted_dir = tmp_path / "neutral-accepted"
    accepted_dir.mkdir(mode=0o700)
    with open_ledger(ledger_path(accepted_dir)) as ledger:
        for index, record in enumerate(
            records_through(graph, "materialization"), start=1
        ):
            ledger.append(record, idempotency_key=f"neutral-accepted-{index}")
        ledger.append(short_resolution, idempotency_key="neutral-short-resolution")
        ledger.append(short_candidate, idempotency_key="neutral-short-candidate")
        same_projection = CandidateFeatureMaterializationV3.create(
            information_set=graph["information"],
            candidate=short_candidate,
            feature_values=(encode_float64_be_hex_null_v1(1.5),),
            feature_available_ts=graph["materialization"].feature_available_ts,
        )
        ledger.append(same_projection, idempotency_key="neutral-same-projection")
        assert ledger.verify().receipt_count == 18

    rejected_dir = tmp_path / "neutral-rejected"
    rejected_dir.mkdir(mode=0o700)
    with open_ledger(ledger_path(rejected_dir)) as ledger:
        for index, record in enumerate(
            records_through(graph, "materialization"), start=1
        ):
            ledger.append(record, idempotency_key=f"neutral-rejected-{index}")
        ledger.append(short_resolution, idempotency_key="neutral-short-resolution")
        ledger.append(short_candidate, idempotency_key="neutral-short-candidate")
        changed_projection = CandidateFeatureMaterializationV3.create(
            information_set=graph["information"],
            candidate=short_candidate,
            feature_values=(encode_float64_be_hex_null_v1(99.0),),
            feature_available_ts=graph["materialization"].feature_available_ts,
        )
        with pytest.raises(LedgerConflictError, match="candidate-neutral"):
            ledger.append(
                changed_projection,
                idempotency_key="neutral-changed-projection",
            )
        assert ledger.verify().receipt_count == 17


def test_candidate_conditioned_projection_may_differ_across_candidates(
    tmp_path: Path,
) -> None:
    source, member, bundle, evidence_registry = governed_source_graph(
        content_suffix="candidate-conditioned-projection"
    )
    _, slot, definition, schema, evidence_registry = governed_protocol_graph(
        source,
        member,
        bundle,
        evidence_registry,
    )
    conditioned_definition = replace(
        definition,
        candidate_conditioned=True,
        candidate_field_names=("side",),
    )
    conditioned_schema = replace(
        schema,
        feature_definition_ids=(conditioned_definition.feature_definition_id,),
    )
    protocol = protocol_manifest(
        source,
        feature_schema_id=conditioned_schema.feature_schema_id,
    )
    evidence_registry.update(
        {
            conditioned_definition.feature_definition_id: conditioned_definition,
            conditioned_schema.feature_schema_id: conditioned_schema,
        }
    )
    information, long_candidate, long_values, _, _, long_resolution = (
        protocol_record_graph(
            protocol,
            source,
            evidence_registry,
        )
    )
    artifact = next(
        item
        for item in evidence_registry.values()
        if isinstance(item, CalendarSourceArtifactV3)
    )
    calendar = next(
        item
        for item in evidence_registry.values()
        if isinstance(item, CalendarScheduleSnapshotV3)
    )
    action_protocol = next(
        item
        for item in evidence_registry.values()
        if isinstance(item, ActionProtocolV3)
    )
    instrument_mapping = next(
        item
        for item in evidence_registry.values()
        if isinstance(item, InstrumentMappingV3)
    )
    short_resolution = resolve_action_v3(
        information_set=information,
        calendar_artifact=artifact,
        calendar=calendar,
        protocol=action_protocol,
        mapping=instrument_mapping,
        primary_signal_id=long_resolution.primary_signal_id,
        primary_signal_version=long_resolution.primary_signal_version,
        primary_signal_policy_id=long_resolution.primary_signal_policy_id,
        signal_ts=long_resolution.signal_ts,
        side=TradeSide.SHORT,
        signal_available_ts=long_resolution.signal_available_ts,
        resolved_at=long_resolution.resolved_at,
    )
    short_candidate = replace(
        long_candidate,
        side=TradeSide.SHORT,
        action_resolution_id=short_resolution.action_resolution_id,
        action_resolution_record_hash=short_resolution.record_hash,
    )
    short_values = CandidateFeatureMaterializationV3.create(
        information_set=information,
        candidate=short_candidate,
        feature_values=(encode_float64_be_hex_null_v1(99.0),),
        feature_available_ts=long_values.feature_available_ts,
    )
    records = (
        artifact,
        calendar,
        action_protocol,
        instrument_mapping,
        member,
        bundle,
        slot,
        conditioned_definition,
        conditioned_schema,
        source,
        protocol,
        information,
        long_resolution,
        long_candidate,
        long_values,
        short_resolution,
        short_candidate,
        short_values,
    )

    with open_ledger(ledger_path(tmp_path)) as ledger:
        for index, record in enumerate(records, start=1):
            ledger.append(record, idempotency_key=f"conditioned-{index}")
        assert ledger.verify().receipt_count == 18


def test_source_lineage_and_label_corrections_require_the_active_predecessor(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir(mode=0o700)
    with open_ledger(ledger_path(source_dir)) as ledger:
        root, root_member, root_bundle, _ = governed_source_graph(
            content_suffix="source-lineage-root"
        )
        child_member = replace(
            root_member,
            semantic_content_root=digest("source-lineage-child-content"),
            artifact_hash=digest("source-lineage-child-artifact"),
            row_count=3,
            event_end_ts="2026-07-14T09:02:00Z",
            knowledge_cutoff_ts="2026-07-14T09:02:03Z",
            parent_source_member_id=root_member.source_member_id,
        )
        child_bundle = replace(
            root_bundle,
            knowledge_cutoff_ts="2026-07-14T09:02:03Z",
            source_member_ids=(child_member.source_member_id,),
            parent_source_bundle_id=root_bundle.source_bundle_id,
        )
        child = source_manifest(
            parent_source_manifest_id=root.manifest_id,
            source_content_root=child_bundle.source_bundle_id,
            knowledge_cutoff_ts="2026-07-14T09:02:03Z",
            calendar_manifest_id=root.payload["calendar_manifest_id"],
        )
        ledger.append(root_member, idempotency_key="source-member-root")
        ledger.append(root_bundle, idempotency_key="source-bundle-root")
        root_receipt = ledger.append(root, idempotency_key="source-root")
        ledger.append(child_member, idempotency_key="source-member-child")
        ledger.append(child_bundle, idempotency_key="source-bundle-child")
        child_receipt = ledger.append(child, idempotency_key="source-child")
        assert child_receipt.expected_head == root.manifest_id
        assert (
            ledger.active_head("SOURCE_LINEAGE", root_receipt.semantic_key)
            == child.manifest_id
        )

        stale_sibling_member = replace(
            root_member,
            semantic_content_root=digest("source-lineage-stale-content"),
            artifact_hash=digest("source-lineage-stale-artifact"),
            row_count=4,
            event_end_ts="2026-07-14T09:03:00Z",
            knowledge_cutoff_ts="2026-07-14T09:03:03Z",
            parent_source_member_id=root_member.source_member_id,
        )
        with pytest.raises(LedgerConflictError, match="parent in an active"):
            ledger.append(stale_sibling_member, idempotency_key="source-stale")

    label_dir = tmp_path / "label"
    label_dir.mkdir(mode=0o700)
    with open_ledger(ledger_path(label_dir)) as ledger:
        _, _, _, _, decision, _ = append_event_graph(ledger)
        activation = barrier_activation(decision)
        ledger.append(activation, idempotency_key="activation")
        outcome = filled_outcome(decision)
        ledger.append(outcome, idempotency_key="outcome-v1")

        corrected = replace(
            outcome,
            mae_bps="60",
            supersedes_label_outcome_id=outcome.label_outcome_id,
        )
        ledger.append(corrected, idempotency_key="outcome-v2")
        assert (
            ledger.active_head("LABEL_OUTCOME", decision.decision_event_id)
            == corrected.label_outcome_id
        )

        backwards_clock = replace(
            corrected,
            label_known_ts="2026-07-14T09:02:45Z",
            supersedes_label_outcome_id=corrected.label_outcome_id,
        )
        with pytest.raises(LedgerConflictError, match="must not move backwards"):
            ledger.append(backwards_clock, idempotency_key="outcome-backwards")

        stale_correction = replace(
            outcome,
            mfe_bps="2001",
            supersedes_label_outcome_id=outcome.label_outcome_id,
        )
        with pytest.raises(LedgerConflictError, match="compare-and-swap"):
            ledger.append(stale_correction, idempotency_key="outcome-stale")
        assert ledger.verify().object_count == 20


def test_dependence_assignment_tracks_active_label_and_uses_linear_supersession(
    tmp_path: Path,
) -> None:
    with open_ledger(ledger_path(tmp_path)) as ledger:
        _, _, _, _, decision, _ = append_event_graph(ledger)
        activation = barrier_activation(decision)
        ledger.append(activation, idempotency_key="activation")
        outcome = filled_outcome(decision)
        ledger.append(outcome, idempotency_key="outcome")
        assignment = EventDependenceAssignmentV3(
            decision_event_id=decision.decision_event_id,
            label_outcome_id=outcome.label_outcome_id,
            dependence_policy_id=digest("dependence-policy"),
            event_cluster_id=digest("event-cluster-v1"),
            dependence_interval_start_ts=decision.earliest_entry_ts,
            dependence_interval_end_ts=outcome.label_known_ts,
            assignment_known_ts=outcome.label_known_ts,
            concurrency=2,
            uniqueness_weight="0.5",
        )
        ledger.append(assignment, idempotency_key="assignment-v1")
        corrected_assignment = replace(
            assignment,
            event_cluster_id=digest("event-cluster-v2"),
            concurrency=3,
            uniqueness_weight="0.33333333",
            supersedes_assignment_id=assignment.assignment_id,
        )
        ledger.append(corrected_assignment, idempotency_key="assignment-v2")

        stale = replace(
            assignment,
            event_cluster_id=digest("event-cluster-stale"),
            supersedes_assignment_id=assignment.assignment_id,
        )
        with pytest.raises(LedgerConflictError, match="compare-and-swap"):
            ledger.append(stale, idempotency_key="assignment-stale")

        corrected_outcome = replace(
            outcome,
            mae_bps="60",
            supersedes_label_outcome_id=outcome.label_outcome_id,
        )
        ledger.append(corrected_outcome, idempotency_key="outcome-v2")
        old_label_assignment = replace(
            corrected_assignment,
            event_cluster_id=digest("event-cluster-old-label"),
            supersedes_assignment_id=corrected_assignment.assignment_id,
        )
        with pytest.raises(LedgerConflictError, match="active label outcome"):
            ledger.append(old_label_assignment, idempotency_key="assignment-old-label")

        current = replace(
            corrected_assignment,
            label_outcome_id=corrected_outcome.label_outcome_id,
            event_cluster_id=digest("event-cluster-current-label"),
            supersedes_assignment_id=corrected_assignment.assignment_id,
        )
        ledger.append(current, idempotency_key="assignment-current-label")
        assert ledger.verify().object_count == 23


def test_only_one_authoritative_writer_can_open_a_ledger(tmp_path: Path) -> None:
    path = ledger_path(tmp_path)
    first = open_ledger(path)
    try:
        with pytest.raises(LedgerWriterLockError, match="authoritative writer lock"):
            open_ledger(path)
    finally:
        first.close()

    with open_ledger(path) as reopened:
        assert reopened.verify().receipt_count == 0


@pytest.mark.parametrize(
    "failure_stage",
    [
        "after_object_insert",
        "after_receipt_insert",
        "after_head_transition_insert",
    ],
)
def test_fault_injection_rolls_back_the_entire_append_transaction(
    tmp_path: Path,
    failure_stage: str,
) -> None:
    enabled = True

    def inject(stage: str) -> None:
        if enabled and stage == failure_stage:
            raise RuntimeError(f"injected fault at {stage}")

    with open_ledger(ledger_path(tmp_path), fault_injector=inject) as ledger:
        source = standalone_record("faulted-source")
        with pytest.raises(RuntimeError, match=failure_stage):
            ledger.append(source, idempotency_key="faulted-source")

        report = ledger.verify()
        assert report.object_count == 0
        assert report.receipt_count == 0
        assert report.head_transition_count == 0
        with pytest.raises(LedgerNotFoundError):
            ledger.receipt_for_idempotency_key("faulted-source")

        enabled = False
        receipt = ledger.append(source, idempotency_key="faulted-source")
        assert receipt.global_sequence == 1
        assert ledger.verify().receipt_count == 1


def test_process_death_before_commit_recovers_without_a_partial_append(
    tmp_path: Path,
) -> None:
    path = ledger_path(tmp_path)
    with open_ledger(path):
        pass

    process = multiprocessing.get_context("spawn").Process(
        target=_crash_during_append,
        args=(str(path),),
    )
    process.start()
    process.join(timeout=20)
    assert process.exitcode == 77

    with open_ledger(path) as ledger:
        report = ledger.verify()
        assert report.object_count == 0
        assert report.receipt_count == 0
        assert report.head_transition_count == 0
        receipt = ledger.append(
            standalone_record("crashing-source"),
            idempotency_key="crashing-source",
        )
        assert receipt.global_sequence == 1


def test_checkpoint_and_holdout_faults_roll_back_governance_state(
    tmp_path: Path,
) -> None:
    failure_stage: str | None = None

    def inject(stage: str) -> None:
        if stage == failure_stage:
            raise RuntimeError(f"injected governance fault at {stage}")

    path = ledger_path(tmp_path)
    with open_ledger(path, fault_injector=inject) as ledger:
        nominal, protocol, forward, final_split, records = final_holdout_graph()
        del nominal, forward
        for index, record in enumerate(records, start=1):
            ledger.append(record, idempotency_key=f"governance-graph-{index}")

        signer = Ed25519CheckpointSigner.generate()
        failure_stage = "after_checkpoint_insert"
        with pytest.raises(RuntimeError, match="after_checkpoint_insert"):
            ledger.create_checkpoint(signer, idempotency_key="checkpoint-fault")
        assert ledger.verify().checkpoint_count == 0
        with pytest.raises(LedgerNotFoundError):
            ledger.receipt_for_idempotency_key("checkpoint-fault")

        failure_stage = None
        checkpoint = ledger.create_checkpoint(
            signer,
            idempotency_key="checkpoint-fault",
        )
        arguments = grant_arguments(
            protocol.manifest_id,
            final_split.manifest_id,
            checkpoint.checkpoint_id,
        )
        failure_stage = "after_holdout_grant_insert"
        with pytest.raises(RuntimeError, match="after_holdout_grant_insert"):
            ledger.grant_final_holdout_evaluation(
                **arguments,
                idempotency_key="grant-fault",
            )
        report = ledger.verify(
            trusted_checkpoint=checkpoint,
            verifier=signer.verifier(),
        )
        assert report.checkpoint_count == 1
        assert report.holdout_grant_count == 0
        with pytest.raises(LedgerNotFoundError):
            ledger.receipt_for_idempotency_key("grant-fault")

        failure_stage = None
        ledger.grant_final_holdout_evaluation(
            **arguments,
            idempotency_key="grant-fault",
        )
        assert ledger.verify().holdout_grant_count == 1


def test_immutability_trigger_blocks_updates_and_verifier_detects_owner_tamper(
    tmp_path: Path,
) -> None:
    path = ledger_path(tmp_path)
    with open_ledger(path) as ledger:
        ledger.append(standalone_record("immutability"), idempotency_key="source")
        with pytest.raises(sqlite3.DatabaseError, match="objects are immutable"):
            ledger._connection.execute(
                "UPDATE objects SET canonical_blob = ?",
                (b"{}",),
            )

    # The owning Unix user can bypass local triggers. Recreating the trigger
    # models an attacker trying to conceal that bypass; content verification
    # must still reject the altered canonical bytes.
    connection = sqlite3.connect(path)
    try:
        original = bytes(
            connection.execute("SELECT canonical_blob FROM objects").fetchone()[0]
        )
        connection.execute("DROP TRIGGER objects_no_update")
        connection.execute(
            "UPDATE objects SET canonical_blob = ?",
            (original + b" ",),
        )
        connection.execute(
            """
            CREATE TRIGGER objects_no_update BEFORE UPDATE ON objects
            BEGIN SELECT RAISE(ABORT, 'objects are immutable'); END
            """
        )
        connection.commit()
    finally:
        connection.close()

    with V3GovernanceLedger.open_read_only(path) as ledger:
        with pytest.raises(LedgerVerificationError):
            ledger.verify()


def test_writable_reopen_refuses_to_extend_malformed_history(tmp_path: Path) -> None:
    path = ledger_path(tmp_path)
    with open_ledger(path) as ledger:
        ledger.append(
            standalone_record("startup-source"),
            idempotency_key="startup-source",
        )

    connection = sqlite3.connect(path)
    try:
        trigger_sql = connection.execute(
            """
            SELECT sql FROM sqlite_schema
            WHERE type = 'trigger' AND name = 'objects_no_update'
            """
        ).fetchone()[0]
        connection.execute("DROP TRIGGER objects_no_update")
        connection.execute("UPDATE objects SET canonical_blob = ?", (b"{",))
        connection.execute(trigger_sql)
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(
        LedgerVerificationError,
        match="stored ledger state could not be decoded",
    ):
        open_ledger(path)


def test_ed25519_checkpoint_is_trusted_only_with_the_matching_public_key(
    tmp_path: Path,
) -> None:
    with open_ledger(ledger_path(tmp_path)) as ledger:
        receipt = ledger.append(
            standalone_record("checkpoint-source"),
            idempotency_key="source",
        )
        signer = Ed25519CheckpointSigner.generate()
        checkpoint = ledger.create_checkpoint(signer, idempotency_key="checkpoint")

        assert checkpoint.global_sequence == receipt.global_sequence
        report = ledger.verify(
            trusted_checkpoint=checkpoint.as_dict(),
            verifier=signer.verifier(),
        )
        assert report.trusted_checkpoint_id == checkpoint.checkpoint_id
        assert report.trusted_global_sequence == checkpoint.global_sequence
        assert report.unanchored_receipt_count == 1
        assert report.checkpoint_count == 1

        wrong_signer = Ed25519CheckpointSigner.generate()
        with pytest.raises(LedgerVerificationError, match="key ID mismatch"):
            ledger.verify(
                trusted_checkpoint=checkpoint,
                verifier=wrong_signer.verifier(),
            )


def test_external_checkpoint_detects_consistent_database_rollback(
    tmp_path: Path,
) -> None:
    path = ledger_path(tmp_path)
    rollback_dir = tmp_path / "rollback"
    rollback_dir.mkdir(mode=0o700)
    rollback_path = rollback_dir / "ledger-before-receipts.sqlite3"

    with open_ledger(path) as ledger:
        ledger.backup_to(rollback_path)
        ledger.append(
            standalone_record("rollback-source"),
            idempotency_key="source",
        )
        signer = Ed25519CheckpointSigner.generate()
        checkpoint = ledger.create_checkpoint(signer, idempotency_key="checkpoint")
        assert (
            ledger.verify(
                trusted_checkpoint=checkpoint,
                verifier=signer.verifier(),
            ).trusted_checkpoint_id
            == checkpoint.checkpoint_id
        )

    with V3GovernanceLedger.open_read_only(rollback_path) as rolled_back:
        assert rolled_back.verify().receipt_count == 0
        with pytest.raises(
            LedgerVerificationError,
            match="missing receipt sequence",
        ):
            rolled_back.verify(
                trusted_checkpoint=checkpoint,
                verifier=signer.verifier(),
            )


def test_split_manifest_must_bind_the_exact_event_and_label_prefix_roots(
    tmp_path: Path,
) -> None:
    with open_ledger(ledger_path(tmp_path)) as ledger:
        source, protocol, _, _, decision, _ = append_event_graph(ledger)
        activation = barrier_activation(decision)
        activation_receipt = ledger.append(activation, idempotency_key="activation")
        outcome = filled_outcome(decision)
        outcome_receipt = ledger.append(outcome, idempotency_key="outcome")

        wrong = split_manifest(
            protocol,
            source,
            event_ledger_root=digest("wrong-event-root"),
            label_ledger_root=outcome_receipt.receipt_hash,
        )
        with pytest.raises(LedgerConflictError, match="event_ledger_root"):
            ledger.append(wrong, idempotency_key="split-wrong")

        exact = split_manifest(
            protocol,
            source,
            event_ledger_root=activation_receipt.receipt_hash,
            label_ledger_root=outcome_receipt.receipt_hash,
        )
        ledger.append(exact, idempotency_key="split-exact")
        assert ledger.get_record(LedgerRecordKind.MANIFEST, exact.manifest_id) == exact
        assert ledger.verify().object_count == 20


def test_final_holdout_grant_is_locally_once_but_is_not_a_data_access_boundary(
    tmp_path: Path,
) -> None:
    path = ledger_path(tmp_path)
    with open_ledger(path) as ledger:
        nominal, protocol, forward, final_split, records = final_holdout_graph()
        del nominal, forward
        for index, record in enumerate(records, start=1):
            ledger.append(record, idempotency_key=f"holdout-graph-{index}")

        signer = Ed25519CheckpointSigner.generate()
        checkpoint = ledger.create_checkpoint(
            signer,
            idempotency_key="holdout-checkpoint",
        )
        arguments = grant_arguments(
            protocol.manifest_id,
            final_split.manifest_id,
            checkpoint.checkpoint_id,
        )
        grant = ledger.grant_final_holdout_evaluation(
            **arguments,
            idempotency_key="holdout-grant",
        )
        assert (
            ledger.grant_final_holdout_evaluation(
                **arguments,
                idempotency_key="holdout-grant",
            )
            == grant
        )
        with pytest.raises(HoldoutGrantConflictError, match="already granted"):
            ledger.grant_final_holdout_evaluation(
                **arguments,
                idempotency_key="second-holdout-grant",
            )

        report = ledger.verify(
            trusted_checkpoint=checkpoint,
            verifier=signer.verifier(),
        )
        assert report.holdout_grant_count == 1

        # This is intentionally an honesty ledger, not a blind evaluator: the
        # same trusted OS user can still retrieve the split and read its bytes.
        assert (
            ledger.get_record(LedgerRecordKind.MANIFEST, final_split.manifest_id)
            == final_split
        )
        observer = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            assert observer.execute("SELECT count(*) FROM objects").fetchone()[0] == 15
        finally:
            observer.close()


def test_backup_is_private_complete_and_independently_verified(tmp_path: Path) -> None:
    path = ledger_path(tmp_path)
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(mode=0o700)
    backup_path = backup_dir / "ledger-backup.sqlite3"

    with open_ledger(path) as ledger:
        ledger.append(standalone_record("backup-source"), idempotency_key="source")
        signer = Ed25519CheckpointSigner.generate()
        ledger.create_checkpoint(signer, idempotency_key="checkpoint")
        expected = ledger.verify()
        backup_report = ledger.backup_to(backup_path)

    assert stat.S_IMODE(backup_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(backup_path.stat().st_mode) == 0o600
    assert backup_report.receipt_count == expected.receipt_count
    assert backup_report.object_count == expected.object_count
    assert backup_report.checkpoint_count == expected.checkpoint_count
    assert backup_report.global_receipt_root == expected.global_receipt_root

    with V3GovernanceLedger.open_read_only(backup_path) as backup:
        assert backup.verify().as_dict() == backup_report.as_dict()


def test_object_size_limit_is_immutable_and_reopen_uses_stored_limit(
    tmp_path: Path,
) -> None:
    path = ledger_path(tmp_path)
    with V3GovernanceLedger(
        path,
        clock=lambda: LEDGER_NOW,
        max_object_bytes=64,
    ) as ledger:
        with pytest.raises(LedgerConflictError, match="max_object_bytes"):
            ledger.append(standalone_record("oversized"), idempotency_key="oversized")
        assert ledger.verify().receipt_count == 0

    with open_ledger(path) as reopened:
        with pytest.raises(LedgerConflictError, match="max_object_bytes"):
            reopened.append(
                standalone_record("oversized"),
                idempotency_key="oversized",
            )
        assert reopened.verify().receipt_count == 0

    with pytest.raises(LedgerConfigurationError, match="max_object_bytes differs"):
        V3GovernanceLedger(path, max_object_bytes=128)


def test_verify_uses_one_snapshot_during_a_concurrent_legitimate_append(
    tmp_path: Path,
) -> None:
    path = ledger_path(tmp_path)
    source = standalone_record("snapshot-first")
    protocol = standalone_record("snapshot-second")
    initial_ready = threading.Event()
    start_second_append = threading.Event()
    writer_inside_transaction = threading.Event()
    writer_done = threading.Event()
    receipt_chain_read = threading.Event()
    continue_verification = threading.Event()
    state: dict[str, object] = {}
    errors: list[BaseException] = []

    def observe_write(stage: str) -> None:
        if stage == "after_object_insert" and initial_ready.is_set():
            writer_inside_transaction.set()

    def writer_target() -> None:
        try:
            with open_ledger(path, fault_injector=observe_write) as writer:
                first = writer.append(source, idempotency_key="snapshot-source")
                state["before"] = (1, 1, 1, first.receipt_hash)
                initial_ready.set()
                if not start_second_append.wait(timeout=10):
                    raise AssertionError("second append was not released")
                second = writer.append(protocol, idempotency_key="snapshot-protocol")
                state["after"] = (2, 2, 2, second.receipt_hash)
        except BaseException as exc:  # pragma: no cover - surfaced below
            errors.append(exc)
        finally:
            writer_done.set()

    original_receipt_verifier = V3GovernanceLedger._verify_receipt_chain

    def pause_after_receipt_chain(self: V3GovernanceLedger):
        result = original_receipt_verifier(self)
        if not self.read_only:
            return result
        receipt_chain_read.set()
        if not continue_verification.wait(timeout=10):
            raise AssertionError("verification was not released")
        return result

    def reader_target() -> None:
        try:
            with V3GovernanceLedger.open_read_only(path) as reader:
                report = reader.verify()
                state["observed"] = (
                    report.object_count,
                    report.receipt_count,
                    report.head_transition_count,
                    report.global_receipt_root,
                )
        except BaseException as exc:  # pragma: no cover - surfaced below
            errors.append(exc)

    with patch.object(
        V3GovernanceLedger,
        "_verify_receipt_chain",
        pause_after_receipt_chain,
    ):
        writer = threading.Thread(target=writer_target, name="ledger-writer")
        writer.start()
        assert initial_ready.wait(timeout=10)

        reader = threading.Thread(target=reader_target, name="ledger-verifier")
        reader.start()
        assert receipt_chain_read.wait(timeout=10)
        start_second_append.set()
        assert writer_inside_transaction.wait(timeout=10)

        # Without a read transaction the writer commits while verification is
        # paused, exposing mixed receipt/object snapshots. With a real snapshot
        # the rollback-journal commit waits for the reader to finish.
        writer_done.wait(timeout=1)
        continue_verification.set()
        reader.join(timeout=10)
        writer.join(timeout=10)

    assert not reader.is_alive()
    assert not writer.is_alive()
    assert errors == []
    assert state["observed"] in {state["before"], state["after"]}


@pytest.mark.parametrize(
    "table",
    ["receipts", "objects", "checkpoints", "holdout_grants"],
)
def test_verifier_rejects_noncanonical_whitespace_in_every_governance_blob(
    tmp_path: Path,
    table: str,
) -> None:
    path = ledger_path(tmp_path)
    with open_ledger(path) as ledger:
        append_holdout_grant(ledger)

    connection = sqlite3.connect(path)
    try:
        rowid, canonical_blob = connection.execute(
            f"SELECT rowid, canonical_blob FROM {table} ORDER BY rowid LIMIT 1"
        ).fetchone()
        connection.execute(f"DROP TRIGGER {_UPDATE_TRIGGER_NAME[table]}")
        connection.execute(
            f"UPDATE {table} SET canonical_blob = ? WHERE rowid = ?",
            (bytes(canonical_blob) + b" ", rowid),
        )
        connection.execute(_UPDATE_TRIGGER_SQL[table])
        connection.commit()
    finally:
        connection.close()

    with V3GovernanceLedger.open_read_only(path) as ledger:
        with pytest.raises(LedgerVerificationError):
            ledger.verify()


@pytest.mark.parametrize(
    "orphaned_table",
    ["objects", "checkpoints", "holdout_grants"],
)
def test_verifier_rejects_receipts_without_their_authoritative_payload_row(
    tmp_path: Path,
    orphaned_table: str,
) -> None:
    path = ledger_path(tmp_path)
    with open_ledger(path) as ledger:
        if orphaned_table == "objects":
            ledger.append(
                standalone_record("orphan-object"),
                idempotency_key="orphan-source",
            )
        elif orphaned_table == "checkpoints":
            ledger.append(
                standalone_record("orphan-checkpoint"),
                idempotency_key="orphan-source",
            )
            ledger.create_checkpoint(
                Ed25519CheckpointSigner.generate(),
                idempotency_key="orphan-checkpoint",
            )
        else:
            append_holdout_grant(ledger)

    connection = sqlite3.connect(path)
    try:
        connection.execute(f"DROP TRIGGER {_DELETE_TRIGGER_NAME[orphaned_table]}")
        connection.execute(f"DELETE FROM {orphaned_table}")
        connection.execute(_DELETE_TRIGGER_SQL[orphaned_table])
        connection.commit()
    finally:
        connection.close()

    with V3GovernanceLedger.open_read_only(path) as ledger:
        with pytest.raises(LedgerVerificationError):
            ledger.verify()


def test_verifier_detects_a_tampered_max_object_bytes_limit(tmp_path: Path) -> None:
    path = ledger_path(tmp_path)
    with open_ledger(path) as ledger:
        ledger.append(
            standalone_record("size-bound-source"),
            idempotency_key="size-bound-source",
        )

    connection = sqlite3.connect(path)
    try:
        connection.execute("DROP TRIGGER ledger_meta_no_update")
        connection.execute("UPDATE ledger_meta SET max_object_bytes = 1")
        connection.execute(
            """
            CREATE TRIGGER ledger_meta_no_update BEFORE UPDATE ON ledger_meta
            BEGIN SELECT RAISE(ABORT, 'ledger_meta is immutable'); END
            """
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(LedgerConfigurationError, match="identity.*metadata"):
        V3GovernanceLedger.open_read_only(path)


def test_ledger_identity_and_checkpoint_bind_an_in_range_policy_increase(
    tmp_path: Path,
) -> None:
    path = ledger_path(tmp_path)
    with open_ledger(path) as ledger:
        ledger.append(
            standalone_record("bound-meta-source"),
            idempotency_key="bound-meta-source",
        )
        signer = Ed25519CheckpointSigner.generate()
        checkpoint = ledger.create_checkpoint(
            signer,
            idempotency_key="bound-meta-checkpoint",
        )

        connection = sqlite3.connect(path)
        try:
            trigger_sql = connection.execute(
                """
                SELECT sql FROM sqlite_schema
                WHERE type = 'trigger' AND name = 'ledger_meta_no_update'
                """
            ).fetchone()[0]
            connection.execute("DROP TRIGGER ledger_meta_no_update")
            connection.execute(
                "UPDATE ledger_meta SET max_object_bytes = ?",
                (2 * 1024 * 1024,),
            )
            connection.execute(trigger_sql)
            connection.commit()
        finally:
            connection.close()

        with pytest.raises(LedgerConfigurationError, match="identity.*metadata"):
            ledger.verify(
                trusted_checkpoint=checkpoint,
                verifier=signer.verifier(),
            )


def test_failed_new_ledger_initialization_does_not_poison_the_path(
    tmp_path: Path,
) -> None:
    path = ledger_path(tmp_path)
    with patch.object(
        V3GovernanceLedger,
        "_initialize_schema",
        side_effect=RuntimeError("injected schema initialization failure"),
    ):
        with pytest.raises(RuntimeError, match="injected schema"):
            open_ledger(path)

    assert not path.exists()
    with open_ledger(path) as ledger:
        receipt = ledger.append(
            standalone_record("retry-source"),
            idempotency_key="retry-source",
        )
        assert receipt.global_sequence == 1
        assert ledger.verify().receipt_count == 1


def test_sidecar_validation_failure_never_raises_after_committing_the_append(
    tmp_path: Path,
) -> None:
    with open_ledger(ledger_path(tmp_path)) as ledger:
        original_validator = ledger._validate_sidecar_permissions

        validation_calls = 0

        def reject_sidecar() -> None:
            nonlocal validation_calls
            validation_calls += 1
            if validation_calls == 2:
                raise LedgerSecurityError("injected unsafe sidecar permissions")

        ledger._validate_sidecar_permissions = reject_sidecar  # type: ignore[method-assign]
        try:
            with pytest.raises(LedgerSecurityError, match="unsafe sidecar"):
                ledger.append(
                    standalone_record("sidecar-source"),
                    idempotency_key="sidecar-source",
                )
        finally:
            ledger._validate_sidecar_permissions = original_validator  # type: ignore[method-assign]

        assert validation_calls == 2
        report = ledger.verify()
        assert report.object_count == 0
        assert report.receipt_count == 0
        assert report.head_transition_count == 0
        with pytest.raises(LedgerNotFoundError):
            ledger.receipt_for_idempotency_key("sidecar-source")


def test_broken_sidecar_symlink_is_rejected_explicitly(tmp_path: Path) -> None:
    path = ledger_path(tmp_path)
    with open_ledger(path):
        pass
    journal = Path(f"{path}-journal")
    journal.symlink_to(tmp_path / "missing-sidecar-target")

    with pytest.raises(LedgerSecurityError, match="not a regular file"):
        open_ledger(path)
    with pytest.raises(LedgerSecurityError, match="not a regular file"):
        V3GovernanceLedger.open_read_only(path)


def test_structural_signer_cannot_register_a_forged_zero_signature(
    tmp_path: Path,
) -> None:
    forged_public_key_bytes = b"\x00" * 32
    assert not ed25519_public_key_is_valid(forged_public_key_bytes)
    assert not ed25519_public_key_is_valid(b"\x01" + b"\x00" * 31)

    class ZeroSignatureSigner:
        algorithm = "ED25519"
        key_id = derive_ed25519_key_id(forged_public_key_bytes)
        public_key_bytes = forged_public_key_bytes

        @staticmethod
        def sign(_payload: bytes) -> bytes:
            return b"\x00" * 64

    with open_ledger(ledger_path(tmp_path)) as ledger:
        ledger.append(
            standalone_record("forged-source"),
            idempotency_key="forged-source",
        )
        with pytest.raises(LedgerConfigurationError, match="invalid.*signature"):
            ledger.create_checkpoint(
                ZeroSignatureSigner(),
                idempotency_key="forged-checkpoint",
            )
        report = ledger.verify()
        assert report.checkpoint_count == 0
        assert report.receipt_count == 1


def test_verifier_checks_every_stored_checkpoint_with_the_trusted_key(
    tmp_path: Path,
) -> None:
    signer = Ed25519CheckpointSigner.generate()
    calls: list[bytes] = []

    class CountingVerifier:
        algorithm = signer.algorithm
        key_id = signer.key_id

        @staticmethod
        def verify(payload: bytes, signature: bytes) -> None:
            calls.append(payload)
            signer.verifier().verify(payload, signature)

    with open_ledger(ledger_path(tmp_path)) as ledger:
        ledger.append(
            standalone_record("signature-source"),
            idempotency_key="signature-source",
        )
        first = ledger.create_checkpoint(signer, idempotency_key="signature-first")
        second = ledger.create_checkpoint(signer, idempotency_key="signature-second")
        report = ledger.verify(
            trusted_checkpoint=second,
            verifier=CountingVerifier(),
        )

    # Both stored checkpoints plus the separately supplied trust anchor are
    # checked. The second signature is deliberately checked twice because the
    # stored chain and detached external evidence are distinct trust inputs.
    assert report.checkpoint_count == 2
    assert report.trusted_checkpoint_id == second.checkpoint_id
    assert len(calls) == 3
    assert first.checkpoint_id != second.checkpoint_id


def test_schema_fingerprint_rejects_same_named_no_op_trigger(tmp_path: Path) -> None:
    path = ledger_path(tmp_path)
    with open_ledger(path) as ledger:
        ledger.append(
            standalone_record("schema-source"),
            idempotency_key="schema-source",
        )

    connection = sqlite3.connect(path)
    try:
        connection.execute("DROP TRIGGER objects_no_update")
        connection.execute(
            """
            CREATE TRIGGER objects_no_update BEFORE UPDATE ON objects
            BEGIN SELECT 1; END
            """
        )
        connection.commit()
    finally:
        connection.close()

    with V3GovernanceLedger.open_read_only(path) as ledger:
        with pytest.raises(LedgerVerificationError, match="certified ledger schema"):
            ledger.verify()


def test_existing_insecure_database_mode_is_rejected_not_repaired(
    tmp_path: Path,
) -> None:
    path = ledger_path(tmp_path)
    with open_ledger(path):
        pass
    path.chmod(0o644)

    with pytest.raises(LedgerSecurityError, match="mode 0600"):
        open_ledger(path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o644

    with pytest.raises(LedgerSecurityError, match="mode 0600"):
        V3GovernanceLedger.open_read_only(path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o644


def test_append_refuses_a_connection_with_weakened_durability(tmp_path: Path) -> None:
    path = ledger_path(tmp_path)
    with open_ledger(path) as ledger:
        ledger._connection.execute("PRAGMA synchronous = OFF")
        with pytest.raises(LedgerConfigurationError, match="synchronous.*EXTRA"):
            ledger.append(
                standalone_record("weakened-durability-source"),
                idempotency_key="weakened-durability-source",
            )

    with open_ledger(path) as ledger:
        assert ledger.verify().receipt_count == 0
        receipt = ledger.append(
            standalone_record("restored-durability-source"),
            idempotency_key="restored-durability-source",
        )
        assert receipt.global_sequence == 1


def test_only_a_post_grant_external_checkpoint_seals_the_holdout_grant(
    tmp_path: Path,
) -> None:
    with open_ledger(ledger_path(tmp_path)) as ledger:
        protocol, final_split, signer, pre_grant_checkpoint, grant = (
            append_holdout_grant(ledger)
        )
        del protocol, final_split

        with pytest.raises(LedgerVerificationError):
            ledger.verify_holdout_evaluation_seal(
                grant.grant_id,
                trusted_checkpoint=pre_grant_checkpoint,
                verifier=signer.verifier(),
            )

        post_grant_checkpoint = ledger.create_checkpoint(
            signer,
            idempotency_key="post-grant-checkpoint",
        )
        seal = ledger.verify_holdout_evaluation_seal(
            grant.grant_id,
            trusted_checkpoint=post_grant_checkpoint.as_dict(),
            verifier=signer.verifier(),
        )
        assert seal.grant_id == grant.grant_id
        assert seal.grant_receipt_sequence == post_grant_checkpoint.global_sequence
        assert seal.trusted_checkpoint_id == post_grant_checkpoint.checkpoint_id
        assert seal.trusted_global_sequence >= seal.grant_receipt_sequence

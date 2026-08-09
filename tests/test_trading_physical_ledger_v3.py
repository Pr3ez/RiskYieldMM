from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from riskyieldmm.trading import (
    CanonicalizationError,
    ContinuityPolicy,
    DependencySelectionMode,
    DerivationKind,
    InformationDependencyV3,
    LedgerChannel,
    LedgerConflictError,
    ObservationSelectionPolicyV3,
    PhysicalGateStage,
    SelectionAnchor,
    V3GovernanceLedger,
    build_physical_evidence_gate_v3,
    observation_value_digest,
    select_observation_revisions_v3,
    utc_iso,
)
from riskyieldmm.trading.evidence import SourceBundleV3
from riskyieldmm.trading.physical_market_data import (
    EvidencePrefixV3,
    MessageDispositionKind,
    PhysicalVintage,
    PrefixHealth,
    ProviderMessageDispositionV3,
    build_bybit_v5_message_disposition,
    normalize_bybit_v5_instrument_info,
    normalize_bybit_v5_kline_message,
)
from tests.test_trading_ledger_v3 import LEDGER_NOW, governed_event_graph
from tests.test_trading_manifests_v3 import (
    governed_protocol_graph,
    protocol_manifest,
    protocol_record_graph,
    source_manifest,
)
from tests.test_trading_physical_market_data_v3 import (
    T0,
    bar_policy,
    digest,
    kline_bytes,
    segment,
    source_member_placeholder,
    status_bytes,
    status_policy,
)


@dataclass
class MutableClock:
    value: datetime

    def __call__(self) -> datetime:
        return self.value


@dataclass
class LedgerScenario:
    ledger: V3GovernanceLedger
    clock: MutableClock
    append_ordinal: int = 0

    def append(self, record: Any, *, at: datetime | None = None):
        if at is not None:
            self.clock.value = at
        self.append_ordinal += 1
        return self.ledger.append(
            record,
            idempotency_key=f"physical-ledger-{self.append_ordinal}",
        )


@contextmanager
def physical_ledger(tmp_path: Path) -> Iterator[LedgerScenario]:
    tmp_path.chmod(0o700)
    calendar = governed_event_graph()["calendar"]
    clock = MutableClock(calendar.frozen_at)
    with V3GovernanceLedger(
        tmp_path / "physical-ledger.sqlite3", clock=clock
    ) as ledger:
        yield LedgerScenario(ledger=ledger, clock=clock)


def append_observation_foundation(
    scenario: LedgerScenario,
    *,
    append_bar_revision: bool = True,
    append_extra_price_segment: bool = False,
) -> dict[str, Any]:
    base = governed_event_graph()
    artifact = base["artifact"]
    calendar = base["calendar"]
    action_protocol = base["action_protocol"]
    mapping = replace(base["instrument_mapping"], provider_id="BYBIT")
    price_policy = replace(
        bar_policy(),
        calendar_manifest_id=calendar.calendar_snapshot_id,
        provider_id=mapping.provider_id,
        frozen_at=calendar.frozen_at,
    )
    instrument_status_policy = replace(
        status_policy(),
        calendar_manifest_id=calendar.calendar_snapshot_id,
        provider_id=mapping.provider_id,
        frozen_at=calendar.frozen_at,
    )
    placeholder = source_member_placeholder(price_policy)
    for record in (
        artifact,
        calendar,
        action_protocol,
        mapping,
        price_policy,
        instrument_status_policy,
    ):
        scenario.append(record)

    status_segment = segment(
        instrument_status_policy,
        status_bytes(),
        received_at=T0 + timedelta(seconds=30, milliseconds=100),
    )
    status_segment_receipt = scenario.append(
        status_segment,
        at=T0 + timedelta(seconds=30, milliseconds=200),
    )
    status_derivation, status_revision = normalize_bybit_v5_instrument_info(
        adapter_policy=instrument_status_policy,
        segment=status_segment,
        message_receipt_id=status_segment.message_receipt_ids[0],
        source_member_key=placeholder.source_member_key,
        instrument_mapping_id=mapping.instrument_mapping_id,
        durably_appended_ts=status_segment_receipt.receipt_ts,
        normalized_at=status_segment_receipt.receipt_ts + timedelta(milliseconds=50),
        available_at=status_segment_receipt.receipt_ts + timedelta(milliseconds=100),
    )
    scenario.append(status_derivation, at=status_revision.available_at)
    scenario.append(status_revision)
    (
        status_disposition,
        classified_status_derivation,
        classified_status_revision,
    ) = build_bybit_v5_message_disposition(
        adapter_policy=instrument_status_policy,
        segment=status_segment,
        message_receipt_id=status_segment.message_receipt_ids[0],
        source_member_key=placeholder.source_member_key,
        instrument_mapping_id=mapping.instrument_mapping_id,
        durably_appended_ts=status_segment_receipt.receipt_ts,
        normalized_at=status_revision.normalized_at,
        available_at=status_revision.available_at,
        classified_at=status_revision.available_at + timedelta(milliseconds=50),
    )
    assert status_disposition.disposition_kind is (
        MessageDispositionKind.NORMALIZED_OBSERVATION
    )
    assert classified_status_derivation == status_derivation
    assert classified_status_revision == status_revision
    scenario.append(status_disposition, at=status_disposition.classified_at)

    price_segment = segment(
        price_policy,
        kline_bytes(),
        received_at=T0 + timedelta(minutes=1, milliseconds=200),
    )
    price_segment_receipt = scenario.append(
        price_segment,
        at=T0 + timedelta(minutes=1, milliseconds=400),
    )
    price_derivation, price_revision = normalize_bybit_v5_kline_message(
        adapter_policy=price_policy,
        segment=price_segment,
        message_receipt_id=price_segment.message_receipt_ids[0],
        source_member_key=placeholder.source_member_key,
        instrument_mapping_id=mapping.instrument_mapping_id,
        durably_appended_ts=price_segment_receipt.receipt_ts,
        normalized_at=price_segment_receipt.receipt_ts + timedelta(milliseconds=100),
        available_at=price_segment_receipt.receipt_ts + timedelta(milliseconds=200),
    )
    scenario.append(price_derivation, at=price_revision.available_at)
    cutoff_receipt = price_segment_receipt
    price_disposition: ProviderMessageDispositionV3 | None = None
    if append_bar_revision:
        scenario.append(price_revision)
        (
            price_disposition,
            classified_price_derivation,
            classified_price_revision,
        ) = build_bybit_v5_message_disposition(
            adapter_policy=price_policy,
            segment=price_segment,
            message_receipt_id=price_segment.message_receipt_ids[0],
            source_member_key=placeholder.source_member_key,
            instrument_mapping_id=mapping.instrument_mapping_id,
            durably_appended_ts=price_segment_receipt.receipt_ts,
            normalized_at=price_revision.normalized_at,
            available_at=price_revision.available_at,
            classified_at=price_revision.available_at + timedelta(milliseconds=50),
        )
        assert price_disposition.disposition_kind is (
            MessageDispositionKind.NORMALIZED_OBSERVATION
        )
        assert classified_price_derivation == price_derivation
        assert classified_price_revision == price_revision
        cutoff_receipt = scenario.append(
            price_disposition,
            at=price_disposition.classified_at,
        )

    extra_price_segment = None
    if append_extra_price_segment:
        extra_price_segment = segment(
            price_policy,
            kline_bytes(confirm=False, close="100.6"),
            sequence=2,
            received_at=T0 + timedelta(minutes=1, milliseconds=300),
            parent=price_segment,
        )
        cutoff_receipt = scenario.append(extra_price_segment)

    return {
        "artifact": artifact,
        "calendar": calendar,
        "action_protocol": action_protocol,
        "mapping": mapping,
        "price_policy": price_policy,
        "status_policy": instrument_status_policy,
        "placeholder": placeholder,
        "status_segment": status_segment,
        "status_derivation": status_derivation,
        "status_revision": status_revision,
        "status_disposition": status_disposition,
        "price_segment": price_segment,
        "price_segment_receipt": price_segment_receipt,
        "price_derivation": price_derivation,
        "price_revision": price_revision,
        "price_disposition": price_disposition,
        "dispositions": tuple(
            item for item in (status_disposition, price_disposition) if item is not None
        ),
        "extra_price_segment": extra_price_segment,
        "cutoff_receipt": cutoff_receipt,
        "knowledge_cutoff": T0 + timedelta(minutes=1, seconds=3),
    }


def make_prefix(
    scenario: LedgerScenario,
    state: dict[str, Any],
    *,
    include_extra_segment: bool = True,
    cutoff_receipt_hash: str | None = None,
    health: PrefixHealth = PrefixHealth.HEALTHY,
    health_reason_codes: tuple[str, ...] = (),
    unresolved_disposition_ids: tuple[str, ...] = (),
) -> EvidencePrefixV3:
    capture_segment_ids = [
        state["price_segment"].capture_segment_id,
        state["status_segment"].capture_segment_id,
    ]
    if include_extra_segment and state["extra_price_segment"] is not None:
        capture_segment_ids.append(state["extra_price_segment"].capture_segment_id)
    cutoff_receipt = state["cutoff_receipt"]
    price_revision = state["price_revision"]
    status_revision = state["status_revision"]
    return EvidencePrefixV3(
        adapter_policy_id=state["price_policy"].adapter_policy_id,
        supporting_adapter_policy_ids=(state["status_policy"].adapter_policy_id,),
        source_member_key=state["placeholder"].source_member_key,
        instrument_mapping_id=state["mapping"].instrument_mapping_id,
        ledger_id=scenario.ledger.ledger_id,
        cutoff_global_sequence=cutoff_receipt.global_sequence,
        cutoff_receipt_hash=(
            cutoff_receipt.receipt_hash
            if cutoff_receipt_hash is None
            else cutoff_receipt_hash
        ),
        knowledge_cutoff_ts=state["knowledge_cutoff"],
        capture_segment_ids=tuple(capture_segment_ids),
        message_disposition_ids=tuple(
            item.provider_message_disposition_id for item in state["dispositions"]
        ),
        observation_revision_ids=(
            price_revision.observation_revision_id,
            status_revision.observation_revision_id,
        ),
        active_observation_revision_ids=(
            price_revision.observation_revision_id,
            status_revision.observation_revision_id,
        ),
        status_observation_revision_ids=(status_revision.observation_revision_id,),
        unresolved_disposition_ids=unresolved_disposition_ids,
        vintage=PhysicalVintage.PROSPECTIVE_LIVE,
        health=health,
        health_reason_codes=health_reason_codes,
        event_time_watermark=T0 + timedelta(minutes=1),
        health_valid_until=T0 + timedelta(minutes=2),
        assembled_at=state["knowledge_cutoff"],
    )


def append_additional_price_disposition(
    scenario: LedgerScenario,
    state: dict[str, Any],
    raw_payload: bytes,
) -> ProviderMessageDispositionV3:
    capture = segment(
        state["price_policy"],
        raw_payload,
        sequence=2,
        received_at=T0 + timedelta(minutes=1, seconds=1),
        parent=state["price_segment"],
    )
    capture_receipt = scenario.append(
        capture,
        at=T0 + timedelta(minutes=1, seconds=1, milliseconds=100),
    )
    disposition, derivation, revision = build_bybit_v5_message_disposition(
        adapter_policy=state["price_policy"],
        segment=capture,
        message_receipt_id=capture.message_receipt_ids[0],
        source_member_key=state["placeholder"].source_member_key,
        instrument_mapping_id=state["mapping"].instrument_mapping_id,
        durably_appended_ts=capture_receipt.receipt_ts,
        normalized_at=capture_receipt.receipt_ts + timedelta(milliseconds=100),
        available_at=capture_receipt.receipt_ts + timedelta(milliseconds=100),
        classified_at=capture_receipt.receipt_ts + timedelta(milliseconds=100),
    )
    assert derivation is None
    assert revision is None
    disposition_receipt = scenario.append(
        disposition,
        at=disposition.classified_at,
    )
    state["extra_price_segment"] = capture
    state["dispositions"] = (*state["dispositions"], disposition)
    state["cutoff_receipt"] = disposition_receipt
    return disposition


def append_source_and_protocol(
    scenario: LedgerScenario,
    state: dict[str, Any],
    *,
    append_exact_proof: bool,
    prefix: EvidencePrefixV3 | None = None,
) -> dict[str, Any]:
    prefix = prefix or make_prefix(scenario, state)
    scenario.append(prefix, at=state["knowledge_cutoff"])
    member = replace(
        state["placeholder"],
        semantic_content_root=prefix.evidence_prefix_id,
        artifact_hash=prefix.raw_receipt_root,
        knowledge_cutoff_ts=state["knowledge_cutoff"],
    )
    scenario.append(member)
    price_policy = state["price_policy"]
    bundle = SourceBundleV3(
        source_dataset_id="physical-bybit-ledger-test",
        source_contract_id=price_policy.adapter_policy_id,
        source_schema_id=price_policy.source_schema_id,
        calendar_manifest_id=price_policy.calendar_manifest_id,
        universe_manifest_id=digest("physical-ledger-universe"),
        first_seen_policy_id=price_policy.availability_policy_id,
        revision_policy_id=price_policy.revision_policy_id,
        vintage_class="LIVE_FIRST_SEEN_CERTIFIED",
        knowledge_cutoff_ts=state["knowledge_cutoff"],
        source_member_ids=(member.source_member_id,),
    )
    scenario.append(bundle)
    source = source_manifest(
        source_dataset_id=bundle.source_dataset_id,
        source_contract_id=bundle.source_contract_id,
        source_schema_id=bundle.source_schema_id,
        source_content_root=bundle.source_bundle_id,
        first_seen_policy_id=bundle.first_seen_policy_id,
        revision_policy_id=bundle.revision_policy_id,
        calendar_manifest_id=bundle.calendar_manifest_id,
        universe_manifest_id=bundle.universe_manifest_id,
        vintage_class=bundle.vintage_class,
        knowledge_cutoff_ts=utc_iso(state["knowledge_cutoff"]),
    )
    evidence_registry = {
        state["artifact"].calendar_source_artifact_id: state["artifact"],
        state["calendar"].calendar_snapshot_id: state["calendar"],
        state["action_protocol"].action_protocol_id: state["action_protocol"],
        state["mapping"].instrument_mapping_id: state["mapping"],
        price_policy.adapter_policy_id: price_policy,
        state["status_policy"].adapter_policy_id: state["status_policy"],
        member.source_member_id: member,
        bundle.source_bundle_id: bundle,
    }
    protocol, slot, definition, schema, evidence_registry = governed_protocol_graph(
        source,
        member,
        bundle,
        evidence_registry,
    )
    old_schema_id = schema.feature_schema_id
    schema = replace(schema, frozen_at=state["knowledge_cutoff"])
    evidence_registry.pop(old_schema_id)
    evidence_registry[schema.feature_schema_id] = schema
    protocol = protocol_manifest(
        source,
        feature_schema_id=schema.feature_schema_id,
        action_protocol_id=state["action_protocol"].action_protocol_id,
        protocol_frozen_at=utc_iso(state["knowledge_cutoff"]),
    )
    selector = ObservationSelectionPolicyV3(
        dependency_slot_id=slot.dependency_slot_id,
        selection_mode=DependencySelectionMode.TRAILING_COMPLETED_OBSERVATIONS,
        anchor=SelectionAnchor.LATEST_COMPLETED_ASOF,
        interval_seconds=price_policy.base_interval_seconds,
        anchor_lag_intervals=0,
        requested_count=1,
        continuity_policy=ContinuityPolicy.STRICT_INTERVAL_GRID,
        maximum_age_seconds=slot.maximum_age_seconds,
        maximum_prefix_age_seconds=price_policy.stale_after_seconds,
        tie_break_policy="AVAILABLE_AT_THEN_REVISION_ID",
        frozen_at=state["knowledge_cutoff"],
    )
    evidence_registry[selector.observation_selection_policy_id] = selector
    scenario.append(slot)
    scenario.append(selector)
    revisions = {
        state["price_revision"].observation_revision_id: state["price_revision"],
        state["status_revision"].observation_revision_id: state["status_revision"],
    }
    proof = select_observation_revisions_v3(
        policy=selector,
        slot=slot,
        member=member,
        prefix=prefix,
        revisions=revisions,
        observation_cutoff_ts=state["knowledge_cutoff"],
        computed_at=state["knowledge_cutoff"],
    )
    if append_exact_proof:
        scenario.append(proof)
    scenario.append(definition)
    scenario.append(schema)
    scenario.append(source)
    scenario.append(protocol)

    price_revision = state["price_revision"]
    revision_values = dict(
        zip(price_revision.field_ids, price_revision.field_values, strict=True)
    )
    selected_values = tuple(revision_values[field] for field in slot.source_field_ids)
    dependency = InformationDependencyV3(
        dependency_slot_id=slot.dependency_slot_id,
        source_member_id=member.source_member_id,
        name="physical-completed-bar",
        source_id=price_revision.source_id,
        source_manifest_id=source.manifest_id,
        source_field_ids=slot.source_field_ids,
        observation_revision_id=price_revision.observation_revision_id,
        source_event_ts=price_revision.source_event_ts,
        bar_open_ts=price_revision.bar_open_ts,
        bar_close_ts=price_revision.bar_close_ts,
        source_publish_ts=price_revision.source_publish_ts,
        ingested_first_seen_ts=price_revision.durably_appended_ts,
        revision_received_ts=price_revision.durably_appended_ts,
        feature_available_ts=price_revision.available_at,
        value_digest=observation_value_digest(slot.source_field_ids, selected_values),
    )
    information, candidate, materialization, _, _, resolution = protocol_record_graph(
        protocol,
        source,
        evidence_registry,
        information_changes={
            "observation_cutoff_ts": state["knowledge_cutoff"],
            "assembled_at": state["knowledge_cutoff"],
            "dependencies": (dependency,),
        },
    )
    return {
        **state,
        "prefix": prefix,
        "member": member,
        "bundle": bundle,
        "source": source,
        "protocol": protocol,
        "slot": slot,
        "selector": selector,
        "proof": proof,
        "revisions": revisions,
        "information": information,
        "resolution": resolution,
        "candidate": candidate,
        "materialization": materialization,
    }


def test_complete_physical_path_passes_gate_promotes_candidate_and_verifies(
    tmp_path: Path,
) -> None:
    with physical_ledger(tmp_path) as scenario:
        state = append_observation_foundation(scenario)
        state = append_source_and_protocol(
            scenario,
            state,
            append_exact_proof=True,
        )
        scenario.append(state["information"], at=state["information"].assembled_at)
        gate = build_physical_evidence_gate_v3(
            information_set=state["information"],
            proofs=(state["proof"],),
            prefixes={state["prefix"].evidence_prefix_id: state["prefix"]},
            revisions=state["revisions"],
            gate_stage=PhysicalGateStage.DECISION_INPUT,
            evaluated_at=state["information"].assembled_at,
        )
        scenario.append(gate, at=gate.evaluated_at)
        scenario.append(state["resolution"], at=state["resolution"].resolved_at)
        scenario.append(
            state["candidate"], at=state["candidate"].candidate_available_ts
        )
        scenario.append(
            state["materialization"],
            at=state["materialization"].feature_available_ts,
        )

        report = scenario.ledger.verify()
        channel_counts = {root.channel: root.sequence for root in report.channel_roots}
        assert channel_counts[LedgerChannel.OBSERVATION] > 0
        assert report.object_count == report.receipt_count


def test_raw_observation_rejects_backdated_durable_clock(tmp_path: Path) -> None:
    with physical_ledger(tmp_path) as scenario:
        state = append_observation_foundation(
            scenario,
            append_bar_revision=False,
        )
        revision = state["price_revision"]
        tampered = replace(
            revision,
            durably_appended_ts=revision.durably_appended_ts
            + timedelta(milliseconds=1),
        )
        with pytest.raises(
            LedgerConflictError,
            match="durable clock differs from capture receipt",
        ):
            scenario.append(tampered)


def test_unverified_timeframe_aggregation_is_rejected_fail_closed(
    tmp_path: Path,
) -> None:
    with physical_ledger(tmp_path) as scenario:
        state = append_observation_foundation(scenario)
        malicious = replace(
            state["price_derivation"],
            derivation_kind=DerivationKind.TIMEFRAME_AGGREGATION,
            input_message_receipt_ids=(),
            input_observation_revision_ids=(
                state["price_revision"].observation_revision_id,
            ),
            transform_parameters_hash=digest("unverified-aggregation"),
            output_field_values=("100", "777", "99", "777", "12.25", "1230.5"),
            derived_at=state["price_revision"].available_at + timedelta(seconds=1),
        )
        with pytest.raises(LedgerConflictError, match="not authoritative"):
            scenario.append(malicious, at=malicious.derived_at)


@pytest.mark.parametrize("attack", ["omission", "cutoff-hash"])
def test_evidence_prefix_rejects_omission_and_cutoff_tampering(
    tmp_path: Path,
    attack: str,
) -> None:
    with physical_ledger(tmp_path) as scenario:
        state = append_observation_foundation(
            scenario,
            append_extra_price_segment=attack == "omission",
        )
        prefix = make_prefix(
            scenario,
            state,
            include_extra_segment=attack != "omission",
            cutoff_receipt_hash=(
                digest("tampered-cutoff-hash") if attack == "cutoff-hash" else None
            ),
        )
        expected = (
            "omits or adds an in-scope capture segment"
            if attack == "omission"
            else "cutoff hash differs from the ledger receipt"
        )
        with pytest.raises(LedgerConflictError, match=expected):
            scenario.append(prefix, at=state["knowledge_cutoff"])


def test_raw_message_accepts_only_one_disposition_semantic_head(
    tmp_path: Path,
) -> None:
    with physical_ledger(tmp_path) as scenario:
        state = append_observation_foundation(scenario)
        disposition = state["price_disposition"]
        assert isinstance(disposition, ProviderMessageDispositionV3)
        second_classification = replace(
            disposition,
            classified_at=disposition.classified_at + timedelta(microseconds=1),
        )
        with pytest.raises(
            LedgerConflictError,
            match="semantic compare-and-swap failed",
        ):
            scenario.append(
                second_classification,
                at=second_classification.classified_at,
            )


def test_evidence_prefix_rejects_message_disposition_omission(
    tmp_path: Path,
) -> None:
    with physical_ledger(tmp_path) as scenario:
        state = append_observation_foundation(scenario)
        prefix = make_prefix(scenario, state)
        omitted = replace(
            prefix,
            message_disposition_ids=prefix.message_disposition_ids[1:],
        )
        with pytest.raises(
            CanonicalizationError,
            match="classify every captured message exactly once",
        ):
            scenario.append(omitted, at=state["knowledge_cutoff"])


def test_neutral_control_disposition_is_covered_without_blocking_prefix(
    tmp_path: Path,
) -> None:
    with physical_ledger(tmp_path) as scenario:
        state = append_observation_foundation(scenario)
        control_payload = json.dumps(
            {
                "success": True,
                "ret_msg": "pong",
                "conn_id": "conn-1",
                "req_id": "heartbeat-1",
                "op": "ping",
            },
            separators=(",", ":"),
        ).encode()
        control = append_additional_price_disposition(
            scenario,
            state,
            control_payload,
        )
        assert control.disposition_kind is MessageDispositionKind.CONTROL_PONG

        prefix = make_prefix(scenario, state)
        scenario.append(prefix, at=state["knowledge_cutoff"])

        assert control.provider_message_disposition_id in (
            prefix.message_disposition_ids
        )
        assert prefix.unresolved_disposition_ids == ()
        assert prefix.health is PrefixHealth.HEALTHY


def test_exact_duplicate_occurrence_is_classified_without_a_second_observation(
    tmp_path: Path,
) -> None:
    with physical_ledger(tmp_path) as scenario:
        state = append_observation_foundation(scenario)
        duplicate_segment = segment(
            state["price_policy"],
            kline_bytes(),
            sequence=2,
            received_at=T0 + timedelta(minutes=1, seconds=1),
            parent=state["price_segment"],
        )
        capture_receipt = scenario.append(
            duplicate_segment,
            at=T0 + timedelta(minutes=1, seconds=1, milliseconds=100),
        )
        duplicate, derivation, revision = build_bybit_v5_message_disposition(
            adapter_policy=state["price_policy"],
            segment=duplicate_segment,
            message_receipt_id=duplicate_segment.message_receipt_ids[0],
            source_member_key=state["placeholder"].source_member_key,
            instrument_mapping_id=state["mapping"].instrument_mapping_id,
            durably_appended_ts=capture_receipt.receipt_ts,
            normalized_at=capture_receipt.receipt_ts + timedelta(milliseconds=100),
            available_at=capture_receipt.receipt_ts + timedelta(milliseconds=100),
            classified_at=capture_receipt.receipt_ts + timedelta(milliseconds=100),
            prior_normalized_occurrences=(
                (state["price_segment"], state["price_disposition"]),
            ),
        )
        assert duplicate.disposition_kind is MessageDispositionKind.EXACT_DUPLICATE
        assert derivation is None
        assert revision is None
        duplicate_receipt = scenario.append(
            duplicate,
            at=duplicate.classified_at,
        )
        state["extra_price_segment"] = duplicate_segment
        state["dispositions"] = (*state["dispositions"], duplicate)
        state["cutoff_receipt"] = duplicate_receipt

        prefix = make_prefix(scenario, state)
        scenario.append(prefix, at=state["knowledge_cutoff"])

        assert prefix.unresolved_disposition_ids == ()
        assert len(prefix.observation_revision_ids) == 2
        assert scenario.ledger.verify().object_count > 0


def test_provider_error_is_retained_as_blocker_and_forces_abstention(
    tmp_path: Path,
) -> None:
    with physical_ledger(tmp_path) as scenario:
        state = append_observation_foundation(scenario)
        error_payload = json.dumps(
            {
                "success": False,
                "ret_msg": "subscription failed",
                "conn_id": "conn-1",
                "req_id": "subscribe-2",
                "op": "subscribe",
            },
            separators=(",", ":"),
        ).encode()
        blocker = append_additional_price_disposition(
            scenario,
            state,
            error_payload,
        )
        assert blocker.disposition_kind is MessageDispositionKind.PROVIDER_ERROR
        prefix = make_prefix(
            scenario,
            state,
            health=PrefixHealth.DISCONNECTED,
            health_reason_codes=("unresolved-provider-error",),
            unresolved_disposition_ids=(blocker.provider_message_disposition_id,),
        )
        state = append_source_and_protocol(
            scenario,
            state,
            append_exact_proof=True,
            prefix=prefix,
        )

        assert state["proof"].status.value == "ABSTAIN"
        gate = build_physical_evidence_gate_v3(
            information_set=state["information"],
            proofs=(state["proof"],),
            prefixes={prefix.evidence_prefix_id: prefix},
            revisions=state["revisions"],
            gate_stage=PhysicalGateStage.DECISION_INPUT,
            evaluated_at=state["information"].assembled_at,
        )
        assert gate.verdict.value == "ABSTAIN"
        assert "physical-prefix-not-healthy" in gate.abstention_reason_codes


def test_physical_information_set_requires_registered_exact_proof(
    tmp_path: Path,
) -> None:
    with physical_ledger(tmp_path) as scenario:
        state = append_observation_foundation(scenario)
        state = append_source_and_protocol(
            scenario,
            state,
            append_exact_proof=False,
        )
        with pytest.raises(
            LedgerConflictError,
            match="requires one exact selection proof",
        ):
            scenario.append(state["information"])


def test_candidate_is_rejected_before_pass_physical_gate(tmp_path: Path) -> None:
    with physical_ledger(tmp_path) as scenario:
        state = append_observation_foundation(scenario)
        state = append_source_and_protocol(
            scenario,
            state,
            append_exact_proof=True,
        )
        scenario.append(state["information"], at=state["information"].assembled_at)
        scenario.append(state["resolution"], at=state["resolution"].resolved_at)
        with pytest.raises(
            LedgerConflictError,
            match="requires one PASS decision-input gate",
        ):
            scenario.append(state["candidate"])


@pytest.mark.parametrize("authority_kind", ["proof", "gate", "candidate"])
def test_physical_authority_receipt_must_precede_evidence_expiry(
    tmp_path: Path,
    authority_kind: str,
) -> None:
    with physical_ledger(tmp_path) as scenario:
        state = append_observation_foundation(scenario)
        state = append_source_and_protocol(
            scenario,
            state,
            append_exact_proof=authority_kind != "proof",
        )
        expiry = state["prefix"].health_valid_until
        if authority_kind == "proof":
            with pytest.raises(
                LedgerConflictError,
                match="authority receipt postdates evidence validity",
            ):
                scenario.append(state["proof"], at=expiry + timedelta(microseconds=1))
            return

        scenario.append(state["information"], at=state["information"].assembled_at)
        gate = build_physical_evidence_gate_v3(
            information_set=state["information"],
            proofs=(state["proof"],),
            prefixes={state["prefix"].evidence_prefix_id: state["prefix"]},
            revisions=state["revisions"],
            gate_stage=PhysicalGateStage.DECISION_INPUT,
            evaluated_at=state["information"].assembled_at,
        )
        if authority_kind == "gate":
            with pytest.raises(
                LedgerConflictError,
                match="authority receipt postdates evidence validity",
            ):
                scenario.append(gate, at=expiry + timedelta(microseconds=1))
            return

        scenario.append(gate, at=gate.evaluated_at)
        scenario.append(state["resolution"], at=state["resolution"].resolved_at)
        with pytest.raises(
            LedgerConflictError,
            match="authority receipt postdates evidence validity",
        ):
            scenario.append(
                state["candidate"],
                at=expiry + timedelta(microseconds=1),
            )


def test_gate_rejects_abstain_proof_from_another_cutoff(tmp_path: Path) -> None:
    with physical_ledger(tmp_path) as scenario:
        state = append_observation_foundation(scenario)
        state = append_source_and_protocol(
            scenario,
            state,
            append_exact_proof=True,
        )
        scenario.append(state["information"], at=state["information"].assembled_at)
        scenario.append(state["resolution"], at=state["resolution"].resolved_at)
        abstain_proof = select_observation_revisions_v3(
            policy=state["selector"],
            slot=state["slot"],
            member=state["member"],
            prefix=state["prefix"],
            revisions=state["revisions"],
            observation_cutoff_ts=state["knowledge_cutoff"] - timedelta(milliseconds=1),
            computed_at=state["knowledge_cutoff"],
        )
        scenario.append(abstain_proof)
        abstain_gate = build_physical_evidence_gate_v3(
            information_set=state["information"],
            proofs=(abstain_proof,),
            prefixes={state["prefix"].evidence_prefix_id: state["prefix"]},
            revisions=state["revisions"],
            evaluated_at=scenario.clock.value,
        )
        with pytest.raises(
            LedgerConflictError,
            match="does not bind every required selection proof",
        ):
            scenario.append(abstain_gate)


def test_legacy_v32_source_path_remains_compatible(tmp_path: Path) -> None:
    tmp_path.chmod(0o700)
    graph = governed_event_graph()
    with V3GovernanceLedger(
        tmp_path / "legacy-ledger.sqlite3",
        clock=lambda: LEDGER_NOW,
    ) as ledger:
        for ordinal, record in enumerate(graph["records"], start=1):
            ledger.append(record, idempotency_key=f"legacy-v32-{ordinal}")
        report = ledger.verify()
        observation_root = next(
            root
            for root in report.channel_roots
            if root.channel is LedgerChannel.OBSERVATION
        )
        assert observation_root.sequence == 0
        assert report.object_count == len(graph["records"])

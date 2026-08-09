from __future__ import annotations

import hashlib
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext

import pytest

from riskyieldmm.trading import (
    AmbiguityResolution,
    BarrierActivationV3,
    BarrierOutcomeV3,
    CanonicalizationError,
    CostComponentV3,
    DecisionEventV3,
    EligibilityDecisionV3,
    EligibilityVerdict,
    EntryScenario,
    EventDependenceAssignmentV3,
    ExecutionMode,
    InformationDependencyV3,
    InformationSetV3,
    LabelOutcomeV3,
    TradeSide,
    VintageClass,
    canonical_decimal,
    canonical_json_bytes,
    sha256_digest,
    strict_json_loads,
    utc_iso,
)
from riskyieldmm.trading.contracts import (
    FEATURE_VECTOR_ENCODING,
    CandidateFeatureMaterializationV3,
    PrimarySignalCandidateV3,
    StateCheckpointDependencyV3,
    decode_float64_be_hex_null_v1,
    encode_float64_be_hex_null_v1,
    float64_feature_vector_digest_v1,
)


def digest(name: str) -> str:
    return hashlib.sha256(name.encode()).hexdigest()


def dependency(**changes: object) -> InformationDependencyV3:
    values: dict[str, object] = {
        "dependency_slot_id": digest("ohlcv-slot"),
        "source_member_id": digest("btc-bybit-source-member"),
        "name": "BTCUSDT.1m.2026-07-14T09:00:00Z",
        "source_id": "bybit.linear.BTCUSDT.1m",
        "source_manifest_id": digest("source-manifest"),
        "source_field_ids": ("open", "high", "low", "close", "volume"),
        "observation_revision_id": digest("revision-1"),
        "source_event_ts": "2026-07-14T09:01:00Z",
        "bar_open_ts": "2026-07-14T09:00:00Z",
        "bar_close_ts": "2026-07-14T09:01:00Z",
        "source_publish_ts": "2026-07-14T09:01:01Z",
        "ingested_first_seen_ts": "2026-07-14T09:01:02Z",
        "revision_received_ts": "2026-07-14T09:01:02Z",
        "feature_available_ts": "2026-07-14T09:01:03Z",
        "value_digest": digest("ohlcv-row"),
    }
    values.update(changes)
    return InformationDependencyV3(**values)  # type: ignore[arg-type]


def state_dependency(**changes: object) -> StateCheckpointDependencyV3:
    values: dict[str, object] = {
        "dependency_slot_id": digest("cusum-state-slot"),
        "state_schema_id": digest("cusum-state-schema"),
        "state_cutoff_ts": "2026-07-14T09:01:00Z",
        "state_available_ts": "2026-07-14T09:01:03Z",
        "value_digest": digest("cusum-state-value"),
        "parent_state_checkpoint_id": digest("previous-cusum-state"),
    }
    values.update(changes)
    return StateCheckpointDependencyV3(**values)  # type: ignore[arg-type]


def information_set(**changes: object) -> InformationSetV3:
    values: dict[str, object] = {
        "asset_id": "BTC",
        "venue_id": "BYBIT",
        "contract_id": "BTCUSDT.LINEAR.PERP",
        "timeframe_id": "1m",
        "observation_cutoff_ts": "2026-07-14T09:01:03Z",
        "assembled_at": "2026-07-14T09:01:04Z",
        "source_manifest_id": digest("source-manifest"),
        "protocol_manifest_id": digest("protocol-manifest"),
        "calendar_manifest_id": digest("calendar-manifest"),
        "feature_schema_id": digest("feature-schema"),
        "dependencies": (dependency(),),
        "state_dependencies": (state_dependency(),),
        "vintage_class": VintageClass.LIVE_FIRST_SEEN_CERTIFIED,
        "point_in_time_certified": True,
        "certification_blockers": (),
        "data_quality_flags": (),
        "universe_snapshot_id": digest("universe-snapshot"),
    }
    values.update(changes)
    return InformationSetV3(**values)  # type: ignore[arg-type]


def test_information_set_rejects_dependency_from_another_source_manifest() -> None:
    with pytest.raises(
        CanonicalizationError,
        match="every dependency source_manifest_id must match the information set",
    ):
        information_set(
            dependencies=(
                dependency(source_manifest_id=digest("different-source-manifest")),
            )
        )


def test_information_dependency_preserves_semantic_source_field_order() -> None:
    first = dependency(source_field_ids=("open", "close"))
    reversed_order = dependency(source_field_ids=("close", "open"))

    assert first.source_field_ids == ("open", "close")
    assert reversed_order.source_field_ids == ("close", "open")
    assert first.dependency_id != reversed_order.dependency_id


def candidate(
    info: InformationSetV3 | None = None,
    **changes: object,
) -> PrimarySignalCandidateV3:
    info = information_set() if info is None else info
    values: dict[str, object] = {
        "primary_signal_id": "online-cusum",
        "primary_signal_version": "v3",
        "primary_signal_policy_id": digest("signal-policy"),
        "signal_ts": "2026-07-14T09:01:03Z",
        "side": TradeSide.LONG,
        "candidate_available_ts": "2026-07-14T09:01:05Z",
        "entry_reference": "100",
        "earliest_order_submission_ts": "2026-07-14T09:01:09Z",
        "earliest_entry_ts": "2026-07-14T09:02:00Z",
        "entry_expiry_ts": "2026-07-14T09:02:00Z",
        "action_protocol_id": digest("action-protocol"),
        "action_resolution_id": digest("action-resolution"),
        "action_resolution_record_hash": digest("action-resolution-record"),
        "executable_contract_id": "BTCUSDT.LINEAR.PERP",
        "label_protocol_id": digest("label-protocol"),
        "entry_scenario": EntryScenario.NEXT_SCHEDULED_BASE_BAR_OPEN,
        "barrier_policy_id": digest("barrier-policy"),
        "cost_scenario_id": digest("cost-scenario"),
        "risk_unit": "10",
        "stop_r_multiple": "1",
        "target_r_multiple": "2",
        "max_holding_seconds": 60,
        "estimated_roundtrip_cost_bps": "3",
    }
    values.update(changes)
    return PrimarySignalCandidateV3.create(
        information_set=info,
        **values,  # type: ignore[arg-type]
    )


def materialization(
    info: InformationSetV3 | None = None,
    candidate_record: PrimarySignalCandidateV3 | None = None,
    **changes: object,
) -> CandidateFeatureMaterializationV3:
    info = information_set() if info is None else info
    candidate_record = candidate(info) if candidate_record is None else candidate_record
    values: dict[str, object] = {
        "feature_values": tuple(
            encode_float64_be_hex_null_v1(value) for value in (1.5, None, -2.0)
        ),
        "feature_available_ts": "2026-07-14T09:01:06Z",
    }
    values.update(changes)
    return CandidateFeatureMaterializationV3.create(
        information_set=info,
        candidate=candidate_record,
        **values,  # type: ignore[arg-type]
    )


def eligibility(
    info: InformationSetV3 | None = None,
    candidate_record: PrimarySignalCandidateV3 | None = None,
    materialization_record: CandidateFeatureMaterializationV3 | None = None,
    **changes: object,
) -> EligibilityDecisionV3:
    info = information_set() if info is None else info
    candidate_record = candidate(info) if candidate_record is None else candidate_record
    materialization_record = (
        materialization(info, candidate_record)
        if materialization_record is None
        else materialization_record
    )
    values: dict[str, object] = {
        "eligibility_policy_id": digest("eligibility-policy"),
        "evaluated_at": "2026-07-14T09:01:07Z",
        "verdict": EligibilityVerdict.ELIGIBLE,
        "reason_codes": (),
    }
    values.update(changes)
    return EligibilityDecisionV3.create(
        information_set=info,
        candidate=candidate_record,
        materialization=materialization_record,
        **values,  # type: ignore[arg-type]
    )


def event(
    info: InformationSetV3 | None = None,
    eligibility_record: EligibilityDecisionV3 | None = None,
    candidate_record: PrimarySignalCandidateV3 | None = None,
    materialization_record: CandidateFeatureMaterializationV3 | None = None,
    **changes: object,
) -> DecisionEventV3:
    info = information_set() if info is None else info
    decision_ts = changes.pop("decision_ts", "2026-07-14T09:01:08Z")
    candidate_record = (
        candidate(info, **changes) if candidate_record is None else candidate_record
    )
    materialization_record = (
        materialization(info, candidate_record)
        if materialization_record is None
        else materialization_record
    )
    eligibility_record = (
        eligibility(info, candidate_record, materialization_record)
        if eligibility_record is None
        else eligibility_record
    )
    return DecisionEventV3.create(
        information_set=info,
        candidate=candidate_record,
        materialization=materialization_record,
        eligibility=eligibility_record,
        decision_ts=decision_ts,
    )


def barrier_activation(decision: DecisionEventV3 | None = None) -> BarrierActivationV3:
    decision = event() if decision is None else decision
    return BarrierActivationV3.create(
        event=decision,
        entry_evidence_revision_id=digest("entry-evidence"),
        actual_entry_ts="2026-07-14T09:02:00Z",
        entry_price="100",
        evidence_available_at="2026-07-14T09:02:00Z",
        activated_at="2026-07-14T09:02:00Z",
    )


def filled_outcome(
    decision: DecisionEventV3 | None = None,
    **changes: object,
) -> LabelOutcomeV3:
    decision = event() if decision is None else decision
    activation = barrier_activation(decision)
    fee = CostComponentV3(
        name="fees",
        bps="1",
        known_at="2026-07-14T09:02:31Z",
        evidence_id=digest("fee-evidence"),
    )
    spread = CostComponentV3(
        name="spread_slippage",
        bps="2",
        known_at="2026-07-14T09:02:31Z",
        evidence_id=digest("spread-evidence"),
    )
    values: dict[str, object] = {
        "decision_event_id": decision.decision_event_id,
        "label_protocol_id": decision.label_protocol_id,
        "cost_scenario_id": decision.cost_scenario_id,
        "execution_mode": ExecutionMode.HISTORICAL_NOMINAL_SCENARIO,
        "outcome": BarrierOutcomeV3.TP_FIRST,
        "label_interval_start_ts": "2026-07-14T09:02:00Z",
        "label_interval_end_ts": "2026-07-14T09:03:00Z",
        "outcome_ts": "2026-07-14T09:02:30Z",
        "barrier_trigger_ts": "2026-07-14T09:02:30Z",
        "barrier_trigger_price": "120",
        "barrier_trigger_evidence_revision_id": digest("barrier-trigger-evidence"),
        "evidence_available_at": "2026-07-14T09:02:31Z",
        "label_known_ts": "2026-07-14T09:03:01Z",
        "path_evidence_root": digest("path-evidence"),
        "vintage_class": decision.vintage_class,
        "barrier_activation_id": activation.barrier_activation_id,
        "barrier_activation_record_hash": activation.record_hash,
        "cost_components": (fee, spread),
        "actual_entry_ts": "2026-07-14T09:02:00Z",
        "entry_price": "100",
        "exit_price": "120",
        "stop_price": "90",
        "target_price": "120",
        "entry_evidence_revision_id": digest("entry-evidence"),
        "exit_evidence_revision_id": digest("exit-evidence"),
        "gross_return_bps": "2000",
        "net_return_bps": "1997",
        "r_multiple": "2",
        "mae_bps": "50",
        "mfe_bps": "2000",
        "gap_loss_bps": "0",
    }
    values.update(changes)
    resolved_outcome = BarrierOutcomeV3(values["outcome"])
    if resolved_outcome is BarrierOutcomeV3.TP_FIRST:
        if "barrier_trigger_ts" not in changes:
            values["barrier_trigger_ts"] = values["outcome_ts"]
        if "barrier_trigger_price" not in changes:
            values["barrier_trigger_price"] = values["target_price"]
        if "barrier_trigger_evidence_revision_id" not in changes:
            values["barrier_trigger_evidence_revision_id"] = digest(
                "barrier-trigger-evidence"
            )
    elif resolved_outcome is BarrierOutcomeV3.SL_FIRST:
        if "barrier_trigger_ts" not in changes:
            values["barrier_trigger_ts"] = values["outcome_ts"]
        if "barrier_trigger_price" not in changes:
            values["barrier_trigger_price"] = values["stop_price"]
        if "barrier_trigger_evidence_revision_id" not in changes:
            values["barrier_trigger_evidence_revision_id"] = digest(
                "barrier-trigger-evidence"
            )
    else:
        for field_name in (
            "barrier_trigger_ts",
            "barrier_trigger_price",
            "barrier_trigger_evidence_revision_id",
        ):
            if field_name not in changes:
                values[field_name] = None
    return LabelOutcomeV3(**values)  # type: ignore[arg-type]


def no_fill_outcome(decision: DecisionEventV3 | None = None) -> LabelOutcomeV3:
    decision = event() if decision is None else decision
    return LabelOutcomeV3(
        decision_event_id=decision.decision_event_id,
        label_protocol_id=decision.label_protocol_id,
        cost_scenario_id=decision.cost_scenario_id,
        execution_mode=ExecutionMode.HISTORICAL_NOMINAL_SCENARIO,
        outcome=BarrierOutcomeV3.NO_FILL,
        label_interval_start_ts=decision.earliest_entry_ts,
        label_interval_end_ts=decision.entry_expiry_ts,
        outcome_ts=decision.entry_expiry_ts,
        barrier_trigger_ts=None,
        barrier_trigger_price=None,
        barrier_trigger_evidence_revision_id=None,
        evidence_available_at=decision.entry_expiry_ts,
        label_known_ts=decision.entry_expiry_ts + timedelta(seconds=1),
        path_evidence_root=digest("no-fill-path"),
        vintage_class=decision.vintage_class,
    )


def test_canonical_json_golden_vector_and_map_order() -> None:
    left = {"z": [1, True, None], "a": "żółć"}
    right = {"a": "żółć", "z": [1, True, None]}

    expected = '{"a":"żółć","z":[1,true,null]}'.encode()
    assert canonical_json_bytes(left) == expected
    assert canonical_json_bytes(right) == expected
    assert (
        sha256_digest(left)
        == "3596b2b8105ef391748acaa9bf90327189baeab678564a00a3d35cc8c5b0b3a1"
    )


@pytest.mark.parametrize(
    "raw",
    [
        '{"x":1,"x":2}',
        '{"x":0.1}',
        '{"x":NaN}',
        '{"x":Infinity}',
    ],
)
def test_strict_json_rejects_ambiguous_numbers_and_duplicate_keys(raw: str) -> None:
    with pytest.raises(CanonicalizationError):
        strict_json_loads(raw)


def test_canonical_json_rejects_float_unsafe_integer_and_cycle() -> None:
    with pytest.raises(CanonicalizationError):
        canonical_json_bytes({"x": 0.1})
    with pytest.raises(CanonicalizationError):
        canonical_json_bytes({"x": 2**53})
    cycle: list[object] = []
    cycle.append(cycle)
    with pytest.raises(CanonicalizationError):
        canonical_json_bytes(cycle)


@pytest.mark.parametrize("value", ["-0", "-0.0", -0.0, Decimal("-0")])
def test_decimal_rejects_negative_zero(value: object) -> None:
    with pytest.raises(CanonicalizationError):
        canonical_decimal(value, field="value")  # type: ignore[arg-type]


def test_decimal_normalization_is_exact_and_non_exponent() -> None:
    assert canonical_decimal("1.000", field="value") == "1"
    assert canonical_decimal("1e-7", field="value") == "0.0000001"
    assert canonical_decimal("1200e2", field="value") == "120000"
    assert canonical_decimal(Decimal("0e-999999999"), field="value") == "0"


def test_timestamp_policy_rejects_nanoseconds_naive_and_non_rfc3339() -> None:
    for value in (
        "2026-07-14T09:00:00.1234567Z",
        "2026-07-14 09:00:00Z",
        "2026-07-14T09:00:00",
        "2026-07-14T09:00:00,1Z",
    ):
        with pytest.raises(CanonicalizationError):
            utc_iso(value)
    assert utc_iso("2026-07-14T11:00:00+02:00") == "2026-07-14T09:00:00Z"


def test_non_nfc_identifier_is_rejected() -> None:
    with pytest.raises(CanonicalizationError, match="NFC"):
        dependency(name="e\u0301")


def test_datetime_subclasses_cannot_hide_submicrosecond_precision() -> None:
    pandas = pytest.importorskip("pandas")
    timestamp = pandas.Timestamp("2026-07-14T09:00:00.123456789Z")
    with pytest.raises(CanonicalizationError, match="subclass"):
        utc_iso(timestamp)


def test_dependency_round_trip_and_identity_tamper_detection() -> None:
    item = dependency()
    assert InformationDependencyV3.from_mapping(item.as_dict()) == item
    tampered = item.as_dict()
    tampered["value_digest"] = digest("tampered")
    with pytest.raises(CanonicalizationError, match="dependency_id"):
        InformationDependencyV3.from_mapping(tampered)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("bar_open_ts", "2026-07-14T09:01:01Z"),
        ("bar_open_ts", "2026-07-14T09:01:00Z"),
        ("source_event_ts", "2026-07-14T08:59:59Z"),
        ("source_event_ts", "2026-07-14T09:01:01Z"),
        ("source_publish_ts", "2026-07-14T09:00:59Z"),
        ("revision_received_ts", "2026-07-14T09:01:01Z"),
        ("feature_available_ts", "2026-07-14T09:01:01Z"),
    ],
)
def test_dependency_rejects_impossible_clocks(field: str, value: str) -> None:
    with pytest.raises(CanonicalizationError):
        dependency(**{field: value})


def test_dependency_rejects_future_publication_poison() -> None:
    with pytest.raises(CanonicalizationError, match="source_publish_ts"):
        dependency(source_publish_ts="2026-07-15T09:01:01Z")


def test_dependency_without_publish_clock_still_rejects_future_event() -> None:
    with pytest.raises(CanonicalizationError, match="ingested_first_seen_ts"):
        dependency(
            source_publish_ts=None,
            ingested_first_seen_ts="2026-07-14T09:00:59Z",
        )


def test_state_dependency_round_trip_parent_and_clock_contract() -> None:
    item = state_dependency()
    assert StateCheckpointDependencyV3.from_mapping(item.as_dict()) == item
    with pytest.raises(CanonicalizationError, match="state_cutoff_ts"):
        state_dependency(state_cutoff_ts="2026-07-14T09:01:04Z")
    with pytest.raises(CanonicalizationError, match="does not match canonical content"):
        payload = item.as_dict()
        payload["state_checkpoint_id"] = digest("forged-checkpoint-id")
        StateCheckpointDependencyV3.from_mapping(payload)


@pytest.mark.parametrize(
    "value",
    [False, 1, Decimal("1"), float("nan"), float("inf"), -0.0],
)
def test_binary64_feature_encoding_rejects_ambiguous_values(value: object) -> None:
    with pytest.raises(CanonicalizationError):
        encode_float64_be_hex_null_v1(value)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0.0, "0000000000000000"),
        (1.5, "3ff8000000000000"),
        (-0.5, "bfe0000000000000"),
        (float.fromhex("0x0.0000000000001p-1022"), "0000000000000001"),
        (float.fromhex("0x1.fffffffffffffp+1023"), "7fefffffffffffff"),
    ],
)
def test_binary64_feature_encoding_golden_bits(value: float, expected: str) -> None:
    assert encode_float64_be_hex_null_v1(value) == expected
    assert decode_float64_be_hex_null_v1(expected) == value


def test_binary64_feature_encoding_null_and_invalid_bits() -> None:
    assert encode_float64_be_hex_null_v1(None) is None
    assert decode_float64_be_hex_null_v1(None) is None
    for invalid in ("3FF8000000000000", "abc", "7ff8000000000000", "8000000000000000"):
        with pytest.raises(CanonicalizationError):
            decode_float64_be_hex_null_v1(invalid)


def test_information_set_identity_separates_semantics_from_attestation() -> None:
    first = information_set()
    second = information_set(
        assembled_at="2026-07-14T09:01:04.500000Z",
    )
    assert first.information_set_id == second.information_set_id
    assert first.record_hash != second.record_hash

    changed_source = information_set(
        dependencies=(
            dependency(
                observation_revision_id=digest("revision-2"),
                value_digest=digest("ohlcv-row-v2"),
            ),
        )
    )
    assert first.information_set_id != changed_source.information_set_id


def test_information_set_fails_closed_on_late_dependency_and_keeps_member_identity() -> (
    None
):
    with pytest.raises(CanonicalizationError, match="became available"):
        information_set(
            dependencies=(dependency(feature_available_ts="2026-07-14T09:01:04Z"),)
        )
    alternate_member = information_set(
        dependencies=(
            dependency(
                source_member_id=digest("other-member"),
            ),
        )
    )
    assert alternate_member.dependencies[0].source_member_id == digest("other-member")
    with pytest.raises(
        CanonicalizationError, match="state checkpoint became available"
    ):
        information_set(
            state_dependencies=(
                state_dependency(state_available_ts="2026-07-14T09:01:04Z"),
            )
        )


def test_information_set_can_be_state_only_when_the_schema_allows_it() -> None:
    item = information_set(dependencies=(), state_dependencies=(state_dependency(),))

    assert item.dependencies == ()
    assert len(item.state_dependencies) == 1
    assert InformationSetV3.from_mapping(item.as_dict()) == item


def test_certification_rules_do_not_retroactively_certify_nominal_history() -> None:
    with pytest.raises(CanonicalizationError, match="NOMINAL_CURRENT_REVISION"):
        information_set(vintage_class=VintageClass.NOMINAL_CURRENT_REVISION)
    nominal = information_set(
        vintage_class=VintageClass.NOMINAL_CURRENT_REVISION,
        point_in_time_certified=False,
        certification_blockers=("HISTORICAL_FIRST_SEEN_UNAVAILABLE",),
    )
    assert not nominal.point_in_time_certified


def test_information_set_is_frozen_and_round_trips_exactly() -> None:
    item = information_set()
    with pytest.raises(FrozenInstanceError):
        item.asset_id = "ETH"  # type: ignore[misc]
    assert InformationSetV3.from_mapping(item.as_dict()) == item
    unknown = item.as_dict()
    unknown["future_price"] = "999"
    with pytest.raises(CanonicalizationError, match="unknown"):
        InformationSetV3.from_mapping(unknown)


def test_eligibility_factory_propagates_graph_and_rejects_mismatch() -> None:
    info = information_set()
    primary = candidate(info)
    features = materialization(info, primary)
    item = eligibility(info, primary, features)
    item.validate_against(info, primary, features)
    invalid = replace(
        item,
        observation_cutoff_ts=datetime(2026, 7, 14, 8, tzinfo=timezone.utc),
    )
    with pytest.raises(CanonicalizationError, match="cutoff differs"):
        invalid.validate_against(info, primary, features)
    with pytest.raises(CanonicalizationError, match="features were available"):
        eligibility(info, evaluated_at="2026-07-14T09:01:03Z")


def test_candidate_identity_excludes_availability_attestation_but_record_binds_it() -> (
    None
):
    info = information_set()
    first = candidate(info)
    later = candidate(info, candidate_available_ts="2026-07-14T09:01:05.500000Z")
    assert first.primary_signal_candidate_id == later.primary_signal_candidate_id
    assert first.record_hash != later.record_hash
    assert PrimarySignalCandidateV3.from_mapping(first.as_dict()) == first
    tampered = first.as_dict()
    tampered["candidate_available_ts"] = "2026-07-14T09:01:05.500000Z"
    with pytest.raises(CanonicalizationError, match="record_hash"):
        PrimarySignalCandidateV3.from_mapping(tampered)


def test_long_and_short_candidates_share_information_but_never_candidate_graph() -> (
    None
):
    info = information_set()
    long_candidate = candidate(info, side=TradeSide.LONG)
    short_candidate = candidate(info, side=TradeSide.SHORT)
    assert long_candidate.information_set_id == short_candidate.information_set_id
    assert (
        long_candidate.primary_signal_candidate_id
        != short_candidate.primary_signal_candidate_id
    )
    long_features = materialization(info, long_candidate)
    short_features = materialization(info, short_candidate)
    assert (
        long_features.candidate_feature_materialization_key
        != short_features.candidate_feature_materialization_key
    )
    long_eligibility = eligibility(info, long_candidate, long_features)
    with pytest.raises(CanonicalizationError, match="supplied candidate"):
        long_eligibility.validate_against(info, short_candidate, short_features)


def test_materialization_binds_exact_ordered_vector_and_detects_tamper() -> None:
    info = information_set()
    primary = candidate(info)
    first = materialization(info, primary)
    swapped_values = (
        first.feature_values[2],
        first.feature_values[1],
        first.feature_values[0],
    )
    swapped = materialization(info, primary, feature_values=swapped_values)
    assert first.feature_vector_digest != swapped.feature_vector_digest
    assert (
        first.candidate_feature_materialization_id
        != swapped.candidate_feature_materialization_id
    )
    assert CandidateFeatureMaterializationV3.from_mapping(first.as_dict()) == first
    tampered = first.as_dict()
    tampered["feature_values"] = list(swapped_values)
    with pytest.raises(CanonicalizationError, match="feature_vector_digest"):
        CandidateFeatureMaterializationV3.from_mapping(tampered)
    assert first.feature_vector_encoding == FEATURE_VECTOR_ENCODING
    assert first.feature_vector_digest == float64_feature_vector_digest_v1(
        feature_schema_id=info.feature_schema_id,
        feature_values=first.feature_values,
    )
    null_moved = (first.feature_values[0], first.feature_values[2], None)
    assert first.feature_vector_digest != float64_feature_vector_digest_v1(
        feature_schema_id=info.feature_schema_id,
        feature_values=null_moved,
    )
    assert first.feature_vector_digest != float64_feature_vector_digest_v1(
        feature_schema_id=digest("different-feature-schema"),
        feature_values=first.feature_values,
    )


def test_complete_predecision_clock_chain_fails_closed() -> None:
    info = information_set()
    with pytest.raises(CanonicalizationError, match="before the information set"):
        candidate(info, candidate_available_ts="2026-07-14T09:01:03Z")
    with pytest.raises(CanonicalizationError, match="earliest_order_submission_ts"):
        candidate(info, candidate_available_ts="2026-07-14T09:01:10Z")

    primary = candidate(info)
    with pytest.raises(CanonicalizationError, match="before the candidate"):
        materialization(
            info,
            primary,
            feature_available_ts="2026-07-14T09:01:04Z",
        )
    features = materialization(info, primary)
    eligible = eligibility(info, primary, features)
    with pytest.raises(CanonicalizationError, match="eligibility_evaluated_at"):
        event(
            info,
            eligible,
            primary,
            features,
            decision_ts="2026-07-14T09:01:06Z",
        )
    with pytest.raises(CanonicalizationError, match="earliest_order_submission_ts"):
        event(
            info,
            eligible,
            primary,
            features,
            decision_ts="2026-07-14T09:01:10Z",
        )


def test_eligibility_reason_contract() -> None:
    info = information_set()
    with pytest.raises(CanonicalizationError, match="must not carry"):
        eligibility(info, reason_codes=("STALE",))
    abstain = eligibility(
        info,
        verdict=EligibilityVerdict.ABSTAIN_DATA,
        reason_codes=("STALE",),
    )
    assert abstain.verdict is EligibilityVerdict.ABSTAIN_DATA


def test_event_factory_propagates_linked_state_and_round_trips() -> None:
    info = information_set()
    primary = candidate(info)
    features = materialization(info, primary)
    eligible = eligibility(info, primary, features)
    item = event(info, eligible, primary, features)
    item.validate_against(info, primary, features, eligible)
    assert item.primary_signal_candidate_id == primary.primary_signal_candidate_id
    assert item.certification_blockers == info.certification_blockers
    assert DecisionEventV3.from_mapping(item.as_dict()) == item


def test_event_rejects_noneligible_or_mismatched_candidate_graph() -> None:
    info = information_set()
    primary = candidate(info)
    features = materialization(info, primary)
    rejected = eligibility(
        info,
        primary,
        features,
        verdict=EligibilityVerdict.INELIGIBLE,
        reason_codes=("CLOSED_MARKET",),
    )
    with pytest.raises(CanonicalizationError, match="ELIGIBLE"):
        event(info, rejected, primary, features)

    valid = eligibility(info, primary, features)
    raw = event(info, valid, primary, features)
    invalid = replace(
        raw,
        primary_signal_candidate_id=digest("different-candidate"),
    )
    with pytest.raises(CanonicalizationError, match="different candidate"):
        invalid.validate_against(info, primary, features, valid)

    wrong_geometry = replace(raw, target_r_multiple="3")
    with pytest.raises(CanonicalizationError, match="target_r_multiple"):
        wrong_geometry.validate_against(info, primary, features, valid)


def test_event_enforces_assembly_and_strict_pre_entry_sequence() -> None:
    with pytest.raises(CanonicalizationError, match="assembly"):
        event(decision_ts="2026-07-14T09:01:03Z")
    with pytest.raises(CanonicalizationError, match="must precede"):
        event(
            earliest_order_submission_ts="2026-07-14T09:02:00Z",
            earliest_entry_ts="2026-07-14T09:02:00Z",
        )


def test_event_identity_contains_policy_but_never_later_outcome() -> None:
    decision = event()
    outcome = filled_outcome(decision)
    original_id = decision.decision_event_id
    corrected = replace(
        outcome,
        mae_bps="60",
        supersedes_label_outcome_id=outcome.label_outcome_id,
    )
    assert corrected.label_outcome_id != outcome.label_outcome_id
    assert decision.decision_event_id == original_id
    changed_policy = event(barrier_policy_id=digest("barrier-policy-v2"))
    assert changed_policy.decision_event_id != original_id


def test_decision_event_key_allows_only_one_decision_per_eligibility() -> None:
    first = event(decision_ts="2026-07-14T09:01:08Z")
    later_attestation = event(decision_ts="2026-07-14T09:01:08.500000Z")

    assert first.decision_event_key == later_attestation.decision_event_key
    assert first.decision_event_id != later_attestation.decision_event_id


def test_filled_outcome_round_trip_cost_math_and_graph() -> None:
    decision = event()
    activation = barrier_activation(decision)
    outcome = filled_outcome(decision)
    activation.validate_against(decision)
    outcome.validate_against(decision, activation)
    assert outcome.total_cost_bps == "3"
    assert outcome.holding_duration_microseconds == 30_000_000
    assert LabelOutcomeV3.from_mapping(outcome.as_dict()) == outcome


def test_outcome_rejects_wrong_cost_math_and_unknown_population_metadata() -> None:
    with pytest.raises(CanonicalizationError, match="minus itemized costs"):
        filled_outcome(net_return_bps="1998")
    payload = filled_outcome().as_dict()
    payload["concurrency"] = 2
    with pytest.raises(CanonicalizationError, match="unknown"):
        LabelOutcomeV3.from_mapping(payload)


def test_outcome_graph_rejects_horizon_mode_and_economic_inconsistency() -> None:
    decision = event()
    activation = barrier_activation(decision)
    too_late = filled_outcome(
        decision,
        label_interval_end_ts="2026-07-14T09:04:00Z",
    )
    with pytest.raises(CanonicalizationError, match="holding horizon"):
        too_late.validate_against(decision, activation)
    wrong_mode = filled_outcome(decision, execution_mode=ExecutionMode.LIVE_ACTUAL)
    with pytest.raises(CanonicalizationError, match="entry scenario"):
        wrong_mode.validate_against(decision, activation)
    inverted = filled_outcome(decision, stop_price="110")
    with pytest.raises(CanonicalizationError, match="barrier activation"):
        inverted.validate_against(decision, activation)
    wrong_sign = filled_outcome(
        decision,
        gross_return_bps="-2000",
        net_return_bps="-2003",
    )
    with pytest.raises(CanonicalizationError, match="sign disagrees"):
        wrong_sign.validate_against(decision, activation)


def test_timeout_cannot_be_known_before_frozen_horizon() -> None:
    decision = event()
    activation = barrier_activation(decision)
    early = filled_outcome(decision, outcome=BarrierOutcomeV3.TIMEOUT)
    with pytest.raises(CanonicalizationError, match="holding deadline"):
        early.validate_against(decision, activation)


def test_exact_return_and_r_multiple_are_recomputed() -> None:
    decision = event()
    activation = barrier_activation(decision)
    overstated = filled_outcome(
        decision,
        gross_return_bps="9999",
        net_return_bps="9996",
        r_multiple="999",
    )
    with pytest.raises(CanonicalizationError, match="does not match"):
        overstated.validate_against(decision, activation)


def test_no_fill_is_distinct_and_matures_at_entry_expiry() -> None:
    decision = event()
    outcome = no_fill_outcome(decision)
    outcome.validate_against(decision)
    with pytest.raises(CanonicalizationError, match="fill/return"):
        replace(outcome, entry_price="100")


def test_persisted_parser_rejects_float_even_if_constructor_normalizes_it() -> None:
    decision = event(risk_unit=10.0)
    assert decision.risk_unit == "10"
    payload = decision.as_dict()
    payload["risk_unit"] = 10.0
    with pytest.raises(CanonicalizationError, match="floating-point"):
        DecisionEventV3.from_mapping(payload)


def test_barrier_activation_freezes_exact_pre_outcome_geometry() -> None:
    decision = event()
    activation = barrier_activation(decision)
    assert activation.stop_price == "90"
    assert activation.target_price == "120"
    assert BarrierActivationV3.from_mapping(activation.as_dict()) == activation
    hindsight = replace(activation, target_price="130")
    with pytest.raises(CanonicalizationError, match="frozen event geometry"):
        hindsight.validate_against(decision)


def test_barrier_outcome_path_cannot_begin_before_activation() -> None:
    decision = event()
    activation = barrier_activation(decision)
    delayed = replace(
        activation,
        evidence_available_at=datetime(2026, 7, 14, 9, 2, 10, tzinfo=timezone.utc),
        activated_at=datetime(2026, 7, 14, 9, 2, 20, tzinfo=timezone.utc),
    )
    outcome = replace(
        filled_outcome(decision),
        barrier_activation_record_hash=delayed.record_hash,
    )
    with pytest.raises(CanonicalizationError, match="barriers become active"):
        outcome.validate_against(decision, delayed)
    delayed_valid = replace(
        outcome,
        label_interval_start_ts=delayed.activated_at,
    )
    delayed_valid.validate_against(decision, delayed)


def test_ambiguous_outcome_requires_conservative_bounds() -> None:
    decision = event()
    activation = barrier_activation(decision)
    with pytest.raises(CanonicalizationError, match="requires conservative"):
        filled_outcome(decision, outcome=BarrierOutcomeV3.AMBIGUOUS)
    false_conservative = filled_outcome(
        decision,
        outcome=BarrierOutcomeV3.AMBIGUOUS,
        ambiguity_resolution=AmbiguityResolution.CONSERVATIVE_LOWER_BOUND,
        gross_return_lower_bound_bps="2000",
        gross_return_upper_bound_bps="2100",
    )
    with pytest.raises(CanonicalizationError, match="conservative exit_price"):
        false_conservative.validate_against(decision, activation)
    ambiguous = filled_outcome(
        decision,
        outcome=BarrierOutcomeV3.AMBIGUOUS,
        ambiguity_resolution=AmbiguityResolution.CONSERVATIVE_LOWER_BOUND,
        exit_price="90",
        gross_return_bps="-1000",
        net_return_bps="-1003",
        r_multiple="-1",
        gross_return_lower_bound_bps="-1000",
        gross_return_upper_bound_bps="2000",
    )
    ambiguous.validate_against(decision, activation)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        (
            {"barrier_trigger_price": "119"},
            "trigger price did not reach the frozen target",
        ),
        (
            {
                "exit_price": "101",
                "gross_return_bps": "100",
                "net_return_bps": "97",
                "r_multiple": "0.1",
            },
            "nominal exit price did not reach the frozen target",
        ),
        (
            {
                "outcome": BarrierOutcomeV3.SL_FIRST,
                "exit_price": "90",
                "gross_return_bps": "-1000",
                "net_return_bps": "-1003",
                "r_multiple": "-1",
                "barrier_trigger_price": "91",
            },
            "trigger price did not reach the frozen stop",
        ),
        (
            {
                "outcome": BarrierOutcomeV3.SL_FIRST,
                "exit_price": "99",
                "gross_return_bps": "-100",
                "net_return_bps": "-103",
                "r_multiple": "-0.1",
            },
            "nominal exit price did not reach the frozen stop",
        ),
    ],
)
def test_barrier_outcome_requires_trigger_and_nominal_fill_geometry(
    changes: dict[str, object],
    message: str,
) -> None:
    decision = event()
    activation = barrier_activation(decision)
    outcome = filled_outcome(decision, **changes)
    with pytest.raises(CanonicalizationError, match=message):
        outcome.validate_against(decision, activation)


@pytest.mark.parametrize(
    "changes",
    [
        {
            "outcome": BarrierOutcomeV3.TP_FIRST,
            "exit_price": "80",
            "gross_return_bps": "2000",
            "net_return_bps": "1997",
            "r_multiple": "2",
        },
        {
            "outcome": BarrierOutcomeV3.SL_FIRST,
            "exit_price": "110",
            "gross_return_bps": "-1000",
            "net_return_bps": "-1003",
            "r_multiple": "-1",
        },
        {
            "outcome": BarrierOutcomeV3.AMBIGUOUS,
            "ambiguity_resolution": AmbiguityResolution.CONSERVATIVE_LOWER_BOUND,
            "exit_price": "110",
            "gross_return_bps": "-1000",
            "net_return_bps": "-1003",
            "r_multiple": "-1",
            "gross_return_lower_bound_bps": "-1000",
            "gross_return_upper_bound_bps": "2000",
        },
    ],
)
def test_short_barrier_outcomes_use_side_correct_geometry(
    changes: dict[str, object],
) -> None:
    decision = event(side=TradeSide.SHORT)
    activation = barrier_activation(decision)
    outcome = filled_outcome(
        decision,
        stop_price="110",
        target_price="80",
        **changes,
    )
    outcome.validate_against(decision, activation)


def test_population_dependence_is_separate_from_intrinsic_outcome() -> None:
    decision = event()
    activation = barrier_activation(decision)
    outcome = filled_outcome(decision)
    outcome.validate_against(decision, activation)
    assignment = EventDependenceAssignmentV3(
        decision_event_id=decision.decision_event_id,
        label_outcome_id=outcome.label_outcome_id,
        dependence_policy_id=digest("dependence-policy"),
        event_cluster_id=digest("event-cluster"),
        dependence_interval_start_ts=decision.earliest_entry_ts,
        dependence_interval_end_ts=outcome.label_known_ts,
        assignment_known_ts=outcome.label_known_ts,
        concurrency=2,
        uniqueness_weight="0.5",
    )
    assignment.validate_against(decision, outcome)
    assert EventDependenceAssignmentV3.from_mapping(assignment.as_dict()) == assignment
    assert "concurrency" not in outcome.as_dict()

    other_decision = event(barrier_policy_id=digest("other-barrier-policy"))
    other_outcome = filled_outcome(other_decision)
    crossed = replace(
        assignment,
        label_outcome_id=other_outcome.label_outcome_id,
        dependence_interval_end_ts=other_outcome.label_known_ts,
    )
    with pytest.raises(CanonicalizationError, match="same graph"):
        crossed.validate_against(decision, other_outcome)


def test_derived_duration_rejects_boolean_tamper() -> None:
    payload = filled_outcome().as_dict()
    payload["holding_duration_microseconds"] = True
    with pytest.raises(CanonicalizationError, match="integer"):
        LabelOutcomeV3.from_mapping(payload)


def test_identity_decimal_arithmetic_ignores_ambient_context() -> None:
    large = CostComponentV3(
        name="large_conservative_deduction",
        bps="12345678901234567890.123456789012345678",
        known_at="2026-07-14T09:02:31Z",
        evidence_id=digest("large-cost-evidence"),
    )
    small = CostComponentV3(
        name="small_conservative_deduction",
        bps="0.000000000000000001",
        known_at="2026-07-14T09:02:31Z",
        evidence_id=digest("small-cost-evidence"),
    )
    with localcontext() as context:
        context.prec = 100
        total = Decimal(large.bps) + Decimal(small.bps)
        expected_net = Decimal("2000") - total
    outcome = filled_outcome(
        cost_components=(large, small),
        net_return_bps=str(expected_net),
    )
    with localcontext() as context:
        context.prec = 28
        low_precision = (outcome.total_cost_bps, outcome.label_outcome_id)
    with localcontext() as context:
        context.prec = 80
        high_precision = (outcome.total_cost_bps, outcome.label_outcome_id)
    assert low_precision == high_precision

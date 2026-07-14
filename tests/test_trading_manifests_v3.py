from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

import pytest

from riskyieldmm.trading import (
    CANONICALIZATION_VERSION,
    CONTRACT_SCHEMA_VERSION,
    CanonicalizationError,
    DecisionEventV3,
    EligibilityDecisionV3,
    EligibilityVerdict,
    EntryScenario,
    ImmutableManifestV3,
    InformationDependencyV3,
    InformationSetV3,
    ManifestType,
    TradeSide,
    VintageClass,
    derive_split_policy_id,
    validate_manifest_graph,
    validate_record_protocol_graph,
)


def digest(name: str) -> str:
    return hashlib.sha256(name.encode()).hexdigest()


def source_manifest(**changes: object) -> ImmutableManifestV3:
    payload: dict[str, object] = {
        "payload_schema_version": "riskyieldmm_source_manifest_payload_v1",
        "source_dataset_id": "canonical-multiasset-ohlcv",
        "source_contract_id": digest("source-contract"),
        "source_schema_id": digest("source-schema"),
        "source_content_root": digest("source-content-root"),
        "first_seen_policy_id": digest("first-seen-policy"),
        "revision_policy_id": digest("revision-policy"),
        "calendar_manifest_id": digest("calendar-manifest"),
        "universe_manifest_id": digest("universe-manifest"),
        "vintage_class": "LIVE_FIRST_SEEN_CERTIFIED",
        "knowledge_cutoff_ts": "2026-07-14T09:00:00Z",
        "parent_source_manifest_id": None,
    }
    payload.update(changes)
    return ImmutableManifestV3.create(
        manifest_type=ManifestType.SOURCE,
        payload=payload,
    )


def protocol_manifest(
    source: ImmutableManifestV3 | None = None,
    **changes: object,
) -> ImmutableManifestV3:
    source = source_manifest() if source is None else source
    split_policy_id = derive_split_policy_id(
        purge_policy_id=digest("purge-policy"),
        embargo_policy_id=digest("embargo-policy"),
        role_names=("TRAIN", "VALIDATION", "CALIBRATION", "POLICY", "TEST"),
    )
    payload: dict[str, object] = {
        "payload_schema_version": "riskyieldmm_protocol_manifest_payload_v1",
        "source_manifest_id": source.manifest_id,
        "source_contract_id": source.payload["source_contract_id"],
        "event_schema_version": CONTRACT_SCHEMA_VERSION,
        "canonicalization_version": CANONICALIZATION_VERSION,
        "calendar_manifest_id": source.payload["calendar_manifest_id"],
        "universe_manifest_id": source.payload["universe_manifest_id"],
        "feature_schema_id": digest("feature-schema"),
        "primary_signal_policy_id": digest("signal-policy"),
        "eligibility_policy_id": digest("eligibility-policy"),
        "action_protocol_id": digest("action-protocol"),
        "label_protocol_id": digest("label-protocol"),
        "barrier_policy_id": digest("barrier-policy"),
        "cost_scenario_id": digest("cost-scenario"),
        "split_policy_id": split_policy_id,
        "primary_metric_id": digest("primary-metric"),
        "evaluation_governance_id": digest("evaluation-governance"),
        "holdout_policy_id": digest("holdout-policy"),
        "code_tree_hash": digest("code-tree"),
        "workspace_state_hash": digest("workspace-state"),
        "environment_hash": digest("environment"),
        "protocol_frozen_at": "2026-07-14T10:00:00Z",
    }
    payload.update(changes)
    return ImmutableManifestV3.create(
        manifest_type=ManifestType.PROTOCOL,
        payload=payload,
    )


def split_manifest(
    protocol: ImmutableManifestV3 | None = None,
    source: ImmutableManifestV3 | None = None,
    **changes: object,
) -> ImmutableManifestV3:
    source = source_manifest() if source is None else source
    protocol = protocol_manifest(source) if protocol is None else protocol
    payload: dict[str, object] = {
        "payload_schema_version": "riskyieldmm_split_manifest_payload_v1",
        "protocol_manifest_id": protocol.manifest_id,
        "source_manifest_id": source.manifest_id,
        "split_policy_id": protocol.payload["split_policy_id"],
        "event_ledger_root": digest("event-ledger"),
        "label_ledger_root": digest("label-ledger"),
        "fold_membership_hash": digest("fold-membership"),
        "holdout_policy_id": protocol.payload["holdout_policy_id"],
        "purge_policy_id": digest("purge-policy"),
        "embargo_policy_id": digest("embargo-policy"),
        "role_names": ["TRAIN", "VALIDATION", "CALIBRATION", "POLICY", "TEST"],
        "support_summary_hash": digest("support-summary"),
        "cohort_class": "DEVELOPMENT",
        "as_of_ts": "2026-07-14T10:01:00Z",
    }
    payload.update(changes)
    return ImmutableManifestV3.create(
        manifest_type=ManifestType.SPLIT,
        payload=payload,
    )


def trial_spec_manifest(
    protocol: ImmutableManifestV3 | None = None,
    split: ImmutableManifestV3 | None = None,
    **changes: object,
) -> ImmutableManifestV3:
    if protocol is None:
        source = source_manifest()
        protocol = protocol_manifest(source)
        split = split_manifest(protocol, source) if split is None else split
    elif split is None:
        raise AssertionError("split is required with an explicit protocol")
    assert split is not None
    payload: dict[str, object] = {
        "payload_schema_version": "riskyieldmm_trial_spec_manifest_payload_v1",
        "protocol_manifest_id": protocol.manifest_id,
        "split_manifest_id": split.manifest_id,
        "hypothesis_family_id": digest("regularized-linear-baseline"),
        "trial_ordinal": 1,
        "parent_trial_spec_id": None,
        "model_spec_hash": digest("model-spec"),
        "preprocessing_spec_hash": digest("preprocessing-spec"),
        "calibration_spec_hash": digest("calibration-spec"),
        "decision_policy_spec_hash": digest("decision-policy-spec"),
        "search_space_hash": digest("search-space"),
        "seed": 20260714,
        "registered_at": "2026-07-14T10:02:00Z",
    }
    payload.update(changes)
    return ImmutableManifestV3.create(
        manifest_type=ManifestType.TRIAL_SPEC,
        payload=payload,
    )


def trial_result_manifest(
    protocol: ImmutableManifestV3,
    source: ImmutableManifestV3,
    split: ImmutableManifestV3,
    spec: ImmutableManifestV3,
    **changes: object,
) -> ImmutableManifestV3:
    payload: dict[str, object] = {
        "payload_schema_version": "riskyieldmm_trial_result_manifest_payload_v1",
        "trial_spec_manifest_id": spec.manifest_id,
        "protocol_manifest_id": protocol.manifest_id,
        "source_manifest_id": source.manifest_id,
        "split_manifest_id": split.manifest_id,
        "run_attempt_id": "attempt-0001",
        "status": "SUCCEEDED",
        "started_at": "2026-07-14T10:03:00Z",
        "completed_at": "2026-07-14T10:03:00.500000Z",
        "code_tree_hash": protocol.payload["code_tree_hash"],
        "workspace_state_hash": protocol.payload["workspace_state_hash"],
        "runtime_environment_hash": protocol.payload["environment_hash"],
        "prediction_ledger_hash": digest("prediction-ledger"),
        "metrics_hash": digest("metrics"),
        "artifact_root_hash": digest("artifact-root"),
        "failure_record_hash": None,
    }
    payload.update(changes)
    return ImmutableManifestV3.create(
        manifest_type=ManifestType.TRIAL_RESULT,
        payload=payload,
    )


def manifest_graph() -> tuple[
    ImmutableManifestV3,
    ImmutableManifestV3,
    ImmutableManifestV3,
    ImmutableManifestV3,
    ImmutableManifestV3,
    dict[str, ImmutableManifestV3],
]:
    source = source_manifest()
    protocol = protocol_manifest(source)
    split = split_manifest(protocol, source)
    spec = trial_spec_manifest(protocol, split)
    result = trial_result_manifest(protocol, source, split, spec)
    registry = {
        item.manifest_id: item for item in (source, protocol, split, spec, result)
    }
    return source, protocol, split, spec, result, registry


def protocol_record_graph(
    protocol: ImmutableManifestV3,
    source: ImmutableManifestV3,
    *,
    eligibility_policy_id: str | None = None,
    event_policy_changes: dict[str, str] | None = None,
    information_changes: dict[str, object] | None = None,
) -> tuple[InformationSetV3, EligibilityDecisionV3, DecisionEventV3]:
    dependency = InformationDependencyV3(
        name="BTCUSDT.1m.2026-07-14T09:00:00Z",
        source_id="bybit.linear.BTCUSDT.1m",
        source_manifest_id=source.manifest_id,
        observation_revision_id=digest("record-revision"),
        source_event_ts="2026-07-14T09:01:00Z",
        bar_open_ts="2026-07-14T09:00:00Z",
        bar_close_ts="2026-07-14T09:01:00Z",
        source_publish_ts="2026-07-14T09:01:01Z",
        ingested_first_seen_ts="2026-07-14T09:01:02Z",
        revision_received_ts="2026-07-14T09:01:02Z",
        feature_available_ts="2026-07-14T09:01:03Z",
        value_digest=digest("record-value"),
    )
    information_values: dict[str, object] = {
        "asset_id": "BTC",
        "venue_id": "BYBIT",
        "contract_id": "BTCUSDT.LINEAR.PERP",
        "timeframe_id": "1m",
        "observation_cutoff_ts": "2026-07-14T09:01:03Z",
        "assembled_at": "2026-07-14T09:01:04Z",
        "source_manifest_id": source.manifest_id,
        "protocol_manifest_id": protocol.manifest_id,
        "calendar_manifest_id": protocol.payload["calendar_manifest_id"],
        "feature_schema_id": protocol.payload["feature_schema_id"],
        "feature_materialization_hash": digest("record-features"),
        "dependencies": (dependency,),
        "vintage_class": VintageClass(source.payload["vintage_class"]),
        "point_in_time_certified": True,
        "certification_blockers": (),
        "universe_snapshot_id": protocol.payload["universe_manifest_id"],
    }
    information_values.update(information_changes or {})
    information_set = InformationSetV3(**information_values)  # type: ignore[arg-type]
    eligibility = EligibilityDecisionV3.create(
        information_set=information_set,
        primary_candidate_id=digest("record-candidate"),
        eligibility_policy_id=(
            protocol.payload["eligibility_policy_id"]
            if eligibility_policy_id is None
            else eligibility_policy_id
        ),
        input_state_hash=information_set.feature_materialization_hash,
        evaluated_at="2026-07-14T09:01:05Z",
        verdict=EligibilityVerdict.ELIGIBLE,
        reason_codes=(),
    )
    event_values = {
        "primary_signal_id": "online-cusum",
        "primary_signal_version": "v3",
        "primary_signal_policy_id": protocol.payload["primary_signal_policy_id"],
        "side": TradeSide.LONG,
        "decision_ts": "2026-07-14T09:01:06Z",
        "earliest_order_submission_ts": "2026-07-14T09:01:06Z",
        "earliest_entry_ts": "2026-07-14T09:02:00Z",
        "entry_expiry_ts": "2026-07-14T09:02:00Z",
        "action_protocol_id": protocol.payload["action_protocol_id"],
        "label_protocol_id": protocol.payload["label_protocol_id"],
        "entry_scenario": EntryScenario.NEXT_REAL_BASE_BAR_OPEN,
        "barrier_policy_id": protocol.payload["barrier_policy_id"],
        "cost_scenario_id": protocol.payload["cost_scenario_id"],
        "risk_unit": "10",
        "stop_r_multiple": "1",
        "target_r_multiple": "2",
        "max_holding_seconds": 60,
    }
    event_values.update(event_policy_changes or {})
    decision = DecisionEventV3.create(
        information_set=information_set,
        eligibility=eligibility,
        **event_values,
    )
    return information_set, eligibility, decision


def test_manifest_golden_id_round_trip_and_exact_envelope() -> None:
    source = source_manifest()
    assert (
        source.manifest_id
        == "07770cf53ec054407349039e75d112705e2e7a98ec8f16423d8e75c366e99a02"
    )
    assert ImmutableManifestV3.from_mapping(source.as_dict()) == source
    envelope = source.as_dict()
    envelope["unknown"] = "value"
    with pytest.raises(CanonicalizationError, match="unknown"):
        ImmutableManifestV3.from_mapping(envelope)


def test_manifest_is_deeply_immutable_across_input_and_output_mutation() -> None:
    original_payload = source_manifest().payload
    item = ImmutableManifestV3.create(
        manifest_type=ManifestType.SOURCE,
        payload=original_payload,
    )
    original_id = item.manifest_id
    original_payload["source_dataset_id"] = "mutated-input"
    returned = item.payload
    returned["source_dataset_id"] = "mutated-output"
    assert item.payload["source_dataset_id"] == "canonical-multiasset-ohlcv"
    assert item.manifest_id == original_id


def test_manifest_rejects_missing_unknown_float_and_tampered_id() -> None:
    payload = source_manifest().payload
    payload.pop("source_schema_id")
    with pytest.raises(CanonicalizationError, match="missing"):
        ImmutableManifestV3.create(manifest_type=ManifestType.SOURCE, payload=payload)

    payload = source_manifest().payload
    payload["unknown"] = "x"
    with pytest.raises(CanonicalizationError, match="unknown"):
        ImmutableManifestV3.create(manifest_type=ManifestType.SOURCE, payload=payload)

    payload = source_manifest().payload
    payload["source_dataset_id"] = 0.1
    with pytest.raises(CanonicalizationError):
        ImmutableManifestV3.create(manifest_type=ManifestType.SOURCE, payload=payload)

    envelope = source_manifest().as_dict()
    envelope["manifest_id"] = digest("tampered")
    with pytest.raises(CanonicalizationError, match="does not match"):
        ImmutableManifestV3.from_mapping(envelope)


def test_trial_result_subsecond_chronology_is_compared_as_time_not_text() -> None:
    source, protocol, split, spec, _, _ = manifest_graph()
    accepted = trial_result_manifest(
        protocol,
        source,
        split,
        spec,
        started_at="2026-07-14T10:03:00Z",
        completed_at="2026-07-14T10:03:00.500000Z",
    )
    assert accepted.payload["completed_at"].endswith(".500000Z")
    with pytest.raises(CanonicalizationError, match="must not precede"):
        trial_result_manifest(
            protocol,
            source,
            split,
            spec,
            started_at="2026-07-14T10:03:00.500000Z",
            completed_at="2026-07-14T10:03:00Z",
        )


def test_trial_result_status_lifecycle() -> None:
    source, protocol, split, spec, _, _ = manifest_graph()
    with pytest.raises(CanonicalizationError, match="missing artifacts"):
        trial_result_manifest(
            protocol,
            source,
            split,
            spec,
            metrics_hash=None,
        )
    failed = trial_result_manifest(
        protocol,
        source,
        split,
        spec,
        status="FAILED",
        prediction_ledger_hash=None,
        metrics_hash=None,
        artifact_root_hash=None,
        failure_record_hash=digest("failure-record"),
    )
    assert failed.payload["status"] == "FAILED"


def test_complete_manifest_graph_is_valid() -> None:
    source, protocol, split, spec, result, registry = manifest_graph()
    for item in (source, protocol, split, spec, result):
        validate_manifest_graph(item, registry)


def test_protocol_graph_rejects_source_contract_or_clock_mismatch() -> None:
    source = source_manifest()
    wrong_contract = protocol_manifest(
        source,
        source_contract_id=digest("different-source-contract"),
    )
    registry = {source.manifest_id: source, wrong_contract.manifest_id: wrong_contract}
    with pytest.raises(CanonicalizationError, match="source_contract_id"):
        validate_manifest_graph(wrong_contract, registry)

    early = protocol_manifest(source, protocol_frozen_at="2026-07-14T08:59:59Z")
    registry[early.manifest_id] = early
    with pytest.raises(CanonicalizationError, match="precedes"):
        validate_manifest_graph(early, registry)


def test_split_accepts_source_descendant_and_rejects_unrelated_source() -> None:
    root = source_manifest()
    protocol = protocol_manifest(root)
    child = source_manifest(
        parent_source_manifest_id=root.manifest_id,
        knowledge_cutoff_ts="2026-07-14T10:00:30Z",
        source_content_root=digest("source-content-root-child"),
    )
    split = split_manifest(
        protocol,
        child,
        as_of_ts="2026-07-14T10:01:00Z",
    )
    registry = {item.manifest_id: item for item in (root, child, protocol, split)}
    validate_manifest_graph(child, registry)
    validate_manifest_graph(split, registry)

    unrelated = source_manifest(
        source_contract_id=digest("unrelated-contract"),
        source_content_root=digest("unrelated-content"),
    )
    wrong = split_manifest(protocol, unrelated)
    registry.update({unrelated.manifest_id: unrelated, wrong.manifest_id: wrong})
    with pytest.raises(CanonicalizationError, match="not a descendant"):
        validate_manifest_graph(wrong, registry)


def test_trial_spec_graph_rejects_split_protocol_mismatch() -> None:
    source = source_manifest()
    protocol = protocol_manifest(source)
    other_protocol = protocol_manifest(source, primary_metric_id=digest("other-metric"))
    split = split_manifest(protocol, source)
    spec = trial_spec_manifest(other_protocol, split)
    registry = {
        item.manifest_id: item
        for item in (source, protocol, other_protocol, split, spec)
    }
    with pytest.raises(CanonicalizationError, match="differs"):
        validate_manifest_graph(spec, registry)


def test_trial_parent_requires_same_family_and_lower_ordinal() -> None:
    source = source_manifest()
    protocol = protocol_manifest(source)
    split = split_manifest(protocol, source)
    parent = trial_spec_manifest(protocol, split)
    child = trial_spec_manifest(
        protocol,
        split,
        parent_trial_spec_id=parent.manifest_id,
        trial_ordinal=2,
        registered_at="2026-07-14T10:03:00Z",
    )
    registry = {
        item.manifest_id: item for item in (source, protocol, split, parent, child)
    }
    validate_manifest_graph(child, registry)

    wrong_family = trial_spec_manifest(
        protocol,
        split,
        parent_trial_spec_id=parent.manifest_id,
        hypothesis_family_id=digest("deep-model-search"),
        trial_ordinal=2,
        registered_at="2026-07-14T10:03:00Z",
    )
    registry[wrong_family.manifest_id] = wrong_family
    with pytest.raises(CanonicalizationError, match="hypothesis_family_id"):
        validate_manifest_graph(wrong_family, registry)


def test_successful_result_must_match_frozen_code_environment_and_inputs() -> None:
    source, protocol, split, spec, _, registry = manifest_graph()
    wrong_environment = trial_result_manifest(
        protocol,
        source,
        split,
        spec,
        runtime_environment_hash=digest("different-environment"),
    )
    registry[wrong_environment.manifest_id] = wrong_environment
    with pytest.raises(CanonicalizationError, match="runtime_environment_hash"):
        validate_manifest_graph(wrong_environment, registry)

    other_protocol = protocol_manifest(source, primary_metric_id=digest("other-metric"))
    wrong_protocol = trial_result_manifest(
        other_protocol,
        source,
        split,
        spec,
    )
    registry.update(
        {
            other_protocol.manifest_id: other_protocol,
            wrong_protocol.manifest_id: wrong_protocol,
        }
    )
    with pytest.raises(CanonicalizationError, match="trial spec"):
        validate_manifest_graph(wrong_protocol, registry)


def test_manifest_graph_missing_or_wrong_type_reference_fails_closed() -> None:
    source, protocol, split, spec, result, registry = manifest_graph()
    missing = dict(registry)
    missing.pop(spec.manifest_id)
    with pytest.raises(CanonicalizationError, match="missing referenced"):
        validate_manifest_graph(result, missing)

    wrong_type = dict(registry)
    wrong_type[spec.manifest_id] = source
    with pytest.raises(CanonicalizationError, match="key does not match"):
        validate_manifest_graph(result, wrong_type)


def test_manifest_graph_validates_dependencies_transitively() -> None:
    root = source_manifest()
    bad_middle = source_manifest(
        parent_source_manifest_id=root.manifest_id,
        knowledge_cutoff_ts="2026-07-14T09:30:00Z",
        source_contract_id=digest("changed-contract"),
        source_content_root=digest("bad-middle-content"),
    )
    child = source_manifest(
        parent_source_manifest_id=bad_middle.manifest_id,
        knowledge_cutoff_ts="2026-07-14T09:45:00Z",
        source_contract_id=bad_middle.payload["source_contract_id"],
        source_content_root=digest("child-content"),
    )
    registry = {item.manifest_id: item for item in (root, bad_middle, child)}
    with pytest.raises(CanonicalizationError, match="source_contract_id"):
        validate_manifest_graph(child, registry)

    protocol = protocol_manifest(root)
    split = split_manifest(protocol, root)
    other_protocol = protocol_manifest(root, primary_metric_id=digest("other-metric"))
    invalid_spec = trial_spec_manifest(other_protocol, split)
    result = trial_result_manifest(other_protocol, root, split, invalid_spec)
    registry = {
        item.manifest_id: item
        for item in (root, protocol, split, other_protocol, invalid_spec, result)
    }
    with pytest.raises(CanonicalizationError, match="split protocol"):
        validate_manifest_graph(result, registry)


def test_split_binds_frozen_policy_and_complete_roles() -> None:
    source = source_manifest()
    protocol = protocol_manifest(source)
    alternate_purge = digest("different-purge-policy")
    alternate_split_policy = derive_split_policy_id(
        purge_policy_id=alternate_purge,
        embargo_policy_id=digest("embargo-policy"),
        role_names=("TRAIN", "VALIDATION", "CALIBRATION", "POLICY", "TEST"),
    )
    wrong_policy = split_manifest(
        protocol,
        source,
        purge_policy_id=alternate_purge,
        split_policy_id=alternate_split_policy,
    )
    registry = {item.manifest_id: item for item in (source, protocol, wrong_policy)}
    with pytest.raises(CanonicalizationError, match="split_policy_id"):
        validate_manifest_graph(wrong_policy, registry)

    with pytest.raises(CanonicalizationError, match="role_names"):
        split_manifest(protocol, source, role_names=["TEST"])


def test_final_holdout_requires_post_freeze_first_seen_source_descendant() -> None:
    nominal = source_manifest(vintage_class="NOMINAL_CURRENT_REVISION")
    protocol = protocol_manifest(nominal)
    invalid = split_manifest(
        protocol,
        nominal,
        cohort_class="FINAL_HOLDOUT",
    )
    registry = {item.manifest_id: item for item in (nominal, protocol, invalid)}
    with pytest.raises(CanonicalizationError, match="LIVE_FIRST_SEEN_CERTIFIED"):
        validate_manifest_graph(invalid, registry)

    forward = source_manifest(
        parent_source_manifest_id=nominal.manifest_id,
        vintage_class="LIVE_FIRST_SEEN_CERTIFIED",
        knowledge_cutoff_ts="2026-07-14T10:00:30Z",
        source_content_root=digest("forward-first-seen-content"),
    )
    final_split = split_manifest(
        protocol,
        forward,
        cohort_class="FINAL_HOLDOUT",
        as_of_ts="2026-07-14T10:01:00Z",
    )
    registry = {
        item.manifest_id: item for item in (nominal, forward, protocol, final_split)
    }
    validate_manifest_graph(final_split, registry)


def test_final_holdout_binds_policy_and_is_unique_per_protocol() -> None:
    nominal = source_manifest(vintage_class="NOMINAL_CURRENT_REVISION")
    protocol = protocol_manifest(nominal)
    forward_a = source_manifest(
        parent_source_manifest_id=nominal.manifest_id,
        vintage_class="LIVE_FIRST_SEEN_CERTIFIED",
        knowledge_cutoff_ts="2026-07-14T10:00:30Z",
        source_content_root=digest("forward-a"),
    )
    forward_b = source_manifest(
        parent_source_manifest_id=forward_a.manifest_id,
        vintage_class="LIVE_FIRST_SEEN_CERTIFIED",
        knowledge_cutoff_ts="2026-07-14T10:00:45Z",
        source_content_root=digest("forward-b"),
    )
    final_a = split_manifest(
        protocol,
        forward_a,
        cohort_class="FINAL_HOLDOUT",
        as_of_ts="2026-07-14T10:01:00Z",
    )
    final_b = split_manifest(
        protocol,
        forward_b,
        cohort_class="FINAL_HOLDOUT",
        as_of_ts="2026-07-14T10:01:15Z",
        fold_membership_hash=digest("alternate-holdout-membership"),
    )
    registry = {
        item.manifest_id: item
        for item in (nominal, forward_a, forward_b, protocol, final_a, final_b)
    }
    with pytest.raises(CanonicalizationError, match="unique key"):
        validate_manifest_graph(final_a, registry)

    wrong_policy = split_manifest(
        protocol,
        forward_a,
        cohort_class="FINAL_HOLDOUT",
        as_of_ts="2026-07-14T10:01:00Z",
        holdout_policy_id=digest("different-holdout-policy"),
    )
    registry = {
        item.manifest_id: item for item in (nominal, forward_a, protocol, wrong_policy)
    }
    with pytest.raises(CanonicalizationError, match="holdout_policy_id"):
        validate_manifest_graph(wrong_policy, registry)


@pytest.mark.parametrize(
    "field",
    [
        "eligibility_policy_id",
        "primary_signal_policy_id",
        "action_protocol_id",
        "label_protocol_id",
        "barrier_policy_id",
        "cost_scenario_id",
    ],
)
def test_record_graph_must_bind_every_frozen_protocol_policy(field: str) -> None:
    source = source_manifest(knowledge_cutoff_ts="2026-07-14T09:01:03Z")
    protocol = protocol_manifest(source)
    if field == "eligibility_policy_id":
        graph = protocol_record_graph(
            protocol,
            source,
            eligibility_policy_id=digest("wrong-eligibility-policy"),
        )
    else:
        graph = protocol_record_graph(
            protocol,
            source,
            event_policy_changes={field: digest(f"wrong-{field}")},
        )
    information_set, eligibility, decision = graph
    registry = {source.manifest_id: source, protocol.manifest_id: protocol}
    with pytest.raises(CanonicalizationError, match=field):
        validate_record_protocol_graph(
            protocol=protocol,
            information_set=information_set,
            eligibility=eligibility,
            event=decision,
            registry=registry,
        )


def test_valid_record_graph_is_bound_to_protocol_source_and_schema() -> None:
    source = source_manifest(knowledge_cutoff_ts="2026-07-14T09:01:03Z")
    protocol = protocol_manifest(source)
    information_set, eligibility, decision = protocol_record_graph(protocol, source)
    registry = {source.manifest_id: source, protocol.manifest_id: protocol}
    validate_record_protocol_graph(
        protocol=protocol,
        information_set=information_set,
        eligibility=eligibility,
        event=decision,
        registry=registry,
    )


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("protocol_manifest_id", "protocol manifest"),
        ("calendar_manifest_id", "calendar_manifest_id"),
        ("feature_schema_id", "feature_schema_id"),
        ("universe_snapshot_id", "universe_snapshot_id"),
    ],
)
def test_record_graph_rejects_protocol_identity_and_schema_substitution(
    field: str,
    message: str,
) -> None:
    source = source_manifest(knowledge_cutoff_ts="2026-07-14T09:01:03Z")
    protocol = protocol_manifest(source)
    information_set, eligibility, decision = protocol_record_graph(
        protocol,
        source,
        information_changes={field: digest(f"wrong-{field}")},
    )
    registry = {source.manifest_id: source, protocol.manifest_id: protocol}
    with pytest.raises(CanonicalizationError, match=message):
        validate_record_protocol_graph(
            protocol=protocol,
            information_set=information_set,
            eligibility=eligibility,
            event=decision,
            registry=registry,
        )


def test_record_graph_rejects_unrelated_or_insufficient_source_manifest() -> None:
    root = source_manifest(knowledge_cutoff_ts="2026-07-14T09:01:03Z")
    protocol = protocol_manifest(root)
    unrelated = source_manifest(
        knowledge_cutoff_ts="2026-07-14T09:01:03Z",
        source_content_root=digest("unrelated-record-source"),
    )
    information_set, eligibility, decision = protocol_record_graph(
        protocol,
        unrelated,
    )
    registry = {item.manifest_id: item for item in (root, unrelated, protocol)}
    with pytest.raises(CanonicalizationError, match="not a descendant"):
        validate_record_protocol_graph(
            protocol=protocol,
            information_set=information_set,
            eligibility=eligibility,
            event=decision,
            registry=registry,
        )

    early_source = source_manifest(knowledge_cutoff_ts="2026-07-14T09:01:02Z")
    early_protocol = protocol_manifest(early_source)
    information_set, eligibility, decision = protocol_record_graph(
        early_protocol,
        early_source,
    )
    early_registry = {
        early_source.manifest_id: early_source,
        early_protocol.manifest_id: early_protocol,
    }
    with pytest.raises(CanonicalizationError, match="source knowledge cutoff"):
        validate_record_protocol_graph(
            protocol=early_protocol,
            information_set=information_set,
            eligibility=eligibility,
            event=decision,
            registry=early_registry,
        )


def test_registry_rejects_duplicate_trial_ordinal_and_attempt_id() -> None:
    source, protocol, split, spec, result, registry = manifest_graph()
    conflicting_spec = trial_spec_manifest(
        protocol,
        split,
        model_spec_hash=digest("conflicting-model-spec"),
    )
    registry[conflicting_spec.manifest_id] = conflicting_spec
    with pytest.raises(CanonicalizationError, match="unique key"):
        validate_manifest_graph(spec, registry)

    registry.pop(conflicting_spec.manifest_id)
    conflicting_result = trial_result_manifest(
        protocol,
        source,
        split,
        spec,
        metrics_hash=digest("conflicting-metrics"),
    )
    registry[conflicting_result.manifest_id] = conflicting_result
    with pytest.raises(CanonicalizationError, match="unique key"):
        validate_manifest_graph(result, registry)


def test_protocol_rejects_uninstalled_event_contract() -> None:
    source = source_manifest()
    with pytest.raises(CanonicalizationError, match="event_schema_version"):
        protocol_manifest(
            source, event_schema_version="unsupported_event_contract_v999"
        )


def test_long_source_lineage_is_validated_without_call_stack_recursion() -> None:
    root = source_manifest()
    registry = {root.manifest_id: root}
    parent = root
    cutoff = datetime(2026, 7, 14, 9, tzinfo=timezone.utc)
    for index in range(1, 1_101):
        child = source_manifest(
            parent_source_manifest_id=parent.manifest_id,
            knowledge_cutoff_ts=(cutoff + timedelta(seconds=index))
            .isoformat()
            .replace("+00:00", "Z"),
            source_content_root=digest(f"source-content-{index}"),
        )
        registry[child.manifest_id] = child
        parent = child
    validate_manifest_graph(parent, registry)

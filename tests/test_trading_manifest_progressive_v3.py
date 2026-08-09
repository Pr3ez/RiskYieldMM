from __future__ import annotations

import hashlib

import pytest

from riskyieldmm.trading.canonical import (
    CANONICALIZATION_VERSION,
    CanonicalizationError,
)
from riskyieldmm.trading.contracts import (
    CONTRACT_SCHEMA_VERSION,
    CandidateFeatureMaterializationV3,
    EligibilityDecisionV3,
    EligibilityVerdict,
    EntryScenario,
    InformationDependencyV3,
    InformationSetV3,
    PrimarySignalCandidateV3,
    TradeSide,
    VintageClass,
    encode_float64_be_hex_null_v1,
)
from riskyieldmm.trading.evidence import (
    CardinalityScope,
    DependencySelectionMode,
    EvidenceKind,
    FeatureDefinitionV3,
    FeatureDependencySlotV3,
    FeatureRole,
    FeatureSchemaV3,
    MissingInputPolicy,
    SourceBundleMemberV3,
    SourceBundleV3,
    SourceRole,
)
from riskyieldmm.trading.manifests import (
    EvidenceRecordV3,
    ImmutableManifestV3,
    ManifestType,
    derive_split_policy_id,
    validate_candidate_protocol_graph,
    validate_eligibility_protocol_graph,
    validate_feature_materialization_protocol_graph,
    validate_information_protocol_graph,
)
from tests.test_trading_manifests_v3 import governed_calendar_action_evidence


def digest(name: str) -> str:
    return hashlib.sha256(name.encode()).hexdigest()


def source_member() -> SourceBundleMemberV3:
    _, schedule, _, _ = governed_calendar_action_evidence()
    return SourceBundleMemberV3(
        source_id="bybit.linear.BTCUSDT.1m",
        source_role=SourceRole.DECISION_INPUT,
        asset_id="BTC",
        venue_id="BYBIT",
        contract_id="BTCUSDT.LINEAR.PERP",
        timeframe_id="1m",
        source_schema_id=digest("source-member-schema"),
        source_field_ids=("open", "high", "low", "close", "volume"),
        availability_policy_id=digest("first-seen-policy"),
        revision_policy_id=digest("revision-policy"),
        calendar_manifest_id=schedule.calendar_snapshot_id,
        semantic_content_root=digest("source-member-semantic-root"),
        artifact_hash=digest("source-member-artifact"),
        row_count=61,
        event_start_ts="2026-07-14T08:01:00Z",
        event_end_ts="2026-07-14T09:01:00Z",
        knowledge_cutoff_ts="2026-07-14T09:01:03Z",
    )


def source_bundle(member: SourceBundleMemberV3) -> SourceBundleV3:
    return SourceBundleV3(
        source_dataset_id="canonical-multiasset-ohlcv",
        source_contract_id=digest("source-contract"),
        source_schema_id=digest("source-schema"),
        calendar_manifest_id=member.calendar_manifest_id,
        universe_manifest_id=digest("universe-manifest"),
        first_seen_policy_id=member.availability_policy_id,
        revision_policy_id=member.revision_policy_id,
        vintage_class="LIVE_FIRST_SEEN_CERTIFIED",
        knowledge_cutoff_ts="2026-07-14T09:01:03Z",
        source_member_ids=(member.source_member_id,),
    )


def source_manifest(bundle: SourceBundleV3) -> ImmutableManifestV3:
    return ImmutableManifestV3.create(
        manifest_type=ManifestType.SOURCE,
        payload={
            "payload_schema_version": "riskyieldmm_source_manifest_payload_v1",
            "source_dataset_id": bundle.source_dataset_id,
            "source_contract_id": bundle.source_contract_id,
            "source_schema_id": bundle.source_schema_id,
            "source_content_root": bundle.source_bundle_id,
            "first_seen_policy_id": bundle.first_seen_policy_id,
            "revision_policy_id": bundle.revision_policy_id,
            "calendar_manifest_id": bundle.calendar_manifest_id,
            "universe_manifest_id": bundle.universe_manifest_id,
            "vintage_class": bundle.vintage_class,
            "knowledge_cutoff_ts": "2026-07-14T09:01:03Z",
            "parent_source_manifest_id": None,
        },
    )


def dependency_slot(member: SourceBundleMemberV3) -> FeatureDependencySlotV3:
    return FeatureDependencySlotV3(
        dependency_slot_name="completed-base-close",
        evidence_kind=EvidenceKind.OBSERVATION,
        selection_mode=DependencySelectionMode.EXACT_EVENT,
        missing_input_policy=MissingInputPolicy.ABSTAIN,
        cardinality_scope=CardinalityScope.PER_SOURCE_MEMBER,
        minimum_count=1,
        maximum_count=1,
        maximum_age_seconds=120,
        source_member_keys=(member.source_member_key,),
        source_field_ids=("close",),
        availability_policy_id=member.availability_policy_id,
        revision_policy_id=member.revision_policy_id,
    )


def feature_definition(slot: FeatureDependencySlotV3) -> FeatureDefinitionV3:
    return FeatureDefinitionV3(
        feature_name="lagged-close-return",
        feature_family="causal-price-state",
        feature_role=FeatureRole.MODEL_INPUT,
        nullable=True,
        transform_hash=digest("lagged-close-return-transform"),
        transform_parameters_hash=digest("lagged-close-return-parameters"),
        normalization_hash=digest("lagged-close-return-normalization"),
        input_dependency_slot_ids=(slot.dependency_slot_id,),
        derived_feature_ids=(),
        candidate_conditioned=False,
    )


def feature_schema(
    bundle: SourceBundleV3,
    slot: FeatureDependencySlotV3,
    feature: FeatureDefinitionV3,
) -> FeatureSchemaV3:
    return FeatureSchemaV3(
        feature_schema_name="progressive-protocol-test",
        feature_schema_version="1.0.0",
        source_contract_id=bundle.source_contract_id,
        source_schema_id=bundle.source_schema_id,
        dependency_slot_ids=(slot.dependency_slot_id,),
        feature_definition_ids=(feature.feature_definition_id,),
        frozen_at="2026-07-14T09:01:03Z",
    )


def protocol_manifest(
    source: ImmutableManifestV3,
    schema: FeatureSchemaV3,
) -> ImmutableManifestV3:
    _, _, action_protocol, _ = governed_calendar_action_evidence()
    return ImmutableManifestV3.create(
        manifest_type=ManifestType.PROTOCOL,
        payload={
            "payload_schema_version": "riskyieldmm_protocol_manifest_payload_v1",
            "source_manifest_id": source.manifest_id,
            "source_contract_id": source.payload["source_contract_id"],
            "event_schema_version": CONTRACT_SCHEMA_VERSION,
            "canonicalization_version": CANONICALIZATION_VERSION,
            "calendar_manifest_id": source.payload["calendar_manifest_id"],
            "universe_manifest_id": source.payload["universe_manifest_id"],
            "feature_schema_id": schema.feature_schema_id,
            "primary_signal_policy_id": digest("signal-policy"),
            "eligibility_policy_id": digest("eligibility-policy"),
            "action_protocol_id": action_protocol.action_protocol_id,
            "label_protocol_id": digest("label-protocol"),
            "barrier_policy_id": digest("barrier-policy"),
            "cost_scenario_id": digest("cost-scenario"),
            "split_policy_id": derive_split_policy_id(
                purge_policy_id=digest("purge-policy"),
                embargo_policy_id=digest("embargo-policy"),
                role_names=(
                    "TRAIN",
                    "VALIDATION",
                    "CALIBRATION",
                    "POLICY",
                    "TEST",
                ),
            ),
            "primary_metric_id": digest("primary-metric"),
            "evaluation_governance_id": digest("evaluation-governance"),
            "holdout_policy_id": digest("holdout-policy"),
            "code_tree_hash": digest("code-tree"),
            "workspace_state_hash": digest("workspace-state"),
            "environment_hash": digest("environment"),
            "protocol_frozen_at": "2026-07-14T09:01:04Z",
        },
    )


def manifest_registry(
    source: ImmutableManifestV3,
    protocol: ImmutableManifestV3,
) -> dict[str, ImmutableManifestV3]:
    return {source.manifest_id: source, protocol.manifest_id: protocol}


def evidence_registry(
    member: SourceBundleMemberV3,
    bundle: SourceBundleV3,
    slot: FeatureDependencySlotV3,
    feature: FeatureDefinitionV3,
    schema: FeatureSchemaV3,
) -> dict[str, EvidenceRecordV3]:
    artifact, schedule, action_protocol, instrument_mapping = (
        governed_calendar_action_evidence()
    )
    return {
        artifact.calendar_source_artifact_id: artifact,
        schedule.calendar_snapshot_id: schedule,
        action_protocol.action_protocol_id: action_protocol,
        instrument_mapping.instrument_mapping_id: instrument_mapping,
        member.source_member_id: member,
        bundle.source_bundle_id: bundle,
        slot.dependency_slot_id: slot,
        feature.feature_definition_id: feature,
        schema.feature_schema_id: schema,
    }


def information_set(
    source: ImmutableManifestV3,
    protocol: ImmutableManifestV3,
    member: SourceBundleMemberV3,
    slot: FeatureDependencySlotV3,
    **changes: object,
) -> InformationSetV3:
    dependency = InformationDependencyV3(
        dependency_slot_id=slot.dependency_slot_id,
        source_member_id=member.source_member_id,
        name="BTCUSDT.1m.2026-07-14T09:00:00Z",
        source_id=member.source_id,
        source_manifest_id=source.manifest_id,
        source_field_ids=slot.source_field_ids,
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
    values: dict[str, object] = {
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
        "dependencies": (dependency,),
        "state_dependencies": (),
        "vintage_class": VintageClass.LIVE_FIRST_SEEN_CERTIFIED,
        "point_in_time_certified": True,
        "certification_blockers": (),
        "universe_snapshot_id": protocol.payload["universe_manifest_id"],
    }
    values.update(changes)
    return InformationSetV3(**values)  # type: ignore[arg-type]


def candidate(
    information: InformationSetV3,
    protocol: ImmutableManifestV3,
    **changes: object,
) -> PrimarySignalCandidateV3:
    values: dict[str, object] = {
        "primary_signal_id": "online-cusum",
        "primary_signal_version": "v3.1",
        "primary_signal_policy_id": protocol.payload["primary_signal_policy_id"],
        "signal_ts": "2026-07-14T09:01:03Z",
        "side": TradeSide.LONG,
        "candidate_available_ts": "2026-07-14T09:01:05Z",
        "entry_reference": "100",
        "earliest_order_submission_ts": "2026-07-14T09:01:09Z",
        "earliest_entry_ts": "2026-07-14T09:02:00Z",
        "entry_expiry_ts": "2026-07-14T09:03:00Z",
        "action_protocol_id": protocol.payload["action_protocol_id"],
        "action_resolution_id": digest("progressive-action-resolution"),
        "action_resolution_record_hash": digest("progressive-action-resolution-record"),
        "executable_contract_id": "BTCUSDT.LINEAR.PERP",
        "label_protocol_id": protocol.payload["label_protocol_id"],
        "entry_scenario": EntryScenario.NEXT_SCHEDULED_BASE_BAR_OPEN,
        "barrier_policy_id": protocol.payload["barrier_policy_id"],
        "cost_scenario_id": protocol.payload["cost_scenario_id"],
        "risk_unit": "10",
        "stop_r_multiple": "1",
        "target_r_multiple": "2",
        "max_holding_seconds": 60,
        "estimated_roundtrip_cost_bps": "3",
    }
    values.update(changes)
    return PrimarySignalCandidateV3.create(
        information_set=information,
        **values,  # type: ignore[arg-type]
    )


def materialization(
    information: InformationSetV3,
    candidate_record: PrimarySignalCandidateV3,
    **changes: object,
) -> CandidateFeatureMaterializationV3:
    values: dict[str, object] = {
        "feature_values": (encode_float64_be_hex_null_v1(1.5),),
        "feature_available_ts": "2026-07-14T09:01:06Z",
    }
    values.update(changes)
    return CandidateFeatureMaterializationV3.create(
        information_set=information,
        candidate=candidate_record,
        **values,  # type: ignore[arg-type]
    )


def eligibility(
    information: InformationSetV3,
    candidate_record: PrimarySignalCandidateV3,
    materialization_record: CandidateFeatureMaterializationV3,
    *,
    policy_id: str,
) -> EligibilityDecisionV3:
    return EligibilityDecisionV3.create(
        information_set=information,
        candidate=candidate_record,
        materialization=materialization_record,
        eligibility_policy_id=policy_id,
        evaluated_at="2026-07-14T09:01:07Z",
        verdict=EligibilityVerdict.ELIGIBLE,
        reason_codes=(),
    )


def progressive_graph() -> tuple[
    SourceBundleMemberV3,
    SourceBundleV3,
    ImmutableManifestV3,
    FeatureDependencySlotV3,
    FeatureDefinitionV3,
    FeatureSchemaV3,
    ImmutableManifestV3,
    InformationSetV3,
    PrimarySignalCandidateV3,
    CandidateFeatureMaterializationV3,
    EligibilityDecisionV3,
    dict[str, ImmutableManifestV3],
    dict[str, EvidenceRecordV3],
]:
    member = source_member()
    bundle = source_bundle(member)
    source = source_manifest(bundle)
    slot = dependency_slot(member)
    feature = feature_definition(slot)
    schema = feature_schema(bundle, slot, feature)
    protocol = protocol_manifest(source, schema)
    information = information_set(source, protocol, member, slot)
    candidate_record = candidate(information, protocol)
    materialization_record = materialization(information, candidate_record)
    decision = eligibility(
        information,
        candidate_record,
        materialization_record,
        policy_id=protocol.payload["eligibility_policy_id"],
    )
    return (
        member,
        bundle,
        source,
        slot,
        feature,
        schema,
        protocol,
        information,
        candidate_record,
        materialization_record,
        decision,
        manifest_registry(source, protocol),
        evidence_registry(member, bundle, slot, feature, schema),
    )


def test_information_set_can_be_validated_before_candidate_exists() -> None:
    (
        *_,
        protocol,
        information,
        _candidate,
        _materialization,
        _decision,
        registry,
        evidence,
    ) = progressive_graph()

    validate_information_protocol_graph(
        protocol=protocol,
        information_set=information,
        registry=registry,
        evidence_registry=evidence,
    )


def test_candidate_can_be_validated_before_feature_materialization_exists() -> None:
    (
        *_,
        protocol,
        information,
        candidate_record,
        _materialization,
        _decision,
        registry,
        evidence,
    ) = progressive_graph()

    validate_candidate_protocol_graph(
        protocol=protocol,
        information_set=information,
        candidate=candidate_record,
        registry=registry,
        evidence_registry=evidence,
    )


def test_feature_materialization_can_be_validated_before_eligibility_exists() -> None:
    (
        *_,
        protocol,
        information,
        candidate_record,
        materialization_record,
        _decision,
        registry,
        evidence,
    ) = progressive_graph()

    validate_feature_materialization_protocol_graph(
        protocol=protocol,
        information_set=information,
        candidate=candidate_record,
        feature_materialization=materialization_record,
        registry=registry,
        evidence_registry=evidence,
    )


def test_eligibility_can_be_validated_before_decision_event_exists() -> None:
    (
        *_,
        protocol,
        information,
        candidate_record,
        materialization_record,
        decision,
        registry,
        evidence,
    ) = progressive_graph()

    validate_eligibility_protocol_graph(
        protocol=protocol,
        information_set=information,
        candidate=candidate_record,
        feature_materialization=materialization_record,
        eligibility=decision,
        registry=registry,
        evidence_registry=evidence,
    )


def test_information_progressive_validation_enforces_frozen_schema() -> None:
    member, bundle, source, slot, feature, schema, protocol, *_ = progressive_graph()
    information = information_set(
        source,
        protocol,
        member,
        slot,
        feature_schema_id=digest("substituted-feature-schema"),
    )
    registry = manifest_registry(source, protocol)
    evidence = evidence_registry(member, bundle, slot, feature, schema)

    with pytest.raises(CanonicalizationError, match="feature_schema_id"):
        validate_information_protocol_graph(
            protocol=protocol,
            information_set=information,
            registry=registry,
            evidence_registry=evidence,
        )


def test_candidate_progressive_validation_enforces_frozen_policy() -> None:
    (
        *_,
        protocol,
        information,
        _candidate,
        _materialization,
        _decision,
        registry,
        evidence,
    ) = progressive_graph()
    substituted = candidate(
        information,
        protocol,
        primary_signal_policy_id=digest("substituted-primary-signal-policy"),
    )

    with pytest.raises(CanonicalizationError, match="primary_signal_policy_id"):
        validate_candidate_protocol_graph(
            protocol=protocol,
            information_set=information,
            candidate=substituted,
            registry=registry,
            evidence_registry=evidence,
        )


def test_forward_candidate_requires_protocol_precommitment() -> None:
    (
        *_,
        protocol,
        information,
        _candidate,
        _materialization,
        _decision,
        registry,
        evidence,
    ) = progressive_graph()
    forward_candidate = candidate(
        information,
        protocol,
        entry_scenario=EntryScenario.FORWARD_MARKET_ORDER,
    )

    with pytest.raises(CanonicalizationError, match="protocol frozen after"):
        validate_candidate_protocol_graph(
            protocol=protocol,
            information_set=information,
            candidate=forward_candidate,
            registry=registry,
            evidence_registry=evidence,
        )


def test_forward_candidate_requires_certified_live_first_seen_evidence() -> None:
    (
        member,
        _bundle,
        source,
        slot,
        _feature,
        _schema,
        protocol,
        _information,
        _candidate,
        _materialization,
        _decision,
        registry,
        evidence,
    ) = progressive_graph()
    uncertified = information_set(
        source,
        protocol,
        member,
        slot,
        point_in_time_certified=False,
        certification_blockers=("missing-prospective-receipt",),
    )
    forward_candidate = candidate(
        uncertified,
        protocol,
        entry_scenario=EntryScenario.FORWARD_MARKET_ORDER,
    )

    with pytest.raises(CanonicalizationError, match="certified live first-seen"):
        validate_candidate_protocol_graph(
            protocol=protocol,
            information_set=uncertified,
            candidate=forward_candidate,
            registry=registry,
            evidence_registry=evidence,
        )


def test_eligibility_progressive_validation_enforces_policy_and_exact_input() -> None:
    (
        member,
        _bundle,
        source,
        slot,
        _feature,
        _schema,
        protocol,
        information,
        candidate_record,
        materialization_record,
        _decision,
        registry,
        evidence,
    ) = progressive_graph()

    wrong_policy = eligibility(
        information,
        candidate_record,
        materialization_record,
        policy_id=digest("substituted-eligibility-policy"),
    )
    with pytest.raises(CanonicalizationError, match="eligibility_policy_id"):
        validate_eligibility_protocol_graph(
            protocol=protocol,
            information_set=information,
            candidate=candidate_record,
            feature_materialization=materialization_record,
            eligibility=wrong_policy,
            registry=registry,
            evidence_registry=evidence,
        )

    rematerialized_information = information_set(
        source,
        protocol,
        member,
        slot,
        assembled_at="2026-07-14T09:01:04.500000Z",
    )
    assert (
        rematerialized_information.information_set_id == information.information_set_id
    )
    assert rematerialized_information.record_hash != information.record_hash
    stale_candidate = candidate(rematerialized_information, protocol)
    stale_materialization = materialization(
        rematerialized_information,
        stale_candidate,
    )
    stale_eligibility = eligibility(
        rematerialized_information,
        stale_candidate,
        stale_materialization,
        policy_id=protocol.payload["eligibility_policy_id"],
    )
    with pytest.raises(CanonicalizationError, match="information_set_record_hash"):
        validate_eligibility_protocol_graph(
            protocol=protocol,
            information_set=information,
            candidate=stale_candidate,
            feature_materialization=stale_materialization,
            eligibility=stale_eligibility,
            registry=registry,
            evidence_registry=evidence,
        )

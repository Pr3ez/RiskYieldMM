from __future__ import annotations

import hashlib
from dataclasses import replace
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
    StateCheckpointDependencyV3,
    TradeSide,
    VintageClass,
    derive_split_policy_id,
    validate_eligibility_protocol_graph,
    validate_feature_materialization_protocol_graph,
    validate_manifest_graph,
    validate_record_protocol_graph,
)
from riskyieldmm.trading.calendar_actions import (
    ActionGridAnchor,
    ActionProtocolV3,
    ActionResolutionV3,
    ActionSelectionRule,
    CalendarAuthority,
    CalendarScheduleSnapshotV3,
    CalendarSourceArtifactV3,
    InstrumentMappingKind,
    InstrumentMappingV3,
    InstrumentPriceTransform,
    TradingIntervalV3,
    resolve_action_v3,
)
from riskyieldmm.trading.contracts import (
    CandidateFeatureMaterializationV3,
    PrimarySignalCandidateV3,
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
from riskyieldmm.trading.manifests import validate_manifest_evidence_graph

EvidenceRegistry = dict[
    str,
    CalendarSourceArtifactV3
    | CalendarScheduleSnapshotV3
    | ActionProtocolV3
    | InstrumentMappingV3
    | SourceBundleMemberV3
    | SourceBundleV3
    | FeatureDependencySlotV3
    | FeatureDefinitionV3
    | FeatureSchemaV3,
]


def digest(name: str) -> str:
    return hashlib.sha256(name.encode()).hexdigest()


def governed_calendar_action_evidence() -> tuple[
    CalendarSourceArtifactV3,
    CalendarScheduleSnapshotV3,
    ActionProtocolV3,
    InstrumentMappingV3,
]:
    artifact = CalendarSourceArtifactV3(
        authority=CalendarAuthority.OFFICIAL_VENUE,
        authority_name="BYBIT",
        source_locator="https://bybit-exchange.github.io/docs/v5/market/instrument",
        source_document_id="bybit-linear-test-schedule",
        content_hash=digest("calendar-source-bytes"),
        parser_contract_id=digest("calendar-parser"),
        published_at="2026-07-13T06:00:00Z",
        first_seen_at="2026-07-13T06:01:00Z",
        retrieved_at="2026-07-13T06:01:01Z",
        effective_start_ts="2026-07-14T00:00:00Z",
        effective_end_ts_exclusive="2026-07-15T00:00:00Z",
    )
    schedule = CalendarScheduleSnapshotV3(
        calendar_name="bybit-linear-utc",
        venue_id="BYBIT",
        contract_id="BTCUSDT.LINEAR.PERP",
        product_id="BTCUSDT",
        calendar_source_artifact_id=artifact.calendar_source_artifact_id,
        calendar_source_artifact_record_hash=artifact.record_hash,
        timezone_name="Etc/UTC",
        tzdb_version="2026a",
        tzdb_artifact_hash=digest("tzdata-2026a"),
        compiler_contract_id=digest("calendar-compiler"),
        base_timeframe_seconds=60,
        coverage_start_ts="2026-07-14T08:00:00Z",
        coverage_end_ts_exclusive="2026-07-14T12:00:00Z",
        known_at="2026-07-14T08:00:00Z",
        frozen_at="2026-07-14T08:00:01Z",
        intervals=(
            TradingIntervalV3(
                session_label="BYBIT-2026-07-14",
                trade_date="2026-07-14",
                phase="CONTINUOUS_TRADING",
                open_ts="2026-07-14T08:00:00Z",
                close_ts_exclusive="2026-07-14T12:00:00Z",
                order_entry_allowed=True,
                matching_allowed=True,
                source_schedule_key="bybit-linear-continuous",
            ),
        ),
    )
    action = ActionProtocolV3(
        protocol_name="next-scheduled-minute",
        protocol_version="1.0.0",
        selection_rule=ActionSelectionRule.NEXT_SCHEDULED_BASE_BAR_OPEN,
        entry_scenario=EntryScenario.NEXT_SCHEDULED_BASE_BAR_OPEN,
        execution_bar_seconds=60,
        entry_window_bars=1,
        computation_delay_microseconds=1_000_000,
        submission_delay_microseconds=3_000_000,
        max_search_seconds=86_400,
        grid_anchor=ActionGridAnchor.UTC_EPOCH,
        require_full_bar=True,
        roll_to_next_interval=True,
        synthetic_rows_authorize_action=False,
        allowed_calendar_authorities=(CalendarAuthority.OFFICIAL_VENUE,),
        resolver_contract_id=digest("action-resolver"),
        frozen_at="2026-07-14T08:00:00Z",
    )
    mapping = InstrumentMappingV3(
        asset_id="BTC",
        venue_id="BYBIT",
        source_contract_id="BTCUSDT.LINEAR.PERP",
        executable_contract_id="BTCUSDT.LINEAR.PERP",
        mapping_kind=InstrumentMappingKind.DIRECT,
        provider_id="bybit-v5",
        source_symbol="BTCUSDT",
        effective_start_ts="2026-07-14T00:00:00Z",
        effective_end_ts_exclusive="2026-07-15T00:00:00Z",
        known_at="2026-07-14T08:00:00Z",
        source_artifact_hash=digest("instrument-response"),
        mapping_policy_id=digest("mapping-policy"),
        price_transform=InstrumentPriceTransform.IDENTITY,
        execution_transform_id=None,
        execution_supported=True,
        blocker_codes=(),
    )
    return artifact, schedule, action, mapping


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


def governed_source_graph(
    *,
    knowledge_cutoff_ts: str = "2026-07-14T09:01:03Z",
    content_suffix: str = "record-root",
) -> tuple[
    ImmutableManifestV3,
    SourceBundleMemberV3,
    SourceBundleV3,
    EvidenceRegistry,
]:
    """Build a SOURCE whose content root resolves to an exact source bundle.

    This helper intentionally leaves ``source_manifest`` unchanged so tests of
    the manifest-only boundary keep proving that opaque manifest construction
    is stable. Strict graph tests use this governed fixture instead.
    """

    artifact, schedule, action, mapping = governed_calendar_action_evidence()
    member = SourceBundleMemberV3(
        source_id="bybit.linear.BTCUSDT.1m",
        source_role=SourceRole.DECISION_INPUT,
        asset_id="BTC",
        venue_id="BYBIT",
        contract_id="BTCUSDT.LINEAR.PERP",
        timeframe_id="1m",
        source_schema_id=digest("btc-1m-member-schema"),
        source_field_ids=("close", "high", "low", "open", "volume"),
        availability_policy_id=digest("first-seen-policy"),
        revision_policy_id=digest("revision-policy"),
        calendar_manifest_id=schedule.calendar_snapshot_id,
        semantic_content_root=digest(f"semantic-content-{content_suffix}"),
        artifact_hash=digest(f"artifact-{content_suffix}"),
        row_count=2,
        event_start_ts="2026-07-14T09:00:00Z",
        event_end_ts="2026-07-14T09:01:00Z",
        knowledge_cutoff_ts=knowledge_cutoff_ts,
    )
    bundle = SourceBundleV3(
        source_dataset_id="canonical-multiasset-ohlcv",
        source_contract_id=digest("source-contract"),
        source_schema_id=digest("source-schema"),
        calendar_manifest_id=schedule.calendar_snapshot_id,
        universe_manifest_id=digest("universe-manifest"),
        first_seen_policy_id=digest("first-seen-policy"),
        revision_policy_id=digest("revision-policy"),
        vintage_class="LIVE_FIRST_SEEN_CERTIFIED",
        knowledge_cutoff_ts=knowledge_cutoff_ts,
        source_member_ids=(member.source_member_id,),
    )
    source = source_manifest(
        source_contract_id=bundle.source_contract_id,
        source_schema_id=bundle.source_schema_id,
        source_content_root=bundle.source_bundle_id,
        first_seen_policy_id=bundle.first_seen_policy_id,
        revision_policy_id=bundle.revision_policy_id,
        calendar_manifest_id=bundle.calendar_manifest_id,
        universe_manifest_id=bundle.universe_manifest_id,
        vintage_class=bundle.vintage_class,
        knowledge_cutoff_ts=knowledge_cutoff_ts,
    )
    registry: EvidenceRegistry = {
        artifact.calendar_source_artifact_id: artifact,
        schedule.calendar_snapshot_id: schedule,
        action.action_protocol_id: action,
        mapping.instrument_mapping_id: mapping,
        member.source_member_id: member,
        bundle.source_bundle_id: bundle,
    }
    return source, member, bundle, registry


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
    default_action_protocol = governed_calendar_action_evidence()[2]
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
        "action_protocol_id": default_action_protocol.action_protocol_id,
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


def governed_protocol_graph(
    source: ImmutableManifestV3,
    member: SourceBundleMemberV3,
    bundle: SourceBundleV3,
    evidence_registry: EvidenceRegistry,
    **protocol_changes: object,
) -> tuple[
    ImmutableManifestV3,
    FeatureDependencySlotV3,
    FeatureDefinitionV3,
    FeatureSchemaV3,
    EvidenceRegistry,
]:
    """Bind an inspectable observation slot and feature DAG to a PROTOCOL."""

    artifact, schedule, default_action, default_mapping = (
        governed_calendar_action_evidence()
    )
    if bundle.calendar_manifest_id == schedule.calendar_snapshot_id:
        evidence_registry = dict(evidence_registry)
        evidence_registry.update(
            {
                artifact.calendar_source_artifact_id: artifact,
                schedule.calendar_snapshot_id: schedule,
                default_action.action_protocol_id: default_action,
                default_mapping.instrument_mapping_id: default_mapping,
            }
        )
    slot = FeatureDependencySlotV3(
        dependency_slot_name="completed_ohlcv_window",
        evidence_kind=EvidenceKind.OBSERVATION,
        selection_mode=DependencySelectionMode.TRAILING_COMPLETED_OBSERVATIONS,
        missing_input_policy=MissingInputPolicy.FAIL,
        cardinality_scope=CardinalityScope.PER_SOURCE_MEMBER,
        minimum_count=1,
        maximum_count=64,
        maximum_age_seconds=3_600,
        source_member_keys=(member.source_member_key,),
        source_field_ids=("close", "high", "low", "open", "volume"),
        availability_policy_id=bundle.first_seen_policy_id,
        revision_policy_id=bundle.revision_policy_id,
    )
    definition = FeatureDefinitionV3(
        feature_name="causal_ohlcv_state",
        feature_family="manifest-record-graph-test",
        feature_role=FeatureRole.MODEL_INPUT,
        nullable=False,
        transform_hash=digest("record-transform"),
        transform_parameters_hash=digest("record-transform-parameters"),
        normalization_hash=digest("record-normalization"),
        input_dependency_slot_ids=(slot.dependency_slot_id,),
        derived_feature_ids=(),
        candidate_conditioned=False,
    )
    schema = FeatureSchemaV3(
        feature_schema_name="record-graph-schema",
        feature_schema_version="1.0.0",
        source_contract_id=bundle.source_contract_id,
        source_schema_id=bundle.source_schema_id,
        dependency_slot_ids=(slot.dependency_slot_id,),
        feature_definition_ids=(definition.feature_definition_id,),
        frozen_at="2026-07-14T09:01:04Z",
    )
    action_protocol = next(
        item
        for item in evidence_registry.values()
        if isinstance(item, ActionProtocolV3)
    )
    protocol = protocol_manifest(
        source,
        feature_schema_id=schema.feature_schema_id,
        action_protocol_id=action_protocol.action_protocol_id,
        **protocol_changes,
    )
    governed_registry = dict(evidence_registry)
    governed_registry.update(
        {
            slot.dependency_slot_id: slot,
            definition.feature_definition_id: definition,
            schema.feature_schema_id: schema,
        }
    )
    return protocol, slot, definition, schema, governed_registry


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
    evidence_registry: EvidenceRegistry,
    *,
    eligibility_policy_id: str | None = None,
    candidate_changes: dict[str, object] | None = None,
    information_changes: dict[str, object] | None = None,
) -> tuple[
    InformationSetV3,
    PrimarySignalCandidateV3,
    CandidateFeatureMaterializationV3,
    EligibilityDecisionV3,
    DecisionEventV3,
    ActionResolutionV3,
]:
    default_artifact, default_schedule, default_action, default_mapping = (
        governed_calendar_action_evidence()
    )
    evidence_registry = dict(evidence_registry)
    if (
        protocol.payload["calendar_manifest_id"]
        == default_schedule.calendar_snapshot_id
    ):
        evidence_registry.setdefault(
            default_artifact.calendar_source_artifact_id, default_artifact
        )
        evidence_registry.setdefault(
            default_schedule.calendar_snapshot_id, default_schedule
        )
    if protocol.payload["action_protocol_id"] == default_action.action_protocol_id:
        evidence_registry.setdefault(default_action.action_protocol_id, default_action)
    evidence_registry.setdefault(default_mapping.instrument_mapping_id, default_mapping)
    bundle = evidence_registry[source.payload["source_content_root"]]
    schema = evidence_registry[protocol.payload["feature_schema_id"]]
    assert isinstance(bundle, SourceBundleV3)
    assert isinstance(schema, FeatureSchemaV3)
    member = evidence_registry[bundle.source_member_ids[0]]
    assert isinstance(member, SourceBundleMemberV3)
    slot = evidence_registry[schema.dependency_slot_ids[0]]
    assert isinstance(slot, FeatureDependencySlotV3)
    information_overrides = dict(information_changes or {})
    dependencies = information_overrides.get("dependencies")
    if dependencies is None:
        assert slot.evidence_kind is EvidenceKind.OBSERVATION
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
        dependencies = (dependency,)
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
        "dependencies": dependencies,
        "state_dependencies": (),
        "vintage_class": VintageClass(source.payload["vintage_class"]),
        "point_in_time_certified": True,
        "certification_blockers": (),
        "data_quality_flags": (),
        "universe_snapshot_id": protocol.payload["universe_manifest_id"],
    }
    information_values.update(information_overrides)
    information_set = InformationSetV3(**information_values)  # type: ignore[arg-type]
    action_protocol = evidence_registry[protocol.payload["action_protocol_id"]]
    calendar_snapshot = evidence_registry[protocol.payload["calendar_manifest_id"]]
    instrument_mapping = next(
        item
        for item in evidence_registry.values()
        if isinstance(item, InstrumentMappingV3)
    )
    assert isinstance(action_protocol, ActionProtocolV3)
    assert isinstance(calendar_snapshot, CalendarScheduleSnapshotV3)
    calendar_artifact = evidence_registry[calendar_snapshot.calendar_source_artifact_id]
    assert isinstance(calendar_artifact, CalendarSourceArtifactV3)
    action_resolution = resolve_action_v3(
        information_set=information_set,
        calendar_artifact=calendar_artifact,
        calendar=calendar_snapshot,
        protocol=action_protocol,
        mapping=instrument_mapping,
        primary_signal_id="online-cusum",
        primary_signal_version="v3.2",
        primary_signal_policy_id=protocol.payload["primary_signal_policy_id"],
        signal_ts="2026-07-14T09:01:03Z",
        side=TradeSide.LONG,
        signal_available_ts="2026-07-14T09:01:05Z",
        resolved_at="2026-07-14T09:01:06Z",
    )
    resolution_is_usable = action_resolution.earliest_order_submission_ts is not None
    candidate_values: dict[str, object] = {
        "primary_signal_id": "online-cusum",
        "primary_signal_version": "v3.2",
        "primary_signal_policy_id": protocol.payload["primary_signal_policy_id"],
        "signal_ts": "2026-07-14T09:01:03Z",
        "side": TradeSide.LONG,
        "candidate_available_ts": action_resolution.resolved_at,
        "entry_reference": "100",
        "earliest_order_submission_ts": (
            action_resolution.earliest_order_submission_ts
            if resolution_is_usable
            else "2026-07-14T09:01:09Z"
        ),
        "earliest_entry_ts": (
            action_resolution.earliest_entry_ts
            if resolution_is_usable
            else "2026-07-14T09:02:00Z"
        ),
        "entry_expiry_ts": (
            action_resolution.entry_expiry_ts
            if resolution_is_usable
            else "2026-07-14T09:03:00Z"
        ),
        "action_protocol_id": action_resolution.action_protocol_id,
        "action_resolution_id": action_resolution.action_resolution_id,
        "action_resolution_record_hash": action_resolution.record_hash,
        "executable_contract_id": action_resolution.executable_contract_id,
        "label_protocol_id": protocol.payload["label_protocol_id"],
        "entry_scenario": action_resolution.entry_scenario,
        "barrier_policy_id": protocol.payload["barrier_policy_id"],
        "cost_scenario_id": protocol.payload["cost_scenario_id"],
        "risk_unit": "10",
        "stop_r_multiple": "1",
        "target_r_multiple": "2",
        "max_holding_seconds": 60,
        "estimated_roundtrip_cost_bps": "3",
    }
    candidate_values.update(candidate_changes or {})
    candidate = PrimarySignalCandidateV3.create(
        information_set=information_set,
        **candidate_values,  # type: ignore[arg-type]
    )
    materialization = CandidateFeatureMaterializationV3.create(
        information_set=information_set,
        candidate=candidate,
        feature_values=(encode_float64_be_hex_null_v1(1.5),),
        feature_available_ts="2026-07-14T09:01:06Z",
    )
    eligibility = EligibilityDecisionV3.create(
        information_set=information_set,
        candidate=candidate,
        materialization=materialization,
        eligibility_policy_id=(
            protocol.payload["eligibility_policy_id"]
            if eligibility_policy_id is None
            else eligibility_policy_id
        ),
        evaluated_at="2026-07-14T09:01:07Z",
        verdict=EligibilityVerdict.ELIGIBLE,
        reason_codes=(),
    )
    decision = DecisionEventV3.create(
        information_set=information_set,
        candidate=candidate,
        materialization=materialization,
        eligibility=eligibility,
        decision_ts="2026-07-14T09:01:08Z",
    )
    return (
        information_set,
        candidate,
        materialization,
        eligibility,
        decision,
        action_resolution,
    )


def missing_policy_graph(
    *,
    policy: MissingInputPolicy,
    feature_values: tuple[str | None, ...],
    verdict: EligibilityVerdict = EligibilityVerdict.ELIGIBLE,
) -> dict[str, object]:
    """Build an insufficient-input graph for executable policy tests."""

    source, member, bundle, evidence_registry = governed_source_graph(
        content_suffix=f"missing-policy-{policy.value.lower()}"
    )
    slot = FeatureDependencySlotV3(
        dependency_slot_name=f"missing_{policy.value.lower()}_close",
        evidence_kind=EvidenceKind.OBSERVATION,
        selection_mode=DependencySelectionMode.LATEST_AVAILABLE_ASOF,
        missing_input_policy=policy,
        cardinality_scope=CardinalityScope.TOTAL,
        minimum_count=1,
        maximum_count=1,
        maximum_age_seconds=3_600,
        source_member_keys=(member.source_member_key,),
        source_field_ids=("close",),
        availability_policy_id=bundle.first_seen_policy_id,
        revision_policy_id=bundle.revision_policy_id,
    )
    value = FeatureDefinitionV3(
        feature_name=f"missing_{policy.value.lower()}_value",
        feature_family="missing-policy-test",
        feature_role=FeatureRole.MODEL_INPUT,
        nullable=True,
        transform_hash=digest(f"{policy.value}-value-transform"),
        transform_parameters_hash=digest(f"{policy.value}-value-parameters"),
        normalization_hash=digest(f"{policy.value}-value-normalization"),
        input_dependency_slot_ids=(slot.dependency_slot_id,),
        derived_feature_ids=(),
        candidate_conditioned=False,
    )
    definitions: tuple[FeatureDefinitionV3, ...]
    if policy is MissingInputPolicy.NULL_WITH_INDICATOR:
        indicator = FeatureDefinitionV3(
            feature_name="missing_null_with_indicator_flag",
            feature_family="missing-policy-test",
            feature_role=FeatureRole.MISSINGNESS_INDICATOR,
            nullable=False,
            transform_hash=digest("missing-indicator-transform"),
            transform_parameters_hash=digest("missing-indicator-parameters"),
            normalization_hash=digest("missing-indicator-normalization"),
            input_dependency_slot_ids=(slot.dependency_slot_id,),
            derived_feature_ids=(),
            candidate_conditioned=False,
        )
        definitions = (value, indicator)
    else:
        definitions = (value,)
    schema = FeatureSchemaV3(
        feature_schema_name=f"missing-{policy.value.lower()}-schema",
        feature_schema_version="1.0.0",
        source_contract_id=bundle.source_contract_id,
        source_schema_id=bundle.source_schema_id,
        dependency_slot_ids=(slot.dependency_slot_id,),
        feature_definition_ids=tuple(
            definition.feature_definition_id for definition in definitions
        ),
        frozen_at="2026-07-14T09:01:04Z",
    )
    protocol = protocol_manifest(source, feature_schema_id=schema.feature_schema_id)
    evidence_registry.update(
        {
            slot.dependency_slot_id: slot,
            schema.feature_schema_id: schema,
            **{
                definition.feature_definition_id: definition
                for definition in definitions
            },
        }
    )
    information, candidate, _, _, _, action_resolution = protocol_record_graph(
        protocol,
        source,
        evidence_registry,
        information_changes={"dependencies": ()},
    )
    materialization = CandidateFeatureMaterializationV3.create(
        information_set=information,
        candidate=candidate,
        feature_values=feature_values,
        feature_available_ts="2026-07-14T09:01:06Z",
    )
    reason_codes = () if verdict is EligibilityVerdict.ELIGIBLE else ("MISSING_INPUT",)
    eligibility = EligibilityDecisionV3.create(
        information_set=information,
        candidate=candidate,
        materialization=materialization,
        eligibility_policy_id=protocol.payload["eligibility_policy_id"],
        evaluated_at="2026-07-14T09:01:07Z",
        verdict=verdict,
        reason_codes=reason_codes,
    )
    registry = {source.manifest_id: source, protocol.manifest_id: protocol}
    calendar_records = tuple(
        item
        for item in evidence_registry.values()
        if isinstance(
            item,
            (
                CalendarSourceArtifactV3,
                CalendarScheduleSnapshotV3,
                ActionProtocolV3,
                InstrumentMappingV3,
            ),
        )
    )
    calendar_records = tuple(
        sorted(
            calendar_records,
            key=lambda item: {
                CalendarSourceArtifactV3: 0,
                CalendarScheduleSnapshotV3: 1,
                ActionProtocolV3: 2,
                InstrumentMappingV3: 3,
            }[type(item)],
        )
    )
    evidence_records = (
        *calendar_records,
        member,
        bundle,
        slot,
        *definitions,
        schema,
    )
    return {
        "candidate": candidate,
        "action_resolution": action_resolution,
        "eligibility": eligibility,
        "evidence_records": evidence_records,
        "evidence_registry": evidence_registry,
        "information": information,
        "materialization": materialization,
        "protocol": protocol,
        "registry": registry,
        "source": source,
    }


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
    anchor = source_manifest(vintage_class="LIVE_FIRST_SEEN_CERTIFIED")
    protocol = protocol_manifest(anchor)
    invalid = split_manifest(
        protocol,
        anchor,
        cohort_class="FINAL_HOLDOUT",
    )
    registry = {item.manifest_id: item for item in (anchor, protocol, invalid)}
    with pytest.raises(CanonicalizationError, match="accrue after"):
        validate_manifest_graph(invalid, registry)

    forward = source_manifest(
        parent_source_manifest_id=anchor.manifest_id,
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
        item.manifest_id: item for item in (anchor, forward, protocol, final_split)
    }
    validate_manifest_graph(final_split, registry)


def test_source_manifest_lineage_cannot_upgrade_nominal_to_live() -> None:
    nominal = source_manifest(vintage_class="NOMINAL_CURRENT_REVISION")
    claimed_live = source_manifest(
        parent_source_manifest_id=nominal.manifest_id,
        vintage_class="LIVE_FIRST_SEEN_CERTIFIED",
        knowledge_cutoff_ts="2026-07-14T10:00:30Z",
        source_content_root=digest("wrapped-live-claim"),
    )
    registry = {item.manifest_id: item for item in (nominal, claimed_live)}

    with pytest.raises(CanonicalizationError, match="separate root lineage"):
        validate_manifest_graph(claimed_live, registry)


def test_final_holdout_binds_policy_and_is_unique_per_protocol() -> None:
    anchor = source_manifest(vintage_class="LIVE_FIRST_SEEN_CERTIFIED")
    protocol = protocol_manifest(anchor)
    forward_a = source_manifest(
        parent_source_manifest_id=anchor.manifest_id,
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
        for item in (anchor, forward_a, forward_b, protocol, final_a, final_b)
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
        item.manifest_id: item for item in (anchor, forward_a, protocol, wrong_policy)
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
    source, member, bundle, evidence_registry = governed_source_graph()
    protocol, _, _, _, evidence_registry = governed_protocol_graph(
        source,
        member,
        bundle,
        evidence_registry,
    )
    if field == "eligibility_policy_id":
        graph = protocol_record_graph(
            protocol,
            source,
            evidence_registry,
            eligibility_policy_id=digest("wrong-eligibility-policy"),
        )
    else:
        graph = protocol_record_graph(
            protocol,
            source,
            evidence_registry,
            candidate_changes={field: digest(f"wrong-{field}")},
        )
    information_set, candidate, materialization, eligibility, decision, _ = graph
    registry = {source.manifest_id: source, protocol.manifest_id: protocol}
    with pytest.raises(CanonicalizationError, match=field):
        validate_record_protocol_graph(
            protocol=protocol,
            information_set=information_set,
            candidate=candidate,
            feature_materialization=materialization,
            eligibility=eligibility,
            event=decision,
            registry=registry,
            evidence_registry=evidence_registry,
        )


def test_strict_manifest_graph_resolves_source_bundle_and_feature_schema() -> None:
    source, member, bundle, evidence_registry = governed_source_graph()
    protocol, _, _, schema, evidence_registry = governed_protocol_graph(
        source,
        member,
        bundle,
        evidence_registry,
    )
    registry = {source.manifest_id: source, protocol.manifest_id: protocol}

    validate_manifest_evidence_graph(protocol, registry, evidence_registry)
    assert source.payload["source_content_root"] == bundle.source_bundle_id
    assert protocol.payload["feature_schema_id"] == schema.feature_schema_id

    missing_schema = dict(evidence_registry)
    missing_schema.pop(schema.feature_schema_id)
    with pytest.raises(CanonicalizationError, match="missing referenced .* evidence"):
        validate_manifest_evidence_graph(protocol, registry, missing_schema)


def test_manifest_only_graph_does_not_masquerade_as_governed_evidence() -> None:
    source = source_manifest()
    protocol = protocol_manifest(source)
    registry = {source.manifest_id: source, protocol.manifest_id: protocol}

    validate_manifest_graph(protocol, registry)
    with pytest.raises(CanonicalizationError, match="missing referenced .* evidence"):
        validate_manifest_evidence_graph(protocol, registry, {})


def test_valid_record_graph_is_bound_to_protocol_source_and_schema() -> None:
    source, member, bundle, evidence_registry = governed_source_graph()
    protocol, _, _, _, evidence_registry = governed_protocol_graph(
        source,
        member,
        bundle,
        evidence_registry,
    )
    information_set, candidate, materialization, eligibility, decision, _ = (
        protocol_record_graph(protocol, source, evidence_registry)
    )
    registry = {source.manifest_id: source, protocol.manifest_id: protocol}
    validate_record_protocol_graph(
        protocol=protocol,
        information_set=information_set,
        candidate=candidate,
        feature_materialization=materialization,
        eligibility=eligibility,
        event=decision,
        registry=registry,
        evidence_registry=evidence_registry,
    )


@pytest.mark.parametrize(
    ("values", "message"),
    [
        (
            (
                encode_float64_be_hex_null_v1(123.0),
                encode_float64_be_hex_null_v1(1.0),
            ),
            "must be null",
        ),
        (
            (None, encode_float64_be_hex_null_v1(0.0)),
            "must equal 1.0",
        ),
    ],
)
def test_null_with_indicator_policy_has_executable_vector_semantics(
    values: tuple[str | None, ...],
    message: str,
) -> None:
    graph = missing_policy_graph(
        policy=MissingInputPolicy.NULL_WITH_INDICATOR,
        feature_values=values,
    )
    with pytest.raises(CanonicalizationError, match=message):
        validate_feature_materialization_protocol_graph(
            protocol=graph["protocol"],
            information_set=graph["information"],
            candidate=graph["candidate"],
            feature_materialization=graph["materialization"],
            registry=graph["registry"],
            evidence_registry=graph["evidence_registry"],
        )

    valid = missing_policy_graph(
        policy=MissingInputPolicy.NULL_WITH_INDICATOR,
        feature_values=(None, encode_float64_be_hex_null_v1(1.0)),
    )
    validate_feature_materialization_protocol_graph(
        protocol=valid["protocol"],
        information_set=valid["information"],
        candidate=valid["candidate"],
        feature_materialization=valid["materialization"],
        registry=valid["registry"],
        evidence_registry=valid["evidence_registry"],
    )


def test_abstain_policy_requires_abstain_data_when_input_is_insufficient() -> None:
    graph = missing_policy_graph(
        policy=MissingInputPolicy.ABSTAIN,
        feature_values=(None,),
    )
    with pytest.raises(CanonicalizationError, match="requires ABSTAIN_DATA"):
        validate_eligibility_protocol_graph(
            protocol=graph["protocol"],
            information_set=graph["information"],
            candidate=graph["candidate"],
            feature_materialization=graph["materialization"],
            eligibility=graph["eligibility"],
            registry=graph["registry"],
            evidence_registry=graph["evidence_registry"],
        )

    abstained = missing_policy_graph(
        policy=MissingInputPolicy.ABSTAIN,
        feature_values=(None,),
        verdict=EligibilityVerdict.ABSTAIN_DATA,
    )
    validate_eligibility_protocol_graph(
        protocol=abstained["protocol"],
        information_set=abstained["information"],
        candidate=abstained["candidate"],
        feature_materialization=abstained["materialization"],
        eligibility=abstained["eligibility"],
        registry=abstained["registry"],
        evidence_registry=abstained["evidence_registry"],
    )


@pytest.mark.parametrize(
    ("dependency_change", "message"),
    [
        (
            {"source_member_id": digest("foreign-source-member")},
            "foreign source member",
        ),
        (
            {"source_field_ids": ("volume", "open", "low", "high", "close")},
            "source fields",
        ),
    ],
)
def test_record_graph_rejects_foreign_member_and_reordered_source_fields(
    dependency_change: dict[str, object],
    message: str,
) -> None:
    source, member, bundle, evidence_registry = governed_source_graph()
    protocol, _, _, _, evidence_registry = governed_protocol_graph(
        source,
        member,
        bundle,
        evidence_registry,
    )
    valid_information, *_ = protocol_record_graph(
        protocol,
        source,
        evidence_registry,
    )
    invalid_dependency = replace(
        valid_information.dependencies[0],
        **dependency_change,
    )
    information, candidate, materialization, eligibility, decision, _ = (
        protocol_record_graph(
            protocol,
            source,
            evidence_registry,
            information_changes={"dependencies": (invalid_dependency,)},
        )
    )
    registry = {source.manifest_id: source, protocol.manifest_id: protocol}

    with pytest.raises(CanonicalizationError, match=message):
        validate_record_protocol_graph(
            protocol=protocol,
            information_set=information,
            candidate=candidate,
            feature_materialization=materialization,
            eligibility=eligibility,
            event=decision,
            registry=registry,
            evidence_registry=evidence_registry,
        )


def test_full_graph_rejects_null_publish_clock_with_future_event() -> None:
    source, member, bundle, evidence_registry = governed_source_graph(
        content_suffix="null-publish-clock"
    )
    protocol, _, _, _, evidence_registry = governed_protocol_graph(
        source,
        member,
        bundle,
        evidence_registry,
    )
    valid_information, *_ = protocol_record_graph(
        protocol,
        source,
        evidence_registry,
    )
    poisoned = replace(
        valid_information.dependencies[0],
        source_publish_ts=None,
    )
    # Simulate an in-memory object whose frozen dataclass guard was bypassed;
    # deserialization rejects this earlier, while the graph remains defensive.
    object.__setattr__(
        poisoned,
        "ingested_first_seen_ts",
        datetime(2026, 7, 14, 8, 59, tzinfo=timezone.utc),
    )
    information, candidate, materialization, eligibility, decision, _ = (
        protocol_record_graph(
            protocol,
            source,
            evidence_registry,
            information_changes={"dependencies": (poisoned,)},
        )
    )
    with pytest.raises(CanonicalizationError, match="ingested_first_seen_ts"):
        validate_record_protocol_graph(
            protocol=protocol,
            information_set=information,
            candidate=candidate,
            feature_materialization=materialization,
            eligibility=eligibility,
            event=decision,
            registry={source.manifest_id: source, protocol.manifest_id: protocol},
            evidence_registry=evidence_registry,
        )


def test_cross_slot_reuse_requires_one_consistent_observation_revision() -> None:
    source, member, bundle, evidence_registry = governed_source_graph()
    first_slot = FeatureDependencySlotV3(
        dependency_slot_name="first_completed_close",
        evidence_kind=EvidenceKind.OBSERVATION,
        selection_mode=DependencySelectionMode.LATEST_AVAILABLE_ASOF,
        missing_input_policy=MissingInputPolicy.FAIL,
        cardinality_scope=CardinalityScope.PER_SOURCE_MEMBER,
        minimum_count=1,
        maximum_count=1,
        maximum_age_seconds=3_600,
        source_member_keys=(member.source_member_key,),
        source_field_ids=("close",),
        availability_policy_id=bundle.first_seen_policy_id,
        revision_policy_id=bundle.revision_policy_id,
    )
    second_slot = replace(
        first_slot,
        dependency_slot_name="second_completed_close",
    )
    first_feature = FeatureDefinitionV3(
        feature_name="first_close_state",
        feature_family="revision-alias-test",
        feature_role=FeatureRole.MODEL_INPUT,
        nullable=False,
        transform_hash=digest("first-close-transform"),
        transform_parameters_hash=digest("first-close-parameters"),
        normalization_hash=digest("first-close-normalization"),
        input_dependency_slot_ids=(first_slot.dependency_slot_id,),
        derived_feature_ids=(),
        candidate_conditioned=False,
    )
    second_feature = replace(
        first_feature,
        feature_name="second_close_state",
        transform_hash=digest("second-close-transform"),
        input_dependency_slot_ids=(second_slot.dependency_slot_id,),
    )
    schema = FeatureSchemaV3(
        feature_schema_name="revision-alias-schema",
        feature_schema_version="1.0.0",
        source_contract_id=bundle.source_contract_id,
        source_schema_id=bundle.source_schema_id,
        dependency_slot_ids=(
            first_slot.dependency_slot_id,
            second_slot.dependency_slot_id,
        ),
        feature_definition_ids=(
            first_feature.feature_definition_id,
            second_feature.feature_definition_id,
        ),
        frozen_at="2026-07-14T09:01:04Z",
    )
    protocol = protocol_manifest(source, feature_schema_id=schema.feature_schema_id)
    evidence_registry.update(
        {
            first_slot.dependency_slot_id: first_slot,
            second_slot.dependency_slot_id: second_slot,
            first_feature.feature_definition_id: first_feature,
            second_feature.feature_definition_id: second_feature,
            schema.feature_schema_id: schema,
        }
    )
    valid_information, *_ = protocol_record_graph(
        protocol,
        source,
        evidence_registry,
    )
    first = valid_information.dependencies[0]
    other_slot_id = next(
        slot_id
        for slot_id in schema.dependency_slot_ids
        if slot_id != first.dependency_slot_id
    )
    registry = {source.manifest_id: source, protocol.manifest_id: protocol}

    conflicting_coordinates = replace(
        first,
        dependency_slot_id=other_slot_id,
        name="BTCUSDT.1m.2026-07-14T08:59:00Z",
        source_event_ts="2026-07-14T09:00:00Z",
        bar_open_ts="2026-07-14T08:59:00Z",
        bar_close_ts="2026-07-14T09:00:00Z",
    )
    graph = protocol_record_graph(
        protocol,
        source,
        evidence_registry,
        information_changes={
            "dependencies": (first, conflicting_coordinates),
        },
    )
    with pytest.raises(CanonicalizationError, match="conflicting coordinates"):
        validate_record_protocol_graph(
            protocol=protocol,
            information_set=graph[0],
            candidate=graph[1],
            feature_materialization=graph[2],
            eligibility=graph[3],
            event=graph[4],
            registry=registry,
            evidence_registry=evidence_registry,
        )

    conflicting_value = replace(
        first,
        dependency_slot_id=other_slot_id,
        value_digest=digest("conflicting-cross-slot-value"),
    )
    graph = protocol_record_graph(
        protocol,
        source,
        evidence_registry,
        information_changes={"dependencies": (first, conflicting_value)},
    )
    with pytest.raises(CanonicalizationError, match="conflicting value digests"):
        validate_record_protocol_graph(
            protocol=protocol,
            information_set=graph[0],
            candidate=graph[1],
            feature_materialization=graph[2],
            eligibility=graph[3],
            event=graph[4],
            registry=registry,
            evidence_registry=evidence_registry,
        )


def test_full_record_graph_rejects_backdated_forward_protocol() -> None:
    source, member, bundle, evidence_registry = governed_source_graph()
    protocol, _, _, _, evidence_registry = governed_protocol_graph(
        source,
        member,
        bundle,
        evidence_registry,
    )
    information, candidate, materialization, eligibility, decision, _ = (
        protocol_record_graph(
            protocol,
            source,
            evidence_registry,
            candidate_changes={
                "entry_scenario": EntryScenario.FORWARD_MARKET_ORDER,
            },
        )
    )

    with pytest.raises(CanonicalizationError, match="protocol frozen after"):
        validate_record_protocol_graph(
            protocol=protocol,
            information_set=information,
            candidate=candidate,
            feature_materialization=materialization,
            eligibility=eligibility,
            event=decision,
            registry={source.manifest_id: source, protocol.manifest_id: protocol},
            evidence_registry=evidence_registry,
        )


def test_record_graph_enforces_declared_dependency_cardinality() -> None:
    source, member, bundle, evidence_registry = governed_source_graph()
    slot = FeatureDependencySlotV3(
        dependency_slot_name="two_completed_observations",
        evidence_kind=EvidenceKind.OBSERVATION,
        selection_mode=DependencySelectionMode.TRAILING_COMPLETED_OBSERVATIONS,
        missing_input_policy=MissingInputPolicy.FAIL,
        cardinality_scope=CardinalityScope.PER_SOURCE_MEMBER,
        minimum_count=2,
        maximum_count=2,
        maximum_age_seconds=3_600,
        source_member_keys=(member.source_member_key,),
        source_field_ids=("close",),
        availability_policy_id=bundle.first_seen_policy_id,
        revision_policy_id=bundle.revision_policy_id,
    )
    definition = FeatureDefinitionV3(
        feature_name="two_bar_state",
        feature_family="cardinality-test",
        feature_role=FeatureRole.MODEL_INPUT,
        nullable=False,
        transform_hash=digest("two-bar-transform"),
        transform_parameters_hash=digest("two-bar-parameters"),
        normalization_hash=digest("two-bar-normalization"),
        input_dependency_slot_ids=(slot.dependency_slot_id,),
        derived_feature_ids=(),
        candidate_conditioned=False,
    )
    schema = FeatureSchemaV3(
        feature_schema_name="cardinality-test-schema",
        feature_schema_version="1.0.0",
        source_contract_id=bundle.source_contract_id,
        source_schema_id=bundle.source_schema_id,
        dependency_slot_ids=(slot.dependency_slot_id,),
        feature_definition_ids=(definition.feature_definition_id,),
        frozen_at="2026-07-14T09:01:04Z",
    )
    protocol = protocol_manifest(source, feature_schema_id=schema.feature_schema_id)
    evidence_registry.update(
        {
            slot.dependency_slot_id: slot,
            definition.feature_definition_id: definition,
            schema.feature_schema_id: schema,
        }
    )
    information, candidate, materialization, eligibility, decision, _ = (
        protocol_record_graph(protocol, source, evidence_registry)
    )
    registry = {source.manifest_id: source, protocol.manifest_id: protocol}

    with pytest.raises(CanonicalizationError, match="cardinality 1 is outside"):
        validate_record_protocol_graph(
            protocol=protocol,
            information_set=information,
            candidate=candidate,
            feature_materialization=materialization,
            eligibility=eligibility,
            event=decision,
            registry=registry,
            evidence_registry=evidence_registry,
        )


def test_realized_unique_observations_cannot_exceed_source_member_row_count() -> None:
    _, original_member, original_bundle, _ = governed_source_graph()
    member = replace(original_member, row_count=1)
    bundle = replace(
        original_bundle,
        source_member_ids=(member.source_member_id,),
    )
    source = source_manifest(
        source_contract_id=bundle.source_contract_id,
        source_schema_id=bundle.source_schema_id,
        source_content_root=bundle.source_bundle_id,
        first_seen_policy_id=bundle.first_seen_policy_id,
        revision_policy_id=bundle.revision_policy_id,
        calendar_manifest_id=bundle.calendar_manifest_id,
        universe_manifest_id=bundle.universe_manifest_id,
        vintage_class=bundle.vintage_class,
        knowledge_cutoff_ts="2026-07-14T09:01:03Z",
    )
    evidence_registry: EvidenceRegistry = {
        member.source_member_id: member,
        bundle.source_bundle_id: bundle,
    }
    protocol, _, _, _, evidence_registry = governed_protocol_graph(
        source,
        member,
        bundle,
        evidence_registry,
    )
    valid_information, *_ = protocol_record_graph(
        protocol,
        source,
        evidence_registry,
    )
    latest = valid_information.dependencies[0]
    earlier = replace(
        latest,
        name="BTCUSDT.1m.2026-07-14T08:59:00Z",
        observation_revision_id=digest("earlier-record-revision"),
        source_event_ts="2026-07-14T09:00:00Z",
        bar_open_ts="2026-07-14T08:59:00Z",
        bar_close_ts="2026-07-14T09:00:00Z",
        value_digest=digest("earlier-record-value"),
    )
    information, candidate, materialization, eligibility, decision, _ = (
        protocol_record_graph(
            protocol,
            source,
            evidence_registry,
            information_changes={"dependencies": (earlier, latest)},
        )
    )

    with pytest.raises(CanonicalizationError, match="exceed source-member row_count"):
        validate_record_protocol_graph(
            protocol=protocol,
            information_set=information,
            candidate=candidate,
            feature_materialization=materialization,
            eligibility=eligibility,
            event=decision,
            registry={source.manifest_id: source, protocol.manifest_id: protocol},
            evidence_registry=evidence_registry,
        )


def test_per_source_member_cardinality_rejects_missing_multi_asset_member() -> None:
    _, btc, base_bundle, base_evidence = governed_source_graph()
    eth = replace(
        btc,
        source_id="bybit.linear.ETHUSDT.1m",
        asset_id="ETH",
        contract_id="ETHUSDT.LINEAR.PERP",
        source_schema_id=digest("eth-1m-member-schema"),
        semantic_content_root=digest("eth-semantic-content"),
        artifact_hash=digest("eth-artifact"),
    )
    bundle = replace(
        base_bundle,
        source_member_ids=(btc.source_member_id, eth.source_member_id),
    )
    source = source_manifest(
        source_contract_id=bundle.source_contract_id,
        source_schema_id=bundle.source_schema_id,
        source_content_root=bundle.source_bundle_id,
        first_seen_policy_id=bundle.first_seen_policy_id,
        revision_policy_id=bundle.revision_policy_id,
        calendar_manifest_id=bundle.calendar_manifest_id,
        universe_manifest_id=bundle.universe_manifest_id,
        vintage_class=bundle.vintage_class,
        knowledge_cutoff_ts="2026-07-14T09:01:03Z",
    )
    slot = FeatureDependencySlotV3(
        dependency_slot_name="btc_eth_completed_close",
        evidence_kind=EvidenceKind.OBSERVATION,
        selection_mode=DependencySelectionMode.TRAILING_COMPLETED_OBSERVATIONS,
        missing_input_policy=MissingInputPolicy.FAIL,
        cardinality_scope=CardinalityScope.PER_SOURCE_MEMBER,
        minimum_count=1,
        maximum_count=64,
        maximum_age_seconds=3_600,
        source_member_keys=(btc.source_member_key, eth.source_member_key),
        source_field_ids=("close",),
        availability_policy_id=bundle.first_seen_policy_id,
        revision_policy_id=bundle.revision_policy_id,
    )
    definition = FeatureDefinitionV3(
        feature_name="btc_eth_relative_close",
        feature_family="multi-asset-cardinality-test",
        feature_role=FeatureRole.MODEL_INPUT,
        nullable=False,
        transform_hash=digest("btc-eth-transform"),
        transform_parameters_hash=digest("btc-eth-parameters"),
        normalization_hash=digest("btc-eth-normalization"),
        input_dependency_slot_ids=(slot.dependency_slot_id,),
        derived_feature_ids=(),
        candidate_conditioned=False,
    )
    schema = FeatureSchemaV3(
        feature_schema_name="multi-asset-cardinality-schema",
        feature_schema_version="1.0.0",
        source_contract_id=bundle.source_contract_id,
        source_schema_id=bundle.source_schema_id,
        dependency_slot_ids=(slot.dependency_slot_id,),
        feature_definition_ids=(definition.feature_definition_id,),
        frozen_at="2026-07-14T09:01:04Z",
    )
    protocol = protocol_manifest(source, feature_schema_id=schema.feature_schema_id)
    evidence_registry: EvidenceRegistry = {
        **base_evidence,
        btc.source_member_id: btc,
        eth.source_member_id: eth,
        bundle.source_bundle_id: bundle,
        slot.dependency_slot_id: slot,
        definition.feature_definition_id: definition,
        schema.feature_schema_id: schema,
    }
    information, candidate, materialization, eligibility, decision, _ = (
        protocol_record_graph(protocol, source, evidence_registry)
    )
    registry = {source.manifest_id: source, protocol.manifest_id: protocol}

    with pytest.raises(CanonicalizationError, match="source member .* cardinality 0"):
        validate_record_protocol_graph(
            protocol=protocol,
            information_set=information,
            candidate=candidate,
            feature_materialization=materialization,
            eligibility=eligibility,
            event=decision,
            registry=registry,
            evidence_registry=evidence_registry,
        )


def test_realized_observation_rejects_empty_source_member() -> None:
    _, member, bundle, _ = governed_source_graph()
    empty_member = replace(
        member,
        semantic_content_root=digest("empty-semantic-content"),
        artifact_hash=digest("empty-artifact"),
        row_count=0,
        event_start_ts=None,
        event_end_ts=None,
    )
    empty_bundle = replace(
        bundle,
        source_member_ids=(empty_member.source_member_id,),
    )
    source = source_manifest(
        source_contract_id=empty_bundle.source_contract_id,
        source_schema_id=empty_bundle.source_schema_id,
        source_content_root=empty_bundle.source_bundle_id,
        first_seen_policy_id=empty_bundle.first_seen_policy_id,
        revision_policy_id=empty_bundle.revision_policy_id,
        calendar_manifest_id=empty_bundle.calendar_manifest_id,
        universe_manifest_id=empty_bundle.universe_manifest_id,
        vintage_class=empty_bundle.vintage_class,
        knowledge_cutoff_ts="2026-07-14T09:01:03Z",
    )
    evidence_registry: EvidenceRegistry = {
        empty_member.source_member_id: empty_member,
        empty_bundle.source_bundle_id: empty_bundle,
    }
    protocol, _, _, _, evidence_registry = governed_protocol_graph(
        source,
        empty_member,
        empty_bundle,
        evidence_registry,
    )
    information, candidate, materialization, eligibility, decision, _ = (
        protocol_record_graph(protocol, source, evidence_registry)
    )

    with pytest.raises(CanonicalizationError, match="empty source member"):
        validate_record_protocol_graph(
            protocol=protocol,
            information_set=information,
            candidate=candidate,
            feature_materialization=materialization,
            eligibility=eligibility,
            event=decision,
            registry={source.manifest_id: source, protocol.manifest_id: protocol},
            evidence_registry=evidence_registry,
        )


def test_information_set_can_realize_state_only_feature_schema() -> None:
    source, member, bundle, evidence_registry = governed_source_graph()
    slot = FeatureDependencySlotV3(
        dependency_slot_name="prior_online_regime_state",
        evidence_kind=EvidenceKind.STATE_CHECKPOINT,
        selection_mode=DependencySelectionMode.PRIOR_STATE_CHECKPOINT,
        missing_input_policy=MissingInputPolicy.FAIL,
        cardinality_scope=CardinalityScope.TOTAL,
        minimum_count=1,
        maximum_count=1,
        maximum_age_seconds=3_600,
        state_schema_id=digest("online-regime-state-schema"),
    )
    definition = FeatureDefinitionV3(
        feature_name="prior_regime_state_value",
        feature_family="state-only-test",
        feature_role=FeatureRole.MODEL_INPUT,
        nullable=False,
        transform_hash=digest("state-only-transform"),
        transform_parameters_hash=digest("state-only-parameters"),
        normalization_hash=digest("state-only-normalization"),
        input_dependency_slot_ids=(slot.dependency_slot_id,),
        derived_feature_ids=(),
        candidate_conditioned=False,
    )
    schema = FeatureSchemaV3(
        feature_schema_name="state-only-schema",
        feature_schema_version="1.0.0",
        source_contract_id=bundle.source_contract_id,
        source_schema_id=bundle.source_schema_id,
        dependency_slot_ids=(slot.dependency_slot_id,),
        feature_definition_ids=(definition.feature_definition_id,),
        frozen_at="2026-07-14T09:01:04Z",
    )
    protocol = protocol_manifest(source, feature_schema_id=schema.feature_schema_id)
    evidence_registry.update(
        {
            slot.dependency_slot_id: slot,
            definition.feature_definition_id: definition,
            schema.feature_schema_id: schema,
        }
    )
    state = StateCheckpointDependencyV3(
        dependency_slot_id=slot.dependency_slot_id,
        state_schema_id=slot.state_schema_id,
        state_cutoff_ts="2026-07-14T09:01:00Z",
        state_available_ts="2026-07-14T09:01:03Z",
        value_digest=digest("prior-online-regime-state"),
        parent_state_checkpoint_id=digest("earlier-online-regime-state"),
    )
    information, candidate, materialization, eligibility, decision, _ = (
        protocol_record_graph(
            protocol,
            source,
            evidence_registry,
            information_changes={
                "dependencies": (),
                "state_dependencies": (state,),
            },
        )
    )

    validate_record_protocol_graph(
        protocol=protocol,
        information_set=information,
        candidate=candidate,
        feature_materialization=materialization,
        eligibility=eligibility,
        event=decision,
        registry={source.manifest_id: source, protocol.manifest_id: protocol},
        evidence_registry=evidence_registry,
    )


def test_information_set_rejects_multiple_revisions_of_same_observation() -> None:
    source, member, bundle, evidence_registry = governed_source_graph()
    protocol, _, _, _, evidence_registry = governed_protocol_graph(
        source,
        member,
        bundle,
        evidence_registry,
    )
    valid_information, *_ = protocol_record_graph(
        protocol,
        source,
        evidence_registry,
    )
    first = valid_information.dependencies[0]
    second_revision = replace(
        first,
        observation_revision_id=digest("second-revision-of-same-bar"),
        value_digest=digest("second-revision-value"),
    )
    information, candidate, materialization, eligibility, decision, _ = (
        protocol_record_graph(
            protocol,
            source,
            evidence_registry,
            information_changes={"dependencies": (first, second_revision)},
        )
    )

    with pytest.raises(CanonicalizationError, match="multiple revisions"):
        validate_record_protocol_graph(
            protocol=protocol,
            information_set=information,
            candidate=candidate,
            feature_materialization=materialization,
            eligibility=eligibility,
            event=decision,
            registry={source.manifest_id: source, protocol.manifest_id: protocol},
            evidence_registry=evidence_registry,
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
    source, member, bundle, evidence_registry = governed_source_graph()
    protocol, _, _, _, evidence_registry = governed_protocol_graph(
        source,
        member,
        bundle,
        evidence_registry,
    )
    information_set, candidate, materialization, eligibility, decision, _ = (
        protocol_record_graph(
            protocol,
            source,
            evidence_registry,
            information_changes={field: digest(f"wrong-{field}")},
        )
    )
    registry = {source.manifest_id: source, protocol.manifest_id: protocol}
    with pytest.raises(CanonicalizationError, match=message):
        validate_record_protocol_graph(
            protocol=protocol,
            information_set=information_set,
            candidate=candidate,
            feature_materialization=materialization,
            eligibility=eligibility,
            event=decision,
            registry=registry,
            evidence_registry=evidence_registry,
        )


def test_record_graph_rejects_unrelated_or_insufficient_source_manifest() -> None:
    root, root_member, root_bundle, root_evidence = governed_source_graph(
        content_suffix="root"
    )
    protocol, _, _, _, evidence_registry = governed_protocol_graph(
        root,
        root_member,
        root_bundle,
        root_evidence,
    )
    unrelated, _, _, unrelated_evidence = governed_source_graph(
        content_suffix="unrelated"
    )
    evidence_registry.update(unrelated_evidence)
    information_set, candidate, materialization, eligibility, decision, _ = (
        protocol_record_graph(
            protocol,
            unrelated,
            evidence_registry,
        )
    )
    registry = {item.manifest_id: item for item in (root, unrelated, protocol)}
    with pytest.raises(CanonicalizationError, match="not a descendant"):
        validate_record_protocol_graph(
            protocol=protocol,
            information_set=information_set,
            candidate=candidate,
            feature_materialization=materialization,
            eligibility=eligibility,
            event=decision,
            registry=registry,
            evidence_registry=evidence_registry,
        )

    early_source, early_member, early_bundle, early_evidence = governed_source_graph(
        knowledge_cutoff_ts="2026-07-14T09:01:02Z",
        content_suffix="early",
    )
    early_protocol, _, _, _, early_evidence = governed_protocol_graph(
        early_source,
        early_member,
        early_bundle,
        early_evidence,
    )
    information_set, candidate, materialization, eligibility, decision, _ = (
        protocol_record_graph(
            early_protocol,
            early_source,
            early_evidence,
        )
    )
    early_registry = {
        early_source.manifest_id: early_source,
        early_protocol.manifest_id: early_protocol,
    }
    with pytest.raises(CanonicalizationError, match="source knowledge cutoff"):
        validate_record_protocol_graph(
            protocol=early_protocol,
            information_set=information_set,
            candidate=candidate,
            feature_materialization=materialization,
            eligibility=eligibility,
            event=decision,
            registry=early_registry,
            evidence_registry=early_evidence,
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

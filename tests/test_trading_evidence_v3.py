from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import replace

import pytest

from riskyieldmm.trading.canonical import CanonicalizationError, canonical_json_bytes
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
    validate_feature_schema_graph,
    validate_source_bundle_graph,
    validate_source_member_lineage,
)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def source_member(
    name: str = "btc",
    *,
    parent_source_member_id: str | None = None,
    row_count: int = 10,
    event_end_ts: str | None = "2026-07-14T09:00:00Z",
    knowledge_cutoff_ts: str = "2026-07-14T09:01:00Z",
    content_suffix: str = "root",
    source_role: SourceRole = SourceRole.DECISION_INPUT,
    source_field_ids: tuple[str, ...] = ("open", "high", "low", "close", "volume"),
) -> SourceBundleMemberV3:
    return SourceBundleMemberV3(
        source_id=f"exchange-bars-{name}",
        source_role=source_role,
        asset_id=name.upper(),
        venue_id="BINANCE",
        contract_id=f"{name.upper()}-USDT-SPOT",
        timeframe_id="1m",
        source_schema_id=digest(f"member-schema-{name}"),
        source_field_ids=source_field_ids,
        availability_policy_id=digest("first-seen-policy"),
        revision_policy_id=digest("revision-policy"),
        calendar_manifest_id=digest("calendar"),
        semantic_content_root=digest(f"semantic-{name}-{content_suffix}"),
        artifact_hash=digest(f"artifact-{name}-{content_suffix}"),
        row_count=row_count,
        event_start_ts=None if row_count == 0 else "2026-07-14T08:51:00Z",
        event_end_ts=event_end_ts,
        knowledge_cutoff_ts=knowledge_cutoff_ts,
        parent_source_member_id=parent_source_member_id,
    )


def source_bundle(
    members: tuple[SourceBundleMemberV3, ...],
    *,
    parent_source_bundle_id: str | None = None,
    knowledge_cutoff_ts: str = "2026-07-14T09:01:00Z",
) -> SourceBundleV3:
    return SourceBundleV3(
        source_dataset_id="canonical-multiasset-ohlcv",
        source_contract_id=digest("source-contract"),
        source_schema_id=digest("bundle-schema"),
        calendar_manifest_id=digest("calendar"),
        universe_manifest_id=digest("universe"),
        first_seen_policy_id=digest("first-seen-policy"),
        revision_policy_id=digest("revision-policy"),
        vintage_class="LIVE_FIRST_SEEN_CERTIFIED",
        knowledge_cutoff_ts=knowledge_cutoff_ts,
        source_member_ids=tuple(member.source_member_id for member in members),
        parent_source_bundle_id=parent_source_bundle_id,
    )


def observation_slot(
    members: tuple[SourceBundleMemberV3, ...],
    *,
    name: str = "completed_close_window",
) -> FeatureDependencySlotV3:
    return FeatureDependencySlotV3(
        dependency_slot_name=name,
        evidence_kind=EvidenceKind.OBSERVATION,
        selection_mode=DependencySelectionMode.TRAILING_COMPLETED_OBSERVATIONS,
        missing_input_policy=MissingInputPolicy.FAIL,
        cardinality_scope=CardinalityScope.PER_SOURCE_MEMBER,
        minimum_count=1,
        maximum_count=128,
        maximum_age_seconds=7200,
        source_member_keys=tuple(member.source_member_key for member in members),
        source_field_ids=("close",),
        availability_policy_id=digest("first-seen-policy"),
        revision_policy_id=digest("revision-policy"),
    )


def state_slot() -> FeatureDependencySlotV3:
    return FeatureDependencySlotV3(
        dependency_slot_name="prior_regime_state",
        evidence_kind=EvidenceKind.STATE_CHECKPOINT,
        selection_mode=DependencySelectionMode.PRIOR_STATE_CHECKPOINT,
        missing_input_policy=MissingInputPolicy.FAIL,
        cardinality_scope=CardinalityScope.TOTAL,
        minimum_count=1,
        maximum_count=1,
        maximum_age_seconds=86_400,
        state_schema_id=digest("regime-state-schema"),
    )


def protocol_slot() -> FeatureDependencySlotV3:
    return FeatureDependencySlotV3(
        dependency_slot_name="frozen_protocol_constants",
        evidence_kind=EvidenceKind.PROTOCOL_CONSTANT,
        selection_mode=DependencySelectionMode.PROTOCOL_CONSTANT,
        missing_input_policy=MissingInputPolicy.FAIL,
        cardinality_scope=CardinalityScope.TOTAL,
        minimum_count=2,
        maximum_count=2,
        maximum_age_seconds=None,
        protocol_field_names=("barrier_policy_id", "cost_scenario_id"),
    )


def feature(
    name: str,
    *,
    slots: tuple[FeatureDependencySlotV3, ...] = (),
    derived_feature_ids: tuple[str, ...] = (),
) -> FeatureDefinitionV3:
    return FeatureDefinitionV3(
        feature_name=name,
        feature_family="causal-test-family",
        feature_role=FeatureRole.MODEL_INPUT,
        nullable=False,
        transform_hash=digest(f"transform-{name}"),
        transform_parameters_hash=digest(f"parameters-{name}"),
        normalization_hash=digest(f"normalization-{name}"),
        input_dependency_slot_ids=tuple(slot.dependency_slot_id for slot in slots),
        derived_feature_ids=derived_feature_ids,
        candidate_conditioned=False,
    )


def feature_schema(
    bundle: SourceBundleV3,
    slots: tuple[FeatureDependencySlotV3, ...],
    features: tuple[FeatureDefinitionV3, ...],
) -> FeatureSchemaV3:
    return FeatureSchemaV3(
        feature_schema_name="leakage-free-baseline",
        feature_schema_version="1.0.0",
        source_contract_id=bundle.source_contract_id,
        source_schema_id=bundle.source_schema_id,
        dependency_slot_ids=tuple(slot.dependency_slot_id for slot in slots),
        feature_definition_ids=tuple(item.feature_definition_id for item in features),
        frozen_at="2026-07-14T09:02:00Z",
    )


def test_all_evidence_contracts_exact_round_trip_and_tamper_detection() -> None:
    btc = source_member()
    bundle = source_bundle((btc,))
    slot = observation_slot((btc,))
    definition = feature("lagged_close", slots=(slot,))
    schema = feature_schema(bundle, (slot,), (definition,))

    contracts: tuple[
        tuple[object, Callable[[dict[str, object]], object], str, object], ...
    ] = (
        (btc, SourceBundleMemberV3.from_mapping, "row_count", 11),
        (bundle, SourceBundleV3.from_mapping, "source_dataset_id", "alternate-dataset"),
        (slot, FeatureDependencySlotV3.from_mapping, "maximum_age_seconds", 7201),
        (definition, FeatureDefinitionV3.from_mapping, "nullable", True),
        (schema, FeatureSchemaV3.from_mapping, "feature_schema_name", "changed-name"),
    )
    for item, parser, field_name, changed_value in contracts:
        payload = item.as_dict()  # type: ignore[attr-defined]
        assert parser(payload) == item

        unknown = dict(payload)
        unknown["unexpected"] = True
        with pytest.raises(CanonicalizationError, match="keys do not match"):
            parser(unknown)

        tampered = dict(payload)
        tampered[field_name] = changed_value
        with pytest.raises(
            CanonicalizationError, match="does not match canonical content"
        ):
            parser(tampered)


def test_source_member_key_is_stable_but_member_id_binds_content() -> None:
    first = source_member()
    second = source_member(
        parent_source_member_id=first.source_member_id,
        row_count=11,
        event_end_ts="2026-07-14T09:01:00Z",
        knowledge_cutoff_ts="2026-07-14T09:02:00Z",
        content_suffix="child",
    )
    assert second.source_member_key == first.source_member_key
    assert second.source_member_id != first.source_member_id


def test_source_member_field_order_is_part_of_stable_membership() -> None:
    first = source_member(source_field_ids=("open", "close"))
    reversed_order = source_member(source_field_ids=("close", "open"))

    assert first.source_field_ids == ("open", "close")
    assert reversed_order.source_field_ids == ("close", "open")
    assert first.source_member_key != reversed_order.source_member_key


def test_source_bundle_lineage_is_append_only_and_member_clocked() -> None:
    btc = source_member("btc")
    eth = source_member("eth")
    root = source_bundle((btc, eth))
    btc_child = source_member(
        "btc",
        parent_source_member_id=btc.source_member_id,
        row_count=11,
        event_end_ts="2026-07-14T09:01:00Z",
        knowledge_cutoff_ts="2026-07-14T09:02:00Z",
        content_suffix="child",
    )
    child = source_bundle(
        (btc_child, eth),
        parent_source_bundle_id=root.source_bundle_id,
        knowledge_cutoff_ts="2026-07-14T09:02:00Z",
    )
    members = {item.source_member_id: item for item in (btc, eth, btc_child)}
    bundles = {item.source_bundle_id: item for item in (root, child)}
    validate_source_bundle_graph(child, members, bundles)

    removed = source_bundle(
        (btc_child,),
        parent_source_bundle_id=root.source_bundle_id,
        knowledge_cutoff_ts="2026-07-14T09:02:00Z",
    )
    bundles[removed.source_bundle_id] = removed
    with pytest.raises(CanonicalizationError, match="removes member keys"):
        validate_source_bundle_graph(removed, members, bundles)

    unlinked_btc = source_member(
        "btc",
        row_count=11,
        event_end_ts="2026-07-14T09:01:00Z",
        knowledge_cutoff_ts="2026-07-14T09:02:00Z",
        content_suffix="unlinked",
    )
    bad_child = source_bundle(
        (unlinked_btc, eth),
        parent_source_bundle_id=root.source_bundle_id,
        knowledge_cutoff_ts="2026-07-14T09:02:00Z",
    )
    members[unlinked_btc.source_member_id] = unlinked_btc
    bundles[bad_child.source_bundle_id] = bad_child
    with pytest.raises(CanonicalizationError, match="exact predecessor"):
        validate_source_bundle_graph(bad_child, members, bundles)


def test_direct_source_member_lineage_rejects_clock_and_row_count_regression() -> None:
    parent = source_member()
    member_registry = {parent.source_member_id: parent}

    lower_row_count = source_member(
        parent_source_member_id=parent.source_member_id,
        row_count=9,
        event_end_ts="2026-07-14T09:00:00Z",
        knowledge_cutoff_ts="2026-07-14T09:02:00Z",
        content_suffix="lower-count",
    )
    with pytest.raises(CanonicalizationError, match="reduces row_count"):
        validate_source_member_lineage(lower_row_count, member_registry)

    earlier_cutoff = source_member(
        parent_source_member_id=parent.source_member_id,
        row_count=10,
        event_end_ts="2026-07-14T09:00:00Z",
        knowledge_cutoff_ts="2026-07-14T09:00:30Z",
        content_suffix="earlier-cutoff",
    )
    with pytest.raises(CanonicalizationError, match="cutoff must follow"):
        validate_source_member_lineage(earlier_cutoff, member_registry)

    unchanged_content = replace(
        parent,
        row_count=11,
        event_end_ts="2026-07-14T09:01:00Z",
        knowledge_cutoff_ts="2026-07-14T09:02:00Z",
        parent_source_member_id=parent.source_member_id,
    )
    with pytest.raises(CanonicalizationError, match="semantic content root"):
        validate_source_member_lineage(unchanged_content, member_registry)

    reused_artifact = replace(
        parent,
        semantic_content_root=digest("revised-semantic-content"),
        knowledge_cutoff_ts="2026-07-14T09:02:00Z",
        parent_source_member_id=parent.source_member_id,
    )
    with pytest.raises(CanonicalizationError, match="new artifact hash"):
        validate_source_member_lineage(reused_artifact, member_registry)


def test_empty_source_member_can_advance_to_its_first_observed_row() -> None:
    empty = source_member(
        row_count=0,
        event_end_ts=None,
        knowledge_cutoff_ts="2026-07-14T08:50:00Z",
        content_suffix="empty",
    )
    first_row = source_member(
        parent_source_member_id=empty.source_member_id,
        row_count=1,
        event_end_ts="2026-07-14T08:51:00Z",
        knowledge_cutoff_ts="2026-07-14T08:52:00Z",
        content_suffix="first-row",
    )
    validate_source_member_lineage(
        first_row,
        {
            empty.source_member_id: empty,
            first_row.source_member_id: first_row,
        },
    )

    parent_bundle = source_bundle(
        (empty,),
        knowledge_cutoff_ts="2026-07-14T08:50:00Z",
    )
    child_bundle = source_bundle(
        (first_row,),
        parent_source_bundle_id=parent_bundle.source_bundle_id,
        knowledge_cutoff_ts="2026-07-14T08:52:00Z",
    )
    validate_source_bundle_graph(
        child_bundle,
        {
            empty.source_member_id: empty,
            first_row.source_member_id: first_row,
        },
        {
            parent_bundle.source_bundle_id: parent_bundle,
            child_bundle.source_bundle_id: child_bundle,
        },
    )


def test_child_bundle_rejects_retroactively_added_member() -> None:
    btc = source_member("btc")
    parent = source_bundle((btc,))
    eth = source_member(
        "eth",
        knowledge_cutoff_ts="2026-07-14T09:00:30Z",
    )
    child = source_bundle(
        (btc, eth),
        parent_source_bundle_id=parent.source_bundle_id,
        knowledge_cutoff_ts="2026-07-14T09:02:00Z",
    )

    with pytest.raises(CanonicalizationError, match="follow the parent bundle"):
        validate_source_bundle_graph(
            child,
            {item.source_member_id: item for item in (btc, eth)},
            {
                parent.source_bundle_id: parent,
                child.source_bundle_id: child,
            },
        )


def test_nominal_to_live_bundle_requires_a_separate_root_lineage() -> None:
    btc = source_member()
    nominal = replace(
        source_bundle((btc,)),
        vintage_class="NOMINAL_CURRENT_REVISION",
    )
    claimed_live = replace(
        nominal,
        vintage_class="LIVE_FIRST_SEEN_CERTIFIED",
        knowledge_cutoff_ts="2026-07-14T09:02:00Z",
        parent_source_bundle_id=nominal.source_bundle_id,
    )

    with pytest.raises(CanonicalizationError, match="cannot change vintage_class"):
        validate_source_bundle_graph(
            claimed_live,
            {btc.source_member_id: btc},
            {
                nominal.source_bundle_id: nominal,
                claimed_live.source_bundle_id: claimed_live,
            },
        )

    no_op_successor = replace(
        btc,
        knowledge_cutoff_ts="2026-07-14T09:02:00Z",
        parent_source_member_id=btc.source_member_id,
    )
    wrapped_claim = replace(
        nominal,
        vintage_class="LIVE_FIRST_SEEN_CERTIFIED",
        knowledge_cutoff_ts="2026-07-14T09:02:00Z",
        source_member_ids=(no_op_successor.source_member_id,),
        parent_source_bundle_id=nominal.source_bundle_id,
    )
    with pytest.raises(CanonicalizationError, match="separate root lineage"):
        validate_source_bundle_graph(
            wrapped_claim,
            {
                btc.source_member_id: btc,
                no_op_successor.source_member_id: no_op_successor,
            },
            {
                nominal.source_bundle_id: nominal,
                wrapped_claim.source_bundle_id: wrapped_claim,
            },
        )


def test_source_bundle_rejects_duplicate_stable_membership_key() -> None:
    first = source_member()
    alternate_content = source_member(content_suffix="alternate")
    bundle = source_bundle((first, alternate_content))
    members = {item.source_member_id: item for item in (first, alternate_content)}
    with pytest.raises(CanonicalizationError, match="duplicate member keys"):
        validate_source_bundle_graph(
            bundle,
            members,
            {bundle.source_bundle_id: bundle},
        )


def test_dependency_slot_variants_are_closed_and_cardinality_is_finite() -> None:
    btc = source_member()
    for slot in (observation_slot((btc,)), state_slot(), protocol_slot()):
        assert FeatureDependencySlotV3.from_mapping(slot.as_dict()) == slot

    with pytest.raises(CanonicalizationError, match="minimum_count"):
        FeatureDependencySlotV3(
            dependency_slot_name="invalid-cardinality",
            evidence_kind=EvidenceKind.STATE_CHECKPOINT,
            selection_mode=DependencySelectionMode.PRIOR_STATE_CHECKPOINT,
            missing_input_policy=MissingInputPolicy.FAIL,
            cardinality_scope=CardinalityScope.TOTAL,
            minimum_count=2,
            maximum_count=1,
            maximum_age_seconds=60,
            state_schema_id=digest("state"),
        )

    with pytest.raises(CanonicalizationError, match="finite maximum_age"):
        FeatureDependencySlotV3(
            dependency_slot_name="unbounded-observation",
            evidence_kind=EvidenceKind.OBSERVATION,
            selection_mode=DependencySelectionMode.LATEST_AVAILABLE_ASOF,
            missing_input_policy=MissingInputPolicy.ABSTAIN,
            cardinality_scope=CardinalityScope.TOTAL,
            minimum_count=0,
            maximum_count=1,
            maximum_age_seconds=None,
            source_member_keys=(btc.source_member_key,),
            source_field_ids=("close",),
            availability_policy_id=digest("first-seen-policy"),
            revision_policy_id=digest("revision-policy"),
        )

    with pytest.raises(CanonicalizationError, match="LATEST_AVAILABLE_ASOF"):
        FeatureDependencySlotV3(
            dependency_slot_name="multiple-latest-observations",
            evidence_kind=EvidenceKind.OBSERVATION,
            selection_mode=DependencySelectionMode.LATEST_AVAILABLE_ASOF,
            missing_input_policy=MissingInputPolicy.ABSTAIN,
            cardinality_scope=CardinalityScope.PER_SOURCE_MEMBER,
            minimum_count=0,
            maximum_count=2,
            maximum_age_seconds=60,
            source_member_keys=(btc.source_member_key,),
            source_field_ids=("close",),
            availability_policy_id=digest("first-seen-policy"),
            revision_policy_id=digest("revision-policy"),
        )

    with pytest.raises(CanonicalizationError, match="PRIOR_STATE_CHECKPOINT"):
        FeatureDependencySlotV3(
            dependency_slot_name="multiple-prior-states",
            evidence_kind=EvidenceKind.STATE_CHECKPOINT,
            selection_mode=DependencySelectionMode.PRIOR_STATE_CHECKPOINT,
            missing_input_policy=MissingInputPolicy.ABSTAIN,
            cardinality_scope=CardinalityScope.TOTAL,
            minimum_count=0,
            maximum_count=2,
            maximum_age_seconds=60,
            state_schema_id=digest("state"),
        )

    with pytest.raises(CanonicalizationError, match="cardinality"):
        FeatureDependencySlotV3(
            dependency_slot_name="incomplete-protocol-binding",
            evidence_kind=EvidenceKind.PROTOCOL_CONSTANT,
            selection_mode=DependencySelectionMode.PROTOCOL_CONSTANT,
            missing_input_policy=MissingInputPolicy.FAIL,
            cardinality_scope=CardinalityScope.TOTAL,
            minimum_count=1,
            maximum_count=1,
            maximum_age_seconds=None,
            protocol_field_names=("barrier_policy_id", "cost_scenario_id"),
        )


def test_multi_source_feature_schema_graph_resolves_exact_members_and_fields() -> None:
    btc = source_member("btc")
    eth = source_member("eth")
    bundle = source_bundle((btc, eth))
    obs = observation_slot((btc, eth))
    state = state_slot()
    protocol = protocol_slot()
    base = feature("relative_close", slots=(obs, protocol))
    derived = feature(
        "regime_conditioned_relative_close",
        slots=(state,),
        derived_feature_ids=(base.feature_definition_id,),
    )
    schema = feature_schema(bundle, (protocol, obs, state), (base, derived))
    member_registry = {item.source_member_id: item for item in (btc, eth)}
    validate_feature_schema_graph(
        schema,
        {item.dependency_slot_id: item for item in (obs, state, protocol)},
        {item.feature_definition_id: item for item in (base, derived)},
        bundle,
        member_registry,
        {bundle.source_bundle_id: bundle},
    )

    label_source = source_member("label", source_role=SourceRole.LABEL)
    label_bundle = source_bundle((label_source,))
    label_slot = observation_slot((label_source,), name="forbidden-label-input")
    label_feature = feature("leaked_label", slots=(label_slot,))
    label_schema = feature_schema(label_bundle, (label_slot,), (label_feature,))
    with pytest.raises(CanonicalizationError, match="DECISION_INPUT"):
        validate_feature_schema_graph(
            label_schema,
            {label_slot.dependency_slot_id: label_slot},
            {label_feature.feature_definition_id: label_feature},
            label_bundle,
            {label_source.source_member_id: label_source},
            {label_bundle.source_bundle_id: label_bundle},
        )


def test_frozen_feature_schema_accepts_later_live_source_evidence() -> None:
    btc = source_member()
    later_bundle = source_bundle((btc,), knowledge_cutoff_ts="2026-07-14T10:00:00Z")
    slot = observation_slot((btc,))
    definition = feature("frozen_before_live_accrual", slots=(slot,))
    schema = feature_schema(later_bundle, (slot,), (definition,))
    assert schema.frozen_at < later_bundle.knowledge_cutoff_ts
    validate_feature_schema_graph(
        schema,
        {slot.dependency_slot_id: slot},
        {definition.feature_definition_id: definition},
        later_bundle,
        {btc.source_member_id: btc},
        {later_bundle.source_bundle_id: later_bundle},
    )


def test_feature_order_changes_schema_identity_and_forward_reference_fails() -> None:
    btc = source_member()
    bundle = source_bundle((btc,))
    obs = observation_slot((btc,))
    first = feature("first", slots=(obs,))
    second = feature("second", derived_feature_ids=(first.feature_definition_id,))
    forward_order = feature_schema(bundle, (obs,), (second, first))
    causal_order = feature_schema(bundle, (obs,), (first, second))
    assert forward_order.feature_schema_id != causal_order.feature_schema_id

    registries = (
        {obs.dependency_slot_id: obs},
        {item.feature_definition_id: item for item in (first, second)},
        {btc.source_member_id: btc},
        {bundle.source_bundle_id: bundle},
    )
    validate_feature_schema_graph(
        causal_order,
        registries[0],
        registries[1],
        bundle,
        registries[2],
        registries[3],
    )
    with pytest.raises(CanonicalizationError, match="earlier features"):
        validate_feature_schema_graph(
            forward_order,
            registries[0],
            registries[1],
            bundle,
            registries[2],
            registries[3],
        )


def test_feature_schema_rejects_unknown_derived_refs_and_unused_slots() -> None:
    btc = source_member()
    bundle = source_bundle((btc,))
    used = observation_slot((btc,), name="used")
    unused = observation_slot((btc,), name="unused")
    base = feature("base", slots=(used,))
    schema = feature_schema(bundle, (used, unused), (base,))
    with pytest.raises(CanonicalizationError, match="unused slots"):
        validate_feature_schema_graph(
            schema,
            {item.dependency_slot_id: item for item in (used, unused)},
            {base.feature_definition_id: base},
            bundle,
            {btc.source_member_id: btc},
            {bundle.source_bundle_id: bundle},
        )

    unknown_ref = feature("unknown-ref", derived_feature_ids=(digest("not-in-schema"),))
    unknown_schema = feature_schema(bundle, (used,), (base, unknown_ref))
    with pytest.raises(CanonicalizationError, match="outside schema"):
        validate_feature_schema_graph(
            unknown_schema,
            {used.dependency_slot_id: used},
            {
                base.feature_definition_id: base,
                unknown_ref.feature_definition_id: unknown_ref,
            },
            bundle,
            {btc.source_member_id: btc},
            {bundle.source_bundle_id: bundle},
        )


def test_null_with_indicator_policy_requires_an_explicit_bound_indicator() -> None:
    btc = source_member()
    bundle = source_bundle((btc,))
    slot = FeatureDependencySlotV3(
        dependency_slot_name="optional_completed_close",
        evidence_kind=EvidenceKind.OBSERVATION,
        selection_mode=DependencySelectionMode.LATEST_AVAILABLE_ASOF,
        missing_input_policy=MissingInputPolicy.NULL_WITH_INDICATOR,
        cardinality_scope=CardinalityScope.TOTAL,
        minimum_count=1,
        maximum_count=1,
        maximum_age_seconds=7_200,
        source_member_keys=(btc.source_member_key,),
        source_field_ids=("close",),
        availability_policy_id=digest("first-seen-policy"),
        revision_policy_id=digest("revision-policy"),
    )
    value = replace(feature("optional_close", slots=(slot,)), nullable=True)
    schema_without_indicator = feature_schema(bundle, (slot,), (value,))
    registries = (
        {slot.dependency_slot_id: slot},
        {value.feature_definition_id: value},
        {btc.source_member_id: btc},
        {bundle.source_bundle_id: bundle},
    )
    with pytest.raises(CanonicalizationError, match="require.*MISSINGNESS_INDICATOR"):
        validate_feature_schema_graph(
            schema_without_indicator,
            registries[0],
            registries[1],
            bundle,
            registries[2],
            registries[3],
        )

    indicator = FeatureDefinitionV3(
        feature_name="optional_close_missing",
        feature_family="causal-test-family",
        feature_role=FeatureRole.MISSINGNESS_INDICATOR,
        nullable=False,
        transform_hash=digest("transform-optional-close-missing"),
        transform_parameters_hash=digest("parameters-optional-close-missing"),
        normalization_hash=digest("normalization-optional-close-missing"),
        input_dependency_slot_ids=(slot.dependency_slot_id,),
        derived_feature_ids=(),
        candidate_conditioned=False,
    )
    with pytest.raises(CanonicalizationError, match="must be non-nullable"):
        replace(indicator, nullable=True)
    schema = feature_schema(bundle, (slot,), (value, indicator))
    validate_feature_schema_graph(
        schema,
        {slot.dependency_slot_id: slot},
        {
            value.feature_definition_id: value,
            indicator.feature_definition_id: indicator,
        },
        bundle,
        {btc.source_member_id: btc},
        {bundle.source_bundle_id: bundle},
    )

    stray_indicator = replace(indicator, input_dependency_slot_ids=(digest("other"),))
    stray_schema = feature_schema(bundle, (slot,), (value, stray_indicator))
    with pytest.raises(CanonicalizationError, match="outside schema"):
        validate_feature_schema_graph(
            stray_schema,
            {slot.dependency_slot_id: slot},
            {
                value.feature_definition_id: value,
                stray_indicator.feature_definition_id: stray_indicator,
            },
            bundle,
            {btc.source_member_id: btc},
            {bundle.source_bundle_id: bundle},
        )


def test_candidate_conditioning_taints_derived_feature_dag() -> None:
    btc = source_member()
    bundle = source_bundle((btc,))
    slot = observation_slot((btc,))
    conditioned = replace(
        feature("candidate_conditioned_base", slots=(slot,)),
        candidate_conditioned=True,
        candidate_field_names=("side",),
    )
    mislabeled_neutral = feature(
        "mislabeled_neutral_derivative",
        derived_feature_ids=(conditioned.feature_definition_id,),
    )
    schema = feature_schema(
        bundle,
        (slot,),
        (conditioned, mislabeled_neutral),
    )

    with pytest.raises(CanonicalizationError, match="candidate-neutral feature"):
        validate_feature_schema_graph(
            schema,
            {slot.dependency_slot_id: slot},
            {
                conditioned.feature_definition_id: conditioned,
                mislabeled_neutral.feature_definition_id: mislabeled_neutral,
            },
            bundle,
            {btc.source_member_id: btc},
            {bundle.source_bundle_id: bundle},
        )


def test_candidate_fields_are_allowlisted_content_addressed_inputs() -> None:
    btc = source_member()
    bundle = source_bundle((btc,))
    candidate_feature = FeatureDefinitionV3(
        feature_name="candidate_reward_risk",
        feature_family="candidate-economics",
        feature_role=FeatureRole.MODEL_INPUT,
        nullable=False,
        transform_hash=digest("candidate-transform"),
        transform_parameters_hash=digest("candidate-parameters"),
        normalization_hash=digest("candidate-normalization"),
        input_dependency_slot_ids=(),
        derived_feature_ids=(),
        candidate_conditioned=True,
        candidate_field_names=("target_r_multiple", "stop_r_multiple", "side"),
    )
    schema = feature_schema(bundle, (), (candidate_feature,))
    validate_feature_schema_graph(
        schema,
        {},
        {candidate_feature.feature_definition_id: candidate_feature},
        bundle,
        {btc.source_member_id: btc},
        {bundle.source_bundle_id: bundle},
    )
    assert FeatureDefinitionV3.from_mapping(candidate_feature.as_dict()) == (
        candidate_feature
    )

    with pytest.raises(CanonicalizationError, match="sealed allowlist"):
        replace(candidate_feature, candidate_field_names=("record_hash",))
    with pytest.raises(CanonicalizationError, match="candidate-neutral"):
        replace(candidate_feature, candidate_conditioned=False)


def test_representative_2530_feature_schema_remains_finite_and_nonrecursive() -> None:
    btc = source_member()
    bundle = source_bundle((btc,))
    slot = observation_slot((btc,))
    features = tuple(
        feature(f"stress_feature_{index:04d}", slots=(slot,)) for index in range(2_530)
    )
    schema = feature_schema(bundle, (slot,), features)

    validate_feature_schema_graph(
        schema,
        {slot.dependency_slot_id: slot},
        {item.feature_definition_id: item for item in features},
        bundle,
        {btc.source_member_id: btc},
        {bundle.source_bundle_id: bundle},
    )

    assert len(schema.feature_definition_ids) == 2_530
    assert len(canonical_json_bytes(schema.as_dict())) < 1_048_576

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from riskyieldmm.trading.canonical import (
    CanonicalizationError,
    canonical_json_bytes,
)
from riskyieldmm.trading.evidence import DependencySelectionMode
from riskyieldmm.trading.physical_evidence_v4 import (
    PHYSICAL_RESULT_LEAF_DOMAIN_V4,
    V4_MAX_SELECTION_RESULTS,
)
from riskyieldmm.trading.physical_market_data import (
    ContinuityPolicy,
    SelectionStatus,
)
from riskyieldmm.trading.physical_selection_v4 import (
    V4_SELECTION_INTERVAL_SECONDS,
    V4_SELECTION_TIE_BREAK_POLICY,
    DependencySelectionProofV4,
    ObservationSelectionProofV4,
    PhysicalProtocolBindingV4,
    SelectionResultChunkV4,
    selection_mode_name_v4,
    selection_result_leaf_input_v4,
    selection_result_root_v4,
    validate_observation_selection_proof_v4,
)
from riskyieldmm.trading.transparency_log import (
    rfc9162_empty_root,
    rfc9162_tree_hash,
)

UTC = timezone.utc
T0 = datetime(2026, 7, 14, 12, 0, tzinfo=UTC)


def digest(value: object) -> str:
    return hashlib.sha256(str(value).encode()).hexdigest()


def binding(
    *,
    mode: DependencySelectionMode | str = (
        DependencySelectionMode.TRAILING_COMPLETED_OBSERVATIONS
    ),
    requested_count: int = 3,
    continuity_policy: ContinuityPolicy = ContinuityPolicy.STRICT_INTERVAL_GRID,
    suffix: str = "base",
) -> PhysicalProtocolBindingV4:
    return PhysicalProtocolBindingV4(
        physical_scope_manifest_id=digest(f"scope-{suffix}"),
        protocol_manifest_id=digest(f"protocol-{suffix}"),
        source_manifest_id=digest(f"source-{suffix}"),
        calendar_manifest_id=digest(f"calendar-{suffix}"),
        feature_schema_id=digest(f"schema-{suffix}"),
        dependency_slot_id=digest(f"slot-{suffix}"),
        source_member_id=digest(f"member-{suffix}"),
        source_member_key=digest(f"member-key-{suffix}"),
        observation_selection_policy_id=digest(f"selector-{suffix}"),
        selection_mode=mode,
        anchor_lag_intervals=1,
        requested_count=requested_count,
        maximum_age_seconds=600,
        continuity_policy=continuity_policy,
        frozen_at=T0,
    )


def result_chunk(
    item_binding: PhysicalProtocolBindingV4,
    revision_ids: tuple[str, ...],
    *,
    evidence_cutoff_id: str | None = None,
) -> SelectionResultChunkV4:
    return SelectionResultChunkV4(
        physical_scope_manifest_id=item_binding.physical_scope_manifest_id,
        physical_protocol_binding_id=(item_binding.physical_protocol_binding_id),
        evidence_cutoff_id=(
            digest("cutoff") if evidence_cutoff_id is None else evidence_cutoff_id
        ),
        ordered_observation_revision_ids=revision_ids,
    )


def selected_proof(
    item_binding: PhysicalProtocolBindingV4,
    chunk: SelectionResultChunkV4,
    **overrides: object,
) -> ObservationSelectionProofV4:
    values: dict[str, object] = {
        "physical_scope_manifest_id": item_binding.physical_scope_manifest_id,
        "ledger_id": digest("ledger"),
        "evidence_cutoff_id": chunk.evidence_cutoff_id,
        "cutoff_global_sequence": 42,
        "cutoff_receipt_hash": digest("cutoff-receipt"),
        "knowledge_cutoff_ts": T0,
        "physical_protocol_binding_id": (item_binding.physical_protocol_binding_id),
        "selection_query_spec_id": item_binding.selection_query_spec_id,
        "observation_selection_policy_id": (
            item_binding.observation_selection_policy_id
        ),
        "dependency_slot_id": item_binding.dependency_slot_id,
        "source_member_id": item_binding.source_member_id,
        "source_member_key": item_binding.source_member_key,
        "observation_cutoff_ts": T0,
        "status": SelectionStatus.SELECTED,
        "selected_result_count": chunk.selected_result_count,
        "selected_result_root": chunk.selected_result_root,
        "selection_result_chunk_id": chunk.selection_result_chunk_id,
        "abstention_reason_codes": (),
        "computed_at": T0,
    }
    values.update(overrides)
    return ObservationSelectionProofV4(**values)


def abstention_proof(
    item_binding: PhysicalProtocolBindingV4,
) -> ObservationSelectionProofV4:
    return ObservationSelectionProofV4(
        physical_scope_manifest_id=item_binding.physical_scope_manifest_id,
        ledger_id=digest("ledger"),
        evidence_cutoff_id=digest("cutoff"),
        cutoff_global_sequence=42,
        cutoff_receipt_hash=digest("cutoff-receipt"),
        knowledge_cutoff_ts=T0,
        physical_protocol_binding_id=(item_binding.physical_protocol_binding_id),
        selection_query_spec_id=item_binding.selection_query_spec_id,
        observation_selection_policy_id=(item_binding.observation_selection_policy_id),
        dependency_slot_id=item_binding.dependency_slot_id,
        source_member_id=item_binding.source_member_id,
        source_member_key=item_binding.source_member_key,
        observation_cutoff_ts=T0,
        status=SelectionStatus.ABSTAIN,
        selected_result_count=0,
        selected_result_root=rfc9162_empty_root().hex(),
        selection_result_chunk_id=None,
        abstention_reason_codes=("NO_COMPLETE_OBSERVATION",),
        computed_at=T0,
    )


def test_v4_selection_contracts_round_trip_and_alias() -> None:
    item_binding = binding()
    chunk = result_chunk(
        item_binding, tuple(digest(f"revision-{index}") for index in range(3))
    )
    proof = selected_proof(item_binding, chunk)
    abstention = abstention_proof(item_binding)

    assert (
        PhysicalProtocolBindingV4.from_mapping(item_binding.as_dict()) == item_binding
    )
    assert SelectionResultChunkV4.from_mapping(chunk.as_dict()) == chunk
    assert ObservationSelectionProofV4.from_mapping(proof.as_dict()) == proof
    assert ObservationSelectionProofV4.from_mapping(abstention.as_dict()) == abstention
    assert DependencySelectionProofV4 is ObservationSelectionProofV4
    assert proof.dependency_selection_proof_id == proof.observation_selection_proof_id


@pytest.mark.parametrize(
    ("mode", "wire_name"),
    [
        (DependencySelectionMode.EXACT_EVENT, "EXACT_EVENT"),
        (DependencySelectionMode.LATEST_AVAILABLE_ASOF, "LATEST_AVAILABLE_ASOF"),
        (
            DependencySelectionMode.TRAILING_COMPLETED_OBSERVATIONS,
            "TRAILING_WINDOW",
        ),
        ("TRAILING_COMPLETED_OBSERVATIONS", "TRAILING_WINDOW"),
        ("TRAILING_WINDOW", "TRAILING_WINDOW"),
    ],
)
def test_selection_modes_have_one_canonical_v4_wire_name(
    mode: DependencySelectionMode | str, wire_name: str
) -> None:
    count = 3 if wire_name == "TRAILING_WINDOW" else 1
    item = binding(mode=mode, requested_count=count)

    assert item.as_dict()["selection_mode"] == wire_name
    assert selection_mode_name_v4(mode) == wire_name
    assert PhysicalProtocolBindingV4.from_mapping(item.as_dict()) == item


def test_legacy_trailing_wire_name_and_unsupported_policy_shapes_fail_closed() -> None:
    item = binding()
    legacy = item.as_dict()
    legacy["selection_mode"] = "TRAILING_COMPLETED_OBSERVATIONS"
    with pytest.raises(CanonicalizationError, match="must be TRAILING_WINDOW"):
        PhysicalProtocolBindingV4.from_mapping(legacy)

    for mode in (
        DependencySelectionMode.EXACT_EVENT,
        DependencySelectionMode.LATEST_AVAILABLE_ASOF,
    ):
        with pytest.raises(CanonicalizationError, match="requires one row"):
            binding(mode=mode, requested_count=2)
    with pytest.raises(CanonicalizationError, match="STRICT_INTERVAL_GRID"):
        binding(
            continuity_policy=ContinuityPolicy.SPARSE_WITH_LIVENESS,
        )
    with pytest.raises(CanonicalizationError, match="interval_seconds"):
        replace(item, interval_seconds=300)
    with pytest.raises(CanonicalizationError, match="tie-break"):
        replace(item, tie_break_policy="AVAILABLE_AT_THEN_REVISION_ID")


def test_protocol_binding_serializes_every_frozen_selector_and_scope_field() -> None:
    item = binding()
    payload = item.as_dict()
    expected_fields = {
        "physical_scope_manifest_id",
        "protocol_manifest_id",
        "source_manifest_id",
        "calendar_manifest_id",
        "feature_schema_id",
        "dependency_slot_id",
        "source_member_id",
        "source_member_key",
        "observation_selection_policy_id",
        "selection_mode",
        "anchor_lag_intervals",
        "requested_count",
        "maximum_age_seconds",
        "continuity_policy",
        "selection_query_spec_id",
        "interval_seconds",
        "tie_break_policy",
        "frozen_at",
    }

    assert expected_fields <= payload.keys()
    assert payload["interval_seconds"] == V4_SELECTION_INTERVAL_SECONDS
    assert payload["tie_break_policy"] == V4_SELECTION_TIE_BREAK_POLICY
    assert payload["source_member_key"] == item.source_member_key
    with pytest.raises(CanonicalizationError, match="source_member_key"):
        replace(item, source_member_key="BTCUSDT-1m")

    substitutions = (
        ("physical_scope_manifest_id", digest("other-scope")),
        ("protocol_manifest_id", digest("other-protocol")),
        ("source_manifest_id", digest("other-source")),
        ("calendar_manifest_id", digest("other-calendar")),
        ("feature_schema_id", digest("other-schema")),
        ("dependency_slot_id", digest("other-slot")),
        ("source_member_id", digest("other-member")),
        ("source_member_key", digest("other-member-key")),
        ("observation_selection_policy_id", digest("other-policy")),
        ("anchor_lag_intervals", 2),
        ("maximum_age_seconds", 601),
        ("frozen_at", T0 + timedelta(seconds=1)),
    )
    for field_name, value in substitutions:
        assert replace(item, **{field_name: value}).physical_protocol_binding_id != (
            item.physical_protocol_binding_id
        )


def test_result_root_is_independent_rfc9162_commitment_to_order_and_ordinal() -> None:
    revision_ids = tuple(digest(f"revision-{index}") for index in range(3))
    expected_leaves = tuple(
        canonical_json_bytes(
            {
                "domain": PHYSICAL_RESULT_LEAF_DOMAIN_V4,
                "observation_revision_id": revision_id,
                "ordinal": ordinal,
            }
        )
        for ordinal, revision_id in enumerate(revision_ids)
    )

    assert (
        selection_result_root_v4(revision_ids)
        == rfc9162_tree_hash(expected_leaves).hex()
    )
    assert (
        selection_result_leaf_input_v4(
            ordinal=0, observation_revision_id=revision_ids[0]
        )
        == expected_leaves[0]
    )
    assert selection_result_leaf_input_v4(
        ordinal=0, observation_revision_id=revision_ids[0]
    ) != selection_result_leaf_input_v4(
        ordinal=1, observation_revision_id=revision_ids[0]
    )
    assert selection_result_root_v4(revision_ids) != selection_result_root_v4(
        revision_ids[::-1]
    )


def test_result_cardinality_and_duplicate_boundaries_are_exact() -> None:
    item_binding = binding(requested_count=1)
    revision_ids = tuple(
        digest(f"revision-{index}") for index in range(V4_MAX_SELECTION_RESULTS + 1)
    )

    assert selection_result_root_v4(()) == rfc9162_empty_root().hex()
    with pytest.raises(CanonicalizationError, match="must not be empty"):
        result_chunk(item_binding, ())

    one = result_chunk(item_binding, revision_ids[:1])
    maximum = result_chunk(item_binding, revision_ids[:V4_MAX_SELECTION_RESULTS])
    assert one.selected_result_count == 1
    assert maximum.selected_result_count == V4_MAX_SELECTION_RESULTS

    with pytest.raises(CanonicalizationError, match="exceeds 256"):
        result_chunk(item_binding, revision_ids)
    with pytest.raises(CanonicalizationError, match="exceeds 256"):
        selection_result_root_v4(revision_ids)
    with pytest.raises(CanonicalizationError, match="duplicate"):
        result_chunk(item_binding, (revision_ids[0], revision_ids[0]))
    with pytest.raises(CanonicalizationError, match="duplicate"):
        selection_result_root_v4((revision_ids[0], revision_ids[0]))


def test_reordering_and_context_substitution_change_chunk_identity() -> None:
    item_binding = binding()
    revision_ids = tuple(digest(f"revision-{index}") for index in range(3))
    original = result_chunk(item_binding, revision_ids)
    reordered = result_chunk(item_binding, revision_ids[::-1])
    other_cutoff = result_chunk(
        item_binding,
        revision_ids,
        evidence_cutoff_id=digest("other-cutoff"),
    )
    other_binding = result_chunk(binding(suffix="other"), revision_ids)

    assert original.selected_result_root != reordered.selected_result_root
    assert original.selection_result_chunk_id != reordered.selection_result_chunk_id
    assert original.selected_result_root == other_cutoff.selected_result_root
    assert original.selection_result_chunk_id != other_cutoff.selection_result_chunk_id
    assert original.selection_result_chunk_id != other_binding.selection_result_chunk_id


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("selected_result_count", 2),
        ("selected_result_root", digest("tampered-root")),
        ("selection_result_chunk_id", digest("tampered-chunk")),
    ],
)
def test_serialized_chunk_tampering_is_rejected(field: str, value: object) -> None:
    item_binding = binding(requested_count=1)
    chunk = result_chunk(item_binding, (digest("revision"),))
    payload = chunk.as_dict()
    payload[field] = value

    with pytest.raises(CanonicalizationError):
        SelectionResultChunkV4.from_mapping(payload)


def test_selected_and_abstention_proof_shapes_and_exact_cutoff() -> None:
    item_binding = binding(requested_count=1)
    chunk = result_chunk(item_binding, (digest("revision"),))
    selected = selected_proof(item_binding, chunk)
    abstention = abstention_proof(item_binding)

    assert selected.status is SelectionStatus.SELECTED
    assert abstention.status is SelectionStatus.ABSTAIN
    assert abstention.selected_result_count == 0
    assert abstention.selection_result_chunk_id is None
    assert abstention.selected_result_root == rfc9162_empty_root().hex()

    with pytest.raises(CanonicalizationError, match="non-empty chunk"):
        selected_proof(item_binding, chunk, selection_result_chunk_id=None)
    with pytest.raises(CanonicalizationError, match="no reasons"):
        selected_proof(
            item_binding,
            chunk,
            abstention_reason_codes=("UNEXPECTED_REASON",),
        )
    with pytest.raises(CanonicalizationError, match="exact knowledge/observation"):
        selected_proof(
            item_binding,
            chunk,
            observation_cutoff_ts=T0 - timedelta(microseconds=1),
        )
    with pytest.raises(CanonicalizationError, match="computed before"):
        selected_proof(
            item_binding,
            chunk,
            computed_at=T0 - timedelta(microseconds=1),
        )
    with pytest.raises(CanonicalizationError, match="zero count"):
        replace(abstention, selected_result_count=1)


def test_cross_binding_and_result_validation_rejects_every_substitution() -> None:
    item_binding = binding()
    revision_ids = tuple(digest(f"revision-{index}") for index in range(3))
    chunk = result_chunk(item_binding, revision_ids)
    proof = selected_proof(item_binding, chunk)
    validate_observation_selection_proof_v4(
        proof=proof, binding=item_binding, chunk=chunk
    )

    with pytest.raises(CanonicalizationError, match="protocol binding"):
        validate_observation_selection_proof_v4(
            proof=proof,
            binding=binding(suffix="other"),
            chunk=chunk,
        )
    with pytest.raises(CanonicalizationError, match="different result chunk"):
        validate_observation_selection_proof_v4(
            proof=proof,
            binding=item_binding,
            chunk=result_chunk(item_binding, revision_ids[::-1]),
        )
    with pytest.raises(CanonicalizationError, match="requires its chunk"):
        validate_observation_selection_proof_v4(
            proof=proof, binding=item_binding, chunk=None
        )
    with pytest.raises(CanonicalizationError, match="cannot resolve a chunk"):
        validate_observation_selection_proof_v4(
            proof=abstention_proof(item_binding),
            binding=item_binding,
            chunk=chunk,
        )

    substituted_context_chunk = result_chunk(
        item_binding,
        revision_ids,
        evidence_cutoff_id=digest("other-cutoff"),
    )
    proof_claiming_substituted_chunk = selected_proof(
        item_binding,
        substituted_context_chunk,
        evidence_cutoff_id=chunk.evidence_cutoff_id,
    )
    with pytest.raises(CanonicalizationError, match="changes proof context"):
        validate_observation_selection_proof_v4(
            proof=proof_claiming_substituted_chunk,
            binding=item_binding,
            chunk=substituted_context_chunk,
        )


def test_cross_validation_enforces_requested_count_and_repeated_binding_fields() -> (
    None
):
    item_binding = binding(requested_count=3)
    short_chunk = result_chunk(
        item_binding, (digest("revision-0"), digest("revision-1"))
    )
    short_proof = selected_proof(item_binding, short_chunk)
    with pytest.raises(CanonicalizationError, match="requested_count"):
        validate_observation_selection_proof_v4(
            proof=short_proof,
            binding=item_binding,
            chunk=short_chunk,
        )

    substituted_binding = replace(item_binding, dependency_slot_id=digest("other-slot"))
    forged = replace(
        selected_proof(
            item_binding,
            result_chunk(
                item_binding,
                (digest("revision-0"), digest("revision-1"), digest("revision-2")),
            ),
        ),
        physical_protocol_binding_id=(substituted_binding.physical_protocol_binding_id),
    )
    with pytest.raises(CanonicalizationError, match="dependency_slot_id"):
        validate_observation_selection_proof_v4(
            proof=forged,
            binding=substituted_binding,
            chunk=None,
        )


def test_serialized_binding_proof_and_chunk_identity_tampering_is_rejected() -> None:
    item_binding = binding(requested_count=1)
    chunk = result_chunk(item_binding, (digest("revision"),))
    proof = selected_proof(item_binding, chunk)

    binding_payload = item_binding.as_dict()
    binding_payload["physical_protocol_binding_id"] = digest("tampered-binding")
    with pytest.raises(CanonicalizationError, match="canonical content"):
        PhysicalProtocolBindingV4.from_mapping(binding_payload)

    chunk_payload = chunk.as_dict()
    chunk_payload["selection_result_chunk_id"] = digest("tampered-chunk")
    with pytest.raises(CanonicalizationError, match="canonical content"):
        SelectionResultChunkV4.from_mapping(chunk_payload)

    proof_payload = proof.as_dict()
    proof_payload["observation_selection_proof_id"] = digest("tampered-proof")
    with pytest.raises(CanonicalizationError, match="canonical content"):
        ObservationSelectionProofV4.from_mapping(proof_payload)

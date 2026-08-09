from __future__ import annotations

import argparse
import copy
import hashlib
import importlib
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

_MODULE_NAME = "riskyieldmm.trading.physical_transport_capacity_contracts_v49f_v8"
_MODULE_BASENAME = "physical_transport_capacity_contracts_v49f_v8"
_GOLDEN_RELATIVE_PATH = "tests/raw_v8_step2_inventory_v49f.json"
_INVENTORY_SCHEMA_VERSION = "riskyieldmm.raw_v8_step2_inventory.v3"
_SCHEMA_VERSION = "riskyieldmm_physical_transport_a2m_raw_v49f_v8"
_EXTERNAL_SCHEMA_REGISTRY_DOMAIN = (
    "RiskYieldMMA2MStep2ExternalSchemaRegistryV2V4_9F_RawV8"
)
_EXTERNAL_TYPE_DESCRIPTOR_DOMAIN = (
    "RiskYieldMMA2MStep2ExternalTypeDescriptorV2V4_9F_RawV8"
)
_EXTERNAL_SCHEMA_REGISTRY_ID = (
    "5dc95a3e99c5646e912b6a7e9c3970cf2489d560ea890b0a19d38af4c51c2140"
)
_EXTERNAL_SCHEMA_REGISTRY_IDENTITY_PAYLOAD_MEMBERS = (
    "external_schema_profile",
    "unicode_source_catalog",
    "identifier_profile_catalog",
    "ascii_dfa_catalog",
    "text_language_catalog",
    "value_schema_catalog",
    "external_type_descriptor_count",
    "ordered_external_type_descriptors",
    "cross_field_rule_descriptor_count",
    "ordered_cross_field_rule_descriptors",
    "fixed_position_resolver_profile_catalog",
    "rule_application_descriptor_count",
    "ordered_rule_application_descriptors",
    "schema_graph_node_count",
    "ordered_schema_graph_node_names",
)
_OPERATIONS = (
    "ACK_DEADLINE_EXPIRY",
    "INGRESS",
    "LOCAL_SHUTDOWN",
    "SUBSCRIPTION_DISPATCH",
)
_PLACEHOLDER_FIELD_REASON_BY_CONTEXT_REASON = {
    "ARTIFACT_BOUND_EXCEEDED": ("CHECKPOINT_PLACEHOLDER_ARTIFACT_BOUND_EXCEEDED"),
    "OBSERVER_INTERNAL_ERROR": ("CHECKPOINT_PLACEHOLDER_OBSERVER_INTERNAL_ERROR"),
    "SOURCE_CLOCK_UNAVAILABLE": ("CHECKPOINT_PLACEHOLDER_SOURCE_CLOCK_UNAVAILABLE"),
    "TARGET_BOUNDARY_NOT_REACHED": (
        "CHECKPOINT_PLACEHOLDER_TARGET_BOUNDARY_NOT_REACHED"
    ),
}
_PLACEHOLDER_PREDICATE_BY_FIELD_REASON = {
    "CHECKPOINT_PLACEHOLDER_ARTIFACT_BOUND_EXCEEDED": (
        "V2_CHECKPOINT_PLACEHOLDER_ARTIFACT_BOUND"
    ),
    "CHECKPOINT_PLACEHOLDER_OBSERVER_INTERNAL_ERROR": (
        "V2_CHECKPOINT_PLACEHOLDER_OBSERVER_INTERNAL_ERROR"
    ),
    "CHECKPOINT_PLACEHOLDER_SOURCE_CLOCK_UNAVAILABLE": (
        "V2_CHECKPOINT_PLACEHOLDER_SOURCE_CLOCK_UNAVAILABLE"
    ),
    "CHECKPOINT_PLACEHOLDER_TARGET_BOUNDARY_NOT_REACHED": (
        "V2_CHECKPOINT_PLACEHOLDER_TARGET_BOUNDARY_NOT_REACHED"
    ),
}
_EXPECTED_FIXTURE_KEYS = frozenset(
    {
        "counter_snapshot",
        "dispatch_window_evidence",
        "due_decision_clock_evidence",
        "local_shutdown_boundary_spec",
        "one_field_mutation_metadata",
        "operation_declaration",
        "operation_results",
        "operation_specs",
        "target_observation_v2_fixtures",
    }
)

_DOMAIN_TO_CLASS_NAME = {
    "RiskYieldMMA2MOperationSpecV4_9F_RawV8": (
        "CapacityMeasurementOperationSpecV49FV8"
    ),
    "RiskYieldMMA2MOperationDeclarationV4_9F_RawV8": (
        "CapacityMeasurementOperationDeclarationV49FV8"
    ),
    "RiskYieldMMA2MDispatchWindowEvidenceV4_9F_RawV8": (
        "CapacityMeasurementDispatchWindowEvidenceV49FV8"
    ),
    "RiskYieldMMA2MDueDecisionClockEvidenceV4_9F_RawV8": (
        "CapacityMeasurementAckDueDecisionClockEvidenceV49FV8"
    ),
    "RiskYieldMMA2MOperationResultEvidenceV4_9F_RawV8": (
        "CapacityMeasurementOperationResultEvidenceV49FV8"
    ),
    "RiskYieldMMA2MTargetFieldRegistryV4_9F_RawV8": (
        "CapacityMeasurementTargetFieldRegistryV49FV8"
    ),
    "RiskYieldMMA2MSourceErrorDetailV4_9F_RawV8": (
        "CapacityMeasurementSourceErrorDetailV49FV8"
    ),
    "RiskYieldMMA2MTargetFieldObservationV4_9F_RawV8": (
        "CapacityMeasurementTargetFieldObservationV49FV8"
    ),
    "RiskYieldMMA2MIngressLogicalOracleProfileV1V4_9F_RawV8": (
        "CapacityMeasurementIngressLogicalOracleProfileV49FV8"
    ),
    "RiskYieldMMA2MMarkerContractV1V4_9F_RawV8": (
        "CapacityMeasurementMarkerContractV49FV8"
    ),
    "RiskYieldMMA2MCheckpointSelectorEntryV1V4_9F_RawV8": (
        "CapacityMeasurementCheckpointSelectorEntryV49FV8"
    ),
    "RiskYieldMMA2MCheckpointSelectorV1V4_9F_RawV8": (
        "CapacityMeasurementCheckpointSelectorV49FV8"
    ),
    "RiskYieldMMA2MTargetObservationContextV2V4_9F_RawV8": (
        "CapacityMeasurementTargetObservationContextV2V49FV8"
    ),
    "RiskYieldMMA2MTargetObservationV2V4_9F_RawV8": (
        "CapacityMeasurementTargetObservationV2V49FV8"
    ),
    "RiskYieldMMA2MTargetObservationRootV2V4_9F_RawV8": (
        "CapacityMeasurementTargetObservationRootV2V49FV8"
    ),
    "RiskYieldMMA2MOperationCounterSnapshotSchemaV4_9F_RawV8": (
        "CapacityMeasurementOperationCounterSnapshotSchemaV49FV8"
    ),
}

_DOMAIN_TO_IDENTITY_FIELD = {
    "RiskYieldMMA2MOperationSpecV4_9F_RawV8": "operation_spec_id",
    "RiskYieldMMA2MOperationDeclarationV4_9F_RawV8": "declaration_id",
    "RiskYieldMMA2MDispatchWindowEvidenceV4_9F_RawV8": ("dispatch_window_evidence_id"),
    "RiskYieldMMA2MDueDecisionClockEvidenceV4_9F_RawV8": (
        "due_decision_clock_evidence_id"
    ),
    "RiskYieldMMA2MOperationResultEvidenceV4_9F_RawV8": "result_evidence_id",
    "RiskYieldMMA2MTargetFieldRegistryV4_9F_RawV8": "target_field_registry_id",
    "RiskYieldMMA2MSourceErrorDetailV4_9F_RawV8": "source_error_detail_sha256",
    "RiskYieldMMA2MTargetFieldObservationV4_9F_RawV8": "field_observation_id",
    "RiskYieldMMA2MIngressLogicalOracleProfileV1V4_9F_RawV8": (
        "logical_oracle_profile_id"
    ),
    "RiskYieldMMA2MMarkerContractV1V4_9F_RawV8": "marker_contract_id",
    "RiskYieldMMA2MCheckpointSelectorEntryV1V4_9F_RawV8": (
        "checkpoint_selector_entry_id"
    ),
    "RiskYieldMMA2MCheckpointSelectorV1V4_9F_RawV8": "checkpoint_selector_id",
    "RiskYieldMMA2MTargetObservationContextV2V4_9F_RawV8": ("observation_context_id"),
    "RiskYieldMMA2MTargetObservationV2V4_9F_RawV8": "observation_id",
    "RiskYieldMMA2MTargetObservationRootV2V4_9F_RawV8": (
        "target_observation_root_sha256"
    ),
    "RiskYieldMMA2MOperationCounterSnapshotSchemaV4_9F_RawV8": ("counter_schema_id"),
}

_CONTEXT_PAYLOAD_KEYS = (
    "observation_role",
    "operation_kind",
    "instrumentation_mode",
    "candidate_id",
    "attempt_id",
    "target_field_registry_id",
    "marker_ordinal",
    "checkpoint_marker_kind",
    "full_checkpoint_selector_id",
    "checkpoint_selector_position",
    "checkpoint_selector_entry_id",
    "expected_checkpoint_marker_kind",
    "expected_occurrence_index_within_kind",
    "checkpoint_binding_status",
    "checkpoint_binding_unavailable_reason",
    "observer_clock_span",
    "boottime_clock_span",
    "loop_clock_span",
)


class HarnessFailure(AssertionError):
    pass


class _MappingSubclass(dict[str, Any]):
    pass


class _IntSubclass(int):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise HarnessFailure(message)


def _reject_json_constant(value: str) -> Any:
    raise HarnessFailure(f"golden contains non-finite JSON constant: {value}")


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise HarnessFailure(f"golden contains duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_golden(repository_root: Path) -> dict[str, Any]:
    path = repository_root / _GOLDEN_RELATIVE_PATH
    _require(path.is_file(), f"Raw V8 Step-2 golden is absent: {path}")
    raw = path.read_bytes()
    value = json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=_strict_object,
        parse_constant=_reject_json_constant,
    )
    _require(type(value) is dict, "Raw V8 Step-2 golden root is not an exact object")
    expected = {
        "checkpoint_selector_catalog",
        "external_schema_registry_v2",
        "fixture_records",
        "ingress_logical_oracle_profile_catalog",
        "inventory_sha256",
        "invariants",
        "marker_contract",
        "normative_document_inputs",
        "operation_contracts",
        "operation_counter_schema",
        "schema_version",
        "target_field_registry",
    }
    _require(set(value) == expected, "Raw V8 Step-2 golden root keys differ")
    _require(
        value["schema_version"] == _INVENTORY_SCHEMA_VERSION,
        "Raw V8 Step-2 golden inventory schema version differs",
    )
    _require(
        value["invariants"]["measurement_schema_version"] == _SCHEMA_VERSION,
        "Raw V8 measurement schema version differs",
    )
    fixtures = value["fixture_records"]
    _require(type(fixtures) is dict, "fixture_records is not an exact object")
    _require(
        set(fixtures) == _EXPECTED_FIXTURE_KEYS,
        "fixture_records keys differ from the frozen grouping",
    )
    for group in ("operation_specs", "operation_results"):
        records = fixtures[group]
        _require(type(records) is dict, f"{group} is not an exact object")
        _require(set(records) == set(_OPERATIONS), f"{group} operation set differs")
    observation_fixtures = fixtures["target_observation_v2_fixtures"]
    _require(
        type(observation_fixtures) is dict
        and set(observation_fixtures)
        == {
            "attempted_on_empty_selector_target_observation_roots",
            "checkpoint_exact_marker_observation",
            "checkpoint_placeholder_observations",
            "maximum_selector_target_observation_root",
            "off_target_observation_root",
            "off_target_observations",
        },
        "target_observation_v2_fixtures keys differ",
    )
    observations = observation_fixtures["off_target_observations"]
    _require(
        type(observations) is list and len(observations) == 3,
        "target_observations must contain the exact three OFF records",
    )
    canonical_root = copy.deepcopy(value)
    inventory_sha256 = canonical_root.pop("inventory_sha256")
    _require(
        inventory_sha256
        == hashlib.sha256(
            json.dumps(
                canonical_root,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest(),
        "Raw V8 Step-2 inventory semantic hash differs",
    )
    return value


def _walk_mappings(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if type(value) is dict:
        found.append(value)
        for child in value.values():
            found.extend(_walk_mappings(child))
    elif type(value) is list:
        for child in value:
            found.extend(_walk_mappings(child))
    return found


def _v2_observation_fixtures(golden: Mapping[str, Any]) -> Mapping[str, Any]:
    value = golden["fixture_records"]["target_observation_v2_fixtures"]
    _require(type(value) is dict, "V2 observation fixtures are not an exact object")
    return value


def _off_observations(golden: Mapping[str, Any]) -> list[dict[str, Any]]:
    value = _v2_observation_fixtures(golden)["off_target_observations"]
    _require(type(value) is list, "OFF observations are not an exact array")
    return value


def _off_observation_root(golden: Mapping[str, Any]) -> dict[str, Any]:
    value = _v2_observation_fixtures(golden)["off_target_observation_root"]
    _require(type(value) is dict, "OFF observation root is not an exact object")
    return value


def _find_domain(value: Any, domain: str) -> dict[str, Any]:
    matches = [
        item for item in _walk_mappings(value) if item.get("record_domain") == domain
    ]
    _require(len(matches) == 1, f"expected one {domain} record, found {len(matches)}")
    return matches[0]


def _find_exact_key_mapping(value: Any, keys: set[str]) -> dict[str, Any]:
    matches = [item for item in _walk_mappings(value) if set(item) == keys]
    _require(
        len(matches) == 1,
        f"expected one nested mapping with keys {sorted(keys)}, found {len(matches)}",
    )
    return matches[0]


def _canonical_bytes(item: Any) -> bytes:
    value = item.canonical_bytes
    result = value() if callable(value) else value
    _require(type(result) is bytes, "canonical_bytes is not exact bytes")
    return result


def _semantic_id(canonical: Any, *, domain: str, payload: Mapping[str, Any]) -> str:
    return canonical.sha256_digest(
        {
            "canonicalization_version": canonical.CANONICALIZATION_VERSION,
            "domain": domain,
            "payload": dict(payload),
            "schema_version": _SCHEMA_VERSION,
        }
    )


def _rehash(canonical: Any, record: dict[str, Any]) -> dict[str, Any]:
    domain = record["record_domain"]
    identity_field = _DOMAIN_TO_IDENTITY_FIELD[domain]
    payload = {
        key: value
        for key, value in record.items()
        if key
        not in {
            "canonicalization_version",
            "measurement_schema_version",
            "record_domain",
            identity_field,
        }
    }
    record[identity_field] = _semantic_id(canonical, domain=domain, payload=payload)
    return record


def _standalone_record(
    canonical: Any,
    *,
    domain: str,
    identity_field: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    identity = _semantic_id(canonical, domain=domain, payload=payload)
    return {
        "canonicalization_version": canonical.CANONICALIZATION_VERSION,
        "measurement_schema_version": _SCHEMA_VERSION,
        "record_domain": domain,
        **dict(payload),
        identity_field: identity,
    }


def _context_envelope_from_observation(
    canonical: Any,
    observation: Mapping[str, Any],
    **updates: Any,
) -> dict[str, Any]:
    embedded = observation["observation_context"]
    _require(type(embedded) is dict, "observation context is not an exact mapping")
    payload = {key: copy.deepcopy(embedded[key]) for key in _CONTEXT_PAYLOAD_KEYS}
    payload.update(updates)
    return _standalone_record(
        canonical,
        domain="RiskYieldMMA2MTargetObservationContextV2V4_9F_RawV8",
        identity_field="observation_context_id",
        payload=payload,
    )


def _fully_recontextualized_observation(
    canonical: Any,
    observation: Mapping[str, Any],
    **updates: Any,
) -> dict[str, Any]:
    record = copy.deepcopy(observation)
    embedded = record["observation_context"]
    _require(type(embedded) is dict, "observation context is not an exact mapping")
    for key, value in updates.items():
        _require(key in _CONTEXT_PAYLOAD_KEYS, f"unknown context update: {key}")
        embedded[key] = value
    context_payload = {key: embedded[key] for key in _CONTEXT_PAYLOAD_KEYS}
    context_id = _semantic_id(
        canonical,
        domain="RiskYieldMMA2MTargetObservationContextV2V4_9F_RawV8",
        payload=context_payload,
    )
    embedded["observation_context_id"] = context_id
    record["observation_context_id"] = context_id
    for field in record["field_observations"]:
        field["observation_context_id"] = context_id
        _rehash(canonical, field)
    return _rehash(canonical, record)


def _expect_rejected(canonical: Any, action: Callable[[], Any], *, label: str) -> None:
    try:
        action()
    except canonical.CanonicalizationError:
        return
    except Exception as exc:
        raise HarnessFailure(
            f"{label} raised {type(exc).__name__}, not CanonicalizationError"
        ) from exc
    raise HarnessFailure(f"{label} was accepted")


def _expect_rejected_containing(
    canonical: Any,
    action: Callable[[], Any],
    *,
    label: str,
    expected_fragment: str,
) -> None:
    try:
        action()
    except canonical.CanonicalizationError as exc:
        _require(
            expected_fragment in str(exc),
            f"{label} omitted stable error {expected_fragment!r}: {exc}",
        )
        return
    except Exception as exc:
        raise HarnessFailure(
            f"{label} raised {type(exc).__name__}, not CanonicalizationError"
        ) from exc
    raise HarnessFailure(f"{label} was accepted")


def _round_trip_standalone(
    canonical: Any,
    record_type: type[Any],
    record: Mapping[str, Any],
    *,
    label: str,
    exercise_adversaries: bool = True,
) -> Any:
    _require(type(record) is dict, f"{label} fixture is not an exact mapping")
    item = record_type.from_mapping(record)
    _require(item.as_dict() == record, f"{label} mapping round trip differs")
    raw = _canonical_bytes(item)
    _require(
        raw == canonical.canonical_json_bytes(record),
        f"{label} canonical bytes differ",
    )
    decoded = record_type.from_json_bytes(raw)
    _require(decoded.as_dict() == record, f"{label} byte round trip differs")

    if not exercise_adversaries:
        return item

    domain = record["record_domain"]
    identity_field = _DOMAIN_TO_IDENTITY_FIELD[domain]
    payload_keys = [
        key
        for key in record
        if key
        not in {
            "canonicalization_version",
            "measurement_schema_version",
            "record_domain",
            identity_field,
        }
    ]
    _require(bool(payload_keys), f"{label} has no identity payload")

    unknown = copy.deepcopy(record)
    unknown["unexpected_raw_v8_member"] = 1
    _expect_rejected(
        canonical,
        lambda: record_type.from_mapping(unknown),
        label=f"{label} unknown member",
    )
    missing = copy.deepcopy(record)
    del missing[payload_keys[0]]
    _expect_rejected(
        canonical,
        lambda: record_type.from_mapping(missing),
        label=f"{label} missing member",
    )
    wrong_id = copy.deepcopy(record)
    wrong_id[identity_field] = "0" * 64
    if wrong_id[identity_field] == record[identity_field]:
        wrong_id[identity_field] = "f" * 64
    _expect_rejected(
        canonical,
        lambda: record_type.from_mapping(wrong_id),
        label=f"{label} wrong identity",
    )
    wrong_domain = copy.deepcopy(record)
    wrong_domain["record_domain"] = f"{domain}Unexpected"
    _expect_rejected(
        canonical,
        lambda: record_type.from_mapping(wrong_domain),
        label=f"{label} wrong domain",
    )
    wrong_schema = copy.deepcopy(record)
    wrong_schema["measurement_schema_version"] = f"{_SCHEMA_VERSION}_unexpected"
    _expect_rejected(
        canonical,
        lambda: record_type.from_mapping(wrong_schema),
        label=f"{label} wrong schema",
    )
    _expect_rejected(
        canonical,
        lambda: record_type.from_mapping(_MappingSubclass(copy.deepcopy(record))),
        label=f"{label} mapping subclass",
    )

    duplicate_json = (
        b'{"canonicalization_version":"'
        + canonical.CANONICALIZATION_VERSION.encode("ascii")
        + b'",'
        + raw[1:]
    )
    _expect_rejected(
        canonical,
        lambda: record_type.from_json_bytes(duplicate_json),
        label=f"{label} duplicate JSON member",
    )
    pretty = json.dumps(record, indent=2, ensure_ascii=False).encode("utf-8")
    _expect_rejected(
        canonical,
        lambda: record_type.from_json_bytes(pretty),
        label=f"{label} noncanonical JSON bytes",
    )
    _expect_rejected(
        canonical,
        lambda: record_type.from_json_bytes(raw + b"\n"),
        label=f"{label} trailing byte",
    )
    return item


def _test_module_constants(contracts: Any, golden: Mapping[str, Any]) -> None:
    _require(
        contracts.PHYSICAL_TRANSPORT_A2M_RAW_V49F_V8_SCHEMA_VERSION == _SCHEMA_VERSION,
        "production Raw V8 schema version differs",
    )
    _require(
        tuple(
            value.value
            for value in contracts.CapacityMeasurementOperationSpecTypeV49FV8
        )
        == (
            "ACK_DEADLINE_EXPIRY_SPEC_V1",
            "INGRESS_OPERATION_SPEC_V2",
            "LOCAL_SHUTDOWN_SPEC_V2",
            "SUBSCRIPTION_DISPATCH_SPEC_V2",
        ),
        "current operation-spec tag set differs",
    )
    _require(
        tuple(
            value.value
            for value in contracts.CapacityMeasurementOperationResultTypeV49FV8
        )
        == (
            "ACK_DEADLINE_EXPIRY_RESULT_EVIDENCE_V1",
            "INGRESS_RESULT_EVIDENCE_V2",
            "LOCAL_SHUTDOWN_RESULT_EVIDENCE_V2",
            "SUBSCRIPTION_DISPATCH_RESULT_EVIDENCE_V2",
        ),
        "current operation-result tag set differs",
    )
    module_text = Path(contracts.__file__).read_text(encoding="utf-8")
    for removed_tag in golden["invariants"]["v1_removal_assertions"]["removed_tags"]:
        _require(
            f'= "{removed_tag}"' not in module_text,
            f"removed V1 tag remains an enum value: {removed_tag}",
        )
    _require(
        len(contracts.RAW_V8_TARGET_FIELD_DESCRIPTORS_V49F) == 185,
        "production target descriptor count differs",
    )
    field_ids = tuple(
        descriptor.field_id
        for descriptor in contracts.RAW_V8_TARGET_FIELD_DESCRIPTORS_V49F
    )
    _require(field_ids == tuple(sorted(field_ids)), "target field IDs are not sorted")
    _require(len(set(field_ids)) == 185, "target field IDs are not unique")
    _require(
        len(contracts.RAW_V8_OPERATION_COUNTER_FIELD_IDS_V49F) == 66,
        "counter coordinate count differs",
    )
    _require(
        len(contracts.RAW_V8_MONOTONE_COUNTER_FIELD_IDS_V49F) == 57,
        "monotone counter coordinate count differs",
    )
    _require(
        contracts.RAW_V8_OPERATION_COUNTER_SCHEMA_ID_V49F
        == "5181eb89788d511ffeb2ccc65264b81e9e0d3ae977043820524f8b08dfa58fc3",
        "counter schema frozen ID differs",
    )
    exact_structural_limits = {
        "RAW_V8_MAXIMUM_JSON_NESTING_DEPTH_V49F": 64,
        "RAW_V8_MAXIMUM_JSON_OBJECT_MEMBERS_V49F": 512,
        "RAW_V8_MAXIMUM_JSON_ARRAY_ELEMENTS_V49F": 524_288,
        "RAW_V8_MAXIMUM_TYPED_NESTING_DEPTH_V49F": 16,
        "RAW_V8_MAXIMUM_TYPED_OBJECT_MEMBERS_V49F": 32,
        "RAW_V8_MAXIMUM_TARGET_OBSERVATION_BYTES_V49F": 262_144,
        "RAW_V8_MAXIMUM_INPUT_CHUNKS_V49F": 128,
        "RAW_V8_MAXIMUM_INPUT_OCTETS_V49F": 65_536,
        "RAW_V8_MAXIMUM_EXPECTED_PARSER_UNITS_V49F": 32_768,
        "RAW_V8_MAXIMUM_EXPECTED_COMPLETED_APPLICATION_MESSAGES_V49F": 32_768,
        "RAW_V8_MAXIMUM_EXPECTED_OUTPUT_FRAMES_V49F": 32_768,
        "RAW_V8_MAXIMUM_EXPECTED_OUTPUT_PAYLOAD_OCTETS_V49F": 65_536,
        "RAW_V8_MAXIMUM_CHECKPOINT_SELECTOR_LENGTH_V49F": 64,
        "RAW_V8_MAXIMUM_TARGET_OBSERVATIONS_V49F": 67,
        "RAW_V8_MAXIMUM_KERNEL_RESULT_IDS_V49F": 256,
        "RAW_V8_MAXIMUM_OPERATION_RESULT_BYTES_V49F": 524_288,
    }
    for name, expected in exact_structural_limits.items():
        _require(getattr(contracts, name) == expected, f"{name} differs")
    undefined_node_caps = {
        name
        for name in vars(contracts)
        if "NODE" in name.upper()
        and any(token in name.upper() for token in ("COUNT", "LIMIT", "MAXIMUM"))
    }
    _require(
        not undefined_node_caps,
        f"Raw V8 added undefined node-count caps: {sorted(undefined_node_caps)}",
    )
    _require(
        golden["invariants"]["semantic_preimage_node_count_limit"] is None,
        "golden introduced an undefined semantic-preimage node-count cap",
    )
    _require(
        contracts.RAW_V8_TARGET_FIELD_REGISTRY_V49F.target_field_registry_id
        == contracts.RAW_V8_TARGET_FIELD_REGISTRY_ID_V49F,
        "registry constant and literal ID differ",
    )
    registry_golden = _find_domain(
        golden["target_field_registry"],
        "RiskYieldMMA2MTargetFieldRegistryV4_9F_RawV8",
    )
    counter_golden = _find_domain(
        golden["operation_counter_schema"],
        "RiskYieldMMA2MOperationCounterSnapshotSchemaV4_9F_RawV8",
    )
    _require(
        contracts.RAW_V8_TARGET_FIELD_REGISTRY_V49F.as_dict() == registry_golden,
        "production registry differs from independent golden",
    )
    _require(
        contracts.RAW_V8_OPERATION_COUNTER_SCHEMA_V49F.as_dict() == counter_golden,
        "production counter schema differs from independent golden",
    )
    _require(
        contracts.RAW_V8_INGRESS_LOGICAL_ORACLE_PROFILE_V49F.as_dict()
        == golden["ingress_logical_oracle_profile_catalog"][0]
        and contracts.RAW_V8_INGRESS_LOGICAL_ORACLE_PROFILE_ID_V49F
        == golden["ingress_logical_oracle_profile_catalog"][0][
            "logical_oracle_profile_id"
        ],
        "production ingress logical-oracle profile differs from independent golden",
    )
    _require(
        contracts.RAW_V8_MARKER_CONTRACT_V49F.as_dict() == golden["marker_contract"]
        and contracts.RAW_V8_MARKER_CONTRACT_ID_V49F
        == golden["marker_contract"]["marker_contract_id"],
        "production marker contract differs from independent golden",
    )
    selector_type = contracts.CapacityMeasurementCheckpointSelectorV49FV8
    selector_catalog = golden["checkpoint_selector_catalog"]
    _require(
        type(selector_catalog) is list
        and len(selector_catalog) == 9
        and len(
            {item["selector"]["checkpoint_selector_id"] for item in selector_catalog}
        )
        == 9,
        "checkpoint selector catalog is not the exact nine-selector set",
    )
    for catalog_entry in selector_catalog:
        selector = selector_type.from_mapping(catalog_entry["selector"])
        _require(
            selector.as_dict() == catalog_entry["selector"],
            f"{catalog_entry['catalog_name']} selector differs from production codec",
        )
    policy = registry_golden["status_reason_policy_definition"]
    reason_rules_by_reason = {item["reason"]: item for item in policy["reason_rules"]}
    dedicated_reasons = frozenset(_PLACEHOLDER_PREDICATE_BY_FIELD_REASON)
    _require(
        len(policy["reason_rules"]) == 26
        and len(
            {
                item["context_predicate"]
                for item in policy["reason_rules"]
                if item["context_predicate"] is not None
            }
        )
        == 6,
        "closure-facing 26-reason/6-predicate policy differs",
    )
    _require(
        dedicated_reasons <= set(reason_rules_by_reason)
        and {
            reason: reason_rules_by_reason[reason]["context_predicate"]
            for reason in dedicated_reasons
        }
        == _PLACEHOLDER_PREDICATE_BY_FIELD_REASON,
        "dedicated checkpoint-placeholder reason/predicate mapping differs",
    )
    for descriptor in registry_golden["descriptors"]:
        _require(
            dedicated_reasons <= set(descriptor["allowed_status_reasons"]),
            f"{descriptor['field_id']} omits a dedicated checkpoint-placeholder reason",
        )
    historical_source_clock = reason_rules_by_reason["SOURCE_CLOCK_UNAVAILABLE"]
    historical_target_boundary = reason_rules_by_reason["TARGET_BOUNDARY_NOT_REACHED"]
    _require(
        historical_source_clock["context_predicate"] is None
        and any(
            item["attempt_state"] == "NOT_ATTEMPTED"
            and item["permitted_failure_phases"] == ["FIRST_CLOCK_READ"]
            for item in historical_source_clock["attempt_state_error_forms"]
        ),
        "historical SOURCE_CLOCK_UNAVAILABLE rule was overwritten",
    )
    _require(
        historical_target_boundary["context_predicate"] is None
        and historical_target_boundary["reason"] == "TARGET_BOUNDARY_NOT_REACHED",
        "historical TARGET_BOUNDARY_NOT_REACHED rule was overwritten",
    )
    context_semantics = golden["invariants"]["context_semantics"]
    null_attempt = context_semantics["null_attempt"]
    compact_partition = context_semantics["compact_coordinate_partition"]
    expected_attempt_required = tuple(null_attempt["ordered_field_ids"])
    expected_operation_local = tuple(
        compact_partition["operation_local"]["ordered_field_ids"]
    )
    expected_point_or_current = tuple(
        compact_partition["point_or_current"]["ordered_field_ids"]
    )
    _require(
        contracts.RAW_V8_ATTEMPT_REQUIRED_FIELD_IDS_V49F == expected_attempt_required
        and contracts.RAW_V8_ATTEMPT_REQUIRED_FIELD_COUNT_V49F == 85,
        "production null-attempt field authority differs from independent golden",
    )
    _require(
        contracts.RAW_V8_COMPACT_OPERATION_LOCAL_FIELD_IDS_V49F
        == expected_operation_local
        and contracts.RAW_V8_COMPACT_OPERATION_LOCAL_FIELD_COUNT_V49F == 58,
        "production compact operation-local partition differs",
    )
    _require(
        contracts.RAW_V8_COMPACT_POINT_OR_CURRENT_FIELD_IDS_V49F
        == expected_point_or_current
        and contracts.RAW_V8_COMPACT_POINT_OR_CURRENT_FIELD_COUNT_V49F == 8,
        "production compact point/current partition differs",
    )


def _test_embedded_external_schema_registry_v2_smoke(
    canonical: Any, golden: Mapping[str, Any]
) -> None:
    """Check the complete V3 structural authority without claiming a full adapter diff."""

    registry_keys = {
        "ascii_dfa_catalog",
        "canonicalization_version",
        "cross_field_rule_descriptor_count",
        "external_schema_profile",
        "external_schema_registry_id",
        "external_type_descriptor_count",
        "fixed_position_resolver_profile_catalog",
        "identifier_profile_catalog",
        "measurement_schema_version",
        "ordered_cross_field_rule_descriptors",
        "ordered_external_type_descriptors",
        "ordered_rule_application_descriptors",
        "ordered_schema_graph_node_names",
        "record_domain",
        "rule_application_descriptor_count",
        "schema_graph_node_count",
        "text_language_catalog",
        "unicode_source_catalog",
        "value_schema_catalog",
    }
    registry = golden["external_schema_registry_v2"]
    _require(
        type(registry) is dict and set(registry) == registry_keys,
        "embedded External Schema V2 registry root differs",
    )
    _require(
        registry["canonicalization_version"] == canonical.CANONICALIZATION_VERSION
        and registry["measurement_schema_version"] == _SCHEMA_VERSION
        and registry["record_domain"] == _EXTERNAL_SCHEMA_REGISTRY_DOMAIN
        and registry["external_schema_profile"]
        == "riskyieldmm_raw_v8_step2_external_schema_v2",
        "embedded External Schema V2 registry envelope differs",
    )
    registry_payload = {
        key: registry[key] for key in _EXTERNAL_SCHEMA_REGISTRY_IDENTITY_PAYLOAD_MEMBERS
    }
    _require(
        registry["external_schema_registry_id"]
        == golden["invariants"]["exact_semantic_ids"]["external_schema_registry_id"]
        == _EXTERNAL_SCHEMA_REGISTRY_ID
        == _semantic_id(
            canonical,
            domain=_EXTERNAL_SCHEMA_REGISTRY_DOMAIN,
            payload=registry_payload,
        ),
        "embedded External Schema V2 registry semantic identity differs",
    )

    exact_catalog_counts = {
        "unicode_source_catalog": 6,
        "identifier_profile_catalog": 3,
        "ascii_dfa_catalog": 9,
        "text_language_catalog": 103,
        "value_schema_catalog": 236,
        "ordered_external_type_descriptors": 52,
        "ordered_cross_field_rule_descriptors": 42,
        "fixed_position_resolver_profile_catalog": 2,
        "ordered_rule_application_descriptors": 8,
        "ordered_schema_graph_node_names": 52,
    }
    for member, expected_count in exact_catalog_counts.items():
        value = registry[member]
        _require(
            type(value) is list and len(value) == expected_count,
            f"embedded External Schema V2 {member} count differs",
        )
    _require(
        registry["external_type_descriptor_count"] == 52
        and registry["cross_field_rule_descriptor_count"] == 42
        and registry["rule_application_descriptor_count"] == 8
        and registry["schema_graph_node_count"] == 52,
        "embedded External Schema V2 declared counts differ",
    )

    descriptor_keys = {
        "codec_byte_bound_relation",
        "codec_octet_limit",
        "described_record_domain",
        "external_type_descriptor_id",
        "identity_field",
        "identity_payload_member_order",
        "ordered_intrinsic_rule_ids",
        "record_member_descriptors",
        "tagged_union_descriptor",
        "type_form",
        "type_name",
        "type_role",
        "type_version_tag",
    }
    descriptors = registry["ordered_external_type_descriptors"]
    descriptor_names: list[str] = []
    descriptor_ids: list[str] = []
    standalone_count = 0
    nested_count = 0
    record_count = 0
    union_count = 0
    for descriptor in descriptors:
        _require(
            type(descriptor) is dict and set(descriptor) == descriptor_keys,
            "embedded external type descriptor shape differs",
        )
        payload = {
            key: value
            for key, value in descriptor.items()
            if key != "external_type_descriptor_id"
        }
        _require(
            descriptor["external_type_descriptor_id"]
            == _semantic_id(
                canonical,
                domain=_EXTERNAL_TYPE_DESCRIPTOR_DOMAIN,
                payload=payload,
            ),
            f"{descriptor['type_name']} external descriptor identity differs",
        )
        descriptor_names.append(descriptor["type_name"])
        descriptor_ids.append(descriptor["external_type_descriptor_id"])
        standalone_count += descriptor["type_role"] == "STANDALONE"
        nested_count += descriptor["type_role"] == "NESTED"
        record_count += descriptor["type_form"] == "RECORD"
        union_count += descriptor["type_form"] == "TAGGED_UNION"
    _require(
        descriptor_names == sorted(descriptor_names)
        and len(set(descriptor_names)) == 52
        and len(set(descriptor_ids)) == 52
        and registry["ordered_schema_graph_node_names"] == descriptor_names,
        "embedded external type descriptor order or uniqueness differs",
    )
    _require(
        (standalone_count, nested_count) == (16, 36)
        and (record_count, union_count) == (49, 3),
        "embedded external type descriptor role/form partition differs",
    )


def _test_structural_scanner_and_exact_scalar_types(
    canonical: Any, contracts: Any, golden: Mapping[str, Any]
) -> None:
    scan = contracts.validate_capacity_measurement_json_structure_before_parse_v49f_v8

    too_deep = b"[" * 65 + b"0" + b"]" * 65
    _expect_rejected_containing(
        canonical,
        lambda: scan(too_deep),
        label="Raw V8 broad nesting-depth limit",
        expected_fragment="V8_JSON_DEPTH_LIMIT_EXCEEDED",
    )
    too_many_members = json.dumps(
        {f"k{index:03d}": 0 for index in range(513)},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    _expect_rejected_containing(
        canonical,
        lambda: scan(too_many_members),
        label="Raw V8 broad object-member limit",
        expected_fragment="V8_JSON_OBJECT_MEMBER_LIMIT_EXCEEDED",
    )
    too_many_array_elements = b"[" + (b"0," * 524_288) + b"0]"
    _expect_rejected_containing(
        canonical,
        lambda: scan(too_many_array_elements),
        label="Raw V8 broad array-element limit",
        expected_fragment="V8_JSON_ARRAY_ELEMENT_LIMIT_EXCEEDED",
    )
    _expect_rejected_containing(
        canonical,
        lambda: scan(b'{"broken":[0,}'),
        label="Raw V8 malformed structural input",
        expected_fragment="V8_JSON_MALFORMED_STRUCTURE",
    )

    registry_type = contracts.CapacityMeasurementTargetFieldRegistryV49FV8
    typed_too_deep: Any = 0
    for _ in range(17):
        typed_too_deep = [typed_too_deep]
    _expect_rejected(
        canonical,
        lambda: registry_type.from_json_bytes(
            canonical.canonical_json_bytes(typed_too_deep)
        ),
        label="Raw V8 typed nesting-depth limit",
    )
    typed_too_wide = {f"k{index:02d}": 0 for index in range(33)}
    _expect_rejected(
        canonical,
        lambda: registry_type.from_json_bytes(
            canonical.canonical_json_bytes(typed_too_wide)
        ),
        label="Raw V8 typed object-member limit",
    )

    declaration_type = contracts.CapacityMeasurementOperationDeclarationV49FV8
    declaration = copy.deepcopy(golden["fixture_records"]["operation_declaration"])
    declaration["sample_sequence"] = 1.0
    _expect_rejected(
        canonical,
        lambda: declaration_type.from_mapping(declaration),
        label="operation declaration floating-point sequence",
    )
    declaration["sample_sequence"] = _IntSubclass(1)
    _expect_rejected(
        canonical,
        lambda: declaration_type.from_mapping(declaration),
        label="operation declaration int-subclass sequence",
    )
    declaration_fixture = golden["fixture_records"]["operation_declaration"]
    for field, maximum in (("stage", 128), ("workload_id", 256)):
        exact_maximum = copy.deepcopy(declaration_fixture)
        exact_maximum[field] = "x" * maximum
        _rehash(canonical, exact_maximum)
        _require(
            declaration_type.from_mapping(exact_maximum).as_dict() == exact_maximum,
            f"operation declaration {field} exact maximum did not round-trip",
        )
        plus_one = copy.deepcopy(declaration_fixture)
        plus_one[field] = "x" * (maximum + 1)
        _rehash(canonical, plus_one)
        _expect_rejected(
            canonical,
            lambda value=plus_one: declaration_type.from_mapping(value),
            label=f"operation declaration {field} exact plus one",
        )
        multibyte_over_octets = copy.deepcopy(declaration_fixture)
        multibyte_over_octets[field] = "\U0010ffff" * maximum
        _rehash(canonical, multibyte_over_octets)
        _expect_rejected(
            canonical,
            lambda value=multibyte_over_octets: declaration_type.from_mapping(value),
            label=f"operation declaration {field} UTF-8 octet bound",
        )

    text_kind = contracts.CapacityMeasurementTargetValueKindV49FV8.TEXT
    optional_text_kind = (
        contracts.CapacityMeasurementTargetValueKindV49FV8.OPTIONAL_TEXT
    )
    text_list_kind = contracts.CapacityMeasurementTargetValueKindV49FV8.TEXT_LIST
    _require(
        contracts._TargetValueV49FV8._MAXIMUM_BYTES
        == contracts.RAW_V8_MAXIMUM_VALUE_UNION_BYTES_V49F
        == 3_072
        and all(
            value_type._MAXIMUM_BYTES == 3_072
            for value_type in contracts._RAW_V8_VALUE_CLASS_BY_KIND_V49F.values()
        ),
        "target-value variants do not inherit the frozen 3-KiB ceiling",
    )
    _require(
        contracts.CapacityMeasurementTextValueV49FV8(
            kind=text_kind,
            value="x" * 256,
        ).as_dict()
        == {"kind": "TEXT", "value": "x" * 256},
        "target TEXT exact maximum did not round-trip",
    )
    _require(
        contracts.CapacityMeasurementOptionalTextValueV49FV8(
            kind=optional_text_kind,
            present=True,
            value="x" * 256,
        ).as_dict()
        == {"kind": "OPTIONAL_TEXT", "present": True, "value": "x" * 256},
        "target OPTIONAL_TEXT exact maximum did not round-trip",
    )
    _require(
        contracts.CapacityMeasurementTextListValueV49FV8(
            kind=text_list_kind,
            values=("x" * 256,),
        ).as_dict()
        == {"kind": "TEXT_LIST", "values": ["x" * 256]},
        "target TEXT_LIST item exact maximum did not round-trip",
    )
    for label, action in (
        (
            "target TEXT 256 plus one",
            lambda: contracts.CapacityMeasurementTextValueV49FV8(
                kind=text_kind,
                value="x" * 257,
            ),
        ),
        (
            "target OPTIONAL_TEXT UTF-8 octet bound",
            lambda: contracts.CapacityMeasurementOptionalTextValueV49FV8(
                kind=optional_text_kind,
                present=True,
                value="\U0010ffff" * 256,
            ),
        ),
        (
            "target TEXT_LIST item surrogate",
            lambda: contracts.CapacityMeasurementTextListValueV49FV8(
                kind=text_list_kind,
                values=("x\ud800",),
            ),
        ),
    ):
        _expect_rejected(canonical, action, label=label)


def _test_all_standalone_codecs(
    canonical: Any, contracts: Any, golden: Mapping[str, Any]
) -> None:
    records = [
        item
        for item in _walk_mappings(golden)
        if item.get("canonicalization_version") == canonical.CANONICALIZATION_VERSION
        and item.get("measurement_schema_version") == _SCHEMA_VERSION
        and item.get("record_domain") in _DOMAIN_TO_CLASS_NAME
        and "external_type_descriptor_id" not in item
    ]
    _require(records, "golden contains no complete standalone Raw V8 envelopes")
    unique_records: list[dict[str, Any]] = []
    seen_canonical_records: set[bytes] = set()
    for record in records:
        raw = canonical.canonical_json_bytes(record)
        if raw not in seen_canonical_records:
            seen_canonical_records.add(raw)
            unique_records.append(record)
    records = unique_records
    first_observation = _off_observations(golden)[0]

    context_payload = {
        key: copy.deepcopy(first_observation["observation_context"][key])
        for key in _CONTEXT_PAYLOAD_KEYS
    }
    context = _standalone_record(
        canonical,
        domain="RiskYieldMMA2MTargetObservationContextV2V4_9F_RawV8",
        identity_field="observation_context_id",
        payload=context_payload,
    )
    _require(
        context["observation_context_id"]
        == first_observation["observation_context_id"],
        "derived context differs from observation context ID",
    )
    records.append(context)

    source_error_detail = _standalone_record(
        canonical,
        domain="RiskYieldMMA2MSourceErrorDetailV4_9F_RawV8",
        identity_field="source_error_detail_sha256",
        payload={
            "field_id": "kernel.siocinq_unread_octets",
            "observation_method": "LINUX_IOCTL",
            "source_failure_phase": "SOURCE_ADAPTER",
            "source_errno_number": 5,
            "source_errno_name": "EIO",
            "source_error_class": "builtins.OSError",
        },
    )
    records.append(source_error_detail)

    seen_domains: dict[str, int] = {}
    for index, record in enumerate(records):
        domain = record.get("record_domain")
        _require(
            domain in _DOMAIN_TO_CLASS_NAME,
            f"fixture {index} has unknown domain {domain!r}",
        )
        first_for_domain = domain not in seen_domains
        record_type = getattr(contracts, _DOMAIN_TO_CLASS_NAME[domain])
        _round_trip_standalone(
            canonical,
            record_type,
            record,
            label=f"{domain} fixture {index}",
            exercise_adversaries=first_for_domain,
        )
        seen_domains[domain] = seen_domains.get(domain, 0) + 1
    _require(
        set(seen_domains) == set(_DOMAIN_TO_CLASS_NAME),
        "standalone codec coverage omitted a frozen Step-2 domain",
    )


def _rehash_spec(canonical: Any, record: dict[str, Any]) -> dict[str, Any]:
    return _rehash(canonical, record)


def _test_operation_spec_adversaries(
    canonical: Any, contracts: Any, golden: Mapping[str, Any]
) -> None:
    spec_type = contracts.CapacityMeasurementOperationSpecV49FV8
    specs = golden["fixture_records"]["operation_specs"]
    for operation in _OPERATIONS:
        record = specs[operation]
        _require(record["operation_kind"] == operation, f"{operation} spec tag differs")
        wrong_tag = copy.deepcopy(record)
        wrong_tag["operation_kind"] = next(
            item for item in _OPERATIONS if item != operation
        )
        _rehash_spec(canonical, wrong_tag)
        _expect_rejected(
            canonical,
            lambda value=wrong_tag: spec_type.from_mapping(value),
            label=f"{operation} spec wrong tag/type pair",
        )
        wrong_type = copy.deepcopy(record)
        wrong_type["spec_type"] = "UNRECOGNIZED_SPEC_V2"
        _rehash_spec(canonical, wrong_type)
        _expect_rejected(
            canonical,
            lambda value=wrong_type: spec_type.from_mapping(value),
            label=f"{operation} unknown spec type",
        )
        extra_body = copy.deepcopy(record)
        extra_body["spec"]["unexpected"] = 1
        _rehash_spec(canonical, extra_body)
        _expect_rejected(
            canonical,
            lambda value=extra_body: spec_type.from_mapping(value),
            label=f"{operation} extra spec body member",
        )

    ingress = copy.deepcopy(specs["INGRESS"])
    ingress["spec"]["ordered_input_chunks_base64"][0] = "AA"
    _rehash_spec(canonical, ingress)
    _expect_rejected(
        canonical,
        lambda: spec_type.from_mapping(ingress),
        label="ingress noncanonical base64",
    )

    for field, rejected_value in (
        ("expected_parser_unit_count", 32_769),
        ("expected_completed_application_message_count", 32_769),
        ("expected_logical_output_frame_count", 32_769),
        ("expected_logical_output_payload_octets", 65_537),
    ):
        over_bound = copy.deepcopy(specs["INGRESS"])
        over_bound["spec"][field] = rejected_value
        _rehash_spec(canonical, over_bound)
        _expect_rejected(
            canonical,
            lambda value=over_bound: spec_type.from_mapping(value),
            label=f"ingress {field} exact plus-one",
        )

    foreign_profile = copy.deepcopy(specs["INGRESS"])
    foreign_profile["spec"]["logical_oracle_profile_id"] = "f" * 64
    if (
        foreign_profile["spec"]["logical_oracle_profile_id"]
        == specs["INGRESS"]["spec"]["logical_oracle_profile_id"]
    ):
        foreign_profile["spec"]["logical_oracle_profile_id"] = "0" * 64
    _rehash_spec(canonical, foreign_profile)
    _expect_rejected(
        canonical,
        lambda: spec_type.from_mapping(foreign_profile),
        label="ingress foreign logical-oracle profile",
    )

    subscription = copy.deepcopy(specs["SUBSCRIPTION_DISPATCH"])
    subscription["spec"]["expected_dispatch_disposition"] = "SENT"
    _rehash_spec(canonical, subscription)
    _expect_rejected(
        canonical,
        lambda: spec_type.from_mapping(subscription),
        label="subscription control-path SENT alias",
    )
    for label, topic in (
        ("leading whitespace", " fixture/topic/1"),
        ("non-NFC", "e\u0301"),
        ("control", "fixture\u0001topic"),
        ("257 code points", "x" * 257),
        ("over 1024 UTF-8 octets", "\U00010000" * 256 + "x"),
    ):
        invalid_topic = copy.deepcopy(specs["SUBSCRIPTION_DISPATCH"])
        invalid_topic["spec"]["expected_topic"] = topic
        _rehash_spec(canonical, invalid_topic)
        _expect_rejected(
            canonical,
            lambda value=invalid_topic: spec_type.from_mapping(value),
            label=f"subscription topic {label}",
        )

    edge_trim_code_points = contracts.RAW_V8_EDGE_TRIM_CODE_POINTS_V49F
    _require(
        type(edge_trim_code_points) is frozenset
        and len(edge_trim_code_points) == 29
        and edge_trim_code_points
        == frozenset(
            {
                *range(0x0009, 0x000E),
                *range(0x001C, 0x0020),
                0x0020,
                0x0085,
                0x00A0,
                0x1680,
                *range(0x2000, 0x200B),
                0x2028,
                0x2029,
                0x202F,
                0x205F,
                0x3000,
            }
        ),
        "Raw V8 frozen edge-trim profile differs",
    )
    for code_point in sorted(edge_trim_code_points):
        for position, topic in (
            ("leading", f"{chr(code_point)}fixture/topic/1"),
            ("trailing", f"fixture/topic/1{chr(code_point)}"),
        ):
            edge_whitespace = copy.deepcopy(specs["SUBSCRIPTION_DISPATCH"])
            edge_whitespace["spec"]["expected_topic"] = topic
            _rehash_spec(canonical, edge_whitespace)
            _expect_rejected(
                canonical,
                lambda value=edge_whitespace: spec_type.from_mapping(value),
                label=(
                    f"subscription topic frozen edge trim U+{code_point:04X} {position}"
                ),
            )

    for code_point in (*range(0x20), 0x7F):
        control_topic = copy.deepcopy(specs["SUBSCRIPTION_DISPATCH"])
        control_topic["spec"]["expected_topic"] = f"fixture{chr(code_point)}topic"
        _rehash_spec(canonical, control_topic)
        _expect_rejected(
            canonical,
            lambda value=control_topic: spec_type.from_mapping(value),
            label=f"subscription topic C0/DEL U+{code_point:04X}",
        )

    for label, topic in (
        ("internal non-ASCII whitespace", "fixture\u00a0topic"),
        ("leading near-miss zero-width space", "\u200bfixture"),
        ("trailing near-miss zero-width space", "fixture\u200b"),
        ("UCD-15 normalization witness", "\U000105d2\u0307"),
        ("exact 256-code-point/1024-octet maximum", "\U0010ffff" * 256),
    ):
        valid_topic = copy.deepcopy(specs["SUBSCRIPTION_DISPATCH"])
        valid_topic["spec"]["expected_topic"] = topic
        _rehash_spec(canonical, valid_topic)
        parsed = spec_type.from_mapping(valid_topic)
        _require(
            parsed.as_dict() == valid_topic,
            f"subscription topic {label} did not round-trip",
        )

    class _TextSubclass(str):
        pass

    subclass_topic = copy.deepcopy(specs["SUBSCRIPTION_DISPATCH"])
    subclass_topic["spec"]["expected_topic"] = _TextSubclass("fixture/topic/1")
    _rehash_spec(canonical, subclass_topic)
    _expect_rejected(
        canonical,
        lambda: spec_type.from_mapping(subclass_topic),
        label="subscription topic string subclass",
    )

    _expect_rejected(
        canonical,
        lambda: contracts._utf8_identifier(
            "fixture\ud800topic",
            field="expected_topic",
            maximum=256,
            maximum_utf8_octets=1_024,
        ),
        label="subscription topic surrogate",
    )

    observed_ucd_version = contracts.unicodedata.unidata_version
    contracts.unicodedata.unidata_version = "16.0.0"
    try:
        _require(
            contracts._ascii_text(
                "ASCII_1",
                field="ascii_capability_probe",
                minimum=1,
                maximum=16,
            )
            == "ASCII_1",
            "ASCII-only validation incorrectly depends on Unicode authority",
        )
        _expect_rejected(
            canonical,
            lambda: spec_type.from_mapping(specs["SUBSCRIPTION_DISPATCH"]),
            label="subscription topic ambient Unicode authority drift",
        )
    finally:
        contracts.unicodedata.unidata_version = observed_ucd_version

    for operation in _OPERATIONS:
        exact_maximum = copy.deepcopy(specs[operation])
        exact_maximum["spec"]["workload_family"] = "w" * 128
        _rehash_spec(canonical, exact_maximum)
        _require(
            spec_type.from_mapping(exact_maximum).as_dict() == exact_maximum,
            f"{operation} workload-family exact maximum did not round-trip",
        )
        plus_one = copy.deepcopy(specs[operation])
        plus_one["spec"]["workload_family"] = "w" * 129
        _rehash_spec(canonical, plus_one)
        _expect_rejected(
            canonical,
            lambda value=plus_one: spec_type.from_mapping(value),
            label=f"{operation} workload-family 128 plus one",
        )
        multibyte_over_octets = copy.deepcopy(specs[operation])
        multibyte_over_octets["spec"]["workload_family"] = "\U0010ffff" * 128
        _rehash_spec(canonical, multibyte_over_octets)
        _expect_rejected(
            canonical,
            lambda value=multibyte_over_octets: spec_type.from_mapping(value),
            label=f"{operation} workload-family UTF-8 octet bound",
        )

    ack = copy.deepcopy(specs["ACK_DEADLINE_EXPIRY"])
    if ack["spec"]["due_scenario"] == "DUE":
        ack["spec"]["expected_terminal_cause_code"] = None
    else:
        ack["spec"]["expected_terminal_cause_code"] = "ACK_DEADLINE_EXPIRED"
    _rehash_spec(canonical, ack)
    _expect_rejected(
        canonical,
        lambda: spec_type.from_mapping(ack),
        label="ACK scenario/cause mismatch",
    )

    shutdown = copy.deepcopy(specs["LOCAL_SHUTDOWN"])
    shutdown["spec"]["expected_local_close_code"] = 1001
    _rehash_spec(canonical, shutdown)
    _expect_rejected(
        canonical,
        lambda: spec_type.from_mapping(shutdown),
        label="shutdown non-frozen Close code",
    )
    shutdown_relation_mutations = (
        ("maximum_terminal_ingress_plaintext_octets", 16_385),
        ("maximum_terminal_ingress_parser_units", 4_097),
        ("maximum_terminal_tls_records", 2),
        ("maximum_terminal_ingress_automatic_outputs", 2),
        ("maximum_websocket_send_attempts", 513),
        ("maximum_tls_control_send_attempts", 257),
        ("maximum_peer_shutdown_polls", 1),
    )
    for field, rejected_value in shutdown_relation_mutations:
        invalid_shutdown = copy.deepcopy(specs["LOCAL_SHUTDOWN"])
        invalid_shutdown["spec"][field] = rejected_value
        _rehash_spec(canonical, invalid_shutdown)
        _expect_rejected(
            canonical,
            lambda value=invalid_shutdown: spec_type.from_mapping(value),
            label=f"shutdown relation violation: {field}",
        )

    removed_v1_tags = golden["invariants"]["v1_removal_assertions"]["removed_tags"]
    for operation in ("INGRESS", "LOCAL_SHUTDOWN", "SUBSCRIPTION_DISPATCH"):
        old_tag = next(
            tag
            for tag in removed_v1_tags
            if "RESULT" not in tag
            and (
                operation.split("_")[0] in tag
                or operation == "SUBSCRIPTION_DISPATCH"
                and tag.startswith("SUBSCRIPTION_")
            )
        )
        relabelled = copy.deepcopy(specs[operation])
        relabelled["spec_type"] = old_tag
        _rehash_spec(canonical, relabelled)
        _expect_rejected(
            canonical,
            lambda value=relabelled: spec_type.from_mapping(value),
            label=f"{operation} removed V1 spec tag",
        )

    forged_identity = spec_type.from_mapping(specs["INGRESS"])
    object.__setattr__(forged_identity, "operation_spec_id", "0" * 64)
    _expect_rejected(
        canonical,
        forged_identity.as_dict,
        label="forged frozen operation-spec identity",
    )
    forged_nested = spec_type.from_mapping(specs["INGRESS"])
    object.__setattr__(forged_nested.spec, "workload_family", "forged")
    _expect_rejected(
        canonical,
        forged_nested.as_dict,
        label="forged nested operation-spec dataclass",
    )


def _test_result_adversaries(
    canonical: Any, contracts: Any, golden: Mapping[str, Any]
) -> None:
    result_type = contracts.CapacityMeasurementOperationResultEvidenceV49FV8
    results = golden["fixture_records"]["operation_results"]
    for operation in _OPERATIONS:
        record = results[operation]
        _require(
            record["operation_kind"] == operation,
            f"{operation} result tag differs",
        )
        wrong_type = copy.deepcopy(record)
        wrong_type["result_type"] = "UNRECOGNIZED_RESULT_V2"
        _rehash(canonical, wrong_type)
        _expect_rejected(
            canonical,
            lambda value=wrong_type: result_type.from_mapping(value),
            label=f"{operation} unknown result type",
        )
        wrong_tag = copy.deepcopy(record)
        wrong_tag["operation_kind"] = next(
            item for item in _OPERATIONS if item != operation
        )
        _rehash(canonical, wrong_tag)
        _expect_rejected(
            canonical,
            lambda value=wrong_tag: result_type.from_mapping(value),
            label=f"{operation} result wrong tag/type pair",
        )
        extra_body = copy.deepcopy(record)
        extra_body["result"]["unexpected"] = 1
        _rehash(canonical, extra_body)
        _expect_rejected(
            canonical,
            lambda value=extra_body: result_type.from_mapping(value),
            label=f"{operation} extra result body member",
        )

    subscription = copy.deepcopy(results["SUBSCRIPTION_DISPATCH"])
    subscription["result"]["local_dispatch_disposition"] = "UNKNOWN_DELIVERY"
    _rehash(canonical, subscription)
    _expect_rejected(
        canonical,
        lambda: result_type.from_mapping(subscription),
        label="returned subscription UNKNOWN_DELIVERY",
    )

    ack = copy.deepcopy(results["ACK_DEADLINE_EXPIRY"])
    ack["result"]["expired"] = not ack["result"]["expired"]
    _rehash(canonical, ack)
    _expect_rejected(
        canonical,
        lambda: result_type.from_mapping(ack),
        label="ACK result truth-table mismatch",
    )

    subscription_pair = copy.deepcopy(results["SUBSCRIPTION_DISPATCH"])
    subscription_pair["result"]["ordered_kernel_result_event_ids"] = []
    _rehash(canonical, subscription_pair)
    _expect_rejected(
        canonical,
        lambda: result_type.from_mapping(subscription_pair),
        label="subscription kernel attempt/result cardinality mismatch",
    )
    ingress = copy.deepcopy(results["INGRESS"])
    ingress["result"]["observed_parser_unit_count"] = 32_769
    _rehash(canonical, ingress)
    _expect_rejected(
        canonical,
        lambda: result_type.from_mapping(ingress),
        label="ingress observed parser units exact plus-one",
    )
    shutdown = copy.deepcopy(results["LOCAL_SHUTDOWN"])
    shutdown["result"]["ordered_terminal_ingress_read_result_event_ids"] = []
    _rehash(canonical, shutdown)
    _expect_rejected(
        canonical,
        lambda: result_type.from_mapping(shutdown),
        label="shutdown read attempt/result cardinality mismatch",
    )
    shutdown_batch = copy.deepcopy(results["LOCAL_SHUTDOWN"])
    shutdown_batch["result"]["final_terminal_ingress_batch_count"] = 0
    _rehash(canonical, shutdown_batch)
    _expect_rejected(
        canonical,
        lambda: result_type.from_mapping(shutdown_batch),
        label="shutdown batch count differs from attempt/result tuples",
    )

    removed_v1_tags = golden["invariants"]["v1_removal_assertions"]["removed_tags"]
    for operation in ("INGRESS", "LOCAL_SHUTDOWN", "SUBSCRIPTION_DISPATCH"):
        old_tag = next(
            tag
            for tag in removed_v1_tags
            if "RESULT" in tag
            and (
                operation.split("_")[0] in tag
                or operation == "SUBSCRIPTION_DISPATCH"
                and tag.startswith("SUBSCRIPTION_")
            )
        )
        relabelled = copy.deepcopy(results[operation])
        relabelled["result_type"] = old_tag
        _rehash(canonical, relabelled)
        _expect_rejected(
            canonical,
            lambda value=relabelled: result_type.from_mapping(value),
            label=f"{operation} removed V1 result tag",
        )


def _test_result_spec_semantic_validation(
    canonical: Any, contracts: Any, golden: Mapping[str, Any]
) -> None:
    fixtures = golden["fixture_records"]
    spec_type = contracts.CapacityMeasurementOperationSpecV49FV8
    result_type = contracts.CapacityMeasurementOperationResultEvidenceV49FV8
    validate = contracts.validate_capacity_measurement_result_against_spec_v49f_v8
    specs = {
        operation: spec_type.from_mapping(fixtures["operation_specs"][operation])
        for operation in _OPERATIONS
    }
    results = {
        operation: result_type.from_mapping(fixtures["operation_results"][operation])
        for operation in _OPERATIONS
    }
    for operation in _OPERATIONS:
        _require(
            validate(result=results[operation], spec=specs[operation]) is None,
            f"valid {operation} result/spec pair did not validate",
        )

    for index, operation in enumerate(_OPERATIONS):
        wrong_spec = specs[_OPERATIONS[(index + 1) % len(_OPERATIONS)]]
        _expect_rejected(
            canonical,
            lambda result=results[operation], spec=wrong_spec: validate(
                result=result, spec=spec
            ),
            label=f"{operation} result paired with a cross-operation spec",
        )

    ingress_spec = copy.deepcopy(fixtures["operation_specs"]["INGRESS"])
    ingress_spec["spec"]["expected_parser_unit_count"] = 2
    _rehash(canonical, ingress_spec)
    mismatched_ingress_spec = spec_type.from_mapping(ingress_spec)
    _expect_rejected(
        canonical,
        lambda: validate(
            result=results["INGRESS"],
            spec=mismatched_ingress_spec,
        ),
        label="ingress result/spec expectation mismatch",
    )

    ack_spec = copy.deepcopy(fixtures["operation_specs"]["ACK_DEADLINE_EXPIRY"])
    ack_spec["spec"]["expected_outbound_subscription_intent_id"] = "f" * 64
    _rehash(canonical, ack_spec)
    mismatched_ack_spec = spec_type.from_mapping(ack_spec)
    _expect_rejected(
        canonical,
        lambda: validate(
            result=results["ACK_DEADLINE_EXPIRY"], spec=mismatched_ack_spec
        ),
        label="ACK result/spec expectation mismatch",
    )

    shutdown_spec = copy.deepcopy(fixtures["operation_specs"]["LOCAL_SHUTDOWN"])
    shutdown_spec["spec"]["maximum_terminal_ingress_ciphertext_octets"] = 1
    _rehash(canonical, shutdown_spec)
    mismatched_shutdown_spec = spec_type.from_mapping(shutdown_spec)
    _expect_rejected(
        canonical,
        lambda: validate(
            result=results["LOCAL_SHUTDOWN"], spec=mismatched_shutdown_spec
        ),
        label="shutdown result exceeds its signed spec limit",
    )

    for field in ("candidate_id", "attempt_id"):
        forged_result = result_type.from_mapping(
            fixtures["operation_results"]["INGRESS"]
        )
        object.__setattr__(forged_result, field, "f" * 64)
        _expect_rejected(
            canonical,
            lambda value=forged_result: validate(result=value, spec=specs["INGRESS"]),
            label=f"forged result {field}/identity mismatch",
        )

    forged_result_id = result_type.from_mapping(
        fixtures["operation_results"]["INGRESS"]
    )
    object.__setattr__(forged_result_id, "result_evidence_id", "0" * 64)
    _expect_rejected(
        canonical,
        lambda: validate(result=forged_result_id, spec=specs["INGRESS"]),
        label="forged result dataclass identity",
    )
    forged_spec_id = spec_type.from_mapping(fixtures["operation_specs"]["INGRESS"])
    object.__setattr__(forged_spec_id, "operation_spec_id", "0" * 64)
    _expect_rejected(
        canonical,
        lambda: validate(result=results["INGRESS"], spec=forged_spec_id),
        label="forged spec dataclass identity",
    )


def _test_supporting_evidence_adversaries(
    canonical: Any, contracts: Any, golden: Mapping[str, Any]
) -> None:
    fixtures = golden["fixture_records"]
    dispatch_type = contracts.CapacityMeasurementDispatchWindowEvidenceV49FV8
    dispatch = copy.deepcopy(fixtures["dispatch_window_evidence"])
    dispatch["dispatch_completed_monotonic_ns"] = dispatch[
        "dispatch_started_monotonic_ns"
    ]
    _rehash(canonical, dispatch)
    _expect_rejected(
        canonical,
        lambda: dispatch_type.from_mapping(dispatch),
        label="dispatch non-increasing monotonic window",
    )

    due_type = contracts.CapacityMeasurementAckDueDecisionClockEvidenceV49FV8
    due = copy.deepcopy(fixtures["due_decision_clock_evidence"])
    due["dispatch_window_evidence_id"] = "0" * 64
    _rehash(canonical, due)
    _expect_rejected(
        canonical,
        lambda: due_type.from_mapping(due),
        label="due evidence duplicated dispatch ID mismatch",
    )
    due_scenario = copy.deepcopy(fixtures["due_decision_clock_evidence"])
    due_scenario["due_scenario"] = "UNRECOGNIZED"
    _rehash(canonical, due_scenario)
    _expect_rejected(
        canonical,
        lambda: due_type.from_mapping(due_scenario),
        label="due evidence unknown scenario",
    )


def _test_registry_adversaries(
    canonical: Any, contracts: Any, golden: Mapping[str, Any]
) -> None:
    record_type = contracts.CapacityMeasurementTargetFieldRegistryV49FV8
    registry = copy.deepcopy(
        _find_domain(
            golden["target_field_registry"],
            "RiskYieldMMA2MTargetFieldRegistryV4_9F_RawV8",
        )
    )
    _require(len(registry["descriptors"]) == 185, "golden registry is not complete")

    reordered = copy.deepcopy(registry)
    reordered["descriptors"][0], reordered["descriptors"][1] = (
        reordered["descriptors"][1],
        reordered["descriptors"][0],
    )
    _rehash(canonical, reordered)
    _expect_rejected(
        canonical,
        lambda: record_type.from_mapping(reordered),
        label="registry descriptor reordering",
    )

    duplicate = copy.deepcopy(registry)
    duplicate["descriptors"][1] = copy.deepcopy(duplicate["descriptors"][0])
    _rehash(canonical, duplicate)
    _expect_rejected(
        canonical,
        lambda: record_type.from_mapping(duplicate),
        label="registry duplicate descriptor",
    )

    vocabulary = copy.deepcopy(registry)
    phase_definition = next(
        item
        for item in vocabulary["ordered_vocabulary_definitions"]
        if item["vocabulary_id"] == "RAW_V8_SOURCE_FAILURE_PHASE"
    )
    phase_definition["members"].remove("VALUE_VALIDATION")
    _rehash(canonical, vocabulary)
    _expect_rejected(
        canonical,
        lambda: record_type.from_mapping(vocabulary),
        label="registry failure-phase vocabulary drift",
    )

    shape = copy.deepcopy(registry)
    scalar_shape = next(
        item
        for item in shape["ordered_value_shape_definitions"]
        if item["value_shape_id"] == "S"
    )
    scalar_shape["minimum_items"] = 0
    _rehash(canonical, shape)
    _expect_rejected(
        canonical,
        lambda: record_type.from_mapping(shape),
        label="registry scalar shape drift",
    )


def _field_error_form(field: Mapping[str, Any]) -> str:
    errno_number = field["source_errno_number"]
    errno_name = field["source_errno_name"]
    error_class = field["source_error_class"]
    error_digest = field["source_error_detail_sha256"]
    _require(
        (errno_number is None) == (errno_name is None),
        f"{field['field_id']} has a partial errno pair",
    )
    _require(
        (error_class is None) == (error_digest is None),
        f"{field['field_id']} has a partial class/digest pair",
    )
    if errno_number is not None:
        return "OS"
    if error_class is not None:
        return "NON_OS"
    if (
        field["availability"] == "UNAVAILABLE"
        and field["observation_attempt"] == "ATTEMPTED"
    ):
        return "STATUS_ONLY"
    return "NONE"


def _test_source_failure_truth_table(
    canonical: Any, contracts: Any, golden: Mapping[str, Any]
) -> None:
    registry = _find_domain(
        golden["target_field_registry"],
        "RiskYieldMMA2MTargetFieldRegistryV4_9F_RawV8",
    )
    policy = registry["status_reason_policy_definition"]
    expected_error_forms = [
        {
            "error_form": "NONE",
            "errno_pair_policy": "FORBIDDEN",
            "error_class_policy": "FORBIDDEN",
            "error_digest_policy": "FORBIDDEN",
            "class_digest_pair_policy": "BOTH_FORBIDDEN",
        },
        {
            "error_form": "NON_OS",
            "errno_pair_policy": "FORBIDDEN",
            "error_class_policy": "REQUIRED",
            "error_digest_policy": "REQUIRED",
            "class_digest_pair_policy": "BOTH_REQUIRED",
        },
        {
            "error_form": "OS",
            "errno_pair_policy": "REQUIRED",
            "error_class_policy": "OPTIONAL",
            "error_digest_policy": "OPTIONAL",
            "class_digest_pair_policy": "BOTH_OR_NEITHER",
        },
        {
            "error_form": "STATUS_ONLY",
            "errno_pair_policy": "FORBIDDEN",
            "error_class_policy": "FORBIDDEN",
            "error_digest_policy": "FORBIDDEN",
            "class_digest_pair_policy": "BOTH_FORBIDDEN",
        },
    ]
    _require(
        policy["error_form_definitions"] == expected_error_forms,
        "registry error-form truth table differs",
    )
    phase_vocabulary = next(
        item
        for item in registry["ordered_vocabulary_definitions"]
        if item["vocabulary_id"] == "RAW_V8_SOURCE_FAILURE_PHASE"
    )
    _require(
        phase_vocabulary["members"]
        == [
            "FIRST_CLOCK_READ",
            "NONE",
            "SECOND_CLOCK_READ",
            "SOURCE_ADAPTER",
            "VALUE_VALIDATION",
        ],
        "registry source-failure-phase vocabulary differs",
    )

    reason_rules = {item["reason"]: item for item in policy["reason_rules"]}
    _require(len(reason_rules) == 22, "status reason policy is incomplete")
    observations = [
        item
        for item in _walk_mappings(golden)
        if item.get("record_domain") == "RiskYieldMMA2MTargetObservationV4_9F_RawV8"
        and item.get("canonicalization_version") == canonical.CANONICALIZATION_VERSION
    ]
    _require(len(observations) >= 5, "golden full-observation fixtures are incomplete")
    for observation in observations:
        for field in observation["field_observations"]:
            error_form = _field_error_form(field)
            availability = field["availability"]
            if availability != "UNAVAILABLE":
                _require(
                    error_form == "NONE" and field["source_failure_phase"] == "NONE",
                    f"{field['field_id']} has an error tuple outside UNAVAILABLE",
                )
                continue
            reason_rule = reason_rules[field["unavailable_reason"]]
            state = next(
                (
                    item
                    for item in reason_rule["attempt_state_error_forms"]
                    if item["attempt_state"] == field["observation_attempt"]
                ),
                None,
            )
            _require(
                state is not None, f"{field['field_id']} has illegal attempt state"
            )
            _require(
                error_form in state["permitted_error_forms"],
                f"{field['field_id']} has illegal {error_form} error form",
            )
            _require(
                field["source_failure_phase"] in state["permitted_failure_phases"],
                f"{field['field_id']} has illegal source-failure phase",
            )

    coverage = golden["invariants"]["error_form_coverage_observation"]
    coverage_observation = coverage["observation"]
    coverage_bytes = canonical.canonical_json_bytes(coverage_observation)
    _require(
        coverage["covered_error_forms"] == ["NONE", "NON_OS", "OS", "STATUS_ONLY"]
        and coverage["canonical_json_bytes"] == len(coverage_bytes) == 258_652
        and coverage["canonical_json_sha256"]
        == hashlib.sha256(coverage_bytes).hexdigest()
        == "5c48949f7ea6061c2145e84d82327c95924484249e57f3be6e6fec625da77c94",
        "golden error-form coverage observation differs",
    )

    worst = golden["invariants"]["worst_case_after_observation"]["maximum"][
        "observation"
    ]
    descriptors = {item["field_id"]: item for item in registry["descriptors"]}
    field_type = contracts.CapacityMeasurementTargetFieldObservationV49FV8

    os_record = copy.deepcopy(
        next(
            field
            for field in worst["field_observations"]
            if _field_error_form(field) == "OS"
            and field["source_error_class"] is not None
            and field["unavailable_reason"] == "SOURCE_CLOCK_UNAVAILABLE"
        )
    )
    none_record = copy.deepcopy(
        next(
            field
            for field in worst["field_observations"]
            if _field_error_form(field) == "NONE"
        )
    )

    non_os_record = copy.deepcopy(
        next(
            field
            for field in worst["field_observations"]
            if "OBSERVER_INTERNAL_ERROR"
            in descriptors[field["field_id"]]["allowed_status_reasons"]
            and field["observation_method"] != "NOT_ATTEMPTED"
        )
    )
    non_os_record.update(
        {
            "availability": "UNAVAILABLE",
            "value": None,
            "adapter_span_status": "AVAILABLE",
            "observation_started_offset_nanoseconds": 9_007_199_254_740_991,
            "observation_completed_offset_nanoseconds": 9_007_199_254_740_991,
            "unavailable_reason": "OBSERVER_INTERNAL_ERROR",
            "censoring": "NONE",
            "source_errno_number": None,
            "source_errno_name": None,
            "source_failure_phase": "VALUE_VALIDATION",
            "source_error_class": "A" * 256,
        }
    )
    non_os_detail_payload = {
        "field_id": non_os_record["field_id"],
        "observation_method": non_os_record["observation_method"],
        "source_failure_phase": non_os_record["source_failure_phase"],
        "source_errno_number": None,
        "source_errno_name": None,
        "source_error_class": non_os_record["source_error_class"],
    }
    non_os_record["source_error_detail_sha256"] = _semantic_id(
        canonical,
        domain="RiskYieldMMA2MSourceErrorDetailV4_9F_RawV8",
        payload=non_os_detail_payload,
    )
    _rehash(canonical, non_os_record)

    source_adapter_record = copy.deepcopy(non_os_record)
    source_adapter_record["source_failure_phase"] = "SOURCE_ADAPTER"
    source_adapter_detail = {
        **non_os_detail_payload,
        "source_failure_phase": "SOURCE_ADAPTER",
    }
    source_adapter_record["source_error_detail_sha256"] = _semantic_id(
        canonical,
        domain="RiskYieldMMA2MSourceErrorDetailV4_9F_RawV8",
        payload=source_adapter_detail,
    )
    _rehash(canonical, source_adapter_record)

    first_clock_record = copy.deepcopy(os_record)
    first_clock_record.update(
        {
            "observation_method": "NOT_ATTEMPTED",
            "observation_attempt": "NOT_ATTEMPTED",
            "adapter_span_status": "NOT_APPLICABLE",
            "observation_started_offset_nanoseconds": None,
            "observation_completed_offset_nanoseconds": None,
            "source_errno_number": None,
            "source_errno_name": None,
            "source_failure_phase": "FIRST_CLOCK_READ",
            "source_error_class": None,
            "source_error_detail_sha256": None,
        }
    )
    _rehash(canonical, first_clock_record)

    status_record = copy.deepcopy(
        next(
            field
            for field in worst["field_observations"]
            if "ARTIFACT_BOUND_EXCEEDED"
            in descriptors[field["field_id"]]["allowed_status_reasons"]
            and field["observation_method"] != "NOT_ATTEMPTED"
        )
    )
    status_record.update(
        {
            "availability": "UNAVAILABLE",
            "value": None,
            "adapter_span_status": "AVAILABLE",
            "observation_started_offset_nanoseconds": 9_007_199_254_740_991,
            "observation_completed_offset_nanoseconds": 9_007_199_254_740_991,
            "unavailable_reason": "ARTIFACT_BOUND_EXCEEDED",
            "censoring": "NONE",
            "source_errno_number": None,
            "source_errno_name": None,
            "source_failure_phase": "NONE",
            "source_error_class": None,
            "source_error_detail_sha256": None,
        }
    )
    _rehash(canonical, status_record)

    valid_forms = {
        _field_error_form(item)
        for item in (none_record, non_os_record, os_record, status_record)
    }
    _require(
        valid_forms == {"NONE", "NON_OS", "OS", "STATUS_ONLY"},
        "constructed truth-table fixtures omit an error form",
    )
    for error_form, record in (
        ("NONE", none_record),
        ("NON_OS", non_os_record),
        ("OS", os_record),
        ("STATUS_ONLY", status_record),
    ):
        _require(
            field_type.from_mapping(record).as_dict() == record,
            f"production rejects valid {error_form} error form",
        )
    for phase, record in (
        ("FIRST_CLOCK_READ", first_clock_record),
        ("NONE", none_record),
        ("SECOND_CLOCK_READ", os_record),
        ("SOURCE_ADAPTER", source_adapter_record),
        ("VALUE_VALIDATION", non_os_record),
    ):
        _require(
            field_type.from_mapping(record).as_dict() == record,
            f"production rejects valid {phase} source-failure phase",
        )

    os_without_detail = copy.deepcopy(os_record)
    os_without_detail["source_error_class"] = None
    os_without_detail["source_error_detail_sha256"] = None
    _rehash(canonical, os_without_detail)
    _require(
        field_type.from_mapping(os_without_detail).as_dict() == os_without_detail,
        "production rejects OS error with the legal no-class/no-digest form",
    )

    non_os_without_digest = copy.deepcopy(non_os_record)
    non_os_without_digest["source_error_detail_sha256"] = None
    _rehash(canonical, non_os_without_digest)
    _expect_rejected(
        canonical,
        lambda: field_type.from_mapping(non_os_without_digest),
        label="NON_OS error missing its metadata digest",
    )

    os_partial_errno = copy.deepcopy(os_record)
    os_partial_errno["source_errno_name"] = None
    _rehash(canonical, os_partial_errno)
    _expect_rejected(
        canonical,
        lambda: field_type.from_mapping(os_partial_errno),
        label="OS error with a partial errno pair",
    )
    os_partial_detail = copy.deepcopy(os_record)
    os_partial_detail["source_error_detail_sha256"] = None
    _rehash(canonical, os_partial_detail)
    _expect_rejected(
        canonical,
        lambda: field_type.from_mapping(os_partial_detail),
        label="OS error with a partial class/digest pair",
    )

    status_with_phase = copy.deepcopy(status_record)
    status_with_phase["source_failure_phase"] = "SOURCE_ADAPTER"
    _rehash(canonical, status_with_phase)
    _expect_rejected(
        canonical,
        lambda: field_type.from_mapping(status_with_phase),
        label="STATUS_ONLY error with a source-adapter failure phase",
    )

    none_with_class = copy.deepcopy(none_record)
    none_with_class["source_error_class"] = "builtins.RuntimeError"
    _rehash(canonical, none_with_class)
    _expect_rejected(
        canonical,
        lambda: field_type.from_mapping(none_with_class),
        label="NONE error form with an error class",
    )

    first_as_second = copy.deepcopy(first_clock_record)
    first_as_second["source_failure_phase"] = "SECOND_CLOCK_READ"
    _rehash(canonical, first_as_second)
    _expect_rejected(
        canonical,
        lambda: field_type.from_mapping(first_as_second),
        label="not-attempted first-clock failure relabeled as second-clock failure",
    )


def _test_observation_adversaries(
    canonical: Any, contracts: Any, golden: Mapping[str, Any]
) -> None:
    observations = golden["fixture_records"]["target_observations"]
    roles = tuple(item["observation_role"] for item in observations)
    _require(
        roles == ("BEFORE_OPERATION", "AFTER_OPERATION", "OPERATION_AGGREGATE"),
        "OFF observation role order differs",
    )
    for observation in observations:
        _require(
            observation["instrumentation_mode"] == "OFF",
            "OFF fixture is mode-relabeled",
        )
        _require(
            len(observation["field_observations"]) == 185,
            "observation does not contain all registry fields",
        )

    observation_type = contracts.CapacityMeasurementTargetObservationV49FV8
    field_type = contracts.CapacityMeasurementTargetFieldObservationV49FV8
    first = copy.deepcopy(observations[0])

    reordered = copy.deepcopy(first)
    reordered["field_observations"][0], reordered["field_observations"][1] = (
        reordered["field_observations"][1],
        reordered["field_observations"][0],
    )
    _rehash(canonical, reordered)
    _expect_rejected(
        canonical,
        lambda: observation_type.from_mapping(reordered),
        label="target observation field reordering",
    )

    context_mismatch = copy.deepcopy(first)
    nested = context_mismatch["field_observations"][0]
    nested["observation_context_id"] = "f" * 64
    if nested["observation_context_id"] == first["observation_context_id"]:
        nested["observation_context_id"] = "0" * 64
    _rehash(canonical, nested)
    _rehash(canonical, context_mismatch)
    _expect_rejected(
        canonical,
        lambda: observation_type.from_mapping(context_mismatch),
        label="nested field observation context substitution",
    )

    phase_mismatch = copy.deepcopy(first["field_observations"][0])
    phase_mismatch["source_failure_phase"] = "SOURCE_ADAPTER"
    _rehash(canonical, phase_mismatch)
    _expect_rejected(
        canonical,
        lambda: field_type.from_mapping(phase_mismatch),
        label="disabled field with source-adapter failure phase",
    )

    bad_span = copy.deepcopy(first["field_observations"][0])
    bad_span["adapter_span_status"] = "AVAILABLE"
    bad_span["observation_started_offset_nanoseconds"] = 5
    bad_span["observation_completed_offset_nanoseconds"] = 4
    _rehash(canonical, bad_span)
    _expect_rejected(
        canonical,
        lambda: field_type.from_mapping(bad_span),
        label="field observation reversed adapter span",
    )

    mode_relabel = copy.deepcopy(first)
    mode_relabel["instrumentation_mode"] = "ON"
    _rehash(canonical, mode_relabel)
    _expect_rejected(
        canonical,
        lambda: observation_type.from_mapping(mode_relabel),
        label="complete observation mode relabel with an OFF-bound context",
    )


def _test_observation_mode_attempt_role_truth_table(
    canonical: Any, contracts: Any, golden: Mapping[str, Any]
) -> None:
    fixtures = golden["fixture_records"]
    worst = golden["invariants"]["worst_case_after_observation"]["maximum"][
        "observation"
    ]
    context_type = contracts.CapacityMeasurementTargetObservationContextV49FV8
    observation_type = contracts.CapacityMeasurementTargetObservationV49FV8
    attempt_id = worst["attempt_id"]

    non_checkpoint_roles = (
        "BEFORE_OPERATION",
        "AFTER_OPERATION",
        "OPERATION_AGGREGATE",
    )
    all_roles = (*non_checkpoint_roles, "STABLE_CHECKPOINT", "STARTUP_RECOVERY")
    for mode in ("OFF", "ON"):
        for role in all_roles:
            for has_attempt in (False, True):
                updates: dict[str, Any] = {
                    "instrumentation_mode": mode,
                    "observation_role": role,
                    "attempt_id": attempt_id if has_attempt else None,
                    "marker_ordinal": None,
                    "checkpoint_marker_kind": None,
                }
                if role == "STABLE_CHECKPOINT":
                    updates["marker_ordinal"] = 1
                    updates["checkpoint_marker_kind"] = "ACK_DEADLINE_NOT_DUE"
                record = _context_envelope_from_observation(canonical, worst, **updates)
                should_accept = (
                    mode == "ON" and (role != "STABLE_CHECKPOINT" or has_attempt)
                ) or (
                    mode == "OFF"
                    and role in (*non_checkpoint_roles, "STARTUP_RECOVERY")
                )
                label = f"{mode}/{role}/attempt={has_attempt} context"
                if should_accept:
                    _require(
                        context_type.from_mapping(record).as_dict() == record,
                        f"production rejects valid {label}",
                    )
                else:
                    _expect_rejected(
                        canonical,
                        lambda value=record: context_type.from_mapping(value),
                        label=label,
                    )

    checkpoint_operations = {
        "ACK_DEADLINE_NOT_DUE": {"ACK_DEADLINE_EXPIRY"},
        "ACK_DEADLINE_TERMINAL_CONVERGED": {"ACK_DEADLINE_EXPIRY"},
        "DISPATCH_RETURN_READY": {"SUBSCRIPTION_DISPATCH"},
        "INGRESS_RETURN_READY": {"INGRESS"},
        "KERNEL_SEND_RESULT_CONVERGED": {"SUBSCRIPTION_DISPATCH"},
        "LOCAL_CLOSE_DISPATCH_CONVERGED": {"LOCAL_SHUTDOWN"},
        "OUTBOUND_ARTIFACTS_PREPARED": {"SUBSCRIPTION_DISPATCH"},
        "PARSER_UNIT_CONVERGED": {"INGRESS"},
        "RAW_PREFIX_COMMITTED": {"INGRESS"},
        "SHUTDOWN_TERMINAL_CONVERGED": {"LOCAL_SHUTDOWN"},
        "TARGET_ESCAPE_OBSERVED": set(_OPERATIONS),
        "TCP_HALF_CLOSE_CONVERGED": {"LOCAL_SHUTDOWN"},
        "TLS_CONTROL_CONVERGED": {"LOCAL_SHUTDOWN"},
    }
    _require(len(checkpoint_operations) == 13, "checkpoint operation table differs")
    for marker, permitted_operations in checkpoint_operations.items():
        for operation in _OPERATIONS:
            record = _context_envelope_from_observation(
                canonical,
                worst,
                observation_role="STABLE_CHECKPOINT",
                instrumentation_mode="ON",
                operation_kind=operation,
                attempt_id=attempt_id,
                marker_ordinal=1,
                checkpoint_marker_kind=marker,
            )
            label = f"{marker} checkpoint under {operation}"
            if operation in permitted_operations:
                _require(
                    context_type.from_mapping(record).as_dict() == record,
                    f"production rejects valid {label}",
                )
            else:
                _expect_rejected(
                    canonical,
                    lambda value=record: context_type.from_mapping(value),
                    label=label,
                )

    invalid_checkpoint = _context_envelope_from_observation(
        canonical,
        worst,
        observation_role="STABLE_CHECKPOINT",
        instrumentation_mode="ON",
        operation_kind="LOCAL_SHUTDOWN",
        attempt_id=attempt_id,
        marker_ordinal=1,
        checkpoint_marker_kind="SHUTDOWN_COMMAND_STARTED",
    )
    _expect_rejected(
        canonical,
        lambda: context_type.from_mapping(invalid_checkpoint),
        label="stable checkpoint at a forbidden pre-convergence marker",
    )

    static_off_field_ids = {
        "loop.probe_interval_ns",
        "process.filesystem_mount_cgroup_identity_id",
        "process.runtime_environment_id",
    }
    descriptors = {
        item["field_id"]: item
        for item in golden["target_field_registry"]["descriptors"]
    }
    for observation in fixtures["target_observations"]:
        _require(
            observation["instrumentation_mode"] == "OFF"
            and observation["observation_role"] in non_checkpoint_roles,
            "OFF golden contains an illegal role",
        )
        for field in observation["field_observations"]:
            descriptor = descriptors[field["field_id"]]
            if (
                observation["operation_kind"]
                not in descriptor["applicable_operation_kinds"]
            ):
                expected = (
                    "NOT_APPLICABLE",
                    "NOT_APPLICABLE_TO_OPERATION",
                    "NOT_ATTEMPTED",
                )
            elif field["field_id"] in static_off_field_ids:
                expected = ("AVAILABLE", None, "ATTEMPTED")
            elif (
                "NO_FROZEN_PRESSURE_POLICY" in descriptor["allowed_status_reasons"]
                and "INSTRUMENTATION_DISABLED"
                not in descriptor["allowed_status_reasons"]
            ):
                expected = (
                    "UNAVAILABLE",
                    "NO_FROZEN_PRESSURE_POLICY",
                    "NOT_ATTEMPTED",
                )
            else:
                expected = (
                    "UNAVAILABLE",
                    "INSTRUMENTATION_DISABLED",
                    "NOT_ATTEMPTED",
                )
            actual = (
                field["availability"],
                field["unavailable_reason"],
                field["observation_attempt"],
            )
            _require(
                actual == expected,
                f"OFF truth table differs for {field['field_id']}",
            )

    for evidence_key in (
        "error_form_coverage_observation",
        "worst_case_after_observation",
    ):
        evidence = golden["invariants"][evidence_key]
        observation = (
            evidence["observation"]
            if "observation" in evidence
            else evidence["maximum"]["observation"]
        )
        _require(
            observation["instrumentation_mode"] == "ON"
            and all(
                field["unavailable_reason"] != "INSTRUMENTATION_DISABLED"
                for field in observation["field_observations"]
            ),
            f"{evidence_key} violates the ON truth table",
        )

    off_relabel = _fully_recontextualized_observation(
        canonical, worst, instrumentation_mode="OFF"
    )
    _require(
        any(
            field["observation_attempt"] == "ATTEMPTED"
            for field in off_relabel["field_observations"]
        ),
        "OFF relabel regression lost its attempted fields",
    )
    _expect_rejected(
        canonical,
        lambda: observation_type.from_mapping(off_relabel),
        label="fully rehashed ON observation relabeled OFF",
    )

    on_relabel = _fully_recontextualized_observation(
        canonical, fixtures["target_observations"][1], instrumentation_mode="ON"
    )
    _require(
        any(
            field["unavailable_reason"] == "INSTRUMENTATION_DISABLED"
            for field in on_relabel["field_observations"]
        ),
        "ON relabel regression lost its disabled fields",
    )
    _expect_rejected(
        canonical,
        lambda: observation_type.from_mapping(on_relabel),
        label="fully rehashed OFF observation relabeled ON",
    )

    context_semantics = golden["invariants"]["context_semantics"]
    attempt_required_ids = tuple(context_semantics["null_attempt"]["ordered_field_ids"])
    _require(
        len(attempt_required_ids) == 85
        and attempt_required_ids == contracts.RAW_V8_ATTEMPT_REQUIRED_FIELD_IDS_V49F,
        "null-attempt field tuple differs from production authority",
    )
    null_attempt_evidence = golden["invariants"]["null_attempt_observation"]
    null_attempt_off = null_attempt_evidence["observation"]
    null_attempt_off_bytes = canonical.canonical_json_bytes(null_attempt_off)
    _require(
        len(null_attempt_off_bytes)
        == null_attempt_evidence["canonical_json_bytes"]
        == 184_324
        and hashlib.sha256(null_attempt_off_bytes).hexdigest()
        == null_attempt_evidence["canonical_json_sha256"]
        == "05bcbfeb19d71a3a0c8c74f32844c7a97c8af4fc7c7dfb0d2627ca98b7329787",
        "independent null-attempt fixture bytes differ",
    )
    _require(
        observation_type.from_mapping(null_attempt_off).as_dict() == null_attempt_off,
        "production rejects the exact null-attempt OFF fixture",
    )

    # Build an ON/null-attempt control from the independently generated
    # worst-case ON observation.  Every one of the frozen 85 operation-local
    # fields is converted to the exact reached-state N/A form.  This keeps all
    # other context and field evidence unchanged, so restoring one attempted
    # donor at a time isolates the null-attempt rule rather than OFF-mode or
    # byte/identity validation.
    attempted_donor_observation = _fully_recontextualized_observation(
        canonical, worst, attempt_id=None
    )
    null_attempt_on = copy.deepcopy(attempted_donor_observation)
    attempt_required_set = set(attempt_required_ids)
    observed_attempt_required: list[str] = []
    for field in null_attempt_on["field_observations"]:
        if field["field_id"] not in attempt_required_set:
            continue
        observed_attempt_required.append(field["field_id"])
        field.update(
            {
                "availability": "NOT_APPLICABLE",
                "value": None,
                "observation_method": "NOT_ATTEMPTED",
                "observation_attempt": "NOT_ATTEMPTED",
                "adapter_span_status": "NOT_APPLICABLE",
                "observation_started_offset_nanoseconds": None,
                "observation_completed_offset_nanoseconds": None,
                "unavailable_reason": "NOT_APPLICABLE_TO_REACHED_STATE",
                "censoring": "NONE",
                "source_errno_number": None,
                "source_errno_name": None,
                "source_failure_phase": "NONE",
                "source_error_class": None,
                "source_error_detail_sha256": None,
            }
        )
        _rehash(canonical, field)
    _require(
        tuple(observed_attempt_required) == attempt_required_ids,
        "ON null-attempt control did not cover the exact 85-field tuple",
    )
    _rehash(canonical, null_attempt_on)
    _require(
        observation_type.from_mapping(null_attempt_on).as_dict() == null_attempt_on,
        "production rejects a valid ON observation with 85 reached-state N/A fields",
    )

    donors_by_id = {
        field["field_id"]: field
        for field in attempted_donor_observation["field_observations"]
    }
    for field_id in attempt_required_ids:
        donor = donors_by_id[field_id]
        _require(
            donor["observation_attempt"] == "ATTEMPTED",
            f"worst-case donor for {field_id} is not attempted",
        )
        adversary = copy.deepcopy(null_attempt_on)
        field_index = next(
            position
            for position, field in enumerate(adversary["field_observations"])
            if field["field_id"] == field_id
        )
        adversary["field_observations"][field_index] = copy.deepcopy(donor)
        _rehash(canonical, adversary)
        _expect_rejected(
            canonical,
            lambda value=adversary: observation_type.from_mapping(value),
            label=f"null attempt with attempted operation-local field {field_id}",
        )


def _test_registry_aware_worst_case_observation(
    canonical: Any, contracts: Any, golden: Mapping[str, Any]
) -> None:
    proof = golden["invariants"]["worst_case_after_observation"]
    maximum = proof["maximum"]
    observation = maximum["observation"]
    canonical_bytes = canonical.canonical_json_bytes(observation)
    canonical_sha256 = hashlib.sha256(canonical_bytes).hexdigest()

    _require(proof["ceiling_bytes"] == 262_144, "target-observation ceiling differs")
    _require(
        proof["comparison"] == "STRICTLY_LESS_THAN"
        and maximum["strictly_below_ceiling"] is True,
        "worst-case target observation is not strictly below its ceiling",
    )
    _require(
        maximum["canonical_json_bytes"] == len(canonical_bytes) == 259_090,
        "exhaustive worst-case target-observation byte count differs",
    )
    _require(
        maximum["margin_bytes"] == 3_054,
        "worst-case target-observation margin differs",
    )
    _require(
        maximum["canonical_json_sha256"]
        == canonical_sha256
        == "e856f15d9e9ce22e37ef2b24c20111d17872a7464c2330e8888fd6a0ce084c0b",
        "worst-case target-observation byte digest differs",
    )
    _require(
        maximum["enumerated_legal_representation_count"] == 2_815,
        "worst-case legal-representation enumeration differs",
    )
    _require(
        maximum["representation_selection_counts"]
        == {
            "AVAILABLE": 5,
            "NOT_APPLICABLE_TO_OPERATION": 1,
            "NOT_APPLICABLE_TO_REACHED_STATE": 1,
            "NO_FROZEN_PRESSURE_POLICY": 1,
            "SOURCE_CLOCK_UNAVAILABLE_OS_WITH_CLASS": 142,
            "UNSUPPORTED_BY_KERNEL_OS_WITH_CLASS": 35,
        },
        "worst-case representation selection differs",
    )
    _require(
        maximum["observation_id"] == observation["observation_id"],
        "worst-case proof is not bound to its full observation envelope",
    )
    _require(
        maximum["operation_kind"]
        == observation["operation_kind"]
        == "ACK_DEADLINE_EXPIRY",
        "the independently maximal operation differs",
    )
    _require(
        observation["observation_role"] == "AFTER_OPERATION"
        and observation["instrumentation_mode"] == "ON",
        "worst-case envelope is not the frozen ON/AFTER observation",
    )
    _require(
        len(observation["field_observations"]) == 185,
        "worst-case envelope omits registry fields",
    )

    registry = _find_domain(
        golden["target_field_registry"],
        "RiskYieldMMA2MTargetFieldRegistryV4_9F_RawV8",
    )
    _require(
        observation["target_field_registry_id"] == registry["target_field_registry_id"],
        "worst-case observation is not registry-bound",
    )
    _require(
        [item["field_id"] for item in observation["field_observations"]]
        == [item["field_id"] for item in registry["descriptors"]],
        "worst-case observation does not follow exact registry order",
    )

    per_operation = proof["per_operation"]
    expected_operation_bytes = {
        "ACK_DEADLINE_EXPIRY": 259_090,
        "INGRESS": 258_680,
        "LOCAL_SHUTDOWN": 259_085,
        "SUBSCRIPTION_DISPATCH": 258_694,
    }
    _require(
        type(per_operation) is list
        and {item["operation_kind"] for item in per_operation} == set(_OPERATIONS),
        "worst-case proof omits an operation",
    )
    for item in per_operation:
        _require(
            item["canonical_json_bytes"]
            == expected_operation_bytes[item["operation_kind"]]
            < proof["ceiling_bytes"],
            f"{item['operation_kind']} reaches the observation byte ceiling",
        )
        _require(
            item["representation_selection_total"]
            == sum(item["representation_selection_counts"].values())
            == 185,
            f"{item['operation_kind']} representation proof is incomplete",
        )

    nested_expected = {
        "strict_value_union": (3_072, 1_565),
        "target_field_observation": (4_096, 2_548),
        "target_observation_clock_span": (512, 183),
        "target_observation_context_semantic_preimage": (2_048, 1_209),
    }
    for name, (ceiling, measured) in nested_expected.items():
        evidence = proof["nested_bound_evidence"][name]
        maximum_key = (
            "canonical_semantic_preimage_bytes"
            if name == "target_observation_context_semantic_preimage"
            else "canonical_json_bytes"
        )
        _require(
            evidence["ceiling_bytes"] == ceiling
            and evidence["comparison"] == "LESS_THAN_OR_EQUAL"
            and evidence["maximum"][maximum_key] == measured <= ceiling,
            f"{name} bound evidence differs",
        )

    observation_type = contracts.CapacityMeasurementTargetObservationV49FV8
    parsed = observation_type.from_mapping(observation)
    _require(
        _canonical_bytes(parsed) == canonical_bytes,
        "production changed the worst-case target-observation bytes",
    )
    _require(
        observation_type.from_json_bytes(canonical_bytes).as_dict() == observation,
        "production cannot decode the full worst-case target observation",
    )
    _expect_rejected(
        canonical,
        lambda: observation_type.from_json_bytes(
            b" " * (contracts.RAW_V8_MAXIMUM_TARGET_OBSERVATION_BYTES_V49F + 1)
        ),
        label="target observation above the exact byte ceiling",
    )


def _test_observation_root_adversaries(
    canonical: Any, contracts: Any, golden: Mapping[str, Any]
) -> None:
    fixtures = golden["fixture_records"]
    root = fixtures["target_observation_root"]
    observations = fixtures["target_observations"]
    _require(
        root["ordered_observation_ids"]
        == [item["observation_id"] for item in observations],
        "observation root IDs differ from nested fixtures",
    )
    root_type = contracts.CapacityMeasurementTargetObservationRootV49FV8
    wrong_count = copy.deepcopy(root)
    wrong_count["observation_count"] += 1
    _rehash(canonical, wrong_count)
    _expect_rejected(
        canonical,
        lambda: root_type.from_mapping(wrong_count),
        label="observation root count mismatch",
    )
    duplicate = copy.deepcopy(root)
    duplicate["ordered_observation_ids"][1] = duplicate["ordered_observation_ids"][0]
    _rehash(canonical, duplicate)
    _expect_rejected(
        canonical,
        lambda: root_type.from_mapping(duplicate),
        label="observation root duplicate ID",
    )


def _test_observation_root_semantic_validation(
    canonical: Any, contracts: Any, golden: Mapping[str, Any]
) -> None:
    fixtures = golden["fixture_records"]
    root_record = fixtures["target_observation_root"]
    observation_records = fixtures["target_observations"]
    root_type = contracts.CapacityMeasurementTargetObservationRootV49FV8
    observation_type = contracts.CapacityMeasurementTargetObservationV49FV8
    validate = contracts.validate_capacity_measurement_target_observation_root_v49f_v8

    def parse_observations(
        records: Sequence[Mapping[str, Any]],
    ) -> tuple[Any, ...]:
        return tuple(observation_type.from_mapping(value) for value in records)

    def root_for_records(
        records: Sequence[Mapping[str, Any]], **updates: Any
    ) -> dict[str, Any]:
        record = copy.deepcopy(root_record)
        record["observation_count"] = len(records)
        record["ordered_observation_ids"] = [
            value["observation_id"] for value in records
        ]
        record.update(updates)
        return _rehash(canonical, record)

    root = root_type.from_mapping(root_record)
    observations = parse_observations(observation_records)
    _require(
        validate(root=root, observations=observations) is None,
        "golden root and observations failed semantic validation",
    )

    mode_root_record = root_for_records(observation_records, instrumentation_mode="ON")
    _expect_rejected(
        canonical,
        lambda: validate(
            root=root_type.from_mapping(mode_root_record),
            observations=observations,
        ),
        label="rehashed ON root over OFF observation contexts",
    )

    reordered_records = [
        observation_records[1],
        observation_records[0],
        observation_records[2],
    ]
    reordered_root = root_type.from_mapping(root_for_records(reordered_records))
    _expect_rejected(
        canonical,
        lambda: validate(
            root=reordered_root,
            observations=parse_observations(reordered_records),
        ),
        label="rehashed root with invalid observation role order",
    )

    short_records = [observation_records[0], observation_records[2]]
    short_root = root_type.from_mapping(root_for_records(short_records))
    _expect_rejected(
        canonical,
        lambda: validate(
            root=short_root,
            observations=parse_observations(short_records),
        ),
        label="rehashed same-process root with only two observations",
    )

    changed_attempt = _fully_recontextualized_observation(
        canonical, observation_records[0], attempt_id="f" * 64
    )
    attempt_records = [changed_attempt, *observation_records[1:]]
    attempt_root = root_type.from_mapping(root_for_records(attempt_records))
    _expect_rejected(
        canonical,
        lambda: validate(
            root=attempt_root,
            observations=parse_observations(attempt_records),
        ),
        label="rehashed observation attempt differing from its root",
    )

    operation_root_record = root_for_records(
        observation_records, operation_kind="ACK_DEADLINE_EXPIRY"
    )
    _expect_rejected(
        canonical,
        lambda: validate(
            root=root_type.from_mapping(operation_root_record),
            observations=observations,
        ),
        label="rehashed root operation differing from observations",
    )

    wrong_id_root_record = copy.deepcopy(root_record)
    wrong_id_root_record["ordered_observation_ids"][1] = "f" * 64
    if (
        wrong_id_root_record["ordered_observation_ids"][1]
        == observation_records[1]["observation_id"]
    ):
        wrong_id_root_record["ordered_observation_ids"][1] = "0" * 64
    _rehash(canonical, wrong_id_root_record)
    _expect_rejected(
        canonical,
        lambda: validate(
            root=root_type.from_mapping(wrong_id_root_record),
            observations=observations,
        ),
        label="rehashed root with a substituted observation ID",
    )

    forged_registry_root = root_type.from_mapping(root_record)
    object.__setattr__(forged_registry_root, "target_field_registry_id", "0" * 64)
    _expect_rejected(
        canonical,
        lambda: validate(root=forged_registry_root, observations=observations),
        label="forged root registry identity",
    )

    forged_nested_mode = list(parse_observations(observation_records))
    object.__setattr__(
        forged_nested_mode[1],
        "instrumentation_mode",
        contracts.CapacityMeasurementInstrumentationModeV49FV8.ON,
    )
    _expect_rejected(
        canonical,
        lambda: validate(root=root, observations=tuple(forged_nested_mode)),
        label="forged nested observation mode under an OFF root",
    )

    forged_context_id = list(parse_observations(observation_records))
    object.__setattr__(forged_context_id[1], "observation_context_id", "0" * 64)
    _expect_rejected(
        canonical,
        lambda: validate(root=root, observations=tuple(forged_context_id)),
        label="forged nested observation context identity",
    )


def _rehash_checkpoint_selector(
    canonical: Any, selector: dict[str, Any]
) -> dict[str, Any]:
    selector["checkpoint_selector_id"] = _semantic_id(
        canonical,
        domain="RiskYieldMMA2MCheckpointSelectorV1V4_9F_RawV8",
        payload={
            "operation_kind": selector["operation_kind"],
            "selector_length": selector["selector_length"],
            "ordered_checkpoint_selector_entry_ids": selector[
                "ordered_checkpoint_selector_entry_ids"
            ],
        },
    )
    return selector


def _test_v2_selector_contracts(
    canonical: Any, contracts: Any, golden: Mapping[str, Any]
) -> None:
    entry_type = contracts.CapacityMeasurementCheckpointSelectorEntryV49FV8
    selector_type = contracts.CapacityMeasurementCheckpointSelectorV49FV8
    catalog = golden["checkpoint_selector_catalog"]
    by_name = {item["catalog_name"]: item["selector"] for item in catalog}
    _require(
        set(by_name)
        == {
            "ACK_EMPTY",
            "ACK_COVERAGE",
            "INGRESS_EMPTY",
            "INGRESS_COVERAGE",
            "INGRESS_MAX64_PARSER_UNITS",
            "LOCAL_SHUTDOWN_EMPTY",
            "LOCAL_SHUTDOWN_COVERAGE",
            "SUBSCRIPTION_EMPTY",
            "SUBSCRIPTION_COVERAGE",
        },
        "checkpoint selector catalog labels differ",
    )
    for name in (
        "ACK_EMPTY",
        "INGRESS_EMPTY",
        "LOCAL_SHUTDOWN_EMPTY",
        "SUBSCRIPTION_EMPTY",
    ):
        selector = selector_type.from_mapping(by_name[name])
        _require(
            selector.selector_length == 0
            and selector.ordered_entries == ()
            and selector.ordered_checkpoint_selector_entry_ids == (),
            f"{name} is not the canonical empty selector",
        )

    maximum = by_name["INGRESS_MAX64_PARSER_UNITS"]
    parsed_maximum = selector_type.from_mapping(maximum)
    _require(
        parsed_maximum.selector_length == 64
        and [item["selector_position"] for item in maximum["ordered_entries"]]
        == list(range(1, 65))
        and [
            item["occurrence_index_within_kind"] for item in maximum["ordered_entries"]
        ]
        == list(range(1, 65)),
        "maximum selector does not cover exact positions/occurrences 1..64",
    )

    wrong_operation_entry = copy.deepcopy(maximum["ordered_entries"][0])
    wrong_operation_entry["operation_kind"] = "ACK_DEADLINE_EXPIRY"
    _rehash(canonical, wrong_operation_entry)
    _expect_rejected(
        canonical,
        lambda: entry_type.from_mapping(wrong_operation_entry),
        label="selector entry uses a checkpoint forbidden for its operation",
    )

    wrong_position = copy.deepcopy(maximum)
    wrong_position["ordered_entries"][1]["selector_position"] = 3
    _rehash(canonical, wrong_position["ordered_entries"][1])
    wrong_position["ordered_checkpoint_selector_entry_ids"][1] = wrong_position[
        "ordered_entries"
    ][1]["checkpoint_selector_entry_id"]
    _rehash_checkpoint_selector(canonical, wrong_position)
    _expect_rejected(
        canonical,
        lambda: selector_type.from_mapping(wrong_position),
        label="selector position gap",
    )

    duplicate_occurrence = copy.deepcopy(maximum)
    duplicate_occurrence["ordered_entries"][1]["occurrence_index_within_kind"] = 1
    _rehash(canonical, duplicate_occurrence["ordered_entries"][1])
    duplicate_occurrence["ordered_checkpoint_selector_entry_ids"][1] = (
        duplicate_occurrence["ordered_entries"][1]["checkpoint_selector_entry_id"]
    )
    _rehash_checkpoint_selector(canonical, duplicate_occurrence)
    _expect_rejected(
        canonical,
        lambda: selector_type.from_mapping(duplicate_occurrence),
        label="selector duplicate marker occurrence",
    )

    plus_one = copy.deepcopy(maximum)
    extra = copy.deepcopy(plus_one["ordered_entries"][-1])
    extra["selector_position"] = 65
    extra["occurrence_index_within_kind"] = 65
    _rehash(canonical, extra)
    plus_one["ordered_entries"].append(extra)
    plus_one["ordered_checkpoint_selector_entry_ids"].append(
        extra["checkpoint_selector_entry_id"]
    )
    plus_one["selector_length"] = 65
    _rehash_checkpoint_selector(canonical, plus_one)
    _expect_rejected(
        canonical,
        lambda: selector_type.from_mapping(plus_one),
        label="selector exact 64 plus one",
    )


def _test_v2_placeholder_reason_and_context_contracts(
    canonical: Any, contracts: Any, golden: Mapping[str, Any]
) -> None:
    observation_type = contracts.CapacityMeasurementTargetObservationV2V49FV8
    context_type = contracts.CapacityMeasurementTargetObservationContextV2V49FV8
    fixtures = _v2_observation_fixtures(golden)
    placeholders = fixtures["checkpoint_placeholder_observations"]
    _require(
        type(placeholders) is dict
        and set(placeholders) == set(_PLACEHOLDER_FIELD_REASON_BY_CONTEXT_REASON),
        "placeholder fixtures omit a frozen V2 context reason",
    )

    for context_reason, observation in placeholders.items():
        expected_field_reason = _PLACEHOLDER_FIELD_REASON_BY_CONTEXT_REASON[
            context_reason
        ]
        context = observation["observation_context"]
        expected_binding = (
            "UNAVAILABLE_TARGET_BOUNDARY_NOT_REACHED"
            if context_reason == "TARGET_BOUNDARY_NOT_REACHED"
            else "UNAVAILABLE_MARKER_OBSERVER_FAILURE"
        )
        _require(
            context["checkpoint_binding_unavailable_reason"] == context_reason
            and context["checkpoint_binding_status"] == expected_binding
            and context["marker_ordinal"] is None
            and context["checkpoint_marker_kind"] is None,
            f"{context_reason} placeholder context truth differs",
        )
        _require(
            len(observation["field_observations"]) == 185
            and all(
                field["availability"] == "UNAVAILABLE"
                and field["value"] is None
                and field["unavailable_reason"] == expected_field_reason
                and field["observation_method"] == "NOT_ATTEMPTED"
                and field["observation_attempt"] == "NOT_ATTEMPTED"
                and field["adapter_span_status"] == "NOT_APPLICABLE"
                and field["observation_started_offset_nanoseconds"] is None
                and field["observation_completed_offset_nanoseconds"] is None
                and field["censoring"] == "NONE"
                and field["source_errno_number"] is None
                and field["source_errno_name"] is None
                and field["source_failure_phase"] == "NONE"
                and field["source_error_class"] is None
                and field["source_error_detail_sha256"] is None
                for field in observation["field_observations"]
            ),
            f"{context_reason} placeholder is not a uniform 185-field projection",
        )
        _require(
            observation_type.from_mapping(observation).as_dict() == observation,
            f"{context_reason} placeholder failed V2 round trip",
        )

        wrong_dedicated_reason = copy.deepcopy(observation)
        field = wrong_dedicated_reason["field_observations"][0]
        field["unavailable_reason"] = next(
            reason
            for reason in _PLACEHOLDER_PREDICATE_BY_FIELD_REASON
            if reason != expected_field_reason
        )
        _rehash(canonical, field)
        _rehash(canonical, wrong_dedicated_reason)
        _expect_rejected(
            canonical,
            lambda value=wrong_dedicated_reason: observation_type.from_mapping(value),
            label=f"{context_reason} placeholder with another dedicated field reason",
        )

        historical_alias = copy.deepcopy(observation)
        historical_alias["field_observations"][0]["unavailable_reason"] = context_reason
        _rehash(canonical, historical_alias["field_observations"][0])
        _rehash(canonical, historical_alias)
        _expect_rejected(
            canonical,
            lambda value=historical_alias: observation_type.from_mapping(value),
            label=f"{context_reason} placeholder relabelled to historical reason",
        )

        mixed_state = copy.deepcopy(observation)
        mixed_state["field_observations"][0]["observation_attempt"] = "ATTEMPTED"
        _rehash(canonical, mixed_state["field_observations"][0])
        _rehash(canonical, mixed_state)
        _expect_rejected(
            canonical,
            lambda value=mixed_state: observation_type.from_mapping(value),
            label=f"{context_reason} placeholder with attempted field",
        )

    source_placeholder = copy.deepcopy(placeholders["SOURCE_CLOCK_UNAVAILABLE"])
    wrong_binding_context = source_placeholder["observation_context"]
    wrong_binding_context["checkpoint_binding_status"] = (
        "UNAVAILABLE_TARGET_BOUNDARY_NOT_REACHED"
    )
    _rehash(canonical, wrong_binding_context)
    source_placeholder["observation_context_id"] = wrong_binding_context[
        "observation_context_id"
    ]
    for field in source_placeholder["field_observations"]:
        field["observation_context_id"] = source_placeholder["observation_context_id"]
        _rehash(canonical, field)
    _rehash(canonical, source_placeholder)
    _expect_rejected(
        canonical,
        lambda: observation_type.from_mapping(source_placeholder),
        label="source-clock placeholder with boundary-not-reached binding",
    )

    exact = fixtures["checkpoint_exact_marker_observation"]
    _require(
        observation_type.from_mapping(exact).as_dict() == exact,
        "exact-marker V2 observation failed round trip",
    )
    escaped_reason = copy.deepcopy(exact)
    replacement = copy.deepcopy(
        placeholders["OBSERVER_INTERNAL_ERROR"]["field_observations"][0]
    )
    replacement["observation_context_id"] = escaped_reason["observation_context_id"]
    _rehash(canonical, replacement)
    escaped_reason["field_observations"][0] = replacement
    _rehash(canonical, escaped_reason)
    _expect_rejected(
        canonical,
        lambda: observation_type.from_mapping(escaped_reason),
        label="dedicated placeholder reason escaped into exact-marker context",
    )

    context_record = exact["observation_context"]
    wrong_context_id = copy.deepcopy(context_record)
    wrong_context_id["checkpoint_selector_entry_id"] = "f" * 64
    _rehash(canonical, wrong_context_id)
    _require(
        context_type.from_mapping(wrong_context_id).as_dict() == wrong_context_id,
        "standalone context should remain structural before selector replay",
    )


def _test_v2_observation_roots_and_bounds(
    canonical: Any, contracts: Any, golden: Mapping[str, Any]
) -> None:
    observation_type = contracts.CapacityMeasurementTargetObservationV2V49FV8
    root_type = contracts.CapacityMeasurementTargetObservationRootV2V49FV8
    validate = (
        contracts.validate_capacity_measurement_target_observation_root_v2_v49f_v8
    )
    fixtures = _v2_observation_fixtures(golden)
    off_records = fixtures["off_target_observations"]
    root_record = fixtures["off_target_observation_root"]
    observations = tuple(observation_type.from_mapping(item) for item in off_records)
    root = root_type.from_mapping(root_record)
    _require(
        validate(root=root, observations=observations, full_checkpoint_selector=None)
        is None,
        "valid selector-free OFF V2 root failed semantic validation",
    )

    wrong_selector = copy.deepcopy(root_record)
    wrong_selector["full_checkpoint_selector_id"] = "f" * 64
    _rehash(canonical, wrong_selector)
    _expect_rejected(
        canonical,
        lambda: validate(
            root=root_type.from_mapping(wrong_selector),
            observations=observations,
            full_checkpoint_selector=None,
        ),
        label="OFF V2 root carrying a selector",
    )

    flattened = copy.deepcopy(off_records[0])
    flattened["observation_context"] = {
        key: flattened["observation_context"][key] for key in _CONTEXT_PAYLOAD_KEYS
    }
    _rehash(canonical, flattened)
    _expect_rejected(
        canonical,
        lambda: observation_type.from_mapping(flattened),
        label="V1-style context payload substituted for complete V2 context",
    )

    duplicate_context_id = copy.deepcopy(off_records[0])
    duplicate_context_id["observation_context_id"] = "f" * 64
    _rehash(canonical, duplicate_context_id)
    _expect_rejected(
        canonical,
        lambda: observation_type.from_mapping(duplicate_context_id),
        label="V2 observation duplicates a foreign context ID",
    )

    maximum_root_record = fixtures["maximum_selector_target_observation_root"]
    maximum_root = root_type.from_mapping(maximum_root_record)
    _require(
        maximum_root.observation_count == 67,
        "maximum-selector root does not contain exactly 67 observations",
    )
    plus_one_root = copy.deepcopy(maximum_root_record)
    plus_one_root["ordered_observation_ids"].append(
        hashlib.sha256(b"root-count-plus-one").hexdigest()
    )
    plus_one_root["observation_count"] = 68
    _rehash(canonical, plus_one_root)
    _expect_rejected(
        canonical,
        lambda: root_type.from_mapping(plus_one_root),
        label="V2 root exact 67 plus one",
    )

    invariants = golden["invariants"]
    frozen_byte_maxima = invariants["frozen_byte_maxima"]
    _require(
        frozen_byte_maxima["target_observation_strict_ceiling"] == 262_144
        and frozen_byte_maxima["operation_result_strict_ceiling"] == 524_288
        and frozen_byte_maxima["target_observation_root_count_maximum"] == 67
        and frozen_byte_maxima["selector_length_maximum"] == 64
        and frozen_byte_maxima["subscription_kernel_pair_count_maximum"] == 256,
        "V3 frozen byte/cardinality ceilings differ",
    )
    maximum_artifact_contract = invariants[
        "constructive_maxima_external_artifact_contract"
    ]
    _require(
        maximum_artifact_contract
        == {
            "intrinsic_byte_maximum_row_count": 66,
            "outer_result_byte_maximum_row_count": 4,
            "root_application_byte_maximum_row_count": 404,
            "total_byte_maximum_row_count": 474,
            "local_shutdown_counterexample_count": 1,
            "maximum_rows_embedded_in_inventory": False,
            "heuristic_bound_proofs_are_authority": False,
        }
        and "target_observation_v2_bound_proof" not in invariants
        and "operation_result_bound_proof" not in invariants,
        "V3 inventory falsely embeds or authorizes legacy maximum proofs",
    )
    _expect_rejected(
        canonical,
        lambda: observation_type.from_json_bytes(b" " * 262_144),
        label="V2 observation decoder strict ceiling",
    )

    result_type = contracts.CapacityMeasurementOperationResultEvidenceV49FV8
    _expect_rejected(
        canonical,
        lambda: result_type.from_json_bytes(b" " * 524_288),
        label="operation result decoder strict ceiling",
    )

    subscription = copy.deepcopy(
        golden["fixture_records"]["operation_results"]["SUBSCRIPTION_DISPATCH"]
    )
    subscription["result"]["ordered_kernel_attempt_event_ids"] = [
        hashlib.sha256(f"attempt:{index}".encode()).hexdigest() for index in range(257)
    ]
    subscription["result"]["ordered_kernel_result_event_ids"] = [
        hashlib.sha256(f"result:{index}".encode()).hexdigest() for index in range(257)
    ]
    _rehash(canonical, subscription)
    _expect_rejected(
        canonical,
        lambda: result_type.from_mapping(subscription),
        label="subscription kernel-pair exact 256 plus one",
    )


def _test_counter_adversaries(
    canonical: Any, contracts: Any, golden: Mapping[str, Any]
) -> None:
    schema_type = contracts.CapacityMeasurementOperationCounterSnapshotSchemaV49FV8
    schema = copy.deepcopy(
        _find_domain(
            golden["operation_counter_schema"],
            "RiskYieldMMA2MOperationCounterSnapshotSchemaV4_9F_RawV8",
        )
    )
    reordered = copy.deepcopy(schema)
    (
        reordered["ordered_counter_field_ids"][0],
        reordered["ordered_counter_field_ids"][1],
    ) = (
        reordered["ordered_counter_field_ids"][1],
        reordered["ordered_counter_field_ids"][0],
    )
    _rehash(canonical, reordered)
    _expect_rejected(
        canonical,
        lambda: schema_type.from_mapping(reordered),
        label="counter schema coordinate reordering",
    )
    expanded = copy.deepcopy(schema)
    excluded = next(
        field_id
        for field_id in expanded["ordered_counter_field_ids"]
        if field_id not in expanded["monotone_counter_field_ids"]
    )
    expanded["monotone_counter_field_ids"].append(excluded)
    expanded["monotone_counter_field_ids"].sort()
    _rehash(canonical, expanded)
    _expect_rejected(
        canonical,
        lambda: schema_type.from_mapping(expanded),
        label="counter schema monotone-set drift",
    )

    snapshot_type = contracts.CapacityMeasurementOperationCounterSnapshotV49FV8
    snapshot = golden["fixture_records"]["counter_snapshot"]
    _require(type(snapshot) is dict, "counter snapshot fixture is not an exact object")
    item = snapshot_type.from_mapping(snapshot)
    _require(item.as_dict() == snapshot, "counter snapshot round trip differs")

    short = copy.deepcopy(snapshot)
    short["availability_bitmap"] = short["availability_bitmap"][:-1]
    _expect_rejected(
        canonical,
        lambda: snapshot_type.from_mapping(short),
        label="counter snapshot short bitmap",
    )
    wrong_id = copy.deepcopy(snapshot)
    wrong_id["counter_schema_id"] = "0" * 64
    _expect_rejected(
        canonical,
        lambda: snapshot_type.from_mapping(wrong_id),
        label="counter snapshot wrong schema",
    )
    one_index = snapshot["availability_bitmap"].find("1")
    if one_index < 0:
        one_index = 0
    null_available = copy.deepcopy(snapshot)
    null_available["availability_bitmap"] = (
        null_available["availability_bitmap"][:one_index]
        + "1"
        + null_available["availability_bitmap"][one_index + 1 :]
    )
    null_available["values"][one_index] = None
    _expect_rejected(
        canonical,
        lambda: snapshot_type.from_mapping(null_available),
        label="counter snapshot available/null mismatch",
    )
    boolean = copy.deepcopy(snapshot)
    boolean["availability_bitmap"] = (
        boolean["availability_bitmap"][:one_index]
        + "1"
        + boolean["availability_bitmap"][one_index + 1 :]
    )
    boolean["values"][one_index] = True
    _expect_rejected(
        canonical,
        lambda: snapshot_type.from_mapping(boolean),
        label="counter snapshot boolean integer",
    )
    floating = copy.deepcopy(boolean)
    floating["values"][one_index] = 1.0
    _expect_rejected(
        canonical,
        lambda: snapshot_type.from_mapping(floating),
        label="counter snapshot floating-point integer",
    )
    integer_subclass = copy.deepcopy(boolean)
    integer_subclass["values"][one_index] = _IntSubclass(1)
    _expect_rejected(
        canonical,
        lambda: snapshot_type.from_mapping(integer_subclass),
        label="counter snapshot integer subclass",
    )


def _run_contracts(repository_root: Path) -> None:
    golden = _load_golden(repository_root)
    if str(repository_root) not in sys.path:
        sys.path.insert(0, str(repository_root))
    canonical = importlib.import_module("riskyieldmm.trading.canonical")
    contracts = importlib.import_module(_MODULE_NAME)

    _test_module_constants(contracts, golden)
    _test_embedded_external_schema_registry_v2_smoke(canonical, golden)
    _test_structural_scanner_and_exact_scalar_types(canonical, contracts, golden)
    _test_all_standalone_codecs(canonical, contracts, golden)
    _test_operation_spec_adversaries(canonical, contracts, golden)
    _test_result_adversaries(canonical, contracts, golden)
    _test_result_spec_semantic_validation(canonical, contracts, golden)
    _test_supporting_evidence_adversaries(canonical, contracts, golden)
    _test_registry_adversaries(canonical, contracts, golden)
    _test_v2_selector_contracts(canonical, contracts, golden)
    _test_v2_placeholder_reason_and_context_contracts(canonical, contracts, golden)
    _test_v2_observation_roots_and_bounds(canonical, contracts, golden)
    _test_counter_adversaries(canonical, contracts, golden)
    print("PASS raw-v8-step2-contracts")


def _run_public_isolation(repository_root: Path) -> None:
    if str(repository_root) not in sys.path:
        sys.path.insert(0, str(repository_root))
    _require(_MODULE_NAME not in sys.modules, "V8 was loaded before package import")
    package = importlib.import_module("riskyieldmm.trading")
    _require(_MODULE_NAME not in sys.modules, "package import loaded private V8 module")
    _require(
        not hasattr(package, _MODULE_BASENAME), "package exports private V8 module"
    )
    for class_name in _DOMAIN_TO_CLASS_NAME.values():
        _require(not hasattr(package, class_name), f"package exports {class_name}")
    print("PASS raw-v8-public-isolation")


def _run_v7_extra_loaded_module(repository_root: Path) -> None:
    if str(repository_root) not in sys.path:
        sys.path.insert(0, str(repository_root))
    source = importlib.import_module(
        "riskyieldmm.trading.physical_transport_capacity_source_observation_v49f"
    )
    importlib.import_module(_MODULE_NAME)
    try:
        observed = source.observe_current_source_v49f(
            repository_root=repository_root,
            deployment_source_tree_sha256="0" * 64,
        )
    except source.SourceObservationV49FError as exc:
        detail = str(exc)
        _require(_MODULE_NAME in detail, "V7 rejection omitted the V8 module name")
        _require(
            "outside the frozen release inventory" in detail,
            "V7 rejection used the wrong extra-module classification",
        )
    else:
        observed.close()
        raise HarnessFailure("V7 observer accepted loaded Raw V8 as existing authority")
    print("PASS v7-rejected-raw-v8-extra-loaded-module")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--case",
        required=True,
        choices=("contracts", "public-isolation", "v7-extra-loaded-module"),
    )
    parser.add_argument("--repository-root", required=True, type=Path)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    namespace = _parser().parse_args(arguments)
    repository_root = namespace.repository_root.resolve(strict=True)
    if namespace.case == "contracts":
        _run_contracts(repository_root)
    elif namespace.case == "public-isolation":
        _run_public_isolation(repository_root)
    else:
        _run_v7_extra_loaded_module(repository_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

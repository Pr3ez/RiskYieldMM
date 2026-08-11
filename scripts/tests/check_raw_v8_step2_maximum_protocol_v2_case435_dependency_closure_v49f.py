#!/usr/bin/env python3
"""Freeze and verify the case-435 exact-optimizer dependency closure.

This checker is deliberately not an optimizer and not a witness producer.  It
reads the accepted JSON authorities plus the accepted rule-runtime source as
data, reconstructs the complete case-435 application/type/rule closure, and
proves the only factorization that is currently justified:

* root/selector/sequence/context state is an explicit separator;
* conditioned on that separator and the fixed authorities, 182 fields are
  singleton components and the three A1 FIFO fields are one coupled component;
* semantic identities are deterministic fixed-width projections; and
* canonical record composition is additive because the already accepted
  260,909-octet superset proof makes the 262,144-octet LT codec cap non-binding.

No exact case-435 maximum or attaining witness is claimed here.
"""

from __future__ import annotations

import ast
import hashlib
import json
import pathlib
import sys
from typing import Any

SEED_RELATIVE_PATH = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.json"
)
INVENTORY_RELATIVE_PATH = "tests/raw_v8_step2_inventory_v4_v49f.json"
STRUCTURAL_REGISTRY_RELATIVE_PATH = (
    "scripts/tests/raw_v8_step2_external_schema_v2_structural_registry_v49f.json"
)
RULE_LITERAL_AUTHORITY_RELATIVE_PATH = (
    "scripts/tests/raw_v8_step2_external_schema_v2_rule_literal_authority_v49f.json"
)
RULE_APPLICATION_LEDGER_RELATIVE_PATH = (
    "scripts/tests/raw_v8_step2_external_schema_v2_rule_application_ledger_v49f.json"
)
RULE_RUNTIME_RELATIVE_PATH = (
    "scripts/tests/validate_raw_v8_step2_external_schema_v2_rule_runtime_v49f.py"
)
CASE435_ANALYZER_RELATIVE_PATH = (
    "scripts/tests/check_raw_v8_step2_maximum_protocol_v2_case435_attainability_v49f.py"
)

PINNED_RAW_SHA256 = {
    SEED_RELATIVE_PATH: (
        "a75a2f352e8513b7ff0043693a0c65ebbf4bc6f06859354789af69e1162b0e4f"
    ),
    INVENTORY_RELATIVE_PATH: (
        "de91eac92d1c36cf1670b2484392fbf1c633d75f928c8e70fcd5e71ae798db2b"
    ),
    STRUCTURAL_REGISTRY_RELATIVE_PATH: (
        "9160297ff316c5931737c92f8b359f0a1e2ec22f0aa996ef3b09cf830dc96bf3"
    ),
    RULE_LITERAL_AUTHORITY_RELATIVE_PATH: (
        "aba3461059367904734e2eb9ae404787b9aab5ed4c3fbcd292925a364926cce2"
    ),
    RULE_APPLICATION_LEDGER_RELATIVE_PATH: (
        "979d7affe2d745d46f5977d9d69a4d1efa473f95c1a374737bf34181d9dac282"
    ),
    RULE_RUNTIME_RELATIVE_PATH: (
        "47aa90d897e8dbae5e244b7c04cbd82dfe036b0292d36ef0f5552c868627ab22"
    ),
    CASE435_ANALYZER_RELATIVE_PATH: (
        "9c524159509c93d45e6e00ace592498c8bf61bfffab0f3d9167f265482f92b22"
    ),
}

CASE_POSITION = 435
PROFILE_POSITION = 369
PROFILE_ID = "505dac244288e6fb666919c99567f883c28ed573a898ce2a5dd680744dd57540"
PLAN_ID = "9f8cd8303e3a9360986f0294210dda931e827af6eed4ec76b0c084e54f722c4a"
PROGRAM_ID = "0e4a94fb5b99c464e7db1ef0fc0525b9408683a004a5ea034fcfbf5c427eb4e8"
MEASURED_SEQUENCE_ORDINAL = 64
TARGET_FIELD_COUNT = 185
CASE435_SUPERSET_ANALYSIS_ID = (
    "b126fb9bef8439baf49c993c036c80a874a03ab0e8f6ab1be016d140dd5d0491"
)
CASE435_LEGAL_SUPERSET_OCTETS = 260_909
TARGET_OBSERVATION_CODEC_LIMIT = 262_144

SELECTED_APPLICATIONS = (
    (
        "APPLY/SELECTOR_MARKER_CONTRACT_V1",
        "RULE/CROSS/SELECTOR_MARKER_CONTRACT_V1",
        "30f3a8688435dff87bc5ff329e7a9dd6bbbf40c71de5dd746a4cb1e9008b3ee5",
        1,
    ),
    (
        "APPLY/V2_OBSERVATION_AGGREGATE_REGISTRY_V1",
        "RULE/CROSS/V2_OBSERVATION_AGGREGATE_REGISTRY_V1",
        "0fff77cbc03f9fcf019e8352875d9b7f49a3ab8a0ed374e9d5b9bb2f7f9a38fb",
        67,
    ),
    (
        "APPLY/V2_OBSERVATION_FIELDS_REGISTRY_V1",
        "RULE/CROSS/V2_OBSERVATION_FIELD_REGISTRY_V1",
        "87b0ee70e1eab470868e357facd3bb6eb203ce4ed8363cbd6fa30a6ee86c8d63",
        67,
    ),
    (
        "APPLY/V2_ROOT_OBSERVATION_MEMBERSHIP_V1",
        "RULE/CROSS/V2_ROOT_OBSERVATION_MEMBERSHIP_V1",
        "0737d82dae748ff1bf3b19230be2196973c7d6d0fa6c97ef834e9517e09e5f0a",
        1,
    ),
    (
        "APPLY/V2_ROOT_SELECTOR_LIFECYCLE_V1",
        "RULE/CROSS/V2_ROOT_SELECTOR_LIFECYCLE_V1",
        "86a3acbf53805768a1a462fe28c75a7e7192487f71579ba021aa03d7992a9a42",
        1,
    ),
)

ROOT_TYPES = (
    "CapacityMeasurementTargetFieldDescriptorV1",
    "CheckpointSelectorV1",
    "MarkerContractV1",
    "TargetFieldObservationV1",
    "TargetFieldRegistryV1",
    "TargetObservationRootV2",
    "TargetObservationV2",
)

A1_CONSTRAINT_ID = "A1_FIFO_SEQUENCE_KIND_LENGTH_AND_ORDER_V1"
A1_FIELD_ROLES = (
    ("COUNT", "count_field_id"),
    ("KIND", "kind_field_id"),
    ("SEQUENCE", "sequence_field_id"),
)

DETERMINISTIC_PROJECTIONS = (
    ("CONTEXT_ID", "TargetObservationContextV2", "observation_context_id", False),
    (
        "SOURCE_ERROR_DETAIL_ID",
        "TargetFieldObservationV1",
        "source_error_detail_sha256",
        True,
    ),
    (
        "FIELD_OBSERVATION_ID",
        "TargetFieldObservationV1",
        "field_observation_id",
        False,
    ),
    ("OBSERVATION_ID", "TargetObservationV2", "observation_id", False),
    (
        "SELECTOR_ENTRY_ID",
        "CheckpointSelectorEntryV1",
        "checkpoint_selector_entry_id",
        False,
    ),
    ("SELECTOR_ID", "CheckpointSelectorV1", "checkpoint_selector_id", False),
    (
        "ROOT_ID",
        "TargetObservationRootV2",
        "target_observation_root_sha256",
        False,
    ),
)

RUNTIME_OPERATOR_FUNCTIONS = {
    "A1_FIFO_FIELDS_VALID": "_a1_fifo_fields_valid",
    "CHECKPOINT_SELECTOR_INTRINSIC_VALID": ("_checkpoint_selector_intrinsic_valid"),
    "CHECKPOINT_SELECTOR_MARKER_CONTRACT_ADMITTED": (
        "_checkpoint_selector_marker_contract_admitted"
    ),
    "FIELD_OBSERVATION_INTRINSIC_VALID": "_field_observation_intrinsic_valid",
    "FIELD_OBSERVATION_SATISFIES_DESCRIPTOR_POLICY": (
        "_field_observation_satisfies_descriptor_policy"
    ),
    "SOURCE_ERROR_DETAIL_ID_RECOMPUTES_FROM_FIELD": (
        "_source_error_detail_id_recomputes_from_field"
    ),
    "TARGET_VALUE_SATISFIES_DESCRIPTOR": "_target_value_satisfies_descriptor",
    "V2_FIELD_OBSERVATION_CONTEXT_VALID": ("_v2_field_observation_context_valid"),
    "V2_ROOT_SEQUENCE_SELECTOR_VALID": "_v2_root_sequence_selector_valid",
}

# These are conservative read/coupling contracts.  ``WHOLE_LOCAL_RECORD`` is
# intentionally broader than a leaf-level source audit but cannot hide a
# cross-field edge.  The sole cross-field contract names the exact three A1
# fields from the fixed registry authority.
OPERATOR_DEPENDENCY_CONTRACTS = (
    {
        "operator": "CHECKPOINT_SELECTOR_INTRINSIC_VALID",
        "ordered_read_classes": [
            "FIXED_SELECTOR_WHOLE_RECORD",
            "FIXED_SELECTOR_ENTRY_SEQUENCE",
        ],
        "decision_coupling": "FIXED_AUTHORITY_ONLY",
        "derived_projection": "SELECTOR_AND_ENTRY_IDENTITIES_FIXED_WIDTH",
    },
    {
        "operator": "CHECKPOINT_SELECTOR_MARKER_CONTRACT_ADMITTED",
        "ordered_read_classes": [
            "FIXED_SELECTOR_OPERATION_LENGTH_AND_ENTRY_MARKERS",
            "FIXED_MARKER_CONTRACT_OPERATION_ROWS_AND_LENGTH_LIMIT",
        ],
        "decision_coupling": "FIXED_AUTHORITY_ONLY",
        "derived_projection": None,
    },
    {
        "operator": "FIELD_OBSERVATION_INTRINSIC_VALID",
        "ordered_read_classes": ["ONE_FIELD_WHOLE_LOCAL_RECORD"],
        "decision_coupling": "ONE_FIELD_ONLY",
        "derived_projection": None,
    },
    {
        "operator": "SOURCE_ERROR_DETAIL_ID_RECOMPUTES_FROM_FIELD",
        "ordered_read_classes": [
            "ONE_FIELD_SOURCE_ERROR_PREIMAGE",
            "ONE_FIELD_SOURCE_ERROR_DETAIL_ID",
        ],
        "decision_coupling": "ONE_FIELD_ONLY",
        "derived_projection": "SOURCE_ERROR_DETAIL_SHA256_FIXED_WIDTH",
    },
    {
        "operator": "FIELD_OBSERVATION_SATISFIES_DESCRIPTOR_POLICY",
        "ordered_read_classes": [
            "ONE_FIELD_STATUS_ATTEMPT_SPAN_AND_ERROR_FORM",
            "FIXED_MATCHING_FIELD_DESCRIPTOR",
            "FIXED_STATUS_REASON_POLICY",
        ],
        "decision_coupling": "ONE_FIELD_ONLY",
        "derived_projection": None,
    },
    {
        "operator": "TARGET_VALUE_SATISFIES_DESCRIPTOR",
        "ordered_read_classes": [
            "ONE_FIELD_TARGET_VALUE",
            "FIXED_MATCHING_FIELD_DESCRIPTOR",
            "FIXED_VALUE_CONSTRAINT_SHAPE_AND_VOCABULARY",
        ],
        "decision_coupling": "ONE_FIELD_ONLY",
        "derived_projection": None,
    },
    {
        "operator": "V2_FIELD_OBSERVATION_CONTEXT_VALID",
        "ordered_read_classes": [
            "ONE_FIELD_WHOLE_LOCAL_RECORD",
            "FIXED_MATCHING_FIELD_DESCRIPTOR_AND_ORDINAL",
            "MEASURED_CONTEXT_BINDING_OPERATION_ATTEMPT_MODE_ROLE_MARKER_AND_OBSERVER_SPAN",
        ],
        "decision_coupling": "ONE_FIELD_CONDITIONED_ON_SEPARATOR",
        "derived_projection": "CONTEXT_ID_FIXED_WIDTH",
    },
    {
        "operator": "A1_FIFO_FIELDS_VALID",
        "ordered_read_classes": [
            "A1_COUNT_FIELD_AVAILABILITY_AND_UINT_VALUE",
            "A1_KIND_FIELD_AVAILABILITY_AND_TEXT_LIST_VALUE",
            "A1_SEQUENCE_FIELD_AVAILABILITY_AND_UINT_LIST_VALUE",
            "FIXED_A1_CROSS_FIELD_CONSTRAINT",
        ],
        "decision_coupling": "EXACT_THREE_FIELD_A1_COMPONENT",
        "derived_projection": None,
    },
    {
        "operator": "V2_ROOT_SEQUENCE_SELECTOR_VALID",
        "ordered_read_classes": [
            "ROOT_SHARED_MEMBERS_COUNT_AND_ORDERED_OBSERVATION_IDS",
            "ALL_OBSERVATION_CONTEXT_LIFECYCLE_MEMBERS",
            "ALL_OBSERVATION_IDENTITY_PAYLOADS_FOR_DETERMINISTIC_RECOMPUTATION",
            "FIXED_SELECTOR_WHOLE_RECORD",
        ],
        "decision_coupling": "ROOT_SELECTOR_SEQUENCE_CONTEXT_SEPARATOR",
        "derived_projection": ("OBSERVATION_SELECTOR_AND_ROOT_IDENTITIES_FIXED_WIDTH"),
    },
)

MANIFEST_DOMAIN = (
    "RiskYieldMMStep2MaximumProtocolV2Case435DependencyManifestV1V4_9F_RawV8"
)
PROOF_DOMAIN = (
    "RiskYieldMMStep2MaximumProtocolV2Case435ConditionalFactorizationProofV1V4_9F_RawV8"
)
REPORT_DOMAIN = (
    "RiskYieldMMStep2MaximumProtocolV2Case435DependencyClosureAuditV1V4_9F_RawV8"
)
RUNTIME_FUNCTION_AST_VECTOR_SHA256 = (
    "ab3c94ffba6effaa04c483dd941e0b26c46a6e86c0074ccf0022dee7f87348c4"
)
RUNTIME_CONSTANT_AST_VECTOR_SHA256 = (
    "c35494f1760b7119e2e357b6cc513e2ef0599c1b6214129d6cfa864c86032e83"
)


class DependencyClosureError(RuntimeError):
    """Raised when an authority or dependency invariant differs."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise DependencyClosureError(message)


def _duplicate_guard(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result, f"duplicate JSON member: {key}")
        result[key] = value
    return result


def _reject_number(value: str) -> Any:
    raise DependencyClosureError(f"floating or non-finite JSON number: {value}")


def _strict_load(raw: bytes, label: str) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8", errors="strict")
        _require(not text.startswith("\ufeff"), f"{label} has a BOM")
        value = json.loads(
            text,
            object_pairs_hook=_duplicate_guard,
            parse_float=_reject_number,
            parse_constant=_reject_number,
        )
    except (UnicodeError, json.JSONDecodeError) as error:
        raise DependencyClosureError(f"{label} is not strict JSON") from error
    _require(type(value) is dict, f"{label} root is not an object")
    return value


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8", errors="strict")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _identity(domain: str, payload: Any) -> str:
    return _sha256(_canonical_bytes({"domain": domain, "payload": payload}))


def _load_authorities(root: pathlib.Path) -> tuple[dict[str, Any], ...]:
    values: list[dict[str, Any]] = []
    for relative in (
        SEED_RELATIVE_PATH,
        INVENTORY_RELATIVE_PATH,
        STRUCTURAL_REGISTRY_RELATIVE_PATH,
        RULE_LITERAL_AUTHORITY_RELATIVE_PATH,
        RULE_APPLICATION_LEDGER_RELATIVE_PATH,
    ):
        raw = (root / relative).read_bytes()
        _require(
            _sha256(raw) == PINNED_RAW_SHA256[relative], f"hash differs: {relative}"
        )
        values.append(_strict_load(raw, relative))
    return tuple(values)


def _index(
    rows: Any,
    member: str,
    label: str,
) -> dict[str, dict[str, Any]]:
    _require(type(rows) is list, f"{label} is not an array")
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        _require(type(row) is dict, f"{label} row is not an object")
        key = row.get(member)
        _require(type(key) is str and key not in result, f"{label} key differs")
        result[key] = row
    return result


def _json_pointer(root: Any, pointer: str) -> Any:
    _require(pointer.startswith("/"), "JSON pointer is not absolute")
    current = root
    for encoded in pointer[1:].split("/"):
        member = encoded.replace("~1", "/").replace("~0", "~")
        if type(current) is list:
            _require(member.isdigit(), "JSON pointer array index differs")
            current = current[int(member)]
        else:
            _require(
                type(current) is dict and member in current, "JSON pointer unresolved"
            )
            current = current[member]
    return current


def _schema_closure(
    registry: dict[str, Any],
    root_types: tuple[str, ...],
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    types = _index(registry["ordered_external_type_descriptors"], "type_name", "type")
    schemas = _index(registry["value_schema_catalog"], "value_schema_id", "schema")
    pending_types = list(root_types)
    pending_schemas: list[str] = []
    seen_types: set[str] = set()
    seen_schemas: set[str] = set()
    while pending_types or pending_schemas:
        if pending_types:
            type_name = pending_types.pop()
            if type_name in seen_types:
                continue
            descriptor = types.get(type_name)
            _require(descriptor is not None, f"type is unresolved: {type_name}")
            seen_types.add(type_name)
            for member in descriptor.get("record_member_descriptors") or []:
                pending_schemas.append(member["value_schema_id"])
            union = descriptor.get("tagged_union_descriptor") or {}
            for alternative in union.get("ordered_alternatives", []):
                pending_types.append(alternative["referenced_type_name"])
            continue
        schema_id = pending_schemas.pop()
        if schema_id in seen_schemas:
            continue
        schema = schemas.get(schema_id)
        _require(schema is not None, f"schema is unresolved: {schema_id}")
        seen_schemas.add(schema_id)
        if schema.get("referenced_type_name") is not None:
            pending_types.append(schema["referenced_type_name"])
        if schema.get("array_item_value_schema_id") is not None:
            pending_schemas.append(schema["array_item_value_schema_id"])

    type_rows = []
    intrinsic_rule_ids: set[str] = set()
    for position, type_name in enumerate(sorted(seen_types), 1):
        descriptor = types[type_name]
        intrinsic = descriptor["ordered_intrinsic_rule_ids"]
        intrinsic_rule_ids.update(intrinsic)
        type_rows.append(
            {
                "closure_type_position": position,
                "type_name": type_name,
                "external_type_descriptor_id": descriptor[
                    "external_type_descriptor_id"
                ],
                "type_form": descriptor["type_form"],
                "codec_byte_bound_relation": descriptor["codec_byte_bound_relation"],
                "codec_octet_limit": descriptor["codec_octet_limit"],
                "ordered_intrinsic_rule_ids": intrinsic,
            }
        )
    return type_rows, sorted(seen_schemas), sorted(intrinsic_rule_ids)


def _rule_manifest_row(rule: dict[str, Any]) -> dict[str, Any]:
    input_paths = []
    operators = []
    for node in rule["ordered_expression_nodes"]:
        operators.append(node["operator"])
        if node["operator"] == "INPUT_PATH":
            input_paths.append(
                {
                    "expression_position": node["expression_position"],
                    "input_binding_name": node["input_binding_name"],
                    "typed_member_path": node["typed_member_path"],
                }
            )
    return {
        "rule_id": rule["rule_id"],
        "rule_descriptor_id": rule["step2_cross_field_rule_descriptor_id"],
        "rule_scope": rule["rule_scope"],
        "expression_node_count": len(rule["ordered_expression_nodes"]),
        "ordered_input_path_records": input_paths,
        "ordered_operator_names": operators,
        "canonical_rule_sha256": _sha256(_canonical_bytes(rule)),
    }


def _runtime_source_closure(raw: bytes) -> dict[str, Any]:
    try:
        tree = ast.parse(raw.decode("utf-8", errors="strict"))
    except (UnicodeError, SyntaxError) as error:
        raise DependencyClosureError("rule runtime source is not parseable") from error
    functions = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    pending = list(RUNTIME_OPERATOR_FUNCTIONS.values())
    seen: set[str] = set()
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        node = functions.get(name)
        _require(node is not None, f"runtime function is absent: {name}")
        seen.add(name)
        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue
            called: str | None = None
            if isinstance(child.func, ast.Name):
                called = child.func.id
            elif (
                isinstance(child.func, ast.Attribute)
                and isinstance(child.func.value, ast.Name)
                and child.func.value.id in {"self", "cls"}
            ):
                called = child.func.attr
            if called in functions and called not in seen:
                pending.append(called)

    function_rows = []
    loaded_constants: set[str] = set()
    for position, name in enumerate(sorted(seen), 1):
        node = functions[name]
        dumped = ast.dump(node, annotate_fields=True, include_attributes=False)
        function_rows.append(
            {
                "function_position": position,
                "function_name": name,
                "function_ast_sha256": _sha256(dumped.encode("utf-8")),
            }
        )
        loaded_constants.update(
            child.id
            for child in ast.walk(node)
            if isinstance(child, ast.Name)
            and isinstance(child.ctx, ast.Load)
            and child.id.isupper()
        )

    assignments: dict[str, ast.AST] = {}
    for node in tree.body:
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        for target in targets:
            if isinstance(target, ast.Name) and target.id in loaded_constants:
                assignments[target.id] = node
    _require(
        set(assignments) == loaded_constants,
        "runtime dependency constant closure is unresolved",
    )
    constant_rows = []
    for position, name in enumerate(sorted(assignments), 1):
        dumped = ast.dump(
            assignments[name], annotate_fields=True, include_attributes=False
        )
        constant_rows.append(
            {
                "constant_position": position,
                "constant_name": name,
                "constant_ast_sha256": _sha256(dumped.encode("utf-8")),
            }
        )
    return {
        "operator_root_function_by_name": dict(
            sorted(RUNTIME_OPERATOR_FUNCTIONS.items())
        ),
        "ordered_transitive_function_ast_records": function_rows,
        "ordered_loaded_constant_ast_records": constant_rows,
        "function_ast_vector_sha256": _sha256(_canonical_bytes(function_rows)),
        "constant_ast_vector_sha256": _sha256(_canonical_bytes(constant_rows)),
    }


def _conditional_components(
    field_ids: list[str],
    cross_edges: list[dict[str, Any]],
) -> list[list[str]]:
    adjacency = {field_id: set() for field_id in field_ids}
    for edge in cross_edges:
        left = edge["left_field_id"]
        right = edge["right_field_id"]
        _require(
            left in adjacency and right in adjacency, "cross-field edge is unresolved"
        )
        _require(left != right, "cross-field edge is reflexive")
        adjacency[left].add(right)
        adjacency[right].add(left)
    components: list[list[str]] = []
    remaining = set(field_ids)
    while remaining:
        start = min(remaining)
        stack = [start]
        component: set[str] = set()
        while stack:
            current = stack.pop()
            if current in component:
                continue
            component.add(current)
            stack.extend(adjacency[current] - component)
        remaining -= component
        components.append(sorted(component))
    return sorted(components, key=lambda values: (values[0], len(values), values))


def validate_dependency_manifest(manifest: dict[str, Any]) -> None:
    required = {
        "manifest_version",
        "case_binding",
        "authority_sha256_by_path",
        "ordered_fixed_authority_records",
        "ordered_application_records",
        "ordered_schema_closure_type_records",
        "ordered_schema_closure_value_schema_ids",
        "ordered_rule_records",
        "ordered_operator_dependency_contracts",
        "runtime_source_closure",
        "ordered_deterministic_projection_records",
        "separator_contract",
        "ordered_field_separator_edges",
        "ordered_cross_field_edges",
        "ordered_conditional_component_records",
        "canonical_composition_contract",
        "global_codec_constraint",
        "case435_dependency_manifest_id",
    }
    _require(set(manifest) == required, "dependency manifest members differ")
    supplied_identity = manifest["case435_dependency_manifest_id"]
    payload = {
        key: value
        for key, value in manifest.items()
        if key != "case435_dependency_manifest_id"
    }
    _require(
        supplied_identity == _identity(MANIFEST_DOMAIN, payload),
        "dependency manifest identity differs",
    )
    case = manifest["case_binding"]
    _require(
        case
        == {
            "case_position": CASE_POSITION,
            "profile_position": PROFILE_POSITION,
            "constraint_scope_profile_id": PROFILE_ID,
            "logical_count_plan_id": PLAN_ID,
            "profile_conditioning_program_id": PROGRAM_ID,
            "measured_type_name": "TargetObservationV2",
            "measured_sequence_ordinal": MEASURED_SEQUENCE_ORDINAL,
            "operation_kind": "INGRESS",
            "selector_present": True,
            "selector_length": 64,
            "observation_count": 67,
        },
        "case-435 binding differs",
    )
    operators = [
        row["operator"] for row in manifest["ordered_operator_dependency_contracts"]
    ]
    _require(
        operators == sorted(RUNTIME_OPERATOR_FUNCTIONS),
        "operator dependency closure differs",
    )
    _require(
        manifest["ordered_operator_dependency_contracts"]
        == sorted(OPERATOR_DEPENDENCY_CONTRACTS, key=lambda row: row["operator"]),
        "operator dependency contract differs",
    )
    _require(
        manifest["authority_sha256_by_path"] == dict(sorted(PINNED_RAW_SHA256.items())),
        "dependency authority identity differs",
    )
    applications = manifest["ordered_application_records"]
    _require(
        len(applications) == len(SELECTED_APPLICATIONS)
        and [
            (
                row["application_name"],
                row["rule_id"],
                row["rule_application_id"],
                row["application_invocation_count_per_scope_case"],
            )
            for row in applications
        ]
        == list(SELECTED_APPLICATIONS),
        "selected application closure differs",
    )
    _require(
        len(manifest["ordered_schema_closure_type_records"]) == 32
        and len(manifest["ordered_schema_closure_value_schema_ids"]) == 133
        and len(manifest["ordered_rule_records"]) == 26
        and len({row["rule_id"] for row in manifest["ordered_rule_records"]}) == 26,
        "schema/rule closure count differs",
    )
    runtime = manifest["runtime_source_closure"]
    _require(
        runtime["operator_root_function_by_name"]
        == dict(sorted(RUNTIME_OPERATOR_FUNCTIONS.items()))
        and len(runtime["ordered_transitive_function_ast_records"]) == 24
        and len(runtime["ordered_loaded_constant_ast_records"]) == 9
        and runtime["function_ast_vector_sha256"] == RUNTIME_FUNCTION_AST_VECTOR_SHA256
        and runtime["constant_ast_vector_sha256"] == RUNTIME_CONSTANT_AST_VECTOR_SHA256,
        "runtime source dependency closure differs",
    )
    projections = manifest["ordered_deterministic_projection_records"]
    _require(
        [
            (
                row["projection_kind"],
                row["owner_type_name"],
                row["member_name"],
                row["nullable"],
            )
            for row in projections
        ]
        == list(DETERMINISTIC_PROJECTIONS)
        and all(
            row["schema_kind"] == "TEXT"
            and row["language_kind"] == "BUILTIN"
            and row["built_in_language_kind"] == "LOWERCASE_SHA256"
            and row["canonical_octets_when_present"] == 66
            and row["canonical_octets_when_null"] == (4 if row["nullable"] else None)
            for row in projections
        ),
        "deterministic projection closure differs",
    )
    separator = manifest["separator_contract"]
    _require(
        separator["separator_node_id"] == "ROOT_SELECTOR_SEQUENCE_AND_MEASURED_CONTEXT"
        and separator["separator_enumeration_or_exact_solver_required"] is True
        and separator["unconditional_field_independence_forbidden"] is True,
        "separator contract differs",
    )
    field_edges = manifest["ordered_field_separator_edges"]
    _require(
        len(field_edges) == TARGET_FIELD_COUNT, "field/separator edge count differs"
    )
    _require(
        len({row["field_id"] for row in field_edges}) == TARGET_FIELD_COUNT
        and all(row["separator_node_id"] == "MEASURED_CONTEXT" for row in field_edges),
        "field/separator closure differs",
    )
    a1 = manifest["separator_contract"]["ordered_a1_field_ids"]
    expected_edges = {
        tuple(sorted(pair))
        for index, left in enumerate(a1)
        for pair in ((left, right) for right in a1[index + 1 :])
    }
    actual_edges = {
        tuple(sorted((row["left_field_id"], row["right_field_id"])))
        for row in manifest["ordered_cross_field_edges"]
    }
    _require(actual_edges == expected_edges, "A1 cross-field edge closure differs")
    _require(
        all(
            row["source_operator"] == "A1_FIFO_FIELDS_VALID"
            and row["source_constraint_id"] == A1_CONSTRAINT_ID
            for row in manifest["ordered_cross_field_edges"]
        ),
        "A1 cross-field edge authority differs",
    )
    component_rows = manifest["ordered_conditional_component_records"]
    component_fields = [
        field_id for row in component_rows for field_id in row["ordered_field_ids"]
    ]
    _require(
        len(component_rows) == 183
        and sorted(component_fields) == sorted(row["field_id"] for row in field_edges)
        and len(component_fields) == len(set(component_fields)),
        "conditional field partition differs",
    )
    sizes = sorted(len(row["ordered_field_ids"]) for row in component_rows)
    _require(sizes == [1] * 182 + [3], "conditional component sizes differ")
    expected_components = _conditional_components(
        [row["field_id"] for row in field_edges],
        manifest["ordered_cross_field_edges"],
    )
    _require(
        [row["ordered_field_ids"] for row in component_rows] == expected_components,
        "conditional component derivation differs",
    )
    composition = manifest["canonical_composition_contract"]
    _require(
        composition
        == {
            "canonicalization_version": "riskyieldmm_canonical_json_v1",
            "measured_type_name": "TargetObservationV2",
            "field_count": TARGET_FIELD_COUNT,
            "fixed_noncontext_nonfield_octets": 422,
            "field_array_bracket_octets": 2,
            "field_array_comma_octets": 184,
            "composition_formula": (
                "422_PLUS_CONTEXT_CANONICAL_OCTETS_PLUS_2_PLUS_184_PLUS_"
                "SUM_185_FIELD_CANONICAL_OCTETS"
            ),
            "identity_width_policy": (
                "ALL_CROSS_RECORD_IDENTITIES_ARE_RECOMPUTED_LOWERCASE_SHA256_"
                "TEXT_WITH_FIXED_66_CANONICAL_OCTETS_WHEN_PRESENT"
            ),
        },
        "canonical composition contract differs",
    )
    global_codec = manifest["global_codec_constraint"]
    _require(
        global_codec["relation"] == "LT"
        and global_codec["codec_octet_limit"] == TARGET_OBSERVATION_CODEC_LIMIT
        and global_codec["accepted_superset_upper_bound_octets"]
        == CASE435_LEGAL_SUPERSET_OCTETS
        and global_codec["accepted_superset_analysis_id"]
        == CASE435_SUPERSET_ANALYSIS_ID
        and global_codec["accepted_superset_upper_bound_octets"]
        < global_codec["codec_octet_limit"],
        "global codec non-binding proof differs",
    )


def validate_factorization_proof(
    proof: dict[str, Any], manifest: dict[str, Any]
) -> None:
    required = {
        "proof_version",
        "case435_dependency_manifest_id",
        "factorization_kind",
        "separator_policy",
        "fixed_authority_policy",
        "deterministic_projection_policy",
        "conditional_component_count",
        "ordinary_singleton_component_count",
        "a1_coupled_component_count",
        "canonical_composition_policy",
        "global_codec_policy",
        "unconditional_independence_claimed",
        "exact_maximum_derived",
        "attaining_witness_constructed",
        "acceptance_state",
        "next_subgate",
        "case435_conditional_factorization_proof_id",
    }
    _require(set(proof) == required, "factorization proof members differ")
    supplied_identity = proof["case435_conditional_factorization_proof_id"]
    payload = {
        key: value
        for key, value in proof.items()
        if key != "case435_conditional_factorization_proof_id"
    }
    _require(
        supplied_identity == _identity(PROOF_DOMAIN, payload),
        "factorization proof identity differs",
    )
    _require(
        proof["case435_dependency_manifest_id"]
        == manifest["case435_dependency_manifest_id"],
        "factorization/manifest join differs",
    )
    _require(
        proof["factorization_kind"]
        == "NESTED_CONDITIONAL_SEPARATOR_PLUS_EXACT_FIELD_COMPONENTS"
        and proof["conditional_component_count"] == 183
        and proof["ordinary_singleton_component_count"] == 182
        and proof["a1_coupled_component_count"] == 1,
        "factorization result differs",
    )
    _require(
        proof["unconditional_independence_claimed"] is False
        and proof["exact_maximum_derived"] is False
        and proof["attaining_witness_constructed"] is False
        and proof["acceptance_state"]
        == "DEPENDENCY_CLOSURE_ACCEPTED_EXACT_OPTIMIZER_NOT_IMPLEMENTED"
        and proof["next_subgate"] == "A4-P6-C435-C1",
        "factorization disposition differs",
    )


def microdomain_factorization_check() -> dict[str, int]:
    """Compare brute force and the selected conditional decomposition."""

    contexts = (0, 1, 2)
    ordinary_domains = {
        "f0": {0: (1, 4), 1: (2,), 2: (1, 3)},
        "f1": {0: (2,), 1: (1, 5), 2: (4,)},
    }
    a1_domains = {
        0: ((0, 2, 2), (1, 4, 3), (2, 1, 5)),
        1: ((0, 3, 1), (1, 2, 4)),
        2: ((0, 1, 1), (1, 3, 3), (2, 5, 2)),
    }
    base = {0: 7, 1: 11, 2: 13}
    brute_values = []
    for context in contexts:
        for left in ordinary_domains["f0"][context]:
            for right in ordinary_domains["f1"][context]:
                for count, kinds, sequences in a1_domains[context]:
                    if count == 0 or kinds + sequences >= count + 3:
                        brute_values.append(
                            base[context] + left + right + count + kinds + sequences
                        )
    factorized_values = []
    for context in contexts:
        a1_maximum = max(
            count + kinds + sequences
            for count, kinds, sequences in a1_domains[context]
            if count == 0 or kinds + sequences >= count + 3
        )
        factorized_values.append(
            base[context]
            + max(ordinary_domains["f0"][context])
            + max(ordinary_domains["f1"][context])
            + a1_maximum
        )
    brute = max(brute_values)
    factorized = max(factorized_values)
    _require(brute == factorized, "microdomain factorization differs")
    return {
        "context_state_count": len(contexts),
        "brute_force_legal_tuple_count": len(brute_values),
        "brute_force_maximum": brute,
        "factorized_maximum": factorized,
    }


def analyze(repository_root: pathlib.Path | str) -> dict[str, Any]:
    root = pathlib.Path(repository_root)
    seed, inventory, registry, literal_authority, application_ledger = (
        _load_authorities(root)
    )
    _require(
        inventory["external_schema_registry_v2"] == registry,
        "inventory/structural registry differs",
    )
    _require(
        literal_authority["target_field_registry"] == inventory["target_field_registry"]
        and literal_authority["marker_contract"] == inventory["marker_contract"],
        "literal/inventory authority differs",
    )

    recipe = seed["logical_plan_recipe_catalog"]
    plan = recipe["ordered_logical_count_plan_records"][CASE_POSITION - 1]
    _require(
        plan["case_position"] == CASE_POSITION
        and plan["logical_count_plan_id"] == PLAN_ID,
        "case-435 plan differs",
    )
    programs = _index(
        recipe["ordered_profile_conditioning_program_records"],
        "profile_conditioning_program_id",
        "profile program",
    )
    program = programs.get(plan["profile_conditioning_program_id"])
    _require(
        program is not None
        and program["profile_conditioning_program_id"] == PROGRAM_ID
        and program["profile_position"] == PROFILE_POSITION
        and program["maximum_constraint_scope_profile_id"] == PROFILE_ID,
        "case-435 program differs",
    )
    scope_cases = program["scope_root_operation"]["ordered_scope_case_records"]
    _require(
        scope_cases
        == [
            {
                "measured_sequence_ordinal": MEASURED_SEQUENCE_ORDINAL,
                "mode_attempt_pair_position": 1,
                "observation_role_position": 1,
                "root_family_position": 1,
                "scope_case_position": 1,
            }
        ],
        "case-435 scope coordinate differs",
    )
    segment = program["application_schedule_operation"][
        "ordered_schedule_segment_records"
    ]
    _require(type(segment) is list and len(segment) == 1, "case-435 schedule differs")
    segment = segment[0]
    actual_schedule = [
        (
            row["application_name"],
            row["rule_id"],
            row["rule_application_id"],
            row["application_invocation_count_per_scope_case"],
        )
        for row in segment["ordered_application_instruction_records"]
    ]
    _require(
        actual_schedule == list(SELECTED_APPLICATIONS), "case-435 applications differ"
    )
    _require(
        segment["selector_present"] is True
        and segment["observation_count"] == 67
        and segment["application_invocation_count_per_scope_case"] == 137
        and segment["cross_rule_evaluation_count_per_scope_case"] == 12_531
        and segment["direct_cross_expression_node_count_per_scope_case"] == 125_431,
        "case-435 schedule counts differ",
    )

    fixed_rows = []
    for operation in program["ordered_fixed_authority_operations"]:
        value = _json_pointer(inventory, operation["inventory_json_pointer"])
        raw = _canonical_bytes(value)
        _require(
            len(raw) == operation["fixed_canonical_octets"]
            and _sha256(raw) == operation["fixed_canonical_sha256"],
            "case-435 fixed authority bytes differ",
        )
        _require(
            value[operation["identity_member_name"]]
            == operation["expected_authority_id"],
            "case-435 fixed authority identity differs",
        )
        fixed_rows.append(operation)

    registry_rules = _index(
        registry["ordered_cross_field_rule_descriptors"], "rule_id", "registry rule"
    )
    ledger_rules = _index(
        application_ledger["ordered_rule_descriptors"], "rule_id", "ledger rule"
    )
    registry_apps = _index(
        registry["ordered_rule_application_descriptors"],
        "application_name",
        "registry application",
    )
    ledger_apps = _index(
        application_ledger["ordered_rule_application_descriptors"],
        "application_name",
        "ledger application",
    )
    application_rows = []
    selected_cross_rule_ids = []
    for position, (name, rule_id, application_id, invocation_count) in enumerate(
        SELECTED_APPLICATIONS, 1
    ):
        _require(
            registry_apps[name] == ledger_apps[name], "application authority differs"
        )
        app = registry_apps[name]
        _require(
            app["rule_id"] == rule_id and app["rule_application_id"] == application_id,
            "selected application binding differs",
        )
        application_rows.append(
            {
                "application_position": position,
                "application_name": name,
                "rule_id": rule_id,
                "rule_application_id": application_id,
                "application_invocation_count_per_scope_case": invocation_count,
                "application_descriptor_sha256": _sha256(_canonical_bytes(app)),
            }
        )
        selected_cross_rule_ids.append(rule_id)

    type_rows, schema_ids, intrinsic_rule_ids = _schema_closure(registry, ROOT_TYPES)
    _require(
        len(type_rows) == 32
        and len(schema_ids) == 133
        and len(intrinsic_rule_ids) == 21,
        "case-435 schema closure count differs",
    )
    selected_rule_ids = sorted(set(selected_cross_rule_ids) | set(intrinsic_rule_ids))
    rule_rows = []
    observed_complex_operators: set[str] = set()
    for rule_id in selected_rule_ids:
        _require(
            registry_rules[rule_id] == ledger_rules[rule_id], "rule authority differs"
        )
        rule = registry_rules[rule_id]
        rule_rows.append(_rule_manifest_row(rule))
        observed_complex_operators.update(
            node["operator"]
            for node in rule["ordered_expression_nodes"]
            if node["operator"] in RUNTIME_OPERATOR_FUNCTIONS
        )
    _require(
        observed_complex_operators == set(RUNTIME_OPERATOR_FUNCTIONS),
        "case-435 complex operator closure differs",
    )

    target_registry = inventory["target_field_registry"]
    descriptors = target_registry["descriptors"]
    field_ids = [row["field_id"] for row in descriptors]
    _require(
        len(field_ids) == TARGET_FIELD_COUNT
        and len(set(field_ids)) == TARGET_FIELD_COUNT,
        "case-435 field universe differs",
    )
    constraints = target_registry["ordered_cross_field_constraint_definitions"]
    _require(
        type(constraints) is list and len(constraints) == 1,
        "cross-field authority differs",
    )
    a1_constraint = constraints[0]
    _require(
        a1_constraint["cross_field_constraint_id"] == A1_CONSTRAINT_ID,
        "A1 constraint identity differs",
    )
    a1_ids = [a1_constraint[member] for _, member in A1_FIELD_ROLES]
    _require(len(set(a1_ids)) == 3, "A1 field set differs")
    cross_edges = []
    edge_position = 0
    for left_position, left in enumerate(a1_ids):
        for right in a1_ids[left_position + 1 :]:
            edge_position += 1
            cross_edges.append(
                {
                    "edge_position": edge_position,
                    "left_field_id": min(left, right),
                    "right_field_id": max(left, right),
                    "source_operator": "A1_FIFO_FIELDS_VALID",
                    "source_constraint_id": A1_CONSTRAINT_ID,
                }
            )
    cross_edges.sort(key=lambda row: (row["left_field_id"], row["right_field_id"]))
    for position, row in enumerate(cross_edges, 1):
        row["edge_position"] = position
    components = _conditional_components(field_ids, cross_edges)
    component_rows = [
        {
            "component_position": position,
            "component_kind": (
                "A1_FIFO_COUPLED" if len(component) == 3 else "ORDINARY_SINGLETON"
            ),
            "ordered_field_ids": component,
        }
        for position, component in enumerate(components, 1)
    ]
    field_separator_edges = [
        {
            "edge_position": position,
            "field_id": field_id,
            "separator_node_id": "MEASURED_CONTEXT",
            "source_operator": "V2_FIELD_OBSERVATION_CONTEXT_VALID",
        }
        for position, field_id in enumerate(field_ids, 1)
    ]

    runtime_raw = (root / RULE_RUNTIME_RELATIVE_PATH).read_bytes()
    _require(
        _sha256(runtime_raw) == PINNED_RAW_SHA256[RULE_RUNTIME_RELATIVE_PATH],
        "rule runtime hash differs",
    )
    runtime_closure = _runtime_source_closure(runtime_raw)
    case435_analyzer_raw = (root / CASE435_ANALYZER_RELATIVE_PATH).read_bytes()
    _require(
        _sha256(case435_analyzer_raw)
        == PINNED_RAW_SHA256[CASE435_ANALYZER_RELATIVE_PATH],
        "case-435 attainability analyzer hash differs",
    )

    types = _index(registry["ordered_external_type_descriptors"], "type_name", "type")
    schemas = _index(registry["value_schema_catalog"], "value_schema_id", "schema")
    languages = _index(
        registry["text_language_catalog"], "text_language_id", "text language"
    )
    projection_rows = []
    for position, (kind, type_name, member_name, nullable) in enumerate(
        DETERMINISTIC_PROJECTIONS, 1
    ):
        descriptor = types[type_name]
        member = next(
            row
            for row in descriptor["record_member_descriptors"]
            if row["member_name"] == member_name
        )
        schema = schemas[member["value_schema_id"]]
        language = languages[schema["text_language_id"]]
        _require(
            schema["schema_kind"] == "TEXT"
            and schema["nullable"] is nullable
            and language["language_kind"] == "BUILTIN"
            and language["built_in_language_kind"] == "LOWERCASE_SHA256",
            "deterministic projection schema differs",
        )
        projection_rows.append(
            {
                "projection_position": position,
                "projection_kind": kind,
                "owner_type_name": type_name,
                "member_name": member_name,
                "value_schema_id": schema["value_schema_id"],
                "schema_kind": schema["schema_kind"],
                "nullable": nullable,
                "language_kind": language["language_kind"],
                "built_in_language_kind": language["built_in_language_kind"],
                "canonical_octets_when_present": 66,
                "canonical_octets_when_null": 4 if nullable else None,
            }
        )

    fixture = json.loads(
        json.dumps(
            inventory["fixture_records"]["target_observation_v2_fixtures"][
                "checkpoint_exact_marker_observation"
            ]
        )
    )
    fixture["observation_context"] = {}
    fixture["field_observations"] = []
    fixture["observation_context_id"] = "0" * 64
    fixture["observation_id"] = "0" * 64
    placeholder_octets = len(_canonical_bytes(fixture))
    fixed_noncontext_nonfield_octets = (
        placeholder_octets - len(_canonical_bytes({})) - len(_canonical_bytes([]))
    )
    _require(
        placeholder_octets == 426 and fixed_noncontext_nonfield_octets == 422,
        "canonical composition constant differs",
    )

    manifest: dict[str, Any] = {
        "manifest_version": (
            "riskyieldmm.raw_v8_step2.maximum_protocol_v2."
            "case435_dependency_manifest.v1"
        ),
        "case_binding": {
            "case_position": CASE_POSITION,
            "profile_position": PROFILE_POSITION,
            "constraint_scope_profile_id": PROFILE_ID,
            "logical_count_plan_id": PLAN_ID,
            "profile_conditioning_program_id": PROGRAM_ID,
            "measured_type_name": "TargetObservationV2",
            "measured_sequence_ordinal": MEASURED_SEQUENCE_ORDINAL,
            "operation_kind": "INGRESS",
            "selector_present": True,
            "selector_length": 64,
            "observation_count": 67,
        },
        "authority_sha256_by_path": dict(sorted(PINNED_RAW_SHA256.items())),
        "ordered_fixed_authority_records": fixed_rows,
        "ordered_application_records": application_rows,
        "ordered_schema_closure_type_records": type_rows,
        "ordered_schema_closure_value_schema_ids": schema_ids,
        "ordered_rule_records": rule_rows,
        "ordered_operator_dependency_contracts": sorted(
            OPERATOR_DEPENDENCY_CONTRACTS, key=lambda row: row["operator"]
        ),
        "runtime_source_closure": runtime_closure,
        "ordered_deterministic_projection_records": projection_rows,
        "separator_contract": {
            "separator_node_id": "ROOT_SELECTOR_SEQUENCE_AND_MEASURED_CONTEXT",
            "ordered_conditioned_member_classes": [
                "ROOT_SHARED_IDENTIFIERS_MODE_OPERATION_AND_COUNT",
                "FIXED_SELECTOR_AND_ENTRY_IDENTITIES",
                "ALL_OBSERVATION_ROLE_AND_CHECKPOINT_LIFECYCLE_MEMBERS",
                "MEASURED_CONTEXT_BINDING_AND_THREE_CLOCK_SPANS",
                "MEASURED_CONTEXT_ID_FIXED_WIDTH_DERIVATION",
            ],
            "ordered_a1_field_ids": a1_ids,
            "separator_enumeration_or_exact_solver_required": True,
            "unconditional_field_independence_forbidden": True,
        },
        "ordered_field_separator_edges": field_separator_edges,
        "ordered_cross_field_edges": cross_edges,
        "ordered_conditional_component_records": component_rows,
        "canonical_composition_contract": {
            "canonicalization_version": "riskyieldmm_canonical_json_v1",
            "measured_type_name": "TargetObservationV2",
            "field_count": TARGET_FIELD_COUNT,
            "fixed_noncontext_nonfield_octets": fixed_noncontext_nonfield_octets,
            "field_array_bracket_octets": 2,
            "field_array_comma_octets": TARGET_FIELD_COUNT - 1,
            "composition_formula": (
                "422_PLUS_CONTEXT_CANONICAL_OCTETS_PLUS_2_PLUS_184_PLUS_"
                "SUM_185_FIELD_CANONICAL_OCTETS"
            ),
            "identity_width_policy": (
                "ALL_CROSS_RECORD_IDENTITIES_ARE_RECOMPUTED_LOWERCASE_SHA256_"
                "TEXT_WITH_FIXED_66_CANONICAL_OCTETS_WHEN_PRESENT"
            ),
        },
        "global_codec_constraint": {
            "type_name": "TargetObservationV2",
            "relation": "LT",
            "codec_octet_limit": TARGET_OBSERVATION_CODEC_LIMIT,
            "accepted_superset_analysis_id": CASE435_SUPERSET_ANALYSIS_ID,
            "accepted_superset_upper_bound_octets": CASE435_LEGAL_SUPERSET_OCTETS,
            "constraint_role_after_superset_proof": "PROVED_NON_BINDING",
        },
    }
    manifest["case435_dependency_manifest_id"] = _identity(MANIFEST_DOMAIN, manifest)
    validate_dependency_manifest(manifest)

    proof: dict[str, Any] = {
        "proof_version": (
            "riskyieldmm.raw_v8_step2.maximum_protocol_v2."
            "case435_conditional_factorization_proof.v1"
        ),
        "case435_dependency_manifest_id": manifest["case435_dependency_manifest_id"],
        "factorization_kind": (
            "NESTED_CONDITIONAL_SEPARATOR_PLUS_EXACT_FIELD_COMPONENTS"
        ),
        "separator_policy": (
            "MAXIMIZE_OVER_ONLY_ROOT_SEQUENCE_CONTEXT_STATES_PROVED_FEASIBLE_"
            "BY_THE_COMPLETE_LIFECYCLE_RULE_CLOSURE"
        ),
        "fixed_authority_policy": (
            "REGISTRY_MARKER_CONTRACT_AND_SELECTOR_ARE_PINNED_NOT_DECISION_VARIABLES"
        ),
        "deterministic_projection_policy": (
            "RECOMPUTE_CONTEXT_FIELD_OBSERVATION_SELECTOR_AND_ROOT_IDENTITIES_"
            "WITHOUT_TREATING_FIXED_WIDTH_HASHES_AS_DECISION_COUPLINGS"
        ),
        "conditional_component_count": len(component_rows),
        "ordinary_singleton_component_count": sum(
            row["component_kind"] == "ORDINARY_SINGLETON" for row in component_rows
        ),
        "a1_coupled_component_count": sum(
            row["component_kind"] == "A1_FIFO_COUPLED" for row in component_rows
        ),
        "canonical_composition_policy": (
            "EXACT_CANONICAL_MEMBER_ARRAY_COMMA_AND_FIXED_WIDTH_IDENTITY_OCTETS"
        ),
        "global_codec_policy": (
            "NON_BINDING_ONLY_BECAUSE_ACCEPTED_LEGAL_SUPERSET_260909_IS_LT_262144"
        ),
        "unconditional_independence_claimed": False,
        "exact_maximum_derived": False,
        "attaining_witness_constructed": False,
        "acceptance_state": (
            "DEPENDENCY_CLOSURE_ACCEPTED_EXACT_OPTIMIZER_NOT_IMPLEMENTED"
        ),
        "next_subgate": "A4-P6-C435-C1",
    }
    proof["case435_conditional_factorization_proof_id"] = _identity(PROOF_DOMAIN, proof)
    validate_factorization_proof(proof, manifest)
    microdomain = microdomain_factorization_check()

    report: dict[str, Any] = {
        "audit_version": (
            "riskyieldmm.raw_v8_step2.maximum_protocol_v2."
            "case435_dependency_closure_audit.v1"
        ),
        "case435_dependency_manifest": manifest,
        "case435_conditional_factorization_proof": proof,
        "microdomain_factorization_check": microdomain,
        "schema_closure_type_count": len(type_rows),
        "schema_closure_value_schema_count": len(schema_ids),
        "schema_closure_intrinsic_rule_count": len(intrinsic_rule_ids),
        "selected_cross_rule_count": len(selected_cross_rule_ids),
        "selected_rule_count": len(rule_rows),
        "selected_rule_expression_node_count": sum(
            row["expression_node_count"] for row in rule_rows
        ),
        "complex_operator_count": len(RUNTIME_OPERATOR_FUNCTIONS),
        "runtime_function_closure_count": len(
            runtime_closure["ordered_transitive_function_ast_records"]
        ),
        "runtime_constant_closure_count": len(
            runtime_closure["ordered_loaded_constant_ast_records"]
        ),
        "field_count": len(field_ids),
        "ordinary_singleton_component_count": 182,
        "a1_coupled_field_count": 3,
        "conditional_component_count": len(component_rows),
        "dependency_closure_complete": True,
        "conditional_factorization_proved": True,
        "unconditional_factorization_rejected": True,
        "exact_case435_maximum_derived": False,
        "legal_case435_attainer_constructed": False,
        "correction_subgate": "A4-P6-C435-B",
        "next_subgate": "A4-P6-C435-C1",
        "verifier_expansion_state": "HOLD",
        "required_disposition": (
            "IMPLEMENT_EXACT_UPPER_BOUND_AND_INDEPENDENT_ATTAINER_UNDER_THE_"
            "FROZEN_DEPENDENCY_MANIFEST_OR_REMAIN_NO_GO"
        ),
    }
    report["case435_dependency_closure_audit_id"] = _identity(REPORT_DOMAIN, report)
    return report


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) > 1:
        raise SystemExit("usage: check...py [repository-root]")
    root = (
        pathlib.Path(argv[0]).resolve()
        if argv
        else pathlib.Path(__file__).resolve().parents[2]
    )
    try:
        report = analyze(root)
    except (DependencyClosureError, OSError, KeyError, TypeError, ValueError) as error:
        sys.stderr.write(f"CASE435_DEPENDENCY_CLOSURE_REJECT: {error}\n")
        return 1
    sys.stdout.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

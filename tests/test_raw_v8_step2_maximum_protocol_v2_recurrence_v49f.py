"""Independent recurrence checks for the Raw-V8 Step-2 V2 seed catalog.

This module intentionally does not import the seed generator.  It treats the
emitted catalog and its pinned structural-registry/inventory authorities as
untrusted inputs and implements a second, small validator for the closed
instruction set, typed parameters, meter programs, schema graph, batching
proof records, owner-codec residuals, and contextual schedules.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.json"
)
REGISTRY_PATH = ROOT / (
    "scripts/tests/raw_v8_step2_external_schema_v2_structural_registry_v49f.json"
)
INVENTORY_PATH = ROOT / "tests/raw_v8_step2_inventory_v4_v49f.json"

SAFE_INTEGER_MAXIMUM = 9_007_199_254_740_991
UINT128_MAXIMUM = (1 << 128) - 1

EXPRESSION_VERSION = "riskyieldmm.raw_v8_step2_external_schema_v2.u128_expression.v1"
METER_VERSION = "riskyieldmm.raw_v8_step2_external_schema_v2.kernel_meter_program.v1"
TRANSFER_VERSION = (
    "riskyieldmm.raw_v8_step2_external_schema_v2.cell_transfer_program.v1"
)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    assert type(value) is dict
    return value


def _catalog() -> dict[str, Any]:
    return _read_json(CATALOG_PATH)


def _registry() -> dict[str, Any]:
    return _read_json(REGISTRY_PATH)


def _inventory() -> dict[str, Any]:
    return _read_json(INVENTORY_PATH)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    raw = value if type(value) is bytes else _canonical_bytes(value)
    return hashlib.sha256(raw).hexdigest()


def _identity(catalog: dict[str, Any], name: str) -> dict[str, Any]:
    matches = [
        row
        for row in catalog["ordered_identity_domain_records"]
        if row["identity_name"] == name
    ]
    assert len(matches) == 1
    return matches[0]


def _semantic_id(
    catalog: dict[str, Any], identity_name: str, payload: dict[str, Any]
) -> str:
    identity = _identity(catalog, identity_name)
    assert set(payload) == set(identity["ordered_payload_member_names"])
    return _sha256(
        {
            "canonicalization_version": catalog["canonicalization_version"],
            "domain": identity["domain_literal"],
            "payload": payload,
            "schema_version": catalog["measurement_schema_version"],
        }
    )


def _const(value: int) -> dict[str, Any]:
    return {"opcode": "CONST_U128", "value": value}


def _multiplicity() -> dict[str, Any]:
    return {"opcode": "STEP_LOGICAL_TRANSFER_MULTIPLICITY"}


def _parameter(name: str) -> dict[str, Any]:
    return {"opcode": "PARAM_U128", "parameter_name": name}


def _list_count(name: str) -> dict[str, Any]:
    return {"opcode": "PARAM_LIST_COUNT", "parameter_name": name}


def _nonzero(name: str) -> dict[str, Any]:
    return {"opcode": "INDICATOR_PARAM_NONZERO", "parameter_name": name}


def _is_null(name: str) -> dict[str, Any]:
    return {"opcode": "INDICATOR_PARAM_IS_NULL", "parameter_name": name}


def _add(*operands: dict[str, Any]) -> dict[str, Any]:
    return {"opcode": "CHECKED_ADD", "ordered_operands": list(operands)}


def _multiply(*operands: dict[str, Any]) -> dict[str, Any]:
    return {"opcode": "CHECKED_MUL", "ordered_operands": list(operands)}


EXPECTED_EXPRESSION_OPCODES = (
    ("CONST_U128", ("value",)),
    ("STEP_LOGICAL_TRANSFER_MULTIPLICITY", ()),
    ("PARAM_U128", ("parameter_name",)),
    ("PARAM_LIST_COUNT", ("parameter_name",)),
    ("INDICATOR_PARAM_NONZERO", ("parameter_name",)),
    ("CHECKED_ADD", ("ordered_operands",)),
    ("CHECKED_MUL", ("ordered_operands",)),
    ("INDICATOR_PARAM_IS_NULL", ("parameter_name",)),
)

EXPECTED_TRANSFER_OPCODES = (
    ("CELL_FIXED_OCTETS_V1", "FIXED_OCTETS"),
    ("CELL_BOOLEAN_LITERAL_V1", "BOOLEAN_LITERAL"),
    ("CELL_SAFE_INTEGER_INTERVAL_V1", "SAFE_INTEGER_INTERVAL"),
    ("CELL_FINITE_TEXT_V1", "FINITE_TEXT_CATALOG_ORDER"),
    ("CELL_BOUNDED_TEXT_OCTETS_V1", "BOUNDED_TEXT_OCTETS"),
    ("CELL_RELAXED_JSON_STRING_V1", "RELAXED_JSON_STRING"),
    ("CELL_DERIVED_IDENTITY_V1", "DERIVED_IDENTITY_FIXED_WIDTH"),
    ("CELL_NULLABLE_V1", "NULL_AND_NON_NULL_BRANCHES"),
    ("CELL_CHILD_BOUNDS_ALIAS_V1", "CHILD_BOUNDS_ALIAS"),
    ("CELL_ARRAY_BATCH_V1", "ARRAY_CARDINALITY_AND_BATCH_FOLD"),
    ("CELL_ARRAY_STREAM_V1", "ARRAY_CARDINALITY_AND_STREAM_FOLD"),
    ("CELL_RECORD_V1", "RECORD_MEMBER_POSTORDER_FOLD"),
    ("CELL_UNION_V1", "ORDERED_ALTERNATIVE_MAXIMUM"),
    ("CELL_CODEC_INTERSECTION_V1", "FULL_CODEC_COORDINATE_INTERSECTION"),
    ("CELL_SAFE_RELAXATION_V1", "BOUND_PRESERVING_VALIDATED_RELAXATION"),
    ("CELL_SCOPE_ROOT_V1", "BOUND_PRESERVING_AUTHORITY_ROOT"),
    ("CELL_APPLICATION_WRAPPER_V1", "BOUND_PRESERVING_APPLICATION_SCHEDULE"),
    (
        "CELL_LOCAL_SHUTDOWN_SWEEP_V2",
        "EXACT_ELEVEN_CANDIDATE_TWELVE_STATE_LOCAL_ANALYTIC_SWEEP",
    ),
)

# kind: (parameter variant, ordered (name, type, nullable, null semantics), opcode)
EXPECTED_KERNELS: dict[
    str, tuple[str, tuple[tuple[str, str, bool, str | None], ...], str]
] = {
    "FIXED_VALUE": (
        "FIXED_VALUE_PARAMETERS_V1",
        (("fixed_canonical_octets", "NONNEGATIVE_SAFE_INTEGER", False, None),),
        "CELL_FIXED_OCTETS_V1",
    ),
    "EXACT_BOOLEAN": (
        "EXACT_BOOLEAN_PARAMETERS_V1",
        (("boolean_literal", "BOOLEAN", True, "FULL_BOOLEAN_DOMAIN_SENTINEL"),),
        "CELL_BOOLEAN_LITERAL_V1",
    ),
    "SAFE_INTEGER_BAND": (
        "SAFE_INTEGER_PARAMETERS_V1",
        (
            ("integer_minimum", "SIGNED_SAFE_INTEGER", False, None),
            ("integer_maximum", "SIGNED_SAFE_INTEGER", False, None),
            ("ordered_probe_values", "ORDERED_JSON_ARRAY", False, None),
        ),
        "CELL_SAFE_INTEGER_INTERVAL_V1",
    ),
    "TEXT_FINITE": (
        "TEXT_FINITE_PARAMETERS_V1",
        (
            ("text_language_position", "NONNEGATIVE_SAFE_INTEGER", False, None),
            ("text_language_id", "TEXT", False, None),
            ("ordered_literals", "ORDERED_JSON_ARRAY", False, None),
        ),
        "CELL_FINITE_TEXT_V1",
    ),
    "TEXT_BUILTIN_BOUNDED": (
        "TEXT_BUILTIN_BOUNDED_PARAMETERS_V1",
        (
            ("built_in_language_kind", "OPTIONAL_TEXT", True, None),
            ("minimum_canonical_octets", "NONNEGATIVE_SAFE_INTEGER", False, None),
            ("maximum_canonical_octets", "NONNEGATIVE_SAFE_INTEGER", False, None),
            ("text_language_id", "TEXT", False, None),
            ("text_language_position", "NONNEGATIVE_SAFE_INTEGER", False, None),
        ),
        "CELL_BOUNDED_TEXT_OCTETS_V1",
    ),
    "TEXT_BOUNDED_LANGUAGE": (
        "TEXT_BOUNDED_LANGUAGE_PARAMETERS_V1",
        (
            ("text_language_position", "NONNEGATIVE_SAFE_INTEGER", False, None),
            ("text_language_id", "TEXT", False, None),
            ("language_kind", "TEXT", False, None),
            ("built_in_language_kind", "OPTIONAL_TEXT", True, None),
            ("ascii_dfa_id", "OPTIONAL_TEXT", True, None),
            ("unicode_identifier_profile_id", "OPTIONAL_TEXT", True, None),
            ("minimum_utf8_octets", "OPTIONAL_NONNEGATIVE_SAFE_INTEGER", True, None),
            ("maximum_utf8_octets", "OPTIONAL_NONNEGATIVE_SAFE_INTEGER", True, None),
            ("minimum_decoded_octets", "OPTIONAL_NONNEGATIVE_SAFE_INTEGER", True, None),
            ("maximum_decoded_octets", "OPTIONAL_NONNEGATIVE_SAFE_INTEGER", True, None),
            ("decimal_maximum", "OPTIONAL_TEXT", True, None),
        ),
        "CELL_RELAXED_JSON_STRING_V1",
    ),
    "DERIVED_IDENTITY_FIXED_WIDTH": (
        "IDENTITY_WIDTH_PARAMETERS_V1",
        (("canonical_octets", "NONNEGATIVE_SAFE_INTEGER", False, None),),
        "CELL_DERIVED_IDENTITY_V1",
    ),
    "NULLABLE_BRANCH": (
        "NULLABLE_PARAMETERS_V1",
        (("child_step_position", "NONNEGATIVE_SAFE_INTEGER", False, None),),
        "CELL_NULLABLE_V1",
    ),
    "OBJECT_REFERENCE": (
        "OBJECT_REFERENCE_PARAMETERS_V1",
        (
            ("referenced_type_name", "TEXT", False, None),
            ("child_step_position", "NONNEGATIVE_SAFE_INTEGER", False, None),
        ),
        "CELL_CHILD_BOUNDS_ALIAS_V1",
    ),
    "ASSOCIATIVE_HOMOGENEOUS_RUN_BATCH": (
        "ARRAY_RUN_PARAMETERS_V1",
        (
            ("minimum_items", "NONNEGATIVE_SAFE_INTEGER", False, None),
            ("maximum_items", "NONNEGATIVE_SAFE_INTEGER", False, None),
            ("item_value_schema_id", "TEXT", False, None),
            ("item_step_position", "NONNEGATIVE_SAFE_INTEGER", False, None),
            ("ordered_run_records", "ORDERED_JSON_ARRAY", False, None),
            ("observer_closure_record", "JSON_VALUE", False, None),
        ),
        "CELL_ARRAY_BATCH_V1",
    ),
    "ARRAY_STREAM_FOLD": (
        "ARRAY_STREAM_PARAMETERS_V1",
        (
            ("minimum_items", "NONNEGATIVE_SAFE_INTEGER", False, None),
            ("maximum_items", "NONNEGATIVE_SAFE_INTEGER", False, None),
            ("item_step_position", "NONNEGATIVE_SAFE_INTEGER", False, None),
        ),
        "CELL_ARRAY_STREAM_V1",
    ),
    "RECORD_MEMBER_FOLD": (
        "RECORD_PARAMETERS_V1",
        (
            ("record_member_count", "NONNEGATIVE_SAFE_INTEGER", False, None),
            ("ordered_member_records", "ORDERED_JSON_ARRAY", False, None),
            (
                "record_syntax_octets_excluding_child_values",
                "NONNEGATIVE_SAFE_INTEGER",
                False,
                None,
            ),
        ),
        "CELL_RECORD_V1",
    ),
    "TAGGED_UNION_BRANCH": (
        "UNION_PARAMETERS_V1",
        (
            ("ordered_alternative_records", "ORDERED_JSON_ARRAY", False, None),
            (
                "owner_type_name",
                "OPTIONAL_TEXT",
                True,
                "NO_OWNER_CODEC_COORDINATE",
            ),
            ("owner_typed_member_path", "TYPED_PATH", False, None),
        ),
        "CELL_UNION_V1",
    ),
    "CODEC_INTERSECTION": (
        "CODEC_PARAMETERS_V1",
        (
            ("ordered_codec_coordinate_records", "ORDERED_JSON_ARRAY", False, None),
            ("child_step_position", "NONNEGATIVE_SAFE_INTEGER", False, None),
        ),
        "CELL_CODEC_INTERSECTION_V1",
    ),
    "SAFE_RELAXATION": (
        "RELAXATION_PARAMETERS_V1",
        (
            ("safe_relaxation_rule_id", "TEXT", False, None),
            ("authority_predicate_locator", "TYPED_PATH", False, None),
            ("child_step_position", "NONNEGATIVE_SAFE_INTEGER", False, None),
        ),
        "CELL_SAFE_RELAXATION_V1",
    ),
    "SCOPE_ROOT": (
        "SCOPE_ROOT_PARAMETERS_V1",
        (
            ("case_binding", "JSON_VALUE", False, None),
            ("fixed_authority_bindings", "ORDERED_JSON_ARRAY", False, None),
            ("child_step_position", "NONNEGATIVE_SAFE_INTEGER", False, None),
        ),
        "CELL_SCOPE_ROOT_V1",
    ),
    "APPLICATION_SCHEDULE_COUNT": (
        "APPLICATION_SCHEDULE_PARAMETERS_V1",
        (
            (
                "ordered_application_invocation_records",
                "ORDERED_JSON_ARRAY",
                False,
                None,
            ),
            ("child_step_position", "NONNEGATIVE_SAFE_INTEGER", False, None),
        ),
        "CELL_APPLICATION_WRAPPER_V1",
    ),
    "LOCAL_SHUTDOWN_ANALYTIC_LENGTH_SWEEP": (
        "LOCAL_SHUTDOWN_ANALYTIC_PARAMETERS_V1",
        (("local_shutdown_analytic_catalog_id", "TEXT", False, None),),
        "CELL_LOCAL_SHUTDOWN_SWEEP_V2",
    ),
}


def _expected_meter(kind: str) -> dict[str, Any]:
    one = _const(1)
    transition: dict[str, Any]
    if kind in {
        "FIXED_VALUE",
        "TEXT_BUILTIN_BOUNDED",
        "TEXT_BOUNDED_LANGUAGE",
        "DERIVED_IDENTITY_FIXED_WIDTH",
        "OBJECT_REFERENCE",
        "SAFE_RELAXATION",
        "SCOPE_ROOT",
    }:
        transition = one
    elif kind == "EXACT_BOOLEAN":
        transition = _add(one, _is_null("boolean_literal"))
    elif kind == "SAFE_INTEGER_BAND":
        transition = _list_count("ordered_probe_values")
    elif kind == "TEXT_FINITE":
        transition = _list_count("ordered_literals")
    elif kind == "NULLABLE_BRANCH":
        transition = _const(3)
    elif kind == "ASSOCIATIVE_HOMOGENEOUS_RUN_BATCH":
        transition = _add(one, _nonzero("maximum_items"))
    elif kind == "ARRAY_STREAM_FOLD":
        transition = _add(one, _parameter("maximum_items"))
    elif kind == "RECORD_MEMBER_FOLD":
        transition = _add(one, _parameter("record_member_count"))
    elif kind == "TAGGED_UNION_BRANCH":
        transition = _add(one, _list_count("ordered_alternative_records"))
    elif kind == "CODEC_INTERSECTION":
        transition = _add(one, _list_count("ordered_codec_coordinate_records"))
    elif kind == "APPLICATION_SCHEDULE_COUNT":
        transition = _add(one, _list_count("ordered_application_invocation_records"))
    elif kind == "LOCAL_SHUTDOWN_ANALYTIC_LENGTH_SWEEP":
        transition = _const(11)
    else:  # pragma: no cover - the exact kernel-set assertion prevents this
        raise AssertionError(f"unhandled kernel {kind}")

    logical_base = transition
    if kind in {
        "ASSOCIATIVE_HOMOGENEOUS_RUN_BATCH",
        "ARRAY_STREAM_FOLD",
    }:
        logical_base = _add(one, _parameter("maximum_items"))
    batch = (
        _nonzero("maximum_items")
        if kind == "ASSOCIATIVE_HOMOGENEOUS_RUN_BATCH"
        else _const(0)
    )
    return {
        "program_version": METER_VERSION,
        "transition_attempt_count_expression": transition,
        "logical_unbatched_transition_equivalent_count_expression": _multiply(
            logical_base, _multiplicity()
        ),
        "batch_application_count_expression": batch,
    }


def _assert_parameter_value(
    value: Any, value_type: str, nullable: bool, null_semantics: str | None
) -> None:
    if value is None:
        assert nullable
        assert null_semantics is not None or value_type.startswith("OPTIONAL_")
        return
    if value_type == "BOOLEAN":
        assert type(value) is bool
    elif value_type in {
        "NONNEGATIVE_SAFE_INTEGER",
        "OPTIONAL_NONNEGATIVE_SAFE_INTEGER",
    }:
        assert type(value) is int
        assert 0 <= value <= SAFE_INTEGER_MAXIMUM
    elif value_type == "SIGNED_SAFE_INTEGER":
        assert type(value) is int
        assert -SAFE_INTEGER_MAXIMUM <= value <= SAFE_INTEGER_MAXIMUM
    elif value_type in {"TEXT", "OPTIONAL_TEXT"}:
        assert type(value) is str
    elif value_type in {"ORDERED_JSON_ARRAY", "TYPED_PATH"}:
        assert type(value) is list
    elif value_type == "JSON_VALUE":
        assert value is not None
    else:  # pragma: no cover - checked against the closed enum first
        raise AssertionError(f"unknown parameter value type {value_type}")


def _evaluate_u128(
    expression: Any,
    *,
    parameters: dict[str, Any],
    logical_transfer_multiplicity: int,
) -> int:
    assert type(expression) is dict
    opcode = expression.get("opcode")
    member_map = dict(EXPECTED_EXPRESSION_OPCODES)
    assert opcode in member_map
    assert set(expression) == {"opcode", *member_map[opcode]}

    if opcode == "CONST_U128":
        value = expression["value"]
    elif opcode == "STEP_LOGICAL_TRANSFER_MULTIPLICITY":
        value = logical_transfer_multiplicity
    elif opcode == "PARAM_U128":
        name = expression["parameter_name"]
        assert name in parameters
        value = parameters[name]
        assert type(value) is int
    elif opcode == "PARAM_LIST_COUNT":
        name = expression["parameter_name"]
        assert name in parameters and type(parameters[name]) is list
        value = len(parameters[name])
    elif opcode == "INDICATOR_PARAM_NONZERO":
        name = expression["parameter_name"]
        assert name in parameters and type(parameters[name]) is int
        assert parameters[name] >= 0
        value = int(parameters[name] != 0)
    elif opcode == "INDICATOR_PARAM_IS_NULL":
        name = expression["parameter_name"]
        assert name in parameters
        value = int(parameters[name] is None)
    else:
        operands = expression["ordered_operands"]
        assert type(operands) is list and len(operands) >= 2
        values = [
            _evaluate_u128(
                operand,
                parameters=parameters,
                logical_transfer_multiplicity=logical_transfer_multiplicity,
            )
            for operand in operands
        ]
        value = 0 if opcode == "CHECKED_ADD" else 1
        for operand in values:
            value = value + operand if opcode == "CHECKED_ADD" else value * operand
            assert value <= UINT128_MAXIMUM
    assert type(value) is int and 0 <= value <= UINT128_MAXIMUM
    return value


def test_closed_instruction_set_kernel_schemas_and_id_references() -> None:
    catalog = _catalog()
    recurrence = catalog["recurrence_catalog"]
    instruction = recurrence["instruction_set"]
    assert set(instruction) == {
        "instruction_set_version",
        "cell_contract",
        "u128_expression_schema",
        "transfer_program_schema",
        "meter_program_schema",
        "parameter_schema_record_schema",
    }

    expression_schema = instruction["u128_expression_schema"]
    assert expression_schema == {
        "expression_version": EXPRESSION_VERSION,
        "evaluation_order": "DEPTH_FIRST_LEFT_TO_RIGHT_CHECKED_UINT128",
        "unknown_or_extra_member_policy": "REJECT",
        "ordered_opcode_records": [
            {
                "opcode_position": position,
                "opcode": opcode,
                "ordered_required_member_names_after_opcode": list(members),
                "return_type": "U128",
            }
            for position, (opcode, members) in enumerate(EXPECTED_EXPRESSION_OPCODES, 1)
        ],
    }
    transfer_schema = instruction["transfer_program_schema"]
    assert set(transfer_schema) == {
        "ordered_member_names",
        "unknown_or_extra_member_policy",
        "ordered_transfer_opcode_records",
    }
    assert transfer_schema["ordered_member_names"] == ["program_version", "opcode"]
    assert transfer_schema["unknown_or_extra_member_policy"] == "REJECT"
    transfer_rows = transfer_schema["ordered_transfer_opcode_records"]
    assert [row["opcode_position"] for row in transfer_rows] == list(range(1, 19))
    assert [row["opcode"] for row in transfer_rows] == [
        opcode for opcode, _operation in EXPECTED_TRANSFER_OPCODES
    ]
    for row in transfer_rows:
        assert set(row) == {
            "opcode_position",
            "opcode",
            "semantic_rule",
            "ordered_required_parameter_names",
            "child_read_mode",
            "state_rule",
            "transfer_rule_id",
            "unknown_or_extra_member_policy",
        }
        assert type(row["semantic_rule"]) is str and row["semantic_rule"]
        assert type(row["ordered_required_parameter_names"]) is list
        assert len(set(row["ordered_required_parameter_names"])) == len(
            row["ordered_required_parameter_names"]
        )
        assert type(row["child_read_mode"]) is str and row["child_read_mode"]
        assert type(row["state_rule"]) is str and row["state_rule"]
        assert len(row["transfer_rule_id"]) == 64
        int(row["transfer_rule_id"], 16)
        assert row["unknown_or_extra_member_policy"] == "REJECT"
    assert instruction["meter_program_schema"] == {
        "ordered_member_names": [
            "program_version",
            "transition_attempt_count_expression",
            "logical_unbatched_transition_equivalent_count_expression",
            "batch_application_count_expression",
        ],
        "all_expressions_return": "U128",
        "event_expansion_order": [
            "LOGICAL_DESCRIPTOR_VISIT",
            "CACHE_INSERT",
            "TRANSITION_ATTEMPT",
            "BATCH_APPLICATION",
            "INTRINSIC_RULE_EVALUATION",
            "RESULT_CELL_EMIT",
            "STEP_COMMITMENT_EMIT",
            "RETENTION_OBSERVATION",
        ],
        "unknown_or_extra_member_policy": "REJECT",
    }
    parameter_schema = instruction["parameter_schema_record_schema"]
    assert parameter_schema == {
        "ordered_member_names": [
            "parameter_position",
            "parameter_name",
            "value_type",
            "nullable",
            "null_semantics",
            "authority_validation",
        ],
        "value_type_enum": [
            "BOOLEAN",
            "NONNEGATIVE_SAFE_INTEGER",
            "SIGNED_SAFE_INTEGER",
            "OPTIONAL_NONNEGATIVE_SAFE_INTEGER",
            "TEXT",
            "OPTIONAL_TEXT",
            "JSON_VALUE",
            "ORDERED_JSON_ARRAY",
            "TYPED_PATH",
        ],
    }

    signatures = recurrence["ordered_state_signature_records"]
    assert [row["signature_position"] for row in signatures] == list(
        range(1, len(signatures) + 1)
    )
    signature_ids: set[str] = set()
    for signature in signatures:
        components = signature["ordered_component_records"]
        assert [row["component_position"] for row in components] == list(
            range(1, len(components) + 1)
        )
        payload = {
            "signature_version": signature["signature_version"],
            "ordered_component_records": components,
        }
        assert signature["state_signature_id"] == _semantic_id(
            catalog, "STATE_SIGNATURE", payload
        )
        signature_ids.add(signature["state_signature_id"])
    assert len(signature_ids) == len(signatures)

    kernels = recurrence["ordered_derivation_kernel_records"]
    assert [row["kernel_position"] for row in kernels] == list(range(1, 19))
    assert {row["derivation_kind"] for row in kernels} == set(EXPECTED_KERNELS)
    assert len({row["kernel_record_sha256"] for row in kernels}) == len(kernels)
    for kernel in kernels:
        kind = kernel["derivation_kind"]
        variant, expected_parameters, transfer_opcode = EXPECTED_KERNELS[kind]
        assert kernel["parameter_variant"] == variant
        assert kernel["ordered_parameter_member_names"] == [
            row[0] for row in expected_parameters
        ]
        expected_schema_records = [
            {
                "parameter_position": position,
                "parameter_name": name,
                "value_type": value_type,
                "nullable": nullable,
                "null_semantics": null_semantics,
                "authority_validation": (
                    "RECOMPUTE_FROM_PINNED_LOCATOR_OR_EXACT_CHILD_REFERENCE"
                ),
            }
            for position, (name, value_type, nullable, null_semantics) in enumerate(
                expected_parameters, 1
            )
        ]
        assert kernel["ordered_parameter_schema_records"] == expected_schema_records
        assert kernel["state_signature_id"] in signature_ids
        assert kernel["transfer_program"] == {
            "program_version": TRANSFER_VERSION,
            "opcode": transfer_opcode,
        }
        assert kernel["meter_program"] == _expected_meter(kind)
        raw_record = dict(kernel)
        kernel_sha = raw_record.pop("kernel_record_sha256")
        assert kernel_sha == _sha256(raw_record)

    batch = recurrence["homogeneous_run_batch_equivalence"]
    assert batch["state_signature_id"] in signature_ids
    assert batch["state_signature_id"] == next(
        row["state_signature_id"]
        for row in signatures
        if [
            component["component_kind"]
            for component in row["ordered_component_records"]
        ]
        == ["ITEM_COUNT", "CAPPED_ITEM_UPPER_OCTET_SUM", "COMMA_COUNT"]
    )


def test_parameter_closure_types_authority_binding_and_boolean_sentinel() -> None:
    catalog = _catalog()
    registry = _registry()
    kernels = {
        row["derivation_kind"]: row
        for row in catalog["recurrence_catalog"]["ordered_derivation_kernel_records"]
    }
    schemas = {row["value_schema_id"]: row for row in registry["value_schema_catalog"]}
    template_steps = [
        (template, step)
        for template in catalog["logical_plan_recipe_catalog"][
            "ordered_logical_plan_templates"
        ]
        for step in template["ordered_template_steps"]
    ]
    assert len(template_steps) == 1_647
    boolean_sentinel_count = 0
    boolean_literal_count = 0
    owner_coordinate_sentinel_steps: list[
        tuple[int, str, str | None, str, str | None]
    ] = []
    for template, step in template_steps:
        kernel = kernels[step["derivation_kind"]]
        parameters = step["recurrence_parameters"]
        assert set(parameters) == set(kernel["ordered_parameter_member_names"])
        assert [
            row["parameter_name"] for row in kernel["ordered_parameter_schema_records"]
        ] == kernel["ordered_parameter_member_names"]
        for parameter_schema in kernel["ordered_parameter_schema_records"]:
            name = parameter_schema["parameter_name"]
            _assert_parameter_value(
                parameters[name],
                parameter_schema["value_type"],
                parameter_schema["nullable"],
                parameter_schema["null_semantics"],
            )

        if step["derivation_kind"] == "EXACT_BOOLEAN":
            authority = schemas[step["value_schema_id"]]
            assert authority["schema_kind"] == "EXACT_BOOLEAN"
            assert parameters["boolean_literal"] == authority["boolean_literal"]
            if parameters["boolean_literal"] is None:
                boolean_sentinel_count += 1
            else:
                boolean_literal_count += 1
        if (
            step["derivation_kind"] == "TAGGED_UNION_BRANCH"
            and parameters["owner_type_name"] is None
        ):
            assert parameters["owner_typed_member_path"] == []
            assert step["type_name"] == "CapacityMeasurementTargetValue"
            owner_coordinate_sentinel_steps.append(
                (
                    template["template_position"],
                    template["root_type_name"],
                    template["root_alternative_name"],
                    step["type_name"],
                    step["alternative_name"],
                )
            )
    assert boolean_sentinel_count > 0
    assert boolean_literal_count > 0
    assert owner_coordinate_sentinel_steps == [
        (
            39,
            "CapacityMeasurementTargetValue",
            "BOOL",
            "CapacityMeasurementTargetValue",
            "BOOL",
        ),
        (
            40,
            "CapacityMeasurementTargetValue",
            "DURATION_BOUND",
            "CapacityMeasurementTargetValue",
            "DURATION_BOUND",
        ),
        (
            41,
            "CapacityMeasurementTargetValue",
            "FIXED_UINT_MAP",
            "CapacityMeasurementTargetValue",
            "FIXED_UINT_MAP",
        ),
        (
            42,
            "CapacityMeasurementTargetValue",
            "OPTIONAL_TEXT",
            "CapacityMeasurementTargetValue",
            "OPTIONAL_TEXT",
        ),
        (
            43,
            "CapacityMeasurementTargetValue",
            "OPTIONAL_UINT",
            "CapacityMeasurementTargetValue",
            "OPTIONAL_UINT",
        ),
        (
            44,
            "CapacityMeasurementTargetValue",
            "TEXT",
            "CapacityMeasurementTargetValue",
            "TEXT",
        ),
        (
            45,
            "CapacityMeasurementTargetValue",
            "TEXT_LIST",
            "CapacityMeasurementTargetValue",
            "TEXT_LIST",
        ),
        (
            46,
            "CapacityMeasurementTargetValue",
            "UINT",
            "CapacityMeasurementTargetValue",
            "UINT",
        ),
        (
            47,
            "CapacityMeasurementTargetValue",
            "UINT_LIST",
            "CapacityMeasurementTargetValue",
            "UINT_LIST",
        ),
        (61, "TargetFieldObservationV1", None, "CapacityMeasurementTargetValue", None),
        (66, "TargetObservationV2", None, "CapacityMeasurementTargetValue", None),
    ]

    boolean_meter = kernels["EXACT_BOOLEAN"]["meter_program"]
    transition_expression = boolean_meter["transition_attempt_count_expression"]
    for value, expected in ((None, 2), (False, 1), (True, 1)):
        assert (
            _evaluate_u128(
                transition_expression,
                parameters={"boolean_literal": value},
                logical_transfer_multiplicity=1,
            )
            == expected
        )


def test_all_1647_meter_asts_recompute_physical_logical_and_batch_counts() -> None:
    catalog = _catalog()
    kernels = {
        row["derivation_kind"]: row
        for row in catalog["recurrence_catalog"]["ordered_derivation_kernel_records"]
    }
    templates = catalog["logical_plan_recipe_catalog"]["ordered_logical_plan_templates"]
    validated = 0
    for template in templates:
        steps = template["ordered_template_steps"]
        for step in steps:
            validated += 1
            kind = step["derivation_kind"]
            kernel = kernels[kind]
            parameters = step["recurrence_parameters"]
            multiplicity = step["logical_transfer_multiplicity"]
            assert type(multiplicity) is int
            assert 0 <= multiplicity <= SAFE_INTEGER_MAXIMUM
            meter = kernel["meter_program"]
            physical = _evaluate_u128(
                meter["transition_attempt_count_expression"],
                parameters=parameters,
                logical_transfer_multiplicity=multiplicity,
            )
            logical = _evaluate_u128(
                meter["logical_unbatched_transition_equivalent_count_expression"],
                parameters=parameters,
                logical_transfer_multiplicity=multiplicity,
            )
            batch = _evaluate_u128(
                meter["batch_application_count_expression"],
                parameters=parameters,
                logical_transfer_multiplicity=multiplicity,
            )
            assert step["physical_transition_count"] == physical
            assert step["logical_unbatched_transition_equivalent_count"] == logical
            assert step["physical_batch_application_count"] == batch
            assert step["kernel_record_sha256"] == kernel["kernel_record_sha256"]
            assert step["state_signature_id"] == kernel["state_signature_id"]
            assert all(
                type(child) is int and 1 <= child < step["template_step_position"]
                for child in step["ordered_child_step_positions"]
            )
    assert validated == 1_647


def test_array_observer_closures_are_identified_and_batch_eligible() -> None:
    catalog = _catalog()
    registry = _registry()
    recurrence = catalog["recurrence_catalog"]
    templates = catalog["logical_plan_recipe_catalog"]["ordered_logical_plan_templates"]
    schemas = {row["value_schema_id"]: row for row in registry["value_schema_catalog"]}
    relaxations = {
        row["relaxation_name"]: row["safe_relaxation_rule_id"]
        for row in recurrence["ordered_safe_relaxation_records"]
    }
    batch_equivalence = recurrence["homogeneous_run_batch_equivalence"]
    expected_observers = [
        {
            "observer_position": 1,
            "observer_kind": "ORDINAL_ORDER_UNIQUENESS",
            "status": "DROPPED_COMPLETE_PREDICATE",
            "safe_relaxation_rule_id": relaxations[
                "DROP_ARRAY_ORDER_AND_UNIQUENESS_TO_SEQUENCE_SUPERSET_V1"
            ],
            "surviving_summary_component": None,
        },
        {
            "observer_position": 2,
            "observer_kind": "INTRINSIC_CROSS_APPLICATION_RULE",
            "status": "DROPPED_COMPLETE_PREDICATE",
            "safe_relaxation_rule_id": relaxations[
                "DROP_COMPLETE_NAMED_CONSTRAINT_TO_SUPERSET_V1"
            ],
            "surviving_summary_component": None,
        },
        {
            "observer_position": 3,
            "observer_kind": "PAYLOAD_DERIVED_IDENTITY_RELATION",
            "status": "DROPPED_EQUALITY_RETAIN_FIXED_WIDTH",
            "safe_relaxation_rule_id": relaxations[
                "DERIVED_IDENTITY_FIXED_WIDTH_PAYLOAD_SUPERSET_V1"
            ],
            "surviving_summary_component": None,
        },
        {
            "observer_position": 4,
            "observer_kind": "CARDINALITY_AND_CANONICAL_BOUNDARY",
            "status": "RETAINED_IN_BATCH_STATE",
            "safe_relaxation_rule_id": None,
            "surviving_summary_component": (
                "ITEM_COUNT,CAPPED_ITEM_UPPER_OCTET_SUM,COMMA_COUNT"
            ),
        },
        {
            "observer_position": 5,
            "observer_kind": "ANCESTOR_CODEC_LENGTH",
            "status": "RETAINED_BY_EFFECTIVE_CEILING_INTERSECTION",
            "safe_relaxation_rule_id": None,
            "surviving_summary_component": ("CAPPED_ITEM_UPPER_OCTET_SUM,COMMA_COUNT"),
        },
    ]
    closure_payload_by_id: dict[str, bytes] = {}
    batch_steps = 0
    for template in templates:
        relaxation_applications = template["ordered_relaxation_application_records"]
        for step in template["ordered_template_steps"]:
            if step["derivation_kind"] != "ASSOCIATIVE_HOMOGENEOUS_RUN_BATCH":
                assert step["batch_equivalence_id"] is None
                continue
            batch_steps += 1
            parameters = step["recurrence_parameters"]
            schema = schemas[step["value_schema_id"]]
            assert schema["schema_kind"] == "ARRAY"
            assert parameters["minimum_items"] == schema["array_minimum_items"]
            assert parameters["maximum_items"] == schema["array_maximum_items"]
            assert (
                parameters["item_value_schema_id"]
                == schema["array_item_value_schema_id"]
            )
            assert (
                parameters["item_step_position"] in step["ordered_child_step_positions"]
            )
            assert parameters["maximum_items"] > 0
            closure = parameters["observer_closure_record"]
            payload = {
                key: closure[key]
                for key in _identity(catalog, "ARRAY_OBSERVER_CLOSURE")[
                    "ordered_payload_member_names"
                ]
            }
            closure_id = closure["array_observer_closure_id"]
            assert set(closure) == {*payload, "array_observer_closure_id"}
            assert closure_id == _semantic_id(
                catalog, "ARRAY_OBSERVER_CLOSURE", payload
            )
            raw_payload = _canonical_bytes(payload)
            assert (
                closure_payload_by_id.setdefault(closure_id, raw_payload) == raw_payload
            )
            assert closure == {
                "closure_version": (
                    "riskyieldmm.raw_v8_step2_external_schema_v2."
                    "array_observer_closure.v1"
                ),
                "array_value_schema_id": step["value_schema_id"],
                "array_typed_path": step["subject_locator"]["typed_path"],
                "ordered_observer_records": expected_observers,
                "surviving_state_signature_id": batch_equivalence["state_signature_id"],
                "batch_eligible": True,
                "proof_rule": (
                    "NO_SURVIVING_ORDINAL_DISTINGUISHER_AND_ASSOCIATIVE_"
                    "COMPLETE_SUMMARY_STATE"
                ),
                "array_observer_closure_id": closure_id,
            }
            assert (
                step["batch_equivalence_id"]
                == batch_equivalence["batch_equivalence_id"]
            )
            run_records = parameters["ordered_run_records"]
            assert run_records == [
                {
                    "run_position": 1,
                    "first_array_ordinal": 0,
                    "item_count": parameters["maximum_items"],
                    "item_step_position": parameters["item_step_position"],
                    "array_observer_closure_id": closure_id,
                }
            ]
            matching_applications = [
                row
                for row in relaxation_applications
                if row["logical_derivation_step_position"]
                == step["template_step_position"]
                and row["predicate_kind"] == "ARRAY_ORDER_AND_UNIQUENESS"
            ]
            assert len(matching_applications) == 1
            assert matching_applications[0]["supporting_closure_id"] == closure_id
            assert (
                matching_applications[0]["authority_predicate_id"]
                == step["value_schema_id"]
            )
    assert batch_steps == 91
    assert not any(
        step["derivation_kind"] == "ARRAY_STREAM_FOLD"
        for template in templates
        for step in template["ordered_template_steps"]
    )


def _schema_graph(
    registry: dict[str, Any],
) -> dict[tuple[str, str], tuple[tuple[str, str], ...]]:
    schemas = registry["value_schema_catalog"]
    descriptors = registry["ordered_external_type_descriptors"]
    schema_ids = [row["value_schema_id"] for row in schemas]
    type_names = [row["type_name"] for row in descriptors]
    assert len(schema_ids) == len(set(schema_ids)) == 236
    assert len(type_names) == len(set(type_names)) == 52
    assert registry["schema_graph_node_count"] == 52
    assert registry["ordered_schema_graph_node_names"] == type_names
    schema_by_id = dict(zip(schema_ids, schemas, strict=True))
    descriptor_by_name = dict(zip(type_names, descriptors, strict=True))
    graph: dict[tuple[str, str], tuple[tuple[str, str], ...]] = {}
    for schema_id, schema in schema_by_id.items():
        edges: list[tuple[str, str]] = []
        if schema["schema_kind"] == "OBJECT_REF":
            assert schema["referenced_type_name"] in descriptor_by_name
            edges.append(("TYPE", schema["referenced_type_name"]))
        elif schema["schema_kind"] == "ARRAY":
            assert schema["array_item_value_schema_id"] in schema_by_id
            edges.append(("VALUE_SCHEMA", schema["array_item_value_schema_id"]))
        graph[("VALUE_SCHEMA", schema_id)] = tuple(edges)
    for type_name, descriptor in descriptor_by_name.items():
        edges = []
        if descriptor["type_form"] == "RECORD":
            members = descriptor["record_member_descriptors"]
            assert [row["member_position"] for row in members] == list(
                range(1, len(members) + 1)
            )
            assert len({row["member_name"] for row in members}) == len(members)
            for member in members:
                assert member["value_schema_id"] in schema_by_id
                edges.append(("VALUE_SCHEMA", member["value_schema_id"]))
        else:
            assert descriptor["type_form"] == "TAGGED_UNION"
            alternatives = descriptor["tagged_union_descriptor"]["ordered_alternatives"]
            assert [row["alternative_position"] for row in alternatives] == list(
                range(1, len(alternatives) + 1)
            )
            assert len({row["alternative_name"] for row in alternatives}) == len(
                alternatives
            )
            for alternative in alternatives:
                assert alternative["referenced_type_name"] in descriptor_by_name
                edges.append(("TYPE", alternative["referenced_type_name"]))
        graph[("TYPE", type_name)] = tuple(edges)
    return graph


def test_schema_graph_ids_references_acyclicity_and_exact_maximum_depth() -> None:
    registry = _registry()
    graph = _schema_graph(registry)
    assert len(graph) == 288
    assert all(child in graph for children in graph.values() for child in children)

    visiting: set[tuple[str, str]] = set()
    depths: dict[tuple[str, str], int] = {}

    def maximum_descendant_edge_depth(node: tuple[str, str]) -> int:
        if node in depths:
            return depths[node]
        assert node not in visiting, f"cycle at {node}"
        visiting.add(node)
        result = max(
            (maximum_descendant_edge_depth(child) + 1 for child in graph[node]),
            default=0,
        )
        visiting.remove(node)
        depths[node] = result
        return result

    assert max(maximum_descendant_edge_depth(node) for node in graph) == 12
    assert len(depths) == 288

    # Every template locator must point back to its exact graph authority row.
    catalog = _catalog()
    schemas = registry["value_schema_catalog"]
    descriptors = registry["ordered_external_type_descriptors"]
    for template in catalog["logical_plan_recipe_catalog"][
        "ordered_logical_plan_templates"
    ]:
        for step in template["ordered_template_steps"]:
            locator = step["subject_locator"]
            position = locator["registry_position"]
            assert type(position) is int and position > 0
            if locator["registry_object_kind"] == "VALUE_SCHEMA":
                authority = schemas[position - 1]
                assert step["value_schema_id"] == authority["value_schema_id"]
                assert locator["canonical_json_pointer"] == (
                    f"/external_schema_registry_v2/value_schema_catalog/{position - 1}"
                )
            else:
                assert locator["registry_object_kind"] == "TYPE_DESCRIPTOR"
                authority = descriptors[position - 1]
                assert step["type_name"] == authority["type_name"]
                assert locator["canonical_json_pointer"] == (
                    "/external_schema_registry_v2/ordered_external_type_descriptors/"
                    f"{position - 1}"
                )


def _safe_integer_probes(minimum: int, maximum: int) -> list[int]:
    assert type(minimum) is int and type(maximum) is int
    assert 0 <= minimum <= maximum <= SAFE_INTEGER_MAXIMUM
    values = {minimum, maximum}
    for exponent in range(1, 17):
        for value in (10**exponent - 1, 10**exponent):
            if minimum <= value <= maximum:
                values.add(value)
    return sorted(values)


def _minimum_schema_octets(
    schema_id: str,
    *,
    schemas: dict[str, dict[str, Any]],
    descriptors: dict[str, dict[str, Any]],
    languages: dict[str, dict[str, Any]],
    schema_cache: dict[str, int],
    type_cache: dict[tuple[str, str | None], int],
) -> int:
    if schema_id in schema_cache:
        return schema_cache[schema_id]
    schema = schemas[schema_id]
    kind = schema["schema_kind"]
    if kind == "EXACT_BOOLEAN":
        literal = schema["boolean_literal"]
        candidates = (False, True) if literal is None else (literal,)
        minimum = min(len(_canonical_bytes(value)) for value in candidates)
    elif kind == "SAFE_INTEGER":
        minimum = min(
            len(_canonical_bytes(value))
            for value in _safe_integer_probes(
                schema["integer_minimum"], schema["integer_maximum"]
            )
        )
    elif kind == "TEXT":
        language = languages[schema["text_language_id"]]
        if language["language_kind"] in {"LITERAL", "ENUM"}:
            minimum = min(
                len(_canonical_bytes(value)) for value in language["ordered_literals"]
            )
        elif language["built_in_language_kind"] == "LOWERCASE_SHA256":
            minimum = 66
        else:
            minimum = 2
    elif kind == "OBJECT_REF":
        minimum = _minimum_type_octets(
            schema["referenced_type_name"],
            alternative_name=None,
            schemas=schemas,
            descriptors=descriptors,
            languages=languages,
            schema_cache=schema_cache,
            type_cache=type_cache,
        )
    else:
        assert kind == "ARRAY"
        item_minimum = _minimum_schema_octets(
            schema["array_item_value_schema_id"],
            schemas=schemas,
            descriptors=descriptors,
            languages=languages,
            schema_cache=schema_cache,
            type_cache=type_cache,
        )
        count = schema["array_minimum_items"]
        minimum = 2 + count * item_minimum + max(count - 1, 0)
    if schema["nullable"]:
        minimum = min(4, minimum)
    schema_cache[schema_id] = minimum
    return minimum


def _minimum_type_octets(
    type_name: str,
    *,
    alternative_name: str | None,
    schemas: dict[str, dict[str, Any]],
    descriptors: dict[str, dict[str, Any]],
    languages: dict[str, dict[str, Any]],
    schema_cache: dict[str, int],
    type_cache: dict[tuple[str, str | None], int],
) -> int:
    key = (type_name, alternative_name)
    if key in type_cache:
        return type_cache[key]
    descriptor = descriptors[type_name]
    if descriptor["type_form"] == "RECORD":
        members = descriptor["record_member_descriptors"]
        minimum = (
            2
            + max(len(members) - 1, 0)
            + sum(len(_canonical_bytes(row["member_name"])) + 1 for row in members)
            + sum(
                _minimum_schema_octets(
                    row["value_schema_id"],
                    schemas=schemas,
                    descriptors=descriptors,
                    languages=languages,
                    schema_cache=schema_cache,
                    type_cache=type_cache,
                )
                for row in members
            )
        )
    else:
        alternatives = descriptor["tagged_union_descriptor"]["ordered_alternatives"]
        selected = [
            row
            for row in alternatives
            if alternative_name is None or row["alternative_name"] == alternative_name
        ]
        assert selected
        minimum = min(
            _minimum_type_octets(
                row["referenced_type_name"],
                alternative_name=None,
                schemas=schemas,
                descriptors=descriptors,
                languages=languages,
                schema_cache=schema_cache,
                type_cache=type_cache,
            )
            for row in selected
        )
    type_cache[key] = minimum
    return minimum


def test_owner_codec_residual_coordinates_for_templates_22_to_25_and_28_to_31() -> None:
    catalog = _catalog()
    registry = _registry()
    templates = {
        row["template_position"]: row
        for row in catalog["logical_plan_recipe_catalog"][
            "ordered_logical_plan_templates"
        ]
    }
    schemas = {row["value_schema_id"]: row for row in registry["value_schema_catalog"]}
    descriptors = {
        row["type_name"]: row for row in registry["ordered_external_type_descriptors"]
    }
    languages = {
        row["text_language_id"]: row for row in registry["text_language_catalog"]
    }
    expected = {
        22: (
            "ACK_DEADLINE_EXPIRY_RESULT_EVIDENCE_V1",
            "result",
            "LT",
            524_288,
            559,
            523_728,
        ),
        23: ("INGRESS_RESULT_EVIDENCE_V2", "result", "LT", 524_288, 535, 523_752),
        24: (
            "LOCAL_SHUTDOWN_RESULT_EVIDENCE_V2",
            "result",
            "LT",
            524_288,
            549,
            523_738,
        ),
        25: (
            "SUBSCRIPTION_DISPATCH_RESULT_EVIDENCE_V2",
            "result",
            "LT",
            524_288,
            563,
            523_724,
        ),
        28: ("ACK_DEADLINE_EXPIRY_SPEC_V1", "spec", "LE", 2_097_152, 371, 2_096_781),
        29: ("INGRESS_OPERATION_SPEC_V2", "spec", "LE", 2_097_152, 357, 2_096_795),
        30: ("LOCAL_SHUTDOWN_SPEC_V2", "spec", "LE", 2_097_152, 361, 2_096_791),
        31: ("SUBSCRIPTION_DISPATCH_SPEC_V2", "spec", "LE", 2_097_152, 375, 2_096_777),
    }
    schema_cache: dict[str, int] = {}
    type_cache: dict[tuple[str, str | None], int] = {}
    for position, (
        alternative_name,
        payload_member,
        relation,
        limit,
        expected_sibling,
        expected_residual,
    ) in expected.items():
        template = templates[position]
        assert template["root_alternative_name"] == alternative_name
        coordinate_matches = [
            coordinate
            for step in template["ordered_template_steps"]
            if step["derivation_kind"] == "CODEC_INTERSECTION"
            and step["type_name"] == template["root_type_name"]
            and step["alternative_name"] == alternative_name
            for coordinate in step["recurrence_parameters"][
                "ordered_codec_coordinate_records"
            ]
            if coordinate["coordinate_scope"] == "OWNER_PAYLOAD_RESIDUAL"
        ]
        assert len(coordinate_matches) == 1
        coordinate = coordinate_matches[0]
        union = descriptors[template["root_type_name"]]["tagged_union_descriptor"]
        owner = descriptors[union["payload_owner_type_name"]]
        selected = next(
            row
            for row in union["ordered_alternatives"]
            if row["alternative_name"] == alternative_name
        )
        discriminators = {
            row["member_name"]: row["text_value"]
            for row in selected["ordered_discriminator_literals"]
        }
        members = owner["record_member_descriptors"]
        syntax = (
            2
            + max(len(members) - 1, 0)
            + sum(len(_canonical_bytes(row["member_name"])) + 1 for row in members)
        )
        sibling = syntax + sum(
            len(_canonical_bytes(discriminators[row["member_name"]]))
            if row["member_name"] in discriminators
            else _minimum_schema_octets(
                row["value_schema_id"],
                schemas=schemas,
                descriptors=descriptors,
                languages=languages,
                schema_cache=schema_cache,
                type_cache=type_cache,
            )
            for row in members
            if row["member_name"] != payload_member
        )
        ceiling = owner["codec_octet_limit"] - int(
            owner["codec_byte_bound_relation"] == "LT"
        )
        residual = ceiling - sibling
        assert (sibling, residual) == (expected_sibling, expected_residual)
        assert coordinate == {
            "coordinate_position": 2,
            "coordinate_scope": "OWNER_PAYLOAD_RESIDUAL",
            "codec_owner_type_name": owner["type_name"],
            "codec_owner_typed_member_path": [payload_member],
            "codec_byte_bound_relation": relation,
            "codec_octet_limit": limit,
            "minimum_sibling_and_syntax_octets": sibling,
            "derived_payload_octet_ceiling": residual,
            "selected_union_alternative_name": alternative_name,
        }


def _schedule_record(
    *,
    position: int,
    application: dict[str, Any],
    invocations: int,
    evaluations: int,
    scope: str,
) -> dict[str, Any]:
    return {
        "schedule_position": position,
        "application_name": application["application_name"],
        "rule_application_id": application["rule_application_id"],
        "rule_id": application["rule_id"],
        "schedule_scope": scope,
        "application_invocation_count": invocations,
        "cross_rule_evaluation_count": evaluations,
    }


def _expected_profile_scope(
    profile: dict[str, Any], applications: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    if profile["profile_kind"] == "OUTER_RESULT_BOUNDARY_FIXTURE":
        application = applications["APPLY/OPERATION_RESULT_SIGNED_SPEC_V1"]
        return {
            "internal_scope_case_count": 1,
            "synthetic_axis_count": 0,
            "constructed_context_occurrence_count": 0,
            "context_record_reference_count": 2,
            "observation_count": 0,
            "application_invocation_count": 1,
            "cross_rule_evaluation_count": 1,
            "direct_cross_expression_node_count": 3,
            "ordered_root_family_schedule_records": [],
            "ordered_application_schedule_records": [
                _schedule_record(
                    position=1,
                    application=application,
                    invocations=1,
                    evaluations=1,
                    scope="ONE_OUTER_RESULT_FIXTURE",
                )
            ],
        }

    total = {
        "internal_scope_case_count": 0,
        "synthetic_axis_count": int(
            len(profile["ordered_admissible_root_families"]) >= 2
        ),
        "constructed_context_occurrence_count": 0,
        "context_record_reference_count": 0,
        "observation_count": 0,
        "application_invocation_count": 0,
        "cross_rule_evaluation_count": 0,
        "direct_cross_expression_node_count": 0,
    }
    names = (
        "APPLY/SELECTOR_MARKER_CONTRACT_V1",
        "APPLY/V2_OBSERVATION_AGGREGATE_REGISTRY_V1",
        "APPLY/V2_OBSERVATION_FIELDS_REGISTRY_V1",
        "APPLY/V2_ROOT_OBSERVATION_MEMBERSHIP_V1",
        "APPLY/V2_ROOT_SELECTOR_LIFECYCLE_V1",
    )
    application_totals = {name: [0, 0] for name in names}
    family_schedules = []
    for family_position, family in enumerate(
        profile["ordered_admissible_root_families"], 1
    ):
        pair_count = len(family["ordered_instrumentation_mode_attempt_presence_pairs"])
        role_count = len(family["ordered_measured_observation_roles"])
        cases = pair_count * role_count
        observations = family["observation_count"]
        selector = int(family["selector_present"])
        total["synthetic_axis_count"] += int(pair_count >= 2)
        total["synthetic_axis_count"] += pair_count * int(role_count >= 2)
        total["internal_scope_case_count"] += cases
        total["constructed_context_occurrence_count"] += cases * observations
        total["context_record_reference_count"] += cases * (observations + 3 + selector)
        total["observation_count"] += cases * observations
        total["application_invocation_count"] += cases * (
            2 * observations + 2 + selector
        )
        total["cross_rule_evaluation_count"] += cases * (
            187 * observations + 1 + selector
        )
        total["direct_cross_expression_node_count"] += cases * (
            1_872 * observations + 4 + 3 * selector
        )
        per_case = (
            ("APPLY/SELECTOR_MARKER_CONTRACT_V1", selector, selector),
            ("APPLY/V2_OBSERVATION_AGGREGATE_REGISTRY_V1", observations, observations),
            (
                "APPLY/V2_OBSERVATION_FIELDS_REGISTRY_V1",
                observations,
                185 * observations,
            ),
            ("APPLY/V2_ROOT_OBSERVATION_MEMBERSHIP_V1", 1, observations),
            ("APPLY/V2_ROOT_SELECTOR_LIFECYCLE_V1", 1, 1),
        )
        for name, invocations, evaluations in per_case:
            application_totals[name][0] += cases * invocations
            application_totals[name][1] += cases * evaluations
        active_per_case = [row for row in per_case if row[1] > 0]
        family_schedules.append(
            {
                "root_family_position": family_position,
                "root_family_kind": family["root_family_kind"],
                "selector_catalog_name": family["selector_catalog_name"],
                "selector_catalog_position": family["selector_catalog_position"],
                "selector_present": family["selector_present"],
                "observation_count": observations,
                "attempt_presence_pair_count": pair_count,
                "measured_observation_role_count": role_count,
                "internal_scope_case_count": cases,
                "ordered_application_schedule_records": [
                    _schedule_record(
                        position=position,
                        application=applications[name],
                        invocations=invocations,
                        evaluations=evaluations,
                        scope="PER_INTERNAL_SCOPE_CASE",
                    )
                    for position, (name, invocations, evaluations) in enumerate(
                        active_per_case, 1
                    )
                ],
            }
        )
    total["ordered_root_family_schedule_records"] = family_schedules
    active_application_totals = [
        row for row in application_totals.items() if row[1][0] > 0
    ]
    total["ordered_application_schedule_records"] = [
        _schedule_record(
            position=position,
            application=applications[name],
            invocations=counts[0],
            evaluations=counts[1],
            scope="PROFILE_TOTAL",
        )
        for position, (name, counts) in enumerate(active_application_totals, 1)
    ]
    return total


def test_context_and_application_schedules_are_recomputed_from_408_profiles() -> None:
    catalog = _catalog()
    registry = _registry()
    inventory = _inventory()
    profiles = inventory["operation_contracts"][
        "maximum_constraint_scope_profile_catalog"
    ]
    assert len(profiles) == 408
    applications = {
        row["application_name"]: row
        for row in registry["ordered_rule_application_descriptors"]
    }
    recipe = catalog["logical_plan_recipe_catalog"]
    plans = recipe["ordered_logical_count_plan_records"]
    programs = recipe["ordered_profile_conditioning_program_records"]
    deletion_policy_id = recipe["p2_cross_application_deletion_policy"][
        "p2_cross_application_deletion_policy_id"
    ]
    assert len(plans) == 475
    total_scope_cases = 0
    total_axes = 0
    count_members = (
        "internal_scope_case_count",
        "synthetic_axis_count",
        "constructed_context_occurrence_count",
        "context_record_reference_count",
        "observation_count",
        "application_invocation_count",
        "cross_rule_evaluation_count",
        "direct_cross_expression_node_count",
    )
    for profile, plan, program in zip(profiles, plans[66:474], programs, strict=True):
        assert plan["case_position"] == profile["profile_position"] + 66
        expanded = _expected_profile_scope(profile, applications)
        expected = {
            "scope_summary_version": (
                "riskyieldmm.raw_v8_step2_external_schema_v2.compact_scope_summary.v1"
            ),
            **{name: expanded[name] for name in count_members},
            "schedule_authority_kind": "PROFILE_CONDITIONING_PROGRAM",
            "schedule_authority_id": program["profile_conditioning_program_id"],
            "application_schedule_operation_position": program[
                "application_schedule_operation"
            ]["operation_position"],
            "p2_cross_application_deletion_policy_id": (
                None if profile["profile_position"] == 3 else deletion_policy_id
            ),
        }
        assert plan["scope_summary"] == expected
        total_scope_cases += expected["internal_scope_case_count"]
        total_axes += expected["synthetic_axis_count"]
        schedules = expanded["ordered_application_schedule_records"]
        assert (
            sum(row["application_invocation_count"] for row in schedules)
            == expected["application_invocation_count"]
        )
        assert (
            sum(row["cross_rule_evaluation_count"] for row in schedules)
            == expected["cross_rule_evaluation_count"]
        )
    assert total_scope_cases == 475
    assert total_axes == 33

    # Direct 66 type/alternative cases have no contextual schedule.
    for plan in plans[:66]:
        scope = plan["scope_summary"]
        assert scope["internal_scope_case_count"] == 1
        assert scope["schedule_authority_kind"] == "NONE"
        assert scope["schedule_authority_id"] is None
        assert scope["application_schedule_operation_position"] is None
        assert scope["p2_cross_application_deletion_policy_id"] is None

    # Case 475 is the exact local prospective-result application.
    local = plans[474]["scope_summary"]
    signed = applications["APPLY/OPERATION_RESULT_SIGNED_SPEC_V1"]
    expected_local_schedule = [
        _schedule_record(
            position=1,
            application=signed,
            invocations=1,
            evaluations=1,
            scope="ONE_LOCAL_PROSPECTIVE_RESULT",
        )
    ]
    assert (
        expected_local_schedule[0]["rule_application_id"]
        == signed["rule_application_id"]
    )
    assert local["application_invocation_count"] == 1
    assert local["cross_rule_evaluation_count"] == 1
    assert local["schedule_authority_kind"] == ("LOCAL_SHUTDOWN_ANALYTIC_CATALOG")
    assert (
        local["schedule_authority_id"]
        == catalog["recurrence_catalog"]["local_shutdown_analytic_catalog"][
            "local_shutdown_analytic_catalog_id"
        ]
    )
    assert local["application_schedule_operation_position"] is None
    assert local["p2_cross_application_deletion_policy_id"] is None
    local_plan = plans[474]
    assert local_plan["upper_bound_mode"] == "EXACT_LEGAL_DOMAIN"
    assert local_plan["ordered_safe_relaxation_rule_ids"] == []

#!/usr/bin/env python3
"""Falsify unattainable frozen P2 endpoints in the 66 intrinsic templates.

This checker is deliberately independent of every producer, verifier, typed
runtime, test oracle, and previously generated witness.  It executes the
frozen structural transfer programs twice:

* once with their published ``RELAXED_JSON_STRING`` cells; and
* once with sound canonical-JSON upper bounds restored from the pinned text
  languages referenced by those same template leaves.

The second execution remains an over-approximation of the P1-legal domain: it
does not use intrinsic rules, payload-derived identities, or cross-field
predicates to make any bound smaller.  Consequently, whenever its root upper
is below the published P2 endpoint, no legal witness can satisfy P3 equality.

Case 8 is additionally closed constructively.  The checker derives its exact
928-octet language-aware upper, constructs a legal record of exactly that
length, recomputes the standalone identity, and verifies the intrinsic order
relations without importing the accepted runtime.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sys
from typing import Any

SEED_RELATIVE_PATH = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.json"
)
REGISTRY_RELATIVE_PATH = (
    "scripts/tests/raw_v8_step2_external_schema_v2_structural_registry_v49f.json"
)
CONTRACT_RELATIVE_PATH = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "all_case_campaign_contract_v49f.json"
)

SEED_RAW_OCTETS = 13_419_905
SEED_RAW_SHA256 = "a75a2f352e8513b7ff0043693a0c65ebbf4bc6f06859354789af69e1162b0e4f"
REGISTRY_RAW_OCTETS = 1_469_663
REGISTRY_RAW_SHA256 = "9160297ff316c5931737c92f8b359f0a1e2ec22f0aa996ef3b09cf830dc96bf3"
CONTRACT_RAW_OCTETS = 382_710
CONTRACT_RAW_SHA256 = "3ca4ff4d6e581895b813043e7fdeed24c33cf2c828e362ac81de1725e95a84bb"

SEED_ID = "ac22151fa74702ac1488924f01161eaa38574545e6272a290db6b0bbd288ae5f"
REGISTRY_ID = "5dc95a3e99c5646e912b6a7e9c3970cf2489d560ea890b0a19d38af4c51c2140"
CONTRACT_ID = "9be94bf6b53b612d62ac26bc74133f25c1101a0962987a855e65cdcd06418583"

CASE_COUNT = 475
INTRINSIC_CASE_COUNT = 66
CASE8_POSITION = 8
U128_MAXIMUM = (1 << 128) - 1
ANALYSIS_DOMAIN = (
    "RiskYieldMMRawV8Step2MaximumProtocolV2IntrinsicTemplate"
    "AttainabilityFalsificationV1"
)

ALLOWED_INTRINSIC_OPCODES = {
    "CELL_ARRAY_BATCH_V1",
    "CELL_BOOLEAN_LITERAL_V1",
    "CELL_BOUNDED_TEXT_OCTETS_V1",
    "CELL_CHILD_BOUNDS_ALIAS_V1",
    "CELL_CODEC_INTERSECTION_V1",
    "CELL_FINITE_TEXT_V1",
    "CELL_NULLABLE_V1",
    "CELL_RECORD_V1",
    "CELL_RELAXED_JSON_STRING_V1",
    "CELL_SAFE_INTEGER_INTERVAL_V1",
    "CELL_UNION_V1",
}


class IntrinsicAttainabilityError(RuntimeError):
    """Raised when a pinned authority or closed derivation differs."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise IntrinsicAttainabilityError(message)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _u128(value: Any, label: str) -> int:
    _require(_is_int(value) and 0 <= value <= U128_MAXIMUM, f"{label} is not UInt128")
    return value


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as error:
        raise IntrinsicAttainabilityError(
            f"canonical JSON encoding rejected: {error}"
        ) from error


def _pretty_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _semantic_id(
    canonicalization_version: str,
    schema_version: str,
    domain: str,
    payload: Any,
) -> str:
    return _sha256(
        _canonical_bytes(
            {
                "canonicalization_version": canonicalization_version,
                "domain": domain,
                "payload": payload,
                "schema_version": schema_version,
            }
        )
    )


def _load_pinned(
    root: pathlib.Path,
    relative_path: str,
    expected_octets: int,
    expected_sha256: str,
) -> dict[str, Any]:
    path = root / relative_path
    _require(
        path.is_file() and not path.is_symlink(),
        f"authority path differs: {relative_path}",
    )
    raw = path.read_bytes()
    _require(len(raw) == expected_octets, f"authority size differs: {relative_path}")
    _require(
        _sha256(raw) == expected_sha256, f"authority hash differs: {relative_path}"
    )
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, UnicodeError) as error:
        raise IntrinsicAttainabilityError(
            f"authority JSON differs: {relative_path}: {error}"
        ) from error
    _require(type(value) is dict, f"authority root differs: {relative_path}")
    return value


def _index(
    rows: Any,
    member_name: str,
    expected_count: int | None,
    label: str,
) -> dict[Any, dict[str, Any]]:
    _require(type(rows) is list, f"{label} is not an array")
    if expected_count is not None:
        _require(len(rows) == expected_count, f"{label} count differs")
    result: dict[Any, dict[str, Any]] = {}
    for row in rows:
        _require(type(row) is dict and member_name in row, f"{label} row differs")
        key = row[member_name]
        _require(key not in result, f"{label} key is duplicated")
        result[key] = row
    return result


def _cell(lower: Any, upper: Any, ceiling: int) -> dict[str, int]:
    lower = _u128(lower, "cell lower")
    upper = _u128(upper, "cell upper")
    ceiling = _u128(ceiling, "cell ceiling")
    _require(lower <= upper <= ceiling, "cell interval differs")
    return {"lower": lower, "upper": upper}


def _checked_sum(values: list[int], label: str) -> int:
    total = 0
    for value in values:
        value = _u128(value, label)
        _require(total <= U128_MAXIMUM - value, f"{label} overflows UInt128")
        total += value
    return total


def _json_ascii_expansion(byte: int) -> int:
    _require(0 <= byte <= 0x7F, "DFA byte is outside ASCII")
    if byte < 0x20:
        return 6
    if byte in {ord('"'), ord("\\")}:
        return 2
    return 1


def _language_json_upper(
    language: dict[str, Any],
    dfas: dict[str, dict[str, Any]],
    profiles: dict[str, dict[str, Any]],
    ambient_ceiling: int,
) -> tuple[int, str]:
    kind = language["language_kind"]
    if kind in {"LITERAL", "ENUM"}:
        literals = language["ordered_literals"]
        _require(type(literals) is list and literals, "closed text language is empty")
        return max(len(_canonical_bytes(value)) for value in literals), kind

    if kind == "BUILTIN":
        built_in = language["built_in_language_kind"]
        if built_in == "LOWERCASE_SHA256":
            return 66, "BUILTIN/LOWERCASE_SHA256"
        if built_in == "UINT128_DECIMAL":
            _require(
                language["decimal_maximum"] == str(U128_MAXIMUM),
                "uint128 text maximum differs",
            )
            return 41, "BUILTIN/UINT128_DECIMAL"
        if built_in == "RFC3339_UTC":
            return 29, "BUILTIN/RFC3339_UTC"
        if built_in == "CANONICAL_BASE64":
            maximum = _u128(
                language["maximum_decoded_octets"], "base64 decoded maximum"
            )
            return 2 + 4 * ((maximum + 2) // 3), "BUILTIN/CANONICAL_BASE64"
        if built_in == "RAW_CANONICAL_JSON_STRING":
            return ambient_ceiling, "BUILTIN/RAW_CANONICAL_JSON_STRING"
        raise IntrinsicAttainabilityError(
            f"built-in text language is unresolved: {built_in}"
        )

    if kind == "ASCII_DFA":
        dfa = dfas.get(language["ascii_dfa_id"])
        _require(dfa is not None, "ASCII DFA is unresolved")
        maximum_octets = _u128(dfa["maximum_octets"], "DFA maximum octets")
        expansion = 1
        rows = dfa["ordered_transition_rows"]
        _require(type(rows) is list and rows, "ASCII DFA has no transitions")
        for row in rows:
            lower = _u128(row["inclusive_byte_minimum"], "DFA byte minimum")
            upper = _u128(row["inclusive_byte_maximum"], "DFA byte maximum")
            _require(lower <= upper <= 0x7F, "ASCII DFA transition differs")
            expansion = max(
                expansion,
                max(_json_ascii_expansion(byte) for byte in range(lower, upper + 1)),
            )
        return min(ambient_ceiling, 2 + maximum_octets * expansion), "ASCII_DFA"

    if kind == "UNICODE_IDENTIFIER":
        profile = profiles.get(language["unicode_identifier_profile_id"])
        _require(profile is not None, "Unicode identifier profile is unresolved")
        maximum_utf8 = _u128(profile["maximum_utf8_octets"], "identifier UTF-8 maximum")
        maximum_scalars = _u128(
            profile["maximum_scalar_values"], "identifier scalar maximum"
        )
        forbidden = profile["forbidden_code_point_ranges"]
        _require(
            ["U+0000", "U+001F"] in forbidden,
            "identifier profile does not forbid JSON control scalars",
        )
        # ensure_ascii=False preserves all non-control Unicode bytes.  Only a
        # quote or reverse solidus can add one byte per scalar in this profile.
        upper = 2 + maximum_utf8 + maximum_scalars
        return min(ambient_ceiling, upper), "UNICODE_IDENTIFIER"

    raise IntrinsicAttainabilityError(f"text language kind is unresolved: {kind}")


def _execute_template(
    template: dict[str, Any],
    recurrence: dict[str, Any],
    schemas: list[dict[str, Any]],
    languages: dict[str, dict[str, Any]],
    dfas: dict[str, dict[str, Any]],
    profiles: dict[str, dict[str, Any]],
    *,
    restore_text_languages: bool,
) -> tuple[dict[str, int], list[str], list[dict[str, int]]]:
    ceiling = _u128(
        recurrence["arithmetic_policy"]["published_maximum"],
        "published arithmetic maximum",
    )
    kernels = _index(
        recurrence["ordered_derivation_kernel_records"],
        "derivation_kind",
        18,
        "derivation kernels",
    )
    opcode_rows = _index(
        recurrence["instruction_set"]["transfer_program_schema"][
            "ordered_transfer_opcode_records"
        ],
        "opcode",
        18,
        "transfer opcodes",
    )
    transfer_rules = _index(
        recurrence["transfer_rule_catalog"]["ordered_transfer_rule_records"],
        "transfer_rule_id",
        19,
        "transfer rules",
    )

    cells: list[dict[str, int]] = []
    restored_language_kinds: list[str] = []
    steps = template["ordered_template_steps"]
    _require(type(steps) is list and steps, "template steps differ")
    for position, step in enumerate(steps, 1):
        _require(step["template_step_position"] == position, "template order differs")
        children = step["ordered_child_step_positions"]
        _require(
            type(children) is list
            and len(children) == len(set(children))
            and all(_is_int(child) and 1 <= child < position for child in children),
            "template child order differs",
        )
        kernel = kernels.get(step["derivation_kind"])
        _require(
            kernel is not None
            and kernel["kernel_record_sha256"] == step["kernel_record_sha256"],
            "template kernel binding differs",
        )
        parameters = step["recurrence_parameters"]
        _require(
            type(parameters) is dict
            and set(parameters) == set(kernel["ordered_parameter_member_names"]),
            "template recurrence parameters differ",
        )
        opcode = kernel["transfer_program"]["opcode"]
        _require(opcode in ALLOWED_INTRINSIC_OPCODES, "intrinsic opcode is unresolved")
        opcode_row = opcode_rows.get(opcode)
        _require(opcode_row is not None, "opcode identity is unresolved")
        transfer_rule = transfer_rules.get(opcode_row["transfer_rule_id"])
        _require(transfer_rule is not None, "transfer-rule identity is unresolved")
        _require(
            set(parameters) == set(transfer_rule["ordered_parameter_names"]),
            "transfer-rule parameters differ",
        )
        child_cells = [cells[child - 1] for child in children]

        if opcode == "CELL_BOOLEAN_LITERAL_V1":
            literal = parameters["boolean_literal"]
            domain = [False, True] if literal is None else [literal]
            _require(
                all(type(value) is bool for value in domain), "Boolean domain differs"
            )
            lengths = [len(_canonical_bytes(value)) for value in domain]
            cell = _cell(min(lengths), max(lengths), ceiling)
        elif opcode == "CELL_SAFE_INTEGER_INTERVAL_V1":
            minimum = parameters["integer_minimum"]
            maximum = parameters["integer_maximum"]
            _require(
                _is_int(minimum)
                and _is_int(maximum)
                and -9_007_199_254_740_991
                <= minimum
                <= maximum
                <= 9_007_199_254_740_991,
                "safe-integer interval differs",
            )
            nearest_zero = (
                0 if minimum <= 0 <= maximum else minimum if minimum > 0 else maximum
            )
            cell = _cell(
                len(str(nearest_zero).encode("ascii")),
                max(
                    len(str(minimum).encode("ascii")), len(str(maximum).encode("ascii"))
                ),
                ceiling,
            )
        elif opcode == "CELL_FINITE_TEXT_V1":
            literals = parameters["ordered_literals"]
            _require(
                type(literals) is list
                and literals
                and all(type(value) is str for value in literals),
                "finite text domain differs",
            )
            lengths = [len(_canonical_bytes(value)) for value in literals]
            cell = _cell(min(lengths), max(lengths), ceiling)
        elif opcode == "CELL_BOUNDED_TEXT_OCTETS_V1":
            cell = _cell(
                parameters["minimum_canonical_octets"],
                parameters["maximum_canonical_octets"],
                ceiling,
            )
        elif opcode == "CELL_RELAXED_JSON_STRING_V1":
            upper = ceiling
            if restore_text_languages:
                locator = step["subject_locator"]
                schema_position = locator["registry_position"]
                _require(
                    locator["registry_object_kind"] == "VALUE_SCHEMA"
                    and _is_int(schema_position)
                    and 1 <= schema_position <= len(schemas),
                    "relaxed-text locator differs",
                )
                schema = schemas[schema_position - 1]
                _require(
                    schema["schema_kind"] == "TEXT"
                    and type(schema["text_language_id"]) is str,
                    "relaxed-text schema differs",
                )
                language = languages.get(schema["text_language_id"])
                _require(language is not None, "relaxed-text language is unresolved")
                upper, language_kind = _language_json_upper(
                    language, dfas, profiles, ceiling
                )
                restored_language_kinds.append(language_kind)
            cell = _cell(2, upper, ceiling)
        elif opcode == "CELL_CHILD_BOUNDS_ALIAS_V1":
            _require(
                children == [parameters["child_step_position"]],
                "alias child differs",
            )
            cell = dict(child_cells[0])
        elif opcode == "CELL_NULLABLE_V1":
            _require(
                children == [parameters["child_step_position"]],
                "nullable child differs",
            )
            child = child_cells[0]
            cell = _cell(min(4, child["lower"]), max(4, child["upper"]), ceiling)
        elif opcode == "CELL_ARRAY_BATCH_V1":
            _require(
                children == [parameters["item_step_position"]],
                "array child differs",
            )
            minimum_items = _u128(parameters["minimum_items"], "array minimum")
            maximum_items = _u128(parameters["maximum_items"], "array maximum")
            _require(minimum_items <= maximum_items, "array cardinality differs")
            observer = parameters["observer_closure_record"]
            runs = parameters["ordered_run_records"]
            _require(
                type(observer) is dict
                and observer.get("batch_eligible") is True
                and type(runs) is list
                and sum(_u128(row["item_count"], "array run count") for row in runs)
                == maximum_items,
                "array batch closure differs",
            )
            child = child_cells[0]
            raw_lower = 2 + minimum_items * child["lower"] + max(0, minimum_items - 1)
            raw_upper = 2 + maximum_items * child["upper"] + max(0, maximum_items - 1)
            _require(raw_lower <= ceiling, "array lower exceeds ceiling")
            cell = _cell(raw_lower, min(raw_upper, ceiling), ceiling)
        elif opcode == "CELL_RECORD_V1":
            rows = parameters["ordered_member_records"]
            _require(
                type(rows) is list
                and parameters["record_member_count"] == len(rows) == len(children),
                "record member count differs",
            )
            syntax = 2 + max(0, len(rows) - 1)
            for member_position, row in enumerate(rows, 1):
                _require(
                    row["member_position"] == member_position
                    and row["child_step_position"] == children[member_position - 1],
                    "record member order differs",
                )
                name_octets = len(_canonical_bytes(row["member_name"]))
                _require(
                    row["member_name_canonical_octets"] == name_octets,
                    "record member-name bound differs",
                )
                syntax += name_octets + 1
            _require(
                parameters["record_syntax_octets_excluding_child_values"] == syntax,
                "record syntax differs",
            )
            lower = _checked_sum(
                [syntax] + [child["lower"] for child in child_cells],
                "record lower",
            )
            upper = _checked_sum(
                [syntax] + [child["upper"] for child in child_cells],
                "record upper",
            )
            _require(lower <= ceiling, "record lower exceeds ceiling")
            cell = _cell(lower, min(upper, ceiling), ceiling)
        elif opcode == "CELL_UNION_V1":
            rows = parameters["ordered_alternative_records"]
            _require(
                type(rows) is list
                and len(rows) == len(children)
                and all(
                    row["child_step_position"] == child
                    for row, child in zip(rows, children, strict=True)
                ),
                "union alternatives differ",
            )
            cell = _cell(
                min(child["lower"] for child in child_cells),
                max(child["upper"] for child in child_cells),
                ceiling,
            )
        elif opcode == "CELL_CODEC_INTERSECTION_V1":
            _require(
                children == [parameters["child_step_position"]],
                "codec child differs",
            )
            payload_ceiling = ceiling
            coordinates = parameters["ordered_codec_coordinate_records"]
            _require(
                type(coordinates) is list and coordinates, "codec coordinates differ"
            )
            for coordinate_position, coordinate in enumerate(coordinates, 1):
                _require(
                    coordinate["coordinate_position"] == coordinate_position,
                    "codec coordinate order differs",
                )
                relation = coordinate["codec_byte_bound_relation"]
                limit = _u128(coordinate["codec_octet_limit"], "codec limit")
                _require(relation in {"LE", "LT"}, "codec relation differs")
                effective = limit - int(relation == "LT")
                sibling = _u128(
                    coordinate["minimum_sibling_and_syntax_octets"],
                    "codec sibling minimum",
                )
                derived = 0 if sibling > effective else effective - sibling
                _require(
                    coordinate["derived_payload_octet_ceiling"] == derived,
                    "codec residual differs",
                )
                payload_ceiling = min(payload_ceiling, derived)
            child = child_cells[0]
            _require(child["lower"] <= payload_ceiling, "codec intersection is empty")
            cell = _cell(child["lower"], min(child["upper"], payload_ceiling), ceiling)
        else:  # pragma: no cover - guarded by ALLOWED_INTRINSIC_OPCODES
            raise IntrinsicAttainabilityError(f"opcode is unresolved: {opcode}")
        cells.append(cell)

    _require(template["root_step_position"] == len(cells), "template root differs")
    return cells[-1], sorted(set(restored_language_kinds)), cells


def _case8_exact_witness(
    template: dict[str, Any],
    recurrence: dict[str, Any],
    registry: dict[str, Any],
    schemas: list[dict[str, Any]],
    languages: dict[str, dict[str, Any]],
    tightened_cells: list[dict[str, int]],
) -> dict[str, Any]:
    kernels = _index(
        recurrence["ordered_derivation_kernel_records"],
        "derivation_kind",
        18,
        "derivation kernels",
    )
    descriptors = _index(
        registry["ordered_external_type_descriptors"],
        "type_name",
        52,
        "external type descriptors",
    )
    descriptor = descriptors["CapacityMeasurementDispatchWindowEvidenceV1"]
    _require(descriptor["type_form"] == "RECORD", "case 8 descriptor differs")

    value: dict[str, Any] = {}
    leaf_positions: dict[str, int] = {}
    for step in template["ordered_template_steps"]:
        opcode = kernels[step["derivation_kind"]]["transfer_program"]["opcode"]
        path = step["subject_locator"]["typed_path"]
        if opcode not in {
            "CELL_FINITE_TEXT_V1",
            "CELL_BOUNDED_TEXT_OCTETS_V1",
            "CELL_RELAXED_JSON_STRING_V1",
        }:
            continue
        _require(
            len(path) == 1
            and path[0]["path_step_kind"] == "RECORD_MEMBER"
            and type(path[0]["member_name"]) is str,
            "case 8 scalar locator differs",
        )
        member = path[0]["member_name"]
        _require(member not in value, "case 8 scalar member is duplicated")
        leaf_positions[member] = step["template_step_position"]
        if opcode == "CELL_FINITE_TEXT_V1":
            literals = step["recurrence_parameters"]["ordered_literals"]
            value[member] = max(
                literals, key=lambda item: (len(_canonical_bytes(item)), item)
            )
        elif opcode == "CELL_BOUNDED_TEXT_OCTETS_V1":
            schema = schemas[step["subject_locator"]["registry_position"] - 1]
            language = languages[schema["text_language_id"]]
            _require(
                language["built_in_language_kind"] == "LOWERCASE_SHA256",
                "case 8 bounded text is not SHA-256",
            )
            value[member] = "f" * 64
        elif member == "dispatch_started_at":
            value[member] = "9999-12-31T23:59:59.999998Z"
        elif member == "dispatch_completed_at":
            value[member] = "9999-12-31T23:59:59.999999Z"
        elif member == "dispatch_started_monotonic_ns":
            value[member] = str(U128_MAXIMUM - 1)
        elif member == "dispatch_completed_monotonic_ns":
            value[member] = str(U128_MAXIMUM)
        else:
            raise IntrinsicAttainabilityError(
                f"case 8 relaxed scalar is unresolved: {member}"
            )

    expected_members = [
        row["member_name"] for row in descriptor["record_member_descriptors"]
    ]
    _require(set(value) == set(expected_members), "case 8 record members differ")
    _require(
        value["canonicalization_version"] == registry["canonicalization_version"]
        and value["measurement_schema_version"]
        == registry["measurement_schema_version"]
        and value["record_domain"] == descriptor["described_record_domain"],
        "case 8 standalone constants differ",
    )

    identity_field = descriptor["identity_field"]
    payload = {
        name: value[name] for name in descriptor["identity_payload_member_order"]
    }
    value[identity_field] = _semantic_id(
        registry["canonicalization_version"],
        registry["measurement_schema_version"],
        descriptor["described_record_domain"],
        payload,
    )

    timestamp_pattern = re.compile(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
        r"\.[0-9]{6}Z"
    )
    _require(
        timestamp_pattern.fullmatch(value["dispatch_started_at"]) is not None
        and timestamp_pattern.fullmatch(value["dispatch_completed_at"]) is not None
        and value["dispatch_started_at"] < value["dispatch_completed_at"],
        "case 8 timestamp order differs",
    )
    started_ns = int(value["dispatch_started_monotonic_ns"])
    completed_ns = int(value["dispatch_completed_monotonic_ns"])
    _require(
        0 <= started_ns < completed_ns <= U128_MAXIMUM,
        "case 8 monotonic order differs",
    )
    for member in (
        "transport_session_id",
        "outbound_subscription_intent_id",
        "socket_lease_id",
        "monotonic_clock_domain_id",
        identity_field,
    ):
        _require(
            re.fullmatch(r"[0-9a-f]{64}", value[member]) is not None,
            f"case 8 SHA-256 member differs: {member}",
        )
    for member, position in leaf_positions.items():
        actual = len(_canonical_bytes(value[member]))
        cell = tightened_cells[position - 1]
        _require(
            cell["lower"] <= actual <= cell["upper"],
            f"case 8 scalar misses tightened cell: {member}",
        )

    raw = _canonical_bytes(value)
    _require(
        descriptor["codec_byte_bound_relation"] == "LE"
        and len(raw) <= descriptor["codec_octet_limit"],
        "case 8 codec bound differs",
    )
    return {
        "exact_legal_maximum_octets": len(raw),
        "exact_legal_maximum_sha256": _sha256(raw),
        "identity_field": identity_field,
        "identity_value": value[identity_field],
        "intrinsic_rule_id": descriptor["ordered_intrinsic_rule_ids"][0],
        "intrinsic_rule_satisfied": True,
        "standalone_identity_recomputed": True,
        "witness_record": value,
    }


def analyze(root: pathlib.Path) -> dict[str, Any]:
    root = pathlib.Path(root).resolve()
    seed = _load_pinned(root, SEED_RELATIVE_PATH, SEED_RAW_OCTETS, SEED_RAW_SHA256)
    registry = _load_pinned(
        root, REGISTRY_RELATIVE_PATH, REGISTRY_RAW_OCTETS, REGISTRY_RAW_SHA256
    )
    contract = _load_pinned(
        root, CONTRACT_RELATIVE_PATH, CONTRACT_RAW_OCTETS, CONTRACT_RAW_SHA256
    )
    _require(seed["seed_catalog_id"] == SEED_ID, "seed semantic identity differs")
    _require(
        registry["external_schema_registry_id"] == REGISTRY_ID,
        "registry semantic identity differs",
    )
    _require(
        contract["all_case_campaign_contract_id"] == CONTRACT_ID,
        "campaign contract identity differs",
    )

    recipe = seed["logical_plan_recipe_catalog"]
    plans = recipe["ordered_logical_count_plan_records"]
    _require(len(plans) == CASE_COUNT, "logical plan count differs")
    templates = _index(
        recipe["ordered_logical_plan_templates"],
        "logical_plan_template_id",
        None,
        "logical plan templates",
    )
    execution_rows = contract["case_universe_contract"][
        "ordered_case_execution_records"
    ]
    _require(len(execution_rows) == CASE_COUNT, "execution ledger count differs")
    schemas = registry["value_schema_catalog"]
    languages = _index(
        registry["text_language_catalog"],
        "text_language_id",
        103,
        "text languages",
    )
    dfas = _index(registry["ascii_dfa_catalog"], "ascii_dfa_id", 9, "ASCII DFAs")
    profiles = _index(
        registry["identifier_profile_catalog"],
        "unicode_identifier_profile_id",
        3,
        "identifier profiles",
    )

    contradiction_records: list[dict[str, Any]] = []
    case8_template = None
    case8_tightened_cells = None
    for position in range(1, INTRINSIC_CASE_COUNT + 1):
        plan = plans[position - 1]
        execution = execution_rows[position - 1]
        _require(
            plan["case_position"] == execution["case_position"] == position
            and execution["execution_family"] == "INTRINSIC_TEMPLATE_ATTAINMENT"
            and execution["candidate_transport"]
            == "INHERITED_CLOSED_CANDIDATE_BUNDLE_V1"
            and plan["upper_bound_mode"]
            == "LEGAL_DOMAIN_SUPERSET_WITH_LEGAL_ATTAINMENT",
            f"intrinsic case binding differs: {position}",
        )
        template = templates.get(plan["logical_plan_template_id"])
        _require(template is not None, f"intrinsic template is unresolved: {position}")
        published, _, _ = _execute_template(
            template,
            seed["recurrence_catalog"],
            schemas,
            languages,
            dfas,
            profiles,
            restore_text_languages=False,
        )
        tightened, language_kinds, tightened_cells = _execute_template(
            template,
            seed["recurrence_catalog"],
            schemas,
            languages,
            dfas,
            profiles,
            restore_text_languages=True,
        )
        if tightened["upper"] < published["upper"]:
            binding = plan["case_binding"]
            contradiction_records.append(
                {
                    "case_position": position,
                    "row_kind": binding["row_kind"],
                    "type_name": binding["type_name"],
                    "alternative_name": binding["alternative_name"],
                    "logical_count_plan_id": plan["logical_count_plan_id"],
                    "published_p2_upper_bound_octets": published["upper"],
                    "language_aware_legal_superset_upper_bound_octets": tightened[
                        "upper"
                    ],
                    "unattainable_gap_octets": published["upper"] - tightened["upper"],
                    "ordered_restored_language_kinds": language_kinds,
                    "p3_equality_possible": False,
                }
            )
        if position == CASE8_POSITION:
            case8_template = template
            case8_tightened_cells = tightened_cells

    _require(
        case8_template is not None and case8_tightened_cells is not None,
        "case 8 template is unresolved",
    )
    case8_exact = _case8_exact_witness(
        case8_template,
        seed["recurrence_catalog"],
        registry,
        schemas,
        languages,
        case8_tightened_cells,
    )
    case8_record = next(
        row for row in contradiction_records if row["case_position"] == CASE8_POSITION
    )
    _require(
        case8_exact["exact_legal_maximum_octets"]
        == case8_record["language_aware_legal_superset_upper_bound_octets"]
        == 928,
        "case 8 exactness join differs",
    )

    positions = [row["case_position"] for row in contradiction_records]
    _require(
        len(positions) == len(set(positions)) and positions == sorted(positions),
        "contradiction order differs",
    )
    analysis = {
        "analysis_version": (
            "riskyieldmm.raw_v8_step2.maximum_protocol_v2."
            "intrinsic_template_attainability_falsification.v1"
        ),
        "packet": "A4-R475-V1-F",
        "decision": "NO_GO_FROZEN_INTRINSIC_P2_ENDPOINTS_UNATTAINABLE",
        "formal_stage1_state": "NO-GO",
        "seed_raw_octets": SEED_RAW_OCTETS,
        "seed_raw_sha256": SEED_RAW_SHA256,
        "seed_catalog_id": SEED_ID,
        "registry_raw_octets": REGISTRY_RAW_OCTETS,
        "registry_raw_sha256": REGISTRY_RAW_SHA256,
        "external_schema_registry_id": REGISTRY_ID,
        "contract_raw_octets": CONTRACT_RAW_OCTETS,
        "contract_raw_sha256": CONTRACT_RAW_SHA256,
        "all_case_campaign_contract_id": CONTRACT_ID,
        "intrinsic_case_count": INTRINSIC_CASE_COUNT,
        "contradiction_case_count": len(contradiction_records),
        "not_falsified_by_text_ceiling_case_count": (
            INTRINSIC_CASE_COUNT - len(contradiction_records)
        ),
        "contradiction_case_positions": positions,
        "ordered_contradiction_records": contradiction_records,
        "contradiction_vector_sha256": _sha256(_canonical_bytes(contradiction_records)),
        "case8_exactness_witness": case8_exact,
        "all_66_p3_equality_possible": False,
        "falsification_strength": (
            "LANGUAGE_AWARE_DOMAIN_SUPERSET_UPPER_BELOW_PUBLISHED_P2"
        ),
        "nonclaim": ("UNCHANGED_CASES_ARE_NOT_PROVEN_ATTAINABLE_BY_THIS_ANALYSIS"),
        "required_action": (
            "VERSIONED_INTRINSIC_TEMPLATE_AUTHORITY_REPAIR_BEFORE_A4_R475_V1"
        ),
        "next_bounded_packet": "A4-R475-V1-C",
    }
    analysis["attainability_falsification_id"] = _semantic_id(
        registry["canonicalization_version"],
        registry["measurement_schema_version"],
        ANALYSIS_DOMAIN,
        analysis,
    )
    return analysis


def _main(argv: list[str]) -> int:
    if len(argv) != 1:
        sys.stderr.write("usage: checker REPOSITORY_ROOT\n")
        return 2
    try:
        result = analyze(pathlib.Path(argv[0]))
    except (IntrinsicAttainabilityError, OSError) as error:
        sys.stderr.write(f"intrinsic-attainability check failed: {error}\n")
        return 1
    sys.stdout.buffer.write(_pretty_bytes(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))

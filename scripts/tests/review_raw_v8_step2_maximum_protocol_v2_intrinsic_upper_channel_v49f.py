#!/usr/bin/env python3
"""Independent C2-U reviewer for the frozen intrinsic legal-upper channel.

This program imports neither channel implementation.  It reconstructs every
case bound from the byte-pinned C1 correction contract and structural registry
with a recursive evaluator and a reverse DFA recurrence, then compares that
oracle with the one official C2-U result.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import pathlib
import sys
from dataclasses import dataclass
from typing import Any, Final, NoReturn

PACKET: Final = "A4-R475-V1-C2-U"
NEXT_PACKET: Final = "A4-R475-V1-C2-A"
CASE_COUNT: Final = 66
PROOF_STEP_COUNT: Final = 1_647
CANONICAL_CEILING: Final = 524_288
SAFE_INTEGER_MAXIMUM: Final = 9_007_199_254_740_991
U128_MAXIMUM: Final = (1 << 128) - 1

CONTRACT_PATH: Final = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_correction_contract_v49f.json"
)
CONTRACT_OCTETS: Final = 5_436_266
CONTRACT_SHA256: Final = (
    "6245595b759cec6cdecd88292f105dac938f5c69ae92f90ae0365bd032180e14"
)
CONTRACT_ID: Final = (
    "171e9d47a7733f8448f94af5a16da4ba5258f30ee08cb4c835289a05adcb8cb9"
)
REGISTRY_PATH: Final = (
    "scripts/tests/raw_v8_step2_external_schema_v2_structural_registry_v49f.json"
)
REGISTRY_OCTETS: Final = 1_469_663
REGISTRY_SHA256: Final = (
    "9160297ff316c5931737c92f8b359f0a1e2ec22f0aa996ef3b09cf830dc96bf3"
)
FREEZE_PATH: Final = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_dual_source_freeze_v49f.json"
)
FREEZE_OCTETS: Final = 9_861
FREEZE_SHA256: Final = (
    "57891c14624ed999e1b370a2478e41c99b23c6d0c471d9493c71c8381c40e3c5"
)
FREEZE_ID: Final = (
    "d6e17e638a99449bc806b72cfefb850d6f64ed578dc5314a135b8e71fe5b008e"
)
UPPER_SOURCE_PATH: Final = (
    "scripts/tests/solve_raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_upper_v49f.py"
)
UPPER_SOURCE_OCTETS: Final = 24_421
UPPER_SOURCE_SHA256: Final = (
    "5ef8441d5ddb14642d2a90f688e5f0cf9e49384a18eb9c91b48e293eab526e8a"
)
UPPER_SCHEMA_PATH: Final = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_upper_result_schema_v49f.json"
)
UPPER_SCHEMA_OCTETS: Final = 3_957
UPPER_SCHEMA_SHA256: Final = (
    "ea4cab7ecf94f3a4951efd92f35ec7bf69a81fb6da5e55e1f41e33ef0f2871eb"
)
UPPER_SCHEMA_ID: Final = (
    "7e2af5b6b28d64bd6251f02bb2ae8d9b005f2c05c3321994e4cc8c1e9449326b"
)
UPPER_RESULT_PATH: Final = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_upper_channel_result_v49f.json"
)
ACCEPTANCE_REPORT_PATH: Final = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_upper_channel_acceptance_report_v49f.json"
)

RESULT_VERSION: Final = (
    "riskyieldmm.raw_v8_step2.maximum_protocol_v2."
    "intrinsic_legal_upper_result.v1"
)
RESULT_DOMAIN: Final = (
    "RiskYieldMMRawV8Step2MaximumProtocolV2IntrinsicLegalUpperResultV1"
)
CASE_DOMAIN: Final = (
    "RiskYieldMMRawV8Step2MaximumProtocolV2IntrinsicLegalUpperCaseV1"
)
PROOF_STEP_DOMAIN: Final = "RiskYieldMMIntrinsicUpperProofStepV1"
SCHEMA_DOMAIN: Final = (
    "RiskYieldMMRawV8Step2MaximumProtocolV2IntrinsicUpperOutputSchemaV1"
)
REPORT_VERSION: Final = (
    "riskyieldmm.raw_v8_step2.maximum_protocol_v2."
    "intrinsic_upper_channel_acceptance.v1"
)
REPORT_DOMAIN: Final = (
    "RiskYieldMMRawV8Step2MaximumProtocolV2"
    "IntrinsicUpperChannelAcceptanceV1"
)

DERIVATION_KINDS: Final = (
    "ASSOCIATIVE_HOMOGENEOUS_RUN_BATCH",
    "CODEC_INTERSECTION",
    "EXACT_BOOLEAN",
    "NULLABLE_BRANCH",
    "OBJECT_REFERENCE",
    "RECORD_MEMBER_FOLD",
    "SAFE_INTEGER_BAND",
    "TAGGED_UNION_BRANCH",
    "TEXT_BOUNDED_LANGUAGE",
    "TEXT_BUILTIN_BOUNDED",
    "TEXT_FINITE",
)
PROOF_METHODS: Final = (
    "ASCII_DFA_DYNAMIC_PROGRAMMING",
    "CLOSED_BUILTIN_FORMULA",
    "CODEC_INTERSECTION",
    "FINITE_ENUMERATION",
    "PINNED_UNICODE_PROFILE_PROGRAM",
    "RULE_AWARE_COMPOSITION",
)
EXPECTED_DERIVATION_CENSUS: Final = {
    "ASSOCIATIVE_HOMOGENEOUS_RUN_BATCH": 91,
    "CODEC_INTERSECTION": 160,
    "EXACT_BOOLEAN": 25,
    "NULLABLE_BRANCH": 145,
    "OBJECT_REFERENCE": 47,
    "RECORD_MEMBER_FOLD": 138,
    "SAFE_INTEGER_BAND": 247,
    "TAGGED_UNION_BRANCH": 22,
    "TEXT_BOUNDED_LANGUAGE": 183,
    "TEXT_BUILTIN_BOUNDED": 254,
    "TEXT_FINITE": 335,
}
EXPECTED_ROOT_MEMBERS: Final = (
    "canonicalization_version",
    "measurement_schema_version",
    "result_version",
    "packet",
    "source_freeze_id",
    "source_sha256",
    "output_schema_id",
    "intrinsic_exactness_correction_contract_id",
    "case_count",
    "ordered_case_upper_records",
    "ordered_case_upper_records_sha256",
    "proof_method_case_census",
    "exactness_claimed",
    "attainer_channel_consumed",
    "formal_stage1_state",
    "next_bounded_packet",
    "upper_channel_result_id",
)
EXPECTED_CASE_MEMBERS: Final = (
    "case_position",
    "intrinsic_correction_case_id",
    "case_execution_record_id",
    "logical_count_plan_id",
    "root_type_name",
    "legal_domain_upper_octets",
    "proof_status",
    "ordered_proof_methods",
    "proof_step_count",
    "proof_step_transcript_sha256",
    "attainer_source_or_output_read",
    "upper_case_record_id",
)
ALLOWED_SOURCE_IMPORTS: Final = {
    "__future__",
    "argparse",
    "hashlib",
    "json",
    "os",
    "pathlib",
    "sys",
    "typing",
}


class ReviewFailure(RuntimeError):
    """Stable fail-closed C2-U review failure."""


def _reject(message: str) -> NoReturn:
    raise ReviewFailure(str(message).replace("\n", " ")[:768])


def _require(condition: bool, message: str) -> None:
    if not condition:
        _reject(message)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _bounded_integer(value: Any, lower: int, upper: int, label: str) -> int:
    _require(_is_int(value) and lower <= value <= upper, f"{label} differs")
    return value


def _u128(value: Any, label: str) -> int:
    return _bounded_integer(value, 0, U128_MAXIMUM, label)


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
        _reject(f"canonical JSON rejected: {error}")


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


def _semantic_id(domain: str, payload: Any) -> str:
    return _sha256(_canonical_bytes({"domain": domain, "payload": payload}))


def _duplicate_guard(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result, f"duplicate JSON member: {key}")
        result[key] = value
    return result


def _reject_number(value: str) -> NoReturn:
    _reject(f"non-integer JSON number is forbidden: {value}")


def _strict_load(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_duplicate_guard,
            parse_float=_reject_number,
            parse_constant=_reject_number,
        )
    except (json.JSONDecodeError, UnicodeError) as error:
        _reject(f"{label} JSON rejected: {error}")
    _require(type(value) is dict, f"{label} root differs")
    return value


def _read_regular(root: pathlib.Path, relative_path: str, label: str) -> bytes:
    path = root / relative_path
    _require(path.is_file() and not path.is_symlink(), f"{label} path differs")
    return path.read_bytes()


def _read_pinned(
    root: pathlib.Path,
    relative_path: str,
    octets: int,
    digest: str,
    label: str,
) -> tuple[bytes, dict[str, Any]]:
    raw = _read_regular(root, relative_path, label)
    _require(len(raw) == octets, f"{label} octets differ")
    _require(_sha256(raw) == digest, f"{label} hash differs")
    return raw, _strict_load(raw, label)


def _index(rows: Any, member: str, label: str) -> dict[Any, dict[str, Any]]:
    _require(type(rows) is list, f"{label} differs")
    result: dict[Any, dict[str, Any]] = {}
    for row in rows:
        _require(type(row) is dict and member in row, f"{label} row differs")
        key = row[member]
        _require(key not in result, f"{label} key is duplicated")
        result[key] = row
    return result


def _checked_sum(values: list[int], label: str) -> int:
    total = 0
    for value in values:
        value = _u128(value, label)
        _require(total <= U128_MAXIMUM - value, f"{label} overflows UInt128")
        total += value
    return total


def _source_imports(raw: bytes) -> set[str]:
    try:
        tree = ast.parse(raw.decode("utf-8"))
    except (SyntaxError, UnicodeError) as error:
        _reject(f"upper source syntax differs: {error}")
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add((node.module or "").split(".")[0])
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            _require(node.func.id != "__import__", "dynamic import is forbidden")
    return imports


def _validate_source(raw: bytes) -> None:
    _require(len(raw) == UPPER_SOURCE_OCTETS, "upper source octets differ")
    _require(_sha256(raw) == UPPER_SOURCE_SHA256, "upper source hash differs")
    _require(_source_imports(raw) == ALLOWED_SOURCE_IMPORTS, "upper imports differ")
    text = raw.decode("utf-8")
    _require(
        "A4_R475_V1_C2_U_STANDALONE_LEGAL_UPPER_SOLVER_V1" in text,
        "upper source marker differs",
    )
    forbidden_fragments = (
        "construct_raw_v8_step2_maximum_protocol_v2_intrinsic_attainers",
        "intrinsic_attainer_channel_result",
        "intrinsic_attainer_witness_shard",
        "validate_raw_v8_step2_external_schema_v2_rule_runtime_v49f",
        "importlib",
        "subprocess",
    )
    _require(
        not any(fragment in text for fragment in forbidden_fragments),
        "upper source contains a forbidden channel/runtime reference",
    )


def _validate_schema(schema: dict[str, Any]) -> None:
    payload = {key: value for key, value in schema.items() if key != "output_schema_id"}
    _require(schema["identity_domain"] == SCHEMA_DOMAIN, "schema domain differs")
    _require(
        schema["output_schema_id"] == _semantic_id(SCHEMA_DOMAIN, payload),
        "schema identity differs",
    )
    _require(schema["output_schema_id"] == UPPER_SCHEMA_ID, "schema ID differs")
    root_schema = schema["root_record_schema"]
    case_schema = schema["case_record_schema"]
    _require(
        tuple(root_schema["ordered_member_names"]) == EXPECTED_ROOT_MEMBERS,
        "root schema members differ",
    )
    _require(
        tuple(case_schema["ordered_member_names"]) == EXPECTED_CASE_MEMBERS,
        "case schema members differ",
    )
    _require(
        root_schema["unknown_member_policy"]
        == case_schema["unknown_member_policy"]
        == "REJECT",
        "schema unknown-member policy differs",
    )
    transport = schema["transport_contract"]
    _require(
        transport["channel_output_relative_path"] == UPPER_RESULT_PATH
        and transport["file_count"] == 1
        and transport["pre_freeze_output_presence_policy"] == "MUST_BE_ABSENT"
        and transport["atomic_publication"]
        == "ABSENT_PATH_EXCLUSIVE_TEMP_FSYNC_LINK_NOREPLACE_UNLINK_TEMP_FSYNC_PARENT",
        "upper transport contract differs",
    )


def _validate_freeze(freeze: dict[str, Any]) -> None:
    payload = {key: value for key, value in freeze.items() if key != "dual_source_freeze_id"}
    _require(
        freeze["dual_source_freeze_id"]
        == _semantic_id(freeze["identity_domain"], payload)
        == FREEZE_ID,
        "source-freeze identity differs",
    )
    rows = freeze["ordered_channel_source_records"]
    own = next((row for row in rows if row.get("channel") == "LEGAL_UPPER"), None)
    _require(type(own) is dict, "upper freeze row is absent")
    _require(
        own["relative_path"] == UPPER_SOURCE_PATH
        and own["raw_octets"] == UPPER_SOURCE_OCTETS
        and own["raw_sha256"] == UPPER_SOURCE_SHA256
        and own["output_schema_relative_path"] == UPPER_SCHEMA_PATH
        and own["output_schema_raw_sha256"] == UPPER_SCHEMA_SHA256
        and own["output_schema_id"] == UPPER_SCHEMA_ID
        and own["ordered_fixed_output_relative_paths"] == [UPPER_RESULT_PATH]
        and own["successor_packet"] == PACKET,
        "upper freeze row differs",
    )
    resources = freeze["resource_contract"]
    projection = freeze["output_transport_projection"]
    _require(
        resources["limit_tuning_from_observed_channel_answer_allowed"] is False
        and resources["total_pinned_input_octets_limit"] == 67_108_864
        and resources["input_file_count_limit"] == 64
        and resources["individual_file_strict_upper_octets"] == 16_777_216
        and projection["answer_observation_used_to_set_limits"] is False
        and projection["upper_result_projected_strict_upper_octets"] == 2_097_152,
        "C2-S resource contract differs",
    )


@dataclass(frozen=True)
class Cell:
    lower: int
    upper: int
    method: str


def _json_width(value: Any) -> int:
    return len(_canonical_bytes(value))


def _transition_width(lower: int, upper: int) -> int:
    _require(0 <= lower <= upper <= 0x7F, "DFA byte range differs")
    if lower <= 0x1F:
        return 6
    if lower <= 0x22 <= upper or lower <= 0x5C <= upper:
        return 2
    return 1


def _reverse_dfa_upper(dfa: dict[str, Any]) -> int:
    minimum = _bounded_integer(dfa["minimum_octets"], 0, 1_048_576, "DFA minimum")
    maximum = _bounded_integer(dfa["maximum_octets"], minimum, 1_048_576, "DFA maximum")
    accepting = set(dfa["ordered_accepting_states"])
    _require(accepting, "DFA accepting set is empty")
    transitions: list[tuple[Any, Any, int]] = []
    for row in dfa["ordered_transition_rows"]:
        transitions.append(
            (
                row["source_state"],
                row["target_state"],
                _transition_width(
                    row["inclusive_byte_minimum"],
                    row["inclusive_byte_maximum"],
                ),
            )
        )
    remaining: dict[Any, int] = dict.fromkeys(accepting, 0)
    winners: list[int] = []
    for length in range(maximum + 1):
        if length >= minimum and dfa["start_state"] in remaining:
            winners.append(remaining[dfa["start_state"]])
        if length == maximum:
            break
        following: dict[Any, int] = {}
        for source, target, width in transitions:
            if target in remaining:
                candidate = width + remaining[target]
                following[source] = max(following.get(source, -1), candidate)
        remaining = following
    _require(winners, "DFA language is empty in its pinned interval")
    return 2 + max(winners)


def _language_upper(
    language: dict[str, Any],
    dfas: dict[Any, dict[str, Any]],
    profiles: dict[Any, dict[str, Any]],
) -> tuple[int, str]:
    kind = language["language_kind"]
    if kind in {"LITERAL", "ENUM"}:
        literals = language["ordered_literals"]
        _require(
            type(literals) is list
            and literals
            and all(type(value) is str for value in literals),
            "finite text language differs",
        )
        return max(_json_width(value) for value in literals), "FINITE_ENUMERATION"
    if kind == "ASCII_DFA":
        dfa = dfas.get(language["ascii_dfa_id"])
        _require(type(dfa) is dict, "ASCII DFA dependency is unresolved")
        return min(CANONICAL_CEILING, _reverse_dfa_upper(dfa)), (
            "ASCII_DFA_DYNAMIC_PROGRAMMING"
        )
    if kind == "UNICODE_IDENTIFIER":
        profile = profiles.get(language["unicode_identifier_profile_id"])
        _require(type(profile) is dict, "Unicode profile dependency is unresolved")
        utf8 = _u128(profile["maximum_utf8_octets"], "Unicode UTF-8 maximum")
        scalars = _u128(profile["maximum_scalar_values"], "Unicode scalar maximum")
        return min(CANONICAL_CEILING, 2 + utf8 + scalars), (
            "PINNED_UNICODE_PROFILE_PROGRAM"
        )
    _require(kind == "BUILTIN", f"unsupported text language: {kind}")
    built_in = language["built_in_language_kind"]
    if built_in == "LOWERCASE_SHA256":
        return 66, "CLOSED_BUILTIN_FORMULA"
    if built_in == "UINT128_DECIMAL":
        _require(
            language["decimal_maximum"] == str(U128_MAXIMUM),
            "UInt128 text maximum differs",
        )
        return 41, "CLOSED_BUILTIN_FORMULA"
    if built_in == "RFC3339_UTC":
        return 29, "CLOSED_BUILTIN_FORMULA"
    if built_in == "CANONICAL_BASE64":
        decoded = _u128(language["maximum_decoded_octets"], "base64 maximum")
        return min(CANONICAL_CEILING, 2 + 4 * ((decoded + 2) // 3)), (
            "CLOSED_BUILTIN_FORMULA"
        )
    if built_in == "RAW_CANONICAL_JSON_STRING":
        return CANONICAL_CEILING, "CLOSED_BUILTIN_FORMULA"
    _reject(f"unsupported built-in language: {built_in}")


class CaseOracle:
    """Recursive independent evaluator over one frozen C1 step graph."""

    def __init__(
        self,
        case: dict[str, Any],
        languages: dict[Any, dict[str, Any]],
        dfas: dict[Any, dict[str, Any]],
        profiles: dict[Any, dict[str, Any]],
    ) -> None:
        self.case = case
        self.steps = case["ordered_step_contract_records"]
        self.languages = languages
        self.dfas = dfas
        self.profiles = profiles
        self.cells: dict[int, Cell] = {}
        self.transcript: dict[int, dict[str, Any]] = {}
        self.visiting: set[int] = set()

    def evaluate(self, position: int) -> Cell:
        if position in self.cells:
            return self.cells[position]
        _require(position not in self.visiting, "step graph contains a cycle")
        _require(1 <= position <= len(self.steps), "step position is out of range")
        self.visiting.add(position)
        step = self.steps[position - 1]
        _require(step["step_position"] == position, "step order differs")
        kind = step["derivation_kind"]
        _require(kind in DERIVATION_KINDS, f"unknown derivation kind: {kind}")
        children = step["ordered_child_step_positions"]
        _require(
            type(children) is list
            and len(children) == len(set(children))
            and all(_is_int(child) and 1 <= child < position for child in children),
            "postorder child relation differs",
        )
        child_cells = [self.evaluate(child) for child in children]
        cell = self._derive(kind, step["recurrence_parameters"], children, child_cells)
        _require(
            0 <= cell.lower <= cell.upper <= CANONICAL_CEILING,
            "derived interval differs",
        )
        payload = {
            "step_position": position,
            "correction_step_id": step["correction_step_id"],
            "derivation_kind": kind,
            "ordered_child_step_positions": children,
            "ordered_dependency_references": step["ordered_dependency_references"],
            "lower_canonical_octets": cell.lower,
            "legal_domain_upper_octets": cell.upper,
            "proof_method": cell.method,
            "predicate_treatment": "INTERSECTION_ONLY_NEVER_DOMAIN_EXPANSION",
        }
        self.transcript[position] = {
            **payload,
            "proof_step_id": _semantic_id(PROOF_STEP_DOMAIN, payload),
        }
        self.cells[position] = cell
        self.visiting.remove(position)
        return cell

    def _derive(
        self,
        kind: str,
        parameters: dict[str, Any],
        children: list[int],
        child_cells: list[Cell],
    ) -> Cell:
        if kind == "EXACT_BOOLEAN":
            literal = parameters["boolean_literal"]
            values = (False, True) if literal is None else (literal,)
            _require(all(type(value) is bool for value in values), "boolean differs")
            sizes = [_json_width(value) for value in values]
            return Cell(min(sizes), max(sizes), "FINITE_ENUMERATION")
        if kind == "SAFE_INTEGER_BAND":
            lower = parameters["integer_minimum"]
            upper = parameters["integer_maximum"]
            _require(
                _is_int(lower)
                and _is_int(upper)
                and -SAFE_INTEGER_MAXIMUM <= lower <= upper <= SAFE_INTEGER_MAXIMUM,
                "safe-integer band differs",
            )
            closest = 0 if lower <= 0 <= upper else min((lower, upper), key=abs)
            return Cell(
                len(str(closest)),
                max(len(str(lower)), len(str(upper))),
                "CLOSED_BUILTIN_FORMULA",
            )
        if kind == "TEXT_FINITE":
            literals = parameters["ordered_literals"]
            _require(
                type(literals) is list
                and literals
                and all(type(value) is str for value in literals),
                "finite text differs",
            )
            sizes = [_json_width(value) for value in literals]
            return Cell(min(sizes), max(sizes), "FINITE_ENUMERATION")
        if kind == "TEXT_BUILTIN_BOUNDED":
            return Cell(
                _u128(parameters["minimum_canonical_octets"], "text minimum"),
                _u128(parameters["maximum_canonical_octets"], "text maximum"),
                "CLOSED_BUILTIN_FORMULA",
            )
        if kind == "TEXT_BOUNDED_LANGUAGE":
            language = self.languages.get(parameters["text_language_id"])
            _require(type(language) is dict, "text language is unresolved")
            upper, method = _language_upper(language, self.dfas, self.profiles)
            return Cell(2, upper, method)
        if kind == "OBJECT_REFERENCE":
            _require(len(child_cells) == 1, "object-reference arity differs")
            return Cell(child_cells[0].lower, child_cells[0].upper, "RULE_AWARE_COMPOSITION")
        if kind == "NULLABLE_BRANCH":
            _require(len(child_cells) == 1, "nullable arity differs")
            child = child_cells[0]
            return Cell(min(4, child.lower), max(4, child.upper), "RULE_AWARE_COMPOSITION")
        if kind == "ASSOCIATIVE_HOMOGENEOUS_RUN_BATCH":
            _require(len(child_cells) == 1, "array arity differs")
            minimum = _u128(parameters["minimum_items"], "array minimum")
            maximum = _u128(parameters["maximum_items"], "array maximum")
            _require(minimum <= maximum, "array cardinality differs")
            child = child_cells[0]
            lower = 2 + minimum * child.lower + max(0, minimum - 1)
            upper = 2 + maximum * child.upper + max(0, maximum - 1)
            return Cell(lower, min(upper, CANONICAL_CEILING), "RULE_AWARE_COMPOSITION")
        if kind == "RECORD_MEMBER_FOLD":
            rows = parameters["ordered_member_records"]
            _require(type(rows) is list and len(rows) == len(children), "record members differ")
            syntax = 2 + max(0, len(rows) - 1)
            for ordinal, (row, child) in enumerate(zip(rows, children, strict=True), 1):
                name_width = _json_width(row["member_name"])
                _require(
                    row["member_position"] == ordinal
                    and row["child_step_position"] == child
                    and row["member_name_canonical_octets"] == name_width,
                    "record member contract differs",
                )
                syntax += name_width + 1
            _require(
                parameters["record_syntax_octets_excluding_child_values"] == syntax,
                "record syntax differs",
            )
            lower = _checked_sum([syntax] + [cell.lower for cell in child_cells], "record lower")
            upper = _checked_sum([syntax] + [cell.upper for cell in child_cells], "record upper")
            return Cell(lower, min(upper, CANONICAL_CEILING), "RULE_AWARE_COMPOSITION")
        if kind == "TAGGED_UNION_BRANCH":
            _require(child_cells, "union is empty")
            return Cell(
                min(cell.lower for cell in child_cells),
                max(cell.upper for cell in child_cells),
                "RULE_AWARE_COMPOSITION",
            )
        _require(kind == "CODEC_INTERSECTION", f"unhandled derivation kind: {kind}")
        _require(len(child_cells) == 1, "codec arity differs")
        residual = CANONICAL_CEILING
        rows = parameters["ordered_codec_coordinate_records"]
        _require(type(rows) is list and rows, "codec coordinates differ")
        for ordinal, row in enumerate(rows, 1):
            relation = row["codec_byte_bound_relation"]
            limit = _u128(row["codec_octet_limit"], "codec limit")
            _require(
                row["coordinate_position"] == ordinal and relation in {"LE", "LT"},
                "codec coordinate differs",
            )
            _require(relation == "LE" or limit > 0, "strict codec limit underflows")
            effective = limit if relation == "LE" else limit - 1
            siblings = _u128(
                row["minimum_sibling_and_syntax_octets"],
                "codec sibling minimum",
            )
            candidate = max(0, effective - siblings)
            _require(
                row["derived_payload_octet_ceiling"] == candidate,
                "codec residual differs",
            )
            residual = min(residual, candidate)
        child = child_cells[0]
        _require(child.lower <= residual, "codec intersection is empty")
        return Cell(child.lower, min(child.upper, residual), "CODEC_INTERSECTION")

    def complete(self) -> tuple[int, list[dict[str, Any]], list[str]]:
        for position in range(1, len(self.steps) + 1):
            self.evaluate(position)
        root = self.case["root_step_position"]
        _require(root == len(self.steps), "root step position differs")
        transcript = [self.transcript[position] for position in range(1, root + 1)]
        methods = sorted({"RULE_AWARE_COMPOSITION", *(cell.method for cell in self.cells.values())})
        return self.cells[root].upper, transcript, methods


def _expected_result(
    contract: dict[str, Any],
    registry: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, int], dict[str, int]]:
    _require(
        contract["intrinsic_exactness_correction_contract_id"] == CONTRACT_ID,
        "C1 contract ID differs",
    )
    cases = contract["ordered_intrinsic_case_records"]
    _require(type(cases) is list and len(cases) == CASE_COUNT, "case count differs")
    languages = _index(registry["text_language_catalog"], "text_language_id", "text languages")
    dfas = _index(registry["ascii_dfa_catalog"], "ascii_dfa_id", "ASCII DFAs")
    profiles = _index(
        registry["identifier_profile_catalog"],
        "unicode_identifier_profile_id",
        "Unicode profiles",
    )
    rows: list[dict[str, Any]] = []
    method_census: dict[str, int] = {}
    derivation_census: dict[str, int] = {}
    total_steps = 0
    for position, case in enumerate(cases, 1):
        _require(case["case_position"] == position, "case order differs")
        oracle = CaseOracle(case, languages, dfas, profiles)
        upper, transcript, methods = oracle.complete()
        total_steps += len(transcript)
        for step in transcript:
            kind = step["derivation_kind"]
            derivation_census[kind] = derivation_census.get(kind, 0) + 1
        for method in methods:
            method_census[method] = method_census.get(method, 0) + 1
        payload = {
            "case_position": position,
            "intrinsic_correction_case_id": case["intrinsic_correction_case_id"],
            "case_execution_record_id": case["case_execution_record_id"],
            "logical_count_plan_id": case["logical_count_plan_id"],
            "root_type_name": case["root_type_name"],
            "legal_domain_upper_octets": upper,
            "proof_status": "PROVED_LEGAL_DOMAIN_SUPERSET",
            "ordered_proof_methods": methods,
            "proof_step_count": len(transcript),
            "proof_step_transcript_sha256": _sha256(_canonical_bytes(transcript)),
            "attainer_source_or_output_read": False,
        }
        rows.append({**payload, "upper_case_record_id": _semantic_id(CASE_DOMAIN, payload)})
    _require(total_steps == PROOF_STEP_COUNT, "proof-step count differs")
    _require(derivation_census == EXPECTED_DERIVATION_CENSUS, "derivation census differs")
    _require(tuple(sorted(method_census)) == PROOF_METHODS, "proof-method coverage differs")
    payload = {
        "canonicalization_version": contract["canonicalization_version"],
        "measurement_schema_version": contract["measurement_schema_version"],
        "result_version": RESULT_VERSION,
        "packet": PACKET,
        "source_freeze_id": FREEZE_ID,
        "source_sha256": UPPER_SOURCE_SHA256,
        "output_schema_id": UPPER_SCHEMA_ID,
        "intrinsic_exactness_correction_contract_id": CONTRACT_ID,
        "case_count": CASE_COUNT,
        "ordered_case_upper_records": rows,
        "ordered_case_upper_records_sha256": _sha256(_canonical_bytes(rows)),
        "proof_method_case_census": dict(sorted(method_census.items())),
        "exactness_claimed": False,
        "attainer_channel_consumed": False,
        "formal_stage1_state": "NO-GO",
        "next_bounded_packet": NEXT_PACKET,
    }
    result = {**payload, "upper_channel_result_id": _semantic_id(RESULT_DOMAIN, payload)}
    return result, dict(sorted(method_census.items())), dict(sorted(derivation_census.items()))


def verify(
    repository_root: pathlib.Path | str,
    result_raw: bytes | None = None,
) -> dict[str, Any]:
    root = pathlib.Path(repository_root).resolve()
    contract_raw, contract = _read_pinned(
        root, CONTRACT_PATH, CONTRACT_OCTETS, CONTRACT_SHA256, "C1 contract"
    )
    registry_raw, registry = _read_pinned(
        root, REGISTRY_PATH, REGISTRY_OCTETS, REGISTRY_SHA256, "structural registry"
    )
    freeze_raw, freeze = _read_pinned(
        root, FREEZE_PATH, FREEZE_OCTETS, FREEZE_SHA256, "C2-S freeze"
    )
    schema_raw, schema = _read_pinned(
        root, UPPER_SCHEMA_PATH, UPPER_SCHEMA_OCTETS, UPPER_SCHEMA_SHA256, "upper schema"
    )
    source_raw = _read_regular(root, UPPER_SOURCE_PATH, "upper source")
    _validate_source(source_raw)
    _validate_schema(schema)
    _validate_freeze(freeze)
    if result_raw is None:
        result_raw = _read_regular(root, UPPER_RESULT_PATH, "upper result")
    _require(len(result_raw) < 2_097_152, "upper result exceeds its frozen projection")
    result = _strict_load(result_raw, "upper result")
    _require(result_raw == _pretty_bytes(result), "upper result encoding differs")
    _require(set(result) == set(EXPECTED_ROOT_MEMBERS), "upper root members differ")
    for row in result["ordered_case_upper_records"]:
        _require(type(row) is dict, "upper case row differs")
        _require(set(row) == set(EXPECTED_CASE_MEMBERS), "upper case members differ")
    expected, method_census, derivation_census = _expected_result(contract, registry)
    _require(result == expected, "upper result differs from independent reconstruction")
    upper_values = [row["legal_domain_upper_octets"] for row in result["ordered_case_upper_records"]]
    execution_inputs = (
        len(contract_raw)
        + len(registry_raw)
        + len(freeze_raw)
        + len(schema_raw)
        + len(source_raw)
    )
    _require(execution_inputs < 67_108_864, "C2-U input F0 differs")
    payload = {
        "verification_version": REPORT_VERSION,
        "packet": PACKET,
        "source_freeze_id": FREEZE_ID,
        "upper_channel_result_id": result["upper_channel_result_id"],
        "upper_result_raw_octets": len(result_raw),
        "upper_result_raw_sha256": _sha256(result_raw),
        "upper_source_sha256": UPPER_SOURCE_SHA256,
        "upper_output_schema_id": UPPER_SCHEMA_ID,
        "intrinsic_exactness_correction_contract_id": CONTRACT_ID,
        "case_count": CASE_COUNT,
        "proof_step_count": PROOF_STEP_COUNT,
        "derivation_kind_census": derivation_census,
        "proof_method_case_census": method_census,
        "legal_domain_upper_minimum_octets": min(upper_values),
        "legal_domain_upper_maximum_octets": max(upper_values),
        "legal_domain_upper_vector_sha256": _sha256(_canonical_bytes(upper_values)),
        "upper_case_record_id_vector_sha256": _sha256(
            _canonical_bytes([row["upper_case_record_id"] for row in result["ordered_case_upper_records"]])
        ),
        "attainer_source_or_output_read_true_case_count": sum(
            bool(row["attainer_source_or_output_read"])
            for row in result["ordered_case_upper_records"]
        ),
        "attainer_channel_consumed": result["attainer_channel_consumed"],
        "exactness_claimed": result["exactness_claimed"],
        "execution_pinned_input_file_count": 5,
        "execution_pinned_input_octets": execution_inputs,
        "official_output_file_count": 1,
        "formal_stage1_state": "NO-GO",
        "next_bounded_packet": NEXT_PACKET,
    }
    return {**payload, "upper_channel_acceptance_report_id": _semantic_id(REPORT_DOMAIN, payload)}


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository_root")
    parser.add_argument("--result")
    parser.add_argument("--output")
    arguments = parser.parse_args(argv)
    result_raw = pathlib.Path(arguments.result).read_bytes() if arguments.result else None
    report = verify(arguments.repository_root, result_raw)
    raw = _pretty_bytes(report)
    if arguments.output:
        pathlib.Path(arguments.output).write_bytes(raw)
    else:
        sys.stdout.buffer.write(raw)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(_main(sys.argv[1:]))
    except (ReviewFailure, OSError, KeyError, TypeError, ValueError) as error:
        print(f"RAW_V8_STEP2_INTRINSIC_UPPER_REVIEW_REJECT: {error}", file=sys.stderr)
        raise SystemExit(1) from None

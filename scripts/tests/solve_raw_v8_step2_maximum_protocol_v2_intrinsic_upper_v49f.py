#!/usr/bin/env python3
"""Standalone C2-U legal-domain upper solver frozen by A4-R475-V1-C2-S.

This source is intentionally not imported by the attainer or the source-freeze
reviewer.  It consumes only the byte-pinned correction contract, structural
registry, its own output schema, and the common source-freeze manifest.  The
program constructs proof-carrying superset bounds; it never reads a witness or
an attainer result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import sys
from typing import Any, Final, NoReturn

SOURCE_MARKER: Final = "A4_R475_V1_C2_U_STANDALONE_LEGAL_UPPER_SOLVER_V1"
PACKET: Final = "A4-R475-V1-C2-U"
CHANNEL: Final = "LEGAL_UPPER"
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

CONTRACT_RELATIVE_PATH: Final = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_correction_contract_v49f.json"
)
CONTRACT_OCTETS: Final = 5_436_266
CONTRACT_SHA256: Final = (
    "6245595b759cec6cdecd88292f105dac938f5c69ae92f90ae0365bd032180e14"
)
REGISTRY_RELATIVE_PATH: Final = (
    "scripts/tests/raw_v8_step2_external_schema_v2_structural_registry_v49f.json"
)
REGISTRY_OCTETS: Final = 1_469_663
REGISTRY_SHA256: Final = (
    "9160297ff316c5931737c92f8b359f0a1e2ec22f0aa996ef3b09cf830dc96bf3"
)
SCHEMA_RELATIVE_PATH: Final = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_upper_result_schema_v49f.json"
)
FREEZE_RELATIVE_PATH: Final = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_dual_source_freeze_v49f.json"
)
OUTPUT_RELATIVE_PATH: Final = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_upper_channel_result_v49f.json"
)

CASE_COUNT: Final = 66
SAFE_INTEGER_MAXIMUM: Final = 9_007_199_254_740_991
U128_MAXIMUM: Final = (1 << 128) - 1
SUPPORTED_DERIVATION_KINDS: Final = frozenset(
    {
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
    }
)
SUPPORTED_PROOF_METHODS: Final = frozenset(
    {
        "FINITE_ENUMERATION",
        "CLOSED_BUILTIN_FORMULA",
        "ASCII_DFA_DYNAMIC_PROGRAMMING",
        "PINNED_UNICODE_PROFILE_PROGRAM",
        "RULE_AWARE_COMPOSITION",
        "CODEC_INTERSECTION",
    }
)


class UpperFailure(RuntimeError):
    """Stable fail-closed rejection from the isolated upper channel."""


def _reject(message: str) -> NoReturn:
    raise UpperFailure(str(message).replace("\n", " ")[:768])


def _require(condition: bool, message: str) -> None:
    if not condition:
        _reject(message)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _u128(value: Any, label: str) -> int:
    _require(_is_int(value) and 0 <= value <= U128_MAXIMUM, f"{label} differs")
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
        _reject(f"canonical JSON rejected: {error}")


def _pretty_bytes(value: Any) -> bytes:
    try:
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
    except (TypeError, ValueError, UnicodeError) as error:
        _reject(f"pretty JSON rejected: {error}")


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


def _reject_float(value: str) -> NoReturn:
    _reject(f"floating JSON number is forbidden: {value}")


def _strict_load(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_duplicate_guard,
            parse_float=_reject_float,
            parse_constant=_reject_float,
        )
    except (json.JSONDecodeError, UnicodeError) as error:
        _reject(f"{label} JSON rejected: {error}")
    _require(type(value) is dict, f"{label} root differs")
    return value


def _load_pinned(
    root: pathlib.Path,
    relative_path: str,
    expected_octets: int | None,
    expected_sha256: str | None,
    label: str,
) -> tuple[bytes, dict[str, Any]]:
    path = root / relative_path
    _require(path.is_file() and not path.is_symlink(), f"{label} path differs")
    raw = path.read_bytes()
    if expected_octets is not None:
        _require(len(raw) == expected_octets, f"{label} octets differ")
    if expected_sha256 is not None:
        _require(_sha256(raw) == expected_sha256, f"{label} hash differs")
    return raw, _strict_load(raw, label)


def _index(rows: Any, key_name: str, label: str) -> dict[Any, dict[str, Any]]:
    _require(type(rows) is list, f"{label} is not an array")
    result: dict[Any, dict[str, Any]] = {}
    for row in rows:
        _require(type(row) is dict and key_name in row, f"{label} row differs")
        key = row[key_name]
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


def _ascii_json_weight(byte: int) -> int:
    _require(0 <= byte <= 0x7F, "ASCII transition byte differs")
    if byte < 0x20:
        return 6
    if byte in {0x22, 0x5C}:
        return 2
    return 1


def _dfa_upper(dfa: dict[str, Any]) -> int:
    maximum = _u128(dfa["maximum_octets"], "DFA maximum")
    minimum = _u128(dfa["minimum_octets"], "DFA minimum")
    _require(minimum <= maximum <= 1_048_576, "DFA length interval differs")
    start = dfa["start_state"]
    accepting = set(dfa["ordered_accepting_states"])
    transitions: dict[int, list[tuple[int, int]]] = {}
    for row in dfa["ordered_transition_rows"]:
        source = row["source_state"]
        target = row["target_state"]
        lower = row["inclusive_byte_minimum"]
        upper = row["inclusive_byte_maximum"]
        _require(
            all(_is_int(value) for value in (source, target, lower, upper))
            and 0 <= lower <= upper <= 0x7F,
            "DFA transition differs",
        )
        weight = max(_ascii_json_weight(byte) for byte in range(lower, upper + 1))
        transitions.setdefault(source, []).append((target, weight))
    current: dict[int, int] = {start: 0}
    best: int | None = None
    for length in range(maximum + 1):
        if length >= minimum:
            candidates = [weight for state, weight in current.items() if state in accepting]
            if candidates:
                candidate = max(candidates)
                best = candidate if best is None else max(best, candidate)
        if length == maximum:
            break
        following: dict[int, int] = {}
        for state, accumulated in current.items():
            for target, weight in transitions.get(state, []):
                following[target] = max(following.get(target, -1), accumulated + weight)
        current = following
        _require(bool(current), "DFA has no path through its maximum search interval")
    _require(best is not None, "DFA accepts no string in its pinned interval")
    return 2 + best


def _language_upper(
    language: dict[str, Any],
    dfas: dict[str, dict[str, Any]],
    profiles: dict[str, dict[str, Any]],
    ceiling: int,
) -> tuple[int, str]:
    kind = language["language_kind"]
    if kind in {"LITERAL", "ENUM"}:
        literals = language["ordered_literals"]
        _require(type(literals) is list and literals, "finite language is empty")
        return max(len(_canonical_bytes(value)) for value in literals), "FINITE_ENUMERATION"
    if kind == "BUILTIN":
        built_in = language["built_in_language_kind"]
        if built_in == "LOWERCASE_SHA256":
            return 66, "CLOSED_BUILTIN_FORMULA"
        if built_in == "UINT128_DECIMAL":
            _require(language["decimal_maximum"] == str(U128_MAXIMUM), "uint128 maximum differs")
            return 41, "CLOSED_BUILTIN_FORMULA"
        if built_in == "RFC3339_UTC":
            return 29, "CLOSED_BUILTIN_FORMULA"
        if built_in == "CANONICAL_BASE64":
            decoded = _u128(language["maximum_decoded_octets"], "base64 maximum")
            return min(ceiling, 2 + 4 * ((decoded + 2) // 3)), "CLOSED_BUILTIN_FORMULA"
        if built_in == "RAW_CANONICAL_JSON_STRING":
            return ceiling, "CLOSED_BUILTIN_FORMULA"
        _reject(f"unsupported built-in language: {built_in}")
    if kind == "ASCII_DFA":
        dfa = dfas.get(language["ascii_dfa_id"])
        _require(dfa is not None, "ASCII DFA is unresolved")
        return min(ceiling, _dfa_upper(dfa)), "ASCII_DFA_DYNAMIC_PROGRAMMING"
    if kind == "UNICODE_IDENTIFIER":
        profile = profiles.get(language["unicode_identifier_profile_id"])
        _require(profile is not None, "Unicode profile is unresolved")
        utf8 = _u128(profile["maximum_utf8_octets"], "Unicode UTF-8 maximum")
        scalars = _u128(profile["maximum_scalar_values"], "Unicode scalar maximum")
        return min(ceiling, 2 + utf8 + scalars), "PINNED_UNICODE_PROFILE_PROGRAM"
    _reject(f"unsupported text language: {kind}")


def _derive_case(
    case: dict[str, Any],
    languages: dict[str, dict[str, Any]],
    dfas: dict[str, dict[str, Any]],
    profiles: dict[str, dict[str, Any]],
) -> tuple[int, list[dict[str, Any]], set[str]]:
    cells: list[tuple[int, int]] = []
    proof_steps: list[dict[str, Any]] = []
    methods: set[str] = {"RULE_AWARE_COMPOSITION"}
    steps = case["ordered_step_contract_records"]
    _require(type(steps) is list and steps, "case step program is empty")
    for position, step in enumerate(steps, 1):
        _require(step["step_position"] == position, "step position differs")
        kind = step["derivation_kind"]
        _require(kind in SUPPORTED_DERIVATION_KINDS, f"unsupported derivation kind: {kind}")
        children = step["ordered_child_step_positions"]
        _require(
            type(children) is list
            and len(children) == len(set(children))
            and all(_is_int(child) and 1 <= child < position for child in children),
            "postorder child relation differs",
        )
        child_cells = [cells[child - 1] for child in children]
        parameters = step["recurrence_parameters"]
        ceiling = 524_288
        method = "RULE_AWARE_COMPOSITION"
        if kind == "EXACT_BOOLEAN":
            literal = parameters["boolean_literal"]
            domain = [False, True] if literal is None else [literal]
            _require(all(type(value) is bool for value in domain), "boolean domain differs")
            sizes = [len(_canonical_bytes(value)) for value in domain]
            cell = (min(sizes), max(sizes))
            method = "FINITE_ENUMERATION"
        elif kind == "SAFE_INTEGER_BAND":
            lower = parameters["integer_minimum"]
            upper = parameters["integer_maximum"]
            _require(
                _is_int(lower)
                and _is_int(upper)
                and -SAFE_INTEGER_MAXIMUM <= lower <= upper <= SAFE_INTEGER_MAXIMUM,
                "safe-integer interval differs",
            )
            nearest = 0 if lower <= 0 <= upper else lower if lower > 0 else upper
            cell = (len(str(nearest)), max(len(str(lower)), len(str(upper))))
            method = "CLOSED_BUILTIN_FORMULA"
        elif kind == "TEXT_FINITE":
            literals = parameters["ordered_literals"]
            _require(type(literals) is list and literals and all(type(x) is str for x in literals), "finite text differs")
            sizes = [len(_canonical_bytes(value)) for value in literals]
            cell = (min(sizes), max(sizes))
            method = "FINITE_ENUMERATION"
        elif kind == "TEXT_BUILTIN_BOUNDED":
            cell = (
                _u128(parameters["minimum_canonical_octets"], "text lower"),
                _u128(parameters["maximum_canonical_octets"], "text upper"),
            )
            method = "CLOSED_BUILTIN_FORMULA"
        elif kind == "TEXT_BOUNDED_LANGUAGE":
            language = languages.get(parameters["text_language_id"])
            _require(language is not None, "bounded language is unresolved")
            upper, method = _language_upper(language, dfas, profiles, ceiling)
            cell = (2, upper)
        elif kind == "OBJECT_REFERENCE":
            _require(len(child_cells) == 1, "object-reference arity differs")
            cell = child_cells[0]
        elif kind == "NULLABLE_BRANCH":
            _require(len(child_cells) == 1, "nullable arity differs")
            cell = (min(4, child_cells[0][0]), max(4, child_cells[0][1]))
        elif kind == "ASSOCIATIVE_HOMOGENEOUS_RUN_BATCH":
            _require(len(child_cells) == 1, "array arity differs")
            minimum = _u128(parameters["minimum_items"], "array minimum")
            maximum = _u128(parameters["maximum_items"], "array maximum")
            _require(minimum <= maximum, "array cardinality differs")
            child = child_cells[0]
            lower = 2 + minimum * child[0] + max(0, minimum - 1)
            upper = 2 + maximum * child[1] + max(0, maximum - 1)
            cell = (lower, min(upper, ceiling))
        elif kind == "RECORD_MEMBER_FOLD":
            rows = parameters["ordered_member_records"]
            _require(type(rows) is list and len(rows) == len(children), "record members differ")
            syntax = 2 + max(0, len(rows) - 1)
            for member_position, row in enumerate(rows, 1):
                _require(
                    row["member_position"] == member_position
                    and row["child_step_position"] == children[member_position - 1],
                    "record member order differs",
                )
                name_size = len(_canonical_bytes(row["member_name"]))
                _require(row["member_name_canonical_octets"] == name_size, "record member-name size differs")
                syntax += name_size + 1
            _require(parameters["record_syntax_octets_excluding_child_values"] == syntax, "record syntax differs")
            lower = _checked_sum([syntax] + [cell[0] for cell in child_cells], "record lower")
            upper = _checked_sum([syntax] + [cell[1] for cell in child_cells], "record upper")
            cell = (lower, min(upper, ceiling))
        elif kind == "TAGGED_UNION_BRANCH":
            _require(bool(child_cells), "union is empty")
            cell = (min(child[0] for child in child_cells), max(child[1] for child in child_cells))
        elif kind == "CODEC_INTERSECTION":
            _require(len(child_cells) == 1, "codec arity differs")
            payload_ceiling = ceiling
            coordinates = parameters["ordered_codec_coordinate_records"]
            _require(type(coordinates) is list and coordinates, "codec coordinates differ")
            for coordinate_position, coordinate in enumerate(coordinates, 1):
                _require(coordinate["coordinate_position"] == coordinate_position, "codec coordinate order differs")
                relation = coordinate["codec_byte_bound_relation"]
                limit = _u128(coordinate["codec_octet_limit"], "codec limit")
                _require(relation in {"LE", "LT"}, "codec relation differs")
                effective = limit - int(relation == "LT")
                sibling = _u128(coordinate["minimum_sibling_and_syntax_octets"], "codec sibling")
                derived = 0 if sibling > effective else effective - sibling
                _require(coordinate["derived_payload_octet_ceiling"] == derived, "codec residual differs")
                payload_ceiling = min(payload_ceiling, derived)
            _require(child_cells[0][0] <= payload_ceiling, "codec intersection is empty")
            cell = (child_cells[0][0], min(child_cells[0][1], payload_ceiling))
            method = "CODEC_INTERSECTION"
        else:
            _reject(f"unhandled derivation kind: {kind}")
        _require(0 <= cell[0] <= cell[1] <= ceiling, "derived cell differs")
        methods.add(method)
        proof_payload = {
            "step_position": position,
            "correction_step_id": step["correction_step_id"],
            "derivation_kind": kind,
            "ordered_child_step_positions": children,
            "ordered_dependency_references": step["ordered_dependency_references"],
            "lower_canonical_octets": cell[0],
            "legal_domain_upper_octets": cell[1],
            "proof_method": method,
            "predicate_treatment": "INTERSECTION_ONLY_NEVER_DOMAIN_EXPANSION",
        }
        proof_steps.append({**proof_payload, "proof_step_id": _semantic_id("RiskYieldMMIntrinsicUpperProofStepV1", proof_payload)})
        cells.append(cell)
    _require(case["root_step_position"] == len(cells), "case root position differs")
    return cells[-1][1], proof_steps, methods


def _validate_freeze(
    root: pathlib.Path,
    freeze: dict[str, Any],
    schema_raw: bytes,
    schema: dict[str, Any],
) -> str:
    payload = {key: value for key, value in freeze.items() if key != "dual_source_freeze_id"}
    freeze_id = _semantic_id(freeze["identity_domain"], payload)
    _require(freeze["dual_source_freeze_id"] == freeze_id, "source-freeze identity differs")
    records = freeze["ordered_channel_source_records"]
    own = next((row for row in records if row["channel"] == CHANNEL), None)
    _require(own is not None, "upper source record is absent")
    source_raw = pathlib.Path(__file__).read_bytes()
    _require(
        own["relative_path"] == pathlib.Path(__file__).resolve().relative_to(root.resolve()).as_posix()
        and own["raw_octets"] == len(source_raw)
        and own["raw_sha256"] == _sha256(source_raw),
        "upper source identity differs",
    )
    _require(
        own["output_schema_relative_path"] == SCHEMA_RELATIVE_PATH
        and own["output_schema_raw_octets"] == len(schema_raw)
        and own["output_schema_raw_sha256"] == _sha256(schema_raw)
        and own["output_schema_id"] == schema["output_schema_id"],
        "upper output-schema identity differs",
    )
    return freeze_id


def solve(repository_root: pathlib.Path | str) -> dict[str, Any]:
    root = pathlib.Path(repository_root).resolve()
    _, contract = _load_pinned(root, CONTRACT_RELATIVE_PATH, CONTRACT_OCTETS, CONTRACT_SHA256, "correction contract")
    _, registry = _load_pinned(root, REGISTRY_RELATIVE_PATH, REGISTRY_OCTETS, REGISTRY_SHA256, "structural registry")
    schema_raw, schema = _load_pinned(root, SCHEMA_RELATIVE_PATH, None, None, "upper output schema")
    _, freeze = _load_pinned(root, FREEZE_RELATIVE_PATH, None, None, "source-freeze manifest")
    freeze_id = _validate_freeze(root, freeze, schema_raw, schema)
    languages = _index(registry["text_language_catalog"], "text_language_id", "text language")
    dfas = _index(registry["ascii_dfa_catalog"], "ascii_dfa_id", "ASCII DFA")
    profiles = _index(registry["identifier_profile_catalog"], "unicode_identifier_profile_id", "identifier profile")
    cases = contract["ordered_intrinsic_case_records"]
    _require(len(cases) == CASE_COUNT, "intrinsic case count differs")
    result_rows: list[dict[str, Any]] = []
    method_census: dict[str, int] = {}
    for position, case in enumerate(cases, 1):
        _require(case["case_position"] == position, "intrinsic case order differs")
        upper, proof_steps, methods = _derive_case(case, languages, dfas, profiles)
        for method in methods:
            method_census[method] = method_census.get(method, 0) + 1
        proof_root = _sha256(_canonical_bytes(proof_steps))
        payload = {
            "case_position": position,
            "intrinsic_correction_case_id": case["intrinsic_correction_case_id"],
            "case_execution_record_id": case["case_execution_record_id"],
            "logical_count_plan_id": case["logical_count_plan_id"],
            "root_type_name": case["root_type_name"],
            "legal_domain_upper_octets": upper,
            "proof_status": "PROVED_LEGAL_DOMAIN_SUPERSET",
            "ordered_proof_methods": sorted(methods),
            "proof_step_count": len(proof_steps),
            "proof_step_transcript_sha256": proof_root,
            "attainer_source_or_output_read": False,
        }
        result_rows.append({**payload, "upper_case_record_id": _semantic_id(CASE_DOMAIN, payload)})
    _require(SUPPORTED_PROOF_METHODS <= set(method_census), "required proof-method coverage is incomplete")
    payload = {
        "canonicalization_version": contract["canonicalization_version"],
        "measurement_schema_version": contract["measurement_schema_version"],
        "result_version": RESULT_VERSION,
        "packet": PACKET,
        "source_freeze_id": freeze_id,
        "source_sha256": _sha256(pathlib.Path(__file__).read_bytes()),
        "output_schema_id": schema["output_schema_id"],
        "intrinsic_exactness_correction_contract_id": contract["intrinsic_exactness_correction_contract_id"],
        "case_count": CASE_COUNT,
        "ordered_case_upper_records": result_rows,
        "ordered_case_upper_records_sha256": _sha256(_canonical_bytes(result_rows)),
        "proof_method_case_census": dict(sorted(method_census.items())),
        "exactness_claimed": False,
        "attainer_channel_consumed": False,
        "formal_stage1_state": "NO-GO",
        "next_bounded_packet": "A4-R475-V1-C2-A",
    }
    result = {**payload, "upper_channel_result_id": _semantic_id(RESULT_DOMAIN, payload)}
    expected_members = schema["root_record_schema"]["ordered_member_names"]
    _require(set(result) == set(expected_members), "upper result schema differs")
    return result


def _publish_exclusive(path: pathlib.Path, raw: bytes) -> None:
    _require(not path.exists() and not path.is_symlink(), "upper result already exists")
    temporary = path.with_name(f".{path.name}.c2u.tmp")
    _require(not temporary.exists() and not temporary.is_symlink(), "upper temporary path exists")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
        temporary.unlink()
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except BaseException:
        if temporary.exists() and not temporary.is_symlink():
            temporary.unlink()
        raise


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", required=True)
    arguments = parser.parse_args(argv)
    root = pathlib.Path(arguments.repository_root).resolve()
    result = solve(root)
    _publish_exclusive(root / OUTPUT_RELATIVE_PATH, _pretty_bytes(result))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(_main(sys.argv[1:]))
    except (UpperFailure, OSError, ValueError, KeyError, TypeError) as error:
        print(f"RAW_V8_STEP2_INTRINSIC_UPPER_REJECT: {error}", file=sys.stderr)
        raise SystemExit(1) from None

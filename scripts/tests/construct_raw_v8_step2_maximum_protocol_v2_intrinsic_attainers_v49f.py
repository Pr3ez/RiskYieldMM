#!/usr/bin/env python3
"""Standalone C2-A constructor frozen by A4-R475-V1-C2-S.

Candidate selection is implemented locally from the correction contract and
the structural registry.  The separately pinned schema runtime is loaded only
after each complete candidate has been selected, solely to perform the final
P1 legality check.  This program has no path, import, argument, or data channel
through which it can consume the other correction result.
"""

from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import os
import pathlib
import sys
import types
from typing import Any, Final, NoReturn

SOURCE_MARKER: Final = "A4_R475_V1_C2_A_STANDALONE_P1_ATTAINER_CONSTRUCTOR_V1"
PACKET: Final = "A4-R475-V1-C2-A"
CHANNEL: Final = "P1_LEGAL_ATTAINER"
RESULT_VERSION: Final = (
    "riskyieldmm.raw_v8_step2.maximum_protocol_v2."
    "intrinsic_p1_attainer_result.v1"
)
RESULT_DOMAIN: Final = (
    "RiskYieldMMRawV8Step2MaximumProtocolV2IntrinsicP1AttainerResultV1"
)
CASE_DOMAIN: Final = (
    "RiskYieldMMRawV8Step2MaximumProtocolV2IntrinsicP1AttainerCaseV1"
)
SHARD_DOMAIN: Final = (
    "RiskYieldMMRawV8Step2MaximumProtocolV2IntrinsicWitnessShardV1"
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
LITERAL_RELATIVE_PATH: Final = (
    "scripts/tests/raw_v8_step2_external_schema_v2_rule_literal_authority_v49f.json"
)
LITERAL_OCTETS: Final = 484_301
LITERAL_SHA256: Final = (
    "aba3461059367904734e2eb9ae404787b9aab5ed4c3fbcd292925a364926cce2"
)
RUNTIME_RELATIVE_PATH: Final = (
    "scripts/tests/validate_raw_v8_step2_external_schema_v2_rule_runtime_v49f.py"
)
RUNTIME_OCTETS: Final = 249_268
RUNTIME_SHA256: Final = (
    "47aa90d897e8dbae5e244b7c04cbd82dfe036b0292d36ef0f5552c868627ab22"
)
SCHEMA_RELATIVE_PATH: Final = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_attainer_result_schema_v49f.json"
)
FREEZE_RELATIVE_PATH: Final = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_dual_source_freeze_v49f.json"
)
ROOT_OUTPUT_RELATIVE_PATH: Final = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_attainer_channel_result_v49f.json"
)
SHARD_OUTPUT_RELATIVE_PATHS: Final = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_intrinsic_attainer_witness_shard_1_v49f.json",
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_intrinsic_attainer_witness_shard_2_v49f.json",
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_intrinsic_attainer_witness_shard_3_v49f.json",
)
SHARD_CASE_RANGES: Final = ((1, 22), (23, 44), (45, 66))
CASE_COUNT: Final = 66
MAXIMUM_CASE_CANONICAL_OCTETS: Final = 524_288
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


class AttainerFailure(RuntimeError):
    """Stable fail-closed rejection from the isolated construction channel."""


def _reject(message: str) -> NoReturn:
    raise AttainerFailure(str(message).replace("\n", " ")[:768])


def _require(condition: bool, message: str) -> None:
    if not condition:
        _reject(message)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


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


def _versioned_semantic_id(
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


def _candidate_key(value: Any) -> tuple[int, bytes]:
    raw = _canonical_bytes(value)
    return len(raw), raw


def _longest(values: list[Any]) -> Any:
    _require(bool(values), "candidate domain is empty")
    return copy.deepcopy(max(values, key=_candidate_key))


def _transition_bytes(row: dict[str, Any]) -> list[int]:
    lower = row["inclusive_byte_minimum"]
    maximum = row["inclusive_byte_maximum"]
    _require(
        _is_int(lower) and _is_int(maximum) and 0 <= lower <= maximum <= 0x7F,
        "DFA transition interval differs",
    )
    values = list(range(lower, maximum + 1))
    values.sort(key=lambda byte: (len(_canonical_bytes(chr(byte))), byte), reverse=True)
    return values


def _longest_dfa_word(dfa: dict[str, Any]) -> str:
    minimum = dfa["minimum_octets"]
    maximum = dfa["maximum_octets"]
    _require(_is_int(minimum) and _is_int(maximum) and 0 <= minimum <= maximum <= 1_048_576, "DFA bounds differ")
    transitions: dict[int, list[tuple[int, int]]] = {}
    for row in dfa["ordered_transition_rows"]:
        source = row["source_state"]
        target = row["target_state"]
        _require(_is_int(source) and _is_int(target), "DFA state differs")
        for byte in _transition_bytes(row):
            transitions.setdefault(source, []).append((target, byte))
    current: dict[int, bytes] = {dfa["start_state"]: b""}
    accepting = set(dfa["ordered_accepting_states"])
    winners: list[bytes] = []
    for length in range(maximum + 1):
        if length >= minimum:
            winners.extend(word for state, word in current.items() if state in accepting)
        if length == maximum:
            break
        following: dict[int, bytes] = {}
        for state, prefix in current.items():
            for target, byte in transitions.get(state, []):
                candidate = prefix + bytes([byte])
                previous = following.get(target)
                if previous is None or _candidate_key(candidate.decode("ascii")) > _candidate_key(previous.decode("ascii")):
                    following[target] = candidate
        current = following
        _require(bool(current), "DFA path set became empty")
    _require(bool(winners), "DFA accepts no pinned-length word")
    return max((word.decode("ascii") for word in winners), key=_candidate_key)


def _text_candidate(
    language: dict[str, Any],
    dfas: dict[str, dict[str, Any]],
    profiles: dict[str, dict[str, Any]],
) -> str:
    kind = language["language_kind"]
    if kind in {"LITERAL", "ENUM"}:
        return _longest(language["ordered_literals"])
    if kind == "ASCII_DFA":
        dfa = dfas.get(language["ascii_dfa_id"])
        _require(dfa is not None, "ASCII DFA is unresolved")
        return _longest_dfa_word(dfa)
    if kind == "UNICODE_IDENTIFIER":
        profile = profiles.get(language["unicode_identifier_profile_id"])
        _require(profile is not None, "Unicode profile is unresolved")
        count = min(profile["maximum_scalar_values"], profile["maximum_utf8_octets"])
        _require(_is_int(count) and count > 0, "Unicode profile maximum differs")
        return "z" * count
    _require(kind == "BUILTIN", f"unsupported text language: {kind}")
    built_in = language["built_in_language_kind"]
    if built_in == "LOWERCASE_SHA256":
        return "f" * 64
    if built_in == "UINT128_DECIMAL":
        return language["decimal_maximum"]
    if built_in == "RFC3339_UTC":
        return "9999-12-31T23:59:59.999999Z"
    if built_in == "CANONICAL_BASE64":
        maximum = language["maximum_decoded_octets"]
        _require(_is_int(maximum) and maximum >= 0, "base64 decoded maximum differs")
        return base64.b64encode(b"\xff" * maximum).decode("ascii")
    if built_in == "RAW_CANONICAL_JSON_STRING":
        _require(
            language.get("maximum_utf8_octets") is None,
            "raw-string authority unexpectedly carries a leaf-local maximum",
        )
        return "z" * (MAXIMUM_CASE_CANONICAL_OCTETS - 2)
    _reject(f"unsupported built-in language: {built_in}")


def _synchronize_references(value: Any) -> None:
    if type(value) is list:
        for child in value:
            _synchronize_references(child)
        return
    if type(value) is not dict:
        return
    for child in value.values():
        _synchronize_references(child)
    for name in list(value):
        if not name.endswith("_id"):
            continue
        sibling = value.get(name[:-3])
        if type(sibling) is dict:
            identity_members = [key for key in sibling if key.endswith("_id") and type(sibling[key]) is str and len(sibling[key]) == 64]
            if len(identity_members) == 1:
                value[name] = sibling[identity_members[0]]


def _reseal_record(
    value: dict[str, Any],
    descriptor: dict[str, Any] | None,
    canonicalization_version: str,
    schema_version: str,
) -> None:
    if descriptor is None or descriptor.get("identity_field") is None:
        return
    identity_field = descriptor["identity_field"]
    order = descriptor["identity_payload_member_order"]
    _require(type(order) is list and all(member in value for member in order), "identity payload differs")
    payload = {member: value[member] for member in order}
    value[identity_field] = _versioned_semantic_id(
        canonicalization_version,
        schema_version,
        descriptor["described_record_domain"],
        payload,
    )


def _distinct_variants(value: Any, count: int) -> list[Any]:
    _require(_is_int(count) and count >= 0, "variant count differs")
    if count == 0:
        return []
    if type(value) is str and value:
        variants = []
        for ordinal in range(count):
            token = format(ordinal, "x")
            _require(len(token) <= len(value), "string domain is too short for distinct variants")
            variants.append(value[: len(value) - len(token)] + token)
        if len({_canonical_bytes(row) for row in variants}) == count:
            return variants
    if _is_int(value):
        return [value - ordinal for ordinal in range(count)]
    if type(value) is bool and count <= 2:
        return [False, True][:count]
    if type(value) is dict:
        string_members = [name for name, child in value.items() if type(child) is str and child]
        if string_members:
            member = max(string_members, key=lambda name: len(value[name]))
            variants = []
            for ordinal in range(count):
                row = copy.deepcopy(value)
                token = format(ordinal, "x")
                _require(len(token) <= len(row[member]), "record string is too short for distinct variants")
                row[member] = row[member][: len(row[member]) - len(token)] + token
                variants.append(row)
            if len({_canonical_bytes(row) for row in variants}) == count:
                return variants
    if count == 1:
        return [copy.deepcopy(value)]
    _reject("closed distinct array domain could not be constructed")


def _shrink(value: Any, maximum_octets: int) -> Any:
    candidate = copy.deepcopy(value)
    for _ in range(4096):
        raw_size = len(_canonical_bytes(candidate))
        if raw_size <= maximum_octets:
            return candidate
        deficit = raw_size - maximum_octets
        if type(candidate) is str and candidate:
            candidate = candidate[: max(0, len(candidate) - deficit)]
            continue
        if type(candidate) is list and candidate:
            average = max(1, (raw_size - 2) // len(candidate))
            removal_count = min(len(candidate), max(1, (deficit + average) // (average + 1)))
            del candidate[-removal_count:]
            continue
        if type(candidate) is dict:
            shrinkable = [
                (len(_canonical_bytes(child)), name)
                for name, child in candidate.items()
                if (type(child) is str and child) or (type(child) is list and child)
            ]
            _require(bool(shrinkable), "codec-constrained record cannot be reduced")
            _, name = max(shrinkable)
            child = candidate[name]
            if type(child) is str:
                candidate[name] = child[: max(0, len(child) - deficit)]
            else:
                average = max(1, len(_canonical_bytes(child)) // len(child))
                removal_count = min(len(child), max(1, (deficit + average) // (average + 1)))
                candidate[name] = child[:-removal_count]
            continue
        _reject("codec-constrained value cannot be reduced")
    _reject("codec reduction iteration ceiling exceeded")


def _construct_case(
    case: dict[str, Any],
    languages: dict[str, dict[str, Any]],
    dfas: dict[str, dict[str, Any]],
    profiles: dict[str, dict[str, Any]],
    descriptors: dict[str, dict[str, Any]],
    canonicalization_version: str,
    schema_version: str,
) -> tuple[Any, list[dict[str, Any]]]:
    values: list[Any] = []
    trace: list[dict[str, Any]] = []
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
        child_values = [values[child - 1] for child in children]
        parameters = step["recurrence_parameters"]
        if kind == "EXACT_BOOLEAN":
            literal = parameters["boolean_literal"]
            value = False if literal is None else literal
            _require(type(value) is bool, "boolean literal differs")
        elif kind == "SAFE_INTEGER_BAND":
            lower = parameters["integer_minimum"]
            maximum = parameters["integer_maximum"]
            _require(_is_int(lower) and _is_int(maximum) and -SAFE_INTEGER_MAXIMUM <= lower <= maximum <= SAFE_INTEGER_MAXIMUM, "integer interval differs")
            value = max((lower, maximum), key=lambda item: (len(str(item)), item))
        elif kind == "TEXT_FINITE":
            value = _longest(parameters["ordered_literals"])
        elif kind == "TEXT_BUILTIN_BOUNDED":
            built_in = parameters["built_in_language_kind"]
            maximum_size = parameters["maximum_canonical_octets"]
            if built_in == "LOWERCASE_SHA256":
                value = "f" * 64
            elif built_in == "UINT128_DECIMAL":
                value = str(U128_MAXIMUM)
            elif built_in == "RFC3339_UTC":
                value = "9999-12-31T23:59:59.999999Z"
            elif built_in == "CANONICAL_BASE64":
                decoded = max(0, 3 * max(0, maximum_size - 2) // 4)
                value = base64.b64encode(b"\xff" * decoded).decode("ascii")
            elif built_in == "RAW_CANONICAL_JSON_STRING":
                value = "z" * max(0, maximum_size - 2)
            else:
                _reject(f"unsupported bounded built-in: {built_in}")
            _require(len(_canonical_bytes(value)) <= maximum_size, "bounded text candidate exceeds limit")
        elif kind == "TEXT_BOUNDED_LANGUAGE":
            language = languages.get(parameters["text_language_id"])
            _require(language is not None, "bounded language is unresolved")
            value = _text_candidate(language, dfas, profiles)
        elif kind == "OBJECT_REFERENCE":
            _require(len(child_values) == 1, "object-reference arity differs")
            value = copy.deepcopy(child_values[0])
        elif kind == "NULLABLE_BRANCH":
            _require(len(child_values) == 1, "nullable arity differs")
            value = _longest([None, child_values[0]])
        elif kind == "ASSOCIATIVE_HOMOGENEOUS_RUN_BATCH":
            _require(len(child_values) == 1, "array arity differs")
            maximum_count = parameters["maximum_items"]
            minimum_count = parameters["minimum_items"]
            _require(_is_int(maximum_count) and _is_int(minimum_count) and 0 <= minimum_count <= maximum_count, "array cardinality differs")
            item_size = len(_canonical_bytes(child_values[0]))
            byte_fit_count = max(0, (MAXIMUM_CASE_CANONICAL_OCTETS - 1) // (item_size + 1))
            count = min(maximum_count, byte_fit_count)
            item_step = steps[children[0] - 1]
            if item_step["derivation_kind"] == "TEXT_FINITE":
                finite = item_step["recurrence_parameters"]["ordered_literals"]
                distinct = list(dict.fromkeys(finite))
                count = min(count, len(distinct))
                value = [copy.deepcopy(row) for row in distinct[:count]]
            elif item_step["derivation_kind"] == "EXACT_BOOLEAN":
                literal = item_step["recurrence_parameters"]["boolean_literal"]
                domain = [False, True] if literal is None else [literal]
                count = min(count, len(domain))
                value = domain[:count]
            else:
                value = _distinct_variants(child_values[0], count)
            _require(len(value) >= minimum_count, "byte-bounded distinct array domain is empty")
        elif kind == "RECORD_MEMBER_FOLD":
            rows = parameters["ordered_member_records"]
            _require(type(rows) is list and len(rows) == len(child_values), "record members differ")
            value = {}
            for member_position, (row, child) in enumerate(zip(rows, child_values, strict=True), 1):
                _require(row["member_position"] == member_position and row["child_step_position"] == children[member_position - 1], "record member order differs")
                value[row["member_name"]] = copy.deepcopy(child)
            _synchronize_references(value)
            _reseal_record(value, descriptors.get(step.get("type_name")), canonicalization_version, schema_version)
        elif kind == "TAGGED_UNION_BRANCH":
            _require(bool(child_values), "union domain is empty")
            value = _longest(child_values)
        elif kind == "CODEC_INTERSECTION":
            _require(len(child_values) == 1, "codec arity differs")
            payload_limit = MAXIMUM_CASE_CANONICAL_OCTETS
            for coordinate in parameters["ordered_codec_coordinate_records"]:
                payload_limit = min(payload_limit, coordinate["derived_payload_octet_ceiling"])
            value = _shrink(child_values[0], payload_limit)
            if type(value) is dict:
                _synchronize_references(value)
                _reseal_record(value, descriptors.get(step.get("type_name")), canonicalization_version, schema_version)
        else:
            _reject(f"unhandled derivation kind: {kind}")
        raw = _canonical_bytes(value)
        if len(raw) > MAXIMUM_CASE_CANONICAL_OCTETS:
            value = _shrink(value, MAXIMUM_CASE_CANONICAL_OCTETS)
            if type(value) is dict:
                _synchronize_references(value)
                _reseal_record(value, descriptors.get(step.get("type_name")), canonicalization_version, schema_version)
            raw = _canonical_bytes(value)
        _require(len(raw) <= MAXIMUM_CASE_CANONICAL_OCTETS, "candidate exceeds protocol ceiling")
        trace.append(
            {
                "step_position": position,
                "correction_step_id": step["correction_step_id"],
                "derivation_kind": kind,
                "candidate_canonical_octets": len(raw),
                "candidate_canonical_sha256": _sha256(raw),
            }
        )
        values.append(value)
    _require(case["root_step_position"] == len(values), "case root position differs")
    result = values[-1]
    if type(result) is dict:
        _synchronize_references(result)
        _reseal_record(result, descriptors.get(case["root_type_name"]), canonicalization_version, schema_version)
    return result, trace


def _load_runtime(root: pathlib.Path, raw: bytes, path: pathlib.Path) -> types.ModuleType:
    module_name = "_riskyieldmm_intrinsic_c2a_pinned_rule_runtime"
    module = types.ModuleType(module_name)
    module.__file__ = os.fspath(path)
    module.__package__ = ""
    sys.modules[module_name] = module
    try:
        code = compile(raw, os.fspath(path), "exec", dont_inherit=True)
        exec(code, module.__dict__)
        runtime = module.ExternalSchemaV2Runtime.load(root)
        report = runtime.validation_report()
    except Exception as error:
        _reject(f"pinned P1 runtime rejected: {type(error).__name__}: {error}")
    _require(report["total_rule_count"] == 42 and report["unsupported_complex_rule_count"] == 0, "P1 runtime capability differs")
    return module


def _validate_freeze(
    root: pathlib.Path,
    freeze: dict[str, Any],
    schema_raw: bytes,
    schema: dict[str, Any],
) -> str:
    payload = {key: value for key, value in freeze.items() if key != "dual_source_freeze_id"}
    freeze_id = _semantic_id(freeze["identity_domain"], payload)
    _require(freeze["dual_source_freeze_id"] == freeze_id, "source-freeze identity differs")
    own = next((row for row in freeze["ordered_channel_source_records"] if row["channel"] == CHANNEL), None)
    _require(own is not None, "attainer source record is absent")
    source_raw = pathlib.Path(__file__).read_bytes()
    _require(
        own["relative_path"] == pathlib.Path(__file__).resolve().relative_to(root.resolve()).as_posix()
        and own["raw_octets"] == len(source_raw)
        and own["raw_sha256"] == _sha256(source_raw),
        "attainer source identity differs",
    )
    _require(
        own["output_schema_relative_path"] == SCHEMA_RELATIVE_PATH
        and own["output_schema_raw_octets"] == len(schema_raw)
        and own["output_schema_raw_sha256"] == _sha256(schema_raw)
        and own["output_schema_id"] == schema["output_schema_id"],
        "attainer output-schema identity differs",
    )
    return freeze_id


def construct(repository_root: pathlib.Path | str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    root = pathlib.Path(repository_root).resolve()
    _, contract = _load_pinned(root, CONTRACT_RELATIVE_PATH, CONTRACT_OCTETS, CONTRACT_SHA256, "correction contract")
    _, registry = _load_pinned(root, REGISTRY_RELATIVE_PATH, REGISTRY_OCTETS, REGISTRY_SHA256, "structural registry")
    _load_pinned(root, LITERAL_RELATIVE_PATH, LITERAL_OCTETS, LITERAL_SHA256, "rule literal authority")
    runtime_raw = (root / RUNTIME_RELATIVE_PATH).read_bytes()
    _require(len(runtime_raw) == RUNTIME_OCTETS and _sha256(runtime_raw) == RUNTIME_SHA256, "P1 runtime identity differs")
    schema_raw, schema = _load_pinned(root, SCHEMA_RELATIVE_PATH, None, None, "attainer output schema")
    _, freeze = _load_pinned(root, FREEZE_RELATIVE_PATH, None, None, "source-freeze manifest")
    freeze_id = _validate_freeze(root, freeze, schema_raw, schema)
    languages = _index(registry["text_language_catalog"], "text_language_id", "text language")
    dfas = _index(registry["ascii_dfa_catalog"], "ascii_dfa_id", "ASCII DFA")
    profiles = _index(registry["identifier_profile_catalog"], "unicode_identifier_profile_id", "identifier profile")
    descriptors = _index(registry["ordered_external_type_descriptors"], "type_name", "type descriptor")
    runtime_module = _load_runtime(root, runtime_raw, root / RUNTIME_RELATIVE_PATH)
    runtime = runtime_module.ExternalSchemaV2Runtime.load(root)
    cases = contract["ordered_intrinsic_case_records"]
    _require(len(cases) == CASE_COUNT, "intrinsic case count differs")
    case_rows: list[dict[str, Any]] = []
    witnesses: list[Any] = []
    for position, case in enumerate(cases, 1):
        _require(case["case_position"] == position, "intrinsic case order differs")
        witness, trace = _construct_case(
            case,
            languages,
            dfas,
            profiles,
            descriptors,
            contract["canonicalization_version"],
            contract["measurement_schema_version"],
        )
        try:
            evidence = runtime.validate_with_evidence(
                runtime_module.TypedValue(value=witness, type_name=case["root_type_name"])
            )
        except Exception as error:
            _reject(f"P1 rejected case {position}: {type(error).__name__}: {error}")
        raw = _canonical_bytes(witness)
        payload = {
            "case_position": position,
            "intrinsic_correction_case_id": case["intrinsic_correction_case_id"],
            "case_execution_record_id": case["case_execution_record_id"],
            "logical_count_plan_id": case["logical_count_plan_id"],
            "root_type_name": case["root_type_name"],
            "measured_attainer_canonical_octets": len(raw),
            "attainer_canonical_sha256": _sha256(raw),
            "construction_step_count": len(trace),
            "construction_transcript_sha256": _sha256(_canonical_bytes(trace)),
            "p1_validation_status": "ACCEPTED",
            "p1_validation_work_limit": evidence.validation_work_limit,
            "p1_validation_work_used": evidence.validation_work_used,
            "construction_source": "LOCAL_LONGEST_FIRST_WITH_FAIL_CLOSED_P1_REPLAY",
            "external_result_consumed": False,
        }
        case_rows.append({**payload, "attainer_case_record_id": _semantic_id(CASE_DOMAIN, payload)})
        witnesses.append(witness)
    shards: list[dict[str, Any]] = []
    shard_records: list[dict[str, Any]] = []
    for shard_position, (first, last) in enumerate(SHARD_CASE_RANGES, 1):
        witness_rows = [
            {"case_position": position, "witness_record": witnesses[position - 1]}
            for position in range(first, last + 1)
        ]
        payload = {
            "witness_shard_version": schema["witness_shard_schema"]["version_literal"],
            "source_freeze_id": freeze_id,
            "shard_position": shard_position,
            "first_case_position": first,
            "last_case_position": last,
            "witness_count": len(witness_rows),
            "ordered_witness_records": witness_rows,
        }
        shard = {**payload, "witness_shard_id": _semantic_id(SHARD_DOMAIN, payload)}
        shard_raw = _canonical_bytes(shard) + b"\n"
        _require(len(shard_raw) < schema["transport_contract"]["individual_file_strict_upper_octets"], "witness shard exceeds F0")
        shards.append(shard)
        shard_records.append(
            {
                "shard_position": shard_position,
                "relative_path": SHARD_OUTPUT_RELATIVE_PATHS[shard_position - 1],
                "first_case_position": first,
                "last_case_position": last,
                "witness_count": len(witness_rows),
                "raw_octets": len(shard_raw),
                "raw_sha256": _sha256(shard_raw),
                "witness_shard_id": shard["witness_shard_id"],
            }
        )
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
        "ordered_case_attainer_records": case_rows,
        "ordered_case_attainer_records_sha256": _sha256(_canonical_bytes(case_rows)),
        "ordered_witness_shard_records": shard_records,
        "ordered_witness_shard_records_sha256": _sha256(_canonical_bytes(shard_records)),
        "exactness_claimed": False,
        "external_result_consumed": False,
        "formal_stage1_state": "NO-GO",
        "next_bounded_packet": "A4-R475-V1-C3",
    }
    result = {**payload, "attainer_channel_result_id": _semantic_id(RESULT_DOMAIN, payload)}
    _require(set(result) == set(schema["root_record_schema"]["ordered_member_names"]), "attainer root schema differs")
    return result, shards


def _write_temporary(path: pathlib.Path, raw: bytes, suffix: str) -> pathlib.Path:
    _require(not path.exists() and not path.is_symlink(), f"output exists: {path.name}")
    temporary = path.with_name(f".{path.name}.{suffix}.tmp")
    _require(not temporary.exists() and not temporary.is_symlink(), f"temporary exists: {path.name}")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb", closefd=True) as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return temporary


def _publish_transaction(root: pathlib.Path, result: dict[str, Any], shards: list[dict[str, Any]]) -> None:
    targets = [root / path for path in SHARD_OUTPUT_RELATIVE_PATHS] + [root / ROOT_OUTPUT_RELATIVE_PATH]
    raws = [_canonical_bytes(shard) + b"\n" for shard in shards] + [_pretty_bytes(result)]
    temporaries: list[pathlib.Path] = []
    published: list[pathlib.Path] = []
    try:
        for position, (target, raw) in enumerate(zip(targets, raws, strict=True), 1):
            temporaries.append(_write_temporary(target, raw, f"c2a{position}"))
        for temporary, target in zip(temporaries, targets, strict=True):
            os.link(temporary, target)
            published.append(target)
            temporary.unlink()
        directory = os.open(targets[-1].parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except BaseException:
        for path in reversed(published):
            if path.exists() and not path.is_symlink():
                path.unlink()
        for path in temporaries:
            if path.exists() and not path.is_symlink():
                path.unlink()
        raise


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", required=True)
    arguments = parser.parse_args(argv)
    root = pathlib.Path(arguments.repository_root).resolve()
    result, shards = construct(root)
    _publish_transaction(root, result, shards)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(_main(sys.argv[1:]))
    except (AttainerFailure, OSError, ValueError, KeyError, TypeError) as error:
        print(f"RAW_V8_STEP2_INTRINSIC_ATTAINER_REJECT: {error}", file=sys.stderr)
        raise SystemExit(1) from None

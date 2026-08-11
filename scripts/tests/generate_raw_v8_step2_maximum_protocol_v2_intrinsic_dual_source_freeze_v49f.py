#!/usr/bin/env python3
"""Build or check the A4-R475-V1-C2-S dual-source freeze manifest."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import pathlib
import sys
from typing import Any, Final, NoReturn

SOURCE_MARKER: Final = "A4_R475_V1_C2_S_DUAL_SOURCE_FREEZE_GENERATOR_V1"
PACKET: Final = "A4-R475-V1-C2-S"
FREEZE_VERSION: Final = (
    "riskyieldmm.raw_v8_step2.maximum_protocol_v2."
    "intrinsic_dual_source_freeze.v1"
)
FREEZE_DOMAIN: Final = (
    "RiskYieldMMRawV8Step2MaximumProtocolV2IntrinsicDualSourceFreezeV1"
)
SCHEMA_ID_DOMAIN_BY_CHANNEL: Final = {
    "LEGAL_UPPER": "RiskYieldMMRawV8Step2MaximumProtocolV2IntrinsicUpperOutputSchemaV1",
    "P1_LEGAL_ATTAINER": "RiskYieldMMRawV8Step2MaximumProtocolV2IntrinsicAttainerOutputSchemaV1",
}

CONTRACT_PATH: Final = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_correction_contract_v49f.json"
)
REGISTRY_PATH: Final = (
    "scripts/tests/raw_v8_step2_external_schema_v2_structural_registry_v49f.json"
)
LITERAL_PATH: Final = (
    "scripts/tests/raw_v8_step2_external_schema_v2_rule_literal_authority_v49f.json"
)
RUNTIME_PATH: Final = (
    "scripts/tests/validate_raw_v8_step2_external_schema_v2_rule_runtime_v49f.py"
)
UPPER_SOURCE_PATH: Final = (
    "scripts/tests/solve_raw_v8_step2_maximum_protocol_v2_intrinsic_upper_v49f.py"
)
ATTAINER_SOURCE_PATH: Final = (
    "scripts/tests/construct_raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_attainers_v49f.py"
)
UPPER_SCHEMA_PATH: Final = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_upper_result_schema_v49f.json"
)
ATTAINER_SCHEMA_PATH: Final = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_attainer_result_schema_v49f.json"
)
MANIFEST_PATH: Final = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_dual_source_freeze_v49f.json"
)
UPPER_OUTPUT_PATH: Final = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_upper_channel_result_v49f.json"
)
ATTAINER_ROOT_OUTPUT_PATH: Final = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_attainer_channel_result_v49f.json"
)
ATTAINER_SHARD_PATHS: Final = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_intrinsic_attainer_witness_shard_1_v49f.json",
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_intrinsic_attainer_witness_shard_2_v49f.json",
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_intrinsic_attainer_witness_shard_3_v49f.json",
)

PINNED_AUTHORITIES: Final = {
    "INTRINSIC_CORRECTION_CONTRACT": (
        CONTRACT_PATH,
        5_436_266,
        "6245595b759cec6cdecd88292f105dac938f5c69ae92f90ae0365bd032180e14",
    ),
    "STRUCTURAL_REGISTRY": (
        REGISTRY_PATH,
        1_469_663,
        "9160297ff316c5931737c92f8b359f0a1e2ec22f0aa996ef3b09cf830dc96bf3",
    ),
    "RULE_LITERAL_AUTHORITY": (
        LITERAL_PATH,
        484_301,
        "aba3461059367904734e2eb9ae404787b9aab5ed4c3fbcd292925a364926cce2",
    ),
    "P1_RULE_RUNTIME": (
        RUNTIME_PATH,
        249_268,
        "47aa90d897e8dbae5e244b7c04cbd82dfe036b0292d36ef0f5552c868627ab22",
    ),
}
SOURCE_CONFIG: Final = {
    "LEGAL_UPPER": {
        "channel_position": 1,
        "packet": "A4-R475-V1-C2-U",
        "relative_path": UPPER_SOURCE_PATH,
        "source_marker": "A4_R475_V1_C2_U_STANDALONE_LEGAL_UPPER_SOLVER_V1",
        "schema_path": UPPER_SCHEMA_PATH,
        "allowed_imports": ["argparse", "hashlib", "json", "os", "pathlib", "sys", "typing"],
        "allowed_authorities": ["INTRINSIC_CORRECTION_CONTRACT", "STRUCTURAL_REGISTRY"],
        "fixed_outputs": [UPPER_OUTPUT_PATH],
        "core_function": "_derive_case",
        "required_functions": ["_derive_case", "_dfa_upper", "_language_upper", "solve"],
        "runtime_policy": "NO_SHARED_RUNTIME_OR_PROJECT_IMPLEMENTATION",
        "algorithm_contract": [
            "FINITE_ENUMERATION",
            "CLOSED_BUILTIN_FORMULA",
            "ASCII_DFA_DYNAMIC_PROGRAMMING",
            "PINNED_UNICODE_PROFILE_PROGRAM",
            "RULE_AWARE_COMPOSITION",
            "CODEC_INTERSECTION",
        ],
    },
    "P1_LEGAL_ATTAINER": {
        "channel_position": 2,
        "packet": "A4-R475-V1-C2-A",
        "relative_path": ATTAINER_SOURCE_PATH,
        "source_marker": "A4_R475_V1_C2_A_STANDALONE_P1_ATTAINER_CONSTRUCTOR_V1",
        "schema_path": ATTAINER_SCHEMA_PATH,
        "allowed_imports": ["argparse", "base64", "copy", "hashlib", "json", "os", "pathlib", "sys", "types", "typing"],
        "allowed_authorities": [
            "INTRINSIC_CORRECTION_CONTRACT",
            "STRUCTURAL_REGISTRY",
            "RULE_LITERAL_AUTHORITY",
            "P1_RULE_RUNTIME",
        ],
        "fixed_outputs": [ATTAINER_ROOT_OUTPUT_PATH, *ATTAINER_SHARD_PATHS],
        "core_function": "_construct_case",
        "required_functions": ["_construct_case", "_longest_dfa_word", "_text_candidate", "construct"],
        "runtime_policy": "PINNED_RUNTIME_FINAL_P1_VALIDATION_ONLY_AFTER_LOCAL_CONSTRUCTION",
        "algorithm_contract": [
            "LOCAL_LONGEST_FIRST_CONSTRUCTION",
            "FINITE_DFA_PATH_RECONSTRUCTION",
            "LOCAL_IDENTITY_RESEAL",
            "FAIL_CLOSED_CODEC_REDUCTION",
            "PINNED_RUNTIME_FINAL_P1_REPLAY",
        ],
    },
}
SUPPORTED_DERIVATION_KINDS: Final = {
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
FORBIDDEN_IMPORT_ROOTS: Final = {
    "ctypes",
    "http",
    "importlib",
    "inspect",
    "marshal",
    "multiprocessing",
    "pickle",
    "random",
    "requests",
    "riskyieldmm",
    "scripts",
    "socket",
    "subprocess",
    "tests",
    "unicodedata",
    "urllib",
}
FORBIDDEN_DYNAMIC_CALLS: Final = {"__import__", "eval"}
INDIVIDUAL_FILE_LIMIT: Final = 16_777_216
TOTAL_PINNED_INPUT_LIMIT: Final = 67_108_864
INPUT_FILE_COUNT_LIMIT: Final = 64
UPPER_OUTPUT_PROJECTION: Final = 2_097_152
ATTAINER_ROOT_OUTPUT_PROJECTION: Final = 2_097_152
ATTAINER_SHARD_OUTPUT_PROJECTION: Final = 11_600_000
MANIFEST_OCTET_LIMIT: Final = 262_144


class FreezeFailure(RuntimeError):
    """A source, schema, authority, or pre-execution invariant differs."""


def _reject(message: str) -> NoReturn:
    raise FreezeFailure(message)


def _require(condition: bool, message: str) -> None:
    if not condition:
        _reject(message)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


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


def _load_json(path: pathlib.Path, label: str) -> tuple[bytes, dict[str, Any]]:
    _require(path.is_file() and not path.is_symlink(), f"{label} path differs")
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, UnicodeError) as error:
        _reject(f"{label} JSON differs: {error}")
    _require(type(value) is dict, f"{label} root differs")
    return raw, value


def _source_imports(tree: ast.AST) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module == "__future__":
                continue
            _require(node.module is not None, "relative source import is forbidden")
            roots.add(node.module.split(".", 1)[0])
    return roots


def _literal_string_set(node: ast.AST) -> set[str] | None:
    if not isinstance(node, (ast.Set, ast.List, ast.Tuple)):
        return None
    values: set[str] = set()
    for child in node.elts:
        if not isinstance(child, ast.Constant) or type(child.value) is not str:
            return None
        values.add(child.value)
    return values


def _assigned_literal_set(tree: ast.Module, name: str) -> set[str] | None:
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
            value = node.value
            if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == "frozenset" and len(value.args) == 1:
                return _literal_string_set(value.args[0])
            if value is not None:
                return _literal_string_set(value)
    return None


def _function_names(tree: ast.Module) -> set[str]:
    return {node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _call_names(tree: ast.AST) -> list[str]:
    result: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                result.append(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                result.append(node.func.attr)
    return result


def _core_fingerprint(tree: ast.Module, function_name: str) -> str:
    function = next(
        (node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == function_name),
        None,
    )
    _require(function is not None, f"core function is absent: {function_name}")
    normalized = ast.dump(function, annotate_fields=True, include_attributes=False)
    return _sha256(normalized.encode("utf-8"))


def _review_source(root: pathlib.Path, channel: str, config: dict[str, Any]) -> tuple[dict[str, Any], str]:
    path = root / config["relative_path"]
    _require(path.is_file() and not path.is_symlink(), f"{channel} source path differs")
    raw = path.read_bytes()
    _require(len(raw) < INDIVIDUAL_FILE_LIMIT, f"{channel} source exceeds F0")
    try:
        source = raw.decode("utf-8")
        tree = ast.parse(source, filename=config["relative_path"])
        compile(tree, config["relative_path"], "exec", dont_inherit=True)
    except (UnicodeError, SyntaxError, ValueError) as error:
        _reject(f"{channel} source is not statically executable: {error}")
    imports = _source_imports(tree)
    _require(imports == set(config["allowed_imports"]), f"{channel} import surface differs")
    _require(imports.isdisjoint(FORBIDDEN_IMPORT_ROOTS), f"{channel} imports forbidden project/dynamic code")
    functions = _function_names(tree)
    _require(set(config["required_functions"]) <= functions, f"{channel} required function is absent")
    _require(_assigned_literal_set(tree, "SUPPORTED_DERIVATION_KINDS") == SUPPORTED_DERIVATION_KINDS, f"{channel} derivation coverage differs")
    _require(config["source_marker"] in source, f"{channel} source marker differs")
    _require("TODO" not in source and "NotImplemented" not in source, f"{channel} contains placeholder implementation")
    _require(not any(isinstance(node, (ast.Pass, ast.AsyncFunctionDef, ast.Await, ast.Yield, ast.YieldFrom)) for node in ast.walk(tree)), f"{channel} contains incomplete or asynchronous control flow")
    calls = _call_names(tree)
    _require(not (set(calls) & FORBIDDEN_DYNAMIC_CALLS), f"{channel} contains forbidden dynamic call")
    if channel == "LEGAL_UPPER":
        _require("compile" not in calls and "exec" not in calls, "legal-upper source executes dynamic code")
        forbidden_fragments = [ATTAINER_SOURCE_PATH, ATTAINER_ROOT_OUTPUT_PATH, *ATTAINER_SHARD_PATHS]
    else:
        _require(calls.count("compile") == 1 and calls.count("exec") == 1, "attainer pinned-runtime loader shape differs")
        forbidden_fragments = [UPPER_SOURCE_PATH, UPPER_OUTPUT_PATH]
    _require(all(fragment not in source for fragment in forbidden_fragments), f"{channel} embeds opposite-channel path")
    _require("case_position ==" not in source and "case_position in" not in source, f"{channel} contains case-specific answer branch")
    schema_raw, schema = _load_json(root / config["schema_path"], f"{channel} schema")
    schema_payload = {key: value for key, value in schema.items() if key != "output_schema_id"}
    expected_schema_id = _semantic_id(SCHEMA_ID_DOMAIN_BY_CHANNEL[channel], schema_payload)
    _require(schema["identity_domain"] == SCHEMA_ID_DOMAIN_BY_CHANNEL[channel] and schema["output_schema_id"] == expected_schema_id, f"{channel} schema identity differs")
    record = {
        "channel_position": config["channel_position"],
        "channel": channel,
        "successor_packet": config["packet"],
        "relative_path": config["relative_path"],
        "source_marker": config["source_marker"],
        "raw_octets": len(raw),
        "raw_sha256": _sha256(raw),
        "source_language": "PYTHON_3_STANDALONE_STANDARD_LIBRARY_ONLY",
        "allowed_standard_library_import_roots": config["allowed_imports"],
        "ordered_allowed_authority_names": config["allowed_authorities"],
        "output_schema_relative_path": config["schema_path"],
        "output_schema_raw_octets": len(schema_raw),
        "output_schema_raw_sha256": _sha256(schema_raw),
        "output_schema_id": schema["output_schema_id"],
        "ordered_fixed_output_relative_paths": config["fixed_outputs"],
        "output_file_count": len(config["fixed_outputs"]),
        "runtime_authority_policy": config["runtime_policy"],
        "ordered_algorithm_contract": config["algorithm_contract"],
        "complete_derivation_kind_count": len(SUPPORTED_DERIVATION_KINDS),
        "placeholder_or_case_specific_answer_policy": "FORBIDDEN",
        "channel_output_allowed_during_source_freeze": False,
    }
    return record, _core_fingerprint(tree, config["core_function"])


def build_manifest(root: pathlib.Path) -> dict[str, Any]:
    authority_records: list[dict[str, Any]] = []
    authority_octets = 0
    for position, (name, (relative_path, octets, digest)) in enumerate(PINNED_AUTHORITIES.items(), 1):
        path = root / relative_path
        _require(path.is_file() and not path.is_symlink(), f"authority path differs: {name}")
        raw = path.read_bytes()
        _require(len(raw) == octets and _sha256(raw) == digest, f"authority bytes differ: {name}")
        authority_octets += len(raw)
        authority_records.append(
            {
                "authority_position": position,
                "authority_name": name,
                "relative_path": relative_path,
                "raw_octets": len(raw),
                "raw_sha256": digest,
            }
        )
    contract = json.loads((root / CONTRACT_PATH).read_bytes())
    _require(contract["next_bounded_packet"] == PACKET, "C1 successor pointer differs")
    _require(contract["formal_stage1_state"] == "NO-GO", "C1 formal state differs")
    source_records: list[dict[str, Any]] = []
    fingerprints: dict[str, str] = {}
    for channel in ("LEGAL_UPPER", "P1_LEGAL_ATTAINER"):
        record, fingerprint = _review_source(root, channel, SOURCE_CONFIG[channel])
        source_records.append(record)
        fingerprints[channel] = fingerprint
    _require(len(set(fingerprints.values())) == 2, "channel core AST fingerprints are equal")
    output_paths = [UPPER_OUTPUT_PATH, ATTAINER_ROOT_OUTPUT_PATH, *ATTAINER_SHARD_PATHS]
    output_absence = []
    for position, relative_path in enumerate(output_paths, 1):
        path = root / relative_path
        _require(not path.exists() and not path.is_symlink(), f"pre-execution channel output exists: {relative_path}")
        output_absence.append(
            {
                "output_position": position,
                "relative_path": relative_path,
                "required_state": "ABSENT_BEFORE_C2_U_OR_C2_A_EXECUTION",
            }
        )
    schema_source_octets = sum(
        row["raw_octets"] + row["output_schema_raw_octets"] for row in source_records
    )
    pre_manifest_octets = authority_octets + schema_source_octets
    projected_input_upper = pre_manifest_octets + MANIFEST_OCTET_LIMIT
    projected_output_upper = (
        UPPER_OUTPUT_PROJECTION
        + ATTAINER_ROOT_OUTPUT_PROJECTION
        + len(ATTAINER_SHARD_PATHS) * ATTAINER_SHARD_OUTPUT_PROJECTION
    )
    _require(projected_input_upper < TOTAL_PINNED_INPUT_LIMIT, "C2 source-freeze input projection exceeds F0")
    _require(projected_output_upper < TOTAL_PINNED_INPUT_LIMIT, "C2 output projection exceeds F0 total-octet ceiling")
    payload: dict[str, Any] = {
        "canonicalization_version": contract["canonicalization_version"],
        "measurement_schema_version": contract["measurement_schema_version"],
        "freeze_version": FREEZE_VERSION,
        "identity_domain": FREEZE_DOMAIN,
        "packet": PACKET,
        "source_marker": SOURCE_MARKER,
        "intrinsic_exactness_correction_contract_id": contract["intrinsic_exactness_correction_contract_id"],
        "ordered_authority_records": authority_records,
        "ordered_channel_source_records": source_records,
        "channel_core_ast_fingerprints": dict(sorted(fingerprints.items())),
        "independence_contract": {
            "both_complete_sources_and_schemas_sealed_by_this_identity_before_execution": True,
            "shared_core_executable_code_policy": "NONE",
            "shared_material_policy": "THIS_FREEZE_C1_AND_EXPLICIT_BYTE_PINNED_SCHEMA_AUTHORITIES_ONLY",
            "mutual_source_import_read_invoke_or_output_access_policy": "FORBIDDEN",
            "generated_witness_or_result_exchange_policy": "FORBIDDEN",
            "human_adaptation_control": "BOTH_SOURCE_BYTES_SEALED_BEFORE_EITHER_OFFICIAL_RESULT_PATH_EXISTS",
            "attainer_runtime_use_policy": "PINNED_P1_VALIDATION_AFTER_LOCAL_SELECTION_ONLY_NOT_SEARCH_OR_OPTIMIZATION",
            "dynamic_code_policy": "ONLY_C2_A_MAY_COMPILE_AND_EXEC_THE_EXACT_PINNED_P1_RUNTIME_BYTES",
            "network_subprocess_reflection_environment_discovery_policy": "FORBIDDEN",
            "source_change_policy_after_acceptance": "REQUIRES_NEW_VERSIONED_C2_S_AND_INVALIDATES_ALL_DESCENDANT_OUTPUTS",
        },
        "pre_execution_output_absence_records": output_absence,
        "output_transport_projection": {
            "projection_basis": "66_CASES_TIMES_524288_MAXIMUM_CANONICAL_OCTETS_SPLIT_INTO_THREE_FIXED_22_CASE_SHARDS_PLUS_FIXED_ROOT_ALLOWANCES",
            "answer_observation_used_to_set_limits": False,
            "upper_result_projected_strict_upper_octets": UPPER_OUTPUT_PROJECTION,
            "attainer_root_projected_strict_upper_octets": ATTAINER_ROOT_OUTPUT_PROJECTION,
            "attainer_witness_shard_count": len(ATTAINER_SHARD_PATHS),
            "attainer_witness_shard_projected_strict_upper_octets_each": ATTAINER_SHARD_OUTPUT_PROJECTION,
            "projected_total_output_upper_octets": projected_output_upper,
            "projected_output_file_count": len(output_paths),
        },
        "resource_contract": {
            "individual_file_strict_upper_octets": INDIVIDUAL_FILE_LIMIT,
            "total_pinned_input_octets_limit": TOTAL_PINNED_INPUT_LIMIT,
            "input_file_count_limit": INPUT_FILE_COUNT_LIMIT,
            "pre_manifest_pinned_input_octets": pre_manifest_octets,
            "manifest_raw_octet_limit": MANIFEST_OCTET_LIMIT,
            "projected_pinned_input_upper_octets": projected_input_upper,
            "projected_pinned_input_file_count": len(authority_records) + len(source_records) * 2 + 1,
            "limit_tuning_from_observed_channel_answer_allowed": False,
        },
        "acceptance_contract": {
            "acceptance_claim": "PRE_EXECUTION_DUAL_SOURCE_AND_OUTPUT_SCHEMA_FREEZE_ONLY",
            "source_files_executed_by_c2_s": False,
            "channel_results_accepted": False,
            "exact_maxima_accepted": False,
            "all_case_campaign_released": False,
            "required_independent_review": "RECONSTRUCT_BYTES_SCHEMAS_AST_POLICY_RESOURCES_AND_OUTPUT_ABSENCE_WITHOUT_GENERATOR_OR_CHANNEL_IMPORT",
        },
        "formal_stage1_state": "NO-GO",
        "next_bounded_packet": "A4-R475-V1-C2-U",
    }
    return {**payload, "dual_source_freeze_id": _semantic_id(FREEZE_DOMAIN, payload)}


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=pathlib.Path(__file__).resolve().parents[2])
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args(argv)
    root = pathlib.Path(arguments.root).resolve()
    prospective = build_manifest(root)
    raw = _pretty_bytes(prospective)
    _require(len(raw) < MANIFEST_OCTET_LIMIT, "source-freeze manifest exceeds its predeclared limit")
    if arguments.check:
        stored = (root / MANIFEST_PATH).read_bytes()
        _require(stored == raw, "stored source-freeze manifest is stale")
    else:
        sys.stdout.buffer.write(raw)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(_main(sys.argv[1:]))
    except (FreezeFailure, OSError, ValueError, KeyError, TypeError) as error:
        print(f"RAW_V8_STEP2_INTRINSIC_SOURCE_FREEZE_REJECT: {error}", file=sys.stderr)
        raise SystemExit(1) from None

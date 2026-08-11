#!/usr/bin/env python3
"""Independent review of A4-R475-V1-C2-S without importing its generator or channels."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import pathlib
import sys
from typing import Any, Final, NoReturn

SOURCE_MARKER: Final = "INDEPENDENT_A4_R475_V1_C2_S_REVIEWER_V1"
REPORT_VERSION: Final = (
    "riskyieldmm.raw_v8_step2.maximum_protocol_v2."
    "intrinsic_dual_source_freeze_acceptance_report.v1"
)
REPORT_DOMAIN: Final = (
    "RiskYieldMMRawV8Step2MaximumProtocolV2IntrinsicDualSourceFreezeAcceptanceReportV1"
)
FREEZE_DOMAIN: Final = (
    "RiskYieldMMRawV8Step2MaximumProtocolV2IntrinsicDualSourceFreezeV1"
)
MANIFEST_RELATIVE_PATH: Final = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_dual_source_freeze_v49f.json"
)
CONTRACT_RELATIVE_PATH: Final = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_correction_contract_v49f.json"
)
EXPECTED_CONTRACT_ID: Final = (
    "171e9d47a7733f8448f94af5a16da4ba5258f30ee08cb4c835289a05adcb8cb9"
)
EXPECTED_AUTHORITIES: Final = (
    (
        "INTRINSIC_CORRECTION_CONTRACT",
        CONTRACT_RELATIVE_PATH,
        5_436_266,
        "6245595b759cec6cdecd88292f105dac938f5c69ae92f90ae0365bd032180e14",
    ),
    (
        "STRUCTURAL_REGISTRY",
        "scripts/tests/raw_v8_step2_external_schema_v2_structural_registry_v49f.json",
        1_469_663,
        "9160297ff316c5931737c92f8b359f0a1e2ec22f0aa996ef3b09cf830dc96bf3",
    ),
    (
        "RULE_LITERAL_AUTHORITY",
        "scripts/tests/raw_v8_step2_external_schema_v2_rule_literal_authority_v49f.json",
        484_301,
        "aba3461059367904734e2eb9ae404787b9aab5ed4c3fbcd292925a364926cce2",
    ),
    (
        "P1_RULE_RUNTIME",
        "scripts/tests/validate_raw_v8_step2_external_schema_v2_rule_runtime_v49f.py",
        249_268,
        "47aa90d897e8dbae5e244b7c04cbd82dfe036b0292d36ef0f5552c868627ab22",
    ),
)
CHANNELS: Final = (
    {
        "channel": "LEGAL_UPPER",
        "position": 1,
        "packet": "A4-R475-V1-C2-U",
        "source": "scripts/tests/solve_raw_v8_step2_maximum_protocol_v2_intrinsic_upper_v49f.py",
        "marker": "A4_R475_V1_C2_U_STANDALONE_LEGAL_UPPER_SOLVER_V1",
        "schema": "scripts/tests/raw_v8_step2_maximum_protocol_v2_intrinsic_upper_result_schema_v49f.json",
        "schema_domain": "RiskYieldMMRawV8Step2MaximumProtocolV2IntrinsicUpperOutputSchemaV1",
        "imports": {"argparse", "hashlib", "json", "os", "pathlib", "sys", "typing"},
        "functions": {"_derive_case", "_dfa_upper", "_language_upper", "solve"},
        "core": "_derive_case",
        "outputs": ["scripts/tests/raw_v8_step2_maximum_protocol_v2_intrinsic_upper_channel_result_v49f.json"],
        "opposite_paths": [
            "scripts/tests/construct_raw_v8_step2_maximum_protocol_v2_intrinsic_attainers_v49f.py",
            "scripts/tests/raw_v8_step2_maximum_protocol_v2_intrinsic_attainer_channel_result_v49f.json",
        ],
        "dynamic_calls": (0, 0),
    },
    {
        "channel": "P1_LEGAL_ATTAINER",
        "position": 2,
        "packet": "A4-R475-V1-C2-A",
        "source": "scripts/tests/construct_raw_v8_step2_maximum_protocol_v2_intrinsic_attainers_v49f.py",
        "marker": "A4_R475_V1_C2_A_STANDALONE_P1_ATTAINER_CONSTRUCTOR_V1",
        "schema": "scripts/tests/raw_v8_step2_maximum_protocol_v2_intrinsic_attainer_result_schema_v49f.json",
        "schema_domain": "RiskYieldMMRawV8Step2MaximumProtocolV2IntrinsicAttainerOutputSchemaV1",
        "imports": {"argparse", "base64", "copy", "hashlib", "json", "os", "pathlib", "sys", "types", "typing"},
        "functions": {"_construct_case", "_longest_dfa_word", "_text_candidate", "construct"},
        "core": "_construct_case",
        "outputs": [
            "scripts/tests/raw_v8_step2_maximum_protocol_v2_intrinsic_attainer_channel_result_v49f.json",
            "scripts/tests/raw_v8_step2_maximum_protocol_v2_intrinsic_attainer_witness_shard_1_v49f.json",
            "scripts/tests/raw_v8_step2_maximum_protocol_v2_intrinsic_attainer_witness_shard_2_v49f.json",
            "scripts/tests/raw_v8_step2_maximum_protocol_v2_intrinsic_attainer_witness_shard_3_v49f.json",
        ],
        "opposite_paths": [
            "scripts/tests/solve_raw_v8_step2_maximum_protocol_v2_intrinsic_upper_v49f.py",
            "scripts/tests/raw_v8_step2_maximum_protocol_v2_intrinsic_upper_channel_result_v49f.json",
        ],
        "dynamic_calls": (1, 1),
    },
)
DERIVATION_KINDS: Final = {
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
FORBIDDEN_IMPORTS: Final = {
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
EXPECTED_ROOT_SCHEMA_MEMBERS: Final = {
    "LEGAL_UPPER": {
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
    },
    "P1_LEGAL_ATTAINER": {
        "canonicalization_version",
        "measurement_schema_version",
        "result_version",
        "packet",
        "source_freeze_id",
        "source_sha256",
        "output_schema_id",
        "intrinsic_exactness_correction_contract_id",
        "case_count",
        "ordered_case_attainer_records",
        "ordered_case_attainer_records_sha256",
        "ordered_witness_shard_records",
        "ordered_witness_shard_records_sha256",
        "exactness_claimed",
        "external_result_consumed",
        "formal_stage1_state",
        "next_bounded_packet",
        "attainer_channel_result_id",
    },
}


class ReviewFailure(RuntimeError):
    """The independently reconstructed source-freeze contract differs."""


def _reject(message: str) -> NoReturn:
    raise ReviewFailure(message)


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


def _strict_load(path: pathlib.Path, label: str) -> tuple[bytes, dict[str, Any]]:
    _require(path.is_file() and not path.is_symlink(), f"{label} path differs")
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, UnicodeError) as error:
        _reject(f"{label} JSON differs: {error}")
    _require(type(value) is dict, f"{label} root differs")
    return raw, value


def _imports(tree: ast.AST) -> set[str]:
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module != "__future__":
            _require(node.module is not None, "relative import is forbidden")
            result.add(node.module.split(".", 1)[0])
    return result


def _calls(tree: ast.AST) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            names.append(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            names.append(node.func.attr)
    return names


def _assigned_kinds(tree: ast.Module) -> set[str]:
    for node in tree.body:
        if not isinstance(node, ast.AnnAssign) or not isinstance(node.target, ast.Name) or node.target.id != "SUPPORTED_DERIVATION_KINDS":
            continue
        value = node.value
        _require(isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == "frozenset", "derivation set wrapper differs")
        _require(len(value.args) == 1 and isinstance(value.args[0], ast.Set), "derivation set literal differs")
        result = set()
        for child in value.args[0].elts:
            _require(isinstance(child, ast.Constant) and type(child.value) is str, "derivation member differs")
            result.add(child.value)
        return result
    _reject("derivation set is absent")


def _core_fingerprint(tree: ast.Module, name: str) -> str:
    function = next((node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name), None)
    _require(function is not None, f"core function is absent: {name}")
    return _sha256(ast.dump(function, annotate_fields=True, include_attributes=False).encode("utf-8"))


def review(repository_root: pathlib.Path | str) -> dict[str, Any]:
    root = pathlib.Path(repository_root).resolve()
    manifest_raw, manifest = _strict_load(root / MANIFEST_RELATIVE_PATH, "source-freeze manifest")
    _require(manifest_raw == _pretty_bytes(manifest), "source-freeze physical encoding differs")
    freeze_payload = {key: value for key, value in manifest.items() if key != "dual_source_freeze_id"}
    freeze_id = _semantic_id(FREEZE_DOMAIN, freeze_payload)
    _require(manifest["identity_domain"] == FREEZE_DOMAIN and manifest["dual_source_freeze_id"] == freeze_id, "source-freeze semantic identity differs")
    _require(manifest["packet"] == "A4-R475-V1-C2-S" and manifest["formal_stage1_state"] == "NO-GO", "source-freeze packet state differs")
    contract_raw, contract = _strict_load(root / CONTRACT_RELATIVE_PATH, "C1 contract")
    _require(_sha256(contract_raw) == EXPECTED_AUTHORITIES[0][3] and contract["intrinsic_exactness_correction_contract_id"] == EXPECTED_CONTRACT_ID, "C1 authority differs")
    authority_records = manifest["ordered_authority_records"]
    _require(len(authority_records) == len(EXPECTED_AUTHORITIES), "authority count differs")
    authority_octets = 0
    for position, (row, expected) in enumerate(zip(authority_records, EXPECTED_AUTHORITIES, strict=True), 1):
        name, relative_path, octets, digest = expected
        raw = (root / relative_path).read_bytes()
        _require(
            row == {
                "authority_position": position,
                "authority_name": name,
                "relative_path": relative_path,
                "raw_octets": octets,
                "raw_sha256": digest,
            }
            and len(raw) == octets
            and _sha256(raw) == digest,
            f"authority record differs: {name}",
        )
        authority_octets += octets
    source_rows = manifest["ordered_channel_source_records"]
    _require(len(source_rows) == len(CHANNELS), "channel source count differs")
    source_schema_octets = 0
    fingerprints: dict[str, str] = {}
    reviewed_sources: list[dict[str, Any]] = []
    all_outputs: list[str] = []
    for row, expected in zip(source_rows, CHANNELS, strict=True):
        channel = expected["channel"]
        source_path = root / expected["source"]
        source_raw = source_path.read_bytes()
        source = source_raw.decode("utf-8")
        tree = ast.parse(source, filename=expected["source"])
        compile(tree, expected["source"], "exec", dont_inherit=True)
        imported = _imports(tree)
        function_names = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
        calls = _calls(tree)
        _require(imported == expected["imports"] and imported.isdisjoint(FORBIDDEN_IMPORTS), f"{channel} imports differ")
        _require(expected["functions"] <= function_names, f"{channel} function surface differs")
        _require(_assigned_kinds(tree) == DERIVATION_KINDS, f"{channel} derivation coverage differs")
        _require(expected["marker"] in source and "TODO" not in source and "NotImplemented" not in source, f"{channel} completion marker differs")
        _require(not any(isinstance(node, (ast.Pass, ast.AsyncFunctionDef, ast.Await, ast.Yield, ast.YieldFrom)) for node in ast.walk(tree)), f"{channel} incomplete control flow differs")
        _require("eval" not in calls and "__import__" not in calls, f"{channel} forbidden dynamic call exists")
        _require((calls.count("compile"), calls.count("exec")) == expected["dynamic_calls"], f"{channel} pinned dynamic-loader surface differs")
        _require(all(fragment not in source for fragment in expected["opposite_paths"]), f"{channel} embeds opposite-channel path")
        _require("case_position ==" not in source and "case_position in" not in source, f"{channel} case-specific branch exists")
        schema_raw, schema = _strict_load(root / expected["schema"], f"{channel} schema")
        schema_payload = {key: value for key, value in schema.items() if key != "output_schema_id"}
        schema_id = _semantic_id(expected["schema_domain"], schema_payload)
        _require(schema["identity_domain"] == expected["schema_domain"] and schema["output_schema_id"] == schema_id, f"{channel} schema identity differs")
        _require(set(schema["root_record_schema"]["ordered_member_names"]) == EXPECTED_ROOT_SCHEMA_MEMBERS[channel], f"{channel} root schema members differ")
        _require(schema["root_record_schema"]["unknown_member_policy"] == "REJECT", f"{channel} root schema is not closed")
        _require(row["channel_position"] == expected["position"] and row["channel"] == channel and row["successor_packet"] == expected["packet"], f"{channel} manifest position differs")
        _require(row["relative_path"] == expected["source"] and row["raw_octets"] == len(source_raw) and row["raw_sha256"] == _sha256(source_raw), f"{channel} source seal differs")
        _require(row["output_schema_relative_path"] == expected["schema"] and row["output_schema_raw_octets"] == len(schema_raw) and row["output_schema_raw_sha256"] == _sha256(schema_raw) and row["output_schema_id"] == schema_id, f"{channel} schema seal differs")
        _require(row["ordered_fixed_output_relative_paths"] == expected["outputs"] and row["channel_output_allowed_during_source_freeze"] is False, f"{channel} output freeze differs")
        fingerprint = _core_fingerprint(tree, expected["core"])
        fingerprints[channel] = fingerprint
        source_schema_octets += len(source_raw) + len(schema_raw)
        all_outputs.extend(expected["outputs"])
        reviewed_sources.append(
            {
                "channel_position": expected["position"],
                "channel": channel,
                "source_raw_octets": len(source_raw),
                "source_raw_sha256": _sha256(source_raw),
                "output_schema_id": schema_id,
                "core_ast_fingerprint": fingerprint,
                "derivation_kind_count": len(DERIVATION_KINDS),
                "opposite_channel_path_reference_count": 0,
                "official_execution_count": 0,
            }
        )
    _require(len(set(fingerprints.values())) == 2 and manifest["channel_core_ast_fingerprints"] == dict(sorted(fingerprints.items())), "channel core implementation independence differs")
    absence_rows = manifest["pre_execution_output_absence_records"]
    _require([row["relative_path"] for row in absence_rows] == all_outputs, "output-absence ledger differs")
    for relative_path in all_outputs:
        path = root / relative_path
        _require(not path.exists() and not path.is_symlink(), f"official channel output exists before execution: {relative_path}")
    resource = manifest["resource_contract"]
    pre_manifest = authority_octets + source_schema_octets
    _require(resource["pre_manifest_pinned_input_octets"] == pre_manifest, "pre-manifest resource sum differs")
    _require(resource["projected_pinned_input_upper_octets"] == pre_manifest + resource["manifest_raw_octet_limit"] < resource["total_pinned_input_octets_limit"], "pinned-input projection differs")
    _require(resource["projected_pinned_input_file_count"] == 9 < resource["input_file_count_limit"], "input-file projection differs")
    projection = manifest["output_transport_projection"]
    expected_output_upper = projection["upper_result_projected_strict_upper_octets"] + projection["attainer_root_projected_strict_upper_octets"] + 3 * projection["attainer_witness_shard_projected_strict_upper_octets_each"]
    _require(projection["projected_total_output_upper_octets"] == expected_output_upper < resource["total_pinned_input_octets_limit"] and projection["answer_observation_used_to_set_limits"] is False, "output projection differs")
    acceptance = manifest["acceptance_contract"]
    _require(
        acceptance == {
            "acceptance_claim": "PRE_EXECUTION_DUAL_SOURCE_AND_OUTPUT_SCHEMA_FREEZE_ONLY",
            "source_files_executed_by_c2_s": False,
            "channel_results_accepted": False,
            "exact_maxima_accepted": False,
            "all_case_campaign_released": False,
            "required_independent_review": "RECONSTRUCT_BYTES_SCHEMAS_AST_POLICY_RESOURCES_AND_OUTPUT_ABSENCE_WITHOUT_GENERATOR_OR_CHANNEL_IMPORT",
        },
        "source-freeze nonclaim differs",
    )
    payload = {
        "report_version": REPORT_VERSION,
        "source_marker": SOURCE_MARKER,
        "packet": "A4-R475-V1-C2-S",
        "dual_source_freeze_id": freeze_id,
        "source_freeze_raw_octets": len(manifest_raw),
        "source_freeze_raw_sha256": _sha256(manifest_raw),
        "intrinsic_exactness_correction_contract_id": EXPECTED_CONTRACT_ID,
        "authority_record_count": len(authority_records),
        "authority_raw_octets": authority_octets,
        "ordered_reviewed_channel_records": reviewed_sources,
        "distinct_core_ast_fingerprint_count": len(set(fingerprints.values())),
        "pre_execution_absent_output_count": len(all_outputs),
        "projected_pinned_input_upper_octets": resource["projected_pinned_input_upper_octets"],
        "projected_total_output_upper_octets": projection["projected_total_output_upper_octets"],
        "source_or_channel_execution_count": 0,
        "channel_results_accepted": False,
        "exact_maxima_accepted": False,
        "decision": "ACCEPTED_PRE_EXECUTION_DUAL_SOURCE_AND_SCHEMA_FREEZE",
        "formal_stage1_state": "NO-GO",
        "next_bounded_packet": "A4-R475-V1-C2-U",
    }
    return {**payload, "dual_source_freeze_acceptance_report_id": _semantic_id(REPORT_DOMAIN, payload)}


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository_root")
    parser.add_argument("--output")
    arguments = parser.parse_args(argv)
    report = review(arguments.repository_root)
    raw = _pretty_bytes(report)
    if arguments.output is None:
        sys.stdout.buffer.write(raw)
    else:
        pathlib.Path(arguments.output).write_bytes(raw)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(_main(sys.argv[1:]))
    except (ReviewFailure, OSError, ValueError, KeyError, TypeError) as error:
        print(f"RAW_V8_STEP2_INTRINSIC_SOURCE_FREEZE_REVIEW_REJECT: {error}", file=sys.stderr)
        raise SystemExit(1) from None

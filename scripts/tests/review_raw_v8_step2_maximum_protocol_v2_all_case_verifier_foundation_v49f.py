#!/usr/bin/env python3
"""Independently review the A4-R475-V0 verifier foundation.

The reviewer never imports the versioned verifier.  It reconstructs the
effective 475-case ledger from pinned seed authorities, inspects the verifier
AST, replays its foundation-only CLI twice with absent candidate/output paths,
and separately replays the accepted typed-rule runtime.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
from typing import Any, Final

SOURCE_MARKER: Final = "INDEPENDENT_A4_R475_V0_FOUNDATION_REVIEWER_V1"
ERROR_PREFIX: Final = "RAW_V8_STEP2_A4_R475_V0_FOUNDATION_REVIEW_"
REPORT_VERSION: Final = (
    "riskyieldmm.raw_v8_step2.maximum_protocol_v2."
    "all_case_verifier_foundation_acceptance_report.v1"
)
REPORT_DOMAIN: Final = (
    "RiskYieldMMRawV8Step2MaximumProtocolV2AllCaseVerifierFoundationAcceptanceReportV1"
)
CONTRACT_DOMAIN: Final = (
    "RiskYieldMMRawV8Step2MaximumProtocolV2AllCaseCampaignContractV1"
)
CASE_RECORD_DOMAIN: Final = (
    "RiskYieldMMRawV8Step2MaximumProtocolV2AllCaseExecutionRecordV1"
)
CASE_LEDGER_DOMAIN: Final = (
    "RiskYieldMMRawV8Step2MaximumProtocolV2AllCaseExecutionLedgerV1"
)

CONTRACT_RELATIVE_PATH: Final = pathlib.Path(
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "all_case_campaign_contract_v49f.json"
)
CONTRACT_OCTETS: Final = 382_710
CONTRACT_SHA256: Final = (
    "3ca4ff4d6e581895b813043e7fdeed24c33cf2c828e362ac81de1725e95a84bb"
)
CONTRACT_ID: Final = (
    "9be94bf6b53b612d62ac26bc74133f25c1101a0962987a855e65cdcd06418583"
)
VERIFIER_RELATIVE_PATH: Final = pathlib.Path(
    "scripts/tests/verify_raw_v8_step2_maximum_protocol_v2_"
    "all_case_candidate_v49f.py"
)
VERIFIER_OCTETS: Final = 42_659
VERIFIER_SHA256: Final = (
    "15adb9fd5c427c1e1e96ff630e13b36d3f385f12eaf68a388a5da7be48dbf5aa"
)
VERIFIER_SOURCE_MARKER: Final = (
    "INDEPENDENT_V2_ALL_CASE_CONSTRUCTIVE_VERIFIER_V1"
)
RUNTIME_RELATIVE_PATH: Final = pathlib.Path(
    "scripts/tests/validate_raw_v8_step2_external_schema_v2_rule_runtime_v49f.py"
)
RUNTIME_OCTETS: Final = 249_268
RUNTIME_SHA256: Final = (
    "47aa90d897e8dbae5e244b7c04cbd82dfe036b0292d36ef0f5552c868627ab22"
)
REGISTRY_RELATIVE_PATH: Final = pathlib.Path(
    "scripts/tests/raw_v8_step2_external_schema_v2_structural_registry_v49f.json"
)
REGISTRY_OCTETS: Final = 1_469_663
REGISTRY_SHA256: Final = (
    "9160297ff316c5931737c92f8b359f0a1e2ec22f0aa996ef3b09cf830dc96bf3"
)
LITERAL_RELATIVE_PATH: Final = pathlib.Path(
    "scripts/tests/raw_v8_step2_external_schema_v2_rule_literal_authority_v49f.json"
)
LITERAL_OCTETS: Final = 484_301
LITERAL_SHA256: Final = (
    "aba3461059367904734e2eb9ae404787b9aab5ed4c3fbcd292925a364926cce2"
)

CASE_COUNT: Final = 475
EXPECTED_FAMILIES: Final = {
    "CORRECTED_APPLICATION_EXACT_PROFILE": 1,
    "GENERIC_PROFILE_ATTAINMENT": 406,
    "INTRINSIC_TEMPLATE_ATTAINMENT": 66,
    "LOCAL_MINIMALITY": 1,
    "SIGNED_ANALYTIC_EXACT_PROFILE": 1,
}
EXPECTED_IMPORTS: Final = {
    "__future__",
    "dataclasses",
    "hashlib",
    "json",
    "os",
    "pathlib",
    "stat",
    "sys",
    "types",
    "typing",
}


class ReviewFailure(ValueError):
    """Independent acceptance rejection."""


def _require(condition: bool, code: str, detail: str = "") -> None:
    if not condition:
        raise ReviewFailure(f"{code}: {detail}" if detail else code)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


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


def _semantic_id(domain: str, payload: Any) -> str:
    return _sha256(_canonical_bytes({"domain": domain, "payload": payload}))


def _duplicate_guard(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, value in pairs:
        _require(name not in result, "JSON_DUPLICATE", name)
        result[name] = value
    return result


def _reject_number(value: str) -> Any:
    raise ReviewFailure(f"JSON_NUMBER_INVALID: {value}")


def _decode(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_duplicate_guard,
            parse_float=_reject_number,
            parse_constant=_reject_number,
        )
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ReviewFailure(f"JSON_INVALID: {label}") from error
    _require(type(value) is dict, "JSON_ROOT_INVALID", label)
    return value


def _read_exact(
    root: pathlib.Path,
    relative: pathlib.Path,
    octets: int,
    digest: str,
    label: str,
) -> bytes:
    path = root / relative
    _require(path.is_file() and not path.is_symlink(), "ARTIFACT_TYPE", label)
    status = path.stat()
    _require(status.st_nlink == 1, "ARTIFACT_LINK", label)
    raw = path.read_bytes()
    _require((len(raw), _sha256(raw)) == (octets, digest), "ARTIFACT_DRIFT", label)
    return raw


def _contract_payload(contract: dict[str, Any]) -> dict[str, Any]:
    return {
        name: value
        for name, value in contract.items()
        if name != "all_case_campaign_contract_id"
    }


def _case_family(position: int, profile_program_id: Any) -> str:
    if position == 475:
        return "LOCAL_MINIMALITY"
    if position == 69:
        return "SIGNED_ANALYTIC_EXACT_PROFILE"
    if position == 435:
        return "CORRECTED_APPLICATION_EXACT_PROFILE"
    if profile_program_id is not None:
        return "GENERIC_PROFILE_ATTAINMENT"
    return "INTRINSIC_TEMPLATE_ATTAINMENT"


def _contract_authority(
    contract: dict[str, Any],
    role: str,
) -> tuple[pathlib.Path, int, str]:
    matches = [
        row
        for row in contract["authority_contract"]["ordered_authority_records"]
        if row["authority_role"] == role
    ]
    _require(len(matches) == 1, "AUTHORITY_ROLE", role)
    row = matches[0]
    return (
        pathlib.Path(row["repository_relative_path"]),
        row["raw_octets"],
        row["raw_sha256"],
    )


def _reconstruct_case_ledger(
    seed: dict[str, Any],
    delta: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    cases = seed["case_universe_catalog"]["ordered_case_bindings"]
    catalog = seed["logical_plan_recipe_catalog"]
    plans = catalog["ordered_logical_count_plan_records"]
    bindings = catalog["ordered_case_plan_bindings"]
    _require(len(cases) == len(plans) == len(bindings) == CASE_COUNT, "CASE_COUNT")
    records: list[dict[str, Any]] = []
    families: dict[str, int] = {}
    for position in range(1, CASE_COUNT + 1):
        case = cases[position - 1]
        plan = (
            delta["successor_case435_logical_count_plan"]
            if position == 435
            else plans[position - 1]
        )
        binding = (
            delta["successor_case435_case_plan_binding"]
            if position == 435
            else bindings[position - 1]
        )
        _require(
            position
            == case["case_position"]
            == plan["case_position"]
            == binding["case_position"]
            == binding["logical_count_plan_position"],
            "CASE_ORDER",
            str(position),
        )
        _require(
            case["case_binding"] == plan["case_binding"]
            and plan["logical_count_plan_id"] == binding["logical_count_plan_id"],
            "CASE_BINDING",
            str(position),
        )
        family = _case_family(position, plan.get("profile_conditioning_program_id"))
        families[family] = families.get(family, 0) + 1
        case_binding = case["case_binding"]
        payload = {
            "campaign_position": position,
            "case_position": position,
            "case_kind": case["case_kind"],
            "row_kind": case_binding.get("row_kind"),
            "type_name": case_binding.get("type_name"),
            "alternative_name": case_binding.get("alternative_name"),
            "constraint_scope_profile_id": case_binding.get(
                "constraint_scope_profile_id"
            ),
            "effective_logical_count_plan_id": plan["logical_count_plan_id"],
            "effective_plan_source": (
                "CASE435_SUCCESSOR_DELTA" if position == 435 else "BASE_SEED"
            ),
            "execution_family": family,
            "candidate_transport": (
                "CASE435_PACKED_CONTEXT_V1"
                if position == 435
                else "INHERITED_CLOSED_CANDIDATE_BUNDLE_V1"
            ),
        }
        records.append(
            {
                **payload,
                "case_execution_record_id": _semantic_id(CASE_RECORD_DOMAIN, payload),
            }
        )
    _require(families == EXPECTED_FAMILIES, "FAMILY_CENSUS")
    return records, families


def _review_contract_and_ledger(
    root: pathlib.Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    contract_raw = _read_exact(
        root,
        CONTRACT_RELATIVE_PATH,
        CONTRACT_OCTETS,
        CONTRACT_SHA256,
        "all-case contract",
    )
    contract = _decode(contract_raw, "all-case contract")
    _require(contract_raw == _pretty_bytes(contract), "CONTRACT_ENCODING")
    _require(
        contract["all_case_campaign_contract_id"]
        == _semantic_id(CONTRACT_DOMAIN, _contract_payload(contract))
        == CONTRACT_ID,
        "CONTRACT_ID",
    )
    seed_path, seed_octets, seed_sha = _contract_authority(contract, "SEED")
    delta_path, delta_octets, delta_sha = _contract_authority(
        contract,
        "CASE435_SEED_DELTA",
    )
    seed = _decode(
        _read_exact(root, seed_path, seed_octets, seed_sha, "seed"),
        "seed",
    )
    delta = _decode(
        _read_exact(root, delta_path, delta_octets, delta_sha, "case435 delta"),
        "case435 delta",
    )
    records, families = _reconstruct_case_ledger(seed, delta)
    universe = contract["case_universe_contract"]
    _require(universe["ordered_case_execution_records"] == records, "CASE_LEDGER")
    _require(
        universe["ordered_case_execution_records_sha256"]
        == _sha256(_canonical_bytes(records)),
        "CASE_LEDGER_SHA",
    )
    _require(
        universe["case_execution_ledger_id"]
        == _semantic_id(
            CASE_LEDGER_DOMAIN,
            {"case_count": CASE_COUNT, "ordered_case_execution_records": records},
        ),
        "CASE_LEDGER_ID",
    )
    _require(
        contract["gate_contract"]["next_bounded_packet_after_contract_acceptance"]
        == "A4-R475-V0"
        and contract["gate_contract"]["formal_stage1_state"] == "NO-GO",
        "GATE_BOUNDARY",
    )
    return contract, {
        "case_count": len(records),
        "execution_family_counts": families,
        "case_execution_ledger_id": universe["case_execution_ledger_id"],
        "ordered_case_execution_records_sha256": universe[
            "ordered_case_execution_records_sha256"
        ],
        "case435_effective_plan_id": records[434][
            "effective_logical_count_plan_id"
        ],
        "successor_plan_case_positions": [
            row["case_position"]
            for row in records
            if row["effective_plan_source"] == "CASE435_SUCCESSOR_DELTA"
        ],
    }


def _review_source_ast(source_raw: bytes) -> dict[str, Any]:
    source = source_raw.decode("utf-8", errors="strict")
    tree = ast.parse(source)
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported.update(
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    )
    _require(imported <= EXPECTED_IMPORTS, "IMPORT_SURFACE", repr(imported))
    functions = {
        node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)
    }
    required = {
        "_load_foundation",
        "_validate_contract_surface",
        "_validate_case_ledger",
        "_load_pinned_runtime",
        "_validate_typed_value",
        "_evaluate_rule_ast",
        "_verify_foundation_only",
    }
    _require(required <= set(functions), "FUNCTION_SURFACE")
    verify = functions["_verify_foundation_only"]
    calls = [
        node.func.id
        for node in ast.walk(verify)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]
    _require(
        calls == ["_load_foundation", "_foundation_recheck", "_reject"],
        "FOUNDATION_ONLY_CALL_GRAPH",
        repr(calls),
    )
    deleted = {
        target.id
        for node in ast.walk(verify)
        if isinstance(node, ast.Delete)
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    _require(deleted == {"candidate_root", "output_root"}, "CANDIDATE_DELETE_BARRIER")
    for forbidden in (
        "produce_raw_v8_step2_maximum_protocol_v2_candidate_v49f",
        "verify_raw_v8_step2_maximum_protocol_v2_candidate_v49f",
        "run_raw_v8_step2_maximum_protocol_v2_pilot_v49f",
        "subprocess",
        "pickle",
        "eval(",
    ):
        _require(forbidden not in source, "FORBIDDEN_SOURCE_TOKEN", forbidden)
    _require(VERIFIER_SOURCE_MARKER in source, "SOURCE_MARKER")
    return {
        "imported_top_level_modules": sorted(imported),
        "required_foundation_function_count": len(required),
        "foundation_only_call_order": calls,
        "candidate_and_output_arguments_deleted_before_rejection": True,
        "forbidden_source_tokens_observed": 0,
    }


def _run_verifier_replays(
    root: pathlib.Path,
    verifier_path: pathlib.Path,
) -> dict[str, Any]:
    outputs: list[tuple[int, bytes, bytes]] = []
    with tempfile.TemporaryDirectory(prefix="a4-r475-v0-review-") as temporary:
        temporary_root = pathlib.Path(temporary)
        for replay in range(2):
            candidate = temporary_root / f"candidate-{replay}-must-remain-absent"
            output = temporary_root / f"output-{replay}-must-remain-absent"
            completed = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-S",
                    "-B",
                    os.fspath(verifier_path),
                    "--repository-root",
                    os.fspath(root),
                    "--boundary",
                    os.fspath(root / CONTRACT_RELATIVE_PATH),
                    "--candidate-root",
                    os.fspath(candidate),
                    "--output-root",
                    os.fspath(output),
                ],
                cwd=root,
                check=False,
                capture_output=True,
                timeout=30,
            )
            _require(not candidate.exists() and not output.exists(), "PATH_SIDE_EFFECT")
            outputs.append((completed.returncode, completed.stdout, completed.stderr))
    expected_stderr = (
        b"RAW_V8_STEP2_MAXIMUM_PROTOCOL_V2_ALL_CASE_VERIFIER_FOUNDATION_ONLY: "
        b"A4-R475-V0 accepts no case and did not open candidate or output paths\n"
    )
    _require(
        outputs[0] == outputs[1] == (1, b"", expected_stderr),
        "VERIFIER_REPLAY",
    )
    return {
        "replay_count": 2,
        "byte_identical": True,
        "return_code": 1,
        "stderr_sha256": _sha256(expected_stderr),
        "candidate_paths_opened": 0,
        "output_paths_created": 0,
    }


def _run_runtime_replays(root: pathlib.Path) -> dict[str, Any]:
    outputs: list[bytes] = []
    for _ in range(2):
        completed = subprocess.run(
            [
                sys.executable,
                "-I",
                "-S",
                "-B",
                os.fspath(root / RUNTIME_RELATIVE_PATH),
                "--repository-root",
                os.fspath(root),
            ],
            cwd=root,
            check=False,
            capture_output=True,
            timeout=30,
        )
        _require(completed.returncode == 0 and completed.stderr == b"", "RUNTIME_REPLAY")
        outputs.append(completed.stdout)
    _require(outputs[0] == outputs[1], "RUNTIME_NONDETERMINISTIC")
    report = _decode(outputs[0], "runtime report")
    _require(
        report["executable_rule_count"] == 42
        and report["executable_application_count"] == 8
        and report["fixed_position_resolver_count"] == 2
        and report["unsupported_complex_rule_count"] == 0
        and report["status"]
        == "APPLICATION_RUNTIME_ONLY_MAXIMA_AND_PRODUCTION_INTEGRATION_PENDING",
        "RUNTIME_CAPABILITY",
    )
    return {
        "replay_count": 2,
        "byte_identical": True,
        "stdout_sha256": _sha256(outputs[0]),
        "rule_count": 42,
        "application_count": 8,
        "resolver_count": 2,
        "unsupported_complex_rule_count": 0,
    }


def _seal_report(report: dict[str, Any]) -> None:
    payload = {
        name: value
        for name, value in report.items()
        if name != "all_case_verifier_foundation_acceptance_report_id"
    }
    report["all_case_verifier_foundation_acceptance_report_id"] = _semantic_id(
        REPORT_DOMAIN,
        payload,
    )


def build_report(root: pathlib.Path, verifier_path: pathlib.Path) -> dict[str, Any]:
    _require(verifier_path == root / VERIFIER_RELATIVE_PATH, "VERIFIER_PATH")
    contract, ledger = _review_contract_and_ledger(root)
    source_raw = _read_exact(
        root,
        VERIFIER_RELATIVE_PATH,
        VERIFIER_OCTETS,
        VERIFIER_SHA256,
        "versioned verifier",
    )
    source_evidence = _review_source_ast(source_raw)
    _read_exact(
        root,
        RUNTIME_RELATIVE_PATH,
        RUNTIME_OCTETS,
        RUNTIME_SHA256,
        "typed runtime",
    )
    _read_exact(
        root,
        REGISTRY_RELATIVE_PATH,
        REGISTRY_OCTETS,
        REGISTRY_SHA256,
        "structural registry",
    )
    _read_exact(
        root,
        LITERAL_RELATIVE_PATH,
        LITERAL_OCTETS,
        LITERAL_SHA256,
        "rule-literal authority",
    )
    verifier_replays = _run_verifier_replays(root, verifier_path)
    runtime_replays = _run_runtime_replays(root)
    authority_octets = (
        CONTRACT_OCTETS
        + sum(
            row["raw_octets"]
            for row in contract["authority_contract"]["ordered_authority_records"]
        )
        + RUNTIME_OCTETS
        + REGISTRY_OCTETS
        + LITERAL_OCTETS
        + VERIFIER_OCTETS
    )
    f0 = {
        row["resource_name"]: row["ceiling_value"]
        for row in contract["resource_contract"]["ordered_f0_limit_records"]
    }
    _require(authority_octets == 16_717_988, "F0_OCTET_RECONSTRUCTION")
    _require(
        18 < f0["INPUT_FILE_COUNT"]
        and authority_octets < f0["TOTAL_PINNED_INPUT_OCTETS"],
        "F0_HEADROOM",
    )
    report: dict[str, Any] = {
        "acceptance_report_version": REPORT_VERSION,
        "source_marker": SOURCE_MARKER,
        "correction_subgate": "A4-R475-V0",
        "verifier_authority": {
            "repository_relative_path": VERIFIER_RELATIVE_PATH.as_posix(),
            "source_marker": VERIFIER_SOURCE_MARKER,
            "raw_octets": VERIFIER_OCTETS,
            "raw_sha256": VERIFIER_SHA256,
        },
        "contract_authority": {
            "repository_relative_path": CONTRACT_RELATIVE_PATH.as_posix(),
            "raw_octets": CONTRACT_OCTETS,
            "raw_sha256": CONTRACT_SHA256,
            "all_case_campaign_contract_id": CONTRACT_ID,
        },
        "independent_case_reconstruction": ledger,
        "independent_source_review": source_evidence,
        "verifier_cli_replay": verifier_replays,
        "typed_runtime_replay": runtime_replays,
        "resource_evidence": {
            "authority_file_count": 18,
            "authority_file_headroom": f0["INPUT_FILE_COUNT"] - 18,
            "pinned_input_octets": authority_octets,
            "pinned_input_octet_headroom": (
                f0["TOTAL_PINNED_INPUT_OCTETS"] - authority_octets
            ),
            "f0_limits_raised": False,
        },
        "fail_first_boundary": {
            "accepted_constructive_case_count": 0,
            "candidate_access_forbidden": True,
            "versioned_verifier_present": True,
            "versioned_producer_present": False,
            "versioned_runner_present": False,
            "expected_remaining_role_failures": 2,
        },
        "ordered_acceptance_criteria": [
            "EXACT_CONTRACT_AND_ALL_475_CASE_BINDINGS_RECONSTRUCTED",
            "UNIQUE_CASE435_SUCCESSOR_DISPATCH",
            "PINNED_COMPLETE_TYPED_RUNTIME",
            "NO_PILOT_ROLE_IMPORT_OR_EXECUTION",
            "NO_CANDIDATE_OR_OUTPUT_ACCESS_IN_V0",
            "TWO_BYTE_IDENTICAL_FAIL_CLOSED_REPLAYS",
            "IMMUTABLE_F0_HEADROOM",
        ],
        "review_decision": "ACCEPTED_FOUNDATION_ONLY",
        "accepted_constructive_case_count": 0,
        "next_bounded_packet": "A4-R475-V1",
        "formal_stage1_state": "NO-GO",
    }
    _seal_report(report)
    return report


def _atomic_write(path: pathlib.Path, raw: bytes) -> None:
    _require(path.is_absolute(), "OUTPUT_PATH")
    _require(path.parent.is_dir() and not path.parent.is_symlink(), "OUTPUT_PARENT")
    _require(not path.exists() and not path.is_symlink(), "OUTPUT_EXISTS")
    temporary = path.parent / f".{path.name}.tmp"
    descriptor: int | None = None
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
            0o600,
        )
        offset = 0
        while offset < len(raw):
            written = os.write(descriptor, raw[offset:])
            _require(written > 0, "OUTPUT_STALLED")
            offset += written
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        os.link(temporary, path, follow_symlinks=False)
        os.unlink(temporary)
        parent = os.open(path.parent, os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _arguments(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--repository-root", required=True)
    parser.add_argument("--verifier", required=True)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--write-report")
    modes.add_argument("--check-report")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        arguments = _arguments(sys.argv[1:] if argv is None else argv)
        root = pathlib.Path(arguments.repository_root)
        verifier = pathlib.Path(arguments.verifier)
        _require(root.is_absolute() and verifier.is_absolute(), "ABSOLUTE_PATHS")
        report = build_report(root, verifier)
        raw = _pretty_bytes(report)
        destination_value = arguments.write_report or arguments.check_report
        destination = pathlib.Path(destination_value)
        _require(destination.is_absolute(), "REPORT_PATH")
        if arguments.write_report is not None:
            _atomic_write(destination, raw)
        else:
            _require(destination.is_file(), "REPORT_ABSENT")
            _require(destination.read_bytes() == raw, "REPORT_DRIFT")
        return 0
    except (ReviewFailure, OSError, ValueError, KeyError, TypeError) as error:
        message = str(error).replace("\n", " ").replace("\r", " ")[:768]
        sys.stderr.write(f"{ERROR_PREFIX}REJECTED: {type(error).__name__}: {message}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

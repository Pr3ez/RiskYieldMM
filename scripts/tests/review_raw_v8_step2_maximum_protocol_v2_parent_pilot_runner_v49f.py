#!/usr/bin/env python3
"""Independent acceptance reviewer for the A4-P6-R parent pilot runner."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import pathlib
import re
import stat
import subprocess
import sys
import tempfile
from typing import Any

SOURCE_MARKER = "INDEPENDENT_A4_P6_R_PARENT_PILOT_RUNNER_REVIEWER_V1"
REPORT_VERSION = (
    "riskyieldmm.raw_v8_step2.maximum_protocol_v2."
    "parent_pilot_runner_acceptance_report.v1"
)
REPORT_DOMAIN = (
    "RiskYieldMMRawV8Step2MaximumProtocolV2ParentPilotRunnerAcceptanceReportV1"
)

RUNNER = pathlib.Path(
    "scripts/tests/run_raw_v8_step2_maximum_protocol_v2_pilot_v49f.py"
)
PRODUCER = pathlib.Path(
    "scripts/tests/produce_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py"
)
VERIFIER = pathlib.Path(
    "scripts/tests/verify_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py"
)
BOUNDARY = pathlib.Path(
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_constructive_boundary_v49f.json"
)
PACKED_BOUNDARY = pathlib.Path(
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "case435_context_pack_boundary_delta_v49f.json"
)
TARGET = pathlib.Path(
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "case435_six_case_target_delta_v49f.json"
)
MANIFEST = pathlib.Path(
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_finalization_manifest_v49f.json"
)
PRODUCER_REPORT = pathlib.Path(
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "separate_producer_expansion_acceptance_report_v49f.json"
)
QUALIFICATION_TEST = pathlib.Path(
    "tests/test_raw_v8_step2_maximum_protocol_v2_parent_pilot_runner_v49f.py"
)
A4_T_TEST = pathlib.Path(
    "tests/test_raw_v8_step2_maximum_protocol_v2_implementation_fail_first_v49f.py"
)

RUNNER_MARKER = "PARENT_OWNED_V2_CONSTRUCTIVE_PILOT_RUNNER_V1"
PRODUCER_MARKER = "SEPARATE_V2_CONSTRUCTIVE_PRODUCER_V1"
VERIFIER_MARKER = "INDEPENDENT_V2_CONSTRUCTIVE_VERIFIER_V1"
ERROR_PREFIX = b"RAW_V8_STEP2_MAXIMUM_PROTOCOL_V2_PILOT_RUNNER_"
EXPECTED_P_REPORT_ID = (
    "defe27a1fafa0c1b37f9e1cf5498b14bb662cc2724dec9660abdb86f78ef9ed6"
)
PILOT_CASES = (5, 24, 54, 69, 435, 475)

EXPECTED_STATIC_ARTIFACTS = {
    RUNNER: (
        50_461,
        "5f1997b4e689a14cbae0a340fce2f320bb058eb9dd04449897ff3dfdf8de7ad7",
    ),
    QUALIFICATION_TEST: (
        17_493,
        "431f3ea5f41c87a5635cb2b5b44f24c548ecc4983c8c3acd02a6b5ab2d7a976c",
    ),
    PRODUCER: (
        129_026,
        "46c67738905488a467cbb66a6de719f4cd4804e7ac68143cb301dc1e9c46d7da",
    ),
    VERIFIER: (
        373_327,
        "b1bfb5778b1408c4b2dc45dd008f1089e2405b503b7eee9686820535d5631d25",
    ),
    BOUNDARY: (
        27_334,
        "05468ec3411869fc5b4b5c60d2820e58f8ebf0af96dea978f06d92705fe3bb2b",
    ),
    PACKED_BOUNDARY: (
        6_049,
        "985f0d67a545d036f1777a627f01b609d396a39c690ac81c1bacfc4f7563f56b",
    ),
    TARGET: (
        4_768,
        "394da62c1b5146990b2769feaefa1c06c75387ab7a38ec410ec7e327699b340b",
    ),
    PRODUCER_REPORT: (
        12_583,
        "2ef2a621df51f5193108a61ed5b639ab48378b9e5fd87daf4cfbd619a9fb20c8",
    ),
}


class ReviewFailure(ValueError):
    """Independent reviewer rejection."""


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


def _load(path: pathlib.Path) -> dict[str, Any]:
    raw = path.read_bytes()
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_duplicate_guard,
            parse_float=_reject_number,
            parse_constant=_reject_number,
        )
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ReviewFailure(f"JSON_INVALID: {path}") from error
    _require(type(value) is dict, "JSON_ROOT_INVALID", str(path))
    return value


def _artifact(root: pathlib.Path, relative: pathlib.Path) -> dict[str, Any]:
    path = root / relative
    raw = path.read_bytes()
    expected = EXPECTED_STATIC_ARTIFACTS[relative]
    _require(
        len(raw) == expected[0] and _sha256(raw) == expected[1],
        "STATIC_ARTIFACT_DRIFT",
        str(relative),
    )
    return {
        "repository_relative_path": relative.as_posix(),
        "raw_octets": len(raw),
        "raw_sha256": _sha256(raw),
    }


def _static_review(root: pathlib.Path) -> dict[str, Any]:
    descriptors = {
        relative: _artifact(root, relative) for relative in EXPECTED_STATIC_ARTIFACTS
    }
    boundary = _load(root / BOUNDARY)
    producer_report = _load(root / PRODUCER_REPORT)
    _require(
        producer_report["separate_producer_acceptance_report_id"]
        == EXPECTED_P_REPORT_ID,
        "P_REPORT_ID_INVALID",
    )
    runner_source = (root / RUNNER).read_text(encoding="utf-8")
    tree = ast.parse(runner_source)
    imports: set[str] = set()
    calls: set[str] = set()
    strings: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            _require(node.level == 0 and node.module is not None, "RELATIVE_IMPORT")
            imports.add(node.module.split(".", 1)[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)
        elif isinstance(node, ast.Constant) and type(node.value) is str:
            strings.add(node.value)
    independence = boundary["independence_contract"]
    allowed = set(independence["allowed_standard_library_import_roots"])
    forbidden = set(independence["forbidden_import_roots"])
    _require(
        imports <= allowed, "RUNNER_IMPORT_INVALID", repr(sorted(imports - allowed))
    )
    _require(imports.isdisjoint(forbidden), "RUNNER_FORBIDDEN_IMPORT")
    _require(
        calls.isdisjoint(
            {
                "__import__",
                "compile",
                "eval",
                "exec",
                "system",
                "popen",
                "spawnl",
                "spawnv",
            }
        ),
        "RUNNER_DYNAMIC_OR_SHELL_EXECUTION",
    )
    _require(
        {"fork", "execve", "wait4", "setrlimit"} <= calls, "PROCESS_BOUNDARY_MISSING"
    )
    _require(RUNNER_MARKER in strings, "RUNNER_MARKER_MISSING")
    _require(
        PRODUCER_MARKER not in runner_source and VERIFIER_MARKER not in runner_source,
        "CHILD_MARKER_COPIED",
    )
    for required in (
        PRODUCER.as_posix(),
        VERIFIER.as_posix(),
        PACKED_BOUNDARY.as_posix(),
        "--case-position",
        "--candidate-root",
        "--write-output-root",
        "--check-output-root",
    ):
        _require(
            required in runner_source or required in strings,
            "RUNNER_SURFACE_MISSING",
            required,
        )
    for row in producer_report["ordered_case_acceptance_records"]:
        for name in (
            "constructive_candidate_id",
            "verification_receipt_id",
            "result_artifact_id",
        ):
            _require(row[name] not in runner_source, "ACCEPTED_ANSWER_COPIED", name)
    return {
        "descriptors": descriptors,
        "allowed_imports": sorted(imports),
        "dynamic_code_loading": False,
        "reviewed_role_imports": False,
        "accepted_answer_literals": False,
        "fixed_execve_process_boundary": True,
    }


def _environment() -> dict[str, str]:
    return {
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
    }


def _run_runner(
    root: pathlib.Path, mode: str, output: pathlib.Path
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            str(root / RUNNER),
            "--repository-root",
            str(root),
            "--boundary",
            str(root / PACKED_BOUNDARY),
            f"--{mode}-output-root",
            str(output),
        ],
        cwd=root,
        check=False,
        capture_output=True,
        env=_environment(),
        timeout=3_600,
    )


def _success(completed: subprocess.CompletedProcess[bytes], code: str) -> None:
    _require(completed.returncode == 0, code, completed.stderr.decode(errors="replace"))
    _require(completed.stdout == completed.stderr == b"", f"{code}_NOISY")


def _reject(completed: subprocess.CompletedProcess[bytes], code: str) -> None:
    _require(completed.returncode != 0, code)
    _require(completed.stdout == b"", f"{code}_STDOUT")
    _require(
        completed.stderr.startswith(ERROR_PREFIX)
        and completed.stderr.count(b"\n") == 1,
        f"{code}_DIAGNOSTIC",
    )


def _snapshot(root: pathlib.Path) -> tuple[tuple[str, int, int, str], ...]:
    rows: list[tuple[str, int, int, str]] = []
    identities: set[tuple[int, int]] = set()
    for path in sorted(root.rglob("*")):
        metadata = path.lstat()
        relative = path.relative_to(root).as_posix()
        _require(not stat.S_ISLNK(metadata.st_mode), "OUTPUT_SYMLINK", relative)
        if path.is_dir():
            _require(
                stat.S_IMODE(metadata.st_mode) == 0o700, "DIRECTORY_MODE", relative
            )
            rows.append((relative + "/", 0o700, 0, ""))
        else:
            _require(
                path.is_file()
                and metadata.st_nlink == 1
                and stat.S_IMODE(metadata.st_mode) == 0o600,
                "FILE_MODE_OR_LINK",
                relative,
            )
            identity = (metadata.st_dev, metadata.st_ino)
            _require(identity not in identities, "FILE_ALIAS", relative)
            identities.add(identity)
            raw = path.read_bytes()
            rows.append((relative, 0o600, len(raw), _sha256(raw)))
    return tuple(rows)


def _file_closure(root: pathlib.Path) -> tuple[int, str]:
    rows = []
    for path, _mode, octets, digest in _snapshot(root):
        if path.endswith("/"):
            continue
        rows.append(
            {
                "repository_relative_path": path,
                "raw_octets": octets,
                "raw_sha256": digest,
            }
        )
    return sum(row["raw_octets"] for row in rows), _sha256(_canonical_bytes(rows))


def _output_json(path: pathlib.Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    value = _load(path)
    _require(raw == _pretty_bytes(value), "OUTPUT_ENCODING", str(path))
    return value, raw


def _validate_pilot(
    root: pathlib.Path, output: pathlib.Path
) -> tuple[bytes, list[dict[str, Any]], list[dict[str, Any]]]:
    boundary = _load(root / BOUNDARY)
    packed = _load(root / PACKED_BOUNDARY)
    target = _load(root / TARGET)
    p_report = _load(root / PRODUCER_REPORT)
    f2_rows = _load(root / MANIFEST)["ordered_f2_limit_records"]
    pilot = boundary["pilot_contract"]
    schema = pilot["pilot_manifest_schema"]
    manifest, manifest_raw = _output_json(output / "constructive_pilot_manifest.json")
    _require(set(manifest) == set(schema["ordered_member_names"]), "MANIFEST_SCHEMA")
    effective = packed["unchanged_effective_authorities"]
    for name, expected in (
        ("pilot_version", pilot["pilot_version"]),
        ("canonicalization_version", boundary["canonicalization_version"]),
        ("protocol_version", boundary["protocol_version"]),
        ("seed_catalog_id", effective["successor_seed_catalog_id"]),
        ("finalization_manifest_id", effective["successor_manifest_id"]),
        ("pilot_status", pilot["pilot_status"]),
    ):
        _require(manifest[name] == expected, "MANIFEST_BINDING", name)
    roles = {
        row["role_name"]: row
        for row in boundary["implementation_role_contract"]["ordered_role_records"]
    }
    for member, role, source in (
        ("producer_authority", "SEPARATE_PRODUCER", PRODUCER),
        ("verifier_authority", "INDEPENDENT_VERIFIER", VERIFIER),
        ("runner_authority", "PARENT_PILOT_RUNNER", RUNNER),
    ):
        raw = (root / source).read_bytes()
        _require(
            manifest[member]
            == {
                "repository_relative_path": roles[role]["repository_relative_path"],
                "raw_octets": len(raw),
                "raw_sha256": _sha256(raw),
                "source_marker": roles[role]["source_marker"],
            },
            "ROLE_AUTHORITY_INVALID",
            role,
        )
    ledger = {
        row["case_position"]: row for row in p_report["ordered_case_acceptance_records"]
    }
    aggregate = [0] * 18
    case_records = []
    expected_rows = target["ordered_pilot_case_records"]
    entries = manifest["ordered_case_result_entries"]
    _require(len(entries) == len(expected_rows) == 6, "CASE_COUNT")
    for expected, entry in zip(expected_rows, entries, strict=True):
        case_position = expected["case_position"]
        case_root = (
            output / "cases" / f"{expected['pilot_position']:04d}-{case_position:04d}"
        )
        candidate_root = case_root / "candidate"
        verified_root = case_root / "verified"
        candidate, _candidate_raw = _output_json(candidate_root / "candidate.json")
        receipt, _receipt_raw = _output_json(
            verified_root / "verification_receipt.json"
        )
        result_name = (
            "local_shutdown_unrepresentable.json"
            if case_position == 475
            else "maximum_attainer.json"
        )
        result, _result_raw = _output_json(verified_root / result_name)
        result_id = result.get("maximum_attainer_id") or result.get(
            "local_shutdown_unrepresentable_id"
        )
        expected_ledger = ledger[case_position]
        _require(
            candidate["constructive_candidate_id"]
            == expected_ledger["constructive_candidate_id"],
            "CANDIDATE_ID",
            str(case_position),
        )
        _require(
            receipt["verification_receipt_id"]
            == expected_ledger["verification_receipt_id"],
            "RECEIPT_ID",
            str(case_position),
        )
        _require(result_id == expected_ledger["result_artifact_id"], "RESULT_ID")
        candidate_octets, candidate_digest = _file_closure(candidate_root)
        verified_octets, verified_digest = _file_closure(verified_root)
        expected_entry = {
            "pilot_position": expected["pilot_position"],
            "case_position": case_position,
            "case_kind": expected["case_kind"],
            "logical_count_plan_id": expected["logical_count_plan_id"],
            "constructive_candidate_id": candidate["constructive_candidate_id"],
            "candidate_root_raw_octets": candidate_octets,
            "candidate_root_sha256": candidate_digest,
            "verification_receipt_id": receipt["verification_receipt_id"],
            "verified_result_artifact_id": result_id,
            "verified_result_root_raw_octets": verified_octets,
            "verified_result_root_sha256": verified_digest,
        }
        _require(entry == expected_entry, "MANIFEST_CASE_ENTRY", str(case_position))
        vector = [
            row["measured_value"]
            for row in result["proof_resource_report"]["ordered_resource_measurements"]
        ]
        _require(vector == expected_ledger["resource_vector"], "RESOURCE_VECTOR")
        for index, (value, limit) in enumerate(zip(vector, f2_rows, strict=True)):
            _require(value <= limit["f2_per_case"], "F2_PER_CASE")
            if limit["full_run_aggregation"] == "SUM":
                aggregate[index] += value
            else:
                aggregate[index] = max(aggregate[index], value)
        case_records.append(
            {
                "pilot_position": expected["pilot_position"],
                "case_position": case_position,
                "logical_count_plan_id": expected["logical_count_plan_id"],
                "constructive_candidate_id": candidate["constructive_candidate_id"],
                "verification_receipt_id": receipt["verification_receipt_id"],
                "verified_result_artifact_id": result_id,
                "candidate_root_raw_octets": candidate_octets,
                "candidate_root_sha256": candidate_digest,
                "verified_result_root_raw_octets": verified_octets,
                "verified_result_root_sha256": verified_digest,
                "resource_vector": vector,
            }
        )
    f2_reconciliation = []
    for value, limit in zip(aggregate, f2_rows, strict=True):
        _require(value <= limit["f2_full_run"], "F2_FULL_RUN", limit["metric_name"])
        f2_reconciliation.append(
            {
                "metric_position": limit["metric_position"],
                "metric_name": limit["metric_name"],
                "full_run_aggregation": limit["full_run_aggregation"],
                "measured_full_run_value": value,
                "f2_full_run": limit["f2_full_run"],
            }
        )
    payload = {name: manifest[name] for name in schema["ordered_member_names"][:-1]}
    _require(
        manifest["constructive_pilot_manifest_id"]
        == _semantic_id(schema["identity_domain"], payload),
        "MANIFEST_IDENTITY",
    )
    return manifest_raw, case_records, f2_reconciliation


def _parse_pytest(
    completed: subprocess.CompletedProcess[bytes], expected: int
) -> dict[str, int]:
    _require(
        completed.returncode == 0,
        "PYTEST_FAILED",
        completed.stdout.decode(errors="replace"),
    )
    combined = completed.stdout + completed.stderr
    match = re.search(rb"(\d+) passed(?:, (\d+) skipped)? in ", combined)
    _require(match is not None, "PYTEST_SUMMARY_MISSING")
    passed = int(match.group(1))
    skipped = int(match.group(2) or b"0")
    _require(passed == expected and skipped == 0, "PYTEST_COUNT_DRIFT")
    return {"passed": passed, "failed": 0, "skipped": skipped}


def _runtime_review(
    root: pathlib.Path,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    with tempfile.TemporaryDirectory(prefix="a4-p6-r-review-") as directory:
        base = pathlib.Path(directory)
        first = base / "first"
        second = base / "second"
        _success(_run_runner(root, "write", first), "FIRST_WRITE")
        first_manifest, cases, f2 = _validate_pilot(root, first)
        first_snapshot = _snapshot(first)
        _success(_run_runner(root, "check", first), "READ_ONLY_CHECK")
        _require(_snapshot(first) == first_snapshot, "CHECK_MUTATED_OUTPUT")
        _success(_run_runner(root, "write", second), "SECOND_WRITE")
        second_manifest, second_cases, second_f2 = _validate_pilot(root, second)
        _require(first_manifest == second_manifest, "MANIFEST_NONDETERMINISTIC")
        _require(_snapshot(second) == first_snapshot, "CLOSURE_NONDETERMINISTIC")
        _require(cases == second_cases and f2 == second_f2, "LEDGER_NONDETERMINISTIC")

        invalid = subprocess.run(
            [sys.executable, "-I", "-S", "-B", str(root / RUNNER), "--invalid"],
            cwd=root,
            check=False,
            capture_output=True,
            env=_environment(),
            timeout=30,
        )
        _reject(invalid, "INVALID_CLI")
        existing = base / "existing"
        existing.mkdir(mode=0o700)
        marker = existing / "owner"
        marker.write_bytes(b"preserve")
        marker.chmod(0o600)
        before = _snapshot(existing)
        _reject(_run_runner(root, "write", existing), "EXISTING_WRITE")
        _reject(_run_runner(root, "check", existing), "MALFORMED_CHECK")
        _require(_snapshot(existing) == before, "REJECT_MODE_MUTATED_OUTPUT")

    qualification = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(QUALIFICATION_TEST)],
        cwd=root,
        check=False,
        capture_output=True,
        env={**_environment(), "PATH": os.environ.get("PATH", "")},
        timeout=1_800,
    )
    a4_t = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(A4_T_TEST)],
        cwd=root,
        check=False,
        capture_output=True,
        env={**_environment(), "PATH": os.environ.get("PATH", "")},
        timeout=900,
    )
    evidence = {
        "direct_parent_transaction": {
            "pilot_runs": 2,
            "producer_child_runs": 12,
            "verifier_child_runs": 12,
            "byte_determinism": "VERIFIED",
            "candidate_immutability": "VERIFIED",
            "read_only_check": "VERIFIED",
            "all_or_nothing_publication": "VERIFIED",
        },
        "qualification_suite": _parse_pytest(qualification, 7),
        "frozen_role_contract_suite": _parse_pytest(a4_t, 64),
        "public_rejection_checks": {
            "invalid_cli": "REJECTED",
            "existing_write_root": "REJECTED_UNCHANGED",
            "malformed_check_root": "REJECTED_UNCHANGED",
        },
    }
    return evidence, cases, f2


def _seal_report(report: dict[str, Any]) -> dict[str, Any]:
    payload = {
        name: value
        for name, value in report.items()
        if name != "parent_pilot_runner_acceptance_report_id"
    }
    report["parent_pilot_runner_acceptance_report_id"] = _semantic_id(
        REPORT_DOMAIN, payload
    )
    return report


def _validate_report_identity(report: dict[str, Any]) -> None:
    identity = report.get("parent_pilot_runner_acceptance_report_id")
    payload = {
        name: value
        for name, value in report.items()
        if name != "parent_pilot_runner_acceptance_report_id"
    }
    _require(
        identity == _semantic_id(REPORT_DOMAIN, payload), "REPORT_IDENTITY_INVALID"
    )


def build_report(root: pathlib.Path, *, execute_runtime: bool) -> dict[str, Any]:
    static = _static_review(root)
    p_report = _load(root / PRODUCER_REPORT)
    runtime = None
    cases = []
    f2 = []
    if execute_runtime:
        runtime, cases, f2 = _runtime_review(root)
    report = {
        "acceptance_report_version": REPORT_VERSION,
        "correction_subgate": "A4-P6-R",
        "formal_stage1_state": "NO-GO",
        "historical_checkpoint": {
            "a4_p6_p_report": static["descriptors"][PRODUCER_REPORT],
            "a4_p6_p_report_id": p_report["separate_producer_acceptance_report_id"],
            "runner_absent_at_a4_p6_p_acceptance": True,
        },
        "runner_source": static["descriptors"][RUNNER],
        "producer_source": static["descriptors"][PRODUCER],
        "verifier_source": static["descriptors"][VERIFIER],
        "qualification_test_source": static["descriptors"][QUALIFICATION_TEST],
        "static_isolation": {
            name: value for name, value in static.items() if name != "descriptors"
        },
        "runtime_evidence": runtime,
        "ordered_case_acceptance_records": cases,
        "ordered_full_run_f2_reconciliation_records": f2,
        "parent_runner_state": "ACCEPTED" if execute_runtime else "UNDER_REVIEW",
        "review_decision": (
            "ACCEPTED" if execute_runtime else "STATIC_PREFLIGHT_ONLY_NOT_ACCEPTED"
        ),
        "next_subgate": "A4-P6-E" if execute_runtime else "A4-P6-R",
        "source_marker": SOURCE_MARKER,
    }
    return _seal_report(report)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", required=True)
    parser.add_argument("--report-out", required=True)
    return parser.parse_args()


def main() -> int:
    arguments = _arguments()
    root = pathlib.Path(arguments.repository_root)
    output = pathlib.Path(arguments.report_out)
    try:
        _require(root.is_absolute() and root.is_dir(), "ROOT_INVALID")
        _require(output.is_absolute() and not output.exists(), "REPORT_OUTPUT_INVALID")
        report = build_report(root, execute_runtime=True)
        _validate_report_identity(report)
        output.write_bytes(_pretty_bytes(report))
    except (ReviewFailure, OSError, ValueError, TypeError) as error:
        sys.stderr.write(f"A4_P6_R_REVIEW_FAILED: {error}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

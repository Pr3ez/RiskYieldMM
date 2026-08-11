#!/usr/bin/env python3
"""Independent A4-P6-E six-case end-to-end release adjudication.

The reviewer never imports the accepted runner, producer, verifier, their
tests, or the A4-P6-R reviewer. It reconstructs the frozen predecessor packet
and executes the predecessor reviewer twice through its CLI. The deterministic
result may release only a versioned A4-R475 implementation, never an immediate
all-case-readiness claim for the six-case binaries.
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
from typing import Any

SOURCE_MARKER = "INDEPENDENT_A4_P6_E_SIX_CASE_END_TO_END_REVIEWER_V1"
ERROR_PREFIX = "RAW_V8_STEP2_MAXIMUM_PROTOCOL_V2_SIX_CASE_END_TO_END_"
REPORT_VERSION = (
    "riskyieldmm.raw_v8_step2.maximum_protocol_v2."
    "six_case_end_to_end_acceptance_report.v1"
)
REPORT_DOMAIN = (
    "RiskYieldMMRawV8Step2MaximumProtocolV2SixCaseEndToEndAcceptanceReportV1"
)
R_REPORT_DOMAIN = (
    "RiskYieldMMRawV8Step2MaximumProtocolV2ParentPilotRunnerAcceptanceReportV1"
)
P_REPORT_DOMAIN = (
    "RiskYieldMMStep2MaximumProtocolV2SeparateProducerExpansionAcceptanceReportV1"
    "V4_9F_RawV8"
)
TARGET_DOMAIN = "RiskYieldMMStep2Case435ExactSixCaseTargetDeltaV1V4_9F_RawV8"

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
TARGET = pathlib.Path(
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "case435_six_case_target_delta_v49f.json"
)
MANIFEST = pathlib.Path(
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_finalization_manifest_v49f.json"
)
SEED = pathlib.Path(
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.json"
)
P_REPORT = pathlib.Path(
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "separate_producer_expansion_acceptance_report_v49f.json"
)
R_QUALIFICATION_TEST = pathlib.Path(
    "tests/test_raw_v8_step2_maximum_protocol_v2_parent_pilot_runner_v49f.py"
)
R_REVIEWER = pathlib.Path(
    "scripts/tests/review_raw_v8_step2_maximum_protocol_v2_parent_pilot_runner_v49f.py"
)
R_REPORT = pathlib.Path(
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "parent_pilot_runner_acceptance_report_v49f.json"
)
R_ACCEPTANCE_TEST = pathlib.Path(
    "tests/test_raw_v8_step2_maximum_protocol_v2_parent_pilot_runner_acceptance_v49f.py"
)
R_ACCEPTANCE_DOC = pathlib.Path(
    "docs/research/v4_9f_a2_raw_v8_step2_v2_"
    "parent_pilot_runner_acceptance_2026-08-10.md"
)

PILOT_CASES = (5, 24, 54, 69, 435, 475)
QUALIFICATION_RULE = "ALL_SIX_CASES_PASS_TWICE_BYTE_IDENTICALLY_UNDER_IMMUTABLE_F2"
EXPECTED_R_REPORT_ID = (
    "ee39ba2ee328f20774ed3c678d6bf9edf4790a68a587c591828813c358f0ca9b"
)
EXPECTED_P_REPORT_ID = (
    "defe27a1fafa0c1b37f9e1cf5498b14bb662cc2724dec9660abdb86f78ef9ed6"
)
EXPECTED_TARGET_ID = "a000285d1bedd88306786ea33e1be9cc7d2a8459fe75b20c045f7174d52cc072"
EXPECTED_CASE_LEDGER_SHA256 = (
    "754a3e36baf38cfd8609dff77a4da508d1f28784b7d48193b277c54406bc084f"
)
EXPECTED_F2_LEDGER_SHA256 = (
    "c25a10ce30aab285e4a771fb59910feb290db3eb7b34a469960b29ce5d8313f6"
)

EXPECTED_STATIC_ARTIFACTS = {
    RUNNER: (
        50_461,
        "5f1997b4e689a14cbae0a340fce2f320bb058eb9dd04449897ff3dfdf8de7ad7",
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
    TARGET: (
        4_768,
        "394da62c1b5146990b2769feaefa1c06c75387ab7a38ec410ec7e327699b340b",
    ),
    MANIFEST: (
        15_560,
        "0136fba014287605336193f782b4885f16e0163000d36429ceb0dfaf0cea52e0",
    ),
    SEED: (
        13_419_905,
        "a75a2f352e8513b7ff0043693a0c65ebbf4bc6f06859354789af69e1162b0e4f",
    ),
    P_REPORT: (
        12_583,
        "2ef2a621df51f5193108a61ed5b639ab48378b9e5fd87daf4cfbd619a9fb20c8",
    ),
    R_QUALIFICATION_TEST: (
        17_493,
        "431f3ea5f41c87a5635cb2b5b44f24c548ecc4983c8c3acd02a6b5ab2d7a976c",
    ),
    R_REVIEWER: (
        25_387,
        "22565dfb4456823377bcea41790888531f0def2d645c7dd4a2d6f272c0bd26eb",
    ),
    R_REPORT: (
        12_969,
        "ae315492c9a7fa24968c3132e5e0f9982693175922db845312a74f3e61e0487a",
    ),
    R_ACCEPTANCE_TEST: (
        6_676,
        "b223ceefc3837e5d7f90827f281f1457038f681d95a0b46585951e6eebfc24a0",
    ),
    R_ACCEPTANCE_DOC: (
        6_864,
        "1d3182dbd6991ce3226b03392ce4d063f68460bff00bb9f8bfb432e9fc427d9d",
    ),
}


class ReviewFailure(ValueError):
    """Independent release reviewer rejection."""


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


def _load(path: pathlib.Path) -> tuple[dict[str, Any], bytes]:
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
    _require(raw == _pretty_bytes(value), "JSON_ENCODING_INVALID", str(path))
    return value, raw


def _descriptor(root: pathlib.Path, relative: pathlib.Path) -> dict[str, Any]:
    path = root / relative
    _require(
        path.is_file() and not path.is_symlink(), "ARTIFACT_INVALID", str(relative)
    )
    raw = path.read_bytes()
    expected_octets, expected_hash = EXPECTED_STATIC_ARTIFACTS[relative]
    _require(
        len(raw) == expected_octets and _sha256(raw) == expected_hash,
        "ARTIFACT_DRIFT",
        str(relative),
    )
    return {
        "repository_relative_path": relative.as_posix(),
        "raw_octets": len(raw),
        "raw_sha256": _sha256(raw),
    }


def _is_hash(value: Any) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _expected_descriptor(relative: pathlib.Path) -> dict[str, Any]:
    octets, digest = EXPECTED_STATIC_ARTIFACTS[relative]
    return {
        "repository_relative_path": relative.as_posix(),
        "raw_octets": octets,
        "raw_sha256": digest,
    }


def _payload_identity(value: dict[str, Any], member: str, domain: str) -> str:
    payload = {name: item for name, item in value.items() if name != member}
    identity = _semantic_id(domain, payload)
    _require(value.get(member) == identity, "PREDECESSOR_IDENTITY_INVALID", member)
    return identity


def _source_imports(source: str) -> set[str]:
    tree = ast.parse(source)
    imports = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imports.update(
        node.module.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    )
    return imports


def _static_review(root: pathlib.Path) -> dict[str, dict[str, Any]]:
    descriptors = {
        relative.as_posix(): _descriptor(root, relative)
        for relative in EXPECTED_STATIC_ARTIFACTS
    }
    reviewer_source = (root / R_REVIEWER).read_text(encoding="utf-8")
    _require(
        "INDEPENDENT_A4_P6_R_PARENT_PILOT_RUNNER_REVIEWER_V1" in reviewer_source,
        "R_REVIEWER_MARKER_INVALID",
    )
    _require(
        "importlib" not in _source_imports(reviewer_source), "R_REVIEWER_IMPORT_INVALID"
    )
    for marker, path in (
        ("PARENT_OWNED_V2_CONSTRUCTIVE_PILOT_RUNNER_V1", RUNNER),
        ("SEPARATE_V2_CONSTRUCTIVE_PRODUCER_V1", PRODUCER),
        ("INDEPENDENT_V2_CONSTRUCTIVE_VERIFIER_V1", VERIFIER),
    ):
        _require(
            marker in (root / path).read_text(encoding="utf-8"), "ROLE_MARKER_INVALID"
        )
    return descriptors


def _validate_predecessor(
    root: pathlib.Path,
    descriptors: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    r_report, _ = _load(root / R_REPORT)
    _require(
        set(r_report)
        == {
            "acceptance_report_version",
            "correction_subgate",
            "formal_stage1_state",
            "historical_checkpoint",
            "next_subgate",
            "ordered_case_acceptance_records",
            "ordered_full_run_f2_reconciliation_records",
            "parent_pilot_runner_acceptance_report_id",
            "parent_runner_state",
            "producer_source",
            "qualification_test_source",
            "review_decision",
            "runner_source",
            "runtime_evidence",
            "source_marker",
            "static_isolation",
            "verifier_source",
        },
        "R_REPORT_SCHEMA_INVALID",
    )
    r_id = _payload_identity(
        r_report,
        "parent_pilot_runner_acceptance_report_id",
        R_REPORT_DOMAIN,
    )
    _require(r_id == EXPECTED_R_REPORT_ID, "R_REPORT_ID_INVALID")
    _require(
        r_report["acceptance_report_version"]
        == "riskyieldmm.raw_v8_step2.maximum_protocol_v2."
        "parent_pilot_runner_acceptance_report.v1"
        and r_report["correction_subgate"] == "A4-P6-R"
        and r_report["parent_runner_state"] == "ACCEPTED"
        and r_report["review_decision"] == "ACCEPTED"
        and r_report["formal_stage1_state"] == "NO-GO"
        and r_report["next_subgate"] == "A4-P6-E",
        "R_REPORT_STATE_INVALID",
    )
    for member, relative in (
        ("runner_source", RUNNER),
        ("producer_source", PRODUCER),
        ("verifier_source", VERIFIER),
        ("qualification_test_source", R_QUALIFICATION_TEST),
    ):
        _require(
            r_report[member] == descriptors[relative.as_posix()],
            "R_REPORT_SOURCE_INVALID",
            member,
        )

    p_report, _ = _load(root / P_REPORT)
    p_id = _payload_identity(
        p_report,
        "separate_producer_acceptance_report_id",
        P_REPORT_DOMAIN,
    )
    _require(p_id == EXPECTED_P_REPORT_ID, "P_REPORT_ID_INVALID")
    _require(
        p_report["correction_subgate"] == "A4-P6-P"
        and p_report["review_decision"] == "ACCEPTED"
        and p_report["next_subgate"] == "A4-P6-R",
        "P_REPORT_STATE_INVALID",
    )
    historical = r_report["historical_checkpoint"]
    _require(
        historical
        == {
            "a4_p6_p_report": descriptors[P_REPORT.as_posix()],
            "a4_p6_p_report_id": EXPECTED_P_REPORT_ID,
            "runner_absent_at_a4_p6_p_acceptance": True,
        },
        "R_REPORT_HISTORY_INVALID",
    )

    expected_runtime = {
        "direct_parent_transaction": {
            "all_or_nothing_publication": "VERIFIED",
            "byte_determinism": "VERIFIED",
            "candidate_immutability": "VERIFIED",
            "pilot_runs": 2,
            "producer_child_runs": 12,
            "read_only_check": "VERIFIED",
            "verifier_child_runs": 12,
        },
        "frozen_role_contract_suite": {"failed": 0, "passed": 64, "skipped": 0},
        "public_rejection_checks": {
            "existing_write_root": "REJECTED_UNCHANGED",
            "invalid_cli": "REJECTED",
            "malformed_check_root": "REJECTED_UNCHANGED",
        },
        "qualification_suite": {"failed": 0, "passed": 7, "skipped": 0},
    }
    _require(r_report["runtime_evidence"] == expected_runtime, "R_RUNTIME_INVALID")
    _require(
        r_report["static_isolation"]
        == {
            "accepted_answer_literals": False,
            "allowed_imports": [
                "hashlib",
                "json",
                "os",
                "pathlib",
                "resource",
                "select",
                "signal",
                "stat",
                "sys",
                "tempfile",
                "time",
            ],
            "dynamic_code_loading": False,
            "fixed_execve_process_boundary": True,
            "reviewed_role_imports": False,
        },
        "R_ISOLATION_INVALID",
    )

    target, _ = _load(root / TARGET)
    target_id = _payload_identity(target, "successor_six_case_target_id", TARGET_DOMAIN)
    _require(target_id == EXPECTED_TARGET_ID, "TARGET_ID_INVALID")
    qualification = target["qualification_contract"]
    _require(
        qualification["all_six_case_acceptance_rule"] == QUALIFICATION_RULE,
        "QUALIFICATION_RULE_INVALID",
    )
    target_rows = target["ordered_pilot_case_records"]
    _require(
        [row["pilot_position"] for row in target_rows] == list(range(1, 7))
        and [row["case_position"] for row in target_rows] == list(PILOT_CASES),
        "TARGET_CASE_ORDER_INVALID",
    )

    seed, _ = _load(root / SEED)
    universe = seed["case_universe_catalog"]["ordered_case_bindings"]
    _require(
        len(universe) == 475
        and [row["case_position"] for row in universe] == list(range(1, 476)),
        "CASE_UNIVERSE_INVALID",
    )
    maximum_count = sum(
        row["case_kind"] == "MAXIMUM_PUBLICATION_ROW" for row in universe
    )
    local_count = sum(
        row["case_kind"] == "LOCAL_SHUTDOWN_UNREPRESENTABLE_MINIMALITY"
        for row in universe
    )
    _require(maximum_count == 474 and local_count == 1, "CASE_KIND_COUNTS_INVALID")

    p_ledger = {
        row["case_position"]: row for row in p_report["ordered_case_acceptance_records"]
    }
    r_rows = r_report["ordered_case_acceptance_records"]
    _require(len(p_ledger) == len(r_rows) == 6, "CASE_LEDGER_COUNT_INVALID")
    manifest, _ = _load(root / MANIFEST)
    limits = manifest["ordered_f2_limit_records"]
    _require(len(limits) == 18, "F2_LIMIT_COUNT_INVALID")
    aggregate = [0] * len(limits)
    release_rows = []
    for target_row, r_row in zip(target_rows, r_rows, strict=True):
        case_position = target_row["case_position"]
        p_row = p_ledger.get(case_position)
        _require(p_row is not None, "P_CASE_MISSING", str(case_position))
        _require(
            r_row["pilot_position"] == target_row["pilot_position"]
            and r_row["case_position"] == case_position
            and r_row["logical_count_plan_id"] == target_row["logical_count_plan_id"],
            "R_CASE_TARGET_INVALID",
            str(case_position),
        )
        _require(
            r_row["constructive_candidate_id"] == p_row["constructive_candidate_id"]
            and r_row["verification_receipt_id"] == p_row["verification_receipt_id"]
            and r_row["verified_result_artifact_id"] == p_row["result_artifact_id"]
            and r_row["candidate_root_raw_octets"]
            == p_row["candidate_closure"]["total_raw_octets"]
            and r_row["verified_result_root_raw_octets"]
            == p_row["verified_closure"]["total_raw_octets"]
            and r_row["resource_vector"] == p_row["resource_vector"],
            "R_CASE_PRODUCER_LEDGER_INVALID",
            str(case_position),
        )
        _require(
            _is_hash(r_row["candidate_root_sha256"])
            and _is_hash(r_row["verified_result_root_sha256"]),
            "R_CASE_CLOSURE_HASH_INVALID",
            str(case_position),
        )
        vector = r_row["resource_vector"]
        _require(len(vector) == len(limits), "RESOURCE_VECTOR_LENGTH_INVALID")
        for index, (value, limit) in enumerate(zip(vector, limits, strict=True)):
            _require(
                type(value) is int and 0 <= value <= limit["f2_per_case"],
                "F2_PER_CASE_INVALID",
                f"{case_position}:{limit['metric_name']}",
            )
            if limit["full_run_aggregation"] == "SUM":
                aggregate[index] += value
            else:
                _require(
                    limit["full_run_aggregation"] == "MAXIMUM",
                    "F2_AGGREGATION_INVALID",
                )
                aggregate[index] = max(aggregate[index], value)
        release_rows.append(
            {
                "pilot_position": target_row["pilot_position"],
                "case_position": case_position,
                "case_kind": target_row["case_kind"],
                "coverage_tag": target_row["coverage_tag"],
                "logical_count_plan_id": target_row["logical_count_plan_id"],
                "constructive_candidate_id": r_row["constructive_candidate_id"],
                "verification_receipt_id": r_row["verification_receipt_id"],
                "verified_result_artifact_id": r_row["verified_result_artifact_id"],
                "candidate_root_raw_octets": r_row["candidate_root_raw_octets"],
                "candidate_root_sha256": r_row["candidate_root_sha256"],
                "verified_result_root_raw_octets": r_row[
                    "verified_result_root_raw_octets"
                ],
                "verified_result_root_sha256": r_row["verified_result_root_sha256"],
                "resource_vector": list(vector),
            }
        )

    f2_rows = []
    for measured, limit in zip(aggregate, limits, strict=True):
        _require(
            measured <= limit["f2_full_run"],
            "F2_FULL_RUN_INVALID",
            limit["metric_name"],
        )
        f2_rows.append(
            {
                "metric_position": limit["metric_position"],
                "metric_name": limit["metric_name"],
                "full_run_aggregation": limit["full_run_aggregation"],
                "measured_full_run_value": measured,
                "f2_full_run": limit["f2_full_run"],
            }
        )
    _require(
        r_report["ordered_full_run_f2_reconciliation_records"] == f2_rows,
        "R_F2_RECONCILIATION_INVALID",
    )

    return {
        "r_report": r_report,
        "case_rows": release_rows,
        "f2_rows": f2_rows,
        "qualification_rule": qualification["all_six_case_acceptance_rule"],
        "campaign_surface": {
            "case_universe_count": len(universe),
            "current_pilot_case_count": len(PILOT_CASES),
            "current_pilot_case_positions": list(PILOT_CASES),
            "current_role_surface": "SIX_CASE_ONLY",
            "maximum_publication_case_count": maximum_count,
            "non_pilot_case_count": len(universe) - len(PILOT_CASES),
            "local_minimality_case_count": local_count,
            "release_scope": "VERSIONED_ALL_475_IMPLEMENTATION_THEN_EXECUTION",
            "unchanged_current_binaries_all_case_ready": False,
            "pilot_f2_implies_full_campaign_fit": False,
        },
    }


def _environment() -> dict[str, str]:
    return {
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": os.environ.get("PATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
    }


def _run_r_reviewer(
    root: pathlib.Path,
    output: pathlib.Path,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            str(root / R_REVIEWER),
            "--repository-root",
            str(root),
            "--report-out",
            str(output),
        ],
        cwd=root,
        check=False,
        capture_output=True,
        env=_environment(),
        timeout=3_600,
    )


def _runtime_replay(root: pathlib.Path, stored_report_raw: bytes) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="a4-p6-e-review-") as directory:
        base = pathlib.Path(directory)
        first_path = base / "first.json"
        second_path = base / "second.json"
        first = _run_r_reviewer(root, first_path)
        _require(
            first.returncode == 0 and first.stdout == first.stderr == b"",
            "R_REVIEW_FIRST_FAILED",
            first.stderr.decode(errors="replace"),
        )
        second = _run_r_reviewer(root, second_path)
        _require(
            second.returncode == 0 and second.stdout == second.stderr == b"",
            "R_REVIEW_SECOND_FAILED",
            second.stderr.decode(errors="replace"),
        )
        first_value, first_raw = _load(first_path)
        second_value, second_raw = _load(second_path)
        _require(first_value == second_value, "R_REVIEW_VALUE_NONDETERMINISTIC")
        _require(first_raw == second_raw, "R_REVIEW_BYTES_NONDETERMINISTIC")
        _require(
            first_raw == stored_report_raw,
            "R_REVIEW_FROZEN_REPORT_MISMATCH",
        )
    return {
        "a4_p6_r_reviewer_replays": 2,
        "effective_parent_transactions_replayed": 4,
        "effective_producer_child_runs_replayed": 24,
        "effective_verifier_child_runs_replayed": 24,
        "frozen_report_match": "BOTH_BYTE_IDENTICAL",
        "reviewer_output_determinism": "VERIFIED",
    }


def _release_criteria(execute_runtime: bool) -> list[dict[str, Any]]:
    runtime_state = "PASS" if execute_runtime else "NOT_RUN"
    return [
        {
            "criterion_position": 1,
            "criterion_name": "FROZEN_PREDECESSOR_ARTIFACT_IDENTITIES",
            "criterion_state": "PASS",
            "evidence": "ALL_PINNED_SIZE_AND_SHA256_BINDINGS_MATCH",
        },
        {
            "criterion_position": 2,
            "criterion_name": "A4_P6_R_REPORT_SEMANTIC_IDENTITY",
            "criterion_state": "PASS",
            "evidence": EXPECTED_R_REPORT_ID,
        },
        {
            "criterion_position": 3,
            "criterion_name": "FROZEN_SIX_CASE_QUALIFICATION_RULE",
            "criterion_state": "PASS",
            "evidence": QUALIFICATION_RULE,
        },
        {
            "criterion_position": 4,
            "criterion_name": "TWO_INDEPENDENT_A4_P6_R_REPLAYS",
            "criterion_state": runtime_state,
            "evidence": (
                "BOTH_BYTE_IDENTICAL_TO_FROZEN_REPORT"
                if execute_runtime
                else "RUNTIME_NOT_EXECUTED"
            ),
        },
        {
            "criterion_position": 5,
            "criterion_name": "TRANSACTION_IMMUTABILITY_AND_REJECTION",
            "criterion_state": runtime_state,
            "evidence": (
                "FOUR_REPLAYED_PARENT_TRANSACTIONS_PLUS_PINNED_QUALIFICATION"
                if execute_runtime
                else "RUNTIME_NOT_EXECUTED"
            ),
        },
        {
            "criterion_position": 6,
            "criterion_name": "EXACT_SIX_CASE_LEDGER",
            "criterion_state": runtime_state,
            "evidence": (
                "TARGET_PRODUCER_AND_RUNNER_LEDGERS_AGREE"
                if execute_runtime
                else "RUNTIME_NOT_EXECUTED"
            ),
        },
        {
            "criterion_position": 7,
            "criterion_name": "IMMUTABLE_FULL_RUN_F2_RECONCILIATION",
            "criterion_state": runtime_state,
            "evidence": (
                "ALL_18_PILOT_AGGREGATES_WITHIN_FROZEN_LIMITS"
                if execute_runtime
                else "RUNTIME_NOT_EXECUTED"
            ),
        },
        {
            "criterion_position": 8,
            "criterion_name": "ALL_475_SCOPE_NONCLAIM_AND_VERSIONED_RELEASE",
            "criterion_state": "PASS",
            "evidence": "SIX_CASE_BINARIES_NOT_MISREPRESENTED_AS_ALL_CASE_READY",
        },
    ]


def _seal_report(report: dict[str, Any]) -> dict[str, Any]:
    report.pop("six_case_end_to_end_acceptance_report_id", None)
    report["six_case_end_to_end_acceptance_report_id"] = _semantic_id(
        REPORT_DOMAIN, report
    )
    return report


def _validate_release_report(
    report: dict[str, Any],
    *,
    require_runtime: bool,
) -> None:
    def valid(condition: bool, detail: str) -> None:
        _require(condition, "RELEASE_REPORT_INVALID", detail)

    valid(
        set(report)
        == {
            "acceptance_report_version",
            "campaign_surface",
            "correction_subgate",
            "formal_stage1_state",
            "independent_replay_evidence",
            "next_subgate",
            "ordered_case_release_records",
            "ordered_full_run_f2_reconciliation_records",
            "ordered_release_criteria",
            "predecessor_a4_p6_r",
            "qualification_rule",
            "release_decision",
            "review_decision",
            "six_case_end_to_end_acceptance_report_id",
            "source_marker",
        },
        "schema",
    )
    identity = report["six_case_end_to_end_acceptance_report_id"]
    payload = {
        name: value
        for name, value in report.items()
        if name != "six_case_end_to_end_acceptance_report_id"
    }
    valid(identity == _semantic_id(REPORT_DOMAIN, payload), "identity")
    valid(report["acceptance_report_version"] == REPORT_VERSION, "version")
    valid(report["correction_subgate"] == "A4-P6-E", "subgate")
    valid(report["formal_stage1_state"] == "NO-GO", "formal-state")
    valid(report["source_marker"] == SOURCE_MARKER, "source-marker")
    valid(report["qualification_rule"] == QUALIFICATION_RULE, "rule")
    predecessor = report["predecessor_a4_p6_r"]
    valid(
        set(predecessor)
        == {
            "acceptance_document",
            "acceptance_test",
            "producer",
            "qualification_test",
            "report",
            "report_id",
            "reviewer",
            "runner",
            "verifier",
        }
        and predecessor["report_id"] == EXPECTED_R_REPORT_ID,
        "predecessor",
    )
    for member, relative in (
        ("report", R_REPORT),
        ("reviewer", R_REVIEWER),
        ("acceptance_test", R_ACCEPTANCE_TEST),
        ("acceptance_document", R_ACCEPTANCE_DOC),
        ("runner", RUNNER),
        ("producer", PRODUCER),
        ("verifier", VERIFIER),
        ("qualification_test", R_QUALIFICATION_TEST),
    ):
        valid(predecessor[member] == _expected_descriptor(relative), member)
    valid(
        report["campaign_surface"]
        == {
            "case_universe_count": 475,
            "current_pilot_case_count": 6,
            "current_pilot_case_positions": list(PILOT_CASES),
            "current_role_surface": "SIX_CASE_ONLY",
            "maximum_publication_case_count": 474,
            "non_pilot_case_count": 469,
            "local_minimality_case_count": 1,
            "release_scope": "VERSIONED_ALL_475_IMPLEMENTATION_THEN_EXECUTION",
            "unchanged_current_binaries_all_case_ready": False,
            "pilot_f2_implies_full_campaign_fit": False,
        },
        "campaign-surface",
    )
    case_rows = report["ordered_case_release_records"]
    valid(len(case_rows) == 6, "case-count")
    valid(
        _sha256(_canonical_bytes(case_rows)) == EXPECTED_CASE_LEDGER_SHA256,
        "case-ledger",
    )
    valid(
        [row["pilot_position"] for row in case_rows] == list(range(1, 7))
        and [row["case_position"] for row in case_rows] == list(PILOT_CASES),
        "case-order",
    )
    aggregate = [0] * 18
    for row in case_rows:
        valid(_is_hash(row["logical_count_plan_id"]), "plan-id")
        valid(_is_hash(row["constructive_candidate_id"]), "candidate-id")
        valid(_is_hash(row["verification_receipt_id"]), "receipt-id")
        valid(_is_hash(row["verified_result_artifact_id"]), "result-id")
        valid(_is_hash(row["candidate_root_sha256"]), "candidate-root")
        valid(_is_hash(row["verified_result_root_sha256"]), "result-root")
        vector = row["resource_vector"]
        valid(type(vector) is list and len(vector) == 18, "resource-vector")
        for index, value in enumerate(vector):
            valid(type(value) is int and value >= 0, "resource-value")
            if index in (14, 15, 16):
                aggregate[index] = max(aggregate[index], value)
            else:
                aggregate[index] += value
    f2_rows = report["ordered_full_run_f2_reconciliation_records"]
    valid(len(f2_rows) == 18, "f2-count")
    valid(
        _sha256(_canonical_bytes(f2_rows)) == EXPECTED_F2_LEDGER_SHA256,
        "f2-ledger",
    )
    valid(
        [row["metric_position"] for row in f2_rows] == list(range(1, 19)),
        "f2-order",
    )
    valid(
        [row["full_run_aggregation"] for row in f2_rows]
        == ["SUM"] * 14 + ["MAXIMUM"] * 3 + ["SUM"],
        "f2-modes",
    )
    valid(
        [row["measured_full_run_value"] for row in f2_rows] == aggregate,
        "f2-aggregate",
    )
    valid(
        all(
            type(row["f2_full_run"]) is int
            and row["measured_full_run_value"] <= row["f2_full_run"]
            for row in f2_rows
        ),
        "f2-limits",
    )
    valid(
        report["ordered_release_criteria"] == _release_criteria(require_runtime),
        "criteria",
    )
    if require_runtime:
        valid(
            report["independent_replay_evidence"]
            == {
                "a4_p6_r_reviewer_replays": 2,
                "effective_parent_transactions_replayed": 4,
                "effective_producer_child_runs_replayed": 24,
                "effective_verifier_child_runs_replayed": 24,
                "frozen_report_match": "BOTH_BYTE_IDENTICAL",
                "reviewer_output_determinism": "VERIFIED",
            },
            "runtime",
        )
        valid(report["review_decision"] == "ACCEPTED", "decision")
        valid(
            report["release_decision"]
            == "RELEASED_FOR_A4_R475_VERSIONED_IMPLEMENTATION",
            "release",
        )
        valid(report["next_subgate"] == "A4-R475", "next")
    else:
        valid(report["independent_replay_evidence"] is None, "static-runtime")
        valid(
            report["review_decision"] == "STATIC_PREFLIGHT_ONLY_NOT_ACCEPTED",
            "static-decision",
        )
        valid(report["release_decision"] == "UNDER_REVIEW", "static-release")
        valid(report["next_subgate"] == "A4-P6-E", "static-next")


def build_report(root: pathlib.Path, *, execute_runtime: bool) -> dict[str, Any]:
    descriptors = _static_review(root)
    predecessor = _validate_predecessor(root, descriptors)
    stored_raw = (root / R_REPORT).read_bytes()
    replay = _runtime_replay(root, stored_raw) if execute_runtime else None
    report = {
        "acceptance_report_version": REPORT_VERSION,
        "correction_subgate": "A4-P6-E",
        "predecessor_a4_p6_r": {
            "report": descriptors[R_REPORT.as_posix()],
            "report_id": EXPECTED_R_REPORT_ID,
            "reviewer": descriptors[R_REVIEWER.as_posix()],
            "acceptance_test": descriptors[R_ACCEPTANCE_TEST.as_posix()],
            "acceptance_document": descriptors[R_ACCEPTANCE_DOC.as_posix()],
            "runner": descriptors[RUNNER.as_posix()],
            "producer": descriptors[PRODUCER.as_posix()],
            "verifier": descriptors[VERIFIER.as_posix()],
            "qualification_test": descriptors[R_QUALIFICATION_TEST.as_posix()],
        },
        "qualification_rule": predecessor["qualification_rule"],
        "independent_replay_evidence": replay,
        "ordered_case_release_records": predecessor["case_rows"],
        "ordered_full_run_f2_reconciliation_records": predecessor["f2_rows"],
        "campaign_surface": predecessor["campaign_surface"],
        "ordered_release_criteria": _release_criteria(execute_runtime),
        "review_decision": (
            "ACCEPTED" if execute_runtime else "STATIC_PREFLIGHT_ONLY_NOT_ACCEPTED"
        ),
        "release_decision": (
            "RELEASED_FOR_A4_R475_VERSIONED_IMPLEMENTATION"
            if execute_runtime
            else "UNDER_REVIEW"
        ),
        "formal_stage1_state": "NO-GO",
        "next_subgate": "A4-R475" if execute_runtime else "A4-P6-E",
        "source_marker": SOURCE_MARKER,
    }
    _seal_report(report)
    _validate_release_report(report, require_runtime=execute_runtime)
    return report


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
        output.write_bytes(_pretty_bytes(report))
    except (ReviewFailure, OSError, ValueError, TypeError) as error:
        sys.stderr.write(f"{ERROR_PREFIX}REVIEW_FAILED: {error}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
VERIFIER = (
    ROOT
    / "scripts/tests/verify_raw_v8_step2_maximum_protocol_v2_"
    "all_case_candidate_v49f.py"
)
REVIEWER = (
    ROOT
    / "scripts/tests/review_raw_v8_step2_maximum_protocol_v2_"
    "all_case_verifier_foundation_v49f.py"
)
REPORT = (
    ROOT
    / "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "all_case_verifier_foundation_acceptance_report_v49f.json"
)
EXPECTED = {
    VERIFIER: (
        42_659,
        "15adb9fd5c427c1e1e96ff630e13b36d3f385f12eaf68a388a5da7be48dbf5aa",
    ),
    REVIEWER: (
        24_299,
        "b835f426b9e15cbb4f2dadb7af8bb4a159356275a2f4c30557da1da00b080544",
    ),
    REPORT: (
        3_776,
        "1a8a5e8500e29d68d45a87aba4955c8041248b42509cf4d675f3ab02a64f8e59",
    ),
}
EXPECTED_REPORT_ID = (
    "127784d23829d3b92179596d5d058d5305c0075208b8a809109e4de49663973f"
)
REPORT_DOMAIN = (
    "RiskYieldMMRawV8Step2MaximumProtocolV2AllCaseVerifierFoundationAcceptanceReportV1"
)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_bytes(value) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _pretty_bytes(value) -> bytes:
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


def _semantic_id(domain: str, payload) -> str:
    return _sha256(_canonical_bytes({"domain": domain, "payload": payload}))


def _load_reviewer():
    specification = importlib.util.spec_from_file_location(
        "a4_r475_v0_foundation_reviewer",
        REVIEWER,
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def _reseal_report(report):
    payload = {
        name: value
        for name, value in report.items()
        if name != "all_case_verifier_foundation_acceptance_report_id"
    }
    report["all_case_verifier_foundation_acceptance_report_id"] = _semantic_id(
        REPORT_DOMAIN,
        payload,
    )


def test_acceptance_artifact_identities_are_exact() -> None:
    for path, expected in EXPECTED.items():
        assert path.is_file() and not path.is_symlink()
        raw = path.read_bytes()
        assert (len(raw), _sha256(raw)) == expected


def test_report_identity_and_scope_are_exact() -> None:
    report = json.loads(REPORT.read_bytes())
    payload = {
        name: value
        for name, value in report.items()
        if name != "all_case_verifier_foundation_acceptance_report_id"
    }
    assert report["all_case_verifier_foundation_acceptance_report_id"] == (
        EXPECTED_REPORT_ID
    )
    assert _semantic_id(REPORT_DOMAIN, payload) == EXPECTED_REPORT_ID
    assert report["review_decision"] == "ACCEPTED_FOUNDATION_ONLY"
    assert report["accepted_constructive_case_count"] == 0
    assert report["fail_first_boundary"] == {
        "accepted_constructive_case_count": 0,
        "candidate_access_forbidden": True,
        "expected_remaining_role_failures": 2,
        "versioned_producer_present": False,
        "versioned_runner_present": False,
        "versioned_verifier_present": True,
    }
    assert report["next_bounded_packet"] == "A4-R475-V1"
    assert report["formal_stage1_state"] == "NO-GO"


def test_independent_reviewer_check_mode_reproduces_report() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            str(REVIEWER),
            "--repository-root",
            str(ROOT),
            "--verifier",
            str(VERIFIER),
            "--check-report",
            str(REPORT),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert completed.stdout == completed.stderr == ""


def test_independent_reviewer_reconstructs_without_verifier_import() -> None:
    module = _load_reviewer()
    report = module.build_report(ROOT, VERIFIER)
    assert report["all_case_verifier_foundation_acceptance_report_id"] == (
        EXPECTED_REPORT_ID
    )
    assert report["independent_case_reconstruction"]["case_count"] == 475
    assert report["independent_case_reconstruction"][
        "successor_plan_case_positions"
    ] == [435]
    source = REVIEWER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported.update(
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    )
    assert all("verify_raw_v8_step2" not in name for name in imported)
    assert "importlib" not in imported


@pytest.mark.parametrize(
    "mutation",
    [
        lambda report: report.update({"accepted_constructive_case_count": 1}),
        lambda report: report["fail_first_boundary"].update(
            {"versioned_producer_present": True}
        ),
        lambda report: report.update({"next_bounded_packet": "A4-R475-V2"}),
        lambda report: report["resource_evidence"].update(
            {"pinned_input_octet_headroom": 1}
        ),
    ],
)
def test_coherently_resealed_acceptance_overclaims_are_rejected(
    tmp_path: Path,
    mutation,
) -> None:
    hostile = copy.deepcopy(json.loads(REPORT.read_bytes()))
    mutation(hostile)
    _reseal_report(hostile)
    hostile_path = tmp_path / "hostile-report.json"
    hostile_path.write_bytes(_pretty_bytes(hostile))
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            str(REVIEWER),
            "--repository-root",
            str(ROOT),
            "--verifier",
            str(VERIFIER),
            "--check-report",
            str(hostile_path),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 1
    assert "REPORT_DRIFT" in completed.stderr


def test_resource_and_runtime_evidence_match_immutable_limits() -> None:
    report = json.loads(REPORT.read_bytes())
    assert report["resource_evidence"] == {
        "authority_file_count": 18,
        "authority_file_headroom": 46,
        "f0_limits_raised": False,
        "pinned_input_octet_headroom": 50_390_876,
        "pinned_input_octets": 16_717_988,
    }
    assert report["typed_runtime_replay"]["replay_count"] == 2
    assert report["typed_runtime_replay"]["byte_identical"] is True
    assert report["typed_runtime_replay"]["rule_count"] == 42
    assert report["typed_runtime_replay"]["application_count"] == 8
    assert report["verifier_cli_replay"]["replay_count"] == 2
    assert report["verifier_cli_replay"]["candidate_paths_opened"] == 0
    assert report["verifier_cli_replay"]["output_paths_created"] == 0

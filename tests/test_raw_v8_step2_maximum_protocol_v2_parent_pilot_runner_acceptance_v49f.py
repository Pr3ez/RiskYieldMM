from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
from types import ModuleType

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
REVIEWER_PATH = (
    ROOT / "scripts/tests/review_raw_v8_step2_maximum_protocol_v2_"
    "parent_pilot_runner_v49f.py"
)
REPORT_PATH = (
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "parent_pilot_runner_acceptance_report_v49f.json"
)
EXPECTED_REVIEWER = (
    25_387,
    "22565dfb4456823377bcea41790888531f0def2d645c7dd4a2d6f272c0bd26eb",
)
EXPECTED_REPORT = (
    12_969,
    "ae315492c9a7fa24968c3132e5e0f9982693175922db845312a74f3e61e0487a",
)
EXPECTED_REPORT_ID = "ee39ba2ee328f20774ed3c678d6bf9edf4790a68a587c591828813c358f0ca9b"


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _load(path: pathlib.Path) -> dict[str, object]:
    return json.loads(path.read_bytes())


def _load_reviewer() -> ModuleType:
    specification = importlib.util.spec_from_file_location(
        "a4_p6_r_reviewer", REVIEWER_PATH
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


REVIEWER = _load_reviewer()


def test_acceptance_artifact_bytes_identity_and_gate_transition_are_exact() -> None:
    for path, (octets, digest) in (
        (REVIEWER_PATH, EXPECTED_REVIEWER),
        (REPORT_PATH, EXPECTED_REPORT),
    ):
        raw = path.read_bytes()
        assert len(raw) == octets
        assert _sha256(raw) == digest
    report = _load(REPORT_PATH)
    REVIEWER._validate_report_identity(report)
    assert report["parent_pilot_runner_acceptance_report_id"] == EXPECTED_REPORT_ID
    assert report["correction_subgate"] == "A4-P6-R"
    assert report["review_decision"] == "ACCEPTED"
    assert report["parent_runner_state"] == "ACCEPTED"
    assert report["formal_stage1_state"] == "NO-GO"
    assert report["next_subgate"] == "A4-P6-E"


def test_static_preflight_is_not_misrepresented_as_acceptance() -> None:
    report = REVIEWER.build_report(ROOT, execute_runtime=False)
    REVIEWER._validate_report_identity(report)
    assert report["review_decision"] == "STATIC_PREFLIGHT_ONLY_NOT_ACCEPTED"
    assert report["parent_runner_state"] == "UNDER_REVIEW"
    assert report["next_subgate"] == "A4-P6-R"
    assert report["runtime_evidence"] is None
    assert report["ordered_case_acceptance_records"] == []
    assert report["ordered_full_run_f2_reconciliation_records"] == []


def test_full_independent_reviewer_replay_matches_frozen_report(
    tmp_path: pathlib.Path,
) -> None:
    output = tmp_path / "acceptance-report.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(REVIEWER_PATH),
            "--repository-root",
            str(ROOT),
            "--report-out",
            str(output),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        env={
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PATH": os.environ.get("PATH", ""),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
        },
        timeout=3_600,
    )
    assert completed.returncode == 0, completed.stderr.decode(errors="replace")
    assert completed.stdout == completed.stderr == b""
    assert output.read_bytes() == REPORT_PATH.read_bytes()


def test_report_binds_exact_two_run_transaction_and_green_contracts() -> None:
    report = _load(REPORT_PATH)
    runtime = report["runtime_evidence"]
    assert runtime["direct_parent_transaction"] == {
        "all_or_nothing_publication": "VERIFIED",
        "byte_determinism": "VERIFIED",
        "candidate_immutability": "VERIFIED",
        "pilot_runs": 2,
        "producer_child_runs": 12,
        "read_only_check": "VERIFIED",
        "verifier_child_runs": 12,
    }
    assert runtime["qualification_suite"] == {
        "failed": 0,
        "passed": 7,
        "skipped": 0,
    }
    assert runtime["frozen_role_contract_suite"] == {
        "failed": 0,
        "passed": 64,
        "skipped": 0,
    }
    assert len(report["ordered_case_acceptance_records"]) == 6
    assert len(report["ordered_full_run_f2_reconciliation_records"]) == 18


def test_full_run_f2_modes_values_and_limits_are_exact() -> None:
    report = _load(REPORT_PATH)
    rows = report["ordered_full_run_f2_reconciliation_records"]
    assert [row["metric_position"] for row in rows] == list(range(1, 19))
    assert [row["measured_full_run_value"] for row in rows] == [
        6,
        4_239_080,
        375,
        2_318,
        8_756_229,
        17,
        375,
        254_204,
        1_840_387,
        2_057_687,
        3_473_350,
        22,
        12_533,
        139,
        17,
        137,
        50_016,
        87_245,
    ]
    assert all(row["measured_full_run_value"] <= row["f2_full_run"] for row in rows)
    assert [row["full_run_aggregation"] for row in rows[-4:]] == [
        "MAXIMUM",
        "MAXIMUM",
        "MAXIMUM",
        "SUM",
    ]


def test_report_identity_rejects_resealed_gate_or_resource_drift() -> None:
    report = copy.deepcopy(_load(REPORT_PATH))
    report["next_subgate"] = "A4-R475"
    with pytest.raises(REVIEWER.ReviewFailure, match="REPORT_IDENTITY_INVALID"):
        REVIEWER._validate_report_identity(report)
    report = copy.deepcopy(_load(REPORT_PATH))
    report["ordered_full_run_f2_reconciliation_records"][0][
        "measured_full_run_value"
    ] = 5
    with pytest.raises(REVIEWER.ReviewFailure, match="REPORT_IDENTITY_INVALID"):
        REVIEWER._validate_report_identity(report)


def test_reviewer_source_is_independent_of_reviewed_roles_and_tests() -> None:
    source = REVIEWER_PATH.read_text(encoding="utf-8")
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
    assert imports <= {
        "__future__",
        "argparse",
        "ast",
        "hashlib",
        "json",
        "os",
        "pathlib",
        "re",
        "stat",
        "subprocess",
        "sys",
        "tempfile",
        "typing",
    }
    assert "importlib" not in imports
    assert REVIEWER.SOURCE_MARKER in source
    assert "spec_from_file_location" not in source

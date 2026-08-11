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
    "separate_producer_expansion_v49f.py"
)
REPORT_PATH = (
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "separate_producer_expansion_acceptance_report_v49f.json"
)
EXPECTED_REVIEWER = (
    32_070,
    "7067aeae07056e09b6ee5bfb1c059744fab55453c3e41431313e6073e345cdb5",
)
EXPECTED_REPORT = (
    12_583,
    "2ef2a621df51f5193108a61ed5b639ab48378b9e5fd87daf4cfbd619a9fb20c8",
)
EXPECTED_REPORT_ID = "defe27a1fafa0c1b37f9e1cf5498b14bb662cc2724dec9660abdb86f78ef9ed6"


def _load_reviewer() -> ModuleType:
    specification = importlib.util.spec_from_file_location(
        "a4_p6_p_reviewer", REVIEWER_PATH
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


REVIEWER = _load_reviewer()


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _load(path: pathlib.Path) -> dict[str, object]:
    return json.loads(path.read_bytes())


def test_acceptance_artifact_bytes_and_semantic_identity_are_exact() -> None:
    for path, (octets, digest) in (
        (REVIEWER_PATH, EXPECTED_REVIEWER),
        (REPORT_PATH, EXPECTED_REPORT),
    ):
        raw = path.read_bytes()
        assert len(raw) == octets
        assert _sha256(raw) == digest
    report = _load(REPORT_PATH)
    REVIEWER._validate_report_identity(report)
    assert report["separate_producer_acceptance_report_id"] == EXPECTED_REPORT_ID
    assert report["review_decision"] == "ACCEPTED"
    assert report["formal_stage1_state"] == "NO-GO"
    assert report["next_subgate"] == "A4-P6-R"
    assert report["parent_runner_state"] == "ABSENT_AND_HELD"


def test_static_preflight_reconstructs_current_and_historical_boundaries() -> None:
    report = REVIEWER.build_report(ROOT, execute_runtime=False)
    REVIEWER._validate_report_identity(report)
    assert report["review_decision"] == "STATIC_PREFLIGHT_ONLY_NOT_ACCEPTED"
    assert report["next_subgate"] == "A4-P6-P"
    assert report["runtime_evidence"] is None
    assert report["predecessor_case5_compatibility"] is None
    assert report["historical_checkpoint"]["a4_p6_v_a_report_id"] == (
        REVIEWER.EXPECTED_V_A_REPORT_ID
    )
    assert [
        row["case_position"] for row in report["ordered_case_acceptance_records"]
    ] == [
        5,
        24,
        54,
        69,
        435,
        475,
    ]


def test_full_reviewer_replay_matches_frozen_report(tmp_path: pathlib.Path) -> None:
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
        timeout=1_800,
    )
    assert completed.returncode == 0, completed.stderr.decode()
    assert completed.stdout == completed.stderr == b""
    assert output.read_bytes() == REPORT_PATH.read_bytes()


def test_report_binds_two_pass_replay_and_expected_red_boundaries() -> None:
    report = _load(REPORT_PATH)
    runtime = report["runtime_evidence"]
    assert runtime["direct_packed_successor_replay"] == {
        "byte_determinism": "VERIFIED",
        "candidate_immutability": "VERIFIED",
        "case_count": 6,
        "producer_runs": 12,
        "verifier_runs": 12,
    }
    assert runtime["successor_qualification"] == {
        "failed": 0,
        "passed": 17,
        "skipped": 0,
    }
    assert runtime["a4_t_expected_red"]["failed"] == 1
    assert runtime["a4_p6_predecessor_expected_red"]["failed"] == 6
    assert len(report["ordered_case_acceptance_records"]) == 6


def test_report_identity_rejects_resealed_state_drift() -> None:
    report = copy.deepcopy(_load(REPORT_PATH))
    report["next_subgate"] = "A4-P6-E"
    with pytest.raises(REVIEWER.ReviewFailure, match="REPORT_IDENTITY_INVALID"):
        REVIEWER._validate_report_identity(report)


def test_green_parser_rejects_changed_pass_count() -> None:
    completed = subprocess.CompletedProcess(
        args=[], returncode=0, stdout=b"16 passed in 1.00s\n", stderr=b""
    )
    with pytest.raises(REVIEWER.ReviewFailure, match="QUALIFICATION_FAILED"):
        REVIEWER._parse_green(completed, 17)


def test_expected_red_parser_rejects_an_extra_failure() -> None:
    completed = subprocess.CompletedProcess(
        args=[],
        returncode=1,
        stdout=(
            b"A4_T_PARENT_PILOT_RUNNER_MISSING\n"
            b"A4_T_UNEXPECTED_FAILURE\n"
            b"1 failed, 61 passed, 2 skipped in 1.00s\n"
        ),
        stderr=b"",
    )
    with pytest.raises(REVIEWER.ReviewFailure, match="EXPECTED_RED_DRIFT"):
        REVIEWER._parse_expected_red(
            completed,
            passed=61,
            skipped=2,
            failures=("A4_T_PARENT_PILOT_RUNNER_MISSING",),
        )


def test_historical_acceptance_is_archived_and_not_collected_as_current() -> None:
    assert not (
        ROOT / "tests/test_raw_v8_step2_maximum_protocol_v2_"
        "independent_verifier_acceptance_v49f.py"
    ).exists()
    for path in (REVIEWER.HISTORICAL_PRODUCER, REVIEWER.HISTORICAL_V_A_TEST):
        assert (ROOT / path).is_file()
        assert "Archive" in path.parts


def test_reviewer_source_is_static_and_does_not_import_reviewed_roles() -> None:
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


def test_parent_runner_is_still_absent() -> None:
    assert not (ROOT / REVIEWER.RUNNER).exists()

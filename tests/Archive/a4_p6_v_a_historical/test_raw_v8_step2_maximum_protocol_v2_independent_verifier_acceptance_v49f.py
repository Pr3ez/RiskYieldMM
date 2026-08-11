from __future__ import annotations

import ast
import copy
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
from types import ModuleType
from typing import Any

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
REVIEWER_PATH = (
    ROOT / "scripts/tests/"
    "review_raw_v8_step2_maximum_protocol_v2_independent_verifier_v49f.py"
)
REPORT_PATH = (
    ROOT / "scripts/tests/"
    "raw_v8_step2_maximum_protocol_v2_"
    "independent_verifier_acceptance_report_v49f.json"
)
EXPECTED_REPORT_ID = "1e20c2c1312abe6b3924c96e6979f046325a87d635f728007a157831381b1da1"


def _load_reviewer() -> ModuleType:
    spec = importlib.util.spec_from_file_location("v_a_reviewer", REVIEWER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


REVIEWER = _load_reviewer()


def _load(path: pathlib.Path) -> dict[str, Any]:
    return json.loads(path.read_bytes())


def test_static_review_reconstructs_authority_control_and_case_ledgers() -> None:
    report = REVIEWER.build_report(ROOT, execute_runtime=False)
    REVIEWER._validate_report_identity(report)
    assert report["review_decision"] == "STATIC_PREFLIGHT_ONLY_NOT_ACCEPTED"
    assert report["formal_stage1_state"] == "NO-GO"
    assert report["next_subgate"] == "A4-P6-V-A"
    assert report["authority_closure"]["input_file_count"] == 39
    assert report["authority_closure"]["total_pinned_input_octets"] == 29_004_595
    assert report["authority_closure"]["input_file_headroom"] == 25
    assert len(report["authority_closure"]["ordered_authority_records"]) == 39
    assert [
        (row["authority_mode"], row["case_position"])
        for row in report["ordered_case_acceptance_records"]
    ] == [
        ("PREDECESSOR_CONSTRUCTIVE_BOUNDARY_V1", 5),
        ("SUCCESSOR_CASE435_EXACT_DELTA_V1", 5),
        ("SUCCESSOR_CASE435_EXACT_DELTA_V1", 24),
        ("SUCCESSOR_CASE435_EXACT_DELTA_V1", 54),
        ("SUCCESSOR_CASE435_EXACT_DELTA_V1", 69),
        ("SUCCESSOR_CASE435_PACKED_CONTEXT_BOUNDARY_V1", 435),
        ("SUCCESSOR_CASE435_PACKED_CONTEXT_BOUNDARY_V1", 475),
    ]
    assert report["static_isolation"]["verifier"]["dynamic_code_loading"] is False
    assert report["runtime_evidence"] == {
        "verifier_replay": None,
        "a4_t_expected_red": None,
        "a4_p6_expected_red": None,
    }


def test_v_a_reviewer_executes_full_replay_and_matches_frozen_report(
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
    )
    assert completed.returncode == 0, completed.stderr.decode()
    assert completed.stdout == completed.stderr == b""
    assert output.read_bytes() == REPORT_PATH.read_bytes()
    report = _load(output)
    assert report["review_decision"] == "ACCEPTED"
    assert report["runtime_evidence"]["verifier_replay"] == {
        "passed": 128,
        "failed": 0,
        "skipped": 0,
        "test_artifact_count": 10,
    }
    assert report["runtime_evidence"]["a4_t_expected_red"]["failed"] == 1
    assert report["runtime_evidence"]["a4_p6_expected_red"]["failed"] == 6
    assert report["candidate_and_context_immutability"] == (
        "VERIFIED_BY_PINNED_DOUBLE_RUN_AND_HOSTILE_REPLAY"
    )
    assert report["next_subgate"] == "A4-P6-P"
    assert report["independent_verifier_acceptance_report_id"] == (EXPECTED_REPORT_ID)


@pytest.mark.parametrize("metric_index", range(18))
def test_f2_enforcement_accepts_minus_one_and_exact_but_rejects_plus_one(
    metric_index: int,
) -> None:
    manifest = _load(ROOT / REVIEWER.MANIFEST)
    ceiling = manifest["ordered_f2_limit_records"][metric_index]["f2_per_case"]
    for accepted in (max(0, ceiling - 1), ceiling):
        ledger = copy.deepcopy(list(REVIEWER.CASE_LEDGER))
        ledger[0]["resource_vector"][metric_index] = accepted
        REVIEWER._validate_case_ledger(manifest, ledger)
    ledger = copy.deepcopy(list(REVIEWER.CASE_LEDGER))
    ledger[0]["resource_vector"][metric_index] = ceiling + 1
    with pytest.raises(REVIEWER.ReviewFailure, match="F2_EXCEEDED"):
        REVIEWER._validate_case_ledger(manifest, ledger)


def test_control_snapshot_rejects_v4_advancement_drift(tmp_path: pathlib.Path) -> None:
    source = (ROOT / REVIEWER.CONTROL).read_text(encoding="utf-8")
    old = '"next_subgate": "A4-P6-V-A"'
    assert source.count(old) == 1
    source = source.replace(old, '"next_subgate": "A4-P6-P"', 1)
    target = tmp_path / REVIEWER.CONTROL
    target.parent.mkdir(parents=True)
    target.write_text(source, encoding="utf-8")
    with pytest.raises(REVIEWER.ReviewFailure, match="CONTROL_INVALID"):
        REVIEWER._control_snapshot(tmp_path)


def test_fixed_descriptor_rejects_byte_identity_drift() -> None:
    descriptor = {
        "repository_relative_path": "artifact",
        "raw_octets": 1,
        "raw_sha256": "0" * 64,
    }
    with pytest.raises(REVIEWER.ReviewFailure, match="ARTIFACT_DRIFT"):
        REVIEWER._validate_descriptor(descriptor, 1, "1" * 64)


@pytest.mark.parametrize(
    "raw",
    [
        b'{"a":1,"a":2}',
        b'{"a":1.0}',
        b'{"a":NaN}',
        b'\xef\xbb\xbf{"a":1}',
        b"\xff",
    ],
    ids=["duplicate", "float", "non-finite", "bom", "invalid-utf8"],
)
def test_strict_json_rejects_noncanonical_or_ambiguous_input(raw: bytes) -> None:
    with pytest.raises(REVIEWER.ReviewFailure, match="JSON_INVALID"):
        REVIEWER._strict_loads(raw)


@pytest.mark.parametrize(
    "injection",
    [
        "\nimport subprocess\n",
        "\nPRODUCER = 'produce_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py'\n",
        "\nexec('pass')\n",
    ],
    ids=["subprocess", "producer", "dynamic-exec"],
)
def test_source_isolation_rejects_new_dependency_or_dynamic_code(
    injection: str,
) -> None:
    source = (ROOT / REVIEWER.VERIFIER).read_text(encoding="utf-8") + injection
    with pytest.raises(REVIEWER.ReviewFailure, match="SOURCE_ISOLATION_INVALID"):
        REVIEWER._validate_verifier_source(source)


def test_green_replay_parser_rejects_a_changed_pass_count() -> None:
    completed = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout=b"127 passed in 1.00s\n",
        stderr=b"",
    )
    with pytest.raises(REVIEWER.ReviewFailure, match="REPLAY_FAILED"):
        REVIEWER._parse_green_replay(completed)


def test_expected_red_parser_rejects_an_unexpected_failure_code() -> None:
    output = (
        b"A4_T_PARENT_PILOT_RUNNER_MISSING\n"
        b"A4_T_UNEXPECTED_FAILURE\n"
        b"1 failed, 61 passed, 2 skipped in 1.00s\n"
    )
    completed = subprocess.CompletedProcess(
        args=[],
        returncode=1,
        stdout=output,
        stderr=b"",
    )
    with pytest.raises(REVIEWER.ReviewFailure, match="EXPECTED_RED_DRIFT"):
        REVIEWER._parse_expected_red(
            completed,
            expected_passed=61,
            expected_skipped=2,
            expected_failures=REVIEWER.EXPECTED_A4_T_FAILURES,
        )


def test_report_identity_rejects_resealed_field_drift() -> None:
    report = REVIEWER.build_report(ROOT, execute_runtime=False)
    report["next_subgate"] = "A4-P6-P"
    with pytest.raises(REVIEWER.ReviewFailure, match="REPORT_IDENTITY_INVALID"):
        REVIEWER._validate_report_identity(report)


@pytest.mark.parametrize("alias_kind", ["symlink", "hardlink"])
def test_secure_reader_rejects_filesystem_aliases(
    tmp_path: pathlib.Path, alias_kind: str
) -> None:
    original = tmp_path / "original"
    original.write_bytes(b"value")
    alias = tmp_path / "alias"
    if alias_kind == "symlink":
        alias.symlink_to(original)
    else:
        os.link(original, alias)
    with pytest.raises(REVIEWER.ReviewFailure, match="FILE_INVALID"):
        REVIEWER._read_regular(tmp_path, pathlib.Path("alias"))


def test_reviewer_source_is_static_and_never_imports_reviewed_roles() -> None:
    source = REVIEWER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    from_imports = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }
    assert imported == {
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
    }
    assert from_imports == {"__future__", "typing"}
    assert calls.isdisjoint({"__import__", "compile", "eval", "exec"})


def test_runner_remains_absent_and_case5_producer_remains_exactly_pinned() -> None:
    assert not (ROOT / REVIEWER.RUNNER).exists()
    raw = (ROOT / REVIEWER.PRODUCER).read_bytes()
    expected_octets, expected_sha = REVIEWER.PINNED_FIXED_ARTIFACTS[REVIEWER.PRODUCER]
    assert len(raw) == expected_octets
    assert REVIEWER._sha256(raw) == expected_sha
    assert b"ONLY_CANONICAL_CASE_5_IS_SUPPORTED" in raw

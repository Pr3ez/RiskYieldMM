from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
REVIEWER_PATH = (
    ROOT
    / "scripts/tests/review_raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_upper_channel_v49f.py"
)
UPPER_SOURCE_PATH = (
    ROOT
    / "scripts/tests/solve_raw_v8_step2_maximum_protocol_v2_intrinsic_upper_v49f.py"
)
RESULT_PATH = (
    ROOT
    / "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_upper_channel_result_v49f.json"
)
REPORT_PATH = (
    ROOT
    / "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_upper_channel_acceptance_report_v49f.json"
)
ALLOWED_EXECUTION_INPUTS = (
    "scripts/tests/solve_raw_v8_step2_maximum_protocol_v2_intrinsic_upper_v49f.py",
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_intrinsic_correction_contract_v49f.json",
    "scripts/tests/raw_v8_step2_external_schema_v2_structural_registry_v49f.json",
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_intrinsic_upper_result_schema_v49f.json",
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_intrinsic_dual_source_freeze_v49f.json",
)


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


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
    return hashlib.sha256(
        _canonical_bytes({"domain": domain, "payload": payload})
    ).hexdigest()


def _resign_case(row: dict[str, Any], reviewer) -> None:
    payload = {key: value for key, value in row.items() if key != "upper_case_record_id"}
    row["upper_case_record_id"] = _semantic_id(reviewer.CASE_DOMAIN, payload)


def _resign_root(result: dict[str, Any], reviewer) -> None:
    rows = result["ordered_case_upper_records"]
    result["ordered_case_upper_records_sha256"] = hashlib.sha256(
        _canonical_bytes(rows)
    ).hexdigest()
    payload = {
        key: value for key, value in result.items() if key != "upper_channel_result_id"
    }
    result["upper_channel_result_id"] = _semantic_id(reviewer.RESULT_DOMAIN, payload)


@pytest.fixture(scope="module")
def reviewer():
    return _load_module(REVIEWER_PATH, "intrinsic_c2u_independent_reviewer")


@pytest.fixture(scope="module")
def result_raw() -> bytes:
    if not RESULT_PATH.is_file() or not REPORT_PATH.is_file():
        pytest.skip("C2-U official result/report are intentionally absent before execution")
    return RESULT_PATH.read_bytes()


@pytest.fixture(scope="module")
def result(result_raw: bytes) -> dict[str, Any]:
    return json.loads(result_raw)


@pytest.fixture(scope="module")
def report() -> dict[str, Any]:
    if not RESULT_PATH.is_file() or not REPORT_PATH.is_file():
        pytest.skip("C2-U official result/report are intentionally absent before execution")
    return json.loads(REPORT_PATH.read_bytes())


def test_c2u_official_artifacts_are_published_together() -> None:
    missing = [
        path.relative_to(ROOT).as_posix()
        for path in (RESULT_PATH, REPORT_PATH)
        if not path.is_file() or path.is_symlink()
    ]
    assert missing == []


def test_c2u_reviewer_is_a_separate_standard_library_program(reviewer) -> None:
    source = REVIEWER_PATH.read_text()
    tree = ast.parse(source)
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.add((node.module or "").split(".")[0])
    assert imports <= {
        "__future__",
        "argparse",
        "ast",
        "dataclasses",
        "hashlib",
        "json",
        "pathlib",
        "sys",
        "typing",
    }
    assert "import solve_raw_v8_step2_maximum_protocol_v2_intrinsic_upper" not in source
    assert "import construct_raw_v8_step2_maximum_protocol_v2_intrinsic" not in source
    assert "class CaseOracle" in source
    assert "def _reverse_dfa_upper" in source
    assert reviewer.PACKET == "A4-R475-V1-C2-U"


def test_c2u_upper_and_reviewer_have_distinct_algorithm_surfaces() -> None:
    upper_tree = ast.parse(UPPER_SOURCE_PATH.read_text())
    review_tree = ast.parse(REVIEWER_PATH.read_text())
    upper_functions = {
        node.name for node in ast.walk(upper_tree) if isinstance(node, ast.FunctionDef)
    }
    review_functions = {
        node.name for node in ast.walk(review_tree) if isinstance(node, ast.FunctionDef)
    }
    assert "_dfa_upper" in upper_functions
    assert "_dfa_upper" not in review_functions
    assert "_reverse_dfa_upper" in review_functions
    assert "_reverse_dfa_upper" not in upper_functions
    assert "_derive_case" in upper_functions
    assert "_derive_case" not in review_functions
    assert "evaluate" in review_functions
    assert "evaluate" not in upper_functions


def test_c2u_independent_review_reads_only_its_declared_surface(
    reviewer, result_raw: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed: set[Path] = set()
    original = Path.read_bytes

    def tracked(path: Path) -> bytes:
        observed.add(path.resolve())
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", tracked)
    reviewer.verify(ROOT, result_raw)
    assert observed == {
        (ROOT / reviewer.CONTRACT_PATH).resolve(),
        (ROOT / reviewer.REGISTRY_PATH).resolve(),
        (ROOT / reviewer.FREEZE_PATH).resolve(),
        (ROOT / reviewer.UPPER_SCHEMA_PATH).resolve(),
        (ROOT / reviewer.UPPER_SOURCE_PATH).resolve(),
    }


def test_c2u_reviewer_reconstructs_the_official_result_and_report(
    reviewer, result_raw: bytes, report: dict[str, Any]
) -> None:
    reconstructed = reviewer.verify(ROOT, result_raw)
    assert reconstructed == report
    payload = {
        key: value
        for key, value in report.items()
        if key != "upper_channel_acceptance_report_id"
    }
    assert report["upper_channel_acceptance_report_id"] == _semantic_id(
        reviewer.REPORT_DOMAIN, payload
    )


def test_c2u_result_is_closed_canonical_and_nonclaiming(
    reviewer, result_raw: bytes, result: dict[str, Any]
) -> None:
    assert result_raw == _pretty_bytes(result)
    assert set(result) == set(reviewer.EXPECTED_ROOT_MEMBERS)
    assert result["packet"] == "A4-R475-V1-C2-U"
    assert result["case_count"] == 66
    assert result["exactness_claimed"] is False
    assert result["attainer_channel_consumed"] is False
    assert result["formal_stage1_state"] == "NO-GO"
    assert result["next_bounded_packet"] == "A4-R475-V1-C2-A"
    assert len(result_raw) < 2_097_152


def test_c2u_all_66_case_records_and_complete_method_surface(
    reviewer, result: dict[str, Any], report: dict[str, Any]
) -> None:
    rows = result["ordered_case_upper_records"]
    assert [row["case_position"] for row in rows] == list(range(1, 67))
    assert all(set(row) == set(reviewer.EXPECTED_CASE_MEMBERS) for row in rows)
    assert all(row["proof_status"] == "PROVED_LEGAL_DOMAIN_SUPERSET" for row in rows)
    assert all(row["attainer_source_or_output_read"] is False for row in rows)
    assert sum(row["proof_step_count"] for row in rows) == 1_647
    assert report["derivation_kind_census"] == reviewer.EXPECTED_DERIVATION_CENSUS
    assert tuple(report["proof_method_case_census"]) == reviewer.PROOF_METHODS
    assert report["attainer_source_or_output_read_true_case_count"] == 0


def test_c2u_result_and_review_are_deterministic_cli_replays(
    reviewer, report: dict[str, Any]
) -> None:
    runs = [
        subprocess.run(
            [sys.executable, str(REVIEWER_PATH), str(ROOT)],
            cwd=ROOT,
            check=False,
            capture_output=True,
        )
        for _ in range(2)
    ]
    assert [run.returncode for run in runs] == [0, 0]
    assert [run.stderr for run in runs] == [b"", b""]
    assert runs[0].stdout == runs[1].stdout == _pretty_bytes(report)
    assert hashlib.sha256(RESULT_PATH.read_bytes()).hexdigest() == report[
        "upper_result_raw_sha256"
    ]


def test_c2u_frozen_source_reproduces_result_in_attainer_free_sandbox(
    result_raw: bytes, tmp_path: Path
) -> None:
    assert shutil.which("strace") is not None
    for relative_path in ALLOWED_EXECUTION_INPUTS:
        source = ROOT / relative_path
        target = tmp_path / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    trace = tmp_path / "upper.strace"
    copied_source = tmp_path / ALLOWED_EXECUTION_INPUTS[0]
    run = subprocess.run(
        [
            "strace",
            "-f",
            "-qq",
            "-e",
            "trace=%file",
            "-o",
            str(trace),
            sys.executable,
            str(copied_source),
            "--repository-root",
            str(tmp_path),
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stderr
    assert run.stdout == run.stderr == ""
    reproduced = tmp_path / RESULT_PATH.relative_to(ROOT)
    assert reproduced.read_bytes() == result_raw
    trace_text = trace.read_text()
    assert "intrinsic_attainer" not in trace_text
    assert "construct_raw_v8_step2_maximum_protocol_v2_intrinsic_attainers" not in trace_text
    for relative_path in ALLOWED_EXECUTION_INPUTS:
        assert str((tmp_path / relative_path).resolve()) in trace_text


@pytest.mark.parametrize(
    ("mutation", "value"),
    [
        ("case_upper", 524_287),
        ("case_transcript", "0" * 64),
        ("case_methods", ["RULE_AWARE_COMPOSITION"]),
        ("method_census", {"RULE_AWARE_COMPOSITION": 66}),
        ("exactness", True),
        ("attainer_consumed", True),
        ("next_packet", "A4-R475-V1-C3"),
        ("source_hash", "0" * 64),
        ("formal_state", "GO"),
        ("packet", "A4-R475-V1-C2-A"),
        ("schema_id", "0" * 64),
        ("reverse_rows", None),
        ("unknown_root", "forged"),
        ("unknown_case", "forged"),
    ],
)
def test_c2u_reviewer_rejects_coherently_resealed_semantic_mutations(
    reviewer,
    result: dict[str, Any],
    mutation: str,
    value: Any,
) -> None:
    forged = copy.deepcopy(result)
    first = forged["ordered_case_upper_records"][0]
    if mutation == "case_upper":
        first["legal_domain_upper_octets"] = value
        _resign_case(first, reviewer)
    elif mutation == "case_transcript":
        first["proof_step_transcript_sha256"] = value
        _resign_case(first, reviewer)
    elif mutation == "case_methods":
        first["ordered_proof_methods"] = value
        _resign_case(first, reviewer)
    elif mutation == "method_census":
        forged["proof_method_case_census"] = value
    elif mutation == "exactness":
        forged["exactness_claimed"] = value
    elif mutation == "attainer_consumed":
        forged["attainer_channel_consumed"] = value
    elif mutation == "next_packet":
        forged["next_bounded_packet"] = value
    elif mutation == "source_hash":
        forged["source_sha256"] = value
    elif mutation == "formal_state":
        forged["formal_stage1_state"] = value
    elif mutation == "packet":
        forged["packet"] = value
    elif mutation == "schema_id":
        forged["output_schema_id"] = value
    elif mutation == "reverse_rows":
        forged["ordered_case_upper_records"].reverse()
    elif mutation == "unknown_root":
        forged["unknown_root_member"] = value
    elif mutation == "unknown_case":
        first["unknown_case_member"] = value
        _resign_case(first, reviewer)
    else:  # pragma: no cover - the parameter table is closed
        raise AssertionError(mutation)
    _resign_root(forged, reviewer)
    with pytest.raises(reviewer.ReviewFailure):
        reviewer.verify(ROOT, _pretty_bytes(forged))


def test_c2u_reviewer_rejects_noncanonical_and_duplicate_json(
    reviewer, result: dict[str, Any], result_raw: bytes
) -> None:
    compact = _canonical_bytes(result)
    assert compact != result_raw
    with pytest.raises(reviewer.ReviewFailure, match="encoding differs"):
        reviewer.verify(ROOT, compact)
    duplicate = result_raw.replace(
        b'{\n  "attainer_channel_consumed": false,',
        b'{\n  "attainer_channel_consumed": false,\n  "attainer_channel_consumed": false,',
        1,
    )
    assert duplicate != result_raw
    with pytest.raises(reviewer.ReviewFailure, match="duplicate JSON member"):
        reviewer.verify(ROOT, duplicate)


def test_c2u_resource_accounting_remains_inside_frozen_f0(report: dict[str, Any]) -> None:
    assert report["execution_pinned_input_file_count"] == 5
    assert report["execution_pinned_input_octets"] < 67_108_864
    assert report["official_output_file_count"] == 1
    assert report["upper_result_raw_octets"] < 2_097_152

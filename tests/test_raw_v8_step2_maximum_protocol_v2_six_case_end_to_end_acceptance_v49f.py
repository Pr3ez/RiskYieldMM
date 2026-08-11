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
    "six_case_end_to_end_v49f.py"
)
REPORT_PATH = (
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "six_case_end_to_end_acceptance_report_v49f.json"
)

# Frozen after the fail-first transition and independent acceptance review.
EXPECTED_REVIEWER = (
    34_288,
    "a0a456b9689cabf369d0c7d57a2cfbaa7ecb9689518408541f24476e945ccc1c",
)
EXPECTED_REPORT = (
    16_064,
    "8aab9f9be12edb028eae154f05c032b0d125865f37cad04e32862857a78b2d7e",
)
EXPECTED_REPORT_ID = "c94c784f29a57fd8fc345cd49b90b7225e2a5697ff2077c8dd0b4b2115809d11"


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _load(path: pathlib.Path) -> dict[str, object]:
    return json.loads(path.read_bytes())


def _require_artifacts() -> None:
    if not REVIEWER_PATH.is_file() or not REPORT_PATH.is_file():
        pytest.skip("A4-P6-E reviewer/report are not implemented")


def _load_reviewer() -> ModuleType:
    _require_artifacts()
    specification = importlib.util.spec_from_file_location(
        "a4_p6_e_reviewer", REVIEWER_PATH
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def test_end_to_end_reviewer_and_report_exist() -> None:
    assert REVIEWER_PATH.is_file(), "A4-P6-E independent reviewer is missing"
    assert REPORT_PATH.is_file(), "A4-P6-E deterministic report is missing"


def test_acceptance_artifact_identity_and_release_transition_are_exact() -> None:
    reviewer = _load_reviewer()
    for path, (octets, digest) in (
        (REVIEWER_PATH, EXPECTED_REVIEWER),
        (REPORT_PATH, EXPECTED_REPORT),
    ):
        raw = path.read_bytes()
        assert len(raw) == octets
        assert _sha256(raw) == digest
    report = _load(REPORT_PATH)
    reviewer._validate_release_report(report, require_runtime=True)
    assert report["six_case_end_to_end_acceptance_report_id"] == EXPECTED_REPORT_ID
    assert report["correction_subgate"] == "A4-P6-E"
    assert report["review_decision"] == "ACCEPTED"
    assert report["release_decision"] == "RELEASED_FOR_A4_R475_VERSIONED_IMPLEMENTATION"
    assert report["formal_stage1_state"] == "NO-GO"
    assert report["next_subgate"] == "A4-R475"


def test_static_preflight_cannot_release_a4_r475() -> None:
    reviewer = _load_reviewer()
    report = reviewer.build_report(ROOT, execute_runtime=False)
    reviewer._validate_release_report(report, require_runtime=False)
    assert report["review_decision"] == "STATIC_PREFLIGHT_ONLY_NOT_ACCEPTED"
    assert report["release_decision"] == "UNDER_REVIEW"
    assert report["next_subgate"] == "A4-P6-E"
    assert report["independent_replay_evidence"] is None


def test_full_independent_reviewer_replay_matches_frozen_report(
    tmp_path: pathlib.Path,
) -> None:
    _require_artifacts()
    output = tmp_path / "a4-p6-e-report.json"
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


def test_release_criteria_and_campaign_surface_are_explicit() -> None:
    _require_artifacts()
    report = _load(REPORT_PATH)
    replay = report["independent_replay_evidence"]
    assert replay == {
        "a4_p6_r_reviewer_replays": 2,
        "effective_parent_transactions_replayed": 4,
        "effective_producer_child_runs_replayed": 24,
        "effective_verifier_child_runs_replayed": 24,
        "frozen_report_match": "BOTH_BYTE_IDENTICAL",
        "reviewer_output_determinism": "VERIFIED",
    }
    assert [
        row["criterion_position"] for row in report["ordered_release_criteria"]
    ] == list(range(1, 9))
    assert all(
        row["criterion_state"] == "PASS" for row in report["ordered_release_criteria"]
    )
    assert report["campaign_surface"] == {
        "case_universe_count": 475,
        "current_pilot_case_count": 6,
        "current_pilot_case_positions": [5, 24, 54, 69, 435, 475],
        "current_role_surface": "SIX_CASE_ONLY",
        "maximum_publication_case_count": 474,
        "non_pilot_case_count": 469,
        "local_minimality_case_count": 1,
        "release_scope": "VERSIONED_ALL_475_IMPLEMENTATION_THEN_EXECUTION",
        "unchanged_current_binaries_all_case_ready": False,
        "pilot_f2_implies_full_campaign_fit": False,
    }


def test_recomputed_case_and_full_run_f2_ledgers_are_exact() -> None:
    _require_artifacts()
    report = _load(REPORT_PATH)
    assert [row["case_position"] for row in report["ordered_case_release_records"]] == [
        5,
        24,
        54,
        69,
        435,
        475,
    ]
    f2 = report["ordered_full_run_f2_reconciliation_records"]
    assert [row["metric_position"] for row in f2] == list(range(1, 19))
    assert [row["measured_full_run_value"] for row in f2] == [
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
    assert all(row["measured_full_run_value"] <= row["f2_full_run"] for row in f2)
    assert [row["full_run_aggregation"] for row in f2[-4:]] == [
        "MAXIMUM",
        "MAXIMUM",
        "MAXIMUM",
        "SUM",
    ]


def test_resealed_gate_surface_case_replay_or_f2_drift_is_rejected() -> None:
    reviewer = _load_reviewer()
    original = _load(REPORT_PATH)
    mutations = (
        ("gate", lambda value: value.__setitem__("next_subgate", "A4-E")),
        (
            "surface",
            lambda value: value["campaign_surface"].__setitem__(
                "unchanged_current_binaries_all_case_ready", True
            ),
        ),
        (
            "case",
            lambda value: value["ordered_case_release_records"][0].__setitem__(
                "case_position", 4
            ),
        ),
        (
            "replay",
            lambda value: value["independent_replay_evidence"].__setitem__(
                "a4_p6_r_reviewer_replays", 1
            ),
        ),
        (
            "f2",
            lambda value: value["ordered_full_run_f2_reconciliation_records"][
                0
            ].__setitem__("measured_full_run_value", 5),
        ),
    )
    for _label, mutate in mutations:
        hostile = copy.deepcopy(original)
        mutate(hostile)
        reviewer._seal_report(hostile)
        with pytest.raises(reviewer.ReviewFailure, match="RELEASE_REPORT_INVALID"):
            reviewer._validate_release_report(hostile, require_runtime=True)


def test_reviewer_source_is_independent_of_reviewed_roles_and_tests() -> None:
    reviewer = _load_reviewer()
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
        "subprocess",
        "sys",
        "tempfile",
        "typing",
    }
    assert "importlib" not in imports
    assert reviewer.SOURCE_MARKER in source
    assert "spec_from_file_location" not in source
    for forbidden in (
        "produce_raw_v8_step2_maximum_protocol_v2_candidate_v49f",
        "verify_raw_v8_step2_maximum_protocol_v2_candidate_v49f",
        "run_raw_v8_step2_maximum_protocol_v2_pilot_v49f",
    ):
        assert f"import {forbidden}" not in source

from __future__ import annotations

import copy
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONTROL_CHECKER_PATH = ROOT / "scripts/tests/check_stage1_execution_control.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location(
        "stage1_execution_control_checker", CONTROL_CHECKER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_stage1_execution_control_matches_recorded_checkpoint() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/tests/check_stage1_execution_control.py"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "STAGE1_CONTROL_OK active_gate=S1-A4" in completed.stdout
    assert "formal_state=NO-GO" in completed.stdout
    assert "catalog_stale=false" in completed.stdout
    assert "s1_a2_comparison_id=8fca05661cbf" in completed.stdout
    assert "s1_a3_manifest_id=edde204e98ed" in completed.stdout
    assert "s1_a4_boundary_id=bdc7363ae28d" in completed.stdout
    assert "s1_a4_fail_first_sha256=10058dabf6b8" in completed.stdout
    assert "s1_a4_verifier_sha256=f85a47ebf5b8" in completed.stdout
    assert "s1_a4_producer_sha256=9a0f20784199" in completed.stdout
    assert "s1_a4_six_case_target_sha256=12c1ff23ca6a" in completed.stdout
    assert "s1_a4_case435_analysis_id=b126fb9bef84" in completed.stdout
    assert "s1_a4_case435_gap_octets=1234" in completed.stdout
    assert "s1_a4_profile_scope_audit_id=10e0ce8a2770" in completed.stdout
    assert "s1_a4_profile_scope_affected=407/474" in completed.stdout
    assert "s1_a4_case435_dependency_audit_id=56923275cd44" in completed.stdout
    assert "s1_a4_case435_components=182+3" in completed.stdout
    assert "s1_a4_case435_upper_certificate_id=c01bba7c5f5f" in completed.stdout
    assert "s1_a4_case435_upper_octets=257887" in completed.stdout
    assert "s1_a4_case435_attainer_certificate_id=1d801ba5b81a" in completed.stdout
    assert "s1_a4_case435_attainer_octets=257887" in completed.stdout
    assert "s1_a4_case435_exactness_join_id=2abf00603826" in completed.stdout
    assert "s1_a4_case435_exact_maximum_octets=257887" in completed.stdout
    assert "s1_a4_case435_successor_seed_id=7fad47e88162" in completed.stdout
    assert "s1_a4_case435_successor_target_id=a000285d1bed" in completed.stdout
    assert (
        "s1_a4_case435_verifier_expansion="
        "RELEASED_FOR_A4_P6_V_IMPLEMENTATION"
    ) in completed.stdout
    assert "s1_a4_verifier_packet=A4-P6-V0" in completed.stdout
    assert "s1_a4_verifier_next=A4-P6-V1" in completed.stdout


def test_stage1_execution_control_rejects_s1_a2_source_identity_drift() -> None:
    checker = _load_checker()
    snapshot = copy.deepcopy(checker._load_control()["s1_a2_snapshot"])
    snapshot["ordered_authority_records"][1]["raw_sha256"] = "0" * 64
    with pytest.raises(checker.ControlFailure, match="authority 2 hash drifted"):
        checker._validate_s1_a2_snapshot(snapshot)


def test_stage1_execution_control_rejects_s1_a3_limit_identity_drift() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a3_snapshot"])
    snapshot["finalization_manifest_raw_sha256"] = "0" * 64
    with pytest.raises(checker.ControlFailure, match="manifest hash drifted"):
        checker._validate_s1_a3_snapshot(snapshot, control["s1_a2_snapshot"])


def test_stage1_execution_control_rejects_s1_a4_boundary_identity_drift() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_boundary_snapshot"])
    snapshot["boundary_raw_sha256"] = "0" * 64
    with pytest.raises(
        checker.ControlFailure, match="constructive boundary hash drifted"
    ):
        checker._validate_s1_a4_boundary_snapshot(
            snapshot,
            control["s1_a3_snapshot"],
        )


def test_stage1_execution_control_rejects_s1_a4_fail_first_identity_drift() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_fail_first_snapshot"])
    snapshot["fail_first_test_raw_sha256"] = "0" * 64
    with pytest.raises(checker.ControlFailure, match="fail-first test hash drifted"):
        checker._validate_s1_a4_fail_first_snapshot(
            snapshot,
            control["s1_a4_boundary_snapshot"],
        )


def test_stage1_execution_control_rejects_s1_a4_verifier_identity_drift() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_verifier_snapshot"])
    snapshot["verifier_raw_sha256"] = "0" * 64
    with pytest.raises(checker.ControlFailure, match="verifier hash drifted"):
        checker._validate_s1_a4_verifier_snapshot(
            snapshot,
            control["s1_a4_boundary_snapshot"],
        )


def test_stage1_execution_control_rejects_s1_a4_producer_identity_drift() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_producer_snapshot"])
    snapshot["producer_raw_sha256"] = "0" * 64
    with pytest.raises(checker.ControlFailure, match="producer hash drifted"):
        checker._validate_s1_a4_producer_snapshot(
            snapshot,
            control["s1_a4_boundary_snapshot"],
        )


def test_stage1_execution_control_rejects_s1_a4_six_case_target_identity_drift() -> (
    None
):
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_six_case_target_snapshot"])
    snapshot["fail_first_test_raw_sha256"] = "0" * 64
    with pytest.raises(checker.ControlFailure, match="six-case target hash drifted"):
        checker._validate_s1_a4_six_case_target_snapshot(
            snapshot,
            control["s1_a4_boundary_snapshot"],
            control["s1_a4_producer_snapshot"],
        )


def test_stage1_execution_control_rejects_case435_analyzer_identity_drift() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(
        control["s1_a4_case435_attainability_falsification_snapshot"]
    )
    snapshot["analyzer_raw_sha256"] = "0" * 64
    with pytest.raises(
        checker.ControlFailure, match="attainability analyzer hash drifted"
    ):
        checker._validate_s1_a4_case435_attainability_falsification_snapshot(
            snapshot,
            control["s1_a4_six_case_target_snapshot"],
            control["seed_snapshot"],
        )


def test_stage1_execution_control_rejects_case435_falsification_gap_drift() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(
        control["s1_a4_case435_attainability_falsification_snapshot"]
    )
    snapshot["p3_unattainable_gap_octets"] += 1
    with pytest.raises(checker.ControlFailure, match="attainability report drifted"):
        checker._validate_s1_a4_case435_attainability_falsification_snapshot(
            snapshot,
            control["s1_a4_six_case_target_snapshot"],
            control["seed_snapshot"],
        )


def test_stage1_execution_control_rejects_case435_verifier_resume() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(
        control["s1_a4_case435_attainability_falsification_snapshot"]
    )
    snapshot["verifier_expansion_state"] = "NEXT"
    with pytest.raises(checker.ControlFailure, match="correction disposition differs"):
        checker._validate_s1_a4_case435_attainability_falsification_snapshot(
            snapshot,
            control["s1_a4_six_case_target_snapshot"],
            control["seed_snapshot"],
        )


def test_stage1_execution_control_rejects_profile_scope_analyzer_drift() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_profile_attainability_scope_snapshot"])
    snapshot["analyzer_raw_sha256"] = "0" * 64
    with pytest.raises(
        checker.ControlFailure,
        match="profile-attainability analyzer hash drifted",
    ):
        checker._validate_s1_a4_profile_attainability_scope_snapshot(
            snapshot,
            control["s1_a4_case435_attainability_falsification_snapshot"],
            control["seed_snapshot"],
        )


def test_stage1_execution_control_rejects_profile_scope_census_drift() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_profile_attainability_scope_snapshot"])
    snapshot["structural_superset_scope_case_count"] -= 1
    with pytest.raises(
        checker.ControlFailure,
        match="profile-attainability scope report drifted",
    ):
        checker._validate_s1_a4_profile_attainability_scope_snapshot(
            snapshot,
            control["s1_a4_case435_attainability_falsification_snapshot"],
            control["seed_snapshot"],
        )


def test_stage1_execution_control_rejects_profile_scope_verifier_resume() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_profile_attainability_scope_snapshot"])
    snapshot["verifier_expansion_state"] = "NEXT"
    with pytest.raises(
        checker.ControlFailure,
        match="profile-attainability disposition differs",
    ):
        checker._validate_s1_a4_profile_attainability_scope_snapshot(
            snapshot,
            control["s1_a4_case435_attainability_falsification_snapshot"],
            control["seed_snapshot"],
        )


def test_stage1_execution_control_rejects_dependency_analyzer_drift() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_case435_dependency_closure_snapshot"])
    snapshot["analyzer_raw_sha256"] = "0" * 64
    with pytest.raises(
        checker.ControlFailure,
        match="dependency-closure analyzer hash drifted",
    ):
        checker._validate_s1_a4_case435_dependency_closure_snapshot(
            snapshot,
            control["s1_a4_profile_attainability_scope_snapshot"],
            control["s1_a4_case435_attainability_falsification_snapshot"],
        )


def test_stage1_execution_control_rejects_dependency_graph_drift() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_case435_dependency_closure_snapshot"])
    snapshot["conditional_component_count"] -= 1
    with pytest.raises(
        checker.ControlFailure,
        match="dependency-closure report drifted",
    ):
        checker._validate_s1_a4_case435_dependency_closure_snapshot(
            snapshot,
            control["s1_a4_profile_attainability_scope_snapshot"],
            control["s1_a4_case435_attainability_falsification_snapshot"],
        )


def test_stage1_execution_control_rejects_dependency_premature_maximum() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_case435_dependency_closure_snapshot"])
    snapshot["exact_case435_maximum_derived"] = True
    with pytest.raises(
        checker.ControlFailure,
        match="dependency-closure report drifted",
    ):
        checker._validate_s1_a4_case435_dependency_closure_snapshot(
            snapshot,
            control["s1_a4_profile_attainability_scope_snapshot"],
            control["s1_a4_case435_attainability_falsification_snapshot"],
        )


def test_stage1_execution_control_rejects_case435_upper_solver_drift() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_case435_upper_snapshot"])
    snapshot["solver_raw_sha256"] = "0" * 64
    with pytest.raises(checker.ControlFailure, match="exact-upper solver hash drifted"):
        checker._validate_s1_a4_case435_upper_snapshot(
            snapshot,
            control["s1_a4_case435_dependency_closure_snapshot"],
        )


def test_stage1_execution_control_rejects_case435_upper_result_drift() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_case435_upper_snapshot"])
    snapshot["exact_upper_bound_octets"] += 1
    with pytest.raises(checker.ControlFailure, match="exact-upper result drifted"):
        checker._validate_s1_a4_case435_upper_snapshot(
            snapshot,
            control["s1_a4_case435_dependency_closure_snapshot"],
        )


def test_stage1_execution_control_rejects_case435_premature_attainer_claim() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_case435_upper_snapshot"])
    snapshot["independent_attainer_accepted"] = True
    with pytest.raises(checker.ControlFailure, match="exact-upper result drifted"):
        checker._validate_s1_a4_case435_upper_snapshot(
            snapshot,
            control["s1_a4_case435_dependency_closure_snapshot"],
        )


def test_stage1_execution_control_rejects_case435_attainer_constructor_drift() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_case435_attainer_snapshot"])
    snapshot["constructor_raw_sha256"] = "0" * 64
    with pytest.raises(
        checker.ControlFailure, match="attainer constructor hash drifted"
    ):
        checker._validate_s1_a4_case435_attainer_snapshot(
            snapshot,
            control["s1_a4_case435_dependency_closure_snapshot"],
        )


def test_stage1_execution_control_rejects_case435_attainer_result_drift() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_case435_attainer_snapshot"])
    snapshot["measured_attainer_canonical_octets"] += 1
    with pytest.raises(checker.ControlFailure, match="attainer result drifted"):
        checker._validate_s1_a4_case435_attainer_snapshot(
            snapshot,
            control["s1_a4_case435_dependency_closure_snapshot"],
        )


def test_stage1_execution_control_rejects_case435_attainer_exactness_claim() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_case435_attainer_snapshot"])
    snapshot["exactness_claimed"] = True
    with pytest.raises(checker.ControlFailure, match="attainer result drifted"):
        checker._validate_s1_a4_case435_attainer_snapshot(
            snapshot,
            control["s1_a4_case435_dependency_closure_snapshot"],
        )


def test_stage1_execution_control_rejects_case435_exactness_join_source_drift() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_case435_exactness_join_snapshot"])
    snapshot["join_raw_sha256"] = "0" * 64
    with pytest.raises(checker.ControlFailure, match="exactness join hash drifted"):
        checker._validate_s1_a4_case435_exactness_join_snapshot(
            snapshot,
            control["s1_a4_case435_dependency_closure_snapshot"],
            control["s1_a4_case435_upper_snapshot"],
            control["s1_a4_case435_attainer_snapshot"],
            {},
            {},
        )


def test_stage1_execution_control_rejects_case435_exact_maximum_drift() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_case435_exactness_join_snapshot"])
    snapshot["exact_maximum_octets"] += 1
    with pytest.raises(checker.ControlFailure, match="exactness-join result drifted"):
        checker._validate_s1_a4_case435_exactness_join_snapshot(
            snapshot,
            control["s1_a4_case435_dependency_closure_snapshot"],
            control["s1_a4_case435_upper_snapshot"],
            control["s1_a4_case435_attainer_snapshot"],
            {},
            {},
        )


def test_stage1_execution_control_rejects_case435_premature_verifier_resume() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_case435_exactness_join_snapshot"])
    snapshot["verifier_expansion_state"] = "NEXT"
    with pytest.raises(checker.ControlFailure, match="exactness-join result drifted"):
        checker._validate_s1_a4_case435_exactness_join_snapshot(
            snapshot,
            control["s1_a4_case435_dependency_closure_snapshot"],
            control["s1_a4_case435_upper_snapshot"],
            control["s1_a4_case435_attainer_snapshot"],
            {},
            {},
        )


def test_stage1_execution_control_rejects_case435_transition_source_drift() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(
        control["s1_a4_case435_authority_transition_snapshot"]
    )
    snapshot["seed_delta_raw_sha256"] = "0" * 64
    with pytest.raises(checker.ControlFailure, match="seed delta hash drifted"):
        checker._validate_s1_a4_case435_authority_transition_snapshot(
            snapshot,
            control["s1_a4_case435_exactness_join_snapshot"],
            control["seed_snapshot"],
            control["s1_a3_snapshot"],
            control["s1_a4_boundary_snapshot"],
        )


def test_stage1_execution_control_rejects_case435_transition_f2_weakening() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(
        control["s1_a4_case435_authority_transition_snapshot"]
    )
    snapshot["f2_resource_requalification_state"] = "NOT_REQUIRED"
    with pytest.raises(checker.ControlFailure, match="transition result drifted"):
        checker._validate_s1_a4_case435_authority_transition_snapshot(
            snapshot,
            control["s1_a4_case435_exactness_join_snapshot"],
            control["seed_snapshot"],
            control["s1_a3_snapshot"],
            control["s1_a4_boundary_snapshot"],
        )


def test_stage1_execution_control_rejects_case435_premature_producer_release() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(
        control["s1_a4_case435_authority_transition_snapshot"]
    )
    snapshot["producer_expansion_state"] = "RELEASED"
    with pytest.raises(checker.ControlFailure, match="transition result drifted"):
        checker._validate_s1_a4_case435_authority_transition_snapshot(
            snapshot,
            control["s1_a4_case435_exactness_join_snapshot"],
            control["seed_snapshot"],
            control["s1_a3_snapshot"],
            control["s1_a4_boundary_snapshot"],
        )


def test_stage1_execution_control_rejects_verifier_v0_source_drift() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_verifier_expansion_v0_snapshot"])
    snapshot["verifier_raw_sha256"] = "0" * 64
    with pytest.raises(checker.ControlFailure, match="V0 verifier hash drifted"):
        checker._validate_s1_a4_verifier_expansion_v0_snapshot(
            snapshot,
            control["s1_a4_verifier_snapshot"],
            control["s1_a4_boundary_snapshot"],
            control["s1_a4_case435_authority_transition_snapshot"],
        )


def test_stage1_execution_control_rejects_verifier_v0_footprint_weakening() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_verifier_expansion_v0_snapshot"])
    snapshot["successor_authority_file_count"] -= 1
    with pytest.raises(
        checker.ControlFailure, match="successor authority footprint differs"
    ):
        checker._validate_s1_a4_verifier_expansion_v0_snapshot(
            snapshot,
            control["s1_a4_verifier_snapshot"],
            control["s1_a4_boundary_snapshot"],
            control["s1_a4_case435_authority_transition_snapshot"],
        )


def test_stage1_execution_control_rejects_verifier_v0_premature_case435_f2_claim() -> (
    None
):
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_verifier_expansion_v0_snapshot"])
    snapshot["case435_resource_requalification_state"] = "ACCEPTED"
    with pytest.raises(checker.ControlFailure, match="V0 state differs"):
        checker._validate_s1_a4_verifier_expansion_v0_snapshot(
            snapshot,
            control["s1_a4_verifier_snapshot"],
            control["s1_a4_boundary_snapshot"],
            control["s1_a4_case435_authority_transition_snapshot"],
        )

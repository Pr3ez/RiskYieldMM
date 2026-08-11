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
    assert "s1_a4_verifier_sha256=b1bfb5778b14" in completed.stdout
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
        "s1_a4_case435_verifier_expansion=RELEASED_FOR_A4_P6_V_IMPLEMENTATION"
    ) in completed.stdout
    assert "s1_a4_case435_context_pack_id=c8448f57dcdc" in completed.stdout
    assert "s1_a4_case435_packed_file_headroom=23" in completed.stdout
    assert "s1_a4_verifier_packet=A4-P6-V-A" in completed.stdout
    assert "s1_a4_verifier_report_id=1e20c2c1312a" in completed.stdout
    assert "s1_a4_verifier_next=A4-P6-P" in completed.stdout
    assert "s1_a4_producer_packet=A4-P6-P" in completed.stdout
    assert "s1_a4_producer_report_id=defe27a1fafa" in completed.stdout
    assert "s1_a4_producer_next=A4-P6-R" in completed.stdout
    assert "s1_a4_runner_packet=A4-P6-R" in completed.stdout
    assert "s1_a4_runner_report_id=ee39ba2ee328" in completed.stdout
    assert "s1_a4_runner_next=A4-P6-E" in completed.stdout
    assert "s1_a4_pilot_acceptance_packet=A4-P6-E" in completed.stdout
    assert "s1_a4_pilot_acceptance_report_id=c94c784f29a5" in completed.stdout
    assert "s1_a4_pilot_acceptance_next=A4-R475" in completed.stdout
    assert "s1_a4_all_case_contract_id=9be94bf6b53b" in completed.stdout
    assert "s1_a4_all_case_contract_report_id=16035e8342cb" in completed.stdout
    assert "s1_a4_all_case_contract_packet=A4-R475-T" in completed.stdout
    assert "s1_a4_all_case_verifier_packet=A4-R475-V0" in completed.stdout
    assert "s1_a4_all_case_verifier_report_id=127784d23829" in completed.stdout
    assert "s1_a4_all_case_verifier_next=A4-R475-V1" in completed.stdout
    assert (
        "s1_a4_intrinsic_attainability_packet=A4-R475-V1-F-A"
        in completed.stdout
    )
    assert "s1_a4_intrinsic_attainability_id=0b53bd2d79c5" in completed.stdout
    assert "s1_a4_intrinsic_contradictions=26/66" in completed.stdout
    assert "s1_a4_intrinsic_case8=928/524288" in completed.stdout
    assert "s1_a4_intrinsic_attainability_next=A4-R475-V1-C" in completed.stdout
    assert "s1_a4_intrinsic_correction_packet=A4-R475-V1-C1" in completed.stdout
    assert "s1_a4_intrinsic_correction_contract_id=171e9d47a773" in completed.stdout
    assert "s1_a4_intrinsic_correction_census=1647/1806" in completed.stdout
    assert "s1_a4_intrinsic_correction_next=A4-R475-V1-C2-S" in completed.stdout
    assert "s1_a4_intrinsic_source_freeze_packet=A4-R475-V1-C2-S" in completed.stdout
    assert "s1_a4_intrinsic_source_freeze_id=d6e17e638a99" in completed.stdout
    assert (
        "s1_a4_intrinsic_source_freeze_report_id=18dcb2b97a13"
        in completed.stdout
    )
    assert "s1_a4_intrinsic_source_freeze_absent_outputs=5" in completed.stdout
    assert "s1_a4_intrinsic_source_freeze_next=A4-R475-V1-C2-U" in completed.stdout
    assert "s1_a4_intrinsic_upper_packet=A4-R475-V1-C2-U" in completed.stdout
    assert "s1_a4_intrinsic_upper_result_id=b57d8d494524" in completed.stdout
    assert "s1_a4_intrinsic_upper_report_id=07ee9289eec6" in completed.stdout
    assert "s1_a4_intrinsic_upper_census=66/1647" in completed.stdout
    assert "s1_a4_intrinsic_upper_next=A4-R475-V1-C2-A" in completed.stdout
    assert "s1_a4_next_packet=A4-R475-V1-C2-A" in completed.stdout


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


def test_stage1_execution_control_rejects_case435_context_pack_identity_drift() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_case435_context_pack_snapshot"])
    snapshot["case435_context_pack_boundary_delta_id"] = "0" * 64
    with pytest.raises(
        checker.ControlFailure,
        match="case435 context-pack report differs",
    ):
        checker._validate_s1_a4_case435_context_pack_snapshot(
            snapshot,
            control["s1_a4_verifier_expansion_v2_snapshot"],
            control["s1_a4_case435_authority_transition_snapshot"],
        )


def test_stage1_execution_control_rejects_s1_a4_v4_verifier_identity_drift() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_verifier_expansion_v4_snapshot"])
    snapshot["verifier_raw_sha256"] = "0" * 64
    with pytest.raises(checker.ControlFailure, match="V4 verifier hash drifted"):
        checker._validate_s1_a4_verifier_expansion_v4_snapshot(
            snapshot,
            control["s1_a4_verifier_expansion_v3_snapshot"],
            control["s1_a4_case435_authority_transition_snapshot"],
        )


def test_stage1_execution_control_rejects_s1_a4_v_a_report_identity_drift() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_verifier_acceptance_snapshot"])
    snapshot["report_raw_sha256"] = "0" * 64
    with pytest.raises(checker.ControlFailure, match="V-A report hash drifted"):
        checker._validate_s1_a4_verifier_acceptance_snapshot(
            snapshot,
            control["s1_a4_verifier_expansion_v4_snapshot"],
        )


def test_stage1_execution_control_rejects_s1_a4_v_a_reviewer_identity_drift() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_verifier_acceptance_snapshot"])
    snapshot["reviewer_raw_sha256"] = "0" * 64
    with pytest.raises(checker.ControlFailure, match="V-A reviewer hash drifted"):
        checker._validate_s1_a4_verifier_acceptance_snapshot(
            snapshot,
            control["s1_a4_verifier_expansion_v4_snapshot"],
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


def test_stage1_execution_control_rejects_s1_a4_p6_p_report_identity_drift() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_producer_expansion_snapshot"])
    snapshot["report_raw_sha256"] = "0" * 64
    with pytest.raises(checker.ControlFailure, match="P6-P report hash drifted"):
        checker._validate_s1_a4_producer_expansion_snapshot(
            snapshot,
            control["s1_a4_producer_snapshot"],
            control["s1_a4_verifier_acceptance_snapshot"],
            control["s1_a4_case435_context_pack_snapshot"],
        )


def test_stage1_execution_control_rejects_s1_a4_p6_p_advancement_drift() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_producer_expansion_snapshot"])
    snapshot["next_subgate"] = "A4-P6-E"
    with pytest.raises(
        checker.ControlFailure, match="producer-expansion state differs"
    ):
        checker._validate_s1_a4_producer_expansion_snapshot(
            snapshot,
            control["s1_a4_producer_snapshot"],
            control["s1_a4_verifier_acceptance_snapshot"],
            control["s1_a4_case435_context_pack_snapshot"],
        )


def test_stage1_execution_control_rejects_s1_a4_p6_r_report_identity_drift() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_parent_runner_snapshot"])
    snapshot["report_raw_sha256"] = "0" * 64
    with pytest.raises(checker.ControlFailure, match="P6-R report hash drifted"):
        checker._validate_s1_a4_parent_runner_snapshot(
            snapshot,
            control["s1_a4_producer_expansion_snapshot"],
        )


def test_stage1_execution_control_rejects_s1_a4_p6_r_f2_vector_drift() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_parent_runner_snapshot"])
    snapshot["full_run_f2_values"][0] += 1
    with pytest.raises(checker.ControlFailure, match="full-run vector differs"):
        checker._validate_s1_a4_parent_runner_snapshot(
            snapshot,
            control["s1_a4_producer_expansion_snapshot"],
        )


def test_stage1_execution_control_rejects_s1_a4_p6_e_report_identity_drift() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_pilot_end_to_end_snapshot"])
    snapshot["report_raw_sha256"] = "0" * 64
    with pytest.raises(checker.ControlFailure, match="P6-E report hash drifted"):
        checker._validate_s1_a4_pilot_end_to_end_snapshot(
            snapshot,
            control["s1_a4_parent_runner_snapshot"],
        )


def test_stage1_execution_control_rejects_s1_a4_p6_e_scope_overclaim() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_pilot_end_to_end_snapshot"])
    snapshot["current_binaries_all_case_ready"] = True
    with pytest.raises(checker.ControlFailure, match="end-to-end state differs"):
        checker._validate_s1_a4_pilot_end_to_end_snapshot(
            snapshot,
            control["s1_a4_parent_runner_snapshot"],
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
    snapshot = copy.deepcopy(control["s1_a4_case435_authority_transition_snapshot"])
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
    snapshot = copy.deepcopy(control["s1_a4_case435_authority_transition_snapshot"])
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
    snapshot = copy.deepcopy(control["s1_a4_case435_authority_transition_snapshot"])
    snapshot["producer_expansion_state"] = "RELEASED"
    with pytest.raises(checker.ControlFailure, match="transition result drifted"):
        checker._validate_s1_a4_case435_authority_transition_snapshot(
            snapshot,
            control["s1_a4_case435_exactness_join_snapshot"],
            control["seed_snapshot"],
            control["s1_a3_snapshot"],
            control["s1_a4_boundary_snapshot"],
        )


def test_stage1_execution_control_rejects_verifier_v0_historical_seal_drift() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_verifier_expansion_v0_snapshot"])
    snapshot["verifier_raw_sha256"] = "0" * 64
    with pytest.raises(checker.ControlFailure, match="V0 acceptance marker absent"):
        checker._validate_s1_a4_verifier_expansion_v0_snapshot(
            snapshot,
            control["s1_a4_verifier_snapshot"],
            control["s1_a4_boundary_snapshot"],
            control["s1_a4_case435_authority_transition_snapshot"],
        )


def test_stage1_execution_control_rejects_verifier_v1_source_drift() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_verifier_expansion_v1_snapshot"])
    snapshot["verifier_raw_sha256"] = "0" * 64
    with pytest.raises(checker.ControlFailure, match="V1 acceptance marker absent"):
        checker._validate_s1_a4_verifier_expansion_v1_snapshot(
            snapshot,
            control["s1_a4_verifier_expansion_v0_snapshot"],
            control["s1_a4_case435_authority_transition_snapshot"],
        )


def test_stage1_execution_control_rejects_verifier_v2_source_drift() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_verifier_expansion_v2_snapshot"])
    snapshot["verifier_raw_sha256"] = "0" * 64
    with pytest.raises(checker.ControlFailure, match="V2 acceptance marker absent"):
        checker._validate_s1_a4_verifier_expansion_v2_snapshot(
            snapshot,
            control["s1_a4_verifier_expansion_v1_snapshot"],
            control["s1_a4_case435_authority_transition_snapshot"],
        )


def test_stage1_execution_control_rejects_verifier_v2_case69_result_drift() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_verifier_expansion_v2_snapshot"])
    snapshot["case69_maximum_canonical_octets"] += 1
    with pytest.raises(checker.ControlFailure, match="case69 exact result differs"):
        checker._validate_s1_a4_verifier_expansion_v2_snapshot(
            snapshot,
            control["s1_a4_verifier_expansion_v1_snapshot"],
            control["s1_a4_case435_authority_transition_snapshot"],
        )


def test_stage1_execution_control_rejects_verifier_v2_vector_drift() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_verifier_expansion_v2_snapshot"])
    snapshot["case69_resource_vector"][1] += 1
    with pytest.raises(checker.ControlFailure, match="case69 exact result differs"):
        checker._validate_s1_a4_verifier_expansion_v2_snapshot(
            snapshot,
            control["s1_a4_verifier_expansion_v1_snapshot"],
            control["s1_a4_case435_authority_transition_snapshot"],
        )


def test_stage1_execution_control_rejects_verifier_v2_premature_v4() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_verifier_expansion_v2_snapshot"])
    snapshot["ordered_remaining_case_positions"] = [475]
    with pytest.raises(checker.ControlFailure, match="V2 state differs"):
        checker._validate_s1_a4_verifier_expansion_v2_snapshot(
            snapshot,
            control["s1_a4_verifier_expansion_v1_snapshot"],
            control["s1_a4_case435_authority_transition_snapshot"],
        )


def test_stage1_execution_control_rejects_verifier_v1_case24_result_drift() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_verifier_expansion_v1_snapshot"])
    snapshot["case24_maximum_canonical_octets"] -= 1
    with pytest.raises(checker.ControlFailure, match="case24 exact result differs"):
        checker._validate_s1_a4_verifier_expansion_v1_snapshot(
            snapshot,
            control["s1_a4_verifier_expansion_v0_snapshot"],
            control["s1_a4_case435_authority_transition_snapshot"],
        )


def test_stage1_execution_control_rejects_verifier_v1_case54_vector_drift() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_verifier_expansion_v1_snapshot"])
    snapshot["case54_resource_vector"][1] += 1
    with pytest.raises(checker.ControlFailure, match="case54 exact result differs"):
        checker._validate_s1_a4_verifier_expansion_v1_snapshot(
            snapshot,
            control["s1_a4_verifier_expansion_v0_snapshot"],
            control["s1_a4_case435_authority_transition_snapshot"],
        )


def test_stage1_execution_control_rejects_verifier_v1_premature_later_packet() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_verifier_expansion_v1_snapshot"])
    snapshot["ordered_remaining_case_positions"] = [435, 475]
    with pytest.raises(checker.ControlFailure, match="V1 state differs"):
        checker._validate_s1_a4_verifier_expansion_v1_snapshot(
            snapshot,
            control["s1_a4_verifier_expansion_v0_snapshot"],
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


def test_stage1_execution_control_rejects_all_case_contract_identity_drift() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_all_case_contract_snapshot"])
    snapshot["contract_raw_sha256"] = "0" * 64
    with pytest.raises(checker.ControlFailure, match="A4-R475-T contract hash drifted"):
        checker._validate_s1_a4_all_case_contract_snapshot(
            snapshot,
            control["s1_a4_pilot_end_to_end_snapshot"],
        )


def test_stage1_execution_control_rejects_all_case_runtime_overclaim() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_all_case_contract_snapshot"])
    snapshot["versioned_all_case_roles_accepted"] = True
    with pytest.raises(
        checker.ControlFailure,
        match="S1-A4 all-case contract state differs",
    ):
        checker._validate_s1_a4_all_case_contract_snapshot(
            snapshot,
            control["s1_a4_pilot_end_to_end_snapshot"],
        )


def test_stage1_execution_control_rejects_all_case_f2_vector_drift() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_all_case_contract_snapshot"])
    snapshot["required_full_run_f2_values"][0] += 1
    with pytest.raises(
        checker.ControlFailure,
        match="S1-A4 all-case required F2 vector differs",
    ):
        checker._validate_s1_a4_all_case_contract_snapshot(
            snapshot,
            control["s1_a4_pilot_end_to_end_snapshot"],
        )


def test_stage1_execution_control_rejects_all_case_verifier_identity_drift() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(
        control["s1_a4_all_case_verifier_foundation_snapshot"]
    )
    snapshot["verifier_raw_sha256"] = "0" * 64
    with pytest.raises(checker.ControlFailure, match="A4-R475-V0 verifier hash drifted"):
        checker._validate_s1_a4_all_case_verifier_foundation_snapshot(
            snapshot,
            control["s1_a4_all_case_contract_snapshot"],
        )


def test_stage1_execution_control_rejects_all_case_verifier_scope_overclaim() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(
        control["s1_a4_all_case_verifier_foundation_snapshot"]
    )
    snapshot["accepted_constructive_case_count"] = 1
    with pytest.raises(
        checker.ControlFailure,
        match="S1-A4 all-case verifier foundation state differs",
    ):
        checker._validate_s1_a4_all_case_verifier_foundation_snapshot(
            snapshot,
            control["s1_a4_all_case_contract_snapshot"],
        )


def test_stage1_execution_control_rejects_all_case_verifier_packet_skip() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(
        control["s1_a4_all_case_verifier_foundation_snapshot"]
    )
    snapshot["next_bounded_packet"] = "A4-R475-V2"
    with pytest.raises(
        checker.ControlFailure,
        match="S1-A4 all-case verifier foundation state differs",
    ):
        checker._validate_s1_a4_all_case_verifier_foundation_snapshot(
            snapshot,
            control["s1_a4_all_case_contract_snapshot"],
        )


def test_stage1_execution_control_rejects_all_case_verifier_f0_drift() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(
        control["s1_a4_all_case_verifier_foundation_snapshot"]
    )
    snapshot["authority_file_headroom"] -= 1
    with pytest.raises(
        checker.ControlFailure,
        match="S1-A4 all-case verifier F0 evidence differs",
    ):
        checker._validate_s1_a4_all_case_verifier_foundation_snapshot(
            snapshot,
            control["s1_a4_all_case_contract_snapshot"],
        )


def test_stage1_execution_control_rejects_intrinsic_analyzer_identity_drift() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_intrinsic_attainability_snapshot"])
    snapshot["analyzer_raw_sha256"] = "0" * 64
    with pytest.raises(
        checker.ControlFailure,
        match="A4-R475-V1-F-A analyzer hash drifted",
    ):
        checker._validate_s1_a4_intrinsic_attainability_snapshot(
            snapshot,
            control["s1_a4_all_case_verifier_foundation_snapshot"],
        )


def test_stage1_execution_control_rejects_intrinsic_contradiction_count_drift() -> (
    None
):
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_intrinsic_attainability_snapshot"])
    snapshot["contradiction_case_count"] -= 1
    with pytest.raises(
        checker.ControlFailure,
        match="S1-A4 intrinsic-attainability disposition differs",
    ):
        checker._validate_s1_a4_intrinsic_attainability_snapshot(
            snapshot,
            control["s1_a4_all_case_verifier_foundation_snapshot"],
        )


def test_stage1_execution_control_rejects_intrinsic_case8_gap_drift() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_intrinsic_attainability_snapshot"])
    snapshot["case8_unattainable_gap_octets"] += 1
    with pytest.raises(
        checker.ControlFailure,
        match="S1-A4 intrinsic-attainability case8 evidence differs",
    ):
        checker._validate_s1_a4_intrinsic_attainability_snapshot(
            snapshot,
            control["s1_a4_all_case_verifier_foundation_snapshot"],
        )


def test_stage1_execution_control_rejects_intrinsic_v1_acceptance_overclaim() -> (
    None
):
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_intrinsic_attainability_snapshot"])
    snapshot["all_case_v1_acceptance_possible_under_frozen_authority"] = True
    with pytest.raises(
        checker.ControlFailure,
        match="S1-A4 intrinsic-attainability disposition differs",
    ):
        checker._validate_s1_a4_intrinsic_attainability_snapshot(
            snapshot,
            control["s1_a4_all_case_verifier_foundation_snapshot"],
        )


def test_stage1_execution_control_rejects_intrinsic_correction_packet_skip() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_intrinsic_attainability_snapshot"])
    snapshot["next_bounded_packet"] = "A4-R475-V1"
    with pytest.raises(
        checker.ControlFailure,
        match="S1-A4 intrinsic-attainability disposition differs",
    ):
        checker._validate_s1_a4_intrinsic_attainability_snapshot(
            snapshot,
            control["s1_a4_all_case_verifier_foundation_snapshot"],
        )


def test_stage1_execution_control_rejects_c1_contract_identity_drift() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(
        control["s1_a4_intrinsic_correction_contract_snapshot"]
    )
    snapshot["contract_raw_sha256"] = "0" * 64
    with pytest.raises(
        checker.ControlFailure,
        match="A4-R475-V1-C1 contract hash drifted",
    ):
        checker._validate_s1_a4_intrinsic_correction_contract_snapshot(
            snapshot,
            control["s1_a4_intrinsic_attainability_snapshot"],
        )


def test_stage1_execution_control_rejects_c1_dependency_census_drift() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(
        control["s1_a4_intrinsic_correction_contract_snapshot"]
    )
    snapshot["total_case_dependency_records"] -= 1
    with pytest.raises(
        checker.ControlFailure,
        match="S1-A4 intrinsic-correction disposition differs",
    ):
        checker._validate_s1_a4_intrinsic_correction_contract_snapshot(
            snapshot,
            control["s1_a4_intrinsic_attainability_snapshot"],
        )


def test_stage1_execution_control_rejects_c1_exactness_overclaim() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(
        control["s1_a4_intrinsic_correction_contract_snapshot"]
    )
    snapshot["all_66_exact_maxima_accepted"] = True
    with pytest.raises(
        checker.ControlFailure,
        match="S1-A4 intrinsic-correction disposition differs",
    ):
        checker._validate_s1_a4_intrinsic_correction_contract_snapshot(
            snapshot,
            control["s1_a4_intrinsic_attainability_snapshot"],
        )


def test_stage1_execution_control_rejects_c1_source_freeze_weakening() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(
        control["s1_a4_intrinsic_correction_contract_snapshot"]
    )
    snapshot["dual_channel_sources_frozen_before_execution"] = False
    with pytest.raises(
        checker.ControlFailure,
        match="S1-A4 intrinsic-correction disposition differs",
    ):
        checker._validate_s1_a4_intrinsic_correction_contract_snapshot(
            snapshot,
            control["s1_a4_intrinsic_attainability_snapshot"],
        )


def test_stage1_execution_control_rejects_c1_channel_packet_skip() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(
        control["s1_a4_intrinsic_correction_contract_snapshot"]
    )
    snapshot["next_bounded_packet"] = "A4-R475-V1-C2-U"
    with pytest.raises(
        checker.ControlFailure,
        match="S1-A4 intrinsic-correction disposition differs",
    ):
        checker._validate_s1_a4_intrinsic_correction_contract_snapshot(
            snapshot,
            control["s1_a4_intrinsic_attainability_snapshot"],
        )


def test_stage1_execution_control_rejects_c2s_source_identity_drift() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(
        control["s1_a4_intrinsic_dual_source_freeze_snapshot"]
    )
    snapshot["upper_source_raw_sha256"] = "0" * 64
    with pytest.raises(
        checker.ControlFailure,
        match="A4-R475-V1-C2-S upper source hash drifted",
    ):
        checker._validate_s1_a4_intrinsic_dual_source_freeze_snapshot(
            snapshot,
            control["s1_a4_intrinsic_correction_contract_snapshot"],
        )


def test_stage1_execution_control_rejects_c2s_result_overclaim() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(
        control["s1_a4_intrinsic_dual_source_freeze_snapshot"]
    )
    snapshot["channel_results_accepted"] = True
    with pytest.raises(
        checker.ControlFailure,
        match="S1-A4 intrinsic dual-source-freeze disposition differs",
    ):
        checker._validate_s1_a4_intrinsic_dual_source_freeze_snapshot(
            snapshot,
            control["s1_a4_intrinsic_correction_contract_snapshot"],
        )


def test_stage1_execution_control_rejects_c2s_successor_skip() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(
        control["s1_a4_intrinsic_dual_source_freeze_snapshot"]
    )
    snapshot["next_bounded_packet"] = "A4-R475-V1-C2-A"
    with pytest.raises(
        checker.ControlFailure,
        match="S1-A4 intrinsic dual-source-freeze disposition differs",
    ):
        checker._validate_s1_a4_intrinsic_dual_source_freeze_snapshot(
            snapshot,
            control["s1_a4_intrinsic_correction_contract_snapshot"],
        )


def test_stage1_execution_control_rejects_c2u_result_identity_drift() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_intrinsic_upper_channel_snapshot"])
    snapshot["upper_result_raw_sha256"] = "0" * 64
    with pytest.raises(
        checker.ControlFailure,
        match="A4-R475-V1-C2-U upper result hash drifted",
    ):
        checker._validate_s1_a4_intrinsic_upper_channel_snapshot(
            snapshot,
            control["s1_a4_intrinsic_dual_source_freeze_snapshot"],
        )


def test_stage1_execution_control_rejects_c2u_exactness_overclaim() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_intrinsic_upper_channel_snapshot"])
    snapshot["exact_maxima_accepted"] = True
    with pytest.raises(
        checker.ControlFailure,
        match="S1-A4 intrinsic upper-channel disposition differs",
    ):
        checker._validate_s1_a4_intrinsic_upper_channel_snapshot(
            snapshot,
            control["s1_a4_intrinsic_dual_source_freeze_snapshot"],
        )


def test_stage1_execution_control_rejects_c2u_successor_skip() -> None:
    checker = _load_checker()
    control = checker._load_control()
    snapshot = copy.deepcopy(control["s1_a4_intrinsic_upper_channel_snapshot"])
    snapshot["next_bounded_packet"] = "A4-R475-V1-C3"
    with pytest.raises(
        checker.ControlFailure,
        match="S1-A4 intrinsic upper-channel disposition differs",
    ):
        checker._validate_s1_a4_intrinsic_upper_channel_snapshot(
            snapshot,
            control["s1_a4_intrinsic_dual_source_freeze_snapshot"],
        )

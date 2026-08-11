from __future__ import annotations

import ast
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHECKER = (
    ROOT
    / "scripts/tests/check_raw_v8_step2_maximum_protocol_v2_profile_attainability_scope_v49f.py"
)

SPEC = importlib.util.spec_from_file_location(
    "profile_attainability_scope_v49f", CHECKER
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

EXPECTED_CORE = {
    "affected_case_position_vector_sha256": (
        "1fa6eb9883e12d3e901dca4af938fbb13131fd06c43e0e4f6ce98e86d3813748"
    ),
    "affected_profile_id_vector_sha256": (
        "b4c3cdc7ef2822a068300f5bd7280d5d88ce14f96d9eee6ae32e23418c9ec907"
    ),
    "affected_profile_record_vector_sha256": (
        "59cf77bfade5b3f53c96ef7d53eb2afccff2b3ca146a8c43f8296726aa02c244"
    ),
    "affected_program_id_vector_sha256": (
        "5600deb5f597db75b8061b9c522add7fb7bd0ff2d6b415ce48194fbab3b81af1"
    ),
    "affected_publication_case_maximum": 474,
    "affected_publication_case_minimum": 67,
    "application_aware_exact_program_count": 1,
    "application_aware_exact_scope_case_count": 1,
    "audit_version": (
        "riskyieldmm.raw_v8_step2.maximum_protocol_v2."
        "profile_attainability_scope_audit.v1"
    ),
    "case435_is_affected": True,
    "current_catalog_satisfies_application_aware_exactness": False,
    "exact_control_case_position": 69,
    "inventory_raw_sha256": (
        "de91eac92d1c36cf1670b2484392fbf1c633d75f928c8e70fcd5e71ae798db2b"
    ),
    "logical_plan_recipe_catalog_id": (
        "727f4008c6cd469fe2a9c7f833b0bb6a56ba18a17009871e7fb4ceaa2c0aede8"
    ),
    "p1_p3_exact_equality_program_count": 408,
    "profile_attainability_scope_audit_id": (
        "10e0ce8a277053e7d4e04d08fada484ccc656c92607eba2d8f2518c1fe8fd09a"
    ),
    "profile_program_count": 408,
    "profile_scope_case_count": 475,
    "required_disposition": (
        "NO_GO_UNTIL_EACH_GENERIC_PROFILE_HAS_A_PROVED_LEGAL_UPPER_BOUND_"
        "AND_AN_INDEPENDENT_LEGAL_ATTAINER"
    ),
    "seed_catalog_id": (
        "ac22151fa74702ac1488924f01161eaa38574545e6272a290db6b0bbd288ae5f"
    ),
    "seed_raw_sha256": (
        "a75a2f352e8513b7ff0043693a0c65ebbf4bc6f06859354789af69e1162b0e4f"
    ),
    "selected_correction_contract_id": (
        "e95d6f101942c0f1171616f0b05cf8978991fda639fc63a355765dd73b18c37b"
    ),
    "structural_superset_application_invocation_count": 46_266,
    "structural_superset_cross_rule_evaluation_count": 4_198_490,
    "structural_superset_deleted_cross_application_count": 2_023,
    "structural_superset_direct_cross_expression_node_count": 42_023_958,
    "structural_superset_program_count": 407,
    "structural_superset_scope_case_count": 474,
    "structural_superset_selector_absent_scope_case_count": 47,
    "structural_superset_selector_present_scope_case_count": 427,
}

EXPECTED_GROUPS = [
    (
        "CapacityMeasurementOperationResultEvidence",
        "OUTER_RESULT_BOUNDARY_FIXTURE",
        "ACK_DEADLINE_EXPIRY",
        "FROZEN_FIXTURE",
        1,
        1,
        1,
        1,
        3,
    ),
    (
        "CapacityMeasurementOperationResultEvidence",
        "OUTER_RESULT_BOUNDARY_FIXTURE",
        "INGRESS",
        "FROZEN_FIXTURE",
        1,
        1,
        1,
        1,
        3,
    ),
    (
        "CapacityMeasurementOperationResultEvidence",
        "OUTER_RESULT_BOUNDARY_FIXTURE",
        "SUBSCRIPTION_DISPATCH",
        "FROZEN_FIXTURE",
        1,
        1,
        1,
        1,
        3,
    ),
    (
        "TargetObservationV2",
        "CHECKPOINT_ROOT_COORDINATE",
        "ACK_DEADLINE_EXPIRY",
        "FROZEN_ROOT_APPLICATION",
        15,
        15,
        225,
        16_860,
        168_585,
    ),
    (
        "TargetObservationV2",
        "CHECKPOINT_ROOT_COORDINATE",
        "INGRESS",
        "FROZEN_ROOT_APPLICATION",
        340,
        340,
        44_180,
        4_036_140,
        40_400_140,
    ),
    (
        "TargetObservationV2",
        "CHECKPOINT_ROOT_COORDINATE",
        "LOCAL_SHUTDOWN",
        "FROZEN_ROOT_APPLICATION",
        25,
        25,
        475,
        37_450,
        374_575,
    ),
    (
        "TargetObservationV2",
        "CHECKPOINT_ROOT_COORDINATE",
        "SUBSCRIPTION_DISPATCH",
        "FROZEN_ROOT_APPLICATION",
        20,
        20,
        340,
        26_220,
        262_220,
    ),
    (
        "TargetObservationV2",
        "NON_CHECKPOINT_ROOT_FAMILY",
        "ACK_DEADLINE_EXPIRY",
        "FROZEN_ROOT_APPLICATION",
        1,
        17,
        152,
        10_495,
        104_918,
    ),
    (
        "TargetObservationV2",
        "NON_CHECKPOINT_ROOT_FAMILY",
        "INGRESS",
        "FROZEN_ROOT_APPLICATION",
        1,
        20,
        569,
        48_649,
        486_827,
    ),
    (
        "TargetObservationV2",
        "NON_CHECKPOINT_ROOT_FAMILY",
        "LOCAL_SHUTDOWN",
        "FROZEN_ROOT_APPLICATION",
        1,
        17,
        164,
        11_617,
        116_150,
    ),
    (
        "TargetObservationV2",
        "NON_CHECKPOINT_ROOT_FAMILY",
        "SUBSCRIPTION_DISPATCH",
        "FROZEN_ROOT_APPLICATION",
        1,
        17,
        158,
        11_056,
        110_534,
    ),
]


def _group_tuple(row: dict[str, object]) -> tuple[object, ...]:
    return tuple(
        row[name]
        for name in (
            "measured_type_name",
            "profile_kind",
            "operation_kind",
            "constraint_scope",
            "program_count",
            "scope_case_count",
            "application_invocation_count",
            "cross_rule_evaluation_count",
            "direct_cross_expression_node_count",
        )
    )


def _unpinned_authorities() -> tuple[dict[str, object], dict[str, object]]:
    seed = json.loads((ROOT / MODULE.SEED_RELATIVE_PATH).read_bytes())
    inventory = json.loads((ROOT / MODULE.INVENTORY_RELATIVE_PATH).read_bytes())
    return seed, inventory


def _analyze_mutation(
    monkeypatch: pytest.MonkeyPatch,
    seed: dict[str, object],
    inventory: dict[str, object],
) -> dict[str, object]:
    values = iter((seed, inventory))
    monkeypatch.setattr(MODULE, "_load_pinned", lambda *_args: next(values))
    return MODULE.analyze(ROOT)


def test_scope_audit_freezes_every_structural_p2_equality_surface() -> None:
    report = MODULE.analyze(ROOT)
    assert {name: report[name] for name in EXPECTED_CORE} == EXPECTED_CORE
    assert report["selected_correction_contract"] == MODULE.CORRECTION_CONTRACT
    assert [_group_tuple(row) for row in report["ordered_affected_group_records"]] == (
        EXPECTED_GROUPS
    )
    assert report["ordered_cross_rule_ids"] == [
        "RULE/CROSS/OPERATION_RESULT_SIGNED_SPEC_V1",
        "RULE/CROSS/SELECTOR_MARKER_CONTRACT_V1",
        "RULE/CROSS/V2_OBSERVATION_AGGREGATE_REGISTRY_V1",
        "RULE/CROSS/V2_OBSERVATION_FIELD_REGISTRY_V1",
        "RULE/CROSS/V2_ROOT_OBSERVATION_MEMBERSHIP_V1",
        "RULE/CROSS/V2_ROOT_SELECTOR_LIFECYCLE_V1",
    ]
    assert report["ordered_safe_relaxation_rule_ids"] == [
        "02629a9730fabf33d77257a3ff505230bbef5cdf6c902982ef88eba3b73181b6",
        "593c30d595d5fe7c3ed25f0eef9bc6a22ecc33c85c95e06a96c447f13dc6f8b0",
        "6ca1835abf942badf8d2245f6f1a6a4c8c83d370b2f7c0b3acb7d8d8219c6d5e",
        "c607e3d096e4eb35151480a574ceded7c89ff9d64310da4af08e6463eb1f0fdf",
    ]


def test_scope_audit_cli_is_deterministic_and_silent_on_stderr() -> None:
    first = subprocess.run(
        [sys.executable, str(CHECKER), str(ROOT)],
        cwd=ROOT,
        check=False,
        capture_output=True,
    )
    second = subprocess.run(
        [sys.executable, str(CHECKER), str(ROOT)],
        cwd=ROOT,
        check=False,
        capture_output=True,
    )
    assert first.returncode == second.returncode == 0
    assert first.stderr == second.stderr == b""
    assert first.stdout == second.stdout
    assert (
        json.loads(first.stdout)["profile_attainability_scope_audit_id"]
        == (EXPECTED_CORE["profile_attainability_scope_audit_id"])
    )


def test_scope_audit_is_independent_of_generator_runtime_and_candidate_pair() -> None:
    source = CHECKER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_roots.add(node.module.split(".", 1)[0])
    assert imported_roots == {
        "__future__",
        "hashlib",
        "json",
        "pathlib",
        "sys",
        "typing",
    }
    forbidden = (
        "generate_raw_v8_step2_maximum_protocol_v2_seed_catalog",
        "produce_raw_v8_step2_maximum_protocol_v2_candidate",
        "verify_raw_v8_step2_maximum_protocol_v2_candidate",
        "validate_raw_v8_step2_external_schema_v2_rule_runtime",
        "raw_v8_step2_external_schema_v2_application_witness",
    )
    assert all(fragment not in source for fragment in forbidden)


def test_fail_first_exactness_boundary_rejects_current_catalog() -> None:
    report = MODULE.analyze(ROOT)
    with pytest.raises(
        MODULE.ProfileScopeAuditError,
        match=(
            "A4_P6_C435_APPLICATION_AWARE_EXACTNESS_NOT_IMPLEMENTED: "
            "407 programs / 474 scope cases remain"
        ),
    ):
        MODULE.require_corrected_application_aware_contract(report)


@pytest.mark.parametrize(
    ("relative_path", "digest"),
    [
        (MODULE.SEED_RELATIVE_PATH, "0" * 64),
        (MODULE.INVENTORY_RELATIVE_PATH, "f" * 64),
    ],
)
def test_scope_audit_rejects_unpinned_authority(
    relative_path: str,
    digest: str,
) -> None:
    with pytest.raises(MODULE.ProfileScopeAuditError, match="authority hash differs"):
        MODULE._load_pinned(ROOT, relative_path, digest)


def test_scope_audit_rejects_structural_p2_disguised_as_exact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed, inventory = _unpinned_authorities()
    program = seed["logical_plan_recipe_catalog"][
        "ordered_profile_conditioning_program_records"
    ][368]
    program["conditioning_transfer_program"]["p2_upper_bound_program"][
        "ordered_instruction_records"
    ][0]["output_type"] = "P2_EXACT_ATTAINED_CELL"
    with pytest.raises(
        MODULE.ProfileScopeAuditError,
        match="generic structural-only P2 differs: 435",
    ):
        _analyze_mutation(monkeypatch, seed, inventory)


def test_scope_audit_rejects_missing_cross_application_deletion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed, inventory = _unpinned_authorities()
    program = seed["logical_plan_recipe_catalog"][
        "ordered_profile_conditioning_program_records"
    ][368]
    program["conditioning_transfer_program"]["p2_upper_bound_program"][
        "ordered_deleted_cross_application_references"
    ].pop()
    with pytest.raises(
        MODULE.ProfileScopeAuditError,
        match="generic cross-application deletion coverage differs: 435",
    ):
        _analyze_mutation(monkeypatch, seed, inventory)


def test_scope_audit_rejects_weakened_p1_p3_equality(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed, inventory = _unpinned_authorities()
    program = seed["logical_plan_recipe_catalog"][
        "ordered_profile_conditioning_program_records"
    ][368]
    program["conditioning_transfer_program"]["p1_p3_attainment_program"][
        "ordered_instruction_records"
    ][-1]["parameters"]["acceptance_rule"] = "P1_TRUE_AND_LENGTH_LE_P2_UPPER"
    with pytest.raises(
        MODULE.ProfileScopeAuditError,
        match="program 369 P1/P3 acceptance differs",
    ):
        _analyze_mutation(monkeypatch, seed, inventory)


def test_scope_audit_rejects_profile_plan_root_substitution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed, inventory = _unpinned_authorities()
    plan = seed["logical_plan_recipe_catalog"]["ordered_logical_count_plan_records"][
        434
    ]
    plan["logical_root_reference"]["root_id"] = "0" * 64
    with pytest.raises(
        MODULE.ProfileScopeAuditError,
        match="program/plan root binding differs: 435",
    ):
        _analyze_mutation(monkeypatch, seed, inventory)

from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
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
CONTRACT = (
    ROOT
    / "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "all_case_campaign_contract_v49f.json"
)
PREDECESSOR_BOUNDARY = (
    ROOT
    / "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "constructive_boundary_v49f.json"
)


def _load_module():
    specification = importlib.util.spec_from_file_location(
        "a4_r475_v0_all_case_verifier",
        VERIFIER,
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def verifier_module():
    return _load_module()


@pytest.fixture(scope="module")
def foundation(verifier_module):
    return verifier_module._load_foundation(ROOT, CONTRACT)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _reseal_mutated_contract(module, contract):
    rows = contract["case_universe_contract"]["ordered_case_execution_records"]
    contract["case_universe_contract"]["ordered_case_execution_records_sha256"] = (
        module._sha256(module._canonical_bytes(rows))
    )
    contract["case_universe_contract"]["case_execution_ledger_id"] = (
        module._semantic_id(
            module.CASE_LEDGER_DOMAIN,
            {"case_count": 475, "ordered_case_execution_records": rows},
        )
    )
    contract["all_case_campaign_contract_id"] = module._semantic_id(
        module.CONTRACT_DOMAIN,
        module._contract_payload(contract),
    )


def test_v0_source_is_new_isolated_role_and_predecessor_is_unchanged(
    verifier_module,
    foundation,
) -> None:
    assert VERIFIER.is_file() and not VERIFIER.is_symlink()
    assert verifier_module.SOURCE_MARKER == (
        "INDEPENDENT_V2_ALL_CASE_CONSTRUCTIVE_VERIFIER_V1"
    )
    predecessor = next(
        record
        for record in foundation.contract["authority_contract"][
            "ordered_authority_records"
        ]
        if record["authority_role"] == "PILOT_VERIFIER"
    )
    predecessor_path = ROOT / predecessor["repository_relative_path"]
    predecessor_raw = predecessor_path.read_bytes()
    assert (len(predecessor_raw), _sha256(predecessor_raw)) == (
        predecessor["raw_octets"],
        predecessor["raw_sha256"],
    )
    assert predecessor_path != VERIFIER


def test_foundation_reconstructs_exact_complete_case_universe(
    verifier_module,
    foundation,
) -> None:
    report = verifier_module._foundation_report(foundation)
    assert report == {
        "acceptance_scope": "AUTHORITY_AND_TYPED_RULE_FOUNDATION_ONLY",
        "accepted_constructive_case_count": 0,
        "all_case_campaign_contract_id": verifier_module.CONTRACT_ID,
        "all_other_cases_resolve_to_base_seed": True,
        "authority_file_count": 18,
        "candidate_access_state": "FORBIDDEN_IN_V0",
        "case435_effective_plan_id": (
            "343259e38b6050fac5905fdc7ed6dca6d345d32c07b8370085bdf865793e7ad8"
        ),
        "case_count": 475,
        "execution_family_counts": verifier_module.EXPECTED_FAMILIES,
        "formal_stage1_state": "NO-GO",
        "next_bounded_packet": "A4-R475-V1",
        "packet": "A4-R475-V0",
        "pinned_input_octets": 16_717_988,
        "source_marker": verifier_module.SOURCE_MARKER,
        "typed_runtime_application_count": 8,
        "typed_runtime_rule_count": 42,
        "typed_runtime_sha256": verifier_module.RUNTIME_SHA256,
    }
    assert [row["case_position"] for row in foundation.case_records] == list(
        range(1, 476)
    )
    assert len({row["case_execution_record_id"] for row in foundation.case_records}) == 475


def test_only_case435_resolves_through_successor_plan(
    verifier_module,
    foundation,
) -> None:
    successor_rows = [
        row
        for row in foundation.case_records
        if row["effective_plan_source"] == "CASE435_SUCCESSOR_DELTA"
    ]
    assert [row["case_position"] for row in successor_rows] == [435]
    record, case, plan = verifier_module._resolve_case_and_plan(foundation, 435)
    assert record["execution_family"] == "CORRECTED_APPLICATION_EXACT_PROFILE"
    assert record["candidate_transport"] == "CASE435_PACKED_CONTEXT_V1"
    assert case["case_position"] == plan["case_position"] == 435
    assert plan["logical_count_plan_id"] == (
        "343259e38b6050fac5905fdc7ed6dca6d345d32c07b8370085bdf865793e7ad8"
    )
    base_plans = foundation.values["SEED"]["logical_plan_recipe_catalog"][
        "ordered_logical_count_plan_records"
    ]
    for position in (1, 5, 24, 54, 69, 434, 436, 475):
        _, _, resolved = verifier_module._resolve_case_and_plan(
            foundation,
            position,
        )
        assert resolved == base_plans[position - 1]


def test_typed_legality_and_rule_ast_foundation_execute_distinct_outcomes(
    verifier_module,
    foundation,
) -> None:
    positive = {
        "kind": "FIXED_UINT_MAP",
        "ordered": [{"key": "a", "value": 1}, {"key": "b", "value": 2}],
    }
    typed = verifier_module._validate_typed_value(
        foundation,
        "CapacityMeasurementFixedUIntMapValueV1",
        positive,
    )
    assert typed.type_name == "CapacityMeasurementFixedUIntMapValueV1"
    rule_id = "RULE/INTRINSIC/CapacityMeasurementFixedUIntMapValueV1/V1"
    accepted = verifier_module._evaluate_rule_ast(
        foundation,
        rule_id,
        {"self": positive},
    )
    assert accepted.root_value is True
    negative = copy.deepcopy(positive)
    negative["ordered"].reverse()
    rejected = verifier_module._evaluate_rule_ast(
        foundation,
        rule_id,
        {"self": negative},
        require_true=False,
    )
    assert rejected.root_value is False
    with pytest.raises(foundation.runtime_module.BusinessRuleFalse):
        verifier_module._evaluate_rule_ast(
            foundation,
            rule_id,
            {"self": negative},
        )


def test_runtime_capability_is_complete_but_not_a_maximum_claim(foundation) -> None:
    report = foundation.runtime_report
    assert report["executable_rule_count"] == report["total_rule_count"] == 42
    assert report["executable_generic_rule_count"] == 33
    assert report["executable_complex_rule_count"] == 9
    assert report["unsupported_complex_rule_count"] == 0
    assert report["executable_application_count"] == 8
    assert report["fixed_position_resolver_count"] == 2
    assert report["status"] == (
        "APPLICATION_RUNTIME_ONLY_MAXIMA_AND_PRODUCTION_INTEGRATION_PENDING"
    )


def test_v0_cli_rejects_before_candidate_or_output_access(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate-must-remain-absent"
    output = tmp_path / "output-must-remain-absent"
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            str(VERIFIER),
            "--repository-root",
            str(ROOT),
            "--boundary",
            str(CONTRACT),
            "--candidate-root",
            str(candidate),
            "--output-root",
            str(output),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 1
    assert completed.stdout == ""
    assert completed.stderr == (
        "RAW_V8_STEP2_MAXIMUM_PROTOCOL_V2_ALL_CASE_VERIFIER_FOUNDATION_ONLY: "
        "A4-R475-V0 accepts no case and did not open candidate or output paths\n"
    )
    assert not candidate.exists()
    assert not output.exists()


def test_unknown_boundary_and_argument_reordering_fail_without_output(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "absent-candidate"
    output = tmp_path / "absent-output"
    wrong_boundary = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            str(VERIFIER),
            "--repository-root",
            str(ROOT),
            "--boundary",
            str(PREDECESSOR_BOUNDARY),
            "--candidate-root",
            str(candidate),
            "--output-root",
            str(output),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert wrong_boundary.returncode == 2
    assert "boundary path is not the accepted all-case contract" in (
        wrong_boundary.stderr
    )
    reordered = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            str(VERIFIER),
            "--boundary",
            str(CONTRACT),
            "--repository-root",
            str(ROOT),
            "--candidate-root",
            str(candidate),
            "--output-root",
            str(output),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert reordered.returncode == 2
    assert "expected four fixed-order option/value pairs" in reordered.stderr
    assert not candidate.exists() and not output.exists()


def test_coherently_resealed_case_ledger_mutation_is_rejected(
    verifier_module,
    foundation,
) -> None:
    hostile = copy.deepcopy(foundation.contract)
    row = hostile["case_universe_contract"]["ordered_case_execution_records"][0]
    row["effective_logical_count_plan_id"] = "0" * 64
    row_payload = {
        name: value
        for name, value in row.items()
        if name != "case_execution_record_id"
    }
    row["case_execution_record_id"] = verifier_module._semantic_id(
        verifier_module.CASE_RECORD_DOMAIN,
        row_payload,
    )
    _reseal_mutated_contract(verifier_module, hostile)
    assert hostile["all_case_campaign_contract_id"] != verifier_module.CONTRACT_ID
    with pytest.raises(
        verifier_module.VerifierReject,
        match="all-case execution ledger differs",
    ):
        verifier_module._validate_case_ledger(hostile, foundation.values)


def test_resealed_role_scope_overclaim_is_rejected(verifier_module, foundation) -> None:
    hostile = copy.deepcopy(foundation.contract)
    hostile["gate_contract"]["all_case_implementation_state"] = "ACCEPTED"
    hostile["versioned_role_contract"]["ordered_role_records"][0][
        "implementation_state"
    ] = "ACCEPTED"
    _reseal_mutated_contract(verifier_module, hostile)
    with pytest.raises(
        verifier_module.VerifierReject,
        match="all-case contract identity differs|all-case gate contract differs",
    ):
        verifier_module._validate_contract_surface(hostile)


def test_snapshot_drift_and_inode_aliases_fail_closed(
    verifier_module,
    foundation,
) -> None:
    hostile = [dict(snapshot) for snapshot in foundation.authority_snapshots]
    hostile[0]["raw_sha256"] = "0" * 64
    with pytest.raises(verifier_module.VerifierReject, match="bytes drifted"):
        verifier_module._recheck_snapshots(tuple(hostile))
    duplicate = list(foundation.authority_snapshots)
    duplicate.append(dict(duplicate[0]))
    with pytest.raises(verifier_module.VerifierReject, match="inode alias"):
        verifier_module._recheck_snapshots(tuple(duplicate))


def test_foundation_stays_inside_immutable_f0(foundation) -> None:
    assert len(foundation.authority_snapshots) == 18
    assert len(foundation.authority_snapshots) < foundation.f0_limits[
        "INPUT_FILE_COUNT"
    ]
    assert foundation.pinned_input_octets == 16_717_988
    assert foundation.pinned_input_octets < foundation.f0_limits[
        "TOTAL_PINNED_INPUT_OCTETS"
    ]


def test_source_has_no_role_import_or_candidate_access_surface() -> None:
    source = VERIFIER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported.update(
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    )
    assert imported <= {
        "__future__",
        "dataclasses",
        "hashlib",
        "json",
        "os",
        "pathlib",
        "stat",
        "sys",
        "types",
        "typing",
    }
    for forbidden in (
        "produce_raw_v8_step2_maximum_protocol_v2_candidate_v49f",
        "verify_raw_v8_step2_maximum_protocol_v2_candidate_v49f",
        "run_raw_v8_step2_maximum_protocol_v2_pilot_v49f",
        "subprocess",
        "pickle",
        "eval(",
    ):
        assert forbidden not in source
    function_names = {
        node.name for node in tree.body if isinstance(node, ast.FunctionDef)
    }
    assert "_load_foundation" in function_names
    assert "_evaluate_rule_ast" in function_names
    assert "_verify_foundation_only" in function_names

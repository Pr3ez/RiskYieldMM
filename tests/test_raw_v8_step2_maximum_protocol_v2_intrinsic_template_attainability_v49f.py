from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHECKER = (
    ROOT / "scripts/tests/check_raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_template_attainability_v49f.py"
)
RUNTIME = (
    ROOT / "scripts/tests/validate_raw_v8_step2_external_schema_v2_rule_runtime_v49f.py"
)

EXPECTED_POSITIONS = [
    1,
    2,
    7,
    8,
    9,
    12,
    18,
    19,
    21,
    22,
    25,
    28,
    30,
    31,
    32,
    34,
    36,
    37,
    42,
    44,
    45,
    48,
    49,
    52,
    59,
    60,
]
EXPECTED_BOUNDS = {
    1: (524_735, 3_132),
    2: (3_145_728, 467),
    7: (3_145_728, 2_261),
    8: (524_288, 928),
    9: (524_288, 2_685),
    12: (3_145_728, 291),
    18: (3_145_728, 1_092),
    19: (3_145_728, 206),
    21: (3_145_728, 2_099_068),
    22: (523_728, 3_132),
    25: (523_724, 36_277),
    28: (2_096_781, 467),
    30: (2_096_791, 1_092),
    31: (2_096_777, 2_042),
    32: (3_072, 563),
    34: (3_145_728, 22_571),
    36: (3_145_728, 36_277),
    37: (3_145_728, 2_042),
    42: (3_072, 563),
    44: (3_072, 538),
    45: (3_072, 2_091),
    48: (3_072, 2_091),
    49: (3_072, 538),
    52: (3_145_728, 2_727),
    59: (2_048, 1_312),
    60: (2_048, 1_071),
}
EXPECTED_ANALYSIS_ID = (
    "0b53bd2d79c5f923f1887f7e33f167625fd43753c22345074ae2768dec0d58ad"
)
EXPECTED_VECTOR_SHA256 = (
    "3d1c35477e174cde53ab163c516dea9d7132a468bfa7c7954f1ca538317f8e5d"
)
EXPECTED_CASE8_SHA256 = (
    "9156a97a005f9d2264e34054f071a6b15169f88b23be54cb59bc254362888665"
)


def _load_module(name: str, path: Path):
    specification = importlib.util.spec_from_file_location(name, path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def checker():
    return _load_module("intrinsic_template_attainability_v49f", CHECKER)


@pytest.fixture(scope="module")
def result(checker):
    return checker.analyze(ROOT)


def test_intrinsic_language_aware_superset_falsifies_26_frozen_endpoints(
    result,
) -> None:
    assert result["packet"] == "A4-R475-V1-F"
    assert result["decision"] == ("NO_GO_FROZEN_INTRINSIC_P2_ENDPOINTS_UNATTAINABLE")
    assert result["formal_stage1_state"] == "NO-GO"
    assert result["intrinsic_case_count"] == 66
    assert result["contradiction_case_count"] == 26
    assert result["not_falsified_by_text_ceiling_case_count"] == 40
    assert result["contradiction_case_positions"] == EXPECTED_POSITIONS
    assert result["contradiction_vector_sha256"] == EXPECTED_VECTOR_SHA256
    assert result["attainability_falsification_id"] == EXPECTED_ANALYSIS_ID
    assert result["all_66_p3_equality_possible"] is False
    assert result["required_action"] == (
        "VERSIONED_INTRINSIC_TEMPLATE_AUTHORITY_REPAIR_BEFORE_A4_R475_V1"
    )
    assert result["next_bounded_packet"] == "A4-R475-V1-C"

    records = result["ordered_contradiction_records"]
    assert [row["case_position"] for row in records] == EXPECTED_POSITIONS
    assert {
        row["case_position"]: (
            row["published_p2_upper_bound_octets"],
            row["language_aware_legal_superset_upper_bound_octets"],
        )
        for row in records
    } == EXPECTED_BOUNDS
    for row in records:
        assert row["p3_equality_possible"] is False
        assert (
            row["language_aware_legal_superset_upper_bound_octets"]
            + row["unattainable_gap_octets"]
            == row["published_p2_upper_bound_octets"]
        )
        assert row["unattainable_gap_octets"] > 0
        assert row["ordered_restored_language_kinds"]


def test_case8_exact_attainer_closes_the_corrected_928_octet_endpoint(
    checker,
    result,
) -> None:
    evidence = result["case8_exactness_witness"]
    witness = evidence["witness_record"]
    assert evidence["exact_legal_maximum_octets"] == 928
    assert evidence["exact_legal_maximum_sha256"] == EXPECTED_CASE8_SHA256
    assert len(checker._canonical_bytes(witness)) == 928
    assert hashlib.sha256(checker._canonical_bytes(witness)).hexdigest() == (
        EXPECTED_CASE8_SHA256
    )
    assert evidence["identity_field"] == "dispatch_window_evidence_id"
    assert witness[evidence["identity_field"]] == evidence["identity_value"]
    assert evidence["standalone_identity_recomputed"] is True
    assert evidence["intrinsic_rule_satisfied"] is True


def test_case8_independent_attainer_agrees_with_pinned_typed_runtime(result) -> None:
    runtime_module = _load_module(
        "intrinsic_template_attainability_runtime_differential_v49f", RUNTIME
    )
    runtime = runtime_module.ExternalSchemaV2Runtime.load(ROOT)
    evidence = result["case8_exactness_witness"]
    witness = evidence["witness_record"]
    declared = runtime.validate_type(
        "CapacityMeasurementDispatchWindowEvidenceV1", witness
    )
    assert declared.type_name == "CapacityMeasurementDispatchWindowEvidenceV1"
    evaluation = runtime.evaluate_rule(evidence["intrinsic_rule_id"], {"self": witness})
    assert evaluation.root_value is True


def test_intrinsic_checker_cli_is_byte_deterministic_and_silent() -> None:
    command = [sys.executable, str(CHECKER), str(ROOT)]
    first = subprocess.run(command, cwd=ROOT, check=False, capture_output=True)
    second = subprocess.run(command, cwd=ROOT, check=False, capture_output=True)
    assert first.returncode == second.returncode == 0
    assert first.stderr == second.stderr == b""
    assert first.stdout == second.stdout
    decoded = json.loads(first.stdout)
    assert decoded["attainability_falsification_id"] == EXPECTED_ANALYSIS_ID
    assert decoded["contradiction_vector_sha256"] == EXPECTED_VECTOR_SHA256


def test_intrinsic_checker_is_independent_of_roles_runtime_and_witnesses() -> None:
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
        "re",
        "sys",
        "typing",
    }
    forbidden_fragments = (
        "produce_raw_v8_step2_maximum_protocol_v2",
        "verify_raw_v8_step2_maximum_protocol_v2",
        "validate_raw_v8_step2_external_schema_v2_rule_runtime",
        "test_raw_v8_step2_maximum_protocol_v2_cell_transfer",
        "generic_rule_witness",
        "complex_rule_witness",
        "application_witness",
    )
    assert all(fragment not in source for fragment in forbidden_fragments)
    assert "over-approximation of the P1-legal domain" in source
    assert "no legal witness can satisfy P3 equality" in source


@pytest.mark.parametrize(
    ("relative_path", "octets", "digest"),
    [
        (
            "scripts/tests/raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.json",
            13_419_905,
            "0" * 64,
        ),
        (
            "scripts/tests/raw_v8_step2_external_schema_v2_structural_registry_v49f.json",
            1_469_663,
            "1" * 64,
        ),
        (
            "scripts/tests/raw_v8_step2_maximum_protocol_v2_all_case_campaign_contract_v49f.json",
            382_710,
            "f" * 64,
        ),
    ],
)
def test_intrinsic_checker_rejects_any_unpinned_authority(
    checker,
    relative_path: str,
    octets: int,
    digest: str,
) -> None:
    with pytest.raises(
        checker.IntrinsicAttainabilityError, match="authority hash differs"
    ):
        checker._load_pinned(ROOT, relative_path, octets, digest)


def test_40_unfalsified_cases_are_not_promoted_to_attainability(result) -> None:
    assert result["nonclaim"] == (
        "UNCHANGED_CASES_ARE_NOT_PROVEN_ATTAINABLE_BY_THIS_ANALYSIS"
    )
    assert "attainable_case_count" not in result
    assert "accepted_constructive_case_count" not in result


def test_accepted_six_case_verifier_remains_byte_exact() -> None:
    contract = json.loads(
        (
            ROOT
            / "scripts/tests/raw_v8_step2_maximum_protocol_v2_all_case_campaign_contract_v49f.json"
        ).read_bytes()
    )
    authority = next(
        row
        for row in contract["authority_contract"]["ordered_authority_records"]
        if row["authority_role"] == "PILOT_VERIFIER"
    )
    raw = (ROOT / authority["repository_relative_path"]).read_bytes()
    assert len(raw) == authority["raw_octets"]
    assert hashlib.sha256(raw).hexdigest() == authority["raw_sha256"]

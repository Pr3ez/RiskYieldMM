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
    / "scripts/tests/check_raw_v8_step2_maximum_protocol_v2_case435_attainability_v49f.py"
)

SPEC = importlib.util.spec_from_file_location("case435_attainability_v49f", CHECKER)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

EXPECTED = {
    "analysis_version": (
        "riskyieldmm.raw_v8_step2.maximum_protocol_v2.case435_attainability.v1"
    ),
    "attainability_analysis_id": (
        "b126fb9bef8439baf49c993c036c80a874a03ab0e8f6ab1be016d140dd5d0491"
    ),
    "case_position": 435,
    "constraint_scope_profile_id": (
        "505dac244288e6fb666919c99567f883c28ed573a898ce2a5dd680744dd57540"
    ),
    "constructed_superset_canonical_sha256": (
        "cc7e307b1a7f20dc99b9288441701f4d704e63e088e6dd23e25d7488cee9df36"
    ),
    "context_structural_superset_canonical_octets": 1_954,
    "derived_legal_domain_superset_upper_bound_octets": 260_909,
    "field_array_syntax_octets": 186,
    "field_superset_upper_bound_sum_octets": 258_347,
    "inventory_raw_sha256": (
        "de91eac92d1c36cf1670b2484392fbf1c633d75f928c8e70fcd5e71ae798db2b"
    ),
    "logical_count_plan_id": (
        "9f8cd8303e3a9360986f0294210dda931e827af6eed4ec76b0c084e54f722c4a"
    ),
    "measured_sequence_ordinal": 64,
    "observation_fixed_nonfield_octets": 2_376,
    "ordered_field_superset_bound_vector_sha256": (
        "8ce7e847cf0020ca6ab10f763f7702cc6aad82e7043a865ce55574af6bd73b57"
    ),
    "p2_structural_upper_bound_octets": 262_143,
    "p3_equality_possible": False,
    "p3_unattainable_gap_octets": 1_234,
    "registry_raw_sha256": (
        "9160297ff316c5931737c92f8b359f0a1e2ec22f0aa996ef3b09cf830dc96bf3"
    ),
    "seed_raw_sha256": (
        "a75a2f352e8513b7ff0043693a0c65ebbf4bc6f06859354789af69e1162b0e4f"
    ),
    "target_field_count": 185,
    "target_type_name": "TargetObservationV2",
}


def test_case435_authority_complete_superset_falsifies_frozen_p3_endpoint() -> None:
    result = MODULE.analyze(ROOT)
    assert result == EXPECTED
    assert (
        result["derived_legal_domain_superset_upper_bound_octets"]
        + result["p3_unattainable_gap_octets"]
        == result["p2_structural_upper_bound_octets"]
    )
    assert (
        result["field_superset_upper_bound_sum_octets"]
        + result["field_array_syntax_octets"]
        + result["observation_fixed_nonfield_octets"]
        == result["derived_legal_domain_superset_upper_bound_octets"]
    )
    assert result["p3_equality_possible"] is False


def test_case435_checker_cli_is_deterministic_and_silent_on_stderr() -> None:
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
    assert json.loads(first.stdout) == EXPECTED


def test_case435_checker_is_independent_of_producer_verifier_and_legacy_v1() -> None:
    source = CHECKER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_roots.add(node.module.split(".", 1)[0])
    assert imported_roots == {"hashlib", "json", "pathlib", "sys"}
    forbidden_fragments = (
        "produce_raw_v8_step2_maximum_protocol_v2_candidate",
        "verify_raw_v8_step2_maximum_protocol_v2_candidate",
        "generate_raw_v8_step2_external_schema_v2_maximum_protocol_pilot",
        "raw_v8_step2_external_schema_v2_maximum_attainers",
        "validate_raw_v8_step2_external_schema_v2_rule_runtime",
        "raw_v8_step2_external_schema_v2_application_witness",
    )
    assert all(fragment not in source for fragment in forbidden_fragments)


@pytest.mark.parametrize(
    ("relative_path", "expected_sha256"),
    [
        (MODULE.SEED_RELATIVE_PATH, "0" * 64),
        (MODULE.INVENTORY_RELATIVE_PATH, "f" * 64),
        (MODULE.REGISTRY_RELATIVE_PATH, "1" * 64),
    ],
)
def test_case435_checker_rejects_any_unpinned_authority_identity(
    relative_path: str,
    expected_sha256: str,
) -> None:
    with pytest.raises(MODULE.AttainabilityCheckError, match="authority hash differs"):
        MODULE._load_pinned(ROOT, relative_path, expected_sha256)


def test_case435_falsification_is_stronger_than_a_failed_candidate_search() -> None:
    source = CHECKER.read_text(encoding="utf-8")
    assert "over-approximation" in source
    assert "upper bound on the legal P1 domain" in source
    assert "generic_attainability_claimed" in source
    assert "constructed_upper < p2_upper" in source

from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = (
    ROOT
    / "scripts/tests/generate_raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_correction_contract_v49f.py"
)
CONTRACT = (
    ROOT
    / "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_correction_contract_v49f.json"
)
CONTRACT_RAW_OCTETS = 5_436_266
CONTRACT_RAW_SHA256 = (
    "6245595b759cec6cdecd88292f105dac938f5c69ae92f90ae0365bd032180e14"
)
CONTRACT_ID = "171e9d47a7733f8448f94af5a16da4ba5258f30ee08cb4c835289a05adcb8cb9"
CASE_VECTOR_SHA256 = (
    "d0e9a0a0ae157e598da1dc8130e30bca6189966d4eadc853eb8a1a0db1f9300b"
)


@pytest.fixture(scope="module")
def generator():
    spec = importlib.util.spec_from_file_location("intrinsic_c1_generator", GENERATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def contract() -> dict:
    raw = CONTRACT.read_bytes()
    assert len(raw) == CONTRACT_RAW_OCTETS
    assert hashlib.sha256(raw).hexdigest() == CONTRACT_RAW_SHA256
    return json.loads(raw)


def test_generator_rebuild_is_byte_identical_and_cli_check_is_silent(
    generator, contract
) -> None:
    first = generator._pretty_bytes(generator.build_contract(ROOT))
    second = generator._pretty_bytes(generator.build_contract(ROOT))
    assert first == second == CONTRACT.read_bytes()
    completed = subprocess.run(
        [
            sys.executable,
            str(GENERATOR),
            "--repository-root",
            str(ROOT),
            "--check",
            str(CONTRACT),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert completed.stdout == ""
    assert completed.stderr == ""


def test_contract_semantic_identity_is_recomputed(generator, contract) -> None:
    payload = {
        name: value
        for name, value in contract.items()
        if name != "intrinsic_exactness_correction_contract_id"
    }
    assert (
        generator._semantic_id(
            contract["canonicalization_version"],
            contract["measurement_schema_version"],
            generator.CONTRACT_DOMAIN,
            payload,
        )
        == contract["intrinsic_exactness_correction_contract_id"]
        == CONTRACT_ID
    )
    assert contract["ordered_intrinsic_case_records_sha256"] == CASE_VECTOR_SHA256
    assert (
        hashlib.sha256(
            generator._canonical_bytes(contract["ordered_intrinsic_case_records"])
        ).hexdigest()
        == CASE_VECTOR_SHA256
    )


def test_all_66_cases_are_closed_ordered_and_never_promoted(contract) -> None:
    cases = contract["ordered_intrinsic_case_records"]
    assert [row["case_position"] for row in cases] == list(range(1, 67))
    statuses = Counter(row["correction_status"] for row in cases)
    assert statuses == {
        "FROZEN_P2_ENDPOINT_CONTRADICTED": 26,
        "EXACTNESS_UNRESOLVED_NOT_ACCEPTED": 40,
    }
    contradicted = [
        row["case_position"]
        for row in cases
        if row["correction_status"] == "FROZEN_P2_ENDPOINT_CONTRADICTED"
    ]
    assert contradicted == contract["correction_scope_contract"][
        "ordered_contradiction_case_positions"
    ]
    assert contract["acceptance_contract"]["all_66_exact_maxima_accepted"] is False
    assert contract["acceptance_contract"]["all_case_campaign_released"] is False


def test_complete_step_and_dependency_census_is_frozen(contract) -> None:
    assert contract["aggregate_dependency_census"] == {
        "dependency_kind_counts": {
            "ARRAY_BATCH": 91,
            "ASCII_DFA": 35,
            "CODEC_COORDINATE_SET": 160,
            "IDENTITY_CONTRACT": 37,
            "INTRINSIC_RULE": 87,
            "TEXT_LANGUAGE": 404,
            "TYPE_DESCRIPTOR": 163,
            "UNICODE_IDENTIFIER_PROFILE": 23,
            "UNICODE_SOURCE": 108,
            "UNION_BRANCH": 22,
            "VALUE_SCHEMA": 676,
        },
        "step_derivation_kind_counts": {
            "ASSOCIATIVE_HOMOGENEOUS_RUN_BATCH": 91,
            "CODEC_INTERSECTION": 160,
            "EXACT_BOOLEAN": 25,
            "NULLABLE_BRANCH": 145,
            "OBJECT_REFERENCE": 47,
            "RECORD_MEMBER_FOLD": 138,
            "SAFE_INTEGER_BAND": 247,
            "TAGGED_UNION_BRANCH": 22,
            "TEXT_BOUNDED_LANGUAGE": 183,
            "TEXT_BUILTIN_BOUNDED": 254,
            "TEXT_FINITE": 335,
        },
        "total_case_dependency_records": 1806,
        "total_step_records": 1647,
    }


def test_every_step_is_postorder_and_every_reference_resolves(contract) -> None:
    for case in contract["ordered_intrinsic_case_records"]:
        dependencies = {
            (row["dependency_kind"], row["dependency_id"])
            for row in case["ordered_authority_dependency_records"]
        }
        assert [
            row["dependency_position"]
            for row in case["ordered_authority_dependency_records"]
        ] == list(range(1, len(dependencies) + 1))
        steps = case["ordered_step_contract_records"]
        assert [row["step_position"] for row in steps] == list(
            range(1, len(steps) + 1)
        )
        assert case["root_step_position"] == len(steps)
        for step in steps:
            assert all(
                child < step["step_position"]
                for child in step["ordered_child_step_positions"]
            )
            references = [
                (row["dependency_kind"], row["dependency_id"])
                for row in step["ordered_dependency_references"]
            ]
            assert len(references) == len(set(references))
            assert set(references) <= dependencies


def test_language_dependencies_include_dfa_and_unicode_source_closure(contract) -> None:
    seen_dfa = False
    seen_unicode = False
    for case in contract["ordered_intrinsic_case_records"]:
        kinds = Counter(
            row["dependency_kind"]
            for row in case["ordered_authority_dependency_records"]
        )
        if kinds["ASCII_DFA"]:
            seen_dfa = True
            assert kinds["TEXT_LANGUAGE"] >= kinds["ASCII_DFA"]
        if kinds["UNICODE_IDENTIFIER_PROFILE"]:
            seen_unicode = True
            # The three identifier profiles intentionally bind the same six
            # pinned Unicode source records; the per-case dependency census
            # is set-like rather than occurrence-multiplying that closure.
            assert kinds["UNICODE_SOURCE"] == 6
    assert seen_dfa is True
    assert seen_unicode is True


def test_every_relaxed_predicate_class_has_a_frozen_dependency_surface(contract) -> (
    None
):
    predicate_counts = Counter()
    for case in contract["ordered_intrinsic_case_records"]:
        dependencies = {
            (row["dependency_kind"], row["dependency_id"])
            for row in case["ordered_authority_dependency_records"]
        }
        for row in case["ordered_relaxation_application_records"]:
            predicate_counts[row["predicate_kind"]] += 1
            if row["predicate_kind"] == "TEXT_LANGUAGE":
                assert ("TEXT_LANGUAGE", row["authority_predicate_id"]) in dependencies
            elif row["predicate_kind"] == "INTRINSIC_RULE":
                assert ("INTRINSIC_RULE", row["authority_predicate_id"]) in dependencies
            elif row["predicate_kind"] == "ARRAY_ORDER_AND_UNIQUENESS":
                assert ("VALUE_SCHEMA", row["authority_predicate_id"]) in dependencies
            else:
                assert row["predicate_kind"] == "PAYLOAD_DERIVED_IDENTITY_EQUALITY"
                assert any(kind == "IDENTITY_CONTRACT" for kind, _ in dependencies)
    assert predicate_counts == {
        "ARRAY_ORDER_AND_UNIQUENESS": 91,
        "INTRINSIC_RULE": 92,
        "PAYLOAD_DERIVED_IDENTITY_EQUALITY": 30,
        "TEXT_LANGUAGE": 183,
    }


def test_dual_channels_and_join_are_separate_and_fail_closed(contract) -> None:
    channels = contract["dual_channel_contract"]
    assert channels["cross_channel_code_sharing_policy"] == "FORBIDDEN"
    assert channels["pre_execution_source_freeze"] == {
        "both_channel_sources_and_output_schemas_frozen_before_execution": True,
        "channel_output_allowed_during_source_freeze": False,
        "mutual_import_read_or_generated_witness_access_policy": "FORBIDDEN",
        "required_packet": "A4-R475-V1-C2-S",
    }
    assert channels["upper_channel"]["ambient_relaxed_text_cell_allowed"] is False
    assert channels["upper_channel"]["source_must_not_read_attainer_output"] is True
    assert channels["upper_channel"]["must_prove_legal_domain_superset"] is True
    assert channels["attainer_channel"]["candidate_source_must_not_read_upper_output"]
    assert channels["attainer_channel"]["must_execute_complete_p1"] is True
    assert channels["exactness_join"]["unresolved_or_unequal_policy"] == "NO_GO"
    assert channels["exactness_join"]["problem_authority_identity_rule"] == (
        "EXACT_MATCH"
    )
    assert [
        row["packet"] for row in contract["ordered_successor_packet_records"]
    ] == [
        "A4-R475-V1-C2-S",
        "A4-R475-V1-C2-U",
        "A4-R475-V1-C2-A",
        "A4-R475-V1-C3",
        "A4-R475-V1",
    ]
    assert contract["next_bounded_packet"] == "A4-R475-V1-C2-S"


def test_predecessor_roles_are_immutable_and_resources_remain_bounded(contract) -> (
    None
):
    predecessor = contract["predecessor_authority_contract"]
    successor = contract["successor_authority_contract"]
    resources = contract["resource_contract"]
    assert predecessor["pilot_role_bytes_must_remain_exact"] is True
    assert successor["accepted_predecessor_edit_policy"] == "FORBIDDEN"
    assert successor["verifier_producer_runner_or_campaign_implemented_by_c1"] is False
    assert successor["all_case_v0_candidate_access_barrier_must_remain"] is True
    assert resources["authority_file_count"] == 8 < resources["authority_file_limit"]
    assert resources["pinned_input_octets"] < resources["pinned_input_octet_limit"]
    assert CONTRACT_RAW_OCTETS < resources["contract_raw_octet_limit"]
    assert resources["limit_tuning_from_observed_answer_allowed"] is False


def test_generator_source_has_no_role_analyzer_or_runtime_import() -> None:
    source = GENERATOR.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_modules.add(node.module)
    assert all("intrinsic_template_attainability" not in name for name in imported_modules)
    assert all("verify_raw_v8_step2" not in name for name in imported_modules)
    assert all("produce_raw_v8_step2" not in name for name in imported_modules)
    assert all("validate_raw_v8_step2" not in name for name in imported_modules)
    assert "A4_R475_V1_C1_INTRINSIC_CORRECTION_CONTRACT_GENERATOR_V1" in source


def test_authority_hash_barrier_rejects_drift(generator, monkeypatch) -> None:
    original = generator.AUTHORITIES["REGISTRY"]
    monkeypatch.setitem(
        generator.AUTHORITIES,
        "REGISTRY",
        (original[0], original[1], "0" * 64),
    )
    with pytest.raises(generator.ContractFailure, match="AUTHORITY_HASH_DRIFT"):
        generator.build_contract(ROOT)


def test_coherently_resealed_overclaims_change_contract_identity(
    generator, contract
) -> None:
    for path, value in (
        (("acceptance_contract", "all_66_exact_maxima_accepted"), True),
        (("successor_authority_contract", "accepted_predecessor_edit_policy"), "ALLOW"),
        (("dual_channel_contract", "cross_channel_code_sharing_policy"), "ALLOW"),
        (("resource_contract", "limit_tuning_from_observed_answer_allowed"), True),
    ):
        mutated = copy.deepcopy(contract)
        mutated[path[0]][path[1]] = value
        payload = {
            name: child
            for name, child in mutated.items()
            if name != "intrinsic_exactness_correction_contract_id"
        }
        resealed = generator._semantic_id(
            contract["canonicalization_version"],
            contract["measurement_schema_version"],
            generator.CONTRACT_DOMAIN,
            payload,
        )
        assert resealed != CONTRACT_ID

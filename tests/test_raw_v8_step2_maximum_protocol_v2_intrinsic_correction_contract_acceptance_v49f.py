from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REVIEWER = (
    ROOT
    / "scripts/tests/review_raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_correction_contract_v49f.py"
)
REPORT = (
    ROOT
    / "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_correction_contract_acceptance_report_v49f.json"
)
CONTRACT = (
    ROOT
    / "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_correction_contract_v49f.json"
)
REPORT_RAW_OCTETS = 1_931
REPORT_RAW_SHA256 = (
    "061d53c69b003cf528d596c1b736fbae58f23da071055fb7d8f321617f0f2303"
)
REPORT_ID = "e3cdc9ea250f3b3b296aeb02fc9a51f0aa615655ec8ee37c77a319855907dc84"


@pytest.fixture(scope="module")
def reviewer():
    spec = importlib.util.spec_from_file_location("intrinsic_c1_reviewer", REVIEWER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def report() -> dict:
    raw = REPORT.read_bytes()
    assert len(raw) == REPORT_RAW_OCTETS
    assert hashlib.sha256(raw).hexdigest() == REPORT_RAW_SHA256
    return json.loads(raw)


def test_independent_reviewer_reconstructs_exact_frozen_report(reviewer, report) -> (
    None
):
    assert reviewer.review(ROOT) == report
    assert report["acceptance_report_id"] == REPORT_ID
    assert report["decision"] == "ACCEPTED_CONTRACT_ONLY"
    assert report["acceptance_scope"] == (
        "C1_DEPENDENCY_AND_SUCCESSOR_INTERFACE_ONLY"
    )


def test_reviewer_cli_is_byte_identical_and_silent_on_stderr(report) -> None:
    completed = subprocess.run(
        [sys.executable, str(REVIEWER), str(ROOT)],
        cwd=ROOT,
        check=False,
        capture_output=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert completed.stdout == REPORT.read_bytes()
    assert completed.stderr == b""


def test_reviewer_does_not_import_generator_or_constructive_roles() -> None:
    source = REVIEWER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_modules.add(node.module)
    assert all("intrinsic_correction_contract" not in name for name in imported_modules)
    assert all("verify_raw_v8_step2" not in name for name in imported_modules)
    assert all("produce_raw_v8_step2" not in name for name in imported_modules)
    assert "_reconstruct_cases" in source
    assert "generator check replay differs" in source


def test_report_semantic_identity_is_independently_recomputed(reviewer, report) -> (
    None
):
    contract = json.loads(CONTRACT.read_bytes())
    payload = {
        name: value for name, value in report.items() if name != "acceptance_report_id"
    }
    assert (
        reviewer._semantic_id(
            contract["canonicalization_version"],
            contract["measurement_schema_version"],
            reviewer.REVIEW_DOMAIN,
            payload,
        )
        == report["acceptance_report_id"]
        == REPORT_ID
    )


def test_acceptance_closes_all_dependency_classes_without_exactness_overclaim(
    report,
) -> None:
    assert report["intrinsic_case_count"] == 66
    assert report["contradiction_case_count"] == 26
    assert report["not_falsified_nonclaim_case_count"] == 40
    assert report["total_step_records"] == 1_647
    assert report["total_case_dependency_records"] == 1_806
    assert set(report["dependency_kind_counts"]) == {
        "ARRAY_BATCH",
        "ASCII_DFA",
        "CODEC_COORDINATE_SET",
        "IDENTITY_CONTRACT",
        "INTRINSIC_RULE",
        "TEXT_LANGUAGE",
        "TYPE_DESCRIPTOR",
        "UNICODE_IDENTIFIER_PROFILE",
        "UNICODE_SOURCE",
        "UNION_BRANCH",
        "VALUE_SCHEMA",
    }
    assert report["all_66_exact_maxima_accepted"] is False
    assert report["all_case_campaign_released"] is False
    assert report["formal_stage1_state"] == "NO-GO"
    assert report["next_bounded_packet"] == "A4-R475-V1-C2-S"


def test_independent_reconstruction_rejects_step_dependency_omission(reviewer) -> (
    None
):
    contract = json.loads(CONTRACT.read_bytes())
    seed = reviewer._load_json(ROOT, "SEED")
    registry = reviewer._load_json(ROOT, "REGISTRY")
    campaign = reviewer._load_json(ROOT, "CAMPAIGN")
    mutated = copy.deepcopy(contract)
    mutated["ordered_intrinsic_case_records"][0][
        "ordered_step_contract_records"
    ][0]["ordered_dependency_references"] = []
    with pytest.raises(reviewer.ReviewFailure, match="step dependency references differ"):
        reviewer._reconstruct_cases(
            mutated,
            seed,
            registry,
            campaign,
            reviewer.EXPECTED_CONTRADICTIONS,
        )


def test_independent_reconstruction_rejects_case_promotion(reviewer) -> None:
    contract = json.loads(CONTRACT.read_bytes())
    seed = reviewer._load_json(ROOT, "SEED")
    registry = reviewer._load_json(ROOT, "REGISTRY")
    campaign = reviewer._load_json(ROOT, "CAMPAIGN")
    mutated = copy.deepcopy(contract)
    mutated["ordered_intrinsic_case_records"][2]["correction_status"] = "ACCEPTED"
    with pytest.raises(reviewer.ReviewFailure, match="case status differs"):
        reviewer._reconstruct_cases(
            mutated,
            seed,
            registry,
            campaign,
            reviewer.EXPECTED_CONTRADICTIONS,
        )


def test_reviewer_hash_barrier_rejects_contract_drift(reviewer, monkeypatch) -> None:
    relative, octets, _ = reviewer.PINNED["CONTRACT"]
    monkeypatch.setitem(
        reviewer.PINNED,
        "CONTRACT",
        (relative, octets, "0" * 64),
    )
    with pytest.raises(reviewer.ReviewFailure, match="CONTRACT hash drifted"):
        reviewer._load_json(ROOT, "CONTRACT")


def test_coherently_resealed_acceptance_overclaims_change_report_id(
    reviewer, report
) -> None:
    contract = json.loads(CONTRACT.read_bytes())
    for name, value in (
        ("all_66_exact_maxima_accepted", True),
        ("all_case_campaign_released", True),
        ("formal_stage1_state", "GO"),
        ("next_bounded_packet", "A4-R475-V1"),
    ):
        mutated = copy.deepcopy(report)
        mutated[name] = value
        payload = {
            key: child
            for key, child in mutated.items()
            if key != "acceptance_report_id"
        }
        resealed = reviewer._semantic_id(
            contract["canonicalization_version"],
            contract["measurement_schema_version"],
            reviewer.REVIEW_DOMAIN,
            payload,
        )
        assert resealed != REPORT_ID


def test_contract_preserves_pinned_predecessor_role_hashes() -> None:
    contract = json.loads(CONTRACT.read_bytes())
    authority = {
        row["authority_name"]: row
        for row in contract["ordered_authority_records"]
    }
    assert authority["PILOT_PRODUCER"]["raw_sha256"] == (
        "46c67738905488a467cbb66a6de719f4cd4804e7ac68143cb301dc1e9c46d7da"
    )
    assert authority["PILOT_VERIFIER"]["raw_sha256"] == (
        "b1bfb5778b1408c4b2dc45dd008f1089e2405b503b7eee9686820535d5631d25"
    )
    assert authority["PILOT_RUNNER"]["raw_sha256"] == (
        "5f1997b4e689a14cbae0a340fce2f320bb058eb9dd04449897ff3dfdf8de7ad7"
    )

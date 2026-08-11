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
    ROOT / "scripts/tests/review_raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_template_attainability_v49f.py"
)
REPORT = (
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_template_attainability_acceptance_report_v49f.json"
)
ANALYZER = (
    ROOT / "scripts/tests/check_raw_v8_step2_maximum_protocol_v2_"
    "intrinsic_template_attainability_v49f.py"
)
REPORT_RAW_OCTETS = 2_137
REPORT_RAW_SHA256 = "a56bd57e795f5c6cda9eed5d8c9512392bff6e0a2637c5fe69fc42508c1ff9ea"
REPORT_ID = "7dfd4073f40f1825356b32c3ed0ca7f291a4a179827882fbbedbdeb96030102e"


def _load_module():
    specification = importlib.util.spec_from_file_location(
        "intrinsic_template_attainability_acceptance_v49f", REVIEWER
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def reviewer():
    return _load_module()


@pytest.fixture(scope="module")
def report():
    raw = REPORT.read_bytes()
    assert len(raw) == REPORT_RAW_OCTETS
    assert hashlib.sha256(raw).hexdigest() == REPORT_RAW_SHA256
    return json.loads(raw)


def test_independent_review_replays_to_the_frozen_acceptance_report(
    reviewer, report
) -> None:
    assert reviewer.review(ROOT) == report
    assert report["acceptance_report_id"] == REPORT_ID
    assert report["packet"] == "A4-R475-V1-F-A"
    assert report["decision"] == ("ACCEPTED_FALSIFICATION_AUTHORITY_REPAIR_REQUIRED")
    assert report["accepted_scope"] == "FALSIFICATION_ONLY_NO_AUTHORITY_REPAIR"
    assert report["formal_stage1_state"] == "NO-GO"
    assert report["all_case_v1_acceptance_possible_under_frozen_authority"] is False
    assert report["producer_runner_or_campaign_implemented"] is False
    assert report["next_bounded_packet"] == "A4-R475-V1-C"


def test_reviewer_cli_is_byte_identical_to_report_and_silent() -> None:
    command = [sys.executable, str(REVIEWER), str(ROOT)]
    first = subprocess.run(command, cwd=ROOT, check=False, capture_output=True)
    second = subprocess.run(command, cwd=ROOT, check=False, capture_output=True)
    assert first.returncode == second.returncode == 0
    assert first.stderr == second.stderr == b""
    assert first.stdout == second.stdout == REPORT.read_bytes()


def test_reviewer_independently_closes_the_decisive_case8_contradiction(
    report,
) -> None:
    case8 = report["case8_independent_review"]
    assert case8 == {
        "case_position": 8,
        "independent_legal_attainer_octets": 928,
        "independent_legal_attainer_sha256": (
            "9156a97a005f9d2264e34054f071a6b15169f88b23be54cb59bc254362888665"
        ),
        "independently_derived_exact_legal_maximum_octets": 928,
        "intrinsic_rule_root": True,
        "p3_equality_possible": False,
        "published_p2_upper_bound_octets": 524_288,
        "standalone_identity_recomputed": True,
        "type_name": "CapacityMeasurementDispatchWindowEvidenceV1",
        "typed_runtime_accepted": True,
        "typed_runtime_sha256": (
            "47aa90d897e8dbae5e244b7c04cbd82dfe036b0292d36ef0f5552c868627ab22"
        ),
        "unattainable_gap_octets": 523_360,
    }


def test_reviewer_does_not_import_analyzer_or_any_constructive_role() -> None:
    source = REVIEWER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_modules.add(node.module)
    assert all(
        "intrinsic_template_attainability" not in name for name in imported_modules
    )
    assert all("verify_raw_v8_step2" not in name for name in imported_modules)
    assert all("produce_raw_v8_step2" not in name for name in imported_modules)
    assert "_run_analyzer" in source
    assert "first_raw == second_raw" in source
    assert "_review_case8" in source


def test_report_semantic_identity_is_independently_recomputed(reviewer, report) -> None:
    registry = json.loads((ROOT / reviewer.REGISTRY_RELATIVE_PATH).read_bytes())
    payload = {
        key: value for key, value in report.items() if key != "acceptance_report_id"
    }
    assert (
        reviewer._semantic_id(
            registry["canonicalization_version"],
            registry["measurement_schema_version"],
            reviewer.REVIEW_DOMAIN,
            payload,
        )
        == report["acceptance_report_id"]
    )


@pytest.mark.parametrize(
    ("path", "octets", "digest"),
    [
        (ANALYZER, 34_534, "0" * 64),
        (REVIEWER, 18_415, "1" * 64),
        (REPORT, REPORT_RAW_OCTETS, "f" * 64),
    ],
)
def test_review_hash_barrier_rejects_drift(
    reviewer, path: Path, octets: int, digest: str
) -> None:
    with pytest.raises(
        reviewer.IntrinsicAttainabilityReviewError, match="review hash differs"
    ):
        reviewer._load_raw(ROOT, str(path.relative_to(ROOT)), octets, digest)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("all_case_v1_acceptance_possible_under_frozen_authority",), True),
        (("producer_runner_or_campaign_implemented",), True),
        (("case8_independent_review", "p3_equality_possible"), True),
        (("case8_independent_review", "unattainable_gap_octets"), 0),
    ],
)
def test_coherently_resealed_acceptance_overclaims_change_identity(
    reviewer, report, path: tuple[str, ...], value
) -> None:
    mutated = copy.deepcopy(report)
    target = mutated
    for member in path[:-1]:
        target = target[member]
    target[path[-1]] = value
    registry = json.loads((ROOT / reviewer.REGISTRY_RELATIVE_PATH).read_bytes())
    payload = {
        key: child for key, child in mutated.items() if key != "acceptance_report_id"
    }
    resealed = reviewer._semantic_id(
        registry["canonicalization_version"],
        registry["measurement_schema_version"],
        reviewer.REVIEW_DOMAIN,
        payload,
    )
    assert resealed != REPORT_ID


def test_falsification_acceptance_does_not_modify_predecessor_roles(report) -> None:
    assert report["accepted_six_case_verifier_unchanged"] is True
    assert ANALYZER != REVIEWER
    assert REPORT != ANALYZER
    assert REPORT != REVIEWER

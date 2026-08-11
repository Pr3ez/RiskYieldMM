from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import pathlib
import subprocess
import sys
from types import ModuleType

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
GENERATOR = (
    ROOT
    / "scripts/tests/generate_raw_v8_step2_maximum_protocol_v2_all_case_campaign_contract_v49f.py"
)
REVIEWER = (
    ROOT
    / "scripts/tests/review_raw_v8_step2_maximum_protocol_v2_all_case_campaign_contract_v49f.py"
)
CONTRACT = (
    ROOT
    / "scripts/tests/raw_v8_step2_maximum_protocol_v2_all_case_campaign_contract_v49f.json"
)
REPORT = (
    ROOT
    / "scripts/tests/raw_v8_step2_maximum_protocol_v2_all_case_campaign_contract_acceptance_report_v49f.json"
)

# Frozen only after the fail-first transition and independent acceptance review.
EXPECTED_GENERATOR: tuple[int, str] | None = (
    35_282,
    "46a350c15cfffae80644e55132a4bbeb3a257b2b76261545f7ee4235835e7bd9",
)
EXPECTED_REVIEWER: tuple[int, str] | None = (
    25_668,
    "9c5c30d7d00da2ca73d1e8f98edbc089b80e366b39bedcb426752fb4d0a86beb",
)
EXPECTED_CONTRACT: tuple[int, str] | None = (
    382_710,
    "3ca4ff4d6e581895b813043e7fdeed24c33cf2c828e362ac81de1725e95a84bb",
)
EXPECTED_REPORT: tuple[int, str] | None = (
    3_607,
    "c6703ae1a6b8262139bba63d5959054b999c43e2ffc7fef0fd854670e303384c",
)
EXPECTED_CONTRACT_ID: str | None = (
    "9be94bf6b53b612d62ac26bc74133f25c1101a0962987a855e65cdcd06418583"
)
EXPECTED_REPORT_ID: str | None = (
    "16035e8342cbe5713aa9d619638da13b34d5e7e56707433e66dfb3aa1078f1cd"
)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _load(path: pathlib.Path) -> dict[str, object]:
    value = json.loads(path.read_bytes())
    assert type(value) is dict
    return value


def _load_reviewer() -> ModuleType:
    _require_packet()
    specification = importlib.util.spec_from_file_location(
        "a4_r475_t_reviewer", REVIEWER
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def _require_packet() -> None:
    missing = [
        path
        for path in (GENERATOR, REVIEWER, CONTRACT, REPORT)
        if not path.is_file()
    ]
    if missing:
        pytest.skip(f"A4-R475-T packet is incomplete: {missing}")


def test_all_case_campaign_contract_packet_exists() -> None:
    assert GENERATOR.is_file(), "A4-R475-T contract generator is missing"
    assert REVIEWER.is_file(), "A4-R475-T independent reviewer is missing"
    assert CONTRACT.is_file(), "A4-R475-T contract artifact is missing"
    assert REPORT.is_file(), "A4-R475-T acceptance report is missing"


def test_frozen_artifact_identities_and_semantic_ids_are_exact() -> None:
    _require_packet()
    expected = {
        GENERATOR: EXPECTED_GENERATOR,
        REVIEWER: EXPECTED_REVIEWER,
        CONTRACT: EXPECTED_CONTRACT,
        REPORT: EXPECTED_REPORT,
    }
    assert all(value is not None for value in expected.values())
    for path, identity in expected.items():
        assert identity is not None
        raw = path.read_bytes()
        assert (len(raw), _sha256(raw)) == identity
    contract = _load(CONTRACT)
    report = _load(REPORT)
    assert contract["all_case_campaign_contract_id"] == EXPECTED_CONTRACT_ID
    assert report["all_case_campaign_contract_acceptance_report_id"] == (
        EXPECTED_REPORT_ID
    )


def test_generator_check_mode_reproduces_contract() -> None:
    _require_packet()
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            str(GENERATOR),
            "--repository-root",
            str(ROOT),
            "--check",
            str(CONTRACT),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr.decode(errors="replace")
    assert completed.stdout == completed.stderr == b""


def test_independent_reviewer_check_mode_reproduces_acceptance_report() -> None:
    _require_packet()
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            str(REVIEWER),
            "--repository-root",
            str(ROOT),
            "--contract",
            str(CONTRACT),
            "--check-report",
            str(REPORT),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr.decode(errors="replace")
    assert completed.stdout == completed.stderr == b""


def test_contract_closes_the_complete_case_and_resource_ledgers() -> None:
    _require_packet()
    contract = _load(CONTRACT)
    universe = contract["case_universe_contract"]
    assert type(universe) is dict
    rows = universe["ordered_case_execution_records"]
    assert type(rows) is list and len(rows) == 475
    assert [row["case_position"] for row in rows] == list(range(1, 476))
    assert sum(row["case_kind"] == "MAXIMUM_PUBLICATION_ROW" for row in rows) == 474
    assert sum(
        row["case_kind"] == "LOCAL_SHUTDOWN_UNREPRESENTABLE_MINIMALITY"
        for row in rows
    ) == 1
    assert universe["execution_family_counts"] == {
        "CORRECTED_APPLICATION_EXACT_PROFILE": 1,
        "GENERIC_PROFILE_ATTAINMENT": 406,
        "INTRINSIC_TEMPLATE_ATTAINMENT": 66,
        "LOCAL_MINIMALITY": 1,
        "SIGNED_ANALYTIC_EXACT_PROFILE": 1,
    }
    resources = contract["resource_contract"]
    assert type(resources) is dict
    f2 = resources["ordered_f2_limit_records"]
    assert type(f2) is list and len(f2) == 18
    assert [row["metric_position"] for row in f2] == list(range(1, 19))
    assert [row["required_full_run"] for row in f2] == [
        475,
        29_189_597,
        66_119,
        417_528,
        170_915_620,
        1_735,
        66_119,
        44_461_267,
        329_067_149,
        367_039_374,
        619_175_993,
        4_160,
        4_198_492,
        46_268,
        17,
        569,
        54_297,
        15_585_644,
    ]
    assert all(row["required_full_run"] <= row["f2_full_run"] for row in f2)


def test_resume_and_publication_contract_is_fail_closed() -> None:
    _require_packet()
    contract = _load(CONTRACT)
    scheduler = contract["scheduler_and_checkpoint_contract"]
    publication = contract["publication_contract"]
    assert scheduler["maximum_concurrent_case_attempts"] == 1
    assert scheduler["completion_order_rule"] == "STRICT_CASE_POSITION_1_THROUGH_475"
    assert scheduler["checkpoint_reuse_rule"] == (
        "REVALIDATE_COMPLETE_CASE_CLOSURE_AUTHORITIES_ROLE_IDENTITIES_AND_CASE_COMMIT_BEFORE_REUSE"
    )
    assert scheduler["corrupt_or_ambiguous_checkpoint_policy"] == (
        "REJECT_WITHOUT_REPAIR_DELETE_OR_SKIP"
    )
    assert publication["accepted_root_rule"] == (
        "RENAME_COMPLETE_PRIVATE_WORK_ROOT_TO_ABSENT_ACCEPTED_ROOT_ONCE"
    )
    assert publication["partial_acceptance_policy"] == "FORBIDDEN"
    assert publication["campaign_manifest_write_order"] == (
        "AFTER_475_CASE_COMMITS_BEFORE_FINAL_ROOT_RENAME"
    )


def test_accepted_six_case_binaries_are_immutable_regression_authorities_only() -> None:
    _require_packet()
    contract = _load(CONTRACT)
    predecessor = contract["predecessor_regression_authority_contract"]
    assert predecessor["surface"] == "EXACTLY_SIX_CASES"
    assert predecessor["ordered_supported_case_positions"] == [5, 24, 54, 69, 435, 475]
    assert predecessor["in_place_extension_policy"] == "FORBIDDEN"
    assert predecessor["all_case_readiness_claimed"] is False
    roles = contract["versioned_role_contract"]["ordered_role_records"]
    assert len(roles) == 3
    assert len({row["repository_relative_path"] for row in roles}) == 3
    assert all(row["implementation_state"] == "ABSENT_FAIL_FIRST" for row in roles)


def test_resealed_case_resource_resume_and_publication_mutations_are_rejected() -> None:
    reviewer = _load_reviewer()
    original = _load(CONTRACT)

    def reseal(value: dict[str, object]) -> None:
        payload = {
            name: child
            for name, child in value.items()
            if name != "all_case_campaign_contract_id"
        }
        value["all_case_campaign_contract_id"] = reviewer._semantic_id(
            reviewer.CONTRACT_DOMAIN, payload
        )

    mutations = []

    case_mutation = copy.deepcopy(original)
    case_row = case_mutation["case_universe_contract"][
        "ordered_case_execution_records"
    ][0]
    case_row["effective_logical_count_plan_id"] = "0" * 64
    case_payload = {
        name: child for name, child in case_row.items() if name != "case_execution_record_id"
    }
    case_row["case_execution_record_id"] = reviewer._semantic_id(
        reviewer.CASE_RECORD_DOMAIN, case_payload
    )
    rows = case_mutation["case_universe_contract"]["ordered_case_execution_records"]
    case_mutation["case_universe_contract"][
        "ordered_case_execution_records_sha256"
    ] = reviewer._sha256(reviewer._canonical_bytes(rows))
    case_mutation["case_universe_contract"]["case_execution_ledger_id"] = (
        reviewer._semantic_id(
            reviewer.CASE_LEDGER_DOMAIN,
            {"case_count": 475, "ordered_case_execution_records": rows},
        )
    )
    mutations.append(case_mutation)

    resource_mutation = copy.deepcopy(original)
    resource_mutation["resource_contract"]["ordered_f2_limit_records"][0][
        "required_full_run"
    ] = 474
    mutations.append(resource_mutation)

    resume_mutation = copy.deepcopy(original)
    resume_mutation["scheduler_and_checkpoint_contract"][
        "maximum_concurrent_case_attempts"
    ] = 2
    mutations.append(resume_mutation)

    publication_mutation = copy.deepcopy(original)
    publication_mutation["publication_contract"]["partial_acceptance_policy"] = (
        "ALLOWED"
    )
    mutations.append(publication_mutation)

    for hostile in mutations:
        reseal(hostile)
        with pytest.raises(reviewer.ReviewFailure):
            reviewer._validate_contract(ROOT, hostile)


def test_current_six_case_producer_rejects_a_nonpilot_case_without_output(
    tmp_path: pathlib.Path,
) -> None:
    producer = (
        ROOT / "scripts/tests/produce_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py"
    )
    boundary = (
        ROOT
        / "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
        "case435_context_pack_boundary_delta_v49f.json"
    )
    output = tmp_path / "must-not-exist"
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            str(producer),
            "--repository-root",
            str(ROOT),
            "--boundary",
            str(boundary),
            "--case-position",
            "1",
            "--output-root",
            str(output),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        timeout=30,
    )
    assert completed.returncode == 2
    assert completed.stdout == b""
    assert b"CASE_POSITION_NOT_CANONICAL_PILOT_MEMBER" in completed.stderr
    assert not output.exists()

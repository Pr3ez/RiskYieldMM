from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import pathlib
import subprocess
import sys
from typing import Any

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MIGRATOR_PATH = (
    ROOT
    / "scripts/tests/migrate_raw_v8_step2_maximum_protocol_v2_case435_authorities_v49f.py"
)
CHECKER_PATH = (
    ROOT
    / "scripts/tests/check_raw_v8_step2_maximum_protocol_v2_case435_authority_transition_v49f.py"
)


def _load(path: pathlib.Path, name: str):
    specification = importlib.util.spec_from_file_location(name, path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


migrator = _load(MIGRATOR_PATH, "case435_authority_migrator_v49f")
checker = _load(CHECKER_PATH, "case435_authority_checker_v49f")

EXPECTED_OUTPUT_PINS = {
    checker.SEED_DELTA_PATH: (
        22_976,
        "5ce6b2156389ff0aecad7272a564308662a6ec3a77c4b94bfcae7ce32739c3da",
        "successor_seed_catalog_id",
        "7fad47e881624d0f39809e72ce2d3d3fd81fb8c85f854fe8332faf543cd1120b",
    ),
    checker.MANIFEST_DELTA_PATH: (
        2_192,
        "daa55d18aa8adfcef9b8a6ea2c6fa734f7922888a902eb863c6307c0fc13bacf",
        "successor_manifest_id",
        "6aed1139c158f8685bcb226697a2efe57af3c42f57831173bd7b3ea169025d9c",
    ),
    checker.BOUNDARY_DELTA_PATH: (
        4_806,
        "208d0cd50eb0bbfe206148dbf58df862f8adc857e382623e91e4e10d942c936c",
        "successor_constructive_boundary_id",
        "7d4c06f56cd3cacd97cc4ff655e31f380fe9231c6c7c1374caee499186e1f73d",
    ),
    checker.TARGET_DELTA_PATH: (
        4_768,
        "394da62c1b5146990b2769feaefa1c06c75387ab7a38ec410ec7e327699b340b",
        "successor_six_case_target_id",
        "a000285d1bedd88306786ea33e1be9cc7d2a8459fe75b20c045f7174d52cc072",
    ),
}


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture(scope="module")
def authorities():
    raws, objects = checker._load_successors(ROOT)
    return raws, objects


@pytest.fixture(scope="module")
def report():
    return checker.verify(ROOT)


def test_successor_authorities_are_physically_and_semantically_frozen(
    authorities,
) -> None:
    raws, objects = authorities
    for path, (octets, digest, id_name, identity) in EXPECTED_OUTPUT_PINS.items():
        assert len(raws[path]) == octets
        assert _sha256(raws[path]) == digest
        assert objects[path][id_name] == identity


def test_independent_checker_accepts_exact_single_case_transition(report) -> None:
    assert report["verification_status"] == "ACCEPTED"
    assert report["authorized_case_change_count"] == 1
    assert report["authorized_profile_program_change_count"] == 1
    assert report["authorized_logical_plan_change_count"] == 1
    assert report["authorized_case_plan_binding_change_count"] == 1
    assert report["unaffected_case_count"] == 474
    assert report["unaffected_profile_program_count"] == 407
    assert report["case435_exact_maximum_octets"] == 257_887
    assert report["f2_resource_requalification_state"] == "REQUIRED_IN_A4_P6_V"
    assert report["verifier_expansion_state"] == (
        "RELEASED_FOR_A4_P6_V_IMPLEMENTATION"
    )
    assert report["next_subgate"] == "A4-P6-V"


def test_generator_reconstructs_exact_published_bytes(authorities) -> None:
    raws, _objects = authorities
    generated = migrator.build_authorities(ROOT)
    assert set(generated) == set(raws)
    for path, value in generated.items():
        assert migrator._pretty_bytes(value) == raws[path]


def test_generator_check_and_checker_cli_are_silent_or_canonical(report) -> None:
    checked = subprocess.run(
        [sys.executable, str(MIGRATOR_PATH), str(ROOT), "--check"],
        cwd=ROOT,
        check=False,
        capture_output=True,
    )
    assert checked.returncode == 0
    assert checked.stdout == b""
    assert checked.stderr == b""
    first = subprocess.run(
        [sys.executable, str(CHECKER_PATH), str(ROOT)],
        cwd=ROOT,
        check=False,
        capture_output=True,
    )
    second = subprocess.run(
        [sys.executable, str(CHECKER_PATH), str(ROOT)],
        cwd=ROOT,
        check=False,
        capture_output=True,
    )
    assert first.returncode == second.returncode == 0
    assert first.stderr == second.stderr == b""
    assert first.stdout == second.stdout == checker._canonical_bytes(report) + b"\n"


def test_case435_effective_program_uses_exact_cell_without_relaxation(
    authorities,
) -> None:
    _raws, objects = authorities
    seed = objects[checker.SEED_DELTA_PATH]
    program = seed["successor_case435_profile_conditioning_program"]
    plan = seed["successor_case435_logical_count_plan"]
    p2 = program["conditioning_transfer_program"]["p2_upper_bound_program"]
    exact_cell = p2["ordered_instruction_records"][0]["parameters"]["exact_cell"]
    assert program["conditioning_strategy"] == (
        "APPLICATION_AWARE_EXACT_UPPER_ATTAINMENT_JOIN_V1"
    )
    assert p2["upper_bound_source"] == "ACCEPTED_CASE_EXACTNESS_JOIN_V1"
    assert p2["root_instruction_position"] == 3
    assert p2["safe_relaxation_applied"] is False
    assert p2["cross_application_deletion_applied"] is False
    assert exact_cell["cell_kind"] == "EXACT_ATTAINED_MAXIMUM"
    assert (
        exact_cell["certified_lower_bound_octets"]
        == exact_cell["certified_upper_bound_octets"]
        == exact_cell["attaining_witness_canonical_octets"]
        == 257_887
    )
    assert exact_cell["proof_source_id"] == checker.EXACTNESS_JOIN_CERTIFICATE_ID
    assert plan["upper_bound_mode"] == "EXACT_LEGAL_DOMAIN"
    assert plan["ordered_safe_relaxation_rule_ids"] == []
    assert plan["scope_summary"]["p2_cross_application_deletion_policy_id"] is None


def test_transition_keeps_predecessor_authorities_byte_exact() -> None:
    for path, (octets, digest, _identity) in checker.PREDECESSOR_PINS.items():
        raw = (ROOT / path).read_bytes()
        assert len(raw) == octets
        assert _sha256(raw) == digest


def test_manifest_does_not_relabel_predecessor_preflight_as_successor_evidence(
    authorities,
) -> None:
    _raws, objects = authorities
    manifest = objects[checker.MANIFEST_DELTA_PATH]
    evidence = manifest["predecessor_evidence_scope"]
    f2 = manifest["f2_limit_authority"]
    assert evidence["comparison_applies_to_predecessor_seed_only"] is True
    assert evidence["comparison_reuse_as_successor_preflight_forbidden"] is True
    assert f2["limits_are_byte_exact_predecessor_ceilings"] is True
    assert f2["limits_may_not_be_raised_or_repaired_by_case435"] is True
    assert f2["case435_successor_resource_requalification"] == (
        "REQUIRED_DURING_A4_P6_V_BEFORE_CASE_ACCEPTANCE"
    )


def test_target_closes_transitive_physical_and_semantic_chain(authorities) -> None:
    raws, objects = authorities
    seed = objects[checker.SEED_DELTA_PATH]
    manifest = objects[checker.MANIFEST_DELTA_PATH]
    boundary = objects[checker.BOUNDARY_DELTA_PATH]
    target = objects[checker.TARGET_DELTA_PATH]
    assert manifest["successor_seed_delta_authority"] == checker._authority(
        checker.SEED_DELTA_PATH,
        raws[checker.SEED_DELTA_PATH],
        "successor_seed_catalog_id",
        seed["successor_seed_catalog_id"],
    )
    assert boundary["successor_manifest_delta_authority"] == checker._authority(
        checker.MANIFEST_DELTA_PATH,
        raws[checker.MANIFEST_DELTA_PATH],
        "successor_manifest_id",
        manifest["successor_manifest_id"],
    )
    assert target["successor_boundary_delta_authority"] == checker._authority(
        checker.BOUNDARY_DELTA_PATH,
        raws[checker.BOUNDARY_DELTA_PATH],
        "successor_constructive_boundary_id",
        boundary["successor_constructive_boundary_id"],
    )


def test_migrator_and_checker_are_separate_standard_library_programs() -> None:
    assert MIGRATOR_PATH != CHECKER_PATH
    allowed = {
        "__future__",
        "argparse",
        "copy",
        "hashlib",
        "json",
        "os",
        "pathlib",
        "secrets",
        "sys",
        "typing",
    }
    for path in (MIGRATOR_PATH, CHECKER_PATH):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        roots = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                roots.add(node.module.split(".")[0])
        assert roots <= allowed
        assert not ({"riskyieldmm", "scripts", "tests"} & roots)


def _reseal_chain(objects: dict[str, dict[str, Any]]):
    seed = objects[checker.SEED_DELTA_PATH]
    seed["successor_seed_catalog_id"] = checker._domain_id(
        checker.SEED_DELTA_DOMAIN,
        {key: value for key, value in seed.items() if key != "successor_seed_catalog_id"},
    )
    seed_raw = checker._pretty_bytes(seed)

    manifest = objects[checker.MANIFEST_DELTA_PATH]
    manifest["successor_seed_delta_authority"] = checker._authority(
        checker.SEED_DELTA_PATH,
        seed_raw,
        "successor_seed_catalog_id",
        seed["successor_seed_catalog_id"],
    )
    manifest["successor_manifest_id"] = checker._domain_id(
        checker.MANIFEST_DELTA_DOMAIN,
        {key: value for key, value in manifest.items() if key != "successor_manifest_id"},
    )
    manifest_raw = checker._pretty_bytes(manifest)

    boundary = objects[checker.BOUNDARY_DELTA_PATH]
    boundary["successor_seed_delta_authority"] = checker._authority(
        checker.SEED_DELTA_PATH,
        seed_raw,
        "successor_seed_catalog_id",
        seed["successor_seed_catalog_id"],
    )
    boundary["successor_manifest_delta_authority"] = checker._authority(
        checker.MANIFEST_DELTA_PATH,
        manifest_raw,
        "successor_manifest_id",
        manifest["successor_manifest_id"],
    )
    f2 = boundary["successor_f2_resource_limit_catalog"]
    f2["successor_seed_catalog_id"] = seed["successor_seed_catalog_id"]
    f2["successor_manifest_id"] = manifest["successor_manifest_id"]
    f2_payload = {
        key: value
        for key, value in f2.items()
        if key
        not in {
            "f2_resource_limit_catalog_id",
            "limit_records_source",
            "resource_requalification_rule",
        }
    }
    f2["f2_resource_limit_catalog_id"] = checker._domain_id(
        checker.F2_CATALOG_DOMAIN, f2_payload
    )
    boundary["successor_constructive_boundary_id"] = checker._domain_id(
        checker.BOUNDARY_DELTA_DOMAIN,
        {
            key: value
            for key, value in boundary.items()
            if key != "successor_constructive_boundary_id"
        },
    )
    boundary_raw = checker._pretty_bytes(boundary)

    target = objects[checker.TARGET_DELTA_PATH]
    target["successor_seed_delta_authority"] = checker._authority(
        checker.SEED_DELTA_PATH,
        seed_raw,
        "successor_seed_catalog_id",
        seed["successor_seed_catalog_id"],
    )
    target["successor_manifest_delta_authority"] = checker._authority(
        checker.MANIFEST_DELTA_PATH,
        manifest_raw,
        "successor_manifest_id",
        manifest["successor_manifest_id"],
    )
    target["successor_boundary_delta_authority"] = checker._authority(
        checker.BOUNDARY_DELTA_PATH,
        boundary_raw,
        "successor_constructive_boundary_id",
        boundary["successor_constructive_boundary_id"],
    )
    target["successor_six_case_target_id"] = checker._domain_id(
        checker.TARGET_DELTA_DOMAIN,
        {
            key: value
            for key, value in target.items()
            if key != "successor_six_case_target_id"
        },
    )
    return {
        checker.SEED_DELTA_PATH: seed_raw,
        checker.MANIFEST_DELTA_PATH: manifest_raw,
        checker.BOUNDARY_DELTA_PATH: boundary_raw,
        checker.TARGET_DELTA_PATH: checker._pretty_bytes(target),
    }


def _mutate_extra_override(objects: dict[str, dict[str, Any]]) -> None:
    contract = objects[checker.SEED_DELTA_PATH]["resolution_contract"]
    contract["ordered_override_case_positions"] = [434, 435]
    contract["override_cardinality"] = 2
    contract["base_fallback_case_count"] = 473


def _mutate_old_plan_mode(objects: dict[str, dict[str, Any]]) -> None:
    plan = objects[checker.SEED_DELTA_PATH]["successor_case435_logical_count_plan"]
    plan["upper_bound_mode"] = "LEGAL_DOMAIN_SUPERSET_WITH_LEGAL_ATTAINMENT"
    plan["logical_count_plan_id"] = checker._domain_id(
        checker.PLAN_DOMAIN,
        {key: value for key, value in plan.items() if key != "logical_count_plan_id"},
    )


def _mutate_cell_endpoint(objects: dict[str, dict[str, Any]]) -> None:
    program = objects[checker.SEED_DELTA_PATH][
        "successor_case435_profile_conditioning_program"
    ]
    parameters = program["conditioning_transfer_program"]["p2_upper_bound_program"][
        "ordered_instruction_records"
    ][0]["parameters"]
    parameters["exact_maximum_octets"] = 257_888
    cell = parameters["exact_cell"]
    cell["certified_lower_bound_octets"] = 257_888
    cell["certified_upper_bound_octets"] = 257_888
    cell["attaining_witness_canonical_octets"] = 257_888
    program["profile_conditioning_program_id"] = checker._domain_id(
        checker.PROGRAM_DOMAIN,
        {
            key: value
            for key, value in program.items()
            if key != "profile_conditioning_program_id"
        },
    )


def _mutate_structural_source(objects: dict[str, dict[str, Any]]) -> None:
    program = objects[checker.SEED_DELTA_PATH][
        "successor_case435_profile_conditioning_program"
    ]
    program["conditioning_transfer_program"]["p2_upper_bound_program"][
        "upper_bound_source"
    ] = "STRUCTURAL_TEMPLATE_SUPERSET_V1"
    program["profile_conditioning_program_id"] = checker._domain_id(
        checker.PROGRAM_DOMAIN,
        {
            key: value
            for key, value in program.items()
            if key != "profile_conditioning_program_id"
        },
    )


def _mutate_safe_relaxation(objects: dict[str, dict[str, Any]]) -> None:
    program = objects[checker.SEED_DELTA_PATH][
        "successor_case435_profile_conditioning_program"
    ]
    program["conditioning_transfer_program"]["p2_upper_bound_program"][
        "safe_relaxation_applied"
    ] = True
    program["profile_conditioning_program_id"] = checker._domain_id(
        checker.PROGRAM_DOMAIN,
        {
            key: value
            for key, value in program.items()
            if key != "profile_conditioning_program_id"
        },
    )


def _mutate_unrelated_digest(objects: dict[str, dict[str, Any]]) -> None:
    objects[checker.SEED_DELTA_PATH]["no_unrelated_drift_proof"][
        "unaffected_case_plan_records_sha256"
    ] = "0" * 64


def _mutate_preflight_scope(objects: dict[str, dict[str, Any]]) -> None:
    objects[checker.MANIFEST_DELTA_PATH]["predecessor_evidence_scope"][
        "comparison_reuse_as_successor_preflight_forbidden"
    ] = False


def _mutate_f2_digest(objects: dict[str, dict[str, Any]]) -> None:
    objects[checker.MANIFEST_DELTA_PATH]["f2_limit_authority"][
        "ordered_f2_limit_records_sha256"
    ] = "0" * 64


def _mutate_producer_release(objects: dict[str, dict[str, Any]]) -> None:
    objects[checker.BOUNDARY_DELTA_PATH]["producer_expansion_state"] = "RELEASED"


def _mutate_target_next(objects: dict[str, dict[str, Any]]) -> None:
    objects[checker.TARGET_DELTA_PATH]["qualification_contract"][
        "next_subgate"
    ] = "A4-P6-P"


def _mutate_extra_target_case(objects: dict[str, dict[str, Any]]) -> None:
    rows = objects[checker.TARGET_DELTA_PATH]["ordered_pilot_case_records"]
    extra = copy.deepcopy(rows[-1])
    extra["pilot_position"] = 7
    rows.append(extra)


@pytest.mark.parametrize(
    "mutation",
    [
        _mutate_extra_override,
        _mutate_old_plan_mode,
        _mutate_cell_endpoint,
        _mutate_structural_source,
        _mutate_safe_relaxation,
        _mutate_unrelated_digest,
        _mutate_preflight_scope,
        _mutate_f2_digest,
        _mutate_producer_release,
        _mutate_target_next,
        _mutate_extra_target_case,
    ],
    ids=lambda mutation: mutation.__name__,
)
def test_independent_checker_rejects_hostile_resealed_mutations(
    authorities, mutation
) -> None:
    _raws, accepted_objects = authorities
    objects = copy.deepcopy(accepted_objects)
    mutation(objects)
    successor_raws = _reseal_chain(objects)
    with pytest.raises(checker.AuthorityTransitionReject):
        checker.validate_objects(
            ROOT,
            successor_raws=successor_raws,
            successor_objects=objects,
        )


@pytest.mark.parametrize(
    "raw",
    [
        b'{"a":1,"a":2}',
        b'{"a":1.5}',
        b'{"a":NaN}',
        b'\xef\xbb\xbf{"a":1}',
        b"\xff",
    ],
)
def test_independent_checker_rejects_non_strict_json(raw: bytes) -> None:
    with pytest.raises(checker.AuthorityTransitionReject):
        checker._strict_json(raw, label="hostile")


def test_target_keeps_all_outcomes_unclaimed_until_future_gates(authorities) -> None:
    _raws, objects = authorities
    target = objects[checker.TARGET_DELTA_PATH]
    qualification = target["qualification_contract"]
    assert qualification["target_status"] == (
        "CORRECTED_AUTHORITY_FROZEN_IMPLEMENTATIONS_NOT_YET_QUALIFIED"
    )
    assert qualification["verifier_expansion_state"] == "NEXT"
    assert qualification["producer_expansion_state"] == "WAITING"
    assert qualification["runner_state"] == "WAITING"
    assert qualification["no_case_result_or_profitability_claimed"] is True

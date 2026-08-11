from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import pathlib
import subprocess
import sys
from collections.abc import Callable
from typing import Any

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
GENERATOR_PATH = (
    ROOT
    / "scripts/tests/generate_raw_v8_step2_maximum_protocol_v2_"
    "case435_context_pack_boundary_v49f.py"
)
CHECKER_PATH = (
    ROOT
    / "scripts/tests/check_raw_v8_step2_maximum_protocol_v2_"
    "case435_context_pack_boundary_v49f.py"
)


def _load(path: pathlib.Path, name: str):
    specification = importlib.util.spec_from_file_location(name, path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


generator = _load(GENERATOR_PATH, "case435_context_pack_boundary_generator_v49f")
checker = _load(CHECKER_PATH, "case435_context_pack_boundary_checker_v49f")


@pytest.fixture(scope="module")
def correction() -> dict[str, Any]:
    return checker.verify(ROOT)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read_correction() -> dict[str, Any]:
    return checker.json.loads((ROOT / checker.CORRECTION_PATH).read_bytes())


def _reseal(value: dict[str, Any]) -> bytes:
    payload = {
        name: child
        for name, child in value.items()
        if name != "case435_context_pack_boundary_delta_id"
    }
    value["case435_context_pack_boundary_delta_id"] = checker._domain_id(
        checker.CORRECTION_DOMAIN, payload
    )
    return checker._pretty_bytes(value)


def _write_fixture_root(
    temporary: pathlib.Path, correction_value: dict[str, Any]
) -> bytes:
    for relative in (checker.SEED_PATH, checker.SUCCESSOR_BOUNDARY_PATH):
        target = temporary / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / relative).read_bytes())
    raw = _reseal(correction_value)
    target = temporary / checker.CORRECTION_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    return raw


def test_independent_checker_accepts_only_the_closed_transport_correction(
    correction: dict[str, Any],
) -> None:
    assert correction == {
        "verification_status": "ACCEPTED",
        "case_position": 435,
        "case435_context_pack_boundary_delta_id": checker.CORRECTION_PIN[2],
        "correction_raw_octets": checker.CORRECTION_PIN[0],
        "correction_raw_sha256": checker.CORRECTION_PIN[1],
        "flat_minimum_input_file_count": 106,
        "packed_minimum_input_file_count": 41,
        "packed_input_file_headroom": 23,
        "logical_context_object_count": 67,
        "required_context_pack_count": 1,
        "individual_pack_strict_upper_octets": 16_777_216,
        "unchanged_case435_exact_maximum_octets": 257_887,
        "next_subgate": "A4-P6-V3",
    }


def test_generator_reconstructs_the_exact_published_authority() -> None:
    expected = (ROOT / generator.OUTPUT_PATH).read_bytes()
    assert generator._pretty_bytes(generator.build(ROOT)) == expected
    assert len(expected) == checker.CORRECTION_PIN[0]
    assert _sha256(expected) == checker.CORRECTION_PIN[1]
    assert checker.json.loads(expected)[
        "case435_context_pack_boundary_delta_id"
    ] == checker.CORRECTION_PIN[2]


def test_generator_check_and_checker_cli_are_deterministic() -> None:
    generated = subprocess.run(
        [sys.executable, str(GENERATOR_PATH), str(ROOT), "--check"],
        cwd=ROOT,
        check=False,
        capture_output=True,
    )
    assert generated.returncode == 0
    assert generated.stdout == generated.stderr == b""
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
    assert first.stdout == second.stdout


def test_contradiction_is_derived_from_immutable_f0_and_full_context() -> None:
    seed = checker.json.loads((ROOT / checker.SEED_PATH).read_bytes())
    successor = checker.json.loads(
        (ROOT / checker.SUCCESSOR_BOUNDARY_PATH).read_bytes()
    )
    correction = _read_correction()
    ceilings = {
        row["resource_name"]: row["ceiling_value"]
        for row in seed["f0_seed_ceiling_catalog"]["ordered_platform_ceiling_records"]
    }
    proof = correction["f0_contradiction_proof"]
    assert ceilings["INPUT_FILE_COUNT"] == proof["input_file_count_ceiling"] == 64
    assert successor["case435_pilot_record_override"]["coverage_tag"] == (
        "MAX64_ROOT_FULL67_CONTEXT_137_APPLICATIONS_EXACT_257887"
    )
    assert proof["logical_context_object_count"] == 1 + (67 - 1) == 67
    assert proof["minimum_flat_input_file_count"] == 38 + 1 + 67 == 106
    assert proof["minimum_flat_input_file_count"] > ceilings["INPUT_FILE_COUNT"]


def test_correction_changes_transport_only_and_does_not_raise_a_limit() -> None:
    correction = _read_correction()
    unchanged = correction["unchanged_effective_authorities"]
    nondrift = correction["scope_and_non_drift_contract"]
    filesystem = correction["filesystem_and_publication_contract"]
    assert unchanged["case435_exact_maximum_octets"] == 257_887
    assert unchanged["case435_logical_count_plan_id"] == (
        "343259e38b6050fac5905fdc7ed6dca6d345d32c07b8370085bdf865793e7ad8"
    )
    assert unchanged["f2_resource_limit_catalog_id"] == (
        "5b2171f64c082ddaa5ecbeb19e2e2f5b952c07336a097364f23fd1658c3d944f"
    )
    assert nondrift["authorized_change"] == (
        "CASE435_CANDIDATE_CONTEXT_PHYSICAL_TRANSPORT_ONLY"
    )
    assert nondrift["f0_or_f2_limit_increase_forbidden"] is True
    assert nondrift["c2_certificate_or_stored_witness_as_verifier_input_forbidden"]
    assert filesystem["verified_output_rule"] == (
        "UNPACK_TO_INHERITED_COMPACT_CONTEXT_OBJECT_FILES_AND_INHERITED_"
        "LOGICAL_RECEIPT_ENTRIES"
    )


Mutation = Callable[[dict[str, Any]], None]


def _mutate_pack_limit(value: dict[str, Any]) -> None:
    value["context_pack_contract"]["individual_pack_strict_upper_octets"] += 1


def _mutate_f2(value: dict[str, Any]) -> None:
    value["unchanged_effective_authorities"]["f2_resource_limit_catalog_id"] = "0" * 64


def _mutate_flat_count(value: dict[str, Any]) -> None:
    value["f0_contradiction_proof"]["minimum_flat_input_file_count"] = 64


def _mutate_context_count(value: dict[str, Any]) -> None:
    value["f0_contradiction_proof"]["logical_context_object_count"] = 66


def _mutate_pack_count(value: dict[str, Any]) -> None:
    value["context_pack_contract"]["required_pack_count_for_case435"] = 2


def _mutate_candidate_members(value: dict[str, Any]) -> None:
    value["packed_context_candidate_contract"]["ordered_payload_member_names"].pop()


def _mutate_allow_c2(value: dict[str, Any]) -> None:
    value["scope_and_non_drift_contract"][
        "c2_certificate_or_stored_witness_as_verifier_input_forbidden"
    ] = False


def _mutate_allow_flat(value: dict[str, Any]) -> None:
    value["scope_and_non_drift_contract"][
        "old_flat_case435_transport_acceptance_policy"
    ] = "ACCEPT"


def _mutate_output_rule(value: dict[str, Any]) -> None:
    value["filesystem_and_publication_contract"]["verified_output_rule"] = (
        "PUBLISH_PACK_WITHOUT_LOGICAL_OBJECTS"
    )


def _mutate_pack_path(value: dict[str, Any]) -> None:
    value["context_pack_contract"]["repository_relative_path_rule"] = "ANY_PATH"


def _mutate_extra(value: dict[str, Any]) -> None:
    value["producer_claim"] = 257_887


@pytest.mark.parametrize(
    "mutation",
    [
        _mutate_pack_limit,
        _mutate_f2,
        _mutate_flat_count,
        _mutate_context_count,
        _mutate_pack_count,
        _mutate_candidate_members,
        _mutate_allow_c2,
        _mutate_allow_flat,
        _mutate_output_rule,
        _mutate_pack_path,
        _mutate_extra,
    ],
    ids=lambda mutation: mutation.__name__,
)
def test_resealed_decision_mutations_fail_closed(
    mutation: Mutation,
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    value = copy.deepcopy(_read_correction())
    mutation(value)
    raw = _write_fixture_root(tmp_path, value)
    monkeypatch.setattr(
        checker,
        "CORRECTION_PIN",
        (
            len(raw),
            _sha256(raw),
            value["case435_context_pack_boundary_delta_id"],
        ),
    )
    with pytest.raises(checker.ContextPackBoundaryReject):
        checker.verify(tmp_path)


def test_generator_and_checker_are_separate_standard_library_programs() -> None:
    assert GENERATOR_PATH != CHECKER_PATH
    allowed = {
        "__future__",
        "argparse",
        "hashlib",
        "json",
        "os",
        "pathlib",
        "secrets",
        "sys",
        "typing",
    }
    for path in (GENERATOR_PATH, CHECKER_PATH):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])
        assert imports <= allowed
    assert "generate_raw_v8_step2" not in CHECKER_PATH.read_text(encoding="utf-8")

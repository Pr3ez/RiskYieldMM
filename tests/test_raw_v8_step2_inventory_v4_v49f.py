from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_GENERATOR = "scripts/tests/generate_raw_v8_step2_inventory_v4_v49f.py"
_VALIDATOR = "scripts/tests/validate_raw_v8_step2_inventory_v4_v49f.py"
_V3_INVENTORY = "tests/raw_v8_step2_inventory_v49f.json"
_V4_INVENTORY = "tests/raw_v8_step2_inventory_v4_v49f.json"
_STRUCTURAL_REGISTRY = (
    "scripts/tests/raw_v8_step2_external_schema_v2_structural_registry_v49f.json"
)
_SCHEMA_V3 = "riskyieldmm.raw_v8_step2_inventory.v3"
_SCHEMA_V4 = "riskyieldmm.raw_v8_step2_inventory.v4"
_CANONICALIZATION_VERSION = "riskyieldmm_canonical_json_v1"
_MEASUREMENT_SCHEMA_VERSION = "riskyieldmm_physical_transport_a2m_raw_v49f_v8"
_PROFILE_DOMAIN = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumConstraintScopeProfileV1V4_9F_RawV8"
)
_STRUCTURAL_REGISTRY_DOMAIN = "RiskYieldMMA2MStep2ExternalSchemaRegistryV2V4_9F_RawV8"
_AMENDMENT_ROLE = "STEP2_COMPACT_MAXIMUM_PROOF_V2_CORRECTION"
_AMENDMENT_PATH = (
    "docs/research/"
    "v4_9f_a2_raw_v8_step2_compact_maximum_proof_v2_correction_2026-08-02.md"
)
_AMENDMENT_OCTETS = 49_849
_AMENDMENT_SHA256 = "f4d35405ef1e66a8ba1c59027fc2097a56563d50408eb72cc48895d2127b71b4"
_V4_INVENTORY_OCTETS = 5_265_855
_V4_INVENTORY_RAW_SHA256 = (
    "de91eac92d1c36cf1670b2484392fbf1c633d75f928c8e70fcd5e71ae798db2b"
)
_V4_INVENTORY_ID = "d1435d11a6c9e110b5afb6dacb312f7cd92be71868b2ebe1c8f69ba7f1def3fd"
_V3_INVENTORY_OCTETS = 5_264_966
_V3_INVENTORY_RAW_SHA256 = (
    "f33c1019afa7f49a316aac1bfbef7498e240f391e4fee00dfd95fdcda658669f"
)
_V3_INVENTORY_ID = "128d07a45dc2300c140f333cc3a45e2497aaa4089684f6e44da048ab403bbf9d"
_STRUCTURAL_REGISTRY_ID = (
    "5dc95a3e99c5646e912b6a7e9c3970cf2489d560ea890b0a19d38af4c51c2140"
)
_PROFILE_IDS_SHA256 = "b50b97b682d5707062867f2789a204e0488bdc95be7977f9ddc408959d1c9e0e"
_MAXIMUM_ROW_UNIVERSE_SHA256 = (
    "836db59c1111080882dea078a27847b130d18eed474a8982ebad2e062d532d1c"
)
_GENERATOR_OCTETS = 41_745
_GENERATOR_SHA256 = "0ea8470bfe0942d92daf9aaf4d53b051264a7325f9dfe8a32f4cecdf1b39649e"
_VALIDATOR_OCTETS = 44_131
_VALIDATOR_SHA256 = "eac22b7828cb65abc85e282ee4b6386e2bcf71b58473282d1610ba109e0b0124"
_GENERATOR_ERROR_PREFIX = "Raw-V8 Step-2 V4 inventory migration error: "
_VALIDATOR_ERROR_PREFIX = "RAW_V8_STEP2_INVENTORY_V4_INVALID: "
_MAXIMUM_PROOF_CONTRACT = {
    "mathematical_acceptance_rule": "SOUND_UPPER_BOUND_PLUS_LEGAL_ATTAINMENT_V1",
    "global_least_attainer_required": False,
    "ordered_component_choice_evidence_required": False,
    "proof_resource_report_is_separate": True,
    "publication_selection_policy": "PINNED_ACCEPTED_ATTAINER_V1",
    "maximum_publication_row_count": 474,
    "verifier_owned_scope_case_count": 475,
}
_NORMATIVE_INPUTS = (
    (
        "PARENT_MARKER_OPERATION_TARGET_PROTOCOL",
        "docs/research/"
        "v4_9f_a2_marker_operation_target_v8_protocol_freeze_2026-07-22.md",
        212_471,
        "15b42d32afe5fdff74890b2c18f735ff761244548729142c4ff2b1034fee2388",
    ),
    (
        "STEP2_V2_CONTRACT_FREEZE",
        "docs/research/v4_9f_a2_raw_v8_step2_v2_contract_freeze_2026-07-26.md",
        34_591,
        "355548cb3ef323ab45b0289be9891ab578b75d0147639ab37c9f3e5ff251aa1c",
    ),
    (
        "STEP2_EXTERNAL_SCHEMA_V2_CORRECTION",
        "docs/research/"
        "v4_9f_a2_raw_v8_step2_external_schema_v2_correction_2026-07-28.md",
        217_135,
        "29ec141e53adeb1c0afd51f205f5b57eb784b8859b5ba40958299abd1b713b55",
    ),
    (
        _AMENDMENT_ROLE,
        _AMENDMENT_PATH,
        _AMENDMENT_OCTETS,
        _AMENDMENT_SHA256,
    ),
    (
        "STEP3_TARGET_AND_LIFECYCLE_CORRECTION",
        "docs/research/"
        "v4_9f_a2_raw_v8_step3_target_and_lifecycle_correction_2026-07-26.md",
        435_478,
        "635952095b0b20089d5ec2c13104255ebeeff11535c8f94131a4983a1a9fec0a",
    ),
)
_ROOT_KEYS = {
    "schema_version",
    "normative_document_inputs",
    "invariants",
    "target_field_registry",
    "operation_counter_schema",
    "marker_contract",
    "checkpoint_selector_catalog",
    "ingress_logical_oracle_profile_catalog",
    "external_schema_registry_v2",
    "operation_contracts",
    "fixture_records",
    "inventory_sha256",
}
_PROTECTED_ROOT_MEMBERS = (
    "target_field_registry",
    "operation_counter_schema",
    "marker_contract",
    "checkpoint_selector_catalog",
    "ingress_logical_oracle_profile_catalog",
    "external_schema_registry_v2",
    "operation_contracts",
    "fixture_records",
)
_ALLOWED_INVARIANT_DELTA = {
    "inventory_schema_version",
    "counts",
    "normative_document_sha256_by_role",
    "compact_maximum_proof_v2_contract",
}


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _pretty(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")


def _inventory_sha256(inventory: dict[str, Any]) -> str:
    unsigned = dict(inventory)
    unsigned.pop("inventory_sha256", None)
    return hashlib.sha256(_canonical(unsigned)).hexdigest()


def _resign_inventory(inventory: dict[str, Any]) -> None:
    inventory["inventory_sha256"] = _inventory_sha256(inventory)


def _semantic_id(domain: str, payload: dict[str, Any]) -> str:
    preimage = {
        "canonicalization_version": _CANONICALIZATION_VERSION,
        "domain": domain,
        "payload": payload,
        "schema_version": _MEASUREMENT_SCHEMA_VERSION,
    }
    return hashlib.sha256(_canonical(preimage)).hexdigest()


def _resign_profile(profile: dict[str, Any]) -> None:
    payload = dict(profile)
    payload.pop("maximum_constraint_scope_profile_id", None)
    profile["maximum_constraint_scope_profile_id"] = _semantic_id(
        _PROFILE_DOMAIN,
        payload,
    )


def _refresh_profile_digest(inventory: dict[str, Any]) -> None:
    profiles = inventory["operation_contracts"][
        "maximum_constraint_scope_profile_catalog"
    ]
    inventory["invariants"][
        "maximum_constraint_scope_profile_ids_canonical_json_sha256"
    ] = hashlib.sha256(
        _canonical([item["maximum_constraint_scope_profile_id"] for item in profiles])
    ).hexdigest()


def _load_module(relative_path: str, module_name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, _root() / relative_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _copy_required_authorities(destination: Path) -> Path:
    source_root = _root()
    destination.mkdir(parents=True, exist_ok=False)
    required_paths = {
        _V3_INVENTORY,
        _STRUCTURAL_REGISTRY,
        *(item[1] for item in _NORMATIVE_INPUTS),
    }
    for relative_path in sorted(required_paths):
        target = destination / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_root / relative_path, target)
    return destination.resolve(strict=True)


def _run_generator(
    repository_root: Path,
    *,
    mode: str,
    output: str = "test_output/inventory-v4.json",
    timeout: int = 90,
) -> subprocess.CompletedProcess[str]:
    assert mode in {"--check", "--write"}
    return subprocess.run(
        (
            sys.executable,
            "-I",
            "-B",
            str(_root() / _GENERATOR),
            mode,
            "--repository-root",
            str(repository_root),
            "--output",
            output,
        ),
        cwd=_root(),
        env={
            **os.environ,
            "PYTHONHASHSEED": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _run_validator(
    repository_root: Path,
    inventory_path: Path,
    *,
    timeout: int = 90,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        (
            sys.executable,
            "-I",
            "-B",
            str(_root() / _VALIDATOR),
            "--repository-root",
            str(repository_root),
            "--inventory",
            str(inventory_path),
        ),
        cwd=_root(),
        env={
            **os.environ,
            "PYTHONHASHSEED": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _assert_generator_rejection(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.startswith(_GENERATOR_ERROR_PREFIX)
    assert result.stderr.endswith("\n")
    assert "Traceback" not in result.stderr


def _assert_validator_rejection(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr.startswith(_VALIDATOR_ERROR_PREFIX)
    assert result.stderr.endswith("\n")
    assert "Traceback" not in result.stderr


def _expected_v4_from_v3(
    predecessor: dict[str, Any],
) -> dict[str, Any]:
    expected = copy.deepcopy(predecessor)
    expected["schema_version"] = _SCHEMA_V4
    expected["normative_document_inputs"].insert(
        3,
        {
            "document_role": _AMENDMENT_ROLE,
            "raw_octet_count": _AMENDMENT_OCTETS,
            "raw_sha256": _AMENDMENT_SHA256,
            "repository_relative_path": _AMENDMENT_PATH,
        },
    )
    invariants = expected["invariants"]
    invariants["inventory_schema_version"] = _SCHEMA_V4
    invariants["counts"]["normative_document_input_count"] = 5
    invariants["normative_document_sha256_by_role"][_AMENDMENT_ROLE] = _AMENDMENT_SHA256
    invariants["compact_maximum_proof_v2_contract"] = copy.deepcopy(
        _MAXIMUM_PROOF_CONTRACT
    )
    _resign_inventory(expected)
    return expected


@pytest.fixture(scope="module")
def generator_module() -> ModuleType:
    return _load_module(_GENERATOR, "_raw_v8_step2_inventory_v4_generator_test")


@pytest.fixture(scope="module")
def validator_module() -> ModuleType:
    return _load_module(_VALIDATOR, "_raw_v8_step2_inventory_v4_validator_test")


@pytest.fixture(scope="module")
def generated_candidate(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, Path, bytes, dict[str, Any], bytes, dict[str, Any]]:
    repository = _copy_required_authorities(
        tmp_path_factory.mktemp("raw_v8_step2_inventory_v4") / "repository"
    )
    (repository / "test_output").mkdir()
    predecessor_path = repository / _V3_INVENTORY
    predecessor_raw = predecessor_path.read_bytes()
    predecessor = json.loads(predecessor_raw)
    candidate = repository / "test_output/inventory-v4.json"
    result = _run_generator(repository, mode="--write")
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout.startswith("wrote ")
    assert predecessor_path.read_bytes() == predecessor_raw
    raw = candidate.read_bytes()
    inventory = json.loads(raw)
    assert type(inventory) is dict
    return repository, candidate, raw, inventory, predecessor_raw, predecessor


def _mutated_candidate(
    generated_candidate: tuple[
        Path,
        Path,
        bytes,
        dict[str, Any],
        bytes,
        dict[str, Any],
    ],
    tmp_path: Path,
    mutation: Callable[[dict[str, Any]], None],
    *,
    resign: bool = True,
) -> tuple[Path, dict[str, Any]]:
    repository, _, _, source, _, _ = generated_candidate
    candidate = copy.deepcopy(source)
    mutation(candidate)
    if resign:
        _resign_inventory(candidate)
    directory = repository / "mutations" / tmp_path.name
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "inventory-v4.json"
    path.write_bytes(_pretty(candidate))
    return path, candidate


def _assert_public_rejects(
    validator_module: ModuleType,
    repository: Path,
    inventory_path: Path,
) -> None:
    with pytest.raises(validator_module.InventoryV4ValidationError):
        validator_module.validate_inventory_v4_file(
            repository_root=repository,
            inventory_path=inventory_path,
        )


def test_write_check_second_write_are_deterministic_and_v3_is_immutable(
    generated_candidate: tuple[
        Path,
        Path,
        bytes,
        dict[str, Any],
        bytes,
        dict[str, Any],
    ],
) -> None:
    repository, candidate, raw, _, predecessor_raw, _ = generated_candidate
    predecessor_path = repository / _V3_INVENTORY

    checked = _run_generator(repository, mode="--check")
    assert checked.returncode == 0, checked.stderr
    assert checked.stderr == ""
    assert checked.stdout.startswith("checked ")
    assert candidate.read_bytes() == raw
    assert predecessor_path.read_bytes() == predecessor_raw

    original_inode = candidate.stat().st_ino
    rewritten = _run_generator(repository, mode="--write")
    assert rewritten.returncode == 0, rewritten.stderr
    assert rewritten.stderr == ""
    assert rewritten.stdout.startswith("wrote ")
    assert candidate.read_bytes() == raw
    assert candidate.stat().st_ino != original_inode
    assert predecessor_path.read_bytes() == predecessor_raw

    second = repository / "test_output/inventory-v4-second.json"
    written = _run_generator(
        repository,
        mode="--write",
        output="test_output/inventory-v4-second.json",
    )
    assert written.returncode == 0, written.stderr
    assert written.stderr == ""
    assert written.stdout.startswith("wrote ")
    assert second.read_bytes() == raw
    assert candidate.read_bytes() == raw
    assert predecessor_path.read_bytes() == predecessor_raw
    assert not (repository / _V4_INVENTORY).exists()


def test_generated_v4_is_the_exact_authorized_recursive_delta(
    generated_candidate: tuple[
        Path,
        Path,
        bytes,
        dict[str, Any],
        bytes,
        dict[str, Any],
    ],
) -> None:
    repository, _, raw, inventory, _, predecessor = generated_candidate
    expected = _expected_v4_from_v3(predecessor)

    assert raw == _pretty(inventory)
    assert len(raw) == _V4_INVENTORY_OCTETS
    assert hashlib.sha256(raw).hexdigest() == _V4_INVENTORY_RAW_SHA256
    assert inventory == expected
    assert set(inventory) == _ROOT_KEYS == set(predecessor)
    assert inventory["schema_version"] == _SCHEMA_V4
    assert predecessor["schema_version"] == _SCHEMA_V3
    assert inventory["inventory_sha256"] == _inventory_sha256(inventory)
    assert inventory["inventory_sha256"] == _V4_INVENTORY_ID
    assert inventory["inventory_sha256"] != predecessor["inventory_sha256"]

    documents = inventory["normative_document_inputs"]
    assert [
        (
            item["document_role"],
            item["repository_relative_path"],
            item["raw_octet_count"],
            item["raw_sha256"],
        )
        for item in documents
    ] == list(_NORMATIVE_INPUTS)
    for item in documents:
        raw_authority = (repository / item["repository_relative_path"]).read_bytes()
        assert len(raw_authority) == item["raw_octet_count"]
        assert hashlib.sha256(raw_authority).hexdigest() == item["raw_sha256"]

    contract = inventory["invariants"]["compact_maximum_proof_v2_contract"]
    assert contract == _MAXIMUM_PROOF_CONTRACT
    assert type(contract["global_least_attainer_required"]) is bool
    assert type(contract["ordered_component_choice_evidence_required"]) is bool
    assert type(contract["proof_resource_report_is_separate"]) is bool
    assert type(contract["maximum_publication_row_count"]) is int
    assert type(contract["verifier_owned_scope_case_count"]) is int
    assert contract["maximum_publication_row_count"] == 474
    assert contract["verifier_owned_scope_case_count"] == 475
    assert (
        inventory["invariants"]["constructive_maxima_external_artifact_contract"][
            "total_byte_maximum_row_count"
        ]
        == 474
    )


def test_every_protected_subtree_profile_and_unrelated_invariant_is_unchanged(
    generated_candidate: tuple[
        Path,
        Path,
        bytes,
        dict[str, Any],
        bytes,
        dict[str, Any],
    ],
) -> None:
    _, _, _, inventory, _, predecessor = generated_candidate
    for key in _PROTECTED_ROOT_MEMBERS:
        assert _canonical(inventory[key]) == _canonical(predecessor[key])

    profiles = inventory["operation_contracts"][
        "maximum_constraint_scope_profile_catalog"
    ]
    old_profiles = predecessor["operation_contracts"][
        "maximum_constraint_scope_profile_catalog"
    ]
    assert len(profiles) == len(old_profiles) == 408
    assert profiles == old_profiles
    assert [item["maximum_constraint_scope_profile_id"] for item in profiles] == [
        item["maximum_constraint_scope_profile_id"] for item in old_profiles
    ]
    assert (
        inventory["external_schema_registry_v2"]
        == predecessor["external_schema_registry_v2"]
    )

    old_invariants = predecessor["invariants"]
    new_invariants = inventory["invariants"]
    for key in set(old_invariants) - _ALLOWED_INVARIANT_DELTA:
        assert new_invariants[key] == old_invariants[key]
    assert set(new_invariants) == set(old_invariants) | {
        "compact_maximum_proof_v2_contract"
    }
    old_counts = old_invariants["counts"]
    new_counts = new_invariants["counts"]
    assert {
        key: value
        for key, value in new_counts.items()
        if key != "normative_document_input_count"
    } == {
        key: value
        for key, value in old_counts.items()
        if key != "normative_document_input_count"
    }
    assert new_counts["normative_document_input_count"] == 5


def test_validator_accepts_candidate_independently_and_reports_root_identity(
    generated_candidate: tuple[
        Path,
        Path,
        bytes,
        dict[str, Any],
        bytes,
        dict[str, Any],
    ],
    validator_module: ModuleType,
) -> None:
    repository, candidate, raw, inventory, _, predecessor = generated_candidate
    report = validator_module.validate_inventory_v4_file(
        repository_root=repository,
        inventory_path=candidate,
    )
    assert report == {
        "component_status": "V4_INVENTORY_NARROW_MIGRATION_VALIDATED",
        "external_schema_registry_id": _STRUCTURAL_REGISTRY_ID,
        "inventory_octets": _V4_INVENTORY_OCTETS,
        "inventory_raw_sha256": _V4_INVENTORY_RAW_SHA256,
        "inventory_sha256": _V4_INVENTORY_ID,
        "maximum_constraint_scope_profile_count": 408,
        "maximum_constraint_scope_profile_ids_canonical_json_sha256": (
            _PROFILE_IDS_SHA256
        ),
        "maximum_publication_row_count": 474,
        "maximum_row_universe_canonical_json_sha256": (_MAXIMUM_ROW_UNIVERSE_SHA256),
        "normative_document_input_count": 5,
        "predecessor_inventory_octets": _V3_INVENTORY_OCTETS,
        "predecessor_inventory_raw_sha256": _V3_INVENTORY_RAW_SHA256,
        "predecessor_inventory_sha256": _V3_INVENTORY_ID,
        "schema_version": _SCHEMA_V4,
        "verifier_owned_scope_case_count": 475,
    }
    assert inventory["inventory_sha256"] == _V4_INVENTORY_ID
    assert predecessor["inventory_sha256"] == _V3_INVENTORY_ID

    result = _run_validator(repository, candidate)
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout.endswith("\n")
    assert "\n" not in result.stdout[:-1]
    cli_report = json.loads(result.stdout)
    assert cli_report == report
    assert hashlib.sha256(raw).hexdigest() == cli_report["inventory_raw_sha256"]


def test_validator_default_inventory_with_relative_repository_root(
    tmp_path: Path,
) -> None:
    repository = _copy_required_authorities(tmp_path / "repository")
    written = _run_generator(
        repository,
        mode="--write",
        output=_V4_INVENTORY,
    )
    assert written.returncode == 0, written.stderr

    result = subprocess.run(
        (
            sys.executable,
            "-I",
            "-B",
            str(_root() / _VALIDATOR),
            "--repository-root",
            "repository",
        ),
        cwd=tmp_path,
        env={
            **os.environ,
            "PYTHONHASHSEED": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    report = json.loads(result.stdout)
    assert report["inventory_sha256"] == _V4_INVENTORY_ID
    assert report["inventory_raw_sha256"] == _V4_INVENTORY_RAW_SHA256


def _v3_relabel(inventory: dict[str, Any]) -> None:
    predecessor = json.loads((_root() / _V3_INVENTORY).read_bytes())
    predecessor["schema_version"] = _SCHEMA_V4
    predecessor["invariants"]["inventory_schema_version"] = _SCHEMA_V4
    inventory.clear()
    inventory.update(predecessor)


def _missing_amendment(inventory: dict[str, Any]) -> None:
    inventory["normative_document_inputs"].pop(3)
    inventory["invariants"]["counts"]["normative_document_input_count"] = 4
    inventory["invariants"]["normative_document_sha256_by_role"].pop(_AMENDMENT_ROLE)


def _duplicate_amendment(inventory: dict[str, Any]) -> None:
    inventory["normative_document_inputs"].insert(
        4,
        copy.deepcopy(inventory["normative_document_inputs"][3]),
    )
    inventory["invariants"]["counts"]["normative_document_input_count"] = 6


def _wrong_document_order(inventory: dict[str, Any]) -> None:
    documents = inventory["normative_document_inputs"]
    documents[2], documents[3] = documents[3], documents[2]


def _wrong_amendment_role(inventory: dict[str, Any]) -> None:
    inventory["normative_document_inputs"][3]["document_role"] = (
        "STEP2_COMPACT_MAXIMUM_PROOF_CORRECTION"
    )


def _wrong_amendment_path(inventory: dict[str, Any]) -> None:
    inventory["normative_document_inputs"][3]["repository_relative_path"] = (
        _NORMATIVE_INPUTS[2][1]
    )


def _wrong_amendment_hash(inventory: dict[str, Any]) -> None:
    inventory["normative_document_inputs"][3]["raw_sha256"] = "0" * 64
    inventory["invariants"]["normative_document_sha256_by_role"][_AMENDMENT_ROLE] = (
        "0" * 64
    )


def _wrong_amendment_size(inventory: dict[str, Any]) -> None:
    inventory["normative_document_inputs"][3]["raw_octet_count"] += 1


def _unrelated_invariant_drift(inventory: dict[str, Any]) -> None:
    inventory["invariants"]["target_field_registry_canonical_json_bytes"] += 1


def _profile_drift_with_nested_resign(inventory: dict[str, Any]) -> None:
    profile = inventory["operation_contracts"][
        "maximum_constraint_scope_profile_catalog"
    ][0]
    profile["application_schedule_formula"] += "_DRIFT"
    _resign_profile(profile)
    _refresh_profile_digest(inventory)


def _registry_drift(inventory: dict[str, Any]) -> None:
    registry = inventory["external_schema_registry_v2"]
    registry["external_schema_profile"] += "_DRIFT"
    payload = {
        key: value
        for key, value in registry.items()
        if key
        not in {
            "canonicalization_version",
            "measurement_schema_version",
            "record_domain",
            "external_schema_registry_id",
        }
    }
    registry["external_schema_registry_id"] = _semantic_id(
        _STRUCTURAL_REGISTRY_DOMAIN,
        payload,
    )


def _pointer_drift_with_nested_resign(inventory: dict[str, Any]) -> None:
    profile = inventory["operation_contracts"][
        "maximum_constraint_scope_profile_catalog"
    ][0]
    other = inventory["fixture_records"]["operation_specs"]["INGRESS"]
    profile["ordered_source_authority_pointers"][0] = (
        "/fixture_records/operation_specs/INGRESS"
    )
    profile["ordered_source_authority_ids"][0] = other["operation_spec_id"]
    _resign_profile(profile)
    _refresh_profile_digest(inventory)


def _wrong_contract_type(inventory: dict[str, Any]) -> None:
    inventory["invariants"]["compact_maximum_proof_v2_contract"][
        "maximum_publication_row_count"
    ] = 474.0


def _wrong_contract_value(inventory: dict[str, Any]) -> None:
    inventory["invariants"]["compact_maximum_proof_v2_contract"][
        "global_least_attainer_required"
    ] = True


_SEMANTIC_MUTATIONS: tuple[tuple[str, Callable[[dict[str, Any]], None]], ...] = (
    ("v3_relabel", _v3_relabel),
    ("missing_amendment", _missing_amendment),
    ("duplicate_amendment", _duplicate_amendment),
    ("wrong_document_order", _wrong_document_order),
    ("wrong_amendment_role", _wrong_amendment_role),
    ("wrong_amendment_path", _wrong_amendment_path),
    ("wrong_amendment_hash", _wrong_amendment_hash),
    ("wrong_amendment_size", _wrong_amendment_size),
    ("unrelated_invariant_drift", _unrelated_invariant_drift),
    ("profile_drift_with_nested_resign", _profile_drift_with_nested_resign),
    ("registry_drift", _registry_drift),
    ("pointer_drift_with_nested_resign", _pointer_drift_with_nested_resign),
    ("wrong_contract_type", _wrong_contract_type),
    ("wrong_contract_value", _wrong_contract_value),
)


@pytest.mark.parametrize(
    ("case", "mutation"),
    _SEMANTIC_MUTATIONS,
    ids=[item[0] for item in _SEMANTIC_MUTATIONS],
)
def test_resigned_semantic_drift_is_rejected(
    generated_candidate: tuple[
        Path,
        Path,
        bytes,
        dict[str, Any],
        bytes,
        dict[str, Any],
    ],
    validator_module: ModuleType,
    tmp_path: Path,
    case: str,
    mutation: Callable[[dict[str, Any]], None],
) -> None:
    del case
    repository, _, _, _, _, _ = generated_candidate
    path, _ = _mutated_candidate(generated_candidate, tmp_path, mutation)
    _assert_public_rejects(validator_module, repository, path)


def test_wrong_root_identity_rejects_before_semantic_acceptance(
    generated_candidate: tuple[
        Path,
        Path,
        bytes,
        dict[str, Any],
        bytes,
        dict[str, Any],
    ],
    validator_module: ModuleType,
    tmp_path: Path,
) -> None:
    repository, _, _, _, _, _ = generated_candidate
    path, _ = _mutated_candidate(
        generated_candidate,
        tmp_path,
        lambda inventory: inventory.__setitem__("inventory_sha256", "0" * 64),
        resign=False,
    )
    _assert_public_rejects(validator_module, repository, path)


def test_duplicate_nonfinite_noncanonical_deep_and_oversize_reject_cleanly(
    generated_candidate: tuple[
        Path,
        Path,
        bytes,
        dict[str, Any],
        bytes,
        dict[str, Any],
    ],
) -> None:
    repository, _, raw, inventory, _, _ = generated_candidate
    directory = repository / "raw-invalid"
    directory.mkdir()
    paths: list[Path] = []

    duplicate = directory / "duplicate.json"
    duplicate.write_bytes(b'{\n  "schema_version": "duplicate",\n' + raw[2:])
    paths.append(duplicate)
    nonfinite = directory / "nonfinite.json"
    nonfinite.write_bytes(b'{"value":NaN}\n')
    paths.append(nonfinite)
    noncanonical = directory / "noncanonical.json"
    noncanonical.write_bytes(_canonical(inventory))
    paths.append(noncanonical)
    deep = directory / "deep.json"
    deep.write_bytes(b'{"x":' + b"[" * 300 + b"0" + b"]" * 300 + b"}\n")
    paths.append(deep)
    oversized = directory / "oversized.json"
    with oversized.open("wb") as stream:
        stream.truncate(16_777_216)
    paths.append(oversized)

    for path in paths:
        _assert_validator_rejection(_run_validator(repository, path))


def test_validator_rejects_outside_symlink_fifo_and_hardlink_candidates(
    generated_candidate: tuple[
        Path,
        Path,
        bytes,
        dict[str, Any],
        bytes,
        dict[str, Any],
    ],
    tmp_path: Path,
) -> None:
    repository, candidate, raw, _, _, _ = generated_candidate

    outside = tmp_path / "outside-v4.json"
    outside.write_bytes(raw)
    _assert_validator_rejection(_run_validator(repository, outside))

    symlink = repository / "candidate-link.json"
    symlink.symlink_to(candidate)
    _assert_validator_rejection(_run_validator(repository, symlink))

    fifo = repository / "candidate.fifo"
    os.mkfifo(fifo)
    _assert_validator_rejection(_run_validator(repository, fifo, timeout=15))

    linked_source = repository / "linked-source.json"
    linked_source.write_bytes(raw)
    hardlink = repository / "candidate-hardlink.json"
    os.link(linked_source, hardlink)
    _assert_validator_rejection(_run_validator(repository, hardlink))


def test_validator_rechecks_all_sources_after_semantic_validation(
    generated_candidate: tuple[
        Path,
        Path,
        bytes,
        dict[str, Any],
        bytes,
        dict[str, Any],
    ],
    validator_module: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, candidate_raw, _, _, _ = generated_candidate
    repository = _copy_required_authorities(tmp_path / "repository")
    candidate = repository / "candidate-v4.json"
    candidate.write_bytes(candidate_raw)
    amendment = repository / _AMENDMENT_PATH
    original_validate = validator_module._validate_v4_candidate
    mutated = False

    def validate_then_mutate(*args: Any, **kwargs: Any) -> tuple[str, str, str]:
        nonlocal mutated
        result = original_validate(*args, **kwargs)
        amendment.write_bytes(amendment.read_bytes() + b"\n")
        mutated = True
        return result

    monkeypatch.setattr(
        validator_module,
        "_validate_v4_candidate",
        validate_then_mutate,
    )
    _assert_public_rejects(validator_module, repository, candidate)
    assert mutated


@pytest.mark.parametrize("kind", ("symlink", "fifo", "hardlink"))
def test_generator_rejects_unsafe_amendment_authority(
    tmp_path: Path,
    kind: str,
) -> None:
    repository = _copy_required_authorities(tmp_path / "repository")
    (repository / "test_output").mkdir()
    amendment = repository / _AMENDMENT_PATH
    original = amendment.read_bytes()
    amendment.unlink()

    if kind == "symlink":
        outside = tmp_path / "outside-amendment.md"
        outside.write_bytes(original)
        amendment.symlink_to(outside)
    elif kind == "fifo":
        os.mkfifo(amendment)
    else:
        regular = repository / "amendment-hardlink-source.md"
        regular.write_bytes(original)
        os.link(regular, amendment)

    _assert_generator_rejection(_run_generator(repository, mode="--write", timeout=15))
    assert not (repository / "test_output/inventory-v4.json").exists()


def test_generator_rejects_input_overwrite_and_path_traversal_without_mutation(
    tmp_path: Path,
) -> None:
    for protected_relative in (
        _V3_INVENTORY,
        _STRUCTURAL_REGISTRY,
        _AMENDMENT_PATH,
    ):
        repository = _copy_required_authorities(
            tmp_path / protected_relative.split("/")[-1]
        )
        protected = repository / protected_relative
        before = protected.read_bytes()
        _assert_generator_rejection(
            _run_generator(
                repository,
                mode="--write",
                output=protected_relative,
            )
        )
        assert protected.read_bytes() == before
        assert list(protected.parent.glob(f".{protected.name}.tmp.*")) == []

    repository = _copy_required_authorities(tmp_path / "traversal-repository")
    escaped = tmp_path / "escaped-v4.json"
    _assert_generator_rejection(
        _run_generator(repository, mode="--write", output="../escaped-v4.json")
    )
    assert not escaped.exists()


@pytest.mark.parametrize("kind", ("symlink", "fifo", "hardlink"))
def test_generator_rejects_unsafe_existing_output_without_overwrite(
    tmp_path: Path,
    kind: str,
) -> None:
    repository = _copy_required_authorities(tmp_path / "repository")
    output_parent = repository / "test_output"
    output_parent.mkdir()
    output = output_parent / "inventory-v4.json"
    sentinel = b"existing-authority-must-survive\n"

    if kind == "symlink":
        outside = tmp_path / "outside-output.json"
        outside.write_bytes(sentinel)
        output.symlink_to(outside)
    elif kind == "fifo":
        os.mkfifo(output)
    else:
        source = output_parent / "hardlink-source.json"
        source.write_bytes(sentinel)
        os.link(source, output)

    _assert_generator_rejection(_run_generator(repository, mode="--write", timeout=15))
    if kind == "symlink":
        assert outside.read_bytes() == sentinel
    elif kind == "hardlink":
        assert source.read_bytes() == sentinel
    assert list(output_parent.glob(".inventory-v4.json.tmp.*")) == []


def test_generator_atomic_failure_preserves_target_and_cleans_temporary(
    tmp_path: Path,
    generator_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = (tmp_path / "repository").resolve()
    output_parent = repository / "test_output"
    output_parent.mkdir(parents=True)
    output = output_parent / "inventory-v4.json"
    original = b"existing-complete-authority\n"
    output.write_bytes(original)
    real_write = generator_module.os.write
    write_calls = 0

    def partial_then_fail(descriptor: int, value: bytes) -> int:
        nonlocal write_calls
        write_calls += 1
        if write_calls == 1:
            return real_write(descriptor, value[:17])
        raise OSError("injected atomic write failure")

    monkeypatch.setattr(generator_module.os, "write", partial_then_fail)
    with pytest.raises(OSError, match="injected atomic write failure"):
        generator_module._atomic_write_repository_output(
            repository,
            "test_output/inventory-v4.json",
            b"replacement" * 10_000,
            protected_inodes=frozenset(),
        )

    assert output.read_bytes() == original
    assert list(output_parent.glob(".inventory-v4.json.tmp.*")) == []


def test_generator_rechecks_all_sources_after_migration_before_publication(
    tmp_path: Path,
    generator_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repository = _copy_required_authorities(tmp_path / "repository")
    (repository / "test_output").mkdir()
    amendment = repository / _AMENDMENT_PATH
    original_migrate = generator_module._migrate_inventory
    mutated = False

    def migrate_then_mutate(predecessor: dict[str, Any]) -> dict[str, Any]:
        nonlocal mutated
        result = original_migrate(predecessor)
        amendment.write_bytes(amendment.read_bytes() + b"\n")
        mutated = True
        return result

    monkeypatch.setattr(generator_module, "_migrate_inventory", migrate_then_mutate)
    return_code = generator_module.main(
        [
            "--write",
            "--repository-root",
            str(repository),
            "--output",
            "test_output/inventory-v4.json",
        ]
    )
    captured = capsys.readouterr()
    assert return_code == 1
    assert mutated
    assert captured.out == ""
    assert captured.err.startswith(_GENERATOR_ERROR_PREFIX)
    assert "Traceback" not in captured.err
    assert not (repository / "test_output/inventory-v4.json").exists()
    assert list((repository / "test_output").glob(".inventory-v4.json.tmp.*")) == []


def test_generator_and_validator_are_stdlib_only_and_validator_is_independent() -> None:
    for relative_path in (_GENERATOR, _VALIDATOR):
        path = _root() / relative_path
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, path.name)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".", 1)[0] in sys.stdlib_module_names
                    assert not alias.name.startswith("riskyieldmm")
            elif isinstance(node, ast.ImportFrom):
                assert node.level == 0
                assert node.module is not None
                assert node.module.split(".", 1)[0] in (
                    sys.stdlib_module_names | {"__future__"}
                )
                assert not node.module.startswith("riskyieldmm")
        assert "sys.path" not in source
        assert "__import__" not in source
        assert "from scripts.tests" not in source

    validator_source = (_root() / _VALIDATOR).read_text(encoding="utf-8")
    assert "generate_raw_v8_step2_inventory_v4_v49f" not in validator_source
    assert "InventoryMigrationError" not in validator_source

    generator_raw = (_root() / _GENERATOR).read_bytes()
    assert len(generator_raw) == _GENERATOR_OCTETS
    assert hashlib.sha256(generator_raw).hexdigest() == _GENERATOR_SHA256
    validator_raw = (_root() / _VALIDATOR).read_bytes()
    assert len(validator_raw) == _VALIDATOR_OCTETS
    assert hashlib.sha256(validator_raw).hexdigest() == _VALIDATOR_SHA256

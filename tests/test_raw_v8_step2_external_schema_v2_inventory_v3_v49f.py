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
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_GENERATOR = "scripts/tests/generate_raw_v8_step2_inventory_v49f.py"
_VALIDATOR = "scripts/tests/validate_raw_v8_step2_external_schema_v2_v49f.py"
_GOLDEN = "tests/raw_v8_step2_inventory_v49f.json"
_STRUCTURAL_REGISTRY = (
    "scripts/tests/raw_v8_step2_external_schema_v2_structural_registry_v49f.json"
)
_SCHEMA_VERSION = "riskyieldmm.raw_v8_step2_inventory.v3"
_CANONICALIZATION_VERSION = "riskyieldmm_canonical_json_v1"
_MEASUREMENT_SCHEMA_VERSION = "riskyieldmm_physical_transport_a2m_raw_v49f_v8"
_STRUCTURAL_REGISTRY_SHA256 = (
    "9160297ff316c5931737c92f8b359f0a1e2ec22f0aa996ef3b09cf830dc96bf3"
)
_STRUCTURAL_REGISTRY_OCTETS = 1_469_663
_STRUCTURAL_REGISTRY_ID = (
    "5dc95a3e99c5646e912b6a7e9c3970cf2489d560ea890b0a19d38af4c51c2140"
)
_INVENTORY_OCTETS = 5_264_966
_INVENTORY_RAW_SHA256 = (
    "f33c1019afa7f49a316aac1bfbef7498e240f391e4fee00dfd95fdcda658669f"
)
_INVENTORY_SEMANTIC_SHA256 = (
    "128d07a45dc2300c140f333cc3a45e2497aaa4089684f6e44da048ab403bbf9d"
)
_GENERATOR_OCTETS = 225_129
_GENERATOR_SHA256 = "f2ec89ef8e2d835ec4805e0f2890eb9d2b5c60f1de1fccd5e58cb0e69b9e0798"
_VALIDATOR_OCTETS = 77_117
_VALIDATOR_SHA256 = "1ec74910c5c4887467bfcaeef6608a44c161f95e8be00bef28b10c615ef43914"
_PROFILE_DOMAIN = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumConstraintScopeProfileV1V4_9F_RawV8"
)
_VALIDATOR_ERROR_PREFIX = "Raw-V8 Step-2 External Schema V2 V3 inventory error: "
_GENERATOR_ERROR_PREFIX = "Raw-V8 Step-2 inventory error: "
_OPERATION_KINDS = (
    "ACK_DEADLINE_EXPIRY",
    "INGRESS",
    "LOCAL_SHUTDOWN",
    "SUBSCRIPTION_DISPATCH",
)
_CHECKPOINT_OUTCOMES = (
    "EXACT_MARKER",
    "ARTIFACT_BOUND_EXCEEDED",
    "OBSERVER_INTERNAL_ERROR",
    "SOURCE_CLOCK_UNAVAILABLE",
    "TARGET_BOUNDARY_NOT_REACHED",
)
_NORMATIVE_INPUTS = (
    (
        "PARENT_MARKER_OPERATION_TARGET_PROTOCOL",
        "docs/research/"
        "v4_9f_a2_marker_operation_target_v8_protocol_freeze_2026-07-22.md",
    ),
    (
        "STEP2_V2_CONTRACT_FREEZE",
        "docs/research/v4_9f_a2_raw_v8_step2_v2_contract_freeze_2026-07-26.md",
    ),
    (
        "STEP2_EXTERNAL_SCHEMA_V2_CORRECTION",
        "docs/research/"
        "v4_9f_a2_raw_v8_step2_external_schema_v2_correction_2026-07-28.md",
    ),
    (
        "STEP3_TARGET_AND_LIFECYCLE_CORRECTION",
        "docs/research/"
        "v4_9f_a2_raw_v8_step3_target_and_lifecycle_correction_2026-07-26.md",
    ),
)
_NORMATIVE_RAW_AUTHORITY = {
    "PARENT_MARKER_OPERATION_TARGET_PROTOCOL": (
        212_471,
        "15b42d32afe5fdff74890b2c18f735ff761244548729142c4ff2b1034fee2388",
    ),
    "STEP2_V2_CONTRACT_FREEZE": (
        34_591,
        "355548cb3ef323ab45b0289be9891ab578b75d0147639ab37c9f3e5ff251aa1c",
    ),
    "STEP2_EXTERNAL_SCHEMA_V2_CORRECTION": (
        217_135,
        "29ec141e53adeb1c0afd51f205f5b57eb784b8859b5ba40958299abd1b713b55",
    ),
    "STEP3_TARGET_AND_LIFECYCLE_CORRECTION": (
        435_478,
        "635952095b0b20089d5ec2c13104255ebeeff11535c8f94131a4983a1a9fec0a",
    ),
}
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
_PROFILE_KEYS = {
    "profile_position",
    "profile_kind",
    "constraint_scope",
    "measured_type_name",
    "operation_kind",
    "ordered_source_authority_pointers",
    "ordered_source_authority_ids",
    "selector_catalog_position",
    "selector_catalog_name",
    "checkpoint_selector_id",
    "checkpoint_selector_entry_id",
    "expected_checkpoint_marker_kind",
    "expected_occurrence_index_within_kind",
    "selector_position",
    "checkpoint_outcome",
    "checkpoint_binding_status",
    "checkpoint_binding_unavailable_reason",
    "checkpoint_field_unavailable_reason",
    "ordered_admissible_root_families",
    "application_schedule_formula",
    "maximum_constraint_scope_profile_id",
}
_ROOT_FAMILY_KEYS = {
    "root_family_kind",
    "ordered_instrumentation_mode_attempt_presence_pairs",
    "selector_catalog_position",
    "selector_catalog_name",
    "checkpoint_selector_id",
    "selector_length",
    "observation_count",
    "role_sequence_formula",
    "ordered_measured_observation_roles",
    "selector_present",
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


def _semantic_id(domain: str, payload: dict[str, Any]) -> str:
    preimage = {
        "canonicalization_version": _CANONICALIZATION_VERSION,
        "domain": domain,
        "payload": payload,
        "schema_version": _MEASUREMENT_SCHEMA_VERSION,
    }
    return hashlib.sha256(_canonical(preimage)).hexdigest()


def _inventory_sha256(inventory: dict[str, Any]) -> str:
    unsigned = dict(inventory)
    unsigned.pop("inventory_sha256", None)
    return hashlib.sha256(_canonical(unsigned)).hexdigest()


def _resign_inventory(inventory: dict[str, Any]) -> None:
    inventory["inventory_sha256"] = _inventory_sha256(inventory)


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


def _copy_authority_repository(destination: Path) -> Path:
    source_root = _root()
    destination.mkdir(parents=True, exist_ok=False)
    for _, relative in _NORMATIVE_INPUTS:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_root / relative, target)
    registry_target = destination / _STRUCTURAL_REGISTRY
    registry_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_root / _STRUCTURAL_REGISTRY, registry_target)
    return destination.resolve(strict=True)


def _run_generator(
    repository_root: Path,
    *,
    output: str,
    mode: str,
    timeout: int = 180,
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
    inventory: Path,
    *,
    timeout: int = 120,
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
            str(inventory),
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


def _assert_controlled_rejection(
    result: subprocess.CompletedProcess[str], *, prefix: str
) -> None:
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.startswith(prefix)
    assert result.stderr.endswith("\n")
    assert "Traceback" not in result.stderr


def _load_script(relative: str, module_name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, _root() / relative)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def generator_module() -> ModuleType:
    return _load_script(_GENERATOR, "_raw_v8_step2_v3_inventory_generator_test")


@pytest.fixture(scope="module")
def validator_module() -> ModuleType:
    return _load_script(_VALIDATOR, "_raw_v8_step2_v3_inventory_validator_test")


@pytest.fixture(scope="module")
def generated_candidate(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, Path, bytes, dict[str, Any]]:
    repository = _copy_authority_repository(
        tmp_path_factory.mktemp("raw_v8_inventory_v3") / "repository"
    )
    (repository / "test_output").mkdir()
    candidate = repository / "test_output/candidate.json"
    result = _run_generator(
        repository,
        output="test_output/candidate.json",
        mode="--write",
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    raw = candidate.read_bytes()
    value = json.loads(raw)
    assert type(value) is dict
    return repository, candidate, raw, value


def _mutated_inventory_path(
    generated_candidate: tuple[Path, Path, bytes, dict[str, Any]],
    tmp_path: Path,
    mutation: Callable[[dict[str, Any]], None],
    *,
    resign: bool = True,
) -> tuple[Path, dict[str, Any]]:
    repository, _, _, source = generated_candidate
    candidate = copy.deepcopy(source)
    mutation(candidate)
    if resign:
        _resign_inventory(candidate)
    directory = repository / "mutations" / tmp_path.name
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "inventory.json"
    path.write_bytes(_pretty(candidate))
    return path, candidate


def _assert_public_rejects(
    validator: ModuleType,
    repository: Path,
    path: Path,
) -> None:
    with pytest.raises(validator.InventoryValidationError):
        validator.validate_inventory_file(
            repository_root=repository,
            inventory_path=path,
        )


def _resolve_pointer(root: dict[str, Any], pointer: str) -> Any:
    assert pointer.startswith("/")
    current: Any = root
    for token in pointer[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if type(current) is list:
            current = current[int(token)]
        else:
            assert type(current) is dict
            current = current[token]
    return current


def _authority_id(value: dict[str, Any]) -> str:
    fields = (
        "operation_spec_id",
        "target_field_registry_id",
        "marker_contract_id",
        "checkpoint_selector_id",
    )
    present = [field for field in fields if field in value]
    assert len(present) == 1
    result = value[present[0]]
    assert type(result) is str
    return result


def test_generator_write_check_and_second_write_are_byte_reproducible(
    generated_candidate: tuple[Path, Path, bytes, dict[str, Any]],
) -> None:
    repository, candidate, raw, _ = generated_candidate
    default_golden = repository / _GOLDEN
    assert not default_golden.exists()

    checked = _run_generator(
        repository,
        output="test_output/candidate.json",
        mode="--check",
    )
    assert checked.returncode == 0, checked.stderr
    assert checked.stderr == ""
    assert checked.stdout.startswith("checked ")

    second = repository / "test_output/candidate-second.json"
    written = _run_generator(
        repository,
        output="test_output/candidate-second.json",
        mode="--write",
    )
    assert written.returncode == 0, written.stderr
    assert written.stderr == ""
    assert second.read_bytes() == raw == candidate.read_bytes()
    assert not default_golden.exists()


def test_generated_v3_root_documents_registry_and_counts_are_exact(
    generated_candidate: tuple[Path, Path, bytes, dict[str, Any]],
) -> None:
    repository, _, raw, inventory = generated_candidate
    assert raw == _pretty(inventory)
    assert len(raw) == _INVENTORY_OCTETS
    assert hashlib.sha256(raw).hexdigest() == _INVENTORY_RAW_SHA256
    assert set(inventory) == _ROOT_KEYS
    assert inventory["schema_version"] == _SCHEMA_VERSION
    assert inventory["inventory_sha256"] == _inventory_sha256(inventory)
    assert inventory["inventory_sha256"] == _INVENTORY_SEMANTIC_SHA256

    documents = inventory["normative_document_inputs"]
    assert [
        (item["document_role"], item["repository_relative_path"]) for item in documents
    ] == list(_NORMATIVE_INPUTS)
    assert len(documents) == 4
    for item in documents:
        document = repository / item["repository_relative_path"]
        source = document.read_bytes()
        assert item["raw_octet_count"] == len(source)
        assert item["raw_sha256"] == hashlib.sha256(source).hexdigest()
        assert (
            item["raw_octet_count"],
            item["raw_sha256"],
        ) == _NORMATIVE_RAW_AUTHORITY[item["document_role"]]

    registry_raw = (repository / _STRUCTURAL_REGISTRY).read_bytes()
    assert len(registry_raw) == _STRUCTURAL_REGISTRY_OCTETS
    assert hashlib.sha256(registry_raw).hexdigest() == _STRUCTURAL_REGISTRY_SHA256
    registry = json.loads(registry_raw)
    assert inventory["external_schema_registry_v2"] == registry
    assert registry["external_schema_registry_id"] == _STRUCTURAL_REGISTRY_ID
    assert "external_type_registry" not in inventory

    counts = inventory["invariants"]["counts"]
    assert counts["normative_document_input_count"] == 4
    assert counts["operation_kind_count"] == 4
    assert counts["target_field_count"] == 185
    assert counts["external_type_descriptor_count"] == 52
    assert counts["checkpoint_selector_catalog_count"] == 9
    assert counts["maximum_constraint_scope_profile_count"] == 408
    assert counts["maximum_result_scope_profile_count"] == 4
    assert counts["maximum_non_checkpoint_scope_profile_count"] == 4
    assert counts["maximum_checkpoint_scope_profile_count"] == 400
    assert inventory["invariants"][
        "constructive_maxima_external_artifact_contract"
    ] == {
        "intrinsic_byte_maximum_row_count": 66,
        "outer_result_byte_maximum_row_count": 4,
        "root_application_byte_maximum_row_count": 404,
        "total_byte_maximum_row_count": 474,
        "local_shutdown_counterexample_count": 1,
        "maximum_rows_embedded_in_inventory": False,
        "heuristic_bound_proofs_are_authority": False,
    }


def test_all_408_scope_profiles_are_complete_self_identifying_and_ordered(
    generated_candidate: tuple[Path, Path, bytes, dict[str, Any]],
) -> None:
    _, _, _, inventory = generated_candidate
    profiles = inventory["operation_contracts"][
        "maximum_constraint_scope_profile_catalog"
    ]
    assert len(profiles) == 408
    assert Counter(item["profile_kind"] for item in profiles) == {
        "OUTER_RESULT_BOUNDARY_FIXTURE": 4,
        "NON_CHECKPOINT_ROOT_FAMILY": 4,
        "CHECKPOINT_ROOT_COORDINATE": 400,
    }
    assert [item["profile_position"] for item in profiles] == list(range(1, 409))
    assert [item["operation_kind"] for item in profiles[:4]] == list(_OPERATION_KINDS)
    assert [item["operation_kind"] for item in profiles[4:8]] == list(_OPERATION_KINDS)

    profile_ids: list[str] = []
    for profile in profiles:
        assert set(profile) == _PROFILE_KEYS
        payload = dict(profile)
        profile_id = payload.pop("maximum_constraint_scope_profile_id")
        assert profile_id == _semantic_id(_PROFILE_DOMAIN, payload)
        profile_ids.append(profile_id)
        pointers = profile["ordered_source_authority_pointers"]
        ids = profile["ordered_source_authority_ids"]
        assert len(pointers) == len(ids)
        assert ids == [
            _authority_id(_resolve_pointer(inventory, pointer)) for pointer in pointers
        ]
        for family in profile["ordered_admissible_root_families"]:
            assert set(family) == _ROOT_FAMILY_KEYS
            assert all(
                type(pair) is list
                and len(pair) == 2
                and pair[0] in {"OFF", "ON"}
                and pair[1] in {"NULL", "NON_NULL"}
                for pair in family[
                    "ordered_instrumentation_mode_attempt_presence_pairs"
                ]
            )
    assert len(set(profile_ids)) == 408
    assert (
        inventory["invariants"][
            "maximum_constraint_scope_profile_ids_canonical_json_sha256"
        ]
        == hashlib.sha256(_canonical(profile_ids)).hexdigest()
    )

    result_null_fields = (
        "selector_catalog_position",
        "selector_catalog_name",
        "checkpoint_selector_id",
        "checkpoint_selector_entry_id",
        "expected_checkpoint_marker_kind",
        "expected_occurrence_index_within_kind",
        "selector_position",
        "checkpoint_outcome",
        "checkpoint_binding_status",
        "checkpoint_binding_unavailable_reason",
        "checkpoint_field_unavailable_reason",
    )
    specs = inventory["fixture_records"]["operation_specs"]
    for position, (operation_kind, profile) in enumerate(
        zip(_OPERATION_KINDS, profiles[:4], strict=True),
        1,
    ):
        assert profile["profile_position"] == position
        assert profile["profile_kind"] == "OUTER_RESULT_BOUNDARY_FIXTURE"
        assert profile["constraint_scope"] == "FROZEN_FIXTURE"
        assert (
            profile["measured_type_name"]
            == "CapacityMeasurementOperationResultEvidence"
        )
        assert profile["operation_kind"] == operation_kind
        assert profile["ordered_source_authority_pointers"] == [
            f"/fixture_records/operation_specs/{operation_kind}"
        ]
        assert profile["ordered_source_authority_ids"] == [
            specs[operation_kind]["operation_spec_id"]
        ]
        assert all(profile[field] is None for field in result_null_fields)
        assert profile["ordered_admissible_root_families"] == []
        assert (
            profile["application_schedule_formula"]
            == "OUTER_RESULT_SIGNED_SPEC_SINGLE_APPLICATION_V1"
        )

    startup_family = {
        "root_family_kind": "STARTUP_RECOVERY_ONE",
        "ordered_instrumentation_mode_attempt_presence_pairs": [
            ["OFF", "NULL"],
            ["ON", "NULL"],
        ],
        "selector_catalog_position": None,
        "selector_catalog_name": None,
        "checkpoint_selector_id": None,
        "selector_length": 0,
        "observation_count": 1,
        "role_sequence_formula": "STARTUP_RECOVERY_ONE_V1",
        "ordered_measured_observation_roles": ["STARTUP_RECOVERY"],
        "selector_present": False,
    }
    selector_free_family = {
        "root_family_kind": "ORDINARY_SELECTOR_FREE_THREE",
        "ordered_instrumentation_mode_attempt_presence_pairs": [
            ["OFF", "NULL"],
            ["OFF", "NON_NULL"],
            ["ON", "NULL"],
        ],
        "selector_catalog_position": None,
        "selector_catalog_name": None,
        "checkpoint_selector_id": None,
        "selector_length": 0,
        "observation_count": 3,
        "role_sequence_formula": ("ORDINARY_BEFORE_CHECKPOINTS_AFTER_AGGREGATE_V1"),
        "ordered_measured_observation_roles": [
            "BEFORE_OPERATION",
            "AFTER_OPERATION",
            "OPERATION_AGGREGATE",
        ],
        "selector_present": False,
    }
    selector_catalog = inventory["checkpoint_selector_catalog"]

    def selector_family(
        catalog_position: int,
        catalog_record: dict[str, Any],
        *,
        measured_roles: list[str],
    ) -> dict[str, Any]:
        selector = catalog_record["selector"]
        return {
            "root_family_kind": "ORDINARY_SELECTOR_BOUND",
            "ordered_instrumentation_mode_attempt_presence_pairs": [["ON", "NON_NULL"]],
            "selector_catalog_position": catalog_position,
            "selector_catalog_name": catalog_record["catalog_name"],
            "checkpoint_selector_id": selector["checkpoint_selector_id"],
            "selector_length": selector["selector_length"],
            "observation_count": selector["selector_length"] + 3,
            "role_sequence_formula": ("ORDINARY_BEFORE_CHECKPOINTS_AFTER_AGGREGATE_V1"),
            "ordered_measured_observation_roles": measured_roles,
            "selector_present": True,
        }

    for offset, operation_kind in enumerate(_OPERATION_KINDS, 4):
        profile = profiles[offset]
        applicable = [
            (position, record)
            for position, record in enumerate(selector_catalog, 1)
            if record["selector"]["operation_kind"] == operation_kind
        ]
        expected_pointers = ["/target_field_registry", "/marker_contract"] + [
            f"/checkpoint_selector_catalog/{position - 1}/selector"
            for position, _ in applicable
        ]
        assert profile["profile_position"] == offset + 1
        assert profile["profile_kind"] == "NON_CHECKPOINT_ROOT_FAMILY"
        assert profile["constraint_scope"] == "FROZEN_ROOT_APPLICATION"
        assert profile["measured_type_name"] == "TargetObservationV2"
        assert profile["operation_kind"] == operation_kind
        assert profile["ordered_source_authority_pointers"] == expected_pointers
        assert profile["ordered_source_authority_ids"] == [
            _authority_id(_resolve_pointer(inventory, pointer))
            for pointer in expected_pointers
        ]
        assert all(profile[field] is None for field in result_null_fields)
        assert profile["ordered_admissible_root_families"] == [
            startup_family,
            selector_free_family,
            *[
                selector_family(
                    position,
                    record,
                    measured_roles=[
                        "BEFORE_OPERATION",
                        "AFTER_OPERATION",
                        "OPERATION_AGGREGATE",
                    ],
                )
                for position, record in applicable
            ],
        ]
        assert (
            profile["application_schedule_formula"]
            == "FINITE_UNION_OF_LISTED_ROOT_FAMILY_SCHEDULES_V1"
        )

    selector_entries = sum(
        item["selector"]["selector_length"] for item in selector_catalog
    )
    assert selector_entries == 80
    checkpoint_profiles = profiles[8:]
    assert len(checkpoint_profiles) == selector_entries * len(_CHECKPOINT_OUTCOMES)
    outcome_bindings = {
        "EXACT_MARKER": ("EXACT_MARKER", None, None),
        "ARTIFACT_BOUND_EXCEEDED": (
            "UNAVAILABLE_MARKER_OBSERVER_FAILURE",
            "ARTIFACT_BOUND_EXCEEDED",
            "CHECKPOINT_PLACEHOLDER_ARTIFACT_BOUND_EXCEEDED",
        ),
        "OBSERVER_INTERNAL_ERROR": (
            "UNAVAILABLE_MARKER_OBSERVER_FAILURE",
            "OBSERVER_INTERNAL_ERROR",
            "CHECKPOINT_PLACEHOLDER_OBSERVER_INTERNAL_ERROR",
        ),
        "SOURCE_CLOCK_UNAVAILABLE": (
            "UNAVAILABLE_MARKER_OBSERVER_FAILURE",
            "SOURCE_CLOCK_UNAVAILABLE",
            "CHECKPOINT_PLACEHOLDER_SOURCE_CLOCK_UNAVAILABLE",
        ),
        "TARGET_BOUNDARY_NOT_REACHED": (
            "UNAVAILABLE_TARGET_BOUNDARY_NOT_REACHED",
            "TARGET_BOUNDARY_NOT_REACHED",
            "CHECKPOINT_PLACEHOLDER_TARGET_BOUNDARY_NOT_REACHED",
        ),
    }
    expected_coordinates: list[tuple[int, dict[str, Any], dict[str, Any], str]] = []
    for catalog_position, catalog_record in enumerate(selector_catalog, 1):
        for entry in catalog_record["selector"]["ordered_entries"]:
            for outcome in _CHECKPOINT_OUTCOMES:
                expected_coordinates.append(
                    (catalog_position, catalog_record, entry, outcome)
                )
    assert len(expected_coordinates) == 400
    for profile, coordinate in zip(
        checkpoint_profiles,
        expected_coordinates,
        strict=True,
    ):
        catalog_position, catalog_record, entry, outcome = coordinate
        selector = catalog_record["selector"]
        binding_status, context_reason, field_reason = outcome_bindings[outcome]
        expected_pointers = [
            "/target_field_registry",
            "/marker_contract",
            f"/checkpoint_selector_catalog/{catalog_position - 1}/selector",
        ]
        assert profile["profile_kind"] == "CHECKPOINT_ROOT_COORDINATE"
        assert profile["constraint_scope"] == "FROZEN_ROOT_APPLICATION"
        assert profile["measured_type_name"] == "TargetObservationV2"
        assert profile["operation_kind"] == selector["operation_kind"]
        assert profile["ordered_source_authority_pointers"] == expected_pointers
        assert profile["ordered_source_authority_ids"] == [
            _authority_id(_resolve_pointer(inventory, pointer))
            for pointer in expected_pointers
        ]
        assert profile["selector_catalog_position"] == catalog_position
        assert profile["selector_catalog_name"] == catalog_record["catalog_name"]
        assert profile["checkpoint_selector_id"] == selector["checkpoint_selector_id"]
        assert (
            profile["checkpoint_selector_entry_id"]
            == entry["checkpoint_selector_entry_id"]
        )
        assert (
            profile["expected_checkpoint_marker_kind"]
            == entry["checkpoint_marker_kind"]
        )
        assert (
            profile["expected_occurrence_index_within_kind"]
            == entry["occurrence_index_within_kind"]
        )
        assert profile["selector_position"] == entry["selector_position"]
        assert profile["checkpoint_outcome"] == outcome
        assert profile["checkpoint_binding_status"] == binding_status
        assert profile["checkpoint_binding_unavailable_reason"] == context_reason
        assert profile["checkpoint_field_unavailable_reason"] == field_reason
        assert profile["ordered_admissible_root_families"] == [
            selector_family(
                catalog_position,
                catalog_record,
                measured_roles=["STABLE_CHECKPOINT"],
            )
        ]
        assert profile["application_schedule_formula"] == (
            "SELECTOR_PRESENT_2N_PLUS_3_CALLS_187N_PLUS_2_EVALS_1872N_PLUS_7_NODES_V1"
        )


def test_validator_accepts_generated_candidate_and_emits_compact_report(
    generated_candidate: tuple[Path, Path, bytes, dict[str, Any]],
) -> None:
    repository, candidate, _, inventory = generated_candidate
    result = _run_validator(repository, candidate)
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout.endswith("\n")
    assert "\n" not in result.stdout[:-1]
    report = json.loads(result.stdout)
    assert type(report) is dict
    assert report["inventory_sha256"] == inventory["inventory_sha256"]
    assert report["maximum_constraint_scope_profile_count"] == 408
    assert report["external_schema_registry_id"] == _STRUCTURAL_REGISTRY_ID


def test_generator_and_validator_are_stdlib_only_and_independent() -> None:
    for relative in (_GENERATOR, _VALIDATOR):
        path = _root() / relative
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
    assert "generate_raw_v8_step2_inventory_v49f" not in validator_source
    generator_raw = (_root() / _GENERATOR).read_bytes()
    assert len(generator_raw) == _GENERATOR_OCTETS
    assert hashlib.sha256(generator_raw).hexdigest() == _GENERATOR_SHA256
    validator_raw = (_root() / _VALIDATOR).read_bytes()
    assert len(validator_raw) == _VALIDATOR_OCTETS
    assert hashlib.sha256(validator_raw).hexdigest() == _VALIDATOR_SHA256


@pytest.mark.parametrize("executable", ("generator", "validator"))
def test_runtime_audit_forbids_production_imports_and_source_reads(
    generated_candidate: tuple[Path, Path, bytes, dict[str, Any]],
    executable: str,
) -> None:
    repository, candidate, _, _ = generated_candidate
    script = _root() / (_GENERATOR if executable == "generator" else _VALIDATOR)
    arguments = (
        [
            str(script),
            "--check",
            "--repository-root",
            str(repository),
            "--output",
            "test_output/candidate.json",
        ]
        if executable == "generator"
        else [
            str(script),
            "--repository-root",
            str(repository),
            "--inventory",
            str(candidate),
        ]
    )
    wrapper = f"""
import os
import runpy
import sys

def audit(event, args):
    if event == "import" and args and str(args[0]).startswith("riskyieldmm"):
        raise AssertionError("production import attempted")
    if event == "open" and args:
        try:
            path = os.path.abspath(os.fspath(args[0]))
        except TypeError:
            return
        if f"{{os.sep}}riskyieldmm{{os.sep}}" in path:
            raise AssertionError("production source read attempted")

sys.addaudithook(audit)
sys.argv = {arguments!r}
runpy.run_path({str(script)!r}, run_name="__main__")
"""
    result = subprocess.run(
        (sys.executable, "-I", "-B", "-c", wrapper),
        cwd=_root(),
        env={
            **os.environ,
            "PYTHONHASHSEED": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""


def _schema_v1_relabel(inventory: dict[str, Any]) -> None:
    inventory["schema_version"] = "riskyieldmm.raw_v8_step2_inventory.v1"


def _schema_v2_relabel(inventory: dict[str, Any]) -> None:
    inventory["schema_version"] = "riskyieldmm.raw_v8_step2_inventory.v2"


def _legacy_registry_member(inventory: dict[str, Any]) -> None:
    inventory["external_type_registry"] = inventory.pop("external_schema_registry_v2")


def _missing_root_member(inventory: dict[str, Any]) -> None:
    inventory.pop("fixture_records")


def _extra_root_member(inventory: dict[str, Any]) -> None:
    inventory["component_status"] = "MAXIMA_ACCEPTED"


def _registry_id_mutation(inventory: dict[str, Any]) -> None:
    inventory["external_schema_registry_v2"]["external_schema_registry_id"] = "0" * 64


def _profile_missing_member(inventory: dict[str, Any]) -> None:
    profile = inventory["operation_contracts"][
        "maximum_constraint_scope_profile_catalog"
    ][0]
    profile.pop("constraint_scope")
    _resign_profile(profile)
    _refresh_profile_digest(inventory)


def _profile_extra_member(inventory: dict[str, Any]) -> None:
    profile = inventory["operation_contracts"][
        "maximum_constraint_scope_profile_catalog"
    ][0]
    profile["maximum_octets"] = 1
    _resign_profile(profile)
    _refresh_profile_digest(inventory)


def _profile_id_mutation(inventory: dict[str, Any]) -> None:
    inventory["operation_contracts"]["maximum_constraint_scope_profile_catalog"][0][
        "maximum_constraint_scope_profile_id"
    ] = "0" * 64
    _refresh_profile_digest(inventory)


def _pointer_id_mismatch(inventory: dict[str, Any]) -> None:
    profile = inventory["operation_contracts"][
        "maximum_constraint_scope_profile_catalog"
    ][0]
    profile["ordered_source_authority_ids"][0] = "0" * 64
    _resign_profile(profile)
    _refresh_profile_digest(inventory)


def _pointer_noncanonical(inventory: dict[str, Any]) -> None:
    profile = inventory["operation_contracts"][
        "maximum_constraint_scope_profile_catalog"
    ][8]
    profile["ordered_source_authority_pointers"][0] = "//target_field_registry"
    _resign_profile(profile)
    _refresh_profile_digest(inventory)


def _pointer_wrong_but_existing(inventory: dict[str, Any]) -> None:
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


def _pointer_order_mutation(inventory: dict[str, Any]) -> None:
    profile = inventory["operation_contracts"][
        "maximum_constraint_scope_profile_catalog"
    ][8]
    profile["ordered_source_authority_pointers"][0:2] = reversed(
        profile["ordered_source_authority_pointers"][0:2]
    )
    profile["ordered_source_authority_ids"][0:2] = reversed(
        profile["ordered_source_authority_ids"][0:2]
    )
    _resign_profile(profile)
    _refresh_profile_digest(inventory)


def _profile_order_mutation(inventory: dict[str, Any]) -> None:
    profiles = inventory["operation_contracts"][
        "maximum_constraint_scope_profile_catalog"
    ]
    profiles[0], profiles[1] = profiles[1], profiles[0]
    for position, profile in enumerate(profiles, 1):
        profile["profile_position"] = position
        _resign_profile(profile)
    _refresh_profile_digest(inventory)


def _checkpoint_outcome_mutation(inventory: dict[str, Any]) -> None:
    profile = inventory["operation_contracts"][
        "maximum_constraint_scope_profile_catalog"
    ][8]
    profile["checkpoint_outcome"] = "ARTIFACT_BOUND_EXCEEDED"
    profile["checkpoint_binding_status"] = "UNAVAILABLE_MARKER_OBSERVER_FAILURE"
    profile["checkpoint_binding_unavailable_reason"] = "ARTIFACT_BOUND_EXCEEDED"
    profile["checkpoint_field_unavailable_reason"] = (
        "CHECKPOINT_PLACEHOLDER_ARTIFACT_BOUND_EXCEEDED"
    )
    _resign_profile(profile)
    _refresh_profile_digest(inventory)


def _root_family_mutation(inventory: dict[str, Any]) -> None:
    profile = inventory["operation_contracts"][
        "maximum_constraint_scope_profile_catalog"
    ][4]
    profile["ordered_admissible_root_families"][0]["observation_count"] = 2
    _resign_profile(profile)
    _refresh_profile_digest(inventory)


def _schedule_mutation(inventory: dict[str, Any]) -> None:
    profile = inventory["operation_contracts"][
        "maximum_constraint_scope_profile_catalog"
    ][8]
    profile["application_schedule_formula"] = (
        "SELECTOR_FREE_2N_PLUS_2_CALLS_187N_PLUS_1_EVALS_1872N_PLUS_4_NODES_V1"
    )
    _resign_profile(profile)
    _refresh_profile_digest(inventory)


def _count_mutation(inventory: dict[str, Any]) -> None:
    inventory["invariants"]["counts"]["maximum_constraint_scope_profile_count"] = 407


def _profile_catalog_cardinality_mutation(inventory: dict[str, Any]) -> None:
    profiles = inventory["operation_contracts"][
        "maximum_constraint_scope_profile_catalog"
    ]
    profiles.pop()
    inventory["invariants"]["counts"]["maximum_constraint_scope_profile_count"] = 407
    inventory["invariants"]["counts"]["maximum_checkpoint_scope_profile_count"] = 399
    _refresh_profile_digest(inventory)


def _profile_position_bool(inventory: dict[str, Any]) -> None:
    profile = inventory["operation_contracts"][
        "maximum_constraint_scope_profile_catalog"
    ][0]
    profile["profile_position"] = True
    _resign_profile(profile)
    _refresh_profile_digest(inventory)


def _profile_position_float(inventory: dict[str, Any]) -> None:
    profile = inventory["operation_contracts"][
        "maximum_constraint_scope_profile_catalog"
    ][0]
    profile["profile_position"] = 1.0
    _resign_profile(profile)
    _refresh_profile_digest(inventory)


def _normative_order_mutation(inventory: dict[str, Any]) -> None:
    documents = inventory["normative_document_inputs"]
    documents[0], documents[1] = documents[1], documents[0]


def _v1_spec_relabel(inventory: dict[str, Any]) -> None:
    inventory["fixture_records"]["operation_specs"]["INGRESS"]["spec_type"] = (
        "INGRESS_OPERATION_SPEC_V1"
    )


_SEMANTIC_MUTATIONS: tuple[tuple[str, Callable[[dict[str, Any]], None]], ...] = (
    ("schema_v1_relabel", _schema_v1_relabel),
    ("schema_v2_relabel", _schema_v2_relabel),
    ("v1_spec_relabel", _v1_spec_relabel),
    ("legacy_external_type_registry", _legacy_registry_member),
    ("missing_root_member", _missing_root_member),
    ("extra_root_member", _extra_root_member),
    ("embedded_registry_id", _registry_id_mutation),
    ("profile_missing_member", _profile_missing_member),
    ("profile_extra_member", _profile_extra_member),
    ("profile_id", _profile_id_mutation),
    ("pointer_id_mismatch", _pointer_id_mismatch),
    ("pointer_noncanonical", _pointer_noncanonical),
    ("pointer_wrong_but_existing", _pointer_wrong_but_existing),
    ("pointer_order", _pointer_order_mutation),
    ("profile_order", _profile_order_mutation),
    ("checkpoint_outcome", _checkpoint_outcome_mutation),
    ("root_family", _root_family_mutation),
    ("schedule", _schedule_mutation),
    ("declared_count", _count_mutation),
    ("catalog_cardinality", _profile_catalog_cardinality_mutation),
    ("profile_position_bool", _profile_position_bool),
    ("profile_position_float", _profile_position_float),
    ("normative_document_order", _normative_order_mutation),
)


@pytest.mark.parametrize(
    ("case", "mutation"),
    _SEMANTIC_MUTATIONS,
    ids=[item[0] for item in _SEMANTIC_MUTATIONS],
)
def test_resigned_semantic_mutations_are_rejected_by_validator(
    generated_candidate: tuple[Path, Path, bytes, dict[str, Any]],
    validator_module: ModuleType,
    tmp_path: Path,
    case: str,
    mutation: Callable[[dict[str, Any]], None],
) -> None:
    del case
    repository, _, _, _ = generated_candidate
    path, _ = _mutated_inventory_path(
        generated_candidate,
        tmp_path,
        mutation,
    )
    _assert_public_rejects(validator_module, repository, path)


def test_inventory_hash_mutation_is_rejected_before_semantic_acceptance(
    generated_candidate: tuple[Path, Path, bytes, dict[str, Any]],
    validator_module: ModuleType,
    tmp_path: Path,
) -> None:
    repository, _, _, _ = generated_candidate
    path, _ = _mutated_inventory_path(
        generated_candidate,
        tmp_path,
        lambda inventory: inventory.__setitem__("inventory_sha256", "0" * 64),
        resign=False,
    )
    _assert_public_rejects(validator_module, repository, path)


def test_v2_shape_relabelled_as_v3_is_rejected(
    generated_candidate: tuple[Path, Path, bytes, dict[str, Any]],
    validator_module: ModuleType,
    tmp_path: Path,
) -> None:
    repository, _, _, source = generated_candidate
    legacy = copy.deepcopy(source)
    legacy["external_type_registry"] = legacy.pop("external_schema_registry_v2")[
        "ordered_external_type_descriptors"
    ]
    legacy["operation_contracts"].pop("maximum_constraint_scope_profile_catalog")
    legacy["schema_version"] = _SCHEMA_VERSION
    _resign_inventory(legacy)
    path = repository / "mutations" / tmp_path.name / "v2-relabel.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_pretty(legacy))
    _assert_public_rejects(validator_module, repository, path)


def test_raw_duplicate_noncanonical_nonfinite_and_depth_inputs_reject_cleanly(
    generated_candidate: tuple[Path, Path, bytes, dict[str, Any]],
) -> None:
    repository, _, raw, inventory = generated_candidate
    directory = repository / "raw-invalid"
    directory.mkdir()
    duplicate = directory / "duplicate.json"
    duplicate.write_bytes(
        b'{\n  "schema_version": "riskyieldmm.raw_v8_step2_inventory.v3",\n' + raw[2:]
    )
    minified = directory / "minified.json"
    minified.write_bytes(_canonical(inventory))
    nonfinite = directory / "nonfinite.json"
    nonfinite.write_bytes(b'{"profile_position":NaN}\n')
    deep = directory / "deep.json"
    deep.write_bytes(b'{"x":' + b"[" * 300 + b"0" + b"]" * 300 + b"}\n")

    for path in (duplicate, minified, nonfinite, deep):
        _assert_controlled_rejection(
            _run_validator(repository, path),
            prefix=_VALIDATOR_ERROR_PREFIX,
        )


def test_validator_rejects_oversize_outside_path_and_symlink_without_traceback(
    generated_candidate: tuple[Path, Path, bytes, dict[str, Any]],
    tmp_path: Path,
) -> None:
    repository, candidate, _, _ = generated_candidate
    oversized = repository / "oversized.json"
    with oversized.open("wb") as stream:
        stream.truncate(16_777_216)
    _assert_controlled_rejection(
        _run_validator(repository, oversized),
        prefix=_VALIDATOR_ERROR_PREFIX,
    )

    outside = tmp_path / "outside.json"
    shutil.copyfile(candidate, outside)
    _assert_controlled_rejection(
        _run_validator(repository, outside),
        prefix=_VALIDATOR_ERROR_PREFIX,
    )

    symlink = repository / "inventory-link.json"
    symlink.symlink_to(candidate)
    _assert_controlled_rejection(
        _run_validator(repository, symlink),
        prefix=_VALIDATOR_ERROR_PREFIX,
    )


def test_generator_rechecks_normative_and_registry_sources_after_build(
    tmp_path: Path,
    generator_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for source_relative in (
        _NORMATIVE_INPUTS[2][1],
        _STRUCTURAL_REGISTRY,
    ):
        repository = _copy_authority_repository(
            tmp_path / source_relative.split("/")[-1]
        )
        source = repository / source_relative
        original = generator_module._operation_contracts
        mutated = False

        def mutate_then_continue(
            *args: Any,
            _source: Path = source,
            _original: Callable[..., dict[str, Any]] = original,
            **kwargs: Any,
        ) -> dict[str, Any]:
            nonlocal mutated
            if not mutated:
                _source.write_bytes(_source.read_bytes() + b"\n")
                mutated = True
            return _original(*args, **kwargs)

        with monkeypatch.context() as context:
            context.setattr(
                generator_module,
                "_operation_contracts",
                mutate_then_continue,
            )
            with pytest.raises(generator_module.InventoryError):
                generator_module._build_inventory(repository)
        assert mutated


def test_validator_source_recheck_is_on_the_acceptance_path_and_detects_mutation(
    tmp_path: Path,
    generated_candidate: tuple[Path, Path, bytes, dict[str, Any]],
    validator_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, candidate_raw, _ = generated_candidate
    repository = _copy_authority_repository(tmp_path / "repository")
    candidate = repository / "candidate.json"
    candidate.write_bytes(candidate_raw)
    source = repository / _NORMATIVE_INPUTS[3][1]
    original_recheck = validator_module._revalidate_source_snapshot
    called = False

    def mutate_then_recheck(
        *,
        repository_root: Path,
        expected_source_bytes: dict[str, bytes],
    ) -> None:
        nonlocal called
        called = True
        source.write_bytes(source.read_bytes() + b"\n")
        original_recheck(
            repository_root=repository_root,
            expected_source_bytes=expected_source_bytes,
        )

    monkeypatch.setattr(
        validator_module,
        "_revalidate_source_snapshot",
        mutate_then_recheck,
    )
    _assert_public_rejects(validator_module, repository, candidate)
    assert called


def test_atomic_writer_publishes_verified_bytes_and_removes_temporary(
    tmp_path: Path,
    generator_module: ModuleType,
) -> None:
    repository = (tmp_path / "repository").resolve()
    output_parent = repository / "output"
    output_parent.mkdir(parents=True)
    output = output_parent / "candidate.json"
    output.write_bytes(b"old-authority\n")
    old_identity = output.stat().st_ino
    rendered = b'{\n  "complete": true\n}\n'

    generator_module._atomic_write_repository_output(
        repository,
        output,
        rendered,
    )

    metadata = output.stat()
    assert output.read_bytes() == rendered
    assert metadata.st_ino != old_identity
    assert metadata.st_mode & 0o777 == 0o644
    assert list(output_parent.glob(".candidate.json.tmp.*")) == []


def test_atomic_writer_failure_preserves_old_target_and_removes_partial_temp(
    tmp_path: Path,
    generator_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = (tmp_path / "repository").resolve()
    output_parent = repository / "output"
    output_parent.mkdir(parents=True)
    output = output_parent / "candidate.json"
    original = b"existing-complete-authority\n"
    output.write_bytes(original)
    real_write = generator_module.os.write
    call_count = 0

    def partial_then_fail(descriptor: int, value: bytes) -> int:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return real_write(descriptor, value[:17])
        raise OSError("injected write failure")

    monkeypatch.setattr(generator_module.os, "write", partial_then_fail)
    with pytest.raises(OSError, match="injected write failure"):
        generator_module._atomic_write_repository_output(
            repository,
            output,
            b"replacement" * 10_000,
        )

    assert output.read_bytes() == original
    assert list(output_parent.glob(".candidate.json.tmp.*")) == []


def test_atomic_writer_rechecks_concurrent_target_before_replace(
    tmp_path: Path,
    generator_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = (tmp_path / "repository").resolve()
    output_parent = repository / "output"
    output_parent.mkdir(parents=True)
    output = output_parent / "candidate.json"
    output.write_bytes(b"initial-target\n")
    concurrent = b"concurrent-writer-won\n"
    original_fingerprint = generator_module._output_entry_fingerprint
    call_count = 0

    def mutate_on_recheck(parent_descriptor: int, leaf_name: str) -> Any:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            output.write_bytes(concurrent)
        return original_fingerprint(parent_descriptor, leaf_name)

    monkeypatch.setattr(
        generator_module,
        "_output_entry_fingerprint",
        mutate_on_recheck,
    )
    with pytest.raises(generator_module.InventoryError):
        generator_module._atomic_write_repository_output(
            repository,
            output,
            b"our-replacement\n",
        )

    assert call_count == 2
    assert output.read_bytes() == concurrent
    assert list(output_parent.glob(".candidate.json.tmp.*")) == []


def test_atomic_writer_rejects_ancestor_swap_without_writing_outside(
    tmp_path: Path,
    generator_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = (tmp_path / "repository").resolve()
    output_parent = repository / "output"
    output_parent.mkdir(parents=True)
    output = output_parent / "candidate.json"
    original = b"old-target\n"
    output.write_bytes(original)
    detached_parent = repository / "detached-output"
    outside_parent = tmp_path / "outside"
    outside_parent.mkdir()
    original_rewalk = generator_module._current_repository_directory_fingerprint
    swapped = False

    def swap_then_rewalk(
        repository_root: Path,
        relative_parts: tuple[str, ...],
        *,
        label: str,
    ) -> tuple[int, int, int]:
        nonlocal swapped
        if not swapped:
            output_parent.rename(detached_parent)
            output_parent.symlink_to(outside_parent, target_is_directory=True)
            swapped = True
        return original_rewalk(
            repository_root,
            relative_parts,
            label=label,
        )

    monkeypatch.setattr(
        generator_module,
        "_current_repository_directory_fingerprint",
        swap_then_rewalk,
    )
    with pytest.raises(generator_module.InventoryError):
        generator_module._atomic_write_repository_output(
            repository,
            output,
            b"replacement\n",
        )

    assert swapped
    assert not (outside_parent / "candidate.json").exists()
    assert (detached_parent / "candidate.json").read_bytes() == original
    assert list(detached_parent.glob(".candidate.json.tmp.*")) == []


def test_bounded_reader_rejects_ancestor_swap_after_bound_read(
    tmp_path: Path,
    generator_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = (tmp_path / "repository").resolve()
    input_parent = repository / "input"
    input_parent.mkdir(parents=True)
    source = input_parent / "authority.json"
    source.write_bytes(b'{"authority":true}\n')
    detached_parent = repository / "detached-input"
    outside_parent = tmp_path / "outside"
    outside_parent.mkdir()
    real_read = generator_module.os.read
    swapped = False

    def read_then_swap(descriptor: int, maximum: int) -> bytes:
        nonlocal swapped
        result = real_read(descriptor, maximum)
        if result and not swapped:
            input_parent.rename(detached_parent)
            input_parent.symlink_to(outside_parent, target_is_directory=True)
            swapped = True
        return result

    monkeypatch.setattr(generator_module.os, "read", read_then_swap)
    with pytest.raises(generator_module.InventoryError):
        generator_module._bounded_repository_read(
            repository,
            "input/authority.json",
            maximum_octets=1_024,
        )

    assert swapped
    assert not (outside_parent / "authority.json").exists()


def test_generator_check_rejects_changed_document_and_recovers_after_restore(
    tmp_path: Path,
) -> None:
    repository = _copy_authority_repository(tmp_path / "repository")
    (repository / "test_output").mkdir()
    relative_output = "test_output/candidate.json"
    written = _run_generator(
        repository,
        output=relative_output,
        mode="--write",
    )
    assert written.returncode == 0, written.stderr
    document = repository / _NORMATIVE_INPUTS[1][1]
    original = document.read_bytes()
    document.write_bytes(original + b"\n")
    _assert_controlled_rejection(
        _run_generator(
            repository,
            output=relative_output,
            mode="--check",
        ),
        prefix=_GENERATOR_ERROR_PREFIX,
    )
    document.write_bytes(original)
    checked = _run_generator(
        repository,
        output=relative_output,
        mode="--check",
    )
    assert checked.returncode == 0, checked.stderr


def test_generator_rejects_symlinked_input_and_output_paths_cleanly(
    tmp_path: Path,
) -> None:
    repository = _copy_authority_repository(tmp_path / "repository")
    (repository / "test_output").mkdir()
    document = repository / _NORMATIVE_INPUTS[0][1]
    outside_document = tmp_path / "outside.md"
    outside_document.write_bytes(document.read_bytes())
    document.unlink()
    document.symlink_to(outside_document)
    _assert_controlled_rejection(
        _run_generator(
            repository,
            output="test_output/candidate.json",
            mode="--write",
        ),
        prefix=_GENERATOR_ERROR_PREFIX,
    )

    document.unlink()
    shutil.copyfile(outside_document, document)
    real_output = repository / "test_output/real.json"
    real_output.write_text("{}\n", encoding="utf-8")
    output_link = repository / "test_output/link.json"
    output_link.symlink_to(real_output)
    _assert_controlled_rejection(
        _run_generator(
            repository,
            output="test_output/link.json",
            mode="--write",
        ),
        prefix=_GENERATOR_ERROR_PREFIX,
    )


def test_generator_rejects_authority_input_as_output_without_mutation(
    tmp_path: Path,
) -> None:
    repository = _copy_authority_repository(tmp_path / "repository")
    authority_relative = _NORMATIVE_INPUTS[2][1]
    authority = repository / authority_relative
    before = authority.read_bytes()

    _assert_controlled_rejection(
        _run_generator(
            repository,
            output=authority_relative,
            mode="--write",
        ),
        prefix=_GENERATOR_ERROR_PREFIX,
    )

    assert authority.read_bytes() == before
    assert list(authority.parent.glob(f".{authority.name}.tmp.*")) == []


def test_generator_rejects_symlink_loop_repository_root_without_traceback(
    tmp_path: Path,
) -> None:
    first = tmp_path / "repository-loop-a"
    second = tmp_path / "repository-loop-b"
    first.symlink_to(second, target_is_directory=True)
    second.symlink_to(first, target_is_directory=True)

    _assert_controlled_rejection(
        _run_generator(
            first,
            output="test_output/candidate.json",
            mode="--write",
        ),
        prefix=_GENERATOR_ERROR_PREFIX,
    )

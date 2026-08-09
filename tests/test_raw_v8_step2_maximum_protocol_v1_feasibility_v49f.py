from __future__ import annotations

import copy
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

_AUDIT_RELATIVE_PATH = (
    "scripts/tests/audit_raw_v8_step2_maximum_protocol_v1_feasibility_v49f.py"
)
_REGISTRY_RELATIVE_PATH = (
    "scripts/tests/raw_v8_step2_external_schema_v2_structural_registry_v49f.json"
)


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def audit_module() -> ModuleType:
    path = _repository_root() / _AUDIT_RELATIVE_PATH
    spec = importlib.util.spec_from_file_location(
        "maximum_protocol_v1_feasibility", path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def registry() -> dict[str, object]:
    with (_repository_root() / _REGISTRY_RELATIVE_PATH).open(
        "r", encoding="utf-8"
    ) as stream:
        value = json.load(stream)
    assert type(value) is dict
    return value


def test_v1_feasibility_audit_proves_exact_presearch_cap_contradiction(
    audit_module: ModuleType,
) -> None:
    report = audit_module.audit(_repository_root())

    assert report == {
        "audit_result": "PASS",
        "finding_id": ("RAW_V8_STEP2_MAXIMUM_PROTOCOL_V1_PRESEARCH_CAP_CONTRADICTION"),
        "protocol_decision": "REJECTED",
        "protocol_octets": 246_093,
        "protocol_sha256": (
            "b3b39b3cb15caa450d9974925db9b5f0b91dd5832a462d2a8687dc19a50c4409"
        ),
        "registry_octets": 1_469_663,
        "registry_sha256": (
            "9160297ff316c5931737c92f8b359f0a1e2ec22f0aa996ef3b09cf830dc96bf3"
        ),
        "registry_semantic_id": (
            "5dc95a3e99c5646e912b6a7e9c3970cf2489d560ea890b0a19d38af4c51c2140"
        ),
        "intrinsic_row_position": 62,
        "type_name": "TargetFieldRegistryV1",
        "external_type_descriptor_position": 48,
        "outer_fixed_descriptor_occurrence_count": 185,
        "inner_array_cardinality_coordinate_count": 185,
        "inner_text_coordinate_count": 94_720,
        "component_choice_coordinate_lower_bound": 94_905,
        "prefix_proof_node_lower_bound": 94_905,
        "tie_break_proof_node_lower_bound": 94_906,
        "maximum_proof_depth_lower_bound": 94_906,
        "seed_component_choice_coordinate_cap": 65_536,
        "seed_proof_node_cap": 65_536,
        "seed_maximum_proof_depth_cap": 65_536,
        "component_coordinate_cap_excess": 29_369,
        "proof_node_cap_excess_before_base_nodes": 29_369,
        "tie_break_proof_node_cap_excess_before_descriptor_and_root_nodes": 29_370,
        "maximum_proof_depth_cap_excess_before_descriptor_and_root_nodes": 29_370,
    }


def test_v1_feasibility_cli_is_deterministic_and_machine_readable() -> None:
    command = (
        sys.executable,
        str(_repository_root() / _AUDIT_RELATIVE_PATH),
        "--repository-root",
        str(_repository_root()),
    )
    first = subprocess.run(command, check=False, capture_output=True)
    second = subprocess.run(command, check=False, capture_output=True)

    assert first.returncode == second.returncode == 0
    assert first.stderr == second.stderr == b""
    assert first.stdout == second.stdout
    assert first.stdout.endswith(b"\n") and first.stdout.count(b"\n") == 1
    report = json.loads(first.stdout)
    assert report["audit_result"] == "PASS"
    assert report["protocol_decision"] == "REJECTED"


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("outer_descriptor_position", "external descriptor position differs"),
        ("outer_type_role", "target registry record/type role differs"),
        ("outer_member_role", "descriptors member role differs"),
        ("outer_cardinality", "descriptor-array authority differs"),
        ("inner_type_role", "target descriptor record/type role differs"),
        ("inner_member_role", "value-shape-key member role differs"),
        ("inner_cardinality", "value-shape-key array authority differs"),
        ("text_language", "value-shape-key text authority differs"),
        ("language_kind", "raw canonical JSON string language authority differs"),
    ),
)
def test_lower_bound_derivation_rejects_authority_shape_drift(
    audit_module: ModuleType,
    registry: dict[str, object],
    mutation: str,
    message: str,
) -> None:
    candidate = copy.deepcopy(registry)
    schemas = {
        item["value_schema_id"]: item for item in candidate["value_schema_catalog"]
    }
    descriptors = {
        item["type_name"]: item
        for item in candidate["ordered_external_type_descriptors"]
    }
    target_registry = descriptors["TargetFieldRegistryV1"]
    target_descriptor = descriptors["CapacityMeasurementTargetFieldDescriptorV1"]
    outer_member = next(
        item
        for item in target_registry["record_member_descriptors"]
        if item["member_name"] == "descriptors"
    )
    inner_member = next(
        item
        for item in target_descriptor["record_member_descriptors"]
        if item["member_name"] == "value_shape_keys"
    )
    outer_schema = schemas[outer_member["value_schema_id"]]
    inner_schema = schemas[inner_member["value_schema_id"]]
    text_schema = schemas[inner_schema["array_item_value_schema_id"]]

    if mutation == "outer_descriptor_position":
        ordered = candidate["ordered_external_type_descriptors"]
        target_index = next(
            position
            for position, item in enumerate(ordered)
            if item["type_name"] == "TargetFieldRegistryV1"
        )
        ordered[target_index - 1], ordered[target_index] = (
            ordered[target_index],
            ordered[target_index - 1],
        )
    elif mutation == "outer_type_role":
        target_registry["type_role"] = "NESTED"
    elif mutation == "outer_member_role":
        outer_member["member_role"] = "NESTED_PAYLOAD"
    elif mutation == "outer_cardinality":
        outer_schema["array_maximum_items"] = 184
    elif mutation == "inner_type_role":
        target_descriptor["type_role"] = "STANDALONE"
    elif mutation == "inner_member_role":
        inner_member["member_role"] = "IDENTITY_PAYLOAD"
    elif mutation == "inner_cardinality":
        inner_schema["array_maximum_items"] = 511
    elif mutation == "text_language":
        text_schema["text_language_id"] = "0" * 64
    else:
        language = next(
            item
            for item in candidate["text_language_catalog"]
            if item["text_language_id"] == audit_module.RAW_STRING_LANGUAGE_ID
        )
        language["language_kind"] = "LITERAL"

    with pytest.raises(audit_module.FeasibilityAuditError, match=message):
        audit_module.derive_target_registry_plan_lower_bound(candidate)


@pytest.mark.parametrize(
    "parameter_name",
    (
        "ascii_dfa_id",
        "decimal_maximum",
        "maximum_decoded_octets",
        "maximum_utf8_octets",
        "minimum_decoded_octets",
        "minimum_utf8_octets",
        "unicode_identifier_profile_id",
    ),
)
@pytest.mark.parametrize("mutation_kind", ("non_null", "missing"))
def test_lower_bound_derivation_requires_each_unused_raw_string_parameter_to_be_null(
    audit_module: ModuleType,
    registry: dict[str, object],
    parameter_name: str,
    mutation_kind: str,
) -> None:
    candidate = copy.deepcopy(registry)
    language = next(
        item
        for item in candidate["text_language_catalog"]
        if item["text_language_id"] == audit_module.RAW_STRING_LANGUAGE_ID
    )
    if mutation_kind == "non_null":
        language[parameter_name] = 0
    else:
        del language[parameter_name]

    with pytest.raises(
        audit_module.FeasibilityAuditError,
        match="unused language parameter differs",
    ):
        audit_module.derive_target_registry_plan_lower_bound(candidate)


@pytest.mark.parametrize(
    "type_name",
    ("TargetFieldRegistryV1", "CapacityMeasurementTargetFieldDescriptorV1"),
)
def test_member_resolution_rejects_non_object_catalog_entries_without_type_error(
    audit_module: ModuleType,
    registry: dict[str, object],
    type_name: str,
) -> None:
    candidate = copy.deepcopy(registry)
    descriptor = next(
        item
        for item in candidate["ordered_external_type_descriptors"]
        if item["type_name"] == type_name
    )
    descriptor["record_member_descriptors"].insert(0, None)

    with pytest.raises(
        audit_module.FeasibilityAuditError,
        match="member descriptor differs",
    ):
        audit_module.derive_target_registry_plan_lower_bound(candidate)


@pytest.mark.parametrize(
    ("cap_name", "replacement", "message"),
    (
        (
            "SEED_COMPONENT_COORDINATE_CAP",
            94_905,
            "component-coordinate lower bound no longer exceeds",
        ),
        (
            "SEED_PROOF_NODE_CAP",
            94_906,
            "tie-break proof-node lower bound no longer exceeds",
        ),
        (
            "SEED_MAXIMUM_PROOF_DEPTH_CAP",
            94_906,
            "maximum-proof-depth lower bound no longer exceeds",
        ),
    ),
)
def test_audit_rejects_when_an_exact_lower_bound_no_longer_exceeds_its_cap(
    audit_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    cap_name: str,
    replacement: int,
    message: str,
) -> None:
    monkeypatch.setattr(audit_module, cap_name, replacement)

    with pytest.raises(audit_module.FeasibilityAuditError, match=message):
        audit_module.audit(_repository_root())


def test_pinned_reader_opens_fifo_leaf_nonblocking_before_rejecting_it(
    audit_module: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    nonblocking_flag = getattr(os, "O_NONBLOCK", 0)
    if not nonblocking_flag or not hasattr(os, "mkfifo"):
        pytest.skip("FIFO nonblocking file-open semantics are unavailable")

    fifo = tmp_path / "authority.json"
    os.mkfifo(fifo)
    actual_open = os.open
    observed_leaf_flags: list[int] = []

    def guarded_open(
        path: object,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        if dir_fd is not None:
            assert flags & nonblocking_flag
            observed_leaf_flags.append(flags)
        return actual_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(audit_module.os, "open", guarded_open)
    with pytest.raises(audit_module.FeasibilityAuditError, match="not a regular file"):
        audit_module._read_pinned_regular_file(
            Path("authority.json"),
            repository_root=tmp_path,
            expected_octets=0,
            expected_sha256=audit_module._sha256(b""),
            label="FIFO authority",
        )

    assert len(observed_leaf_flags) == 1

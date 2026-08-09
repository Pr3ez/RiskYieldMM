from __future__ import annotations

import ast
import copy
import dataclasses
import hashlib
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

_VALIDATOR_RELATIVE_PATH = (
    "scripts/tests/validate_raw_v8_step2_external_schema_v2_topology_v49f.py"
)
_LEDGER_RELATIVE_PATH = (
    "scripts/tests/raw_v8_step2_external_schema_v2_topology_ledger_v49f.json"
)
_PRODUCTION_MODULE = "riskyieldmm.trading.physical_transport_capacity_contracts_v49f_v8"
_TOPOLOGY_LEDGER_SHA256 = (
    "17b6355afcc23438efad97967180fb7e6292b7dd3d72d8b91a0320bfb9696778"
)
_TOPOLOGY_LEDGER_OCTETS = 257_432
_ERROR_PREFIX = "Raw-V8 Step-2 external-schema V2 topology error: "
_EXPECTED_EXCLUSIONS = [
    "CapacityMeasurementClockSpanV1",
    "CapacityMeasurementTargetObservationContextV1",
    "CapacityMeasurementTargetObservationV1",
    "CapacityMeasurementTargetObservationRootV1",
    "_HistoricalCapacityMeasurementLocalShutdownResultEvidenceV1V49FV8",
]
_NON_CAPACITY_RUNTIME_NAMES = {
    "CheckpointSelectorEntryV1": ("CapacityMeasurementCheckpointSelectorEntryV49FV8"),
    "CheckpointSelectorV1": "CapacityMeasurementCheckpointSelectorV49FV8",
    "MarkerContractV1": "CapacityMeasurementMarkerContractV49FV8",
    "OperationCounterSnapshotSchemaV1": (
        "CapacityMeasurementOperationCounterSnapshotSchemaV49FV8"
    ),
    "OperationCounterSnapshotV1": ("CapacityMeasurementOperationCounterSnapshotV49FV8"),
    "SourceErrorDetailV1": "CapacityMeasurementSourceErrorDetailV49FV8",
    "TargetFieldObservationV1": ("CapacityMeasurementTargetFieldObservationV49FV8"),
    "TargetFieldRegistryV1": "CapacityMeasurementTargetFieldRegistryV49FV8",
    "TargetObservationClockSpanV2": (
        "CapacityMeasurementTargetObservationClockSpanV2V49FV8"
    ),
    "TargetObservationContextV2": (
        "CapacityMeasurementTargetObservationContextV2V49FV8"
    ),
    "TargetObservationRootV2": ("CapacityMeasurementTargetObservationRootV2V49FV8"),
    "TargetObservationV2": "CapacityMeasurementTargetObservationV2V49FV8",
}
_SPECIAL_RUNTIME_NAMES = {
    "CapacityMeasurementDueDecisionClockEvidenceV1": (
        "CapacityMeasurementAckDueDecisionClockEvidenceV49FV8"
    ),
}


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _ledger_path() -> Path:
    return _repository_root() / _LEDGER_RELATIVE_PATH


def _load_ledger() -> dict[str, Any]:
    value = json.loads(_ledger_path().read_text(encoding="utf-8"))
    assert type(value) is dict
    return value


def _canonical_pretty_bytes(value: Any) -> bytes:
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


def _run_validator(path: Path) -> subprocess.CompletedProcess[str]:
    validator = _repository_root() / _VALIDATOR_RELATIVE_PATH
    return subprocess.run(
        (sys.executable, "-I", "-B", str(validator), "--ledger", str(path)),
        cwd=_repository_root(),
        env={
            **os.environ,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
        },
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _write_ledger(path: Path, value: dict[str, Any]) -> Path:
    path.write_bytes(_canonical_pretty_bytes(value))
    return path


def _assert_controlled_rejection(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.startswith(_ERROR_PREFIX)
    assert result.stderr.endswith("\n")
    assert "Traceback" not in result.stderr


def _descriptor(ledger: dict[str, Any], type_name: str) -> dict[str, Any]:
    return next(
        descriptor
        for descriptor in ledger["type_descriptors"]
        if descriptor["type_name"] == type_name
    )


def _runtime_class_name(type_name: str) -> str:
    if type_name in _SPECIAL_RUNTIME_NAMES:
        return _SPECIAL_RUNTIME_NAMES[type_name]
    if type_name in _NON_CAPACITY_RUNTIME_NAMES:
        return _NON_CAPACITY_RUNTIME_NAMES[type_name]
    assert type_name.startswith("CapacityMeasurement")
    base = type_name
    if base.endswith(("V1", "V2")):
        base = base[:-2]
    return base + "V49FV8"


def _external_name_by_runtime(ledger: dict[str, Any]) -> dict[str, str]:
    return {
        _runtime_class_name(descriptor["type_name"]): descriptor["type_name"]
        for descriptor in ledger["type_descriptors"]
        if descriptor["type_form"] == "RECORD"
    }


def test_frozen_topology_ledger_and_independent_report() -> None:
    raw = _ledger_path().read_bytes()
    assert len(raw) == _TOPOLOGY_LEDGER_OCTETS
    assert hashlib.sha256(raw).hexdigest() == _TOPOLOGY_LEDGER_SHA256
    assert raw == _canonical_pretty_bytes(json.loads(raw))

    result = _run_validator(_ledger_path())
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert result.stderr == ""
    report = json.loads(result.stdout)
    assert report == {
        "component_status": "TOPOLOGY_ONLY_NOT_FULL_REGISTRY",
        "concrete_record_count": 49,
        "ledger_octets": _TOPOLOGY_LEDGER_OCTETS,
        "ledger_path": str(_ledger_path()),
        "ledger_sha256": _TOPOLOGY_LEDGER_SHA256,
        "maximum_type_graph_depth": 5,
        "nested_type_count": 36,
        "record_member_path_count": 421,
        "standalone_record_count": 16,
        "tagged_union_count": 3,
        "total_type_count": 52,
        "typed_reference_path_count": 26,
        "union_binding_path_count": 8,
    }


def test_topology_marker_counts_exclusions_and_non_registry_boundary() -> None:
    ledger = _load_ledger()
    assert ledger["component_status"] == "TOPOLOGY_ONLY_NOT_FULL_REGISTRY"
    assert ledger["concrete_record_count"] == 49
    assert ledger["tagged_union_count"] == 3
    assert ledger["standalone_record_count"] == 16
    assert ledger["nested_type_count"] == 36
    assert ledger["total_type_count"] == 52
    assert ledger["excluded_production_type_names"] == _EXPECTED_EXCLUSIONS
    assert {descriptor["type_form"] for descriptor in ledger["type_descriptors"]} == {
        "RECORD",
        "TAGGED_UNION",
    }
    assert {
        descriptor["type_name"] for descriptor in ledger["type_descriptors"]
    }.isdisjoint(_EXPECTED_EXCLUSIONS)
    assert "value_schema_catalog" not in ledger
    assert "text_language_catalog" not in ledger
    assert "external_schema_registry_id" not in ledger


def test_validator_is_stdlib_only_and_independent() -> None:
    path = _repository_root() / _VALIDATOR_RELATIVE_PATH
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_roots = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_roots.update(
        node.module.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    )
    assert imported_roots <= {
        "__future__",
        "argparse",
        "collections",
        "hashlib",
        "json",
        "os",
        "pathlib",
        "stat",
        "sys",
        "typing",
    }
    lowered = source.lower()
    assert "import riskyieldmm" not in lowered
    assert "generate_raw_v8_step2_inventory_v49f" not in lowered
    assert "external_schema_v2_foundation" not in lowered


def test_production_records_match_authoritative_topology() -> None:
    ledger = _load_ledger()
    production = importlib.import_module(_PRODUCTION_MODULE)
    for descriptor in ledger["type_descriptors"]:
        if descriptor["type_form"] != "RECORD":
            continue
        runtime_class = getattr(
            production,
            _runtime_class_name(descriptor["type_name"]),
        )
        expected_fields = [
            member["member_name"] for member in descriptor["member_topology"]
        ]
        if descriptor["type_role"] == "STANDALONE":
            expected_fields = expected_fields[3:]
            assert runtime_class._DOMAIN == descriptor["described_record_domain"]
            assert runtime_class._IDENTITY_FIELD == descriptor["identity_field"]
        assert [field.name for field in dataclasses.fields(runtime_class)] == (
            expected_fields
        )
        assert runtime_class._MAXIMUM_BYTES == descriptor["codec_octet_limit"]
        is_exclusive = getattr(
            runtime_class,
            "_MAXIMUM_BYTES_IS_EXCLUSIVE",
            False,
        )
        assert is_exclusive == (descriptor["codec_byte_bound_relation"] == "LT")


def test_production_union_tables_match_exact_union_alternatives() -> None:
    ledger = _load_ledger()
    production = importlib.import_module(_PRODUCTION_MODULE)
    external_by_runtime = _external_name_by_runtime(ledger)

    spec_union = _descriptor(
        ledger,
        "CapacityMeasurementOperationSpecBody",
    )["tagged_union_topology"]
    observed_specs = sorted(
        (
            kind.value,
            tag.value,
            external_by_runtime[body.__name__],
        )
        for kind, (tag, body) in production._SPEC_TAG_MATRIX_V49FV8.items()
    )
    expected_specs = sorted(
        (
            alternative["ordered_discriminator_literals"][0]["text_value"],
            alternative["ordered_discriminator_literals"][1]["text_value"],
            alternative["referenced_type_name"],
        )
        for alternative in spec_union["ordered_alternatives"]
    )
    assert observed_specs == expected_specs

    result_union = _descriptor(
        ledger,
        "CapacityMeasurementOperationResultBody",
    )["tagged_union_topology"]
    observed_results = sorted(
        (
            kind.value,
            tag.value,
            external_by_runtime[body.__name__],
        )
        for kind, (tag, body) in production._RESULT_TAG_MATRIX_V49FV8.items()
    )
    expected_results = sorted(
        (
            alternative["ordered_discriminator_literals"][0]["text_value"],
            alternative["ordered_discriminator_literals"][1]["text_value"],
            alternative["referenced_type_name"],
        )
        for alternative in result_union["ordered_alternatives"]
    )
    assert observed_results == expected_results

    value_union = _descriptor(
        ledger,
        "CapacityMeasurementTargetValue",
    )["tagged_union_topology"]
    observed_values = sorted(
        (kind.value, external_by_runtime[body.__name__])
        for kind, body in production._RAW_V8_VALUE_CLASS_BY_KIND_V49F.items()
    )
    expected_values = sorted(
        (
            alternative["ordered_discriminator_literals"][0]["text_value"],
            alternative["referenced_type_name"],
        )
        for alternative in value_union["ordered_alternatives"]
    )
    assert observed_values == expected_values


def test_production_retains_but_topology_excludes_five_legacy_nodes() -> None:
    production = importlib.import_module(_PRODUCTION_MODULE)
    runtime_exclusions = (
        "CapacityMeasurementClockSpanV49FV8",
        "CapacityMeasurementTargetObservationContextV49FV8",
        "CapacityMeasurementTargetObservationV49FV8",
        "CapacityMeasurementTargetObservationRootV49FV8",
        "_HistoricalCapacityMeasurementLocalShutdownResultEvidenceV1V49FV8",
    )
    assert all(hasattr(production, name) for name in runtime_exclusions)
    ledger_text = _ledger_path().read_text(encoding="utf-8")
    for excluded_name in _EXPECTED_EXCLUSIONS:
        assert ledger_text.count(excluded_name) == 1


def _mutated_ledger(case: str) -> dict[str, Any]:
    ledger = copy.deepcopy(_load_ledger())
    first_record = ledger["type_descriptors"][0]
    first_union = ledger["type_descriptors"][49]
    selector = _descriptor(ledger, "CheckpointSelectorV1")
    context = _descriptor(ledger, "TargetObservationContextV2")
    if case == "missing_root_member":
        ledger.pop("component_status")
    elif case == "extra_root_member":
        ledger["unexpected"] = None
    elif case == "status_promotion":
        ledger["component_status"] = "EXTERNAL_SCHEMA_REGISTRY_V2"
    elif case == "ledger_version_drift":
        ledger["topology_ledger_version"] += ".drift"
    elif case == "record_count_drift":
        ledger["concrete_record_count"] = 48
    elif case == "standalone_count_drift":
        ledger["standalone_record_count"] = 15
    elif case == "nested_count_drift":
        ledger["nested_type_count"] = 35
    elif case == "union_count_drift":
        ledger["tagged_union_count"] = 2
    elif case == "total_count_boolean":
        ledger["total_type_count"] = True
    elif case == "exclusion_missing":
        ledger["excluded_production_type_names"].pop()
    elif case == "exclusion_extra":
        ledger["excluded_production_type_names"].append("AnotherLegacyTypeV1")
    elif case == "exclusion_order_swap":
        ledger["excluded_production_type_names"][0:2] = reversed(
            ledger["excluded_production_type_names"][0:2]
        )
    elif case == "excluded_type_reintroduced":
        clone = copy.deepcopy(first_record)
        clone["type_name"] = ledger["excluded_production_type_names"][0]
        ledger["type_descriptors"].append(clone)
    elif case == "descriptor_missing":
        ledger["type_descriptors"].pop(8)
    elif case == "descriptor_order_swap":
        ledger["type_descriptors"][0:2] = reversed(ledger["type_descriptors"][0:2])
    elif case == "descriptor_name_drift":
        first_record["type_name"] += "Renamed"
    elif case == "type_version_tag_drift":
        first_record["type_version_tag"] += "/drift"
    elif case == "type_role_drift":
        first_record["type_role"] = "STANDALONE"
    elif case == "type_form_drift":
        first_record["type_form"] = "TAGGED_UNION"
    elif case == "domain_drift":
        _descriptor(
            ledger,
            "CapacityMeasurementOperationSpec",
        )["described_record_domain"] += "Drift"
    elif case == "identity_field_drift":
        _descriptor(
            ledger,
            "CapacityMeasurementOperationSpec",
        )["identity_field"] = "wrong_id"
    elif case == "identity_payload_order_swap":
        payload = selector["identity_payload_member_order"]
        payload[0:2] = reversed(payload[0:2])
    elif case == "identity_payload_includes_envelope_member":
        selector["identity_payload_member_order"].insert(1, "ordered_entries")
    elif case == "codec_relation_drift":
        first_record["codec_byte_bound_relation"] = "LT"
    elif case == "codec_limit_drift":
        first_record["codec_octet_limit"] -= 1
    elif case == "codec_limit_boolean":
        first_record["codec_octet_limit"] = True
    elif case == "codec_inclusive_flag_drift":
        first_record["codec_bound_inclusive"] = False
    elif case == "member_missing":
        first_record["member_topology"].pop()
    elif case == "member_extra":
        first_record["member_topology"].append(
            {
                "member_name": "unexpected",
                "member_position": 5,
                "member_role": "NESTED_PAYLOAD",
            }
        )
    elif case == "member_order_swap":
        first_record["member_topology"][0:2] = reversed(
            first_record["member_topology"][0:2]
        )
    elif case == "member_position_drift":
        first_record["member_topology"][0]["member_position"] = 2
    elif case == "member_name_drift":
        first_record["member_topology"][0]["member_name"] += "_renamed"
    elif case == "member_role_drift":
        first_record["member_topology"][0]["member_role"] = "IDENTITY_PAYLOAD"
    elif case == "selector_non_identity_role_drift":
        selector["member_topology"][4]["member_role"] = "IDENTITY_PAYLOAD"
    elif case == "standalone_prefix_drift":
        selector["member_topology"][0]["member_name"] = "schema_version"
    elif case == "reference_missing":
        context["typed_member_references"].pop()
    elif case == "reference_order_swap":
        context["typed_member_references"][0:2] = reversed(
            context["typed_member_references"][0:2]
        )
    elif case == "reference_kind_drift":
        context["typed_member_references"][0]["reference_kind"] = "OBJECT"
    elif case == "reference_target_drift":
        context["typed_member_references"][0]["referenced_type_name"] = (
            "CapacityMeasurementClockSpanV1"
        )
    elif case == "reference_path_drift":
        context["typed_member_references"][0]["typed_member_path"] = ["loop_clock_span"]
    elif case == "union_payload_scope_drift":
        first_union["tagged_union_topology"]["payload_binding_scope"] = "SELF_VALUE"
    elif case == "union_payload_owner_drift":
        first_union["tagged_union_topology"]["payload_owner_type_name"] = None
    elif case == "union_payload_path_drift":
        first_union["tagged_union_topology"]["payload_typed_member_path"] = [
            "spec_type"
        ]
    elif case == "union_discriminator_missing":
        first_union["tagged_union_topology"]["ordered_discriminator_topology"].pop()
    elif case == "union_discriminator_order_swap":
        discriminators = first_union["tagged_union_topology"][
            "ordered_discriminator_topology"
        ]
        discriminators[0:2] = reversed(discriminators[0:2])
    elif case == "union_discriminator_position_drift":
        first_union["tagged_union_topology"]["ordered_discriminator_topology"][0][
            "discriminator_position"
        ] = 2
    elif case == "union_discriminator_scope_drift":
        first_union["tagged_union_topology"]["ordered_discriminator_topology"][0][
            "discriminator_scope"
        ] = "SELECTED_VALUE"
    elif case == "union_discriminator_owner_drift":
        first_union["tagged_union_topology"]["ordered_discriminator_topology"][0][
            "discriminator_owner_type_name"
        ] = None
    elif case == "union_discriminator_path_drift":
        first_union["tagged_union_topology"]["ordered_discriminator_topology"][0][
            "discriminator_typed_member_path"
        ] = ["spec_type"]
    elif case == "union_alternative_missing":
        first_union["tagged_union_topology"]["ordered_alternatives"].pop()
    elif case == "union_alternative_order_swap":
        alternatives = first_union["tagged_union_topology"]["ordered_alternatives"]
        alternatives[0:2] = reversed(alternatives[0:2])
    elif case == "union_alternative_position_drift":
        first_union["tagged_union_topology"]["ordered_alternatives"][0][
            "alternative_position"
        ] = 2
    elif case == "union_alternative_name_drift":
        first_union["tagged_union_topology"]["ordered_alternatives"][0][
            "alternative_name"
        ] += "_RENAMED"
    elif case == "union_literal_member_drift":
        first_union["tagged_union_topology"]["ordered_alternatives"][0][
            "ordered_discriminator_literals"
        ][0]["member_name"] = "spec_type"
    elif case == "union_literal_value_drift":
        first_union["tagged_union_topology"]["ordered_alternatives"][0][
            "ordered_discriminator_literals"
        ][0]["text_value"] = "INGRESS"
    elif case == "union_alternative_target_drift":
        first_union["tagged_union_topology"]["ordered_alternatives"][0][
            "referenced_type_name"
        ] = "CapacityMeasurementClockSpanV1"
    elif case == "target_union_payload_owner_drift":
        target_union = _descriptor(ledger, "CapacityMeasurementTargetValue")
        target_union["tagged_union_topology"]["payload_owner_type_name"] = (
            "TargetFieldObservationV1"
        )
    elif case == "target_union_discriminator_scope_drift":
        target_union = _descriptor(ledger, "CapacityMeasurementTargetValue")
        target_union["tagged_union_topology"]["ordered_discriminator_topology"][0][
            "discriminator_scope"
        ] = "OWNER_OBJECT"
    elif case == "record_path_missing":
        ledger["path_ledger"]["record_member_paths"].pop()
    elif case == "record_path_order_swap":
        paths = ledger["path_ledger"]["record_member_paths"]
        paths[0:2] = reversed(paths[0:2])
    elif case == "record_path_position_drift":
        ledger["path_ledger"]["record_member_paths"][0]["path_position"] = 2
    elif case == "record_path_source_drift":
        ledger["path_ledger"]["record_member_paths"][0]["source_type_name"] += "Drift"
    elif case == "record_path_member_role_drift":
        ledger["path_ledger"]["record_member_paths"][0]["member_role"] = (
            "IDENTITY_PAYLOAD"
        )
    elif case == "record_path_typed_path_drift":
        ledger["path_ledger"]["record_member_paths"][0]["typed_member_path"] = [
            "due_scenario"
        ]
    elif case == "reference_path_target_drift":
        ledger["path_ledger"]["typed_reference_paths"][0]["referenced_type_name"] = (
            "CapacityMeasurementClockSpanV1"
        )
    elif case == "union_binding_missing":
        ledger["path_ledger"]["union_binding_paths"].pop()
    elif case == "union_binding_kind_drift":
        ledger["path_ledger"]["union_binding_paths"][0]["binding_kind"] = (
            "DISCRIMINATOR"
        )
    elif case == "union_binding_scope_drift":
        ledger["path_ledger"]["union_binding_paths"][0]["binding_scope"] = "SELF_VALUE"
    elif case == "union_binding_owner_drift":
        ledger["path_ledger"]["union_binding_paths"][0]["owner_type_name"] = None
    elif case == "path_count_drift":
        ledger["record_member_path_count"] -= 1
    elif case == "empty_type_catalog":
        ledger["type_descriptors"] = []
    else:
        raise AssertionError(f"unknown mutation case: {case}")
    return ledger


@pytest.mark.parametrize(
    "case",
    (
        "missing_root_member",
        "extra_root_member",
        "status_promotion",
        "ledger_version_drift",
        "record_count_drift",
        "standalone_count_drift",
        "nested_count_drift",
        "union_count_drift",
        "total_count_boolean",
        "exclusion_missing",
        "exclusion_extra",
        "exclusion_order_swap",
        "excluded_type_reintroduced",
        "descriptor_missing",
        "descriptor_order_swap",
        "descriptor_name_drift",
        "type_version_tag_drift",
        "type_role_drift",
        "type_form_drift",
        "domain_drift",
        "identity_field_drift",
        "identity_payload_order_swap",
        "identity_payload_includes_envelope_member",
        "codec_relation_drift",
        "codec_limit_drift",
        "codec_limit_boolean",
        "codec_inclusive_flag_drift",
        "member_missing",
        "member_extra",
        "member_order_swap",
        "member_position_drift",
        "member_name_drift",
        "member_role_drift",
        "selector_non_identity_role_drift",
        "standalone_prefix_drift",
        "reference_missing",
        "reference_order_swap",
        "reference_kind_drift",
        "reference_target_drift",
        "reference_path_drift",
        "union_payload_scope_drift",
        "union_payload_owner_drift",
        "union_payload_path_drift",
        "union_discriminator_missing",
        "union_discriminator_order_swap",
        "union_discriminator_position_drift",
        "union_discriminator_scope_drift",
        "union_discriminator_owner_drift",
        "union_discriminator_path_drift",
        "union_alternative_missing",
        "union_alternative_order_swap",
        "union_alternative_position_drift",
        "union_alternative_name_drift",
        "union_literal_member_drift",
        "union_literal_value_drift",
        "union_alternative_target_drift",
        "target_union_payload_owner_drift",
        "target_union_discriminator_scope_drift",
        "record_path_missing",
        "record_path_order_swap",
        "record_path_position_drift",
        "record_path_source_drift",
        "record_path_member_role_drift",
        "record_path_typed_path_drift",
        "reference_path_target_drift",
        "union_binding_missing",
        "union_binding_kind_drift",
        "union_binding_scope_drift",
        "union_binding_owner_drift",
        "path_count_drift",
        "empty_type_catalog",
    ),
)
def test_topology_mutation_is_rejected(
    tmp_path: Path,
    case: str,
) -> None:
    path = _write_ledger(tmp_path / "mutated.json", _mutated_ledger(case))
    _assert_controlled_rejection(_run_validator(path))


@pytest.mark.parametrize(
    "case",
    (
        "minified",
        "duplicate_key",
        "float",
        "non_finite",
        "lone_surrogate",
        "excessive_nesting",
        "oversized",
    ),
)
def test_raw_json_attack_is_rejected(tmp_path: Path, case: str) -> None:
    raw = _ledger_path().read_bytes()
    if case == "minified":
        payload = json.dumps(
            json.loads(raw),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    elif case == "duplicate_key":
        payload = raw.replace(
            b'  "component_status":',
            b'  "component_status": "DUPLICATE",\n  "component_status":',
            1,
        )
    elif case == "float":
        payload = raw.replace(
            b'  "concrete_record_count": 49,',
            b'  "concrete_record_count": 49.0,',
            1,
        )
    elif case == "non_finite":
        payload = raw.replace(
            b'  "concrete_record_count": 49,',
            b'  "concrete_record_count": NaN,',
            1,
        )
    elif case == "lone_surrogate":
        payload = raw.replace(
            b'"CapacityMeasurementClockSpanV1"',
            b'"\\ud800"',
            1,
        )
    elif case == "excessive_nesting":
        payload = b"[" * 17 + b"0" + b"]" * 17
    elif case == "oversized":
        payload = raw + b" " * (1_048_576 - len(raw) + 1)
    else:
        raise AssertionError(case)
    path = tmp_path / "raw-attack.json"
    path.write_bytes(payload)
    _assert_controlled_rejection(_run_validator(path))


def test_symlink_ledger_is_rejected_without_traceback(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_bytes(_ledger_path().read_bytes())
    link = tmp_path / "ledger-link.json"
    link.symlink_to(target)
    _assert_controlled_rejection(_run_validator(link))


def test_non_regular_ledger_is_rejected_without_traceback(tmp_path: Path) -> None:
    _assert_controlled_rejection(_run_validator(tmp_path))


def test_fifo_ledger_is_rejected_without_blocking(tmp_path: Path) -> None:
    fifo = tmp_path / "ledger.fifo"
    os.mkfifo(fifo)
    _assert_controlled_rejection(_run_validator(fifo))

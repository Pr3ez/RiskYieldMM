from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_VALIDATOR = (
    "scripts/tests/validate_raw_v8_step2_external_schema_v2_structural_registry_v49f.py"
)
_REGISTRY = (
    "scripts/tests/raw_v8_step2_external_schema_v2_structural_registry_v49f.json"
)
_CORE = "scripts/tests/raw_v8_step2_external_schema_v2_core_ledger_v49f.json"
_TOPOLOGY = "scripts/tests/raw_v8_step2_external_schema_v2_topology_ledger_v49f.json"
_SCALAR = "scripts/tests/raw_v8_step2_external_schema_v2_scalar_path_ledger_v49f.json"
_RULE = (
    "scripts/tests/raw_v8_step2_external_schema_v2_rule_application_ledger_v49f.json"
)
_REGISTRY_SHA256 = "9160297ff316c5931737c92f8b359f0a1e2ec22f0aa996ef3b09cf830dc96bf3"
_REGISTRY_OCTETS = 1_469_663
_REGISTRY_ID = "5dc95a3e99c5646e912b6a7e9c3970cf2489d560ea890b0a19d38af4c51c2140"
_STATUS = "STRUCTURAL_REGISTRY_ONLY_RULE_RUNTIME_AND_MAXIMA_PENDING"
_ERROR_PREFIX = "Raw-V8 Step-2 structural External Schema V2 error: "


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load(relative: str) -> dict[str, Any]:
    value = json.loads((_root() / relative).read_text(encoding="utf-8"))
    assert type(value) is dict
    return value


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


@pytest.fixture(scope="module")
def validator() -> ModuleType:
    path = _root() / _VALIDATOR
    spec = importlib.util.spec_from_file_location(
        "_raw_v8_structural_registry_validator",
        path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def dependencies() -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
]:
    return _load(_CORE), _load(_TOPOLOGY), _load(_SCALAR), _load(_RULE)


def _run(
    path: Path,
    *,
    repository_root: Path | None = None,
    timeout: int = 60,
) -> subprocess.CompletedProcess[str]:
    root = _root()
    return subprocess.run(
        (
            sys.executable,
            "-I",
            "-B",
            str(root / _VALIDATOR),
            "--repository-root",
            str(root if repository_root is None else repository_root),
            "--registry",
            str(path),
        ),
        cwd=root,
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


def _assert_reject(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.startswith(_ERROR_PREFIX)
    assert result.stderr.endswith("\n")
    assert "Traceback" not in result.stderr


def _resign_registry(module: ModuleType, registry: dict[str, Any]) -> None:
    payload_names = (
        "external_schema_profile",
        "unicode_source_catalog",
        "identifier_profile_catalog",
        "ascii_dfa_catalog",
        "text_language_catalog",
        "value_schema_catalog",
        "external_type_descriptor_count",
        "ordered_external_type_descriptors",
        "cross_field_rule_descriptor_count",
        "ordered_cross_field_rule_descriptors",
        "fixed_position_resolver_profile_catalog",
        "rule_application_descriptor_count",
        "ordered_rule_application_descriptors",
        "schema_graph_node_count",
        "ordered_schema_graph_node_names",
    )
    registry["external_schema_registry_id"] = module._semantic_id(
        module.REGISTRY_RECORD_DOMAIN,
        {name: registry[name] for name in payload_names},
    )


def _resign_type(
    module: ModuleType,
    registry: dict[str, Any],
    descriptor: dict[str, Any],
) -> None:
    payload = {
        key: value
        for key, value in descriptor.items()
        if key != "external_type_descriptor_id"
    }
    descriptor["external_type_descriptor_id"] = module._semantic_id(
        module.TYPE_DOMAIN,
        payload,
    )
    _resign_registry(module, registry)


def _resign_rule(
    module: ModuleType,
    registry: dict[str, Any],
    rule: dict[str, Any],
) -> None:
    payload = {
        key: value
        for key, value in rule.items()
        if key != "step2_cross_field_rule_descriptor_id"
    }
    rule["step2_cross_field_rule_descriptor_id"] = module._semantic_id(
        module.RULE_DOMAIN,
        payload,
    )
    registry["ordered_cross_field_rule_descriptors"].sort(
        key=lambda item: item["step2_cross_field_rule_descriptor_id"]
    )
    _resign_registry(module, registry)


def _resign_application(
    module: ModuleType,
    registry: dict[str, Any],
    application: dict[str, Any],
) -> None:
    payload = {
        key: value for key, value in application.items() if key != "rule_application_id"
    }
    application["rule_application_id"] = module._semantic_id(
        module.APPLICATION_DOMAIN,
        payload,
    )
    _resign_registry(module, registry)


def _type(registry: dict[str, Any], name: str) -> dict[str, Any]:
    return next(
        item
        for item in registry["ordered_external_type_descriptors"]
        if item["type_name"] == name
    )


def _assert_static_reject(
    module: ModuleType,
    dependencies: tuple[
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
    ],
    registry: dict[str, Any],
) -> None:
    core, topology, scalar, rules = dependencies
    with pytest.raises(module.StructuralRegistryError):
        module.validate_materialized_registry(
            core=core,
            topology=topology,
            scalar=scalar,
            rules=rules,
            registry=registry,
        )


def test_exact_registry_bytes_root_and_cli_report() -> None:
    raw = (_root() / _REGISTRY).read_bytes()
    registry = json.loads(raw)
    assert raw == _pretty(registry)
    assert len(raw) == _REGISTRY_OCTETS
    assert hashlib.sha256(raw).hexdigest() == _REGISTRY_SHA256
    assert registry["external_schema_registry_id"] == _REGISTRY_ID
    assert "component_status" not in registry
    assert set(registry) == {
        "canonicalization_version",
        "measurement_schema_version",
        "record_domain",
        "external_schema_profile",
        "unicode_source_catalog",
        "identifier_profile_catalog",
        "ascii_dfa_catalog",
        "text_language_catalog",
        "value_schema_catalog",
        "external_type_descriptor_count",
        "ordered_external_type_descriptors",
        "cross_field_rule_descriptor_count",
        "ordered_cross_field_rule_descriptors",
        "fixed_position_resolver_profile_catalog",
        "rule_application_descriptor_count",
        "ordered_rule_application_descriptors",
        "schema_graph_node_count",
        "ordered_schema_graph_node_names",
        "external_schema_registry_id",
    }

    result = _run(_root() / _REGISTRY)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert result.stderr == ""
    assert json.loads(result.stdout) == {
        "ascii_dfa_count": 9,
        "component_status": _STATUS,
        "cross_field_rule_descriptor_count": 42,
        "external_schema_registry_id": _REGISTRY_ID,
        "external_type_descriptor_count": 52,
        "identifier_profile_count": 3,
        "maximum_type_graph_depth": 5,
        "registry_octets": _REGISTRY_OCTETS,
        "registry_path": str(_root() / _REGISTRY),
        "registry_sha256": _REGISTRY_SHA256,
        "rule_application_descriptor_count": 8,
        "schema_graph_node_count": 52,
        "text_language_count": 103,
        "unicode_source_count": 6,
        "value_schema_count": 236,
    }


def test_generator_is_byte_deterministic_across_hash_seeds(
    tmp_path: Path,
) -> None:
    expected = (_root() / _REGISTRY).read_bytes()
    for seed in ("0", "1", "918273"):
        output = tmp_path / f"registry-{seed}.json"
        result = subprocess.run(
            (
                sys.executable,
                "-I",
                "-B",
                str(_root() / _VALIDATOR),
                "--repository-root",
                str(_root()),
                "--write-expected-registry",
                str(output),
            ),
            cwd=_root(),
            env={
                **os.environ,
                "PYTHONHASHSEED": seed,
                "PYTHONDONTWRITEBYTECODE": "1",
            },
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert result.returncode == 0, (result.stdout, result.stderr)
        assert result.stdout == result.stderr == ""
        assert output.read_bytes() == expected


def test_catalogs_are_exact_accepted_component_assembly() -> None:
    registry = _load(_REGISTRY)
    scalar = _load(_SCALAR)
    rules = _load(_RULE)
    assert (
        registry["identifier_profile_catalog"]
        == scalar["ordered_unicode_identifier_profiles"]
    )
    assert registry["ascii_dfa_catalog"] == scalar["ordered_ascii_dfa_descriptors"]
    assert (
        registry["text_language_catalog"] == scalar["ordered_text_language_descriptors"]
    )
    assert {item["value_schema_id"] for item in registry["value_schema_catalog"]} == {
        item["value_schema_id"] for item in scalar["ordered_value_schemas"]
    } | {
        item["value_schema_id"] for item in rules["ordered_additive_rule_value_schemas"]
    }
    assert (
        registry["ordered_cross_field_rule_descriptors"]
        == rules["ordered_rule_descriptors"]
    )
    assert (
        registry["fixed_position_resolver_profile_catalog"]
        == rules["ordered_fixed_position_resolver_profiles"]
    )
    assert (
        registry["ordered_rule_application_descriptors"]
        == rules["ordered_rule_application_descriptors"]
    )


def test_exact_49_plus_3_type_graph_and_union_metadata() -> None:
    registry = _load(_REGISTRY)
    descriptors = registry["ordered_external_type_descriptors"]
    assert len(descriptors) == 52
    assert sum(item["type_form"] == "RECORD" for item in descriptors) == 49
    assert sum(item["type_form"] == "TAGGED_UNION" for item in descriptors) == 3
    assert (
        sum(len(item["record_member_descriptors"] or []) for item in descriptors) == 421
    )
    assert sum(len(item["ordered_intrinsic_rule_ids"]) for item in descriptors) == 34
    target_union = _type(registry, "CapacityMeasurementTargetValue")
    discriminator = target_union["tagged_union_descriptor"][
        "ordered_discriminator_descriptors"
    ][0]
    assert discriminator["text_language_id"] == (
        "6808a2be6b5f527719c6cd18621ddbfdb9afd6944a705a555e4207e092a74769"
    )
    assert len(target_union["tagged_union_descriptor"]["ordered_alternatives"]) == 9


def test_validator_is_stdlib_only_and_does_not_claim_complete_gate() -> None:
    source = (_root() / _VALIDATOR).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imports.update(
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    )
    assert not any(
        name.startswith(("riskyieldmm", "numpy", "pandas", "polars"))
        for name in imports
    )
    assert _STATUS in source
    assert "constructive maxima" in source


def test_root_order_count_and_extra_member_mutations_reject_after_resigning(
    validator: ModuleType,
    dependencies: tuple[
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
    ],
) -> None:
    extra = _load(_REGISTRY)
    extra["component_status"] = _STATUS
    _assert_static_reject(validator, dependencies, extra)

    reordered = _load(_REGISTRY)
    reordered["ordered_external_type_descriptors"][0:2] = reversed(
        reordered["ordered_external_type_descriptors"][0:2]
    )
    _resign_registry(validator, reordered)
    _assert_static_reject(validator, dependencies, reordered)

    missing = _load(_REGISTRY)
    removed = missing["ordered_external_type_descriptors"].pop()
    missing["external_type_descriptor_count"] -= 1
    missing["schema_graph_node_count"] -= 1
    missing["ordered_schema_graph_node_names"].remove(removed["type_name"])
    _resign_registry(validator, missing)
    _assert_static_reject(validator, dependencies, missing)


def test_member_role_position_schema_and_cycle_mutations_reject(
    validator: ModuleType,
    dependencies: tuple[
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
    ],
) -> None:
    position = _load(_REGISTRY)
    descriptor = _type(position, "CapacityMeasurementDispatchWindowEvidenceV1")
    descriptor["record_member_descriptors"][3]["member_position"] = 5
    _resign_type(validator, position, descriptor)
    _assert_static_reject(validator, dependencies, position)

    role = _load(_REGISTRY)
    descriptor = _type(role, "CapacityMeasurementDispatchWindowEvidenceV1")
    descriptor["record_member_descriptors"][3]["member_role"] = "ENVELOPE_NON_IDENTITY"
    _resign_type(validator, role, descriptor)
    _assert_static_reject(validator, dependencies, role)

    cycle = _load(_REGISTRY)
    descriptor = _type(cycle, "TargetObservationV2")
    self_schema = next(
        item["value_schema_id"]
        for item in cycle["value_schema_catalog"]
        if item["schema_kind"] == "OBJECT_REF"
        and not item["nullable"]
        and item["referenced_type_name"] == "TargetObservationV2"
    )
    descriptor["record_member_descriptors"][3]["value_schema_id"] = self_schema
    _resign_type(validator, cycle, descriptor)
    _assert_static_reject(validator, dependencies, cycle)


def test_union_language_and_catalog_reachability_mutations_reject(
    validator: ModuleType,
    dependencies: tuple[
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
    ],
) -> None:
    union_mutation = _load(_REGISTRY)
    descriptor = _type(union_mutation, "CapacityMeasurementTargetValue")
    descriptor["tagged_union_descriptor"]["ordered_discriminator_descriptors"][0][
        "text_language_id"
    ] = next(
        item["text_language_id"]
        for item in union_mutation["text_language_catalog"]
        if item["language_kind"] == "ENUM" and len(item["ordered_literals"]) != 9
    )
    _resign_type(validator, union_mutation, descriptor)
    _assert_static_reject(validator, dependencies, union_mutation)

    extra_schema = _load(_REGISTRY)
    payload = {
        "schema_kind": "SAFE_INTEGER",
        "nullable": False,
        "boolean_literal": None,
        "integer_minimum": 456_789,
        "integer_maximum": 456_790,
        "text_language_id": None,
        "array_minimum_items": None,
        "array_maximum_items": None,
        "array_item_value_schema_id": None,
        "referenced_type_name": None,
    }
    identifier = validator._semantic_id(validator.VALUE_SCHEMA_DOMAIN, payload)
    extra_schema["value_schema_catalog"].append(
        {**payload, "value_schema_id": identifier}
    )
    extra_schema["value_schema_catalog"].sort(key=lambda item: item["value_schema_id"])
    _resign_registry(validator, extra_schema)
    _assert_static_reject(validator, dependencies, extra_schema)


def test_resigned_rule_application_and_root_mutations_reject(
    validator: ModuleType,
    dependencies: tuple[
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
    ],
) -> None:
    rule_mutation = _load(_REGISTRY)
    rule = next(
        item
        for item in rule_mutation["ordered_cross_field_rule_descriptors"]
        if item["rule_id"] == "RULE/INTRINSIC/TargetObservationRootV2/V1"
    )
    rule["rule_version"] = "riskyieldmm_raw_v8_step2_typed_rule_v2_MUTATED"
    _resign_rule(validator, rule_mutation, rule)
    _assert_static_reject(validator, dependencies, rule_mutation)

    application_mutation = _load(_REGISTRY)
    application = next(
        item
        for item in application_mutation["ordered_rule_application_descriptors"]
        if item["application_name"] == "APPLY/V2_OBSERVATION_FIELDS_REGISTRY_V1"
    )
    application["maximum_rule_evaluations"] -= 1
    _resign_application(
        validator,
        application_mutation,
        application,
    )
    _assert_static_reject(
        validator,
        dependencies,
        application_mutation,
    )

    root_mutation = _load(_REGISTRY)
    root_mutation["external_schema_profile"] += "_MUTATED"
    _resign_registry(validator, root_mutation)
    _assert_static_reject(validator, dependencies, root_mutation)


def test_unicode_source_mutation_and_semantic_id_reject(
    validator: ModuleType,
    dependencies: tuple[
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
    ],
) -> None:
    registry = _load(_REGISTRY)
    source = registry["unicode_source_catalog"][0]
    source["byte_count"] += 1
    payload = {
        key: value for key, value in source.items() if key != "unicode_source_record_id"
    }
    source["unicode_source_record_id"] = validator._semantic_id(
        validator.SOURCE_DOMAIN,
        payload,
    )
    registry["unicode_source_catalog"].sort(
        key=lambda item: item["unicode_source_record_id"]
    )
    _resign_registry(validator, registry)
    _assert_static_reject(validator, dependencies, registry)


def test_dependency_hash_pin_rejects_changed_component(
    tmp_path: Path,
) -> None:
    for relative in (_CORE, _TOPOLOGY, _SCALAR, _RULE):
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(_root() / relative, destination)
    core_path = tmp_path / _CORE
    core_path.write_bytes(core_path.read_bytes() + b" ")
    _assert_reject(
        _run(
            _root() / _REGISTRY,
            repository_root=tmp_path,
        )
    )


def test_cli_is_cwd_independent_from_tmp(tmp_path: Path) -> None:
    result = subprocess.run(
        (
            sys.executable,
            "-I",
            "-B",
            str(_root() / _VALIDATOR),
            "--repository-root",
            str(_root()),
            "--registry",
            str(_root() / _REGISTRY),
        ),
        cwd=tmp_path,
        env={
            **os.environ,
            "PYTHONHASHSEED": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert result.stderr == ""
    assert json.loads(result.stdout)["external_schema_registry_id"] == (_REGISTRY_ID)


def test_bounded_reader_rejects_symlink_fifo_directory_and_limit(
    tmp_path: Path,
) -> None:
    symlink = tmp_path / "registry-link.json"
    symlink.symlink_to(_root() / _REGISTRY)
    _assert_reject(_run(symlink))

    fifo = tmp_path / "registry.fifo"
    os.mkfifo(fifo)
    _assert_reject(_run(fifo))
    _assert_reject(_run(tmp_path))

    exact_limit = tmp_path / "exact-limit.json"
    exact_limit.write_bytes(b" " * 16_777_216)
    _assert_reject(_run(exact_limit))


@pytest.mark.parametrize(
    "raw",
    [
        b'{"a":1,"a":1}\n',
        b'{"floating":1.5}\n',
        b'{"surrogate":"\\ud800"}\n',
        b'{"huge":' + (b"9" * 5_000) + b"}\n",
        (b'{"deep":' + (b"[" * 17) + b"0" + (b"]" * 17) + b"}\n"),
        b'{"unterminated":"value}\n',
        b'{"unbalanced":[1,2}\n',
    ],
)
def test_raw_json_adversaries_fail_closed_without_traceback(
    tmp_path: Path,
    raw: bytes,
) -> None:
    path = tmp_path / "adversarial.json"
    path.write_bytes(raw)
    _assert_reject(_run(path))

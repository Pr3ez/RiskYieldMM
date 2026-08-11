from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

_V8_MODULE_NAME = "riskyieldmm.trading.physical_transport_capacity_contracts_v49f_v8"
_V8_MODULE_RELATIVE_PATH = (
    "riskyieldmm/trading/physical_transport_capacity_contracts_v49f_v8.py"
)
_HARNESS_RELATIVE_PATH = "tests/_raw_v8_step2_contract_harness_v49f.py"
_GENERATOR_RELATIVE_PATH = "scripts/tests/generate_raw_v8_step2_inventory_v49f.py"
_GOLDEN_RELATIVE_PATH = "tests/raw_v8_step2_inventory_v49f.json"
_INVENTORY_SCHEMA_VERSION = "riskyieldmm.raw_v8_step2_inventory.v3"

_EXPECTED_GOLDEN_KEYS = frozenset(
    {
        "fixture_records",
        "checkpoint_selector_catalog",
        "external_schema_registry_v2",
        "ingress_logical_oracle_profile_catalog",
        "inventory_sha256",
        "invariants",
        "marker_contract",
        "normative_document_inputs",
        "operation_contracts",
        "operation_counter_schema",
        "schema_version",
        "target_field_registry",
    }
)
_EXPECTED_FIXTURE_KEYS = frozenset(
    {
        "counter_snapshot",
        "dispatch_window_evidence",
        "due_decision_clock_evidence",
        "local_shutdown_boundary_spec",
        "one_field_mutation_metadata",
        "operation_declaration",
        "operation_results",
        "operation_specs",
        "target_observation_v2_fixtures",
    }
)
_EXPECTED_NORMATIVE_SHA256_BY_ROLE = {
    "PARENT_MARKER_OPERATION_TARGET_PROTOCOL": (
        "15b42d32afe5fdff74890b2c18f735ff761244548729142c4ff2b1034fee2388"
    ),
    "STEP2_V2_CONTRACT_FREEZE": (
        "355548cb3ef323ab45b0289be9891ab578b75d0147639ab37c9f3e5ff251aa1c"
    ),
    "STEP2_EXTERNAL_SCHEMA_V2_CORRECTION": (
        "29ec141e53adeb1c0afd51f205f5b57eb784b8859b5ba40958299abd1b713b55"
    ),
    "STEP3_TARGET_AND_LIFECYCLE_CORRECTION": (
        "635952095b0b20089d5ec2c13104255ebeeff11535c8f94131a4983a1a9fec0a"
    ),
}


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _reject_json_constant(value: str) -> Any:
    raise ValueError(f"non-finite JSON constant: {value}")


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_golden(path: Path) -> dict[str, Any]:
    payload = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_strict_object,
        parse_constant=_reject_json_constant,
    )
    assert type(payload) is dict
    assert frozenset(payload) == _EXPECTED_GOLDEN_KEYS
    assert payload["schema_version"] == _INVENTORY_SCHEMA_VERSION
    assert type(payload["inventory_sha256"]) is str
    assert len(payload["inventory_sha256"]) == 64
    assert type(payload["fixture_records"]) is dict
    assert frozenset(payload["fixture_records"]) == _EXPECTED_FIXTURE_KEYS
    assert [
        item["document_role"] for item in payload["normative_document_inputs"]
    ] == list(_EXPECTED_NORMATIVE_SHA256_BY_ROLE)
    assert {
        item["document_role"]: item["raw_sha256"]
        for item in payload["normative_document_inputs"]
    } == _EXPECTED_NORMATIVE_SHA256_BY_ROLE
    assert len(payload["checkpoint_selector_catalog"]) == 9
    assert len(payload["ingress_logical_oracle_profile_catalog"]) == 1
    counts = payload["invariants"]["counts"]
    assert counts["status_reason_count"] == 26
    assert counts["context_predicate_count"] == 6
    assert counts["target_field_count"] == 185
    assert counts["counter_field_count"] == 66
    return payload


def _run_child(*arguments: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    root = _repository_root()
    return subprocess.run(
        (sys.executable, "-I", "-B", *arguments),
        cwd=root,
        env={**os.environ, "PYTHONHASHSEED": "0", "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _assert_child_passed(
    result: subprocess.CompletedProcess[str], *, expected_stdout: str
) -> None:
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert result.stderr == ""
    assert result.stdout == f"{expected_stdout}\n"


def test_raw_v8_step2_source_is_private_and_parent_remains_import_isolated() -> None:
    root = _repository_root()
    module_path = root / _V8_MODULE_RELATIVE_PATH
    harness_path = root / _HARNESS_RELATIVE_PATH
    package_init_path = root / "riskyieldmm/trading/__init__.py"

    assert module_path.is_file()
    assert harness_path.is_file()
    module_tree = ast.parse(module_path.read_text(encoding="utf-8"), module_path.name)
    parent_tree = ast.parse(
        Path(__file__).read_text(encoding="utf-8"), Path(__file__).name
    )
    package_tree = ast.parse(
        package_init_path.read_text(encoding="utf-8"), package_init_path.name
    )

    production_imports: list[tuple[int, str | None, tuple[str, ...]]] = []
    for node in ast.walk(module_tree):
        if isinstance(node, ast.Import):
            production_imports.append(
                (0, None, tuple(alias.name for alias in node.names))
            )
        elif isinstance(node, ast.ImportFrom):
            production_imports.append(
                (
                    node.level,
                    node.module,
                    tuple(alias.name for alias in node.names),
                )
            )

    forbidden_fragments = (
        "capacity_lifecycle",
        "capacity_measurement",
        "capacity_sampler",
        "capacity_source_observation",
        "physical_transport_actor",
        "physical_transport_runtime",
        "physical_projection",
        "physical_transport_v4",
    )
    for level, module, names in production_imports:
        imported = " ".join((module or "", *names))
        assert not any(fragment in imported for fragment in forbidden_fragments)
        if level:
            assert level == 1
            assert module == "canonical"
        elif module is not None:
            assert module == "__future__" or not module.startswith("riskyieldmm")
        else:
            assert not any(name.startswith("riskyieldmm") for name in names)

    for node in ast.walk(parent_tree):
        if isinstance(node, ast.Import):
            assert all(_V8_MODULE_NAME not in alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert _V8_MODULE_NAME not in (node.module or "")

    package_source = package_init_path.read_text(encoding="utf-8")
    assert "physical_transport_capacity_contracts_v49f_v8" not in package_source
    functions_by_name = {
        node.name: node
        for node in module_tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    unicode_validator = functions_by_name["_utf8_identifier"]
    unicode_attribute_calls = {
        node.func.attr
        for node in ast.walk(unicode_validator)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    unicode_direct_calls = {
        node.func.id
        for node in ast.walk(unicode_validator)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert {"strip", "isspace", "normalize"}.isdisjoint(unicode_attribute_calls)
    assert "canonical_identifier" not in unicode_direct_calls
    ascii_validator = functions_by_name["_ascii_text"]
    ascii_direct_calls = {
        node.func.id
        for node in ast.walk(ascii_validator)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "_utf8_identifier" not in ascii_direct_calls
    v8_symbol_names = {
        node.name
        for node in module_tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and not node.name.startswith("_")
    }
    package_bound_names = {
        alias.asname or alias.name
        for node in ast.walk(package_tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert v8_symbol_names.isdisjoint(package_bound_names)

    result = _run_child(
        str(harness_path),
        "--case",
        "public-isolation",
        "--repository-root",
        str(root),
    )
    _assert_child_passed(result, expected_stdout="PASS raw-v8-public-isolation")


def test_raw_v8_unicode_authority_is_separate_from_ascii_import_capability() -> None:
    root = _repository_root()
    source = f"""
import sys
import unicodedata

sys.path.insert(0, {str(root)!r})
unicodedata.unidata_version = "16.0.0"
import riskyieldmm.trading
from riskyieldmm.trading import physical_transport_capacity_contracts_v49f_v8 as c

assert c._ascii_text(
    "ASCII_1",
    field="probe",
    minimum=1,
    maximum=16,
) == "ASCII_1"
try:
    c._utf8_identifier("unicode", field="probe", maximum=16)
except c.CanonicalizationError as exc:
    assert "Unicode authority differs" in str(exc)
else:
    raise AssertionError("unrestricted Unicode accepted under UCD drift")
print("PASS raw-v8-unicode-capability-separation")
"""
    result = _run_child("-c", source)
    _assert_child_passed(
        result,
        expected_stdout="PASS raw-v8-unicode-capability-separation",
    )


def test_raw_v8_direct_constructors_enforce_persisted_string_array_bounds() -> None:
    root = _repository_root()
    source = f"""
import sys
from dataclasses import replace

sys.path.insert(0, {str(root)!r})
from riskyieldmm.trading import physical_transport_capacity_contracts_v49f_v8 as c

def reject(action, label):
    try:
        action()
    except c.CanonicalizationError:
        return
    raise AssertionError(label)

raw_513 = tuple(f"v{{index:04d}}" for index in range(513))
c.CapacityMeasurementVocabularyDefinitionV49FV8(
    vocabulary_id="VOCABULARY",
    members=raw_513[:-1],
)
reject(
    lambda: c.CapacityMeasurementVocabularyDefinitionV49FV8(
        vocabulary_id="VOCABULARY",
        members=raw_513,
    ),
    "direct vocabulary constructor accepted 513 members",
)
c.CapacityMeasurementValueShapeDefinitionV49FV8(
    value_shape_id="SHAPE",
    container_kind="FIXED_MAP",
    minimum_items=512,
    maximum_items=512,
    ordered_keys=raw_513[:-1],
)
reject(
    lambda: c.CapacityMeasurementValueShapeDefinitionV49FV8(
        value_shape_id="SHAPE",
        container_kind="FIXED_MAP",
        minimum_items=513,
        maximum_items=513,
        ordered_keys=raw_513,
    ),
    "direct value-shape constructor accepted 513 keys",
)
descriptor = c.RAW_V8_TARGET_FIELD_DESCRIPTORS_V49F[0]
replace(descriptor, value_shape_keys=raw_513[:-1])
reject(
    lambda: replace(descriptor, value_shape_keys=raw_513),
    "direct target-descriptor constructor accepted 513 shape keys",
)
raw_17 = tuple(f"constraint_{{index:02d}}" for index in range(17))
replace(descriptor, cross_field_constraint_ids=raw_17[:-1])
reject(
    lambda: replace(descriptor, cross_field_constraint_ids=raw_17),
    "direct target-descriptor constructor accepted 17 constraint IDs",
)
method_pair = descriptor.observation_method_role_pairs[0]
raw_9_method_pairs = tuple(
    replace(
        method_pair,
        observation_method=method,
    )
    for method in tuple(c.CapacityMeasurementTargetObservationMethodV49FV8)[:9]
)
replace(descriptor, observation_method_role_pairs=raw_9_method_pairs[:-1])
reject(
    lambda: replace(descriptor, observation_method_role_pairs=raw_9_method_pairs),
    "direct target-descriptor constructor accepted 9 method-role pairs",
)
print("PASS raw-v8-direct-string-array-bounds")
"""
    result = _run_child("-c", source)
    _assert_child_passed(
        result,
        expected_stdout="PASS raw-v8-direct-string-array-bounds",
    )


def test_raw_v8_step2_generator_reproduces_the_frozen_golden() -> None:
    root = _repository_root()
    generator = root / _GENERATOR_RELATIVE_PATH
    golden = root / _GOLDEN_RELATIVE_PATH
    assert generator.is_file()
    assert golden.is_file()

    result = _run_child(
        str(generator),
        "--check",
        "--repository-root",
        str(root),
        "--output",
        str(golden),
        timeout=180,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert result.stderr == ""
    _load_golden(golden)


def test_raw_v8_step2_exact_contracts_pass_only_in_an_isolated_child() -> None:
    root = _repository_root()
    result = _run_child(
        str(root / _HARNESS_RELATIVE_PATH),
        "--case",
        "contracts",
        "--repository-root",
        str(root),
        timeout=180,
    )
    _assert_child_passed(result, expected_stdout="PASS raw-v8-step2-contracts")


def test_v7_source_observer_rejects_loaded_v8_in_a_separate_isolated_child() -> None:
    root = _repository_root()
    result = _run_child(
        str(root / _HARNESS_RELATIVE_PATH),
        "--case",
        "v7-extra-loaded-module",
        "--repository-root",
        str(root),
    )
    _assert_child_passed(
        result,
        expected_stdout="PASS v7-rejected-raw-v8-extra-loaded-module",
    )

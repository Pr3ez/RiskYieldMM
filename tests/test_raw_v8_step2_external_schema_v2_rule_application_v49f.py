from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_VALIDATOR = (
    "scripts/tests/validate_raw_v8_step2_external_schema_v2_rule_application_v49f.py"
)
_CAPTURE = (
    "scripts/tests/"
    "capture_raw_v8_step2_external_schema_v2_rule_literal_authority_v49f.py"
)
_LEDGER = (
    "scripts/tests/raw_v8_step2_external_schema_v2_rule_application_ledger_v49f.json"
)
_TOPOLOGY = "scripts/tests/raw_v8_step2_external_schema_v2_topology_ledger_v49f.json"
_SCALAR = "scripts/tests/raw_v8_step2_external_schema_v2_scalar_path_ledger_v49f.json"
_LITERALS = (
    "scripts/tests/raw_v8_step2_external_schema_v2_rule_literal_authority_v49f.json"
)
_LEDGER_SHA256 = "979d7affe2d745d46f5977d9d69a4d1efa473f95c1a374737bf34181d9dac282"
_LEDGER_OCTETS = 1_141_506
_COMPONENT_ID = "0a1e0ffed2bf8d07a94c24c5f247270bb86f9a172e448830600c0ddcecf010a8"
_ERROR_PREFIX = "Raw-V8 Step-2 external-schema V2 rule/application error: "


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load(path: str) -> dict[str, Any]:
    value = json.loads((_root() / path).read_text(encoding="utf-8"))
    assert type(value) is dict
    return value


def _canonical(value: Any) -> bytes:
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
    spec = importlib.util.spec_from_file_location("_raw_v8_rule_validator", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def authorities() -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
]:
    return _load(_TOPOLOGY), _load(_SCALAR), _load(_LITERALS)


def _run(path: Path, *, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    root = _root()
    return subprocess.run(
        (
            sys.executable,
            "-I",
            "-B",
            str(root / _VALIDATOR),
            "--repository-root",
            str(root),
            "--ledger",
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


def _assert_controlled_rejection(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.startswith(_ERROR_PREFIX)
    assert result.stderr.endswith("\n")
    assert "Traceback" not in result.stderr


def _resign_component(module: ModuleType, ledger: dict[str, Any]) -> None:
    payload = {
        key: value
        for key, value in ledger.items()
        if key != "rule_application_component_sha256"
    }
    ledger["rule_application_component_sha256"] = module._semantic_id(
        module.COMPONENT_DOMAIN,
        payload,
    )


def _resign_rule(
    module: ModuleType,
    ledger: dict[str, Any],
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
    _resign_component(module, ledger)


def _resign_application(
    module: ModuleType,
    ledger: dict[str, Any],
    application: dict[str, Any],
) -> None:
    payload = {
        key: value for key, value in application.items() if key != "rule_application_id"
    }
    application["rule_application_id"] = module._semantic_id(
        module.APPLICATION_DOMAIN,
        payload,
    )
    _resign_component(module, ledger)


def _rule(ledger: dict[str, Any], rule_id: str) -> dict[str, Any]:
    return next(
        item
        for item in ledger["ordered_rule_descriptors"]
        if item["rule_id"] == rule_id
    )


def _application(
    ledger: dict[str, Any],
    application_name: str,
) -> dict[str, Any]:
    return next(
        item
        for item in ledger["ordered_rule_application_descriptors"]
        if item["application_name"] == application_name
    )


def _assert_static_rejection(
    module: ModuleType,
    authorities: tuple[
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
    ],
    ledger: dict[str, Any],
) -> None:
    topology, scalar, literals = authorities
    with pytest.raises(module.ValidationError):
        module.validate_materialized_ledger(
            topology=topology,
            scalar=scalar,
            literals=literals,
            ledger=ledger,
        )


def test_exact_canonical_component_and_independent_cli_report() -> None:
    raw = (_root() / _LEDGER).read_bytes()
    ledger = json.loads(raw)
    assert raw == _canonical(ledger)
    assert len(raw) == _LEDGER_OCTETS
    assert hashlib.sha256(raw).hexdigest() == _LEDGER_SHA256
    assert ledger["component_status"] == "RULE_APPLICATION_ONLY_NOT_FULL_REGISTRY"
    assert ledger["rule_application_component_sha256"] == _COMPONENT_ID

    result = _run(_root() / _LEDGER)
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert result.stderr == ""
    report = json.loads(result.stdout)
    assert report == {
        "additive_rule_value_schema_count": 36,
        "component_status": "RULE_APPLICATION_ONLY_NOT_FULL_REGISTRY",
        "concrete_attachment_count": 49,
        "cross_rule_count": 8,
        "fixed_position_resolver_profile_count": 2,
        "full_reachable_value_schema_count": 236,
        "intrinsic_rule_count": 34,
        "ledger_octets": _LEDGER_OCTETS,
        "ledger_path": str(_root() / _LEDGER),
        "ledger_sha256": _LEDGER_SHA256,
        "literal_validation_scope": (
            "STATIC_STRUCTURE_PLUS_EXACT_FROZEN_SELECTION;"
            "ATTACHED_INTRINSIC_EXECUTION_DEFERRED_TO_FULL_REGISTRY_EVALUATOR"
        ),
        "rule_application_component_sha256": _COMPONENT_ID,
        "rule_application_descriptor_count": 8,
        "total_expression_node_count": 1057,
        "typed_rule_count": 42,
    }


def test_generator_reproduces_exact_frozen_bytes(tmp_path: Path) -> None:
    expected = (_root() / _LEDGER).read_bytes()
    for seed in ("0", "1", "8675309"):
        output = tmp_path / f"generated-{seed}.json"
        result = subprocess.run(
            (
                sys.executable,
                "-I",
                "-B",
                str(_root() / _VALIDATOR),
                "--repository-root",
                str(_root()),
                "--write-expected-ledger",
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


def test_exact_rule_attachment_application_and_schema_closure() -> None:
    ledger = _load(_LEDGER)
    topology = _load(_TOPOLOGY)
    records = [
        item["type_name"]
        for item in topology["type_descriptors"]
        if item["type_form"] == "RECORD"
    ]
    attachments = ledger["ordered_intrinsic_rule_attachments"]
    assert [item["type_name"] for item in attachments] == records
    attached = [
        rule_id
        for item in attachments
        for rule_id in item["ordered_intrinsic_rule_ids"]
    ]
    assert len(attached) == len(set(attached)) == 34
    assert all(
        rule_id == f"RULE/INTRINSIC/{type_name}/V1"
        for type_name, rule_ids in (
            (item["type_name"], item["ordered_intrinsic_rule_ids"])
            for item in attachments
        )
        for rule_id in rule_ids
    )
    applications = ledger["ordered_rule_application_descriptors"]
    assert len({item["rule_id"] for item in applications}) == 8
    assert len({item["rule_application_id"] for item in applications}) == 8
    assert [item["application_name"] for item in applications] == sorted(
        item["application_name"] for item in applications
    )
    assert ledger["member_value_schema_count"] == 200
    assert ledger["additive_rule_value_schema_count"] == 36
    assert ledger["full_reachable_value_schema_count"] == 236
    assert ledger["closure_evidence"] == {
        "additive_schema_ids_disjoint_from_member_schema_ids": True,
        "all_additive_rule_schemas_reachable": True,
        "all_intrinsic_rules_attached_exactly_once": True,
        "all_cross_rules_applied_exactly_once": True,
        "member_union_additive_equals_full_reachable_catalog": True,
        "union_nodes_remain_rule_attachment_free": True,
    }


def test_validator_is_stdlib_only_and_capture_is_explicitly_one_way() -> None:
    validator_source = (_root() / _VALIDATOR).read_text(encoding="utf-8")
    tree = ast.parse(validator_source)
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
        name.startswith(("riskyieldmm", "pandas", "polars", "numpy"))
        for name in imports
    )
    assert "production provenance capture helper" in (_root() / _CAPTURE).read_text(
        encoding="utf-8"
    )


def test_frozen_literal_authority_matches_current_production_constructors() -> None:
    from riskyieldmm.trading.physical_transport_capacity_contracts_v49f_v8 import (
        RAW_V8_MARKER_CONTRACT_V49F,
        RAW_V8_OPERATION_COUNTER_SCHEMA_V49F,
        capacity_measurement_target_field_registry_v49f_v8,
    )

    authority = _load(_LITERALS)
    assert authority["marker_contract"] == RAW_V8_MARKER_CONTRACT_V49F.as_dict()
    assert (
        authority["operation_counter_schema"]
        == RAW_V8_OPERATION_COUNTER_SCHEMA_V49F.as_dict()
    )
    assert (
        authority["target_field_registry"]
        == capacity_measurement_target_field_registry_v49f_v8().as_dict()
    )
    assert authority["target_field_registry"]["target_field_registry_id"] == (
        "ae01f3a8e53163eefdc77bb4a863710dc851aec22738719639a3c21fe683a618"
    )


def test_static_type_validator_rejects_wrong_same_arity_operator_and_result(
    validator: ModuleType,
    authorities: tuple[
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
    ],
) -> None:
    wrong_operator = _load(_LEDGER)
    target = _rule(
        wrong_operator,
        "RULE/INTRINSIC/TargetObservationRootV2/V1",
    )
    equality = next(
        node for node in target["ordered_expression_nodes"] if node["operator"] == "EQ"
    )
    equality["operator"] = "AND"
    _resign_rule(validator, wrong_operator, target)
    _assert_static_rejection(validator, authorities, wrong_operator)

    wrong_result = _load(_LEDGER)
    target = _rule(
        wrong_result,
        "RULE/INTRINSIC/TargetObservationRootV2/V1",
    )
    boolean_node = next(
        node
        for node in target["ordered_expression_nodes"]
        if node["operator"] == "ARRAY_UNIQUE"
    )
    boolean_node["result_value_schema_id"] = next(
        item["value_schema_id"]
        for item in wrong_result["ordered_additive_rule_value_schemas"]
        if item["schema_kind"] == "SAFE_INTEGER"
    )
    _resign_rule(validator, wrong_result, target)
    _assert_static_rejection(validator, authorities, wrong_result)


def test_tight_operator_rejects_same_kind_wrong_exact_text_schema(
    validator: ModuleType,
    authorities: tuple[
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
    ],
) -> None:
    ledger = _load(_LEDGER)
    _, scalar, _ = authorities
    schemas = {
        item["value_schema_id"]: item for item in scalar["ordered_value_schemas"]
    }
    languages = {
        item["text_language_id"]: item
        for item in scalar["ordered_text_language_descriptors"]
    }
    replacement_schema_id, replacement_literal = next(
        (
            schema_id,
            languages[schema["text_language_id"]]["ordered_literals"][0],
        )
        for schema_id, schema in schemas.items()
        if schema["schema_kind"] == "TEXT"
        and not schema["nullable"]
        and languages[schema["text_language_id"]]["language_kind"]
        in {"LITERAL", "ENUM"}
    )
    target = _rule(
        ledger,
        "RULE/INTRINSIC/CapacityMeasurementLogicalOutputFrameV1/V1",
    )
    opcode = next(
        node
        for node in target["ordered_expression_nodes"]
        if node["operator"] == "INPUT_PATH" and node["typed_member_path"] == ["opcode"]
    )
    opcode.update(
        {
            "operator": "LITERAL",
            "result_value_schema_id": replacement_schema_id,
            "input_binding_name": None,
            "typed_member_path": [],
            "literal_value_schema_id": replacement_schema_id,
            "literal_value": replacement_literal,
        }
    )
    _resign_rule(validator, ledger, target)
    _assert_static_rejection(validator, authorities, ledger)


def test_expression_graph_and_metadata_adversaries_are_rejected(
    validator: ModuleType,
    authorities: tuple[
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
    ],
) -> None:
    forward = _load(_LEDGER)
    target = _rule(forward, "RULE/INTRINSIC/TargetObservationRootV2/V1")
    consumer = next(
        node
        for node in target["ordered_expression_nodes"]
        if node["ordered_operand_positions"]
    )
    consumer["ordered_operand_positions"][0] = consumer["expression_position"]
    _resign_rule(validator, forward, target)
    _assert_static_rejection(validator, authorities, forward)

    unreachable = _load(_LEDGER)
    target = _rule(
        unreachable,
        "RULE/INTRINSIC/TargetObservationContextV2/V1",
    )
    literal = copy.deepcopy(
        next(
            node
            for node in target["ordered_expression_nodes"]
            if node["operator"] == "LITERAL"
        )
    )
    literal["expression_position"] = 1
    for node in target["ordered_expression_nodes"]:
        node["expression_position"] += 1
        node["ordered_operand_positions"] = [
            position + 1 for position in node["ordered_operand_positions"]
        ]
    target["ordered_expression_nodes"].insert(0, literal)
    target["maximum_expression_nodes"] += 1
    target["root_expression_position"] += 1
    _resign_rule(validator, unreachable, target)
    _assert_static_rejection(validator, authorities, unreachable)

    extra_metadata = _load(_LEDGER)
    target = _rule(
        extra_metadata,
        "RULE/INTRINSIC/TargetObservationRootV2/V1",
    )
    target["ordered_expression_nodes"][0]["unexpected_metadata"] = False
    _resign_rule(validator, extra_metadata, target)
    _assert_static_rejection(validator, authorities, extra_metadata)


def test_unused_binding_and_schema_closure_adversaries_are_rejected(
    validator: ModuleType,
    authorities: tuple[
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
    ],
) -> None:
    unused_binding = _load(_LEDGER)
    target = _rule(
        unused_binding,
        "RULE/CROSS/COUNTER_SNAPSHOT_SCHEMA_V1",
    )
    extra = copy.deepcopy(target["ordered_rule_input_bindings"][0])
    extra["binding_name"] = "unused_counter_snapshot"
    target["ordered_rule_input_bindings"].append(extra)
    _resign_rule(validator, unused_binding, target)
    _assert_static_rejection(validator, authorities, unused_binding)

    extra_schema = _load(_LEDGER)
    payload = validator._schema_payload(
        schema_kind="SAFE_INTEGER",
        nullable=False,
        integer_minimum=123_456,
        integer_maximum=123_457,
    )
    identifier = validator._semantic_id(validator.VALUE_SCHEMA_DOMAIN, payload)
    extra_schema["ordered_additive_rule_value_schemas"].append(
        {**payload, "value_schema_id": identifier}
    )
    extra_schema["ordered_additive_rule_value_schemas"].sort(
        key=lambda item: item["value_schema_id"]
    )
    extra_schema["additive_rule_value_schema_count"] += 1
    extra_schema["full_reachable_value_schema_count"] += 1
    _resign_component(validator, extra_schema)
    _assert_static_rejection(validator, authorities, extra_schema)


def test_attachment_dependency_and_application_adversaries_are_rejected(
    validator: ModuleType,
    authorities: tuple[
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
    ],
) -> None:
    duplicate_attachment = _load(_LEDGER)
    source = next(
        item
        for item in duplicate_attachment["ordered_intrinsic_rule_attachments"]
        if item["ordered_intrinsic_rule_ids"]
    )
    empty = next(
        item
        for item in duplicate_attachment["ordered_intrinsic_rule_attachments"]
        if not item["ordered_intrinsic_rule_ids"]
    )
    empty["ordered_intrinsic_rule_ids"] = list(source["ordered_intrinsic_rule_ids"])
    _resign_component(validator, duplicate_attachment)
    _assert_static_rejection(validator, authorities, duplicate_attachment)

    duplicate_edge = _load(_LEDGER)
    duplicate_edge["ordered_rule_dependency_edges"].append(
        copy.deepcopy(duplicate_edge["ordered_rule_dependency_edges"][0])
    )
    _resign_component(validator, duplicate_edge)
    _assert_static_rejection(validator, authorities, duplicate_edge)

    off_by_one = _load(_LEDGER)
    application = _application(
        off_by_one,
        "APPLY/V2_OBSERVATION_FIELDS_REGISTRY_V1",
    )
    application["maximum_rule_evaluations"] -= 1
    _resign_application(validator, off_by_one, application)
    _assert_static_rejection(validator, authorities, off_by_one)

    wrong_resolver = _load(_LEDGER)
    application = _application(
        wrong_resolver,
        "APPLY/V2_ROOT_OBSERVATION_MEMBERSHIP_V1",
    )
    application["ordered_sequence_input_bindings"][0][
        "fixed_position_resolver_profile_id"
    ] = "73acbeea28d638acb77aab44dad201e08cc5267e830ddd4714d54aa70813b54b"
    _resign_application(validator, wrong_resolver, application)
    _assert_static_rejection(validator, authorities, wrong_resolver)


def test_composite_literal_mutation_is_rejected_after_resigning(
    validator: ModuleType,
    authorities: tuple[
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
    ],
) -> None:
    ledger = _load(_LEDGER)
    target = _rule(ledger, "RULE/INTRINSIC/TargetFieldRegistryV1/V1")
    array_literal = next(
        node
        for node in target["ordered_expression_nodes"]
        if node["operator"] == "LITERAL"
        and type(node["literal_value"]) is list
        and len(node["literal_value"]) == 25
    )
    array_literal["literal_value"][0], array_literal["literal_value"][1] = (
        array_literal["literal_value"][1],
        array_literal["literal_value"][0],
    )
    _resign_rule(validator, ledger, target)
    _assert_static_rejection(validator, authorities, ledger)


def test_bounded_reader_rejects_symlink_and_oversized_input(
    tmp_path: Path,
) -> None:
    symlink = tmp_path / "ledger-link.json"
    symlink.symlink_to(_root() / _LEDGER)
    _assert_controlled_rejection(_run(symlink))

    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b" " * (8_388_608 + 1))
    _assert_controlled_rejection(_run(oversized))


def test_bounded_reader_rejects_fifo_and_directory(tmp_path: Path) -> None:
    fifo = tmp_path / "ledger.fifo"
    os.mkfifo(fifo)
    _assert_controlled_rejection(_run(fifo))
    _assert_controlled_rejection(_run(tmp_path))


@pytest.mark.parametrize(
    "raw",
    [
        b'{"a":1,"a":1}\n',
        b'{"floating":1.5}\n',
        b'{"surrogate":"\\ud800"}\n',
        b'{"huge":' + (b"9" * 5_000) + b"}\n",
    ],
)
def test_json_adversaries_fail_closed_without_traceback(
    tmp_path: Path,
    raw: bytes,
) -> None:
    path = tmp_path / "adversarial.json"
    path.write_bytes(raw)
    _assert_controlled_rejection(_run(path))

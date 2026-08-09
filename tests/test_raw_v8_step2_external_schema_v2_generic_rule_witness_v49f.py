from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, NoReturn

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PATH = (
    ROOT / "scripts/tests/validate_raw_v8_step2_external_schema_v2_rule_runtime_v49f.py"
)
WITNESS_PATH = (
    ROOT
    / "scripts/tests/raw_v8_step2_external_schema_v2_generic_rule_witness_v49f.json"
)

WITNESS_OCTETS = 296_275
WITNESS_PHYSICAL_SHA256 = (
    "c8a3748755489944c96d7bb22107cb6eb7c54d3731f6d4d2bd070a7789a5b595"
)
WITNESS_SEMANTIC_SHA256 = (
    "10fc6bfd9b1f04baf1bb0335c744185d9f0f0482bd493fa2ad2b0a2a32d370e7"
)
WITNESS_IDENTITY_DOMAIN = "RiskYieldMMRawV8Step2ExternalSchemaV2GenericRuleWitnessV1"
SAFE_INTEGER_MAXIMUM = 9_007_199_254_740_991

EXPECTED_NONCLAIMS = [
    (
        "This artifact is an independent generic-rule test witness, not a "
        "schema, literal, production, calibration, trading, or acceptance "
        "authority."
    ),
    (
        "Candidate-extracted values are frozen here so tests never read "
        "test_output; their presence does not accept the candidate inventory."
    ),
    (
        "Positive/negative witnesses establish the current 33 generic rule "
        "roots only; the nine complex rules, eight applications, maxima, and "
        "production adapters remain outside scope."
    ),
]
EXPECTED_SOURCE_CANDIDATE = {
    "inventory_sha256": (
        "4c078be059a2a8cd5c5388727e5d6bff7aaabaeb3ad6b0a999c1fede2502140f"
    ),
    "physical_octets": 2_849_662,
    "physical_sha256": (
        "3b80a2569155a9655215a1e5e61ae63eac482e83c1d28a87e910a29a95b91252"
    ),
    "relative_path_for_provenance_only": (
        "test_output/raw_v8_step2_inventory_v2_candidate.json"
    ),
}

SPEC = importlib.util.spec_from_file_location(
    "raw_v8_rule_runtime_generic_witness_v49f",
    RUNTIME_PATH,
)
assert SPEC is not None and SPEC.loader is not None
runtime_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runtime_module
SPEC.loader.exec_module(runtime_module)


def _reject_json_float(value: str) -> NoReturn:
    raise ValueError(f"floating-point JSON is forbidden: {value}")


def _reject_json_constant(value: str) -> NoReturn:
    raise ValueError(f"non-finite JSON is forbidden: {value}")


def _parse_json_integer(value: str) -> int:
    if len(value) > 17:
        raise ValueError("JSON integer exceeds the predecode digit bound")
    parsed = int(value)
    if not -SAFE_INTEGER_MAXIMUM <= parsed <= SAFE_INTEGER_MAXIMUM:
        raise ValueError(f"JSON integer is outside the safe-I-JSON domain: {value}")
    return parsed


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _assert_exact_json(value: Any, *, path: tuple[str | int, ...] = ()) -> None:
    if value is None or type(value) in {bool, str}:
        return
    if type(value) is int:
        assert -SAFE_INTEGER_MAXIMUM <= value <= SAFE_INTEGER_MAXIMUM, path
        return
    if type(value) is list:
        for index, member in enumerate(value):
            _assert_exact_json(member, path=(*path, index))
        return
    if type(value) is dict:
        for key, member in value.items():
            assert type(key) is str, (*path, key)
            _assert_exact_json(member, path=(*path, key))
        return
    raise AssertionError(f"non-exact JSON value at {path}: {type(value).__name__}")


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _pretty_bytes(value: Any) -> bytes:
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


def _load_witness() -> dict[str, Any]:
    raw = WITNESS_PATH.read_bytes()
    assert len(raw) == WITNESS_OCTETS
    assert hashlib.sha256(raw).hexdigest() == WITNESS_PHYSICAL_SHA256
    document = json.loads(
        raw,
        object_pairs_hook=_strict_object,
        parse_int=_parse_json_integer,
        parse_float=_reject_json_float,
        parse_constant=_reject_json_constant,
    )
    assert type(document) is dict
    _assert_exact_json(document)
    assert _pretty_bytes(document) == raw
    return document


def _traverse(value: Any, path: list[str | int]) -> Any:
    current = value
    for member in path:
        assert type(member) in {str, int}
        if type(member) is str:
            assert type(current) is dict and member in current
        else:
            assert type(current) is list and 0 <= member < len(current)
        current = current[member]
    return current


def _resolve_binding(
    runtime: Any,
    fixture_records: dict[str, Any],
    reference: dict[str, Any],
) -> Any:
    assert type(reference) is dict and len(reference) == 1
    reference_kind, reference_value = next(iter(reference.items()))
    if reference_kind == "inline_value":
        return copy.deepcopy(reference_value)
    assert reference_kind in {"fixture_path", "authority_path"}
    assert type(reference_value) is list and reference_value
    if reference_kind == "fixture_path":
        fixture_name, *member_path = reference_value
        assert type(fixture_name) is str and fixture_name in fixture_records
        fixture = fixture_records[fixture_name]
        assert type(fixture) is dict and set(fixture) == {"provenance", "value"}
        source = fixture["value"]
        return copy.deepcopy(_traverse(source, member_path))
    return copy.deepcopy(_traverse(runtime.literal_authority, reference_value))


def _apply_mutation(bindings: dict[str, Any], mutation: dict[str, Any]) -> None:
    assert type(mutation) is dict
    operation = mutation.get("mutation")
    common_keys = {"binding_name", "mutation", "typed_path"}
    expected_keys = {
        "SET": common_keys | {"value"},
        "ADD": common_keys | {"integer_delta"},
        "REVERSE": common_keys,
    }
    assert operation in expected_keys
    assert set(mutation) == expected_keys[operation]
    binding_name = mutation["binding_name"]
    path = mutation["typed_path"]
    assert type(binding_name) is str and binding_name in bindings
    assert type(path) is list and path
    parent = _traverse(bindings[binding_name], path[:-1])
    final = path[-1]
    assert type(final) in {str, int}
    if type(final) is str:
        assert type(parent) is dict and final in parent
    else:
        assert type(parent) is list and 0 <= final < len(parent)
    if operation == "SET":
        parent[final] = copy.deepcopy(mutation["value"])
    elif operation == "ADD":
        delta = mutation["integer_delta"]
        assert type(parent[final]) is int and type(delta) is int
        parent[final] += delta
    else:
        target = parent[final]
        assert type(target) is list and len(target) >= 2
        target.reverse()


def _rehash_binding(
    runtime: Any,
    bindings: dict[str, Any],
    rehash: dict[str, Any],
) -> None:
    assert type(rehash) is dict
    assert set(rehash) == {"binding_name", "type_name"}
    binding_name = rehash["binding_name"]
    type_name = rehash["type_name"]
    assert type(binding_name) is str and binding_name in bindings
    assert type(type_name) is str and type_name in runtime.records
    descriptor = runtime.records[type_name]
    identity_field = descriptor["identity_field"]
    assert type(identity_field) is str
    value = bindings[binding_name]
    assert type(value) is dict and identity_field in value
    payload = {
        member_name: value[member_name]
        for member_name in descriptor["identity_payload_member_order"]
    }
    value[identity_field] = runtime_module._semantic_id(
        descriptor["described_record_domain"],
        payload,
    )


def _validate_rule_bindings(
    runtime: Any,
    rule_id: str,
    bindings: dict[str, Any],
) -> None:
    descriptors = runtime.rules[rule_id]["ordered_rule_input_bindings"]
    assert set(bindings) == {descriptor["binding_name"] for descriptor in descriptors}
    for descriptor in descriptors:
        runtime.validate_schema(
            descriptor["expected_value_schema_id"],
            bindings[descriptor["binding_name"]],
        )


@pytest.fixture(scope="module")
def runtime() -> Any:
    return runtime_module.ExternalSchemaV2Runtime.load(ROOT)


@pytest.fixture(scope="module")
def witness() -> dict[str, Any]:
    return _load_witness()


def test_generic_rule_witness_is_hash_pinned_and_explicitly_non_authoritative(
    runtime: Any,
    witness: dict[str, Any],
) -> None:
    assert set(witness) == {
        "artifact_version",
        "canonicalization_version",
        "component_status",
        "fixture_records",
        "generic_rule_witness_sha256",
        "measurement_schema_version",
        "nonclaims",
        "ordered_cases",
        "source_candidate",
        "source_literal_authority",
    }
    assert witness["artifact_version"] == (
        "riskyieldmm.raw_v8_step2_external_schema_v2.generic_rule_witness.v1"
    )
    assert witness["component_status"] == (
        "TEST_WITNESS_NOT_SCHEMA_OR_PRODUCTION_AUTHORITY"
    )
    assert witness["canonicalization_version"] == (
        runtime_module.CANONICALIZATION_VERSION
    )
    assert witness["measurement_schema_version"] == (
        runtime_module.MEASUREMENT_SCHEMA_VERSION
    )
    assert witness["nonclaims"] == EXPECTED_NONCLAIMS
    assert witness["source_candidate"] == EXPECTED_SOURCE_CANDIDATE
    assert witness["source_literal_authority"] == {
        "physical_octets": runtime_module.RULE_LITERAL_AUTHORITY_OCTETS,
        "physical_sha256": runtime_module.RULE_LITERAL_AUTHORITY_SHA256,
        "rule_literal_authority_sha256": (
            runtime.literal_authority["rule_literal_authority_sha256"]
        ),
    }
    assert witness["generic_rule_witness_sha256"] == WITNESS_SEMANTIC_SHA256
    semantic_payload = {
        key: value
        for key, value in witness.items()
        if key != "generic_rule_witness_sha256"
    }
    assert (
        hashlib.sha256(
            _canonical_bytes(
                {
                    "domain": WITNESS_IDENTITY_DOMAIN,
                    "payload": semantic_payload,
                }
            )
        ).hexdigest()
        == WITNESS_SEMANTIC_SHA256
    )


def test_every_generic_rule_has_schema_valid_true_and_false_witnesses(
    runtime: Any,
    witness: dict[str, Any],
) -> None:
    fixture_records = witness["fixture_records"]
    cases = witness["ordered_cases"]
    assert type(fixture_records) is dict
    assert type(cases) is list and len(cases) == 33
    rule_ids = [case["rule_id"] for case in cases]
    assert rule_ids == sorted(rule_ids)
    assert len(set(rule_ids)) == len(rule_ids)
    assert set(rule_ids) == runtime.generic_rule_ids

    for case in cases:
        rule_id = case["rule_id"]
        assert set(case) == {
            "expected_direct_expression_nodes",
            "expected_intrinsic_rule_invocations",
            "expected_total_expression_nodes",
            "negative_mutations",
            "ordered_rehash_bindings",
            "positive_bindings",
            "rule_id",
        }, rule_id
        bindings = {
            binding_name: _resolve_binding(runtime, fixture_records, reference)
            for binding_name, reference in case["positive_bindings"].items()
        }
        _validate_rule_bindings(runtime, rule_id, bindings)
        positive = runtime.evaluate_rule(rule_id, bindings)
        assert positive.rule_id == rule_id
        assert positive.root_value is True, rule_id
        assert (
            positive.direct_expression_nodes
            == (case["expected_direct_expression_nodes"])
        ), rule_id
        assert (
            positive.intrinsic_rule_invocations
            == (case["expected_intrinsic_rule_invocations"])
        ), rule_id
        assert (
            positive.total_expression_nodes == (case["expected_total_expression_nodes"])
        ), rule_id

        negative_bindings = copy.deepcopy(bindings)
        mutations = case["negative_mutations"]
        rehashes = case["ordered_rehash_bindings"]
        assert type(mutations) is list and mutations
        assert type(rehashes) is list
        for mutation in mutations:
            _apply_mutation(negative_bindings, mutation)
        for rehash in rehashes:
            _rehash_binding(runtime, negative_bindings, rehash)
        _validate_rule_bindings(runtime, rule_id, negative_bindings)

        negative = runtime.evaluate_rule(
            rule_id,
            negative_bindings,
            require_true=False,
        )
        assert negative.rule_id == rule_id
        assert negative.root_value is False, rule_id
        assert (
            negative.direct_expression_nodes
            == (case["expected_direct_expression_nodes"])
        ), rule_id
        assert (
            negative.intrinsic_rule_invocations
            == (case["expected_intrinsic_rule_invocations"])
        ), rule_id
        assert (
            negative.total_expression_nodes == (case["expected_total_expression_nodes"])
        ), rule_id
        with pytest.raises(runtime_module.BusinessRuleFalse) as caught:
            runtime.evaluate_rule(rule_id, negative_bindings)
        assert caught.value.failure_class == "BUSINESS_RULE_FALSE", rule_id

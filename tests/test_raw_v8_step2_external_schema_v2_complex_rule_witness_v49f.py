from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, NoReturn

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PATH = (
    ROOT / "scripts/tests/validate_raw_v8_step2_external_schema_v2_rule_runtime_v49f.py"
)
WITNESS_PATH = (
    ROOT
    / "scripts/tests/raw_v8_step2_external_schema_v2_complex_rule_witness_v49f.json"
)

WITNESS_OCTETS = 456_162
WITNESS_PHYSICAL_SHA256 = (
    "d74bbc6bd98de6f143bd1bfcc9c2660f8923713ac901911289939dfd12712e4b"
)
WITNESS_SEMANTIC_SHA256 = (
    "ac01e4b1eee0ae3ee394818f230380a71dc778f7d7c688d084da1f9aebb81e2a"
)
WITNESS_IDENTITY_DOMAIN = "RiskYieldMMRawV8Step2ExternalSchemaV2ComplexRuleWitnessV1"
SAFE_INTEGER_MAXIMUM = 9_007_199_254_740_991

EXPECTED_RULE_IDS = {
    "RULE/CROSS/FIELD_OBSERVATION_FROZEN_REGISTRY_V1",
    "RULE/CROSS/OPERATION_RESULT_SIGNED_SPEC_V1",
    "RULE/CROSS/SELECTOR_MARKER_CONTRACT_V1",
    "RULE/CROSS/V2_OBSERVATION_AGGREGATE_REGISTRY_V1",
    "RULE/CROSS/V2_OBSERVATION_FIELD_REGISTRY_V1",
    "RULE/CROSS/V2_ROOT_SELECTOR_LIFECYCLE_V1",
    "RULE/INTRINSIC/CheckpointSelectorV1/V1",
    "RULE/INTRINSIC/OperationCounterSnapshotV1/V1",
    "RULE/INTRINSIC/TargetFieldObservationV1/V1",
}
EXPECTED_NONCLAIMS = [
    (
        "This artifact is an independent complex-rule test witness, not a "
        "schema, literal, production, calibration, trading, or acceptance "
        "authority."
    ),
    (
        "Candidate- and generator-derived values are frozen here; runtime "
        "tests never read test_output, and provenance does not accept the "
        "candidate or prove that the current generator reproduces it."
    ),
    (
        "Registry, marker-contract, and counter-schema operands resolve only "
        "from the separately hash-pinned literal authority; copied mutations "
        "are adversarial inputs and never replacement authority."
    ),
    (
        "The selector-marker business-false probe intentionally violates the "
        "selector intrinsic precondition; no exact-authority business-false "
        "is claimed for an intrinsically valid selector and the frozen marker "
        "contract."
    ),
    (
        "The compact root matrix covers startup, ordinary selector-free, "
        "selector-bound empty, and selector-bound one-entry branches; it does "
        "not materialize the 67-observation max64 root."
    ),
    (
        "Expected true, business-false, and evaluation-failure outcomes are "
        "conformance vectors; this artifact alone is not execution evidence "
        "for applications, maxima, production adapters, or Stage-1 acceptance."
    ),
]

SPEC = importlib.util.spec_from_file_location(
    "raw_v8_rule_runtime_complex_witness_v49f",
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


def _resolve_reference(
    runtime: Any,
    fixture_records: dict[str, Any],
    reference: dict[str, Any],
) -> Any:
    assert type(reference) is dict and len(reference) == 1
    reference_kind, reference_value = next(iter(reference.items()))
    if reference_kind == "inline_value":
        return copy.deepcopy(reference_value)
    if reference_kind == "ordered_values":
        assert type(reference_value) is list
        return [
            _resolve_reference(runtime, fixture_records, member)
            for member in reference_value
        ]
    assert reference_kind in {"fixture_path", "authority_path"}
    assert type(reference_value) is list and reference_value
    if reference_kind == "fixture_path":
        fixture_name, *member_path = reference_value
        assert type(fixture_name) is str and fixture_name in fixture_records
        fixture = fixture_records[fixture_name]
        assert type(fixture) is dict and set(fixture) == {"provenance", "value"}
        return copy.deepcopy(_traverse(fixture["value"], member_path))
    return copy.deepcopy(_traverse(runtime.literal_authority, reference_value))


def _set_path(
    bindings: dict[str, Any], binding_name: str, path: list[Any], value: Any
) -> None:
    assert type(binding_name) is str and binding_name in bindings
    assert type(path) is list and path
    parent = _traverse(bindings[binding_name], path[:-1])
    final = path[-1]
    assert type(final) in {str, int}
    if type(final) is str:
        assert type(parent) is dict and final in parent
    else:
        assert type(parent) is list and 0 <= final < len(parent)
    parent[final] = copy.deepcopy(value)


def _rehash_record(runtime: Any, value: Any, type_name: str) -> None:
    assert type(type_name) is str and type_name in runtime.records
    descriptor = runtime.records[type_name]
    identity_field = descriptor["identity_field"]
    assert type(identity_field) is str
    assert type(value) is dict and identity_field in value
    payload = {
        member_name: value[member_name]
        for member_name in descriptor["identity_payload_member_order"]
    }
    value[identity_field] = runtime_module._semantic_id(
        descriptor["described_record_domain"],
        payload,
    )


def _apply_transform(
    runtime: Any,
    bindings: dict[str, Any],
    transform: dict[str, Any],
) -> None:
    assert type(transform) is dict
    operation = transform.get("transform")
    binding_name = transform.get("binding_name")
    path = transform.get("typed_path")
    assert type(binding_name) is str and binding_name in bindings
    assert type(path) is list
    if operation == "SET":
        assert set(transform) == {"binding_name", "transform", "typed_path", "value"}
        _set_path(bindings, binding_name, path, transform["value"])
        return
    if operation == "ADD":
        assert set(transform) == {
            "binding_name",
            "integer_delta",
            "transform",
            "typed_path",
        }
        current = _traverse(bindings[binding_name], path)
        assert type(current) is int and type(transform["integer_delta"]) is int
        _set_path(
            bindings,
            binding_name,
            path,
            current + transform["integer_delta"],
        )
        return
    if operation == "SET_FROM_BINDING":
        assert set(transform) == {
            "binding_name",
            "source_binding_name",
            "source_typed_path",
            "transform",
            "typed_path",
        }
        source_binding = transform["source_binding_name"]
        source_path = transform["source_typed_path"]
        assert type(source_binding) is str and source_binding in bindings
        assert type(source_path) is list
        _set_path(
            bindings,
            binding_name,
            path,
            _traverse(bindings[source_binding], source_path),
        )
        return
    if operation == "PROJECT_MEMBER":
        assert set(transform) == {
            "binding_name",
            "source_binding_name",
            "source_typed_path",
            "transform",
            "typed_path",
        }
        source_binding = transform["source_binding_name"]
        source_path = transform["source_typed_path"]
        assert type(source_binding) is str and source_binding in bindings
        assert type(source_path) is list and source_path
        source = bindings[source_binding]
        assert type(source) is list
        projected = [_traverse(member, source_path) for member in source]
        _set_path(bindings, binding_name, path, projected)
        return
    assert operation == "REHASH_RECORD"
    assert set(transform) == {
        "binding_name",
        "transform",
        "type_name",
        "typed_path",
    }
    _rehash_record(
        runtime,
        _traverse(bindings[binding_name], path),
        transform["type_name"],
    )


def _materialize_case(
    runtime: Any,
    witness: dict[str, Any],
    case: dict[str, Any],
) -> dict[str, Any]:
    bindings = {
        binding_name: _resolve_reference(
            runtime,
            witness["fixture_records"],
            reference,
        )
        for binding_name, reference in case["bindings"].items()
    }
    for transform in case["ordered_transforms"]:
        _apply_transform(runtime, bindings, transform)
    return bindings


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


def test_complex_rule_witness_is_hash_pinned_and_non_authoritative(
    runtime: Any,
    witness: dict[str, Any],
) -> None:
    assert set(witness) == {
        "artifact_version",
        "canonicalization_version",
        "component_status",
        "complex_rule_witness_sha256",
        "fixture_records",
        "measurement_schema_version",
        "nonclaims",
        "ordered_cases",
        "source_candidate",
        "source_generator",
        "source_literal_authority",
    }
    assert witness["artifact_version"] == (
        "riskyieldmm.raw_v8_step2_external_schema_v2.complex_rule_witness.v1"
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
    assert witness["source_candidate"] == {
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
        "schema_version": "riskyieldmm.raw_v8_step2_inventory.v2",
    }
    assert witness["source_generator"] == {
        "physical_octets": 249_703,
        "physical_sha256": (
            "44d73d3141a921c0b270f61808e1dd561cb4e18ce9b82175c1035cae9fe1a86b"
        ),
        "relative_path_for_constructor_lineage_only": (
            "scripts/tests/generate_raw_v8_step2_inventory_v49f.py"
        ),
        "reproduction_claim": False,
    }
    assert witness["source_literal_authority"] == {
        "physical_octets": runtime_module.RULE_LITERAL_AUTHORITY_OCTETS,
        "physical_sha256": runtime_module.RULE_LITERAL_AUTHORITY_SHA256,
        "rule_literal_authority_sha256": (
            runtime.literal_authority["rule_literal_authority_sha256"]
        ),
    }
    assert witness["complex_rule_witness_sha256"] == WITNESS_SEMANTIC_SHA256
    semantic_payload = {
        key: value
        for key, value in witness.items()
        if key != "complex_rule_witness_sha256"
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


def test_frozen_fixtures_are_self_pinned_and_do_not_read_candidate_at_runtime(
    runtime: Any,
    witness: dict[str, Any],
) -> None:
    fixtures = witness["fixture_records"]
    assert type(fixtures) is dict and len(fixtures) == 11
    assert list(fixtures) == sorted(fixtures)
    for fixture_name, fixture in fixtures.items():
        assert type(fixture) is dict
        assert set(fixture) == {"provenance", "value"}
        provenance = fixture["provenance"]
        assert provenance["kind"] in {
            "FROZEN_CANDIDATE_EXTRACT",
            "FROZEN_CANDIDATE_EXTRACT_THEN_CONSTRUCTED_SLICE",
        }
        assert (
            provenance["frozen_value_canonical_sha256"]
            == hashlib.sha256(_canonical_bytes(fixture["value"])).hexdigest()
        ), fixture_name

    coverage = copy.deepcopy(fixtures["selector_ingress_coverage"]["value"])
    coverage["selector_length"] = 1
    coverage["ordered_entries"] = coverage["ordered_entries"][:1]
    coverage["ordered_checkpoint_selector_entry_ids"] = coverage[
        "ordered_checkpoint_selector_entry_ids"
    ][:1]
    _rehash_record(runtime, coverage, "CheckpointSelectorV1")
    assert coverage == fixtures["selector_ingress_one"]["value"]

    counter_snapshot = fixtures["counter_snapshot"]["value"]
    assert (
        counter_snapshot["counter_schema_id"]
        == (runtime.literal_authority["operation_counter_schema"]["counter_schema_id"])
    )


def test_complex_case_matrix_is_complete_and_every_binding_is_schema_valid(
    runtime: Any,
    witness: dict[str, Any],
) -> None:
    cases = witness["ordered_cases"]
    assert type(cases) is list and len(cases) == 44
    identities = [(case["rule_id"], case["case_id"]) for case in cases]
    assert identities == sorted(identities)
    assert len(set(identities)) == len(identities)
    assert {case["rule_id"] for case in cases} == EXPECTED_RULE_IDS
    assert EXPECTED_RULE_IDS == runtime.complex_rule_ids

    outcomes_by_rule: dict[str, set[str]] = defaultdict(set)
    all_tags: set[str] = set()
    for case in cases:
        assert set(case) == {
            "bindings",
            "case_id",
            "coverage_tags",
            "expected_direct_expression_nodes",
            "expected_failure_class",
            "expected_intrinsic_rule_invocations",
            "expected_outcome",
            "expected_total_expression_nodes",
            "ordered_transforms",
            "precondition_note",
            "rule_id",
        }
        assert case["expected_outcome"] in {
            "TRUE",
            "BUSINESS_FALSE",
            "EVALUATION_FAILURE",
        }
        if case["expected_outcome"] == "EVALUATION_FAILURE":
            assert case["expected_failure_class"] in {
                "UNRESOLVED_REFERENCE",
                "IMPOSSIBLE_STATE",
                "WORK_BOUND_EXCEEDED",
            }
        else:
            assert case["expected_failure_class"] is None
        outcomes_by_rule[case["rule_id"]].add(case["expected_outcome"])
        all_tags.update(case["coverage_tags"])
        bindings = _materialize_case(runtime, witness, case)
        _validate_rule_bindings(runtime, case["rule_id"], bindings)

    assert all(
        {"TRUE", "BUSINESS_FALSE"} <= outcomes_by_rule[rule_id]
        for rule_id in EXPECTED_RULE_IDS
    )
    assert {
        "RESULT_KIND_ACK_DEADLINE_EXPIRY",
        "RESULT_KIND_INGRESS",
        "RESULT_KIND_LOCAL_SHUTDOWN",
        "RESULT_KIND_SUBSCRIPTION_DISPATCH",
    } <= all_tags
    assert {
        "VALUE_BOOL",
        "VALUE_DURATION_BOUND",
        "VALUE_FIXED_UINT_MAP",
        "VALUE_NULL",
        "VALUE_OPTIONAL_TEXT",
        "VALUE_OPTIONAL_UINT",
        "VALUE_TEXT",
        "VALUE_TEXT_LIST",
        "VALUE_UINT",
        "VALUE_UINT_LIST",
    } <= all_tags
    assert {
        "BITMAP",
        "A1_FIFO",
        "SELECTOR_EMPTY",
        "SELECTOR_MAXIMUM_64",
        "ROOT_STARTUP_RECOVERY",
        "ROOT_SELECTOR_FREE",
        "ROOT_SELECTOR_BOUND_EMPTY",
        "ROOT_SELECTOR_BOUND_NONEMPTY",
    } <= all_tags


def test_complex_cases_execute_once_runtime_support_is_complete(
    runtime: Any,
    witness: dict[str, Any],
) -> None:
    probe = next(
        case for case in witness["ordered_cases"] if case["expected_outcome"] == "TRUE"
    )
    probe_bindings = _materialize_case(runtime, witness, probe)
    try:
        runtime.evaluate_rule(probe["rule_id"], probe_bindings, require_true=False)
    except runtime_module.UnsupportedRule:
        pytest.skip("complex-rule runtime is not implemented yet")

    for case in witness["ordered_cases"]:
        bindings = _materialize_case(runtime, witness, case)
        outcome = case["expected_outcome"]
        if outcome == "EVALUATION_FAILURE":
            with pytest.raises(runtime_module.RuntimeFailure) as caught:
                runtime.evaluate_rule(
                    case["rule_id"],
                    bindings,
                    require_true=False,
                )
            assert not isinstance(caught.value, runtime_module.UnsupportedRule)
            assert caught.value.failure_class == case["expected_failure_class"]
            continue

        evidence = runtime.evaluate_rule(
            case["rule_id"],
            bindings,
            require_true=False,
        )
        assert evidence.root_value is (outcome == "TRUE"), (
            case["rule_id"],
            case["case_id"],
        )
        assert (
            evidence.direct_expression_nodes
            == (case["expected_direct_expression_nodes"])
        )
        assert (
            evidence.intrinsic_rule_invocations
            == (case["expected_intrinsic_rule_invocations"])
        )
        assert (
            evidence.total_expression_nodes == (case["expected_total_expression_nodes"])
        )
        if outcome == "BUSINESS_FALSE":
            with pytest.raises(runtime_module.BusinessRuleFalse):
                runtime.evaluate_rule(case["rule_id"], bindings)

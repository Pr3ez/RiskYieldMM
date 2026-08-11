from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, NoReturn

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PATH = (
    ROOT / "scripts/tests/validate_raw_v8_step2_external_schema_v2_rule_runtime_v49f.py"
)
WITNESS_PATH = (
    ROOT / "scripts/tests/raw_v8_step2_external_schema_v2_application_witness_v49f.json"
)

WITNESS_OCTETS = 697_208
WITNESS_PHYSICAL_SHA256 = (
    "d2f40badc85c58965a72e52fd98bfebbd4caf3335ec5a0415a89294cc3fb3415"
)
WITNESS_SEMANTIC_SHA256 = (
    "1d859520c24a973a5a157139183ae24ef0184ce4cede5531bb4b442227e1a8ba"
)
WITNESS_IDENTITY_DOMAIN = "RiskYieldMMRawV8Step2ExternalSchemaV2ApplicationWitnessV1"
SAFE_INTEGER_MAXIMUM = 9_007_199_254_740_991

EXPECTED_APPLICATIONS = {
    "APPLY/COUNTER_SNAPSHOT_SCHEMA_V1": ("RECORD_TUPLE", 1),
    "APPLY/FIELD_OBSERVATION_FROZEN_REGISTRY_V1": ("RECORD_TUPLE", 1),
    "APPLY/OPERATION_RESULT_SIGNED_SPEC_V1": ("RECORD_TUPLE", 1),
    "APPLY/SELECTOR_MARKER_CONTRACT_V1": ("RECORD_TUPLE", 1),
    "APPLY/V2_OBSERVATION_AGGREGATE_REGISTRY_V1": ("RECORD_TUPLE", 1),
    "APPLY/V2_OBSERVATION_FIELDS_REGISTRY_V1": ("ARRAY_EACH", 185),
    "APPLY/V2_ROOT_OBSERVATION_MEMBERSHIP_V1": (
        "FOR_EACH_FIXED_POSITION_BINDING",
        67,
    ),
    "APPLY/V2_ROOT_SELECTOR_LIFECYCLE_V1": ("FIXED_SEQUENCE_AGGREGATE", 1),
}
EXPECTED_RESOLVER_IDS = [
    "73acbeea28d638acb77aab44dad201e08cc5267e830ddd4714d54aa70813b54b",
    "87224ef058fff2867da671aec58d53c0a06fc9542ae84ad0378af6db48349daf",
]
EXPECTED_FAILURE_CLASSES = {
    None,
    "BUSINESS_RULE_FALSE",
    "MALFORMED_OPERAND",
    "UNRESOLVED_AUTHORITY",
    "TYPE_OR_UNION_MISMATCH",
    "IMPOSSIBLE_BRANCH",
    "WORK_BOUND_EXCEEDED",
}

SPEC = importlib.util.spec_from_file_location(
    "raw_v8_rule_runtime_application_witness_v49f",
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
        raise ValueError(f"JSON integer is outside safe I-JSON: {value}")
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
    raise AssertionError(f"non-exact JSON at {path}: {type(value).__name__}")


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


def _set_path(value: Any, path: list[str | int], replacement: Any) -> None:
    assert path
    parent = _traverse(value, path[:-1])
    final = path[-1]
    if type(final) is str:
        assert type(parent) is dict and final in parent
    else:
        assert type(parent) is list and 0 <= final < len(parent)
    parent[final] = copy.deepcopy(replacement)


def _rehash_record(runtime: Any, value: Any, type_name: str) -> None:
    descriptor = runtime.records[type_name]
    identity_field = descriptor["identity_field"]
    payload = {
        name: value[name] for name in descriptor["identity_payload_member_order"]
    }
    value[identity_field] = runtime_module._semantic_id(
        descriptor["described_record_domain"],
        payload,
    )


def _rebase_outer_observation(
    runtime: Any,
    witness: dict[str, Any],
    root: dict[str, Any],
    *,
    role: str,
    mode: str,
    attempt_id: str | None,
) -> dict[str, Any]:
    observation = copy.deepcopy(
        witness["fixture_records"]["exact_marker_observation"]["value"]
    )
    context = observation["observation_context"]
    context.update(
        {
            "attempt_id": attempt_id,
            "candidate_id": root["candidate_id"],
            "instrumentation_mode": mode,
            "observation_role": role,
            "operation_kind": root["operation_kind"],
            "target_field_registry_id": root["target_field_registry_id"],
        }
    )
    for member in (
        "checkpoint_binding_status",
        "checkpoint_binding_unavailable_reason",
        "checkpoint_marker_kind",
        "checkpoint_selector_entry_id",
        "checkpoint_selector_position",
        "expected_checkpoint_marker_kind",
        "expected_occurrence_index_within_kind",
        "full_checkpoint_selector_id",
        "marker_ordinal",
    ):
        context[member] = None
    _rehash_record(runtime, context, "TargetObservationContextV2")
    observation["observation_context_id"] = context["observation_context_id"]
    for field in observation["field_observations"]:
        field["observation_context_id"] = context["observation_context_id"]
        field["target_field_registry_id"] = root["target_field_registry_id"]
        _rehash_record(runtime, field, "TargetFieldObservationV1")
    _rehash_record(runtime, observation, "TargetObservationV2")
    return observation


def _rebase_checkpoint_observation(
    runtime: Any,
    witness: dict[str, Any],
    root: dict[str, Any],
    selector: dict[str, Any],
    entry: dict[str, Any],
) -> dict[str, Any]:
    observation = copy.deepcopy(
        witness["fixture_records"]["target_boundary_placeholder_observation"]["value"]
    )
    context = observation["observation_context"]
    context.update(
        {
            "attempt_id": root["attempt_id"],
            "candidate_id": root["candidate_id"],
            "checkpoint_binding_status": ("UNAVAILABLE_TARGET_BOUNDARY_NOT_REACHED"),
            "checkpoint_binding_unavailable_reason": ("TARGET_BOUNDARY_NOT_REACHED"),
            "checkpoint_marker_kind": None,
            "checkpoint_selector_entry_id": (entry["checkpoint_selector_entry_id"]),
            "checkpoint_selector_position": entry["selector_position"],
            "expected_checkpoint_marker_kind": entry["checkpoint_marker_kind"],
            "expected_occurrence_index_within_kind": (
                entry["occurrence_index_within_kind"]
            ),
            "full_checkpoint_selector_id": selector["checkpoint_selector_id"],
            "instrumentation_mode": "ON",
            "marker_ordinal": None,
            "observation_role": "STABLE_CHECKPOINT",
            "operation_kind": root["operation_kind"],
            "target_field_registry_id": root["target_field_registry_id"],
        }
    )
    _rehash_record(runtime, context, "TargetObservationContextV2")
    observation["observation_context_id"] = context["observation_context_id"]
    for field in observation["field_observations"]:
        field["observation_context_id"] = context["observation_context_id"]
        field["target_field_registry_id"] = root["target_field_registry_id"]
        _rehash_record(runtime, field, "TargetFieldObservationV1")
    _rehash_record(runtime, observation, "TargetObservationV2")
    return observation


def _materialize_recipe(
    runtime: Any,
    witness: dict[str, Any],
    recipe_name: str,
) -> dict[str, Any]:
    recipe = witness["materialization_recipes"][recipe_name]
    root = copy.deepcopy(
        witness["fixture_records"][recipe["source_root_fixture"]]["value"]
    )
    selector_name = recipe["selector_fixture"]
    selector = (
        None
        if selector_name is None
        else copy.deepcopy(witness["fixture_records"][selector_name]["value"])
    )
    if recipe["startup_recovery"]:
        root["attempt_id"] = None
        observations = [
            _rebase_outer_observation(
                runtime,
                witness,
                root,
                role="STARTUP_RECOVERY",
                mode="OFF",
                attempt_id=None,
            )
        ]
    else:
        mode = recipe["instrumentation_mode"]
        observations = [
            _rebase_outer_observation(
                runtime,
                witness,
                root,
                role="BEFORE_OPERATION",
                mode=mode,
                attempt_id=root["attempt_id"],
            )
        ]
        if selector is not None:
            observations.extend(
                _rebase_checkpoint_observation(
                    runtime,
                    witness,
                    root,
                    selector,
                    entry,
                )
                for entry in selector["ordered_entries"]
            )
        observations.extend(
            [
                _rebase_outer_observation(
                    runtime,
                    witness,
                    root,
                    role="AFTER_OPERATION",
                    mode=mode,
                    attempt_id=root["attempt_id"],
                ),
                _rebase_outer_observation(
                    runtime,
                    witness,
                    root,
                    role="OPERATION_AGGREGATE",
                    mode=mode,
                    attempt_id=root["attempt_id"],
                ),
            ]
        )
    root["instrumentation_mode"] = recipe["instrumentation_mode"]
    root["full_checkpoint_selector_id"] = (
        None if selector is None else selector["checkpoint_selector_id"]
    )
    root["observation_count"] = len(observations)
    root["ordered_observation_ids"] = [
        observation["observation_id"] for observation in observations
    ]
    _rehash_record(runtime, root, "TargetObservationRootV2")
    return {"observations": observations, "root": root, "selector": selector}


def _resolve_reference(
    runtime: Any,
    witness: dict[str, Any],
    recipes: dict[str, dict[str, Any]],
    reference: dict[str, Any],
) -> Any:
    assert type(reference) is dict and len(reference) == 1
    kind, payload = next(iter(reference.items()))
    if kind == "inline_value":
        return copy.deepcopy(payload)
    if kind == "ordered_values":
        assert type(payload) is list
        return [
            _resolve_reference(runtime, witness, recipes, member) for member in payload
        ]
    assert type(payload) is list and payload
    if kind == "fixture_path":
        fixture_name, *path = payload
        return copy.deepcopy(
            _traverse(witness["fixture_records"][fixture_name]["value"], path)
        )
    if kind == "authority_path":
        return copy.deepcopy(_traverse(runtime.literal_authority, payload))
    assert kind == "recipe_path"
    recipe_name, *path = payload
    return copy.deepcopy(_traverse(recipes[recipe_name], path))


def _find_input(
    materialized: dict[str, Any],
    target_kind: str,
    binding_name: str,
) -> dict[str, Any]:
    key = "root_inputs" if target_kind == "ROOT_RECORD" else "external_sequences"
    matches = [
        item for item in materialized[key] if item["binding_name"] == binding_name
    ]
    assert len(matches) == 1
    return matches[0]


def _target_value(
    materialized: dict[str, Any],
    target_kind: str,
    binding_name: str,
) -> Any:
    item = _find_input(materialized, target_kind, binding_name)
    return item["value"] if target_kind == "ROOT_RECORD" else item["records"]


def _apply_transform(
    runtime: Any,
    materialized: dict[str, Any],
    transform: dict[str, Any],
) -> None:
    operation = transform["operation"]
    target_kind = transform["target_kind"]
    binding_name = transform["binding_name"]
    path = transform["typed_path"]
    target = _target_value(materialized, target_kind, binding_name)
    if operation == "SET":
        _set_path(target, path, transform["value"])
        return
    if operation == "ADD":
        current = _traverse(target, path)
        assert type(current) is int
        _set_path(target, path, current + transform["integer_delta"])
        return
    if operation == "SET_FROM_PATH":
        source = _target_value(
            materialized,
            transform["source_target_kind"],
            transform["source_binding_name"],
        )
        _set_path(target, path, _traverse(source, transform["source_typed_path"]))
        return
    if operation == "REHASH_RECORD":
        _rehash_record(runtime, _traverse(target, path), transform["type_name"])
        return
    if operation == "TRUNCATE_LIST":
        sequence = _traverse(target, path)
        assert type(sequence) is list
        del sequence[transform["new_length"] :]
        return
    if operation == "SWAP_LIST_ITEMS":
        sequence = _traverse(target, path)
        first = transform["first_index"]
        second = transform["second_index"]
        sequence[first], sequence[second] = sequence[second], sequence[first]
        return
    if operation == "APPEND_LIST_ITEM_COPY":
        sequence = _traverse(target, path)
        sequence.append(copy.deepcopy(sequence[transform["source_index"]]))
        return
    if operation == "REPLACE_LIST_ITEM_COPY":
        sequence = _traverse(target, path)
        sequence[transform["target_index"]] = copy.deepcopy(
            sequence[transform["source_index"]]
        )
        return
    if operation == "SET_OBSERVATION_CONTEXT_AND_REHASH_CLOSURE":
        observation = _traverse(target, path)
        context = observation["observation_context"]
        context[transform["member_name"]] = copy.deepcopy(transform["value"])
        _rehash_record(runtime, context, "TargetObservationContextV2")
        observation["observation_context_id"] = context["observation_context_id"]
        for field in observation["field_observations"]:
            field["observation_context_id"] = context["observation_context_id"]
            field["target_field_registry_id"] = context["target_field_registry_id"]
            _rehash_record(runtime, field, "TargetFieldObservationV1")
        _rehash_record(runtime, observation, "TargetObservationV2")
        return
    assert operation == "SYNC_ROOT_OBSERVATION_IDS"
    source = _target_value(
        materialized,
        "EXTERNAL_SEQUENCE",
        transform["source_sequence_binding_name"],
    )
    root = _traverse(target, path)
    root["observation_count"] = len(source)
    root["ordered_observation_ids"] = [
        observation["observation_id"] for observation in source
    ]
    _rehash_record(runtime, root, "TargetObservationRootV2")


def _materialize_case(
    runtime: Any,
    witness: dict[str, Any],
    recipes: dict[str, dict[str, Any]],
    case: dict[str, Any],
) -> dict[str, Any]:
    materialized = {
        "root_inputs": [
            {
                "binding_name": item["binding_name"],
                "declared_type_name": item["declared_type_name"],
                "value": _resolve_reference(
                    runtime,
                    witness,
                    recipes,
                    item["value_reference"],
                ),
            }
            for item in case["ordered_root_inputs"]
        ],
        "external_sequences": [
            {
                "binding_name": item["binding_name"],
                "declared_item_type_name": item["declared_item_type_name"],
                "records": _resolve_reference(
                    runtime,
                    witness,
                    recipes,
                    item["records_reference"],
                ),
            }
            for item in case["ordered_external_sequences"]
        ],
    }
    for transform in case["ordered_transforms"]:
        _apply_transform(runtime, materialized, transform)
    return materialized


@pytest.fixture(scope="module")
def runtime() -> Any:
    return runtime_module.ExternalSchemaV2Runtime.load(ROOT)


@pytest.fixture(scope="module")
def witness() -> dict[str, Any]:
    return _load_witness()


@pytest.fixture(scope="module")
def recipes(runtime: Any, witness: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        name: _materialize_recipe(runtime, witness, name)
        for name in witness["materialization_recipes"]
    }


def test_application_witness_is_hash_pinned_and_explicitly_non_authoritative(
    runtime: Any,
    witness: dict[str, Any],
) -> None:
    assert witness["artifact_version"] == (
        "riskyieldmm.raw_v8_step2_external_schema_v2.application_witness.v1"
    )
    assert witness["component_status"] == (
        "EXECUTABLE_APPLICATION_TEST_WITNESS_NOT_AUTHORITY"
    )
    assert witness["canonicalization_version"] == (
        runtime_module.CANONICALIZATION_VERSION
    )
    assert witness["measurement_schema_version"] == (
        runtime_module.MEASUREMENT_SCHEMA_VERSION
    )
    assert witness["application_witness_sha256"] == WITNESS_SEMANTIC_SHA256
    payload = {
        key: value
        for key, value in witness.items()
        if key != "application_witness_sha256"
    }
    assert (
        hashlib.sha256(
            _canonical_bytes(
                {
                    "domain": WITNESS_IDENTITY_DOMAIN,
                    "payload": payload,
                }
            )
        ).hexdigest()
        == WITNESS_SEMANTIC_SHA256
    )
    assert witness["source_candidate"]["physical_sha256"] == (
        "3b80a2569155a9655215a1e5e61ae63eac482e83c1d28a87e910a29a95b91252"
    )
    assert witness["source_generator"]["reproduction_claim"] is False
    assert witness["source_literal_authority"]["physical_sha256"] == (
        runtime_module.RULE_LITERAL_AUTHORITY_SHA256
    )
    assert any(
        "legal application boundary is not a constructive canonical-byte maximum"
        in nonclaim
        for nonclaim in witness["nonclaims"]
    )
    assert any(
        "runtime tests never read test_output" in nonclaim
        for nonclaim in witness["nonclaims"]
    )


def test_profiles_and_fixed_resolvers_match_the_frozen_runtime(
    runtime: Any,
    witness: dict[str, Any],
) -> None:
    profiles = witness["application_profiles"]
    assert [profile["application_name"] for profile in profiles] == sorted(
        EXPECTED_APPLICATIONS
    )
    registry_profiles = {
        profile["application_name"]: profile
        for profile in runtime.registry["ordered_rule_application_descriptors"]
    }
    for profile in profiles:
        application_name = profile["application_name"]
        expected_kind, expected_maximum = EXPECTED_APPLICATIONS[application_name]
        frozen = registry_profiles[application_name]
        assert profile["application_kind"] == expected_kind
        assert profile["maximum_rule_evaluations"] == expected_maximum
        assert profile["rule_id"] == frozen["rule_id"]
        assert profile["rule_application_id"] == frozen["rule_application_id"]
        assert (
            profile["iteration_ordinal_binding_name"]
            == frozen["iteration_ordinal_binding_name"]
        )
    assert witness["fixed_position_resolver_profile_ids"] == EXPECTED_RESOLVER_IDS
    assert [
        profile["fixed_position_resolver_profile_id"]
        for profile in runtime.registry["fixed_position_resolver_profile_catalog"]
    ] == EXPECTED_RESOLVER_IDS


def test_fixtures_and_all_five_causal_recipes_are_self_pinned(
    runtime: Any,
    witness: dict[str, Any],
    recipes: dict[str, dict[str, Any]],
) -> None:
    fixtures = witness["fixture_records"]
    assert list(fixtures) == sorted(fixtures)
    assert len(fixtures) == 13
    for fixture_name, fixture in fixtures.items():
        assert fixture["provenance"]["frozen_value_canonical_sha256"] == (
            hashlib.sha256(_canonical_bytes(fixture["value"])).hexdigest()
        ), fixture_name
    assert set(recipes) == {
        "ordinary_off_three",
        "ordinary_on_empty_three",
        "ordinary_on_max64_full67",
        "ordinary_on_one_four",
        "startup_one",
    }
    for recipe_name, materialized in recipes.items():
        recipe = witness["materialization_recipes"][recipe_name]
        root = materialized["root"]
        observations = materialized["observations"]
        selector = materialized["selector"]
        assert len(observations) == recipe["expected_observation_count"]
        assert (
            root["target_observation_root_sha256"] == (recipe["expected_root_identity"])
        )
        assert (
            hashlib.sha256(_canonical_bytes(root)).hexdigest()
            == (recipe["expected_root_canonical_sha256"])
        )
        assert (
            hashlib.sha256(_canonical_bytes(observations)).hexdigest()
            == (recipe["expected_sequence_canonical_sha256"])
        )
        assert (
            hashlib.sha256(
                _canonical_bytes(root["ordered_observation_ids"])
            ).hexdigest()
            == (recipe["expected_ordered_observation_ids_canonical_sha256"])
        )
        runtime.validate_schema(
            next(
                schema_id
                for schema_id, schema in runtime.schemas.items()
                if schema["schema_kind"] == "OBJECT_REF"
                and schema["nullable"] is False
                and schema["referenced_type_name"] == "TargetObservationRootV2"
            ),
            root,
        )
        for observation in observations:
            runtime.validate_schema(
                next(
                    schema_id
                    for schema_id, schema in runtime.schemas.items()
                    if schema["schema_kind"] == "OBJECT_REF"
                    and schema["nullable"] is False
                    and schema["referenced_type_name"] == "TargetObservationV2"
                ),
                observation,
            )
        lifecycle = runtime.evaluate_rule(
            "RULE/CROSS/V2_ROOT_SELECTOR_LIFECYCLE_V1",
            {
                "observations": observations,
                "root": root,
                "selector": selector,
            },
            require_true=False,
        )
        assert lifecycle.root_value is True, recipe_name
        for ordinal, observation in enumerate(observations):
            membership = runtime.evaluate_rule(
                "RULE/CROSS/V2_ROOT_OBSERVATION_MEMBERSHIP_V1",
                {
                    "observation": observation,
                    "observation_ordinal": ordinal,
                    "root": root,
                },
                require_true=False,
            )
            assert membership.root_value is True, (recipe_name, ordinal)

    maximum = recipes["ordinary_on_max64_full67"]
    assert len(maximum["selector"]["ordered_entries"]) == 64
    assert len(maximum["observations"]) == 67
    assert (
        maximum["observations"][0]["observation_context"]["observation_role"]
        == "BEFORE_OPERATION"
    )
    assert (
        maximum["observations"][1]["observation_context"][
            "checkpoint_selector_position"
        ]
        == 1
    )
    assert (
        maximum["observations"][64]["observation_context"][
            "checkpoint_selector_position"
        ]
        == 64
    )
    assert (
        maximum["observations"][66]["observation_context"]["observation_role"]
        == "OPERATION_AGGREGATE"
    )


def test_case_matrix_freezes_shapes_coordinates_charges_and_boundaries(
    runtime: Any,
    witness: dict[str, Any],
    recipes: dict[str, dict[str, Any]],
) -> None:
    cases = witness["ordered_cases"]
    assert len(cases) == 57
    identities = [(case["application_name"], case["case_id"]) for case in cases]
    assert identities == sorted(identities)
    assert len(set(identities)) == len(identities)
    assert {case["application_name"] for case in cases} == set(EXPECTED_APPLICATIONS)
    assert Counter(case["expected_outcome"] for case in cases) == {
        "ACCEPT": 18,
        "APPLICATION_FAILURE": 26,
        "BUSINESS_FALSE": 13,
    }
    cases_by_application: dict[str, list[dict[str, Any]]] = defaultdict(list)
    all_tags: set[str] = set()
    for case in cases:
        cases_by_application[case["application_name"]].append(case)
        all_tags.update(case["coverage_tags"])
        profile = next(
            profile
            for profile in witness["application_profiles"]
            if profile["application_name"] == case["application_name"]
        )
        coordinate = case["expected_coordinate"]
        assert coordinate["application_name"] == case["application_name"]
        assert coordinate["rule_application_id"] == profile["rule_application_id"]
        assert coordinate["failure_class"] in EXPECTED_FAILURE_CLASSES
        assert (coordinate["failure_class"] is None) == (
            case["expected_outcome"] == "ACCEPT"
        )
        if case["expected_outcome"] == "ACCEPT":
            assert coordinate["iteration_ordinal"] is None
            assert coordinate["rule_id"] == profile["rule_id"]
        if case["expected_charged_cross_rule_evaluations"] == 0:
            assert coordinate["iteration_ordinal"] is None
        assert (
            0
            <= case["expected_completed_cross_rule_evaluations"]
            <= case["expected_charged_cross_rule_evaluations"]
            <= profile["maximum_rule_evaluations"]
        )
        bounds = case["expected_iteration_ordinal_bounds"]
        if bounds is not None:
            assert 0 <= bounds["first"] <= bounds["last"]
            assert bounds["last"] < profile["maximum_rule_evaluations"]
        _materialize_case(runtime, witness, recipes, case)

    for application_name, application_cases in cases_by_application.items():
        assert any(
            case["expected_outcome"] == "ACCEPT" for case in application_cases
        ), application_name
        assert any(
            case["expected_outcome"] != "ACCEPT" for case in application_cases
        ), application_name
    assert {
        "TUPLE_EXTRA",
        "TUPLE_MISSING",
        "TUPLE_REORDER",
        "TUPLE_WRONG_TYPE",
        "INTRINSIC_BEFORE_CROSS",
        "INTRINSIC_VALID_CROSS_MISMATCH",
        "SELECTOR_EMPTY",
        "SELECTOR_MAX64",
        "BOUNDARY_0",
        "BOUNDARY_184",
        "MAXIMUM_67",
        "ORDINAL_66",
        "OBSERVATION_RESOLVER",
        "SELECTOR_RESOLVER",
        "NULL_RECORD",
        "STALE_ROOT",
        "WRONG_IDENTITY",
    } <= all_tags
    fields_accept = next(
        case for case in cases if case["case_id"] == "accept_all_185_fields"
    )
    assert fields_accept["expected_charged_cross_rule_evaluations"] == 185
    assert fields_accept["expected_iteration_ordinal_bounds"] == {
        "first": 0,
        "last": 184,
    }
    membership_accept = next(
        case for case in cases if case["case_id"] == "accept_full_67"
    )
    assert membership_accept["expected_charged_cross_rule_evaluations"] == 67
    assert membership_accept["expected_iteration_ordinal_bounds"] == {
        "first": 0,
        "last": 66,
    }
    empty_lifecycle = next(
        case for case in cases if case["case_id"] == "accept_on_empty"
    )
    materialized = _materialize_case(
        runtime,
        witness,
        recipes,
        empty_lifecycle,
    )
    selector_sequence = next(
        sequence
        for sequence in materialized["external_sequences"]
        if sequence["binding_name"] == "selector"
    )
    assert len(selector_sequence["records"]) == 1
    assert selector_sequence["records"][0]["selector_length"] == 0
    assert empty_lifecycle["expected_charged_cross_rule_evaluations"] == 1

    operation_false_cases = [
        case
        for case in cases
        if case["application_name"] == "APPLY/OPERATION_RESULT_SIGNED_SPEC_V1"
        and case["expected_outcome"] == "BUSINESS_FALSE"
    ]
    assert len(operation_false_cases) == 4
    for case in operation_false_cases:
        assert case["ordered_transforms"] == []
        result_fixture = case["ordered_root_inputs"][0]["value_reference"][
            "fixture_path"
        ][0]
        spec_fixture = case["ordered_root_inputs"][1]["value_reference"][
            "fixture_path"
        ][0]
        assert result_fixture != spec_fixture
        assert "INTRINSIC_VALID_CROSS_MISMATCH" in case["coverage_tags"]


def test_all_application_cases_execute_through_the_public_runtime_api(
    runtime: Any,
    witness: dict[str, Any],
    recipes: dict[str, dict[str, Any]],
) -> None:
    for case in witness["ordered_cases"]:
        materialized = _materialize_case(runtime, witness, recipes, case)
        ordered_root_inputs = tuple(
            runtime_module.ApplicationRecordInput(
                binding_name=item["binding_name"],
                declared=runtime_module.TypedValue(
                    value=item["value"],
                    type_name=item["declared_type_name"],
                ),
            )
            for item in materialized["root_inputs"]
        )
        ordered_external_sequences = tuple(
            runtime_module.ApplicationSequenceInput(
                binding_name=item["binding_name"],
                ordered_records=tuple(
                    runtime_module.TypedValue(
                        value=record,
                        type_name=item["declared_item_type_name"],
                    )
                    for record in item["records"]
                ),
            )
            for item in materialized["external_sequences"]
        )
        evidence = runtime.evaluate_application(
            case["application_name"],
            ordered_root_inputs,
            ordered_external_sequences,
        )
        expected_coordinate = case["expected_coordinate"]
        assert evidence.accepted is (case["expected_outcome"] == "ACCEPT"), (
            case["application_name"],
            case["case_id"],
        )
        assert {
            "application_name": evidence.result_coordinate.application_name,
            "rule_application_id": (evidence.result_coordinate.rule_application_id),
            "rule_id": evidence.result_coordinate.rule_id,
            "iteration_ordinal": (evidence.result_coordinate.iteration_ordinal),
            "failure_class": evidence.result_coordinate.failure_class,
        } == expected_coordinate, (case["application_name"], case["case_id"])
        assert (
            evidence.charged_rule_evaluations
            == (case["expected_charged_cross_rule_evaluations"])
        ), (case["application_name"], case["case_id"])
        assert (
            evidence.completed_rule_evaluations
            == (case["expected_completed_cross_rule_evaluations"])
        ), (case["application_name"], case["case_id"])

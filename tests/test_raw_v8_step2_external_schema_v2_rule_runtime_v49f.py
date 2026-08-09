from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from collections import deque
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    ROOT / "scripts/tests/validate_raw_v8_step2_external_schema_v2_rule_runtime_v49f.py"
)
COMPLEX_WITNESS_PATH = (
    ROOT
    / "scripts/tests/raw_v8_step2_external_schema_v2_complex_rule_witness_v49f.json"
)
COMPLEX_WITNESS_OCTETS = 456_162
COMPLEX_WITNESS_SHA256 = (
    "d74bbc6bd98de6f143bd1bfcc9c2660f8923713ac901911289939dfd12712e4b"
)
APPLICATION_WITNESS_PATH = (
    ROOT / "scripts/tests/raw_v8_step2_external_schema_v2_application_witness_v49f.json"
)
SPEC = importlib.util.spec_from_file_location("raw_v8_rule_runtime_v49f", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
runtime_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runtime_module
SPEC.loader.exec_module(runtime_module)


@pytest.fixture(scope="module")
def runtime():
    return runtime_module.ExternalSchemaV2Runtime.load(ROOT)


def _member_schema_id(runtime, type_name, member_name):
    descriptor = runtime.types[type_name]
    return next(
        member["value_schema_id"]
        for member in descriptor["record_member_descriptors"]
        if member["member_name"] == member_name
    )


def _semantic_record(runtime, type_name, payload):
    descriptor = runtime.records[type_name]
    value = {
        "canonicalization_version": runtime_module.CANONICALIZATION_VERSION,
        "measurement_schema_version": runtime_module.MEASUREMENT_SCHEMA_VERSION,
        "record_domain": descriptor["described_record_domain"],
        **payload,
    }
    value[descriptor["identity_field"]] = runtime_module._semantic_id(
        descriptor["described_record_domain"],
        {name: value[name] for name in descriptor["identity_payload_member_order"]},
    )
    return value


def _complex_witness_fixtures():
    raw = COMPLEX_WITNESS_PATH.read_bytes()
    assert len(raw) == COMPLEX_WITNESS_OCTETS
    assert hashlib.sha256(raw).hexdigest() == COMPLEX_WITNESS_SHA256
    return json.loads(raw)["fixture_records"]


def _rehash_existing_record(runtime, value, type_name):
    descriptor = runtime.records[type_name]
    value[descriptor["identity_field"]] = runtime_module._semantic_id(
        descriptor["described_record_domain"],
        {name: value[name] for name in descriptor["identity_payload_member_order"]},
    )


def _rebase_recipe_observation(
    runtime,
    witness,
    root,
    *,
    role,
    selector=None,
    entry=None,
):
    checkpoint = role == "STABLE_CHECKPOINT"
    fixture_name = (
        "target_boundary_placeholder_observation"
        if checkpoint
        else "exact_marker_observation"
    )
    observation = copy.deepcopy(witness["fixture_records"][fixture_name]["value"])
    context = observation["observation_context"]
    context.update(
        {
            "attempt_id": root["attempt_id"],
            "candidate_id": root["candidate_id"],
            "instrumentation_mode": root["instrumentation_mode"],
            "observation_role": role,
            "operation_kind": root["operation_kind"],
            "target_field_registry_id": root["target_field_registry_id"],
        }
    )
    if checkpoint:
        context.update(
            {
                "checkpoint_binding_status": (
                    "UNAVAILABLE_TARGET_BOUNDARY_NOT_REACHED"
                ),
                "checkpoint_binding_unavailable_reason": (
                    "TARGET_BOUNDARY_NOT_REACHED"
                ),
                "checkpoint_marker_kind": None,
                "checkpoint_selector_entry_id": (entry["checkpoint_selector_entry_id"]),
                "checkpoint_selector_position": entry["selector_position"],
                "expected_checkpoint_marker_kind": (entry["checkpoint_marker_kind"]),
                "expected_occurrence_index_within_kind": (
                    entry["occurrence_index_within_kind"]
                ),
                "full_checkpoint_selector_id": selector["checkpoint_selector_id"],
                "marker_ordinal": None,
            }
        )
    else:
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
    _rehash_existing_record(runtime, context, "TargetObservationContextV2")
    observation["observation_context_id"] = context["observation_context_id"]
    for field in observation["field_observations"]:
        field["observation_context_id"] = context["observation_context_id"]
        field["target_field_registry_id"] = root["target_field_registry_id"]
        _rehash_existing_record(runtime, field, "TargetFieldObservationV1")
    _rehash_existing_record(runtime, observation, "TargetObservationV2")
    return observation


def _application_recipe(runtime, recipe_name):
    witness = json.loads(APPLICATION_WITNESS_PATH.read_bytes())
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
    root["instrumentation_mode"] = recipe["instrumentation_mode"]
    if recipe["startup_recovery"]:
        root["attempt_id"] = None
        observations = [
            _rebase_recipe_observation(
                runtime,
                witness,
                root,
                role="STARTUP_RECOVERY",
            )
        ]
    else:
        observations = [
            _rebase_recipe_observation(
                runtime,
                witness,
                root,
                role="BEFORE_OPERATION",
            )
        ]
        if selector is not None:
            observations.extend(
                _rebase_recipe_observation(
                    runtime,
                    witness,
                    root,
                    role="STABLE_CHECKPOINT",
                    selector=selector,
                    entry=entry,
                )
                for entry in selector["ordered_entries"]
            )
        observations.extend(
            (
                _rebase_recipe_observation(
                    runtime,
                    witness,
                    root,
                    role="AFTER_OPERATION",
                ),
                _rebase_recipe_observation(
                    runtime,
                    witness,
                    root,
                    role="OPERATION_AGGREGATE",
                ),
            )
        )
    root["full_checkpoint_selector_id"] = (
        None if selector is None else selector["checkpoint_selector_id"]
    )
    root["observation_count"] = len(observations)
    root["ordered_observation_ids"] = [
        observation["observation_id"] for observation in observations
    ]
    _rehash_existing_record(runtime, root, "TargetObservationRootV2")
    return root, tuple(observations), selector


def _shortest_accepted_dfa_text(dfa):
    transitions = {}
    for row in dfa["ordered_transition_rows"]:
        transitions.setdefault(row["source_state"], []).append(
            (row["inclusive_byte_minimum"], row["target_state"])
        )
    queue = deque([(dfa["start_state"], b"")])
    visited = {(dfa["start_state"], 0)}
    accepting = set(dfa["ordered_accepting_states"])
    while queue:
        state, prefix = queue.popleft()
        if len(prefix) >= dfa["minimum_octets"] and state in accepting:
            return prefix.decode("ascii")
        if len(prefix) == dfa["maximum_octets"]:
            continue
        for byte, target in transitions.get(state, ()):
            key = (target, len(prefix) + 1)
            if key not in visited:
                visited.add(key)
                queue.append((target, prefix + bytes((byte,))))
    raise AssertionError(f"DFA has no accepted bounded path: {dfa['ascii_dfa_id']}")


BOOL_SCHEMA_ID = "e35ba28ae2abdcdefdd9d56862b866d0cf72645f5c8d0bdf8c86b156c5dddb97"
SAFE_UINT_SCHEMA_ID = "3555d621c77a96d171a0883f4511ccf5ff3d297b314558d5cbd114e9175aebc4"
NULLABLE_SAFE_UINT_SCHEMA_ID = (
    "7192b6f27f38c255572a3d7a66253836da246a6fddbbc1a2114b55bb2bf6595a"
)
RAW_TEXT_ARRAY_SCHEMA_ID = (
    "b3b5daccd42697266933f56530f4a9e5f4f90c0afd041f9021570520a447eab4"
)
RAW_TEXT_SCHEMA_ID = "d3b2e4009fbf09a23faf77ca7cebb6c0f71f6b9e87943281d580ac8cad4b23f8"
FIXED_MAP_ENTRY_SCHEMA_ID = (
    "925339066108ddbf86d40719b74a296aaa992be23fc960359ec8bbcb2fd24a1c"
)
FIXED_MAP_ARRAY_SCHEMA_ID = (
    "b54c214fcc8d1cd4526fe87af05eeb38e6246b8d8b75068c8fcbec332440aeed"
)
FIXED_MAP_KEY_ARRAY_SCHEMA_ID = (
    "b0c6dca976aecc6c196c3ad07557a026f0b6bdef7918fbfd2f473cf3bded6a58"
)
FIXED_MAP_KEY_SCHEMA_ID = (
    "436a2d78be1999813b31917fa7d810947a1f7093ba3a70a647aecdc55cdd4a5e"
)
RFC3339_SCHEMA_ID = "fe496f61efb4afddf352baf26669d11d5b445e3720114dc0aa30ca38f73b5fd3"
UINT128_TEXT_SCHEMA_ID = (
    "494da2538286ea86370111a5947d3d612651dbe446a6b1361eb6f3241761fc01"
)
FRAME_BASE64_SCHEMA_ID = (
    "2efadf0f7c32380c7d9c4f41027be9fae6db6ab2ddb1a7517d1e8df1d6466ca5"
)
INGRESS_BASE64_ARRAY_SCHEMA_ID = (
    "9b06afcc23489f48364000410f3bd2352e849f30b19fe8d5cb8b6dd5b8aa52b2"
)
LOWERCASE_SHA_SCHEMA_ID = (
    "47e559bb9b8e9dd409a551cf51f96067c3636f02f5adf5df7c582ab19bc7d1ab"
)
SOURCE_ERROR_SCHEMA_ID = (
    "5baf374528315466a7469d26e602ab1a313b0b0902de942052d4cae05ce894a5"
)
RFC6455_OPCODE_SCHEMA_ID = (
    "353646e6e58c5372e6e38adbf8a31eecb82bc86bc02e2507cab983b645c6e2d5"
)
LAYER_SCHEMA_ID = "f4ffc9b02011306bb5c5113869b43385de37d7d13187dda80d2a43bed465c7ac"
FIELD_ID_SCHEMA_ID = "e4949ef1ce43711e261980c911003cc69d46eb99a9281e95b6a783c498a1c8a5"


def _expression(value, result_type_kind="VALUE_SCHEMA", schema_id=None):
    if schema_id is None and result_type_kind == "VALUE_SCHEMA":
        schema_id = BOOL_SCHEMA_ID
    return runtime_module._ExpressionValue(
        value=value,
        result_type_kind=result_type_kind,
        value_schema_id=schema_id,
    )


def _operator_node(
    operator,
    *,
    schema_id=BOOL_SCHEMA_ID,
    result_type_kind="VALUE_SCHEMA",
    path=(),
    binding_name=None,
    literal_schema_id=None,
    literal_value=None,
):
    return {
        "expression_position": 1,
        "operator": operator,
        "result_type_kind": result_type_kind,
        "result_value_schema_id": (
            schema_id if result_type_kind == "VALUE_SCHEMA" else None
        ),
        "ordered_operand_positions": [],
        "input_binding_name": binding_name,
        "typed_member_path": list(path),
        "literal_value_schema_id": literal_schema_id,
        "literal_value": literal_value,
    }


def _execute_operator(
    runtime,
    operator,
    operands=(),
    *,
    schema_id=BOOL_SCHEMA_ID,
    result_type_kind="VALUE_SCHEMA",
    path=(),
    bindings=None,
    binding_name=None,
    literal_schema_id=None,
    literal_value=None,
):
    node = _operator_node(
        operator,
        schema_id=schema_id,
        result_type_kind=result_type_kind,
        path=path,
        binding_name=binding_name,
        literal_schema_id=literal_schema_id,
        literal_value=literal_value,
    )
    value = runtime._execute_operator(
        node,
        list(operands),
        bindings={} if bindings is None else bindings,
        counters=runtime_module._RuleCounters(),
        literal_rule_stack=(),
    )
    runtime._validate_expression_result(
        node,
        _expression(
            value,
            result_type_kind=result_type_kind,
            schema_id=(schema_id if result_type_kind == "VALUE_SCHEMA" else None),
        ),
    )
    return value


@pytest.mark.parametrize(
    ("authority_name", "type_name"),
    [
        ("marker_contract", "MarkerContractV1"),
        ("operation_counter_schema", "OperationCounterSnapshotSchemaV1"),
        ("target_field_registry", "TargetFieldRegistryV1"),
    ],
)
def test_frozen_composite_authority_validates(runtime, authority_name, type_name):
    value = runtime.literal_authority[authority_name]
    declared = runtime.validate_type(type_name, value)
    assert declared.type_name == type_name
    assert declared.value is value


def test_runtime_catalog_is_complete(runtime):
    assert len(runtime.schemas) == 236
    assert {item["schema_kind"] for item in runtime.schemas.values()} == {
        "ARRAY",
        "EXACT_BOOLEAN",
        "OBJECT_REF",
        "SAFE_INTEGER",
        "TEXT",
    }
    assert len(runtime.languages) == 103
    assert {item["language_kind"] for item in runtime.languages.values()} == {
        "ASCII_DFA",
        "BUILTIN",
        "ENUM",
        "LITERAL",
        "UNICODE_IDENTIFIER",
    }
    assert len(runtime.dfas) == 9
    assert len(runtime.profiles) == 3
    assert len(runtime.records) == 49
    assert len(runtime.unions) == 3
    assert runtime.derived_maximum_validation_work == 4_202_555
    assert (
        runtime.maximum_work_schema_id
        == "fd8bcbf5fe9553bef23b4a4b45e206961717ad4cfd3fa331618b3bed2aae7cda"
    )
    assert (
        runtime.schemas[runtime.maximum_work_schema_id]["referenced_type_name"]
        == "CapacityMeasurementOperationResultEvidence"
    )
    assert runtime.maximum_work_type_name == (
        "CapacityMeasurementOperationResultEvidence"
    )


def test_declared_schema_rejects_bool_as_integer(runtime):
    integer_schema_id = next(
        identifier
        for identifier, schema in runtime.schemas.items()
        if schema["schema_kind"] == "SAFE_INTEGER"
        and schema["integer_minimum"] <= 1 <= schema["integer_maximum"]
    )
    with pytest.raises(runtime_module.TypeMismatch) as caught:
        runtime.validate_schema(integer_schema_id, True)
    assert caught.value.failure_class == "TYPE_MISMATCH"


def test_declared_schema_rejects_integer_as_boolean(runtime):
    boolean_schema_id = next(
        identifier
        for identifier, schema in runtime.schemas.items()
        if schema["schema_kind"] == "EXACT_BOOLEAN"
        and schema["boolean_literal"] is None
    )
    with pytest.raises(runtime_module.TypeMismatch):
        runtime.validate_schema(boolean_schema_id, 1)


def test_declared_identifier_and_global_work_ceiling_are_exact(runtime):
    with pytest.raises(ValueError):
        runtime_module.TypedValue(value={}, type_name=1)
    with pytest.raises(ValueError):
        runtime_module.TypedValue(value={}, value_schema_id="")
    with pytest.raises(ValueError):
        runtime.validate_type(
            "MarkerContractV1",
            runtime.literal_authority["marker_contract"],
            maximum_work=runtime_module.MAXIMUM_VALIDATION_WORK + 1,
        )


def test_standalone_semantic_identity_is_enforced(runtime):
    value = copy.deepcopy(runtime.literal_authority["marker_contract"])
    value["ordered_marker_kinds"][0], value["ordered_marker_kinds"][1] = (
        value["ordered_marker_kinds"][1],
        value["ordered_marker_kinds"][0],
    )
    with pytest.raises(runtime_module.ConstraintViolation) as caught:
        runtime.validate_type("MarkerContractV1", value)
    assert caught.value.path == ("marker_contract_id",)


def test_standalone_domain_and_exact_members_are_enforced(runtime):
    value = copy.deepcopy(runtime.literal_authority["operation_counter_schema"])
    value["record_domain"] = "wrong"
    with pytest.raises(runtime_module.ConstraintViolation):
        runtime.validate_type("OperationCounterSnapshotSchemaV1", value)
    value = copy.deepcopy(runtime.literal_authority["operation_counter_schema"])
    value["unexpected"] = None
    with pytest.raises(runtime_module.MalformedValue):
        runtime.validate_type("OperationCounterSnapshotSchemaV1", value)


def test_work_bound_and_cyclic_python_value_fail_explicitly(runtime):
    with pytest.raises(runtime_module.WorkBoundExceeded):
        runtime.validate_type(
            "MarkerContractV1",
            runtime.literal_authority["marker_contract"],
            maximum_work=1,
        )
    value = copy.deepcopy(runtime.literal_authority["target_field_registry"])
    value["status_reason_policy_definition"] = value
    with pytest.raises(runtime_module.MalformedValue):
        runtime.validate_type("TargetFieldRegistryV1", value)


def test_non_text_object_key_rejects_before_hostile_equality_can_escape(runtime):
    class HostileKey:
        def __hash__(self):
            return hash("record_domain")

        def __eq__(self, other):
            raise RuntimeError(f"host equality must not execute: {other!r}")

    value = copy.deepcopy(runtime.literal_authority["marker_contract"])
    record_domain = value.pop("record_domain")
    value[HostileKey()] = record_domain
    with pytest.raises(runtime_module.MalformedValue) as caught:
        runtime.validate_type("MarkerContractV1", value)
    assert caught.value.failure_class == "MALFORMED_VALUE"
    assert caught.value.path == ()


def test_work_evidence_and_exact_small_boundary(runtime):
    declared = runtime_module.TypedValue(
        value=runtime.literal_authority["marker_contract"],
        type_name="MarkerContractV1",
    )
    evidence = runtime.validate_with_evidence(declared, maximum_work=190)
    assert evidence.validation_work_used == 190
    assert evidence.validation_work_limit == 190
    with pytest.raises(runtime_module.WorkBoundExceeded):
        runtime.validate_with_evidence(declared, maximum_work=189)


def test_self_value_and_owner_member_union_positive_dispatch(runtime):
    selected = {"kind": "BOOL", "value": True}
    runtime.validate_type("CapacityMeasurementTargetValue", selected)

    spec = {
        "workload_family": "family",
        "expected_outbound_subscription_intent_id": "0" * 64,
        "due_scenario": "DUE",
        "expected_terminal_cause_code": "ACK_DEADLINE_EXPIRED",
    }
    owner = _semantic_record(
        runtime,
        "CapacityMeasurementOperationSpec",
        {
            "operation_kind": "ACK_DEADLINE_EXPIRY",
            "spec_type": "ACK_DEADLINE_EXPIRY_SPEC_V1",
            "spec": spec,
        },
    )
    runtime.validate_type("CapacityMeasurementOperationSpec", owner)


def test_selected_union_enforces_concrete_and_union_codec_bounds(
    runtime,
    monkeypatch,
):
    observed = []
    original = runtime._validate_codec_bound

    def recording_bound(descriptor, value, *, path):
        observed.append(descriptor["type_name"])
        return original(descriptor, value, path=path)

    monkeypatch.setattr(runtime, "_validate_codec_bound", recording_bound)
    runtime.validate_type(
        "CapacityMeasurementTargetValue",
        {"kind": "BOOL", "value": True},
    )
    assert observed == [
        "CapacityMeasurementBoolValueV1",
        "CapacityMeasurementTargetValue",
    ]


def test_owner_member_union_cannot_be_validated_without_owner(runtime):
    union_name = next(
        name
        for name, descriptor in runtime.unions.items()
        if descriptor["tagged_union_descriptor"]["payload_binding_scope"]
        == "OWNER_MEMBER"
    )
    with pytest.raises(runtime_module.UnresolvedReference):
        runtime.validate_type(union_name, {})


def test_composite_mutations_fail_at_exact_nested_path(runtime):
    value = copy.deepcopy(runtime.literal_authority["target_field_registry"])
    value["descriptors"][0]["field_id"] = "not a valid field id"
    with pytest.raises(runtime_module.ConstraintViolation) as caught:
        runtime.validate_type("TargetFieldRegistryV1", value)
    assert caught.value.path[:2] == ("descriptors", 0)


def test_dfa_builtin_and_raw_string_representatives(runtime):
    field_id_schema = _member_schema_id(
        runtime,
        "CapacityMeasurementTargetFieldDescriptorV1",
        "field_id",
    )
    runtime.validate_schema(field_id_schema, "a1.active_count")
    with pytest.raises(runtime_module.ConstraintViolation):
        runtime.validate_schema(field_id_schema, "not a field id")

    timestamp_schema = next(
        identifier
        for identifier, schema in runtime.schemas.items()
        if schema["schema_kind"] == "TEXT"
        and runtime.languages[schema["text_language_id"]]["built_in_language_kind"]
        == "RFC3339_UTC"
    )
    runtime.validate_schema(timestamp_schema, "0001-01-01T00:00:00Z")
    runtime.validate_schema(timestamp_schema, "9999-12-31T23:59:59.999999Z")
    for invalid in (
        "2026-07-28T10:20:30.000000Z",
        "2026-07-28T10:20:60Z",
        "2026-07-28t10:20:30z",
        "2026-07-28T10:20:30.1Z",
    ):
        with pytest.raises(runtime_module.ConstraintViolation):
            runtime.validate_schema(timestamp_schema, invalid)

    uint128_schema = next(
        identifier
        for identifier, schema in runtime.schemas.items()
        if schema["schema_kind"] == "TEXT"
        and runtime.languages[schema["text_language_id"]]["built_in_language_kind"]
        == "UINT128_DECIMAL"
    )
    runtime.validate_schema(uint128_schema, str((1 << 128) - 1))
    for invalid in ("00", str(1 << 128), "-1"):
        with pytest.raises(runtime_module.ConstraintViolation):
            runtime.validate_schema(uint128_schema, invalid)

    base64_schema = next(
        identifier
        for identifier, schema in runtime.schemas.items()
        if schema["schema_kind"] == "TEXT"
        and not schema["nullable"]
        and runtime.languages[schema["text_language_id"]]["built_in_language_kind"]
        == "CANONICAL_BASE64"
        and runtime.languages[schema["text_language_id"]]["minimum_utf8_octets"]
        <= 4
        <= runtime.languages[schema["text_language_id"]]["maximum_utf8_octets"]
    )
    runtime.validate_schema(base64_schema, "YQ==")
    with pytest.raises(runtime_module.ConstraintViolation):
        runtime.validate_schema(base64_schema, "YQ")

    raw_schema = next(
        identifier
        for identifier, schema in runtime.schemas.items()
        if schema["schema_kind"] == "TEXT"
        and runtime.languages[schema["text_language_id"]]["built_in_language_kind"]
        == "RAW_CANONICAL_JSON_STRING"
    )
    runtime.validate_schema(raw_schema, "")
    runtime.validate_schema(raw_schema, " \u0000 decomposed e\u0301 ")
    with pytest.raises(runtime_module.MalformedValue):
        runtime.validate_schema(raw_schema, "\ud800")


def test_all_nine_ascii_dfas_execute_accept_and_reject_paths(runtime):
    exercised = set()
    for language in runtime.languages.values():
        if language["language_kind"] != "ASCII_DFA":
            continue
        dfa = runtime.dfas[language["ascii_dfa_id"]]
        schema_id = next(
            identifier
            for identifier, schema in runtime.schemas.items()
            if schema["schema_kind"] == "TEXT"
            and schema["text_language_id"] == language["text_language_id"]
        )
        runtime.validate_schema(schema_id, _shortest_accepted_dfa_text(dfa))
        with pytest.raises(runtime_module.ConstraintViolation):
            runtime.validate_schema(schema_id, "é")
        exercised.add(dfa["ascii_dfa_id"])
    assert exercised == set(runtime.dfas)


def test_unicode_identifier_exact_authority_and_boundaries(runtime):
    unicode_schema = _member_schema_id(
        runtime,
        "CapacityMeasurementTextValueV1",
        "value",
    )
    runtime.validate_schema(unicode_schema, "a" * 256)
    runtime.validate_schema(unicode_schema, "é" * 128)
    for invalid in (
        "",
        "a" * 257,
        "é" * 129,
        "e\u0301",
        " leading",
        "trailing\u00a0",
        "a\u0000b",
    ):
        with pytest.raises(runtime_module.ConstraintViolation):
            runtime.validate_schema(unicode_schema, invalid)


def test_all_unicode_profiles_and_host_version_partition(runtime, monkeypatch):
    exercised = set()
    unicode_schema_ids = []
    for language in runtime.languages.values():
        if language["language_kind"] != "UNICODE_IDENTIFIER":
            continue
        profile = runtime.profiles[language["unicode_identifier_profile_id"]]
        schema_id = next(
            identifier
            for identifier, schema in runtime.schemas.items()
            if schema["schema_kind"] == "TEXT"
            and schema["text_language_id"] == language["text_language_id"]
        )
        unicode_schema_ids.append(schema_id)
        ascii_maximum = min(
            profile["maximum_scalar_values"],
            profile["maximum_utf8_octets"],
        )
        runtime.validate_schema(schema_id, "a" * ascii_maximum)
        with pytest.raises(runtime_module.ConstraintViolation):
            runtime.validate_schema(schema_id, "a" * (ascii_maximum + 1))
        exercised.add(profile["unicode_identifier_profile_id"])
    assert exercised == set(runtime.profiles)

    field_id_schema = _member_schema_id(
        runtime,
        "CapacityMeasurementTargetFieldDescriptorV1",
        "field_id",
    )
    monkeypatch.setattr(runtime_module.unicodedata, "unidata_version", "16.0.0")
    with pytest.raises(runtime_module.ImpossibleState):
        runtime.validate_schema(unicode_schema_ids[0], "identifier")
    runtime.validate_schema(field_id_schema, "a1.active_count")


def test_pinned_loader_security_and_canonical_json(tmp_path):
    valid = runtime_module._pretty_bytes({"a": 1})
    valid_path = tmp_path / "valid.json"
    valid_path.write_bytes(valid)
    digest = hashlib.sha256(valid).hexdigest()
    assert runtime_module._read_pinned_json(
        valid_path,
        expected_sha256=digest,
        expected_octets=len(valid),
    ) == {"a": 1}

    with pytest.raises(runtime_module.ArtifactFailure):
        runtime_module._read_pinned_json(
            valid_path,
            expected_sha256="0" * 64,
            expected_octets=len(valid),
        )
    with pytest.raises(runtime_module.ArtifactFailure):
        runtime_module._read_pinned_json(
            valid_path,
            expected_sha256=digest,
            expected_octets=len(valid) + 1,
        )

    symlink = tmp_path / "link.json"
    symlink.symlink_to(valid_path)
    with pytest.raises(runtime_module.ArtifactFailure):
        runtime_module._read_pinned_json(
            symlink,
            expected_sha256=digest,
            expected_octets=len(valid),
        )

    with pytest.raises(runtime_module.ArtifactFailure):
        runtime_module._read_pinned_json(
            tmp_path,
            expected_sha256=digest,
            expected_octets=len(valid),
        )

    fifo = tmp_path / "authority.fifo"
    os.mkfifo(fifo)
    with pytest.raises(runtime_module.ArtifactFailure):
        runtime_module._read_pinned_json(
            fifo,
            expected_sha256=digest,
            expected_octets=0,
        )

    minified = b'{"a":1}'
    minified_path = tmp_path / "minified.json"
    minified_path.write_bytes(minified)
    with pytest.raises(runtime_module.ArtifactFailure):
        runtime_module._read_pinned_json(
            minified_path,
            expected_sha256=hashlib.sha256(minified).hexdigest(),
            expected_octets=len(minified),
        )


@pytest.mark.parametrize(
    "raw",
    [
        b'{\n  "a": 1,\n  "a": 2\n}\n',
        ("[" * 17 + "0" + "]" * 17).encode(),
        b'{\n  "a": "\\ud800"\n}\n',
        b'{\n  "a": 9007199254740992\n}\n',
        b'{\n  "a": 1.0\n}\n',
        b'{\n  "a": NaN\n}\n',
        b'{\n  "a": ' + b"9" * 5_000 + b"\n}\n",
        b"\xff",
        b"\xef\xbb\xbf{\n}\n",
        b"",
        b"[]\n",
        b'{\n  "a": "unterminated\n}\n',
        b'{\n  "a": "raw\x00control"\n}\n',
    ],
)
def test_pinned_loader_rejects_adversarial_json_before_acceptance(tmp_path, raw):
    path = tmp_path / "adversarial.json"
    path.write_bytes(raw)
    with pytest.raises(runtime_module.ArtifactFailure):
        runtime_module._read_pinned_json(
            path,
            expected_sha256=hashlib.sha256(raw).hexdigest(),
            expected_octets=len(raw),
        )


def test_loader_rejects_exclusive_size_boundary(tmp_path):
    oversized = tmp_path / "oversized.json"
    with oversized.open("wb") as stream:
        stream.truncate(runtime_module.MAXIMUM_ARTIFACT_OCTETS)
    with pytest.raises(runtime_module.ArtifactFailure):
        runtime_module._read_pinned_json(
            oversized,
            expected_sha256="0" * 64,
            expected_octets=runtime_module.MAXIMUM_ARTIFACT_OCTETS,
        )


def test_constructor_requires_internal_capability_and_exact_json_graph(runtime):
    with pytest.raises(TypeError):
        runtime_module.ExternalSchemaV2Runtime(
            runtime.registry,
            runtime.literal_authority,
        )
    with pytest.raises(runtime_module.ArtifactFailure):
        runtime_module.ExternalSchemaV2Runtime(
            runtime.registry,
            runtime.literal_authority,
            _capability=object(),
        )

    registry = json.loads(
        (ROOT / runtime_module.STRUCTURAL_REGISTRY_RELATIVE_PATH).read_text()
    )
    literals = json.loads(
        (ROOT / runtime_module.RULE_LITERAL_AUTHORITY_RELATIVE_PATH).read_text()
    )
    sealed = runtime_module.ExternalSchemaV2Runtime(
        registry,
        literals,
        _capability=runtime_module._LOAD_CAPABILITY,
    )
    literals["marker_contract"]["contract_version"] = "substituted"
    registry["external_schema_registry_id"] = "0" * 64
    sealed.validate_type(
        "MarkerContractV1",
        sealed.literal_authority["marker_contract"],
    )
    sealed.schemas = dict(sealed.schemas)
    schema_id = next(iter(sealed.schemas))
    sealed.schemas[schema_id] = {
        **sealed.schemas[schema_id],
        "nullable": not sealed.schemas[schema_id]["nullable"],
    }
    with pytest.raises(runtime_module.ArtifactFailure):
        sealed.validate_type(
            "MarkerContractV1",
            sealed.literal_authority["marker_contract"],
        )
    with pytest.raises(runtime_module.ArtifactFailure):
        runtime_module.ExternalSchemaV2Runtime(
            registry,
            literals,
            _capability=runtime_module._LOAD_CAPABILITY,
        )

    registry = json.loads(
        (ROOT / runtime_module.STRUCTURAL_REGISTRY_RELATIVE_PATH).read_text()
    )
    literals = json.loads(
        (ROOT / runtime_module.RULE_LITERAL_AUTHORITY_RELATIVE_PATH).read_text()
    )
    record_descriptor = next(
        descriptor
        for descriptor in registry["ordered_external_type_descriptors"]
        if descriptor["type_form"] == "RECORD"
    )
    record_descriptor["record_member_descriptors"] = tuple(
        record_descriptor["record_member_descriptors"]
    )
    with pytest.raises(runtime_module.ArtifactFailure):
        runtime_module.ExternalSchemaV2Runtime(
            registry,
            literals,
            _capability=runtime_module._LOAD_CAPABILITY,
        )


def test_all_41_generic_operator_dispatch_keys_have_defining_success_edges(runtime):
    exercised = set()

    def run(operator, operands=(), **kwargs):
        exercised.add(operator)
        return _execute_operator(runtime, operator, operands, **kwargs)

    assert (
        run(
            "INPUT_PATH",
            bindings={"binding": {"value": 7}},
            binding_name="binding",
            path=("value",),
            schema_id=SAFE_UINT_SCHEMA_ID,
        )
        == 7
    )
    assert (
        run(
            "LITERAL",
            schema_id=SAFE_UINT_SCHEMA_ID,
            literal_schema_id=SAFE_UINT_SCHEMA_ID,
            literal_value=7,
        )
        == 7
    )
    assert run(
        "IS_NULL",
        (_expression(None, schema_id=NULLABLE_SAFE_UINT_SCHEMA_ID),),
    )
    assert run("NOT", (_expression(False),))
    assert run("AND", (_expression(True), _expression(True)))
    assert run("OR", (_expression(False), _expression(True)))
    assert run("IMPLIES", (_expression(False), _expression(False)))
    assert run("EQ", (_expression(True), _expression(True)))
    assert run("NE", (_expression(True), _expression(False)))
    internal_one = _expression(1, "INTERNAL_UINT128", None)
    internal_two = _expression(2, "INTERNAL_UINT128", None)
    assert run("LT", (internal_one, internal_two))
    assert run("LE", (internal_one, internal_one))
    assert run("GT", (internal_two, internal_one))
    assert run("GE", (internal_two, internal_two))
    assert run(
        "PRESENT_EQ",
        (
            _expression(3, schema_id=NULLABLE_SAFE_UINT_SCHEMA_ID),
            _expression(3, schema_id=SAFE_UINT_SCHEMA_ID),
        ),
    )
    assert run(
        "PRESENT_LE",
        (
            _expression(3, schema_id=NULLABLE_SAFE_UINT_SCHEMA_ID),
            _expression(4, schema_id=NULLABLE_SAFE_UINT_SCHEMA_ID),
        ),
    )
    safe_one = _expression(1, schema_id=SAFE_UINT_SCHEMA_ID)
    safe_two = _expression(2, schema_id=SAFE_UINT_SCHEMA_ID)
    assert (
        run(
            "SAFE_ADD",
            (safe_one, safe_two),
            schema_id=SAFE_UINT_SCHEMA_ID,
        )
        == 3
    )
    assert (
        run(
            "SAFE_MULTIPLY",
            (safe_two, safe_two),
            schema_id=SAFE_UINT_SCHEMA_ID,
        )
        == 4
    )
    assert (
        run(
            "SAFE_FLOOR_DIVIDE",
            (_expression(5, schema_id=SAFE_UINT_SCHEMA_ID), safe_two),
            schema_id=SAFE_UINT_SCHEMA_ID,
        )
        == 2
    )
    assert (
        run(
            "SAFE_CEIL_DIVIDE",
            (_expression(5, schema_id=SAFE_UINT_SCHEMA_ID), safe_two),
            schema_id=SAFE_UINT_SCHEMA_ID,
        )
        == 3
    )

    raw_array = _expression(["a", "b"], schema_id=RAW_TEXT_ARRAY_SCHEMA_ID)
    assert (
        run(
            "ARRAY_LENGTH",
            (raw_array,),
            schema_id=SAFE_UINT_SCHEMA_ID,
        )
        == 2
    )
    assert run("ARRAY_UNIQUE", (raw_array,))
    assert run(
        "ARRAY_STRICT_ASCENDING",
        (_expression(["a", "b"], schema_id=FIXED_MAP_KEY_ARRAY_SCHEMA_ID),),
    )
    assert run("ARRAY_POSITIONAL_EQUAL", (raw_array, raw_array))
    fixed_entries = _expression(
        [{"key": "a", "value": 1}, {"key": "b", "value": 2}],
        schema_id=FIXED_MAP_ARRAY_SCHEMA_ID,
    )
    assert run(
        "ARRAY_PROJECT_REQUIRED_MEMBER",
        (fixed_entries,),
        schema_id=FIXED_MAP_KEY_ARRAY_SCHEMA_ID,
        path=("key",),
    ) == ["a", "b"]
    assert run(
        "ARRAY_CONTAINS",
        (raw_array, _expression("b", schema_id=RAW_TEXT_SCHEMA_ID)),
    )

    descriptors = runtime.literal_authority["target_field_registry"]["descriptors"]
    descriptor_array_schema = _member_schema_id(
        runtime,
        "TargetFieldRegistryV1",
        "descriptors",
    )
    descriptor_schema = runtime.schemas[descriptor_array_schema][
        "array_item_value_schema_id"
    ]
    first_descriptor = descriptors[0]
    field_id_schema = _member_schema_id(
        runtime,
        "CapacityMeasurementTargetFieldDescriptorV1",
        "field_id",
    )
    assert (
        run(
            "ARRAY_FIND_UNIQUE_OBJECT_BY_MEMBER",
            (
                _expression(descriptors, schema_id=descriptor_array_schema),
                _expression(
                    first_descriptor["field_id"],
                    schema_id=field_id_schema,
                ),
            ),
            schema_id=descriptor_schema,
            path=("field_id",),
        )
        == first_descriptor
    )
    assert (
        run(
            "OBJECT_MEMBER",
            (
                _expression(
                    {"key": "a", "value": 1},
                    schema_id=FIXED_MAP_ENTRY_SCHEMA_ID,
                ),
            ),
            schema_id=SAFE_UINT_SCHEMA_ID,
            path=("value",),
        )
        == 1
    )

    assert (
        run(
            "TIMESTAMP_TO_EPOCH_MICROSECONDS",
            (_expression("1970-01-01T00:00:00.000001Z", schema_id=RFC3339_SCHEMA_ID),),
            result_type_kind="INTERNAL_INT128",
        )
        == 1
    )
    maximum_uint128_text = str(runtime_module.UINT128_MAXIMUM)
    assert (
        run(
            "UINT128_PARSE",
            (_expression(maximum_uint128_text, schema_id=UINT128_TEXT_SCHEMA_ID),),
            result_type_kind="INTERNAL_UINT128",
        )
        == runtime_module.UINT128_MAXIMUM
    )
    assert (
        run(
            "SAFE_UINT_TO_INTERNAL_UINT128",
            (safe_two,),
            result_type_kind="INTERNAL_UINT128",
        )
        == 2
    )
    assert (
        run(
            "UINT128_ADD",
            (internal_one, internal_two),
            result_type_kind="INTERNAL_UINT128",
        )
        == 3
    )
    assert (
        run(
            "UINT128_MULTIPLY",
            (internal_two, internal_two),
            result_type_kind="INTERNAL_UINT128",
        )
        == 4
    )
    decoded = run(
        "BASE64_DECODE",
        (_expression("YQ==", schema_id=FRAME_BASE64_SCHEMA_ID),),
        result_type_kind="INTERNAL_BYTES",
    )
    assert decoded == b"a"
    assert (
        run(
            "BASE64_ARRAY_DECODE_CONCAT",
            (
                _expression(
                    ["YQ==", "Yg=="],
                    schema_id=INGRESS_BASE64_ARRAY_SCHEMA_ID,
                ),
                _expression(2, schema_id=SAFE_UINT_SCHEMA_ID),
            ),
            result_type_kind="INTERNAL_BYTES",
        )
        == b"ab"
    )
    assert (
        run(
            "INTERNAL_BYTES_LENGTH",
            (_expression(b"a", "INTERNAL_BYTES", None),),
            schema_id=SAFE_UINT_SCHEMA_ID,
        )
        == 1
    )
    assert (
        run(
            "SHA256_BYTES",
            (_expression(b"a", "INTERNAL_BYTES", None),),
            schema_id=LOWERCASE_SHA_SCHEMA_ID,
        )
        == hashlib.sha256(b"a").hexdigest()
    )
    chunks = ["YQ=="]
    ingress_digest = hashlib.sha256(
        runtime_module._canonical_bytes(
            {
                "domain": "RiskYieldMMExactOrderedDecryptedIngressChunksV4_5",
                "ordered_chunks_base64": chunks,
            }
        )
    ).hexdigest()
    assert run(
        "RAW_INGRESS_BATCH_ID_RECOMPUTES",
        (
            _expression(chunks, schema_id=INGRESS_BASE64_ARRAY_SCHEMA_ID),
            _expression(ingress_digest, schema_id=LOWERCASE_SHA_SCHEMA_ID),
        ),
    )
    assert run(
        "RFC6455_CLOSE_PAYLOAD_VALID",
        (
            _expression("CLOSE", schema_id=RFC6455_OPCODE_SCHEMA_ID),
            _expression(b"\x03\xe8ok", "INTERNAL_BYTES", None),
        ),
    )
    assert run(
        "FIELD_LAYER_EQUALS_UPPERCASE_FIELD_PREFIX",
        (
            _expression("A1", schema_id=LAYER_SCHEMA_ID),
            _expression("a1.active_count", schema_id=FIELD_ID_SCHEMA_ID),
        ),
    )

    source_payload = {
        "field_id": "kernel.siocinq_unread_octets",
        "observation_method": "LINUX_IOCTL",
        "source_failure_phase": "SOURCE_ADAPTER",
        "source_errno_number": 5,
        "source_errno_name": "EIO",
        "source_error_class": "builtins.OSError",
    }
    source_error = _semantic_record(runtime, "SourceErrorDetailV1", source_payload)
    source_id = source_error["source_error_detail_sha256"]
    source_expression = _expression(source_error, schema_id=SOURCE_ERROR_SCHEMA_ID)
    assert run(
        "SEMANTIC_ID_RECOMPUTES",
        (
            source_expression,
            _expression(source_id, schema_id=LOWERCASE_SHA_SCHEMA_ID),
        ),
    )
    assert run("CANONICAL_BYTES_SATISFY_BOUND", (source_expression,))
    assert exercised == runtime_module.GENERIC_OPERATOR_NAMES


def test_generic_operator_defining_failure_edges_are_deterministic(runtime):
    safe_maximum = _expression(
        runtime_module.SAFE_INTEGER_MAXIMUM,
        schema_id=SAFE_UINT_SCHEMA_ID,
    )
    safe_one = _expression(1, schema_id=SAFE_UINT_SCHEMA_ID)
    for operator in ("SAFE_ADD", "SAFE_MULTIPLY"):
        with pytest.raises(runtime_module.ConstraintViolation):
            _execute_operator(
                runtime,
                operator,
                (safe_maximum, _expression(2, schema_id=SAFE_UINT_SCHEMA_ID)),
                schema_id=SAFE_UINT_SCHEMA_ID,
            )
    for operator in ("SAFE_FLOOR_DIVIDE", "SAFE_CEIL_DIVIDE"):
        with pytest.raises(runtime_module.ConstraintViolation):
            _execute_operator(
                runtime,
                operator,
                (safe_one, _expression(0, schema_id=SAFE_UINT_SCHEMA_ID)),
                schema_id=SAFE_UINT_SCHEMA_ID,
            )
    maximum = _expression(
        runtime_module.UINT128_MAXIMUM,
        "INTERNAL_UINT128",
        None,
    )
    with pytest.raises(runtime_module.ConstraintViolation):
        _execute_operator(
            runtime,
            "UINT128_ADD",
            (maximum, _expression(1, "INTERNAL_UINT128", None)),
            result_type_kind="INTERNAL_UINT128",
        )
    with pytest.raises(runtime_module.ConstraintViolation):
        _execute_operator(
            runtime,
            "UINT128_MULTIPLY",
            (maximum, _expression(2, "INTERNAL_UINT128", None)),
            result_type_kind="INTERNAL_UINT128",
        )
    with pytest.raises(runtime_module.ConstraintViolation):
        _execute_operator(
            runtime,
            "BASE64_DECODE",
            (_expression("YQ", schema_id=FRAME_BASE64_SCHEMA_ID),),
            result_type_kind="INTERNAL_BYTES",
        )
    with pytest.raises(runtime_module.ConstraintViolation):
        _execute_operator(
            runtime,
            "BASE64_ARRAY_DECODE_CONCAT",
            (
                _expression(["YQ=="], schema_id=INGRESS_BASE64_ARRAY_SCHEMA_ID),
                _expression(0, schema_id=SAFE_UINT_SCHEMA_ID),
            ),
            result_type_kind="INTERNAL_BYTES",
        )
    for invalid in (
        "1970-01-01T00:00:00.000000Z",
        "1970-01-01T24:00:00Z",
        "1970-02-30T00:00:00Z",
    ):
        with pytest.raises(runtime_module.ConstraintViolation):
            _execute_operator(
                runtime,
                "TIMESTAMP_TO_EPOCH_MICROSECONDS",
                (_expression(invalid, schema_id=RFC3339_SCHEMA_ID),),
                result_type_kind="INTERNAL_INT128",
            )
    with pytest.raises(runtime_module.UnresolvedReference):
        _execute_operator(
            runtime,
            "ARRAY_FIND_UNIQUE_OBJECT_BY_MEMBER",
            (
                _expression(
                    [{"key": "a", "value": 1}, {"key": "a", "value": 2}],
                    schema_id=FIXED_MAP_ARRAY_SCHEMA_ID,
                ),
                _expression("a", schema_id=FIXED_MAP_KEY_SCHEMA_ID),
            ),
            schema_id=FIXED_MAP_ENTRY_SCHEMA_ID,
            path=("key",),
        )
    assert not _execute_operator(
        runtime,
        "RFC6455_CLOSE_PAYLOAD_VALID",
        (
            _expression("CLOSE", schema_id=RFC6455_OPCODE_SCHEMA_ID),
            _expression(b"\x03", "INTERNAL_BYTES", None),
        ),
    )
    assert not _execute_operator(
        runtime,
        "RFC6455_CLOSE_PAYLOAD_VALID",
        (
            _expression("CLOSE", schema_id=RFC6455_OPCODE_SCHEMA_ID),
            _expression(b"\x03\xe8\xff", "INTERNAL_BYTES", None),
        ),
    )


def test_generic_operator_business_false_and_boundary_edges(runtime):
    safe_one = _expression(1, schema_id=SAFE_UINT_SCHEMA_ID)
    safe_two = _expression(2, schema_id=SAFE_UINT_SCHEMA_ID)
    assert _execute_operator(runtime, "LT", (safe_one, safe_two))
    assert _execute_operator(
        runtime,
        "LT",
        (
            _expression("a", schema_id=FIXED_MAP_KEY_SCHEMA_ID),
            _expression("\u00e9", schema_id=FIXED_MAP_KEY_SCHEMA_ID),
        ),
    )
    assert _execute_operator(
        runtime,
        "LT",
        (
            _expression(-1, "INTERNAL_INT128", None),
            _expression(0, "INTERNAL_INT128", None),
        ),
    )
    assert not _execute_operator(
        runtime,
        "PRESENT_EQ",
        (
            _expression(None, schema_id=NULLABLE_SAFE_UINT_SCHEMA_ID),
            safe_one,
        ),
    )
    assert not _execute_operator(
        runtime,
        "PRESENT_LE",
        (
            _expression(None, schema_id=NULLABLE_SAFE_UINT_SCHEMA_ID),
            _expression(1, schema_id=NULLABLE_SAFE_UINT_SCHEMA_ID),
        ),
    )

    entries = _expression(
        [{"key": "a", "value": 1}],
        schema_id=FIXED_MAP_ARRAY_SCHEMA_ID,
    )
    with pytest.raises(runtime_module.UnresolvedReference):
        _execute_operator(
            runtime,
            "ARRAY_FIND_UNIQUE_OBJECT_BY_MEMBER",
            (
                entries,
                _expression("missing", schema_id=FIXED_MAP_KEY_SCHEMA_ID),
            ),
            schema_id=FIXED_MAP_ENTRY_SCHEMA_ID,
            path=("key",),
        )

    for invalid in (
        "01",
        str(runtime_module.UINT128_MAXIMUM + 1),
        "9" * 5_000,
    ):
        with pytest.raises(runtime_module.ConstraintViolation):
            _execute_operator(
                runtime,
                "UINT128_PARSE",
                (_expression(invalid, schema_id=UINT128_TEXT_SCHEMA_ID),),
                result_type_kind="INTERNAL_UINT128",
            )

    chunks = ["YQ=="]
    assert not _execute_operator(
        runtime,
        "RAW_INGRESS_BATCH_ID_RECOMPUTES",
        (
            _expression(chunks, schema_id=INGRESS_BASE64_ARRAY_SCHEMA_ID),
            _expression("0" * 64, schema_id=LOWERCASE_SHA_SCHEMA_ID),
        ),
    )
    source_payload = {
        "field_id": "kernel.siocinq_unread_octets",
        "observation_method": "LINUX_IOCTL",
        "source_failure_phase": "SOURCE_ADAPTER",
        "source_errno_number": 5,
        "source_errno_name": "EIO",
        "source_error_class": "builtins.OSError",
    }
    source_error = _semantic_record(runtime, "SourceErrorDetailV1", source_payload)
    assert not _execute_operator(
        runtime,
        "SEMANTIC_ID_RECOMPUTES",
        (
            _expression(source_error, schema_id=SOURCE_ERROR_SCHEMA_ID),
            _expression("0" * 64, schema_id=LOWERCASE_SHA_SCHEMA_ID),
        ),
    )


def test_uint128_language_rejects_unbounded_decimal_before_host_int_conversion(
    runtime,
):
    with pytest.raises(runtime_module.ConstraintViolation) as caught:
        runtime.validate_schema(UINT128_TEXT_SCHEMA_ID, "9" * 4_301)
    assert caught.value.failure_class == "CONSTRAINT_VIOLATION"


@pytest.mark.parametrize(
    "status_code",
    [
        1000,
        1001,
        1002,
        1003,
        1007,
        1008,
        1009,
        1010,
        1011,
        1012,
        1013,
        1014,
        3000,
        4999,
    ],
)
def test_rfc6455_close_payload_accepts_exact_frozen_status_boundaries(
    runtime,
    status_code,
):
    assert _execute_operator(
        runtime,
        "RFC6455_CLOSE_PAYLOAD_VALID",
        (
            _expression("CLOSE", schema_id=RFC6455_OPCODE_SCHEMA_ID),
            _expression(
                status_code.to_bytes(2, byteorder="big") + b"reason",
                "INTERNAL_BYTES",
                None,
            ),
        ),
    )


@pytest.mark.parametrize("status_code", [999, 1004, 1005, 1006, 1015, 2999, 5000])
def test_rfc6455_close_payload_rejects_codes_outside_frozen_language(
    runtime,
    status_code,
):
    assert not _execute_operator(
        runtime,
        "RFC6455_CLOSE_PAYLOAD_VALID",
        (
            _expression("CLOSE", schema_id=RFC6455_OPCODE_SCHEMA_ID),
            _expression(
                status_code.to_bytes(2, byteorder="big"),
                "INTERNAL_BYTES",
                None,
            ),
        ),
    )


def test_rfc6455_empty_close_and_non_close_payload_semantics(runtime):
    assert _execute_operator(
        runtime,
        "RFC6455_CLOSE_PAYLOAD_VALID",
        (
            _expression("CLOSE", schema_id=RFC6455_OPCODE_SCHEMA_ID),
            _expression(b"", "INTERNAL_BYTES", None),
        ),
    )
    assert _execute_operator(
        runtime,
        "RFC6455_CLOSE_PAYLOAD_VALID",
        (
            _expression("PONG", schema_id=RFC6455_OPCODE_SCHEMA_ID),
            _expression(b"\xff", "INTERNAL_BYTES", None),
        ),
    )


def test_array_unique_is_exact_for_composites_and_linear_in_item_count(
    runtime,
    monkeypatch,
):
    left = {"key": "a", "value": 1}
    right = {"value": 1, "key": "a"}
    assert not _execute_operator(
        runtime,
        "ARRAY_UNIQUE",
        (
            _expression(
                [left, right],
                schema_id=FIXED_MAP_ARRAY_SCHEMA_ID,
            ),
        ),
    )

    original = runtime_module._canonical_bytes
    calls = 0

    def counted(value):
        nonlocal calls
        calls += 1
        return original(value)

    monkeypatch.setattr(runtime_module, "_canonical_bytes", counted)
    item_count = 2_048
    assert _execute_operator(
        runtime,
        "ARRAY_UNIQUE",
        (
            _expression(
                [f"item-{index}" for index in range(item_count)],
                schema_id=RAW_TEXT_ARRAY_SCHEMA_ID,
            ),
        ),
    )
    assert calls == item_count


@pytest.mark.parametrize(
    ("operator", "left"),
    [("AND", False), ("OR", True), ("IMPLIES", False)],
)
def test_boolean_operators_reject_invalid_rhs_even_when_lhs_decides_result(
    runtime,
    operator,
    left,
):
    with pytest.raises(runtime_module.TypeMismatch):
        _execute_operator(
            runtime,
            operator,
            (
                _expression(left),
                _expression(1, schema_id=SAFE_UINT_SCHEMA_ID),
            ),
        )


def test_expression_results_are_validated_before_any_consumer(runtime):
    node = _operator_node("EQ")
    with pytest.raises(runtime_module.TypeMismatch):
        runtime._validate_expression_result(
            node,
            _expression(1, schema_id=BOOL_SCHEMA_ID),
        )
    internal_node = _operator_node(
        "UINT128_PARSE",
        result_type_kind="INTERNAL_UINT128",
    )
    with pytest.raises(runtime_module.TypeMismatch):
        runtime._validate_expression_result(
            internal_node,
            _expression(True, "INTERNAL_UINT128", None),
        )


def test_expression_result_declaration_must_equal_its_frozen_node(runtime):
    node = _operator_node("EQ")
    with pytest.raises(runtime_module.ImpossibleState):
        runtime._validate_expression_result(
            node,
            _expression("x", schema_id=RAW_TEXT_SCHEMA_ID),
        )
    with pytest.raises(runtime_module.ImpossibleState):
        runtime._validate_expression_result(
            node,
            _expression(b"x", "INTERNAL_BYTES", None),
        )


def test_all_binding_kinds_enforce_exact_nullability_and_concrete_type(runtime):
    bindings = [
        binding
        for rule in runtime.rules.values()
        for binding in rule["ordered_rule_input_bindings"]
    ]
    observed = {binding["binding_kind"] for binding in bindings}
    for binding in bindings:
        runtime._assert_binding_type_contract(binding)
    assert observed == {
        "RECORD",
        "SAFE_UINT",
        "FIXED_RECORD_SEQUENCE",
        "OPTIONAL_FIXED_RECORD",
    }

    optional = copy.deepcopy(
        next(
            binding
            for binding in bindings
            if binding["binding_kind"] == "OPTIONAL_FIXED_RECORD"
        )
    )
    optional["binding_kind"] = "RECORD"
    with pytest.raises(runtime_module.ImpossibleState):
        runtime._assert_binding_type_contract(optional)

    nullable_uint = {
        "binding_kind": "SAFE_UINT",
        "expected_type_name": None,
        "expected_value_schema_id": NULLABLE_SAFE_UINT_SCHEMA_ID,
    }
    with pytest.raises(runtime_module.ImpossibleState):
        runtime._assert_binding_type_contract(nullable_uint)

    invalid_sequence = {
        "binding_kind": "FIXED_RECORD_SEQUENCE",
        "expected_type_name": "CheckpointSelectorV1",
        "expected_value_schema_id": optional["expected_value_schema_id"],
    }
    with pytest.raises(runtime_module.ImpossibleState):
        runtime._assert_binding_type_contract(invalid_sequence)


@pytest.mark.parametrize(
    ("authority_name", "type_name", "expected_invocations", "expected_nodes"),
    [
        ("marker_contract", "MarkerContractV1", 14, 1042),
        (
            "operation_counter_schema",
            "OperationCounterSnapshotSchemaV1",
            1,
            7,
        ),
        ("target_field_registry", "TargetFieldRegistryV1", 485, 5032),
    ],
)
def test_composite_literal_rules_execute_recursive_frozen_oracle(
    runtime,
    authority_name,
    type_name,
    expected_invocations,
    expected_nodes,
):
    evidence = runtime.evaluate_rule(
        f"RULE/INTRINSIC/{type_name}/V1",
        {"self": runtime.literal_authority[authority_name]},
    )
    assert evidence.root_value is True
    assert evidence.intrinsic_rule_invocations == expected_invocations
    assert evidence.total_expression_nodes == expected_nodes


def test_generic_rule_false_root_is_distinct_from_evaluation_failure(runtime):
    rule_id = "RULE/INTRINSIC/CapacityMeasurementFixedUIntMapValueV1/V1"
    positive = {
        "kind": "FIXED_UINT_MAP",
        "ordered": [{"key": "a", "value": 1}, {"key": "b", "value": 2}],
    }
    assert runtime.evaluate_rule(rule_id, {"self": positive}).root_value is True
    negative = copy.deepcopy(positive)
    negative["ordered"].reverse()
    evidence = runtime.evaluate_rule(
        rule_id,
        {"self": negative},
        require_true=False,
    )
    assert evidence.root_value is False
    with pytest.raises(runtime_module.BusinessRuleFalse) as caught:
        runtime.evaluate_rule(rule_id, {"self": negative})
    assert caught.value.failure_class == "BUSINESS_RULE_FALSE"


@pytest.mark.parametrize("invalid", [None, 0, 1, "false"])
def test_rule_require_true_control_requires_exact_boolean(runtime, invalid):
    with pytest.raises(runtime_module.TypeMismatch):
        runtime.evaluate_rule(
            "RULE/INTRINSIC/CapacityMeasurementFixedUIntMapValueV1/V1",
            {"self": {}},
            require_true=invalid,
        )


def _complex_selector(runtime, operation="INGRESS", marker_occurrences=()):
    entries = []
    for position, (marker, occurrence) in enumerate(marker_occurrences, start=1):
        entries.append(
            _semantic_record(
                runtime,
                "CheckpointSelectorEntryV1",
                {
                    "selector_position": position,
                    "operation_kind": operation,
                    "checkpoint_marker_kind": marker,
                    "occurrence_index_within_kind": occurrence,
                },
            )
        )
    return _semantic_record(
        runtime,
        "CheckpointSelectorV1",
        {
            "operation_kind": operation,
            "ordered_entries": entries,
            "selector_length": len(entries),
            "ordered_checkpoint_selector_entry_ids": [
                entry["checkpoint_selector_entry_id"] for entry in entries
            ],
        },
    )


def _complex_field(runtime, **overrides):
    payload = {
        "target_field_registry_id": runtime.literal_authority["target_field_registry"][
            "target_field_registry_id"
        ],
        "observation_context_id": "1" * 64,
        "field_id": "a1.active_count",
        "availability": "AVAILABLE",
        "value": {"kind": "UINT", "value": 1},
        "observation_method": "A1_OWNER_SNAPSHOT",
        "observation_attempt": "ATTEMPTED",
        "adapter_span_status": "AVAILABLE",
        "observation_started_offset_nanoseconds": 1,
        "observation_completed_offset_nanoseconds": 2,
        "unavailable_reason": None,
        "censoring": "NONE",
        "source_errno_number": None,
        "source_errno_name": None,
        "source_failure_phase": "NONE",
        "source_error_class": None,
        "source_error_detail_sha256": None,
    }
    payload.update(overrides)
    return _semantic_record(runtime, "TargetFieldObservationV1", payload)


def _descriptor(runtime, field_id):
    return next(
        descriptor
        for descriptor in runtime.literal_authority["target_field_registry"][
            "descriptors"
        ]
        if descriptor["field_id"] == field_id
    )


def _value_for_descriptor(runtime, descriptor):
    registry = runtime.literal_authority["target_field_registry"]
    constraint = next(
        item
        for item in registry["ordered_value_constraint_definitions"]
        if item["value_constraint_id"] == descriptor["value_constraint_id"]
    )
    shape = next(
        item
        for item in registry["ordered_value_shape_definitions"]
        if item["value_shape_id"] == descriptor["value_shape_id"]
    )
    kind = descriptor["value_kind"]
    if kind == "BOOL":
        return {"kind": kind, "value": True}
    if kind == "DURATION_BOUND":
        return {
            "kind": kind,
            "relation": "EXACT",
            "lower_nanoseconds": 1,
            "upper_nanoseconds": 1,
        }
    if kind == "FIXED_UINT_MAP":
        return {
            "kind": kind,
            "ordered": [{"key": key, "value": 0} for key in shape["ordered_keys"]],
        }
    if kind == "OPTIONAL_UINT":
        return {"kind": kind, "present": True, "value": 0}
    if kind == "UINT":
        minimum = constraint["integer_minimum"]
        return {"kind": kind, "value": minimum}
    if kind in {"TEXT", "OPTIONAL_TEXT"}:
        profile = constraint["scalar_profile"]
        if profile == "ENUM":
            vocabulary = next(
                item
                for item in registry["ordered_vocabulary_definitions"]
                if item["vocabulary_id"] == constraint["vocabulary_id"]
            )
            scalar = vocabulary["members"][0]
        elif profile == "PLATFORM_ERRNO":
            scalar = "EIO"
        elif profile == "SHA256":
            scalar = "0" * 64
        elif profile == "UINT128_DECIMAL":
            scalar = "0"
        else:
            raise AssertionError(profile)
        if kind == "OPTIONAL_TEXT":
            return {"kind": kind, "present": True, "value": scalar}
        return {"kind": kind, "value": scalar}
    if kind in {"UINT_LIST", "TEXT_LIST"}:
        count = max(1, shape["minimum_items"])
        if kind == "UINT_LIST":
            values = list(range(count))
        else:
            item_constraint = next(
                item
                for item in registry["ordered_value_constraint_definitions"]
                if item["value_constraint_id"]
                == constraint["collection_item_constraint_id"]
            )
            vocabulary = next(
                item
                for item in registry["ordered_vocabulary_definitions"]
                if item["vocabulary_id"] == item_constraint["vocabulary_id"]
            )
            values = [vocabulary["members"][0]] * count
        return {"kind": kind, "values": values}
    raise AssertionError(kind)


def _complex_operation_pair(kind):
    if kind == "SUBSCRIPTION_DISPATCH":
        spec_type = "SUBSCRIPTION_DISPATCH_SPEC_V2"
        result_type = "SUBSCRIPTION_DISPATCH_RESULT_EVIDENCE_V2"
        spec_body = {
            "expected_logical_opcode": "TEXT",
            "expected_dispatch_disposition": "COMPLETE",
        }
        result_body = {
            "generated_logical_opcode": "TEXT",
            "local_dispatch_disposition": "COMPLETE",
        }
    elif kind == "INGRESS":
        spec_type = "INGRESS_OPERATION_SPEC_V2"
        result_type = "INGRESS_RESULT_EVIDENCE_V2"
        spec_body = {
            "input_octet_count": 1,
            "expected_parser_unit_count": 2,
            "expected_completed_application_message_count": 3,
            "expected_logical_output_frame_count": 4,
            "expected_logical_output_payload_octets": 5,
            "expected_logical_output_frames_sha256": "0" * 64,
        }
        result_body = {
            "observed_consumed_new_input_octets": 1,
            "observed_parser_unit_count": 2,
            "observed_completed_application_message_count": 3,
            "observed_logical_output_frame_count": 4,
            "observed_logical_output_payload_octets": 5,
            "observed_logical_output_frames_sha256": "0" * 64,
        }
    elif kind == "ACK_DEADLINE_EXPIRY":
        spec_type = "ACK_DEADLINE_EXPIRY_SPEC_V1"
        result_type = "ACK_DEADLINE_EXPIRY_RESULT_EVIDENCE_V1"
        spec_body = {
            "expected_outbound_subscription_intent_id": "1" * 64,
            "due_scenario": "DUE",
        }
        result_body = {
            "due_decision_clock_evidence": {
                "outbound_subscription_intent_id": "1" * 64,
                "due_scenario": "DUE",
            }
        }
    elif kind == "LOCAL_SHUTDOWN":
        spec_type = "LOCAL_SHUTDOWN_SPEC_V2"
        result_type = "LOCAL_SHUTDOWN_RESULT_EVIDENCE_V2"
        spec_body = {"expected_terminal_outcome": "CLOSED"}
        result_body = {
            "terminal_outcome": "CLOSED",
            "ordered_terminal_ingress_read_attempt_event_ids": [],
            "ordered_terminal_parser_transition_event_ids": [],
        }
        pairs = (
            (
                "final_terminal_ingress_batch_count",
                "maximum_terminal_ingress_batches",
            ),
            (
                "final_terminal_ingress_ciphertext_octets",
                "maximum_terminal_ingress_ciphertext_octets",
            ),
            (
                "final_terminal_ingress_plaintext_octets",
                "maximum_terminal_ingress_plaintext_octets",
            ),
            (
                "final_terminal_socket_receive_call_count",
                "maximum_terminal_socket_receive_calls",
            ),
            (
                "final_terminal_tls_record_count",
                "maximum_terminal_tls_records",
            ),
            (
                "final_terminal_tls_unwrap_iteration_count",
                "maximum_terminal_tls_unwrap_iterations",
            ),
            (
                "final_terminal_zero_progress_iteration_count",
                "maximum_terminal_zero_progress_iterations",
            ),
            (
                "final_terminal_ingress_parser_unit_count",
                "maximum_terminal_ingress_parser_units",
            ),
            (
                "final_terminal_ingress_automatic_output_count",
                "maximum_terminal_ingress_automatic_outputs",
            ),
            (
                "final_websocket_send_attempt_count",
                "maximum_websocket_send_attempts",
            ),
            (
                "final_tls_control_send_attempt_count",
                "maximum_tls_control_send_attempts",
            ),
            (
                "final_peer_shutdown_poll_count",
                "maximum_peer_shutdown_polls",
            ),
        )
        for result_member, spec_member in pairs:
            result_body[result_member] = 0
            spec_body[spec_member] = 0
    else:
        raise AssertionError(kind)
    return (
        {
            "operation_kind": kind,
            "result_type": result_type,
            "result": result_body,
        },
        {
            "operation_kind": kind,
            "spec_type": spec_type,
            "spec": spec_body,
        },
    )


def _minimal_v2_observation(runtime, context, ordinal):
    context = {**context, "observation_context_id": f"{ordinal + 1:064x}"}
    return _semantic_record(
        runtime,
        "TargetObservationV2",
        {
            "observation_context": context,
            "observation_context_id": context["observation_context_id"],
            "field_observations": [],
        },
    )


def test_complex_bitmap_positive_false_and_type_failure(runtime):
    assert _execute_operator(
        runtime,
        "BITMAP_NULLABILITY_MATCHES",
        [_expression("10" * 33), _expression([1, None] * 33)],
    )
    assert not _execute_operator(
        runtime,
        "BITMAP_NULLABILITY_MATCHES",
        [_expression("01" * 33), _expression([1, None] * 33)],
    )
    with pytest.raises(runtime_module.TypeMismatch):
        _execute_operator(
            runtime,
            "BITMAP_NULLABILITY_MATCHES",
            [_expression(0), _expression([])],
        )


def test_complex_selector_intrinsic_positive_false_and_identity_work(runtime):
    selector = _complex_selector(
        runtime,
        marker_occurrences=(
            ("RAW_PREFIX_COMMITTED", 1),
            ("RAW_PREFIX_COMMITTED", 2),
            ("PARSER_UNIT_CONVERGED", 1),
        ),
    )
    counters = runtime_module._RuleCounters()
    assert runtime._execute_complex_operator(
        "CHECKPOINT_SELECTOR_INTRINSIC_VALID",
        [_expression(selector)],
        counters=counters,
        path=("test",),
    )
    assert counters.complex_operator_invocations == 1
    assert counters.complex_row_item_visits == 3
    assert counters.complex_canonicalized_octets > 0
    invalid = copy.deepcopy(selector)
    invalid["ordered_entries"][1]["occurrence_index_within_kind"] = 1
    assert not _execute_operator(
        runtime,
        "CHECKPOINT_SELECTOR_INTRINSIC_VALID",
        [_expression(invalid)],
    )
    malformed = copy.deepcopy(selector)
    malformed["operation_kind"] = "UNKNOWN"
    with pytest.raises(runtime_module.UnresolvedReference):
        _execute_operator(
            runtime,
            "CHECKPOINT_SELECTOR_INTRINSIC_VALID",
            [_expression(malformed)],
        )


def test_complex_selector_marker_contract_positive_and_authority_failure(runtime):
    selector = _complex_selector(
        runtime,
        marker_occurrences=(("RAW_PREFIX_COMMITTED", 1),),
    )
    contract = runtime.literal_authority["marker_contract"]
    assert _execute_operator(
        runtime,
        "CHECKPOINT_SELECTOR_MARKER_CONTRACT_ADMITTED",
        [_expression(selector), _expression(contract)],
    )
    inconsistent = copy.deepcopy(contract)
    inconsistent["ordered_checkpoint_operation_records"].pop()
    with pytest.raises(runtime_module.UnresolvedReference):
        _execute_operator(
            runtime,
            "CHECKPOINT_SELECTOR_MARKER_CONTRACT_ADMITTED",
            [_expression(selector), _expression(inconsistent)],
        )


@pytest.mark.parametrize(
    "mutator",
    [
        lambda field: field.update(observation_completed_offset_nanoseconds=0),
        lambda field: field.update(source_errno_name="EIO"),
        lambda field: field.update(observation_method="NOT_ATTEMPTED"),
        lambda field: field.update(censoring="LEFT"),
    ],
)
def test_complex_field_intrinsic_positive_and_independent_false_edges(runtime, mutator):
    field = _complex_field(runtime)
    assert _execute_operator(
        runtime,
        "FIELD_OBSERVATION_INTRINSIC_VALID",
        [_expression(field)],
    )
    invalid = copy.deepcopy(field)
    mutator(invalid)
    assert not _execute_operator(
        runtime,
        "FIELD_OBSERVATION_INTRINSIC_VALID",
        [_expression(invalid)],
    )


def test_complex_source_error_digest_and_preloaded_counter_regression(runtime):
    payload = {
        "field_id": "a1.active_count",
        "observation_method": "A1_OWNER_SNAPSHOT",
        "source_failure_phase": "SOURCE_ADAPTER",
        "source_errno_number": None,
        "source_errno_name": None,
        "source_error_class": "ExampleError",
    }
    digest = runtime_module._semantic_id(
        runtime_module.SOURCE_ERROR_DETAIL_DOMAIN,
        payload,
    )
    field = _complex_field(
        runtime,
        availability="UNAVAILABLE",
        value=None,
        unavailable_reason="OBSERVER_INTERNAL_ERROR",
        source_failure_phase="SOURCE_ADAPTER",
        source_error_class="ExampleError",
        source_error_detail_sha256=digest,
    )
    counters = runtime_module._RuleCounters(complex_canonicalized_octets=1_000_000)
    assert runtime._execute_complex_operator(
        "SOURCE_ERROR_DETAIL_ID_RECOMPUTES_FROM_FIELD",
        [_expression(field)],
        counters=counters,
        path=("test",),
    )
    corrupted = copy.deepcopy(field)
    corrupted["source_error_detail_sha256"] = "0" * 64
    assert not _execute_operator(
        runtime,
        "SOURCE_ERROR_DETAIL_ID_RECOMPUTES_FROM_FIELD",
        [_expression(corrupted)],
    )


@pytest.mark.parametrize(
    "kind",
    [
        "SUBSCRIPTION_DISPATCH",
        "INGRESS",
        "ACK_DEADLINE_EXPIRY",
        "LOCAL_SHUTDOWN",
    ],
)
def test_complex_signed_result_matrix_all_four_branches(runtime, kind):
    result, spec = _complex_operation_pair(kind)
    assert _execute_operator(
        runtime,
        "OPERATION_RESULT_MATCHES_SIGNED_SPEC",
        [_expression(result), _expression(spec)],
    )
    invalid = copy.deepcopy(result)
    if kind == "SUBSCRIPTION_DISPATCH":
        invalid["result"]["generated_logical_opcode"] = "BINARY"
    elif kind == "INGRESS":
        invalid["result"]["observed_parser_unit_count"] += 1
    elif kind == "ACK_DEADLINE_EXPIRY":
        invalid["result"]["due_decision_clock_evidence"]["due_scenario"] = "NOT_DUE"
    else:
        invalid["result"]["final_terminal_ingress_batch_count"] = 1
    assert not _execute_operator(
        runtime,
        "OPERATION_RESULT_MATCHES_SIGNED_SPEC",
        [_expression(invalid), _expression(spec)],
    )
    wrong_branch = copy.deepcopy(result)
    wrong_branch["result_type"] = "UNKNOWN"
    with pytest.raises(runtime_module.UnresolvedReference):
        _execute_operator(
            runtime,
            "OPERATION_RESULT_MATCHES_SIGNED_SPEC",
            [_expression(wrong_branch), _expression(spec)],
        )


def test_complex_all_17_target_value_constraints_positive(runtime):
    registry = runtime.literal_authority["target_field_registry"]
    observed = set()
    for constraint in registry["ordered_value_constraint_definitions"]:
        descriptor = next(
            item
            for item in registry["descriptors"]
            if item["value_constraint_id"] == constraint["value_constraint_id"]
        )
        field = {
            "target_field_registry_id": registry["target_field_registry_id"],
            "field_id": descriptor["field_id"],
            "value": _value_for_descriptor(runtime, descriptor),
        }
        assert _execute_operator(
            runtime,
            "TARGET_VALUE_SATISFIES_DESCRIPTOR",
            [_expression(field), _expression(descriptor), _expression(registry)],
        )
        observed.add(constraint["value_constraint_id"])
    assert len(observed) == 17


def test_complex_target_value_false_and_unresolved_authority(runtime):
    registry = runtime.literal_authority["target_field_registry"]
    descriptor = _descriptor(runtime, "loop.probe_interval_ns")
    field = {
        "target_field_registry_id": registry["target_field_registry_id"],
        "field_id": descriptor["field_id"],
        "value": {"kind": "UINT", "value": 999_999},
    }
    assert not _execute_operator(
        runtime,
        "TARGET_VALUE_SATISFIES_DESCRIPTOR",
        [_expression(field), _expression(descriptor), _expression(registry)],
    )
    duplicated = copy.deepcopy(registry)
    duplicated["ordered_value_constraint_definitions"][-1] = copy.deepcopy(
        duplicated["ordered_value_constraint_definitions"][0]
    )
    with pytest.raises(runtime_module.UnresolvedReference):
        _execute_operator(
            runtime,
            "TARGET_VALUE_SATISFIES_DESCRIPTOR",
            [_expression(field), _expression(descriptor), _expression(duplicated)],
        )


def test_complex_descriptor_policy_positive_false_and_failure(runtime):
    registry = runtime.literal_authority["target_field_registry"]
    descriptor = _descriptor(runtime, "a1.active_count")
    field = _complex_field(runtime)
    assert _execute_operator(
        runtime,
        "FIELD_OBSERVATION_SATISFIES_DESCRIPTOR_POLICY",
        [_expression(field), _expression(descriptor), _expression(registry)],
    )
    disallowed = copy.deepcopy(field)
    disallowed["availability"] = "UNAVAILABLE"
    disallowed["value"] = None
    disallowed["unavailable_reason"] = "NO_FROZEN_PRESSURE_POLICY"
    assert not _execute_operator(
        runtime,
        "FIELD_OBSERVATION_SATISFIES_DESCRIPTOR_POLICY",
        [_expression(disallowed), _expression(descriptor), _expression(registry)],
    )
    foreign_descriptor = copy.deepcopy(descriptor)
    foreign_descriptor["unit"] = "OTHER"
    with pytest.raises(runtime_module.UnresolvedReference):
        _execute_operator(
            runtime,
            "FIELD_OBSERVATION_SATISFIES_DESCRIPTOR_POLICY",
            [
                _expression(field),
                _expression(foreign_descriptor),
                _expression(registry),
            ],
        )


def test_complex_v2_context_positive_false_and_ordinal_taxonomy(runtime):
    registry = runtime.literal_authority["target_field_registry"]
    descriptor = _descriptor(runtime, "a1.active_count")
    ordinal = registry["descriptors"].index(descriptor)
    field = _complex_field(runtime)
    context = {
        "target_field_registry_id": registry["target_field_registry_id"],
        "observation_context_id": field["observation_context_id"],
        "checkpoint_binding_unavailable_reason": None,
        "operation_kind": "INGRESS",
        "attempt_id": "2" * 64,
        "instrumentation_mode": "ON",
        "observation_role": "BEFORE_OPERATION",
        "checkpoint_marker_kind": None,
        "observer_clock_span": {
            "span_status": "AVAILABLE",
            "started_offset_nanoseconds": 0,
            "completed_offset_nanoseconds": 3,
        },
    }
    operands = [
        _expression(field),
        _expression(descriptor),
        _expression(registry),
        _expression(context),
        _expression(ordinal),
    ]
    assert _execute_operator(
        runtime,
        "V2_FIELD_OBSERVATION_CONTEXT_VALID",
        operands,
    )
    outside = copy.deepcopy(context)
    outside["observer_clock_span"]["completed_offset_nanoseconds"] = 1
    assert not _execute_operator(
        runtime,
        "V2_FIELD_OBSERVATION_CONTEXT_VALID",
        [*operands[:3], _expression(outside), operands[4]],
    )
    assert not _execute_operator(
        runtime,
        "V2_FIELD_OBSERVATION_CONTEXT_VALID",
        [*operands[:4], _expression(185)],
    )
    assert not _execute_operator(
        runtime,
        "V2_FIELD_OBSERVATION_CONTEXT_VALID",
        [*operands[:4], _expression(ordinal + 1)],
    )
    with pytest.raises(runtime_module.TypeMismatch):
        _execute_operator(
            runtime,
            "V2_FIELD_OBSERVATION_CONTEXT_VALID",
            [*operands[:4], _expression(-1)],
        )


def test_complex_a1_fifo_positive_false_vacuous_and_authority_failure(runtime):
    registry = runtime.literal_authority["target_field_registry"]
    fields = [
        {
            "field_id": "a1.waiting_count",
            "availability": "AVAILABLE",
            "value": {"kind": "UINT", "value": 2},
        },
        {
            "field_id": "a1.waiting_sequences",
            "availability": "AVAILABLE",
            "value": {"kind": "UINT_LIST", "values": [1, 2]},
        },
        {
            "field_id": "a1.waiting_kinds",
            "availability": "AVAILABLE",
            "value": {"kind": "TEXT_LIST", "values": ["INGRESS", "INGRESS"]},
        },
    ]
    assert _execute_operator(
        runtime,
        "A1_FIFO_FIELDS_VALID",
        [_expression(fields), _expression(registry)],
    )
    invalid = copy.deepcopy(fields)
    invalid[1]["value"]["values"] = [2, 1]
    assert not _execute_operator(
        runtime,
        "A1_FIFO_FIELDS_VALID",
        [_expression(invalid), _expression(registry)],
    )
    unavailable = copy.deepcopy(invalid)
    unavailable[0]["availability"] = "UNAVAILABLE"
    assert _execute_operator(
        runtime,
        "A1_FIFO_FIELDS_VALID",
        [_expression(unavailable), _expression(registry)],
    )
    missing = copy.deepcopy(registry)
    missing["ordered_cross_field_constraint_definitions"] = []
    with pytest.raises(runtime_module.UnresolvedReference):
        _execute_operator(
            runtime,
            "A1_FIFO_FIELDS_VALID",
            [_expression(fields), _expression(missing)],
        )


def test_complex_v2_root_off_and_attempted_empty_selector_paths(runtime):
    base_context = {
        "candidate_id": "3" * 64,
        "attempt_id": None,
        "operation_kind": "INGRESS",
        "instrumentation_mode": "OFF",
        "target_field_registry_id": runtime.literal_authority["target_field_registry"][
            "target_field_registry_id"
        ],
    }
    observations = [
        _minimal_v2_observation(
            runtime,
            {**base_context, "observation_role": role},
            ordinal,
        )
        for ordinal, role in enumerate(
            ("BEFORE_OPERATION", "AFTER_OPERATION", "OPERATION_AGGREGATE")
        )
    ]
    root = {
        **base_context,
        "full_checkpoint_selector_id": None,
        "observation_count": 3,
        "ordered_observation_ids": [
            observation["observation_id"] for observation in observations
        ],
    }
    assert _execute_operator(
        runtime,
        "V2_ROOT_SEQUENCE_SELECTOR_VALID",
        [_expression(root), _expression(observations), _expression(None)],
    )
    invalid = copy.deepcopy(observations)
    invalid[1] = _minimal_v2_observation(
        runtime,
        {**base_context, "observation_role": "STABLE_CHECKPOINT"},
        1,
    )
    invalid_root = {
        **root,
        "ordered_observation_ids": [
            observation["observation_id"] for observation in invalid
        ],
    }
    assert not _execute_operator(
        runtime,
        "V2_ROOT_SEQUENCE_SELECTOR_VALID",
        [_expression(invalid_root), _expression(invalid), _expression(None)],
    )

    selector = _complex_selector(runtime)
    on_context = {
        **base_context,
        "attempt_id": "4" * 64,
        "instrumentation_mode": "ON",
    }
    on_observations = [
        _minimal_v2_observation(
            runtime,
            {**on_context, "observation_role": role},
            ordinal,
        )
        for ordinal, role in enumerate(
            ("BEFORE_OPERATION", "AFTER_OPERATION", "OPERATION_AGGREGATE")
        )
    ]
    on_root = {
        **on_context,
        "full_checkpoint_selector_id": selector["checkpoint_selector_id"],
        "observation_count": 3,
        "ordered_observation_ids": [
            observation["observation_id"] for observation in on_observations
        ],
    }
    assert _execute_operator(
        runtime,
        "V2_ROOT_SEQUENCE_SELECTOR_VALID",
        [_expression(on_root), _expression(on_observations), _expression(selector)],
    )
    corrupted = copy.deepcopy(on_observations)
    corrupted[0]["observation_id"] = "0" * 64
    with pytest.raises(runtime_module.UnresolvedReference):
        _execute_operator(
            runtime,
            "V2_ROOT_SEQUENCE_SELECTOR_VALID",
            [_expression(on_root), _expression(corrupted), _expression(selector)],
        )


def test_all_nine_complex_rules_are_in_the_exact_executable_partition(runtime):
    assert runtime.complex_rule_ids == {
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
    assert runtime.generic_rule_ids | runtime.complex_rule_ids == set(runtime.rules)
    assert not (runtime.generic_rule_ids & runtime.complex_rule_ids)


def test_complex_intrinsic_rules_execute_through_public_rule_api(runtime):
    selector = _complex_selector(
        runtime,
        marker_occurrences=(("RAW_PREFIX_COMMITTED", 1),),
    )
    selector_evidence = runtime.evaluate_rule(
        "RULE/INTRINSIC/CheckpointSelectorV1/V1",
        {"self": selector},
    )
    assert selector_evidence.root_value is True
    assert selector_evidence.complex_operator_invocations == 1
    assert selector_evidence.complex_row_item_visits == 1

    snapshot = {
        "counter_schema_id": runtime.literal_authority["operation_counter_schema"][
            "counter_schema_id"
        ],
        "availability_bitmap": "0" * 66,
        "values": [None] * 66,
    }
    snapshot_evidence = runtime.evaluate_rule(
        "RULE/INTRINSIC/OperationCounterSnapshotV1/V1",
        {"self": snapshot},
    )
    assert snapshot_evidence.root_value is True
    assert snapshot_evidence.complex_operator_invocations == 1
    assert snapshot_evidence.complex_row_item_visits == 66

    field = _complex_field(runtime)
    field_evidence = runtime.evaluate_rule(
        "RULE/INTRINSIC/TargetFieldObservationV1/V1",
        {"self": field},
    )
    assert field_evidence.root_value is True
    assert field_evidence.complex_operator_invocations == 2


def test_complex_cross_rules_execute_supplied_authority_through_public_api(runtime):
    selector = _complex_selector(
        runtime,
        marker_occurrences=(("RAW_PREFIX_COMMITTED", 1),),
    )
    selector_evidence = runtime.evaluate_rule(
        "RULE/CROSS/SELECTOR_MARKER_CONTRACT_V1",
        {
            "selector": selector,
            "marker_contract": runtime.literal_authority["marker_contract"],
        },
    )
    assert selector_evidence.root_value is True
    assert selector_evidence.complex_operator_invocations == 1

    field = _complex_field(runtime)
    registry = runtime.literal_authority["target_field_registry"]
    field_evidence = runtime.evaluate_rule(
        "RULE/CROSS/FIELD_OBSERVATION_FROZEN_REGISTRY_V1",
        {
            "field_observation": field,
            "target_registry": registry,
        },
    )
    assert field_evidence.root_value is True
    assert field_evidence.complex_operator_invocations == 2
    assert field_evidence.complex_row_item_visits > 0
    assert field_evidence.complex_canonicalized_octets > 0


def _application_record(binding_name, type_name, value):
    return runtime_module.ApplicationRecordInput(
        binding_name=binding_name,
        declared=runtime_module.TypedValue(
            value=value,
            type_name=type_name,
        ),
    )


def _application_sequence(binding_name, type_name, records):
    return runtime_module.ApplicationSequenceInput(
        binding_name=binding_name,
        ordered_records=tuple(
            runtime_module.TypedValue(value=value, type_name=type_name)
            for value in records
        ),
    )


def _first_five_application_inputs(runtime):
    fixtures = _complex_witness_fixtures()
    observation = fixtures["exact_marker_observation"]["value"]
    operation = fixtures["operation_pair_ingress"]["value"]
    return {
        "APPLY/COUNTER_SNAPSHOT_SCHEMA_V1": (
            _application_record(
                "counter_snapshot",
                "OperationCounterSnapshotV1",
                fixtures["counter_snapshot"]["value"],
            ),
            _application_record(
                "counter_schema",
                "OperationCounterSnapshotSchemaV1",
                runtime.literal_authority["operation_counter_schema"],
            ),
        ),
        "APPLY/FIELD_OBSERVATION_FROZEN_REGISTRY_V1": (
            _application_record(
                "field_observation",
                "TargetFieldObservationV1",
                observation["field_observations"][0],
            ),
            _application_record(
                "target_registry",
                "TargetFieldRegistryV1",
                runtime.literal_authority["target_field_registry"],
            ),
        ),
        "APPLY/OPERATION_RESULT_SIGNED_SPEC_V1": (
            _application_record(
                "result",
                "CapacityMeasurementOperationResultEvidence",
                operation["result"],
            ),
            _application_record(
                "signed_spec",
                "CapacityMeasurementOperationSpec",
                operation["signed_spec"],
            ),
        ),
        "APPLY/SELECTOR_MARKER_CONTRACT_V1": (
            _application_record(
                "selector",
                "CheckpointSelectorV1",
                fixtures["selector_ingress_one"]["value"],
            ),
            _application_record(
                "marker_contract",
                "MarkerContractV1",
                runtime.literal_authority["marker_contract"],
            ),
        ),
        "APPLY/V2_OBSERVATION_AGGREGATE_REGISTRY_V1": (
            _application_record(
                "observation",
                "TargetObservationV2",
                observation,
            ),
            _application_record(
                "target_registry",
                "TargetFieldRegistryV1",
                runtime.literal_authority["target_field_registry"],
            ),
        ),
    }


def test_first_five_record_tuple_applications_accept_with_exact_coordinate(runtime):
    for application_name, roots in _first_five_application_inputs(runtime).items():
        evidence = runtime.evaluate_application(application_name, roots)
        plan = runtime.compiled_applications[application_name]
        assert evidence.accepted is True
        assert evidence.charged_rule_evaluations == 1
        assert evidence.completed_rule_evaluations == 1
        assert evidence.maximum_rule_evaluations == 1
        assert (
            evidence.result_coordinate
            == runtime_module.ApplicationFailureCoordinate(
                application_name=application_name,
                rule_application_id=plan.rule_application_id,
                rule_id=plan.rule_id,
                iteration_ordinal=None,
                failure_class=None,
            )
        )
        assert tuple(evidence.result_coordinate.__dataclass_fields__) == (
            "application_name",
            "rule_application_id",
            "rule_id",
            "iteration_ordinal",
            "failure_class",
        )
        assert evidence.logical_record_graph_validations == len(roots)
        assert evidence.physical_record_graph_validations == len(roots)
        assert evidence.record_graph_validation_cache_hits == 0
        assert evidence.intrinsic_rule_logical_invocations >= (
            evidence.intrinsic_rule_physical_executions
        )
        assert evidence.intrinsic_rule_cache_hits == (
            evidence.intrinsic_rule_logical_invocations
            - evidence.intrinsic_rule_physical_executions
        )


def test_application_intrinsic_failure_precedes_cross_and_uses_intrinsic_rule(runtime):
    roots = list(
        _first_five_application_inputs(runtime)["APPLY/SELECTOR_MARKER_CONTRACT_V1"]
    )
    selector = copy.deepcopy(roots[0].declared.value)
    selector["selector_length"] = 0
    descriptor = runtime.records["CheckpointSelectorV1"]
    selector[descriptor["identity_field"]] = runtime_module._semantic_id(
        descriptor["described_record_domain"],
        {name: selector[name] for name in descriptor["identity_payload_member_order"]},
    )
    roots[0] = _application_record(
        "selector",
        "CheckpointSelectorV1",
        selector,
    )
    evidence = runtime.evaluate_application(
        "APPLY/SELECTOR_MARKER_CONTRACT_V1",
        tuple(roots),
    )
    assert evidence.accepted is False
    assert evidence.charged_rule_evaluations == 0
    assert evidence.completed_rule_evaluations == 0
    assert evidence.result_coordinate.rule_id == (
        "RULE/INTRINSIC/CheckpointSelectorV1/V1"
    )
    assert evidence.result_coordinate.iteration_ordinal is None
    assert evidence.result_coordinate.failure_class == "BUSINESS_RULE_FALSE"


@pytest.mark.parametrize("mutation", ["missing", "extra", "reordered", "wrong_type"])
def test_application_root_envelope_failures_are_zero_charge(runtime, mutation):
    application_name = "APPLY/COUNTER_SNAPSHOT_SCHEMA_V1"
    roots = list(_first_five_application_inputs(runtime)[application_name])
    if mutation == "missing":
        roots.pop()
    elif mutation == "extra":
        roots.append(roots[-1])
    elif mutation == "reordered":
        roots.reverse()
    else:
        roots[0] = _application_record(
            "counter_snapshot",
            "MarkerContractV1",
            runtime.literal_authority["marker_contract"],
        )
    evidence = runtime.evaluate_application(application_name, tuple(roots))
    assert evidence.accepted is False
    assert evidence.charged_rule_evaluations == 0
    assert evidence.completed_rule_evaluations == 0
    assert evidence.result_coordinate.iteration_ordinal is None
    assert evidence.result_coordinate.rule_id == (
        "RULE/CROSS/COUNTER_SNAPSHOT_SCHEMA_V1"
    )
    assert evidence.result_coordinate.failure_class in {
        "MALFORMED_OPERAND",
        "TYPE_OR_UNION_MISMATCH",
    }


def test_application_has_no_importable_prevalidated_execution_capability(runtime):
    assert not hasattr(runtime_module, "_PREVALIDATED_RULE_CAPABILITY")
    assert not hasattr(runtime, "_evaluate_rule_prevalidated")


@pytest.mark.parametrize("adversary", ["cycle", "subclass", "float", "depth"])
def test_application_snapshot_rejects_adversarial_values_without_host_helpers(
    runtime,
    adversary,
):
    application_name = "APPLY/COUNTER_SNAPSHOT_SCHEMA_V1"
    roots = list(_first_five_application_inputs(runtime)[application_name])
    snapshot = copy.deepcopy(roots[0].declared.value)
    if adversary == "cycle":
        snapshot["values"][0] = snapshot
        expected = "MALFORMED_OPERAND"
    elif adversary == "subclass":

        class DictSubclass(dict):
            def __deepcopy__(self, memo):
                raise AssertionError("deepcopy must not execute")

        snapshot = DictSubclass(snapshot)
        expected = "MALFORMED_OPERAND"
    elif adversary == "float":
        snapshot["values"][0] = 1.0
        expected = "MALFORMED_OPERAND"
    else:
        nested = None
        for _ in range(runtime_module.MAXIMUM_JSON_DEPTH + 2):
            nested = [nested]
        snapshot["unexpected"] = nested
        expected = "WORK_BOUND_EXCEEDED"
    roots[0] = _application_record(
        "counter_snapshot",
        "OperationCounterSnapshotV1",
        snapshot,
    )
    evidence = runtime.evaluate_application(application_name, tuple(roots))
    assert evidence.accepted is False
    assert evidence.charged_rule_evaluations == 0
    assert evidence.result_coordinate.failure_class == expected
    assert evidence.result_coordinate.iteration_ordinal is None


def test_application_snapshot_rejects_exact_ijson_edge_adversaries_without_hooks(
    runtime,
):
    class HostileList(list):
        def __iter__(self):
            raise AssertionError("list subclass iterator must not execute")

    class HostileInt(int):
        def __int__(self):
            raise AssertionError("integer subclass conversion must not execute")

        def __index__(self):
            raise AssertionError("integer subclass indexing must not execute")

    factories = (
        lambda value: value.update({"values": HostileList(value["values"])}),
        lambda value: value["values"].__setitem__(0, HostileInt(1)),
        lambda value: value["values"].__setitem__(
            0,
            runtime_module.SAFE_INTEGER_MAXIMUM + 1,
        ),
        lambda value: value.update({"counter_schema_id": "\ud800"}),
        lambda value: value.__setitem__("\ud800", None),
        lambda value: value.update({"values": tuple(value["values"])}),
        lambda value: value.update({"values": set()}),
        lambda value: value.__setitem__(1, None),
    )
    application_name = "APPLY/COUNTER_SNAPSHOT_SCHEMA_V1"
    baseline = _first_five_application_inputs(runtime)[application_name]
    for mutate in factories:
        candidate = copy.deepcopy(baseline[0].declared.value)
        mutate(candidate)
        evidence = runtime.evaluate_application(
            application_name,
            (
                _application_record(
                    "counter_snapshot",
                    "OperationCounterSnapshotV1",
                    candidate,
                ),
                baseline[1],
            ),
        )
        assert evidence.accepted is False
        assert evidence.charged_rule_evaluations == 0
        assert evidence.completed_rule_evaluations == 0
        assert evidence.result_coordinate.iteration_ordinal is None
        assert evidence.result_coordinate.failure_class == "MALFORMED_OPERAND"


def test_later_root_structural_failure_prevents_all_intrinsic_execution(runtime):
    roots = list(
        _first_five_application_inputs(runtime)["APPLY/SELECTOR_MARKER_CONTRACT_V1"]
    )
    invalid_later_root = copy.deepcopy(roots[1].declared.value)
    invalid_later_root["contract_version"] = 1
    roots[1] = _application_record(
        "marker_contract",
        "MarkerContractV1",
        invalid_later_root,
    )
    evidence = runtime.evaluate_application(
        "APPLY/SELECTOR_MARKER_CONTRACT_V1",
        tuple(roots),
    )
    assert evidence.accepted is False
    assert evidence.result_coordinate.failure_class == ("TYPE_OR_UNION_MISMATCH")
    assert evidence.charged_rule_evaluations == 0
    assert evidence.completed_rule_evaluations == 0
    assert evidence.intrinsic_rule_logical_invocations == 0
    assert evidence.intrinsic_rule_physical_executions == 0
    assert evidence.intrinsic_rule_cache_hits == 0
    assert evidence.logical_record_graph_validations == 2
    assert evidence.physical_record_graph_validations == 2
    assert evidence.validation_work_used > 0


def test_application_uses_private_snapshot_after_caller_value_changes(
    runtime,
    monkeypatch,
):
    application_name = "APPLY/COUNTER_SNAPSHOT_SCHEMA_V1"
    roots = list(_first_five_application_inputs(runtime)[application_name])
    mutable_caller_record = copy.deepcopy(roots[0].declared.value)
    roots[0] = _application_record(
        "counter_snapshot",
        "OperationCounterSnapshotV1",
        mutable_caller_record,
    )
    original = runtime._validate_application_record_graph
    changed = False

    def mutate_caller_after_snapshot(type_name, snapshot, **kwargs):
        nonlocal changed
        if not changed:
            changed = True
            mutable_caller_record["availability_bitmap"] = "1"
            mutable_caller_record["values"] = []
        return original(type_name, snapshot, **kwargs)

    monkeypatch.setattr(
        runtime,
        "_validate_application_record_graph",
        mutate_caller_after_snapshot,
    )
    evidence = runtime.evaluate_application(application_name, tuple(roots))
    assert changed is True
    assert evidence.accepted is True
    assert evidence.charged_rule_evaluations == 1


def test_array_each_executes_all_185_ordinals_and_preserves_failure_prefix(runtime):
    fixtures = _complex_witness_fixtures()
    observation = fixtures["exact_marker_observation"]["value"]
    roots = (
        _application_record(
            "observation",
            "TargetObservationV2",
            observation,
        ),
        _application_record(
            "target_registry",
            "TargetFieldRegistryV1",
            runtime.literal_authority["target_field_registry"],
        ),
    )
    evidence = runtime.evaluate_application(
        "APPLY/V2_OBSERVATION_FIELDS_REGISTRY_V1",
        roots,
    )
    assert evidence.accepted is True
    assert evidence.charged_rule_evaluations == 185
    assert evidence.completed_rule_evaluations == 185
    assert len(evidence.ordered_rule_step_evidence) == 185
    assert [
        evidence.ordered_rule_step_evidence[0].iteration_ordinal,
        evidence.ordered_rule_step_evidence[-1].iteration_ordinal,
    ] == [0, 184]

    mismatched = copy.deepcopy(observation)
    mismatched["field_observations"][1], mismatched["field_observations"][2] = (
        mismatched["field_observations"][2],
        mismatched["field_observations"][1],
    )
    _rehash_existing_record(runtime, mismatched, "TargetObservationV2")
    rejected = runtime.evaluate_application(
        "APPLY/V2_OBSERVATION_FIELDS_REGISTRY_V1",
        (
            _application_record(
                "observation",
                "TargetObservationV2",
                mismatched,
            ),
            roots[1],
        ),
    )
    assert rejected.accepted is False
    assert rejected.result_coordinate.failure_class == "UNRESOLVED_AUTHORITY"
    assert rejected.result_coordinate.iteration_ordinal == 1
    assert rejected.charged_rule_evaluations == 2
    assert rejected.completed_rule_evaluations == 1
    assert [step.iteration_ordinal for step in rejected.ordered_rule_step_evidence] == [
        0
    ]
    assert [step.root_value for step in rejected.ordered_rule_step_evidence] == [True]


def test_fixed_position_membership_executes_67_and_resolver_work_is_exact(runtime):
    root, observations, _selector = _application_recipe(
        runtime,
        "ordinary_on_max64_full67",
    )
    evidence = runtime.evaluate_application(
        "APPLY/V2_ROOT_OBSERVATION_MEMBERSHIP_V1",
        (
            _application_record(
                "root",
                "TargetObservationRootV2",
                root,
            ),
        ),
        (
            _application_sequence(
                "observation",
                "TargetObservationV2",
                observations,
            ),
        ),
    )
    assert evidence.accepted is True
    assert evidence.charged_rule_evaluations == 67
    assert evidence.completed_rule_evaluations == 67
    assert len(evidence.ordered_rule_step_evidence) == 67
    assert [
        evidence.ordered_rule_step_evidence[0].iteration_ordinal,
        evidence.ordered_rule_step_evidence[-1].iteration_ordinal,
    ] == [0, 66]
    assert evidence.resolver_invocations == 1
    assert evidence.resolver_source_identity_count == 67
    assert evidence.resolver_identity_logical_recomputations == 67
    assert evidence.resolver_identity_physical_recomputations == 67
    assert evidence.resolver_identity_cache_hits == 0
    assert evidence.resolver_logical_comparisons == 67
    assert evidence.logical_record_graph_validations == 68
    assert evidence.physical_record_graph_validations == 68
    assert evidence.record_graph_validation_cache_hits == 0


def test_resolver_preserves_source_order_and_never_deduplicates(runtime):
    root, observations, _selector = _application_recipe(
        runtime,
        "ordinary_off_three",
    )
    for supplied in (
        tuple(reversed(observations)),
        (observations[0], observations[0], observations[2]),
        observations[:-1],
    ):
        evidence = runtime.evaluate_application(
            "APPLY/V2_ROOT_OBSERVATION_MEMBERSHIP_V1",
            (
                _application_record(
                    "root",
                    "TargetObservationRootV2",
                    root,
                ),
            ),
            (
                _application_sequence(
                    "observation",
                    "TargetObservationV2",
                    supplied,
                ),
            ),
        )
        assert evidence.accepted is False
        assert evidence.result_coordinate.failure_class == ("UNRESOLVED_AUTHORITY")
        assert evidence.result_coordinate.iteration_ordinal is None
        assert evidence.charged_rule_evaluations == 0
        assert evidence.resolver_invocations == 1


def test_lifecycle_resolves_complete_and_optional_sequences_then_runs_once(runtime):
    root, observations, selector = _application_recipe(
        runtime,
        "ordinary_on_max64_full67",
    )
    evidence = runtime.evaluate_application(
        "APPLY/V2_ROOT_SELECTOR_LIFECYCLE_V1",
        (
            _application_record(
                "root",
                "TargetObservationRootV2",
                root,
            ),
        ),
        (
            _application_sequence(
                "observations",
                "TargetObservationV2",
                observations,
            ),
            _application_sequence(
                "selector",
                "CheckpointSelectorV1",
                (selector,),
            ),
        ),
    )
    assert evidence.accepted is True
    assert evidence.charged_rule_evaluations == 1
    assert evidence.completed_rule_evaluations == 1
    assert [step.iteration_ordinal for step in evidence.ordered_rule_step_evidence] == [
        None
    ]
    assert evidence.resolver_invocations == 2
    assert evidence.resolver_source_identity_count == 68
    assert evidence.resolver_identity_logical_recomputations == 68
    assert evidence.resolver_identity_physical_recomputations == 68
    assert evidence.resolver_identity_cache_hits == 0
    assert evidence.resolver_logical_comparisons == 68

    off_root, off_observations, off_selector = _application_recipe(
        runtime,
        "ordinary_off_three",
    )
    assert off_selector is None
    off = runtime.evaluate_application(
        "APPLY/V2_ROOT_SELECTOR_LIFECYCLE_V1",
        (
            _application_record(
                "root",
                "TargetObservationRootV2",
                off_root,
            ),
        ),
        (
            _application_sequence(
                "observations",
                "TargetObservationV2",
                off_observations,
            ),
            _application_sequence(
                "selector",
                "CheckpointSelectorV1",
                (),
            ),
        ),
    )
    assert off.accepted is True
    assert off.charged_rule_evaluations == 1
    assert off.completed_rule_evaluations == 1
    assert off.resolver_invocations == 2
    assert off.resolver_source_identity_count == 3


def test_later_external_intrinsic_failure_precedes_every_cross_candidate(runtime):
    root, observations, _selector = _application_recipe(
        runtime,
        "ordinary_off_three",
    )
    observations = list(observations)
    field = observations[-1]["field_observations"][0]
    field["source_error_detail_sha256"] = "0" * 64
    _rehash_existing_record(runtime, field, "TargetFieldObservationV1")
    _rehash_existing_record(runtime, observations[-1], "TargetObservationV2")
    root["ordered_observation_ids"][-1] = observations[-1]["observation_id"]
    _rehash_existing_record(runtime, root, "TargetObservationRootV2")
    evidence = runtime.evaluate_application(
        "APPLY/V2_ROOT_OBSERVATION_MEMBERSHIP_V1",
        (
            _application_record(
                "root",
                "TargetObservationRootV2",
                root,
            ),
        ),
        (
            _application_sequence(
                "observation",
                "TargetObservationV2",
                observations,
            ),
        ),
    )
    assert evidence.accepted is False
    assert evidence.result_coordinate.rule_id == (
        "RULE/INTRINSIC/TargetFieldObservationV1/V1"
    )
    assert evidence.result_coordinate.failure_class == "BUSINESS_RULE_FALSE"
    assert evidence.result_coordinate.iteration_ordinal is None
    assert evidence.charged_rule_evaluations == 0
    assert evidence.completed_rule_evaluations == 0
    assert evidence.ordered_rule_step_evidence == ()


def test_plain_impossible_and_compiled_plan_substitution_remain_fatal(
    runtime,
    monkeypatch,
):
    application_name = "APPLY/COUNTER_SNAPSHOT_SCHEMA_V1"
    roots = _first_five_application_inputs(runtime)[application_name]
    original_operator = runtime._execute_operator

    def impossible(*args, **kwargs):
        raise runtime_module.ImpossibleState("invariant defect")

    monkeypatch.setattr(runtime, "_execute_operator", impossible)
    with pytest.raises(runtime_module.ArtifactFailure):
        runtime.evaluate_application(application_name, roots)
    monkeypatch.setattr(runtime, "_execute_operator", original_operator)

    monkeypatch.setitem(
        runtime.compiled_applications,
        application_name,
        runtime.compiled_applications["APPLY/FIELD_OBSERVATION_FROZEN_REGISTRY_V1"],
    )
    with pytest.raises(runtime_module.ArtifactFailure):
        runtime.evaluate_application(application_name, roots)


@pytest.mark.parametrize(
    "mutated_rule_id",
    [
        "RULE/CROSS/COUNTER_SNAPSHOT_SCHEMA_V1",
        "RULE/INTRINSIC/OperationCounterSnapshotV1/V1",
    ],
)
def test_midcall_cross_or_intrinsic_rule_mutation_is_fatal(
    runtime,
    monkeypatch,
    mutated_rule_id,
):
    application_name = "APPLY/COUNTER_SNAPSHOT_SCHEMA_V1"
    roots = _first_five_application_inputs(runtime)[application_name]
    original = runtime._validate_application_record_graph
    mutated = False

    def mutate_rule_after_first_structural_validation(*args, **kwargs):
        nonlocal mutated
        result = original(*args, **kwargs)
        if not mutated:
            mutated = True
            final_node = runtime.rules[mutated_rule_id]["ordered_expression_nodes"][-1]
            monkeypatch.setitem(final_node, "operator", "OR")
        return result

    monkeypatch.setattr(
        runtime,
        "_validate_application_record_graph",
        mutate_rule_after_first_structural_validation,
    )
    with pytest.raises(runtime_module.ArtifactFailure):
        runtime.evaluate_application(application_name, roots)
    assert mutated is True


def test_cli_reports_runtime_only_boundary():
    completed = subprocess.run(
        [sys.executable, str(MODULE_PATH), "--repository-root", str(ROOT)],
        check=True,
        capture_output=True,
        text=True,
        cwd="/tmp",
    )
    report = json.loads(completed.stdout)
    assert report["status"] == (
        "APPLICATION_RUNTIME_ONLY_MAXIMA_AND_PRODUCTION_INTEGRATION_PENDING"
    )
    assert report["value_schema_count"] == 236
    assert report["external_type_count"] == 52
    assert report["generic_operator_count"] == 41
    assert report["complex_operator_count"] == 11
    assert report["generic_operator_node_count_across_full_catalog"] == 1044
    assert report["total_rule_expression_node_count"] == 1057
    assert report["executable_generic_rule_count"] == 33
    assert report["executable_complex_rule_count"] == 9
    assert report["executable_rule_count"] == 42
    assert report["executable_application_count"] == 8
    assert report["fixed_position_resolver_count"] == 2
    assert report["sum_of_per_application_maximum_rule_evaluations"] == 258
    assert report["sum_of_per_application_direct_expression_node_maxima"] == 3_154
    assert report["executable_expression_node_count"] == 1057
    assert report["unsupported_complex_rule_count"] == 0
    assert report["unsupported_complex_rule_expression_node_count"] == 0
    assert report["complex_operator_node_count_across_full_catalog"] == 13
    assert report["executed_literal_authority_intrinsic_rule_invocations"] == 500
    assert report["executed_literal_authority_expression_nodes"] == 6081
    assert report["total_rule_count"] == 42
    assert report["validation_work_limit"] == 4_202_555
    assert report["validation_work_unit"] == "SCHEMA_NODE_VISIT"
    assert report["validation_work_limit_kind"] == (
        "CONSERVATIVE_FROZEN_SCHEMA_MAXIMA_NOT_LEGAL_VALUE_MAXIMUM"
    )
    assert {
        key: (
            value["validation_work_used"],
            value["executed_intrinsic_rule_invocations"],
            value["executed_expression_nodes"],
        )
        for key, value in report[
            "validated_and_rule_executed_composite_authorities"
        ].items()
    } == {
        "marker_contract": (190, 14, 1042),
        "operation_counter_schema": (258, 1, 7),
        "target_field_registry": (21_180, 485, 5032),
    }
    assert set(report["validated_and_rule_executed_composite_authorities"]) == {
        "marker_contract",
        "operation_counter_schema",
        "target_field_registry",
    }


def test_cli_default_root_is_cwd_independent_and_isolated():
    completed = subprocess.run(
        [sys.executable, "-I", "-B", str(MODULE_PATH)],
        check=True,
        capture_output=True,
        text=True,
        cwd="/tmp",
    )
    assert completed.stderr == ""
    assert json.loads(completed.stdout)["executable_generic_rule_count"] == 33


def test_cli_failure_is_controlled_without_traceback(tmp_path):
    completed = subprocess.run(
        [
            sys.executable,
            str(MODULE_PATH),
            "--repository-root",
            str(tmp_path),
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd="/tmp",
    )
    assert completed.returncode == 1
    assert completed.stdout == ""
    assert completed.stderr.startswith("Raw-V8 Step-2 runtime validation error:")
    assert "Traceback" not in completed.stderr


def test_runtime_is_stdlib_only_and_has_no_production_imports():
    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".", 1)[0])
    assert imported_roots <= {
        "__future__",
        "argparse",
        "base64",
        "binascii",
        "collections",
        "copy",
        "dataclasses",
        "datetime",
        "hashlib",
        "json",
        "os",
        "pathlib",
        "re",
        "stat",
        "sys",
        "typing",
        "unicodedata",
    }
    assert not any(
        isinstance(node, ast.ImportFrom) and node.level for node in ast.walk(tree)
    )
    assert "__import__(" not in source
    assert "importlib" not in source
    assert "sys.path" not in source
    assert "riskyieldmm." not in source
    assert "validate_raw_v8_step2_external_schema_v2_structural_registry" not in source
    assert "validate_raw_v8_step2_external_schema_v2_rule_application" not in source

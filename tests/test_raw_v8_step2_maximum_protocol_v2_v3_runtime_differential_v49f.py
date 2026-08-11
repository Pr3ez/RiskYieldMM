"""Differential samples for the static A4-P6-V3 case-435 rule subset.

The production verifier remains stdlib-only and does not execute imported
authority code.  These tests run the separately pinned generic runtime only as
an out-of-process semantic oracle over the same complete records exercised by
the V3 static verifier acceptance tests.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from types import ModuleType
from typing import Any

import pytest

from tests.test_raw_v8_step2_maximum_protocol_v2_independent_verifier_expansion_v3_v49f import (
    INVENTORY,
    MEASURED_ORDINAL,
    REGISTRY,
    ROOT,
    VERIFIER,
    _aggregate_registry_false,
    _clone_bundle,
    _descriptor_policy_false,
    _mutated_root_bundle,
    _mutated_witness_bundle,
    _nonattaining_witness,
    _reseal_typed_record,
    _root_lifecycle_false,
    _root_membership_false,
)
from tests.test_raw_v8_step2_maximum_protocol_v2_independent_verifier_expansion_v3_v49f import (
    case435_fixture as case435_fixture,
)

RUNTIME = ROOT / (
    "scripts/tests/validate_raw_v8_step2_external_schema_v2_rule_runtime_v49f.py"
)
COMPLEX_WITNESS = ROOT / (
    "scripts/tests/raw_v8_step2_external_schema_v2_complex_rule_witness_v49f.json"
)


def _load_runtime_module() -> ModuleType:
    name = "_riskyieldmm_v3_case435_differential_runtime"
    specification = importlib.util.spec_from_file_location(name, RUNTIME)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    try:
        specification.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


def _load_static_module() -> ModuleType:
    name = "_riskyieldmm_v3_case435_static_subset"
    specification = importlib.util.spec_from_file_location(name, VERIFIER)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def generic_runtime() -> tuple[ModuleType, Any]:
    module = _load_runtime_module()
    return module, module.ExternalSchemaV2Runtime.load(ROOT)


@pytest.fixture(scope="module")
def static_subset() -> tuple[ModuleType, dict[str, Any], Any]:
    module = _load_static_module()
    registry = json.loads(REGISTRY.read_bytes())
    indexes = module._registry_indexes(registry)
    return module, indexes, module._Case435RuleRuntime(indexes)


def _record_input(
    module: ModuleType,
    binding_name: str,
    type_name: str,
    value: dict[str, Any],
) -> Any:
    return module.ApplicationRecordInput(
        binding_name=binding_name,
        declared=module.TypedValue(value=value, type_name=type_name),
    )


def _sequence_input(
    module: ModuleType,
    binding_name: str,
    type_name: str,
    values: list[dict[str, Any]],
) -> Any:
    return module.ApplicationSequenceInput(
        binding_name=binding_name,
        ordered_records=tuple(
            module.TypedValue(value=value, type_name=type_name) for value in values
        ),
    )


def _resolved_records(
    bundle: dict[str, Any],
) -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
]:
    candidate = bundle["candidate"]
    witness = candidate["candidate_payload"]["witness_record"]
    scope = candidate["candidate_payload"]["scope_witness_context"]
    rows = bundle["pack"]["ordered_context_object_records"]
    records = {row["maximum_context_object_id"]: row["record"] for row in rows}
    root = records[scope["root_record_reference"]["maximum_context_object_id"]]
    observations = []
    for reference in scope["ordered_observation_record_references"]:
        if reference["reference_kind"] == "WITNESS_RECORD":
            observations.append(witness)
        else:
            observations.append(records[reference["maximum_context_object_id"]])
    inventory = json.loads(INVENTORY.read_bytes())
    selector = inventory["checkpoint_selector_catalog"][3]["selector"]
    target_registry = inventory["target_field_registry"]
    marker_contract = inventory["marker_contract"]
    return root, observations, selector, target_registry, marker_contract


def _sample_all_application_families(
    module: ModuleType,
    runtime: Any,
    bundle: dict[str, Any],
) -> dict[str, Any]:
    root, observations, selector, target_registry, marker_contract = (
        _resolved_records(bundle)
    )
    measured = observations[MEASURED_ORDINAL]
    return {
        "selector": runtime.evaluate_application(
            "APPLY/SELECTOR_MARKER_CONTRACT_V1",
            (
                _record_input(module, "selector", "CheckpointSelectorV1", selector),
                _record_input(
                    module,
                    "marker_contract",
                    "MarkerContractV1",
                    marker_contract,
                ),
            ),
        ),
        "aggregate": runtime.evaluate_application(
            "APPLY/V2_OBSERVATION_AGGREGATE_REGISTRY_V1",
            (
                _record_input(
                    module, "observation", "TargetObservationV2", measured
                ),
                _record_input(
                    module,
                    "target_registry",
                    "TargetFieldRegistryV1",
                    target_registry,
                ),
            ),
        ),
        "fields": runtime.evaluate_application(
            "APPLY/V2_OBSERVATION_FIELDS_REGISTRY_V1",
            (
                _record_input(
                    module, "observation", "TargetObservationV2", measured
                ),
                _record_input(
                    module,
                    "target_registry",
                    "TargetFieldRegistryV1",
                    target_registry,
                ),
            ),
        ),
        "membership": runtime.evaluate_application(
            "APPLY/V2_ROOT_OBSERVATION_MEMBERSHIP_V1",
            (_record_input(module, "root", "TargetObservationRootV2", root),),
            (
                _sequence_input(
                    module, "observation", "TargetObservationV2", observations
                ),
            ),
        ),
        "lifecycle": runtime.evaluate_application(
            "APPLY/V2_ROOT_SELECTOR_LIFECYCLE_V1",
            (_record_input(module, "root", "TargetObservationRootV2", root),),
            (
                _sequence_input(
                    module, "observations", "TargetObservationV2", observations
                ),
                _sequence_input(
                    module, "selector", "CheckpointSelectorV1", [selector]
                ),
            ),
        ),
    }


def _measured_fields_evidence(
    module: ModuleType,
    runtime: Any,
    bundle: dict[str, Any],
) -> Any:
    _root, observations, _selector, target_registry, _marker = _resolved_records(
        bundle
    )
    return runtime.evaluate_application(
        "APPLY/V2_OBSERVATION_FIELDS_REGISTRY_V1",
        (
            _record_input(
                module,
                "observation",
                "TargetObservationV2",
                observations[MEASURED_ORDINAL],
            ),
            _record_input(
                module,
                "target_registry",
                "TargetFieldRegistryV1",
                target_registry,
            ),
        ),
    )


def test_v3_static_subset_positive_samples_match_the_pinned_generic_runtime(
    generic_runtime: tuple[ModuleType, Any],
    case435_fixture: dict[str, Any],
) -> None:
    module, runtime = generic_runtime
    evidence = _sample_all_application_families(
        module, runtime, _clone_bundle(case435_fixture)
    )
    assert set(evidence) == {
        "selector",
        "aggregate",
        "fields",
        "membership",
        "lifecycle",
    }
    assert all(row.accepted is True for row in evidence.values())
    assert all(
        row.result_coordinate.failure_class is None
        and row.result_coordinate.iteration_ordinal is None
        for row in evidence.values()
    )
    assert {
        name: row.completed_rule_evaluations for name, row in evidence.items()
    } == {
        "selector": 1,
        "aggregate": 1,
        "fields": 185,
        "membership": 67,
        "lifecycle": 1,
    }


def test_v3_static_subset_descriptor_rejection_matches_the_generic_runtime(
    generic_runtime: tuple[ModuleType, Any],
    case435_fixture: dict[str, Any],
) -> None:
    module, runtime = generic_runtime
    bundle = _mutated_witness_bundle(case435_fixture, _descriptor_policy_false)
    evidence = _measured_fields_evidence(module, runtime, bundle)
    assert evidence.accepted is False
    assert evidence.result_coordinate is not None
    assert evidence.result_coordinate.rule_id == (
        "RULE/CROSS/V2_OBSERVATION_FIELD_REGISTRY_V1"
    )
    assert evidence.result_coordinate.failure_class == "BUSINESS_RULE_FALSE"
    assert evidence.result_coordinate.iteration_ordinal == 20


def test_v3_p1_acceptance_does_not_replace_the_separate_p3_check(
    generic_runtime: tuple[ModuleType, Any],
    case435_fixture: dict[str, Any],
) -> None:
    module, runtime = generic_runtime
    bundle = _mutated_witness_bundle(case435_fixture, _nonattaining_witness)
    evidence = _measured_fields_evidence(module, runtime, bundle)
    assert evidence.accepted is True
    assert evidence.result_coordinate.failure_class is None
    assert evidence.result_coordinate.iteration_ordinal is None


def test_v3_field_context_rejection_matches_the_generic_runtime(
    generic_runtime: tuple[ModuleType, Any],
    case435_fixture: dict[str, Any],
) -> None:
    module, runtime = generic_runtime
    bundle = _mutated_witness_bundle(case435_fixture, _aggregate_registry_false)
    evidence = _measured_fields_evidence(module, runtime, bundle)
    assert evidence.accepted is False
    assert evidence.result_coordinate.rule_id == (
        "RULE/CROSS/V2_OBSERVATION_FIELD_REGISTRY_V1"
    )
    assert evidence.result_coordinate.failure_class == "BUSINESS_RULE_FALSE"
    assert evidence.result_coordinate.iteration_ordinal == 0


def test_v3_a1_fifo_true_and_false_samples_match_the_static_and_generic_runtimes(
    generic_runtime: tuple[ModuleType, Any],
    static_subset: tuple[ModuleType, dict[str, Any], Any],
) -> None:
    generic_module, generic = generic_runtime
    static_module, indexes, static = static_subset
    fixture = json.loads(COMPLEX_WITNESS.read_bytes())["fixture_records"]
    target_registry = json.loads(INVENTORY.read_bytes())["target_field_registry"]
    positive = copy.deepcopy(fixture["exact_marker_observation"]["value"])
    negative = copy.deepcopy(positive)
    count_field = negative["field_observations"][32]
    assert count_field["field_id"] == "a1.waiting_count"
    count_field["value"]["value"] = 1
    _reseal_typed_record(count_field, "TargetFieldObservationV1")
    _reseal_typed_record(negative, "TargetObservationV2")

    for observation, expected in ((positive, True), (negative, False)):
        evidence = generic.evaluate_application(
            "APPLY/V2_OBSERVATION_AGGREGATE_REGISTRY_V1",
            (
                _record_input(
                    generic_module,
                    "observation",
                    "TargetObservationV2",
                    observation,
                ),
                _record_input(
                    generic_module,
                    "target_registry",
                    "TargetFieldRegistryV1",
                    target_registry,
                ),
            ),
        )
        assert evidence.accepted is expected
        values = {
            "observation": observation,
            "target_registry": target_registry,
        }
        types = {
            "observation": "TargetObservationV2",
            "target_registry": "TargetFieldRegistryV1",
        }
        if expected:
            assert static_module._evaluate_subset_rule(
                indexes,
                "RULE/CROSS/V2_OBSERVATION_AGGREGATE_REGISTRY_V1",
                values,
                types,
                "CROSS_RECORD",
                static,
            ) == 3
        else:
            with pytest.raises(static_module.VerifierReject) as rejected:
                static_module._evaluate_subset_rule(
                    indexes,
                    "RULE/CROSS/V2_OBSERVATION_AGGREGATE_REGISTRY_V1",
                    values,
                    types,
                    "CROSS_RECORD",
                    static,
                )
            assert rejected.value.code == "WITNESS_ILLEGAL"


@pytest.mark.parametrize(
    ("mutation", "application_name", "expected_rule_id"),
    [
        (
            _root_membership_false,
            "APPLY/V2_ROOT_OBSERVATION_MEMBERSHIP_V1",
            "RULE/CROSS/V2_ROOT_OBSERVATION_MEMBERSHIP_V1",
        ),
        (
            _root_lifecycle_false,
            "APPLY/V2_ROOT_SELECTOR_LIFECYCLE_V1",
            "RULE/CROSS/V2_ROOT_SELECTOR_LIFECYCLE_V1",
        ),
    ],
    ids=["membership", "lifecycle"],
)
def test_v3_root_relation_rejections_match_the_generic_runtime(
    generic_runtime: tuple[ModuleType, Any],
    case435_fixture: dict[str, Any],
    mutation: Any,
    application_name: str,
    expected_rule_id: str,
) -> None:
    module, runtime = generic_runtime
    bundle = _mutated_root_bundle(case435_fixture, mutation)
    root, observations, selector, _registry, _marker = _resolved_records(bundle)
    if application_name == "APPLY/V2_ROOT_OBSERVATION_MEMBERSHIP_V1":
        evidence = runtime.evaluate_application(
            application_name,
            (_record_input(module, "root", "TargetObservationRootV2", root),),
            (
                _sequence_input(
                    module, "observation", "TargetObservationV2", observations
                ),
            ),
        )
    else:
        evidence = runtime.evaluate_application(
            application_name,
            (_record_input(module, "root", "TargetObservationRootV2", root),),
            (
                _sequence_input(
                    module, "observations", "TargetObservationV2", observations
                ),
                _sequence_input(
                    module, "selector", "CheckpointSelectorV1", [selector]
                ),
            ),
        )
    assert evidence.accepted is False
    assert evidence.result_coordinate.rule_id == expected_rule_id
    assert evidence.result_coordinate.failure_class == "UNRESOLVED_AUTHORITY"

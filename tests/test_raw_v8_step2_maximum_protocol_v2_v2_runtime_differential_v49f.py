"""Differential P1 checks for the static A4-P6-V2 case-69 subset.

The production verifier stays stdlib-only and never dynamically loads code.
This test uses the separately pinned runtime only as an out-of-process semantic
oracle for independently constructed result/spec records and hostile variants.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from collections.abc import Callable
from types import ModuleType
from typing import Any

import pytest

from tests.test_raw_v8_step2_maximum_protocol_v2_independent_verifier_expansion_v2_v49f import (
    CROSS_RULE_ID,
    INVENTORY,
    ROOT,
    _canonical_bytes,
    _case69_witness,
    _reseal_result,
)

CASE69_BODY_TYPE = "CapacityMeasurementLocalShutdownResultEvidenceV2"
CASE69_SPEC_BODY_TYPE = "CapacityMeasurementLocalShutdownSpecV2"
CASE69_RESULT_INTRINSIC_RULE = (
    "RULE/INTRINSIC/CapacityMeasurementLocalShutdownResultEvidenceV2/V1"
)
CASE69_SPEC_INTRINSIC_RULE = (
    "RULE/INTRINSIC/CapacityMeasurementLocalShutdownSpecV2/V1"
)

RUNTIME = (
    ROOT / "scripts/tests/validate_raw_v8_step2_external_schema_v2_rule_runtime_v49f.py"
)


def _load_runtime_module() -> ModuleType:
    name = "_riskyieldmm_v2_case69_differential_runtime"
    specification = importlib.util.spec_from_file_location(name, RUNTIME)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    try:
        specification.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


@pytest.fixture(scope="module")
def runtime() -> tuple[ModuleType, Any]:
    module = _load_runtime_module()
    return module, module.ExternalSchemaV2Runtime.load(ROOT)


def _spec() -> dict[str, Any]:
    inventory = json.loads(INVENTORY.read_bytes())
    return copy.deepcopy(
        inventory["fixture_records"]["operation_specs"]["LOCAL_SHUTDOWN"]
    )


def _reseal_spec(spec: dict[str, Any]) -> None:
    payload = {
        name: spec[name]
        for name in ("operation_kind", "spec_type", "spec")
    }
    envelope = {
        "canonicalization_version": spec["canonicalization_version"],
        "domain": spec["record_domain"],
        "payload": payload,
        "schema_version": spec["measurement_schema_version"],
    }
    spec["operation_spec_id"] = hashlib.sha256(_canonical_bytes(envelope)).hexdigest()


def _runtime_accepts(oracle: Any, result: dict[str, Any], spec: dict[str, Any]) -> None:
    oracle.validate_type("CapacityMeasurementOperationResultEvidence", result)
    oracle.validate_type("CapacityMeasurementOperationSpec", spec)
    oracle.evaluate_rule(
        CASE69_RESULT_INTRINSIC_RULE,
        {"self": result["result"]},
        require_true=True,
    )
    oracle.evaluate_rule(
        CASE69_SPEC_INTRINSIC_RULE,
        {"self": spec["spec"]},
        require_true=True,
    )
    oracle.evaluate_rule(
        CROSS_RULE_ID,
        {"result": result, "signed_spec": spec},
        require_true=True,
    )


def test_v2_case69_static_subset_positive_pair_matches_the_pinned_runtime(
    runtime: tuple[ModuleType, Any],
) -> None:
    _module, oracle = runtime
    _runtime_accepts(oracle, _case69_witness(), _spec())


def _cross_false(result: dict[str, Any], _spec_record: dict[str, Any]) -> None:
    result["result"]["final_terminal_socket_receive_call_count"] = 5
    _reseal_result(result)


def _result_intrinsic_false(
    result: dict[str, Any], _spec_record: dict[str, Any]
) -> None:
    result["result"]["ordered_terminal_ingress_read_attempt_event_ids"].append(
        "f" * 64
    )
    _reseal_result(result)


def _spec_intrinsic_false(
    _result: dict[str, Any], spec_record: dict[str, Any]
) -> None:
    spec_record["spec"]["maximum_terminal_ingress_plaintext_octets"] = 1
    _reseal_spec(spec_record)


@pytest.mark.parametrize(
    "mutation",
    [_cross_false, _result_intrinsic_false, _spec_intrinsic_false],
    ids=["signed-spec-false", "result-intrinsic-false", "spec-intrinsic-false"],
)
def test_v2_case69_static_subset_rejection_samples_match_the_pinned_runtime(
    runtime: tuple[ModuleType, Any],
    mutation: Callable[[dict[str, Any], dict[str, Any]], None],
) -> None:
    module, oracle = runtime
    result = _case69_witness()
    spec = _spec()
    mutation(result, spec)
    with pytest.raises(module.RuntimeFailure):
        _runtime_accepts(oracle, result, spec)


def test_v2_differential_fixture_types_are_the_frozen_local_branches() -> None:
    assert CASE69_BODY_TYPE == "CapacityMeasurementLocalShutdownResultEvidenceV2"
    assert CASE69_SPEC_BODY_TYPE == "CapacityMeasurementLocalShutdownSpecV2"

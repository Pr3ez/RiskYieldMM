"""Differential P1 checks for the static A4-P6-V1 subset interpreter.

The production verifier cannot dynamically load code under the frozen role
isolation contract.  These tests therefore use the separately pinned runtime
only as an out-of-process test oracle over the same independently built V1
fixtures and mutations.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from collections.abc import Callable
from types import ModuleType
from typing import Any

import pytest

from tests.test_raw_v8_step2_maximum_protocol_v2_independent_verifier_expansion_v1_v49f import (
    INVENTORY,
    ROOT,
    _case24_witness,
    _case54_witness,
    _overflow_case24,
    _reseal_owner,
)

CASE24_INTRINSIC_RULE = (
    "RULE/INTRINSIC/CapacityMeasurementLocalShutdownResultEvidenceV2/V1"
)
CASE54_INTRINSIC_RULE = (
    "RULE/INTRINSIC/CapacityMeasurementVocabularyDefinitionV1/V1"
)

RUNTIME = (
    ROOT / "scripts/tests/validate_raw_v8_step2_external_schema_v2_rule_runtime_v49f.py"
)


def _load_runtime_module() -> ModuleType:
    name = "_riskyieldmm_v1_differential_runtime"
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


def _owner_for(witness: dict[str, Any]) -> dict[str, Any]:
    inventory = json.loads(INVENTORY.read_bytes())
    owner = copy.deepcopy(
        inventory["fixture_records"]["operation_results"]["LOCAL_SHUTDOWN"]
    )
    owner["result"] = copy.deepcopy(witness)
    _reseal_owner(owner)
    return owner


def _runtime_accepts_case24(runtime: Any, witness: dict[str, Any]) -> None:
    runtime.validate_type("CapacityMeasurementOperationResultEvidence", _owner_for(witness))
    runtime.evaluate_rule(CASE24_INTRINSIC_RULE, {"self": witness}, require_true=True)


def _runtime_accepts_case54(runtime: Any, witness: dict[str, Any]) -> None:
    runtime.validate_type("CapacityMeasurementVocabularyDefinitionV1", witness)
    runtime.evaluate_rule(CASE54_INTRINSIC_RULE, {"self": witness}, require_true=True)


def test_v1_static_subset_positive_attainers_match_the_pinned_runtime(
    runtime: tuple[ModuleType, Any],
) -> None:
    _module, oracle = runtime
    _runtime_accepts_case24(oracle, _case24_witness())
    _runtime_accepts_case54(oracle, _case54_witness())


def _duplicate_case24(witness: dict[str, Any]) -> None:
    values = witness["ordered_terminal_ingress_read_attempt_event_ids"]
    values[1] = values[0]


def _bad_count_case24(witness: dict[str, Any]) -> None:
    witness["final_terminal_ingress_batch_count"] = 923


def _duplicate_case54(witness: dict[str, Any]) -> None:
    witness["members"][1] = witness["members"][0]


def _reorder_case54(witness: dict[str, Any]) -> None:
    witness["members"][0], witness["members"][1] = (
        witness["members"][1],
        witness["members"][0],
    )


def _overflow_case54(witness: dict[str, Any]) -> None:
    witness["members"][-1] += "z"


@pytest.mark.parametrize(
    ("case_position", "mutation"),
    [
        (24, _duplicate_case24),
        (24, _bad_count_case24),
        (24, _overflow_case24),
        (54, _duplicate_case54),
        (54, _reorder_case54),
        (54, _overflow_case54),
    ],
    ids=[
        "case24-duplicate",
        "case24-cross-field-count",
        "case24-owner-codec",
        "case54-duplicate",
        "case54-order",
        "case54-codec",
    ],
)
def test_v1_static_subset_rejection_samples_match_the_pinned_runtime(
    runtime: tuple[ModuleType, Any],
    case_position: int,
    mutation: Callable[[dict[str, Any]], None],
) -> None:
    module, oracle = runtime
    witness = _case24_witness() if case_position == 24 else _case54_witness()
    mutation(witness)
    with pytest.raises(module.RuntimeFailure):
        if case_position == 24:
            _runtime_accepts_case24(oracle, witness)
        else:
            _runtime_accepts_case54(oracle, witness)

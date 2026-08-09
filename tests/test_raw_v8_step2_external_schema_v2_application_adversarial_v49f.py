from __future__ import annotations

import copy
import dataclasses
import dis
import hashlib
import importlib.util
import json
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from types import CodeType, ModuleType
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

COUNTER_APPLICATION = "APPLY/COUNTER_SNAPSHOT_SCHEMA_V1"
COUNTER_CASE = "accept_exact_schema"
FIELD_APPLICATION = "APPLY/FIELD_OBSERVATION_FROZEN_REGISTRY_V1"
FIELD_CASE = "accept_field_zero"
MEMBERSHIP_APPLICATION = "APPLY/V2_ROOT_OBSERVATION_MEMBERSHIP_V1"


def _load_runtime_module() -> ModuleType:
    assert RUNTIME_PATH.is_file()
    assert RUNTIME_PATH.parent == ROOT / "scripts/tests"
    spec = importlib.util.spec_from_file_location(
        "raw_v8_rule_runtime_application_adversarial_v49f",
        RUNTIME_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


runtime_module = _load_runtime_module()


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


def _has_surrogate(value: str) -> bool:
    return any(0xD800 <= ord(character) <= 0xDFFF for character in value)


def _assert_exact_json(value: Any, *, path: tuple[str | int, ...] = ()) -> None:
    if value is None or type(value) is bool:
        return
    if type(value) is int:
        assert -SAFE_INTEGER_MAXIMUM <= value <= SAFE_INTEGER_MAXIMUM, path
        return
    if type(value) is str:
        assert not _has_surrogate(value), path
        return
    if type(value) is list:
        for ordinal, member in enumerate(value):
            _assert_exact_json(member, path=(*path, ordinal))
        return
    if type(value) is dict:
        for key, member in value.items():
            assert type(key) is str and not _has_surrogate(key), (*path, key)
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
    assert document["application_witness_sha256"] == WITNESS_SEMANTIC_SHA256
    payload = {
        key: value
        for key, value in document.items()
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
    return document


@pytest.fixture(scope="module")
def runtime() -> Any:
    return runtime_module.ExternalSchemaV2Runtime.load(ROOT)


@pytest.fixture(scope="module")
def witness() -> dict[str, Any]:
    return _load_witness()


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


def _resolve_simple_reference(
    runtime: Any,
    witness: dict[str, Any],
    reference: dict[str, Any],
) -> Any:
    assert type(reference) is dict and len(reference) == 1
    kind, path = next(iter(reference.items()))
    assert type(path) is list and path
    if kind == "fixture_path":
        fixture_name, *member_path = path
        value = witness["fixture_records"][fixture_name]["value"]
        return copy.deepcopy(_traverse(value, member_path))
    assert kind == "authority_path"
    return copy.deepcopy(_traverse(runtime.literal_authority, path))


def _simple_accepted_inputs(
    runtime: Any,
    witness: dict[str, Any],
    *,
    case_id: str,
) -> tuple[str, tuple[Any, ...]]:
    matches = [case for case in witness["ordered_cases"] if case["case_id"] == case_id]
    assert len(matches) == 1
    case = matches[0]
    assert case["expected_outcome"] == "ACCEPT"
    assert case["ordered_external_sequences"] == []
    assert case["ordered_transforms"] == []
    roots = tuple(
        runtime_module.ApplicationRecordInput(
            binding_name=item["binding_name"],
            declared=runtime_module.TypedValue(
                value=_resolve_simple_reference(
                    runtime,
                    witness,
                    item["value_reference"],
                ),
                type_name=item["declared_type_name"],
            ),
        )
        for item in case["ordered_root_inputs"]
    )
    return case["application_name"], roots


def _counter_inputs(
    runtime: Any,
    witness: dict[str, Any],
) -> tuple[Any, ...]:
    application_name, roots = _simple_accepted_inputs(
        runtime,
        witness,
        case_id=COUNTER_CASE,
    )
    assert application_name == COUNTER_APPLICATION
    return roots


def _assert_coordinate(
    runtime: Any,
    evidence: Any,
    *,
    application_name: str,
    accepted: bool,
    failure_class: str | None,
) -> None:
    plan = runtime.compiled_applications[application_name]
    assert type(evidence) is runtime_module.ApplicationEvaluationEvidence
    assert evidence.accepted is accepted
    coordinate = evidence.result_coordinate
    assert type(coordinate) is runtime_module.ApplicationFailureCoordinate
    assert coordinate.application_name == application_name
    assert coordinate.rule_application_id == plan.rule_application_id
    assert type(coordinate.rule_id) is str and coordinate.rule_id
    assert coordinate.failure_class == failure_class
    if accepted:
        assert coordinate.rule_id == plan.rule_id
        assert coordinate.iteration_ordinal is None
        assert coordinate.failure_class is None


def _assert_no_rule_execution(evidence: Any) -> None:
    assert evidence.intrinsic_rule_logical_invocations == 0
    assert evidence.intrinsic_rule_physical_executions == 0
    assert evidence.intrinsic_rule_cache_hits == 0
    assert evidence.charged_rule_evaluations == 0
    assert evidence.completed_rule_evaluations == 0
    assert evidence.ordered_rule_step_evidence == ()


class _TupleSubclass(tuple):
    pass


@pytest.mark.parametrize(
    "subclass_surface",
    [
        "root_tuple",
        "external_tuple",
        "record_envelope",
        "root_typed_value",
        "sequence_envelope",
        "sequence_record_tuple",
        "sequence_typed_value",
    ],
)
def test_public_application_api_rejects_tuple_and_dataclass_subclasses(
    runtime: Any,
    witness: dict[str, Any],
    subclass_surface: str,
) -> None:
    if subclass_surface in {
        "root_tuple",
        "external_tuple",
        "record_envelope",
        "root_typed_value",
    }:
        roots = _counter_inputs(runtime, witness)
        external_sequences: tuple[Any, ...] = ()
        if subclass_surface == "root_tuple":
            supplied_roots: tuple[Any, ...] = _TupleSubclass(roots)
        else:
            supplied_roots = roots
        if subclass_surface == "external_tuple":
            external_sequences = _TupleSubclass()
        elif subclass_surface == "record_envelope":

            class RecordInputSubclass(runtime_module.ApplicationRecordInput):
                pass

            original = roots[0]
            supplied_roots = (
                RecordInputSubclass(original.binding_name, original.declared),
                *roots[1:],
            )
        elif subclass_surface == "root_typed_value":

            class TypedValueSubclass(runtime_module.TypedValue):
                pass

            original = roots[0]
            supplied_roots = (
                runtime_module.ApplicationRecordInput(
                    original.binding_name,
                    TypedValueSubclass(
                        original.declared.value,
                        type_name=original.declared.type_name,
                    ),
                ),
                *roots[1:],
            )
        evidence = runtime.evaluate_application(
            COUNTER_APPLICATION,
            supplied_roots,
            external_sequences,
        )
        application_name = COUNTER_APPLICATION
    else:
        supplied_roots = (
            runtime_module.ApplicationRecordInput(
                "root",
                runtime_module.TypedValue(
                    value={},
                    type_name="TargetObservationRootV2",
                ),
            ),
        )
        record: Any = runtime_module.TypedValue(
            value={},
            type_name="TargetObservationV2",
        )
        records: tuple[Any, ...] = (record,)
        if subclass_surface == "sequence_record_tuple":
            records = _TupleSubclass(records)
        elif subclass_surface == "sequence_typed_value":

            class TypedValueSubclass(runtime_module.TypedValue):
                pass

            record = TypedValueSubclass(value={}, type_name="TargetObservationV2")
            records = (record,)
        sequence: Any = runtime_module.ApplicationSequenceInput(
            "observation",
            records,
        )
        if subclass_surface == "sequence_envelope":

            class SequenceInputSubclass(runtime_module.ApplicationSequenceInput):
                pass

            sequence = SequenceInputSubclass("observation", records)
        evidence = runtime.evaluate_application(
            MEMBERSHIP_APPLICATION,
            supplied_roots,
            (sequence,),
        )
        application_name = MEMBERSHIP_APPLICATION

    _assert_coordinate(
        runtime,
        evidence,
        application_name=application_name,
        accepted=False,
        failure_class="TYPE_OR_UNION_MISMATCH",
    )
    _assert_no_rule_execution(evidence)
    assert evidence.logical_record_graph_validations == 0
    assert evidence.snapshot_canonicalized_octets == 0


@pytest.mark.parametrize("subclass_kind", ["dict", "list", "str", "int"])
def test_nested_container_and_scalar_subclass_hooks_are_never_run(
    runtime: Any,
    witness: dict[str, Any],
    subclass_kind: str,
) -> None:
    calls: list[str] = []

    def trip(name: str) -> NoReturn:
        calls.append(name)
        raise AssertionError(f"hostile {subclass_kind} hook ran: {name}")

    if subclass_kind == "dict":

        class HostileDict(dict):
            def items(self) -> Any:
                trip("items")

            def __iter__(self) -> Any:
                trip("iter")

            def __getitem__(self, key: Any) -> Any:
                trip("getitem")

            def __len__(self) -> int:
                trip("len")

        application_name, roots = _simple_accepted_inputs(
            runtime,
            witness,
            case_id=FIELD_CASE,
        )
        assert application_name == FIELD_APPLICATION
        field = roots[0].declared.value
        field["value"] = HostileDict(field["value"])
    else:
        roots = _counter_inputs(runtime, witness)
        counter = roots[0].declared.value
        if subclass_kind == "list":

            class HostileList(list):
                def __iter__(self) -> Any:
                    trip("iter")

                def __getitem__(self, key: Any) -> Any:
                    trip("getitem")

                def __len__(self) -> int:
                    trip("len")

            counter["values"] = HostileList(counter["values"])
        elif subclass_kind == "str":

            class HostileStr(str):
                def __str__(self) -> str:
                    trip("str")

                def __iter__(self) -> Any:
                    trip("iter")

                def __len__(self) -> int:
                    trip("len")

                def encode(self, *args: Any, **kwargs: Any) -> bytes:
                    trip("encode")

            counter["availability_bitmap"] = HostileStr(counter["availability_bitmap"])
        else:

            class HostileInt(int):
                def __int__(self) -> int:
                    trip("int")

                def __index__(self) -> int:
                    trip("index")

                def __lt__(self, other: Any) -> bool:
                    trip("lt")

                def __le__(self, other: Any) -> bool:
                    trip("le")

            counter["values"][0] = HostileInt(counter["values"][0])
        application_name = COUNTER_APPLICATION

    evidence = runtime.evaluate_application(application_name, roots)
    _assert_coordinate(
        runtime,
        evidence,
        application_name=application_name,
        accepted=False,
        failure_class="MALFORMED_OPERAND",
    )
    _assert_no_rule_execution(evidence)
    assert evidence.logical_record_graph_validations == 0
    assert calls == []


@pytest.mark.parametrize(
    "invalid_kind",
    [
        "unsafe_integer",
        "surrogate_value",
        "surrogate_key",
        "tuple",
        "set",
        "nontext_key",
        "cycle",
    ],
)
def test_snapshot_rejects_every_non_exact_ijson_graph_form(
    runtime: Any,
    witness: dict[str, Any],
    invalid_kind: str,
) -> None:
    roots = _counter_inputs(runtime, witness)
    counter = roots[0].declared.value
    if invalid_kind == "unsafe_integer":
        counter["values"][0] = SAFE_INTEGER_MAXIMUM + 1
    elif invalid_kind == "surrogate_value":
        counter["availability_bitmap"] = "\ud800"
    elif invalid_kind == "surrogate_key":
        counter["\ud800"] = None
    elif invalid_kind == "tuple":
        counter["values"] = tuple(counter["values"])
    elif invalid_kind == "set":
        counter["values"] = {0}
    elif invalid_kind == "nontext_key":
        counter[1] = None
    else:
        counter["cycle"] = counter

    evidence = runtime.evaluate_application(COUNTER_APPLICATION, roots)
    _assert_coordinate(
        runtime,
        evidence,
        application_name=COUNTER_APPLICATION,
        accepted=False,
        failure_class="MALFORMED_OPERAND",
    )
    _assert_no_rule_execution(evidence)
    assert evidence.logical_record_graph_validations == 0
    assert evidence.physical_record_graph_validations == 0


def _nested_copy_code(runtime: Any) -> CodeType:
    method_code = runtime._snapshot_application_record.__func__.__code__
    matches = [
        constant
        for constant in method_code.co_consts
        if isinstance(constant, CodeType) and constant.co_name == "copy_value"
    ]
    assert len(matches) == 1
    return matches[0]


def _dict_items_loop_line(copy_code: CodeType) -> int:
    matches = [
        instruction.positions.lineno
        for instruction in dis.get_instructions(copy_code)
        if instruction.opname in {"LOAD_ATTR", "LOAD_METHOD"}
        and instruction.argval == "items"
    ]
    assert len(matches) == 1 and matches[0] is not None
    return matches[0]


def test_concurrent_exact_dict_mutation_is_a_controlled_application_failure(
    runtime: Any,
    witness: dict[str, Any],
) -> None:
    roots = _counter_inputs(runtime, witness)
    target = roots[0].declared.value
    copy_code = _nested_copy_code(runtime)
    loop_line = _dict_items_loop_line(copy_code)
    mutate = threading.Event()
    mutated = threading.Event()
    loop_visits = 0

    def worker() -> None:
        assert mutate.wait(timeout=5)
        target["concurrent_mutation"] = None
        mutated.set()

    thread = threading.Thread(target=worker, name="application-dict-mutator")
    thread.start()

    def trace(frame: Any, event: str, arg: Any) -> Callable[..., Any] | None:
        nonlocal loop_visits
        del arg
        if (
            event == "line"
            and frame.f_code is copy_code
            and frame.f_locals.get("current") is target
            and frame.f_lineno == loop_line
        ):
            loop_visits += 1
            if loop_visits == 2:
                mutate.set()
                assert mutated.wait(timeout=5)
        return trace

    previous_trace = sys.gettrace()
    try:
        sys.settrace(trace)
        evidence = runtime.evaluate_application(COUNTER_APPLICATION, roots)
    finally:
        sys.settrace(previous_trace)
        mutate.set()
        thread.join(timeout=5)

    assert not thread.is_alive()
    assert loop_visits == 2
    assert mutated.is_set()
    _assert_coordinate(
        runtime,
        evidence,
        application_name=COUNTER_APPLICATION,
        accepted=False,
        failure_class="MALFORMED_OPERAND",
    )
    _assert_no_rule_execution(evidence)
    assert evidence.logical_record_graph_validations == 0


def test_every_root_is_snapshotted_before_any_root_is_schema_validated(
    runtime: Any,
    witness: dict[str, Any],
) -> None:
    roots = _counter_inputs(runtime, witness)
    first_root = roots[0].declared.value
    later_root = roots[1].declared.value
    first_root.pop("availability_bitmap")
    later_root["ordered_counter_field_ids"] = tuple(
        later_root["ordered_counter_field_ids"]
    )

    evidence = runtime.evaluate_application(COUNTER_APPLICATION, roots)
    _assert_coordinate(
        runtime,
        evidence,
        application_name=COUNTER_APPLICATION,
        accepted=False,
        failure_class="MALFORMED_OPERAND",
    )
    _assert_no_rule_execution(evidence)
    assert evidence.snapshot_canonicalized_octets == len(_canonical_bytes(first_root))
    assert evidence.logical_record_graph_validations == 0
    assert evidence.physical_record_graph_validations == 0
    assert evidence.validation_work_used == 0


def test_later_root_schema_failure_precedes_every_intrinsic_and_cross_rule(
    runtime: Any,
    witness: dict[str, Any],
) -> None:
    roots = _counter_inputs(runtime, witness)
    first_root = roots[0].declared.value
    later_root = roots[1].declared.value
    later_root.pop("counter_field_count")

    evidence = runtime.evaluate_application(COUNTER_APPLICATION, roots)
    _assert_coordinate(
        runtime,
        evidence,
        application_name=COUNTER_APPLICATION,
        accepted=False,
        failure_class="MALFORMED_OPERAND",
    )
    _assert_no_rule_execution(evidence)
    assert evidence.snapshot_canonicalized_octets == (
        len(_canonical_bytes(first_root)) + len(_canonical_bytes(later_root))
    )
    assert evidence.logical_record_graph_validations == 2
    assert evidence.physical_record_graph_validations == 2
    assert evidence.record_graph_validation_cache_hits == 0
    assert evidence.validation_work_used > 0


def _mutate_after_all_root_validations(
    runtime: Any,
    mutation: Callable[[], None],
) -> Callable[..., None]:
    original = runtime._validate_application_record_graph
    completed = 0

    def wrapped(
        type_name: str,
        snapshot: dict[str, Any],
        *,
        counters: Any,
        path: tuple[str | int, ...],
    ) -> None:
        nonlocal completed
        original(
            type_name,
            snapshot,
            counters=counters,
            path=path,
        )
        completed += 1
        if completed == 2:
            mutation()

    return wrapped


def test_mid_call_compiled_plan_substitution_escapes_as_fatal(
    witness: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = runtime_module.ExternalSchemaV2Runtime.load(ROOT)
    roots = _counter_inputs(runtime, witness)
    original_plan = runtime.compiled_applications[COUNTER_APPLICATION]

    def mutate() -> None:
        runtime.compiled_applications[COUNTER_APPLICATION] = dataclasses.replace(
            original_plan,
            maximum_rule_evaluations=original_plan.maximum_rule_evaluations + 1,
        )

    monkeypatch.setattr(
        runtime,
        "_validate_application_record_graph",
        _mutate_after_all_root_validations(runtime, mutate),
    )
    with pytest.raises(
        runtime_module.ArtifactFailure,
        match="application plan changed during execution",
    ):
        runtime.evaluate_application(COUNTER_APPLICATION, roots)


def test_mid_call_rule_substitution_escapes_as_fatal_not_as_a_coordinate(
    witness: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = runtime_module.ExternalSchemaV2Runtime.load(ROOT)
    roots = _counter_inputs(runtime, witness)
    rule_id = runtime.compiled_applications[COUNTER_APPLICATION].rule_id

    def mutate() -> None:
        first_node = runtime.rules[rule_id]["ordered_expression_nodes"][0]
        first_node["typed_member_path"] = ["authority_was_substituted"]

    monkeypatch.setattr(
        runtime,
        "_validate_application_record_graph",
        _mutate_after_all_root_validations(runtime, mutate),
    )
    with pytest.raises(runtime_module.ArtifactFailure):
        runtime.evaluate_application(COUNTER_APPLICATION, roots)


@pytest.mark.parametrize(
    ("failure_type", "expected_failure_class"),
    [
        ("generic", None),
        ("candidate", "IMPOSSIBLE_BRANCH"),
    ],
)
def test_only_explicit_candidate_impossible_is_coordinate_mapped(
    witness: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    failure_type: str,
    expected_failure_class: str | None,
) -> None:
    runtime = runtime_module.ExternalSchemaV2Runtime.load(ROOT)
    roots = _counter_inputs(runtime, witness)
    failure_class = (
        runtime_module.ImpossibleState
        if failure_type == "generic"
        else runtime_module.CandidateImpossibleState
    )

    def fail_validation(*args: Any, **kwargs: Any) -> NoReturn:
        del args, kwargs
        raise failure_class("injected impossible distinction")

    monkeypatch.setattr(
        runtime,
        "_validate_application_record_graph",
        fail_validation,
    )
    if failure_type == "generic":
        with pytest.raises(
            runtime_module.ArtifactFailure,
            match="application failure has no frozen mapping",
        ):
            runtime.evaluate_application(COUNTER_APPLICATION, roots)
        return

    evidence = runtime.evaluate_application(COUNTER_APPLICATION, roots)
    _assert_coordinate(
        runtime,
        evidence,
        application_name=COUNTER_APPLICATION,
        accepted=False,
        failure_class=expected_failure_class,
    )
    _assert_no_rule_execution(evidence)


def test_intrinsic_cache_records_only_accepted_physical_executions(
    runtime: Any,
    witness: dict[str, Any],
) -> None:
    value = _counter_inputs(runtime, witness)[0].declared.value
    context = runtime_module._ApplicationExecutionContext(
        counters=runtime_module._ApplicationCounters(),
        rule_counters=runtime_module._RuleCounters(),
        intrinsic_accept_cache=set(),
        ordered_rule_steps=[],
    )
    outcomes = iter((False, False, True))
    physical_calls: list[str] = []

    def execute_prevalidated(
        rule_id: str,
        bindings: dict[str, Any],
        intrinsic_owner_type_name: str | None,
    ) -> bool:
        assert intrinsic_owner_type_name == "OperationCounterSnapshotV1"
        assert list(bindings) == ["self"] and bindings["self"] is value
        physical_calls.append(rule_id)
        return next(outcomes)

    for expected_physical in (1, 2):
        with pytest.raises(runtime_module._ApplicationCandidateFailure):
            runtime._walk_application_type_intrinsics(
                "OperationCounterSnapshotV1",
                value,
                owner=None,
                context=context,
                execute_prevalidated=execute_prevalidated,
                path=("cache_probe",),
            )
        assert context.counters.intrinsic_rule_cache_hits == 0
        assert context.counters.intrinsic_rule_physical_executions == expected_physical
        assert context.intrinsic_accept_cache == set()

    runtime._walk_application_type_intrinsics(
        "OperationCounterSnapshotV1",
        value,
        owner=None,
        context=context,
        execute_prevalidated=execute_prevalidated,
        path=("cache_probe",),
    )
    assert len(context.intrinsic_accept_cache) == 1
    runtime._walk_application_type_intrinsics(
        "OperationCounterSnapshotV1",
        value,
        owner=None,
        context=context,
        execute_prevalidated=execute_prevalidated,
        path=("cache_probe",),
    )
    assert len(physical_calls) == 3
    assert context.counters.intrinsic_rule_logical_invocations == 4
    assert context.counters.intrinsic_rule_physical_executions == 3
    assert context.counters.intrinsic_rule_cache_hits == 1
    assert (
        context.counters.intrinsic_rule_logical_invocations
        == context.counters.intrinsic_rule_physical_executions
        + context.counters.intrinsic_rule_cache_hits
    )


def test_accepted_public_evidence_has_exact_coordinate_and_cache_accounting(
    runtime: Any,
    witness: dict[str, Any],
) -> None:
    application_name, roots = _simple_accepted_inputs(
        runtime,
        witness,
        case_id=FIELD_CASE,
    )
    assert application_name == FIELD_APPLICATION
    evidence = runtime.evaluate_application(application_name, roots)

    _assert_coordinate(
        runtime,
        evidence,
        application_name=application_name,
        accepted=True,
        failure_class=None,
    )
    assert (
        evidence.intrinsic_rule_logical_invocations,
        evidence.intrinsic_rule_physical_executions,
        evidence.intrinsic_rule_cache_hits,
    ) == (486, 287, 199)
    assert (
        evidence.intrinsic_rule_logical_invocations
        == evidence.intrinsic_rule_physical_executions
        + evidence.intrinsic_rule_cache_hits
    )
    assert evidence.charged_rule_evaluations == 1
    assert evidence.completed_rule_evaluations == 1
    assert len(evidence.ordered_rule_step_evidence) == 1

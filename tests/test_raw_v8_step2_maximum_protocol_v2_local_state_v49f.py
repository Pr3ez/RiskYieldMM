"""Independent checks for the V2 case-475 LOCAL_SHUTDOWN controller.

This test intentionally does not import the seed generator.  It interprets the
closed local opcodes from the emitted catalog and rebuilds all twelve semantic
states, all eleven transitions, their identities, and the defensible non-byte
resource counts.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = (
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.json"
)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _catalog() -> dict[str, Any]:
    return json.loads(CATALOG_PATH.read_bytes())


def _identity(catalog: dict[str, Any], role: str) -> dict[str, Any]:
    matches = [
        row
        for row in catalog["ordered_identity_domain_records"]
        if row["identity_name"] == role
    ]
    assert len(matches) == 1
    return matches[0]


def _semantic_id(catalog: dict[str, Any], role: str, payload: dict[str, Any]) -> str:
    identity = _identity(catalog, role)
    assert list(payload) == identity["ordered_payload_member_names"]
    preimage = _canonical_bytes(
        {
            "canonicalization_version": catalog["canonicalization_version"],
            "domain": identity["domain_literal"],
            "payload": payload,
            "schema_version": catalog["measurement_schema_version"],
        }
    )
    return _sha256(preimage)


def _payload(
    catalog: dict[str, Any], role: str, record: dict[str, Any]
) -> dict[str, Any]:
    identity = _identity(catalog, role)
    return {name: record[name] for name in identity["ordered_payload_member_names"]}


def _batch_octets(local: dict[str, Any], batch_limit: int) -> int:
    program = local["batch_unsaturated_program"]
    assert set(program) == {
        "opcode",
        "constant_octets",
        "linear_variable",
        "linear_coefficient",
        "decimal_width_coefficient",
        "valid_minimum",
        "valid_maximum",
    }
    assert program["opcode"] == "PIECEWISE_AFFINE_DECIMAL_WIDTH_V1"
    assert program["valid_minimum"] <= batch_limit <= program["valid_maximum"]
    return (
        program["constant_octets"]
        + program["linear_coefficient"] * batch_limit
        + program["decimal_width_coefficient"] * len(str(batch_limit))
    )


def _eval_u128(expression: dict[str, Any], parameters: dict[str, int]) -> int:
    opcode = expression["opcode"]
    if opcode == "CONST_U128":
        assert set(expression) == {"opcode", "value"}
        value = expression["value"]
    elif opcode == "PARAM_U128":
        assert set(expression) == {"opcode", "parameter_name"}
        value = parameters[expression["parameter_name"]]
    elif opcode in {"CHECKED_ADD", "CHECKED_MUL"}:
        assert set(expression) == {"opcode", "ordered_operands"}
        operands = [
            _eval_u128(item, parameters) for item in expression["ordered_operands"]
        ]
        value = 0 if opcode == "CHECKED_ADD" else 1
        for operand in operands:
            value = value + operand if opcode == "CHECKED_ADD" else value * operand
            assert value < 1 << 128
    else:  # pragma: no cover - closed opcode rejection
        raise AssertionError(f"unknown UInt128 opcode: {opcode}")
    assert type(value) is int and 0 <= value < 1 << 128
    return value


def _evaluate_candidate(
    local: dict[str, Any], record: dict[str, Any], program: dict[str, Any]
) -> tuple[str, int, int, tuple[int, str, int] | None]:
    common = {
        "program_version",
        "opcode",
        "baseline_value",
        "strict_limit_octets",
    }
    assert program["program_version"].endswith(
        "local_shutdown_candidate_evaluation_program.v1"
    )
    assert program["baseline_value"] == record["baseline_value"]
    assert program["strict_limit_octets"] == local["masked_outer_codec_octet_limit"]
    opcode = program["opcode"]
    if opcode == "EMPTY_NONDECREASING_INTERVAL_V1":
        assert set(program) == common | {
            "non_decreasing_upper",
            "decisive_attainable_maximum_octets",
        }
        value = program["non_decreasing_upper"]
        octets = program["decisive_attainable_maximum_octets"]
        assert value == record["one_field_non_decreasing_upper"]
        assert value <= record["baseline_value"]
        assert octets == record["one_field_endpoint_or_cap_maximum_octets"]
        assert octets < program["strict_limit_octets"]
        return "EMPTY_NONDECREASING_MUTATION_INTERVAL", value, octets, None
    if opcode == "MONOTONE_ENDPOINT_BELOW_STRICT_LIMIT_V1":
        assert set(program) == common | {
            "endpoint_mutated_value",
            "endpoint_attainable_maximum_octets",
        }
        value = program["endpoint_mutated_value"]
        octets = program["endpoint_attainable_maximum_octets"]
        assert value == record["one_field_non_decreasing_upper"]
        assert value > record["baseline_value"]
        assert octets == record["one_field_endpoint_or_cap_maximum_octets"]
        assert octets < program["strict_limit_octets"]
        return "ENDPOINT_BELOW_STRICT_OUTER_CODEC_LIMIT", value, octets, None
    assert opcode == "FIRST_MONOTONE_STRICT_LIMIT_VIOLATION_V1"
    assert set(program) == common | {
        "length_program_locator",
        "predecessor_mutated_value",
        "predecessor_attainable_maximum_octets",
        "candidate_mutated_value",
        "candidate_attainable_maximum_octets",
    }
    assert program["length_program_locator"] == "/batch_unsaturated_program"
    predecessor = program["predecessor_mutated_value"]
    candidate = program["candidate_mutated_value"]
    assert candidate == predecessor + 1
    predecessor_octets = _batch_octets(local, predecessor)
    candidate_octets = _batch_octets(local, candidate)
    assert predecessor_octets == program["predecessor_attainable_maximum_octets"]
    assert candidate_octets == program["candidate_attainable_maximum_octets"]
    assert predecessor_octets < program["strict_limit_octets"] <= candidate_octets
    assert (
        record["baseline_value"] < candidate <= record["one_field_non_decreasing_upper"]
    )
    # The independent scan proves there is no skipped smaller integer, including
    # decimal-width boundaries in the declared unsaturated region.
    first = next(
        value
        for value in range(
            local["batch_unsaturated_program"]["valid_minimum"], candidate + 1
        )
        if _batch_octets(local, value) >= program["strict_limit_octets"]
    )
    assert first == candidate
    objective = (candidate - record["baseline_value"], record["member_name"], candidate)
    return "FIRST_STRICT_OUTER_CODEC_VIOLATION", candidate, candidate_octets, objective


def test_local_controller_rebuilds_all_states_transitions_and_identities() -> None:
    catalog = _catalog()
    recurrence = catalog["recurrence_catalog"]
    local = recurrence["local_shutdown_analytic_catalog"]
    signatures = recurrence["ordered_state_signature_records"]
    signature = next(
        row
        for row in signatures
        if row["state_signature_id"] == local["state_signature_id"]
    )
    components = signature["ordered_component_records"]
    assert len(components) == 8
    assert [row["component_position"] for row in components] == list(range(1, 9))
    assert [row["component_kind"] for row in components] == local[
        "controller_instruction_set"
    ]["ordered_state_component_kinds"]
    assert all(
        row["value_source_kind"] == "DERIVED_LOCAL_SWEEP_STATE" for row in components
    )

    states = local["ordered_controller_state_records"]
    transitions = local["ordered_controller_transition_records"]
    limits = local["ordered_mutable_limit_records"]
    assert len(states) == local["fixed_controller_state_count"] == 12
    assert len(transitions) == local["fixed_controller_transition_count"] == 11
    assert len(limits) == 11
    assert local["initial_controller_state_position"] == 1
    assert local["terminal_controller_state_position"] == 12

    state_by_id: dict[str, dict[str, Any]] = {}
    for position, state in enumerate(states, 1):
        assert state["controller_state_position"] == position
        assert len(state["ordered_state_components"]) == 8
        state_payload = _payload(catalog, "LOCAL_SHUTDOWN_CONTROLLER_STATE", state)
        expected_id = _semantic_id(
            catalog, "LOCAL_SHUTDOWN_CONTROLLER_STATE", state_payload
        )
        assert state["controller_state_id"] == expected_id
        assert expected_id not in state_by_id
        state_by_id[expected_id] = state

    expected_components: list[Any] = [
        0,
        "NOT_EVALUATED",
        None,
        None,
        None,
        None,
        None,
        None,
    ]
    assert states[0]["state_kind"] == "INITIAL"
    assert states[0]["ordered_state_components"] == expected_components
    best: tuple[int, str, int] | None = None
    best_position: int | None = None
    best_octets: int | None = None
    for position, (record, transition) in enumerate(zip(limits, transitions), 1):
        assert record["lexical_position"] == position
        assert transition["controller_transition_position"] == position
        assert transition["input_mutable_limit_lexical_position"] == position
        assert (
            transition["source_controller_state_id"]
            == states[position - 1]["controller_state_id"]
        )
        assert (
            transition["target_controller_state_id"]
            == states[position]["controller_state_id"]
        )
        assert transition["source_controller_state_id"] in state_by_id
        assert transition["target_controller_state_id"] in state_by_id
        program = transition["transition_program"]
        assert set(program) == {
            "program_version",
            "opcode",
            "candidate_evaluation_program",
            "objective_member_order",
            "best_update_opcode",
        }
        assert program["opcode"] == "EVALUATE_ONE_FIELD_AND_FOLD_OBJECTIVE_V1"
        outcome, value, octets, objective = _evaluate_candidate(
            local, record, program["candidate_evaluation_program"]
        )
        assert transition["candidate_outcome"] == outcome
        if objective is not None and (best is None or objective < best):
            expected_update = (
                "SET_FIRST_ELIGIBLE_BEST_V1"
                if best is None
                else "REPLACE_WITH_LEXICOGRAPHICALLY_SMALLER_BEST_V1"
            )
            best = objective
            best_position = position
            best_octets = octets
        elif objective is not None:
            expected_update = "KEEP_LEXICOGRAPHICALLY_SMALLER_BEST_V1"
        else:
            expected_update = "KEEP_NO_ELIGIBLE_BEST_V1"
        assert program["best_update_opcode"] == expected_update
        expected_objective = (
            None
            if objective is None
            else {
                "changed_limit_field_count": 1,
                "sum_absolute_integer_deltas": objective[0],
                "changed_member_names_in_lexical_order": [objective[1]],
                "resulting_changed_values_in_that_same_order": [objective[2]],
            }
        )
        assert transition["candidate_objective"] == expected_objective
        expected_components = [
            position,
            outcome,
            value,
            octets,
            best_position,
            None if best is None else best[2],
            None if best is None else best[0],
            best_octets,
        ]
        assert transition["expected_target_state_components"] == expected_components
        assert states[position]["ordered_state_components"] == expected_components
        transition_payload = _payload(
            catalog, "LOCAL_SHUTDOWN_CONTROLLER_TRANSITION", transition
        )
        assert transition["controller_transition_id"] == _semantic_id(
            catalog, "LOCAL_SHUTDOWN_CONTROLLER_TRANSITION", transition_payload
        )

    assert states[-1]["state_kind"] == "TERMINAL"
    assert best == (1_947, "maximum_terminal_ingress_batches", 1_948)
    assert best_position == 2
    assert best_octets == 524_380
    assert local["winning_member_name"] == best[1]
    assert local["winning_mutated_value"] == best[2]
    assert local["winning_absolute_delta"] == best[0]
    assert local["winner_attainable_maximum_octets"] == best_octets


def test_local_kernel_catalog_binding_and_non_byte_metrics_are_closed() -> None:
    catalog = _catalog()
    recurrence = catalog["recurrence_catalog"]
    local = recurrence["local_shutdown_analytic_catalog"]
    local_payload = _payload(catalog, "LOCAL_SHUTDOWN_ANALYTIC_CATALOG", local)
    assert local["local_shutdown_analytic_catalog_id"] == _semantic_id(
        catalog, "LOCAL_SHUTDOWN_ANALYTIC_CATALOG", local_payload
    )
    kernel = next(
        row
        for row in recurrence["ordered_derivation_kernel_records"]
        if row["derivation_kind"] == "LOCAL_SHUTDOWN_ANALYTIC_LENGTH_SWEEP"
    )
    kernel_payload = {
        name: value for name, value in kernel.items() if name != "kernel_record_sha256"
    }
    assert kernel["kernel_record_sha256"] == _sha256(_canonical_bytes(kernel_payload))
    assert kernel["state_signature_id"] == local["state_signature_id"]
    assert kernel["kernel_record_sha256"] == local["derivation_kernel_record_sha256"]
    assert kernel["transfer_program"]["opcode"] == "CELL_LOCAL_SHUTDOWN_SWEEP_V2"
    assert kernel["meter_program"]["transition_attempt_count_expression"] == {
        "opcode": "CONST_U128",
        "value": len(local["ordered_controller_transition_records"]),
    }
    assert kernel["meter_program"]["batch_application_count_expression"] == {
        "opcode": "CONST_U128",
        "value": 0,
    }

    plan = catalog["logical_plan_recipe_catalog"]["ordered_logical_count_plan_records"][
        -1
    ]
    assert plan["case_position"] == 475
    assert plan["logical_plan_template_id"] is None
    assert (
        plan["local_analytic_catalog_id"] == local["local_shutdown_analytic_catalog_id"]
    )
    assert plan["recurrence_catalog_id"] == recurrence["recurrence_catalog_id"]

    count_program = local["controller_metric_count_program"]
    assert count_program["runtime_byte_metric_seed_value_claimed"] is False
    assert count_program["ordered_runtime_byte_metric_positions"] == [
        8,
        9,
        10,
        11,
        17,
        18,
    ]
    states = local["ordered_controller_state_records"]
    transitions = local["ordered_controller_transition_records"]
    exact: dict[int, int] = {}
    for record in count_program["ordered_exact_non_byte_metric_records"]:
        opcode = record["value_opcode"]
        if opcode == "CONTROLLER_TRANSITION_COUNT":
            value = len(transitions)
        elif opcode == "CONTROLLER_STATE_COUNT":
            value = len(states)
        elif opcode == "CONST_U128":
            assert len(record["ordered_authority_values"]) == 1
            value = record["ordered_authority_values"][0]
        elif opcode in {
            "ORDERED_INTRINSIC_RULE_ID_COUNT",
            "ORDERED_CROSS_RULE_ID_COUNT",
            "ORDERED_APPLICATION_ID_COUNT",
        }:
            value = len(record["ordered_authority_values"])
            assert len(set(record["ordered_authority_values"])) == value
        else:  # pragma: no cover - closed opcode rejection
            raise AssertionError(f"unknown local metric opcode: {opcode}")
        assert value == record["expected_value"]
        exact[record["metric_position"]] = value
    assert exact == {
        1: 1,
        2: 11,
        3: 12,
        4: 11,
        5: 11,
        6: 0,
        7: 12,
        12: 2,
        13: 1,
        14: 1,
        15: 1,
        16: 11,
    }
    # No provisional byte-count vector is trusted: positions 8-11 and 17-18
    # remain explicitly assigned to final-ID-bound runtime canonical objects.
    assert set(exact).isdisjoint(count_program["ordered_runtime_byte_metric_positions"])


def test_local_catalog_uses_only_closed_structured_programs() -> None:
    local = _catalog()["recurrence_catalog"]["local_shutdown_analytic_catalog"]
    assert "candidate_enumeration_rule" not in local
    assert "unique_sha256_item_construction" not in local
    assert isinstance(local["candidate_enumeration_program"], dict)
    assert isinstance(local["unique_sha256_item_construction_program"], dict)
    assert isinstance(
        local["batch_saturation_proof"]["unique_item_construction_program"], dict
    )
    assert isinstance(
        local["saturated_attainer_program"]["required_sha256_item_program"], dict
    )
    assert isinstance(
        local["saturated_attainer_program"]["result_evidence_id_program"], dict
    )


def test_local_non_batch_endpoints_reconstruct_from_pinned_fixture_bytes() -> None:
    catalog = _catalog()
    local = catalog["recurrence_catalog"]["local_shutdown_analytic_catalog"]
    inventory = json.loads(
        (ROOT / "tests/raw_v8_step2_inventory_v4_v49f.json").read_bytes()
    )
    fixture = inventory["fixture_records"]["operation_results"]["LOCAL_SHUTDOWN"]
    baseline_spec = inventory["fixture_records"]["operation_specs"]["LOCAL_SHUTDOWN"][
        "spec"
    ]
    counter_map = {
        "maximum_terminal_ingress_batches": "final_terminal_ingress_batch_count",
        "maximum_terminal_ingress_ciphertext_octets": "final_terminal_ingress_ciphertext_octets",
        "maximum_terminal_ingress_plaintext_octets": "final_terminal_ingress_plaintext_octets",
        "maximum_terminal_socket_receive_calls": "final_terminal_socket_receive_call_count",
        "maximum_terminal_tls_records": "final_terminal_tls_record_count",
        "maximum_terminal_tls_unwrap_iterations": "final_terminal_tls_unwrap_iteration_count",
        "maximum_terminal_zero_progress_iterations": "final_terminal_zero_progress_iteration_count",
        "maximum_terminal_ingress_parser_units": "final_terminal_ingress_parser_unit_count",
        "maximum_terminal_ingress_automatic_outputs": "final_terminal_ingress_automatic_output_count",
        "maximum_websocket_send_attempts": "final_websocket_send_attempt_count",
        "maximum_tls_control_send_attempts": "final_tls_control_send_attempt_count",
    }
    batch_arrays = (
        "ordered_terminal_ingress_read_attempt_event_ids",
        "ordered_terminal_ingress_read_result_event_ids",
        "ordered_terminal_raw_ingress_commit_ids",
        "ordered_terminal_raw_ingress_actor_event_ids",
    )
    for record in local["ordered_mutable_limit_records"]:
        if record["member_name"] == "maximum_terminal_ingress_batches":
            continue
        candidate = copy.deepcopy(fixture)
        body = candidate["result"]
        one_sha = ["0" * 64]
        for member_name in batch_arrays:
            body[member_name] = one_sha.copy()
        parser_count = (
            record["one_field_non_decreasing_upper"]
            if record["member_name"] == "maximum_terminal_ingress_parser_units"
            else baseline_spec["maximum_terminal_ingress_parser_units"]
        )
        body["ordered_terminal_parser_transition_event_ids"] = [
            f"{ordinal:064x}" for ordinal in range(parser_count)
        ]
        body["local_shutdown_deadline_evidence_event_id"] = "e" * 64
        body["shutdown_trace_step_count"] = 9_007_199_254_740_991
        for spec_member, result_member in counter_map.items():
            body[result_member] = baseline_spec[spec_member]
        body[counter_map[record["member_name"]]] = record[
            "one_field_non_decreasing_upper"
        ]
        assert (
            len(_canonical_bytes(candidate))
            == record["one_field_endpoint_or_cap_maximum_octets"]
        )

    saturation = local["batch_saturation_proof"]
    components = saturation["attainment_component_octets"]
    independently_summed_body = (
        components["fixed_non_array_non_integer_octets"]
        + components["paired_array_linear_coefficient"]
        * components["paired_array_cardinality_sum"]
        + components["parser_and_array_constant_octets"]
        + components["integer_lexeme_octets"]
    )
    assert independently_summed_body == local["nested_body_codec_octet_limit"]
    assert independently_summed_body == components["total_body_octets"]
    assert (
        independently_summed_body + local["wrapper_overhead_octets"]
        == saturation["attaining_wrapper_octets"]
        == next(
            record["one_field_endpoint_or_cap_maximum_octets"]
            for record in local["ordered_mutable_limit_records"]
            if record["member_name"] == "maximum_terminal_ingress_batches"
        )
    )


def test_local_intrinsic_relations_are_closed_asts_and_bound_each_upper() -> None:
    catalog = _catalog()
    local = catalog["recurrence_catalog"]["local_shutdown_analytic_catalog"]
    inventory = json.loads(
        (ROOT / "tests/raw_v8_step2_inventory_v4_v49f.json").read_bytes()
    )
    baseline = dict(
        inventory["fixture_records"]["operation_specs"]["LOCAL_SHUTDOWN"]["spec"]
    )
    authority_literals = inventory["operation_contracts"][
        "local_shutdown_intrinsic_limit_relations"
    ]
    records = local["ordered_intrinsic_affine_relation_records"]
    assert [record["relation_position"] for record in records] == list(range(1, 6))
    assert [
        record["authority_relation_literal"] for record in records
    ] == authority_literals
    for record in records:
        program = record["relation_program"]
        assert set(program) == {
            "program_version",
            "opcode",
            "left_expression",
            "right_expression",
        }
        assert program["opcode"] == "CHECK_LE_U128_V1"
        assert _eval_u128(program["left_expression"], baseline) <= _eval_u128(
            program["right_expression"], baseline
        )

    for limit in local["ordered_mutable_limit_records"]:
        candidate = dict(baseline)
        candidate[limit["member_name"]] = limit["one_field_non_decreasing_upper"]
        for relation in records:
            program = relation["relation_program"]
            assert _eval_u128(program["left_expression"], candidate) <= _eval_u128(
                program["right_expression"], candidate
            )


def test_case_475_executes_signed_spec_application_without_relaxation() -> None:
    catalog = _catalog()
    plan = catalog["logical_plan_recipe_catalog"]["ordered_logical_count_plan_records"][
        474
    ]
    scope = plan["scope_summary"]
    assert plan["case_position"] == 475
    assert plan["upper_bound_mode"] == "EXACT_LEGAL_DOMAIN"
    assert plan["ordered_safe_relaxation_rule_ids"] == []
    local = catalog["recurrence_catalog"]["local_shutdown_analytic_catalog"]
    assert scope["schedule_authority_kind"] == "LOCAL_SHUTDOWN_ANALYTIC_CATALOG"
    assert scope["schedule_authority_id"] == local["local_shutdown_analytic_catalog_id"]
    assert scope["application_schedule_operation_position"] is None
    assert scope["p2_cross_application_deletion_policy_id"] is None
    application_count = next(
        row
        for row in local["controller_metric_count_program"][
            "ordered_exact_non_byte_metric_records"
        ]
        if row["metric_position"] == 14
    )
    assert application_count["value_opcode"] == "ORDERED_APPLICATION_ID_COUNT"
    assert application_count["expected_value"] == 1
    assert len(application_count["ordered_authority_values"]) == 1

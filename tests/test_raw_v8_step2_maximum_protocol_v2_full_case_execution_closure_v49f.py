"""Fail-closed checks for executable full-case event construction.

The three bounded hand oracles prove the event meter on representative
microfixtures.  F1 additionally needs one deterministic construction for every
subject and event cardinality in each of the 475 complete cases.  Schema-valid
subjects are not sufficient: byte metrics and the logical event-stream digest
depend on their exact canonical bytes.

This test is intentionally independent of the seed generator.  It remains a
fail-first correction gate until the serialized seed publishes the missing
full-case execution authority.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = (
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.json"
)

EVENT_KINDS = (
    "CASE_OPEN",
    "LOGICAL_DESCRIPTOR_VISIT",
    "CACHE_INSERT",
    "TRANSITION_ATTEMPT",
    "BATCH_APPLICATION",
    "RESULT_CELL_EMIT",
    "STEP_COMMITMENT_EMIT",
    "FINAL_RESULT_EMIT",
    "INTRINSIC_RULE_EVALUATION",
    "CROSS_RULE_EVALUATION",
    "APPLICATION_EVALUATION",
    "HASH_PREIMAGE",
    "RETENTION_OBSERVATION",
    "DERIVATION_DEPTH_OBSERVATION",
    "ITERATION_DEPTH_OBSERVATION",
    "EVENT_STREAM_CLOSE",
)
U128_MAX = (1 << 128) - 1


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _catalog() -> dict[str, Any]:
    value = json.loads(CATALOG_PATH.read_bytes())
    assert type(value) is dict
    return value


def _tagged_subject(
    recurrence: dict[str, Any], schema_name: str, values: dict[str, Any]
) -> dict[str, Any]:
    schema = recurrence[schema_name]
    members = schema["ordered_member_names"]
    version_member = members[0]
    complete = {version_member: schema[version_member], **values}
    assert set(complete) <= set(members)
    return {name: complete.get(name) for name in members}


def _fingerprint(value: Any) -> tuple[int, str]:
    raw = _canonical_bytes(value)
    return len(raw), hashlib.sha256(raw).hexdigest()


def _validate_event_metadata_program(grammar: dict[str, Any]) -> None:
    metadata = grammar["event_metadata_program"]
    assert set(metadata) == {
        "binding_rule",
        "logical_derivation_step_position_source_enum",
        "observed_value_source_enum",
        "ordered_program_metadata_records",
        "program_version",
        "subject_ordinal_source_enum",
        "unknown_or_extra_member_policy",
    }
    assert metadata["program_version"] == (
        "riskyieldmm.raw_v8_step2_external_schema_v2.event_metadata_program.v1"
    )
    assert metadata["unknown_or_extra_member_policy"] == "REJECT"
    assert metadata["binding_rule"] == (
        "ZIP_PROGRAM_POSITION_THEN_EMISSION_POSITION_AND_MATERIALIZE_METADATA_"
        "ON_EMISSION_RECORD_BEFORE_TOKENIZATION_V1"
    )
    assert metadata["logical_derivation_step_position_source_enum"] == [
        "NULL",
        "CURRENT_ORDINARY_TEMPLATE_STEP_POSITION",
    ]
    assert metadata["observed_value_source_enum"] == [
        "NULL",
        "SUBJECT_OBSERVED_VALUE",
    ]
    assert metadata["subject_ordinal_source_enum"] == [
        "NULL",
        "EMISSION_SUBJECT_COLLECTION_ORDINAL",
        "EVENT_KIND_ORDINAL",
        "DERIVATION_UNIT_ORDINAL",
    ]

    expected_roles = {
        "CASE_OPEN": ["CASE_OPEN_RECORD"],
        "BOUND_PLAN_HASH_PREIMAGE": ["BOUND_PLAN_IDENTITY_ENVELOPE"],
        "ORDINARY_POSTORDER_STEPS": [
            "LOGICAL_STEP_REFERENCE",
            "ORDINARY_TRANSITION",
            "HOMOGENEOUS_RUN_BATCH",
            "ORDINARY_RESULT_CELL",
            "ORDINARY_CACHE_KEY",
            "LIVE_CHILDREN_PLUS_PROSPECTIVE_PARENT",
            "RETAINED_RESULT_CELL_PREIMAGE",
            "ORDINARY_STEP_COMMITMENT",
            "STEP_COMMITMENT_PREIMAGE",
            "AFTER_PARENT_COMMITMENT_HASH_AND_RELEASE",
        ],
        "LOCAL_CONTROLLER": [
            "LOCAL_CONTROLLER_REFERENCE",
            "LOCAL_CONTROLLER_TRANSITION",
            "LOCAL_CONTROLLER_INTRINSIC_RELATIONS",
            "LOCAL_CONTROLLER_STATE_RESULT_CELL",
            "LOCAL_CONTROLLER_STATE_CACHE_KEY",
            "LIVE_CHILDREN_PLUS_PROSPECTIVE_PARENT",
            "RETAINED_RESULT_CELL_PREIMAGE",
            "LOCAL_CONTROLLER_COMMITMENT",
            "STEP_COMMITMENT_PREIMAGE",
            "AFTER_PARENT_COMMITMENT_HASH_AND_RELEASE",
        ],
        "EXACT_ATTAINER_VALIDATION": ["EXACT_RETAINED_ATTAINER_INTRINSIC_RULES"],
        "SCOPE_APPLICATIONS": [
            "EXACT_SCOPE_APPLICATION_INVOCATIONS",
            "EXACT_SCOPE_CROSS_RULE_ROOTS",
        ],
        "DEPTH_AND_RETENTION": [
            "DERIVATION_DAG_DEPTH",
            "ITERATION_DEPTH",
            "ROOT_COMMITMENT_DIGEST_THROUGH_FINAL_RESULT_HASH",
        ],
        "FINAL_RESULT": [
            "COMPLETE_LOGICAL_CASE_DERIVATION_RESULT",
            "FINAL_RESULT_IDENTITY_PREIMAGE",
        ],
        "STREAM_FINALIZATION": [
            "EVENT_STREAM_PREIMAGE_DESCRIPTOR",
            "EVENT_STREAM_PREIMAGE",
        ],
    }
    programs = grammar["ordered_case_program_records"]
    rows = metadata["ordered_program_metadata_records"]
    assert len(rows) == len(programs) == len(expected_roles) == 9
    observed_kinds = {
        "RETENTION_OBSERVATION",
        "DERIVATION_DEPTH_OBSERVATION",
        "ITERATION_DEPTH_OBSERVATION",
    }
    for position, (program, row) in enumerate(zip(programs, rows, strict=True), 1):
        assert set(row) == {
            "logical_derivation_step_position_source",
            "observed_value_sources",
            "ordered_subject_role_literals",
            "program_name",
            "program_position",
            "subject_ordinal_sources",
        }
        assert row["program_position"] == program["program_position"] == position
        assert row["program_name"] == program["program_name"]
        assert (
            row["ordered_subject_role_literals"]
            == expected_roles[program["program_name"]]
        )
        emissions = program["ordered_event_emission_records"]
        assert len(row["observed_value_sources"]) == len(emissions)
        assert len(row["subject_ordinal_sources"]) == len(emissions)
        assert row["logical_derivation_step_position_source"] == (
            "CURRENT_ORDINARY_TEMPLATE_STEP_POSITION"
            if program["program_name"] == "ORDINARY_POSTORDER_STEPS"
            else "NULL"
        )
        for emission, observed_source, ordinal_source in zip(
            emissions,
            row["observed_value_sources"],
            row["subject_ordinal_sources"],
            strict=True,
        ):
            assert (observed_source == "SUBJECT_OBSERVED_VALUE") == (
                emission["event_kind"] in observed_kinds
            )
            assert ordinal_source in metadata["subject_ordinal_source_enum"]


def _validate_full_case_execution_surface(catalog: dict[str, Any]) -> None:
    recurrence = catalog["recurrence_catalog"]
    grammar = catalog["logical_event_catalog"]["case_level_event_grammar"]
    _validate_event_metadata_program(grammar)
    execution = grammar["full_case_execution_program"]
    assert execution["derivation_unit_context_program"] == {
        "local_unit": {
            "derivation_kind": "LOCAL_SHUTDOWN_ANALYTIC_CONTROLLER",
            "effective_canonical_octet_ceiling_source": "AMBIENT_CEILING",
            "logical_derivation_step_id_source": "PLAN.local_analytic_catalog_id",
            "logical_derivation_step_position": None,
            "ordered_result_cell_source": (
                "LOCAL_CONTROLLER_STATE_CELLS_IN_POSITION_ORDER"
            ),
            "owner_profile_position": None,
            "state_signature_source": "LOCAL_CATALOG.state_signature_id",
            "subject_variant": "LOCAL_CONTROLLER",
        },
        "ordinary_unit": {
            "derivation_kind_source": "STEP.derivation_kind",
            "effective_canonical_octet_ceiling_source": "AMBIENT_CEILING",
            "logical_derivation_step_id_source": "STEP.logical_derivation_step_id",
            "logical_derivation_step_position_source": "STEP.template_step_position",
            "ordered_result_cell_source": "SINGLE_EVALUATED_STEP_RESULT_CELL",
            "owner_profile_position_source": (
                "MATCH_PROFILE_PROGRAM_ID_TO_PROFILE_POSITION_OR_NULL"
            ),
            "state_signature_source": "STEP.state_signature_id",
            "subject_variant": "ORDINARY_STEP",
        },
        "program_version": (
            "riskyieldmm.raw_v8_step2_external_schema_v2."
            "derivation_unit_context_program.v1"
        ),
        "unknown_or_extra_member_policy": "REJECT",
    }
    kernels = recurrence["ordered_derivation_kernel_records"]
    expansions = execution["ordered_kernel_transition_expansion_program_records"]
    assert len(expansions) == len(kernels) == 18
    for position, (kernel, expansion) in enumerate(
        zip(kernels, expansions, strict=True), 1
    ):
        assert expansion["kernel_position"] == position
        assert expansion["derivation_kind"] == kernel["derivation_kind"]
        assert expansion["kernel_record_sha256"] == kernel["kernel_record_sha256"]
        base = (
            "/recurrence_catalog/ordered_derivation_kernel_records/"
            f"{position - 1}/meter_program"
        )
        assert expansion["physical_transition_count_expression_pointer"] == (
            f"{base}/transition_attempt_count_expression"
        )
        assert expansion["logical_unbatched_count_expression_pointer"] == (
            f"{base}/logical_unbatched_transition_equivalent_count_expression"
        )
        assert expansion["logical_count_distribution_rule"] == (
            "EUCLIDEAN_QUOTIENT_REMAINDER_FIRST_R_TOKENS_PLUS_ONE_V1"
        )
        assert expansion["input_symbol_rule"] == (
            "ORDERED_OBJECT_DERIVATION_KIND_THEN_PHYSICAL_TRANSITION_ORDINAL_V1"
        )

    constructors = execution["ordered_subject_constructor_records"]
    subjects = grammar["ordered_subject_schema_records"]
    assert len(constructors) == len(subjects) == 16
    for position, (subject, constructor) in enumerate(
        zip(subjects, constructors, strict=True), 1
    ):
        assert constructor["constructor_position"] == position
        assert constructor["event_kind"] == subject["event_kind"]
        sources = constructor["ordered_value_source_records"]
        assert [row["value_source_position"] for row in sources] == list(
            range(1, len(sources) + 1)
        )
        assert len({row["member_name"] for row in sources}) == len(sources)

    source_maps = {
        row["event_kind"]: {
            source["member_name"]: source["value_source"]
            for source in row["ordered_value_source_records"]
        }
        for row in constructors
    }
    assert source_maps["LOGICAL_DESCRIPTOR_VISIT"] == {
        "logical_step_reference_version": (
            "CONST:riskyieldmm.raw_v8_step2_external_schema_v2."
            "logical_step_reference.v1"
        ),
        "logical_count_plan_id": "PLAN.logical_count_plan_id",
        "subject_variant": "UNIT.subject_variant",
        "logical_derivation_step_position": "UNIT.logical_derivation_step_position",
        "logical_derivation_step_id": "UNIT.logical_derivation_step_id",
        "derivation_kind": "UNIT.derivation_kind",
    }
    assert source_maps["CACHE_INSERT"]["owner_profile_position"] == (
        "UNIT.owner_profile_position"
    )
    assert source_maps["STEP_COMMITMENT_EMIT"]["initial_controller_state_id"] == (
        "ORDINARY:null|LOCAL:INITIAL_CONTROLLER_STATE.controller_state_id"
    )
    assert source_maps["STEP_COMMITMENT_EMIT"]["terminal_controller_state_id"] == (
        "ORDINARY:null|LOCAL:TERMINAL_CONTROLLER_STATE.controller_state_id"
    )
    assert all(
        "LOCAL_CATALOG.initial_controller_state_id" not in value
        and "LOCAL_CATALOG.terminal_controller_state_id" not in value
        for source_map in source_maps.values()
        for value in source_map.values()
    )

    export_name = execution["subject_collection_export_name"]
    assert export_name == "CASE_PROGRAM_EXACT_SUBJECT_COLLECTION"
    for program in grammar["ordered_case_program_records"]:
        for emission in program["ordered_event_emission_records"]:
            assert emission["subject_collection_locator"] == {"source": export_name}
            assert emission["cardinality_expression"] == {
                "opcode": "SOURCE_LIST_COUNT",
                "source_locator": {
                    "event_kind": emission["event_kind"],
                    "program_name": program["program_name"],
                    "source": export_name,
                },
            }
    assert (
        execution["local_controller_state_cell_program"]["certified_upper_bound_rule"]
        == "INITIAL_BASELINE_INTERMEDIATE_COMPONENT_3_TERMINAL_COMPONENT_7_V1"
    )
    assert (
        execution["local_controller_state_cell_program"][
            "initial_controller_state_source"
        ]
        == "CONTROLLER_STATE_AT_LOCAL_CATALOG_INITIAL_POSITION"
    )
    assert (
        execution["local_controller_state_cell_program"][
            "terminal_controller_state_source"
        ]
        == "CONTROLLER_STATE_AT_LOCAL_CATALOG_TERMINAL_POSITION"
    )
    assert execution["local_transition_expansion_program"] == {
        "candidate_state_component_source": (
            "CONTROLLER_TRANSITION.expected_target_state_components"
        ),
        "candidate_upper_bound_source": (
            "TARGET_STATE_CELL.certified_upper_bound_octets"
        ),
        "input_symbol_source": (
            "CONTROLLER_TRANSITION.input_mutable_limit_lexical_position"
        ),
        "logical_unbatched_count_per_token": 1,
        "physical_transition_ordinal_source": (
            "CONTROLLER_TRANSITION.controller_transition_position"
        ),
        "physical_transition_count_source": (
            "LOCAL_CATALOG.fixed_controller_transition_count"
        ),
        "source_state_selector": "CONTROLLER_STATE_AT_TRANSITION_POSITION",
        "source_state_component_source": "SOURCE_STATE.ordered_state_components",
        "target_state_cell_selector": "RESULT_CELL_AT_TRANSITION_POSITION_PLUS_ONE",
        "transition_order": (
            "controller_transition_position_ASCENDING_CONTIGUOUS_ONE_BASED"
        ),
    }
    assert execution["stream_finalization_program"]["excluded_from_preimage"] == [
        "EVENT_STREAM_CLOSE",
        "FINAL_EVENT_STREAM_HASH_PREIMAGE_EVENT",
    ]


def test_schema_valid_transition_tokens_do_not_determine_one_stream_identity() -> None:
    """Exhibit the ambiguity that blocks two independent full-case counters."""

    catalog = _catalog()
    recurrence = catalog["recurrence_catalog"]
    plan = catalog["logical_plan_recipe_catalog"]["ordered_logical_count_plan_records"][
        0
    ]
    schema = recurrence["transition_token_schema"]
    member_names = schema["ordered_member_names"]
    version_member = member_names[0]

    common = {
        version_member: schema[version_member],
        "subject_variant": "ORDINARY_STEP",
        "logical_count_plan_id": plan["logical_count_plan_id"],
        "transition_ordinal": 1,
        "transition_kind": "ORDINARY_KERNEL_TRANSITION",
        "source_state_components": [],
        "candidate_state_components": [],
        "candidate_certified_upper_bound_octets": 5,
        "logical_derivation_step_position": 1,
        "local_controller_transition_position": None,
        "local_controller_transition_id": None,
        "source_controller_state_id": None,
        "target_controller_state_id": None,
    }
    token_a = {name: common.get(name) for name in member_names}
    token_b = {**token_a, "input_symbol": "INPUT_A"}
    token_a["input_symbol"] = "INPUT_B"

    raw_a = _canonical_bytes(token_a)
    raw_b = _canonical_bytes(token_b)
    assert len(raw_a) == len(raw_b)
    assert hashlib.sha256(raw_a).digest() != hashlib.sha256(raw_b).digest()

    # Both values satisfy every currently serialized ordinary-variant member
    # and null rule.  Neither the recurrence kernel nor the case program tells
    # an F1 implementation which equal-length input symbol is authoritative.
    ordinary = schema["ordered_variant_records"][0]
    for candidate in (token_a, token_b):
        assert set(candidate) == set(member_names)
        assert all(
            candidate[name] is not None
            for name in ordinary["ordered_required_member_names"]
        )
        assert all(
            candidate[name] is None for name in ordinary["ordered_null_member_names"]
        )


def test_every_kernel_has_one_closed_transition_expansion_program() -> None:
    catalog = _catalog()
    kernels = catalog["recurrence_catalog"]["ordered_derivation_kernel_records"]
    assert len(kernels) == 18
    grammar = catalog["logical_event_catalog"]["case_level_event_grammar"]
    execution = grammar["full_case_execution_program"]
    programs = execution["ordered_kernel_transition_expansion_program_records"]
    assert [row["kernel_position"] for row in programs] == list(range(1, 19))
    for kernel, program in zip(kernels, programs, strict=True):
        assert set(program) == {
            "kernel_position",
            "derivation_kind",
            "kernel_record_sha256",
            "program_version",
            "physical_transition_count_expression_pointer",
            "logical_unbatched_count_expression_pointer",
            "token_ordinal_rule",
            "logical_count_distribution_rule",
            "source_state_component_rule",
            "input_symbol_rule",
            "candidate_state_component_rule",
            "candidate_upper_bound_rule",
        }
        assert program["kernel_position"] == kernel["kernel_position"]
        assert program["derivation_kind"] == kernel["derivation_kind"]
        assert program["kernel_record_sha256"] == kernel["kernel_record_sha256"]
        base = (
            "/recurrence_catalog/ordered_derivation_kernel_records/"
            f"{kernel['kernel_position'] - 1}/meter_program"
        )
        assert program["physical_transition_count_expression_pointer"] == (
            f"{base}/transition_attempt_count_expression"
        )
        assert program["logical_unbatched_count_expression_pointer"] == (
            f"{base}/logical_unbatched_transition_equivalent_count_expression"
        )


def test_every_ordinary_transition_run_has_one_exact_positive_distribution() -> None:
    catalog = _catalog()
    execution = catalog["logical_event_catalog"]["case_level_event_grammar"][
        "full_case_execution_program"
    ]
    symbol_contract = execution["ordinary_transition_input_symbol_contract"]
    assert symbol_contract == {
        "ordered_member_names": [
            "derivation_kind",
            "physical_transition_ordinal",
        ],
        "unknown_or_extra_member_policy": "REJECT",
    }
    templates = catalog["logical_plan_recipe_catalog"]["ordered_logical_plan_templates"]
    checked_runs = 0
    for template in templates:
        for step in template["ordered_template_steps"]:
            physical = step["physical_transition_count"]
            logical = step["logical_unbatched_transition_equivalent_count"]
            assert type(physical) is int and 0 < physical <= U128_MAX
            assert type(logical) is int and physical <= logical <= U128_MAX
            quotient, remainder = divmod(logical, physical)
            distribution = [
                quotient + int(ordinal <= remainder)
                for ordinal in range(1, physical + 1)
            ]
            assert all(value > 0 for value in distribution)
            assert len(distribution) == physical
            assert sum(distribution) == logical

            symbols = [
                {
                    "derivation_kind": step["derivation_kind"],
                    "physical_transition_ordinal": ordinal,
                }
                for ordinal in range(1, physical + 1)
            ]
            assert all(
                list(symbol) == symbol_contract["ordered_member_names"]
                for symbol in symbols
            )
            assert len({_canonical_bytes(symbol) for symbol in symbols}) == physical
            checked_runs += 1
    assert checked_runs == 1_647


def test_local_state_cells_and_transitions_are_exactly_adjacent() -> None:
    catalog = _catalog()
    recurrence = catalog["recurrence_catalog"]
    execution = catalog["logical_event_catalog"]["case_level_event_grammar"][
        "full_case_execution_program"
    ]
    local = recurrence["local_shutdown_analytic_catalog"]
    states = local["ordered_controller_state_records"]
    transitions = local["ordered_controller_transition_records"]
    cell_program = execution["local_controller_state_cell_program"]
    transition_program = execution["local_transition_expansion_program"]

    assert len(states) == local["fixed_controller_state_count"] == 12
    assert len(transitions) == local["fixed_controller_transition_count"] == 11
    assert cell_program["certified_upper_bound_rule"] == (
        "INITIAL_BASELINE_INTERMEDIATE_COMPONENT_3_TERMINAL_COMPONENT_7_V1"
    )
    cell_uppers = []
    for position, state in enumerate(states, 1):
        components = state["ordered_state_components"]
        upper = (
            local["baseline_attainable_maximum_octets"]
            if position == 1
            else components[7]
            if position == len(states)
            else components[3]
        )
        assert type(upper) is int and 0 <= upper <= U128_MAX
        cell_uppers.append(upper)
    assert cell_uppers[-1] == local["winner_attainable_maximum_octets"]

    assert transition_program["candidate_upper_bound_source"] == (
        "TARGET_STATE_CELL.certified_upper_bound_octets"
    )
    for position, transition in enumerate(transitions, 1):
        source = states[position - 1]
        target = states[position]
        assert transition["controller_transition_position"] == position
        assert transition["source_controller_state_id"] == source["controller_state_id"]
        assert transition["target_controller_state_id"] == target["controller_state_id"]
        assert (
            transition["expected_target_state_components"]
            == target["ordered_state_components"]
        )
        assert cell_uppers[position] >= 0


def test_ordinary_reference_subject_bundle_has_fixed_canonical_bytes() -> None:
    """Pin one exact leaf cell, transition run, key, and commitment."""

    catalog = _catalog()
    recurrence = catalog["recurrence_catalog"]
    recipes = catalog["logical_plan_recipe_catalog"]
    plan = recipes["ordered_logical_count_plan_records"][0]
    template = next(
        row
        for row in recipes["ordered_logical_plan_templates"]
        if row["logical_plan_template_id"] == plan["logical_plan_template_id"]
    )
    step = template["ordered_template_steps"][0]
    assert step["derivation_kind"] == "EXACT_BOOLEAN"
    assert step["recurrence_parameters"] == {"boolean_literal": None}
    assert step["physical_transition_count"] == 2
    assert step["logical_unbatched_transition_equivalent_count"] == 2

    common = {
        "subject_variant": "ORDINARY_STEP",
        "logical_count_plan_id": plan["logical_count_plan_id"],
    }
    result_cell = _tagged_subject(
        recurrence,
        "result_cell_schema",
        {
            **common,
            "state_signature_id": step["state_signature_id"],
            "ordered_state_components": [],
            "cell_status": "MAY_BE_NONEMPTY",
            "certified_lower_bound_octets": 4,
            "certified_upper_bound_octets": 5,
            "logical_derivation_step_position": 1,
            "result_cell_ordinal": 1,
            "local_controller_state_position": None,
            "local_controller_state_id": None,
        },
    )
    cache_key = _tagged_subject(
        recurrence,
        "cache_key_schema",
        {
            **common,
            "effective_canonical_octet_ceiling": recurrence["arithmetic_policy"][
                "published_maximum"
            ],
            "state_signature_id": step["state_signature_id"],
            "ordered_state_components": [],
            "logical_derivation_step_position": 1,
            "derivation_kind": "EXACT_BOOLEAN",
            "occurrence_ordinal": 1,
            "array_ordinal": None,
            "owner_profile_position": None,
            "application_invocation_ordinal": None,
            "observation_ordinal": None,
            "local_controller_state_position": None,
            "local_controller_state_id": None,
        },
    )
    transitions = [
        _tagged_subject(
            recurrence,
            "transition_token_schema",
            {
                **common,
                "transition_ordinal": ordinal,
                "transition_kind": "ORDINARY_KERNEL_TRANSITION",
                "source_state_components": [],
                "input_symbol": {
                    "derivation_kind": "EXACT_BOOLEAN",
                    "physical_transition_ordinal": ordinal,
                },
                "candidate_state_components": [],
                "candidate_certified_upper_bound_octets": 5,
                "logical_derivation_step_position": 1,
                "local_controller_transition_position": None,
                "local_controller_transition_id": None,
                "source_controller_state_id": None,
                "target_controller_state_id": None,
            },
        )
        for ordinal in (1, 2)
    ]
    commitment = _tagged_subject(
        recurrence,
        "step_commitment_schema",
        {
            **common,
            "state_count": 1,
            "certified_upper_bound_octets": 5,
            "ordered_result_cell_sha256": [_fingerprint(result_cell)[1]],
            "logical_derivation_step_position": 1,
            "local_shutdown_analytic_catalog_id": None,
            "initial_controller_state_id": None,
            "terminal_controller_state_id": None,
        },
    )
    bundle = {
        "ordered_cache_keys": [cache_key],
        "ordered_transition_tokens": transitions,
        "ordered_result_cells": [result_cell],
        "step_commitment": commitment,
    }

    assert _fingerprint(cache_key) == (
        669,
        "a4cb26293060d65d030e905dafea7b65e8f74d338c5bbf7730dedbecdedb9b05",
    )
    assert [_fingerprint(row) for row in transitions] == [
        (
            674,
            "24d19f53a214fe9eeb0329d831c0df21dc85841b195e1d3eabdf25e4ce7d6508",
        ),
        (
            674,
            "9795d8aec8eee7fca805a2a906861cd842d259edef392dfa064bef77387f9f9d",
        ),
    ]
    assert _fingerprint(result_cell) == (
        569,
        "5abb165e989b9099b5e898b35cf78995fcec8e9719fa63fbb590c6e52ace17c9",
    )
    assert _fingerprint(commitment) == (
        525,
        "33fab0bf8898db5d8e9605239f8cdbc4e0a876d609f4095b02465e8c8907dab8",
    )
    assert _fingerprint(bundle) == (
        3_213,
        "8944d523e6671c3f7725d702cf8e675b4ab23b1131369faa7556fe21c1901a8d",
    )


def test_local_reference_subject_bundle_has_fixed_canonical_bytes() -> None:
    """Pin all 12 local cells/keys, 11 transitions, and one commitment."""

    catalog = _catalog()
    recurrence = catalog["recurrence_catalog"]
    local = recurrence["local_shutdown_analytic_catalog"]
    plan = catalog["logical_plan_recipe_catalog"]["ordered_logical_count_plan_records"][
        474
    ]
    states = local["ordered_controller_state_records"]
    transition_rows = local["ordered_controller_transition_records"]
    initial_position = local["initial_controller_state_position"]
    terminal_position = local["terminal_controller_state_position"]
    assert initial_position == 1
    assert terminal_position == len(states) == 12

    common = {
        "subject_variant": "LOCAL_CONTROLLER",
        "logical_count_plan_id": plan["logical_count_plan_id"],
    }
    result_cells = []
    cache_keys = []
    for position, state in enumerate(states, 1):
        upper = (
            local["baseline_attainable_maximum_octets"]
            if position == initial_position
            else state["ordered_state_components"][7]
            if position == terminal_position
            else state["ordered_state_components"][3]
        )
        result_cells.append(
            _tagged_subject(
                recurrence,
                "result_cell_schema",
                {
                    **common,
                    "state_signature_id": state["state_signature_id"],
                    "ordered_state_components": state["ordered_state_components"],
                    "cell_status": "MAY_BE_NONEMPTY",
                    "certified_lower_bound_octets": 0,
                    "certified_upper_bound_octets": upper,
                    "logical_derivation_step_position": None,
                    "result_cell_ordinal": None,
                    "local_controller_state_position": position,
                    "local_controller_state_id": state["controller_state_id"],
                },
            )
        )
        cache_keys.append(
            _tagged_subject(
                recurrence,
                "cache_key_schema",
                {
                    **common,
                    "effective_canonical_octet_ceiling": recurrence[
                        "arithmetic_policy"
                    ]["published_maximum"],
                    "state_signature_id": state["state_signature_id"],
                    "ordered_state_components": state["ordered_state_components"],
                    "logical_derivation_step_position": None,
                    "derivation_kind": None,
                    "occurrence_ordinal": None,
                    "array_ordinal": None,
                    "owner_profile_position": None,
                    "application_invocation_ordinal": None,
                    "observation_ordinal": None,
                    "local_controller_state_position": position,
                    "local_controller_state_id": state["controller_state_id"],
                },
            )
        )

    transitions = []
    for transition in transition_rows:
        ordinal = transition["controller_transition_position"]
        transitions.append(
            _tagged_subject(
                recurrence,
                "transition_token_schema",
                {
                    **common,
                    "transition_ordinal": ordinal,
                    "transition_kind": "LOCAL_CONTROLLER_TRANSITION",
                    "source_state_components": states[ordinal - 1][
                        "ordered_state_components"
                    ],
                    "input_symbol": transition["input_mutable_limit_lexical_position"],
                    "candidate_state_components": transition[
                        "expected_target_state_components"
                    ],
                    "candidate_certified_upper_bound_octets": result_cells[ordinal][
                        "certified_upper_bound_octets"
                    ],
                    "logical_derivation_step_position": None,
                    "local_controller_transition_position": ordinal,
                    "local_controller_transition_id": transition[
                        "controller_transition_id"
                    ],
                    "source_controller_state_id": transition[
                        "source_controller_state_id"
                    ],
                    "target_controller_state_id": transition[
                        "target_controller_state_id"
                    ],
                },
            )
        )

    commitment = _tagged_subject(
        recurrence,
        "step_commitment_schema",
        {
            **common,
            "state_count": len(result_cells),
            "certified_upper_bound_octets": max(
                row["certified_upper_bound_octets"] for row in result_cells
            ),
            "ordered_result_cell_sha256": [
                _fingerprint(row)[1] for row in result_cells
            ],
            "logical_derivation_step_position": None,
            "local_shutdown_analytic_catalog_id": plan["local_analytic_catalog_id"],
            "initial_controller_state_id": states[initial_position - 1][
                "controller_state_id"
            ],
            "terminal_controller_state_id": states[terminal_position - 1][
                "controller_state_id"
            ],
        },
    )
    bundle = {
        "ordered_cache_keys": cache_keys,
        "ordered_transition_tokens": transitions,
        "ordered_result_cells": result_cells,
        "step_commitment": commitment,
    }

    assert _fingerprint(cache_keys[0]) == (
        773,
        "492eef6f6ed8a4fbe85c5b5ddca9cb54c96e626810d8dc15160ed95d58779667",
    )
    assert _fingerprint(transitions[0]) == (
        916,
        "b7300a25950610e3294ef232105727367444616934f9cf5d1e1ad9f8c714a973",
    )
    assert _fingerprint(result_cells[0]) == (
        687,
        "75107ef4b44cc029fa99dbe8000a85f3966f93593cf59f65ff6b822abae1c05f",
    )
    assert _fingerprint(result_cells[-1]) == (
        715,
        "dcd95f44c38d4b18e19cb7fb842766ddb8a5cd43a14b2de51eb2b3d370691f11",
    )
    assert _fingerprint(commitment) == (
        1_460,
        "0f0135c6d1d2f201dcd8f679642565eef4f795c5840644ad8f078cf80c445d9a",
    )
    assert _fingerprint(bundle) == (
        30_205,
        "32c359df8922b8e929906387ce5c5a23f7d75c2cbe10c18e85eab5ac50d9e40b",
    )


def test_event_grammar_publishes_exact_full_case_subject_and_cardinality_program() -> (
    None
):
    catalog = _catalog()
    grammar = catalog["logical_event_catalog"]["case_level_event_grammar"]
    assert "full_case_execution_program" in grammar
    program = grammar["full_case_execution_program"]
    assert set(program) == {
        "program_version",
        "unknown_or_extra_member_policy",
        "ambient_ceiling_source",
        "ordinary_derivation_unit_order",
        "local_derivation_unit_order",
        "derivation_unit_context_program",
        "ordinary_cell_execution_program",
        "ordinary_transition_input_symbol_contract",
        "local_transition_expansion_program",
        "local_controller_state_cell_program",
        "ordered_kernel_transition_expansion_program_records",
        "ordered_subject_constructor_records",
        "ordinary_event_cardinality_program",
        "local_event_cardinality_program",
        "rule_application_event_program",
        "depth_observation_program",
        "retention_observation_program",
        "final_result_program",
        "stream_finalization_program",
        "subject_collection_export_name",
    }
    assert program["unknown_or_extra_member_policy"] == "REJECT"
    constructors = program["ordered_subject_constructor_records"]
    assert [row["constructor_position"] for row in constructors] == list(
        range(1, len(EVENT_KINDS) + 1)
    )
    assert [row["event_kind"] for row in constructors] == list(EVENT_KINDS)
    for row in constructors:
        assert set(row) == {
            "constructor_position",
            "event_kind",
            "constructor_opcode",
            "subject_member_order_source",
            "ordered_value_source_records",
        }
        assert row["ordered_value_source_records"]


def test_case_program_subject_collection_is_resolved_by_the_full_case_program() -> None:
    catalog = _catalog()
    grammar = catalog["logical_event_catalog"]["case_level_event_grammar"]
    execution = grammar["full_case_execution_program"]
    export_name = execution["subject_collection_export_name"]
    assert export_name == "CASE_PROGRAM_EXACT_SUBJECT_COLLECTION"
    programs = grammar["ordered_case_program_records"]
    for program in programs:
        for emission in program["ordered_event_emission_records"]:
            locator = emission["subject_collection_locator"]
            assert locator == {"source": export_name}, (
                program["program_name"],
                emission["event_kind"],
            )
            assert emission["cardinality_expression"] == {
                "opcode": "SOURCE_LIST_COUNT",
                "source_locator": {
                    "event_kind": emission["event_kind"],
                    "program_name": program["program_name"],
                    "source": export_name,
                },
            }


def test_full_case_execution_surface_is_closed() -> None:
    _validate_full_case_execution_surface(_catalog())


@pytest.mark.parametrize(
    "mutation",
    [
        "DROP_PROGRAM_ROW",
        "ALTER_PROGRAM_BINDING",
        "DROP_ROLE",
        "ALTER_LOCAL_CELL_ROLE",
        "ALTER_OBSERVED_VALUE_SOURCE",
        "ALTER_SUBJECT_ORDINAL_SOURCE",
        "ALTER_DERIVATION_STEP_SOURCE",
    ],
)
def test_event_metadata_program_rejects_hostile_mutations(mutation: str) -> None:
    catalog = copy.deepcopy(_catalog())
    grammar = catalog["logical_event_catalog"]["case_level_event_grammar"]
    metadata = grammar["event_metadata_program"]
    rows = metadata["ordered_program_metadata_records"]

    if mutation == "DROP_PROGRAM_ROW":
        rows.pop()
    elif mutation == "ALTER_PROGRAM_BINDING":
        rows[0]["program_name"] = "FUTURE_CASE_OPEN"
    elif mutation == "DROP_ROLE":
        rows[2]["ordered_subject_role_literals"].pop()
    elif mutation == "ALTER_LOCAL_CELL_ROLE":
        rows[3]["ordered_subject_role_literals"][3] = "LOCAL_TERMINAL_RESULT_CELL"
    elif mutation == "ALTER_OBSERVED_VALUE_SOURCE":
        rows[2]["observed_value_sources"][5] = "NULL"
    elif mutation == "ALTER_SUBJECT_ORDINAL_SOURCE":
        rows[2]["subject_ordinal_sources"][1] = "HOST_CHOSEN_ORDINAL"
    elif mutation == "ALTER_DERIVATION_STEP_SOURCE":
        rows[2]["logical_derivation_step_position_source"] = "NULL"
    else:  # pragma: no cover - parametrization is the closed mutation enum.
        raise AssertionError(mutation)

    with pytest.raises(AssertionError):
        _validate_event_metadata_program(grammar)


@pytest.mark.parametrize(
    "mutation",
    [
        "DROP_KERNEL_EXPANSION",
        "DUPLICATE_KERNEL_EXPANSION",
        "REORDER_KERNEL_EXPANSION",
        "ALTER_KERNEL_POINTER",
        "ALTER_TRANSITION_INPUT_RULE",
        "DROP_SUBJECT_CONSTRUCTOR",
        "DUPLICATE_SUBJECT_MEMBER",
        "PLACEHOLDER_EVENT_CARDINALITY",
        "DROP_DERIVATION_UNIT_CONTEXT",
        "ABSENT_LOCAL_ENDPOINT_SOURCE",
        "ALTER_LOCAL_TERMINAL_CELL_RULE",
        "INCLUDE_STREAM_CLOSE_IN_PREIMAGE",
    ],
)
def test_full_case_execution_surface_rejects_hostile_mutations(mutation: str) -> None:
    catalog = copy.deepcopy(_catalog())
    grammar = catalog["logical_event_catalog"]["case_level_event_grammar"]
    execution = grammar["full_case_execution_program"]
    expansions = execution["ordered_kernel_transition_expansion_program_records"]
    constructors = execution["ordered_subject_constructor_records"]

    if mutation == "DROP_KERNEL_EXPANSION":
        expansions.pop()
    elif mutation == "DUPLICATE_KERNEL_EXPANSION":
        expansions.append(copy.deepcopy(expansions[-1]))
    elif mutation == "REORDER_KERNEL_EXPANSION":
        expansions[0], expansions[1] = expansions[1], expansions[0]
    elif mutation == "ALTER_KERNEL_POINTER":
        expansions[0]["physical_transition_count_expression_pointer"] += "/future"
    elif mutation == "ALTER_TRANSITION_INPUT_RULE":
        expansions[0]["input_symbol_rule"] = "HOST_CHOSEN_INPUT_SYMBOL"
    elif mutation == "DROP_SUBJECT_CONSTRUCTOR":
        constructors.pop()
    elif mutation == "DUPLICATE_SUBJECT_MEMBER":
        constructors[0]["ordered_value_source_records"][1]["member_name"] = (
            constructors[0]["ordered_value_source_records"][0]["member_name"]
        )
    elif mutation == "PLACEHOLDER_EVENT_CARDINALITY":
        grammar["ordered_case_program_records"][2]["ordered_event_emission_records"][1][
            "cardinality_expression"
        ] = {"opcode": "CONST_U128", "value": 1}
    elif mutation == "DROP_DERIVATION_UNIT_CONTEXT":
        execution["derivation_unit_context_program"]["ordinary_unit"].pop(
            "derivation_kind_source"
        )
    elif mutation == "ABSENT_LOCAL_ENDPOINT_SOURCE":
        commitment = next(
            row for row in constructors if row["event_kind"] == "STEP_COMMITMENT_EMIT"
        )
        endpoint = next(
            row
            for row in commitment["ordered_value_source_records"]
            if row["member_name"] == "initial_controller_state_id"
        )
        endpoint["value_source"] = (
            "ORDINARY:null|LOCAL:LOCAL_CATALOG.initial_controller_state_id"
        )
    elif mutation == "ALTER_LOCAL_TERMINAL_CELL_RULE":
        execution["local_controller_state_cell_program"][
            "certified_upper_bound_rule"
        ] = "USE_COMPONENT_3_FOR_ALL_STATES"
    elif mutation == "INCLUDE_STREAM_CLOSE_IN_PREIMAGE":
        execution["stream_finalization_program"]["excluded_from_preimage"].pop(0)
    else:  # pragma: no cover - parametrization is the closed mutation enum.
        raise AssertionError(mutation)

    with pytest.raises(AssertionError):
        _validate_full_case_execution_surface(catalog)

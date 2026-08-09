from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = ROOT / "tests/raw_v8_step2_inventory_v4_v49f.json"
CATALOG_PATH = (
    ROOT / "scripts/tests/raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.json"
)


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    assert type(value) is dict
    return value


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


def _identity(catalog: dict[str, Any], name: str) -> dict[str, Any]:
    records = [
        row
        for row in catalog["ordered_identity_domain_records"]
        if row["identity_name"] == name
    ]
    assert len(records) == 1
    return records[0]


def _semantic_id(catalog: dict[str, Any], domain: str, payload: Any) -> str:
    return _sha256(
        _canonical_bytes(
            {
                "canonicalization_version": catalog["canonicalization_version"],
                "domain": domain,
                "payload": payload,
                "schema_version": catalog["measurement_schema_version"],
            }
        )
    )


def _unescape_pointer_token(token: str) -> str:
    output: list[str] = []
    position = 0
    while position < len(token):
        if token[position] != "~":
            output.append(token[position])
            position += 1
            continue
        assert position + 1 < len(token)
        escaped = token[position + 1]
        assert escaped in {"0", "1"}
        output.append("~" if escaped == "0" else "/")
        position += 2
    return "".join(output)


def _resolve_pointer(root: Any, pointer: str) -> Any:
    assert pointer.startswith("/") and pointer != "/"
    value = root
    for raw_token in pointer[1:].split("/"):
        token = _unescape_pointer_token(raw_token)
        if type(value) is list:
            assert token == "0" or (token.isdecimal() and not token.startswith("0"))
            value = value[int(token)]
        else:
            assert type(value) is dict and token in value
            value = value[token]
    return value


def _identity_member_name(value: Any, expected_id: str) -> str:
    assert type(value) is dict
    matches = [
        name
        for name, member_value in value.items()
        if name.endswith("_id") and member_value == expected_id
    ]
    assert len(matches) == 1
    return matches[0]


def _expected_scope_cases(profile: dict[str, Any]) -> list[dict[str, Any]]:
    if profile["profile_kind"] == "OUTER_RESULT_BOUNDARY_FIXTURE":
        return [
            {
                "scope_case_position": 1,
                "root_family_position": None,
                "mode_attempt_pair_position": None,
                "observation_role_position": None,
                "measured_sequence_ordinal": None,
            }
        ]

    records: list[dict[str, Any]] = []
    for family_position, family in enumerate(
        profile["ordered_admissible_root_families"], 1
    ):
        for pair_position, _pair in enumerate(
            family["ordered_instrumentation_mode_attempt_presence_pairs"], 1
        ):
            for role_position, role in enumerate(
                family["ordered_measured_observation_roles"], 1
            ):
                if role == "STARTUP_RECOVERY":
                    ordinal = 0
                elif role == "BEFORE_OPERATION":
                    ordinal = 0
                elif role == "STABLE_CHECKPOINT":
                    ordinal = profile["selector_position"]
                elif role == "AFTER_OPERATION":
                    ordinal = family["selector_length"] + 1
                else:
                    assert role == "OPERATION_AGGREGATE"
                    ordinal = family["selector_length"] + 2
                assert (
                    type(ordinal) is int and 0 <= ordinal < family["observation_count"]
                )
                records.append(
                    {
                        "scope_case_position": len(records) + 1,
                        "root_family_position": family_position,
                        "mode_attempt_pair_position": pair_position,
                        "observation_role_position": role_position,
                        "measured_sequence_ordinal": ordinal,
                    }
                )
    return records


def _expected_strategy(profile: dict[str, Any]) -> str:
    if profile["profile_position"] == 3:
        assert profile["profile_kind"] == "OUTER_RESULT_BOUNDARY_FIXTURE"
        assert profile["operation_kind"] == "LOCAL_SHUTDOWN"
        return "LOCAL_SHUTDOWN_BASELINE_ANALYTIC_EXACT_V1"
    return "STRUCTURAL_TEMPLATE_SUPERSET_WITH_EXACT_RETAINED_ATTAINMENT_V1"


def _expected_schedule_counts(profile: dict[str, Any]) -> tuple[int, int, int]:
    if profile["profile_kind"] == "OUTER_RESULT_BOUNDARY_FIXTURE":
        return (1, 1, 3)
    application_count = 0
    evaluation_count = 0
    expression_count = 0
    for family in profile["ordered_admissible_root_families"]:
        multiplicity = len(
            family["ordered_instrumentation_mode_attempt_presence_pairs"]
        ) * len(family["ordered_measured_observation_roles"])
        observations = family["observation_count"]
        selector = int(family["selector_present"])
        application_count += multiplicity * (2 * observations + 2 + selector)
        evaluation_count += multiplicity * (187 * observations + 1 + selector)
        expression_count += multiplicity * (1_872 * observations + 4 + 3 * selector)
    return application_count, evaluation_count, expression_count


def _instruction(
    position: int,
    application: dict[str, Any],
    ordinal_program: str,
    invocations: int,
    evaluations: int,
) -> dict[str, Any]:
    return {
        "instruction_position": position,
        "application_name": application["application_name"],
        "rule_application_id": application["rule_application_id"],
        "rule_id": application["rule_id"],
        "invocation_ordinal_program": ordinal_program,
        "application_invocation_count_per_scope_case": invocations,
        "cross_rule_evaluation_count_per_scope_case": evaluations,
    }


def _expected_schedule_segments(
    profile: dict[str, Any], applications: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    if profile["profile_kind"] == "OUTER_RESULT_BOUNDARY_FIXTURE":
        application = applications["APPLY/OPERATION_RESULT_SIGNED_SPEC_V1"]
        return [
            {
                "segment_position": 1,
                "root_family_position": None,
                "scope_case_multiplicity": 1,
                "observation_count": 0,
                "selector_present": False,
                "ordered_application_instruction_records": [
                    _instruction(
                        1,
                        application,
                        "SINGLE_ZERO_NULL_BOUND_V1",
                        1,
                        1,
                    )
                ],
                "application_invocation_count_per_scope_case": 1,
                "cross_rule_evaluation_count_per_scope_case": 1,
                "direct_cross_expression_node_count_per_scope_case": 3,
            }
        ]

    segments: list[dict[str, Any]] = []
    for family_position, family in enumerate(
        profile["ordered_admissible_root_families"], 1
    ):
        observations = family["observation_count"]
        selector = bool(family["selector_present"])
        specs: list[tuple[str, str, int, int]] = []
        if selector:
            specs.append(
                (
                    "APPLY/SELECTOR_MARKER_CONTRACT_V1",
                    "SINGLE_ZERO_NULL_BOUND_V1",
                    1,
                    1,
                )
            )
        specs.extend(
            [
                (
                    "APPLY/V2_OBSERVATION_AGGREGATE_REGISTRY_V1",
                    "ZERO_BASED_OBSERVATION_RANGE_V1",
                    observations,
                    observations,
                ),
                (
                    "APPLY/V2_OBSERVATION_FIELDS_REGISTRY_V1",
                    "ZERO_BASED_OBSERVATION_RANGE_V1",
                    observations,
                    185 * observations,
                ),
                (
                    "APPLY/V2_ROOT_OBSERVATION_MEMBERSHIP_V1",
                    "SINGLE_ZERO_NULL_BOUND_V1",
                    1,
                    observations,
                ),
                (
                    "APPLY/V2_ROOT_SELECTOR_LIFECYCLE_V1",
                    "SINGLE_ZERO_NULL_BOUND_V1",
                    1,
                    1,
                ),
            ]
        )
        assert [row[0] for row in specs] == sorted(row[0] for row in specs)
        multiplicity = len(
            family["ordered_instrumentation_mode_attempt_presence_pairs"]
        ) * len(family["ordered_measured_observation_roles"])
        selector_integer = int(selector)
        segments.append(
            {
                "segment_position": family_position,
                "root_family_position": family_position,
                "scope_case_multiplicity": multiplicity,
                "observation_count": observations,
                "selector_present": selector,
                "ordered_application_instruction_records": [
                    _instruction(position, applications[name], ordinal, calls, evals)
                    for position, (name, ordinal, calls, evals) in enumerate(specs, 1)
                ],
                "application_invocation_count_per_scope_case": (
                    2 * observations + 2 + selector_integer
                ),
                "cross_rule_evaluation_count_per_scope_case": (
                    187 * observations + 1 + selector_integer
                ),
                "direct_cross_expression_node_count_per_scope_case": (
                    1_872 * observations + 4 + 3 * selector_integer
                ),
            }
        )
    return segments


def _summary_record(
    position: int,
    application: dict[str, Any],
    scope: str,
    invocations: int,
    evaluations: int,
) -> dict[str, Any]:
    return {
        "schedule_position": position,
        "application_name": application["application_name"],
        "rule_application_id": application["rule_application_id"],
        "rule_id": application["rule_id"],
        "schedule_scope": scope,
        "application_invocation_count": invocations,
        "cross_rule_evaluation_count": evaluations,
    }


def _expected_summary_schedules(
    profile: dict[str, Any], applications: dict[str, dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[list[dict[str, Any]]]]:
    if profile["profile_kind"] == "OUTER_RESULT_BOUNDARY_FIXTURE":
        return (
            [
                _summary_record(
                    1,
                    applications["APPLY/OPERATION_RESULT_SIGNED_SPEC_V1"],
                    "ONE_OUTER_RESULT_FIXTURE",
                    1,
                    1,
                )
            ],
            [],
        )
    totals = {
        name: [0, 0]
        for name in (
            "APPLY/SELECTOR_MARKER_CONTRACT_V1",
            "APPLY/V2_OBSERVATION_AGGREGATE_REGISTRY_V1",
            "APPLY/V2_OBSERVATION_FIELDS_REGISTRY_V1",
            "APPLY/V2_ROOT_OBSERVATION_MEMBERSHIP_V1",
            "APPLY/V2_ROOT_SELECTOR_LIFECYCLE_V1",
        )
    }
    family_records: list[list[dict[str, Any]]] = []
    for family in profile["ordered_admissible_root_families"]:
        observations = family["observation_count"]
        selector = int(family["selector_present"])
        multiplicity = len(
            family["ordered_instrumentation_mode_attempt_presence_pairs"]
        ) * len(family["ordered_measured_observation_roles"])
        specs = (
            ("APPLY/SELECTOR_MARKER_CONTRACT_V1", selector, selector),
            (
                "APPLY/V2_OBSERVATION_AGGREGATE_REGISTRY_V1",
                observations,
                observations,
            ),
            (
                "APPLY/V2_OBSERVATION_FIELDS_REGISTRY_V1",
                observations,
                185 * observations,
            ),
            ("APPLY/V2_ROOT_OBSERVATION_MEMBERSHIP_V1", 1, observations),
            ("APPLY/V2_ROOT_SELECTOR_LIFECYCLE_V1", 1, 1),
        )
        active = [row for row in specs if row[1] > 0]
        family_records.append(
            [
                _summary_record(
                    position,
                    applications[name],
                    "PER_INTERNAL_SCOPE_CASE",
                    invocations,
                    evaluations,
                )
                for position, (name, invocations, evaluations) in enumerate(active, 1)
            ]
        )
        for name, invocations, evaluations in specs:
            totals[name][0] += multiplicity * invocations
            totals[name][1] += multiplicity * evaluations
    active_totals = [row for row in totals.items() if row[1][0] > 0]
    aggregate = [
        _summary_record(
            position,
            applications[name],
            "PROFILE_TOTAL",
            counts[0],
            counts[1],
        )
        for position, (name, counts) in enumerate(active_totals, 1)
    ]
    return aggregate, family_records


def _expected_context_relaxation_records(
    schedules: list[dict[str, Any]], named_relaxation_id: str
) -> list[dict[str, Any]]:
    return [
        {
            "application_position": row["schedule_position"],
            "safe_relaxation_rule_id": named_relaxation_id,
            "predicate_kind": "CROSS_RULE_APPLICATION",
            "rule_application_id": row["rule_application_id"],
            "rule_id": row["rule_id"],
            "application_invocation_count": row["application_invocation_count"],
            "cross_rule_evaluation_count": row["cross_rule_evaluation_count"],
        }
        for row in schedules
    ]


def test_all_408_profiles_have_exact_reconstructible_conditioning_programs() -> None:
    inventory = _load(INVENTORY_PATH)
    catalog = _load(CATALOG_PATH)
    profiles = inventory["operation_contracts"][
        "maximum_constraint_scope_profile_catalog"
    ]
    recipe = catalog["logical_plan_recipe_catalog"]
    programs = recipe["ordered_profile_conditioning_program_records"]
    plans = recipe["ordered_logical_count_plan_records"]
    applications = {
        row["application_name"]: row
        for row in inventory["external_schema_registry_v2"][
            "ordered_rule_application_descriptors"
        ]
    }
    program_identity = _identity(catalog, "PROFILE_CONDITIONING_PROGRAM")
    plan_identity = _identity(catalog, "LOGICAL_COUNT_PLAN")
    program_schema = recipe["profile_conditioning_program_schema"]
    assert program_schema["ordered_member_names"] == [
        *program_identity["ordered_payload_member_names"],
        "profile_conditioning_program_id",
    ]
    assert program_schema["cross_application_relaxation_contract"] == {
        "generic_profile_policy": (
            "PERMITTED_ONLY_WHEN_EVERY_SCHEDULED_CROSS_APPLICATION_IS_"
            "BIJECTIVELY_MAPPED_TO_THE_IDENTITY_BOUND_DELETION_POLICY"
        ),
        "local_shutdown_profile_position_3_policy": "FORBIDDEN",
        "p1_p3_policy": "EXACT_APPLICATION_NO_RELAXATION",
    }
    assert program_schema["ordered_operation_opcodes"] == [
        "FIXED_VALUE",
        "SCOPE_ROOT",
        "APPLICATION_SCHEDULE_COUNT",
    ]
    template_by_id = {
        row["logical_plan_template_id"]: row
        for row in recipe["ordered_logical_plan_templates"]
    }
    relaxation_catalog = catalog["recurrence_catalog"][
        "ordered_safe_relaxation_records"
    ]
    named_relaxation = next(
        row
        for row in relaxation_catalog
        if row["relaxation_name"] == "DROP_COMPLETE_NAMED_CONSTRAINT_TO_SUPERSET_V1"
    )
    assert named_relaxation["soundness_rule"] == ("DELETE_CONJUNCT_PRODUCES_SUPERSET")

    assert len(profiles) == len(programs) == 408
    assert [row["profile_position"] for row in profiles] == list(range(1, 409))
    assert [row["program_position"] for row in programs] == list(range(1, 409))
    assert {
        kind: sum(profile["profile_kind"] == kind for profile in profiles)
        for kind in {
            "OUTER_RESULT_BOUNDARY_FIXTURE",
            "NON_CHECKPOINT_ROOT_FAMILY",
            "CHECKPOINT_ROOT_COORDINATE",
        }
    } == {
        "OUTER_RESULT_BOUNDARY_FIXTURE": 4,
        "NON_CHECKPOINT_ROOT_FAMILY": 4,
        "CHECKPOINT_ROOT_COORDINATE": 400,
    }

    for profile, program, plan in zip(profiles, programs, plans[66:474], strict=True):
        profile_position = profile["profile_position"]
        assert program["profile_position"] == profile_position
        assert program["case_position"] == profile_position + 66
        assert (
            program["maximum_constraint_scope_profile_id"]
            == profile["maximum_constraint_scope_profile_id"]
        )
        assert program["profile_inventory_json_pointer"] == (
            "/operation_contracts/maximum_constraint_scope_profile_catalog/"
            f"{profile_position - 1}"
        )
        assert program["profile_kind"] == profile["profile_kind"]
        assert program["conditioning_strategy"] == _expected_strategy(profile)
        assert program["measured_type_name"] == profile["measured_type_name"]
        assert set(program) == {
            *program_identity["ordered_payload_member_names"],
            "profile_conditioning_program_id",
        }
        program_payload = {
            name: program[name]
            for name in program_identity["ordered_payload_member_names"]
        }
        assert (
            program["profile_conditioning_program_version"]
            == program_identity["version_literal"]
        )
        assert program["profile_conditioning_program_id"] == _semantic_id(
            catalog, program_identity["domain_literal"], program_payload
        )

        expected_fixed = []
        for operation_position, (pointer, authority_id) in enumerate(
            zip(
                profile["ordered_source_authority_pointers"],
                profile["ordered_source_authority_ids"],
                strict=True,
            ),
            1,
        ):
            authority = _resolve_pointer(inventory, pointer)
            raw = _canonical_bytes(authority)
            expected_fixed.append(
                {
                    "operation_position": operation_position,
                    "opcode": "FIXED_VALUE",
                    "inventory_json_pointer": pointer,
                    "identity_member_name": _identity_member_name(
                        authority, authority_id
                    ),
                    "expected_authority_id": authority_id,
                    "fixed_canonical_octets": len(raw),
                    "fixed_canonical_sha256": _sha256(raw),
                }
            )
        assert program["ordered_fixed_authority_operations"] == expected_fixed

        profile_raw = _canonical_bytes(profile)
        scope = program["scope_root_operation"]
        template = template_by_id[program["logical_plan_template_id"]]
        expected_scope = {
            "operation_position": len(expected_fixed) + 1,
            "opcode": "SCOPE_ROOT",
            "profile_canonical_octets": len(profile_raw),
            "profile_canonical_sha256": _sha256(profile_raw),
            "scope_transfer_kind": (
                "OUTER_RESULT_APPLICATION"
                if profile["profile_kind"] == "OUTER_RESULT_BOUNDARY_FIXTURE"
                else "ROOT_APPLICATION"
            ),
            "measured_template_root_step_position": template["root_step_position"],
            "ordered_fixed_authority_operation_positions": list(
                range(1, len(expected_fixed) + 1)
            ),
            "ordered_scope_case_records": _expected_scope_cases(profile),
        }
        assert scope == expected_scope

        expected_counts = _expected_schedule_counts(profile)
        application = program["application_schedule_operation"]
        expected_segments = _expected_schedule_segments(profile, applications)
        assert application == {
            "operation_position": expected_scope["operation_position"] + 1,
            "opcode": "APPLICATION_SCHEDULE_COUNT",
            "child_operation_position": expected_scope["operation_position"],
            "execution_mode": "EXACT_CROSS_RULE_APPLICATION_V1",
            "ordered_schedule_segment_records": expected_segments,
            "application_invocation_count": expected_counts[0],
            "cross_rule_evaluation_count": expected_counts[1],
            "direct_cross_expression_node_count": expected_counts[2],
        }

        _expected_total_schedules, _expected_family_schedules = (
            _expected_summary_schedules(profile, applications)
        )
        scope_summary = plan["scope_summary"]
        scope_schema = recipe["logical_plan_schema"]["compact_scope_summary_schema"]
        assert set(scope_summary) == set(scope_schema["ordered_member_names"])
        assert (
            scope_summary["application_invocation_count"],
            scope_summary["cross_rule_evaluation_count"],
            scope_summary["direct_cross_expression_node_count"],
        ) == expected_counts

        assert "attainment_endpoint_contract" not in program
        assert "conditioning_transfer_program" in program
        assert (
            plan["profile_conditioning_program_id"]
            == program["profile_conditioning_program_id"]
        )
        assert (
            plan["profile_conditioning_program_id"]
            == program["profile_conditioning_program_id"]
        )
        assert plan["logical_root_reference"] == {
            "root_kind": "PROFILE_CONDITIONING_PROGRAM",
            "root_id": program["profile_conditioning_program_id"],
        }
        is_local_analytic = profile_position == 3
        assert scope_summary["schedule_authority_kind"] == (
            "PROFILE_CONDITIONING_PROGRAM"
        )
        assert (
            scope_summary["schedule_authority_id"]
            == program["profile_conditioning_program_id"]
        )
        assert (
            scope_summary["application_schedule_operation_position"]
            == (application["operation_position"])
        )
        assert scope_summary["p2_cross_application_deletion_policy_id"] == (
            None
            if is_local_analytic
            else recipe["p2_cross_application_deletion_policy"][
                "p2_cross_application_deletion_policy_id"
            ]
        )
        template_relaxation_ids = template["ordered_required_safe_relaxation_rule_ids"]
        required_relaxation_ids = {
            *template_relaxation_ids,
            named_relaxation["safe_relaxation_rule_id"],
        }
        expected_plan_relaxation_ids = (
            []
            if is_local_analytic
            else [
                row["safe_relaxation_rule_id"]
                for row in relaxation_catalog
                if row["safe_relaxation_rule_id"] in required_relaxation_ids
            ]
        )
        assert plan["ordered_safe_relaxation_rule_ids"] == (
            expected_plan_relaxation_ids
        )
        if not is_local_analytic:
            for relaxation_application in template[
                "ordered_relaxation_application_records"
            ]:
                assert relaxation_application["safe_relaxation_rule_id"] in (
                    expected_plan_relaxation_ids
                )
                assert relaxation_application["predicate_kind"] != (
                    "CROSS_RULE_APPLICATION"
                )
        plan_payload = {
            name: plan[name] for name in plan_identity["ordered_payload_member_names"]
        }
        assert set(plan) == {
            *plan_identity["ordered_payload_member_names"],
            "logical_count_plan_id",
        }
        assert plan["logical_count_plan_id"] == _semantic_id(
            catalog, plan_identity["domain_literal"], plan_payload
        )

    program_ids = [row["profile_conditioning_program_id"] for row in programs]
    binding_program_ids = [
        row["profile_conditioning_program_id"] for row in plans[66:474]
    ]
    assert len(set(program_ids)) == 408
    assert binding_program_ids == program_ids
    assert {row["logical_root_reference"]["root_id"] for row in plans[66:474]} == set(
        program_ids
    )
    assert all(
        row["logical_root_reference"]["root_kind"] == "PROFILE_CONDITIONING_PROGRAM"
        for row in plans[66:474]
    )


def test_case_69_uses_exact_local_baseline_program_not_structural_codec_cap() -> None:
    inventory = _load(INVENTORY_PATH)
    catalog = _load(CATALOG_PATH)
    recipe = catalog["logical_plan_recipe_catalog"]
    case_69 = recipe["ordered_logical_count_plan_records"][68]
    program_by_id = {
        row["profile_conditioning_program_id"]: row
        for row in recipe["ordered_profile_conditioning_program_records"]
    }
    program = program_by_id[case_69["profile_conditioning_program_id"]]
    local = catalog["recurrence_catalog"]["local_shutdown_analytic_catalog"]

    assert case_69["case_position"] == 69
    assert program["profile_position"] == 3
    assert program["operation_kind"] == "LOCAL_SHUTDOWN"
    assert program["conditioning_strategy"] == (
        "LOCAL_SHUTDOWN_BASELINE_ANALYTIC_EXACT_V1"
    )
    assert local["baseline_attainable_maximum_octets"] == 2_581
    p2 = program["conditioning_transfer_program"]["p2_upper_bound_program"]
    assert p2["upper_bound_source"] == ("LOCAL_SHUTDOWN_BASELINE_ANALYTIC_EXACT_V1")
    assert p2["ordered_safe_relaxation_rule_ids"] == []
    assert p2["ordered_template_relaxation_application_record_positions"] == []
    assert p2["ordered_deleted_cross_application_references"] == []
    assert p2["p2_cross_application_deletion_policy_id"] is None
    assert p2["application_schedule_operation_position"] is None
    assert case_69["scope_summary"]["p2_cross_application_deletion_policy_id"] is None
    assert case_69["upper_bound_mode"] == "EXACT_LEGAL_DOMAIN"
    assert case_69["ordered_safe_relaxation_rule_ids"] == []

    template = next(
        row
        for row in recipe["ordered_logical_plan_templates"]
        if row["logical_plan_template_id"] == case_69["logical_plan_template_id"]
    )
    structural_root = template["ordered_template_steps"][
        template["root_step_position"] - 1
    ]
    assert structural_root["derivation_kind"] == "CODEC_INTERSECTION"
    assert (
        structural_root["recurrence_parameters"]["ordered_codec_coordinate_records"][0][
            "derived_payload_octet_ceiling"
        ]
        == 524_287
    )
    local_cell = _execute_local_profile_p2(
        program=program,
        inventory=inventory,
        catalog=catalog,
    )
    assert local_cell["certified_lower_bound_octets"] == 2_581
    assert local_cell["certified_upper_bound_octets"] == 2_581
    assert local_cell["attaining_witness_canonical_octets"] == 2_581
    assert local_cell["certified_upper_bound_octets"] != 524_287


_P2_OPCODE_TYPES = {
    "LOAD_STRUCTURAL_TEMPLATE_SUPERSET_CELL_V1": ((), "P2_SUPERSET_BOUND_CELL"),
    "LOAD_FIXED_AUTHORITY_SET_V1": ((), "FIXED_AUTHORITY_SET"),
    "EXECUTE_LOCAL_SHUTDOWN_BASELINE_ANALYTIC_EXACT_V1": (
        ("FIXED_AUTHORITY_SET",),
        "P2_EXACT_ATTAINED_CELL",
    ),
    "INTERSECT_EXACT_ANALYTIC_WITH_STRUCTURAL_CELL_V1": (
        ("P2_EXACT_ATTAINED_CELL", "P2_SUPERSET_BOUND_CELL"),
        "P2_EXACT_ATTAINED_CELL",
    ),
}

_P1_P3_OPCODE_TYPES = {
    "IMPORT_P2_BOUND_CELL_V1": ((), "P2_BOUND_CELL"),
    "LOAD_RETAINED_WITNESS_CONTEXT_V1": ((), "RETAINED_WITNESS_CONTEXT"),
    "LOAD_FIXED_AUTHORITY_SET_V1": ((), "FIXED_AUTHORITY_SET"),
    "MATCH_EXACT_PROFILE_SCOPE_CASE_V1": (
        ("RETAINED_WITNESS_CONTEXT", "FIXED_AUTHORITY_SET"),
        "SELECTED_EXACT_SCOPE_CASE",
    ),
    "RECONSTRUCT_EXACT_APPLICATION_SCHEDULE_V1": (
        ("SELECTED_EXACT_SCOPE_CASE", "FIXED_AUTHORITY_SET"),
        "EXACT_APPLICATION_SCHEDULE",
    ),
    "EXECUTE_PINNED_APPLICATION_RULE_AST_ON_RETAINED_BYTES_V1": (
        (
            "RETAINED_WITNESS_CONTEXT",
            "FIXED_AUTHORITY_SET",
            "EXACT_APPLICATION_SCHEDULE",
        ),
        "P1_LEGALITY_RESULT",
    ),
    "MEASURE_RETAINED_WITNESS_CANONICAL_OCTETS_V1": (
        ("RETAINED_WITNESS_CONTEXT",),
        "MEASURED_CANONICAL_OCTETS",
    ),
    "REQUIRE_P1_AND_P3_EQUALITY_V1": (
        ("P2_BOUND_CELL", "P1_LEGALITY_RESULT", "MEASURED_CANONICAL_OCTETS"),
        "PROFILE_MAXIMUM_ACCEPTANCE_RESULT",
    ),
}


def _typecheck_instruction_program(
    instruction_program: dict[str, Any],
    *,
    expected_version: str,
    opcode_types: dict[str, tuple[tuple[str, ...], str]],
    expected_root_type: str,
) -> None:
    assert instruction_program["program_version"] == expected_version
    instructions = instruction_program["ordered_instruction_records"]
    assert [row["instruction_position"] for row in instructions] == list(
        range(1, len(instructions) + 1)
    )
    output_type_by_position: dict[int, str] = {}
    for instruction in instructions:
        position = instruction["instruction_position"]
        assert set(instruction) == {
            "instruction_position",
            "opcode",
            "ordered_input_instruction_positions",
            "output_type",
            "parameters",
        }
        opcode = instruction["opcode"]
        assert opcode in opcode_types
        expected_input_types, expected_output_type = opcode_types[opcode]
        input_positions = instruction["ordered_input_instruction_positions"]
        assert all(
            type(child) is int and 1 <= child < position for child in input_positions
        )
        assert tuple(output_type_by_position[child] for child in input_positions) == (
            expected_input_types
        )
        assert instruction["output_type"] == expected_output_type
        output_type_by_position[position] = expected_output_type
    root = instruction_program["root_instruction_position"]
    assert root == len(instructions)
    assert output_type_by_position[root] == expected_root_type
    assert instruction_program["failure_policy"] == (
        "UNRESOLVED_EMPTY_INVALID_OR_LIMIT_EXCEEDED_NO_GO"
    )


def _typecheck_dual_channel_program(program: dict[str, Any]) -> None:
    transfer = program["conditioning_transfer_program"]
    assert set(transfer) == {
        "program_version",
        "cell_contract_id",
        "p2_upper_bound_program",
        "p1_p3_attainment_program",
    }
    assert transfer["program_version"] == (
        "riskyieldmm.raw_v8_step2_external_schema_v2."
        "profile_conditioning_dual_channel_program.v1"
    )
    p2 = transfer["p2_upper_bound_program"]
    expected_p2_root_type = (
        "P2_EXACT_ATTAINED_CELL"
        if program["profile_position"] == 3
        else "P2_SUPERSET_BOUND_CELL"
    )
    _typecheck_instruction_program(
        p2,
        expected_version=(
            "riskyieldmm.raw_v8_step2_external_schema_v2."
            "profile_p2_upper_bound_program.v1"
        ),
        opcode_types=_P2_OPCODE_TYPES,
        expected_root_type=expected_p2_root_type,
    )
    _typecheck_instruction_program(
        transfer["p1_p3_attainment_program"],
        expected_version=(
            "riskyieldmm.raw_v8_step2_external_schema_v2."
            "profile_p1_p3_attainment_program.v1"
        ),
        opcode_types=_P1_P3_OPCODE_TYPES,
        expected_root_type="PROFILE_MAXIMUM_ACCEPTANCE_RESULT",
    )


def _decimal_width(value: int) -> int:
    assert type(value) is int and value >= 0
    return len(str(value))


def _execute_local_profile_p2(
    *,
    program: dict[str, Any],
    inventory: dict[str, Any],
    catalog: dict[str, Any],
) -> dict[str, Any]:
    _typecheck_dual_channel_program(program)
    transfer = program["conditioning_transfer_program"]
    p2 = transfer["p2_upper_bound_program"]
    instructions = p2["ordered_instruction_records"]
    values: dict[int, tuple[str, Any]] = {}
    fixed_by_position = {
        row["operation_position"]: row
        for row in program["ordered_fixed_authority_operations"]
    }
    local = catalog["recurrence_catalog"]["local_shutdown_analytic_catalog"]
    for instruction in instructions:
        position = instruction["instruction_position"]
        opcode = instruction["opcode"]
        parameters = instruction["parameters"]
        input_values = [
            values[input_position][1]
            for input_position in instruction["ordered_input_instruction_positions"]
        ]
        if opcode == "LOAD_STRUCTURAL_TEMPLATE_SUPERSET_CELL_V1":
            assert (
                parameters["logical_plan_template_id"]
                == program["logical_plan_template_id"]
            )
            template = next(
                row
                for row in catalog["logical_plan_recipe_catalog"][
                    "ordered_logical_plan_templates"
                ]
                if row["logical_plan_template_id"]
                == parameters["logical_plan_template_id"]
            )
            assert (
                parameters["template_root_step_position"]
                == template["root_step_position"]
            )
            root = template["ordered_template_steps"][
                template["root_step_position"] - 1
            ]
            assert root["derivation_kind"] == "CODEC_INTERSECTION"
            coordinates = root["recurrence_parameters"][
                "ordered_codec_coordinate_records"
            ]
            assert coordinates
            structural_upper = min(
                row["derived_payload_octet_ceiling"] for row in coordinates
            )
            assert type(structural_upper) is int and structural_upper >= 0
            value: Any = {
                "cell_kind": "SUPERSET_UPPER_BOUND",
                "cell_status": "CERTIFIED_SUPERSET",
                "certified_lower_bound_octets": 0,
                "certified_upper_bound_octets": structural_upper,
                "attaining_witness_canonical_octets": None,
                "proof_source_id": template["logical_plan_template_id"],
            }
        elif opcode == "LOAD_FIXED_AUTHORITY_SET_V1":
            assert parameters == {
                "ordered_fixed_authority_operation_positions": list(fixed_by_position)
            }
            value = fixed_by_position
        elif opcode == "EXECUTE_LOCAL_SHUTDOWN_BASELINE_ANALYTIC_EXACT_V1":
            assert (
                parameters["local_shutdown_analytic_catalog_id"]
                == local["local_shutdown_analytic_catalog_id"]
            )
            fixed_operation = fixed_by_position[
                parameters["fixed_spec_operation_position"]
            ]
            assert fixed_operation["inventory_json_pointer"] == (
                "/fixture_records/operation_specs/LOCAL_SHUTDOWN"
            )
            spec = _resolve_pointer(
                inventory, fixed_operation["inventory_json_pointer"]
            )
            assert (
                spec[fixed_operation["identity_member_name"]]
                == fixed_operation["expected_authority_id"]
            )
            batch_limit = spec["spec"]["maximum_terminal_ingress_batches"]
            analytic = local["batch_unsaturated_program"]
            assert analytic["opcode"] == "PIECEWISE_AFFINE_DECIMAL_WIDTH_V1"
            assert analytic["valid_minimum"] <= batch_limit <= analytic["valid_maximum"]
            derived = (
                analytic["constant_octets"]
                + analytic["linear_coefficient"] * batch_limit
                + analytic["decimal_width_coefficient"] * _decimal_width(batch_limit)
            )
            value = {
                "cell_kind": "EXACT_ATTAINED_MAXIMUM",
                "cell_status": "EXACT_ATTAINED",
                "certified_lower_bound_octets": derived,
                "certified_upper_bound_octets": derived,
                "attaining_witness_canonical_octets": derived,
                "proof_source_id": local["local_shutdown_analytic_catalog_id"],
            }
        elif opcode == "INTERSECT_EXACT_ANALYTIC_WITH_STRUCTURAL_CELL_V1":
            assert parameters == {
                "intersection_rule": (
                    "EXACT_ANALYTIC_UPPER_MUST_NOT_EXCEED_STRUCTURAL_UPPER"
                ),
                "empty_structural_cell_policy": "NO_GO",
                "analytic_above_structural_upper_policy": "NO_GO",
                "preserve_exact_attained_cell": True,
            }
            analytic_cell, structural_cell = input_values
            assert structural_cell["cell_status"] == "CERTIFIED_SUPERSET"
            assert (
                structural_cell["certified_lower_bound_octets"]
                <= (structural_cell["certified_upper_bound_octets"])
            )
            assert analytic_cell["cell_kind"] == "EXACT_ATTAINED_MAXIMUM"
            assert (
                analytic_cell["certified_upper_bound_octets"]
                <= (structural_cell["certified_upper_bound_octets"])
            )
            value = analytic_cell
        else:
            raise AssertionError(f"unexpected local P2 opcode: {opcode}")
        values[position] = (instruction["output_type"], value)
    return values[p2["root_instruction_position"]][1]


def _assert_exact_attained_cell(cell: dict[str, Any], contract: dict[str, Any]) -> None:
    assert set(cell) == set(contract["p2_cell_ordered_member_names"])
    assert cell["cell_kind"] == "EXACT_ATTAINED_MAXIMUM"
    assert cell["cell_status"] == "EXACT_ATTAINED"
    assert cell["certified_lower_bound_octets"] == cell["certified_upper_bound_octets"]
    assert (
        cell["attaining_witness_canonical_octets"]
        == cell["certified_upper_bound_octets"]
    )
    assert contract["unresolved_or_unattained_policy"] == "NO_GO"
    assert contract["structural_bound_only_acceptance_forbidden"] is True


def _expected_deleted_cross_application_references(
    schedules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "deletion_position": position,
            "application_schedule_position": schedule["schedule_position"],
            "rule_application_id": schedule["rule_application_id"],
        }
        for position, schedule in enumerate(schedules, 1)
    ]


def _assert_exact_relaxation_policy(
    *,
    program: dict[str, Any],
    plan: dict[str, Any],
    schedules: list[dict[str, Any]],
    template: dict[str, Any],
    named_relaxation: dict[str, Any],
    deletion_policy: dict[str, Any],
    relaxation_catalog: list[dict[str, Any]],
) -> None:
    p2 = program["conditioning_transfer_program"]["p2_upper_bound_program"]
    is_local = program["profile_position"] == 3
    expected_template_positions = (
        []
        if is_local
        else list(range(1, len(template["ordered_relaxation_application_records"]) + 1))
    )
    assert [row["schedule_position"] for row in schedules] == list(
        range(1, len(schedules) + 1)
    )
    expected_cross = (
        [] if is_local else _expected_deleted_cross_application_references(schedules)
    )
    assert p2["ordered_template_relaxation_application_record_positions"] == (
        expected_template_positions
    )
    assert p2["p2_cross_application_deletion_policy_id"] == (
        None if is_local else deletion_policy["p2_cross_application_deletion_policy_id"]
    )
    assert p2["application_schedule_operation_position"] == (
        None
        if is_local
        else program["application_schedule_operation"]["operation_position"]
    )
    assert p2["ordered_deleted_cross_application_references"] == expected_cross
    required_safe_ids = {
        *template["ordered_required_safe_relaxation_rule_ids"],
        named_relaxation["safe_relaxation_rule_id"],
    }
    expected_safe_ids = (
        []
        if is_local
        else [
            row["safe_relaxation_rule_id"]
            for row in relaxation_catalog
            if row["safe_relaxation_rule_id"] in required_safe_ids
        ]
    )
    assert p2["ordered_safe_relaxation_rule_ids"] == expected_safe_ids
    assert plan["ordered_safe_relaxation_rule_ids"] == expected_safe_ids
    assert named_relaxation["soundness_rule"] == "DELETE_CONJUNCT_PRODUCES_SUPERSET"
    assert expected_safe_ids.count(named_relaxation["safe_relaxation_rule_id"]) == (
        0 if is_local else 1
    )

    mapping_by_application_id = {
        row["rule_application_id"]: row
        for row in deletion_policy["ordered_rule_application_mapping_records"]
    }
    assert len(mapping_by_application_id) == len(
        deletion_policy["ordered_rule_application_mapping_records"]
    )
    schedule_by_position = {row["schedule_position"]: row for row in schedules}
    for reference in expected_cross:
        schedule = schedule_by_position[reference["application_schedule_position"]]
        assert schedule["rule_application_id"] == reference["rule_application_id"]
        mapping = mapping_by_application_id[reference["rule_application_id"]]
        assert mapping["rule_id"] == schedule["rule_id"]
    scope = plan["scope_summary"]
    assert scope["schedule_authority_kind"] == "PROFILE_CONDITIONING_PROGRAM"
    assert scope["schedule_authority_id"] == program["profile_conditioning_program_id"]
    assert (
        scope["application_schedule_operation_position"]
        == program["application_schedule_operation"]["operation_position"]
    )
    assert scope["p2_cross_application_deletion_policy_id"] == (
        None if is_local else deletion_policy["p2_cross_application_deletion_policy_id"]
    )


def test_profile_conditioning_requires_executable_typed_transfer_and_exact_output() -> (
    None
):
    inventory = _load(INVENTORY_PATH)
    catalog = _load(CATALOG_PATH)
    recipe = catalog["logical_plan_recipe_catalog"]
    contract = recipe["profile_conditioned_cell_contract"]
    assert contract["contract_version"] == (
        "riskyieldmm.raw_v8_step2_external_schema_v2."
        "profile_conditioned_cell_contract.v1"
    )
    assert contract["p2_cell_ordered_member_names"] == [
        "cell_kind",
        "cell_status",
        "certified_lower_bound_octets",
        "certified_upper_bound_octets",
        "attaining_witness_canonical_octets",
        "proof_source_id",
    ]
    assert contract["unresolved_or_unattained_policy"] == "NO_GO"
    assert contract["structural_bound_only_acceptance_forbidden"] is True
    assert contract["p2_cell_kind_enum"] == [
        "SUPERSET_UPPER_BOUND",
        "EXACT_ATTAINED_MAXIMUM",
    ]
    assert contract["generic_superset_attainability_claimed"] is False
    contract_identity = _identity(catalog, "PROFILE_CONDITIONED_CELL_CONTRACT")
    contract_payload = {
        name: contract[name]
        for name in contract_identity["ordered_payload_member_names"]
    }
    assert set(contract) == {
        *contract_identity["ordered_payload_member_names"],
        "profile_conditioned_cell_contract_id",
    }
    assert contract["profile_conditioned_cell_contract_id"] == _semantic_id(
        catalog,
        contract_identity["domain_literal"],
        contract_payload,
    )

    programs = recipe["ordered_profile_conditioning_program_records"]
    plans = recipe["ordered_logical_count_plan_records"][66:474]
    profiles = inventory["operation_contracts"][
        "maximum_constraint_scope_profile_catalog"
    ]
    templates = {
        row["logical_plan_template_id"]: row
        for row in recipe["ordered_logical_plan_templates"]
    }
    named_relaxation = next(
        row
        for row in catalog["recurrence_catalog"]["ordered_safe_relaxation_records"]
        if row["relaxation_name"] == "DROP_COMPLETE_NAMED_CONSTRAINT_TO_SUPERSET_V1"
    )
    deletion_policy = recipe["p2_cross_application_deletion_policy"]
    deletion_policy_identity = _identity(
        catalog, "P2_CROSS_APPLICATION_DELETION_POLICY"
    )
    deletion_policy_payload = {
        name: deletion_policy[name]
        for name in deletion_policy_identity["ordered_payload_member_names"]
    }
    assert set(deletion_policy) == {
        *deletion_policy_identity["ordered_payload_member_names"],
        "p2_cross_application_deletion_policy_id",
    }
    assert deletion_policy["p2_cross_application_deletion_policy_id"] == (
        _semantic_id(
            catalog,
            deletion_policy_identity["domain_literal"],
            deletion_policy_payload,
        )
    )
    assert (
        deletion_policy["safe_relaxation_rule_id"]
        == named_relaxation["safe_relaxation_rule_id"]
    )
    assert (
        deletion_policy["deleted_predicate_class"]
        == named_relaxation["deleted_predicate_class"]
    )
    assert deletion_policy["soundness_rule"] == named_relaxation["soundness_rule"]
    applications = {
        row["application_name"]: row
        for row in inventory["external_schema_registry_v2"][
            "ordered_rule_application_descriptors"
        ]
    }
    mapped_names = [
        "APPLY/OPERATION_RESULT_SIGNED_SPEC_V1",
        "APPLY/SELECTOR_MARKER_CONTRACT_V1",
        "APPLY/V2_OBSERVATION_AGGREGATE_REGISTRY_V1",
        "APPLY/V2_OBSERVATION_FIELDS_REGISTRY_V1",
        "APPLY/V2_ROOT_OBSERVATION_MEMBERSHIP_V1",
        "APPLY/V2_ROOT_SELECTOR_LIFECYCLE_V1",
    ]
    assert mapped_names == sorted(mapped_names)
    assert deletion_policy["ordered_rule_application_mapping_records"] == [
        {
            "mapping_position": position,
            "rule_application_id": applications[name]["rule_application_id"],
            "rule_id": applications[name]["rule_id"],
        }
        for position, name in enumerate(mapped_names, 1)
    ]
    assert len(programs) == 408
    for program, plan, profile in zip(programs, plans, profiles, strict=True):
        _typecheck_dual_channel_program(program)
        assert (
            program["conditioning_transfer_program"]["cell_contract_id"]
            == (contract["profile_conditioned_cell_contract_id"])
        )
        p2 = program["conditioning_transfer_program"]["p2_upper_bound_program"]
        if program["profile_position"] == 3:
            assert p2["upper_bound_source"] == (
                "LOCAL_SHUTDOWN_BASELINE_ANALYTIC_EXACT_V1"
            )
        else:
            assert p2["upper_bound_source"] == "STRUCTURAL_TEMPLATE_SUPERSET_V1"
            assert p2["generic_attainability_claimed"] is False
        _assert_exact_relaxation_policy(
            program=program,
            plan=plan,
            schedules=_expected_summary_schedules(profile, applications)[0],
            template=templates[program["logical_plan_template_id"]],
            named_relaxation=named_relaxation,
            deletion_policy=deletion_policy,
            relaxation_catalog=catalog["recurrence_catalog"][
                "ordered_safe_relaxation_records"
            ],
        )

    local_program = programs[2]
    assert local_program["case_position"] == 69
    local_cell = _execute_local_profile_p2(
        program=local_program,
        inventory=inventory,
        catalog=catalog,
    )
    _assert_exact_attained_cell(local_cell, contract)
    assert local_cell["certified_upper_bound_octets"] == 2_581

    above_cap_catalog = deepcopy(catalog)
    above_cap_catalog["recurrence_catalog"]["local_shutdown_analytic_catalog"][
        "batch_unsaturated_program"
    ]["constant_octets"] += 524_288
    try:
        _execute_local_profile_p2(
            program=local_program,
            inventory=inventory,
            catalog=above_cap_catalog,
        )
    except AssertionError:
        pass
    else:
        raise AssertionError("analytic exact cell above structural cap was accepted")

    empty_structural_catalog = deepcopy(catalog)
    empty_template = next(
        row
        for row in empty_structural_catalog["logical_plan_recipe_catalog"][
            "ordered_logical_plan_templates"
        ]
        if row["logical_plan_template_id"] == local_program["logical_plan_template_id"]
    )
    empty_template["ordered_template_steps"][empty_template["root_step_position"] - 1][
        "recurrence_parameters"
    ]["ordered_codec_coordinate_records"] = []
    try:
        _execute_local_profile_p2(
            program=local_program,
            inventory=inventory,
            catalog=empty_structural_catalog,
        )
    except AssertionError:
        pass
    else:
        raise AssertionError("empty structural cell was accepted")

    forged_structural_cell = deepcopy(local_cell)
    forged_structural_cell["certified_upper_bound_octets"] = 524_287
    try:
        _assert_exact_attained_cell(forged_structural_cell, contract)
    except AssertionError:
        pass
    else:
        raise AssertionError("detached structural cap was accepted as exact profile U")

    generic_program = deepcopy(programs[0])
    generic_plan = plans[0]
    generic_p2 = generic_program["conditioning_transfer_program"][
        "p2_upper_bound_program"
    ]
    assert generic_p2["ordered_deleted_cross_application_references"]
    for mutation in (
        generic_p2["ordered_deleted_cross_application_references"][:-1],
        [
            *generic_p2["ordered_deleted_cross_application_references"],
            generic_p2["ordered_deleted_cross_application_references"][0],
        ],
    ):
        mutated = deepcopy(generic_program)
        mutated["conditioning_transfer_program"]["p2_upper_bound_program"][
            "ordered_deleted_cross_application_references"
        ] = mutation
        try:
            _assert_exact_relaxation_policy(
                program=mutated,
                plan=generic_plan,
                schedules=_expected_summary_schedules(profiles[0], applications)[0],
                template=templates[generic_program["logical_plan_template_id"]],
                named_relaxation=named_relaxation,
                deletion_policy=deletion_policy,
                relaxation_catalog=catalog["recurrence_catalog"][
                    "ordered_safe_relaxation_records"
                ],
            )
        except AssertionError:
            pass
        else:
            raise AssertionError("missing or extra deleted predicate was accepted")

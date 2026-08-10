#!/usr/bin/env python3
"""Independent census of the V2 profile-attainability correction surface.

The accepted seed deliberately computes a structural P2 superset for generic
profile-conditioning programs.  The same programs later require a retained
P1-legal witness whose canonical length equals the P2 endpoint.  This checker
does not guess which of those endpoints happen to be attainable.  It proves
which programs and internal scope cases use that shortcut, and it fails closed
if their plan, inventory, application-schedule, or P1/P3 bindings drift.

This is a read-only audit.  It imports neither the seed generator nor any
producer, verifier, runtime, or legacy constructive implementation.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys
from typing import Any

SEED_RELATIVE_PATH = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.json"
)
INVENTORY_RELATIVE_PATH = "tests/raw_v8_step2_inventory_v4_v49f.json"

SEED_RAW_SHA256 = "a75a2f352e8513b7ff0043693a0c65ebbf4bc6f06859354789af69e1162b0e4f"
INVENTORY_RAW_SHA256 = (
    "de91eac92d1c36cf1670b2484392fbf1c633d75f928c8e70fcd5e71ae798db2b"
)

GENERIC_STRATEGY = "STRUCTURAL_TEMPLATE_SUPERSET_WITH_EXACT_RETAINED_ATTAINMENT_V1"
EXACT_STRATEGY = "LOCAL_SHUTDOWN_BASELINE_ANALYTIC_EXACT_V1"
GENERIC_P2_SOURCE = "STRUCTURAL_TEMPLATE_SUPERSET_V1"
EXACT_P2_SOURCE = "LOCAL_SHUTDOWN_BASELINE_ANALYTIC_EXACT_V1"
P1_P3_ACCEPTANCE = "P1_TRUE_AND_MEASURED_CANONICAL_OCTETS_EQUALS_P2_UPPER"
PLAN_GENERIC_MODE = "LEGAL_DOMAIN_SUPERSET_WITH_LEGAL_ATTAINMENT"
PLAN_EXACT_MODE = "EXACT_LEGAL_DOMAIN"
AUDIT_DOMAIN = (
    "RiskYieldMMStep2MaximumProtocolV2ProfileAttainabilityScopeAuditV1V4_9F_RawV8"
)
CORRECTION_CONTRACT_DOMAIN = (
    "RiskYieldMMStep2MaximumProtocolV2ApplicationAwareExactnessCorrectionV2V4_9F_RawV8"
)

CORRECTION_CONTRACT = {
    "contract_version": (
        "riskyieldmm.raw_v8_step2.maximum_protocol_v2."
        "application_aware_exactness_correction.v2"
    ),
    "affected_profile_policy": (
        "EVERY_STRUCTURAL_SUPERSET_PROFILE_TRANSITIONS_TO_THE_V2_EXACTNESS_JOIN_"
        "OR_REMAINS_NO_GO"
    ),
    "upper_bound_channel": {
        "result_kind": "PROVED_LEGAL_UPPER_BOUND",
        "structural_cell_role": "SAFETY_CEILING_ONLY_NOT_EXACTNESS_EVIDENCE",
        "scope_rule": (
            "DERIVE_EXACT_MAXIMUM_FOR_EVERY_INTERNAL_SCOPE_CASE_THEN_TAKE_"
            "THE_MAXIMUM_WITH_A_BOUND_WINNER_SCOPE_CASE"
        ),
        "derivation_rule": (
            "PINNED_TYPED_RULE_DEPENDENCY_GRAPH_PLUS_EXACT_COMPONENT_OPTIMIZATION"
        ),
        "certificate_rule": (
            "IDENTITY_BOUND_RECOMPUTABLE_DOMAIN_COMPONENT_AND_COMPOSITION_CERTIFICATE"
        ),
        "unresolved_unbounded_or_intractable_policy": "NO_GO",
    },
    "attainment_channel": {
        "result_kind": "INDEPENDENT_LEGAL_ATTAINMENT",
        "legality_rule": (
            "EXECUTE_PINNED_APPLICATION_RULE_AST_ON_RETAINED_CANONICAL_BYTES"
        ),
        "measurement_rule": "MEASURE_RETAINED_WITNESS_CANONICAL_OCTETS",
        "independence_rule": (
            "NO_SHARED_EXECUTABLE_OR_PRECOMPUTED_ANSWER_WITH_UPPER_BOUND_DERIVER"
        ),
        "unresolved_invalid_or_unattained_policy": "NO_GO",
    },
    "exactness_join": {
        "input_kinds": [
            "PROVED_LEGAL_UPPER_BOUND",
            "INDEPENDENT_LEGAL_ATTAINMENT",
        ],
        "authority_rule": (
            "PROFILE_SCOPE_FIXED_AUTHORITIES_AND_APPLICATION_SCHEDULE_IDENTITIES_"
            "MUST_MATCH"
        ),
        "equality_rule": (
            "LEGAL_WITNESS_CANONICAL_OCTETS_EQUALS_PROVED_LEGAL_UPPER_BOUND"
        ),
        "success_result_kind": "EXACT_ATTAINED_MAXIMUM",
        "superset_join_policy": "FORBIDDEN",
    },
    "optimization_policy": {
        "selected_method": (
            "TYPED_FACTORIZED_EXACT_OPTIMIZER_WITH_CHECKABLE_CERTIFICATE"
        ),
        "dependency_partition_rule": (
            "PARTITION_ONLY_AFTER_ALL_RULE_AST_AND_COMPLEX_OPERATOR_READS_"
            "AND_WRITES_PROVE_COMPONENT_CLOSURE"
        ),
        "external_solver_policy": (
            "MAY_PROPOSE_WITNESSES_OR_CERTIFICATES_BUT_IS_NEVER_ACCEPTANCE_AUTHORITY"
        ),
        "per_profile_formula_policy": (
            "FORBIDDEN_EXCEPT_IDENTITY_BOUND_CLOSED_LOCAL_ANALYTIC_SPECIAL_CASES"
        ),
        "guessed_independence_policy": "FORBIDDEN",
    },
    "migration_policy": {
        "accepted_v1_identity_policy": "IMMUTABLE_PREDECESSOR_EVIDENCE",
        "transition_rule": (
            "NEW_SEED_MANIFEST_BOUNDARY_TARGET_VERIFIER_PRODUCER_AND_RUNNER_VERSION"
        ),
        "pilot_resume_rule": (
            "CASE435_EXACT_BOUND_AND_INDEPENDENT_ATTAINER_PASS_BEFORE_A4_P6_V"
        ),
        "all_profile_closure_rule": (
            "ALL_407_AFFECTED_PROGRAMS_AND_474_SCOPE_CASES_CLOSE_BEFORE_475_CASE_"
            "MAXIMUM_CLAIM"
        ),
    },
}


class ProfileScopeAuditError(RuntimeError):
    """Raised when the frozen authority or the audited contract differs."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ProfileScopeAuditError(message)


def _duplicate_guard(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        _require(key not in value, f"duplicate JSON member: {key}")
        value[key] = item
    return value


def _reject_number(value: str) -> Any:
    raise ProfileScopeAuditError(f"floating or non-finite JSON number: {value}")


def _strict_load(raw: bytes, label: str) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8", errors="strict")
        _require(not text.startswith("\ufeff"), f"{label} has a BOM")
        value = json.loads(
            text,
            object_pairs_hook=_duplicate_guard,
            parse_float=_reject_number,
            parse_constant=_reject_number,
        )
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ProfileScopeAuditError(f"{label} is not strict JSON") from error
    _require(type(value) is dict, f"{label} root is not an object")
    return value


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8", errors="strict")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _load_pinned(
    root: pathlib.Path,
    relative_path: str,
    expected_sha256: str,
) -> dict[str, Any]:
    path = root / relative_path
    _require(
        path.is_file() and not path.is_symlink(), f"authority absent: {relative_path}"
    )
    raw = path.read_bytes()
    _require(
        _sha256(raw) == expected_sha256,
        f"authority hash differs: {relative_path}",
    )
    return _strict_load(raw, relative_path)


def _positive_integer(value: Any, label: str) -> int:
    _require(
        type(value) is int and value > 0,
        f"{label} is not a positive integer",
    )
    return value


def _contiguous_positions(rows: Any, name: str, label: str) -> list[dict[str, Any]]:
    _require(type(rows) is list and rows, f"{label} is empty")
    _require(
        all(type(row) is dict for row in rows),
        f"{label} contains a non-object",
    )
    _require(
        [row.get(name) for row in rows] == list(range(1, len(rows) + 1)),
        f"{label} positions differ",
    )
    return rows


def _index(
    rows: Any, name: str, expected_count: int, label: str
) -> dict[Any, dict[str, Any]]:
    _require(
        type(rows) is list and len(rows) == expected_count,
        f"{label} count differs",
    )
    result: dict[Any, dict[str, Any]] = {}
    for row in rows:
        _require(type(row) is dict and name in row, f"{label} member differs")
        key = row[name]
        _require(key not in result, f"{label} key is duplicated: {key}")
        result[key] = row
    return result


def _group_records(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys = (
        "measured_type_name",
        "profile_kind",
        "operation_kind",
        "constraint_scope",
    )
    grouped: dict[tuple[str, ...], dict[str, Any]] = {}
    for row in rows:
        key = tuple(row[name] for name in keys)
        record = grouped.setdefault(
            key,
            {
                **dict(zip(keys, key, strict=True)),
                "program_count": 0,
                "scope_case_count": 0,
                "application_invocation_count": 0,
                "cross_rule_evaluation_count": 0,
                "direct_cross_expression_node_count": 0,
            },
        )
        record["program_count"] += 1
        record["scope_case_count"] += row["scope_case_count"]
        record["application_invocation_count"] += row["application_invocation_count"]
        record["cross_rule_evaluation_count"] += row["cross_rule_evaluation_count"]
        record["direct_cross_expression_node_count"] += row[
            "direct_cross_expression_node_count"
        ]
    return [grouped[key] for key in sorted(grouped)]


def _validate_schedule(program: dict[str, Any]) -> tuple[int, int, set[str]]:
    label = f"program {program['program_position']} schedule"
    scope_cases = _contiguous_positions(
        program["scope_root_operation"]["ordered_scope_case_records"],
        "scope_case_position",
        f"{label} scope cases",
    )
    schedule = program["application_schedule_operation"]
    segments = _contiguous_positions(
        schedule["ordered_schedule_segment_records"],
        "segment_position",
        f"{label} segments",
    )
    _require(
        sum(
            _positive_integer(row["scope_case_multiplicity"], label) for row in segments
        )
        == len(scope_cases),
        f"{label} multiplicity differs",
    )
    totals = {
        aggregate_name: sum(
            _positive_integer(row[per_case_name], label)
            * _positive_integer(row["scope_case_multiplicity"], label)
            for row in segments
        )
        for aggregate_name, per_case_name in (
            (
                "application_invocation_count",
                "application_invocation_count_per_scope_case",
            ),
            (
                "cross_rule_evaluation_count",
                "cross_rule_evaluation_count_per_scope_case",
            ),
            (
                "direct_cross_expression_node_count",
                "direct_cross_expression_node_count_per_scope_case",
            ),
        )
    }
    for name, expected in totals.items():
        _require(schedule[name] == expected, f"{label} {name} differs")

    scheduled_application_ids: set[str] = set()
    selector_present_scope_cases = 0
    for segment in segments:
        instructions = _contiguous_positions(
            segment["ordered_application_instruction_records"],
            "instruction_position",
            f"{label} segment instructions",
        )
        _require(
            sum(
                row["application_invocation_count_per_scope_case"]
                for row in instructions
            )
            == segment["application_invocation_count_per_scope_case"],
            f"{label} segment invocation sum differs",
        )
        _require(
            sum(
                row["cross_rule_evaluation_count_per_scope_case"]
                for row in instructions
            )
            == segment["cross_rule_evaluation_count_per_scope_case"],
            f"{label} segment evaluation sum differs",
        )
        scheduled_application_ids.update(
            row["rule_application_id"] for row in instructions
        )
        if segment["selector_present"] is True:
            selector_present_scope_cases += segment["scope_case_multiplicity"]
        else:
            _require(
                segment["selector_present"] is False,
                f"{label} selector flag differs",
            )
    return len(scope_cases), selector_present_scope_cases, scheduled_application_ids


def _validate_p1_p3(program: dict[str, Any]) -> None:
    p1_p3 = program["conditioning_transfer_program"]["p1_p3_attainment_program"]
    instructions = _contiguous_positions(
        p1_p3["ordered_instruction_records"],
        "instruction_position",
        f"program {program['program_position']} P1/P3 instructions",
    )
    expected_opcodes = (
        "IMPORT_P2_BOUND_CELL_V1",
        "LOAD_RETAINED_WITNESS_CONTEXT_V1",
        "LOAD_FIXED_AUTHORITY_SET_V1",
        "MATCH_EXACT_PROFILE_SCOPE_CASE_V1",
        "RECONSTRUCT_EXACT_APPLICATION_SCHEDULE_V1",
        "EXECUTE_PINNED_APPLICATION_RULE_AST_ON_RETAINED_BYTES_V1",
        "MEASURE_RETAINED_WITNESS_CANONICAL_OCTETS_V1",
        "REQUIRE_P1_AND_P3_EQUALITY_V1",
    )
    _require(
        tuple(row["opcode"] for row in instructions) == expected_opcodes,
        f"program {program['program_position']} P1/P3 opcode order differs",
    )
    _require(
        p1_p3["root_instruction_position"] == 8
        and instructions[-1]["parameters"]["acceptance_rule"] == P1_P3_ACCEPTANCE,
        f"program {program['program_position']} P1/P3 acceptance differs",
    )
    _require(
        instructions[1]["parameters"]
        == {
            "constraint_scope_profile_id": program[
                "maximum_constraint_scope_profile_id"
            ],
            "measured_type_name": program["measured_type_name"],
        },
        f"program {program['program_position']} retained context binding differs",
    )


def _affected_row(
    program: dict[str, Any],
    plan: dict[str, Any],
    scope_case_count: int,
    selector_present_scope_case_count: int,
) -> dict[str, Any]:
    schedule = program["application_schedule_operation"]
    return {
        "program_position": program["program_position"],
        "case_position": program["case_position"],
        "profile_position": program["profile_position"],
        "profile_conditioning_program_id": program["profile_conditioning_program_id"],
        "maximum_constraint_scope_profile_id": program[
            "maximum_constraint_scope_profile_id"
        ],
        "logical_count_plan_id": plan["logical_count_plan_id"],
        "measured_type_name": program["measured_type_name"],
        "profile_kind": program["profile_kind"],
        "operation_kind": program["operation_kind"],
        "constraint_scope": program["constraint_scope"],
        "scope_case_count": scope_case_count,
        "selector_present_scope_case_count": selector_present_scope_case_count,
        "application_invocation_count": schedule["application_invocation_count"],
        "cross_rule_evaluation_count": schedule["cross_rule_evaluation_count"],
        "direct_cross_expression_node_count": schedule[
            "direct_cross_expression_node_count"
        ],
    }


def analyze(repository_root: pathlib.Path | str) -> dict[str, Any]:
    root = pathlib.Path(repository_root)
    seed = _load_pinned(root, SEED_RELATIVE_PATH, SEED_RAW_SHA256)
    inventory = _load_pinned(root, INVENTORY_RELATIVE_PATH, INVENTORY_RAW_SHA256)
    recipe = seed["logical_plan_recipe_catalog"]

    programs = _contiguous_positions(
        recipe["ordered_profile_conditioning_program_records"],
        "program_position",
        "profile programs",
    )
    _require(len(programs) == 408, "profile program count differs")
    profiles = _contiguous_positions(
        inventory["operation_contracts"]["maximum_constraint_scope_profile_catalog"],
        "profile_position",
        "inventory profiles",
    )
    _require(len(profiles) == len(programs), "profile inventory count differs")
    plans = _index(
        recipe["ordered_logical_count_plan_records"],
        "case_position",
        475,
        "logical plans",
    )
    bindings = _index(
        recipe["ordered_case_plan_bindings"],
        "case_position",
        475,
        "case-plan bindings",
    )
    _require(set(plans) == set(range(1, 476)), "logical-plan positions differ")
    _require(set(bindings) == set(range(1, 476)), "case-plan positions differ")

    cell_contract = recipe["profile_conditioned_cell_contract"]
    _require(
        cell_contract["p2_cell_kind_enum"]
        == ["SUPERSET_UPPER_BOUND", "EXACT_ATTAINED_MAXIMUM"]
        and cell_contract["generic_superset_attainability_claimed"] is False
        and cell_contract["structural_bound_only_acceptance_forbidden"] is True
        and cell_contract["unresolved_or_unattained_policy"] == "NO_GO",
        "profile-conditioned cell contract differs",
    )

    affected: list[dict[str, Any]] = []
    exact: list[dict[str, Any]] = []
    selector_present_total = 0
    rule_ids: set[str] = set()
    safe_relaxation_ids: set[str] = set()
    deleted_cross_application_count = 0
    total_scope_cases = 0

    for position, (program, profile) in enumerate(
        zip(programs, profiles, strict=True),
        1,
    ):
        _require(
            program["program_position"]
            == program["profile_position"]
            == profile["profile_position"]
            == position,
            f"program/profile position differs: {position}",
        )
        _require(
            program["case_position"] == position + 66,
            f"program case mapping differs: {position}",
        )
        expected_pointer = (
            "/operation_contracts/maximum_constraint_scope_profile_catalog/"
            f"{position - 1}"
        )
        _require(
            program["profile_inventory_json_pointer"] == expected_pointer,
            f"program profile pointer differs: {position}",
        )
        for name in (
            "maximum_constraint_scope_profile_id",
            "profile_kind",
            "constraint_scope",
            "operation_kind",
            "measured_type_name",
        ):
            _require(
                program[name] == profile[name],
                f"program/profile {name} differs: {position}",
            )

        case_position = program["case_position"]
        plan = plans[case_position]
        binding = bindings[case_position]
        _require(
            binding["logical_count_plan_id"] == plan["logical_count_plan_id"],
            f"case-plan binding differs: {case_position}",
        )
        _require(
            plan["profile_conditioning_program_id"]
            == plan["logical_root_reference"]["root_id"]
            == program["profile_conditioning_program_id"]
            and plan["logical_root_reference"]["root_kind"]
            == "PROFILE_CONDITIONING_PROGRAM",
            f"program/plan root binding differs: {case_position}",
        )
        _require(
            plan["case_binding"]["constraint_scope_profile_id"]
            == program["maximum_constraint_scope_profile_id"]
            and plan["case_binding"]["row_kind"] == program["profile_kind"]
            and plan["case_binding"]["type_name"] == program["measured_type_name"],
            f"program/plan profile binding differs: {case_position}",
        )

        _validate_p1_p3(program)
        scope_count, selector_count, scheduled_ids = _validate_schedule(program)
        total_scope_cases += scope_count
        selector_present_total += selector_count
        schedule = program["application_schedule_operation"]
        rule_ids.update(
            instruction["rule_id"]
            for segment in schedule["ordered_schedule_segment_records"]
            for instruction in segment["ordered_application_instruction_records"]
        )

        p2 = program["conditioning_transfer_program"]["p2_upper_bound_program"]
        strategy = program["conditioning_strategy"]
        if strategy == GENERIC_STRATEGY:
            _require(
                p2["upper_bound_source"] == GENERIC_P2_SOURCE
                and p2["generic_attainability_claimed"] is False,
                f"generic P2 source/claim differs: {case_position}",
            )
            instructions = _contiguous_positions(
                p2["ordered_instruction_records"],
                "instruction_position",
                f"program {position} generic P2 instructions",
            )
            _require(
                len(instructions) == 1
                and instructions[0]["opcode"]
                == "LOAD_STRUCTURAL_TEMPLATE_SUPERSET_CELL_V1"
                and instructions[0]["output_type"] == "P2_SUPERSET_BOUND_CELL"
                and p2["root_instruction_position"] == 1,
                f"generic structural-only P2 differs: {case_position}",
            )
            deletion_rows = _contiguous_positions(
                p2["ordered_deleted_cross_application_references"],
                "deletion_position",
                f"program {position} deleted cross applications",
            )
            deleted_ids = {row["rule_application_id"] for row in deletion_rows}
            _require(
                deleted_ids == scheduled_ids and len(deleted_ids) == len(deletion_rows),
                f"generic cross-application deletion coverage differs: {case_position}",
            )
            _require(
                plan["upper_bound_mode"] == PLAN_GENERIC_MODE,
                f"generic plan upper-bound mode differs: {case_position}",
            )
            deleted_cross_application_count += len(deletion_rows)
            safe_relaxation_ids.update(p2["ordered_safe_relaxation_rule_ids"])
            affected.append(
                _affected_row(
                    program,
                    plan,
                    scope_count,
                    selector_count,
                )
            )
        elif strategy == EXACT_STRATEGY:
            _require(
                case_position == 69
                and position == 3
                and p2["upper_bound_source"] == EXACT_P2_SOURCE
                and p2["generic_attainability_claimed"] is None
                and plan["upper_bound_mode"] == PLAN_EXACT_MODE,
                "exact analytic control differs",
            )
            instructions = _contiguous_positions(
                p2["ordered_instruction_records"],
                "instruction_position",
                "exact analytic P2 instructions",
            )
            _require(
                instructions[-1]["output_type"] == "P2_EXACT_ATTAINED_CELL"
                and p2["root_instruction_position"]
                == instructions[-1]["instruction_position"],
                "exact analytic P2 result differs",
            )
            _require(
                p2["ordered_deleted_cross_application_references"] == []
                and p2["ordered_safe_relaxation_rule_ids"] == [],
                "exact analytic relaxation differs",
            )
            exact.append(
                _affected_row(
                    program,
                    plan,
                    scope_count,
                    selector_count,
                )
            )
        else:
            raise ProfileScopeAuditError(f"unknown conditioning strategy: {strategy}")

    _require(total_scope_cases == 475, "total profile scope-case count differs")
    _require(len(affected) == 407 and len(exact) == 1, "strategy census differs")
    _require(
        sum(row["scope_case_count"] for row in affected) == 474,
        "affected scope-case count differs",
    )
    _require(
        exact[0]["case_position"] == 69 and exact[0]["scope_case_count"] == 1,
        "exact control case differs",
    )
    _require(
        any(row["case_position"] == 435 for row in affected),
        "case 435 is absent from affected profiles",
    )

    affected_case_positions = [row["case_position"] for row in affected]
    affected_profile_ids = [
        row["maximum_constraint_scope_profile_id"] for row in affected
    ]
    affected_program_ids = [row["profile_conditioning_program_id"] for row in affected]
    groups = _group_records(affected)
    payload: dict[str, Any] = {
        "audit_version": (
            "riskyieldmm.raw_v8_step2.maximum_protocol_v2."
            "profile_attainability_scope_audit.v1"
        ),
        "seed_catalog_id": seed["seed_catalog_id"],
        "logical_plan_recipe_catalog_id": recipe["logical_plan_recipe_catalog_id"],
        "seed_raw_sha256": SEED_RAW_SHA256,
        "inventory_raw_sha256": INVENTORY_RAW_SHA256,
        "profile_program_count": len(programs),
        "profile_scope_case_count": total_scope_cases,
        "p1_p3_exact_equality_program_count": len(programs),
        "application_aware_exact_program_count": len(exact),
        "application_aware_exact_scope_case_count": exact[0]["scope_case_count"],
        "exact_control_case_position": exact[0]["case_position"],
        "structural_superset_program_count": len(affected),
        "structural_superset_scope_case_count": sum(
            row["scope_case_count"] for row in affected
        ),
        "structural_superset_selector_present_scope_case_count": selector_present_total
        - exact[0]["selector_present_scope_case_count"],
        "structural_superset_selector_absent_scope_case_count": sum(
            row["scope_case_count"] for row in affected
        )
        - (selector_present_total - exact[0]["selector_present_scope_case_count"]),
        "structural_superset_deleted_cross_application_count": (
            deleted_cross_application_count
        ),
        "structural_superset_application_invocation_count": sum(
            row["application_invocation_count"] for row in affected
        ),
        "structural_superset_cross_rule_evaluation_count": sum(
            row["cross_rule_evaluation_count"] for row in affected
        ),
        "structural_superset_direct_cross_expression_node_count": sum(
            row["direct_cross_expression_node_count"] for row in affected
        ),
        "affected_publication_case_minimum": min(affected_case_positions),
        "affected_publication_case_maximum": max(affected_case_positions),
        "case435_is_affected": True,
        "current_catalog_satisfies_application_aware_exactness": False,
        "required_disposition": (
            "NO_GO_UNTIL_EACH_GENERIC_PROFILE_HAS_A_PROVED_LEGAL_UPPER_BOUND_"
            "AND_AN_INDEPENDENT_LEGAL_ATTAINER"
        ),
        "selected_correction_contract": CORRECTION_CONTRACT,
        "selected_correction_contract_id": _sha256(
            _canonical_bytes(
                {
                    "domain": CORRECTION_CONTRACT_DOMAIN,
                    "payload": CORRECTION_CONTRACT,
                }
            )
        ),
        "ordered_affected_group_records": groups,
        "ordered_cross_rule_ids": sorted(rule_ids),
        "ordered_safe_relaxation_rule_ids": sorted(safe_relaxation_ids),
        "affected_case_position_vector_sha256": _sha256(
            _canonical_bytes(affected_case_positions)
        ),
        "affected_profile_id_vector_sha256": _sha256(
            _canonical_bytes(affected_profile_ids)
        ),
        "affected_program_id_vector_sha256": _sha256(
            _canonical_bytes(affected_program_ids)
        ),
        "affected_profile_record_vector_sha256": _sha256(_canonical_bytes(affected)),
    }
    payload["profile_attainability_scope_audit_id"] = _sha256(
        _canonical_bytes({"domain": AUDIT_DOMAIN, "payload": payload})
    )
    return payload


def require_corrected_application_aware_contract(
    report: dict[str, Any],
) -> None:
    """Fail until every equality-qualified profile has an exact P2 proof.

    This is the fail-first correction boundary.  It intentionally rejects the
    accepted V1 catalog without modifying that immutable authority.
    """

    _require(
        report["current_catalog_satisfies_application_aware_exactness"] is True,
        "A4_P6_C435_APPLICATION_AWARE_EXACTNESS_NOT_IMPLEMENTED: "
        f"{report['structural_superset_program_count']} programs / "
        f"{report['structural_superset_scope_case_count']} scope cases remain",
    )


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) > 1:
        raise SystemExit("usage: check...py [repository-root]")
    root = (
        pathlib.Path(arguments[0]).resolve()
        if arguments
        else pathlib.Path(__file__).parents[2]
    )
    try:
        result = analyze(root)
    except ProfileScopeAuditError as error:
        sys.stderr.write(f"PROFILE_ATTAINABILITY_SCOPE_REJECT: {error}\n")
        return 1
    sys.stdout.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

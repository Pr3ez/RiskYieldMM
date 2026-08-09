"""Independent executable contract for the Raw V8 Step-2 V2 cell transfer.

This file intentionally does not import the seed-catalog generator.  The small
interpreter and its micro-oracles are an independently authored design oracle.
The catalog-conformance test is expected to fail until the candidate catalog
publishes the complete typed opcode contracts described here.

The transfer is bottom-up.  A child is never pruned by an inferred ancestor
residual.  A CODEC_INTERSECTION node applies a structured self or owner-payload
coordinate to an already computed abstract interval.  This matters because a
max-only child summary cannot prove that a shorter value needed by an ancestor
cap is attainable; retaining both a certified lower and upper bound is sound.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SEED_CATALOG_PATH = (
    REPOSITORY_ROOT
    / "scripts/tests/raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.json"
)
STRUCTURAL_REGISTRY_PATH = (
    REPOSITORY_ROOT
    / "scripts/tests/raw_v8_step2_external_schema_v2_structural_registry_v49f.json"
)
INVENTORY_PATH = REPOSITORY_ROOT / "tests/raw_v8_step2_inventory_v4_v49f.json"

U128_MAX = (1 << 128) - 1
IJSON_SAFE_INTEGER_MAX = 9_007_199_254_740_991

MAY_BE_NONEMPTY = "MAY_BE_NONEMPTY"
PROVABLY_EMPTY = "PROVABLY_EMPTY"


class TransferReject(ValueError):
    """The transfer input is not a member of the frozen typed grammar."""


@dataclass(frozen=True)
class Cell:
    status: str
    lower: int
    upper: int
    state: tuple[Any, ...] = ()


@dataclass(frozen=True)
class CappedU128:
    value: int
    exceeded_ceiling: bool


def _is_plain_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def u128(value: object, *, name: str = "value") -> int:
    if not _is_plain_int(value) or not 0 <= value <= U128_MAX:
        raise TransferReject(f"{name} is not UInt128")
    return value


def checked_add(*values: int) -> int:
    total = 0
    for position, value in enumerate(values, 1):
        value = u128(value, name=f"addend[{position}]")
        if value > U128_MAX - total:
            raise TransferReject("UInt128 addition overflow")
        total += value
    return total


def checked_sub(left: int, right: int) -> int:
    left = u128(left, name="minuend")
    right = u128(right, name="subtrahend")
    if right > left:
        raise TransferReject("UInt128 subtraction underflow")
    return left - right


def checked_mul(left: int, right: int) -> int:
    left = u128(left, name="multiplicand")
    right = u128(right, name="multiplier")
    if left and right > U128_MAX // left:
        raise TransferReject("UInt128 multiplication overflow")
    return left * right


def capped_add(ceiling: int, *values: int) -> CappedU128:
    """Add without overflowing; distinguish exact ceiling from saturation."""

    ceiling = u128(ceiling, name="ceiling")
    total = 0
    for position, value in enumerate(values, 1):
        value = u128(value, name=f"capped_addend[{position}]")
        if total > ceiling or value > ceiling - total:
            return CappedU128(ceiling, True)
        total += value
    return CappedU128(total, False)


def capped_mul(ceiling: int, left: int, right: int) -> CappedU128:
    """Multiply without overflowing; distinguish exact ceiling from saturation."""

    ceiling = u128(ceiling, name="ceiling")
    left = u128(left, name="capped_multiplicand")
    right = u128(right, name="capped_multiplier")
    if left > ceiling or (left and right > ceiling // left):
        return CappedU128(ceiling, True)
    return CappedU128(left * right, False)


def empty(*, state: Sequence[Any] = ()) -> Cell:
    return Cell(PROVABLY_EMPTY, 0, 0, tuple(state))


def nonempty(
    lower: int,
    upper: int,
    ceiling: int,
    *,
    state: Sequence[Any] = (),
) -> Cell:
    lower = u128(lower, name="certified_lower_bound_octets")
    upper = u128(upper, name="certified_upper_bound_octets")
    ceiling = u128(ceiling, name="effective_canonical_octet_ceiling")
    if not lower <= upper <= ceiling:
        raise TransferReject("nonempty cell violates 0 <= lower <= upper <= ceiling")
    return Cell(MAY_BE_NONEMPTY, lower, upper, tuple(state))


def validate_cell(cell: Cell, ceiling: int) -> Cell:
    ceiling = u128(ceiling, name="effective_canonical_octet_ceiling")
    if cell.status == PROVABLY_EMPTY:
        if (cell.lower, cell.upper) != (0, 0):
            raise TransferReject("empty cell is not in the (0, 0) normal form")
        return cell
    if cell.status != MAY_BE_NONEMPTY:
        raise TransferReject("unknown cell status")
    return nonempty(cell.lower, cell.upper, ceiling, state=cell.state)


def _clip_raw_bounds(
    raw_lower: int,
    raw_upper: int,
    ceiling: int,
    *,
    state: Sequence[Any] = (),
) -> Cell:
    raw_lower = u128(raw_lower, name="raw_lower")
    raw_upper = u128(raw_upper, name="raw_upper")
    ceiling = u128(ceiling, name="effective_canonical_octet_ceiling")
    if raw_lower > raw_upper:
        raise TransferReject("raw lower exceeds raw upper")
    if raw_lower > ceiling:
        return empty(state=state)
    # The clipped endpoint is an abstract upper bound.  No claim that every
    # intermediate length, or the clipped endpoint itself, is attainable.
    return nonempty(raw_lower, min(raw_upper, ceiling), ceiling, state=state)


def _clip_cell(child: Cell, ceiling: int) -> Cell:
    validate_cell(child, U128_MAX)
    if child.status == PROVABLY_EMPTY:
        return child
    return _clip_raw_bounds(
        child.lower,
        child.upper,
        ceiling,
        state=child.state,
    )


def canonical_string_octets(value: object) -> int:
    if not isinstance(value, str):
        raise TransferReject("finite text member is not TEXT")
    try:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        return len(encoded.encode("utf-8"))
    except (UnicodeEncodeError, ValueError) as exc:
        raise TransferReject("text is not an encodable I-JSON string") from exc


def transfer_fixed(octets: int, ceiling: int) -> Cell:
    octets = u128(octets, name="fixed_canonical_octets")
    return _clip_raw_bounds(octets, octets, ceiling)


def transfer_boolean(literal: bool | None, ceiling: int) -> Cell:
    ceiling = u128(ceiling, name="effective_canonical_octet_ceiling")
    if literal is None:  # Exact sentinel: the full {false, true} domain.
        admitted = [length for length in (4, 5) if length <= ceiling]
    elif literal is True:
        admitted = [4] if 4 <= ceiling else []
    elif literal is False:
        admitted = [5] if 5 <= ceiling else []
    else:
        raise TransferReject("boolean_literal is not BOOLEAN or null sentinel")
    return nonempty(min(admitted), max(admitted), ceiling) if admitted else empty()


def _safe_integer(value: object, *, name: str) -> int:
    if not _is_plain_int(value) or not (
        -IJSON_SAFE_INTEGER_MAX <= value <= IJSON_SAFE_INTEGER_MAX
    ):
        raise TransferReject(f"{name} is not a signed I-JSON safe integer")
    return value


def transfer_safe_integer(
    integer_minimum: int, integer_maximum: int, ceiling: int
) -> Cell:
    lower_endpoint = _safe_integer(integer_minimum, name="integer_minimum")
    upper_endpoint = _safe_integer(integer_maximum, name="integer_maximum")
    if lower_endpoint > upper_endpoint:
        raise TransferReject("integer interval is inverted")

    nearest_zero = (
        0
        if lower_endpoint <= 0 <= upper_endpoint
        else lower_endpoint
        if lower_endpoint > 0
        else upper_endpoint
    )
    raw_lower = len(str(nearest_zero).encode("ascii"))
    raw_upper = max(
        len(str(lower_endpoint).encode("ascii")),
        len(str(upper_endpoint).encode("ascii")),
    )
    return _clip_raw_bounds(raw_lower, raw_upper, ceiling)


def transfer_finite_text(ordered_literals: Sequence[str], ceiling: int) -> Cell:
    ceiling = u128(ceiling, name="effective_canonical_octet_ceiling")
    if isinstance(ordered_literals, (str, bytes)):
        raise TransferReject("ordered_literals is not an ordered text array")
    lengths = [canonical_string_octets(value) for value in ordered_literals]
    admitted = [length for length in lengths if length <= ceiling]
    return nonempty(min(admitted), max(admitted), ceiling) if admitted else empty()


def transfer_bounded_text(
    minimum_canonical_octets: int,
    maximum_canonical_octets: int,
    ceiling: int,
) -> Cell:
    minimum = u128(minimum_canonical_octets, name="minimum_canonical_octets")
    maximum = u128(maximum_canonical_octets, name="maximum_canonical_octets")
    if minimum > maximum:
        raise TransferReject("bounded text interval is inverted")
    return _clip_raw_bounds(minimum, maximum, ceiling)


def transfer_relaxed_json_string(ceiling: int) -> Cell:
    ceiling = u128(ceiling, name="effective_canonical_octet_ceiling")
    # The safe language relaxation is all canonical JSON strings admitted by
    # the effective byte ceiling.  The empty string proves non-emptiness at 2.
    return empty() if ceiling < 2 else nonempty(2, ceiling, ceiling)


def transfer_nullable(child: Cell, ceiling: int) -> Cell:
    ceiling = u128(ceiling, name="effective_canonical_octet_ceiling")
    child = _clip_cell(child, ceiling)
    intervals: list[tuple[int, int]] = []
    if 4 <= ceiling:  # canonical `null`
        intervals.append((4, 4))
    if child.status == MAY_BE_NONEMPTY:
        intervals.append((child.lower, child.upper))
    if not intervals:
        return empty()
    return nonempty(
        min(item[0] for item in intervals),
        max(item[1] for item in intervals),
        ceiling,
    )


def transfer_alias(child: Cell, ceiling: int) -> Cell:
    return _clip_cell(child, ceiling)


def _array_capped_length(
    cardinality: int, item_octets: int, ceiling: int
) -> CappedU128:
    cardinality = u128(cardinality, name="array_cardinality")
    item_octets = u128(item_octets, name="item_octets")
    ceiling = u128(ceiling, name="effective_canonical_octet_ceiling")
    commas = checked_sub(cardinality, 1) if cardinality else 0
    item_sum = capped_mul(ceiling, cardinality, item_octets)
    if item_sum.exceeded_ceiling:
        return CappedU128(ceiling, True)
    return capped_add(ceiling, 2, item_sum.value, commas)


def transfer_array(
    child: Cell,
    minimum_items: int,
    maximum_items: int,
    ceiling: int,
    *,
    mode: str,
) -> Cell:
    minimum_items = u128(minimum_items, name="minimum_items")
    maximum_items = u128(maximum_items, name="maximum_items")
    ceiling = u128(ceiling, name="effective_canonical_octet_ceiling")
    if minimum_items > maximum_items:
        raise TransferReject("array cardinality interval is inverted")
    if mode not in {"BATCH", "STREAM"}:
        raise TransferReject("unknown homogeneous-array evaluation mode")

    # A nonempty array requires a nonempty item domain; the zero-cardinality
    # value remains legal independently of the child.
    if child.status == PROVABLY_EMPTY:
        return _clip_raw_bounds(2, 2, ceiling) if minimum_items == 0 else empty()
    child = validate_cell(child, U128_MAX)
    bounded_lower = _array_capped_length(minimum_items, child.lower, ceiling)
    if bounded_lower.exceeded_ceiling:
        return empty()
    bounded_upper = _array_capped_length(maximum_items, child.upper, ceiling)
    item_upper_sum = capped_mul(ceiling, maximum_items, child.upper).value
    comma_count = checked_sub(maximum_items, 1) if maximum_items else 0
    state = (
        (maximum_items, item_upper_sum, comma_count)
        if mode == "BATCH"
        else (maximum_items, maximum_items, item_upper_sum, comma_count)
    )
    return nonempty(
        bounded_lower.value,
        bounded_upper.value,
        ceiling,
        state=state,
    )


def transfer_record(
    ordered_children: Sequence[Cell],
    syntax_octets_excluding_child_values: int,
    ceiling: int,
) -> Cell:
    syntax = u128(
        syntax_octets_excluding_child_values,
        name="record_syntax_octets_excluding_child_values",
    )
    children = [validate_cell(child, U128_MAX) for child in ordered_children]
    if any(child.status == PROVABLY_EMPTY for child in children):
        return empty()
    bounded_lower = capped_add(ceiling, syntax, *(child.lower for child in children))
    if bounded_lower.exceeded_ceiling:
        return empty()
    bounded_upper = capped_add(ceiling, syntax, *(child.upper for child in children))
    return nonempty(bounded_lower.value, bounded_upper.value, ceiling)


def transfer_union(ordered_alternatives: Sequence[Cell], ceiling: int) -> Cell:
    ceiling = u128(ceiling, name="effective_canonical_octet_ceiling")
    admitted = [
        _clip_cell(child, ceiling)
        for child in ordered_alternatives
        if child.status != PROVABLY_EMPTY and child.lower <= ceiling
    ]
    if not admitted:
        return empty()
    return nonempty(
        min(child.lower for child in admitted),
        max(child.upper for child in admitted),
        ceiling,
    )


def _inclusive_codec_ceiling(coordinate: Mapping[str, Any]) -> int:
    limit = u128(coordinate.get("codec_octet_limit"), name="codec_octet_limit")
    relation = coordinate.get("codec_byte_bound_relation")
    if relation == "LE":
        return limit
    if relation == "LT":
        return checked_sub(limit, 1)
    raise TransferReject("codec relation is not LE or LT")


def derive_coordinate_payload_ceiling(coordinate: Mapping[str, Any]) -> int:
    required = {
        "codec_byte_bound_relation",
        "codec_octet_limit",
        "coordinate_scope",
        "minimum_sibling_and_syntax_octets",
        "derived_payload_octet_ceiling",
    }
    if not required <= coordinate.keys():
        raise TransferReject("codec coordinate omits a residual operand")
    inclusive = _inclusive_codec_ceiling(coordinate)
    overhead = u128(
        coordinate["minimum_sibling_and_syntax_octets"],
        name="minimum_sibling_and_syntax_octets",
    )
    scope = coordinate["coordinate_scope"]
    if scope == "SELF_TYPE" and overhead != 0:
        raise TransferReject("SELF_TYPE coordinate has nonzero owner overhead")
    if scope not in {"SELF_TYPE", "OWNER_PAYLOAD_RESIDUAL"}:
        raise TransferReject("unknown codec coordinate scope")
    derived = checked_sub(inclusive, overhead)
    # Never trust a precomputed residual: recompute and compare it.
    if coordinate["derived_payload_octet_ceiling"] != derived:
        raise TransferReject("stored owner residual is not derivable")
    return derived


def transfer_codec_intersection(
    child: Cell,
    ordered_coordinates: Sequence[Mapping[str, Any]],
    ambient_ceiling: int,
) -> Cell:
    if not ordered_coordinates:
        raise TransferReject("codec intersection has no coordinates")
    effective = min(
        u128(ambient_ceiling, name="ambient_ceiling"),
        *(derive_coordinate_payload_ceiling(item) for item in ordered_coordinates),
    )
    if child.status == PROVABLY_EMPTY or child.lower > effective:
        return empty(state=child.state)
    child = validate_cell(child, U128_MAX)
    return nonempty(
        child.lower,
        min(child.upper, effective),
        effective,
        state=child.state,
    )


def transfer_validated_alias(
    child: Cell, ceiling: int, *, evidence_valid: bool
) -> Cell:
    if evidence_valid is not True:
        raise TransferReject("bound-preserving wrapper evidence did not validate")
    return transfer_alias(child, ceiling)


def transfer_derived_upper_intersection(
    child: Cell,
    ceiling: int,
    *,
    independently_derived_upper: int,
) -> Cell:
    """Intersect with an executed P2 result, never a detached expected value."""

    derived = u128(
        independently_derived_upper,
        name="independently_derived_profile_upper_octets",
    )
    return _clip_cell(child, min(u128(ceiling, name="ceiling"), derived))


def transfer_local_shutdown(
    local_catalog: Mapping[str, Any],
    ceiling: int,
) -> Cell:
    states = local_catalog.get("ordered_controller_state_records")
    transitions = local_catalog.get("ordered_controller_transition_records")
    if not isinstance(states, list) or not isinstance(transitions, list):
        raise TransferReject("local controller is not materialized")
    if len(states) != 12 or len(transitions) != 11:
        raise TransferReject(
            "local controller is not exactly 12 states / 11 transitions"
        )
    if [row.get("controller_state_position") for row in states] != list(range(1, 13)):
        raise TransferReject("local state positions are not contiguous")
    if [row.get("controller_transition_position") for row in transitions] != list(
        range(1, 12)
    ):
        raise TransferReject("local transition positions are not contiguous")
    for index, transition in enumerate(transitions):
        if transition.get("source_controller_state_id") != states[index].get(
            "controller_state_id"
        ):
            raise TransferReject("local transition source is not the preceding state")
        if transition.get("target_controller_state_id") != states[index + 1].get(
            "controller_state_id"
        ):
            raise TransferReject("local transition target is not the following state")
        if transition.get("expected_target_state_components") != states[index + 1].get(
            "ordered_state_components"
        ):
            raise TransferReject("local transition does not reproduce its target state")

    terminal = states[-1]
    if terminal.get("state_kind") != "TERMINAL":
        raise TransferReject("local controller has no terminal final state")
    components = terminal.get("ordered_state_components")
    if not isinstance(components, list) or len(components) != 8:
        raise TransferReject(
            "local terminal state does not match the 8-component signature"
        )
    winner = u128(components[7], name="best_candidate_attainable_maximum_octets")
    if winner != local_catalog.get("winner_attainable_maximum_octets"):
        raise TransferReject("local terminal winner disagrees with the catalog summary")
    return _clip_raw_bounds(winner, winner, ceiling, state=components)


# This is the exact typed surface the seed catalog must publish.  The semantic
# rule names are opcodes, not prose formulas; their complete behavior is the
# executable interpreter above.  Parameters remain in the derivation-kernel
# records and children are read only by strict earlier postorder positions.
EXPECTED_TRANSFER_OPCODE_CONTRACTS: dict[str, dict[str, Any]] = {
    "CELL_FIXED_OCTETS_V1": {
        "semantic_rule": "FIXED_EXACT_OR_EMPTY_V1",
        "ordered_required_parameter_names": ["fixed_canonical_octets"],
        "child_read_mode": "NONE",
        "state_rule": "EMPTY_SIGNATURE_V1",
    },
    "CELL_BOOLEAN_LITERAL_V1": {
        "semantic_rule": "BOOLEAN_LITERAL_OR_FULL_DOMAIN_SENTINEL_V1",
        "ordered_required_parameter_names": ["boolean_literal"],
        "child_read_mode": "NONE",
        "state_rule": "EMPTY_SIGNATURE_V1",
    },
    "CELL_SAFE_INTEGER_INTERVAL_V1": {
        "semantic_rule": "SIGNED_SAFE_INTEGER_ENDPOINT_AND_NEAREST_ZERO_V1",
        "ordered_required_parameter_names": [
            "integer_minimum",
            "integer_maximum",
            "ordered_probe_values",
        ],
        "child_read_mode": "NONE",
        "state_rule": "EMPTY_SIGNATURE_V1",
    },
    "CELL_FINITE_TEXT_V1": {
        "semantic_rule": "FINITE_CANONICAL_STRING_LENGTH_EXTREMA_V1",
        "ordered_required_parameter_names": [
            "text_language_position",
            "text_language_id",
            "ordered_literals",
        ],
        "child_read_mode": "NONE",
        "state_rule": "EMPTY_SIGNATURE_V1",
    },
    "CELL_BOUNDED_TEXT_OCTETS_V1": {
        "semantic_rule": "BOUNDED_CANONICAL_STRING_OCTET_INTERVAL_V1",
        "ordered_required_parameter_names": [
            "built_in_language_kind",
            "minimum_canonical_octets",
            "maximum_canonical_octets",
            "text_language_id",
            "text_language_position",
        ],
        "child_read_mode": "NONE",
        "state_rule": "EMPTY_SIGNATURE_V1",
    },
    "CELL_RELAXED_JSON_STRING_V1": {
        "semantic_rule": "ALL_CANONICAL_JSON_STRINGS_UNDER_EFFECTIVE_CEILING_V1",
        "ordered_required_parameter_names": [
            "text_language_position",
            "text_language_id",
            "language_kind",
            "built_in_language_kind",
            "ascii_dfa_id",
            "unicode_identifier_profile_id",
            "minimum_utf8_octets",
            "maximum_utf8_octets",
            "minimum_decoded_octets",
            "maximum_decoded_octets",
            "decimal_maximum",
        ],
        "child_read_mode": "NONE",
        "state_rule": "EMPTY_SIGNATURE_V1",
    },
    "CELL_DERIVED_IDENTITY_V1": {
        "semantic_rule": "FIXED_EXACT_OR_EMPTY_V1",
        "ordered_required_parameter_names": ["canonical_octets"],
        "child_read_mode": "NONE",
        "state_rule": "EMPTY_SIGNATURE_V1",
    },
    "CELL_NULLABLE_V1": {
        "semantic_rule": "NULL_LITERAL_AND_NON_NULL_CHILD_UNION_V1",
        "ordered_required_parameter_names": ["child_step_position"],
        "child_read_mode": "ONE_EARLIER_POSITION_V1",
        "state_rule": "EMPTY_SIGNATURE_V1",
    },
    "CELL_CHILD_BOUNDS_ALIAS_V1": {
        "semantic_rule": "VALIDATED_CHILD_BOUNDS_ALIAS_V1",
        "ordered_required_parameter_names": [
            "referenced_type_name",
            "child_step_position",
        ],
        "child_read_mode": "ONE_EARLIER_POSITION_V1",
        "state_rule": "PRESERVE_CHILD_STATE_V1",
    },
    "CELL_ARRAY_BATCH_V1": {
        "semantic_rule": "HOMOGENEOUS_ARRAY_CLOSED_INTERVAL_V1",
        "ordered_required_parameter_names": [
            "minimum_items",
            "maximum_items",
            "item_value_schema_id",
            "item_step_position",
            "ordered_run_records",
            "observer_closure_record",
        ],
        "child_read_mode": "ONE_EARLIER_POSITION_V1",
        "state_rule": "BATCH_ITEM_SUMMARY_V1",
    },
    "CELL_ARRAY_STREAM_V1": {
        "semantic_rule": "HOMOGENEOUS_ARRAY_CLOSED_INTERVAL_V1",
        "ordered_required_parameter_names": [
            "minimum_items",
            "maximum_items",
            "item_step_position",
        ],
        "child_read_mode": "ONE_EARLIER_POSITION_V1",
        "state_rule": "STREAM_ITEM_SUMMARY_V1",
    },
    "CELL_RECORD_V1": {
        "semantic_rule": "RECORD_SYNTAX_PLUS_ORDERED_CHILD_SUM_V1",
        "ordered_required_parameter_names": [
            "record_member_count",
            "ordered_member_records",
            "record_syntax_octets_excluding_child_values",
        ],
        "child_read_mode": "ORDERED_MEMBER_EARLIER_POSITIONS_V1",
        "state_rule": "EMPTY_SIGNATURE_V1",
    },
    "CELL_UNION_V1": {
        "semantic_rule": "ORDERED_NONEMPTY_ALTERNATIVE_INTERVAL_UNION_V1",
        "ordered_required_parameter_names": [
            "ordered_alternative_records",
            "owner_type_name",
            "owner_typed_member_path",
        ],
        "child_read_mode": "ORDERED_ALTERNATIVE_EARLIER_POSITIONS_V1",
        "state_rule": "EMPTY_SIGNATURE_V1",
    },
    "CELL_CODEC_INTERSECTION_V1": {
        "semantic_rule": "RECOMPUTED_CODEC_RESIDUAL_INTERSECTION_V1",
        "ordered_required_parameter_names": [
            "ordered_codec_coordinate_records",
            "child_step_position",
        ],
        "child_read_mode": "ONE_EARLIER_POSITION_V1",
        "state_rule": "PRESERVE_CHILD_STATE_V1",
    },
    "CELL_SAFE_RELAXATION_V1": {
        "semantic_rule": "VALIDATED_BOUND_PRESERVING_ALIAS_V1",
        "ordered_required_parameter_names": [
            "safe_relaxation_rule_id",
            "authority_predicate_locator",
            "child_step_position",
        ],
        "child_read_mode": "ONE_EARLIER_POSITION_V1",
        "state_rule": "PRESERVE_CHILD_STATE_V1",
    },
    "CELL_SCOPE_ROOT_V1": {
        "semantic_rule": "VALIDATED_BOUND_PRESERVING_ALIAS_V1",
        "ordered_required_parameter_names": [
            "case_binding",
            "fixed_authority_bindings",
            "child_step_position",
        ],
        "child_read_mode": "ONE_EARLIER_POSITION_V1",
        "state_rule": "PRESERVE_CHILD_STATE_V1",
    },
    "CELL_APPLICATION_WRAPPER_V1": {
        "semantic_rule": "VALIDATED_BOUND_PRESERVING_ALIAS_V1",
        "ordered_required_parameter_names": [
            "ordered_application_invocation_records",
            "child_step_position",
        ],
        "child_read_mode": "ONE_EARLIER_POSITION_V1",
        "state_rule": "PRESERVE_CHILD_STATE_V1",
    },
    "CELL_LOCAL_SHUTDOWN_SWEEP_V2": {
        "semantic_rule": "EXACT_CHAINED_LOCAL_CONTROLLER_TERMINAL_WINNER_V2",
        "ordered_required_parameter_names": ["local_shutdown_analytic_catalog_id"],
        "child_read_mode": "RESOLVE_BOUND_LOCAL_CATALOG_V1",
        "state_rule": "LOCAL_TERMINAL_EIGHT_COMPONENT_STATE_V1",
    },
}


# Closed, low-level transfer-rule AST.  A catalog rule is executable only via
# these primitives; high-level semantic labels are diagnostics, not programs.
AST_OPCODE_SIGNATURES: dict[str, tuple[list[str], str, str]] = {
    "CONST_V1": (["value"], "NONE", "LITERAL"),
    "PARAM_V1": (["parameter_name"], "NONE", "PARAMETER_VALUE"),
    "CHILD_V1": (["zero_based_index"], "NONE", "CELL"),
    "CHILDREN_V1": ([], "NONE", "CELL_LIST"),
    "CEILING_V1": ([], "NONE", "U128"),
    "VAR_V1": (["variable_name"], "NONE", "BOUND_VALUE"),
    "LET_V1": (
        ["ordered_bindings", "result_expression"],
        "SEQUENTIAL_BINDINGS",
        "RESULT_TYPE",
    ),
    "IF_V1": (
        ["condition", "then_expression", "else_expression"],
        "BOOL,LAZY_BRANCHES",
        "COMMON_BRANCH_TYPE",
    ),
    "VALIDATE_V1": (
        ["condition", "error_code", "result_expression"],
        "BOOL,TEXT,LAZY_RESULT",
        "RESULT_TYPE",
    ),
    "EQ_V1": (["left", "right"], "SAME_TYPE", "BOOL"),
    "LE_V1": (["left", "right"], "ORDERED_SAME_TYPE", "BOOL"),
    "LT_V1": (["left", "right"], "ORDERED_SAME_TYPE", "BOOL"),
    "AND_V1": (["ordered_operands"], "BOOL_LIST", "BOOL"),
    "OR_V1": (["ordered_operands"], "BOOL_LIST", "BOOL"),
    "NOT_V1": (["operand"], "BOOL", "BOOL"),
    "IN_SET_V1": (["operand", "ordered_values"], "VALUE,LITERAL_LIST", "BOOL"),
    "IS_NULL_V1": (["operand"], "ANY", "BOOL"),
    "IS_BOOLEAN_V1": (["operand"], "ANY", "BOOL"),
    "IS_TEXT_V1": (["operand"], "ANY", "BOOL"),
    "IS_U128_V1": (["operand"], "ANY", "BOOL"),
    "IS_SIGNED_SAFE_INTEGER_V1": (["operand"], "ANY", "BOOL"),
    "IS_LIST_V1": (["operand"], "ANY", "BOOL"),
    "IS_MAPPING_V1": (["operand"], "ANY", "BOOL"),
    "IS_CELL_EMPTY_V1": (["cell"], "CELL", "BOOL"),
    "HAS_EXACT_KEYS_V1": (["mapping", "ordered_keys"], "MAPPING,TEXT_LIST", "BOOL"),
    "FIELD_V1": (["mapping", "field_name"], "MAPPING,TEXT", "ANY"),
    "INDEX_V1": (["sequence", "zero_based_index"], "SEQUENCE,U128", "ANY"),
    "LIST_V1": (["ordered_items"], "EXPRESSION_LIST", "LIST"),
    "CONCAT_V1": (["ordered_sequences"], "LIST_LIST", "LIST"),
    "LIST_LENGTH_V1": (["sequence"], "SEQUENCE", "U128"),
    "MAP_V1": (
        ["sequence", "item_variable", "map_expression"],
        "SEQUENCE,TEXT,SCOPED_EXPRESSION",
        "LIST",
    ),
    "FILTER_V1": (
        ["sequence", "item_variable", "predicate"],
        "SEQUENCE,TEXT,SCOPED_BOOL",
        "LIST",
    ),
    "ANY_V1": (
        ["sequence", "item_variable", "predicate"],
        "SEQUENCE,TEXT,SCOPED_BOOL",
        "BOOL",
    ),
    "ALL_V1": (
        ["sequence", "item_variable", "predicate"],
        "SEQUENCE,TEXT,SCOPED_BOOL",
        "BOOL",
    ),
    "ALL_INDEXED_V1": (
        ["sequence", "index_variable", "item_variable", "predicate"],
        "SEQUENCE,TEXT,TEXT,SCOPED_BOOL",
        "BOOL",
    ),
    "FOLD_MIN_U128_V1": (["sequence"], "NONEMPTY_U128_LIST", "U128"),
    "FOLD_MAX_U128_V1": (["sequence"], "NONEMPTY_U128_LIST", "U128"),
    "CHECKED_ADD_LIST_U128_V1": (["sequence"], "U128_LIST", "U128"),
    "CHECKED_SUB_U128_V1": (["left", "right"], "U128,U128", "U128"),
    "CHECKED_MUL_U128_V1": (["left", "right"], "U128,U128", "U128"),
    "CAPPED_ADD_LIST_U128_V1": (
        ["ceiling", "sequence"],
        "U128,U128_LIST",
        "CAPPED_U128",
    ),
    "CAPPED_MUL_U128_V1": (
        ["ceiling", "left", "right"],
        "U128,U128,U128",
        "CAPPED_U128",
    ),
    "CAPPED_VALUE_V1": (["capped_value"], "CAPPED_U128", "U128"),
    "CAPPED_EXCEEDED_V1": (["capped_value"], "CAPPED_U128", "BOOL"),
    "DECIMAL_OCTETS_V1": (["signed_integer"], "SIGNED_SAFE_INTEGER", "U128"),
    "CANONICAL_STRING_OCTETS_V1": (["text"], "TEXT", "U128"),
    "CELL_EMPTY_V1": (["state_expression"], "LIST", "CELL"),
    "CELL_BUILD_CLIPPED_V1": (
        ["lower", "upper", "ceiling", "state_expression"],
        "U128,U128,U128,LIST",
        "CELL",
    ),
    "CELL_BUILD_FROM_CAPPED_V1": (
        ["lower_capped", "upper_capped", "ceiling", "state_expression"],
        "CAPPED_U128,CAPPED_U128,U128,LIST",
        "CELL",
    ),
    "CELL_CLIP_V1": (["cell", "ceiling"], "CELL,U128", "CELL"),
    "CELL_LOWER_V1": (["cell"], "CELL", "U128"),
    "CELL_UPPER_V1": (["cell"], "CELL", "U128"),
    "CELL_STATE_V1": (["cell"], "CELL", "LIST"),
    "CALL_RULE_V1": (
        ["transfer_rule_id", "ordered_argument_bindings"],
        "SHA256_RULE_ID,TYPED_ARGUMENT_BINDINGS",
        "RULE_RESULT_TYPE",
    ),
    "RESOLVE_LOCAL_CATALOG_V1": (["catalog_id"], "TEXT", "MAPPING"),
}


def _ast(opcode: str, **members: Any) -> dict[str, Any]:
    return {"opcode": opcode, **members}


def _c(value: Any) -> dict[str, Any]:
    return _ast("CONST_V1", value=value)


def _p(name: str) -> dict[str, Any]:
    return _ast("PARAM_V1", parameter_name=name)


def _v(name: str) -> dict[str, Any]:
    return _ast("VAR_V1", variable_name=name)


def _children() -> dict[str, Any]:
    return _ast("CHILDREN_V1")


def _child(position: int) -> dict[str, Any]:
    return _ast("CHILD_V1", zero_based_index=position)


def _ceiling() -> dict[str, Any]:
    return _ast("CEILING_V1")


def _list(*items: Any) -> dict[str, Any]:
    return _ast("LIST_V1", ordered_items=list(items))


def _field(mapping: Any, name: str) -> dict[str, Any]:
    return _ast("FIELD_V1", mapping=mapping, field_name=name)


def _eq(left: Any, right: Any) -> dict[str, Any]:
    return _ast("EQ_V1", left=left, right=right)


def _le(left: Any, right: Any) -> dict[str, Any]:
    return _ast("LE_V1", left=left, right=right)


def _lt(left: Any, right: Any) -> dict[str, Any]:
    return _ast("LT_V1", left=left, right=right)


def _and(*operands: Any) -> dict[str, Any]:
    return _ast("AND_V1", ordered_operands=list(operands))


def _or(*operands: Any) -> dict[str, Any]:
    return _ast("OR_V1", ordered_operands=list(operands))


def _if(condition: Any, then: Any, otherwise: Any) -> dict[str, Any]:
    return _ast(
        "IF_V1",
        condition=condition,
        then_expression=then,
        else_expression=otherwise,
    )


def _let(bindings: list[tuple[str, Any]], result: Any) -> dict[str, Any]:
    return _ast(
        "LET_V1",
        ordered_bindings=[
            {"binding_name": name, "value_expression": expression}
            for name, expression in bindings
        ],
        result_expression=result,
    )


def _validate(condition: Any, code: str, result: Any) -> dict[str, Any]:
    return _ast(
        "VALIDATE_V1",
        condition=condition,
        error_code=code,
        result_expression=result,
    )


def _empty_ast(state: Any | None = None) -> dict[str, Any]:
    return _ast("CELL_EMPTY_V1", state_expression=state or _list())


def _cell_clipped(lower: Any, upper: Any, state: Any | None = None) -> dict[str, Any]:
    return _ast(
        "CELL_BUILD_CLIPPED_V1",
        lower=lower,
        upper=upper,
        ceiling=_ceiling(),
        state_expression=state or _list(),
    )


def _map(sequence: Any, variable: str, expression: Any) -> dict[str, Any]:
    return _ast(
        "MAP_V1",
        sequence=sequence,
        item_variable=variable,
        map_expression=expression,
    )


def _filter(sequence: Any, variable: str, predicate: Any) -> dict[str, Any]:
    return _ast(
        "FILTER_V1",
        sequence=sequence,
        item_variable=variable,
        predicate=predicate,
    )


def _require_bool(value: object, name: str) -> bool:
    if type(value) is not bool:
        raise TransferReject(f"{name} is not BOOL")
    return value


def _eval_transfer_ast(
    expression: Mapping[str, Any],
    *,
    parameters: Mapping[str, Any],
    children: Sequence[Cell],
    ceiling: int,
    variables: Mapping[str, Any],
    rules_by_name: Mapping[str, Mapping[str, Any]],
    local_catalogs_by_id: Mapping[str, Mapping[str, Any]],
) -> Any:
    if not isinstance(expression, dict) or "opcode" not in expression:
        raise TransferReject("transfer AST node is not an opcode mapping")
    opcode = expression["opcode"]
    if opcode not in AST_OPCODE_SIGNATURES:
        raise TransferReject(f"unknown transfer AST opcode: {opcode}")
    required_members = AST_OPCODE_SIGNATURES[opcode][0]
    if set(expression) != {"opcode", *required_members}:
        raise TransferReject(f"transfer AST members differ for {opcode}")

    def evaluate(child_expression: Mapping[str, Any]) -> Any:
        return _eval_transfer_ast(
            child_expression,
            parameters=parameters,
            children=children,
            ceiling=ceiling,
            variables=variables,
            rules_by_name=rules_by_name,
            local_catalogs_by_id=local_catalogs_by_id,
        )

    if opcode == "CONST_V1":
        return expression["value"]
    if opcode == "PARAM_V1":
        name = expression["parameter_name"]
        if name not in parameters:
            raise TransferReject(f"transfer parameter is absent: {name}")
        return parameters[name]
    if opcode == "CHILD_V1":
        index = u128(expression["zero_based_index"], name="child index")
        if index >= len(children):
            raise TransferReject("child index is out of range")
        return validate_cell(children[index], U128_MAX)
    if opcode == "CHILDREN_V1":
        return [validate_cell(child, U128_MAX) for child in children]
    if opcode == "CEILING_V1":
        return u128(ceiling, name="effective_canonical_octet_ceiling")
    if opcode == "VAR_V1":
        name = expression["variable_name"]
        if name not in variables:
            raise TransferReject(f"unbound transfer variable: {name}")
        return variables[name]
    if opcode == "LET_V1":
        scoped = dict(variables)
        seen: set[str] = set()
        for binding in expression["ordered_bindings"]:
            if list(binding) != ["binding_name", "value_expression"]:
                raise TransferReject("LET binding members differ")
            name = binding["binding_name"]
            if not isinstance(name, str) or not name or name in seen:
                raise TransferReject("LET binding name is invalid or duplicate")
            value = _eval_transfer_ast(
                binding["value_expression"],
                parameters=parameters,
                children=children,
                ceiling=ceiling,
                variables=scoped,
                rules_by_name=rules_by_name,
                local_catalogs_by_id=local_catalogs_by_id,
            )
            scoped[name] = value
            seen.add(name)
        return _eval_transfer_ast(
            expression["result_expression"],
            parameters=parameters,
            children=children,
            ceiling=ceiling,
            variables=scoped,
            rules_by_name=rules_by_name,
            local_catalogs_by_id=local_catalogs_by_id,
        )
    if opcode == "IF_V1":
        branch = (
            expression["then_expression"]
            if _require_bool(evaluate(expression["condition"]), "IF condition")
            else expression["else_expression"]
        )
        return evaluate(branch)
    if opcode == "VALIDATE_V1":
        if not _require_bool(evaluate(expression["condition"]), "VALIDATE condition"):
            raise TransferReject(f"AST validation failed: {expression['error_code']}")
        return evaluate(expression["result_expression"])
    if opcode in {"EQ_V1", "LE_V1", "LT_V1"}:
        left = evaluate(expression["left"])
        right = evaluate(expression["right"])
        return (
            left == right
            if opcode == "EQ_V1"
            else left <= right
            if opcode == "LE_V1"
            else left < right
        )
    if opcode in {"AND_V1", "OR_V1"}:
        values = [
            _require_bool(evaluate(item), f"{opcode} operand")
            for item in expression["ordered_operands"]
        ]
        return all(values) if opcode == "AND_V1" else any(values)
    if opcode == "NOT_V1":
        return not _require_bool(evaluate(expression["operand"]), "NOT operand")
    if opcode == "IN_SET_V1":
        values = expression["ordered_values"]
        if not isinstance(values, list):
            raise TransferReject("IN_SET values are not a list")
        return evaluate(expression["operand"]) in values
    if opcode.startswith("IS_"):
        operand = evaluate(expression.get("operand", expression.get("cell")))
        if opcode == "IS_NULL_V1":
            return operand is None
        if opcode == "IS_BOOLEAN_V1":
            return type(operand) is bool
        if opcode == "IS_TEXT_V1":
            return isinstance(operand, str)
        if opcode == "IS_U128_V1":
            return _is_plain_int(operand) and 0 <= operand <= U128_MAX
        if opcode == "IS_SIGNED_SAFE_INTEGER_V1":
            return _is_plain_int(operand) and (
                -IJSON_SAFE_INTEGER_MAX <= operand <= IJSON_SAFE_INTEGER_MAX
            )
        if opcode == "IS_LIST_V1":
            return isinstance(operand, list)
        if opcode == "IS_MAPPING_V1":
            return isinstance(operand, dict)
        if opcode == "IS_CELL_EMPTY_V1":
            if not isinstance(operand, Cell):
                raise TransferReject("IS_CELL_EMPTY operand is not CELL")
            return operand.status == PROVABLY_EMPTY
    if opcode == "HAS_EXACT_KEYS_V1":
        mapping = evaluate(expression["mapping"])
        keys = expression["ordered_keys"]
        if not isinstance(mapping, dict) or not isinstance(keys, list):
            raise TransferReject("HAS_EXACT_KEYS operands differ")
        return list(mapping) == keys
    if opcode == "FIELD_V1":
        mapping = evaluate(expression["mapping"])
        name = expression["field_name"]
        if not isinstance(mapping, dict) or name not in mapping:
            raise TransferReject(f"mapping field is absent: {name}")
        return mapping[name]
    if opcode == "INDEX_V1":
        sequence = evaluate(expression["sequence"])
        index = u128(evaluate(expression["zero_based_index"]), name="sequence index")
        if not isinstance(sequence, (list, tuple)) or index >= len(sequence):
            raise TransferReject("sequence index is out of range")
        return sequence[index]
    if opcode == "LIST_V1":
        return [evaluate(item) for item in expression["ordered_items"]]
    if opcode == "CONCAT_V1":
        output: list[Any] = []
        for sequence_expression in expression["ordered_sequences"]:
            sequence = evaluate(sequence_expression)
            if not isinstance(sequence, list):
                raise TransferReject("CONCAT operand is not LIST")
            output.extend(sequence)
        return output
    if opcode == "LIST_LENGTH_V1":
        sequence = evaluate(expression["sequence"])
        if not isinstance(sequence, (list, tuple)):
            raise TransferReject("LIST_LENGTH operand is not a sequence")
        return u128(len(sequence), name="sequence length")
    if opcode in {"MAP_V1", "FILTER_V1", "ANY_V1", "ALL_V1"}:
        sequence = evaluate(expression["sequence"])
        if not isinstance(sequence, (list, tuple)):
            raise TransferReject(f"{opcode} sequence differs")
        variable_name = expression["item_variable"]
        if not isinstance(variable_name, str) or not variable_name:
            raise TransferReject(f"{opcode} variable differs")
        expression_name = "map_expression" if opcode == "MAP_V1" else "predicate"
        results: list[Any] = []
        for item in sequence:
            scoped = {**variables, variable_name: item}
            result = _eval_transfer_ast(
                expression[expression_name],
                parameters=parameters,
                children=children,
                ceiling=ceiling,
                variables=scoped,
                rules_by_name=rules_by_name,
                local_catalogs_by_id=local_catalogs_by_id,
            )
            results.append(result)
        if opcode == "MAP_V1":
            return results
        bool_results = [_require_bool(item, f"{opcode} predicate") for item in results]
        if opcode == "FILTER_V1":
            return [
                item
                for item, admitted in zip(sequence, bool_results, strict=True)
                if admitted
            ]
        return any(bool_results) if opcode == "ANY_V1" else all(bool_results)
    if opcode == "ALL_INDEXED_V1":
        sequence = evaluate(expression["sequence"])
        if not isinstance(sequence, (list, tuple)):
            raise TransferReject("ALL_INDEXED sequence differs")
        results = []
        for index, item in enumerate(sequence):
            scoped = {
                **variables,
                expression["index_variable"]: index,
                expression["item_variable"]: item,
            }
            result = _eval_transfer_ast(
                expression["predicate"],
                parameters=parameters,
                children=children,
                ceiling=ceiling,
                variables=scoped,
                rules_by_name=rules_by_name,
                local_catalogs_by_id=local_catalogs_by_id,
            )
            results.append(_require_bool(result, "ALL_INDEXED predicate"))
        return all(results)
    if opcode in {"FOLD_MIN_U128_V1", "FOLD_MAX_U128_V1"}:
        sequence = evaluate(expression["sequence"])
        if not isinstance(sequence, list) or not sequence:
            raise TransferReject("U128 extrema sequence is empty or not LIST")
        values = [u128(item, name="U128 extrema operand") for item in sequence]
        return min(values) if opcode == "FOLD_MIN_U128_V1" else max(values)
    if opcode == "CHECKED_ADD_LIST_U128_V1":
        sequence = evaluate(expression["sequence"])
        if not isinstance(sequence, list):
            raise TransferReject("checked-add operand is not LIST")
        return checked_add(*sequence)
    if opcode == "CHECKED_SUB_U128_V1":
        return checked_sub(evaluate(expression["left"]), evaluate(expression["right"]))
    if opcode == "CHECKED_MUL_U128_V1":
        return checked_mul(evaluate(expression["left"]), evaluate(expression["right"]))
    if opcode == "CAPPED_ADD_LIST_U128_V1":
        sequence = evaluate(expression["sequence"])
        if not isinstance(sequence, list):
            raise TransferReject("capped-add operand is not LIST")
        return capped_add(evaluate(expression["ceiling"]), *sequence)
    if opcode == "CAPPED_MUL_U128_V1":
        return capped_mul(
            evaluate(expression["ceiling"]),
            evaluate(expression["left"]),
            evaluate(expression["right"]),
        )
    if opcode in {"CAPPED_VALUE_V1", "CAPPED_EXCEEDED_V1"}:
        capped_value = evaluate(expression["capped_value"])
        if not isinstance(capped_value, CappedU128):
            raise TransferReject("capped projection operand differs")
        return (
            capped_value.value
            if opcode == "CAPPED_VALUE_V1"
            else capped_value.exceeded_ceiling
        )
    if opcode == "DECIMAL_OCTETS_V1":
        value = _safe_integer(
            evaluate(expression["signed_integer"]), name="decimal integer"
        )
        return len(str(value).encode("ascii"))
    if opcode == "CANONICAL_STRING_OCTETS_V1":
        return canonical_string_octets(evaluate(expression["text"]))
    if opcode == "CELL_EMPTY_V1":
        state = evaluate(expression["state_expression"])
        if not isinstance(state, list):
            raise TransferReject("empty-cell state is not LIST")
        return empty(state=state)
    if opcode == "CELL_BUILD_CLIPPED_V1":
        state = evaluate(expression["state_expression"])
        if not isinstance(state, list):
            raise TransferReject("cell state is not LIST")
        return _clip_raw_bounds(
            evaluate(expression["lower"]),
            evaluate(expression["upper"]),
            evaluate(expression["ceiling"]),
            state=state,
        )
    if opcode == "CELL_BUILD_FROM_CAPPED_V1":
        lower = evaluate(expression["lower_capped"])
        upper = evaluate(expression["upper_capped"])
        state = evaluate(expression["state_expression"])
        target_ceiling = evaluate(expression["ceiling"])
        if not isinstance(lower, CappedU128) or not isinstance(upper, CappedU128):
            raise TransferReject("bounded-cell operands are not CAPPED_U128")
        if not isinstance(state, list):
            raise TransferReject("bounded-cell state is not LIST")
        return (
            empty(state=state)
            if lower.exceeded_ceiling
            else nonempty(lower.value, upper.value, target_ceiling, state=state)
        )
    if opcode == "CELL_CLIP_V1":
        cell = evaluate(expression["cell"])
        if not isinstance(cell, Cell):
            raise TransferReject("CELL_CLIP operand is not CELL")
        return _clip_cell(cell, evaluate(expression["ceiling"]))
    if opcode in {"CELL_LOWER_V1", "CELL_UPPER_V1", "CELL_STATE_V1"}:
        cell = evaluate(expression["cell"])
        if not isinstance(cell, Cell):
            raise TransferReject("cell projection operand differs")
        return (
            cell.lower
            if opcode == "CELL_LOWER_V1"
            else cell.upper
            if opcode == "CELL_UPPER_V1"
            else list(cell.state)
        )
    if opcode == "CALL_RULE_V1":
        rule_id = expression["transfer_rule_id"]
        called_rule = next(
            (
                row
                for row in rules_by_name.values()
                if row["transfer_rule_id"] == rule_id
            ),
            None,
        )
        if called_rule is None:
            raise TransferReject(f"called transfer rule identity is absent: {rule_id}")
        argument_bindings = expression["ordered_argument_bindings"]
        called_parameters: dict[str, Any] = {}
        for binding in argument_bindings:
            if list(binding) != ["parameter_name", "value_expression"]:
                raise TransferReject("CALL_RULE argument members differ")
            name = binding["parameter_name"]
            if name in called_parameters:
                raise TransferReject("CALL_RULE argument is duplicate")
            called_parameters[name] = evaluate(binding["value_expression"])
        return _run_ast_rule(
            called_rule,
            parameters=called_parameters,
            children=children,
            ceiling=ceiling,
            rules_by_name=rules_by_name,
            local_catalogs_by_id=local_catalogs_by_id,
        )
    if opcode == "RESOLVE_LOCAL_CATALOG_V1":
        catalog_id = evaluate(expression["catalog_id"])
        if not isinstance(catalog_id, str) or catalog_id not in local_catalogs_by_id:
            raise TransferReject("local catalog identity did not resolve")
        return local_catalogs_by_id[catalog_id]
    raise AssertionError(f"unimplemented closed AST opcode: {opcode}")


def _run_ast_rule(
    rule: Mapping[str, Any],
    *,
    parameters: Mapping[str, Any],
    children: Sequence[Cell],
    ceiling: int,
    rules_by_name: Mapping[str, Mapping[str, Any]],
    local_catalogs_by_id: Mapping[str, Mapping[str, Any]],
) -> Cell:
    expected_parameters = rule["ordered_parameter_names"]
    if list(parameters) != expected_parameters:
        raise TransferReject(f"rule parameters differ for {rule['transfer_rule_name']}")
    result = _eval_transfer_ast(
        rule["program"],
        parameters=parameters,
        children=children,
        ceiling=ceiling,
        variables={},
        rules_by_name=rules_by_name,
        local_catalogs_by_id=local_catalogs_by_id,
    )
    if not isinstance(result, Cell):
        raise TransferReject("transfer-rule program did not return CELL")
    return validate_cell(result, ceiling)


def _binding(name: str, expression: Any) -> dict[str, Any]:
    return {"parameter_name": name, "value_expression": expression}


def _call(rule_name: str, **arguments: Any) -> dict[str, Any]:
    return _ast(
        "CALL_RULE_V1",
        transfer_rule_id=rule_name,
        ordered_argument_bindings=[
            _binding(name, expression) for name, expression in arguments.items()
        ],
    )


def _cell_lower(cell: Any) -> dict[str, Any]:
    return _ast("CELL_LOWER_V1", cell=cell)


def _cell_upper(cell: Any) -> dict[str, Any]:
    return _ast("CELL_UPPER_V1", cell=cell)


def _capped_value(expression: Any) -> dict[str, Any]:
    return _ast("CAPPED_VALUE_V1", capped_value=expression)


def _capped_exceeded(expression: Any) -> dict[str, Any]:
    return _ast("CAPPED_EXCEEDED_V1", capped_value=expression)


def _capped_add_ast(*operands: Any) -> dict[str, Any]:
    return _ast(
        "CAPPED_ADD_LIST_U128_V1", ceiling=_ceiling(), sequence=_list(*operands)
    )


def _capped_mul_ast(left: Any, right: Any) -> dict[str, Any]:
    return _ast("CAPPED_MUL_U128_V1", ceiling=_ceiling(), left=left, right=right)


def _comma_count(cardinality: Any) -> dict[str, Any]:
    return _if(
        _eq(cardinality, _c(0)),
        _c(0),
        _ast("CHECKED_SUB_U128_V1", left=cardinality, right=_c(1)),
    )


def _array_rule_program(*, batch: bool) -> dict[str, Any]:
    child = _v("item")
    minimum = _v("minimum")
    maximum = _v("maximum")
    lower_item_sum = _capped_mul_ast(minimum, _cell_lower(child))
    upper_item_sum = _capped_mul_ast(maximum, _cell_upper(child))
    lower_total = _capped_add_ast(
        _c(2), _capped_value(lower_item_sum), _comma_count(minimum)
    )
    upper_total = _capped_add_ast(
        _c(2), _capped_value(upper_item_sum), _comma_count(maximum)
    )
    state = (
        _list(maximum, _capped_value(upper_item_sum), _comma_count(maximum))
        if batch
        else _list(
            maximum,
            maximum,
            _capped_value(upper_item_sum),
            _comma_count(maximum),
        )
    )
    nonempty_result = _ast(
        "CELL_BUILD_FROM_CAPPED_V1",
        lower_capped=lower_total,
        upper_capped=upper_total,
        ceiling=_ceiling(),
        state_expression=state,
    )
    empty_child_result = _if(
        _eq(minimum, _c(0)), _cell_clipped(_c(2), _c(2)), _empty_ast()
    )
    base_validation = _and(
        _ast("IS_U128_V1", operand=minimum),
        _ast("IS_U128_V1", operand=maximum),
        _le(minimum, maximum),
    )
    if batch:
        run_sum = _ast(
            "CHECKED_ADD_LIST_U128_V1",
            sequence=_map(
                _p("ordered_run_records"),
                "run",
                _field(_v("run"), "item_count"),
            ),
        )
        base_validation = _and(
            base_validation,
            _ast("IS_MAPPING_V1", operand=_p("observer_closure_record")),
            _eq(_field(_p("observer_closure_record"), "batch_eligible"), _c(True)),
            _ast("IS_LIST_V1", operand=_p("ordered_run_records")),
            _eq(run_sum, maximum),
        )
    return _let(
        [
            ("item", _child(0)),
            ("minimum", _p("minimum_items")),
            ("maximum", _p("maximum_items")),
        ],
        _validate(
            base_validation,
            "ARRAY_PARAMETERS_INVALID",
            _if(
                _ast("IS_CELL_EMPTY_V1", cell=child),
                empty_child_result,
                nonempty_result,
            ),
        ),
    )


def _reference_rule_programs() -> list[tuple[str, list[str], dict[str, Any]]]:
    fixed = _cell_clipped(_p("fixed_canonical_octets"), _p("fixed_canonical_octets"))
    boolean_lengths = _filter(
        _list(_c(4), _c(5)), "length", _le(_v("length"), _ceiling())
    )
    boolean_full = _let(
        [("admitted", boolean_lengths)],
        _if(
            _eq(_ast("LIST_LENGTH_V1", sequence=_v("admitted")), _c(0)),
            _empty_ast(),
            _cell_clipped(
                _ast("FOLD_MIN_U128_V1", sequence=_v("admitted")),
                _ast("FOLD_MAX_U128_V1", sequence=_v("admitted")),
            ),
        ),
    )
    boolean = _validate(
        _or(
            _ast("IS_NULL_V1", operand=_p("boolean_literal")),
            _ast("IS_BOOLEAN_V1", operand=_p("boolean_literal")),
        ),
        "BOOLEAN_SENTINEL_INVALID",
        _if(
            _ast("IS_NULL_V1", operand=_p("boolean_literal")),
            boolean_full,
            _if(
                _p("boolean_literal"),
                _cell_clipped(_c(4), _c(4)),
                _cell_clipped(_c(5), _c(5)),
            ),
        ),
    )

    integer_minimum = _p("integer_minimum")
    integer_maximum = _p("integer_maximum")
    nearest_zero = _if(
        _and(_le(integer_minimum, _c(0)), _le(_c(0), integer_maximum)),
        _c(0),
        _if(_lt(_c(0), integer_minimum), integer_minimum, integer_maximum),
    )
    integer = _validate(
        _and(
            _ast("IS_SIGNED_SAFE_INTEGER_V1", operand=integer_minimum),
            _ast("IS_SIGNED_SAFE_INTEGER_V1", operand=integer_maximum),
            _le(integer_minimum, integer_maximum),
        ),
        "SAFE_INTEGER_INTERVAL_INVALID",
        _cell_clipped(
            _ast("DECIMAL_OCTETS_V1", signed_integer=nearest_zero),
            _ast(
                "FOLD_MAX_U128_V1",
                sequence=_list(
                    _ast("DECIMAL_OCTETS_V1", signed_integer=integer_minimum),
                    _ast("DECIMAL_OCTETS_V1", signed_integer=integer_maximum),
                ),
            ),
        ),
    )

    literal_lengths = _map(
        _p("ordered_literals"),
        "literal",
        _ast("CANONICAL_STRING_OCTETS_V1", text=_v("literal")),
    )
    finite_text = _let(
        [
            ("lengths", literal_lengths),
            (
                "admitted",
                _filter(_v("lengths"), "length", _le(_v("length"), _ceiling())),
            ),
        ],
        _validate(
            _ast(
                "ALL_V1",
                sequence=_p("ordered_literals"),
                item_variable="literal",
                predicate=_ast("IS_TEXT_V1", operand=_v("literal")),
            ),
            "FINITE_TEXT_LITERAL_INVALID",
            _if(
                _eq(_ast("LIST_LENGTH_V1", sequence=_v("admitted")), _c(0)),
                _empty_ast(),
                _cell_clipped(
                    _ast("FOLD_MIN_U128_V1", sequence=_v("admitted")),
                    _ast("FOLD_MAX_U128_V1", sequence=_v("admitted")),
                ),
            ),
        ),
    )
    bounded_text = _validate(
        _and(
            _ast("IS_U128_V1", operand=_p("minimum_canonical_octets")),
            _ast("IS_U128_V1", operand=_p("maximum_canonical_octets")),
            _le(
                _p("minimum_canonical_octets"),
                _p("maximum_canonical_octets"),
            ),
        ),
        "BOUNDED_TEXT_INTERVAL_INVALID",
        _cell_clipped(_p("minimum_canonical_octets"), _p("maximum_canonical_octets")),
    )
    relaxed_text = _if(
        _lt(_ceiling(), _c(2)),
        _empty_ast(),
        _cell_clipped(_c(2), _ceiling()),
    )

    nullable = _let(
        [("child", _ast("CELL_CLIP_V1", cell=_child(0), ceiling=_ceiling()))],
        _if(
            _lt(_ceiling(), _c(4)),
            _v("child"),
            _if(
                _ast("IS_CELL_EMPTY_V1", cell=_v("child")),
                _cell_clipped(_c(4), _c(4)),
                _cell_clipped(
                    _ast(
                        "FOLD_MIN_U128_V1",
                        sequence=_list(_c(4), _cell_lower(_v("child"))),
                    ),
                    _ast(
                        "FOLD_MAX_U128_V1",
                        sequence=_list(_c(4), _cell_upper(_v("child"))),
                    ),
                ),
            ),
        ),
    )
    alias = _ast("CELL_CLIP_V1", cell=_child(0), ceiling=_ceiling())

    # List concatenation keeps the AST data-only and avoids Python-side
    # expansion of a runtime child list.
    lower_sequence = _ast(
        "CONCAT_V1",
        ordered_sequences=[
            _list(_p("record_syntax_octets_excluding_child_values")),
            _map(_v("children"), "member", _cell_lower(_v("member"))),
        ],
    )
    upper_sequence = _ast(
        "CONCAT_V1",
        ordered_sequences=[
            _list(_p("record_syntax_octets_excluding_child_values")),
            _map(_v("children"), "member", _cell_upper(_v("member"))),
        ],
    )
    record = _let(
        [
            ("children", _children()),
            (
                "lower",
                _ast(
                    "CAPPED_ADD_LIST_U128_V1",
                    ceiling=_ceiling(),
                    sequence=lower_sequence,
                ),
            ),
            (
                "upper",
                _ast(
                    "CAPPED_ADD_LIST_U128_V1",
                    ceiling=_ceiling(),
                    sequence=upper_sequence,
                ),
            ),
        ],
        _validate(
            _and(
                _eq(
                    _p("record_member_count"),
                    _ast("LIST_LENGTH_V1", sequence=_v("children")),
                ),
                _eq(
                    _ast("LIST_LENGTH_V1", sequence=_p("ordered_member_records")),
                    _ast("LIST_LENGTH_V1", sequence=_v("children")),
                ),
            ),
            "RECORD_CHILD_BINDING_INVALID",
            _if(
                _ast(
                    "ANY_V1",
                    sequence=_v("children"),
                    item_variable="member",
                    predicate=_ast("IS_CELL_EMPTY_V1", cell=_v("member")),
                ),
                _empty_ast(),
                _ast(
                    "CELL_BUILD_FROM_CAPPED_V1",
                    lower_capped=_v("lower"),
                    upper_capped=_v("upper"),
                    ceiling=_ceiling(),
                    state_expression=_list(),
                ),
            ),
        ),
    )

    admitted_union_children = _filter(
        _children(),
        "alternative",
        _and(
            _ast(
                "NOT_V1",
                operand=_ast("IS_CELL_EMPTY_V1", cell=_v("alternative")),
            ),
            _le(_cell_lower(_v("alternative")), _ceiling()),
        ),
    )
    union = _let(
        [
            ("children", _children()),
            ("admitted", admitted_union_children),
            (
                "clipped",
                _map(
                    _v("admitted"),
                    "alternative",
                    _ast(
                        "CELL_CLIP_V1",
                        cell=_v("alternative"),
                        ceiling=_ceiling(),
                    ),
                ),
            ),
        ],
        _validate(
            _eq(
                _ast(
                    "LIST_LENGTH_V1",
                    sequence=_p("ordered_alternative_records"),
                ),
                _ast("LIST_LENGTH_V1", sequence=_v("children")),
            ),
            "UNION_CHILD_BINDING_INVALID",
            _if(
                _eq(_ast("LIST_LENGTH_V1", sequence=_v("clipped")), _c(0)),
                _empty_ast(),
                _cell_clipped(
                    _ast(
                        "FOLD_MIN_U128_V1",
                        sequence=_map(
                            _v("clipped"),
                            "alternative",
                            _cell_lower(_v("alternative")),
                        ),
                    ),
                    _ast(
                        "FOLD_MAX_U128_V1",
                        sequence=_map(
                            _v("clipped"),
                            "alternative",
                            _cell_upper(_v("alternative")),
                        ),
                    ),
                ),
            ),
        ),
    )

    coordinate_rule = _let(
        [
            ("coordinate", _p("coordinate")),
            ("relation", _field(_v("coordinate"), "codec_byte_bound_relation")),
            ("limit", _field(_v("coordinate"), "codec_octet_limit")),
            ("scope", _field(_v("coordinate"), "coordinate_scope")),
            (
                "overhead",
                _field(_v("coordinate"), "minimum_sibling_and_syntax_octets"),
            ),
            (
                "inclusive",
                _if(
                    _eq(_v("relation"), _c("LE")),
                    _v("limit"),
                    _ast("CHECKED_SUB_U128_V1", left=_v("limit"), right=_c(1)),
                ),
            ),
            (
                "derived",
                _ast(
                    "CHECKED_SUB_U128_V1",
                    left=_v("inclusive"),
                    right=_v("overhead"),
                ),
            ),
        ],
        _validate(
            _and(
                _ast("IS_MAPPING_V1", operand=_v("coordinate")),
                _ast(
                    "HAS_EXACT_KEYS_V1",
                    mapping=_v("coordinate"),
                    ordered_keys=[
                        "codec_byte_bound_relation",
                        "codec_octet_limit",
                        "codec_owner_type_name",
                        "codec_owner_typed_member_path",
                        "coordinate_position",
                        "coordinate_scope",
                        "derived_payload_octet_ceiling",
                        "minimum_sibling_and_syntax_octets",
                        "selected_union_alternative_name",
                    ],
                ),
                _ast("IN_SET_V1", operand=_v("relation"), ordered_values=["LE", "LT"]),
                _ast(
                    "IN_SET_V1",
                    operand=_v("scope"),
                    ordered_values=["SELF_TYPE", "OWNER_PAYLOAD_RESIDUAL"],
                ),
                _or(
                    _ast("NOT_V1", operand=_eq(_v("scope"), _c("SELF_TYPE"))),
                    _eq(_v("overhead"), _c(0)),
                ),
                _eq(
                    _v("derived"),
                    _field(_v("coordinate"), "derived_payload_octet_ceiling"),
                ),
            ),
            "CODEC_COORDINATE_INVALID",
            _cell_clipped(_v("derived"), _v("derived")),
        ),
    )
    codec = _let(
        [
            (
                "coordinate_cells",
                _map(
                    _p("ordered_codec_coordinate_records"),
                    "coordinate",
                    _call(
                        "CODEC_COORDINATE_CEILING_V1",
                        coordinate=_v("coordinate"),
                    ),
                ),
            ),
            (
                "effective",
                _ast(
                    "FOLD_MIN_U128_V1",
                    sequence=_ast(
                        "CONCAT_V1",
                        ordered_sequences=[
                            _list(_ceiling()),
                            _map(
                                _v("coordinate_cells"),
                                "coordinate_cell",
                                _cell_upper(_v("coordinate_cell")),
                            ),
                        ],
                    ),
                ),
            ),
        ],
        _validate(
            _lt(
                _c(0),
                _ast(
                    "LIST_LENGTH_V1",
                    sequence=_p("ordered_codec_coordinate_records"),
                ),
            ),
            "CODEC_COORDINATE_LIST_EMPTY",
            _ast("CELL_CLIP_V1", cell=_child(0), ceiling=_v("effective")),
        ),
    )

    local = _let(
        [
            (
                "catalog",
                _ast(
                    "RESOLVE_LOCAL_CATALOG_V1",
                    catalog_id=_p("local_shutdown_analytic_catalog_id"),
                ),
            ),
            ("states", _field(_v("catalog"), "ordered_controller_state_records")),
            (
                "transitions",
                _field(_v("catalog"), "ordered_controller_transition_records"),
            ),
            (
                "terminal",
                _ast("INDEX_V1", sequence=_v("states"), zero_based_index=_c(11)),
            ),
            ("components", _field(_v("terminal"), "ordered_state_components")),
            (
                "winner",
                _ast("INDEX_V1", sequence=_v("components"), zero_based_index=_c(7)),
            ),
        ],
        _validate(
            _and(
                _ast("IS_LIST_V1", operand=_v("states")),
                _ast("IS_LIST_V1", operand=_v("transitions")),
                _eq(_ast("LIST_LENGTH_V1", sequence=_v("states")), _c(12)),
                _eq(_ast("LIST_LENGTH_V1", sequence=_v("transitions")), _c(11)),
                _ast(
                    "ALL_INDEXED_V1",
                    sequence=_v("states"),
                    index_variable="state_index",
                    item_variable="state",
                    predicate=_eq(
                        _field(_v("state"), "controller_state_position"),
                        _ast(
                            "CHECKED_ADD_LIST_U128_V1",
                            sequence=_list(_v("state_index"), _c(1)),
                        ),
                    ),
                ),
                _ast(
                    "ALL_INDEXED_V1",
                    sequence=_v("transitions"),
                    index_variable="transition_index",
                    item_variable="transition",
                    predicate=_and(
                        _eq(
                            _field(_v("transition"), "controller_transition_position"),
                            _ast(
                                "CHECKED_ADD_LIST_U128_V1",
                                sequence=_list(_v("transition_index"), _c(1)),
                            ),
                        ),
                        _eq(
                            _field(_v("transition"), "source_controller_state_id"),
                            _field(
                                _ast(
                                    "INDEX_V1",
                                    sequence=_v("states"),
                                    zero_based_index=_v("transition_index"),
                                ),
                                "controller_state_id",
                            ),
                        ),
                        _eq(
                            _field(_v("transition"), "target_controller_state_id"),
                            _field(
                                _ast(
                                    "INDEX_V1",
                                    sequence=_v("states"),
                                    zero_based_index=_ast(
                                        "CHECKED_ADD_LIST_U128_V1",
                                        sequence=_list(_v("transition_index"), _c(1)),
                                    ),
                                ),
                                "controller_state_id",
                            ),
                        ),
                        _eq(
                            _field(
                                _v("transition"), "expected_target_state_components"
                            ),
                            _field(
                                _ast(
                                    "INDEX_V1",
                                    sequence=_v("states"),
                                    zero_based_index=_ast(
                                        "CHECKED_ADD_LIST_U128_V1",
                                        sequence=_list(_v("transition_index"), _c(1)),
                                    ),
                                ),
                                "ordered_state_components",
                            ),
                        ),
                    ),
                ),
                _eq(_field(_v("terminal"), "state_kind"), _c("TERMINAL")),
                _eq(_ast("LIST_LENGTH_V1", sequence=_v("components")), _c(8)),
                _ast("IS_U128_V1", operand=_v("winner")),
                _eq(
                    _v("winner"),
                    _field(_v("catalog"), "winner_attainable_maximum_octets"),
                ),
            ),
            "LOCAL_CONTROLLER_INVALID",
            _cell_clipped(_v("winner"), _v("winner"), _v("components")),
        ),
    )

    return [
        ("FIXED_EXACT_OR_EMPTY_V1", ["fixed_canonical_octets"], fixed),
        ("BOOLEAN_LITERAL_OR_FULL_DOMAIN_SENTINEL_V1", ["boolean_literal"], boolean),
        (
            "SIGNED_SAFE_INTEGER_ENDPOINT_AND_NEAREST_ZERO_V1",
            ["integer_minimum", "integer_maximum", "ordered_probe_values"],
            integer,
        ),
        (
            "FINITE_CANONICAL_STRING_LENGTH_EXTREMA_V1",
            ["text_language_position", "text_language_id", "ordered_literals"],
            finite_text,
        ),
        (
            "BOUNDED_CANONICAL_STRING_OCTET_INTERVAL_V1",
            [
                "built_in_language_kind",
                "minimum_canonical_octets",
                "maximum_canonical_octets",
                "text_language_id",
                "text_language_position",
            ],
            bounded_text,
        ),
        (
            "ALL_CANONICAL_JSON_STRINGS_UNDER_EFFECTIVE_CEILING_V1",
            [
                "text_language_position",
                "text_language_id",
                "language_kind",
                "built_in_language_kind",
                "ascii_dfa_id",
                "unicode_identifier_profile_id",
                "minimum_utf8_octets",
                "maximum_utf8_octets",
                "minimum_decoded_octets",
                "maximum_decoded_octets",
                "decimal_maximum",
            ],
            relaxed_text,
        ),
        (
            "DERIVED_IDENTITY_EXACT_OR_EMPTY_V1",
            ["canonical_octets"],
            _cell_clipped(_p("canonical_octets"), _p("canonical_octets")),
        ),
        ("NULL_LITERAL_AND_NON_NULL_CHILD_UNION_V1", ["child_step_position"], nullable),
        (
            "VALIDATED_CHILD_BOUNDS_ALIAS_V1",
            ["referenced_type_name", "child_step_position"],
            alias,
        ),
        (
            "HOMOGENEOUS_ARRAY_BATCH_INTERVAL_V1",
            [
                "minimum_items",
                "maximum_items",
                "item_value_schema_id",
                "item_step_position",
                "ordered_run_records",
                "observer_closure_record",
            ],
            _array_rule_program(batch=True),
        ),
        (
            "HOMOGENEOUS_ARRAY_STREAM_INTERVAL_V1",
            ["minimum_items", "maximum_items", "item_step_position"],
            _array_rule_program(batch=False),
        ),
        (
            "RECORD_SYNTAX_PLUS_ORDERED_CHILD_SUM_V1",
            [
                "record_member_count",
                "ordered_member_records",
                "record_syntax_octets_excluding_child_values",
            ],
            record,
        ),
        (
            "ORDERED_NONEMPTY_ALTERNATIVE_INTERVAL_UNION_V1",
            [
                "ordered_alternative_records",
                "owner_type_name",
                "owner_typed_member_path",
            ],
            union,
        ),
        (
            "CODEC_COORDINATE_CEILING_V1",
            ["coordinate"],
            coordinate_rule,
        ),
        (
            "RECOMPUTED_CODEC_RESIDUAL_INTERSECTION_V1",
            ["ordered_codec_coordinate_records", "child_step_position"],
            codec,
        ),
        (
            "VALIDATED_RELAXATION_ALIAS_V1",
            [
                "safe_relaxation_rule_id",
                "authority_predicate_locator",
                "child_step_position",
            ],
            alias,
        ),
        (
            "VALIDATED_SCOPE_ALIAS_V1",
            ["case_binding", "fixed_authority_bindings", "child_step_position"],
            alias,
        ),
        (
            "VALIDATED_APPLICATION_ALIAS_V1",
            ["ordered_application_invocation_records", "child_step_position"],
            alias,
        ),
        (
            "EXACT_CHAINED_LOCAL_CONTROLLER_TERMINAL_WINNER_V2",
            ["local_shutdown_analytic_catalog_id"],
            local,
        ),
    ]


TRANSFER_RULE_NAME_BY_OPCODE = {
    "CELL_FIXED_OCTETS_V1": "FIXED_EXACT_OR_EMPTY_V1",
    "CELL_BOOLEAN_LITERAL_V1": "BOOLEAN_LITERAL_OR_FULL_DOMAIN_SENTINEL_V1",
    "CELL_SAFE_INTEGER_INTERVAL_V1": "SIGNED_SAFE_INTEGER_ENDPOINT_AND_NEAREST_ZERO_V1",
    "CELL_FINITE_TEXT_V1": "FINITE_CANONICAL_STRING_LENGTH_EXTREMA_V1",
    "CELL_BOUNDED_TEXT_OCTETS_V1": "BOUNDED_CANONICAL_STRING_OCTET_INTERVAL_V1",
    "CELL_RELAXED_JSON_STRING_V1": "ALL_CANONICAL_JSON_STRINGS_UNDER_EFFECTIVE_CEILING_V1",
    "CELL_DERIVED_IDENTITY_V1": "DERIVED_IDENTITY_EXACT_OR_EMPTY_V1",
    "CELL_NULLABLE_V1": "NULL_LITERAL_AND_NON_NULL_CHILD_UNION_V1",
    "CELL_CHILD_BOUNDS_ALIAS_V1": "VALIDATED_CHILD_BOUNDS_ALIAS_V1",
    "CELL_ARRAY_BATCH_V1": "HOMOGENEOUS_ARRAY_BATCH_INTERVAL_V1",
    "CELL_ARRAY_STREAM_V1": "HOMOGENEOUS_ARRAY_STREAM_INTERVAL_V1",
    "CELL_RECORD_V1": "RECORD_SYNTAX_PLUS_ORDERED_CHILD_SUM_V1",
    "CELL_UNION_V1": "ORDERED_NONEMPTY_ALTERNATIVE_INTERVAL_UNION_V1",
    "CELL_CODEC_INTERSECTION_V1": "RECOMPUTED_CODEC_RESIDUAL_INTERSECTION_V1",
    "CELL_SAFE_RELAXATION_V1": "VALIDATED_RELAXATION_ALIAS_V1",
    "CELL_SCOPE_ROOT_V1": "VALIDATED_SCOPE_ALIAS_V1",
    "CELL_APPLICATION_WRAPPER_V1": "VALIDATED_APPLICATION_ALIAS_V1",
    "CELL_LOCAL_SHUTDOWN_SWEEP_V2": "EXACT_CHAINED_LOCAL_CONTROLLER_TERMINAL_WINNER_V2",
}

TRANSFER_RULE_VERSION = (
    "riskyieldmm.raw_v8_step2_external_schema_v2.cell_transfer_rule.v1"
)
TRANSFER_RULE_CATALOG_VERSION = (
    "riskyieldmm.raw_v8_step2_external_schema_v2.cell_transfer_rule_catalog.v1"
)
TRANSFER_RULE_DOMAIN = (
    "RiskYieldMMA2MStep2ExternalSchemaV2CellTransferRuleV1V4_9F_RawV8"
)
TRANSFER_RULE_CATALOG_DOMAIN = (
    "RiskYieldMMA2MStep2ExternalSchemaV2CellTransferRuleCatalogV1V4_9F_RawV8"
)


def _semantic_id_for_test(domain: str, payload: Mapping[str, Any]) -> str:
    envelope = {
        "canonicalization_version": "riskyieldmm_canonical_json_v1",
        "domain": domain,
        "payload": payload,
        "schema_version": "riskyieldmm_physical_transport_a2m_raw_v49f_v8",
    }
    encoded = json.dumps(
        envelope,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _bind_subrule_identities(
    value: object, rule_ids_by_name: Mapping[str, str]
) -> object:
    if isinstance(value, list):
        return [_bind_subrule_identities(item, rule_ids_by_name) for item in value]
    if not isinstance(value, dict):
        return value
    rebound = {
        key: _bind_subrule_identities(child, rule_ids_by_name)
        for key, child in value.items()
    }
    if rebound.get("opcode") == "CALL_RULE_V1":
        unbound_name = rebound["transfer_rule_id"]
        if unbound_name not in rule_ids_by_name:
            raise TransferReject(
                f"subrule is not earlier in topological identity order: {unbound_name}"
            )
        rebound["transfer_rule_id"] = rule_ids_by_name[unbound_name]
    return rebound


def _reference_parameter_type(name: str) -> str:
    if name == "boolean_literal":
        return "BOOLEAN_OR_NULL_FULL_DOMAIN_SENTINEL"
    if name in {"integer_minimum", "integer_maximum"}:
        return "SIGNED_SAFE_INTEGER"
    if name in {
        "fixed_canonical_octets",
        "canonical_octets",
        "text_language_position",
        "minimum_canonical_octets",
        "maximum_canonical_octets",
        "minimum_items",
        "maximum_items",
        "item_step_position",
        "child_step_position",
        "record_member_count",
        "record_syntax_octets_excluding_child_values",
    }:
        return "U128"
    if name in {
        "minimum_utf8_octets",
        "maximum_utf8_octets",
        "minimum_decoded_octets",
        "maximum_decoded_octets",
    }:
        return "OPTIONAL_U128"
    if name in {
        "built_in_language_kind",
        "ascii_dfa_id",
        "unicode_identifier_profile_id",
        "decimal_maximum",
        "owner_type_name",
    }:
        return "OPTIONAL_TEXT"
    if name in {
        "text_language_id",
        "language_kind",
        "item_value_schema_id",
        "referenced_type_name",
        "safe_relaxation_rule_id",
        "local_shutdown_analytic_catalog_id",
    }:
        return "TEXT"
    if name in {"case_binding", "observer_closure_record", "coordinate"}:
        return "JSON_MAPPING"
    if name in {"owner_typed_member_path", "authority_predicate_locator"}:
        return "TYPED_PATH"
    if name.startswith("ordered_") or name == "fixed_authority_bindings":
        return "ORDERED_JSON_ARRAY"
    raise AssertionError(f"reference transfer parameter type is absent: {name}")


def _build_reference_transfer_rule_catalog() -> dict[str, Any]:
    rules: list[dict[str, Any]] = []
    rule_ids_by_name: dict[str, str] = {}
    for position, (name, parameter_names, unbound_program) in enumerate(
        _reference_rule_programs(), 1
    ):
        program = _bind_subrule_identities(unbound_program, rule_ids_by_name)
        payload = {
            "transfer_rule_version": TRANSFER_RULE_VERSION,
            "rule_position": position,
            "transfer_rule_name": name,
            "ordered_parameter_names": parameter_names,
            "ordered_parameter_type_records": [
                {
                    "parameter_position": parameter_position,
                    "parameter_name": parameter_name,
                    "value_type": _reference_parameter_type(parameter_name),
                }
                for parameter_position, parameter_name in enumerate(parameter_names, 1)
            ],
            "result_type": "CELL",
            "program": program,
        }
        rule_id = _semantic_id_for_test(TRANSFER_RULE_DOMAIN, payload)
        rules.append({**payload, "transfer_rule_id": rule_id})
        rule_ids_by_name[name] = rule_id
    primitive_records = [
        {
            "opcode_position": position,
            "opcode": opcode,
            "ordered_required_member_names_after_opcode": members,
            "operand_type_rule": operand_types,
            "result_type": result_type,
            "unknown_or_extra_member_policy": "REJECT",
        }
        for position, (opcode, (members, operand_types, result_type)) in enumerate(
            AST_OPCODE_SIGNATURES.items(), 1
        )
    ]
    payload = {
        "transfer_rule_catalog_version": TRANSFER_RULE_CATALOG_VERSION,
        "evaluation_order": "DEPTH_FIRST_LEFT_TO_RIGHT_LAZY_BRANCHES_CHECKED_UINT128",
        "unknown_or_extra_ast_member_policy": "REJECT",
        "ordered_primitive_opcode_records": primitive_records,
        "ordered_transfer_rule_records": rules,
    }
    return {
        **payload,
        "transfer_rule_catalog_id": _semantic_id_for_test(
            TRANSFER_RULE_CATALOG_DOMAIN, payload
        ),
    }


REFERENCE_TRANSFER_RULE_CATALOG = _build_reference_transfer_rule_catalog()


def _validate_ast_nodes(value: object) -> None:
    if isinstance(value, dict):
        if "opcode" in value:
            opcode = value["opcode"]
            if opcode not in AST_OPCODE_SIGNATURES:
                raise TransferReject(f"AST contains unknown opcode: {opcode}")
            members = AST_OPCODE_SIGNATURES[opcode][0]
            if set(value) != {"opcode", *members}:
                raise TransferReject(f"AST node schema differs: {opcode}")
        for child in value.values():
            _validate_ast_nodes(child)
    elif isinstance(value, list):
        for child in value:
            _validate_ast_nodes(child)


def _called_transfer_rule_ids(value: object) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        if value.get("opcode") == "CALL_RULE_V1":
            found.append(value["transfer_rule_id"])
        for child in value.values():
            found.extend(_called_transfer_rule_ids(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_called_transfer_rule_ids(child))
    return found


def _walk_ast_mappings(value: object) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_ast_mappings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_ast_mappings(child)


def _rules_by_name(rule_catalog: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    rows = rule_catalog["ordered_transfer_rule_records"]
    by_name = {row["transfer_rule_name"]: row for row in rows}
    if len(by_name) != len(rows):
        raise TransferReject("transfer-rule name is duplicate")
    return by_name


def execute_rule_catalog_transfer(
    rule_catalog: Mapping[str, Any],
    opcode: str,
    parameters: Mapping[str, Any],
    ordered_children: Sequence[Cell],
    ceiling: int,
    *,
    local_catalogs_by_id: Mapping[str, Mapping[str, Any]] | None = None,
) -> Cell:
    if opcode not in TRANSFER_RULE_NAME_BY_OPCODE:
        raise TransferReject("transfer opcode has no identity-bound rule")
    rules = _rules_by_name(rule_catalog)
    rule_name = TRANSFER_RULE_NAME_BY_OPCODE[opcode]
    if rule_name not in rules:
        raise TransferReject("identity-bound transfer rule is absent")
    return _run_ast_rule(
        rules[rule_name],
        parameters=parameters,
        children=ordered_children,
        ceiling=ceiling,
        rules_by_name=rules,
        local_catalogs_by_id=local_catalogs_by_id or {},
    )


def execute_linked_catalog_transfer(
    recurrence: Mapping[str, Any],
    opcode: str,
    parameters: Mapping[str, Any],
    ordered_children: Sequence[Cell],
    ceiling: int,
    *,
    local_catalogs_by_id: Mapping[str, Mapping[str, Any]] | None = None,
) -> Cell:
    rule_catalog = recurrence["transfer_rule_catalog"]
    opcode_rows = recurrence["instruction_set"]["transfer_program_schema"][
        "ordered_transfer_opcode_records"
    ]
    opcode_row = next((row for row in opcode_rows if row["opcode"] == opcode), None)
    if opcode_row is None:
        raise TransferReject("transfer opcode row is absent")
    rule_id = opcode_row.get("transfer_rule_id")
    rule_rows = rule_catalog["ordered_transfer_rule_records"]
    rule = next((row for row in rule_rows if row["transfer_rule_id"] == rule_id), None)
    if rule is None:
        raise TransferReject("opcode transfer-rule identity did not resolve")
    rules = _rules_by_name(rule_catalog)
    return _run_ast_rule(
        rule,
        parameters=parameters,
        children=ordered_children,
        ceiling=ceiling,
        rules_by_name=rules,
        local_catalogs_by_id=local_catalogs_by_id or {},
    )


def execute_transfer(
    opcode: str,
    parameters: Mapping[str, Any],
    ordered_children: Sequence[Cell],
    ceiling: int,
    *,
    wrapper_evidence_valid: bool = True,
    local_catalogs_by_id: Mapping[str, Mapping[str, Any]] | None = None,
) -> Cell:
    """Execute one closed transfer opcode with strict parameters and children."""

    contract = EXPECTED_TRANSFER_OPCODE_CONTRACTS.get(opcode)
    if contract is None:
        raise TransferReject("unknown transfer opcode")
    required = contract["ordered_required_parameter_names"]
    if list(parameters) != required:
        raise TransferReject("transfer parameters are absent, extra, or out of order")

    mode = contract["child_read_mode"]
    expected_child_counts = {
        "NONE": 0,
        "ONE_EARLIER_POSITION_V1": 1,
        "RESOLVE_BOUND_LOCAL_CATALOG_V1": 0,
    }
    if (
        mode in expected_child_counts
        and len(ordered_children) != expected_child_counts[mode]
    ):
        raise TransferReject("transfer child count does not match child-read mode")

    if opcode == "CELL_FIXED_OCTETS_V1":
        return transfer_fixed(parameters["fixed_canonical_octets"], ceiling)
    if opcode == "CELL_BOOLEAN_LITERAL_V1":
        return transfer_boolean(parameters["boolean_literal"], ceiling)
    if opcode == "CELL_SAFE_INTEGER_INTERVAL_V1":
        return transfer_safe_integer(
            parameters["integer_minimum"], parameters["integer_maximum"], ceiling
        )
    if opcode == "CELL_FINITE_TEXT_V1":
        return transfer_finite_text(parameters["ordered_literals"], ceiling)
    if opcode == "CELL_BOUNDED_TEXT_OCTETS_V1":
        return transfer_bounded_text(
            parameters["minimum_canonical_octets"],
            parameters["maximum_canonical_octets"],
            ceiling,
        )
    if opcode == "CELL_RELAXED_JSON_STRING_V1":
        return transfer_relaxed_json_string(ceiling)
    if opcode == "CELL_DERIVED_IDENTITY_V1":
        return transfer_fixed(parameters["canonical_octets"], ceiling)
    if opcode == "CELL_NULLABLE_V1":
        return transfer_nullable(ordered_children[0], ceiling)
    if opcode == "CELL_CHILD_BOUNDS_ALIAS_V1":
        return transfer_alias(ordered_children[0], ceiling)
    if opcode in {"CELL_ARRAY_BATCH_V1", "CELL_ARRAY_STREAM_V1"}:
        if opcode == "CELL_ARRAY_BATCH_V1":
            observer = parameters["observer_closure_record"]
            if (
                not isinstance(observer, dict)
                or observer.get("batch_eligible") is not True
            ):
                raise TransferReject(
                    "batch transfer lacks an eligible observer closure"
                )
            runs = parameters["ordered_run_records"]
            if (
                not isinstance(runs, list)
                or sum(
                    u128(row.get("item_count"), name="run.item_count") for row in runs
                )
                != parameters["maximum_items"]
            ):
                raise TransferReject("batch runs do not cover maximum cardinality")
        return transfer_array(
            ordered_children[0],
            parameters["minimum_items"],
            parameters["maximum_items"],
            ceiling,
            mode="BATCH" if opcode == "CELL_ARRAY_BATCH_V1" else "STREAM",
        )
    if opcode == "CELL_RECORD_V1":
        if parameters["record_member_count"] != len(ordered_children):
            raise TransferReject("record member count disagrees with child reads")
        member_records = parameters["ordered_member_records"]
        if not isinstance(member_records, list) or len(member_records) != len(
            ordered_children
        ):
            raise TransferReject("record member records disagree with child reads")
        return transfer_record(
            ordered_children,
            parameters["record_syntax_octets_excluding_child_values"],
            ceiling,
        )
    if opcode == "CELL_UNION_V1":
        alternatives = parameters["ordered_alternative_records"]
        if not isinstance(alternatives, list) or len(alternatives) != len(
            ordered_children
        ):
            raise TransferReject("union alternatives disagree with child reads")
        return transfer_union(ordered_children, ceiling)
    if opcode == "CELL_CODEC_INTERSECTION_V1":
        return transfer_codec_intersection(
            ordered_children[0],
            parameters["ordered_codec_coordinate_records"],
            ceiling,
        )
    if opcode in {
        "CELL_SAFE_RELAXATION_V1",
        "CELL_SCOPE_ROOT_V1",
        "CELL_APPLICATION_WRAPPER_V1",
    }:
        return transfer_validated_alias(
            ordered_children[0], ceiling, evidence_valid=wrapper_evidence_valid
        )
    if opcode == "CELL_LOCAL_SHUTDOWN_SWEEP_V2":
        catalog_id = parameters["local_shutdown_analytic_catalog_id"]
        if local_catalogs_by_id is None or catalog_id not in local_catalogs_by_id:
            raise TransferReject("bound local analytic catalog did not resolve")
        return transfer_local_shutdown(local_catalogs_by_id[catalog_id], ceiling)
    raise AssertionError("closed opcode map and dispatcher diverged")


def _load_catalog() -> dict[str, Any]:
    return json.loads(SEED_CATALOG_PATH.read_text(encoding="utf-8"))


def _load_registry() -> dict[str, Any]:
    return json.loads(STRUCTURAL_REGISTRY_PATH.read_text(encoding="utf-8"))


def _load_inventory() -> dict[str, Any]:
    return json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))


def _compact_canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _derive_case69_local_baseline_upper(
    profile_program: Mapping[str, Any],
    local_catalog: Mapping[str, Any],
    inventory: Mapping[str, Any],
) -> int:
    """Independent typed execution proposed for case 69's P2 intersection."""

    if (
        profile_program.get("case_position") != 69
        or profile_program.get("profile_position") != 3
        or profile_program.get("operation_kind") != "LOCAL_SHUTDOWN"
    ):
        raise TransferReject("local baseline program is not bound to case 69/profile 3")
    fixed_operations = profile_program.get("ordered_fixed_authority_operations")
    if not isinstance(fixed_operations, list) or len(fixed_operations) != 1:
        raise TransferReject("local baseline has no unique fixed-spec operation")
    fixed = fixed_operations[0]
    pointer = "/fixture_records/operation_specs/LOCAL_SHUTDOWN"
    if fixed.get("inventory_json_pointer") != pointer:
        raise TransferReject("local baseline fixed-spec pointer differs")
    spec_record = inventory["fixture_records"]["operation_specs"]["LOCAL_SHUTDOWN"]
    spec_bytes = _compact_canonical_bytes(spec_record)
    if (
        fixed.get("expected_authority_id") != spec_record.get("operation_spec_id")
        or fixed.get("fixed_canonical_octets") != len(spec_bytes)
        or fixed.get("fixed_canonical_sha256") != hashlib.sha256(spec_bytes).hexdigest()
        or local_catalog.get("baseline_inventory_json_pointer") != pointer
        or local_catalog.get("baseline_operation_spec_id")
        != spec_record.get("operation_spec_id")
    ):
        raise TransferReject("local baseline spec is not authority-bound")

    transfer = profile_program.get("conditioning_transfer_program")
    if not isinstance(transfer, Mapping):
        raise TransferReject("local profile has no typed conditioning program")
    p2 = transfer.get("p2_upper_bound_program")
    if not isinstance(p2, Mapping):
        raise TransferReject("local profile has no typed P2 program")
    instructions = p2.get("ordered_instruction_records")
    if not isinstance(instructions, list) or len(instructions) != 4:
        raise TransferReject("local profile P2 instruction chain differs")
    local_instruction = instructions[2]
    if (
        local_instruction.get("opcode")
        != "EXECUTE_LOCAL_SHUTDOWN_BASELINE_ANALYTIC_EXACT_V1"
        or local_instruction.get("parameters", {}).get(
            "local_shutdown_analytic_catalog_id"
        )
        != local_catalog.get("local_shutdown_analytic_catalog_id")
        or local_instruction.get("parameters", {}).get("fixed_spec_operation_position")
        != 1
    ):
        raise TransferReject("local analytic source identity differs")
    length_program = local_catalog.get("batch_unsaturated_program")
    if length_program.get("opcode") != "PIECEWISE_AFFINE_DECIMAL_WIDTH_V1":
        raise TransferReject("local baseline length program opcode differs")
    batch_limit = _safe_integer(
        spec_record["spec"]["maximum_terminal_ingress_batches"],
        name="maximum_terminal_ingress_batches",
    )
    if (
        not length_program["valid_minimum"]
        <= batch_limit
        <= length_program["valid_maximum"]
    ):
        raise TransferReject("local baseline is outside the unsaturated program")
    derived = checked_add(
        length_program["constant_octets"],
        checked_mul(length_program["linear_coefficient"], batch_limit),
        checked_mul(length_program["decimal_width_coefficient"], len(str(batch_limit))),
    )
    if derived != local_catalog.get("baseline_attainable_maximum_octets"):
        raise TransferReject("executed local baseline differs from catalog comparator")
    return derived


def _derive_owner_overheads_from_registry_and_plan(
    catalog: Mapping[str, Any], registry: Mapping[str, Any], owner_type_name: str
) -> dict[str, int]:
    descriptors = registry["ordered_external_type_descriptors"]
    owner_descriptor = next(
        row for row in descriptors if row["type_name"] == owner_type_name
    )
    union_descriptor = next(
        row
        for row in descriptors
        if row["type_form"] == "TAGGED_UNION"
        and row["tagged_union_descriptor"]["payload_owner_type_name"] == owner_type_name
    )["tagged_union_descriptor"]
    payload_member_name = union_descriptor["payload_typed_member_path"][0]

    template = next(
        row
        for row in catalog["logical_plan_recipe_catalog"][
            "ordered_logical_plan_templates"
        ]
        if row["root_type_name"] == owner_type_name
    )
    steps = {
        row["template_step_position"]: row for row in template["ordered_template_steps"]
    }
    record_step = next(
        row
        for row in steps.values()
        if row["derivation_kind"] == "RECORD_MEMBER_FOLD"
        and row["type_name"] == owner_type_name
    )
    member_records = record_step["recurrence_parameters"]["ordered_member_records"]
    assert [row["member_name"] for row in member_records] == [
        row["member_name"] for row in owner_descriptor["record_member_descriptors"]
    ]

    overhead_by_alternative: dict[str, int] = {}
    for alternative in union_descriptor["ordered_alternatives"]:
        discriminator_literals = {
            row["member_name"]: row["text_value"]
            for row in alternative["ordered_discriminator_literals"]
        }
        overhead = record_step["recurrence_parameters"][
            "record_syntax_octets_excluding_child_values"
        ]
        for member in member_records:
            member_name = member["member_name"]
            if member_name == payload_member_name:
                continue
            if member_name in discriminator_literals:
                overhead = checked_add(
                    overhead,
                    canonical_string_octets(discriminator_literals[member_name]),
                )
                continue
            child = steps[member["child_step_position"]]
            parameters = child["recurrence_parameters"]
            if child["derivation_kind"] == "TEXT_FINITE":
                literals = parameters["ordered_literals"]
                if len(literals) != 1:
                    raise AssertionError(
                        f"non-discriminator sibling {member_name} is not exact"
                    )
                exact_octets = canonical_string_octets(literals[0])
            elif child["derivation_kind"] == "TEXT_BUILTIN_BOUNDED":
                if (
                    parameters["minimum_canonical_octets"]
                    != parameters["maximum_canonical_octets"]
                ):
                    raise AssertionError(
                        f"non-discriminator sibling {member_name} is not fixed width"
                    )
                exact_octets = parameters["minimum_canonical_octets"]
            else:
                raise AssertionError(
                    f"unsupported owner sibling transfer: {child['derivation_kind']}"
                )
            overhead = checked_add(overhead, exact_octets)
        overhead_by_alternative[alternative["alternative_name"]] = overhead
    return overhead_by_alternative


def _all_string_formula_paths(value: object, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}/{key}"
            if "formula" in key.lower() and isinstance(child, str):
                found.append(child_path)
            found.extend(_all_string_formula_paths(child, child_path))
    elif isinstance(value, list):
        for position, child in enumerate(value):
            found.extend(_all_string_formula_paths(child, f"{path}/{position}"))
    return found


def _micro_local_catalog() -> dict[str, Any]:
    states: list[dict[str, Any]] = []
    for position in range(1, 13):
        components = [
            position - 1,
            "NOT_EVALUATED" if position == 1 else "CANDIDATE_EVALUATED",
            None,
            None,
            2 if position >= 3 else None,
            1948 if position >= 3 else None,
            1947 if position >= 3 else None,
            524380 if position >= 3 else None,
        ]
        states.append(
            {
                "controller_state_position": position,
                "controller_state_id": f"state-{position}",
                "state_kind": (
                    "INITIAL"
                    if position == 1
                    else "TERMINAL"
                    if position == 12
                    else "INTERMEDIATE"
                ),
                "ordered_state_components": components,
            }
        )
    transitions = [
        {
            "controller_transition_position": position,
            "source_controller_state_id": states[position - 1]["controller_state_id"],
            "target_controller_state_id": states[position]["controller_state_id"],
            "expected_target_state_components": states[position][
                "ordered_state_components"
            ],
        }
        for position in range(1, 12)
    ]
    return {
        "ordered_controller_state_records": states,
        "ordered_controller_transition_records": transitions,
        "winner_attainable_maximum_octets": 524380,
    }


def _ast_micro_scenarios() -> list[
    tuple[str, dict[str, Any], list[Cell], int, dict[str, Mapping[str, Any]], Cell]
]:
    coordinate = {
        "codec_byte_bound_relation": "LT",
        "codec_octet_limit": 12,
        "codec_owner_type_name": "Owner",
        "codec_owner_typed_member_path": ["payload"],
        "coordinate_position": 1,
        "coordinate_scope": "OWNER_PAYLOAD_RESIDUAL",
        "derived_payload_octet_ceiling": 8,
        "minimum_sibling_and_syntax_octets": 3,
        "selected_union_alternative_name": "ALT",
    }
    item = Cell(MAY_BE_NONEMPTY, 1, 2)
    bounded_child = Cell(MAY_BE_NONEMPTY, 2, 8)
    local_catalog = {
        **_micro_local_catalog(),
        "local_shutdown_analytic_catalog_id": "micro-local-catalog",
    }
    return [
        (
            "CELL_FIXED_OCTETS_V1",
            {"fixed_canonical_octets": 7},
            [],
            10,
            {},
            transfer_fixed(7, 10),
        ),
        (
            "CELL_BOOLEAN_LITERAL_V1",
            {"boolean_literal": None},
            [],
            U128_MAX,
            {},
            transfer_boolean(None, U128_MAX),
        ),
        (
            "CELL_SAFE_INTEGER_INTERVAL_V1",
            {
                "integer_minimum": -10,
                "integer_maximum": 9,
                "ordered_probe_values": [-10, -9, -1, 0, 9],
            },
            [],
            U128_MAX,
            {},
            transfer_safe_integer(-10, 9, U128_MAX),
        ),
        (
            "CELL_FINITE_TEXT_V1",
            {
                "text_language_position": 1,
                "text_language_id": "language",
                "ordered_literals": ["", '"', "é"],
            },
            [],
            U128_MAX,
            {},
            transfer_finite_text(["", '"', "é"], U128_MAX),
        ),
        (
            "CELL_BOUNDED_TEXT_OCTETS_V1",
            {
                "built_in_language_kind": "LOWERCASE_SHA256",
                "minimum_canonical_octets": 2,
                "maximum_canonical_octets": 66,
                "text_language_id": "language",
                "text_language_position": 1,
            },
            [],
            10,
            {},
            transfer_bounded_text(2, 66, 10),
        ),
        (
            "CELL_RELAXED_JSON_STRING_V1",
            {
                "text_language_position": 1,
                "text_language_id": "language",
                "language_kind": "ASCII_DFA",
                "built_in_language_kind": None,
                "ascii_dfa_id": "dfa",
                "unicode_identifier_profile_id": None,
                "minimum_utf8_octets": None,
                "maximum_utf8_octets": None,
                "minimum_decoded_octets": None,
                "maximum_decoded_octets": None,
                "decimal_maximum": None,
            },
            [],
            9,
            {},
            transfer_relaxed_json_string(9),
        ),
        (
            "CELL_DERIVED_IDENTITY_V1",
            {"canonical_octets": 66},
            [],
            100,
            {},
            transfer_fixed(66, 100),
        ),
        (
            "CELL_NULLABLE_V1",
            {"child_step_position": 1},
            [bounded_child],
            10,
            {},
            transfer_nullable(bounded_child, 10),
        ),
        (
            "CELL_CHILD_BOUNDS_ALIAS_V1",
            {"referenced_type_name": "Referenced", "child_step_position": 1},
            [bounded_child],
            10,
            {},
            transfer_alias(bounded_child, 10),
        ),
        (
            "CELL_ARRAY_BATCH_V1",
            {
                "minimum_items": 0,
                "maximum_items": 3,
                "item_value_schema_id": "item-schema",
                "item_step_position": 1,
                "ordered_run_records": [{"item_count": 3}],
                "observer_closure_record": {"batch_eligible": True},
            },
            [item],
            20,
            {},
            transfer_array(item, 0, 3, 20, mode="BATCH"),
        ),
        (
            "CELL_ARRAY_STREAM_V1",
            {
                "minimum_items": 0,
                "maximum_items": 3,
                "item_step_position": 1,
            },
            [item],
            20,
            {},
            transfer_array(item, 0, 3, 20, mode="STREAM"),
        ),
        (
            "CELL_RECORD_V1",
            {
                "record_member_count": 2,
                "ordered_member_records": [{"member": 1}, {"member": 2}],
                "record_syntax_octets_excluding_child_values": 13,
            },
            [Cell(MAY_BE_NONEMPTY, 4, 4), Cell(MAY_BE_NONEMPTY, 1, 3)],
            100,
            {},
            Cell(MAY_BE_NONEMPTY, 18, 20),
        ),
        (
            "CELL_UNION_V1",
            {
                "ordered_alternative_records": [{}, {}, {}],
                "owner_type_name": "Owner",
                "owner_typed_member_path": ["payload"],
            },
            [Cell(MAY_BE_NONEMPTY, 4, 5), bounded_child, empty()],
            10,
            {},
            transfer_union([Cell(MAY_BE_NONEMPTY, 4, 5), bounded_child, empty()], 10),
        ),
        (
            "CELL_CODEC_INTERSECTION_V1",
            {
                "ordered_codec_coordinate_records": [coordinate],
                "child_step_position": 1,
            },
            [Cell(MAY_BE_NONEMPTY, 2, 100)],
            U128_MAX,
            {},
            Cell(MAY_BE_NONEMPTY, 2, 8),
        ),
        (
            "CELL_SAFE_RELAXATION_V1",
            {
                "safe_relaxation_rule_id": "rule",
                "authority_predicate_locator": [],
                "child_step_position": 1,
            },
            [bounded_child],
            10,
            {},
            bounded_child,
        ),
        (
            "CELL_SCOPE_ROOT_V1",
            {
                "case_binding": {},
                "fixed_authority_bindings": [],
                "child_step_position": 1,
            },
            [bounded_child],
            10,
            {},
            bounded_child,
        ),
        (
            "CELL_APPLICATION_WRAPPER_V1",
            {
                "ordered_application_invocation_records": [],
                "child_step_position": 1,
            },
            [bounded_child],
            10,
            {},
            bounded_child,
        ),
        (
            "CELL_LOCAL_SHUTDOWN_SWEEP_V2",
            {"local_shutdown_analytic_catalog_id": "micro-local-catalog"},
            [],
            U128_MAX,
            {"micro-local-catalog": local_catalog},
            transfer_local_shutdown(local_catalog, U128_MAX),
        ),
    ]


def test_identity_bound_reference_ast_executes_all_hand_micro_oracles() -> None:
    primitive_records = REFERENCE_TRANSFER_RULE_CATALOG[
        "ordered_primitive_opcode_records"
    ]
    assert [row["opcode"] for row in primitive_records] == list(AST_OPCODE_SIGNATURES)
    rules = REFERENCE_TRANSFER_RULE_CATALOG["ordered_transfer_rule_records"]
    preceding_rule_ids: set[str] = set()
    for rule in rules:
        payload = {
            key: value for key, value in rule.items() if key != "transfer_rule_id"
        }
        assert rule["transfer_rule_id"] == _semantic_id_for_test(
            TRANSFER_RULE_DOMAIN, payload
        )
        _validate_ast_nodes(rule["program"])
        assert set(_called_transfer_rule_ids(rule["program"])) <= preceding_rule_ids
        preceding_rule_ids.add(rule["transfer_rule_id"])

    for (
        opcode,
        parameters,
        children,
        ceiling,
        local_catalogs,
        expected,
    ) in _ast_micro_scenarios():
        assert (
            execute_rule_catalog_transfer(
                REFERENCE_TRANSFER_RULE_CATALOG,
                opcode,
                parameters,
                children,
                ceiling,
                local_catalogs_by_id=local_catalogs,
            )
            == expected
        ), opcode


def test_reference_ast_rejects_unknown_members_opcodes_and_subrule_ids() -> None:
    fixed_rule = _rules_by_name(REFERENCE_TRANSFER_RULE_CATALOG)[
        "FIXED_EXACT_OR_EMPTY_V1"
    ]
    extra_member_program = json.loads(json.dumps(fixed_rule["program"]))
    extra_member_program["unexpected"] = 1
    with pytest.raises(TransferReject, match="schema differs"):
        _validate_ast_nodes(extra_member_program)

    unknown_opcode_program = json.loads(json.dumps(fixed_rule["program"]))
    unknown_opcode_program["opcode"] = "EXECUTE_HOST_LANGUAGE_V1"
    with pytest.raises(TransferReject, match="unknown opcode"):
        _validate_ast_nodes(unknown_opcode_program)

    mutated_catalog = json.loads(json.dumps(REFERENCE_TRANSFER_RULE_CATALOG))
    codec_rule = next(
        row
        for row in mutated_catalog["ordered_transfer_rule_records"]
        if row["transfer_rule_name"] == "RECOMPUTED_CODEC_RESIDUAL_INTERSECTION_V1"
    )
    call_node = next(
        node
        for node in _walk_ast_mappings(codec_rule["program"])
        if node.get("opcode") == "CALL_RULE_V1"
    )
    call_node["transfer_rule_id"] = "0" * 64
    coordinate = _ast_micro_scenarios()[13][1]["ordered_codec_coordinate_records"][0]
    with pytest.raises(TransferReject, match="identity is absent"):
        execute_rule_catalog_transfer(
            mutated_catalog,
            "CELL_CODEC_INTERSECTION_V1",
            {
                "ordered_codec_coordinate_records": [coordinate],
                "child_step_position": 1,
            },
            [Cell(MAY_BE_NONEMPTY, 2, 100)],
            U128_MAX,
        )


def test_hand_micro_oracles_close_every_ordinary_transfer_family() -> None:
    assert transfer_fixed(7, 10) == Cell(MAY_BE_NONEMPTY, 7, 7)
    assert transfer_fixed(7, 6) == empty()

    assert transfer_boolean(None, U128_MAX) == Cell(MAY_BE_NONEMPTY, 4, 5)
    assert transfer_boolean(True, 4) == Cell(MAY_BE_NONEMPTY, 4, 4)
    assert transfer_boolean(False, 4) == empty()
    assert transfer_boolean(None, 4) == Cell(MAY_BE_NONEMPTY, 4, 4)

    assert transfer_safe_integer(-10, 9, U128_MAX) == Cell(MAY_BE_NONEMPTY, 1, 3)
    assert transfer_safe_integer(10, 99, U128_MAX) == Cell(MAY_BE_NONEMPTY, 2, 2)
    assert transfer_safe_integer(-9, -1, U128_MAX) == Cell(MAY_BE_NONEMPTY, 2, 2)

    assert transfer_finite_text(["", '"', "é"], U128_MAX) == Cell(MAY_BE_NONEMPTY, 2, 4)
    assert transfer_bounded_text(2, 66, 10) == Cell(MAY_BE_NONEMPTY, 2, 10)
    assert transfer_relaxed_json_string(9) == Cell(MAY_BE_NONEMPTY, 2, 9)
    assert transfer_relaxed_json_string(1) == empty()

    child = Cell(MAY_BE_NONEMPTY, 2, 8)
    assert transfer_nullable(child, 10) == Cell(MAY_BE_NONEMPTY, 2, 8)
    assert transfer_alias(child, 10) == child

    item = Cell(MAY_BE_NONEMPTY, 1, 2)
    assert transfer_array(item, 0, 3, 20, mode="BATCH") == Cell(
        MAY_BE_NONEMPTY, 2, 10, (3, 6, 2)
    )
    assert transfer_array(item, 0, 3, 20, mode="STREAM") == Cell(
        MAY_BE_NONEMPTY, 2, 10, (3, 3, 6, 2)
    )
    assert transfer_array(item, 0, 3, 8, mode="BATCH") == Cell(
        MAY_BE_NONEMPTY, 2, 8, (3, 6, 2)
    )
    assert transfer_array(empty(), 0, 3, 20, mode="BATCH") == Cell(
        MAY_BE_NONEMPTY, 2, 2
    )

    assert transfer_record(
        [Cell(MAY_BE_NONEMPTY, 4, 4), Cell(MAY_BE_NONEMPTY, 1, 3)],
        13,
        100,
    ) == Cell(MAY_BE_NONEMPTY, 18, 20)
    assert transfer_record([empty()], 2, 100) == empty()
    assert transfer_record([Cell(MAY_BE_NONEMPTY, 2, U128_MAX)], 2, 100) == Cell(
        MAY_BE_NONEMPTY, 4, 100
    )
    assert transfer_array(
        Cell(MAY_BE_NONEMPTY, 2, U128_MAX), 0, 3, 100, mode="BATCH"
    ) == Cell(MAY_BE_NONEMPTY, 2, 100, (3, 100, 2))
    assert transfer_union([Cell(MAY_BE_NONEMPTY, 4, 5), child, empty()], 10) == Cell(
        MAY_BE_NONEMPTY, 2, 8
    )

    coordinates = [
        {
            "codec_byte_bound_relation": "LE",
            "codec_octet_limit": 20,
            "coordinate_scope": "SELF_TYPE",
            "minimum_sibling_and_syntax_octets": 0,
            "derived_payload_octet_ceiling": 20,
        },
        {
            "codec_byte_bound_relation": "LT",
            "codec_octet_limit": 12,
            "coordinate_scope": "OWNER_PAYLOAD_RESIDUAL",
            "minimum_sibling_and_syntax_octets": 3,
            "derived_payload_octet_ceiling": 8,
        },
    ]
    assert transfer_codec_intersection(
        Cell(MAY_BE_NONEMPTY, 2, 100), coordinates, U128_MAX
    ) == Cell(MAY_BE_NONEMPTY, 2, 8)

    assert transfer_validated_alias(child, 10, evidence_valid=True) == child
    local = transfer_local_shutdown(_micro_local_catalog(), U128_MAX)
    assert (local.status, local.lower, local.upper, len(local.state)) == (
        MAY_BE_NONEMPTY,
        524380,
        524380,
        8,
    )


def test_checked_uint128_cap_and_reject_paths_are_closed() -> None:
    assert checked_add(U128_MAX - 1, 1) == U128_MAX
    assert checked_mul(U128_MAX, 1) == U128_MAX
    assert checked_sub(0, 0) == 0
    assert capped_add(10, 7, 3) == CappedU128(10, False)
    assert capped_add(10, 7, 4) == CappedU128(10, True)
    assert capped_mul(10, 2, 5) == CappedU128(10, False)
    assert capped_mul(10, 2, 6) == CappedU128(10, True)
    assert capped_mul(U128_MAX, U128_MAX, 2) == CappedU128(U128_MAX, True)
    with pytest.raises(TransferReject, match="addition overflow"):
        checked_add(U128_MAX, 1)
    with pytest.raises(TransferReject, match="multiplication overflow"):
        checked_mul(U128_MAX, 2)
    with pytest.raises(TransferReject, match="subtraction underflow"):
        checked_sub(0, 1)
    with pytest.raises(TransferReject, match="not UInt128"):
        u128(True)
    with pytest.raises(TransferReject, match="signed I-JSON safe integer"):
        transfer_safe_integer(-IJSON_SAFE_INTEGER_MAX - 1, 0, U128_MAX)
    with pytest.raises(TransferReject, match="inverted"):
        transfer_safe_integer(1, 0, U128_MAX)

    wrong_residual = {
        "codec_byte_bound_relation": "LT",
        "codec_octet_limit": 12,
        "coordinate_scope": "OWNER_PAYLOAD_RESIDUAL",
        "minimum_sibling_and_syntax_octets": 3,
        "derived_payload_octet_ceiling": 9,
    }
    with pytest.raises(TransferReject, match="not derivable"):
        derive_coordinate_payload_ceiling(wrong_residual)
    with pytest.raises(TransferReject, match="underflow"):
        derive_coordinate_payload_ceiling(
            {
                **wrong_residual,
                "codec_octet_limit": 0,
                "minimum_sibling_and_syntax_octets": 0,
                "derived_payload_octet_ceiling": 0,
            }
        )


def test_seed_catalog_must_publish_closed_typed_transfer_opcode_records() -> None:
    catalog = _load_catalog()
    recurrence = catalog["recurrence_catalog"]
    instruction_set = recurrence["instruction_set"]
    rows = instruction_set["transfer_program_schema"]["ordered_transfer_opcode_records"]
    by_opcode = {row["opcode"]: row for row in rows}
    assert len(by_opcode) == len(rows) == len(EXPECTED_TRANSFER_OPCODE_CONTRACTS)
    assert set(by_opcode) == set(EXPECTED_TRANSFER_OPCODE_CONTRACTS)

    required_record_members = {
        "opcode_position",
        "opcode",
        "semantic_rule",
        "ordered_required_parameter_names",
        "child_read_mode",
        "state_rule",
        "transfer_rule_id",
        "unknown_or_extra_member_policy",
    }
    for opcode, expected in EXPECTED_TRANSFER_OPCODE_CONTRACTS.items():
        row = by_opcode[opcode]
        assert set(row) == required_record_members, opcode
        assert {key: row[key] for key in expected} == expected, opcode
        assert row["unknown_or_extra_member_policy"] == "REJECT", opcode

    # The two published cell contracts must be one schema and must include
    # state; a three-member prose invariant is not an executable cell.
    expected_cell_members = [
        "cell_status",
        "certified_lower_bound_octets",
        "certified_upper_bound_octets",
        "ordered_state_components",
    ]
    assert recurrence["cell_invariant"]["cell_members"] == expected_cell_members
    assert instruction_set["cell_contract"]["ordered_member_names"] == (
        expected_cell_members
    )


def test_seed_catalog_must_publish_and_execute_identity_bound_transfer_rule_ast() -> (
    None
):
    catalog = _load_catalog()
    recurrence = catalog["recurrence_catalog"]
    assert "transfer_rule_catalog" in recurrence
    rule_catalog = recurrence["transfer_rule_catalog"]
    assert set(rule_catalog) == {
        "transfer_rule_catalog_version",
        "evaluation_order",
        "unknown_or_extra_ast_member_policy",
        "ordered_primitive_opcode_records",
        "ordered_transfer_rule_records",
        "transfer_rule_catalog_id",
    }
    assert rule_catalog["transfer_rule_catalog_version"] == (
        TRANSFER_RULE_CATALOG_VERSION
    )
    assert (
        rule_catalog["ordered_primitive_opcode_records"]
        == (REFERENCE_TRANSFER_RULE_CATALOG["ordered_primitive_opcode_records"])
    )
    catalog_payload = {
        key: value
        for key, value in rule_catalog.items()
        if key != "transfer_rule_catalog_id"
    }
    assert rule_catalog["transfer_rule_catalog_id"] == _semantic_id_for_test(
        TRANSFER_RULE_CATALOG_DOMAIN, catalog_payload
    )

    rules = rule_catalog["ordered_transfer_rule_records"]
    assert len(rules) == len(_reference_rule_programs())
    preceding_rule_ids: set[str] = set()
    for position, rule in enumerate(rules, 1):
        assert set(rule) == {
            "transfer_rule_version",
            "rule_position",
            "transfer_rule_name",
            "ordered_parameter_names",
            "ordered_parameter_type_records",
            "result_type",
            "program",
            "transfer_rule_id",
        }
        assert rule["rule_position"] == position
        assert rule["transfer_rule_version"] == TRANSFER_RULE_VERSION
        payload = {
            key: value for key, value in rule.items() if key != "transfer_rule_id"
        }
        assert rule["transfer_rule_id"] == _semantic_id_for_test(
            TRANSFER_RULE_DOMAIN, payload
        )
        _validate_ast_nodes(rule["program"])
        assert set(_called_transfer_rule_ids(rule["program"])) <= preceding_rule_ids
        preceding_rule_ids.add(rule["transfer_rule_id"])

    opcode_rows = recurrence["instruction_set"]["transfer_program_schema"][
        "ordered_transfer_opcode_records"
    ]
    rule_by_name = _rules_by_name(rule_catalog)
    for row in opcode_rows:
        expected_name = TRANSFER_RULE_NAME_BY_OPCODE[row["opcode"]]
        assert (
            row["transfer_rule_id"] == rule_by_name[expected_name]["transfer_rule_id"]
        )

    # Execute the catalog-carried AST, following each opcode's identity link,
    # and compare it with independently authored hand oracles.
    for (
        opcode,
        parameters,
        children,
        ceiling,
        local_catalogs,
        expected,
    ) in _ast_micro_scenarios():
        assert (
            execute_linked_catalog_transfer(
                recurrence,
                opcode,
                parameters,
                children,
                ceiling,
                local_catalogs_by_id=local_catalogs,
            )
            == expected
        ), opcode


def test_seed_catalog_must_use_structured_checked_arithmetic_and_signed_integer_type() -> (
    None
):
    catalog = _load_catalog()
    recurrence = catalog["recurrence_catalog"]
    assert _all_string_formula_paths(recurrence) == []

    policy = recurrence["arithmetic_policy"]
    assert policy["ordered_arithmetic_opcode_records"] == [
        {
            "opcode_position": 1,
            "opcode": "CHECKED_ADD_U128_V1",
            "overflow_policy": "REJECT_BEFORE_COMMIT",
        },
        {
            "opcode_position": 2,
            "opcode": "CHECKED_SUB_U128_V1",
            "underflow_policy": "REJECT_BEFORE_COMMIT",
        },
        {
            "opcode_position": 3,
            "opcode": "CHECKED_MUL_U128_V1",
            "overflow_policy": "REJECT_BEFORE_COMMIT",
        },
        {
            "opcode_position": 4,
            "opcode": "CAPPED_ADD_U128_TO_CEILING_V1",
            "overflow_policy": "SATURATE_WITH_EXCEEDED_CEILING_TRUE",
        },
        {
            "opcode_position": 5,
            "opcode": "CAPPED_MUL_U128_TO_CEILING_V1",
            "overflow_policy": "SATURATE_WITH_EXCEEDED_CEILING_TRUE",
        },
        {
            "opcode_position": 6,
            "opcode": "MIN_U128_V1",
            "empty_operand_policy": "REJECT",
        },
    ]

    value_types = recurrence["instruction_set"]["parameter_schema_record_schema"][
        "value_type_enum"
    ]
    assert "SIGNED_SAFE_INTEGER" in value_types
    integer_kernel = next(
        row
        for row in recurrence["ordered_derivation_kernel_records"]
        if row["derivation_kind"] == "SAFE_INTEGER_BAND"
    )
    types = {
        row["parameter_name"]: row["value_type"]
        for row in integer_kernel["ordered_parameter_schema_records"]
    }
    assert types["integer_minimum"] == "SIGNED_SAFE_INTEGER"
    assert types["integer_maximum"] == "SIGNED_SAFE_INTEGER"


def test_case69_requires_executed_profile_conditioned_cell_intersection() -> None:
    catalog = _load_catalog()
    inventory = _load_inventory()
    recurrence = catalog["recurrence_catalog"]
    recipe = catalog["logical_plan_recipe_catalog"]
    profile_program = next(
        row
        for row in recipe["ordered_profile_conditioning_program_records"]
        if row["case_position"] == 69
    )
    template = next(
        row
        for row in recipe["ordered_logical_plan_templates"]
        if row["logical_plan_template_id"]
        == profile_program["logical_plan_template_id"]
    )
    root_step = next(
        row
        for row in template["ordered_template_steps"]
        if row["template_step_position"] == template["root_step_position"]
    )
    root_ceiling = min(
        derive_coordinate_payload_ceiling(coordinate)
        for coordinate in root_step["recurrence_parameters"][
            "ordered_codec_coordinate_records"
        ]
    )
    assert root_ceiling == 524287
    root_cell = Cell(MAY_BE_NONEMPTY, 1, root_ceiling)
    after_scope_alias = transfer_validated_alias(
        root_cell, root_ceiling, evidence_valid=True
    )
    after_application_alias = transfer_validated_alias(
        after_scope_alias, root_ceiling, evidence_valid=True
    )
    assert after_application_alias.upper == 524287

    local_catalog = recurrence["local_shutdown_analytic_catalog"]
    independently_derived = _derive_case69_local_baseline_upper(
        profile_program, local_catalog, inventory
    )
    assert independently_derived == 2581
    conditioned = transfer_derived_upper_intersection(
        after_application_alias,
        root_ceiling,
        independently_derived_upper=independently_derived,
    )
    assert conditioned.upper == 2581

    # A detached expected number and a P2 opcode label cannot perform this
    # transformation. The accepted dual-channel program binds the structural
    # cell, fixed spec, local analytic identity, and explicit intersection.
    assert "attainment_endpoint_contract" not in profile_program
    p2 = profile_program["conditioning_transfer_program"]["p2_upper_bound_program"]
    instructions = p2["ordered_instruction_records"]
    assert [row["opcode"] for row in instructions] == [
        "LOAD_STRUCTURAL_TEMPLATE_SUPERSET_CELL_V1",
        "LOAD_FIXED_AUTHORITY_SET_V1",
        "EXECUTE_LOCAL_SHUTDOWN_BASELINE_ANALYTIC_EXACT_V1",
        "INTERSECT_EXACT_ANALYTIC_WITH_STRUCTURAL_CELL_V1",
    ]
    assert instructions[2]["ordered_input_instruction_positions"] == [2]
    assert instructions[2]["parameters"] == {
        "local_shutdown_analytic_catalog_id": local_catalog[
            "local_shutdown_analytic_catalog_id"
        ],
        "fixed_spec_operation_position": 1,
    }
    assert instructions[3]["ordered_input_instruction_positions"] == [3, 1]
    assert instructions[3]["parameters"] == {
        "intersection_rule": ("EXACT_ANALYTIC_UPPER_MUST_NOT_EXCEED_STRUCTURAL_UPPER"),
        "empty_structural_cell_policy": "NO_GO",
        "analytic_above_structural_upper_policy": "NO_GO",
        "preserve_exact_attained_cell": True,
    }
    assert p2["root_instruction_position"] == 4


def test_template_child_reads_are_strict_postorder_and_parameter_bound() -> None:
    catalog = _load_catalog()
    templates = catalog["logical_plan_recipe_catalog"]["ordered_logical_plan_templates"]
    one_child_parameter = {
        "NULLABLE_BRANCH": "child_step_position",
        "OBJECT_REFERENCE": "child_step_position",
        "ASSOCIATIVE_HOMOGENEOUS_RUN_BATCH": "item_step_position",
        "ARRAY_STREAM_FOLD": "item_step_position",
        "CODEC_INTERSECTION": "child_step_position",
        "SAFE_RELAXATION": "child_step_position",
        "SCOPE_ROOT": "child_step_position",
        "APPLICATION_SCHEDULE_COUNT": "child_step_position",
    }
    for template in templates:
        for step in template["ordered_template_steps"]:
            position = step["template_step_position"]
            children = step["ordered_child_step_positions"]
            assert len(children) == len(set(children)), (
                template["template_position"],
                position,
            )
            assert all(1 <= child < position for child in children), (
                template["template_position"],
                position,
            )
            parameters = step["recurrence_parameters"]
            kind = step["derivation_kind"]
            if kind in one_child_parameter:
                assert children == [parameters[one_child_parameter[kind]]]
            elif kind == "RECORD_MEMBER_FOLD":
                assert children == [
                    row["child_step_position"]
                    for row in parameters["ordered_member_records"]
                ]
            elif kind == "TAGGED_UNION_BRANCH":
                assert children == [
                    row["child_step_position"]
                    for row in parameters["ordered_alternative_records"]
                ]
            else:
                assert children == []


def test_all_structured_owner_residuals_recompute_exactly() -> None:
    catalog = _load_catalog()
    registry = _load_registry()
    templates = catalog["logical_plan_recipe_catalog"]["ordered_logical_plan_templates"]
    owner_residuals: list[Mapping[str, Any]] = []
    for template in templates:
        for step in template["ordered_template_steps"]:
            if step["derivation_kind"] != "CODEC_INTERSECTION":
                continue
            for coordinate in step["recurrence_parameters"][
                "ordered_codec_coordinate_records"
            ]:
                if coordinate["coordinate_scope"] == "OWNER_PAYLOAD_RESIDUAL":
                    owner_residuals.append(coordinate)
                    assert (
                        derive_coordinate_payload_ceiling(coordinate)
                        == coordinate["derived_payload_octet_ceiling"]
                    )

    # Four result and four spec alternatives have owner-payload coordinates.
    assert len(owner_residuals) == 8
    independently_derived_overheads = {
        owner_type_name: _derive_owner_overheads_from_registry_and_plan(
            catalog, registry, owner_type_name
        )
        for owner_type_name in {
            "CapacityMeasurementOperationResultEvidence",
            "CapacityMeasurementOperationSpec",
        }
    }
    for coordinate in owner_residuals:
        assert (
            coordinate["minimum_sibling_and_syntax_octets"]
            == (
                independently_derived_overheads[coordinate["codec_owner_type_name"]][
                    coordinate["selected_union_alternative_name"]
                ]
            )
        )
    assert sorted(
        item["derived_payload_octet_ceiling"] for item in owner_residuals
    ) == [
        523724,
        523728,
        523738,
        523752,
        2096777,
        2096781,
        2096791,
        2096795,
    ]

#!/usr/bin/env python3
"""Derive the exact case-435 application-aware upper bound and certificate.

This standard-library-only solver reads frozen authorities as data.  It does
not import or execute the accepted rule runtime, dependency checker, maximum
producer, maximum verifier, or any candidate artifact.  Infinite scalar
domains are quotient by canonical-length and predicate-equivalent endpoint
representatives; every remaining status/method/reason/censoring/error branch
is enumerated.  The output is a portable proof certificate, not the separate
attainer required by A4-P6-C435-C2.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sys
from itertools import product
from typing import Any

SEED_PATH = "scripts/tests/raw_v8_step2_maximum_protocol_v2_seed_catalog_v49f.json"
INVENTORY_PATH = "tests/raw_v8_step2_inventory_v4_v49f.json"
REGISTRY_PATH = (
    "scripts/tests/raw_v8_step2_external_schema_v2_structural_registry_v49f.json"
)
LITERAL_PATH = (
    "scripts/tests/raw_v8_step2_external_schema_v2_rule_literal_authority_v49f.json"
)
APPLICATION_LEDGER_PATH = (
    "scripts/tests/raw_v8_step2_external_schema_v2_rule_application_ledger_v49f.json"
)
RUNTIME_PATH = (
    "scripts/tests/validate_raw_v8_step2_external_schema_v2_rule_runtime_v49f.py"
)
DEPENDENCY_ANALYZER_PATH = (
    "scripts/tests/check_raw_v8_step2_maximum_protocol_v2_"
    "case435_dependency_closure_v49f.py"
)

PINNED_SHA256 = {
    SEED_PATH: "a75a2f352e8513b7ff0043693a0c65ebbf4bc6f06859354789af69e1162b0e4f",
    INVENTORY_PATH: "de91eac92d1c36cf1670b2484392fbf1c633d75f928c8e70fcd5e71ae798db2b",
    REGISTRY_PATH: "9160297ff316c5931737c92f8b359f0a1e2ec22f0aa996ef3b09cf830dc96bf3",
    LITERAL_PATH: "aba3461059367904734e2eb9ae404787b9aab5ed4c3fbcd292925a364926cce2",
    APPLICATION_LEDGER_PATH: (
        "979d7affe2d745d46f5977d9d69a4d1efa473f95c1a374737bf34181d9dac282"
    ),
    RUNTIME_PATH: "47aa90d897e8dbae5e244b7c04cbd82dfe036b0292d36ef0f5552c868627ab22",
    DEPENDENCY_ANALYZER_PATH: (
        "f882042d0bd519ced260734a43a9ee2c9b390ffac965ebe7c04ac261c2932f30"
    ),
}

CASE_POSITION = 435
PROFILE_POSITION = 369
PROFILE_ID = "505dac244288e6fb666919c99567f883c28ed573a898ce2a5dd680744dd57540"
PLAN_ID = "9f8cd8303e3a9360986f0294210dda931e827af6eed4ec76b0c084e54f722c4a"
PROGRAM_ID = "0e4a94fb5b99c464e7db1ef0fc0525b9408683a004a5ea034fcfbf5c427eb4e8"
DEPENDENCY_MANIFEST_ID = (
    "d80797d6d34486ed15f73d19a201c7b5ff0ac19593e25302bcba081c2e7b5c3c"
)
MEASURED_SEQUENCE_ORDINAL = 64
FIELD_COUNT = 185
SAFE_INTEGER_MAXIMUM = 9_007_199_254_740_991
OBSERVATION_CODEC_LIMIT = 262_144
FIELD_CODEC_LIMIT = 4_096
CONTEXT_CODEC_LIMIT = 2_048
SOURCE_ERROR_PREIMAGE_LIMIT = 2_048
SOURCE_ERROR_DOMAIN = "RiskYieldMMA2MSourceErrorDetailV4_9F_RawV8"

CERTIFICATE_VERSION = (
    "riskyieldmm.raw_v8_step2.maximum_protocol_v2.case435_upper_certificate.v1"
)
CERTIFICATE_DOMAIN = (
    "RiskYieldMMStep2MaximumProtocolV2Case435UpperCertificateV1V4_9F_RawV8"
)
REDUCTION_VERSION = (
    "riskyieldmm.raw_v8_step2.maximum_protocol_v2.finite_canonical_length_quotient.v1"
)

PLACEHOLDER_FIELD_REASON = {
    "ARTIFACT_BOUND_EXCEEDED": ("CHECKPOINT_PLACEHOLDER_ARTIFACT_BOUND_EXCEEDED"),
    "OBSERVER_INTERNAL_ERROR": ("CHECKPOINT_PLACEHOLDER_OBSERVER_INTERNAL_ERROR"),
    "SOURCE_CLOCK_UNAVAILABLE": ("CHECKPOINT_PLACEHOLDER_SOURCE_CLOCK_UNAVAILABLE"),
    "TARGET_BOUNDARY_NOT_REACHED": (
        "CHECKPOINT_PLACEHOLDER_TARGET_BOUNDARY_NOT_REACHED"
    ),
}
PLACEHOLDER_ORDER = tuple(PLACEHOLDER_FIELD_REASON)
A1_FIELDS = (
    "a1.waiting_count",
    "a1.waiting_kinds",
    "a1.waiting_sequences",
)


class UpperBoundError(RuntimeError):
    """Raised when authority closure or an exact derivation fails closed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise UpperBoundError(message)


def _reject_number(value: str) -> Any:
    raise UpperBoundError(f"non-integer JSON number is forbidden: {value}")


def _duplicate_guard(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _strict_load(raw: bytes, label: str) -> dict[str, Any]:
    value = json.loads(
        raw,
        object_pairs_hook=_duplicate_guard,
        parse_float=_reject_number,
        parse_constant=_reject_number,
    )
    _require(type(value) is dict, f"{label} root is not an object")
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


def _semantic_id(
    canonicalization_version: str,
    schema_version: str,
    domain: str,
    payload: Any,
) -> str:
    return _sha256(
        _canonical_bytes(
            {
                "canonicalization_version": canonicalization_version,
                "domain": domain,
                "payload": payload,
                "schema_version": schema_version,
            }
        )
    )


def _certificate_id(payload: dict[str, Any]) -> str:
    return _sha256(_canonical_bytes({"domain": CERTIFICATE_DOMAIN, "payload": payload}))


def _index(rows: Any, member: str, expected: int, label: str) -> dict[str, Any]:
    _require(type(rows) is list and len(rows) == expected, f"{label} count differs")
    result: dict[str, Any] = {}
    for row in rows:
        _require(type(row) is dict, f"{label} row is not an object")
        key = row.get(member)
        _require(type(key) is str and key not in result, f"{label} key differs")
        result[key] = row
    return result


def _record_identity(
    record: dict[str, Any],
    descriptor: dict[str, Any],
    canonicalization_version: str,
    schema_version: str,
) -> str:
    member = descriptor["identity_field"]
    payload = {
        name: record[name] for name in descriptor["identity_payload_member_order"]
    }
    identity = _semantic_id(
        canonicalization_version,
        schema_version,
        descriptor["described_record_domain"],
        payload,
    )
    record[member] = identity
    return identity


def _load_authorities(root: pathlib.Path) -> tuple[dict[str, Any], ...]:
    loaded: dict[str, dict[str, Any]] = {}
    for relative_path, expected in PINNED_SHA256.items():
        raw = (root / relative_path).read_bytes()
        _require(_sha256(raw) == expected, f"authority hash differs: {relative_path}")
        if relative_path.endswith(".json"):
            loaded[relative_path] = _strict_load(raw, relative_path)
    return (
        loaded[SEED_PATH],
        loaded[INVENTORY_PATH],
        loaded[REGISTRY_PATH],
        loaded[LITERAL_PATH],
        loaded[APPLICATION_LEDGER_PATH],
    )


def _longest_json_value(values: list[Any]) -> Any:
    _require(values, "finite value domain is empty")
    return max(
        values,
        key=lambda value: (len(_canonical_bytes(value)), _canonical_bytes(value)),
    )


def _dfa_accepts(dfa: dict[str, Any], value: str) -> bool:
    try:
        raw = value.encode("ascii")
    except UnicodeEncodeError:
        return False
    if not dfa["minimum_octets"] <= len(raw) <= dfa["maximum_octets"]:
        return False
    state = dfa["start_state"]
    for byte in raw:
        matches = [
            row
            for row in dfa["ordered_transition_rows"]
            if row["source_state"] == state
            and row["inclusive_byte_minimum"] <= byte <= row["inclusive_byte_maximum"]
        ]
        if len(matches) != 1:
            return False
        state = matches[0]["target_state"]
    return state in dfa["ordered_accepting_states"]


def _longest_dfa_value(dfa: dict[str, Any]) -> str:
    transitions = dfa["ordered_transition_rows"]
    for row in transitions:
        low = row["inclusive_byte_minimum"]
        high = row["inclusive_byte_maximum"]
        _require(
            low >= 32 and not low <= ord('"') <= high and not low <= ord("\\") <= high,
            "DFA admits JSON-expanding bytes",
        )
    accepting = set(dfa["ordered_accepting_states"])
    maximum = dfa["maximum_octets"]
    reachable: dict[tuple[Any, int], bool] = {}

    def can_finish(state: Any, remaining: int) -> bool:
        key = (state, remaining)
        if key in reachable:
            return reachable[key]
        if remaining == 0:
            answer = state in accepting
        else:
            answer = any(
                row["source_state"] == state
                and can_finish(row["target_state"], remaining - 1)
                for row in transitions
            )
        reachable[key] = answer
        return answer

    selected_length = next(
        (
            length
            for length in range(maximum, dfa["minimum_octets"] - 1, -1)
            if can_finish(dfa["start_state"], length)
        ),
        None,
    )
    _require(selected_length is not None, "DFA accepted language is empty")
    state = dfa["start_state"]
    result = bytearray()
    for remaining in range(selected_length, 0, -1):
        choices = [
            (row["inclusive_byte_maximum"], row["target_state"])
            for row in transitions
            if row["source_state"] == state
            and can_finish(row["target_state"], remaining - 1)
        ]
        _require(choices, "DFA maximum path is unresolved")
        byte, state = max(choices)
        result.append(byte)
    value = result.decode("ascii")
    _require(_dfa_accepts(dfa, value), "DFA maximum witness is rejected")
    return value


def _maximum_scalar(constraint: dict[str, Any], vocabularies: dict[str, Any]) -> Any:
    profile = constraint["scalar_profile"]
    if profile == "EXACT_BOOL":
        return False
    if profile == "SAFE_IJSON_UINT":
        return constraint["integer_maximum"]
    if profile == "ENUM":
        return _longest_json_value(vocabularies[constraint["vocabulary_id"]]["members"])
    if profile == "SHA256":
        return "f" * 64
    if profile == "UINT128_DECIMAL":
        return constraint["decimal_maximum"]
    if profile == "PLATFORM_ERRNO":
        return "Z" + "Z" * 63
    raise UpperBoundError(f"scalar profile is unresolved: {profile}")


def _scalar_valid(
    value: Any,
    constraint: dict[str, Any],
    vocabularies: dict[str, Any],
) -> bool:
    profile = constraint["scalar_profile"]
    if profile == "EXACT_BOOL":
        return type(value) is bool
    if profile == "SAFE_IJSON_UINT":
        return (
            type(value) is int
            and constraint["integer_minimum"] <= value <= constraint["integer_maximum"]
        )
    if type(value) is not str:
        return False
    raw = value.encode("utf-8")
    if not (
        constraint["text_minimum_utf8_bytes"]
        <= len(raw)
        <= constraint["text_maximum_utf8_bytes"]
    ):
        return False
    if profile == "ENUM":
        return value in vocabularies[constraint["vocabulary_id"]]["members"]
    pattern = constraint["text_ascii_pattern"]
    if type(pattern) is not str or re.fullmatch(pattern, value, flags=re.ASCII) is None:
        return False
    if profile == "UINT128_DECIMAL":
        maximum = constraint["decimal_maximum"]
        return len(value) < len(maximum) or (
            len(value) == len(maximum) and value <= maximum
        )
    return profile in {"SHA256", "PLATFORM_ERRNO"}


def _maximum_target_value(
    descriptor: dict[str, Any],
    constraints: dict[str, Any],
    shapes: dict[str, Any],
    vocabularies: dict[str, Any],
    *,
    censoring: str | None = None,
) -> dict[str, Any]:
    constraint = constraints[descriptor["value_constraint_id"]]
    kind = descriptor["value_kind"]
    if kind == "DURATION_BOUND":
        maximum = constraint["integer_maximum"]
        relation = (
            "EXACT"
            if censoring is None
            else {
                "INTERVAL": "INTERVAL",
                "LEFT": "UPPER_BOUND",
                "RIGHT": "LOWER_BOUND",
            }[censoring]
        )
        return {
            "kind": kind,
            "lower_nanoseconds": (
                maximum if relation in {"EXACT", "LOWER_BOUND", "INTERVAL"} else None
            ),
            "relation": relation,
            "upper_nanoseconds": (
                maximum if relation in {"EXACT", "UPPER_BOUND", "INTERVAL"} else None
            ),
        }
    if kind in {"BOOL", "UINT", "TEXT"}:
        return {"kind": kind, "value": _maximum_scalar(constraint, vocabularies)}
    if kind in {"OPTIONAL_UINT", "OPTIONAL_TEXT"}:
        present = {
            "kind": kind,
            "present": True,
            "value": _maximum_scalar(constraint, vocabularies),
        }
        absent = {"kind": kind, "present": False, "value": None}
        return _longest_json_value([present, absent])
    item_constraint = constraints[constraint["collection_item_constraint_id"]]
    shape = shapes[descriptor["value_shape_id"]]
    if kind in {"UINT_LIST", "TEXT_LIST"}:
        return {
            "kind": kind,
            "values": [_maximum_scalar(item_constraint, vocabularies)]
            * shape["maximum_items"],
        }
    if kind == "FIXED_UINT_MAP":
        item = _maximum_scalar(item_constraint, vocabularies)
        return {
            "kind": kind,
            "ordered": [
                {"key": key, "value": item} for key in descriptor["value_shape_keys"]
            ],
        }
    raise UpperBoundError(f"target value kind is unresolved: {kind}")


def _target_value_valid(
    field: dict[str, Any],
    descriptor: dict[str, Any],
    constraints: dict[str, Any],
    shapes: dict[str, Any],
    vocabularies: dict[str, Any],
) -> bool:
    value = field["value"]
    if value is None:
        return True
    kind = descriptor["value_kind"]
    if type(value) is not dict or value.get("kind") != kind:
        return False
    constraint = constraints[descriptor["value_constraint_id"]]
    if kind == "DURATION_BOUND":
        relation = value.get("relation")
        lower = value.get("lower_nanoseconds")
        upper = value.get("upper_nanoseconds")
        valid = {
            "EXACT": type(lower) is int and type(upper) is int and lower == upper,
            "LOWER_BOUND": type(lower) is int and upper is None,
            "UPPER_BOUND": lower is None and type(upper) is int,
            "INTERVAL": type(lower) is int and type(upper) is int and lower <= upper,
        }.get(relation, False)
        return valid and all(
            endpoint is None
            or constraint["integer_minimum"]
            <= endpoint
            <= constraint["integer_maximum"]
            for endpoint in (lower, upper)
        )
    if kind in {"BOOL", "UINT", "TEXT"}:
        return _scalar_valid(value.get("value"), constraint, vocabularies)
    if kind in {"OPTIONAL_UINT", "OPTIONAL_TEXT"}:
        present = value.get("present")
        scalar = value.get("value")
        return (
            type(present) is bool
            and present == (scalar is not None)
            and (scalar is None or _scalar_valid(scalar, constraint, vocabularies))
        )
    item_constraint = constraints[constraint["collection_item_constraint_id"]]
    shape = shapes[descriptor["value_shape_id"]]
    if kind in {"UINT_LIST", "TEXT_LIST"}:
        values = value.get("values")
        return (
            type(values) is list
            and shape["minimum_items"] <= len(values) <= shape["maximum_items"]
            and all(
                _scalar_valid(item, item_constraint, vocabularies) for item in values
            )
        )
    if kind == "FIXED_UINT_MAP":
        ordered = value.get("ordered")
        return (
            type(ordered) is list
            and shape["minimum_items"] <= len(ordered) <= shape["maximum_items"]
            and [row.get("key") for row in ordered] == descriptor["value_shape_keys"]
            and all(
                _scalar_valid(row.get("value"), item_constraint, vocabularies)
                for row in ordered
            )
        )
    return False


def _source_error_digest(
    field: dict[str, Any], canonicalization: str, schema_version: str
) -> str | None:
    if field["source_error_class"] is None:
        return None
    payload = {
        name: field[name]
        for name in (
            "field_id",
            "observation_method",
            "source_failure_phase",
            "source_errno_number",
            "source_errno_name",
            "source_error_class",
        )
    }
    _require(
        len(_canonical_bytes(payload)) <= SOURCE_ERROR_PREIMAGE_LIMIT,
        "source-error preimage exceeds codec",
    )
    return _semantic_id(canonicalization, schema_version, SOURCE_ERROR_DOMAIN, payload)


def _field_intrinsic_valid(field: dict[str, Any]) -> bool:
    availability = field["availability"]
    value = field["value"]
    method = field["observation_method"]
    attempt = field["observation_attempt"]
    span = field["adapter_span_status"]
    started = field["observation_started_offset_nanoseconds"]
    completed = field["observation_completed_offset_nanoseconds"]
    reason = field["unavailable_reason"]
    censoring = field["censoring"]
    errno_number = field["source_errno_number"]
    errno_name = field["source_errno_name"]
    phase = field["source_failure_phase"]
    error_class = field["source_error_class"]
    error_digest = field["source_error_detail_sha256"]
    span_valid = (
        span == "AVAILABLE"
        and type(started) is int
        and type(completed) is int
        and started <= completed
    ) or (span != "AVAILABLE" and started is None and completed is None)
    if not span_valid or (errno_number is None) != (errno_name is None):
        return False
    if (error_class is None) != (error_digest is None):
        return False
    source_absent = all(
        value is None for value in (errno_number, errno_name, error_class, error_digest)
    )
    if not (
        (attempt == "ATTEMPTED" and method != "NOT_ATTEMPTED")
        or (attempt == "NOT_ATTEMPTED" and method == "NOT_ATTEMPTED")
    ):
        return False
    if availability in {"AVAILABLE", "CENSORED"}:
        if (
            value is None
            or attempt != "ATTEMPTED"
            or span != "AVAILABLE"
            or reason is not None
            or phase != "NONE"
            or not source_absent
        ):
            return False
        if availability == "AVAILABLE":
            return censoring == "NONE" and (
                value.get("kind") != "DURATION_BOUND"
                or value.get("relation") == "EXACT"
            )
        return value.get("kind") == "DURATION_BOUND" and value.get("relation") == {
            "LEFT": "UPPER_BOUND",
            "RIGHT": "LOWER_BOUND",
            "INTERVAL": "INTERVAL",
        }.get(censoring)
    if availability == "NOT_APPLICABLE":
        return (
            value is None
            and reason
            in {"NOT_APPLICABLE_TO_OPERATION", "NOT_APPLICABLE_TO_REACHED_STATE"}
            and method == "NOT_ATTEMPTED"
            and attempt == "NOT_ATTEMPTED"
            and span == "NOT_APPLICABLE"
            and censoring == "NONE"
            and phase == "NONE"
            and source_absent
        )
    if availability == "UNAVAILABLE":
        return value is None and reason is not None and censoring == "NONE"
    return False


def _descriptor_policy_valid(
    field: dict[str, Any], descriptor: dict[str, Any], reason_rules: dict[str, Any]
) -> bool:
    reason = field["unavailable_reason"]
    if reason is None:
        return not (
            field["availability"] == "CENSORED"
            and descriptor["censoring_allowed"] is not True
        )
    if reason not in descriptor["allowed_status_reasons"]:
        return False
    rule = reason_rules.get(reason)
    if rule is None or rule["required_availability"] != field["availability"]:
        return False
    rows = [
        row
        for row in rule["attempt_state_error_forms"]
        if row["attempt_state"] == field["observation_attempt"]
    ]
    if len(rows) != 1:
        return False
    row = rows[0]
    expected_span = {
        "AVAILABLE_ONLY": "AVAILABLE",
        "NOT_APPLICABLE_ONLY": "NOT_APPLICABLE",
        "UNAVAILABLE_ONLY": "UNAVAILABLE",
    }[row["adapter_span_policy"]]
    if (
        field["adapter_span_status"] != expected_span
        or field["source_failure_phase"] not in row["permitted_failure_phases"]
    ):
        return False
    if field["source_errno_number"] is not None:
        effective = "OS"
    elif field["source_error_class"] is not None:
        effective = "NON_OS"
    elif "STATUS_ONLY" in row["permitted_error_forms"]:
        effective = "STATUS_ONLY"
    else:
        effective = "NONE"
    return effective in row["permitted_error_forms"]


def _field_context_valid(
    field: dict[str, Any],
    descriptor: dict[str, Any],
    context: dict[str, Any],
    ordinal: int,
    registry_id: str,
) -> bool:
    if (
        field["field_id"] != descriptor["field_id"]
        or field["target_field_registry_id"] != registry_id
        or field["observation_context_id"] != context["observation_context_id"]
        or ordinal < 0
        or ordinal >= FIELD_COUNT
    ):
        return False
    binding_reason = context["checkpoint_binding_unavailable_reason"]
    placeholder = PLACEHOLDER_FIELD_REASON.get(binding_reason)
    if placeholder is not None:
        return (
            field["availability"] == "UNAVAILABLE"
            and field["value"] is None
            and field["unavailable_reason"] == placeholder
            and field["observation_method"] == "NOT_ATTEMPTED"
            and field["observation_attempt"] == "NOT_ATTEMPTED"
            and field["adapter_span_status"] == "NOT_APPLICABLE"
            and field["observation_started_offset_nanoseconds"] is None
            and field["observation_completed_offset_nanoseconds"] is None
            and field["censoring"] == "NONE"
            and field["source_failure_phase"] == "NONE"
            and field["source_errno_number"] is None
            and field["source_errno_name"] is None
            and field["source_error_class"] is None
            and field["source_error_detail_sha256"] is None
        )
    if field["unavailable_reason"] in set(PLACEHOLDER_FIELD_REASON.values()):
        return False
    operation_applies = (
        context["operation_kind"] in descriptor["applicable_operation_kinds"]
    )
    if not operation_applies:
        return (
            field["availability"] == "NOT_APPLICABLE"
            and field["unavailable_reason"] == "NOT_APPLICABLE_TO_OPERATION"
        )
    if field["unavailable_reason"] == "NOT_APPLICABLE_TO_OPERATION":
        return False
    if (
        context["instrumentation_mode"] == "ON"
        and field["unavailable_reason"] == "INSTRUMENTATION_DISABLED"
    ):
        return False
    if field["observation_attempt"] == "ATTEMPTED":
        rows = [
            row
            for row in descriptor["observation_method_role_pairs"]
            if row["observation_method"] == field["observation_method"]
        ]
        if (
            len(rows) != 1
            or context["observation_role"] not in rows[0]["allowed_roles"]
        ):
            return False
        if (
            context["observation_role"] == "STABLE_CHECKPOINT"
            and context["checkpoint_marker_kind"]
            not in descriptor["allowed_checkpoint_marker_kinds"]
        ):
            return False
    if field["adapter_span_status"] == "AVAILABLE":
        span = context["observer_clock_span"]
        values = (
            span["started_offset_nanoseconds"],
            field["observation_started_offset_nanoseconds"],
            field["observation_completed_offset_nanoseconds"],
            span["completed_offset_nanoseconds"],
        )
        return (
            span["span_status"] == "AVAILABLE"
            and all(type(value) is int for value in values)
            and values[0] <= values[1] <= values[2] <= values[3]
        )
    return True


def _a1_valid(fields: tuple[dict[str, Any], ...]) -> bool:
    if any(field["availability"] != "AVAILABLE" for field in fields):
        return True
    by_id = {field["field_id"]: field for field in fields}
    count = by_id[A1_FIELDS[0]]["value"]["value"]
    kinds = by_id[A1_FIELDS[1]]["value"]["values"]
    sequences = by_id[A1_FIELDS[2]]["value"]["values"]
    return (
        type(count) is int
        and type(kinds) is list
        and type(sequences) is list
        and count == len(kinds) == len(sequences)
        and len(sequences) <= 4
        and all(left < right for left, right in zip(sequences, sequences[1:]))
    )


def _build_context(
    fixture: dict[str, Any],
    root: dict[str, Any],
    selector: dict[str, Any],
    entry: dict[str, Any],
    types: dict[str, Any],
    canonicalization: str,
    schema_version: str,
    registry_id: str,
    *,
    reason: str | None,
) -> dict[str, Any]:
    context = json.loads(json.dumps(fixture))
    exact = reason is None
    context.update(
        {
            "attempt_id": root["attempt_id"],
            "candidate_id": root["candidate_id"],
            "checkpoint_binding_status": (
                "EXACT_MARKER"
                if exact
                else "UNAVAILABLE_TARGET_BOUNDARY_NOT_REACHED"
                if reason == "TARGET_BOUNDARY_NOT_REACHED"
                else "UNAVAILABLE_MARKER_OBSERVER_FAILURE"
            ),
            "checkpoint_binding_unavailable_reason": reason,
            "checkpoint_marker_kind": entry["checkpoint_marker_kind"]
            if exact
            else None,
            "checkpoint_selector_entry_id": entry["checkpoint_selector_entry_id"],
            "checkpoint_selector_position": entry["selector_position"],
            "expected_checkpoint_marker_kind": entry["checkpoint_marker_kind"],
            "expected_occurrence_index_within_kind": entry[
                "occurrence_index_within_kind"
            ],
            "full_checkpoint_selector_id": selector["checkpoint_selector_id"],
            "instrumentation_mode": "ON",
            "marker_ordinal": SAFE_INTEGER_MAXIMUM if exact else None,
            "observation_role": "STABLE_CHECKPOINT",
            "operation_kind": "INGRESS",
            "target_field_registry_id": registry_id,
        }
    )
    for member, domain in (
        ("observer_clock_span", "OBSERVER_MONOTONIC"),
        ("boottime_clock_span", "BOOTTIME"),
        ("loop_clock_span", "EVENT_LOOP"),
    ):
        context[member] = {
            "clock_domain": domain,
            "completed_offset_nanoseconds": SAFE_INTEGER_MAXIMUM if exact else None,
            "span_status": "AVAILABLE" if exact else "UNAVAILABLE",
            "started_offset_nanoseconds": SAFE_INTEGER_MAXIMUM if exact else None,
            "unavailable_reason": reason,
        }
    _record_identity(
        context,
        types["TargetObservationContextV2"],
        canonicalization,
        schema_version,
    )
    _require(
        len(_canonical_bytes(context)) <= CONTEXT_CODEC_LIMIT, "context codec exceeded"
    )
    return context


def _base_field(
    frozen: dict[str, Any], context_id: str, registry_id: str
) -> dict[str, Any]:
    field = dict(frozen)
    field["observation_context_id"] = context_id
    field["target_field_registry_id"] = registry_id
    return field


def _attempted_methods(
    descriptor: dict[str, Any], context: dict[str, Any]
) -> list[str]:
    if context["operation_kind"] not in descriptor["applicable_operation_kinds"]:
        return []
    if (
        context["checkpoint_marker_kind"]
        not in descriptor["allowed_checkpoint_marker_kinds"]
    ):
        return []
    return [
        row["observation_method"]
        for row in descriptor["observation_method_role_pairs"]
        if context["observation_role"] in row["allowed_roles"]
    ]


def _available_candidate(
    frozen: dict[str, Any],
    descriptor: dict[str, Any],
    context: dict[str, Any],
    registry_id: str,
    method: str,
    constraints: dict[str, Any],
    shapes: dict[str, Any],
    vocabularies: dict[str, Any],
    field_type: dict[str, Any],
    canonicalization: str,
    schema_version: str,
    *,
    censoring: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    field = _base_field(frozen, context["observation_context_id"], registry_id)
    field.update(
        {
            "adapter_span_status": "AVAILABLE",
            "availability": "AVAILABLE" if censoring is None else "CENSORED",
            "censoring": "NONE" if censoring is None else censoring,
            "observation_attempt": "ATTEMPTED",
            "observation_completed_offset_nanoseconds": SAFE_INTEGER_MAXIMUM,
            "observation_method": method,
            "observation_started_offset_nanoseconds": SAFE_INTEGER_MAXIMUM,
            "source_errno_name": None,
            "source_errno_number": None,
            "source_error_class": None,
            "source_error_detail_sha256": None,
            "source_failure_phase": "NONE",
            "unavailable_reason": None,
            "value": _maximum_target_value(
                descriptor,
                constraints,
                shapes,
                vocabularies,
                censoring=censoring,
            ),
        }
    )
    _record_identity(field, field_type, canonicalization, schema_version)
    return (
        {
            "branch_kind": "CENSORED_VALUE" if censoring else "AVAILABLE_VALUE",
            "censoring": censoring,
            "error_form": "NONE",
            "method": method,
            "phase": "NONE",
            "reason": None,
        },
        field,
    )


def _reason_candidate(
    frozen: dict[str, Any],
    context: dict[str, Any],
    registry_id: str,
    method: str,
    reason: str,
    reason_rule: dict[str, Any],
    attempt_row: dict[str, Any],
    error_form: str,
    field_type: dict[str, Any],
    canonicalization: str,
    schema_version: str,
    errno_name: str,
    error_class: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    field = _base_field(frozen, context["observation_context_id"], registry_id)
    span = {
        "AVAILABLE_ONLY": "AVAILABLE",
        "NOT_APPLICABLE_ONLY": "NOT_APPLICABLE",
        "UNAVAILABLE_ONLY": "UNAVAILABLE",
    }[attempt_row["adapter_span_policy"]]
    attempted = attempt_row["attempt_state"] == "ATTEMPTED"
    phase = _longest_json_value(attempt_row["permitted_failure_phases"])
    field.update(
        {
            "adapter_span_status": span,
            "availability": reason_rule["required_availability"],
            "censoring": "NONE",
            "observation_attempt": attempt_row["attempt_state"],
            "observation_completed_offset_nanoseconds": (
                SAFE_INTEGER_MAXIMUM if span == "AVAILABLE" else None
            ),
            "observation_method": method if attempted else "NOT_ATTEMPTED",
            "observation_started_offset_nanoseconds": (
                SAFE_INTEGER_MAXIMUM if span == "AVAILABLE" else None
            ),
            "source_failure_phase": phase,
            "unavailable_reason": reason,
            "value": None,
        }
    )
    if error_form == "OS_PLUS_NON_OS_DETAIL":
        field["source_errno_number"] = SAFE_INTEGER_MAXIMUM
        field["source_errno_name"] = errno_name
        field["source_error_class"] = error_class
    elif error_form == "OS_ONLY":
        field["source_errno_number"] = SAFE_INTEGER_MAXIMUM
        field["source_errno_name"] = errno_name
        field["source_error_class"] = None
    elif error_form == "NON_OS":
        field["source_errno_number"] = None
        field["source_errno_name"] = None
        field["source_error_class"] = error_class
    else:
        field["source_errno_number"] = None
        field["source_errno_name"] = None
        field["source_error_class"] = None
    field["source_error_detail_sha256"] = _source_error_digest(
        field, canonicalization, schema_version
    )
    _record_identity(field, field_type, canonicalization, schema_version)
    return (
        {
            "branch_kind": "STATUS_REASON",
            "censoring": None,
            "error_form": error_form,
            "method": field["observation_method"],
            "phase": phase,
            "reason": reason,
        },
        field,
    )


def _candidate_valid(
    field: dict[str, Any],
    descriptor: dict[str, Any],
    context: dict[str, Any],
    ordinal: int,
    registry_id: str,
    reason_rules: dict[str, Any],
    constraints: dict[str, Any],
    shapes: dict[str, Any],
    vocabularies: dict[str, Any],
    field_type: dict[str, Any],
    canonicalization: str,
    schema_version: str,
) -> bool:
    identity = field[field_type["identity_field"]]
    probe = dict(field)
    if (
        _record_identity(probe, field_type, canonicalization, schema_version)
        != identity
    ):
        return False
    return (
        len(_canonical_bytes(field)) <= FIELD_CODEC_LIMIT
        and _field_intrinsic_valid(field)
        and field["source_error_detail_sha256"]
        == _source_error_digest(field, canonicalization, schema_version)
        and _descriptor_policy_valid(field, descriptor, reason_rules)
        and _target_value_valid(field, descriptor, constraints, shapes, vocabularies)
        and _field_context_valid(field, descriptor, context, ordinal, registry_id)
    )


def _field_candidates(
    frozen: dict[str, Any],
    descriptor: dict[str, Any],
    context: dict[str, Any],
    registry_id: str,
    reason_rules: dict[str, Any],
    constraints: dict[str, Any],
    shapes: dict[str, Any],
    vocabularies: dict[str, Any],
    field_type: dict[str, Any],
    canonicalization: str,
    schema_version: str,
    errno_name: str,
    error_class: str,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    candidates: list[tuple[dict[str, Any], dict[str, Any]]] = []
    methods = _attempted_methods(descriptor, context)
    for method in methods:
        candidates.append(
            _available_candidate(
                frozen,
                descriptor,
                context,
                registry_id,
                method,
                constraints,
                shapes,
                vocabularies,
                field_type,
                canonicalization,
                schema_version,
            )
        )
        if (
            descriptor["censoring_allowed"]
            and descriptor["value_kind"] == "DURATION_BOUND"
        ):
            for censoring in ("INTERVAL", "LEFT", "RIGHT"):
                candidates.append(
                    _available_candidate(
                        frozen,
                        descriptor,
                        context,
                        registry_id,
                        method,
                        constraints,
                        shapes,
                        vocabularies,
                        field_type,
                        canonicalization,
                        schema_version,
                        censoring=censoring,
                    )
                )
    for reason in descriptor["allowed_status_reasons"]:
        reason_rule = reason_rules.get(reason)
        if reason_rule is None:
            continue
        for attempt_row in reason_rule["attempt_state_error_forms"]:
            selected_methods = (
                methods
                if attempt_row["attempt_state"] == "ATTEMPTED"
                else ["NOT_ATTEMPTED"]
            )
            forms = attempt_row["permitted_error_forms"]
            error_forms: list[str] = []
            if "OS" in forms:
                error_forms.extend(("OS_PLUS_NON_OS_DETAIL", "OS_ONLY"))
            if "NON_OS" in forms:
                error_forms.append("NON_OS")
            if "STATUS_ONLY" in forms:
                error_forms.append("STATUS_ONLY")
            elif "NONE" in forms:
                error_forms.append("NONE")
            for method, error_form in product(selected_methods, error_forms):
                candidates.append(
                    _reason_candidate(
                        frozen,
                        context,
                        registry_id,
                        method,
                        reason,
                        reason_rule,
                        attempt_row,
                        error_form,
                        field_type,
                        canonicalization,
                        schema_version,
                        errno_name,
                        error_class,
                    )
                )
    return candidates


def _a1_variants(
    candidates: list[tuple[dict[str, Any], dict[str, Any]]],
    field_id: str,
    field_type: dict[str, Any],
    canonicalization: str,
    schema_version: str,
    vocabularies: dict[str, Any],
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    available = [item for item in candidates if item[1]["availability"] == "AVAILABLE"]
    _require(available, f"A1 available branch is absent: {field_id}")
    base_branch, base = max(
        available,
        key=lambda item: (len(_canonical_bytes(item[1])), _canonical_bytes(item[1])),
    )
    result = list(candidates)
    kind_maximum = _longest_json_value(
        vocabularies["RAW_V8_A1_COMMAND_KIND"]["members"]
    )
    for cardinality in range(5):
        field = json.loads(json.dumps(base))
        if field_id == A1_FIELDS[0]:
            field["value"] = {"kind": "UINT", "value": cardinality}
        elif field_id == A1_FIELDS[1]:
            field["value"] = {
                "kind": "TEXT_LIST",
                "values": [kind_maximum] * cardinality,
            }
        else:
            field["value"] = {
                "kind": "UINT_LIST",
                "values": list(
                    range(
                        SAFE_INTEGER_MAXIMUM - cardinality + 1,
                        SAFE_INTEGER_MAXIMUM + 1,
                    )
                ),
            }
        _record_identity(field, field_type, canonicalization, schema_version)
        branch = dict(base_branch)
        branch["branch_kind"] = "A1_COMPATIBLE_AVAILABLE_VALUE"
        branch["a1_cardinality"] = cardinality
        result.append((branch, field))
    return result


def _winner_key(item: tuple[dict[str, Any], dict[str, Any]]) -> tuple[Any, ...]:
    branch, field = item
    raw = _canonical_bytes(field)
    return len(raw), raw, _canonical_bytes(branch)


def _rebind_observation(
    source: dict[str, Any],
    root: dict[str, Any],
    types: dict[str, Any],
    canonicalization: str,
    schema_version: str,
    registry_id: str,
) -> dict[str, Any]:
    observation = json.loads(json.dumps(source))
    context = observation["observation_context"]
    for member in (
        "candidate_id",
        "attempt_id",
        "operation_kind",
        "instrumentation_mode",
    ):
        context[member] = root[member]
    context["target_field_registry_id"] = registry_id
    _record_identity(
        context,
        types["TargetObservationContextV2"],
        canonicalization,
        schema_version,
    )
    observation["observation_context_id"] = context["observation_context_id"]
    for field in observation["field_observations"]:
        field["target_field_registry_id"] = registry_id
        field["observation_context_id"] = context["observation_context_id"]
        _record_identity(
            field,
            types["TargetFieldObservationV1"],
            canonicalization,
            schema_version,
        )
    _record_identity(
        observation,
        types["TargetObservationV2"],
        canonicalization,
        schema_version,
    )
    return observation


def _placeholder_observation(
    template: dict[str, Any],
    root: dict[str, Any],
    selector: dict[str, Any],
    entry: dict[str, Any],
    types: dict[str, Any],
    canonicalization: str,
    schema_version: str,
    registry_id: str,
) -> dict[str, Any]:
    observation = json.loads(json.dumps(template))
    context = observation["observation_context"]
    context.update(
        {
            "attempt_id": root["attempt_id"],
            "candidate_id": root["candidate_id"],
            "checkpoint_selector_entry_id": entry["checkpoint_selector_entry_id"],
            "checkpoint_selector_position": entry["selector_position"],
            "expected_checkpoint_marker_kind": entry["checkpoint_marker_kind"],
            "expected_occurrence_index_within_kind": entry[
                "occurrence_index_within_kind"
            ],
            "full_checkpoint_selector_id": selector["checkpoint_selector_id"],
            "instrumentation_mode": root["instrumentation_mode"],
            "operation_kind": root["operation_kind"],
            "target_field_registry_id": registry_id,
        }
    )
    return _rebind_observation(
        observation,
        root,
        types,
        canonicalization,
        schema_version,
        registry_id,
    )


def _lifecycle_valid(
    root: dict[str, Any], observations: list[dict[str, Any]], selector: dict[str, Any]
) -> bool:
    if (
        root["observation_count"] != len(observations)
        or not 1 <= len(observations) <= 67
    ):
        return False
    ids = [row["observation_id"] for row in observations]
    if root["ordered_observation_ids"] != ids:
        return False
    contexts = [row["observation_context"] for row in observations]
    if any(
        any(
            context[member] != root[member]
            for member in (
                "candidate_id",
                "attempt_id",
                "operation_kind",
                "instrumentation_mode",
                "target_field_registry_id",
            )
        )
        for context in contexts
    ):
        return False
    roles = [row["observation_role"] for row in contexts]
    if not (
        roles[0] == "BEFORE_OPERATION"
        and roles[-2:] == ["AFTER_OPERATION", "OPERATION_AGGREGATE"]
        and all(role == "STABLE_CHECKPOINT" for role in roles[1:-2])
    ):
        return False
    entries = selector["ordered_entries"]
    if (
        selector["operation_kind"] != root["operation_kind"]
        or selector["checkpoint_selector_id"] != root["full_checkpoint_selector_id"]
        or len(contexts) != selector["selector_length"] + 3
    ):
        return False
    exact_ordinals: list[int] = []
    for context, entry in zip(contexts[1:-2], entries, strict=True):
        if (
            context["full_checkpoint_selector_id"] != selector["checkpoint_selector_id"]
            or context["checkpoint_selector_position"] != entry["selector_position"]
            or context["checkpoint_selector_entry_id"]
            != entry["checkpoint_selector_entry_id"]
            or context["expected_checkpoint_marker_kind"]
            != entry["checkpoint_marker_kind"]
            or context["expected_occurrence_index_within_kind"]
            != entry["occurrence_index_within_kind"]
        ):
            return False
        if context["checkpoint_binding_status"] == "EXACT_MARKER":
            exact_ordinals.append(context["marker_ordinal"])
    return all(left < right for left, right in zip(exact_ordinals, exact_ordinals[1:]))


def solve(repository_root: pathlib.Path | str) -> dict[str, Any]:
    root_path = pathlib.Path(repository_root)
    seed, inventory, registry, literal, ledger = _load_authorities(root_path)
    _require(
        inventory["external_schema_registry_v2"] == registry, "registry join differs"
    )
    _require(
        literal["target_field_registry"] == inventory["target_field_registry"],
        "literal target registry differs",
    )
    canonicalization = seed["canonicalization_version"]
    schema_version = seed["measurement_schema_version"]
    recipe = seed["logical_plan_recipe_catalog"]
    plan = recipe["ordered_logical_count_plan_records"][CASE_POSITION - 1]
    _require(
        plan["case_position"] == CASE_POSITION
        and plan["logical_count_plan_id"] == PLAN_ID
        and plan["profile_conditioning_program_id"] == PROGRAM_ID,
        "case binding differs",
    )
    program = next(
        row
        for row in recipe["ordered_profile_conditioning_program_records"]
        if row["profile_conditioning_program_id"] == PROGRAM_ID
    )
    _require(
        program["profile_position"] == PROFILE_POSITION
        and program["maximum_constraint_scope_profile_id"] == PROFILE_ID
        and program["scope_root_operation"]["ordered_scope_case_records"]
        == [
            {
                "measured_sequence_ordinal": MEASURED_SEQUENCE_ORDINAL,
                "mode_attempt_pair_position": 1,
                "observation_role_position": 1,
                "root_family_position": 1,
                "scope_case_position": 1,
            }
        ],
        "profile scope differs",
    )
    types = _index(
        registry["ordered_external_type_descriptors"], "type_name", 52, "type"
    )
    schemas = _index(registry["value_schema_catalog"], "value_schema_id", 236, "schema")
    languages = _index(
        registry["text_language_catalog"], "text_language_id", 103, "language"
    )
    dfas = _index(registry["ascii_dfa_catalog"], "ascii_dfa_id", 9, "DFA")
    rules = _index(
        registry["ordered_cross_field_rule_descriptors"], "rule_id", 42, "rule"
    )
    ledger_rules = _index(
        ledger["ordered_rule_descriptors"], "rule_id", 42, "ledger rule"
    )
    for rule_id in (
        "RULE/INTRINSIC/TargetObservationContextV2/V1",
        "RULE/INTRINSIC/TargetFieldObservationV1/V1",
        "RULE/CROSS/V2_OBSERVATION_FIELD_REGISTRY_V1",
        "RULE/CROSS/V2_OBSERVATION_AGGREGATE_REGISTRY_V1",
        "RULE/CROSS/V2_ROOT_SELECTOR_LIFECYCLE_V1",
    ):
        _require(
            rules[rule_id] == ledger_rules[rule_id], f"rule ledger differs: {rule_id}"
        )
    target_registry = inventory["target_field_registry"]
    descriptors = target_registry["descriptors"]
    _require(len(descriptors) == FIELD_COUNT, "field count differs")
    constraints = _index(
        target_registry["ordered_value_constraint_definitions"],
        "value_constraint_id",
        17,
        "constraint",
    )
    shapes = _index(
        target_registry["ordered_value_shape_definitions"],
        "value_shape_id",
        6,
        "shape",
    )
    vocabularies = _index(
        target_registry["ordered_vocabulary_definitions"],
        "vocabulary_id",
        25,
        "vocabulary",
    )
    reason_rules = _index(
        target_registry["status_reason_policy_definition"]["reason_rules"],
        "reason",
        26,
        "reason",
    )
    registry_id = target_registry["target_field_registry_id"]
    field_type = types["TargetFieldObservationV1"]
    field_members = {
        row["member_name"]: schemas[row["value_schema_id"]]
        for row in field_type["record_member_descriptors"]
    }
    error_language = languages[field_members["source_error_class"]["text_language_id"]]
    errno_language = languages[field_members["source_errno_name"]["text_language_id"]]
    _require(
        error_language["language_kind"] == "ASCII_DFA"
        and errno_language["language_kind"] == "ASCII_DFA",
        "source error languages differ",
    )
    error_class = _longest_dfa_value(dfas[error_language["ascii_dfa_id"]])
    errno_name = _longest_dfa_value(dfas[errno_language["ascii_dfa_id"]])
    _require(len(error_class) == 256 and len(errno_name) == 64, "DFA maxima differ")

    fixtures = inventory["fixture_records"]["target_observation_v2_fixtures"]
    maximum_root = fixtures["maximum_selector_target_observation_root"]
    selector = next(
        row["selector"]
        for row in inventory["checkpoint_selector_catalog"]
        if row["selector"]["checkpoint_selector_id"]
        == maximum_root["full_checkpoint_selector_id"]
    )
    _require(selector["selector_length"] == 64, "selector length differs")
    entry = selector["ordered_entries"][MEASURED_SEQUENCE_ORDINAL - 1]
    _require(
        entry["selector_position"] == MEASURED_SEQUENCE_ORDINAL
        and entry["checkpoint_marker_kind"] == "PARSER_UNIT_CONVERGED",
        "measured selector entry differs",
    )
    exact_context = _build_context(
        fixtures["checkpoint_exact_marker_observation"]["observation_context"],
        maximum_root,
        selector,
        entry,
        types,
        canonicalization,
        schema_version,
        registry_id,
        reason=None,
    )
    frozen_fields = fixtures["checkpoint_exact_marker_observation"][
        "field_observations"
    ]
    field_candidate_sets: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    legal_sets: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    for ordinal, (frozen, descriptor) in enumerate(
        zip(frozen_fields, descriptors, strict=True)
    ):
        _require(frozen["field_id"] == descriptor["field_id"], "field order differs")
        candidates = _field_candidates(
            frozen,
            descriptor,
            exact_context,
            registry_id,
            reason_rules,
            constraints,
            shapes,
            vocabularies,
            field_type,
            canonicalization,
            schema_version,
            errno_name,
            error_class,
        )
        if descriptor["field_id"] in A1_FIELDS:
            candidates = _a1_variants(
                candidates,
                descriptor["field_id"],
                field_type,
                canonicalization,
                schema_version,
                vocabularies,
            )
        legal = [
            item
            for item in candidates
            if _candidate_valid(
                item[1],
                descriptor,
                exact_context,
                ordinal,
                registry_id,
                reason_rules,
                constraints,
                shapes,
                vocabularies,
                field_type,
                canonicalization,
                schema_version,
            )
        ]
        _require(legal, f"field legal quotient is empty: {descriptor['field_id']}")
        field_candidate_sets[descriptor["field_id"]] = candidates
        legal_sets[descriptor["field_id"]] = legal

    a1_legal_tuples = [
        rows
        for rows in product(*(legal_sets[field_id] for field_id in A1_FIELDS))
        if _a1_valid(tuple(item[1] for item in rows))
    ]
    _require(a1_legal_tuples, "A1 quotient has no legal tuple")
    a1_winner = max(
        a1_legal_tuples,
        key=lambda rows: (
            sum(len(_canonical_bytes(item[1])) for item in rows),
            _canonical_bytes([item[1] for item in rows]),
        ),
    )
    selected_by_id = dict(zip(A1_FIELDS, a1_winner, strict=True))
    for descriptor in descriptors:
        field_id = descriptor["field_id"]
        if field_id not in selected_by_id:
            selected_by_id[field_id] = max(legal_sets[field_id], key=_winner_key)

    ordered_fields = [selected_by_id[row["field_id"]][1] for row in descriptors]
    field_rows = []
    for position, descriptor in enumerate(descriptors, 1):
        field_id = descriptor["field_id"]
        branch, winner = selected_by_id[field_id]
        raw = _canonical_bytes(winner)
        field_rows.append(
            {
                "field_position": position,
                "field_id": field_id,
                "descriptor_canonical_sha256": _sha256(_canonical_bytes(descriptor)),
                "component_kind": (
                    "A1_FIFO_COUPLED" if field_id in A1_FIELDS else "ORDINARY_SINGLETON"
                ),
                "reduced_candidate_count": len(field_candidate_sets[field_id]),
                "legal_reduced_candidate_count": len(legal_sets[field_id]),
                "maximum_canonical_octets": len(raw),
                "winner_canonical_sha256": _sha256(raw),
                "winner_field_observation_id": winner["field_observation_id"],
                "winner_branch": branch,
            }
        )

    exact_observation = json.loads(
        json.dumps(fixtures["checkpoint_exact_marker_observation"])
    )
    exact_observation["observation_context"] = exact_context
    exact_observation["observation_context_id"] = exact_context[
        "observation_context_id"
    ]
    exact_observation["field_observations"] = ordered_fields
    _record_identity(
        exact_observation,
        types["TargetObservationV2"],
        canonicalization,
        schema_version,
    )
    exact_raw = _canonical_bytes(exact_observation)
    _require(
        len(exact_raw) < OBSERVATION_CODEC_LIMIT, "exact observation codec exceeded"
    )

    branch_rows = [
        {
            "branch_position": 1,
            "binding_branch": "EXACT_MARKER",
            "binding_reason": None,
            "context_canonical_octets": len(_canonical_bytes(exact_context)),
            "field_maximum_sum_octets": sum(
                row["maximum_canonical_octets"] for row in field_rows
            ),
            "observation_canonical_octets": len(exact_raw),
            "observation_canonical_sha256": _sha256(exact_raw),
        }
    ]
    placeholder_templates = fixtures["checkpoint_placeholder_observations"]
    for position, reason in enumerate(PLACEHOLDER_ORDER, 2):
        observation = _placeholder_observation(
            placeholder_templates[reason],
            maximum_root,
            selector,
            entry,
            types,
            canonicalization,
            schema_version,
            registry_id,
        )
        context = observation["observation_context"]
        expected_reason = PLACEHOLDER_FIELD_REASON[reason]
        _require(
            all(
                field["unavailable_reason"] == expected_reason
                and _field_context_valid(
                    field, descriptor, context, ordinal, registry_id
                )
                for ordinal, (field, descriptor) in enumerate(
                    zip(observation["field_observations"], descriptors, strict=True)
                )
            ),
            f"placeholder field branch differs: {reason}",
        )
        raw = _canonical_bytes(observation)
        branch_rows.append(
            {
                "branch_position": position,
                "binding_branch": context["checkpoint_binding_status"],
                "binding_reason": reason,
                "context_canonical_octets": len(_canonical_bytes(context)),
                "field_maximum_sum_octets": sum(
                    len(_canonical_bytes(field))
                    for field in observation["field_observations"]
                ),
                "observation_canonical_octets": len(raw),
                "observation_canonical_sha256": _sha256(raw),
            }
        )
    selected_branch = max(
        branch_rows,
        key=lambda row: (row["observation_canonical_octets"], -row["branch_position"]),
    )
    _require(
        selected_branch["binding_branch"] == "EXACT_MARKER", "separator winner differs"
    )

    preceding = [
        _placeholder_observation(
            placeholder_templates["TARGET_BOUNDARY_NOT_REACHED"],
            maximum_root,
            selector,
            selected_entry,
            types,
            canonicalization,
            schema_version,
            registry_id,
        )
        for selected_entry in selector["ordered_entries"][:63]
    ]
    outer = fixtures["off_target_observations"]
    observations = [
        _rebind_observation(
            outer[0], maximum_root, types, canonicalization, schema_version, registry_id
        ),
        *preceding,
        exact_observation,
        _rebind_observation(
            outer[1], maximum_root, types, canonicalization, schema_version, registry_id
        ),
        _rebind_observation(
            outer[2], maximum_root, types, canonicalization, schema_version, registry_id
        ),
    ]
    _require(len(observations) == 67, "separator sequence length differs")
    full_root = json.loads(json.dumps(maximum_root))
    full_root["ordered_observation_ids"] = [
        row["observation_id"] for row in observations
    ]
    _record_identity(
        full_root,
        types["TargetObservationRootV2"],
        canonicalization,
        schema_version,
    )
    _require(
        _lifecycle_valid(full_root, observations, selector),
        "separator lifecycle is infeasible",
    )

    field_sum = sum(row["maximum_canonical_octets"] for row in field_rows)
    composition_total = 422 + len(_canonical_bytes(exact_context)) + 2 + 184 + field_sum
    _require(
        composition_total == len(exact_raw) == 257_887, "exact composition differs"
    )
    reduction = {
        "reduction_version": REDUCTION_VERSION,
        "proof_policy": (
            "ENUMERATE_ALL_FINITE_STATUS_METHOD_REASON_CENSORING_ERROR_AND_A1_BRANCHES_"
            "WITH_CANONICAL_LENGTH_AND_PREDICATE_EQUIVALENT_SCALAR_ENDPOINTS"
        ),
        "safe_integer_representatives": [0, SAFE_INTEGER_MAXIMUM],
        "marker_ordinal_representative": SAFE_INTEGER_MAXIMUM,
        "preceding_checkpoint_policy": (
            "63_TARGET_BOUNDARY_PLACEHOLDERS_PROVE_FINAL_EXACT_MARKER_FEASIBLE"
        ),
        "text_policy": (
            "CLOSED_ENUM_LONGEST_CANONICAL_LITERAL_OR_EXACT_LONGEST_ACCEPTED_DFA_WORD"
        ),
        "collection_policy": (
            "ENUMERATE_CARDINALITY_ENDPOINTS_AND_A1_CARDINALITIES_0_THROUGH_4"
        ),
        "identity_policy": "RECOMPUTE_ALL_IDENTITIES_FIXED_64_HEX_CHARACTER_WIDTH",
        "source_errno_name_maximum": errno_name,
        "source_error_class_maximum_sha256": _sha256(error_class.encode("ascii")),
        "source_error_class_maximum_octets": len(error_class),
        "separator_branch_count": len(branch_rows),
        "ordinary_singleton_component_count": FIELD_COUNT - len(A1_FIELDS),
        "a1_component_field_count": len(A1_FIELDS),
    }
    certificate: dict[str, Any] = {
        "certificate_version": CERTIFICATE_VERSION,
        "case_binding": {
            "case_position": CASE_POSITION,
            "profile_position": PROFILE_POSITION,
            "constraint_scope_profile_id": PROFILE_ID,
            "logical_count_plan_id": PLAN_ID,
            "profile_conditioning_program_id": PROGRAM_ID,
            "measured_sequence_ordinal": MEASURED_SEQUENCE_ORDINAL,
            "target_type_name": "TargetObservationV2",
        },
        "authority_sha256_by_path": dict(sorted(PINNED_SHA256.items())),
        "case435_dependency_manifest_id": DEPENDENCY_MANIFEST_ID,
        "finite_domain_reduction": reduction,
        "ordered_separator_branch_bound_records": branch_rows,
        "ordered_field_maximum_records": field_rows,
        "a1_component_certificate": {
            "ordered_field_ids": list(A1_FIELDS),
            "reduced_cartesian_tuple_count": (
                len(legal_sets[A1_FIELDS[0]])
                * len(legal_sets[A1_FIELDS[1]])
                * len(legal_sets[A1_FIELDS[2]])
            ),
            "legal_reduced_tuple_count": len(a1_legal_tuples),
            "maximum_component_canonical_octets": sum(
                len(_canonical_bytes(item[1])) for item in a1_winner
            ),
            "winner_field_observation_id_vector_sha256": _sha256(
                _canonical_bytes(
                    [item[1]["field_observation_id"] for item in a1_winner]
                )
            ),
            "winner_activates_constraint": all(
                item[1]["availability"] == "AVAILABLE" for item in a1_winner
            ),
        },
        "separator_feasibility_certificate": {
            "observation_count": len(observations),
            "preceding_placeholder_count": len(preceding),
            "selected_exact_marker_count": 1,
            "exact_marker_ordinal_vector": [SAFE_INTEGER_MAXIMUM],
            "ordered_context_projection_sha256": _sha256(
                _canonical_bytes(
                    [
                        {
                            "binding_reason": row["observation_context"][
                                "checkpoint_binding_unavailable_reason"
                            ],
                            "binding_status": row["observation_context"][
                                "checkpoint_binding_status"
                            ],
                            "marker_ordinal": row["observation_context"][
                                "marker_ordinal"
                            ],
                            "observation_context_id": row["observation_context_id"],
                            "observation_role": row["observation_context"][
                                "observation_role"
                            ],
                            "selector_position": row["observation_context"][
                                "checkpoint_selector_position"
                            ],
                        }
                        for row in observations
                    ]
                )
            ),
            "ordered_observation_id_vector_sha256": _sha256(
                _canonical_bytes(full_root["ordered_observation_ids"])
            ),
            "root_id": full_root["target_observation_root_sha256"],
            "root_canonical_sha256": _sha256(_canonical_bytes(full_root)),
            "lifecycle_feasible": True,
        },
        "canonical_composition": {
            "fixed_noncontext_nonfield_octets": 422,
            "context_canonical_octets": len(_canonical_bytes(exact_context)),
            "field_array_bracket_octets": 2,
            "field_array_comma_octets": 184,
            "field_maximum_sum_octets": field_sum,
            "exact_upper_bound_octets": composition_total,
            "codec_relation": "LT",
            "codec_octet_limit": OBSERVATION_CODEC_LIMIT,
            "codec_constraint_satisfied": composition_total < OBSERVATION_CODEC_LIMIT,
            "maximizing_observation_id": exact_observation["observation_id"],
            "maximizing_observation_canonical_sha256": _sha256(exact_raw),
        },
        "exact_upper_bound_octets": composition_total,
        "exact_upper_bound_proved": True,
        "independent_attainer_accepted": False,
        "acceptance_state": "EXACT_UPPER_BOUND_PROVED_INDEPENDENT_ATTAINER_PENDING",
        "correction_subgate": "A4-P6-C435-C1",
        "next_subgate": "A4-P6-C435-C2",
    }
    certificate["case435_upper_certificate_id"] = _certificate_id(certificate)
    return certificate


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) > 1:
        raise SystemExit("usage: solve...py [repository-root]")
    root = (
        pathlib.Path(argv[0]).resolve()
        if argv
        else pathlib.Path(__file__).resolve().parents[2]
    )
    try:
        certificate = solve(root)
    except (UpperBoundError, OSError, KeyError, TypeError, ValueError) as error:
        sys.stderr.write(f"CASE435_UPPER_SOLVER_REJECT: {error}\n")
        return 1
    sys.stdout.write(json.dumps(certificate, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

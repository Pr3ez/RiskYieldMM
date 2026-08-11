#!/usr/bin/env python3
"""Independently replay a portable case-435 exact-upper certificate.

The checker imports neither the upper solver nor the accepted rule runtime.
Its independent oracle enumerates only legal decision-table branches derived
from the pinned registry, whereas the solver generates a broader quotient and
filters it through separately implemented predicates.
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
SAFE_INTEGER_MAXIMUM = 9_007_199_254_740_991
FIELD_COUNT = 185
MEASURED_SEQUENCE_ORDINAL = 64
EXACT_UPPER_BOUND = 257_887
CERTIFICATE_VERSION = (
    "riskyieldmm.raw_v8_step2.maximum_protocol_v2.case435_upper_certificate.v1"
)
CERTIFICATE_DOMAIN = (
    "RiskYieldMMStep2MaximumProtocolV2Case435UpperCertificateV1V4_9F_RawV8"
)
REDUCTION_VERSION = (
    "riskyieldmm.raw_v8_step2.maximum_protocol_v2.finite_canonical_length_quotient.v1"
)
SOURCE_ERROR_DOMAIN = "RiskYieldMMA2MSourceErrorDetailV4_9F_RawV8"

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


class CertificateError(RuntimeError):
    """Raised when a certificate or authority fails closed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CertificateError(message)


def _reject_number(value: str) -> Any:
    raise CertificateError(f"non-integer JSON number is forbidden: {value}")


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
    canonicalization: str, schema_version: str, domain: str, payload: Any
) -> str:
    return _sha256(
        _canonical_bytes(
            {
                "canonicalization_version": canonicalization,
                "domain": domain,
                "payload": payload,
                "schema_version": schema_version,
            }
        )
    )


def _record_identity(
    record: dict[str, Any],
    descriptor: dict[str, Any],
    canonicalization: str,
    schema_version: str,
) -> str:
    payload = {
        name: record[name] for name in descriptor["identity_payload_member_order"]
    }
    identity = _semantic_id(
        canonicalization,
        schema_version,
        descriptor["described_record_domain"],
        payload,
    )
    record[descriptor["identity_field"]] = identity
    return identity


def _index(rows: Any, member: str, expected: int, label: str) -> dict[str, Any]:
    _require(type(rows) is list and len(rows) == expected, f"{label} count differs")
    result: dict[str, Any] = {}
    for row in rows:
        key = row.get(member)
        _require(type(key) is str and key not in result, f"{label} key differs")
        result[key] = row
    return result


def _load_authorities(root: pathlib.Path) -> tuple[dict[str, Any], ...]:
    values: dict[str, dict[str, Any]] = {}
    for relative_path, expected in PINNED_SHA256.items():
        raw = (root / relative_path).read_bytes()
        _require(_sha256(raw) == expected, f"authority hash differs: {relative_path}")
        if relative_path.endswith(".json"):
            values[relative_path] = _strict_load(raw, relative_path)
    return (
        values[SEED_PATH],
        values[INVENTORY_PATH],
        values[REGISTRY_PATH],
        values[LITERAL_PATH],
        values[APPLICATION_LEDGER_PATH],
    )


def _longest(values: list[Any]) -> Any:
    _require(values, "finite domain is empty")
    return max(
        values,
        key=lambda value: (len(_canonical_bytes(value)), _canonical_bytes(value)),
    )


def _dfa_word(dfa: dict[str, Any]) -> str:
    transitions = dfa["ordered_transition_rows"]
    accepting = set(dfa["ordered_accepting_states"])
    memo: dict[tuple[Any, int], bool] = {}

    def reachable(state: Any, remaining: int) -> bool:
        key = (state, remaining)
        if key not in memo:
            memo[key] = (
                state in accepting
                if remaining == 0
                else any(
                    row["source_state"] == state
                    and reachable(row["target_state"], remaining - 1)
                    for row in transitions
                )
            )
        return memo[key]

    length = next(
        (
            size
            for size in range(dfa["maximum_octets"], dfa["minimum_octets"] - 1, -1)
            if reachable(dfa["start_state"], size)
        ),
        None,
    )
    _require(length is not None, "DFA language is empty")
    state = dfa["start_state"]
    result = bytearray()
    for remaining in range(length, 0, -1):
        choices = []
        for row in transitions:
            low = row["inclusive_byte_minimum"]
            high = row["inclusive_byte_maximum"]
            _require(
                low >= 32
                and not low <= ord('"') <= high
                and not low <= ord("\\") <= high,
                "DFA JSON-width proof differs",
            )
            if row["source_state"] == state and reachable(
                row["target_state"], remaining - 1
            ):
                choices.append((high, row["target_state"]))
        _require(choices, "DFA path is unresolved")
        byte, state = max(choices)
        result.append(byte)
    return result.decode("ascii")


def _scalar_maximum(constraint: dict[str, Any], vocabularies: dict[str, Any]) -> Any:
    profile = constraint["scalar_profile"]
    if profile == "EXACT_BOOL":
        return False
    if profile == "SAFE_IJSON_UINT":
        return constraint["integer_maximum"]
    if profile == "ENUM":
        return _longest(vocabularies[constraint["vocabulary_id"]]["members"])
    if profile == "SHA256":
        return "f" * 64
    if profile == "UINT128_DECIMAL":
        return constraint["decimal_maximum"]
    if profile == "PLATFORM_ERRNO":
        value = "Z" * 64
        _require(
            re.fullmatch(constraint["text_ascii_pattern"], value, flags=re.ASCII)
            is not None,
            "platform errno representative differs",
        )
        return value
    raise CertificateError(f"unresolved scalar profile: {profile}")


def _target_value(
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
        endpoint = constraint["integer_maximum"]
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
                endpoint if relation in {"EXACT", "LOWER_BOUND", "INTERVAL"} else None
            ),
            "relation": relation,
            "upper_nanoseconds": (
                endpoint if relation in {"EXACT", "UPPER_BOUND", "INTERVAL"} else None
            ),
        }
    if kind in {"BOOL", "UINT", "TEXT"}:
        return {"kind": kind, "value": _scalar_maximum(constraint, vocabularies)}
    if kind in {"OPTIONAL_UINT", "OPTIONAL_TEXT"}:
        return _longest(
            [
                {
                    "kind": kind,
                    "present": True,
                    "value": _scalar_maximum(constraint, vocabularies),
                },
                {"kind": kind, "present": False, "value": None},
            ]
        )
    item = constraints[constraint["collection_item_constraint_id"]]
    shape = shapes[descriptor["value_shape_id"]]
    if kind in {"UINT_LIST", "TEXT_LIST"}:
        return {
            "kind": kind,
            "values": [_scalar_maximum(item, vocabularies)] * shape["maximum_items"],
        }
    if kind == "FIXED_UINT_MAP":
        scalar = _scalar_maximum(item, vocabularies)
        return {
            "kind": kind,
            "ordered": [
                {"key": key, "value": scalar} for key in descriptor["value_shape_keys"]
            ],
        }
    raise CertificateError(f"unresolved target kind: {kind}")


def _source_digest(
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
    _require(len(_canonical_bytes(payload)) <= 2_048, "source preimage exceeds bound")
    return _semantic_id(canonicalization, schema_version, SOURCE_ERROR_DOMAIN, payload)


def _base_field(
    frozen: dict[str, Any], context_id: str, registry_id: str
) -> dict[str, Any]:
    field = dict(frozen)
    field["observation_context_id"] = context_id
    field["target_field_registry_id"] = registry_id
    return field


def _available(
    frozen: dict[str, Any],
    descriptor: dict[str, Any],
    context_id: str,
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
    field = _base_field(frozen, context_id, registry_id)
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
            "value": _target_value(
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


def _reason(
    frozen: dict[str, Any],
    context_id: str,
    registry_id: str,
    method: str,
    reason: str,
    rule: dict[str, Any],
    attempt_row: dict[str, Any],
    error_form: str,
    field_type: dict[str, Any],
    canonicalization: str,
    schema_version: str,
    errno_name: str,
    error_class: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    field = _base_field(frozen, context_id, registry_id)
    span = {
        "AVAILABLE_ONLY": "AVAILABLE",
        "NOT_APPLICABLE_ONLY": "NOT_APPLICABLE",
        "UNAVAILABLE_ONLY": "UNAVAILABLE",
    }[attempt_row["adapter_span_policy"]]
    attempted = attempt_row["attempt_state"] == "ATTEMPTED"
    phase = _longest(attempt_row["permitted_failure_phases"])
    field.update(
        {
            "adapter_span_status": span,
            "availability": rule["required_availability"],
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
        field.update(
            {
                "source_errno_number": SAFE_INTEGER_MAXIMUM,
                "source_errno_name": errno_name,
                "source_error_class": error_class,
            }
        )
    elif error_form == "OS_ONLY":
        field.update(
            {
                "source_errno_number": SAFE_INTEGER_MAXIMUM,
                "source_errno_name": errno_name,
                "source_error_class": None,
            }
        )
    elif error_form == "NON_OS":
        field.update(
            {
                "source_errno_number": None,
                "source_errno_name": None,
                "source_error_class": error_class,
            }
        )
    else:
        field.update(
            {
                "source_errno_number": None,
                "source_errno_name": None,
                "source_error_class": None,
            }
        )
    field["source_error_detail_sha256"] = _source_digest(
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


def _error_forms(forms: list[str]) -> list[str]:
    result: list[str] = []
    if "OS" in forms:
        result.extend(("OS_PLUS_NON_OS_DETAIL", "OS_ONLY"))
    if "NON_OS" in forms:
        result.append("NON_OS")
    if "STATUS_ONLY" in forms:
        result.append("STATUS_ONLY")
    elif "NONE" in forms:
        result.append("NONE")
    return result


def _legal_candidates(
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
) -> tuple[int, list[tuple[dict[str, Any], dict[str, Any]]]]:
    operation_applies = (
        context["operation_kind"] in descriptor["applicable_operation_kinds"]
    )
    methods = (
        [
            row["observation_method"]
            for row in descriptor["observation_method_role_pairs"]
            if context["observation_role"] in row["allowed_roles"]
            and context["checkpoint_marker_kind"]
            in descriptor["allowed_checkpoint_marker_kinds"]
        ]
        if operation_applies
        else []
    )
    broad: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for method in methods:
        broad.append(
            _available(
                frozen,
                descriptor,
                context["observation_context_id"],
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
                broad.append(
                    _available(
                        frozen,
                        descriptor,
                        context["observation_context_id"],
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
        rule = reason_rules.get(reason)
        if rule is None:
            continue
        for attempt_row in rule["attempt_state_error_forms"]:
            selected_methods = (
                methods
                if attempt_row["attempt_state"] == "ATTEMPTED"
                else ["NOT_ATTEMPTED"]
            )
            for method, error_form in product(
                selected_methods, _error_forms(attempt_row["permitted_error_forms"])
            ):
                broad.append(
                    _reason(
                        frozen,
                        context["observation_context_id"],
                        registry_id,
                        method,
                        reason,
                        rule,
                        attempt_row,
                        error_form,
                        field_type,
                        canonicalization,
                        schema_version,
                        errno_name,
                        error_class,
                    )
                )
    legal = []
    placeholder_reasons = set(PLACEHOLDER_FIELD_REASON.values())
    for item in broad:
        field = item[1]
        reason = field["unavailable_reason"]
        if reason in placeholder_reasons or reason == "INSTRUMENTATION_DISABLED":
            continue
        if operation_applies:
            if reason == "NOT_APPLICABLE_TO_OPERATION":
                continue
        elif not (
            field["availability"] == "NOT_APPLICABLE"
            and reason == "NOT_APPLICABLE_TO_OPERATION"
        ):
            continue
        if len(_canonical_bytes(field)) > 4_096:
            continue
        legal.append(item)
    if descriptor["field_id"] in A1_FIELDS:
        available = [item for item in broad if item[1]["availability"] == "AVAILABLE"]
        _require(available, "A1 available branch is absent")
        base_branch, base = max(
            available,
            key=lambda item: (
                len(_canonical_bytes(item[1])),
                _canonical_bytes(item[1]),
            ),
        )
        kind = _longest(vocabularies["RAW_V8_A1_COMMAND_KIND"]["members"])
        for cardinality in range(5):
            field = json.loads(json.dumps(base))
            if descriptor["field_id"] == A1_FIELDS[0]:
                field["value"] = {"kind": "UINT", "value": cardinality}
            elif descriptor["field_id"] == A1_FIELDS[1]:
                field["value"] = {
                    "kind": "TEXT_LIST",
                    "values": [kind] * cardinality,
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
            broad.append((branch, field))
            legal.append((branch, field))
    return len(broad), legal


def _a1_valid(items: tuple[tuple[dict[str, Any], dict[str, Any]], ...]) -> bool:
    fields = [item[1] for item in items]
    if any(field["availability"] != "AVAILABLE" for field in fields):
        return True
    by_id = {field["field_id"]: field for field in fields}
    count = by_id[A1_FIELDS[0]]["value"]["value"]
    kinds = by_id[A1_FIELDS[1]]["value"]["values"]
    sequences = by_id[A1_FIELDS[2]]["value"]["values"]
    return (
        count == len(kinds) == len(sequences)
        and len(sequences) <= 4
        and all(left < right for left, right in zip(sequences, sequences[1:]))
    )


def _winner_key(item: tuple[dict[str, Any], dict[str, Any]]) -> tuple[Any, ...]:
    raw = _canonical_bytes(item[1])
    return len(raw), raw, _canonical_bytes(item[0])


def _exact_context(
    fixture: dict[str, Any],
    root: dict[str, Any],
    selector: dict[str, Any],
    entry: dict[str, Any],
    types: dict[str, Any],
    canonicalization: str,
    schema_version: str,
    registry_id: str,
) -> dict[str, Any]:
    context = json.loads(json.dumps(fixture))
    context.update(
        {
            "attempt_id": root["attempt_id"],
            "candidate_id": root["candidate_id"],
            "checkpoint_binding_status": "EXACT_MARKER",
            "checkpoint_binding_unavailable_reason": None,
            "checkpoint_marker_kind": entry["checkpoint_marker_kind"],
            "checkpoint_selector_entry_id": entry["checkpoint_selector_entry_id"],
            "checkpoint_selector_position": entry["selector_position"],
            "expected_checkpoint_marker_kind": entry["checkpoint_marker_kind"],
            "expected_occurrence_index_within_kind": entry[
                "occurrence_index_within_kind"
            ],
            "full_checkpoint_selector_id": selector["checkpoint_selector_id"],
            "instrumentation_mode": "ON",
            "marker_ordinal": SAFE_INTEGER_MAXIMUM,
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
            "completed_offset_nanoseconds": SAFE_INTEGER_MAXIMUM,
            "span_status": "AVAILABLE",
            "started_offset_nanoseconds": SAFE_INTEGER_MAXIMUM,
            "unavailable_reason": None,
        }
    _record_identity(
        context,
        types["TargetObservationContextV2"],
        canonicalization,
        schema_version,
    )
    return context


def _rebind(
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


def _placeholder(
    source: dict[str, Any],
    root: dict[str, Any],
    selector: dict[str, Any],
    entry: dict[str, Any],
    types: dict[str, Any],
    canonicalization: str,
    schema_version: str,
    registry_id: str,
) -> dict[str, Any]:
    observation = json.loads(json.dumps(source))
    observation["observation_context"].update(
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
    return _rebind(
        observation, root, types, canonicalization, schema_version, registry_id
    )


def _separator_projection(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "binding_reason": row["observation_context"][
                "checkpoint_binding_unavailable_reason"
            ],
            "binding_status": row["observation_context"]["checkpoint_binding_status"],
            "marker_ordinal": row["observation_context"]["marker_ordinal"],
            "observation_context_id": row["observation_context_id"],
            "observation_role": row["observation_context"]["observation_role"],
            "selector_position": row["observation_context"][
                "checkpoint_selector_position"
            ],
        }
        for row in observations
    ]


def verify(
    repository_root: pathlib.Path | str,
    certificate_source: pathlib.Path | str | bytes,
) -> dict[str, Any]:
    root_path = pathlib.Path(repository_root)
    certificate_raw = (
        certificate_source
        if isinstance(certificate_source, bytes)
        else pathlib.Path(certificate_source).read_bytes()
    )
    certificate = _strict_load(certificate_raw, "certificate")
    expected_members = {
        "certificate_version",
        "case_binding",
        "authority_sha256_by_path",
        "case435_dependency_manifest_id",
        "finite_domain_reduction",
        "ordered_separator_branch_bound_records",
        "ordered_field_maximum_records",
        "a1_component_certificate",
        "separator_feasibility_certificate",
        "canonical_composition",
        "exact_upper_bound_octets",
        "exact_upper_bound_proved",
        "independent_attainer_accepted",
        "acceptance_state",
        "correction_subgate",
        "next_subgate",
        "case435_upper_certificate_id",
    }
    _require(set(certificate) == expected_members, "certificate members differ")
    supplied_id = certificate["case435_upper_certificate_id"]
    identity_payload = {
        key: value
        for key, value in certificate.items()
        if key != "case435_upper_certificate_id"
    }
    expected_id = _sha256(
        _canonical_bytes({"domain": CERTIFICATE_DOMAIN, "payload": identity_payload})
    )
    _require(supplied_id == expected_id, "certificate identity differs")
    _require(
        certificate["certificate_version"] == CERTIFICATE_VERSION
        and certificate["case435_dependency_manifest_id"] == DEPENDENCY_MANIFEST_ID
        and certificate["authority_sha256_by_path"]
        == dict(sorted(PINNED_SHA256.items())),
        "certificate authority binding differs",
    )
    seed, inventory, registry, literal, ledger = _load_authorities(root_path)
    _require(
        inventory["external_schema_registry_v2"] == registry, "registry join differs"
    )
    _require(
        literal["target_field_registry"] == inventory["target_field_registry"],
        "literal registry differs",
    )
    canonicalization = seed["canonicalization_version"]
    schema_version = seed["measurement_schema_version"]
    plan = seed["logical_plan_recipe_catalog"]["ordered_logical_count_plan_records"][
        CASE_POSITION - 1
    ]
    expected_binding = {
        "case_position": CASE_POSITION,
        "profile_position": PROFILE_POSITION,
        "constraint_scope_profile_id": PROFILE_ID,
        "logical_count_plan_id": PLAN_ID,
        "profile_conditioning_program_id": PROGRAM_ID,
        "measured_sequence_ordinal": MEASURED_SEQUENCE_ORDINAL,
        "target_type_name": "TargetObservationV2",
    }
    _require(
        certificate["case_binding"] == expected_binding
        and plan["logical_count_plan_id"] == PLAN_ID
        and plan["profile_conditioning_program_id"] == PROGRAM_ID,
        "case binding differs",
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
            rules[rule_id] == ledger_rules[rule_id], f"rule join differs: {rule_id}"
        )
    target_registry = inventory["target_field_registry"]
    descriptors = target_registry["descriptors"]
    constraints = _index(
        target_registry["ordered_value_constraint_definitions"],
        "value_constraint_id",
        17,
        "constraint",
    )
    shapes = _index(
        target_registry["ordered_value_shape_definitions"], "value_shape_id", 6, "shape"
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
    field_type = types["TargetFieldObservationV1"]
    field_members = {
        row["member_name"]: schemas[row["value_schema_id"]]
        for row in field_type["record_member_descriptors"]
    }
    error_language = languages[field_members["source_error_class"]["text_language_id"]]
    errno_language = languages[field_members["source_errno_name"]["text_language_id"]]
    error_class = _dfa_word(dfas[error_language["ascii_dfa_id"]])
    errno_name = _dfa_word(dfas[errno_language["ascii_dfa_id"]])
    reduction = certificate["finite_domain_reduction"]
    _require(
        reduction["reduction_version"] == REDUCTION_VERSION
        and reduction["safe_integer_representatives"] == [0, SAFE_INTEGER_MAXIMUM]
        and reduction["source_errno_name_maximum"] == errno_name
        and reduction["source_error_class_maximum_sha256"]
        == _sha256(error_class.encode("ascii"))
        and reduction["source_error_class_maximum_octets"] == len(error_class) == 256,
        "finite-domain reduction differs",
    )
    fixtures = inventory["fixture_records"]["target_observation_v2_fixtures"]
    maximum_root = fixtures["maximum_selector_target_observation_root"]
    selector = next(
        row["selector"]
        for row in inventory["checkpoint_selector_catalog"]
        if row["selector"]["checkpoint_selector_id"]
        == maximum_root["full_checkpoint_selector_id"]
    )
    entry = selector["ordered_entries"][MEASURED_SEQUENCE_ORDINAL - 1]
    context = _exact_context(
        fixtures["checkpoint_exact_marker_observation"]["observation_context"],
        maximum_root,
        selector,
        entry,
        types,
        canonicalization,
        schema_version,
        target_registry["target_field_registry_id"],
    )
    _require(len(_canonical_bytes(context)) == 1_747, "context maximum differs")
    frozen_fields = fixtures["checkpoint_exact_marker_observation"][
        "field_observations"
    ]
    broad_counts: dict[str, int] = {}
    legal: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    for frozen, descriptor in zip(frozen_fields, descriptors, strict=True):
        broad_count, candidates = _legal_candidates(
            frozen,
            descriptor,
            context,
            target_registry["target_field_registry_id"],
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
        _require(candidates, f"legal candidate set is empty: {descriptor['field_id']}")
        broad_counts[descriptor["field_id"]] = broad_count
        legal[descriptor["field_id"]] = candidates
    a1_tuples = [
        rows
        for rows in product(*(legal[field_id] for field_id in A1_FIELDS))
        if _a1_valid(rows)
    ]
    a1_winner = max(
        a1_tuples,
        key=lambda rows: (
            sum(len(_canonical_bytes(item[1])) for item in rows),
            _canonical_bytes([item[1] for item in rows]),
        ),
    )
    winners = dict(zip(A1_FIELDS, a1_winner, strict=True))
    for descriptor in descriptors:
        winners.setdefault(
            descriptor["field_id"], max(legal[descriptor["field_id"]], key=_winner_key)
        )
    expected_field_rows = []
    for position, descriptor in enumerate(descriptors, 1):
        field_id = descriptor["field_id"]
        branch, field = winners[field_id]
        raw = _canonical_bytes(field)
        expected_field_rows.append(
            {
                "field_position": position,
                "field_id": field_id,
                "descriptor_canonical_sha256": _sha256(_canonical_bytes(descriptor)),
                "component_kind": (
                    "A1_FIFO_COUPLED" if field_id in A1_FIELDS else "ORDINARY_SINGLETON"
                ),
                "reduced_candidate_count": broad_counts[field_id],
                "legal_reduced_candidate_count": len(legal[field_id]),
                "maximum_canonical_octets": len(raw),
                "winner_canonical_sha256": _sha256(raw),
                "winner_field_observation_id": field["field_observation_id"],
                "winner_branch": branch,
            }
        )
    _require(
        certificate["ordered_field_maximum_records"] == expected_field_rows,
        "field maximum vector differs",
    )
    expected_a1 = {
        "ordered_field_ids": list(A1_FIELDS),
        "reduced_cartesian_tuple_count": (
            len(legal[A1_FIELDS[0]])
            * len(legal[A1_FIELDS[1]])
            * len(legal[A1_FIELDS[2]])
        ),
        "legal_reduced_tuple_count": len(a1_tuples),
        "maximum_component_canonical_octets": sum(
            len(_canonical_bytes(item[1])) for item in a1_winner
        ),
        "winner_field_observation_id_vector_sha256": _sha256(
            _canonical_bytes([item[1]["field_observation_id"] for item in a1_winner])
        ),
        "winner_activates_constraint": all(
            item[1]["availability"] == "AVAILABLE" for item in a1_winner
        ),
    }
    _require(certificate["a1_component_certificate"] == expected_a1, "A1 proof differs")
    ordered_fields = [winners[row["field_id"]][1] for row in descriptors]
    exact_observation = json.loads(
        json.dumps(fixtures["checkpoint_exact_marker_observation"])
    )
    exact_observation["observation_context"] = context
    exact_observation["observation_context_id"] = context["observation_context_id"]
    exact_observation["field_observations"] = ordered_fields
    _record_identity(
        exact_observation,
        types["TargetObservationV2"],
        canonicalization,
        schema_version,
    )
    exact_raw = _canonical_bytes(exact_observation)
    field_sum = sum(len(_canonical_bytes(field)) for field in ordered_fields)
    _require(
        422 + 1_747 + 2 + 184 + field_sum == len(exact_raw) == EXACT_UPPER_BOUND,
        "canonical composition differs",
    )
    expected_branches = [
        {
            "branch_position": 1,
            "binding_branch": "EXACT_MARKER",
            "binding_reason": None,
            "context_canonical_octets": 1_747,
            "field_maximum_sum_octets": field_sum,
            "observation_canonical_octets": len(exact_raw),
            "observation_canonical_sha256": _sha256(exact_raw),
        }
    ]
    for position, reason in enumerate(PLACEHOLDER_ORDER, 2):
        observation = _placeholder(
            fixtures["checkpoint_placeholder_observations"][reason],
            maximum_root,
            selector,
            entry,
            types,
            canonicalization,
            schema_version,
            target_registry["target_field_registry_id"],
        )
        raw = _canonical_bytes(observation)
        expected_branches.append(
            {
                "branch_position": position,
                "binding_branch": observation["observation_context"][
                    "checkpoint_binding_status"
                ],
                "binding_reason": reason,
                "context_canonical_octets": len(
                    _canonical_bytes(observation["observation_context"])
                ),
                "field_maximum_sum_octets": sum(
                    len(_canonical_bytes(field))
                    for field in observation["field_observations"]
                ),
                "observation_canonical_octets": len(raw),
                "observation_canonical_sha256": _sha256(raw),
            }
        )
    _require(
        certificate["ordered_separator_branch_bound_records"] == expected_branches
        and max(row["observation_canonical_octets"] for row in expected_branches)
        == EXACT_UPPER_BOUND,
        "separator branch proof differs",
    )
    preceding = [
        _placeholder(
            fixtures["checkpoint_placeholder_observations"][
                "TARGET_BOUNDARY_NOT_REACHED"
            ],
            maximum_root,
            selector,
            selected_entry,
            types,
            canonicalization,
            schema_version,
            target_registry["target_field_registry_id"],
        )
        for selected_entry in selector["ordered_entries"][:63]
    ]
    outer = fixtures["off_target_observations"]
    observations = [
        _rebind(
            outer[0],
            maximum_root,
            types,
            canonicalization,
            schema_version,
            target_registry["target_field_registry_id"],
        ),
        *preceding,
        exact_observation,
        _rebind(
            outer[1],
            maximum_root,
            types,
            canonicalization,
            schema_version,
            target_registry["target_field_registry_id"],
        ),
        _rebind(
            outer[2],
            maximum_root,
            types,
            canonicalization,
            schema_version,
            target_registry["target_field_registry_id"],
        ),
    ]
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
    feasibility = {
        "observation_count": 67,
        "preceding_placeholder_count": 63,
        "selected_exact_marker_count": 1,
        "exact_marker_ordinal_vector": [SAFE_INTEGER_MAXIMUM],
        "ordered_context_projection_sha256": _sha256(
            _canonical_bytes(_separator_projection(observations))
        ),
        "ordered_observation_id_vector_sha256": _sha256(
            _canonical_bytes(full_root["ordered_observation_ids"])
        ),
        "root_id": full_root["target_observation_root_sha256"],
        "root_canonical_sha256": _sha256(_canonical_bytes(full_root)),
        "lifecycle_feasible": True,
    }
    _require(
        [row["observation_context"]["observation_role"] for row in observations]
        == ["BEFORE_OPERATION"]
        + ["STABLE_CHECKPOINT"] * 64
        + ["AFTER_OPERATION", "OPERATION_AGGREGATE"]
        and all(
            row["observation_context"]["checkpoint_selector_position"] == position
            for position, row in enumerate(observations[1:65], 1)
        )
        and certificate["separator_feasibility_certificate"] == feasibility,
        "separator feasibility differs",
    )
    expected_composition = {
        "fixed_noncontext_nonfield_octets": 422,
        "context_canonical_octets": 1_747,
        "field_array_bracket_octets": 2,
        "field_array_comma_octets": 184,
        "field_maximum_sum_octets": field_sum,
        "exact_upper_bound_octets": EXACT_UPPER_BOUND,
        "codec_relation": "LT",
        "codec_octet_limit": 262_144,
        "codec_constraint_satisfied": True,
        "maximizing_observation_id": exact_observation["observation_id"],
        "maximizing_observation_canonical_sha256": _sha256(exact_raw),
    }
    _require(
        certificate["canonical_composition"] == expected_composition
        and certificate["exact_upper_bound_octets"] == EXACT_UPPER_BOUND
        and certificate["exact_upper_bound_proved"] is True
        and certificate["independent_attainer_accepted"] is False
        and certificate["acceptance_state"]
        == "EXACT_UPPER_BOUND_PROVED_INDEPENDENT_ATTAINER_PENDING"
        and certificate["correction_subgate"] == "A4-P6-C435-C1"
        and certificate["next_subgate"] == "A4-P6-C435-C2",
        "certificate disposition differs",
    )
    return {
        "verification_version": (
            "riskyieldmm.raw_v8_step2.maximum_protocol_v2."
            "case435_upper_certificate_verification.v1"
        ),
        "case435_upper_certificate_id": supplied_id,
        "exact_upper_bound_octets": EXACT_UPPER_BOUND,
        "field_count": FIELD_COUNT,
        "separator_branch_count": len(expected_branches),
        "legal_reduced_candidate_count": sum(len(rows) for rows in legal.values()),
        "legal_a1_tuple_count": len(a1_tuples),
        "independent_attainer_accepted": False,
        "next_subgate": "A4-P6-C435-C2",
    }


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not 1 <= len(argv) <= 2:
        raise SystemExit("usage: check...py CERTIFICATE [repository-root]")
    certificate_source: pathlib.Path | bytes = (
        sys.stdin.buffer.read()
        if argv[0] in {"-", "/dev/stdin"}
        else pathlib.Path(argv[0]).resolve()
    )
    root = (
        pathlib.Path(argv[1]).resolve()
        if len(argv) == 2
        else pathlib.Path(__file__).resolve().parents[2]
    )
    try:
        report = verify(root, certificate_source)
    except (CertificateError, OSError, KeyError, TypeError, ValueError) as error:
        sys.stderr.write(f"CASE435_UPPER_CERTIFICATE_REJECT: {error}\n")
        return 1
    sys.stdout.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

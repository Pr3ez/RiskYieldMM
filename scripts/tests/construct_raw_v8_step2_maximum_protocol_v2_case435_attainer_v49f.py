#!/usr/bin/env python3
"""Construct a case-435 P1-legal retained witness without C1 inputs.

This program uses the accepted schema/rule runtime only as the frozen P1
execution authority.  Its witness search, identity construction, lifecycle
assembly, measurement, and certificate publication are local to this source.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import importlib.util
import json
import pathlib
import sys
from itertools import product
from types import ModuleType
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
MEASURED_SEQUENCE_ORDINAL = 64
PROFILE_ID = "505dac244288e6fb666919c99567f883c28ed573a898ce2a5dd680744dd57540"
PLAN_ID = "9f8cd8303e3a9360986f0294210dda931e827af6eed4ec76b0c084e54f722c4a"
PROGRAM_ID = "0e4a94fb5b99c464e7db1ef0fc0525b9408683a004a5ea034fcfbf5c427eb4e8"
DEPENDENCY_MANIFEST_ID = (
    "d80797d6d34486ed15f73d19a201c7b5ff0ac19593e25302bcba081c2e7b5c3c"
)
FIELD_COUNT = 185
SOURCE_ERROR_DOMAIN = "RiskYieldMMA2MSourceErrorDetailV4_9F_RawV8"
ATTAINER_CERTIFICATE_VERSION = (
    "riskyieldmm.raw_v8_step2.maximum_protocol_v2.case435_attainer_certificate.v1"
)
ATTAINER_CERTIFICATE_DOMAIN = (
    "RiskYieldMMStep2MaximumProtocolV2Case435AttainerCertificateV1V4_9F_RawV8"
)
CONSTRUCTION_PROTOCOL_VERSION = (
    "riskyieldmm.raw_v8_step2.maximum_protocol_v2."
    "case435_independent_longest_first_attainer.v1"
)
A1_FIELDS = (
    "a1.waiting_count",
    "a1.waiting_kinds",
    "a1.waiting_sequences",
)
PLACEHOLDER_FIELD_REASON = {
    "ARTIFACT_BOUND_EXCEEDED": "CHECKPOINT_PLACEHOLDER_ARTIFACT_BOUND_EXCEEDED",
    "OBSERVER_INTERNAL_ERROR": "CHECKPOINT_PLACEHOLDER_OBSERVER_INTERNAL_ERROR",
    "SOURCE_CLOCK_UNAVAILABLE": "CHECKPOINT_PLACEHOLDER_SOURCE_CLOCK_UNAVAILABLE",
    "TARGET_BOUNDARY_NOT_REACHED": (
        "CHECKPOINT_PLACEHOLDER_TARGET_BOUNDARY_NOT_REACHED"
    ),
}
APPLICATION_ORDER = (
    "APPLY/SELECTOR_MARKER_CONTRACT_V1",
    "APPLY/V2_OBSERVATION_AGGREGATE_REGISTRY_V1",
    "APPLY/V2_OBSERVATION_FIELDS_REGISTRY_V1",
    "APPLY/V2_ROOT_OBSERVATION_MEMBERSHIP_V1",
    "APPLY/V2_ROOT_SELECTOR_LIFECYCLE_V1",
)


class AttainerError(RuntimeError):
    """Raised when independent construction or P1 execution fails closed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AttainerError(message)


def _reject_number(value: str) -> Any:
    raise AttainerError(f"non-integer JSON number is forbidden: {value}")


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


def _record_identity(
    record: dict[str, Any],
    descriptor: dict[str, Any],
    canonicalization_version: str,
    schema_version: str,
) -> str:
    identity_member = descriptor["identity_field"]
    payload = {
        member: record[member] for member in descriptor["identity_payload_member_order"]
    }
    identity = _semantic_id(
        canonicalization_version,
        schema_version,
        descriptor["described_record_domain"],
        payload,
    )
    record[identity_member] = identity
    return identity


def _index(rows: Any, member: str, expected_count: int, label: str) -> dict[str, Any]:
    _require(
        type(rows) is list and len(rows) == expected_count,
        f"{label} count differs",
    )
    result: dict[str, Any] = {}
    for row in rows:
        _require(type(row) is dict, f"{label} row is not an object")
        key = row.get(member)
        _require(type(key) is str and key not in result, f"{label} key differs")
        result[key] = row
    return result


def _load_authorities(root: pathlib.Path) -> tuple[dict[str, Any], ...]:
    loaded: dict[str, dict[str, Any]] = {}
    for relative_path, expected_hash in PINNED_SHA256.items():
        path = root / relative_path
        _require(
            path.is_file() and not path.is_symlink(),
            f"authority absent: {relative_path}",
        )
        raw = path.read_bytes()
        _require(
            _sha256(raw) == expected_hash,
            f"authority hash differs: {relative_path}",
        )
        if relative_path.endswith(".json"):
            loaded[relative_path] = _strict_load(raw, relative_path)
    return (
        loaded[SEED_PATH],
        loaded[INVENTORY_PATH],
        loaded[REGISTRY_PATH],
        loaded[LITERAL_PATH],
        loaded[APPLICATION_LEDGER_PATH],
    )


def _load_runtime(root: pathlib.Path) -> ModuleType:
    path = root / RUNTIME_PATH
    spec = importlib.util.spec_from_file_location("case435_attainer_p1_runtime", path)
    _require(spec is not None and spec.loader is not None, "P1 runtime is unloadable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _longest(values: list[Any]) -> Any:
    _require(bool(values), "closed value domain is empty")
    return max(
        values,
        key=lambda value: (len(_canonical_bytes(value)), _canonical_bytes(value)),
    )


def _longest_dfa_word(dfa: dict[str, Any]) -> str:
    transitions = dfa["ordered_transition_rows"]
    accepting = set(dfa["ordered_accepting_states"])
    reachable: dict[tuple[Any, int], bool] = {}

    def accepts_suffix(state: Any, remaining: int) -> bool:
        key = (state, remaining)
        if key not in reachable:
            reachable[key] = (
                state in accepting
                if remaining == 0
                else any(
                    row["source_state"] == state
                    and accepts_suffix(row["target_state"], remaining - 1)
                    for row in transitions
                )
            )
        return reachable[key]

    length = next(
        (
            candidate
            for candidate in range(dfa["maximum_octets"], dfa["minimum_octets"] - 1, -1)
            if accepts_suffix(dfa["start_state"], candidate)
        ),
        None,
    )
    _require(length is not None, "DFA language has no accepted word")
    state = dfa["start_state"]
    result = bytearray()
    for remaining in range(length, 0, -1):
        choices: list[tuple[int, Any]] = []
        for row in transitions:
            if row["source_state"] != state:
                continue
            for byte in range(
                row["inclusive_byte_maximum"],
                row["inclusive_byte_minimum"] - 1,
                -1,
            ):
                if byte in {ord('"'), ord("\\")} or byte < 32:
                    continue
                if accepts_suffix(row["target_state"], remaining - 1):
                    choices.append((byte, row["target_state"]))
                    break
        _require(bool(choices), "DFA longest-word path is unresolved")
        byte, state = max(choices)
        result.append(byte)
    return result.decode("ascii")


def _scalar_witness(constraint: dict[str, Any], vocabularies: dict[str, Any]) -> Any:
    profile = constraint["scalar_profile"]
    if profile == "EXACT_BOOL":
        return _longest([False, True])
    if profile == "SAFE_IJSON_UINT":
        return _longest([constraint["integer_minimum"], constraint["integer_maximum"]])
    if profile == "ENUM":
        return _longest(vocabularies[constraint["vocabulary_id"]]["members"])
    if profile == "SHA256":
        return "f" * 64
    if profile == "UINT128_DECIMAL":
        return constraint["decimal_maximum"]
    if profile == "PLATFORM_ERRNO":
        return "Z" + "_" * 63
    raise AttainerError(f"unresolved scalar profile: {profile}")


def _target_value_witness(
    descriptor: dict[str, Any],
    constraints: dict[str, Any],
    shapes: dict[str, Any],
    vocabularies: dict[str, Any],
    *,
    censoring: str | None,
) -> dict[str, Any]:
    kind = descriptor["value_kind"]
    constraint = constraints[descriptor["value_constraint_id"]]
    if kind == "DURATION_BOUND":
        endpoint = constraint["integer_maximum"]
        relation = {
            None: "EXACT",
            "INTERVAL": "INTERVAL",
            "LEFT": "UPPER_BOUND",
            "RIGHT": "LOWER_BOUND",
        }[censoring]
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
        return {"kind": kind, "value": _scalar_witness(constraint, vocabularies)}
    if kind in {"OPTIONAL_UINT", "OPTIONAL_TEXT"}:
        return _longest(
            [
                {
                    "kind": kind,
                    "present": True,
                    "value": _scalar_witness(constraint, vocabularies),
                },
                {"kind": kind, "present": False, "value": None},
            ]
        )
    item_constraint = constraints[constraint["collection_item_constraint_id"]]
    shape = shapes[descriptor["value_shape_id"]]
    item = _scalar_witness(item_constraint, vocabularies)
    if kind in {"UINT_LIST", "TEXT_LIST"}:
        return {"kind": kind, "values": [item] * shape["maximum_items"]}
    if kind == "FIXED_UINT_MAP":
        return {
            "kind": kind,
            "ordered": [
                {"key": key, "value": item} for key in descriptor["value_shape_keys"]
            ],
        }
    raise AttainerError(f"unresolved target value kind: {kind}")


def _source_error_digest(
    field: dict[str, Any], canonicalization: str, schema_version: str
) -> str | None:
    if field["source_error_class"] is None:
        return None
    payload = {
        member: field[member]
        for member in (
            "field_id",
            "observation_method",
            "source_failure_phase",
            "source_errno_number",
            "source_errno_name",
            "source_error_class",
        )
    }
    return _semantic_id(
        canonicalization,
        schema_version,
        SOURCE_ERROR_DOMAIN,
        payload,
    )


def _context(
    fixture: dict[str, Any],
    root: dict[str, Any],
    selector: dict[str, Any],
    entry: dict[str, Any],
    registry_id: str,
    context_type: dict[str, Any],
    canonicalization: str,
    schema_version: str,
    safe_integer_endpoint: int,
) -> dict[str, Any]:
    context = copy.deepcopy(fixture)
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
            "marker_ordinal": safe_integer_endpoint,
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
            "completed_offset_nanoseconds": safe_integer_endpoint,
            "span_status": "AVAILABLE",
            "started_offset_nanoseconds": safe_integer_endpoint,
            "unavailable_reason": None,
        }
    _record_identity(context, context_type, canonicalization, schema_version)
    return context


def _candidate_base(
    frozen: dict[str, Any], context_id: str, registry_id: str
) -> dict[str, Any]:
    field = copy.deepcopy(frozen)
    field["observation_context_id"] = context_id
    field["target_field_registry_id"] = registry_id
    return field


def _methods(descriptor: dict[str, Any], context: dict[str, Any]) -> list[str]:
    if context["operation_kind"] not in descriptor["applicable_operation_kinds"]:
        return []
    if (
        context["observation_role"] == "STABLE_CHECKPOINT"
        and context["checkpoint_marker_kind"]
        not in descriptor["allowed_checkpoint_marker_kinds"]
    ):
        return []
    return [
        row["observation_method"]
        for row in descriptor["observation_method_role_pairs"]
        if context["observation_role"] in row["allowed_roles"]
    ]


def _available_proposal(
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
    safe_integer_endpoint: int,
    *,
    censoring: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    field = _candidate_base(
        frozen,
        context["observation_context_id"],
        registry_id,
    )
    field.update(
        {
            "adapter_span_status": "AVAILABLE",
            "availability": "AVAILABLE" if censoring is None else "CENSORED",
            "censoring": "NONE" if censoring is None else censoring,
            "observation_attempt": "ATTEMPTED",
            "observation_completed_offset_nanoseconds": safe_integer_endpoint,
            "observation_method": method,
            "observation_started_offset_nanoseconds": safe_integer_endpoint,
            "source_errno_name": None,
            "source_errno_number": None,
            "source_error_class": None,
            "source_error_detail_sha256": None,
            "source_failure_phase": "NONE",
            "unavailable_reason": None,
            "value": _target_value_witness(
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
            "branch_kind": "AVAILABLE_VALUE" if censoring is None else "CENSORED_VALUE",
            "censoring": censoring,
            "error_form": "NONE",
            "method": method,
            "phase": "NONE",
            "reason": None,
        },
        field,
    )


def _error_variants(forms: list[str]) -> list[str]:
    variants: list[str] = []
    if "OS" in forms:
        variants.extend(("OS_PLUS_NON_OS_DETAIL", "OS_ONLY"))
    if "NON_OS" in forms:
        variants.append("NON_OS")
    if "STATUS_ONLY" in forms:
        variants.append("STATUS_ONLY")
    if "NONE" in forms:
        variants.append("NONE")
    return variants


def _reason_proposal(
    frozen: dict[str, Any],
    context: dict[str, Any],
    registry_id: str,
    method: str,
    reason: str,
    reason_policy: dict[str, Any],
    attempt_policy: dict[str, Any],
    phase: str,
    error_form: str,
    errno_name: str,
    error_class: str,
    field_type: dict[str, Any],
    canonicalization: str,
    schema_version: str,
    safe_integer_endpoint: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    field = _candidate_base(
        frozen,
        context["observation_context_id"],
        registry_id,
    )
    span = {
        "AVAILABLE_ONLY": "AVAILABLE",
        "NOT_APPLICABLE_ONLY": "NOT_APPLICABLE",
        "UNAVAILABLE_ONLY": "UNAVAILABLE",
    }[attempt_policy["adapter_span_policy"]]
    field.update(
        {
            "adapter_span_status": span,
            "availability": reason_policy["required_availability"],
            "censoring": "NONE",
            "observation_attempt": attempt_policy["attempt_state"],
            "observation_completed_offset_nanoseconds": (
                safe_integer_endpoint if span == "AVAILABLE" else None
            ),
            "observation_method": method,
            "observation_started_offset_nanoseconds": (
                safe_integer_endpoint if span == "AVAILABLE" else None
            ),
            "source_errno_name": (
                errno_name
                if error_form in {"OS_PLUS_NON_OS_DETAIL", "OS_ONLY"}
                else None
            ),
            "source_errno_number": (
                safe_integer_endpoint
                if error_form in {"OS_PLUS_NON_OS_DETAIL", "OS_ONLY"}
                else None
            ),
            "source_error_class": (
                error_class
                if error_form in {"OS_PLUS_NON_OS_DETAIL", "NON_OS"}
                else None
            ),
            "source_error_detail_sha256": None,
            "source_failure_phase": phase,
            "unavailable_reason": reason,
            "value": None,
        }
    )
    field["source_error_detail_sha256"] = _source_error_digest(
        field,
        canonicalization,
        schema_version,
    )
    _record_identity(field, field_type, canonicalization, schema_version)
    return (
        {
            "branch_kind": "STATUS_REASON",
            "censoring": None,
            "error_form": error_form,
            "method": method,
            "phase": phase,
            "reason": reason,
        },
        field,
    )


def _proposals(
    frozen: dict[str, Any],
    descriptor: dict[str, Any],
    context: dict[str, Any],
    registry_id: str,
    reason_policies: dict[str, Any],
    constraints: dict[str, Any],
    shapes: dict[str, Any],
    vocabularies: dict[str, Any],
    field_type: dict[str, Any],
    canonicalization: str,
    schema_version: str,
    safe_integer_endpoint: int,
    errno_name: str,
    error_class: str,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    result: list[tuple[dict[str, Any], dict[str, Any]]] = []
    methods = _methods(descriptor, context)
    for method in methods:
        result.append(
            _available_proposal(
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
                safe_integer_endpoint,
                censoring=None,
            )
        )
        if (
            descriptor["censoring_allowed"]
            and descriptor["value_kind"] == "DURATION_BOUND"
        ):
            for censoring in ("INTERVAL", "LEFT", "RIGHT"):
                result.append(
                    _available_proposal(
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
                        safe_integer_endpoint,
                        censoring=censoring,
                    )
                )

    operation_applies = (
        context["operation_kind"] in descriptor["applicable_operation_kinds"]
    )
    for reason in descriptor["allowed_status_reasons"]:
        if reason in PLACEHOLDER_FIELD_REASON.values():
            continue
        if reason == "INSTRUMENTATION_DISABLED":
            continue
        if operation_applies == (reason == "NOT_APPLICABLE_TO_OPERATION"):
            continue
        policy = reason_policies[reason]
        for attempt_policy in policy["attempt_state_error_forms"]:
            selected_methods = (
                methods
                if attempt_policy["attempt_state"] == "ATTEMPTED"
                else ["NOT_ATTEMPTED"]
            )
            for method, phase, error_form in product(
                selected_methods,
                attempt_policy["permitted_failure_phases"],
                _error_variants(attempt_policy["permitted_error_forms"]),
            ):
                result.append(
                    _reason_proposal(
                        frozen,
                        context,
                        registry_id,
                        method,
                        reason,
                        policy,
                        attempt_policy,
                        phase,
                        error_form,
                        errno_name,
                        error_class,
                        field_type,
                        canonicalization,
                        schema_version,
                        safe_integer_endpoint,
                    )
                )
    _require(bool(result), f"no witness proposal: {descriptor['field_id']}")
    unique: dict[bytes, tuple[dict[str, Any], dict[str, Any]]] = {}
    for item in result:
        unique.setdefault(_canonical_bytes(item[1]), item)
    return list(unique.values())


def _a1_variants(
    candidates: list[tuple[dict[str, Any], dict[str, Any]]],
    field_id: str,
    field_type: dict[str, Any],
    canonicalization: str,
    schema_version: str,
    vocabularies: dict[str, Any],
    maximum_items: int,
    safe_integer_endpoint: int,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    available = [item for item in candidates if item[1]["availability"] == "AVAILABLE"]
    _require(bool(available), f"A1 available proposal absent: {field_id}")
    template_branch, template = max(
        available,
        key=lambda item: (len(_canonical_bytes(item[1])), _canonical_bytes(item[1])),
    )
    extended = list(candidates)
    longest_kind = _longest(vocabularies["RAW_V8_A1_COMMAND_KIND"]["members"])
    for cardinality in range(maximum_items + 1):
        field = copy.deepcopy(template)
        if field_id == A1_FIELDS[0]:
            field["value"] = {"kind": "UINT", "value": cardinality}
        elif field_id == A1_FIELDS[1]:
            field["value"] = {
                "kind": "TEXT_LIST",
                "values": [longest_kind] * cardinality,
            }
        else:
            field["value"] = {
                "kind": "UINT_LIST",
                "values": list(
                    range(
                        safe_integer_endpoint - cardinality + 1,
                        safe_integer_endpoint + 1,
                    )
                ),
            }
        _record_identity(field, field_type, canonicalization, schema_version)
        branch = dict(template_branch)
        branch["branch_kind"] = "A1_CARDINALITY_COMPATIBLE_AVAILABLE_VALUE"
        branch["a1_cardinality"] = cardinality
        extended.append((branch, field))
    unique: dict[bytes, tuple[dict[str, Any], dict[str, Any]]] = {}
    for item in extended:
        unique.setdefault(_canonical_bytes(item[1]), item)
    return list(unique.values())


def _a1_compatible(items: tuple[tuple[dict[str, Any], dict[str, Any]], ...]) -> bool:
    fields = [item[1] for item in items]
    if any(field["availability"] != "AVAILABLE" for field in fields):
        return True
    by_id = {field["field_id"]: field for field in fields}
    count = by_id[A1_FIELDS[0]]["value"]["value"]
    kinds = by_id[A1_FIELDS[1]]["value"]["values"]
    sequences = by_id[A1_FIELDS[2]]["value"]["values"]
    return count == len(kinds) == len(sequences) and all(
        left < right for left, right in zip(sequences, sequences[1:])
    )


def _selection_key(item: tuple[dict[str, Any], dict[str, Any]]) -> tuple[Any, ...]:
    branch, field = item
    raw = _canonical_bytes(field)
    return len(raw), raw, _canonical_bytes(branch)


def _candidate_context_legal(
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
        method_rows = [
            row
            for row in descriptor["observation_method_role_pairs"]
            if row["observation_method"] == field["observation_method"]
        ]
        if (
            len(method_rows) != 1
            or context["observation_role"] not in method_rows[0]["allowed_roles"]
        ):
            return False
        if (
            context["observation_role"] == "STABLE_CHECKPOINT"
            and context["checkpoint_marker_kind"]
            not in descriptor["allowed_checkpoint_marker_kinds"]
        ):
            return False
    if field["adapter_span_status"] == "AVAILABLE":
        observer_span = context["observer_clock_span"]
        offsets = (
            observer_span["started_offset_nanoseconds"],
            field["observation_started_offset_nanoseconds"],
            field["observation_completed_offset_nanoseconds"],
            observer_span["completed_offset_nanoseconds"],
        )
        return (
            observer_span["span_status"] == "AVAILABLE"
            and all(type(value) is int for value in offsets)
            and offsets[0] <= offsets[1] <= offsets[2] <= offsets[3]
        )
    return True


def _candidate_sets_for_context(
    frozen_fields: list[dict[str, Any]],
    descriptors: list[dict[str, Any]],
    context: dict[str, Any],
    registry_id: str,
    reason_policies: dict[str, Any],
    constraints: dict[str, Any],
    shapes: dict[str, Any],
    vocabularies: dict[str, Any],
    field_type: dict[str, Any],
    canonicalization: str,
    schema_version: str,
    safe_integer_endpoint: int,
    errno_name: str,
    error_class: str,
) -> dict[str, list[tuple[dict[str, Any], dict[str, Any]]]]:
    result: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    for ordinal, (frozen, descriptor) in enumerate(
        zip(frozen_fields, descriptors, strict=True)
    ):
        _require(frozen["field_id"] == descriptor["field_id"], "field order differs")
        candidates = _proposals(
            frozen,
            descriptor,
            context,
            registry_id,
            reason_policies,
            constraints,
            shapes,
            vocabularies,
            field_type,
            canonicalization,
            schema_version,
            safe_integer_endpoint,
            errno_name,
            error_class,
        )
        if descriptor["field_id"] in A1_FIELDS and any(
            item[1]["availability"] == "AVAILABLE" for item in candidates
        ):
            candidates = _a1_variants(
                candidates,
                descriptor["field_id"],
                field_type,
                canonicalization,
                schema_version,
                vocabularies,
                shapes["L_A1_FIFO_4"]["maximum_items"],
                safe_integer_endpoint,
            )
        legal = [
            item
            for item in candidates
            if _candidate_context_legal(
                item[1], descriptor, context, ordinal, registry_id
            )
        ]
        _require(bool(legal), f"no context-legal proposal: {descriptor['field_id']}")
        result[descriptor["field_id"]] = legal
    return result


def _select_candidate_fields(
    candidates_by_field: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]],
    descriptors: list[dict[str, Any]],
) -> tuple[
    dict[str, tuple[dict[str, Any], dict[str, Any]]],
    list[tuple[tuple[dict[str, Any], dict[str, Any]], ...]],
]:
    a1_combinations = [
        combination
        for combination in product(
            *(candidates_by_field[field_id] for field_id in A1_FIELDS)
        )
        if _a1_compatible(combination)
    ]
    _require(bool(a1_combinations), "A1 witness product is empty")
    a1_selection = max(
        a1_combinations,
        key=lambda combination: (
            sum(len(_canonical_bytes(item[1])) for item in combination),
            _canonical_bytes([item[1] for item in combination]),
        ),
    )
    selected = dict(zip(A1_FIELDS, a1_selection, strict=True))
    for descriptor in descriptors:
        field_id = descriptor["field_id"]
        if field_id not in selected:
            selected[field_id] = max(candidates_by_field[field_id], key=_selection_key)
    return selected, a1_combinations


def _rebind_observation(
    source: dict[str, Any],
    root: dict[str, Any],
    types: dict[str, Any],
    canonicalization: str,
    schema_version: str,
    registry_id: str,
) -> dict[str, Any]:
    observation = copy.deepcopy(source)
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


def _outer_context(
    template: dict[str, Any],
    role: str,
    root: dict[str, Any],
    context_type: dict[str, Any],
    canonicalization: str,
    schema_version: str,
    registry_id: str,
) -> dict[str, Any]:
    context = copy.deepcopy(template)
    context.update(
        {
            "attempt_id": root["attempt_id"],
            "candidate_id": root["candidate_id"],
            "instrumentation_mode": root["instrumentation_mode"],
            "observation_role": role,
            "operation_kind": root["operation_kind"],
            "target_field_registry_id": registry_id,
        }
    )
    for member in (
        "checkpoint_binding_status",
        "checkpoint_binding_unavailable_reason",
        "checkpoint_marker_kind",
        "checkpoint_selector_entry_id",
        "checkpoint_selector_position",
        "expected_checkpoint_marker_kind",
        "expected_occurrence_index_within_kind",
        "full_checkpoint_selector_id",
        "marker_ordinal",
    ):
        context[member] = None
    _record_identity(
        context,
        context_type,
        canonicalization,
        schema_version,
    )
    return context


def _observation_from_context_and_fields(
    template: dict[str, Any],
    context: dict[str, Any],
    fields: list[dict[str, Any]],
    observation_type: dict[str, Any],
    canonicalization: str,
    schema_version: str,
) -> dict[str, Any]:
    observation = copy.deepcopy(template)
    observation["observation_context"] = context
    observation["observation_context_id"] = context["observation_context_id"]
    observation["field_observations"] = fields
    _record_identity(
        observation,
        observation_type,
        canonicalization,
        schema_version,
    )
    return observation


def _checkpoint_placeholder(
    template: dict[str, Any],
    root: dict[str, Any],
    selector: dict[str, Any],
    entry: dict[str, Any],
    types: dict[str, Any],
    canonicalization: str,
    schema_version: str,
    registry_id: str,
) -> dict[str, Any]:
    observation = copy.deepcopy(template)
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
    return _rebind_observation(
        observation,
        root,
        types,
        canonicalization,
        schema_version,
        registry_id,
    )


def _record_input(
    runtime_module: ModuleType,
    binding_name: str,
    type_name: str,
    value: dict[str, Any],
) -> Any:
    return runtime_module.ApplicationRecordInput(
        binding_name=binding_name,
        declared=runtime_module.TypedValue(value=value, type_name=type_name),
    )


def _sequence_input(
    runtime_module: ModuleType,
    binding_name: str,
    type_name: str,
    values: list[dict[str, Any]],
) -> Any:
    return runtime_module.ApplicationSequenceInput(
        binding_name=binding_name,
        ordered_records=tuple(
            runtime_module.TypedValue(value=value, type_name=type_name)
            for value in values
        ),
    )


def _receipt(
    evidence: Any, schedule_position: int, ordinal: int | None
) -> dict[str, Any]:
    payload = dataclasses.asdict(evidence)
    _require(
        payload["accepted"] is True,
        (
            "P1 application rejected retained bytes: "
            f"schedule_position={schedule_position}, invocation_ordinal={ordinal}, "
            f"coordinate={payload['result_coordinate']}"
        ),
    )
    return {
        "application_schedule_position": schedule_position,
        "invocation_ordinal": ordinal,
        "application_name": payload["application_name"],
        "rule_application_id": payload["rule_application_id"],
        "rule_id": payload["rule_id"],
        "charged_rule_evaluations": payload["charged_rule_evaluations"],
        "completed_rule_evaluations": payload["completed_rule_evaluations"],
        "total_expression_nodes": payload["total_expression_nodes"],
        "direct_expression_nodes": sum(
            row["direct_expression_nodes"]
            for row in payload["ordered_rule_step_evidence"]
        ),
        "evidence_canonical_sha256": _sha256(_canonical_bytes(payload)),
    }


def _execute_schedule(
    runtime_module: ModuleType,
    runtime: Any,
    root: dict[str, Any],
    observations: list[dict[str, Any]],
    selector: dict[str, Any],
    marker_contract: dict[str, Any],
    target_registry: dict[str, Any],
) -> list[dict[str, Any]]:
    receipts: list[dict[str, Any]] = []
    selector_evidence = runtime.evaluate_application(
        APPLICATION_ORDER[0],
        (
            _record_input(
                runtime_module,
                "selector",
                "CheckpointSelectorV1",
                selector,
            ),
            _record_input(
                runtime_module,
                "marker_contract",
                "MarkerContractV1",
                marker_contract,
            ),
        ),
    )
    receipts.append(_receipt(selector_evidence, 1, None))

    for ordinal, observation in enumerate(observations):
        evidence = runtime.evaluate_application(
            APPLICATION_ORDER[1],
            (
                _record_input(
                    runtime_module,
                    "observation",
                    "TargetObservationV2",
                    observation,
                ),
                _record_input(
                    runtime_module,
                    "target_registry",
                    "TargetFieldRegistryV1",
                    target_registry,
                ),
            ),
        )
        receipts.append(_receipt(evidence, 2, ordinal))

    for ordinal, observation in enumerate(observations):
        evidence = runtime.evaluate_application(
            APPLICATION_ORDER[2],
            (
                _record_input(
                    runtime_module,
                    "observation",
                    "TargetObservationV2",
                    observation,
                ),
                _record_input(
                    runtime_module,
                    "target_registry",
                    "TargetFieldRegistryV1",
                    target_registry,
                ),
            ),
        )
        receipts.append(_receipt(evidence, 3, ordinal))

    membership_evidence = runtime.evaluate_application(
        APPLICATION_ORDER[3],
        (_record_input(runtime_module, "root", "TargetObservationRootV2", root),),
        (
            _sequence_input(
                runtime_module,
                "observation",
                "TargetObservationV2",
                observations,
            ),
        ),
    )
    receipts.append(_receipt(membership_evidence, 4, None))
    lifecycle_evidence = runtime.evaluate_application(
        APPLICATION_ORDER[4],
        (_record_input(runtime_module, "root", "TargetObservationRootV2", root),),
        (
            _sequence_input(
                runtime_module,
                "observations",
                "TargetObservationV2",
                observations,
            ),
            _sequence_input(
                runtime_module,
                "selector",
                "CheckpointSelectorV1",
                [selector],
            ),
        ),
    )
    receipts.append(_receipt(lifecycle_evidence, 5, None))
    return receipts


def construct(repository_root: pathlib.Path | str) -> dict[str, Any]:
    root_path = pathlib.Path(repository_root)
    seed, inventory, registry, literal, ledger = _load_authorities(root_path)
    _require(
        inventory["external_schema_registry_v2"] == registry, "registry join differs"
    )
    _require(
        literal["target_field_registry"] == inventory["target_field_registry"],
        "target registry join differs",
    )
    canonicalization = seed["canonicalization_version"]
    schema_version = seed["measurement_schema_version"]
    recipe = seed["logical_plan_recipe_catalog"]
    plan = recipe["ordered_logical_count_plan_records"][CASE_POSITION - 1]
    program = next(
        row
        for row in recipe["ordered_profile_conditioning_program_records"]
        if row["profile_conditioning_program_id"] == PROGRAM_ID
    )
    _require(
        plan["case_position"] == CASE_POSITION
        and plan["logical_count_plan_id"] == PLAN_ID
        and plan["profile_conditioning_program_id"] == PROGRAM_ID
        and program["profile_position"] == PROFILE_POSITION
        and program["maximum_constraint_scope_profile_id"] == PROFILE_ID,
        "case/profile binding differs",
    )
    schedule = program["application_schedule_operation"]
    instructions = schedule["ordered_schedule_segment_records"][0][
        "ordered_application_instruction_records"
    ]
    _require(
        [row["application_name"] for row in instructions] == list(APPLICATION_ORDER)
        and [row["application_invocation_count_per_scope_case"] for row in instructions]
        == [1, 67, 67, 1, 1],
        "P1 application schedule differs",
    )
    ledger_applications = {
        row["application_name"]: row
        for row in ledger["ordered_rule_application_descriptors"]
    }
    _require(
        all(
            ledger_applications[row["application_name"]]["rule_application_id"]
            == row["rule_application_id"]
            for row in instructions
        ),
        "application ledger join differs",
    )

    types = _index(
        registry["ordered_external_type_descriptors"], "type_name", 52, "type"
    )
    schemas = _index(registry["value_schema_catalog"], "value_schema_id", 236, "schema")
    languages = _index(
        registry["text_language_catalog"], "text_language_id", 103, "language"
    )
    dfas = _index(registry["ascii_dfa_catalog"], "ascii_dfa_id", 9, "DFA")
    target_registry = inventory["target_field_registry"]
    descriptors = target_registry["descriptors"]
    _require(len(descriptors) == FIELD_COUNT, "target field count differs")
    constraints = _index(
        target_registry["ordered_value_constraint_definitions"],
        "value_constraint_id",
        17,
        "value constraint",
    )
    shapes = _index(
        target_registry["ordered_value_shape_definitions"],
        "value_shape_id",
        6,
        "value shape",
    )
    vocabularies = _index(
        target_registry["ordered_vocabulary_definitions"],
        "vocabulary_id",
        25,
        "vocabulary",
    )
    reason_policies = _index(
        target_registry["status_reason_policy_definition"]["reason_rules"],
        "reason",
        26,
        "status reason",
    )
    safe_integer_endpoint = constraints["UINT_SAFE_IJSON"]["integer_maximum"]
    field_type = types["TargetFieldObservationV1"]
    field_member_schemas = {
        row["member_name"]: schemas[row["value_schema_id"]]
        for row in field_type["record_member_descriptors"]
    }
    errno_language = languages[
        field_member_schemas["source_errno_name"]["text_language_id"]
    ]
    error_language = languages[
        field_member_schemas["source_error_class"]["text_language_id"]
    ]
    errno_name = _longest_dfa_word(dfas[errno_language["ascii_dfa_id"]])
    error_class = _longest_dfa_word(dfas[error_language["ascii_dfa_id"]])

    fixtures = inventory["fixture_records"]["target_observation_v2_fixtures"]
    maximum_root = copy.deepcopy(fixtures["maximum_selector_target_observation_root"])
    selector = next(
        row["selector"]
        for row in inventory["checkpoint_selector_catalog"]
        if row["selector"]["checkpoint_selector_id"]
        == maximum_root["full_checkpoint_selector_id"]
    )
    _require(selector["selector_length"] == 64, "selector length differs")
    selected_entry = selector["ordered_entries"][MEASURED_SEQUENCE_ORDINAL - 1]
    exact_fixture = fixtures["checkpoint_exact_marker_observation"]
    exact_context = _context(
        exact_fixture["observation_context"],
        maximum_root,
        selector,
        selected_entry,
        target_registry["target_field_registry_id"],
        types["TargetObservationContextV2"],
        canonicalization,
        schema_version,
        safe_integer_endpoint,
    )

    candidates_by_field = _candidate_sets_for_context(
        exact_fixture["field_observations"],
        descriptors,
        exact_context,
        target_registry["target_field_registry_id"],
        reason_policies,
        constraints,
        shapes,
        vocabularies,
        field_type,
        canonicalization,
        schema_version,
        safe_integer_endpoint,
        errno_name,
        error_class,
    )
    selected, a1_combinations = _select_candidate_fields(
        candidates_by_field, descriptors
    )

    ordered_fields = [selected[row["field_id"]][1] for row in descriptors]
    exact_observation = copy.deepcopy(exact_fixture)
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

    preceding = [
        _checkpoint_placeholder(
            fixtures["checkpoint_placeholder_observations"][
                "TARGET_BOUNDARY_NOT_REACHED"
            ],
            maximum_root,
            selector,
            entry,
            types,
            canonicalization,
            schema_version,
            target_registry["target_field_registry_id"],
        )
        for entry in selector["ordered_entries"][: MEASURED_SEQUENCE_ORDINAL - 1]
    ]
    outer_observations: dict[str, dict[str, Any]] = {}
    outer_proposal_counts: dict[str, int] = {}
    for role in ("BEFORE_OPERATION", "AFTER_OPERATION", "OPERATION_AGGREGATE"):
        context = _outer_context(
            exact_fixture["observation_context"],
            role,
            maximum_root,
            types["TargetObservationContextV2"],
            canonicalization,
            schema_version,
            target_registry["target_field_registry_id"],
        )
        role_candidates = _candidate_sets_for_context(
            exact_fixture["field_observations"],
            descriptors,
            context,
            target_registry["target_field_registry_id"],
            reason_policies,
            constraints,
            shapes,
            vocabularies,
            field_type,
            canonicalization,
            schema_version,
            safe_integer_endpoint,
            errno_name,
            error_class,
        )
        role_selected, _role_a1_combinations = _select_candidate_fields(
            role_candidates, descriptors
        )
        outer_proposal_counts[role] = sum(
            len(rows) for rows in role_candidates.values()
        )
        outer_observations[role] = _observation_from_context_and_fields(
            exact_fixture,
            context,
            [role_selected[row["field_id"]][1] for row in descriptors],
            types["TargetObservationV2"],
            canonicalization,
            schema_version,
        )
    observations = [
        outer_observations["BEFORE_OPERATION"],
        *preceding,
        exact_observation,
        outer_observations["AFTER_OPERATION"],
        outer_observations["OPERATION_AGGREGATE"],
    ]
    _require(len(observations) == 67, "retained observation count differs")
    root = copy.deepcopy(maximum_root)
    root["ordered_observation_ids"] = [row["observation_id"] for row in observations]
    _record_identity(
        root,
        types["TargetObservationRootV2"],
        canonicalization,
        schema_version,
    )

    runtime_module = _load_runtime(root_path)
    runtime = runtime_module.ExternalSchemaV2Runtime.load(root_path)
    receipts = _execute_schedule(
        runtime_module,
        runtime,
        root,
        observations,
        selector,
        inventory["marker_contract"],
        target_registry,
    )
    _require(
        len(receipts) == schedule["application_invocation_count"] == 137,
        "P1 invocation count differs",
    )
    charged = sum(row["charged_rule_evaluations"] for row in receipts)
    direct_nodes = sum(row["direct_expression_nodes"] for row in receipts)
    _require(
        charged == schedule["cross_rule_evaluation_count"]
        and direct_nodes == schedule["direct_cross_expression_node_count"],
        "P1 schedule work differs",
    )

    measured_raw = _canonical_bytes(exact_observation)
    selected_field_records = []
    for position, descriptor in enumerate(descriptors, 1):
        branch, field = selected[descriptor["field_id"]]
        field_raw = _canonical_bytes(field)
        selected_field_records.append(
            {
                "field_position": position,
                "field_id": descriptor["field_id"],
                "proposal_count": len(candidates_by_field[descriptor["field_id"]]),
                "selected_branch": branch,
                "selected_canonical_octets": len(field_raw),
                "selected_canonical_sha256": _sha256(field_raw),
                "selected_field_observation_id": field["field_observation_id"],
            }
        )

    certificate: dict[str, Any] = {
        "attainer_certificate_version": ATTAINER_CERTIFICATE_VERSION,
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
        "construction_protocol": {
            "construction_protocol_version": CONSTRUCTION_PROTOCOL_VERSION,
            "candidate_policy": (
                "DERIVE_CLOSED_SCHEMA_ENDPOINTS_AND_ALL_STATUS_METHOD_REASON_"
                "ERROR_BRANCHES_THEN_SELECT_LONGEST_CANONICAL_LEGAL_SHAPE"
            ),
            "a1_policy": "EXHAUSTIVE_THREE_FIELD_CARTESIAN_LEGALITY_BEFORE_SELECTION",
            "runtime_role": "PINNED_P1_EXECUTION_AUTHORITY_NOT_OPTIMIZATION_SOURCE",
            "external_upper_channel_imported": False,
            "precomputed_witness_imported": False,
            "total_field_proposal_count": sum(
                len(rows) for rows in candidates_by_field.values()
            ),
            "outer_role_total_field_proposal_count": outer_proposal_counts,
            "a1_cartesian_tuple_count": (
                len(candidates_by_field[A1_FIELDS[0]])
                * len(candidates_by_field[A1_FIELDS[1]])
                * len(candidates_by_field[A1_FIELDS[2]])
            ),
            "a1_legal_tuple_count": len(a1_combinations),
        },
        "schedule_authority": {
            "application_schedule_operation_position": schedule["operation_position"],
            "application_invocation_count": schedule["application_invocation_count"],
            "cross_rule_evaluation_count": schedule["cross_rule_evaluation_count"],
            "direct_cross_expression_node_count": schedule[
                "direct_cross_expression_node_count"
            ],
            "ordered_application_instruction_sha256": _sha256(
                _canonical_bytes(instructions)
            ),
        },
        "ordered_selected_field_witness_records": selected_field_records,
        "retained_witness_context": {
            "checkpoint_selector": selector,
            "target_observation_root": root,
            "ordered_observations": observations,
        },
        "p1_execution_certificate": {
            "ordered_application_execution_receipts": receipts,
            "application_invocation_count": len(receipts),
            "charged_rule_evaluation_count": charged,
            "completed_rule_evaluation_count": sum(
                row["completed_rule_evaluations"] for row in receipts
            ),
            "direct_expression_node_count": direct_nodes,
            "all_applications_accepted": True,
            "receipt_vector_sha256": _sha256(_canonical_bytes(receipts)),
        },
        "measured_attainer": {
            "observation_sequence_position": MEASURED_SEQUENCE_ORDINAL + 1,
            "measured_sequence_ordinal": MEASURED_SEQUENCE_ORDINAL,
            "observation_id": exact_observation["observation_id"],
            "canonical_octets": len(measured_raw),
            "canonical_sha256": _sha256(measured_raw),
            "root_id": root["target_observation_root_sha256"],
            "root_canonical_sha256": _sha256(_canonical_bytes(root)),
            "ordered_observation_id_vector_sha256": _sha256(
                _canonical_bytes(root["ordered_observation_ids"])
            ),
        },
        "p1_legal": True,
        "legal_attainer_constructed": True,
        "exactness_claimed": False,
        "acceptance_state": "LEGAL_ATTAINER_CONSTRUCTED_EXACTNESS_JOIN_PENDING",
        "correction_subgate": "A4-P6-C435-C2",
        "next_subgate": "A4-P6-C435-C3",
    }
    certificate["case435_attainer_certificate_id"] = _sha256(
        _canonical_bytes(
            {"domain": ATTAINER_CERTIFICATE_DOMAIN, "payload": certificate}
        )
    )
    return certificate


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) > 1:
        raise SystemExit("usage: construct...py [repository-root]")
    root = (
        pathlib.Path(argv[0]).resolve()
        if argv
        else pathlib.Path(__file__).resolve().parents[2]
    )
    try:
        certificate = construct(root)
    except (AttainerError, OSError, KeyError, TypeError, ValueError) as error:
        sys.stderr.write(f"CASE435_ATTAINER_CONSTRUCTION_REJECT: {error}\n")
        return 1
    sys.stdout.buffer.write(_canonical_bytes(certificate) + b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

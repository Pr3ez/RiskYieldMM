#!/usr/bin/env python3
"""Generate or validate the isolated Raw-V8 Step-2 typed-rule ledger.

This verifier is intentionally standard-library-only.  It consumes pinned,
bounded JSON authorities and never imports production code or a runtime schema
implementation.  Its output remains a component ledger until the complete
External Schema V2 registry is assembled.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import datetime as dt
import hashlib
import json
import os
import re
import stat
import sys
import unicodedata
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

CANONICALIZATION_VERSION: Final = "riskyieldmm_canonical_json_v1"
MEASUREMENT_SCHEMA_VERSION: Final = "riskyieldmm_physical_transport_a2m_raw_v49f_v8"
COMPONENT_STATUS: Final = "RULE_APPLICATION_ONLY_NOT_FULL_REGISTRY"
LEDGER_VERSION: Final = (
    "riskyieldmm.raw_v8_step2_external_schema_v2.rule_application_ledger.v1"
)
RULE_VERSION: Final = "riskyieldmm_raw_v8_step2_typed_rule_v2"

TOPOLOGY_RELATIVE_PATH: Final = (
    "scripts/tests/raw_v8_step2_external_schema_v2_topology_ledger_v49f.json"
)
SCALAR_RELATIVE_PATH: Final = (
    "scripts/tests/raw_v8_step2_external_schema_v2_scalar_path_ledger_v49f.json"
)
FROZEN_LITERAL_RELATIVE_PATH: Final = (
    "scripts/tests/raw_v8_step2_external_schema_v2_rule_literal_authority_v49f.json"
)
LEDGER_RELATIVE_PATH: Final = (
    "scripts/tests/raw_v8_step2_external_schema_v2_rule_application_ledger_v49f.json"
)

TOPOLOGY_SHA256: Final = (
    "17b6355afcc23438efad97967180fb7e6292b7dd3d72d8b91a0320bfb9696778"
)
SCALAR_SHA256: Final = (
    "b0b8783c8783012d5dc966578c82f348c902f6bf0d44583a4a7d5be6a16079aa"
)
FROZEN_LITERAL_SHA256: Final = (
    "aba3461059367904734e2eb9ae404787b9aab5ed4c3fbcd292925a364926cce2"
)
LEDGER_SHA256: Final = (
    "979d7affe2d745d46f5977d9d69a4d1efa473f95c1a374737bf34181d9dac282"
)
LEDGER_OCTETS: Final = 1_141_506

MAXIMUM_TOPOLOGY_OCTETS: Final = 1_048_576
MAXIMUM_SCALAR_OCTETS: Final = 1_048_576
MAXIMUM_FROZEN_LITERAL_OCTETS: Final = 1_048_576
MAXIMUM_LEDGER_OCTETS: Final = 8_388_608
MAXIMUM_JSON_DEPTH: Final = 64
MAXIMUM_EXPRESSION_NODES: Final = 4_096
SAFE_UINT_MAX: Final = 9_007_199_254_740_991

VALUE_SCHEMA_DOMAIN: Final = "RiskYieldMMA2MStep2ValueSchemaV2V4_9F_RawV8"
RULE_DOMAIN: Final = "RiskYieldMMA2MStep2CrossFieldRuleDescriptorV2V4_9F_RawV8"
RESOLVER_DOMAIN: Final = "RiskYieldMMA2MStep2FixedPositionResolverProfileV2V4_9F_RawV8"
APPLICATION_DOMAIN: Final = "RiskYieldMMA2MStep2RuleApplicationDescriptorV2V4_9F_RawV8"
COMPONENT_DOMAIN: Final = "RiskYieldMMA2MStep2RuleApplicationComponentV1V4_9F_RawV8"

BOOLEAN_SCHEMA_ID: Final = (
    "e35ba28ae2abdcdefdd9d56862b866d0cf72645f5c8d0bdf8c86b156c5dddb97"
)

INTRINSIC_TYPE_POSITIONS: Final = (
    1,
    2,
    3,
    4,
    6,
    8,
    9,
    10,
    11,
    15,
    16,
    17,
    18,
    19,
    20,
    21,
    22,
    23,
    24,
    25,
    26,
    27,
    28,
    29,
    30,
    33,
    34,
    36,
    38,
    39,
    43,
    44,
    48,
    49,
)
NO_INTRINSIC_TYPE_POSITIONS: Final = (
    5,
    7,
    12,
    13,
    14,
    31,
    32,
    35,
    37,
    40,
    41,
    42,
    45,
    46,
    47,
)

CROSS_RULE_IDS: Final = (
    "RULE/CROSS/COUNTER_SNAPSHOT_SCHEMA_V1",
    "RULE/CROSS/FIELD_OBSERVATION_FROZEN_REGISTRY_V1",
    "RULE/CROSS/OPERATION_RESULT_SIGNED_SPEC_V1",
    "RULE/CROSS/SELECTOR_MARKER_CONTRACT_V1",
    "RULE/CROSS/V2_OBSERVATION_AGGREGATE_REGISTRY_V1",
    "RULE/CROSS/V2_OBSERVATION_FIELD_REGISTRY_V1",
    "RULE/CROSS/V2_ROOT_OBSERVATION_MEMBERSHIP_V1",
    "RULE/CROSS/V2_ROOT_SELECTOR_LIFECYCLE_V1",
)

OPERATOR_ARITY: Final = {
    "INPUT_PATH": 0,
    "LITERAL": 0,
    "IS_NULL": 1,
    "NOT": 1,
    "AND": 2,
    "OR": 2,
    "IMPLIES": 2,
    "EQ": 2,
    "NE": 2,
    "LT": 2,
    "LE": 2,
    "GT": 2,
    "GE": 2,
    "PRESENT_EQ": 2,
    "PRESENT_LE": 2,
    "SAFE_ADD": 2,
    "SAFE_MULTIPLY": 2,
    "SAFE_FLOOR_DIVIDE": 2,
    "SAFE_CEIL_DIVIDE": 2,
    "ARRAY_LENGTH": 1,
    "ARRAY_UNIQUE": 1,
    "ARRAY_STRICT_ASCENDING": 1,
    "ARRAY_POSITIONAL_EQUAL": 2,
    "ARRAY_PROJECT_REQUIRED_MEMBER": 1,
    "ARRAY_CONTAINS": 2,
    "ARRAY_FIND_UNIQUE_OBJECT_BY_MEMBER": 2,
    "OBJECT_MEMBER": 1,
    "TIMESTAMP_TO_EPOCH_MICROSECONDS": 1,
    "UINT128_PARSE": 1,
    "SAFE_UINT_TO_INTERNAL_UINT128": 1,
    "UINT128_ADD": 2,
    "UINT128_MULTIPLY": 2,
    "BASE64_DECODE": 1,
    "BASE64_ARRAY_DECODE_CONCAT": 2,
    "INTERNAL_BYTES_LENGTH": 1,
    "SHA256_BYTES": 1,
    "RAW_INGRESS_BATCH_ID_RECOMPUTES": 2,
    "RFC6455_CLOSE_PAYLOAD_VALID": 2,
    "FIELD_LAYER_EQUALS_UPPERCASE_FIELD_PREFIX": 2,
    "SEMANTIC_ID_RECOMPUTES": 2,
    "CANONICAL_BYTES_SATISFY_BOUND": 1,
    "CHECKPOINT_SELECTOR_INTRINSIC_VALID": 1,
    "CHECKPOINT_SELECTOR_MARKER_CONTRACT_ADMITTED": 2,
    "FIELD_OBSERVATION_INTRINSIC_VALID": 1,
    "FIELD_OBSERVATION_SATISFIES_DESCRIPTOR_POLICY": 3,
    "V2_FIELD_OBSERVATION_CONTEXT_VALID": 5,
    "SOURCE_ERROR_DETAIL_ID_RECOMPUTES_FROM_FIELD": 1,
    "TARGET_VALUE_SATISFIES_DESCRIPTOR": 3,
    "A1_FIFO_FIELDS_VALID": 2,
    "BITMAP_NULLABILITY_MATCHES": 2,
    "V2_ROOT_SEQUENCE_SELECTOR_VALID": 3,
    "OPERATION_RESULT_MATCHES_SIGNED_SPEC": 2,
}

VALUE_SCHEMA_KEYS: Final = {
    "schema_kind",
    "nullable",
    "boolean_literal",
    "integer_minimum",
    "integer_maximum",
    "text_language_id",
    "array_minimum_items",
    "array_maximum_items",
    "array_item_value_schema_id",
    "referenced_type_name",
    "value_schema_id",
}
RULE_KEYS: Final = {
    "rule_id",
    "rule_version",
    "rule_scope",
    "ordered_rule_input_bindings",
    "maximum_expression_nodes",
    "root_expression_position",
    "ordered_expression_nodes",
    "step2_cross_field_rule_descriptor_id",
}
RULE_BINDING_KEYS: Final = {
    "binding_name",
    "binding_kind",
    "expected_type_name",
    "expected_value_schema_id",
}
EXPRESSION_NODE_KEYS: Final = {
    "expression_position",
    "operator",
    "result_type_kind",
    "result_value_schema_id",
    "ordered_operand_positions",
    "input_binding_name",
    "typed_member_path",
    "literal_value_schema_id",
    "literal_value",
}
ATTACHMENT_KEYS: Final = {
    "concrete_type_position",
    "type_name",
    "ordered_intrinsic_rule_ids",
}
DEPENDENCY_EDGE_KEYS: Final = {
    "predecessor_rule_id",
    "successor_rule_id",
}
RESOLVER_KEYS: Final = {
    "profile_name",
    "source_root_type_name",
    "ordered_source_identity_path_descriptors",
    "resolved_item_type_name",
    "minimum_items",
    "maximum_items",
    "resolution_semantics",
    "fixed_position_resolver_profile_id",
}
RESOLVER_PATH_KEYS: Final = {
    "path_position",
    "typed_member_path",
    "result_kind",
    "null_semantics",
}
APPLICATION_KEYS: Final = {
    "application_name",
    "rule_id",
    "application_kind",
    "ordered_root_input_bindings",
    "ordered_sequence_input_bindings",
    "iteration_ordinal_binding_name",
    "maximum_rule_evaluations",
    "requires_equal_cardinality",
    "evaluation_order",
    "rule_application_id",
}
ROOT_BINDING_KEYS: Final = {
    "binding_name",
    "tuple_position",
    "expected_type_name",
}
SEQUENCE_BINDING_KEYS: Final = {
    "binding_name",
    "binding_mode",
    "source_kind",
    "source_root_binding_name",
    "embedded_array_typed_member_path",
    "fixed_position_resolver_profile_id",
    "expected_item_type_name",
}
COMPONENT_KEYS: Final = {
    "canonicalization_version",
    "measurement_schema_version",
    "component_status",
    "rule_application_ledger_version",
    "dependency_sha256",
    "concrete_attachment_count",
    "intrinsic_rule_count",
    "cross_rule_count",
    "typed_rule_count",
    "rule_application_descriptor_count",
    "fixed_position_resolver_profile_count",
    "member_value_schema_count",
    "additive_rule_value_schema_count",
    "full_reachable_value_schema_count",
    "total_expression_node_count",
    "ordered_additive_rule_value_schemas",
    "ordered_intrinsic_rule_attachments",
    "ordered_rule_dependency_edges",
    "ordered_rule_descriptors",
    "ordered_fixed_position_resolver_profiles",
    "ordered_rule_application_descriptors",
    "closure_evidence",
    "rule_application_component_sha256",
}

MARKERS: Final = (
    "ACK_DEADLINE_NOT_DUE",
    "ACK_DEADLINE_TERMINAL_CONVERGED",
    "ADMISSION_CANDIDATE_COMMITTED",
    "ADMISSION_GRANTED",
    "ADMISSION_NOT_GRANTED",
    "ADMISSION_TICKET_ACCEPTED",
    "DISPATCH_RETURN_READY",
    "INGRESS_RETURN_READY",
    "KERNEL_SEND_RESULT_CONVERGED",
    "LOCAL_CLOSE_DISPATCH_CONVERGED",
    "OUTBOUND_ARTIFACTS_PREPARED",
    "PARSER_UNIT_CONVERGED",
    "RAW_PREFIX_COMMITTED",
    "SHUTDOWN_COMMAND_STARTED",
    "SHUTDOWN_TERMINAL_CONVERGED",
    "TARGET_EFFECT_ENTRY",
    "TARGET_ESCAPE_OBSERVED",
    "TCP_HALF_CLOSE_CONVERGED",
    "TLS_CONTROL_CONVERGED",
)
FULL_CHECKPOINT_MARKERS: Final = (
    "ACK_DEADLINE_NOT_DUE",
    "ACK_DEADLINE_TERMINAL_CONVERGED",
    "DISPATCH_RETURN_READY",
    "INGRESS_RETURN_READY",
    "KERNEL_SEND_RESULT_CONVERGED",
    "LOCAL_CLOSE_DISPATCH_CONVERGED",
    "OUTBOUND_ARTIFACTS_PREPARED",
    "PARSER_UNIT_CONVERGED",
    "RAW_PREFIX_COMMITTED",
    "SHUTDOWN_TERMINAL_CONVERGED",
    "TARGET_ESCAPE_OBSERVED",
    "TCP_HALF_CLOSE_CONVERGED",
    "TLS_CONTROL_CONVERGED",
)
FORBIDDEN_CHECKPOINT_MARKERS: Final = (
    "ADMISSION_CANDIDATE_COMMITTED",
    "ADMISSION_GRANTED",
    "ADMISSION_NOT_GRANTED",
    "ADMISSION_TICKET_ACCEPTED",
    "TARGET_EFFECT_ENTRY",
)
MARKER_OPERATIONS: Final = {
    "ACK_DEADLINE_NOT_DUE": ("ACK_DEADLINE_EXPIRY",),
    "ACK_DEADLINE_TERMINAL_CONVERGED": ("ACK_DEADLINE_EXPIRY",),
    "DISPATCH_RETURN_READY": ("SUBSCRIPTION_DISPATCH",),
    "INGRESS_RETURN_READY": ("INGRESS",),
    "KERNEL_SEND_RESULT_CONVERGED": ("SUBSCRIPTION_DISPATCH",),
    "LOCAL_CLOSE_DISPATCH_CONVERGED": ("LOCAL_SHUTDOWN",),
    "OUTBOUND_ARTIFACTS_PREPARED": ("SUBSCRIPTION_DISPATCH",),
    "PARSER_UNIT_CONVERGED": ("INGRESS",),
    "RAW_PREFIX_COMMITTED": ("INGRESS",),
    "SHUTDOWN_TERMINAL_CONVERGED": ("LOCAL_SHUTDOWN",),
    "TARGET_ESCAPE_OBSERVED": (
        "ACK_DEADLINE_EXPIRY",
        "INGRESS",
        "LOCAL_SHUTDOWN",
        "SUBSCRIPTION_DISPATCH",
    ),
    "TCP_HALF_CLOSE_CONVERGED": ("LOCAL_SHUTDOWN",),
    "TLS_CONTROL_CONVERGED": ("LOCAL_SHUTDOWN",),
}


class ValidationError(ValueError):
    """Controlled deterministic ledger validation failure."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


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


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _semantic_id(domain: str, payload: dict[str, Any]) -> str:
    return _sha256(
        _canonical_bytes(
            {
                "canonicalization_version": CANONICALIZATION_VERSION,
                "domain": domain,
                "payload": payload,
                "schema_version": MEASUREMENT_SCHEMA_VERSION,
            }
        )
    )


def _json_depth(value: Any) -> int:
    maximum = 1
    stack: list[tuple[Any, int]] = [(value, 1)]
    while stack:
        current, depth = stack.pop()
        maximum = max(maximum, depth)
        if isinstance(current, dict):
            stack.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            stack.extend((item, depth + 1) for item in current)
    return maximum


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result, f"duplicate JSON member {key!r}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValidationError(f"non-I-JSON numeric constant {value}")


def _reject_json_float(value: str) -> None:
    raise ValidationError(f"floating-point JSON number {value}")


def _require_json_scalar_strings(value: Any) -> None:
    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            for key, item in current.items():
                _require(type(key) is str, "JSON object key is not text")
                _require(
                    not any(0xD800 <= ord(char) <= 0xDFFF for char in key),
                    "JSON object key contains a surrogate",
                )
                stack.append(item)
        elif isinstance(current, list):
            stack.extend(current)
        elif type(current) is str:
            _require(
                not any(0xD800 <= ord(char) <= 0xDFFF for char in current),
                "JSON string contains a surrogate",
            )
        else:
            _require(
                current is None
                or type(current) is bool
                or (
                    type(current) is int and -SAFE_UINT_MAX <= current <= SAFE_UINT_MAX
                ),
                "JSON scalar is outside the controlled I-JSON subset",
            )


def _bounded_regular_read(path: Path, *, maximum_octets: int) -> bytes:
    flags = os.O_RDONLY | os.O_NONBLOCK
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ValidationError(f"cannot open bounded authority: {path.name}") from exc
    try:
        before = os.fstat(descriptor)
        _require(stat.S_ISREG(before.st_mode), f"{path.name} is not a regular file")
        _require(
            before.st_size <= maximum_octets,
            f"{path.name} exceeds its byte bound",
        )
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(65_536, maximum_octets + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            _require(total <= maximum_octets, f"{path.name} exceeds its byte bound")
            chunks.append(chunk)
        after = os.fstat(descriptor)
        _require(
            (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
            )
            == (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
            ),
            f"{path.name} changed during read",
        )
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _decode_json_document(path: Path, raw: bytes) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=_strict_json_object,
            parse_constant=_reject_json_constant,
            parse_float=_reject_json_float,
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        RecursionError,
        ValidationError,
        ValueError,
    ) as exc:
        raise ValidationError(f"{path.name} is not controlled canonical JSON") from exc
    _require(type(value) is dict, f"{path.name} root must be an object")
    _require_json_scalar_strings(value)
    _require(_json_depth(value) <= MAXIMUM_JSON_DEPTH, f"{path.name} is too deep")
    _require(_pretty_bytes(value) == raw, f"{path.name} is not canonical pretty JSON")
    return value


def _load_json_document(
    path: Path,
    *,
    maximum_octets: int,
    expected_sha256: str | None = None,
) -> tuple[dict[str, Any], bytes]:
    raw = _bounded_regular_read(path, maximum_octets=maximum_octets)
    if expected_sha256 is not None:
        _require(_sha256(raw) == expected_sha256, f"{path.name} SHA-256 differs")
    return _decode_json_document(path, raw), raw


def _load_json(
    path: Path,
    *,
    maximum_octets: int,
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    value, _ = _load_json_document(
        path,
        maximum_octets=maximum_octets,
        expected_sha256=expected_sha256,
    )
    return value


def _schema_payload(
    *,
    schema_kind: str,
    nullable: bool,
    boolean_literal: bool | None = None,
    integer_minimum: int | None = None,
    integer_maximum: int | None = None,
    text_language_id: str | None = None,
    array_minimum_items: int | None = None,
    array_maximum_items: int | None = None,
    array_item_value_schema_id: str | None = None,
    referenced_type_name: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_kind": schema_kind,
        "nullable": nullable,
        "boolean_literal": boolean_literal,
        "integer_minimum": integer_minimum,
        "integer_maximum": integer_maximum,
        "text_language_id": text_language_id,
        "array_minimum_items": array_minimum_items,
        "array_maximum_items": array_maximum_items,
        "array_item_value_schema_id": array_item_value_schema_id,
        "referenced_type_name": referenced_type_name,
    }


class SchemaCatalog:
    """Member plus exactly-reachable rule-derived value schemas."""

    def __init__(self, topology: dict[str, Any], scalar: dict[str, Any]) -> None:
        self.topology = topology
        self.record_by_name = {
            item["type_name"]: item
            for item in topology["type_descriptors"]
            if item["type_form"] == "RECORD"
        }
        self.union_names = {
            item["type_name"]
            for item in topology["type_descriptors"]
            if item["type_form"] == "TAGGED_UNION"
        }
        self.member_schemas = {
            item["value_schema_id"]: item for item in scalar["ordered_value_schemas"]
        }
        self.schemas = dict(self.member_schemas)
        self.additive: dict[str, dict[str, Any]] = {}
        self.assignment_by_path = {
            (
                item["source_type_name"],
                tuple(item["typed_member_path"]),
            ): item["value_schema_id"]
            for item in scalar["ordered_member_path_assignments"]
        }
        self.used: set[str] = set()

    def add(self, payload: dict[str, Any]) -> str:
        identifier = _semantic_id(VALUE_SCHEMA_DOMAIN, payload)
        record = {**payload, "value_schema_id": identifier}
        existing = self.schemas.get(identifier)
        if existing is not None:
            _require(existing == record, "value-schema semantic-ID collision")
        else:
            self.schemas[identifier] = record
            self.additive[identifier] = record
        self.used.add(identifier)
        return identifier

    def use(self, identifier: str) -> str:
        _require(identifier in self.schemas, f"unresolved value schema {identifier}")
        self.used.add(identifier)
        return identifier

    def object_ref(self, type_name: str, *, nullable: bool = False) -> str:
        _require(
            type_name in self.record_by_name or type_name in self.union_names,
            f"unknown object-ref target {type_name}",
        )
        return self.add(
            _schema_payload(
                schema_kind="OBJECT_REF",
                nullable=nullable,
                referenced_type_name=type_name,
            )
        )

    def safe_uint(self, minimum: int, maximum: int, *, nullable: bool = False) -> str:
        _require(0 <= minimum <= maximum <= SAFE_UINT_MAX, "bad safe-uint bounds")
        return self.add(
            _schema_payload(
                schema_kind="SAFE_INTEGER",
                nullable=nullable,
                integer_minimum=minimum,
                integer_maximum=maximum,
            )
        )

    def array(self, minimum: int, maximum: int, item_schema_id: str) -> str:
        self.use(item_schema_id)
        return self.add(
            _schema_payload(
                schema_kind="ARRAY",
                nullable=False,
                array_minimum_items=minimum,
                array_maximum_items=maximum,
                array_item_value_schema_id=item_schema_id,
            )
        )

    def member(self, type_name: str, path: Sequence[str]) -> str:
        _require(path, "member path cannot be empty")
        current_type = type_name
        for index, segment in enumerate(path):
            descriptor = self.record_by_name.get(current_type)
            _require(descriptor is not None, f"path enters non-record {current_type}")
            member_names = {
                item["member_name"] for item in descriptor["member_topology"]
            }
            _require(
                segment in member_names, f"unresolved member {current_type}.{segment}"
            )
            direct_id = self.assignment_by_path.get((current_type, (segment,)))
            _require(
                direct_id is not None,
                f"missing scalar assignment {current_type}.{segment}",
            )
            if index == len(path) - 1:
                return self.use(direct_id)
            schema = self.schemas[direct_id]
            _require(
                schema["schema_kind"] == "OBJECT_REF" and not schema["nullable"],
                f"path crosses non-object or nullable member {current_type}.{segment}",
            )
            current_type = schema["referenced_type_name"]
        raise AssertionError("unreachable")

    def projection(self, source_array_schema_id: str, item_path: Sequence[str]) -> str:
        source = self.schemas[self.use(source_array_schema_id)]
        _require(source["schema_kind"] == "ARRAY", "projection source is not array")
        item = self.schemas[source["array_item_value_schema_id"]]
        _require(
            item["schema_kind"] == "OBJECT_REF" and not item["nullable"],
            "projection item is not a required object",
        )
        projected_item = self.member(item["referenced_type_name"], item_path)
        return self.array(
            source["array_minimum_items"],
            source["array_maximum_items"],
            projected_item,
        )

    def array_length_schema(self, array_schema_id: str) -> str:
        source = self.schemas[self.use(array_schema_id)]
        _require(source["schema_kind"] == "ARRAY", "length source is not array")
        return self.safe_uint(
            source["array_minimum_items"],
            source["array_maximum_items"],
        )

    def nonnullable_base(self, nullable_schema_id: str) -> str:
        source = self.schemas[self.use(nullable_schema_id)]
        _require(source["nullable"] is True, "schema is not nullable")
        payload = {
            key: value for key, value in source.items() if key != "value_schema_id"
        }
        payload["nullable"] = False
        return self.add(payload)


@dataclass(frozen=True)
class Binding:
    binding_name: str
    binding_kind: str
    expected_type_name: str | None
    expected_value_schema_id: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "binding_name": self.binding_name,
            "binding_kind": self.binding_kind,
            "expected_type_name": self.expected_type_name,
            "expected_value_schema_id": self.expected_value_schema_id,
        }


class RuleBuilder:
    def __init__(
        self,
        *,
        schemas: SchemaCatalog,
        rule_id: str,
        rule_scope: str,
        bindings: Sequence[Binding],
    ) -> None:
        self.schemas = schemas
        self.rule_id = rule_id
        self.rule_scope = rule_scope
        self.bindings = tuple(bindings)
        self.binding_by_name = {item.binding_name: item for item in bindings}
        _require(
            len(self.binding_by_name) == len(self.bindings),
            f"{rule_id} repeats a binding name",
        )
        self.nodes: list[dict[str, Any]] = []

    def _node(
        self,
        operator: str,
        operands: Sequence[int] = (),
        *,
        result_type_kind: str = "VALUE_SCHEMA",
        result_value_schema_id: str | None = BOOLEAN_SCHEMA_ID,
        input_binding_name: str | None = None,
        typed_member_path: Sequence[str] = (),
        literal_value_schema_id: str | None = None,
        literal_value: Any = None,
    ) -> int:
        _require(operator in OPERATOR_ARITY, f"unknown operator {operator}")
        _require(
            len(operands) == OPERATOR_ARITY[operator],
            f"{operator} arity differs",
        )
        position = len(self.nodes) + 1
        _require(
            all(type(item) is int and 1 <= item < position for item in operands),
            f"{self.rule_id} has a forward operand",
        )
        if result_type_kind == "VALUE_SCHEMA":
            _require(result_value_schema_id is not None, "value result lacks schema")
            self.schemas.use(result_value_schema_id)
        else:
            _require(
                result_type_kind
                in {"INTERNAL_BYTES", "INTERNAL_UINT128", "INTERNAL_INT128"},
                "unknown internal result kind",
            )
            _require(result_value_schema_id is None, "internal result has schema")
        node = {
            "expression_position": position,
            "operator": operator,
            "result_type_kind": result_type_kind,
            "result_value_schema_id": result_value_schema_id,
            "ordered_operand_positions": list(operands),
            "input_binding_name": input_binding_name,
            "typed_member_path": list(typed_member_path),
            "literal_value_schema_id": literal_value_schema_id,
            "literal_value": literal_value,
        }
        self.nodes.append(node)
        return position

    def input(self, binding_name: str, *path: str) -> int:
        binding = self.binding_by_name[binding_name]
        if path:
            _require(binding.binding_kind == "RECORD", "sequence path is forbidden")
            schema_id = self.schemas.member(binding.expected_type_name or "", path)
        else:
            schema_id = self.schemas.use(binding.expected_value_schema_id)
        return self._node(
            "INPUT_PATH",
            result_value_schema_id=schema_id,
            input_binding_name=binding_name,
            typed_member_path=path,
        )

    def literal(self, schema_id: str, value: Any) -> int:
        return self._node(
            "LITERAL",
            result_value_schema_id=schema_id,
            literal_value_schema_id=schema_id,
            literal_value=value,
        )

    def op(
        self,
        operator: str,
        *operands: int,
        schema_id: str = BOOLEAN_SCHEMA_ID,
        path: Sequence[str] = (),
    ) -> int:
        return self._node(
            operator,
            operands,
            result_value_schema_id=schema_id,
            typed_member_path=path,
        )

    def internal(self, operator: str, *operands: int, kind: str) -> int:
        return self._node(
            operator,
            operands,
            result_type_kind=kind,
            result_value_schema_id=None,
        )

    def eq(self, left: int, right: int) -> int:
        return self.op("EQ", left, right)

    def ne(self, left: int, right: int) -> int:
        return self.op("NE", left, right)

    def is_null(self, value: int) -> int:
        return self.op("IS_NULL", value)

    def negate(self, value: int) -> int:
        return self.op("NOT", value)

    def conjunction(self, values: Iterable[int]) -> int:
        items = list(values)
        _require(items, "empty conjunction")
        while len(items) > 1:
            next_level = []
            for index in range(0, len(items), 2):
                if index + 1 == len(items):
                    next_level.append(items[index])
                else:
                    next_level.append(self.op("AND", items[index], items[index + 1]))
            items = next_level
        return items[0]

    def disjunction(self, values: Iterable[int]) -> int:
        items = list(values)
        _require(items, "empty disjunction")
        while len(items) > 1:
            next_level = []
            for index in range(0, len(items), 2):
                if index + 1 == len(items):
                    next_level.append(items[index])
                else:
                    next_level.append(self.op("OR", items[index], items[index + 1]))
            items = next_level
        return items[0]

    def equals_literal(self, value: int, literal_value: Any) -> int:
        schema_id = self.nodes[value - 1]["result_value_schema_id"]
        _require(schema_id is not None, "internal result cannot use value literal")
        return self.eq(value, self.literal(schema_id, literal_value))

    def uint128(self, value: int) -> int:
        return self.internal(
            "SAFE_UINT_TO_INTERNAL_UINT128",
            value,
            kind="INTERNAL_UINT128",
        )

    def uint128_literal(self, value: int) -> int:
        schema = self.schemas.safe_uint(value, value)
        return self.uint128(self.literal(schema, value))

    def length(self, array_value: int) -> int:
        schema_id = self.nodes[array_value - 1]["result_value_schema_id"]
        _require(schema_id is not None, "array value lacks schema")
        length_schema = self.schemas.array_length_schema(schema_id)
        return self.op("ARRAY_LENGTH", array_value, schema_id=length_schema)

    def project(self, array_value: int, *path: str) -> int:
        schema_id = self.nodes[array_value - 1]["result_value_schema_id"]
        _require(schema_id is not None, "projection source lacks schema")
        result = self.schemas.projection(schema_id, path)
        return self.op(
            "ARRAY_PROJECT_REQUIRED_MEMBER",
            array_value,
            schema_id=result,
            path=path,
        )

    def finish(self, root_position: int) -> dict[str, Any]:
        _require(root_position == len(self.nodes), "root must be final expression node")
        _require(
            self.nodes[root_position - 1]["result_value_schema_id"]
            == BOOLEAN_SCHEMA_ID,
            "rule root is not the unrestricted Boolean",
        )
        payload = {
            "rule_id": self.rule_id,
            "rule_version": RULE_VERSION,
            "rule_scope": self.rule_scope,
            "ordered_rule_input_bindings": [item.as_dict() for item in self.bindings],
            "maximum_expression_nodes": len(self.nodes),
            "root_expression_position": root_position,
            "ordered_expression_nodes": self.nodes,
        }
        _require(
            1 <= len(self.nodes) <= MAXIMUM_EXPRESSION_NODES,
            f"{self.rule_id} expression count is outside the bound",
        )
        return {
            **payload,
            "step2_cross_field_rule_descriptor_id": _semantic_id(
                RULE_DOMAIN,
                payload,
            ),
        }


def _intrinsic_builder(schemas: SchemaCatalog, type_name: str) -> RuleBuilder:
    return RuleBuilder(
        schemas=schemas,
        rule_id=f"RULE/INTRINSIC/{type_name}/V1",
        rule_scope="INTRINSIC_RECORD",
        bindings=(
            Binding(
                "self",
                "RECORD",
                type_name,
                schemas.object_ref(type_name),
            ),
        ),
    )


def _timestamp(builder: RuleBuilder, position: int) -> int:
    return builder.internal(
        "TIMESTAMP_TO_EPOCH_MICROSECONDS",
        position,
        kind="INTERNAL_INT128",
    )


def _uint128_text(builder: RuleBuilder, position: int) -> int:
    return builder.internal(
        "UINT128_PARSE",
        position,
        kind="INTERNAL_UINT128",
    )


def _all_null(builder: RuleBuilder, positions: Sequence[int]) -> int:
    return builder.conjunction(builder.is_null(item) for item in positions)


def _all_nonnull(builder: RuleBuilder, positions: Sequence[int]) -> int:
    return builder.conjunction(
        builder.negate(builder.is_null(item)) for item in positions
    )


def _rule_t1(schemas: SchemaCatalog) -> dict[str, Any]:
    builder = _intrinsic_builder(
        schemas,
        "CapacityMeasurementAckDeadlineExpirySpecV1",
    )
    due = builder.input("self", "due_scenario")
    cause = builder.input("self", "expected_terminal_cause_code")
    due_branch = builder.conjunction(
        (
            builder.equals_literal(due, "DUE"),
            builder.equals_literal(cause, "ACK_DEADLINE_EXPIRED"),
        )
    )
    not_due_branch = builder.conjunction(
        (
            builder.equals_literal(due, "NOT_DUE"),
            builder.is_null(cause),
        )
    )
    return builder.finish(builder.disjunction((due_branch, not_due_branch)))


def _rule_t2(schemas: SchemaCatalog) -> dict[str, Any]:
    builder = _intrinsic_builder(
        schemas,
        "CapacityMeasurementAckDeadlineExpiryResultEvidenceV1",
    )
    embedded_id = builder.input(
        "self",
        "due_decision_clock_evidence",
        "due_decision_clock_evidence_id",
    )
    sibling_id = builder.input("self", "due_decision_clock_evidence_id")
    id_equal = builder.eq(embedded_id, sibling_id)
    expired = builder.input("self", "expired")
    due_scenario = builder.input(
        "self",
        "due_decision_clock_evidence",
        "due_scenario",
    )
    expired_due = builder.eq(
        expired,
        builder.equals_literal(due_scenario, "DUE"),
    )
    terminal_ids = (
        builder.input("self", "ack_deadline_expired_event_id"),
        builder.input("self", "terminal_transition_event_id"),
        builder.input("self", "transport_session_termination_id"),
    )
    distinct = builder.conjunction(
        (
            builder.ne(terminal_ids[0], terminal_ids[1]),
            builder.ne(terminal_ids[0], terminal_ids[2]),
            builder.ne(terminal_ids[1], terminal_ids[2]),
        )
    )
    expired_truth = builder.op(
        "IMPLIES",
        expired,
        builder.conjunction((_all_nonnull(builder, terminal_ids), distinct)),
    )
    not_expired_truth = builder.op(
        "IMPLIES",
        builder.negate(expired),
        _all_null(builder, terminal_ids),
    )
    return builder.finish(
        builder.conjunction((id_equal, expired_due, expired_truth, not_expired_truth))
    )


def _rule_t3(schemas: SchemaCatalog) -> dict[str, Any]:
    builder = _intrinsic_builder(
        schemas,
        "CapacityMeasurementDispatchWindowEvidenceV1",
    )
    started_at = _timestamp(builder, builder.input("self", "dispatch_started_at"))
    completed_at = _timestamp(
        builder,
        builder.input("self", "dispatch_completed_at"),
    )
    started_ns = _uint128_text(
        builder,
        builder.input("self", "dispatch_started_monotonic_ns"),
    )
    completed_ns = _uint128_text(
        builder,
        builder.input("self", "dispatch_completed_monotonic_ns"),
    )
    return builder.finish(
        builder.conjunction(
            (
                builder.op("GE", completed_at, started_at),
                builder.op("GT", completed_ns, started_ns),
            )
        )
    )


def _rule_t4(schemas: SchemaCatalog) -> dict[str, Any]:
    builder = _intrinsic_builder(
        schemas,
        "CapacityMeasurementDueDecisionClockEvidenceV1",
    )
    equality_paths = (
        ("dispatch_window_evidence_id", "dispatch_window_evidence_id"),
        ("transport_session_id", "transport_session_id"),
        (
            "outbound_subscription_intent_id",
            "outbound_subscription_intent_id",
        ),
        ("monotonic_clock_domain_id", "monotonic_clock_domain_id"),
    )
    equalities = []
    for embedded_name, sibling_name in equality_paths:
        equalities.append(
            builder.eq(
                builder.input("self", "dispatch_window_evidence", embedded_name),
                builder.input("self", sibling_name),
            )
        )
    wall_before = _timestamp(builder, builder.input("self", "wall_before_at"))
    sampled = _timestamp(builder, builder.input("self", "sampled_at"))
    wall_after = _timestamp(builder, builder.input("self", "wall_after_at"))
    valid_until = _timestamp(builder, builder.input("self", "valid_until"))
    deadline = _timestamp(
        builder,
        builder.input("self", "committed_ack_deadline_at"),
    )
    dispatch_completed = _timestamp(
        builder,
        builder.input(
            "self",
            "dispatch_window_evidence",
            "dispatch_completed_at",
        ),
    )
    mono_before = _uint128_text(
        builder,
        builder.input("self", "monotonic_before_ns"),
    )
    mono_sampled = _uint128_text(
        builder,
        builder.input("self", "monotonic_sampled_ns"),
    )
    mono_after = _uint128_text(
        builder,
        builder.input("self", "monotonic_after_ns"),
    )
    mono_deadline = _uint128_text(
        builder,
        builder.input("self", "committed_ack_deadline_monotonic_ns"),
    )
    dispatch_completed_mono = _uint128_text(
        builder,
        builder.input(
            "self",
            "dispatch_window_evidence",
            "dispatch_completed_monotonic_ns",
        ),
    )
    chronyd_pair = builder.eq(
        builder.is_null(builder.input("self", "chronyd_launch_id")),
        builder.is_null(builder.input("self", "chronyd_runtime_observation_sha256")),
    )
    due = builder.equals_literal(
        builder.input("self", "due_scenario"),
        "DUE",
    )
    derived_due = builder.conjunction(
        (
            builder.op("GE", wall_before, deadline),
            builder.op("GE", mono_before, mono_deadline),
        )
    )
    checks = (
        *equalities,
        builder.op("LE", wall_before, sampled),
        builder.op("LE", sampled, wall_after),
        builder.op("GE", valid_until, sampled),
        builder.op("GT", deadline, dispatch_completed),
        builder.op("LE", mono_before, mono_sampled),
        builder.op("LE", mono_sampled, mono_after),
        builder.op("GT", mono_deadline, dispatch_completed_mono),
        chronyd_pair,
        builder.eq(due, derived_due),
    )
    return builder.finish(builder.conjunction(checks))


def _rule_t6(schemas: SchemaCatalog) -> dict[str, Any]:
    builder = _intrinsic_builder(
        schemas,
        "CapacityMeasurementIngressOperationSpecV2",
    )
    chunks = builder.input("self", "ordered_input_chunks_base64")
    chunk_count = builder.input("self", "input_chunk_count")
    input_octets = builder.input("self", "input_octet_count")
    cap = builder.literal(schemas.safe_uint(65_536, 65_536), 65_536)
    decoded = builder.internal(
        "BASE64_ARRAY_DECODE_CONCAT",
        chunks,
        cap,
        kind="INTERNAL_BYTES",
    )
    decoded_length = builder.op(
        "INTERNAL_BYTES_LENGTH",
        decoded,
        schema_id=builder.nodes[input_octets - 1]["result_value_schema_id"],
    )
    input_sha = builder.input("self", "input_sha256")
    digest = builder.op(
        "SHA256_BYTES",
        decoded,
        schema_id=builder.nodes[input_sha - 1]["result_value_schema_id"],
    )
    parser = builder.uint128(builder.input("self", "expected_parser_unit_count"))
    completed = builder.uint128(
        builder.input("self", "expected_completed_application_message_count")
    )
    frames = builder.uint128(
        builder.input("self", "expected_logical_output_frame_count")
    )
    output_octets = builder.uint128(
        builder.input("self", "expected_logical_output_payload_octets")
    )
    input_octets_128 = builder.uint128(input_octets)
    two_parser = builder.internal(
        "UINT128_MULTIPLY",
        builder.uint128_literal(2),
        parser,
        kind="INTERNAL_UINT128",
    )
    max_output = builder.internal(
        "UINT128_MULTIPLY",
        builder.uint128_literal(125),
        frames,
        kind="INTERNAL_UINT128",
    )
    checks = (
        builder.eq(builder.length(chunks), chunk_count),
        builder.eq(decoded_length, input_octets),
        builder.eq(digest, input_sha),
        builder.op(
            "RAW_INGRESS_BATCH_ID_RECOMPUTES",
            chunks,
            builder.input("self", "raw_ingress_batch_sha256"),
        ),
        builder.op("LE", two_parser, input_octets_128),
        builder.op("LE", completed, parser),
        builder.op("LE", frames, parser),
        builder.op("LE", output_octets, max_output),
    )
    return builder.finish(builder.conjunction(checks))


def _rule_t8(schemas: SchemaCatalog) -> dict[str, Any]:
    builder = _intrinsic_builder(
        schemas,
        "CapacityMeasurementLocalShutdownSpecV2",
    )

    def value(name: str) -> int:
        return builder.uint128(builder.input("self", name))

    batches = value("maximum_terminal_ingress_batches")
    plaintext = value("maximum_terminal_ingress_plaintext_octets")
    parser = value("maximum_terminal_ingress_parser_units")
    tls_records = value("maximum_terminal_tls_records")
    outputs = value("maximum_terminal_ingress_automatic_outputs")
    websocket = value("maximum_websocket_send_attempts")
    sixteen_k_batches = builder.internal(
        "UINT128_MULTIPLY",
        builder.uint128_literal(16_384),
        batches,
        kind="INTERNAL_UINT128",
    )
    two_parser = builder.internal(
        "UINT128_MULTIPLY",
        builder.uint128_literal(2),
        parser,
        kind="INTERNAL_UINT128",
    )
    one_plus_outputs = builder.internal(
        "UINT128_ADD",
        builder.uint128_literal(1),
        outputs,
        kind="INTERNAL_UINT128",
    )
    websocket_bound = builder.internal(
        "UINT128_MULTIPLY",
        builder.uint128_literal(256),
        one_plus_outputs,
        kind="INTERNAL_UINT128",
    )
    return builder.finish(
        builder.conjunction(
            (
                builder.op("LE", plaintext, sixteen_k_batches),
                builder.op("LE", two_parser, plaintext),
                builder.op("LE", tls_records, batches),
                builder.op("LE", outputs, parser),
                builder.op("LE", websocket, websocket_bound),
            )
        )
    )


def _rule_t9(schemas: SchemaCatalog) -> dict[str, Any]:
    builder = _intrinsic_builder(
        schemas,
        "CapacityMeasurementLocalShutdownResultEvidenceV2",
    )
    array_names = (
        "ordered_terminal_ingress_read_attempt_event_ids",
        "ordered_terminal_ingress_read_result_event_ids",
        "ordered_terminal_raw_ingress_commit_ids",
        "ordered_terminal_raw_ingress_actor_event_ids",
        "ordered_terminal_parser_transition_event_ids",
    )
    arrays = {name: builder.input("self", name) for name in array_names}
    lengths = {
        name: builder.uint128(builder.length(position))
        for name, position in arrays.items()
    }
    checks = [builder.op("ARRAY_UNIQUE", position) for position in arrays.values()]
    checks.extend(
        (
            builder.op(
                "EQ",
                lengths["ordered_terminal_ingress_read_attempt_event_ids"],
                lengths["ordered_terminal_ingress_read_result_event_ids"],
            ),
            builder.op(
                "EQ",
                lengths["ordered_terminal_raw_ingress_commit_ids"],
                lengths["ordered_terminal_raw_ingress_actor_event_ids"],
            ),
            builder.op(
                "LE",
                lengths["ordered_terminal_raw_ingress_commit_ids"],
                lengths["ordered_terminal_ingress_read_result_event_ids"],
            ),
            builder.op(
                "EQ",
                builder.uint128(
                    builder.input("self", "final_terminal_ingress_batch_count")
                ),
                lengths["ordered_terminal_ingress_read_attempt_event_ids"],
            ),
            builder.op(
                "GE",
                builder.uint128(
                    builder.input(
                        "self",
                        "final_terminal_ingress_parser_unit_count",
                    )
                ),
                lengths["ordered_terminal_parser_transition_event_ids"],
            ),
        )
    )
    return builder.finish(builder.conjunction(checks))


def _rule_t10(schemas: SchemaCatalog) -> dict[str, Any]:
    builder = _intrinsic_builder(
        schemas,
        "CapacityMeasurementLogicalOutputFrameV1",
    )
    opcode = builder.input("self", "opcode")
    payload = builder.input("self", "payload_base64")
    decoded = builder.internal("BASE64_DECODE", payload, kind="INTERNAL_BYTES")
    return builder.finish(builder.op("RFC6455_CLOSE_PAYLOAD_VALID", opcode, decoded))


def _rule_t11(schemas: SchemaCatalog) -> dict[str, Any]:
    builder = _intrinsic_builder(
        schemas,
        "CapacityMeasurementOperationDeclarationV1",
    )
    return builder.finish(
        builder.conjunction(
            (
                builder.eq(
                    builder.input("self", "operation_kind"),
                    builder.input("self", "operation_spec", "operation_kind"),
                ),
                builder.eq(
                    builder.input("self", "operation_spec_id"),
                    builder.input(
                        "self",
                        "operation_spec",
                        "operation_spec_id",
                    ),
                ),
            )
        )
    )


def _rule_t15(schemas: SchemaCatalog) -> dict[str, Any]:
    builder = _intrinsic_builder(
        schemas,
        "CapacityMeasurementSubscriptionDispatchResultEvidenceV2",
    )
    attempts = builder.input("self", "ordered_kernel_attempt_event_ids")
    results = builder.input("self", "ordered_kernel_result_event_ids")
    return builder.finish(
        builder.conjunction(
            (
                builder.eq(
                    builder.input("self", "generated_request_command_sha256"),
                    builder.input("self", "generated_logical_payload_sha256"),
                ),
                builder.eq(
                    builder.input(
                        "self",
                        "dispatch_window_evidence",
                        "dispatch_window_evidence_id",
                    ),
                    builder.input("self", "dispatch_window_evidence_id"),
                ),
                builder.eq(
                    builder.input(
                        "self",
                        "dispatch_window_evidence",
                        "outbound_subscription_intent_id",
                    ),
                    builder.input("self", "outbound_subscription_intent_id"),
                ),
                builder.eq(builder.length(attempts), builder.length(results)),
                builder.op("ARRAY_UNIQUE", attempts),
                builder.op("ARRAY_UNIQUE", results),
            )
        )
    )


def _rule_t16(schemas: SchemaCatalog) -> dict[str, Any]:
    builder = _intrinsic_builder(schemas, "CheckpointSelectorEntryV1")
    operation = builder.input("self", "operation_kind")
    marker = builder.input("self", "checkpoint_marker_kind")
    branches = []
    for marker_literal, operations in MARKER_OPERATIONS.items():
        for operation_literal in operations:
            branches.append(
                builder.conjunction(
                    (
                        builder.equals_literal(operation, operation_literal),
                        builder.equals_literal(marker, marker_literal),
                    )
                )
            )
    return builder.finish(builder.disjunction(branches))


def _rule_t17(schemas: SchemaCatalog) -> dict[str, Any]:
    builder = _intrinsic_builder(schemas, "CheckpointSelectorV1")
    return builder.finish(
        builder.op(
            "CHECKPOINT_SELECTOR_INTRINSIC_VALID",
            builder.input("self"),
        )
    )


def _marker_contract_literals() -> dict[str, Any]:
    return {
        "ordered_marker_kinds": list(MARKERS),
        "ordered_full_checkpoint_marker_kinds": list(FULL_CHECKPOINT_MARKERS),
        "ordered_checkpoint_operation_records": [
            {
                "checkpoint_marker_kind": marker,
                "applicable_operation_kinds": list(MARKER_OPERATIONS[marker]),
            }
            for marker in FULL_CHECKPOINT_MARKERS
        ],
        "forbidden_full_checkpoint_marker_kinds": list(FORBIDDEN_CHECKPOINT_MARKERS),
    }


def _rule_t18(schemas: SchemaCatalog) -> dict[str, Any]:
    builder = _intrinsic_builder(schemas, "MarkerContractV1")
    checks = []
    for member_name, literal in _marker_contract_literals().items():
        value = builder.input("self", member_name)
        checks.append(builder.equals_literal(value, literal))
    return builder.finish(builder.conjunction(checks))


def _operation_marker_compatible(
    builder: RuleBuilder,
    operation: int,
    marker: int,
) -> int:
    branches = []
    for marker_literal, operations in MARKER_OPERATIONS.items():
        for operation_literal in operations:
            branches.append(
                builder.conjunction(
                    (
                        builder.equals_literal(operation, operation_literal),
                        builder.equals_literal(marker, marker_literal),
                    )
                )
            )
    return builder.disjunction(branches)


def _rule_t19(schemas: SchemaCatalog) -> dict[str, Any]:
    builder = _intrinsic_builder(schemas, "TargetObservationClockSpanV2")
    status = builder.input("self", "span_status")
    started = builder.input("self", "started_offset_nanoseconds")
    completed = builder.input("self", "completed_offset_nanoseconds")
    reason = builder.input("self", "unavailable_reason")
    available = builder.conjunction(
        (
            builder.equals_literal(status, "AVAILABLE"),
            _all_nonnull(builder, (started, completed)),
            builder.op("PRESENT_LE", started, completed),
            builder.is_null(reason),
        )
    )
    unavailable = builder.conjunction(
        (
            builder.equals_literal(status, "UNAVAILABLE"),
            _all_null(builder, (started, completed)),
            builder.negate(builder.is_null(reason)),
        )
    )
    return builder.finish(builder.disjunction((available, unavailable)))


def _span_status(
    builder: RuleBuilder,
    span_name: str,
    status_literal: str,
) -> int:
    return builder.equals_literal(
        builder.input("self", span_name, "span_status"),
        status_literal,
    )


def _span_reason(
    builder: RuleBuilder,
    span_name: str,
    reason_literal: str,
) -> int:
    return builder.equals_literal(
        builder.input("self", span_name, "unavailable_reason"),
        reason_literal,
    )


def _rule_t20(schemas: SchemaCatalog) -> dict[str, Any]:
    builder = _intrinsic_builder(schemas, "TargetObservationContextV2")
    role = builder.input("self", "observation_role")
    operation = builder.input("self", "operation_kind")
    mode = builder.input("self", "instrumentation_mode")
    attempt = builder.input("self", "attempt_id")
    marker_ordinal = builder.input("self", "marker_ordinal")
    marker = builder.input("self", "checkpoint_marker_kind")
    selector_id = builder.input("self", "full_checkpoint_selector_id")
    selector_position = builder.input("self", "checkpoint_selector_position")
    selector_entry_id = builder.input("self", "checkpoint_selector_entry_id")
    expected_marker = builder.input("self", "expected_checkpoint_marker_kind")
    expected_occurrence = builder.input(
        "self",
        "expected_occurrence_index_within_kind",
    )
    binding_status = builder.input("self", "checkpoint_binding_status")
    binding_reason = builder.input(
        "self",
        "checkpoint_binding_unavailable_reason",
    )
    spans = (
        "observer_clock_span",
        "boottime_clock_span",
        "loop_clock_span",
    )
    domain_checks = builder.conjunction(
        (
            builder.equals_literal(
                builder.input("self", "observer_clock_span", "clock_domain"),
                "OBSERVER_MONOTONIC",
            ),
            builder.equals_literal(
                builder.input("self", "boottime_clock_span", "clock_domain"),
                "BOOTTIME",
            ),
            builder.equals_literal(
                builder.input("self", "loop_clock_span", "clock_domain"),
                "EVENT_LOOP",
            ),
        )
    )
    checkpoint_members = (
        selector_id,
        selector_position,
        selector_entry_id,
        expected_marker,
        expected_occurrence,
        binding_status,
    )
    nonstable = builder.conjunction(
        (
            builder.ne(
                role,
                builder.literal(
                    builder.nodes[role - 1]["result_value_schema_id"],
                    "STABLE_CHECKPOINT",
                ),
            ),
            _all_null(
                builder,
                (
                    marker_ordinal,
                    marker,
                    *checkpoint_members,
                    binding_reason,
                ),
            ),
            builder.op(
                "IMPLIES",
                builder.equals_literal(role, "STARTUP_RECOVERY"),
                builder.is_null(attempt),
            ),
        )
    )
    stable_base = builder.conjunction(
        (
            builder.equals_literal(role, "STABLE_CHECKPOINT"),
            builder.equals_literal(mode, "ON"),
            builder.negate(builder.is_null(attempt)),
            _all_nonnull(builder, checkpoint_members),
            _operation_marker_compatible(builder, operation, expected_marker),
        )
    )
    exact_marker = builder.conjunction(
        (
            builder.equals_literal(binding_status, "EXACT_MARKER"),
            builder.negate(builder.is_null(marker_ordinal)),
            builder.eq(marker, expected_marker),
            builder.is_null(binding_reason),
            *(_span_status(builder, name, "AVAILABLE") for name in spans),
        )
    )
    boundary_reason = "TARGET_BOUNDARY_NOT_REACHED"
    boundary = builder.conjunction(
        (
            builder.equals_literal(
                binding_status,
                "UNAVAILABLE_TARGET_BOUNDARY_NOT_REACHED",
            ),
            _all_null(builder, (marker_ordinal, marker)),
            builder.equals_literal(binding_reason, boundary_reason),
            *(
                builder.conjunction(
                    (
                        _span_status(builder, name, "UNAVAILABLE"),
                        _span_reason(builder, name, boundary_reason),
                    )
                )
                for name in spans
            ),
        )
    )
    observer_failure_branches = []
    for reason_literal in (
        "ARTIFACT_BOUND_EXCEEDED",
        "OBSERVER_INTERNAL_ERROR",
        "SOURCE_CLOCK_UNAVAILABLE",
    ):
        observer_failure_branches.append(
            builder.conjunction(
                (
                    builder.equals_literal(
                        binding_status,
                        "UNAVAILABLE_MARKER_OBSERVER_FAILURE",
                    ),
                    _all_null(builder, (marker_ordinal, marker)),
                    builder.equals_literal(binding_reason, reason_literal),
                    *(
                        builder.conjunction(
                            (
                                _span_status(builder, name, "UNAVAILABLE"),
                                _span_reason(builder, name, reason_literal),
                            )
                        )
                        for name in spans
                    ),
                )
            )
        )
    stable = builder.conjunction(
        (
            stable_base,
            builder.disjunction(
                (
                    exact_marker,
                    boundary,
                    builder.disjunction(observer_failure_branches),
                )
            ),
        )
    )
    return builder.finish(
        builder.conjunction((domain_checks, builder.disjunction((nonstable, stable))))
    )


def _rule_t21(schemas: SchemaCatalog) -> dict[str, Any]:
    builder = _intrinsic_builder(schemas, "TargetFieldObservationV1")
    whole = builder.input("self")
    return builder.finish(
        builder.conjunction(
            (
                builder.op("FIELD_OBSERVATION_INTRINSIC_VALID", whole),
                builder.op(
                    "SOURCE_ERROR_DETAIL_ID_RECOMPUTES_FROM_FIELD",
                    whole,
                ),
            )
        )
    )


def _rule_t22(schemas: SchemaCatalog) -> dict[str, Any]:
    builder = _intrinsic_builder(schemas, "TargetObservationV2")
    return builder.finish(
        builder.eq(
            builder.input(
                "self",
                "observation_context",
                "observation_context_id",
            ),
            builder.input("self", "observation_context_id"),
        )
    )


def _rule_t23(schemas: SchemaCatalog) -> dict[str, Any]:
    builder = _intrinsic_builder(schemas, "TargetObservationRootV2")
    ids = builder.input("self", "ordered_observation_ids")
    count = builder.input("self", "observation_count")
    return builder.finish(
        builder.conjunction(
            (
                builder.eq(builder.length(ids), count),
                builder.op("ARRAY_UNIQUE", ids),
            )
        )
    )


def _rule_t24(
    schemas: SchemaCatalog,
    literals: dict[str, Any],
) -> dict[str, Any]:
    builder = _intrinsic_builder(schemas, "TargetFieldRegistryV1")
    registry = literals["target_field_registry"]
    member_names = (
        "status_reason_policy_definition",
        "ordered_vocabulary_definitions",
        "ordered_value_shape_definitions",
        "ordered_value_constraint_definitions",
        "ordered_cross_field_constraint_definitions",
        "descriptors",
    )
    return builder.finish(
        builder.conjunction(
            builder.equals_literal(
                builder.input("self", member_name),
                registry[member_name],
            )
            for member_name in member_names
        )
    )


def _rule_t25(
    schemas: SchemaCatalog,
    literals: dict[str, Any],
) -> dict[str, Any]:
    builder = _intrinsic_builder(
        schemas,
        "OperationCounterSnapshotSchemaV1",
    )
    counter = literals["operation_counter_schema"]
    return builder.finish(
        builder.conjunction(
            builder.equals_literal(
                builder.input("self", member_name),
                counter[member_name],
            )
            for member_name in (
                "ordered_counter_field_ids",
                "monotone_counter_field_ids",
            )
        )
    )


def _rule_t26(schemas: SchemaCatalog) -> dict[str, Any]:
    builder = _intrinsic_builder(schemas, "OperationCounterSnapshotV1")
    return builder.finish(
        builder.op(
            "BITMAP_NULLABILITY_MATCHES",
            builder.input("self", "availability_bitmap"),
            builder.input("self", "values"),
        )
    )


def _rule_t27(schemas: SchemaCatalog) -> dict[str, Any]:
    builder = _intrinsic_builder(schemas, "SourceErrorDetailV1")
    return builder.finish(
        builder.eq(
            builder.is_null(builder.input("self", "source_errno_number")),
            builder.is_null(builder.input("self", "source_errno_name")),
        )
    )


def _rule_t28(schemas: SchemaCatalog) -> dict[str, Any]:
    builder = _intrinsic_builder(
        schemas,
        "CapacityMeasurementObservationMethodRolePairV1",
    )
    return builder.finish(
        builder.op(
            "ARRAY_STRICT_ASCENDING",
            builder.input("self", "allowed_roles"),
        )
    )


def _rule_t29(schemas: SchemaCatalog) -> dict[str, Any]:
    builder = _intrinsic_builder(
        schemas,
        "CapacityMeasurementVocabularyDefinitionV1",
    )
    return builder.finish(
        builder.op(
            "ARRAY_STRICT_ASCENDING",
            builder.input("self", "members"),
        )
    )


def _rule_t30(schemas: SchemaCatalog) -> dict[str, Any]:
    builder = _intrinsic_builder(
        schemas,
        "CapacityMeasurementValueShapeDefinitionV1",
    )
    kind = builder.input("self", "container_kind")
    minimum = builder.input("self", "minimum_items")
    maximum = builder.input("self", "maximum_items")
    keys = builder.input("self", "ordered_keys")
    keys_length = builder.op(
        "ARRAY_LENGTH",
        keys,
        schema_id=schemas.nonnullable_base(
            builder.nodes[minimum - 1]["result_value_schema_id"]
        ),
    )
    minimum_null = builder.is_null(minimum)
    maximum_null = builder.is_null(maximum)
    paired = builder.eq(minimum_null, maximum_null)
    ordered = builder.op("ARRAY_STRICT_ASCENDING", keys)
    zero_keys = builder.equals_literal(keys_length, 0)
    both_present = builder.conjunction(
        (builder.negate(minimum_null), builder.negate(maximum_null))
    )
    scalar_branch = builder.conjunction(
        (
            builder.equals_literal(kind, "SCALAR"),
            minimum_null,
            maximum_null,
            zero_keys,
        )
    )
    list_branch = builder.conjunction(
        (
            builder.equals_literal(kind, "LIST"),
            both_present,
            zero_keys,
        )
    )
    fixed_branch = builder.conjunction(
        (
            builder.equals_literal(kind, "FIXED_MAP"),
            both_present,
            builder.eq(minimum, maximum),
            builder.op("PRESENT_EQ", minimum, keys_length),
            builder.op("PRESENT_EQ", maximum, keys_length),
        )
    )
    return builder.finish(
        builder.conjunction(
            (
                paired,
                builder.op(
                    "IMPLIES", both_present, builder.op("PRESENT_LE", minimum, maximum)
                ),
                ordered,
                builder.disjunction((scalar_branch, list_branch, fixed_branch)),
            )
        )
    )


def _rule_t33(schemas: SchemaCatalog) -> dict[str, Any]:
    builder = _intrinsic_builder(
        schemas,
        "CapacityMeasurementAttemptStateErrorFormsV1",
    )
    return builder.finish(
        builder.conjunction(
            (
                builder.op(
                    "ARRAY_STRICT_ASCENDING",
                    builder.input("self", "permitted_error_forms"),
                ),
                builder.op(
                    "ARRAY_STRICT_ASCENDING",
                    builder.input("self", "permitted_failure_phases"),
                ),
            )
        )
    )


def _rule_t34(schemas: SchemaCatalog) -> dict[str, Any]:
    builder = _intrinsic_builder(
        schemas,
        "CapacityMeasurementStatusReasonRuleV1",
    )
    projected = builder.project(
        builder.input("self", "attempt_state_error_forms"),
        "attempt_state",
    )
    return builder.finish(builder.op("ARRAY_STRICT_ASCENDING", projected))


def _rule_t36(schemas: SchemaCatalog) -> dict[str, Any]:
    builder = _intrinsic_builder(
        schemas,
        "CapacityMeasurementStatusReasonPolicyDefinitionV1",
    )
    projections = (
        ("availability_state_rules", "availability"),
        ("reason_rules", "reason"),
        ("error_form_definitions", "error_form"),
    )
    return builder.finish(
        builder.conjunction(
            builder.op(
                "ARRAY_STRICT_ASCENDING",
                builder.project(builder.input("self", array_name), key_name),
            )
            for array_name, key_name in projections
        )
    )


def _rule_t38(schemas: SchemaCatalog) -> dict[str, Any]:
    builder = _intrinsic_builder(
        schemas,
        "CapacityMeasurementTargetFieldDescriptorV1",
    )
    method_projection = builder.project(
        builder.input("self", "observation_method_role_pairs"),
        "observation_method",
    )
    ascending_members = (
        "allowed_checkpoint_marker_kinds",
        "applicable_operation_kinds",
        "allowed_status_reasons",
        "value_shape_keys",
        "cross_field_constraint_ids",
    )
    return builder.finish(
        builder.conjunction(
            (
                builder.op(
                    "FIELD_LAYER_EQUALS_UPPERCASE_FIELD_PREFIX",
                    builder.input("self", "layer"),
                    builder.input("self", "field_id"),
                ),
                builder.op("ARRAY_STRICT_ASCENDING", method_projection),
                *(
                    builder.op(
                        "ARRAY_STRICT_ASCENDING",
                        builder.input("self", member_name),
                    )
                    for member_name in ascending_members
                ),
            )
        )
    )


def _rule_t39(schemas: SchemaCatalog) -> dict[str, Any]:
    builder = _intrinsic_builder(
        schemas,
        "CapacityMeasurementCheckpointOperationRecordV1",
    )
    marker = builder.input("self", "checkpoint_marker_kind")
    operations = builder.input("self", "applicable_operation_kinds")
    branches = []
    for marker_literal in FULL_CHECKPOINT_MARKERS:
        branches.append(
            builder.conjunction(
                (
                    builder.equals_literal(marker, marker_literal),
                    builder.equals_literal(
                        operations,
                        list(MARKER_OPERATIONS[marker_literal]),
                    ),
                )
            )
        )
    return builder.finish(builder.disjunction(branches))


def _optional_presence_rule(
    schemas: SchemaCatalog,
    type_name: str,
) -> dict[str, Any]:
    builder = _intrinsic_builder(schemas, type_name)
    return builder.finish(
        builder.eq(
            builder.input("self", "present"),
            builder.negate(builder.is_null(builder.input("self", "value"))),
        )
    )


def _rule_t48(schemas: SchemaCatalog) -> dict[str, Any]:
    builder = _intrinsic_builder(
        schemas,
        "CapacityMeasurementFixedUIntMapValueV1",
    )
    projected = builder.project(
        builder.input("self", "ordered"),
        "key",
    )
    return builder.finish(builder.op("ARRAY_STRICT_ASCENDING", projected))


def _rule_t49(schemas: SchemaCatalog) -> dict[str, Any]:
    builder = _intrinsic_builder(
        schemas,
        "CapacityMeasurementDurationBoundValueV1",
    )
    relation = builder.input("self", "relation")
    lower = builder.input("self", "lower_nanoseconds")
    upper = builder.input("self", "upper_nanoseconds")
    lower_null = builder.is_null(lower)
    upper_null = builder.is_null(upper)
    exact = builder.conjunction(
        (
            builder.equals_literal(relation, "EXACT"),
            builder.negate(lower_null),
            builder.eq(upper, lower),
        )
    )
    lower_bound = builder.conjunction(
        (
            builder.equals_literal(relation, "LOWER_BOUND"),
            builder.negate(lower_null),
            upper_null,
        )
    )
    upper_bound = builder.conjunction(
        (
            builder.equals_literal(relation, "UPPER_BOUND"),
            lower_null,
            builder.negate(upper_null),
        )
    )
    interval = builder.conjunction(
        (
            builder.equals_literal(relation, "INTERVAL"),
            builder.negate(lower_null),
            builder.negate(upper_null),
            builder.op("PRESENT_LE", lower, upper),
        )
    )
    return builder.finish(
        builder.disjunction((exact, lower_bound, upper_bound, interval))
    )


def _record_binding(
    schemas: SchemaCatalog,
    binding_name: str,
    type_name: str,
) -> Binding:
    return Binding(
        binding_name,
        "RECORD",
        type_name,
        schemas.object_ref(type_name),
    )


def _cross_rule_counter(schemas: SchemaCatalog) -> dict[str, Any]:
    builder = RuleBuilder(
        schemas=schemas,
        rule_id=CROSS_RULE_IDS[0],
        rule_scope="CROSS_RECORD",
        bindings=(
            _record_binding(
                schemas,
                "counter_snapshot",
                "OperationCounterSnapshotV1",
            ),
            _record_binding(
                schemas,
                "counter_schema",
                "OperationCounterSnapshotSchemaV1",
            ),
        ),
    )
    values = builder.input("counter_snapshot", "values")
    return builder.finish(
        builder.conjunction(
            (
                builder.eq(
                    builder.input("counter_snapshot", "counter_schema_id"),
                    builder.input("counter_schema", "counter_schema_id"),
                ),
                builder.op(
                    "EQ",
                    builder.uint128(builder.length(values)),
                    builder.uint128(
                        builder.input("counter_schema", "counter_field_count")
                    ),
                ),
            )
        )
    )


def _find_field_descriptor(
    builder: RuleBuilder,
    *,
    field_binding: str,
    registry_binding: str,
) -> int:
    descriptors = builder.input(registry_binding, "descriptors")
    field_id = builder.input(field_binding, "field_id")
    descriptor_schema = builder.schemas.object_ref(
        "CapacityMeasurementTargetFieldDescriptorV1"
    )
    return builder.op(
        "ARRAY_FIND_UNIQUE_OBJECT_BY_MEMBER",
        descriptors,
        field_id,
        schema_id=descriptor_schema,
        path=("field_id",),
    )


def _cross_rule_field_registry(schemas: SchemaCatalog) -> dict[str, Any]:
    builder = RuleBuilder(
        schemas=schemas,
        rule_id=CROSS_RULE_IDS[1],
        rule_scope="CROSS_RECORD",
        bindings=(
            _record_binding(
                schemas,
                "field_observation",
                "TargetFieldObservationV1",
            ),
            _record_binding(
                schemas,
                "target_registry",
                "TargetFieldRegistryV1",
            ),
        ),
    )
    field = builder.input("field_observation")
    registry = builder.input("target_registry")
    descriptor = _find_field_descriptor(
        builder,
        field_binding="field_observation",
        registry_binding="target_registry",
    )
    return builder.finish(
        builder.conjunction(
            (
                builder.op(
                    "FIELD_OBSERVATION_SATISFIES_DESCRIPTOR_POLICY",
                    field,
                    descriptor,
                    registry,
                ),
                builder.op(
                    "TARGET_VALUE_SATISFIES_DESCRIPTOR",
                    field,
                    descriptor,
                    registry,
                ),
            )
        )
    )


def _cross_rule_operation_result(schemas: SchemaCatalog) -> dict[str, Any]:
    builder = RuleBuilder(
        schemas=schemas,
        rule_id=CROSS_RULE_IDS[2],
        rule_scope="CROSS_RECORD",
        bindings=(
            _record_binding(
                schemas,
                "result",
                "CapacityMeasurementOperationResultEvidence",
            ),
            _record_binding(
                schemas,
                "signed_spec",
                "CapacityMeasurementOperationSpec",
            ),
        ),
    )
    return builder.finish(
        builder.op(
            "OPERATION_RESULT_MATCHES_SIGNED_SPEC",
            builder.input("result"),
            builder.input("signed_spec"),
        )
    )


def _cross_rule_selector_marker(schemas: SchemaCatalog) -> dict[str, Any]:
    builder = RuleBuilder(
        schemas=schemas,
        rule_id=CROSS_RULE_IDS[3],
        rule_scope="CROSS_RECORD",
        bindings=(
            _record_binding(schemas, "selector", "CheckpointSelectorV1"),
            _record_binding(schemas, "marker_contract", "MarkerContractV1"),
        ),
    )
    return builder.finish(
        builder.op(
            "CHECKPOINT_SELECTOR_MARKER_CONTRACT_ADMITTED",
            builder.input("selector"),
            builder.input("marker_contract"),
        )
    )


def _cross_rule_v2_observation_aggregate(
    schemas: SchemaCatalog,
) -> dict[str, Any]:
    builder = RuleBuilder(
        schemas=schemas,
        rule_id=CROSS_RULE_IDS[4],
        rule_scope="CROSS_RECORD",
        bindings=(
            _record_binding(schemas, "observation", "TargetObservationV2"),
            _record_binding(
                schemas,
                "target_registry",
                "TargetFieldRegistryV1",
            ),
        ),
    )
    return builder.finish(
        builder.op(
            "A1_FIFO_FIELDS_VALID",
            builder.input("observation", "field_observations"),
            builder.input("target_registry"),
        )
    )


def _v2_field_bindings(schemas: SchemaCatalog) -> tuple[Binding, ...]:
    return (
        _record_binding(schemas, "observation", "TargetObservationV2"),
        _record_binding(
            schemas,
            "target_registry",
            "TargetFieldRegistryV1",
        ),
        _record_binding(
            schemas,
            "field_observation",
            "TargetFieldObservationV1",
        ),
        _record_binding(
            schemas,
            "field_descriptor",
            "CapacityMeasurementTargetFieldDescriptorV1",
        ),
        Binding(
            "field_ordinal",
            "SAFE_UINT",
            None,
            schemas.safe_uint(0, 184),
        ),
    )


def _cross_rule_v2_observation_field(
    schemas: SchemaCatalog,
) -> dict[str, Any]:
    builder = RuleBuilder(
        schemas=schemas,
        rule_id=CROSS_RULE_IDS[5],
        rule_scope="CROSS_RECORD",
        bindings=_v2_field_bindings(schemas),
    )
    field = builder.input("field_observation")
    descriptor = builder.input("field_descriptor")
    registry = builder.input("target_registry")
    context = builder.input("observation", "observation_context")
    ordinal = builder.input("field_ordinal")
    return builder.finish(
        builder.conjunction(
            (
                builder.op(
                    "FIELD_OBSERVATION_SATISFIES_DESCRIPTOR_POLICY",
                    field,
                    descriptor,
                    registry,
                ),
                builder.op(
                    "TARGET_VALUE_SATISFIES_DESCRIPTOR",
                    field,
                    descriptor,
                    registry,
                ),
                builder.op(
                    "V2_FIELD_OBSERVATION_CONTEXT_VALID",
                    field,
                    descriptor,
                    registry,
                    context,
                    ordinal,
                ),
            )
        )
    )


def _root_membership_bindings(schemas: SchemaCatalog) -> tuple[Binding, ...]:
    return (
        _record_binding(schemas, "root", "TargetObservationRootV2"),
        _record_binding(schemas, "observation", "TargetObservationV2"),
        Binding(
            "observation_ordinal",
            "SAFE_UINT",
            None,
            schemas.safe_uint(0, 66),
        ),
    )


def _cross_rule_root_membership(schemas: SchemaCatalog) -> dict[str, Any]:
    builder = RuleBuilder(
        schemas=schemas,
        rule_id=CROSS_RULE_IDS[6],
        rule_scope="CROSS_RECORD",
        bindings=_root_membership_bindings(schemas),
    )
    comparisons = []
    for member_name in (
        "candidate_id",
        "attempt_id",
        "operation_kind",
        "instrumentation_mode",
        "target_field_registry_id",
    ):
        comparisons.append(
            builder.eq(
                builder.input("root", member_name),
                builder.input(
                    "observation",
                    "observation_context",
                    member_name,
                ),
            )
        )
    # The ordinal is required for deterministic application evidence; the
    # fixed-position resolver owns ordinal-to-identity positioning.
    return builder.finish(builder.conjunction(comparisons))


def _root_lifecycle_bindings(schemas: SchemaCatalog) -> tuple[Binding, ...]:
    observation_ref = schemas.object_ref("TargetObservationV2")
    observations = schemas.array(1, 67, observation_ref)
    selector = schemas.object_ref("CheckpointSelectorV1", nullable=True)
    return (
        _record_binding(schemas, "root", "TargetObservationRootV2"),
        Binding(
            "observations",
            "FIXED_RECORD_SEQUENCE",
            "TargetObservationV2",
            observations,
        ),
        Binding(
            "selector",
            "OPTIONAL_FIXED_RECORD",
            "CheckpointSelectorV1",
            selector,
        ),
    )


def _cross_rule_root_lifecycle(schemas: SchemaCatalog) -> dict[str, Any]:
    builder = RuleBuilder(
        schemas=schemas,
        rule_id=CROSS_RULE_IDS[7],
        rule_scope="CROSS_RECORD",
        bindings=_root_lifecycle_bindings(schemas),
    )
    return builder.finish(
        builder.op(
            "V2_ROOT_SEQUENCE_SELECTOR_VALID",
            builder.input("root"),
            builder.input("observations"),
            builder.input("selector"),
        )
    )


def _intrinsic_rules(
    schemas: SchemaCatalog,
    literals: dict[str, Any],
) -> list[dict[str, Any]]:
    rules = (
        _rule_t1(schemas),
        _rule_t2(schemas),
        _rule_t3(schemas),
        _rule_t4(schemas),
        _rule_t6(schemas),
        _rule_t8(schemas),
        _rule_t9(schemas),
        _rule_t10(schemas),
        _rule_t11(schemas),
        _rule_t15(schemas),
        _rule_t16(schemas),
        _rule_t17(schemas),
        _rule_t18(schemas),
        _rule_t19(schemas),
        _rule_t20(schemas),
        _rule_t21(schemas),
        _rule_t22(schemas),
        _rule_t23(schemas),
        _rule_t24(schemas, literals),
        _rule_t25(schemas, literals),
        _rule_t26(schemas),
        _rule_t27(schemas),
        _rule_t28(schemas),
        _rule_t29(schemas),
        _rule_t30(schemas),
        _rule_t33(schemas),
        _rule_t34(schemas),
        _rule_t36(schemas),
        _rule_t38(schemas),
        _rule_t39(schemas),
        _optional_presence_rule(
            schemas,
            "CapacityMeasurementOptionalUIntValueV1",
        ),
        _optional_presence_rule(
            schemas,
            "CapacityMeasurementOptionalTextValueV1",
        ),
        _rule_t48(schemas),
        _rule_t49(schemas),
    )
    return list(rules)


def _cross_rules(schemas: SchemaCatalog) -> list[dict[str, Any]]:
    return [
        _cross_rule_counter(schemas),
        _cross_rule_field_registry(schemas),
        _cross_rule_operation_result(schemas),
        _cross_rule_selector_marker(schemas),
        _cross_rule_v2_observation_aggregate(schemas),
        _cross_rule_v2_observation_field(schemas),
        _cross_rule_root_membership(schemas),
        _cross_rule_root_lifecycle(schemas),
    ]


def _resolver_profiles() -> list[dict[str, Any]]:
    records = [
        {
            "profile_name": "RAW_V8_V2_ROOT_OBSERVATION_RESOLVER_V1",
            "source_root_type_name": "TargetObservationRootV2",
            "ordered_source_identity_path_descriptors": [
                {
                    "path_position": 1,
                    "typed_member_path": ["ordered_observation_ids"],
                    "result_kind": "ARRAY",
                    "null_semantics": "REJECT_NULL",
                }
            ],
            "resolved_item_type_name": "TargetObservationV2",
            "minimum_items": 1,
            "maximum_items": 67,
            "resolution_semantics": (
                "CALLER_SUPPLIED_COMPLETE_RECORDS_ID_MATCH_IN_SOURCE_ORDER"
            ),
        },
        {
            "profile_name": "RAW_V8_V2_ROOT_SELECTOR_RESOLVER_V1",
            "source_root_type_name": "TargetObservationRootV2",
            "ordered_source_identity_path_descriptors": [
                {
                    "path_position": 1,
                    "typed_member_path": ["full_checkpoint_selector_id"],
                    "result_kind": "OPTIONAL_SCALAR",
                    "null_semantics": "NULL_TO_EMPTY_SEQUENCE",
                }
            ],
            "resolved_item_type_name": "CheckpointSelectorV1",
            "minimum_items": 0,
            "maximum_items": 1,
            "resolution_semantics": (
                "CALLER_SUPPLIED_COMPLETE_RECORDS_ID_MATCH_IN_SOURCE_ORDER"
            ),
        },
    ]
    expected_ids = {
        "RAW_V8_V2_ROOT_OBSERVATION_RESOLVER_V1": (
            "87224ef058fff2867da671aec58d53c0a06fc9542ae84ad0378af6db48349daf"
        ),
        "RAW_V8_V2_ROOT_SELECTOR_RESOLVER_V1": (
            "73acbeea28d638acb77aab44dad201e08cc5267e830ddd4714d54aa70813b54b"
        ),
    }
    materialized = []
    for payload in records:
        identifier = _semantic_id(RESOLVER_DOMAIN, payload)
        _require(
            identifier == expected_ids[payload["profile_name"]],
            f"resolver ID drifted for {payload['profile_name']}",
        )
        materialized.append(
            {**payload, "fixed_position_resolver_profile_id": identifier}
        )
    return sorted(
        materialized,
        key=lambda item: item["fixed_position_resolver_profile_id"],
    )


def _root_binding(
    name: str,
    position: int,
    type_name: str,
) -> dict[str, Any]:
    return {
        "binding_name": name,
        "tuple_position": position,
        "expected_type_name": type_name,
    }


def _sequence_binding(
    *,
    binding_name: str,
    binding_mode: str,
    source_kind: str,
    source_root_binding_name: str,
    embedded_path: Sequence[str],
    resolver_id: str | None,
    item_type: str,
) -> dict[str, Any]:
    return {
        "binding_name": binding_name,
        "binding_mode": binding_mode,
        "source_kind": source_kind,
        "source_root_binding_name": source_root_binding_name,
        "embedded_array_typed_member_path": list(embedded_path),
        "fixed_position_resolver_profile_id": resolver_id,
        "expected_item_type_name": item_type,
    }


def _application_payloads() -> list[dict[str, Any]]:
    observation_resolver = (
        "87224ef058fff2867da671aec58d53c0a06fc9542ae84ad0378af6db48349daf"
    )
    selector_resolver = (
        "73acbeea28d638acb77aab44dad201e08cc5267e830ddd4714d54aa70813b54b"
    )
    return [
        {
            "application_name": "APPLY/COUNTER_SNAPSHOT_SCHEMA_V1",
            "rule_id": CROSS_RULE_IDS[0],
            "application_kind": "RECORD_TUPLE",
            "ordered_root_input_bindings": [
                _root_binding(
                    "counter_snapshot",
                    1,
                    "OperationCounterSnapshotV1",
                ),
                _root_binding(
                    "counter_schema",
                    2,
                    "OperationCounterSnapshotSchemaV1",
                ),
            ],
            "ordered_sequence_input_bindings": [],
            "iteration_ordinal_binding_name": None,
            "maximum_rule_evaluations": 1,
            "requires_equal_cardinality": False,
            "evaluation_order": "SINGLE_EVALUATION",
        },
        {
            "application_name": "APPLY/FIELD_OBSERVATION_FROZEN_REGISTRY_V1",
            "rule_id": CROSS_RULE_IDS[1],
            "application_kind": "RECORD_TUPLE",
            "ordered_root_input_bindings": [
                _root_binding(
                    "field_observation",
                    1,
                    "TargetFieldObservationV1",
                ),
                _root_binding("target_registry", 2, "TargetFieldRegistryV1"),
            ],
            "ordered_sequence_input_bindings": [],
            "iteration_ordinal_binding_name": None,
            "maximum_rule_evaluations": 1,
            "requires_equal_cardinality": False,
            "evaluation_order": "SINGLE_EVALUATION",
        },
        {
            "application_name": "APPLY/OPERATION_RESULT_SIGNED_SPEC_V1",
            "rule_id": CROSS_RULE_IDS[2],
            "application_kind": "RECORD_TUPLE",
            "ordered_root_input_bindings": [
                _root_binding(
                    "result",
                    1,
                    "CapacityMeasurementOperationResultEvidence",
                ),
                _root_binding(
                    "signed_spec",
                    2,
                    "CapacityMeasurementOperationSpec",
                ),
            ],
            "ordered_sequence_input_bindings": [],
            "iteration_ordinal_binding_name": None,
            "maximum_rule_evaluations": 1,
            "requires_equal_cardinality": False,
            "evaluation_order": "SINGLE_EVALUATION",
        },
        {
            "application_name": "APPLY/SELECTOR_MARKER_CONTRACT_V1",
            "rule_id": CROSS_RULE_IDS[3],
            "application_kind": "RECORD_TUPLE",
            "ordered_root_input_bindings": [
                _root_binding("selector", 1, "CheckpointSelectorV1"),
                _root_binding("marker_contract", 2, "MarkerContractV1"),
            ],
            "ordered_sequence_input_bindings": [],
            "iteration_ordinal_binding_name": None,
            "maximum_rule_evaluations": 1,
            "requires_equal_cardinality": False,
            "evaluation_order": "SINGLE_EVALUATION",
        },
        {
            "application_name": "APPLY/V2_OBSERVATION_AGGREGATE_REGISTRY_V1",
            "rule_id": CROSS_RULE_IDS[4],
            "application_kind": "RECORD_TUPLE",
            "ordered_root_input_bindings": [
                _root_binding("observation", 1, "TargetObservationV2"),
                _root_binding("target_registry", 2, "TargetFieldRegistryV1"),
            ],
            "ordered_sequence_input_bindings": [],
            "iteration_ordinal_binding_name": None,
            "maximum_rule_evaluations": 1,
            "requires_equal_cardinality": False,
            "evaluation_order": "SINGLE_EVALUATION",
        },
        {
            "application_name": "APPLY/V2_OBSERVATION_FIELDS_REGISTRY_V1",
            "rule_id": CROSS_RULE_IDS[5],
            "application_kind": "ARRAY_EACH",
            "ordered_root_input_bindings": [
                _root_binding("observation", 1, "TargetObservationV2"),
                _root_binding("target_registry", 2, "TargetFieldRegistryV1"),
            ],
            "ordered_sequence_input_bindings": [
                _sequence_binding(
                    binding_name="field_observation",
                    binding_mode="ITERATED_RECORD",
                    source_kind="EMBEDDED_ARRAY",
                    source_root_binding_name="observation",
                    embedded_path=("field_observations",),
                    resolver_id=None,
                    item_type="TargetFieldObservationV1",
                ),
                _sequence_binding(
                    binding_name="field_descriptor",
                    binding_mode="ITERATED_RECORD",
                    source_kind="EMBEDDED_ARRAY",
                    source_root_binding_name="target_registry",
                    embedded_path=("descriptors",),
                    resolver_id=None,
                    item_type="CapacityMeasurementTargetFieldDescriptorV1",
                ),
            ],
            "iteration_ordinal_binding_name": "field_ordinal",
            "maximum_rule_evaluations": 185,
            "requires_equal_cardinality": True,
            "evaluation_order": ("LEXICAL_APPLICATION_NAME_THEN_SEQUENCE_ORDINAL"),
        },
        {
            "application_name": "APPLY/V2_ROOT_OBSERVATION_MEMBERSHIP_V1",
            "rule_id": CROSS_RULE_IDS[6],
            "application_kind": "FOR_EACH_FIXED_POSITION_BINDING",
            "ordered_root_input_bindings": [
                _root_binding("root", 1, "TargetObservationRootV2")
            ],
            "ordered_sequence_input_bindings": [
                _sequence_binding(
                    binding_name="observation",
                    binding_mode="ITERATED_RECORD",
                    source_kind="EXTERNAL_FIXED_SEQUENCE",
                    source_root_binding_name="root",
                    embedded_path=(),
                    resolver_id=observation_resolver,
                    item_type="TargetObservationV2",
                )
            ],
            "iteration_ordinal_binding_name": "observation_ordinal",
            "maximum_rule_evaluations": 67,
            "requires_equal_cardinality": False,
            "evaluation_order": ("LEXICAL_APPLICATION_NAME_THEN_SEQUENCE_ORDINAL"),
        },
        {
            "application_name": "APPLY/V2_ROOT_SELECTOR_LIFECYCLE_V1",
            "rule_id": CROSS_RULE_IDS[7],
            "application_kind": "FIXED_SEQUENCE_AGGREGATE",
            "ordered_root_input_bindings": [
                _root_binding("root", 1, "TargetObservationRootV2")
            ],
            "ordered_sequence_input_bindings": [
                _sequence_binding(
                    binding_name="observations",
                    binding_mode="COMPLETE_RECORD_SEQUENCE",
                    source_kind="EXTERNAL_FIXED_SEQUENCE",
                    source_root_binding_name="root",
                    embedded_path=(),
                    resolver_id=observation_resolver,
                    item_type="TargetObservationV2",
                ),
                _sequence_binding(
                    binding_name="selector",
                    binding_mode="OPTIONAL_RECORD",
                    source_kind="EXTERNAL_FIXED_SEQUENCE",
                    source_root_binding_name="root",
                    embedded_path=(),
                    resolver_id=selector_resolver,
                    item_type="CheckpointSelectorV1",
                ),
            ],
            "iteration_ordinal_binding_name": None,
            "maximum_rule_evaluations": 1,
            "requires_equal_cardinality": False,
            "evaluation_order": "SINGLE_EVALUATION",
        },
    ]


def _applications() -> list[dict[str, Any]]:
    expected_ids = {
        "APPLY/COUNTER_SNAPSHOT_SCHEMA_V1": (
            "1011bd624480ce2c9a8bf559c16e876c33fc2167857ee696fcea37cc0cb628f2"
        ),
        "APPLY/FIELD_OBSERVATION_FROZEN_REGISTRY_V1": (
            "5fcc7e2bdc01bde47d4cd57c1fb134c1da6888d9609c65ec0bfe431365965b27"
        ),
        "APPLY/OPERATION_RESULT_SIGNED_SPEC_V1": (
            "770d99b0001802ceb6bdc044b9b55ce3cfd319754e9b9716c10d0b3d2e214f18"
        ),
        "APPLY/SELECTOR_MARKER_CONTRACT_V1": (
            "30f3a8688435dff87bc5ff329e7a9dd6bbbf40c71de5dd746a4cb1e9008b3ee5"
        ),
        "APPLY/V2_OBSERVATION_AGGREGATE_REGISTRY_V1": (
            "0fff77cbc03f9fcf019e8352875d9b7f49a3ab8a0ed374e9d5b9bb2f7f9a38fb"
        ),
        "APPLY/V2_OBSERVATION_FIELDS_REGISTRY_V1": (
            "87b0ee70e1eab470868e357facd3bb6eb203ce4ed8363cbd6fa30a6ee86c8d63"
        ),
        "APPLY/V2_ROOT_OBSERVATION_MEMBERSHIP_V1": (
            "0737d82dae748ff1bf3b19230be2196973c7d6d0fa6c97ef834e9517e09e5f0a"
        ),
        "APPLY/V2_ROOT_SELECTOR_LIFECYCLE_V1": (
            "86a3acbf53805768a1a462fe28c75a7e7192487f71579ba021aa03d7992a9a42"
        ),
    }
    result = []
    for payload in _application_payloads():
        identifier = _semantic_id(APPLICATION_DOMAIN, payload)
        _require(
            identifier == expected_ids[payload["application_name"]],
            f"application ID drifted for {payload['application_name']}",
        )
        result.append({**payload, "rule_application_id": identifier})
    _require(
        [item["application_name"] for item in result]
        == sorted(item["application_name"] for item in result),
        "application names are not lexical",
    )
    return result


def _attachment_ledger(topology: dict[str, Any]) -> list[dict[str, Any]]:
    records = [
        item for item in topology["type_descriptors"] if item["type_form"] == "RECORD"
    ]
    _require(len(records) == 49, "attachment topology must contain 49 records")
    attached = set(INTRINSIC_TYPE_POSITIONS)
    unattached = set(NO_INTRINSIC_TYPE_POSITIONS)
    _require(
        attached.isdisjoint(unattached) and attached | unattached == set(range(1, 50)),
        "intrinsic attachment partition differs",
    )
    result = []
    for position, descriptor in enumerate(records, 1):
        rule_ids = (
            [f"RULE/INTRINSIC/{descriptor['type_name']}/V1"]
            if position in attached
            else []
        )
        result.append(
            {
                "concrete_type_position": position,
                "type_name": descriptor["type_name"],
                "ordered_intrinsic_rule_ids": rule_ids,
            }
        )
    return result


RULE_DEPENDENCY_EDGES: Final = (
    (
        "RULE/INTRINSIC/CapacityMeasurementDispatchWindowEvidenceV1/V1",
        "RULE/INTRINSIC/CapacityMeasurementDueDecisionClockEvidenceV1/V1",
    ),
    (
        "RULE/INTRINSIC/CapacityMeasurementDueDecisionClockEvidenceV1/V1",
        "RULE/INTRINSIC/CapacityMeasurementAckDeadlineExpiryResultEvidenceV1/V1",
    ),
    (
        "RULE/INTRINSIC/CapacityMeasurementDispatchWindowEvidenceV1/V1",
        "RULE/INTRINSIC/CapacityMeasurementSubscriptionDispatchResultEvidenceV2/V1",
    ),
    (
        "RULE/INTRINSIC/CheckpointSelectorEntryV1/V1",
        "RULE/INTRINSIC/CheckpointSelectorV1/V1",
    ),
    (
        "RULE/INTRINSIC/CapacityMeasurementCheckpointOperationRecordV1/V1",
        "RULE/INTRINSIC/MarkerContractV1/V1",
    ),
    (
        "RULE/INTRINSIC/TargetObservationClockSpanV2/V1",
        "RULE/INTRINSIC/TargetObservationContextV2/V1",
    ),
    (
        "RULE/INTRINSIC/TargetObservationContextV2/V1",
        "RULE/INTRINSIC/TargetObservationV2/V1",
    ),
    (
        "RULE/INTRINSIC/TargetFieldObservationV1/V1",
        "RULE/INTRINSIC/TargetObservationV2/V1",
    ),
    (
        "RULE/INTRINSIC/CapacityMeasurementObservationMethodRolePairV1/V1",
        "RULE/INTRINSIC/CapacityMeasurementTargetFieldDescriptorV1/V1",
    ),
    (
        "RULE/INTRINSIC/CapacityMeasurementAttemptStateErrorFormsV1/V1",
        "RULE/INTRINSIC/CapacityMeasurementStatusReasonRuleV1/V1",
    ),
    (
        "RULE/INTRINSIC/CapacityMeasurementStatusReasonRuleV1/V1",
        "RULE/INTRINSIC/CapacityMeasurementStatusReasonPolicyDefinitionV1/V1",
    ),
    (
        "RULE/INTRINSIC/CapacityMeasurementVocabularyDefinitionV1/V1",
        "RULE/INTRINSIC/TargetFieldRegistryV1/V1",
    ),
    (
        "RULE/INTRINSIC/CapacityMeasurementValueShapeDefinitionV1/V1",
        "RULE/INTRINSIC/TargetFieldRegistryV1/V1",
    ),
    (
        "RULE/INTRINSIC/CapacityMeasurementStatusReasonPolicyDefinitionV1/V1",
        "RULE/INTRINSIC/TargetFieldRegistryV1/V1",
    ),
    (
        "RULE/INTRINSIC/CapacityMeasurementTargetFieldDescriptorV1/V1",
        "RULE/INTRINSIC/TargetFieldRegistryV1/V1",
    ),
)


def _validate_literal_authority(value: dict[str, Any]) -> None:
    expected_keys = {
        "canonicalization_version",
        "component_status",
        "measurement_schema_version",
        "rule_literal_authority_version",
        "marker_contract",
        "operation_counter_schema",
        "target_field_registry",
        "selected_literal_canonical_sha256",
        "rule_literal_authority_sha256",
    }
    _require(set(value) == expected_keys, "literal-authority keys differ")
    _require(
        value["canonicalization_version"] == CANONICALIZATION_VERSION,
        "literal-authority canonicalization differs",
    )
    _require(
        value["measurement_schema_version"] == MEASUREMENT_SCHEMA_VERSION,
        "literal-authority schema version differs",
    )
    _require(
        value["component_status"] == "RULE_LITERAL_AUTHORITY_ONLY_NOT_FULL_REGISTRY",
        "literal-authority status differs",
    )
    selected = value["selected_literal_canonical_sha256"]
    _require(
        set(selected)
        == {
            "marker_contract",
            "operation_counter_schema",
            "target_field_registry",
        },
        "selected literal hash catalog differs",
    )
    for name in selected:
        _require(
            _sha256(_canonical_bytes(value[name])) == selected[name],
            f"selected literal hash differs for {name}",
        )
    payload = {
        key: item
        for key, item in value.items()
        if key != "rule_literal_authority_sha256"
    }
    _require(
        _semantic_id(
            "RiskYieldMMA2MStep2RuleLiteralAuthorityV1V4_9F_RawV8",
            payload,
        )
        == value["rule_literal_authority_sha256"],
        "literal-authority semantic ID differs",
    )
    marker = value["marker_contract"]
    _require(
        marker["marker_contract_id"]
        == "1e529cc6ced2f3a67cafca3ec2af5146322c73b89f9cd4385cbd7b72949132b4",
        "marker-contract identity differs",
    )
    expected_marker_literals = _marker_contract_literals()
    for name, expected in expected_marker_literals.items():
        _require(marker[name] == expected, f"marker-contract {name} differs")
    counter = value["operation_counter_schema"]
    _require(
        counter["counter_schema_id"]
        == "5181eb89788d511ffeb2ccc65264b81e9e0d3ae977043820524f8b08dfa58fc3",
        "counter-schema identity differs",
    )
    _require(
        counter["counter_field_count"] == 66
        and len(counter["ordered_counter_field_ids"]) == 66
        and len(counter["monotone_counter_field_ids"]) == 57,
        "counter-schema counts differ",
    )
    registry = value["target_field_registry"]
    _require(
        registry["target_field_registry_id"]
        == "ae01f3a8e53163eefdc77bb4a863710dc851aec22738719639a3c21fe683a618",
        "target-registry identity differs",
    )
    expected_counts = {
        "ordered_vocabulary_definitions": 25,
        "ordered_value_shape_definitions": 6,
        "ordered_value_constraint_definitions": 17,
        "ordered_cross_field_constraint_definitions": 1,
        "descriptors": 185,
    }
    _require(registry["field_count"] == 185, "target-registry count differs")
    for name, count in expected_counts.items():
        _require(len(registry[name]) == count, f"target-registry {name} differs")
    policy = registry["status_reason_policy_definition"]
    _require(
        len(policy["availability_state_rules"]) == 4
        and len(policy["reason_rules"]) == 26
        and len(policy["error_form_definitions"]) == 4,
        "status-reason policy counts differ",
    )
    _require(
        _sha256(_canonical_bytes(registry))
        == "1d68328b6b2245f21fcda85a396918dd664bf7c2b71bd1547c92235c0a2a2222",
        "target-registry canonical record hash differs",
    )


def _validate_dependency_headers(
    topology: dict[str, Any],
    scalar: dict[str, Any],
) -> None:
    _require(
        topology["component_status"] == "TOPOLOGY_ONLY_NOT_FULL_REGISTRY",
        "topology component status differs",
    )
    _require(
        topology["concrete_record_count"] == 49
        and topology["tagged_union_count"] == 3
        and topology["total_type_count"] == 52,
        "topology counts differ",
    )
    _require(
        scalar["component_status"] == "SCALAR_PATH_ONLY_NOT_FULL_REGISTRY",
        "scalar component status differs",
    )
    _require(
        scalar["value_schema_count"] == 200
        and scalar["member_path_assignment_count"] == 421,
        "scalar component counts differ",
    )
    schema_ids = {item["value_schema_id"] for item in scalar["ordered_value_schemas"]}
    _require(BOOLEAN_SCHEMA_ID in schema_ids, "unrestricted Boolean is absent")


def _dependency_edges() -> list[dict[str, str]]:
    return [
        {
            "predecessor_rule_id": predecessor,
            "successor_rule_id": successor,
        }
        for predecessor, successor in RULE_DEPENDENCY_EDGES
    ]


def build_ledger(
    topology: dict[str, Any],
    scalar: dict[str, Any],
    literals: dict[str, Any],
) -> dict[str, Any]:
    _validate_dependency_headers(topology, scalar)
    _validate_literal_authority(literals)
    schemas = SchemaCatalog(topology, scalar)
    intrinsic = _intrinsic_rules(schemas, literals)
    cross = _cross_rules(schemas)
    rules = intrinsic + cross
    _require(len(intrinsic) == 34, "intrinsic rule count differs")
    _require(len(cross) == 8, "cross rule count differs")
    _require(len(rules) == 42, "typed rule count differs")
    rule_by_id = {item["rule_id"]: item for item in rules}
    _require(len(rule_by_id) == 42, "rule symbolic IDs are not unique")
    attachments = _attachment_ledger(topology)
    attached_counter = Counter(
        rule_id
        for item in attachments
        for rule_id in item["ordered_intrinsic_rule_ids"]
    )
    attached_ids = set(attached_counter)
    _require(
        attached_ids == {item["rule_id"] for item in intrinsic},
        "intrinsic rule attachment closure differs",
    )
    _require(
        set(attached_counter.values()) == {1}
        and all(
            len(item["ordered_intrinsic_rule_ids"])
            == len(set(item["ordered_intrinsic_rule_ids"]))
            for item in attachments
        ),
        "intrinsic rule attachment multiplicity differs",
    )
    _require(
        len(attachments) == 49
        and [item["type_name"] for item in attachments]
        == [
            item["type_name"]
            for item in topology["type_descriptors"]
            if item["type_form"] == "RECORD"
        ],
        "intrinsic attachment row closure differs",
    )
    _require(
        set(CROSS_RULE_IDS) == {item["rule_id"] for item in cross},
        "cross rule application closure differs",
    )
    resolvers = _resolver_profiles()
    applications = _applications()
    application_rule_counter = Counter(item["rule_id"] for item in applications)
    application_rule_ids = set(application_rule_counter)
    _require(
        application_rule_ids == set(CROSS_RULE_IDS),
        "application rule closure differs",
    )
    _require(
        set(application_rule_counter.values()) == {1}
        and len({item["rule_application_id"] for item in applications})
        == len(applications)
        == 8,
        "application rule/identity multiplicity differs",
    )
    additive_ids = set(schemas.additive)
    member_ids = set(schemas.member_schemas)
    _require(additive_ids.isdisjoint(member_ids), "additive schemas overlap member set")
    _require(
        additive_ids <= schemas.used,
        "an additive rule schema is unused",
    )
    expression_count = sum(len(item["ordered_expression_nodes"]) for item in rules)
    payload = {
        "canonicalization_version": CANONICALIZATION_VERSION,
        "measurement_schema_version": MEASUREMENT_SCHEMA_VERSION,
        "component_status": COMPONENT_STATUS,
        "rule_application_ledger_version": LEDGER_VERSION,
        "dependency_sha256": {
            "topology_ledger": TOPOLOGY_SHA256,
            "scalar_path_ledger": SCALAR_SHA256,
            "rule_literal_authority": FROZEN_LITERAL_SHA256,
        },
        "concrete_attachment_count": len(attachments),
        "intrinsic_rule_count": len(intrinsic),
        "cross_rule_count": len(cross),
        "typed_rule_count": len(rules),
        "rule_application_descriptor_count": len(applications),
        "fixed_position_resolver_profile_count": len(resolvers),
        "member_value_schema_count": len(member_ids),
        "additive_rule_value_schema_count": len(additive_ids),
        "full_reachable_value_schema_count": len(member_ids | additive_ids),
        "total_expression_node_count": expression_count,
        "ordered_additive_rule_value_schemas": sorted(
            schemas.additive.values(),
            key=lambda item: item["value_schema_id"],
        ),
        "ordered_intrinsic_rule_attachments": attachments,
        "ordered_rule_dependency_edges": _dependency_edges(),
        "ordered_rule_descriptors": sorted(
            rules,
            key=lambda item: item["step2_cross_field_rule_descriptor_id"],
        ),
        "ordered_fixed_position_resolver_profiles": resolvers,
        "ordered_rule_application_descriptors": applications,
        "closure_evidence": {
            "additive_schema_ids_disjoint_from_member_schema_ids": True,
            "all_additive_rule_schemas_reachable": True,
            "all_intrinsic_rules_attached_exactly_once": True,
            "all_cross_rules_applied_exactly_once": True,
            "member_union_additive_equals_full_reachable_catalog": True,
            "union_nodes_remain_rule_attachment_free": True,
        },
    }
    return {
        **payload,
        "rule_application_component_sha256": _semantic_id(
            COMPONENT_DOMAIN,
            payload,
        ),
    }


def _index_unique(
    records: Any,
    *,
    key: str,
    label: str,
) -> dict[Any, dict[str, Any]]:
    _require(type(records) is list, f"{label} catalog is not an array")
    result: dict[Any, dict[str, Any]] = {}
    for record in records:
        _require(type(record) is dict and key in record, f"{label} row shape differs")
        identifier = record[key]
        _require(identifier not in result, f"duplicate {label} key {identifier!r}")
        result[identifier] = record
    return result


class StaticDescriptorValidator:
    """Independent static type and closure validator for a materialized ledger."""

    def __init__(
        self,
        *,
        topology: dict[str, Any],
        scalar: dict[str, Any],
        literals: dict[str, Any],
        ledger: dict[str, Any],
    ) -> None:
        self.topology = topology
        self.scalar = scalar
        self.literals = literals
        self.ledger = ledger
        _require(
            type(ledger) is dict and set(ledger) == COMPONENT_KEYS,
            "component root shape differs",
        )
        type_descriptors = topology["type_descriptors"]
        type_index = _index_unique(
            type_descriptors,
            key="type_name",
            label="topology type",
        )
        self.records = {
            name: item
            for name, item in type_index.items()
            if item.get("type_form") == "RECORD"
        }
        self.unions = {
            name: item
            for name, item in type_index.items()
            if item.get("type_form") == "TAGGED_UNION"
        }
        member_schemas = scalar["ordered_value_schemas"]
        additive = ledger["ordered_additive_rule_value_schemas"]
        member_schema_index = _index_unique(
            member_schemas,
            key="value_schema_id",
            label="member value schema",
        )
        additive_schema_index = _index_unique(
            additive,
            key="value_schema_id",
            label="additive value schema",
        )
        self.member_schema_ids = set(member_schema_index)
        self.additive_schema_ids = set(additive_schema_index)
        _require(
            self.member_schema_ids.isdisjoint(self.additive_schema_ids),
            "static additive/member schema sets overlap",
        )
        self.schemas = {**member_schema_index, **additive_schema_index}
        assignments = scalar["ordered_member_path_assignments"]
        _require(type(assignments) is list, "member-path assignment catalog differs")
        self.assignments: dict[tuple[str, tuple[str, ...]], str] = {}
        for item in assignments:
            _require(
                type(item) is dict and type(item.get("typed_member_path")) is list,
                "member-path assignment row differs",
            )
            key = (
                item["source_type_name"],
                tuple(item["typed_member_path"]),
            )
            _require(key not in self.assignments, "duplicate member-path assignment")
            self.assignments[key] = item["value_schema_id"]
        self.languages = _index_unique(
            scalar["ordered_text_language_descriptors"],
            key="text_language_id",
            label="text language",
        )
        self.dfas = _index_unique(
            scalar["ordered_ascii_dfa_descriptors"],
            key="ascii_dfa_id",
            label="ASCII DFA",
        )
        self.profiles = _index_unique(
            scalar["ordered_unicode_identifier_profiles"],
            key="unicode_identifier_profile_id",
            label="Unicode profile",
        )
        self.rules = _index_unique(
            ledger["ordered_rule_descriptors"],
            key="rule_id",
            label="rule descriptor",
        )
        _require(
            all(
                "step2_cross_field_rule_descriptor_id" in item
                for item in ledger["ordered_rule_descriptors"]
            )
            and len(
                {
                    item["step2_cross_field_rule_descriptor_id"]
                    for item in ledger["ordered_rule_descriptors"]
                }
            )
            == len(self.rules),
            "duplicate terminal rule descriptor ID",
        )
        attachment_rows = ledger["ordered_intrinsic_rule_attachments"]
        attachment_index = _index_unique(
            attachment_rows,
            key="type_name",
            label="intrinsic attachment",
        )
        _require(
            all(
                type(item.get("ordered_intrinsic_rule_ids")) is list
                for item in attachment_rows
            ),
            "intrinsic attachment rule-list shape differs",
        )
        self.attachments = {
            type_name: tuple(item["ordered_intrinsic_rule_ids"])
            for type_name, item in attachment_index.items()
        }
        self.resolvers = _index_unique(
            ledger["ordered_fixed_position_resolver_profiles"],
            key="fixed_position_resolver_profile_id",
            label="resolver profile",
        )
        self._current_rule_id: str | None = None
        self._literal_record_references: list[tuple[str, str]] = []

    def validate(self) -> None:
        self._validate_schema_catalog()
        self._validate_attachments()
        for rule in self.rules.values():
            self._validate_rule(rule)
        self._validate_rule_dependency_dag()
        self._validate_resolvers()
        self._validate_applications()
        self._validate_literal_selection()
        self._validate_component_identity()

    def _validate_schema_catalog(self) -> None:
        for identifier, schema in self.schemas.items():
            _require(set(schema) == VALUE_SCHEMA_KEYS, "value-schema shape differs")
            payload = {
                key: value for key, value in schema.items() if key != "value_schema_id"
            }
            _require(
                _semantic_id(VALUE_SCHEMA_DOMAIN, payload) == identifier,
                f"value-schema semantic ID differs: {identifier}",
            )
            _require(type(schema["nullable"]) is bool, "schema nullability differs")
            kind = schema["schema_kind"]
            _require(
                kind
                in {"EXACT_BOOLEAN", "SAFE_INTEGER", "TEXT", "ARRAY", "OBJECT_REF"},
                f"unknown schema kind {kind}",
            )
            if kind == "EXACT_BOOLEAN":
                _require(
                    schema["boolean_literal"] in {None, True, False},
                    "Boolean literal differs",
                )
            elif kind == "SAFE_INTEGER":
                minimum = schema["integer_minimum"]
                maximum = schema["integer_maximum"]
                _require(
                    type(minimum) is int
                    and type(maximum) is int
                    and 0 <= minimum <= maximum <= SAFE_UINT_MAX,
                    "safe-integer schema bounds differ",
                )
            elif kind == "TEXT":
                _require(
                    schema["text_language_id"] in self.languages,
                    "text schema language is unresolved",
                )
            elif kind == "ARRAY":
                minimum = schema["array_minimum_items"]
                maximum = schema["array_maximum_items"]
                _require(
                    type(minimum) is int
                    and type(maximum) is int
                    and 0 <= minimum <= maximum <= SAFE_UINT_MAX,
                    "array schema bounds differ",
                )
                _require(
                    schema["array_item_value_schema_id"] in self.schemas,
                    "array item schema is unresolved",
                )
            else:
                _require(
                    schema["referenced_type_name"] in self.records
                    or schema["referenced_type_name"] in self.unions,
                    "object-ref target is unresolved",
                )
            allowed_nonnull = {
                "EXACT_BOOLEAN": {"boolean_literal"},
                "SAFE_INTEGER": {"integer_minimum", "integer_maximum"},
                "TEXT": {"text_language_id"},
                "ARRAY": {
                    "array_minimum_items",
                    "array_maximum_items",
                    "array_item_value_schema_id",
                },
                "OBJECT_REF": {"referenced_type_name"},
            }[kind]
            constraint_names = {
                "boolean_literal",
                "integer_minimum",
                "integer_maximum",
                "text_language_id",
                "array_minimum_items",
                "array_maximum_items",
                "array_item_value_schema_id",
                "referenced_type_name",
            }
            for name in constraint_names - allowed_nonnull:
                _require(schema[name] is None, f"{kind} carries foreign {name}")

    def _validate_attachments(self) -> None:
        _require(len(self.attachments) == 49, "attachment count differs")
        rows = self.ledger["ordered_intrinsic_rule_attachments"]
        _require(
            all(
                set(item) == ATTACHMENT_KEYS
                and type(item["concrete_type_position"]) is int
                and type(item["ordered_intrinsic_rule_ids"]) is list
                and len(item["ordered_intrinsic_rule_ids"])
                == len(set(item["ordered_intrinsic_rule_ids"]))
                for item in rows
            ),
            "intrinsic attachment row shape/multiplicity differs",
        )
        _require(
            [item["concrete_type_position"] for item in rows] == list(range(1, 50)),
            "intrinsic attachment positions differ",
        )
        attached = {
            rule_id for rule_ids in self.attachments.values() for rule_id in rule_ids
        }
        intrinsic = {
            rule_id
            for rule_id, rule in self.rules.items()
            if rule["rule_scope"] == "INTRINSIC_RECORD"
        }
        cross = {
            rule_id
            for rule_id, rule in self.rules.items()
            if rule["rule_scope"] == "CROSS_RECORD"
        }
        _require(attached == intrinsic, "intrinsic attachment closure differs")
        _require(attached.isdisjoint(cross), "cross rule is intrinsically attached")
        for type_name, rule_ids in self.attachments.items():
            _require(type_name in self.records, "attachment type is unresolved")
            _require(len(rule_ids) <= 1, "multiple intrinsic rules attached")
            for rule_id in rule_ids:
                rule = self.rules[rule_id]
                binding = rule["ordered_rule_input_bindings"][0]
                _require(
                    binding["expected_type_name"] == type_name,
                    "intrinsic attachment binding type differs",
                )

    def _resolve_path(self, type_name: str, path: Sequence[str]) -> str:
        _require(path, "empty member path cannot be resolved")
        current = type_name
        for index, segment in enumerate(path):
            _require(current in self.records, f"path enters non-record {current}")
            descriptor = self.records[current]
            member_names = {
                item["member_name"] for item in descriptor["member_topology"]
            }
            _require(segment in member_names, f"unresolved path {current}.{segment}")
            schema_id = self.assignments.get((current, (segment,)))
            _require(
                schema_id in self.schemas, f"missing path schema {current}.{segment}"
            )
            if index == len(path) - 1:
                return schema_id
            schema = self.schemas[schema_id]
            _require(
                schema["schema_kind"] == "OBJECT_REF"
                and not schema["nullable"]
                and schema["referenced_type_name"] in self.records,
                f"path crosses non-record {current}.{segment}",
            )
            current = schema["referenced_type_name"]
        raise AssertionError("unreachable")

    def _schema_type(self, schema_id: str) -> tuple[str, str]:
        _require(schema_id in self.schemas, f"unresolved schema {schema_id}")
        return ("VALUE_SCHEMA", schema_id)

    def _is_boolean_type(self, node_type: tuple[str, str | None]) -> bool:
        return node_type == ("VALUE_SCHEMA", BOOLEAN_SCHEMA_ID)

    def _schema_for_type(
        self,
        node_type: tuple[str, str | None],
    ) -> dict[str, Any]:
        _require(node_type[0] == "VALUE_SCHEMA", "internal value has no schema")
        identifier = node_type[1]
        _require(identifier in self.schemas, "node schema is unresolved")
        return self.schemas[identifier]

    def _same_nonnull_base(self, first: dict[str, Any], second: dict[str, Any]) -> bool:
        first_payload = {
            key: value
            for key, value in first.items()
            if key not in {"value_schema_id", "nullable"}
        }
        second_payload = {
            key: value
            for key, value in second.items()
            if key not in {"value_schema_id", "nullable"}
        }
        return first_payload == second_payload

    def _is_ordered_scalar(self, schema: dict[str, Any]) -> bool:
        if schema["nullable"]:
            return False
        if schema["schema_kind"] == "SAFE_INTEGER":
            return True
        if schema["schema_kind"] == "TEXT":
            return (
                self.languages[schema["text_language_id"]]["ordering_semantics"]
                == "UNICODE_SCALAR_LEXICOGRAPHIC"
            )
        return False

    def _binding_type(self, binding: dict[str, Any]) -> tuple[str, str]:
        schema_id = binding["expected_value_schema_id"]
        schema = self.schemas.get(schema_id)
        _require(schema is not None, "binding schema is unresolved")
        kind = binding["binding_kind"]
        type_name = binding["expected_type_name"]
        if kind == "RECORD":
            _require(
                schema["schema_kind"] == "OBJECT_REF"
                and not schema["nullable"]
                and schema["referenced_type_name"] == type_name
                and type_name in self.records,
                "RECORD binding schema differs",
            )
        elif kind == "SAFE_UINT":
            _require(
                type_name is None
                and schema["schema_kind"] == "SAFE_INTEGER"
                and not schema["nullable"],
                "SAFE_UINT binding schema differs",
            )
        elif kind == "FIXED_RECORD_SEQUENCE":
            _require(
                schema["schema_kind"] == "ARRAY" and not schema["nullable"],
                "FIXED_RECORD_SEQUENCE binding array schema differs",
            )
            item_schema_id = schema["array_item_value_schema_id"]
            _require(
                item_schema_id in self.schemas,
                "FIXED_RECORD_SEQUENCE item schema is unresolved",
            )
            item = self.schemas[item_schema_id]
            _require(
                item["schema_kind"] == "OBJECT_REF"
                and not item["nullable"]
                and item["referenced_type_name"] == type_name
                and type_name in self.records,
                "FIXED_RECORD_SEQUENCE binding schema differs",
            )
        elif kind == "OPTIONAL_FIXED_RECORD":
            _require(
                schema["schema_kind"] == "OBJECT_REF"
                and schema["nullable"]
                and schema["referenced_type_name"] == type_name
                and type_name in self.records,
                "OPTIONAL_FIXED_RECORD binding schema differs",
            )
        else:
            raise ValidationError(f"unknown binding kind {kind}")
        return self._schema_type(schema_id)

    def _validate_rule(self, rule: dict[str, Any]) -> None:
        self._current_rule_id = rule["rule_id"]
        _require(set(rule) == RULE_KEYS, "rule descriptor shape differs")
        payload = {
            key: value
            for key, value in rule.items()
            if key != "step2_cross_field_rule_descriptor_id"
        }
        _require(
            _semantic_id(RULE_DOMAIN, payload)
            == rule["step2_cross_field_rule_descriptor_id"],
            f"rule descriptor ID differs: {rule['rule_id']}",
        )
        _require(rule["rule_version"] == RULE_VERSION, "rule version differs")
        bindings = rule["ordered_rule_input_bindings"]
        _require(
            type(bindings) is list
            and all(set(item) == RULE_BINDING_KEYS for item in bindings),
            "rule binding shape differs",
        )
        _require(
            len({item["binding_name"] for item in bindings}) == len(bindings),
            "rule binding names are not unique",
        )
        binding_types = {
            item["binding_name"]: self._binding_type(item) for item in bindings
        }
        if rule["rule_scope"] == "INTRINSIC_RECORD":
            _require(
                len(bindings) == 1
                and bindings[0]["binding_name"] == "self"
                and bindings[0]["binding_kind"] == "RECORD",
                "intrinsic binding shape differs",
            )
        else:
            _require(
                rule["rule_scope"] == "CROSS_RECORD" and len(bindings) >= 2,
                "cross rule binding shape differs",
            )
        nodes = rule["ordered_expression_nodes"]
        _require(
            type(nodes) is list
            and all(set(item) == EXPRESSION_NODE_KEYS for item in nodes),
            "expression-node shape differs",
        )
        _require(
            rule["maximum_expression_nodes"] == len(nodes)
            and 1 <= len(nodes) <= MAXIMUM_EXPRESSION_NODES,
            "rule expression bound differs",
        )
        _require(
            rule["root_expression_position"] == len(nodes),
            "rule root is not the final node",
        )
        node_types: dict[int, tuple[str, str | None]] = {}
        depths: dict[int, int] = {}
        for position, node in enumerate(nodes, 1):
            _require(
                node["expression_position"] == position,
                "expression positions are not contiguous",
            )
            operator = node["operator"]
            _require(operator in OPERATOR_ARITY, f"unknown operator {operator}")
            operands = node["ordered_operand_positions"]
            _require(
                len(operands) == OPERATOR_ARITY[operator]
                and all(
                    type(item) is int and 1 <= item < position for item in operands
                ),
                f"{operator} operand positions differ",
            )
            actual_type = (
                (
                    "VALUE_SCHEMA",
                    node["result_value_schema_id"],
                )
                if node["result_type_kind"] == "VALUE_SCHEMA"
                else (node["result_type_kind"], None)
            )
            if actual_type[0] == "VALUE_SCHEMA":
                _require(
                    actual_type[1] in self.schemas, "node result schema unresolved"
                )
            else:
                _require(
                    actual_type[0]
                    in {"INTERNAL_BYTES", "INTERNAL_UINT128", "INTERNAL_INT128"}
                    and node["result_value_schema_id"] is None,
                    "internal node result differs",
                )
            operand_types = [node_types[item] for item in operands]
            self._validate_operator(
                rule=rule,
                node=node,
                actual_type=actual_type,
                operand_types=operand_types,
                binding_types=binding_types,
            )
            node_types[position] = actual_type
            depths[position] = 1 + max((depths[item] for item in operands), default=0)
        root = rule["root_expression_position"]
        _require(self._is_boolean_type(node_types[root]), "rule root type differs")
        _require(max(depths.values()) <= 16, "rule expression depth exceeds 16")
        reachable: set[int] = set()
        stack = [root]
        while stack:
            position = stack.pop()
            if position in reachable:
                continue
            reachable.add(position)
            stack.extend(nodes[position - 1]["ordered_operand_positions"])
        _require(
            reachable == set(range(1, len(nodes) + 1)),
            "rule contains an unreachable expression node",
        )
        used_bindings = {
            node["input_binding_name"]
            for node in nodes
            if node["operator"] == "INPUT_PATH"
        }
        unused = set(binding_types) - used_bindings
        # This ordinal is application-coordinate evidence, not predicate input.
        # No other rule binding receives an unused-binding exception.
        permitted_unused = (
            {"observation_ordinal"}
            if rule["rule_id"] == "RULE/CROSS/V2_ROOT_OBSERVATION_MEMBERSHIP_V1"
            else set()
        )
        _require(
            unused == permitted_unused
            and (
                not permitted_unused
                or next(
                    item
                    for item in bindings
                    if item["binding_name"] == "observation_ordinal"
                )["binding_kind"]
                == "SAFE_UINT"
            ),
            "unused rule binding differs from the ordinal-evidence exception",
        )
        self._current_rule_id = None

    def _validate_operator(
        self,
        *,
        rule: dict[str, Any],
        node: dict[str, Any],
        actual_type: tuple[str, str | None],
        operand_types: list[tuple[str, str | None]],
        binding_types: dict[str, tuple[str, str]],
    ) -> None:
        operator = node["operator"]
        path_operators = {
            "INPUT_PATH",
            "ARRAY_PROJECT_REQUIRED_MEMBER",
            "ARRAY_FIND_UNIQUE_OBJECT_BY_MEMBER",
            "OBJECT_MEMBER",
        }
        if operator == "INPUT_PATH":
            binding_name = node["input_binding_name"]
            _require(
                binding_name in binding_types
                and node["literal_value_schema_id"] is None
                and node["literal_value"] is None,
                "INPUT_PATH metadata/binding differs",
            )
            path = node["typed_member_path"]
            if path:
                binding = next(
                    item
                    for item in rule["ordered_rule_input_bindings"]
                    if item["binding_name"] == binding_name
                )
                _require(binding["binding_kind"] == "RECORD", "sequence path differs")
                expected = self._schema_type(
                    self._resolve_path(binding["expected_type_name"], path)
                )
            else:
                expected = binding_types[binding_name]
            _require(actual_type == expected, "INPUT_PATH result type differs")
        elif operator == "LITERAL":
            _require(
                node["input_binding_name"] is None
                and not node["typed_member_path"]
                and node["literal_value_schema_id"] == actual_type[1],
                "literal schema/result differ",
            )
            self._validate_literal(actual_type[1], node["literal_value"], set())
        else:
            _require(node["input_binding_name"] is None, f"{operator} has binding")
            _require(
                node["literal_value_schema_id"] is None
                and node["literal_value"] is None,
                f"{operator} carries literal fields",
            )
        if operator not in path_operators:
            _require(not node["typed_member_path"], f"{operator} carries a path")
        if operator not in {"INPUT_PATH", "LITERAL"}:
            self._validate_typed_operator(
                operator,
                actual_type,
                operand_types,
                node["typed_member_path"],
            )

    def _require_boolean_result(self, actual_type: tuple[str, str | None]) -> None:
        _require(self._is_boolean_type(actual_type), "operator result is not Boolean")

    def _object_target(self, node_type: tuple[str, str | None]) -> str:
        schema = self._schema_for_type(node_type)
        _require(
            schema["schema_kind"] == "OBJECT_REF" and not schema["nullable"],
            "operand is not a required object",
        )
        return schema["referenced_type_name"]

    def _array_schema(self, node_type: tuple[str, str | None]) -> dict[str, Any]:
        schema = self._schema_for_type(node_type)
        _require(
            schema["schema_kind"] == "ARRAY" and not schema["nullable"],
            "operand is not a required array",
        )
        return schema

    def _safe_schema(self, node_type: tuple[str, str | None]) -> dict[str, Any]:
        schema = self._schema_for_type(node_type)
        _require(
            schema["schema_kind"] == "SAFE_INTEGER" and not schema["nullable"],
            "operand is not a non-null safe integer",
        )
        return schema

    def _text_builtin(
        self,
        node_type: tuple[str, str | None],
        built_in: str,
    ) -> bool:
        if node_type[0] != "VALUE_SCHEMA":
            return False
        schema = self.schemas[node_type[1]]
        if schema["schema_kind"] != "TEXT" or schema["nullable"]:
            return False
        language = self.languages[schema["text_language_id"]]
        return (
            language["language_kind"] == "BUILTIN"
            and language["built_in_language_kind"] == built_in
        )

    def _validate_typed_operator(
        self,
        operator: str,
        actual_type: tuple[str, str | None],
        operands: list[tuple[str, str | None]],
        path: Sequence[str],
    ) -> None:
        boolean_unary = {"NOT"}
        boolean_binary = {"AND", "OR", "IMPLIES"}
        comparisons = {"EQ", "NE"}
        ordered_comparisons = {"LT", "LE", "GT", "GE"}
        if operator == "IS_NULL":
            schema = self._schema_for_type(operands[0])
            _require(schema["nullable"], "IS_NULL operand is non-null")
            self._require_boolean_result(actual_type)
        elif operator in boolean_unary:
            _require(self._is_boolean_type(operands[0]), "NOT operand differs")
            self._require_boolean_result(actual_type)
        elif operator in boolean_binary:
            _require(
                all(self._is_boolean_type(item) for item in operands),
                f"{operator} operands differ",
            )
            self._require_boolean_result(actual_type)
        elif operator in comparisons:
            _require(operands[0] == operands[1], f"{operator} types differ")
            self._require_boolean_result(actual_type)
        elif operator in ordered_comparisons:
            _require(operands[0] == operands[1], f"{operator} types differ")
            if operands[0][0] == "VALUE_SCHEMA":
                _require(
                    self._is_ordered_scalar(self.schemas[operands[0][1]]),
                    f"{operator} operand is not ordered",
                )
            else:
                _require(
                    operands[0][0] in {"INTERNAL_UINT128", "INTERNAL_INT128"},
                    f"{operator} internal type differs",
                )
            self._require_boolean_result(actual_type)
        elif operator == "PRESENT_EQ":
            first = self._schema_for_type(operands[0])
            second = self._schema_for_type(operands[1])
            _require(
                first["nullable"]
                and not second["nullable"]
                and first["schema_kind"] in {"EXACT_BOOLEAN", "SAFE_INTEGER", "TEXT"}
                and self._same_nonnull_base(first, second),
                "PRESENT_EQ operand schemas differ",
            )
            self._require_boolean_result(actual_type)
        elif operator == "PRESENT_LE":
            _require(operands[0] == operands[1], "PRESENT_LE schemas differ")
            schema = self._schema_for_type(operands[0])
            _require(
                schema["nullable"]
                and (
                    schema["schema_kind"] == "SAFE_INTEGER"
                    or (
                        schema["schema_kind"] == "TEXT"
                        and self.languages[schema["text_language_id"]][
                            "ordering_semantics"
                        ]
                        == "UNICODE_SCALAR_LEXICOGRAPHIC"
                    )
                ),
                "PRESENT_LE operand is not nullable ordered scalar",
            )
            self._require_boolean_result(actual_type)
        elif operator in {
            "SAFE_ADD",
            "SAFE_MULTIPLY",
            "SAFE_FLOOR_DIVIDE",
            "SAFE_CEIL_DIVIDE",
        }:
            self._safe_schema(operands[0])
            self._safe_schema(operands[1])
            self._safe_schema(actual_type)
        elif operator == "ARRAY_LENGTH":
            array = self._array_schema(operands[0])
            result = self._safe_schema(actual_type)
            _require(
                result["integer_minimum"] <= array["array_minimum_items"]
                and result["integer_maximum"] >= array["array_maximum_items"],
                "ARRAY_LENGTH result range is too narrow",
            )
        elif operator == "ARRAY_UNIQUE":
            self._array_schema(operands[0])
            self._require_boolean_result(actual_type)
        elif operator == "ARRAY_STRICT_ASCENDING":
            array = self._array_schema(operands[0])
            item = self.schemas[array["array_item_value_schema_id"]]
            _require(
                self._is_ordered_scalar(item),
                "ARRAY_STRICT_ASCENDING item is not ordered",
            )
            self._require_boolean_result(actual_type)
        elif operator == "ARRAY_POSITIONAL_EQUAL":
            _require(
                operands[0] == operands[1],
                "ARRAY_POSITIONAL_EQUAL schemas differ",
            )
            self._array_schema(operands[0])
            self._require_boolean_result(actual_type)
        elif operator == "ARRAY_PROJECT_REQUIRED_MEMBER":
            array = self._array_schema(operands[0])
            item = self.schemas[array["array_item_value_schema_id"]]
            _require(
                item["schema_kind"] == "OBJECT_REF" and not item["nullable"] and path,
                "projection source/path differs",
            )
            projected_id = self._resolve_path(item["referenced_type_name"], path)
            result = self._array_schema(actual_type)
            _require(
                result["array_minimum_items"] == array["array_minimum_items"]
                and result["array_maximum_items"] == array["array_maximum_items"]
                and result["array_item_value_schema_id"] == projected_id,
                "projection result schema differs",
            )
        elif operator == "ARRAY_CONTAINS":
            array = self._array_schema(operands[0])
            _require(
                operands[1] == self._schema_type(array["array_item_value_schema_id"]),
                "ARRAY_CONTAINS item schema differs",
            )
            self._require_boolean_result(actual_type)
        elif operator == "ARRAY_FIND_UNIQUE_OBJECT_BY_MEMBER":
            array = self._array_schema(operands[0])
            item = self.schemas[array["array_item_value_schema_id"]]
            _require(
                item["schema_kind"] == "OBJECT_REF" and not item["nullable"] and path,
                "ARRAY_FIND source/path differs",
            )
            key_id = self._resolve_path(item["referenced_type_name"], path)
            _require(
                operands[1] == self._schema_type(key_id)
                and actual_type
                == self._schema_type(array["array_item_value_schema_id"]),
                "ARRAY_FIND key/result differs",
            )
        elif operator == "OBJECT_MEMBER":
            target = self._object_target(operands[0])
            _require(path, "OBJECT_MEMBER path is empty")
            _require(
                actual_type == self._schema_type(self._resolve_path(target, path)),
                "OBJECT_MEMBER result differs",
            )
        elif operator == "TIMESTAMP_TO_EPOCH_MICROSECONDS":
            _require(
                self._text_builtin(operands[0], "RFC3339_UTC")
                and actual_type == ("INTERNAL_INT128", None),
                "timestamp conversion types differ",
            )
        elif operator == "UINT128_PARSE":
            _require(
                self._text_builtin(operands[0], "UINT128_DECIMAL")
                and actual_type == ("INTERNAL_UINT128", None),
                "uint128 parse types differ",
            )
        elif operator == "SAFE_UINT_TO_INTERNAL_UINT128":
            self._safe_schema(operands[0])
            _require(
                actual_type == ("INTERNAL_UINT128", None),
                "safe-uint widening result differs",
            )
        elif operator in {"UINT128_ADD", "UINT128_MULTIPLY"}:
            _require(
                operands
                == [
                    ("INTERNAL_UINT128", None),
                    ("INTERNAL_UINT128", None),
                ]
                and actual_type == ("INTERNAL_UINT128", None),
                f"{operator} types differ",
            )
        elif operator == "BASE64_DECODE":
            _require(
                self._text_builtin(operands[0], "CANONICAL_BASE64")
                and actual_type == ("INTERNAL_BYTES", None),
                "BASE64_DECODE types differ",
            )
        elif operator == "BASE64_ARRAY_DECODE_CONCAT":
            array = self._array_schema(operands[0])
            _require(
                self._text_builtin(
                    self._schema_type(array["array_item_value_schema_id"]),
                    "CANONICAL_BASE64",
                ),
                "BASE64 array item differs",
            )
            self._safe_schema(operands[1])
            _require(
                actual_type == ("INTERNAL_BYTES", None),
                "BASE64 concat result differs",
            )
        elif operator == "INTERNAL_BYTES_LENGTH":
            _require(
                operands[0] == ("INTERNAL_BYTES", None),
                "byte length operand differs",
            )
            self._safe_schema(actual_type)
        elif operator == "SHA256_BYTES":
            _require(
                operands[0] == ("INTERNAL_BYTES", None)
                and self._text_builtin(actual_type, "LOWERCASE_SHA256"),
                "SHA256_BYTES types differ",
            )
        elif operator == "RAW_INGRESS_BATCH_ID_RECOMPUTES":
            _require(
                operands[0]
                == self._schema_type(
                    self._resolve_path(
                        "CapacityMeasurementIngressOperationSpecV2",
                        ("ordered_input_chunks_base64",),
                    )
                )
                and operands[1]
                == self._schema_type(
                    self._resolve_path(
                        "CapacityMeasurementIngressOperationSpecV2",
                        ("raw_ingress_batch_sha256",),
                    )
                ),
                "raw-ingress recomputation operands differ",
            )
            self._require_boolean_result(actual_type)
        elif operator == "RFC6455_CLOSE_PAYLOAD_VALID":
            _require(
                operands[0]
                == self._schema_type(
                    self._resolve_path(
                        "CapacityMeasurementLogicalOutputFrameV1",
                        ("opcode",),
                    )
                )
                and operands[1] == ("INTERNAL_BYTES", None),
                "RFC6455 operands differ",
            )
            self._require_boolean_result(actual_type)
        elif operator == "FIELD_LAYER_EQUALS_UPPERCASE_FIELD_PREFIX":
            _require(
                operands
                == [
                    self._schema_type(
                        self._resolve_path(
                            "CapacityMeasurementTargetFieldDescriptorV1",
                            ("layer",),
                        )
                    ),
                    self._schema_type(
                        self._resolve_path(
                            "CapacityMeasurementTargetFieldDescriptorV1",
                            ("field_id",),
                        )
                    ),
                ],
                "field-layer operands differ",
            )
            self._require_boolean_result(actual_type)
        elif operator == "SEMANTIC_ID_RECOMPUTES":
            target = self._object_target(operands[0])
            _require(
                target in self.records,
                "semantic-ID recomputation target is not concrete",
            )
            descriptor = self.records[target]
            _require(
                descriptor["type_role"] == "STANDALONE"
                and type(descriptor["described_record_domain"]) is str
                and bool(descriptor["described_record_domain"])
                and type(descriptor["identity_field"]) is str
                and bool(descriptor["identity_field"])
                and type(descriptor["identity_payload_member_order"]) is list
                and bool(descriptor["identity_payload_member_order"])
                and descriptor["identity_field"]
                in {item["member_name"] for item in descriptor["member_topology"]}
                and all(
                    type(item) is str
                    and item
                    and item
                    in {
                        member["member_name"]
                        for member in descriptor["member_topology"]
                    }
                    for item in descriptor["identity_payload_member_order"]
                )
                and self._text_builtin(operands[1], "LOWERCASE_SHA256"),
                "semantic-ID recomputation operands differ",
            )
            identity_schema_id = self._resolve_path(
                target,
                (descriptor["identity_field"],),
            )
            _require(
                operands[1] == self._schema_type(identity_schema_id),
                "semantic-ID identity schema differs",
            )
            self._require_boolean_result(actual_type)
        elif operator == "CANONICAL_BYTES_SATISFY_BOUND":
            target = self._object_target(operands[0])
            _require(
                target in self.records,
                "canonical byte-bound target is not concrete",
            )
            descriptor = self.records[target]
            relation = descriptor["codec_byte_bound_relation"]
            limit = descriptor["codec_octet_limit"]
            _require(
                relation in {"LE", "LT"}
                and type(limit) is int
                and 1 <= limit <= SAFE_UINT_MAX
                and type(descriptor["codec_bound_inclusive"]) is bool
                and descriptor["codec_bound_inclusive"] == (relation == "LE"),
                "canonical byte-bound contract differs",
            )
            self._require_boolean_result(actual_type)
        elif operator == "CHECKPOINT_SELECTOR_INTRINSIC_VALID":
            _require(
                self._object_target(operands[0]) == "CheckpointSelectorV1",
                "selector intrinsic operand differs",
            )
            self._require_boolean_result(actual_type)
        elif operator == "CHECKPOINT_SELECTOR_MARKER_CONTRACT_ADMITTED":
            _require(
                self._object_target(operands[0]) == "CheckpointSelectorV1"
                and self._object_target(operands[1]) == "MarkerContractV1",
                "selector/marker operands differ",
            )
            self._require_boolean_result(actual_type)
        elif operator == "FIELD_OBSERVATION_INTRINSIC_VALID":
            _require(
                self._object_target(operands[0]) == "TargetFieldObservationV1",
                "field intrinsic operand differs",
            )
            self._require_boolean_result(actual_type)
        elif operator == "FIELD_OBSERVATION_SATISFIES_DESCRIPTOR_POLICY":
            _require(
                self._object_target(operands[0]) == "TargetFieldObservationV1"
                and self._object_target(operands[1])
                == "CapacityMeasurementTargetFieldDescriptorV1"
                and self._object_target(operands[2]) == "TargetFieldRegistryV1",
                "field policy operands differ",
            )
            self._require_boolean_result(actual_type)
        elif operator == "V2_FIELD_OBSERVATION_CONTEXT_VALID":
            _require(
                self._object_target(operands[0]) == "TargetFieldObservationV1"
                and self._object_target(operands[1])
                == "CapacityMeasurementTargetFieldDescriptorV1"
                and self._object_target(operands[2]) == "TargetFieldRegistryV1"
                and self._object_target(operands[3]) == "TargetObservationContextV2",
                "V2 field context object operands differ",
            )
            ordinal = self._safe_schema(operands[4])
            _require(
                ordinal["integer_minimum"] == 0 and ordinal["integer_maximum"] == 184,
                "V2 field ordinal schema differs",
            )
            self._require_boolean_result(actual_type)
        elif operator == "SOURCE_ERROR_DETAIL_ID_RECOMPUTES_FROM_FIELD":
            _require(
                self._object_target(operands[0]) == "TargetFieldObservationV1",
                "source-error operand differs",
            )
            self._require_boolean_result(actual_type)
        elif operator == "TARGET_VALUE_SATISFIES_DESCRIPTOR":
            _require(
                self._object_target(operands[0]) == "TargetFieldObservationV1"
                and self._object_target(operands[1])
                == "CapacityMeasurementTargetFieldDescriptorV1"
                and self._object_target(operands[2]) == "TargetFieldRegistryV1",
                "target-value operands differ",
            )
            self._require_boolean_result(actual_type)
        elif operator == "A1_FIFO_FIELDS_VALID":
            _require(
                operands[0]
                == self._schema_type(
                    self._resolve_path(
                        "TargetObservationV2",
                        ("field_observations",),
                    )
                )
                and self._object_target(operands[1]) == "TargetFieldRegistryV1",
                "A1 FIFO operands differ",
            )
            self._require_boolean_result(actual_type)
        elif operator == "BITMAP_NULLABILITY_MATCHES":
            _require(
                operands
                == [
                    self._schema_type(
                        self._resolve_path(
                            "OperationCounterSnapshotV1",
                            ("availability_bitmap",),
                        )
                    ),
                    self._schema_type(
                        self._resolve_path(
                            "OperationCounterSnapshotV1",
                            ("values",),
                        )
                    ),
                ],
                "bitmap/nullability operands differ",
            )
            self._require_boolean_result(actual_type)
        elif operator == "V2_ROOT_SEQUENCE_SELECTOR_VALID":
            _require(
                self._object_target(operands[0]) == "TargetObservationRootV2",
                "V2 root operand differs",
            )
            observations = self._array_schema(operands[1])
            item = self.schemas[observations["array_item_value_schema_id"]]
            selector = self._schema_for_type(operands[2])
            _require(
                observations["array_minimum_items"] == 1
                and observations["array_maximum_items"] == 67
                and item["schema_kind"] == "OBJECT_REF"
                and not item["nullable"]
                and item["referenced_type_name"] == "TargetObservationV2"
                and selector["schema_kind"] == "OBJECT_REF"
                and selector["nullable"]
                and selector["referenced_type_name"] == "CheckpointSelectorV1",
                "V2 root sequence/selector operands differ",
            )
            self._require_boolean_result(actual_type)
        elif operator == "OPERATION_RESULT_MATCHES_SIGNED_SPEC":
            _require(
                self._object_target(operands[0])
                == "CapacityMeasurementOperationResultEvidence"
                and self._object_target(operands[1])
                == "CapacityMeasurementOperationSpec",
                "operation result/spec operands differ",
            )
            self._require_boolean_result(actual_type)
        else:
            raise ValidationError(f"operator type validator missing {operator}")

    def _validate_literal(
        self,
        schema_id: str | None,
        value: Any,
        visiting: set[str],
    ) -> None:
        _require(schema_id in self.schemas, "literal schema is unresolved")
        schema = self.schemas[schema_id]
        if value is None:
            _require(schema["nullable"], "null literal uses a non-null schema")
            return
        _require(schema_id not in visiting, "literal value-schema cycle detected")
        active = {*visiting, schema_id}
        kind = schema["schema_kind"]
        if kind == "EXACT_BOOLEAN":
            _require(type(value) is bool, "Boolean literal is not exact Boolean")
            exact = schema["boolean_literal"]
            _require(
                exact is None or value is exact,
                "Boolean literal differs from exact schema",
            )
        elif kind == "SAFE_INTEGER":
            _require(
                type(value) is int
                and schema["integer_minimum"] <= value <= schema["integer_maximum"],
                "integer literal differs from safe bounds",
            )
        elif kind == "TEXT":
            _require(type(value) is str, "text literal is not text")
            self._validate_text_literal(schema["text_language_id"], value)
        elif kind == "ARRAY":
            _require(type(value) is list, "array literal is not an array")
            _require(
                schema["array_minimum_items"]
                <= len(value)
                <= schema["array_maximum_items"],
                "array literal cardinality differs",
            )
            for item in value:
                self._validate_literal(
                    schema["array_item_value_schema_id"],
                    item,
                    active,
                )
        elif kind == "OBJECT_REF":
            _require(type(value) is dict, "object literal is not an object")
            target = schema["referenced_type_name"]
            if target in self.records:
                self._validate_record_literal(target, value, active)
            else:
                _require(target in self.unions, "literal object target is unresolved")
                self._validate_union_literal(target, value, active)
        else:
            raise ValidationError(f"literal schema kind is unknown: {kind}")

    def _validate_text_literal(self, language_id: str, value: str) -> None:
        _require(language_id in self.languages, "literal text language unresolved")
        _require(
            not any(0xD800 <= ord(char) <= 0xDFFF for char in value),
            "literal text contains a surrogate",
        )
        language = self.languages[language_id]
        encoded_length = len(value.encode("utf-8"))
        if language["minimum_utf8_octets"] is not None:
            _require(
                language["minimum_utf8_octets"]
                <= encoded_length
                <= language["maximum_utf8_octets"],
                "text literal differs from language UTF-8 bounds",
            )
        kind = language["language_kind"]
        if kind in {"LITERAL", "ENUM"}:
            _require(
                value in language["ordered_literals"],
                "literal text is outside the closed language",
            )
            return
        if kind == "ASCII_DFA":
            dfa_id = language["ascii_dfa_id"]
            _require(dfa_id in self.dfas, "literal ASCII DFA is unresolved")
            self._validate_ascii_dfa_literal(self.dfas[dfa_id], value)
            return
        if kind == "UNICODE_IDENTIFIER":
            profile_id = language["unicode_identifier_profile_id"]
            _require(
                profile_id in self.profiles,
                "literal Unicode profile is unresolved",
            )
            self._validate_unicode_literal(self.profiles[profile_id], value)
            return
        _require(kind == "BUILTIN", "literal text language kind differs")
        built_in = language["built_in_language_kind"]
        if built_in == "LOWERCASE_SHA256":
            _require(
                re.fullmatch(r"[0-9a-f]{64}", value) is not None,
                "SHA-256 literal is not lowercase canonical hex",
            )
        elif built_in == "UINT128_DECIMAL":
            _require(
                re.fullmatch(r"(?:0|[1-9][0-9]*)", value) is not None
                and int(value) <= int(language["decimal_maximum"]),
                "uint128 literal is not canonical or is out of range",
            )
        elif built_in == "CANONICAL_BASE64":
            try:
                encoded = value.encode("ascii", errors="strict")
                decoded = base64.b64decode(encoded, validate=True)
            except (UnicodeEncodeError, binascii.Error, ValueError) as exc:
                raise ValidationError("base64 literal is malformed") from exc
            _require(
                base64.b64encode(decoded) == encoded,
                "base64 literal is not canonical",
            )
            _require(
                language["minimum_utf8_octets"]
                <= len(encoded)
                <= language["maximum_utf8_octets"]
                and language["minimum_decoded_octets"]
                <= len(decoded)
                <= language["maximum_decoded_octets"],
                "base64 literal byte bounds differ",
            )
        elif built_in == "RFC3339_UTC":
            match = re.fullmatch(
                r"([0-9]{4})-([0-9]{2})-([0-9]{2})T"
                r"([0-9]{2}):([0-9]{2}):([0-9]{2})"
                r"(?:\\.([0-9]{6}))?Z",
                value,
            )
            _require(
                match is not None and len(value.encode("utf-8")) in {20, 27},
                "timestamp literal is outside the frozen UTC grammar",
            )
            try:
                dt.datetime(
                    int(match.group(1)),
                    int(match.group(2)),
                    int(match.group(3)),
                    int(match.group(4)),
                    int(match.group(5)),
                    int(match.group(6)),
                    int(match.group(7) or "0"),
                    tzinfo=dt.timezone.utc,
                )
            except ValueError as exc:
                raise ValidationError(
                    "timestamp literal is not a valid UTC instant"
                ) from exc
        elif built_in == "RAW_CANONICAL_JSON_STRING":
            # The JSON reader already rejected lone surrogates and any repair.
            _require(type(value) is str, "raw JSON string literal differs")
        else:
            raise ValidationError(f"unknown built-in text language {built_in}")

    def _validate_ascii_dfa_literal(
        self,
        dfa: dict[str, Any],
        value: str,
    ) -> None:
        try:
            octets = value.encode("ascii", errors="strict")
        except UnicodeEncodeError as exc:
            raise ValidationError("ASCII-DFA literal contains non-ASCII text") from exc
        _require(
            dfa["minimum_octets"] <= len(octets) <= dfa["maximum_octets"],
            "ASCII-DFA literal length differs",
        )
        transitions: dict[tuple[int, int], int] = {}
        for row in dfa["ordered_transition_rows"]:
            for byte in range(
                row["inclusive_byte_minimum"],
                row["inclusive_byte_maximum"] + 1,
            ):
                key = (row["source_state"], byte)
                _require(key not in transitions, "ASCII DFA transitions overlap")
                transitions[key] = row["target_state"]
        state = dfa["start_state"]
        for byte in octets:
            _require(
                (state, byte) in transitions,
                "ASCII-DFA literal has no transition",
            )
            state = transitions[(state, byte)]
        _require(
            state in dfa["ordered_accepting_states"],
            "ASCII-DFA literal ends in a rejecting state",
        )

    def _validate_unicode_literal(
        self,
        profile: dict[str, Any],
        value: str,
    ) -> None:
        _require(
            unicodedata.unidata_version == "15.0.0"
            and profile["unicode_version"] == "15.0.0",
            "host/profile Unicode authority is not frozen at 15.0.0",
        )
        _require(
            profile["normalization_form"] == "NFC"
            and unicodedata.normalize("NFC", value) == value,
            "Unicode literal is not NFC",
        )
        _require(
            len(value) <= profile["maximum_scalar_values"]
            and len(value.encode("utf-8")) <= profile["maximum_utf8_octets"],
            "Unicode literal exceeds its scalar/octet bound",
        )

        def code_point(text: str) -> int:
            _require(
                re.fullmatch(r"U\\+[0-9A-F]{4,6}", text) is not None,
                "Unicode code-point authority differs",
            )
            return int(text[2:], 16)

        forbidden = [
            (code_point(lower), code_point(upper))
            for lower, upper in profile["forbidden_code_point_ranges"]
        ]
        _require(
            all(
                not any(lower <= ord(char) <= upper for lower, upper in forbidden)
                for char in value
            ),
            "Unicode literal contains a forbidden code point",
        )
        edge_trim = {code_point(item) for item in profile["edge_trim_code_points"]}
        _require(
            not value
            or (ord(value[0]) not in edge_trim and ord(value[-1]) not in edge_trim),
            "Unicode literal has forbidden edge trim",
        )

    def _validate_record_literal(
        self,
        type_name: str,
        value: dict[str, Any],
        visiting: set[str],
    ) -> None:
        descriptor = self.records[type_name]
        members = descriptor["member_topology"]
        member_names = [item["member_name"] for item in members]
        _require(
            set(value) == set(member_names) and len(value) == len(member_names),
            f"object literal members differ for {type_name}",
        )
        for member_name in member_names:
            schema_id = self.assignments.get((type_name, (member_name,)))
            _require(
                schema_id in self.schemas,
                f"object literal member schema unresolved for {type_name}.{member_name}",
            )
            self._validate_literal(schema_id, value[member_name], visiting)
        encoded_octets = len(_canonical_bytes(value))
        relation = descriptor["codec_byte_bound_relation"]
        limit = descriptor["codec_octet_limit"]
        _require(
            (relation == "LE" and encoded_octets <= limit)
            or (relation == "LT" and encoded_octets < limit),
            f"object literal codec bound differs for {type_name}",
        )
        if self._current_rule_id is not None:
            self._literal_record_references.append((self._current_rule_id, type_name))

    def _literal_path(self, value: dict[str, Any], path: Sequence[str]) -> Any:
        current: Any = value
        for segment in path:
            _require(
                type(current) is dict and segment in current, "literal path unresolved"
            )
            current = current[segment]
        return current

    def _validate_union_literal(
        self,
        type_name: str,
        value: dict[str, Any],
        visiting: set[str],
    ) -> None:
        topology = self.unions[type_name]["tagged_union_topology"]
        discriminators = topology["ordered_discriminator_topology"]
        _require(
            all(
                item["discriminator_scope"] == "SELECTED_VALUE"
                for item in discriminators
            ),
            "owner-scoped union cannot be selected by an isolated literal",
        )
        matches = []
        for alternative in topology["ordered_alternatives"]:
            literal_by_member = {
                item["member_name"]: item["text_value"]
                for item in alternative["ordered_discriminator_literals"]
            }
            if all(
                self._literal_path(
                    value,
                    discriminator["discriminator_typed_member_path"],
                )
                == literal_by_member[
                    discriminator["discriminator_typed_member_path"][-1]
                ]
                for discriminator in discriminators
            ):
                matches.append(alternative)
        _require(len(matches) == 1, "union literal discriminator is ambiguous")
        self._validate_record_literal(
            matches[0]["referenced_type_name"],
            value,
            visiting,
        )

    def _validate_rule_dependency_dag(self) -> None:
        edges = self.ledger["ordered_rule_dependency_edges"]
        _require(
            type(edges) is list
            and all(set(item) == DEPENDENCY_EDGE_KEYS for item in edges),
            "rule dependency edge shape differs",
        )
        _require(
            edges == _dependency_edges(),
            "rule dependency edge catalog differs",
        )
        pairs = [
            (item["predecessor_rule_id"], item["successor_rule_id"]) for item in edges
        ]
        _require(len(pairs) == len(set(pairs)), "duplicate rule dependency edge")
        intrinsic = {
            identifier
            for identifier, rule in self.rules.items()
            if rule["rule_scope"] == "INTRINSIC_RECORD"
        }
        _require(
            all(first in intrinsic and second in intrinsic for first, second in pairs),
            "dependency edge references a non-intrinsic rule",
        )
        successors = {identifier: set() for identifier in intrinsic}
        predecessors = {identifier: set() for identifier in intrinsic}
        for first, second in pairs:
            _require(first != second, "self rule dependency edge")
            successors[first].add(second)
            predecessors[second].add(first)
        ready = sorted(
            identifier for identifier, incoming in predecessors.items() if not incoming
        )
        emitted: list[str] = []
        depth = dict.fromkeys(ready, 1)
        remaining = {key: set(value) for key, value in predecessors.items()}
        while ready:
            current = ready.pop(0)
            emitted.append(current)
            for successor in sorted(successors[current]):
                depth[successor] = max(
                    depth.get(successor, 1),
                    depth[current] + 1,
                )
                remaining[successor].remove(current)
                if not remaining[successor]:
                    ready.append(successor)
                    ready.sort()
        _require(set(emitted) == intrinsic, "rule dependency graph is cyclic")
        _require(max(depth.values()) <= 16, "rule dependency depth exceeds 16")

        reachable: dict[str, set[str]] = {identifier: set() for identifier in intrinsic}
        for identifier in reversed(emitted):
            for successor in successors[identifier]:
                reachable[identifier].add(successor)
                reachable[identifier].update(reachable[successor])
        for current_rule, literal_type in self._literal_record_references:
            for attached_rule in self.attachments[literal_type]:
                _require(
                    attached_rule != current_rule
                    and current_rule in reachable[attached_rule],
                    "composite literal intrinsic rule does not precede consumer",
                )

    def _validate_resolvers(self) -> None:
        records = self.ledger["ordered_fixed_position_resolver_profiles"]
        _require(
            len(records) == 2 and all(set(item) == RESOLVER_KEYS for item in records),
            "resolver profile count/shape differs",
        )
        _require(
            len(self.resolvers) == len(records)
            and len({item["profile_name"] for item in records}) == len(records),
            "resolver identity/name multiplicity differs",
        )
        _require(
            [item["fixed_position_resolver_profile_id"] for item in records]
            == sorted(self.resolvers),
            "resolver catalog order differs",
        )
        for resolver in records:
            _require(set(resolver) == RESOLVER_KEYS, "resolver shape differs")
            payload = {
                key: value
                for key, value in resolver.items()
                if key != "fixed_position_resolver_profile_id"
            }
            _require(
                _semantic_id(RESOLVER_DOMAIN, payload)
                == resolver["fixed_position_resolver_profile_id"],
                "resolver semantic ID differs",
            )
            _require(
                resolver["source_root_type_name"] in self.records
                and resolver["resolved_item_type_name"] in self.records,
                "resolver source/item type is unresolved",
            )
            _require(
                resolver["resolution_semantics"]
                == "CALLER_SUPPLIED_COMPLETE_RECORDS_ID_MATCH_IN_SOURCE_ORDER",
                "resolver semantics differ",
            )
            minimum = resolver["minimum_items"]
            maximum = resolver["maximum_items"]
            _require(
                type(minimum) is int
                and type(maximum) is int
                and 0 <= minimum <= maximum <= SAFE_UINT_MAX,
                "resolver bounds differ",
            )
            item_descriptor = self.records[resolver["resolved_item_type_name"]]
            _require(
                item_descriptor["type_role"] == "STANDALONE"
                and type(item_descriptor["identity_field"]) is str,
                "resolver item has no standalone identity",
            )
            item_identity_id = self._resolve_path(
                resolver["resolved_item_type_name"],
                (item_descriptor["identity_field"],),
            )
            item_identity = self.schemas[item_identity_id]
            _require(
                not item_identity["nullable"], "resolver item identity is nullable"
            )
            implied_minimum = 0
            implied_maximum = 0
            paths = resolver["ordered_source_identity_path_descriptors"]
            _require(
                type(paths) is list
                and bool(paths)
                and all(set(item) == RESOLVER_PATH_KEYS for item in paths),
                "resolver source-path shape differs",
            )
            for position, path_descriptor in enumerate(paths, 1):
                _require(
                    path_descriptor["path_position"] == position
                    and bool(path_descriptor["typed_member_path"]),
                    "resolver path position/path differs",
                )
                source_id = self._resolve_path(
                    resolver["source_root_type_name"],
                    path_descriptor["typed_member_path"],
                )
                source = self.schemas[source_id]
                result_kind = path_descriptor["result_kind"]
                null_semantics = path_descriptor["null_semantics"]
                if result_kind == "ARRAY":
                    _require(
                        null_semantics == "REJECT_NULL"
                        and source["schema_kind"] == "ARRAY"
                        and not source["nullable"]
                        and source["array_item_value_schema_id"] == item_identity_id,
                        "resolver ARRAY path schema differs",
                    )
                    implied_minimum += source["array_minimum_items"]
                    implied_maximum += source["array_maximum_items"]
                elif result_kind == "REQUIRED_SCALAR":
                    _require(
                        null_semantics == "REJECT_NULL"
                        and source_id == item_identity_id,
                        "resolver required-scalar path schema differs",
                    )
                    implied_minimum += 1
                    implied_maximum += 1
                elif result_kind == "OPTIONAL_SCALAR":
                    _require(
                        null_semantics == "NULL_TO_EMPTY_SEQUENCE"
                        and source["nullable"]
                        and self._same_nonnull_base(source, item_identity),
                        "resolver optional-scalar path schema differs",
                    )
                    implied_maximum += 1
                else:
                    raise ValidationError(f"unknown resolver result kind {result_kind}")
            _require(
                (minimum, maximum) == (implied_minimum, implied_maximum),
                "resolver declared bounds differ from source paths",
            )

    def _schema_id_for_payload(self, payload: dict[str, Any]) -> str:
        identifier = _semantic_id(VALUE_SCHEMA_DOMAIN, payload)
        _require(identifier in self.schemas, "derived application schema is absent")
        _require(
            self.schemas[identifier] == {**payload, "value_schema_id": identifier},
            "derived application schema differs",
        )
        return identifier

    def _effective_record_binding(
        self,
        binding_name: str,
        type_name: str,
    ) -> dict[str, Any]:
        return {
            "binding_name": binding_name,
            "binding_kind": "RECORD",
            "expected_type_name": type_name,
            "expected_value_schema_id": self._schema_id_for_payload(
                _schema_payload(
                    schema_kind="OBJECT_REF",
                    nullable=False,
                    referenced_type_name=type_name,
                )
            ),
        }

    def _validate_applications(self) -> None:
        applications = self.ledger["ordered_rule_application_descriptors"]
        _require(
            len(applications) == 8
            and all(set(item) == APPLICATION_KEYS for item in applications),
            "application count/shape differs",
        )
        _require(
            [item["application_name"] for item in applications]
            == sorted(item["application_name"] for item in applications),
            "application catalog is not in lexical-name order",
        )
        _require(
            len({item["application_name"] for item in applications}) == 8
            and len({item["rule_application_id"] for item in applications}) == 8,
            "application name/identity multiplicity differs",
        )
        application_rule_counter = Counter(item["rule_id"] for item in applications)
        _require(
            application_rule_counter == Counter(dict.fromkeys(CROSS_RULE_IDS, 1)),
            "cross-rule application multiplicity differs",
        )
        for application in applications:
            _require(set(application) == APPLICATION_KEYS, "application shape differs")
            payload = {
                key: value
                for key, value in application.items()
                if key != "rule_application_id"
            }
            _require(
                _semantic_id(APPLICATION_DOMAIN, payload)
                == application["rule_application_id"],
                "application semantic ID differs",
            )
            rule_id = application["rule_id"]
            _require(
                rule_id in self.rules
                and self.rules[rule_id]["rule_scope"] == "CROSS_RECORD",
                "application references a non-cross rule",
            )
            roots = application["ordered_root_input_bindings"]
            _require(
                type(roots) is list
                and bool(roots)
                and all(set(item) == ROOT_BINDING_KEYS for item in roots),
                "application root-binding shape differs",
            )
            effective = []
            root_by_name: dict[str, dict[str, Any]] = {}
            for position, root in enumerate(roots, 1):
                _require(
                    root["tuple_position"] == position
                    and root["expected_type_name"] in self.records
                    and root["binding_name"] not in root_by_name,
                    "application root binding differs",
                )
                root_by_name[root["binding_name"]] = root
                effective.append(
                    self._effective_record_binding(
                        root["binding_name"],
                        root["expected_type_name"],
                    )
                )
            sequence_bounds: list[int] = []
            sequences = application["ordered_sequence_input_bindings"]
            _require(
                type(sequences) is list
                and all(set(item) == SEQUENCE_BINDING_KEYS for item in sequences),
                "application sequence-binding shape differs",
            )
            sequence_names: set[str] = set()
            for sequence in sequences:
                name = sequence["binding_name"]
                _require(
                    name not in root_by_name and name not in sequence_names,
                    "application sequence binding name is duplicated",
                )
                sequence_names.add(name)
                root_name = sequence["source_root_binding_name"]
                _require(root_name in root_by_name, "sequence root binding unresolved")
                expected_type = sequence["expected_item_type_name"]
                _require(expected_type in self.records, "sequence item type unresolved")
                source_kind = sequence["source_kind"]
                mode = sequence["binding_mode"]
                if source_kind == "EMBEDDED_ARRAY":
                    _require(
                        mode == "ITERATED_RECORD"
                        and bool(sequence["embedded_array_typed_member_path"])
                        and sequence["fixed_position_resolver_profile_id"] is None,
                        "embedded sequence shape differs",
                    )
                    source_id = self._resolve_path(
                        root_by_name[root_name]["expected_type_name"],
                        sequence["embedded_array_typed_member_path"],
                    )
                    source = self.schemas[source_id]
                    _require(
                        source["schema_kind"] == "ARRAY" and not source["nullable"],
                        "embedded sequence source is not a bounded array",
                    )
                    item_id = source["array_item_value_schema_id"]
                    item = self.schemas[item_id]
                    _require(
                        item["schema_kind"] == "OBJECT_REF"
                        and not item["nullable"]
                        and item["referenced_type_name"] == expected_type,
                        "embedded sequence item schema differs",
                    )
                    sequence_bounds.append(source["array_maximum_items"])
                    effective.append(
                        {
                            "binding_name": name,
                            "binding_kind": "RECORD",
                            "expected_type_name": expected_type,
                            "expected_value_schema_id": item_id,
                        }
                    )
                elif source_kind == "EXTERNAL_FIXED_SEQUENCE":
                    _require(
                        not sequence["embedded_array_typed_member_path"],
                        "external sequence carries an embedded path",
                    )
                    resolver_id = sequence["fixed_position_resolver_profile_id"]
                    _require(
                        resolver_id in self.resolvers, "sequence resolver unresolved"
                    )
                    resolver = self.resolvers[resolver_id]
                    _require(
                        resolver["source_root_type_name"]
                        == root_by_name[root_name]["expected_type_name"]
                        and resolver["resolved_item_type_name"] == expected_type,
                        "sequence resolver source/item differs",
                    )
                    item_id = self._schema_id_for_payload(
                        _schema_payload(
                            schema_kind="OBJECT_REF",
                            nullable=False,
                            referenced_type_name=expected_type,
                        )
                    )
                    if mode == "ITERATED_RECORD":
                        sequence_bounds.append(resolver["maximum_items"])
                        effective.append(
                            {
                                "binding_name": name,
                                "binding_kind": "RECORD",
                                "expected_type_name": expected_type,
                                "expected_value_schema_id": item_id,
                            }
                        )
                    elif mode == "COMPLETE_RECORD_SEQUENCE":
                        array_id = self._schema_id_for_payload(
                            _schema_payload(
                                schema_kind="ARRAY",
                                nullable=False,
                                array_minimum_items=resolver["minimum_items"],
                                array_maximum_items=resolver["maximum_items"],
                                array_item_value_schema_id=item_id,
                            )
                        )
                        effective.append(
                            {
                                "binding_name": name,
                                "binding_kind": "FIXED_RECORD_SEQUENCE",
                                "expected_type_name": expected_type,
                                "expected_value_schema_id": array_id,
                            }
                        )
                    elif mode == "OPTIONAL_RECORD":
                        _require(
                            resolver["minimum_items"] == 0
                            and resolver["maximum_items"] == 1,
                            "optional resolver bounds differ",
                        )
                        optional_id = self._schema_id_for_payload(
                            _schema_payload(
                                schema_kind="OBJECT_REF",
                                nullable=True,
                                referenced_type_name=expected_type,
                            )
                        )
                        effective.append(
                            {
                                "binding_name": name,
                                "binding_kind": "OPTIONAL_FIXED_RECORD",
                                "expected_type_name": expected_type,
                                "expected_value_schema_id": optional_id,
                            }
                        )
                    else:
                        raise ValidationError(f"unknown external binding mode {mode}")
                else:
                    raise ValidationError(f"unknown sequence source kind {source_kind}")

            ordinal_name = application["iteration_ordinal_binding_name"]
            maximum = application["maximum_rule_evaluations"]
            kind = application["application_kind"]
            _require(
                type(maximum) is int and 1 <= maximum <= SAFE_UINT_MAX,
                "application evaluation bound differs",
            )
            if kind == "RECORD_TUPLE":
                _require(
                    len(roots) >= 2
                    and not sequences
                    and ordinal_name is None
                    and maximum == 1
                    and application["requires_equal_cardinality"] is False
                    and application["evaluation_order"] == "SINGLE_EVALUATION",
                    "record-tuple application shape differs",
                )
            elif kind in {"ARRAY_EACH", "FOR_EACH_FIXED_POSITION_BINDING"}:
                _require(
                    bool(sequences)
                    and all(
                        item["binding_mode"] == "ITERATED_RECORD" for item in sequences
                    )
                    and type(ordinal_name) is str
                    and bool(ordinal_name)
                    and ordinal_name not in root_by_name
                    and ordinal_name not in sequence_names
                    and maximum == min(sequence_bounds)
                    and application["requires_equal_cardinality"]
                    is (len(sequences) > 1)
                    and application["evaluation_order"]
                    == "LEXICAL_APPLICATION_NAME_THEN_SEQUENCE_ORDINAL",
                    "iterated application shape/bound differs",
                )
                external_count = sum(
                    item["source_kind"] == "EXTERNAL_FIXED_SEQUENCE"
                    for item in sequences
                )
                _require(
                    (kind == "ARRAY_EACH" and external_count == 0)
                    or (
                        kind == "FOR_EACH_FIXED_POSITION_BINDING"
                        and external_count >= 1
                    ),
                    "iterated application kind/source partition differs",
                )
                ordinal_id = self._schema_id_for_payload(
                    _schema_payload(
                        schema_kind="SAFE_INTEGER",
                        nullable=False,
                        integer_minimum=0,
                        integer_maximum=maximum - 1,
                    )
                )
                effective.append(
                    {
                        "binding_name": ordinal_name,
                        "binding_kind": "SAFE_UINT",
                        "expected_type_name": None,
                        "expected_value_schema_id": ordinal_id,
                    }
                )
            elif kind == "FIXED_SEQUENCE_AGGREGATE":
                _require(
                    bool(sequences)
                    and all(
                        item["source_kind"] == "EXTERNAL_FIXED_SEQUENCE"
                        and item["binding_mode"]
                        in {"COMPLETE_RECORD_SEQUENCE", "OPTIONAL_RECORD"}
                        for item in sequences
                    )
                    and ordinal_name is None
                    and maximum == 1
                    and application["requires_equal_cardinality"] is False
                    and application["evaluation_order"] == "SINGLE_EVALUATION",
                    "fixed-sequence aggregate shape differs",
                )
            else:
                raise ValidationError(f"unknown application kind {kind}")
            _require(
                effective == self.rules[rule_id]["ordered_rule_input_bindings"],
                "application effective binding ledger differs from rule",
            )

    def _rule_literal_values(self, rule_id: str) -> list[Any]:
        rule = self.rules[rule_id]
        return [
            node["literal_value"]
            for node in rule["ordered_expression_nodes"]
            if node["operator"] == "LITERAL"
        ]

    def _validate_literal_selection(self) -> None:
        marker_rule = "RULE/INTRINSIC/MarkerContractV1/V1"
        registry_rule = "RULE/INTRINSIC/TargetFieldRegistryV1/V1"
        counter_rule = "RULE/INTRINSIC/OperationCounterSnapshotSchemaV1/V1"
        marker_members = _marker_contract_literals()
        _require(
            self._rule_literal_values(marker_rule) == list(marker_members.values()),
            "marker-contract frozen literal selection differs",
        )
        registry = self.literals["target_field_registry"]
        registry_members = (
            "status_reason_policy_definition",
            "ordered_vocabulary_definitions",
            "ordered_value_shape_definitions",
            "ordered_value_constraint_definitions",
            "ordered_cross_field_constraint_definitions",
            "descriptors",
        )
        _require(
            self._rule_literal_values(registry_rule)
            == [registry[name] for name in registry_members],
            "target-registry frozen literal selection differs",
        )
        counter = self.literals["operation_counter_schema"]
        _require(
            self._rule_literal_values(counter_rule)
            == [
                counter["ordered_counter_field_ids"],
                counter["monotone_counter_field_ids"],
            ],
            "counter-schema frozen literal selection differs",
        )
        encoded = _canonical_bytes(self.literals)
        _require(
            b"d092a" not in encoded
            and registry["target_field_registry_id"].encode("ascii") in encoded,
            "stale/current target-registry identity selection differs",
        )

    def _validate_component_identity(self) -> None:
        _require(set(self.ledger) == COMPONENT_KEYS, "component root shape differs")
        _require(
            self.ledger["canonicalization_version"] == CANONICALIZATION_VERSION
            and self.ledger["measurement_schema_version"] == MEASUREMENT_SCHEMA_VERSION
            and self.ledger["component_status"] == COMPONENT_STATUS
            and self.ledger["rule_application_ledger_version"] == LEDGER_VERSION,
            "component header differs",
        )
        _require(
            self.ledger["dependency_sha256"]
            == {
                "topology_ledger": TOPOLOGY_SHA256,
                "scalar_path_ledger": SCALAR_SHA256,
                "rule_literal_authority": FROZEN_LITERAL_SHA256,
            },
            "component dependency digest catalog differs",
        )
        rules = self.ledger["ordered_rule_descriptors"]
        intrinsic = [item for item in rules if item["rule_scope"] == "INTRINSIC_RECORD"]
        cross = [item for item in rules if item["rule_scope"] == "CROSS_RECORD"]
        expression_count = sum(len(item["ordered_expression_nodes"]) for item in rules)
        _require(
            self.ledger["concrete_attachment_count"] == 49
            and self.ledger["intrinsic_rule_count"] == len(intrinsic) == 34
            and self.ledger["cross_rule_count"] == len(cross) == 8
            and self.ledger["typed_rule_count"] == len(rules) == 42
            and self.ledger["rule_application_descriptor_count"] == 8
            and self.ledger["fixed_position_resolver_profile_count"] == 2
            and self.ledger["member_value_schema_count"]
            == len(self.member_schema_ids)
            == 200
            and self.ledger["additive_rule_value_schema_count"]
            == len(self.additive_schema_ids)
            and self.ledger["full_reachable_value_schema_count"] == len(self.schemas)
            and self.ledger["total_expression_node_count"] == expression_count,
            "component derived counts differ",
        )
        _require(
            [
                item["value_schema_id"]
                for item in self.ledger["ordered_additive_rule_value_schemas"]
            ]
            == sorted(self.additive_schema_ids)
            and [item["step2_cross_field_rule_descriptor_id"] for item in rules]
            == sorted(item["step2_cross_field_rule_descriptor_id"] for item in rules),
            "component schema/rule catalog order differs",
        )
        referenced = set()
        for rule in rules:
            referenced.update(
                item["expected_value_schema_id"]
                for item in rule["ordered_rule_input_bindings"]
            )
            referenced.update(
                node["result_value_schema_id"]
                for node in rule["ordered_expression_nodes"]
                if node["result_type_kind"] == "VALUE_SCHEMA"
            )
            referenced.update(
                node["literal_value_schema_id"]
                for node in rule["ordered_expression_nodes"]
                if node["literal_value_schema_id"] is not None
            )
        reachable = set()
        stack = list(referenced)
        while stack:
            identifier = stack.pop()
            _require(identifier in self.schemas, "rule schema reference unresolved")
            if identifier in reachable:
                continue
            reachable.add(identifier)
            schema = self.schemas[identifier]
            if schema["schema_kind"] == "ARRAY":
                stack.append(schema["array_item_value_schema_id"])
        _require(
            reachable & self.additive_schema_ids == self.additive_schema_ids,
            "additive schema reachability closure differs",
        )
        attachment_counter = Counter(
            rule_id
            for item in self.ledger["ordered_intrinsic_rule_attachments"]
            for rule_id in item["ordered_intrinsic_rule_ids"]
        )
        _require(
            attachment_counter == Counter({item["rule_id"]: 1 for item in intrinsic}),
            "intrinsic attachment multiplicity differs",
        )
        _require(
            [
                item["type_name"]
                for item in self.ledger["ordered_intrinsic_rule_attachments"]
            ]
            == [
                item["type_name"]
                for item in self.topology["type_descriptors"]
                if item["type_form"] == "RECORD"
            ],
            "attachment rows do not match concrete topology order",
        )
        _require(
            self.ledger["closure_evidence"]
            == {
                "additive_schema_ids_disjoint_from_member_schema_ids": True,
                "all_additive_rule_schemas_reachable": True,
                "all_intrinsic_rules_attached_exactly_once": True,
                "all_cross_rules_applied_exactly_once": True,
                "member_union_additive_equals_full_reachable_catalog": True,
                "union_nodes_remain_rule_attachment_free": True,
            },
            "closure evidence differs",
        )
        payload = {
            key: value
            for key, value in self.ledger.items()
            if key != "rule_application_component_sha256"
        }
        _require(
            _semantic_id(COMPONENT_DOMAIN, payload)
            == self.ledger["rule_application_component_sha256"],
            "rule/application component semantic ID differs",
        )


def _load_dependencies(
    repository_root: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    topology = _load_json(
        repository_root / TOPOLOGY_RELATIVE_PATH,
        maximum_octets=MAXIMUM_TOPOLOGY_OCTETS,
        expected_sha256=TOPOLOGY_SHA256,
    )
    scalar = _load_json(
        repository_root / SCALAR_RELATIVE_PATH,
        maximum_octets=MAXIMUM_SCALAR_OCTETS,
        expected_sha256=SCALAR_SHA256,
    )
    literals = _load_json(
        repository_root / FROZEN_LITERAL_RELATIVE_PATH,
        maximum_octets=MAXIMUM_FROZEN_LITERAL_OCTETS,
        expected_sha256=FROZEN_LITERAL_SHA256,
    )
    _validate_dependency_headers(topology, scalar)
    _validate_literal_authority(literals)
    return topology, scalar, literals


def validate_materialized_ledger(
    *,
    topology: dict[str, Any],
    scalar: dict[str, Any],
    literals: dict[str, Any],
    ledger: dict[str, Any],
) -> None:
    """Validate static descriptor semantics, then the exact materialization."""

    _validate_dependency_headers(topology, scalar)
    _validate_literal_authority(literals)
    StaticDescriptorValidator(
        topology=topology,
        scalar=scalar,
        literals=literals,
        ledger=ledger,
    ).validate()
    expected = build_ledger(topology, scalar, literals)
    _require(
        ledger == expected,
        "rule/application ledger differs from the explicit authority",
    )


def validate_rule_application_ledger(
    *,
    repository_root: Path,
    ledger_path: Path,
) -> dict[str, Any]:
    topology, scalar, literals = _load_dependencies(repository_root)
    ledger, raw = _load_json_document(
        ledger_path,
        maximum_octets=MAXIMUM_LEDGER_OCTETS,
    )
    validate_materialized_ledger(
        topology=topology,
        scalar=scalar,
        literals=literals,
        ledger=ledger,
    )
    _require(len(raw) == LEDGER_OCTETS, "rule/application ledger octets differ")
    _require(_sha256(raw) == LEDGER_SHA256, "rule/application ledger digest differs")
    return {
        "additive_rule_value_schema_count": ledger["additive_rule_value_schema_count"],
        "component_status": ledger["component_status"],
        "concrete_attachment_count": ledger["concrete_attachment_count"],
        "cross_rule_count": ledger["cross_rule_count"],
        "fixed_position_resolver_profile_count": ledger[
            "fixed_position_resolver_profile_count"
        ],
        "full_reachable_value_schema_count": ledger[
            "full_reachable_value_schema_count"
        ],
        "intrinsic_rule_count": ledger["intrinsic_rule_count"],
        "ledger_octets": len(raw),
        "ledger_path": str(ledger_path),
        "ledger_sha256": _sha256(raw),
        "literal_validation_scope": (
            "STATIC_STRUCTURE_PLUS_EXACT_FROZEN_SELECTION;"
            "ATTACHED_INTRINSIC_EXECUTION_DEFERRED_TO_FULL_REGISTRY_EVALUATOR"
        ),
        "rule_application_component_sha256": ledger[
            "rule_application_component_sha256"
        ],
        "rule_application_descriptor_count": ledger[
            "rule_application_descriptor_count"
        ],
        "total_expression_node_count": ledger["total_expression_node_count"],
        "typed_rule_count": ledger["typed_rule_count"],
    }


def _write_expected_ledger(
    *,
    repository_root: Path,
    output: Path,
) -> None:
    topology, scalar, literals = _load_dependencies(repository_root)
    ledger = build_ledger(topology, scalar, literals)
    validate_materialized_ledger(
        topology=topology,
        scalar=scalar,
        literals=literals,
        ledger=ledger,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(_pretty_bytes(ledger))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path.cwd(),
    )
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--write-expected-ledger", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    repository_root = arguments.repository_root.resolve()
    try:
        _require(
            not (
                arguments.ledger is not None
                and arguments.write_expected_ledger is not None
            ),
            "--ledger and --write-expected-ledger are mutually exclusive",
        )
        if arguments.write_expected_ledger is not None:
            _write_expected_ledger(
                repository_root=repository_root,
                output=arguments.write_expected_ledger,
            )
            return 0
        ledger_path = (
            arguments.ledger
            if arguments.ledger is not None
            else repository_root / LEDGER_RELATIVE_PATH
        )
        report = validate_rule_application_ledger(
            repository_root=repository_root,
            ledger_path=ledger_path,
        )
    except (
        AssertionError,
        AttributeError,
        IndexError,
        KeyError,
        OSError,
        TypeError,
        UnicodeError,
        ValidationError,
        ValueError,
    ) as exc:
        print(
            f"Raw-V8 Step-2 external-schema V2 rule/application error: {exc}",
            file=sys.stderr,
        )
        return 1
    print(
        json.dumps(
            report,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

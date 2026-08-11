#!/usr/bin/env python3
"""Materialize or validate the standalone structural External Schema V2.

This standard-library-only component consumes the four independently accepted
foundation/topology/scalar/rule ledgers.  It assembles the exact structural
registry without importing production code.  Rule execution, recursive
intrinsic evaluation, constructive maxima, production adapters, and the final
Step-2 GO decision deliberately remain outside this component.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Final

CANONICALIZATION_VERSION: Final = "riskyieldmm_canonical_json_v1"
MEASUREMENT_SCHEMA_VERSION: Final = "riskyieldmm_physical_transport_a2m_raw_v49f_v8"
STRUCTURAL_STATUS: Final = "STRUCTURAL_REGISTRY_ONLY_RULE_RUNTIME_AND_MAXIMA_PENDING"
EXTERNAL_SCHEMA_PROFILE: Final = "riskyieldmm_raw_v8_step2_external_schema_v2"
REGISTRY_RECORD_DOMAIN: Final = "RiskYieldMMA2MStep2ExternalSchemaRegistryV2V4_9F_RawV8"

CORE_RELATIVE_PATH: Final = (
    "scripts/tests/raw_v8_step2_external_schema_v2_core_ledger_v49f.json"
)
TOPOLOGY_RELATIVE_PATH: Final = (
    "scripts/tests/raw_v8_step2_external_schema_v2_topology_ledger_v49f.json"
)
SCALAR_RELATIVE_PATH: Final = (
    "scripts/tests/raw_v8_step2_external_schema_v2_scalar_path_ledger_v49f.json"
)
RULE_RELATIVE_PATH: Final = (
    "scripts/tests/raw_v8_step2_external_schema_v2_rule_application_ledger_v49f.json"
)
REGISTRY_RELATIVE_PATH: Final = (
    "scripts/tests/raw_v8_step2_external_schema_v2_structural_registry_v49f.json"
)

CORE_SHA256: Final = "fc2b888559067fddb5178a87bcae3ab4876e5c17fab766da6ce54581eeff34fb"
TOPOLOGY_SHA256: Final = (
    "17b6355afcc23438efad97967180fb7e6292b7dd3d72d8b91a0320bfb9696778"
)
SCALAR_SHA256: Final = (
    "b0b8783c8783012d5dc966578c82f348c902f6bf0d44583a4a7d5be6a16079aa"
)
RULE_SHA256: Final = "979d7affe2d745d46f5977d9d69a4d1efa473f95c1a374737bf34181d9dac282"

REGISTRY_SHA256: Final = (
    "9160297ff316c5931737c92f8b359f0a1e2ec22f0aa996ef3b09cf830dc96bf3"
)
REGISTRY_OCTETS: Final = 1_469_663

MAXIMUM_DEPENDENCY_OCTETS: Final = 8_388_608
REGISTRY_EXCLUSIVE_OCTET_LIMIT: Final = 16_777_216
MAXIMUM_JSON_DEPTH: Final = 16
SAFE_UINT_MAX: Final = 9_007_199_254_740_991

SOURCE_DOMAIN: Final = "RiskYieldMMA2MStep2UnicodeSourceRecordV1V4_9F_RawV8"
PROFILE_DOMAIN: Final = "RiskYieldMMA2MStep2UnicodeIdentifierProfileV1V4_9F_RawV8"
DFA_DOMAIN: Final = "RiskYieldMMA2MStep2AsciiDfaDescriptorV2V4_9F_RawV8"
TEXT_DOMAIN: Final = "RiskYieldMMA2MStep2TextLanguageDescriptorV2V4_9F_RawV8"
VALUE_SCHEMA_DOMAIN: Final = "RiskYieldMMA2MStep2ValueSchemaV2V4_9F_RawV8"
TYPE_DOMAIN: Final = "RiskYieldMMA2MStep2ExternalTypeDescriptorV2V4_9F_RawV8"
RULE_DOMAIN: Final = "RiskYieldMMA2MStep2CrossFieldRuleDescriptorV2V4_9F_RawV8"
RESOLVER_DOMAIN: Final = "RiskYieldMMA2MStep2FixedPositionResolverProfileV2V4_9F_RawV8"
APPLICATION_DOMAIN: Final = "RiskYieldMMA2MStep2RuleApplicationDescriptorV2V4_9F_RawV8"

REGISTRY_KEYS: Final = {
    "canonicalization_version",
    "measurement_schema_version",
    "record_domain",
    "external_schema_profile",
    "unicode_source_catalog",
    "identifier_profile_catalog",
    "ascii_dfa_catalog",
    "text_language_catalog",
    "value_schema_catalog",
    "external_type_descriptor_count",
    "ordered_external_type_descriptors",
    "cross_field_rule_descriptor_count",
    "ordered_cross_field_rule_descriptors",
    "fixed_position_resolver_profile_catalog",
    "rule_application_descriptor_count",
    "ordered_rule_application_descriptors",
    "schema_graph_node_count",
    "ordered_schema_graph_node_names",
    "external_schema_registry_id",
}
SOURCE_KEYS: Final = {
    "source_name",
    "unicode_version",
    "official_url",
    "byte_count",
    "sha256",
    "unicode_source_record_id",
}
PROFILE_KEYS: Final = {
    "profile_id",
    "unicode_version",
    "normalization_form",
    "maximum_scalar_values",
    "maximum_utf8_octets",
    "forbidden_code_point_ranges",
    "edge_trim_code_points",
    "unicode_source_record_ids",
    "unicode_identifier_profile_id",
}
DFA_KEYS: Final = {
    "state_count",
    "start_state",
    "ordered_accepting_states",
    "ordered_transition_rows",
    "minimum_octets",
    "maximum_octets",
    "ascii_dfa_id",
}
TRANSITION_KEYS: Final = {
    "source_state",
    "inclusive_byte_minimum",
    "inclusive_byte_maximum",
    "target_state",
}
TEXT_KEYS: Final = {
    "language_kind",
    "ordered_literals",
    "built_in_language_kind",
    "ascii_dfa_id",
    "minimum_utf8_octets",
    "maximum_utf8_octets",
    "minimum_decoded_octets",
    "maximum_decoded_octets",
    "decimal_maximum",
    "unicode_identifier_profile_id",
    "ordering_semantics",
    "text_language_id",
}
VALUE_KEYS: Final = {
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
TYPE_KEYS: Final = {
    "type_name",
    "type_version_tag",
    "type_role",
    "type_form",
    "described_record_domain",
    "identity_field",
    "identity_payload_member_order",
    "codec_byte_bound_relation",
    "codec_octet_limit",
    "record_member_descriptors",
    "tagged_union_descriptor",
    "ordered_intrinsic_rule_ids",
    "external_type_descriptor_id",
}
MEMBER_KEYS: Final = {
    "member_position",
    "member_name",
    "member_role",
    "value_schema_id",
}
UNION_KEYS: Final = {
    "payload_binding_scope",
    "payload_owner_type_name",
    "payload_typed_member_path",
    "ordered_discriminator_descriptors",
    "ordered_alternatives",
}
DISCRIMINATOR_KEYS: Final = {
    "discriminator_position",
    "discriminator_scope",
    "discriminator_owner_type_name",
    "discriminator_typed_member_path",
    "text_language_id",
}
ALTERNATIVE_KEYS: Final = {
    "alternative_position",
    "alternative_name",
    "ordered_discriminator_literals",
    "referenced_type_name",
}
DISCRIMINATOR_LITERAL_KEYS: Final = {"member_name", "text_value"}
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


class StructuralRegistryError(ValueError):
    """Controlled deterministic structural-registry validation failure."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise StructuralRegistryError(message)


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


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result, f"duplicate JSON member {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise StructuralRegistryError(f"non-I-JSON numeric constant {value}")


def _reject_float(value: str) -> None:
    raise StructuralRegistryError(f"floating-point JSON number {value}")


def _validate_json_scalars(value: Any) -> None:
    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            for key, item in current.items():
                _require(type(key) is str, "JSON key is not text")
                _require(
                    not any(0xD800 <= ord(char) <= 0xDFFF for char in key),
                    "JSON key contains a surrogate",
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


def _scan_json_structure(text: str) -> int:
    """Scan raw JSON nesting before decode without interpreting values."""

    stack: list[str] = []
    in_string = False
    escaped = False
    maximum = 0
    closing = {"}": "{", "]": "["}
    for character in text:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            else:
                _require(
                    ord(character) >= 0x20,
                    "raw JSON string contains an unescaped control",
                )
            continue
        if character == '"':
            in_string = True
        elif character in "[{":
            stack.append(character)
            maximum = max(maximum, len(stack))
            _require(
                maximum <= MAXIMUM_JSON_DEPTH,
                "raw JSON nesting exceeds the structural bound",
            )
        elif character in "]}":
            _require(
                bool(stack) and stack[-1] == closing[character],
                "raw JSON delimiters are unbalanced",
            )
            stack.pop()
    _require(not in_string and not escaped, "raw JSON string is unterminated")
    _require(not stack, "raw JSON delimiters are unterminated")
    return maximum


def _bounded_regular_read(
    path: Path,
    *,
    maximum_octets: int,
    exclusive: bool,
) -> bytes:
    flags = os.O_RDONLY | os.O_NONBLOCK
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise StructuralRegistryError(
            f"cannot open bounded authority: {path.name}"
        ) from exc
    try:
        before = os.fstat(descriptor)
        _require(stat.S_ISREG(before.st_mode), f"{path.name} is not a regular file")
        size_ok = (
            before.st_size < maximum_octets
            if exclusive
            else before.st_size <= maximum_octets
        )
        _require(size_ok, f"{path.name} exceeds its byte bound")
        chunks: list[bytes] = []
        total = 0
        hard_limit = maximum_octets - 1 if exclusive else maximum_octets
        while True:
            chunk = os.read(descriptor, min(65_536, hard_limit + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            _require(total <= hard_limit, f"{path.name} exceeds its byte bound")
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


def _decode_document(path: Path, raw: bytes) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8", errors="strict")
        _scan_json_structure(text)
        value = json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
            parse_float=_reject_float,
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        RecursionError,
        StructuralRegistryError,
        ValueError,
    ) as exc:
        raise StructuralRegistryError(
            f"{path.name} is not controlled canonical JSON"
        ) from exc
    _require(type(value) is dict, f"{path.name} root is not an object")
    _validate_json_scalars(value)
    _require(_json_depth(value) <= MAXIMUM_JSON_DEPTH, f"{path.name} is too deep")
    _require(_pretty_bytes(value) == raw, f"{path.name} is not canonical pretty JSON")
    return value


def _load_document(
    path: Path,
    *,
    maximum_octets: int,
    exclusive: bool = False,
    expected_sha256: str | None = None,
) -> tuple[dict[str, Any], bytes]:
    raw = _bounded_regular_read(
        path,
        maximum_octets=maximum_octets,
        exclusive=exclusive,
    )
    if expected_sha256 is not None:
        _require(_sha256(raw) == expected_sha256, f"{path.name} SHA-256 differs")
    return _decode_document(path, raw), raw


def _index_unique(
    records: Any,
    *,
    key: str,
    label: str,
) -> dict[Any, dict[str, Any]]:
    _require(type(records) is list, f"{label} catalog is not an array")
    result: dict[Any, dict[str, Any]] = {}
    for record in records:
        _require(type(record) is dict and key in record, f"{label} row differs")
        identifier = record[key]
        _require(identifier not in result, f"duplicate {label} {identifier!r}")
        result[identifier] = record
    return result


def _load_dependencies(
    repository_root: Path,
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
]:
    core, _ = _load_document(
        repository_root / CORE_RELATIVE_PATH,
        maximum_octets=MAXIMUM_DEPENDENCY_OCTETS,
        expected_sha256=CORE_SHA256,
    )
    topology, _ = _load_document(
        repository_root / TOPOLOGY_RELATIVE_PATH,
        maximum_octets=MAXIMUM_DEPENDENCY_OCTETS,
        expected_sha256=TOPOLOGY_SHA256,
    )
    scalar, _ = _load_document(
        repository_root / SCALAR_RELATIVE_PATH,
        maximum_octets=MAXIMUM_DEPENDENCY_OCTETS,
        expected_sha256=SCALAR_SHA256,
    )
    rules, _ = _load_document(
        repository_root / RULE_RELATIVE_PATH,
        maximum_octets=MAXIMUM_DEPENDENCY_OCTETS,
        expected_sha256=RULE_SHA256,
    )
    _require(
        core["component_status"] == "FOUNDATION_ONLY_NOT_EXTERNAL_SCHEMA_REGISTRY_V2",
        "foundation component status differs",
    )
    _require(
        topology["component_status"] == "TOPOLOGY_ONLY_NOT_FULL_REGISTRY"
        and topology["total_type_count"] == 52,
        "topology dependency differs",
    )
    _require(
        scalar["component_status"] == "SCALAR_PATH_ONLY_NOT_FULL_REGISTRY"
        and scalar["value_schema_count"] == 200
        and scalar["text_language_count"] == 103,
        "scalar dependency differs",
    )
    _require(
        rules["component_status"] == "RULE_APPLICATION_ONLY_NOT_FULL_REGISTRY"
        and rules["typed_rule_count"] == 42
        and rules["additive_rule_value_schema_count"] == 36,
        "rule/application dependency differs",
    )
    return core, topology, scalar, rules


def _materialize_unicode_sources(core: dict[str, Any]) -> list[dict[str, Any]]:
    records = []
    for spec in core["unicode_source_specs"]:
        record = {
            **spec,
            "unicode_source_record_id": _semantic_id(SOURCE_DOMAIN, spec),
        }
        records.append(record)
    return sorted(records, key=lambda item: item["unicode_source_record_id"])


def _resolve_path_schema_id(
    *,
    assignments: dict[tuple[str, tuple[str, ...]], str],
    schemas: dict[str, dict[str, Any]],
    records: dict[str, dict[str, Any]],
    type_name: str,
    path: list[str],
) -> str:
    _require(bool(path), "typed member path is empty")
    current_type = type_name
    for index, segment in enumerate(path):
        _require(current_type in records, f"path enters non-record {current_type}")
        schema_id = assignments.get((current_type, (segment,)))
        _require(
            schema_id in schemas, f"path schema unresolved {current_type}.{segment}"
        )
        if index == len(path) - 1:
            return schema_id
        schema = schemas[schema_id]
        _require(
            schema["schema_kind"] == "OBJECT_REF"
            and not schema["nullable"]
            and schema["referenced_type_name"] in records,
            f"path crosses a non-required record at {current_type}.{segment}",
        )
        current_type = schema["referenced_type_name"]
    raise AssertionError("unreachable")


def _union_discriminator_language_id(
    *,
    discriminator: dict[str, Any],
    alternatives: list[dict[str, Any]],
    assignments: dict[tuple[str, tuple[str, ...]], str],
    schemas: dict[str, dict[str, Any]],
    languages: dict[str, dict[str, Any]],
    records: dict[str, dict[str, Any]],
) -> str:
    path = discriminator["discriminator_typed_member_path"]
    position = discriminator["discriminator_position"] - 1
    literals = [
        alternative["ordered_discriminator_literals"][position]["text_value"]
        for alternative in alternatives
    ]
    _require(
        len(literals) == len(set(literals)),
        "union discriminator literals are not unique",
    )
    expected_literals = sorted(literals)
    if discriminator["discriminator_scope"] == "OWNER_OBJECT":
        owner = discriminator["discriminator_owner_type_name"]
        schema_id = _resolve_path_schema_id(
            assignments=assignments,
            schemas=schemas,
            records=records,
            type_name=owner,
            path=path,
        )
        schema = schemas[schema_id]
        _require(
            schema["schema_kind"] == "TEXT" and not schema["nullable"],
            "owner discriminator is not required text",
        )
        language = languages[schema["text_language_id"]]
        _require(
            language["ordered_literals"] == expected_literals,
            "owner discriminator language literal closure differs",
        )
        return language["text_language_id"]

    _require(
        discriminator["discriminator_scope"] == "SELECTED_VALUE"
        and discriminator["discriminator_owner_type_name"] is None,
        "selected-value discriminator scope differs",
    )
    for alternative, literal in zip(alternatives, literals, strict=True):
        schema_id = _resolve_path_schema_id(
            assignments=assignments,
            schemas=schemas,
            records=records,
            type_name=alternative["referenced_type_name"],
            path=path,
        )
        schema = schemas[schema_id]
        _require(
            schema["schema_kind"] == "TEXT"
            and not schema["nullable"]
            and languages[schema["text_language_id"]]["ordered_literals"] == [literal],
            "selected alternative discriminator schema differs",
        )
    candidates = [
        language["text_language_id"]
        for language in languages.values()
        if language["ordered_literals"] == expected_literals
        and language["language_kind"] in {"LITERAL", "ENUM"}
    ]
    _require(
        len(candidates) == 1,
        "selected-value union-wide discriminator language is not unique",
    )
    return candidates[0]


def _materialize_union(
    *,
    topology: dict[str, Any],
    assignments: dict[tuple[str, tuple[str, ...]], str],
    schemas: dict[str, dict[str, Any]],
    languages: dict[str, dict[str, Any]],
    records: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    source = topology["tagged_union_topology"]
    alternatives = [
        {
            "alternative_position": item["alternative_position"],
            "alternative_name": item["alternative_name"],
            "ordered_discriminator_literals": item["ordered_discriminator_literals"],
            "referenced_type_name": item["referenced_type_name"],
        }
        for item in source["ordered_alternatives"]
    ]
    discriminators = []
    for item in source["ordered_discriminator_topology"]:
        discriminators.append(
            {
                "discriminator_position": item["discriminator_position"],
                "discriminator_scope": item["discriminator_scope"],
                "discriminator_owner_type_name": item["discriminator_owner_type_name"],
                "discriminator_typed_member_path": item[
                    "discriminator_typed_member_path"
                ],
                "text_language_id": _union_discriminator_language_id(
                    discriminator=item,
                    alternatives=alternatives,
                    assignments=assignments,
                    schemas=schemas,
                    languages=languages,
                    records=records,
                ),
            }
        )
    return {
        "payload_binding_scope": source["payload_binding_scope"],
        "payload_owner_type_name": source["payload_owner_type_name"],
        "payload_typed_member_path": source["payload_typed_member_path"],
        "ordered_discriminator_descriptors": discriminators,
        "ordered_alternatives": alternatives,
    }


def _materialize_types(
    *,
    topology: dict[str, Any],
    scalar: dict[str, Any],
    rules: dict[str, Any],
    full_schemas: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    topology_by_name = _index_unique(
        topology["type_descriptors"],
        key="type_name",
        label="topology type",
    )
    record_by_name = {
        name: item
        for name, item in topology_by_name.items()
        if item["type_form"] == "RECORD"
    }
    schemas = _index_unique(
        full_schemas,
        key="value_schema_id",
        label="value schema",
    )
    languages = _index_unique(
        scalar["ordered_text_language_descriptors"],
        key="text_language_id",
        label="text language",
    )
    assignments: dict[tuple[str, tuple[str, ...]], str] = {}
    for item in scalar["ordered_member_path_assignments"]:
        key = (item["source_type_name"], tuple(item["typed_member_path"]))
        _require(key not in assignments, "duplicate member-path assignment")
        assignments[key] = item["value_schema_id"]
    attachment_by_type = _index_unique(
        rules["ordered_intrinsic_rule_attachments"],
        key="type_name",
        label="intrinsic attachment",
    )

    descriptors = []
    for type_name in sorted(topology_by_name):
        source = topology_by_name[type_name]
        if source["type_form"] == "RECORD":
            members = [
                {
                    "member_position": item["member_position"],
                    "member_name": item["member_name"],
                    "member_role": item["member_role"],
                    "value_schema_id": assignments[(type_name, (item["member_name"],))],
                }
                for item in source["member_topology"]
            ]
            tagged_union = None
            intrinsic_ids = attachment_by_type[type_name]["ordered_intrinsic_rule_ids"]
        else:
            members = None
            tagged_union = _materialize_union(
                topology=source,
                assignments=assignments,
                schemas=schemas,
                languages=languages,
                records=record_by_name,
            )
            intrinsic_ids = []
        payload = {
            "type_name": type_name,
            "type_version_tag": source["type_version_tag"],
            "type_role": source["type_role"],
            "type_form": source["type_form"],
            "described_record_domain": source["described_record_domain"],
            "identity_field": source["identity_field"],
            "identity_payload_member_order": source["identity_payload_member_order"],
            "codec_byte_bound_relation": source["codec_byte_bound_relation"],
            "codec_octet_limit": source["codec_octet_limit"],
            "record_member_descriptors": members,
            "tagged_union_descriptor": tagged_union,
            "ordered_intrinsic_rule_ids": intrinsic_ids,
        }
        descriptors.append(
            {
                **payload,
                "external_type_descriptor_id": _semantic_id(
                    TYPE_DOMAIN,
                    payload,
                ),
            }
        )
    return descriptors


def build_registry(
    core: dict[str, Any],
    topology: dict[str, Any],
    scalar: dict[str, Any],
    rules: dict[str, Any],
) -> dict[str, Any]:
    sources = _materialize_unicode_sources(core)
    member_schemas = scalar["ordered_value_schemas"]
    additive_schemas = rules["ordered_additive_rule_value_schemas"]
    member_ids = {item["value_schema_id"] for item in member_schemas}
    additive_ids = {item["value_schema_id"] for item in additive_schemas}
    _require(
        len(member_ids) == 200
        and len(additive_ids) == 36
        and member_ids.isdisjoint(additive_ids),
        "member/additive schema partition differs",
    )
    full_schemas = sorted(
        [*member_schemas, *additive_schemas],
        key=lambda item: item["value_schema_id"],
    )
    types = _materialize_types(
        topology=topology,
        scalar=scalar,
        rules=rules,
        full_schemas=full_schemas,
    )
    names = [item["type_name"] for item in types]
    payload = {
        "external_schema_profile": EXTERNAL_SCHEMA_PROFILE,
        "unicode_source_catalog": sources,
        "identifier_profile_catalog": scalar["ordered_unicode_identifier_profiles"],
        "ascii_dfa_catalog": scalar["ordered_ascii_dfa_descriptors"],
        "text_language_catalog": scalar["ordered_text_language_descriptors"],
        "value_schema_catalog": full_schemas,
        "external_type_descriptor_count": len(types),
        "ordered_external_type_descriptors": types,
        "cross_field_rule_descriptor_count": rules["typed_rule_count"],
        "ordered_cross_field_rule_descriptors": rules["ordered_rule_descriptors"],
        "fixed_position_resolver_profile_catalog": rules[
            "ordered_fixed_position_resolver_profiles"
        ],
        "rule_application_descriptor_count": rules["rule_application_descriptor_count"],
        "ordered_rule_application_descriptors": rules[
            "ordered_rule_application_descriptors"
        ],
        "schema_graph_node_count": len(names),
        "ordered_schema_graph_node_names": names,
    }
    return {
        "canonicalization_version": CANONICALIZATION_VERSION,
        "measurement_schema_version": MEASUREMENT_SCHEMA_VERSION,
        "record_domain": REGISTRY_RECORD_DOMAIN,
        **payload,
        "external_schema_registry_id": _semantic_id(
            REGISTRY_RECORD_DOMAIN,
            payload,
        ),
    }


class StaticStructuralRegistryValidator:
    """Independent static closure validator for the structural registry."""

    def __init__(
        self,
        *,
        core: dict[str, Any],
        topology: dict[str, Any],
        scalar: dict[str, Any],
        rules: dict[str, Any],
        registry: dict[str, Any],
    ) -> None:
        self.core = core
        self.topology = topology
        self.scalar = scalar
        self.rules_dependency = rules
        self.registry = registry
        _require(set(registry) == REGISTRY_KEYS, "registry root shape differs")
        self.sources = _index_unique(
            registry["unicode_source_catalog"],
            key="unicode_source_record_id",
            label="Unicode source",
        )
        self.profiles = _index_unique(
            registry["identifier_profile_catalog"],
            key="unicode_identifier_profile_id",
            label="identifier profile",
        )
        self.dfas = _index_unique(
            registry["ascii_dfa_catalog"],
            key="ascii_dfa_id",
            label="ASCII DFA",
        )
        self.languages = _index_unique(
            registry["text_language_catalog"],
            key="text_language_id",
            label="text language",
        )
        self.schemas = _index_unique(
            registry["value_schema_catalog"],
            key="value_schema_id",
            label="value schema",
        )
        self.types = _index_unique(
            registry["ordered_external_type_descriptors"],
            key="type_name",
            label="external type",
        )
        self.rules = _index_unique(
            registry["ordered_cross_field_rule_descriptors"],
            key="rule_id",
            label="cross-field rule",
        )
        self.resolvers = _index_unique(
            registry["fixed_position_resolver_profile_catalog"],
            key="fixed_position_resolver_profile_id",
            label="resolver",
        )
        self.applications = _index_unique(
            registry["ordered_rule_application_descriptors"],
            key="application_name",
            label="application",
        )
        _require(
            all(
                "external_type_descriptor_id" in item
                for item in registry["ordered_external_type_descriptors"]
            )
            and all(
                "step2_cross_field_rule_descriptor_id" in item
                for item in registry["ordered_cross_field_rule_descriptors"]
            )
            and all(
                "rule_application_id" in item
                for item in registry["ordered_rule_application_descriptors"]
            )
            and len(
                {
                    item["external_type_descriptor_id"]
                    for item in registry["ordered_external_type_descriptors"]
                }
            )
            == len(self.types)
            and len(
                {
                    item["step2_cross_field_rule_descriptor_id"]
                    for item in registry["ordered_cross_field_rule_descriptors"]
                }
            )
            == len(self.rules)
            and len(
                {
                    item["rule_application_id"]
                    for item in registry["ordered_rule_application_descriptors"]
                }
            )
            == len(self.applications),
            "terminal type/rule/application identities are not unique",
        )

    def validate(self) -> dict[str, int]:
        self._validate_root_and_catalog_order()
        self._validate_unicode_sources_and_profiles()
        self._validate_dfas_languages_schemas()
        maximum_type_depth = self._validate_types_and_type_dag()
        self._validate_rule_resolver_application_ids()
        self._validate_catalog_closure()
        self._validate_registry_identity()
        return {"maximum_type_graph_depth": maximum_type_depth}

    def _validate_root_and_catalog_order(self) -> None:
        _require(
            self.registry["canonicalization_version"] == CANONICALIZATION_VERSION
            and self.registry["measurement_schema_version"]
            == MEASUREMENT_SCHEMA_VERSION
            and self.registry["record_domain"] == REGISTRY_RECORD_DOMAIN
            and self.registry["external_schema_profile"] == EXTERNAL_SCHEMA_PROFILE,
            "registry header differs",
        )
        ordered_ids = (
            ("unicode_source_catalog", "unicode_source_record_id"),
            ("identifier_profile_catalog", "unicode_identifier_profile_id"),
            ("ascii_dfa_catalog", "ascii_dfa_id"),
            ("text_language_catalog", "text_language_id"),
            ("value_schema_catalog", "value_schema_id"),
            (
                "ordered_cross_field_rule_descriptors",
                "step2_cross_field_rule_descriptor_id",
            ),
            (
                "fixed_position_resolver_profile_catalog",
                "fixed_position_resolver_profile_id",
            ),
        )
        for catalog_name, identifier_name in ordered_ids:
            identifiers = [
                item[identifier_name] for item in self.registry[catalog_name]
            ]
            _require(
                identifiers == sorted(identifiers),
                f"{catalog_name} semantic-ID order differs",
            )
        type_names = [
            item["type_name"]
            for item in self.registry["ordered_external_type_descriptors"]
        ]
        application_names = [
            item["application_name"]
            for item in self.registry["ordered_rule_application_descriptors"]
        ]
        _require(
            type_names == sorted(type_names)
            and type_names == self.registry["ordered_schema_graph_node_names"],
            "type/name catalog order differs",
        )
        _require(
            application_names == sorted(application_names),
            "application catalog order differs",
        )
        _require(
            self.registry["external_type_descriptor_count"] == len(type_names) == 52
            and self.registry["schema_graph_node_count"] == len(type_names) == 52
            and self.registry["cross_field_rule_descriptor_count"]
            == len(self.rules)
            == 42
            and self.registry["rule_application_descriptor_count"]
            == len(self.applications)
            == 8,
            "registry count fields differ",
        )

    def _validate_unicode_sources_and_profiles(self) -> None:
        _require(len(self.sources) == 6, "Unicode source count differs")
        expected_by_name = {
            item["source_name"]: item for item in self.core["unicode_source_specs"]
        }
        actual_by_name = {}
        for source in self.sources.values():
            _require(set(source) == SOURCE_KEYS, "Unicode source shape differs")
            payload = {
                key: value
                for key, value in source.items()
                if key != "unicode_source_record_id"
            }
            _require(
                _semantic_id(SOURCE_DOMAIN, payload)
                == source["unicode_source_record_id"],
                "Unicode source semantic ID differs",
            )
            actual_by_name[source["source_name"]] = payload
        _require(actual_by_name == expected_by_name, "Unicode source authority differs")
        ids_by_name = [actual_by_name[name] for name in sorted(actual_by_name)]
        _require(len(ids_by_name) == 6, "Unicode source-name order differs")
        expected_source_ids = [
            next(
                item["unicode_source_record_id"]
                for item in self.sources.values()
                if item["source_name"] == name
            )
            for name in sorted(actual_by_name)
        ]
        _require(len(self.profiles) == 3, "identifier profile count differs")
        for profile in self.profiles.values():
            _require(set(profile) == PROFILE_KEYS, "identifier profile shape differs")
            payload = {
                key: value
                for key, value in profile.items()
                if key != "unicode_identifier_profile_id"
            }
            _require(
                _semantic_id(PROFILE_DOMAIN, payload)
                == profile["unicode_identifier_profile_id"],
                "identifier profile semantic ID differs",
            )
            _require(
                profile["unicode_source_record_ids"] == expected_source_ids,
                "identifier profile Unicode-source order differs",
            )

    def _validate_dfas_languages_schemas(self) -> None:
        _require(
            (len(self.dfas), len(self.languages), len(self.schemas)) == (9, 103, 236),
            "DFA/language/schema counts differ",
        )
        for dfa in self.dfas.values():
            _require(set(dfa) == DFA_KEYS, "ASCII DFA shape differs")
            _require(
                all(
                    set(row) == TRANSITION_KEYS
                    for row in dfa["ordered_transition_rows"]
                ),
                "ASCII DFA transition shape differs",
            )
            payload = {
                key: value for key, value in dfa.items() if key != "ascii_dfa_id"
            }
            _require(
                _semantic_id(DFA_DOMAIN, payload) == dfa["ascii_dfa_id"],
                "ASCII DFA semantic ID differs",
            )
            self._validate_dfa_graph(dfa)
        for language in self.languages.values():
            _require(set(language) == TEXT_KEYS, "text-language shape differs")
            payload = {
                key: value
                for key, value in language.items()
                if key != "text_language_id"
            }
            _require(
                _semantic_id(TEXT_DOMAIN, payload) == language["text_language_id"],
                "text-language semantic ID differs",
            )
            kind = language["language_kind"]
            _require(
                kind
                in {
                    "LITERAL",
                    "ENUM",
                    "BUILTIN",
                    "ASCII_DFA",
                    "UNICODE_IDENTIFIER",
                },
                "text-language kind differs",
            )
            literals = language["ordered_literals"]
            if kind == "LITERAL":
                _require(len(literals) == 1, "LITERAL language cardinality differs")
            elif kind == "ENUM":
                _require(
                    len(literals) >= 2 and literals == sorted(set(literals)),
                    "ENUM language order/cardinality differs",
                )
            elif kind == "ASCII_DFA":
                _require(
                    language["ascii_dfa_id"] in self.dfas,
                    "ASCII_DFA language reference unresolved",
                )
            elif kind == "UNICODE_IDENTIFIER":
                _require(
                    language["unicode_identifier_profile_id"] in self.profiles,
                    "Unicode language profile unresolved",
                )
        for schema in self.schemas.values():
            _require(set(schema) == VALUE_KEYS, "value-schema shape differs")
            payload = {
                key: value for key, value in schema.items() if key != "value_schema_id"
            }
            _require(
                _semantic_id(VALUE_SCHEMA_DOMAIN, payload) == schema["value_schema_id"],
                "value-schema semantic ID differs",
            )
            kind = schema["schema_kind"]
            _require(type(schema["nullable"]) is bool, "schema nullability differs")
            if kind == "EXACT_BOOLEAN":
                _require(
                    schema["boolean_literal"] is None
                    or type(schema["boolean_literal"]) is bool,
                    "Boolean schema literal differs",
                )
            elif kind == "SAFE_INTEGER":
                _require(
                    type(schema["integer_minimum"]) is int
                    and type(schema["integer_maximum"]) is int
                    and 0
                    <= schema["integer_minimum"]
                    <= schema["integer_maximum"]
                    <= SAFE_UINT_MAX,
                    "safe-integer schema bounds differ",
                )
            elif kind == "TEXT":
                _require(
                    schema["text_language_id"] in self.languages,
                    "TEXT schema language unresolved",
                )
            elif kind == "ARRAY":
                _require(
                    type(schema["array_minimum_items"]) is int
                    and type(schema["array_maximum_items"]) is int
                    and 0
                    <= schema["array_minimum_items"]
                    <= schema["array_maximum_items"]
                    <= SAFE_UINT_MAX
                    and schema["array_item_value_schema_id"] in self.schemas,
                    "ARRAY item schema unresolved",
                )
            elif kind == "OBJECT_REF":
                _require(
                    schema["referenced_type_name"] in self.types,
                    "OBJECT_REF target unresolved",
                )
            else:
                raise StructuralRegistryError(f"unknown value-schema kind {kind}")
            allowed = {
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
            _require(
                all(schema[name] is None for name in constraint_names - allowed),
                "value schema carries a foreign constraint",
            )
        referenced_languages = {
            item["text_language_id"]
            for item in self.schemas.values()
            if item["schema_kind"] == "TEXT"
        }
        _require(
            referenced_languages == set(self.languages),
            "text-language reachability closure differs",
        )
        referenced_dfas = {
            item["ascii_dfa_id"]
            for item in self.languages.values()
            if item["language_kind"] == "ASCII_DFA"
        }
        referenced_profiles = {
            item["unicode_identifier_profile_id"]
            for item in self.languages.values()
            if item["language_kind"] == "UNICODE_IDENTIFIER"
        }
        _require(
            referenced_dfas == set(self.dfas)
            and referenced_profiles == set(self.profiles),
            "DFA/profile reachability closure differs",
        )

    def _validate_dfa_graph(self, dfa: dict[str, Any]) -> None:
        state_count = dfa["state_count"]
        _require(
            type(state_count) is int
            and state_count >= 1
            and type(dfa["start_state"]) is int
            and 0 <= dfa["start_state"] < state_count
            and dfa["ordered_accepting_states"]
            == sorted(set(dfa["ordered_accepting_states"]))
            and bool(dfa["ordered_accepting_states"])
            and all(
                type(state) is int and 0 <= state < state_count
                for state in dfa["ordered_accepting_states"]
            )
            and type(dfa["minimum_octets"]) is int
            and type(dfa["maximum_octets"]) is int
            and 0 <= dfa["minimum_octets"] <= dfa["maximum_octets"],
            "ASCII DFA state/bound header differs",
        )
        rows = dfa["ordered_transition_rows"]
        _require(
            rows
            == sorted(
                rows,
                key=lambda item: (
                    item["source_state"],
                    item["inclusive_byte_minimum"],
                ),
            ),
            "ASCII DFA transition order differs",
        )
        transitions: dict[int, set[int]] = {
            state: set() for state in range(state_count)
        }
        reverse: dict[int, set[int]] = {state: set() for state in range(state_count)}
        previous_maximum: dict[int, int] = {}
        for row in rows:
            source = row["source_state"]
            target = row["target_state"]
            lower = row["inclusive_byte_minimum"]
            upper = row["inclusive_byte_maximum"]
            _require(
                type(source) is int
                and type(target) is int
                and type(lower) is int
                and type(upper) is int
                and 0 <= source < state_count
                and 0 <= target < state_count
                and 0 <= lower <= upper <= 0x7F
                and lower > previous_maximum.get(source, -1),
                "ASCII DFA transition row is invalid or overlapping",
            )
            previous_maximum[source] = upper
            transitions[source].add(target)
            reverse[target].add(source)

        def reachable(start: set[int], edges: dict[int, set[int]]) -> set[int]:
            seen = set(start)
            stack = list(start)
            while stack:
                current = stack.pop()
                for target in edges[current]:
                    if target not in seen:
                        seen.add(target)
                        stack.append(target)
            return seen

        _require(
            reachable({dfa["start_state"]}, transitions) == set(range(state_count)),
            "ASCII DFA contains a start-unreachable state",
        )
        _require(
            reachable(set(dfa["ordered_accepting_states"]), reverse)
            == set(range(state_count)),
            "ASCII DFA contains a non-coaccessible state",
        )

    def _validate_types_and_type_dag(self) -> int:
        _require(len(self.types) == 52, "external type count differs")
        concrete_names = {
            item["type_name"]
            for item in self.topology["type_descriptors"]
            if item["type_form"] == "RECORD"
        }
        union_names = {
            item["type_name"]
            for item in self.topology["type_descriptors"]
            if item["type_form"] == "TAGGED_UNION"
        }
        _require(
            len(concrete_names) == 49
            and len(union_names) == 3
            and set(self.types) == concrete_names | union_names,
            "49+3 type partition differs",
        )
        _require(
            Counter(item["type_role"] for item in self.types.values())
            == Counter({"STANDALONE": 16, "NESTED": 36}),
            "standalone/nested type partition differs",
        )
        graph = {name: set() for name in self.types}
        member_schema_ids: set[str] = set()
        attached_counter: Counter[str] = Counter()
        for descriptor in self.types.values():
            _require(set(descriptor) == TYPE_KEYS, "external type shape differs")
            payload = {
                key: value
                for key, value in descriptor.items()
                if key != "external_type_descriptor_id"
            }
            _require(
                _semantic_id(TYPE_DOMAIN, payload)
                == descriptor["external_type_descriptor_id"],
                "external type semantic ID differs",
            )
            _require(
                descriptor["type_version_tag"]
                == "RAW_V8_STEP2_EXTERNAL_SCHEMA_V2/" + descriptor["type_name"],
                "external type version tag differs",
            )
            _require(
                descriptor["type_role"] in {"NESTED", "STANDALONE"}
                and descriptor["type_form"] in {"RECORD", "TAGGED_UNION"}
                and descriptor["codec_byte_bound_relation"] in {"LE", "LT"}
                and type(descriptor["codec_octet_limit"]) is int
                and 1 <= descriptor["codec_octet_limit"] <= SAFE_UINT_MAX,
                "external type role/form/codec contract differs",
            )
            if descriptor["type_form"] == "RECORD":
                members = descriptor["record_member_descriptors"]
                _require(
                    type(members) is list
                    and bool(members)
                    and descriptor["tagged_union_descriptor"] is None
                    and all(set(item) == MEMBER_KEYS for item in members),
                    "record member descriptor shape differs",
                )
                _require(
                    [item["member_position"] for item in members]
                    == list(range(1, len(members) + 1)),
                    "record member positions differ",
                )
                member_names = [item["member_name"] for item in members]
                _require(
                    len(member_names) == len(set(member_names)),
                    "record member names are not unique",
                )
                if descriptor["type_role"] == "STANDALONE":
                    _require(
                        type(descriptor["described_record_domain"]) is str
                        and bool(descriptor["described_record_domain"])
                        and type(descriptor["identity_field"]) is str
                        and bool(descriptor["identity_field"])
                        and type(descriptor["identity_payload_member_order"]) is list
                        and members[0]["member_name"] == "canonicalization_version"
                        and members[0]["member_role"] == "ENVELOPE_PREFIX"
                        and members[1]["member_name"] == "measurement_schema_version"
                        and members[1]["member_role"] == "ENVELOPE_PREFIX"
                        and members[2]["member_name"] == "record_domain"
                        and members[2]["member_role"] == "ENVELOPE_PREFIX"
                        and members[-1]["member_name"] == descriptor["identity_field"]
                        and members[-1]["member_role"] == "IDENTITY_FIELD"
                        and descriptor["identity_payload_member_order"]
                        == [
                            item["member_name"]
                            for item in members[3:-1]
                            if item["member_role"] == "IDENTITY_PAYLOAD"
                        ]
                        and all(
                            item["member_role"]
                            in {"IDENTITY_PAYLOAD", "ENVELOPE_NON_IDENTITY"}
                            for item in members[3:-1]
                        ),
                        "standalone member/identity contract differs",
                    )
                else:
                    _require(
                        descriptor["described_record_domain"] is None
                        and descriptor["identity_field"] is None
                        and descriptor["identity_payload_member_order"] is None
                        and all(
                            item["member_role"] == "NESTED_PAYLOAD" for item in members
                        ),
                        "nested record identity/member contract differs",
                    )
                _require(
                    len(descriptor["ordered_intrinsic_rule_ids"]) <= 1,
                    "record has multiple intrinsic rule attachments",
                )
                for member in members:
                    schema_id = member["value_schema_id"]
                    _require(schema_id in self.schemas, "member schema unresolved")
                    member_schema_ids.add(schema_id)
                    self._add_schema_type_edges(
                        graph[descriptor["type_name"]],
                        schema_id,
                    )
                attached_counter.update(descriptor["ordered_intrinsic_rule_ids"])
            else:
                _require(
                    descriptor["type_role"] == "NESTED"
                    and descriptor["described_record_domain"] is None
                    and descriptor["identity_field"] is None
                    and descriptor["identity_payload_member_order"] is None
                    and descriptor["record_member_descriptors"] is None
                    and descriptor["ordered_intrinsic_rule_ids"] == [],
                    "tagged-union envelope differs",
                )
                self._validate_union_descriptor(descriptor, graph)
        expected_member_ids = {
            item["value_schema_id"] for item in self.scalar["ordered_value_schemas"]
        }
        stack = list(member_schema_ids)
        while stack:
            schema_id = stack.pop()
            schema = self.schemas[schema_id]
            if (
                schema["schema_kind"] == "ARRAY"
                and schema["array_item_value_schema_id"] not in member_schema_ids
            ):
                member_schema_ids.add(schema["array_item_value_schema_id"])
                stack.append(schema["array_item_value_schema_id"])
        _require(
            member_schema_ids == expected_member_ids,
            "record-member schema closure differs",
        )
        intrinsic_rules = {
            item["rule_id"]
            for item in self.rules.values()
            if item["rule_scope"] == "INTRINSIC_RECORD"
        }
        _require(
            attached_counter == Counter(dict.fromkeys(intrinsic_rules, 1)),
            "intrinsic attachment multiplicity differs",
        )
        indegree = dict.fromkeys(graph, 0)
        successors = {name: set() for name in graph}
        for source, dependencies in graph.items():
            for dependency in dependencies:
                _require(dependency in graph, "type graph reference unresolved")
                successors[dependency].add(source)
                indegree[source] += 1
        ready = sorted(name for name, degree in indegree.items() if degree == 0)
        depth = dict.fromkeys(ready, 1)
        emitted = []
        while ready:
            current = ready.pop(0)
            emitted.append(current)
            for successor in sorted(successors[current]):
                depth[successor] = max(
                    depth.get(successor, 1),
                    depth[current] + 1,
                )
                indegree[successor] -= 1
                if indegree[successor] == 0:
                    ready.append(successor)
                    ready.sort()
        _require(len(emitted) == 52, "type graph is cyclic")
        maximum_depth = max(depth.values())
        _require(maximum_depth <= 16, "type graph depth exceeds 16")
        return maximum_depth

    def _resolve_registry_path(self, type_name: str, path: list[str]) -> str:
        _require(bool(path), "registry typed member path is empty")
        current_type = type_name
        for position, segment in enumerate(path):
            descriptor = self.types.get(current_type)
            _require(
                descriptor is not None and descriptor["type_form"] == "RECORD",
                f"registry path enters non-record {current_type}",
            )
            member = next(
                (
                    item
                    for item in descriptor["record_member_descriptors"]
                    if item["member_name"] == segment
                ),
                None,
            )
            _require(member is not None, f"registry path member {segment} unresolved")
            schema_id = member["value_schema_id"]
            if position == len(path) - 1:
                return schema_id
            schema = self.schemas[schema_id]
            _require(
                schema["schema_kind"] == "OBJECT_REF"
                and not schema["nullable"]
                and schema["referenced_type_name"] in self.types,
                "registry path crosses a non-required object",
            )
            current_type = schema["referenced_type_name"]
        raise AssertionError("unreachable")

    def _add_schema_type_edges(self, edges: set[str], schema_id: str) -> None:
        active = set()
        stack = [schema_id]
        while stack:
            current = stack.pop()
            if current in active:
                continue
            active.add(current)
            schema = self.schemas[current]
            if schema["schema_kind"] == "ARRAY":
                stack.append(schema["array_item_value_schema_id"])
            elif schema["schema_kind"] == "OBJECT_REF":
                edges.add(schema["referenced_type_name"])

    def _validate_union_descriptor(
        self,
        descriptor: dict[str, Any],
        graph: dict[str, set[str]],
    ) -> None:
        union = descriptor["tagged_union_descriptor"]
        _require(
            type(union) is dict and set(union) == UNION_KEYS, "union shape differs"
        )
        discriminators = union["ordered_discriminator_descriptors"]
        alternatives = union["ordered_alternatives"]
        scope = union["payload_binding_scope"]
        if scope == "OWNER_MEMBER":
            owner = union["payload_owner_type_name"]
            path = union["payload_typed_member_path"]
            _require(
                owner in self.types
                and self.types[owner]["type_form"] == "RECORD"
                and bool(path),
                "owner-member union payload binding differs",
            )
            payload_schema = self.schemas[self._resolve_registry_path(owner, path)]
            _require(
                payload_schema["schema_kind"] == "OBJECT_REF"
                and not payload_schema["nullable"]
                and payload_schema["referenced_type_name"] == descriptor["type_name"],
                "owner-member union payload path target differs",
            )
        else:
            _require(
                scope == "SELF_VALUE"
                and union["payload_owner_type_name"] is None
                and union["payload_typed_member_path"] == [],
                "self-value union payload binding differs",
            )
        _require(
            type(discriminators) is list
            and bool(discriminators)
            and all(set(item) == DISCRIMINATOR_KEYS for item in discriminators)
            and [item["discriminator_position"] for item in discriminators]
            == list(range(1, len(discriminators) + 1)),
            "union discriminator catalog differs",
        )
        _require(
            type(alternatives) is list
            and bool(alternatives)
            and all(set(item) == ALTERNATIVE_KEYS for item in alternatives)
            and [item["alternative_position"] for item in alternatives]
            == list(range(1, len(alternatives) + 1)),
            "union alternative catalog differs",
        )
        tuples = []
        for alternative in alternatives:
            _require(
                alternative["referenced_type_name"] in self.types
                and self.types[alternative["referenced_type_name"]]["type_form"]
                == "RECORD"
                and len(alternative["ordered_discriminator_literals"])
                == len(discriminators)
                and all(
                    set(item) == DISCRIMINATOR_LITERAL_KEYS
                    for item in alternative["ordered_discriminator_literals"]
                ),
                "union alternative target/literal shape differs",
            )
            values = tuple(
                item["text_value"]
                for item in alternative["ordered_discriminator_literals"]
            )
            tuples.append(values)
            graph[descriptor["type_name"]].add(alternative["referenced_type_name"])
        _require(len(tuples) == len(set(tuples)), "union literal tuples duplicate")
        for position, discriminator in enumerate(discriminators):
            language = self.languages.get(discriminator["text_language_id"])
            _require(
                language is not None
                and language["language_kind"] in {"LITERAL", "ENUM"},
                "union discriminator language is not closed",
            )
            expected_name = discriminator["discriminator_typed_member_path"][-1]
            discriminator_scope = discriminator["discriminator_scope"]
            if discriminator_scope == "OWNER_OBJECT":
                _require(
                    scope == "OWNER_MEMBER"
                    and discriminator["discriminator_owner_type_name"]
                    == union["payload_owner_type_name"],
                    "owner discriminator owner/scope differs",
                )
                source_schema = self.schemas[
                    self._resolve_registry_path(
                        discriminator["discriminator_owner_type_name"],
                        discriminator["discriminator_typed_member_path"],
                    )
                ]
                _require(
                    source_schema["schema_kind"] == "TEXT"
                    and not source_schema["nullable"]
                    and source_schema["text_language_id"]
                    == discriminator["text_language_id"],
                    "owner discriminator path language differs",
                )
            else:
                _require(
                    discriminator_scope == "SELECTED_VALUE"
                    and scope == "SELF_VALUE"
                    and discriminator["discriminator_owner_type_name"] is None,
                    "selected-value discriminator owner/scope differs",
                )
            values = []
            for alternative in alternatives:
                literal = alternative["ordered_discriminator_literals"][position]
                _require(
                    literal["member_name"] == expected_name,
                    "union discriminator literal member differs",
                )
                values.append(literal["text_value"])
                if discriminator_scope == "SELECTED_VALUE":
                    selected_schema = self.schemas[
                        self._resolve_registry_path(
                            alternative["referenced_type_name"],
                            discriminator["discriminator_typed_member_path"],
                        )
                    ]
                    _require(
                        selected_schema["schema_kind"] == "TEXT"
                        and not selected_schema["nullable"]
                        and self.languages[selected_schema["text_language_id"]][
                            "ordered_literals"
                        ]
                        == [literal["text_value"]],
                        "selected-value alternative discriminator differs",
                    )
            _require(
                language["ordered_literals"] == sorted(values),
                "union discriminator language closure differs",
            )

    def _validate_rule_resolver_application_ids(self) -> None:
        _require(
            (len(self.rules), len(self.resolvers), len(self.applications))
            == (42, 2, 8),
            "rule/resolver/application counts differ",
        )
        for rule in self.rules.values():
            _require(
                set(rule) == RULE_KEYS
                and type(rule["ordered_rule_input_bindings"]) is list
                and type(rule["ordered_expression_nodes"]) is list
                and all(
                    set(item) == RULE_BINDING_KEYS
                    for item in rule["ordered_rule_input_bindings"]
                )
                and all(
                    set(item) == EXPRESSION_NODE_KEYS
                    for item in rule["ordered_expression_nodes"]
                ),
                "rule/binding/expression shape differs",
            )
            payload = {
                key: value
                for key, value in rule.items()
                if key != "step2_cross_field_rule_descriptor_id"
            }
            _require(
                _semantic_id(RULE_DOMAIN, payload)
                == rule["step2_cross_field_rule_descriptor_id"],
                "rule semantic ID differs",
            )
        for resolver in self.resolvers.values():
            _require(
                set(resolver) == RESOLVER_KEYS
                and type(resolver["ordered_source_identity_path_descriptors"]) is list
                and all(
                    set(item) == RESOLVER_PATH_KEYS
                    for item in resolver["ordered_source_identity_path_descriptors"]
                ),
                "resolver/path shape differs",
            )
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
        cross_rules = {
            item["rule_id"]
            for item in self.rules.values()
            if item["rule_scope"] == "CROSS_RECORD"
        }
        application_rules = Counter()
        resolver_references = set()
        for application in self.applications.values():
            _require(
                set(application) == APPLICATION_KEYS
                and type(application["ordered_root_input_bindings"]) is list
                and type(application["ordered_sequence_input_bindings"]) is list
                and all(
                    set(item) == ROOT_BINDING_KEYS
                    for item in application["ordered_root_input_bindings"]
                )
                and all(
                    set(item) == SEQUENCE_BINDING_KEYS
                    for item in application["ordered_sequence_input_bindings"]
                ),
                "application/root/sequence binding shape differs",
            )
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
            application_rules[application["rule_id"]] += 1
            resolver_references.update(
                item["fixed_position_resolver_profile_id"]
                for item in application["ordered_sequence_input_bindings"]
                if item["fixed_position_resolver_profile_id"] is not None
            )
        _require(
            application_rules == Counter(dict.fromkeys(cross_rules, 1)),
            "cross-rule application multiplicity differs",
        )
        _require(
            resolver_references == set(self.resolvers),
            "resolver application reachability differs",
        )

    def _validate_catalog_closure(self) -> None:
        member_ids = {
            item["value_schema_id"] for item in self.scalar["ordered_value_schemas"]
        }
        additive_ids = {
            item["value_schema_id"]
            for item in self.rules_dependency["ordered_additive_rule_value_schemas"]
        }
        _require(
            member_ids.isdisjoint(additive_ids)
            and member_ids | additive_ids == set(self.schemas),
            "member/additive/full schema closure differs",
        )
        referenced = set(member_ids)
        for rule in self.rules.values():
            referenced.update(
                item["expected_value_schema_id"]
                for item in rule["ordered_rule_input_bindings"]
            )
            referenced.update(
                item["result_value_schema_id"]
                for item in rule["ordered_expression_nodes"]
                if item["result_type_kind"] == "VALUE_SCHEMA"
            )
            referenced.update(
                item["literal_value_schema_id"]
                for item in rule["ordered_expression_nodes"]
                if item["literal_value_schema_id"] is not None
            )
        reachable = set()
        stack = list(referenced)
        while stack:
            schema_id = stack.pop()
            _require(schema_id in self.schemas, "schema closure reference unresolved")
            if schema_id in reachable:
                continue
            reachable.add(schema_id)
            schema = self.schemas[schema_id]
            if schema["schema_kind"] == "ARRAY":
                stack.append(schema["array_item_value_schema_id"])
        _require(reachable == set(self.schemas), "value-schema reachability differs")

    def _validate_registry_identity(self) -> None:
        payload_names = (
            "external_schema_profile",
            "unicode_source_catalog",
            "identifier_profile_catalog",
            "ascii_dfa_catalog",
            "text_language_catalog",
            "value_schema_catalog",
            "external_type_descriptor_count",
            "ordered_external_type_descriptors",
            "cross_field_rule_descriptor_count",
            "ordered_cross_field_rule_descriptors",
            "fixed_position_resolver_profile_catalog",
            "rule_application_descriptor_count",
            "ordered_rule_application_descriptors",
            "schema_graph_node_count",
            "ordered_schema_graph_node_names",
        )
        payload = {name: self.registry[name] for name in payload_names}
        _require(
            _semantic_id(REGISTRY_RECORD_DOMAIN, payload)
            == self.registry["external_schema_registry_id"],
            "external schema registry identity differs",
        )


def validate_materialized_registry(
    *,
    core: dict[str, Any],
    topology: dict[str, Any],
    scalar: dict[str, Any],
    rules: dict[str, Any],
    registry: dict[str, Any],
) -> dict[str, int]:
    evidence = StaticStructuralRegistryValidator(
        core=core,
        topology=topology,
        scalar=scalar,
        rules=rules,
        registry=registry,
    ).validate()
    _require(
        registry == build_registry(core, topology, scalar, rules),
        "structural registry differs from the explicit accepted-ledger assembly",
    )
    return evidence


def validate_registry_file(
    *,
    repository_root: Path,
    registry_path: Path,
) -> dict[str, Any]:
    core, topology, scalar, rules = _load_dependencies(repository_root)
    registry, raw = _load_document(
        registry_path,
        maximum_octets=REGISTRY_EXCLUSIVE_OCTET_LIMIT,
        exclusive=True,
    )
    evidence = validate_materialized_registry(
        core=core,
        topology=topology,
        scalar=scalar,
        rules=rules,
        registry=registry,
    )
    _require(len(raw) == REGISTRY_OCTETS, "structural registry octets differ")
    _require(_sha256(raw) == REGISTRY_SHA256, "structural registry digest differs")
    return {
        "ascii_dfa_count": len(registry["ascii_dfa_catalog"]),
        "component_status": STRUCTURAL_STATUS,
        "cross_field_rule_descriptor_count": registry[
            "cross_field_rule_descriptor_count"
        ],
        "external_schema_registry_id": registry["external_schema_registry_id"],
        "external_type_descriptor_count": registry["external_type_descriptor_count"],
        "identifier_profile_count": len(registry["identifier_profile_catalog"]),
        "maximum_type_graph_depth": evidence["maximum_type_graph_depth"],
        "registry_octets": len(raw),
        "registry_path": str(registry_path),
        "registry_sha256": _sha256(raw),
        "rule_application_descriptor_count": registry[
            "rule_application_descriptor_count"
        ],
        "schema_graph_node_count": registry["schema_graph_node_count"],
        "text_language_count": len(registry["text_language_catalog"]),
        "unicode_source_count": len(registry["unicode_source_catalog"]),
        "value_schema_count": len(registry["value_schema_catalog"]),
    }


def _write_expected_registry(
    *,
    repository_root: Path,
    output: Path,
) -> None:
    core, topology, scalar, rules = _load_dependencies(repository_root)
    registry = build_registry(core, topology, scalar, rules)
    validate_materialized_registry(
        core=core,
        topology=topology,
        scalar=scalar,
        rules=rules,
        registry=registry,
    )
    raw = _pretty_bytes(registry)
    _require(
        len(raw) < REGISTRY_EXCLUSIVE_OCTET_LIMIT,
        "generated structural registry reaches its exclusive bound",
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(raw)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path.cwd(),
    )
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--write-expected-registry", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    repository_root = arguments.repository_root.resolve()
    try:
        _require(
            not (
                arguments.registry is not None
                and arguments.write_expected_registry is not None
            ),
            "--registry and --write-expected-registry are mutually exclusive",
        )
        if arguments.write_expected_registry is not None:
            _write_expected_registry(
                repository_root=repository_root,
                output=arguments.write_expected_registry,
            )
            return 0
        registry_path = (
            arguments.registry
            if arguments.registry is not None
            else repository_root / REGISTRY_RELATIVE_PATH
        )
        report = validate_registry_file(
            repository_root=repository_root,
            registry_path=registry_path,
        )
    except (
        AssertionError,
        AttributeError,
        IndexError,
        KeyError,
        OSError,
        StructuralRegistryError,
        TypeError,
        UnicodeError,
        ValueError,
    ) as exc:
        print(
            f"Raw-V8 Step-2 structural External Schema V2 error: {exc}",
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

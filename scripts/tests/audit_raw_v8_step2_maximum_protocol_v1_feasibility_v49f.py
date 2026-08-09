#!/usr/bin/env python3
"""Prove that the rejected Raw-V8 Step-2 maximum protocol V1 cannot seed.

This audit is intentionally smaller than the maximum-protocol checker.  It
reads only pinned authorities, follows one descriptor path, and establishes a
strict pre-search lower bound.  No producer artifact, witness, frontier, or
solver output participates in the result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any, Final

PROTOCOL_RELATIVE_PATH: Final = (
    "docs/research/"
    "v4_9f_a2_raw_v8_step2_constructive_maximum_protocol_freeze_2026-08-01.md"
)
REGISTRY_RELATIVE_PATH: Final = (
    "scripts/tests/raw_v8_step2_external_schema_v2_structural_registry_v49f.json"
)

PROTOCOL_OCTETS: Final = 246_093
PROTOCOL_SHA256: Final = (
    "b3b39b3cb15caa450d9974925db9b5f0b91dd5832a462d2a8687dc19a50c4409"
)
REGISTRY_OCTETS: Final = 1_469_663
REGISTRY_SHA256: Final = (
    "9160297ff316c5931737c92f8b359f0a1e2ec22f0aa996ef3b09cf830dc96bf3"
)
REGISTRY_SEMANTIC_ID: Final = (
    "5dc95a3e99c5646e912b6a7e9c3970cf2489d560ea890b0a19d38af4c51c2140"
)

TARGET_REGISTRY_TYPE: Final = "TargetFieldRegistryV1"
TARGET_DESCRIPTOR_TYPE: Final = "CapacityMeasurementTargetFieldDescriptorV1"
RAW_STRING_LANGUAGE_ID: Final = (
    "eb311c28e0711cd6f7e5f21119366b18881a30ef6dd56d8626c5cfea2d5bc727"
)
EXPECTED_INTRINSIC_ROW_POSITION: Final = 62
EXPECTED_TARGET_REGISTRY_DESCRIPTOR_POSITION: Final = 48
EXPECTED_DESCRIPTOR_COUNT: Final = 185
EXPECTED_KEY_CARDINALITY_MAXIMUM: Final = 512
SEED_COMPONENT_COORDINATE_CAP: Final = 65_536
SEED_PROOF_NODE_CAP: Final = 65_536
SEED_MAXIMUM_PROOF_DEPTH_CAP: Final = 65_536


class FeasibilityAuditError(ValueError):
    """A pinned authority or the exact lower-bound derivation differs."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FeasibilityAuditError(message)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read_pinned_regular_file(
    path: Path,
    *,
    repository_root: Path,
    expected_octets: int,
    expected_sha256: str,
    label: str,
) -> bytes:
    root = repository_root.resolve(strict=True)
    candidate = path if path.is_absolute() else root / path
    parent = candidate.parent.resolve(strict=True)
    _require(
        parent == root or root in parent.parents,
        f"{label} escapes the repository root",
    )
    # O_NONBLOCK is inert for regular files and prevents an attacker-controlled
    # FIFO from blocking before fstat can reject the non-regular leaf.
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    parent_flags = (
        os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_DIRECTORY", 0)
    )
    parent_descriptor = os.open(parent, parent_flags)
    try:
        descriptor = os.open(candidate.name, flags, dir_fd=parent_descriptor)
    except OSError as exc:
        os.close(parent_descriptor)
        raise FeasibilityAuditError(f"{label} cannot be opened safely") from exc
    os.close(parent_descriptor)
    try:
        before = os.fstat(descriptor)
        _require(stat.S_ISREG(before.st_mode), f"{label} is not a regular file")
        _require(before.st_size == expected_octets, f"{label} octet pin differs")
        chunks: list[bytes] = []
        remaining = expected_octets
        while remaining:
            chunk = os.read(descriptor, min(1_048_576, remaining))
            _require(bool(chunk), f"{label} ended before its pinned length")
            chunks.append(chunk)
            remaining -= len(chunk)
        _require(os.read(descriptor, 1) == b"", f"{label} exceeds its pinned length")
        after = os.fstat(descriptor)
        _require(
            (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns),
            f"{label} changed during the read",
        )
    finally:
        os.close(descriptor)
    raw = b"".join(chunks)
    _require(_sha256(raw) == expected_sha256, f"{label} SHA-256 pin differs")
    return raw


def _decode_json(raw: bytes, *, label: str) -> dict[str, Any]:
    def reject_duplicate(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            _require(key not in result, f"{label} repeats object member {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(
            raw,
            object_pairs_hook=reject_duplicate,
            parse_float=lambda _: (_ for _ in ()).throw(
                FeasibilityAuditError(f"{label} contains a float")
            ),
            parse_constant=lambda _: (_ for _ in ()).throw(
                FeasibilityAuditError(f"{label} contains a non-I-JSON number")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FeasibilityAuditError(f"{label} is not strict JSON") from exc
    _require(type(value) is dict, f"{label} root is not an object")
    return value


def _unique_named(
    values: Any,
    *,
    key: str,
    expected: str,
    label: str,
) -> dict[str, Any]:
    _require(type(values) is list, f"{label} catalog is not an array")
    matches = [
        item for item in values if type(item) is dict and item.get(key) == expected
    ]
    _require(len(matches) == 1, f"{label} does not contain one exact {expected}")
    return matches[0]


def _member(
    descriptor: dict[str, Any],
    *,
    member_name: str,
    member_position: int,
    label: str,
) -> dict[str, Any]:
    members = descriptor.get("record_member_descriptors")
    _require(type(members) is list, f"{label} members are unavailable")
    _require(
        all(type(item) is dict for item in members),
        f"{label} member descriptor differs",
    )
    matches = [item for item in members if item.get("member_name") == member_name]
    _require(len(matches) == 1, f"{label} member {member_name} does not resolve once")
    result = matches[0]
    _require(
        result.get("member_position") == member_position,
        f"{label} member {member_name} position differs",
    )
    return result


def _schema(
    schemas: Any,
    schema_id: Any,
    *,
    label: str,
) -> dict[str, Any]:
    _require(type(schema_id) is str and len(schema_id) == 64, f"{label} ID differs")
    return _unique_named(
        schemas,
        key="value_schema_id",
        expected=schema_id,
        label=label,
    )


def derive_target_registry_plan_lower_bound(registry: dict[str, Any]) -> dict[str, int]:
    """Derive the unavoidable coordinate/prefix count without enumeration."""

    _require(
        registry.get("external_schema_registry_id") == REGISTRY_SEMANTIC_ID,
        "registry semantic identity differs",
    )
    descriptors = registry.get("ordered_external_type_descriptors")
    _require(type(descriptors) is list, "external type descriptors are unavailable")
    target_descriptor_positions = [
        position
        for position, item in enumerate(descriptors, 1)
        if type(item) is dict and item.get("type_name") == TARGET_REGISTRY_TYPE
    ]
    _require(
        len(target_descriptor_positions) == 1,
        "TargetFieldRegistryV1 descriptor does not resolve once",
    )
    target_descriptor_position = target_descriptor_positions[0]
    _require(
        target_descriptor_position == EXPECTED_TARGET_REGISTRY_DESCRIPTOR_POSITION,
        "TargetFieldRegistryV1 external descriptor position differs",
    )
    intrinsic_row_position = 0
    for descriptor_position, descriptor in enumerate(descriptors, 1):
        _require(type(descriptor) is dict, "external type descriptor differs")
        if descriptor.get("type_form") == "RECORD":
            intrinsic_row_position += 1
        elif descriptor.get("type_form") == "TAGGED_UNION":
            union = descriptor.get("tagged_union_descriptor")
            alternatives = (
                union.get("ordered_alternatives") if type(union) is dict else None
            )
            _require(
                type(alternatives) is list and alternatives,
                "tagged-union alternatives differ",
            )
            intrinsic_row_position += len(alternatives)
        else:
            raise FeasibilityAuditError("external type form differs")
        if descriptor_position == target_descriptor_position:
            break
    _require(
        intrinsic_row_position == EXPECTED_INTRINSIC_ROW_POSITION,
        "TargetFieldRegistryV1 intrinsic row position differs",
    )
    target_registry = descriptors[target_descriptor_position - 1]
    _require(
        target_registry.get("type_form") == "RECORD"
        and target_registry.get("type_role") == "STANDALONE",
        "target registry record/type role differs",
    )
    descriptor_member = _member(
        target_registry,
        member_name="descriptors",
        member_position=11,
        label=TARGET_REGISTRY_TYPE,
    )
    _require(
        descriptor_member.get("member_role") == "IDENTITY_PAYLOAD",
        "target-registry descriptors member role differs",
    )
    schemas = registry.get("value_schema_catalog")
    descriptor_array = _schema(
        schemas,
        descriptor_member.get("value_schema_id"),
        label="target-registry descriptor-array schema",
    )
    _require(
        descriptor_array.get("schema_kind") == "ARRAY"
        and descriptor_array.get("nullable") is False
        and descriptor_array.get("array_minimum_items") == EXPECTED_DESCRIPTOR_COUNT
        and descriptor_array.get("array_maximum_items") == EXPECTED_DESCRIPTOR_COUNT,
        "target-registry descriptor-array authority differs",
    )
    descriptor_item = _schema(
        schemas,
        descriptor_array.get("array_item_value_schema_id"),
        label="target-registry descriptor-item schema",
    )
    _require(
        descriptor_item.get("schema_kind") == "OBJECT_REF"
        and descriptor_item.get("nullable") is False
        and descriptor_item.get("referenced_type_name") == TARGET_DESCRIPTOR_TYPE,
        "target-registry descriptor-item authority differs",
    )
    target_descriptor = _unique_named(
        descriptors,
        key="type_name",
        expected=TARGET_DESCRIPTOR_TYPE,
        label="target-field descriptor",
    )
    _require(
        target_descriptor.get("type_form") == "RECORD"
        and target_descriptor.get("type_role") == "NESTED",
        "target descriptor record/type role differs",
    )
    keys_member = _member(
        target_descriptor,
        member_name="value_shape_keys",
        member_position=14,
        label=TARGET_DESCRIPTOR_TYPE,
    )
    _require(
        keys_member.get("member_role") == "NESTED_PAYLOAD",
        "value-shape-key member role differs",
    )
    key_array = _schema(
        schemas,
        keys_member.get("value_schema_id"),
        label="value-shape-key array schema",
    )
    _require(
        key_array.get("schema_kind") == "ARRAY"
        and key_array.get("nullable") is False
        and key_array.get("array_minimum_items") == 0
        and key_array.get("array_maximum_items") == EXPECTED_KEY_CARDINALITY_MAXIMUM,
        "value-shape-key array authority differs",
    )
    key_item = _schema(
        schemas,
        key_array.get("array_item_value_schema_id"),
        label="value-shape-key item schema",
    )
    _require(
        key_item.get("schema_kind") == "TEXT"
        and key_item.get("nullable") is False
        and key_item.get("text_language_id") == RAW_STRING_LANGUAGE_ID,
        "value-shape-key text authority differs",
    )
    language = _unique_named(
        registry.get("text_language_catalog"),
        key="text_language_id",
        expected=RAW_STRING_LANGUAGE_ID,
        label="raw canonical JSON string language",
    )
    _require(
        language.get("language_kind") == "BUILTIN"
        and language.get("built_in_language_kind") == "RAW_CANONICAL_JSON_STRING"
        and language.get("ordered_literals") == []
        and language.get("ordering_semantics") == "UNICODE_SCALAR_LEXICOGRAPHIC",
        "raw canonical JSON string language authority differs",
    )
    unused_language_parameters = (
        "ascii_dfa_id",
        "decimal_maximum",
        "maximum_decoded_octets",
        "maximum_utf8_octets",
        "minimum_decoded_octets",
        "minimum_utf8_octets",
        "unicode_identifier_profile_id",
    )
    _require(
        all(
            name in language and language[name] is None
            for name in unused_language_parameters
        ),
        "raw canonical JSON string unused language parameter differs",
    )

    per_descriptor = 1 + EXPECTED_KEY_CARDINALITY_MAXIMUM
    coordinate_lower_bound = EXPECTED_DESCRIPTOR_COUNT * per_descriptor
    # The V1 tie-break subgraph contains exactly one maximum-slice node plus
    # one chained prefix node per coordinate.  Descriptor/rule nodes and the
    # codec-attainment root can only increase both total nodes and depth.
    tie_break_node_lower_bound = coordinate_lower_bound + 1
    return {
        "external_type_descriptor_position": target_descriptor_position,
        "outer_fixed_descriptor_occurrence_count": EXPECTED_DESCRIPTOR_COUNT,
        "inner_array_cardinality_coordinate_count": EXPECTED_DESCRIPTOR_COUNT,
        "inner_text_coordinate_count": (
            EXPECTED_DESCRIPTOR_COUNT * EXPECTED_KEY_CARDINALITY_MAXIMUM
        ),
        "component_choice_coordinate_lower_bound": coordinate_lower_bound,
        "prefix_proof_node_lower_bound": coordinate_lower_bound,
        "tie_break_proof_node_lower_bound": tie_break_node_lower_bound,
        "maximum_proof_depth_lower_bound": tie_break_node_lower_bound,
    }


def _validate_protocol_semantics(raw: bytes) -> None:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FeasibilityAuditError("protocol is not UTF-8") from exc
    required_fragments = (
        "Status: **REJECTED — PRE-SEARCH PLAN EXCEEDS IMMUTABLE SEED CAPS**",
        "array with at least two legal cardinalities",
        "noncatalog text language containing at least two values",
        "The later prefix chain has one node for every plan coordinate.",
        "Add the exact maximum-slice node and one lexicographic prefix-exclusion node",
        "must not depend on codec survival, intrinsic or",
        "| `proof_node_count` | 65,536 |",
        "| `maximum_proof_depth` | 65,536 |",
        "| `component_choice_coordinate_count` | 65,536 |",
    )
    for fragment in required_fragments:
        _require(fragment in text, f"protocol semantic fragment is absent: {fragment}")


def audit(repository_root: Path) -> dict[str, Any]:
    protocol_raw = _read_pinned_regular_file(
        Path(PROTOCOL_RELATIVE_PATH),
        repository_root=repository_root,
        expected_octets=PROTOCOL_OCTETS,
        expected_sha256=PROTOCOL_SHA256,
        label="rejected maximum protocol V1",
    )
    _validate_protocol_semantics(protocol_raw)
    registry_raw = _read_pinned_regular_file(
        Path(REGISTRY_RELATIVE_PATH),
        repository_root=repository_root,
        expected_octets=REGISTRY_OCTETS,
        expected_sha256=REGISTRY_SHA256,
        label="external-schema V2 registry",
    )
    registry = _decode_json(registry_raw, label="external-schema V2 registry")
    lower_bound = derive_target_registry_plan_lower_bound(registry)
    coordinate_lower_bound = lower_bound["component_choice_coordinate_lower_bound"]
    prefix_node_lower_bound = lower_bound["prefix_proof_node_lower_bound"]
    proof_node_lower_bound = lower_bound["tie_break_proof_node_lower_bound"]
    maximum_depth_lower_bound = lower_bound["maximum_proof_depth_lower_bound"]
    _require(
        coordinate_lower_bound > SEED_COMPONENT_COORDINATE_CAP,
        "component-coordinate lower bound no longer exceeds the seed cap",
    )
    _require(
        proof_node_lower_bound > SEED_PROOF_NODE_CAP,
        "tie-break proof-node lower bound no longer exceeds the seed cap",
    )
    _require(
        maximum_depth_lower_bound > SEED_MAXIMUM_PROOF_DEPTH_CAP,
        "maximum-proof-depth lower bound no longer exceeds the seed cap",
    )
    return {
        "audit_result": "PASS",
        "finding_id": "RAW_V8_STEP2_MAXIMUM_PROTOCOL_V1_PRESEARCH_CAP_CONTRADICTION",
        "protocol_decision": "REJECTED",
        "protocol_octets": len(protocol_raw),
        "protocol_sha256": _sha256(protocol_raw),
        "registry_octets": len(registry_raw),
        "registry_sha256": _sha256(registry_raw),
        "registry_semantic_id": registry["external_schema_registry_id"],
        "intrinsic_row_position": EXPECTED_INTRINSIC_ROW_POSITION,
        "type_name": TARGET_REGISTRY_TYPE,
        **lower_bound,
        "seed_component_choice_coordinate_cap": SEED_COMPONENT_COORDINATE_CAP,
        "seed_proof_node_cap": SEED_PROOF_NODE_CAP,
        "seed_maximum_proof_depth_cap": SEED_MAXIMUM_PROOF_DEPTH_CAP,
        "component_coordinate_cap_excess": (
            coordinate_lower_bound - SEED_COMPONENT_COORDINATE_CAP
        ),
        "proof_node_cap_excess_before_base_nodes": (
            prefix_node_lower_bound - SEED_PROOF_NODE_CAP
        ),
        "tie_break_proof_node_cap_excess_before_descriptor_and_root_nodes": (
            proof_node_lower_bound - SEED_PROOF_NODE_CAP
        ),
        "maximum_proof_depth_cap_excess_before_descriptor_and_root_nodes": (
            maximum_depth_lower_bound - SEED_MAXIMUM_PROOF_DEPTH_CAP
        ),
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        report = audit(args.repository_root)
    except (FeasibilityAuditError, OSError) as exc:
        sys.stderr.write(
            f"Raw-V8 Step-2 maximum protocol V1 feasibility audit error: {exc}\n"
        )
        return 1
    sys.stdout.write(json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

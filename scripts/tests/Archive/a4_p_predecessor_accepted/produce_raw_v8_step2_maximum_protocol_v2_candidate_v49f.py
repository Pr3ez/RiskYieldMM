#!/usr/bin/env python3
"""Produce the bounded Raw V8 Step-2 V2 case-5 candidate bundle."""

import hashlib
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

SOURCE_MARKER = "SEPARATE_V2_CONSTRUCTIVE_PRODUCER_V1"

BOUNDARY_RELATIVE_PATH = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_constructive_boundary_v49f.json"
)
PRODUCER_RELATIVE_PATH = (
    "scripts/tests/produce_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py"
)
BOUNDARY_ID = "bdc7363ae28dfe9a1c1dc132808cb1bd4a06c409201cd49b31e394893142a7ed"
BOUNDARY_RAW_OCTETS = 27334
BOUNDARY_RAW_SHA256 = "05468ec3411869fc5b4b5c60d2820e58f8ebf0af96dea978f06d92705fe3bb2b"
BOUNDARY_IDENTITY_DOMAIN = "RiskYieldMMStep2ConstructiveExecutionBoundaryV1V4_9F_RawV8"
CASE_POSITION = 5
CASE_KIND = "MAXIMUM_PUBLICATION_ROW"
CASE_TYPE_NAME = "CapacityMeasurementBoolValueV1"

INVOCATION_PREFIX = "RAW_V8_STEP2_MAXIMUM_PROTOCOL_V2_PRODUCER_INVOCATION_INVALID: "
REJECTION_PREFIX = "RAW_V8_STEP2_MAXIMUM_PROTOCOL_V2_PRODUCER_REJECTED: "

SAFE_INTEGER_MAXIMUM = (1 << 53) - 1
INITIAL_FILE_LIMIT = 16 * 1024 * 1024
INITIAL_NODE_LIMIT = 2 * 1024 * 1024
INITIAL_ARRAY_LIMIT = 1024 * 1024
INITIAL_MEMBER_LIMIT = 1024 * 1024
INITIAL_DEPTH_LIMIT = 96


class InvocationReject(Exception):
    """The fixed CLI contract was not satisfied."""


class ProducerReject(Exception):
    """A frozen authority, derivation, or publication condition failed."""


def _reject(code: str) -> None:
    raise ProducerReject(code)


def _require(condition: bool, code: str) -> None:
    if not condition:
        _reject(code)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeError) as error:
        raise ProducerReject("CANONICALIZATION_FAILED") from error


def _pretty_bytes(value: Any) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                indent=2,
            )
            + "\n"
        ).encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeError) as error:
        raise ProducerReject("PHYSICAL_ENCODING_FAILED") from error


def _semantic_id(domain: str, payload: Any) -> str:
    return _sha256(_canonical_bytes({"domain": domain, "payload": payload}))


def _duplicate_key_guard(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _reject("DUPLICATE_JSON_MEMBER")
        result[key] = value
    return result


def _reject_float(_value: str) -> Any:
    _reject("NON_INTEGER_JSON_NUMBER")


def _parse_integer(value: str) -> int:
    if value == "-0":
        _reject("NEGATIVE_ZERO")
    try:
        parsed = int(value, 10)
    except ValueError as error:
        raise ProducerReject("INVALID_INTEGER") from error
    _require(-SAFE_INTEGER_MAXIMUM <= parsed <= SAFE_INTEGER_MAXIMUM, "UNSAFE_INTEGER")
    return parsed


def _validate_json_domain(
    value: Any,
    *,
    node_limit: int,
    array_limit: int,
    member_limit: int,
    depth_limit: int,
) -> None:
    stack: list[tuple[Any, int]] = [(value, 1)]
    node_count = 0
    array_count = 0
    member_count = 0
    while stack:
        current, depth = stack.pop()
        node_count += 1
        _require(node_count <= node_limit, "JSON_NODE_LIMIT")
        _require(depth <= depth_limit, "JSON_DEPTH_LIMIT")
        if type(current) is dict:
            member_count += len(current)
            _require(member_count <= member_limit, "JSON_MEMBER_LIMIT")
            for key, item in current.items():
                _require(type(key) is str, "NON_TEXT_JSON_MEMBER")
                try:
                    key.encode("utf-8", errors="strict")
                except UnicodeError as error:
                    raise ProducerReject("INVALID_MEMBER_UNICODE") from error
                stack.append((item, depth + 1))
        elif type(current) is list:
            array_count += len(current)
            _require(array_count <= array_limit, "JSON_ARRAY_LIMIT")
            for item in current:
                stack.append((item, depth + 1))
        elif type(current) is str:
            try:
                current.encode("utf-8", errors="strict")
            except UnicodeError as error:
                raise ProducerReject("INVALID_TEXT_UNICODE") from error
        else:
            _require(
                current is None or type(current) is bool or type(current) is int,
                "INVALID_JSON_VALUE",
            )
            if type(current) is int:
                _require(
                    -SAFE_INTEGER_MAXIMUM <= current <= SAFE_INTEGER_MAXIMUM,
                    "UNSAFE_INTEGER",
                )


def _strict_json(
    raw: bytes,
    *,
    require_pretty: bool = False,
    node_limit: int = INITIAL_NODE_LIMIT,
    array_limit: int = INITIAL_ARRAY_LIMIT,
    member_limit: int = INITIAL_MEMBER_LIMIT,
    depth_limit: int = INITIAL_DEPTH_LIMIT,
) -> dict[str, Any]:
    _require(not raw.startswith(b"\xef\xbb\xbf"), "JSON_BOM")
    try:
        text = raw.decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=_duplicate_key_guard,
            parse_int=_parse_integer,
            parse_float=_reject_float,
            parse_constant=_reject_float,
        )
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ProducerReject("STRICT_JSON_DECODE") from error
    _require(type(value) is dict, "JSON_ROOT_NOT_OBJECT")
    _validate_json_domain(
        value,
        node_limit=node_limit,
        array_limit=array_limit,
        member_limit=member_limit,
        depth_limit=depth_limit,
    )
    if require_pretty:
        _require(_pretty_bytes(value) == raw, "NONCANONICAL_JSON_BYTES")
    return value


def _snapshot_tuple(metadata: os.stat_result, raw: bytes) -> tuple[Any, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
        _sha256(raw),
    )


def _open_absolute_directory(path_text: str) -> int:
    _require(os.path.isabs(path_text), "DIRECTORY_NOT_ABSOLUTE")
    _require(os.path.normpath(path_text) == path_text, "DIRECTORY_NOT_CANONICAL")
    parts = Path(path_text).parts
    _require(parts and parts[0] == os.path.sep, "DIRECTORY_ROOT_INVALID")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(os.path.sep, flags)
    try:
        for part in parts[1:]:
            _require(part not in ("", ".", ".."), "DIRECTORY_COMPONENT_INVALID")
            child = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        metadata = os.fstat(descriptor)
        _require(stat.S_ISDIR(metadata.st_mode), "DIRECTORY_TYPE_INVALID")
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _relative_parts(relative_path: str) -> tuple[str, ...]:
    _require(type(relative_path) is str, "RELATIVE_PATH_NOT_TEXT")
    _require(relative_path != "", "RELATIVE_PATH_EMPTY")
    _require(not relative_path.startswith("/"), "RELATIVE_PATH_ABSOLUTE")
    _require("\\" not in relative_path, "RELATIVE_PATH_SEPARATOR")
    parts = tuple(relative_path.split("/"))
    _require(all(part not in ("", ".", "..") for part in parts), "PATH_COMPONENT")
    _require("/".join(parts) == relative_path, "RELATIVE_PATH_NONCANONICAL")
    return parts


def _read_beneath(
    root_descriptor: int,
    relative_path: str,
    *,
    octet_limit: int,
) -> tuple[bytes, tuple[Any, ...]]:
    parts = _relative_parts(relative_path)
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC
    file_flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        directory_flags |= os.O_NOFOLLOW
        file_flags |= os.O_NOFOLLOW
    if hasattr(os, "O_NONBLOCK"):
        file_flags |= os.O_NONBLOCK

    directory = os.dup(root_descriptor)
    file_descriptor: int | None = None
    try:
        for part in parts[:-1]:
            child = os.open(part, directory_flags, dir_fd=directory)
            os.close(directory)
            directory = child
        file_descriptor = os.open(parts[-1], file_flags, dir_fd=directory)
        before = os.fstat(file_descriptor)
        _require(stat.S_ISREG(before.st_mode), "INPUT_NOT_REGULAR")
        _require(before.st_nlink == 1, "INPUT_LINK_COUNT")
        _require(0 <= before.st_size <= octet_limit, "INPUT_FILE_LIMIT")
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(file_descriptor, min(remaining, 64 * 1024))
            _require(chunk != b"", "INPUT_EARLY_EOF")
            chunks.append(chunk)
            remaining -= len(chunk)
        _require(os.read(file_descriptor, 1) == b"", "INPUT_TRAILING_BYTES")
        raw = b"".join(chunks)
        after = os.fstat(file_descriptor)
        _require(
            (
                before.st_dev,
                before.st_ino,
                before.st_mode,
                before.st_nlink,
                before.st_size,
                before.st_mtime_ns,
                before.st_ctime_ns,
            )
            == (
                after.st_dev,
                after.st_ino,
                after.st_mode,
                after.st_nlink,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            ),
            "INPUT_CHANGED_DURING_READ",
        )
        return raw, _snapshot_tuple(after, raw)
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)
        os.close(directory)


def _closed(value: Any, names: list[str], code: str) -> dict[str, Any]:
    _require(type(value) is dict, code)
    _require(set(value) == set(names), code)
    return value


def _hex_digest(value: Any, code: str) -> str:
    _require(
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value),
        code,
    )
    return value


def _platform_limits(seed: dict[str, Any]) -> dict[str, int]:
    catalog = seed.get("f0_seed_ceiling_catalog")
    _require(type(catalog) is dict, "F0_CATALOG")
    records = catalog.get("ordered_platform_ceiling_records")
    _require(type(records) is list, "F0_PLATFORM_RECORDS")
    result: dict[str, int] = {}
    for expected_position, record in enumerate(records, 1):
        _closed(
            record,
            ["ceiling_position", "ceiling_value", "resource_name"],
            "F0_PLATFORM_RECORD",
        )
        _require(record["ceiling_position"] == expected_position, "F0_POSITION")
        name = record["resource_name"]
        value = record["ceiling_value"]
        _require(type(name) is str and name not in result, "F0_NAME")
        _require(type(value) is int and value >= 0, "F0_VALUE")
        result[name] = value
    required = {
        "INDIVIDUAL_FILE_STRICT_UPPER_OCTETS",
        "TOTAL_PINNED_INPUT_OCTETS",
        "INPUT_FILE_COUNT",
        "JSON_NESTING_DEPTH",
        "DECODED_JSON_NODE_COUNT",
        "DECODED_JSON_ARRAY_ENTRY_COUNT",
        "DECODED_JSON_OBJECT_MEMBER_COUNT",
    }
    _require(required <= set(result), "F0_REQUIRED_LIMIT")
    return result


def _validate_boundary(boundary: dict[str, Any]) -> None:
    _require(boundary.get("constructive_boundary_id") == BOUNDARY_ID, "BOUNDARY_ID")
    payload = {
        name: value
        for name, value in boundary.items()
        if name != "constructive_boundary_id"
    }
    _require(
        _semantic_id(BOUNDARY_IDENTITY_DOMAIN, payload) == BOUNDARY_ID,
        "BOUNDARY_SEMANTIC_ID",
    )
    roles = boundary.get("implementation_role_contract", {}).get("ordered_role_records")
    _require(type(roles) is list and len(roles) == 3, "ROLE_CATALOG")
    producer_rows = [
        row for row in roles if row.get("role_name") == "SEPARATE_PRODUCER"
    ]
    _require(len(producer_rows) == 1, "PRODUCER_ROLE")
    role = producer_rows[0]
    _require(role.get("role_position") == 2, "PRODUCER_ROLE_POSITION")
    _require(
        role.get("repository_relative_path") == PRODUCER_RELATIVE_PATH,
        "PRODUCER_ROLE_PATH",
    )
    _require(role.get("source_marker") == SOURCE_MARKER, "PRODUCER_ROLE_MARKER")
    _require(role.get("semantic_authority") is False, "PRODUCER_ROLE_AUTHORITY")
    _require(role.get("may_execute_other_role") is False, "PRODUCER_ROLE_EXECUTION")


def _validate_seed_and_manifest(
    boundary: dict[str, Any],
    seed: dict[str, Any],
    manifest: dict[str, Any],
    seed_raw: bytes,
    manifest_raw: bytes,
) -> None:
    authority = boundary.get("authority_contract")
    _require(type(authority) is dict, "AUTHORITY_CONTRACT")
    seed_authority = authority.get("seed_authority")
    manifest_authority = authority.get("finalization_manifest_authority")
    _require(type(seed_authority) is dict, "SEED_AUTHORITY")
    _require(type(manifest_authority) is dict, "MANIFEST_AUTHORITY")
    _require(len(seed_raw) == seed_authority.get("raw_octets"), "SEED_SIZE")
    _require(_sha256(seed_raw) == seed_authority.get("raw_sha256"), "SEED_HASH")
    _require(
        seed.get("seed_catalog_id") == seed_authority.get("seed_catalog_id"),
        "SEED_ID",
    )
    _require(
        seed.get("protocol_counting_semantics_id")
        == seed_authority.get("protocol_counting_semantics_id"),
        "COUNTING_ID",
    )
    _require(
        len(seed.get("ordered_authority_binding_records", []))
        == seed_authority.get("ordered_authority_binding_record_count"),
        "SEED_AUTHORITY_COUNT",
    )
    _require(
        len(manifest_raw) == manifest_authority.get("raw_octets"),
        "MANIFEST_SIZE",
    )
    _require(
        _sha256(manifest_raw) == manifest_authority.get("raw_sha256"),
        "MANIFEST_HASH",
    )
    _require(
        manifest.get("finalization_manifest_id")
        == manifest_authority.get("finalization_manifest_id"),
        "MANIFEST_ID",
    )
    _require(
        manifest.get("finalization_status")
        == manifest_authority.get("finalization_status"),
        "MANIFEST_STATUS",
    )
    manifest_seed = manifest.get("seed_authority")
    _require(type(manifest_seed) is dict, "MANIFEST_SEED")
    _require(
        manifest_seed.get("seed_catalog_id") == seed.get("seed_catalog_id"),
        "MANIFEST_SEED_ID",
    )
    _require(manifest_seed.get("raw_sha256") == _sha256(seed_raw), "MANIFEST_SEED_HASH")
    _require(
        boundary.get("protocol_version")
        == seed.get("protocol_version")
        == manifest.get("protocol_version"),
        "PROTOCOL_VERSION",
    )
    _require(
        boundary.get("canonicalization_version")
        == seed.get("canonicalization_version")
        == manifest.get("canonicalization_version"),
        "CANONICALIZATION_VERSION",
    )


def _load_frozen_inputs(
    repository_descriptor: int,
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    list[tuple[str, tuple[Any, ...], int]],
    dict[str, int],
]:
    snapshots: list[tuple[str, tuple[Any, ...], int]] = []
    boundary_raw, boundary_snapshot = _read_beneath(
        repository_descriptor,
        BOUNDARY_RELATIVE_PATH,
        octet_limit=INITIAL_FILE_LIMIT,
    )
    _require(len(boundary_raw) == BOUNDARY_RAW_OCTETS, "BOUNDARY_RAW_SIZE")
    _require(_sha256(boundary_raw) == BOUNDARY_RAW_SHA256, "BOUNDARY_RAW_HASH")
    snapshots.append((BOUNDARY_RELATIVE_PATH, boundary_snapshot, INITIAL_FILE_LIMIT))
    boundary = _strict_json(boundary_raw)
    _validate_boundary(boundary)

    authority = boundary["authority_contract"]
    seed_authority = authority["seed_authority"]
    seed_path = seed_authority.get("repository_relative_path")
    _require(type(seed_path) is str, "SEED_PATH")
    seed_raw, seed_snapshot = _read_beneath(
        repository_descriptor,
        seed_path,
        octet_limit=INITIAL_FILE_LIMIT,
    )
    snapshots.append((seed_path, seed_snapshot, INITIAL_FILE_LIMIT))
    seed = _strict_json(seed_raw, require_pretty=True)
    limits = _platform_limits(seed)
    file_limit = limits["INDIVIDUAL_FILE_STRICT_UPPER_OCTETS"]
    _require(file_limit <= INITIAL_FILE_LIMIT, "FILE_LIMIT_EXPANSION")

    manifest_authority = authority["finalization_manifest_authority"]
    manifest_path = manifest_authority.get("repository_relative_path")
    _require(type(manifest_path) is str, "MANIFEST_PATH")
    manifest_raw, manifest_snapshot = _read_beneath(
        repository_descriptor,
        manifest_path,
        octet_limit=file_limit,
    )
    snapshots.append((manifest_path, manifest_snapshot, file_limit))
    manifest = _strict_json(
        manifest_raw,
        require_pretty=True,
        node_limit=limits["DECODED_JSON_NODE_COUNT"],
        array_limit=limits["DECODED_JSON_ARRAY_ENTRY_COUNT"],
        member_limit=limits["DECODED_JSON_OBJECT_MEMBER_COUNT"],
        depth_limit=limits["JSON_NESTING_DEPTH"],
    )
    _validate_seed_and_manifest(boundary, seed, manifest, seed_raw, manifest_raw)

    records = seed["ordered_authority_binding_records"]
    _require(type(records) is list, "AUTHORITY_RECORDS")
    raw_by_role: dict[str, bytes] = {}
    seen_paths: set[str] = {BOUNDARY_RELATIVE_PATH, seed_path, manifest_path}
    seen_files: set[tuple[int, int]] = {
        (snapshot[0], snapshot[1]) for _path, snapshot, _limit in snapshots
    }
    total_octets = sum(snapshot[4] for _path, snapshot, _limit in snapshots)
    for expected_position, record in enumerate(records, 1):
        _closed(
            record,
            [
                "authority_position",
                "authority_role",
                "raw_octet_count",
                "raw_sha256",
                "repository_relative_path",
                "semantic_id",
            ],
            "AUTHORITY_RECORD",
        )
        _require(
            record["authority_position"] == expected_position, "AUTHORITY_POSITION"
        )
        role = record["authority_role"]
        relative_path = record["repository_relative_path"]
        _require(type(role) is str and role not in raw_by_role, "AUTHORITY_ROLE")
        _require(
            type(relative_path) is str and relative_path not in seen_paths,
            "AUTHORITY_PATH",
        )
        expected_octets = record["raw_octet_count"]
        _require(
            type(expected_octets) is int and expected_octets <= file_limit,
            "AUTHORITY_SIZE",
        )
        expected_hash = _hex_digest(record["raw_sha256"], "AUTHORITY_HASH")
        raw, snapshot = _read_beneath(
            repository_descriptor,
            relative_path,
            octet_limit=file_limit,
        )
        _require(len(raw) == expected_octets, "AUTHORITY_SIZE")
        _require(_sha256(raw) == expected_hash, "AUTHORITY_HASH")
        device_inode = (snapshot[0], snapshot[1])
        _require(device_inode not in seen_files, "AUTHORITY_FILE_ALIAS")
        seen_files.add(device_inode)
        seen_paths.add(relative_path)
        raw_by_role[role] = raw
        snapshots.append((relative_path, snapshot, file_limit))
        total_octets += len(raw)

    _require(len(snapshots) <= limits["INPUT_FILE_COUNT"], "INPUT_FILE_COUNT")
    _require(total_octets <= limits["TOTAL_PINNED_INPUT_OCTETS"], "TOTAL_INPUT_OCTETS")
    registry_raw = raw_by_role.get("STRUCTURAL_REGISTRY")
    _require(type(registry_raw) is bytes, "STRUCTURAL_REGISTRY")
    registry = _strict_json(
        registry_raw,
        require_pretty=True,
        node_limit=limits["DECODED_JSON_NODE_COUNT"],
        array_limit=limits["DECODED_JSON_ARRAY_ENTRY_COUNT"],
        member_limit=limits["DECODED_JSON_OBJECT_MEMBER_COUNT"],
        depth_limit=limits["JSON_NESTING_DEPTH"],
    )
    return boundary, seed, manifest, registry, snapshots, limits


def _case_and_plan(seed: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    cases = seed.get("case_universe_catalog", {}).get("ordered_case_bindings")
    plans = seed.get("logical_plan_recipe_catalog", {}).get(
        "ordered_logical_count_plan_records"
    )
    _require(type(cases) is list and type(plans) is list, "CASE_PLAN_CATALOG")
    matching_cases = [row for row in cases if row.get("case_position") == CASE_POSITION]
    matching_plans = [row for row in plans if row.get("case_position") == CASE_POSITION]
    _require(len(matching_cases) == 1 and len(matching_plans) == 1, "CASE_PLAN_UNIQUE")
    case = matching_cases[0]
    plan = matching_plans[0]
    _require(case.get("case_kind") == CASE_KIND, "CASE_KIND")
    binding = case.get("case_binding")
    _require(type(binding) is dict, "CASE_BINDING")
    _require(binding.get("type_name") == CASE_TYPE_NAME, "CASE_TYPE")
    _require(binding.get("row_position") == CASE_POSITION, "CASE_ROW_POSITION")
    _require(plan.get("case_kind") == CASE_KIND, "PLAN_CASE_KIND")
    _require(plan.get("case_binding") == binding, "PLAN_CASE_BINDING")
    _hex_digest(plan.get("logical_count_plan_id"), "LOGICAL_PLAN_ID")
    return case, plan


def _derive_witness(case: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    descriptors = registry.get("ordered_external_type_descriptors")
    schemas = registry.get("value_schema_catalog")
    languages = registry.get("text_language_catalog")
    _require(
        type(descriptors) is list and type(schemas) is list and type(languages) is list,
        "REGISTRY_CATALOG",
    )
    type_name = case["case_binding"]["type_name"]
    matches = [row for row in descriptors if row.get("type_name") == type_name]
    _require(len(matches) == 1, "TYPE_DESCRIPTOR_UNIQUE")
    descriptor = matches[0]
    _require(descriptor.get("type_form") == "RECORD", "TYPE_FORM")
    members = descriptor.get("record_member_descriptors")
    _require(type(members) is list and len(members) == 2, "TYPE_MEMBERS")
    _require(
        [(row.get("member_position"), row.get("member_name")) for row in members]
        == [(1, "kind"), (2, "value")],
        "TYPE_MEMBER_ORDER",
    )
    schemas_by_id = {
        row.get("value_schema_id"): row
        for row in schemas
        if type(row) is dict and type(row.get("value_schema_id")) is str
    }
    kind_schema = schemas_by_id.get(members[0].get("value_schema_id"))
    value_schema = schemas_by_id.get(members[1].get("value_schema_id"))
    _require(type(kind_schema) is dict and type(value_schema) is dict, "VALUE_SCHEMA")
    _require(kind_schema.get("schema_kind") == "TEXT", "KIND_SCHEMA")
    _require(value_schema.get("schema_kind") == "EXACT_BOOLEAN", "VALUE_SCHEMA_KIND")
    language_id = kind_schema.get("text_language_id")
    language_matches = [
        row for row in languages if row.get("text_language_id") == language_id
    ]
    _require(len(language_matches) == 1, "KIND_LANGUAGE_UNIQUE")
    language = language_matches[0]
    _require(language.get("language_kind") == "LITERAL", "KIND_LANGUAGE")
    literals = language.get("ordered_literals")
    _require(type(literals) is list and len(literals) == 1, "KIND_LITERAL")
    tag = literals[0]
    _require(type(tag) is str, "KIND_LITERAL_TYPE")

    alternatives = [{"kind": tag, "value": value} for value in (False, True)]
    alternatives.sort(key=lambda row: (_canonical_bytes(row),), reverse=True)
    alternatives.sort(key=lambda row: len(_canonical_bytes(row)), reverse=True)
    witness = alternatives[0]
    codec_limit = descriptor.get("codec_octet_limit")
    _require(type(codec_limit) is int and codec_limit >= 0, "CODEC_LIMIT")
    _require(len(_canonical_bytes(witness)) <= codec_limit, "CODEC_LIMIT_EXCEEDED")
    return witness


def _build_candidate(
    boundary: dict[str, Any],
    seed: dict[str, Any],
    manifest: dict[str, Any],
    registry: dict[str, Any],
) -> dict[str, Any]:
    case, plan = _case_and_plan(seed)
    witness = _derive_witness(case, registry)
    bundle = boundary.get("candidate_bundle_contract")
    _require(type(bundle) is dict, "CANDIDATE_CONTRACT")
    schema = bundle.get("candidate_envelope_schema")
    tagged_union = bundle.get("candidate_payload_tagged_union")
    _require(type(schema) is dict and type(tagged_union) is dict, "CANDIDATE_SCHEMA")
    member_names = schema.get("ordered_member_names")
    _require(
        member_names
        == [
            "candidate_version",
            "canonicalization_version",
            "measurement_schema_version",
            "protocol_version",
            "seed_catalog_id",
            "finalization_manifest_id",
            "case_position",
            "case_kind",
            "case_binding",
            "logical_count_plan_id",
            "candidate_payload",
            "constructive_candidate_id",
        ],
        "CANDIDATE_MEMBER_SCHEMA",
    )
    alternatives = tagged_union.get("ordered_alternative_records")
    _require(type(alternatives) is list, "CANDIDATE_ALTERNATIVES")
    maximum_rows = [
        row
        for row in alternatives
        if row.get("candidate_kind") == "MAXIMUM_WITNESS_CONTEXT"
    ]
    _require(len(maximum_rows) == 1, "MAXIMUM_CANDIDATE_ALTERNATIVE")
    _require(
        maximum_rows[0].get("required_case_kind") == CASE_KIND, "CANDIDATE_CASE_KIND"
    )
    _require(
        maximum_rows[0].get("ordered_member_names")
        == [
            "candidate_kind",
            "witness_record",
            "scope_witness_context",
            "ordered_context_object_entries",
        ],
        "CANDIDATE_PAYLOAD_SCHEMA",
    )
    candidate: dict[str, Any] = {
        "candidate_version": schema.get("version_literal"),
        "canonicalization_version": boundary.get("canonicalization_version"),
        "measurement_schema_version": boundary.get("measurement_schema_version"),
        "protocol_version": boundary.get("protocol_version"),
        "seed_catalog_id": seed.get("seed_catalog_id"),
        "finalization_manifest_id": manifest.get("finalization_manifest_id"),
        "case_position": CASE_POSITION,
        "case_kind": CASE_KIND,
        "case_binding": json.loads(_canonical_bytes(case["case_binding"])),
        "logical_count_plan_id": plan["logical_count_plan_id"],
        "candidate_payload": {
            "candidate_kind": "MAXIMUM_WITNESS_CONTEXT",
            "witness_record": witness,
            "scope_witness_context": None,
            "ordered_context_object_entries": [],
        },
    }
    identity_domain = schema.get("identity_domain")
    _require(type(identity_domain) is str, "CANDIDATE_IDENTITY_DOMAIN")
    identity_payload = {name: candidate[name] for name in member_names[:-1]}
    candidate["constructive_candidate_id"] = _semantic_id(
        identity_domain, identity_payload
    )
    _closed(candidate, member_names, "CANDIDATE_CLOSED")
    forbidden = set(bundle.get("forbidden_producer_claim_member_names", []))
    stack: list[Any] = [candidate]
    while stack:
        current = stack.pop()
        if type(current) is dict:
            _require(forbidden.isdisjoint(current), "CANDIDATE_CONTAINS_PROOF_FIELD")
            stack.extend(current.values())
        elif type(current) is list:
            stack.extend(current)
    return candidate


def _write_all(descriptor: int, raw: bytes) -> None:
    offset = 0
    while offset < len(raw):
        written = os.write(descriptor, raw[offset:])
        _require(written > 0, "OUTPUT_WRITE_FAILED")
        offset += written


def _safe_unlink(name: str, directory: int) -> None:
    try:
        os.unlink(name, dir_fd=directory)
    except FileNotFoundError:
        pass


def _cleanup_bundle(parent: int, name: str, expected: tuple[int, int] | None) -> None:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        bundle = os.open(name, flags, dir_fd=parent)
    except (FileNotFoundError, NotADirectoryError, OSError):
        return
    try:
        metadata = os.fstat(bundle)
        if expected is not None and (metadata.st_dev, metadata.st_ino) != expected:
            return
        for entry in os.listdir(bundle):
            if entry == "context_objects":
                try:
                    os.rmdir(entry, dir_fd=bundle)
                except OSError:
                    return
            elif entry == "candidate.json" or entry.startswith(".candidate-"):
                _safe_unlink(entry, bundle)
            else:
                return
    finally:
        os.close(bundle)
    try:
        os.rmdir(name, dir_fd=parent)
    except OSError:
        pass


def _recheck_inputs(
    repository_descriptor: int,
    snapshots: list[tuple[str, tuple[Any, ...], int]],
) -> None:
    for relative_path, expected, limit in snapshots:
        _raw, observed = _read_beneath(
            repository_descriptor,
            relative_path,
            octet_limit=limit,
        )
        _require(observed == expected, "PINNED_INPUT_DRIFT")


def _publish_candidate(
    output_path: str,
    candidate: dict[str, Any],
    *,
    file_limit: int,
    before_publish: Any,
) -> None:
    _require(os.path.isabs(output_path), "OUTPUT_NOT_ABSOLUTE")
    _require(os.path.normpath(output_path) == output_path, "OUTPUT_NOT_CANONICAL")
    parent_path, output_name = os.path.split(output_path)
    _require(output_name not in ("", ".", ".."), "OUTPUT_NAME")
    parent = _open_absolute_directory(parent_path)
    staging_name: str | None = None
    staging_identity: tuple[int, int] | None = None
    published = False
    try:
        try:
            os.stat(output_name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            _reject("OUTPUT_ALREADY_EXISTS")

        token = os.urandom(16).hex()
        staging_name = f".raw-v8-v2-producer-{os.getpid()}-{token}"
        os.mkdir(staging_name, mode=0o700, dir_fd=parent)
        directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            directory_flags |= os.O_NOFOLLOW
        staging = os.open(staging_name, directory_flags, dir_fd=parent)
        try:
            os.fchmod(staging, 0o700)
            staging_metadata = os.fstat(staging)
            staging_identity = (staging_metadata.st_dev, staging_metadata.st_ino)
            os.mkdir("context_objects", mode=0o700, dir_fd=staging)
            context = os.open("context_objects", directory_flags, dir_fd=staging)
            try:
                os.fchmod(context, 0o700)
                os.fsync(context)
            finally:
                os.close(context)

            raw = _pretty_bytes(candidate)
            _require(len(raw) <= file_limit, "OUTPUT_FILE_LIMIT")
            temporary_name = f".candidate-{os.urandom(16).hex()}.tmp"
            file_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
            if hasattr(os, "O_NOFOLLOW"):
                file_flags |= os.O_NOFOLLOW
            file_descriptor = os.open(
                temporary_name,
                file_flags,
                0o600,
                dir_fd=staging,
            )
            try:
                os.fchmod(file_descriptor, 0o600)
                _write_all(file_descriptor, raw)
                os.fsync(file_descriptor)
            finally:
                os.close(file_descriptor)
            os.link(
                temporary_name,
                "candidate.json",
                src_dir_fd=staging,
                dst_dir_fd=staging,
                follow_symlinks=False,
            )
            os.unlink(temporary_name, dir_fd=staging)
            candidate_descriptor = os.open(
                "candidate.json",
                os.O_RDONLY | os.O_CLOEXEC,
                dir_fd=staging,
            )
            try:
                metadata = os.fstat(candidate_descriptor)
                _require(stat.S_ISREG(metadata.st_mode), "OUTPUT_FILE_TYPE")
                _require(metadata.st_nlink == 1, "OUTPUT_FILE_LINK_COUNT")
                _require(stat.S_IMODE(metadata.st_mode) == 0o600, "OUTPUT_FILE_MODE")
                observed = b""
                while len(observed) < len(raw):
                    chunk = os.read(candidate_descriptor, len(raw) - len(observed))
                    _require(chunk != b"", "OUTPUT_FILE_EARLY_EOF")
                    observed += chunk
                _require(
                    os.read(candidate_descriptor, 1) == b"", "OUTPUT_FILE_TRAILING"
                )
                _require(observed == raw, "OUTPUT_FILE_MISMATCH")
            finally:
                os.close(candidate_descriptor)
            os.fsync(staging)
        finally:
            os.close(staging)

        before_publish()
        try:
            os.stat(output_name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            _reject("OUTPUT_RACE")
        os.rename(staging_name, output_name, src_dir_fd=parent, dst_dir_fd=parent)
        published = True
        staging_name = None
        output = os.open(output_name, directory_flags, dir_fd=parent)
        try:
            metadata = os.fstat(output)
            _require(
                staging_identity == (metadata.st_dev, metadata.st_ino),
                "OUTPUT_ROOT_IDENTITY",
            )
            _require(stat.S_IMODE(metadata.st_mode) == 0o700, "OUTPUT_ROOT_MODE")
            _require(
                set(os.listdir(output)) == {"candidate.json", "context_objects"},
                "OUTPUT_ROOT_ENTRIES",
            )
        finally:
            os.close(output)
        os.fsync(parent)
    except Exception:
        if staging_name is not None:
            _cleanup_bundle(parent, staging_name, staging_identity)
        elif published:
            _cleanup_bundle(parent, output_name, staging_identity)
        raise
    finally:
        os.close(parent)


def _parse_arguments(arguments: list[str]) -> tuple[str, str, int, str]:
    expected_flags = [
        "--repository-root",
        "--boundary",
        "--case-position",
        "--output-root",
    ]
    if len(arguments) != len(expected_flags) * 2:
        raise InvocationReject("EXPECTED_FOUR_OPTION_VALUE_PAIRS")
    for offset, flag in enumerate(expected_flags):
        if arguments[offset * 2] != flag:
            raise InvocationReject("FIXED_ARGUMENT_ORDER_REQUIRED")
        if arguments[offset * 2 + 1] == "":
            raise InvocationReject("EMPTY_ARGUMENT_VALUE")
    repository_root = arguments[1]
    boundary_path = arguments[3]
    case_text = arguments[5]
    output_root = arguments[7]
    if case_text != str(CASE_POSITION):
        raise InvocationReject("ONLY_CANONICAL_CASE_5_IS_SUPPORTED")
    if (
        not os.path.isabs(repository_root)
        or os.path.normpath(repository_root) != repository_root
    ):
        raise InvocationReject("REPOSITORY_ROOT_MUST_BE_CANONICAL_ABSOLUTE")
    expected_boundary = os.path.join(repository_root, BOUNDARY_RELATIVE_PATH)
    if boundary_path != expected_boundary:
        raise InvocationReject("BOUNDARY_PATH_MISMATCH")
    if not os.path.isabs(output_root) or os.path.normpath(output_root) != output_root:
        raise InvocationReject("OUTPUT_ROOT_MUST_BE_CANONICAL_ABSOLUTE")
    return repository_root, boundary_path, CASE_POSITION, output_root


def _produce(
    repository_root: str, boundary_path: str, case_position: int, output_root: str
) -> None:
    _require(case_position == CASE_POSITION, "UNSUPPORTED_CASE")
    _require(
        boundary_path == os.path.join(repository_root, BOUNDARY_RELATIVE_PATH),
        "BOUNDARY_PATH",
    )
    repository = _open_absolute_directory(repository_root)
    try:
        source_raw, source_snapshot = _read_beneath(
            repository,
            PRODUCER_RELATIVE_PATH,
            octet_limit=INITIAL_FILE_LIMIT,
        )
        _require(SOURCE_MARKER.encode("utf-8") in source_raw, "SOURCE_MARKER")
        executed_path = os.path.abspath(__file__)
        expected_source = os.path.join(repository_root, PRODUCER_RELATIVE_PATH)
        _require(executed_path == expected_source, "EXECUTED_SOURCE_PATH")
        boundary, seed, manifest, registry, snapshots, limits = _load_frozen_inputs(
            repository
        )
        snapshots.append((PRODUCER_RELATIVE_PATH, source_snapshot, INITIAL_FILE_LIMIT))
        _require(
            len(snapshots) <= limits["INPUT_FILE_COUNT"],
            "INPUT_FILE_COUNT_WITH_SOURCE",
        )
        total_octets = sum(snapshot[4] for _path, snapshot, _limit in snapshots)
        _require(
            total_octets <= limits["TOTAL_PINNED_INPUT_OCTETS"],
            "TOTAL_INPUT_OCTETS_WITH_SOURCE",
        )
        candidate = _build_candidate(boundary, seed, manifest, registry)
        _publish_candidate(
            output_root,
            candidate,
            file_limit=limits["INDIVIDUAL_FILE_STRICT_UPPER_OCTETS"],
            before_publish=lambda: _recheck_inputs(repository, snapshots),
        )
    finally:
        os.close(repository)


def main(arguments: list[str] | None = None) -> int:
    if arguments is None:
        arguments = sys.argv[1:]
    try:
        repository_root, boundary_path, case_position, output_root = _parse_arguments(
            arguments
        )
    except InvocationReject as error:
        sys.stderr.write(INVOCATION_PREFIX + str(error) + "\n")
        return 2
    try:
        _produce(repository_root, boundary_path, case_position, output_root)
    except ProducerReject as error:
        sys.stderr.write(REJECTION_PREFIX + str(error) + "\n")
        return 1
    except (OSError, ValueError, TypeError, MemoryError):
        sys.stderr.write(REJECTION_PREFIX + "FAIL_CLOSED\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

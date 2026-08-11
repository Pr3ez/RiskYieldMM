#!/usr/bin/env python3
"""Produce one bounded Raw V8 Step-2 V2 constructive candidate bundle."""

import hashlib
import json
import os
import stat
import sys
from itertools import product
from pathlib import Path
from typing import Any

SOURCE_MARKER = "SEPARATE_V2_CONSTRUCTIVE_PRODUCER_V1"

BOUNDARY_RELATIVE_PATH = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_constructive_boundary_v49f.json"
)
SUCCESSOR_BOUNDARY_RELATIVE_PATH = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_boundary_delta_v49f.json"
)
SUCCESSOR_SEED_DELTA_RELATIVE_PATH = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_seed_delta_v49f.json"
)
SUCCESSOR_MANIFEST_DELTA_RELATIVE_PATH = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_case435_manifest_delta_v49f.json"
)
PACKED_BOUNDARY_RELATIVE_PATH = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "case435_context_pack_boundary_delta_v49f.json"
)
PRODUCER_RELATIVE_PATH = (
    "scripts/tests/produce_raw_v8_step2_maximum_protocol_v2_candidate_v49f.py"
)
BOUNDARY_ID = "bdc7363ae28dfe9a1c1dc132808cb1bd4a06c409201cd49b31e394893142a7ed"
BOUNDARY_RAW_OCTETS = 27334
BOUNDARY_RAW_SHA256 = "05468ec3411869fc5b4b5c60d2820e58f8ebf0af96dea978f06d92705fe3bb2b"
BOUNDARY_IDENTITY_DOMAIN = "RiskYieldMMStep2ConstructiveExecutionBoundaryV1V4_9F_RawV8"
SUCCESSOR_BOUNDARY_RAW_OCTETS = 4_806
SUCCESSOR_BOUNDARY_RAW_SHA256 = (
    "208d0cd50eb0bbfe206148dbf58df862f8adc857e382623e91e4e10d942c936c"
)
SUCCESSOR_BOUNDARY_ID = (
    "7d4c06f56cd3cacd97cc4ff655e31f380fe9231c6c7c1374caee499186e1f73d"
)
SUCCESSOR_BOUNDARY_IDENTITY_DOMAIN = (
    "RiskYieldMMStep2Case435ExactBoundaryDeltaV1V4_9F_RawV8"
)
SUCCESSOR_SEED_DELTA_RAW_OCTETS = 22_976
SUCCESSOR_SEED_DELTA_RAW_SHA256 = (
    "5ce6b2156389ff0aecad7272a564308662a6ec3a77c4b94bfcae7ce32739c3da"
)
SUCCESSOR_SEED_ID = "7fad47e881624d0f39809e72ce2d3d3fd81fb8c85f854fe8332faf543cd1120b"
SUCCESSOR_SEED_IDENTITY_DOMAIN = "RiskYieldMMStep2Case435ExactSeedDeltaV1V4_9F_RawV8"
SUCCESSOR_MANIFEST_DELTA_RAW_OCTETS = 2_192
SUCCESSOR_MANIFEST_DELTA_RAW_SHA256 = (
    "daa55d18aa8adfcef9b8a6ea2c6fa734f7922888a902eb863c6307c0fc13bacf"
)
SUCCESSOR_MANIFEST_ID = (
    "6aed1139c158f8685bcb226697a2efe57af3c42f57831173bd7b3ea169025d9c"
)
SUCCESSOR_MANIFEST_IDENTITY_DOMAIN = (
    "RiskYieldMMStep2Case435ExactManifestDeltaV1V4_9F_RawV8"
)
SUCCESSOR_F2_ID = "5b2171f64c082ddaa5ecbeb19e2e2f5b952c07336a097364f23fd1658c3d944f"
SUCCESSOR_CASE435_PLAN_ID = (
    "343259e38b6050fac5905fdc7ed6dca6d345d32c07b8370085bdf865793e7ad8"
)
SUCCESSOR_CASE435_PROGRAM_ID = (
    "160486e8c6023b4cfb7ac430065a1dd8c8c422342535fbd5b9b0bceb2ca2e820"
)
PACKED_BOUNDARY_RAW_OCTETS = 6_049
PACKED_BOUNDARY_RAW_SHA256 = (
    "985f0d67a545d036f1777a627f01b609d396a39c690ac81c1bacfc4f7563f56b"
)
PACKED_BOUNDARY_ID = "c8448f57dcdc3e4f1f3239043ed4977013efbd99c750cb2e2e857025f5ac0acd"
PACKED_BOUNDARY_IDENTITY_DOMAIN = (
    "RiskYieldMMStep2Case435ContextPackBoundaryDeltaV1V4_9F_RawV8"
)

PREDECESSOR_MODE = "PREDECESSOR_CONSTRUCTIVE_BOUNDARY_V1"
PACKED_SUCCESSOR_MODE = "SUCCESSOR_CASE435_PACKED_CONTEXT_BOUNDARY_V1"
PILOT_CASE_POSITIONS = (5, 24, 54, 69, 435, 475)
CASE5_POSITION = 5
CASE24_POSITION = 24
CASE54_POSITION = 54
CASE69_POSITION = 69
CASE435_POSITION = 435
CASE475_POSITION = 475
MAXIMUM_CASE_KIND = "MAXIMUM_PUBLICATION_ROW"
LOCAL_CASE_KIND = "LOCAL_SHUTDOWN_UNREPRESENTABLE_MINIMALITY"

CONTEXT_OBJECT_DOMAIN = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumContextObjectV2V4_9F_RawV8"
)
RECORD_REFERENCE_DOMAIN = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumRecordReferenceV2V4_9F_RawV8"
)
CASE435_PACK_DOMAIN = "RiskYieldMMStep2Case435ContextPackV1V4_9F_RawV8"
SOURCE_ERROR_DETAIL_DOMAIN = "RiskYieldMMA2MSourceErrorDetailV4_9F_RawV8"

CASE24_OWNER_TYPE = "CapacityMeasurementOperationResultEvidence"
CASE54_TYPE = "CapacityMeasurementVocabularyDefinitionV1"
CASE69_TYPE = "CapacityMeasurementOperationResultEvidence"
CASE69_SPEC_TYPE = "CapacityMeasurementOperationSpec"
CASE69_PROFILE_ID = "92a80f3b2dc5d4b9a6284adfb6819823de7e2546d4141b2b12c5c7c9afff21f4"
CASE69_APPLICATION_NAME = "APPLY/OPERATION_RESULT_SIGNED_SPEC_V1"
CASE69_SPEC_POINTER = "/fixture_records/operation_specs/LOCAL_SHUTDOWN"

CASE435_PROFILE_POSITION = 369
CASE435_PROFILE_ID = "505dac244288e6fb666919c99567f883c28ed573a898ce2a5dd680744dd57540"
CASE435_PREDECESSOR_PLAN_ID = (
    "9f8cd8303e3a9360986f0294210dda931e827af6eed4ec76b0c084e54f722c4a"
)
CASE435_PREDECESSOR_PROGRAM_ID = (
    "0e4a94fb5b99c464e7db1ef0fc0525b9408683a004a5ea034fcfbf5c427eb4e8"
)
CASE435_MEASURED_SEQUENCE_ORDINAL = 64
CASE435_FIELD_COUNT = 185
CASE435_A1_FIELDS = (
    "a1.waiting_count",
    "a1.waiting_kinds",
    "a1.waiting_sequences",
)
CASE435_PLACEHOLDER_FIELD_REASON = {
    "ARTIFACT_BOUND_EXCEEDED": "CHECKPOINT_PLACEHOLDER_ARTIFACT_BOUND_EXCEEDED",
    "OBSERVER_INTERNAL_ERROR": "CHECKPOINT_PLACEHOLDER_OBSERVER_INTERNAL_ERROR",
    "SOURCE_CLOCK_UNAVAILABLE": "CHECKPOINT_PLACEHOLDER_SOURCE_CLOCK_UNAVAILABLE",
    "TARGET_BOUNDARY_NOT_REACHED": (
        "CHECKPOINT_PLACEHOLDER_TARGET_BOUNDARY_NOT_REACHED"
    ),
}
CASE435_APPLICATION_ORDER = (
    "APPLY/SELECTOR_MARKER_CONTRACT_V1",
    "APPLY/V2_OBSERVATION_AGGREGATE_REGISTRY_V1",
    "APPLY/V2_OBSERVATION_FIELDS_REGISTRY_V1",
    "APPLY/V2_ROOT_OBSERVATION_MEMBERSHIP_V1",
    "APPLY/V2_ROOT_SELECTOR_LIFECYCLE_V1",
)

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


A1_FIELDS = CASE435_A1_FIELDS
PLACEHOLDER_FIELD_REASON = CASE435_PLACEHOLDER_FIELD_REASON
FIELD_COUNT = CASE435_FIELD_COUNT
SOURCE_ERROR_DOMAIN = SOURCE_ERROR_DETAIL_DOMAIN


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


class _CanonicalJsonCopy:
    """Deep-copy the producer's closed JSON domain without another import root."""

    @staticmethod
    def deepcopy(value: Any) -> Any:
        try:
            return json.loads(_canonical_bytes(value))
        except (json.JSONDecodeError, UnicodeError) as error:
            raise ProducerReject("CANONICAL_COPY_FAILED") from error


copy = _CanonicalJsonCopy()


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


def _authority_member(*parts: str) -> str:
    """Name an input-authority member without claiming it in candidate output."""

    return "_".join(parts)


def _seed_semantic_id(seed: dict[str, Any], domain: str, payload: Any) -> str:
    return _sha256(
        _canonical_bytes(
            {
                "canonicalization_version": seed["canonicalization_version"],
                "domain": domain,
                "payload": payload,
                "schema_version": seed["measurement_schema_version"],
            }
        )
    )


def _record_semantic_id(
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
    identity_member = descriptor.get("identity_field")
    member_order = descriptor.get("identity_payload_member_order")
    domain = descriptor.get("described_record_domain")
    _require(
        type(identity_member) is str
        and type(member_order) is list
        and type(domain) is str,
        "RECORD_IDENTITY_CONTRACT",
    )
    payload = {name: record[name] for name in member_order}
    identity = _record_semantic_id(
        canonicalization_version, schema_version, domain, payload
    )
    record[identity_member] = identity
    return identity


def _descriptor_index(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = registry.get("ordered_external_type_descriptors")
    _require(type(rows) is list, "TYPE_DESCRIPTOR_CATALOG")
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        _require(type(row) is dict, "TYPE_DESCRIPTOR")
        type_name = row.get("type_name")
        _require(type(type_name) is str and type_name not in result, "TYPE_DESCRIPTOR")
        result[type_name] = row
    return result


def _reseal_typed_record(
    record: dict[str, Any],
    type_name: str,
    registry: dict[str, Any],
    seed: dict[str, Any],
) -> None:
    descriptor = _descriptor_index(registry).get(type_name)
    _require(type(descriptor) is dict, "RESEAL_TYPE_DESCRIPTOR")
    identity_field = descriptor.get("identity_field")
    member_order = descriptor.get("identity_payload_member_order")
    domain = descriptor.get("described_record_domain")
    _require(
        type(identity_field) is str
        and type(member_order) is list
        and type(domain) is str,
        "RESEAL_IDENTITY_CONTRACT",
    )
    _require(
        all(type(name) is str and name in record for name in member_order),
        "RESEAL_PAYLOAD",
    )
    payload = {name: record[name] for name in member_order}
    record[identity_field] = _seed_semantic_id(seed, domain, payload)


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
    inventory_raw = raw_by_role.get("V4_INVENTORY")
    _require(
        type(registry_raw) is bytes and type(inventory_raw) is bytes,
        "CONSTRUCTION_AUTHORITIES",
    )
    registry = _strict_json(
        registry_raw,
        require_pretty=True,
        node_limit=limits["DECODED_JSON_NODE_COUNT"],
        array_limit=limits["DECODED_JSON_ARRAY_ENTRY_COUNT"],
        member_limit=limits["DECODED_JSON_OBJECT_MEMBER_COUNT"],
        depth_limit=limits["JSON_NESTING_DEPTH"],
    )
    inventory = _strict_json(
        inventory_raw,
        require_pretty=True,
        node_limit=limits["DECODED_JSON_NODE_COUNT"],
        array_limit=limits["DECODED_JSON_ARRAY_ENTRY_COUNT"],
        member_limit=limits["DECODED_JSON_OBJECT_MEMBER_COUNT"],
        depth_limit=limits["JSON_NESTING_DEPTH"],
    )
    _require(
        inventory.get("external_schema_registry_v2") == registry,
        "INVENTORY_REGISTRY_JOIN",
    )
    return boundary, seed, manifest, registry, inventory, snapshots, limits


def _read_additional_json_authority(
    repository_descriptor: int,
    relative_path: str,
    *,
    expected_octets: int,
    expected_sha256: str,
    snapshots: list[tuple[str, tuple[Any, ...], int]],
    limits: dict[str, int],
) -> tuple[bytes, dict[str, Any]]:
    _require(
        relative_path not in {path for path, _snapshot, _limit in snapshots},
        "SUCCESSOR_AUTHORITY_PATH_DUPLICATE",
    )
    file_limit = limits["INDIVIDUAL_FILE_STRICT_UPPER_OCTETS"]
    raw, snapshot = _read_beneath(
        repository_descriptor,
        relative_path,
        octet_limit=file_limit,
    )
    _require(len(raw) == expected_octets, "SUCCESSOR_AUTHORITY_SIZE")
    _require(_sha256(raw) == expected_sha256, "SUCCESSOR_AUTHORITY_HASH")
    inode = (snapshot[0], snapshot[1])
    _require(
        inode not in {(row[0], row[1]) for _path, row, _limit in snapshots},
        "SUCCESSOR_AUTHORITY_FILE_ALIAS",
    )
    value = _strict_json(
        raw,
        require_pretty=True,
        node_limit=limits["DECODED_JSON_NODE_COUNT"],
        array_limit=limits["DECODED_JSON_ARRAY_ENTRY_COUNT"],
        member_limit=limits["DECODED_JSON_OBJECT_MEMBER_COUNT"],
        depth_limit=limits["JSON_NESTING_DEPTH"],
    )
    snapshots.append((relative_path, snapshot, file_limit))
    _require(len(snapshots) <= limits["INPUT_FILE_COUNT"], "INPUT_FILE_COUNT")
    _require(
        sum(row[4] for _path, row, _limit in snapshots)
        <= limits["TOTAL_PINNED_INPUT_OCTETS"],
        "TOTAL_INPUT_OCTETS",
    )
    return raw, value


def _require_payload_identity(
    value: dict[str, Any], identity_member: str, domain: str, expected: str
) -> None:
    _require(value.get(identity_member) == expected, "SUCCESSOR_SEMANTIC_ID")
    payload = {name: child for name, child in value.items() if name != identity_member}
    _require(_semantic_id(domain, payload) == expected, "SUCCESSOR_SEMANTIC_ID")


def _authority_descriptor(
    relative_path: str,
    raw: bytes,
    identity_member: str | None = None,
    identity_value: str | None = None,
) -> dict[str, Any]:
    descriptor: dict[str, Any] = {
        "raw_octets": len(raw),
        "raw_sha256": _sha256(raw),
        "repository_relative_path": relative_path,
    }
    if identity_member is not None:
        _require(type(identity_value) is str, "AUTHORITY_DESCRIPTOR_IDENTITY")
        descriptor[identity_member] = identity_value
    return descriptor


def _load_packed_successor_authorities(
    repository_descriptor: int,
    boundary: dict[str, Any],
    seed: dict[str, Any],
    manifest: dict[str, Any],
    snapshots: list[tuple[str, tuple[Any, ...], int]],
    limits: dict[str, int],
) -> dict[str, Any]:
    seed_raw, seed_delta = _read_additional_json_authority(
        repository_descriptor,
        SUCCESSOR_SEED_DELTA_RELATIVE_PATH,
        expected_octets=SUCCESSOR_SEED_DELTA_RAW_OCTETS,
        expected_sha256=SUCCESSOR_SEED_DELTA_RAW_SHA256,
        snapshots=snapshots,
        limits=limits,
    )
    manifest_raw, manifest_delta = _read_additional_json_authority(
        repository_descriptor,
        SUCCESSOR_MANIFEST_DELTA_RELATIVE_PATH,
        expected_octets=SUCCESSOR_MANIFEST_DELTA_RAW_OCTETS,
        expected_sha256=SUCCESSOR_MANIFEST_DELTA_RAW_SHA256,
        snapshots=snapshots,
        limits=limits,
    )
    successor_raw, successor_boundary = _read_additional_json_authority(
        repository_descriptor,
        SUCCESSOR_BOUNDARY_RELATIVE_PATH,
        expected_octets=SUCCESSOR_BOUNDARY_RAW_OCTETS,
        expected_sha256=SUCCESSOR_BOUNDARY_RAW_SHA256,
        snapshots=snapshots,
        limits=limits,
    )
    packed_raw, packed_boundary = _read_additional_json_authority(
        repository_descriptor,
        PACKED_BOUNDARY_RELATIVE_PATH,
        expected_octets=PACKED_BOUNDARY_RAW_OCTETS,
        expected_sha256=PACKED_BOUNDARY_RAW_SHA256,
        snapshots=snapshots,
        limits=limits,
    )

    _require_payload_identity(
        seed_delta,
        "successor_seed_catalog_id",
        SUCCESSOR_SEED_IDENTITY_DOMAIN,
        SUCCESSOR_SEED_ID,
    )
    _require_payload_identity(
        manifest_delta,
        "successor_manifest_id",
        SUCCESSOR_MANIFEST_IDENTITY_DOMAIN,
        SUCCESSOR_MANIFEST_ID,
    )
    _require_payload_identity(
        successor_boundary,
        "successor_constructive_boundary_id",
        SUCCESSOR_BOUNDARY_IDENTITY_DOMAIN,
        SUCCESSOR_BOUNDARY_ID,
    )
    _require_payload_identity(
        packed_boundary,
        "case435_context_pack_boundary_delta_id",
        PACKED_BOUNDARY_IDENTITY_DOMAIN,
        PACKED_BOUNDARY_ID,
    )

    _require(
        seed_delta.get("predecessor_seed_authority")
        == {
            "raw_octets": boundary["authority_contract"]["seed_authority"][
                "raw_octets"
            ],
            "raw_sha256": boundary["authority_contract"]["seed_authority"][
                "raw_sha256"
            ],
            "repository_relative_path": boundary["authority_contract"][
                "seed_authority"
            ]["repository_relative_path"],
            "seed_catalog_id": seed["seed_catalog_id"],
        },
        "SUCCESSOR_SEED_PREDECESSOR_BINDING",
    )
    _require(
        manifest_delta.get("predecessor_finalization_manifest_authority")
        == {
            "finalization_manifest_id": manifest["finalization_manifest_id"],
            "raw_octets": boundary["authority_contract"][
                "finalization_manifest_authority"
            ]["raw_octets"],
            "raw_sha256": boundary["authority_contract"][
                "finalization_manifest_authority"
            ]["raw_sha256"],
            "repository_relative_path": boundary["authority_contract"][
                "finalization_manifest_authority"
            ]["repository_relative_path"],
        }
        and manifest_delta.get("successor_seed_delta_authority")
        == _authority_descriptor(
            SUCCESSOR_SEED_DELTA_RELATIVE_PATH,
            seed_raw,
            "successor_seed_catalog_id",
            SUCCESSOR_SEED_ID,
        ),
        "SUCCESSOR_MANIFEST_BINDING",
    )
    _require(
        successor_boundary.get("predecessor_constructive_boundary_authority")
        == {
            "constructive_boundary_id": BOUNDARY_ID,
            "raw_octets": BOUNDARY_RAW_OCTETS,
            "raw_sha256": BOUNDARY_RAW_SHA256,
            "repository_relative_path": BOUNDARY_RELATIVE_PATH,
        }
        and successor_boundary.get("successor_seed_delta_authority")
        == _authority_descriptor(
            SUCCESSOR_SEED_DELTA_RELATIVE_PATH,
            seed_raw,
            "successor_seed_catalog_id",
            SUCCESSOR_SEED_ID,
        )
        and successor_boundary.get("successor_manifest_delta_authority")
        == _authority_descriptor(
            SUCCESSOR_MANIFEST_DELTA_RELATIVE_PATH,
            manifest_raw,
            "successor_manifest_id",
            SUCCESSOR_MANIFEST_ID,
        ),
        "SUCCESSOR_BOUNDARY_BINDING",
    )
    _require(
        packed_boundary.get("predecessor_successor_boundary_authority")
        == _authority_descriptor(
            SUCCESSOR_BOUNDARY_RELATIVE_PATH,
            successor_raw,
            "successor_constructive_boundary_id",
            SUCCESSOR_BOUNDARY_ID,
        ),
        "PACKED_BOUNDARY_BINDING",
    )

    resolution = seed_delta.get("resolution_contract")
    plan = seed_delta.get("successor_case435_logical_count_plan")
    program = seed_delta.get("successor_case435_profile_conditioning_program")
    binding = seed_delta.get("successor_case435_case_plan_binding")
    _require(
        type(resolution) is dict
        and resolution.get("ordered_override_case_positions") == [CASE435_POSITION]
        and resolution.get("override_cardinality") == 1
        and resolution.get("base_fallback_case_count") == 474,
        "SUCCESSOR_RESOLUTION",
    )
    _require(
        type(plan) is dict
        and type(program) is dict
        and type(binding) is dict
        and plan.get("logical_count_plan_id") == SUCCESSOR_CASE435_PLAN_ID
        and program.get("profile_conditioning_program_id")
        == SUCCESSOR_CASE435_PROGRAM_ID
        and plan.get("profile_conditioning_program_id") == SUCCESSOR_CASE435_PROGRAM_ID
        and plan.get(_authority_member("upper", "bound", "mode"))
        == "EXACT_LEGAL_DOMAIN"
        and plan.get(_authority_member("ordered", "safe", "relaxation", "rule", "ids"))
        == []
        and binding.get("logical_count_plan_id") == SUCCESSOR_CASE435_PLAN_ID,
        "SUCCESSOR_CASE435_PLAN",
    )
    f2 = successor_boundary.get("successor_f2_resource_limit_catalog")
    _require(
        type(f2) is dict
        and f2.get("f2_resource_limit_catalog_id") == SUCCESSOR_F2_ID
        and f2.get("successor_seed_catalog_id") == SUCCESSOR_SEED_ID
        and f2.get("successor_manifest_id") == SUCCESSOR_MANIFEST_ID,
        "SUCCESSOR_F2_BINDING",
    )
    effective = packed_boundary.get("unchanged_effective_authorities")
    non_drift = packed_boundary.get("scope_and_non_drift_contract")
    _require(
        type(effective) is dict
        and effective.get("successor_seed_catalog_id") == SUCCESSOR_SEED_ID
        and effective.get("successor_manifest_id") == SUCCESSOR_MANIFEST_ID
        and effective.get("maximum_protocol_sha256")
        == SUCCESSOR_MANIFEST_DELTA_RAW_SHA256
        and effective.get("case435_logical_count_plan_id") == SUCCESSOR_CASE435_PLAN_ID
        and effective.get("case435_profile_conditioning_program_id")
        == SUCCESSOR_CASE435_PROGRAM_ID
        and effective.get("f2_resource_limit_catalog_id") == SUCCESSOR_F2_ID
        and type(non_drift) is dict
        and non_drift.get("f0_or_f2_limit_increase_forbidden") is True
        and non_drift.get(
            "seed_manifest_plan_program_exactness_and_f2_values_unchanged"
        )
        is True,
        "PACKED_EFFECTIVE_AUTHORITY",
    )
    return {
        "mode": PACKED_SUCCESSOR_MODE,
        "seed_id": SUCCESSOR_SEED_ID,
        "manifest_id": SUCCESSOR_MANIFEST_ID,
        "protocol_sha256": SUCCESSOR_MANIFEST_DELTA_RAW_SHA256,
        "case435_plan": plan,
        "packed_boundary": packed_boundary,
        "successor_boundary": successor_boundary,
    }


def _case_and_plan(
    seed: dict[str, Any],
    case_position: int,
    effective: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    cases = seed.get("case_universe_catalog", {}).get("ordered_case_bindings")
    plans = seed.get("logical_plan_recipe_catalog", {}).get(
        "ordered_logical_count_plan_records"
    )
    _require(type(cases) is list and type(plans) is list, "CASE_PLAN_CATALOG")
    matching_cases = [row for row in cases if row.get("case_position") == case_position]
    matching_plans = [row for row in plans if row.get("case_position") == case_position]
    _require(len(matching_cases) == 1 and len(matching_plans) == 1, "CASE_PLAN_UNIQUE")
    case = matching_cases[0]
    plan = (
        effective["case435_plan"]
        if case_position == CASE435_POSITION
        and effective["mode"] == PACKED_SUCCESSOR_MODE
        else matching_plans[0]
    )
    expected_kind = (
        LOCAL_CASE_KIND if case_position == CASE475_POSITION else MAXIMUM_CASE_KIND
    )
    _require(case.get("case_kind") == expected_kind, "CASE_KIND")
    binding = case.get("case_binding")
    _require(type(binding) is dict, "CASE_BINDING")
    _require(case.get("case_position") == case_position, "CASE_POSITION")
    if case_position != CASE475_POSITION:
        _require(binding.get("row_position") == case_position, "CASE_ROW_POSITION")
    _require(plan.get("case_kind") == expected_kind, "PLAN_CASE_KIND")
    _require(plan.get("case_binding") == binding, "PLAN_CASE_BINDING")
    _hex_digest(plan.get("logical_count_plan_id"), "LOGICAL_PLAN_ID")
    return case, plan


def _derive_case5_witness(
    case: dict[str, Any], registry: dict[str, Any]
) -> dict[str, Any]:
    descriptors = registry.get("ordered_external_type_descriptors")
    schemas = registry.get("value_schema_catalog")
    languages = registry.get("text_language_catalog")
    _require(
        type(descriptors) is list and type(schemas) is list and type(languages) is list,
        "REGISTRY_CATALOG",
    )
    type_name = case["case_binding"]["type_name"]
    _require(type_name == "CapacityMeasurementBoolValueV1", "CASE5_TYPE")
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


def _codec_boundary(descriptor: dict[str, Any]) -> int:
    limit = descriptor.get("codec_octet_limit")
    relation = descriptor.get("codec_byte_bound_relation")
    _require(type(limit) is int and limit >= 0, "CODEC_LIMIT")
    _require(relation in {"LE", "LT"}, "CODEC_RELATION")
    return limit if relation == "LE" else limit - 1


def _authority_provenance(seed: dict[str, Any]) -> tuple[str, str, str]:
    rows = seed.get("ordered_authority_binding_records")
    _require(type(rows) is list, "AUTHORITY_PROVENANCE")
    by_role = {
        row.get("authority_role"): row
        for row in rows
        if type(row) is dict and type(row.get("authority_role")) is str
    }
    inventory = by_role.get("V4_INVENTORY")
    registry = by_role.get("STRUCTURAL_REGISTRY")
    literal = by_role.get("RULE_LITERAL_AUTHORITY")
    _require(
        type(inventory) is dict and type(registry) is dict and type(literal) is dict,
        "AUTHORITY_PROVENANCE",
    )
    return (
        _hex_digest(inventory.get("semantic_id"), "INVENTORY_ID"),
        _hex_digest(registry.get("semantic_id"), "REGISTRY_ID"),
        _hex_digest(literal.get("raw_sha256"), "LITERAL_HASH"),
    )


def _record_reference(seed: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(payload)
    result["maximum_record_reference_id"] = _seed_semantic_id(
        seed, RECORD_REFERENCE_DOMAIN, payload
    )
    return result


def _context_object(
    record: dict[str, Any],
    type_name: str,
    identity_field: str,
    *,
    seed: dict[str, Any],
    protocol_sha256: str,
) -> dict[str, Any]:
    source_inventory_id, registry_id, literal_sha = _authority_provenance(seed)
    _require(identity_field in record, "CONTEXT_OBJECT_IDENTITY_FIELD")
    raw = _canonical_bytes(record)
    payload = {
        "maximum_protocol_sha256": protocol_sha256,
        "source_inventory_sha256": source_inventory_id,
        "external_schema_registry_id": registry_id,
        "rule_literal_authority_sha256": literal_sha,
        "record_type_name": type_name,
        "record_identity_field": identity_field,
        "record_identity": record[identity_field],
        "record_canonical_byte_length": len(raw),
        "record_canonical_sha256": _sha256(raw),
        "record": record,
    }
    return {
        "maximum_context_object_id": _seed_semantic_id(
            seed, CONTEXT_OBJECT_DOMAIN, payload
        ),
        **payload,
    }


def _reference_for_record(
    record: dict[str, Any],
    *,
    seed: dict[str, Any],
    reference_kind: str,
    type_name: str,
    identity_field: str,
    context_object_id: str | None = None,
    inventory_pointer: str | None = None,
) -> dict[str, Any]:
    raw = _canonical_bytes(record)
    payload: dict[str, Any] = {"reference_kind": reference_kind}
    if reference_kind == "CONTEXT_OBJECT":
        _require(
            type(context_object_id) is str and inventory_pointer is None,
            "CONTEXT_REFERENCE",
        )
        payload["maximum_context_object_id"] = context_object_id
    elif reference_kind == "V3_INVENTORY_POINTER":
        source_inventory_id, _registry_id, _literal_sha = _authority_provenance(seed)
        _require(
            type(inventory_pointer) is str and context_object_id is None,
            "INVENTORY_REFERENCE",
        )
        payload["source_inventory_sha256"] = source_inventory_id
        payload["inventory_json_pointer"] = inventory_pointer
    else:
        _require(
            reference_kind == "WITNESS_RECORD"
            and context_object_id is None
            and inventory_pointer is None,
            "WITNESS_REFERENCE",
        )
    payload.update(
        {
            "record_type_name": type_name,
            "record_identity_field": identity_field,
            "record_identity": record[identity_field],
            "record_canonical_byte_length": len(raw),
            "record_canonical_sha256": _sha256(raw),
        }
    )
    return _record_reference(seed, payload)


def _case24_target_octets(
    inventory: dict[str, Any], registry: dict[str, Any], seed: dict[str, Any]
) -> int:
    owner = copy.deepcopy(
        inventory["fixture_records"]["operation_results"]["LOCAL_SHUTDOWN"]
    )
    owner["result"] = {}
    _reseal_typed_record(owner, CASE24_OWNER_TYPE, registry, seed)
    owner_descriptor = _descriptor_index(registry)[CASE24_OWNER_TYPE]
    owner_boundary = _codec_boundary(owner_descriptor)
    shell_octets = len(_canonical_bytes(owner)) - len(_canonical_bytes({}))
    target = owner_boundary - shell_octets
    _require(target > 0, "CASE24_OWNER_BUDGET")
    return target


def _case24_witness(
    inventory: dict[str, Any], registry: dict[str, Any], seed: dict[str, Any]
) -> dict[str, Any]:
    owner = copy.deepcopy(
        inventory["fixture_records"]["operation_results"]["LOCAL_SHUTDOWN"]
    )
    witness = owner["result"]
    target = _case24_target_octets(inventory, registry, seed)
    batch_arrays = (
        "ordered_terminal_ingress_read_attempt_event_ids",
        "ordered_terminal_ingress_read_result_event_ids",
        "ordered_terminal_raw_ingress_commit_ids",
        "ordered_terminal_raw_ingress_actor_event_ids",
    )
    parser_array = "ordered_terminal_parser_transition_event_ids"
    free_integers = (
        "shutdown_trace_step_count",
        "final_terminal_ingress_ciphertext_octets",
        "final_terminal_ingress_plaintext_octets",
        "final_terminal_socket_receive_call_count",
        "final_terminal_tls_record_count",
        "final_terminal_tls_unwrap_iteration_count",
        "final_terminal_zero_progress_iteration_count",
        "final_terminal_ingress_automatic_output_count",
        "final_websocket_send_attempt_count",
        "final_tls_control_send_attempt_count",
    )
    for name in (*batch_arrays, parser_array):
        witness[name] = []
    for name in free_integers:
        witness[name] = 0
    witness["final_terminal_ingress_batch_count"] = 0
    witness["final_terminal_ingress_parser_unit_count"] = 0
    witness["final_peer_shutdown_poll_count"] = 0

    type_descriptor = _descriptor_index(registry)[
        "CapacityMeasurementLocalShutdownResultEvidenceV2"
    ]
    schemas = {row["value_schema_id"]: row for row in registry["value_schema_catalog"]}
    member_schemas = {
        row["member_name"]: schemas[row["value_schema_id"]]
        for row in type_descriptor["record_member_descriptors"]
    }
    parser_maximum = member_schemas[parser_array]["array_maximum_items"]
    batch_maximum = min(
        member_schemas[name]["array_maximum_items"] for name in batch_arrays
    )
    _require(
        type(parser_maximum) is int
        and type(batch_maximum) is int
        and parser_maximum >= 0
        and batch_maximum >= 0,
        "CASE24_ARRAY_LIMIT",
    )
    base_octets = len(_canonical_bytes(witness))
    maximum_decimal_residue = len(free_integers) * (len(str(SAFE_INTEGER_MAXIMUM)) - 1)

    selected: tuple[int, int, int] | None = None
    for parser_count in range(parser_maximum, -1, -1):
        parser_delta = 0 if parser_count == 0 else 67 * parser_count - 1
        parser_delta += len(str(parser_count)) - 1
        remaining = target - base_octets - parser_delta
        if remaining < 0:
            continue
        approximate = remaining // (67 * len(batch_arrays))
        for batch_count in range(
            min(batch_maximum, approximate + 2), max(-1, approximate - 2), -1
        ):
            if batch_count < 0:
                continue
            one_array_delta = 0 if batch_count == 0 else 67 * batch_count - 1
            batch_delta = len(batch_arrays) * one_array_delta
            batch_delta += len(str(batch_count)) - 1
            residue = target - base_octets - parser_delta - batch_delta
            if 0 <= residue <= maximum_decimal_residue:
                selected = (parser_count, batch_count, residue)
                break
        if selected is not None:
            break
    _require(selected is not None, "CASE24_INTEGER_RESIDUE_UNRESOLVED")
    parser_count, batch_count, residue = selected
    values = [f"{position:064x}" for position in range(max(parser_count, batch_count))]
    for name in batch_arrays:
        witness[name] = values[:batch_count]
    witness[parser_array] = values[:parser_count]
    witness["final_terminal_ingress_batch_count"] = batch_count
    witness["final_terminal_ingress_parser_unit_count"] = parser_count
    for name in free_integers:
        increment = min(len(str(SAFE_INTEGER_MAXIMUM)) - 1, residue)
        witness[name] = (
            SAFE_INTEGER_MAXIMUM
            if increment == 15
            else (10**increment if increment else 0)
        )
        residue -= increment
    _require(residue == 0, "CASE24_INTEGER_RESIDUE")
    _require(len(_canonical_bytes(witness)) == target, "CASE24_WITNESS_LENGTH")
    return witness


def _case24_context(
    witness: dict[str, Any],
    inventory: dict[str, Any],
    registry: dict[str, Any],
    seed: dict[str, Any],
    protocol_sha256: str,
) -> tuple[list[dict[str, Any]], dict[str, bytes], dict[str, Any]]:
    owner = copy.deepcopy(
        inventory["fixture_records"]["operation_results"]["LOCAL_SHUTDOWN"]
    )
    owner["result"] = copy.deepcopy(witness)
    _reseal_typed_record(owner, CASE24_OWNER_TYPE, registry, seed)
    logical = _context_object(
        owner,
        CASE24_OWNER_TYPE,
        "result_evidence_id",
        seed=seed,
        protocol_sha256=protocol_sha256,
    )
    object_id = logical["maximum_context_object_id"]
    raw = _canonical_bytes(owner)
    relative = f"context_objects/{object_id[:2]}/{object_id}.json"
    entry = {
        "context_object_position": 1,
        "claimed_maximum_context_object_id": object_id,
        "record_type_name": CASE24_OWNER_TYPE,
        "repository_relative_path": relative,
        "raw_octet_count": len(raw),
        "raw_sha256": _sha256(raw),
    }
    scope = {
        "context_kind": "OWNER_MEMBER",
        "owner_record_reference": _reference_for_record(
            owner,
            seed=seed,
            reference_kind="CONTEXT_OBJECT",
            type_name=CASE24_OWNER_TYPE,
            identity_field="result_evidence_id",
            context_object_id=object_id,
        ),
        "payload_typed_member_path": ["result"],
    }
    return [entry], {relative: raw}, scope


def _case54_witness(registry: dict[str, Any]) -> dict[str, Any]:
    descriptor = _descriptor_index(registry)[CASE54_TYPE]
    target = _codec_boundary(descriptor)
    witness = {
        "vocabulary_id": "v",
        "members": [f"a{position:03d}" for position in range(511)] + ["z"],
    }
    deficit = target - len(_canonical_bytes(witness))
    _require(deficit >= 0, "CASE54_CODEC_BUDGET")
    witness["members"][-1] = "z" * (deficit + 1)
    _require(
        len(witness["members"]) == 512
        and all(
            left < right
            for left, right in zip(
                witness["members"], witness["members"][1:], strict=False
            )
        )
        and len(_canonical_bytes(witness)) == target,
        "CASE54_WITNESS",
    )
    return witness


def _case69_witness(
    inventory: dict[str, Any], registry: dict[str, Any], seed: dict[str, Any]
) -> dict[str, Any]:
    witness = copy.deepcopy(
        inventory["fixture_records"]["operation_results"]["LOCAL_SHUTDOWN"]
    )
    body = witness["result"]
    _require(
        body.get("local_shutdown_deadline_evidence_event_id") is None,
        "CASE69_NULLABLE_SHA_BASELINE",
    )
    body["local_shutdown_deadline_evidence_event_id"] = "0" * 64
    body["shutdown_trace_step_count"] = SAFE_INTEGER_MAXIMUM
    _reseal_typed_record(witness, CASE69_TYPE, registry, seed)
    return witness


def _case69_scope(
    witness: dict[str, Any], inventory: dict[str, Any], seed: dict[str, Any]
) -> dict[str, Any]:
    spec = inventory["fixture_records"]["operation_specs"]["LOCAL_SHUTDOWN"]
    return {
        "context_kind": "OUTER_RESULT_APPLICATION",
        "constraint_scope_profile_id": CASE69_PROFILE_ID,
        "operation_result_record_reference": _reference_for_record(
            witness,
            seed=seed,
            reference_kind="WITNESS_RECORD",
            type_name=CASE69_TYPE,
            identity_field="result_evidence_id",
        ),
        "operation_spec_authority_reference": _reference_for_record(
            spec,
            seed=seed,
            reference_kind="V3_INVENTORY_POINTER",
            type_name=CASE69_SPEC_TYPE,
            identity_field="operation_spec_id",
            inventory_pointer=CASE69_SPEC_POINTER,
        ),
        "ordered_application_invocations": [
            {
                "application_name": CASE69_APPLICATION_NAME,
                "application_invocation_ordinal": 0,
                "bound_observation_ordinal": None,
            }
        ],
    }


def _local_attainer_result(
    baseline_result: dict[str, Any],
    signed_spec: dict[str, Any],
    registry: dict[str, Any],
    seed: dict[str, Any],
) -> dict[str, Any]:
    result = copy.deepcopy(baseline_result)
    body = result["result"]
    batch_count = signed_spec["spec"]["maximum_terminal_ingress_batches"]
    parser_count = signed_spec["spec"]["maximum_terminal_ingress_parser_units"]
    _require(
        type(batch_count) is int
        and 0 <= batch_count <= 20_000
        and type(parser_count) is int
        and 0 <= parser_count <= 20_000,
        "LOCAL_SEARCH_CARDINALITY_LIMIT",
    )
    batch_values = [f"{ordinal:064x}" for ordinal in range(batch_count)]
    for name in (
        "ordered_terminal_ingress_read_attempt_event_ids",
        "ordered_terminal_ingress_read_result_event_ids",
        "ordered_terminal_raw_ingress_commit_ids",
        "ordered_terminal_raw_ingress_actor_event_ids",
    ):
        body[name] = batch_values.copy()
    body["ordered_terminal_parser_transition_event_ids"] = [
        f"{ordinal:064x}" for ordinal in range(parser_count)
    ]
    for position, name in enumerate(
        (
            "local_close_dispatch_completion_event_id",
            "local_shutdown_deadline_evidence_event_id",
            "websocket_close_received_transition_event_id",
        ),
        1,
    ):
        body[name] = f"{position:064x}"
    body["shutdown_trace_step_count"] = SAFE_INTEGER_MAXIMUM
    counter_map = {
        "maximum_terminal_ingress_batches": "final_terminal_ingress_batch_count",
        "maximum_terminal_ingress_ciphertext_octets": "final_terminal_ingress_ciphertext_octets",
        "maximum_terminal_ingress_plaintext_octets": "final_terminal_ingress_plaintext_octets",
        "maximum_terminal_socket_receive_calls": "final_terminal_socket_receive_call_count",
        "maximum_terminal_tls_records": "final_terminal_tls_record_count",
        "maximum_terminal_tls_unwrap_iterations": "final_terminal_tls_unwrap_iteration_count",
        "maximum_terminal_zero_progress_iterations": "final_terminal_zero_progress_iteration_count",
        "maximum_terminal_ingress_parser_units": "final_terminal_ingress_parser_unit_count",
        "maximum_terminal_ingress_automatic_outputs": "final_terminal_ingress_automatic_output_count",
        "maximum_websocket_send_attempts": "final_websocket_send_attempt_count",
        "maximum_tls_control_send_attempts": "final_tls_control_send_attempt_count",
        "maximum_peer_shutdown_polls": "final_peer_shutdown_poll_count",
    }
    for spec_name, result_name in counter_map.items():
        body[result_name] = signed_spec["spec"][spec_name]
    _reseal_typed_record(result, CASE69_TYPE, registry, seed)
    return result


def _case475_payload(
    inventory: dict[str, Any], registry: dict[str, Any], seed: dict[str, Any]
) -> dict[str, Any]:
    baseline_spec = copy.deepcopy(
        inventory["fixture_records"]["operation_specs"]["LOCAL_SHUTDOWN"]
    )
    baseline_result = inventory["fixture_records"]["operation_results"][
        "LOCAL_SHUTDOWN"
    ]
    outer_boundary = _codec_boundary(_descriptor_index(registry)[CASE69_TYPE])
    spec_body = baseline_spec["spec"]
    candidates: list[tuple[int, str, int, dict[str, Any], dict[str, Any]]] = []
    for name, baseline in sorted(spec_body.items()):
        if type(baseline) is not int:
            continue
        low = baseline + 1
        high = low
        crossing: tuple[dict[str, Any], dict[str, Any]] | None = None
        while high <= 20_000:
            trial_spec = copy.deepcopy(baseline_spec)
            trial_spec["spec"][name] = high
            _reseal_typed_record(trial_spec, CASE69_SPEC_TYPE, registry, seed)
            try:
                trial_result = _local_attainer_result(
                    baseline_result, trial_spec, registry, seed
                )
            except ProducerReject as error:
                if str(error) == "LOCAL_SEARCH_CARDINALITY_LIMIT":
                    break
                raise
            if len(_canonical_bytes(trial_result)) > outer_boundary:
                crossing = (trial_spec, trial_result)
                break
            high = min(20_001, baseline + 2 * (high - baseline))
        if crossing is None:
            continue
        left = low
        right = high
        while left < right:
            middle = (left + right) // 2
            trial_spec = copy.deepcopy(baseline_spec)
            trial_spec["spec"][name] = middle
            _reseal_typed_record(trial_spec, CASE69_SPEC_TYPE, registry, seed)
            trial_result = _local_attainer_result(
                baseline_result, trial_spec, registry, seed
            )
            if len(_canonical_bytes(trial_result)) > outer_boundary:
                right = middle
                crossing = (trial_spec, trial_result)
            else:
                left = middle + 1
        _require(crossing is not None and left == right, "LOCAL_SEARCH_BINARY")
        winning_spec = copy.deepcopy(baseline_spec)
        winning_spec["spec"][name] = left
        _reseal_typed_record(winning_spec, CASE69_SPEC_TYPE, registry, seed)
        winning_result = _local_attainer_result(
            baseline_result, winning_spec, registry, seed
        )
        _require(
            len(_canonical_bytes(winning_result)) > outer_boundary,
            "LOCAL_SEARCH_CROSSING",
        )
        candidates.append((left - baseline, name, left, winning_spec, winning_result))
    _require(bool(candidates), "LOCAL_SEARCH_EMPTY")
    candidates.sort(key=lambda row: (row[0], row[1], row[2]))
    _delta, _name, _value, mutated_spec, prospective_result = candidates[0]
    return {
        "candidate_kind": "LOCAL_SHUTDOWN_MUTATION",
        "mutated_spec": mutated_spec,
        "prospective_result": prospective_result,
    }


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
    raise ProducerReject(f"unresolved scalar profile: {profile}")


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
    raise ProducerReject(f"unresolved target value kind: {kind}")


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
    return _record_semantic_id(
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


def _closed_index(
    rows: Any, member: str, expected_count: int, code: str
) -> dict[str, dict[str, Any]]:
    _require(type(rows) is list and len(rows) == expected_count, code)
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        _require(type(row) is dict, code)
        key = row.get(member)
        _require(type(key) is str and key not in result, code)
        result[key] = row
    return result


def _case435_invocations() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name, count in zip(
        CASE435_APPLICATION_ORDER,
        (1, 67, 67, 1, 1),
        strict=True,
    ):
        if count == 1:
            rows.append(
                {
                    "application_name": name,
                    "application_invocation_ordinal": 0,
                    "bound_observation_ordinal": None,
                }
            )
        else:
            rows.extend(
                {
                    "application_name": name,
                    "application_invocation_ordinal": ordinal,
                    "bound_observation_ordinal": ordinal,
                }
                for ordinal in range(count)
            )
    _require(len(rows) == 137, "CASE435_INVOCATION_COUNT")
    return rows


def _construct_case435_retained_context(
    seed: dict[str, Any],
    inventory: dict[str, Any],
    registry: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    canonicalization = seed["canonicalization_version"]
    schema_version = seed["measurement_schema_version"]
    recipe = seed["logical_plan_recipe_catalog"]
    predecessor_plan = recipe["ordered_logical_count_plan_records"][
        CASE435_POSITION - 1
    ]
    predecessor_program = next(
        row
        for row in recipe["ordered_profile_conditioning_program_records"]
        if row["profile_conditioning_program_id"] == CASE435_PREDECESSOR_PROGRAM_ID
    )
    _require(
        predecessor_plan["case_position"] == CASE435_POSITION
        and predecessor_plan["logical_count_plan_id"] == CASE435_PREDECESSOR_PLAN_ID
        and predecessor_plan["profile_conditioning_program_id"]
        == CASE435_PREDECESSOR_PROGRAM_ID
        and predecessor_program["profile_position"] == CASE435_PROFILE_POSITION
        and predecessor_program["maximum_constraint_scope_profile_id"]
        == CASE435_PROFILE_ID,
        "CASE435_PREDECESSOR_P1_BINDING",
    )
    schedule = predecessor_program["application_schedule_operation"]
    instructions = schedule["ordered_schedule_segment_records"][0][
        "ordered_application_instruction_records"
    ]
    _require(
        [row["application_name"] for row in instructions]
        == list(CASE435_APPLICATION_ORDER)
        and [row["application_invocation_count_per_scope_case"] for row in instructions]
        == [1, 67, 67, 1, 1]
        and schedule["application_invocation_count"] == 137,
        "CASE435_P1_SCHEDULE",
    )

    types = _closed_index(
        registry["ordered_external_type_descriptors"],
        "type_name",
        52,
        "CASE435_TYPES",
    )
    schemas = _closed_index(
        registry["value_schema_catalog"],
        "value_schema_id",
        236,
        "CASE435_SCHEMAS",
    )
    languages = _closed_index(
        registry["text_language_catalog"],
        "text_language_id",
        103,
        "CASE435_LANGUAGES",
    )
    dfas = _closed_index(
        registry["ascii_dfa_catalog"], "ascii_dfa_id", 9, "CASE435_DFAS"
    )
    target_registry = inventory["target_field_registry"]
    descriptors = target_registry["descriptors"]
    _require(len(descriptors) == CASE435_FIELD_COUNT, "CASE435_FIELD_COUNT")
    constraints = _closed_index(
        target_registry["ordered_value_constraint_definitions"],
        "value_constraint_id",
        17,
        "CASE435_CONSTRAINTS",
    )
    shapes = _closed_index(
        target_registry["ordered_value_shape_definitions"],
        "value_shape_id",
        6,
        "CASE435_SHAPES",
    )
    vocabularies = _closed_index(
        target_registry["ordered_vocabulary_definitions"],
        "vocabulary_id",
        25,
        "CASE435_VOCABULARIES",
    )
    reason_policies = _closed_index(
        target_registry["status_reason_policy_definition"]["reason_rules"],
        "reason",
        26,
        "CASE435_REASON_POLICIES",
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
    _require(selector["selector_length"] == 64, "CASE435_SELECTOR_LENGTH")
    selected_entry = selector["ordered_entries"][CASE435_MEASURED_SEQUENCE_ORDINAL - 1]
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
    selected, _a1_combinations = _select_candidate_fields(
        candidates_by_field, descriptors
    )
    exact_observation = copy.deepcopy(exact_fixture)
    exact_observation["observation_context"] = exact_context
    exact_observation["observation_context_id"] = exact_context[
        "observation_context_id"
    ]
    exact_observation["field_observations"] = [
        selected[row["field_id"]][1] for row in descriptors
    ]
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
        for entry in selector["ordered_entries"][
            : CASE435_MEASURED_SEQUENCE_ORDINAL - 1
        ]
    ]
    outer_observations: dict[str, dict[str, Any]] = {}
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
        role_selected, _role_a1 = _select_candidate_fields(role_candidates, descriptors)
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
    _require(len(observations) == 67, "CASE435_OBSERVATION_COUNT")
    root = copy.deepcopy(maximum_root)
    root["ordered_observation_ids"] = [row["observation_id"] for row in observations]
    _record_identity(
        root,
        types["TargetObservationRootV2"],
        canonicalization,
        schema_version,
    )
    return exact_observation, root, observations, selector


def _case435_payload_and_context(
    seed: dict[str, Any],
    inventory: dict[str, Any],
    registry: dict[str, Any],
    effective: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, bytes]]:
    witness, root, observations, selector = _construct_case435_retained_context(
        seed, inventory, registry
    )
    protocol_sha256 = effective["protocol_sha256"]
    logical_objects = [
        _context_object(
            root,
            "TargetObservationRootV2",
            "target_observation_root_sha256",
            seed=seed,
            protocol_sha256=protocol_sha256,
        )
    ]
    logical_objects.extend(
        _context_object(
            observation,
            "TargetObservationV2",
            "observation_id",
            seed=seed,
            protocol_sha256=protocol_sha256,
        )
        for ordinal, observation in enumerate(observations)
        if ordinal != CASE435_MEASURED_SEQUENCE_ORDINAL
    )
    logical_objects.sort(key=lambda row: row["maximum_context_object_id"])
    _require(len(logical_objects) == 67, "CASE435_LOGICAL_CONTEXT_COUNT")
    object_by_identity = {row["record_identity"]: row for row in logical_objects}
    pack_rows = [
        {
            "context_object_position": position,
            "maximum_context_object_id": row["maximum_context_object_id"],
            "record_type_name": row["record_type_name"],
            "record_identity_field": row["record_identity_field"],
            "record_identity": row["record_identity"],
            "record_canonical_byte_length": row["record_canonical_byte_length"],
            "record_canonical_sha256": row["record_canonical_sha256"],
            "record": row["record"],
        }
        for position, row in enumerate(logical_objects, 1)
    ]
    packed = effective["packed_boundary"]
    contract = packed["context_pack_contract"]
    pack_payload = {
        "context_pack_version": contract["context_pack_version"],
        "canonicalization_version": seed["canonicalization_version"],
        "measurement_schema_version": seed["measurement_schema_version"],
        "maximum_protocol_sha256": protocol_sha256,
        "case_position": CASE435_POSITION,
        "pack_position": 1,
        "ordered_context_object_records": pack_rows,
    }
    pack = {
        **pack_payload,
        "context_pack_id": _semantic_id(
            contract["context_pack_identity_domain"], pack_payload
        ),
    }
    _require(
        list(pack) == contract["ordered_pack_member_names"],
        "CASE435_PACK_MEMBER_ORDER",
    )
    pack_raw = _canonical_bytes(pack)
    _require(
        len(pack_raw) < contract["individual_pack_strict_upper_octets"],
        "CASE435_PACK_LIMIT",
    )
    pack_id = pack["context_pack_id"]
    pack_path = f"context_objects/packs/{pack_id[:2]}/{pack_id}.json"
    target_registry = inventory["target_field_registry"]
    marker_contract = inventory["marker_contract"]
    root_object = object_by_identity[root["target_observation_root_sha256"]]
    observation_references = []
    for ordinal, observation in enumerate(observations):
        if ordinal == CASE435_MEASURED_SEQUENCE_ORDINAL:
            reference = _reference_for_record(
                observation,
                seed=seed,
                reference_kind="WITNESS_RECORD",
                type_name="TargetObservationV2",
                identity_field="observation_id",
            )
        else:
            object_row = object_by_identity[observation["observation_id"]]
            reference = _reference_for_record(
                observation,
                seed=seed,
                reference_kind="CONTEXT_OBJECT",
                type_name="TargetObservationV2",
                identity_field="observation_id",
                context_object_id=object_row["maximum_context_object_id"],
            )
        observation_references.append(reference)
    scope = {
        "context_kind": "ROOT_APPLICATION",
        "constraint_scope_profile_id": CASE435_PROFILE_ID,
        "selected_root_family_position": 1,
        "measured_sequence_ordinal": CASE435_MEASURED_SEQUENCE_ORDINAL,
        "root_record_reference": _reference_for_record(
            root,
            seed=seed,
            reference_kind="CONTEXT_OBJECT",
            type_name="TargetObservationRootV2",
            identity_field="target_observation_root_sha256",
            context_object_id=root_object["maximum_context_object_id"],
        ),
        "selector_authority_reference": _reference_for_record(
            selector,
            seed=seed,
            reference_kind="V3_INVENTORY_POINTER",
            type_name="CheckpointSelectorV1",
            identity_field="checkpoint_selector_id",
            inventory_pointer="/checkpoint_selector_catalog/3/selector",
        ),
        "target_field_registry_authority_reference": _reference_for_record(
            target_registry,
            seed=seed,
            reference_kind="V3_INVENTORY_POINTER",
            type_name="TargetFieldRegistryV1",
            identity_field="target_field_registry_id",
            inventory_pointer="/target_field_registry",
        ),
        "marker_contract_authority_reference": _reference_for_record(
            marker_contract,
            seed=seed,
            reference_kind="V3_INVENTORY_POINTER",
            type_name="MarkerContractV1",
            identity_field="marker_contract_id",
            inventory_pointer="/marker_contract",
        ),
        "ordered_observation_record_references": observation_references,
        "ordered_application_invocations": _case435_invocations(),
    }
    payload = {
        "candidate_kind": "MAXIMUM_WITNESS_PACKED_CONTEXT",
        "witness_record": witness,
        "scope_witness_context": scope,
        "ordered_context_pack_entries": [
            {
                "context_pack_position": 1,
                "context_pack_id": pack_id,
                "first_maximum_context_object_id": pack_rows[0][
                    "maximum_context_object_id"
                ],
                "last_maximum_context_object_id": pack_rows[-1][
                    "maximum_context_object_id"
                ],
                "context_object_count": len(pack_rows),
                "repository_relative_path": pack_path,
                "raw_octet_count": len(pack_raw),
                "raw_sha256": _sha256(pack_raw),
            }
        ],
    }
    return payload, {pack_path: pack_raw}


def _build_candidate(
    boundary: dict[str, Any],
    seed: dict[str, Any],
    manifest: dict[str, Any],
    registry: dict[str, Any],
    inventory: dict[str, Any],
    case_position: int,
    effective: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, bytes]]:
    case, plan = _case_and_plan(seed, case_position, effective)
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
    _require(
        type(alternatives) is list and len(alternatives) == 2, "CANDIDATE_ALTERNATIVES"
    )
    maximum_rows = [
        row
        for row in alternatives
        if row.get("candidate_kind") == "MAXIMUM_WITNESS_CONTEXT"
    ]
    local_rows = [
        row
        for row in alternatives
        if row.get("candidate_kind") == "LOCAL_SHUTDOWN_MUTATION"
    ]
    _require(len(maximum_rows) == 1, "MAXIMUM_CANDIDATE_ALTERNATIVE")
    _require(len(local_rows) == 1, "LOCAL_CANDIDATE_ALTERNATIVE")
    _require(
        maximum_rows[0].get("required_case_kind") == MAXIMUM_CASE_KIND
        and local_rows[0].get("required_case_kind") == LOCAL_CASE_KIND,
        "CANDIDATE_CASE_KIND",
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
    _require(
        local_rows[0].get("ordered_member_names")
        == ["candidate_kind", "mutated_spec", "prospective_result"],
        "LOCAL_PAYLOAD_SCHEMA",
    )

    context_files: dict[str, bytes] = {}
    if case_position == CASE5_POSITION:
        payload: dict[str, Any] = {
            "candidate_kind": "MAXIMUM_WITNESS_CONTEXT",
            "witness_record": _derive_case5_witness(case, registry),
            "scope_witness_context": None,
            "ordered_context_object_entries": [],
        }
    elif case_position == CASE24_POSITION:
        witness = _case24_witness(inventory, registry, seed)
        entries, context_files, scope = _case24_context(
            witness,
            inventory,
            registry,
            seed,
            effective["protocol_sha256"],
        )
        payload = {
            "candidate_kind": "MAXIMUM_WITNESS_CONTEXT",
            "witness_record": witness,
            "scope_witness_context": scope,
            "ordered_context_object_entries": entries,
        }
    elif case_position == CASE54_POSITION:
        payload = {
            "candidate_kind": "MAXIMUM_WITNESS_CONTEXT",
            "witness_record": _case54_witness(registry),
            "scope_witness_context": None,
            "ordered_context_object_entries": [],
        }
    elif case_position == CASE69_POSITION:
        witness = _case69_witness(inventory, registry, seed)
        payload = {
            "candidate_kind": "MAXIMUM_WITNESS_CONTEXT",
            "witness_record": witness,
            "scope_witness_context": _case69_scope(witness, inventory, seed),
            "ordered_context_object_entries": [],
        }
    elif case_position == CASE435_POSITION:
        payload, context_files = _case435_payload_and_context(
            seed, inventory, registry, effective
        )
    else:
        _require(case_position == CASE475_POSITION, "UNSUPPORTED_CASE")
        payload = _case475_payload(inventory, registry, seed)

    packed_case = case_position == CASE435_POSITION
    if packed_case:
        packed_contract = effective["packed_boundary"][
            "packed_context_candidate_contract"
        ]
        candidate_version = packed_contract["candidate_version_literal"]
        identity_domain = packed_contract["candidate_identity_domain"]
        _require(
            list(payload) == packed_contract["ordered_payload_member_names"],
            "PACKED_CANDIDATE_PAYLOAD_SCHEMA",
        )
    else:
        candidate_version = schema.get("version_literal")
        identity_domain = schema.get("identity_domain")
    _require(type(candidate_version) is str, "CANDIDATE_VERSION")
    _require(type(identity_domain) is str, "CANDIDATE_IDENTITY_DOMAIN")

    candidate: dict[str, Any] = {
        "candidate_version": candidate_version,
        "canonicalization_version": boundary.get("canonicalization_version"),
        "measurement_schema_version": boundary.get("measurement_schema_version"),
        "protocol_version": boundary.get("protocol_version"),
        "seed_catalog_id": effective["seed_id"],
        "finalization_manifest_id": effective["manifest_id"],
        "case_position": case_position,
        "case_kind": case["case_kind"],
        "case_binding": json.loads(_canonical_bytes(case["case_binding"])),
        "logical_count_plan_id": plan["logical_count_plan_id"],
        "candidate_payload": payload,
    }
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
    _require(
        (effective["mode"] == PREDECESSOR_MODE)
        == (
            effective["seed_id"] == seed.get("seed_catalog_id")
            and effective["manifest_id"] == manifest.get("finalization_manifest_id")
        ),
        "EFFECTIVE_AUTHORITY_MODE",
    )
    return candidate, context_files


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


def _cleanup_directory_contents(directory: int) -> None:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    for entry in os.listdir(directory):
        try:
            metadata = os.stat(entry, dir_fd=directory, follow_symlinks=False)
        except FileNotFoundError:
            continue
        if stat.S_ISDIR(metadata.st_mode):
            try:
                child = os.open(entry, flags, dir_fd=directory)
            except OSError:
                continue
            try:
                _cleanup_directory_contents(child)
            finally:
                os.close(child)
            try:
                os.rmdir(entry, dir_fd=directory)
            except OSError:
                pass
        else:
            _safe_unlink(entry, directory)


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
        _cleanup_directory_contents(bundle)
    finally:
        os.close(bundle)
    try:
        os.rmdir(name, dir_fd=parent)
    except OSError:
        pass


def _open_or_create_directory(parent: int, name: str) -> int:
    _require(name not in {"", ".", ".."} and "/" not in name, "OUTPUT_DIRECTORY_NAME")
    try:
        os.mkdir(name, mode=0o700, dir_fd=parent)
    except FileExistsError:
        pass
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(name, flags, dir_fd=parent)
    metadata = os.fstat(descriptor)
    _require(stat.S_ISDIR(metadata.st_mode), "OUTPUT_DIRECTORY_TYPE")
    _require(stat.S_IMODE(metadata.st_mode) == 0o700, "OUTPUT_DIRECTORY_MODE")
    return descriptor


def _write_exclusive_regular(directory: int, name: str, raw: bytes) -> None:
    _require(name not in {"", ".", ".."} and "/" not in name, "OUTPUT_FILE_NAME")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(name, flags, 0o600, dir_fd=directory)
    try:
        os.fchmod(descriptor, 0o600)
        _write_all(descriptor, raw)
        os.fsync(descriptor)
        metadata = os.fstat(descriptor)
        _require(stat.S_ISREG(metadata.st_mode), "OUTPUT_FILE_TYPE")
        _require(metadata.st_nlink == 1, "OUTPUT_FILE_LINK_COUNT")
        _require(stat.S_IMODE(metadata.st_mode) == 0o600, "OUTPUT_FILE_MODE")
        _require(metadata.st_size == len(raw), "OUTPUT_FILE_SIZE")
    finally:
        os.close(descriptor)
    os.fsync(directory)


def _write_context_files(
    staging: int, context_files: dict[str, bytes], file_limit: int
) -> None:
    _require(len(context_files) == len(set(context_files)), "CONTEXT_PATH_DUPLICATE")
    for relative_path, raw in sorted(context_files.items()):
        parts = _relative_parts(relative_path)
        _require(
            len(parts) in {3, 4}
            and parts[0] == "context_objects"
            and (len(parts) == 3 or parts[1] == "packs")
            and len(parts[-2]) == 2
            and all(character in "0123456789abcdef" for character in parts[-2])
            and parts[-1].endswith(".json"),
            "CONTEXT_PATH_SCHEMA",
        )
        _require(len(raw) < file_limit, "CONTEXT_FILE_LIMIT")
        current = os.dup(staging)
        try:
            for component in parts[:-1]:
                child = _open_or_create_directory(current, component)
                os.close(current)
                current = child
            _write_exclusive_regular(current, parts[-1], raw)
        finally:
            os.close(current)


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
    context_files: dict[str, bytes],
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
            _write_context_files(staging, context_files, file_limit)

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
    try:
        case_position = int(case_text, 10)
    except ValueError as error:
        raise InvocationReject("CASE_POSITION_NOT_DECIMAL") from error
    if case_position not in PILOT_CASE_POSITIONS or case_text != str(case_position):
        raise InvocationReject("CASE_POSITION_NOT_CANONICAL_PILOT_MEMBER")
    if (
        not os.path.isabs(repository_root)
        or os.path.normpath(repository_root) != repository_root
    ):
        raise InvocationReject("REPOSITORY_ROOT_MUST_BE_CANONICAL_ABSOLUTE")
    allowed_boundaries = {
        os.path.join(repository_root, BOUNDARY_RELATIVE_PATH),
        os.path.join(repository_root, PACKED_BOUNDARY_RELATIVE_PATH),
    }
    if boundary_path not in allowed_boundaries:
        raise InvocationReject("BOUNDARY_PATH_MISMATCH")
    if (
        boundary_path == os.path.join(repository_root, BOUNDARY_RELATIVE_PATH)
        and case_position != CASE5_POSITION
    ):
        raise InvocationReject("ONLY_CANONICAL_CASE_5_IS_SUPPORTED")
    if not os.path.isabs(output_root) or os.path.normpath(output_root) != output_root:
        raise InvocationReject("OUTPUT_ROOT_MUST_BE_CANONICAL_ABSOLUTE")
    return repository_root, boundary_path, case_position, output_root


def _produce(
    repository_root: str, boundary_path: str, case_position: int, output_root: str
) -> None:
    predecessor_path = os.path.join(repository_root, BOUNDARY_RELATIVE_PATH)
    packed_path = os.path.join(repository_root, PACKED_BOUNDARY_RELATIVE_PATH)
    _require(
        boundary_path in {predecessor_path, packed_path},
        "BOUNDARY_PATH",
    )
    _require(
        boundary_path == packed_path or case_position == CASE5_POSITION,
        "PREDECESSOR_MODE_CASE5_ONLY",
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
        (
            boundary,
            seed,
            manifest,
            registry,
            inventory,
            snapshots,
            limits,
        ) = _load_frozen_inputs(repository)
        effective = (
            {
                "mode": PREDECESSOR_MODE,
                "seed_id": seed["seed_catalog_id"],
                "manifest_id": manifest["finalization_manifest_id"],
                "protocol_sha256": _sha256(_pretty_bytes(manifest)),
                "case435_plan": None,
                "packed_boundary": None,
            }
            if boundary_path == predecessor_path
            else _load_packed_successor_authorities(
                repository,
                boundary,
                seed,
                manifest,
                snapshots,
                limits,
            )
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
        candidate, context_files = _build_candidate(
            boundary,
            seed,
            manifest,
            registry,
            inventory,
            case_position,
            effective,
        )
        _publish_candidate(
            output_root,
            candidate,
            context_files,
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

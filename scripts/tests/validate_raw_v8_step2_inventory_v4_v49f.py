#!/usr/bin/env python3
"""Independently validate the narrowly migrated Raw-V8 Step-2 V4 inventory.

This verifier is deliberately standard-library-only.  It imports neither the
V4 migrator, the V3 generator or validator, production ``riskyieldmm`` code,
nor any producer-owned constants.  The complete expected V4 object is rebuilt
from the physically pinned accepted V3 golden and the one accepted compact
maximum-proof correction.  Any change outside that exact patch fails closed.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import stat
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Final, NamedTuple

CANONICALIZATION_VERSION: Final = "riskyieldmm_canonical_json_v1"
MEASUREMENT_SCHEMA_VERSION: Final = "riskyieldmm_physical_transport_a2m_raw_v49f_v8"
V3_SCHEMA_VERSION: Final = "riskyieldmm.raw_v8_step2_inventory.v3"
V4_SCHEMA_VERSION: Final = "riskyieldmm.raw_v8_step2_inventory.v4"

V3_INVENTORY_RELATIVE_PATH: Final = "tests/raw_v8_step2_inventory_v49f.json"
V4_INVENTORY_RELATIVE_PATH: Final = "tests/raw_v8_step2_inventory_v4_v49f.json"
V3_INVENTORY_OCTETS: Final = 5_264_966
V3_INVENTORY_RAW_SHA256: Final = (
    "f33c1019afa7f49a316aac1bfbef7498e240f391e4fee00dfd95fdcda658669f"
)
V3_INVENTORY_ID: Final = (
    "128d07a45dc2300c140f333cc3a45e2497aaa4089684f6e44da048ab403bbf9d"
)
V4_INVENTORY_OCTETS: Final = 5_265_855
V4_INVENTORY_RAW_SHA256: Final = (
    "de91eac92d1c36cf1670b2484392fbf1c633d75f928c8e70fcd5e71ae798db2b"
)
V4_INVENTORY_ID: Final = (
    "d1435d11a6c9e110b5afb6dacb312f7cd92be71868b2ebe1c8f69ba7f1def3fd"
)
MAXIMUM_ROW_UNIVERSE_SHA256: Final = (
    "836db59c1111080882dea078a27847b130d18eed474a8982ebad2e062d532d1c"
)

STRUCTURAL_REGISTRY_RELATIVE_PATH: Final = (
    "scripts/tests/raw_v8_step2_external_schema_v2_structural_registry_v49f.json"
)
STRUCTURAL_REGISTRY_OCTETS: Final = 1_469_663
STRUCTURAL_REGISTRY_RAW_SHA256: Final = (
    "9160297ff316c5931737c92f8b359f0a1e2ec22f0aa996ef3b09cf830dc96bf3"
)
STRUCTURAL_REGISTRY_ID: Final = (
    "5dc95a3e99c5646e912b6a7e9c3970cf2489d560ea890b0a19d38af4c51c2140"
)
STRUCTURAL_REGISTRY_DOMAIN: Final = (
    "RiskYieldMMA2MStep2ExternalSchemaRegistryV2V4_9F_RawV8"
)
TARGET_FIELD_REGISTRY_ID: Final = (
    "ae01f3a8e53163eefdc77bb4a863710dc851aec22738719639a3c21fe683a618"
)
TARGET_FIELD_REGISTRY_DOMAIN: Final = "RiskYieldMMA2MTargetFieldRegistryV4_9F_RawV8"

COMPACT_CORRECTION_ROLE: Final = "STEP2_COMPACT_MAXIMUM_PROOF_V2_CORRECTION"
COMPACT_CORRECTION_RELATIVE_PATH: Final = (
    "docs/research/"
    "v4_9f_a2_raw_v8_step2_compact_maximum_proof_v2_correction_2026-08-02.md"
)
COMPACT_CORRECTION_OCTETS: Final = 49_849
COMPACT_CORRECTION_SHA256: Final = (
    "f4d35405ef1e66a8ba1c59027fc2097a56563d50408eb72cc48895d2127b71b4"
)

INVENTORY_EXCLUSIVE_OCTET_LIMIT: Final = 16_777_216
SOURCE_EXCLUSIVE_OCTET_LIMIT: Final = 16_777_216
MAXIMUM_JSON_NESTING_DEPTH: Final = 16
SAFE_INTEGER_MAXIMUM: Final = 9_007_199_254_740_991
SHA256_HEX_LENGTH: Final = 64

NORMATIVE_DOCUMENTS: Final = (
    (
        "PARENT_MARKER_OPERATION_TARGET_PROTOCOL",
        "docs/research/"
        "v4_9f_a2_marker_operation_target_v8_protocol_freeze_2026-07-22.md",
        212_471,
        "15b42d32afe5fdff74890b2c18f735ff761244548729142c4ff2b1034fee2388",
    ),
    (
        "STEP2_V2_CONTRACT_FREEZE",
        "docs/research/v4_9f_a2_raw_v8_step2_v2_contract_freeze_2026-07-26.md",
        34_591,
        "355548cb3ef323ab45b0289be9891ab578b75d0147639ab37c9f3e5ff251aa1c",
    ),
    (
        "STEP2_EXTERNAL_SCHEMA_V2_CORRECTION",
        "docs/research/"
        "v4_9f_a2_raw_v8_step2_external_schema_v2_correction_2026-07-28.md",
        217_135,
        "29ec141e53adeb1c0afd51f205f5b57eb784b8859b5ba40958299abd1b713b55",
    ),
    (
        COMPACT_CORRECTION_ROLE,
        COMPACT_CORRECTION_RELATIVE_PATH,
        COMPACT_CORRECTION_OCTETS,
        COMPACT_CORRECTION_SHA256,
    ),
    (
        "STEP3_TARGET_AND_LIFECYCLE_CORRECTION",
        "docs/research/"
        "v4_9f_a2_raw_v8_step3_target_and_lifecycle_correction_2026-07-26.md",
        435_478,
        "635952095b0b20089d5ec2c13104255ebeeff11535c8f94131a4983a1a9fec0a",
    ),
)

INVENTORY_ROOT_KEYS: Final = frozenset(
    {
        "schema_version",
        "normative_document_inputs",
        "invariants",
        "target_field_registry",
        "operation_counter_schema",
        "marker_contract",
        "checkpoint_selector_catalog",
        "ingress_logical_oracle_profile_catalog",
        "external_schema_registry_v2",
        "operation_contracts",
        "fixture_records",
        "inventory_sha256",
    }
)
PROTECTED_ROOT_MEMBERS: Final = (
    "target_field_registry",
    "operation_counter_schema",
    "marker_contract",
    "checkpoint_selector_catalog",
    "ingress_logical_oracle_profile_catalog",
    "external_schema_registry_v2",
    "operation_contracts",
    "fixture_records",
)
NORMATIVE_DOCUMENT_KEYS: Final = frozenset(
    {
        "document_role",
        "repository_relative_path",
        "raw_octet_count",
        "raw_sha256",
    }
)
COMPACT_MAXIMUM_PROOF_V2_CONTRACT: Final = {
    "mathematical_acceptance_rule": "SOUND_UPPER_BOUND_PLUS_LEGAL_ATTAINMENT_V1",
    "global_least_attainer_required": False,
    "ordered_component_choice_evidence_required": False,
    "proof_resource_report_is_separate": True,
    "publication_selection_policy": "PINNED_ACCEPTED_ATTAINER_V1",
    "maximum_publication_row_count": 474,
    "verifier_owned_scope_case_count": 475,
}

STRUCTURAL_REGISTRY_KEYS: Final = frozenset(
    {
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
)
STRUCTURAL_REGISTRY_IDENTITY_PAYLOAD_MEMBERS: Final = (
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

MAXIMUM_SCOPE_PROFILE_DOMAIN: Final = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumConstraintScopeProfileV1V4_9F_RawV8"
)
PROFILE_KEYS: Final = frozenset(
    {
        "profile_position",
        "profile_kind",
        "constraint_scope",
        "measured_type_name",
        "operation_kind",
        "ordered_source_authority_pointers",
        "ordered_source_authority_ids",
        "selector_catalog_position",
        "selector_catalog_name",
        "checkpoint_selector_id",
        "checkpoint_selector_entry_id",
        "expected_checkpoint_marker_kind",
        "expected_occurrence_index_within_kind",
        "selector_position",
        "checkpoint_outcome",
        "checkpoint_binding_status",
        "checkpoint_binding_unavailable_reason",
        "checkpoint_field_unavailable_reason",
        "ordered_admissible_root_families",
        "application_schedule_formula",
        "maximum_constraint_scope_profile_id",
    }
)
PROFILE_ID_PAYLOAD_MEMBERS: Final = (
    "profile_position",
    "profile_kind",
    "constraint_scope",
    "measured_type_name",
    "operation_kind",
    "ordered_source_authority_pointers",
    "ordered_source_authority_ids",
    "selector_catalog_position",
    "selector_catalog_name",
    "checkpoint_selector_id",
    "checkpoint_selector_entry_id",
    "expected_checkpoint_marker_kind",
    "expected_occurrence_index_within_kind",
    "selector_position",
    "checkpoint_outcome",
    "checkpoint_binding_status",
    "checkpoint_binding_unavailable_reason",
    "checkpoint_field_unavailable_reason",
    "ordered_admissible_root_families",
    "application_schedule_formula",
)


class InventoryV4ValidationError(ValueError):
    """Controlled V4 inventory validation failure."""


class FrozenFile(NamedTuple):
    """One securely retained physical-file snapshot."""

    path: Path
    raw: bytes
    signature: tuple[int, ...]
    device_inode: tuple[int, int]


class InputSpec(NamedTuple):
    """One pinned or candidate input and its read bound."""

    label: str
    path: Path
    maximum_octets: int


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise InventoryV4ValidationError(message)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


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


def _is_sha256(value: Any) -> bool:
    return (
        type(value) is str
        and len(value) == SHA256_HEX_LENGTH
        and all(character in "0123456789abcdef" for character in value)
    )


def _validate_exact_keys(
    value: Any, expected: frozenset[str], *, label: str
) -> dict[str, Any]:
    _require(type(value) is dict, f"{label} must be an exact object")
    missing = sorted(expected - set(value))
    extra = sorted(set(value) - expected)
    _require(
        not missing and not extra,
        f"{label} keys differ: missing={missing}, extra={extra}",
    )
    return value


def _repository_relative_path(value: str) -> Path:
    _require(type(value) is str and bool(value), "repository path must be text")
    _require("\\" not in value, f"repository path uses an alternate separator: {value}")
    parsed = PurePosixPath(value)
    _require(
        not parsed.is_absolute()
        and bool(parsed.parts)
        and all(part not in {"", ".", ".."} for part in parsed.parts),
        f"repository path is not normalized relative POSIX: {value}",
    )
    _require(parsed.as_posix() == value, f"repository path is not canonical: {value}")
    return Path(*parsed.parts)


def _absolute_below_repository(
    path: Path, *, repository_root: Path, label: str
) -> Path:
    candidate = path if path.is_absolute() else repository_root / path
    _require(candidate.is_absolute(), f"{label} path is not absolute")
    _require(
        all(part not in {"", ".", ".."} for part in candidate.parts[1:]),
        f"{label} path is not lexically normalized",
    )
    try:
        relative = candidate.relative_to(repository_root)
    except ValueError as exc:
        raise InventoryV4ValidationError(
            f"{label} path is outside the repository root"
        ) from exc
    _require(bool(relative.parts), f"{label} path names the repository directory")
    return candidate


def _stat_signature(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_uid,
        value.st_gid,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _secure_bounded_read(spec: InputSpec) -> FrozenFile:
    """Read through no-follow descriptors and retain exact physical identity."""

    _require(type(spec.maximum_octets) is int and spec.maximum_octets > 1, "bad bound")
    _require(spec.path.is_absolute(), f"{spec.label} secure path is not absolute")
    _require(
        hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_NONBLOCK"),
        "platform lacks mandatory secure-open flags",
    )
    hard_limit = spec.maximum_octets - 1
    directory_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    directory_flags |= getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW
    file_flags = os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0)
    file_flags |= os.O_NOFOLLOW

    directory_fd: int | None = None
    file_fd: int | None = None
    chunks: list[bytes] = []
    before: os.stat_result | None = None
    try:
        directory_fd = os.open("/", directory_flags)
        parts = spec.path.parts[1:]
        _require(bool(parts), f"{spec.label} path names no file")
        for part in parts[:-1]:
            next_fd = os.open(part, directory_flags, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = next_fd
        file_name = parts[-1]
        file_fd = os.open(file_name, file_flags, dir_fd=directory_fd)
        before = os.fstat(file_fd)
        _require(stat.S_ISREG(before.st_mode), f"{spec.label} is not a regular file")
        _require(before.st_nlink == 1, f"{spec.label} hard-link count differs from one")
        _require(before.st_size <= hard_limit, f"{spec.label} exceeds its byte bound")

        total = 0
        while True:
            remaining = hard_limit + 1 - total
            _require(remaining > 0, f"{spec.label} exceeds its byte bound")
            chunk = os.read(file_fd, min(65_536, remaining))
            if not chunk:
                break
            total += len(chunk)
            _require(total <= hard_limit, f"{spec.label} exceeds its byte bound")
            chunks.append(chunk)

        after = os.fstat(file_fd)
        _require(
            _stat_signature(before) == _stat_signature(after),
            f"{spec.label} changed during read",
        )
        bound_entry = os.stat(file_name, dir_fd=directory_fd, follow_symlinks=False)
        _require(
            not stat.S_ISLNK(bound_entry.st_mode)
            and _stat_signature(before) == _stat_signature(bound_entry),
            f"{spec.label} directory-entry identity changed during read",
        )
    except OSError as exc:
        raise InventoryV4ValidationError(
            f"cannot securely read {spec.label} without symlink traversal"
        ) from exc
    finally:
        if file_fd is not None:
            os.close(file_fd)
        if directory_fd is not None:
            os.close(directory_fd)

    _require(before is not None, f"{spec.label} secure read produced no identity")
    raw = b"".join(chunks)
    _require(len(raw) == before.st_size, f"{spec.label} was truncated during read")
    return FrozenFile(
        path=spec.path,
        raw=raw,
        signature=_stat_signature(before),
        device_inode=(before.st_dev, before.st_ino),
    )


def _scan_json_structure(raw: bytes, *, label: str) -> None:
    _require(not raw.startswith(b"\xef\xbb\xbf"), f"{label} JSON BOM is forbidden")
    stack: list[int] = []
    closing = {ord("}"): ord("{"), ord("]"): ord("[")}
    in_string = False
    escaped = False
    for octet in raw:
        if in_string:
            if escaped:
                escaped = False
            elif octet == ord("\\"):
                escaped = True
            elif octet == ord('"'):
                in_string = False
            elif octet < 0x20:
                raise InventoryV4ValidationError(
                    f"{label} JSON contains an unescaped control octet"
                )
            continue
        if octet == ord('"'):
            in_string = True
        elif octet in (ord("["), ord("{")):
            stack.append(octet)
            _require(
                len(stack) <= MAXIMUM_JSON_NESTING_DEPTH,
                f"{label} JSON nesting exceeds {MAXIMUM_JSON_NESTING_DEPTH}",
            )
        elif octet in closing:
            _require(
                bool(stack) and stack[-1] == closing[octet],
                f"{label} JSON structural delimiters are unbalanced",
            )
            stack.pop()
    _require(not in_string and not escaped, f"{label} JSON string is unterminated")
    _require(not stack, f"{label} JSON container is unterminated")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InventoryV4ValidationError(f"duplicate JSON key is forbidden: {key}")
        result[key] = value
    return result


def _reject_float(value: str) -> Any:
    raise InventoryV4ValidationError(f"JSON float is forbidden: {value}")


def _reject_nonfinite(value: str) -> Any:
    raise InventoryV4ValidationError(f"non-finite JSON value is forbidden: {value}")


def _parse_integer(value: str) -> int:
    parsed = int(value, 10)
    _require(
        -SAFE_INTEGER_MAXIMUM <= parsed <= SAFE_INTEGER_MAXIMUM,
        "JSON integer is outside the exact safe-integer domain",
    )
    return parsed


def _validate_json_scalars(value: Any, *, label: str) -> None:
    pending = [value]
    while pending:
        current = pending.pop()
        if type(current) is dict:
            pending.extend(current.keys())
            pending.extend(current.values())
        elif type(current) is list:
            pending.extend(current)
        elif type(current) is str:
            _require(
                not any(0xD800 <= ord(character) <= 0xDFFF for character in current),
                f"{label} JSON string contains a surrogate code point",
            )
        else:
            _require(
                current is None
                or type(current) is bool
                or (
                    type(current) is int
                    and -SAFE_INTEGER_MAXIMUM <= current <= SAFE_INTEGER_MAXIMUM
                ),
                f"{label} JSON scalar is outside the exact I-JSON subset",
            )


def _decode_pretty_json(raw: bytes, *, label: str) -> Any:
    _scan_json_structure(raw, label=label)
    try:
        text = raw.decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_float=_reject_float,
            parse_int=_parse_integer,
            parse_constant=_reject_nonfinite,
        )
    except (
        InventoryV4ValidationError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        RecursionError,
    ) as exc:
        raise InventoryV4ValidationError(
            f"{label} is not strict canonical JSON"
        ) from exc
    _validate_json_scalars(value, label=label)
    _require(_pretty_bytes(value) == raw, f"{label} is not canonical pretty JSON")
    return value


def _document_record(
    role: str, relative_path: str, octets: int, sha256: str
) -> dict[str, Any]:
    return {
        "document_role": role,
        "repository_relative_path": relative_path,
        "raw_octet_count": octets,
        "raw_sha256": sha256,
    }


def _input_specs(
    *, repository_root: Path, inventory_path: Path
) -> tuple[InputSpec, ...]:
    specs = [
        InputSpec(
            "accepted V3 inventory",
            repository_root / _repository_relative_path(V3_INVENTORY_RELATIVE_PATH),
            INVENTORY_EXCLUSIVE_OCTET_LIMIT,
        ),
        InputSpec(
            "standalone structural registry",
            repository_root
            / _repository_relative_path(STRUCTURAL_REGISTRY_RELATIVE_PATH),
            SOURCE_EXCLUSIVE_OCTET_LIMIT,
        ),
    ]
    specs.extend(
        InputSpec(
            f"normative document {role}",
            repository_root / _repository_relative_path(relative_path),
            SOURCE_EXCLUSIVE_OCTET_LIMIT,
        )
        for role, relative_path, _octets, _sha256_value in NORMATIVE_DOCUMENTS
    )
    specs.append(
        InputSpec(
            "candidate V4 inventory",
            inventory_path,
            INVENTORY_EXCLUSIVE_OCTET_LIMIT,
        )
    )
    return tuple(specs)


def _read_all(specs: tuple[InputSpec, ...]) -> dict[str, FrozenFile]:
    snapshots: dict[str, FrozenFile] = {}
    inode_owner: dict[tuple[int, int], str] = {}
    for spec in specs:
        _require(spec.label not in snapshots, "input labels are not unique")
        snapshot = _secure_bounded_read(spec)
        prior_owner = inode_owner.get(snapshot.device_inode)
        _require(
            prior_owner is None,
            f"input inode alias is forbidden: {prior_owner} and {spec.label}",
        )
        inode_owner[snapshot.device_inode] = spec.label
        snapshots[spec.label] = snapshot
    return snapshots


def _revalidate_snapshots(
    specs: tuple[InputSpec, ...], expected: dict[str, FrozenFile]
) -> None:
    repeated = _read_all(specs)
    _require(set(repeated) == set(expected), "repeated source snapshot set differs")
    for label in sorted(expected):
        first = expected[label]
        second = repeated[label]
        _require(
            first.raw == second.raw
            and first.signature == second.signature
            and first.device_inode == second.device_inode,
            f"{label} changed before V4 acceptance",
        )


def _validate_physical_pins(snapshots: dict[str, FrozenFile]) -> None:
    v3 = snapshots["accepted V3 inventory"].raw
    _require(len(v3) == V3_INVENTORY_OCTETS, "accepted V3 inventory octets differ")
    _require(
        _sha256(v3) == V3_INVENTORY_RAW_SHA256,
        "accepted V3 inventory raw SHA-256 differs",
    )
    registry = snapshots["standalone structural registry"].raw
    _require(
        len(registry) == STRUCTURAL_REGISTRY_OCTETS,
        "standalone structural registry octets differ",
    )
    _require(
        _sha256(registry) == STRUCTURAL_REGISTRY_RAW_SHA256,
        "standalone structural registry raw SHA-256 differs",
    )
    for role, _path, octets, sha256 in NORMATIVE_DOCUMENTS:
        raw = snapshots[f"normative document {role}"].raw
        _require(len(raw) == octets, f"normative document octets differ: {role}")
        _require(
            _sha256(raw) == sha256,
            f"normative document raw SHA-256 differs: {role}",
        )
    candidate = snapshots["candidate V4 inventory"].raw
    _require(
        len(candidate) == V4_INVENTORY_OCTETS,
        "accepted V4 inventory octets differ",
    )
    _require(
        _sha256(candidate) == V4_INVENTORY_RAW_SHA256,
        "accepted V4 inventory raw SHA-256 differs",
    )


def _validate_inventory_identity(
    inventory: dict[str, Any], *, expected: str | None, label: str
) -> str:
    identity = inventory.get("inventory_sha256")
    _require(_is_sha256(identity), f"{label} inventory_sha256 differs")
    unsigned = dict(inventory)
    unsigned.pop("inventory_sha256")
    recomputed = _sha256(_canonical_bytes(unsigned))
    _require(recomputed == identity, f"{label} semantic inventory identity differs")
    if expected is not None:
        _require(identity == expected, f"{label} identity differs from its pin")
    return identity


def _validate_structural_registry(
    registry: Any, *, raw: bytes, label: str
) -> dict[str, Any]:
    value = _validate_exact_keys(registry, STRUCTURAL_REGISTRY_KEYS, label=label)
    _require(_pretty_bytes(value) == raw, f"{label} bytes differ from standalone pin")
    _require(
        value["canonicalization_version"] == CANONICALIZATION_VERSION
        and value["measurement_schema_version"] == MEASUREMENT_SCHEMA_VERSION
        and value["record_domain"] == STRUCTURAL_REGISTRY_DOMAIN,
        f"{label} identity envelope differs",
    )
    payload = {
        member: value[member] for member in STRUCTURAL_REGISTRY_IDENTITY_PAYLOAD_MEMBERS
    }
    _require(
        _semantic_id(STRUCTURAL_REGISTRY_DOMAIN, payload)
        == value["external_schema_registry_id"]
        == STRUCTURAL_REGISTRY_ID,
        f"{label} semantic identity differs",
    )
    _require(
        type(value["external_type_descriptor_count"]) is int
        and value["external_type_descriptor_count"] == 52
        and len(value["ordered_external_type_descriptors"]) == 52,
        f"{label} external descriptor count differs",
    )
    return value


def _validate_target_field_registry(value: Any, *, label: str) -> None:
    _require(type(value) is dict, f"{label} must be an object")
    _require(
        value.get("canonicalization_version") == CANONICALIZATION_VERSION
        and value.get("measurement_schema_version") == MEASUREMENT_SCHEMA_VERSION
        and value.get("record_domain") == TARGET_FIELD_REGISTRY_DOMAIN,
        f"{label} identity envelope differs",
    )
    identity = value.get("target_field_registry_id")
    _require(_is_sha256(identity), f"{label} identity is not SHA-256")
    excluded = {
        "canonicalization_version",
        "measurement_schema_version",
        "record_domain",
        "target_field_registry_id",
    }
    payload = {key: item for key, item in value.items() if key not in excluded}
    _require(
        _semantic_id(TARGET_FIELD_REGISTRY_DOMAIN, payload)
        == identity
        == TARGET_FIELD_REGISTRY_ID,
        f"{label} semantic identity differs",
    )


def _validate_document_records(actual: Any) -> None:
    _require(type(actual) is list, "V4 normative_document_inputs must be an array")
    expected = [_document_record(*item) for item in NORMATIVE_DOCUMENTS]
    _require(len(actual) == len(expected), "V4 normative input count differs from five")
    for position, (record, expected_record) in enumerate(
        zip(actual, expected, strict=True), 1
    ):
        _validate_exact_keys(
            record,
            NORMATIVE_DOCUMENT_KEYS,
            label=f"V4 normative input {position}",
        )
        _require(
            type(record["document_role"]) is str
            and type(record["repository_relative_path"]) is str
            and type(record["raw_octet_count"]) is int
            and type(record["raw_sha256"]) is str,
            f"V4 normative input {position} member type differs",
        )
        _require(
            record == expected_record,
            f"V4 normative input {position} differs from its authority",
        )


def _validate_compact_contract(value: Any) -> None:
    expected_keys = frozenset(COMPACT_MAXIMUM_PROOF_V2_CONTRACT)
    contract = _validate_exact_keys(
        value,
        expected_keys,
        label="compact_maximum_proof_v2_contract",
    )
    for member in (
        "mathematical_acceptance_rule",
        "publication_selection_policy",
    ):
        _require(type(contract[member]) is str, f"{member} must be exact text")
    for member in (
        "global_least_attainer_required",
        "ordered_component_choice_evidence_required",
        "proof_resource_report_is_separate",
    ):
        _require(type(contract[member]) is bool, f"{member} must be an exact boolean")
    for member in (
        "maximum_publication_row_count",
        "verifier_owned_scope_case_count",
    ):
        _require(
            type(contract[member]) is int,
            f"{member} must be an exact integer, not boolean",
        )
    _require(
        _canonical_bytes(contract)
        == _canonical_bytes(COMPACT_MAXIMUM_PROOF_V2_CONTRACT),
        "compact_maximum_proof_v2_contract differs",
    )


def _expected_v4_from_v3(v3: dict[str, Any]) -> dict[str, Any]:
    expected = copy.deepcopy(v3)
    expected["schema_version"] = V4_SCHEMA_VERSION
    expected["normative_document_inputs"] = [
        _document_record(*item) for item in NORMATIVE_DOCUMENTS
    ]
    invariants = expected["invariants"]
    _require(type(invariants) is dict, "accepted V3 invariants must be an object")
    invariants["inventory_schema_version"] = V4_SCHEMA_VERSION
    counts = invariants["counts"]
    _require(type(counts) is dict, "accepted V3 invariant counts must be an object")
    counts["normative_document_input_count"] = 5
    hashes = invariants["normative_document_sha256_by_role"]
    _require(type(hashes) is dict, "accepted V3 document hash mirror must be an object")
    hashes[COMPACT_CORRECTION_ROLE] = COMPACT_CORRECTION_SHA256
    invariants["compact_maximum_proof_v2_contract"] = copy.deepcopy(
        COMPACT_MAXIMUM_PROOF_V2_CONTRACT
    )
    expected.pop("inventory_sha256")
    expected["inventory_sha256"] = _sha256(_canonical_bytes(expected))
    _require(
        expected["inventory_sha256"] == V4_INVENTORY_ID,
        "independently derived V4 identity differs from its acceptance pin",
    )
    return expected


def _validate_profile_catalog(
    v4: dict[str, Any], *, v3: dict[str, Any]
) -> tuple[list[dict[str, Any]], str]:
    profiles = v4["operation_contracts"]["maximum_constraint_scope_profile_catalog"]
    predecessor = v3["operation_contracts"]["maximum_constraint_scope_profile_catalog"]
    _require(type(profiles) is list, "V4 maximum profile catalog must be an array")
    _require(
        type(predecessor) is list and len(profiles) == len(predecessor) == 408,
        "maximum profile catalog count differs from 408",
    )
    expected_kinds = (
        ["OUTER_RESULT_BOUNDARY_FIXTURE"] * 4
        + ["NON_CHECKPOINT_ROOT_FAMILY"] * 4
        + ["CHECKPOINT_ROOT_COORDINATE"] * 400
    )
    ids: list[str] = []
    seen: set[str] = set()
    for position, (profile, old_profile) in enumerate(
        zip(profiles, predecessor, strict=True), 1
    ):
        _validate_exact_keys(
            profile,
            PROFILE_KEYS,
            label=f"V4 maximum profile {position}",
        )
        _require(
            _canonical_bytes(profile) == _canonical_bytes(old_profile),
            f"V4 maximum profile {position} differs byte-for-byte from V3",
        )
        _require(
            type(profile["profile_position"]) is int
            and profile["profile_position"] == position,
            f"V4 maximum profile {position} position differs",
        )
        _require(
            profile["profile_kind"] == expected_kinds[position - 1],
            f"V4 maximum profile {position} kind/order differs",
        )
        payload = {member: profile[member] for member in PROFILE_ID_PAYLOAD_MEMBERS}
        profile_id = profile["maximum_constraint_scope_profile_id"]
        _require(_is_sha256(profile_id), f"V4 maximum profile {position} ID differs")
        _require(
            _semantic_id(MAXIMUM_SCOPE_PROFILE_DOMAIN, payload) == profile_id,
            f"V4 maximum profile {position} semantic ID differs",
        )
        _require(profile_id not in seen, "V4 maximum profile IDs repeat")
        seen.add(profile_id)
        ids.append(profile_id)
    digest = _sha256(_canonical_bytes(ids))
    v3_digest = v3["invariants"][
        "maximum_constraint_scope_profile_ids_canonical_json_sha256"
    ]
    v4_digest = v4["invariants"][
        "maximum_constraint_scope_profile_ids_canonical_json_sha256"
    ]
    _require(
        digest == v3_digest == v4_digest,
        "maximum profile-ID sequence digest differs",
    )
    return profiles, digest


def _derive_maximum_row_universe(
    registry: dict[str, Any], profiles: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], str]:
    descriptors = registry["ordered_external_type_descriptors"]
    _require(
        type(descriptors) is list and len(descriptors) == 52, "descriptor set differs"
    )
    rows: list[dict[str, Any]] = []
    for descriptor in descriptors:
        _require(type(descriptor) is dict, "external descriptor is not an object")
        type_name = descriptor.get("type_name")
        type_form = descriptor.get("type_form")
        _require(
            type(type_name) is str and bool(type_name), "descriptor type name differs"
        )
        if type_form == "RECORD":
            rows.append(
                {
                    "row_position": len(rows) + 1,
                    "row_kind": "INTRINSIC_RECORD",
                    "type_name": type_name,
                    "alternative_name": None,
                    "constraint_scope_profile_id": None,
                }
            )
            continue
        _require(type_form == "TAGGED_UNION", "descriptor type form differs")
        union = descriptor.get("tagged_union_descriptor")
        _require(type(union) is dict, "tagged-union descriptor differs")
        alternatives = union.get("ordered_alternatives")
        _require(type(alternatives) is list, "tagged-union alternatives differ")
        for alternative_position, alternative in enumerate(alternatives, 1):
            _require(type(alternative) is dict, "tagged-union alternative differs")
            _require(
                type(alternative.get("alternative_position")) is int
                and alternative["alternative_position"] == alternative_position,
                "tagged-union alternative order differs",
            )
            alternative_name = alternative.get("alternative_name")
            _require(
                type(alternative_name) is str and bool(alternative_name),
                "tagged-union alternative name differs",
            )
            rows.append(
                {
                    "row_position": len(rows) + 1,
                    "row_kind": "INTRINSIC_UNION_ALTERNATIVE",
                    "type_name": type_name,
                    "alternative_name": alternative_name,
                    "constraint_scope_profile_id": None,
                }
            )
    _require(len(rows) == 66, "intrinsic maximum row count/order differs from 66")
    _require(
        rows[61]["row_kind"] == "INTRINSIC_RECORD"
        and rows[61]["type_name"] == "TargetFieldRegistryV1",
        "intrinsic row 62 authority differs",
    )
    for profile in profiles:
        rows.append(
            {
                "row_position": len(rows) + 1,
                "row_kind": profile["profile_kind"],
                "type_name": profile["measured_type_name"],
                "alternative_name": None,
                "constraint_scope_profile_id": profile[
                    "maximum_constraint_scope_profile_id"
                ],
            }
        )
    _require(
        len(rows) == 474
        and [row["row_position"] for row in rows] == list(range(1, 475)),
        "complete 474-row universe/order differs",
    )
    row_keys = [
        (
            row["row_kind"],
            row["type_name"],
            row["alternative_name"],
            row["constraint_scope_profile_id"],
        )
        for row in rows
    ]
    _require(len(set(row_keys)) == 474, "maximum row universe contains duplicates")
    return rows, _sha256(_canonical_bytes(rows))


def _validate_v3_predecessor(v3: Any, *, registry: dict[str, Any]) -> dict[str, Any]:
    predecessor = _validate_exact_keys(
        v3, INVENTORY_ROOT_KEYS, label="accepted V3 root"
    )
    _require(
        predecessor["schema_version"] == V3_SCHEMA_VERSION,
        "accepted V3 schema version differs",
    )
    _validate_inventory_identity(
        predecessor,
        expected=V3_INVENTORY_ID,
        label="accepted V3 inventory",
    )
    expected_v3_documents = [
        _document_record(*NORMATIVE_DOCUMENTS[position]) for position in (0, 1, 2, 4)
    ]
    _require(
        predecessor["normative_document_inputs"] == expected_v3_documents,
        "accepted V3 normative input mirror differs",
    )
    invariants = predecessor["invariants"]
    _require(type(invariants) is dict, "accepted V3 invariants differ")
    _require(
        invariants.get("inventory_schema_version") == V3_SCHEMA_VERSION,
        "accepted V3 invariant schema version differs",
    )
    _require(
        type(invariants.get("counts")) is dict
        and type(invariants["counts"].get("normative_document_input_count")) is int
        and invariants["counts"]["normative_document_input_count"] == 4,
        "accepted V3 normative count invariant differs",
    )
    _require(
        COMPACT_CORRECTION_ROLE
        not in invariants.get("normative_document_sha256_by_role", {}),
        "accepted V3 unexpectedly contains the compact correction",
    )
    _require(
        "compact_maximum_proof_v2_contract" not in invariants,
        "accepted V3 unexpectedly contains the V2 compact contract",
    )
    _require(
        _canonical_bytes(predecessor["external_schema_registry_v2"])
        == _canonical_bytes(registry),
        "accepted V3 embedded structural registry differs",
    )
    _validate_target_field_registry(
        predecessor["target_field_registry"],
        label="accepted V3 target-field registry",
    )
    return predecessor


def _validate_v4_candidate(
    candidate: Any,
    *,
    candidate_raw: bytes,
    predecessor: dict[str, Any],
    expected: dict[str, Any],
    registry: dict[str, Any],
) -> tuple[str, str, str]:
    inventory = _validate_exact_keys(candidate, INVENTORY_ROOT_KEYS, label="V4 root")
    _require(inventory["schema_version"] == V4_SCHEMA_VERSION, "V4 schema differs")
    _validate_document_records(inventory["normative_document_inputs"])
    _require(
        type(inventory["invariants"]) is dict,
        "V4 invariants must be an exact object",
    )
    _validate_compact_contract(
        inventory["invariants"].get("compact_maximum_proof_v2_contract")
    )
    _require(
        type(inventory["invariants"].get("counts")) is dict
        and type(
            inventory["invariants"]["counts"].get("normative_document_input_count")
        )
        is int
        and inventory["invariants"]["counts"]["normative_document_input_count"] == 5,
        "V4 normative input count invariant differs",
    )
    expected_invariant_keys = frozenset(predecessor["invariants"]) | {
        "compact_maximum_proof_v2_contract"
    }
    _validate_exact_keys(
        inventory["invariants"], expected_invariant_keys, label="V4 invariants"
    )
    for member in PROTECTED_ROOT_MEMBERS:
        _require(
            _canonical_bytes(inventory[member])
            == _canonical_bytes(predecessor[member]),
            f"protected V4 root member drifted: {member}",
        )
    _require(
        _canonical_bytes(inventory["external_schema_registry_v2"])
        == _canonical_bytes(registry),
        "V4 embedded structural registry differs",
    )
    _validate_target_field_registry(
        inventory["target_field_registry"], label="V4 target-field registry"
    )
    profile_catalog, profile_digest = _validate_profile_catalog(
        inventory, v3=predecessor
    )
    rows, row_digest = _derive_maximum_row_universe(registry, profile_catalog)
    _require(
        inventory["invariants"]["compact_maximum_proof_v2_contract"][
            "maximum_publication_row_count"
        ]
        == len(rows),
        "compact contract does not bind all 474 rows",
    )
    _require(
        inventory["invariants"]["compact_maximum_proof_v2_contract"][
            "verifier_owned_scope_case_count"
        ]
        == len(rows) + 1,
        "compact contract does not bind 474 maxima plus local minimality",
    )
    identity = _validate_inventory_identity(
        inventory,
        expected=V4_INVENTORY_ID,
        label="accepted V4 inventory",
    )
    _require(
        inventory["invariants"] == expected["invariants"],
        "V4 invariant patch includes unauthorized drift",
    )
    _require(
        candidate_raw == _pretty_bytes(expected),
        "candidate V4 differs from the exact V3-to-V4 authorized patch",
    )
    _require(identity == expected["inventory_sha256"], "V4 root identity differs")
    _require(
        row_digest == MAXIMUM_ROW_UNIVERSE_SHA256,
        "maximum row-universe digest differs from its acceptance pin",
    )
    return identity, profile_digest, row_digest


def validate_inventory_v4_file(
    *, repository_root: Path, inventory_path: Path
) -> dict[str, Any]:
    """Validate one candidate V4 inventory and return deterministic evidence."""

    root = repository_root.resolve(strict=True)
    _require(root.is_dir(), "repository root is not a directory")
    candidate_path = _absolute_below_repository(
        inventory_path,
        repository_root=root,
        label="candidate V4 inventory",
    )
    specs = _input_specs(repository_root=root, inventory_path=candidate_path)
    snapshots = _read_all(specs)
    _validate_physical_pins(snapshots)

    v3_raw = snapshots["accepted V3 inventory"].raw
    registry_raw = snapshots["standalone structural registry"].raw
    candidate_raw = snapshots["candidate V4 inventory"].raw
    v3_value = _decode_pretty_json(v3_raw, label="accepted V3 inventory")
    registry_value = _decode_pretty_json(
        registry_raw, label="standalone structural registry"
    )
    candidate_value = _decode_pretty_json(candidate_raw, label="candidate V4 inventory")
    registry = _validate_structural_registry(
        registry_value,
        raw=registry_raw,
        label="standalone structural registry",
    )
    predecessor = _validate_v3_predecessor(v3_value, registry=registry)
    expected = _expected_v4_from_v3(predecessor)
    identity, profile_digest, row_digest = _validate_v4_candidate(
        candidate_value,
        candidate_raw=candidate_raw,
        predecessor=predecessor,
        expected=expected,
        registry=registry,
    )
    _revalidate_snapshots(specs, snapshots)
    return {
        "component_status": "V4_INVENTORY_NARROW_MIGRATION_VALIDATED",
        "external_schema_registry_id": STRUCTURAL_REGISTRY_ID,
        "inventory_octets": len(candidate_raw),
        "inventory_raw_sha256": _sha256(candidate_raw),
        "inventory_sha256": identity,
        "maximum_constraint_scope_profile_count": 408,
        "maximum_constraint_scope_profile_ids_canonical_json_sha256": (profile_digest),
        "maximum_publication_row_count": 474,
        "maximum_row_universe_canonical_json_sha256": row_digest,
        "normative_document_input_count": 5,
        "predecessor_inventory_octets": V3_INVENTORY_OCTETS,
        "predecessor_inventory_raw_sha256": V3_INVENTORY_RAW_SHA256,
        "predecessor_inventory_sha256": V3_INVENTORY_ID,
        "schema_version": V4_SCHEMA_VERSION,
        "verifier_owned_scope_case_count": 475,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--inventory", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        repository_root = arguments.repository_root
        inventory_path = (
            arguments.inventory
            if arguments.inventory is not None
            else Path(V4_INVENTORY_RELATIVE_PATH)
        )
        report = validate_inventory_v4_file(
            repository_root=repository_root,
            inventory_path=inventory_path,
        )
    except (
        AssertionError,
        AttributeError,
        IndexError,
        InventoryV4ValidationError,
        KeyError,
        OSError,
        RuntimeError,
        TypeError,
        UnicodeError,
        ValueError,
    ) as exc:
        message = str(exc) or type(exc).__name__
        print(f"RAW_V8_STEP2_INVENTORY_V4_INVALID: {message}", file=sys.stderr)
        return 2
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

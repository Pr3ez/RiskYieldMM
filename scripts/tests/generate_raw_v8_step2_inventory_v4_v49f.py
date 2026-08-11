#!/usr/bin/env python3
"""Generate or check the narrowly migrated Raw-V8 Step-2 V4 inventory.

This is an independent, standard-library-only V3-to-V4 migrator.  It does not
reconstruct the large Step-2 inventory from implementation code.  Instead it
starts from the byte-pinned accepted V3 golden, verifies every authority input,
applies the exact accepted compact-maximum-proof amendment, and proves that no
other recursively reachable value changed.

Write mode is an offline, single-writer publication operation.  Directory-fd
and identity checks reject observed namespace drift, but they are not a lock
against an uncooperative process with concurrent mutation rights in the same
repository directories.  Such a workspace is not admissible for publication.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import secrets
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final


class InventoryMigrationError(ValueError):
    """Raised when the exact V3-to-V4 inventory migration cannot be proved."""


V3_SCHEMA_VERSION: Final = "riskyieldmm.raw_v8_step2_inventory.v3"
V4_SCHEMA_VERSION: Final = "riskyieldmm.raw_v8_step2_inventory.v4"
V3_INVENTORY_PATH: Final = "tests/raw_v8_step2_inventory_v49f.json"
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

PARENT_PROTOCOL_PATH: Final = (
    "docs/research/v4_9f_a2_marker_operation_target_v8_protocol_freeze_2026-07-22.md"
)
STEP2_V2_FREEZE_PATH: Final = (
    "docs/research/v4_9f_a2_raw_v8_step2_v2_contract_freeze_2026-07-26.md"
)
EXTERNAL_CORRECTION_PATH: Final = (
    "docs/research/v4_9f_a2_raw_v8_step2_external_schema_v2_correction_2026-07-28.md"
)
COMPACT_CORRECTION_PATH: Final = "docs/research/v4_9f_a2_raw_v8_step2_compact_maximum_proof_v2_correction_2026-08-02.md"
STEP3_CORRECTION_PATH: Final = (
    "docs/research/v4_9f_a2_raw_v8_step3_target_and_lifecycle_correction_2026-07-26.md"
)
STRUCTURAL_REGISTRY_PATH: Final = (
    "scripts/tests/raw_v8_step2_external_schema_v2_structural_registry_v49f.json"
)
DEFAULT_OUTPUT: Final = "tests/raw_v8_step2_inventory_v4_v49f.json"

STRUCTURAL_REGISTRY_OCTETS: Final = 1_469_663
STRUCTURAL_REGISTRY_RAW_SHA256: Final = (
    "9160297ff316c5931737c92f8b359f0a1e2ec22f0aa996ef3b09cf830dc96bf3"
)
STRUCTURAL_REGISTRY_ID: Final = (
    "5dc95a3e99c5646e912b6a7e9c3970cf2489d560ea890b0a19d38af4c51c2140"
)
MAXIMUM_SCOPE_PROFILE_COUNT: Final = 408
MAXIMUM_SCOPE_PROFILE_IDS_SHA256: Final = (
    "b50b97b682d5707062867f2789a204e0488bdc95be7977f9ddc408959d1c9e0e"
)
MAXIMUM_JSON_NESTING_DEPTH: Final = 128

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

PREDECESSOR_NORMATIVE_DOCUMENTS: Final = (
    (
        "PARENT_MARKER_OPERATION_TARGET_PROTOCOL",
        PARENT_PROTOCOL_PATH,
        212_471,
        "15b42d32afe5fdff74890b2c18f735ff761244548729142c4ff2b1034fee2388",
    ),
    (
        "STEP2_V2_CONTRACT_FREEZE",
        STEP2_V2_FREEZE_PATH,
        34_591,
        "355548cb3ef323ab45b0289be9891ab578b75d0147639ab37c9f3e5ff251aa1c",
    ),
    (
        "STEP2_EXTERNAL_SCHEMA_V2_CORRECTION",
        EXTERNAL_CORRECTION_PATH,
        217_135,
        "29ec141e53adeb1c0afd51f205f5b57eb784b8859b5ba40958299abd1b713b55",
    ),
    (
        "STEP3_TARGET_AND_LIFECYCLE_CORRECTION",
        STEP3_CORRECTION_PATH,
        435_478,
        "635952095b0b20089d5ec2c13104255ebeeff11535c8f94131a4983a1a9fec0a",
    ),
)
COMPACT_CORRECTION_ROLE: Final = "STEP2_COMPACT_MAXIMUM_PROOF_V2_CORRECTION"
COMPACT_CORRECTION_OCTETS: Final = 49_849
COMPACT_CORRECTION_RAW_SHA256: Final = (
    "f4d35405ef1e66a8ba1c59027fc2097a56563d50408eb72cc48895d2127b71b4"
)
SUCCESSOR_NORMATIVE_DOCUMENTS: Final = (
    *PREDECESSOR_NORMATIVE_DOCUMENTS[:3],
    (
        COMPACT_CORRECTION_ROLE,
        COMPACT_CORRECTION_PATH,
        COMPACT_CORRECTION_OCTETS,
        COMPACT_CORRECTION_RAW_SHA256,
    ),
    PREDECESSOR_NORMATIVE_DOCUMENTS[3],
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


@dataclass(frozen=True)
class _SourceSpec:
    label: str
    relative_path: str
    exact_octets: int
    raw_sha256: str
    json_input: bool = False


@dataclass(frozen=True)
class _SourceSnapshot:
    spec: _SourceSpec
    raw: bytes
    identity: tuple[int, int, int, int, int, int, int]
    parent_identity: tuple[int, int, int]


PINNED_SOURCE_SPECS: Final = (
    _SourceSpec(
        "accepted V3 inventory",
        V3_INVENTORY_PATH,
        V3_INVENTORY_OCTETS,
        V3_INVENTORY_RAW_SHA256,
        True,
    ),
    *(
        _SourceSpec(f"normative document {role}", path, octets, digest)
        for role, path, octets, digest in SUCCESSOR_NORMATIVE_DOCUMENTS
    ),
    _SourceSpec(
        "external-schema V2 structural registry",
        STRUCTURAL_REGISTRY_PATH,
        STRUCTURAL_REGISTRY_OCTETS,
        STRUCTURAL_REGISTRY_RAW_SHA256,
        True,
    ),
)
PROTECTED_INPUT_PATHS: Final = frozenset(
    item.relative_path for item in PINNED_SOURCE_SPECS
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise InventoryMigrationError(message)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


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


def _repository_relative_parts(relative_path: str) -> tuple[str, ...]:
    _require(type(relative_path) is str, "repository path is not exact text")
    path = Path(relative_path)
    _require(
        not path.is_absolute()
        and bool(path.parts)
        and relative_path == path.as_posix()
        and all(part not in {"", ".", ".."} for part in path.parts),
        f"repository path is not an exact relative POSIX path: {relative_path}",
    )
    return path.parts


def _open_repository_directory_fd(
    repository_root: Path,
    relative_parts: tuple[str, ...],
    *,
    label: str,
) -> int:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(repository_root, flags)
        _require(
            stat.S_ISDIR(os.fstat(descriptor).st_mode),
            "repository root is not a directory",
        )
        for part in relative_parts:
            child = os.open(part, flags, dir_fd=descriptor)
            try:
                _require(
                    stat.S_ISDIR(os.fstat(child).st_mode),
                    f"{label} parent component is not a directory",
                )
            except Exception:
                os.close(child)
                raise
            os.close(descriptor)
            descriptor = child
        return descriptor
    except (InventoryMigrationError, OSError) as exc:
        if descriptor is not None:
            os.close(descriptor)
        if isinstance(exc, InventoryMigrationError):
            raise
        raise InventoryMigrationError(f"cannot securely open {label} parent") from exc


def _directory_identity(descriptor: int) -> tuple[int, int, int]:
    metadata = os.fstat(descriptor)
    _require(stat.S_ISDIR(metadata.st_mode), "repository path is not a directory")
    return (metadata.st_dev, metadata.st_ino, metadata.st_mode)


def _current_directory_identity(
    repository_root: Path,
    relative_parts: tuple[str, ...],
    *,
    label: str,
) -> tuple[int, int, int]:
    descriptor = _open_repository_directory_fd(
        repository_root,
        relative_parts,
        label=label,
    )
    try:
        return _directory_identity(descriptor)
    finally:
        os.close(descriptor)


def _file_identity(
    metadata: os.stat_result,
) -> tuple[int, int, int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _bounded_repository_snapshot(
    repository_root: Path,
    spec: _SourceSpec,
) -> _SourceSnapshot:
    _require(
        type(spec.exact_octets) is int and spec.exact_octets > 0,
        f"{spec.label} byte bound is invalid",
    )
    parts = _repository_relative_parts(spec.relative_path)
    parent_descriptor = _open_repository_directory_fd(
        repository_root,
        parts[:-1],
        label=spec.label,
    )
    parent_identity = _directory_identity(parent_descriptor)
    flags = os.O_RDONLY | os.O_NONBLOCK
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        try:
            descriptor = os.open(parts[-1], flags, dir_fd=parent_descriptor)
        except OSError as exc:
            raise InventoryMigrationError(
                f"cannot securely open {spec.label}: {spec.relative_path}"
            ) from exc
        try:
            before = os.fstat(descriptor)
            _require(
                stat.S_ISREG(before.st_mode),
                f"{spec.label} is not a regular file: {spec.relative_path}",
            )
            _require(
                before.st_nlink == 1,
                f"{spec.label} is not single-link: {spec.relative_path}",
            )
            _require(
                before.st_size == spec.exact_octets,
                f"{spec.label} byte count differs: {spec.relative_path}",
            )
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = os.read(descriptor, 65_536)
                if not chunk:
                    break
                total += len(chunk)
                _require(
                    total <= spec.exact_octets,
                    f"{spec.label} exceeds its byte bound: {spec.relative_path}",
                )
                chunks.append(chunk)
            after = os.fstat(descriptor)
            _require(
                _file_identity(before) == _file_identity(after),
                f"{spec.label} changed during read: {spec.relative_path}",
            )
        finally:
            os.close(descriptor)

        raw = b"".join(chunks)
        _require(
            len(raw) == spec.exact_octets,
            f"{spec.label} was truncated during read: {spec.relative_path}",
        )
        _require(
            _sha256_bytes(raw) == spec.raw_sha256,
            f"{spec.label} SHA-256 differs: {spec.relative_path}",
        )
        try:
            path_metadata = os.stat(
                parts[-1],
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except OSError as exc:
            raise InventoryMigrationError(
                f"{spec.label} disappeared after read: {spec.relative_path}"
            ) from exc
        _require(
            _file_identity(path_metadata) == _file_identity(after),
            f"{spec.label} path identity changed: {spec.relative_path}",
        )
        _require(
            _current_directory_identity(
                repository_root,
                parts[:-1],
                label=spec.label,
            )
            == parent_identity,
            f"{spec.label} parent identity changed: {spec.relative_path}",
        )
        return _SourceSnapshot(
            spec=spec,
            raw=raw,
            identity=_file_identity(after),
            parent_identity=parent_identity,
        )
    finally:
        os.close(parent_descriptor)


def _bounded_repository_read(
    repository_root: Path,
    relative_path: str,
    *,
    exact_octets: int,
    expected_sha256: str,
    label: str = "repository input",
) -> bytes:
    """Read one exact, single-link repository file through the secure path walk."""

    return _bounded_repository_snapshot(
        repository_root,
        _SourceSpec(label, relative_path, exact_octets, expected_sha256),
    ).raw


def _snapshot_all_sources(repository_root: Path) -> dict[str, _SourceSnapshot]:
    snapshots: dict[str, _SourceSnapshot] = {}
    inode_owner: dict[tuple[int, int], str] = {}
    for spec in PINNED_SOURCE_SPECS:
        _require(
            spec.relative_path not in snapshots,
            f"duplicate pinned input path: {spec.relative_path}",
        )
        snapshot = _bounded_repository_snapshot(repository_root, spec)
        inode = snapshot.identity[:2]
        _require(
            inode not in inode_owner,
            f"cross-input inode alias: {spec.relative_path} and {inode_owner.get(inode)}",
        )
        inode_owner[inode] = spec.relative_path
        snapshots[spec.relative_path] = snapshot
    return snapshots


def _assert_snapshot_sets_equal(
    first: dict[str, _SourceSnapshot],
    second: dict[str, _SourceSnapshot],
) -> None:
    _require(
        tuple(first) == tuple(second),
        "pinned input path order changed between complete snapshots",
    )
    for path in first:
        left = first[path]
        right = second[path]
        _require(
            left.spec == right.spec
            and left.identity == right.identity
            and left.parent_identity == right.parent_identity
            and left.raw == right.raw,
            f"pinned input changed between complete snapshots: {path}",
        )


def _load_repeatable_source_snapshots(
    repository_root: Path,
) -> dict[str, _SourceSnapshot]:
    first = _snapshot_all_sources(repository_root)
    second = _snapshot_all_sources(repository_root)
    _assert_snapshot_sets_equal(first, second)
    return second


def _reject_json_constant(value: str) -> Any:
    raise InventoryMigrationError(f"controlled JSON contains non-finite value: {value}")


def _reject_json_float(value: str) -> Any:
    raise InventoryMigrationError(f"controlled JSON contains a float: {value}")


def _parse_json_integer(value: str) -> int:
    _require(len(value.lstrip("-")) <= 128, "controlled JSON integer is too long")
    return int(value, 10)


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InventoryMigrationError(
                f"controlled JSON contains duplicate key: {key}"
            )
        result[key] = value
    return result


def _scan_json_nesting(text: str, *, maximum_depth: int) -> None:
    stack: list[str] = []
    closing = {"}": "{", "]": "["}
    in_string = False
    escaped = False
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
                    "controlled JSON contains an unescaped control character",
                )
            continue
        if character == '"':
            in_string = True
        elif character in "[{":
            stack.append(character)
            _require(
                len(stack) <= maximum_depth,
                "controlled JSON nesting exceeds its bound",
            )
        elif character in "]}":
            _require(
                bool(stack) and stack[-1] == closing[character],
                "controlled JSON delimiters are unbalanced",
            )
            stack.pop()
    _require(not in_string and not escaped, "controlled JSON string is unterminated")
    _require(not stack, "controlled JSON containers are unterminated")


def _validate_json_scalars(value: Any) -> None:
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
                "controlled JSON contains a surrogate code point",
            )
        else:
            _require(
                current is None or type(current) in {bool, int},
                "controlled JSON contains an unsupported scalar type",
            )


def _parse_strict_canonical_json(raw: bytes, *, label: str) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InventoryMigrationError(f"{label} is not UTF-8") from exc
    _scan_json_nesting(text, maximum_depth=MAXIMUM_JSON_NESTING_DEPTH)
    try:
        value = json.loads(
            text,
            object_pairs_hook=_strict_json_object,
            parse_constant=_reject_json_constant,
            parse_float=_reject_json_float,
            parse_int=_parse_json_integer,
        )
    except InventoryMigrationError:
        raise
    except (ValueError, TypeError, RecursionError) as exc:
        raise InventoryMigrationError(f"{label} is not strict JSON") from exc
    _require(type(value) is dict, f"{label} root is not an object")
    _validate_json_scalars(value)
    _require(
        _pretty_bytes(value) == raw,
        f"{label} is not exact sorted canonical pretty JSON",
    )
    return value


def _assert_equal_recursive(left: Any, right: Any, *, path: str) -> None:
    _require(type(left) is type(right), f"recursive type drift at {path}")
    if type(left) is dict:
        _require(set(left) == set(right), f"recursive object-key drift at {path}")
        for key in sorted(left):
            _assert_equal_recursive(left[key], right[key], path=f"{path}.{key}")
    elif type(left) is list:
        _require(len(left) == len(right), f"recursive list-length drift at {path}")
        for index, (left_item, right_item) in enumerate(zip(left, right, strict=True)):
            _assert_equal_recursive(
                left_item,
                right_item,
                path=f"{path}[{index}]",
            )
    else:
        _require(left == right, f"recursive value drift at {path}")


def _normative_entry(
    role: str,
    path: str,
    octets: int,
    digest: str,
) -> dict[str, Any]:
    return {
        "document_role": role,
        "repository_relative_path": path,
        "raw_octet_count": octets,
        "raw_sha256": digest,
    }


def _validate_predecessor(
    predecessor: dict[str, Any],
    structural_registry: dict[str, Any],
) -> None:
    _require(
        frozenset(predecessor) == INVENTORY_ROOT_KEYS,
        "accepted V3 inventory root keys differ",
    )
    _require(
        predecessor.get("schema_version") == V3_SCHEMA_VERSION, "V3 schema differs"
    )
    _require(
        predecessor.get("inventory_sha256") == V3_INVENTORY_ID,
        "accepted V3 inventory identity differs",
    )
    without_identity = dict(predecessor)
    without_identity.pop("inventory_sha256")
    _require(
        _sha256_bytes(_canonical_bytes(without_identity)) == V3_INVENTORY_ID,
        "accepted V3 root identity preimage differs",
    )

    expected_documents = [
        _normative_entry(*document) for document in PREDECESSOR_NORMATIVE_DOCUMENTS
    ]
    _assert_equal_recursive(
        predecessor.get("normative_document_inputs"),
        expected_documents,
        path="$.normative_document_inputs",
    )
    invariants = predecessor.get("invariants")
    _require(type(invariants) is dict, "V3 invariants are not an object")
    _require(
        invariants.get("inventory_schema_version") == V3_SCHEMA_VERSION,
        "V3 invariant schema mirror differs",
    )
    counts = invariants.get("counts")
    _require(type(counts) is dict, "V3 counts are not an object")
    _require(
        counts.get("normative_document_input_count") == 4,
        "V3 normative input count differs",
    )
    expected_hashes = {
        role: digest for role, _path, _octets, digest in PREDECESSOR_NORMATIVE_DOCUMENTS
    }
    _assert_equal_recursive(
        invariants.get("normative_document_sha256_by_role"),
        expected_hashes,
        path="$.invariants.normative_document_sha256_by_role",
    )
    _require(
        "compact_maximum_proof_v2_contract" not in invariants,
        "V3 already contains the V4 compact-maximum-proof contract",
    )

    embedded_registry = predecessor.get("external_schema_registry_v2")
    _require(type(embedded_registry) is dict, "embedded structural registry is absent")
    _assert_equal_recursive(
        embedded_registry,
        structural_registry,
        path="$.external_schema_registry_v2",
    )
    _require(
        embedded_registry.get("external_schema_registry_id") == STRUCTURAL_REGISTRY_ID,
        "embedded structural registry identity differs",
    )

    operation_contracts = predecessor.get("operation_contracts")
    _require(type(operation_contracts) is dict, "V3 operation contracts are absent")
    profiles = operation_contracts.get("maximum_constraint_scope_profile_catalog")
    _require(type(profiles) is list, "V3 maximum-scope profile catalog is absent")
    _require(
        len(profiles) == MAXIMUM_SCOPE_PROFILE_COUNT,
        "V3 maximum-scope profile count differs",
    )
    profile_ids: list[str] = []
    for position, profile in enumerate(profiles):
        _require(type(profile) is dict, f"V3 profile {position} is not an object")
        profile_id = profile.get("maximum_constraint_scope_profile_id")
        _require(
            type(profile_id) is str
            and len(profile_id) == 64
            and all(character in "0123456789abcdef" for character in profile_id),
            f"V3 profile {position} identity differs",
        )
        profile_ids.append(profile_id)
    _require(len(set(profile_ids)) == len(profile_ids), "V3 profile IDs are not unique")
    profile_digest = _sha256_bytes(_canonical_bytes(profile_ids))
    _require(
        profile_digest == MAXIMUM_SCOPE_PROFILE_IDS_SHA256
        and invariants.get("maximum_constraint_scope_profile_ids_canonical_json_sha256")
        == profile_digest,
        "V3 ordered maximum-scope profile-ID digest differs",
    )
    _require(
        counts.get("maximum_constraint_scope_profile_count")
        == MAXIMUM_SCOPE_PROFILE_COUNT,
        "V3 maximum-scope profile-count mirror differs",
    )


def _recompute_inventory_identity(inventory: dict[str, Any]) -> str:
    without_identity = dict(inventory)
    without_identity.pop("inventory_sha256", None)
    return _sha256_bytes(_canonical_bytes(without_identity))


def _prove_allowed_delta(
    predecessor: dict[str, Any],
    successor: dict[str, Any],
) -> None:
    _require(
        frozenset(successor) == INVENTORY_ROOT_KEYS,
        "V4 inventory root keys differ",
    )
    _require(successor.get("schema_version") == V4_SCHEMA_VERSION, "V4 schema differs")
    expected_documents = [
        _normative_entry(*document) for document in SUCCESSOR_NORMATIVE_DOCUMENTS
    ]
    _assert_equal_recursive(
        successor.get("normative_document_inputs"),
        expected_documents,
        path="$.normative_document_inputs",
    )

    predecessor_invariants = predecessor["invariants"]
    successor_invariants = successor.get("invariants")
    _require(type(successor_invariants) is dict, "V4 invariants are not an object")
    _require(
        set(successor_invariants)
        == set(predecessor_invariants) | {"compact_maximum_proof_v2_contract"},
        "V4 invariant key set exceeds the authorized amendment",
    )
    _require(
        successor_invariants.get("inventory_schema_version") == V4_SCHEMA_VERSION,
        "V4 invariant schema mirror differs",
    )
    successor_counts = successor_invariants.get("counts")
    predecessor_counts = predecessor_invariants["counts"]
    _require(type(successor_counts) is dict, "V4 counts are not an object")
    _require(set(successor_counts) == set(predecessor_counts), "V4 count keys drifted")
    _require(
        successor_counts.get("normative_document_input_count") == 5,
        "V4 normative input count differs",
    )
    expected_hashes = {
        role: digest for role, _path, _octets, digest in SUCCESSOR_NORMATIVE_DOCUMENTS
    }
    _assert_equal_recursive(
        successor_invariants.get("normative_document_sha256_by_role"),
        expected_hashes,
        path="$.invariants.normative_document_sha256_by_role",
    )
    _assert_equal_recursive(
        successor_invariants.get("compact_maximum_proof_v2_contract"),
        COMPACT_MAXIMUM_PROOF_V2_CONTRACT,
        path="$.invariants.compact_maximum_proof_v2_contract",
    )
    _require(
        successor.get("inventory_sha256") == _recompute_inventory_identity(successor),
        "V4 root identity does not commit the exact root without itself",
    )

    # Reverse exactly the authorized edits and require full recursive equality.
    # This is deliberately stronger than a shallow top-level equality test.
    reverted = copy.deepcopy(successor)
    reverted["schema_version"] = predecessor["schema_version"]
    reverted["normative_document_inputs"] = copy.deepcopy(
        predecessor["normative_document_inputs"]
    )
    reverted_invariants = reverted["invariants"]
    reverted_invariants["inventory_schema_version"] = predecessor_invariants[
        "inventory_schema_version"
    ]
    reverted_invariants["counts"]["normative_document_input_count"] = (
        predecessor_counts["normative_document_input_count"]
    )
    reverted_invariants["normative_document_sha256_by_role"] = copy.deepcopy(
        predecessor_invariants["normative_document_sha256_by_role"]
    )
    reverted_invariants.pop("compact_maximum_proof_v2_contract")
    reverted["inventory_sha256"] = predecessor["inventory_sha256"]
    _assert_equal_recursive(predecessor, reverted, path="$")

    # Make the two highest-risk frozen subtrees explicit in the proof report.
    _assert_equal_recursive(
        predecessor["external_schema_registry_v2"],
        successor["external_schema_registry_v2"],
        path="$.external_schema_registry_v2",
    )
    _assert_equal_recursive(
        predecessor["target_field_registry"],
        successor["target_field_registry"],
        path="$.target_field_registry",
    )
    predecessor_profiles = predecessor["operation_contracts"][
        "maximum_constraint_scope_profile_catalog"
    ]
    successor_profiles = successor["operation_contracts"][
        "maximum_constraint_scope_profile_catalog"
    ]
    _require(
        len(successor_profiles) == MAXIMUM_SCOPE_PROFILE_COUNT,
        "V4 maximum-scope profile count differs",
    )
    _assert_equal_recursive(
        predecessor_profiles,
        successor_profiles,
        path="$.operation_contracts.maximum_constraint_scope_profile_catalog",
    )


def _migrate_inventory(predecessor: dict[str, Any]) -> dict[str, Any]:
    successor = copy.deepcopy(predecessor)
    successor["schema_version"] = V4_SCHEMA_VERSION
    successor["normative_document_inputs"].insert(
        3,
        _normative_entry(*SUCCESSOR_NORMATIVE_DOCUMENTS[3]),
    )
    invariants = successor["invariants"]
    invariants["inventory_schema_version"] = V4_SCHEMA_VERSION
    invariants["counts"]["normative_document_input_count"] = 5
    invariants["normative_document_sha256_by_role"][COMPACT_CORRECTION_ROLE] = (
        COMPACT_CORRECTION_RAW_SHA256
    )
    invariants["compact_maximum_proof_v2_contract"] = copy.deepcopy(
        COMPACT_MAXIMUM_PROOF_V2_CONTRACT
    )
    successor["inventory_sha256"] = _recompute_inventory_identity(successor)
    _prove_allowed_delta(predecessor, successor)
    return successor


def _build_v4_inventory(
    snapshots: dict[str, _SourceSnapshot],
) -> dict[str, Any]:
    for _role, path, _octets, _digest in SUCCESSOR_NORMATIVE_DOCUMENTS:
        raw = snapshots[path].raw
        _require(bool(raw), f"normative document is empty: {path}")
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise InventoryMigrationError(
                f"normative document is not UTF-8: {path}"
            ) from exc

    predecessor = _parse_strict_canonical_json(
        snapshots[V3_INVENTORY_PATH].raw,
        label="accepted V3 inventory",
    )
    structural_registry = _parse_strict_canonical_json(
        snapshots[STRUCTURAL_REGISTRY_PATH].raw,
        label="external-schema V2 structural registry",
    )
    _validate_predecessor(predecessor, structural_registry)
    return _migrate_inventory(predecessor)


def _enforce_v4_physical_freeze(
    inventory: dict[str, Any],
    rendered: bytes,
) -> None:
    _require(
        inventory.get("inventory_sha256") == V4_INVENTORY_ID,
        "derived V4 inventory identity differs from the accepted freeze",
    )
    _require(
        len(rendered) == V4_INVENTORY_OCTETS,
        "derived V4 inventory byte count differs from the accepted freeze",
    )
    _require(
        _sha256_bytes(rendered) == V4_INVENTORY_RAW_SHA256,
        "derived V4 inventory raw SHA-256 differs from the accepted freeze",
    )


def _output_entry_identity(
    parent_descriptor: int,
    leaf_name: str,
) -> tuple[int, int, int, int, int, int, int] | None:
    try:
        metadata = os.stat(
            leaf_name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return None
    _require(stat.S_ISREG(metadata.st_mode), "existing output is not a regular file")
    _require(metadata.st_nlink == 1, "existing output is not single-link")
    return _file_identity(metadata)


def _protected_inodes(
    snapshots: dict[str, _SourceSnapshot],
) -> frozenset[tuple[int, int]]:
    return frozenset(snapshot.identity[:2] for snapshot in snapshots.values())


def _resolve_output(
    repository_root: Path,
    output_argument: Path,
    *,
    protected_inodes: frozenset[tuple[int, int]],
) -> tuple[Path, str]:
    _require(
        not output_argument.is_absolute(), "output path must be repository-relative"
    )
    relative_path = output_argument.as_posix()
    parts = _repository_relative_parts(relative_path)
    _require(
        relative_path == DEFAULT_OUTPUT
        or (len(parts) >= 2 and parts[0] == "test_output"),
        "output is outside the canonical or test_output publication roots",
    )
    _require(
        relative_path not in PROTECTED_INPUT_PATHS,
        "output path would overwrite a protected input",
    )
    parent_descriptor = _open_repository_directory_fd(
        repository_root,
        parts[:-1],
        label="repository output",
    )
    try:
        identity = _output_entry_identity(parent_descriptor, parts[-1])
        if identity is not None:
            _require(
                identity[:2] not in protected_inodes,
                "existing output aliases a protected input inode",
            )
    finally:
        os.close(parent_descriptor)
    return repository_root.joinpath(*parts), relative_path


def _atomic_write_repository_output(
    repository_root: Path,
    relative_path: str,
    rendered: bytes,
    *,
    protected_inodes: frozenset[tuple[int, int]],
) -> None:
    parts = _repository_relative_parts(relative_path)
    parent_descriptor = _open_repository_directory_fd(
        repository_root,
        parts[:-1],
        label="repository output",
    )
    parent_identity = _directory_identity(parent_descriptor)
    leaf_name = parts[-1]
    temporary_name: str | None = None
    temporary_descriptor: int | None = None
    temporary_inode: tuple[int, int] | None = None
    renamed = False
    try:
        original_identity = _output_entry_identity(parent_descriptor, leaf_name)
        if original_identity is not None:
            _require(
                original_identity[:2] not in protected_inodes,
                "existing output aliases a protected input inode",
            )
        temporary_flags = os.O_RDWR | os.O_NONBLOCK | os.O_CREAT | os.O_EXCL
        temporary_flags |= getattr(os, "O_CLOEXEC", 0)
        temporary_flags |= getattr(os, "O_NOFOLLOW", 0)
        for _ in range(32):
            candidate = f".{leaf_name}.tmp.{os.getpid()}.{secrets.token_hex(16)}"
            try:
                temporary_descriptor = os.open(
                    candidate,
                    temporary_flags,
                    0o600,
                    dir_fd=parent_descriptor,
                )
            except FileExistsError:
                continue
            temporary_name = candidate
            break
        _require(
            temporary_descriptor is not None and temporary_name is not None,
            "cannot allocate a unique atomic output temporary",
        )
        offset = 0
        while offset < len(rendered):
            written = os.write(temporary_descriptor, rendered[offset:])
            _require(written > 0, "atomic output write made no progress")
            offset += written
        os.fchmod(temporary_descriptor, 0o644)
        os.fsync(temporary_descriptor)
        temporary_metadata = os.fstat(temporary_descriptor)
        _require(
            stat.S_ISREG(temporary_metadata.st_mode)
            and temporary_metadata.st_nlink == 1
            and temporary_metadata.st_size == len(rendered),
            "atomic output temporary metadata differs",
        )
        temporary_inode = (temporary_metadata.st_dev, temporary_metadata.st_ino)
        _require(
            temporary_inode not in protected_inodes,
            "atomic output temporary aliases a protected input inode",
        )
        os.lseek(temporary_descriptor, 0, os.SEEK_SET)
        verified = bytearray()
        while len(verified) < len(rendered):
            chunk = os.read(
                temporary_descriptor,
                min(65_536, len(rendered) - len(verified)),
            )
            _require(bool(chunk), "atomic output temporary was truncated")
            verified.extend(chunk)
        _require(bytes(verified) == rendered, "atomic output temporary bytes differ")
        os.close(temporary_descriptor)
        temporary_descriptor = None

        _require(
            _output_entry_identity(parent_descriptor, leaf_name) == original_identity,
            "output path identity changed before atomic replacement",
        )
        _require(
            _current_directory_identity(
                repository_root,
                parts[:-1],
                label="repository output",
            )
            == parent_identity,
            "output parent identity changed before atomic replacement",
        )
        os.replace(
            temporary_name,
            leaf_name,
            src_dir_fd=parent_descriptor,
            dst_dir_fd=parent_descriptor,
        )
        renamed = True
        os.fsync(parent_descriptor)

        final_flags = os.O_RDONLY | os.O_NONBLOCK
        final_flags |= getattr(os, "O_CLOEXEC", 0)
        final_flags |= getattr(os, "O_NOFOLLOW", 0)
        final_descriptor = os.open(leaf_name, final_flags, dir_fd=parent_descriptor)
        try:
            before = os.fstat(final_descriptor)
            _require(
                stat.S_ISREG(before.st_mode)
                and before.st_nlink == 1
                and before.st_size == len(rendered),
                "atomically published output metadata differs",
            )
            _require(
                (before.st_dev, before.st_ino) == temporary_inode,
                "atomically published output identity differs from temporary",
            )
            chunks: list[bytes] = []
            total = 0
            while total < len(rendered):
                chunk = os.read(final_descriptor, min(65_536, len(rendered) - total))
                _require(bool(chunk), "atomically published output was truncated")
                chunks.append(chunk)
                total += len(chunk)
            after = os.fstat(final_descriptor)
            _require(
                _file_identity(before) == _file_identity(after)
                and b"".join(chunks) == rendered,
                "atomically published output bytes or identity differ",
            )
            path_metadata = os.stat(
                leaf_name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
            _require(
                _file_identity(path_metadata) == _file_identity(after),
                "atomically published output path identity changed",
            )
        finally:
            os.close(final_descriptor)
        _require(
            _current_directory_identity(
                repository_root,
                parts[:-1],
                label="repository output",
            )
            == parent_identity,
            "output parent identity changed after atomic replacement",
        )
    finally:
        if temporary_descriptor is not None:
            os.close(temporary_descriptor)
        if temporary_name is not None and not renamed:
            try:
                os.unlink(temporary_name, dir_fd=parent_descriptor)
            except FileNotFoundError:
                pass
        os.close(parent_descriptor)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="check the frozen V4 JSON")
    mode.add_argument("--write", action="store_true", help="write the frozen V4 JSON")
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path(DEFAULT_OUTPUT))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        repository_root = args.repository_root.resolve(strict=True)
        root_descriptor = _open_repository_directory_fd(
            repository_root,
            (),
            label="repository root",
        )
        os.close(root_descriptor)

        snapshots = _load_repeatable_source_snapshots(repository_root)
        protected_inodes = _protected_inodes(snapshots)
        output, relative_output = _resolve_output(
            repository_root,
            args.output,
            protected_inodes=protected_inodes,
        )
        inventory = _build_v4_inventory(snapshots)
        rendered = _pretty_bytes(inventory)
        _enforce_v4_physical_freeze(inventory, rendered)

        # Close the source snapshot again immediately before observing/publishing
        # the output so a completed earlier pass cannot authorize later drift.
        current_sources = _snapshot_all_sources(repository_root)
        _assert_snapshot_sets_equal(snapshots, current_sources)
        if args.write:
            _atomic_write_repository_output(
                repository_root,
                relative_output,
                rendered,
                protected_inodes=protected_inodes,
            )
            action = "wrote"
        else:
            output_spec = _SourceSpec(
                "frozen V4 inventory",
                relative_output,
                len(rendered),
                _sha256_bytes(rendered),
                True,
            )
            actual = _bounded_repository_snapshot(repository_root, output_spec).raw
            _require(
                actual == rendered,
                "frozen V4 inventory differs from the exact migration; run --write explicitly",
            )
            _parse_strict_canonical_json(actual, label="frozen V4 inventory")
            action = "checked"

        final_sources = _snapshot_all_sources(repository_root)
        _assert_snapshot_sets_equal(snapshots, final_sources)
        print(
            f"{action} {output}: predecessor={V3_INVENTORY_ID} "
            f"inventory={inventory['inventory_sha256']} "
            f"profiles={MAXIMUM_SCOPE_PROFILE_COUNT} normative_inputs=5"
        )
        return 0
    except (InventoryMigrationError, OSError, RuntimeError) as exc:
        print(
            f"Raw-V8 Step-2 V4 inventory migration error: {exc}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

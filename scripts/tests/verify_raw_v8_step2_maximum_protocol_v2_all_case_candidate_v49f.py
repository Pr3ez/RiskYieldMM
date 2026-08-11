#!/usr/bin/env python3
"""A4-R475-V0 foundation for the versioned all-case V2 verifier.

This packet intentionally accepts no constructive candidate.  It independently
loads and reconstructs the complete all-case authority map, securely pins the
accepted External Schema V2 typed-rule runtime, and exposes the typed-legality
and rule-AST primitives required by later verifier packets.  The fixed single-
case CLI rejects after the complete authority barrier and before opening the
candidate or output paths.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import stat
import sys
import types
from dataclasses import dataclass
from typing import Any, Final, NoReturn

SOURCE_MARKER: Final = "INDEPENDENT_V2_ALL_CASE_CONSTRUCTIVE_VERIFIER_V1"
PACKET: Final = "A4-R475-V0"
ERROR_PREFIX: Final = (
    "RAW_V8_STEP2_MAXIMUM_PROTOCOL_V2_ALL_CASE_VERIFIER_"
)

CONTRACT_RELATIVE_PATH: Final = (
    "scripts/tests/raw_v8_step2_maximum_protocol_v2_"
    "all_case_campaign_contract_v49f.json"
)
CONTRACT_OCTETS: Final = 382_710
CONTRACT_SHA256: Final = (
    "3ca4ff4d6e581895b813043e7fdeed24c33cf2c828e362ac81de1725e95a84bb"
)
CONTRACT_ID: Final = (
    "9be94bf6b53b612d62ac26bc74133f25c1101a0962987a855e65cdcd06418583"
)
CONTRACT_DOMAIN: Final = (
    "RiskYieldMMRawV8Step2MaximumProtocolV2AllCaseCampaignContractV1"
)
CASE_RECORD_DOMAIN: Final = (
    "RiskYieldMMRawV8Step2MaximumProtocolV2AllCaseExecutionRecordV1"
)
CASE_LEDGER_DOMAIN: Final = (
    "RiskYieldMMRawV8Step2MaximumProtocolV2AllCaseExecutionLedgerV1"
)

RUNTIME_RELATIVE_PATH: Final = (
    "scripts/tests/validate_raw_v8_step2_external_schema_v2_rule_runtime_v49f.py"
)
RUNTIME_OCTETS: Final = 249_268
RUNTIME_SHA256: Final = (
    "47aa90d897e8dbae5e244b7c04cbd82dfe036b0292d36ef0f5552c868627ab22"
)
STRUCTURAL_REGISTRY_RELATIVE_PATH: Final = (
    "scripts/tests/raw_v8_step2_external_schema_v2_structural_registry_v49f.json"
)
STRUCTURAL_REGISTRY_OCTETS: Final = 1_469_663
STRUCTURAL_REGISTRY_SHA256: Final = (
    "9160297ff316c5931737c92f8b359f0a1e2ec22f0aa996ef3b09cf830dc96bf3"
)
RULE_LITERAL_AUTHORITY_RELATIVE_PATH: Final = (
    "scripts/tests/raw_v8_step2_external_schema_v2_rule_literal_authority_v49f.json"
)
RULE_LITERAL_AUTHORITY_OCTETS: Final = 484_301
RULE_LITERAL_AUTHORITY_SHA256: Final = (
    "aba3461059367904734e2eb9ae404787b9aab5ed4c3fbcd292925a364926cce2"
)

EXPECTED_AUTHORITY_ROLES: Final = (
    "PREFLIGHT_CONTRACT",
    "SEED",
    "FINALIZATION_MANIFEST",
    "CONSTRUCTIVE_BOUNDARY",
    "CASE435_SEED_DELTA",
    "CASE435_MANIFEST_DELTA",
    "CASE435_BOUNDARY_DELTA",
    "CASE435_TARGET_DELTA",
    "PACKED_CONTEXT_BOUNDARY",
    "A4_P6_E_REPORT",
    "PILOT_PRODUCER",
    "PILOT_VERIFIER",
    "PILOT_RUNNER",
)
EXPECTED_FAMILIES: Final = {
    "CORRECTED_APPLICATION_EXACT_PROFILE": 1,
    "GENERIC_PROFILE_ATTAINMENT": 406,
    "INTRINSIC_TEMPLATE_ATTAINMENT": 66,
    "LOCAL_MINIMALITY": 1,
    "SIGNED_ANALYTIC_EXACT_PROFILE": 1,
}
EXPECTED_PILOT_CASES: Final = [5, 24, 54, 69, 435, 475]
CASE_COUNT: Final = 475
CASE69_POSITION: Final = 69
CASE435_POSITION: Final = 435
LOCAL_CASE_POSITION: Final = 475

SAFE_INTEGER_MAXIMUM: Final = 9_007_199_254_740_991
DEFAULT_LIMITS: Final = {
    "INDIVIDUAL_FILE_STRICT_UPPER_OCTETS": 16_777_216,
    "TOTAL_PINNED_INPUT_OCTETS": 67_108_864,
    "INPUT_FILE_COUNT": 64,
    "JSON_NESTING_DEPTH": 96,
    "DECODED_JSON_NODE_COUNT": 2_097_152,
    "DECODED_JSON_ARRAY_ENTRY_COUNT": 1_048_576,
    "DECODED_JSON_OBJECT_MEMBER_COUNT": 1_048_576,
}


class VerifierReject(ValueError):
    """A stable fail-closed verifier rejection."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = str(message).replace("\n", " ").replace("\r", " ")[:768]
        super().__init__(f"{code}: {self.message}")


@dataclass(frozen=True)
class Foundation:
    """Immutable V0 authority and typed-runtime snapshot."""

    repository_root: pathlib.Path
    boundary_path: pathlib.Path
    contract: dict[str, Any]
    values: dict[str, Any]
    case_records: tuple[dict[str, Any], ...]
    cases: tuple[dict[str, Any], ...]
    plans: tuple[dict[str, Any], ...]
    runtime_module: types.ModuleType
    runtime: Any
    runtime_report: dict[str, Any]
    authority_snapshots: tuple[dict[str, Any], ...]
    f0_limits: dict[str, int]
    pinned_input_octets: int


def _reject(code: str, message: str) -> NoReturn:
    raise VerifierReject(code, message)


def _require(condition: bool, code: str, message: str) -> None:
    if not condition:
        _reject(code, message)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


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
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as error:
        _reject("CANONICALIZATION_INVALID", f"canonical JSON rejected: {error}")


def _pretty_bytes(value: Any, *, sort_keys: bool = True) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=sort_keys,
                indent=2,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as error:
        _reject("CANONICALIZATION_INVALID", f"pretty JSON rejected: {error}")


def _semantic_id(domain: str, payload: Any) -> str:
    return _sha256(_canonical_bytes({"domain": domain, "payload": payload}))


def _duplicate_guard(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, child in pairs:
        _require(
            key not in result,
            "CANONICALIZATION_INVALID",
            f"duplicate JSON key: {key}",
        )
        result[key] = child
    return result


def _reject_float(value: str) -> NoReturn:
    _reject("CANONICALIZATION_INVALID", f"floating JSON number is forbidden: {value}")


def _reject_constant(value: str) -> NoReturn:
    _reject("CANONICALIZATION_INVALID", f"non-finite number is forbidden: {value}")


def _validate_json_shape(value: Any, limits: dict[str, int]) -> None:
    stack: list[tuple[Any, int]] = [(value, 1)]
    nodes = 0
    array_entries = 0
    object_members = 0
    while stack:
        child, depth = stack.pop()
        nodes += 1
        _require(
            depth <= limits["JSON_NESTING_DEPTH"],
            "INPUT_LIMIT_EXCEEDED",
            "JSON nesting depth exceeded",
        )
        _require(
            nodes <= limits["DECODED_JSON_NODE_COUNT"],
            "INPUT_LIMIT_EXCEEDED",
            "decoded JSON node count exceeded",
        )
        if isinstance(child, dict):
            object_members += len(child)
            _require(
                object_members <= limits["DECODED_JSON_OBJECT_MEMBER_COUNT"],
                "INPUT_LIMIT_EXCEEDED",
                "decoded JSON object-member count exceeded",
            )
            for key, nested in child.items():
                _require(
                    isinstance(key, str),
                    "CANONICALIZATION_INVALID",
                    "JSON object key is not text",
                )
                stack.append((key, depth + 1))
                stack.append((nested, depth + 1))
        elif isinstance(child, list):
            array_entries += len(child)
            _require(
                array_entries <= limits["DECODED_JSON_ARRAY_ENTRY_COUNT"],
                "INPUT_LIMIT_EXCEEDED",
                "decoded JSON array-entry count exceeded",
            )
            stack.extend((nested, depth + 1) for nested in child)
        elif isinstance(child, str):
            _require(
                all(not 0xD800 <= ord(character) <= 0xDFFF for character in child),
                "CANONICALIZATION_INVALID",
                "lone surrogate is forbidden",
            )
        elif child is None or isinstance(child, bool):
            continue
        elif _is_int(child):
            _require(
                -SAFE_INTEGER_MAXIMUM <= child <= SAFE_INTEGER_MAXIMUM,
                "CANONICALIZATION_INVALID",
                "JSON integer exceeds safe-integer bounds",
            )
        else:
            _reject("CANONICALIZATION_INVALID", "unsupported decoded JSON value")


def _strict_loads(raw: bytes, limits: dict[str, int]) -> Any:
    try:
        text = raw.decode("utf-8", errors="strict")
        _require(
            not text.startswith("\ufeff"),
            "CANONICALIZATION_INVALID",
            "UTF-8 BOM is forbidden",
        )
        value = json.loads(
            text,
            object_pairs_hook=_duplicate_guard,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except VerifierReject:
        raise
    except (UnicodeError, json.JSONDecodeError) as error:
        _reject("CANONICALIZATION_INVALID", f"strict JSON rejected: {error}")
    _validate_json_shape(value, limits)
    return value


def _closed(value: Any, names: set[str], label: str) -> dict[str, Any]:
    _require(isinstance(value, dict), "SCHEMA_INVALID", f"{label} is not an object")
    _require(set(value) == names, "SCHEMA_INVALID", f"{label} members differ")
    return value


def _signature(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _absolute_lexical_path(
    value: pathlib.Path,
    label: str,
    *,
    must_exist: bool,
) -> pathlib.Path:
    path = pathlib.Path(value)
    _require(path.is_absolute(), "INVOCATION_INVALID", f"{label} must be absolute")
    _require(
        path == pathlib.Path(os.path.abspath(os.fspath(path))),
        "INVOCATION_INVALID",
        f"{label} must be lexically canonical",
    )
    probe = path if must_exist else path.parent
    _require(probe.exists(), "INVOCATION_INVALID", f"{label} anchor is absent")
    current = pathlib.Path(path.anchor)
    for component in probe.parts[1:]:
        _require(
            component not in {"", ".", ".."},
            "INVOCATION_INVALID",
            f"{label} has a forbidden component",
        )
        current = current / component
        info = os.lstat(current)
        _require(
            not stat.S_ISLNK(info.st_mode),
            "FILESYSTEM_INVALID",
            f"{label} traverses a symlink",
        )
    return path


def _directory_signature(path: pathlib.Path, label: str) -> tuple[int, ...]:
    info = os.lstat(path)
    _require(
        stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode),
        "FILESYSTEM_INVALID",
        f"{label} is not a direct directory",
    )
    return _signature(info)


def _safe_relative_path(
    repository_root: pathlib.Path,
    relative: str,
    label: str,
) -> pathlib.Path:
    _require(
        isinstance(relative, str) and relative and not relative.startswith("/"),
        "AUTHORITY_INVALID",
        f"{label} path is not repository-relative",
    )
    parts = pathlib.PurePosixPath(relative).parts
    _require(
        parts and all(part not in {"", ".", ".."} for part in parts),
        "AUTHORITY_INVALID",
        f"{label} path escapes the repository",
    )
    current = repository_root
    for component in parts[:-1]:
        current = current / component
        _directory_signature(current, label)
    return repository_root.joinpath(*parts)


def _read_regular(
    path: pathlib.Path,
    limit: int,
    label: str,
) -> tuple[bytes, tuple[int, ...]]:
    before = os.lstat(path)
    _require(
        stat.S_ISREG(before.st_mode) and not stat.S_ISLNK(before.st_mode),
        "FILESYSTEM_INVALID",
        f"{label} is not a direct regular file",
    )
    _require(
        before.st_nlink == 1,
        "FILESYSTEM_INVALID",
        f"{label} is not single-link",
    )
    _require(
        0 <= before.st_size < limit,
        "INPUT_LIMIT_EXCEEDED",
        f"{label} exceeds the strict file limit",
    )
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        _require(
            _signature(opened) == _signature(before),
            "INPUT_RACE_DETECTED",
            f"{label} changed before read",
        )
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 1 << 20))
            _require(chunk != b"", "INPUT_RACE_DETECTED", f"{label} ended early")
            chunks.append(chunk)
            remaining -= len(chunk)
        _require(
            os.read(descriptor, 1) == b"",
            "INPUT_RACE_DETECTED",
            f"{label} grew during read",
        )
        _require(
            _signature(os.fstat(descriptor)) == _signature(before),
            "INPUT_RACE_DETECTED",
            f"{label} changed during read",
        )
    finally:
        os.close(descriptor)
    return b"".join(chunks), _signature(before)


def _snapshot_file(
    path: pathlib.Path,
    limits: dict[str, int],
    label: str,
    *,
    expected_octets: int | None = None,
    expected_sha256: str | None = None,
) -> tuple[bytes, dict[str, Any]]:
    raw, signature = _read_regular(
        path,
        limits["INDIVIDUAL_FILE_STRICT_UPPER_OCTETS"],
        label,
    )
    digest = _sha256(raw)
    if expected_octets is not None:
        _require(len(raw) == expected_octets, "AUTHORITY_INVALID", f"{label} size drifted")
    if expected_sha256 is not None:
        _require(digest == expected_sha256, "AUTHORITY_INVALID", f"{label} hash drifted")
    return raw, {
        "label": label,
        "path": path,
        "signature": signature,
        "raw_octets": len(raw),
        "raw_sha256": digest,
    }


def _recheck_snapshots(snapshots: tuple[dict[str, Any], ...]) -> int:
    seen_inodes: set[tuple[int, int]] = set()
    total = 0
    for snapshot in snapshots:
        raw, signature = _read_regular(
            snapshot["path"],
            DEFAULT_LIMITS["INDIVIDUAL_FILE_STRICT_UPPER_OCTETS"],
            snapshot["label"],
        )
        _require(
            signature == snapshot["signature"],
            "INPUT_RACE_DETECTED",
            f"{snapshot['label']} signature drifted",
        )
        _require(
            len(raw) == snapshot["raw_octets"]
            and _sha256(raw) == snapshot["raw_sha256"],
            "INPUT_RACE_DETECTED",
            f"{snapshot['label']} bytes drifted",
        )
        inode = (signature[0], signature[1])
        _require(
            inode not in seen_inodes,
            "FILESYSTEM_INVALID",
            "authority inode alias detected",
        )
        seen_inodes.add(inode)
        total += len(raw)
    return total


def _contract_payload(contract: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in contract.items()
        if key != "all_case_campaign_contract_id"
    }


def _validate_contract_surface(contract: dict[str, Any]) -> None:
    expected_root = {
        "acceptance_contract",
        "all_case_campaign_contract_id",
        "all_case_campaign_contract_version",
        "architecture_decision_contract",
        "authority_contract",
        "candidate_and_result_contract",
        "canonicalization_version",
        "case_universe_contract",
        "checkpoint_schema_contract",
        "effective_authority_contract",
        "gate_contract",
        "implementation_sequence_contract",
        "measurement_schema_version",
        "predecessor_regression_authority_contract",
        "protocol_version",
        "publication_contract",
        "resource_contract",
        "scheduler_and_checkpoint_contract",
        "versioned_role_contract",
    }
    _closed(contract, expected_root, "all-case contract")
    _require(
        contract["all_case_campaign_contract_id"]
        == _semantic_id(CONTRACT_DOMAIN, _contract_payload(contract))
        == CONTRACT_ID,
        "AUTHORITY_INVALID",
        "all-case contract identity differs",
    )
    gate = contract["gate_contract"]
    _require(
        gate["correction_subgate"] == "A4-R475-T"
        and gate["accepted_scope"] == "CONTRACT_AND_FAIL_FIRST_BOUNDARY_ONLY"
        and gate["all_case_implementation_state"] == "FAIL_FIRST_NOT_IMPLEMENTED"
        and gate["formal_stage1_state"] == "NO-GO"
        and gate["next_bounded_packet_after_contract_acceptance"] == PACKET
        and gate["profitability_safety_or_live_readiness_claimed"] is False,
        "AUTHORITY_INVALID",
        "all-case gate contract differs",
    )
    sequence = contract["implementation_sequence_contract"]
    packets = sequence["ordered_packet_records"]
    _require(
        [row["packet_position"] for row in packets] == list(range(1, 8))
        and [row["packet"] for row in packets]
        == [
            "A4-R475-V0",
            "A4-R475-V1",
            "A4-R475-V2",
            "A4-R475-V3",
            "A4-R475-P",
            "A4-R475-R",
            "A4-R475-E",
        ],
        "AUTHORITY_INVALID",
        "implementation sequence differs",
    )
    roles = contract["versioned_role_contract"]["ordered_role_records"]
    _require(
        len(roles) == 3
        and roles[0]
        == {
            "implementation_state": "ABSENT_FAIL_FIRST",
            "may_execute_other_role": False,
            "repository_relative_path": (
                "scripts/tests/verify_raw_v8_step2_maximum_protocol_v2_"
                "all_case_candidate_v49f.py"
            ),
            "role_name": "VERSIONED_ALL_CASE_VERIFIER",
            "role_position": 1,
            "semantic_authority": True,
            "source_marker": SOURCE_MARKER,
        }
        and [row["role_position"] for row in roles] == [1, 2, 3],
        "AUTHORITY_INVALID",
        "versioned role contract differs",
    )
    predecessor = contract["predecessor_regression_authority_contract"]
    _require(
        predecessor["surface"] == "EXACTLY_SIX_CASES"
        and predecessor["ordered_supported_case_positions"] == EXPECTED_PILOT_CASES
        and predecessor["non_pilot_case_count"] == 469
        and predecessor["in_place_extension_policy"] == "FORBIDDEN"
        and predecessor["all_case_readiness_claimed"] is False,
        "AUTHORITY_INVALID",
        "predecessor regression contract differs",
    )


def _resource_limits(contract: dict[str, Any]) -> dict[str, int]:
    rows = contract["resource_contract"]["ordered_f0_limit_records"]
    _require(
        isinstance(rows, list) and len(rows) == 12,
        "AUTHORITY_INVALID",
        "F0 contract differs",
    )
    limits: dict[str, int] = {}
    for position, row in enumerate(rows, 1):
        _require(
            row["ceiling_position"] == position
            and _is_int(row["ceiling_value"])
            and row["ceiling_value"] >= 0,
            "AUTHORITY_INVALID",
            "F0 record differs",
        )
        limits[row["resource_name"]] = row["ceiling_value"]
    _require(
        all(limits[name] == value for name, value in DEFAULT_LIMITS.items()),
        "AUTHORITY_INVALID",
        "required V0 F0 limits differ",
    )
    return limits


def _load_contract(
    repository_root: pathlib.Path,
    boundary_path: pathlib.Path,
) -> tuple[dict[str, Any], dict[str, int], dict[str, Any]]:
    expected = repository_root / CONTRACT_RELATIVE_PATH
    _require(
        boundary_path == expected,
        "INVOCATION_INVALID",
        "boundary path is not the accepted all-case contract",
    )
    raw, snapshot = _snapshot_file(
        boundary_path,
        DEFAULT_LIMITS,
        "all-case contract",
        expected_octets=CONTRACT_OCTETS,
        expected_sha256=CONTRACT_SHA256,
    )
    contract = _strict_loads(raw, DEFAULT_LIMITS)
    _require(
        isinstance(contract, dict) and raw == _pretty_bytes(contract),
        "CANONICALIZATION_INVALID",
        "all-case contract physical encoding differs",
    )
    _validate_contract_surface(contract)
    return contract, _resource_limits(contract), snapshot


def _load_contract_authorities(
    repository_root: pathlib.Path,
    contract: dict[str, Any],
    limits: dict[str, int],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    authority = contract["authority_contract"]
    records = authority["ordered_authority_records"]
    _require(
        authority["authority_loading_rule"]
        == (
            "OPEN_NOFOLLOW_REGULAR_SINGLE_LINK_EXACT_SIZE_HASH_AND_RECHECK_"
            "BEFORE_EVERY_CASE_COMMIT_AND_FINAL_PUBLICATION"
        )
        and authority["unknown_missing_extra_or_drifted_authority_policy"]
        == "REJECT"
        and isinstance(records, list)
        and [row["authority_role"] for row in records]
        == list(EXPECTED_AUTHORITY_ROLES),
        "AUTHORITY_INVALID",
        "ordered authority contract differs",
    )
    values: dict[str, Any] = {}
    snapshots: list[dict[str, Any]] = []
    for record in records:
        _closed(
            record,
            {
                "authority_role",
                "repository_relative_path",
                "raw_octets",
                "raw_sha256",
            },
            "authority record",
        )
        role = record["authority_role"]
        path = _safe_relative_path(
            repository_root,
            record["repository_relative_path"],
            role,
        )
        raw, snapshot = _snapshot_file(
            path,
            limits,
            role,
            expected_octets=record["raw_octets"],
            expected_sha256=record["raw_sha256"],
        )
        snapshots.append(snapshot)
        if record["repository_relative_path"].endswith(".json"):
            value = _strict_loads(raw, limits)
            _require(isinstance(value, dict), "AUTHORITY_INVALID", f"{role} root differs")
            if role != "CONSTRUCTIVE_BOUNDARY":
                _require(
                    raw == _pretty_bytes(value),
                    "CANONICALIZATION_INVALID",
                    f"{role} physical encoding differs",
                )
            values[role] = value
        else:
            values[role] = raw
    return values, snapshots


def _validate_authority_chain(values: dict[str, Any]) -> None:
    preflight = values["PREFLIGHT_CONTRACT"]
    seed = values["SEED"]
    manifest = values["FINALIZATION_MANIFEST"]
    boundary = values["CONSTRUCTIVE_BOUNDARY"]
    seed_delta = values["CASE435_SEED_DELTA"]
    manifest_delta = values["CASE435_MANIFEST_DELTA"]
    boundary_delta = values["CASE435_BOUNDARY_DELTA"]
    target_delta = values["CASE435_TARGET_DELTA"]
    packed = values["PACKED_CONTEXT_BOUNDARY"]
    acceptance = values["A4_P6_E_REPORT"]
    _require(
        preflight["contract_id"]
        == "6609ad7b9abf21432136e49af178e20c17cb7bc27d3b444a4b6f01a17073fc76"
        and seed["seed_catalog_id"]
        == "ac22151fa74702ac1488924f01161eaa38574545e6272a290db6b0bbd288ae5f"
        and manifest["finalization_manifest_id"]
        == "edde204e98ed1caeeb8ae270487d85e39a2168e0a3692ce1d8748d2d8e7fd858"
        and boundary["constructive_boundary_id"]
        == "bdc7363ae28dfe9a1c1dc132808cb1bd4a06c409201cd49b31e394893142a7ed",
        "AUTHORITY_INVALID",
        "predecessor authority identities differ",
    )
    _require(
        seed_delta["successor_seed_catalog_id"]
        == "7fad47e881624d0f39809e72ce2d3d3fd81fb8c85f854fe8332faf543cd1120b"
        and manifest_delta["successor_manifest_id"]
        == "6aed1139c158f8685bcb226697a2efe57af3c42f57831173bd7b3ea169025d9c"
        and boundary_delta["successor_constructive_boundary_id"]
        == "7d4c06f56cd3cacd97cc4ff655e31f380fe9231c6c7c1374caee499186e1f73d"
        and target_delta["successor_six_case_target_id"]
        == "a000285d1bedd88306786ea33e1be9cc7d2a8459fe75b20c045f7174d52cc072"
        and packed["case435_context_pack_boundary_delta_id"]
        == "c8448f57dcdc3e4f1f3239043ed4977013efbd99c750cb2e2e857025f5ac0acd",
        "AUTHORITY_INVALID",
        "successor authority identities differ",
    )
    _require(
        acceptance["six_case_end_to_end_acceptance_report_id"]
        == "c94c784f29a57fd8fc345cd49b90b7225e2a5697ff2077c8dd0b4b2115809d11"
        and acceptance["release_decision"]
        == "RELEASED_FOR_A4_R475_VERSIONED_IMPLEMENTATION",
        "AUTHORITY_INVALID",
        "pilot release authority differs",
    )
    effective = packed["unchanged_effective_authorities"]
    successor_plan = seed_delta["successor_case435_logical_count_plan"]
    _require(
        effective["successor_seed_catalog_id"]
        == seed_delta["successor_seed_catalog_id"]
        and effective["successor_manifest_id"]
        == manifest_delta["successor_manifest_id"]
        and effective["case435_logical_count_plan_id"]
        == successor_plan["logical_count_plan_id"]
        and effective["f2_resource_limit_catalog_id"]
        == boundary_delta["successor_f2_resource_limit_catalog"]
        ["f2_resource_limit_catalog_id"],
        "AUTHORITY_INVALID",
        "effective successor authority chain differs",
    )
    _require(
        manifest_delta["f2_limit_authority"]["ordered_f2_limit_records_sha256"]
        == _sha256(_canonical_bytes(manifest["ordered_f2_limit_records"])),
        "AUTHORITY_INVALID",
        "F2 authority chain differs",
    )


def _execution_family(case_position: int, plan: dict[str, Any]) -> str:
    if case_position == LOCAL_CASE_POSITION:
        return "LOCAL_MINIMALITY"
    if case_position == CASE69_POSITION:
        return "SIGNED_ANALYTIC_EXACT_PROFILE"
    if case_position == CASE435_POSITION:
        return "CORRECTED_APPLICATION_EXACT_PROFILE"
    if plan.get("profile_conditioning_program_id") is not None:
        return "GENERIC_PROFILE_ATTAINMENT"
    return "INTRINSIC_TEMPLATE_ATTAINMENT"


def _reconstruct_case_ledger(
    values: dict[str, Any],
) -> tuple[
    tuple[dict[str, Any], ...],
    tuple[dict[str, Any], ...],
    tuple[dict[str, Any], ...],
]:
    seed = values["SEED"]
    seed_delta = values["CASE435_SEED_DELTA"]
    cases = seed["case_universe_catalog"]["ordered_case_bindings"]
    base_plans = seed["logical_plan_recipe_catalog"]
    plans = base_plans["ordered_logical_count_plan_records"]
    bindings = base_plans["ordered_case_plan_bindings"]
    _require(
        len(cases) == len(plans) == len(bindings) == CASE_COUNT,
        "AUTHORITY_INVALID",
        "base case universe cardinality differs",
    )
    records: list[dict[str, Any]] = []
    effective_plans: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for position in range(1, CASE_COUNT + 1):
        case = cases[position - 1]
        plan = (
            seed_delta["successor_case435_logical_count_plan"]
            if position == CASE435_POSITION
            else plans[position - 1]
        )
        binding = (
            seed_delta["successor_case435_case_plan_binding"]
            if position == CASE435_POSITION
            else bindings[position - 1]
        )
        _require(
            case["case_position"]
            == plan["case_position"]
            == binding["case_position"]
            == binding["logical_count_plan_position"]
            == position,
            "AUTHORITY_INVALID",
            f"case/plan order differs at {position}",
        )
        _require(
            case["case_binding"] == plan["case_binding"]
            and binding["logical_count_plan_id"] == plan["logical_count_plan_id"],
            "AUTHORITY_INVALID",
            f"case/plan binding differs at {position}",
        )
        family = _execution_family(position, plan)
        counts[family] = counts.get(family, 0) + 1
        case_binding = case["case_binding"]
        payload = {
            "campaign_position": position,
            "case_position": position,
            "case_kind": case["case_kind"],
            "row_kind": case_binding.get("row_kind"),
            "type_name": case_binding.get("type_name"),
            "alternative_name": case_binding.get("alternative_name"),
            "constraint_scope_profile_id": case_binding.get(
                "constraint_scope_profile_id"
            ),
            "effective_logical_count_plan_id": plan["logical_count_plan_id"],
            "effective_plan_source": (
                "CASE435_SUCCESSOR_DELTA"
                if position == CASE435_POSITION
                else "BASE_SEED"
            ),
            "execution_family": family,
            "candidate_transport": (
                "CASE435_PACKED_CONTEXT_V1"
                if position == CASE435_POSITION
                else "INHERITED_CLOSED_CANDIDATE_BUNDLE_V1"
            ),
        }
        records.append(
            {
                **payload,
                "case_execution_record_id": _semantic_id(CASE_RECORD_DOMAIN, payload),
            }
        )
        effective_plans.append(plan)
    _require(
        counts == EXPECTED_FAMILIES,
        "AUTHORITY_INVALID",
        "execution-family census differs",
    )
    return tuple(records), tuple(cases), tuple(effective_plans)


def _validate_case_ledger(
    contract: dict[str, Any],
    values: dict[str, Any],
) -> tuple[
    tuple[dict[str, Any], ...],
    tuple[dict[str, Any], ...],
    tuple[dict[str, Any], ...],
]:
    records, cases, plans = _reconstruct_case_ledger(values)
    universe = contract["case_universe_contract"]
    _require(
        universe["case_count"] == CASE_COUNT
        and universe["maximum_publication_case_count"] == 474
        and universe["local_minimality_case_count"] == 1
        and universe["execution_family_counts"] == EXPECTED_FAMILIES
        and universe["ordered_case_execution_records"] == list(records)
        and universe["ordered_case_execution_records_sha256"]
        == _sha256(_canonical_bytes(list(records)))
        and universe["case_execution_ledger_id"]
        == _semantic_id(
            CASE_LEDGER_DOMAIN,
            {"case_count": CASE_COUNT, "ordered_case_execution_records": list(records)},
        ),
        "AUTHORITY_INVALID",
        "all-case execution ledger differs from reconstructed authorities",
    )
    effective = contract["effective_authority_contract"]
    packed = values["PACKED_CONTEXT_BOUNDARY"]["unchanged_effective_authorities"]
    _require(
        effective["predecessor_seed_catalog_id"]
        == values["SEED"]["seed_catalog_id"]
        and effective["effective_successor_seed_catalog_id"]
        == packed["successor_seed_catalog_id"]
        and effective["effective_successor_manifest_id"]
        == packed["successor_manifest_id"]
        and effective["effective_f2_resource_limit_catalog_id"]
        == packed["f2_resource_limit_catalog_id"]
        and effective["case435_effective_plan_rule"]
        == "ONLY_CASE_435_RESOLVES_THROUGH_ACCEPTED_SUCCESSOR_SEED_DELTA",
        "AUTHORITY_INVALID",
        "effective all-case authority bindings differ",
    )
    return records, cases, plans


def _load_extra_pinned_file(
    repository_root: pathlib.Path,
    limits: dict[str, int],
    relative_path: str,
    octets: int,
    digest: str,
    label: str,
) -> tuple[bytes, dict[str, Any]]:
    path = _safe_relative_path(repository_root, relative_path, label)
    return _snapshot_file(
        path,
        limits,
        label,
        expected_octets=octets,
        expected_sha256=digest,
    )


def _load_pinned_runtime(
    repository_root: pathlib.Path,
    runtime_raw: bytes,
    runtime_path: pathlib.Path,
) -> tuple[types.ModuleType, Any, dict[str, Any]]:
    module_name = "_riskyieldmm_a4_r475_v0_pinned_rule_runtime"
    module = types.ModuleType(module_name)
    module.__file__ = os.fspath(runtime_path)
    module.__package__ = ""
    sys.modules[module_name] = module
    try:
        code = compile(runtime_raw, os.fspath(runtime_path), "exec", dont_inherit=True)
        exec(code, module.__dict__)
        runtime_class = module.ExternalSchemaV2Runtime
        runtime = runtime_class.load(repository_root)
        report = runtime.validation_report()
    except VerifierReject:
        raise
    except Exception as error:
        _reject(
            "TYPED_RUNTIME_INVALID",
            f"pinned typed runtime rejected: {type(error).__name__}: {error}",
        )
    expected_report = {
        "ascii_dfa_count": 9,
        "complex_operator_count": 11,
        "derived_maximum_validation_work": 4_202_555,
        "executable_application_count": 8,
        "executable_complex_rule_count": 9,
        "executable_expression_node_count": 1_057,
        "executable_generic_rule_count": 33,
        "executable_rule_count": 42,
        "external_type_count": 52,
        "fixed_position_resolver_count": 2,
        "generic_operator_count": 41,
        "record_type_count": 49,
        "tagged_union_type_count": 3,
        "text_language_count": 103,
        "total_rule_count": 42,
        "total_rule_expression_node_count": 1_057,
        "unsupported_complex_rule_count": 0,
        "unsupported_complex_rule_expression_node_count": 0,
        "value_schema_count": 236,
    }
    _require(
        all(report.get(key) == value for key, value in expected_report.items())
        and report.get("status")
        == "APPLICATION_RUNTIME_ONLY_MAXIMA_AND_PRODUCTION_INTEGRATION_PENDING",
        "TYPED_RUNTIME_INVALID",
        "typed-runtime capability report differs",
    )
    return module, runtime, report


def _load_foundation(
    repository_root: pathlib.Path,
    boundary_path: pathlib.Path,
) -> Foundation:
    repository_root = _absolute_lexical_path(
        pathlib.Path(repository_root),
        "repository root",
        must_exist=True,
    )
    _directory_signature(repository_root, "repository root")
    boundary_path = _absolute_lexical_path(
        pathlib.Path(boundary_path),
        "boundary",
        must_exist=True,
    )
    contract, limits, contract_snapshot = _load_contract(
        repository_root,
        boundary_path,
    )
    values, authority_snapshots = _load_contract_authorities(
        repository_root,
        contract,
        limits,
    )
    _validate_authority_chain(values)
    records, cases, plans = _validate_case_ledger(contract, values)

    runtime_raw, runtime_snapshot = _load_extra_pinned_file(
        repository_root,
        limits,
        RUNTIME_RELATIVE_PATH,
        RUNTIME_OCTETS,
        RUNTIME_SHA256,
        "typed-rule runtime source",
    )
    _, registry_snapshot = _load_extra_pinned_file(
        repository_root,
        limits,
        STRUCTURAL_REGISTRY_RELATIVE_PATH,
        STRUCTURAL_REGISTRY_OCTETS,
        STRUCTURAL_REGISTRY_SHA256,
        "structural registry",
    )
    _, literal_snapshot = _load_extra_pinned_file(
        repository_root,
        limits,
        RULE_LITERAL_AUTHORITY_RELATIVE_PATH,
        RULE_LITERAL_AUTHORITY_OCTETS,
        RULE_LITERAL_AUTHORITY_SHA256,
        "rule-literal authority",
    )
    source_path = pathlib.Path(__file__).resolve()
    expected_source = repository_root / (
        "scripts/tests/verify_raw_v8_step2_maximum_protocol_v2_"
        "all_case_candidate_v49f.py"
    )
    _require(
        source_path == expected_source,
        "AUTHORITY_INVALID",
        "versioned verifier source path differs",
    )
    _, source_snapshot = _snapshot_file(
        source_path,
        limits,
        "versioned verifier source",
    )

    snapshots = tuple(
        [contract_snapshot]
        + authority_snapshots
        + [runtime_snapshot, registry_snapshot, literal_snapshot, source_snapshot]
    )
    _require(
        len(snapshots) <= limits["INPUT_FILE_COUNT"],
        "INPUT_LIMIT_EXCEEDED",
        "V0 authority file count exceeds F0",
    )
    pinned_octets = _recheck_snapshots(snapshots)
    _require(
        pinned_octets <= limits["TOTAL_PINNED_INPUT_OCTETS"],
        "INPUT_LIMIT_EXCEEDED",
        "V0 authority bytes exceed F0",
    )
    runtime_module, runtime, runtime_report = _load_pinned_runtime(
        repository_root,
        runtime_raw,
        runtime_snapshot["path"],
    )
    _require(
        _recheck_snapshots(snapshots) == pinned_octets,
        "INPUT_RACE_DETECTED",
        "V0 authority footprint drifted during runtime load",
    )
    return Foundation(
        repository_root=repository_root,
        boundary_path=boundary_path,
        contract=contract,
        values=values,
        case_records=records,
        cases=cases,
        plans=plans,
        runtime_module=runtime_module,
        runtime=runtime,
        runtime_report=runtime_report,
        authority_snapshots=snapshots,
        f0_limits=limits,
        pinned_input_octets=pinned_octets,
    )


def _foundation_recheck(foundation: Foundation) -> None:
    _require(
        _recheck_snapshots(foundation.authority_snapshots)
        == foundation.pinned_input_octets,
        "INPUT_RACE_DETECTED",
        "V0 authority footprint changed",
    )


def _resolve_case_and_plan(
    foundation: Foundation,
    case_position: int,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    _require(
        _is_int(case_position) and 1 <= case_position <= CASE_COUNT,
        "CASE_UNSUPPORTED",
        "case position is outside the frozen universe",
    )
    index = case_position - 1
    record = foundation.case_records[index]
    case = foundation.cases[index]
    plan = foundation.plans[index]
    _require(
        record["case_position"] == case["case_position"] == plan["case_position"],
        "AUTHORITY_INVALID",
        "resolved case/plan position differs",
    )
    return record, case, plan


def _validate_typed_value(
    foundation: Foundation,
    type_name: str,
    value: Any,
) -> str:
    _foundation_recheck(foundation)
    try:
        return foundation.runtime.validate_type(type_name, value)
    except Exception as error:
        runtime_failure = foundation.runtime_module.RuntimeFailure
        if isinstance(error, runtime_failure):
            raise
        _reject(
            "TYPED_RUNTIME_INVALID",
            f"typed validation failed closed: {type(error).__name__}: {error}",
        )


def _evaluate_rule_ast(
    foundation: Foundation,
    rule_id: str,
    bindings: dict[str, Any],
    *,
    require_true: bool = True,
) -> Any:
    _foundation_recheck(foundation)
    try:
        return foundation.runtime.evaluate_rule(
            rule_id,
            bindings,
            require_true=require_true,
        )
    except Exception as error:
        runtime_failure = foundation.runtime_module.RuntimeFailure
        if isinstance(error, runtime_failure):
            raise
        _reject(
            "TYPED_RUNTIME_INVALID",
            f"rule-AST execution failed closed: {type(error).__name__}: {error}",
        )


def _foundation_report(foundation: Foundation) -> dict[str, Any]:
    family_counts: dict[str, int] = {}
    for record in foundation.case_records:
        family = record["execution_family"]
        family_counts[family] = family_counts.get(family, 0) + 1
    return {
        "source_marker": SOURCE_MARKER,
        "packet": PACKET,
        "acceptance_scope": "AUTHORITY_AND_TYPED_RULE_FOUNDATION_ONLY",
        "all_case_campaign_contract_id": CONTRACT_ID,
        "case_count": len(foundation.case_records),
        "execution_family_counts": family_counts,
        "case435_effective_plan_id": foundation.plans[CASE435_POSITION - 1][
            "logical_count_plan_id"
        ],
        "all_other_cases_resolve_to_base_seed": True,
        "typed_runtime_sha256": RUNTIME_SHA256,
        "typed_runtime_rule_count": foundation.runtime_report[
            "executable_rule_count"
        ],
        "typed_runtime_application_count": foundation.runtime_report[
            "executable_application_count"
        ],
        "authority_file_count": len(foundation.authority_snapshots),
        "pinned_input_octets": foundation.pinned_input_octets,
        "candidate_access_state": "FORBIDDEN_IN_V0",
        "accepted_constructive_case_count": 0,
        "next_bounded_packet": "A4-R475-V1",
        "formal_stage1_state": "NO-GO",
    }


def _lexical_cli_path(value: str, label: str) -> pathlib.Path:
    path = pathlib.Path(value)
    _require(path.is_absolute(), "INVOCATION_INVALID", f"{label} must be absolute")
    _require(
        path == pathlib.Path(os.path.abspath(os.fspath(path))),
        "INVOCATION_INVALID",
        f"{label} must be lexically canonical",
    )
    _require(
        all(part not in {"", ".", ".."} for part in path.parts[1:]),
        "INVOCATION_INVALID",
        f"{label} has a forbidden component",
    )
    return path


def _arguments(argv: list[str]) -> tuple[pathlib.Path, ...]:
    flags = [
        "--repository-root",
        "--boundary",
        "--candidate-root",
        "--output-root",
    ]
    _require(
        len(argv) == 8 and argv[::2] == flags,
        "INVOCATION_INVALID",
        "expected four fixed-order option/value pairs",
    )
    return tuple(
        _lexical_cli_path(value, flag[2:])
        for flag, value in zip(flags, argv[1::2], strict=True)
    )


def _verify_foundation_only(
    repository_root: pathlib.Path,
    boundary_path: pathlib.Path,
    candidate_root: pathlib.Path,
    output_root: pathlib.Path,
) -> NoReturn:
    del candidate_root, output_root
    foundation = _load_foundation(repository_root, boundary_path)
    _foundation_recheck(foundation)
    _reject(
        "FOUNDATION_ONLY",
        "A4-R475-V0 accepts no case and did not open candidate or output paths",
    )


def _entrypoint(argv: list[str]) -> int:
    try:
        arguments = _arguments(argv)
        _verify_foundation_only(*arguments)
    except VerifierReject as error:
        sys.stderr.write(f"{ERROR_PREFIX}{error.code}: {error.message}\n")
        return 2 if error.code == "INVOCATION_INVALID" else 1
    except Exception as error:
        message = f"{type(error).__name__}: {error}".replace("\n", " ").replace(
            "\r", " "
        )[:768]
        sys.stderr.write(f"{ERROR_PREFIX}INTERNAL_FAIL_CLOSED: {message}\n")
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(_entrypoint(sys.argv[1:]))

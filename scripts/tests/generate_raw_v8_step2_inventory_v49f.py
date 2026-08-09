#!/usr/bin/env python3
"""Generate or check the independent Raw-V8 Step-2 V3 golden inventory.

This generator deliberately uses only the Python standard library and the
four normative Markdown inputs plus the pinned standalone External Schema V2
registry.  It must never import ``riskyieldmm`` or any Raw V8 production
module: the resulting JSON is the independent byte authority against which
the implementation is tested.

Write mode is an offline, single-writer publication operation. Directory-fd
and identity checks reject observed namespace drift, but they are not a lock
against an uncooperative process with concurrent mutation rights on the same
repository directories. Such a workspace is not an admissible publication
environment.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import secrets
import stat
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Final

INVENTORY_SCHEMA_VERSION: Final = "riskyieldmm.raw_v8_step2_inventory.v3"
MEASUREMENT_SCHEMA_VERSION: Final = "riskyieldmm_physical_transport_a2m_raw_v49f_v8"
CANONICALIZATION_VERSION: Final = "riskyieldmm_canonical_json_v1"
PROTOCOL_PATH: Final = (
    "docs/research/v4_9f_a2_marker_operation_target_v8_protocol_freeze_2026-07-22.md"
)
STEP2_V2_FREEZE_PATH: Final = (
    "docs/research/v4_9f_a2_raw_v8_step2_v2_contract_freeze_2026-07-26.md"
)
STEP2_EXTERNAL_SCHEMA_V2_CORRECTION_PATH: Final = (
    "docs/research/v4_9f_a2_raw_v8_step2_external_schema_v2_correction_2026-07-28.md"
)
STEP3_CORRECTION_PATH: Final = (
    "docs/research/v4_9f_a2_raw_v8_step3_target_and_lifecycle_correction_2026-07-26.md"
)
NORMATIVE_DOCUMENT_INPUTS: Final = (
    ("PARENT_MARKER_OPERATION_TARGET_PROTOCOL", PROTOCOL_PATH),
    ("STEP2_V2_CONTRACT_FREEZE", STEP2_V2_FREEZE_PATH),
    (
        "STEP2_EXTERNAL_SCHEMA_V2_CORRECTION",
        STEP2_EXTERNAL_SCHEMA_V2_CORRECTION_PATH,
    ),
    ("STEP3_TARGET_AND_LIFECYCLE_CORRECTION", STEP3_CORRECTION_PATH),
)
MAXIMUM_NORMATIVE_DOCUMENT_OCTETS: Final = 1_048_576
DEFAULT_OUTPUT: Final = "tests/raw_v8_step2_inventory_v49f.json"
STRUCTURAL_REGISTRY_PATH: Final = (
    "scripts/tests/raw_v8_step2_external_schema_v2_structural_registry_v49f.json"
)
STRUCTURAL_REGISTRY_SHA256: Final = (
    "9160297ff316c5931737c92f8b359f0a1e2ec22f0aa996ef3b09cf830dc96bf3"
)
STRUCTURAL_REGISTRY_OCTET_COUNT: Final = 1_469_663
STRUCTURAL_REGISTRY_EXCLUSIVE_OCTET_LIMIT: Final = 16_777_216
STRUCTURAL_REGISTRY_ID: Final = (
    "5dc95a3e99c5646e912b6a7e9c3970cf2489d560ea890b0a19d38af4c51c2140"
)
STRUCTURAL_REGISTRY_PROFILE: Final = "riskyieldmm_raw_v8_step2_external_schema_v2"
STRUCTURAL_REGISTRY_DOMAIN: Final = (
    "RiskYieldMMA2MStep2ExternalSchemaRegistryV2V4_9F_RawV8"
)
STRUCTURAL_REGISTRY_MAXIMUM_JSON_NESTING_DEPTH: Final = 16
STRUCTURAL_REGISTRY_KEYS: Final = frozenset(
    {
        "ascii_dfa_catalog",
        "canonicalization_version",
        "cross_field_rule_descriptor_count",
        "external_schema_profile",
        "external_schema_registry_id",
        "external_type_descriptor_count",
        "fixed_position_resolver_profile_catalog",
        "identifier_profile_catalog",
        "measurement_schema_version",
        "ordered_cross_field_rule_descriptors",
        "ordered_external_type_descriptors",
        "ordered_rule_application_descriptors",
        "ordered_schema_graph_node_names",
        "record_domain",
        "rule_application_descriptor_count",
        "schema_graph_node_count",
        "text_language_catalog",
        "unicode_source_catalog",
        "value_schema_catalog",
    }
)
STRUCTURAL_REGISTRY_IDENTITY_PAYLOAD_ORDER: Final = (
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
FOUNDATION_LEDGER_PATH: Final = (
    "scripts/tests/raw_v8_step2_external_schema_v2_core_ledger_v49f.json"
)
FOUNDATION_LEDGER_SHA256: Final = (
    "fc2b888559067fddb5178a87bcae3ab4876e5c17fab766da6ce54581eeff34fb"
)
FOUNDATION_LEDGER_OCTET_COUNT: Final = 10_811
FOUNDATION_LEDGER_VERSION: Final = (
    "riskyieldmm.raw_v8_step2_external_schema_v2.foundation_ledger.v1"
)
FOUNDATION_COMPONENT_STATUS: Final = "FOUNDATION_ONLY_NOT_EXTERNAL_SCHEMA_REGISTRY_V2"
FOUNDATION_MAXIMUM_JSON_NESTING_DEPTH: Final = 16
SAFE_UINT_MAX: Final = 9_007_199_254_740_991
UINT128_MAX_TEXT: Final = "340282366920938463463374607431768211455"
TARGET_OBSERVATION_MAX_BYTES: Final = 262_144
OPERATION_RESULT_MAX_BYTES: Final = 524_288

FOUNDATION_SOURCE_DOMAIN: Final = "RiskYieldMMA2MStep2UnicodeSourceRecordV1V4_9F_RawV8"
FOUNDATION_PROFILE_DOMAIN: Final = (
    "RiskYieldMMA2MStep2UnicodeIdentifierProfileV1V4_9F_RawV8"
)
FOUNDATION_SOURCE_PAYLOAD_ORDER: Final = (
    "source_name",
    "unicode_version",
    "official_url",
    "byte_count",
    "sha256",
)
FOUNDATION_PROFILE_PAYLOAD_ORDER: Final = (
    "profile_id",
    "unicode_version",
    "normalization_form",
    "maximum_scalar_values",
    "maximum_utf8_octets",
    "forbidden_code_point_ranges",
    "edge_trim_code_points",
    "unicode_source_record_ids",
)
FOUNDATION_PROFILE_SPEC_ORDER: Final = (
    "profile_id",
    "unicode_version",
    "normalization_form",
    "maximum_scalar_values",
    "maximum_utf8_octets",
    "forbidden_code_point_ranges",
    "edge_trim_code_points",
    "unicode_source_names",
)
FOUNDATION_SURFACE_ASSIGNMENT_ORDER: Final = (
    "surface_position",
    "type_name",
    "typed_member_path",
    "value_location",
    "nullable",
    "profile_id",
)
FOUNDATION_EDGE_TRIM_CODE_POINTS: Final = (
    "U+0009",
    "U+000A",
    "U+000B",
    "U+000C",
    "U+000D",
    "U+001C",
    "U+001D",
    "U+001E",
    "U+001F",
    "U+0020",
    "U+0085",
    "U+00A0",
    "U+1680",
    "U+2000",
    "U+2001",
    "U+2002",
    "U+2003",
    "U+2004",
    "U+2005",
    "U+2006",
    "U+2007",
    "U+2008",
    "U+2009",
    "U+200A",
    "U+2028",
    "U+2029",
    "U+202F",
    "U+205F",
    "U+3000",
)
FOUNDATION_PROFILE_LIMITS: Final = {
    "RAW_V8_UNICODE_IDENTIFIER_A_V1": (128, 128, 5),
    "RAW_V8_UNICODE_IDENTIFIER_B_V1": (256, 256, 4),
    "RAW_V8_UNICODE_IDENTIFIER_C_V1": (256, 1_024, 1),
}

DOMAINS: Final = {
    "operation_declaration": "RiskYieldMMA2MOperationDeclarationV4_9F_RawV8",
    "operation_spec": "RiskYieldMMA2MOperationSpecV4_9F_RawV8",
    "operation_result": "RiskYieldMMA2MOperationResultEvidenceV4_9F_RawV8",
    "dispatch_window": "RiskYieldMMA2MDispatchWindowEvidenceV4_9F_RawV8",
    "due_decision_clock": "RiskYieldMMA2MDueDecisionClockEvidenceV4_9F_RawV8",
    "target_registry": "RiskYieldMMA2MTargetFieldRegistryV4_9F_RawV8",
    "field_observation": "RiskYieldMMA2MTargetFieldObservationV4_9F_RawV8",
    "source_error_detail": "RiskYieldMMA2MSourceErrorDetailV4_9F_RawV8",
    "observation_context": "RiskYieldMMA2MTargetObservationContextV2V4_9F_RawV8",
    "target_observation": "RiskYieldMMA2MTargetObservationV2V4_9F_RawV8",
    "target_observation_root": "RiskYieldMMA2MTargetObservationRootV2V4_9F_RawV8",
    "counter_schema": ("RiskYieldMMA2MOperationCounterSnapshotSchemaV4_9F_RawV8"),
    "oracle_profile": ("RiskYieldMMA2MIngressLogicalOracleProfileV1V4_9F_RawV8"),
    "marker_contract": "RiskYieldMMA2MMarkerContractV1V4_9F_RawV8",
    "checkpoint_selector_entry": ("RiskYieldMMA2MCheckpointSelectorEntryV1V4_9F_RawV8"),
    "checkpoint_selector": "RiskYieldMMA2MCheckpointSelectorV1V4_9F_RawV8",
    "external_type_descriptor": (
        "RiskYieldMMA2MStep2ExternalTypeDescriptorV1V4_9F_RawV8"
    ),
}

OPERATION_KINDS: Final = (
    "ACK_DEADLINE_EXPIRY",
    "INGRESS",
    "LOCAL_SHUTDOWN",
    "SUBSCRIPTION_DISPATCH",
)
OBSERVATION_ROLES: Final = (
    "AFTER_OPERATION",
    "BEFORE_OPERATION",
    "OPERATION_AGGREGATE",
    "STABLE_CHECKPOINT",
    "STARTUP_RECOVERY",
)
ROLE_ALIASES: Final = {
    "A": "AFTER_OPERATION",
    "B": "BEFORE_OPERATION",
    "C": "STABLE_CHECKPOINT",
    "G": "OPERATION_AGGREGATE",
    "R": "STARTUP_RECOVERY",
}

AVAILABILITIES: Final = (
    "AVAILABLE",
    "CENSORED",
    "NOT_APPLICABLE",
    "UNAVAILABLE",
)
OBSERVATION_ATTEMPTS: Final = ("ATTEMPTED", "NOT_ATTEMPTED")
SOURCE_FAILURE_PHASES: Final = (
    "FIRST_CLOCK_READ",
    "NONE",
    "SECOND_CLOCK_READ",
    "SOURCE_ADAPTER",
    "VALUE_VALIDATION",
)
ADAPTER_SPAN_STATUSES: Final = (
    "AVAILABLE",
    "NOT_APPLICABLE",
    "UNAVAILABLE",
)
CLOCK_SPAN_STATUSES: Final = ("AVAILABLE", "UNAVAILABLE")
CLOCK_DOMAINS: Final = ("BOOTTIME", "EVENT_LOOP", "OBSERVER_MONOTONIC")
INSTRUMENTATION_MODES: Final = ("OFF", "ON")
CENSORING_VALUES: Final = ("INTERVAL", "LEFT", "NONE", "RIGHT")
VALUE_KINDS: Final = (
    "BOOL",
    "DURATION_BOUND",
    "FIXED_UINT_MAP",
    "OPTIONAL_TEXT",
    "OPTIONAL_UINT",
    "TEXT",
    "TEXT_LIST",
    "UINT",
    "UINT_LIST",
)
DURATION_RELATIONS: Final = (
    "EXACT",
    "INTERVAL",
    "LOWER_BOUND",
    "UPPER_BOUND",
)
ERROR_FORMS: Final = ("NONE", "NON_OS", "OS", "STATUS_ONLY")

A1_ADMISSION_OUTCOMES: Final = (
    "CANCELLED_BEFORE_ENTRY",
    "CLOSED_BEFORE_ENTRY",
    "FAILED_BEFORE_ENTRY",
    "GRANTED",
    "INTERRUPTED_BEFORE_ENTRY",
    "REJECTED",
    "TIMED_OUT",
    "UNRESOLVED_PROCESS_LOSS",
)
A1_REJECTION_CLASSES: Final = (
    "CANCELLED_BEFORE_ENTRY",
    "CAPACITY_REJECTED",
    "CLOSED_BEFORE_ENTRY",
    "DUPLICATE_KIND_REJECTED",
    "FAILED_BEFORE_ENTRY",
    "INTERRUPTED_BEFORE_ENTRY",
    "TERMINAL_BARRIER_REJECTED",
    "TIMED_OUT",
)
SQLITE_RESULT_CLASSES: Final = (
    "BUSY",
    "FULL",
    "INTERRUPT",
    "IOERR",
    "LOCKED",
    "NOMEM",
    "OK",
    "OTHER",
)
SQLITE_PRIMARY_RESULTS: Final = tuple(
    sorted(
        [
            f"{stage}.{result}"
            for stage in ("BEGIN", "BODY", "COMMIT")
            for result in SQLITE_RESULT_CLASSES
        ]
        + ["NONE"]
    )
)
SQLITE_STAGE_RESULTS: Final = tuple(
    sorted(
        f"{stage}.{result}"
        for stage in ("BEGIN", "BODY", "COMMIT", "ROLLBACK")
        for result in SQLITE_RESULT_CLASSES
    )
)
GC_GENERATION_KEYS: Final = ("GENERATION_0", "GENERATION_1", "GENERATION_2")

ACTOR_KIND_KEYS: Final = (
    "ACK_DEADLINE_EXPIRED",
    "APPLICATION_MESSAGE_COMMITTED",
    "KERNEL_SEND_ATTEMPT",
    "KERNEL_SEND_FAILURE",
    "KERNEL_SEND_RESULT",
    "LOCAL_SHUTDOWN_COMMAND_STARTED",
    "LOCAL_SHUTDOWN_DEADLINE_EVIDENCE",
    "OUTBOUND_DISPATCH_COMPLETED",
    "OUTBOUND_WIRE_PREPARED",
    "PARSER_TRANSITION",
    "RAW_INGRESS_COMMITTED",
    "SUBSCRIPTION_ACK_BOUND",
    "TCP_HALF_CLOSE_ATTEMPT",
    "TCP_HALF_CLOSE_RESULT",
    "TERMINAL_INGRESS_FAILURE",
    "TERMINAL_TRANSITION",
    "TLS_CIPHERTEXT_PREPARED",
    "TLS_CONTROL_CIPHERTEXT_PREPARED",
    "TLS_CONTROL_KERNEL_SEND_ATTEMPT",
    "TLS_CONTROL_KERNEL_SEND_FAILURE",
    "TLS_CONTROL_KERNEL_SEND_RESULT",
    "TLS_PROTOCOL_OPERATION_FAILED",
    "TLS_PROTOCOL_OPERATION_STARTED",
    "TLS_SHUTDOWN_OBSERVED",
    "WRITE_PERMIT_CONSUMED",
)

STATUS_REASONS: Final = (
    "ARTIFACT_BOUND_EXCEEDED",
    "CHECKPOINT_PLACEHOLDER_ARTIFACT_BOUND_EXCEEDED",
    "CHECKPOINT_PLACEHOLDER_OBSERVER_INTERNAL_ERROR",
    "CHECKPOINT_PLACEHOLDER_SOURCE_CLOCK_UNAVAILABLE",
    "CHECKPOINT_PLACEHOLDER_TARGET_BOUNDARY_NOT_REACHED",
    "INSTRUMENTATION_DISABLED",
    "MARKER_RING_OVERWROTE_PREFIX",
    "NOT_APPLICABLE_TO_OPERATION",
    "NOT_APPLICABLE_TO_REACHED_STATE",
    "NO_FROZEN_PRESSURE_POLICY",
    "NO_STABLE_SLOW_CALLBACK_SOURCE",
    "OBSERVATION_WOULD_MUTATE_TARGET",
    "OBSERVATION_WOULD_REENTER_ACTIVE_SQLITE_TRANSACTION",
    "OBSERVATION_WOULD_REENTER_TARGET_LOCK",
    "OBSERVER_INTERNAL_ERROR",
    "OS_OBSERVATION_ERROR",
    "PERIODIC_PROBE_DID_NOT_FIRE",
    "PERMISSION_DENIED",
    "PROBE_RING_OVERWROTE_PREFIX",
    "PROCESS_LOSS_VOLATILE_MARKER_STATE",
    "SOURCE_CLOCK_UNAVAILABLE",
    "SOURCE_COUNTER_NOT_INSTRUMENTED",
    "SOURCE_DURABLE_RECORD_ABSENT",
    "TARGET_BOUNDARY_NOT_REACHED",
    "UNSUPPORTED_BY_KERNEL",
    "UNSUPPORTED_BY_PYTHON_RUNTIME",
)

UNAVAILABILITY_PROFILES: Final = {
    "U_OWNER": {
        "INSTRUMENTATION_DISABLED",
        "TARGET_BOUNDARY_NOT_REACHED",
        "UNSUPPORTED_BY_PYTHON_RUNTIME",
        "OBSERVER_INTERNAL_ERROR",
        "OBSERVATION_WOULD_MUTATE_TARGET",
        "OBSERVATION_WOULD_REENTER_TARGET_LOCK",
        "PROCESS_LOSS_VOLATILE_MARKER_STATE",
        "SOURCE_DURABLE_RECORD_ABSENT",
        "SOURCE_COUNTER_NOT_INSTRUMENTED",
        "SOURCE_CLOCK_UNAVAILABLE",
        "ARTIFACT_BOUND_EXCEEDED",
    },
    "U_OS": set(),
    "U_SQLITE": set(),
    "U_COUNTER": {
        "INSTRUMENTATION_DISABLED",
        "TARGET_BOUNDARY_NOT_REACHED",
        "UNSUPPORTED_BY_PYTHON_RUNTIME",
        "OBSERVER_INTERNAL_ERROR",
        "PROCESS_LOSS_VOLATILE_MARKER_STATE",
        "SOURCE_DURABLE_RECORD_ABSENT",
        "SOURCE_COUNTER_NOT_INSTRUMENTED",
        "SOURCE_CLOCK_UNAVAILABLE",
        "ARTIFACT_BOUND_EXCEEDED",
    },
    "U_LOOP": set(),
    "U_GC": set(),
    "U_MARKER": set(),
    "U_POLICY": {"NO_FROZEN_PRESSURE_POLICY"},
    "U_STATIC": set(),
}
UNAVAILABILITY_PROFILES["U_OS"] = UNAVAILABILITY_PROFILES["U_OWNER"] | {
    "UNSUPPORTED_BY_KERNEL",
    "PERMISSION_DENIED",
    "OS_OBSERVATION_ERROR",
}
UNAVAILABILITY_PROFILES["U_SQLITE"] = UNAVAILABILITY_PROFILES["U_OS"] | {
    "OBSERVATION_WOULD_REENTER_ACTIVE_SQLITE_TRANSACTION"
}
UNAVAILABILITY_PROFILES["U_LOOP"] = UNAVAILABILITY_PROFILES["U_COUNTER"] | {
    "NO_STABLE_SLOW_CALLBACK_SOURCE",
    "PERIODIC_PROBE_DID_NOT_FIRE",
    "PROBE_RING_OVERWROTE_PREFIX",
}
UNAVAILABILITY_PROFILES["U_GC"] = set(UNAVAILABILITY_PROFILES["U_COUNTER"])
UNAVAILABILITY_PROFILES["U_MARKER"] = UNAVAILABILITY_PROFILES["U_COUNTER"] | {
    "MARKER_RING_OVERWROTE_PREFIX"
}

NON_APPLICABLE_REASONS: Final = {
    "NOT_APPLICABLE_TO_OPERATION",
    "NOT_APPLICABLE_TO_REACHED_STATE",
}
STATUS_REASON_POLICY_ID: Final = "RAW_V8_STATUS_REASON_ATTEMPT_ERROR_POLICY_V1"
CROSS_FIELD_CONSTRAINT_ID: Final = "A1_FIFO_SEQUENCE_KIND_LENGTH_AND_ORDER_V1"
NULL_ATTEMPT_DERIVED_PROFILE_SPELLINGS: Final = {
    "P_OP_ACCUM",
    "P_OP_DURABLE",
    "P_SQLITE_OP",
    "P_LOOP_OP",
    "P_LOOP_BOUND",
    "P_PROCESS_CPU(OWNER_THREAD_CPU_CLOCK)",
    "P_PROCESS_CPU(PROCESS_CPU_CLOCK)",
    "P_GC_OP",
    "P_FRESH_UNITS",
    "P_FRESH_LATENCY",
}
NULL_ATTEMPT_EXPLICIT_FIELD_ID: Final = "freshness.target_effect_elapsed_boottime_ns"
OFF_STATIC_AVAILABLE_FIELD_IDS: Final = (
    "loop.probe_interval_ns",
    "process.filesystem_mount_cgroup_identity_id",
    "process.runtime_environment_id",
)


class InventoryError(ValueError):
    """Raised when the protocol cannot produce the exact frozen inventory."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def _semantic_id(domain: str, payload: dict[str, Any]) -> str:
    preimage = {
        "canonicalization_version": CANONICALIZATION_VERSION,
        "domain": domain,
        "payload": payload,
        "schema_version": MEASUREMENT_SCHEMA_VERSION,
    }
    return _sha256_bytes(_canonical_bytes(preimage))


def _standalone_envelope(
    domain: str, payload: dict[str, Any], identity_field: str
) -> dict[str, Any]:
    reserved = {
        "canonicalization_version",
        "measurement_schema_version",
        "record_domain",
        identity_field,
    }
    collisions = sorted(reserved & set(payload))
    _require(
        not collisions,
        "standalone payload collides with envelope/identity members: "
        + ",".join(collisions),
    )
    result = {
        "canonicalization_version": CANONICALIZATION_VERSION,
        "measurement_schema_version": MEASUREMENT_SCHEMA_VERSION,
        "record_domain": domain,
        **payload,
    }
    result[identity_field] = _semantic_id(domain, payload)
    return result


def _standalone_envelope_collision_guard_self_test() -> dict[str, Any]:
    identity_field = "self_test_id"
    guarded_members = (
        "canonicalization_version",
        "measurement_schema_version",
        "record_domain",
        identity_field,
    )
    rejected: list[str] = []
    for member in guarded_members:
        try:
            _standalone_envelope(
                "RiskYieldMMA2MStandaloneEnvelopeCollisionSelfTestV1",
                {member: "collision"},
                identity_field,
            )
        except InventoryError:
            rejected.append(member)
        else:
            raise InventoryError(
                f"standalone envelope accepted reserved payload member: {member}"
            )
    return {
        "guarded_payload_members": list(guarded_members),
        "rejected_collision_members": rejected,
        "all_reserved_member_collisions_reject": rejected == list(guarded_members),
    }


def _fixture_id(label: str) -> str:
    return _sha256_text(f"riskyieldmm.raw-v8-step2.fixture:{label}")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise InventoryError(message)


def _repository_relative_parts(relative_path: str) -> tuple[str, ...]:
    _require(type(relative_path) is str, "repository input path is not exact text")
    path = Path(relative_path)
    _require(
        not path.is_absolute()
        and relative_path == path.as_posix()
        and path.parts
        and all(part not in {"", ".", ".."} for part in path.parts),
        f"repository input path is not an exact relative POSIX path: {relative_path}",
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
    except (InventoryError, OSError) as exc:
        if descriptor is not None:
            os.close(descriptor)
        if isinstance(exc, InventoryError):
            raise
        raise InventoryError(f"cannot securely open {label} parent") from exc


def _directory_fd_fingerprint(descriptor: int) -> tuple[int, int, int]:
    metadata = os.fstat(descriptor)
    _require(stat.S_ISDIR(metadata.st_mode), "repository path is not a directory")
    return (metadata.st_dev, metadata.st_ino, metadata.st_mode)


def _current_repository_directory_fingerprint(
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
        return _directory_fd_fingerprint(descriptor)
    finally:
        os.close(descriptor)


def _bounded_repository_read(
    repository_root: Path,
    relative_path: str,
    *,
    maximum_octets: int,
    exclusive: bool = False,
    expected_octets: int | None = None,
    expected_sha256: str | None = None,
) -> bytes:
    _require(
        type(maximum_octets) is int and maximum_octets > 0,
        "repository input byte bound is invalid",
    )
    relative_parts = _repository_relative_parts(relative_path)
    parent_descriptor = _open_repository_directory_fd(
        repository_root,
        relative_parts[:-1],
        label=f"repository input {relative_path}",
    )
    parent_fingerprint = _directory_fd_fingerprint(parent_descriptor)
    flags = os.O_RDONLY | os.O_NONBLOCK
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        try:
            descriptor = os.open(
                relative_parts[-1],
                flags,
                dir_fd=parent_descriptor,
            )
        except OSError as exc:
            raise InventoryError(
                f"cannot securely open repository input: {relative_path}"
            ) from exc
        try:
            before = os.fstat(descriptor)
            _require(
                stat.S_ISREG(before.st_mode),
                f"repository input is not a regular file: {relative_path}",
            )
            hard_limit = maximum_octets - 1 if exclusive else maximum_octets
            _require(
                before.st_size <= hard_limit,
                f"repository input exceeds its byte bound: {relative_path}",
            )
            if expected_octets is not None:
                _require(
                    before.st_size == expected_octets,
                    f"repository input byte count differs: {relative_path}",
                )
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = os.read(descriptor, min(65_536, hard_limit + 1 - total))
                if not chunk:
                    break
                total += len(chunk)
                _require(
                    total <= hard_limit,
                    f"repository input exceeds its byte bound: {relative_path}",
                )
                chunks.append(chunk)
            after = os.fstat(descriptor)
            _require(
                (
                    before.st_dev,
                    before.st_ino,
                    before.st_mode,
                    before.st_size,
                    before.st_mtime_ns,
                    before.st_ctime_ns,
                )
                == (
                    after.st_dev,
                    after.st_ino,
                    after.st_mode,
                    after.st_size,
                    after.st_mtime_ns,
                    after.st_ctime_ns,
                ),
                f"repository input changed during read: {relative_path}",
            )
        finally:
            os.close(descriptor)
        raw = b"".join(chunks)
        _require(
            len(raw) == before.st_size,
            f"repository input was truncated during read: {relative_path}",
        )
        try:
            after_path = os.stat(
                relative_parts[-1],
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except OSError as exc:
            raise InventoryError(
                f"repository input disappeared after read: {relative_path}"
            ) from exc
        _require(
            stat.S_ISREG(after_path.st_mode)
            and (after_path.st_dev, after_path.st_ino, after_path.st_size)
            == (before.st_dev, before.st_ino, before.st_size),
            f"repository input identity changed during read: {relative_path}",
        )
        if expected_sha256 is not None:
            _require(
                _sha256_bytes(raw) == expected_sha256,
                f"repository input SHA-256 differs: {relative_path}",
            )
        _require(
            _current_repository_directory_fingerprint(
                repository_root,
                relative_parts[:-1],
                label=f"repository input {relative_path}",
            )
            == parent_fingerprint,
            f"repository input parent identity changed during read: {relative_path}",
        )
        return raw
    finally:
        os.close(parent_descriptor)


def _reject_controlled_json_constant(value: str) -> Any:
    raise InventoryError(f"controlled JSON contains non-finite value: {value}")


def _reject_controlled_json_float(value: str) -> Any:
    raise InventoryError(f"controlled JSON contains a float: {value}")


def _strict_controlled_json_object(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InventoryError(f"controlled JSON contains duplicate key: {key}")
        result[key] = value
    return result


def _scan_controlled_json_nesting(text: str, *, maximum_depth: int) -> None:
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


def _validate_controlled_json_scalars(value: Any) -> None:
    stack = [value]
    while stack:
        current = stack.pop()
        if type(current) is dict:
            stack.extend(current.keys())
            stack.extend(current.values())
        elif type(current) is list:
            stack.extend(current)
        elif type(current) is str:
            _require(
                not any(0xD800 <= ord(character) <= 0xDFFF for character in current),
                "controlled JSON contains a non-scalar string",
            )
        else:
            _require(
                current is None
                or type(current) is bool
                or (
                    type(current) is int and -SAFE_UINT_MAX <= current <= SAFE_UINT_MAX
                ),
                "controlled JSON scalar is outside the exact I-JSON subset",
            )


def _load_structural_registry(repository_root: Path) -> dict[str, Any]:
    raw = _bounded_repository_read(
        repository_root,
        STRUCTURAL_REGISTRY_PATH,
        maximum_octets=STRUCTURAL_REGISTRY_EXCLUSIVE_OCTET_LIMIT,
        exclusive=True,
        expected_octets=STRUCTURAL_REGISTRY_OCTET_COUNT,
        expected_sha256=STRUCTURAL_REGISTRY_SHA256,
    )
    try:
        text = raw.decode("utf-8", errors="strict")
        _scan_controlled_json_nesting(
            text,
            maximum_depth=STRUCTURAL_REGISTRY_MAXIMUM_JSON_NESTING_DEPTH,
        )
        registry = json.loads(
            text,
            object_pairs_hook=_strict_controlled_json_object,
            parse_constant=_reject_controlled_json_constant,
            parse_float=_reject_controlled_json_float,
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        InventoryError,
        RecursionError,
    ) as exc:
        raise InventoryError(
            "external-schema V2 structural registry is not controlled JSON"
        ) from exc
    _require(type(registry) is dict, "structural registry root is not an object")
    _validate_controlled_json_scalars(registry)
    _require(
        _canonical_pretty_bytes(registry) == raw,
        "structural registry is not canonical pretty JSON",
    )
    _require(
        frozenset(registry) == STRUCTURAL_REGISTRY_KEYS,
        "structural registry root shape differs",
    )
    _require(
        registry["canonicalization_version"] == CANONICALIZATION_VERSION
        and registry["measurement_schema_version"] == MEASUREMENT_SCHEMA_VERSION
        and registry["record_domain"] == STRUCTURAL_REGISTRY_DOMAIN
        and registry["external_schema_profile"] == STRUCTURAL_REGISTRY_PROFILE,
        "structural registry envelope identity differs",
    )
    expected_counts = {
        "external_type_descriptor_count": 52,
        "cross_field_rule_descriptor_count": 42,
        "rule_application_descriptor_count": 8,
        "schema_graph_node_count": 52,
    }
    for count_member, expected_count in expected_counts.items():
        _require(
            type(registry[count_member]) is int
            and registry[count_member] == expected_count,
            f"structural registry {count_member} differs",
        )
    catalog_bindings = (
        ("external_type_descriptor_count", "ordered_external_type_descriptors"),
        ("cross_field_rule_descriptor_count", "ordered_cross_field_rule_descriptors"),
        ("rule_application_descriptor_count", "ordered_rule_application_descriptors"),
        ("schema_graph_node_count", "ordered_schema_graph_node_names"),
    )
    for count_member, catalog_member in catalog_bindings:
        _require(
            type(registry[catalog_member]) is list
            and len(registry[catalog_member]) == registry[count_member],
            f"structural registry {catalog_member} cardinality differs",
        )
    descriptor_names = [
        descriptor.get("type_name") if type(descriptor) is dict else None
        for descriptor in registry["ordered_external_type_descriptors"]
    ]
    _require(
        descriptor_names == registry["ordered_schema_graph_node_names"]
        and descriptor_names == sorted(descriptor_names),
        "structural registry graph-node ledger differs from descriptor order",
    )
    payload = {
        member: registry[member]
        for member in STRUCTURAL_REGISTRY_IDENTITY_PAYLOAD_ORDER
    }
    recomputed_id = _semantic_id(STRUCTURAL_REGISTRY_DOMAIN, payload)
    _require(
        registry["external_schema_registry_id"] == STRUCTURAL_REGISTRY_ID
        and recomputed_id == STRUCTURAL_REGISTRY_ID,
        "structural registry semantic identity differs",
    )
    return registry


def _revalidate_source_snapshot(
    repository_root: Path,
    *,
    normative_bytes: dict[str, bytes],
    structural_registry: dict[str, Any],
) -> None:
    _require(
        tuple(normative_bytes) == tuple(path for _, path in NORMATIVE_DOCUMENT_INPUTS),
        "normative source snapshot path order differs",
    )
    for _, relative_path in NORMATIVE_DOCUMENT_INPUTS:
        current = _bounded_repository_read(
            repository_root,
            relative_path,
            maximum_octets=MAXIMUM_NORMATIVE_DOCUMENT_OCTETS,
        )
        _require(
            current == normative_bytes[relative_path],
            f"normative document changed during inventory generation: {relative_path}",
        )
    _require(
        _load_structural_registry(repository_root) == structural_registry,
        "structural registry changed during inventory generation",
    )


def _reject_foundation_json_constant(value: str) -> Any:
    raise InventoryError(f"foundation ledger contains non-finite JSON: {value}")


def _reject_foundation_json_float(value: str) -> Any:
    raise InventoryError(f"foundation ledger contains a float: {value}")


def _strict_foundation_json_object(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InventoryError(
                f"foundation ledger contains duplicate JSON key: {key}"
            )
        result[key] = value
    return result


def _validate_foundation_json_nesting(text: str) -> None:
    """Bound JSON nesting before decode while ignoring structure inside strings."""

    depth = 0
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
            continue
        if character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            _require(
                depth <= FOUNDATION_MAXIMUM_JSON_NESTING_DEPTH,
                "foundation ledger JSON nesting exceeds the reviewed bound",
            )
        elif character in "]}":
            depth -= 1
            _require(
                depth >= 0,
                "foundation ledger JSON closes an unopened container",
            )
    _require(not in_string, "foundation ledger contains an unterminated JSON string")
    _require(depth == 0, "foundation ledger JSON has unclosed containers")


def _require_foundation_json_scalar_strings(value: Any) -> None:
    """Reject escaped lone surrogates in every decoded JSON key and value."""

    if type(value) is str:
        _require(
            not any(0xD800 <= ord(character) <= 0xDFFF for character in value),
            "foundation ledger contains a non-scalar JSON string",
        )
    elif type(value) is list:
        for item in value:
            _require_foundation_json_scalar_strings(item)
    elif type(value) is dict:
        for key, item in value.items():
            _require_foundation_json_scalar_strings(key)
            _require_foundation_json_scalar_strings(item)


def _canonical_pretty_bytes(value: Any) -> bytes:
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


def _require_exact_foundation_object(
    value: Any,
    member_order: tuple[str, ...],
    *,
    label: str,
) -> dict[str, Any]:
    _require(type(value) is dict, f"{label} is not an exact object")
    _require(
        set(value) == set(member_order),
        f"{label} has missing or extra members",
    )
    return value


def _expected_foundation_metadata_shapes() -> dict[str, dict[str, Any]]:
    source_payload = list(FOUNDATION_SOURCE_PAYLOAD_ORDER)
    profile_payload = list(FOUNDATION_PROFILE_PAYLOAD_ORDER)
    surface_payload = list(FOUNDATION_SURFACE_ASSIGNMENT_ORDER)
    return {
        "identifier_profile": {
            "identity_field": "unicode_identifier_profile_id",
            "identity_payload_member_order": profile_payload,
            "materialized_member_order": [
                *profile_payload,
                "unicode_identifier_profile_id",
            ],
            "semantic_id_domain": FOUNDATION_PROFILE_DOMAIN,
            "source_spec_member_order": list(FOUNDATION_PROFILE_SPEC_ORDER),
        },
        "surface_assignment": {
            "identity_field": None,
            "identity_payload_member_order": None,
            "materialized_member_order": surface_payload,
            "semantic_id_domain": None,
            "source_spec_member_order": surface_payload,
        },
        "unicode_source": {
            "identity_field": "unicode_source_record_id",
            "identity_payload_member_order": source_payload,
            "materialized_member_order": [
                *source_payload,
                "unicode_source_record_id",
            ],
            "semantic_id_domain": FOUNDATION_SOURCE_DOMAIN,
            "source_spec_member_order": source_payload,
        },
    }


def _load_foundation_ledger(
    repository_root: Path,
) -> tuple[bytes, dict[str, Any]]:
    try:
        raw = _bounded_repository_read(
            repository_root,
            FOUNDATION_LEDGER_PATH,
            maximum_octets=FOUNDATION_LEDGER_OCTET_COUNT,
            expected_octets=FOUNDATION_LEDGER_OCTET_COUNT,
            expected_sha256=FOUNDATION_LEDGER_SHA256,
        )
    except InventoryError as exc:
        detail = str(exc)
        if any(
            marker in detail
            for marker in (
                "exceeds its byte bound",
                "byte count differs",
                "was truncated during read",
            )
        ):
            raise InventoryError(
                "external-schema V2 foundation ledger octet count differs "
                "from the reviewed slice"
            ) from exc
        if "SHA-256 differs" in detail:
            raise InventoryError(
                "external-schema V2 foundation ledger bytes differ from the "
                "reviewed slice"
            ) from exc
        raise
    try:
        text = raw.decode("utf-8")
    except UnicodeError as exc:
        raise InventoryError(f"cannot decode foundation ledger: {exc}") from exc
    _validate_foundation_json_nesting(text)
    try:
        value = json.loads(
            text,
            object_pairs_hook=_strict_foundation_json_object,
            parse_constant=_reject_foundation_json_constant,
            parse_float=_reject_foundation_json_float,
        )
    except (json.JSONDecodeError, InventoryError, RecursionError) as exc:
        raise InventoryError(f"invalid foundation ledger JSON: {exc}") from exc
    _require(type(value) is dict, "foundation ledger root is not an exact object")
    _require_foundation_json_scalar_strings(value)
    try:
        canonical = _canonical_pretty_bytes(value)
    except (UnicodeError, RecursionError, ValueError) as exc:
        raise InventoryError(
            f"cannot canonicalize foundation ledger JSON: {exc}"
        ) from exc
    _require(
        raw == canonical,
        "foundation ledger bytes are not canonical pretty JSON",
    )
    return raw, value


def _foundation_code_point(value: Any) -> int:
    _require(
        type(value) is str and re.fullmatch(r"U\+[0-9A-F]{4,6}", value) is not None,
        "foundation code point is not canonical U+ notation",
    )
    result = int(value[2:], 16)
    _require(
        result <= 0x10FFFF and not 0xD800 <= result <= 0xDFFF,
        "foundation code point is not a Unicode scalar value",
    )
    return result


def _build_external_schema_v2_foundation_report(
    repository_root: Path,
) -> dict[str, Any]:
    raw, ledger = _load_foundation_ledger(repository_root)
    root_order = (
        "canonicalization_version",
        "component_status",
        "foundation_ledger_version",
        "identifier_profile_specs",
        "measurement_schema_version",
        "metadata_shape_declarations",
        "surface_assignments",
        "unicode_source_specs",
    )
    _require_exact_foundation_object(ledger, root_order, label="foundation ledger")
    _require(
        ledger["canonicalization_version"] == CANONICALIZATION_VERSION,
        "foundation canonicalization version differs",
    )
    _require(
        ledger["measurement_schema_version"] == MEASUREMENT_SCHEMA_VERSION,
        "foundation measurement schema version differs",
    )
    _require(
        ledger["foundation_ledger_version"] == FOUNDATION_LEDGER_VERSION,
        "foundation ledger version differs",
    )
    _require(
        ledger["component_status"] == FOUNDATION_COMPONENT_STATUS,
        "foundation component status differs",
    )
    _require(
        ledger["metadata_shape_declarations"] == _expected_foundation_metadata_shapes(),
        "foundation metadata-shape declarations differ",
    )

    source_specs = ledger["unicode_source_specs"]
    _require(
        type(source_specs) is list and len(source_specs) == 6,
        "foundation must contain exactly six Unicode source specs",
    )
    expected_source_names = (
        "CompositionExclusions.txt",
        "DerivedNormalizationProps.txt",
        "NormalizationTest.txt",
        "PropList.txt",
        "ReadMe.txt",
        "UnicodeData.txt",
    )
    source_names = tuple(
        _require_exact_foundation_object(
            spec,
            FOUNDATION_SOURCE_PAYLOAD_ORDER,
            label=f"Unicode source spec {position}",
        )["source_name"]
        for position, spec in enumerate(source_specs, 1)
    )
    _require(
        source_names == expected_source_names,
        "Unicode source specs are not in exact lexical source-name order",
    )
    source_records: list[dict[str, Any]] = []
    source_id_by_name: dict[str, str] = {}
    for spec in source_specs:
        source_name = spec["source_name"]
        _require(type(source_name) is str, "Unicode source name is not exact text")
        _require(
            spec["unicode_version"] == "15.0.0",
            f"Unicode source {source_name} version differs",
        )
        _require(
            spec["official_url"]
            == f"https://www.unicode.org/Public/15.0.0/ucd/{source_name}",
            f"Unicode source {source_name} official URL differs",
        )
        _require(
            type(spec["byte_count"]) is int and 0 < spec["byte_count"] <= SAFE_UINT_MAX,
            f"Unicode source {source_name} byte count is invalid",
        )
        _require(
            type(spec["sha256"]) is str
            and re.fullmatch(r"[0-9a-f]{64}", spec["sha256"]) is not None,
            f"Unicode source {source_name} SHA-256 is invalid",
        )
        payload = {member: spec[member] for member in FOUNDATION_SOURCE_PAYLOAD_ORDER}
        source_id = _semantic_id(FOUNDATION_SOURCE_DOMAIN, payload)
        source_id_by_name[source_name] = source_id
        source_records.append({**payload, "unicode_source_record_id": source_id})

    profile_specs = ledger["identifier_profile_specs"]
    _require(
        type(profile_specs) is list and len(profile_specs) == 3,
        "foundation must contain exactly three identifier profile specs",
    )
    profile_ids = tuple(
        _require_exact_foundation_object(
            spec,
            FOUNDATION_PROFILE_SPEC_ORDER,
            label=f"identifier profile spec {position}",
        )["profile_id"]
        for position, spec in enumerate(profile_specs, 1)
    )
    _require(
        profile_ids == tuple(FOUNDATION_PROFILE_LIMITS),
        "identifier profiles are not in exact A/B/C semantic order",
    )
    expected_forbidden_ranges = [
        ["U+0000", "U+001F"],
        ["U+007F", "U+007F"],
    ]
    profile_records: list[dict[str, Any]] = []
    profile_semantic_id_by_profile_id: dict[str, str] = {}
    for spec in profile_specs:
        profile_id = spec["profile_id"]
        scalar_maximum, octet_maximum, _ = FOUNDATION_PROFILE_LIMITS[profile_id]
        _require(
            spec["unicode_version"] == "15.0.0",
            f"identifier profile {profile_id} Unicode version differs",
        )
        _require(
            spec["normalization_form"] == "NFC",
            f"identifier profile {profile_id} normalization form differs",
        )
        _require(
            type(spec["maximum_scalar_values"]) is int
            and spec["maximum_scalar_values"] == scalar_maximum,
            f"identifier profile {profile_id} scalar maximum differs",
        )
        _require(
            type(spec["maximum_utf8_octets"]) is int
            and spec["maximum_utf8_octets"] == octet_maximum,
            f"identifier profile {profile_id} UTF-8 maximum differs",
        )
        _require(
            spec["forbidden_code_point_ranges"] == expected_forbidden_ranges,
            f"identifier profile {profile_id} forbidden ranges differ",
        )
        edge_trim = spec["edge_trim_code_points"]
        _require(
            type(edge_trim) is list
            and tuple(edge_trim) == FOUNDATION_EDGE_TRIM_CODE_POINTS,
            f"identifier profile {profile_id} edge-trim set differs",
        )
        parsed_trim = tuple(_foundation_code_point(item) for item in edge_trim)
        _require(
            len(parsed_trim) == 29
            and len(set(parsed_trim)) == 29
            and tuple(sorted(parsed_trim)) == parsed_trim,
            f"identifier profile {profile_id} edge-trim set is not exact",
        )
        profile_source_names = spec["unicode_source_names"]
        _require(
            type(profile_source_names) is list
            and tuple(profile_source_names) == expected_source_names,
            f"identifier profile {profile_id} source order differs",
        )
        payload = {
            "profile_id": profile_id,
            "unicode_version": spec["unicode_version"],
            "normalization_form": spec["normalization_form"],
            "maximum_scalar_values": spec["maximum_scalar_values"],
            "maximum_utf8_octets": spec["maximum_utf8_octets"],
            "forbidden_code_point_ranges": spec["forbidden_code_point_ranges"],
            "edge_trim_code_points": edge_trim,
            "unicode_source_record_ids": [
                source_id_by_name[name] for name in profile_source_names
            ],
        }
        _require(
            tuple(payload) == FOUNDATION_PROFILE_PAYLOAD_ORDER,
            f"identifier profile {profile_id} payload order differs",
        )
        semantic_id = _semantic_id(FOUNDATION_PROFILE_DOMAIN, payload)
        profile_semantic_id_by_profile_id[profile_id] = semantic_id
        profile_records.append(
            {**payload, "unicode_identifier_profile_id": semantic_id}
        )

    surface_assignments = ledger["surface_assignments"]
    _require(
        type(surface_assignments) is list and len(surface_assignments) == 10,
        "foundation must contain exactly ten Unicode surface assignments",
    )
    coordinates: list[tuple[str, tuple[str, ...], str]] = []
    for expected_position, assignment in enumerate(surface_assignments, 1):
        assignment = _require_exact_foundation_object(
            assignment,
            FOUNDATION_SURFACE_ASSIGNMENT_ORDER,
            label=f"surface assignment {expected_position}",
        )
        _require(
            type(assignment["surface_position"]) is int
            and assignment["surface_position"] == expected_position,
            "surface assignment positions are not contiguous from one",
        )
        _require(
            type(assignment["type_name"]) is str and bool(assignment["type_name"]),
            f"surface assignment {expected_position} type name is invalid",
        )
        path = assignment["typed_member_path"]
        _require(
            type(path) is list
            and len(path) == 1
            and type(path[0]) is str
            and bool(path[0]),
            f"surface assignment {expected_position} typed path is invalid",
        )
        _require(
            assignment["value_location"] in {"MEMBER_VALUE", "ARRAY_ITEM_VALUE"},
            f"surface assignment {expected_position} value location differs",
        )
        _require(
            type(assignment["nullable"]) is bool,
            f"surface assignment {expected_position} nullability is invalid",
        )
        _require(
            assignment["profile_id"] in FOUNDATION_PROFILE_LIMITS,
            f"surface assignment {expected_position} profile is unknown",
        )
        coordinates.append(
            (
                assignment["type_name"],
                tuple(path),
                assignment["value_location"],
            )
        )
    _require(
        len(set(coordinates)) == 10,
        "foundation Unicode surface coordinates are not unique",
    )
    surface_counts = Counter(
        assignment["profile_id"] for assignment in surface_assignments
    )
    _require(
        {
            profile_id: surface_counts[profile_id]
            for profile_id in FOUNDATION_PROFILE_LIMITS
        }
        == {
            profile_id: limits[2]
            for profile_id, limits in FOUNDATION_PROFILE_LIMITS.items()
        },
        "foundation Unicode surface profile counts differ",
    )
    nullable_coordinates = {
        coordinate
        for coordinate, assignment in zip(coordinates, surface_assignments, strict=True)
        if assignment["nullable"]
    }
    _require(
        nullable_coordinates
        == {
            (
                "CapacityMeasurementOptionalTextValueV1",
                ("value",),
                "MEMBER_VALUE",
            )
        },
        "foundation nullable Unicode surface differs",
    )
    array_item_coordinates = {
        coordinate
        for coordinate, assignment in zip(coordinates, surface_assignments, strict=True)
        if assignment["value_location"] == "ARRAY_ITEM_VALUE"
    }
    _require(
        array_item_coordinates
        == {
            (
                "CapacityMeasurementTextListValueV1",
                ("values",),
                "ARRAY_ITEM_VALUE",
            )
        },
        "foundation array-item Unicode surface differs",
    )

    ordered_source_records = sorted(
        source_records,
        key=lambda item: item["unicode_source_record_id"],
    )
    ordered_profile_records = sorted(
        profile_records,
        key=lambda item: item["unicode_identifier_profile_id"],
    )
    report = {
        "component_status": FOUNDATION_COMPONENT_STATUS,
        "foundation_ledger_sha256": _sha256_bytes(raw),
        "foundation_ledger_version": FOUNDATION_LEDGER_VERSION,
        "identifier_profile_count": len(ordered_profile_records),
        "ordered_unicode_identifier_profile_ids": [
            item["unicode_identifier_profile_id"] for item in ordered_profile_records
        ],
        "ordered_unicode_source_record_ids": [
            item["unicode_source_record_id"] for item in ordered_source_records
        ],
        "profile_semantic_id_by_profile_id": dict(
            sorted(profile_semantic_id_by_profile_id.items())
        ),
        "surface_assignment_count": len(surface_assignments),
        "surface_assignment_count_by_profile_id": {
            profile_id: surface_counts[profile_id]
            for profile_id in FOUNDATION_PROFILE_LIMITS
        },
        "surface_assignments_sha256": _sha256_bytes(
            _canonical_bytes(surface_assignments)
        ),
        "unicode_source_count": len(ordered_source_records),
        "unicode_source_record_id_by_source_name": dict(
            sorted(source_id_by_name.items())
        ),
    }
    report["foundation_component_sha256"] = _sha256_bytes(_canonical_bytes(report))
    return report


def _extract_fenced_tokens(text: str, anchor: str) -> tuple[str, ...]:
    start = text.find(anchor)
    if start < 0:
        raise InventoryError(f"protocol anchor is absent: {anchor!r}")
    opening = text.find("```text", start)
    if opening < 0:
        raise InventoryError(f"text fence is absent after: {anchor!r}")
    body_start = opening + len("```text")
    closing = text.find("```", body_start)
    if closing < 0:
        raise InventoryError(f"text fence is unterminated after: {anchor!r}")
    tokens = tuple(
        line.strip() for line in text[body_start:closing].splitlines() if line.strip()
    )
    if not tokens:
        raise InventoryError(f"empty token fence after: {anchor!r}")
    return tokens


def _normalize_token(value: str) -> str:
    return re.sub(r"[ -]+", "_", value.upper())


def _strip_code(value: str) -> str:
    value = value.strip()
    if value.startswith("`") and value.endswith("`"):
        return value[1:-1]
    return value


def _parse_protocol(text: str) -> dict[str, Any]:
    _require(MEASUREMENT_SCHEMA_VERSION in text, "measurement schema literal drifted")
    _require(CANONICALIZATION_VERSION in text, "canonicalization literal drifted")
    for domain in (
        DOMAINS["operation_declaration"],
        DOMAINS["operation_spec"],
        DOMAINS["operation_result"],
        DOMAINS["dispatch_window"],
        DOMAINS["due_decision_clock"],
        DOMAINS["target_registry"],
        DOMAINS["field_observation"],
        DOMAINS["source_error_detail"],
        DOMAINS["counter_schema"],
    ):
        _require(domain in text, f"record domain is absent from protocol: {domain}")

    methods = tuple(
        sorted(
            _extract_fenced_tokens(
                text,
                "The registry uses only these observation methods, in this exact lexical form:",
            )
        )
    )
    markers = tuple(
        sorted(
            _extract_fenced_tokens(
                text,
                "The exact marker-kind key tuple, serialized in ascending UTF-8 order, is:",
            )
        )
    )
    checkpoint_markers = tuple(
        sorted(
            _extract_fenced_tokens(
                text, "`CP_TARGET` means the exact checkpoint-marker set:"
            )
        )
    )
    reasons = tuple(sorted(_extract_fenced_tokens(text, "The frozen reason enum is:")))
    actor_keys = tuple(
        sorted(
            _extract_fenced_tokens(
                text, "`M_ACTOR_KINDS_25` is the sorted exact tuple:"
            )
        )
    )
    counter_fields = tuple(
        _extract_fenced_tokens(
            text,
            "Bit/position `i` names the same coordinate in this exact ascending UTF-8 tuple:",
        )
    )
    null_attempt_fields = tuple(
        _extract_fenced_tokens(
            text,
            "null value, `censoring=NONE`, and no source-error metadata:",
        )
    )
    compact_point_fields = tuple(
        _extract_fenced_tokens(
            text,
            "The other eight compact coordinates are point/current",
        )
    )

    _require(len(methods) == 32, "protocol must freeze exactly 32 method tokens")
    _require(len(markers) == 19, "protocol must freeze exactly 19 marker kinds")
    _require(
        len(checkpoint_markers) == 13,
        "protocol must freeze exactly 13 checkpoint marker kinds",
    )
    parent_status_reasons = tuple(
        reason
        for reason in STATUS_REASONS
        if not reason.startswith("CHECKPOINT_PLACEHOLDER_")
    )
    _require(
        reasons == parent_status_reasons,
        "parent status-reason vocabulary drifted",
    )
    _require(actor_keys == ACTOR_KIND_KEYS, "actor-kind key tuple drifted")
    _require(
        len(counter_fields) == 66
        and counter_fields == tuple(sorted(counter_fields))
        and len(set(counter_fields)) == 66,
        "compact-counter coordinate tuple is not the exact sorted 66-field set",
    )
    _require(
        len(null_attempt_fields) == 85
        and null_attempt_fields == tuple(sorted(null_attempt_fields))
        and len(set(null_attempt_fields)) == 85,
        "null-attempt field tuple is not the exact sorted 85-field set",
    )
    _require(
        len(compact_point_fields) == 8
        and compact_point_fields == tuple(sorted(compact_point_fields))
        and len(set(compact_point_fields)) == 8,
        "compact point/current tuple is not the exact sorted eight-field set",
    )

    fields: list[dict[str, str]] = []
    field_pattern = re.compile(
        r"^\| `(?P<field_id>[a-z][a-z0-9_]*\.[a-z0-9_]+)` "
        r"\| (?P<value_unit>[^|]+?) \| `(?P<profile>[^`]+)` "
        r"\| `(?P<shape>[^`]+)` \|",
        re.MULTILINE,
    )
    for match in field_pattern.finditer(text):
        value_unit = match.group("value_unit").strip()
        _require(
            value_unit.count(" / ") == 1,
            f"field value/unit delimiter drifted: {match.group('field_id')}",
        )
        raw_kind, raw_unit = value_unit.split(" / ")
        fields.append(
            {
                "field_id": match.group("field_id"),
                "value_kind": _normalize_token(raw_kind),
                "unit": _normalize_token(raw_unit),
                "profile": match.group("profile"),
                "value_shape_id": match.group("shape"),
            }
        )
    _require(len(fields) == 185, "protocol must contain exactly 185 target fields")
    _require(
        len({row["field_id"] for row in fields}) == 185,
        "target field IDs are not unique",
    )

    profiles: dict[str, dict[str, Any]] = {}
    for line in text.splitlines():
        if not line.startswith("| `P_"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        _require(len(cells) == 7, f"malformed descriptor-profile row: {line}")
        profile_id = _strip_code(cells[0])
        method_cell = cells[1]
        if method_cell == "none" or method_cell.startswith("exact row-selected"):
            method_role_pairs: list[dict[str, Any]] | None = (
                [] if method_cell == "none" else None
            )
        else:
            method_role_pairs = []
            for pair in _strip_code(method_cell).split(";"):
                method, raw_roles = pair.split("@", 1)
                allowed_roles = tuple(
                    sorted(ROLE_ALIASES[token] for token in raw_roles.split(","))
                )
                method_role_pairs.append(
                    {
                        "observation_method": method,
                        "allowed_roles": list(allowed_roles),
                    }
                )
            method_role_pairs.sort(key=lambda item: item["observation_method"])

        checkpoint_cell = _strip_code(cells[2])
        if checkpoint_cell == "CP_TARGET":
            allowed_checkpoints = checkpoint_markers
        elif checkpoint_cell == "-":
            allowed_checkpoints = ()
        else:
            raise InventoryError(
                f"unknown checkpoint alias for profile {profile_id}: {checkpoint_cell}"
            )

        operation_cell = _strip_code(cells[3])
        if operation_cell == "ALL4":
            operations = OPERATION_KINDS
        elif operation_cell == "ACK":
            operations = ("ACK_DEADLINE_EXPIRY",)
        elif operation_cell == "SHUTDOWN":
            operations = ("LOCAL_SHUTDOWN",)
        else:
            raise InventoryError(
                f"unknown operation alias for profile {profile_id}: {operation_cell}"
            )

        reason_profile = _strip_code(cells[4])
        _require(
            reason_profile in UNAVAILABILITY_PROFILES,
            f"unknown unavailability profile: {reason_profile}",
        )
        censoring = cells[5] == "yes"
        _require(cells[5] in {"yes", "no"}, f"bad censoring flag: {cells[5]}")
        later_action = _strip_code(cells[6])
        _require(later_action == "FAIL_CLOSED", "later-action literal drifted")
        profiles[profile_id] = {
            "method_role_pairs": method_role_pairs,
            "allowed_checkpoint_marker_kinds": list(allowed_checkpoints),
            "applicable_operation_kinds": list(operations),
            "reason_profile": reason_profile,
            "censoring_allowed": censoring,
            "later_threshold_action_if_unavailable": later_action,
        }
    _require(len(profiles) == 37, "protocol must contain exactly 37 profiles")

    marker_section_start = text.find("### 7.2 Frozen marker kinds and anchors")
    marker_section_end = text.find(
        "### 7.3 Compact marker schema", marker_section_start
    )
    _require(
        marker_section_start >= 0 and marker_section_end > marker_section_start,
        "marker operation table is absent",
    )
    marker_section = text[marker_section_start:marker_section_end]
    operation_label_map = {
        "ACK expiry": ("ACK_DEADLINE_EXPIRY",),
        "Ingress": ("INGRESS",),
        "Local shutdown": ("LOCAL_SHUTDOWN",),
        "Subscription": ("SUBSCRIPTION_DISPATCH",),
    }
    checkpoint_operation_map: dict[str, tuple[str, ...]] = {}
    for operation_label, marker_kind in re.findall(
        r"^\| ([^|]+?) \| `([A-Z][A-Z0-9_]*)` \|",
        marker_section,
        flags=re.MULTILINE,
    ):
        if marker_kind not in checkpoint_markers:
            continue
        if operation_label.startswith("All"):
            operations = OPERATION_KINDS
        else:
            _require(
                operation_label in operation_label_map,
                f"unknown checkpoint operation label: {operation_label}",
            )
            operations = operation_label_map[operation_label]
        checkpoint_operation_map[marker_kind] = operations
    _require(
        tuple(sorted(checkpoint_operation_map)) == checkpoint_markers,
        "checkpoint-operation map does not cover the exact 13 checkpoint markers",
    )

    off_start = text.find("The frozen `OFF` profile is likewise exact")
    off_end = text.find("remain the three always-available signed", off_start)
    _require(
        off_start >= 0 and off_end > off_start, "frozen OFF static tuple is absent"
    )
    off_static_fields = tuple(
        sorted(re.findall(r"`([a-z][a-z0-9_.]+)`", text[off_start:off_end]))
    )
    _require(
        off_static_fields == OFF_STATIC_AVAILABLE_FIELD_IDS,
        "frozen OFF static field tuple drifted",
    )
    for required_clause in (
        r"Operation exclusion has precedence\s+over the attempt rule",
        r"`ON` forbids\s+`INSTRUMENTATION_DISABLED`",
        r"`OFF` forbids `STABLE_CHECKPOINT` but permits the\s+single `STARTUP_RECOVERY`",
    ):
        _require(
            re.search(required_clause, text) is not None,
            f"context-semantics clause is absent: {required_clause}",
        )

    contracts = {
        "methods": methods,
        "markers": markers,
        "checkpoint_markers": checkpoint_markers,
        "reasons": reasons,
        "actor_keys": actor_keys,
        "counter_fields": counter_fields,
        "null_attempt_fields": null_attempt_fields,
        "compact_point_fields": compact_point_fields,
        "checkpoint_operation_map": checkpoint_operation_map,
        "off_static_fields": off_static_fields,
        "fields": fields,
        "profiles": profiles,
    }
    return contracts


def _vocabulary_definitions(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    definitions = {
        "RAW_V8_OPERATION_KIND": OPERATION_KINDS,
        "RAW_V8_OBSERVATION_ROLE": OBSERVATION_ROLES,
        "RAW_V8_MARKER_KIND": parsed["markers"],
        "RAW_V8_FULL_CHECKPOINT_MARKER_KIND": parsed["checkpoint_markers"],
        "RAW_V8_OBSERVATION_METHOD": parsed["methods"],
        "RAW_V8_STATUS_REASON": STATUS_REASONS,
        "RAW_V8_AVAILABILITY": AVAILABILITIES,
        "RAW_V8_OBSERVATION_ATTEMPT": OBSERVATION_ATTEMPTS,
        "RAW_V8_SOURCE_FAILURE_PHASE": SOURCE_FAILURE_PHASES,
        "RAW_V8_ADAPTER_SPAN_STATUS": ADAPTER_SPAN_STATUSES,
        "RAW_V8_CLOCK_SPAN_STATUS": CLOCK_SPAN_STATUSES,
        "RAW_V8_CLOCK_DOMAIN": CLOCK_DOMAINS,
        "RAW_V8_INSTRUMENTATION_MODE": INSTRUMENTATION_MODES,
        "RAW_V8_CENSORING": CENSORING_VALUES,
        "RAW_V8_VALUE_KIND": VALUE_KINDS,
        "RAW_V8_DURATION_RELATION": DURATION_RELATIONS,
        "RAW_V8_LATER_ACTION": ("FAIL_CLOSED",),
        "RAW_V8_A1_COMMAND_KIND": OPERATION_KINDS,
        "RAW_V8_A1_ADMISSION_OUTCOME": A1_ADMISSION_OUTCOMES,
        "RAW_V8_A1_REJECTION_CLASS": A1_REJECTION_CLASSES,
        "RAW_V8_SQLITE_PRIMARY_RESULT": SQLITE_PRIMARY_RESULTS,
        "RAW_V8_ACTOR_KIND_MAP_KEY": ACTOR_KIND_KEYS,
        "RAW_V8_SQLITE_STAGE_RESULT_MAP_KEY": SQLITE_STAGE_RESULTS,
        "RAW_V8_GC_GENERATION_MAP_KEY": GC_GENERATION_KEYS,
        "RAW_V8_ERROR_FORM": ERROR_FORMS,
    }
    _require(len(definitions) == 25, "registry must contain 25 vocabularies")
    records: list[dict[str, Any]] = []
    for vocabulary_id in sorted(definitions):
        members = tuple(sorted(definitions[vocabulary_id]))
        _require(
            len(members) == len(set(members)),
            f"duplicate member in {vocabulary_id}",
        )
        records.append({"vocabulary_id": vocabulary_id, "members": list(members)})
    return records


def _value_shape_definitions() -> list[dict[str, Any]]:
    records = [
        {
            "value_shape_id": "S",
            "container_kind": "SCALAR",
            "minimum_items": None,
            "maximum_items": None,
            "ordered_keys": [],
        },
        {
            "value_shape_id": "L_A1_FIFO_4",
            "container_kind": "LIST",
            "minimum_items": 0,
            "maximum_items": 4,
            "ordered_keys": [],
        },
        {
            "value_shape_id": "L_GC_GENERATIONS_3",
            "container_kind": "LIST",
            "minimum_items": 3,
            "maximum_items": 3,
            "ordered_keys": [],
        },
        {
            "value_shape_id": "M_ACTOR_KINDS_25",
            "container_kind": "FIXED_MAP",
            "minimum_items": 25,
            "maximum_items": 25,
            "ordered_keys": list(ACTOR_KIND_KEYS),
        },
        {
            "value_shape_id": "M_SQLITE_STAGE_RESULTS_32",
            "container_kind": "FIXED_MAP",
            "minimum_items": 32,
            "maximum_items": 32,
            "ordered_keys": list(SQLITE_STAGE_RESULTS),
        },
        {
            "value_shape_id": "M_GC_GENERATIONS_3",
            "container_kind": "FIXED_MAP",
            "minimum_items": 3,
            "maximum_items": 3,
            "ordered_keys": list(GC_GENERATION_KEYS),
        },
    ]
    return sorted(records, key=lambda item: item["value_shape_id"])


def _value_constraint_definitions() -> list[dict[str, Any]]:
    member_names = (
        "value_constraint_id",
        "value_kind",
        "scalar_profile",
        "vocabulary_id",
        "integer_minimum",
        "integer_maximum",
        "text_minimum_utf8_bytes",
        "text_maximum_utf8_bytes",
        "text_ascii_pattern",
        "decimal_maximum",
        "collection_item_constraint_id",
        "external_authority_profile",
    )

    def record(
        value_constraint_id: str,
        value_kind: str,
        scalar_profile: str,
        **updates: Any,
    ) -> dict[str, Any]:
        result = dict.fromkeys(member_names)
        result.update(
            {
                "value_constraint_id": value_constraint_id,
                "value_kind": value_kind,
                "scalar_profile": scalar_profile,
                **updates,
            }
        )
        _require(set(result) == set(member_names), "constraint key drift")
        return result

    safe_range = {"integer_minimum": 0, "integer_maximum": SAFE_UINT_MAX}
    sha_range = {
        "text_minimum_utf8_bytes": 64,
        "text_maximum_utf8_bytes": 64,
        "text_ascii_pattern": "[0-9a-f]{64}",
    }
    enum_range = {"text_minimum_utf8_bytes": 1, "text_maximum_utf8_bytes": 256}
    records = [
        record("UINT_SAFE_IJSON", "UINT", "SAFE_IJSON_UINT", **safe_range),
        record(
            "UINT_LOOP_PROBE_INTERVAL_NS",
            "UINT",
            "SAFE_IJSON_UINT",
            integer_minimum=1_000_000,
            integer_maximum=60_000_000_000,
        ),
        record(
            "OPTIONAL_UINT_SAFE_IJSON",
            "OPTIONAL_UINT",
            "SAFE_IJSON_UINT",
            **safe_range,
        ),
        record("BOOL_EXACT", "BOOL", "EXACT_BOOL"),
        record("TEXT_SHA256", "TEXT", "SHA256", **sha_range),
        record("OPTIONAL_TEXT_SHA256", "OPTIONAL_TEXT", "SHA256", **sha_range),
        record(
            "OPTIONAL_TEXT_UINT128_DECIMAL",
            "OPTIONAL_TEXT",
            "UINT128_DECIMAL",
            text_minimum_utf8_bytes=1,
            text_maximum_utf8_bytes=39,
            text_ascii_pattern="0|[1-9][0-9]*",
            decimal_maximum=UINT128_MAX_TEXT,
        ),
        record(
            "OPTIONAL_TEXT_PLATFORM_ERRNO",
            "OPTIONAL_TEXT",
            "PLATFORM_ERRNO",
            text_minimum_utf8_bytes=1,
            text_maximum_utf8_bytes=64,
            text_ascii_pattern="[A-Z][A-Z0-9_]{0,63}",
            external_authority_profile=(
                "MANIFEST_BOUND_PLATFORM_ERRNO_MAP_AND_DURABLE_SEND_PREFIX_V1"
            ),
        ),
        record(
            "UINT_LIST_SAFE_IJSON",
            "UINT_LIST",
            "SAFE_IJSON_COLLECTION",
            collection_item_constraint_id="UINT_SAFE_IJSON",
            **safe_range,
        ),
        record(
            "FIXED_UINT_MAP_SAFE_IJSON",
            "FIXED_UINT_MAP",
            "SAFE_IJSON_COLLECTION",
            collection_item_constraint_id="UINT_SAFE_IJSON",
            **safe_range,
        ),
        record(
            "DURATION_BOUND_SAFE_IJSON",
            "DURATION_BOUND",
            "DURATION_BOUND",
            **safe_range,
        ),
        record(
            "TEXT_ENUM_A1_COMMAND_KIND",
            "TEXT",
            "ENUM",
            vocabulary_id="RAW_V8_A1_COMMAND_KIND",
            **enum_range,
        ),
        record(
            "OPTIONAL_TEXT_ENUM_A1_COMMAND_KIND",
            "OPTIONAL_TEXT",
            "ENUM",
            vocabulary_id="RAW_V8_A1_COMMAND_KIND",
            **enum_range,
        ),
        record(
            "TEXT_LIST_ENUM_A1_COMMAND_KIND",
            "TEXT_LIST",
            "SAFE_IJSON_COLLECTION",
            vocabulary_id="RAW_V8_A1_COMMAND_KIND",
            collection_item_constraint_id="TEXT_ENUM_A1_COMMAND_KIND",
            **enum_range,
        ),
        record(
            "TEXT_ENUM_A1_ADMISSION_OUTCOME",
            "TEXT",
            "ENUM",
            vocabulary_id="RAW_V8_A1_ADMISSION_OUTCOME",
            **enum_range,
        ),
        record(
            "OPTIONAL_TEXT_ENUM_A1_REJECTION_CLASS",
            "OPTIONAL_TEXT",
            "ENUM",
            vocabulary_id="RAW_V8_A1_REJECTION_CLASS",
            **enum_range,
        ),
        record(
            "TEXT_ENUM_SQLITE_PRIMARY_RESULT",
            "TEXT",
            "ENUM",
            vocabulary_id="RAW_V8_SQLITE_PRIMARY_RESULT",
            **enum_range,
        ),
    ]
    _require(len(records) == 17, "registry must contain 17 value constraints")
    return sorted(records, key=lambda item: item["value_constraint_id"])


def _status_reason_policy_definition() -> dict[str, Any]:
    availability_state_rules = [
        {
            "availability": "AVAILABLE",
            "value_policy": "REQUIRED",
            "reason_policy": "FORBIDDEN",
            "censoring_policy": "NONE_ONLY",
            "attempt_policy": "ATTEMPTED_ONLY",
            "adapter_span_policy": "AVAILABLE_ONLY",
        },
        {
            "availability": "CENSORED",
            "value_policy": "DURATION_BOUND_REQUIRED",
            "reason_policy": "FORBIDDEN",
            "censoring_policy": "DESCRIPTOR_BOUND_MAPPING",
            "attempt_policy": "ATTEMPTED_ONLY",
            "adapter_span_policy": "AVAILABLE_ONLY",
        },
        {
            "availability": "NOT_APPLICABLE",
            "value_policy": "FORBIDDEN",
            "reason_policy": "NOT_APPLICABLE_REQUIRED",
            "censoring_policy": "NONE_ONLY",
            "attempt_policy": "NOT_ATTEMPTED_ONLY",
            "adapter_span_policy": "NOT_APPLICABLE_ONLY",
        },
        {
            "availability": "UNAVAILABLE",
            "value_policy": "FORBIDDEN",
            "reason_policy": "UNAVAILABLE_REQUIRED",
            "censoring_policy": "NONE_ONLY",
            "attempt_policy": "REASON_RULE",
            "adapter_span_policy": "REASON_RULE",
        },
    ]
    availability_state_rules.sort(key=lambda item: item["availability"])

    def state(
        attempt_state: str,
        error_forms: tuple[str, ...],
        failure_phases: tuple[str, ...],
        adapter_span_policy: str,
    ) -> dict[str, Any]:
        return {
            "attempt_state": attempt_state,
            "permitted_error_forms": sorted(error_forms),
            "permitted_failure_phases": sorted(failure_phases),
            "adapter_span_policy": adapter_span_policy,
        }

    not_attempted_none = lambda: state(  # noqa: E731 - compact literal factory
        "NOT_ATTEMPTED", ("NONE",), ("NONE",), "NOT_APPLICABLE_ONLY"
    )
    attempted_os = lambda: state(  # noqa: E731 - compact literal factory
        "ATTEMPTED", ("OS",), ("SOURCE_ADAPTER",), "AVAILABLE_ONLY"
    )
    attempted_status = lambda: state(  # noqa: E731 - compact literal factory
        "ATTEMPTED", ("STATUS_ONLY",), ("NONE",), "AVAILABLE_ONLY"
    )

    rules: dict[str, list[dict[str, Any]]] = {}
    for reason in (
        "CHECKPOINT_PLACEHOLDER_ARTIFACT_BOUND_EXCEEDED",
        "CHECKPOINT_PLACEHOLDER_OBSERVER_INTERNAL_ERROR",
        "CHECKPOINT_PLACEHOLDER_SOURCE_CLOCK_UNAVAILABLE",
        "CHECKPOINT_PLACEHOLDER_TARGET_BOUNDARY_NOT_REACHED",
        "INSTRUMENTATION_DISABLED",
        "NOT_APPLICABLE_TO_OPERATION",
        "NOT_APPLICABLE_TO_REACHED_STATE",
        "TARGET_BOUNDARY_NOT_REACHED",
        "NO_FROZEN_PRESSURE_POLICY",
        "OBSERVATION_WOULD_MUTATE_TARGET",
        "OBSERVATION_WOULD_REENTER_TARGET_LOCK",
        "OBSERVATION_WOULD_REENTER_ACTIVE_SQLITE_TRANSACTION",
        "NO_STABLE_SLOW_CALLBACK_SOURCE",
        "PROCESS_LOSS_VOLATILE_MARKER_STATE",
        "SOURCE_DURABLE_RECORD_ABSENT",
        "SOURCE_COUNTER_NOT_INSTRUMENTED",
    ):
        rules[reason] = [not_attempted_none()]
    for reason in (
        "UNSUPPORTED_BY_KERNEL",
        "PERMISSION_DENIED",
        "OS_OBSERVATION_ERROR",
    ):
        rules[reason] = [attempted_os()]
    for reason in (
        "MARKER_RING_OVERWROTE_PREFIX",
        "PERIODIC_PROBE_DID_NOT_FIRE",
        "PROBE_RING_OVERWROTE_PREFIX",
        "ARTIFACT_BOUND_EXCEEDED",
    ):
        rules[reason] = [attempted_status()]
    rules["UNSUPPORTED_BY_PYTHON_RUNTIME"] = [
        state(
            "ATTEMPTED",
            ("NON_OS",),
            ("SOURCE_ADAPTER",),
            "AVAILABLE_ONLY",
        ),
        not_attempted_none(),
    ]
    rules["OBSERVER_INTERNAL_ERROR"] = [
        state(
            "ATTEMPTED",
            ("NON_OS",),
            ("SOURCE_ADAPTER", "VALUE_VALIDATION"),
            "AVAILABLE_ONLY",
        )
    ]
    rules["SOURCE_CLOCK_UNAVAILABLE"] = [
        state(
            "ATTEMPTED",
            ("NON_OS", "OS"),
            ("SECOND_CLOCK_READ",),
            "UNAVAILABLE_ONLY",
        ),
        state(
            "NOT_ATTEMPTED",
            ("NONE",),
            ("FIRST_CLOCK_READ",),
            "NOT_APPLICABLE_ONLY",
        ),
    ]
    _require(set(rules) == set(STATUS_REASONS), "reason-policy coverage drifted")

    reason_rules: list[dict[str, Any]] = []
    for reason in sorted(rules):
        if reason == "NOT_APPLICABLE_TO_OPERATION":
            required_availability = "NOT_APPLICABLE"
            context_predicate: str | None = "OPERATION_EXCLUDED"
        elif reason == "NOT_APPLICABLE_TO_REACHED_STATE":
            required_availability = "NOT_APPLICABLE"
            context_predicate = "REACHED_STATE_EXCLUDED"
        elif reason == "CHECKPOINT_PLACEHOLDER_ARTIFACT_BOUND_EXCEEDED":
            required_availability = "UNAVAILABLE"
            context_predicate = "V2_CHECKPOINT_PLACEHOLDER_ARTIFACT_BOUND"
        elif reason == "CHECKPOINT_PLACEHOLDER_OBSERVER_INTERNAL_ERROR":
            required_availability = "UNAVAILABLE"
            context_predicate = "V2_CHECKPOINT_PLACEHOLDER_OBSERVER_INTERNAL_ERROR"
        elif reason == "CHECKPOINT_PLACEHOLDER_SOURCE_CLOCK_UNAVAILABLE":
            required_availability = "UNAVAILABLE"
            context_predicate = "V2_CHECKPOINT_PLACEHOLDER_SOURCE_CLOCK_UNAVAILABLE"
        elif reason == "CHECKPOINT_PLACEHOLDER_TARGET_BOUNDARY_NOT_REACHED":
            required_availability = "UNAVAILABLE"
            context_predicate = "V2_CHECKPOINT_PLACEHOLDER_TARGET_BOUNDARY_NOT_REACHED"
        else:
            required_availability = "UNAVAILABLE"
            context_predicate = None
        states = sorted(rules[reason], key=lambda item: item["attempt_state"])
        reason_rules.append(
            {
                "reason": reason,
                "required_availability": required_availability,
                "context_predicate": context_predicate,
                "attempt_state_error_forms": states,
            }
        )

    error_form_definitions = [
        {
            "error_form": "NONE",
            "errno_pair_policy": "FORBIDDEN",
            "error_class_policy": "FORBIDDEN",
            "error_digest_policy": "FORBIDDEN",
            "class_digest_pair_policy": "BOTH_FORBIDDEN",
        },
        {
            "error_form": "NON_OS",
            "errno_pair_policy": "FORBIDDEN",
            "error_class_policy": "REQUIRED",
            "error_digest_policy": "REQUIRED",
            "class_digest_pair_policy": "BOTH_REQUIRED",
        },
        {
            "error_form": "OS",
            "errno_pair_policy": "REQUIRED",
            "error_class_policy": "OPTIONAL",
            "error_digest_policy": "OPTIONAL",
            "class_digest_pair_policy": "BOTH_OR_NEITHER",
        },
        {
            "error_form": "STATUS_ONLY",
            "errno_pair_policy": "FORBIDDEN",
            "error_class_policy": "FORBIDDEN",
            "error_digest_policy": "FORBIDDEN",
            "class_digest_pair_policy": "BOTH_FORBIDDEN",
        },
    ]
    error_form_definitions.sort(key=lambda item: item["error_form"])
    return {
        "status_reason_policy_id": STATUS_REASON_POLICY_ID,
        "availability_state_rules": availability_state_rules,
        "reason_rules": reason_rules,
        "error_form_definitions": error_form_definitions,
    }


def _cross_field_constraint_definitions() -> list[dict[str, Any]]:
    return [
        {
            "cross_field_constraint_id": CROSS_FIELD_CONSTRAINT_ID,
            "count_field_id": "a1.waiting_count",
            "sequence_field_id": "a1.waiting_sequences",
            "kind_field_id": "a1.waiting_kinds",
            "activation_condition": "ALL_MEMBERS_AVAILABLE",
            "maximum_items": 4,
            "sequence_order": "STRICTLY_INCREASING_UNIQUE",
            "cardinality_rule": "COUNT_EQUALS_BOTH_ARRAY_LENGTHS",
            "pairing_rule": "SAME_INDEX",
        }
    ]


def _constraint_for_field(field: dict[str, str]) -> str:
    field_id = field["field_id"]
    special = {
        "loop.probe_interval_ns": "UINT_LOOP_PROBE_INTERVAL_NS",
        "a1.target_command_kind": "TEXT_ENUM_A1_COMMAND_KIND",
        "a1.active_kind": "OPTIONAL_TEXT_ENUM_A1_COMMAND_KIND",
        "a1.waiting_kinds": "TEXT_LIST_ENUM_A1_COMMAND_KIND",
        "a1.target_admission_outcome": "TEXT_ENUM_A1_ADMISSION_OUTCOME",
        "a1.target_rejection_class": "OPTIONAL_TEXT_ENUM_A1_REJECTION_CLASS",
        "sqlite.last_primary_result_class": "TEXT_ENUM_SQLITE_PRIMARY_RESULT",
    }
    if field_id in special:
        return special[field_id]
    kind = field["value_kind"]
    unit = field["unit"]
    direct = {
        "UINT": "UINT_SAFE_IJSON",
        "BOOL": "BOOL_EXACT",
        "OPTIONAL_UINT": "OPTIONAL_UINT_SAFE_IJSON",
        "UINT_LIST": "UINT_LIST_SAFE_IJSON",
        "FIXED_UINT_MAP": "FIXED_UINT_MAP_SAFE_IJSON",
        "DURATION_BOUND": "DURATION_BOUND_SAFE_IJSON",
    }
    if kind in direct:
        return direct[kind]
    if kind == "TEXT" and unit in {"IDENTITY", "HASH"}:
        return "TEXT_SHA256"
    if kind == "OPTIONAL_TEXT" and unit in {"IDENTITY", "HASH"}:
        return "OPTIONAL_TEXT_SHA256"
    if kind == "OPTIONAL_TEXT" and unit == "ABSOLUTE_NS":
        return "OPTIONAL_TEXT_UINT128_DECIMAL"
    if kind == "OPTIONAL_TEXT" and unit == "ERRNO":
        return "OPTIONAL_TEXT_PLATFORM_ERRNO"
    raise InventoryError(
        f"no exact value-constraint assignment for {field_id}: {kind}/{unit}"
    )


def _expanded_profile(
    profile_spelling: str, profiles: dict[str, dict[str, Any]]
) -> tuple[str, dict[str, Any]]:
    match = re.fullmatch(
        r"(P_PROCESS_POINT|P_PROCESS_CPU)\(([A-Z0-9_]+)\)", profile_spelling
    )
    if match is None:
        _require(profile_spelling in profiles, f"unknown profile: {profile_spelling}")
        profile = profiles[profile_spelling]
        _require(
            profile["method_role_pairs"] is not None,
            f"parameter required for {profile_spelling}",
        )
        return profile_spelling, profile

    base, method = match.groups()
    allowed = {
        "P_PROCESS_POINT": {
            "CGROUP_V2_MEMORY_CURRENT",
            "PROCFS_SMAPS_ROLLUP",
            "PROCFS_STATM",
            "PROCFS_STATUS",
        },
        "P_PROCESS_CPU": {"OWNER_THREAD_CPU_CLOCK", "PROCESS_CPU_CLOCK"},
    }
    _require(method in allowed[base], f"illegal parameterized method: {method}")
    template = profiles[base]
    role_tokens = (
        ("B", "C", "A", "R")
        if base == "P_PROCESS_POINT"
        else (
            "C",
            "A",
            "G",
        )
    )
    expanded = dict(template)
    expanded["method_role_pairs"] = [
        {
            "observation_method": method,
            "allowed_roles": sorted(ROLE_ALIASES[token] for token in role_tokens),
        }
    ]
    return base, expanded


def _build_target_registry(
    parsed: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    shape_definitions = _value_shape_definitions()
    shapes_by_id = {item["value_shape_id"]: item for item in shape_definitions}
    metadata: list[dict[str, Any]] = []
    descriptors: list[dict[str, Any]] = []
    for field in parsed["fields"]:
        profile_id, profile = _expanded_profile(field["profile"], parsed["profiles"])
        value_shape_id = field["value_shape_id"]
        _require(value_shape_id in shapes_by_id, f"unknown shape: {value_shape_id}")
        reasons = sorted(
            UNAVAILABILITY_PROFILES[profile["reason_profile"]]
            | NON_APPLICABLE_REASONS
            | {
                "CHECKPOINT_PLACEHOLDER_ARTIFACT_BOUND_EXCEEDED",
                "CHECKPOINT_PLACEHOLDER_OBSERVER_INTERNAL_ERROR",
                "CHECKPOINT_PLACEHOLDER_SOURCE_CLOCK_UNAVAILABLE",
                "CHECKPOINT_PLACEHOLDER_TARGET_BOUNDARY_NOT_REACHED",
            }
        )
        cross_constraints = (
            [CROSS_FIELD_CONSTRAINT_ID]
            if field["field_id"]
            in {"a1.waiting_count", "a1.waiting_sequences", "a1.waiting_kinds"}
            else []
        )
        descriptor = {
            "field_id": field["field_id"],
            "layer": field["field_id"].split(".", 1)[0].upper(),
            "value_kind": field["value_kind"],
            "unit": field["unit"],
            "value_constraint_id": _constraint_for_field(field),
            "observation_method_role_pairs": profile["method_role_pairs"],
            "allowed_checkpoint_marker_kinds": profile[
                "allowed_checkpoint_marker_kinds"
            ],
            "applicable_operation_kinds": profile["applicable_operation_kinds"],
            "allowed_status_reasons": reasons,
            "status_reason_policy_id": STATUS_REASON_POLICY_ID,
            "censoring_allowed": profile["censoring_allowed"],
            "later_threshold_action_if_unavailable": profile[
                "later_threshold_action_if_unavailable"
            ],
            "value_shape_id": value_shape_id,
            "value_shape_keys": list(shapes_by_id[value_shape_id]["ordered_keys"]),
            "cross_field_constraint_ids": cross_constraints,
        }
        descriptors.append(descriptor)
        metadata.append(
            {
                "descriptor": descriptor,
                "profile_id": profile_id,
                "profile_spelling": field["profile"],
                "reason_profile": profile["reason_profile"],
            }
        )
    descriptors.sort(key=lambda item: item["field_id"])
    metadata.sort(key=lambda item: item["descriptor"]["field_id"])
    _require(
        [item["descriptor"] for item in metadata] == descriptors,
        "descriptor metadata order drifted",
    )
    payload = {
        "target_registry_profile": "COMPLETE_TYPED_FIELD_AVAILABILITY_V1",
        "status_reason_policy_definition": _status_reason_policy_definition(),
        "ordered_vocabulary_definitions": _vocabulary_definitions(parsed),
        "ordered_value_shape_definitions": shape_definitions,
        "ordered_value_constraint_definitions": _value_constraint_definitions(),
        "ordered_cross_field_constraint_definitions": (
            _cross_field_constraint_definitions()
        ),
        "field_count": 185,
        "descriptors": descriptors,
    }
    envelope = _standalone_envelope(
        DOMAINS["target_registry"], payload, "target_field_registry_id"
    )
    return envelope, metadata


MONOTONE_COUNTER_EXCLUSIONS: Final = {
    "actor.pending_control_obligations",
    "actor.pending_control_octets",
    "actor.pending_wire_obligations",
    "actor.pending_wire_octets",
    "ingress.durable_buffer_octets",
    "ingress.pending_raw_chunks",
    "ingress.pending_raw_octets",
    "parser.last_unit_elapsed_ns",
    "parser.last_unit_thread_cpu_ns",
}
FROZEN_COUNTER_SCHEMA_ID: Final = (
    "5181eb89788d511ffeb2ccc65264b81e9e0d3ae977043820524f8b08dfa58fc3"
)


def _build_counter_schema(parsed: dict[str, Any]) -> dict[str, Any]:
    fields = tuple(parsed["counter_fields"])
    _require(
        MONOTONE_COUNTER_EXCLUSIONS < set(fields),
        "counter monotone exclusions are not a strict subset",
    )
    monotone_fields = tuple(
        field_id for field_id in fields if field_id not in MONOTONE_COUNTER_EXCLUSIONS
    )
    _require(len(monotone_fields) == 57, "counter monotone subset must contain 57")
    payload = {
        "counter_field_count": 66,
        "ordered_counter_field_ids": list(fields),
        "monotone_counter_field_ids": list(monotone_fields),
    }
    envelope = _standalone_envelope(
        DOMAINS["counter_schema"], payload, "counter_schema_id"
    )
    _require(
        envelope["counter_schema_id"] == FROZEN_COUNTER_SCHEMA_ID,
        "counter schema ID differs from the frozen protocol literal",
    )
    return envelope


def _context_semantics_invariants(
    *,
    parsed: dict[str, Any],
    metadata: list[dict[str, Any]],
    counter_schema: dict[str, Any],
) -> dict[str, Any]:
    descriptor_ids = {item["descriptor"]["field_id"] for item in metadata}
    null_attempt_fields = tuple(parsed["null_attempt_fields"])
    _require(
        set(null_attempt_fields) <= descriptor_ids,
        "null-attempt tuple refers to a non-registry field",
    )
    profile_derived_fields = tuple(
        sorted(
            item["descriptor"]["field_id"]
            for item in metadata
            if item["profile_spelling"] in NULL_ATTEMPT_DERIVED_PROFILE_SPELLINGS
        )
    )
    _require(
        len(profile_derived_fields) == 84,
        "null-attempt profile derivation must produce exactly 84 fields",
    )
    explicit_items = [
        item
        for item in metadata
        if item["descriptor"]["field_id"] == NULL_ATTEMPT_EXPLICIT_FIELD_ID
    ]
    _require(len(explicit_items) == 1, "explicit target-effect field is absent")
    explicit_item = explicit_items[0]
    _require(
        explicit_item["profile_spelling"] == "P_TARGET_BOUND"
        and explicit_item["descriptor"]["value_kind"] == "DURATION_BOUND"
        and explicit_item["descriptor"]["censoring_allowed"] is True,
        "explicit target-effect field descriptor drifted",
    )
    _require(
        set(profile_derived_fields).isdisjoint({NULL_ATTEMPT_EXPLICIT_FIELD_ID})
        and tuple(sorted((*profile_derived_fields, NULL_ATTEMPT_EXPLICIT_FIELD_ID)))
        == null_attempt_fields,
        "85-field null-attempt tuple does not equal 84 profile-derived fields plus target effect",
    )

    counter_fields = tuple(counter_schema["ordered_counter_field_ids"])
    compact_operation_local_fields = tuple(
        field_id for field_id in counter_fields if field_id in set(null_attempt_fields)
    )
    _require(
        len(compact_operation_local_fields) == 58,
        "null-attempt tuple must contain exactly 58 compact coordinates",
    )
    compact_point_fields = tuple(parsed["compact_point_fields"])
    _require(
        tuple(
            field_id
            for field_id in counter_fields
            if field_id not in set(compact_operation_local_fields)
        )
        == compact_point_fields,
        "compact operation-local and point tuples do not partition all 66 coordinates",
    )

    derived_static_fields = tuple(
        sorted(
            item["descriptor"]["field_id"]
            for item in metadata
            if item["reason_profile"] == "U_STATIC"
        )
    )
    _require(
        derived_static_fields
        == tuple(parsed["off_static_fields"])
        == OFF_STATIC_AVAILABLE_FIELD_IDS,
        "OFF static tuple does not match registry profile derivation",
    )

    checkpoint_entries = [
        {
            "checkpoint_marker_kind": marker_kind,
            "applicable_operation_kinds": list(
                parsed["checkpoint_operation_map"][marker_kind]
            ),
        }
        for marker_kind in sorted(parsed["checkpoint_operation_map"])
    ]

    def tuple_proof(values: tuple[str, ...]) -> dict[str, Any]:
        return {
            "count": len(values),
            "ordered_field_ids": list(values),
            "ordered_field_ids_canonical_json_sha256": _sha256_bytes(
                _canonical_bytes(list(values))
            ),
        }

    return {
        "null_attempt": {
            **tuple_proof(null_attempt_fields),
            "profile_derived": tuple_proof(profile_derived_fields),
            "derivation_profile_spellings": sorted(
                NULL_ATTEMPT_DERIVED_PROFILE_SPELLINGS
            ),
            "explicit_target_effect_field": {
                "field_id": NULL_ATTEMPT_EXPLICIT_FIELD_ID,
                "descriptor_profile": explicit_item["profile_spelling"],
                "value_kind": explicit_item["descriptor"]["value_kind"],
                "censoring_allowed": explicit_item["descriptor"]["censoring_allowed"],
            },
            "operation_exclusion_precedes_null_attempt": True,
        },
        "compact_coordinate_partition": {
            "operation_local": tuple_proof(compact_operation_local_fields),
            "point_or_current": tuple_proof(compact_point_fields),
            "partition_field_count": len(counter_fields),
            "partition_is_complete_and_disjoint": True,
        },
        "off_mode": {
            "static_available": tuple_proof(derived_static_fields),
            "null_attempt_precedes_off_fallback": True,
            "instrumentation_disabled_fallback": True,
            "stable_checkpoint_forbidden": True,
            "startup_recovery_permitted": True,
        },
        "on_mode": {"instrumentation_disabled_forbidden": True},
        "checkpoint_operation_map": {
            "entry_count": len(checkpoint_entries),
            "ordered_entries": checkpoint_entries,
            "ordered_entries_canonical_json_sha256": _sha256_bytes(
                _canonical_bytes(checkpoint_entries)
            ),
            "stable_checkpoint_requires_attempt": True,
        },
    }


SPEC_TYPES: Final = {
    "ACK_DEADLINE_EXPIRY": "ACK_DEADLINE_EXPIRY_SPEC_V1",
    "INGRESS": "INGRESS_OPERATION_SPEC_V2",
    "LOCAL_SHUTDOWN": "LOCAL_SHUTDOWN_SPEC_V2",
    "SUBSCRIPTION_DISPATCH": "SUBSCRIPTION_DISPATCH_SPEC_V2",
}
RESULT_TYPES: Final = {
    "ACK_DEADLINE_EXPIRY": "ACK_DEADLINE_EXPIRY_RESULT_EVIDENCE_V1",
    "INGRESS": "INGRESS_RESULT_EVIDENCE_V2",
    "LOCAL_SHUTDOWN": "LOCAL_SHUTDOWN_RESULT_EVIDENCE_V2",
    "SUBSCRIPTION_DISPATCH": "SUBSCRIPTION_DISPATCH_RESULT_EVIDENCE_V2",
}
SPEC_BODY_MEMBERS: Final = {
    "ACK_DEADLINE_EXPIRY": (
        "workload_family",
        "expected_outbound_subscription_intent_id",
        "due_scenario",
        "expected_terminal_cause_code",
    ),
    "INGRESS": (
        "workload_family",
        "ordered_input_chunks_base64",
        "input_chunk_count",
        "input_octet_count",
        "input_sha256",
        "raw_ingress_batch_sha256",
        "timeout_seconds",
        "logical_oracle_profile_id",
        "expected_parser_unit_count",
        "expected_completed_application_message_count",
        "expected_logical_output_frame_count",
        "expected_logical_output_payload_octets",
        "expected_logical_output_frames_sha256",
    ),
    "LOCAL_SHUTDOWN": (
        "workload_family",
        "timeout_seconds",
        "expected_terminal_outcome",
        "expected_local_close_code",
        "expected_local_close_reason_sha256",
        "maximum_terminal_ingress_batches",
        "maximum_terminal_ingress_ciphertext_octets",
        "maximum_terminal_ingress_plaintext_octets",
        "maximum_terminal_socket_receive_calls",
        "maximum_terminal_tls_records",
        "maximum_terminal_tls_unwrap_iterations",
        "maximum_terminal_zero_progress_iterations",
        "maximum_terminal_ingress_parser_units",
        "maximum_terminal_ingress_automatic_outputs",
        "maximum_websocket_send_attempts",
        "maximum_tls_control_send_attempts",
        "maximum_peer_shutdown_polls",
    ),
    "SUBSCRIPTION_DISPATCH": (
        "workload_family",
        "idempotency_key",
        "transport_subscription_policy_id",
        "adapter_policy_id",
        "expected_topic",
        "expected_operation",
        "expected_logical_opcode",
        "expected_dispatch_disposition",
    ),
}
RESULT_BODY_MEMBERS: Final = {
    "ACK_DEADLINE_EXPIRY": (
        "expired",
        "due_decision_clock_evidence",
        "due_decision_clock_evidence_id",
        "ack_deadline_expired_event_id",
        "terminal_transition_event_id",
        "transport_session_termination_id",
    ),
    "INGRESS": (
        "ingress_progress_evidence_id",
        "final_parser_cursor_id",
        "final_retained_tail_id",
        "final_retained_tail_octets",
        "final_retained_tail_sha256",
        "sealed_pending_input_id",
        "ingress_oracle_baseline_id",
        "observed_consumed_new_input_octets",
        "observed_parser_unit_count",
        "observed_completed_application_message_count",
        "observed_logical_output_frame_count",
        "observed_logical_output_payload_octets",
        "observed_logical_output_frames_sha256",
    ),
    "LOCAL_SHUTDOWN": (
        "local_shutdown_started_event_id",
        "local_shutdown_deadline_evidence_event_id",
        "local_close_dispatch_completion_event_id",
        "ordered_terminal_ingress_read_attempt_event_ids",
        "ordered_terminal_ingress_read_result_event_ids",
        "ordered_terminal_raw_ingress_commit_ids",
        "ordered_terminal_raw_ingress_actor_event_ids",
        "ordered_terminal_parser_transition_event_ids",
        "websocket_close_received_transition_event_id",
        "shutdown_trace_step_count",
        "shutdown_trace_root_sha256",
        "final_terminal_ingress_batch_count",
        "final_terminal_ingress_ciphertext_octets",
        "final_terminal_ingress_plaintext_octets",
        "final_terminal_socket_receive_call_count",
        "final_terminal_tls_record_count",
        "final_terminal_tls_unwrap_iteration_count",
        "final_terminal_zero_progress_iteration_count",
        "final_terminal_ingress_parser_unit_count",
        "final_terminal_ingress_automatic_output_count",
        "final_websocket_send_attempt_count",
        "final_tls_control_send_attempt_count",
        "final_peer_shutdown_poll_count",
        "final_terminal_tls_staging_state_id",
        "decisive_terminal_transition_event_id",
        "transport_session_termination_id",
        "terminal_outcome",
    ),
    "SUBSCRIPTION_DISPATCH": (
        "outbound_subscription_intent_id",
        "generated_request_id",
        "generated_request_command_sha256",
        "generated_logical_opcode",
        "generated_logical_payload_sha256",
        "generated_logical_payload_octets",
        "dispatch_window_evidence",
        "dispatch_window_evidence_id",
        "outbound_wire_prepared_event_id",
        "tls_ciphertext_prepared_event_id",
        "ordered_kernel_attempt_event_ids",
        "ordered_kernel_result_event_ids",
        "outbound_dispatch_completed_event_id",
        "submitted_ciphertext_octets",
        "local_dispatch_disposition",
    ),
}

DECLARATION_PAYLOAD_MEMBERS: Final = (
    "campaign_manifest_id",
    "manifest_authority_id",
    "measurement_design_id",
    "workload_plan_id",
    "workload_id",
    "workload_sha256",
    "sample_sequence",
    "operation_sequence",
    "trial_index",
    "repetition_index",
    "is_warmup",
    "stage",
    "timeout_policy_id",
    "operation_kind",
    "operation_spec",
    "operation_spec_id",
)
DISPATCH_WINDOW_PAYLOAD_MEMBERS: Final = (
    "transport_session_id",
    "outbound_subscription_intent_id",
    "socket_lease_id",
    "monotonic_clock_domain_id",
    "dispatch_started_at",
    "dispatch_completed_at",
    "dispatch_started_monotonic_ns",
    "dispatch_completed_monotonic_ns",
)
DUE_DECISION_CLOCK_PAYLOAD_MEMBERS: Final = (
    "transport_session_id",
    "outbound_subscription_intent_id",
    "dispatch_window_evidence",
    "dispatch_window_evidence_id",
    "clock_source_manifest_id",
    "monotonic_clock_domain_id",
    "wall_before_at",
    "sampled_at",
    "wall_after_at",
    "monotonic_before_ns",
    "monotonic_sampled_ns",
    "monotonic_after_ns",
    "uncertainty_milliseconds",
    "synchronized",
    "valid_until",
    "clock_resolution_ns",
    "source_observation_sha256",
    "selectable_source_count",
    "chronyd_launch_id",
    "chronyd_runtime_observation_sha256",
    "committed_ack_deadline_at",
    "committed_ack_deadline_monotonic_ns",
    "due_scenario",
)
SOURCE_ERROR_DETAIL_PAYLOAD_MEMBERS: Final = (
    "field_id",
    "observation_method",
    "source_failure_phase",
    "source_errno_number",
    "source_errno_name",
    "source_error_class",
)
CLOCK_SPAN_MEMBERS: Final = (
    "clock_domain",
    "span_status",
    "started_offset_nanoseconds",
    "completed_offset_nanoseconds",
    "unavailable_reason",
)
OBSERVATION_CONTEXT_PAYLOAD_MEMBERS: Final = (
    "observation_role",
    "operation_kind",
    "instrumentation_mode",
    "candidate_id",
    "attempt_id",
    "target_field_registry_id",
    "marker_ordinal",
    "checkpoint_marker_kind",
    "observer_clock_span",
    "boottime_clock_span",
    "loop_clock_span",
)
FIELD_OBSERVATION_PAYLOAD_MEMBERS: Final = (
    "target_field_registry_id",
    "observation_context_id",
    "field_id",
    "availability",
    "value",
    "observation_method",
    "observation_attempt",
    "adapter_span_status",
    "observation_started_offset_nanoseconds",
    "observation_completed_offset_nanoseconds",
    "unavailable_reason",
    "censoring",
    "source_errno_number",
    "source_errno_name",
    "source_failure_phase",
    "source_error_class",
    "source_error_detail_sha256",
)
TARGET_OBSERVATION_PAYLOAD_MEMBERS: Final = (
    *OBSERVATION_CONTEXT_PAYLOAD_MEMBERS[:6],
    "observation_context_id",
    *OBSERVATION_CONTEXT_PAYLOAD_MEMBERS[6:],
    "field_observations",
)
TARGET_OBSERVATION_ROOT_PAYLOAD_MEMBERS: Final = (
    "candidate_id",
    "attempt_id",
    "operation_kind",
    "instrumentation_mode",
    "target_field_registry_id",
    "observation_count",
    "ordered_observation_ids",
)

MARKER_KINDS: Final = (
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
FULL_CHECKPOINT_MARKER_KINDS: Final = (
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
FORBIDDEN_FULL_CHECKPOINT_MARKER_KINDS: Final = (
    "ADMISSION_CANDIDATE_COMMITTED",
    "ADMISSION_GRANTED",
    "ADMISSION_NOT_GRANTED",
    "ADMISSION_TICKET_ACCEPTED",
    "TARGET_EFFECT_ENTRY",
)
CHECKPOINT_OPERATION_MAP: Final = {
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
    "TARGET_ESCAPE_OBSERVED": OPERATION_KINDS,
    "TCP_HALF_CLOSE_CONVERGED": ("LOCAL_SHUTDOWN",),
    "TLS_CONTROL_CONVERGED": ("LOCAL_SHUTDOWN",),
}
CHECKPOINT_SELECTOR_DEFINITIONS: Final = {
    "ACK_EMPTY": ("ACK_DEADLINE_EXPIRY", ()),
    "ACK_COVERAGE": (
        "ACK_DEADLINE_EXPIRY",
        (
            "ACK_DEADLINE_NOT_DUE",
            "ACK_DEADLINE_TERMINAL_CONVERGED",
            "TARGET_ESCAPE_OBSERVED",
        ),
    ),
    "INGRESS_EMPTY": ("INGRESS", ()),
    "INGRESS_COVERAGE": (
        "INGRESS",
        (
            "RAW_PREFIX_COMMITTED",
            "PARSER_UNIT_CONVERGED",
            "INGRESS_RETURN_READY",
            "TARGET_ESCAPE_OBSERVED",
        ),
    ),
    "LOCAL_SHUTDOWN_EMPTY": ("LOCAL_SHUTDOWN", ()),
    "LOCAL_SHUTDOWN_COVERAGE": (
        "LOCAL_SHUTDOWN",
        (
            "LOCAL_CLOSE_DISPATCH_CONVERGED",
            "TLS_CONTROL_CONVERGED",
            "TCP_HALF_CLOSE_CONVERGED",
            "SHUTDOWN_TERMINAL_CONVERGED",
            "TARGET_ESCAPE_OBSERVED",
        ),
    ),
    "SUBSCRIPTION_EMPTY": ("SUBSCRIPTION_DISPATCH", ()),
    "SUBSCRIPTION_COVERAGE": (
        "SUBSCRIPTION_DISPATCH",
        (
            "OUTBOUND_ARTIFACTS_PREPARED",
            "KERNEL_SEND_RESULT_CONVERGED",
            "DISPATCH_RETURN_READY",
            "TARGET_ESCAPE_OBSERVED",
        ),
    ),
}
REMOVED_V1_TAGS: Final = (
    "INGRESS_OPERATION_SPEC_V1",
    "INGRESS_RESULT_EVIDENCE_V1",
    "LOCAL_SHUTDOWN_SPEC_V1",
    "LOCAL_SHUTDOWN_RESULT_EVIDENCE_V1",
    "SUBSCRIPTION_DISPATCH_SPEC_V1",
    "SUBSCRIPTION_DISPATCH_RESULT_EVIDENCE_V1",
)
V2_CONTEXT_PAYLOAD_MEMBERS: Final = (
    "observation_role",
    "operation_kind",
    "instrumentation_mode",
    "candidate_id",
    "attempt_id",
    "target_field_registry_id",
    "marker_ordinal",
    "checkpoint_marker_kind",
    "full_checkpoint_selector_id",
    "checkpoint_selector_position",
    "checkpoint_selector_entry_id",
    "expected_checkpoint_marker_kind",
    "expected_occurrence_index_within_kind",
    "checkpoint_binding_status",
    "checkpoint_binding_unavailable_reason",
    "observer_clock_span",
    "boottime_clock_span",
    "loop_clock_span",
)
V2_OBSERVATION_PAYLOAD_MEMBERS: Final = (
    "observation_context",
    "observation_context_id",
    "field_observations",
)
V2_ROOT_PAYLOAD_MEMBERS: Final = (
    "candidate_id",
    "attempt_id",
    "operation_kind",
    "instrumentation_mode",
    "target_field_registry_id",
    "full_checkpoint_selector_id",
    "observation_count",
    "ordered_observation_ids",
)
V2_CLOCK_UNAVAILABLE_REASONS: Final = (
    "ARTIFACT_BOUND_EXCEEDED",
    "OBSERVER_INTERNAL_ERROR",
    "PROCESS_LOSS_VOLATILE_MARKER_STATE",
    "SOURCE_CLOCK_UNAVAILABLE",
    "TARGET_BOUNDARY_NOT_REACHED",
)
CHECKPOINT_BINDING_STATUSES: Final = (
    "EXACT_MARKER",
    "UNAVAILABLE_MARKER_OBSERVER_FAILURE",
    "UNAVAILABLE_TARGET_BOUNDARY_NOT_REACHED",
)
CHECKPOINT_CONTEXT_TO_FIELD_REASON: Final = {
    "ARTIFACT_BOUND_EXCEEDED": ("CHECKPOINT_PLACEHOLDER_ARTIFACT_BOUND_EXCEEDED"),
    "OBSERVER_INTERNAL_ERROR": ("CHECKPOINT_PLACEHOLDER_OBSERVER_INTERNAL_ERROR"),
    "SOURCE_CLOCK_UNAVAILABLE": ("CHECKPOINT_PLACEHOLDER_SOURCE_CLOCK_UNAVAILABLE"),
    "TARGET_BOUNDARY_NOT_REACHED": (
        "CHECKPOINT_PLACEHOLDER_TARGET_BOUNDARY_NOT_REACHED"
    ),
}
MAXIMUM_SCOPE_PROFILE_DOMAIN: Final = (
    "RiskYieldMMA2MStep2ExternalSchemaV2MaximumConstraintScopeProfileV1V4_9F_RawV8"
)
MAXIMUM_CHECKPOINT_OUTCOMES: Final = (
    "EXACT_MARKER",
    "ARTIFACT_BOUND_EXCEEDED",
    "OBSERVER_INTERNAL_ERROR",
    "SOURCE_CLOCK_UNAVAILABLE",
    "TARGET_BOUNDARY_NOT_REACHED",
)
MAXIMUM_CHECKPOINT_OUTCOME_BINDINGS: Final = {
    "EXACT_MARKER": ("EXACT_MARKER", None, None),
    "ARTIFACT_BOUND_EXCEEDED": (
        "UNAVAILABLE_MARKER_OBSERVER_FAILURE",
        "ARTIFACT_BOUND_EXCEEDED",
        "CHECKPOINT_PLACEHOLDER_ARTIFACT_BOUND_EXCEEDED",
    ),
    "OBSERVER_INTERNAL_ERROR": (
        "UNAVAILABLE_MARKER_OBSERVER_FAILURE",
        "OBSERVER_INTERNAL_ERROR",
        "CHECKPOINT_PLACEHOLDER_OBSERVER_INTERNAL_ERROR",
    ),
    "SOURCE_CLOCK_UNAVAILABLE": (
        "UNAVAILABLE_MARKER_OBSERVER_FAILURE",
        "SOURCE_CLOCK_UNAVAILABLE",
        "CHECKPOINT_PLACEHOLDER_SOURCE_CLOCK_UNAVAILABLE",
    ),
    "TARGET_BOUNDARY_NOT_REACHED": (
        "UNAVAILABLE_TARGET_BOUNDARY_NOT_REACHED",
        "TARGET_BOUNDARY_NOT_REACHED",
        "CHECKPOINT_PLACEHOLDER_TARGET_BOUNDARY_NOT_REACHED",
    ),
}
MAXIMUM_SCOPE_PROFILE_COUNT: Final = 408


def _build_marker_contract(parsed: dict[str, Any]) -> dict[str, Any]:
    _require(tuple(parsed["markers"]) == MARKER_KINDS, "marker-kind tuple drifted")
    _require(
        tuple(parsed["checkpoint_markers"]) == FULL_CHECKPOINT_MARKER_KINDS,
        "full-checkpoint marker tuple drifted",
    )
    records = [
        {
            "checkpoint_marker_kind": marker_kind,
            "applicable_operation_kinds": list(CHECKPOINT_OPERATION_MAP[marker_kind]),
        }
        for marker_kind in FULL_CHECKPOINT_MARKER_KINDS
    ]
    payload = {
        "contract_version": "riskyieldmm_raw_v8_marker_contract_v1",
        "ordered_marker_kinds": list(MARKER_KINDS),
        "ordered_full_checkpoint_marker_kinds": list(FULL_CHECKPOINT_MARKER_KINDS),
        "ordered_checkpoint_operation_records": records,
        "forbidden_full_checkpoint_marker_kinds": list(
            FORBIDDEN_FULL_CHECKPOINT_MARKER_KINDS
        ),
        "minimum_marker_ring_capacity": 8,
        "maximum_marker_ring_capacity": 4_096,
        "maximum_checkpoint_selector_length": 64,
        "stable_checkpoint_requires_attempt": True,
    }
    return _standalone_envelope(
        DOMAINS["marker_contract"], payload, "marker_contract_id"
    )


def _checkpoint_selector_entry(
    operation_kind: str,
    position: int,
    marker_kind: str,
    occurrence: int,
) -> dict[str, Any]:
    _require(operation_kind in CHECKPOINT_OPERATION_MAP[marker_kind], "bad selector")
    payload = {
        "selector_position": position,
        "operation_kind": operation_kind,
        "checkpoint_marker_kind": marker_kind,
        "occurrence_index_within_kind": occurrence,
    }
    return _standalone_envelope(
        DOMAINS["checkpoint_selector_entry"],
        payload,
        "checkpoint_selector_entry_id",
    )


def _complete_checkpoint_selector(
    operation_kind: str, marker_kinds: tuple[str, ...]
) -> dict[str, Any]:
    occurrences: Counter[str] = Counter()
    entries: list[dict[str, Any]] = []
    for position, marker_kind in enumerate(marker_kinds, 1):
        occurrences[marker_kind] += 1
        entries.append(
            _checkpoint_selector_entry(
                operation_kind,
                position,
                marker_kind,
                occurrences[marker_kind],
            )
        )
    identity_payload = {
        "operation_kind": operation_kind,
        "selector_length": len(entries),
        "ordered_checkpoint_selector_entry_ids": [
            item["checkpoint_selector_entry_id"] for item in entries
        ],
    }
    selector = {
        "canonicalization_version": CANONICALIZATION_VERSION,
        "measurement_schema_version": MEASUREMENT_SCHEMA_VERSION,
        "record_domain": DOMAINS["checkpoint_selector"],
        "operation_kind": operation_kind,
        "ordered_entries": entries,
        "selector_length": len(entries),
        "ordered_checkpoint_selector_entry_ids": identity_payload[
            "ordered_checkpoint_selector_entry_ids"
        ],
        "checkpoint_selector_id": _semantic_id(
            DOMAINS["checkpoint_selector"], identity_payload
        ),
    }
    _require(len(entries) <= 64, "selector exceeds 64 entries")
    return selector


def _build_checkpoint_selector_catalog() -> list[dict[str, Any]]:
    catalog: list[dict[str, Any]] = []
    for catalog_name, (
        operation_kind,
        marker_kinds,
    ) in CHECKPOINT_SELECTOR_DEFINITIONS.items():
        catalog.append(
            {
                "catalog_name": catalog_name,
                "selector": _complete_checkpoint_selector(operation_kind, marker_kinds),
            }
        )
    maximum_marker_kinds = tuple("PARSER_UNIT_CONVERGED" for _ in range(64))
    catalog.append(
        {
            "catalog_name": "INGRESS_MAX64_PARSER_UNITS",
            "selector": _complete_checkpoint_selector("INGRESS", maximum_marker_kinds),
        }
    )
    _require(len(catalog) == 9, "selector catalog must contain exactly nine")
    return sorted(catalog, key=lambda item: item["selector"]["checkpoint_selector_id"])


def _clock_span_v2(
    clock_domain: str,
    *,
    started: int | None = None,
    completed: int | None = None,
    unavailable_reason: str | None = None,
) -> dict[str, Any]:
    if unavailable_reason is None:
        _require(
            isinstance(started, int)
            and not isinstance(started, bool)
            and isinstance(completed, int)
            and not isinstance(completed, bool)
            and 0 <= started <= completed <= SAFE_UINT_MAX,
            "available V2 clock span is invalid",
        )
        status = "AVAILABLE"
    else:
        _require(
            unavailable_reason in V2_CLOCK_UNAVAILABLE_REASONS,
            "unknown V2 clock-span reason",
        )
        _require(started is None and completed is None, "unavailable span has offsets")
        status = "UNAVAILABLE"
    return {
        "clock_domain": clock_domain,
        "span_status": status,
        "started_offset_nanoseconds": started,
        "completed_offset_nanoseconds": completed,
        "unavailable_reason": unavailable_reason,
    }


def _observation_context_v2(
    *,
    role: str,
    operation_kind: str,
    instrumentation_mode: str,
    candidate_id: str,
    attempt_id: str | None,
    registry_id: str,
    selector: dict[str, Any] | None = None,
    selector_position: int | None = None,
    binding_status: str | None = None,
    binding_reason: str | None = None,
    marker_ordinal: int | None = None,
    actual_marker_kind: str | None = None,
    maximal_spans: bool = False,
) -> dict[str, Any]:
    checkpoint = role == "STABLE_CHECKPOINT"
    entry: dict[str, Any] | None = None
    if checkpoint:
        _require(attempt_id is not None, "stable checkpoint requires an attempt")
        _require(selector is not None, "checkpoint requires selector")
        _require(
            isinstance(selector_position, int)
            and not isinstance(selector_position, bool)
            and 1 <= selector_position <= selector["selector_length"],
            "checkpoint selector position is invalid",
        )
        entry = selector["ordered_entries"][selector_position - 1]
        _require(
            binding_status in CHECKPOINT_BINDING_STATUSES,
            "checkpoint binding status is invalid",
        )
        if binding_status == "EXACT_MARKER":
            _require(
                isinstance(marker_ordinal, int)
                and not isinstance(marker_ordinal, bool)
                and marker_ordinal > 0
                and actual_marker_kind == entry["checkpoint_marker_kind"]
                and binding_reason is None,
                "exact-marker binding truth is invalid",
            )
            start = SAFE_UINT_MAX if maximal_spans else 10
            spans = tuple(
                _clock_span_v2(domain, started=start, completed=start)
                for domain in ("OBSERVER_MONOTONIC", "BOOTTIME", "EVENT_LOOP")
            )
        else:
            if binding_status == "UNAVAILABLE_TARGET_BOUNDARY_NOT_REACHED":
                _require(
                    binding_reason == "TARGET_BOUNDARY_NOT_REACHED",
                    "not-reached binding reason drifted",
                )
            else:
                _require(
                    binding_reason
                    in {
                        "SOURCE_CLOCK_UNAVAILABLE",
                        "ARTIFACT_BOUND_EXCEEDED",
                        "OBSERVER_INTERNAL_ERROR",
                    },
                    "observer-failure binding reason drifted",
                )
            _require(
                marker_ordinal is None and actual_marker_kind is None,
                "placeholder cannot carry actual marker truth",
            )
            spans = tuple(
                _clock_span_v2(domain, unavailable_reason=binding_reason)
                for domain in ("OBSERVER_MONOTONIC", "BOOTTIME", "EVENT_LOOP")
            )
    else:
        _require(
            selector is None
            and selector_position is None
            and binding_status is None
            and binding_reason is None
            and marker_ordinal is None
            and actual_marker_kind is None,
            "non-checkpoint context carries selector/binding truth",
        )
        start = SAFE_UINT_MAX if maximal_spans else 10
        spans = tuple(
            _clock_span_v2(domain, started=start, completed=start)
            for domain in ("OBSERVER_MONOTONIC", "BOOTTIME", "EVENT_LOOP")
        )
    payload = {
        "observation_role": role,
        "operation_kind": operation_kind,
        "instrumentation_mode": instrumentation_mode,
        "candidate_id": candidate_id,
        "attempt_id": attempt_id,
        "target_field_registry_id": registry_id,
        "marker_ordinal": marker_ordinal,
        "checkpoint_marker_kind": actual_marker_kind,
        "full_checkpoint_selector_id": (
            selector["checkpoint_selector_id"] if selector is not None else None
        ),
        "checkpoint_selector_position": selector_position,
        "checkpoint_selector_entry_id": (
            entry["checkpoint_selector_entry_id"] if entry is not None else None
        ),
        "expected_checkpoint_marker_kind": (
            entry["checkpoint_marker_kind"] if entry is not None else None
        ),
        "expected_occurrence_index_within_kind": (
            entry["occurrence_index_within_kind"] if entry is not None else None
        ),
        "checkpoint_binding_status": binding_status,
        "checkpoint_binding_unavailable_reason": binding_reason,
        "observer_clock_span": spans[0],
        "boottime_clock_span": spans[1],
        "loop_clock_span": spans[2],
    }
    _require(tuple(payload) == V2_CONTEXT_PAYLOAD_MEMBERS, "V2 context key drift")
    return _standalone_envelope(
        DOMAINS["observation_context"], payload, "observation_context_id"
    )


def _field_observation_rebound(
    field: dict[str, Any], *, context_id: str
) -> dict[str, Any]:
    payload = {
        member: (context_id if member == "observation_context_id" else field[member])
        for member in FIELD_OBSERVATION_PAYLOAD_MEMBERS
    }
    return _standalone_envelope(
        DOMAINS["field_observation"], payload, "field_observation_id"
    )


def _target_observation_v2(
    context: dict[str, Any], fields: list[dict[str, Any]]
) -> dict[str, Any]:
    context_id = context["observation_context_id"]
    _require(len(fields) == 185, "V2 observation must contain all 185 fields")
    _require(
        all(item["observation_context_id"] == context_id for item in fields),
        "V2 fields do not bind the embedded context",
    )
    payload = {
        "observation_context": context,
        "observation_context_id": context_id,
        "field_observations": fields,
    }
    return _standalone_envelope(
        DOMAINS["target_observation"], payload, "observation_id"
    )


def _checkpoint_placeholder_observation_v2(
    *,
    context: dict[str, Any],
    metadata: list[dict[str, Any]],
) -> dict[str, Any]:
    context_reason = context["checkpoint_binding_unavailable_reason"]
    _require(
        context_reason in CHECKPOINT_CONTEXT_TO_FIELD_REASON,
        "placeholder has no field-level reason mapping",
    )
    field_reason = CHECKPOINT_CONTEXT_TO_FIELD_REASON[context_reason]
    fields = [
        _field_observation_envelope(
            registry_id=context["target_field_registry_id"],
            context_id=context["observation_context_id"],
            descriptor=item["descriptor"],
            availability="UNAVAILABLE",
            value=None,
            observation_method="NOT_ATTEMPTED",
            observation_attempt="NOT_ATTEMPTED",
            adapter_span_status="NOT_APPLICABLE",
            started_offset=None,
            completed_offset=None,
            unavailable_reason=field_reason,
        )
        for item in metadata
    ]
    return _target_observation_v2(context, fields)


def _target_observation_root_v2(
    *,
    candidate_id: str,
    attempt_id: str | None,
    operation_kind: str,
    instrumentation_mode: str,
    registry_id: str,
    selector_id: str | None,
    ordered_observation_ids: list[str],
) -> dict[str, Any]:
    payload = {
        "candidate_id": candidate_id,
        "attempt_id": attempt_id,
        "operation_kind": operation_kind,
        "instrumentation_mode": instrumentation_mode,
        "target_field_registry_id": registry_id,
        "full_checkpoint_selector_id": selector_id,
        "observation_count": len(ordered_observation_ids),
        "ordered_observation_ids": ordered_observation_ids,
    }
    _require(tuple(payload) == V2_ROOT_PAYLOAD_MEMBERS, "V2 root key drift")
    return _standalone_envelope(
        DOMAINS["target_observation_root"],
        payload,
        "target_observation_root_sha256",
    )


def _maximum_root_family(
    *,
    root_family_kind: str,
    mode_attempt_pairs: tuple[tuple[str, str], ...],
    selector_catalog_position: int | None,
    selector_catalog_name: str | None,
    checkpoint_selector_id: str | None,
    selector_length: int,
    observation_count: int,
    role_sequence_formula: str,
    measured_roles: tuple[str, ...],
    selector_present: bool,
) -> dict[str, Any]:
    family = {
        "root_family_kind": root_family_kind,
        "ordered_instrumentation_mode_attempt_presence_pairs": [
            list(pair) for pair in mode_attempt_pairs
        ],
        "selector_catalog_position": selector_catalog_position,
        "selector_catalog_name": selector_catalog_name,
        "checkpoint_selector_id": checkpoint_selector_id,
        "selector_length": selector_length,
        "observation_count": observation_count,
        "role_sequence_formula": role_sequence_formula,
        "ordered_measured_observation_roles": list(measured_roles),
        "selector_present": selector_present,
    }
    _require(
        tuple(family)
        == (
            "root_family_kind",
            "ordered_instrumentation_mode_attempt_presence_pairs",
            "selector_catalog_position",
            "selector_catalog_name",
            "checkpoint_selector_id",
            "selector_length",
            "observation_count",
            "role_sequence_formula",
            "ordered_measured_observation_roles",
            "selector_present",
        ),
        "maximum root-family member order drifted",
    )
    return family


def _build_maximum_constraint_scope_profile_catalog(
    *,
    specs: dict[str, dict[str, Any]],
    selector_catalog: list[dict[str, Any]],
    target_registry: dict[str, Any],
    marker_contract: dict[str, Any],
) -> list[dict[str, Any]]:
    profiles: list[dict[str, Any]] = []

    def add(
        *,
        profile_kind: str,
        constraint_scope: str,
        measured_type_name: str,
        operation_kind: str,
        source_pointers: list[str],
        source_ids: list[str],
        selector_catalog_position: int | None,
        selector_catalog_name: str | None,
        checkpoint_selector_id: str | None,
        checkpoint_selector_entry_id: str | None,
        expected_checkpoint_marker_kind: str | None,
        expected_occurrence_index_within_kind: int | None,
        selector_position: int | None,
        checkpoint_outcome: str | None,
        checkpoint_binding_status: str | None,
        checkpoint_binding_unavailable_reason: str | None,
        checkpoint_field_unavailable_reason: str | None,
        root_families: list[dict[str, Any]],
        schedule_formula: str,
    ) -> None:
        _require(
            len(source_pointers) == len(source_ids),
            "maximum scope-profile source authority cardinality differs",
        )
        payload = {
            "profile_position": len(profiles) + 1,
            "profile_kind": profile_kind,
            "constraint_scope": constraint_scope,
            "measured_type_name": measured_type_name,
            "operation_kind": operation_kind,
            "ordered_source_authority_pointers": source_pointers,
            "ordered_source_authority_ids": source_ids,
            "selector_catalog_position": selector_catalog_position,
            "selector_catalog_name": selector_catalog_name,
            "checkpoint_selector_id": checkpoint_selector_id,
            "checkpoint_selector_entry_id": checkpoint_selector_entry_id,
            "expected_checkpoint_marker_kind": expected_checkpoint_marker_kind,
            "expected_occurrence_index_within_kind": (
                expected_occurrence_index_within_kind
            ),
            "selector_position": selector_position,
            "checkpoint_outcome": checkpoint_outcome,
            "checkpoint_binding_status": checkpoint_binding_status,
            "checkpoint_binding_unavailable_reason": (
                checkpoint_binding_unavailable_reason
            ),
            "checkpoint_field_unavailable_reason": (
                checkpoint_field_unavailable_reason
            ),
            "ordered_admissible_root_families": root_families,
            "application_schedule_formula": schedule_formula,
        }
        profile = {
            **payload,
            "maximum_constraint_scope_profile_id": _semantic_id(
                MAXIMUM_SCOPE_PROFILE_DOMAIN,
                payload,
            ),
        }
        profiles.append(profile)

    for operation_kind in OPERATION_KINDS:
        spec = specs[operation_kind]
        add(
            profile_kind="OUTER_RESULT_BOUNDARY_FIXTURE",
            constraint_scope="FROZEN_FIXTURE",
            measured_type_name="CapacityMeasurementOperationResultEvidence",
            operation_kind=operation_kind,
            source_pointers=[f"/fixture_records/operation_specs/{operation_kind}"],
            source_ids=[spec["operation_spec_id"]],
            selector_catalog_position=None,
            selector_catalog_name=None,
            checkpoint_selector_id=None,
            checkpoint_selector_entry_id=None,
            expected_checkpoint_marker_kind=None,
            expected_occurrence_index_within_kind=None,
            selector_position=None,
            checkpoint_outcome=None,
            checkpoint_binding_status=None,
            checkpoint_binding_unavailable_reason=None,
            checkpoint_field_unavailable_reason=None,
            root_families=[],
            schedule_formula="OUTER_RESULT_SIGNED_SPEC_SINGLE_APPLICATION_V1",
        )

    startup_family = _maximum_root_family(
        root_family_kind="STARTUP_RECOVERY_ONE",
        mode_attempt_pairs=(("OFF", "NULL"), ("ON", "NULL")),
        selector_catalog_position=None,
        selector_catalog_name=None,
        checkpoint_selector_id=None,
        selector_length=0,
        observation_count=1,
        role_sequence_formula="STARTUP_RECOVERY_ONE_V1",
        measured_roles=("STARTUP_RECOVERY",),
        selector_present=False,
    )
    selector_free_family = _maximum_root_family(
        root_family_kind="ORDINARY_SELECTOR_FREE_THREE",
        mode_attempt_pairs=(
            ("OFF", "NULL"),
            ("OFF", "NON_NULL"),
            ("ON", "NULL"),
        ),
        selector_catalog_position=None,
        selector_catalog_name=None,
        checkpoint_selector_id=None,
        selector_length=0,
        observation_count=3,
        role_sequence_formula="ORDINARY_BEFORE_CHECKPOINTS_AFTER_AGGREGATE_V1",
        measured_roles=(
            "BEFORE_OPERATION",
            "AFTER_OPERATION",
            "OPERATION_AGGREGATE",
        ),
        selector_present=False,
    )

    selector_rows_by_operation: dict[str, list[tuple[int, dict[str, Any]]]] = {
        operation_kind: [] for operation_kind in OPERATION_KINDS
    }
    for catalog_position, catalog_record in enumerate(selector_catalog, 1):
        selector = catalog_record["selector"]
        selector_rows_by_operation[selector["operation_kind"]].append(
            (catalog_position, catalog_record)
        )

    for operation_kind in OPERATION_KINDS:
        source_pointers = ["/target_field_registry", "/marker_contract"]
        source_ids = [
            target_registry["target_field_registry_id"],
            marker_contract["marker_contract_id"],
        ]
        families = [startup_family, selector_free_family]
        for catalog_position, catalog_record in selector_rows_by_operation[
            operation_kind
        ]:
            selector = catalog_record["selector"]
            source_pointers.append(
                f"/checkpoint_selector_catalog/{catalog_position - 1}/selector"
            )
            source_ids.append(selector["checkpoint_selector_id"])
            families.append(
                _maximum_root_family(
                    root_family_kind="ORDINARY_SELECTOR_BOUND",
                    mode_attempt_pairs=(("ON", "NON_NULL"),),
                    selector_catalog_position=catalog_position,
                    selector_catalog_name=catalog_record["catalog_name"],
                    checkpoint_selector_id=selector["checkpoint_selector_id"],
                    selector_length=selector["selector_length"],
                    observation_count=selector["selector_length"] + 3,
                    role_sequence_formula=(
                        "ORDINARY_BEFORE_CHECKPOINTS_AFTER_AGGREGATE_V1"
                    ),
                    measured_roles=(
                        "BEFORE_OPERATION",
                        "AFTER_OPERATION",
                        "OPERATION_AGGREGATE",
                    ),
                    selector_present=True,
                )
            )
        add(
            profile_kind="NON_CHECKPOINT_ROOT_FAMILY",
            constraint_scope="FROZEN_ROOT_APPLICATION",
            measured_type_name="TargetObservationV2",
            operation_kind=operation_kind,
            source_pointers=source_pointers,
            source_ids=source_ids,
            selector_catalog_position=None,
            selector_catalog_name=None,
            checkpoint_selector_id=None,
            checkpoint_selector_entry_id=None,
            expected_checkpoint_marker_kind=None,
            expected_occurrence_index_within_kind=None,
            selector_position=None,
            checkpoint_outcome=None,
            checkpoint_binding_status=None,
            checkpoint_binding_unavailable_reason=None,
            checkpoint_field_unavailable_reason=None,
            root_families=families,
            schedule_formula="FINITE_UNION_OF_LISTED_ROOT_FAMILY_SCHEDULES_V1",
        )

    for catalog_position, catalog_record in enumerate(selector_catalog, 1):
        selector = catalog_record["selector"]
        for entry in selector["ordered_entries"]:
            family = _maximum_root_family(
                root_family_kind="ORDINARY_SELECTOR_BOUND",
                mode_attempt_pairs=(("ON", "NON_NULL"),),
                selector_catalog_position=catalog_position,
                selector_catalog_name=catalog_record["catalog_name"],
                checkpoint_selector_id=selector["checkpoint_selector_id"],
                selector_length=selector["selector_length"],
                observation_count=selector["selector_length"] + 3,
                role_sequence_formula=(
                    "ORDINARY_BEFORE_CHECKPOINTS_AFTER_AGGREGATE_V1"
                ),
                measured_roles=("STABLE_CHECKPOINT",),
                selector_present=True,
            )
            for outcome in MAXIMUM_CHECKPOINT_OUTCOMES:
                (
                    binding_status,
                    binding_unavailable_reason,
                    field_unavailable_reason,
                ) = MAXIMUM_CHECKPOINT_OUTCOME_BINDINGS[outcome]
                add(
                    profile_kind="CHECKPOINT_ROOT_COORDINATE",
                    constraint_scope="FROZEN_ROOT_APPLICATION",
                    measured_type_name="TargetObservationV2",
                    operation_kind=selector["operation_kind"],
                    source_pointers=[
                        "/target_field_registry",
                        "/marker_contract",
                        (
                            "/checkpoint_selector_catalog/"
                            f"{catalog_position - 1}/selector"
                        ),
                    ],
                    source_ids=[
                        target_registry["target_field_registry_id"],
                        marker_contract["marker_contract_id"],
                        selector["checkpoint_selector_id"],
                    ],
                    selector_catalog_position=catalog_position,
                    selector_catalog_name=catalog_record["catalog_name"],
                    checkpoint_selector_id=selector["checkpoint_selector_id"],
                    checkpoint_selector_entry_id=entry["checkpoint_selector_entry_id"],
                    expected_checkpoint_marker_kind=entry["checkpoint_marker_kind"],
                    expected_occurrence_index_within_kind=entry[
                        "occurrence_index_within_kind"
                    ],
                    selector_position=entry["selector_position"],
                    checkpoint_outcome=outcome,
                    checkpoint_binding_status=binding_status,
                    checkpoint_binding_unavailable_reason=(binding_unavailable_reason),
                    checkpoint_field_unavailable_reason=field_unavailable_reason,
                    root_families=[family],
                    schedule_formula=(
                        "SELECTOR_PRESENT_2N_PLUS_3_CALLS_187N_PLUS_2_EVALS_"
                        "1872N_PLUS_7_NODES_V1"
                    ),
                )

    _require(
        len(profiles) == MAXIMUM_SCOPE_PROFILE_COUNT,
        "maximum constraint-scope profile count differs",
    )
    _require(
        [profile["profile_position"] for profile in profiles]
        == list(range(1, MAXIMUM_SCOPE_PROFILE_COUNT + 1)),
        "maximum constraint-scope profile positions differ",
    )
    _require(
        len({profile["maximum_constraint_scope_profile_id"] for profile in profiles})
        == MAXIMUM_SCOPE_PROFILE_COUNT,
        "maximum constraint-scope profile IDs are not unique",
    )
    return profiles


def _operation_contracts(
    *, maximum_constraint_scope_profiles: list[dict[str, Any]]
) -> dict[str, Any]:
    value_union_variants = [
        {"kind": "BOOL", "members": ["kind", "value"]},
        {
            "kind": "DURATION_BOUND",
            "members": [
                "kind",
                "relation",
                "lower_nanoseconds",
                "upper_nanoseconds",
            ],
        },
        {"kind": "FIXED_UINT_MAP", "members": ["kind", "ordered"]},
        {"kind": "OPTIONAL_TEXT", "members": ["kind", "present", "value"]},
        {"kind": "OPTIONAL_UINT", "members": ["kind", "present", "value"]},
        {"kind": "TEXT", "members": ["kind", "value"]},
        {"kind": "TEXT_LIST", "members": ["kind", "values"]},
        {"kind": "UINT", "members": ["kind", "value"]},
        {"kind": "UINT_LIST", "members": ["kind", "values"]},
    ]
    spec_variants = [
        {
            "operation_kind": operation_kind,
            "spec_type": SPEC_TYPES[operation_kind],
            "spec_body_members": list(SPEC_BODY_MEMBERS[operation_kind]),
        }
        for operation_kind in OPERATION_KINDS
    ]
    result_variants = [
        {
            "operation_kind": operation_kind,
            "result_type": RESULT_TYPES[operation_kind],
            "result_body_members": list(RESULT_BODY_MEMBERS[operation_kind]),
        }
        for operation_kind in OPERATION_KINDS
    ]
    record_types = [
        {
            "record_type": "OperationSpec",
            "record_domain": DOMAINS["operation_spec"],
            "identity_payload_members": ["operation_kind", "spec_type", "spec"],
            "identity_field": "operation_spec_id",
        },
        {
            "record_type": "OperationDeclaration",
            "record_domain": DOMAINS["operation_declaration"],
            "identity_payload_members": list(DECLARATION_PAYLOAD_MEMBERS),
            "identity_field": "declaration_id",
        },
        {
            "record_type": "DispatchWindowEvidence",
            "record_domain": DOMAINS["dispatch_window"],
            "identity_payload_members": list(DISPATCH_WINDOW_PAYLOAD_MEMBERS),
            "identity_field": "dispatch_window_evidence_id",
        },
        {
            "record_type": "DueDecisionClockEvidence",
            "record_domain": DOMAINS["due_decision_clock"],
            "identity_payload_members": list(DUE_DECISION_CLOCK_PAYLOAD_MEMBERS),
            "identity_field": "due_decision_clock_evidence_id",
        },
        {
            "record_type": "OperationResultEvidence",
            "record_domain": DOMAINS["operation_result"],
            "identity_payload_members": [
                "candidate_id",
                "attempt_id",
                "operation_kind",
                "result_type",
                "result",
            ],
            "identity_field": "result_evidence_id",
        },
        {
            "record_type": "SourceErrorDetail",
            "record_domain": DOMAINS["source_error_detail"],
            "identity_payload_members": list(SOURCE_ERROR_DETAIL_PAYLOAD_MEMBERS),
            "identity_field": "source_error_detail_sha256",
            "maximum_semantic_preimage_bytes": 2_048,
        },
        {
            "record_type": "TargetObservationContextV2",
            "record_domain": DOMAINS["observation_context"],
            "identity_payload_members": list(V2_CONTEXT_PAYLOAD_MEMBERS),
            "identity_field": "observation_context_id",
        },
        {
            "record_type": "TargetFieldObservation",
            "record_domain": DOMAINS["field_observation"],
            "identity_payload_members": list(FIELD_OBSERVATION_PAYLOAD_MEMBERS),
            "identity_field": "field_observation_id",
        },
        {
            "record_type": "TargetObservationV2",
            "record_domain": DOMAINS["target_observation"],
            "identity_payload_members": list(V2_OBSERVATION_PAYLOAD_MEMBERS),
            "identity_field": "observation_id",
        },
        {
            "record_type": "TargetObservationRootV2",
            "record_domain": DOMAINS["target_observation_root"],
            "identity_payload_members": list(V2_ROOT_PAYLOAD_MEMBERS),
            "identity_field": "target_observation_root_sha256",
        },
        {
            "record_type": "OperationCounterSnapshotSchema",
            "record_domain": DOMAINS["counter_schema"],
            "identity_payload_members": [
                "counter_field_count",
                "ordered_counter_field_ids",
                "monotone_counter_field_ids",
            ],
            "identity_field": "counter_schema_id",
        },
        {
            "record_type": "OperationCounterSnapshot",
            "record_domain": None,
            "identity_payload_members": [
                "counter_schema_id",
                "availability_bitmap",
                "values",
            ],
            "identity_field": None,
        },
    ]
    source_error_detail_payload = {
        "field_id": "kernel.siocinq_unread_octets",
        "observation_method": "LINUX_IOCTL",
        "source_failure_phase": "SOURCE_ADAPTER",
        "source_errno_number": 5,
        "source_errno_name": "EIO",
        "source_error_class": "builtins.OSError",
    }
    _require(
        tuple(source_error_detail_payload) == SOURCE_ERROR_DETAIL_PAYLOAD_MEMBERS,
        "source-error-detail fixture is not the exact six-key payload",
    )
    source_error_detail_preimage = {
        "canonicalization_version": CANONICALIZATION_VERSION,
        "domain": DOMAINS["source_error_detail"],
        "payload": source_error_detail_payload,
        "schema_version": MEASUREMENT_SCHEMA_VERSION,
    }
    registry_definition_type_members = {
        "AvailabilityStateRule": [
            "availability",
            "value_policy",
            "reason_policy",
            "censoring_policy",
            "attempt_policy",
            "adapter_span_policy",
        ],
        "AttemptStateErrorForms": [
            "attempt_state",
            "permitted_error_forms",
            "permitted_failure_phases",
            "adapter_span_policy",
        ],
        "CrossFieldConstraintDefinition": [
            "cross_field_constraint_id",
            "count_field_id",
            "sequence_field_id",
            "kind_field_id",
            "activation_condition",
            "maximum_items",
            "sequence_order",
            "cardinality_rule",
            "pairing_rule",
        ],
        "ErrorFormDefinition": [
            "error_form",
            "errno_pair_policy",
            "error_class_policy",
            "error_digest_policy",
            "class_digest_pair_policy",
        ],
        "StatusReasonPolicyDefinition": [
            "status_reason_policy_id",
            "availability_state_rules",
            "reason_rules",
            "error_form_definitions",
        ],
        "StatusReasonRule": [
            "reason",
            "required_availability",
            "context_predicate",
            "attempt_state_error_forms",
        ],
        "ValueConstraintDefinition": [
            "value_constraint_id",
            "value_kind",
            "scalar_profile",
            "vocabulary_id",
            "integer_minimum",
            "integer_maximum",
            "text_minimum_utf8_bytes",
            "text_maximum_utf8_bytes",
            "text_ascii_pattern",
            "decimal_maximum",
            "collection_item_constraint_id",
            "external_authority_profile",
        ],
        "ValueShapeDefinition": [
            "value_shape_id",
            "container_kind",
            "minimum_items",
            "maximum_items",
            "ordered_keys",
        ],
        "VocabularyDefinition": ["vocabulary_id", "members"],
    }
    contracts = {
        "semantic_id_preimage_members": [
            "canonicalization_version",
            "domain",
            "payload",
            "schema_version",
        ],
        "standalone_envelope_prefix_members": [
            "canonicalization_version",
            "measurement_schema_version",
            "record_domain",
        ],
        "semantic_preimage_structural_scan": {
            "byte_bound_precedes_json_decode": True,
            "node_count_limit": None,
        },
        "clock_span_members": list(CLOCK_SPAN_MEMBERS),
        "value_union_variants": value_union_variants,
        "operation_spec_variants": spec_variants,
        "operation_result_variants": result_variants,
        "record_types": record_types,
        "registry_definition_type_members": registry_definition_type_members,
        "source_error_detail_fixture": {
            "payload": source_error_detail_payload,
            "source_error_detail_sha256": _semantic_id(
                DOMAINS["source_error_detail"], source_error_detail_payload
            ),
            "semantic_preimage_bytes": len(
                _canonical_bytes(source_error_detail_preimage)
            ),
            "maximum_semantic_preimage_bytes": 2_048,
        },
    }
    contracts.update(
        {
            "removed_v1_tags": list(REMOVED_V1_TAGS),
            "current_spec_type_by_operation": {
                key: SPEC_TYPES[key] for key in OPERATION_KINDS
            },
            "current_result_type_by_operation": {
                key: RESULT_TYPES[key] for key in OPERATION_KINDS
            },
            "checkpoint_binding_statuses": list(CHECKPOINT_BINDING_STATUSES),
            "checkpoint_context_to_field_reason": dict(
                sorted(CHECKPOINT_CONTEXT_TO_FIELD_REASON.items())
            ),
            "checkpoint_placeholder_context_predicate_by_field_reason": {
                "CHECKPOINT_PLACEHOLDER_ARTIFACT_BOUND_EXCEEDED": (
                    "V2_CHECKPOINT_PLACEHOLDER_ARTIFACT_BOUND"
                ),
                "CHECKPOINT_PLACEHOLDER_OBSERVER_INTERNAL_ERROR": (
                    "V2_CHECKPOINT_PLACEHOLDER_OBSERVER_INTERNAL_ERROR"
                ),
                "CHECKPOINT_PLACEHOLDER_SOURCE_CLOCK_UNAVAILABLE": (
                    "V2_CHECKPOINT_PLACEHOLDER_SOURCE_CLOCK_UNAVAILABLE"
                ),
                "CHECKPOINT_PLACEHOLDER_TARGET_BOUNDARY_NOT_REACHED": (
                    "V2_CHECKPOINT_PLACEHOLDER_TARGET_BOUNDARY_NOT_REACHED"
                ),
            },
            "checkpoint_placeholder_discharge_rule": (
                "MATCHING_TARGET_OBSERVATION_V2_STABLE_CHECKPOINT_"
                "UNAVAILABLE_MARKER_OBSERVER_FAILURE_CONTEXT_REQUIRED"
            ),
            "target_observation_v2_payload_members": list(
                V2_OBSERVATION_PAYLOAD_MEMBERS
            ),
            "target_observation_context_v2_payload_members": list(
                V2_CONTEXT_PAYLOAD_MEMBERS
            ),
            "target_observation_root_v2_payload_members": list(V2_ROOT_PAYLOAD_MEMBERS),
            "operation_result_canonical_byte_ceiling": (OPERATION_RESULT_MAX_BYTES),
            "local_shutdown_intrinsic_limit_relations": [
                (
                    "maximum_terminal_ingress_plaintext_octets"
                    "<=16384*maximum_terminal_ingress_batches"
                ),
                (
                    "2*maximum_terminal_ingress_parser_units"
                    "<=maximum_terminal_ingress_plaintext_octets"
                ),
                ("maximum_terminal_tls_records<=maximum_terminal_ingress_batches"),
                (
                    "maximum_terminal_ingress_automatic_outputs"
                    "<=maximum_terminal_ingress_parser_units"
                ),
                (
                    "maximum_websocket_send_attempts"
                    "<=256*(1+maximum_terminal_ingress_automatic_outputs)"
                ),
            ],
            "local_shutdown_scalar_limit_domains": [
                {
                    "member_name": member_name,
                    "integer_minimum": minimum,
                    "integer_maximum": maximum,
                }
                for member_name, minimum, maximum in (
                    ("maximum_terminal_ingress_batches", 1, SAFE_UINT_MAX),
                    (
                        "maximum_terminal_ingress_ciphertext_octets",
                        1,
                        SAFE_UINT_MAX,
                    ),
                    (
                        "maximum_terminal_ingress_plaintext_octets",
                        1,
                        SAFE_UINT_MAX,
                    ),
                    ("maximum_terminal_socket_receive_calls", 1, SAFE_UINT_MAX),
                    ("maximum_terminal_tls_records", 1, SAFE_UINT_MAX),
                    (
                        "maximum_terminal_tls_unwrap_iterations",
                        1,
                        SAFE_UINT_MAX,
                    ),
                    (
                        "maximum_terminal_zero_progress_iterations",
                        1,
                        SAFE_UINT_MAX,
                    ),
                    ("maximum_terminal_ingress_parser_units", 1, 4_096),
                    ("maximum_terminal_ingress_automatic_outputs", 1, 4_096),
                    ("maximum_websocket_send_attempts", 1, 1_048_832),
                    ("maximum_tls_control_send_attempts", 1, 256),
                    ("maximum_peer_shutdown_polls", 2, 2),
                )
            ],
            "local_shutdown_operational_result_relations": [
                "result.terminal_outcome=spec.expected_terminal_outcome",
                *[
                    f"result.{result_member}<=spec.{spec_member}"
                    for result_member, spec_member in (
                        (
                            "final_terminal_ingress_batch_count",
                            "maximum_terminal_ingress_batches",
                        ),
                        (
                            "final_terminal_ingress_ciphertext_octets",
                            "maximum_terminal_ingress_ciphertext_octets",
                        ),
                        (
                            "final_terminal_ingress_plaintext_octets",
                            "maximum_terminal_ingress_plaintext_octets",
                        ),
                        (
                            "final_terminal_socket_receive_call_count",
                            "maximum_terminal_socket_receive_calls",
                        ),
                        (
                            "final_terminal_tls_record_count",
                            "maximum_terminal_tls_records",
                        ),
                        (
                            "final_terminal_tls_unwrap_iteration_count",
                            "maximum_terminal_tls_unwrap_iterations",
                        ),
                        (
                            "final_terminal_zero_progress_iteration_count",
                            "maximum_terminal_zero_progress_iterations",
                        ),
                        (
                            "final_terminal_ingress_parser_unit_count",
                            "maximum_terminal_ingress_parser_units",
                        ),
                        (
                            "final_terminal_ingress_automatic_output_count",
                            "maximum_terminal_ingress_automatic_outputs",
                        ),
                        (
                            "final_websocket_send_attempt_count",
                            "maximum_websocket_send_attempts",
                        ),
                        (
                            "final_tls_control_send_attempt_count",
                            "maximum_tls_control_send_attempts",
                        ),
                        (
                            "final_peer_shutdown_poll_count",
                            "maximum_peer_shutdown_polls",
                        ),
                    )
                ],
                (
                    "len(result.ordered_terminal_ingress_read_attempt_event_ids)"
                    "<=spec.maximum_terminal_ingress_batches"
                ),
                (
                    "len(result.ordered_terminal_parser_transition_event_ids)"
                    "<=spec.maximum_terminal_ingress_parser_units"
                ),
            ],
            "maximum_constraint_scope_profile_catalog": (
                maximum_constraint_scope_profiles
            ),
        }
    )
    return contracts


def _build_ingress_logical_oracle_profile() -> dict[str, Any]:
    payload = {
        "profile_version": "riskyieldmm_ingress_logical_oracle_profile_v1",
        "oracle_kind": "INDEPENDENT_RESTRICTED_WASM_RFC6455_STREAM",
        "input_chunk_semantics": "EXACT_ORDERED_DECRYPTED_APPLICATION_OCTETS",
        "requires_empty_fragmentation_baseline": True,
        "requires_empty_complete_unit_baseline": True,
        "maximum_input_chunks": 128,
        "maximum_input_octets": 65_536,
        "maximum_parser_units": 32_768,
        "maximum_completed_application_messages": 32_768,
        "maximum_logical_output_frames": 32_768,
        "maximum_logical_output_payload_octets": 65_536,
        "logical_output_frame_domain": ("RiskYieldMMA2MExactLogicalOutputFramesV4_9F"),
        "raw_ingress_batch_domain": (
            "RiskYieldMMExactOrderedDecryptedIngressChunksV4_5"
        ),
        "streamed_digest_algorithm": ("CANONICAL_JSON_SHA256_INCREMENTAL_V1"),
        "parser_oracle_descriptor_requirement": (
            "COMPLETE_DESCRIPTOR_AND_CONFORMANCE_CORPUS_IN_TARGET_BOUND_UNIVERSE"
        ),
    }
    return _standalone_envelope(
        DOMAINS["oracle_profile"], payload, "logical_oracle_profile_id"
    )


def _build_operation_specs(
    oracle_profile: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    pong_payload = b"fixture-pong"
    mask = b"\x01\x02\x03\x04"
    masked_payload = bytes(
        value ^ mask[index % len(mask)] for index, value in enumerate(pong_payload)
    )
    input_bytes = bytes((0x89, 0x80 | len(pong_payload))) + mask + masked_payload
    chunks = [base64.b64encode(input_bytes).decode("ascii")]
    frames = [
        {
            "opcode": "PONG",
            "payload_base64": base64.b64encode(pong_payload).decode("ascii"),
        }
    ]
    input_batch_payload = {
        "domain": "RiskYieldMMExactOrderedDecryptedIngressChunksV4_5",
        "ordered_chunks_base64": chunks,
    }
    output_frame_payload = {
        "domain": "RiskYieldMMA2MExactLogicalOutputFramesV4_9F",
        "ordered_frames": frames,
    }
    empty_reason_sha256 = _sha256_bytes(b"")
    bodies: dict[str, dict[str, Any]] = {
        "ACK_DEADLINE_EXPIRY": {
            "workload_family": "fixture-ack-deadline-expiry-v1",
            "expected_outbound_subscription_intent_id": _fixture_id(
                "outbound-subscription-intent"
            ),
            "due_scenario": "DUE",
            "expected_terminal_cause_code": "ACK_DEADLINE_EXPIRED",
        },
        "INGRESS": {
            "workload_family": "fixture-ingress-v2",
            "ordered_input_chunks_base64": chunks,
            "input_chunk_count": len(chunks),
            "input_octet_count": len(input_bytes),
            "input_sha256": _sha256_bytes(input_bytes),
            "raw_ingress_batch_sha256": _sha256_bytes(
                _canonical_bytes(input_batch_payload)
            ),
            "timeout_seconds": 1,
            "logical_oracle_profile_id": oracle_profile["logical_oracle_profile_id"],
            "expected_parser_unit_count": 1,
            "expected_completed_application_message_count": 0,
            "expected_logical_output_frame_count": len(frames),
            "expected_logical_output_payload_octets": len(pong_payload),
            "expected_logical_output_frames_sha256": _sha256_bytes(
                _canonical_bytes(output_frame_payload)
            ),
        },
        "LOCAL_SHUTDOWN": {
            "workload_family": "fixture-local-shutdown-v2",
            "timeout_seconds": 1,
            "expected_terminal_outcome": "CLEAN_ALL_LAYERS",
            "expected_local_close_code": 1000,
            "expected_local_close_reason_sha256": empty_reason_sha256,
            "maximum_terminal_ingress_batches": 1,
            "maximum_terminal_ingress_ciphertext_octets": 16_645,
            "maximum_terminal_ingress_plaintext_octets": 16_384,
            "maximum_terminal_socket_receive_calls": 4,
            "maximum_terminal_tls_records": 1,
            "maximum_terminal_tls_unwrap_iterations": 2,
            "maximum_terminal_zero_progress_iterations": 2,
            "maximum_terminal_ingress_parser_units": 1,
            "maximum_terminal_ingress_automatic_outputs": 1,
            "maximum_websocket_send_attempts": 2,
            "maximum_tls_control_send_attempts": 2,
            "maximum_peer_shutdown_polls": 2,
        },
        "SUBSCRIPTION_DISPATCH": {
            "workload_family": "fixture-subscription-dispatch-v2",
            "idempotency_key": "fixture.subscription.1",
            "transport_subscription_policy_id": _fixture_id(
                "transport-subscription-policy"
            ),
            "adapter_policy_id": _fixture_id("adapter-policy"),
            "expected_topic": "fixture/topic/1",
            "expected_operation": "subscribe",
            "expected_logical_opcode": "TEXT",
            "expected_dispatch_disposition": "COMPLETE_LOCAL_SUBMISSION",
        },
    }
    specs: dict[str, dict[str, Any]] = {}
    for operation_kind in OPERATION_KINDS:
        body = bodies[operation_kind]
        _require(
            tuple(body) == SPEC_BODY_MEMBERS[operation_kind],
            f"fixture spec member order drifted: {operation_kind}",
        )
        specs[operation_kind] = _standalone_envelope(
            DOMAINS["operation_spec"],
            {
                "operation_kind": operation_kind,
                "spec_type": SPEC_TYPES[operation_kind],
                "spec": body,
            },
            "operation_spec_id",
        )
    return specs


def _build_operation_declaration(
    specs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    spec = specs["INGRESS"]
    payload = {
        "campaign_manifest_id": _fixture_id("campaign-manifest"),
        "manifest_authority_id": _fixture_id("manifest-authority"),
        "measurement_design_id": _fixture_id("measurement-design"),
        "workload_plan_id": _fixture_id("workload-plan"),
        "workload_id": "fixture-ingress-workload-1",
        "workload_sha256": _fixture_id("workload"),
        "sample_sequence": 1,
        "operation_sequence": 1,
        "trial_index": 0,
        "repetition_index": 0,
        "is_warmup": False,
        "stage": "measurement",
        "timeout_policy_id": _fixture_id("timeout-policy"),
        "operation_kind": "INGRESS",
        "operation_spec": spec,
        "operation_spec_id": spec["operation_spec_id"],
    }
    _require(
        tuple(payload) == DECLARATION_PAYLOAD_MEMBERS,
        "operation declaration member order drifted",
    )
    return _standalone_envelope(
        DOMAINS["operation_declaration"], payload, "declaration_id"
    )


def _build_dispatch_window_evidence() -> dict[str, Any]:
    payload = {
        "transport_session_id": _fixture_id("transport-session"),
        "outbound_subscription_intent_id": _fixture_id("outbound-subscription-intent"),
        "socket_lease_id": _fixture_id("socket-lease"),
        "monotonic_clock_domain_id": _fixture_id("monotonic-clock-domain"),
        "dispatch_started_at": "2026-07-22T00:00:00Z",
        "dispatch_completed_at": "2026-07-22T00:00:00.000001Z",
        "dispatch_started_monotonic_ns": "100",
        "dispatch_completed_monotonic_ns": "200",
    }
    _require(
        tuple(payload) == DISPATCH_WINDOW_PAYLOAD_MEMBERS,
        "dispatch-window member order drifted",
    )
    return _standalone_envelope(
        DOMAINS["dispatch_window"], payload, "dispatch_window_evidence_id"
    )


def _build_due_decision_clock_evidence(
    dispatch_window: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "transport_session_id": dispatch_window["transport_session_id"],
        "outbound_subscription_intent_id": dispatch_window[
            "outbound_subscription_intent_id"
        ],
        "dispatch_window_evidence": dispatch_window,
        "dispatch_window_evidence_id": dispatch_window["dispatch_window_evidence_id"],
        "clock_source_manifest_id": _fixture_id("clock-source-manifest"),
        "monotonic_clock_domain_id": dispatch_window["monotonic_clock_domain_id"],
        "wall_before_at": "2026-07-22T00:00:02Z",
        "sampled_at": "2026-07-22T00:00:02Z",
        "wall_after_at": "2026-07-22T00:00:02.000001Z",
        "monotonic_before_ns": "300",
        "monotonic_sampled_ns": "301",
        "monotonic_after_ns": "302",
        "uncertainty_milliseconds": 0,
        "synchronized": True,
        "valid_until": "2026-07-22T01:00:00Z",
        "clock_resolution_ns": 1,
        "source_observation_sha256": _fixture_id("clock-source-observation"),
        "selectable_source_count": 1,
        "chronyd_launch_id": _fixture_id("chronyd-launch"),
        "chronyd_runtime_observation_sha256": _fixture_id(
            "chronyd-runtime-observation"
        ),
        "committed_ack_deadline_at": "2026-07-22T00:00:01Z",
        "committed_ack_deadline_monotonic_ns": "250",
        "due_scenario": "DUE",
    }
    _require(
        tuple(payload) == DUE_DECISION_CLOCK_PAYLOAD_MEMBERS,
        "due-decision clock member order drifted",
    )
    return _standalone_envelope(
        DOMAINS["due_decision_clock"], payload, "due_decision_clock_evidence_id"
    )


def _build_operation_results(
    dispatch_window: dict[str, Any],
    due_clock: dict[str, Any],
    specs: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    ingress_spec = specs["INGRESS"]["spec"]
    shutdown_spec = specs["LOCAL_SHUTDOWN"]["spec"]
    subscription_payload = b'{"operation":"subscribe","topic":"fixture/topic/1"}'
    subscription_payload_sha256 = _sha256_bytes(subscription_payload)
    bodies: dict[str, dict[str, Any]] = {
        "ACK_DEADLINE_EXPIRY": {
            "expired": True,
            "due_decision_clock_evidence": due_clock,
            "due_decision_clock_evidence_id": due_clock[
                "due_decision_clock_evidence_id"
            ],
            "ack_deadline_expired_event_id": _fixture_id("ack-expired-event"),
            "terminal_transition_event_id": _fixture_id("ack-terminal-event"),
            "transport_session_termination_id": _fixture_id("ack-termination"),
        },
        "INGRESS": {
            "ingress_progress_evidence_id": _fixture_id("ingress-progress"),
            "final_parser_cursor_id": _fixture_id("final-parser-cursor"),
            "final_retained_tail_id": _fixture_id("final-retained-tail"),
            "final_retained_tail_octets": 0,
            "final_retained_tail_sha256": _sha256_bytes(b""),
            "sealed_pending_input_id": _fixture_id("sealed-pending-input"),
            "ingress_oracle_baseline_id": _fixture_id("ingress-oracle-baseline"),
            "observed_consumed_new_input_octets": ingress_spec["input_octet_count"],
            "observed_parser_unit_count": ingress_spec["expected_parser_unit_count"],
            "observed_completed_application_message_count": ingress_spec[
                "expected_completed_application_message_count"
            ],
            "observed_logical_output_frame_count": ingress_spec[
                "expected_logical_output_frame_count"
            ],
            "observed_logical_output_payload_octets": ingress_spec[
                "expected_logical_output_payload_octets"
            ],
            "observed_logical_output_frames_sha256": ingress_spec[
                "expected_logical_output_frames_sha256"
            ],
        },
        "LOCAL_SHUTDOWN": {
            "local_shutdown_started_event_id": _fixture_id("shutdown-started"),
            "local_shutdown_deadline_evidence_event_id": None,
            "local_close_dispatch_completion_event_id": _fixture_id(
                "local-close-completion"
            ),
            "ordered_terminal_ingress_read_attempt_event_ids": [
                _fixture_id("terminal-ingress-read-attempt-1")
            ],
            "ordered_terminal_ingress_read_result_event_ids": [
                _fixture_id("terminal-ingress-read-result-1")
            ],
            "ordered_terminal_raw_ingress_commit_ids": [
                _fixture_id("terminal-raw-ingress-commit-1")
            ],
            "ordered_terminal_raw_ingress_actor_event_ids": [
                _fixture_id("terminal-raw-ingress-actor-event-1")
            ],
            "ordered_terminal_parser_transition_event_ids": [
                _fixture_id("terminal-parser-transition-1")
            ],
            "websocket_close_received_transition_event_id": _fixture_id(
                "websocket-close-received-transition"
            ),
            "shutdown_trace_step_count": 8,
            "shutdown_trace_root_sha256": _fixture_id("shutdown-trace-root"),
            "final_terminal_ingress_batch_count": 1,
            "final_terminal_ingress_ciphertext_octets": shutdown_spec[
                "maximum_terminal_ingress_ciphertext_octets"
            ],
            "final_terminal_ingress_plaintext_octets": shutdown_spec[
                "maximum_terminal_ingress_plaintext_octets"
            ],
            "final_terminal_socket_receive_call_count": shutdown_spec[
                "maximum_terminal_socket_receive_calls"
            ],
            "final_terminal_tls_record_count": shutdown_spec[
                "maximum_terminal_tls_records"
            ],
            "final_terminal_tls_unwrap_iteration_count": shutdown_spec[
                "maximum_terminal_tls_unwrap_iterations"
            ],
            "final_terminal_zero_progress_iteration_count": shutdown_spec[
                "maximum_terminal_zero_progress_iterations"
            ],
            "final_terminal_ingress_parser_unit_count": shutdown_spec[
                "maximum_terminal_ingress_parser_units"
            ],
            "final_terminal_ingress_automatic_output_count": shutdown_spec[
                "maximum_terminal_ingress_automatic_outputs"
            ],
            "final_websocket_send_attempt_count": shutdown_spec[
                "maximum_websocket_send_attempts"
            ],
            "final_tls_control_send_attempt_count": shutdown_spec[
                "maximum_tls_control_send_attempts"
            ],
            "final_peer_shutdown_poll_count": shutdown_spec[
                "maximum_peer_shutdown_polls"
            ],
            "final_terminal_tls_staging_state_id": _fixture_id(
                "final-terminal-tls-staging-state"
            ),
            "decisive_terminal_transition_event_id": _fixture_id(
                "decisive-terminal-transition"
            ),
            "transport_session_termination_id": _fixture_id("shutdown-termination"),
            "terminal_outcome": "CLEAN_ALL_LAYERS",
        },
        "SUBSCRIPTION_DISPATCH": {
            "outbound_subscription_intent_id": dispatch_window[
                "outbound_subscription_intent_id"
            ],
            "generated_request_id": "fixture_request_1",
            "generated_request_command_sha256": subscription_payload_sha256,
            "generated_logical_opcode": "TEXT",
            "generated_logical_payload_sha256": subscription_payload_sha256,
            "generated_logical_payload_octets": len(subscription_payload),
            "dispatch_window_evidence": dispatch_window,
            "dispatch_window_evidence_id": dispatch_window[
                "dispatch_window_evidence_id"
            ],
            "outbound_wire_prepared_event_id": _fixture_id("wire-prepared-event"),
            "tls_ciphertext_prepared_event_id": _fixture_id(
                "tls-ciphertext-prepared-event"
            ),
            "ordered_kernel_attempt_event_ids": [_fixture_id("kernel-attempt-event-1")],
            "ordered_kernel_result_event_ids": [_fixture_id("kernel-result-event-1")],
            "outbound_dispatch_completed_event_id": _fixture_id(
                "dispatch-completed-event"
            ),
            "submitted_ciphertext_octets": len(subscription_payload) + 32,
            "local_dispatch_disposition": "COMPLETE_LOCAL_SUBMISSION",
        },
    }
    results: dict[str, dict[str, Any]] = {}
    for operation_kind in OPERATION_KINDS:
        body = bodies[operation_kind]
        _require(
            tuple(body) == RESULT_BODY_MEMBERS[operation_kind],
            f"fixture result member order drifted: {operation_kind}",
        )
        payload = {
            "candidate_id": _fixture_id(f"candidate:{operation_kind}"),
            "attempt_id": _fixture_id(f"attempt:{operation_kind}"),
            "operation_kind": operation_kind,
            "result_type": RESULT_TYPES[operation_kind],
            "result": body,
        }
        results[operation_kind] = _standalone_envelope(
            DOMAINS["operation_result"], payload, "result_evidence_id"
        )
    return results


def _method_for_role(descriptor: dict[str, Any], role: str) -> str | None:
    methods = [
        pair["observation_method"]
        for pair in descriptor["observation_method_role_pairs"]
        if role in pair["allowed_roles"]
    ]
    _require(len(methods) <= 1, f"ambiguous method for {descriptor['field_id']}/{role}")
    return methods[0] if methods else None


def _available_value(descriptor: dict[str, Any], *, maximal: bool) -> dict[str, Any]:
    kind = descriptor["value_kind"]
    constraint = descriptor["value_constraint_id"]
    scalar_uint = SAFE_UINT_MAX if maximal else 0
    if constraint == "UINT_LOOP_PROBE_INTERVAL_NS":
        scalar_uint = 60_000_000_000 if maximal else 1_000_000
    if kind == "UINT":
        return {"kind": kind, "value": scalar_uint}
    if kind == "BOOL":
        return {"kind": kind, "value": False}
    if kind == "TEXT":
        if constraint == "TEXT_ENUM_A1_COMMAND_KIND":
            value = max(OPERATION_KINDS, key=len) if maximal else OPERATION_KINDS[0]
        elif constraint == "TEXT_ENUM_A1_ADMISSION_OUTCOME":
            value = (
                max(A1_ADMISSION_OUTCOMES, key=len)
                if maximal
                else A1_ADMISSION_OUTCOMES[0]
            )
        elif constraint == "TEXT_ENUM_SQLITE_PRIMARY_RESULT":
            value = (
                max(SQLITE_PRIMARY_RESULTS, key=len)
                if maximal
                else SQLITE_PRIMARY_RESULTS[0]
            )
        else:
            value = "f" * 64 if maximal else _fixture_id(descriptor["field_id"])
        return {"kind": kind, "value": value}
    if kind == "OPTIONAL_UINT":
        return {"kind": kind, "present": True, "value": scalar_uint}
    if kind == "OPTIONAL_TEXT":
        if constraint == "OPTIONAL_TEXT_ENUM_A1_COMMAND_KIND":
            value = max(OPERATION_KINDS, key=len) if maximal else OPERATION_KINDS[0]
        elif constraint == "OPTIONAL_TEXT_ENUM_A1_REJECTION_CLASS":
            value = (
                max(A1_REJECTION_CLASSES, key=len)
                if maximal
                else A1_REJECTION_CLASSES[0]
            )
        elif constraint == "OPTIONAL_TEXT_UINT128_DECIMAL":
            value = UINT128_MAX_TEXT if maximal else "0"
        elif constraint == "OPTIONAL_TEXT_PLATFORM_ERRNO":
            value = "E" + ("A" * 63) if maximal else "EIO"
        else:
            value = "f" * 64 if maximal else _fixture_id(descriptor["field_id"])
        return {"kind": kind, "present": True, "value": value}
    if kind == "UINT_LIST":
        if descriptor["value_shape_id"] == "L_GC_GENERATIONS_3":
            count = 3
        else:
            count = 4 if maximal else 0
        return {"kind": kind, "values": [scalar_uint] * count}
    if kind == "TEXT_LIST":
        count = 4 if maximal else 0
        value = max(OPERATION_KINDS, key=len)
        return {"kind": kind, "values": [value] * count}
    if kind == "FIXED_UINT_MAP":
        return {
            "kind": kind,
            "ordered": [
                {"key": key, "value": scalar_uint}
                for key in descriptor["value_shape_keys"]
            ],
        }
    if kind == "DURATION_BOUND":
        return {
            "kind": kind,
            "relation": "EXACT",
            "lower_nanoseconds": scalar_uint,
            "upper_nanoseconds": scalar_uint,
        }
    raise InventoryError(f"unsupported value kind: {kind}")


def _field_observation_envelope(
    *,
    registry_id: str,
    context_id: str,
    descriptor: dict[str, Any],
    availability: str,
    value: dict[str, Any] | None,
    observation_method: str,
    observation_attempt: str,
    adapter_span_status: str,
    started_offset: int | None,
    completed_offset: int | None,
    unavailable_reason: str | None,
    censoring: str = "NONE",
    source_errno_number: int | None = None,
    source_errno_name: str | None = None,
    source_failure_phase: str = "NONE",
    source_error_class: str | None = None,
) -> dict[str, Any]:
    source_error_detail_sha256: str | None = None
    if source_error_class is not None:
        detail_payload = {
            "field_id": descriptor["field_id"],
            "observation_method": observation_method,
            "source_failure_phase": source_failure_phase,
            "source_errno_number": source_errno_number,
            "source_errno_name": source_errno_name,
            "source_error_class": source_error_class,
        }
        _require(
            tuple(detail_payload) == SOURCE_ERROR_DETAIL_PAYLOAD_MEMBERS,
            "SourceErrorDetail must have exactly the frozen six-key payload",
        )
        detail_preimage = {
            "canonicalization_version": CANONICALIZATION_VERSION,
            "domain": DOMAINS["source_error_detail"],
            "payload": detail_payload,
            "schema_version": MEASUREMENT_SCHEMA_VERSION,
        }
        _require(
            len(_canonical_bytes(detail_preimage)) <= 2_048,
            "SourceErrorDetail semantic preimage exceeds 2 KiB",
        )
        source_error_detail_sha256 = _semantic_id(
            DOMAINS["source_error_detail"], detail_payload
        )
    payload = {
        "target_field_registry_id": registry_id,
        "observation_context_id": context_id,
        "field_id": descriptor["field_id"],
        "availability": availability,
        "value": value,
        "observation_method": observation_method,
        "observation_attempt": observation_attempt,
        "adapter_span_status": adapter_span_status,
        "observation_started_offset_nanoseconds": started_offset,
        "observation_completed_offset_nanoseconds": completed_offset,
        "unavailable_reason": unavailable_reason,
        "censoring": censoring,
        "source_errno_number": source_errno_number,
        "source_errno_name": source_errno_name,
        "source_failure_phase": source_failure_phase,
        "source_error_class": source_error_class,
        "source_error_detail_sha256": source_error_detail_sha256,
    }
    _require(
        tuple(payload) == FIELD_OBSERVATION_PAYLOAD_MEMBERS,
        "field-observation member order drifted",
    )
    return _standalone_envelope(
        DOMAINS["field_observation"], payload, "field_observation_id"
    )


def _available_clock_span(
    clock_domain: str, started_offset: int, completed_offset: int
) -> dict[str, Any]:
    _require(started_offset <= completed_offset, "clock span is reversed")
    result = {
        "clock_domain": clock_domain,
        "span_status": "AVAILABLE",
        "started_offset_nanoseconds": started_offset,
        "completed_offset_nanoseconds": completed_offset,
        "unavailable_reason": None,
    }
    _require(tuple(result) == CLOCK_SPAN_MEMBERS, "clock-span member order drifted")
    return result


def _observation_context_payload(
    *,
    role: str,
    operation_kind: str,
    instrumentation_mode: str,
    candidate_id: str,
    attempt_id: str | None,
    registry_id: str,
    started_offset: int,
    completed_offset: int,
) -> dict[str, Any]:
    payload = {
        "observation_role": role,
        "operation_kind": operation_kind,
        "instrumentation_mode": instrumentation_mode,
        "candidate_id": candidate_id,
        "attempt_id": attempt_id,
        "target_field_registry_id": registry_id,
        "marker_ordinal": None,
        "checkpoint_marker_kind": None,
        "observer_clock_span": _available_clock_span(
            "OBSERVER_MONOTONIC", started_offset, completed_offset
        ),
        "boottime_clock_span": _available_clock_span(
            "BOOTTIME", started_offset, completed_offset
        ),
        "loop_clock_span": _available_clock_span(
            "EVENT_LOOP", started_offset, completed_offset
        ),
    }
    _require(
        tuple(payload) == OBSERVATION_CONTEXT_PAYLOAD_MEMBERS,
        "observation-context member order drifted",
    )
    return payload


def _target_observation_envelope(
    context_payload: dict[str, Any],
    field_observations: list[dict[str, Any]],
) -> dict[str, Any]:
    context_id = _semantic_id(DOMAINS["observation_context"], context_payload)
    _require(
        all(
            item["observation_context_id"] == context_id for item in field_observations
        ),
        "field observations do not bind the exact context ID",
    )
    payload = {
        "observation_role": context_payload["observation_role"],
        "operation_kind": context_payload["operation_kind"],
        "instrumentation_mode": context_payload["instrumentation_mode"],
        "candidate_id": context_payload["candidate_id"],
        "attempt_id": context_payload["attempt_id"],
        "target_field_registry_id": context_payload["target_field_registry_id"],
        "observation_context_id": context_id,
        "marker_ordinal": context_payload["marker_ordinal"],
        "checkpoint_marker_kind": context_payload["checkpoint_marker_kind"],
        "observer_clock_span": context_payload["observer_clock_span"],
        "boottime_clock_span": context_payload["boottime_clock_span"],
        "loop_clock_span": context_payload["loop_clock_span"],
        "field_observations": field_observations,
    }
    _require(
        tuple(payload) == TARGET_OBSERVATION_PAYLOAD_MEMBERS,
        "target-observation member order drifted",
    )
    return _standalone_envelope(
        DOMAINS["target_observation"], payload, "observation_id"
    )


def _build_off_observation(
    *,
    role: str,
    operation_kind: str,
    candidate_id: str,
    attempt_id: str,
    registry_id: str,
    metadata: list[dict[str, Any]],
    started_offset: int,
    completed_offset: int,
) -> dict[str, Any]:
    context = _observation_context_payload(
        role=role,
        operation_kind=operation_kind,
        instrumentation_mode="OFF",
        candidate_id=candidate_id,
        attempt_id=attempt_id,
        registry_id=registry_id,
        started_offset=started_offset,
        completed_offset=completed_offset,
    )
    context_id = _semantic_id(DOMAINS["observation_context"], context)
    fields: list[dict[str, Any]] = []
    for index, item in enumerate(metadata):
        descriptor = item["descriptor"]
        method = _method_for_role(descriptor, role)
        if operation_kind not in descriptor["applicable_operation_kinds"]:
            field = _field_observation_envelope(
                registry_id=registry_id,
                context_id=context_id,
                descriptor=descriptor,
                availability="NOT_APPLICABLE",
                value=None,
                observation_method="NOT_ATTEMPTED",
                observation_attempt="NOT_ATTEMPTED",
                adapter_span_status="NOT_APPLICABLE",
                started_offset=None,
                completed_offset=None,
                unavailable_reason="NOT_APPLICABLE_TO_OPERATION",
            )
        elif item["reason_profile"] == "U_STATIC":
            _require(method is not None, "static fixture field has no role method")
            adapter_offset = min(started_offset + 1 + index, completed_offset)
            field = _field_observation_envelope(
                registry_id=registry_id,
                context_id=context_id,
                descriptor=descriptor,
                availability="AVAILABLE",
                value=_available_value(descriptor, maximal=False),
                observation_method=method,
                observation_attempt="ATTEMPTED",
                adapter_span_status="AVAILABLE",
                started_offset=adapter_offset,
                completed_offset=adapter_offset,
                unavailable_reason=None,
            )
        elif item["reason_profile"] == "U_POLICY":
            field = _field_observation_envelope(
                registry_id=registry_id,
                context_id=context_id,
                descriptor=descriptor,
                availability="UNAVAILABLE",
                value=None,
                observation_method="NOT_ATTEMPTED",
                observation_attempt="NOT_ATTEMPTED",
                adapter_span_status="NOT_APPLICABLE",
                started_offset=None,
                completed_offset=None,
                unavailable_reason="NO_FROZEN_PRESSURE_POLICY",
            )
        else:
            field = _field_observation_envelope(
                registry_id=registry_id,
                context_id=context_id,
                descriptor=descriptor,
                availability="UNAVAILABLE",
                value=None,
                observation_method="NOT_ATTEMPTED",
                observation_attempt="NOT_ATTEMPTED",
                adapter_span_status="NOT_APPLICABLE",
                started_offset=None,
                completed_offset=None,
                unavailable_reason="INSTRUMENTATION_DISABLED",
            )
        fields.append(field)
    return _target_observation_envelope(context, fields)


def _build_off_observations_and_root(
    *,
    registry_id: str,
    metadata: list[dict[str, Any]],
    operation_results: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ingress_result = operation_results["INGRESS"]
    candidate_id = ingress_result["candidate_id"]
    attempt_id = ingress_result["attempt_id"]
    observations = [
        _build_off_observation(
            role=role,
            operation_kind="INGRESS",
            candidate_id=candidate_id,
            attempt_id=attempt_id,
            registry_id=registry_id,
            metadata=metadata,
            started_offset=started,
            completed_offset=completed,
        )
        for role, started, completed in (
            ("BEFORE_OPERATION", 0, 1_000),
            ("AFTER_OPERATION", 2_000, 3_000),
            ("OPERATION_AGGREGATE", 4_000, 5_000),
        )
    ]
    root_payload = {
        "candidate_id": candidate_id,
        "attempt_id": attempt_id,
        "operation_kind": "INGRESS",
        "instrumentation_mode": "OFF",
        "target_field_registry_id": registry_id,
        "observation_count": len(observations),
        "ordered_observation_ids": [item["observation_id"] for item in observations],
    }
    _require(
        tuple(root_payload) == TARGET_OBSERVATION_ROOT_PAYLOAD_MEMBERS,
        "target-observation-root member order drifted",
    )
    root = _standalone_envelope(
        DOMAINS["target_observation_root"],
        root_payload,
        "target_observation_root_sha256",
    )
    return observations, root


def _convert_flat_observation_to_v2(
    observation: dict[str, Any],
    *,
    registry_id: str,
    maximal_spans: bool = False,
) -> dict[str, Any]:
    context = _observation_context_v2(
        role=observation["observation_role"],
        operation_kind=observation["operation_kind"],
        instrumentation_mode=observation["instrumentation_mode"],
        candidate_id=observation["candidate_id"],
        attempt_id=observation["attempt_id"],
        registry_id=registry_id,
        maximal_spans=maximal_spans,
    )
    context_payload = {member: context[member] for member in V2_CONTEXT_PAYLOAD_MEMBERS}
    for span_member in (
        "observer_clock_span",
        "boottime_clock_span",
        "loop_clock_span",
    ):
        context_payload[span_member] = observation[span_member]
    context = _standalone_envelope(
        DOMAINS["observation_context"],
        context_payload,
        "observation_context_id",
    )
    fields = [
        _field_observation_rebound(field, context_id=context["observation_context_id"])
        for field in observation["field_observations"]
    ]
    return _target_observation_v2(context, fields)


def _exact_checkpoint_observation_v2(
    *,
    context: dict[str, Any],
    metadata: list[dict[str, Any]],
) -> dict[str, Any]:
    marker_kind = context["checkpoint_marker_kind"]
    operation_kind = context["operation_kind"]
    fields: list[dict[str, Any]] = []
    for item in metadata:
        descriptor = item["descriptor"]
        if operation_kind not in descriptor["applicable_operation_kinds"]:
            availability = "NOT_APPLICABLE"
            reason = "NOT_APPLICABLE_TO_OPERATION"
            value = None
            method = "NOT_ATTEMPTED"
            attempt = "NOT_ATTEMPTED"
            span = "NOT_APPLICABLE"
            started = completed = None
        elif marker_kind not in descriptor["allowed_checkpoint_marker_kinds"]:
            availability = "NOT_APPLICABLE"
            reason = "NOT_APPLICABLE_TO_REACHED_STATE"
            value = None
            method = "NOT_ATTEMPTED"
            attempt = "NOT_ATTEMPTED"
            span = "NOT_APPLICABLE"
            started = completed = None
        else:
            method_for_checkpoint = _method_for_role(descriptor, "STABLE_CHECKPOINT")
            _require(
                method_for_checkpoint is not None,
                "checkpoint-eligible descriptor has no checkpoint method",
            )
            availability = "AVAILABLE"
            reason = None
            value = _available_value(descriptor, maximal=False)
            method = method_for_checkpoint
            attempt = "ATTEMPTED"
            span = "AVAILABLE"
            started = completed = 10
        fields.append(
            _field_observation_envelope(
                registry_id=context["target_field_registry_id"],
                context_id=context["observation_context_id"],
                descriptor=descriptor,
                availability=availability,
                value=value,
                observation_method=method,
                observation_attempt=attempt,
                adapter_span_status=span,
                started_offset=started,
                completed_offset=completed,
                unavailable_reason=reason,
            )
        )
    return _target_observation_v2(context, fields)


def _build_v2_observation_fixtures(
    *,
    registry_id: str,
    metadata: list[dict[str, Any]],
    selector_catalog: list[dict[str, Any]],
) -> dict[str, Any]:
    by_name = {item["catalog_name"]: item["selector"] for item in selector_catalog}
    old_off, _ = _build_off_observations_and_root(
        registry_id=registry_id,
        metadata=metadata,
        operation_results={
            "INGRESS": {
                "candidate_id": _fixture_id("candidate:INGRESS"),
                "attempt_id": _fixture_id("attempt:INGRESS"),
            }
        },
    )
    off_observations = [
        _convert_flat_observation_to_v2(item, registry_id=registry_id)
        for item in old_off
    ]
    candidate_id = off_observations[0]["observation_context"]["candidate_id"]
    attempt_id = off_observations[0]["observation_context"]["attempt_id"]
    off_root = _target_observation_root_v2(
        candidate_id=candidate_id,
        attempt_id=attempt_id,
        operation_kind="INGRESS",
        instrumentation_mode="OFF",
        registry_id=registry_id,
        selector_id=None,
        ordered_observation_ids=[item["observation_id"] for item in off_observations],
    )

    selector = by_name["INGRESS_COVERAGE"]
    checkpoint_candidate = _fixture_id("v2-checkpoint-candidate")
    checkpoint_attempt = _fixture_id("v2-checkpoint-attempt")
    exact_context = _observation_context_v2(
        role="STABLE_CHECKPOINT",
        operation_kind="INGRESS",
        instrumentation_mode="ON",
        candidate_id=checkpoint_candidate,
        attempt_id=checkpoint_attempt,
        registry_id=registry_id,
        selector=selector,
        selector_position=1,
        binding_status="EXACT_MARKER",
        marker_ordinal=6,
        actual_marker_kind="RAW_PREFIX_COMMITTED",
    )
    exact_observation = _exact_checkpoint_observation_v2(
        context=exact_context, metadata=metadata
    )
    placeholder_cases = (
        (
            "TARGET_BOUNDARY_NOT_REACHED",
            "UNAVAILABLE_TARGET_BOUNDARY_NOT_REACHED",
        ),
        ("SOURCE_CLOCK_UNAVAILABLE", "UNAVAILABLE_MARKER_OBSERVER_FAILURE"),
        ("ARTIFACT_BOUND_EXCEEDED", "UNAVAILABLE_MARKER_OBSERVER_FAILURE"),
        ("OBSERVER_INTERNAL_ERROR", "UNAVAILABLE_MARKER_OBSERVER_FAILURE"),
    )
    placeholder_observations: dict[str, dict[str, Any]] = {}
    for position, (reason, status) in enumerate(placeholder_cases, 1):
        context = _observation_context_v2(
            role="STABLE_CHECKPOINT",
            operation_kind="INGRESS",
            instrumentation_mode="ON",
            candidate_id=checkpoint_candidate,
            attempt_id=checkpoint_attempt,
            registry_id=registry_id,
            selector=selector,
            selector_position=position,
            binding_status=status,
            binding_reason=reason,
        )
        placeholder_observations[reason] = _checkpoint_placeholder_observation_v2(
            context=context, metadata=metadata
        )

    max_selector = by_name["INGRESS_MAX64_PARSER_UNITS"]
    max_root_ids = [
        _fixture_id("root-max64:BEFORE"),
        *[
            _fixture_id(f"root-max64:CHECKPOINT:{position}")
            for position in range(1, 65)
        ],
        _fixture_id("root-max64:AFTER"),
        _fixture_id("root-max64:AGGREGATE"),
    ]
    maximum_root = _target_observation_root_v2(
        candidate_id=_fixture_id("root-max64-candidate"),
        attempt_id=_fixture_id("root-max64-attempt"),
        operation_kind="INGRESS",
        instrumentation_mode="ON",
        registry_id=registry_id,
        selector_id=max_selector["checkpoint_selector_id"],
        ordered_observation_ids=max_root_ids,
    )
    _require(maximum_root["observation_count"] == 67, "maximum root is not 67")
    empty_selector_name_by_operation = {
        "ACK_DEADLINE_EXPIRY": "ACK_EMPTY",
        "INGRESS": "INGRESS_EMPTY",
        "LOCAL_SHUTDOWN": "LOCAL_SHUTDOWN_EMPTY",
        "SUBSCRIPTION_DISPATCH": "SUBSCRIPTION_EMPTY",
    }
    attempted_on_empty_roots: dict[str, dict[str, Any]] = {}
    for operation_kind, catalog_name in empty_selector_name_by_operation.items():
        empty_selector = by_name[catalog_name]
        _require(
            empty_selector["selector_length"] == 0,
            "empty-selector root fixture bound a nonempty selector",
        )
        root = _target_observation_root_v2(
            candidate_id=_fixture_id(f"empty-root-candidate:{operation_kind}"),
            attempt_id=_fixture_id(f"empty-root-attempt:{operation_kind}"),
            operation_kind=operation_kind,
            instrumentation_mode="ON",
            registry_id=registry_id,
            selector_id=empty_selector["checkpoint_selector_id"],
            ordered_observation_ids=[
                _fixture_id(f"empty-root:{operation_kind}:BEFORE"),
                _fixture_id(f"empty-root:{operation_kind}:AFTER"),
                _fixture_id(f"empty-root:{operation_kind}:AGGREGATE"),
            ],
        )
        _require(
            root["observation_count"] == 3
            and root["full_checkpoint_selector_id"]
            == empty_selector["checkpoint_selector_id"],
            "attempted-ON empty-selector root truth drifted",
        )
        attempted_on_empty_roots[operation_kind] = root
    return {
        "off_target_observations": off_observations,
        "off_target_observation_root": off_root,
        "checkpoint_exact_marker_observation": exact_observation,
        "checkpoint_placeholder_observations": {
            key: placeholder_observations[key]
            for key in sorted(placeholder_observations)
        },
        "attempted_on_empty_selector_target_observation_roots": (
            attempted_on_empty_roots
        ),
        "maximum_selector_target_observation_root": maximum_root,
    }


def _local_shutdown_limit_relation_boundary_cases() -> list[dict[str, Any]]:
    base = {
        "maximum_terminal_ingress_batches": 1,
        "maximum_terminal_ingress_ciphertext_octets": 16_645,
        "maximum_terminal_ingress_plaintext_octets": 16_384,
        "maximum_terminal_socket_receive_calls": 4,
        "maximum_terminal_tls_records": 1,
        "maximum_terminal_tls_unwrap_iterations": 2,
        "maximum_terminal_zero_progress_iterations": 2,
        "maximum_terminal_ingress_parser_units": 1,
        "maximum_terminal_ingress_automatic_outputs": 1,
        "maximum_websocket_send_attempts": 2,
        "maximum_tls_control_send_attempts": 2,
        "maximum_peer_shutdown_polls": 2,
    }
    case_inputs = (
        (
            "PLAINTEXT_LE_16384_TIMES_BATCHES",
            {},
            "maximum_terminal_ingress_plaintext_octets",
            16_385,
        ),
        (
            "PARSER_UNITS_LE_FLOOR_PLAINTEXT_DIV_2",
            {"maximum_terminal_ingress_plaintext_octets": 2},
            "maximum_terminal_ingress_parser_units",
            2,
        ),
        (
            "PARSER_UNITS_LE_4096",
            {
                "maximum_terminal_ingress_plaintext_octets": 8_194,
                "maximum_terminal_ingress_parser_units": 4_096,
            },
            "maximum_terminal_ingress_parser_units",
            4_097,
        ),
        (
            "TLS_RECORDS_LE_BATCHES",
            {},
            "maximum_terminal_tls_records",
            2,
        ),
        (
            "AUTOMATIC_OUTPUTS_LE_PARSER_UNITS",
            {},
            "maximum_terminal_ingress_automatic_outputs",
            2,
        ),
        (
            "WS_SEND_ATTEMPTS_LE_256_TIMES_ONE_PLUS_AUTO_OUTPUTS",
            {"maximum_websocket_send_attempts": 512},
            "maximum_websocket_send_attempts",
            513,
        ),
        (
            "TLS_CONTROL_SEND_ATTEMPTS_LE_256",
            {"maximum_tls_control_send_attempts": 256},
            "maximum_tls_control_send_attempts",
            257,
        ),
        (
            "PEER_SHUTDOWN_POLLS_EQUALS_2",
            {},
            "maximum_peer_shutdown_polls",
            3,
        ),
    )
    cases = []
    for rule_id, overrides, mutation_field, mutation_value in case_inputs:
        equality_fixture = {**base, **overrides}
        cases.append(
            {
                "relation_rule_id": rule_id,
                "equality_fixture": equality_fixture,
                "one_field_violation": {
                    "field_name": mutation_field,
                    "mutated_value": mutation_value,
                    "all_other_fields_unchanged": True,
                    "expected_rejection": True,
                },
            }
        )
    return cases


def _one_field_mutation_metadata() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []

    def add(
        case_id: str,
        base_fixture: str,
        field_path: str,
        mutated_value: Any,
        expected_rule: str,
    ) -> None:
        cases.append(
            {
                "mutation_case_id": case_id,
                "base_fixture": base_fixture,
                "field_path": field_path,
                "mutated_value": mutated_value,
                "expected_rejection_rule": expected_rule,
            }
        )

    for tag in REMOVED_V1_TAGS:
        add(
            f"REMOVED_TAG_{tag}",
            "matching_v2_operation_envelope",
            "spec_type_or_result_type",
            tag,
            "REMOVED_V1_TAG_FORBIDDEN",
        )
    add(
        "STANDALONE_PAYLOAD_RESERVED_RECORD_DOMAIN",
        "external_schema_registry_v2.ordered_external_type_descriptors[0]",
        "identity_payload.record_domain",
        "RiskYieldMMA2MForbiddenPayloadDomain",
        "STANDALONE_ENVELOPE_RESERVED_MEMBER_COLLISION",
    )
    for field, value in (
        ("expected_parser_unit_count", 32_769),
        ("expected_completed_application_message_count", 32_769),
        ("expected_logical_output_frame_count", 32_769),
        ("expected_logical_output_payload_octets", 65_537),
        ("input_chunk_count", 129),
        ("input_octet_count", 65_537),
    ):
        add(
            f"INGRESS_PLUS_ONE_{field}",
            "operation_specs.INGRESS",
            field,
            value,
            "INGRESS_V2_BOUND",
        )
    add(
        "SELECTOR_LENGTH_65",
        "checkpoint_selector_catalog.INGRESS_MAX64_PARSER_UNITS",
        "selector_length",
        65,
        "SELECTOR_LENGTH_MAX_64",
    )
    add(
        "ROOT_COUNT_68",
        "maximum_selector_target_observation_root",
        "observation_count",
        68,
        "ATTEMPTED_ON_ROOT_COUNT_EQUALS_SELECTOR_LENGTH_PLUS_3",
    )
    add(
        "SUBSCRIPTION_KERNEL_COUNT_257",
        "operation_results.SUBSCRIPTION_DISPATCH",
        "result.ordered_kernel_attempt_event_ids",
        "257_UNIQUE_HASHES",
        "SUBSCRIPTION_KERNEL_CARDINALITY_MAX_256",
    )
    local_mutations = (
        (
            "maximum_terminal_ingress_plaintext_octets",
            16_385,
            "PLAINTEXT_LE_16384_TIMES_BATCHES",
        ),
        (
            "maximum_terminal_ingress_parser_units",
            2,
            "PARSER_UNITS_LE_FLOOR_PLAINTEXT_DIV_2",
        ),
        (
            "maximum_terminal_ingress_parser_units",
            4_097,
            "PARSER_UNITS_LE_4096",
        ),
        (
            "maximum_terminal_tls_records",
            2,
            "TLS_RECORDS_LE_BATCHES",
        ),
        (
            "maximum_terminal_ingress_automatic_outputs",
            2,
            "AUTOMATIC_OUTPUTS_LE_PARSER_UNITS",
        ),
        (
            "maximum_websocket_send_attempts",
            513,
            "WS_SEND_ATTEMPTS_LE_256_TIMES_ONE_PLUS_AUTO_OUTPUTS",
        ),
        (
            "maximum_tls_control_send_attempts",
            257,
            "TLS_CONTROL_SEND_ATTEMPTS_LE_256",
        ),
        ("maximum_peer_shutdown_polls", 3, "PEER_SHUTDOWN_POLLS_EQUALS_2"),
    )
    for field, value, rule in local_mutations:
        add(
            f"LOCAL_LIMIT_{rule}",
            f"local_shutdown_limit_relation_cases.{rule}.equality_fixture",
            field,
            value,
            rule,
        )
    for reason, field_reason in CHECKPOINT_CONTEXT_TO_FIELD_REASON.items():
        add(
            f"CHECKPOINT_REASON_MISMATCH_{reason}",
            "checkpoint_placeholder_observations",
            "field_observations[0].unavailable_reason",
            (
                "CHECKPOINT_PLACEHOLDER_OBSERVER_INTERNAL_ERROR"
                if field_reason != "CHECKPOINT_PLACEHOLDER_OBSERVER_INTERNAL_ERROR"
                else "CHECKPOINT_PLACEHOLDER_ARTIFACT_BOUND_EXCEEDED"
            ),
            "V2_CHECKPOINT_CONTEXT_FIELD_REASON_ONE_TO_ONE",
        )
    return sorted(cases, key=lambda item: item["mutation_case_id"])


def _build_inventory(repository_root: Path) -> dict[str, Any]:
    normative_documents: list[dict[str, Any]] = []
    normative_bytes: dict[str, bytes] = {}
    for document_role, path in NORMATIVE_DOCUMENT_INPUTS:
        try:
            raw = _bounded_repository_read(
                repository_root,
                path,
                maximum_octets=MAXIMUM_NORMATIVE_DOCUMENT_OCTETS,
            )
            _require(bool(raw), f"normative document is empty: {path}")
            raw.decode("utf-8")
        except (InventoryError, OSError, UnicodeError) as exc:
            raise InventoryError(
                f"cannot read normative document {path}: {exc}"
            ) from exc
        normative_bytes[path] = raw
        normative_documents.append(
            {
                "document_role": document_role,
                "repository_relative_path": path,
                "raw_octet_count": len(raw),
                "raw_sha256": _sha256_bytes(raw),
            }
        )
    _require(
        tuple(
            (
                item["document_role"],
                item["repository_relative_path"],
            )
            for item in normative_documents
        )
        == NORMATIVE_DOCUMENT_INPUTS,
        "normative documents are not in the exact V3 semantic order",
    )

    protocol_bytes = normative_bytes[PROTOCOL_PATH]
    protocol_text = protocol_bytes.decode("utf-8")
    parsed = _parse_protocol(protocol_text)
    registry, descriptor_metadata = _build_target_registry(parsed)
    counter_schema = _build_counter_schema(parsed)
    context_semantics = _context_semantics_invariants(
        parsed=parsed,
        metadata=descriptor_metadata,
        counter_schema=counter_schema,
    )
    marker_contract = _build_marker_contract(parsed)
    selector_catalog = _build_checkpoint_selector_catalog()
    oracle_profile = _build_ingress_logical_oracle_profile()
    external_schema_registry_v2 = _load_structural_registry(repository_root)
    specs = _build_operation_specs(oracle_profile)
    maximum_constraint_scope_profiles = _build_maximum_constraint_scope_profile_catalog(
        specs=specs,
        selector_catalog=selector_catalog,
        target_registry=registry,
        marker_contract=marker_contract,
    )
    declaration = _build_operation_declaration(specs)
    dispatch_window = _build_dispatch_window_evidence()
    due_clock = _build_due_decision_clock_evidence(dispatch_window)
    results = _build_operation_results(dispatch_window, due_clock, specs)
    observation_fixtures = _build_v2_observation_fixtures(
        registry_id=registry["target_field_registry_id"],
        metadata=descriptor_metadata,
        selector_catalog=selector_catalog,
    )
    mutation_metadata = _one_field_mutation_metadata()
    counter_snapshot = {
        "counter_schema_id": counter_schema["counter_schema_id"],
        "availability_bitmap": "1" * 66,
        "values": [0] * 66,
    }

    descriptors = registry["descriptors"]
    layer_counts = Counter(item["layer"] for item in descriptors)
    kind_counts = Counter(item["value_kind"] for item in descriptors)
    vocabularies = registry["ordered_vocabulary_definitions"]
    monotone_positions = [
        index
        for index, field_id in enumerate(counter_schema["ordered_counter_field_ids"])
        if field_id in set(counter_schema["monotone_counter_field_ids"])
    ]
    expected_monotone_positions = [
        *range(0, 6),
        *range(10, 16),
        *range(17, 19),
        *range(21, 27),
        *range(29, 66),
    ]
    _require(
        monotone_positions == expected_monotone_positions,
        "monotone counter positions differ from the frozen protocol",
    )
    field_ids = [item["field_id"] for item in descriptors]
    invariants = {
        "protocol_sha256": _sha256_bytes(protocol_bytes),
        "canonicalization_version": CANONICALIZATION_VERSION,
        "measurement_schema_version": MEASUREMENT_SCHEMA_VERSION,
        "semantic_preimage_node_count_limit": None,
        "counts": {
            "operation_kind_count": len(OPERATION_KINDS),
            "operation_spec_variant_count": len(SPEC_TYPES),
            "operation_result_variant_count": len(RESULT_TYPES),
            "removed_v1_tag_count": len(REMOVED_V1_TAGS),
            "descriptor_profile_count": len(parsed["profiles"]),
            "target_field_count": len(descriptors),
            "vocabulary_count": len(vocabularies),
            "vocabulary_member_count": sum(
                len(item["members"]) for item in vocabularies
            ),
            "marker_kind_count": len(parsed["markers"]),
            "full_checkpoint_marker_kind_count": len(parsed["checkpoint_markers"]),
            "observation_method_count": len(parsed["methods"]),
            "status_reason_count": len(STATUS_REASONS),
            "context_predicate_count": len(
                {
                    item["context_predicate"]
                    for item in registry["status_reason_policy_definition"][
                        "reason_rules"
                    ]
                    if item["context_predicate"] is not None
                }
            ),
            "availability_state_rule_count": len(
                registry["status_reason_policy_definition"]["availability_state_rules"]
            ),
            "status_reason_rule_count": len(
                registry["status_reason_policy_definition"]["reason_rules"]
            ),
            "error_form_definition_count": len(
                registry["status_reason_policy_definition"]["error_form_definitions"]
            ),
            "value_shape_definition_count": len(
                registry["ordered_value_shape_definitions"]
            ),
            "value_constraint_definition_count": len(
                registry["ordered_value_constraint_definitions"]
            ),
            "cross_field_constraint_definition_count": len(
                registry["ordered_cross_field_constraint_definitions"]
            ),
            "counter_field_count": len(counter_schema["ordered_counter_field_ids"]),
            "monotone_counter_field_count": len(
                counter_schema["monotone_counter_field_ids"]
            ),
            "nonmonotone_counter_field_count": len(MONOTONE_COUNTER_EXCLUSIONS),
            "off_target_observation_count": len(
                observation_fixtures["off_target_observations"]
            ),
            "off_field_observation_envelope_count": sum(
                len(item["field_observations"])
                for item in observation_fixtures["off_target_observations"]
            ),
            "source_error_detail_payload_member_count": len(
                SOURCE_ERROR_DETAIL_PAYLOAD_MEMBERS
            ),
            "null_attempt_field_count": len(parsed["null_attempt_fields"]),
            "null_attempt_profile_derived_field_count": context_semantics[
                "null_attempt"
            ]["profile_derived"]["count"],
            "compact_operation_local_field_count": context_semantics[
                "compact_coordinate_partition"
            ]["operation_local"]["count"],
            "compact_point_or_current_field_count": context_semantics[
                "compact_coordinate_partition"
            ]["point_or_current"]["count"],
            "off_static_available_field_count": context_semantics["off_mode"][
                "static_available"
            ]["count"],
            "checkpoint_operation_map_entry_count": context_semantics[
                "checkpoint_operation_map"
            ]["entry_count"],
            "checkpoint_selector_catalog_count": len(selector_catalog),
            "maximum_constraint_scope_profile_count": len(
                maximum_constraint_scope_profiles
            ),
            "maximum_result_scope_profile_count": sum(
                item["profile_kind"] == "OUTER_RESULT_BOUNDARY_FIXTURE"
                for item in maximum_constraint_scope_profiles
            ),
            "maximum_non_checkpoint_scope_profile_count": sum(
                item["profile_kind"] == "NON_CHECKPOINT_ROOT_FAMILY"
                for item in maximum_constraint_scope_profiles
            ),
            "maximum_checkpoint_scope_profile_count": sum(
                item["profile_kind"] == "CHECKPOINT_ROOT_COORDINATE"
                for item in maximum_constraint_scope_profiles
            ),
            "external_type_descriptor_count": external_schema_registry_v2[
                "external_type_descriptor_count"
            ],
            "normative_document_input_count": len(normative_documents),
            "one_field_mutation_case_count": len(mutation_metadata),
        },
        "target_field_layer_counts": {
            key: layer_counts[key] for key in sorted(layer_counts)
        },
        "target_field_value_kind_counts": {
            key: kind_counts[key] for key in sorted(kind_counts)
        },
        "target_field_ids_canonical_json_sha256": _sha256_bytes(
            _canonical_bytes(field_ids)
        ),
        "target_field_registry_id": registry["target_field_registry_id"],
        "target_field_registry_canonical_json_bytes": len(_canonical_bytes(registry)),
        "operation_counter_schema_id": counter_schema["counter_schema_id"],
        "exact_semantic_ids": {
            "target_field_registry_id": registry["target_field_registry_id"],
            "operation_counter_schema_id": counter_schema["counter_schema_id"],
            "marker_contract_id": marker_contract["marker_contract_id"],
            "logical_oracle_profile_id": oracle_profile["logical_oracle_profile_id"],
            "external_schema_registry_id": external_schema_registry_v2[
                "external_schema_registry_id"
            ],
        },
        "normative_document_sha256_by_role": {
            item["document_role"]: item["raw_sha256"] for item in normative_documents
        },
        "maximum_constraint_scope_profile_ids_canonical_json_sha256": (
            _sha256_bytes(
                _canonical_bytes(
                    [
                        item["maximum_constraint_scope_profile_id"]
                        for item in maximum_constraint_scope_profiles
                    ]
                )
            )
        ),
        "constructive_maxima_external_artifact_contract": {
            "intrinsic_byte_maximum_row_count": 66,
            "outer_result_byte_maximum_row_count": 4,
            "root_application_byte_maximum_row_count": 404,
            "total_byte_maximum_row_count": 474,
            "local_shutdown_counterexample_count": 1,
            "maximum_rows_embedded_in_inventory": False,
            "heuristic_bound_proofs_are_authority": False,
        },
        "inventory_schema_version": INVENTORY_SCHEMA_VERSION,
        "forbidden_downstream_identity_fields": [
            "admitted_plan_record_id",
            "candidate_id_as_inventory_identity",
            "target_bound_inventory_id",
            "target_bound_universe_manifest_id",
        ],
        "v1_removal_assertions": {
            "removed_tags": list(REMOVED_V1_TAGS),
            "removed_tags_absent_from_current_spec_map": not bool(
                set(REMOVED_V1_TAGS) & set(SPEC_TYPES.values())
            ),
            "removed_tags_absent_from_current_result_map": not bool(
                set(REMOVED_V1_TAGS) & set(RESULT_TYPES.values())
            ),
            "historical_v1_body_relabelled_with_v2_tag_rejects": True,
        },
        "frozen_byte_maxima": {
            "target_observation_strict_ceiling": TARGET_OBSERVATION_MAX_BYTES,
            "operation_result_strict_ceiling": OPERATION_RESULT_MAX_BYTES,
            "selector_length_maximum": 64,
            "target_observation_root_count_maximum": 67,
            "subscription_kernel_pair_count_maximum": 256,
        },
        "monotone_counter_zero_based_positions": monotone_positions,
        "context_semantics": context_semantics,
        "checkpoint_placeholder_reason_amendment": {
            "closure_facing_status_reason_count": len(STATUS_REASONS),
            "context_predicate_count": 6,
            "field_reason_by_context_reason": dict(
                sorted(CHECKPOINT_CONTEXT_TO_FIELD_REASON.items())
            ),
            "matching_v2_context_required": True,
        },
        "generated_boundary_proofs": {
            "standalone_envelope_collision_guard": (
                _standalone_envelope_collision_guard_self_test()
            ),
            "ingress_counts": {
                "parser_units": [0, 32_768],
                "completed_application_messages": [0, 32_768],
                "logical_output_frames": [0, 32_768],
                "logical_output_payload_octets": [0, 65_536],
                "exact_plus_one_rejects": True,
            },
            "selector_lengths": {
                "accepted": [0, 64],
                "rejected": [65],
            },
            "root_counts": {"accepted": [3, 67], "rejected": [68]},
            "subscription_kernel_pair_cardinalities": {
                "accepted": [1, 256],
                "rejected": [257],
            },
            "local_shutdown_limit_relation_cases": (
                _local_shutdown_limit_relation_boundary_cases()
            ),
            "checkpoint_binding_state_count": len(CHECKPOINT_BINDING_STATUSES),
        },
    }
    _require(
        invariants["target_field_ids_canonical_json_sha256"]
        == "6f1dec4190415c1046a0a08356c2717463453f4a5ec3a5a45ea5e73bfb44348d",
        "canonical target-field-ID tuple digest drifted",
    )

    _require(
        invariants["counts"]["status_reason_count"] == 26,
        "closure-facing status reason count must be 26",
    )
    _require(
        invariants["counts"]["context_predicate_count"] == 6,
        "context predicate count must be 6",
    )

    fixture_records = {
        "operation_specs": specs,
        "operation_declaration": declaration,
        "dispatch_window_evidence": dispatch_window,
        "due_decision_clock_evidence": due_clock,
        "operation_results": results,
        "target_observation_v2_fixtures": observation_fixtures,
        "counter_snapshot": counter_snapshot,
        "local_shutdown_boundary_spec": specs["LOCAL_SHUTDOWN"],
        "one_field_mutation_metadata": mutation_metadata,
    }

    inventory = {
        "schema_version": INVENTORY_SCHEMA_VERSION,
        "normative_document_inputs": normative_documents,
        "invariants": invariants,
        "target_field_registry": registry,
        "operation_counter_schema": counter_schema,
        "marker_contract": marker_contract,
        "checkpoint_selector_catalog": selector_catalog,
        "ingress_logical_oracle_profile_catalog": [oracle_profile],
        "external_schema_registry_v2": external_schema_registry_v2,
        "operation_contracts": _operation_contracts(
            maximum_constraint_scope_profiles=(maximum_constraint_scope_profiles)
        ),
        "fixture_records": fixture_records,
    }
    _revalidate_source_snapshot(
        repository_root,
        normative_bytes=normative_bytes,
        structural_registry=external_schema_registry_v2,
    )
    inventory["inventory_sha256"] = _sha256_bytes(_canonical_bytes(inventory))
    _require(
        frozenset(inventory) == INVENTORY_ROOT_KEYS,
        "inventory root shape drifted",
    )
    inventory_without_identity = dict(inventory)
    inventory_without_identity.pop("inventory_sha256")
    _require(
        inventory["inventory_sha256"]
        == _sha256_bytes(_canonical_bytes(inventory_without_identity)),
        "inventory identity does not commit the exact root without itself",
    )
    return inventory


def _render_inventory(inventory: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            inventory,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")


def _resolve_output(repository_root: Path, output: Path) -> Path:
    candidate = output if output.is_absolute() else repository_root / output
    try:
        relative = candidate.relative_to(repository_root)
    except ValueError as exc:
        raise InventoryError("output path escapes the repository") from exc
    _require(
        relative.parts and all(part not in {"", ".", ".."} for part in relative.parts),
        "output path is not an exact repository-relative path",
    )
    _require(
        relative.as_posix() == DEFAULT_OUTPUT
        or (len(relative.parts) >= 2 and relative.parts[0] == "test_output"),
        "output path is outside the canonical or test-output publication roots",
    )
    resolved = repository_root.joinpath(*relative.parts)
    parent_descriptor = _open_repository_directory_fd(
        repository_root,
        relative.parts[:-1],
        label="repository output",
    )
    try:
        try:
            metadata = os.stat(
                relative.parts[-1],
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            metadata = None
        if metadata is not None:
            _require(
                stat.S_ISREG(metadata.st_mode),
                "existing output path is not a regular file",
            )
    finally:
        os.close(parent_descriptor)
    return resolved


def _output_entry_fingerprint(
    parent_descriptor: int,
    leaf_name: str,
) -> tuple[int, int, int, int, int, int] | None:
    try:
        metadata = os.stat(
            leaf_name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return None
    _require(
        stat.S_ISREG(metadata.st_mode),
        "existing output path is not a regular file",
    )
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _atomic_write_repository_output(
    repository_root: Path,
    output: Path,
    rendered: bytes,
) -> None:
    try:
        relative = output.relative_to(repository_root)
    except ValueError as exc:  # pragma: no cover - guarded by _resolve_output
        raise InventoryError("output path escapes the repository") from exc
    parent_descriptor = _open_repository_directory_fd(
        repository_root,
        relative.parts[:-1],
        label="repository output",
    )
    parent_fingerprint = _directory_fd_fingerprint(parent_descriptor)
    leaf_name = relative.parts[-1]
    temporary_name: str | None = None
    temporary_descriptor: int | None = None
    temporary_identity: tuple[int, int] | None = None
    renamed = False
    try:
        original_fingerprint = _output_entry_fingerprint(
            parent_descriptor,
            leaf_name,
        )
        temporary_flags = os.O_RDWR | os.O_CREAT | os.O_EXCL
        temporary_flags |= getattr(os, "O_CLOEXEC", 0)
        temporary_flags |= getattr(os, "O_NOFOLLOW", 0)
        for _ in range(32):
            candidate_name = f".{leaf_name}.tmp.{os.getpid()}.{secrets.token_hex(16)}"
            try:
                temporary_descriptor = os.open(
                    candidate_name,
                    temporary_flags,
                    0o600,
                    dir_fd=parent_descriptor,
                )
            except FileExistsError:
                continue
            temporary_name = candidate_name
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
        temporary_identity = (
            temporary_metadata.st_dev,
            temporary_metadata.st_ino,
        )
        os.lseek(temporary_descriptor, 0, os.SEEK_SET)
        verified_chunks: list[bytes] = []
        verified_octets = 0
        while verified_octets < len(rendered):
            chunk = os.read(
                temporary_descriptor,
                min(65_536, len(rendered) - verified_octets),
            )
            _require(bool(chunk), "atomic output temporary was truncated")
            verified_chunks.append(chunk)
            verified_octets += len(chunk)
        _require(
            b"".join(verified_chunks) == rendered,
            "atomic output temporary bytes differ",
        )
        os.close(temporary_descriptor)
        temporary_descriptor = None

        _require(
            _output_entry_fingerprint(parent_descriptor, leaf_name)
            == original_fingerprint,
            "output path identity changed before atomic replacement",
        )
        _require(
            _current_repository_directory_fingerprint(
                repository_root,
                relative.parts[:-1],
                label="repository output",
            )
            == parent_fingerprint,
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
        final_descriptor = os.open(
            leaf_name,
            final_flags,
            dir_fd=parent_descriptor,
        )
        try:
            final_before = os.fstat(final_descriptor)
            _require(
                stat.S_ISREG(final_before.st_mode)
                and final_before.st_size == len(rendered),
                "atomically published output metadata differs",
            )
            _require(
                (final_before.st_dev, final_before.st_ino) == temporary_identity,
                "atomically published output identity differs from temporary",
            )
            final_chunks: list[bytes] = []
            final_octets = 0
            while final_octets < len(rendered):
                chunk = os.read(
                    final_descriptor,
                    min(65_536, len(rendered) - final_octets),
                )
                _require(bool(chunk), "atomically published output was truncated")
                final_chunks.append(chunk)
                final_octets += len(chunk)
            final_after = os.fstat(final_descriptor)
            _require(
                (
                    final_before.st_dev,
                    final_before.st_ino,
                    final_before.st_mode,
                    final_before.st_size,
                    final_before.st_mtime_ns,
                    final_before.st_ctime_ns,
                )
                == (
                    final_after.st_dev,
                    final_after.st_ino,
                    final_after.st_mode,
                    final_after.st_size,
                    final_after.st_mtime_ns,
                    final_after.st_ctime_ns,
                )
                and b"".join(final_chunks) == rendered,
                "atomically published output bytes or identity differ",
            )
            final_path = os.stat(
                leaf_name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
            _require(
                stat.S_ISREG(final_path.st_mode)
                and (final_path.st_dev, final_path.st_ino, final_path.st_size)
                == (final_after.st_dev, final_after.st_ino, final_after.st_size),
                "atomically published output path identity changed",
            )
        finally:
            os.close(final_descriptor)
        _require(
            _current_repository_directory_fingerprint(
                repository_root,
                relative.parts[:-1],
                label="repository output",
            )
            == parent_fingerprint,
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
    mode.add_argument("--check", action="store_true", help="check the frozen JSON")
    mode.add_argument("--write", action="store_true", help="write the frozen JSON")
    mode.add_argument(
        "--check-external-schema-v2-foundation",
        action="store_true",
        help=(
            "validate and report the isolated external-schema V2 Unicode "
            "foundation without building or replacing the V3 golden"
        ),
    )
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path(DEFAULT_OUTPUT))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        repository_root = args.repository_root.resolve(strict=True)
        if not repository_root.is_dir():
            raise InventoryError("repository root is not a directory")
        if args.check_external_schema_v2_foundation:
            report = _build_external_schema_v2_foundation_report(repository_root)
            print(_canonical_bytes(report).decode("utf-8"))
            return 0
        output = _resolve_output(repository_root, args.output)
        inventory = _build_inventory(repository_root)
        rendered = _render_inventory(inventory)
        if args.write:
            _atomic_write_repository_output(repository_root, output, rendered)
            action = "wrote"
        else:
            try:
                relative_output = output.relative_to(repository_root).as_posix()
                actual = _bounded_repository_read(
                    repository_root,
                    relative_output,
                    maximum_octets=len(rendered),
                    expected_octets=len(rendered),
                )
            except (InventoryError, OSError, ValueError) as exc:
                raise InventoryError(f"cannot read frozen inventory: {exc}") from exc
            if actual != rendered:
                raise InventoryError(
                    "frozen inventory differs from the independently regenerated bytes; "
                    "review the protocol delta and run --write explicitly"
                )
            action = "checked"
        print(
            f"{action} {output}: registry="
            f"{inventory['external_schema_registry_v2']['external_schema_registry_id']} "
            f"inventory={inventory['inventory_sha256']} "
            f"fields={inventory['invariants']['counts']['target_field_count']} "
            f"counter_fields={inventory['invariants']['counts']['counter_field_count']} "
            "maximum_scope_profiles="
            f"{inventory['invariants']['counts']['maximum_constraint_scope_profile_count']} "
            "constructive_maxima=pending"
        )
        return 0
    except (InventoryError, OSError, RuntimeError) as exc:
        print(f"Raw-V8 Step-2 inventory error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
